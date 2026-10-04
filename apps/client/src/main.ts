import {currentDevice} from "./community";
import {ProgressionFeedback} from './progression-feedback.mjs';
import {refinementNotice} from './refinement-notice.mjs';
import {MagePilotClient,parseMageTrialState,parseMageCastState} from './mage-pilot-client.mjs';
import {MageTrialActivation} from './mage-trial-activation.mjs';
import { createReconnectScheduler } from "./reconnect-scheduler.mjs";
import { monsterActiveMotion } from './monster-snapshot-motion.mjs';
import { localCooldownDeadline, ActionResultOrder } from "./cooldown-clock.mjs";
import { CorrectionSmoother, InputTickScheduler, Predictor, RemoteView, ServerTickClock } from "./netcode.mjs";
import { parseCoordinateFixture, parseStaticColliders } from "./coordinate-fixture";
import { encodeAction, encodeCold, encodeInput, encodeJoin, encodePing } from "./wire.mjs";
import {createSnapshotDelivery} from './snapshot-delivery.mjs';
import {fnv1a64Halves as fnv1a64} from './boot-content-hash.mjs';
import {afterVisibleBootPaint} from './boot-first-paint';
import { ActionResultMessage, ColdClientMessage, ErrorMessage, PongMessage, ServerMessage, SnapshotMessage, WelcomeMessage } from "./protocol";
import type { CharacterStateMessage, DialogueMessage, DropEntry, DropsMessage, PartyStateMessage, QuestStateMessage } from "./cold_v4.gen";
import { sound } from "./audio";
import { runLoginGate } from "./login";
import { fetchRooms, switchChannel } from "./rooms-ui";
import { fetchTowerState } from "./tower-ui";
import { onChatMessage } from "./chat";
import { chatModerationText } from './chat-moderation-copy.mjs';
import { sanitizeChatText } from "./social-parse.mjs";
import { sanitizeHandle } from "./social-parse.mjs";
import type { SplashTelegraph } from "./combat-fx";
import { clearContentMismatchReload, shouldReloadContentMismatch } from "./content-reload.mjs";
import type { TerrainCellDefinition, WorldPropDefinition, WorldRouteDefinition } from "./world-layout";
import { parseCityTraversal, sampleCityHeight } from './grounded-city.mjs';
import { createCityWalkReview } from './city-walk-review';
import { recordCityRepresentationPhase } from './city-review-recorder';
import { createCityPreparationBarrier } from './city-preparation-barrier.mjs';
import { createHudControlLayout } from './hud-control-layout-controller';
import {createDungeonWarpHub} from './dungeon-warp-hub.svelte.js';
import {DUNGEON_WARP_HUB} from './dungeon-warp-policy.mjs';
import { createMobileWebApp } from './mobile-web-app/controller.svelte.js';
import { createConnectionLobby } from './connection-lobby/controller.svelte.js';
import { createChannelSelectionService } from './channel-selection-service';
import { BOOTSTRAP_PHASE_IDS, type BootstrapPhaseEvent, type BootstrapPhaseId } from './bootstrap-progress.mjs';
import { readLoginLanguage } from './login-locale';
import { combatEventPresentation, gameplayInputBlocked, movementSimulationEnabled } from './combat-event-routing.mjs';
import type {CombatUiMonster} from './combat-ui-projection';
import {parseDeathNotice,parseCombatGain} from './combat-notices.mjs';
import type {DeathStateDTO,ResourceKey} from './ui';
import {createMutationReplayLedger} from './mutation-replay.mjs';

interface BundleAbility {
	cooldown_ms: number;
	range?: number;
	damage?: number;
	targets?: number;
	duration_ms?: number;
	speed_mult?: number;
	heal?: number;
}

interface ContentBundle {
	tick_hz: number;
	player: { hp: number; speed: number };
	zones: Array<{
		id: number;
		city_traversal?: unknown;
		half_extent: number;
		monster_spawns: Array<{ enemy: string; x: number; z: number }>;
		pois: Record<string, { x: number; z: number }>;
		static_colliders?: unknown;
		terrain_cells: TerrainCellDefinition[];
		world_props: WorldPropDefinition[];
		world_routes: WorldRouteDefinition[];
	}>;
	abilities: Record<string, BundleAbility>;
	items: Record<string, { name_key: string }>;
	quests: Record<string, { name_key: string; giver: string }>;
	economy?: {
		skins: Record<string, { tunic: string }>;
		pets: Record<string, { tint?: string }>;
	} | null;
	npcs: Record<string, { zone: number; x: number; z: number; facing: number; radius: number; name_key: string }>;
	enemies: Record<string, { kind: number; hp: number; exp: number;level?:number;rank?:'normal'|'elite'|'boss';element?:string; name_key: string; splash_radius: number; splash_damage: number; splash_windup_ms: number; splash_active_ms: number; splash_recovery_ms: number; splash_cooldown_ms: number }>;
	dialogue: Record<string, Record<string, string>>;
}
import { GameHud } from "./ui";
import "./style.css";

const canvasElement = document.getElementById("game-canvas");
if (!(canvasElement instanceof HTMLCanvasElement)) throw new Error("Game canvas is missing.");
const canvas: HTMLCanvasElement = canvasElement;

const fatal = document.getElementById("fatal-error");

function showFatal(error: unknown): void {
	console.error("Aetherfield failed to start:", error);
	if (!fatal) return;
	let message: string;
	if (error instanceof Error) {
		message = error.message;
	} else if (typeof error === "string") {
		message = error;
	} else {
		try {
			message = JSON.stringify(error) ?? String(error);
		} catch {
			message = String(error);
		}
	}
	fatal.hidden = false;
	fatal.textContent = message.trim() || "The browser could not start the 3D game.";
}

let startupLobby: ReturnType<typeof createConnectionLobby> | undefined;
let startupFailure: ((code: string) => void) | undefined;
void start().catch(error => {
	startupFailure?.('initialization_failed');
	showFatal(error);
	startupLobby?.showError(document.documentElement.lang==='th'?'เริ่มเกมไม่สำเร็จ กรุณาลองอีกครั้ง':'Could not start the game. Please try again.',()=>location.reload());
});
// The existing pagehide path disposes the game; never resume a disposed BFCache page.
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });

async function start(): Promise<void> {
	const reviewQuery = new URLSearchParams(location.search);
	const mageTrialRequested=import.meta.env.DEV&&reviewQuery.get('mageTrial')==='1';
	if(import.meta.env.DEV&&reviewQuery.get('heroDetailLab')==='1'){
		const {mountHeroDetailLab}=await import('./lookdev/hero-detail-lab');await mountHeroDetailLab();return;
	}
	if(import.meta.env.DEV&&reviewQuery.get('warpFxLab')==='1'){
		const {mountDungeonWarpLab}=await import('./lookdev/dungeon-warp-lab');await mountDungeonWarpLab();return;
	}
	const lookdevEnabled = import.meta.env.DEV && reviewQuery.get('lookdev') === '1';
	if (lookdevEnabled && (!reviewQuery.has('envHour') || !reviewQuery.has('envWeather'))) {
		const canonical = new URL(location.href);
		if (!reviewQuery.has('envHour')) canonical.searchParams.set('envHour','13');
		if (!reviewQuery.has('envWeather')) canonical.searchParams.set('envWeather','clear');
		location.replace(canonical); return;
	}
	let disposed = false;
	const startupFetch = new AbortController();
	let entryTimer: ReturnType<typeof setTimeout> | undefined;
	const mobileWebApp = createMobileWebApp({language:navigator.language.toLowerCase().startsWith('th')?'th':'en'});
	window.addEventListener('pagehide', () => {
		disposed = true; startupFetch.abort(); clearTimeout(entryTimer); startupLobby?.dispose(); mobileWebApp.dispose();
	}, {once:true});
	if (mobileWebApp.isBlocked()) {
		await new Promise<void>(resolve => {
			let unsubscribe = () => {};
			unsubscribe = mobileWebApp.onBlockedChange(blocked => { if (!blocked) { unsubscribe(); resolve(); } });
		});
	}
	if (disposed) return;
	const sceneryPreview = lookdevEnabled || (import.meta.env.DEV && reviewQuery.get('cityOverview')==='1');
	let gameEntryReady = sceneryPreview;
	let bootPhase: BootstrapPhaseId = 'content';
	let entryFrameQueued = false;
	let entryFailed = false;
	let abortEntryConnection = () => {};
	const reportBoot = (event: BootstrapPhaseEvent) => {
		if (disposed || (entryFailed && event.state!=='error')) return;
		bootPhase=event.id; startupLobby?.updatePhase(event);
	};
	const failEntry = (code: string) => {
		if (disposed || gameEntryReady || entryFailed || !startupLobby) return;
		entryFailed = true;
		clearTimeout(entryTimer);
		startupFetch.abort();
		abortEntryConnection();
		reportBoot({id:bootPhase,state:'error',errorCode:code});
		startupLobby.showError(readLoginLanguage()==='th'?'เชื่อมต่อห้องไม่สำเร็จ ลองใหม่เพื่อเลือกแชนแนลอีกครั้ง':'Could not enter the room. Retry to choose a channel again.',()=>location.reload());
	};
	startupFailure=failEntry;
	if (!sceneryPreview) {
		const identity = await runLoginGate({deferChannelSelection:true, signal:startupFetch.signal});
		if (disposed) return;
		if (identity) {
			startupLobby=createConnectionLobby({language:readLoginLanguage(),worldName:'Verdant Frontier'});
			await startupLobby.chooseChannel(createChannelSelectionService({worldName:'Verdant Frontier'}));
			if (disposed) return;
			startupLobby.beginLoading(BOOTSTRAP_PHASE_IDS);
			entryTimer=setTimeout(()=>failEntry('initialization_timeout'),120000);
		} else { gameEntryReady=true; }
	}
	reportBoot({id:'content',state:'active'});
	// A background/aborted boot never requests 3D modules before a visible paint opportunity.
	if(!await afterVisibleBootPaint(startupFetch.signal) || disposed || entryFailed)return;
	const [{createGameScene,createRenderer},{applyLocalSkin,cosmeticHex,spawnLocalPet},{HitStop},{projectCombatActors},{PointerEventTypes}]=await Promise.all([
		import('./scene'),import('./cosmetics'),import('./combat-fx'),import('./combat-ui-projection'),import('@babylonjs/core/Events/pointerEvents'),
	]);
	if(disposed || entryFailed)return;
	const fixtureResponse = await fetch("/coordinate-fixture-v1.json", {signal:startupFetch.signal});
	if (!fixtureResponse.ok) throw new Error("The shared coordinate fixture could not be loaded.");
	const fixture = parseCoordinateFixture(await fixtureResponse.json());
	const bundleResponse = await fetch("/content/bundle.json", {signal:startupFetch.signal});
	if (!bundleResponse.ok) throw new Error("The content bundle could not be loaded. Run the content build first.");
	const bundleText = await bundleResponse.text();
	const bundleHash = fnv1a64(new TextEncoder().encode(bundleText));
	const bundle = JSON.parse(bundleText) as ContentBundle;
	if (!bundle.abilities || !bundle.items || !bundle.quests || !bundle.npcs || !bundle.enemies || !bundle.dialogue || !bundle.zones) {
		throw new Error("The content bundle is missing required tables.");
	}
	reportBoot({id:'content',state:'complete'});
	const zone = bundle.zones[0];
	const cityTraversal = zone?.city_traversal ? parseCityTraversal(zone.city_traversal, zone.half_extent) : undefined;
	const staticColliders = parseStaticColliders(zone?.static_colliders ?? []);
	const cityGateZ = Number.isFinite(zone?.pois?.city_gate?.z) ? zone.pois.city_gate.z : 24;
	// D-06: Thai and English keys; default from the browser language.
	const lang = navigator.language.toLowerCase().startsWith("th") ? "th" : "en";
	const strings = bundle.dialogue[lang] ?? bundle.dialogue.en;
	const tr = (key: string): string => strings[key] ?? key;
	const rotateTitle = document.getElementById("rotate-device-title");
	const rotateCopy = document.getElementById("rotate-device-copy");
	if (rotateTitle) rotateTitle.textContent = lang === "th" ? "หมุนอุปกรณ์เป็นแนวนอน" : "Turn your device sideways";
	if (rotateCopy) rotateCopy.textContent = lang === "th" ? "เกม Xexoria ออกแบบมาสำหรับการเล่นแนวนอน" : "Xexoria is designed for landscape play.";
	const enemyName = (kind: number): string => {
		const def = Object.values(bundle.enemies).find((entry) => entry.kind === kind);
		return def ? tr(def.name_key) : `#${kind}`;
	};
	const abilityCooldown = (action: string): number => bundle.abilities[action]?.cooldown_ms ?? 500;
	reportBoot({id:'renderer',state:'active'});
	const renderer = await createRenderer(canvas);
	if (disposed || entryFailed) { renderer.engine.dispose(); return; }
	reportBoot({id:'renderer',state:'complete'});
	const gameCanvas = renderer.canvas;
	const sceneEnemies = (bundle.zones[0]?.monster_spawns ?? []).map((spawn, index) => ({
		id: 101 + index,
		kind:bundle.enemies[spawn.enemy]?.kind??1,
		hp:bundle.enemies[spawn.enemy]?.hp??90,
		x: spawn.x,
		z: spawn.z,
		name: enemyName(bundle.enemies[spawn.enemy]?.kind ?? 0),
	}));
	const routeNpc = bundle.npcs.sella;
	const starterPreview = import.meta.env.DEV && new URLSearchParams(location.search).get("starterPreview") === "1";
	const meadowPlaytest = import.meta.env.DEV && new URLSearchParams(location.search).get("meadowPlaytest") === "1";
	const startZ = meadowPlaytest ? -92 : starterPreview && routeNpc ? routeNpc.z - 10 : -2;
	const routeMarkers = Object.entries(bundle.zones[0]?.pois ?? {}).map(([id, point]) => ({ id, ...point }));
	const world = await createGameScene(
		renderer.engine,
		gameCanvas,
		fixture,
		sceneEnemies,
		routeNpc ? { id: "sella", x: routeNpc.x, z: routeNpc.z } : undefined,
		routeMarkers,
		staticColliders,
		cityGateZ,
		bundle.zones[0]?.terrain_cells ?? [],
		bundle.zones[0]?.world_props ?? [],
		bundle.zones[0]?.half_extent ?? 308,
		Object.entries(bundle.npcs).filter(([id, npc]) => id === 'bovine_shaman' && npc.zone === zone?.id).map(([id, npc]) => ({ id, x: npc.x, y: (sampleCityHeight(cityTraversal, npc.x, npc.z) ?? 0) + (cityTraversal?.feetOffsetM ?? 0), z: npc.z, facing: npc.facing, name: tr(npc.name_key) })),
		cityTraversal,
		reportBoot,
		Object.values(bundle.enemies).map(enemy=>({kind:enemy.kind,name:tr(enemy.name_key),rank:enemy.rank})),
	).catch(error => { renderer.engine.dispose(); throw error; });
	if (disposed || entryFailed) { world.dispose(); return; }
	let lookdevTools: {dispose():void} | undefined;
	if (lookdevEnabled) {
		const {installLookdevSandbox} = await import('./lookdev/lookdev-sandbox');
		const {parseLookdevRequest} = await import('./lookdev/lookdev-data.mjs');
		const request = parseLookdevRequest(location.search)!;
		const blueprintReview=request.pillar==='blueprint';
		const blueprint=blueprintReview?(await import('./blueprint-review.mjs')).blueprintReviewView(reviewQuery.get('blueprintView')??'spawn'):null;
		const stoneReview = request.pillar === 'stone';
		const naturalWaterReview=request.pillar==='natural-water';
		const grassReview=request.pillar==='grass'||reviewQuery.has('grassFocus');
		const grassTarget=reviewQuery.get('grassFocus')==='south'?{x:-3,y:1,z:-92}:{x:-6,y:1,z:-10};
		const waterBody=reviewQuery.get('waterBody');
		const waterTarget=waterBody==='mere'?{x:-46.4,y:0,z:3.5}:waterBody==='cove'?{x:-53,y:0,z:-80}:{x:-17,y:1.65,z:-41};
		const waterPlayer=waterBody==='mere'?{x:-37.6,z:-4.6}:waterBody==='cove'?{x:-46,z:-82}:{x:-17,z:-48};
		const terrainReview = blueprintReview || grassReview || naturalWaterReview || stoneReview || request.pillar === 'terrain' || request.pillar === 'foliage';
		if (terrainReview) { await world.ensureTerrainCells(); world.setLocalPosition(blueprint?blueprint.player.x:grassReview?grassTarget.x:naturalWaterReview?waterPlayer.x:stoneReview?-9.5:0,blueprint?blueprint.player.z:grassReview?grassTarget.z-7:naturalWaterReview?waterPlayer.z:stoneReview?-106:-92); }
		else { await world.ensureDetailedCity(); world.revealDetailedCity(); world.setLocalPosition(0,160); }
		if ((blueprintReview || (naturalWaterReview && reviewQuery.get('waterArt') === 'pass4b')) && reviewQuery.get('blueprintCity') === 'detail') {
			await world.ensureDetailedCity();
			world.revealDetailedCity();
			world.scene.metadata={...world.scene.metadata,waterReviewCityDetail:world.cityDetailState()};
		}
		const height = (sampleCityHeight(cityTraversal,world.localRoot.position.x,world.localRoot.position.z)??0)+(cityTraversal?.feetOffsetM??0);
		world.localRoot.position.y=height;
		const candidate = reviewQuery.get('cityArtCandidate');
		lookdevTools=installLookdevSandbox({
			scene:world.scene,camera:world.camera,pillar:request.pillar,cycle:request.cycle,variant:request.variant,lodDistance:blueprint?.radius??request.lodDistance,
			sampleTimeoutMs:120000,
			target:blueprint?blueprint.target:grassReview?grassTarget:naturalWaterReview?waterTarget:stoneReview?{x:-9.5,y:1.25,z:-97.5}:terrainReview?{x:24,y:3.8,z:-86}:{x:0,y:6,z:176},
			cameraTargets:naturalWaterReview?{player:waterTarget,side:waterBody==='falls'?{x:-9.2,y:2.5,z:-38}:waterTarget,close:!waterBody||waterBody==='falls'?{x:-10.4,y:-.25,z:-40.3}:waterTarget,elevated:waterTarget}:terrainReview?undefined:{player:{x:0,y:height+1.65,z:162},close:request.pillar==='materials'?{x:-105.0142059,y:3.3,z:239.4612122}:request.pillar==='water'?{x:7.45,y:2.20,z:176}:{x:0,y:13,z:176}},
			getSettings:()=>({tier:world.getGraphicsTier(),hours:Number(reviewQuery.get('envHour')),weather:reviewQuery.get('envWeather')??'clear'}),
			applySettings(change){const url=new URL(location.href);if(change.tier)url.searchParams.set('lookdevTier',change.tier);if(change.hours!==undefined&&change.hours!==null)url.searchParams.set('envHour',String(change.hours));if(change.weather)url.searchParams.set('envWeather',change.weather);location.assign(url);},
			metadata:()=>{
				const graphics=world.getGraphicsDiagnostics();
				return {contentHash:bundleHash.toString(16).padStart(16,'0'),deviceLabel:`${renderer.label}; hardware unqualified`,phaseSeed:null,
					reviewParameters:{noGlow:reviewQuery.get('noglow')==='1',noShadow:reviewQuery.get('noshadow')==='1',cityOverview:reviewQuery.get('cityOverview')==='1'},
					sourceGlbSha256:!terrainReview && candidate!=='guardian-v1' && candidate!=='guardian-v2'?'91b5c4952deeff608bbc2f6b5a9e0c67927f838aa70f34c6d9191ebdf21c4572':null,
					graphics:{profile:{...graphics.profile},frameCap:graphics.frameCap,environment:{...graphics.environment,profile:{...graphics.environment.profile},fountain:{...graphics.environment.fountain}}},
					grass:world.scene.metadata?.grassField??null,
					blueprint:blueprint?{view:blueprint.key,wave:reviewQuery.get('blueprintWave')==='off'?'off':'P0',physicalAdmission:'UNVERIFIED'}:null,
					runtimeGlbSha256:terrainReview?null:candidate==='forge-r6'?'93910787c74e3655f40df4c8fb73630503d67e540d7fe98286febd0a1907fb61':candidate==='guardian-v2'?'8e7668042f044ff175a2d2d3fc45cfedc1eb4fdd6c058be7150271d862d02f05':candidate==='guardian-v1'?'1cb2656f1bfd6e3652e042d18249de2f535a2e8ebdcbdcb6a39fedd7e717bfa2':'95d2c8a80fa097918dbe04c666df2489fb2743b20fe7a540c34fc7e6fec90c72'};
			},
		});
	}
	const predictor = new Predictor({
		cityTraversal,
		radius: world.playerRadius,
		height: world.playerHeight,
		boxes: world.collisionBoxes,
		limit: bundle.zones[0]?.half_extent ?? 28,
		speed: bundle.player.speed,
	});
	const remotes = new RemoteView();
	const correctionSmoother = new CorrectionSmoother();
	const serverClock = new ServerTickClock();
	const inputScheduler = new InputTickScheduler();
	const cityPreparationBarrier = createCityPreparationBarrier();
	predictor.reset(0, startZ, 0);
	const dodgeSpeedMult = bundle.abilities.dodge?.speed_mult ?? 2.2;
	const dodgeDurationSteps = Math.round((bundle.abilities.dodge?.duration_ms ?? 280) / 50);
	let online = false;
	let inputSyncReady = false;
	let inputClockReady = false;
	let snapshotSyncReady = false;
	let playerId = 0;
	let connectionEpoch = 0;
	const progressionFeedback=new ProgressionFeedback();
	const mageClient=new MagePilotClient(()=>serverClock.estimate(performance.now())*50);
	let mageSp:number|null=null,mageFocusEquipped=false;
	const mageActivation=new MageTrialActivation(()=>performance.now(),createOperationId);
	let sequence = 0;
	let lastTick = 0n;
	let lastSnapshotAt = 0;
	let socket: WebSocket | null = null;
	let reconnectBlocked = false;
	const reconnect = createReconnectScheduler(() => connect(), () => !disposed && !entryFailed && !reconnectBlocked);
	abortEntryConnection = () => { reconnect.reset(); socket?.close(); };
	let lastFacing = 0;
	let lastDodgeActionSeq = 0;
	let dodgeBoostEndSeq = 0;
	let pingNonce = 0;
	let rttEstimateMs = 0;
	const pingSent = new Map<number, number>();
	const rttSamples: number[] = [];
	const correctionSamples: number[] = [];
	const cityCorrectionEvents: Array<Record<string, unknown>> = [];
	const cityConnectionEvents: Array<Record<string, unknown>> = [];
	const recordCityNetwork = (stage:string,detail:Record<string,unknown>={}) => {
		if(!import.meta.env.DEV || new URLSearchParams(location.search).get('cityWalkReview')!=='1')return;
		cityConnectionEvents.push({stage,time:performance.now(),...detail});
		if(cityConnectionEvents.length>32)cityConnectionEvents.shift();
	};
	let lastPingAt = 0;
	let stepAcc = 0;
	const knownRemotes = new Set<number>();
	const remoteConnected = new Map<number, boolean>();
	const clientCooldown = new Map<string, number>();
	const pendingActions = new Map<number, import("./protocol").ActionKind>();
	const actionResultOrder = new ActionResultOrder();
	let cityTransitionStarted = 0;
	const pendingQuestClaims = new Map<string, string>();
	let questState: QuestStateMessage | null = null;
	let petHandle: { id: string; dispose: () => void } | null = null;
	let currentDrops: DropEntry[] = [];
	const offlineMonsters = new Map<number, { kind: number; x: number; z: number; hp: number; max_hp: number; active: boolean }>(
		(bundle.zones[0]?.monster_spawns ?? []).map((spawn, index) => {
			const def = bundle.enemies[spawn.enemy] ?? { kind: 0, hp: 90, exp: 0 };
			return [101 + index, { kind: def.kind, x: spawn.x, z: spawn.z, hp: def.hp, max_hp: def.hp, active: true }];
		}),
	);
	const playerMaxHp = bundle.player.hp;
	let offlinePlayerHp = playerMaxHp;
	let localDead = false;
	const hitStop = new HitStop();
	const activeTelegraphs = new Set<SplashTelegraph>();
	const serverTelegraphs = new Map<number, SplashTelegraph>();
	const serverMonsterStates = new Map<number, number>();
	const seenCombatEvents = new Map<bigint, number>();
	const enemyByKind = new Map(Object.values(bundle.enemies).map((enemy) => [enemy.kind, enemy]));
	const combatCatalog=new Map(Object.values(bundle.enemies).map(enemy=>[enemy.kind,{...enemy,name:tr(enemy.name_key)}]));
	let combatMonsters:CombatUiMonster[]=[];
	let selectedTargetId:number|null=null;
	const lastMonsterDamage=new Map<number,number>();
	let latestDeathNotice:{state:DeathStateDTO;receivedAt:number}|null=null;
	const pendingMutationPackets=createMutationReplayLedger();
	let resourceEpoch=0;
	const partyMemberIds=new Set<number>();
	const targetPicker=world.scene.onPointerObservable.add(info=>{
		if(inputBlockedNow())return;
		const id=info.pickInfo?.pickedMesh?.metadata?.monsterId;
		const target=combatMonsters.find(monster=>monster.id===id&&monster.active);
		if(!target)return;selectedTargetId=target.id;
		lastFacing=Math.atan2(target.x-world.localRoot.position.x,target.z-world.localRoot.position.z);
	},PointerEventTypes.POINTERPICK);

	window.addEventListener("keydown", (e) => {
		// M opens the world map (HUD panel); mute lives on N.
		if (e.code === "KeyN" && !e.repeat) {
			const muted = sound.toggleMuted();
			hud.showToast(muted ? "Sound Muted" : "Sound Unmuted");
		}
	});

	const resolveItemName = (item: string) => {
		const key = bundle.items[item]?.name_key;
		return key ? tr(key) : item.replaceAll("_", " ");
	};

	let controlLayout: ReturnType<typeof createHudControlLayout> | undefined;
	let warpHub:ReturnType<typeof createDungeonWarpHub>|undefined;
	const hud = new GameHud({
		onReturnToTown(opId,deathRevision){
			return sendColdIntent({t:'return_to_town',op_id:opId,death_revision:deathRevision} as unknown as ColdClientMessage);
		},
		onRefreshResource(key){
			if(!online)return false;
			if(['friends','group','rooms','tower'].includes(key)){void refreshServerPanel(key);return true;}
			return sendColdIntent({t:'resync'});
		},
		onCombatReadabilityChanged(value){world.configureCombatPresentation({textScale:value.combatTextScale,showOthers:!value.hideOtherEffects,lowEffects:value.lowEffects,screenShake:value.screenShake});},
		onAction(action) {
			if (inputBlockedNow()) return;
			if(mageTrialRequested&&(action==='attack'||action==='arc_slash')){
				requestMageCast(action==='attack'?'h02_basic':'h02_star_lance');return;
			}
			const now = performance.now();
			const cooldown = abilityCooldown(action);
			if ((clientCooldown.get(action) ?? 0) > now) return;
			clientCooldown.set(action, now + cooldown);
			hud.setActionCooldown(action, now + cooldown, cooldown);

			if (action === "dodge") {
				sound.playDodge();
				world.cameraRig.punchFov(0.35);
				world.cameraRig.addTrauma(0.12);
			} else if (action === "attack" || action === "arc_slash") {
				sound.playSwing(action === "arc_slash");
				world.playHeroAttack();
				world.slashArc.play(
					world.localRoot.position.x,
					world.localRoot.position.y,
					world.localRoot.position.z,
					lastFacing,
					action === "arc_slash",
				);
			}

			if (online && socket?.readyState === WebSocket.OPEN && playerId > 0) {
				const actionSequence = nextSequence();
				if (actionSequence !== null) {
					if (action === "dodge") {
						lastDodgeActionSeq = actionSequence;
						dodgeBoostEndSeq = actionSequence + dodgeDurationSteps;
					}
					pendingActions.set(actionSequence, action);
					actionResultOrder.register(action, actionSequence);
					socket.send(encodeAction(connectionEpoch, actionSequence, action, lastFacing, selectedTargetId??0, Number(lastTick)));
				}
				return;
			}
			if (action === "dodge") {
				lastDodgeActionSeq = (sequence ?? 0);
				dodgeBoostEndSeq = (sequence ?? 0) + dodgeDurationSteps;
			}
			applyOfflineAction(action);
		},
		onCommunity(action) {return sendColdIntent({t:"community",action:action.kind==="sync"?{...action,device:currentDevice()}:action} as unknown as ColdClientMessage);},
		onChatSend(channel, text) {
			const clean = sanitizeChatText(text,channel==="megaphone"?110:160);
			if (!clean) return;
			const intent = channel === "megaphone" ? {t:"community",action:{kind:"megaphone",text:clean}} : {t:"chat",channel,text:clean};
			if (!sendColdIntent(intent as unknown as ColdClientMessage)) {
				hud.showToast(lang === "th" ? "เข้าห้องก่อนพิมพ์แชทได้" : "Join the game room first.");
			}
		},
		onFriendAdd(handle) {
			const clean = sanitizeHandle(handle);
			if (clean) sendColdIntent({ t: "friend_add", handle: clean } as unknown as ColdClientMessage);
		},
		onFriendRemove(handle) {
			const clean = sanitizeHandle(handle);
			if (clean) sendColdIntent({ t: "friend_remove", handle: clean } as unknown as ColdClientMessage);
		},
		onGroupCreate() {
			sendColdIntent({ t: "group_create" } as unknown as ColdClientMessage);
		},
		onGroupJoin(code) {
			sendColdIntent({ t: "group_join", code } as unknown as ColdClientMessage);
		},
		onGroupLeave() {
			sendColdIntent({ t: "group_leave" } as unknown as ColdClientMessage);
		},
		onTowerEnter() {
			void requestTowerEntry();
		},
		onTowerLeave() {
			if (!gameEntryReady || mobileWebApp.isBlocked()) return;
			void fetch("/tower/leave", { method: "POST", cache: "no-store" }).catch(() => null);
			socket?.close(); // reconnect to the normal field
		},
		onChannelPicked(channel) {
			if (!gameEntryReady || mobileWebApp.isBlocked()) return;
			void switchChannel(channel);
		},
		onBuy(itemOrCosmeticId) {
			const opId = createOperationId();
			sendColdIntent({ t: "store_buy", item: itemOrCosmeticId, op_id: opId });
		},
		onOpenBox(boxId) {
			const opId = createOperationId();
			sendColdIntent({ t: "box_open", item: boxId, op_id: opId });
		},
		onEquipItem(item) {
			sendColdIntent({ t: "equip_item", item, op_id: crypto.randomUUID() } as unknown as ColdClientMessage);
		},
		onMoveItemInstance(opId,instanceId,expectedRevision,to){
			return sendColdIntent({t:'move_item_instance',op_id:opId,instance_id:instanceId,expected_revision:expectedRevision,to} as unknown as ColdClientMessage);
		},
		itemEquipmentSlot(item){const slot=(bundle.items[item] as {equip_slot?:unknown}|undefined)?.equip_slot;return slot==='weapon'||slot==='armor'?slot:null;},
		equippable(item) {
			const def = (bundle.items ?? {})[item] as { equip_slot?: string } | undefined;
			return typeof def?.equip_slot === "string";
		},
		onUseItem(item) {
			const opId = createOperationId();
			sendColdIntent({ t: "use_item", item, op_id: opId });
		},
		isConsumable(item) {
			const def = (bundle.items ?? {})[item] as { type?: string } | undefined;
			return def?.type === "consumable";
		},
		isBox(item) {
			const def = (bundle.items ?? {})[item] as { type?: string } | undefined;
			return def?.type === "box";
		},
		onEquip(slot, id) {
			const opId = createOperationId();
			sendColdIntent({ t: "cosmetics_equip", slot, id, op_id: opId });
		},
		onRefineItem(slot,instanceId,expectedRevision) {
			sendColdIntent({t:'refine_item',slot,op_id:createOperationId(),...(instanceId!==undefined&&expectedRevision!==undefined?{instance_id:instanceId,expected_revision:expectedRevision}:{})} as unknown as ColdClientMessage);
		},
		onAllocateStat(stat) {
			const opId = createOperationId();
			if(!sendColdIntent({ t: "stat_allocate", stat, points: 1, op_id: opId }))hud.showToast(lang==='th'?'ยังไม่ได้ส่งรายการ ตรวจการเชื่อมต่อ':'Request was not sent. Check the connection.');
		},
		onPotion(opId) {
			if (inputBlockedNow()) return false;
			if (online) {
				if (!opId || !socket || socket.readyState !== WebSocket.OPEN) return false;
				try {
					return sendColdIntent({t:'use_item',item:'trail_potion',op_id:opId});
				} catch {
					return false;
				}
			}
			const heal = bundle.abilities.potion?.heal ?? 40;
			offlinePlayerHp = Math.min(playerMaxHp, offlinePlayerHp + heal);
			hud.setHp(offlinePlayerHp, playerMaxHp);
			return true;
		},
		onContext(action) {
			if (action.kind === "talk") sendColdIntent({ t: "interact", npc: action.id });
			else if (action.kind === "activate") sendColdIntent({ t: "activate", marker: action.id });
			else if (action.kind === "pickup") sendColdIntent({ t: "pickup_drop", encounter: action.id, op_id: createOperationId() });
		},
		onChoose(npc, token, choice) {
			sendColdIntent({ t: "choose", npc, token, choice });
		},
		onClaim(quest) {
			const opId = createOperationId();
			pendingQuestClaims.set(opId, quest);
			if (!sendColdIntent({ t: "claim", quest, op_id: opId })) pendingQuestClaims.delete(opId);
		},
		onParty(action) {
			const message: ColdClientMessage = action.kind === "create"
				? { t: "party_create" }
				: action.kind === "join"
					? { t: "party_join", code: action.code ?? "" }
					: { t: "party_leave" };
			if (!sendColdIntent(message)) hud.showToast(lang === "th" ? "เชื่อมต่อห้องเกมก่อน" : "Join the game room first.");
		},
		itemName: resolveItemName,
		questName(quest) {
			const key = bundle.quests[quest]?.name_key;
			return key ? tr(key) : quest.replaceAll("_", " ");
		},
		translate(key) {
			return tr(key);
		},
		language: lang,
	});
	const readability=hud.getCombatReadability();
	world.configureCombatPresentation({locale:lang,textScale:readability.combatTextScale,showOthers:!readability.hideOtherEffects,lowEffects:readability.lowEffects,screenShake:readability.screenShake});
	controlLayout = createHudControlLayout({language:lang,onEditingChange(editing){if(editing){hud.releaseMovement();world.setHeroMotion('idle');}}});
	async function requestTowerEntry():Promise<boolean>{
		if(!gameEntryReady||mobileWebApp.isBlocked())return false;
		const response=await fetch('/tower/enter',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',cache:'no-store'}).catch(()=>null);
		if(response?.status===204){socket?.close();return true;} // existing authoritative assignment + reconnect flow
		hud.showToast(response?.status===503?(lang==='th'?'หอคอยเต็มชั่วคราว':'The tower is full right now'):(lang==='th'?'เข้าหอคอยไม่สำเร็จ':'Could not enter the tower'));return false;
	}
	if(import.meta.env.DEV&&(reviewQuery.get('dressing')==='v3'||reviewQuery.get('warpHub')==='1')){
		const floor=sampleCityHeight(cityTraversal,DUNGEON_WARP_HUB.x,DUNGEON_WARP_HUB.z);
		if(floor!==null)warpHub=createDungeonWarpHub(world.scene,{y:Math.max(floor,DUNGEON_WARP_HUB.platformTopY),th:lang==='th',mobile:currentDevice()==='mobile',
			focus:()=>({x:world.localRoot.position.x,y:world.localRoot.position.y,z:world.localRoot.position.z}),
			checkTower:async()=>online&&playerId>0&&(await fetchTowerState())!==null,enterTower:requestTowerEntry});
		else console.warn('Dungeon warp hub omitted: city support is not admitted at its planned anchor.');
	}
	hud.setMapData({ ...bundle.zones[0]?.pois, ...Object.fromEntries(Object.entries(bundle.npcs).filter(([, npc]) => npc.zone === zone?.id).map(([id, npc]) => [id, { x: npc.x, z: npc.z }])) }, bundle.zones[0]?.half_extent ?? 28, bundle.zones[0]?.world_routes ?? []);

	function sendColdIntent(message: ColdClientMessage): boolean {
		const passive = message as {t:string;action?:{kind?:string}};
		if ((!gameEntryReady || mobileWebApp.isBlocked()) && !(passive.t==='community' && passive.action?.kind==='sync')) return false;
		if (!online || !socket || socket.readyState !== WebSocket.OPEN) return false;
		try {
			const packet=encodeCold(message);
			const mutation=message as {t:string;op_id?:string};
			if(mutation.op_id){
				const resource:ResourceKey=mutation.t==='claim'?'journal':mutation.t==='store_buy'||mutation.t==='cosmetics_equip'?'wallet':mutation.t==='stat_allocate'||mutation.t==='return_to_town'?'character':'inventory';
				if(!pendingMutationPackets.register(mutation.op_id,packet,resource)){hud.showToast(lang==='th'?'กำลังรอข้อมูลตัวละครหรือผลยืนยันรายการก่อนหน้า':'Waiting for character data or an earlier operation');return false;}
				hud.setTransactionState({resource,requestId:mutation.op_id,phase:'submitting',reason:null});
			}
			socket.send(packet);
			return true;
		} catch {
			const opId=(message as {op_id?:string}).op_id;
			const pending=opId?pendingMutationPackets.pending().find(entry=>entry.opId===opId):undefined;
			if(pending){hud.setTransactionState({resource:pending.resource,requestId:pending.opId,phase:'outcome-unknown',reason:'send_failed'});socket?.close();return true;}
			return false;
		}
	}

	function createOperationId(): string {
		const bytes = crypto.getRandomValues(new Uint8Array(16));
		bytes[6] = (bytes[6] & 0x0f) | 0x40;
		bytes[8] = (bytes[8] & 0x3f) | 0x80;
		const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
		return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
	}

	async function refreshServerPanel(key:ResourceKey):Promise<void>{
		const epoch=resourceEpoch,requestId=createOperationId();
		hud.setPanelResource(key,{status:'loading',requestId});
		try{
			if(key==='tower'){
				const data=await fetchTowerState();if(epoch!==resourceEpoch||disposed)return;
				if(!data)throw new Error('refresh failed');hud.setTowerState(data,requestId);
			}else if(key==='rooms'){
				const data=await fetchRooms();if(epoch!==resourceEpoch||disposed)return;
				if(!data)throw new Error('refresh failed');hud.setChannelState({rooms:data,current:null},requestId);
			}else{
				const response=await fetch(key==='friends'?'/friends':'/group',{cache:'no-store'});
				if(!response.ok)throw new Error('refresh failed');const data=await response.json();
				if(epoch!==resourceEpoch||disposed)return;
				if(key==='friends')hud.setFriendsPayload(data,requestId);else hud.setGroupPayload(data,requestId);
			}
		}catch{
			if(epoch===resourceEpoch&&!disposed)hud.setPanelResource(key,{status:'error',requestId,message:lang==='th'?'โหลดข้อมูลไม่สำเร็จ ลองอีกครั้ง':'Could not refresh. Please retry.'});
		}
	}

	function updateContextAction(): void {
		if (!online) {
			hud.setContextAction(null);
			return;
		}
		const position = world.localRoot.position;
		const nearbyNpc = Object.entries(bundle.npcs).filter(([, npc]) => npc.zone === zone?.id && Math.hypot(position.x - npc.x, position.z - npc.z) <= npc.radius)
			.sort(([, a], [, b]) => Math.hypot(position.x - a.x, position.z - a.z) - Math.hypot(position.x - b.x, position.z - b.z))[0];
		if (nearbyNpc) {
			hud.setContextAction({ kind: "talk", id: nearbyNpc[0], label: lang === "th" ? `คุยกับ${tr(nearbyNpc[1].name_key)}` : `Talk to ${tr(nearbyNpc[1].name_key)}` });
			return;
		}
		if (questState?.state === "active") {
			const nextMarkerId = `windmark_${(questState.objectives.windmark ?? 0) + 1}`;
			const point = bundle.zones[0]?.pois[nextMarkerId];
			const nearby = point && Math.hypot(position.x - point.x, position.z - point.z) <= 2
				? { id: nextMarkerId, point }
				: undefined;
			if (nearby) {
				hud.setContextAction({ kind: "activate", id: nearby.id, label: lang === "th" ? "ปลุกเครื่องหมายลม" : "Awaken windmark" });
				return;
			}
		}
		let nearestDrop: DropEntry | null = null;
		let minDropDist = 2.0;
		for (const drop of currentDrops) {
			const d = Math.hypot(position.x - drop.x, position.z - drop.z);
			if (d <= minDropDist) {
				minDropDist = d;
				nearestDrop = drop;
			}
		}
		if (nearestDrop) {
			const itemLabel = resolveItemName(nearestDrop.item);
			hud.setContextAction({
				kind: "pickup",
				id: nearestDrop.encounter,
				label: lang === "th" ? `เก็บ ${itemLabel}` : `Pick up ${itemLabel}`,
			});
			return;
		}
		hud.setContextAction(null);
	}

	function nextSequence(): number | null {
		if (sequence >= 0xffff_fffe) {
			socket?.close();
			return null;
		}
		return ++sequence;
	}

	function simulateMovementStep(): void {
		const screenMovement = hud.getMovement();
		const alpha = world.camera.alpha;
		const forwardX = -Math.cos(alpha);
		const forwardZ = -Math.sin(alpha);
		const rightX = -Math.sin(alpha);
		const rightZ = Math.cos(alpha);
		const movement = {
			x: screenMovement.x * rightX + screenMovement.z * forwardX,
			z: screenMovement.x * rightZ + screenMovement.z * forwardZ,
		};
		const reviewMovement = walkReview?.axes();
		if (reviewMovement) { movement.x = reviewMovement.x; movement.z = reviewMovement.z; }
		const cityHeld = cityPreparationBarrier.shouldHold(world.waitingForCity(), world.cityDetailState());
		if (inputBlockedNow()) { movement.x = 0; movement.z = 0; }
		if (movement.x !== 0 || movement.z !== 0) lastFacing = Math.atan2(movement.x, movement.z);
		world.setHeroMotion(movement.x !== 0 || movement.z !== 0 ? "run" : "idle");
		const inputSequence = nextSequence();
		if (inputSequence === null) return;
		if (cityHeld) cityPreparationBarrier.noteStopInput(inputSequence);
		const isDodging = lastDodgeActionSeq > 0
			&& inputSequence > lastDodgeActionSeq
			&& inputSequence <= dodgeBoostEndSeq;
		const mult = isDodging ? dodgeSpeedMult : 1;
		predictor.step(inputSequence, movement.x, movement.z, lastFacing, mult);
		if (online && socket?.readyState === WebSocket.OPEN) {
			socket.send(encodeInput(connectionEpoch, inputSequence, movement.x, movement.z, lastFacing));
		}
	}

	function inputBlockedNow(): boolean {
		const focused = document.activeElement;
		return gameplayInputBlocked({
			ready:gameEntryReady&&(playerId===0||online&&inputSyncReady&&pendingMutationPackets.ready), dead:localDead, hidden:document.hidden,
			typing:focused instanceof Element && focused.closest('input,textarea,select,[contenteditable="true"]') !== null,
			uiBlocked:hud.isGameplayBlocked()||warpHub?.isOpen()===true, mobileBlocked:mobileWebApp.isBlocked(),
			editing:controlLayout?.isEditing() === true,
			cityHeld:cityPreparationBarrier.shouldHold(world.waitingForCity(),world.cityDetailState()),
		});
	}

	hud.setRenderer(renderer.label);
	hud.setConnection(false);
	hud.setMageTrialHud(mageTrialRequested,null,null);
	world.setMonsters([...offlineMonsters.entries()].map(([id, state]) => ({ id, ...state })));
	world.localRoot.position.set(0, 0, startZ);

	function requestMageCast(skillId:'h02_basic'|'h02_star_lance'):void{
		if(!online||!mageFocusEquipped)return;
		const metadata=mageClient.profile?.skills.find(s=>s.skill_id===skillId),position=world.localRoot.position;
		const selected=combatMonsters.find(m=>m.id===selectedTargetId&&m.hp>0);
		const nearest=[...combatMonsters].filter(m=>m.hp>0&&Math.hypot(m.x-position.x,m.z-position.z)<=(metadata?.range_m??0)).sort((a,b)=>Math.hypot(a.x-position.x,a.z-position.z)-Math.hypot(b.x-position.x,b.z-position.z))[0];
		const target=selected??nearest,result=mageClient.request(skillId,target?.id??0,mageSp??NaN);
		if(!result.ok){if(result.reason!=='busy'&&result.reason!=='cooldown')hud.showToast(lang==='th'?'เลือกมอนสเตอร์ที่อยู่ในระยะและตรวจ SP':'Select a monster in range and check your SP.');return;}
		if(!sendColdIntent(result.intent as unknown as ColdClientMessage)){mageClient.notSent(result.intent.sequence);hud.showToast(lang==='th'?'ยังไม่ได้ส่งเวท ตรวจการเชื่อมต่อ':'Spell was not sent. Check the connection.');}
	}
	function handleMageCastState(raw:unknown):void{
		const state=mageClient.receive(raw);if(!state)return;
		const now=performance.now(),action=state.skill_id==='h02_basic'?'attack':'arc_slash';
		world.setMageTrialContext(playerId,serverClock.estimate(now)*50,mageFocusEquipped&&mageClient.profile?.focus_equipped===true);
		if(state.phase==='started'){
			lastFacing=Math.atan2(state.target[0]-state.origin[0],state.target[2]-state.origin[2]);
			world.beginMageCast(state);
			sound.playMageCue('charge');
			const deadline=localCooldownDeadline(state.cooldown_end_ms,serverClock.estimate(now),now);
			hud.setActionCooldown(action,deadline,mageClient.profile?.skills.find(s=>s.skill_id===state.skill_id)?.cooldown_ms??0);
		}else if(state.phase==='released'){
			world.releaseMageCast(state);
			sound.playMageCue('release');
		}else if(state.phase==='impact'){
			world.resolveMageCast(state);
			if(state.damage>0){
				const critical=(state.flags&32)!==0;selectedTargetId=state.target_id;lastMonsterDamage.set(state.target_id,now);
				sound.playMageCue('impact');
				world.flashMonster(state.target_id,critical,{x:state.origin[0],z:state.origin[2],relation:'mine'});
				world.showDamage(state.target[0],state.target[2],state.damage,critical?'crit':'monster',state.target[1]+1.4,{targetId:state.target_id,sourceId:state.source_id,relation:'mine'});
			}else if((state.flags&64)!==0)world.showCombatWord(state.target[0],state.target[2],'miss',state.target[1]+1.4,{targetId:state.target_id,sourceId:state.source_id,relation:'mine'});
		}else if(state.phase==='cancelled'||state.phase==='rejected'){
			world.resolveMageCast(state);
			if(state.phase==='rejected'&&state.reason==='cooldown')hud.setActionCooldown(action,localCooldownDeadline(state.cooldown_end_ms,serverClock.estimate(now),now),mageClient.profile?.skills.find(s=>s.skill_id===state.skill_id)?.cooldown_ms??0);
			const copy:Record<string,[string,string]>={out_of_range:['Target is out of range.','เป้าหมายอยู่นอกระยะ'],no_target:['The target is unavailable.','เป้าหมายไม่พร้อม'],blocked:['The spell is blocked.','มีสิ่งกีดขวางเวท'],insufficient_sp:['Not enough SP.','SP ไม่เพียงพอ'],moved:['Casting cancelled by movement.','หยุดร่ายเมื่อเคลื่อนที่'],focus_required:['Equip your Arcane Focus first.','สวมโฟกัสอาคมก่อนร่าย'],focus_removed:['Casting cancelled: Arcane Focus removed.','หยุดร่ายเมื่อถอดโฟกัสอาคม'],cooldown:['The spell is still recovering.','เวทกำลังพักฟื้น']};
			if(state.phase==='rejected'||state.reason==='moved'||state.reason==='focus_removed')hud.showToast(copy[state.reason]?.[lang==='th'?1:0]??(lang==='th'?'เวทไม่ได้ส่งผล':'The spell did not take effect.'));
		}
	}
	async function requestJoinTicket(): Promise<Uint8Array> {
		const sessionResponse = await fetch("/session", {
			method: "POST",
			cache: "no-store",
			credentials: "same-origin",
		});
		recordCityNetwork('session-response',{status:sessionResponse.status});
		if (!sessionResponse.ok) throw new Error("Could not create or refresh the local session.");

		const ticketResponse = await fetch("/session/ticket", {
			method: "POST",
			cache: "no-store",
			credentials: "same-origin",
		});
		recordCityNetwork('ticket-response',{status:ticketResponse.status});
		if (!ticketResponse.ok) throw new Error("Could not issue a local join ticket.");
		const body: unknown = await ticketResponse.json();
		if (typeof body !== "object" || body === null || !("ticket" in body) || typeof body.ticket !== "string" || !/^[0-9a-f]{64}$/.test(body.ticket)) {
			throw new Error("The local room returned an invalid join ticket.");
		}
		const ticket = new Uint8Array(32);
		for (let index = 0; index < ticket.length; index++) {
			ticket[index] = Number.parseInt(body.ticket.slice(index * 2, index * 2 + 2), 16);
		}
		return ticket;
	}

	function sendJoin(ws: WebSocket, ticket: Uint8Array): void {
		try {
			ws.send(encodeJoin(ticket));
		} finally {
			ticket.fill(0);
		}
	}

	function scheduleReconnect(): void { reconnect.schedule(); }

	async function connect(): Promise<void> {
		if (disposed || entryFailed) return;
		let ticket: Uint8Array;
		try {
			ticket = await requestJoinTicket();
		} catch {
			if (disposed) return;
			failEntry('ticket_failed');
			hud.setConnection(false, "Waiting for a local session ticket…");
			scheduleReconnect();
			return;
		}
		if (disposed || entryFailed) {
			ticket.fill(0);
			return;
		}
		const scheme = location.protocol === "https:" ? "wss:" : "ws:";
		let ws: WebSocket;
		recordCityNetwork('ws-construct',{pageProtocol:location.protocol,pageHost:location.host});
		try {
			ws = new WebSocket(`${scheme}//${location.host}/ws`);
		} catch (error) {
			recordCityNetwork('ws-constructor-rejected',{name:error instanceof Error?error.name:'unknown'});
			ticket.fill(0);
			scheduleReconnect();
			return;
		}
		ws.binaryType = "arraybuffer";
		socket = ws;
		inputSyncReady = inputClockReady = snapshotSyncReady = false;
		const snapshotDelivery = createSnapshotDelivery({
			zoneLimit: bundle.zones[0]?.half_extent ?? 28,
			now: () => performance.now(),
			isCurrent: () => !disposed && !entryFailed && socket === ws && ws.readyState === WebSocket.OPEN,
			applyMessage: handleServerMessage,
			sendPacket: packet => ws.send(packet),
			close: () => ws.close(),
			onReadyChange(ready) {
				snapshotSyncReady = ready;
				inputSyncReady = ready && inputClockReady;
				if (inputSyncReady) inputScheduler.reset(serverClock.estimate(performance.now()), rttEstimateMs);
				else hud.releaseMovement();
			},
			onResync: reason => recordCityNetwork('ws-snapshot-resync', {reason}),
			onError: (stage, error, type) => recordCityNetwork(`ws-${stage}-rejected`, {type, name:error instanceof Error ? error.name : 'unknown'}),
		});
		ws.addEventListener("open", () => {
			if (disposed || entryFailed || socket!==ws) { ticket.fill(0); ws.close(); return; }
			recordCityNetwork('ws-open');sendJoin(ws, ticket);
		}, { once: true });
		ws.addEventListener("message", (event) => {
			snapshotDelivery.receive(event.data);
		});
		ws.addEventListener("close", (event) => {
			snapshotDelivery.dispose();
			if (disposed || socket!==ws) return;
			recordCityNetwork('ws-closed',{code:event.code});
			online = false;
			mageClient.connect(0,0);mageSp=null;mageFocusEquipped=false;world.clearMagePresentation();hud.setMageTrialHud(mageTrialRequested,null,null);
			inputSyncReady = inputClockReady = snapshotSyncReady = false;
			resourceEpoch++;
			hud.releaseMovement();
			pendingMutationPackets.beginReconnect();
			for(const entry of pendingMutationPackets.pending())hud.setTransactionState({resource:entry.resource,requestId:entry.opId,phase:'outcome-unknown',reason:'connection_lost'});
			const town=hud.getPendingReturnToTown();
			if(town)hud.setReturnToTownResult({...town,state:'outcome-unknown',reason:'connection_lost'});
			questState = null;
			hud.setContextAction(null);
			hud.closeDialogue();
			for (const telegraph of serverTelegraphs.values()) {
				telegraph.dispose();
				activeTelegraphs.delete(telegraph);
			}
			serverTelegraphs.clear();
			serverMonsterStates.clear();
			hud.setConnection(false);
			if (!reconnectBlocked) scheduleReconnect();
		});
		ws.addEventListener("error", () => {
			ticket.fill(0);
			ws.close();
		});
		ws.addEventListener("close", () => ticket.fill(0), { once: true });
	}

	function handleServerMessage(message: ServerMessage): void {
		if (message.type === "error") {
			handleServerError(message);
			return;
		}
		if (message.type === "welcome") {
			handleWelcome(message);
			return;
		}
		if (message.type === "action_result") {
			handleActionResult(message);
			return;
		}
		if (message.type === "pong") {
			handlePong(message);
			return;
		}
		if (message.type === "cold") {
			const data = message.data;
			const trial=mageTrialRequested?parseMageTrialState(data):null;
			if(trial){
				if(mageClient.setProfile(data)){mageActivation.confirm(trial);hud.setMageTrialHud(true,mageClient.profile,mageSp);world.setMageTrialContext(playerId,serverClock.estimate(performance.now())*50,mageFocusEquipped&&trial.focus_equipped);}
				return;
			}
			const magic=mageTrialRequested?parseMageCastState(data):null;
			if(magic){handleMageCastState(data);return;}
			if (data.t === "character_state" && isCharacterState(data)) {
				const binding=pendingMutationPackets.bind(data.character_id);
				if(hud.beginCharacterAuthority(data.character_id)){latestDeathNotice=null;localDead=false;selectedTargetId=null;partyMemberIds.clear();}
				if(binding.discarded.length)hud.showToast(lang==='th'?'เปลี่ยนตัวละครแล้ว รายการเก่าที่ยังไม่ทราบผลจะไม่ถูกส่งซ้ำ':'Character changed. Uncertain previous requests were not replayed.');
				if(!hud.setCharacterState(data))return;
				if(mageTrialRequested){
					mageSp=typeof data.sp==='number'?data.sp:null;
					mageFocusEquipped=data.equipment.some(row=>row.slot==='weapon'&&row.item==='arcane_focus');
					hud.setMageTrialHud(true,mageClient.profile,mageSp);
					world.setMageTrialContext(playerId,serverClock.estimate(performance.now())*50,mageFocusEquipped&&mageClient.profile?.focus_equipped===true);
				}
				const levelCue=progressionFeedback.accept({characterId:data.character_id??`${playerId}/${connectionEpoch}`,revision:data.rev,level:data.level,jobLevel:data.job_level,statPoints:data.stat_points});
				if(levelCue){
					sound.playMageCue('level');
					const tracks=[levelCue.baseLevelsGained?(lang==='th'?`เลเวลพื้นฐาน ${levelCue.level}`:`Base level ${levelCue.level}`):'',levelCue.jobLevelsGained?(lang==='th'?`เลเวลอาชีพ ${levelCue.jobLevel}`:`Job level ${levelCue.jobLevel}`):''].filter(Boolean);
					hud.showToast(`${tracks.join(' · ')} · ${lang==='th'?`แต้มสเตตัสคงเหลือ ${levelCue.pointsAvailable}`:`${levelCue.pointsAvailable} stat points available`}`);
				}
				for(const entry of binding.replay)socket?.send(entry.packet);
				const playerName = (data as { name?: unknown }).name;
				if (typeof playerName === "string" && playerName) hud.playerName(playerName);
				// D-14: wallet + cosmetics ride the same revisioned state.
				hud.setWalletState({
					gold: data.gold,
					coin: data.coin,
					ownedCosmetics: data.owned_cosmetics,
					skin: data.skin,
					pet: data.pet,
					bagCounts: Object.fromEntries(data.bag.map((entry) => [entry.item, entry.count])),
				});
				applyLocalSkin(world, cosmeticHex(bundle.economy ?? null, data.skin ?? "default"));
				if (data.pet) {
					if (petHandle?.id !== data.pet) {
						petHandle?.dispose();
						petHandle = { id: data.pet, dispose: spawnLocalPet(world.scene, world, cosmeticHex(bundle.economy ?? null, data.pet)) ?? (() => {}) };
					}
				} else {
					petHandle?.dispose();
					petHandle = null;
				}
			} else if (data.t === "quest_state" && isQuestState(data)) {
				questState = data;
				hud.setQuestState(data);
				world.setQuestProgress(Object.keys(data.objectives).filter((id) => id.startsWith("windmark_") && data.objectives[id] > 0));
			} else if (data.t === "dialogue" && isDialogueMessage(data)) {
				world.playNpcGreeting(data.npc);
				const quest = Object.entries(bundle.quests).find(([, definition]) => definition.giver === data.npc)?.[0] ?? "";
				hud.showDialogue(data, tr(data.text_key), quest);
			} else if (data.t === "dialogue_closed" && isDialogueClosed(data)) {
				hud.closeDialogue();
			} else if (data.t === "party_state" && isPartyState(data)) {
				hud.setPartyState(data);
				partyMemberIds.clear();for(const member of data.members)partyMemberIds.add(member.id);
			} else if (data.t === "notice" && isNoticeMessage(data)) {
				const params = (data as { params?: Record<string, unknown> }).params;
				if(data.key==='death_state'){
					const state=parseDeathNotice(params);if(!state)return;
					latestDeathNotice={state,receivedAt:performance.now()};
					if(state.down){localDead=true;hud.setDeathState(state);hud.releaseMovement();}
					return;
				}
				const gain=parseCombatGain(data.key,params);
				if(gain?.kind==='heal'){world.showDamage(world.localRoot.position.x,world.localRoot.position.z,gain.amount,'heal',world.localRoot.position.y+1.8,{targetId:playerId,relation:'mine'});return;}
				if(gain?.kind==='exp_gain'){
					world.showDamage(world.localRoot.position.x,world.localRoot.position.z,gain.base,'exp',world.localRoot.position.y+1.8,{targetId:playerId,relation:'mine'});
					hud.showToast(`+${gain.base} Base EXP · +${gain.job} Job EXP`);return;
				}
				const chatReason = data.key==='community_result' ? params?.reason : data.key;
				const chatNotice = chatModerationText(chatReason,lang);
				if (chatNotice) {
					if (data.key==='community_result' && typeof chatReason==='string') hud.communityResult(chatReason);
					hud.showToast(chatNotice); return;
				}
				if(data.key==="community_state"){hud.setCommunityPayload(params);return;}
				if(data.key==="community_result"){hud.communityResult(typeof params?.reason==="string"?params.reason:"unknown");return;}
				if(data.key==="friends_refresh"){void fetch("/friends",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(body=>{if(body)hud.setFriendsPayload(body);}).catch(()=>{});return;}
				const floor = typeof params?.floor === "number" ? params.floor : undefined;
				hud.showGameNotice(data.key, floor === undefined ? undefined : { floor });
			} else if (data.t === "chat" && typeof (data as { from?: unknown }).from === "string" && typeof data.text === "string") {
				onChatMessage(data);
			} else if (data.t === "friends") {
				hud.setFriendsPayload(data);
			} else if (data.t === "group") {
				hud.setGroupPayload(data);
			} else if (data.t === "drops" && isDropsMessage(data)) {
				currentDrops = data.entries;
				world.updateDrops(data.entries);
			} else if (data.t === "op_result" && isOperationResult(data)) {
				mageActivation.settle(data.op_id);
				const pending=pendingMutationPackets.settle(data.op_id);
				if(pending)hud.setTransactionState({resource:pending.resource,requestId:data.op_id,phase:data.status==='accepted'?'committed':'rejected',reason:data.reason});
				const town=hud.getPendingReturnToTown();
				if(town?.opId===data.op_id)hud.setReturnToTownResult({...town,state:data.status==='accepted'?'committed':'rejected',reason:data.reason});
				const quest = pendingQuestClaims.get(data.op_id);
				if (quest) {
					pendingQuestClaims.delete(data.op_id);
					const copy = lang === "th"
						? { accepted: "รับรางวัลภารกิจแล้ว", inventory_full: "กระเป๋าเต็ม ต้องมีช่องว่างหนึ่งช่อง", out_of_range: "กลับไปหาเซลล่าก่อน", fallback: "รับรางวัลไม่สำเร็จ" }
						: { accepted: "Quest reward claimed", inventory_full: "Your bag is full; free one slot first.", out_of_range: "Return to Sella to claim the reward.", fallback: "Quest claim was rejected" };
					hud.showToast(data.status === "accepted" ? copy.accepted : copy[data.reason as keyof typeof copy] ?? copy.fallback);
				} else if (data.reason === "allocated") {
					hud.showToast(lang === "th" ? "อัปเกรดค่าสเตตัสสำเร็จ!" : "Allocated status point!");
				} else if (data.reason === "insufficient_stat_points") {
					hud.showToast(lang === "th" ? "แต้มสเตตัสไม่เพียงพอ" : "Insufficient stat points");
				} else if (refinementNotice(data.status,data.reason,lang)) {
					hud.showToast(refinementNotice(data.status,data.reason,lang)!);
				} else if (data.reason === "picked_up" || (Array.isArray(data.grants) && data.grants.length > 0)) {
					const grantTexts = (data.grants ?? []).map((g) => `+${g.count} ${resolveItemName(g.def)}`).join(", ");
					hud.showToast(grantTexts ? (lang === "th" ? `ได้รับ ${grantTexts}` : `Obtained ${grantTexts}`) : (lang === "th" ? "เก็บไอเทมแล้ว" : "Item picked up"));
				} else {
					hud.setPotionResult(data.op_id, data.status, data.reason, localCooldownDeadline(data.ends_at_ms, serverClock.estimate(performance.now()), performance.now(), 60_000));
				}
			}
			return;
		}
		handleSnapshot(message);
	}

	function handleWelcome(message: WelcomeMessage): void {
		recordCityNetwork('welcome',{contentMatches:message.content_hash===bundleHash});
		if (message.content_hash !== bundleHash) {
			reconnectBlocked = true;
			inputSyncReady = inputClockReady = snapshotSyncReady = false;
			socket?.close(1002, 'content mismatch');
			const canRetry = shouldReloadContentMismatch(
				(() => { try { return window.sessionStorage; } catch { return null; } })(),
				bundleHash,
			);
			if (canRetry) {
				hud.setConnection(false, "Content mismatch — refreshing once…");
				window.location.reload();
			} else {
				hud.setConnection(false, "Content still mismatched after one refresh. Close and reopen the game after the build updates.");
			}
			return;
		}
		clearContentMismatchReload((() => { try { return window.sessionStorage; } catch { return null; } })());
		playerId = message.player_id;
		connectionEpoch = message.epoch;
		mageClient.connect(playerId,connectionEpoch);mageActivation.connect(connectionEpoch);mageSp=null;mageFocusEquipped=false;world.clearMagePresentation();
		sequence = 0;
		pendingActions.clear();
		actionResultOrder.reset();
		lastDodgeActionSeq = 0;
		dodgeBoostEndSeq = 0;
		clientCooldown.clear();
		for (const action of ["attack", "arc_slash", "dodge", "guard"] as const) hud.setActionCooldown(action, 0, 0);
		for (const telegraph of serverTelegraphs.values()) {
			telegraph.dispose();
			activeTelegraphs.delete(telegraph);
		}
		serverTelegraphs.clear();
		serverMonsterStates.clear();
		seenCombatEvents.clear();
		questState = null;
		pingSent.clear();
		correctionSmoother.reset();
		inputSyncReady = inputClockReady = snapshotSyncReady = false;
		for (const id of knownRemotes) world.removeRemote(id);
		knownRemotes.clear();
		remoteConnected.clear();
		remotes.clear();
		lastTick = message.tick;
		world.setWorldTick(Number(message.tick));
		const now = performance.now();
		lastSnapshotAt = now;
		serverClock.reset(Number(message.tick), now);
		inputScheduler.reset(serverClock.estimate(now));
		online = true;
		if(mageTrialRequested)hud.setMageTrialHud(true,null,null);
		pendingMutationPackets.beginReconnect();
		if (!gameEntryReady) { reportBoot({id:'room',state:'complete'}); reportBoot({id:'snapshot',state:'active'}); }
		reconnectBlocked = false;
		reconnect.reset();
		lastPingAt = now;
		predictor.reset(message.x, message.z, 0);
		cityPreparationBarrier.reset();
		world.setLocalPosition(message.x, message.z);
		hud.setConnection(true);
		hud.setPosition(message.x, message.z);
		hud.releaseMovement();
		localDead = false;
		hud.showToast(`Joined local room · zone ${message.zone_id} · traveler ${playerId}`);
		resourceEpoch++;
		for(const key of ['tower','rooms','friends','group'] as const)void refreshServerPanel(key);
		sendPing(now);
		// Cold-path heartbeat: validates the 0x10 envelope live (V5-06+ sends real gameplay cold).
		if (socket?.readyState === WebSocket.OPEN) {socket.send(encodeCold({ t: "resync" }));sendColdIntent({t:"community",action:{kind:"sync",device:currentDevice()}} as unknown as ColdClientMessage);}
	}

	function handleActionResult(message: ActionResultMessage): void {
		const action = pendingActions.get(message.seq);
		pendingActions.delete(message.seq);
		if (!action || !actionResultOrder.isLatest(action, message.seq)) return;
		const now = performance.now();
		const readyAt = localCooldownDeadline(message.ends_at_ms, serverClock.estimate(now), now);
		if (readyAt > 0) clientCooldown.set(action, readyAt);
		else clientCooldown.delete(action);
		hud.setActionCooldown(action, readyAt, Math.max(abilityCooldown(action), readyAt - now));
		if (message.accepted) return;
		if (action === "dodge") {
			lastDodgeActionSeq = 0;
			dodgeBoostEndSeq = 0;
			predictor.cancelDodgeBoost(message.seq);
		}
		hud.showToast(`Action rejected · ${message.reason}`);
	}

	function handlePong(message: PongMessage): void {
		const sentAt = pingSent.get(message.nonce);
		if (sentAt === undefined) return;
		pingSent.delete(message.nonce);
		const now = performance.now();
		const rtt = Math.max(0, now - sentAt);
		if (rtt < 10000) {
			rttSamples.push(rtt);
			if (rttSamples.length > 16) rttSamples.shift();
			const sorted = [...rttSamples].sort((a, b) => a - b);
			const filteredRtt = sorted[Math.floor(sorted.length * 0.5)];
			rttEstimateMs = filteredRtt;
			const observedAt = performance.now();
			if (!inputSyncReady) {
				inputScheduler.reset(serverClock.estimate(observedAt), rttEstimateMs);
			}
			inputClockReady = true;
			inputSyncReady = snapshotSyncReady;
			hud.setNet(filteredRtt);
		}
	}

	function sendPing(now: number): void {
		if (!online || socket?.readyState !== WebSocket.OPEN) return;
		lastPingAt = now;
		for (const [nonce, pendingAt] of pingSent) {
			if (now - pendingAt >= 10000) pingSent.delete(nonce);
		}
		while (pingSent.size >= 8) pingSent.delete(pingSent.keys().next().value!);
		pingNonce = (pingNonce + 1) >>> 0;
		if (pingNonce === 0) pingNonce = 1;
		pingSent.set(pingNonce, now);
		socket.send(encodePing(pingNonce, Math.floor(now) % 4294967296));
	}

	function handleSnapshot(message: SnapshotMessage): void {
		// The first full snapshot may share the Welcome tick (native v8 contract).
		if (message.tick < lastTick || (message.tick === lastTick && snapshotSyncReady)) return;
		const entrySnapshot = !gameEntryReady && online && playerId>0 && message.players.some(player=>player.id===playerId);
		lastTick = message.tick;
		world.setWorldTick(Number(message.tick));
		const receivedAt = performance.now();
		lastSnapshotAt = receivedAt;
		serverClock.observe(Number(message.tick), receivedAt);
		remotes.observeSnapshot(Number(message.tick), receivedAt);
		if (playerId > 0) {
			const present = new Set<number>();
			for (const player of message.players) {
				if (player.id === playerId) continue;
				present.add(player.id);
				remoteConnected.set(player.id, player.connected);
				remotes.push(player.id, Number(message.tick), player.x, player.z);
			}
			for (const id of [...knownRemotes]) {
				if (!present.has(id)) {
					knownRemotes.delete(id);
					remoteConnected.delete(id);
					world.removeRemote(id);
				}
			}
			for (const id of present) knownRemotes.add(id);
			remotes.prune(present);
			const self = message.players.find((player) => player.id === playerId);
			if (self) {
				const before = { x: predictor.x, z: predictor.z };
				const result = predictor.reconcile(
					{ x: message.ack_x, z: message.ack_z },
					message.ack_seq,
					{ x: self.x, z: self.z },
				);
				correctionSmoother.correct(
					before,
					{ x: predictor.x, z: predictor.z },
					result.error,
					result.band,
					receivedAt,
				);
				correctionSamples.push(result.error);
				cityPreparationBarrier.acknowledge(message.ack_seq);
				if (import.meta.env.DEV && new URLSearchParams(location.search).get('cityWalkReview') === '1' && result.error > .01) {
					cityCorrectionEvents.push({time:receivedAt,seq:message.ack_seq,before,ack:[message.ack_x,message.ack_z],server:[self.x,self.z],after:[predictor.x,predictor.z],hp:self.hp,...result,city:world.cityDetailState()});
					if(cityCorrectionEvents.length>32)cityCorrectionEvents.shift();
				}
				if (correctionSamples.length > 4096) correctionSamples.shift();
				hud.setHp(self.hp, self.max_hp);
				if (self.hp === 0 && !localDead) hud.releaseMovement();
				localDead = self.hp === 0;
				if(latestDeathNotice&&latestDeathNotice.receivedAt<=receivedAt&&latestDeathNotice.state.down===localDead)hud.setDeathState(latestDeathNotice.state);
				else if(localDead)hud.setDeathState({revision:null,down:true,cause:null,penalty:null,costs:null,free_return:null,auto_revive_at_ms:null});
				else hud.confirmAliveSnapshot();
			}
		}
		world.setMonsters(message.monsters);
		combatMonsters=message.monsters;
		const monsterIds=new Set(message.monsters.map(monster=>monster.id));
		for(const id of serverMonsterStates.keys())if(!monsterIds.has(id))serverMonsterStates.delete(id);
		for(const id of lastMonsterDamage.keys())if(!monsterIds.has(id))lastMonsterDamage.delete(id);
		if(selectedTargetId!==null&&!message.monsters.some(monster=>monster.id===selectedTargetId&&monster.active))selectedTargetId=null;
		for(const [id,telegraph]of serverTelegraphs)if(!monsterIds.has(id)){telegraph.dispose();activeTelegraphs.delete(telegraph);serverTelegraphs.delete(id);serverMonsterStates.delete(id);}
		for (const monster of message.monsters) {
			const previousState = serverMonsterStates.get(monster.id);
			const existingTelegraph = serverTelegraphs.get(monster.id);
			const enemy = enemyByKind.get(monster.kind);
			const radius = enemy?.splash_radius ?? 2.5;
			if (monster.active && monster.state === 2 && monster.ability === 5) {
				let telegraph = existingTelegraph;
				if (!telegraph) {
					telegraph = world.createSplashTelegraph(monster.target_x, monster.target_z, radius, Math.max(50, monster.state_ticks * 50));
					serverTelegraphs.set(monster.id, telegraph);
					activeTelegraphs.add(telegraph);
					if((monster.flags&4)!==0)sound.playTelegraphChime();
				} else {
					telegraph.setRemainingMs(monster.state_ticks * 50);
				}
				world.animateMonsterHop(monster.id, "windup");
			} else {
				if (existingTelegraph) {
					serverTelegraphs.delete(monster.id);
					activeTelegraphs.delete(existingTelegraph);
					if (monster.active && monster.state === 3) existingTelegraph.impact();
					else existingTelegraph.dispose();
				} else if (monster.active && monster.state === 3 && previousState !== 3) {
					const impact = world.createSplashTelegraph(monster.target_x, monster.target_z, radius, 50);
					impact.impact();
				}
				if (monster.active && monster.state === 3) {
					const motion=monsterActiveMotion(previousState,monster.state_ticks);
					if(motion.phase){
						if((monster.flags&4)!==0){sound.playSplashImpact();world.cameraRig.addTrauma(0.35);}
						world.animateMonsterHop(monster.id,motion.phase);
						if(motion.impactDelayMs>0){
							const actor=world.slimes.get(monster.id);
							window.setTimeout(() => {if(world.slimes.get(monster.id)===actor&&serverMonsterStates.get(monster.id)===3)world.animateMonsterHop(monster.id,"impact");},motion.impactDelayMs);
						}
					}
				} else if (monster.active && (monster.state === 4 || monster.state === 5)) {
					world.animateMonsterHop(monster.id, "recovery");
				} else {
					world.animateMonsterHop(monster.id, "idle");
				}
			}
			serverMonsterStates.set(monster.id, monster.state);
		}
		for (const event of message.events) {
			if (seenCombatEvents.has(event.id)) continue;
			seenCombatEvents.set(event.id, receivedAt);
			if (seenCombatEvents.size > 128) seenCombatEvents.delete(seenCombatEvents.keys().next().value!);
			if (event.target_kind === 1) {
				if (playerId !== 0 && event.target_id === playerId) {
					const defense=combatEventPresentation(event,playerId);
					if(defense.word)world.showCombatWord(world.localRoot.position.x,world.localRoot.position.z,defense.word,world.localRoot.position.y+1.8,{targetId:playerId,sourceId:event.source_id,relation:'mine'});
					if ((event.flags & 8) !== 0) {
						hud.showToast("Quickstep Evade!");
						world.cameraRig.punchFov(0.3);
					} else if ((event.flags & 4) !== 0) {
						hud.showToast("Perfect Guard!");
						sound.playHit(true);
						world.flashMonster(event.source_id);
						world.animateMonsterHop(event.source_id, "recovery");
					} else {
						if ((event.flags & 2) !== 0) hud.showToast("Guarded");
						if (event.amount > 0) {
							sound.playPlayerHurt();
							hud.flashHurtScreen();
							world.cameraRig.addTrauma(0.5);
							world.showDamage(event.world_x, event.world_z, event.amount, "player");
						}
					}
				}
				continue;
			}
			if (event.target_kind === 0) {
				const feedback = combatEventPresentation(event, playerId);
				const relation=feedback.mine?'mine':event.source_kind===0&&partyMemberIds.has(event.source_id)?'party':'other';
				if(feedback.word)world.showCombatWord(event.world_x,event.world_z,feedback.word,undefined,{targetId:event.target_id,sourceId:event.source_id,relation});
				if (!feedback.damaging) continue;
				lastMonsterDamage.set(event.target_id,receivedAt);
				if(feedback.mine)selectedTargetId=event.target_id;
				if (feedback.localImpact) {
					hitStop.trigger(feedback.hitStopMs);
					sound.playHit(feedback.crit);
					world.cameraRig.addTrauma(0.22);
				}
				const source=message.players.find(player=>player.id===event.source_id);
				world.flashMonster(event.target_id,feedback.crit,{x:source?.x??event.world_x,z:source?.z??event.world_z,relation});
				world.showDamage(
					event.world_x,
					event.world_z,
					event.amount,

					feedback.damageKind,
					undefined,{targetId:event.target_id,sourceId:event.source_id,relation},
				);
			}
		}
		if (entrySnapshot) {
			// Apply this accepted snapshot before the scene's next render (its loop runs first).
			const self=message.players.find(player=>player.id===playerId)!;
			world.setLocalPosition(self.x,self.z);
			for (const player of message.players) if (player.id!==playerId) world.placeRemote(player.id,player.x,player.z,player.connected);
			acceptEntrySnapshot();
		}
	}

	function acceptEntrySnapshot(): void {
		if (disposed || entryFailed || gameEntryReady || entryFrameQueued || !online) return;
		const acceptedSocket=socket;
		const acceptedEpoch=connectionEpoch;
		reportBoot({id:'snapshot',state:'complete'});
		reportBoot({id:'first_frame',state:'active'});
		entryFrameQueued=true;
		world.scene.onAfterRenderObservable.addOnce(() => {
			entryFrameQueued=false;
			if (disposed || entryFailed || !online || world.scene.isDisposed || socket!==acceptedSocket || connectionEpoch!==acceptedEpoch) return;
			clearTimeout(entryTimer); reportBoot({id:'first_frame',state:'complete'});
			gameEntryReady=true; startupLobby?.ready();
		});
	}

	function puddlekinExp(): number {
		return bundle.enemies.puddlekin?.exp ?? 9;
	}

	function handleServerError(message: ErrorMessage): void {
		failEntry('room_rejected');
		if (message.code === "session_active") {
			reconnectBlocked = true;
			hud.setConnection(false, "This local session is active in another tab.");
			socket?.close();
			return;
		}
		if (message.code === "session_expired") {
			socket?.close();
			return;
		}
		if (message.code === "rate_limited") {
			hud.setConnection(false, "Sending too fast — reconnecting.");
			return;
		}
		hud.setConnection(false, "The local room rejected this session.");
	}

	let nextOfflineSplashHopAt = performance.now() + 3500;
	let offlineSplashHopState: {
		monsterId: number;
		phase: "windup" | "leap" | "recovery";
		targetX: number;
		targetZ: number;
		telegraph: SplashTelegraph;
		hopUntil: number;
	} | null = null;

	function tickOfflineMonsterAi(now: number): void {
		if (online) return;
		if (offlineSplashHopState) {
			const s = offlineSplashHopState;
			if (s.phase === "windup") {
				if (s.telegraph.isFinished) {
					s.phase = "leap";
					world.animateMonsterHop(s.monsterId, "leap");
					window.setTimeout(() => {
						if (offlineSplashHopState === s && !online) s.telegraph.impact();
						world.animateMonsterHop(s.monsterId, "impact");
						sound.playSplashImpact();
						world.cameraRig.addTrauma(0.42);

						const playerDist = Math.hypot(
							world.localRoot.position.x - s.targetX,
							world.localRoot.position.z - s.targetZ,
						);
						const isDodging = lastDodgeActionSeq > 0
							&& (sequence ?? 0) > lastDodgeActionSeq
							&& (sequence ?? 0) <= dodgeBoostEndSeq;

						if (playerDist <= 2.5) {
							if (isDodging) {
								hud.showToast("Quickstep Evade!");
								world.cameraRig.punchFov(0.35);
							} else {
								const splashDamage = 18;
								offlinePlayerHp = Math.max(0, offlinePlayerHp - splashDamage);
								hud.setHp(offlinePlayerHp, playerMaxHp);
								sound.playPlayerHurt();
								hud.flashHurtScreen();
								world.cameraRig.addTrauma(0.52);
								world.showDamage(
									world.localRoot.position.x,
									world.localRoot.position.z,
									splashDamage,

									"player",
								);
								if (offlinePlayerHp === 0) {
									hud.showToast("Defeated · Returning to Camp");
									window.setTimeout(() => {
										offlinePlayerHp = Math.floor(playerMaxHp / 2);
										hud.setHp(offlinePlayerHp, playerMaxHp);
										predictor.reset(0, -2, 0);
									}, 2500);
								}
							}
						}
					}, 120);

					s.hopUntil = now + 700;
					s.phase = "recovery";
					world.animateMonsterHop(s.monsterId, "recovery");
				}
			} else if (s.phase === "recovery") {
				if (now >= s.hopUntil) {
					world.animateMonsterHop(s.monsterId, "idle");
					offlineSplashHopState = null;
					nextOfflineSplashHopAt = now + 5000 + Math.random() * 3000;
				}
			}
			return;
		}

		if (now >= nextOfflineSplashHopAt) {
			const local = world.localRoot.position;
			const candidate = [...offlineMonsters.entries()]
				.filter(([, m]) => m.active)
				.map(([id, m]) => ({ id, m, dist: Math.hypot(m.x - local.x, m.z - local.z) }))
				.filter((c) => c.dist <= 10)
				.sort((a, b) => a.dist - b.dist)[0];

			if (candidate) {
				const targetX = local.x;
				const targetZ = local.z;
				const telegraph = world.createSplashTelegraph(targetX, targetZ, 2.5, 900);
				activeTelegraphs.add(telegraph);
				sound.playTelegraphChime();
				world.animateMonsterHop(candidate.id, "windup");
				offlineSplashHopState = {
					monsterId: candidate.id,
					phase: "windup",
					targetX,
					targetZ,
					telegraph,
					hopUntil: now + 900,
				};
			} else {
				nextOfflineSplashHopAt = now + 2000;
			}
		}
	}

	function applyOfflineAction(action: "attack" | "arc_slash" | "dodge" | "guard"): void {
		if (action === "dodge") {
			hud.showToast("Quickstep");
			return;
		}
		if (action === "guard") {
			hud.showToast("Guard Stance · ready");
			return;
		}
		const tuning = bundle.abilities[action];
		const range = tuning?.range ?? 3.25;
		const local = world.localRoot.position;
		const target = [...offlineMonsters.entries()]
			.filter(([, monster]) => monster.active)
			.map(([id, monster]) => ({ id, monster, distance: Math.hypot(monster.x - local.x, monster.z - local.z) }))
			.filter((item) => item.distance <= range)
			.sort((a, b) => a.distance - b.distance)[0];
		if (!target) {
			hud.showToast(`Move closer to a ${enemyName(1).toLowerCase()}`);
			return;
		}
		const isArcSlash = action === "arc_slash";
		const isCounterOpening = offlineSplashHopState?.monsterId === target.id && offlineSplashHopState?.phase === "recovery";
		const baseDamage = tuning?.damage ?? 25;
		const damage = Math.round(baseDamage * (isCounterOpening ? 1.5 : 1));

		sound.playHit(isArcSlash);
		world.flashMonster(target.id, isArcSlash);
		world.cameraRig.addTrauma(isArcSlash ? 0.38 : 0.22);
		hitStop.trigger(isArcSlash ? 80 : 65);

		target.monster.hp = Math.max(0, target.monster.hp - damage);
		const defeated = target.monster.hp === 0;
		if (defeated) {
			target.monster.active = false;
			if (offlineSplashHopState?.monsterId === target.id) {
				offlineSplashHopState.telegraph.dispose();
				activeTelegraphs.delete(offlineSplashHopState.telegraph);
				offlineSplashHopState = null;
			}
			window.setTimeout(() => {
				target.monster.hp = target.monster.max_hp;
				target.monster.active = true;
				world.setMonsters([...offlineMonsters.entries()].map(([id, state]) => ({ id, ...state })));
			}, 15000);
		}
		world.setMonsters([...offlineMonsters.entries()].map(([id, state]) => ({ id, ...state })));
		world.showDamage(
			target.monster.x,
			target.monster.z,
			damage,

			isArcSlash ? "crit" : "monster",
		);
		if (defeated) hud.recordDefeat(enemyName(target.monster.kind), puddlekinExp());
	}

	const walkReview = createCityWalkReview(() => ({ online, waiting:world.waitingForCity(), x:world.localRoot.position.x, y:world.localRoot.position.y, z:world.localRoot.position.z, correction:correctionSamples.at(-1) ?? 0, correctionEvents:cityCorrectionEvents, connectionEvents:cityConnectionEvents }), () => recordCityRepresentationPhase(world.scene, 'exit-reentry'));
	// D-13 login gate: blocks connect() until the player signs in; the offline
	// preview (server unreachable) skips it entirely.
	// Scenery review must not compete with the player's authenticated room session.
	const cityArtPreview = import.meta.env.DEV && new URLSearchParams(location.search).get("cityOverview") === "1";
	if (!cityArtPreview && !lookdevEnabled) {
		clearTimeout(entryTimer);
		reportBoot({id:'room',state:'active'});
		if (!gameEntryReady) entryTimer=setTimeout(()=>failEntry('join_timeout'),20000);
		void connect();
	}
	let previousFrame = performance.now();
	let lastStepTime = performance.now();
	let lastHudUpdate = 0;
	let lastPerformanceUpdate = 0;
	const unsubscribeMobileInput = mobileWebApp.onBlockedChange(blocked => {
		const now = performance.now();
		stepAcc = 0; previousFrame = now; lastStepTime = now;
		inputScheduler.reset(serverClock.estimate(now), rttEstimateMs);
		if (blocked) {
			world.setHeroMotion('idle');
			if (online && inputSyncReady && socket?.readyState===WebSocket.OPEN) simulateMovementStep();
		}
	});
	world.setFrameUpdate(() => {
		const now = performance.now();
		if(mageTrialRequested){
			const activation=mageActivation.poll(online&&gameEntryReady&&mageSp!==null&&socket?.readyState===WebSocket.OPEN);
			const recovery=online?mageClient.pollRecovery():null;
			for(const due of [activation,recovery]){
				if(due?.kind==='retry')sendColdIntent(due.intent as unknown as ColdClientMessage);
				else if(due?.kind==='reconnect'){hud.showToast(lang==='th'?'รอผลเวทนานเกินไป กำลังเชื่อมต่อเพื่อตรวจสถานะ':'Spell response delayed. Reconnecting to verify state.');socket?.close(1000,'mage-response-timeout');break;}
			}
		}
		if(mageTrialRequested)world.setMageTrialContext(playerId,serverClock.estimate(now)*50,mageFocusEquipped&&mageClient.profile?.focus_equipped===true);
		world.setLocalPresentationPaused(hitStop.isStopped(now));
		const delta = Math.min((now - previousFrame) / 1000, 0.05);
		previousFrame = now;
		const waitingForCity = cityPreparationBarrier.shouldHold(world.waitingForCity(), world.cityDetailState());
		if (waitingForCity) {
			if (!cityTransitionStarted) cityTransitionStarted = now;
			hud.setWorldLoading(true);
			cityPreparationBarrier.markCover(now);
			if (cityPreparationBarrier.canBegin(online, now)) world.allowCityPreparation();
			// Commit behind the already-painted loading cover, not in the player's live view.
			if (now - cityTransitionStarted >= 300 && world.cityDetailState() === "prepared") {
				try { world.revealDetailedCity(); }
				catch (error) { console.warn("City reveal failed; the town proxy remains available.", error); }
			}
		} else { cityTransitionStarted = 0; hud.setWorldLoading(false); }
		if (now - lastPerformanceUpdate >= 500) {
			hud.setFps(world.getRenderFps());
			lastPerformanceUpdate = now;
		}

		// Update ground telegraphs
		for (const tel of [...activeTelegraphs]) {
			if (!tel.update()) activeTelegraphs.delete(tel);
		}

		// Update offline monster AI
		if (!lookdevEnabled) tickOfflineMonsterAi(now);

		let tookStep = false;
		if (movementSimulationEnabled({lookdev:lookdevEnabled})) {
			// Online fixed steps follow server ticks, with an RTT/2 uplink lead.
			// Offline preview uses a local fixed-step accumulator.
			if (online) {
				if (inputSyncReady) {
					const dueTicks = inputScheduler.takeDue(serverClock.estimate(now), rttEstimateMs, 2);
					for (let step = 0; step < dueTicks.length; step++) {
						simulateMovementStep();
						tookStep = true;
					}
				}
			} else {
				stepAcc += delta * 1000;
				while (stepAcc >= 50) {
					stepAcc -= 50;
					simulateMovementStep();
					tookStep = true;
				}
			}
			if (tookStep) lastStepTime = now;
		}
		const stepFraction = online
			? Math.min(1, Math.max(0, (now - lastStepTime) / 50))
			: Math.min(1, Math.max(0, stepAcc / 50));
		const renderPos = predictor.renderPosition(stepFraction);
		const localPosition = correctionSmoother.sample(renderPos.x, renderPos.z, now);
		if (!lookdevEnabled) world.setLocalPosition(localPosition.x, localPosition.z);
		if (remoteConnected.size > 0) {
			const estimatedServerTick = serverClock.estimate(now);
			for (const [id, connected] of remoteConnected) {
				const remote = remotes.sample(id, estimatedServerTick);
				if (remote) world.placeRemote(id, remote.x, remote.z, connected);
			}
		}
		world.localRoot.rotation.y = predictor.facing;
		// Snapshot watchdog (R4): no snapshot for ~3 s while online means the
		// world dropped us without closing the socket. Close and let the
		// reconnect flow (with session takeover) recover.
		if (online && socket?.readyState === WebSocket.OPEN && now - lastSnapshotAt > 3000) {
			socket.close();
		}
		if (online && socket?.readyState === WebSocket.OPEN && now - lastPingAt >= 2000) {
			sendPing(now);
		}
		if (now - lastHudUpdate > 100) {
			if(!online)combatMonsters=[...offlineMonsters.entries()].map(([id,monster])=>({id,...monster}));
			const actors=projectCombatActors(world,combatMonsters,combatCatalog,lastMonsterDamage,now);
			hud.setCombatPresentation({nowMs:now,formFactor:world.getGraphicsDiagnostics().profile.formFactor==='mobile'?'mobile':'desktop',selectedTargetId,actors});
			hud.setPosition(world.localRoot.position.x, world.localRoot.position.z);
			updateContextAction();
				lastHudUpdate = now;
		}
	});

	window.addEventListener("pagehide", () => {
		clearTimeout(entryTimer); startupLobby?.dispose();
		unsubscribeMobileInput();
		world.scene.onPointerObservable.remove(targetPicker);
		mobileWebApp.dispose();
		lookdevTools?.dispose();
		walkReview?.dispose();
		controlLayout?.dispose();
		warpHub?.dispose();
		disposed = true;
		reconnect.dispose();
		socket?.close();
		if (correctionSamples.length > 0 || rttSamples.length > 0) {
			const summarize = (samples: number[]) => {
				const sorted = [...samples].sort((a, b) => a - b);
				if (sorted.length === 0) return { n: 0, p50: 0, p95: 0, max: 0 };
				return {
					n: sorted.length,
					p50: sorted[Math.floor(sorted.length * 0.5)],
					p95: sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))],
					max: sorted[sorted.length - 1],
				};
			};
			console.info("[netcode] session summary", {
				correction_m: summarize(correctionSamples),
				rtt_ms: summarize(rttSamples),
				interpolation_delay_ms: remotes.delayMs,
				interpolation_jitter_p95_ms: remotes.jitterP95Ms,
			});
		}
		petHandle?.dispose();
		world.setFrameUpdate(null);
		world.dispose();
	}, { once: true });
}

function isCharacterState(value: Record<string, unknown>): value is Record<string, unknown> & CharacterStateMessage {
	return value.t === "character_state"
		&& typeof value.character_id==='string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.character_id)
		&& Number.isSafeInteger(value.rev) && Number(value.rev) > 0
		&& Number.isSafeInteger(value.level) && Number(value.level) > 0
		&& Number.isSafeInteger(value.exp) && Number(value.exp) >= 0
		&& Number.isSafeInteger(value.hp) && Number(value.hp) >= 0
		&& Number.isSafeInteger(value.max_hp) && Number(value.max_hp) > 0 && Number(value.hp) <= Number(value.max_hp)
		&& Array.isArray(value.bag) && value.bag.length <= 12
		&& typeof value.pouch === "object" && value.pouch !== null
		&& Number.isSafeInteger(value.gold) && Number(value.gold) >= 0
		&& Number.isSafeInteger(value.coin) && Number(value.coin) >= 0
		&& (value.skin === null || typeof value.skin === "string")
		&& (value.pet === null || typeof value.pet === "string")
		&& Array.isArray(value.owned_cosmetics)
		&& value.owned_cosmetics.every((id) => typeof id === "string");
}

function isQuestState(value: Record<string, unknown>): value is Record<string, unknown> & QuestStateMessage {
	return value.t === "quest_state"
		&& Number.isSafeInteger(value.rev) && Number(value.rev) > 0
		&& typeof value.quest === "string" && /^[a-zA-Z0-9_]{1,64}$/.test(value.quest)
		&& ["not_started", "active", "ready_to_claim", "completed"].includes(String(value.state))
		&& typeof value.objectives === "object" && value.objectives !== null
		&& Object.values(value.objectives).every((count) => Number.isSafeInteger(count) && Number(count) >= 0)
		&& typeof value.step_ticks === "object" && value.step_ticks !== null
		&& Object.values(value.step_ticks).every((tick) => Number.isSafeInteger(tick) && Number(tick) >= 0);
}

function isOperationResult(value: Record<string, unknown>): value is Record<string, unknown> & { t: "op_result"; op_id: string; status: string; reason: string; ends_at_ms: number; grants?: Array<{ def: string; count: number }> } {
	return value.t === "op_result"
		&& typeof value.op_id === "string" && /^[0-9a-fA-F-]{36}$/.test(value.op_id)
		&& typeof value.status === "string" && typeof value.reason === "string"
		&& Number.isSafeInteger(value.ends_at_ms) && Number(value.ends_at_ms) >= 0;
}

function isDialogueMessage(value: Record<string, unknown>): value is Record<string, unknown> & DialogueMessage {
	return value.t === "dialogue"
		&& typeof value.npc === "string" && /^[a-zA-Z0-9_]{1,64}$/.test(value.npc)
		&& typeof value.token === "string" && /^[a-zA-Z0-9_-]{1,64}$/.test(value.token)
		&& typeof value.text_key === "string" && /^[a-zA-Z0-9_]{1,64}$/.test(value.text_key)
		&& Array.isArray(value.choices)
		&& value.choices.every((choice) => typeof choice === "object" && choice !== null
			&& "id" in choice && typeof choice.id === "string"
			&& "label_key" in choice && typeof choice.label_key === "string");
}

function isPartyState(value: Record<string, unknown>): value is Record<string, unknown> & PartyStateMessage {
	return value.t === "party_state"
		&& Number.isSafeInteger(value.rev) && Number(value.rev) >= 0
		&& Number.isSafeInteger(value.leader) && Number(value.leader) >= 0
		&& typeof value.code === "string" && (value.code === "" || /^[A-Z0-9]{6}$/.test(value.code))
		&& Number.isSafeInteger(value.expires_s) && Number(value.expires_s) >= 0 && Number(value.expires_s) <= 600
		&& Array.isArray(value.members) && value.members.length <= 4
		&& value.members.every((member) => typeof member === "object" && member !== null
			&& "id" in member && Number.isSafeInteger(member.id) && Number(member.id) > 0
			&& "name" in member && typeof member.name === "string" && member.name.length > 0 && member.name.length <= 48);
}

function isDialogueClosed(value: Record<string, unknown>): value is Record<string, unknown> & { t: "dialogue_closed"; npc: string; reason: string } {
	return value.t === "dialogue_closed" && typeof value.npc === "string" && typeof value.reason === "string";
}

function isNoticeMessage(value: Record<string, unknown>): value is Record<string, unknown> & { t: "notice"; key: string } {
	return value.t === "notice" && typeof value.key === "string" && /^[a-zA-Z0-9_]{1,64}$/.test(value.key);
}

function isDropsMessage(value: Record<string, unknown>): value is Record<string, unknown> & DropsMessage {
	return value.t === "drops" && Array.isArray(value.entries);
}
