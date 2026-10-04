import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { NullEngine } from '@babylonjs/core/Engines/nullEngine.js';
import { Scene } from '@babylonjs/core/scene.js';
import { FreeCamera } from '@babylonjs/core/Cameras/freeCamera.js';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { createFrameRatePolicy, createPacedFrameRequester } from '../src/frame-rate-policy.mjs';

// Replay the application's actual update callback, without opening a browser or a GPU.
// The registration may become setFrameUpdate/onBeforeRender when root applies the proposal.
const mainSource = readFileSync(new URL('../src/main.ts', import.meta.url), 'utf8');
const parsedMain = ts.createSourceFile('main.ts', mainSource, ts.ScriptTarget.Latest, true);
const callbacks = [];
function visit(node) {
  if (ts.isCallExpression(node)) {
    for (const argument of node.arguments) {
      if (ts.isArrowFunction(argument) && ts.isBlock(argument.body)) {
        const body = argument.body.getText(parsedMain);
        if (body.includes('const delta = Math.min') && body.includes('simulateMovementStep()') && body.includes('predictor.renderPosition')) callbacks.push(argument);
      }
    }
  }
  ts.forEachChild(node, visit);
}
visit(parsedMain);
assert.equal(callbacks.length, 1, 'one authoritative main.ts frame-update body');
const callbackJs = ts.transpileModule(`(${callbacks[0].getText(parsedMain)})`, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;
const sceneSource = readFileSync(new URL('../src/scene.ts', import.meta.url), 'utf8');
const parsedScene = ts.createSourceFile('scene.ts', sceneSource, ts.ScriptTarget.Latest, true);
const sceneLoops = [];
function visitScene(node) {
  if (ts.isCallExpression(node) && node.expression.getText(parsedScene) === 'engine.runRenderLoop') sceneLoops.push(node.arguments[0]);
  ts.forEachChild(node, visitScene);
}
visitScene(parsedScene);
assert.equal(sceneLoops.length, 1, 'scene.ts owns exactly one engine loop');
const sceneLoopJs = ts.transpileModule(`(${sceneLoops[0].getText(parsedScene)})`, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;

function harness({ legacyOrder = false, renderPaused = false, autoCeilingFps = 60, setting = 30, mageTrialRequested=false } = {}) {
  let now = 0, id = 0, previousBegin = null, cancelled = 0;
  const queue = new Map();
  const engine = new NullEngine({ renderWidth: 8, renderHeight: 8 });
  const scene = new Scene(engine);
  new FreeCamera('cpu-only-test-camera', new Vector3(0, 1, -3), scene);
  const policy = createFrameRatePolicy({ setting, tierTargetFps: 30, formFactor: 'mobile', autoCeilingFps });
  const requester = createPacedFrameRequester({ policy,
    requestFrame: callback => { queue.set(++id, callback); return id; },
    cancelFrame: handle => { if (queue.delete(handle)) cancelled++; }, now: () => now,
  });
  engine.maxFPS = undefined;
  engine.customAnimationFrameRequester = requester;
  // NullEngine normally measures wall time. Inject a deterministic clock only at that boundary;
  // real Babylon beginFrame/render/endFrame and scene observables still execute.
  engine._measureFps = () => { engine._deltaTime = previousBegin === null ? 0 : now - previousBegin; previousBegin = now; };
  const trace = { updates: 0, before: [], after: [], begins: [], ends: 0, hud: 0, movement: 0, watchdogCloses: 0, mage:[] };
  const world = {
    scene, localRoot: { position: { x: 0, y: 0, z: 0 }, rotation: { y: 0 } },
    setLocalPresentationPaused() {}, waitingForCity: () => false, cityDetailState: () => 'ready',
    setMageTrialContext(actorId,serverMs,focus){trace.mage.push({actorId,serverMs,focus,renderFrame:scene.getFrameId()});},
    getRenderFps: () => 30, getGraphicsDiagnostics: () => ({ profile: { formFactor: 'mobile' } }),
    setLocalPosition(x, z) { this.localRoot.position.x = x; this.localRoot.position.z = z; },
    placeRemote() {}, allowCityPreparation() {}, revealDetailedCity() {},
  };
  const context = {
    mageTrialRequested,mageClient:{profile:{focus_equipped:true},pollRecovery:()=>null},mageActivation:{poll:()=>null},mageFocusEquipped:true,playerId:7,gameEntryReady:false,mageSp:null,
    performance: { now: () => now }, previousFrame: 0, stepAcc: 0, lastStepTime: 0,
    world, hitStop: { isStopped: () => false }, hud: { setWorldLoading() {}, setFps() {}, setPosition() {}, setCombatPresentation() { trace.hud++; } },
    cityPreparationBarrier: { shouldHold: () => false }, cityTransitionStarted: 0,
    lastPerformanceUpdate: 0, activeTelegraphs: new Set(), lookdevEnabled: false,
    tickOfflineMonsterAi() {}, movementSimulationEnabled: () => true,
    online: true, inputSyncReady: true, inputScheduler: { takeDue: () => [1] },
    serverClock: { estimate: () => now / 50 }, rttEstimateMs: 0,
    simulateMovementStep() { trace.movement++; },
    predictor: { facing: 0, renderPosition: () => ({ x: trace.movement, z: 0 }) },
    correctionSmoother: { sample: (x, z) => ({ x, z }) }, remoteConnected: new Map(), remotes: {},
    socket: { readyState: 1, close() { trace.watchdogCloses++; } }, WebSocket: { OPEN: 1 },
    lastSnapshotAt: 0, lastPingAt: 0, sendPing() {}, lastHudUpdate: 0,
    offlineMonsters: new Map(), combatMonsters: [], combatCatalog: {}, lastMonsterDamage: new Map(),
    projectCombatActors: () => [], selectedTargetId: null, updateContextAction() {},
  };
  const actualUpdate = vm.runInNewContext(callbackJs, context);
  const update = () => { trace.updates++; actualUpdate(now); };
  scene.onBeforeRenderObservable.add(() => trace.before.push({ t: now, x: world.localRoot.position.x, dt: engine.getDeltaTime() }));
  scene.onAfterRenderObservable.add(() => trace.after.push({ t: now, x: world.localRoot.position.x }));
  engine.onBeginFrameObservable.add(() => trace.begins.push(now));
  engine.onEndFrameObservable.add(() => trace.ends++);
  const draw = () => { if (!renderPaused) scene.render(); };
  const loopContext = { performance: { now: () => now }, worldDisposed: false,
    isRendererResetRequired: () => false, frameUpdate: update, renderPaused, scene, engine, framePolicy: policy,
    renderScaling: null, lastScaleSignalAt: 0, countedFrames: 0, counterStarted: 0, renderedFps: 0,
  };
  const actualSceneLoop = vm.runInNewContext(sceneLoopJs, loopContext);
  if (legacyOrder) { engine.runRenderLoop(draw); engine.runRenderLoop(update); }
  else { engine.runRenderLoop(actualSceneLoop); }
  return { engine, scene, policy, requester, queue, trace, context, loopContext,
    tick(timestamp) { now = timestamp; context.lastSnapshotAt = now; assert.equal(queue.size, 1); const [key, callback] = queue.entries().next().value; queue.delete(key); callback(now); },
    setPaused(value) { renderPaused = value; loopContext.renderPaused = value; },
    close() { scene.dispose(); engine.dispose(); requester.dispose(); assert.equal(queue.size, 0); return cancelled; },
  };
}

test('Mage server-clock context updates in the same rendered frame without an extra loop',()=>{
 const h=harness({mageTrialRequested:true});try{for(let i=1;i<=12;i++)h.tick(i*1000/60);assert.equal(h.trace.mage.length,h.trace.updates);assert.ok(h.trace.mage.length>0);for(const row of h.trace.mage){assert.equal(row.actorId,7);assert.equal(row.focus,true);assert.ok(row.serverMs>0);}}finally{h.close();}
});
test('one paced owner presents the actual main update to scene observers in the same frame', () => {
  const h = harness();
  try {
    for (let i = 1; i <= 24; i++) h.tick(i * 1000 / 60);
    assert.equal(h.engine.activeRenderLoops.length, 1);
    assert.equal(h.trace.before.length, h.trace.updates);
    h.trace.before.forEach((frame, i) => assert.equal(frame.x, i + 1));
    assert.deepEqual(h.trace.after.map(f => f.x), h.trace.before.map(f => f.x));
    assert.ok(h.trace.hud > 0, 'actual HUD update remains reachable');
  } finally { h.close(); }
});

test('control: scene-first and update-second callbacks present the previous frame', () => {
  const h = harness({ legacyOrder: true });
  try { h.tick(1000 / 60); assert.equal(h.trace.before[0].x, 0); assert.equal(h.trace.movement, 1); }
  finally { h.close(); }
});

test('paced skips avoid begin/end work and preserve the rendered interval for animation', () => {
  const h = harness();
  try {
    for (let i = 1; i <= 120; i++) h.tick(i * 1000 / 60);
    assert.ok(h.trace.begins.length >= 59 && h.trace.begins.length <= 61);
    assert.equal(h.trace.ends, h.trace.begins.length);
    assert.equal(h.engine.frameId, h.trace.begins.length);
    const deltas = h.trace.before.slice(1).map(f => f.dt);
    assert.ok(deltas.every(dt => Math.abs(dt - 1000 / 30) < 0.001));
  } finally { h.close(); }
});

test('render pause keeps the application/UI phase and preserves observers for readiness on resume', () => {
  const h = harness({ renderPaused: true }); let ready = 0;
  h.scene.onAfterRenderObservable.addOnce(() => ready++);
  try {
    for (let i = 1; i <= 12; i++) h.tick(i * 1000 / 60);
    assert.ok(h.trace.updates > 0); assert.ok(h.trace.hud > 0); assert.equal(h.trace.before.length, 0); assert.equal(ready, 0);
    h.setPaused(false);
    for (let i = 13; i <= 16; i++) h.tick(i * 1000 / 60);
    assert.ok(h.trace.before.length > 0); assert.equal(ready, 1);
    assert.equal(h.trace.before.at(-1).x, h.trace.movement);
  } finally { h.close(); }
});

test('visibility suspension gates engine work, then resumes the same update and scene observers', () => {
  const h = harness();
  try {
    h.tick(1000 / 60); const updates = h.trace.updates;
    h.policy.notifyVisibility(true, 20);
    for (let i = 2; i <= 8; i++) h.tick(i * 1000 / 60);
    assert.equal(h.trace.updates, updates); assert.equal(h.trace.ends, updates);
    h.policy.notifyVisibility(false, 140);
    for (let i = 9; i <= 13; i++) h.tick(i * 1000 / 60);
    assert.ok(h.trace.updates > updates); assert.equal(h.trace.before.length, h.trace.updates);
    assert.equal(h.trace.watchdogCloses, 0);
  } finally { h.close(); }
});

test('disposing with the requester attached cancels one native request and fences a late callback', () => {
  const h = harness(); h.tick(1000 / 60);
  const late = h.queue.values().next().value, updates = h.trace.updates;
  assert.equal(h.close(), 1); late(1000);
  assert.equal(h.trace.updates, updates); assert.equal(h.requester.pending, false);
});

test('tier changes forward the Auto ceiling through the existing policy without replacing the requester', () => {
  const h = harness({ setting: 'auto', autoCeilingFps: 30 });
  try {
    for (let i = 1; i <= 90; i++) h.tick(i * 1000 / 60);
    assert.equal(h.policy.state().autoCeilingFps, 30);
    assert.deepEqual([...h.policy.state().autoLadder], [30]);
    h.policy.setTier({ targetFps: 30, formFactor: 'mobile', autoCeilingFps: 60 }, 1500);
    assert.equal(h.policy.state().autoCeilingFps, 60);
    assert.ok(h.policy.state().autoLadder.includes(60));
    h.policy.notifyResize(1500);
    for (let i = 91; i <= 100; i++) h.tick(i * 1000 / 60);
    assert.equal(h.engine.customAnimationFrameRequester, h.requester);
    assert.equal(h.engine.activeRenderLoops.length, 1);
    assert.equal(h.queue.size, 1);
  } finally { h.close(); }
});

test('a required manual graphics reset fences the actual scene loop and application callback', () => {
  const h = harness();
  try {
    h.tick(1000 / 60); const updates = h.trace.updates, draws = h.trace.before.length;
    h.loopContext.isRendererResetRequired = () => true;
    for (let i = 2; i <= 10; i++) h.tick(i * 1000 / 60);
    assert.equal(h.trace.updates, updates); assert.equal(h.trace.before.length, draws);
  } finally { h.close(); }
});

test('removing the update callback and disposing fences a late actual scene callback', () => {
  const h = harness();
  try {
    h.tick(1000 / 60); const updates = h.trace.updates;
    h.loopContext.frameUpdate = null;
    for (let i = 2; i <= 8; i++) h.tick(i * 1000 / 60);
    assert.equal(h.trace.updates, updates); assert.ok(h.trace.before.length > updates);
    h.loopContext.worldDisposed = true; const draws = h.trace.before.length;
    for (let i = 9; i <= 15; i++) h.tick(i * 1000 / 60);
    assert.equal(h.trace.before.length, draws);
  } finally { h.close(); }
});
