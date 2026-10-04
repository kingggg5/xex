"""Verified existing stone/flora placement overlay only; no new models or frozen edits."""
from pathlib import Path
import json,math
ROOT=Path(__file__).resolve().parents[3]
EV=ROOT/'planning/evidence/water-art-pass4b-20261003';derived=json.loads((EV/'water-derived.json').read_text(encoding='utf-8'))
entries=[]
def add(asset,x,z,size=None,height=None,base=0,yaw=0,r=.5,role='bank'):
 e={'id':f'water_art_{role}_{len(entries):03d}','asset_id':asset,'class':'water_art','blueprint_id':'WATER_ART','x':round(x,4),'y':0,'z':round(z,4),'yaw':yaw,'scale':1,'visual_absolute_base_y':round(base,4),'footprint_r':r,'collider':'none','cell':f'{math.floor(x/64)},{math.floor(z/64)}','landmark':True,'shadow':True,'rule':'water_art_pass4b','role':role,'moss_requires_world_normal_y':.6}
 if size:e['target_size_xyz']=size
 if height:e['target_height']=height
 entries.append(e)
for asset,x,z,size,base in [('sm_cliff_wall_03',-1,-43,[7.2,7.2,2],0),('sm_cliff_wall_02',-1,-35,[6.8,6.5,2],0),('sm_cliff_corner_04',2.6,-43.6,[3.6,8.0,2.4],0),('sm_cliff_cap_06',-1.5,-39,[7.4,1.4,7.8],6.5),('sm_cliff_cap_06',-.8,-39.2,[6.5,1.2,6.1],7.8),('sm_boulder_03',-4.3,-42.8,[2.8,3.2,2.2],0),('sm_boulder_04',-4.3,-35.2,[2.9,3.3,2.2],0)]:add(asset,x,z,size=size,base=base,r=3,role='grotto_bluff')
for st in derived['stones']:
 h=max(.18,st['top_y']-st['base_y']);r=st['r'];asset='sm_boulder_03' if r>.75 else 'sm_medium_03'
 add(asset,st['x'],st['z'],size=[2*r,h,2*r*st.get('squash',.8)],base=st['base_y'],yaw=st['yaw'],r=r,role='contact_stone')
samples=derived['stream']['samples_1m']
for k in range(5,len(samples)-2,6):
 p=samples[k];a=samples[k-1];b=samples[k+1];dx,dz=b['x']-a['x'],b['z']-a['z'];L=math.hypot(dx,dz);nx,nz=dz/L,-dx/L
 for side in [-1,1]:
  x,z=p['x']+nx*side*(p['w']/2+.65),p['z']+nz*side*(p['w']/2+.65)
  add('sm_reeds_02',x,z,height=.7,base=0,yaw=k*.3,r=.2,role='stream_reeds')
mere=next(b for b in derived['lakes'] if b['id']=='lotus_mere_pond');poly=mere['outline_xz'];cx=sum(p[0] for p in poly)/len(poly);cz=sum(p[1] for p in poly)/len(poly)
for k in range(0,len(poly),4):
 p=poly[k];dx,dz=p[0]-cx,p[1]-cz;L=math.hypot(dx,dz);x,z=p[0]+dx/L*.25,p[1]+dz/L*.25
 add('sm_reeds_02',x,z,height=.65,base=-.08,r=.2,role='mere_edge')
 if k%8==0:add('sm_medium_03',p[0],p[1],size=[.9,.45,.75],base=-.38,yaw=k*.4,r=.45,role='mere_overlap_stone')
proposal=json.loads((ROOT/'planning/evidence/blueprint-light-anchors-20261003/l1-anchor-proposal-r01.json').read_text(encoding='utf-8'))
patches=[{'id':r['id'],'x':r['proposed']['q'][0],'z':r['proposed']['q'][1]} for r in proposal['proposal_rows']]
out={'schema':'xexoria.water-art-dressing-overlay/1','candidate':'water-art-pass4b','entries':entries,'L1_patches':patches,'L1_exception':'20–28mactualroutegaps,no strict20mclaim;8sameIDs,noextralamps/range/intensity','physical_admission':'UNVERIFIED_ROOT','legacy_float_patch':{'packed_sha256':'fd4126c80c310ea702ef04a0c278bb09e1897202642cd2e5a30bf5eb93ce1f6a','material':'stone_foundation','cell':'sunmeadow_c7_r6','source_id':'terrain_edge_stone_sunmeadow_c7_r6_09','triangle_ordinals':[180,200],'world_aabb':{'min':[-53.0572840329,.04637354353,-82.7720570556],'max':[-52.6510216287,.25731748417,-82.1196933873]}},'bluff_passage':'Keeporiginalmouth/tunnel andcompoundcollisionrequests; outerverifiedkitmass+roof coversbareappearance, noactorheightchange'}
(ROOT/'planning/levels/sunmeadow-water-art-pass4b-overlay.json').write_text(json.dumps(out,indent=1)+'\n',encoding='utf-8')
print('WATER_ART_OVERLAY',len(entries),'verifiedkitinstances,8L1patches')
