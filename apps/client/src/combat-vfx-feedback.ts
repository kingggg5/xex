import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import type { Material } from "@babylonjs/core/Materials/material";
import type { UniformBuffer } from "@babylonjs/core/Materials/uniformBuffer";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import type { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import type { Scene } from "@babylonjs/core/scene";

export type HitFeedbackKind="light"|"heavy"|"crit"|"counter"|"kill";
export const HIT_STOP_MS:Readonly<Record<HitFeedbackKind,number>>=Object.freeze({light:50,heavy:70,crit:85,counter:85,kill:110});
export function hitStopFor(kind:HitFeedbackKind,ownHit:boolean):number{return ownHit?HIT_STOP_MS[kind]:0;}
const KNOCK:Readonly<Record<HitFeedbackKind,number>>={light:.12,heavy:.30,crit:.25,counter:.35,kill:.12};
const ownedMaterials=new WeakMap<Material,object>();

class FeedbackSurface extends MaterialPluginBase {
	flash=0;dissolve=-1;colour=Color3.FromHexString("#ffd892");
	constructor(material:Material){super(material,"CombatActorFeedback",210,{},true,false);this.registerForExtraEvents=true;this._enable(true);}
	isCompatible(language:ShaderLanguage){return language===ShaderLanguage.GLSL||language===ShaderLanguage.WGSL;}
	getUniforms(language=ShaderLanguage.GLSL){return {ubo:[{name:"actorFeedback",size:4,type:"vec4"},{name:"actorFlashColor",size:3,type:"vec3"}],fragment:language===ShaderLanguage.GLSL?"uniform vec4 actorFeedback;uniform vec3 actorFlashColor;":""};}
	hardBindForSubMesh(buffer:UniformBuffer){buffer.updateFloat4("actorFeedback",this.flash,this.dissolve,0,0);buffer.updateColor3("actorFlashColor",this.colour);}
	getCustomCode(stage:string,language=ShaderLanguage.GLSL){
		if(stage!=="fragment")return null;
		const pbr=this._material.getClassName().startsWith("PBR"),colour=pbr?"finalColor":"color",wgsl=language===ShaderLanguage.WGSL;
		return wgsl?{CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR:`
let actorCell=floor(fragmentInputs.vPositionW*38.0);
let actorNoise=fract(sin(dot(actorCell,vec3f(12.9898,78.233,39.425)))*43758.5453);
if(uniforms.actorFeedback.y>=0.0 && actorNoise<uniforms.actorFeedback.y){discard;}
let actorEdge=select(0.0,1.0-smoothstep(0.0,.055,actorNoise-uniforms.actorFeedback.y),uniforms.actorFeedback.y>0.0);
${colour}=vec4f(mix(${colour}.rgb,uniforms.actorFlashColor,min(.60,uniforms.actorFeedback.x+actorEdge*.35)),${colour}.a);`}:{CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR:`
vec3 actorCell=floor(vPositionW*38.0);
float actorNoise=fract(sin(dot(actorCell,vec3(12.9898,78.233,39.425)))*43758.5453);
if(actorFeedback.y>=0.0 && actorNoise<actorFeedback.y)discard;
float actorEdge=actorFeedback.y>0.0?1.0-smoothstep(0.0,.055,actorNoise-actorFeedback.y):0.0;
${colour}.rgb=mix(${colour}.rgb,actorFlashColor,min(.60,actorFeedback.x+actorEdge*.35));`};
	}
}

/** Cosmetic child only. Shared actor materials must be cloned once by the view owner before admission. */
export function createActorFeedback(scene:Scene,visual:TransformNode,materials:readonly Material[],options:{now?:()=>number;rank?:"normal"|"elite"|"boss";reduceMotion?:()=>boolean}={}){
	const token={},clock=options.now??(()=>performance.now()),home=visual.position.clone(),rank=options.rank??"normal";
	for(const material of materials)if(ownedMaterials.has(material))throw new Error("Combat feedback requires per-actor materials");
	const actorMaterials=[...new Set(materials)];
	const surfaces=actorMaterials.map(material=>{ownedMaterials.set(material,token);return material.pluginManager?.getPlugin("CombatActorFeedback") as FeedbackSurface??new FeedbackSurface(material);});
	let disposed=false,hitAt=-1e6,flashAt=-1e6,deathAt:number|null=null,lastFlashAt=-1e6,mutedFlash=false;
	const direction=new Vector3();let distance=0;
	const pickability=new Map<ReturnType<TransformNode["getChildMeshes"]>[number],boolean>();
	const observer=scene.onBeforeRenderObservable.add(()=>{
		if(disposed||visual.isDisposed())return;const now=clock(),age=now-hitAt,flashAge=now-flashAt;
		const knock=age<70?1-(1-age/70)**3:age<290?1-((age-70)/220)**2:0;
		// Never write the authoritative monster root or its world coordinates.
		visual.position.copyFrom(home).addInPlaceFromFloats(direction.x*distance*knock,0,direction.z*distance*knock);
		const flash=mutedFlash?(flashAge<120?.35:0):flashAge<=40?.60:Math.max(0,.60*(1-(flashAge-40)/80));
		for(const surface of surfaces){surface.flash=flash;surface.dissolve=deathAt===null?-1:Math.max(0,Math.min(1,(now-deathAt-450)/800));}
		if(deathAt!==null&&now-deathAt>=1250)visual.setEnabled(false);
	});
	const disposal=scene.onDisposeObservable.addOnce(()=>api.dispose());
	const api={
		hit(kind:HitFeedbackKind,attackerX:number,attackerZ:number){
			if(disposed||deathAt!==null||![attackerX,attackerZ].every(Number.isFinite))return;
			const now=clock(),parent=visual.parent as TransformNode|null,root=parent?.getAbsolutePosition?.()??visual.getAbsolutePosition();direction.set(root.x-attackerX,0,root.z-attackerZ);if(direction.lengthSquared()>1e-8)direction.normalize();
			distance=options.reduceMotion?.()?0:rank==="boss"?0:KNOCK[kind]*(rank==="elite"?.5:1);
			hitAt=flashAt=now;mutedFlash=now-lastFlashAt<334;if(!mutedFlash)lastFlashAt=now;
		},
		die(){if(disposed||deathAt!==null)return;deathAt=clock();for(const mesh of visual.getChildMeshes()){pickability.set(mesh,mesh.isPickable);mesh.isPickable=false;}},
		respawn(){if(disposed)return;deathAt=null;hitAt=flashAt=-1e6;visual.position.copyFrom(home);visual.setEnabled(true);for(const [mesh,value] of pickability)if(!mesh.isDisposed())mesh.isPickable=value;pickability.clear();for(const surface of surfaces){surface.flash=0;surface.dissolve=-1;}},
		async prewarm(){const meshes=visual.getChildMeshes();await Promise.all(actorMaterials.flatMap(material=>{const mesh=meshes.find(mesh=>mesh.material===material);return mesh?[material.forceCompilationAsync(mesh)]:[];}));},
		get dying(){return deathAt!==null;},get finished(){return deathAt!==null&&clock()-deathAt>=1250;},
		dispose(){if(disposed)return;disposed=true;scene.onBeforeRenderObservable.remove(observer);scene.onDisposeObservable.remove(disposal);if(!visual.isDisposed())visual.position.copyFrom(home);for(const [mesh,value] of pickability)if(!mesh.isDisposed())mesh.isPickable=value;pickability.clear();for(let i=0;i<actorMaterials.length;i++){if(ownedMaterials.get(actorMaterials[i])===token)ownedMaterials.delete(actorMaterials[i]);surfaces[i].flash=0;surfaces[i].dissolve=-1;surfaces[i].dispose();}},
	};
	return api;
}
