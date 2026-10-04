import { InputBlock } from '@babylonjs/core/Materials/Node/Blocks/Input/inputBlock';
import { NodeMaterialSystemValues } from '@babylonjs/core/Materials/Node/Enums/nodeMaterialSystemValues';
import type { NodeMaterialBuildState } from '@babylonjs/core/Materials/Node/nodeMaterialBuildState';
import { ShaderLanguage } from '@babylonjs/core/Materials/shaderLanguage';

/** Graph-local Babylon 9.27 CSM compatibility. WGSL shadowsVertex references
 * uniforms.view, while ordinary InputBlock names its system uniform u_view.
 * InputBlock still owns per-bind scene-matrix updates and GLSL keeps u_view;
 * changing GLSL to view would shadow the PBR block's local mat4 view alias. */
export class CityWaterViewInput extends InputBlock {
	constructor() { super('view'); this.setAsSystemValue(NodeMaterialSystemValues.View); }
	protected override _buildBlock(state: NodeMaterialBuildState): void {
		if (state.shaderLanguage === ShaderLanguage.WGSL) this.associatedVariableName = 'view';
		super._buildBlock(state);
	}
}
