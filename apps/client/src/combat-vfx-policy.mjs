/** Gameplay warnings and ally identity are never optional decoration. */
export function shouldShowCombatFx(kind,relation='mine',preferences={}) {
	if(kind==='telegraph'||kind==='nameplate'||kind==='party')return true;
	if(relation==='party'||relation==='mine')return true;
	return !preferences.hideOthers;
}
