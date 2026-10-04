// One command for a before/after check of the current tree against a captured baseline:
//   node tools/capture/ab.mjs --label <new label> [--baseline 2026-10-02-A] [--only city-noon] [--noise <A/A report.json>]
// 1. build.mjs --label <label>  2. capture.mjs with the baseline's shot list  3. compare.py baseline vs new (A/A noise floor)
// Prints the report.html path. Extra capture flags (--max-minutes, --vsync, --resume, --no-ledger) pass through.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { REPO, SCRATCH, TOOL_DIR, log, parseArgs, slug } from "./lib.mjs";

const args = parseArgs(process.argv.slice(2), { booleans: ["resume", "noLedger", "skipBuild"] });
if (!args.label) { console.error("usage: node tools/capture/ab.mjs --label <new label> [--baseline 2026-10-02-A] [--only a,b] [--noise report.json]"); process.exit(2); }
const label = slug(args.label), baseline = slug(args.baseline ?? "2026-10-02-A");
const searchDirs = [args.runs, join(REPO, "planning", "evidence", "captures"), join(REPO, "planning", "evidence", "capture-baseline-20261002", "runs")].filter(Boolean).map(dir => resolve(dir));
const baselineDir = searchDirs.map(dir => join(dir, baseline)).find(dir => existsSync(join(dir, "run.json")));
if (!baselineDir) throw new Error(`Baseline run ${baseline} not found in ${searchDirs.join(", ")}`);
const baselineRun = JSON.parse(readFileSync(join(baselineDir, "run.json"), "utf8"));
const shots = resolve(REPO, args.shots ?? baselineRun.shotList.path);
const out = resolve(args.out ?? join(REPO, "planning", "evidence", "captures"));
const dist = args.dist ? resolve(args.dist) : join(SCRATCH, `dist-capture-${label}`);
if (args.dist && !args.skipBuild) throw new Error("--dist reuses an existing build; pass --skip-build with it");
const defaultNoise = join(REPO, "planning", "evidence", "capture-baseline-20261002", "compare-A-vs-A-rerun", "report.json");
const noise = args.noise ? resolve(args.noise) : existsSync(defaultNoise) ? defaultNoise : null;
const step = (command, commandArgs) => {
	log(`$ ${[command, ...commandArgs].join(" ")}`);
	const result = spawnSync(command, commandArgs, { cwd: REPO, stdio: "inherit", windowsHide: true });
	if (result.status !== 0) throw new Error(`${command} exited with ${result.status}`);
};
if (!args.skipBuild) step(process.execPath, [join(TOOL_DIR, "build.mjs"), "--label", label]);
const pass = ["only", "maxMinutes", "vsync", "views"].flatMap(key => args[key] === undefined ? [] : [`--${key.replace(/[A-Z]/g, c => `-${c.toLowerCase()}`)}`, String(args[key])]);
if (args.resume) pass.push("--resume");
if (args.noLedger) pass.push("--no-ledger");
const capture = spawnSync(process.execPath, [join(TOOL_DIR, "capture.mjs"), "--label", label, "--shots", shots, "--dist", dist, "--out", out, ...pass], { cwd: REPO, stdio: "inherit", windowsHide: true });
if (capture.status !== 0) log(`capture exited with ${capture.status}; comparing what was captured`);
const report = join(out, `compare-${baseline}-vs-${label}`);
step("python", [join(TOOL_DIR, "compare.py"), "--before", baselineDir, "--after", join(out, label), "--out", report, ...(noise ? ["--noise", noise] : []), "--title", `${baseline} → ${label}`]);
log(`report: ${join(report, "report.html")}`);
