export function rgbToLab(r:number,g:number,b:number):number[];
export function deltaE00(a:readonly number[],b:readonly number[]):number;
export function measureDraftVfxPixels(rgba:Uint8Array|Uint8ClampedArray,background:Uint8Array|Uint8ClampedArray,width:number,height:number,roi:{x:number;y:number;width:number;height:number}):{changedPixels:number;roiChangedPixels:number;screenCoverage:number;colourfulnessM:number|null;whiteClipFraction:number|null;basis:string};
