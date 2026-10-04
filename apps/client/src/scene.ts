import { createWorldCombatLabels } from "./world-combat-labels";
import {createAmbientAtmosphere} from './ambient-atmosphere';
import { createMonsterViewRegistry } from './monster-view-registry.mjs';
import { preloadMonsterStandins, type MonsterStandinView } from './monster-standin-renderer';
import {createActorFeedback} from './combat-vfx-feedback';
import type {CombatTextPreferences,DamageIdentity} from './world-combat-labels';
import type { EnemyHealthLabel, DamageKind } from "./world-combat-labels";
import { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Vector3 } from "@babylonjs/core/Maths/math.vector";
import { MeshBuilder } from "@babylonjs/core/Meshes/meshBuilder";
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { MultiMaterial } from "@babylonjs/core/Materials/multiMaterial";
import type { Material } from "@babylonjs/core/Materials/material";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import { Scene } from "@babylonjs/core/scene";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { SceneLoader } from "@babylonjs/core/Loading/sceneLoader";
import {heroReviewIdentity} from './hero-review-policy.mjs';
import {playerFraming} from './player-framing.mjs';
import type {MageCastState} from './mage-pilot-client.mjs';
import {resolveWeaponFxMarkers} from './combat-vfx-weapon-markers';
import quaterniusWarriorAssetUrl from "./assets/characters/quaternius-warrior.meshopt-etc1s.glb?url";
import villageLanternAssetUrl from "./assets/models/prop_village_lantern_01.glb?url";
import wayfarerKitAssetUrl from "./assets/models/prop_wayfarer_kit.glb?url";
import type { CollisionBox, CoordinateFixture, StaticCollider } from "./coordinate-fixture";
import { staticColliderBoxes } from "./coordinate-collision.mjs";
import {configureAssetCodecs} from "./asset-codecs";
import { bootstrapAssetProgress, type BootstrapPhaseEvent } from './bootstrap-progress.mjs';
import { CameraRig, SlashArc, SplashTelegraph, createCombatFx } from "./combat-fx";
import { createAmbientWorld } from "./ambient-world";
import { configure360Orbit } from "./camera-orbit";
import { createEnvironment, type EnvironmentGraphicsDiagnostics } from "./environment";
import type { TerrainCellDefinition, WorldPropDefinition } from "./world-layout";
import { createGateTriggeredLoader, createSouthboundCellLoader } from "./city-streaming.mjs";
import {isRendererResetRequired} from './renderer-manual-reset';
import {getRendererHealth} from './renderer-health';
import {createRenderer as createRendererChoice} from './renderer-choice';
import {installReadyTextureCacheRelease,releasePreparedStaticGeometry,type CpuCacheReceipt} from './asset-runtime-cache';
import {getGraphicsPreference, resolveGraphicsPreset, subscribeGraphicsPreference, type ResolvedGraphicsPreset} from "./graphics-quality.mjs";
import {createFrameRatePolicy,createPacedFrameRequester,describeFrameRateOptions,parseStoredFrameRateSetting,FRAME_RATE_STORAGE_KEY,FRAME_RATE_SETTING_EVENT,FRAME_RATE_STATE_EVENT,type FrameRateSetting,type FrameRatePolicyState} from './frame-rate-policy.mjs';
import type {RenderScalingHandle} from './render-scaling';
import { createCityNpc, type CityNpcDefinition } from './city-npc';
import { sampleCityHeight, type CityTraversalField } from './grounded-city.mjs';
import {
	createHero as createHeroActor,
	createMaterials as createActorMaterials,
	createRouteGuide as createRouteGuideActor,
	createSlime as createSlimeActor,
	createWindmark as createWindmarkActor,
} from "./actors";

export interface RendererChoice {
	engine: AbstractEngine;
	label: string;
	canvas: HTMLCanvasElement;
	fallbackReason:string|null;
}

export interface GameScene {
	engine: AbstractEngine;
	scene: Scene;
	camera: ArcRotateCamera;
	cameraRig: CameraRig;
	slashArc: SlashArc;
	localRoot: TransformNode;
	setHeroMotion(motion: "idle" | "run"): void;
	setLocalPresentationPaused(paused:boolean):void;
	playHeroAttack(): void;
	setMageTrialContext(actorId:number,serverNowMs:number,focusEquipped:boolean):void;
	beginMageCast(state:Readonly<MageCastState>):void;
	releaseMageCast(state:Readonly<MageCastState>):void;
	resolveMageCast(state:Readonly<MageCastState>):void;
	clearMagePresentation():void;
	playNpcGreeting(id: string): void;
	remotePlayers: Map<number, TransformNode>;
	slimes: Map<number, { root: TransformNode; body: TransformNode; material: Material; hp: EnemyHealthLabel; standin?: MonsterStandinView }>;
	collisionBoxes: CollisionBox[];
	playerRadius: number;
	playerHeight: number;
	setLocalPosition(x: number, z: number): void;
	placeRemote(id: number, x: number, z: number, connected: boolean): void;
	removeRemote(id: number): void;
	setMonsters(monsters: Array<{ id: number; kind:number; x: number; z: number; hp: number; max_hp: number; active: boolean;facing?:number }>): void;
	flashMonster(id: number, strong?: boolean,attacker?:{x:number;z:number;relation:'mine'|'party'|'other'}): void;
	animateMonsterHop(id: number, phase: "windup" | "leap" | "impact" | "recovery" | "idle"): void;
	createSplashTelegraph(x: number, z: number, radius?: number, durationMs?: number): SplashTelegraph;
	setQuestProgress(activatedWindmarks: string[]): void;
	updateDrops(entries: Array<{ encounter: string; item: string; count: number; x: number; z: number }>): void;
	clearDrops(): void;
	showDamage(x: number, z: number, amount: number, kind?: DamageKind, anchorY?: number, identity?:DamageIdentity): void;
	showCombatWord(x:number,z:number,word:'miss'|'evade'|'parry'|'counter',anchorY?:number,identity?:DamageIdentity):void;
	configureCombatPresentation(preferences:CombatTextPreferences&{lowEffects?:boolean;screenShake?:boolean}):void;
	setWorldTick(tick: number): void;
	cityDetailState(): "idle" | "loading" | "prepared" | "ready" | "failed";
	waitingForCity(): boolean;
	allowCityPreparation(): void;
	ensureDetailedCity(): Promise<void>;
	ensureTerrainCells(): Promise<void>;
	revealDetailedCity(): void;
	getRenderFps(): number;
	getGraphicsTier(): 'low' | 'medium' | 'high' | 'ultra';
	getGraphicsDiagnostics(): { profile: ResolvedGraphicsPreset; frameCap: number | null; frameRate: FrameRatePolicyState; environment: EnvironmentGraphicsDiagnostics };
	setFrameUpdate(callback:(()=>void)|null):void;
	/** Keep the input/network/UI callback alive while omitting the 3D scene draw. */
	setPaused(paused:boolean):void;
	releasePreparedStaticCaches(auditedMeshes:readonly Mesh[]):CpuCacheReceipt;
	dispose(): void;
}

export async function createRenderer(canvas: HTMLCanvasElement): Promise<RendererChoice> {
	return createRendererChoice(canvas);
}

export interface SceneEnemyDef {
	id: number;
	kind:number;
	hp:number;
	x: number;
	z: number;
	name: string;
}

export interface SceneNpcDef {
	id: string;
	x: number;
	z: number;
}

export interface SceneMarkerDef {
	id: string;
	x: number;
	z: number;
}

export async function createGameScene(
	engine: AbstractEngine,
	canvas: HTMLCanvasElement,
	fixture: CoordinateFixture,
	enemies: SceneEnemyDef[],
	routeNpc?: SceneNpcDef,
	markers: SceneMarkerDef[] = [],
	staticColliders: StaticCollider[] = [],
	cityGateZ = 24,
	terrainCells: TerrainCellDefinition[] = [],
	worldProps: WorldPropDefinition[] = [],
	worldHalfExtent = 308,
	cityNpcs: CityNpcDefinition[] = [],
	cityTraversal?: CityTraversalField,
	onBootstrapProgress?: (event: BootstrapPhaseEvent) => void,
	enemyKinds: ReadonlyArray<{kind:number;name:string;rank?:'normal'|'elite'|'boss'}> = [],
): Promise<GameScene> {
	onBootstrapProgress?.({id:'codecs',state:'active'});
	await configureAssetCodecs();
	onBootstrapProgress?.({id:'codecs',state:'complete'});
	onBootstrapProgress?.({id:'assets',state:'active'});
	const scene = new Scene(engine);
	scene.skipPointerMovePicking=true;
	scene.pointerDownPredicate=mesh=>mesh.isPickable&&typeof mesh.metadata?.monsterId==='number';
	scene.pointerUpPredicate=scene.pointerDownPredicate;
	// DEV-only inspection handle for art/lookdev review tooling (never in production builds).
	if (import.meta.env.DEV) (window as unknown as { __xexoria?: { scene: Scene; engine: typeof engine } }).__xexoria = { scene, engine };
	const lookdev = import.meta.env.DEV && new URLSearchParams(location.search).get('lookdev') === '1';
	const requestedTier = lookdev ? new URLSearchParams(location.search).get('lookdevTier') : null;
	const lookdevTier = requestedTier === 'low' || requestedTier === 'medium' || requestedTier === 'high' || requestedTier === 'ultra' ? requestedTier : null;
	const resolveQuality = () => resolveGraphicsPreset(lookdevTier ?? getGraphicsPreference(), {
		formFactor: matchMedia("(pointer: coarse)").matches || (canvas.clientWidth <= 1000 && canvas.clientHeight <= 900) ? "mobile" : "desktop",
		width: canvas.clientWidth, height: canvas.clientHeight, devicePixelRatio,
	});
	let quality = resolveQuality();
	// The paced requester owns the cap; Babylon's accumulator gives uneven vsync gaps.
	engine.maxFPS = undefined;
	engine.setHardwareScalingLevel(quality.hardwareScalingLevel);
	engine.resize();
	const cityOverview = import.meta.env.DEV && new URLSearchParams(location.search).get("cityOverview") === "1";
	const southSectorPreview = import.meta.env.DEV && new URLSearchParams(location.search).get("worldSector") === "1";
	const meadowPlaytest = import.meta.env.DEV && new URLSearchParams(location.search).get("meadowPlaytest") === "1";
	const mageTrialRequested=import.meta.env.DEV&&new URLSearchParams(location.search).get('mageTrial')==='1';

	// Third-person MMO framing: keep the avatar low-center while opening the meadow and distant gate.
	const framing=playerFraming(location.search,canvas.clientHeight>canvas.clientWidth,import.meta.env.DEV);
	const camera = new ArcRotateCamera("follow-camera", -Math.PI / 2, framing.beta, framing.radius, new Vector3(0, framing.targetHeight, 0), scene);
	camera.fov = framing.fov;
	camera.lowerRadiusLimit = 8.5;
	camera.upperRadiusLimit = 24;
	camera.lowerBetaLimit = 0.72;
	camera.upperBetaLimit = framing.upperBeta;
	camera.wheelDeltaPercentage = 0.015;
	camera.panningSensibility = 0;
	camera.attachControl(canvas, true);
	const releaseOrbitControls = configure360Orbit(camera, canvas);
	scene.onDisposeObservable.addOnce(releaseOrbitControls);
	if (meadowPlaytest) { camera.beta = 1.02; camera.radius = 17; }
	if (cityOverview) {
		const requestedView = new URLSearchParams(location.search).get("cityView") || "overview";
		const view = requestedView === "arrival" || requestedView === "plaza" || requestedView === "homes" || requestedView === "npc" || requestedView === "fountain" ? requestedView : "overview";
		const cityCenterZ = cityGateZ + 152;
		const viewTarget = view === "fountain" ? new Vector3(0, 7, cityCenterZ) : view === "npc" ? new Vector3(cityNpcs[0]?.x ?? 20, 1.5, cityNpcs[0]?.z ?? 156) : view === "arrival"
			? new Vector3(0, 14, cityGateZ)
			: view === "homes" ? new Vector3(-108, 5, cityCenterZ + 68)
			: view === "plaza"
				? new Vector3(0, 12, cityCenterZ)
				: new Vector3(0, 18, 160);
		camera.setTarget(viewTarget);
		camera.alpha = view === "npc" ? -2.3 : view === "overview" ? -1.27 : -1.48;
		camera.beta = view === "overview" ? 0.86 : view === "arrival" ? 1.15 : 1.25;
		camera.radius = view === "fountain" ? 31 : view === "npc" ? 7 : view === "overview" ? 270 : view === "arrival" ? 120 : view === "homes" ? 16 : 96;
		camera.lowerRadiusLimit = view === "npc" ? 3 : view === "fountain" ? 15 : view === "homes" ? 8.5 : 25;
		camera.upperRadiusLimit = 380;
		camera.upperBetaLimit = 1.55;
		camera.fov = 0.92;
		if (view === 'fountain') {
			const angle = new URLSearchParams(location.search).get('cityAngle');
			if (angle === 'side') camera.alpha = .62;
			if (angle === 'top') { camera.beta = .68; camera.radius = 38; }
			if (angle === 'player') { camera.setTarget(new Vector3(0, 2.3, cityCenterZ)); camera.beta = 1.54; camera.radius = 24; }
			if (angle === 'close') { camera.setTarget(new Vector3(0, 13, cityCenterZ)); camera.beta = 1.2; camera.radius = 18; }
		}
		const badge = document.createElement("div");
		badge.textContent = "CITY ART PREVIEW · Blender model · scenery only";
		badge.style.cssText = "position:fixed;top:34px;left:12px;z-index:1000;background:#142027e8;color:#f3da9e;padding:8px 12px;font:13px system-ui;pointer-events:none";
		document.body.append(badge);
		const views = document.createElement("nav");
		views.setAttribute("aria-label", "City viewpoints");
		views.style.cssText = "position:fixed;bottom:18px;left:50%;transform:translateX(-50%);z-index:1001;display:flex;gap:8px;background:#142027ed;padding:9px;border-radius:8px";
		for (const [key, label] of [["overview", "เมืองทั้งหมด"], ["arrival", "ทางเข้าเมือง"], ["plaza", "ลานน้ำพุ"], ["homes", "บ้านพัก"], ["npc", "รูน · ผู้เฒ่า"], ["fountain", "น้ำพุ"]]) {
			const link = document.createElement("a");
			link.href = `?cityOverview=1&cityView=${key}`;
			link.textContent = label;
			link.style.cssText = `color:${key === view ? "#142027" : "#f3da9e"};background:${key === view ? "#f3da9e" : "transparent"};padding:9px 12px;white-space:nowrap;text-decoration:none;font:14px system-ui;border-radius:5px`;
			views.append(link);
		}
		document.body.append(views);
		const previewStyle = document.createElement("style");
		previewStyle.textContent = "#hud > :not(#performance-stats), #world-vignette, #screen-hurt, #rotate-device, #toast, .enemy-label {display:none!important}";
		document.head.append(previewStyle);
		scene.onDisposeObservable.add(() => { badge.remove(); views.remove(); previewStyle.remove(); });
	}
	if (southSectorPreview) {
		const sectorView = new URLSearchParams(location.search).get("sectorView") ?? "trail";
		const overview = sectorView === "overview";
		const oakView = sectorView.startsWith("oak-");
		const borderView = sectorView.startsWith("border-");
		const oak = worldProps.find(prop => prop.id === "sunmeadow_oak_east");
		const marker = worldProps.find(prop => prop.kind === "trail_marker");
		camera.setTarget(oakView ? new Vector3(oak?.x ?? 24, sectorView === "oak-close" ? 1.6 : 3.8, oak?.z ?? -86)
			: sectorView === "waystone" ? new Vector3(marker?.x ?? -9.5, 1.3, marker?.z ?? -97.5) : new Vector3(-2, 1.3, -96));
		camera.alpha = sectorView === "oak-side" ? 0 : oakView ? -1.1 : sectorView === "waystone" ? 0.65 : 0.91;
		camera.beta = overview ? 0.65 : oakView ? 1.22 : sectorView === "waystone" ? 1.0 : 0.83;
		camera.radius = overview ? 76 : sectorView === "oak-close" ? 8 : oakView ? 18 : sectorView === "waystone" ? 14 : 30.6;
		camera.fov = 0.78;
		if (borderView) {
			camera.setTarget(new Vector3(0, 12, -96));
			camera.alpha = ({ "border-south": Math.PI / 2, "border-north": -Math.PI / 2,
				"border-east": Math.PI, "border-west": 0 } as Record<string, number>)[sectorView] ?? Math.PI / 2;
			camera.beta = 1.43;
			camera.radius = 70;
			camera.fov = 0.90;
		}
		camera.lowerRadiusLimit = 8;
		camera.upperRadiusLimit = 140;
		camera.upperBetaLimit = 1.5;
		const badge = document.createElement("div");
		badge.textContent = new URLSearchParams(location.search).get("heroOakPreview") === "1"
			? "SUNMEADOW · P2.0 experimental model · visual gate failed"
			: "SUNMEADOW SOUTH · authored landscape review";
		badge.style.cssText = "position:fixed;top:34px;left:12px;z-index:1000;background:#142027e8;color:#f3da9e;padding:8px 12px;font:13px system-ui;pointer-events:none";
		document.body.append(badge);
		const sectorViews = document.createElement("nav");
		sectorViews.setAttribute("aria-label", "Meadow viewpoints");
		sectorViews.style.cssText = "position:fixed;bottom:18px;left:50%;transform:translateX(-50%);z-index:1001;display:flex;gap:8px;background:#142027ed;padding:9px;border-radius:8px";
		sectorViews.style.maxWidth = "calc(100vw - 24px)";
		sectorViews.style.overflowX = "auto";
		sectorViews.style.whiteSpace = "nowrap";
		for (const [key, title] of [["trail", "ทางเดิน"], ["waystone", "แท่นหิน"], ["overview", "ภาพรวม"],
			["oak-player", "ต้นไม้"], ["oak-side", "ด้านข้าง"], ["oak-close", "ใกล้"],
			["border-south", "ภูเขาใต้"], ["border-north", "ภูเขาเหนือ"], ["border-east", "ภูเขาตะวันออก"], ["border-west", "ภูเขาตะวันตก"]]) {
			const link = document.createElement("a");
			link.href = `?worldSector=1&sectorView=${key}`;
			link.textContent = title;
			link.style.cssText = `color:${key === sectorView ? "#142027" : "#f3da9e"};background:${key === sectorView ? "#f3da9e" : "transparent"};padding:9px 12px;text-decoration:none;font:14px system-ui;border-radius:5px`;
			sectorViews.append(link);
		}
		document.body.append(sectorViews);
		const previewStyle = document.createElement("style");
		previewStyle.textContent = "#hud > :not(#performance-stats), #world-vignette, #screen-hurt, #rotate-device, #toast, .enemy-label {display:none!important}";
		document.head.append(previewStyle);
		scene.onDisposeObservable.add(() => { badge.remove(); sectorViews.remove(); previewStyle.remove(); });
	}

	const materials = createActorMaterials(scene);
	const environment = await createEnvironment(
		scene,
		materials,
		cityGateZ,
		(mesh) => warmSceneShaders(scene, [mesh]),
		terrainCells,
		worldProps,
		worldHalfExtent,
		cityTraversal?.bounds,
		quality,
		(x, z) => cityTraversal ? sampleCityHeight(cityTraversal, x, z) : 0,
	);
	// Begin preparation on the approach, while the proxy still provides a complete town.
	const requestCityUpgradeAtGate = createGateTriggeredLoader(cityGateZ - 24, environment.ensureDetailedCity);
	let cityPreparationAllowed = false;
	const residents = new Map(cityNpcs.map(definition => [definition.id, createCityNpc(scene, definition, {
		low: quality.preset === 'low' || quality.formFactor === 'mobile', preview: cityOverview,
		addShadowCaster: environment.addShadowCaster, prepare: async meshes => {
			for (const mesh of meshes) if (mesh.material && mesh.getTotalVertices() > 0) await mesh.material.forceCompilationAsync(mesh);
		},
	})]));
	const requestSouthboundCells = createSouthboundCellLoader(-40, environment.ensureTerrainCells);
	const coordinateFixtureRoute = import.meta.env.DEV && new URLSearchParams(location.search).get("coordinateFixture") === "1";
	const collisionBoxes = coordinateFixtureRoute
		? createCoordinateObstacles(scene, materials, fixture)
		: staticColliderBoxes(staticColliders);
	const guide = routeNpc ? createRouteGuideActor(scene, materials, routeNpc.id) : null;
	if (guide && routeNpc) {
		stripFakeShadows(guide, materials);
		environment.addShadowCaster(guide);
		guide.position.set(routeNpc.x, 0, routeNpc.z);
		try {
			const asset = await SceneLoader.ImportMeshAsync("", "", villageLanternAssetUrl, scene);
			const lantern = new TransformNode("prop-village-lantern-01", scene);
			for (const node of [
				...asset.transformNodes.filter((node) => !node.parent),
				...asset.meshes.filter((mesh) => !mesh.parent),
			]) node.parent = lantern;
			lantern.position.set(routeNpc.x + 2.6, 0, routeNpc.z - 0.3);
			for (const mesh of asset.meshes) {
				mesh.isPickable = false;
				mesh.receiveShadows = true;
			}
			environment.addShadowCaster(lantern);
		} catch (error) {
			console.warn("Village lantern asset unavailable; continuing without the decorative prop.", error);
		}
		try {
			const asset = await SceneLoader.ImportMeshAsync("", "", wayfarerKitAssetUrl, scene);
			const placements = [
				["prop_wayfinder_sign_01", [[routeNpc.x - 6.8, routeNpc.z - 1.5]]],
				["prop_village_banner_01", [[routeNpc.x - 6.9, routeNpc.z - 10], [routeNpc.x + 2.9, routeNpc.z - 10]]],
				["prop_flower_planter_01", [[routeNpc.x - 6.7, routeNpc.z - 5.5], [routeNpc.x + 2.7, routeNpc.z - 5.5]]],
			] as const;
			const sources = new Map(asset.meshes
				.filter((mesh): mesh is Mesh => mesh instanceof Mesh)
				.map((mesh) => [mesh.name, mesh] as const));
			if (placements.some(([name]) => !sources.has(name))) {
				for (const mesh of asset.meshes) mesh.dispose();
				throw new Error("Wayfarer kit is missing an expected prop mesh.");
			}
			// Decorative only: keep the central starter path clear and do not add collision.
			for (const [name, locations] of placements) {
				const source = sources.get(name)!;
				source.isVisible = false;
				source.isPickable = false;
				source.receiveShadows = true;
				for (const [index, [x, z]] of locations.entries()) {
					const instance = source.createInstance(`${name}-${index}`);
					// The imported glTF root flips X; place instances in world space.
					instance.setAbsolutePosition(new Vector3(x, 0, z));
					instance.isPickable = false;
				}
			}
		} catch (error) {
			console.warn("Wayfarer kit unavailable; continuing without the decorative props.", error);
		}
	}
	const routeMarkers = new Map<string, ReturnType<typeof createWindmarkActor>>();
	for (const marker of markers.filter((point) => point.id.startsWith("windmark_"))) {
		const windmark = createWindmarkActor(scene, materials, marker.id);
		stripFakeShadows(windmark.root, materials);
		environment.addShadowCaster(windmark.root);
		windmark.root.position.set(marker.x, 0, marker.z);
		routeMarkers.set(marker.id, windmark);
	}

	const localRoot = new TransformNode("hero-local", scene);
	const heroReview=heroReviewIdentity(mageTrialRequested?'?heroReview=02':location.search,import.meta.env.DEV);
	const requestedHeroPack=new URLSearchParams(location.search).get('heroPack');
	const heroAsset = heroReview ? await (await import('./hero-review-loader')).loadHeroReview(scene,heroReview.id,requestedHeroPack==='r04'?'r04':requestedHeroPack==='r03'?'r03':requestedHeroPack==='r02'?'r02':'r01') : await SceneLoader.ImportMeshAsync("", "", quaterniusWarriorAssetUrl, scene, progress => {
		const event=bootstrapAssetProgress('starter-character',progress); if(event)onBootstrapProgress?.(event);
	});
	const importedRoots = [
		...heroAsset.transformNodes.filter((node) => !node.parent),
		...heroAsset.meshes.filter((mesh) => !mesh.parent),
	];
	for (const node of new Set(importedRoots)) node.parent = localRoot;
	localRoot.scaling.setAll((heroReview?.scale??0.9)*framing.avatarScale);
	for (const mesh of heroAsset.meshes) {
		mesh.isPickable = false;
		mesh.receiveShadows = true;
	}
	const heroAnimations = new Map(heroAsset.animationGroups.map((group) => [group.name, group]));
	let currentHeroAnimation = "";
	let wantedHeroMotion: "idle" | "run" = "idle";
	let localPresentationPaused = false;
	const pausedHeroSpeeds = new Map<import('@babylonjs/core/Animations/animationGroup').AnimationGroup,number>();
	const playHeroClip = (name: string, loop: boolean) => {
		const next = heroAnimations.get(name);
		if (!next || currentHeroAnimation === name && next.isPlaying) return;
		for (const group of heroAnimations.values()) group.stop();
		currentHeroAnimation = name;
		next.start(loop, 1);
		if(localPresentationPaused){pausedHeroSpeeds.set(next,1);next.speedRatio=0;}
	};
	const isHeroAttack=(name:string)=>(heroReview?.isAttack(name)??name.startsWith('Sword_Attack'))||(mageTrialRequested&&name==='mage.skill_bolt');
	const playHeroLocomotion = () => playHeroClip(wantedHeroMotion === "run" ? heroReview?.run??"Run_Weapon" : heroReview?.idle??"Idle_Weapon", true);
	playHeroLocomotion();
	stripFakeShadows(localRoot, materials);
	environment.addShadowCaster(localRoot);
	const remotePlayers = new Map<number, TransformNode>();
	const slimes = new Map<number, { root: TransformNode; body: TransformNode; material: Material; hp: EnemyHealthLabel; standin?: MonsterStandinView }>();
	const groundAt = (x: number, z: number) => cityTraversal ? sampleCityHeight(cityTraversal, x, z) : 0;
	const combatFx = createCombatFx(scene, { groundAt, lowDetail: quality.preset === "low" || quality.formFactor === "mobile" });
	const ambientFx = createAmbientWorld(scene, { cityCenterZ: cityGateZ + 152, cityBounds: cityTraversal?.bounds });
	ambientFx.setQuality(quality);
	const atmosphereV2=import.meta.env.DEV&&new URLSearchParams(location.search).get('atmosphere')==='v2';
	const atmosphere=atmosphereV2?createAmbientAtmosphere(scene,{
		quality,focus:()=>localRoot.position,groundAt:(x,z)=>{
			// Until the water lane supplies a surface classifier, contacts are limited to known land.
			if(x < -35 || (cityTraversal&&z>=cityTraversal.bounds.minZ))return null;
			return groundAt(x,z);
		},clusters:[
			{x:-43,y:0,z:2,radius:4,kind:'water'},
			{x:37,y:0,z:-5,radius:3,kind:'vegetation'},
			{x:-14,y:0,z:-65,radius:1.4,kind:'vegetation'},
			{x:14,y:0,z:-65,radius:1.4,kind:'vegetation'},
			{x:-28,y:0,z:-35,radius:2.5,kind:'vegetation'},
		],
	}):null;
	if(atmosphere){environment.useExternalRain();void atmosphere.prewarm().catch(error=>console.warn('[atmosphere] shader warm-up failed',error));}
	combatFx.attachSword(heroAsset.meshes.find((mesh): mesh is Mesh => mesh instanceof Mesh && mesh.name === "Warrior_Sword") ?? null);
	if(heroReview?.id==='01'&&'weaponOwner' in heroAsset&&heroAsset.weaponOwner instanceof TransformNode)combatFx.attachWeaponMarkers(heroAsset.weaponOwner);
	const combatLabels = createWorldCombatLabels(scene, enemies.map(enemy => enemy.name), { groundAt });
	let reduceCombatMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
	combatLabels.configure({mobile:quality.formFactor==='mobile',locale:document.documentElement.lang==='th'?'th':'en',reduceMotion:reduceCombatMotion});
	const actorFeedback = new Map<number,ReturnType<typeof createActorFeedback>>();
	const previousMonsterActive = new Map<number,boolean>();
	const dropEntities = new Map<string, { root: TransformNode; gem: Mesh; ring: Mesh; item: string }>();
	const getDropMat = (itemId: string): StandardMaterial => {
		if (itemId.includes("box")) return materials.flowerGold;
		if (itemId.includes("blade") || itemId.includes("vest") || itemId.includes("armor")) return materials.roofLight;
		if (itemId.includes("potion") || itemId.includes("root") || itemId.includes("plume")) return materials.leavesLight;
		return materials.windmark;
	};
	const monsterNames = new Map(enemyKinds.map(enemy=>[enemy.kind,enemy.name]));
	const monsterReview = import.meta.env.DEV && new URLSearchParams(location.search).get('dressing') === 'v3'
		&& new URLSearchParams(location.search).get('monsterStandins') !== 'off';
	const standinKit = monsterReview ? await preloadMonsterStandins(scene) : null;
	const monsterViews = createMonsterViewRegistry<{id:number;kind:number;x:number;z:number;hp:number;max_hp:number;active:boolean;facing?:number},typeof slimes extends Map<number,infer V> ? V : never>({
		create(monster) {
			const standin = standinKit && monster.kind >= 1 && monster.kind <= 4 ? standinKit.create(monster.kind,monster.id) : undefined;
			const {root,body,material}=standin ?? createSlimeActor(scene,materials,`monster-${monster.id}`);
			const visual=standin?.visual ?? new TransformNode(`monster-${monster.id}-visual`,scene);
			if(!standin){visual.parent=root;body.parent=visual;}
			body.metadata={monsterId:monster.id};
			stripFakeShadows(root,materials);
			if(!standin)environment.addShadowCaster(root);
			root.position.set(monster.x,groundAt(monster.x,monster.z)??0,monster.z);
			root.metadata={monsterId:monster.id,kind:monster.kind,name:monsterNames.get(monster.kind)??`#${monster.kind}`,visualStatus:standin?'CC0_INTERIM':'LEGACY_PROXY'};
			const hp=combatLabels.createEnemyLabel(root,0);
			actorFeedback.set(monster.id,createActorFeedback(scene,visual,standin?.materials ?? [material],{rank:enemyKinds.find(enemy=>enemy.kind===monster.kind)?.rank,reduceMotion:()=>reduceCombatMotion}));
			previousMonsterActive.set(monster.id,monster.active);
			const view={root,body,material,hp,standin};slimes.set(monster.id,view);return view;
		},
		update(item,monster) {
			item.root.position.x+=(monster.x-item.root.position.x)*.5;
			item.root.position.z+=(monster.z-item.root.position.z)*.5;
			if(monster.facing!==undefined)item.root.rotation.y=monster.facing;
			const feedback=actorFeedback.get(monster.id)!;
			if(monster.active && !previousMonsterActive.get(monster.id))feedback.respawn();
			if(!monster.active && previousMonsterActive.get(monster.id))feedback.die();
			previousMonsterActive.set(monster.id,monster.active);
			item.root.setEnabled(monster.active || feedback.dying && !feedback.finished);
			item.hp.setHealth(monster.hp,monster.max_hp,monster.active);
		},
		dispose(item,id) {
			actorFeedback.get(id)?.dispose();actorFeedback.delete(id);previousMonsterActive.delete(id);
			item.hp.dispose();
			// Actor eye/belly materials are shared across the kit; only its cloned body material is owned.
			if(item.standin)item.standin.dispose();else{item.root.dispose(false,false);item.material.dispose();}
			slimes.delete(id);
		},
	});
	monsterViews.synchronize(enemies.map(enemy=>({id:enemy.id,kind:enemy.kind,x:enemy.x,z:enemy.z,hp:enemy.hp,max_hp:enemy.hp,active:true})));

	const cameraRig = new CameraRig(camera);
	const slashArc = new SlashArc(scene, combatFx);

	scene.onBeforeRenderObservable.add(() => {
		const now = performance.now() * 0.001;
		if (cityTraversal) {
			const floor = sampleCityHeight(cityTraversal, localRoot.position.x, localRoot.position.z);
			if (floor !== null) localRoot.position.y = floor + cityTraversal.feetOffsetM;
		} else { localRoot.position.y = heroReview ? 0 : Math.sin(now * 2.1) * 0.035 + .02; }
		if (guide) guide.position.y = Math.sin(now * 1.8) * 0.025;
		for (const [index, marker] of [...routeMarkers.values()].entries()) {
			marker.crystal.position.y = 1.05 + Math.sin(now * 1.4 + index) * 0.09;
		}
		const cameraForwardX = -Math.cos(camera.alpha);
		const cameraForwardZ = -Math.sin(camera.alpha);
		if (!cityOverview && !southSectorPreview && !lookdev) {
			cameraRig.setTarget(
				localRoot.position.x + cameraForwardX * framing.lookAhead,
				localRoot.position.y + framing.targetHeight,
				localRoot.position.z + cameraForwardZ * framing.lookAhead,
			);
			cameraRig.update(localPresentationPaused ? 0 : scene.getEngine().getDeltaTime() / 1000);
		}
		for (const [index, item] of [...slimes.values()].entries()) {
			item.root.position.y = (groundAt(item.root.position.x,item.root.position.z)??0)+(item.standin ? .015 : Math.abs(Math.sin(now * 2.6 + index))*.12);
			if(item.standin)item.standin.tick(now*1000,reduceCombatMotion);
			else item.body.rotation.y = Math.sin(now * 0.7 + index) * 0.08;
		}
		for (const [index, drop] of [...dropEntities.values()].entries()) {
			drop.gem.rotation.y = now * 2.8 + index;
			drop.gem.position.y = 0.42 + Math.sin(now * 3.5 + index * 1.5) * 0.08;
			const scale = 0.95 + Math.sin(now * 2.5 + index) * 0.1;
			drop.ring.scaling.set(scale, 1, scale);
		}
	});

	onBootstrapProgress?.({id:'assets',state:'complete'});
	onBootstrapProgress?.({id:'shaders',state:'active'});
	await Promise.all([combatFx.prewarm(),combatLabels.prewarm()]);
	await Promise.all([...actorFeedback.values()].map(feedback=>feedback.prewarm()));
	let mageNowMs=0,mageActorId=0;
	let mageFx:ReturnType<typeof import('./mage-pilot-fx')['createMagePilotFx']>|null=null;
	let mageMotion:typeof import('./mage-pilot-fx')['magePilotMotion']|null=null;
	let mageCastOrigin:((actorId:number)=>Readonly<{x:number;y:number;z:number}>|null)|null=null;
	let disposeMageMotionEnd:(()=>void)|null=null;
	const clearMageMotionEnd=()=>{disposeMageMotionEnd?.();disposeMageMotionEnd=null;};
	const mageWeapon='weaponOwner' in heroAsset&&heroAsset.weaponOwner instanceof TransformNode?heroAsset.weaponOwner:null;
	if(mageTrialRequested&&mageWeapon){
		const {createMagePilotFx,magePilotMotion}=await import('./mage-pilot-fx');mageMotion=magePilotMotion;
		const markers=resolveWeaponFxMarkers(mageWeapon,['fx_head']);
		mageCastOrigin=actorId=>actorId===mageActorId?markers.position('fx_head'):null;
		mageFx=createMagePilotFx(scene,{now:()=>mageNowMs,groundAt,castOrigin:actorId=>typeof actorId==='number'?mageCastOrigin?.(actorId)??null:null,lowEffects:()=>quality.preset==='low'});
		mageWeapon.setEnabled(false);await mageFx.prewarm();
		if(import.meta.env.DEV)Object.assign((window as unknown as {__xexoria:object}).__xexoria,{magePilot:()=>({stats:mageFx?.stats(),staffHead:markers.position('fx_head'),weaponVisible:mageWeapon.isEnabled()})});
	}
	await warmSceneShaders(scene, [...combatFx.prewarmMeshes(), ...ambientFx.prewarmMeshes()]);
	const disposeTextureCacheRelease=installReadyTextureCacheRelease(scene);
	if (import.meta.env.DEV && new URLSearchParams(location.search).has("vfxdemo")) {
		const { installCombatVfxDemo } = await import("./combat-vfx-demo");
		const weaponMarkers='weaponOwner' in heroAsset&&heroAsset.weaponOwner instanceof TransformNode?resolveWeaponFxMarkers(heroAsset.weaponOwner,['fx_head']):null;
		await installCombatVfxDemo({ scene, player: localRoot, camera, groundAt, preset: () => quality.preset,castOrigin:weaponMarkers?()=>weaponMarkers.position('fx_head'):undefined });
		await warmSceneShaders(scene, [...combatFx.prewarmMeshes(), ...ambientFx.prewarmMeshes()]);
	}
	if (import.meta.env.DEV && new URLSearchParams(location.search).get("renderProfile") === "1") {
		const { installRenderDiagnostics } = await import("./render-diagnostics");
		installRenderDiagnostics(scene);
	}
	// A loss during async asset/shader preparation must not restart a released renderer.
	if(isRendererResetRequired(engine))throw new Error('Graphics reset during loading. Reload and reconnect to receive current server state.');
	let frameUpdate:(()=>void)|null=null;
	let renderPaused=false;
	let worldDisposed=false;
	const readFrameRateSetting=():FrameRateSetting=>{
		try{return parseStoredFrameRateSetting(localStorage.getItem(FRAME_RATE_STORAGE_KEY));}catch{return 'auto';}
	};
	const publishFrameRate=():void=>{
		const state=framePolicy.state();
		window.dispatchEvent(new CustomEvent(FRAME_RATE_STATE_EVENT,{detail:Object.freeze({
			setting:state.setting,capFps:state.capFps,rafHz:state.refreshDetected?state.rafHz:null,
			refreshHz:state.refreshDetected?state.refreshHz:null,browserCap30:state.browserCap30,
			lowPowerSuspected:state.lowPowerSuspected,thermalSuspected:state.thermalSuspected,
			optIn:state.optIn,lastChangeReason:state.lastChange?.reason??null,options:describeFrameRateOptions(state),
		})}));
	};
	const framePolicy=createFrameRatePolicy({setting:readFrameRateSetting(),tierTargetFps:quality.targetFps,
		formFactor:quality.formFactor,autoCeilingFps:quality.autoCeilingFps,onChange:publishFrameRate});
	const pacedRequester=createPacedFrameRequester({policy:framePolicy,
		requestFrame:callback=>window.requestAnimationFrame(callback),cancelFrame:handle=>window.cancelAnimationFrame(handle),now:()=>performance.now()});
	engine.customAnimationFrameRequester=pacedRequester;
	const onFrameVisibility=():void=>framePolicy.notifyVisibility(document.visibilityState==='hidden',performance.now());
	document.addEventListener('visibilitychange',onFrameVisibility);
	let dprQuery=matchMedia(`(resolution: ${devicePixelRatio}dppx)`);
	const onScreenChange=():void=>{
		framePolicy.notifyScreenChange(performance.now());
		dprQuery.removeEventListener('change',onScreenChange);
		dprQuery=matchMedia(`(resolution: ${devicePixelRatio}dppx)`);
		dprQuery.addEventListener('change',onScreenChange);
	};
	dprQuery.addEventListener('change',onScreenChange);
	const display=screen as Screen&Partial<EventTarget>;
	display.addEventListener?.('change',onScreenChange);
	const onFrameRateSetting=(event:Event):void=>{
		framePolicy.setSetting((event as CustomEvent<{setting?:FrameRateSetting}>).detail?.setting??'auto',performance.now());
	};
	window.addEventListener(FRAME_RATE_SETTING_EVENT,onFrameRateSetting);
	onFrameVisibility();
	publishFrameRate();
	let renderScaling:RenderScalingHandle|null=null;
	// FSR 1 stays opt-in. Deferred installation cannot revive a lost or disposed renderer.
	if(new URLSearchParams(location.search).has('fsr'))void import('./render-scaling').then(({installRenderScalingFromQuery})=>{
		if(worldDisposed || scene.isDisposed || isRendererResetRequired(engine))return;
		renderScaling=installRenderScalingFromQuery(scene,{targetFps:()=>framePolicy.targetFps,
			frameSample:()=>renderPaused?null:framePolicy.lastFrameIntervalMs});
	}).catch((error:unknown)=>console.warn('Render scaling unavailable; rendering at native size.',error));
	let lastScaleSignalAt=0;
	let countedFrames = 0;
	onBootstrapProgress?.({id:'shaders',state:'complete'});
	let counterStarted = performance.now();
	let renderedFps = 0;
	if(import.meta.env.DEV && new URLSearchParams(location.search).get('renderHealth')==='1'){
		const {installRendererHealthProbe}=await import('./renderer-health-probe');installRendererHealthProbe(scene);
	}
	// Until SC2's facade lands, use the already-tested local collector directly. No second render loop.
	if(new URLSearchParams(location.search).get('perf')==='1'){
		const [{createBabylonPerfSource},{installPerfOverlay}]=await Promise.all([import('./perf/babylon-source'),import('./perf/controller')]);
		if(!worldDisposed && !scene.isDisposed && !isRendererResetRequired(engine)){
			const source=createBabylonPerfSource(scene);
			const overlay=installPerfOverlay({readState:()=>{
				const rate=framePolicy.state(),scale=renderScaling?.stats();
				return {...source.readState(),preset:quality.preset,targetFps:rate.capFps,rafHz:rate.rafHz,browserCap30:rate.browserCap30,
					renderWidth:scale?.allocatedWidth??engine.getRenderWidth(),renderHeight:scale?.allocatedHeight??engine.getRenderHeight(),
					fsrActive:scale?.active??false,fsrScale:scale?.scale??1,rendererHealth:getRendererHealth(engine)?.status??null};
			}});
			const observer=scene.onAfterRenderObservable.add(()=>{overlay?.recordFrame(source.readFrame(performance.now()));});
			scene.onDisposeObservable.addOnce(()=>{scene.onAfterRenderObservable.remove(observer);overlay?.dispose();source.dispose();});
		}
	}
	engine.runRenderLoop(() => {
		const now = performance.now();
		if(worldDisposed || isRendererResetRequired(engine))return;
		frameUpdate?.();
		if(!renderPaused && !scene.isDisposed){
			scene.render();countedFrames++;
			if(now-lastScaleSignalAt>=250){lastScaleSignalAt=now;framePolicy.observeScale(renderScaling?.stats().controller??null,now);}
		}
		if (now - counterStarted >= 1000) {
			renderedFps = countedFrames * 1000 / (now - counterStarted); countedFrames = 0; counterStarted = now;
		}
	});
	const applyQuality = () => {
		quality = resolveQuality(); engine.maxFPS = undefined;
		framePolicy.setTier({targetFps:quality.targetFps,formFactor:quality.formFactor,autoCeilingFps:quality.autoCeilingFps},performance.now());
		combatLabels.configure({mobile:quality.formFactor==='mobile'});
		engine.setHardwareScalingLevel(quality.hardwareScalingLevel); engine.resize();
		environment.applyGraphics(quality);
		combatFx.setLowDetail(quality.preset === "low" || quality.formFactor === "mobile");
		ambientFx.setQuality(quality);
		atmosphere?.setQuality(quality);
	};
	const unsubscribeQuality = subscribeGraphicsPreference(applyQuality);
	const resize = () => {
		applyQuality();
		framePolicy.notifyResize(performance.now());
		cameraRig.setBaseFov(canvas.clientHeight > canvas.clientWidth ? 0.98 : 1.02);
	};
	window.addEventListener("resize", resize, { passive: true });

	return {
		playNpcGreeting(id) { residents.get(id)?.speak(); },
		engine,
		scene,
		camera,
		cameraRig,
		slashArc,
		localRoot,
		setMageTrialContext(actorId,serverNowMs,focusEquipped){
			if(!Number.isFinite(serverNowMs)||serverNowMs<0)return;mageActorId=actorId;mageNowMs=serverNowMs;
			if(mageTrialRequested)mageWeapon?.setEnabled(focusEquipped);
		},
		beginMageCast(state){
			if(!mageFx||!mageMotion||state.source_id!==mageActorId||(state.impact_ms!==null&&mageNowMs>=state.impact_ms))return;
			const cue={castId:state.cast_id,actorId:state.source_id,ability:state.skill_id,targetXZ:{x:state.target[0],z:state.target[2]},startedAt:state.start_ms,releaseAt:state.release_ms,impactAt:state.impact_ms,facing:Math.atan2(state.target[0]-state.origin[0],state.target[2]-state.origin[2]),deferReleaseUntilConfirmed:state.impact_ms===null};
			const motion=mageMotion(cue),clip=heroAnimations.get(motion.clip);
			if(clip){
				clearMageMotionEnd();
				for(const group of heroAnimations.values())group.stop();currentHeroAnimation=clip.name;
				const end=clip.onAnimationGroupEndObservable.addOnce(()=>{disposeMageMotionEnd=null;if(currentHeroAnimation===clip.name)playHeroLocomotion();});
				disposeMageMotionEnd=()=>clip.onAnimationGroupEndObservable.remove(end);
				clip.start(false,motion.speedRatio);const fps=clip.targetedAnimations[0]?.animation.framePerSecond??60;
				clip.goToFrame(Math.min(clip.to,clip.from+Math.max(0,mageNowMs-state.start_ms)/1000*fps*motion.speedRatio));
			}
			mageFx.beginAcceptedCast(cue);
		},
		releaseMageCast(state){
			if(state.impact_ms===null)return;
			// Staff origin is presentation only; the server's collision path and damage remain authoritative.
			const origin=mageCastOrigin?.(state.source_id)??{x:state.origin[0],y:state.origin[1],z:state.origin[2]};
			mageFx?.confirmReleasedCast({castId:state.cast_id,origin,targetXZ:{x:state.target[0],z:state.target[2]},releaseAt:state.release_ms,impactAt:state.impact_ms});
		},
		resolveMageCast(state){
			let contactRadius:number|undefined;
			if(state.phase==='impact'&&state.damage>0){const body=slimes.get(state.target_id)?.body;if(body){body.computeWorldMatrix(true);const bounds=body instanceof Mesh?{min:body.getBoundingInfo().boundingBox.minimumWorld,max:body.getBoundingInfo().boundingBox.maximumWorld}:body.getHierarchyBoundingVectors();const extent=Math.max(bounds.max.x-bounds.min.x,bounds.max.z-bounds.min.z);if(Number.isFinite(extent))contactRadius=Math.min(4,Math.max(.25,extent/2+.12));}}
			mageFx?.resolve({castId:state.cast_id,outcome:state.phase==='impact'?(state.damage>0?'hit':'miss'):'cancelled',targetXZ:{x:state.target[0],z:state.target[2]},...(contactRadius===undefined?{}:{contactRadius})});
			if(state.phase==='cancelled'||state.phase==='rejected'){clearMageMotionEnd();for(const group of heroAnimations.values())group.stop();currentHeroAnimation='';playHeroLocomotion();}
		},
		clearMagePresentation(){mageFx?.clear();clearMageMotionEnd();if(mageTrialRequested){for(const group of heroAnimations.values())group.stop();currentHeroAnimation='';playHeroLocomotion();}},
		setWorldTick: environment.setWorldTick,
		getRenderFps: () => renderedFps,
		getGraphicsTier: () => quality.preset,
		getGraphicsDiagnostics: () => ({profile:{...quality},frameCap:framePolicy.capFps,frameRate:framePolicy.state(),environment:environment.graphicsDiagnostics()}),
		setFrameUpdate(callback){if(!worldDisposed)frameUpdate=callback;},
		setPaused(paused){if(!worldDisposed)renderPaused=paused;},
		setHeroMotion(motion) {
			wantedHeroMotion = motion;
			if (localPresentationPaused) return;
			if (isHeroAttack(currentHeroAnimation)) {
				const active = heroAnimations.get(currentHeroAnimation);
				if (active?.isPlaying) return;
			}
			playHeroLocomotion();
		},
		setLocalPresentationPaused(paused) {
			if(paused===localPresentationPaused)return;localPresentationPaused=paused;
			if(paused) {
				for(const group of heroAnimations.values())if(group.isPlaying){pausedHeroSpeeds.set(group,group.speedRatio);group.speedRatio=0;}
			}else{
				for(const [group,speed]of pausedHeroSpeeds)group.speedRatio=speed;
				pausedHeroSpeeds.clear();
				if(!isHeroAttack(currentHeroAnimation))playHeroLocomotion();
			}
		},
		playHeroAttack() {
			const attack = heroAnimations.get(heroReview?.attacks[0]??"Sword_Attack") ?? heroAnimations.get(heroReview?.attacks[1]??"Sword_Attack2");
			if (!attack) return;
			for (const group of heroAnimations.values()) group.stop();
			currentHeroAnimation = attack.name;
			attack.onAnimationEndObservable.addOnce(() => {
				if (currentHeroAnimation === attack.name) playHeroLocomotion();
			});
			attack.start(false, 1);
			if(localPresentationPaused){pausedHeroSpeeds.set(attack,1);attack.speedRatio=0;}
			combatFx.beginBladeSwing();
		},
		remotePlayers,
		cityDetailState: environment.cityDetailState,
		ensureDetailedCity: environment.ensureDetailedCity,
		ensureTerrainCells: environment.ensureTerrainCells,
		revealDetailedCity: environment.revealDetailedCity,
		waitingForCity: () => localRoot.position.z >= cityGateZ - 24 && ["idle", "loading", "prepared"].includes(environment.cityDetailState()),
		allowCityPreparation() { cityPreparationAllowed = true; },
		slimes,
		collisionBoxes,
		playerRadius: fixture.player_capsule.radius,
		playerHeight: fixture.player_capsule.height,
		setLocalPosition(x, z) {
			localRoot.position.x = x;
			localRoot.position.z = z;
			const request = cityPreparationAllowed ? requestCityUpgradeAtGate(z) : undefined;
			if (request) {
				void request.catch((error: unknown) => {
					console.warn("Detailed R5 city load failed; the meadow HLOD remains visible.", error);
				});
			}
			const cellRequest = requestSouthboundCells(z);
			if (cellRequest) {
				void cellRequest.catch((error: unknown) => {
					console.warn("Southbound terrain details failed to load; the flat connector remains walkable.", error);
				});
			}
		},
		placeRemote(id, x, z, connected) {
			let root = remotePlayers.get(id);
			if (!root) {
				root = createHeroActor(scene, materials, `hero-${id}`, new Color3(0.58, 0.35, 0.63));
				root.scaling.scaleInPlace(framing.avatarScale);
				stripFakeShadows(root, materials);
				environment.addShadowCaster(root);
				remotePlayers.set(id, root);
			}
			root.position.x = x;
			root.position.z = z;
			if (cityTraversal) {
				const floor = sampleCityHeight(cityTraversal, x, z);
				if (floor !== null) root.position.y = floor + cityTraversal.feetOffsetM;
			}
			root.setEnabled(connected);
		},
		removeRemote(id) {
			const root = remotePlayers.get(id);
			if (root) {
				root.dispose(false, true);
				remotePlayers.delete(id);
			}
		},
		setMonsters(monsters) {
			monsterViews.synchronize(monsters);
		},
		flashMonster(id, strong = false,attacker) {
			const item = slimes.get(id);
			if (!item) return;
			const source=attacker??{x:localRoot.position.x,z:localRoot.position.z,relation:'mine' as const};
			actorFeedback.get(id)?.hit(strong?'crit':'light',source.x,source.z);
			const point = item.body.getAbsolutePosition().clone();
			if(item.standin)point.y+=.4;
			combatFx.hitBurst(point.x, point.y, point.z, source.x,source.z,strong,source.relation);
		},
		animateMonsterHop(id, phase) {
			const item = slimes.get(id);
			if (!item) return;
			if(actorFeedback.get(id)?.dying)return;
			if(item.standin){item.standin.setPhase(phase);return;}
			switch (phase) {
				case "windup":
					item.body.scaling.set(1.4, 0.42, 1.3);
					item.body.position.y = 0.28;
					break;
				case "leap":
					item.body.scaling.set(0.85, 1.45, 0.85);
					item.body.position.y = 2.0;
					break;
				case "impact":
					item.body.scaling.set(1.5, 0.38, 1.4);
					item.body.position.y = 0.25;
					break;
				case "recovery":
					item.body.scaling.set(1.2, 0.52, 1.15);
					item.body.position.y = 0.35;
					break;
				case "idle":
				default:
					item.body.scaling.set(1.05, 0.72, 0.9);
					item.body.position.y = 0.52;
					break;
			}
		},
		createSplashTelegraph(x, z, radius = 2.5, durationMs = 900) {
			return combatFx.createSplashTelegraph(x, z, radius, durationMs);
		},
		setQuestProgress(activatedWindmarks) {
			const activated = new Set(activatedWindmarks);
			for (const [id, marker] of routeMarkers) {
				const isActivated = activated.has(id);
				marker.crystal.material = isActivated ? materials.metal : materials.windmark;
				marker.ring.material = isActivated ? materials.flowerGold : materials.windmark;
			}
		},
		updateDrops(entries) {
			const activeIds = new Set(entries.map((e) => e.encounter));
			for (const [id, drop] of dropEntities) {
				if (!activeIds.has(id)) {
					drop.root.dispose(false, true);
					dropEntities.delete(id);
				}
			}
			for (const entry of entries) {
				if (!dropEntities.has(entry.encounter)) {
					const root = new TransformNode(`drop-${entry.encounter}`, scene);
					root.position.set(entry.x, 0, entry.z);
					const mat = getDropMat(entry.item);
					const gem = MeshBuilder.CreatePolyhedron(`gem-${entry.encounter}`, { type: 1, size: 0.22 }, scene);
					gem.material = mat;
					gem.position.y = 0.42;
					gem.parent = root;
					const ring = MeshBuilder.CreateTorus(`ring-${entry.encounter}`, { diameter: 0.55, thickness: 0.04, tessellation: 12 }, scene);
					ring.position.y = 0.05;
					ring.rotation.x = Math.PI / 2;
					ring.material = mat;
					ring.parent = root;
					dropEntities.set(entry.encounter, { root, gem, ring, item: entry.item });
				}
			}
		},
		clearDrops() {
			for (const drop of dropEntities.values()) drop.root.dispose(false, true);
			dropEntities.clear();
		},
		showDamage: combatLabels.showDamage,
		showCombatWord:combatLabels.showWord,
		configureCombatPresentation(preferences){
			if(preferences.reduceMotion!==undefined)reduceCombatMotion=preferences.reduceMotion;
			if(preferences.lowEffects!==undefined)combatFx.setLowEffects(preferences.lowEffects);
			cameraRig.setShakeEnabled((preferences.screenShake??true)&&!reduceCombatMotion);
			combatLabels.configure(preferences);combatFx.setHideOtherEffects(preferences.showOthers===false);
		},
		releasePreparedStaticCaches(auditedMeshes){return releasePreparedStaticGeometry(scene,auditedMeshes);},
		dispose() {
			if(worldDisposed)return;worldDisposed=true;frameUpdate=null;
			disposeTextureCacheRelease();
			unsubscribeQuality();
			window.removeEventListener("resize", resize);
			document.removeEventListener('visibilitychange',onFrameVisibility);
			dprQuery.removeEventListener('change',onScreenChange);
			display.removeEventListener?.('change',onScreenChange);
			window.removeEventListener(FRAME_RATE_SETTING_EVENT,onFrameRateSetting);
			slashArc.dispose();
			combatFx.dispose();
			clearMageMotionEnd();mageFx?.dispose();
			ambientFx.dispose();
			monsterViews.dispose();
			standinKit?.dispose();
			combatLabels.dispose();
			for (const remote of remotePlayers.values()) remote.dispose(false, true);
			for (const drop of dropEntities.values()) drop.root.dispose(false, true);
			dropEntities.clear();
			scene.dispose();
			engine.dispose();
			// Babylon cancels through this requester; keep it attached until engine disposal.
			pacedRequester.dispose();
		},
	};
}

async function warmSceneShaders(scene: Scene, includeHiddenMeshes: readonly Mesh[] = []): Promise<void> {
	const variants = new Map<string, { material: NonNullable<Mesh["material"]>; mesh: Mesh; useInstances: boolean }>();
	const forceIncluded = new Set(includeHiddenMeshes);
	const addVariant = (material: Material | null, mesh: Mesh, useInstances: boolean) => {
		if (!material) return;
		const key = `${material.uniqueId}:${mesh.useVertexColors ? 1 : 0}:${mesh.skeleton?.bones.length ?? 0}:${useInstances ? 1 : 0}`;
		if (!variants.has(key)) variants.set(key, { material, mesh, useInstances });
	};
	for (const candidate of scene.meshes) {
		if (!(candidate instanceof Mesh)) continue;
		const mesh = candidate;
		if ((!mesh.isVisible && !mesh.hasInstances && !mesh.hasThinInstances && !forceIncluded.has(mesh)) || !mesh.isEnabled() || mesh.getTotalVertices() === 0 || !mesh.material) continue;
		const useInstances = mesh.hasInstances || mesh.hasThinInstances;
		if (mesh.material instanceof MultiMaterial) {
			for (const subMesh of mesh.subMeshes) addVariant(mesh.material.getSubMaterial(subMesh.materialIndex), mesh, useInstances);
		} else {
			addVariant(mesh.material, mesh, useInstances);
		}
	}

	const compileJobs = [...variants.values()];
	for (let index = 0; index < compileJobs.length; index += 2) {
		await Promise.all(compileJobs.slice(index, index + 2).map(async ({ material, mesh, useInstances }) => {
			try {
				await material.forceCompilationAsync(mesh, { useInstances });
			} catch (error) {
				console.warn(`Shader warm-up skipped for ${material.name}.`, error);
			}
		}));
	}
}

function createCoordinateObstacles(
	scene: Scene,
	materials: Record<string, StandardMaterial>,
	fixture: CoordinateFixture,
): CollisionBox[] {
	const colliders: CollisionBox[] = [];
	const cubeSpec = fixture.unit_cube;
	const cube = MeshBuilder.CreateBox("fixture-meter-stone", {
		width: cubeSpec.dimensions[0],
		height: cubeSpec.dimensions[1],
		depth: cubeSpec.dimensions[2],
	}, scene);
	cube.position.set(...cubeSpec.center);
	cube.material = materials.pathDark;
	cube.isPickable = false;
	cube.isVisible = false;
	cube.computeWorldMatrix(true);
	colliders.push(collisionBoxFromMesh(cube));

	const gate = fixture.doorway;
	const [x, y, z] = gate.floor_center;
	const post = gate.wall_thickness;
	for (const [name, centerX] of [
		["left", x - gate.clear_width / 2 - post / 2],
		["right", x + gate.clear_width / 2 + post / 2],
	] as const) {
		const jamb = MeshBuilder.CreateBox(`fixture-gate-${name}`, {
			width: post,
			height: gate.clear_height,
			depth: post,
		}, scene);
		jamb.position.set(centerX, y + gate.clear_height / 2, z);
		jamb.material = materials.wallLight;
		jamb.isPickable = false;
		jamb.isVisible = false;
		jamb.computeWorldMatrix(true);
		colliders.push(collisionBoxFromMesh(jamb));
	}
	const lintel = MeshBuilder.CreateBox("fixture-gate-lintel", {
		width: gate.clear_width + post * 2,
		height: post,
		depth: post,
	}, scene);
	lintel.position.set(x, y + gate.clear_height + post / 2, z);
	lintel.material = materials.wall;
	lintel.isPickable = false;
	lintel.isVisible = false;

	return colliders;
}

function collisionBoxFromMesh(mesh: ReturnType<typeof MeshBuilder.CreateBox>): CollisionBox {
	const box = mesh.getBoundingInfo().boundingBox;
	return {
		minX: box.minimumWorld.x,
		maxX: box.maximumWorld.x,
		minY: box.minimumWorld.y,
		maxY: box.maximumWorld.y,
		minZ: box.minimumWorld.z,
		maxZ: box.maximumWorld.z,
	};
}

/** actors.ts paints fake contact blobs; the real shadow map replaces them. */
function stripFakeShadows(root: TransformNode, materials: Record<string, StandardMaterial>): void {
	for (const descendant of root.getDescendants(false)) {
		if (descendant instanceof Mesh && descendant.material === materials.shadowBlob) {
			descendant.dispose();
		}
	}
}
