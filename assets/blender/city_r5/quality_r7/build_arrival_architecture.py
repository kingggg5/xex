"""One CPU-only r01 architecture export; baseline terrain/trees are never rebuilt."""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
import bpy, bmesh

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=ROOT/'assets/models/reference-city/r5/arrival-hlod-r01'
SELECTED=['m5-p0-c193','m5-p0-c195','m5-p0-c208','m5-p0-c244','m3-p0-c67','m3-p0-c68','m3-p0-c80','m4-p0-c86']
SHA='771fdf2bc450c3df2cc937f231176145d9d27bfae7772b616298a0dd063038b5'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default=str(OUT))
    raw=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    output=Path(parser.parse_args(raw).out).resolve()
    if output!=OUT.resolve(): raise RuntimeError('Only the new r01 directory is owned')
    baseline=ROOT/'apps/client/src/assets/models/env_reference_city_hlod.glb'
    if sha(baseline)!=SHA: raise RuntimeError('Pinned baseline changed')
    report=json.loads((OUT/'cpu-inspection.json').read_text())
    components={c['id']:c for c in report['components']}
    selected=[components[k] for k in SELECTED]
    if sum(c['triangles'] for c in selected)!=100: raise RuntimeError('Selected source topology mismatch')
    glb=output/'architecture-only.glb';blend=output/'architecture-source.blend';receipt=output/'architecture-receipt.json'
    if any(p.exists() for p in (glb,blend,receipt)): raise RuntimeError('Create-only outputs already exist')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene;scene.render.threads_mode='FIXED';scene.render.threads=6
    materials={}
    for source in report['materials']:
        material=bpy.data.materials.new(source['name']);material.use_nodes=True
        pbr=source.get('pbrMetallicRoughness',{});node=material.node_tree.nodes.get('Principled BSDF')
        node.inputs['Base Color'].default_value=pbr.get('baseColorFactor',[1,1,1,1])
        node.inputs['Roughness'].default_value=pbr.get('roughnessFactor',1)
        node.inputs['Metallic'].default_value=pbr.get('metallicFactor',0)
        materials[source['name']]=material
    collection=bpy.data.collections.new('Arrival r01 architecture');scene.collection.children.link(collection)
    parts=[]

    def mesh(name,vertices,faces,face_materials,colors,origin):
        data=bpy.data.meshes.new(name);data.from_pydata(vertices,[],faces);data.update()
        obj=bpy.data.objects.new(name,data);collection.objects.link(obj)
        keys=list(dict.fromkeys(face_materials))
        for key in keys:data.materials.append(materials[key])
        for p,key in zip(data.polygons,face_materials):p.material_index=keys.index(key)
        attr=data.color_attributes.new(name='COLOR_0',type='FLOAT_COLOR',domain='CORNER')
        for p,color in zip(data.polygons,colors):
            for i in p.loop_indices:attr.data[i].color=(*color,1)
        data.color_attributes.active_color_index=data.color_attributes.find('COLOR_0')
        uv=data.uv_layers.new(name='UVMap')
        for p in data.polygons:
            coords=[vertices[data.loops[i].vertex_index] for i in p.loop_indices]
            spans=[max(v[a] for v in coords)-min(v[a] for v in coords) for a in range(3)]
            axes=sorted(range(3),key=lambda a:spans[a],reverse=True)[:2]
            for i in p.loop_indices:
                v=vertices[data.loops[i].vertex_index]
                uv.data[i].uv=tuple((v[a]-min(q[a] for q in coords))/max(spans[a],1e-8) for a in axes)
        bm=bmesh.new();bm.from_mesh(data);bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.normal_update()
        if any(not e.is_manifold for e in bm.edges): raise RuntimeError(name+' non-manifold architecture')
        bm.to_mesh(data);bm.free();data.update()
        if data.validate(verbose=False,clean_customdata=False):raise RuntimeError(name+' required geometry repair')
        obj['arrival_source_component']=origin;obj['original_expression']='layered roof / framed recessed facade'
        parts.append(obj);return obj

    def box(name,bounds,key,origin,color=(1,1,1)):
        lo,hi=bounds;v=[(lo[0],lo[1],lo[2]),(hi[0],lo[1],lo[2]),(hi[0],hi[1],lo[2]),(lo[0],hi[1],lo[2]),(lo[0],lo[1],hi[2]),(hi[0],lo[1],hi[2]),(hi[0],hi[1],hi[2]),(lo[0],hi[1],hi[2])]
        f=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        return mesh(name,v,f,[key]*6,[color]*6,origin)

    def facade(c):
        lo,hi=c['boundsBlender']['min'],c['boundsBlender']['max'];x0,y0,z0=lo;x1,y1,z1=hi
        width,height=x1-x0,z1-z0;front=y0+0.12;back=y1;depth=0.20
        centers=[x0+width*.27,x0+width*.73];windows=[]
        for cx in centers:
            for fraction in (.27,.67):
                cz=z0+height*fraction;windows.append((cx-width*.095,cx+width*.095,cz-height*.085,cz+height*.085))
        xs=sorted(set([x0,x1]+[v for w in windows for v in w[:2]]));zs=sorted(set([z0,z1]+[v for w in windows for v in w[2:]]))
        vertices=[];faces=[];keys=[];colors=[];seen={}
        def face(coords,key='HLOD_Stone',color=(1,1,1)):
            ids=[]
            for p in coords:
                p=tuple(p);token=tuple(round(t,8) for t in p)
                if token not in seen:seen[token]=len(vertices);vertices.append(p)
                ids.append(seen[token])
            faces.append(ids);keys.append(key);colors.append(color)
        for i,(a,b) in enumerate(zip(xs,xs[1:])):
            for j,(d,e) in enumerate(zip(zs,zs[1:])):
                inside=any(l<(a+b)/2<r and bottom<(d+e)/2<top for l,r,bottom,top in windows)
                if not inside:face([(a,front,d),(b,front,d),(b,front,e),(a,front,e)],color=(.94+.025*(i%2),.97,.98))
                face([(a,back,d),(a,back,e),(b,back,e),(b,back,d)])
        for d,e in zip(zs,zs[1:]):
            face([(x0,front,d),(x0,front,e),(x0,back,e),(x0,back,d)])
            face([(x1,front,d),(x1,back,d),(x1,back,e),(x1,front,e)])
        for a,b in zip(xs,xs[1:]):
            face([(a,front,z1),(b,front,z1),(b,back,z1),(a,back,z1)])
            face([(a,front,z0),(a,back,z0),(b,back,z0),(b,front,z0)])
        for l,r,bottom,top in windows:
            rear=front+depth
            face([(l,front,bottom),(l,rear,bottom),(l,rear,top),(l,front,top)],color=(.66,.70,.75))
            face([(r,front,bottom),(r,front,top),(r,rear,top),(r,rear,bottom)],color=(.84,.87,.90))
            face([(l,front,bottom),(r,front,bottom),(r,rear,bottom),(l,rear,bottom)],color=(1.05,1.03,1))
            face([(l,front,top),(l,rear,top),(r,rear,top),(r,front,top)],color=(.66,.70,.75))
            face([(l,rear,bottom),(r,rear,bottom),(r,rear,top),(l,rear,top)],'HLOD_Wood',(.65,.70,.80))
        mesh(c['id']+' recessed-wall',vertices,faces,keys,colors,c['id'])
        # Medium cap/plinth and corner frame, contained in the old wall envelope.
        for label,a,b in [('plinth',z0,z0+.50),('crown',z1-.38,z1)]:box(c['id']+' '+label,([x0,y0,a],[x1,front+.06,b]),'HLOD_Stone',c['id'],(1.03,1.01,.96))
        for label,a,b in [('left',x0,x0+.24),('right',x1-.24,x1)]:box(c['id']+' '+label+' frame',([a,y0,z0+.5],[b,front+.05,z1-.38]),'HLOD_Stone',c['id'],(.89,.92,.97))
        for index,(l,r,bottom,top) in enumerate(windows):box(c['id']+' sill '+str(index),([l-.035,y0+.035,bottom-.085],[r+.035,front+.065,bottom+.005]),'HLOD_Wood',c['id'],(1.12,1.08,1))

    def gable(c):
        lo,hi=c['boundsBlender']['min'],c['boundsBlender']['max'];x0,y0,z0=lo;x1,y1,z1=hi;cy=(y0+y1)/2;d=(y1-y0)/2;h=z1-z0
        profile=[(y0,z0),(y0+d*.10,z0+h*.075),(y0+d*.12,z0+h*.055),(y0+d*.34,z0+h*.31),(y0+d*.36,z0+h*.27),(y0+d*.64,z0+h*.61),(y0+d*.66,z0+h*.57),(cy,z1)]
        profile+= [(2*cy-y,z) for y,z in profile[:-1][::-1]]
        n=len(profile);v=[(x,y,z) for x in (x0,x1) for y,z in profile]
        f=[tuple(reversed(range(n))),tuple(range(n,2*n))];colors=[(.90,.94,1),(.90,.94,1)]
        for i in range(n):j=(i+1)%n;f.append((i,j,n+j,n+i));colors.append((1.02,1.02,1.02) if i%2 else (.82,.89,.97))
        mesh(c['id']+' layered-gable',v,f,[c['material']]*len(f),colors,c['id'])

    def cone(c):
        lo,hi=c['boundsBlender']['min'],c['boundsBlender']['max'];cx=(lo[0]+hi[0])/2;cy=(lo[1]+hi[1])/2;rx=(hi[0]-lo[0])/2;ry=(hi[1]-lo[1])/2;z0=lo[2];h=hi[2]-z0
        profile=[(0,1),(.07,.94),(.10,.97),(.13,.87),(.42,.56),(.44,.59),(.48,.51),(.96,.02)]
        n=12;v=[]
        for z,r in profile:
            for i in range(n):a=math.tau*i/n;v.append((cx+math.cos(a)*rx*r,cy+math.sin(a)*ry*r,z0+z*h))
        apex=len(v);v.append((cx,cy,hi[2]));f=[tuple(reversed(range(n)))];colors=[(.75,.82,.92)]
        for ring in range(len(profile)-1):
            for i in range(n):j=(i+1)%n;f.append((ring*n+i,ring*n+j,(ring+1)*n+j,(ring+1)*n+i));colors.append((.86,.92,1) if ring%2 else (1.03,1.03,1.02))
        for i in range(n):f.append(((len(profile)-1)*n+i,(len(profile)-1)*n+(i+1)%n,apex));colors.append((1,1,1))
        mesh(c['id']+' tiered-roof',v,f,[c['material']]*len(f),colors,c['id'])

    for c in selected:
        if c['material']=='HLOD_Stone':facade(c)
        elif c['triangles']==8:gable(c)
        else:cone(c)
    bpy.context.view_layer.update()
    per_component={}
    for c in selected:
        objs=[o for o in parts if o['arrival_source_component']==c['id']]
        bounds=[o.matrix_world@v.co for o in objs for v in o.data.vertices]
        low=[min(p[a] for p in bounds) for a in range(3)];high=[max(p[a] for p in bounds) for a in range(3)]
        expected=c['boundsBlender']
        if max(abs(low[a]-expected['min'][a]) for a in range(3))>1e-4 or max(abs(high[a]-expected['max'][a]) for a in range(3))>1e-4:raise RuntimeError(c['id']+' envelope changed')
        tris=sum(len(o.data.polygons) for o in objs)
        per_component[c['id']]={'old_triangles':c['triangles'],'new_triangles':tris,'bounds':{'min':low,'max':high}}
    count=sum(p['new_triangles'] for p in per_component.values())
    if 21400-100+count>25000:raise RuntimeError('Candidate exceeds25ktris')
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:o.select_set(True)
    bpy.context.view_layer.objects.active=parts[0]
    bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',use_selection=True,export_yup=True,export_apply=True,export_materials='EXPORT',export_vertex_color='ACTIVE',export_animations=False,export_cameras=False,export_lights=False,export_extras=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    if sha(baseline)!=SHA:raise RuntimeError('Protected baseline changed')
    payload={'schema':'xexoria.arrival-architecture/1','status':'BLENDER_CPU_GEOMETRY_NOT_NATIVE_ART_PASS','source_sha256':SHA,'selected_ids':SELECTED,'removed_triangles':100,'new_architecture_triangles':count,'projected_triangles':21400-100+count,'per_component':per_component,'materials':'existing8names;targetedCOLOR_0;noimages','trees_created':0,'terrain_created_or_changed':0,'colliders_changed':0,'glb_sha256':sha(glb),'blender_version':bpy.app.version_string,'threads':6}
    receipt.write_text(json.dumps(payload,indent=2)+'\n');print(json.dumps(payload))
if __name__=='__main__':main()
