import type {CombatEvent} from './protocol';
export function combatEventPresentation(event: CombatEvent, playerId: number): {
	mine:boolean; hurtsMe:boolean; damaging:boolean;crit:boolean;miss:boolean;localImpact:boolean;hitStopMs:number;
	word:'miss'|'evade'|'parry'|'counter'|null;damageKind:'player'|'crit'|'monster';
};
export function movementSimulationEnabled(options?:{lookdev?:boolean}):boolean;
export function gameplayInputBlocked(options:{ready:boolean;dead:boolean;hidden:boolean;typing:boolean;uiBlocked:boolean;mobileBlocked:boolean;editing:boolean;cityHeld:boolean}):boolean;
