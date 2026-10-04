"""Audit exact redecoded runtime triangles; no Blender/GPU/scene mutation."""
import json, math, collections
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
EVID=ROOT/'planning/evidence/water-art-pass4b-20261003/r03'
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def ray(origin,target,t):
 d=sub(target,origin);a,b,c=t;e1=sub(b,a);e2=sub(c,a);h=cross(d,e2);det=dot(e1,h)
 if abs(det)<1e-10:return None
 inv=1/det;s=sub(origin,a);u=dot(s,h)*inv
 if u<-.000001 or u>1.000001:return None
 q=cross(s,e1);v=dot(d,q)*inv
 if v<-.000001 or u+v>1.000001:return None
 k=dot(e2,q)*inv
 return k if .000001<k<.999999 else None
def box_overlap(t,mn,mx):
 centre=tuple((a+b)/2 for a,b in zip(mn,mx));half=tuple((b-a)/2 for a,b in zip(mn,mx));p=[sub(v,centre) for v in t]
 edges=[sub(p[1],p[0]),sub(p[2],p[1]),sub(p[0],p[2])];units=[(1,0,0),(0,1,0),(0,0,1)]
 axes=units+[cross(edges[0],edges[1])]+[cross(e,u) for e in edges for u in units]
 for axis in axes:
  if dot(axis,axis)<1e-20:continue
  vals=[dot(q,axis) for q in p];r=sum(abs(x)*y for x,y in zip(axis,half))
  if min(vals)>r+1e-6 or max(vals)<-r-1e-6:return False
 return True
def closest(a,b,c,p):
 ab=sub(b,a);ac=sub(c,a);ap=sub(p,a);d1=dot(ab,ap);d2=dot(ac,ap)
 if d1<=0 and d2<=0:return a
 bp=sub(p,b);d3=dot(ab,bp);d4=dot(ac,bp)
 if d3>=0 and d4<=d3:return b
 vc=d1*d4-d3*d2
 if vc<=0 and d1>=0 and d3<=0:
  v=d1/(d1-d3);return tuple(a[i]+v*ab[i] for i in range(3))
 cp=sub(p,c);d5=dot(ab,cp);d6=dot(ac,cp)
 if d6>=0 and d5<=d6:return c
 vb=d5*d2-d1*d6
 if vb<=0 and d2>=0 and d6<=0:
  w=d2/(d2-d6);return tuple(a[i]+w*ac[i] for i in range(3))
 va=d3*d6-d5*d4
 if va<=0 and d4-d3>=0 and d5-d6>=0:
  w=(d4-d3)/((d4-d3)+(d5-d6));return tuple(b[i]+w*(c[i]-b[i]) for i in range(3))
 den=va+vb+vc
 if abs(den)<1e-20:return a
 v=vb/den;w=vc/den;return tuple(a[i]+ab[i]*v+ac[i]*w for i in range(3))
def height_hits(tris,x,z):
 hits=[]
 for i,t in enumerate(tris):
  a,b,c=t
  if x<min(a[0],b[0],c[0])-1e-6 or x>max(a[0],b[0],c[0])+1e-6 or z<min(a[2],b[2],c[2])-1e-6 or z>max(a[2],b[2],c[2])+1e-6:continue
  den=(b[2]-c[2])*(a[0]-c[0])+(c[0]-b[0])*(a[2]-c[2])
  if abs(den)<1e-10:continue
  u=((b[2]-c[2])*(x-c[0])+(c[0]-b[0])*(z-c[2]))/den
  v=((c[2]-a[2])*(x-c[0])+(a[0]-c[0])*(z-c[2]))/den;w=1-u-v
  if min(u,v,w)<-1e-5:continue
  hits.append(u*a[1]+v*b[1]+w*c[1])
 return sorted({round(y,5) for y in hits})
water=json.loads((ROOT/'planning/evidence/water-art-pass4b-20261003/water-geometry.json').read_text())['falls0']['position']
rows=[(-6.60,7.55,1.4),(-6.891667,7.55,1.466667),(-7.183333,7.55,1.533333),(-7.366668,7.533147,1.577194),(-7.42,7.45,1.6)]
samples=[]
for a,b in zip(rows,rows[1:]):
 for xi in range(9):
  q=xi/8;x=a[0]*(1-q)+b[0]*q;y=a[1]*(1-q)+b[1]*q;width=a[2]*(1-q)+b[2]*q
  for zi in range(17):samples.append([x,y,-38+width*(zi/16-.5)])
camera=[2.819878161304265,7.452022716769464,-38]
targets=[('camera-centre',[-9.2,2.5,-38])]
for q in [.1,.3,.6,.9,1.261]:
 for z in [-.8,0,.8]:targets.append((f'fall-{q}-{z}',[-7.42-1.5*q,7.45-4.905*q*q,-38+z]))
for dx in [-1,0,1]:
 for dz in [-1,0,1]:targets.append((f'pool-{dx}-{dz}',[-9.6+dx,-.35,-38+dz]))
records=[]
for suffix in ['lod0','lod1','lod2','collider','shadow']:
 data=json.loads((EVID/f'sculpt-{suffix}-runtime-geometry.json').read_text());positions=[];tris=[];welded={};mesh_faces=[]
 for prim in data['geometry']:
  v=prim['positions'];idx=prim['indices'];positions+=v
  for i in range(0,len(idx),3):
   t=[v[j] for j in idx[i:i+3]];tris.append(t);f=[]
   for p in t:
    key=tuple(round(a,6) for a in p)
    if key not in welded:welded[key]=len(welded)
    f.append(welded[key])
   mesh_faces.append(tuple(f))
 edges=collections.Counter();graph=collections.defaultdict(set);degenerate=[]
 for i,(t,f) in enumerate(zip(tris,mesh_faces)):
  area=math.sqrt(dot(cross(sub(t[1],t[0]),sub(t[2],t[0])),cross(sub(t[1],t[0]),sub(t[2],t[0]))))/2
  if len(set(f))!=3 or area<1e-12:degenerate.append(i);continue
  for a,b in zip(f,f[1:]+f[:1]):edges[tuple(sorted((a,b)))]+=1;graph[a].add(b);graph[b].add(a)
 seen=set();components=[]
 for v in graph:
  if v in seen:continue
  pending=[v];seen.add(v);size=0
  while pending:
   a=pending.pop();size+=1
   for b in graph[a]:
    if b not in seen:seen.add(b);pending.append(b)
  components.append(size)
 passage=[i for i,t in enumerate(tris) if box_overlap(t,[-4+.002,.002,-41.4+.002],[.892-.002,5.1-.002,-36.6-.002])]
 rec=dict(suffix=suffix,file=data['file'],sha256=data['sha256'],triangles=len(tris),weldedVertices=len(welded),
  zeroAreaOrCollapsedTriangles=degenerate,nonManifoldGeometricEdges=sum(n!=2 for n in edges.values()),components=components,
  negativePassageTriangleOverlap=passage,negativePassageToleranceM=.002,
  attributeReceipts=[p['attributeReceipt'] for p in data['geometry']])
 if suffix.startswith('lod'):
  support=[]
  for p in samples:
   h=height_hits(tris,p[0],p[2]);below=[y for y in h if y<p[1]+.005];top=max(below) if below else None
   lower=[y for y in h if top is not None and y<top-.01]
   thickness=top-max(lower) if top is not None and lower else None
   gap=p[1]-top if top is not None else None
   support.append(dict(point=p,stoneTop=top,gap=gap,thickness=thickness,pass_=gap is not None and .03<=gap<=.06,pierces=bool(h and max(h)>p[1]+.005)))
  rec['denseFilmSupport']={'sampleCount':len(support),'minGapM':min(s['gap'] for s in support if s['gap'] is not None),'maxGapM':max(s['gap'] for s in support if s['gap'] is not None),
   'failed':[s for s in support if not s['pass_'] or s['pierces']],'minStoneThicknessM':min(s['thickness'] for s in support if s['thickness'] is not None),'maxStoneThicknessM':max(s['thickness'] for s in support if s['thickness'] is not None)}
 if suffix=='lod0':
  rays=[]
  for label,target in targets:
   first=min((k for t in tris if (k:=ray(camera,target,t)) is not None),default=None)
   rays.append(dict(label=label,target=target,clear=first is None,firstFraction=first))
  rec['sideRays']=rays;rec['requiredLowerFallPoolRaysClear']=all(r['clear'] for r in rays if not r['label'].startswith('fall-0.1'))
  rec['fixedSideCameraNearestDistanceM']=min(math.dist(camera,closest(*t,camera)) for t in tris if dot(cross(sub(t[1],t[0]),sub(t[2],t[0])),cross(sub(t[1],t[0]),sub(t[2],t[0])))>1e-15)
  rec['nearPlaneRadiusM']=.1;rec['nearPlaneConservativeClearanceM']=rec['fixedSideCameraNearestDistanceM']-.1
 records.append(rec)
 print(suffix,len(tris),'tri manifoldEdges',rec['nonManifoldGeometricEdges'],'degenerate',len(degenerate),'passageOverlap',len(passage),'supportFails',len(rec.get('denseFilmSupport',{}).get('failed',[])))
geometry_ok=not any(r['nonManifoldGeometricEdges'] or r['zeroAreaOrCollapsedTriangles'] or len(r['components'])!=1 or r['negativePassageTriangleOverlap'] or r.get('denseFilmSupport',{}).get('failed') for r in records)
report=dict(schema='xexoria.sculpt-grotto-runtime-geometry-audit/1',status='PASS_GEOMETRY_CHECKS' if geometry_ok else 'FAIL_GEOMETRY_CHECKS',source='Exact meshopt-decoded runtime GLB matrices and triangles; no native rendering',records=records,
 limits=['Triangle overlap and sampled support inspect the new candidate only. Parent owns remaining-baseline/native scene rays.','Foam/lip decoration has original +.03/.05m offset above primary film. Contact gap is assessed on primary film; all fixed effect vertices stay unchanged.'])
(EVID/'sculpt-runtime-geometry-audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
if not geometry_ok:raise SystemExit('Runtime geometry defect: inspect receipt before candidate admission')
