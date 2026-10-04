"""Label and compose the hero 02 BLENDER REVIEW renders (system Python + Pillow).

python h02_label.py <tag>   reads planning/evidence/hero02-witch-20261002/renders/raw/<tag>_*.png and writes
planning/evidence/hero02-witch-20261002/renders/<tag>/*.png, every image carrying a "BLENDER REVIEW" header.
"""
import glob
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
EV = ROOT / "planning" / "evidence" / "hero02-witch-20261002"
RAW = EV / "renders" / "raw"
tag = sys.argv[1] if len(sys.argv) > 1 else "pass1"
OUT = EV / "renders" / tag
OUT.mkdir(parents=True, exist_ok=True)
clips = json.loads((EV / "reports" / "clips.json").read_text(encoding="utf-8"))["clips"]
rig = json.loads((EV / "reports" / "rig.json").read_text(encoding="utf-8"))
lod_tris = {int(k): v["triangles"] for k, v in rig["lods"].items()}


def font(size, bold=False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def header(img, title, sub):
    w = img.width
    band = 64
    out = Image.new("RGB", (w, img.height + band), (24, 26, 30))
    out.paste(img, (0, band))
    d = ImageDraw.Draw(out)
    d.text((14, 6), "BLENDER REVIEW", font=font(24, True), fill=(255, 196, 64))
    d.text((230, 9), title, font=font(20, True), fill=(235, 235, 235))
    d.text((14, 38), sub, font=font(15), fill=(170, 175, 185))
    return out


def caption(img, text, size=18):
    d = ImageDraw.Draw(img)
    pad = 6
    tw = d.textlength(text, font=font(size, True))
    d.rectangle((0, img.height - size - 2 * pad, tw + 2 * pad, img.height), fill=(24, 26, 30))
    d.text((pad, img.height - size - pad), text, font=font(size, True), fill=(240, 240, 240))
    return img


def raw(name):
    p = RAW / f"{tag}_{name}.png"
    return Image.open(p).convert("RGB") if p.exists() else None


SUB = (f"hero02 witch (Mage) - LOD0 {lod_tris.get(0, '?'):,} tris - one 2048 atlas - XS1 59 joints - "
       "Cycles CPU, AgX - grey witness = 1.80 m - 2026-10-02")
made = []
views = [(n, raw(f"view_{n}")) for n in ("front", "side", "back", "threequarter")]
views = [(n, im) for n, im in views if im]
if views:
    w = sum(im.width for _, im in views)
    h = max(im.height for _, im in views)
    sheet = Image.new("RGB", (w, h), (0, 0, 0))
    x = 0
    for n, im in views:
        sheet.paste(caption(im, f"{n} - idle frame 0, staff in socket_weapon_R"), (x, 0))
        x += im.width
    header(sheet, "front / side / back / three-quarter", SUB).save(OUT / "views_front_side_back.png", optimize=True)
    made.append("views_front_side_back.png")
cb, ca, cs = raw("cast_before"), raw("cast_after"), raw("cast_skill_bolt_release")
if cb and ca:
    parts = [caption(cb, "BEFORE: owner's Tripo rig + Tripo weights (cast_a_spell.001)"),
             caption(ca, "AFTER: XS1 + new weights + sleeve/skirt rules (same pose)")]
    if cs:
        rel = next(e["frame"] for e in clips["mage.skill_bolt"]["events"] if e["id"] == "release")
        parts.append(caption(cs, f"AFTER: shipped mage.skill_bolt, release frame {rel}"))
    sheet = Image.new("RGB", (sum(p.width for p in parts), max(p.height for p in parts)))
    x = 0
    for p in parts:
        sheet.paste(p, (x, 0))
        x += p.width
    header(sheet, "cast pose: sleeve and waist collapse, before / after", SUB).save(OUT / "cast_before_after.png", optimize=True)
    made.append("cast_before_after.png")
lu = raw("lineup_lods")
if lu:
    lu = caption(lu, f"LOD0 {lod_tris.get(0):,} | LOD1 {lod_tris.get(1):,} | LOD2 {lod_tris.get(2):,} tris - witness 1.80 m at left")
    header(lu, "LOD lineup with the 1.8 m witness", SUB).save(OUT / "lineup_lods_witness.png", optimize=True)
    made.append("lineup_lods_witness.png")
sil = raw("lineup_silhouette")
if sil:
    header(caption(sil, "greyscale silhouette: LOD0 / LOD1 / LOD2"), "silhouette check", SUB).save(OUT / "lineup_silhouette.png", optimize=True)
    made.append("lineup_silhouette.png")
cells = sorted(glob.glob(str(RAW / f"{tag}_sheet_*.png")))
if cells:
    ims = []
    for c in cells:
        stem = Path(c).stem[len(tag) + 7:]
        clip, f = stem.rsplit("_f", 1)
        clip = clip.replace("_", ".", 1)
        meta = clips.get(clip, {})
        ev = {e["frame"]: e["id"] for e in meta.get("events", [])}
        lab = f"{clip}  f{int(f)}" + (f"  [{ev[int(f)]}]" if int(f) in ev else "")
        ims.append(caption(Image.open(c).convert("RGB"), lab, 16))
    cols = 6
    cw, ch = ims[0].width, ims[0].height
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), (40, 40, 44))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * cw, (i // cols) * ch))
    header(sheet, "clip contact sheet (release frame and 2 frames before it; mid-cycle for loops)", SUB).save(
        OUT / "clips_contact_sheet.png", optimize=True)
    made.append("clips_contact_sheet.png")
for n in ("gamecam_back", "gamecam_turn135"):
    im = raw(n)
    if im:
        header(caption(im, "game camera: radius 13 m, beta 1.18 rad, FOV 1.02 rad, target 1.65 m up / 2 m ahead"),
               n.replace("_", " "), SUB).save(OUT / f"{n}.png", optimize=True)
        made.append(f"{n}.png")
print(json.dumps({"tag": tag, "written": made}))
