/** Atlas identity is part of the UV contract, even when material families match. */
export function dressingMaterialIdentity(asset) {
	const family=asset?.family, atlas=asset?.textures?.atlas;
	if(typeof family!=='string'||!family.length)throw new TypeError('Dressing material family required');
	if((typeof atlas!=='string'||!atlas.length)&&family!=='cc0-mushroom')throw new TypeError(`Dressing atlas required for ${family}`);
	return JSON.stringify([family,atlas??null]);
}

/** Babylon's default alpha roughness takes precedence over ORM green. */
export function configureDressingOrm(material) {
	material.useRoughnessFromMetallicTextureAlpha=false;
	material.useRoughnessFromMetallicTextureGreen=true;
	material.useAmbientOcclusionFromMetallicTextureRed=true;
	material.useMetallnessFromMetallicTextureBlue=true;
	return material;
}
