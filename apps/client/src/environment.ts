import { mergeStaticModel } from "./static-model.mjs";
import { prepareGateCityTreeCandidate } from './gate-city-tree-runtime';
import { GATE_CITY_TREE } from './gate-city-tree-candidate.mjs';
// C-MAP-DRESSING import begin
import { createSunmeadowDressing } from "./sunmeadow-dressing.js";
import { BLUEPRINT_WALK_PADS } from './blueprint-walk-support.mjs';
import { repairStandardLightPool } from './night-pool-render-fix.mjs';
import { markLookV2DressingReady } from './look-v2-pool-events.mjs';
// C-MAP-DRESSING import end
import { alignWorldAuthoredGlb } from "./world-asset-coordinates.mjs";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";
import { DynamicTexture } from "@babylonjs/core/Materials/Textures/dynamicTexture";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { PBRMaterial } from "@babylonjs/core/Materials/PBR/pbrMaterial";
import type { Material } from '@babylonjs/core/Materials/material';
import { MultiMaterial } from "@babylonjs/core/Materials/multiMaterial";
import { Texture } from "@babylonjs/core/Materials/Textures/texture";
import { SceneLoader } from "@babylonjs/core/Loading/sceneLoader";
import { createCityFountain, removeFountainPlaceholders } from './city-fountain';
import { bindCityMaterialLighting } from './city-material-lighting';
import { configureLevelEnvironment } from './level-environment-light';
import { clipLegacyGroundToCity, type CityGroundBounds } from './city-ground-ownership';
import { recordCityRepresentationPhase } from './city-review-recorder';
import { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import { HemisphericLight } from "@babylonjs/core/Lights/hemisphericLight";
import { Constants } from "@babylonjs/core/Engines/constants";
import { EmitterGlowLayer } from "./glow-emitters";
import { ShadowGenerator } from "@babylonjs/core/Lights/Shadows/shadowGenerator";
import { ImageProcessingConfiguration } from "@babylonjs/core/Materials/imageProcessingConfiguration";
import { ColorCurves } from "@babylonjs/core/Materials/colorCurves";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import "@babylonjs/core/Meshes/instancedMesh";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import type { AbstractMesh } from "@babylonjs/core/Meshes/abstractMesh";
import type { InstancedMesh } from "@babylonjs/core/Meshes/instancedMesh";
import { Scene } from "@babylonjs/core/scene";
import { createLazyLoadOnce, createStagedCityLoader } from "./city-streaming.mjs";
import { addWind, addWaterWaves, advanceNatureClock, type NatureClock } from "./nature-motion";
import { loadHeroOaks } from "./hero-oak";
import { addMeadowSurface } from "./meadow-surface";
import { addGrassShading } from "./meadow-grass-shading";
import { loadWorldBorder } from "./world-border";
import { addCloudSurface } from "./cloud-surface";
import { getGraphicsPreference, resolveGraphicsPreset, type ResolvedGraphicsPreset } from "./graphics-quality.mjs";
import { createWorldWeather } from "./world-weather";
import {applyLegacyPlantDensity} from './legacy-plant-density.mjs';
import {installWaterLandCutout} from './water-host-cutout';
import {createGrassField} from './grass-field'; // C-P1-GRASS import
import type { TerrainCellDefinition, WorldPropDefinition } from "./world-layout";
import keepAssetUrl from "./assets/models/env_reference_city.glb?url";
import guardianReviewAssetUrl from '../../../assets/models/reference-city/r5/fountain-guardian-review-candidate/city-runtime.meshopt.glb?url';
import guardianReviewV2AssetUrl from '../../../assets/models/reference-city/r5/fountain-guardian-review-v2-candidate/city-runtime.meshopt.glb?url';
import forgeR6ReviewAssetUrl from '../../../assets/models/reference-city/r5/forge-r6-texture-review-candidate/city-runtime.meshopt.glb?url';
// C-MAPDRESS-R6 begin
import cityR6CandidateAssetUrl from '../../../assets/models/reference-city/r6-candidate/city-runtime.meshopt.glb?url';
// C-MAPDRESS-R6 end
import keepHlodAssetUrl from "./assets/models/env_reference_city_hlod.glb?url";
import arrivalHlodReviewUrl from '../../../assets/models/reference-city/r5/arrival-hlod-r01/arrival-hlod-r01-runtime.glb?url';
import arrivalHlodReviewR02Url from '../../../assets/models/reference-city/r5/arrival-hlod-r02/arrival-hlod-r02-runtime-final.glb?url';
import arrivalHlodReviewR03Url from '../../../assets/models/reference-city/r5/arrival-hlod-r03/arrival-hlod-r03-runtime.glb?url';
import guardianMaterialR03Url from '../../../assets/models/reference-city/r5/guardian-material-r03-candidate/city-runtime.meshopt.glb?url';
import {createCityLampPools} from './city-lamp-pools';
import meadowTreeAssetUrl from "./assets/models/env_meadow_tree_v2.meshopt.glb?url";
import southMeadowWestAssetUrl from "./assets/world/env_sunmeadow_c7_r6.meshopt.glb?url";
import southMeadowEastAssetUrl from "./assets/world/env_sunmeadow_c8_r6.meshopt.glb?url";
import waterArtHostMaskUrl from "./assets/world/water-art-pass4b/host-mask/land-cutout-v3.png?url";
import waterArtHostMaskReceipt from "./assets/world/water-art-pass4b/host-mask/land-cutout-v3.json";
// Art pass v1 (2026-10-02): hand-painted ground and road, generated by tools/paint_meadow_textures.py.
import grassAlbedoUrl from "./assets/world/meadow_grass_painted_albedo.png?url";
import grassNormalUrl from "./assets/world/meadow_grass_painted_normal.png?url";
// v2: same alpha, RGB edge-bled into transparent texels so filtered leaf edges no longer go dark (2026-10-02).
import canopyAlbedoUrl from "./assets/world/leaf_canopy_albedo_v2.png?url";
// Painted dressed stone (tools/paint_meadow_textures.py): arch, posts, waystone, pads (art pass v1).
import stoneAlbedoUrl from "./assets/world/stone_painted_albedo.png?url";
import stoneNormalUrl from "./assets/world/stone_painted_normal.png?url";
import timberAlbedoUrl from "./assets/world/timber_dark_albedo.png?url";
import timberNormalUrl from "./assets/world/timber_dark_normal.png?url";
import treeBarkAlbedoUrl from "./assets/world/world_tree_bark_albedo.png?url";
import roadAlbedoUrl from "./assets/world/meadow_road_painted_albedo.png?url";
import roadNormalUrl from "./assets/world/meadow_road_painted_normal.png?url";
import kenneyBushAssetUrl from "./assets/foliage/kenney/plant_bushDetailed.glb?url";
import kenneyRockLargeAAssetUrl from "./assets/foliage/kenney/rock_largeA.glb?url";
import kenneyRockLargeBAssetUrl from "./assets/foliage/kenney/rock_largeB.glb?url";
// C-P1-TREE (trees in Babylon): sunmeadow-trees-v4 runtime kit, impostor atlas v3 and the thin-instance LOD field.
// Everything that uses these lives in the "C-P1-TREE" section at the end of this file.
import { ImportMeshAsync } from "@babylonjs/core/Loading/sceneLoader";
import { createNatureWater } from "./nature-water.js"; // C-P1-WATER import
import { Vector2 } from "@babylonjs/core/Maths/math.vector";
import { createImpostorField, createTreeLodField, type ImpostorAtlasManifest, type ImpostorField, type TreeLodField, type TreeLodPlacement, type TreeLodSpecies, type TreeLodStats } from "./impostors";
import { treeLodPlan, type TreeLodPlan } from "./impostor-math.mjs";
import { HERO_OAK_PROP_IDS } from "./hero-oak";
import treeImpostorManifestUrl from "./assets/world/impostors/sunmeadow-trees-v3/sunmeadow_trees_v3.impostors.json?url";
import {createStyledSakura} from './stylized-sakura';
import {isSakuraPlacement} from './sakura-look-policy.mjs';

/**
 * Static scenery, sky and lighting for the Verdant Frontier meadow (plan §14,
 * zero-spend procedural pipeline). Original IP: nothing here copies any named
 * game's assets. Owns everything scene.ts used to build with
 * createGround/createCastle/createTreesAndFences/createFlowers, upgraded:
 * gradient sky dome, warm sun with a soft shadow map, vertex-colored ground,
 * instanced grass and flowering meadow dressing.
 *
 * Contracts relied on by scene.ts:
 * - createEnvironment returns the sun (for shadows) and addShadowCaster, used
 *   to register hero/monster/guide/windmark roots.
 * - Nothing feeds server collision; decorative props avoid the walkable path
 *   and stream bands exactly like the layout they replace.
 * - No lights or shadow/glow objects live in actors.ts; this module owns them.
 * - Nothing runs at import time.
 */

export interface EnvironmentGraphicsDiagnostics {
	profile: ResolvedGraphicsPreset;
	iblCubeFaceSize: 64 | 128 | null;
	shadowMapSize: number | null;
	shadowKind: 'cascaded' | 'single-map';
	shadowCascades: number;
	shadowRenderingEnabled: boolean;
	glowEnabledActual: boolean;
	cascadedViewDistanceM: number | null;
	singleMapDistanceCulling: false;
	vegetationDensityEffective: number;
	fountain: ReturnType<typeof createCityFountain>['stats'];
	/** C-P1-TREE: sunmeadow-trees-v4 field (null until the kit is ready, or when it fell back to the legacy trees). */
	trees: (TreeLodStats & { plan: TreeLodPlan }) | null;
	limitations: string[];
}

export interface EnvironmentResult {
	/** The warm sun; kept public because the shadow generator hangs on it. */
	sun: DirectionalLight;
	/** Loads the detailed R5 city after the player crosses into the city gate. */
	ensureDetailedCity(): Promise<void>;
	revealDetailedCity(): void;
	cityDetailState(): "idle" | "loading" | "prepared" | "ready" | "failed";
	/** Loads the authored Sunmeadow detail cells before the player reaches them. */
	ensureTerrainCells(): Promise<void>;
	/** Registers a mesh (or every mesh under a root) into the shadow map. */
	addShadowCaster(target: Mesh | TransformNode, includeChildren?: boolean): void;
	applyGraphics(profile: ResolvedGraphicsPreset): void;
	graphicsDiagnostics(): EnvironmentGraphicsDiagnostics;
	setWorldTick(tick: number): void;
	/** Transfers the existing rain emitter to the pooled atmosphere owner. */
	useExternalRain(): void;
}

const FIELD_LIMIT = 27;
const PATH_HALF_WIDTH = 3.2;
const STREAM_Z = 19;
const STREAM_HALF_WIDTH = 2.4;
const CASTLE_Z_START = 31;

export async function createEnvironment(
	scene: Scene,
	materials: Record<string, StandardMaterial>,
	cityGateZ = 24,
	prepareDetailedCity: (mesh: Mesh) => Promise<void> = async () => {},
	terrainCells: TerrainCellDefinition[] = [],
	worldProps: WorldPropDefinition[] = [],
	worldHalfExtent = 308,
	cityGroundBounds?: CityGroundBounds,
	initialGraphics?: ResolvedGraphicsPreset,
	getGroundHeight: (x: number, z: number) => number | null = () => 0,
): Promise<EnvironmentResult> {
	const rng = seededRandom(20260925);

	const animation: Array<(time: number, deltaSeconds: number) => void> = [];
	const natureClock: NatureClock = { phase: 0 };
	animation.push((_time, delta) => advanceNatureClock(natureClock, delta));
	const cityOverview = import.meta.env.DEV && new URLSearchParams(window.location.search).get("cityOverview") === "1";

	// Everything created from here to the meadow dressing is static scenery except the drifting cloud
	// puffs; it is frozen once built (see freezeStaticScenery).
	const staticSceneryBefore = new Set(scene.meshes);
	const driftingCloudPuffs = createSky(scene, materials, animation, rng);
	scene.fogMode = Scene.FOGMODE_EXP2;
	scene.fogDensity = cityOverview ? 0.00075 : 0.0017;
	scene.fogColor = cityOverview ? Color3.FromHexString("#d8e8f4") : Color3.FromHexString("#cfe0d2");

	const hemisphere = new HemisphericLight("env-sky-fill", new Vector3(0, 1, 0), scene);
	hemisphere.intensity = 0.62;
	// Art pass v1: saturated sky fill above, green-brown meadow bounce below (shadows stay coloured, not grey).
	hemisphere.diffuse = Color3.FromHexString("#a9c9f4");
	hemisphere.groundColor = Color3.FromHexString("#6a7440");

	const sun = new DirectionalLight("env-sun", new Vector3(-0.55, -0.82, 0.35), scene);
	sun.position = new Vector3(-42, 65, -56);
	sun.intensity = 1.65;
	sun.diffuse = Color3.FromHexString("#fff1d6");
	sun.specular = Color3.FromHexString("#fff8ea");
	// Art pass v1 (2026-10-02): PBR surfaces took most of their light from the sky IBL, which erased sun
	// shadows on the meadow ground and path. The IBL is now soft fill (see the intensity driver below) and the
	// sun carries the form on every PBR surface, including glTF props loaded later. The weight follows the
	// sun (1.0 under the moon, 1.6 in full sun) through the light driver further down.
	let pbrDirectWeight = 1.6;
	const weightDirectLight = (material: Material) => { if (material instanceof PBRMaterial) material.directIntensity = pbrDirectWeight; };
	for (const material of scene.materials) weightDirectLight(material);
	scene.onNewMaterialAddedObservable.add(weightDirectLight);

	// Debug toggles for engine triage (?noshadow=1 / ?noglow=1).
	const debug = new URLSearchParams(window.location.search);
	const shadowsEnabled = debug.get("noshadow") !== "1";
	const previewHeroOak = import.meta.env.DEV && debug.get("heroOakPreview") === "1";
	const glowEnabled = debug.get("noglow") !== "1";
	const { CascadedShadowGenerator } = await import("@babylonjs/core/Lights/Shadows/cascadedShadowGenerator");
	const canvas = scene.getEngine().getRenderingCanvas();
	// The scene and its environment must start with the same resolved tier.
	let profile = initialGraphics ?? resolveGraphicsPreset(getGraphicsPreference(), {
		formFactor: matchMedia("(pointer: coarse)").matches || ((canvas?.clientWidth ?? innerWidth) <= 1000 && (canvas?.clientHeight ?? innerHeight) <= 900) ? "mobile" : "desktop",
		width: canvas?.clientWidth, height: canvas?.clientHeight, devicePixelRatio,
	});
	let levelLight: Awaited<ReturnType<typeof configureLevelEnvironment>> | undefined;
	try { levelLight = await configureLevelEnvironment(scene, profile); }
	catch (error) { console.warn('Environment reflection light unavailable; keeping ambient lighting.', error); }
	// A bounded lookdev control: compare filter cost without changing map size, cascades or casters.
	const shadowFilteringQuality = import.meta.env.DEV && debug.get("shadowFilter") === "low"
		? ShadowGenerator.QUALITY_LOW : ShadowGenerator.QUALITY_MEDIUM;
	const makeShadows = (quality: ResolvedGraphicsPreset) => {
		const result = quality.cascades > 1 && CascadedShadowGenerator.IsSupported
			? new CascadedShadowGenerator(quality.shadowMapSize, sun) : new ShadowGenerator(quality.shadowMapSize, sun);
		if (result instanceof CascadedShadowGenerator) {
			result.numCascades = quality.cascades; result.lambda = .72; result.stabilizeCascades = true;
			result.shadowMaxZ = cityOverview ? Math.max(240, quality.shadowDistance) : quality.shadowDistance;
			result.cascadeBlendPercentage = .12;
		}
		result.usePercentageCloserFiltering = true; result.filteringQuality = shadowFilteringQuality;
		result.darkness = .20; result.bias = .00015; result.normalBias = .025;
		result.transparencyShadow = true; result.enableSoftTransparentShadow = false;
		return result;
	};
	let shadows = makeShadows(profile);
	// PCF keeps contact shadows readable on both backends; ESM washed out here.
	shadows.usePercentageCloserFiltering = true;
	shadows.filteringQuality = shadowFilteringQuality;
	shadows.darkness = 0.20;
	shadows.bias = 0.00015;
	shadows.normalBias = 0.025;
	shadows.transparencyShadow = true;
	// Wrapped wind shaders in 9.27.1 omit the WGSL Bayer helper for this mode.
	shadows.enableSoftTransparentShadow = false;
	// Clouds stay out of the shadow map (inbox B5, done here in the map lane): they cost a caster pass per
	// cascade and stretched the auto-fitted depth range. ambient-world adds its cloud shadow cards only while
	// these puffs are listed, so it adds none now. Cloud shadows return as the sky spec §7.3 light cookie.
	sun.shadowMinZ = 2;
	// The R4 city extends far beyond the original keep; keep the depth range
	// wide enough that its rear walls and skyline still cast shadows.
	sun.shadowMaxZ = 240;
	// Fit the depth range to the casters, or the shadow map can clip empty.
	sun.autoCalcShadowZBounds = shadowsEnabled;

	// Opt-in glow: only emitters are drawn into its target, not every visible mesh (glow-emitters.ts).
	// Our post path is LDR, so the glow is clamped and screen-blended and cannot push a pixel past white
	// (babylon docs recheck 8.2/C3; constructor-only options).
	const glow = glowEnabled ? new EmitterGlowLayer("env-glow", scene, {
		mainTextureSamples: 2, ldrMerge: true, alphaBlendingMode: Constants.ALPHA_SCREENMODE,
	}) : null;
	if (glow) {
		glow.isEnabled = profile.glowEnabled;
		glow.intensity = 0.55;
		// Sky color and cloud fill are ambient scenery, not magical emitters.
		for (const mesh of scene.meshes) {
			if (mesh instanceof Mesh && (mesh.name === "env-sky-dome" || mesh.name.startsWith("env-cloud-master-"))) {
				glow.addExcludedMesh(mesh);
			}
		}
	}
	// C-LOOK-V2 begin: DEV-only ?look=v2 (default off): sky-dome gradient remap, grade fog density, night light pools.
	// Colours and the post grade come from look-grade-v2.mjs through world-weather.ts. Doc: docs/reviews/2026-10-03-look-grade-v2.md
	if (import.meta.env.DEV && new URLSearchParams(location.search).get("look") === "v2") {
		void import("./look-grade-v2-scene").then(async ({ installLookGradeV2 }) => {
			if(scene.isDisposed)return;
			installLookGradeV2(scene, glow, {nativeSky:true,nativeFog:true});
			const pool=scene.getMeshByName('look-v2-pool');
			const material=scene.getMaterialByName('look-v2-pool-mat');
			if(pool instanceof Mesh && material instanceof StandardMaterial && repairStandardLightPool(material))
				await material.forceCompilationAsync(pool,{useInstances:true});
		})
			.catch(error => console.warn("look v2 unavailable", error));
	}
	// C-LOOK-V2 end
	const masonryTexture = createMasonryTexture(scene);
	for (const material of [materials.wall, materials.wallLight]) material.diffuseTexture = masonryTexture;
	const leafTexture = createLeafTexture(scene);
	for (const material of [materials.leaves, materials.leavesLight, materials.leavesGold]) material.diffuseTexture = leafTexture;

	scene.imageProcessingConfiguration.toneMappingEnabled = true;
	scene.imageProcessingConfiguration.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
	scene.imageProcessingConfiguration.contrast = 1.12;
	scene.imageProcessingConfiguration.exposure = 1.0;
	// Hand-painted MMO grade: richer colour without touching individual materials.
	scene.imageProcessingConfiguration.colorCurvesEnabled = true;
	const grade = new ColorCurves();
	grade.globalSaturation = 16;
	scene.imageProcessingConfiguration.colorCurves = grade;

	const terrainMaterial = createTerrainMaterial(scene);
	terrainMaterial.backFaceCulling = false;
	terrainMaterial.forceNormalForward = true;
	const stoneCellMaterial = createPbrCellMaterial(scene, "env-cell-stone", stoneAlbedoUrl, stoneNormalUrl, 0.92);
	const timberCellMaterial = createPbrCellMaterial(scene, "env-cell-timber", timberAlbedoUrl, timberNormalUrl, 0.86);
	const treeBarkMaterial = new PBRMaterial("env-shared-tree-bark", scene);
	// C-P1-TREE: this bark only dresses the home-made fallback trees now (field GLB and cell trees, used when the
	// sunmeadow-trees-v4 kit fails to load), so its 0.6 MB albedo loads on first fallback use, not at every start.
	const legacyTreeBark = () => {
		if (treeBarkMaterial.albedoTexture) return treeBarkMaterial;
		const treeBarkTexture = new Texture(treeBarkAlbedoUrl, scene, false, false);
		treeBarkTexture.gammaSpace = true;
		// The original albedo is not a seamless scan. Mirrored even repeats give
		// equal colors at tube UV seams; retain the original source and its audit.
		treeBarkTexture.wrapU = treeBarkTexture.wrapV = Texture.MIRROR_ADDRESSMODE;
		treeBarkTexture.uScale = 2;
		treeBarkTexture.vScale = 4;
		treeBarkMaterial.albedoTexture = treeBarkTexture;
		return treeBarkMaterial;
	};
	treeBarkMaterial.metallic = 0;
	treeBarkMaterial.roughness = 0.95;
	addWind(treeBarkMaterial, scene, natureClock, 0.14, 1.65, 6);
	// C-P1-TREE: starts loading the tree kit and the impostor atlas now; field and cell trees join when ready.
	const sunmeadowTrees = createSunmeadowTrees(scene, natureClock, () => shadows, shadowsEnabled, profile);
	// C-MAP-DRESSING begin
	const dressingQuery = import.meta.env.DEV ? new URLSearchParams(location.search) : new URLSearchParams();
	if (dressingQuery.get("dressing") === "v3") {
		await createSunmeadowDressing(scene, { getProfile: () => profile, getShadows: () => shadows, shadowsEnabled, getGroundHeight });
		if(dressingQuery.get('blueprintWave')!=='off' && dressingQuery.get('blueprintSheep')!=='off') {
			const {createBlueprintSheep}=await import('./blueprint-sheep');
			await createBlueprintSheep(scene,{profile,groundAt:getGroundHeight,shadows,shadowsEnabled});
		}
	}
	// C-MAP-DRESSING end
	if (import.meta.env.DEV && debug.get('look') === 'v2') markLookV2DressingReady(scene);
	if (import.meta.env.DEV && debug.get("cellDoubleSided") === "1") {
		stoneCellMaterial.backFaceCulling = false;
		timberCellMaterial.backFaceCulling = false;
	}
	if (import.meta.env.DEV && debug.get("cellStoneNoNormal") === "1") stoneCellMaterial.bumpTexture = null;
	const trailMaterial = createRoadMaterial(scene);
	addWind(timberCellMaterial, scene, natureClock, 0.16, 1.65, 6);
	for (const key of ["grass", "grassLight", "stem", "flowerWhite", "flowerGold", "flowerPink"]) {
		materials[key].backFaceCulling = false;
		materials[key].twoSidedLighting = true;
		addWind(materials[key], scene, natureClock, 0.11, 0, 0.8);
	}
	// Art pass v1: blades grow out of the painted ground (dark root -> lit tip, ground-like lighting).
	addGrassShading(materials.grassLight, { root: "#34482a", tip: "#63783a", height: 0.85, upBend: 0.8 });
	addGrassShading(materials.grass, { root: "#2f4226", tip: "#566a34", height: 0.6, upBend: 0.8 });
	createGroundAndPath(scene, materials, rng, terrainMaterial, trailMaterial, natureClock, animation, worldHalfExtent);
	// Water host review: clip the flat legacy land before admitting derived beds/banks.
	const waterArtPreview=import.meta.env.DEV&&debug.get('waterArt')==='pass4b';
	const waterReviewEnabled=import.meta.env.DEV&&(debug.get('water')==='natural'||debug.get('dressing')==='v3'||waterArtPreview);
	const waterHost=waterReviewEnabled?installWaterLandCutout(scene,[terrainMaterial,trailMaterial,
		materials.grass,materials.grassLight,materials.stem,materials.flowerWhite,materials.flowerGold,materials.flowerPink],
		waterArtPreview?{textureUrl:waterArtHostMaskUrl,receipt:waterArtHostMaskReceipt}:undefined):null;
	if (cityGroundBounds) clipLegacyGroundToCity(scene, cityGroundBounds);
	// These visible apron patches share their exact extents and height with server walk support.
	for (const pad of BLUEPRINT_WALK_PADS) {
		const [minX, maxX, minZ, maxZ] = pad.boundsXZ;
		const mesh = MeshBuilder.CreateGround(pad.id, { width: maxX - minX, height: maxZ - minZ }, scene);
		mesh.position.set((minX + maxX) / 2, pad.y, (minZ + maxZ) / 2);
		mesh.material = terrainMaterial;
		mesh.receiveShadows = true;
		mesh.isPickable = false;
		mesh.metadata = { walkSupportId: pad.id };
	}
	let grassField: ReturnType<typeof createGrassField> | null = null; // C-P1-GRASS-ADOPT declaration
	const ensureTerrainCells = createLazyLoadOnce(async () => {
		await loadTerrainCells(scene, terrainCells, terrainMaterial, stoneCellMaterial, timberCellMaterial,
			materials, shadows, shadowsEnabled, prepareDetailedCity, natureClock, previewHeroOak, legacyTreeBark,
			sunmeadowTrees, worldProps);
		// Host-water adoption: Cell world_leaf_green uses this dedicated fern/card material.
		waterHost?.adoptMaterial(scene.getMaterialByName('env-cell-canopy'));
		// C-P1-GRASS-ADOPT begin
		grassField?.adoptTerrainCells(scene.meshes);
		// C-P1-GRASS-ADOPT end
		if (previewHeroOak) await loadHeroOaks(scene, worldProps, natureClock, shadows, shadowsEnabled, prepareDetailedCity);
		applyGraphics(profile);
	});
	const proceduralKeep = createCastle(scene, materials);
	const fallbackMountains = createDistantMountains(scene, worldHalfExtent);
	try {
		await loadWorldBorder(scene, terrainMaterial, prepareDetailedCity);
		for (const mesh of fallbackMountains) { mesh.material?.dispose(); mesh.dispose(); }
	} catch (error) {
		console.warn("Authored mountain border unavailable; fallback ridges remain.", error);
	}
	createFencesAndHills(scene, materials);
	if (import.meta.env.DEV && debug.get('arrivalProps') === 'r01') {
		try { await (await import('./arrival-fence-review')).createArrivalFenceReview(scene); }
		catch (error) { console.warn('Arrival fence review failed; original fences retained.', error); }
	}
	const proceduralTrees = createTrees(scene, materials, rng);
	await createKenneyFoliage(scene);
	const legacyPlants = createMeadowDressing(scene, materials, rng);
	if (import.meta.env.DEV && debug.get('starterRocks') === 'r01') {
		const { installStarterRocksReview } = await import('./starter-rocks-review');
		await installStarterRocksReview(scene);
	}
	const driftingClouds = new Set<AbstractMesh>(driftingCloudPuffs);
	freezeStaticScenery(scene.meshes.filter((mesh) => !staticSceneryBefore.has(mesh) && !driftingClouds.has(mesh)));
	recordCityRepresentationPhase(scene, 'cold');
	const ensureDetailedCity = await upgradeKeepAndTrees(
		scene, proceduralKeep, proceduralTrees, cityGateZ, () => shadows, shadowsEnabled, prepareDetailedCity,
		natureClock, legacyTreeBark, () => profile.waterDetail, sunmeadowTrees, getGroundHeight,
	);
	const weather = createWorldWeather(scene, sun, hemisphere, terrainMaterial, natureClock);
	// C-P1-WATER begin
	const naturalWater = waterReviewEnabled
		? createNatureWater(scene, () => profile, glow, { particles: debug.get("waterFx") !== "0" }) : null;
	if (naturalWater) {
		await naturalWater.ready.then(() => { if (debug.get("waterVisible") !== "0") naturalWater.reveal(); }).catch(error => {
			console.warn("Natural water unavailable; opt-in review remains incomplete.", error);
		});
	}
	// C-P1-WATER end
	// Host cutouts fail closed when water loading/compilation/quality replacement fails.
	animation.push(()=>{const status=naturalWater?.stats();const ready=!!status?.ready&&!status.error&&(status.revealed||debug.get('waterVisible')==='0');waterHost?.setEnabled(ready);waterHost?.setP0Enabled(ready&&debug.get('dressing')==='v3'&&debug.get('blueprintWave')!=='off');});
	waterHost?.setDecksEnabled(dressingQuery.get('dressing')==='v3'&&scene.meshes.some(mesh=>mesh.metadata?.dressingV3));
	let previousEnvironmentIntensity = -1;
	let previousDirectWeight = -1;
	animation.push(() => {
		// Art pass v1: 0 under the moon .. 1 in full sun. The sky IBL is soft fill (.03 night, .25 day; it was
		// up to .52 and out-lit the sun) and PBR takes the stronger share of direct light by day only, so PBR
		// ground and StandardMaterial props stay in one brightness range at night.
		const sunWeight = Math.max(0, Math.min(1, (sun.intensity - .25) / .9));
		const settled = sunWeight === 0 || sunWeight === 1;
		const value = .03 + .22 * sunWeight;
		if (Math.abs(value - previousEnvironmentIntensity) > .01 || (settled && value !== previousEnvironmentIntensity)) {
			levelLight?.setIntensity(value); previousEnvironmentIntensity = value;
		}
		const directWeight = 1 + .6 * sunWeight;
		if (Math.abs(directWeight - previousDirectWeight) > .02 || (settled && directWeight !== previousDirectWeight)) {
			pbrDirectWeight = directWeight; previousDirectWeight = directWeight;
			for (const material of scene.materials) weightDirectLight(material);
		}
	});
	const originalIndices = new WeakMap<object, number>();
	let plantMeshes: Mesh[] = [];
	let visibilityChecked = 0;
	function applyGraphics(next: ResolvedGraphicsPreset) {
		const rebuild = next.shadowMapSize !== profile.shadowMapSize || next.cascades !== profile.cascades;
		const casters = shadows.getShadowMap()?.renderList?.slice() ?? [];
		profile = next;
		if (rebuild) {
			shadows.dispose(); shadows = makeShadows(next);
			if (shadowsEnabled) for (const mesh of casters) if (!mesh.isDisposed()) shadows.addShadowCaster(mesh, false);
		}
		if (shadows instanceof CascadedShadowGenerator) shadows.shadowMaxZ = cityOverview ? Math.max(240,next.shadowDistance) : next.shadowDistance;
		if (glow) glow.isEnabled = next.glowEnabled;
		weather.setQuality(next);
		sunmeadowTrees.setProfile(next); // C-P1-TREE: tier swap/end distances, LOD1 coverage, density
		plantMeshes = scene.meshes.filter((mesh): mesh is Mesh => mesh instanceof Mesh && mesh.name.startsWith("Cell ")
			&& /world_cell_grass|world_cell_flower|world_leaf_green/.test(mesh.name));
		for (const mesh of plantMeshes) {
			applyLegacyPlantDensity(mesh,next.vegetationDensity,originalIndices);
		}
	}
	animation.push((time) => {
		if(time-visibilityChecked<.4)return;visibilityChecked=time;
		const camera=scene.activeCamera;if(!camera)return;
		for(const mesh of plantMeshes){
			// A replacement field may dispose legacy cell plants after this tier snapshot was built.
			if(mesh.isDisposed()||mesh.getTotalVertices()===0)continue;
			const bound=mesh.getBoundingInfo().boundingSphere;
			const range=110*profile.vegetationDistanceFactor+bound.radiusWorld;
			mesh.isVisible=Vector3.DistanceSquared(camera.position,bound.centerWorld)<range*range;
		}
		for(const group of legacyPlants){
			const density=Math.min(1,Math.max(0,profile.vegetationDensity));
			const chosen=(group.order*.61803398875)%1<density;
			const dx=camera.position.x-group.x,dz=camera.position.z-group.z;
			const range=75*profile.vegetationDistanceFactor;
			const visible=chosen&&dx*dx+dz*dz<range*range;
			for(const part of group.parts)if(!part.isDisposed())part.isVisible=visible;
		}
	});
	applyGraphics(profile);
	if (import.meta.env.DEV && (debug.get("worldSector") === "1" || debug.get("meadowPlaytest") === "1")) {
		try {
			await ensureTerrainCells();
		} catch (error) {
			console.warn("Sunmeadow detail cells could not be loaded for preview.", error);
		}
	}
	if (cityOverview) {
		try {
			await ensureDetailedCity();
			ensureDetailedCity.reveal();
		} catch (error) {
			console.warn("Detailed city preview failed; the meadow HLOD remains available.", error);
		}
	}

	scene.onBeforeRenderObservable.add(() => {
		const time = performance.now() * 0.001;
		const delta = scene.getEngine().getDeltaTime() / 1000;
		for (const tick of animation) tick(time, delta);
	});

	// C-P1-GRASS begin
	grassField = import.meta.env.DEV && (debug.get('grass') === 'field' || debug.get('dressing') === 'v3')
		? createGrassField(scene,{terrainMaterial,natureClock,glow,profile:()=>profile}) : null;
	if(grassField) await grassField.ready.catch(error=>console.warn('Grass field review incomplete.',error));
	// C-P1-GRASS end
	return {
		sun,
		applyGraphics,
		graphicsDiagnostics() {
			return {
				profile: {...profile}, iblCubeFaceSize: levelLight?.cubeFaceSize ?? null,
				shadowMapSize: shadows.getShadowMap()?.getSize().width ?? null,
				shadowKind: shadows instanceof CascadedShadowGenerator ? 'cascaded' : 'single-map',
				shadowCascades: shadows instanceof CascadedShadowGenerator ? shadows.numCascades : 1,
				shadowRenderingEnabled: shadowsEnabled, glowEnabledActual: glow?.isEnabled ?? false,
				cascadedViewDistanceM: shadows instanceof CascadedShadowGenerator ? shadows.shadowMaxZ : null,
				singleMapDistanceCulling: false,
				vegetationDensityEffective: Math.min(1,Math.max(0,profile.vegetationDensity)),
				fountain: ensureDetailedCity.getWaterStats(),
				trees: sunmeadowTrees.stats(),
				limitations: ['IBL cube resolution is fixed at startup.', 'Single-map shadows do not implement the requested caster-distance limit.', 'Ultra foliage density clamps to the authored maximum; merged city trees are not density-managed.', 'Native fountain uses two outlet selections; Ultra has no extra outlet tier.'],
			};
		},
		setWorldTick: weather.setWorldTick,
		useExternalRain: weather.useExternalRain,
		ensureDetailedCity,
		cityDetailState: ensureDetailedCity.getState,
		revealDetailedCity: ensureDetailedCity.reveal,
		ensureTerrainCells,
		addShadowCaster(target, includeChildren = true) {
			if (!shadowsEnabled) return;
			if (target instanceof Mesh) {
				shadows.addShadowCaster(target, includeChildren);
				return;
			}
			for (const child of target.getChildMeshes(false)) {
				if (child instanceof Mesh) shadows.addShadowCaster(child, false);
			}
		},
	};
}

/** Zenith-to-horizon gradient painted once onto an unlit inverted dome. */
function createSky(scene: Scene, materials: Record<string, StandardMaterial>, animation: Array<(time: number, deltaSeconds: number) => void>, rng: () => number): InstancedMesh[] {
	const dome = MeshBuilder.CreateSphere("env-sky-dome", { diameter: 2200, segments: import.meta.env.DEV && new URLSearchParams(location.search).get("look") === "v2" ? 64 : 16, sideOrientation: Mesh.BACKSIDE }, scene);
	dome.isPickable = false;
	const texture = new DynamicTexture("env-sky-texture", { width: 16, height: 256 }, scene, false);
	const context = texture.getContext() as CanvasRenderingContext2D;
	const gradient = context.createLinearGradient(0, 0, 0, 256);
	gradient.addColorStop(0, "#2f6fc4");
	gradient.addColorStop(0.42, "#7fb2e6");
	gradient.addColorStop(0.68, "#c6e2ef");
	gradient.addColorStop(0.85, "#eaf2d4");
	gradient.addColorStop(1, "#e6edc8");
	context.fillStyle = gradient;
	context.fillRect(0, 0, 16, 256);
	texture.update();

	const material = new StandardMaterial("env-sky-material", scene);
	material.emissiveTexture = texture;
	material.disableLighting = true;
	material.backFaceCulling = false;
	material.disableDepthWrite = true;
	material.fogEnabled = false;
	dome.material = material;

	const cloudMaterial = materials.cloud;
	cloudMaterial.emissiveColor = new Color3(0.25, 0.27, 0.28);
	cloudMaterial.linkEmissiveWithDiffuse = true;
	cloudMaterial.transparencyMode = StandardMaterial.MATERIAL_ALPHABLEND;
	cloudMaterial.alpha = 0.93;
	addCloudSurface(cloudMaterial);
	const cityOverview = import.meta.env.DEV && new URLSearchParams(window.location.search).get("cityOverview") === "1";
	const masters = [
		MeshBuilder.CreateSphere("env-cloud-master-s", { diameter: 9, segments: 12 }, scene),
		MeshBuilder.CreateSphere("env-cloud-master-m", { diameter: 14, segments: 12 }, scene),
	];
	const puffs: Array<{ puff: InstancedMesh; speed: number }> = [];
	for (let cloud = 0; cloud < 16; cloud++) {
		const master = masters[cloud % masters.length];
		const southern = cloud >= 9;
		const baseX = (rng() * 2 - 1) * (southern ? 145 : 85);
		const baseY = (southern ? 38 : 30) + rng() * 16;
		const baseZ = southern ? -145 - rng() * 115 : -35 + rng() * 100;
		const puffsPerCloud = 5 + Math.floor(rng() * 3);
		for (let puff = 0; puff < puffsPerCloud; puff++) {
			const instance = master.createInstance(`env-cloud-${cloud}-${puff}`);
			const spread = (puff - (puffsPerCloud - 1) * 0.5) * 3.9;
			instance.position.set(baseX + spread, baseY + Math.sin(puff * 1.7) * 1.8, baseZ + (rng() * 2 - 1) * 3.8);
			instance.scaling.setAll(0.70 + rng() * 0.6);
			instance.scaling.x *= 1.25;
			instance.scaling.y *= 0.48 + rng() * 0.16;
			if (cityOverview) instance.isVisible = false;
			instance.isPickable = false;
			puffs.push({ puff: instance, speed: 0.25 + rng() * 0.35 });
		}
	}
	masters[0].material = cloudMaterial;
	masters[1].material = cloudMaterial;
	for (const master of masters) {
		master.isVisible = false;
		master.isPickable = false;
	}
	animation.push((_time, delta) => {
		for (const entry of puffs) {
			entry.puff.position.x += entry.speed * delta;
			if (entry.puff.position.x > 180) entry.puff.position.x = -180;
		}
	});
	return puffs.map(entry => entry.puff);
}

function createTerrainMaterial(scene: Scene): PBRMaterial {
	const material = new PBRMaterial("env-shared-world-grass", scene);
	const albedo = new Texture(grassAlbedoUrl, scene, false, false);
	albedo.wrapU = Texture.WRAP_ADDRESSMODE;
	albedo.wrapV = Texture.WRAP_ADDRESSMODE;
	albedo.gammaSpace = true;
	const normal = new Texture(grassNormalUrl, scene, false, false);
	normal.wrapU = Texture.WRAP_ADDRESSMODE;
	normal.wrapV = Texture.WRAP_ADDRESSMODE;
	normal.gammaSpace = false;
	// The painted normal is weak by construction; this lets clumps catch a little low sun.
	normal.level = 0.35;
	material.albedoTexture = albedo;
	material.bumpTexture = normal;
	material.albedoColor = Color3.FromHexString("#e9f0dc");
	material.metallic = 0;
	material.roughness = 0.94;
	addMeadowSurface(material);
	return material;
}

/** Hand-painted dirt road: strip texture, U across (clamped, ragged grass shoulders alpha-tested), V along. */
function createRoadMaterial(scene: Scene): PBRMaterial {
	const material = new PBRMaterial("env-meadow-road", scene);
	const albedo = new Texture(roadAlbedoUrl, scene, false, false);
	albedo.wrapU = Texture.CLAMP_ADDRESSMODE;
	albedo.wrapV = Texture.WRAP_ADDRESSMODE;
	albedo.gammaSpace = true;
	albedo.hasAlpha = true;
	const normal = new Texture(roadNormalUrl, scene, false, false);
	normal.wrapU = Texture.CLAMP_ADDRESSMODE;
	normal.wrapV = Texture.WRAP_ADDRESSMODE;
	normal.gammaSpace = false;
	normal.level = 0.6;
	material.albedoTexture = albedo;
	material.bumpTexture = normal;
	material.albedoColor = Color3.White();
	material.metallic = 0;
	material.roughness = 0.9;
	material.useAlphaFromAlbedoTexture = true;
	material.transparencyMode = PBRMaterial.MATERIAL_ALPHATEST;
	material.alphaCutOff = 0.5;
	return material;
}

function createPbrCellMaterial(scene: Scene, name: string, albedoUrl: string, normalUrl: string, roughness: number): PBRMaterial {
	const material = new PBRMaterial(name, scene);
	const albedo = new Texture(albedoUrl, scene, false, false);
	albedo.wrapU = Texture.WRAP_ADDRESSMODE;
	albedo.wrapV = Texture.WRAP_ADDRESSMODE;
	albedo.gammaSpace = true;
	const normal = new Texture(normalUrl, scene, false, false);
	normal.wrapU = Texture.WRAP_ADDRESSMODE;
	normal.wrapV = Texture.WRAP_ADDRESSMODE;
	normal.gammaSpace = false;
	material.albedoTexture = albedo;
	material.bumpTexture = normal;
	material.albedoColor = Color3.White();
	material.metallic = 0;
	material.roughness = roughness;
	material.transparencyMode = PBRMaterial.MATERIAL_OPAQUE;
	material.useAlphaFromAlbedoTexture = false;
	return material;
}

function applyWorldGroundAttributes(mesh: Mesh): void {
	const positions = mesh.getVerticesData(VertexBuffer.PositionKind);
	if (!positions) throw new Error(`Ground mesh ${mesh.name} has no positions.`);
	const uvs = new Float32Array(positions.length / 3 * 2);
	const colors = new Float32Array(positions.length / 3 * 4);
	for (let offset = 0; offset < positions.length; offset += 3) {
		const vertex = offset / 3;
		const x = positions[offset] + mesh.position.x;
		const z = positions[offset + 2] + mesh.position.z;
		uvs[vertex * 2] = x / 6;
		uvs[vertex * 2 + 1] = z / 6;
		const variation = groundVariation(x, z);
		colors[vertex * 4] = lerp(0.82, 0.98, variation);
		colors[vertex * 4 + 1] = lerp(0.84, 0.99, variation);
		colors[vertex * 4 + 2] = lerp(0.79, 0.94, variation);
		colors[vertex * 4 + 3] = 1;
	}
	mesh.setVerticesData(VertexBuffer.UVKind, uvs);
	mesh.setVerticesData(VertexBuffer.ColorKind, colors);
}

/** Opaque share of the painted road strip (alpha-tested shoulders take the rest). */
const ROAD_OPAQUE_FRACTION = 0.72;
/** World metres per repeat of the road strip along its length (512 x 1024 px -> ~100 px/m both ways). */
const ROAD_REPEAT_METERS = 10;

/** Road strip UVs: U across the ribbon (0 = left bank, 1 = right bank), V along it in world metres. */
function applyRoadStripCoordinates(mesh: Mesh, banks: [Vector3[], Vector3[]], repeatMeters: number): void {
	const positions = mesh.getVerticesData(VertexBuffer.PositionKind);
	if (!positions || !Number.isFinite(repeatMeters) || repeatMeters <= 0 || banks[0].length < 2) {
		throw new Error(`Mesh ${mesh.name} cannot receive road strip UVs.`);
	}
	const [left, right] = banks;
	const firstZ = left[0].z;
	const step = left[1].z - firstZ;
	const uvs = new Float32Array(positions.length / 3 * 2);
	for (let offset = 0; offset < positions.length; offset += 3) {
		const vertex = offset / 3;
		const x = positions[offset] + mesh.position.x;
		const z = positions[offset + 2] + mesh.position.z;
		const index = Math.max(0, Math.min(left.length - 1, Math.round((z - firstZ) / step)));
		uvs[vertex * 2] = Math.abs(x - left[index].x) <= Math.abs(x - right[index].x) ? 0 : 1;
		uvs[vertex * 2 + 1] = z / repeatMeters;
	}
	mesh.setVerticesData(VertexBuffer.UVKind, uvs);
}

function createLeafCardMaterial(scene: Scene, name: string, clock: NatureClock) {
	const material = new StandardMaterial(name, scene);
	const texture = new Texture(canopyAlbedoUrl, scene, false, false);
	texture.hasAlpha = true;
	texture.wrapU = Texture.CLAMP_ADDRESSMODE;
	texture.wrapV = Texture.CLAMP_ADDRESSMODE;
	material.diffuseTexture = texture;
	material.diffuseColor = Color3.White();
	material.specularColor = Color3.Black();
	material.transparencyMode = StandardMaterial.MATERIAL_ALPHATEST;
	material.useAlphaFromDiffuseTexture = true;
	material.alphaCutOff = 0.42;
	material.backFaceCulling = false;
	material.twoSidedLighting = true;
	material.emissiveColor = new Color3(0.09, 0.12, 0.06);
	material.linkEmissiveWithDiffuse = true;
	addWind(material, scene, clock, 0.28, 0, 6);
	return { material, texture };
}

async function loadTerrainCells(
	scene: Scene,
	cells: TerrainCellDefinition[],
	terrainMaterial: PBRMaterial,
	stoneMaterial: PBRMaterial,
	timberMaterial: PBRMaterial,
	materials: Record<string, StandardMaterial>,
	shadows: ShadowGenerator,
	shadowsEnabled: boolean,
	prepareCellMesh: (mesh: Mesh) => Promise<void>,
	natureClock: NatureClock,
	previewHeroOak: boolean,
	legacyTreeBark: () => PBRMaterial,
	trees: SunmeadowTrees,
	worldProps: readonly WorldPropDefinition[],
): Promise<void> {
	const assets: Record<string, string> = {
		env_sunmeadow_c7_r6: southMeadowWestAssetUrl,
		env_sunmeadow_c8_r6: southMeadowEastAssetUrl,
	};
	const cellMeshes: Mesh[] = [];
	const canopyMaterial = new StandardMaterial("env-cell-canopy", scene);
	canopyMaterial.diffuseColor = Color3.FromHexString("#668a40");
	canopyMaterial.specularColor = Color3.FromHexString("#10200b");
	canopyMaterial.backFaceCulling = false;
	canopyMaterial.twoSidedLighting = true;
	// C-P1-TREE: with the sunmeadow-trees-v4 kit ready, the cells' baked home-made trees (world_tree_bark* and
	// world_leaf_cards* meshes, hero fallbacks included) are dropped and the same world-prop trees come back as kit
	// species at their collision blockers (sunmeadowCellTrees). The legacy bark and leaf-card materials are made only
	// when the kit failed and the old trees stay.
	const legacyTrees = !(await trees.ready);
	const legacyLeaves = legacyTrees ? createLeafCardMaterial(scene, "env-cell-leaf-cards", natureClock) : null;
	const debugStone = import.meta.env.DEV && new URLSearchParams(location.search).get("cellStoneSolid") === "1"
		? new StandardMaterial("env-stone-visibility-debug", scene) : null;
	if (debugStone) {
		debugStone.disableLighting = true;
		debugStone.emissiveColor = new Color3(0.7, 0.75, 0.8);
		debugStone.backFaceCulling = false;
	}
	addWind(canopyMaterial, scene, natureClock, 0.13, 0, 0.9);
	// Match specific flower variants before their common prefix.
	const cellMaterials: Array<[string, PBRMaterial | StandardMaterial]> = [
		["grass_ground", terrainMaterial],
		["stone_foundation", stoneMaterial],
		["timber_dark", timberMaterial],
		...(legacyLeaves ? [["world_tree_bark", legacyTreeBark()], ["world_leaf_cards", legacyLeaves.material]] as Array<[string, PBRMaterial | StandardMaterial]> : []),
		["world_cell_grass", materials.grassLight],
		["world_leaf_green", canopyMaterial],
		["world_cell_flower_center", materials.flowerGold],
		["world_cell_flower_rose", materials.flowerPink],
		["world_cell_flower_cream", materials.flowerWhite],
		["world_cell_flower", materials.flowerGold],
		["magic_blue", materials.windmark],
		["metal_iron", materials.metal],
	];
	try {
		for (const cell of cells.filter((candidate) => candidate.walkable)) {
			const assetUrl = assets[cell.asset];
			if (!assetUrl) throw new Error(`No runtime asset is registered for terrain cell ${cell.id}.`);
			const loaded = await SceneLoader.ImportMeshAsync("", "", assetUrl, scene);
			alignWorldAuthoredGlb(loaded, scene);
			const meshes = loaded.meshes.filter((mesh): mesh is Mesh => mesh instanceof Mesh && mesh.getTotalVertices() > 0);
			if (meshes.length === 0) throw new Error(`Terrain cell ${cell.id} contains no static meshes.`);
			for (const mesh of meshes) {
				const name = mesh.name.toLowerCase();
				if ((previewHeroOak && name.includes("hero_fallback"))
					|| (!legacyTrees && (name.includes("world_tree_bark") || name.includes("world_leaf_cards")))) {
					mesh.dispose(false, false);
					continue;
				}
				mesh.material = cellMaterials.find(([key]) => name.includes(key))?.[1] ?? materials.stone;
				if (debugStone && name.includes("stone_foundation")) mesh.material = debugStone;
				mesh.isPickable = false;
				// Dense overlapping leaf cards use a small diffuse fill; their cast shadows
				// still move with the gusts, without multiplying dark self-shadow layers.
				mesh.receiveShadows = true;
				mesh.isVisible = false;
				cellMeshes.push(mesh);
			}
		}
		for (const mesh of cellMeshes) await prepareCellMesh(mesh);
		if (shadowsEnabled) {
			for (const mesh of cellMeshes) {
				if (!mesh.name.toLowerCase().includes("grass_ground")) shadows.addShadowCaster(mesh, false);
			}
		}
		// C-P1-TREE: the kit trees join (shaders compiled) before the cells are revealed, so nothing pops in.
		if (!legacyTrees) {
			for (const cell of cells.filter((candidate) => candidate.walkable)) {
				await trees.add(sunmeadowCellTrees(worldProps, cell.id, previewHeroOak ? HERO_OAK_PROP_IDS : new Set()));
			}
		}
		for (const mesh of cellMeshes) mesh.isVisible = true;
		freezeStaticScenery(cellMeshes);
	} catch (error) {
		for (const mesh of cellMeshes) mesh.dispose(false, false);
		canopyMaterial.dispose();
		legacyLeaves?.material.dispose();
		legacyLeaves?.texture.dispose();
		throw error;
	}
}

function createGroundAndPath(
	scene: Scene,
	materials: Record<string, StandardMaterial>,
	rng: () => number,
	terrainMaterial: PBRMaterial,
	trailMaterial: PBRMaterial,
	natureClock: NatureClock,
	animation: Array<(time: number, deltaSeconds: number) => void>,
 	worldHalfExtent: number,
): void {
	// The canonical outdoor surface is flat across the square. Carry the art
	// under the city outskirts and the off-map toes so the skyline has no void.
	const backdropExtent = worldHalfExtent + 48;
	const horizonGround = MeshBuilder.CreateGround("env-world-base", {
		width: backdropExtent * 2, height: backdropExtent * 2, subdivisions: 32,
	}, scene);
	horizonGround.position.set(0, -0.002, 0);
	horizonGround.material = terrainMaterial;
	horizonGround.receiveShadows = true;
	horizonGround.isPickable = false;
	horizonGround.useVertexColors = true;
	applyWorldGroundAttributes(horizonGround);
	const ground = MeshBuilder.CreateGround("env-meadow", { width: 100, height: 100, subdivisions: 64 }, scene);
	ground.position.z = 8;
	ground.isPickable = false;
	ground.receiveShadows = true;
	ground.useVertexColors = true;
	ground.material = terrainMaterial;
	applyWorldGroundAttributes(ground);

	// A small connector closes the 22 m gap between the old field edge (Z=-42)
	// and the two authored flat terrain cells that begin at Z=-64.
	const connector = MeshBuilder.CreateGround("env-sunmeadow-south-connector", { width: 128, height: 22, subdivisions: 24 }, scene);
	connector.position.set(0, 0.001, -53);
	connector.isPickable = false;
	connector.receiveShadows = true;
	connector.useVertexColors = true;
	connector.material = terrainMaterial;
	applyWorldGroundAttributes(connector);

	// One gently bending trail replaces the stack of hard-edged path slabs. The same
	// road rises into a shallow bridge crown as it crosses the stream.
	const banks: [Vector3[], Vector3[]] = [[], []];
	for (let index = 0; index <= 147; index++) {
		// Carry the dirt road behind the spawn/camera so its near edge does not
		// begin as a sharp wedge beneath the adventurer.
		const z = -128 + index * 1.3;
		const center = Math.sin(z * 0.11) * 0.9;
		const taperStart = Math.max(0, Math.min(1, (z + 128) / 8));
		const taperEnd = Math.max(0, Math.min(1, (64 - z) / 4));
		const taper = Math.min(taperStart * taperStart * (3 - 2 * taperStart), taperEnd * taperEnd * (3 - 2 * taperEnd));
		// The painted road strip is opaque over ~72 % of its width (ragged grass shoulders are alpha-tested),
		// so the ribbon is widened to keep the old 3.0-3.8 m of walkable-looking dirt.
		const halfWidth = (1.5 + Math.max(0, Math.min(1, (z + 4) / 50)) * 0.42) * taper / ROAD_OPAQUE_FRACTION;
		const bridgeRise = Math.exp(-(((z - STREAM_Z) / 2.7) ** 2)) * 0.28;
		banks[0].push(new Vector3(center - halfWidth, 0.045 + bridgeRise, z));
		banks[1].push(new Vector3(center + halfWidth, 0.045 + bridgeRise, z));
	}
	const trail = MeshBuilder.CreateRibbon("env-meadow-trail", { pathArray: banks, sideOrientation: Mesh.DOUBLESIDE }, scene);
	applyRoadStripCoordinates(trail, banks, ROAD_REPEAT_METERS);
	trail.material = trailMaterial;
	trail.isPickable = false;
	trail.receiveShadows = true;

	// Stream and pale sandy banks.
	const waterBanks: [Vector3[], Vector3[]] = [[], []];
	const southBank: [Vector3[], Vector3[]] = [[], []];
	const northBank: [Vector3[], Vector3[]] = [[], []];
	for (let index = 0; index <= 72; index++) {
		const x = -36 + index;
		const centerZ = STREAM_Z + Math.sin(x * 0.11) * 0.48;
		waterBanks[0].push(new Vector3(x, 0.045, centerZ - STREAM_HALF_WIDTH));
		waterBanks[1].push(new Vector3(x, 0.045, centerZ + STREAM_HALF_WIDTH));
		southBank[0].push(new Vector3(x, 0.027, centerZ - STREAM_HALF_WIDTH - 0.2));
		southBank[1].push(new Vector3(x, 0.027, centerZ - STREAM_HALF_WIDTH - 1.05));
		northBank[0].push(new Vector3(x, 0.027, centerZ + STREAM_HALF_WIDTH + 0.2));
		northBank[1].push(new Vector3(x, 0.027, centerZ + STREAM_HALF_WIDTH + 1.05));
	}
	const water = materials.water.clone("env-stream-water")!;
	water.diffuseColor = Color3.FromHexString("#8ec8d2");
	water.specularColor = Color3.FromHexString("#e7fbff");
	water.specularPower = 96;
	water.alpha = 0.93;
	const waterGrid: Vector3[][] = [];
	for (let row = 0; row <= 12; row++) {
		const rowPoints: Vector3[] = [];
		for (let column = 0; column <= 72; column++) {
			rowPoints.push(Vector3.Lerp(waterBanks[0][column], waterBanks[1][column], row / 12));
		}
		waterGrid.push(rowPoints);
	}
	const stream = MeshBuilder.CreateRibbon("env-stream", { pathArray: waterGrid, sideOrientation: Mesh.DOUBLESIDE }, scene);
	addWaterWaves(water, natureClock);
	const waterTexture = createWaterTexture(scene);
	waterTexture.uScale = 1.2;
	waterTexture.vScale = 12;
	water.diffuseTexture = waterTexture;
	stream.material = water;
	stream.isPickable = false;
	animation.push((_time, delta) => {
		waterTexture.uOffset = (waterTexture.uOffset + Math.min(delta, 0.08) * 0.018) % 1;
		waterTexture.vOffset = (waterTexture.vOffset - Math.min(delta, 0.08) * 0.007) % 1;
	});
	const sand = new StandardMaterial("env-sandy-banks", scene);
	sand.diffuseColor = Color3.FromHexString("#b9aa82");
	sand.specularColor = Color3.FromHexString("#6f674f");
	for (const side of [-1, 1]) {
		const edges = side === -1 ? southBank : northBank;
		const bank = MeshBuilder.CreateRibbon(`env-bank-${side}`, { pathArray: edges, sideOrientation: Mesh.DOUBLESIDE }, scene);
		bank.material = sand;
		bank.isPickable = false;
	}

	// Short timber rails frame the ford where the road crosses the stream.
	const bridgeCenterX = Math.sin(STREAM_Z * 0.11) * 0.9;
	for (const side of [-1, 1]) {
		const rail = MeshBuilder.CreateBox("env-bridge-rail-" + side, { width: 0.14, height: 0.15, depth: 5.0 }, scene);
		rail.position.set(bridgeCenterX + side * 2.38, 0.78, STREAM_Z);
		rail.material = materials.woodLight;
		rail.isPickable = false;
		for (const z of [STREAM_Z - 2.1, STREAM_Z, STREAM_Z + 2.1]) {
			const post = MeshBuilder.CreateBox("env-bridge-post-" + side + "-" + z, { width: 0.19, height: 1.05, depth: 0.19 }, scene);
			post.position.set(bridgeCenterX + side * 2.38, 0.52, z);
			post.material = materials.wood;
			post.isPickable = false;
		}
	}

	// Small stones along the path edges.
	const rockMaster = MeshBuilder.CreateSphere("env-stone-master", { diameter: 0.5, segments: 4 }, scene);
	rockMaster.convertToFlatShadedMesh();
	rockMaster.material = materials.stone;
	rockMaster.isVisible = false;
	rockMaster.isPickable = false;
	for (let index = 0; index < 26; index++) {
		const stone = rockMaster.createInstance(`env-path-stone-${index}`);
		const side = rng() < 0.5 ? -1 : 1;
		const z = -6 + rng() * 40;
		stone.position.set(side * (PATH_HALF_WIDTH + 0.5 + rng() * 1.2), 0.1 + rng() * 0.05, z);
		stone.rotation.set(rng() * Math.PI, rng() * Math.PI, 0);
		stone.scaling.setAll(0.5 + rng() * 0.9);
		stone.isPickable = false;
	}
}

function createMasonryTexture(scene: Scene): DynamicTexture {
	const texture = new DynamicTexture("env-limestone-detail-texture", { width: 256, height: 256 }, scene, false);
	const context = texture.getContext() as CanvasRenderingContext2D;
	context.fillStyle = "#fffdf3";
	context.fillRect(0, 0, 256, 256);
	for (let row = -1; row < 6; row++) {
		for (let column = -1; column < 6; column++) {
			const x = column * 52 + (row % 2) * 26;
			const y = row * 48;
			const tone = 0.96 + ((row * 3 + column * 5) % 4) * 0.01;
			context.fillStyle = `rgba(190,180,153,${1 - tone})`;
			context.fillRect(x + 2, y + 2, 49, 45);
			context.strokeStyle = "rgba(79,74,61,0.15)";
			context.lineWidth = 1.4;
			context.strokeRect(x + 1, y + 1, 51, 47);
			context.strokeStyle = "rgba(255,255,244,0.7)";
			context.beginPath();
			context.moveTo(x + 4, y + 4);
			context.lineTo(x + 48, y + 4);
			context.stroke();
		}
	}
	for (let index = 0; index < 360; index++) {
		const x = (index * 73) % 256;
		const y = (index * 139) % 256;
		context.fillStyle = index % 2 ? "rgba(88,81,65,0.08)" : "rgba(255,255,244,0.12)";
		context.fillRect(x, y, 1 + index % 3, 1 + (index >> 2) % 2);
	}
	texture.update();
	texture.wrapU = Texture.WRAP_ADDRESSMODE;
	texture.wrapV = Texture.WRAP_ADDRESSMODE;
	return texture;
}

function createLeafTexture(scene: Scene): DynamicTexture {
	const texture = new DynamicTexture("env-leaf-detail-texture", { width: 256, height: 256 }, scene, false);
	const context = texture.getContext() as CanvasRenderingContext2D;
	context.fillStyle = "#ffffff";
	context.fillRect(0, 0, 256, 256);
	let seed = 773204;
	const random = () => {
		seed = (seed * 1664525 + 1013904223) >>> 0;
		return seed / 0x1_0000_0000;
	};
	for (let index = 0; index < 1800; index++) {
		const hue = 77 + Math.floor(random() * 44);
		const saturation = 26 + Math.floor(random() * 34);
		const lightness = 36 + Math.floor(random() * 36);
		context.fillStyle = `hsla(${hue}, ${saturation}%, ${lightness}%, 0.3)`;
		const x = random() * 256;
		const y = random() * 256;
		context.beginPath();
		context.ellipse(x, y, 1.3 + random() * 2.5, 0.7 + random() * 1.4, random() * Math.PI, 0, Math.PI * 2);
		context.fill();
	}
	texture.update();
	texture.wrapU = Texture.WRAP_ADDRESSMODE;
	texture.wrapV = Texture.WRAP_ADDRESSMODE;
	return texture;
}

function createWaterTexture(scene: Scene): DynamicTexture {
	const texture = new DynamicTexture("env-stream-texture", { width: 512, height: 512 }, scene, false);
	const context = texture.getContext() as CanvasRenderingContext2D;
	const gradient = context.createLinearGradient(0, 0, 512, 512);
	gradient.addColorStop(0, "#5c9eae");
	gradient.addColorStop(0.45, "#76b8c3");
	gradient.addColorStop(1, "#477f96");
	context.fillStyle = gradient;
	context.fillRect(0, 0, 512, 512);
	let seed = 17062026;
	const random = () => {
		seed = (seed * 1664525 + 1013904223) >>> 0;
		return seed / 0x1_0000_0000;
	};
	for (let row = 0; row < 48; row++) {
		const y = row * 12 + random() * 8;
		context.beginPath();
		context.moveTo(0, y);
		context.bezierCurveTo(140, y + random() * 8, 370, y - random() * 7, 512, y + random() * 5);
		context.strokeStyle = row % 3 === 0 ? "rgba(233,250,242,0.28)" : "rgba(30,78,97,0.13)";
		context.lineWidth = row % 3 === 0 ? 1.6 : 1;
		context.stroke();
	}
	for (let index = 0; index < 220; index++) {
		context.fillStyle = random() > 0.5 ? "rgba(233,249,236,0.3)" : "rgba(22,73,98,0.18)";
		context.beginPath();
		context.ellipse(random() * 512, random() * 512, 1 + random() * 6, 0.8 + random() * 2, 0, 0, Math.PI * 2);
		context.fill();
	}
	texture.update();
	texture.wrapU = Texture.WRAP_ADDRESSMODE;
	texture.wrapV = Texture.WRAP_ADDRESSMODE;
	return texture;
}

/** Layered sine pseudo-noise in [0, 1] with per-vertex jitter. */
function groundVariation(x: number, z: number): number {
	const value =
		0.55 +
		0.14 * Math.sin(x * 0.17 + 1.7) * Math.cos(z * 0.15) +
		0.08 * Math.sin(x * 0.36 - z * 0.26 + 3.1) +
		0.03 * Math.cos(x * 0.68 + z * 0.52);
	return Math.min(1, Math.max(0, value));
}

function lerp(a: number, b: number, t: number): number {
	return a + (b - a) * t;
}


/** Keep the compact meadow proxy resident and request the full R5 city only
 * after an authoritative/local position crosses the authored gate. */
async function upgradeKeepAndTrees(
	scene: Scene,
	proceduralKeep: TransformNode,
	proceduralTrees: TransformNode,
	cityGateZ: number,
	getShadows: () => ShadowGenerator,
	shadowsEnabled: boolean,
	prepareDetailedCity: (mesh: Mesh) => Promise<void>,
	natureClock: NatureClock,
	legacyBark: () => PBRMaterial,
	getWaterDetail: () => number,
	trees: SunmeadowTrees,
	getGroundHeight: (x:number,z:number)=>number|null,
): Promise<(() => Promise<void>) & { getState(): "idle" | "loading" | "prepared" | "ready" | "failed"; reveal(): void; getWaterStats(): ReturnType<typeof createCityFountain>['stats'] }> {
	let hlodMesh: Mesh | null = null;
	let preparedMesh: Mesh | null = null;
	let gateTreeCandidate: ReturnType<typeof prepareGateCityTreeCandidate> | null = null;
	let gateTreeAdded = false;
	let cityLampPools: ReturnType<typeof createCityLampPools> | null = null;
	const fountain = createCityFountain(scene, cityGateZ + 152, natureClock);
	fountain.setDetail(getWaterDetail());
	const fountainQuality = scene.onBeforeRenderObservable.add(() => fountain.setDetail(getWaterDetail()));
	scene.onDisposeObservable.addOnce(() => scene.onBeforeRenderObservable.remove(fountainQuality));
	try {
		const arrivalVersion = import.meta.env.DEV ? new URLSearchParams(location.search).get('cityArrival') : null;
		const arrivalReview = arrivalVersion === 'r01' || arrivalVersion === 'r02' || arrivalVersion === 'r03';
		const hlodUrl = arrivalVersion === 'r03' ? arrivalHlodReviewR03Url : arrivalVersion === 'r02' ? arrivalHlodReviewR02Url : arrivalReview ? arrivalHlodReviewUrl : keepHlodAssetUrl;
		const loadedHlod = await SceneLoader.ImportMeshAsync("", "", hlodUrl, scene);
		if (!loadedHlod.meshes.some((mesh) => mesh instanceof Mesh && mesh.getTotalVertices() > 0)) {
			throw new Error("Meadow HLOD has no static geometry.");
		}
		for (const mesh of loadedHlod.meshes) {
			if (!(mesh instanceof Mesh) || mesh.getTotalVertices() === 0) continue;
			mesh.isPickable = false;
			mesh.receiveShadows = true;
		}
		hlodMesh = mergeStaticModel(loadedHlod, "reference-city-hlod-merged");
		hlodMesh.metadata = { ...hlodMesh.metadata, arrivalHlod: arrivalReview ? `${arrivalVersion}-unadmitted` : 'baseline',
			assetSha256: arrivalVersion === 'r03' ? 'fd7ec28b2302c5658988c78dd0234780356c00fe141a5568585490cf1a536111'
				: arrivalVersion === 'r02' ? 'dc17f36aa72c3b4d8427cc50fc993ab993914b6f296b80ad7776e9d7167d520c'
				: arrivalReview ? '8aaa42a1ab65900d25ba46845cf02c8cd9f77139ab3b7c1914f44a040c0dae1c'
				: '771fdf2bc450c3df2cc937f231176145d9d27bfae7772b616298a0dd063038b5' };
		hlodMesh.receiveShadows = true;
		hlodMesh.isVisible = true;
		const hlodRoot = new TransformNode("reference-city-hlod", scene);
		hlodMesh.parent = hlodRoot;
		hlodRoot.position.set(0, 0, cityGateZ + 152);
		hlodRoot.rotation.y = Math.PI;
		freezeStaticScenery([hlodMesh]);
		if (shadowsEnabled) getShadows().addShadowCaster(hlodMesh, false);
		proceduralKeep.dispose(false, false);
		recordCityRepresentationPhase(scene, 'approach');
	} catch (error) {
		console.warn("City meadow HLOD unavailable; procedural keep stays visible.", error);
	}

	const ensureCity = createStagedCityLoader(async () => {
		// Container loading keeps raw, unpositioned meshes out of the live scene.
		const reviewGuardian = import.meta.env.DEV ? new URLSearchParams(location.search).get('cityArtCandidate') : null;
		const selectedUrl = reviewGuardian === 'guardian-r03' ? guardianMaterialR03Url : reviewGuardian === 'forge-r6' ? forgeR6ReviewAssetUrl : reviewGuardian === 'guardian-v2' ? guardianReviewV2AssetUrl : reviewGuardian === 'guardian-v1' ? guardianReviewAssetUrl : keepAssetUrl;
		// C-MAPDRESS-R6 begin: DEV-only ?city=r6 previews the r6 dressing candidate (visual only; traversal/colliders stay r5)
		const cityR6Preview = import.meta.env.DEV && new URLSearchParams(location.search).get('city') === 'r6';
		if (cityR6Preview) console.info('[city] r6 dressing candidate preview (not admitted)');
		const loadedCity = await SceneLoader.LoadAssetContainerAsync("", cityR6Preview ? cityR6CandidateAssetUrl : selectedUrl, scene);
		// C-MAPDRESS-R6 end
		if (scene.isDisposed) { loadedCity.dispose(); throw new Error("City scene was disposed while loading"); }
		let candidateRoot: TransformNode | null = null;
		let cityLighting: ReturnType<typeof bindCityMaterialLighting> | null = null;
		try {
		for (const mesh of loadedCity.meshes) mesh.isVisible = false;
		loadedCity.addAllToScene();
		if (!loadedCity.meshes.some((mesh) => mesh instanceof Mesh && mesh.getTotalVertices() > 0)) {
			throw new Error("Detailed R5 city has no static geometry.");
		}
		for (const mesh of loadedCity.meshes) {
			if (!(mesh instanceof Mesh) || mesh.getTotalVertices() === 0) continue;
			mesh.receiveShadows = true;
			mesh.isPickable = false;
		}
		// Review only: retire the witnessed ball-canopy tree after its existing CC0 kit loads.
		const gateTreeReview = import.meta.env.DEV && new URLSearchParams(location.search).get('dressing') === 'v3'
			&& cityGateZ === 24 && !cityR6Preview && selectedUrl === keepAssetUrl;
		if (gateTreeReview && await trees.ready) {
			try {
				gateTreeCandidate = prepareGateCityTreeCandidate(loadedCity, GATE_CITY_TREE.runtimeSha256);
				scene.metadata = { ...scene.metadata, gateCityTreeCandidate: { status: 'PREPARED', ...gateTreeCandidate,
					pinnedRuntimeSha256: GATE_CITY_TREE.runtimeSha256, oldHeight: GATE_CITY_TREE.oldHeight,
					replacementHeight: GATE_CITY_TREE.replacementHeight, physics: 'UNCHANGED' } };
			} catch (error) {
				console.warn('[city] gate tree guard failed; original geometry retained', error);
			}
		}
		const detailedMesh = mergeStaticModel(loadedCity, "reference-city-merged");
		if (reviewGuardian === 'guardian-r03' && !cityR6Preview) detailedMesh.metadata = {...detailedMesh.metadata,
			cityArtCandidate: 'guardian-r03-unadmitted', assetSha256: 'a8a8182e83a4ba6deefa38f223e3709a198770eef1981f33870b22b8d5d8cc7b',
			triangleBudgetPassed: false, geometryDonor: 'guardian-v2'};
		detailedMesh.receiveShadows = true;
		detailedMesh.isVisible = false;
		const detailedRoot = new TransformNode("reference-city-detail", scene);
		candidateRoot = detailedRoot;
		detailedMesh.parent = detailedRoot;
		detailedRoot.position.set(0, 0, cityGateZ + 152);
		detailedRoot.rotation.y = Math.PI;
		cityLighting = bindCityMaterialLighting(scene, detailedMesh, () => getShadows().getLight().intensity);
		if(import.meta.env.DEV && new URLSearchParams(location.search).get('look')==='v2' && !cityR6Preview) {
			cityLampPools=createCityLampPools(scene,cityGateZ+152,getGroundHeight);
			await cityLampPools.ready;
		}
		const removedWaterFaces = removeFountainPlaceholders(detailedMesh, cityGateZ + 152);
		if (import.meta.env.DEV && new URLSearchParams(location.search).get('debugFountain') === '1') console.info('Fountain placeholder faces removed', removedWaterFaces, detailedMesh.subMeshes.map(sub => ({material:sub.getMaterial()?.name,indices:sub.indexCount})).filter(sub=>/water|foam|magic/.test(sub.material ?? '')));
		// Compile the full materials while the small HLOD remains on screen.
		await prepareDetailedCity(detailedMesh);
		await fountain.ready;
		const warmed = new Set<Material>();
		for (const mesh of fountain.meshes) if (mesh.material && !warmed.has(mesh.material)) {
			await mesh.material.forceCompilationAsync(mesh); warmed.add(mesh.material);
		}
		if (scene.isDisposed) throw new Error("City scene was disposed while preparing");
		const waterDeadline = performance.now()+10000;
		while(!fountain.particleSystems.every(system=>system.isReady())) {
			if(scene.isDisposed || performance.now()>waterDeadline)throw new Error('Native water particle effects did not become GPU-ready.');
			await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
		}
		preparedMesh = detailedMesh;
		recordCityRepresentationPhase(scene, 'prepared');
		return;
		} catch (error) {
			cityLighting?.dispose();
		cityLampPools?.dispose();cityLampPools=null;
			candidateRoot?.dispose(false, true);
			loadedCity.dispose();
			throw error;
		}
	}, () => {
		if (!preparedMesh || scene.isDisposed) throw new Error("Prepared city is no longer available");
		if (shadowsEnabled) getShadows().addShadowCaster(preparedMesh, false);
		preparedMesh.isVisible = true;
		cityLampPools?.reveal();
		if (gateTreeCandidate && !gateTreeAdded) {
			gateTreeAdded = true;
			void trees.add([gateTreeCandidate.placement]).then(() => {
				if (!scene.isDisposed) scene.metadata.gateCityTreeCandidate.status = 'REVEALED';
			}).catch(error => {
				if (!scene.isDisposed) scene.metadata.gateCityTreeCandidate.status = 'FAILED';
				console.error('[city] gate tree candidate registration failed', error);
			});
		}
		freezeStaticScenery([preparedMesh]);
		fountain.reveal();
		if (hlodMesh) {
			hlodMesh.isVisible = false;
			if (shadowsEnabled) getShadows().removeShadowCaster(hlodMesh, false);
		}
		if (!proceduralKeep.isDisposed()) proceduralKeep.dispose(false, false);
		recordCityRepresentationPhase(scene, 'revealed');
	});

	// C-P1-TREE: the 12 TREE_SPOTS field trees come from the sunmeadow-trees-v4 kit (same visual anchors). The
	// home-made GLB trees below stay as the fallback when the kit cannot load, then the procedural trees.
	try {
		if (await trees.ready) {
			await trees.add(sunmeadowFieldTrees());
			proceduralTrees.dispose(false, false);
			return Object.assign(ensureCity, {getWaterStats: () => fountain.stats});
		}
	} catch (error) {
		console.warn("Sunmeadow tree kit could not be placed; the home-made fallback trees load instead.", error);
	}
	try {
		const loadedTrees = await SceneLoader.ImportMeshAsync("", "", meadowTreeAssetUrl, scene);
		const variantKits = TREE_VARIANTS.map((variant) => ({
			trunk: loadedTrees.meshes.find((mesh) => mesh.name === `tree_${variant}_trunk`) as Mesh | undefined,
			canopy: loadedTrees.meshes.find((mesh) => mesh.name === `tree_${variant}_canopy`) as Mesh | undefined,
		}));
		const usable = variantKits.filter((kit) => kit.trunk instanceof Mesh && kit.canopy instanceof Mesh);
		if (usable.length > 0) {
			const leafMaterial = createLeafCardMaterial(scene, "env-field-leaf-cards", natureClock).material;
			for (const kit of usable) {
				// Bake the asset-local import transform before assigning world positions
				// to instances; otherwise the importer root mirrors their placement.
				const trunk = mergeStaticModel({ meshes: [kit.trunk as Mesh], transformNodes: [], animationGroups: [] }, "field-tree-trunk");
				const canopy = mergeStaticModel({ meshes: [kit.canopy as Mesh], transformNodes: [], animationGroups: [] }, "field-tree-canopy");
				kit.trunk = trunk;
				kit.canopy = canopy;
				trunk.isVisible = false;
				canopy.isVisible = false;
				trunk.isPickable = false;
				canopy.isPickable = false;
				trunk.material = legacyBark();
				trunk.receiveShadows = true;
				canopy.material = leafMaterial;
			}
			TREE_SPOTS.forEach(([x, z, height], index) => {
				const kit = usable[index % usable.length];
				const trunk = kit.trunk as Mesh;
				const canopy = kit.canopy as Mesh;
				const variantHeight = { A: 7.0, B: 5.6, C: 8.6 }[TREE_VARIANTS[index % TREE_VARIANTS.length]];
				const scale = Math.max(0.8, Math.min(1.25, height / variantHeight));
				const trunkInstance = trunk.createInstance(`glb-tree-trunk-${index}`);
				trunkInstance.position.set(x, 0, z);
				trunkInstance.scaling.setAll(scale);
				trunkInstance.rotation.y = index * 1.3;
				trunkInstance.isPickable = false;
				const canopyInstance = canopy.createInstance(`glb-tree-canopy-${index}`);
				canopyInstance.position.set(x, 0, z);
				canopyInstance.scaling.setAll(scale);
				canopyInstance.rotation.y = index * 1.3;
				canopyInstance.isPickable = false;
				if (shadowsEnabled) {
					getShadows().addShadowCaster(trunkInstance, false);
					getShadows().addShadowCaster(canopyInstance, false);
				}
			});
			// Wind sways these in the vertex shader; their transforms never change.
			freezeStaticScenery(usable.flatMap((kit) => [kit.trunk as Mesh, kit.canopy as Mesh, ...(kit.trunk as Mesh).instances, ...(kit.canopy as Mesh).instances]));
			for (const mesh of loadedTrees.meshes) {
				if (!mesh.isDisposed() && mesh.getTotalVertices() === 0) mesh.dispose(false, false);
			}
			proceduralTrees.dispose(false, false);
		}
	} catch (error) {
		console.warn("GLB foliage kit unavailable; procedural trees stay.", error);
	}
	return Object.assign(ensureCity, {getWaterStats: () => fountain.stats});
}

function createCastle(scene: Scene, materials: Record<string, StandardMaterial>): TransformNode {
	const baseZ = 62;
	const casters: Mesh[] = [];
	const root = new TransformNode("procedural-keep", scene);
	const add = (mesh: Mesh, material: StandardMaterial, caster = true): Mesh => {
		mesh.material = material;
		mesh.parent = root;
		mesh.isPickable = false;
		if (caster) casters.push(mesh);
		return mesh;
	};

	const opening = 8.5;
	const wallWidth = 38;
	const wallHeight = 8.4;
	const sectionWidth = (wallWidth - opening) / 2;
	for (const side of [-1, 1]) {
		const sectionName = "env-castle-wall-" + side;
		const section = add(MeshBuilder.CreateBox(sectionName, { width: sectionWidth, height: wallHeight, depth: 2.4 }, scene), materials.wall);
		section.position.set(side * (opening / 2 + sectionWidth / 2), wallHeight / 2, baseZ);
		const pierName = "env-castle-gate-pier-" + side;
		const pier = add(MeshBuilder.CreateBox(pierName, { width: 0.85, height: 4.1, depth: 2.9 }, scene), materials.wallLight);
		pier.position.set(side * (opening / 2 + 0.45), 2.05, baseZ - 0.15);
	}
	// Build the wall around the opening: the route must read as a passage,
	// with masonry above its arch and no central tower standing in the doorway.
	const archCeiling: Vector3[] = [];
	const archWallTop: Vector3[] = [];
	for (let index = 0; index <= 32; index++) {
		const x = -opening / 2 + (index / 32) * opening;
		const y = 2.1 + Math.sqrt(Math.max(0, 1 - (x / (opening / 2)) ** 2)) * 4.1;
		archCeiling.push(new Vector3(x, y, baseZ - 1.2));
		archWallTop.push(new Vector3(x, wallHeight, baseZ - 1.2));
	}
	add(MeshBuilder.CreateRibbon("env-gate-spandrel", { pathArray: [archCeiling, archWallTop], sideOrientation: Mesh.DOUBLESIDE }, scene), materials.wall);
	const vaultBack = archCeiling.map((point) => new Vector3(point.x, point.y, baseZ + 2.5));
	add(MeshBuilder.CreateRibbon("env-gate-vault", { pathArray: [archCeiling, vaultBack], sideOrientation: Mesh.DOUBLESIDE }, scene), materials.wall);
	// A continuous raised arch gives the gate a carved masonry silhouette.
	const archPath: Vector3[] = [];
	const innerArchPath: Vector3[] = [];
	for (let index = 0; index <= 24; index++) {
		const angle = Math.PI - index * Math.PI / 24;
		const x = Math.cos(angle) * 4.25;
		const y = 2.1 + Math.sin(angle) * 4.1;
		archPath.push(new Vector3(x, y, baseZ - 1.55));
		innerArchPath.push(new Vector3(x, y - 0.36, baseZ - 1.58));
	}
	add(MeshBuilder.CreateTube("env-castle-gate-arch", { path: archPath, radius: 0.42, tessellation: 10 }, scene), materials.wallLight);
	add(MeshBuilder.CreateTube("env-castle-gate-inner-moulding", { path: innerArchPath, radius: 0.075, tessellation: 8 }, scene), materials.metal, false);
	const gate = MeshBuilder.CreateBox("env-castle-gate-shadow", { width: 8.35, height: 7.4, depth: 0.12 }, scene);
	gate.position.set(0, 3.7, baseZ + 1.25);
	const gateMaterial = new StandardMaterial("env-gate-shadow-material", scene);
	gateMaterial.diffuseColor = Color3.FromHexString("#17252c");
	gateMaterial.emissiveColor = Color3.FromHexString("#080e12");
	gateMaterial.specularColor = Color3.Black();
	add(gate, gateMaterial, false);
	const masonryMasters = [
		MeshBuilder.CreateBox("env-masonry-a", { width: 1.55, height: 0.76, depth: 0.1 }, scene),
		MeshBuilder.CreateBox("env-masonry-b", { width: 1.55, height: 0.76, depth: 0.1 }, scene),
	];
	masonryMasters[0].material = materials.wallLight;
	masonryMasters[1].material = materials.wall;
	for (const master of masonryMasters) {
		master.parent = root;
		master.isVisible = false;
		master.isPickable = false;
	}
	for (const side of [-1, 1]) {
		for (let row = 0; row < 5; row++) {
			for (let column = 0; column < 8; column++) {
				const x = side < 0 ? -18.2 + column * 1.72 + (row % 2) * 0.42 : 5.0 + column * 1.72 + (row % 2) * 0.42;
				const blockName = "env-wall-block-" + side + "-" + row + "-" + column;
				const block = masonryMasters[(row + column) % masonryMasters.length].createInstance(blockName);
				block.parent = root;
				block.position.set(x, 0.95 + row * 1.42, baseZ - 1.28);
				block.isPickable = false;
			}
		}
		for (const x of (side < 0 ? [-16, -12, -8] : [8, 12, 16])) {
			for (const y of [3.5, 6.3]) {
				const slit = add(MeshBuilder.CreateBox("env-wall-window-" + side + "-" + x + "-" + y, { width: 0.3, height: 0.78, depth: 0.08 }, scene), materials.window, false);
				slit.position.set(x, y, baseZ - 1.31);
			}
		}
	}

	for (let x = -18; x <= 18; x += 3) {
		if (Math.abs(x) < 6) continue;
		const merlon = add(MeshBuilder.CreateBox(`env-castle-merlon-${x}`, { width: 1.35, height: 1.25, depth: 2.65 }, scene), materials.wallLight);
		merlon.position.set(x, 8.95, baseZ);
	}

	// Paired gatehouses establish the entrance; distant towers vary in height
	// instead of repeating five identical pointed roofs across the facade.
	for (const [index, x, height] of [[0, -18, 13.5], [1, -6.7, 10.5], [2, 6.7, 10.5], [3, 18, 15]] as const) {
		const z = baseZ + 0.5;
		const tower = add(MeshBuilder.CreateCylinder(`env-castle-tower-${index}`, { height, diameter: 4.4, tessellation: 16 }, scene), materials.wall);
		tower.position.set(x, height / 2 + 0.3, z);
		for (const bandY of [0.5, height - 0.2]) {
			const band = add(MeshBuilder.CreateCylinder(`env-castle-cornice-${index}-${bandY}`, { height: 0.35, diameter: 4.8, tessellation: 16 }, scene), materials.wallLight);
			band.position.set(x, bandY, z);
		}
		const roofHeight = index === 1 || index === 2 ? 2.4 : 3.7;
		const roof = add(MeshBuilder.CreateCylinder(`env-castle-roof-${index}`, { height: roofHeight, diameterTop: 0.18, diameterBottom: 5.1, tessellation: 16 }, scene), materials.roof);
		roof.position.set(x, height + roofHeight / 2 + 0.3, z);
		for (const y of [3.3, 6.7, 9.4]) {
			if (y >= height - 1) continue;
			const slit = MeshBuilder.CreateBox(`env-castle-window-${index}-${y}`, { width: 0.38, height: 1.15, depth: 0.12 }, scene);
			slit.position.set(x, y, z - 2.42);
			add(slit, materials.window, false);
		}
	}

	const keep = add(MeshBuilder.CreateBox("env-castle-keep", { width: 15, height: 12, depth: 10 }, scene), materials.wall);
	keep.position.set(-3, 9, baseZ + 15);
	for (const [index, x] of [-10, -3, 5].entries()) {
		const turret = add(MeshBuilder.CreateCylinder(`env-castle-turret-${index}`, { height: 7 + (index % 2) * 2, diameter: 2.8, tessellation: 8 }, scene), materials.wallLight);
		turret.position.set(x, 16 + (index % 2), baseZ + 13 + index * 2);
		const turretRoof = add(MeshBuilder.CreateCylinder(`env-castle-turret-roof-${index}`, { height: 3, diameterTop: 0, diameterBottom: 3.8, tessellation: 8 }, scene), materials.roof);
		turretRoof.position.set(x, 21.5 + (index % 2), baseZ + 13 + index * 2);
	}
	for (const side of [-1, 1]) {
		const banner = add(MeshBuilder.CreateBox(`env-castle-banner-${side}`, { width: 1.8, height: 4.2, depth: 0.13 }, scene), materials.flag, false);
		banner.position.set(side * 7.1, 5.4, baseZ - 1.6);
		const trim = add(MeshBuilder.CreateBox(`env-castle-banner-trim-${side}`, { width: 0.12, height: 4.4, depth: 0.2 }, scene), materials.metal, false);
		trim.position.set(side * 6.8, 5.4, baseZ - 1.7);
	}
	return root;
}

function createDistantMountains(scene: Scene, worldHalfExtent: number): Mesh[] {
	const created: Mesh[] = [];
	// Broad connected ridges keep the horizon natural. Each range is one mesh;
	// height variation and vertex tint replace glossy, isolated cone peaks.
	const ranges = [
		{ z: worldHalfExtent + 88, depth: 28, height: 62, color: "#a2b7c7", phase: 0.9 },
		{ z: worldHalfExtent + 56, depth: 24, height: 45, color: "#829dae", phase: 2.8 },
		{ z: worldHalfExtent + 22, depth: 20, height: 27, color: "#6d8c8f", phase: 4.7 },
		{ z: -worldHalfExtent - 80, depth: 28, height: 72, color: "#a2b7c7", phase: 1.8 },
		{ z: -worldHalfExtent - 48, depth: 24, height: 48, color: "#829dae", phase: 3.6 },
		{ z: -worldHalfExtent - 20, depth: 20, height: 32, color: "#6d8c8f", phase: 5.4 },
	];
	for (const [index, range] of ranges.entries()) {
		const rows: Vector3[][] = [];
		for (let row = 0; row <= 8; row++) {
			const depthFraction = row / 8;
			const slope = Math.sin(depthFraction * Math.PI);
			const path: Vector3[] = [];
			for (let column = 0; column <= 80; column++) {
				const x = -91 + column * 2.275;
				const broad = 0.62 + Math.sin(x * 0.063 + range.phase) * 0.17;
				const broken = Math.sin(x * 0.17 + range.phase * 2) * 0.11 + Math.sin(x * 0.37 - range.phase) * 0.045;
				const shoulder = Math.sin(x * 0.10 + depthFraction * 3 + range.phase) * 0.04;
				const centerValley = 1 - 0.22 * Math.exp(-((x / 23) ** 2));
				const height = range.height * (broad + broken + shoulder) * Math.pow(slope, 0.78) * centerValley;
				path.push(new Vector3(x * (worldHalfExtent * 1.15 / 91), height - 2, range.z + (depthFraction - 0.5) * range.depth));
			}
			rows.push(path);
		}
		const ridge = MeshBuilder.CreateRibbon(`env-mountain-range-${index}`, { pathArray: rows, sideOrientation: Mesh.DOUBLESIDE }, scene);
		const material = new StandardMaterial(`env-mountain-range-material-${index}`, scene);
		material.diffuseColor = Color3.White();
		material.specularColor = Color3.Black();
		material.emissiveColor = Color3.FromHexString(range.color).scale(0.16);
		ridge.material = material;
		created.push(ridge);
		ridge.isPickable = false;
		ridge.useVertexColors = true;
		const positions = ridge.getVerticesData(VertexBuffer.PositionKind);
		if (positions) {
			const base = Color3.FromHexString(range.color);
			const colors: number[] = [];
			for (let vertex = 0; vertex < positions.length; vertex += 3) {
				const height = positions[vertex + 1];
				const variation = 0.84 + Math.sin(positions[vertex] * 0.24 + positions[vertex + 2] * 0.2) * 0.06 + height / range.height * 0.2;
				colors.push(base.r * variation, base.g * variation, base.b * variation, 1);
			}
			ridge.setVerticesData(VertexBuffer.ColorKind, colors);
		}
	}
	return created;
}

function createFencesAndHills(scene: Scene, materials: Record<string, StandardMaterial>): void {
	for (const side of [-1, 1]) {
		for (let z = -4; z < 12; z += 1.9) {
			const post = MeshBuilder.CreateBox(`env-fence-post-${side}-${z}`, { width: 0.22, height: 1.15, depth: 0.22 }, scene);
			post.position.set(side * (5.3 + Math.sin(z * 0.2) * 0.4), 0.56, z);
			post.material = materials.wood;
			post.isPickable = false;
		}
		for (const y of [0.45, 0.88]) {
			const rail = MeshBuilder.CreateBox(`env-fence-rail-${side}-${y}`, { width: 0.16, height: 0.16, depth: 16 }, scene);
			rail.position.set(side * 5.35, y, 3.4);
			rail.material = materials.woodLight;
			rail.isPickable = false;
		}
	}
	// S07: authored border mountains supersede all six legacy submerged hill spheres.
}

async function createKenneyFoliage(scene: Scene): Promise<void> {
	const bush = await importKenneyNatureMesh(scene, "plant-bush-detailed", kenneyBushAssetUrl, "#6c9848", "#6c9848");
	if (bush) {
		for (const [index, [x, z]] of ([[-9, 11], [9, 12], [-8, 27], [10, 29], [-14, 38], [15, 39]] as const).entries()) {
			const instance = bush.createInstance(`kenney-bush-${index}`);
			instance.position.set(x, 0, z);
			instance.scaling.setAll(2.4 + (index % 3) * 0.35);
			instance.rotation.y = index * 1.1;
			instance.isPickable = false;
		}
	}

	const rockAssets = [
		["rock-large-a", kenneyRockLargeAAssetUrl],
		["rock-large-b", kenneyRockLargeBAssetUrl],
	] as const;
	for (const [rockIndex, [assetName, assetUrl]] of rockAssets.entries()) {
		const rock = await importKenneyNatureMesh(scene, assetName, assetUrl, "#687e49", "#8b8272");
		if (!rock) continue;
		for (const [index, [x, z]] of ([[-8, 8], [8, 9], [-9, 21], [9, 24], [-13, 33], [13, 35]] as const).entries()) {
			if (index % 2 !== rockIndex) continue;
			const instance = rock.createInstance(`kenney-rock-${rockIndex}-${index}`);
			instance.position.set(x, 0.15, z);
			instance.scaling.setAll(1.7 + (index % 3) * 0.25);
			instance.rotation.y = index * 0.73;
			instance.isPickable = false;
		}
	}
}

async function importKenneyNatureMesh(scene: Scene, assetName: string, assetUrl: string, leafColor: string, barkColor: string, accentColor = leafColor): Promise<Mesh | null> {
	const loaded = await SceneLoader.ImportMeshAsync("", "", assetUrl, scene);
	const mesh = mergeStaticModel(loaded, `nature-master-${assetName}`);
 applyNaturePalette(mesh.material, leafColor, barkColor, accentColor);
 return mesh;
}

function applyNaturePalette(sourceMaterial: Mesh["material"], leafColor: string, barkColor: string, accentColor: string): void {
	const materials = sourceMaterial instanceof MultiMaterial ? sourceMaterial.subMaterials : [sourceMaterial];
	for (const material of materials) {
		if (!(material instanceof PBRMaterial)) continue;
		const name = material.name.toLowerCase();
		const color = name.includes("wood") || name.includes("bark") || name.includes("dirt")
			? barkColor
			: name.includes("purple") || name.includes("yellow") || name.includes("flower")
				? accentColor
				: leafColor;
		material.albedoColor = Color3.FromHexString(color);
		material.metallic = 0;
		material.roughness = 0.94;
	}
}

const TREE_SPOTS: Array<[number, number, number]> = [
	[-18, 5, 7], [18, 7, 8], [-20, 17, 8], [20, 21, 9],
	[-25, 30, 9], [-12, 35, 7], [14, 35, 8], [27, 31, 9],
	[-22, -6, 7], [22, -4, 8], [-8, 40, 9], [9, 42, 8],
];
const TREE_VARIANTS = ["A", "B", "C"] as const;

function createTrees(scene: Scene, materials: Record<string, StandardMaterial>, rng: () => number): TransformNode {
	const trunk = MeshBuilder.CreateCylinder("env-tree-trunk-master", { height: 1, diameterTop: 0.45, diameterBottom: 0.8, tessellation: 7 }, scene);
	trunk.material = materials.wood;
	trunk.isVisible = false;
	trunk.isPickable = false;
	const branch = MeshBuilder.CreateCylinder("env-tree-branch-master", { height: 1, diameterTop: 0.12, diameterBottom: 0.29, tessellation: 6 }, scene);
	branch.material = materials.wood;
	branch.isVisible = false;
	branch.isPickable = false;
	const canopies = [
		MeshBuilder.CreateSphere("env-tree-crown-a", { diameter: 5.2, segments: 10 }, scene),
		MeshBuilder.CreateSphere("env-tree-crown-b", { diameter: 4.7, segments: 10 }, scene),
		MeshBuilder.CreateSphere("env-tree-crown-c", { diameter: 4.1, segments: 10 }, scene),
	];
	const crownMaterials = [materials.leaves, materials.leavesLight, materials.leavesGold];
	for (const [index, crown] of canopies.entries()) {
		crown.material = crownMaterials[index];
		crown.isVisible = false;
		crown.isPickable = false;
	}

	const root = new TransformNode("procedural-trees", scene);
	for (const [index, [x, z, height]] of TREE_SPOTS.entries()) {
		const trunkInstance = trunk.createInstance(`env-tree-trunk-${index}`);
		trunkInstance.parent = root;
		trunkInstance.position.set(x, (height * 0.9) / 2, z);
		trunkInstance.scaling.y = height * 0.9;
		trunkInstance.isPickable = false;
		for (const [branchIndex, side] of [-1, 1].entries()) {
			const limb = branch.createInstance(`env-tree-branch-${index}-${branchIndex}`);
			limb.parent = root;
			limb.position.set(x + side * 0.25, height * 0.79, z);
			limb.rotation.z = side * 0.72;
			limb.rotation.x = side * 0.18;
			limb.scaling.setAll(0.9);
			limb.isPickable = false;
		}
		const crowns = 3 + Math.floor(rng() * 3);
		for (let puff = 0; puff < crowns; puff++) {
			const crown = canopies[(index + puff) % canopies.length].createInstance(`env-tree-crown-${index}-${puff}`);
			crown.parent = root;
			const angle = (puff / crowns) * Math.PI * 2 + rng() * 0.35;
			crown.position.set(
				x + Math.cos(angle) * (0.85 + rng() * 0.45),
				height * 0.88 + (puff % 2) * 0.75 + 0.8,
				z + Math.sin(angle) * (0.85 + rng() * 0.45),
			);
			crown.scaling.set(0.82 + rng() * 0.33, 0.58 + rng() * 0.25, 0.78 + rng() * 0.3);
			crown.rotation.y = angle;
			crown.isPickable = false;
		}
	}
	return root;
}

function createMeadowDressing(scene: Scene, materials: Record<string, StandardMaterial>, rng: () => number) {
	const groups: Array<{x:number;z:number;order:number;parts:InstancedMesh[]}> = [];
	// Grass tufts: thin cones read like blades from the RO-style camera.
	const bladeMasters = [
		MeshBuilder.CreateCylinder("env-blade-a", { height: 0.62, diameterBottom: 0.14, diameterTop: 0, tessellation: 3 }, scene),
		MeshBuilder.CreateCylinder("env-blade-b", { height: 0.52, diameterBottom: 0.12, diameterTop: 0, tessellation: 3 }, scene),
	];
	bladeMasters[0].material = materials.grassLight;
	bladeMasters[1].material = materials.grass;
	const stemMaster = MeshBuilder.CreateCylinder("env-flower-stem", { height: 0.38, diameterTop: 0.018, diameterBottom: 0.028, tessellation: 4 }, scene);
	stemMaster.material = materials.stem;
	const bloomMasters = [
		MeshBuilder.CreateSphere("env-flower-white", { diameter: 0.19, segments: 6 }, scene),
		MeshBuilder.CreateSphere("env-flower-gold", { diameter: 0.18, segments: 6 }, scene),
		MeshBuilder.CreateSphere("env-flower-pink", { diameter: 0.17, segments: 6 }, scene),
	];
	const bloomMaterials = [materials.flowerWhite, materials.flowerGold, materials.flowerPink];
	for (const [index, bloom] of bloomMasters.entries()) {
		bloom.material = bloomMaterials[index];
	}
	const flowerCenter = MeshBuilder.CreateSphere("env-flower-center", { diameter: 0.13, segments: 6 }, scene);
	flowerCenter.material = materials.flowerGold;
	const masters = [...bladeMasters, stemMaster, ...bloomMasters, flowerCenter];
	for (const master of masters) {
		master.isVisible = false;
		master.isPickable = false;
	}

	for (let index = 0; index < 720; index++) {
		const isBloom = index % 3 === 2;
		const spot = meadowSpot(rng, isBloom ? 0.5 : 1);
		if (!spot) continue;
		const parts: InstancedMesh[] = [];
		if (isBloom) {
			const flowerType = Math.floor(index / 3) % bloomMasters.length;
			const stem = stemMaster.createInstance("env-flower-stem-" + index);
			stem.position.set(spot.x, 0.19, spot.z);
			stem.isPickable = false;
			parts.push(stem);
			for (let petal = 0; petal < 5; petal++) {
				const angle = petal * Math.PI * 2 / 5;
				const bloom = bloomMasters[flowerType].createInstance(`env-flower-${index}-${petal}`);
				bloom.position.set(spot.x + Math.cos(angle) * 0.1, 0.4, spot.z + Math.sin(angle) * 0.1);
				bloom.scaling.set(0.62, 0.25, 0.92);
				bloom.rotation.y = angle;
				bloom.isPickable = false;
				parts.push(bloom);
			}
			const center = flowerCenter.createInstance("env-flower-center-" + index);
			center.position.set(spot.x, 0.43, spot.z);
			center.scaling.setAll(0.52);
			center.isPickable = false;
			parts.push(center);
		} else {
			const master = bladeMasters[index % bladeMasters.length];
			for (let tuft = 0; tuft < 3; tuft++) {
				const blade = master.createInstance(`env-blade-${index}-${tuft}`);
				blade.position.set(spot.x + (rng() - 0.5) * 0.24, 0.24, spot.z + (rng() - 0.5) * 0.24);
				blade.rotation.y = rng() * Math.PI;
				blade.scaling.set(0.68 + rng() * 0.5, 0.65 + rng() * 0.75, 0.72 + rng() * 0.45);
				blade.isPickable = false;
				parts.push(blade);
			}
		}
		groups.push({x:spot.x,z:spot.z,order:index,parts});
	}

	// Scattered rocks away from the play lanes.
	const rockMaster = MeshBuilder.CreateSphere("env-rock-master", { diameter: 1.1, segments: 4 }, scene);
	rockMaster.material = materials.stone;
	rockMaster.isVisible = false;
	rockMaster.isPickable = false;
	for (let index = 0; index < 26; index++) {
		const spot = meadowSpot(rng, 1);
		if (!spot) continue;
		const rock = rockMaster.createInstance(`env-rock-${index}`);
		rock.position.set(spot.x, 0.2 + rng() * 0.1, spot.z);
		rock.rotation.set(rng() * Math.PI, rng() * Math.PI, rng() * Math.PI);
		rock.scaling.set(0.6 + rng() * 1.1, 0.5 + rng() * 0.6, 0.6 + rng() * 1.1);
		rock.isPickable = false;
	}
	return groups;
}

/** Rejects spots on the path, the stream and the castle terrace. */
function meadowSpot(rng: () => number, spread: number): { x: number; z: number } | null {
	const x = (rng() * 2 - 1) * FIELD_LIMIT * spread;
	const z = -9 + rng() * 42;
	if (Math.abs(x) < PATH_HALF_WIDTH && z > -6 && z < 34) return null;
	if (Math.abs(z - STREAM_Z) < STREAM_HALF_WIDTH + 0.6) return null;
	if (z > CASTLE_Z_START) return null;
	return { x, z };
}

function seededRandom(seed: number): () => number {
	let state = seed >>> 0;
	return () => {
		state = (state * 1664525 + 1013904223) >>> 0;
		return state / 0x1_0000_0000;
	};
}

/**
 * Scenery that never moves after load (wind and waves move vertices in the shader, never transforms):
 * skip its per-frame world-matrix and bounds sync (community practice §2.1). The final world bounds are
 * applied before syncing stops, so culling and shadow fitting stay exact. Nothing in the client picks
 * scenery (no scene.pick, actions or pointer observers), so it stays unpickable. Unfreeze before moving.
 */
function freezeStaticScenery(meshes: Iterable<AbstractMesh>): void {
	for (const mesh of meshes) {
		if (mesh.isDisposed() || mesh.isWorldMatrixFrozen) continue;
		mesh.freezeWorldMatrix();
		mesh.getBoundingInfo();
		mesh.doNotSyncBoundingInfo = true;
		mesh.isPickable = false;
	}
}

// =====================================================================================================================
// C-P1-TREE · sunmeadow-trees-v4 in the live Sunmeadow cells (docs/reviews/2026-10-02-trees-in-babylon.md)
//
// Kit: the seven Quaternius CC0 picks, stylised in Blender (assets/blender/trees_v4), exported through the shared
// export helper and apps/client/scripts/gltf-postprocess.mjs (EXT_meshopt + quantised geometry, one shared KTX2 set:
// ETC1S bark albedo and leaf atlas, UASTC bark normal). Provenance: assets/models/sunmeadow-trees-v4/candidates/
// quaternius-stylized/provenance.json. This section is self-contained; the hooks into the code above are marked
// "C-P1-TREE" (imports, createEnvironment, applyGraphics, graphicsDiagnostics, loadTerrainCells, upgradeKeepAndTrees).
//
// - GLBs load without their glTF materials. Two shared StandardMaterials carry the KTX2 textures, the TEXCOORD_1 wind
//   (nature-motion "uv2" weights: per-clump phase, nothing sways below 1 m above the root) and the dithered LOD fade,
//   so every species, LOD and cell shares one shader variant per pass. StandardMaterial on purpose: the impostor cards
//   light like it, so the LOD1 -> card swap keeps its brightness.
// - Trees are thin instances per species per 64 m cell (impostors.ts createTreeLodField). Distances per tier come from
//   the device-tiers plan 3.3: LOD1 at 0.035 screen coverage x coverageScale, card swap at shadow distance + 10 m with a
//   10 m dithered band, cards to the detail draw distance (impostor-math.mjs treeLodPlan).
// - Vegetation density thins the decorative TREE_SPOTS trees (except four landmarks) and never the world-prop trees:
//   those stand on server collision blockers and must stay visible.
// - Colliders stay with the server (world_props boxes). Each kit tree is centred on its blocker and its trunk at 1 m
//   (+ 0.05 m) fits inside the box (checked below); canopies never collide. TREE_SPOTS keep their visual anchors and
//   have no blockers yet (root hand-off contract 3). Proposed trunk capsules: see the review doc.
// - Ground is the flat Y = 0 support; a future terrain pass only has to give each placement its ground y (the wind is
//   measured from the instance origin, not from world height).
// =====================================================================================================================

type SunmeadowTreeSpecies = "qn_broadleaf_s" | "qn_broadleaf_m" | "qn_broadleaf_l" | "qn_conifer_m" | "qn_conifer_l";

const TREE_KIT_SPECIES: readonly SunmeadowTreeSpecies[] = ["qn_broadleaf_s", "qn_broadleaf_m", "qn_broadleaf_l", "qn_conifer_m", "qn_conifer_l"];
const TREE_KIT_GLB = import.meta.glob("./assets/models/sunmeadow-trees-v4/*.glb", { query: "?url", import: "default", eager: true }) as Record<string, string>;
const TREE_KIT_KTX2 = import.meta.glob("./assets/models/sunmeadow-trees-v4/textures/*.ktx2", { query: "?url", import: "default", eager: true }) as Record<string, string>;
const TREE_IMPOSTOR_KTX2 = import.meta.glob("./assets/world/impostors/sunmeadow-trees-v3/*.ktx2", { query: "?url", import: "default", eager: true }) as Record<string, string>;
/** Trunk radius at 1 m at scale 1 (provenance after.trunk_r_1m_m) and the decision-doc minimum per slot (4.1). */
const TREE_TRUNK_AT_1M: Record<SunmeadowTreeSpecies, [radius: number, minimum: number]> = {
	qn_broadleaf_s: [0.27, 0.25], qn_broadleaf_m: [0.336, 0.32], qn_broadleaf_l: [0.475, 0.42], qn_conifer_m: [0.221, 0.22], qn_conifer_l: [0.322, 0.30],
};
/** Tip sway at wind strength 1, metres (decision doc 4.3: 0.10-0.25 m). */
const TREE_TIP_SWAY_M = 0.2;
/**
 * Tree look in this lighting (sun 1.65, hemisphere 0.62, ACES + contrast 1.12), tuned against the Route A target
 * swatches on tree-masked captures (review doc, pass 2). StandardMaterial clamps light x albedo at the albedo, so:
 * - TREE_ALBEDO_GAIN lifts the albedo itself (texture level) for the highlights (p90 was 0.18 luma under target);
 * - TREE_FOLIAGE_FILL is added to the light before the clamp (linkEmissiveWithDiffuse), so it lifts the shaded side,
 *   cool-tinted (more G/B than R) to pull the shadow hue from olive towards the target's blue-green (p10 was #0C1100);
 * - TREE_BARK_FILL keeps trunks under the crown a readable warm brown.
 * world-weather scales every *foliage* emissive by daylight (24 % at night), so the fills fade with the sun.
 * The impostor manifest (sunmeadow-trees-v3 shading) carries the same gain and fill, so cards match at the swap.
 */
const TREE_ALBEDO_GAIN = 1.22;
const TREE_FOLIAGE_FILL = new Color3(0.26, 0.34, 0.36);
const TREE_BARK_FILL = new Color3(0.22, 0.2, 0.18);
/** TREE_SPOTS (index-aligned) -> species, scale, landmark (kept at every vegetation density). <= 3 species per cell. */
const SUNMEADOW_FIELD_TREES: ReadonlyArray<[SunmeadowTreeSpecies, number, boolean]> = [
	["qn_broadleaf_m", 0.96, true],   // (-18, 5)  west of the spawn road
	["qn_broadleaf_l", 0.9, true],    // (18, 7)   east of the spawn road
	["qn_conifer_m", 1.0, false],     // (-20, 17)
	["qn_broadleaf_m", 1.1, false],   // (20, 21)
	["qn_conifer_l", 0.94, true],     // (-25, 30) west castle-wall landmark
	["qn_broadleaf_m", 0.96, false],  // (-12, 35)
	["qn_conifer_m", 1.05, false],    // (14, 35)
	["qn_broadleaf_l", 0.95, true],   // (27, 31)  east castle-wall landmark
	["qn_broadleaf_s", 1.05, false],  // (-22, -6)
	["qn_conifer_m", 1.0, false],     // (22, -4)
	["qn_broadleaf_m", 1.0, false],   // (-8, 40)
	["qn_broadleaf_m", 1.06, false],  // (9, 42)
];
/** Sunmeadow c7/c8 world-prop trees -> species and scale: c7 "pine" props lean conifer, c8 "oak" props broadleaf. */
const SUNMEADOW_CELL_TREES: Readonly<Record<string, [SunmeadowTreeSpecies, number]>> = {
	sunmeadow_pine_west: ["qn_conifer_m", 1.0],
	sunmeadow_pine_northwest: ["qn_conifer_m", 1.05],
	sunmeadow_pine_west_mid: ["qn_conifer_l", 0.96],
	sunmeadow_pine_west_south: ["qn_conifer_m", 1.1],
	sunmeadow_pine_west_inner_north: ["qn_broadleaf_s", 0.95],
	sunmeadow_pine_west_inner_south: ["qn_conifer_l", 0.94],
	sunmeadow_pine_trail_north: ["qn_broadleaf_s", 1.0],
	sunmeadow_oak_east: ["qn_broadleaf_l", 1.0],
	sunmeadow_oak_east_mid: ["qn_broadleaf_s", 0.95],
	sunmeadow_oak_east_south: ["qn_broadleaf_l", 0.93],
	sunmeadow_oak_east_inner_north: ["qn_broadleaf_m", 0.96],
	sunmeadow_oak_east_inner_south: ["qn_broadleaf_s", 1.05],
	sunmeadow_oak_southeast: ["qn_broadleaf_m", 1.05],
	sunmeadow_oak_trail_north: ["qn_broadleaf_m", 0.96],
};

/** Key of the 64 m world cell grid (c7_r6 = x -64..0, z -128..-64). */
const worldCellKey = (x: number, z: number) => `c${Math.floor(x / 64) + 8}_r${Math.floor(z / 64) + 8}`;

/** The 12 field trees at the TREE_SPOTS anchors. */
function sunmeadowFieldTrees(): TreeLodPlacement[] {
	return TREE_SPOTS.map(([x, z], index) => {
		const [species, scale, keep] = SUNMEADOW_FIELD_TREES[index];
		return { species, x, y: 0, z, yaw: index * 1.3, scale, cell: worldCellKey(x, z), keep, order: index, id: `tree_spot_${index}` };
	});
}

/** World-prop trees of one cell, centred on their collision blockers (kept at every density). */
function sunmeadowCellTrees(props: readonly WorldPropDefinition[], cellId: string, skip: ReadonlySet<string>): TreeLodPlacement[] {
	return props.filter((prop) => prop.cell === cellId && prop.kind.startsWith("tree_") && !skip.has(prop.id)).map((prop, index) => {
		const target = prop.height * prop.scale;
		const [species, scale] = SUNMEADOW_CELL_TREES[prop.id]
			?? (target <= 5.8 ? ["qn_broadleaf_s", 1] : target <= 8 ? ["qn_broadleaf_m", 1] : ["qn_broadleaf_l", 1]);
		const [trunk] = TREE_TRUNK_AT_1M[species];
		const half = Math.min(prop.collider_size[0], prop.collider_size[2]) / 2;
		if (trunk * scale + 0.05 > half) console.warn(`Tree ${prop.id}: trunk ${(trunk * scale).toFixed(2)} m is wider than its blocker (half ${half} m).`);
		return { species, x: prop.x, y: 0, z: prop.z, yaw: prop.yaw, scale, cell: worldCellKey(prop.x, prop.z), keep: true, order: 100 + index, id: prop.id };
	});
}

interface SunmeadowTrees {
	/** True once the kit, its materials and the impostor atlas loaded; false keeps the legacy trees. */
	readonly ready: Promise<boolean>;
	/** Adds trees (no-op when the kit failed) and compiles their shaders before they can draw. */
	add(placements: TreeLodPlacement[]): Promise<void>;
	setProfile(profile: ResolvedGraphicsPreset): void;
	stats(): (TreeLodStats & { plan: TreeLodPlan }) | null;
}

function createSunmeadowTrees(scene: Scene, clock: NatureClock, getShadows: () => ShadowGenerator, shadowsEnabled: boolean,
	initialProfile: ResolvedGraphicsPreset): SunmeadowTrees {
	// DEV review hooks: ?treeKit=0 (legacy trees), ?treeLod=lod0|lod1|impostor|none (force one representation; none =
	// no trees, the background plate for tree-pixel masks), ?treeSwap=<m> (move the card swap into a locked view),
	// ?treeSelfShadow=1 (foliage receives shadows).
	const query = import.meta.env.DEV ? new URLSearchParams(location.search) : new URLSearchParams();
	const force = ((value) => (value === "lod0" || value === "lod1" || value === "impostor" || value === "none" ? value : null))(query.get("treeLod"));
	const swapOverride = Number(query.get("treeSwap"));
	const planFor = (profile: ResolvedGraphicsPreset) => treeLodPlan(profile, { force, swap: swapOverride > 0 ? swapOverride : undefined });
	let plan = planFor(initialProfile);
	let field: TreeLodField | null = null;
	let cards: ImpostorField | null = null;
	let sakura:ReturnType<typeof createStyledSakura>|null=null;
	const sakuraEnabled=query.get('sakura')==='1'||query.get('sakura')!=='off'&&query.get('dressing')==='v3';
	const ready = query.get("treeKit") === "0" ? Promise.resolve(false) : loadSunmeadowTreeKit(scene, clock, query.get("treeSelfShadow") === "1").then((kit) => {
		cards = kit.cards;
		if(sakuraEnabled){
			const atlas=Object.fromEntries(Object.entries(TREE_IMPOSTOR_KTX2).map(([path,url])=>[path.slice(path.lastIndexOf('/')+1),url]));
			try{sakura=createStyledSakura(scene,{species:kit.species,manifest:cards.manifest,resolveUrl:name=>{
				const url=atlas[name];if(!url)throw Error(`Sakura impostor page missing: ${name}`);return url;
			},clock,plan,onBatch(mesh){mesh.metadata={...mesh.metadata,glow:false,sakura:true};mesh.receiveShadows=kit.receiveShadows(mesh);if(shadowsEnabled)getShadows().addShadowCaster(mesh,false);}});}
			catch(error){console.warn('Sakura palette unavailable; authored green trees remain.',error);}
		}
		field = createTreeLodField(scene, kit.species, {
			name: "sunmeadow-trees", plan, field: kit.cards,
			onBatch(mesh) {
				// Emissive fill is part of the material, not a glow source (keeps glow draws for real emitters).
				mesh.metadata = { ...mesh.metadata, glow: false };
				mesh.receiveShadows = kit.receiveShadows(mesh);
				if (shadowsEnabled) getShadows().addShadowCaster(mesh, false);
			},
		});
		if (import.meta.env.DEV) (window as unknown as { __xexoriaTrees?: unknown }).__xexoriaTrees = { field, kit };
		// DEV ?treeWitness=1: the decision doc's 1.8 m scale witness, 3 m south of the c8 oak (the lookdev target).
		if (query.get("treeWitness") === "1") {
			const witness = MeshBuilder.CreateCapsule("tree-review-witness-1p8m", { height: 1.8, radius: 0.3 }, scene);
			witness.position.set(24, 0.9, -89);
			const grey = new StandardMaterial("tree-review-witness", scene);
			grey.diffuseColor = Color3.FromHexString("#b9bec4");
			grey.specularColor = Color3.Black();
			witness.material = grey;
			witness.isPickable = false;
			if (shadowsEnabled) getShadows().addShadowCaster(witness, false);
		}
		return true;
	}, (error) => {
		console.warn("Sunmeadow tree kit unavailable; the legacy trees stay.", error);
		return false;
	});
	return {
		ready,
		async add(placements) {
			if (!(await ready) || !field || !placements.length) return;
			const pink=sakura?placements.filter(isSakuraPlacement):[];
			const created = [...field.add(sakura?placements.filter(p=>!isSakuraPlacement(p)):placements),...(sakura?.add(pink)??[])];
			if(pink.length)scene.metadata={...scene.metadata,sakura:{revision:'r01',source:'Quaternius Stylized Nature MegaKit CC0',placementsAdded:0,replacedVisualIds:pink.map(p=>p.id),anchorsAndScale:'UNCHANGED',colliders:'EXISTING_CONTRACT_UNCHANGED',newSkeletalAnimation:false}};
			// One compile per material variant (all batches share it). Bounded: a texture that never loads would keep
			// forceCompilationAsync waiting forever and stall the world start; a not-ready batch is simply not drawn.
			const seen = new Set<Material>();
			for (const mesh of created) {
				if (!mesh.material || seen.has(mesh.material)) continue;
				seen.add(mesh.material);
				const compiled = await Promise.race([mesh.material.forceCompilationAsync(mesh).then(() => true),
					new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 10000))]);
				if (!compiled) console.warn(`Tree material ${mesh.material.name} is not ready after 10 s; its trees draw once it is.`);
			}
			// Cards compile once their atlas pages arrive (3 MB of KTX2); a card that is not ready yet is simply not drawn,
			// so startup never waits for it.
			void cards?.whenReady();
		},
		setProfile(profile) {
			plan = planFor(profile);
			field?.setPlan(plan);
			sakura?.setPlan(plan);
		},
		stats() {
			const current = field as TreeLodField | null;
			return current ? { ...current.stats(), plan: { ...current.plan },sakura:sakura?.stats()??null } : null;
		},
	};
}

/** Loads the five tree species (LOD0 + LOD1), the shared materials and the impostor cards. */
async function loadSunmeadowTreeKit(scene: Scene, clock: NatureClock, selfShadow: boolean): Promise<{
	species: Record<SunmeadowTreeSpecies, TreeLodSpecies>; cards: ImpostorField; receiveShadows(mesh: Mesh): boolean;
}> {
	const file = (table: Record<string, string>, name: string) => {
		const hit = Object.entries(table).find(([path]) => path.endsWith(`/${name}`) || path.includes(`/${name}-`));
		if (!hit) throw new Error(`Tree kit file ${name} is missing from the build.`);
		return hit[1];
	};
	// KTX2 decodes to compressed UNORM formats; ETC1S colour carries the sRGB transfer, so gammaSpace stays true and
	// StandardMaterial reads it like the PNG would. glTF UVs: no flip (invertY false), as the glTF loader does.
	const texture = (name: string, wrap: number) => {
		const result = new Texture(file(TREE_KIT_KTX2, name), scene, false, false, Texture.TRILINEAR_SAMPLINGMODE);
		result.wrapU = result.wrapV = wrap;
		return result;
	};
	const barkAlbedo = texture("qn_bark_albedo", Texture.WRAP_ADDRESSMODE);
	const barkNormal = texture("qn_bark_normal", Texture.WRAP_ADDRESSMODE);
	const leafAtlas = texture("qn_leaf_atlas_albedo", Texture.CLAMP_ADDRESSMODE);
	leafAtlas.hasAlpha = true;
	barkAlbedo.level = leafAtlas.level = TREE_ALBEDO_GAIN;

	const wind = { weights: "uv2", rigidBelow: 1, fadeIn: 1 } as const;
	// Named *foliage* too, only so world-weather dims its fill at night like the crown's.
	const bark = new StandardMaterial("env-qn-tree-foliage-bark", scene);
	bark.diffuseTexture = barkAlbedo;
	bark.bumpTexture = barkNormal;
	// Same normal-map convention the glTF loader applies in a left-handed scene (the bark tangents are re-signed when
	// the importer's mirrored root is baked in, below).
	bark.invertNormalMapX = !scene.useRightHandedSystem;
	bark.invertNormalMapY = scene.useRightHandedSystem;
	bark.specularColor = Color3.Black();
	bark.emissiveColor = TREE_BARK_FILL.clone();
	bark.linkEmissiveWithDiffuse = true;
	// Export receipt: bark is double-sided (open limb ends); glTF double-sided = no culling + two-sided lighting.
	bark.backFaceCulling = false;
	bark.twoSidedLighting = true;
	addWind(bark, scene, clock, TREE_TIP_SWAY_M, 0, 0, wind);
	// Named *foliage*: world-weather dims its emissive fill at night like the impostor cards and the old leaf cards.
	const foliage = new StandardMaterial("env-qn-tree-foliage", scene);
	foliage.diffuseTexture = leafAtlas;
	foliage.useAlphaFromDiffuseTexture = true;
	foliage.transparencyMode = StandardMaterial.MATERIAL_ALPHATEST;
	foliage.alphaCutOff = 0.45;
	foliage.backFaceCulling = false;
	// No two-sided lighting: the card normals were transferred from one soft proxy per clump (decision doc 4.2 step
	// 3), so both faces of a card must shade like that clump's surface. Flipping them on back faces darkened every
	// card seen from behind into black spikes at the crown edge (smoke capture trees-smoke-p1).
	foliage.twoSidedLighting = false;
	foliage.specularColor = Color3.Black();
	foliage.emissiveColor = TREE_FOLIAGE_FILL.clone();
	foliage.linkEmissiveWithDiffuse = true;
	addWind(foliage, scene, clock, TREE_TIP_SWAY_M, 0, 0, wind);

	const loadLod = async (stem: string): Promise<Mesh[]> => {
		let json: { meshes?: Array<{ primitives?: Array<{ material?: number }> }>; materials?: Array<{ name?: string }> } | undefined;
		const loaded = await ImportMeshAsync(file(TREE_KIT_GLB, `${stem}.glb`), scene, {
			pluginExtension: ".glb",
			pluginOptions: { gltf: { skipMaterials: true, onParsed: (data) => { json = data.json as typeof json; } } },
		});
		const parts: Mesh[] = [];
		for (const source of loaded.meshes) {
			if (!(source instanceof Mesh) || source.getTotalVertices() === 0) continue;
			const primitive = Number(/_primitive(\d+)$/.exec(source.name)?.[1] ?? 0);
			const role = json?.materials?.[json?.meshes?.[0]?.primitives?.[primitive]?.material ?? -1]?.name?.endsWith("_bark") ? "bark" : "foliage";
			source.computeWorldMatrix(true);
			const mirrored = source.getWorldMatrix().determinant() < 0;
			// Bake the importer's handedness root into asset-space geometry (static-model.mjs fixes the winding).
			const part = mergeStaticModel({ meshes: [source], transformNodes: [], animationGroups: [] }, `${stem}-${role}`);
			const tangents = mirrored ? part.getVerticesData(VertexBuffer.TangentKind) : null;
			if (tangents) {
				// Baking a mirror into the vertices flips cross(normal, tangent); re-sign w so the bitangent matches the
				// unbaked glTF path the normal-map flags above assume.
				for (let index = 3; index < tangents.length; index += 4) tangents[index] = -tangents[index];
				part.setVerticesData(VertexBuffer.TangentKind, tangents, false, 4);
			}
			part.material = role === "bark" ? bark : foliage;
			part.isVisible = false;
			part.isPickable = false;
			// Wind moves tips up to TREE_TIP_SWAY_M: widen the culling bounds by 0.3 m on every side.
			if (part.geometry) part.geometry.boundingBias = new Vector2(0, 0.3);
			parts.push(part);
		}
		for (const mesh of loaded.meshes) if (!mesh.isDisposed()) mesh.dispose(false, false);
		for (const node of loaded.transformNodes) if (!node.isDisposed()) node.dispose(false, false);
		if (!parts.length) throw new Error(`Tree kit ${stem} has no geometry.`);
		// Bark first, foliage last: one predictable batch order per species.
		return parts.sort((a, b) => Number(a.material === foliage) - Number(b.material === foliage));
	};

	const manifestRequest = fetch(treeImpostorManifestUrl).then((response) => {
		if (!response.ok) throw new Error(`Impostor manifest ${response.status}`);
		return response.json() as Promise<ImpostorAtlasManifest>;
	});
	const species = {} as Record<SunmeadowTreeSpecies, TreeLodSpecies>;
	const created: Mesh[] = [];
	try {
		for (const id of TREE_KIT_SPECIES) {
			const lod0 = await loadLod(`${id}_lod0`);
			const lod1 = await loadLod(`${id}_lod1`);
			created.push(...lod0, ...lod1);
			const { min, max } = Mesh.MinMax(lod0);
			species[id] = { lods: [lod0, lod1], impostorId: id, centreY: (min.y + max.y) / 2, radius: max.subtract(min).length() / 2 };
		}
		const manifest = await manifestRequest;
		const atlas = Object.fromEntries(Object.entries(TREE_IMPOSTOR_KTX2).map(([path, url]) => [path.slice(path.lastIndexOf("/") + 1), url]));
		const cards = createImpostorField(scene, manifest, (name) => {
			const url = atlas[name];
			if (!url) throw new Error(`Impostor page ${name} is missing from the build.`);
			return url;
		}, { ktx2: true });
		for (const mesh of cards.meshes) mesh.metadata = { ...mesh.metadata, glow: false };
		for (const id of TREE_KIT_SPECIES) {
			if (!manifest.objects.some((object) => object.id === id)) throw new Error(`Impostor atlas has no card for ${id}.`);
		}
		return { species, cards, receiveShadows: (mesh) => mesh.material === bark || selfShadow };
	} catch (error) {
		for (const mesh of created) mesh.dispose(false, false);
		for (const material of [bark, foliage]) material.dispose(false, true);
		throw error;
	}
}
