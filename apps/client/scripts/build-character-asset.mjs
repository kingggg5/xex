import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const clientRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(clientRoot, "..", "..");
const source = path.join(repoRoot, "assets", "characters", "quaternius-rpg", "Warrior.gltf");
const output = path.join(clientRoot, "src", "assets", "characters", "quaternius-warrior.meshopt-etc1s.glb");
const cli = path.join(clientRoot, "node_modules", "@gltf-transform", "cli", "bin", "cli.js");
const ktxBin = process.env.KTX_SOFTWARE_BIN;

if (!existsSync(source)) throw new Error(`Missing CC0 source model: ${source}`);
if (!existsSync(cli)) throw new Error("Missing glTF Transform CLI. Run npm install in apps/client first.");
if (!ktxBin) throw new Error("Set KTX_SOFTWARE_BIN to the KTX-Software 4.4.2 bin directory before rebuilding this asset.");

const ktxExecutable = path.join(ktxBin, process.platform === "win32" ? "ktx.exe" : "ktx");
if (!existsSync(ktxExecutable)) throw new Error(`KTX CLI not found: ${ktxExecutable}`);
const version = spawnSync(ktxExecutable, ["--version"], { encoding: "utf8" });
if (version.status !== 0 || !`${version.stdout}\n${version.stderr}`.includes("4.4.2")) {
	throw new Error("This asset recipe is pinned to KTX-Software 4.4.2.");
}

mkdirSync(path.dirname(output), { recursive: true });
const temporaryRoot = mkdtempSync(path.join(tmpdir(), "aetherfield-warrior-"));
const intermediate = path.join(temporaryRoot, "warrior-etc1s.glb");
const environment = {
	...process.env,
	PATH: [ktxBin, process.env.PATH ?? ""].filter(Boolean).join(path.delimiter),
};

function run(args) {
	const result = spawnSync(process.execPath, [cli, ...args], {
		cwd: repoRoot,
		env: environment,
		stdio: "inherit",
	});
	if (result.error) throw result.error;
	if (result.status !== 0) throw new Error(`gltf-transform ${args[0]} failed with status ${result.status}`);
}

try {
	// Texture conversion runs first; the final Meshopt pass must be last so the
	// EXT_meshopt_compression extension remains in the shipped GLB.
	run(["etc1s", source, intermediate, "--slots", "baseColor", "--quality", "255"]);
	run(["meshopt", intermediate, output, "--level", "medium"]);
} finally {
	const resolvedTempRoot = path.resolve(temporaryRoot);
	const resolvedTempParent = path.resolve(tmpdir());
	if (path.dirname(resolvedTempRoot) !== resolvedTempParent || !path.basename(resolvedTempRoot).startsWith("aetherfield-warrior-")) {
		throw new Error("Refusing to remove an unexpected temporary asset-build directory.");
	}
	rmSync(resolvedTempRoot, { recursive: true, force: true });
}
