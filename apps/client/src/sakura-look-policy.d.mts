export const SAKURA_TREE_IDS:readonly string[];
export const SAKURA_PALETTE:Readonly<{shadow:readonly number[];petal:readonly number[]}>;
export function isSakuraPlacement(placement:{id:string}):boolean;
export function sakuraPlacement<T extends {id:string;species:string}>(placement:T):T;
export function sakuraShaderCode(wgsl?:boolean):string;
