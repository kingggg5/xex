"""Check signed volume of connected closed components in actual source GLBs."""
from pathlib import Path
import json
import numpy as np
from np_flora_validate import read,accessor
ROOT=Path(__file__).resolve().parents[3]
def check(path):
    doc,data=read(path);volumes=[]
    for me in doc['meshes']:
        for p in me['primitives']:
            v=np.asarray(accessor(doc,data,p['attributes']['POSITION']));idx=np.asarray(accessor(doc,data,p['indices'])).reshape(-1,3)
            unique,inverse=np.unique(np.round(v,6),axis=0,return_inverse=True);tris=inverse[idx];parent=list(range(len(unique)))
            def find(x):
                while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
                return x
            for tri in tris:
                root=find(int(tri[0]))
                for x in tri[1:]:parent[find(int(x))]=root
            groups={}
            for i,t in enumerate(tris):groups.setdefault(find(int(t[0])),[]).append(i)
            for ids in groups.values():
                tv=v[idx[ids]];origin=tv.reshape(-1,3).mean(axis=0);q=tv-origin
                volume=float(np.sum(q[:,0]*np.cross(q[:,1],q[:,2]))/6)
                volumes.append(round(volume,10))
    negative=[x for x in volumes if x < -1e-7]
    return {'file':str(path),'components':len(volumes),'negative_volumes':negative,'status':'FAIL' if negative else 'PASS'}
def main():
    src=ROOT/'assets/models/sunmeadow-props/craft/source';out=[]
    for path in sorted(src.glob('sm_*_lod*.glb')):
        rp=path.with_suffix('.receipt.json')
        if rp.exists() and json.loads(rp.read_text(encoding='utf8')).get('status')=='PASS':out.append(check(path))
    dest=ROOT/'planning/evidence/sunmeadow-props-20261002/craft/outward-normal-validation.json';dest.write_text(json.dumps(out,indent=2),encoding='utf8')
    print('OUTWARD COMPONENTS',sum(x['status']=='PASS' for x in out),'/',len(out))
    for x in out:
        if x['negative_volumes']:print(Path(x['file']).name,x['negative_volumes'])
    if not out or any(x['status']!='PASS' for x in out):raise SystemExit(1)
if __name__=='__main__':main()
