/** Bounded local UI assets; streaming avoids allocating an unbounded response body. */
export async function readUiResource(url: string, maximumBytes: number, signal?: AbortSignal): Promise<ArrayBuffer> {
	const deadline = AbortSignal.timeout(12_000);
	const requestSignal = signal ? AbortSignal.any([signal, deadline]) : deadline;
	const response = await fetch(url, { credentials: "same-origin", signal: requestSignal });
	if (!response.ok || Number(response.headers.get("content-length")) > maximumBytes) throw new Error("UI resource unavailable or too large");
	const reader = response.body?.getReader();
	if (!reader) throw new Error("UI resource has no body");
	const chunks: Uint8Array[] = [];
	let count = 0;
	try {
		while (true) {
			const chunk = await reader.read();
			if (chunk.done) break;
			count += chunk.value.byteLength;
			if (count > maximumBytes) { await reader.cancel(); throw new Error("UI resource exceeds its byte budget"); }
			chunks.push(chunk.value);
		}
	} finally { reader.releaseLock(); }
	const bytes = new Uint8Array(count);
	let offset = 0;
	for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
	return bytes.buffer;
}
