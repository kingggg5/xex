export function dressingMaterialIdentity(asset:{family:string;textures?:{atlas?:string}}):string;
export function configureDressingOrm<T extends {
 useRoughnessFromMetallicTextureAlpha:boolean;useRoughnessFromMetallicTextureGreen:boolean;
 useAmbientOcclusionFromMetallicTextureRed:boolean;useMetallnessFromMetallicTextureBlue:boolean;
}>(material:T):T;
