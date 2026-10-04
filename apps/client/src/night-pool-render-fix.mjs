/** StandardMaterial adds emissiveTexture RGB to emissiveColor. The painted
 * grayscale pool belongs in opacity so its black edge contributes zero light. */
export function repairStandardLightPool(material) {
 if(!material || material.name!=='look-v2-pool-mat' || material.emissiveTexture?.name!=='look-v2-pool-falloff')return false;
 const falloff=material.emissiveTexture;
 falloff.getAlphaFromRGB=true;
 material.opacityTexture=falloff;
 material.emissiveTexture=null;
 material.useEmissiveAsIllumination=true;
 return true;
}
