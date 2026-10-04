/** Imperative adapter boundary: dispatch releases on their original targets before dropping capture. */
export function releaseHeldInputs(ledger, events) {
	const records = ledger.drain(); let failures = 0;
	for (const record of records.keys) {
		try {
			record.target.dispatchEvent(events.keyUp(record));
			if (events.isDisconnected?.(record.target)) events.globalKeyUp?.(record);
		} catch { failures++; }
	}
	for (const record of records.pointers) {
		try { const event = events.pointerCancel(record); if (event) record.target.dispatchEvent(event); } catch { failures++; }
		try { if (typeof record.target.hasPointerCapture === 'function' && record.target.hasPointerCapture(record.pointerId)) record.target.releasePointerCapture(record.pointerId); } catch { failures++; }
	}
	return { keys: records.keys.length, pointers: records.pointers.length, failures };
}
