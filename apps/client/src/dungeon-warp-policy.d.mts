export const DUNGEON_WARP_HUB:Readonly<{id:string;x:number;z:number;radius:number;effectDistance:number;platformTopY:number;cityLocalXZ:readonly number[]}>;
export const DUNGEON_DESTINATIONS:readonly {id:string;name:string;thai:string;description:string;thaiDescription:string;kind:string}[];
export function warpDestinationEnabled(id:string,state?:{connected?:boolean;busy?:boolean}):boolean;
export function warpProximity(player:{x:number;z:number},origin?:{x:number;z:number;radius:number;effectDistance:number}):{near:boolean;effects:boolean};
