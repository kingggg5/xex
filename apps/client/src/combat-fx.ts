import type { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Vector3, Quaternion } from "@babylonjs/core/Maths/math.vector";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import type { Scene } from "@babylonjs/core/scene";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";
import { VertexData } from "@babylonjs/core/Meshes/mesh.vertexData";
import { ParticleSystem } from "@babylonjs/core/Particles/particleSystem";
import { Scalar } from "@babylonjs/core/Maths/math.scalar";
import { Constants } from "@babylonjs/core/Engines/constants";
import type { GlowLayer } from "@babylonjs/core/Layers/glowLayer";
import type { Observer } from "@babylonjs/core/Misc/observable";
import { shouldShowCombatFx } from "./combat-vfx-policy.mjs";
import { resolveWeaponFxMarkers } from "./combat-vfx-weapon-markers";

/**
 * Trauma-based camera shake inspired by Sekiro/Shinobi-Duel.
 * Trauma decays exponentially; displacement is proportional to trauma^2 (non-linear impact response).
 */
export class CameraRig {
	private camera: ArcRotateCamera;
	private baseTarget = new Vector3(0, 0, 0);
	private trauma = 0;
	private time = 0;
	private fovPunch = 0;
	private baseFov: number;
	private shakeEnabled=true;

	constructor(camera: ArcRotateCamera) {
		this.camera = camera;
		this.baseFov = camera.fov;
		this.baseTarget.copyFrom(camera.target);
	}

	setTarget(x: number, y: number, z: number): void {
		this.baseTarget.set(x, y, z);
	}

	setBaseFov(fov: number): void {
		this.baseFov = fov;
	}

	addTrauma(amount: number): void {
		if(!this.shakeEnabled||!Number.isFinite(amount)||amount<=0)return;
		this.trauma = Math.min(1.0, this.trauma + amount);
	}

	punchFov(amount: number): void {
		if(!this.shakeEnabled||!Number.isFinite(amount)||amount<=0)return;
		this.fovPunch = Math.min(1.0, this.fovPunch + amount);
	}
	setShakeEnabled(enabled:boolean):void {
		this.shakeEnabled=enabled;
		if(!enabled){this.trauma=0;this.fovPunch=0;this.camera.target.copyFrom(this.baseTarget);this.camera.fov=this.baseFov;}
	}

	update(dt: number): void {
		this.time += dt;
		this.trauma = Math.max(0, this.trauma - dt * 2.0);
		this.fovPunch *= Math.exp(-dt / 0.12);

		const shake = this.trauma * this.trauma;
		if (shake > 0.001) {
			const t = this.time;
			// Multi-frequency noise shake
			const nx = (Math.sin(t * 47) * 0.6 + Math.sin(t * 109) * 0.4) * shake * 0.28;
			const ny = (Math.sin(t * 53) * 0.6 + Math.sin(t * 127) * 0.4) * shake * 0.22;
			const nz = (Math.sin(t * 41) * 0.6 + Math.sin(t * 97) * 0.4) * shake * 0.28;

			this.camera.target.set(
				this.baseTarget.x + nx,
				this.baseTarget.y + ny,
				this.baseTarget.z + nz,
			);
		} else {
			this.camera.target.copyFrom(this.baseTarget);
		}

		// Subtle FOV punch on impacts / quickstep
		const targetFov = this.baseFov - this.fovPunch * 0.08;
		this.camera.fov = targetFov;
	}
}

/**
 * Hit-stop micro-freeze gives weapon impacts mechanical crunch.
 */
export class HitStop {
	private stopUntil = 0;
	constructor(private readonly clock:()=>number=()=>performance.now()) {}

	trigger(durationMs = 70): void {
		if(!Number.isFinite(durationMs)||durationMs<=0)return;
		// A weaker hit never shortens an existing freeze; bursts do not add durations.
		this.stopUntil = Math.max(this.stopUntil,this.clock()+Math.min(120,durationMs));
	}

	isStopped(now = this.clock()): boolean {
		return now < this.stopUntil;
	}
	remainingMs(now=this.clock()):number{return Math.max(0,this.stopUntil-now);}
	clear():void{this.stopUntil=0;}
}

export interface CombatFxOptions {
	groundAt(x: number, z: number): number | null;
	lowDetail: boolean;
	/** Injectable monotonic clock for deterministic lifecycle tests. */
	now?: () => number;
}
const WARNING_CAPACITY = 64;
const IMPACT_CAPACITY = 12;
const HIT_CAPACITY = 12;
const ARC_CAPACITY = 4;
const TRAIL_SAMPLES = 24;
const SUBDIVISIONS = 3;
const TRAIL_POINTS = (TRAIL_SAMPLES - 1) * SUBDIVISIONS + 1;
type WarningState = "free" | "warning" | "armed" | "fade";
export type TelegraphStyle="amber"|"unblockable"|"guard"|"opening";
interface WarningSlot {
	root: TransformNode; ring: Mesh; fill: Mesh; pulse: Mesh;
	generation: number; state: WarningState; x: number; z: number; radius: number;
	start: number; deadline: number; duration: number; fadeAt: number; supported: boolean;
}
interface ImpactSlot { mesh: Mesh; particles: ParticleSystem; emitter: Vector3; active: boolean; start: number; radius: number }
interface HitSlot { mesh: Mesh; particles: ParticleSystem; emitter: Vector3; active: boolean; start: number }
interface ArcSlot { mesh: Mesh; colors: Float32Array; active: boolean; start: number }
const owners = new WeakMap<Scene, SceneCombatFx>();
const clamp = (value: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, value));
const smooth = (value: number) => { const t=clamp(value,0,1); return t*t*(3-2*t); };

/** One owner, one clock/scene observer. Secondary overload replaces oldest pooled effects. */
export function createCombatFx(scene: Scene, options: CombatFxOptions = { groundAt: () => 0, lowDetail: false }): SceneCombatFx {
	const existing=owners.get(scene);
	if(existing) return existing;
	const system=new SceneCombatFx(scene,options); owners.set(scene,system); return system;
}

export class SceneCombatFx {
	private readonly clock: () => number;
	private lowDetail: boolean;
	private lowEffects=false;
	private disposed=false;
	private readonly materials: StandardMaterial[]=[];
	private readonly textures: DynamicTexture[]=[];
	private readonly warnings: WarningSlot[]=[];
	private readonly impacts: ImpactSlot[]=[];
	private readonly hits: HitSlot[]=[];
	private readonly arcs: ArcSlot[]=[];
	private readonly observer: Observer<Scene>;
	private readonly disposeObserver: Observer<Scene>;
	private readonly glow: GlowLayer | undefined;
	private readonly up=Vector3.Up();
	private readonly normal=Vector3.Up();
	private readonly tilt=Quaternion.Identity();
	private readonly trail: Mesh;
	private readonly trailColors=new Float32Array(TRAIL_POINTS*2*4);
	private readonly trailPositions=new Float32Array(TRAIL_POINTS*2*3);
	private readonly trailBase=Array.from({length:TRAIL_SAMPLES},()=>Vector3.Zero());
	private readonly trailTip=Array.from({length:TRAIL_SAMPLES},()=>Vector3.Zero());
	private readonly trailTimes=new Float64Array(TRAIL_SAMPLES);
	private readonly trailWeights=new Float32Array(TRAIL_SAMPLES);
	private readonly currentBase=Vector3.Zero();
	private readonly currentTip=Vector3.Zero();
	private readonly localBase=new Vector3(0,-.45,0);
	private readonly localTip=new Vector3(0,.97,0);
	private sword: Mesh | null=null;
	private weaponOwner: TransformNode | null=null;
	private weaponMarkers: ReturnType<typeof resolveWeaponFxMarkers> | null=null;
	private trailCount=0;
	private trailHead=-1;
	private trailUntil=-1;
	private trailArc=false;
	private readonly steel: StandardMaterial;
	private readonly gold: StandardMaterial;
	private impactCount=0;
	private hitCount=0;
	private warningOverflows=0;
	private unsupported=0;
	private hideOthers=false;
	private readonly warningMaterials=new Map<TelegraphStyle,StandardMaterial>();

	constructor(private readonly scene: Scene, private readonly options: CombatFxOptions) {
		this.clock=options.now ?? (()=>performance.now()); this.lowDetail=options.lowDetail;
		this.glow=scene.effectLayers?.find(layer=>layer.name==="env-glow") as GlowLayer | undefined;
		const warning=this.mask("combat-warning-mask",256,"warning");
		const fill=this.mask("combat-fill-mask",128,"fill");
		const wave=this.mask("combat-wave-mask",128,"wave");
		const spark=this.mask("combat-spark-mask",64,"spark");
		const flash=this.mask("combat-flash-mask",64,"flash");
		const trailMask=this.mask("combat-blade-mask",128,"blade");
		const ringMat=this.material("combat-warning-material","#fff3c4",warning);
		this.warningMaterials.set("amber",ringMat);
		for(const [style,color] of [["unblockable","#ef6045"],["guard","#b4d9e8"],["opening","#f2c45d"]] as const){
			const texture=this.mask("combat-warning-"+style,256,style);
			this.warningMaterials.set(style,this.material("combat-warning-"+style+"-material",color,texture));
		}
		const fillMat=this.material("combat-fill-material","#eea958",fill);
		const pulseMat=this.material("combat-pulse-material","#ffe2a1",wave);
		const waterMat=this.material("combat-water-ring-material","#9bd1ea",wave);
		const flashSteel=this.material("combat-hit-steel-material","#b9deeb",flash,true);
		const flashGold=this.material("combat-hit-gold-material","#edc784",flash,true);
		this.steel=this.material("combat-trail-steel-material","#87bddb",trailMask,true);
		this.gold=this.material("combat-trail-gold-material","#e2bc77",trailMask,true);
		for(let i=0;i<WARNING_CAPACITY;i++) {
			const root=new TransformNode("combat-warning-root-"+i,scene);
			const ring=this.groundMesh("combat-warning-ring-"+i,ringMat,root);
			const inner=this.groundMesh("combat-warning-fill-"+i,fillMat,root); inner.position.y=.002;
			const pulse=this.groundMesh("combat-warning-pulse-"+i,pulseMat,root); pulse.position.y=.003;
			root.setEnabled(false);
			this.warnings.push({root,ring,fill:inner,pulse,generation:0,state:"free",x:0,z:0,radius:1,start:0,deadline:0,duration:1,fadeAt:0,supported:false});
		}
		for(let i=0;i<IMPACT_CAPACITY;i++) {
			const emitter=Vector3.Zero();
			const mesh=this.groundMesh("combat-splash-ring-"+i,waterMat);
			const particles=this.particles("combat-droplets-"+i,spark,emitter,true);
			mesh.setEnabled(false);this.impacts.push({mesh,particles,emitter,active:false,start:0,radius:1});
		}
		for(let i=0;i<HIT_CAPACITY;i++) {
			const emitter=Vector3.Zero();
			const mesh=MeshBuilder.CreatePlane("combat-hit-flash-"+i,{size:1},scene);
			this.configure(mesh,flashSteel);mesh.billboardMode=Mesh.BILLBOARDMODE_ALL;mesh.setEnabled(false);
			const particles=this.particles("combat-hit-sparks-"+i,spark,emitter,false);
			this.hits.push({mesh,particles,emitter,active:false,start:0});
		}
		for(let i=0;i<ARC_CAPACITY;i++) {
			const mesh=new Mesh("combat-arc-crescent-"+i,scene);
			const count=33, positions=new Float32Array(count*2*3),uvs=new Float32Array(count*2*2),colors=new Float32Array(count*2*4),normals=new Float32Array(count*2*3),indices:number[]=[];
			for(let j=0;j<count;j++) {
				const angle=-Math.PI/3+j/(count-1)*Math.PI*2/3;
				for(let side=0;side<2;side++) {
					const vertex=j*2+side,radius=side?4:4*.72;
					positions[vertex*3]=Math.sin(angle)*radius;positions[vertex*3+2]=Math.cos(angle)*radius;
					normals[vertex*3+1]=1;uvs[vertex*2]=j/(count-1);uvs[vertex*2+1]=side;
					colors.set([1,1,1,0],vertex*4);
				}
				if(j<count-1){const v=j*2;indices.push(v,v+1,v+3,v,v+3,v+2);}
			}
			const data=new VertexData();data.positions=positions;data.normals=normals;data.uvs=uvs;data.colors=colors;data.indices=indices;data.applyToMesh(mesh,true);
			this.configure(mesh,this.gold);mesh.hasVertexAlpha=true;mesh.setEnabled(false);this.arcs.push({mesh,colors,active:false,start:0});
		}
		const paths=[Array.from({length:TRAIL_POINTS},()=>Vector3.Zero()),Array.from({length:TRAIL_POINTS},()=>Vector3.Zero())];
		this.trail=MeshBuilder.CreateRibbon("combat-blade-trail",{pathArray:paths,updatable:true},scene);
		this.configure(this.trail,this.steel);this.trail.hasVertexAlpha=true;this.trail.alwaysSelectAsActiveMesh=true;
		this.trail.setVerticesData(VertexBuffer.ColorKind,this.trailColors,true,4);
		const uv=new Float32Array(TRAIL_POINTS*2*2);
		// CreateRibbon orders its vertex paths consecutively: base path then tip path.
		for(let side=0;side<2;side++)for(let i=0;i<TRAIL_POINTS;i++){const v=side*TRAIL_POINTS+i;uv[v*2]=i/(TRAIL_POINTS-1);uv[v*2+1]=side;}
		this.trail.updateVerticesData(VertexBuffer.UVKind,uv);this.trail.setEnabled(false);
		this.observer=scene.onBeforeRenderObservable.add(()=>this.tick());
		this.disposeObserver=scene.onDisposeObservable.addOnce(()=>this.dispose());
		// Particle effects are engine-owned; ask Babylon to prepare their shader variants.
		for(const slot of this.impacts)slot.particles.isReady();
		for(const slot of this.hits)slot.particles.isReady();
		// Keep flash materials referenced even before the first strong hit.
		this.flashSteel=flashSteel;this.flashGold=flashGold;
	}
	private readonly flashSteel: StandardMaterial;
	private readonly flashGold: StandardMaterial;
	private configure(mesh: Mesh, material: StandardMaterial): void {
		mesh.material=material;mesh.isPickable=false;mesh.checkCollisions=false;mesh.receiveShadows=false;
		this.glow?.addExcludedMesh(mesh);
	}
	private groundMesh(name: string, material: StandardMaterial, parent?: TransformNode): Mesh {
		const mesh=MeshBuilder.CreateGround(name,{width:1,height:1,subdivisions:1},this.scene);
		this.configure(mesh,material);if(parent)mesh.parent=parent;return mesh;
	}
	private material(name:string,color:string,texture:DynamicTexture,additive=false):StandardMaterial {
		const material=new StandardMaterial(name,this.scene);
		material.disableLighting=true;material.diffuseColor.set(0,0,0);material.emissiveColor=Color3.FromHexString(color);
		material.specularColor.set(0,0,0);material.diffuseTexture=texture;material.emissiveTexture=texture;
		material.useAlphaFromDiffuseTexture=true;material.backFaceCulling=false;material.fogEnabled=false;
		material.disableDepthWrite=true;material.zOffset=-2;
		if(additive)material.alphaMode=Constants.ALPHA_ADD;
		this.materials.push(material);return material;
	}
	private mask(name:string,size:number,kind:"warning"|"fill"|"wave"|"spark"|"flash"|"blade"|"unblockable"|"guard"|"opening"):DynamicTexture {
		const texture=new DynamicTexture(name,{width:size,height:size},this.scene,false,Texture.BILINEAR_SAMPLINGMODE);
		texture.hasAlpha=true;texture.wrapU=texture.wrapV=Texture.CLAMP_ADDRESSMODE;
		const c=texture.getContext() as CanvasRenderingContext2D;c.clearRect(0,0,size,size);
		if(kind==="unblockable") {
			const center=size/2;c.strokeStyle="rgba(255,255,255,.95)";c.lineWidth=size*.025;
			for(const radius of [.44,.37]){c.beginPath();c.arc(center,center,size*radius,0,Math.PI*2);c.stroke();}
			for(let i=0;i<12;i++){const a=i*Math.PI/6;c.beginPath();c.moveTo(center+Math.cos(a-.035)*size*.40,center+Math.sin(a-.035)*size*.40);c.lineTo(center+Math.cos(a)*size*.48,center+Math.sin(a)*size*.48);c.lineTo(center+Math.cos(a+.035)*size*.40,center+Math.sin(a+.035)*size*.40);c.stroke();}
		} else if(kind==="guard"||kind==="opening") {
			const center=size/2;c.strokeStyle="rgba(255,255,255,.97)";c.lineWidth=size*.025;c.beginPath();
			const points=kind==="guard"?4:8;
			for(let i=0;i<points*2;i++){const angle=i*Math.PI/points-Math.PI/2,r=i%2?size*.08:size*.43,x=center+Math.cos(angle)*r,y=center+Math.sin(angle)*r;if(i===0)c.moveTo(x,y);else c.lineTo(x,y);}c.closePath();c.stroke();
		} else if(kind==="blade") {
			const gradient=c.createLinearGradient(0,0,0,size);
			gradient.addColorStop(0,"rgba(255,255,255,0)");gradient.addColorStop(.65,"rgba(180,208,231,.2)");
			gradient.addColorStop(.94,"rgba(240,247,255,.95)");gradient.addColorStop(1,"rgba(255,255,255,.15)");
			c.fillStyle=gradient;c.fillRect(0,0,size,size);
		} else if(kind==="warning"||kind==="wave") {
			const center=size/2,radius=size*.46;
			c.beginPath();c.arc(center,center,radius,0,Math.PI*2);c.strokeStyle=kind==="warning"?"rgba(8,12,18,.95)":"rgba(62,115,151,.4)";c.lineWidth=size*.07;c.stroke();
			c.beginPath();c.arc(center,center,radius-size*.014,0,Math.PI*2);c.strokeStyle=kind==="warning"?"rgba(255,186,75,.95)":"rgba(196,233,252,.9)";c.lineWidth=size*.021;c.stroke();
			c.beginPath();c.arc(center,center,radius-size*.034,0,Math.PI*2);c.strokeStyle=kind==="warning"?"rgba(255,209,126,.27)":"rgba(156,210,241,.24)";c.lineWidth=size*.03;c.stroke();
		} else {
			const gradient=c.createRadialGradient(size/2,size/2,0,size/2,size/2,size*.48);
			gradient.addColorStop(0,kind==="fill"?"rgba(255,202,109,.28)":"rgba(255,255,255,.96)");
			gradient.addColorStop(kind==="fill"?.88:.18,kind==="fill"?"rgba(255,186,72,.22)":"rgba(223,242,255,.66)");
			gradient.addColorStop(1,"rgba(255,255,255,0)");c.fillStyle=gradient;c.fillRect(0,0,size,size);
		}
		texture.update(false);this.textures.push(texture);return texture;
	}
	private particles(name:string,texture:DynamicTexture,emitter:Vector3,droplets:boolean):ParticleSystem {
		const system=new ParticleSystem(name,48,this.scene);
		system.particleTexture=texture;system.emitter=emitter;system.emitRate=0;system.manualEmitCount=0;
		system.updateSpeed=1/60;system.disposeOnStop=false;system.targetStopDuration=.03;
		system.minLifeTime=droplets?.18:.08;system.maxLifeTime=droplets?.5:.25;
		system.minSize=droplets?.04:.025;system.maxSize=droplets?.1:.065;
		system.minEmitPower=droplets?1.8:2.5;system.maxEmitPower=droplets?3.8:7;
		system.createPointEmitter(Vector3.Zero(),Vector3.Up());
		system.gravity.set(0,droplets?-9.8:-3,0);system.blendMode=ParticleSystem.BLENDMODE_ADD;
		if(!droplets){system.billboardMode=ParticleSystem.BILLBOARDMODE_STRETCHED;system.minScaleY=2;system.maxScaleY=3.5;}
		system.color1=new Color4(.64,.83,1,.9);system.color2=new Color4(.91,.97,1,.8);system.colorDead=new Color4(.5,.7,1,0);
		return system;
	}
	private placeOnGround(root: TransformNode,x:number,z:number,radius:number):boolean {
		const h=this.options.groundAt(x,z);if(h===null||!Number.isFinite(h)){root.setEnabled(false);this.unsupported++;return false;}
		root.position.set(x,h+.035,z);root.rotationQuaternion ??=Quaternion.Identity();
		root.rotationQuaternion.set(0,0,0,1);
		const d=.6*radius,l=this.options.groundAt(x-d,z),r=this.options.groundAt(x+d,z),n=this.options.groundAt(x,z-d),s=this.options.groundAt(x,z+d);
		if(l!==null&&r!==null&&n!==null&&s!==null&&[l,r,n,s].every(Number.isFinite)) {
			const gx=(r-l)/(2*d),gz=(s-n)/(2*d);
			const residual=Math.max(Math.abs((l+r)/2-h),Math.abs((n+s)/2-h));
			if(Math.hypot(gx,gz)<=Math.tan(Math.PI/6)&&residual<=.08) {
				this.normal.set(-gx,1,-gz).normalize();Quaternion.FromUnitVectorsToRef(this.up,this.normal,this.tilt);
				root.rotationQuaternion.copyFrom(this.tilt);
			}
		}
		root.setEnabled(true);return true;
	}
	acquireWarning(x:number,z:number,radius:number,duration:number,style:TelegraphStyle="amber"):{slot:WarningSlot;generation:number}|null {
		if(this.disposed||!Number.isFinite(x)||!Number.isFinite(z))return null;
		const slot=this.warnings.find(value=>value.state==="free");
		if(!slot){this.warningOverflows++;return null;} // Never evict another actor's active warning.
		slot.generation++;slot.state="warning";slot.x=x;slot.z=z;
		slot.ring.material=this.warningMaterials.get(style)??this.warningMaterials.get("amber")!;
		slot.radius=Number.isFinite(radius)?clamp(radius,.1,30):2.5;slot.duration=Number.isFinite(duration)?Math.max(1,duration):900;
		slot.start=this.clock();slot.deadline=slot.start+slot.duration;slot.root.scaling.set(slot.radius*2,1,slot.radius*2);
		slot.supported=this.placeOnGround(slot.root,x,z,slot.radius);
		slot.ring.visibility=1;slot.fill.visibility=1;slot.pulse.visibility=1;slot.fill.scaling.set(.001,1,.001);
		return {slot,generation:slot.generation};
	}
	isCurrent(slot:WarningSlot,generation:number):boolean {return !this.disposed&&slot.generation===generation&&slot.state!=="free";}
	now():number {return this.clock();}
	cancelWarning(slot:WarningSlot,generation:number):void {
		if(!this.isCurrent(slot,generation)||slot.state==="fade")return;
		slot.state="fade";slot.fadeAt=this.clock();
	}
	confirmWarning(slot:WarningSlot,generation:number):void {
		if(!this.isCurrent(slot,generation)||slot.state==="fade")return;
		slot.state="free";slot.root.setEnabled(false);
		const impact=this.impacts.find(value=>!value.active)??this.impacts.reduce((a,b)=>a.start<b.start?a:b);
		impact.particles.stop();impact.particles.reset();
		impact.active=true;impact.start=this.clock();impact.radius=slot.radius;
		if(!this.placeOnGround(impact.mesh,slot.x,slot.z,slot.radius)){impact.active=false;return;}
		impact.mesh.visibility=1;impact.mesh.scaling.set(slot.radius*2*.55,1,slot.radius*2*.55);
		impact.emitter.set(slot.x,impact.mesh.position.y+.08,slot.z);
		impact.particles.direction1.set(-.8,1,-.8);impact.particles.direction2.set(.8,1.5,.8);
		impact.particles.manualEmitCount=this.lowEffects?0:this.lowDetail?12:24;if(!this.lowEffects)impact.particles.start();this.impactCount++;
	}
	createSplashTelegraph(x:number,z:number,radius=2.5,durationMs=900,style:TelegraphStyle="amber"):SplashTelegraph {
		return new SplashTelegraph(this.scene,x,z,radius,durationMs,this,style);
	}
	setLowDetail(low:boolean):void {this.lowDetail=low;}
	/** User preference independent of the graphics tier. Warning outline/fill and party identity persist. */
	setLowEffects(low:boolean):void {
		this.lowEffects=low;if(low){this.clearTrail();for(const slot of [...this.hits,...this.impacts]){slot.particles.stop();slot.particles.reset();slot.particles.manualEmitCount=0;}}
		for(const slot of this.warnings)slot.pulse.setEnabled(!low);
	}
	setHideOtherEffects(value:boolean):void{this.hideOthers=value;}
	attachSword(sword:Mesh|null):void {this.sword=sword;this.weaponOwner=null;this.weaponMarkers=null;this.clearTrail();}
	attachWeaponMarkers(owner:TransformNode|null):void {
		const markers=owner?resolveWeaponFxMarkers(owner,['fx_base','fx_tip']):null;
		this.sword=null;this.weaponOwner=owner;this.weaponMarkers=markers;this.clearTrail();
	}
	beginBladeSwing():void {if(this.disposed)return;this.clearTrail();this.trailArc=false;this.trailUntil=this.clock()+700;this.trail.material=this.steel;}
	playSlash(x:number,y:number,z:number,facing:number,isArc:boolean,relation:"mine"|"party"|"other"="mine"):void {
		if(!shouldShowCombatFx("slash",relation,{hideOthers:this.hideOthers}))return;
		if(this.disposed||![x,y,z,facing].every(Number.isFinite))return;
		if(this.trailUntil<this.clock())this.beginBladeSwing();
		if(!isArc)return;this.trailArc=true;this.trail.material=this.gold;
		const slot=this.arcs.find(value=>!value.active)??this.arcs.reduce((a,b)=>a.start<b.start?a:b);
		slot.active=true;slot.start=this.clock();slot.mesh.position.set(x,y+.9,z);slot.mesh.rotation.y=facing;
		slot.mesh.scaling.setAll(1);slot.mesh.visibility=1;slot.mesh.setEnabled(true);
	}
	hitBurst(x:number,y:number,z:number,attackerX:number,attackerZ:number,strong=false,relation:"mine"|"party"|"other"="mine"):void {
		if(!shouldShowCombatFx("impact",relation,{hideOthers:this.hideOthers}))return;
		if(this.disposed||![x,y,z,attackerX,attackerZ].every(Number.isFinite))return;
		const slot=this.hits.find(value=>!value.active)??this.hits.reduce((a,b)=>a.start<b.start?a:b);
		slot.particles.stop();slot.particles.reset();slot.active=true;slot.start=this.clock();
		slot.mesh.material=strong?this.flashGold:this.flashSteel;slot.mesh.position.set(x,y,z);
		slot.mesh.scaling.setAll(strong?.8:.48);slot.mesh.visibility=1;slot.mesh.setEnabled(true);
		slot.emitter.set(x,y,z);const dx=x-attackerX,dz=z-attackerZ,len=Math.hypot(dx,dz)||1;
		slot.particles.direction1.set(dx/len-.25,.05,dz/len-.25);slot.particles.direction2.set(dx/len+.25,.4,dz/len+.25);
		slot.particles.color1.set(strong?1:.65,strong?.76:.84,strong?.36:1,.9);
		slot.particles.color2.set(1,strong?.91:.97,strong?.62:1,.8);
		slot.particles.manualEmitCount=this.lowEffects?0:(strong?28:14)/(this.lowDetail?2:1);if(!this.lowEffects)slot.particles.start();this.hitCount++;
	}
	private clearTrail():void {this.trailCount=0;this.trailHead=-1;this.trail?.setEnabled(false);}
	private updateTrail(now:number):void {
		if(this.lowEffects){this.clearTrail();return;}
		if(this.weaponOwner?.isDisposed()){this.weaponOwner=null;this.weaponMarkers=null;}
		if(!this.weaponMarkers&&(!this.sword||this.sword.isDisposed())){this.clearTrail();return;}
		if(now<this.trailUntil) {
			if(this.weaponMarkers){
				const base=this.weaponMarkers.position('fx_base'),tip=this.weaponMarkers.position('fx_tip');
				this.currentBase.set(base.x,base.y,base.z);this.currentTip.set(tip.x,tip.y,tip.z);
			}else{
				const matrix=this.sword!.computeWorldMatrix(true);
				Vector3.TransformCoordinatesToRef(this.localBase,matrix,this.currentBase);Vector3.TransformCoordinatesToRef(this.localTip,matrix,this.currentTip);
			}
			const previous=this.trailHead;
			if(previous>=0 && Vector3.DistanceSquared(this.trailTip[previous],this.currentTip)>9)this.clearTrail();
			if(this.trailHead<0||now>this.trailTimes[this.trailHead]) {
				const last=this.trailHead;this.trailHead=(this.trailHead+1)%TRAIL_SAMPLES;
				const index=this.trailHead;this.trailBase[index].copyFrom(this.currentBase);this.trailTip[index].copyFrom(this.currentTip);
				const dt=last>=0?Math.max(.001,(now-this.trailTimes[last])/1000):0;
				this.trailWeights[index]=dt>0?smooth((Vector3.Distance(this.trailTip[last],this.currentTip)/dt-2.5)/6.5):0;
				this.trailTimes[index]=now;this.trailCount=Math.min(TRAIL_SAMPLES,this.trailCount+1);
			}
		}
		const lifetime=this.trailArc?200:140;
		if(this.trailCount>0&&now-this.trailTimes[this.trailHead]>=lifetime){this.clearTrail();return;}
		if(this.trailCount<2){this.trail.setEnabled(false);return;}
		const first=(this.trailHead-this.trailCount+1+TRAIL_SAMPLES)%TRAIL_SAMPLES;
		const at=(index:number)=>(first+clamp(index,0,this.trailCount-1))%TRAIL_SAMPLES;
		for(let point=0;point<TRAIL_POINTS;point++) {
			const fraction=point/(TRAIL_POINTS-1)*(this.trailCount-1),segment=Math.min(this.trailCount-2,Math.floor(fraction)),t=fraction-segment;
			const a=at(segment-1),b=at(segment),c=at(segment+1),d=at(segment+2);
			const age=now-(this.trailTimes[b]+(this.trailTimes[c]-this.trailTimes[b])*t);
			const weight=this.trailWeights[b]+(this.trailWeights[c]-this.trailWeights[b])*t;
			const alpha=Math.max(0,1-age/lifetime)*weight;
			for(let side=0;side<2;side++) {
				const path=side?this.trailTip:this.trailBase,v=side*TRAIL_POINTS+point;
				for(let axis=0;axis<3;axis++) {
					const key=axis===0?"x":axis===1?"y":"z";
					this.trailPositions[v*3+axis]=Scalar.Hermite(path[b][key],(path[c][key]-path[a][key])*.5,path[c][key],(path[d][key]-path[b][key])*.5,t);
				}
				this.trailColors[v*4]=this.trailColors[v*4+1]=this.trailColors[v*4+2]=1;this.trailColors[v*4+3]=alpha;
			}
		}
		this.trail.updateVerticesData(VertexBuffer.PositionKind,this.trailPositions);
		this.trail.updateVerticesData(VertexBuffer.ColorKind,this.trailColors);this.trail.setEnabled(true);
	}
	private tick():void {
		if(this.disposed)return;const now=this.clock();
		for(const slot of this.warnings) {
			if(slot.state==="free")continue;
			if(slot.state==="warning"&&now>=slot.deadline)slot.state="armed";
			if(slot.state==="armed"&&now-slot.deadline>650){slot.state="fade";slot.fadeAt=now;}
			if(slot.state==="fade") {
				const alpha=1-(now-slot.fadeAt)/180;
				if(alpha<=0){slot.state="free";slot.root.setEnabled(false);continue;}
				slot.ring.visibility=slot.fill.visibility=slot.pulse.visibility=alpha;continue;
			}
			const progress=clamp((now-slot.start)/slot.duration,0,1),scale=Math.max(.001,progress);
			slot.fill.scaling.set(scale,1,scale);
			slot.pulse.visibility=.3+.5*Math.abs(Math.sin((now-slot.start)/1000*(6+progress*14)));
			const pulseScale=.90+.06*Math.sin((now-slot.start)/1000*(6+progress*14));slot.pulse.scaling.set(pulseScale,1,pulseScale);
		}
		for(const slot of this.impacts)if(slot.active) {
			const t=(now-slot.start)/420;
			if(t>=1){slot.mesh.setEnabled(false);if(now-slot.start>=600){slot.active=false;slot.particles.stop();slot.particles.reset();}continue;}
			const scale=slot.radius*2*(.55+.65*(1-(1-t)**3));slot.mesh.scaling.set(scale,1,scale);slot.mesh.visibility=(1-t)**2;
		}
		for(const slot of this.hits)if(slot.active) {
			const age=now-slot.start;slot.mesh.visibility=age<=40?1:Math.max(0,1-(age-40)/80);
			if(age>=120)slot.mesh.setEnabled(false);
			if(age>=400){slot.active=false;slot.particles.stop();slot.particles.reset();}
		}
		for(const slot of this.arcs)if(slot.active) {
			const t=(now-slot.start)/220;
			if(t>=1){slot.active=false;slot.mesh.setEnabled(false);continue;}
			const grow=1+t*.08;slot.mesh.scaling.set(grow,1,grow);slot.mesh.visibility=(1-t)**2;
			const sweep=Math.min(1,(now-slot.start)/90);
			for(let j=0;j<33;j++){
				const along=j/32,front=1-along,breakup=.78+.22*Math.sin(j*2.7);
				const reveal=clamp((sweep-front)*10,0,1)*breakup;
				slot.colors[j*8+3]=reveal*.28;slot.colors[j*8+7]=reveal;
			}
			slot.mesh.updateVerticesData(VertexBuffer.ColorKind,slot.colors);
		}
		this.updateTrail(now);
	}
	prewarmMeshes():readonly Mesh[] {return [this.trail,...this.warnings.flatMap(slot=>[slot.ring,slot.fill,slot.pulse]),...this.impacts.map(slot=>slot.mesh),...this.hits.map(slot=>slot.mesh),...this.arcs.map(slot=>slot.mesh)];}
	async prewarm():Promise<void>{
		const variants=new Map<StandardMaterial,Mesh>();for(const mesh of this.prewarmMeshes())if(mesh.material instanceof StandardMaterial&&!variants.has(mesh.material))variants.set(mesh.material,mesh);
		const warningMesh=this.warnings[0].ring;for(const material of this.warningMaterials.values())variants.set(material,warningMesh);
		await Promise.all([...variants].map(([material,mesh])=>material.forceCompilationAsync(mesh)));
		const deadline=performance.now()+15000;while(![...this.impacts,...this.hits].every(slot=>slot.particles.isReady())){if(this.disposed||this.scene.isDisposed)throw new Error("Combat FX disposed during prewarm");if(performance.now()>deadline)throw new Error("Combat FX particle shader prewarm timeout");await new Promise(resolve=>setTimeout(resolve,16));}
	}
	diagnostics(){return {impactCount:this.impactCount,hitCount:this.hitCount,warningOverflows:this.warningOverflows,unsupported:this.unsupported,activeWarnings:this.warnings.filter(slot=>slot.state!=="free").length,activeImpacts:this.impacts.filter(slot=>slot.active).length,trailSamples:this.trailCount,warningCapacity:WARNING_CAPACITY,lowEffects:this.lowEffects,lowDetail:this.lowDetail};}
	dispose():void {
		if(this.disposed)return;this.disposed=true;owners.delete(this.scene);
		this.scene.onBeforeRenderObservable.remove(this.observer);this.scene.onDisposeObservable.remove(this.disposeObserver);
		for(const mesh of this.prewarmMeshes())this.glow?.removeExcludedMesh(mesh);
		for(const slot of this.warnings)slot.root.dispose(false,false);
		for(const slot of this.impacts){slot.mesh.dispose(false,false);slot.particles.dispose(false);}
		for(const slot of this.hits){slot.mesh.dispose(false,false);slot.particles.dispose(false);}
		for(const slot of this.arcs)slot.mesh.dispose(false,false);
		this.trail.dispose(false,false);
		for(const material of this.materials)material.dispose(false,false);
		for(const texture of this.textures)texture.dispose();
		this.sword=null;
	}
}

/** Compatibility handle. isFinished retains the old *wind-up elapsed* meaning for offline AI.
 * update() reports the visual lease lifetime, including armed wait and cancellation fade. */
export class SplashTelegraph {
	private readonly lease: {slot:WarningSlot;generation:number}|null;
	private readonly point: {x:number;z:number};
	constructor(scene:Scene,x:number,z:number,radius=2.5,durationMs=900,private readonly owner=createCombatFx(scene),style:TelegraphStyle="amber"){
		this.point=Object.freeze({x,z});this.lease=owner.acquireWarning(x,z,radius,durationMs,style);
	}
	get target(){return this.point;}
	get progress():number {const lease=this.lease;return lease&&this.owner.isCurrent(lease.slot,lease.generation)?clamp((this.owner.now()-lease.slot.start)/lease.slot.duration,0,1):1;}
	get isFinished():boolean {const lease=this.lease;return !lease||!this.owner.isCurrent(lease.slot,lease.generation)||this.owner.now()>=lease.slot.deadline;}
	setRemainingMs(remainingMs:number):void {const lease=this.lease;if(!lease||!Number.isFinite(remainingMs)||!this.owner.isCurrent(lease.slot,lease.generation)||lease.slot.state==="fade")return;
		const slot=lease.slot,remaining=clamp(remainingMs,0,slot.duration);slot.deadline=this.owner.now()+remaining;slot.start=slot.deadline-slot.duration;slot.state=remaining>0?"warning":"armed";
	}
	impact():void {const lease=this.lease;if(lease)this.owner.confirmWarning(lease.slot,lease.generation);}
	update():boolean {const lease=this.lease;return !!lease&&this.owner.isCurrent(lease.slot,lease.generation);}
	dispose():void {const lease=this.lease;if(lease)this.owner.cancelWarning(lease.slot,lease.generation);}
}
export class SlashArc {
	constructor(scene:Scene,private readonly owner=createCombatFx(scene)){}
	play(x:number,y:number,z:number,facing:number,isArcSlash=false):void {this.owner.playSlash(x,y,z,facing,isArcSlash);}
	/** The scene/system owns shared resources; this compatibility wrapper has no private pool. */
	dispose():void {}
}
