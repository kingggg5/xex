/** Bounded snapshot identity registry. Validate the entire snapshot before changing visible state. */
export function createMonsterViewRegistry(adapter, maximum = 64) {
	if (!Number.isInteger(maximum) || maximum < 1 || maximum > 64) throw new RangeError('invalid monster view cap');
	const entries = new Map();
	let disposed = false;
	function synchronize(monsters) {
		if (disposed) return;
		if (!Array.isArray(monsters) || monsters.length > maximum) throw new RangeError('monster snapshot exceeds view cap');
		const incoming = new Set();
		for (const monster of monsters) {
			if (!Number.isSafeInteger(monster.id) || monster.id <= 0 || !Number.isInteger(monster.kind) || monster.kind <= 0 || incoming.has(monster.id)) throw new TypeError('invalid or duplicate monster identity');
			incoming.add(monster.id);
		}
		for (const [id, entry] of entries) {
			if (!incoming.has(id)) { adapter.dispose(entry.view, id); entries.delete(id); }
		}
		for (const monster of monsters) {
			let entry = entries.get(monster.id);
			if (entry && entry.kind !== monster.kind) {
				adapter.dispose(entry.view, monster.id); entries.delete(monster.id); entry = undefined;
			}
			if (!entry) {
				entry = {kind:monster.kind,view:adapter.create(monster)};
				entries.set(monster.id, entry);
			}
			adapter.update(entry.view, monster);
		}
	}
	function dispose() {
		if (disposed) return; disposed = true;
		for (const [id, entry] of entries) adapter.dispose(entry.view, id);
		entries.clear();
	}
	return {synchronize,dispose,get:(id)=>entries.get(id)?.view,size:()=>entries.size};
}
