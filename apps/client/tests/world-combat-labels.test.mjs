import test from "node:test";
import assert from "node:assert/strict";
import {build} from "esbuild";
import {fileURLToPath} from "node:url";

const bundled = await build({stdin:{contents:`
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { Scene } from "@babylonjs/core/scene";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import { createWorldCombatLabels } from "./src/world-combat-labels";
export { NullEngine, Scene, TransformNode, createWorldCombatLabels };`,resolveDir:fileURLToPath(new URL("..",import.meta.url)),loader:"ts"},bundle:true,platform:"node",format:"esm",write:false,logLevel:"silent"});
const {NullEngine,Scene,TransformNode,createWorldCombatLabels} = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString("base64")}`);

test("combat bursts reuse a bounded mesh/material pool, expire and release scene resources", async () => {
	const oldCanvas = globalThis.OffscreenCanvas, oldPerformance = globalThis.performance;
	let now = 100;
	globalThis.OffscreenCanvas = class {
		constructor(width,height){this.width=width;this.height=height;}
		getContext(){return {clearRect(){},strokeText(){},fillText(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},fill(){}};}
	};
	Object.defineProperty(globalThis,"performance",{configurable:true,value:{now:()=>now}});
	const engine=new NullEngine(), scene=new Scene(engine);
	try {
		const root=new TransformNode("enemy",scene);
		const labels=createWorldCombatLabels(scene,["Puddlekin"]);
		const bar=labels.createEnemyLabel(root,0);
		bar.setHealth(0,100,false); assert.equal(bar.root.isEnabled(),false);
		bar.setHealth(30,100,true); assert.equal(bar.fill.scaling.x,.3);
		const meshes=scene.meshes.length, materials=scene.materials.length, textures=scene.textures.length;
		for(let i=0;i<1000;i++){now++;labels.showDamage(i%4,0,42,i%2?"player":"crit");}
		assert.equal(scene.meshes.length,meshes);
		assert.equal(scene.materials.length,materials);
		assert.equal(scene.textures.length,textures);
		assert.ok(labels.diagnostics().active<=32);
		assert.equal(scene.meshes.filter(mesh=>mesh.name.startsWith("combat-text-")).length,2);
		assert.ok(scene.meshes.filter(mesh=>mesh.name.startsWith("combat-text-")).every(mesh=>mesh.hasThinInstances));
		assert.equal(scene.textures.some(texture=>texture.name==='enemy-name-atlas'),false);
		labels.configure({mobile:true,locale:'th'});assert.ok(labels.diagnostics().active<=20);assert.equal(labels.diagnostics().glyphInstances,256);
		labels.showWord(0,0,'parry',3,{targetId:'local'});assert.equal(labels.diagnostics().slots.at(-1).text,'ปัดป้อง!');
		now+=1300; scene.onBeforeRenderObservable.notifyObservers(scene);
		assert.equal(labels.diagnostics().active,0);
		labels.dispose();labels.dispose();
		// Babylon defers observer removal to the next event-loop turn.
		await new Promise(resolve=>setTimeout(resolve,0));
		assert.equal(scene.meshes.length,0);
		assert.equal(scene.materials.length,0);
		assert.equal(scene.textures.length,0);
		assert.equal(scene.onBeforeRenderObservable.observers.length,0);
	} finally { scene.dispose();engine.dispose();globalThis.OffscreenCanvas=oldCanvas;Object.defineProperty(globalThis,"performance",{configurable:true,value:oldPerformance}); }
});
