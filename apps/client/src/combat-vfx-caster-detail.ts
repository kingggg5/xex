import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {Color4} from '@babylonjs/core/Maths/math.color';
import type {SkillFactory} from './combat-vfx-skills';
import {decal,instanced,meshLayer,particles,beams,clamp01,type VfxLayer} from './combat-vfx-kit';

/** Bounded kit assembly, authored shapes and atmosphere; these are visual review effects only. */
export function casterDetailFactory(kind:'lance'|'ward'|'orrery'):SkillFactory{return (ctx,origin)=>{
 const kit=ctx.kit,prefix=`caster-${kind}`;
 const ring=decal(kit,'prior-ground','runeInner','void',{intensity:.75,opacity:.75,valueScale:.65});
 const shock=decal(kit,'prior-anticipation','shock','rim',{intensity:.9,opacity:.7,valueScale:.7});
 const core=instanced(kit,'prior-core',kit.crystalShard??kit.blade,'streak','void',kind==='lance'?4:8,{intensity:1.05,opacity:.78,valueScale:.78});
 const shell=meshLayer(kit,`${prefix}-shell`,kit.ringWall,'swirl','rim',{intensity:.52,opacity:.4,valueScale:.6,fresnel:2});
 const orbit=kind==='orrery'?meshLayer(kit,'caster-orrery-orbit',kit.ringWall,'streak','void',{intensity:.65,opacity:.45,valueScale:.65}):null;
 const sparks=particles(kit,'prior-secondary',{capacity:80,texture:'star',color:new Color4(.4,.8,1,.8),color2:new Color4(.96,.69,.3,.8),size:[.035,.12],life:[.25,.7],gravity:new Vector3(0,-.4,0)});
 const dust=particles(kit,'prior-after',{capacity:48,texture:'dust',sheet:{cols:4,rows:4,cell:16,loop:false},blend:'standard',color:new Color4(.4,.32,.62,.3),color2:new Color4(.17,.23,.34,.1),size:[.2,.5],life:[.5,1.1],gravity:new Vector3(0,.12,0)});
 const arc=beams(kit,`${prefix}-filaments`,'rim',8,{intensity:.6,opacity:.5,valueScale:.62});
 const layers:VfxLayer[]=[ring,shock,core,shell,sparks,dust,arc,...(orbit?[orbit]:[])];
 const at=origin.clone(),ahead=new Vector3(),muzzle=new Vector3(),a=new Vector3(),b=new Vector3();
 let facing=0,seed=0,released=false,active=false;
 const release={lance:.467,ward:.3,orrery:.9}[kind],duration={lance:2.4,ward:2.8,orrery:3.8}[kind];
 const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
 sparks.system.startPositionFunction=(_matrix,pos)=>{const theta=random()*Math.PI*2,r=random()*(kind==='orrery'?2:1);pos.set(at.x+Math.cos(theta)*r,at.y+.8+random()*.8,at.z+Math.sin(theta)*r);};
 sparks.system.startDirectionFunction=(_matrix,dir)=>{const theta=random()*Math.PI*2;dir.set(Math.cos(theta)*1.2,.6+random(),Math.sin(theta)*1.2);};
 dust.system.startPositionFunction=(_matrix,pos)=>{const theta=random()*Math.PI*2,r=.6+random()*1.5;pos.set(ahead.x+Math.cos(theta)*r,ahead.y+.12,ahead.z+Math.sin(theta)*r);};
 dust.system.startDirectionFunction=(_matrix,dir)=>{dir.set((random()-.5)*.6,.15+random()*.25,(random()-.5)*.6);};
 const stop=()=>{active=false;for(const layer of [ring,shock,core,shell,arc,...(orbit?[orbit]:[])]){layer.mesh.setEnabled(false);layer.mesh.instances.forEach(i=>i.setEnabled(false));}for(const layer of [sparks,dust]){layer.system.stop();layer.system.reset();layer.system.manualEmitCount=0;}arc.clear();};
 stop();
 return {id:`h02_${kind}_detail_r01`,duration,contract:'VISUAL CANDIDATE · layered kit assembly · no damage or class unlock',layers:()=>layers,
 reset(pos,angle){stop();at.copyFrom(pos);facing=angle;seed=901;released=false;ahead.copyFrom(at).addInPlaceFromFloats(Math.sin(facing)*(kind==='lance'?6:0),0,Math.cos(facing)*(kind==='lance'?6:0));const floor=ctx.groundAt(ahead.x,ahead.z);if(floor===null||!Number.isFinite(floor))throw Error('Unsupported caster effect endpoint');ahead.y=floor;const marker=ctx.castOrigin?.();if(marker){if(![marker.x,marker.y,marker.z].every(Number.isFinite))throw Error('Invalid weapon cast marker');muzzle.set(marker.x,marker.y,marker.z);}else muzzle.copyFrom(at).addInPlaceFromFloats(0,1.25,0);active=true;for(const layer of [sparks,dust])layer.system.start();},
 update(t){if(!active)return;const charge=clamp01(t/release),fade=1-clamp01((t-release-.25)/(duration-release-.25)),impact=clamp01((t-release)/.24);
  if(kind==='lance'&&t<=release){const marker=ctx.castOrigin?.();if(marker&&[marker.x,marker.y,marker.z].every(Number.isFinite))muzzle.set(marker.x,marker.y,marker.z);}
  ring.mesh.setEnabled(fade>.01);ring.mesh.position.set(at.x,at.y+.045,at.z);ring.mesh.scaling.setAll((kind==='orrery'?5:3)*(.65+.35*charge));ring.fx.wipe=charge;ring.fx.opacity=.62*fade;ring.fx.rotation=t*.18;
  shock.mesh.setEnabled(t>=release&&fade>.01);shock.mesh.position.set(ahead.x,ahead.y+.06,ahead.z);shock.mesh.scaling.setAll((kind==='lance'?3:5)*(.4+impact));shock.fx.opacity=.6*fade*(1-clamp01((t-release)/1.1));
  shell.mesh.setEnabled(kind!=='lance'&&fade>.01);shell.mesh.position.set(at.x,at.y+(kind==='orrery'?1.4:.25),at.z);shell.mesh.scaling.set(kind==='orrery'?2:1.6,kind==='orrery'?.035:1.2,kind==='orrery'?2:1.6);shell.fx.opacity=(kind==='orrery'?.55:.14)*charge*fade;shell.fx.scrollV=-t*.13;shell.mesh.rotation.set(kind==='orrery'?.5:0,t*.7,0);
  if(orbit){orbit.mesh.setEnabled(fade>.01);orbit.mesh.position.set(at.x,at.y+1.4,at.z);orbit.mesh.scaling.set(2.1,.035,2.1);orbit.mesh.rotation.set(-.5,-t*.55,.5);orbit.fx.opacity=.45*charge*fade;orbit.fx.scrollU=t*.15;}
  core.mesh.setEnabled(fade>.01);for(const [i,instance] of core.instances.entries()){
   const theta=i/core.instances.length*Math.PI*2+t*(kind==='lance'?0:.65),r=kind==='orrery'?1.7:1.25;
   if(kind==='lance'){const travel=clamp01((t-release)/.38);instance.position.set(muzzle.x+(ahead.x-muzzle.x)*travel+Math.cos(facing)*(i-1.5)*.15,muzzle.y+(ahead.y+.5-muzzle.y)*travel+(i%2)*.2,muzzle.z+(ahead.z-muzzle.z)*travel-Math.sin(facing)*(i-1.5)*.15);instance.rotation.set(Math.PI/2,facing,0);instance.scaling.set(.8,1.4+charge,.8);}
   else{instance.position.set(at.x+Math.cos(theta)*r,at.y+.65+charge*(kind==='orrery'?1.8:1),at.z+Math.sin(theta)*r);instance.rotation.set(0,theta,-.24);instance.scaling.set(.8,(kind==='orrery'?1:.75)*charge,.8);}
   instance.setEnabled(fade>.01);const uniform=instance.instancedBuffers.vfxInst;uniform.x=.78;uniform.y=1-fade;uniform.z=fade;uniform.w=1;
  }
  arc.clear();if(t>=release&&t<release+.45){for(let i=0;i<8;i++){const theta=i/8*Math.PI*2+t; a.set(at.x+Math.cos(theta)*.5,at.y+.7,at.z+Math.sin(theta)*.5);b.set(ahead.x+Math.cos(theta)*1.3,ahead.y+.5+(i%3)*.4,ahead.z+Math.sin(theta)*1.3);arc.set(i,a,b,.025,i,.48*fade);}arc.commit(ctx.eye());}
  if(t>=release&&!released){released=true;sparks.system.manualEmitCount=64;dust.system.manualEmitCount=32;}
 },stop,dispose(){stop();layers.forEach(layer=>layer.dispose());},
 };
};}
