"""H05 preparation only: immutable intake/provenance/spec. Does not import bpy or render."""
from __future__ import annotations

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[4]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import hashlib, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(str(_XEXORIA_AGENT_OUTPUT / '20261004-hero05-scaffold-r01'))
ORIGINAL = Path(str(_XEXORIA_ASSET_SOURCE.parent / 'hero/05'))
FAILED = Path(str(_XEXORIA_AGENT_OUTPUT / '20261004-hero05-individual-r03'))
UAL = ROOT/'assets/models/heroes/hero02/source/third-party/ual1-standard-2025-06-10'
VIEW_FILES = {
    'front': 'ChatGPT Image Oct 1, 2026, 01_14_13 PM.png',
    'left': 'ChatGPT Image Oct 1, 2026, 01_15_15 PM.png',
    'right': 'ChatGPT Image Oct 1, 2026, 01_15_12 PM.png',
    'back': 'ChatGPT Image Oct 1, 2026, 01_15_44 PM.png',
    'weapons_separate': 'ChatGPT Image Oct 1, 2026, 01_16_07 PM.png',
}

def facts(path: Path):
    data = path.read_bytes()
    result = {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    if data[:8] == b'\x89PNG\r\n\x1a\n': result['native_dimensions'] = list(struct.unpack('>II', data[16:24]))
    return result

def prepare():
    provenance = json.loads((UAL/'provenance.json').read_text(encoding='utf-8-sig'))
    assert provenance['licence'] == 'CC0-1.0'
    verified = []
    for pin in provenance['files']:
        actual = facts(UAL/pin['file'])
        assert actual['sha256'] == pin['sha256'], f"UAL immutable pin mismatch: {pin['file']}"
        verified.append({**actual, 'expected_sha256': pin['sha256'], 'matches': True})
    gltf = json.loads((UAL/'AnimationLibrary_Godot_Standard.gltf').read_text(encoding='utf-8'))
    primitives = [p for mesh in gltf['meshes'] for p in mesh['primitives']]
    geometry = {'meshes': len(gltf['meshes']), 'primitives': len(primitives),
        'vertices': sum(gltf['accessors'][p['attributes']['POSITION']]['count'] for p in primitives),
        'triangles': sum(gltf['accessors'][p['indices']]['count']//3 for p in primitives),
        'skin_joints': len(gltf['skins'][0]['joints']), 'clips': len(gltf['animations']),
        'uv_normal_weights': all(all(k in p['attributes'] for k in ['TEXCOORD_0','NORMAL','WEIGHTS_0']) for p in primitives)}
    originals = {view: facts(ORIGINAL/file) for view, file in VIEW_FILES.items()}
    failed = {view: facts(FAILED/file) for view, file in {'front':'front.png','left':'left.png','back':'back-shape-lock.png','right':'right-corrected.png'}.items()}
    spec = {
        'schema':'xexoria.hero05.projection-scaffold-spec/1', 'status':'PREPARED_NOT_EXECUTED',
        'identity':'Owner-original adult brown-haired bearded MALE rogue. Root corrected accidental female wording; no generated persona substitution.',
        'style': ['purple hood/cowl','ONE long torn purple cape with restrained gold motifs','black/dark leather cross-straps and pouches','layered silver shoulder/bracer/knee/boot armor'],
        'sources': originals, 'failed_quartet_preserved': failed,
        'independent_review': 'planning/evidence/heroes-six-20261004/continuation/hero05-independent-review/review.json',
        'method_change': {'previous':'Three independent rear imagegen attempts remain below mirrorIoU .90 (.874/.872/.8792); left framing is +4.68% median.',
            'next':'One editable geometric projection master; single pose, cape topology/outline and camera framing; no independent rear regeneration.'},
        'verified_reference': {'asset':'UAL1 Standard mannequin', 'licence':'CC0-1.0','provenance':str(UAL/'provenance.json'), 'files':verified, 'geometry':geometry,
            'height_m':1.829,'rest':'T-pose,53joint reference','rank':'LICENSED_ANATOMY_REFERENCE_ONLY_NOT_FITTED_H05',
            'limits':'Neutral mannequin is not owner face/costume or an accepted H05 concept/finished3D. Existing H01 heat-cage code is method reference only; no H01 mesh/weights transfer.'},
        'missing_source': {'fitted_h05_body':'NOT_FOUND_VERIFIED_BY_INVENTORY','approved_h05_metres':'NOT_IN_2D_REFERENCES; use normalized proportions and reference height only until Root fits/approves physical scale'},
        'canonical_master': {'coordinate':'Blender X right, -Y front, Z up; feet Z0; no per-view transform changes',
            'pose':'Authorized45degree A-pose, relaxed open EMPTY hands, no weapon in body views',
            'body':'Fit reviewed reference cage to owner male proportions; author H05 body/head/hair/beard; a cage is not a qualified concept',
            'cape':'Trace ONE outer border from original rear cloth, then reconcile original front/sides. Author holes/frays once as actual shared topology; keep thickness/drape at rest; no physics simulation or view-dependent masks.',
            'gloves':'One left/right hand construction, dorsal armor tied to hand local dorsal axis; original side/back plated knuckles/wrist. Rear must not display broad exposed front palms.',
            'boots':'Single volumetric toe/sole/heel/shaft per side, floor-contacting; preserve armor/panel joins through all four cameras.',
            'attachments':'Same shoulder layers, chest cross-straps, belt buckle/pouches, thigh straps and cowl links in every view. Owner references determine count/placement; no random added greebles.',
            'materials':'Source-consistent dark leather, purple cloth/gold motifs, silver metal; separate structural validation from painting/material finish.'},
        'projection_contract': {'views':['front','right','back','left'],'angles_degrees':[0,90,180,270], 'camera':'ORTHO','shared_ortho_scale':'masterHeight / .80','native_pixels':[2048,2048],
            'same_ground_and_top_margin':True,'same_pose_mesh_visibility':True,'light':'Neutral fixed rig/world; no silhouette-hiding shadow/bloom','background':'Flat neutral or true transparent, labelled REFERENCE SCAFFOLD',
            'no_upscale_quality_claim':True},
        'future_checks': {'unchanged_qa':True,'front_back_mirror_iou':.90,'left_right_mirror_iou':.90,'height_deviation_fraction':.03,
            'design':'Independent rear hands, cape tears/outer tips, boot toe/heel, attachments and bearded male identity against owner originals',
            'reference_scaffold_cannot_pass':'Concept/material/anatomy/game-ready/final3D merely by camera consistency'},
        'future_budget': {'blender_cpu_threads':2,'no_simulation':True,'one_master':True,'preview_views':4,'initial_cpu_work_budget_seconds':300,
            'execution':'Not authorized now. Root must assign an idle CPU window and exact source/output invocation; stop on anatomy/source/shape failure.'},
        'toolchain': {'harness_project':'project-a6dcbc9c-dcdf-4efe-9428-b88a9b5694bf','harness_run':'RUN-20260923-mmorpg-plan-v3','shared_state_writes':0,
            'jev':'Reused verified task-family receipt20261004-heroes-continuation-r02 (733input47output finish_local_gaps); cache/savings unmeasured, no duplicate call',
            'context7':'Camera/basic APIs checked via classic Blender4.2 docs; installed5.2 integration still UNVERIFIED until authorized execution',
            'game_dev':'CLI absent in prior task capability discovery; existing project Blender recipe route retained, no package/install claim'},
        'verdicts': {'source_provenance':'PASS for existing reference/canonical2D intake','recipe':'PREPARED','body_fit':'UNVERIFIED','geometry':'NOT_BUILT','visual':'UNVERIFIED','runtime':'NOT_IN_SCOPE'},
        'no_blender_render_provider_client_qa_or_harness_mutations':True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    destination=OUT/'scaffold-spec-r01.json'
    assert not destination.exists(), 'Create-only spec destination already exists'
    destination.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':spec['status'],'out':str(destination),'reference':geometry,'fittedBody':'NOT_FOUND','BlenderLaunched':False}))
    return spec

if __name__ == '__main__': prepare()
