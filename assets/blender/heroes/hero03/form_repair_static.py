"""CPU-light immutable GLB/region audit; Python stdlib only, no Blender.
Matches the Blender plan's source-space projection anchors before a CPU slot.
Does not alter source or create a candidate mesh.
"""
import argparse
import hashlib
import json
import struct
from collections import defaultdict
from pathlib import Path

PIN="bdce6f6c664d552ad71624622f6d70921e8b782bcfc1cc7c627b2a72da4d11e2"
TYPE_COUNTS={"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4}
COMPONENTS={5126:("f",4),5125:("I",4),5123:("H",2),5121:("B",1)}


def load(path):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PIN:raise ValueError("Source hash differs")
    magic,version,size=struct.unpack_from("<III",raw)
    if magic!=0x46546c67 or version!=2 or size!=len(raw):raise ValueError("Malformed GLB")
    json_len,json_kind=struct.unpack_from("<II",raw,12)
    if json_kind!=0x4e4f534a:raise ValueError("Missing JSON chunk")
    doc=json.loads(raw[20:20+json_len])
    bin_offset=20+json_len
    bin_len,bin_kind=struct.unpack_from("<II",raw,bin_offset)
    if bin_kind!=0x004e4942:raise ValueError("Missing BIN chunk")
    binary=memoryview(raw)[bin_offset+8:bin_offset+8+bin_len]
    def accessor(index):
        a=doc["accessors"][index];view=doc["bufferViews"][a["bufferView"]]
        if a.get("sparse") or view.get("extensions"):raise ValueError("Compressed/sparse source needs installed decoder")
        kind,width=COMPONENTS[a["componentType"]];count=TYPE_COUNTS[a["type"]]
        stride=view.get("byteStride",width*count);start=view.get("byteOffset",0)+a.get("byteOffset",0)
        return [struct.unpack_from("<"+kind*count,binary,start+i*stride) for i in range(a["count"])]
    if any(any(k in node for k in ["translation","rotation","scale","matrix"]) for node in doc["nodes"]):
        raise ValueError("Source node transforms differ from pinned identity")
    primitives=[p for mesh in doc["meshes"] for p in mesh["primitives"]]
    if len(primitives)!=1:raise ValueError("Expected one pinned primitive")
    primitive=primitives[0]
    positions=[(x,-z,y) for x,y,z in accessor(primitive["attributes"]["POSITION"])]
    indices=[v[0] for v in accessor(primitive["indices"])]
    return positions,[tuple(indices[i:i+3]) for i in range(0,len(indices),3)]


def front_hit(positions,faces,x,z):
    hits=[]
    for face_index,face in enumerate(faces):
        p,q,r=[positions[index] for index in face]
        den=(q[2]-r[2])*(p[0]-r[0])+(r[0]-q[0])*(p[2]-r[2])
        if abs(den)<1e-15:continue
        a=((q[2]-r[2])*(x-r[0])+(r[0]-q[0])*(z-r[2]))/den
        b=((r[2]-p[2])*(x-r[0])+(p[0]-r[0])*(z-r[2]))/den
        c=1-a-b
        if min(a,b,c)>=-1e-8:
            hits.append((a*p[1]+b*q[1]+c*r[1],face_index))
    if not hits:raise ValueError(f"No frontal hit at{x,z}")
    y,face_index=min(hits)
    return {"point":[x,y,z],"face":face_index,"intersections":len(hits)}


def audit(positions,faces):
    adjacency=[set() for _ in positions];edge_faces=defaultdict(list)
    zero=[]
    for index,(a,b,c) in enumerate(faces):
        for left,right in [(a,b),(b,c),(c,a)]:
            adjacency[left].add(right);adjacency[right].add(left);edge_faces[tuple(sorted((left,right)))].append(index)
        p,q,r=[positions[v] for v in (a,b,c)]
        u=[q[k]-p[k] for k in range(3)];v=[r[k]-p[k] for k in range(3)]
        cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        if sum(value*value for value in cross)<4e-20:zero.append(index)
    seen=set();parts=[]
    for vertex in range(len(positions)):
        if vertex in seen:continue
        stack=[vertex];part=[];seen.add(vertex)
        while stack:
            item=stack.pop();part.append(item)
            for other in adjacency[item]:
                if other not in seen:seen.add(other);stack.append(other)
        parts.append(part)
    parts.sort(key=len,reverse=True)
    component_of={vertex:part_index for part_index,part in enumerate(parts) for vertex in part}
    duplicates=defaultdict(list)
    for face_index,face in enumerate(faces):duplicates[tuple(sorted(face))].append(face_index)
    overconnected=[]
    for edge,linked in edge_faces.items():
        if len(linked)<=2:continue
        centre=[sum(positions[vertex][k] for vertex in edge)/2 for k in range(3)]
        x,y,z=centre;component=component_of[edge[0]]
        region='tail' if component==1 else 'paw' if z<.12 else 'hand' if abs(x)>.18 and .40<z<.68 else 'face/hair' if abs(x)<.10 and z>.77 else 'rear_torso' if abs(x)<.15 and y>.012 and .525<z<.725 else 'body/garment'
        overconnected.append({"vertices":list(edge),"component":component,"region":region,"centre":centre,"linked_faces":linked})
    rear=[i for i in parts[0] if abs(positions[i][0])<.15 and .525<positions[i][2]<.725 and positions[i][1]>.012]
    eyes=[front_hit(positions,faces,sign*.041,.855) for sign in [-1,1]]
    mouth=front_hit(positions,faces,0,.774)
    counts=[]
    for eye in eyes:
        x,y,z=eye["point"]
        counts.append(sum(((positions[i][0]-x)/.025)**2+((positions[i][2]-z)/.016)**2<1 and abs(positions[i][1]-y)<.023 for i in parts[0]))
    return {"vertices":len(positions),"triangles":len(faces),"component_vertices":[len(part) for part in parts],
            "boundary_edges":sum(len(linked)==1 for linked in edge_faces.values()),
            "overconnected_edges":sum(len(linked)>2 for linked in edge_faces.values()),
            "overconnected_witnesses":overconnected,
            "duplicate_face_vertex_sets":[linked for linked in duplicates.values() if len(linked)>1],
            "zero_area_faces":zero,"rear_region_vertices":len(rear),"eyes":eyes,"orbital_region_vertices":counts,
            "mouth":mouth,"Blender_execution":False,"source_changes":False,"candidate_created":False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True);args=parser.parse_args()
    if args.out.exists():raise ValueError("Preserve existing static audit")
    positions,faces=load(args.source);report=audit(positions,faces)
    report.update({"schema":"xexoria.hero03.form-static-audit/1","source_sha256":PIN,"status":"INPUT_REGIONS_AUDITED_FORM_UNVERIFIED"})
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report))


if __name__=="__main__":main()
