"""Small CPU preflight: triangle budgets, closed edges, finite coordinates and source hashes."""
import hashlib,json,math
from collections import Counter
from pathlib import Path
from weapon_geometry import RECIPES
ROOT=Path(__file__).resolve().parents[3]
def main():
 results={}
 for hero,recipe in RECIPES.items():
  parts,markers=recipe();checks=[]
  for part in parts:
   edges=Counter(tuple(sorted((face[i],face[(i+1)%len(face)]))) for face in part.faces for i in range(len(face)))
   checks.append({'part':part.name,'triangles':part.triangles,'finite':all(math.isfinite(v) for p in part.vertices for v in p),
                 'closed_edges':all(count==2 for count in edges.values()),'valid_indices':all(0<=i<len(part.vertices) for f in part.faces for i in f)})
  vertices=[v for p in parts for v in p.vertices];count=sum(p.triangles for p in parts)
  results[hero]={'triangles':count,'bounds_blender':{'min':[min(v[i] for v in vertices)for i in range(3)],'max':[max(v[i]for v in vertices)for i in range(3)]},
                'marker_names':sorted(markers),'parts':checks,'pass':count<=2500 and all(c['finite']and c['closed_edges']and c['valid_indices']for c in checks)}
 script=Path(__file__).with_name('weapon_geometry.py')
 report={'schema':'xexoria.weapon-recipe-preflight/1','scope':'Pure recipe topology only; not Blender export, appearance or integration acceptance.',
         'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'weapons':results,'pass':all(r['pass']for r in results.values())}
 output=ROOT/'planning/evidence/hero-weapons-20261002/preflight.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
 print(json.dumps({'pass':report['pass'],'triangles':{h:r['triangles']for h,r in results.items()}}))
 if not report['pass']:raise SystemExit(1)
if __name__=='__main__':main()
