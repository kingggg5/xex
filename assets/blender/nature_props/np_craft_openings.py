"""Static GLB triangle checks for clear doorway/threshold body corridors.

This proves geometry clearance only; authoritative runtime movement stays unverified.
"""
from pathlib import Path
import json
import numpy as np
from np_flora_validate import read,accessor
ROOT=Path(__file__).resolve().parents[3]

def intersects(v,tri,a,b):
    direction=np.asarray(b)-a;aa=v[tri[:,0]];e1=v[tri[:,1]]-aa;e2=v[tri[:,2]]-aa
    hh=np.cross(np.broadcast_to(direction,e2.shape),e2);det=np.sum(e1*hh,axis=1)
    inv=np.zeros_like(det);valid=np.abs(det)>1e-9;inv[valid]=1/det[valid]
    ss=np.asarray(a)-aa;u=inv*np.sum(ss*hh,axis=1);qq=np.cross(ss,e1);vv=inv*np.sum(direction*qq,axis=1);t=inv*np.sum(e2*qq,axis=1)
    return int(np.sum(valid&(u>=-1e-6)&(vv>=-1e-6)&(u+vv<=1+1e-6)&(t>=0)&(t<=1)))

def check(path,halfwidth,end_z,start_z=4):
    doc,data=read(path);tests=[]
    if any('matrix' in n or 'rotation' in n or 'translation' in n or 'scale' in n for n in doc['nodes']):raise ValueError('Transform must be resolved before clearance test')
    for x in (-halfwidth,0,halfwidth):
        for y in (.15,.9,1.8,2.05):
            count=0
            for m in doc['meshes']:
                for p in m['primitives']:
                    v=np.asarray(accessor(doc,data,p['attributes']['POSITION']));tri=np.array(accessor(doc,data,p['indices'])).reshape(-1,3)
                    count+=intersects(v,tri,np.array([x,y,start_z]),np.array([x,y,end_z]))
            tests.append({'x':x,'height':y,'intersections':count})
    return {'file':str(path),'status':'PASS' if all(t['intersections']==0 for t in tests) else 'FAIL','corridor_half_width_m':halfwidth,'probes':tests,
            'limit':'Static triangle probes, not swept capsule or authoritative movement integration.'}

def main():
    out=ROOT/'assets/models/sunmeadow-props/craft/source';results=[]
    for aid,half,end in [('sm_croft_hut',.90,0),('sm_threshold_gate',1.40,-2)]:
        for suffix in ('lod0','lod1','lod2','collider'):
            path=out/f'{aid}_{suffix}.glb'
            if path.exists():results.append(check(path,half,end))
    dest=ROOT/'planning/evidence/sunmeadow-props-20261002/craft/opening-clearance.json';dest.write_text(json.dumps(results,indent=2),encoding='utf8')
    print('STATIC OPENING CHECK',sum(r['status']=='PASS' for r in results),'/',len(results))
    for r in results:
        if r['status']!='PASS':print(r['file'],[p for p in r['probes'] if p['intersections']])
    if not results or any(r['status']!='PASS' for r in results):raise SystemExit(1)
if __name__=='__main__':main()
