import { copyFile, mkdir, readdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
// apps/client/scripts -> repo root/content/build
const buildRoot = resolve(scriptDirectory, "../../../content/build");
const destinationDir = resolve(scriptDirectory, "../public/content");

let entries;
try {
	entries = await readdir(buildRoot, { withFileTypes: true });
} catch {
	console.error("content/build is missing: run `cargo run --manifest-path apps/server/Cargo.toml --bin build_content` first.");
	process.exit(1);
}
const hashes = entries.filter((entry) => entry.isDirectory()).map((entry) => entry.name);
if (hashes.length !== 1) {
	console.error(`content/build must contain exactly one bundle, found ${hashes.length}. Rebuild content.`);
	process.exit(1);
}
await mkdir(destinationDir, { recursive: true });
await copyFile(resolve(buildRoot, hashes[0], "bundle.json"), resolve(destinationDir, "bundle.json"));
console.log(`content bundle ${hashes[0]} synced for the client.`);
