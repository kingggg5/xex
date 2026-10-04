import { Engine, Scene, ArcRotateCamera, Vector3, Color3, Color4, HemisphericLight, DirectionalLight, MeshBuilder, PBRMaterial, ShadowGenerator, ImportMeshAsync, AnimationGroup, AbstractMesh, Skeleton, TransformNode } from '@babylonjs/core';
import '@babylonjs/loaders/glTF';
import { configureAssetCodecs } from './asset-codecs';
import lod0 from '../../../assets/characters/bovine-shaman/rig-v1/runtime/optimized/minotaur_lod0.etc1s-meshopt.glb?url';
import lod1 from '../../../assets/characters/bovine-shaman/rig-v1/runtime/optimized/minotaur_lod1.etc1s-meshopt.glb?url';
import lod2 from '../../../assets/characters/bovine-shaman/rig-v1/runtime/optimized/minotaur_lod2.etc1s-meshopt.glb?url';

const byId = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvas = byId<HTMLCanvasElement>('renderCanvas');
const engine = new Engine(canvas, true, { preserveDrawingBuffer: true, stencil: true });
engine.setHardwareScalingLevel(Math.max(1, window.devicePixelRatio / 1.5));
const scene = new Scene(engine); scene.clearColor = new Color4(.085, .105, .14, 1);
const camera = new ArcRotateCamera('reviewCamera', Math.PI / 2, 1.38, 4.3, new Vector3(.1, 1.2, 0), scene);
camera.lowerRadiusLimit = .9; camera.upperRadiusLimit = 8; camera.minZ = .03; camera.wheelPrecision = 55;
camera.attachControl(canvas, true);
new HemisphericLight('ambient', new Vector3(0, 1, 0), scene).intensity = .75;
const sun = new DirectionalLight('sun', new Vector3(.5, -1, -.7), scene); sun.position = new Vector3(-3, 5, 4); sun.intensity = 1.2;
const shadows = new ShadowGenerator(1024, sun); shadows.usePercentageCloserFiltering = true; shadows.bias = .0003;
const floor = MeshBuilder.CreateGround('reviewFloor', { width: 14, height: 14 }, scene); floor.receiveShadows = true;
const floorMaterial = new PBRMaterial('floor', scene); floorMaterial.albedoColor = new Color3(.14, .17, .21); floorMaterial.roughness = .9; floorMaterial.metallic = 0; floor.material = floorMaterial;
let groups: AnimationGroup[] = [], meshes: AbstractMesh[] = [], selected: AnimationGroup | undefined, generation = 0;
let skeletons: Skeleton[] = [], transforms: TransformNode[] = [];
const clip = byId<HTMLSelectElement>('clip'), frame = byId<HTMLInputElement>('frame'), status = byId<HTMLOutputElement>('status');
const loops = new Set(['Idle', 'Walk', 'Run', 'Talk']);
function stopAll() { groups.forEach(group => group.stop()); }
function choose(name: string, play = true) {
	stopAll(); selected = groups.find(group => group.name === name); if (!selected) return;
	selected.start(loops.has(name), 1); if (!play) selected.pause();
	frame.max = String(selected.to); frame.value = String(selected.from); frame.min = String(selected.from);
	if (name !== 'Death') camera.target.set(.1, 1.2, 0); else camera.target.set(.8, .65, 0);
}
async function load() {
	const own = ++generation; status.textContent = 'กำลังโหลดโมเดล…';
	stopAll(); groups.forEach(group => group.dispose()); meshes.forEach(mesh => mesh.dispose(false, true)); skeletons.forEach(skeleton => skeleton.dispose()); transforms.forEach(node => node.dispose()); groups = []; meshes = []; selected = undefined;
	try {
		await configureAssetCodecs();
		const index = Number(byId<HTMLSelectElement>('lod').value);
		const result = await ImportMeshAsync([lod0, lod1, lod2][index], scene);
		if (own !== generation) { result.animationGroups.forEach(group => group.dispose()); result.meshes.forEach(mesh => mesh.dispose(false, true)); result.skeletons.forEach(skeleton => skeleton.dispose()); result.transformNodes.forEach(node => node.dispose()); return; }
		groups = result.animationGroups; meshes = result.meshes;
		skeletons = result.skeletons; transforms = result.transformNodes;
		meshes.forEach(mesh => shadows.addShadowCaster(mesh));
		clip.replaceChildren(...groups.map(group => { const option = document.createElement('option'); option.value = group.name; option.textContent = group.name; return option; }));
		clip.value = 'Idle'; choose('Idle');
		const triangles = meshes.reduce((sum, mesh) => sum + mesh.getTotalIndices() / 3, 0);
		status.textContent = `LOD${index} · ${triangles.toLocaleString()} triangles\n${groups.length} ท่า · ${result.skeletons[0]?.bones.length ?? 0} bones`;
	} catch (error) { if (own === generation) status.textContent = `โหลดไม่สำเร็จ: ${String(error)}`; }
}
byId<HTMLSelectElement>('lod').addEventListener('change', () => { void load(); });
clip.addEventListener('change', () => choose(clip.value));
byId('play').addEventListener('click', () => { if (selected?.isPlaying) return; selected?.play(loops.has(clip.value)); });
byId('pause').addEventListener('click', () => selected?.pause());
frame.addEventListener('input', () => { if (selected) { if (!selected.isStarted) selected.start(false); selected.pause(); selected.goToFrame(Number(frame.value)); } });
byId('front').addEventListener('click', () => { camera.alpha = Math.PI / 2; camera.beta = 1.38; camera.radius = 4.3; });
byId('side').addEventListener('click', () => { camera.alpha = 0; camera.beta = 1.38; camera.radius = 4.3; });
byId('player').addEventListener('click', () => { camera.alpha = Math.PI / 3; camera.beta = 1.02; camera.radius = 4.3; });
let lastFps = 0;
engine.runRenderLoop(() => { scene.render(); if (performance.now() - lastFps > 500) { byId('fps').textContent = `${Math.round(engine.getFps())} FPS · WebGL2 review`; lastFps = performance.now(); } });
window.addEventListener('resize', () => engine.resize());
window.addEventListener('pagehide', () => { stopAll(); scene.dispose(); engine.dispose(); }, { once: true });
void load();
