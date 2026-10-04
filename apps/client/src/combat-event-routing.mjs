/** Source IDs and target IDs use different wire enums: player source=0, player target=1. */
export function combatEventPresentation(event, playerId) {
	const mine = playerId > 0 && event.source_kind === 0 && event.source_id === playerId;
	const hurtsMe = playerId > 0 && event.target_kind === 1 && event.target_id === playerId;
	const miss = (event.flags & 64) !== 0;
	const damaging = !miss && event.amount > 0;
	const crit = damaging && (event.flags & 32) !== 0;
	const perfect = (event.flags & 4) !== 0;
	const evade = (event.flags & 8) !== 0;
	return {
		mine, hurtsMe, damaging, crit, miss,
		localImpact: mine && event.target_kind === 0 && damaging,
		hitStopMs: mine && event.target_kind === 0 && damaging
			? (event.flags & 1) !== 0 ? 110 : crit || perfect ? 85 : event.action === 'arc_slash' ? 70 : 50
			: 0,
		word: miss ? 'miss' : evade ? 'evade' : perfect ? event.target_kind === 0 ? 'counter' : 'parry' : null,
		damageKind: event.target_kind === 1 ? 'player' : crit ? 'crit' : 'monster',
	};
}

/** Hitstop belongs to presentation only; no visual effect may gate the fixed-step scheduler. */
export function movementSimulationEnabled({lookdev = false} = {}) { return !lookdev; }

export function gameplayInputBlocked({ready, dead, hidden, typing, uiBlocked, mobileBlocked, editing, cityHeld}) {
	return !ready || dead || hidden || typing || uiBlocked || mobileBlocked || editing || cityHeld;
}
