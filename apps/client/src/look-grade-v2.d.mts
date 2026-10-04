export interface LookGrade {
 readonly zenith:number[]; readonly horizon:number[]; readonly fog:number[];
 readonly sun:number[]; readonly fill:number[]; readonly ground:number[];
 readonly sunIntensity:number; readonly fillIntensity:number; readonly exposure:number;
 readonly contrast:number; readonly saturation:number; readonly fogDensity:number;
}
export interface PoolAnchor { x:number; y:number; z:number }
export function sampleLookGrade(state:{readonly hours:number;readonly daylight:number;readonly rain:number}):LookGrade;
export function skyCanvasFraction(elevationDeg:number):number;
export function poolStrength(daylight:number, rain?:number):number;
export const LOOK_POOL:{readonly radius:number;readonly color:readonly number[];readonly cell:number;readonly emitterPattern:RegExp};
export function clusterAnchors(points:Iterable<readonly number[]>, cell?:number, existing?:readonly PoolAnchor[]):PoolAnchor[];
