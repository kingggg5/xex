"""Tests for export_helper.py. Run under Blender 5.2 headless (one Blender process at a time):

    & $env:BLENDER_BIN --background --factory-startup --python-exit-code 1 `
        --python assets/blender/tools/test_export_helper.py

Exit code 0 = every test passed; 1 = a failure (the script raises after printing the unittest summary).
The option-completeness tests read the installed exporter RNA, so a Blender or add-on upgrade that adds, removes or
renames an option fails here until the helper classifies it.
"""
from __future__ import annotations

import json
import shutil
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_helper as H  # noqa: E402


class OptionCompleteness(unittest.TestCase):
    """Every option of the installed glTF exporter is either set explicitly or defaulted on purpose."""

    def test_every_exporter_option_is_set_or_defaulted_on_purpose(self):
        props = H.exporter_rna()
        self.assertGreaterEqual(len(props), 100, "unexpectedly small exporter RNA")
        for name in H.PROFILES:
            opts = H.resolve_export_options(name)
            missing = sorted(set(props) - set(opts) - set(H.DEFAULTED_ON_PURPOSE))
            unknown = sorted(set(opts) - set(props))
            self.assertEqual(missing, [], f"{name}: exporter options neither set nor defaulted on purpose")
            self.assertEqual(unknown, [], f"{name}: options unknown to the installed exporter")
            self.assertEqual(H.check_options(opts, props, H.DEFAULTED_ON_PURPOSE), [], f"{name}: invalid values")

    def test_defaulted_on_purpose_options_exist_and_are_inert(self):
        props = H.exporter_rna()
        self.assertEqual(sorted(H.DEFAULTED_ON_PURPOSE), ["filter_glob", "gltf_export_id", "ui_tab"])
        for key in H.DEFAULTED_ON_PURPOSE:
            self.assertIn(key, props)
        self.assertTrue(set(H.PER_CALL_OPTIONS) <= set(props))

    def test_importer_options_complete(self):
        props = H.importer_rna()
        opts = dict(H.IMPORT_OPTIONS, filepath="")
        self.assertEqual(H.check_options(opts, props, H.IMPORT_DEFAULTED_ON_PURPOSE), [])

    def test_never_khr_meshopt_draco_or_gltfpack(self):
        for name in H.PROFILES:
            o = H.resolve_export_options(name)
            self.assertIs(o["export_meshopt_compression_enable"], False)
            self.assertEqual(o["export_meshopt_extension"], "EXT_meshopt_compression")
            self.assertIs(o["export_draco_mesh_compression_enable"], False)
            self.assertIs(o["export_use_gltfpack"], False)

    def test_profile_policies(self):
        for name, prof in H.PROFILES.items():
            o = H.resolve_export_options(name)
            self.assertIs(o["export_yup"], True)
            self.assertIs(o["export_cameras"], False)
            self.assertIs(o["export_lights"], False)
            self.assertIs(o["export_all_vertex_colors"], False)
            self.assertEqual(o["export_vertex_color"], "MATERIAL")
            self.assertEqual(o["export_image_format"], "AUTO")
            self.assertIs(o["export_gpu_instances"], False)
            self.assertIs(o["will_save_settings"], False)
            self.assertIs(o["export_animations"], prof.skinned, name)
            self.assertIs(o["export_skins"], prof.skinned, name)
            self.assertIs(o["export_apply"], not prof.skinned, name)
            self.assertEqual(o["export_influence_nb"], 4)
            self.assertEqual(prof.tangents, "auto")
            self.assertIn(prof.color0, ("RGB", "RGBA"))
        self.assertEqual(sorted(H.PROFILES), ["character_skinned", "foliage", "impostor_card", "prop", "static_world"])
        self.assertEqual(H.PROFILES["foliage"].double_sided, "alpha")
        self.assertEqual(H.PROFILES["static_world"].double_sided, "explicit")


def _socket(node, identifier, outputs=False):
    return next(s for s in (node.outputs if outputs else node.inputs) if s.identifier == identifier)


def _png_bytes(width, height, rgba) -> bytes:
    """Minimal RGBA8 PNG writer (builders load textures from files, so the test does too)."""
    def chunk(kind, payload):
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    px = bytes(round(max(0.0, min(1.0, c)) * 255) for c in rgba)
    raw = b"".join(b"\x00" + px * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    signature = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _image(name, tmp: Path, rgba, data=False):
    path = tmp / f"{name}.png"
    path.write_bytes(_png_bytes(8, 8, rgba))
    img = bpy.data.images.load(str(path), check_existing=False)
    img.name = name
    img.colorspace_settings.name = "Non-Color" if data else "sRGB"
    img.alpha_mode = "STRAIGHT"
    assert tuple(img.size) == (8, 8), f"{name}: image failed to load"
    return img


def _material(name, albedo, normal=None, cutoff=None, vertex_alpha=False):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = albedo
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Color"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    _socket(mix, "Factor_Float").default_value = 1.0
    nt.links.new(tex.outputs["Color"], _socket(mix, "A_Color"))
    nt.links.new(vc.outputs["Color"], _socket(mix, "B_Color"))
    nt.links.new(_socket(mix, "Result_Color", outputs=True), bsdf.inputs["Base Color"])
    if normal is not None:
        ntex = nt.nodes.new("ShaderNodeTexImage")
        ntex.image = normal
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    if cutoff is not None:  # glTF MASK recipe: 1 - (alpha < cutoff)
        lt = nt.nodes.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        alpha_src = tex.outputs["Alpha"]
        if vertex_alpha:  # what Blender's glTF importer builds for MASK materials with COLOR_0
            mul = nt.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            nt.links.new(tex.outputs["Alpha"], mul.inputs[0])
            nt.links.new(vc.outputs["Alpha"], mul.inputs[1])
            alpha_src = mul.outputs["Value"]
        nt.links.new(alpha_src, lt.inputs[0])
        lt.inputs[1].default_value = cutoff
        sub = nt.nodes.new("ShaderNodeMath")
        sub.operation = "SUBTRACT"
        sub.inputs[0].default_value = 1.0
        nt.links.new(lt.outputs["Value"], sub.inputs[1])
        nt.links.new(sub.outputs["Value"], bsdf.inputs["Alpha"])
    mat.use_backface_culling = False  # Blender's default: the helper's policy must decide, not this flag
    return mat


def _mesh(name, kind, mat, uv_sets=1):
    bm = bmesh.new()
    if kind == "cube":
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0.0, 0.0, 0.5))
    else:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(1.5708, 3, "X"))
        bmesh.ops.translate(bm, verts=bm.verts, vec=(2.0, 0.0, 0.5))
    for i in range(uv_sets):
        layer = bm.loops.layers.uv.new("UVMap" if i == 0 else f"wind_{i}")
        for f in bm.faces:
            for loop in f.loops:
                co = loop.vert.co
                loop[layer].uv = ((co.x + co.y) * 0.5 % 1.0, co.z % 1.0) if i == 0 else (co.z / 1.0, 0.25)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    col = me.color_attributes.new("Color", "FLOAT_COLOR", "CORNER")
    for d in col.data:
        d.color = (0.8, 0.7, 0.6, 1.0)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


class ExportEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        cls.tmp = Path(tempfile.mkdtemp(prefix="xex-export-helper-test-"))
        src = cls.tmp / "src"
        src.mkdir()
        cls.albedo = _image("crate_albedo", src, (0.7, 0.5, 0.3, 1.0))
        cls.normal = _image("crate_normal", src, (0.5, 0.5, 1.0, 1.0), data=True)
        cls.leaf_img = _image("leaf_atlas", src, (0.3, 0.6, 0.2, 0.0))
        cls.crate_mat = _material("crate_mat", cls.albedo, cls.normal)
        cls.leaf_mat = _material("leaf_mat", cls.leaf_img, cutoff=0.5)
        cls.crate = _mesh("crate", "cube", cls.crate_mat)
        cls.leaf = _mesh("leaf_card", "card", cls.leaf_mat, uv_sets=2)
        cls.out = cls.tmp / "out"
        cls.receipt = H.export_glb([cls.crate, cls.leaf], cls.out / "tree_test.glb", "foliage",
                                   texture_dir=cls.out / "textures", fail_on_validation=False)
        cls.gltf, _ = H.read_glb(cls.out / "tree_test.glb")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_receipt_pass_and_written(self):
        self.assertEqual(self.receipt["status"], "PASS", json.dumps(self.receipt.get("failures")))
        on_disk = json.loads((self.out / "tree_test.receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["status"], "PASS")
        self.assertEqual(len(on_disk["outputs"][0]["sha256"]), 64)
        self.assertIn("export_tangents", on_disk["exporter_options"])
        self.assertTrue(all(c["pass"] for c in on_disk["validation"] if c["check"] != "no_expensive_material_extensions"))

    def test_double_sided_policy(self):
        mats = {m["name"]: m for m in self.gltf["materials"]}
        self.assertNotIn("doubleSided", mats["crate_mat"], "opaque bark-like material must be single-sided (GAP-4)")
        self.assertTrue(mats["leaf_mat"].get("doubleSided"), "alpha-tested card stays double-sided")
        self.assertEqual(mats["leaf_mat"].get("alphaMode"), "MASK")
        self.assertFalse(self.crate_mat.use_backface_culling, "the builder's material flag is restored after export")

    def test_tangents_color0_uv(self):
        prims = {self.gltf["materials"][p["material"]]["name"]: p for m in self.gltf["meshes"] for p in m["primitives"]}
        acc = self.gltf["accessors"]
        for name, p in prims.items():
            self.assertIn("TANGENT", p["attributes"], f"{name}: a normal map is exported, so tangents are on")
            self.assertEqual(acc[p["attributes"]["COLOR_0"]]["type"], "VEC3", f"{name}: COLOR_0 must be RGB (GAP-3)")
        self.assertIn("TEXCOORD_1", prims["leaf_mat"]["attributes"], "second UV set (wind data) is kept")

    def test_images_external_and_deduplicated(self):
        self.assertTrue(all("uri" in i and "bufferView" not in i for i in self.gltf["images"]))
        files = sorted(p.name for p in (self.out / "textures").iterdir())
        self.assertEqual(len(files), 3, files)
        again = H.export_glb([self.crate, self.leaf], self.out / "tree_test_copy.glb", "foliage",
                             texture_dir=self.out / "textures", reimport=False, fail_on_validation=False)
        self.assertEqual({i["dedup"] for i in again["images"]}, {"reused"})
        self.assertEqual(sorted(p.name for p in (self.out / "textures").iterdir()), files)

    def test_reimport_validation(self):
        r = self.receipt["reimport"]
        self.assertEqual(r["triangles"], self.receipt["glb"]["triangles"])
        self.assertEqual(r["triangles"], self.receipt["source"]["triangles"])
        self.assertFalse(r["materials"]["leaf_mat"]["use_backface_culling"])
        self.assertTrue(r["materials"]["crate_mat"]["use_backface_culling"])
        self.assertIn("crate", bpy.data.objects, "scratch re-import keeps the caller's session")
        self.assertEqual(len(bpy.data.scenes), 1, "the scratch scene is removed")

    def test_vec4_color0_rewritten_to_rgb(self):
        plain = bpy.data.objects.new("plain", self.crate.data.copy())
        bpy.context.scene.collection.objects.link(plain)
        plain.data.materials.clear()
        rec = H.export_glb([plain], self.out / "plain.glb", "static_world", materials="NONE",
                           vertex_color_when_no_material=True, texture_dir=self.out / "textures", fail_on_validation=False)
        self.assertEqual(rec["status"], "PASS", rec["failures"])
        self.assertTrue(rec["color0_conversions"], "the exporter wrote VEC4 (active colour, no material) and it was rewritten")
        gltf, binary = H.read_glb(self.out / "plain.glb")
        c0 = gltf["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"]
        self.assertEqual(gltf["accessors"][c0]["type"], "VEC3")
        rgb = H.read_accessor(gltf, binary, c0)
        self.assertAlmostEqual(float(rgb[:, 0].mean()), 0.8, places=3)

    def test_color0_survives_mixed_vertex_alpha_materials(self):
        """One mesh, two materials: opaque uses vertex colour, MASK also uses vertex alpha (importer wiring).
        Without the helper's RGB alpha policy the exporter writes white COLOR_0 for one primitive."""
        mixed_mat = _material("leaf_va_mat", self.leaf_img, cutoff=0.5, vertex_alpha=True)
        ob = _mesh("mixed", "cube", self.crate_mat)
        ob.data.materials.append(mixed_mat)
        for i, poly in enumerate(ob.data.polygons):
            poly.material_index = i % 2
        rec = H.export_glb([ob], self.out / "mixed.glb", "foliage", texture_dir=self.out / "textures",
                           fail_on_validation=False)
        self.assertEqual(rec["status"], "PASS", rec["failures"])
        self.assertTrue(rec["policy"]["vertex_alpha_links_detached"], "the vertex-alpha link is detached for export")
        gltf, binary = H.read_glb(self.out / "mixed.glb")
        for prim in gltf["meshes"][0]["primitives"]:
            rgb = H.read_accessor(gltf, binary, prim["attributes"]["COLOR_0"])
            self.assertAlmostEqual(float(rgb[:, 1].mean()), 0.7, places=2, msg="COLOR_0 keeps the source colour")
        leaf = next(m for m in gltf["materials"] if m["name"] == "leaf_va_mat")
        self.assertEqual(leaf.get("pbrMetallicRoughness", {}).get("baseColorFactor", [1, 1, 1, 1])[3], 1,
                         "detaching the vertex-alpha link must not leave a 0.5 alpha factor behind")
        nt = mixed_mat.node_tree
        self.assertTrue(any(l.from_socket.identifier == "Alpha" and l.from_node.type == "VERTEX_COLOR"
                            for l in nt.links), "the builder's node tree is restored after export")

    def test_skinned_profile_requires_applied_modifiers(self):
        ob = bpy.data.objects.new("body", self.crate.data.copy())
        bpy.context.scene.collection.objects.link(ob)
        ob.modifiers.new("smooth", "SUBSURF")
        with self.assertRaises(H.ExportValidationError) as ctx:
            H.export_glb([ob], self.out / "body.glb", "character_skinned", texture_dir=self.out / "textures")
        self.assertEqual(ctx.exception.receipt["status"], "FAIL")
        self.assertTrue(any("must be applied" in f for f in ctx.exception.receipt["failures"]))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    print(f"TESTS run={result.testsRun} failures={len(result.failures)} errors={len(result.errors)}", flush=True)
    if not result.wasSuccessful():
        raise SystemExit(1)
