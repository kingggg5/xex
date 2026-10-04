"""One versioned water-art candidate; reuse verified construction, never overwrite v3."""
from pathlib import Path
import json,math,inspect,hashlib
import numpy as np
import prepare_water_v3 as P
ROOT=Path(__file__).resolve().parents[3]
EV=ROOT/'planning/evidence/water-art-pass4b-20261003'
OUT=ROOT/'apps/client/src/assets/world/water-art-pass4b'
EV.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
base=ROOT/'planning/levels/sunmeadow-v2-layout.json';layout=json.loads(base.read_text(encoding='utf-8'))
stream=next(b for b in layout['water'] if b['id']=='sunmeadow_stream')
stream['points'][4][1]-=.45;stream['points'][5][1]+=.35;stream['points'][6][1]-=.20
mere=next(b for b in layout['water'] if b['id']=='lotus_mere_pond')
original=np.asarray(mere['outline_xz'],float)
dense,_=P.W.catmull_rom(original,samples=8,closed=True)
seg=np.linalg.norm(np.diff(np.vstack([dense,dense[:1]]),axis=0),axis=1);cum=np.r_[0,np.cumsum(seg)]
samples=np.arange(48)*cum[-1]/48;poly=np.stack([np.interp(samples,cum,np.r_[dense[:,i],dense[0,i]]) for i in range(2)],axis=1)
edges=np.roll(poly,-1,axis=0)-np.roll(poly,1,axis=0);edges/=np.linalg.norm(edges,axis=1)[:,None]
normal=np.stack([edges[:,1],-edges[:,0]],1)*(1 if P.W.polygon_area(poly)>0 else -1)
theta=np.arange(48)*math.tau/48;poly+=normal*(.16*np.sin(theta*7+.4)+.07*np.sin(theta*11+1.7))[:,None]
mere['outline_xz']=np.round(poly,4).tolist()
cove=next(b for b in layout['water'] if b['id']=='brightwater_cove_lake');cove['shallow_band_m']=4.2
candidate_layout=EV/'layout-candidate.json';candidate_layout.write_text(json.dumps(layout,indent=1)+'\n',encoding='utf-8')
OriginalModel=P.W.WaterModel
def candidate_model():
 m=OriginalModel(candidate_layout);width=m.sp.width
 def organic_width(s):
  s=np.asarray(s,float);w=width(s)*(1+.30*np.sin(s*math.tau/21.7)*m.sp.variation_mask(s))
  for a,b,cap in m.sp.width_caps:w=np.where((s>=a)&(s<=b),np.minimum(w,cap),w)
  return w
 m.sp.width=organic_width;m.stones=P.W.place_stones(m.sp,m.seed)
 m.notes.append('water-art-pass4b: pinned bridge/lips, gentle centreline, width.7–1.3 except tighter safetycaps; Lotus48organic; Covedepth4.2mshoreband.')
 return m
P.W.WaterModel=candidate_model;P.OUT=OUT;P.EVIDENCE=EV
bake_source=inspect.getsource(P.bake_atlas).replace('W.smoothstep(.03,.28,sdf)','W.smoothstep(.08,.50,sdf)').replace('W.smoothstep(0,.28,np.maximum(0,dist))','W.smoothstep(.03,.55,np.maximum(0,dist))')
bake_source=bake_source.replace('return masks,flow,islands',"noise=.45+.55*(.5+.5*np.sin(np.indices(flow.shape[:2])[1]*.19+np.sin(np.indices(flow.shape[:2])[0]*.31)*2))\n    flow[...,2]=(flow[...,2]*noise*.78).round().astype(np.uint8)\n    return masks,flow,islands")
exec(bake_source,P.__dict__)
main_source=inspect.getsource(P.main).replace('M.build_surface(model)','M.build_surface(model,cols=3)').replace('lake_mesh(body,rect)','lake_mesh(body,rect,step=4.6)')
main_source=main_source.replace('merge(bed,stones)','# Contactstones are verified M1kitinstances in candidate dressing, not homemade bed geometry.')
main_source=main_source.replace('M.build_bank_strip(model,step=.9)','M.build_bank_strip(model,step=1.10)')
main_source=main_source.replace("distances=(-.15,.6) if body.get('blueprint_id') else (-.15,.15,.6,1.2)","distances=(-.15,1.2) if body['id']=='lotus_mere_pond' else (-.15,.6) if body.get('blueprint_id') else (-.15,.15,.6,1.2)")
exec(main_source,P.__dict__);P.main()
manifest=json.loads((OUT/'water-manifest.json').read_text(encoding='utf-8'));manifest['recipe']='water-art-pass4b/1';manifest['candidate']='water-art-pass4b';manifest['base_layout_sha256']=hashlib.sha256(base.read_bytes()).hexdigest();manifest['physical_admission']='UNVERIFIED_ROOT_CANDIDATE'
(OUT/'water-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('CANDIDATE_ONLY',manifest['meshes']['surface']['triangles'],manifest['support']['bank_triangles'])
