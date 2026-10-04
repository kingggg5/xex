"""Read-only immutable GLB and animation intake for compact hero04/06 candidates."""

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[4]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import hashlib,json,struct,io
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'planning/evidence/heroes-six-20261004/continuation/heroes04-06-rig-intake.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read_glb(p):
 data=Path(p).read_bytes();length=struct.unpack_from('<I',data,12)[0]
 doc=json.loads(data[20:20+length]);return doc,data[28+length:]
def accessor(doc,bin,index):
 a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
 types={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'};sizes={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}
 dtype=np.dtype(types[a['componentType']]);stride=v.get('byteStride',dtype.itemsize*sizes[a['type']])
 return np.ndarray((a['count'],sizes[a['type']]),dtype=dtype,buffer=bin,
                   offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(stride,dtype.itemsize)).copy()
records=[]
for hero,stem,pinned in [('04','hero04-P2-smartuv-4k-pbr-9b2d0fd3','92e22dc8fed0cca1a06fb8fc6eb1d789086e77aa004a3e47a62be5eb8310cba4'),
                         ('06','hero06-P2-smartuv-4k-pbr-59405068','8dadd6e9981bfcbaeff45ba21c2156c188e39c189ae8a9510f4144e3f5587651')]:
 p=Path(str(_XEXORIA_ASSET_SOURCE / f'sources/tripo/hero-{hero}/texture4k-pbr-20261004/{stem}.glb'))
 assert sha(p)==pinned
 doc,bin=read_glb(p);primitive=doc['meshes'][0]['primitives'][0]
 pos=accessor(doc,bin,primitive['attributes']['POSITION']);indices=accessor(doc,bin,primitive['indices']).ravel()
 # glTF+Y-up to Blender+Z-up for the documented forward axis, no source mutation.
 co=pos[:,[0,2,1]].astype(float);co[:,1]*=-1
 images=[]
 for image in doc.get('images',[]):
  view=doc['bufferViews'][image['bufferView']];raw=bin[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']]
  with Image.open(io.BytesIO(raw)) as im:size=list(im.size);mode=im.mode
  images.append({'name':image.get('name'),'mime':image['mimeType'],'native_size':size,'mode':mode,'sha256':hashlib.sha256(raw).hexdigest()})
 parent=np.arange(len(co))
 def find(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 def union(a,b):
  a,b=find(int(a)),find(int(b))
  if a!=b:parent[b]=a
 for tri in indices.reshape(-1,3):union(tri[0],tri[1]);union(tri[1],tri[2])
 coincident={}
 for i,point in enumerate(co):
  key=tuple(np.round(point,5))
  if key in coincident:union(i,coincident[key])
  else:coincident[key]=i
 comps={}
 for i in range(len(co)):comps.setdefault(find(i),[]).append(i)
 components=[]
 for comp in comps.values():
  pts=co[comp];components.append({'vertices':len(comp),'min':pts.min(0).tolist(),'max':pts.max(0).tolist(),'centroid':pts.mean(0).tolist()})
 material=doc['materials'][primitive.get('material',0)]
 records.append({'hero':hero,'source':str(p),'sha256':pinned,'bytes':p.stat().st_size,
                 'triangles':len(indices)//3,'exported_vertices':len(pos),'unique_positions':len(coincident),
                 'attributes':primitive['attributes'],'blender_bounds':{'min':co.min(0).tolist(),'max':co.max(0).tolist()},
                 'images':images,'material':material,'textures':doc.get('textures',[]),
                 'seam_linked_components':len(components),'largest_components':sorted(components,key=lambda c:-c['vertices'])[:40]})
ual=ROOT/'assets/models/heroes/hero02/source/third-party/ual1-standard-2025-06-10'
provenance=json.loads((ual/'provenance.json').read_text(encoding='utf-8-sig'))
for item in provenance['files']:assert sha(ual/item['file'])==item['sha256']
names=[a['name'] for a in json.loads((ual/'AnimationLibrary_Godot_Standard.gltf').read_text())['animations']]
receipt={'schema':'xexoria.compact-hero-intake/1','heroes':records,'ual':{'path':str(ual),'licence':provenance['licence'],'clips':names,'immutable_rechecked':True},
         'budgets':{'lod0_triangles':5500,'lod0_vertices':5000,'lod1_triangles':3000,'lod2_triangles':1200,'joints':60,'influences':4},
         'status':'PREPARATION_NO_BLENDER_OR_RUNTIME_ACCEPTANCE'}
assert not OUT.exists(),'Immutable intake already exists'
OUT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'heroes':[{k:r[k] for k in ['hero','triangles','exported_vertices','unique_positions','seam_linked_components']} for r in records],'ual_clips':names}))
