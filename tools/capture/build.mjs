// Production build for capture runs.
//   node tools/capture/build.mjs --label 2026-10-02-A [--out <dir>] [--plain] [--skip-prebuild]
// 1. Runs the client prebuild scripts (codec worker, coordinate fixture, content sync), as `npm run build` does.
// 2. `vite build` with apps/client/vite.config.ts in production mode (minified, NODE_ENV=production,
//    production Svelte) into <scratchpad>/dist-capture-<label>.
//    The one difference from a plain build: import.meta.env.DEV is defined true, because the lookdev sandbox,
//    the locked cameras and window.__xexoria are DEV-gated and a plain build strips them. Each DEV hook acts
//    only when its URL parameter is present. --plain builds without the define (no locked views).
// 3. Writes capture-build.json (source + dist hashes, git state) into the build directory.
import { spawnSync } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { CLIENT, SCRATCH, gitState, log, parseArgs, slug, treeHash } from "./lib.mjs";

const args = parseArgs(process.argv.slice(2), { booleans: ["plain", "skipPrebuild"] });
if (!args.label) { console.error("usage: node tools/capture/build.mjs --label <label> [--out <dir>] [--plain] [--skip-prebuild]"); process.exit(2); }
const label = slug(args.label);
const outDir = resolve(args.out ?? join(SCRATCH, `dist-capture-${label}`));
const devHooks = !args.plain;
const prebuild = ["scripts/build-codec-worker.mjs", "scripts/sync-coordinate-fixture.mjs", "scripts/sync-content.mjs"];

const started = Date.now();
if (!args.skipPrebuild) {
	for (const script of prebuild) {
		log("prebuild", script);
		const result = spawnSync(process.execPath, [script], { cwd: CLIENT, stdio: "inherit", windowsHide: true });
		if (result.status !== 0) throw new Error(`${script} failed with ${result.status}`);
	}
}
const vite = await import(pathToFileURL(join(CLIENT, "node_modules", "vite", "dist", "node", "index.js")).href);
log(`vite ${vite.version} build -> ${outDir}${devHooks ? " (DEV review hooks defined)" : " (plain)"}`);
const buildStarted = Date.now();
await vite.build({
	root: CLIENT, configFile: join(CLIENT, "vite.config.ts"), mode: "production", logLevel: "warn",
	...(devHooks ? { define: { "import.meta.env.DEV": "true" } } : {}),
	build: { outDir, emptyOutDir: true },
});
const buildMs = Date.now() - buildStarted;
if (!existsSync(join(outDir, "index.html"))) throw new Error("vite build produced no index.html");
const skipSource = (_path, name) => name === "node_modules" || name === "__pycache__" || name === ".vite";
const source = treeHash(join(CLIENT, "src"), { skip: skipSource });
const dist = treeHash(outDir, { skip: (_path, name) => name === "capture-build.json" });
const receipt = {
	schema: "xexoria-capture-build/1", label, outDir, builtAt: new Date().toISOString(), buildMs, totalMs: Date.now() - started,
	vite: vite.version, mode: "production", nodeEnv: process.env.NODE_ENV ?? null, devHooks,
	define: devHooks ? { "import.meta.env.DEV": "true" } : {}, prebuild: args.skipPrebuild ? [] : prebuild,
	buildHash: dist.sha256.slice(0, 16), distSha256: dist.sha256, distFiles: dist.files, distBytes: dist.bytes,
	sourceSha256: source.sha256, sourceFiles: source.files, git: gitState(),
};
writeFileSync(join(outDir, "capture-build.json"), JSON.stringify(receipt, null, 2));
log(`build ${receipt.buildHash} · ${dist.files} files · ${(dist.bytes / 1048576).toFixed(0)} MiB · ${(buildMs / 1000).toFixed(1)} s`);
console.log(JSON.stringify({ outDir, buildHash: receipt.buildHash, sourceSha256: source.sha256.slice(0, 16), devHooks }, null, 2));
