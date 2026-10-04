import type {ActionKind,CombatActionKind} from './protocol';
export const COMBAT_ACTIONS:ReadonlyArray<Readonly<{action:CombatActionKind;id:number;code:string|null;key:string|null;player:boolean;en:string;th:string}>>;
export const ACTION_IDS:Readonly<Record<CombatActionKind,number>>;
export const PLAYER_ACTION_IDS:Readonly<Record<ActionKind,number>>;
export const ACTION_NAMES:Map<number,CombatActionKind>;
export const ACTION_BINDINGS:Readonly<Record<string,ActionKind>>;
export function actionByCode(code:string):ActionKind|null;
export function actionDescription(action:string,locale?:string):{label:string;key:string|null}|null;
