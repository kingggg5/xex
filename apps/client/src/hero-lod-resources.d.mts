import type {Scene} from '@babylonjs/core/scene';
import type {AbstractMesh} from '@babylonjs/core/Meshes/abstractMesh';
import type {AnimationGroup} from '@babylonjs/core/Animations/animationGroup';
export interface HeroResourceAsset {meshes:readonly AbstractMesh[];animationGroups:readonly AnimationGroup[]}
export interface HeroLodResourceReceipt {
 schema:'xexoria.hero-lod-resources/1';status:'CANDIDATE_C1';scope:string;before:{baseTextures:number;uniqueInternalTextures:number};after:{baseTextures:number;uniqueInternalTextures:number};
 texturesDisposed:number;lowerGroupsDisposed:number;bindingsReplaced:number;shared:readonly unknown[];skipped:Readonly<Record<string,number>>;hardwareMemoryMeasured:false;
}
export function optimizeHeroLodResources(scene:Scene,base:HeroResourceAsset,levels:readonly HeroResourceAsset[]):Promise<HeroLodResourceReceipt>;
