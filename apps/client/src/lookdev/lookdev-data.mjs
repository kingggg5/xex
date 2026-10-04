/** Plain lookdev data: bounded samples, locked camera contracts and a dependency-free evidence ZIP. */
export const LOOKDEV_VIEWS = Object.freeze(["player", "side", "close", "elevated"]);
export const LOOKDEV_CAMERAS = Object.freeze({
	player: Object.freeze({ alpha: -Math.PI / 2, beta: 1.18, radius: 13, fov: 1.02 }),
	side: Object.freeze({ alpha: 0, beta: 1.18, radius: 13, fov: 1.02 }),
	close: Object.freeze({ alpha: -1.32, beta: 1.22, radius: 2.5, fov: .92 }),
	elevated: Object.freeze({ alpha: -1.27, beta: .65, radius: 26, fov: 1.02 }),
});
export const LOOKDEV_MAX_SAMPLES = 10000;
export const LOOKDEV_MAX_ARCHIVE_BYTES = 48 * 1024 * 1024;
export function evidenceSlug(value, fallback = "baseline") {
	return typeof value === "string" && /^[a-z0-9][a-z0-9_-]{0,63}$/i.test(value) ? value.toLowerCase() : fallback;
}
export function parseLookdevRequest(search) {
	const params = new URLSearchParams(search);
	if (params.get("lookdev") !== "1") return null;
	const distance = Number(params.get("lodDistance"));
	return { pillar: evidenceSlug(params.get("set"), "water"), cycle: evidenceSlug(params.get("cycle"), "baseline"),
		variant: params.get("variant") === "B" ? "B" : "A", lodDistance: distance === 40 || distance === 120 ? distance : null };
}
export function clonePrimitiveMetadata(input) {
	let keys = 0, stringBytes = 0; const parents = new WeakSet(), encoder = new TextEncoder();
	const visit = (value, depth) => {
		if (value === null || typeof value === "boolean") return value;
		if (typeof value === "string") {
			if (value.length > 65536) throw new Error("Lookdev metadata string exceeded limit");
			stringBytes += encoder.encode(value).byteLength;
			if (stringBytes > 65536) throw new Error("Lookdev metadata strings exceeded 64 KiB");
			return value;
		}
		if (typeof value === "number" && Number.isFinite(value)) return value;
		if (depth > 6 || value === null || typeof value !== "object" || parents.has(value)) throw new Error("Lookdev metadata must contain bounded primitive DTOs only");
		if (!Array.isArray(value) && ![Object.prototype, null].includes(Object.getPrototypeOf(value))) throw new Error("Engine/class objects are not lookdev metadata");
		parents.add(value);
		if (Array.isArray(value)) { if (value.length > 256) throw new Error("Lookdev metadata array exceeded limit"); const result = value.map(entry => visit(entry, depth + 1)); parents.delete(value); return result; }
		const entries = Object.entries(value); keys += entries.length;
		if (keys > 256 || entries.some(([key]) => key.length > 256 || ["__proto__", "constructor", "prototype"].includes(key))) throw new Error("Lookdev metadata keys exceeded limit");
		const result = Object.fromEntries(entries.map(([key, entry]) => [key, visit(entry, depth + 1)])); parents.delete(value); return result;
	};
	const output = visit(input, 0);
	if (output === null || typeof output !== "object" || Array.isArray(output) || encoder.encode(JSON.stringify(output)).byteLength > 65536) throw new Error("Lookdev metadata must be an object of at most 64 KiB");
	return output;
}
export function lockedCamera(view, target, lodDistance = null) {
	if (!LOOKDEV_VIEWS.includes(view) || !target || [target.x, target.y, target.z].some(value => !Number.isFinite(value))) throw new Error("Invalid lookdev camera contract");
	if (lodDistance !== null && lodDistance !== 40 && lodDistance !== 120) throw new Error("Unsupported LOD review distance");
	return { view, ...LOOKDEV_CAMERAS[view], radius: lodDistance ?? LOOKDEV_CAMERAS[view].radius, target: { x: target.x, y: target.y, z: target.z } };
}
export function summarize(values) {
	const finite = Array.from(values).filter(Number.isFinite).sort((a, b) => a - b);
	if (!finite.length) return { n: 0, p50: null, p95: null, min: null, max: null };
	const quantile = fraction => finite[Math.max(0, Math.ceil(fraction * finite.length) - 1)];
	return { n: finite.length, p50: quantile(.5), p95: quantile(.95), min: finite[0], max: finite.at(-1) };
}
/** One row represents one sampled render. Missing GPU samples stay missing, never zero. */
export class LookdevSampleWindow {
	constructor(capacity = 600) {
		this.capacity = Math.max(30, Math.min(LOOKDEV_MAX_SAMPLES, Math.floor(Number.isFinite(capacity) ? capacity : 600)));
		this.fields = ["frameIntervalMs", "cpuSceneMs", "cpuSubmissionMs", "cpuTargetsMs", "gpuMs", "drawCalls", "activeMeshes", "activeTriangles", "particles"];
		this.columns = Object.fromEntries(this.fields.map(field => [field, new Float64Array(this.capacity)]));
		this.focusFlags = new Uint8Array(this.capacity);
		this.reset();
	}
	reset() { this.length = 0; this.next = 0; this.total = 0; }
	push(sample) {
		for (const field of this.fields) this.columns[field][this.next] = Number.isFinite(sample[field]) && sample[field] >= 0 ? sample[field] : NaN;
		this.focusFlags[this.next] = sample.focused === true ? 2 : sample.focused === false ? 1 : 0;
		this.next = (this.next + 1) % this.capacity; this.length = Math.min(this.capacity, this.length + 1); this.total++;
	}
	snapshot() {
		let focusedFrames = 0, unfocusedFrames = 0, unknownFrames = 0;
		for (let index = 0; index < this.length; index++) { const flag = this.focusFlags[index]; if (flag === 2) focusedFrames++; else if (flag === 1) unfocusedFrames++; else unknownFrames++; }
		return { capacity: this.capacity, retained: this.length, total: this.total, focus: { focusedFrames, unfocusedFrames, unknownFrames },
			...Object.fromEntries(this.fields.map(field => [field, summarize(this.columns[field].subarray(0, this.length))])) };
	}
}
const crcTable = Uint32Array.from({ length: 256 }, (_, value) => {
	let crc = value; for (let bit = 0; bit < 8; bit++) crc = crc & 1 ? 0xedb88320 ^ crc >>> 1 : crc >>> 1; return crc >>> 0;
});
export function crc32(bytes) { let crc = 0xffffffff; for (const byte of bytes) crc = crcTable[(crc ^ byte) & 255] ^ crc >>> 8; return (crc ^ 0xffffffff) >>> 0; }
/** ZIP STORE, UTF-8 filenames, no ZIP64. Limits protect browser memory and prohibit unsafe paths. */
export function createEvidenceZip(files) {
	if (!Array.isArray(files) || files.length < 1 || files.length > 16) throw new Error("Evidence file count exceeded");
	let total = 22; const seen = new Set(); const prepared = files.map(file => {
		if (!file || typeof file.name !== "string" || file.name.length > 240 || !/^[a-zA-Z0-9_./-]+$/.test(file.name)
			|| file.name.startsWith("/") || file.name.split("/").some(part => !part || part === "." || part === "..") || seen.has(file.name)
			|| !(file.bytes instanceof Uint8Array)) throw new Error("Invalid evidence file");
		seen.add(file.name); const name = new TextEncoder().encode(file.name);
		total += 30 + 46 + name.length * 2 + file.bytes.length;
		if (total > LOOKDEV_MAX_ARCHIVE_BYTES) throw new Error("Evidence archive exceeds 48 MiB limit");
		return { ...file, nameBytes: name, crc: crc32(file.bytes) };
	});
	if (total > LOOKDEV_MAX_ARCHIVE_BYTES) throw new Error("Evidence archive exceeds 48 MiB limit");
	const result = new Uint8Array(total), view = new DataView(result.buffer); let offset = 0;
	const u16 = (at, value) => view.setUint16(at, value, true), u32 = (at, value) => view.setUint32(at, value, true);
	for (const file of prepared) {
		file.offset = offset; u32(offset, 0x04034b50); u16(offset + 4, 20); u16(offset + 6, 0x800); u16(offset + 12, 0x21);
		u32(offset + 14, file.crc); u32(offset + 18, file.bytes.length); u32(offset + 22, file.bytes.length); u16(offset + 26, file.nameBytes.length);
		result.set(file.nameBytes, offset + 30); result.set(file.bytes, offset + 30 + file.nameBytes.length); offset += 30 + file.nameBytes.length + file.bytes.length;
	}
	const directory = offset;
	for (const file of prepared) {
		u32(offset, 0x02014b50); u16(offset + 4, 20); u16(offset + 6, 20); u16(offset + 8, 0x800); u16(offset + 14, 0x21);
		u32(offset + 16, file.crc); u32(offset + 20, file.bytes.length); u32(offset + 24, file.bytes.length); u16(offset + 28, file.nameBytes.length); u32(offset + 42, file.offset);
		result.set(file.nameBytes, offset + 46); offset += 46 + file.nameBytes.length;
	}
	u32(offset, 0x06054b50); u16(offset + 8, prepared.length); u16(offset + 10, prepared.length); u32(offset + 12, offset - directory); u32(offset + 16, directory);
	return result;
}
export function compareLookdevPacks(a, b) {
	const mismatches = [];
	if (!a || !b || !Array.isArray(a.captures) || !Array.isArray(b.captures) || a.captures.length !== 4 || b.captures.length !== 4) return { comparable: false, mismatches: ["Four views required in both packs"], deltas: [] };
	const stable = value => value !== null && typeof value === "object" ? Array.isArray(value) ? value.map(stable) : Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
	const same = (left, right) => { try { return JSON.stringify(stable(left)) === JSON.stringify(stable(right)); } catch { return false; } };
	for (const key of ["pillar", "settings", "lodDistance"]) if (!same(a[key], b[key])) mismatches.push(`Different ${key}`);
	if (!a.capturePhaseFrozen || !b.capturePhaseFrozen) mismatches.push("Animation phase was not frozen by the host");
	if (a.metadata?.phaseSeed == null || a.metadata.phaseSeed !== b.metadata?.phaseSeed) mismatches.push("Missing or different shared phase seed");
	if (typeof a.metadata?.deviceLabel !== "string" || !a.metadata.deviceLabel || a.metadata.deviceLabel !== b.metadata?.deviceLabel) mismatches.push("Missing or different host device identity");
	const deltas = [];
	for (const view of LOOKDEV_VIEWS) {
		const left = a.captures.find(capture => capture.view === view), right = b.captures.find(capture => capture.view === view);
		if (!left || !right) { mismatches.push(`Missing ${view} view`); continue; }
		for (const key of ["camera", "renderIdentity", "imageSize"]) if (!same(left[key], right[key])) mismatches.push(`${view}: different ${key}`);
		const exposures = [left.metrics?.window?.focus, right.metrics?.window?.focus];
		if (exposures.some(focus => !focus || focus.unfocusedFrames > 0 || focus.unknownFrames > 0 || focus.focusedFrames < 30)) mismatches.push(`${view}: missing or unfocused baseline exposure`);
		const delta = metric => {
			const av = left.metrics?.window?.[metric]?.p95, bv = right.metrics?.window?.[metric]?.p95;
			return Number.isFinite(av) && Number.isFinite(bv) ? bv - av : null;
		};
		const gpuQualified = left.metrics?.gpuStatus === "available" && right.metrics?.gpuStatus === "available"
			&& left.metrics?.window?.gpuMs?.n >= 30 && right.metrics?.window?.gpuMs?.n >= 30;
		deltas.push({ view, p95FrameMs: delta("frameIntervalMs"), p95CpuMs: delta("cpuSceneMs"), p95GpuMs: gpuQualified ? delta("gpuMs") : null, p95DrawCalls: delta("drawCalls"), p95ActiveTriangles: delta("activeTriangles") });
	}
	return { comparable: mismatches.length === 0, mismatches, deltas: mismatches.length ? [] : deltas };
}
