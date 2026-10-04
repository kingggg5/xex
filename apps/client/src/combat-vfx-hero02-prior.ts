import type {AssetContainer} from '@babylonjs/core/assetContainer';
import {TransformNode} from '@babylonjs/core/Meshes/transformNode';
import type {Mesh} from '@babylonjs/core/Meshes/mesh';
import type {VfxLayer} from './combat-vfx-kit';
import type {SkillFactory} from './combat-vfx-skills';

/** Reuse the editable prior-art node/animation structure for a marked review preview, never gameplay. */
export function priorHero02Factory(kind:'lance'|'aegis'|'orrery'):SkillFactory{return (ctx,origin)=>{
 const container=ctx.kit.hero02Prior?.[kind];if(!container)throw new Error(`ITERATE: missing hero02 ${kind} source container`);
 const copy=container.instantiateModelsToScene(name=>`h02-source-${kind}-${name}`,true,{doNotInstantiate:true});
 const root=new TransformNode(`h02-source-${kind}-preview`,ctx.scene);for(const node of copy.rootNodes)node.parent=root;
 root.position.copyFrom(origin);
 const meshes=root.getChildMeshes() as Mesh[];
 const groups=copy.animationGroups;for(const group of groups){group.start(false);group.pause();}
 const roles=new Map<string,Mesh[]>();
 const roleOf=(name:string)=>/Trail|Slipstream|Ribbon|Prismatic/i.test(name)?'secondary':/Impact|Nova_Ripple|Orrery_Nova|Dust|Release_Star/i.test(name)?'after':/Charge|Armillary|Crown|Constellation/i.test(name)?'anticipation':/Astral_Circle|Sigil|Telegraph|Shield_Ripple|Inner_Halo|Contact_Ripple/i.test(name)?'ground':'core';
 for(const mesh of meshes){mesh.isPickable=false;mesh.receiveShadows=false;const role=roleOf(mesh.name);const list=roles.get(role)??[];list.push(mesh);roles.set(role,list);}
 const muted=new Set<string>();
 const layers:VfxLayer[]=[...roles].map(([role,parts])=>({name:`prior-${role}`,drawCalls:()=>muted.has(role)?0:parts.filter(mesh=>mesh.isEnabled()&&mesh.isVisible&&Math.max(mesh.scaling.x,mesh.scaling.y,mesh.scaling.z)>.005).reduce((sum,mesh)=>sum+Math.max(1,mesh.subMeshes?.length??1),0),particles:()=>0,setVisible(value){if(value)muted.delete(role);else muted.add(role);for(const mesh of parts)mesh.isVisible=value;},dispose(){}}));
 const duration={lance:2,aegis:6.5,orrery:4.8}[kind],sourceDuration={lance:1.65,aegis:1.85,orrery:3.25}[kind];
 root.setEnabled(false);
 return {id:`hero02_prior_${kind}`,duration,contract:`DRAFT VISUAL ONLY · prior ${kind} · ITERATE missing kit/clip authoring`,layers:()=>layers,
 reset(at,facing){root.position.copyFrom(at);root.rotation.y=facing;root.setEnabled(true);muted.clear();for(const mesh of meshes)mesh.isVisible=true;},
 update(t){for(const group of groups){const fps=group.targetedAnimations[0]?.animation.framePerSecond??60;group.goToFrame(group.from+Math.min(sourceDuration,t/duration*sourceDuration)*fps);}for(const [role,parts]of roles)for(const mesh of parts)mesh.isVisible=!muted.has(role);},
 stop(){root.setEnabled(false);},
 dispose(){groups.forEach(group=>group.dispose());copy.dispose();root.dispose();},
 };
};}
export type Hero02PriorContainers=Readonly<Record<'lance'|'aegis'|'orrery',AssetContainer>>;
