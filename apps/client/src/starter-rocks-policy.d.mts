import type { Scene } from '@babylonjs/core/scene';
import type { Mesh } from '@babylonjs/core/Meshes/mesh';
import type { PBRMaterial } from '@babylonjs/core/Materials/PBR/pbrMaterial';
import type { BaseTexture } from '@babylonjs/core/Materials/Textures/baseTexture';
export const STARTER_ROCK_SOURCE: Readonly<{id:string;diameter:number;triangles:readonly number[];sha256:readonly string[];atlas:Readonly<{albedo:string;normal:string;orm:string}>;sourcePixelsPerMetre:number}>;
export function validateStarterRockMaterial(material:PBRMaterial,scene:Scene):PBRMaterial;
export function starterRockTextureColorSpace(texture:BaseTexture,channel:'albedo'|'normal'|'orm'):{shaderGamma:boolean;hardwareSRGB:boolean;valid:boolean};
export function createStarterRockMaterial(scene:Scene,textures:{albedo:BaseTexture;normal:BaseTexture;orm:BaseTexture}):PBRMaterial;
export function normalizeStarterRockGeometry(scene:Scene,templates:readonly Mesh[],sourceHashes:readonly string[]):{
 meshes:Mesh[];centre:number[];scale:number;normalizedRadius:number;geometryAttributeLocations:number;instanceMatrixLocations:number;maximumAttributeLocations:number;basePixelsPerMetre:number
};
