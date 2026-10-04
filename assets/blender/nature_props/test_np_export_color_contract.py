"""Regression for the observed cliff COLOR_0 mean false positive (CPU only)."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from export_helper import glb_facts


def fixture(indexed=True):
    positions=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],dtype='<f4')
    colors=np.array([[0,0,0],[1,1,1],[0,0,0],[1,1,1]],dtype='<f4')
    indices=np.array([0,1,2,0,2,3],dtype='<u2')
    chunks=[positions.tobytes(),colors.tobytes(),indices.tobytes()]
    binary=b''.join(chunks)
    views=[];offset=0
    for chunk in chunks:
        views.append({'buffer':0,'byteOffset':offset,'byteLength':len(chunk)});offset+=len(chunk)
    primitive={'attributes':{'POSITION':0,'COLOR_0':1},'material':0}
    if indexed:primitive['indices']=2
    gltf={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}], 'bufferViews':views,
          'accessors':[{'bufferView':0,'componentType':5126,'count':4,'type':'VEC3'},
                       {'bufferView':1,'componentType':5126,'count':4,'type':'VEC3'},
                       {'bufferView':2,'componentType':5123,'count':6,'type':'SCALAR'}],
          'materials':[{'name':'stone'}],'meshes':[{'primitives':[primitive]}],
          'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
    return gltf,binary


class IndexedColorContract(unittest.TestCase):
    def test_shared_vertices_are_weighted_by_triangle_corners(self):
        # Four unique vertices average .5, but the source's six face corners
        # contain four dark and two light samples and therefore average 1/3.
        facts=glb_facts(*fixture(True))
        got=facts['meshes'][0]['primitives'][0]['color0_mean']
        self.assertTrue(np.allclose(got,[1/3]*3,atol=5e-5),got)

    def test_nonindexed_attribute_mean_is_unchanged(self):
        facts=glb_facts(*fixture(False))
        self.assertEqual(facts['meshes'][0]['primitives'][0]['color0_mean'],[.5,.5,.5])


if __name__=='__main__':unittest.main()
