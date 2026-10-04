"""Annotate BLENDER REVIEW renders with circled findings and build before/after pairs.

  python assets/blender/city_r5/annotate_review_r6.py annotate --views <tag_views.json> --points <points.json> \
      --out <dir> [--kinds F,S,O,Z,P,B,D,E,T] [--only id1,id2] [--title "..."]
  python assets/blender/city_r5/annotate_review_r6.py pair --before <png> --after <png> --out <png> --title "..."
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COLORS = {'F': (230, 40, 40), 'S': (255, 140, 0), 'O': (220, 40, 220), 'Z': (250, 220, 0), 'P': (0, 200, 230),
          'B': (40, 90, 255), 'D': (255, 255, 255), 'E': (60, 210, 90), 'T': (255, 90, 120), 'A': (60, 230, 140)}
NAMES = {'F': 'floating', 'S': 'sinking / buried', 'O': 'orphan child part', 'Z': 'z-fighting overlap',
         'P': 'path runs into building', 'B': 'prop in avenue band', 'D': 'duplicate house module',
         'E': 'empty filler', 'T': 'legacy starter prop floating', 'A': 'added in R6'}


def font(size):
    for f in ('C:/Windows/Fonts/segoeuib.ttf', 'C:/Windows/Fonts/arialbd.ttf', 'C:/Windows/Fonts/arial.ttf'):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def banner(img, text, sub=''):
    d = ImageDraw.Draw(img, 'RGBA')
    f, fs = font(22), font(15)
    w = max(d.textlength(text, font=f), d.textlength(sub, font=fs)) + 28
    d.rectangle([10, 10, 10 + w, 66 if sub else 44], fill=(10, 14, 22, 200))
    d.text((24, 14), text, font=f, fill=(255, 255, 255))
    if sub:
        d.text((24, 42), sub, font=fs, fill=(210, 220, 235))


def legend(img, kinds):
    d = ImageDraw.Draw(img, 'RGBA')
    f = font(14)
    x, y = 12, img.height - 20 * len(kinds) - 14
    d.rectangle([x - 4, y - 6, x + 250, img.height - 8], fill=(10, 14, 22, 190))
    for k in kinds:
        d.ellipse([x, y + 2, x + 12, y + 14], outline=COLORS[k], width=3)
        d.text((x + 20, y), f'{k}  {NAMES[k]}', font=f, fill=(240, 240, 240))
        y += 20


LENS = {'side': 40.0, 'close': 32.0, 'elevated': 34.0}
TOP_SCALE = {}


def reproject(view, points, cameras):
    """Project runtime points with the same camera model as render_review_r6.py (no re-render needed)."""
    import math
    cx, cy, cz = view['camera_blender']
    tx, ty, tz = view['target_blender']
    out = []
    if view['kind'] == 'ORTHO':
        scale = next(t['scale'] for t in cameras['tops'] if t['id'] == view['id'])
        for p in points:
            bx, by = p['x'], p['z'] - 176.0
            u, v = 0.5 + (bx - cx) / scale, 0.5 - (by - cy) / scale
            if 0 <= u <= 1 and 0 <= v <= 1:
                out.append({'id': p['id'], 'u': u, 'v': v, 'depth': 400.0})
        return out
    f = [tx - cx, ty - cy, tz - cz]
    n = math.sqrt(sum(c * c for c in f)); f = [c / n for c in f]
    r = [f[1] * 1 - f[2] * 0, f[2] * 0 - f[0] * 1, 0.0]  # f x Z
    n = math.sqrt(sum(c * c for c in r)) or 1.0; r = [c / n for c in r]
    up = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    aspect = view['width'] / view['height']
    vname = view['id'].rsplit('_', 1)[-1]
    if vname == 'player':
        tv = math.tan(1.02 / 2); th = tv * aspect
    else:
        th = 18.0 / LENS.get(vname, 40.0); tv = th / aspect
    for p in points:
        d = [p['x'] - cx, (p['z'] - 176.0) - cy, p['y'] - cz]
        zc = sum(a * b for a, b in zip(d, f))
        if zc <= 0.2:
            continue
        xc = sum(a * b for a, b in zip(d, r)); yc = sum(a * b for a, b in zip(d, up))
        u, v = 0.5 + xc / (zc * th * 2), 0.5 - yc / (zc * tv * 2)
        if 0 <= u <= 1 and 0 <= v <= 1:
            out.append({'id': p['id'], 'u': u, 'v': v, 'depth': zc})
    return out


def annotate(a):
    views = json.loads(Path(a.views).read_text(encoding='utf-8'))
    plist = json.loads(Path(a.points).read_text(encoding='utf-8'))
    pts = {p['id']: p for p in plist}
    if a.cameras:
        cams = json.loads(Path(a.cameras).read_text(encoding='utf-8'))
        for v in views['views']:
            v['points'] = reproject(v, plist, cams)
    kinds = [k for k in (a.kinds.split(',') if a.kinds else COLORS)]
    only = {s for s in a.only.split(',') if s} if a.only else None
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = Path(a.views).parent
    for v in views['views']:
        if only and v['id'] not in only:
            continue
        img = Image.open(base / v['image']).convert('RGB')
        d = ImageDraw.Draw(img, 'RGBA')
        f = font(13)
        used = set()
        drawn = 0
        for pr in v['points']:
            p = pts.get(pr['id'])
            if p is None or p['kind'] not in kinds:
                continue
            x, y = pr['u'] * img.width, pr['v'] * img.height
            r = 9 if v['kind'] == 'ORTHO' else max(8, min(40, 340 / max(pr['depth'], 4)))
            c = COLORS[p['kind']]
            d.ellipse([x - r, y - r, x + r, y + r], outline=c + (255,), width=3)
            if v['kind'] != 'ORTHO' and drawn < 40:
                d.text((x + r + 2, y - 8), p['id'], font=f, fill=c + (255,))
            used.add(p['kind'])
            drawn += 1
        banner(img, f"BLENDER REVIEW  {views['tag']}  {v['id']}", a.title or 'Cycles CPU; circles = lint/audit findings')
        if used:
            legend(img, [k for k in kinds if k in used])
        img.save(out / f"{views['tag']}_{v['id']}_annotated.png", optimize=True)
    print('annotated ->', out)


def pair(a):
    b, c = Image.open(a.before).convert('RGB'), Image.open(a.after).convert('RGB')
    w = b.width + c.width + 12
    h = max(b.height, c.height)
    img = Image.new('RGB', (w, h + 40), (14, 18, 26))
    img.paste(b, (0, 40))
    img.paste(c, (b.width + 12, 40))
    d = ImageDraw.Draw(img)
    f = font(22)
    d.text((14, 8), 'BEFORE  r5-market-gate-20261001', font=f, fill=(255, 210, 200))
    d.text((b.width + 26, 8), 'AFTER  r6-candidate (not admitted)', font=f, fill=(200, 255, 215))
    if a.title:
        d.text((w // 2 - d.textlength(a.title, font=f) // 2, h + 40 - 30), a.title, font=f, fill=(255, 255, 255))
    if a.scale and a.scale != 1.0:
        img = img.resize((int(img.width * a.scale), int(img.height * a.scale)), Image.LANCZOS)
    img.save(a.out, optimize=True)
    print('pair ->', a.out)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p1 = sub.add_parser('annotate')
    p1.add_argument('--views', required=True)
    p1.add_argument('--points', required=True)
    p1.add_argument('--out', required=True)
    p1.add_argument('--kinds', default='')
    p1.add_argument('--only', default='')
    p1.add_argument('--title', default='')
    p1.add_argument('--cameras', default='')
    p2 = sub.add_parser('pair')
    p2.add_argument('--before', required=True)
    p2.add_argument('--after', required=True)
    p2.add_argument('--out', required=True)
    p2.add_argument('--title', default='')
    p2.add_argument('--scale', type=float, default=1.0)
    a = ap.parse_args()
    annotate(a) if a.cmd == 'annotate' else pair(a)


if __name__ == '__main__':
    main()
