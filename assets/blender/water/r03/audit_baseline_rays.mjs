/** Exact remaining dressing LOD0 geometry + new r03 camera-ray baseline, CPU only. */
import fs from 'node:fs/promises';import path from 'node:path';import crypto from 'node:crypto';import {fileURLToPath,pathToFileURL} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../..'),evid=path.join(root,'planning/evidence/water-art-pass4b-20261003/r03');
const {createIO}=await import(pathToFileURL(path.join(root,'apps/client/scripts/gltf-postprocess.mjs')).href),io=await createIO();
const {blueprintScale,blueprintFloor,dressingAssetId,applySemanticDressingOverlay}=await import(pathToFileURL(path.join(root,'apps/client/src/sunmeadow-dressing.mjs')).href);
const read=async p=>JSON.parse(await fs.readFile(path.join(root,p),'utf8')),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const basePath='planning/levels/sunmeadow-v3-dressing-p2.json',overlayPath='planning/levels/sunmeadow-water-art-pass4b-r02-overlay.json';
const base=applySemanticDressingOverlay(await read(basePath),await read('planning/levels/sunmeadow-st8-posts-v1.json')),overlay=await read(overlayPath),manifest=await read('assets/models/sunmeadow-props/manifest.json');
const assets=new Map(Object.values(manifest.families).flat().map(a=>[a.id,a]));
for(const p of ['assets/models/blueprint-p0-fence/manifest.json','assets/models/blueprint-p2-torch/manifest.json']){
 const m=await read(p);for(const a of m.assets??Object.values(m.families??{}).flat())assets.set(a.id,a);
}
const removed=new Set(['v3_grotto_mouth','v3_grotto_tunnel',...Array.from({length:7},(_,i)=>'water_art_grotto_bluff_'+String(i).padStart(3,'0'))]);
let entries=base.entries.map(e=>{const p=overlay.L1_patches.find(p=>p.id===e.id);return p?{...e,x:p.x,z:p.z}:e;}).concat(overlay.entries).filter(e=>!removed.has(e.id));
// The only other generated landmark near this region is east of the camera/ray AABB.
entries.push({id:'v3_grotto_crystals',asset_id:'sm_crystals_03',x:10.2,z:-36.1,yaw:0,scale:1,scale_xyz:[1.3,1.65,1.3],landmark:true,footprint_r:12});
const cam=[2.819878161304265,7.452022716769464,-38],targets=[{label:'camera-centre',target:[-9.2,2.5,-38]}];
for(const t of [.1,.3,.6,.9,1.261])for(const z of [-.8,0,.8])targets.push({label:`fall-${t}-${z}`,target:[-7.42-1.5*t,7.45-4.905*t*t,-38+z]});
for(const dx of [-1,0,1])for(const dz of [-1,0,1])targets.push({label:`pool-${dx}-${dz}`,target:[-9.6+dx,-.35,-38+dz]});
const sub=(a,b)=>a.map((v,i)=>v-b[i]),dot=(a,b)=>a.reduce((n,v,i)=>n+v*b[i],0),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
function hit(a,b,t){const d=sub(b,a),e1=sub(t[1],t[0]),e2=sub(t[2],t[0]),h=cross(d,e2),det=dot(e1,h);if(Math.abs(det)<1e-10)return null;const inv=1/det,s=sub(a,t[0]),u=dot(s,h)*inv;if(u< -1e-6||u>1+1e-6)return null;const q=cross(s,e1),v=dot(d,q)*inv;if(v< -1e-6||u+v>1+1e-6)return null;const k=dot(e2,q)*inv;return k>1e-6&&k<1-1e-6?k:null;}
function bounds(verts){return {min:[0,1,2].map(k=>Math.min(...verts.map(p=>p[k]))),max:[0,1,2].map(k=>Math.max(...verts.map(p=>p[k])))};}
function overlaps(b){return b.min[0]<=2.92&&b.max[0]>=-10.7&&b.min[2]<=-36.9&&b.max[2]>=-39.1&&b.max[1]>=-.4&&b.min[1]<=7.6;}
const cache=new Map(),included=[],pruned=[],unknown=[],triangles=[];
for(const entry of entries){
 const id=dressingAssetId(entry,assets),asset=id&&assets.get(id);
 if(!asset?.bounds){if(entry.x>-16&&entry.x<8&&entry.z>-45&&entry.z<-32)unknown.push({id:entry.id,asset:entry.asset_id});continue;}
 const scale=blueprintScale(entry,asset.bounds),cx=(asset.bounds.min[0]+asset.bounds.max[0])/2,cz=(asset.bounds.min[2]+asset.bounds.max[2])/2,c=Math.cos(entry.yaw),s=Math.sin(entry.yaw);
 const aquatic=['lotus','reeds','lilypad'].some(v=>id.includes(v));const baseY=entry.visual_absolute_base_y??(entry.visual_base_y??0),y=entry.surface_y??(aquatic?-.3:baseY-blueprintFloor(entry,asset.bounds,scale));
 // P1 Euler poses are all outside this narrow ray region; record unknown rather than approximate one.
 const transform=v=>{const x=(v[0]-cx)*scale[0],z=(v[2]-cz)*scale[2];return [entry.x+x*c+z*s,y+v[1]*scale[1],entry.z-x*s+z*c];};
 const corners=[];for(const x of [asset.bounds.min[0],asset.bounds.max[0]])for(const yy of [asset.bounds.min[1],asset.bounds.max[1]])for(const z of [asset.bounds.min[2],asset.bounds.max[2]])corners.push(transform([x,yy,z]));
 const bb=bounds(corners);if(!overlaps(bb)){pruned.push({id:entry.id,asset:id,bounds:bb});continue;}
 if(entry.pitch||entry.roll){unknown.push({id:entry.id,asset:id,reason:'Euler pose needs full native matrix'});continue;}
 if(!cache.has(id)){
  const file=asset.lods[0].file,bytes=await fs.readFile(path.join(root,file)),doc=await io.read(path.join(root,file)),ts=[];
  for(const n of doc.getRoot().listNodes()){const mesh=n.getMesh();if(!mesh)continue;const m=n.getWorldMatrix();for(const p of mesh.listPrimitives()){
   const a=p.getAttribute('POSITION'),v=[],el=[];for(let i=0;i<a.getCount();i++){a.getElement(i,el);v.push([-(m[0]*el[0]+m[4]*el[1]+m[8]*el[2]+m[12]),m[1]*el[0]+m[5]*el[1]+m[9]*el[2]+m[13],m[2]*el[0]+m[6]*el[1]+m[10]*el[2]+m[14]]);}
   const idx=p.getIndices()?.getArray()??Array.from({length:v.length},(_,i)=>i);for(let i=0;i<idx.length;i+=3)ts.push([v[idx[i]],v[idx[i+1]],v[idx[i+2]]]);}}
  cache.set(id,{file,sha256:sha(bytes),tris:ts});
 }
 const src=cache.get(id),ts=src.tris.map(t=>t.map(transform));included.push({id:entry.id,asset:id,file:src.file,sha256:src.sha256,triangles:ts.length,bounds:bb,baseY:y});for(const t of ts)triangles.push({id:entry.id,tri:t});
}
const current=await read('planning/evidence/water-art-pass4b-20261003/r03/sculpt-lod0-runtime-geometry.json');
for(const p of current.geometry)for(let i=0;i<p.indices.length;i+=3)triangles.push({id:'sm_grotto_organic_r03',tri:p.indices.slice(i,i+3).map(j=>p.positions[j])});
const rays=targets.map(t=>{let first=null;for(const q of triangles){const k=hit(cam,t.target,q.tri);if(k!==null&&(!first||k<first.k))first={id:q.id,k,point:cam.map((v,i)=>v+k*(t.target[i]-v))};}return {...t,clear:first===null,first};});
const nearCameraIntersections=triangles.filter(q=>q.id!=='sm_grotto_organic_r03'&&[0,1,2].every(k=>Math.min(...q.tri.map(p=>p[k]))<=cam[k]+.1&&Math.max(...q.tri.map(p=>p[k]))>=cam[k]-.1)).length;
const result={schema:'xexoria.sculpt-grotto-remaining-dressing-rays/1',sourceFiles:[basePath,overlayPath],exactIncluded:included,prunedByBoundsCount:pruned.length,prunedByBounds:pruned,unknownNearCandidates:unknown,
 removedVisualIds:[...removed],newGrottoSha256:current.sha256,totalTriangles:triangles.length,rays,remainingDressingCameraNearAabbIntersections:nearCameraIntersections,
 requiredLowerFallPoolRaysClear:rays.filter(r=>!r.label.startsWith('fall-0.1')).every(r=>r.clear),
 limits:['Exact remaining dressing LOD0s plus new grotto; groundY0 is the frozen source placement assumption for non-absolute dressing entries.',
  'Terrain material cutouts, whole-map terrain/city/foliage, particles and alpha coverage require parent native verification; this does not represent a full native scene raycast.']};
await fs.writeFile(path.join(evid,'sculpt-baseline-rays.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({included:included.map(x=>x.id),pruned:pruned.length,unknown,requiredRaysClear:result.requiredLowerFallPoolRaysClear,remainingDressingNearAabb:nearCameraIntersections}));
