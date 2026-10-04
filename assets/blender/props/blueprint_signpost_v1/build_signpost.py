"""ST8 original signpost, versioned candidate only; shared immutable craft maps."""
from pathlib import Path
import argparse, hashlib, json, math, sys, time
import bpy, bmesh, numpy as np
from mathutils import Vector
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'assets/blender/nature_props'))
import np_lib as L
import np_review as R
from np_craft_texture import uv_rect
OUT=ROOT/'assets/models/props/blueprint-signpost-v1-candidate'
EVID=ROOT/'planning/evidence/blueprint-semantic-props-20261003'
TEX=ROOT/'assets/models/sunmeadow-props/craft/textures-source'
GUARDIAN=ROOT/'assets/models/reference-city/r5/art-candidates/fountain-guardian-v2/fountain_guardian_v2.blend'
ATLAS=2048; DENSITY=360

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def uv_project(ob,tile='wood'):
    while ob.data.uv_layers:ob.data.uv_layers.remove(ob.data.uv_layers[0])
    uv=ob.data.uv_layers.new(name='UVMap');u0,v0,du,dv=uv_rect(tile)
    for face in ob.data.polygons:
        normal=face.normal;axis=int(np.argmin(np.abs(normal)))
        direction=Vector(tuple(1 if i==axis else 0 for i in range(3)))
        U=(direction-normal*direction.dot(normal)).normalized();V=normal.cross(U).normalized()
        points=np.array([(ob.data.vertices[ob.data.loops[li].vertex_index].co.dot(U),ob.data.vertices[ob.data.loops[li].vertex_index].co.dot(V)) for li in face.loop_indices]);points-=points.min(0)
        if np.max(points[:,0])*DENSITY/ATLAS>du or np.max(points[:,1])*DENSITY/ATLAS>dv:raise ValueError('Face exceeds craft tile; add a real UV face subdivision')
        for row,li in zip(points,face.loop_indices):uv.data[li].uv=(u0+row[0]*DENSITY/ATLAS,v0+row[1]*DENSITY/ATLAS)

def finish(ob,mat,bevel=0,tile='wood'):
    L.apply_transform(ob)
    if bevel:L.bevel(ob,bevel,segments=1)
    bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free();ob.data.update()
    uv_project(ob,tile);ob.data.materials.clear();ob.data.materials.append(mat)
    if bevel:
        for poly in ob.data.polygons:poly.use_smooth=True
        mod=ob.modifiers.new('craft area weighted normals','WEIGHTED_NORMAL');mod.keep_sharp=True;mod.weight=40;L.apply_modifiers(ob)
    L.triangulate(ob)
    return ob

def post():
    # Split coplanar side faces at half-height: consistent density without crossing atlas tiles.
    verts=[(x,y,z) for z in (0,1.1,2.2) for x,y in ((-.075,-.075),(.075,-.075),(.075,.075),(-.075,.075))]
    faces=[[3,2,1,0],[8,9,10,11]]
    for r in (0,4):
        for i in range(4):j=(i+1)%4;faces.append([r+i,r+j,r+j+4,r+i+4])
    return L.mesh_from_arrays('grounded_full_height_post',verts,faces)

def arrow(name,center_x,height,direction=1):
    section=[(-.55,-.11),(.25,-.11),(.25,-.19),(.55,0),(.25,.19),(.25,.11),(-.55,.11)]
    verts=[(center_x+direction*x,y,height+z) for y in (-.175,-.075) for x,z in section]
    n=len(section);faces=[list(range(n-1,-1,-1)),list(range(n,2*n))]
    faces.extend([[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)])
    return L.mesh_from_arrays(name,verts,faces)

def build(lod,mat):
    bevel=.012 if lod==0 else 0
    parts=[finish(post(),mat,bevel)]
    parts.extend([finish(arrow('joined_arrow_lower_right',.25,1.5,1),mat,bevel),finish(arrow('joined_arrow_upper_left',-.25,1.9,-1),mat,bevel)])
    if lod<2:
        for z in (1.5,1.9):
            for x in ((-.045,.045) if lod==0 else (0,)):
                bpy.ops.mesh.primitive_cylinder_add(vertices=8 if lod==0 else 4,radius=.024,depth=.255,location=(x,-.065,z),rotation=(math.pi/2,0,0))
                peg=bpy.context.object;peg.name='visible_timber_joint_peg';parts.append(finish(peg,mat))
    ob=L.join(parts,f'sm_blueprint_signpost_lod{lod}');report=L.mesh_report(ob)
    if report['non_manifold_edges'] or report['zero_area_faces']:raise ValueError(f'Invalid closed signpost: {report}')
    if report['triangles']>[800,400,140][lod]:raise ValueError(f'LOD{lod} budget: {report}')
    return ob,report

def density(ob):
    layer=ob.data.uv_layers[0];values=[];area=0
    for face in ob.data.polygons:
        li=list(face.loop_indices);a,b,c=[layer.data[i].uv for i in li];uv_area=abs((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x))/2
        value=math.sqrt(uv_area/face.area)*ATLAS;values.append(value);area+=face.area
    return {'min':min(values),'median':float(np.median(values)),'max':max(values),'triangles':len(values),'area_m2':area,'target_px_m':DENSITY}

def guardian_audit(ev):
    # Read-only feasibility check; no anatomy or source master alteration.
    with bpy.data.libraries.load(str(GUARDIAN),link=False) as (data_from,data_to):
        data_to.objects=[name for name in data_from.objects if 'anatomy' in name.lower()]
    records=[]
    for ob in data_to.objects:
        if ob is None or ob.type!='MESH':continue
        points=np.array([tuple(ob.matrix_world@v.co) for v in ob.data.vertices]);records.append({'name':ob.name,'triangles':L.tri_count(ob),'bounds_min':points.min(0).tolist(),'bounds_max':points.max(0).tolist(),'vertex_groups':[g.name for g in ob.vertex_groups],'vertices_above_5_9m':int(sum(points[:,2]>5.9))})
        bpy.data.objects.remove(ob,do_unlink=True)
    L.write_json(ev/'guardian-head-feasibility.json',{'source':str(GUARDIAN.relative_to(ROOT)),'sha256':sha(GUARDIAN),'objects':records,'status':'INSPECTED_ONLY_HEAD_NOT_CREATED'})

def review(ob,ev):
    R.setup_render((900,600),12,6);R.setup_world(.60);sun=R.add_sun(225,48,3.0);ground=R.ground_plane('sand',16,(0,0));ground.location.z=-.001;witness=R.witness((-1.15,.3));views=[]
    for name,loc,target,fov in [('game',(0,-12.01,6.60),(0,0,1.65),1.02),('front',(0,-4.5,2.7),(0,0,1.15),.78),('side',(3,-2.3,2.1),(0,0,1.2),.78)]:
        cam=R.camera(name,loc,target,fov_y=fov);bpy.context.scene.camera=cam;p=ev/f'BLENDER_REVIEW_signpost_{name}.png';seconds=R.render(p);views.append({'view':name,'path':str(p.relative_to(ROOT)),'seconds':seconds,'witness_m':1.8,'label':'BLENDER REVIEW'})
        L.delete([cam])
    L.write_json(ev/'source-views.json',{'views':views,'render':{'CPU_threads':6,'samples':12,'resolution':[900,600]}});L.delete([sun,ground,witness])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,default=1);ap.add_argument('--export-saved',action='store_true');args=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);rev=f'r{args.revision:02d}';out=OUT/rev;ev=EVID/'signpost'/rev;blend=HERE/'sources'/f'sm_blueprint_signpost_{rev}.blend'
    for path in (out/'source',ev,blend.parent):path.mkdir(parents=True,exist_ok=True)
    if args.export_saved:
        bpy.ops.wm.open_mainfile(filepath=str(blend))
        for suffix in ('lod0','lod1','lod2','collider','shadow_proxy'):
            ob=bpy.data.objects[f'sm_blueprint_signpost_{suffix}'];p=out/'source'/f'{ob.name}.glb'
            if p.exists():raise ValueError('Immutable export exists')
            rec=L.export_lod(ob,p,texture_dir=out/'source/textures',materials='EXPORT' if suffix.startswith('lod') else 'NONE',vertex_color='NONE',notes='ST8 original signpost candidate; one existing craft atlas; no live promotion')
            if rec['status']!='PASS':raise ValueError('Export validation failed')
        return
    if blend.exists():raise ValueError('Immutable source exists; use a new revision')
    L.reset();L.setup_cycles(12,6);mat=L.pbr_material('sm_craft_timber',TEX/'sm_craft_albedo.png',TEX/'sm_craft_normal.png',TEX/'sm_craft_orm.png',normal_strength=.3)
    lods=[];reports={}
    for i in range(3):
        ob,report=build(i,mat);report['uv_density']=density(ob);lods.append(ob);reports[f'lod{i}']=report;ob.hide_render=i>0;ob.hide_set(i>0)
    col=L.box_object('sm_blueprint_signpost_collider',(.2,.2,2.2),(0,0,1.1));L.triangulate(col);col.hide_render=True;col.hide_set(True)
    proxy=L.join([L.box_object('shadow_pole',(.15,.15,2.2),(0,0,1.1)),arrow('shadow_lower',.25,1.5,1),arrow('shadow_upper',-.25,1.9,-1)],'sm_blueprint_signpost_shadow_proxy');L.triangulate(proxy);proxy.hide_render=True;proxy.hide_set(True)
    metadata={'schema':'xexoria.blueprint-signpost-candidate/1','revision':rev,'status':'SOURCE_CANDIDATE_NOT_PROMOTED','asset_id':'sm_blueprint_signpost','slots':['sm_craft_timber'],'atlas_family':'sm_craft','atlas_sources':[{ 'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in (TEX/'sm_craft_albedo.png',TEX/'sm_craft_normal.png',TEX/'sm_craft_orm.png')],'units':'metres','pivot':[0,0,0],'body_height_m':2.2,'arrow_centres_y':[1.5,1.9],'front':'Blender -Y / Babylon +Z','arrow_directions_local_x':[1,-1],'labels':'none; readable route labels are data/HTML later, no baked glyphs','lods':reports,'collider':{'type':'pole box','min':[-.1,0,-.1],'max':[.1,2.2,.1],'admission':'UNVERIFIED_ROOT_OWNS_PLACEMENT'},'shadow_proxy_triangles':L.tri_count(proxy),'expected_instances':4,'native_import':'UNVERIFIED'}
    L.write_json(out/'candidate.json',metadata);L.write_json(ev/'source-receipt.json',metadata);guardian_audit(ev);bpy.ops.wm.save_as_mainfile(filepath=str(blend),compress=True);review(lods[0],ev)
    print('SIGNPOST_SOURCE_PASS',rev,[reports[f'lod{i}']['triangles'] for i in range(3)],flush=True)

if __name__=='__main__':main()
