"""Read-only skinning audit of the rejected H04 partial bytes; no Blender/GPU production."""

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[4]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

from pathlib import Path
import hashlib,json,struct,io,math,sys,argparse
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[4]
BASE=Path(str(_XEXORIA_AGENT_OUTPUT / '20261004-heroes04-06-compact-r01'))
parser=argparse.ArgumentParser();parser.add_argument('--file',type=Path);parser.add_argument('--out',type=Path);parser.add_argument('--hero',default='04');parser.add_argument('--diagnose',action='store_true');parser.add_argument('--dense',action='store_true');parser.add_argument('--hz',type=int,default=60)
args=parser.parse_args()
FILE=args.file or BASE/'04/hero04_acolyte_lod0.glb'
OUT=args.out or ROOT/'planning/evidence/heroes-six-20261004/continuation/heroes04-06-rig-partial-audit.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
data=FILE.read_bytes();n=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+n]);bin=data[28+n:]
def acc(index):
 a=doc['accessors'][index];assert not a.get('sparse');v=doc['bufferViews'][a['bufferView']]
 dt=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]);width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
 result=np.ndarray((a['count'],width),dtype=dt,buffer=bin,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',dt.itemsize*width),dt.itemsize)).copy()
 if a.get('normalized') and a['componentType']!=5126:result=result.astype(float)/np.iinfo(dt).max
 return result
def mat_tqs(t,r,s):
 x,y,z,w=r;q=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]],dtype=float)
 m=np.eye(4);m[:3,:3]=q@np.diag(s);m[:3,3]=t;return m
parents={child:i for i,node in enumerate(doc['nodes']) for child in node.get('children',[])}
def worlds(overrides):
 cache={}
 def node(i):
  if i in cache:return cache[i]
  row=doc['nodes'][i];o=overrides.get(i,{})
  local=np.array(row['matrix'],dtype=float).reshape(4,4).T if 'matrix' in row and not o else mat_tqs(o.get('translation',row.get('translation',[0,0,0])),o.get('rotation',row.get('rotation',[0,0,0,1])),o.get('scale',row.get('scale',[1,1,1])))
  cache[i]=(node(parents[i]) if i in parents else np.eye(4))@local;return cache[i]
 for i in range(len(doc['nodes'])):node(i)
 return cache
def evaluate(animation,t):
 override={}
 for channel in animation['channels']:
  sampler=animation['samplers'][channel['sampler']];times=acc(sampler['input']).ravel();values=acc(sampler['output']).astype(float)
  assert sampler.get('interpolation','LINEAR') in ['LINEAR','STEP']
  hi=min(len(times)-1,int(np.searchsorted(times,t,side='right')));lo=max(0,hi-1)
  if t>=times[-1]:lo=hi=len(times)-1
  w=0 if hi==lo else float((t-times[lo])/(times[hi]-times[lo]));w=max(0,min(1,w))
  a,b=values[lo],values[hi];path=channel['target']['path']
  if sampler.get('interpolation')=='STEP':value=a
  elif path=='rotation':
   if np.dot(a,b)<0:b=-b
   dot=float(np.clip(np.dot(a,b),-1,1))
   if dot>.9995:value=a+(b-a)*w
   else:angle=math.acos(dot);value=(math.sin((1-w)*angle)*a+math.sin(w*angle)*b)/math.sin(angle)
   value=value/np.linalg.norm(value)
  else:value=a+(b-a)*w
  override.setdefault(channel['target']['node'],{})[path]=value
 return worlds(override)
primitive=doc['meshes'][0]['primitives'][0];attributes=primitive['attributes']
position=acc(attributes['POSITION']).astype(float);normal=acc(attributes['NORMAL']).astype(float);uv=acc(attributes['TEXCOORD_0']).astype(float)
joint=acc(attributes['JOINTS_0']).astype(int);weight=acc(attributes['WEIGHTS_0']).astype(float);indices=acc(primitive['indices']).ravel().astype(int)
skin=doc['skins'][0];names=[doc['nodes'][i]['name'] for i in skin['joints']];inverse=np.array([row.reshape(4,4).T for row in acc(skin['inverseBindMatrices']).astype(float)])
homogeneous=np.column_stack((position,np.ones(len(position))))
edges=np.unique(np.sort(np.concatenate([indices.reshape(-1,3)[:,[0,1]],indices.reshape(-1,3)[:,[1,2]],indices.reshape(-1,3)[:,[2,0]]]),axis=1),axis=0)
length=np.linalg.norm(position[edges[:,0]]-position[edges[:,1]],axis=1);valid=length>.002
root_index=next(i for i,row in enumerate(doc['nodes']) if row.get('name')=='root');rest=worlds({})
foot_ids={side:[i for i,n in enumerate(names) if n in [f'foot.{side}',f'toe.{side}']] for side in ['L','R']}
foot_masks={side:np.sum(np.where(np.isin(joint,ids),weight,0),axis=1)>.5 for side,ids in foot_ids.items()}
def posed(matrices):
 m=np.array([matrices[i] for i in skin['joints']])@inverse
 points=np.zeros((len(position),4))
 for k in range(4):points+=np.einsum('nij,nj->ni',m[joint[:,k]],homogeneous)*weight[:,k,None]
 return points[:,:3]
bind=posed(rest);clips=[]
for animation in doc.get('animations',[]):
 duration=max(float(acc(s['input'])[-1,0]) for s in animation['samplers']);samples=[]
 times=np.linspace(0,duration,math.ceil(duration*args.hz)+1).tolist() if args.dense else np.linspace(0,duration,21).tolist()
 for t in sorted(set(times+([.1] if animation['name'].startswith('heavy_1h') else []))):
  matrices=evaluate(animation,t);points=posed(matrices);stretch=np.linalg.norm(points[edges[:,0]]-points[edges[:,1]],axis=1)[valid]/length[valid]
  samples.append({'time_s':t,'floor_min_m':float(points[:,1].min()),'height_m':float(np.ptp(points[:,1])),
                  'root_drift_m':float(np.linalg.norm(matrices[root_index][:3,3]-rest[root_index][:3,3])),
                  'edge_stretch_p99':float(np.quantile(stretch,.99)),'edges_over_2x':int((stretch>2).sum()),
                  'feet':{side:{'min_y_m':float(points[mask,1].min()),'max_y_m':float(points[mask,1].max()),'centroid':points[mask].mean(0).tolist()} for side,mask in foot_masks.items()}})
 clips.append({'name':animation['name'],'duration_s':duration,'sample_count':len(samples),'worst_floor_m':min(s['floor_min_m'] for s in samples),
               'max_root_drift_m':max(s['root_drift_m'] for s in samples),'max_edge_stretch_p99':max(s['edge_stretch_p99'] for s in samples),
               'floor_candidate_gate':min(s['floor_min_m'] for s in samples)>=-.001,
               'deformation_candidate_gate':max(s['edge_stretch_p99'] for s in samples)<=2.0,'samples':samples})
images=[]
for image in doc['images']:
 view=doc['bufferViews'][image['bufferView']];raw=bin[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']]
 with Image.open(io.BytesIO(raw)) as im:size=list(im.size);mode=im.mode
 images.append({'mime':image['mimeType'],'size':size,'mode':mode,'sha256':hashlib.sha256(raw).hexdigest()})
source_paths=[Path(str(_XEXORIA_ASSET_SOURCE / f'sources/tripo/hero-{hero}/texture4k-pbr-20261004/{stem}.glb')) for hero,stem in [('04','hero04-P2-smartuv-4k-pbr-9b2d0fd3'),('06','hero06-P2-smartuv-4k-pbr-59405068')]]
record={'schema':'xexoria.compact-partial-byte-audit/1','hero':args.hero,'status':'STAGED_RIG_CANDIDATE_UNVERIFIED_NATIVE','file':str(FILE),'bytes':FILE.stat().st_size,'sha256':sha(FILE),
 'facts':{'triangles':len(indices)//3,'vertices':len(position),'joints':len(names),'joint_names':names,'clips':len(clips),
          'images':images,'material':doc['materials'],'uv_range':{'min':uv.min(0).tolist(),'max':uv.max(0).tolist()},
          'all_attributes_finite':bool(all(np.isfinite(a).all() for a in [position,normal,uv,weight,inverse])),
          'indices_valid':bool((indices>=0).all() and (indices<len(position)).all()),'skin_joint_indices_valid':bool((joint>=0).all() and (joint<len(names)).all()),
          'max_influences':int((weight>1e-7).sum(1).max()),'max_weight_sum_error':float(np.max(np.abs(weight.sum(1)-1))),
          'max_normal_length_error':float(np.max(np.abs(np.linalg.norm(normal,axis=1)-1))),
          'rest_skin_max_position_deviation_m':float(np.max(np.linalg.norm(bind-position,axis=1))),
          'geometry_triangle_cap_pass':len(indices)//3<=5500,'geometry_vertex_cap_pass':len(position)<=5000},
 'actual_exported_skinning':clips,'sampling':f'{args.hz}Hz actual exported SLERP/linear interpolation' if args.dense else '21 actual exported samples per clip',
 'immutable_source_hashes':{str(p):sha(p) for p in source_paths},
 'limits':['Actual-byte numeric skinning only. No native renderer, weapon, PBR appearance or costume-collision acceptance.',
           'Bone counts and starter clips do not make an asset game-ready; weapon/costume/face and actual controller foot locking remain unverified.']}
record['failed_candidate_gates']=[]
if not record['facts']['geometry_vertex_cap_pass']:record['failed_candidate_gates'].append('LOD0_vertices_above5000')
for clip in clips:
 if not clip['floor_candidate_gate']:record['failed_candidate_gates'].append(clip['name']+':floor_below_minus1mm')
 if not clip['deformation_candidate_gate']:record['failed_candidate_gates'].append(clip['name']+':p99_edge_stretch_above2x')
if record['failed_candidate_gates']:record['status']='REJECTED_CANDIDATE_GATES'
if '--diagnose' in sys.argv:
 diagnosis=[]
 for clip in clips:
  if clip['name'] not in ['base.run','heavy_1h.attack_1','death','dodge']:continue
  sample=max(clip['samples'],key=lambda s:s['edge_stretch_p99']);animation=next(a for a in doc['animations'] if a['name']==clip['name']);points=posed(evaluate(animation,sample['time_s']))
  ratio=np.linalg.norm(points[edges[:,0]]-points[edges[:,1]],axis=1)/np.maximum(length,1e-12);bad=np.where(valid&(ratio>2))[0]
  mid=(position[edges[bad,0]]+position[edges[bad,1]])/2
  zone={}
  for midpoint in mid:
   label=('head' if midpoint[1]>1.75 else 'shoulder_neck' if midpoint[1]>1.55 else 'arm_torso' if midpoint[1]>1.20 else 'hips_hands' if midpoint[1]>.9 else 'robe_legs')
   zone[label]=zone.get(label,0)+1
  rows=[]
  for edge_index in sorted(bad,key=lambda k:-ratio[k])[:20]:
   pair=edges[edge_index];rows.append({'vertices':pair.tolist(),'ratio':float(ratio[edge_index]),'bind_length_m':float(length[edge_index]),'bind_mid_glTF':((position[pair[0]]+position[pair[1]])/2).tolist(),
    'weights':[[[names[int(j)],float(w)] for j,w in zip(joint[vi],weight[vi]) if w>.01] for vi in pair]})
  diagnosis.append({'clip':clip['name'],'time_s':sample['time_s'],'edges_over_2x_by_zone':zone,'largest_edges':rows})
 target=OUT.with_name(OUT.stem+'-diagnosis.json') if args.out else OUT.with_name('heroes04-06-rig-partial-diagnosis.json');assert not target.exists();target.write_text(json.dumps(diagnosis,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps([{'clip':r['clip'],'zones':r['edges_over_2x_by_zone'],'top5':r['largest_edges'][:5]} for r in diagnosis]))
else:
 assert not OUT.exists(),'Immutable partial audit already exists';OUT.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':record['status'],'facts':{k:record['facts'][k] for k in ['triangles','vertices','joints','clips','max_influences','max_weight_sum_error','rest_skin_max_position_deviation_m']},
                   'clips':[{'name':c['name'],'floor':c['worst_floor_m'],'root':c['max_root_drift_m'],'stretch_p99':c['max_edge_stretch_p99']} for c in clips]}))
