"""Stage 1a: the single 2048 atlas layout and the transfer bakes on the cleaned high mesh.

Layout: the Tripo Smart UV layout is kept (77 % fill, uniform 700 px/m at 2048). Only the face island and the hand
islands are enlarged (face x1.6, hands x1.3, smaller factors if needed) and moved into free space found with an FFT
occupancy search on a 1024 raster (12 px gaps at 2048); every other island stays exactly where Tripo put it. If an
enlarged island cannot be placed, smaller factors are tried, and finally the Tripo layout is used unchanged.

Bakes (Cycles CPU, on the high mesh itself, no cage):
- albedo   8K Tripo base colour through UV_tripo -> UV_atlas, 4096 (downsampled to 2048 by h02_textures.py)
- rm       Tripo metal/rough 4K -> 2048
- clothmask 1 on cloth faces, 0 on body faces (2048), so AO on double-sided cloth uses its more open side
- ao_front / ao_back  128 samples, 0.30 m, front-side and flipped-side hemispheres (2048)
Then the meshopt vertex/index arrays for h02_simplify.mjs are written from UV_atlas.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
import h02_common as C  # noqa: E402

log = C.Log("h02_atlas_bake")
bpy.ops.wm.open_mainfile(filepath=str(C.WORK / "h02_hiclean.blend"))
scn = bpy.context.scene
hi = bpy.data.objects["hero02_hiclean"]
me = hi.data
body = bpy.data.materials["hero02_witch_body"]
cloth = bpy.data.materials["hero02_witch_cloth"]
src_mat = bpy.data.materials["hero02_tripo_source"]
REG = ["head", "hat", "hands", "forearm", "upperarm", "torso", "hips", "thigh", "shin", "feet", "other", "face", "hair"]
if "UV_atlas" in me.uv_layers:
    me.uv_layers.remove(me.uv_layers["UV_atlas"])
me.uv_layers.active = me.uv_layers["UV_tripo"]
preg = np.array([me.attributes["xex_region"].data[i].value for i in range(len(me.polygons))])


def islands_of(layer_name):
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv[layer_name]
    fi = [-1] * len(bm.faces)
    n = 0
    for f in bm.faces:
        if fi[f.index] >= 0:
            continue
        fi[f.index] = n
        stack = [f]
        while stack:
            cur = stack.pop()
            for loop in cur.loops:
                e = loop.edge
                for of in e.link_faces:
                    if fi[of.index] >= 0:
                        continue
                    ok = True
                    for v in e.verts:
                        ua = next(l[uvl].uv for l in cur.loops if l.vert == v)
                        ub = next(l[uvl].uv for l in of.loops if l.vert == v)
                        if (ua - ub).length > 1e-6:
                            ok = False
                            break
                    if ok:
                        fi[of.index] = n
                        stack.append(of)
        n += 1
    bm.free()
    return np.array(fi), n


face_isl, n_isl = islands_of("UV_tripo")
isl_region = {}
for i in range(n_isl):
    regs = preg[face_isl == i]
    vals, cnt = np.unique(regs, return_counts=True)
    isl_region[i] = REG[int(vals[np.argmax(cnt)])]
log("islands", n_isl)


def raster_tris(uv_tris, res, grid=None):
    """Mark every texel whose centre lies inside a UV triangle (plus the vertex texels of thin triangles)."""
    if grid is None:
        grid = np.zeros((res, res), bool)
    for tri in uv_tris:
        t = tri * res
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, res - 1), min(y1, res - 1)
        for q in t:
            grid[min(max(int(q[1]), 0), res - 1), min(max(int(q[0]), 0), res - 1)] = True
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        a, b, c = t
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        w1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        w2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
        inside = (w1 >= 0) & (w2 >= 0) & (1 - w1 - w2 >= 0)
        grid[y0:y1 + 1, x0:x1 + 1][inside] = True
    return grid


def dilate(g, r):
    out = g.copy()
    H, W = g.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx == 0 and dy == 0:
                continue
            out[max(dy, 0):H + min(dy, 0), max(dx, 0):W + min(dx, 0)] |= \
                g[max(-dy, 0):H + min(-dy, 0), max(-dx, 0):W + min(-dx, 0)]
    return out


def find_spot(occ, mask, prefer):
    R = occ.shape[0]
    h, w = mask.shape
    if h >= R or w >= R:
        return None
    F = np.fft.rfft2(occ.astype(np.float32))
    K = np.zeros((R, R), np.float32)
    K[:h, :w] = mask
    corr = np.fft.irfft2(F * np.conj(np.fft.rfft2(K)), s=(R, R))
    valid = np.zeros((R, R), bool)
    valid[:R - h, :R - w] = corr[:R - h, :R - w] < 0.5
    ys, xs = np.nonzero(valid)
    if len(ys) == 0:
        return None
    k = int(np.argmin((ys - prefer[0]) ** 2 + (xs - prefer[1]) ** 2))
    return int(ys[k]), int(xs[k])


RES = 1024           # placement raster: 1 texel = 2 px of the 2048 atlas
MARGIN = 4           # dilation of the fixed islands (8 px at 2048) plus 2 on the moved island = 12 px gaps


def try_layout(factors):
    if "UV_atlas" in me.uv_layers:
        me.uv_layers.remove(me.uv_layers["UV_atlas"])
    me.uv_layers.active = me.uv_layers["UV_tripo"]
    atlas = me.uv_layers.new(name="UV_atlas", do_init=True)
    me.uv_layers.active = atlas
    luv = np.empty(len(me.loops) * 2)
    atlas.data.foreach_get("uv", luv)
    luv = luv.reshape(-1, 2)
    loops = np.array([list(p.loop_indices) for p in me.polygons], np.int64)
    moving = [i for i in range(n_isl) if factors.get(isl_region[i])]
    moving.sort(key=lambda i: -int((face_isl == i).sum()))
    fixed_faces = ~np.isin(face_isl, moving)
    occ = dilate(raster_tris(luv[loops[fixed_faces]], RES), MARGIN)
    placed = []
    for i in moving:
        fac = factors[isl_region[i]]
        fl = loops[face_isl == i]
        pts = luv[fl]
        cen = pts.reshape(-1, 2).mean(0)
        st = (pts - cen) * fac
        lo = st.reshape(-1, 2).min(0)
        st = st - lo + 2.0 / RES
        size = st.reshape(-1, 2).max(0) + 2.0 / RES
        h, w = int(np.ceil(size[1] * RES)) + 1, int(np.ceil(size[0] * RES)) + 1
        mk = dilate(raster_tris(st, max(h, w))[:h, :w], 2)
        prefer = (int((cen[1] + lo[1]) * RES), int((cen[0] + lo[0]) * RES))
        best = None
        for rot in range(4):
            mm = np.rot90(mk, rot)
            spot = find_spot(occ, mm, prefer)
            if spot is not None:
                best = (rot, spot, mm)
                break
        if best is None:
            return {"factors": factors, "ok": False, "failed_island": int(i), "placed": placed}
        rot, (y, x), mm = best
        occ[y:y + mm.shape[0], x:x + mm.shape[1]] |= mm
        Hm, Wm = h / RES, w / RES
        u, v = st[..., 0], st[..., 1]
        if rot == 0:
            nu, nv = u, v
        elif rot == 1:          # np.rot90 k=1: (row, col) -> (W - col, row)
            nu, nv = v, Wm - u
        elif rot == 2:
            nu, nv = Wm - u, Hm - v
        else:                   # k=3: (row, col) -> (col, H - row)
            nu, nv = Hm - v, u
        luv[fl] = np.stack([nu + x / RES, nv + y / RES], -1)
        placed.append({"island": int(i), "region": isl_region[i], "factor": fac, "rotation_deg": 90 * rot,
                       "texel_offset_1024": [x, y], "faces": int(len(fl))})
    atlas.data.foreach_set("uv", luv.ravel())
    me.update()
    allpts = luv[loops].reshape(-1, 2)
    ok = bool(allpts.min() >= 0 and allpts.max() <= 1)
    return {"factors": factors, "ok": ok, "placed": placed, "uv_min": allpts.min(0).round(4).tolist(),
            "uv_max": allpts.max(0).round(4).tolist()}


def density(layer):
    luv = np.empty(len(me.loops) * 2)
    me.uv_layers[layer].data.foreach_get("uv", luv)
    luv = luv.reshape(-1, 2)
    ua = np.zeros(len(me.polygons))
    a3 = np.zeros(len(me.polygons))
    for p in me.polygons:
        li = list(p.loop_indices)
        a, b, c = luv[li[0]], luv[li[1]], luv[li[2]]
        ua[p.index] = abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) * 0.5
        a3[p.index] = p.area
    out = {"uv_fill": round(float(ua.sum()), 4),
           "average_px_per_m_2048": round(float(math.sqrt(ua.sum() * 2048 ** 2 / a3.sum())), 1)}
    for r in range(len(REG)):
        m = preg == r
        if m.any():
            out[REG[r]] = round(float(math.sqrt(ua[m].sum() * 2048 ** 2 / max(a3[m].sum(), 1e-9))), 1)
    return out


attempts = []
chosen = None
for factors in ({"face": 1.6, "hands": 1.3}, {"face": 1.5, "hands": 1.2}, {"face": 1.4, "hands": 1.15},
                {"face": 1.3}, {"face": 1.2}):
    res = try_layout(factors)
    attempts.append(res)
    log("layout attempt", {k: v for k, v in res.items() if k != "placed"}, "placed", len(res.get("placed", [])))
    if res["ok"]:
        chosen = factors
        break
if chosen is None:
    if "UV_atlas" in me.uv_layers:
        me.uv_layers.remove(me.uv_layers["UV_atlas"])
    me.uv_layers.active = me.uv_layers["UV_tripo"]
    atlas = me.uv_layers.new(name="UV_atlas", do_init=True)
    chosen = {}
    log("fallback: Tripo layout unchanged")
me.uv_layers.active = me.uv_layers["UV_atlas"]
dens = {"UV_tripo": density("UV_tripo"), "UV_atlas": density("UV_atlas")}
log("density", dens)
# ------------------------------------------------------------------------------------------------ bakes
def new_image(name, size, colorspace):
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    return img


def emission_material(mat, source_image, target_image, constant=None):
    if mat is src_mat:
        return add_target_node(mat, target_image)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emi = nt.nodes.new("ShaderNodeEmission")
    if constant is not None:
        emi.inputs["Color"].default_value = (constant, constant, constant, 1)
    else:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = source_image
        tex.interpolation = "Cubic"
        uvn = nt.nodes.new("ShaderNodeUVMap")
        uvn.uv_map = "UV_tripo"
        nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], emi.inputs["Color"])
    nt.links.new(emi.outputs[0], out.inputs["Surface"])
    tgt = nt.nodes.new("ShaderNodeTexImage")
    tgt.image = target_image
    nt.nodes.active = tgt


def add_target_node(mat, target_image):
    """The unused source slot only needs an active target node; its texture nodes stay for the normal bake."""
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.name.startswith("xex_bake_target"):
            nt.nodes.remove(n)
    t = nt.nodes.new("ShaderNodeTexImage")
    t.name = "xex_bake_target"
    t.image = target_image
    nt.nodes.active = t


def ao_material(mat, target_image):
    if mat is src_mat:
        return add_target_node(mat, target_image)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    nt.links.new(dif.outputs[0], out.inputs["Surface"])
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = target_image
    nt.nodes.active = t


def save_png(img, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    return path


def bake(kind, margin):
    bpy.ops.object.bake(type=kind, margin=margin, margin_type="EXTEND", use_clear=True, uv_layer="UV_atlas",
                        target="IMAGE_TEXTURES", use_selected_to_active=False)


scn.render.engine = "CYCLES"
scn.cycles.device = "CPU"
scn.cycles.use_denoising = False
for o in scn.objects:
    o.select_set(o is hi)
bpy.context.view_layer.objects.active = hi
base8k = next(i for i in bpy.data.images if "basecolor" in i.name)
rm4k = next(i for i in bpy.data.images if "_rm" in i.name)
for img in bpy.data.images:
    if "hero02_mage_p20" in img.name:
        img.use_fake_user = True
base8k.colorspace_settings.name = "sRGB"
rm4k.colorspace_settings.name = "Non-Color"
report = {"layout_attempts": attempts, "chosen_factors": chosen, "density": dens, "bakes": {}}
for name, src_img, cs, size, samples, margin in (("albedo", base8k, "sRGB", 4096, 4, 32),
                                                 ("rm", rm4k, "Non-Color", 2048, 4, 16)):
    tgt = new_image(f"h02_{name}_bake", size, cs)
    for mat in (body, cloth, src_mat):
        emission_material(mat, src_img, tgt)
    scn.cycles.samples = samples
    bake("EMIT", margin)
    p = save_png(tgt, C.WORK / "bake" / f"h02_{name}_{size}.png")
    report["bakes"][name] = {"file": C.rel(p), "size": size, "samples": samples}
    log("baked", name)
tgt = new_image("h02_clothmask_bake", 2048, "Non-Color")
emission_material(body, None, tgt, constant=0.0)
emission_material(cloth, None, tgt, constant=1.0)
emission_material(src_mat, None, tgt, constant=0.0)
scn.cycles.samples = 1
bake("EMIT", 16)
p = save_png(tgt, C.WORK / "bake" / "h02_clothmask_2048.png")
report["bakes"]["clothmask"] = {"file": C.rel(p), "size": 2048}
if scn.world is None:
    scn.world = bpy.data.worlds.new("bake_world")
scn.world.light_settings.distance = 0.30
scn.cycles.samples = 128
for side in ("front", "back"):
    if side == "back":
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.to_mesh(me)
        bm.free()
        me.update()
    tgt = new_image(f"h02_ao_{side}_bake", 2048, "Non-Color")
    for mat in (body, cloth, src_mat):
        ao_material(mat, tgt)
    bake("AO", 16)
    p = save_png(tgt, C.WORK / "bake" / f"h02_ao_{side}_2048.png")
    report["bakes"][f"ao_{side}"] = {"file": C.rel(p), "size": 2048, "samples": 128, "distance_m": 0.30}
    log("baked AO", side)
    if side == "back":
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.to_mesh(me)
        bm.free()
        me.update()
for n in list(src_mat.node_tree.nodes):
    if n.name.startswith("xex_bake_target"):
        src_mat.node_tree.nodes.remove(n)
for mat in (body, cloth):
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    o_ = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    b_ = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    mat.node_tree.links.new(b_.outputs[0], o_.inputs["Surface"])

# ------------------------------------------------------------------------------------------------ meshopt arrays
nverts = len(me.vertices)
vco = np.empty(nverts * 3, np.float32)
me.vertices.foreach_get("co", vco)
vco = vco.reshape(-1, 3)
vno = np.empty(nverts * 3, np.float32)
me.vertices.foreach_get("normal", vno)
vno = vno.reshape(-1, 3)
luv = np.empty(len(me.loops) * 2, np.float32)
me.uv_layers["UV_atlas"].data.foreach_get("uv", luv)
luv = luv.reshape(-1, 2)
lvi = np.empty(len(me.loops), np.int64)
me.loops.foreach_get("vertex_index", lvi)
pmat = np.empty(len(me.polygons), np.int64)
me.polygons.foreach_get("material_index", pmat)
protect_by_region = {"face": 1.0, "hands": 0.7, "head": 0.4, "hair": 0.35, "hat": 0.2}
vprot = np.zeros(nverts, np.float32)
for p in me.polygons:
    w = protect_by_region.get(REG[preg[p.index]], 0.0)
    for vi in p.vertices:
        vprot[vi] = max(vprot[vi], w)
key_to_u = {}
u_vert, u_uv, u_mat, tri = [], [], [], []
for p in me.polygons:
    t = []
    for li in p.loop_indices:
        vi = int(lvi[li])
        k = (vi, round(float(luv[li, 0]), 6), round(float(luv[li, 1]), 6), int(pmat[p.index]))
        u = key_to_u.get(k)
        if u is None:
            u = len(u_vert)
            key_to_u[k] = u
            u_vert.append(vi)
            u_uv.append((luv[li, 0], luv[li, 1]))
            u_mat.append(pmat[p.index])
        t.append(u)
    tri.append(t)
u_vert = np.array(u_vert, np.uint32)
out_dir = C.WORK / "meshopt"
out_dir.mkdir(parents=True, exist_ok=True)
vco[u_vert].tofile(out_dir / "positions.f32")
vno[u_vert].tofile(out_dir / "normals.f32")
np.array(u_uv, np.float32).tofile(out_dir / "uvs.f32")
np.array(u_mat, np.float32).tofile(out_dir / "material.f32")
vprot[u_vert].tofile(out_dir / "protect.f32")
u_vert.tofile(out_dir / "orig_vertex.u32")
np.array(tri, np.uint32).tofile(out_dir / "indices.u32")
C.write_json(out_dir / "meta.json", {"vertices": int(len(u_vert)), "triangles": len(tri), "orig_vertices": nverts,
                                     "materials": ["hero02_witch_body", "hero02_witch_cloth"],
                                     "protect_by_region": protect_by_region, "uv_layer": "UV_atlas"})
log("meshopt arrays: corners", len(u_vert), "triangles", len(tri))
bpy.ops.wm.save_as_mainfile(filepath=str(C.WORK / "h02_hiclean.blend"), compress=True)
C.write_json(C.REPORTS / "atlas_bake.json", report)
log("saved")
