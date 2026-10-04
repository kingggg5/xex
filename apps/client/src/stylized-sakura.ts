import {MaterialPluginBase} from '@babylonjs/core/Materials/materialPluginBase';
import {StandardMaterial} from '@babylonjs/core/Materials/standardMaterial';
import {ShaderLanguage} from '@babylonjs/core/Materials/shaderLanguage';
import {Mesh} from '@babylonjs/core/Meshes/mesh';
import type {Scene} from '@babylonjs/core/scene';
import type {NatureClock} from './nature-motion';
import {addWind} from './nature-motion';
import {createImpostorField,createTreeLodField,type ImpostorAtlasManifest,type TreeLodSpecies,type TreeLodPlacement} from './impostors';
import type {TreeLodPlan} from './impostor-math.mjs';
import {sakuraPlacement,sakuraShaderCode} from './sakura-look-policy.mjs';

class SakuraBlossomPlugin extends MaterialPluginBase {
	constructor(material:StandardMaterial,impostor=false){super(material,'SakuraBlossom',260,{SAKURA_BLOSSOM:true,SAKURA_IMPOSTOR:impostor},true,false);this._enable(true);}
	isCompatible(language:ShaderLanguage){return language===ShaderLanguage.GLSL||language===ShaderLanguage.WGSL;}
	getCustomCode(stage:string,language=ShaderLanguage.GLSL){return stage==='fragment'?{CUSTOM_FRAGMENT_BEFORE_LIGHTS:sakuraShaderCode(language===ShaderLanguage.WGSL)}:null;}
}

/** Uses authored CC0 kit branches/cards, shared textures and the existing LOD/wind engines. */
export function createStyledSakura(scene:Scene,options:{species:Record<string,TreeLodSpecies>;manifest:ImpostorAtlasManifest;
	resolveUrl:(file:string)=>string;clock:NatureClock;plan:TreeLodPlan;onBatch:(mesh:Mesh)=>void}){
	const materials=new Map<StandardMaterial,StandardMaterial>(),templates:Mesh[]=[],species:Record<string,TreeLodSpecies>={};
	const cards=createImpostorField(scene,options.manifest,options.resolveUrl,{ktx2:true});
	for(const mesh of cards.meshes)if(mesh.material instanceof StandardMaterial){new SakuraBlossomPlugin(mesh.material,true);mesh.metadata={...mesh.metadata,glow:false,sakura:true};}
	try{
		for(const id of ['qn_broadleaf_m','qn_broadleaf_l']){
			const original=options.species[id];if(!original)throw Error(`Sakura kit species missing: ${id}`);
			const lods=original.lods.map((parts,lod)=>parts.map((part,index)=>{
				const mesh=part.clone(`sakura-template-${id}-${lod}-${index}`,null,true);if(!mesh)throw Error('Sakura template clone failed');
				templates.push(mesh);mesh.isVisible=false;mesh.setEnabled(false);
				if(part.material instanceof StandardMaterial&&!part.material.name.endsWith('-bark')){
					let material=materials.get(part.material);
					if(!material){
						const source=part.material;material=new StandardMaterial('env-sakura-foliage',scene);
						// Share the real texture objects; never dispose these through the variant.
						material.diffuseTexture=source.diffuseTexture;material.bumpTexture=source.bumpTexture;
						material.diffuseColor.copyFrom(source.diffuseColor);material.specularColor.copyFrom(source.specularColor);
						material.emissiveColor.copyFrom(source.emissiveColor);material.linkEmissiveWithDiffuse=source.linkEmissiveWithDiffuse;
						material.backFaceCulling=source.backFaceCulling;material.twoSidedLighting=source.twoSidedLighting;
						material.transparencyMode=source.transparencyMode;material.alphaCutOff=source.alphaCutOff;
						material.useAlphaFromDiffuseTexture=source.useAlphaFromDiffuseTexture;
						material.invertNormalMapX=source.invertNormalMapX;material.invertNormalMapY=source.invertNormalMapY;
						material.metadata={glow:false,sakura:true};
						addWind(material,scene,options.clock,.2,0,0,{weights:'uv2',rigidBelow:1,fadeIn:1});
						new SakuraBlossomPlugin(material);materials.set(source,material);
					}
					mesh.material=material;
				}
				return mesh;
			})) as unknown as TreeLodSpecies['lods'];
			species['sakura-'+id]={...original,lods};
		}
		const field=createTreeLodField(scene,species,{name:'sunmeadow-sakura',plan:options.plan,field:cards,onBatch:options.onBatch});
		let disposed=false;
		const dispose=()=>{if(disposed)return;disposed=true;field.dispose();cards.dispose();for(const mesh of templates)mesh.dispose(false,false);for(const material of materials.values())material.dispose(false,false);};
		scene.onDisposeObservable.addOnce(dispose);
		return {add:(placements:readonly TreeLodPlacement[])=>field.add(placements.map(sakuraPlacement)),setPlan:(plan:TreeLodPlan)=>field.setPlan(plan),stats:()=>field.stats(),list:()=>field.list(),dispose};
	}catch(error){cards.dispose();for(const mesh of templates)mesh.dispose(false,false);for(const material of materials.values())material.dispose(false,false);throw error;}
}
