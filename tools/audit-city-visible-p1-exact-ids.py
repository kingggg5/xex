"""Read-only exact-ID P1/S07 audit, selected source against guardian city v2."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

P=argparse.ArgumentParser();P.add_argument('--root',required=True,type=Path);P.add_argument('--output',required=True,type=Path)
A=P.parse_args(sys.argv[sys.argv.index('--')+1:]);ROOT=A.root.resolve()
active_path=ROOT/'assets/models/reference-city/r5/active-revision.json';active=json.loads(active_path.read_text())
selected=ROOT/next(r['path'] for n,r in active['files'].items() if n.endswith('.blend'))
v2=ROOT/'assets/models/reference-city/r5/fountain-guardian-review-v2-candidate/reference_city_guardian_review_v2.blend'
paths=[selected,v2,active_path];guards={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
traversal=json.loads((ROOT/active['files']['city-traversal-v1.json']['path']).read_text())
blockers={r['id']:r for r in traversal['blockers']}
lamp_ids=['city lamp stone foot','city lamp iron column','city lamp crystal','city lamp crown']
bench_ids=['plaza bench oak slat'+('' if i==0 else f'.{i:03d}') for i in range(4)]+[
    prefix+suffix for prefix in ['plaza bench stone leg','plaza bench carved arm'] for suffix in ['', '.001']]

def ancestry(ob):
    out=[]
    while ob:out.append(ob.name);ob=ob.parent
    return out

def runtime(p):return [float(p.x),float(p.z),float(176+p.y)]

def material_info(m):
    result={'slot':m.name}
    if m.use_nodes and m.node_tree:
        bsdf=next((n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if bsdf:
            for key in ['Base Color','Metallic','Roughness','Alpha','Emission Color','Emission Strength']:
                socket=bsdf.inputs.get(key)
                if socket:
                    value=socket.default_value
                    result[key]=list(value) if hasattr(value,'__len__') else float(value)
                    result[key+'_linked']=socket.is_linked
    return result

def row(ob):
    result={'id':ob.name,'type':ob.type,'ancestry':ancestry(ob),'collections':[c.name for c in ob.users_collection],
            'origin_runtime':runtime(ob.matrix_world.translation),'collider':blockers.get(ob.name)}
    if ob.type=='MESH':
        points=np.array([runtime(ob.matrix_world@v.co) for v in ob.data.vertices])
        result.update({'bounds_runtime':{'min':points.min(0).tolist(),'max':points.max(0).tolist()},
                       'triangles':sum(len(p.vertices)-2 for p in ob.data.polygons),'materials':[material_info(m) for m in ob.data.materials if m],
                       'world_vertex_signature_1um':hashlib.sha256(json.dumps(sorted(tuple(round(float(v),6) for v in p) for p in points),separators=(',',':')).encode()).hexdigest()})
    return result

revisions=[]
for label,path in [('selected',selected),('guardian-city-v2',v2)]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    objects=list(bpy.context.scene.objects)
    east=[row(o) for o in objects if 'kit_arcane_portal' in ancestry(o)]
    door=[row(o) for o in objects if o.name.startswith(('castle nave stone body','castle portal deep recess','castle violet portal core','castle portal jamb','castle pointed portal'))]
    wizard=[row(o) for o in objects if o.name.startswith(('wizard tower decorative belt','wizard rune ring ','wizard ring rune crystal','anim_wizard_ring','wizard purple lancet'))]
    cluster=[row(bpy.data.objects[name]) for name in lamp_ids+bench_ids]
    revisions.append({'revision':label,'master_path':str(path.relative_to(ROOT)),'sha256':guards[str(path.relative_to(ROOT))],
                      'east_landmark':east,'castle_door':door,'wizard_bands_windows':wizard,'s07_cluster':cluster})

for path in paths:
    if hashlib.sha256(path.read_bytes()).hexdigest()!=guards[str(path.relative_to(ROOT))]:raise RuntimeError('Read-only audit changed an input file.')
current=revisions[-1];door={r['id']:r for r in current['castle_door']};core=door['castle violet portal core'];slab=door['castle portal deep recess'];nave=door['castle nave stone body']
door_metrics={'portal_core_depth_m':core['bounds_runtime']['max'][2]-core['bounds_runtime']['min'][2],
              'recess_slab_depth_m':slab['bounds_runtime']['max'][2]-slab['bounds_runtime']['min'][2],
              'slab_to_nave_front_gap_m':nave['bounds_runtime']['min'][2]-slab['bounds_runtime']['max'][2],
              'diagnosis':'The named deep recess is a thin slab in front of the solid nave, not a carved doorway.'}
positions={'existing_lamp':[24*math.cos(math.pi/12),0,176+24*math.sin(math.pi/12)],'existing_bench':[30,0,176],
           'proposed_lamp':[28,0,171],'proposed_bench':[30,0,176]}
direction=np.array([40.,10.]);positions['lamp_distance_to_proposed_portal_axis_m']=abs(40*(positions['existing_lamp'][2]-176)-10*positions['existing_lamp'][0])/np.linalg.norm(direction)
positions['moved_lamp_distance_to_proposed_portal_axis_m']=abs(40*(-5)-10*28)/np.linalg.norm(direction)
arch_groups={}
for item in current['castle_door']:
    if item['id'].startswith('castle pointed portal carved arch stone'):
        key=(item['world_vertex_signature_1um'],tuple(m['slot'] for m in item['materials']),item['triangles'])
        arch_groups.setdefault(key,[]).append(item['id'])
duplicate_arch_pairs=[ids for ids in arch_groups.values() if len(ids)>1]
old_by_id={item['id']:item for category in ['east_landmark','castle_door','wizard_bands_windows','s07_cluster'] for item in revisions[0][category]}
changed_p1_ids=[]
for category in ['east_landmark','castle_door','wizard_bands_windows','s07_cluster']:
    for item in current[category]:
        previous=old_by_id.get(item['id'])
        if previous and any(item.get(key)!=previous.get(key) for key in ['bounds_runtime','origin_runtime','triangles','materials','world_vertex_signature_1um']):changed_p1_ids.append(item['id'])

plans={
 'east_landmark':{
   'identity':'Source layout/kits identify this as arcane_portal, not a fountain; role must not silently change.',
   'REWORK':['portal vertical light column','portal glass disc'],
   'KEEP':['portal eight-sided dais','portal blue stone inlay','portal luminous rune ring 1','portal luminous rune ring 2','portal luminous rune ring 3','fx_portal_beam','anim_portal_disc'],
   'engine_plan':['Keep the physical dais/rune/pylon assembly. Replace the solid emissive cone with native ParticleSystem or a NodeMaterial-owned effect anchored at fx_portal_beam, only by the authorized effect owner.',
                  'The apparent water sheet is portal glass disc with magic_blue, not a water material. Investigate intended portal surface rather than deleting by cyan color.',
                  'If the human explicitly wants a fountain here, first rework the existing dais into a proper basin with annular lip, inner wall and floor. Do not add water particles without a basin/outlet contract.'],
   'conditional_fountain_contract':{'status':'INTENT_REQUIRED_NOT_ACTIVATED','owner':'Root NodeMaterial/water worker',
      'origin_world':[40,0,186],'physical_basin_required':True,'mouth_count':'Use only geometry-backed existing/reworked outlet identities; no invented emitter origins.',
      'system':'Native Babylon ParticleSystem, point/narrow box emitter; world emitter and normalized direction supplied by source outlet.',
      'budget_proposal':{'Low_capacity_total':192,'High_capacity_total':512,'distance_pause_m':55},
      'parameters':['emitter','minEmitBox','maxEmitBox','direction1','direction2','emitRate','minEmitPower','maxEmitPower','minLifeTime','maxLifeTime','gravity'],
      'life_rule':'Set life to measured flight-to-basin time; gravity and impact position must follow real outlet/target heights. Avoid extra reflection passes.'}},
 'castle_door':{
   'exact_ids':['castle nave stone body','castle portal deep recess','castle violet portal core','castle portal jamb','castle portal jamb.001'],
   'REWORK':['castle portal deep recess','castle violet portal core'],'KEEP':['castle portal jamb','castle portal jamb.001']+[r['id'] for r in current['castle_door'] if r['id'].startswith('castle pointed portal carved arch stone')],
   'INVESTIGATE_duplicate_pairs':duplicate_arch_pairs,
   'engine_plan':['Create a versioned copy of castle nave stone body and its associated doorway assembly. Use a bounded Blender Boolean DIFFERENCE with solver EXACT for a real shallow pointed-arch recess; do not cut the whole merged city material bucket.',
                  'Reuse existing jamb/arch trim. Place a physically thick recessed surface or existing door design at the back of the recess rather than a0.12m emissive rectangle on the front.',
                  'Portal-versus-door behavior belongs to the human design owner. NodeMaterial owner may confine glow to a recessed inlay, not change all magic_purple materials.',
                  'Regenerate/check the exact nave blocker in a candidate if geometry/collision actually opens; a decorative recess alone must not imply a traversable new interior.']},
 'wizard_bands':{
   'KEEP':['wizard rune ring 1','wizard rune ring 2','anim_wizard_ring_1','anim_wizard_ring_2'],
   'REWORK':[r['id'] for r in current['wizard_bands_windows'] if r['id'].startswith('wizard ring rune crystal ')],
   'INVESTIGATE_windows':[r['id'] for r in current['wizard_bands_windows'] if r['id'].startswith('wizard purple lancet')],
   'diagnosis':'Structural ring shells use metal_gold; magenta comes from separate magic_purple rune crystal/window parts. Do not delete the physical ring or globally recolor all purple.',
   'engine_plan':['Keep real annular metal ring thickness, current open inner walls and animation hook identities.',
                  'Replace projecting rune cones with shallow recessed rune inlays/socket geometry using native bpy/citykit primitives or exact local booleans, preserving16 source rune identities per ring.',
                  'NodeMaterial/material owner may soften only the approved rune inlay surface budget after geometry review; no forge map is selected by this audit.']},
 's07_one_cluster':{
   'purpose':'Existing portal-west pause/viewpoint cluster, pending the human-owned landmark intent; no new props or gameplay systems.',
   'KEEP_position_and_existing_asset_identity':bench_ids,'MOVE':lamp_ids,'REWORK':bench_ids,
   'positions':positions,
   'collision_relation':'All eight bench pieces are current street_object blockers. Lamp parts have no blockers in the selected contract. Any move/rework must carry all assembly meshes/shadows and rebuild matching collider footprint/vertical range.',
   'plan':['Keep the bench centre at30,176 and move the complete four-part lamp from23.182,182.212 to28,171, off the proposed portal approach axis.',
           'Rework the four vertically stacked oak strips into a usable seat/back using the same existing IDs; target seat height0.45–0.50m, two real legs and supported arms. This is a proposal, not a source change.',
           'Validate a3m clear walk corridor around the existing portal dais and fountain plinth with the shared0.35m capsule; the line used here is proposed, not an already declared route.',
           'Leave the other ring placements untouched pending cluster-by-cluster purpose and collision review; no blanket deletion.']}}

report={'schema':'xexoria.visible-p1-exact-object-audit/1','read_only':True,'revisions':revisions,'door_metrics':door_metrics,'plans':plans,
 'selected_to_v2_p1_geometry_material_changes':changed_p1_ids,'coincident_castle_arch_pairs':duplicate_arch_pairs,
 'source_definitions':['assets/blender/city_r5/layout.json:128-136','assets/blender/city_r5/kits/landmarks.py:252-274','assets/blender/city_r5/kits/castle.py:158-164','assets/blender/city_r5/kits/landmarks.py:133-142','assets/blender/city_r5/kits/vegetation.py:157-177'],
 'documentation':['https://docs.blender.org/api/current/bpy.types.BooleanModifier.html','https://doc.babylonjs.com/features/featuresDeepDive/particles/particle_system/particles_tuning'],
 'guards_unchanged':True,'forge_files_used':False,'renders_performed':False,'root_browser_used':False,
 'limits':['No solo/native object-ID capture for these P1s; source identity does not prove the live representation is selected.','Plans require a separate authorized geometry/NodeMaterial implementation; no material/image/global source edits here.','Suggested cluster route/particle budgets are proposals, not measured mobile/network capacity.']}
A.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print('VISIBLE_P1_IDS',json.dumps({'east_root':'kit_arcane_portal','east_rework':plans['east_landmark']['REWORK'],'door_metrics':door_metrics,'wizard_shell_materials':{r['id']:[m['slot'] for m in r.get('materials',[])] for r in current['wizard_bands_windows'] if r['id'] in ['wizard rune ring 1','wizard rune ring 2']},'cluster':positions,'read_only':True}))
