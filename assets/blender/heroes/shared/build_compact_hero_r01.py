"""Original-source fitted XS1 rig candidates for H04/H06; CPU only, immutable intake.

Uses the reviewed native heat-cage and idle-reference UAL retarget methods, never
another hero's mesh or weights. Geometry/material/animation candidates need native review.
"""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[4]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import argparse,hashlib,json,math,shutil,struct,sys,colorsys
from pathlib import Path
sys.dont_write_bytecode=True
import bpy,numpy as np
from mathutils import Matrix,Quaternion,Vector
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'assets/blender/heroes/hero02'))
import h02_xs1 as X
import h02_animlib as A
UAL=ROOT/'assets/models/heroes/hero02/source/third-party/ual1-standard-2025-06-10'
DEFAULT_OUT=Path(str(_XEXORIA_AGENT_OUTPUT / '20261004-heroes04-06-compact-r01'))
P=argparse.ArgumentParser();P.add_argument('--hero',choices=['04','06','both'],default='both');P.add_argument('--out',type=Path,default=DEFAULT_OUT)
P.add_argument('--lod0-target',type=int,default=5300)
args=P.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
CONFIG={
 '04':{'role':'acolyte','crown':2.05,'crown_fraction':.972,'stem':'hero04-P2-smartuv-4k-pbr-9b2d0fd3','sha':'92e22dc8fed0cca1a06fb8fc6eb1d789086e77aa004a3e47a62be5eb8310cba4','triangles':24426,
       'hips':.51,'shoulder':(.198,.018,.80),'elbow':(.262,-.010,.635),'wrist':(.282,-.033,.515),'knuckle':(.287,-.057,.465),'thigh_x':.115,'knee':(.133,.005,.285),'ankle':(.153,.027,.105),'toe_y':-.108,
       'gait':.55,'arm_swing':.50},
 '06':{'role':'tinker','crown':1.72,'crown_fraction':.974,'stem':'hero06-P2-smartuv-4k-pbr-59405068','sha':'8dadd6e9981bfcbaeff45ba21c2156c188e39c189ae8a9510f4144e3f5587651','triangles':24622,
       'hips':.525,'shoulder':(.131,.000,.80),'elbow':(.204,-.008,.638),'wrist':(.247,-.014,.529),'knuckle':(.253,-.036,.481),'thigh_x':.080,'knee':(.110,.000,.287),'ankle':(.112,.025,.085),'toe_y':-.115,
       'gait':.80,'arm_swing':.70}}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def select(objs,active=None):
 bpy.ops.object.select_all(action='DESELECT')
 for obj in objs:obj.select_set(True)
 bpy.context.view_layer.objects.active=active or objs[0]
def smooth(a,b,x):
 t=max(0,min(1,(x-a)/(b-a)));return t*t*(3-2*t)
def glb_facts(p):
 b=Path(p).read_bytes();n=struct.unpack_from('<I',b,12)[0];j=json.loads(b[20:20+n]);pr=[p for m in j['meshes'] for p in m['primitives']]
 return {'triangles':sum(j['accessors'][p['indices']]['count']//3 for p in pr),'vertices':sum(j['accessors'][p['attributes']['POSITION']]['count'] for p in pr),
         'joints':[[j['nodes'][n].get('name') for n in s['joints']] for s in j.get('skins',[])],'clips':[a.get('name') for a in j.get('animations',[])],
         'has_uv0':all('TEXCOORD_0' in p['attributes'] for p in pr),'images':len(j.get('images',[])),'materials':len(j.get('materials',[]))}
provenance=json.loads((UAL/'provenance.json').read_text(encoding='utf-8-sig'))
assert provenance['licence']=='CC0-1.0'
for row in provenance['files']:assert sha(UAL/row['file'])==row['sha256'],'UAL provenance changed'
assert shutil.disk_usage(args.out.parent).free>250_000_000
args.out.mkdir(parents=True,exist_ok=True)
for hero in ([args.hero] if args.hero!='both' else ['04','06']):
 c=CONFIG[hero];prefix=f'hero{hero}_{c["role"]}'
 source=Path(str(_XEXORIA_ASSET_SOURCE / f'sources/tripo/hero-{hero}/texture4k-pbr-20261004/{c["stem"]}.glb'))
 assert sha(source)==c['sha'],'Original source changed'
 out=args.out/hero;out.mkdir(exist_ok=True)
 assert not (out/'receipt.json').exists(),'Versioned candidate already exists'
 bpy.ops.wm.read_factory_settings(use_empty=True);scn=bpy.context.scene;scn.render.fps=30;scn.render.fps_base=1
 scn.render.threads_mode='FIXED';scn.render.threads=2
 print('COMPACT_STAGE',hero,'original_intake',flush=True)
 bpy.ops.import_scene.gltf(filepath=str(source),merge_vertices=False,import_shading='NORMALS')
 body=next(o for o in scn.objects if o.type=='MESH');assert sum(o.type=='MESH' for o in scn.objects)==1
 body.name=prefix+'_original_candidate';world=body.matrix_world.copy()
 raw=np.array([tuple(world@v.co) for v in body.data.vertices],dtype=float);lo,hi=raw.min(0),raw.max(0)
 full_height=(hi[2]-lo[2])*c['crown_fraction'];scale=c['crown']/full_height;H=(hi[2]-lo[2])*scale
 pivot=np.array([(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]])
 co=(raw-pivot)*scale;body.parent=None;body.matrix_world=Matrix.Identity(4);body.data.vertices.foreach_set('co',co.ravel());body.data.update()
 body.data.calc_loop_triangles();assert len(body.data.loop_triangles)==c['triangles'];assert len(body.data.uv_layers)>=1
 # The atlas resampling is an explicitly authorized lossy optimization; source bytes stay immutable.
 images=[];texture_roles={}
 for mat in body.data.materials:
  assert mat and mat.use_nodes
  for node in mat.node_tree.nodes:
   if node.type=='TEX_IMAGE' and node.image:
    im=node.image
    if im not in images:images.append(im)
    role='data'
    for link in node.outputs['Color'].links:
     if link.to_socket.name=='Base Color':role='albedo'
     if link.to_node.type=='NORMAL_MAP':role='normal'
     if link.to_node.type in ('SEPARATE_COLOR','SEPRGB'):role='orm'
    if role=='data' and im.colorspace_settings.name=='sRGB':role='albedo'
    texture_roles[im.name]=role
 assert len(images)==3,'Expected the original3PBRmaps'
 for im in images:
  role=texture_roles[im.name];target=1024 if role=='orm' else 2048
  original_size=list(im.size);assert original_size==[4096,4096]
  im.scale(target,target);im.pack();im['xex_original_size']=json.dumps(original_size);im['xex_role']=role
 assert sorted(list(im.size) for im in images)==[[1024,1024],[2048,2048],[2048,2048]],texture_roles
 for poly in body.data.polygons:poly.use_smooth=True
 semantic_hsv=None
 if hero in ['04','06']:
  # Source albedo helps distinguish the joined orange apron/hair from the dark body.
  # This is a read-only weight-classification guide, never a repaint of the atlas.
  color_image=next(im for im in images if texture_roles[im.name]=='albedo')
  pixels=np.empty(len(color_image.pixels),dtype=np.float32);color_image.pixels.foreach_get(pixels)
  pixels=pixels.reshape((color_image.size[1],color_image.size[0],4));uv=np.zeros((len(co),2),dtype=float)
  for loop in body.data.loops:uv[loop.vertex_index]=body.data.uv_layers.active.data[loop.index].uv
  x=np.clip((uv[:,0]*color_image.size[0]).astype(int),0,color_image.size[0]-1);y=np.clip((uv[:,1]*color_image.size[1]).astype(int),0,color_image.size[1]-1)
  rgb=np.maximum(pixels[y,x,:3],0);rgb=np.where(rgb<=.0031308,12.92*rgb,1.055*np.power(rgb,1/2.4)-.055)
  semantic_hsv=np.array([colorsys.rgb_to_hsv(*row) for row in rgb]);del pixels,rgb,uv
 def v(x,y,z):return Vector((x*H,y*H,z*H))
 hips=c['hips'];specs={'root':(v(0,0,0),v(0,0,.10)),'hips':(v(0,.008,hips),v(0,.008,hips+.085)),
  'spine':(v(0,.008,hips+.085),v(0,.008,.68)),'chest':(v(0,.008,.68),v(0,.006,.745)),
  'upper_chest':(v(0,.006,.745),v(0,.005,.82)),'neck':(v(0,.005,.82),v(0,-.003,.875)),
  'head':(v(0,-.003,.875),v(0,-.014,c['crown_fraction']))}
 for side,sign in [('L',1),('R',-1)]:
  shoulder=v(sign*c['shoulder'][0],c['shoulder'][1],c['shoulder'][2]);elbow=v(sign*c['elbow'][0],c['elbow'][1],c['elbow'][2]);wrist=v(sign*c['wrist'][0],c['wrist'][1],c['wrist'][2]);knuckle=v(sign*c['knuckle'][0],c['knuckle'][1],c['knuckle'][2])
  specs.update({f'shoulder.{side}':(v(sign*.07,.006,c['shoulder'][2]),shoulder),f'upper_arm.{side}':(shoulder,elbow),
   f'upper_arm_twist.{side}':(shoulder.lerp(elbow,.30),shoulder.lerp(elbow,.60)),f'forearm.{side}':(elbow,wrist),
   f'forearm_twist.{side}':(elbow.lerp(wrist,.60),elbow.lerp(wrist,.95)),f'hand.{side}':(wrist,knuckle),
   f'pauldron.{side}':(shoulder+v(0,0,.025),shoulder+v(sign*.055,0,.025)),
   f'socket_weapon_{side}':(knuckle+v(-sign*.008,-.015,.015),knuckle+v(-sign*.008,-.015,.075)),
   f'thigh.{side}':(v(sign*c['thigh_x'],.008,hips),v(sign*c['knee'][0],c['knee'][1],c['knee'][2])),
   f'shin.{side}':(v(sign*c['knee'][0],c['knee'][1],c['knee'][2]),v(sign*c['ankle'][0],c['ankle'][1],c['ankle'][2])),
   f'foot.{side}':(v(sign*c['ankle'][0],c['ankle'][1],c['ankle'][2]),v(sign*c['ankle'][0],c['toe_y']*.65,.033)),
   f'toe.{side}':(v(sign*c['ankle'][0],c['toe_y']*.65,.033),v(sign*c['ankle'][0],c['toe_y'],.027))})
  for finger,dx,zshift in [('thumb',-sign*.025,.020),('index',-sign*.010,-.004),('grip',sign*.010,-.007)]:
   start=knuckle+v(dx,-.010,zshift);mid=start+v(sign*.001,-.012,-.023);end=mid+v(-sign*.001,-.018,-.022)
   specs[f'{finger}.01.{side}']=(start,mid);specs[f'{finger}.02.{side}']=(mid,end)
 parents={n:X.PARENT[n] for n in X.CORE};secondary=[]
 for sector,x,y in [('F',0,-.12),('B',0,.105),('L',.15,0),('R',-.15,0)]:
  first,second=f'skirt.{sector}.01',f'skirt.{sector}.02';secondary.extend([first,second])
  specs[first]=(v(x,y,hips),v(x,y,.36));specs[second]=(v(x,y,.36),v(x,y,.17 if hero=='04' else .30));parents[first]='hips';parents[second]=first
 if hero=='04':
  for side,sign in [('L',1),('R',-1)]:
   n=f'sleeve.{side}.01';secondary.append(n);specs[n]=(v(sign*.235,-.01,.64),v(sign*.24,-.01,.48));parents[n]=f'forearm.{side}'
  for n,z0,z1,p in [('beard.01',.885,.80,'head'),('beard.02',.80,.745,'beard.01')]:
   secondary.append(n);specs[n]=(v(0,-.075,z0),v(0,-.095,z1));parents[n]=p
 else:
  for side,sign in [('L',1),('R',-1)]:
   for number,z0,z1 in [(1,.87,.76),(2,.76,.64)]:
    n=f'braid.{side}.{number:02}';secondary.append(n);specs[n]=(v(sign*.092,-.075,z0),v(sign*.092,-.078,z1));parents[n]='head' if number==1 else f'braid.{side}.01'
   n=f'belt.{side}.01';secondary.append(n);specs[n]=(v(sign*.15,-.04,hips+.045),v(sign*.16,-.04,hips-.10));parents[n]='hips'
  for number,z0,z1 in [(1,.885,.79),(2,.79,.68)]:
   n=f'hair.B.{number:02}';secondary.append(n);specs[n]=(v(0,.070,z0),v(0,.08,z1));parents[n]='head' if number==1 else 'hair.B.01'
 joints=list(X.CORE)+secondary;assert len(joints)<=60 and len(secondary)<=17
 adata=bpy.data.armatures.new(prefix+'_XS1');arm=bpy.data.objects.new(prefix+'_XS1',adata);scn.collection.objects.link(arm);select([arm]);bpy.ops.object.mode_set(mode='EDIT')
 for n in joints:
  b=adata.edit_bones.new(n);b.head,b.tail=specs[n];b.use_connect=False
  if parents[n]:b.parent=adata.edit_bones[parents[n]]
  b.align_roll(Vector((0,0,1)) if n.startswith(('foot.','toe.')) else Vector((0,-1,0)))
 bpy.ops.object.mode_set(mode='OBJECT');arm.show_in_front=True
 for pb in arm.pose.bones:pb.rotation_mode='QUATERNION'
 print('COMPACT_STAGE',hero,'native_heat_cage',flush=True)
 proxy=body.copy();proxy.data=body.data.copy();proxy.name=prefix+'_disposable_heat_cage';scn.collection.objects.link(proxy);select([proxy])
 proxy.data.remesh_voxel_size=.027 if hero=='06' else .030;bpy.ops.object.voxel_remesh()
 mod=proxy.modifiers.new('CageSmooth','SMOOTH');mod.factor=1;mod.iterations=3;bpy.ops.object.modifier_apply(modifier=mod.name)
 heat_names=[n for n in X.CORE if not any(k in n for k in ['root','twist','socket','pauldron','thumb','index','grip'])]
 for b in arm.data.bones:b.use_deform=b.name in heat_names
 select([proxy,arm],arm);bpy.ops.object.parent_set(type='ARMATURE_AUTO')
 coverage=sum(bool(p.groups) for p in proxy.data.vertices)/max(1,len(proxy.data.vertices));assert coverage>.95,f'Native heat coverage failed:{coverage}'
 for b in arm.data.bones:b.use_deform=True
 for group in proxy.vertex_groups:body.vertex_groups.new(name=group.name)
 select([body]);transfer=body.modifiers.new('OwnGeometryHeatTransfer','DATA_TRANSFER');transfer.object=proxy;transfer.use_vert_data=True;transfer.data_types_verts={'VGROUP_WEIGHTS'};transfer.vert_mapping='POLYINTERP_NEAREST';transfer.layers_vgroup_select_src='ALL';transfer.layers_vgroup_select_dst='NAME';bpy.ops.object.modifier_apply(modifier=transfer.name)
 proxy_mesh=proxy.data;bpy.data.objects.remove(proxy,do_unlink=True)
 if proxy_mesh.users==0:bpy.data.meshes.remove(proxy_mesh)
 body.parent=arm;skin=body.modifiers.new(prefix+'_Skin','ARMATURE');skin.object=arm;skin.use_deform_preserve_volume=False
 def weights(obj,index,values):
  for old in list(obj.data.vertices[index].groups):obj.vertex_groups[old.group].remove([index])
  items=sorted([(n,float(w)) for n,w in values.items() if n in joints and w>1e-7],key=lambda t:-t[1])[:4];total=sum(w for _,w in items);assert total>0
  for n,w in items:(obj.vertex_groups.get(n) or obj.vertex_groups.new(name=n)).add([index],w/total,'REPLACE')
 def normalize(obj):
  fallback=0
  for vertex in obj.data.vertices:
   values={obj.vertex_groups[g.group].name:g.weight for g in vertex.groups if obj.vertex_groups[g.group].name in joints}
   if not values:values={min(heat_names,key=lambda n:(vertex.co-arm.data.bones[n].head_local).length):1};fallback+=1
   weights(obj,vertex.index,values)
  return fallback
 # Components connect UV seams in an analysis graph only; actual UV/normals remain intact.
 adjacency=[[] for _ in co]
 for edge in body.data.edges:
  a,b=edge.vertices;adjacency[a].append(b);adjacency[b].append(a)
 coincident={}
 for index,point in enumerate(co):
  key=tuple(np.round(point,5))
  if key in coincident:prior=coincident[key];adjacency[index].append(prior);adjacency[prior].append(index)
  else:coincident[key]=index
 seen=set();components=[]
 for i in range(len(co)):
  if i in seen:continue
  todo=[i];seen.add(i);component=[]
  while todo:
   vi=todo.pop();component.append(vi)
   for other in adjacency[vi]:
    if other not in seen:seen.add(other);todo.append(other)
  components.append(component)
 assignment_counts={};garment_ids=set();rigid_ids=set();leg_island_ids=set();joined_apron_ids=set()
 def assign(indices,bone):
  for vi in indices:weights(body,vi,{bone:1});rigid_ids.add(vi)
  assignment_counts[bone]=assignment_counts.get(bone,0)+len(indices)
 for comp in components:
  pts=co[comp]/H;cen=pts.mean(0);extent=pts.max(0)-pts.min(0);x,y,z=cen;side='L' if x>0 else 'R'
  bone=None
  if hero=='06' and pts.min(0)[2]<.03 and pts.max(0)[2]>.30 and pts.max(0)[2]<.50 and .02<abs(x)<.18 and extent[0]<.23:
   leg_island_ids.update(comp)
  if hero=='06' and len(comp)>4000 and pts.min(0)[2]>.25 and pts.max(0)[2]>.9:
   # The inspected joined upper-body island's low section is the split apron;
   # both actual lower-leg islands are independent components below it.
   joined_apron_ids.update(vi for vi in comp if co[vi,2]/H<hips+.02 and abs(co[vi,0]/H)<.19)
  if z>.88 and extent[2]<.16:bone='head'
  elif hero=='04' and .70<z<.80 and abs(x)<.07 and np.linalg.norm(extent)<.14:bone='upper_chest'
  elif hero=='04' and .80<z<.87 and abs(x)<.13 and extent[2]<.10 and float(np.mean((semantic_hsv[comp,0]<.12)&(semantic_hsv[comp,1]>.25)&(semantic_hsv[comp,2]<.75)))>.50:bone='beard.01'
  elif z<.09 and extent[2]<.12:bone=f'foot.{side}'
  elif .75<z<.85 and abs(x)>.13 and extent[2]<.13 and len(comp)<500:bone=f'pauldron.{side}'
  elif hips-.08<z<hips+.095 and abs(x)>.08 and np.linalg.norm(extent)<.18:bone='hips' if hero=='04' else f'belt.{side}.01'
  elif .42<z<.56 and abs(x)>c['wrist'][0]-.025 and extent[2]<.18:bone=f'hand.{side}'
  elif .52<z<.70 and abs(x)>c['elbow'][0]-.055 and extent[2]<.24:bone=f'forearm.{side}'
  elif z<hips+.015 and z>.12 and extent[2]>.17 and (abs(y)>.045 or extent[0]>.23) and extent[0]<.50:
   garment_ids.update(comp)
  if bone:assign(comp,bone)
 garment_ids.update(joined_apron_ids)
 if hero=='06':
  for vi,(x,y,z) in enumerate(co/H):
   hue,saturation,value=semantic_hsv[vi]
   if vi not in rigid_ids and vi not in leg_island_ids and .295<z<hips+.02 and abs(x)<.185 and (y<-.055 or y>.06) and .085<hue<.19 and saturation>.35 and value>.35:
    garment_ids.add(vi)
 # Separate panel components plus source-specific orange apron classification; no actual UV weld.
 for vi in garment_ids:
  x,y,z=co[vi]/H
  sector='F' if y<0 else 'B'
  if abs(x)>.14 and abs(y)<.08:sector='L' if x>0 else 'R'
  blend=1-smooth(.22,.42,z);weights(body,vi,{f'skirt.{sector}.01':1-blend,f'skirt.{sector}.02':blend})
 assignment_counts['garment_vertices']=len(garment_ids)
 for vi,point in enumerate(co/H):
  x,y,z=point;side='L' if x>0 else 'R'
  if z>.90:weights(body,vi,{'head':1})
  if z<c['ankle'][2]+.015 and vi not in garment_ids:weights(body,vi,{f'foot.{side}':1})
  if vi in leg_island_ids:
   ankle=smooth(c['ankle'][2]-.035,c['ankle'][2]+.045,z);knee=smooth(c['knee'][2]-.055,c['knee'][2]+.055,z)
   weights(body,vi,{f'foot.{side}':1-ankle,f'shin.{side}':ankle*(1-knee),f'thigh.{side}':ankle*knee})
   if z<c['ankle'][2]+.015:weights(body,vi,{f'foot.{side}':1})
  if vi not in rigid_ids and vi not in garment_ids and vi not in leg_island_ids and hips<z<.82:
   width=(.15,.22) if hero=='04' else (.09,.145);blend=1-smooth(width[0],width[1],abs(x))
   if blend>0:
    levels=[('hips',hips),('spine',hips+.085),('chest',.68),('upper_chest',.745)]
    target={'upper_chest':1} if z>=.745 else {'hips':1}
    for (a,za),(b,zb) in zip(levels,levels[1:]):
     if za<=z<zb:w=smooth(za,zb,z);target={a:1-w,b:w};break
    values={body.vertex_groups[g.group].name:g.weight*(1-blend) for g in body.data.vertices[vi].groups}
    for bone,w in target.items():values[bone]=values.get(bone,0)+blend*w
    weights(body,vi,values)
  if vi not in rigid_ids and .41<z<c['wrist'][2]+.035 and abs(x)>c['wrist'][0]-.035:
   w=smooth(c['wrist'][0]-.035,c['wrist'][0]+.004,abs(x))*(1-smooth(c['wrist'][2],c['wrist'][2]+.035,z))
   values={body.vertex_groups[g.group].name:g.weight*(1-w) for g in body.data.vertices[vi].groups};values[f'hand.{side}']=values.get(f'hand.{side}',0)+w;weights(body,vi,values)
  if vi not in rigid_ids and z>.73 and abs(x)<.22:
   hue,saturation,value=semantic_hsv[vi]
   fur=smooth(.20,.40,saturation)*(1-smooth(.57,.75,value))*(1-smooth(.10,.14,hue)) if hero=='04' else 0
   beard_radius=.030+.060*smooth(.75,.87,z)
   beard_shape=(1-smooth(beard_radius,beard_radius+.025,abs(x)))*smooth(.080,.112,-y)
   back_hair=smooth(.050,.100,y)*smooth(.80,.86,z)
   head_amount=max(smooth(.825,.905,z),fur*max(beard_shape*smooth(.745,.82,z),back_hair))
   neck_amount=(1-head_amount)*smooth(.76,.845,z)
   reference_weights={'head':head_amount,'neck':neck_amount,'upper_chest':max(0,1-head_amount-neck_amount)}
   blend=smooth(.73,.82,z)*(1-smooth(.14,.22,abs(x)))
   values={body.vertex_groups[g.group].name:g.weight*(1-blend) for g in body.data.vertices[vi].groups}
   for bone,w in reference_weights.items():values[bone]=values.get(bone,0)+blend*w
   weights(body,vi,values)
   if hero=='04':
    beard_strength=fur*(1-smooth(.85,.89,z))*smooth(.71,.76,z)*beard_shape
    if beard_strength>0:
     values={body.vertex_groups[g.group].name:g.weight*(1-beard_strength) for g in body.data.vertices[vi].groups};tip=1-smooth(.775,.82,z)
     values['beard.01']=values.get('beard.01',0)+beard_strength*(1-tip);values['beard.02']=values.get('beard.02',0)+beard_strength*tip;weights(body,vi,values)
  hair_color=hero=='06' and semantic_hsv[vi,0]<.085 and semantic_hsv[vi,1]>.45 and semantic_hsv[vi,2]>.4
  if hero=='06' and hair_color and .60<z<.94 and y<-.055 and .048<abs(x)<.15:
   blend=1-smooth(.71,.80,z);weights(body,vi,{f'braid.{side}.01':1-blend,f'braid.{side}.02':blend})
  if hero=='06' and hair_color and .69<z<.89 and y>.035 and abs(x)<.17:
   blend=1-smooth(.74,.82,z);weights(body,vi,{'hair.B.01':1-blend,'hair.B.02':blend})
 neck_vertices=[i for i,(x,y,z) in enumerate(co/H) if .73<z<.90 and abs(x)<.22 and i not in rigid_ids]
 # Smooth only the diagnosed neck/hood transition graph, retaining rigid islands.
 for iteration in range(4):
  snapshot={i:{body.vertex_groups[g.group].name:g.weight for g in body.data.vertices[i].groups} for i in set(neck_vertices)|{j for i in neck_vertices for j in adjacency[i]}}
  for i in neck_vertices:
   near=adjacency[i]
   if not near:continue
   values={n:w*.60 for n,w in snapshot[i].items()}
   for j in near:
    for n,w in snapshot[j].items():values[n]=values.get(n,0)+.40*w/len(near)
   weights(body,i,values)
 assignment_counts['smoothed_neck_hood_vertices']=len(neck_vertices)
 assignment_counts['restricted_leg_island_vertices']=len(leg_island_ids)
 assignment_counts['joined_apron_island_vertices']=len(joined_apron_ids)
 fallback=normalize(body);base=body.data.copy();lods={}
 print('COMPACT_STAGE',hero,'UV_preserving_LODs',flush=True)
 assert 4000<=args.lod0_target<=5500
 for level,target in [(0,args.lod0_target),(1,3000),(2,1200)]:
  obj=body.copy();obj.data=base.copy();obj.name=f'{prefix}_lod{level}';scn.collection.objects.link(obj);select([obj])
  decimate=obj.modifiers.new('NativeCompactLOD','DECIMATE');decimate.ratio=target/c['triangles'];decimate.use_collapse_triangulate=True
  bpy.ops.object.modifier_move_up(modifier=decimate.name);bpy.ops.object.modifier_apply(modifier=decimate.name)
  normalize(obj)
  for vertex in obj.data.vertices:
   if vertex.co.z<0:vertex.co.z=0
  obj.data.update();obj.data.calc_loop_triangles();assert len(obj.data.loop_triangles)<=target
  lods[level]=obj;obj.hide_set(True)
 body.hide_set(True)
 print('COMPACT_STAGE',hero,'licensed_idle_reference_retarget',flush=True)
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(UAL/'AnimationLibrary_Godot_Standard.gltf'),bone_heuristic='BLENDER',guess_original_bind_pose=True)
 imported=[o for o in bpy.data.objects if o not in before];ual_arm=next(o for o in imported if o.type=='ARMATURE');ual_names=[b.name for b in ual_arm.data.bones]
 def ual_action(name):return next(a for a in bpy.data.actions if a.name==name or a.name.split('|')[-1]==name)
 sk=A.Skeleton(arm);reference=A.SourceClip(ual_arm,ual_action('Idle_Loop'),[float(ual_action('Idle_Loop').frame_range[0])],ual_names).frames[0]
 hip_scale=sk.rest['thigh.L'].translation.z/(ual_arm.matrix_world@ual_arm.data.bones['DEF-thigh.L'].head_local).z
 bake_hz=120;time_scale=30/bake_hz
 def write_sampled(name,frames,loop,markers30=None):
  markers={n:int(f/time_scale) for n,f in (markers30 or {}).items()}
  action=A.write_action(arm,name,frames,joints,fps=30,loop=loop,markers=markers or None)
  for layer in action.layers:
   for strip in layer.strips:
    for bag in strip.channelbags:
     for fc in bag.fcurves:
      for key in fc.keyframe_points:key.co.x*=time_scale
      fc.update()
  for marker in action.pose_markers:marker.frame=round(marker.frame*time_scale)
  action.frame_start=0;action.frame_end=(len(frames)-1)*time_scale;action['xex_pose_bake_hz']=bake_hz
  return action
 clip_specs=[('base.idle','Idle_Loop',76,True),('base.walk','Walk_Loop',33,True),('base.run','Jog_Fwd_Loop',23,True),
             ('heavy_1h.attack_1','Sword_Attack',13,False),('heavy_1h.attack_2','Sword_Attack',13,False),
             ('hit_light','Hit_Chest',10,False),('dodge','Roll',13,False),('death','Death01',73,False)]
 clips={};frames_by_clip={}
 for name,source_name,contract_count,loop in clip_specs:
  count=(contract_count-1)*4+1
  action=ual_action(source_name);f0,f1=action.frame_range;times=[f0+(f1-f0)*i/(count-1) for i in range(count)]
  if name.startswith('heavy_1h'):
   dense=A.SourceClip(ual_arm,action,[float(f) for f in range(int(f0),int(f1)+1)],ual_names);wrist=[row['DEF-hand.R'][1] for row in dense.frames]
   peak=1+max(range(len(wrist)-1),key=lambda k:(wrist[k+1]-wrist[k]).length);hit=f0+peak
   hit_key=12;times=[f0+(hit-f0)*i/hit_key if i<=hit_key else hit+(f1-hit)*(i-hit_key)/(count-1-hit_key) for i in range(count)]
  if name=='dodge':
   # Heavy robe/apron uses the UAL roll's initial tuck and return over grounded legs.
   # Full360degree roll compressed to12keys penetrated8.6cm between keys in the rejected export.
   times=[f0+(f1-f0)*.20*math.sin(math.pi*i/(count-1)) for i in range(count)]
  source_clip=A.SourceClip(ual_arm,action,times,ual_names)
  for bone in list(source_clip.rest):
   if bone in reference:q,p=reference[bone];source_clip.rest[bone]=(q.copy(),p.copy(),(q@Vector((0,1,0))).normalized())
  frames=A.retarget(sk,source_clip,X.UAL_POSE,'DEF-hips',hip_scale,in_place=True,delta_bones=tuple(X.UAL_POSE.values()))
  for i,(pose,hips_loc) in enumerate(frames):
   for side in ('L','R'):
    for n in ['upper_arm_twist','forearm_twist','pauldron']:pose[f'{n}.{side}']=Quaternion()
   planted=name in ['base.idle','hit_light','dodge'] or name.startswith('heavy_1h')
   if planted:
    hips_loc.x=hips_loc.y=0;pose['hips']=Quaternion()
    for side in ('L','R'):
     for n in ['thigh','shin','foot','toe']:pose[f'{n}.{side}']=Quaternion()
   if name=='dodge':
    for bone,q in list(pose.items()):
     if bone not in ['hips'] and not bone.startswith(('thigh','shin','foot','toe')):pose[bone]=Quaternion().slerp(q,.65)
    M=sk.fk(pose,hips_loc);hips_target=sk.rest['hips'].translation+Vector((0,0,-(.045 if hero=='04' else .065)*math.sin(math.pi*i/(count-1))))
    hips_loc[:]=sk.hips_loc_for_world(M,hips_target)
   if name in ['base.walk','base.run']:
    for side in ('L','R'):
     for n in ['thigh','shin']:pose[f'{n}.{side}']=Quaternion().slerp(pose.get(f'{n}.{side}',Quaternion()),c['gait'])
     for n in ['shoulder','upper_arm','forearm']:pose[f'{n}.{side}']=Quaternion().slerp(pose.get(f'{n}.{side}',Quaternion()),c['arm_swing'])
   if name.startswith('heavy_1h'):
    phase=math.sin(math.pi*i/(count-1));sk.rotate_world(pose,hips_loc,'chest',(0,0,1),(10 if name.endswith('_1') else -14)*phase)
    for side in ('L','R'):
     pose[f'grip.01.{side}']=A.q_axis((1,0,0),27);pose[f'grip.02.{side}']=A.q_axis((1,0,0),32)
    if hero=='06':
     M=sk.fk(pose,hips_loc);target=M['hand.R'].translation+Vector((.13,-.035,.04))
     sk.ik2(pose,hips_loc,'upper_arm.L','forearm.L','hand.L',target,Vector((.55,-.45,.90)))
   if planted or name in ['base.walk','base.run']:
    for side in ('L','R'):
     foot=f'foot.{side}';rest=sk.rest[foot].translation;M=sk.fk(pose,hips_loc);target=rest.copy() if planted else M[foot].translation.copy()
     target.z=max(target.z,rest.z)
     sk.ik2(pose,hips_loc,f'thigh.{side}',f'shin.{side}',foot,target,Vector((rest.x,-.60,.45)))
     sk.set_world(pose,hips_loc,foot,sk.rest[foot].to_quaternion());sk.set_world(pose,hips_loc,f'toe.{side}',sk.rest[f'toe.{side}'].to_quaternion())
   # Bounded authored secondary sway, no cloth simulation or physics acceptance implied.
   phase=2*math.pi*i/max(1,count-1)
   for bone in secondary:
    amount=(1.2 if name=='base.idle' else 2.2) if loop else 0
    pose[bone]=A.q_axis((1,0,0),amount*math.sin(phase+(.7 if bone.endswith('02') else 0)))
  if loop:A.close_loop(frames,blend_frames=16)
  markers={'hit':3,'trail_on':2,'trail_off':5} if name.startswith('heavy_1h') else None
  write_sampled(name,frames,loop,markers)
  clips[name]={'source_clip':source_name,'licence':'CC0-1.0','frames':contract_count,'sampled_key_count':count,'bake_hz':bake_hz,'duration_s':(contract_count-1)/30,'loop':loop,
               'release_ms':100 if markers else None,'events':markers,'retarget':'Reviewed fitted-rest/UAL Idle-reference world delta',
               'limits':'Real weapon contact, controller-speed foot locking, costume collisions and native pose review pending'}
  if name=='dodge':clips[name]['adaptation']='Grounded fitted UAL initial20percent tuck/recovery,65percent upper motion; full roll rejected after actual-interpolated floor audit'
  frames_by_clip[name]=frames
 for obj in imported:bpy.data.objects.remove(obj,do_unlink=True)
 for action in list(bpy.data.actions):
  if action.name not in clips:bpy.data.actions.remove(action)
 marker_objects=[]
 for name,parent in X.STATIC_NODES.items():
  o=bpy.data.objects.new(name,None);scn.collection.objects.link(o);o.parent=arm;o.parent_type='BONE';o.parent_bone=parent;o.matrix_world=Matrix.Translation(arm.data.bones[parent].head_local);marker_objects.append(o)
 print('COMPACT_STAGE',hero,'sampled_own_mesh_deformation',flush=True)
 obj=lods[0];obj.hide_set(False);dg=bpy.context.evaluated_depsgraph_get();bind=np.array([tuple(v.co) for v in obj.data.vertices]);edges=np.array([tuple(e.vertices) for e in obj.data.edges],dtype=int);bind_lengths=np.linalg.norm(bind[edges[:,0]]-bind[edges[:,1]],axis=1);valid=bind_lengths>.002
 deformation={}
 for name,frames in frames_by_clip.items():
  action=bpy.data.actions[name];arm.animation_data.action=action;arm.animation_data.action_slot=action.slots[0];samples=[];ground_offsets=[]
  sampled=set(int(f) for f in np.linspace(0,len(frames)-1,17))
  for frame in range(len(frames)):
   timeline=frame*time_scale;scn.frame_set(int(timeline),subframe=timeline%1);bpy.context.view_layer.update();evaluated=obj.evaluated_get(dg);mesh=evaluated.to_mesh();pts=np.array([tuple(evaluated.matrix_world@v.co) for v in mesh.vertices]);evaluated.to_mesh_clear()
   floor=float(pts[:,2].min());margin=.003 if name in ['death','dodge'] else .0001
   ground_offsets.append(max(0,margin-floor) if floor<0 else 0)
   if frame in sampled:
    lengths=np.linalg.norm(pts[edges[:,0]]-pts[edges[:,1]],axis=1);stretch=lengths[valid]/bind_lengths[valid]
    samples.append({'frame':frame,'floor_min_m':floor,'height_m':float(np.ptp(pts[:,2])),'edge_stretch_p99':float(np.quantile(stretch,.99)),'edges_over_2x':int((stretch>2).sum())})
  if max(ground_offsets)>0:
   updated=[]
   for (pose,hips_loc),offset in zip(frames,ground_offsets):M=sk.fk(pose,hips_loc);updated.append((pose,sk.hips_loc_for_world(M,M['hips'].translation+Vector((0,0,offset)))))
   write_sampled(name,updated,clips[name]['loop'],clips[name]['events']);frames_by_clip[name]=updated
  deformation[name]={'samples_before_floor_offset':samples,'per_frame_ground_offsets_m':ground_offsets,'max_ground_offset_m':max(ground_offsets),
                     'grounding_method':'Per-frame source-specific floor correction; no constant whole-clip lift','status':'NUMERIC_CANDIDATE_NATIVE_VISUAL_UNVERIFIED'}
 arm.animation_data.action=None
 for pb in arm.pose.bones:pb.matrix_basis=Matrix.Identity(4)
 scn.frame_set(0);bpy.context.view_layer.update();obj.hide_set(True);outputs=[]
 for level,obj in lods.items():
  obj.hide_set(False);select([obj,arm]+(marker_objects if level==0 else []),arm);file=out/f'{prefix}_lod{level}.glb';assert not file.exists()
  bpy.ops.export_scene.gltf(filepath=str(file),export_format='GLB',use_selection=True,export_materials='EXPORT',export_image_format='AUTO',
    export_animations=level==0,export_animation_mode='ACTIONS',export_frame_range=False,export_force_sampling=False,export_skins=True,
    export_influence_nb=4,export_all_influences=False,export_reset_pose_bones=True,export_anim_slide_to_zero=True,export_cameras=False,export_lights=False,export_extras=True)
  facts=glb_facts(file);assert facts['triangles']<=[5500,3000,1200][level]
  assert level!=0 or facts['vertices']<=5000,f'Actual exported L0 vertex budget failed:{facts["vertices"]}'
  assert len(facts['joints'])==1 and len(facts['joints'][0])==len(joints) and set(facts['joints'][0])==set(joints)
  assert len(facts['clips'])==(8 if level==0 else 0);assert facts['has_uv0'] and facts['images']==3
  vals=[sum(g.weight for g in v.groups) for v in obj.data.vertices]
  outputs.append({'lod':level,'file':str(file),'bytes':file.stat().st_size,'sha256':sha(file),'facts':facts,
                  'max_weight_sum_error':max(abs(x-1) for x in vals),'max_influences':max(len(v.groups) for v in obj.data.vertices)})
  obj.hide_set(True)
 obj=lods[0];obj.hide_set(False);select([obj,arm],arm);bpy.data.objects.remove(body,do_unlink=True)
 if base.users==0:bpy.data.meshes.remove(base)
 for mesh in list(bpy.data.meshes):
  if mesh.users==0:bpy.data.meshes.remove(mesh)
 blend=out/f'{prefix}_rig_r01.blend';scn.frame_start=0;scn.frame_end=75;bpy.context.preferences.filepaths.save_version=0
 bpy.ops.wm.save_as_mainfile(filepath=str(blend),compress=True)
 assert sha(source)==c['sha'],'Source mutated'
 receipt={'schema':'xexoria.compact-hero-rig/1','hero':hero,'class':c['role'],'status':'FITTED_RIG_CANDIDATE_NOT_GAME_READY',
  'source':{'path':str(source),'sha256':c['sha'],'bytes':source.stat().st_size,'immutable_rechecked':True,'triangles':c['triangles']},
  'blender':bpy.app.version_string,'threads':2,'no_render_or_gpu':True,'height':{'crown_target_m':c['crown'],'full_bound_height_m':H,'crown_fraction':c['crown_fraction'],'status':'PROVISIONAL_LANDMARK_FIT_NATIVE_CROWN_VERIFICATION_PENDING'},
  'source_pivot':pivot.tolist(),'source_scale':scale,'lod0_triangle_target':args.lod0_target,'facing':'Blender-Y forward / glTF+Z / Babylon+Z','feet':'Bind minimumZclamped0 after decimation; actual exported animation floor audit still required',
  'rig':{'joints':joints,'core_joints':43,'secondary':secondary,'parents':parents,'fitted_specs':{n:[list(x) for x in s] for n,s in specs.items()},
         'weight_method':'Native own-source voxel heat cage / own-source closest-surface transfer / inspected rigid garment assignments','heat_coverage':coverage,'fallback_vertices':fallback,
         'seam_linked_components':len(components),'rigid_assignment_vertices':assignment_counts,'no_other_hero_mesh_or_weights':True},
  'textures':[{'name':im.name,'role':texture_roles[im.name],'size':list(im.size),'source_size':[4096,4096],'colorspace':im.colorspace_settings.name,'lossy_resize':True} for im in images],
  'clips':clips,'deformation':deformation,'outputs':outputs,'blend':{'file':str(blend),'bytes':blend.stat().st_size,'sha256':sha(blend)},
  'ual_provenance':str(UAL/'provenance.json'),'helpers':[{'path':str(ROOT/'assets/blender/heroes/hero02'/n),'sha256':sha(ROOT/'assets/blender/heroes/hero02'/n)} for n in ['h02_xs1.py','h02_animlib.py']],
  'limits':['No actual weapon attached; H06 two-handed grip is provisional fitted IK.','Eight starter clips only; six skills per hero not delivered by this lane.','Atlas downsampling2Kcolor/normal1KORM is lossy, source4K maps preserved in original.','Native PBR/deformation/face/robe/hair/weapon contact and actual-speed foot-locking remain unverified.','No gameplay balance, capsule, code, loader, map material or shared-state changes.','No baked normals from high tolow geometry or texture compression has been performed by this Blender recipe.']}
 write(out/'receipt.json',receipt)
 print('COMPACT_COMPLETE',hero,json.dumps({'outputs':outputs,'joint_count':len(joints),'heat_coverage':coverage}),flush=True)
 assert sum(p.stat().st_size for p in args.out.rglob('*') if p.is_file())<200_000_000,'Bounded output cap exceeded'
