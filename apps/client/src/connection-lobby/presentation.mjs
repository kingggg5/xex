/** Presentation preserves server facts and caps data before it enters reactive state. */
export function lobbyRooms(rooms, worldName) {
	if (!Array.isArray(rooms)) return [];
	const seen = new Set();
	return rooms.slice(0, 256).flatMap(room => {
		if (!room || !Number.isSafeInteger(room.channel) || room.channel < 0 || room.channel > 9999 || seen.has(room.channel)
			|| !Number.isSafeInteger(room.players) || room.players < 0 || !Number.isSafeInteger(room.capacity) || room.capacity < 1) return [];
		seen.add(room.channel);
		return [{ channel: room.channel, players: room.players, capacity: room.capacity,
			name: typeof room.name === 'string' && room.name.trim() ? room.name.trim().slice(0, 96) : worldName }];
	}).sort((a, b) => a.channel - b.channel);
}
export function displayChannel(channel) { return String(channel + 1).padStart(2, '0'); }
export function displayLatency(value) { return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? `~${Math.round(value)} ms` : '—'; }
export function transferText(event) {
	if (!event?.resource || !Number.isSafeInteger(event.loaded) || !Number.isSafeInteger(event.total) || event.total <= 0 || event.loaded < 0 || event.loaded > event.total) return null;
	const format = value => value >= 1048576 ? `${(value / 1048576).toFixed(1)} MiB` : value >= 1024 ? `${(value / 1024).toFixed(1)} KiB` : `${value} B`;
	return `${format(event.loaded)} / ${format(event.total)}`;
}
export function chosenAvailable(model) {
	return model.hasSelection && (model.selected === null ? model.autoAvailable : model.rooms.some(room => room.channel === model.selected && room.players < room.capacity));
}
