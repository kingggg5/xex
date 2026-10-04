import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import "@babylonjs/core/Meshes/thinInstanceMesh";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { Buffer } from "@babylonjs/core/Buffers/buffer";
import { Vector2 } from "@babylonjs/core/Maths/math.vector";
import type { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import type { Scene } from "@babylonjs/core/scene";
import type { GlowLayer } from "@babylonjs/core/Layers/glowLayer";
import { createCombatTextPool, TEXT_TYPES, type CombatTextSlot } from "./combat-vfx-text-pool.mjs";
import { COMBAT_TEXT_ATTRIBUTES, createGlyphMaterial } from "./combat-vfx-glyph-shader";

export type DamageKind="player"|"monster"|"crit"|"heal"|"exp"|"counter";
export interface DamageIdentity {targetId?:number|string;sourceId?:number|string;relation?:"mine"|"party"|"other"}
export interface CombatTextPreferences {mobile?:boolean;locale?:"th"|"en";textScale?:number;showOthers?:boolean;reduceMotion?:boolean}
export interface CombatLabelOptions extends CombatTextPreferences {groundAt(x:number,z:number):number|null;now?:()=>number}
export interface EnemyHealthLabel {root:Mesh;fill:Mesh;active:boolean;setHealth(hp:number,maximum:number,active:boolean):void;dispose():void}
const WORDS={miss:["พลาด","Miss"],evade:["หลบ!","Evade"],parry:["ปัดป้อง!","Parry!"],counter:["สวนกลับ!","Counter!"],guard:["ป้องกัน","Guard"]} as const;
const POOL=48,GLYPHS=8;
const COLOURS=[[1,.957,.863],[1,.835,.29],[1,.361,.278],[.812,.89,.941],[.373,.89,.604],[.784,.714,1],[1,.957,.863],[1,.957,.863]];

/** Two thin-instance draws; glyph motion and fade run in shaders, never in a DOM/name atlas. */
export function createWorldCombatLabels(scene:Scene,_names:readonly string[]=[],options:CombatLabelOptions={groundAt:()=>0}) {
	const now=options.now??(()=>performance.now()),epoch=now(),pool=createCombatTextPool(!!options.mobile);
	let preferences:CombatTextPreferences={mobile:!!options.mobile,locale:options.locale??"en",textScale:1,showOthers:false,reduceMotion:false,...options};
	let disposed=false,fontFallback=false,dirty=false;
	const glow=scene.effectLayers?.find(layer=>layer.name==="env-glow") as GlowLayer|undefined;
	const atlas=new DynamicTexture("combat-text-coverage-atlas",{width:1024,height:1024},scene,false,Texture.BILINEAR_SAMPLINGMODE);
	atlas.hasAlpha=true;atlas.wrapU=atlas.wrapV=Texture.CLAMP_ADDRESSMODE;
	const rects=new Map<string,{uv:number[];width:number;height:number}>();
	function bake(){
		const c=atlas.getContext() as CanvasRenderingContext2D;c.clearRect(0,0,1024,1024);
		c.textAlign="center";c.textBaseline="middle";c.lineJoin="round";
		const draw=(text:string,x:number,y:number,width:number,height:number,font:number)=>{
			c.font=`700 ${font}px "Noto Sans Thai", Arial, sans-serif`;c.lineWidth=font*.048;c.strokeStyle="#00ff00";c.fillStyle="#ff0000";c.shadowColor="rgba(0,0,255,.8)";c.shadowBlur=font*.075;
			c.strokeText(text,x+width/2,y+height/2);c.shadowBlur=0;c.fillText(text,x+width/2,y+height/2);
			rects.set(text,{uv:[(x+1)/1024,1-(y+height-1)/1024,(x+width-1)/1024,1-(y+1)/1024],width:width/font,height:height/font});
		};
		"0123456789".split("").forEach((v,i)=>draw(v,i*96,0,96,128,96));
		"+KM,!×−".split("").forEach((v,i)=>draw(v,i*96,128,96,128,96));
		[...Object.values(WORDS).flat(),"EXP"].forEach((v,i)=>draw(v,(i%4)*256,256+Math.floor(i/4)*96,256,96,56));
		const bx=896,by=768;c.fillStyle="#ff0000";c.beginPath();
		for(let i=0;i<16;i++){const a=i*Math.PI/8,r=i%2?20:58,x=bx+64+Math.cos(a)*r,y=by+64+Math.sin(a)*r;if(i===0)c.moveTo(x,y);else c.lineTo(x,y);}c.closePath();c.fill();
		rects.set("burst",{uv:[bx/1024,1-(by+128)/1024,(bx+128)/1024,1-by/1024],width:2.5,height:2.5});
		atlas.update(true);for(const s of pool.slots)s.dirty=true;dirty=true;
	}
	bake();
	function layer(name:string,burst:boolean){
		const mesh=MeshBuilder.CreatePlane(name,{size:1},scene),material=createGlyphMaterial(scene,burst);
		mesh.material=material;mesh.isPickable=false;mesh.receiveShadows=false;mesh.alwaysSelectAsActiveMesh=true;mesh.metadata={glow:false,combatText:true};glow?.addExcludedMesh(mesh);
		const capacity=burst?POOL:POOL*GLYPHS,matrices=new Float32Array(capacity*16);
		for(let i=0;i<capacity;i++)matrices[i*16]=matrices[i*16+5]=matrices[i*16+10]=matrices[i*16+15]=1;
		mesh.thinInstanceSetBuffer("matrix",matrices,16,true);mesh.thinInstanceCount=capacity;
		const buffers=Object.fromEntries(COMBAT_TEXT_ATTRIBUTES.map(k=>[k,new Float32Array(capacity*4)])) as Record<typeof COMBAT_TEXT_ATTRIBUTES[number],Float32Array>;
		// Six vec4 attributes share one allocation. Separate thin-instance buffers exceed
		// WebGPU's minimum eight-buffer limit once position, UV and world matrices bind.
		const stride=COMBAT_TEXT_ATTRIBUTES.length*4,packed=new Float32Array(capacity*stride);
		const instanceBuffer=new Buffer(scene.getEngine(),packed,true,stride,false,true,false,1,`${name}-packed`);
		COMBAT_TEXT_ATTRIBUTES.forEach((key,i)=>mesh.setVerticesBuffer(instanceBuffer.createVertexBuffer(key,i*4,4,stride,true)));
		function pack(first:number,count:number){
			for(let instance=first;instance<first+count;instance++)for(let attribute=0;attribute<COMBAT_TEXT_ATTRIBUTES.length;attribute++){
				const source=buffers[COMBAT_TEXT_ATTRIBUTES[attribute]],src=instance*4,dst=instance*stride+attribute*4;
				for(let component=0;component<4;component++)packed[dst+component]=source[src+component];
			}
		}
		material.setTexture("ctAtlas",atlas);material.setFloat("ctScale",1);material.setFloat("ctReduced",0);material.setVector2("ctViewport",new Vector2(1920,1080));material.setFloat("ctNow",0);
		return {mesh,material,buffers,instanceBuffer,packed,pack};
	}
	const glyph=layer("combat-text-glyph-instances",false),burst=layer("combat-text-burst-instances",true);
	function applyInstanceBudget(){glyph.mesh.thinInstanceCount=(preferences.mobile?32:48)*GLYPHS;burst.mesh.thinInstanceCount=preferences.mobile?32:48;}
	applyInstanceBudget();
	const compatibility:EnemyHealthLabel[]=[];
	function write(s:CombatTextSlot){
		const size=(preferences.mobile?[20,26,22,17,19,16,23,14]:[26,34,28,22,24,20,30,18])[s.type];
		const entries=rects.has(s.text)?[s.text]:s.type===4?["+",...s.text.slice(0,6).split("")]:s.type===5?["+",...s.text.slice(0,5).split(""),"EXP"]:s.text.slice(0,GLYPHS).split("");
		const widths=entries.map(text=>text.length===1?.64:rects.get(text)?.width??1),total=widths.reduce((a,b)=>a+b,0);let offset=-total/2;
		for(let i=0;i<GLYPHS;i++){
			const index=(s.index*GLYPHS+i)*4,rect=rects.get(entries[i]);
			glyph.buffers.ctAnchorType.set([s.x,s.y,s.z,s.type],index);
			glyph.buffers.ctTime.set([(s.born-epoch)/1000,(s.expires-epoch)/1000,s.lane,s.side],index);
			glyph.buffers.ctGlyph.set(rect?.uv??[0,0,0,0],index);
			glyph.buffers.ctLayout.set([offset+(widths[i]??0)/2,rect?.width??0,rect?.height??0,size],index);
			glyph.buffers.ctFill.set([...COLOURS[s.type],s.active&&rect?(s.relation==="mine"?1:.6):0],index);glyph.buffers.ctLine.set(s.type===6?[1,.694,.231,(s.lastHit-epoch)/1000]:[.102,.071,.031,(s.lastHit-epoch)/1000],index);offset+=widths[i]??0;
		}
		const index=s.index*4,rect=rects.get("burst")!;
		burst.buffers.ctAnchorType.set([s.x,s.y,s.z,9],index);burst.buffers.ctTime.set([(s.lastHit-epoch)/1000,(s.lastHit-epoch)/1000+.28,s.lane,0],index);burst.buffers.ctGlyph.set(rect.uv,index);burst.buffers.ctLayout.set([0,rect.width,rect.height,size],index);burst.buffers.ctFill.set([1,.62,.11,s.active&&(s.type===1||s.type===6)&&!preferences.reduceMotion?.65:0],index);burst.buffers.ctLine.set([0,0,0,0],index);
		glyph.pack(s.index*GLYPHS,GLYPHS);burst.pack(s.index,1);s.dirty=false;
	}
	const viewport=new Vector2();
	const observer=scene.onBeforeRenderObservable.add(()=>{
		const time=now();pool.expire(time);let updated=dirty;
		for(const s of pool.slots)if(s.dirty){write(s);updated=true;}
		if(updated)for(const value of [glyph,burst])value.instanceBuffer.update(value.packed);
		dirty=false;const canvas=scene.getEngine().getRenderingCanvas();viewport.set(canvas?.clientWidth||scene.getEngine().getRenderWidth(),canvas?.clientHeight||scene.getEngine().getRenderHeight());
		for(const value of [glyph,burst]){value.material.setFloat("ctNow",(time-epoch)/1000);value.material.setVector2("ctViewport",viewport);value.material.setFloat("ctScale",Math.max(.8,Math.min(2,preferences.textScale??1)));value.material.setFloat("ctReduced",preferences.reduceMotion?1:0);}
	});
	const disposal=scene.onDisposeObservable.addOnce(()=>api.dispose());
	function spawn(x:number,z:number,type:number,amount:number,text:string|undefined,anchorY:number|undefined,identity:DamageIdentity={}){
		if(disposed||![x,z,amount].every(Number.isFinite)||identity.relation==="other"&&!preferences.showOthers)return;
		const support=options.groundAt(x,z),y=Number.isFinite(anchorY)?anchorY!:support!==null&&Number.isFinite(support)?support+1.8:null;if(y===null)return;
		if(pool.spawn({x,y,z,type,amount,text,...identity},now()))dirty=true;
	}
	const api={
		get capacity(){return pool.cap;},
		showDamage(x:number,z:number,amount:number,kind:DamageKind="monster",anchorY?:number,identity?:DamageIdentity){if(amount<=0)return;spawn(x,z,kind==="crit"?1:kind==="player"?2:kind==="heal"?4:kind==="exp"?5:kind==="counter"?6:0,amount,undefined,anchorY,identity);},
		showWord(x:number,z:number,word:keyof typeof WORDS,anchorY?:number,identity?:DamageIdentity){spawn(x,z,TEXT_TYPES.word,0,WORDS[word][preferences.locale==="th"?0:1],anchorY,identity);},
		configure(next:CombatTextPreferences){preferences={...preferences,...next};pool.setMobile(!!preferences.mobile);applyInstanceBudget();for(const s of pool.slots)s.dirty=true;dirty=true;},
		/** No geometry/text: retained while the root migrates call sites to the DOM plate bridge. */
		createEnemyLabel(parent:TransformNode,index:number):EnemyHealthLabel{const root=new Mesh(`enemy-label-anchor-${index}`,scene),fill=new Mesh(`enemy-health-contract-${index}`,scene);root.parent=parent;fill.parent=root;root.position.y=1.55;root.isPickable=fill.isPickable=false;const label:EnemyHealthLabel={root,fill,active:true,setHealth(hp,max,active){label.active=active;root.setEnabled(active);fill.scaling.x=max>0?Math.max(0,Math.min(1,hp/max)):0;},dispose(){root.dispose();const i=compatibility.indexOf(label);if(i>=0)compatibility.splice(i,1);}};compatibility.push(label);return label;},
		async prewarm(){
			if(typeof document!=="undefined"&&document.fonts){let timer:ReturnType<typeof setTimeout>|undefined;try{const result=await Promise.race([document.fonts.load('700 64px "Noto Sans Thai"'),new Promise<null>(resolve=>{timer=setTimeout(()=>resolve(null),1500);})]);fontFallback=result===null||result.length===0;if(!disposed)bake();}finally{if(timer)clearTimeout(timer);}}
			await Promise.all([glyph,burst].map(value=>value.material.forceCompilationAsync(value.mesh,{useInstances:true})));
		},
		diagnostics(){return {active:pool.active().length,capacity:pool.cap,fontFallback,glyphInstances:glyph.mesh.thinInstanceCount,drawCallsUpperBound:2,slots:pool.active().map(s=>({target:s.target,text:s.text,type:s.type,position:[s.x,s.y,s.z],born:s.born,expires:s.expires,lane:s.lane}))};},
		dispose(){if(disposed)return;disposed=true;pool.clear();scene.onBeforeRenderObservable.remove(observer);scene.onDisposeObservable.remove(disposal);for(const value of [glyph,burst]){glow?.removeExcludedMesh(value.mesh);value.mesh.dispose(false,false);value.instanceBuffer.dispose();value.material.dispose(false,false);}for(const label of compatibility)label.root.dispose();atlas.dispose();},
	};
	return api;
}
