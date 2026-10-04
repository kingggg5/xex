import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const clientRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.join(clientRoot, "src", "assets", "codecs", "ktx2decoder.worker.js");

mkdirSync(path.dirname(output), { recursive: true });
await build({
	entryPoints: [path.join(clientRoot, "src", "ktx2decoder.worker.ts")],
	bundle: true,
	format: "iife",
	platform: "browser",
	target: "es2022",
	outfile: output,
	minify: true,
	legalComments: "eof",
});
