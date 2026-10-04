export interface RendererHealth {status:'BLANK_RENDER'|'INVALID_RENDER'|'NONEMPTY_OUTPUT'|'UNVERIFIED';valid:boolean|null;blankRender:boolean|null;gpuErrors:number;validationErrors:number;probe:string;messages:Array<{kind:string;message:string}>;}
export interface RendererHealthTracker {error(kind:string,message:string):boolean;readback(rgba:unknown,options?:{ready?:boolean;scope?:string}):RendererHealth;snapshot():RendererHealth;dispose():void;}
export function createRendererHealth():RendererHealthTracker;
