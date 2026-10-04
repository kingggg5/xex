/** Serialization fixture only: import with the Python collector to verify standard ZIP interoperability. */
import { writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { createEvidenceZip } from "../src/lookdev/lookdev-data.mjs";

const output = process.argv[2];
if (!output) throw new Error("Pass the output ZIP path");
const bytes = Uint8Array.from(Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42EAAAAASUVORK5CYII=", "base64"));
const cycle = `interop-${Date.now()}`, prefix = `lookdev/fixture/${cycle}`;
const captures = ["player", "side", "close", "elevated"].map(view => ({ view, image: `A-${view}.png`, bytes: bytes.length,
	sha256: createHash("sha256").update(bytes).digest("hex"), imageSize: { width: 1, height: 1 } }));
const manifest = { schema: "xexoria-lookdev-v0", pillar: "fixture", cycle, variant: "A", captures,
	qualification: "Static 1px serialization fixture; no renderer, image quality or device claim" };
const zip = createEvidenceZip([...captures.map(capture => ({ name: `${prefix}/${capture.image}`, bytes })),
	{ name: `${prefix}/A-manifest.json`, bytes: new TextEncoder().encode(JSON.stringify(manifest)) }]);
await writeFile(output, zip); console.log(JSON.stringify({ archive: output, cycle, bytes: zip.length, qualification: manifest.qualification }));
