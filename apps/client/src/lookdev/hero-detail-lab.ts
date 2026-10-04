import {Scene} from '@babylonjs/core/scene';
import {ArcRotateCamera} from '@babylonjs/core/Cameras/arcRotateCamera';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {Color3,Color4} from '@babylonjs/core/Maths/math.color';
import {HemisphericLight} from '@babylonjs/core/Lights/hemisphericLight';
import {DirectionalLight} from '@babylonjs/core/Lights/directionalLight';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';
import {CreateGround} from '@babylonjs/core/Meshes/Builders/groundBuilder';
import {TransformNode} from '@babylonjs/core/Meshes/transformNode';
import {Mesh} from '@babylonjs/core/Meshes/mesh';
import {createRenderer} from '../renderer-choice';
import {configureAssetCodecs} from '../asset-codecs';
import {loadHeroReview} from '../hero-review-loader';
import {HERO_REVIEW_ROSTER,MAGE_REVIEW_SKILLS} from '../hero-review-policy.mjs';
import {loadVfxKit} from '../combat-vfx-kit';
import {createCombatVfx} from '../combat-vfx-skills';
import {resolveWeaponFxMarkers} from '../combat-vfx-weapon-markers';
import {playerFraming} from '../player-framing.mjs';

/** Native art/animation/FX review using actual candidate bytes, not class or server acceptance. */
export async function mountHeroDetailLab(){
 const query=new URLSearchParams(location.search),canvas=document.getElementById('game-canvas') as HTMLCanvasElement;
 const hud=document.getElementById('hud');if(hud)hud.hidden=true;
 await configureAssetCodecs();const renderer=await createRenderer(canvas),scene=new Scene(renderer.engine);
 (window as unknown as {__xexoria?:unknown}).__xexoria={scene,engine:renderer.engine};
 scene.metadata={heroLabPhase:'lights'};
 const night=query.get('envHour')==='0';scene.clearColor=new Color4(night?.025:.13,night?.028:.18,night?.07:.25,1);
 const camera=new ArcRotateCamera('hero-detail-camera',Math.PI/2,1.25,query.get('heroCamera')==='close'?4:13,new Vector3(0,1,0),scene);camera.attachControl(canvas,true);
 const fill=new HemisphericLight('hero-detail-fill',new Vector3(0,1,0),scene);fill.intensity=night?.55:.8;fill.groundColor=Color3.FromHexString('#263449');
 const sun=new DirectionalLight('hero-detail-key',new Vector3(-.4,-1,.6),scene);sun.intensity=night?.45:1.35;sun.diffuse=Color3.FromHexString(night?'#94aff2':'#ffe3b7');
 const floor=CreateGround('hero-detail-ground',{width:32,height:32,subdivisions:2},scene),mat=new StandardMaterial('hero-detail-stone',scene);mat.diffuseColor=Color3.FromHexString('#384553');mat.specularColor=Color3.Black();floor.material=mat;
 renderer.engine.runRenderLoop(()=>scene.render());
 const heroId=query.get('heroReview')==='01'?'01':'02',basicClip=heroId==='01'?'blade_1h.attack_1':'caster.attack_1';
 scene.metadata.heroLabPhase='model';const hero=new TransformNode('hero-local',scene),asset=await loadHeroReview(scene,heroId,query.get('heroPack')==='r04'?'r04':query.get('heroPack')==='r03'?'r03':query.get('heroPack')==='r02'?'r02':'r01');
 hero.scaling.setAll(playerFraming(location.search,false,true).avatarScale);
 for(const node of [...asset.meshes,...asset.transformNodes])if(!node.parent)node.parent=hero;
 const clips=new Map(asset.animationGroups.map(g=>[g.name,g]));let selectedClip='base.idle',oneShot=false;
 const play=(name:string,loop=true)=>{const clip=clips.get(name);if(!clip)return false;for(const g of clips.values())g.stop();selectedClip=name;oneShot=!loop;clip.start(loop);return true;};play('base.idle');
 const markers=asset.weaponOwner?resolveWeaponFxMarkers(asset.weaponOwner,['fx_head']):null;
 scene.metadata.heroLabPhase='kit';const tier=matchMedia('(pointer:coarse)').matches?'medium':'high',hero02Draft=heroId==='02',kit=await loadVfxKit(scene,{hero02Draft}),fx=createCombatVfx(scene,kit,{groundAt:()=>0,preset:()=>tier,ownKit:true,lookVersion:hero02Draft?2:1,hero02Draft,castOrigin:markers?()=>markers.position('fx_head'):undefined});
 const panel=document.createElement('section');panel.dataset.heroDetailPanel='';panel.style.cssText='position:fixed;left:max(12px,env(safe-area-inset-left));bottom:12px;z-index:1500;padding:10px;max-width:min(600px,calc(100vw - 24px));background:#101d2aeb;color:#dae5ed;border:1px solid #ad9270;font:13px system-ui;display:flex;gap:6px;flex-wrap:wrap';
 const title=document.createElement('strong');title.textContent=`HERO ${heroId} ART / VFX REVIEW · actual rig candidate · no server damage`;title.style.width='100%';panel.append(title);
 const roster=document.createElement('small');roster.textContent=HERO_REVIEW_ROSTER.map(h=>`${h.id} ${h.name}: ${h.state}`).join(' · ');roster.style.width='100%';panel.append(roster);
 const label=document.createElement('label');label.textContent='Animation ';const select=document.createElement('select');select.dataset.heroClip='';for(const name of clips.keys()){const option=document.createElement('option');option.value=name;option.textContent=name;select.append(option);}select.value='base.idle';select.onchange=()=>play(select.value);label.append(select);panel.append(label);
 // Pause before seeking: speedRatio=0 would resample the first frame on the next render.
 const pose=(name:string,phase:number)=>{const clip=clips.get(name);if(!clip)return null;play(name,true);clip.pause();clip.goToFrame(clip.from+(clip.to-clip.from)*Math.max(0,Math.min(1,phase)));select.value=name;return {name,from:clip.from,to:clip.to,frame:clip.getCurrentFrame(),paused:!clip.isPlaying};};
 const status=document.createElement('span');status.dataset.heroFxStatus='';status.textContent='Warming shader variants';
 const buttons:HTMLButtonElement[]=[];
 const reviewSkills=heroId==='02'?MAGE_REVIEW_SKILLS:[
  {id:'h01_lodestar_arc',clip:'swordsman.skill_arc',name:'Lodestar Arc'},
  {id:'xs_bladeward_nova',clip:'swordsman.skill_nova',name:'Bladeward Nova · FX study'},
  {id:'h01_ironfall_cleave',clip:'swordsman.skill_ironfall',name:'Ironfall Cleave'},
  {id:'h01_compass_rush',clip:'swordsman.skill_rush',name:'Compass Rush'},
  {id:'h01_eightfold_ward',clip:'swordsman.skill_ward',name:'Eightfold Ward'},
  {id:'h01_stormfall_cleave',clip:'swordsman.skill_stormfall',name:'Stormfall Cleave'},
 ];
 for(const skill of reviewSkills){const button=document.createElement('button');button.textContent=skill.name;button.dataset.heroSkill=skill.id;button.style.cssText='min-height:44px;padding:8px;background:#203b50;color:#f4e6c8;border:1px solid #ac9474;border-radius:4px';button.disabled=true;button.onclick=()=>{play(skill.clip,false);const ready=fx.previewReadiness(skill.id);const result=ready.ready?fx.cast(skill.id,hero.position,hero.rotation.y):null;status.textContent=result?'Visual cast · gameplay unchanged':heroId==='01'?'Animation study · FX/gameplay pending':ready.missing.join(', ')||'Visual pool unavailable';};buttons.push(button);panel.append(button);}
 panel.append(status);document.body.append(panel);
 const keys=new Set<string>();const down=(e:KeyboardEvent)=>{if(e.target instanceof HTMLInputElement||e.target instanceof HTMLSelectElement||e.target instanceof HTMLButtonElement)return;keys.add(e.code);if(e.code==='Space'){e.preventDefault();play(basicClip,false);}},up=(e:KeyboardEvent)=>keys.delete(e.code);window.addEventListener('keydown',down);window.addEventListener('keyup',up);
 const observer=scene.onBeforeRenderObservable.add(()=>{const dt=Math.min(.05,renderer.engine.getDeltaTime()/1000),x=Number(keys.has('KeyD'))-Number(keys.has('KeyA')),z=Number(keys.has('KeyW'))-Number(keys.has('KeyS'));
  if(x||z){const length=Math.hypot(x,z);hero.position.x+=x/length*4.5*dt;hero.position.z+=z/length*4.5*dt;hero.rotation.y=Math.atan2(x,z);if(selectedClip!=='base.run')play('base.run');}
  else if(selectedClip==='base.run'||oneShot&&!clips.get(selectedClip)?.isPlaying)play('base.idle');
  camera.target.set(hero.position.x,hero.position.y+1,hero.position.z);
 });
 const started=performance.now();for(const mesh of scene.meshes)if(mesh instanceof Mesh&&mesh.material&&mesh.getTotalVertices()){
  scene.metadata.heroLabPhase='warm:'+mesh.name;console.info('[hero-lab-warm]',mesh.name);
  await mesh.material.forceCompilationAsync(mesh,{useInstances:mesh.instances.length>0||mesh.hasThinInstances});
 }
 const deadline=performance.now()+20000;while(!scene.particleSystems.every(p=>p.isReady())){if(performance.now()>deadline)throw Error('Hero particle prewarm deadline');await new Promise(r=>setTimeout(r,16));}
 const warmupMs=performance.now()-started;for(const button of buttons){button.disabled=heroId==='01'?!clips.has(reviewSkills.find(s=>s.id===button.dataset.heroSkill)?.clip??''):!fx.previewReadiness(button.dataset.heroSkill!).ready;button.title=heroId==='01'?'Animation/VFX study only; no gameplay damage':fx.previewReadiness(button.dataset.heroSkill!).missing.join(', ');}status.textContent=`${renderer.engine.isWebGPU?'WebGPU':'WebGL2'} · ready · warm ${warmupMs.toFixed(0)} ms (load time)`;
 scene.metadata.heroLabPhase='ready';
 (window as unknown as {__xexoria?:unknown;__xexHeroLab?:unknown}).__xexoria={scene,engine:renderer.engine};
 (window as unknown as {__xexHeroLab?:unknown}).__xexHeroLab={hero,clips,fx,play,pose,camera,warmupMs,stats:()=>({clip:selectedClip,frame:clips.get(selectedClip)?.getCurrentFrame(),paused:!clips.get(selectedClip)?.isPlaying,position:hero.position.asArray(),joints:asset.skeletons[0].bones.length,fx:fx.stats(),readiness:MAGE_REVIEW_SKILLS.map(s=>({id:s.id,...fx.previewReadiness(s.id)}))})};
 const resize=()=>renderer.engine.resize();window.addEventListener('resize',resize);window.addEventListener('pagehide',()=>{keys.clear();window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);window.removeEventListener('resize',resize);scene.onBeforeRenderObservable.remove(observer);fx.dispose();panel.remove();renderer.engine.stopRenderLoop();scene.dispose();renderer.engine.dispose();},{once:true});
}
