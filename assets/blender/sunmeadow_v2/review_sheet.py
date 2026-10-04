"""Label BLENDER REVIEW renders, build the contact sheet, the plan comparison and the collider overlay.

  python assets/blender/sunmeadow_v2/review_sheet.py --raw <raw/passN> --out planning/evidence/sunmeadow-v2-blockout/passN \
      --pass N [--before planning/evidence/sunmeadow-v2-blockout/pass1]
      [--before-glade <labelled passN-1 dir> --before-instances <passN-1 instances.json>] [--arena <arena_check JSON>]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sm2_geom as G  # noqa: E402
from sm2_site import ROOT, Site  # noqa: E402

PLAN = ROOT / 'planning' / 'evidence' / 'sunmeadow-v2-layout' / 'plan.png'
DATE = '2026-10-02'
ORDER = ['hunt_player', 'hunt_side', 'hunt_close', 'hunt_elevated', 'glade_player', 'glade_side', 'glade_close',
         'glade_elevated', 'wallow_player', 'wallow_side', 'wallow_close', 'wallow_elevated',
         'sl1_eye', 'sl1_cam', 'sl2_eye', 'sl2_cam', 'sl3_eye', 'sl3_cam', 'sl4_eye', 'sl4_cam', 'top', 'arena_top']
GLADE_VIEWS = ['glade_player', 'glade_side', 'glade_close', 'glade_elevated']
HEAD = 30        # label() header height: raw pixels start at y = HEAD in a labelled image


def font(size, bold=False):
    for name in (('arialbd.ttf', 'consolab.ttf') if bold else ('arial.ttf', 'consola.ttf')):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def label(img: Image.Image, title: str, lines: list[str]) -> Image.Image:
    import textwrap
    width_chars = max(60, int(img.width / 7.1))
    lines = [w for ln in lines for w in (textwrap.wrap(ln, width_chars) or [''])]
    head, foot = 30, 18 * len(lines) + 8
    out = Image.new('RGB', (img.width, img.height + head + foot), (16, 18, 22))
    out.paste(img, (0, head))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, img.width, head], fill=(150, 28, 28))
    d.text((8, 6), title, fill=(255, 255, 255), font=font(16, True))
    for k, ln in enumerate(lines):
        d.text((8, img.height + head + 4 + 18 * k), ln, fill=(225, 225, 225), font=font(13))
    return out


def cam_line(m):
    if m.get('kind') == 'game' or m.get('type') == 'game':
        col = ' (camera collision: boom %.1f m)' % m['boom_m'] if m.get('collided') else ''
        return (f"game camera: ArcRotate r={m['radius']} m, beta={m['beta']} rad, FOV {m['fov_y']} rad, target +{m['target_h']} m, "
                f"yaw {m['yaw']:.2f}{col}")
    if m.get('type') == 'ortho_top':
        return 'orthographic top view, 6 px/m, north up, x east to the right'
    if m.get('type') == 'ortho_close':
        c = m['centre_xz']
        return (f"orthographic top view centred ({c[0]:g},{c[1]:g}), {m['size_m']:g} x {m['size_m']:g} m, {m['px_per_m']:g} px/m, "
                f"north up, x east to the right")
    e, a = m['eye_babylon'], m['at_babylon']
    return f"eye ({e[0]:.1f}, {e[1]:.2f}, {e[2]:.1f}) -> ({a[0]:.1f}, {a[1]:.2f}, {a[2]:.1f}) Babylon XYZ, vertical FOV {m['fov_y']} rad"


def stage_px(site, x, z, scale=6.0):
    x0, x1, z0, z1 = site.stage
    return ((x - x0) * scale, (z1 - z) * scale)


def plan_compare(site, top_raw: Image.Image, out: Path, title):
    plan = Image.open(PLAN).convert('RGB').crop((60, 100, 828, 904))
    w, h = top_raw.size
    plan = plan.resize((w, h))
    blend = Image.blend(top_raw.convert('RGB'), plan, 0.45)
    sheet = Image.new('RGB', (w * 3 + 40, h + 70), (16, 18, 22))
    for k, (im, cap) in enumerate(((top_raw, 'BLENDER REVIEW top ortho'), (plan, 'PLAN (layout plan.png, same scale)'),
                                   (blend, 'overlay 55/45'))):
        sheet.paste(im.convert('RGB'), (10 + k * (w + 10), 60))
        ImageDraw.Draw(sheet).text((14 + k * (w + 10), 40), cap, fill=(230, 230, 230), font=font(14, True))
    d = ImageDraw.Draw(sheet)
    d.rectangle([0, 0, sheet.width, 30], fill=(150, 28, 28))
    d.text((8, 6), title, fill=(255, 255, 255), font=font(16, True))
    sheet.save(out)


def collider_overlay(site, top_raw: Image.Image, colliders: dict, walk: dict | None, out: Path, title):
    img = top_raw.convert('RGB').copy()
    d = ImageDraw.Draw(img, 'RGBA')
    colours = {'relief': (255, 60, 60, 150), 'water': (40, 140, 255, 160), 'trunk': (40, 220, 90, 170),
               'stone': (230, 230, 60, 190), 'rock': (255, 160, 40, 170), 'camp': (255, 90, 220, 180),
               'landmark': (255, 90, 220, 180), 'prop': (255, 90, 220, 180), 'bridge': (255, 255, 255, 220),
               'bush_existing': (120, 255, 120, 150), 'existing_city': (160, 160, 160, 160),
               'existing_city_hazard': (40, 140, 255, 120)}
    for c in colliders['colliders'] + colliders.get('existing_preserved', []):
        poly = [stage_px(site, q[0], q[1]) for q in c['polygon_xz']]
        col = colours.get(c['category'], (255, 0, 255, 160))
        d.polygon(poly, outline=col[:3] + (255,), fill=col[:3] + (60,))
    for pid, pf in site.paths.items():
        pts = [stage_px(site, *q) for q in pf.line.pts]
        d.line(pts, fill=(255, 255, 255, 230), width=2)
    if walk:
        for pid, pr in walk['paths'].items():
            for r in pr['hit_runs']:
                x, z = r['xz_from']
                u, v = stage_px(site, x, z)
                d.ellipse([u - 6, v - 6, u + 6, v + 6], outline=(255, 0, 0, 255) if not r['expected'] else (255, 200, 0, 255), width=3)
    out_img = label(img, title, ['colliders.json footprints over the top render: red relief / blue water / green trunks / '
                                 'yellow stones / orange rocks / pink camp+landmarks / white rails',
                                 'white lines = JSON path centrelines; circles = walk-check hits (amber = by design: closed south gate)'])
    out_img.save(out)


def contact_sheet(files, out: Path, title, cols=4, tw=480):
    thumbs = []
    for f in files:
        im = Image.open(f).convert('RGB')
        th = int(im.height * tw / im.width)
        thumbs.append(im.resize((tw, th)))
    rows = [thumbs[i:i + cols] for i in range(0, len(thumbs), cols)]
    heights = [max(t.height for t in row) for row in rows]          # per-row height (the tall top view gets its own row)
    sheet = Image.new('RGB', (cols * (tw + 8) + 8, sum(h + 8 for h in heights) + 44), (16, 18, 22))
    d = ImageDraw.Draw(sheet)
    d.rectangle([0, 0, sheet.width, 34], fill=(150, 28, 28))
    d.text((10, 8), title, fill=(255, 255, 255), font=font(17, True))
    y = 42
    for row, h in zip(rows, heights):
        for c, t in enumerate(row):
            sheet.paste(t, (8 + c * (tw + 8), y))
        y += h + 8
    sheet.save(out)


def before_after(before: Path, after: Path, names, out: Path, title, before_tag='pass 1'):
    pairs = [(before / f'{n}.png', after / f'{n}.png') for n in names if (before / f'{n}.png').exists() and (after / f'{n}.png').exists()]
    if not pairs:
        return False
    tw = 560
    ims = []
    for b, a in pairs:
        bi, ai = Image.open(b).convert('RGB'), Image.open(a).convert('RGB')
        th = int(bi.height * tw / bi.width)
        ims.append((bi.resize((tw, th)), ai.resize((tw, int(ai.height * tw / ai.width)))))
    hrow = max(max(b.height, a.height) for b, a in ims)
    sheet = Image.new('RGB', (2 * tw + 24, len(ims) * (hrow + 8) + 70), (16, 18, 22))
    d = ImageDraw.Draw(sheet)
    d.rectangle([0, 0, sheet.width, 34], fill=(150, 28, 28))
    d.text((10, 8), title, fill=(255, 255, 255), font=font(17, True))
    d.text((10, 44), f'BEFORE ({before_tag})', fill=(230, 230, 230), font=font(14, True))
    d.text((tw + 18, 44), 'AFTER (this pass)', fill=(230, 230, 230), font=font(14, True))
    for k, (b, a) in enumerate(ims):
        y = 66 + k * (hrow + 8)
        sheet.paste(b, (8, y))
        sheet.paste(a, (tw + 16, y))
    sheet.save(out)
    return True


# ----------------------------------------------------------------------------- boss arena (pass 5)
def _ring(d, to_px, c, r, colour, width=2, dash=None):
    """Circle of radius r (m) around c, solid or dashed (dash = (on_deg, off_deg))."""
    if dash is None:
        pts = [to_px(c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a))) for a in range(0, 361, 2)]
        d.line(pts, fill=colour, width=width)
        return
    on, off = dash
    a = 0.0
    while a < 360:
        seg = [to_px(c[0] + r * math.cos(math.radians(t)), c[1] + r * math.sin(math.radians(t)))
               for t in [a + k * on / 6 for k in range(7)]]
        d.line(seg, fill=colour, width=width)
        a += on + off


def _arrow(d, p0, p1, colour, width=3, head=11):
    d.line([p0, p1], fill=colour, width=width)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for s in (-1, 1):
        a = ang + math.pi - s * 0.45
        d.line([p1, (p1[0] + head * math.cos(a), p1[1] + head * math.sin(a))], fill=colour, width=width)


def _moved_this_pass(instances, before_instances):
    """[(id, old_xz, new_xz)]: props a layout landmark moves whose position changed since the previous pass
    (without before_instances: every recorded move, from its compact v1 position)."""
    prev = {i['id']: tuple(i['position_xz']) for i in before_instances['instances']} if before_instances else None
    out = []
    for i in instances['instances']:
        mf = i.get('params', {}).get('moved_from_xz')
        if not mf:
            continue
        new = tuple(i['position_xz'])
        old = prev.get(i['id']) if prev is not None else tuple(mf)
        if old is not None and math.dist(old, new) > 0.01:
            out.append((i['id'], old, new))
    return out


def _collider_edge(c, p):
    if c['shape'] == 'capsule':
        return max(0.0, math.hypot(p[0] - c['center'][0], p[1] - c['center'][2]) - c['radius'])
    poly = [tuple(q) for q in c['polygon_xz']]
    return 0.0 if G.point_in_polygon(p, poly) else G.polygon_edge_distance(p, poly)


def _draw_arena(d, img_w, to_px, ppm, site, colliders, instances, moved, draw_colliders=True, label_cols=True,
                arrows=True, mark_decor=True, fnt=None):
    """Arena rings, collider footprints, glade-edge decor marks and moved-prop arrows on an ortho image
    (to_px maps Babylon x, z -> pixels; ppm = pixels per metre)."""
    circ = site.landmarks['windstone_circle']
    cc = tuple(float(v) for v in circ['center_xz'])
    keep = float(circ.get('arena_keep_clear_m', circ['boss_arena_radius_m']))
    arena = float(circ['boss_arena_radius_m'])
    exempt = {f"col_{i['id']}" for i in instances['instances']
              if (i['zone'] == 'windstone_circle' and i['category'] == 'stone') or i['species'] == 'altar'}
    cols = colliders['colliders'] + colliders.get('existing_preserved', [])
    fnt = fnt or font(13)
    _ring(d, to_px, cc, float(circ['radius_m']), (255, 255, 255, 150), 1)
    _ring(d, to_px, cc, 11.5, (90, 235, 255, 210), 1, dash=(4, 4))
    _ring(d, to_px, cc, 13.0, (90, 235, 255, 210), 1, dash=(4, 4))
    _ring(d, to_px, cc, arena, (235, 40, 40, 255), 3)
    _ring(d, to_px, cc, keep, (255, 165, 20, 255), 3, dash=(5, 3))
    if draw_colliders:
        for c in cols:
            if math.hypot(c['center'][0] - cc[0], c['center'][2] - cc[1]) > keep + 5.0:
                continue
            col = (255, 225, 40) if c['id'] in exempt else (255, 60, 220)
            d.polygon([to_px(q[0], q[1]) for q in c['polygon_xz']], outline=col + (255,), fill=col + (55,))
    if mark_decor:
        for i in instances['instances']:
            if i['zone'] != 'glade_edge':
                continue
            u, v = to_px(*i['position_xz'])
            if i['category'] == 'mushroom':
                rr = 0.55 * ppm
                d.ellipse([u - rr, v - rr, u + rr, v + rr], outline=(90, 235, 255, 255), width=2)
            else:
                rr = 0.12 * ppm + 1
                d.ellipse([u - rr, v - rr, u + rr, v + rr], fill=(255, 255, 255, 230))
    for pid, old, new in moved:
        c = next((c for c in cols if c['id'] == f'col_{pid}'), None)
        rr = ((c.get('radius') if c else None) or 0.8) * ppm + 3
        u0, v0 = to_px(*old)
        _ring(d, lambda x, z: (x, z), (u0, v0), rr, (235, 235, 235, 255), 2, dash=(24, 18))
        if arrows:
            _arrow(d, (u0, v0), to_px(*new), (255, 255, 255, 255), 3)
    if label_cols:
        # ring radii, tagged where each ring crosses due south (1 m = ppm px apart, so the tags do not overlap)
        for r, txt, colour in ((float(circ['radius_m']), f"stone ring {float(circ['radius_m']):g} m", (255, 255, 255, 255)),
                               (arena, f'boss arena {arena:g} m', (255, 90, 90, 255)),
                               (keep, f'keep-clear {keep:g} m', (255, 180, 60, 255)),
                               (13.0, 'mushroom band outer 13 m (inner 11.5 m)', (120, 240, 255, 255))):
            u, v = to_px(cc[0], cc[1] - r)
            tw = d.textlength(txt, font=fnt)
            d.rectangle([u + 5, v - 9, u + tw + 13, v + 10], fill=(16, 18, 22, 210))
            d.text((u + 9, v - 8), txt, fill=colour, font=fnt)
        for c in cols:
            if c['id'] in exempt:
                continue
            dc = math.hypot(c['center'][0] - cc[0], c['center'][2] - cc[1])
            de = _collider_edge(c, cc)
            if de > keep + 2.0:
                continue
            u, v = to_px(c['center'][0], c['center'][2])
            name = c['id'].replace('col_sunmeadow_', '').replace('col_sm2_', '').replace('col_', '')
            txt = f'{name}  c {dc:.2f} / e {de:.2f} m'
            tw = d.textlength(txt, font=fnt)
            if u + 16 + tw < img_w - 4:                  # right of the collider
                x, y = u + 16, v - 8
            else:                                        # below it, kept inside the image
                x, y = min(u - tw / 2, img_w - tw - 8), v + 16
            d.rectangle([x - 3, y - 2, x + tw + 3, y + 17], fill=(16, 18, 22, 200))
            d.text((x, y), txt, fill=(255, 255, 255, 255), font=fnt)
    return cc, keep, arena


def arena_overlay(site, raw: Path, views, colliders, instances, moved, arena_json, out: Path, title):
    m = views['views'].get('arena_top')
    if not m or not (raw / 'arena_top.png').exists():
        return False
    img = Image.open(raw / 'arena_top.png').convert('RGB')
    cx, cz = m['centre_xz']
    S = float(m['size_m'])
    ppm = img.width / S

    def to_px(x, z):
        return ((x - (cx - S / 2)) * ppm, ((cz + S / 2) - z) * ppm)

    d = ImageDraw.Draw(img, 'RGBA')
    _draw_arena(d, img.width, to_px, ppm, site, colliders, instances, moved, fnt=font(14))
    # scale bar 5 m, bottom-left
    x0, y0 = 20, img.height - 28
    d.rectangle([x0 - 6, y0 - 22, x0 + 5 * ppm + 8, y0 + 12], fill=(16, 18, 22, 190))
    d.line([(x0, y0), (x0 + 5 * ppm, y0)], fill=(255, 255, 255, 255), width=4)
    d.text((x0, y0 - 20), '5 m', fill=(255, 255, 255, 255), font=font(14, True))
    lines = ['rings: white 8.12 m stone ring, red 11 m boss arena, orange dashed 12 m arena keep-clear (layout arena_keep_clear_m), '
             'cyan dashed 11.5 / 13 m glowing-mushroom band',
             'collider footprints (colliders.json polygon_xz): yellow = exempt (6 ring stones + altar block), magenta = every other '
             'collider; labels: c = collider centre, e = footprint edge distance to (0,-68)',
             'glade_edge decor: cyan rings = glowing mushrooms, white dots = flower patches; grey dashed circles + white arrows = '
             'pass 4 position -> layout prop_move position; orange/amber/purple discs = spawn / v2 home / POI marks']
    if arena_json:
        s = arena_json['summary']
        k = arena_json['arena_keep_clear']
        g = arena_json['ground_cover']
        fp = '; '.join(f"{r['collider'].replace('col_sunmeadow_', '')} e {r['footprint_edge_m']:.2f} / c {r['centre_m']:.2f} m"
                       for r in k['non_exempt_within_keep_clear_by_footprint']) or 'none'
        lines += [f"keep-clear 12 m: centre rule (layout checker) {'PASS' if s['keep_clear_pass_centre_rule'] else 'FAIL'}; "
                  f"footprint rule {'PASS' if s['keep_clear_pass_footprint_rule'] else 'FLAG'} ({fp}); 11 m arena by footprint "
                  f"{'PASS' if s['arena_11m_pass_by_footprint'] else 'FAIL'}; exempt colliders inside 12 m: {s['exempt_within_keep_clear']}",
                  f"glowing mushrooms: {s['glow_mushrooms_glade_edge']} at r {s['glow_mushroom_r_m'][0]:.2f}-{s['glow_mushroom_r_m'][1]:.2f} m "
                  f"(GLB glow vertices min r {s['glb_mushroom_glow_min_r_m']:.2f} m); inside 11 m: {s['flowers_inside_arena']} flower patches, "
                  f"GLB flower max height {s['glb_flower_y_max_m']:.3f} m, non-flower ground cover "
                  f"{len(g['instances_inside_arena_by_footprint']['non_flower_items'])}"]
    label(img, title, [m['label'], cam_line(m)] + lines).save(out)
    return True


def glade_before_after(site, before: Path, after: Path, colliders, instances, moved, out: Path, title, before_tag, after_tag):
    """Glade views of two passes side by side (same cameras) + a top-ortho crop around the arena with the rings."""
    pairs = [(before / f'{n}.png', after / f'{n}.png') for n in GLADE_VIEWS
             if (before / f'{n}.png').exists() and (after / f'{n}.png').exists()]
    tw = 600
    rows = []
    for b, a in pairs:
        bi, ai = Image.open(b).convert('RGB'), Image.open(a).convert('RGB')
        rows.append((bi.resize((tw, int(bi.height * tw / bi.width))), ai.resize((tw, int(ai.height * tw / ai.width)))))
    if (before / 'top.png').exists() and (after / 'top.png').exists():
        circ = site.landmarks['windstone_circle']
        cx, cz = (float(v) for v in circ['center_xz'])
        x0, x1, z0, z1 = site.stage
        half, px = 17.0, 6.0
        box = (int((cx - half - x0) * px), int((z1 - (cz + half)) * px) + HEAD,
               int((cx + half - x0) * px), int((z1 - (cz - half)) * px) + HEAD)
        k = tw / (box[2] - box[0])

        def to_px(x, z):
            return ((x - (cx - half)) * px * k, ((cz + half) - z) * px * k)

        crops = []
        for src, is_after in ((before / 'top.png', False), (after / 'top.png', True)):
            im = Image.open(src).convert('RGB').crop(box).resize((tw, tw), Image.LANCZOS)
            d = ImageDraw.Draw(im, 'RGBA')
            # before: rings + dashed circles on the moved props' previous positions; after: rings, the current
            # collider footprints and arrows from the previous positions
            _draw_arena(d, tw, to_px, px * k, site, colliders, instances, moved, draw_colliders=is_after, label_cols=False,
                        arrows=is_after, mark_decor=False)
            crops.append(im)
        rows.append(tuple(crops))
    if not rows:
        return False
    import textwrap
    names = ', '.join(pid.replace('sunmeadow_', '') for pid, o, n in moved) or 'none'
    notes = [f'last row: the top-ortho render of each pass (same camera, 6 px/m) cropped to 34 x 34 m around the circle centre '
             f'(0,-68), upscaled; red ring 11 m boss arena, orange dashed 12 m keep-clear, cyan dashed 11.5 / 13 m mushroom band.',
             f'grey dashed circles = {before_tag} positions of the props moved in this pass ({names}); after crop: white arrows to '
             f'the layout prop_move positions and the colliders.json footprints (yellow = exempt ring stones + altar block, '
             f'magenta = other colliders).']
    notes = [w for ln in notes for w in textwrap.wrap(ln, int((2 * tw + 24) / 7.0))]
    hrow = [max(b.height, a.height) for b, a in rows]
    foot = 20 * len(notes) + 12
    sheet = Image.new('RGB', (2 * tw + 24, sum(h + 8 for h in hrow) + 70 + foot), (16, 18, 22))
    d = ImageDraw.Draw(sheet)
    d.rectangle([0, 0, sheet.width, 34], fill=(150, 28, 28))
    d.text((10, 8), title, fill=(255, 255, 255), font=font(17, True))
    d.text((10, 44), f'BEFORE ({before_tag})', fill=(230, 230, 230), font=font(14, True))
    d.text((tw + 18, 44), f'AFTER ({after_tag})', fill=(230, 230, 230), font=font(14, True))
    y = 66
    for (b, a), h in zip(rows, hrow):
        sheet.paste(b, (8, y))
        sheet.paste(a, (tw + 16, y))
        y += h + 8
    for k2, ln in enumerate(notes):
        d.text((10, y + 6 + 20 * k2), ln, fill=(225, 225, 225), font=font(13))
    sheet.save(out)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--pass', dest='pass_no', type=int, default=1)
    ap.add_argument('--colliders', default='assets/models/sunmeadow-v2/blockout/colliders.json')
    ap.add_argument('--walk', default='planning/evidence/sunmeadow-v2-blockout/walk_check.json')
    ap.add_argument('--before', default=None)
    ap.add_argument('--instances', default='assets/models/sunmeadow-v2/blockout/instances.json')
    ap.add_argument('--sightlines', default=None,
                    help='sightline JSON (default: <out>/sightlines_passN.json, else the evidence root sightlines_passN.json)')
    ap.add_argument('--arena', default=None, help='arena_check.py JSON for the arena overlay footer')
    ap.add_argument('--before-glade', default=None, help='labelled renders of the previous pass for before_after_glade.png')
    ap.add_argument('--before-instances', default=None, help="previous pass instances.json (which props moved this pass)")
    a = ap.parse_args()
    raw, out = Path(a.raw), Path(a.out)
    out = out if out.is_absolute() else ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    views = json.loads((raw / 'views.json').read_text(encoding='utf-8'))
    site = Site()
    labelled = []
    tag = f'BLENDER REVIEW · Sunmeadow v2 whole-map blockout · pass {a.pass_no} · {DATE}'
    if a.sightlines:
        slp = ROOT / a.sightlines
    elif (out / f'sightlines_pass{a.pass_no}.json').exists():
        slp = out / f'sightlines_pass{a.pass_no}.json'
    else:
        slp = ROOT / 'planning' / 'evidence' / 'sunmeadow-v2-blockout' / f'sightlines_pass{a.pass_no}.json'
    sl = json.loads(slp.read_text(encoding='utf-8'))['sightlines'] if slp.exists() else {}
    sl_lines = {}
    if sl:
        by_no = {k.split('_')[0]: v for k, v in sl.items()}       # result keys are '<n>_<origin>_to_<target>'
        v1 = by_no['1']['views']
        sl_lines['sl1'] = ('ray check: pine top visible ' + ', '.join(f"{k.split(' ')[0]} {v['pine_visible_top_m']} m"
                                                                      for k, v in v1.items())
                           + '; glade stone samples visible ' + ', '.join(f"{v['glade_stone_samples_visible']}" for v in v1.values()))
        v2 = by_no['2']['views']
        sl_lines['sl2'] = 'ray check: falls / pool visible share ' + ', '.join(
            f"{k.split(' ')[0]} {v['falls_visible_share']}/{v['pool_visible_share']}" for k, v in v2.items())
        v3 = by_no['3']['views']
        sl_lines['sl3'] = 'ray check: bluff face / falls visible share ' + ', '.join(
            f"{k.split(' ')[0]} {v['bluff_south_face_visible_share']}/{v['falls_visible_share']}" for k, v in v3.items())
        v4 = by_no['4']['views']
        sl_lines['sl4'] = 'ray check: hero-oak samples visible ' + ', '.join(
            f"{k.split(' ')[0]} ({v['distance_to_oak_m']} m) {v['oak_samples_visible']}" for k, v in v4.items())
    for name in ORDER:
        f = raw / f'{name}.png'
        if not f.exists():
            continue
        m = views['views'][name]
        img = Image.open(f).convert('RGB')
        lines = [m['label'], cam_line(m),
                 f"Cycles CPU {views['samples']} spp + OIDN, {img.width}x{img.height}, view '{views['view_transform']}'; "
                 f"sun SE 55 deg + blue sky fill; flat greybox colours by material; red figure = 1.8 m witness "
                 f"at {m.get('witness_xz')}; render {m.get('render_s')} s"]
        if name[:3] in sl_lines:
            lines.append(sl_lines[name[:3]])
        lab = label(img, f'{tag} · {name}', lines)
        dst = out / f'{name}.png'
        lab.save(dst)
        labelled.append(dst)
    cols = json.loads((ROOT / a.colliders).read_text(encoding='utf-8')) if (ROOT / a.colliders).exists() else None
    walk = json.loads((ROOT / a.walk).read_text(encoding='utf-8')) if (ROOT / a.walk).exists() else None
    extra = []
    if (raw / 'top.png').exists():
        top_raw = Image.open(raw / 'top.png').convert('RGB')
        plan_compare(site, top_raw, out / 'top_vs_plan.png', f'{tag} · top ortho vs PLAN')
        extra.append(out / 'top_vs_plan.png')
        if cols:
            collider_overlay(site, top_raw, cols, walk, out / 'top_colliders_overlay.png', f'{tag} · colliders + walk check')
            extra.append(out / 'top_colliders_overlay.png')
    contact_sheet(labelled, out / 'contact_sheet.png', f'{tag} · contact sheet ({len(labelled)} views)')
    if a.before:
        bdir = Path(a.before)
        bdir = bdir if bdir.is_absolute() else ROOT / bdir
        btag = bdir.name.replace('pass', 'pass ') if bdir.name.startswith('pass') else bdir.name
        if before_after(bdir, out, [n for n in ORDER if n not in ('top', 'arena_top')], out / 'before_after.png',
                        f'BLENDER REVIEW · Sunmeadow v2 blockout · {btag} vs pass {a.pass_no} (same view names)', btag):
            extra.append(out / 'before_after.png')
    inst = json.loads((ROOT / a.instances).read_text(encoding='utf-8')) if (ROOT / a.instances).exists() else None
    before_inst = json.loads((ROOT / a.before_instances).read_text(encoding='utf-8')) if a.before_instances else None
    moved = _moved_this_pass(inst, before_inst) if inst else []
    arena_json = json.loads((ROOT / a.arena).read_text(encoding='utf-8')) if a.arena else None
    if cols and inst and arena_overlay(site, raw, views, cols, inst, moved, arena_json, out / 'arena_top_overlay.png',
                                       f'{tag} · boss arena keep-clear overlay'):
        extra.append(out / 'arena_top_overlay.png')
    if a.before_glade and cols and inst:
        bdir = Path(a.before_glade)
        bdir = bdir if bdir.is_absolute() else ROOT / bdir
        btag = bdir.name.replace('pass', 'pass ') if bdir.name.startswith('pass') else bdir.name
        if glade_before_after(site, bdir, out, cols, inst, moved, out / 'before_after_glade.png',
                              f'BLENDER REVIEW · Sunmeadow v2 blockout · windstone_glade {btag} vs pass {a.pass_no} (same cameras)',
                              btag, f'pass {a.pass_no}'):
            extra.append(out / 'before_after_glade.png')
    print('labelled', len(labelled), 'extra', [p.name for p in extra], 'moved this pass', [m[0] for m in moved])


if __name__ == '__main__':
    main()
