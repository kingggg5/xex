"""Write the hero 02 clip sidecar and runtime manifest (system Python).

Outputs (both copied to helper/ and runtime/):
  hero02_witch.clips.json     xexoria.xs1-clips/1: every clip with frames, duration, loop, events (ms), source/licence,
                              plus the skill-slot -> clip -> release frame -> VFX mapping
  hero02_witch.manifest.json  LOD files and switch distances, weapon file + socket + markers, sockets, joint count,
                              display scale, budgets measured by the post-process, LOD binding recipe
"""
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
EV = ROOT / "planning" / "evidence" / "hero02-witch-20261002"
M = ROOT / "assets" / "models" / "heroes" / "hero02"
clips = json.loads((EV / "reports" / "clips.json").read_text(encoding="utf-8"))
rig = json.loads((EV / "reports" / "rig.json").read_text(encoding="utf-8"))
staff = json.loads((EV / "reports" / "staff.json").read_text(encoding="utf-8"))

LAYER = {"base.idle": "full", "base.walk": "full", "base.run": "full", "base.hit_light": "upper (additive-capable)",
         "base.dodge": "full", "base.death": "full"}
BLEND = {"base.idle": (150, 150), "base.walk": (120, 150), "base.run": (150, 150), "base.dodge": (50, 100),
         "base.death": (100, 0), "base.hit_light": (30, 120)}
DESIGN = json.loads((ROOT / "planning/assets/hero-skills.json").read_text(encoding="utf-8"))
H02_SKILLS = sorted((s for s in DESIGN["skills"] if s["hero"] == "h02"), key=lambda s: s["slot"])
CLIP_BY_SLOT = {0: "caster.attack_1", 1: "mage.skill_gale", 2: "mage.skill_nova", 3: "mage.skill_rift",
                4: "mage.skill_bolt", 5: "mage.skill_ward", 6: "mage.skill_starfall"}
SKILLS = [(f"slot_{s['slot']}", s["id"], CLIP_BY_SLOT[s["slot"]], s["vfx"]["preset"],
           "weapon.fx_head (owner-relative)", s["summary"]) for s in H02_SKILLS if s["slot"]]

out = {
    "schema": "xexoria.xs1-clips/1", "skeleton": "XS1", "skeleton_revision": "xs1-r0-hero02 (Tier P: clips baked on hero 02)",
    "fps": clips["fps"], "time_unit": "ms", "hero": "hero02_witch",
    "authority": "presentation only; the server owns damage, movement and cast success",
    "clips": {}, "skills": {}, "basic_attack": {},
}
for name, c in clips["clips"].items():
    bi, bo = BLEND.get(name, (50, 150))
    out["clips"][name] = {
        "loop": c["loop"], "frames": c["frames"], "duration_ms": c["duration_ms"],
        "layer": LAYER.get(name, "full standing; upper body while moving"),
        "ability": c.get("ability"), "contract": c.get("contract"),
        "events": c["events"],
        "release_frame": next((e["frame"] for e in c["events"] if e["id"] == "release"), None),
        "release_ms": next((e["t_ms"] for e in c["events"] if e["id"] == "release"), None),
        "blend_in_ms": bi, "blend_out_ms": bo,
        "implied_speed_mps": c.get("implied_speed_mps"),
        "source": c["source"], "notes": c.get("notes"),
        "qa": {"hips_xy_drift_m": c["hips_xy_drift_m"]},
    }
for slot, sid, clip, vfx, anchor, note in SKILLS:
    c = out["clips"][clip]
    out["skills"][slot] = {"skill_id": sid, "clip": clip, "release_frame": c["release_frame"],
                           "release_ms": c["release_ms"], "duration_ms": c["duration_ms"], "vfx": vfx,
                           "vfx_anchor": anchor, "events": c["events"], "note": note}
out["basic_attack"] = {"combo": ["caster.attack_1", "caster.attack_2"],
                       "release_ms": out["clips"]["caster.attack_1"]["release_ms"],
                       "contract": {"windup_ms": 100, "active_ms": 67, "recovery_ms": 233, "next_link_ms": [400, 650]},
                       "trail": {"from": "staff fx_base", "to": "staff fx_tip", "on_event": "trail_on", "off_event": "trail_off"}}
clip_map = {"schema": "xexoria.hero02-clip-map/1", "fps": 30, "design_schema": DESIGN["schema"],
            "design_version": DESIGN["version"], "status": "presentation mapping; gameplay remains server-authoritative",
            "marker_resolution": "resolve weapon.fx_head beneath the attached weapon owner, never global rig fx_head",
            "aliases": {"mage.skill_hollow": "mage.skill_rift", "mage.skill_lance": "mage.skill_bolt", "mage.skill_orrery": "mage.skill_starfall"},
            "plant_rounding": "Nova keeps the explicit animation plan plant f4 (133ms); hit/release f6 (200ms). Design text150ms is a half-frame and remains a documented discrepancy.",
            "skills": {}}
for s in H02_SKILLS:
    t=s["timing"]; name=CLIP_BY_SLOT[s["slot"]]; c=out["clips"][name]
    expected=int(t["windup_ms"] * .03 + .5)
    if c["release_frame"] != expected:
        raise ValueError(f"{s['id']}: animated release {c['release_frame']} != canonical {expected}")
    row={"slot": s["slot"], "clip": name, "windup_ms": t["windup_ms"], "active_ms": t["active_ms"],
         "release_frame": expected, "recovery_ms": t["recovery_ms"], "duration_ms": c["duration_ms"],
         "vfx": s["vfx"]["preset"], "marker": "weapon.fx_head", "missing_clip": False}
    if s["slot"] == 0: row["combo"]=["caster.attack_1", "caster.attack_2"]
    clip_map["skills"][s["id"]]=row
    if s["slot"]: out["skills"][f"slot_{s['slot']}"].update({k:v for k,v in row.items() if k in ("windup_ms","active_ms","recovery_ms")})
# Exported counts are authoritative after duplicate-face cleanup.
for L in (0, 1):
    receipt=M / "helper" / f"hero02_staff_lod{L}.receipt.json"
    if receipt.exists():staff["lods"][str(L)]=json.loads(receipt.read_text(encoding="utf-8"))["glb"]["triangles"]
manifest = {
    "schema": "xexoria.hero-manifest/1", "hero": "hero02_witch", "class": "mage", "status": "INTEGRATION_CANDIDATE",
    "display_scale": 1.0, "crown_height_m": 1.80, "hair_top_m": 1.83, "hat_tip_m": 1.97,
    "capsule": {"radius_m": 0.35, "height_m": 1.8},
    "facing": "Babylon +Z (facing 0); Blender -Y", "pivot": "ground, between the ankles",
    "joints": rig["joint_count"], "skeleton_tier": "P (per-hero bake; XS1 joint names and order)",
    "lods": [
        {"lod": 0, "file": "hero02_witch_lod0.glb", "triangles": rig["lods"]["0"]["triangles"], "band": "A, < 15 m", "has_clips": True},
        {"lod": 1, "file": "hero02_witch_lod1.glb", "triangles": rig["lods"]["1"]["triangles"], "band": "B, 15-35 m", "has_clips": False},
        {"lod": 2, "file": "hero02_witch_lod2.glb", "triangles": rig["lods"]["2"]["triangles"], "band": "C, 35-60 m", "has_clips": False},
    ],
    "lod_switch_m": [15, 35, 60], "lod_switch_note": "High tier; multiply by the tier lodDistanceScale (device tiers plan 3.4)",
    "lod_binding": ("Load LOD0 (skeleton + clips). Load LOD1/LOD2, parent their __root__ beside LOD0's, then link every "
                    "LOD1/LOD2 bone to the LOD0 joint node with the same name (Bone.linkTransformNode). Each file keeps "
                    "its own inverse bind matrices (the post-process quantizes per mesh), so never assign the LOD0 "
                    "skeleton to a LOD1/LOD2 mesh. Then lod0Primitive.addLODLevel(15, lod1Primitive), (35, lod2), (60, null)."),
    "weapon": {"lods": ["hero02_staff_lod0.glb", "hero02_staff_lod1.glb"],
               "triangles": staff["lods"], "length_m": staff["length_m"], "socket": "socket_weapon_R",
               "attach": "parent the staff file's top node (child of its __root__) to socket_weapon_R with identity TRS",
               "markers_m": staff["markers_m"]},
    "sockets": rig["static_nodes"] + ["socket_weapon_R", "socket_weapon_L"],
    "clips": "hero02_witch.clips.json",
    "repair_pipeline": ["hair_policy (annotated pieces intersecting measured seams)", "cloth_floor (secondary bones only)", "export", "postprocess", "sidecar", "test", "validator", "reimport"],
    "materials": {"hero02_witch_body": "single-sided", "hero02_witch_cloth": "double-sided (robe, sleeves, capelet)"},
}
for d in (M / "helper", M / "runtime"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "clip-map.json").write_text(json.dumps(clip_map, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (d / "hero02_witch.clips.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (d / "hero02_witch.manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({slot: (v["clip"], v["release_frame"], v["release_ms"], v["vfx"]) for slot, v in out["skills"].items()}))
