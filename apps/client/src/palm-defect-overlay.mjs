/** Exact existing-root candidate; source datasets and their planned colliders are never mutated. */
export function applyPalmDefectOverlay(entries, overlay) {
 if(!Array.isArray(entries)||!overlay||overlay.schema!=='xexoria.palm-defect-overlay/1'||!Array.isArray(overlay.patches)||overlay.patches.length!==10||!Number.isFinite(overlay.targetHeightM)||overlay.targetHeightM<6||overlay.targetHeightM>9||!Number.isFinite(overlay.groundingOffsetM)||overlay.groundingOffsetM<0||overlay.groundingOffsetM>.05)throw new Error('Invalid D4 palm contract');
 if(overlay.patches.some(p=>!p||typeof p!=='object'))throw new Error('Invalid D4 root patch');
 const patches=new Map(overlay.patches.map(p=>[p.id,p]));
 if(patches.size!==10)throw new Error('Duplicate D4 root');
 for(const p of patches.values())if(!/^bp_PL1_00[0-9]$/.test(p.id)||Object.keys(p).some(k=>!['id','x','z','yaw','pitch'].includes(k))||![p.x,p.z,p.yaw,p.pitch].every(Number.isFinite)||p.x < -42||p.x > -36||p.z < -88||p.z > -72||Math.abs(p.pitch)>Math.PI/36+1e-9)throw new Error('D4 crest/root mismatch');
 const roots=entries.filter(e=>patches.has(e.id));
 if(roots.length!==10||new Set(roots.map(e=>e.id)).size!==10||entries.filter(e=>e.blueprint_id==='PL1').length!==10||roots.some(e=>e.blueprint_id!=='PL1'||e.asset_id!=='blueprint_cc0_palm'||!Number.isFinite(e.y)||!Number.isFinite(e.visual_base_y??0)||e.visual_absolute_base_y!==undefined||e.surface_y!==undefined))throw new Error('Existing ten PL1 palms required');
 return entries.map(entry=>{const patch=patches.get(entry.id);return patch?{...entry,x:patch.x,z:patch.z,yaw:patch.yaw,pitch:patch.pitch,target_height:overlay.targetHeightM,visual_base_y:(entry.visual_base_y??0)+overlay.groundingOffsetM,cell:`${Math.floor(patch.x/64)},${Math.floor(patch.z/64)}`} :entry;});
}
export function distanceFromSegmentXZ(point, start, end) {
 if(![point,start,end].every(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)))throw new TypeError('Finite XZ points required');
 const dx=end[0]-start[0],dz=end[1]-start[1],d=dx*dx+dz*dz;
 const t=d?Math.max(0,Math.min(1,((point[0]-start[0])*dx+(point[1]-start[1])*dz)/d)):0;
 return Math.hypot(point[0]-start[0]-t*dx,point[1]-start[1]-t*dz);
}
