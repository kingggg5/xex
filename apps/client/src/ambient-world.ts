import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { Constants } from "@babylonjs/core/Engines/constants";
import type { InstancedMesh } from "@babylonjs/core/Meshes/instancedMesh";
import "@babylonjs/core/Meshes/instancedMesh";
import type { AbstractMesh } from "@babylonjs/core/Meshes/abstractMesh";
import type { Scene } from "@babylonjs/core/scene";
import type { GlowLayer } from "@babylonjs/core/Layers/glowLayer";
import type { ShadowGenerator } from "@babylonjs/core/Lights/Shadows/shadowGenerator";
import type { ResolvedGraphicsPreset } from "./graphics-quality.mjs";
import { skyPaletteStops } from "./sky-palette-stops.mjs";

export interface AmbientAppearance { hours:number;daylight:number;dawn:number;cloud:number;direction:readonly number[];skyPalette?:{zenith:readonly number[];horizon:readonly number[]} }
export interface AmbientOptions { cityCenterZ:number;cityBounds?:{minX:number;maxX:number;minZ:number;maxZ:number};now?:()=>number }
interface Bird { root:TransformNode;left:InstancedMesh;right:InstancedMesh;index:number }
interface Cloud { anchor:AbstractMesh;cards:InstancedMesh[];caster:InstancedMesh }
interface Obstacle { minX:number;maxX:number;minZ:number;maxZ:number;top:number }
const MAX_BIRDS=24;
const MAX_CLOUDS=16;
const SHADOW_ONLY_LAYER=0x10000000;
const owners=new WeakMap<Scene,AmbientWorld>();
const samples=new WeakMap<Scene,AmbientAppearance>();
const clamp=(value:number,lo:number,hi:number)=>Math.max(lo,Math.min(hi,value));

/** Authoritative weather sampler calls this; ambient never advances another day/night clock. */
export function updateAmbientAppearance(scene:Scene,sample:AmbientAppearance):boolean {
  samples.set(scene,sample);const owner=owners.get(scene);owner?.appearance(sample);return !!owner;
}
export function createAmbientWorld(scene:Scene,options:AmbientOptions):AmbientWorld {
  const existing=owners.get(scene);if(existing)return existing;
  const world=new AmbientWorld(scene,options);owners.set(scene,world);
  const sample=samples.get(scene);if(sample)world.appearance(sample);return world;
}
export class AmbientWorld {
  private disposed=false;
  private readonly clock:()=>number;
  private readonly started:number;
  private readonly glow:GlowLayer|undefined;
  private readonly materials:StandardMaterial[]=[];
  private readonly textures:DynamicTexture[]=[];
  private readonly masters:Mesh[]=[];
  private readonly legacy:Array<{mesh:AbstractMesh;visible:boolean}>=[];
  private readonly clouds:Cloud[]=[];
  private readonly cirrus:InstancedMesh[]=[];
  private readonly birds:Bird[]=[];
  private readonly obstacles:Obstacle[]=[];
  private readonly cloudMaterial:StandardMaterial;
  private readonly sun:Mesh;
  private readonly sky:DynamicTexture|undefined;
  private readonly originalSky:ImageData|undefined;
  private skyKey="";
  private birdBudget=12;
  private cloudBudget=16;
  private layerBudget=3;
  private daylight=1;
  private cloudCover=.15;
  private lastScan=-Infinity;
  private rescan=true;
  private highestCity=45;
  private highestObstacle=45;
  private obstacleOverflow=false;
  private readonly warmHorizon=Color3.FromHexString("#edc7a3");
  private readonly duskHorizon=Color3.FromHexString("#c797b4");
  private readonly middayHorizon=Color3.FromHexString("#cce4ec");
  private readonly nightHorizon=Color3.FromHexString("#253751");
  private readonly middayZenith=Color3.FromHexString("#427dc0");
  private readonly duskZenith=Color3.FromHexString("#424a79");
  private readonly nightZenith=Color3.FromHexString("#0c1730");
  private readonly horizon=new Color3();
  private readonly zenith=new Color3();
  private readonly tint=new Color3();
  private readonly observer;
  private readonly meshObserver;
  private readonly disposeObserver;

  constructor(private readonly scene:Scene,private readonly options:AmbientOptions) {
    this.clock=options.now??(()=>performance.now());this.started=this.clock();
    this.glow=scene.effectLayers?.find(layer=>layer.name==="env-glow") as GlowLayer|undefined;
    this.sky=scene.textures.find(texture=>texture.name==="env-sky-texture"&&texture instanceof DynamicTexture) as DynamicTexture|undefined;
    const context=this.sky?.getContext() as CanvasRenderingContext2D|undefined;
    this.originalSky=context?.getImageData?.(0,0,16,256);
    const cloudTexture=this.cloudMask();
    this.cloudMaterial=this.material("ambient-cloud-sprites",cloudTexture);
    // StandardMaterial ADDS emissiveTexture RGB to emissiveColor. For clouds the painted
    // diffuse RGB must instead be modulated by the shared day/night tint; keep its soft alpha.
    this.cloudMaterial.emissiveTexture=null;
    this.cloudMaterial.transparencyMode=StandardMaterial.MATERIAL_ALPHABLEND;
    this.cloudMaterial.emissiveColor.set(.14,.19,.26); // linear tint; leave headroom for the shared ACES night grade
    const castMaterial=this.material("ambient-cloud-shadow-mask",cloudTexture);
    castMaterial.transparencyMode=StandardMaterial.MATERIAL_ALPHATEST;
    castMaterial.disableDepthWrite=false;
    const layers=Array.from({length:3},(_,layer)=>{const master=MeshBuilder.CreatePlane("ambient-cloud-master-"+layer,{size:1},scene);master.material=this.cloudMaterial;master.billboardMode=Mesh.BILLBOARDMODE_ALL;master.visibility=layer===0?.72:layer===1?.54:.34;master.isVisible=false;return master;});
    const cirrusMaster=MeshBuilder.CreatePlane("ambient-cirrus-master",{size:1},scene);cirrusMaster.material=this.cloudMaterial;cirrusMaster.billboardMode=Mesh.BILLBOARDMODE_ALL;cirrusMaster.visibility=.14;cirrusMaster.isVisible=false;
    const caster=MeshBuilder.CreateGround("ambient-cloud-shadow-master",{width:1,height:1},scene);caster.material=castMaterial;caster.isVisible=false;caster.layerMask=SHADOW_ONLY_LAYER;
    this.masters.push(...layers,cirrusMaster,caster);
    const groups=new Map<number,AbstractMesh[]>();
    for(const mesh of scene.meshes){const match=/^env-cloud-(\d+)-\d+$/.exec(mesh.name);if(!match)continue;
      this.legacy.push({mesh,visible:mesh.isVisible});mesh.isVisible=false;
      const id=Number(match[1]);const group=groups.get(id)??[];group.push(mesh);groups.set(id,group);
    }
    for(const [id,puffs] of groups){if(this.clouds.length>=MAX_CLOUDS)break;
      const anchor=puffs[Math.floor(puffs.length/2)];const cards:InstancedMesh[]=[];
      for(let layer=0;layer<3;layer++){const instance=layers[layer].createInstance("ambient-cloud-"+id+"-"+layer);instance.billboardMode=Mesh.BILLBOARDMODE_ALL;instance.isPickable=false;instance.scaling.set(25-layer*4,12-layer*2,1);cards.push(instance);}
      const shadow=caster.createInstance("ambient-cloud-shadow-"+id);shadow.layerMask=SHADOW_ONLY_LAYER;shadow.scaling.set(22,1,13);shadow.isPickable=false;
      this.clouds.push({anchor,cards,caster:shadow});
    }
    for(let i=0;i<4;i++){const plane=cirrusMaster.createInstance("ambient-cirrus-"+i);plane.scaling.set(135,10,1);plane.billboardMode=Mesh.BILLBOARDMODE_ALL;plane.isPickable=false;this.cirrus.push(plane);}
    const sunTexture=this.radialMask("ambient-sun-mask");const sunMaterial=this.material("ambient-sun-glow",sunTexture);sunMaterial.alphaMode=Constants.ALPHA_ADD;sunMaterial.fogEnabled=false;sunMaterial.emissiveColor.set(.88,.71,.48);
    this.sun=MeshBuilder.CreatePlane("ambient-sun-glow-billboard",{size:160},scene);this.sun.material=sunMaterial;this.sun.billboardMode=Mesh.BILLBOARDMODE_ALL;this.sun.isPickable=false;this.glow?.addExcludedMesh(this.sun);
    this.sun.setEnabled(false);
    const birdMaterial=new StandardMaterial("ambient-bird-material",scene);birdMaterial.diffuseColor.set(.18,.23,.29);birdMaterial.specularColor.set(0,0,0);birdMaterial.backFaceCulling=false;this.materials.push(birdMaterial);
    const body=MeshBuilder.CreateSphere("ambient-bird-body-master",{diameter:.22,segments:4},scene);body.scaling.set(.7,.6,2.2);body.material=birdMaterial;body.isVisible=false;
    const wing=MeshBuilder.CreateRibbon("ambient-bird-wing-master",{pathArray:[[new Vector3(0,0,-.18),new Vector3(0,0,.22)],[new Vector3(.68,0,-.32),new Vector3(.68,0,-.32)]]},scene);wing.material=birdMaterial;wing.isVisible=false;this.masters.push(body,wing);
    for(let i=0;i<MAX_BIRDS;i++){
      const root=new TransformNode("ambient-bird-"+i,scene);root.scaling.setAll(1.2);
      const torso=body.createInstance("ambient-bird-body-"+i);torso.parent=root;torso.isPickable=false;
      const left=wing.createInstance("ambient-bird-left-"+i);left.parent=root;left.scaling.x=-1;left.isPickable=false;
      const right=wing.createInstance("ambient-bird-right-"+i);right.parent=root;right.isPickable=false;
      this.birds.push({root,left,right,index:i});root.setEnabled(false);
    }
    for(const master of this.masters){master.isPickable=false;master.checkCollisions=false;this.glow?.addExcludedMesh(master);}
    this.observer=scene.onBeforeRenderObservable.add(()=>this.tick());
    this.meshObserver=scene.onNewMeshAddedObservable.add(()=>{this.rescan=true;});
    this.disposeObserver=scene.onDisposeObservable.addOnce(()=>this.dispose());
  }
  private material(name:string,texture:DynamicTexture):StandardMaterial {
    const material=new StandardMaterial(name,this.scene);material.disableLighting=true;material.diffuseColor.set(0,0,0);material.emissiveColor.set(1,1,1);
    material.diffuseTexture=texture;material.emissiveTexture=texture;material.useAlphaFromDiffuseTexture=true;material.backFaceCulling=false;material.disableDepthWrite=true;material.specularColor.set(0,0,0);
    this.materials.push(material);return material;
  }
  private cloudMask():DynamicTexture {
    const texture=new DynamicTexture("ambient-cloud-mask",{width:256,height:128},this.scene,false,Texture.BILINEAR_SAMPLINGMODE);texture.hasAlpha=true;texture.wrapU=texture.wrapV=Texture.CLAMP_ADDRESSMODE;
    const c=texture.getContext() as CanvasRenderingContext2D;c.clearRect(0,0,256,128);
    // Overlapping soft lobes, shaded at their bases. Painted once, no per-frame noise generation.
    for(let i=0;i<18;i++){
      const x=35+(i*37%186),y=45+(i*19%42),r=17+(i*11%22);
      const gradient=c.createRadialGradient(x,y,r*.12,x,y,r);
      const shade=Math.round(232-(y-40)*1.8);gradient.addColorStop(0,"rgba("+shade+","+(shade+5)+","+Math.min(255,shade+15)+",.55)");gradient.addColorStop(.65,"rgba("+shade+","+(shade+5)+","+Math.min(255,shade+15)+",.22)");gradient.addColorStop(1,"rgba(180,204,230,0)");
      c.fillStyle=gradient;c.fillRect(x-r,y-r,r*2,r*2);
    }
    texture.update(false);this.textures.push(texture);return texture;
  }
  private radialMask(name:string):DynamicTexture {
    const texture=new DynamicTexture(name,{width:128,height:128},this.scene,false,Texture.BILINEAR_SAMPLINGMODE);texture.hasAlpha=true;
    const c=texture.getContext() as CanvasRenderingContext2D,g=c.createRadialGradient(64,64,0,64,64,62);
    g.addColorStop(0,"rgba(255,255,255,.74)");g.addColorStop(.18,"rgba(255,244,222,.30)");g.addColorStop(1,"rgba(255,232,199,0)");c.fillStyle=g;c.fillRect(0,0,128,128);texture.update(false);this.textures.push(texture);return texture;
  }
  appearance(sample:AmbientAppearance):void {
    if(this.disposed)return;this.daylight=clamp(sample.daylight,0,1);this.cloudCover=clamp(sample.cloud,0,1);
    const dawn=clamp(sample.dawn,0,1),day=this.daylight;
    Color3.LerpToRef(this.nightZenith,this.middayZenith,day,this.zenith);
    Color3.LerpToRef(this.zenith,this.duskZenith,dawn*.45,this.zenith);
    Color3.LerpToRef(this.nightHorizon,this.middayHorizon,day,this.horizon);
    Color3.LerpToRef(this.horizon,sample.hours<12?this.warmHorizon:this.duskHorizon,dawn*.8,this.horizon);
    if(sample.skyPalette){this.zenith.set(...sample.skyPalette.zenith as [number,number,number]);this.horizon.set(...sample.skyPalette.horizon as [number,number,number]);}
    const key=Math.floor(sample.hours*6)+":"+Math.round(this.cloudCover*10)+":"+(sample.skyPalette?`v2:${this.zenith.toHexString()}:${this.horizon.toHexString()}`:'v1');
    if(this.sky&&key!==this.skyKey){this.skyKey=key;const c=this.sky.getContext() as CanvasRenderingContext2D,size=this.sky.getSize();
      const gradient=c.createLinearGradient(0,0,0,size.height);
      if(sample.skyPalette){
        for(const stop of skyPaletteStops(sample.skyPalette.zenith,sample.skyPalette.horizon))gradient.addColorStop(stop.offset,new Color3(stop.color[0],stop.color[1],stop.color[2]).toHexString());
      }else{
        gradient.addColorStop(0,this.zenith.toHexString());gradient.addColorStop(.48,this.zenith.toHexString());gradient.addColorStop(.76,this.horizon.toHexString());gradient.addColorStop(1,this.horizon.toHexString());
      }
      c.fillStyle=gradient;c.fillRect(0,0,size.width,size.height);this.sky.update(false);
    }
    this.tint.set(.14+day*.75,.19+day*.73,.26+day*.68);this.cloudMaterial.emissiveColor.copyFrom(this.tint);
    this.cloudMaterial.alpha=.38+this.cloudCover*.36;
    const camera=this.scene.activeCamera?.position;
    this.sun.position.set((camera?.x??0)-sample.direction[0]*900,(camera?.y??0)-sample.direction[1]*900,(camera?.z??0)-sample.direction[2]*900);
    this.sun.visibility=day*(1-this.cloudCover*.86)*.55;this.sun.setEnabled(day>.02);
  }
  setQuality(profile:ResolvedGraphicsPreset):void {
    this.birdBudget=profile.formFactor==="mobile"||profile.preset==="low"?6:profile.preset==="ultra"?24:profile.preset==="high"?18:12;
    this.cloudBudget=profile.preset==="low"?8:16;this.layerBudget=profile.formFactor==="mobile"||profile.preset==="low"?2:3;
  }
  private scanObstacles():void {
    this.obstacles.length=0;this.highestCity=45;this.highestObstacle=45;this.obstacleOverflow=false;
    const bounds=this.options.cityBounds;
    for(const mesh of this.scene.meshes){
      if(!mesh.isEnabled()||!mesh.isVisible||/ambient-|env-cloud|sky|mountain|border|tree|foliage|leaf|grass|terrain|combat-|hero|slime|enemy-|damage-|drop-/i.test(mesh.name))continue;
      mesh.computeWorldMatrix(true);const box=mesh.getBoundingInfo().boundingBox,top=box.maximumWorld.y;
      if(top<18||top>300)continue;
      const min=box.minimumWorld,max=box.maximumWorld;
      this.highestObstacle=Math.max(this.highestObstacle,top);
      if(this.obstacles.length<512)this.obstacles.push({minX:min.x,maxX:max.x,minZ:min.z,maxZ:max.z,top});
      else this.obstacleOverflow=true;
      if(bounds&&max.x>=bounds.minX&&min.x<=bounds.maxX&&max.z>=bounds.minZ&&min.z<=bounds.maxZ)this.highestCity=Math.max(this.highestCity,top);
    }
    this.rescan=false;
  }
  private shadowCasters():void {
    for(const light of this.scene.lights){const generator=light.getShadowGenerator() as ShadowGenerator|null;const list=generator?.getShadowMap()?.renderList;if(!generator||!list||!this.legacy.some(item=>list.includes(item.mesh)))continue;
      for(const cloud of this.clouds)if(!list.includes(cloud.caster))generator.addShadowCaster(cloud.caster,false);
    }
  }
  private tick():void {
    if(this.disposed)return;const now=this.clock(),time=(now-this.started)/1000;
    if(this.rescan||now-this.lastScan>2000){this.lastScan=now;this.scanObstacles();this.shadowCasters();}
    for(let i=0;i<this.clouds.length;i++){const cloud=this.clouds[i],active=i<this.cloudBudget;
      for(let layer=0;layer<cloud.cards.length;layer++){const card=cloud.cards[layer];card.setEnabled(active&&layer<this.layerBudget);card.position.set(cloud.anchor.position.x+(layer-1)*6,cloud.anchor.position.y+layer*1.4,cloud.anchor.position.z+(layer-1)*2);}
      cloud.caster.setEnabled(active);cloud.caster.position.copyFrom(cloud.anchor.position);
    }
    for(let i=0;i<this.cirrus.length;i++){const card=this.cirrus[i];card.position.set(-220+i*145+Math.sin(time*.008+i)*35,105+i*9,60-i*75);card.setEnabled(this.cloudBudget>8&&this.daylight>.05);}
    const camera=this.scene.activeCamera?.position;
    for(const bird of this.birds){const i=bird.index;if(i>=this.birdBudget||this.daylight<.2){bird.root.setEnabled(false);continue;}
      const city=i%2===0,member=Math.floor(i/2),flock=Math.floor(member/3),formation=member%3;
      const angle=time*(city?.07:.09)+flock*1.8+formation*.07,radius=(city?38:42)+formation*2+flock*3;
      const cx=city?0:-20,cz=city?this.options.cityCenterZ:-120;
      const x=cx+Math.cos(angle)*radius,z=cz+Math.sin(angle)*radius;
      let y=(city?this.highestCity+35:48)+Math.sin(time*.6+i)*3;
      if(this.obstacleOverflow)y=Math.max(y,this.highestObstacle+28);
      for(const box of this.obstacles)if(x>box.minX-4&&x<box.maxX+4&&z>box.minZ-4&&z<box.maxZ+4)y=Math.max(y,box.top+28);
      bird.root.position.set(x,y,z);bird.root.rotation.y=Math.atan2(-Math.sin(angle),Math.cos(angle));
      const flap=Math.sin(time*8+i*1.7)*.66;bird.left.rotation.z=-flap;bird.right.rotation.z=flap;
      bird.root.setEnabled(!camera||(x-camera.x)**2+(y-camera.y)**2+(z-camera.z)**2>12**2);
    }
  }
  diagnostics(){return {birdBudget:this.birdBudget,activeBirds:this.birds.filter(bird=>bird.root.isEnabled()).length,cloudGroups:this.clouds.length,visibleCards:this.clouds.reduce((n,cloud)=>n+cloud.cards.filter(card=>card.isEnabled()).length,0),legacyBallsVisible:this.legacy.filter(item=>item.mesh.isVisible).length,obstacleCount:this.obstacles.length,obstacleOverflow:this.obstacleOverflow,highestCity:this.highestCity,skyKey:this.skyKey};}
  prewarmMeshes():readonly Mesh[]{return [this.sun,...this.masters];}
  dispose():void {
    if(this.disposed)return;this.disposed=true;owners.delete(this.scene);samples.delete(this.scene);
    this.scene.onBeforeRenderObservable.remove(this.observer);this.scene.onNewMeshAddedObservable.remove(this.meshObserver);this.scene.onDisposeObservable.remove(this.disposeObserver);
    for(const mesh of this.prewarmMeshes())this.glow?.removeExcludedMesh(mesh);
    for(const light of this.scene.lights){const generator=light.getShadowGenerator() as ShadowGenerator|null;if(generator?.getShadowMap())for(const cloud of this.clouds)generator.removeShadowCaster(cloud.caster,false);}
    for(const item of this.legacy)if(!item.mesh.isDisposed())item.mesh.isVisible=item.visible;
    if(this.sky&&this.originalSky){const c=this.sky.getContext() as CanvasRenderingContext2D;c.putImageData(this.originalSky,0,0);this.sky.update(false);}
    for(const cloud of this.clouds){for(const card of cloud.cards)card.dispose(false,false);cloud.caster.dispose(false,false);}
    for(const card of this.cirrus)card.dispose(false,false);
    for(const bird of this.birds)bird.root.dispose(false,false);
    this.sun.dispose(false,false);for(const master of this.masters)master.dispose(false,false);
    for(const material of this.materials)material.dispose(false,false);for(const texture of this.textures)texture.dispose();
  }
}
