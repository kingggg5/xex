/** Canonical client action IDs, controls and readable tutorial labels. Wire IDs match Rust v7. */
export const COMBAT_ACTIONS=Object.freeze([
	Object.freeze({action:'attack',id:1,code:'KeyF',key:'F',player:true,en:'Attack',th:'โจมตี'}),
	Object.freeze({action:'arc_slash',id:2,code:'Digit1',key:'1',player:true,en:'Arc Slash',th:'ฟันกวาด'}),
	Object.freeze({action:'dodge',id:3,code:'Space',key:'Space',player:true,en:'Quickstep',th:'หลบ'}),
	Object.freeze({action:'guard',id:4,code:'KeyG',key:'G',player:true,en:'Guard',th:'ป้องกัน'}),
	Object.freeze({action:'splash_hop',id:5,code:null,key:null,player:false,en:'Splash Hop',th:'กระโดดกระแทก'}),
]);
export const ACTION_IDS=Object.freeze(Object.fromEntries(COMBAT_ACTIONS.map(row=>[row.action,row.id])));
export const PLAYER_ACTION_IDS=Object.freeze(Object.fromEntries(COMBAT_ACTIONS.filter(row=>row.player).map(row=>[row.action,row.id])));
export const ACTION_NAMES=new Map(COMBAT_ACTIONS.map(row=>[row.id,row.action]));
export const ACTION_BINDINGS=Object.freeze(Object.fromEntries(COMBAT_ACTIONS.filter(row=>row.player).map(row=>[row.code,row.action])));
export function actionByCode(code){return ACTION_BINDINGS[code]??null;}
export function actionDescription(action,locale='en'){const row=COMBAT_ACTIONS.find(row=>row.action===action);return row?{label:row[locale==='th'?'th':'en'],key:row.key}:null;}
