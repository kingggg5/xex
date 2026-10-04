export const WATER_TIERS=Object.freeze({
 low:Object.freeze({lod:2,draws:2,fetches:6,normalStart:18,normalEnd:50,exponent:64,glint:.5,gpuMs:.25,cpuMs:.05}),
 medium:Object.freeze({lod:1,draws:2,fetches:8,normalStart:22,normalEnd:65,exponent:160,glint:.9,gpuMs:.35,cpuMs:.08}),
 high:Object.freeze({lod:0,draws:2,fetches:8,normalStart:25,normalEnd:80,exponent:220,glint:1.2,gpuMs:.5,cpuMs:.10}),
 ultra:Object.freeze({lod:0,draws:2,fetches:8,normalStart:30,normalEnd:100,exponent:220,glint:1.2,gpuMs:.7,cpuMs:.10}),
 epic:Object.freeze({lod:0,draws:2,fetches:8,normalStart:30,normalEnd:100,exponent:220,glint:1.2,gpuMs:.7,cpuMs:.10})
});
export function waterTier(value){return WATER_TIERS[value]??WATER_TIERS.high;}
export function rainPuddleVisibility({ready,revealed,culled,rain}){return !!ready&&!!revealed&&!culled&&Number.isFinite(rain)&&rain>.05;}
export function supportedRainPuddles(bodies,groundAt,{maxOutlineVertices=32}={}){
 if(maxOutlineVertices!==32&&maxOutlineVertices!==48)throw new TypeError('Boundedrainoutlinevertexlimitrequired');
 if(!Array.isArray(bodies)||bodies.length>8||typeof groundAt!=='function')throw new TypeError('Boundedrainpuddlecontractrequired');
 const accepted=[],pending=[];
 for(const b of bodies){
  if(!b||typeof b.id!=='string'||!Array.isArray(b.center_xz)||!Array.isArray(b.outline_xz)||b.outline_xz.length<3||b.outline_xz.length>maxOutlineVertices||!Number.isFinite(b.surface_y)||b.surface_y<0||b.surface_y>.03)throw new TypeError('Invalidrainpuddlegeometry');
  const safe=[b.center_xz,...b.outline_xz].every(p=>{if(p.length!==2||p.some(v=>!Number.isFinite(v)))throw new TypeError('FinitepuddleXZrequired');const y=groundAt(p[0],p[1]);return y!==null&&Number.isFinite(y)&&Math.abs(y)<.001;});
  (safe?accepted:pending).push(safe?b:b.id);
 }
 return {accepted,pending};
}
export function rainPuddleAtlasUV(point,centre,rx,rz,organic=false){
 if(!Array.isArray(point)||!Array.isArray(centre)||point.length!==2||centre.length!==2||[...point,...centre,rx,rz].some(v=>!Number.isFinite(v))||rx<=0||rz<=0)throw new TypeError('Finitepuddleradialmappingrequired');
 const u=(point[0]-centre[0])/(2*rx),v=(point[1]-centre[1])/(2*rz),d=Math.hypot(u,v);
 if(organic&&d<=1e-8)throw new Error('Degenerate organic puddle perimeter');
 const scale=organic?.5/d:1;return [.5+u*scale,.5+v*scale];
}
export function flowCycle(phase){
 if(!Number.isFinite(phase))throw new TypeError('Water phase must be finite');
 const a=((phase/(2*Math.PI)*8)%1+1)%1;
 return {a,b:(a+.5)%1,weightB:Math.abs(2*a-1)};
}
export function fallsTrajectory(t){if(!Number.isFinite(t)||t<0)throw new TypeError('Invalid flight time');return {x:-7.42-1.5*t,y:7.45-4.905*t*t,z:-38};}
export function depthOpacity(depth,viewY=.38){if(!Number.isFinite(depth)||depth<0)throw new TypeError('Invalid depth');return .16+.78*(1-Math.exp(-2.6*depth*(1+.35*(1/Math.max(.25,viewY)-1))));}
export function decodeFlow(r,g){return [(r/255*2-1)*1.2,(g/255*2-1)*1.2];}
export function varianceExponent(exponent,dx,dy){return exponent/(1+exponent*.3*(dx*dx+dy*dy));}
export function validateWaterManifest(m){
 if(!m||m.schema!=='xexoria.water-bodies.v1'||!Array.isArray(m.bodies)||m.bodies.length>16||m.atlas?.width!==1024||m.atlas?.height!==128)throw new TypeError('Invalid water manifest');
 if(!/^[a-f0-9]{64}$/.test(m.layout_sha256)||!m.anchors?.anchor_sm_falls_landing)throw new TypeError('Water input hash/anchor missing');
 for(const [name,a] of Object.entries(m.anchors)){if(!/^(anchor_|emit_)/.test(name)||!Array.isArray(a.position)||a.position.length!==3||a.position.some(v=>!Number.isFinite(v)))throw new TypeError('Invalid anchor');}
 for(const [name,rec] of Object.entries(m.meshes)){const cap=name==='surface'?1300:name==='falls0'?1400:name==='falls1'?1050:500;if(!Number.isInteger(rec.triangles)||rec.triangles>cap)throw new RangeError('Water triangles over budget');}
 return m;
}
const smooth=(a,b,v)=>{const t=Math.max(0,Math.min(1,(v-a)/(b-a)));return t*t*(3-2*t);};
function polygonDistance(x,z,poly){
 let inside=false,distance=Infinity;
 for(let i=0,j=poly.length-1;i<poly.length;j=i++){
  const a=poly[j],b=poly[i],dx=b[0]-a[0],dz=b[1]-a[1],t=Math.max(0,Math.min(1,((x-a[0])*dx+(z-a[1])*dz)/(dx*dx+dz*dz||1)));
  distance=Math.min(distance,Math.hypot(x-a[0]-dx*t,z-a[1]-dz*t));
  if((a[1]>z)!==(b[1]>z)&&x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0])inside=!inside;
 }
 return inside?-distance:distance;
}
/** Terrain owner may query this immutable derived contract while cutting host
 * visual geometry. It does not alter physical support or create colliders. */
export function createWaterTerrainSampler(derived){
 if(!derived||!Array.isArray(derived.stream?.samples_1m)||!Array.isArray(derived.lakes))throw new TypeError('Derived water contract required');
 const samples=derived.stream.samples_1m;
 return (x,z)=>{
  if(!Number.isFinite(x)||!Number.isFinite(z))throw new TypeError('Finite terrain position required');
  let best=null;
  const offer=(body,signed,surface,depth)=>{if(signed>1.2)return;const heightY=signed>0?surface*(1-smooth(0,1.2,signed)):surface-depth;
   if(!best||heightY<best.heightY)best={body,heightY,surfaceY:surface,depthM:Math.max(0,depth),distanceToShoreM:-signed};};
  for(let i=0;i<samples.length-1;i++){
   const a=samples[i],b=samples[i+1],dx=b.x-a.x,dz=b.z-a.z,t=Math.max(0,Math.min(1,((x-a.x)*dx+(z-a.z)*dz)/(dx*dx+dz*dz||1)));
   const distance=Math.hypot(x-a.x-dx*t,z-a.z-dz*t),width=a.w+(b.w-a.w)*t,dc=a.dc+(b.dc-a.dc)*t;
   const signed=distance-width/2,depth=dc*(1-Math.pow(Math.min(1,distance/(width/2)),2.2));
   offer('sunmeadow_stream',signed,a.surface_y+(b.surface_y-a.surface_y)*t,depth);
  }
  const pool=derived.pool,rad=Math.hypot(x-pool.center_xz[0],z-pool.center_xz[1]);
  const depth=Math.max(0,.75*(1-Math.pow(rad/pool.radius,2.5)))+.35*Math.exp(-Math.pow(Math.hypot(x-derived.falls.landing[0],z-derived.falls.landing[2])/.7,2));
  offer('falls_pool',Math.max(rad-pool.radius,x-pool.east_clip_x),-.35,depth);
  for(const lake of derived.lakes){const signed=lake.outline_xz?polygonDistance(x,z,lake.outline_xz):Math.hypot(x-lake.center_xz[0],z-lake.center_xz[1])-lake.radius_m;
   offer(lake.id,signed,lake.surface_y,(lake.surface_y-lake.bed_y)*smooth(0,lake.shallow_band_m??2.2,-signed));}
  return best;
 };
}
