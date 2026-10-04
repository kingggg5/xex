"""Hero 02 staff: an equipable weapon GLB source (decisions section 6; rig doc section 3.4).

--phase prep : import the verified Tripo staff copy, scale to 2.270 m, grip centre at the origin, shaft along
               Blender +Z (glTF/Babylon +Y), weld, sharp edges above 40 deg, AO bake on the high mesh, meshopt arrays.
--phase lods : rebuild LOD0/1 from work/staff_meshopt/lod*.indices.u32 (h02_simplify.mjs), bake tangent normals
               high -> each LOD, build the material (albedo 1024, ORM 1024, emissive crystal 512) and the markers
               fx_base (gold collar under the crystal), fx_tip (crystal tip), fx_head (crystal centre) and
               grip_r (origin) and grip_l (0.23 m below the right-hand grip); save work/h02_staff.blend.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
import h02_common as C  # noqa: E402

log = C.Log("h02_staff")
args = C.script_args()
phase = args[args.index("--phase") + 1] if "--phase" in args else "prep"
LENGTH = 2.270
GRIP_U = (2.270 - 1.40) / 2.270          # grip height along the source staff (units, 0 = butt, 0.9995 = crystal tip)
SECOND_U = 0.39         # left-hand grip
OUT = C.WORK / "staff_meshopt"
OUT.mkdir(parents=True, exist_ok=True)
TEX = C.WORK / "tex"
TEX.mkdir(parents=True, exist_ok=True)


def staff_metrics():
    s = LENGTH / 0.9995
    return s


if phase == "prep":
    C.verify_sources([C.SRC_STAFF])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(C.SRC_STAFF), merge_vertices=False, import_shading="NORMALS")
    objs = [o for o in bpy.data.objects if o not in before]
    st = next(o for o in objs if o.type == "MESH")
    mw = st.matrix_world.copy()
    st.parent = None
    st.matrix_world = Matrix.Identity(4)
    st.data.transform(mw)
    for o in objs:
        if o is not st:
            bpy.data.objects.remove(o, do_unlink=True)
    me = st.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    zmin, zmax = co[:, 2].min(), co[:, 2].max()
    shaft = co[(co[:, 2] > zmin + 0.40 * (zmax - zmin)) & (co[:, 2] < zmin + 0.60 * (zmax - zmin))]
    r = np.hypot(shaft[:, 0] - np.median(shaft[:, 0]), shaft[:, 1] - np.median(shaft[:, 1]))
    core = shaft[r < np.percentile(r, 40)]
    cx, cy = float(np.median(core[:, 0])), float(np.median(core[:, 1]))
    s = LENGTH / (zmax - zmin)
    grip_z = zmin + GRIP_U * (zmax - zmin)
    me.transform(Matrix.Diagonal((s, s, s, 1)) @ Matrix.Translation((-cx, -cy, -grip_z)))
    me.update()
    st.name = "hero02_staff"
    me.name = "hero02_staff_high"
    for img in bpy.data.images:
        if img.packed_file is None and img.source == "FILE":
            img.pack()
        img.use_fake_user = True
    with bpy.context.temp_override(object=st, active_object=st, selected_objects=[st]):
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=5e-6)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(40))
    me.update()
    me.uv_layers[0].name = "UV_staff"
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    rr = np.hypot(co[:, 0], co[:, 1])
    log("staff metres: z", co[:, 2].min().round(4), co[:, 2].max().round(4), "max radius", rr.max().round(4),
        "shaft radius at grip", float(np.percentile(rr[np.abs(co[:, 2]) < 0.03], 50)).__round__(4),
        "verts", len(me.vertices), "tris", len(me.polygons))
    # AO on the high staff (front side only: a closed rigid prop)
    mat = me.materials[0]
    mat.name = "hero02_staff_source"
    ao = bpy.data.images.new("hero02_staff_ao", 1024, 1024, alpha=False)
    ao.colorspace_settings.name = "Non-Color"
    nt = mat.node_tree
    tnode = nt.nodes.new("ShaderNodeTexImage")
    tnode.name = "xex_bake_target"
    tnode.image = ao
    nt.nodes.active = tnode
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.render.threads_mode = "FIXED"
    scn.render.threads = 6
    scn.cycles.samples = 96
    scn.world = bpy.data.worlds.new("w")
    scn.world.light_settings.distance = 0.12
    st.select_set(True)
    bpy.context.view_layer.objects.active = st
    bpy.ops.object.bake(type="AO", margin=8, margin_type="EXTEND", use_clear=True, uv_layer="UV_staff",
                        target="IMAGE_TEXTURES")
    ao.filepath_raw = str(TEX / "hero02_staff_ao_1024.png")
    ao.file_format = "PNG"
    ao.save()
    nt.nodes.remove(tnode)
    # meshopt arrays: unique (vertex, uv, corner normal) corners; sharp edges split the normals
    me.calc_loop_triangles()
    nv = len(me.vertices)
    vco = np.empty(nv * 3, np.float32)
    me.vertices.foreach_get("co", vco)
    vco = vco.reshape(-1, 3)
    cn = np.empty(len(me.loops) * 3, np.float32)
    me.corner_normals.foreach_get("vector", cn)
    cn = cn.reshape(-1, 3)
    luv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers["UV_staff"].data.foreach_get("uv", luv)
    luv = luv.reshape(-1, 2)
    lvi = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lvi)
    key_to_u = {}
    u_vert, u_uv, u_n, tri = [], [], [], []
    for lt in me.loop_triangles:
        t = []
        for li in lt.loops:
            vi = int(lvi[li])
            k = (vi, round(float(luv[li, 0]), 6), round(float(luv[li, 1]), 6),
                 round(float(cn[li, 0]), 3), round(float(cn[li, 1]), 3), round(float(cn[li, 2]), 3))
            u = key_to_u.get(k)
            if u is None:
                u = len(u_vert)
                key_to_u[k] = u
                u_vert.append(vi)
                u_uv.append(luv[li])
                u_n.append(cn[li])
            t.append(u)
        tri.append(t)
    u_vert = np.array(u_vert, np.uint32)
    vco[u_vert].tofile(OUT / "positions.f32")
    np.array(u_n, np.float32).tofile(OUT / "normals.f32")
    np.array(u_uv, np.float32).tofile(OUT / "uvs.f32")
    np.zeros(len(u_vert), np.float32).tofile(OUT / "material.f32")
    # protect the crystal head silhouette a little
    np.where(vco[u_vert][:, 2] > 0.20, 0.3, 0.0).astype(np.float32).tofile(OUT / "protect.f32")
    u_vert.tofile(OUT / "orig_vertex.u32")
    np.array(tri, np.uint32).tofile(OUT / "indices.u32")
    C.write_json(OUT / "meta.json", {"vertices": int(len(u_vert)), "triangles": len(tri), "length_m": LENGTH,
                                     "grip_fraction": GRIP_U, "scale": s})
    bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK / "h02_staff_high.blend"), compress=True)
    log("prep saved; corners", len(u_vert), "triangles", len(tri))

else:
    bpy.ops.wm.open_mainfile(filepath=str(C.WORK / "h02_staff_high.blend"))
    scn = bpy.context.scene
    hi = bpy.data.objects["hero02_staff"]
    hi.name = "hero02_staff_highsrc"
    me = hi.data
    # Resume the immutable completed high mesh without rebaking unrelated body stages.
    # Its prior 1.70 m frame is normalized to the shared 2.270 m staff frame.
    zlo = min(v.co.z for v in me.vertices)
    zhi = max(v.co.z for v in me.vertices)
    scale = LENGTH / (zhi - zlo)
    me.transform(Matrix.Translation((0, 0, -0.870)) @ Matrix.Diagonal((scale, scale, scale, 1)) @ Matrix.Translation((0, 0, -zlo)))
    me.update()
    nv = len(me.vertices)
    co = np.empty(nv * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    orig = np.fromfile(OUT / "orig_vertex.u32", np.uint32)
    uvs = np.fromfile(OUT / "uvs.f32", np.float32).reshape(-1, 2)
    nrm = np.fromfile(OUT / "normals.f32", np.float32).reshape(-1, 3)
    srcmat = bpy.data.materials["hero02_staff_source"]
    base = next(i for i in bpy.data.images if i.name.startswith("tripo_image"))
    rmimg = next(i for i in bpy.data.images if "metallic" in i.name or "roughness" in i.name)
    nimg = next(i for i in bpy.data.images if i.name.startswith("tripo_normal"))
    base.colorspace_settings.name = "sRGB"
    rmimg.colorspace_settings.name = "Non-Color"
    nimg.colorspace_settings.name = "Non-Color"
    lods = {}
    for L in (0, 1):
        idx = np.fromfile(OUT / f"lod{L}.indices.u32", np.uint32).reshape(-1, 3)
        if len(idx) == 0:
            raise RuntimeError(f"Staff LOD{L} has no triangles; refusing to bake/export")
        ov = orig[idx]
        keep = (ov[:, 0] != ov[:, 1]) & (ov[:, 1] != ov[:, 2]) & (ov[:, 0] != ov[:, 2])
        idx, ov = idx[keep], ov[keep]
        used = np.unique(ov)
        remap = {int(o): k for k, o in enumerate(used)}
        faces = [[remap[int(a)], remap[int(b)], remap[int(c)]] for a, b, c in ov]
        m = bpy.data.meshes.new(f"hero02_staff_lod{L}")
        m.from_pydata([tuple(co[int(o)]) for o in used], [], faces)
        m.update()
        m.uv_layers.new(name="UV_staff").data.foreach_set("uv", uvs[idx].reshape(-1, 2).ravel())
        m.shade_smooth()
        m.normals_split_custom_set(nrm[idx].reshape(-1, 3).tolist())
        o = bpy.data.objects.new(f"hero02_staff_lod{L}", m)
        scn.collection.objects.link(o)
        lods[L] = o
        log(f"staff LOD{L}", len(faces), "triangles")
    scn.render.engine = "CYCLES"
    scn.cycles.device = "CPU"
    scn.render.threads_mode = "FIXED"
    scn.render.threads = 6
    scn.cycles.samples = 8
    sizes = {0: 1024, 1: 512, 2: 256}
    for L, o in lods.items():
        img = bpy.data.images.new(f"hero02_staff_normal_lod{L}", sizes[L], sizes[L], alpha=False)
        img.colorspace_settings.name = "Non-Color"
        tmp = bpy.data.materials.new(f"tmp_staff_{L}")
        tmp.use_nodes = True
        tn = tmp.node_tree.nodes.new("ShaderNodeTexImage")
        tn.image = img
        tmp.node_tree.nodes.active = tn
        o.data.materials.clear()
        o.data.materials.append(tmp)
        for ob in scn.objects:
            ob.select_set(False)
        hi.select_set(True)
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", use_selected_to_active=True,
                            cage_extrusion=0.006 * (L + 1), max_ray_distance=0.02 * (L + 1), margin=4,
                            margin_type="EXTEND", use_clear=True, uv_layer="UV_staff", target="IMAGE_TEXTURES")
        img.filepath_raw = str(TEX / f"hero02_staff_normal_lod{L}.png")
        img.file_format = "PNG"
        img.save()
        bpy.data.materials.remove(tmp)
        log("baked staff normal", L)
    # final material: albedo / ORM / emissive written by h02_textures_staff (system python) -> loaded here
    import subprocess  # noqa: F401  (textures are made beforehand; see run order in the doc)
    alb = bpy.data.images.load(str(TEX / "hero02_staff_albedo.png"))
    alb.colorspace_settings.name = "sRGB"
    ormi = bpy.data.images.load(str(TEX / "hero02_staff_orm.png"))
    ormi.colorspace_settings.name = "Non-Color"
    emi = bpy.data.images.load(str(TEX / "hero02_staff_emissive.png"))
    emi.colorspace_settings.name = "sRGB"
    g = bpy.data.node_groups.get("glTF Material Output")
    if g is None:
        g = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        g.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        g.interface.new_socket("Thickness", in_out="INPUT", socket_type="NodeSocketFloat")
    for L, o in lods.items():
        sfx = "" if L == 0 else f"_lod{L}"
        mat = bpy.data.materials.new(f"hero02_staff{sfx}")
        mat["xex_double_sided"] = False
        mat.use_backface_culling = True
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
        ta = nt.nodes.new("ShaderNodeTexImage")
        ta.image = alb
        nt.links.new(ta.outputs["Color"], bsdf.inputs["Base Color"])
        to = nt.nodes.new("ShaderNodeTexImage")
        to.image = ormi
        sp = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(to.outputs["Color"], sp.inputs["Color"])
        nt.links.new(sp.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sp.outputs["Blue"], bsdf.inputs["Metallic"])
        gn = nt.nodes.new("ShaderNodeGroup")
        gn.node_tree = g
        nt.links.new(sp.outputs["Red"], gn.inputs["Occlusion"])
        te = nt.nodes.new("ShaderNodeTexImage")
        te.image = emi
        nt.links.new(te.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 1.0
        nimg_l = bpy.data.images.load(str(TEX / f"hero02_staff_normal_lod{L}.png"), check_existing=True)
        nimg_l.colorspace_settings.name = "Non-Color"
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = nimg_l
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.uv_map = "UV_staff"
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        o.data.materials.clear()
        o.data.materials.append(mat)
    # markers (positions in metres; grip at the origin, shaft along +Z)
    s = LENGTH / 0.9995
    zs = co[:, 2]
    rr = np.hypot(co[:, 0], co[:, 1])
    tip_z = float(zs.max())
    head_pts = co[zs > (0.80 - GRIP_U) * s]
    crystal_c = head_pts.mean(0)
    collar_z = (0.68 - GRIP_U) * s
    marks = {"grip_r": (0.0, 0.0, 0.0), "grip_l": (0.0, 0.0, -0.23),
             "fx_base": (0.0, 0.0, 0.25), "fx_tip": (0.0, 0.0, 1.40),
             "fx_head": (float(crystal_c[0]), float(crystal_c[1]), float(crystal_c[2]))}
    for L, o in lods.items():
        for name, pos in marks.items():
            e = bpy.data.objects.new(name if L == 0 else f"{name}.lod{L}", None)
            e.empty_display_type = "ARROWS"
            e.empty_display_size = 0.05
            scn.collection.objects.link(e)
            e.parent = o
            e.location = pos
            e["xex_marker"] = name
    hi.hide_render = True
    hi.hide_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK / "h02_staff.blend"), compress=True)
    C.write_json(C.REPORTS / "staff.json", {"length_m": LENGTH, "grip_fraction": GRIP_U, "markers_m": marks,
                                            "lods": {L: len(o.data.polygons) for L, o in lods.items()}})
    log("saved staff blend", marks)
