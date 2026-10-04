"""Read exported GLB bytes and verify wind phase flip, alpha mode and attributes."""
from pathlib import Path
import argparse
import json
import math
import struct

ROOT=Path(__file__).resolve().parents[3]
def read(path):
    data=Path(path).read_bytes();magic,version,length=struct.unpack_from('<III',data)
    if magic!=0x46546c67 or version!=2 or length!=len(data):raise ValueError('Bad GLB header')
    pos=12;doc=None;bin_data=b''
    while pos<len(data):
        n,kind=struct.unpack_from('<II',data,pos);chunk=data[pos+8:pos+8+n];pos+=8+n
        if kind==0x4e4f534a:doc=json.loads(chunk)
        elif kind==0x004e4942:bin_data=chunk
    return doc,bin_data
def accessor(doc,data,idx):
    a=doc['accessors'][idx];v=doc['bufferViews'][a['bufferView']]
    fmt={5126:'f',5123:'H',5125:'I',5121:'B',5122:'h',5120:'b'}[a['componentType']];count={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
    size=struct.calcsize('<'+fmt*count);offset=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',size)
    rows=[struct.unpack_from('<'+fmt*count,data,offset+i*stride) for i in range(a['count'])]
    if a.get('normalized'):
        div={5123:65535,5121:255,5122:32767,5120:127}[a['componentType']]
        rows=[tuple(max(-1,x/div) for x in row) for row in rows]
    return rows
def validate(path,receipt,runtime=False):
    doc,data=read(path);results=[]
    for me in doc['meshes']:
        for p in me['primitives']:
            attrs=p['attributes'];wind=accessor(doc,data,attrs['TEXCOORD_1']);xyz=accessor(doc,data,attrs['POSITION'])
            if any(not all(math.isfinite(x) and -.0001<=x<=1.0001 for x in row) for row in wind):raise ValueError('Nonfinite/out-of-range wind')
            for m in doc.get('materials',[]):
                if m.get('alphaMode')!='MASK' or not m.get('doubleSided'):raise ValueError('Flora must be MASK and double-sided')
            if 'TANGENT' not in attrs:raise ValueError('Missing normal tangent')
            # Exact seed phase for pad/lotus proves export V flipped from 1-phase.
            recipe=receipt['recipe'];expected=None
            if recipe=='flora.lilypad/1':expected=[(.618+receipt['seed']*.137)%1]
            elif recipe=='flora.lotus/1':expected=[(receipt['seed']*.137)%1]
            elif recipe=='flora.reeds/1':
                expected=[(.6180339887*(i+1)+receipt['seed']*.137)%1 for i in range(receipt['params']['cards'])]
                expected +=[(.37*(i+1)+receipt['seed']*.11)%1 for i in range(receipt['params'].get('cattails',0))]
            tolerance=1/4095+.00001 if runtime else 2e-6
            if expected is not None and any(min(abs(w[1]-e) for e in expected)>tolerance for w in wind):raise ValueError('Wind phase v-flip mismatch')
            if runtime:base=[min(w[0] for w in wind)]
            elif recipe=='flora.lilypad/1':base=[w[0] for q,w in zip(xyz,wind) if abs(q[0])<1e-6 and abs(q[2])<1e-6]
            else:base=[w[0] for q,w in zip(xyz,wind) if q[1]<=0]
            if base and max(base)>1e-5:raise ValueError('Base wind not fixed')
            results.append({'vertices':len(xyz),'attributes':list(attrs),'wind_min':[min(w[j] for w in wind) for j in (0,1)],
                 'wind_max':[max(w[j] for w in wind) for j in (0,1)],'expected_phase':expected,'phase_flip_verified':expected is not None,'base_fixed':bool(base)})
    return {'file':str(path),'checks':results,'status':'PASS'}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--only',default='');ap.add_argument('--runtime',action='store_true');a=ap.parse_args();only=set(filter(None,a.only.split(',')));results=[]
    evid=ROOT/'planning/evidence/sunmeadow-props-20261002/craft'
    for p in sorted((evid/'receipts').glob('sm_*.json')):
        r=json.loads(p.read_text(encoding='utf8'))
        if r.get('family')!='flora' or (only and r['id'] not in only):continue
        for f in r['source_files']:
            path=evid/'decoded-review/flora'/(Path(f).stem+'.review.glb') if a.runtime else ROOT/f
            results.append(validate(path,r,a.runtime))
    if not results:raise ValueError('No flora outputs')
    (evid/('flora-wind-runtime-validation.json' if a.runtime else 'flora-wind-validation.json')).write_text(json.dumps({'status':'PASS','runtime_decoded':a.runtime,'files':results},indent=2),encoding='utf8')
    print('FLORA EXPORTED WIND/ALPHA/TANGENTS PASS',len(results))
if __name__=='__main__':main()
