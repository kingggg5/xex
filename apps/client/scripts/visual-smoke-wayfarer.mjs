import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const clientRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const auto = process.argv.includes('--auto');
const mobile = process.argv.includes('--mobile');
const chromePath = process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const outputDir = path.join(clientRoot, 'target/wayfarer-smoke');
const variant = mobile ? 'mobile' : auto ? 'auto' : 'webgl2';
const output = path.join(outputDir, `wayfarer_${variant}_${new Date().toISOString().replace(/[:.]/g, '-')}.png`);
if (!existsSync(chromePath)) throw new Error(`Chrome not found: ${chromePath}. Set CHROME_BIN to its executable.`);
mkdirSync(outputDir, { recursive: true });
if (existsSync(output)) throw new Error(`Refusing to overwrite an existing screenshot: ${output}`);

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const result = await check();
    if (result) return result;
    await sleep(200);
  }
  throw new Error(`Browser smoke timed out after ${timeoutMs} ms.`);
}

let server;
let chrome;
let socket;
let profile;
try {
  server = await createServer({ root: clientRoot, logLevel: 'error', server: { host: '127.0.0.1', port: 0, strictPort: false } });
  await server.listen();
  const port = server.httpServer.address().port;
  profile = mkdtempSync(path.join(tmpdir(), 'aetherfield-wayfarer-smoke-'));
  chrome = spawn(chromePath, [
    '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
    '--enable-webgl', '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader',
    '--remote-debugging-port=0', `--user-data-dir=${profile}`, mobile ? '--window-size=844,390' : '--window-size=1280,720', 'about:blank',
  ], { stdio: 'ignore' });
  const portFile = path.join(profile, 'DevToolsActivePort');
  const chromePort = await until(() => {
    if (chrome.exitCode !== null) throw new Error(`Chrome exited with ${chrome.exitCode}.`);
    return existsSync(portFile) ? Number(readFileSync(portFile, 'utf8').split('\n')[0]) : null;
  }, 20000);
  const tabs = await (await fetch(`http://127.0.0.1:${chromePort}/json`)).json();
  const tab = tabs.find(entry => entry.type === 'page');
  assert.ok(tab, 'Chrome did not expose a page target');
  socket = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let nextId = 0;
  const pending = new Map();
  const warnings = [];
  socket.onmessage = ({ data }) => {
    const reply = JSON.parse(data);
    if (reply.id) {
      const job = pending.get(reply.id);
      pending.delete(reply.id);
      if (reply.error) job?.reject(new Error(reply.error.message));
      else job?.resolve(reply.result);
    } else if (reply.method === 'Runtime.consoleAPICalled' && ['warning', 'error'].includes(reply.params.type)) {
      warnings.push(reply.params.args.map(arg => arg.value ?? arg.description).join(' '));
    }
  };
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const result = await call('Runtime.evaluate', { expression, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  };
  await call('Page.enable');
  await call('Runtime.enable');
  await call('Emulation.setDeviceMetricsOverride', mobile
    ? { width: 844, height: 390, deviceScaleFactor: 2, mobile: true }
    : { width: 1280, height: 720, deviceScaleFactor: 1, mobile: false });
  await call('Page.navigate', { url: `http://127.0.0.1:${port}/?starterPreview=1${auto ? '' : '&renderer=webgl2'}` });
  const probe = "(()=>({fatal:document.querySelector('#fatal-error')?.hidden === false ? document.querySelector('#fatal-error')?.textContent : null, renderer:document.querySelector('#renderer-label')?.textContent?.trim(), coords:document.querySelector('#map-coords')?.textContent?.trim(), fps:document.querySelector('#performance-fps')?.textContent?.trim(), visibility:document.visibilityState}))()";
  const ready = await until(async () => {
    const status = await evaluate(probe);
    if (status?.fatal) throw new Error(status.fatal);
    const z = Number(status?.coords?.split(',')[1]);
    return status?.renderer?.startsWith('WEB') && Number.isFinite(z) && z <= -23 ? status : null;
  }, 35000);
  if (!auto) assert.equal(ready.renderer, 'WEBGL2');
  await sleep(1800);
  const shot = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  writeFileSync(output, Buffer.from(shot.data, 'base64'));
  assert.ok(!warnings.some(message => /Wayfarer kit unavailable|Village lantern asset unavailable/.test(message)), 'Decorative GLBs must load');
  console.log(JSON.stringify({ output, bytes: readFileSync(output).length, renderer: ready.renderer, coords: ready.coords, fps: ready.fps, warnings: warnings.slice(-15) }, null, 2));
} finally {
  socket?.close();
  if (chrome?.pid) {
    if (process.platform === 'win32') spawnSync('taskkill.exe', ['/PID', String(chrome.pid), '/T', '/F'], { stdio: 'ignore', timeout: 5000 });
    else chrome.kill('SIGTERM');
    if (chrome.exitCode === null) await Promise.race([new Promise(resolve => chrome.once('close', resolve)), sleep(2000)]);
  }
  if (server) await server.close();
  if (profile && path.basename(profile).startsWith('aetherfield-wayfarer-smoke-')) {
    try { rmSync(profile, { recursive: true, force: true, maxRetries: 8, retryDelay: 400 }); }
    catch (error) { console.warn('Chrome profile could not be removed:', error); }
  }
}
