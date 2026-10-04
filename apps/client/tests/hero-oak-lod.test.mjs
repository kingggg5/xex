import test from "node:test";
import assert from "node:assert/strict";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine.js";
import { Scene } from "@babylonjs/core/scene.js";
import { FreeCamera } from "@babylonjs/core/Cameras/freeCamera.js";
import { Vector3 } from "@babylonjs/core/Maths/math.vector.js";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder.js";
import "@babylonjs/core/Meshes/instancedMesh.js";
import { configureHeroOakLod } from "../src/hero-oak-lod.mjs";

function withLods(run) {
	const engine = new NullEngine({ renderWidth: 1280, renderHeight: 720 });
	const scene = new Scene(engine);
	try {
		const camera = new FreeCamera("test-view", new Vector3(0, 0, -60), scene);
		camera.minZ = 0.1;
		camera.fov = 0.92;
		const master = MeshBuilder.CreateBox("full", { size: 8 }, scene);
		const medium = MeshBuilder.CreateBox("medium", { size: 8 }, scene);
		const distant = MeshBuilder.CreateBox("distant", { size: 8 }, scene);
		configureHeroOakLod(master, medium, distant);
		const update = () => {
			camera.getViewMatrix(true);
			camera.getProjectionMatrix(true);
			master.computeWorldMatrix(true);
		};
		update();
		run({ camera, master, medium, distant, update });
	} finally { scene.dispose(); engine.dispose(); }
}

test("oak coverage LOD adapts to object scale rather than using a universal distance", () => withLods(({ camera, master, medium, update }) => {
	assert.equal(master.getLOD(camera), medium);
	master.scaling.setAll(3);
	update();
	assert.equal(master.getLOD(camera), master);
}));

test("a closer camera and narrower lens preserve more geometry", () => withLods(({ camera, master, medium, distant, update }) => {
	assert.equal(master.getLOD(camera), medium);
	camera.position.z = -150;
	update();
	assert.equal(master.getLOD(camera), distant);
	camera.position.z = -60;
	camera.fov = 0.5;
	update();
	assert.equal(master.getLOD(camera), master);
}));

test("oak instances inherit LOD and use their own placement bounds", () => withLods(({ camera, master, distant, update }) => {
	master.isVisible = false;
	const instance = master.createInstance("far-placement");
	instance.position.z = 200;
	instance.computeWorldMatrix(true);
	update();
	assert.equal(instance.getLOD(camera), distant);
	assert.equal(master.isVisible, false);
	assert.equal(instance.isVisible, true);
}));
