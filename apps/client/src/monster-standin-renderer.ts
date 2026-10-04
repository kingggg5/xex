import type {Scene} from '@babylonjs/core/scene';
import {SceneLoader} from '@babylonjs/core/Loading/sceneLoader';
import type {AssetContainer} from '@babylonjs/core/assetContainer';
import {TransformNode} from '@babylonjs/core/Meshes/transformNode';
import {MultiMaterial} from '@babylonjs/core/Materials/multiMaterial';
import type {Material} from '@babylonjs/core/Materials/material';
import {VertexBuffer} from '@babylonjs/core/Buffers/buffer';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import {sampleMonsterStandinPose,MONSTER_STANDIN_SPECIES,type MonsterStandinPhase} from './monster-standin-motion-policy.mjs';
import {createMonsterGroundContact,MAX_MONSTER_CONTACT_VERTICES,type MonsterGroundContactProfile} from './monster-ground-contact.mjs';
import puddlekinUrl from './assets/models/monster-standins-r01/puddlekin.glb?url';
import mosslingUrl from './assets/models/monster-standins-r01/mossling.glb?url';
import boarUrl from './assets/models/monster-standins-r01/thistle_boar.glb?url';
import wispUrl from './assets/models/monster-standins-r01/glade_wisp.glb?url';

const URLS:Readonly<Record<number,string>>={1:puddlekinUrl,2:mosslingUrl,3:boarUrl,4:wispUrl};
export interface MonsterStandinView {
	root:TransformNode;visual:TransformNode;body:TransformNode;
	/** Compatibility convenience only; feedback must receive every owned material. */
	material:Material;materials:readonly Material[];
	setPhase:(phase:MonsterStandinPhase)=>void;
	/** Called by existing scene animation loop; never creates an independent clock. */
	tick:(elapsedMs:number,reduceMotion?:boolean)=>void;
	dispose:()=>void;
}

/** Await once before createMonsterViewRegistry.synchronize. Creation is then synchronous. */
export async function preloadMonsterStandins(scene:Scene) {
	const containers=new Map<number,AssetContainer>();
	try {
		// Four bounded loads; templates stay out of scene, do not cast shadows or create observers.
		for(const [kind,url] of Object.entries(URLS))containers.set(Number(kind),await SceneLoader.LoadAssetContainerAsync('',url,scene));
		return createMonsterStandinFactory(scene,containers);
	} catch(error) {for(const container of containers.values())container.dispose();throw error;}
}

/** Public injection seam permits CPU NullEngine lifecycle verification without network or GPU. */
export function createMonsterStandinFactory(scene:Scene,containers:ReadonlyMap<number,AssetContainer>) {
	const live=new Set<MonsterStandinView>(),contactProfiles=new Map<number,MonsterGroundContactProfile>();let disposed=false;
	function create(kind:number,id:number):MonsterStandinView {
		if(disposed)throw new Error('Monster stand-in factory disposed');
		const container=containers.get(kind);
		if(!container||!MONSTER_STANDIN_SPECIES[kind])throw new RangeError(`No preloaded CC0 interim creature for kind ${kind}`);
		if(!Number.isSafeInteger(id)||id<=0)throw new TypeError('Invalid monster identity');
		const name=`monster-${id}`;
		// Forced mesh clones share geometry/texture resources but own materials for flash/dissolve.
		const entries=container.instantiateModelsToScene(source=>`${name}-${source}`,true,{doNotInstantiate:true});
		const root=new TransformNode(name,scene),visual=new TransformNode(`${name}-visual`,scene),body=new TransformNode(`${name}-body-pose`,scene);
		visual.parent=root;body.parent=visual;
		for(const node of entries.rootNodes)(node as TransformNode).parent=body;
		const owned=new Set<Material>(),ownedMultiMaterials=new Set<MultiMaterial>();
		for(const mesh of body.getChildMeshes()) {
			mesh.metadata={...(mesh.metadata??{}),monsterId:id,kind};
			if(mesh.material instanceof MultiMaterial){ownedMultiMaterials.add(mesh.material);for(const material of mesh.material.subMaterials)if(material)owned.add(material);}
			else if(mesh.material)owned.add(mesh.material);
		}
		const materials=[...owned];
		if(!materials.length){entries.dispose();root.dispose();throw new Error(`CC0 creature kind ${kind} contains no material`);}
		for(const group of entries.animationGroups)group.stop();
		let contact=contactProfiles.get(kind);
		if(!contact)try {
			// Preserve importer handedness and every authored ancestor transform. Body is
			// still at identity pose here; later roots may carry gameplay position/facing.
			const inverseBody=body.computeWorldMatrix(true).clone().invert(),positions:number[]=[];
			const vertex=new Vector3(),point=new Vector3();
			for(const mesh of body.getChildMeshes()){
				if(mesh.getTotalVertices()===0)continue;
				if(mesh.skeleton)throw new Error(`Ground contact requires a static stand-in for kind ${kind}`);
				const source=mesh.getVerticesData(VertexBuffer.PositionKind);
				if(!source||source.length!==mesh.getTotalVertices()*3)throw new Error(`Ground contact CPU positions unavailable for ${mesh.name}`);
				if(positions.length/3+source.length/3>MAX_MONSTER_CONTACT_VERTICES)throw new Error(`Ground contact vertex budget exceeded for kind ${kind}`);
				const toBody=mesh.computeWorldMatrix(true).multiply(inverseBody);
				for(let i=0;i<source.length;i+=3){vertex.set(source[i],source[i+1],source[i+2]);Vector3.TransformCoordinatesToRef(vertex,toBody,point);positions.push(point.x,point.y,point.z);}
			}
			contact=createMonsterGroundContact(kind,positions);contactProfiles.set(kind,contact);
		} catch(error) {
			entries.dispose();root.dispose(false,false);for(const material of materials)material.dispose(false,false);for(const material of ownedMultiMaterials)material.dispose(false,false);throw error;
		}
		const support=contact;
		let phase:MonsterStandinPhase='idle',viewDisposed=false;
		const view:MonsterStandinView={root,visual,body,material:materials[0],materials,
			setPhase(next){sampleMonsterStandinPose(kind,next,0,id);phase=next;},
			tick(elapsedMs,reduceMotion=false){if(viewDisposed)return;const pose=sampleMonsterStandinPose(kind,phase,elapsedMs,id,reduceMotion);body.scaling.set(pose.scale[0],pose.scale[1],pose.scale[2]);body.position.y=pose.y+support.phases[phase].supportOffset;body.rotation.set(pose.pitch,0,pose.roll);},
			dispose(){if(viewDisposed)return;viewDisposed=true;live.delete(view);entries.dispose();root.dispose(false,false);for(const material of materials)material.dispose(false,false);for(const material of ownedMultiMaterials)material.dispose(false,false);},
		};
		view.tick(0);live.add(view);return view;
	}
	return {create,dispose(){if(disposed)return;disposed=true;for(const view of [...live])view.dispose();for(const container of containers.values())container.dispose();contactProfiles.clear();},get size(){return live.size;},get contactSpeciesCount(){return contactProfiles.size;}};
}
