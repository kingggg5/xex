import type {ResourceKey} from './ui/combat-model';
export function createMutationReplayLedger(maximum?:number):{
	readonly ready:boolean;beginReconnect():void;
	bind(characterId:string):{changed:boolean;discarded:Array<{opId:string;resource:ResourceKey}>;replay:Array<{opId:string;resource:ResourceKey;packet:ArrayBuffer}>};
	register(opId:string,packet:ArrayBuffer,resource:ResourceKey):boolean;
	settle(opId:string):{resource:ResourceKey}|undefined;pending():Array<{opId:string;resource:ResourceKey}>;clear():void;
};
