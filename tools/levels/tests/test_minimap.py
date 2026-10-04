import json
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from render_minimap import affine,world_uv,render,CLASSES
ROOT=Path(__file__).resolve().parents[3]

class MinimapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout=json.loads((ROOT/'planning/levels/sunmeadow-v2-layout.json').read_text(encoding='utf8'))
        cls.base,cls.edges,cls.classes,cls.meta=render(cls.layout,256)
    def test_affine_north_up(self):
        a=affine([-64,64,-110,24])
        self.assertEqual(world_uv(-64,24,a),[0,0])
        self.assertEqual(world_uv(64,-110,a),[1,1])
    def test_classes_edges_determinism(self):
        self.assertEqual(self.base.tobytes(),render(self.layout,256)[0].tobytes())
        self.assertEqual(set(np.unique(np.asarray(self.classes))),set(CLASSES.values()))
        self.assertEqual(set(np.unique(np.asarray(self.edges))),{0,255})
    def test_icons_separate_and_rectangle(self):
        ids={q['id'] for q in self.meta['icon_anchors']}
        self.assertTrue({'player_spawn','waterfall_grotto','lotus_mere','brightwater_cove','sunmeadow_croft','hunter_camp'}<=ids)
        self.assertEqual(self.meta['presentation']['shape'],'rounded-rectangle')
        self.assertFalse(self.meta['presentation']['icons_baked'])
    def test_west_cliff_gap_and_pier(self):
        def sample(x,z):
            u,v=world_uv(x,z,self.meta['world_xz_to_uv_affine'])
            return int(np.asarray(self.classes)[round(v*255),round(u*255)])
        self.assertNotEqual(sample(-57,-80),CLASSES['rock'])
        self.assertEqual(sample(-55,-74.25),CLASSES['buildings'])
        self.assertEqual(sample(-51,9),CLASSES['water'])

if __name__=='__main__':unittest.main()
