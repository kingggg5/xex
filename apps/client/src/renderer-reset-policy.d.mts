export function createManualGraphicsReset(options:{onLost:(reason:string)=>void;onReload:()=>void;schedule?:typeof setTimeout;cancel?:typeof clearTimeout;enableReloadDelayMs?:number}):{lost(reason?:string):boolean;reload():boolean;state():'healthy'|'lost'|'reloading'|'disposed';dispose():void};
export function rendererFailureReason(error:unknown):string;
