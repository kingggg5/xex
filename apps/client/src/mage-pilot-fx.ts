import { Mesh } from '@babylonjs/core/Meshes/mesh';
import { VertexData } from '@babylonjs/core/Meshes/mesh.vertexData';
import { VertexBuffer } from '@babylonjs/core/Buffers/buffer';
import { StandardMaterial } from '@babylonjs/core/Materials/standardMaterial';
import { Material } from '@babylonjs/core/Materials/material';
import { Color3 } from '@babylonjs/core/Maths/math.color';
import { Quaternion, Vector3 } from '@babylonjs/core/Maths/math.vector';
import type { Scene } from '@babylonjs/core/scene';
import { mageDynamicShape, mageOpenSigilShape, magePointedShape, mageShardShape, type MageShape } from './mage-pilot-fx-geometry';

export type MagePilotAbility='h02_basic'|'h02_star_lance';
export type MagePilotId=string|number;
export interface MagePilotCast {
 /** Root must supply an epoch-scoped server ID; client animation events cannot mint one. */
 castId:MagePilotId;actorId:MagePilotId;ability:MagePilotAbility;
 targetXZ:Readonly<{x:number;z:number}>;
 /** All timestamps use the injected server-clock milliseconds. */
 startedAt:number;releaseAt:number;impactAt:number|null;facing:number;
 /** Numeric estimates are presentation-only while deferred; null impact implies deferral. */
 deferReleaseUntilConfirmed?:boolean;
}
export interface MagePilotReleasedCast {
 castId:MagePilotId;origin:Readonly<{x:number;y:number;z:number}>;
 targetXZ:Readonly<{x:number;z:number}>;releaseAt:number;impactAt:number;
}
export interface MagePilotResolution {
 castId:MagePilotId;outcome:'hit'|'miss'|'cancelled';targetXZ:Readonly<{x:number;z:number}>;
 /** Cosmetic only: root supplies worldXZ body radius plus surface clearance. */
 contactRadius?:number;
}
/** Clip events are source30fps metadata; Babylon import frames may use a different fps. */
export function magePilotMotion(cast:Pick<MagePilotCast,'ability'|'startedAt'|'releaseAt'>){
 const lance=cast.ability==='h02_star_lance',sourceReleaseMs=lance?14/30*1000:100;
 return {clip:lance?'mage.skill_bolt':'caster.attack_1',
  speedRatio:sourceReleaseMs/Math.max(1,cast.releaseAt-cast.startedAt),sourceReleaseMs};
}
export interface MagePilotOptions {
 now():number;
 castOrigin(actorId:MagePilotId):Readonly<{x:number;y:number;z:number}>|null;
 groundAt(x:number,z:number):number|null;
 onMotion?(cast:Readonly<MagePilotCast>,phase:'accepted'|'released'|'hit'|'miss'|'cancelled'|'expired'):void;
 lowEffects?():boolean;
 prewarmDeadlineMs?:number;
 basicCapacity?:number;lanceCapacity?:number;
 deferReleaseUntilConfirmed?:boolean;
}
type DynamicMesh={mesh:Mesh;positions:Float32Array;normals:Float32Array;indices:number[]};
type Slot={lance:boolean;core:Mesh;trail:DynamicMesh;shards:DynamicMesh;sigil:Mesh|null;
 coreMaterial:StandardMaterial;trailMaterial:StandardMaterial;sigilMaterial:StandardMaterial|null;
 cast:MagePilotCast|null;key:string;generation:number;phase:'free'|'charge'|'travel'|'await'|'hit'|'fade';
 resolvedAt:number;origin:Vector3;goal:Vector3;contact:Vector3;contactFacing:number;contactGroundY:number;contactRadius:number;position:Vector3;released:boolean;
 deferRelease:boolean;flight:Readonly<MagePilotReleasedCast>|null;flightFingerprint:string};
const clamp=(n:number)=>Math.max(0,Math.min(1,n));
const validId=(n:unknown):n is MagePilotId=>typeof n==='string'?n.length>0&&n.length<=96:typeof n==='number'&&Number.isSafeInteger(n)&&n>=0;
const idKey=(id:MagePilotId)=>typeof id+':'+String(id);
const finitePoint=(point:Readonly<{x:number;y:number;z:number}>|null)=>!!point&&[point.x,point.y,point.z].every(n=>Number.isFinite(n)&&Math.abs(n)<=10000);
const finiteXZ=(point:Readonly<{x:number;z:number}>|null)=>!!point&&[point.x,point.z].every(n=>Number.isFinite(n)&&Math.abs(n)<=10000);
const owners=new WeakMap<Scene,ReturnType<typeof createMagePilotFx>>();

/** Two presentation templates only. No ability/resource/reward/gameplay mutation.
 * Timed travel predicts presentation; ONLY resolve(hit) creates a confirmed impact.
 */
export function createMagePilotFx(scene:Scene,options:MagePilotOptions){
 if(scene.isDisposed)throw new Error('Cannot create Mage pilot in a disposed scene');
 if(owners.has(scene))throw new Error('Mage pilot presentation already owns this scene');
 const materials:StandardMaterial[]=[],meshes:Mesh[]=[],history=new Map<string,string>();
 let disposed=false,ready=false,prewarmState='NOT_STARTED',prewarmPromise:Promise<void>|null=null;
 let cancelPrewarm:(()=>void)|null=null,clock=0,lastCpuMs=0;
 let accepted=0,confirmedHits=0,cancelled=0,invalid=0,duplicates=0,dropped=0,callbackErrors=0,expired=0;
 let releaseUpdates=0,duplicateReleaseUpdates=0,invalidReleaseUpdates=0;
 const readOrigin=(actorId:MagePilotId)=>{try{return options.castOrigin(actorId);}catch{callbackErrors++;return null;}};
 const readGround=(x:number,z:number)=>{try{return options.groundAt(x,z);}catch{callbackErrors++;return null;}};
 const readNow=()=>{try{return options.now();}catch{callbackErrors++;return NaN;}};
 const readLow=()=>{try{return !!options.lowEffects?.();}catch{callbackErrors++;return true;}};
 const material=(name:string)=>{
  const m=new StandardMaterial('mage-pilot-fx-'+name,scene);materials.push(m);
  m.disableLighting=true;m.diffuseColor=Color3.White();m.emissiveColor=new Color3(.90,.90,.90);
  m.specularColor=Color3.Black();m.backFaceCulling=false;m.disableDepthWrite=true;
  m.transparencyMode=Material.MATERIAL_ALPHABLEND;m.alpha=.999;m.fogEnabled=true;
  return m;
 };
 const makeMesh=(name:string,shape:MageShape,m:StandardMaterial,updatable=false)=>{
  const mesh=new Mesh('mage-pilot-fx-'+name,scene),data=new VertexData();
  data.positions=shape.positions;data.indices=shape.indices;data.colors=shape.colors;
  const normals=new Float32Array(shape.positions.length);VertexData.ComputeNormals(shape.positions,shape.indices,normals);data.normals=normals;
  data.applyToMesh(mesh,updatable);mesh.material=m;mesh.hasVertexAlpha=true;mesh.isPickable=false;mesh.receiveShadows=false;
  mesh.metadata={magePilotFx:true,glow:false,serverDamage:false};mesh.setEnabled(false);meshes.push(mesh);
  return {mesh,positions:Float32Array.from(shape.positions),normals,indices:shape.indices};
 };
 const createSlot=(lance:boolean,index:number):Slot=>{
  const prefix=(lance?'lance':'basic')+'-'+index,coreMaterial=material(prefix+'-facets'),trailMaterial=material(prefix+'-trail');
  const core=makeMesh(prefix+'-core',magePointedShape(lance),coreMaterial).mesh;
  const trail=makeMesh(prefix+'-trail',mageDynamicShape(lance?12:6),trailMaterial,true);
  const shards=makeMesh(prefix+'-shards',mageShardShape(lance?12:6),coreMaterial,true);
  const sigilMaterial=lance?material(prefix+'-sigil'):null;
  const sigil=sigilMaterial?makeMesh(prefix+'-open-sigil',mageOpenSigilShape(),sigilMaterial).mesh:null;
  return {lance,core,trail,shards,sigil,coreMaterial,trailMaterial,sigilMaterial,cast:null,key:'',generation:0,
   phase:'free',resolvedAt:0,origin:Vector3.Zero(),goal:Vector3.Zero(),contact:Vector3.Zero(),contactFacing:0,contactGroundY:0,contactRadius:0,position:Vector3.Zero(),released:false,
   deferRelease:false,flight:null,flightFingerprint:''};
 };
 const capacity=(n:number|undefined,fallback:number)=>n===undefined?fallback:Number.isInteger(n)?Math.max(1,Math.min(16,n)):fallback;
 const slots=[...Array.from({length:capacity(options.basicCapacity,8)},(_,i)=>createSlot(false,i)),
  ...Array.from({length:capacity(options.lanceCapacity,4)},(_,i)=>createSlot(true,i))];
 const direction=Vector3.Zero(),side=Vector3.Zero(),up=new Vector3(0,1,0),rotation=Quaternion.Identity();
 const notify=(slot:Slot,phase:Parameters<NonNullable<MagePilotOptions['onMotion']>>[1])=>{
  if(!slot.cast)return;try{options.onMotion?.(slot.cast,phase);}catch{callbackErrors++;}
 };
 const hide=(slot:Slot)=>{
  slot.core.setEnabled(false);slot.trail.mesh.setEnabled(false);slot.shards.mesh.setEnabled(false);slot.sigil?.setEnabled(false);
 };
 const free=(slot:Slot)=>{hide(slot);slot.cast=null;slot.phase='free';slot.flight=null;slot.flightFingerprint='';slot.generation++;};
 const deadline=(slot:Slot)=>((slot.deferRelease&&!slot.flight?slot.cast!.releaseAt:slot.flight?.impactAt??slot.cast!.impactAt??slot.cast!.releaseAt)+1500);
 const prepareContact=(slot:Slot,radius?:number)=>{
  // Cosmetic surface contact only. The explicit projectile/collision goal stays intact.
  const dx=slot.origin.x-slot.goal.x,dz=slot.origin.z-slot.goal.z,d=Math.hypot(dx,dz);
  slot.contactFacing=d>.001?Math.atan2(dx,dz):slot.cast!.facing+Math.PI;
  const offset=radius??(slot.lance?.85:.75);slot.contactRadius=offset;
  slot.contact.copyFrom(slot.goal).addInPlaceFromFloats(Math.sin(slot.contactFacing)*offset,.18,Math.cos(slot.contactFacing)*offset);
  const floor=readGround(slot.contact.x,slot.contact.z);
  slot.contactGroundY=floor!==null&&Number.isFinite(floor)&&Math.abs(floor)<=10000?floor:slot.goal.y-.65;
  slot.contact.y=Math.max(slot.contact.y,slot.contactGroundY+.78);
 };
 const upload=(dynamic:DynamicMesh)=>{
  VertexData.ComputeNormals(dynamic.positions,dynamic.indices,dynamic.normals);
  dynamic.mesh.updateVerticesData(VertexBuffer.PositionKind,dynamic.positions,true);
  dynamic.mesh.updateVerticesData(VertexBuffer.NormalKind,dynamic.normals,false);
 };
 const trail=(slot:Slot,progress:number,fade:number)=>{
  const mesh=slot.trail.mesh,p=slot.trail.positions,total=slot.trail.indices.length/6;
  const count=slot.lance?6:total;
  const low=readLow(),width=slot.lance?.055:.025;
  direction.copyFrom(slot.goal).subtractInPlace(slot.origin);
  const distance=Math.max(.001,direction.length());direction.scaleInPlace(1/distance);
  Vector3.CrossToRef(direction,up,side);if(side.lengthSquared()<.00001)side.set(1,0,0);else side.normalize();
  for(let q=0;q<total;q++){
   const lane=Math.floor(q/count),segment=q%count,from=Math.max(0,progress-(segment+1)*.035),to=Math.max(0,progress-segment*.035);
   const w=width*(1-segment/count)*fade*(low&&lane>0?0:1),curl=slot.lance?Math.sin(segment*.8+lane*Math.PI)*.05:0;
   const a=from*distance,b=to*distance;
   for(let v=0;v<4;v++){
    const d=v<2?a:b,s=(v===0||v===3?1:-1)*w+curl;
    const offset=q*12+v*3;p[offset]=slot.origin.x+direction.x*d+side.x*s;
    p[offset+1]=slot.origin.y+direction.y*d+(slot.lance?Math.cos(segment*.8+lane*Math.PI)*.018:0);
    p[offset+2]=slot.origin.z+direction.z*d+side.z*s;
   }
  }
  upload(slot.trail);mesh.setEnabled(progress>0&&fade>.01);slot.trailMaterial.alpha=.62*fade;
 };
 const burst=(slot:Slot,age:number)=>{
  const fade=1-clamp(age/320),p=slot.shards.positions,count=slot.shards.positions.length/12;
  const actual=readLow()?Math.min(4,count):count;
  for(let q=0;q<count;q++){
   const a=slot.contactFacing+(q/Math.max(1,count-1)-.5)*Math.PI*2/3,t=age/1000;
   const r=(slot.lance?.12:.06)+t*(slot.lance?1.7:1.2),size=q<actual?(slot.lance?.125:.065)*fade:0;
   const x=slot.contact.x+Math.sin(a)*r,y=slot.contact.y+t*(.9+(q%3)*.25)-2*t*t,z=slot.contact.z+Math.cos(a)*r;
   // Four actual facets, a sharp tip, and a volumetric base; no flat fleck cloud.
   for(let v=0;v<4;v++){const offset=q*12+v*3;p[offset]=x+(v===1?-size:v===2?size:0);
    p[offset+1]=y+(v===0?size*2.2:-size*.8);p[offset+2]=z+(v===3?size*.8:-size*.45);}
  }
  upload(slot.shards);slot.shards.mesh.setEnabled(fade>.01);slot.coreMaterial.alpha=.92*fade;
  // A short transparent ice spine rises ONLY on confirmed signature contact,
  // reusing the projectile draw. The target stays visible through its thin shell.
  if(slot.lance&&!readLow()&&age<180){
   slot.core.position.set(slot.contact.x,slot.contactGroundY+.40,slot.contact.z);
   slot.core.rotationQuaternion??=Quaternion.Identity();Quaternion.RotationYawPitchRollToRef(0,-Math.PI/2,0,slot.core.rotationQuaternion);
   slot.core.scaling.setAll(.35+.25*Math.sin(clamp(age/180)*Math.PI));slot.core.setEnabled(true);
  }else slot.core.setEnabled(false);
  if(slot.sigil&&slot.sigilMaterial){
   slot.sigil.billboardMode=Mesh.BILLBOARDMODE_NONE;
   slot.sigil.position.set(slot.contact.x,slot.contactGroundY+.035,slot.contact.z);slot.sigil.rotation.set(Math.PI/2,0,0);
   slot.sigil.scaling.setAll(.45+.35*clamp(age/320));slot.sigilMaterial.alpha=.40*fade;
   slot.sigil.setEnabled(fade>.01&&!readLow());
  }
 };
 const updateSlot=(slot:Slot)=>{
  if(!slot.cast||!ready||disposed)return;
  const cast=slot.cast;
  const releaseAt=slot.flight?.releaseAt??cast.releaseAt,impactAt=slot.flight?.impactAt??cast.impactAt;
  if(slot.phase==='hit'){burst(slot,clock-slot.resolvedAt);if(clock-slot.resolvedAt>=320)free(slot);return;}
  if(slot.phase==='fade'){
   const fade=1-clamp((clock-slot.resolvedAt)/100);slot.coreMaterial.alpha=.45*fade;slot.trailMaterial.alpha=.45*fade;
   if(slot.sigilMaterial)slot.sigilMaterial.alpha=.45*fade;
   if(fade<=0)free(slot);return;
  }
  if(clock<cast.startedAt){hide(slot);return;}
  if(slot.deferRelease&&!slot.flight&&clock>deadline(slot)){
   expired++;notify(slot,'expired');if(slot.cast===cast)free(slot);return;
  }
  if(!slot.released&&(clock<releaseAt||(slot.deferRelease&&!slot.flight))){
   const point=readOrigin(cast.actorId);
   if(!finitePoint(point)){cancelled++;slot.phase='fade';slot.resolvedAt=clock;notify(slot,'cancelled');return;}
   slot.origin.set(point!.x,point!.y,point!.z);slot.position.copyFrom(slot.origin);
   const charge=clamp((clock-cast.startedAt)/Math.max(1,releaseAt-cast.startedAt));
   slot.core.position.copyFrom(slot.origin);slot.core.rotationQuaternion??=Quaternion.Identity();
   Quaternion.RotationYawPitchRollToRef(cast.facing,0,0,slot.core.rotationQuaternion);
   slot.core.scaling.setAll(slot.lance?.12+.22*charge:.14+.16*charge);slot.coreMaterial.alpha=.50+.40*charge;slot.core.setEnabled(true);
   if(slot.sigil&&slot.sigilMaterial){slot.sigil.billboardMode=Mesh.BILLBOARDMODE_Y;slot.sigil.position.copyFrom(slot.origin);slot.sigil.rotation.set(0,0,0);
    slot.sigil.scaling.setAll(.45+.55*charge);slot.sigilMaterial.alpha=.36+.42*charge;slot.sigil.setEnabled(true);}
   slot.phase='charge';return;
  }
  if(impactAt===null)return;
  if(!slot.released){
   const point=slot.flight?.origin??readOrigin(cast.actorId);if(finitePoint(point))slot.origin.set(point!.x,point!.y,point!.z);
   slot.released=true;notify(slot,'released');if(disposed||slot.cast!==cast)return;
  }
  const progress=clamp((clock-releaseAt)/Math.max(1,impactAt-releaseAt));
  Vector3.LerpToRef(slot.origin,slot.goal,progress,slot.position);
  slot.core.position.copyFrom(slot.position);slot.core.scaling.setAll(1);
  direction.copyFrom(slot.goal).subtractInPlace(slot.origin);
  if(direction.lengthSquared()>.00001){direction.normalize();
   // Authored mesh forward is+Z. Look-direction quaternions use camera conventions.
   Quaternion.RotationYawPitchRollToRef(Math.atan2(direction.x,direction.z),-Math.atan2(direction.y,Math.hypot(direction.x,direction.z)),0,rotation);
   slot.core.rotationQuaternion??=Quaternion.Identity();slot.core.rotationQuaternion.copyFrom(rotation);}
  const unconfirmedFade=1-clamp((clock-impactAt)/150);
  slot.coreMaterial.alpha=.92*unconfirmedFade;slot.core.setEnabled(unconfirmedFade>.01);trail(slot,progress,unconfirmedFade);
  if(slot.sigilMaterial)slot.sigilMaterial.alpha=.78*(1-clamp((clock-releaseAt)/180));
  if(slot.sigil)slot.sigil.setEnabled(clock<releaseAt+180);
  slot.phase=progress<1?'travel':'await';
  if(clock>deadline(slot)){expired++;notify(slot,'expired');if(slot.cast===cast)free(slot);}
 };
 const update=()=>{
  if(disposed)return;const time=readNow();if(!Number.isFinite(time))return;clock=Math.max(clock,time);
  const started=performance.now();for(const slot of slots)updateSlot(slot);lastCpuMs=performance.now()-started;
 };
 const observer=scene.onBeforeRenderObservable.add(update);
 const sceneDisposal=scene.onDisposeObservable.addOnce(()=>runtime.dispose());
 const runtime={
  beginAcceptedCast(input:MagePilotCast):boolean{
   if(disposed)return false;
   const time=readNow();
   const deferred=input?.deferReleaseUntilConfirmed??options.deferReleaseUntilConfirmed??input?.impactAt===null;
   const estimate=input?.impactAt??input?.releaseAt;
   if(!ready||!Number.isFinite(time)||!validId(input?.castId)||!validId(input?.actorId)||
    !['h02_basic','h02_star_lance'].includes(input?.ability)||!finiteXZ(input?.targetXZ)||
    typeof deferred!=='boolean'||(input.impactAt===null&&!deferred)||(input.impactAt!==null&&!Number.isFinite(input.impactAt))||
    ![input.startedAt,input.releaseAt,estimate,input.facing].every(Number.isFinite)||
    input.releaseAt<input.startedAt||estimate<input.releaseAt||estimate-input.startedAt>30000||time>(deferred?input.releaseAt:estimate)+1500||input.startedAt>time+10000){invalid++;return false;}
   const cast=Object.freeze({castId:input.castId,actorId:input.actorId,ability:input.ability,targetXZ:Object.freeze({x:input.targetXZ.x,z:input.targetXZ.z}),startedAt:input.startedAt,releaseAt:input.releaseAt,impactAt:input.impactAt,facing:input.facing,deferReleaseUntilConfirmed:deferred});
   const key=idKey(input.castId),fingerprint=JSON.stringify(cast);
   if(history.has(key)){if(history.get(key)===fingerprint)duplicates++;else invalid++;return false;}
   const origin=readOrigin(input.actorId),ground=readGround(input.targetXZ.x,input.targetXZ.z);
   if(!finitePoint(origin)||ground===null||!Number.isFinite(ground)||Math.abs(ground)>10000){invalid++;return false;}
   history.set(key,fingerprint);if(history.size>512)history.delete(history.keys().next().value!);
   const slot=slots.find(s=>!s.cast&&s.lance===(input.ability==='h02_star_lance'));
   if(!slot){dropped++;return false;}
   slot.cast=cast;slot.key=key;slot.generation++;slot.phase='charge';slot.released=false;slot.deferRelease=deferred;slot.flight=null;slot.flightFingerprint='';
   slot.origin.set(origin!.x,origin!.y,origin!.z);slot.goal.set(cast.targetXZ.x,ground+.65,cast.targetXZ.z);
   slot.shards.mesh.setEnabled(false);accepted++;clock=Math.max(clock,time);notify(slot,'accepted');if(!disposed)updateSlot(slot);return true;
  },
  /** An authoritative released/impact snapshot updates an existing accepted cast.
   * It never allocates a new nonce, replays accepted motion or creates hit feedback. */
  confirmReleasedCast(input:MagePilotReleasedCast):boolean{
   if(disposed||!validId(input?.castId)||!finitePoint(input?.origin)||!finiteXZ(input?.targetXZ)||
    ![input.releaseAt,input.impactAt].every(Number.isFinite)||input.impactAt<input.releaseAt){invalidReleaseUpdates++;return false;}
   const slot=slots.find(s=>s.cast&&s.key===idKey(input.castId)&&!['hit','fade'].includes(s.phase));
   if(!slot)return false;
   const time=readNow(),cast=slot.cast!;
   if(!Number.isFinite(time)||input.releaseAt<cast.startedAt||input.impactAt-cast.startedAt>30000||input.releaseAt>time+10000||time>input.impactAt+1500){invalidReleaseUpdates++;return false;}
   const ground=readGround(input.targetXZ.x,input.targetXZ.z);
   if(ground===null||!Number.isFinite(ground)||Math.abs(ground)>10000){invalidReleaseUpdates++;return false;}
   const flight=Object.freeze({castId:input.castId,origin:Object.freeze({x:input.origin.x,y:input.origin.y,z:input.origin.z}),
    targetXZ:Object.freeze({x:input.targetXZ.x,z:input.targetXZ.z}),releaseAt:input.releaseAt,impactAt:input.impactAt});
   const fingerprint=JSON.stringify(flight);
   if(slot.flightFingerprint===fingerprint){duplicateReleaseUpdates++;return false;}
   slot.flight=flight;slot.flightFingerprint=fingerprint;
   if(slot.released)slot.origin.set(flight.origin.x,flight.origin.y,flight.origin.z);
   slot.goal.set(flight.targetXZ.x,ground+.65,flight.targetXZ.z);releaseUpdates++;clock=Math.max(clock,time);updateSlot(slot);return true;
  },
  resolve(input:MagePilotResolution):boolean{
   if(disposed||!validId(input?.castId)||!['hit','miss','cancelled'].includes(input?.outcome)||!finiteXZ(input?.targetXZ))return false;
   // Hit placement may use known target bounds; malformed radii cannot produce
   // unbounded cosmetic geometry. Miss/cancel never consult a contact radius.
   if(input.outcome==='hit'&&input.contactRadius!==undefined&&
    (!Number.isFinite(input.contactRadius)||input.contactRadius<.25||input.contactRadius>4)){invalid++;return false;}
   const slot=slots.find(s=>s.cast&&s.key===idKey(input.castId)&&!['hit','fade'].includes(s.phase));if(!slot)return false;
   const time=readNow();if(!Number.isFinite(time))return false;clock=Math.max(clock,time);
   if(clock>deadline(slot)){const stale=slot.cast;expired++;notify(slot,'expired');if(slot.cast===stale)free(slot);return false;}
   const cast=slot.cast;hide(slot);slot.resolvedAt=clock;
   if(input.outcome==='hit'){
    const ground=readGround(input.targetXZ.x,input.targetXZ.z);
    if(ground!==null&&Number.isFinite(ground)&&Math.abs(ground)<=10000)slot.goal.set(input.targetXZ.x,ground+.65,input.targetXZ.z);
    prepareContact(slot,input.contactRadius);slot.phase='hit';confirmedHits++;notify(slot,'hit');if(!disposed&&slot.cast===cast&&slot.phase==='hit')burst(slot,0);
   }else{slot.phase='fade';if(input.outcome==='cancelled')cancelled++;notify(slot,input.outcome);}
   return true;
  },
  prewarm():Promise<void>{
   if(disposed)return Promise.reject(new Error('Mage pilot is disposed'));
   if(prewarmPromise)return prewarmPromise;
   const limit=Number.isFinite(options.prewarmDeadlineMs)?options.prewarmDeadlineMs!:15000;
   prewarmState='WARMING';const deadline=performance.now()+Math.max(50,Math.min(15000,limit));
   prewarmPromise=new Promise<void>((resolve,reject)=>{
    let timer:ReturnType<typeof setTimeout>|undefined,ended=false;
    const finish=(error?:Error)=>{if(ended)return;ended=true;if(timer!==undefined)clearTimeout(timer);cancelPrewarm=null;
     if(error){prewarmState=disposed?'DISPOSED':'FAILED';reject(error);}else{ready=true;prewarmState='READY';resolve();}};
    cancelPrewarm=()=>finish(new Error('Mage pilot prewarm cancelled by disposal'));
    const poll=()=>{
     if(disposed){finish(new Error('Mage pilot disposed during prewarm'));return;}
     if(performance.now()>deadline){finish(new Error('Mage pilot material warmup deadline'));return;}
     try{if(meshes.every(mesh=>(mesh.material as StandardMaterial).isReadyForSubMesh(mesh,mesh.subMeshes[0],false))){finish();return;}}
     catch(error){finish(error instanceof Error?error:new Error(String(error)));return;}
     timer=setTimeout(poll,16);
    };poll();
   });return prewarmPromise;
  },
  clear(){for(const slot of slots)free(slot);history.clear();const time=readNow();if(Number.isFinite(time))clock=time;},
  stats(){return {ready,prewarmState,active:slots.filter(s=>s.cast).length,phases:slots.filter(s=>s.cast).map(s=>({castId:s.cast!.castId,actorId:s.cast!.actorId,phase:s.phase,generation:s.generation,
   deferReleaseUntilConfirmed:s.deferRelease,flightConfirmed:!!s.flight,releaseAt:s.flight?.releaseAt??s.cast!.releaseAt,impactAt:s.flight?.impactAt??s.cast!.impactAt,
   projectileGoal:s.goal.asArray(),cosmeticContact:s.phase==='hit'?s.contact.asArray():null,cosmeticContactRadius:s.phase==='hit'?s.contactRadius:null})),
   drawCallsEstimate:meshes.filter(m=>m.isEnabled()).length,meshCount:meshes.length,materialCount:materials.length,history:history.size,
   accepted,confirmedHits,cancelled,invalid,duplicates,dropped,callbackErrors,expired,releaseUpdates,duplicateReleaseUpdates,invalidReleaseUpdates,lastUpdateCpuMs:lastCpuMs,particles:0,lights:0,
   scope:'PRESENTATION_ONLY; estimates are not native draw/device qualification'};},
  dispose(){if(disposed)return;disposed=true;ready=false;cancelPrewarm?.();runtime.clear();
   scene.onBeforeRenderObservable.remove(observer);scene.onDisposeObservable.remove(sceneDisposal);
   for(const mesh of meshes)mesh.dispose(false,false);for(const m of materials)m.dispose(false,false);owners.delete(scene);prewarmState='DISPOSED';},
 };
 owners.set(scene,runtime);return runtime;
}
