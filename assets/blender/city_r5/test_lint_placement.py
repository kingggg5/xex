"""Synthetic test for lint_placement.py (rules L1-L5). Builds a tiny scene and asserts each rule fires once.

  blender -b --factory-startup --python-exit-code 1 --python assets/blender/city_r5/test_lint_placement.py
"""
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'lib'))
import citykit as ck  # noqa: E402
import lint_placement as lint  # noqa: E402

ck.reset_scene()
col = bpy.context.scene.collection
ground = ck.new_object('terrain / grass ground', [(-50, -50, 0), (50, -50, 0), (50, 50, 0), (-50, 50, 0)], [(0, 1, 2, 3)], 'grass_ground', col)
ck.box('crate resting', (0, 0, 0.5), (1, 1, 1), 'timber_dark', col)              # touches the ground: no finding
ck.box('crate floating', (5, 0, 0.6), (1, 1, 1), 'timber_dark', col)             # 10 cm gap: L1
ck.box('crate joint gap', (0, 0, 1.52), (1, 1, 1), 'timber_dark', col)           # 2 cm above 'crate resting': contact, no L1
ck.box('barrel sunk', (10, 0, 0.3), (1, 1, 1), 'timber_dark', col)               # bottom at -0.2: L2
ck.box('rock sunk', (12, 0, 0.3), (1, 1, 1), 'stone_foundation', col)            # 'rock': intentional L2
ck.box('lantern off island', (80, 0, 1.0), (0.5, 0.5, 0.5), 'metal_gold', col)   # no ground under it: L5
root = bpy.data.objects.new('kit_test', None)
col.objects.link(root)
root.location = (20, 0, 0)
owner = ck.lathe('tower cap', [(1.0, 0), (0.0, 2.0)], segments=8, material='roof_slate_blue', center=(0, 0, 3.0))
owner.parent = root
owner.matrix_parent_inverse = Matrix.Identity(4)
ck.box('tower body', (20, 0, 1.5), (2, 2, 3), 'stone_wall_warm', col)
ck.lathe('tower cap copper finial', [(0.2, 2.0), (0.0, 3.0)], segments=8, material='metal_gold', center=(0, 0, 3.0))  # never parented: L3 (+ floating)
ck.box('tile a', (30, 0, 0.05), (2, 2, 0.1), 'paver_surface', col)
ck.box('tile b', (30.5, 0, 0.05), (2, 2, 0.1), 'paver_surface', col)              # coplanar overlapping top faces: L4
bpy.context.view_layer.update()
rep = lint.run_lint('city', log=lambda *_: None)
got = {r: sorted(f['id'] for f in rep['findings'] if f['rule'] == r and not f['intentional']) for r in ('L1', 'L2', 'L3', 'L4', 'L5')}
print(got)
assert any('crate floating' in i for i in got['L1']), got
assert not any('crate joint gap' in i or 'crate resting' == i for i in got['L1']), got
assert got['L2'] == ['barrel sunk'], got
assert any(f['rule'] == 'L2' and f['intentional'] and f['id'] == 'rock sunk' for f in rep['findings']), 'rock should be intentional'
assert got['L3'] == ['tower cap copper finial'], got
assert any('tile a' in i and 'tile b' in i for i in got['L4']), got
assert got['L5'] == ['lantern off island'], got
print('lint_placement synthetic test: PASS')
