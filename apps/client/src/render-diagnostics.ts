import { SceneInstrumentation } from "@babylonjs/core/Instrumentation/sceneInstrumentation";
import { EngineInstrumentation } from "@babylonjs/core/Instrumentation/engineInstrumentation";
import "@babylonjs/core/Engines/Extensions/engine.query";
import "@babylonjs/core/Engines/AbstractEngine/abstractEngine.timeQuery";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import type { Scene } from "@babylonjs/core/scene";

/** Opt-in development counters; CPU submission time is never labelled GPU time. */
export function installRenderDiagnostics(scene: Scene): void {
	const metrics = new SceneInstrumentation(scene);
	metrics.captureFrameTime = true;
	metrics.captureRenderTime = true;
	metrics.captureActiveMeshesEvaluationTime = true;
	metrics.captureRenderTargetsRenderTime = true;
	const engineMetrics = new EngineInstrumentation(scene.getEngine());
	const engine = scene.getEngine();
	let gpuSupported = Boolean(engine.getCaps().timerQuery)
		&& typeof engine.captureGPUFrameTime === "function"
		&& typeof engine.getGPUFrameTimeCounter === "function";
	if (gpuSupported) {
		try { engineMetrics.captureGPUFrameTime = true; }
		catch { gpuSupported = false; }
	}
	const panel = document.createElement("pre");
	panel.id = "render-diagnostics";
	panel.style.cssText = "position:fixed;left:8px;bottom:10px;z-index:1010;background:#101b22e8;color:#e6f1dc;padding:8px;font:11px monospace;pointer-events:none;max-width:360px";
	document.body.append(panel);
	const interval: number[] = [];
	const cpu: number[] = [];
	const targets: number[] = [];
	let previous = 0;
	let frames = 0;
	let published = 0;
	const summary = (samples: number[]) => {
		const sorted = [...samples].sort((a, b) => a - b);
		return { n: sorted.length,
			p50: sorted[Math.floor(sorted.length * 0.5)] ?? null,
			p95: sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))] ?? null };
	};
	const observer = scene.onAfterRenderObservable.add(() => {
		const now = performance.now();
		frames++;
		if (previous && frames > 30 && document.visibilityState === "visible") {
			interval.push(now - previous);
			cpu.push(metrics.frameTimeCounter.current);
			targets.push(metrics.renderTargetsRenderTimeCounter.current);
			if (interval.length > 600) { interval.shift(); cpu.shift(); targets.shift(); }
		}
		previous = now;
		if (now - published < 1000) return;
		published = now;
		const engine = scene.getEngine();
		const snapshot = {
			backend: engine.isWebGPU ? "WebGPU" : "WebGL2", frames, visibility: document.visibilityState, focused: document.hasFocus(),
			camera_position: scene.activeCamera?.position.asArray(), camera_view: scene.activeCamera?.getViewMatrix().asArray(),
			width: engine.getRenderWidth(), height: engine.getRenderHeight(), device_pixel_ratio: devicePixelRatio,
			frame_interval_ms: summary(interval), cpu_scene_ms: summary(cpu), cpu_targets_ms: summary(targets),
			cpu_draw_submission_ms: metrics.renderTimeCounter.current,
			cpu_active_meshes_ms: metrics.activeMeshesEvaluationTimeCounter.current,
			draw_calls: metrics.drawCallsCounter.current, active_meshes: scene.getActiveMeshes().length,
			rendered_indices: scene.getActiveIndices(), scene_meshes: scene.meshes.length,
			textures: scene.textures.length, materials: scene.materials.length,
			cell_ground_bounds: scene.meshes.filter(mesh => mesh.name.startsWith("Cell ") && mesh.name.includes("grass_ground"))
				.map(mesh => ({ name: mesh.name,
					min: mesh.getBoundingInfo().boundingBox.minimumWorld.asArray(),
					max: mesh.getBoundingInfo().boundingBox.maximumWorld.asArray() })),
			cell_solids: scene.meshes.filter((mesh): mesh is Mesh => mesh instanceof Mesh && mesh.name.startsWith("Cell ") && /stone_foundation|metal_iron|magic_blue/.test(mesh.name))
				.map(mesh => ({ name: mesh.name, visible: mesh.isVisible, side: mesh.sideOrientation,
					material: mesh.material?.name, material_alpha: mesh.material?.alpha,
					back_face_culling: mesh.material?.backFaceCulling,
					material_side: mesh.material?.sideOrientation,
					enabled: mesh.isEnabled(), vertices: mesh.getTotalVertices(), indices: mesh.getTotalIndices(),
					determinant: mesh.getWorldMatrix().determinant(),
					min: mesh.getBoundingInfo().boundingBox.minimumWorld.asArray(),
					max: mesh.getBoundingInfo().boundingBox.maximumWorld.asArray() })),
			gpu_ms: gpuSupported && engineMetrics.gpuFrameTimeCounter.current > 0
				? engineMetrics.gpuFrameTimeCounter.current / 1_000_000 : null,
			gpu_reason: gpuSupported ? "Backend timestamp query; asynchronous last available frame." : "Timestamp queries unavailable on this backend/device.",
			interval_over_50ms: interval.filter(value => value > 50).length,
		};
		panel.dataset.metrics = JSON.stringify(snapshot);
		panel.textContent = `${snapshot.backend} · ${snapshot.width}×${snapshot.height}\n`
			+ `visible ${snapshot.active_meshes}/${snapshot.scene_meshes} · draws ${snapshot.draw_calls}\n`
			+ `frame p50 ${snapshot.frame_interval_ms.p50?.toFixed(1) ?? "warming"} ms\n`
			+ `CPU scene p50 ${snapshot.cpu_scene_ms.p50?.toFixed(1) ?? "warming"} ms\n`
			+ `CPU targets ${snapshot.cpu_targets_ms.p50?.toFixed(1) ?? "warming"} ms · GPU ${snapshot.gpu_ms?.toFixed(1) ?? "n/a"}`;
	});
	scene.onDisposeObservable.addOnce(() => {
		scene.onAfterRenderObservable.remove(observer);
		metrics.dispose();
		engineMetrics.dispose();
		panel.remove();
	});
}
