"""Stage 5: export the hero 02 runtime candidates through the shared helper (character_skinned / prop profiles).

Writes to assets/models/heroes/hero02/helper/:
  hero02_witch_lod0.glb   skin (59 XS1 joints) + LOD0 mesh + all clips + socket/fx nodes   (budget class hero_lod0)
  hero02_witch_lod1.glb   same skin + LOD1 mesh, no clips, no static nodes                  (hero_lod1)
  hero02_witch_lod2.glb   same skin + LOD2 mesh, no clips, no static nodes                  (hero_lod2)
  hero02_staff_lod0/1.glb  staff with fx_base / fx_tip / fx_head / grip_r / grip_l nodes   (prop, prop_lod1)
  textures/               shared PNG intermediates (deduplicated by SHA-256)
  *.receipt.json          helper receipts
Then gltf-postprocess.mjs turns them into assets/models/heroes/hero02/runtime/ (see run order in the doc).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import bpy  # noqa: E402
import h02_common as C  # noqa: E402
from export_helper import export_glb  # noqa: E402

log = C.Log("h02_export")
OUT = C.HELPER
TEXD = OUT / "textures"
COPY = ("Xexoria hero 02 (witch, Mage). Mesh and textures: owner's Tripo P2.0 job cfdd51e7 (paid-user Outputs, "
        "Tripo terms 5.2.2). Clips: Quaternius UAL1 CC0 retargets + authored. Not for redistribution outside the game.")
STAFF_COPY = "Xexoria hero 02 staff. Owner's Tripo P2.0 job 24cd0fd7 (paid-user Outputs, Tripo terms 5.2.2)."
receipts = {}

def prepare_material_groups():
    # The saved atlas group predates the Blender5.2 importer schema. Keep linked
    # Occlusion/Thickness sockets and add the current built-in optional inputs.
    for g in bpy.data.node_groups:
        if g.name == "glTF Material Output":
            names={item.name for item in g.interface.items_tree if item.item_type == "SOCKET" and item.in_out == "INPUT"}
            for name,default in (("Dispersion",0.0),("Iridescence Factor",0.0),("Iridescence Thickness Minimum",100.0)):
                if name not in names:
                    socket=g.interface.new_socket(name,in_out="INPUT",socket_type="NodeSocketFloat")
                    socket.default_value=default
    for ob in bpy.data.objects:
        if ob.type == "MESH" and ob.name.startswith("hero02_"):
            changed=ob.data.validate(verbose=False,clean_customdata=False)
            log("mesh_validate",ob.name,"repaired",changed,"materials",[(m.name if m else None) for m in ob.data.materials])
            ob.data.update()


bpy.ops.wm.open_mainfile(filepath=str(C.WORK / "h02_anim.blend"))
prepare_material_groups()
arm = bpy.data.objects["hero02_XS1"]
lods = {L: bpy.data.objects[f"hero02_witch_lod{L}"] for L in (0, 1, 2)}
empties = [o for o in bpy.data.objects if o.get("xex_socket")]
hi = bpy.data.objects.get("hero02_hiclean")
actions = [a.name for a in bpy.data.actions]
log("actions", actions)
arm.animation_data.action = None
for L in (0, 1, 2):
    o = lods[L]
    cloth = [m.name for m in o.data.materials if "cloth" in m.name]
    body = [m.name for m in o.data.materials if "body" in m.name]
    if L == 0:
        objs = [arm, o] + empties
    else:
        objs = [arm, o]
        saved_ad = [a for a in bpy.data.actions]
        arm.animation_data_clear()
    path = OUT / f"hero02_witch_lod{L}.glb"
    r = export_glb(objs, path, "character_skinned", receipt_path=OUT / f"hero02_witch_lod{L}.receipt.json",
                   texture_dir=TEXD, asset_id=f"hero02_witch_lod{L}", budget_class=f"hero_lod{L}",
                   double_sided_materials=cloth, single_sided_materials=body, copyright_text=COPY,
                   notes=f"hero02 witch LOD{L}; clips only in LOD0; LOD1/LOD2 bind to the same XS1 joints")
    receipts[path.name] = r["status"]
    log("export", path.name, r["status"], "warnings", len(r.get("warnings", [])))
    if L != 0:
        arm.animation_data_create()

# ------------------------------------------------------------------------------------------------ staff
bpy.ops.wm.open_mainfile(filepath=str(C.WORK / "h02_staff.blend"))
prepare_material_groups()
slods = {L: bpy.data.objects[f"hero02_staff_lod{L}"] for L in (0, 1)}
markers = {L: [c for c in o.children if c.get("xex_marker")] for L, o in slods.items()}
for L, o in slods.items():
    # every LOD file gets canonical marker names
    for M_ in (0, 1):
        for e in markers[M_]:
            e.name = f"tmp_{M_}_{e['xex_marker']}"
    for e in markers[L]:
        e.name = e["xex_marker"]
    o.name = "hero02_staff" if L == 0 else f"hero02_staff_lod{L}"
    path = OUT / f"hero02_staff_lod{L}.glb"
    r = export_glb([o] + markers[L], path, "prop", receipt_path=OUT / f"hero02_staff_lod{L}.receipt.json",
                   texture_dir=TEXD, asset_id=f"hero02_staff_lod{L}",
                   budget_class="prop" if L == 0 else "prop_lod1", copyright_text=STAFF_COPY,
                   notes="weapon GLB: origin at the right-hand grip, shaft along +Y; fx_base/fx_tip trail markers")
    receipts[path.name] = r["status"]
    log("export", path.name, r["status"])
    o.name = f"hero02_staff_lod{L}"
C.write_json(C.REPORTS / "export.json", {"receipts": receipts, "actions": actions})
log("done", receipts)
