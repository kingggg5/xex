import {Vector3} from '@babylonjs/core/Maths/math.vector';
import type {TransformNode} from '@babylonjs/core/Meshes/transformNode';
const allowed=new Set(['fx_base','fx_tip','fx_head','fx_nock']);
/** Weapon subtree only: a rig anchor called fx_head elsewhere in the scene is never a match. */
export function resolveWeaponFxMarkers(weapon:TransformNode,required:readonly string[]=['fx_base','fx_tip']){
 if(weapon.isDisposed())throw new Error('Weapon marker owner is disposed');
 if(required.length>4||new Set(required).size!==required.length||required.some(name=>!allowed.has(name)))throw new Error('Invalid weapon marker contract');
 const result=new Map<string,TransformNode>();
 for(const name of required){const matches=weapon.getDescendants(false).filter(node=>node.name===name&&!node.isDisposed());if(matches.length!==1)throw new Error(`Weapon marker ${name}: expected one, found ${matches.length}`);
  const marker=matches[0] as TransformNode;let owner=marker.parent;while(owner&&owner!==weapon)owner=owner.parent;if(owner!==weapon||typeof marker.computeWorldMatrix!=='function')throw new Error(`Wrong-owner weapon marker ${name}`);result.set(name,marker);
 }
 return {names:Object.freeze([...result.keys()]),position(name:string){const marker=result.get(name);if(!marker||marker.isDisposed())throw new Error(`Missing live weapon marker ${name}`);marker.computeWorldMatrix(true);const point=Vector3.TransformCoordinates(Vector3.Zero(),marker.getWorldMatrix());if(![point.x,point.y,point.z].every(Number.isFinite))throw new Error(`Invalid marker world position ${name}`);return {x:point.x,y:point.y,z:point.z};}};
}
