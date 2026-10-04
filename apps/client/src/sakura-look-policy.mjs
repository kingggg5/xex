/** Restyle existing kit trees; preserve root, scale, geometry and collider contract. */
export const SAKURA_TREE_IDS=Object.freeze(['tree_spot_0','tree_spot_1']);
export const SAKURA_PALETTE=Object.freeze({shadow:[.52,.20,.32],petal:[.96,.61,.75]});
export function isSakuraPlacement(placement){return SAKURA_TREE_IDS.includes(placement.id);}
export function sakuraPlacement(placement){
	if(!isSakuraPlacement(placement)||!placement.species.startsWith('qn_broadleaf_'))throw new Error('Sakura requires an existing selected broadleaf kit tree');
	return {...placement,species:'sakura-'+placement.species};
}
export function sakuraShaderCode(wgsl=false){
	const vec=wgsl?'vec3f':'vec3',vec4=wgsl?'vec4f':'vec4';
	const n=wgsl?'let sakuraLuma =':'float sakuraLuma =';
	const shadow=SAKURA_PALETTE.shadow.join(', '),petal=SAKURA_PALETTE.petal.join(', ');
	const pink=wgsl?'let sakuraPink =':'vec3 sakuraPink =';
	const mask=wgsl?'let sakuraLeafMask =':'float sakuraLeafMask =';
	return `${n} clamp(dot(baseColor.rgb, ${vec}(0.2126, 0.7152, 0.0722)), 0.0, 1.0);\n${pink} mix(${vec}(${shadow}), ${vec}(${petal}), smoothstep(0.06, 0.85, sakuraLuma));\n#ifdef SAKURA_IMPOSTOR\n${mask} smoothstep(0.045, 0.20, (baseColor.g - max(baseColor.r, baseColor.b)) / max(sakuraLuma, 0.03));\nbaseColor = ${vec4}(mix(baseColor.rgb, sakuraPink, sakuraLeafMask), baseColor.a);\n#else\nbaseColor = ${vec4}(sakuraPink, baseColor.a);\n#endif`;
}
