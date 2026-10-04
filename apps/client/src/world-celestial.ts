import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { VertexData } from "@babylonjs/core/Meshes/mesh.vertexData";
import type { Scene } from "@babylonjs/core/scene";

export interface CelestialSkySample {
	hours: number;
	daylight: number;
	cloud: number;
}

export interface CelestialSky {
	update(sample: CelestialSkySample): void;
	dispose(): void;
}

const STAR_COUNT = 64;
const STAR_SHELL_RADIUS = 850;
const MOON_ORBIT_RADIUS = 900;

/** Build small, scene-owned night accents; caller supplies the WorldWeather sample. */
export function createCelestialSky(scene: Scene): CelestialSky {
	const moonTexture = createMoonCraterTexture(scene);
	const moonMaterial = new StandardMaterial("world-celestial-moon-material", scene);
	moonMaterial.diffuseTexture = moonTexture;
	moonMaterial.diffuseColor.set(0.82, 0.87, 0.98);
	moonMaterial.emissiveColor.set(0.035, 0.045, 0.075);
	moonMaterial.specularColor.set(0.02, 0.02, 0.025);
	moonMaterial.disableLighting = true;
	moonMaterial.fogEnabled = false;

	const moon = MeshBuilder.CreateSphere("world-celestial-moon", {
		diameter: 28,
		segments: 20,
	}, scene);
	moon.material = moonMaterial;
	moon.isPickable = false;
	moon.checkCollisions = false;
	moon.receiveShadows = false;
	moon.visibility = 0;

	const stars = createStarMesh(scene);
	const starTexture = new DynamicTexture("world-celestial-star-mask", { width: 64, height: 64 }, scene, false, Texture.BILINEAR_SAMPLINGMODE);
	starTexture.hasAlpha = true;
	const starContext = starTexture.getContext() as CanvasRenderingContext2D;
	const starGlow = starContext.createRadialGradient(32, 32, 0, 32, 32, 30);
	starGlow.addColorStop(0, "rgba(255,255,255,1)");
	starGlow.addColorStop(.14, "rgba(239,245,255,.7)");
	starGlow.addColorStop(1, "rgba(227,240,255,0)");
	starContext.fillStyle = starGlow; starContext.fillRect(0, 0, 64, 64); starTexture.update(false);
	const starMaterial = new StandardMaterial("world-celestial-stars-material", scene);
	starMaterial.diffuseTexture = starTexture;
	starMaterial.emissiveTexture = starTexture;
	starMaterial.useAlphaFromDiffuseTexture = true;
	starMaterial.disableDepthWrite = true;
	starMaterial.diffuseColor.set(0.60, 0.72, 0.98);
	starMaterial.emissiveColor.set(0.19, 0.25, 0.42);
	starMaterial.specularColor.set(0, 0, 0);
	starMaterial.disableLighting = true;
	starMaterial.backFaceCulling = false;
	starMaterial.fogEnabled = false;
	stars.material = starMaterial;
	stars.isPickable = false;
	stars.checkCollisions = false;
	stars.receiveShadows = false;
	stars.visibility = 0;

	const origin = Vector3.Zero();
	let disposed = false;
	const dispose = () => {
		if (disposed) return;
		disposed = true;
		moon.dispose(false, false);
		stars.dispose(false, false);
		moonMaterial.dispose(false, false);
		starMaterial.dispose(false, false);
		moonTexture.dispose();
		starTexture.dispose();
	};
	scene.onDisposeObservable.addOnce(dispose);

	return {
		update(sample) {
			if (disposed) return;
			const daylight = clamp01(sample.daylight);
			const cloud = clamp01(sample.cloud);
			const night = 1 - daylight;
			const cloudFade = 1 - cloud * 0.92;
			const hours = ((Number.isFinite(sample.hours) ? sample.hours : 0) % 24 + 24) % 24;
			const phase = hours * Math.PI / 12;
			const moonAltitude = Math.cos(phase);
			const moonRise = smoothstep(0.02, 0.28, moonAltitude);
			const moonFade = night * cloudFade * moonRise;

			moon.position.set(
				Math.sin(phase) * MOON_ORBIT_RADIUS,
				moonAltitude * MOON_ORBIT_RADIUS,
				0,
			);
			moon.lookAt(origin);
			moon.visibility = moonFade;
			moonMaterial.emissiveColor.set(0.035 * moonFade, 0.045 * moonFade, 0.075 * moonFade);
			stars.visibility = night * cloudFade;
		},
		dispose,
	};
}

function createMoonCraterTexture(scene: Scene): DynamicTexture {
	const size = 256;
	const canvas = document.createElement("canvas");
	canvas.width = size;
	canvas.height = size;
	const texture = new DynamicTexture(
		"world-celestial-moon-albedo",
		canvas,
		scene,
		false,
		Texture.BILINEAR_SAMPLINGMODE,
	);
	const context = texture.getContext() as CanvasRenderingContext2D;
	context.fillStyle = "#b2b7c0";
	context.fillRect(0, 0, size, size);

	let seed = 0x584558;
	const random = () => {
		seed = (seed * 1664525 + 1013904223) >>> 0;
		return seed / 0x1_0000_0000;
	};
	for (let i = 0; i < 24; i++) {
		const radius = 5 + random() * 15;
		const x = 14 + random() * (size - 28);
		const y = 14 + random() * (size - 28);
		context.beginPath();
		context.arc(x, y, radius, 0, Math.PI * 2);
		context.fillStyle = `rgba(75, 82, 94, ${0.08 + random() * 0.12})`;
		context.fill();
		context.beginPath();
		context.arc(x, y, radius * (0.58 + random() * 0.14), 0, Math.PI * 2);
		context.strokeStyle = `rgba(221, 225, 232, ${0.10 + random() * 0.10})`;
		context.lineWidth = 1 + random() * 1.5;
		context.stroke();
	}
	for (let i = 0; i < 1100; i++) {
		const shade = random() < 0.5 ? 104 : 221;
		context.fillStyle = `rgba(${shade}, ${shade + 2}, ${shade + 5}, ${0.04 + random() * 0.08})`;
		const x = Math.floor(random() * size);
		const y = Math.floor(random() * size);
		context.fillRect(x, y, 1, 1);
	}
	texture.update(false);
	texture.wrapU = Texture.WRAP_ADDRESSMODE;
	texture.wrapV = Texture.CLAMP_ADDRESSMODE;
	return texture;
}

function createStarMesh(scene: Scene): Mesh {
	const positions: number[] = [];
	const normals: number[] = [];
	const uvs: number[] = [];
	const indices: number[] = [];
	const goldenAngle = Math.PI * (3 - Math.sqrt(5));
	let seed = 0x584558;
	const random = () => {
		seed = (seed * 1664525 + 1013904223) >>> 0;
		return seed / 0x1_0000_0000;
	};

	for (let i = 0; i < STAR_COUNT; i++) {
		const altitude = (i + 0.5) / STAR_COUNT;
		const azimuth = i * goldenAngle;
		const horizontal = Math.sqrt(1 - altitude * altitude);
		const dx = Math.cos(azimuth) * horizontal;
		const dy = altitude;
		const dz = Math.sin(azimuth) * horizontal;
		const radius = STAR_SHELL_RADIUS + (random() - 0.5) * 12;
		const centerX = dx * radius;
		const centerY = dy * radius;
		const centerZ = dz * radius;

		const helperX = 0;
		const helperY = Math.abs(dy) > 0.92 ? 0 : 1;
		const helperZ = Math.abs(dy) > 0.92 ? 1 : 0;
		let rightX = helperY * dz - helperZ * dy;
		let rightY = helperZ * dx - helperX * dz;
		let rightZ = helperX * dy - helperY * dx;
		const rightLength = Math.hypot(rightX, rightY, rightZ) || 1;
		rightX /= rightLength;
		rightY /= rightLength;
		rightZ /= rightLength;
		const upX = dy * rightZ - dz * rightY;
		const upY = dz * rightX - dx * rightZ;
		const upZ = dx * rightY - dy * rightX;
		const halfSize = 1.2 + random() * 1.6;
		const corners: Array<[number, number]> = [
			[-1, -1], [1, -1], [1, 1], [-1, 1],
		];
		const first = positions.length / 3;
		for (const [sx, sy] of corners) {
			positions.push(
				centerX + (rightX * sx + upX * sy) * halfSize,
				centerY + (rightY * sx + upY * sy) * halfSize,
				centerZ + (rightZ * sx + upZ * sy) * halfSize,
			);
			normals.push(-dx, -dy, -dz);
		}
		uvs.push(0, 1, 1, 1, 1, 0, 0, 0);
		// Reverse the outward tangent winding so the star-card normal faces the origin.
		indices.push(first, first + 2, first + 1, first, first + 3, first + 2);
	}

	const mesh = new Mesh("world-celestial-stars", scene);
	const vertexData = new VertexData();
	vertexData.positions = positions;
	vertexData.normals = normals;
	vertexData.uvs = uvs;
	vertexData.indices = indices;
	vertexData.applyToMesh(mesh);
	return mesh;
}

function clamp01(value: number): number {
	return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
}

function smoothstep(edge0: number, edge1: number, value: number): number {
	const t = Math.min(1, Math.max(0, (value - edge0) / (edge1 - edge0)));
	return t * t * (3 - 2 * t);
}
