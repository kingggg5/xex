"""Inspect immutable GLB connected parts without Blender/GPU or source writes."""

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[4]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import json
import struct
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[4]
SOURCE = Path(str(_XEXORIA_ASSET_SOURCE / 'sources/tripo/hero-01/texture4k-pbr-20261003/hero-01-P2-smartuv-4k-pbr-60b43240.glb'))
d = SOURCE.read_bytes()
jl = struct.unpack_from('<I', d, 12)[0]
j = json.loads(d[20:20+jl])
bin_start = 28 + jl
types = {5126: '<f4', 5125: '<u4', 5123: '<u2'}
def array(index, width):
    a = j['accessors'][index]
    v = j['bufferViews'][a['bufferView']]
    dtype = np.dtype(types[a['componentType']])
    offset = bin_start + v.get('byteOffset',0) + a.get('byteOffset',0)
    return np.ndarray((a['count'],width),dtype=dtype,buffer=d,offset=offset,strides=(v.get('byteStride',dtype.itemsize*width),dtype.itemsize))
prim = j['meshes'][0]['primitives'][0]
p = array(prim['attributes']['POSITION'],3)
co = p[:,[0,2,1]].astype(float)
co[:,1] *= -1
co *= 2.04 / (co[:,2].max()-co[:,2].min())
tri = array(prim['indices'],1).reshape(-1,3)
adj = [set() for _ in range(len(co))]
for a,b,c in tri:
    adj[a].update([b,c]); adj[b].update([a,c]); adj[c].update([a,b])
cache = {}
for index,point in enumerate(co):
    key = tuple(np.round(point,5))
    if key in cache:
        other = cache[key];adj[index].add(other);adj[other].add(index)
    else: cache[key] = index
seen,records,ids = set(),[],np.empty(len(co),dtype=np.int32)
for index in range(len(co)):
    if index in seen: continue
    todo,part=[index],[];seen.add(index)
    while todo:
        q=todo.pop();part.append(q)
        for nxt in adj[q]:
            if nxt not in seen:seen.add(nxt);todo.append(nxt)
    x=co[part];pid=len(records);ids[part]=pid
    records.append({'id':pid,'vertices':len(part),'center':x.mean(0).tolist(),'min':x.min(0).tolist(),'max':x.max(0).tolist(),'size':(x.max(0)-x.min(0)).tolist()})
targets={'beard':[0,-.19,1.66],'chest_fitting':[.23,-.04,1.28],'tabard_tip':[0,-.1,.20],'hand':[.66,-.04,.90]}
matches = {}
for name, point in targets.items():
    index = int(np.argmin(np.linalg.norm(co - np.array(point), axis=1)))
    matches[name] = {'nearest_vertex': index, 'part': records[int(ids[index])]}
out={'schema':'xexoria.hero01-source-parts/1','component_count':len(records),'problem_regions':matches,'components':records}
(ROOT/'planning/evidence/heroes-six-20261004/hero01-source-parts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'count':len(records),'regions':matches},ensure_ascii=False))
