import type{AssetContainer}from'@babylonjs/core/assetContainer';
import type{PBRMaterial}from'@babylonjs/core/Materials/PBR/pbrMaterial';
import type{Texture}from'@babylonjs/core/Materials/Textures/texture';
import type{Mesh}from'@babylonjs/core/Meshes/mesh';
import type{Scene}from'@babylonjs/core/scene';
export function createOwnedWaterFloorMaterial(name:string,scene:Scene,owned:PBRMaterial[]):PBRMaterial;
export function adoptWaterBankGround(scene:Scene,bank:PBRMaterial,borrowed:Set<Texture>):PBRMaterial;
export function projectWaterBankUV(mesh:Mesh):void;
export function releaseWaterFloorAssets(support:AssetContainer|null|undefined,materials:PBRMaterial[],textures:Texture[],borrowed:Set<Texture>):void;
