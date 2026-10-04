"""UNEXECUTED H05 canonical projection recipe. No bpy import or work at module load.

This supplies controlled authoring/view helpers, not a toy generated hero. A licensed
reference cage does not qualify as H05 concept/final3D. Root must authorize any build/render.
Original imagery, UAL data, other heroes' meshes/weights and all failed takes remain immutable.
"""
from __future__ import annotations
from pathlib import Path
import json, math

REQUIRED_COLLECTIONS = ['H05_BODY_AUTHORED','H05_CAPE_CANONICAL','H05_GLOVE_DORSAL_L','H05_GLOVE_DORSAL_R','H05_BOOT_L','H05_BOOT_R','H05_GEAR_ATTACHMENTS']

def load_spec(path):
    spec=json.loads(Path(path).read_text(encoding='utf-8'))
    assert spec['schema']=='xexoria.hero05.projection-scaffold-spec/1'
    assert 'MALE' in spec['identity']
    return spec

def create_common_orthographic_cameras(scene, master_height):
    """Later Blender invocation only. Shared scale, floor and pose enforce one-object projection."""
    import bpy
    from mathutils import Vector
    assert master_height>0
    centre=Vector((0,0,master_height*.5))
    cameras=[]
    for name,angle in [('front',0),('right',90),('back',180),('left',270)]:
        theta=math.radians(angle)
        position=Vector((math.sin(theta)*master_height*4,-math.cos(theta)*master_height*4,master_height*.5))
        data=bpy.data.cameras.new('H05_ORTHO_'+name)
        data.type='ORTHO';data.ortho_scale=master_height/.80
        data.shift_x=data.shift_y=0;data.clip_start=.001;data.clip_end=master_height*20
        camera=bpy.data.objects.new(data.name,data);scene.collection.objects.link(camera)
        camera.location=position;camera.rotation_euler=(centre-position).to_track_quat('-Z','Y').to_euler()
        camera['projection_view']=name;camera['shared_geometry_only']=True;cameras.append(camera)
    scene.render.resolution_x=2048;scene.render.resolution_y=2048;scene.render.resolution_percentage=100
    scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
    return cameras

def validate_canonical_authoring_contract(scene):
    """Do not fill missing mature anatomy with capsules/cubes or certify reference mannequin."""
    import bpy
    missing=[name for name in REQUIRED_COLLECTIONS if name not in bpy.data.collections]
    if missing:raise RuntimeError('Author H05 anatomy/costume before projection: '+','.join(missing))
    bodies=[obj for obj in bpy.data.collections['H05_BODY_AUTHORED'].all_objects if obj.type=='MESH']
    if not bodies or any(obj.get('reference_cage_only',False) for obj in bodies):
        raise RuntimeError('Reference cage or toy body cannot qualify as H05 authored body')
    capes=[obj for obj in bpy.data.collections['H05_CAPE_CANONICAL'].all_objects if obj.type=='MESH']
    if len(capes)!=1:raise RuntimeError('Exactly ONE canonical cape mesh required, not per-view pieces')
    cape=capes[0]
    if not cape.get('owner_outline_trace_reviewed',False):raise RuntimeError('Canonical owner rear cape outline/holes must be traced and reviewed once')
    if any(mod.type=='CLOTH' for mod in cape.modifiers):raise RuntimeError('Projection uses one cape-at-rest state, no per-view cloth simulation')
    for side in ['L','R']:
        gloves=bpy.data.collections['H05_GLOVE_DORSAL_'+side]
        if not any(o.get('hand_surface')=='dorsal_plate' for o in gloves.all_objects):raise RuntimeError('Explicit dorsal glove plating required '+side)
        boots=bpy.data.collections['H05_BOOT_'+side]
        for role in ['toe','heel','sole','shaft']:
            if not any(o.get('boot_role')==role for o in boots.all_objects):raise RuntimeError('Missing volumetric boot '+side+' '+role)
    return {'cape':cape.name,'body_meshes':[o.name for o in bodies],'rank':'AUTHORING_CONTRACT_ONLY_NOT_VISUAL_ACCEPTANCE'}

def authoring_recipe():
    return [
        'Verify and duplicate the CC0 UAL reference into a NEW scene only; stop all46clips and keep immutable originals.',
        'Fit male cage proportions to owner front/side landmarks in normalized height; preserve head/hair/beard identity. No reuse of another hero mesh or weights.',
        'Author and review mature H05 body/face/gear volumes. Keep UAL_REFERENCE_ONLY separately and excluded from qualified concept output.',
        'Trace one cape boundary and tear topology from owner rear, resolve with owner front/sides, then author ONE editable cloth surface with thickness and fixed at-rest drape.',
        'Author dorsal glove plates/knuckles and actual palm/finger side once; boots keep toe/sole/heel/shaft volume and ground contact.',
        'Establish one45degree A-pose with open empty hands; attach shoulder armor, straps and pouches once. Weapon pair remains a separate artifact.',
        'Use four shared-scale ORTHO cameras with no object/pose/visibility edits per view,2048square native output, neutral light, fixed floor/top margins.',
        'When Root authorizes rendering, label source outputs REFERENCE SCAFFOLD until independent anatomy/costume and unchanged turnaround QA gates pass.',
    ]

if __name__ == '__main__':
    raise SystemExit('Preparation-only H05 recipe. No Blender launch/render authorized; use scaffold_spec_r01.py for CPU provenance/spec.')
