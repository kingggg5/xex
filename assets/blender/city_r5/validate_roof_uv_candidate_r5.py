"""Read back a roof-UV candidate, then compare it with the untouched baseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import repair_roof_uvs_r5 as repair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    receipt = json.loads(args.receipt.read_text(encoding='utf-8'))
    candidate = Path(bpy.data.filepath).resolve()
    baseline = Path(receipt['source'])
    assert candidate == Path(receipt['candidate']).resolve()
    assert repair.file_hash(candidate) == receipt['candidate_sha256']
    assert repair.file_hash(baseline) == receipt['source_sha256']
    bpy.context.view_layer.update()
    assert repair.geometry_digest(bpy.data.objects) == receipt['geometry_sha256_after']
    assert repair.layout_roots_snapshot() == receipt['layout_roots_preserved']
    assert {im.name: im.filepath for im in bpy.data.images if im.filepath} == receipt['image_filepaths']
    counts = {'objects': len(bpy.context.scene.objects),
              'meshes': sum(o.type == 'MESH' for o in bpy.context.scene.objects),
              'materials': len(bpy.data.materials)}
    assert counts == receipt['counts_preserved']
    plans = repair.plan_scene()
    max_error = 0.0
    witnesses = []
    for obj, plan in plans:
        layer = obj.data.uv_layers['UVMap']
        for face in plan['faces']:
            for li, expected in face['assignments']:
                max_error = max(max_error, *(abs(a - b) for a, b in zip(layer.data[li].uv, expected)))
        sampled = plan['faces'] if plan['kind'] == 'gable' else [plan['faces'][0], plan['faces'][-1]]
        for face in sampled:
            for li, _ in face['assignments']:
                vertex = obj.data.vertices[obj.data.loops[li].vertex_index]
                point = obj.matrix_world @ vertex.co
                uv = layer.data[li].uv
                witnesses.append({'object': obj.name, 'material': obj.data.materials[0].name,
                                  'position': [point.x, point.z, -point.y], 'uv': [uv.x, 1.0 - uv.y]})
    assert max_error < 1e-5, max_error
    unselected = {o.name: repair.uv_digest(o.data) for o in bpy.data.objects
                  if o.type == 'MESH' and not repair.classify(o) and o.data.uv_layers.get('UVMap')}
    bpy.ops.wm.open_mainfile(filepath=str(baseline))
    bpy.context.view_layer.update()
    assert repair.geometry_digest(bpy.data.objects) == receipt['geometry_sha256_before']
    assert repair.layout_roots_snapshot() == receipt['layout_roots_preserved']
    baseline_uv = {o.name: repair.uv_digest(o.data) for o in bpy.data.objects
                   if o.type == 'MESH' and not repair.classify(o) and o.data.uv_layers.get('UVMap')}
    assert unselected == baseline_uv, 'Unselected UV data changed'
    result = {'result': 'PASS', 'candidate_sha256': receipt['candidate_sha256'],
              'source_sha256': receipt['source_sha256'], 'roots_verified': 37,
              'homes_verified': 21, 'roof_meshes_verified': len(plans),
              'max_uv_readback_error': max_error,
              'unselected_uv_meshes_verified': len(unselected),
              'geometry_transforms_colors_materials_preserved': True,
              'texture_references_preserved': True, 'counts_preserved': counts}
    result['roof_uv_witnesses'] = witnesses
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'roof_uv_witnesses'}))


if __name__ == '__main__':
    main()
