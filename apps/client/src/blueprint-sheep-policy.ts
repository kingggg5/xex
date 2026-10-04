import {BoundingInfo} from '@babylonjs/core/Culling/boundingInfo';
import {Frustum} from '@babylonjs/core/Maths/math.frustum';
import {Vector3} from '@babylonjs/core/Maths/math.vector';
import type {AnimationGroup} from '@babylonjs/core/Animations/animationGroup';
import type {TransformNode} from '@babylonjs/core/Meshes/transformNode';
import type {Scene} from '@babylonjs/core/scene';

export const SHEEP_DISTANCE_LIMIT_M=45;
// Idle head/ear motion stays within this envelope (checked against the original clip).
export const SHEEP_IDLE_BOUNDS_MARGIN_M=.15;

export function createSheepActor(root:TransformNode,idle:AnimationGroup,index:number) {
 const {min,max}=root.getHierarchyBoundingVectors(true);
 const margin=new Vector3(SHEEP_IDLE_BOUNDS_MARGIN_M,SHEEP_IDLE_BOUNDS_MARGIN_M,SHEEP_IDLE_BOUNDS_MARGIN_M);
 const bounds=new BoundingInfo(min.subtract(margin),max.add(margin));
 return {root,idle,index,bounds,enabled:root.isEnabled(),
  fps:idle.targetedAnimations[0]?.animation.framePerSecond??60,length:idle.to-idle.from};
}

/** Six cached actor envelopes; no scene scans, new clocks, or detached skeletons. */
export function createSheepVisibilityPolicy(scene:Scene,actors:ReturnType<typeof createSheepActor>[]) {
 const planes=Frustum.GetPlanes(scene.getTransformMatrix());
 const stats={distanceLimitM:SHEEP_DISTANCE_LIMIT_M,visibleCount:0,animatedCount:0,
  distanceCulledCount:0,frustumCulledCount:0,animationFrozenCount:actors.length,poseUpdates:0};
 return {
  stats,
  update(worldMs:number|undefined) {
   const camera=scene.activeCamera;
   stats.visibleCount=0;stats.animatedCount=0;stats.distanceCulledCount=0;stats.frustumCulledCount=0;
   if(camera) {
    // getTransformationMatrix uses cached view/projection matrices in classic Babylon.
    camera.getViewMatrix();camera.getProjectionMatrix();
    Frustum.GetPlanesToRef(camera.getTransformationMatrix(),planes);
   }
   for(const actor of actors) {
    // Camera world matrices use floats; keep the exact 45 m boundary inclusive.
    const inDistance=!!camera&&Vector3.DistanceSquared(camera.globalPosition,actor.bounds.boundingSphere.centerWorld)<=SHEEP_DISTANCE_LIMIT_M**2+1e-4;
    const inFrustum=inDistance&&actor.bounds.isInFrustum(planes);
    if(actor.enabled!==inFrustum){actor.root.setEnabled(inFrustum);actor.enabled=inFrustum;}
    if(!inDistance){stats.distanceCulledCount++;continue;}
    if(!inFrustum){stats.frustumCulledCount++;continue;}
    stats.visibleCount++;
    if(Number.isFinite(worldMs)&&actor.length>0) {
     actor.idle.goToFrame(actor.idle.from+(((worldMs as number)/1000*actor.fps+actor.index*37)%actor.length));
     stats.animatedCount++;stats.poseUpdates++;
    }
   }
   stats.animationFrozenCount=actors.length-stats.animatedCount;
  }
 };
}
