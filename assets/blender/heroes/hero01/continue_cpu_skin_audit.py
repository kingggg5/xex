"""Sample actual exported glTF animation and linear skinning on CPU; no Blender/renderer/images."""
import os
os.environ['OPENBLAS_NUM_THREADS']='2'
os.environ['OMP_NUM_THREADS']='2'
import argparse
import hashlib
import json
import struct
from pathlib import Path
import numpy as np
P=argparse.ArgumentParser();P.add_argument('--input',type=Path,required=True);P.add_argument('--report',type=Path,required=True)
a=P.parse_args();data=a.input.read_bytes();offset=12;doc=None;binary=b''
while offset<len(data):
    n,tag=struct.unpack_from('<2I',data,offset);chunk=data[offset+8:offset+8+n]
    if tag==0x4e4f534a:doc=json.loads(chunk)
    elif tag==0x004e4942:binary=chunk
    offset+=8+n
types={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'};sizes={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}
def acc(index):
    item=doc['accessors'][index];view=doc['bufferViews'][item['bufferView']];dtype=np.dtype(types[item['componentType']]);size=sizes[item['type']]
    values=np.ndarray((item['count'],size),dtype=dtype,buffer=binary,offset=view.get('byteOffset',0)+item.get('byteOffset',0),strides=(view.get('byteStride',dtype.itemsize*size),dtype.itemsize)).copy()
    if item.get('normalized') and dtype.kind=='u':values=values.astype(float)/np.iinfo(dtype).max
    return values
nodes=doc['nodes'];parents={child:i for i,node in enumerate(nodes) for child in node.get('children',[])}
skin=doc['skins'][0];joint_nodes=skin['joints'];assert len(joint_nodes)==47
ibm=acc(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1).astype(float)
prims=[p for mesh in doc['meshes'] for p in mesh['primitives']];assert len(prims)==1
prim=prims[0];attrs=prim['attributes'];pos=acc(attrs['POSITION']).astype(float);n=len(pos)
hom=np.column_stack((pos,np.ones(n)));joint_indices=acc(attrs['JOINTS_0']).astype(int);weights=acc(attrs['WEIGHTS_0']).astype(float)
weights/=weights.sum(1)[:,None]
indices=acc(prim['indices']).ravel().reshape(-1,3)
edges=np.unique(np.sort(np.vstack((indices[:,[0,1]],indices[:,[1,2]],indices[:,[2,0]])),axis=1),axis=0)
def qmatrix(q):
    x,y,z,w=q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def slerp(q0,q1,t):
    q0=q0/np.linalg.norm(q0);q1=q1/np.linalg.norm(q1);dot=float(q0@q1)
    if dot<0:q1=-q1;dot=-dot
    if dot>.9995:
        q=q0+t*(q1-q0);return q/np.linalg.norm(q)
    theta=np.arccos(np.clip(dot,-1,1));return (np.sin((1-t)*theta)*q0+np.sin(t*theta)*q1)/np.sin(theta)
def sampled_world(animation,time):
    tr=[np.array(n.get('translation',[0,0,0]),dtype=float) for n in nodes]
    ro=[np.array(n.get('rotation',[0,0,0,1]),dtype=float) for n in nodes]
    sc=[np.array(n.get('scale',[1,1,1]),dtype=float) for n in nodes]
    if animation:
        for channel in animation['channels']:
            sampler=animation['samplers'][channel['sampler']];times=acc(sampler['input']).ravel();values=acc(sampler['output']).astype(float)
            i=max(0,min(len(times)-2,int(np.searchsorted(times,time,side='right')-1)))
            if len(times)==1:value=values[0]
            elif time<=times[0]:value=values[0]
            elif time>=times[-1]:value=values[-1]
            else:
                t=float((time-times[i])/(times[i+1]-times[i]))
                if sampler.get('interpolation','LINEAR')=='STEP':value=values[i]
                elif channel['target']['path']=='rotation':value=slerp(values[i],values[i+1],t)
                else:value=values[i]*(1-t)+values[i+1]*t
            target=channel['target']['node'];kind=channel['target']['path']
            if kind=='translation':tr[target]=value
            elif kind=='rotation':ro[target]=value
            elif kind=='scale':sc[target]=value
    world=[None]*len(nodes)
    def visit(i):
        if world[i] is not None:return world[i]
        if 'matrix'in nodes[i]:local=np.array(nodes[i]['matrix']).reshape(4,4).T
        else:
            local=np.eye(4);local[:3,:3]=qmatrix(ro[i])@np.diag(sc[i]);local[:3,3]=tr[i]
        world[i]=visit(parents[i])@local if i in parents else local
        return world[i]
    for i in range(len(nodes)):visit(i)
    return np.array(world)
def skinned(world):
    matrices=world[joint_nodes]@ibm
    output=np.zeros((n,4))
    for influence in range(4):
        output+=np.einsum('nij,nj->ni',matrices[joint_indices[:,influence]],hom)*weights[:,influence,None]
    return output[:,:3]
rest=skinned(sampled_world(None,0));lengths=np.linalg.norm(rest[edges[:,0]]-rest[edges[:,1]],axis=1);valid=lengths>.002
root_index=next(i for i,node in enumerate(nodes) if node.get('name')=='root');socket=next(i for i,node in enumerate(nodes) if node.get('name')=='socket_weapon_R')
rows=[]
for animation in doc['animations']:
    times=np.unique(np.concatenate([acc(s['input']).ravel() for s in animation['samplers']]))
    start,end=float(times[0]),float(times[-1]);samples=[];roots=[]
    sample_times=list(np.linspace(start,end,21))
    if animation['name']=='swordsman.skill_arc':sample_times.append(.25)
    if animation['name']=='swordsman.skill_nova':sample_times.append(.15)
    for time in sorted(set(sample_times)):
        world=sampled_world(animation,time);vertices=skinned(world);assert np.isfinite(vertices).all()
        ratio=np.linalg.norm(vertices[edges[:,0]]-vertices[edges[:,1]],axis=1)[valid]/lengths[valid]
        root=world[root_index,:3,3];roots.append(root)
        top=int(np.argmax(vertices[:,1]));low=int(np.argmin(vertices[:,1]))
        samples.append({'time_s':time,'floor_min_m':float(vertices[:,1].min()),'height_max_m':float(vertices[:,1].max()),
                        'stretch_p99':float(np.quantile(ratio,.99)),'edges_over2x':int((ratio>2).sum()),
                        'right_socket_world_gltf':world[socket,:3,3].tolist(),'highest_vertex_bind':pos[top].tolist(),
                        'lowest_vertex_bind':pos[low].tolist()})
    roots=np.array(roots);drift=roots.max(0)-roots.min(0);assert np.max(np.abs(drift))<1e-6
    rows.append({'clip':animation['name'],'duration_s':end-start,'root_xyz_drift_m':drift.tolist(),'samples':samples,
                 'native_visual':'UNVERIFIED'})
result={'schema':'xexoria.hero01-actual-byte-skinning/1','status':'CPU_EXPORTED_POSE_AUDIT_COMPLETE_NATIVE_REVIEW_REQUIRED',
        'input':str(a.input),'sha256':hashlib.sha256(data).hexdigest(),'vertical_axis':'glTF+Y','method':'glTF LINEAR/STEP interpolation; quaternion slerp; jointWorld*inverseBind normalized linear skinning',
        'rows':rows,'limits':['No renderer/GPU/image decoding. Actual shader/device/art comparison remains pending.']}
a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps([{'clip':r['clip'],'duration_s':r['duration_s'],'floor_min':min(s['floor_min_m'] for s in r['samples']),
                  'stretch_p99':max(s['stretch_p99'] for s in r['samples']),'end_height':r['samples'][-1]['height_max_m']} for r in rows]))
