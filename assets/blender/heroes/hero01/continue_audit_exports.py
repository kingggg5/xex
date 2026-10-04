"""Inspect lean exported clip/rig bytes without a renderer or image decoding."""

# Portable external asset/output roots; no source data or admission thresholds are changed.
from pathlib import Path as _XexoriaPath
from os import environ as _xexoria_env
_XEXORIA_REPO = _XexoriaPath(__file__).resolve().parents[4]
_XEXORIA_ASSET_SOURCE = _XexoriaPath(_xexoria_env.get('XEXORIA_ASSET_SOURCE_ROOT') or (_XexoriaPath.home() / 'Downloads' / 'Xexoria-Game'))
_XEXORIA_AGENT_OUTPUT = _XexoriaPath(_xexoria_env.get('XEXORIA_AGENT_OUTPUT') or (_XEXORIA_ASSET_SOURCE / 'agent-output'))

import argparse
import hashlib
import json
import struct
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
SOURCE=Path(str(_XEXORIA_AGENT_OUTPUT / '20261004-hero01-rig-r01'))
def parse(path):
    data=Path(path).read_bytes();pos=12;doc=None;binary=b''
    while pos<len(data):
        n,tag=struct.unpack_from('<2I',data,pos);chunk=data[pos+8:pos+8+n]
        if tag==0x4e4f534a:doc=json.loads(chunk)
        elif tag==0x004e4942:binary=chunk
        pos+=8+n
    def accessor(index):
        acc=doc['accessors'][index];view=doc['bufferViews'][acc['bufferView']]
        dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[acc['componentType']]);size={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[acc['type']]
        values=np.ndarray((acc['count'],size),dtype=dtype,buffer=binary,offset=view.get('byteOffset',0)+acc.get('byteOffset',0),strides=(view.get('byteStride',dtype.itemsize*size),dtype.itemsize)).copy()
        if acc.get('normalized') and dtype.kind=='u':values=values.astype(float)/np.iinfo(dtype).max
        return values
    return data,doc,accessor
def joint_signature(doc):
    parent={child:index for index,node in enumerate(doc['nodes']) for child in node.get('children',[])}
    return [(doc['nodes'][j].get('name'),doc['nodes'][parent[j]].get('name') if j in parent else None) for j in doc['skins'][0]['joints']]
rows=[]
for lod in range(3):
    source_bytes,source,sourceacc=parse(SOURCE/f'hero01_swordsman_lod{lod}.glb')
    path=a.out/f'hero01_swordsman_lod{lod}.geometry-clips.glb';data,doc,acc=parse(path)
    signature=joint_signature(doc);assert signature==joint_signature(source),'joint names/order/hierarchy changed'
    assert len(signature)==47
    ibm=acc(doc['skins'][0]['inverseBindMatrices']);oldibm=sourceacc(source['skins'][0]['inverseBindMatrices'])
    ibm_deviation=float(np.abs(ibm-oldibm).max());assert ibm_deviation<1e-6,'inverse binds changed'
    clips=[]
    for animation in doc.get('animations',[]):
        times=np.unique(np.concatenate([acc(s['input']).ravel() for s in animation['samplers']]))
        clips.append({'name':animation['name'],'duration_s':float(times.max()-times.min()),'times':times.tolist(),'channels':len(animation['channels'])})
    assert len(clips)==(14 if lod==0 else 0)
    if lod==0:
        arc=next(c for c in clips if c['name']=='swordsman.skill_arc')
        assert any(abs(t-.25)<1e-6 for t in arc['times']),'exact half-frame250ms Arc key missing'
        nova=next(c for c in clips if c['name']=='swordsman.skill_nova')
        assert any(abs(t-.15)<1e-6 for t in nova['times']),'exact150ms Nova plant key missing'
    assert not doc.get('images') and not doc.get('textures'),'heavy map copy emitted'
    triangles=0;max_error=0;max_influences=0
    for mesh in doc['meshes']:
        for prim in mesh['primitives']:
            attrs=prim['attributes'];assert 'TEXCOORD_0'in attrs
            assert 'JOINTS_1'not in attrs and 'WEIGHTS_1'not in attrs
            weights=acc(attrs['WEIGHTS_0']);max_error=max(max_error,float(np.abs(weights.sum(1)-1).max()));max_influences=max(max_influences,int((weights>0).sum(1).max()))
            triangles+=doc['accessors'][prim['indices']]['count']//3
    assert triangles==[12000,6000,2499][lod] and max_influences<=4 and max_error<1e-5
    rows.append({'lod':lod,'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'joints':47,'joint_signature_matches':True,
                 'inverse_bind_max_deviation':ibm_deviation,'triangles':triangles,'max_influences':max_influences,'weight_sum_error':max_error,
                 'maps':0,'uv0':True,'clips':clips,'source_sha256':hashlib.sha256(source_bytes).hexdigest()})
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps({'schema':'xexoria.hero01-clip-byte-audit/1','status':'TECHNICAL_BYTES_PASS_VISUAL_UNVERIFIED','rows':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps([{'lod':r['lod'],'bytes':r['bytes'],'joints':r['joints'],'triangles':r['triangles'],'clips':[c['name'] for c in r['clips']]} for r in rows]))
