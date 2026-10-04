import type {Mesh} from '@babylonjs/core/Meshes/mesh';
import type {SubMesh} from '@babylonjs/core/Meshes/subMesh';
export function applyLegacyPlantDensity(mesh:Mesh,density:number,originals:WeakMap<SubMesh,number>):void;
