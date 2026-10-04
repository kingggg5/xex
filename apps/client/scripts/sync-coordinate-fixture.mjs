import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const source = resolve(scriptDirectory, "../../protocol/coordinate-fixture-v1.json");
const destination = resolve(scriptDirectory, "../public/coordinate-fixture-v1.json");

await mkdir(dirname(destination), { recursive: true });
await copyFile(source, destination);
