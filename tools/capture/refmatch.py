"""Reference-match mode (gauntlet loop Stage C): an in-engine capture against a 2D reference (e.g. 16:9 key art).

python tools/capture/refmatch.py --reference ref.jpg --capture shot.png --out <dir>
       [--exclude-ref x0,y0,x1,y1 ...] [--exclude-cap x0,y0,x1,y1 ...]   (fractions 0..1 or pixels; HUD/UI boxes to ignore)
       [--ref-mask mask.png] [--cap-mask mask.png]                      (silhouette IoU; alpha channels are used when present)
       [--work 960] [--title "..."]

The composition is never pixel-identical, so only global statistics are compared:
mean luma, contrast (luma p90 - p10), luma-histogram EMD, mean saturation, a 6-colour palette matched by
CIEDE2000, and silhouette IoU when masks exist. Gates come from docs/plans/2026-10-02-reference-gauntlet-loop.md.
Luma is Rec.709 Y' of gamma-encoded sRGB (0..1); saturation is HSV S = (max - min) / max.
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import linear_sum_assignment

from imaging import delta_e2000, lab_to_srgb, load_alpha, load_rgb, luma, save_jpeg, srgb_to_lab

GATES = {  # metric: (kind, limit)
    "meanLuma": ("abs-delta", 0.05),
    "contrast": ("abs-delta", 0.05),
    "histogramEmd": ("max", 0.06),
    "saturation": ("abs-delta", 0.06),
    "paletteDeltaE00": ("max", 8.0),
    "silhouetteIoU": ("min", 0.85),
}
LABELS = {"meanLuma": "Mean luminance (Y')", "contrast": "Contrast (luma p90 − p10)", "histogramEmd": "Luma-histogram distance (EMD)",
          "saturation": "Saturation mean (HSV S)", "paletteDeltaE00": "Palette ΔE00 (6 dominant, matched)", "silhouetteIoU": "Silhouette IoU (assets only)"}
BINS = 64


def parse_box(text: str) -> tuple[float, float, float, float]:
    values = [float(part) for part in text.split(",")]
    if len(values) != 4:
        raise argparse.ArgumentTypeError("box must be x0,y0,x1,y1")
    return tuple(values)  # type: ignore[return-value]


def include_mask(shape: tuple[int, int], boxes: list[tuple[float, float, float, float]]) -> np.ndarray:
    height, width = shape
    mask = np.ones((height, width), dtype=bool)
    for x0, y0, x1, y1 in boxes:
        if max(x0, y0, x1, y1) <= 1.0:
            x0, x1, y0, y1 = x0 * width, x1 * width, y0 * height, y1 * height
        mask[max(0, int(y0)):min(height, int(np.ceil(y1))), max(0, int(x0)):min(width, int(np.ceil(x1)))] = False
    return mask


def work_size(image: np.ndarray, width: int) -> np.ndarray:
    pil = Image.fromarray(image)
    scale = width / pil.width
    return np.asarray(pil.resize((width, max(1, round(pil.height * scale))), Image.Resampling.LANCZOS)) if scale < 1 else image


def kmeans_lab(lab: np.ndarray, k: int = 6, iterations: int = 25, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic k-means++ in CIELAB on a pixel sample; returns centers sorted by share and the shares."""
    rng = np.random.default_rng(seed)
    sample = lab[rng.choice(len(lab), size=min(len(lab), 40000), replace=False)].astype(np.float64)
    centers = [sample[rng.integers(len(sample))]]
    for _ in range(1, k):
        distance = np.min(((sample[:, None, :] - np.array(centers)[None]) ** 2).sum(axis=2), axis=1)
        centers.append(sample[rng.choice(len(sample), p=distance / distance.sum())])
    centers = np.array(centers)
    for _ in range(iterations):
        labels = np.argmin(((sample[:, None, :] - centers[None]) ** 2).sum(axis=2), axis=1)
        updated = np.array([sample[labels == index].mean(axis=0) if np.any(labels == index) else centers[index] for index in range(k)])
        if np.allclose(updated, centers, atol=1e-3):
            break
        centers = updated
    labels = np.argmin(((sample[:, None, :] - centers[None]) ** 2).sum(axis=2), axis=1)
    shares = np.bincount(labels, minlength=k) / len(labels)
    order = np.argsort(shares)[::-1]
    return centers[order], shares[order]


def stats(rgb: np.ndarray, include: np.ndarray) -> dict:
    y = luma(rgb)[include]
    value = rgb.astype(np.float32)[include] / 255.0
    high, low = value.max(axis=1), value.min(axis=1)
    saturation = np.where(high > 0, (high - low) / np.maximum(high, 1e-6), 0)
    histogram = np.histogram(y, bins=BINS, range=(0, 1))[0].astype(np.float64)
    histogram /= max(1.0, histogram.sum())
    centers, shares = kmeans_lab(srgb_to_lab(rgb[include]))
    return {"meanLuma": float(y.mean()), "contrast": float(np.percentile(y, 90) - np.percentile(y, 10)), "p10": float(np.percentile(y, 10)),
            "p90": float(np.percentile(y, 90)), "saturation": float(saturation.mean()), "histogram": histogram.tolist(),
            "palette": [{"lab": [round(float(v), 2) for v in center], "hex": "#%02x%02x%02x" % tuple(int(c) for c in lab_to_srgb(center)), "share": round(float(share), 4)}
                        for center, share in zip(centers, shares)], "pixels": int(include.sum())}


def emd(a: list[float], b: list[float]) -> float:
    """1-D earth mover's distance between normalised histograms on [0, 1] (mass x luma distance)."""
    return float(np.abs(np.cumsum(a) - np.cumsum(b)).sum() / BINS)


def palette_match(ref: list[dict], cap: list[dict]) -> dict:
    lab_ref, lab_cap = np.array([p["lab"] for p in ref]), np.array([p["lab"] for p in cap])
    matrix = delta_e2000(lab_ref[:, None, :], lab_cap[None, :, :])
    rows, cols = linear_sum_assignment(matrix)
    pairs, total, weight = [], 0.0, 0.0
    for r, c in zip(rows, cols):
        w = (ref[r]["share"] + cap[c]["share"]) / 2
        pairs.append({"ref": ref[r]["hex"], "cap": cap[c]["hex"], "refShare": ref[r]["share"], "capShare": cap[c]["share"], "deltaE00": round(float(matrix[r, c]), 2)})
        total += w * matrix[r, c]
        weight += w
    pairs.sort(key=lambda pair: -(pair["refShare"] + pair["capShare"]))
    return {"weightedMean": round(total / weight, 2), "max": round(float(max(pair["deltaE00"] for pair in pairs)), 2), "pairs": pairs}


def mask_of(path: Path | None, image_path: Path, size: tuple[int, int]) -> np.ndarray | None:
    source = load_alpha(path) if path and path.suffix.lower() == ".png" and load_alpha(path) is not None else None
    if path and source is None:
        source = np.asarray(Image.open(path).convert("L"))
    if source is None:
        source = load_alpha(image_path)
    if source is None:
        return None
    mask = np.asarray(Image.fromarray(source).resize(size, Image.Resampling.NEAREST)) > 127
    return None if mask.all() or not mask.any() else mask  # an opaque frame or an empty mask is not a silhouette


def gate(metric: str, ref_value: float | None, cap_value: float | None, value: float | None) -> dict:
    kind, limit = GATES[metric]
    if value is None:
        return {"metric": metric, "label": LABELS[metric], "gate": f"{'≥' if kind == 'min' else '≤'} {limit}" if kind != "abs-delta" else f"±{limit}", "ref": ref_value, "capture": cap_value,
                "value": None, "status": "N/A"}
    ok = abs(value) <= limit if kind == "abs-delta" else value <= limit if kind == "max" else value >= limit
    return {"metric": metric, "label": LABELS[metric], "gate": f"±{limit}" if kind == "abs-delta" else f"≤ {limit}" if kind == "max" else f"≥ {limit}",
            "ref": None if ref_value is None else round(ref_value, 4), "capture": None if cap_value is None else round(cap_value, 4), "value": round(value, 4), "status": "PASS" if ok else "FAIL"}


def preview(rgb: np.ndarray, boxes: list, path: Path) -> None:
    image = Image.fromarray(rgb).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    for x0, y0, x1, y1 in boxes:
        if max(x0, y0, x1, y1) <= 1.0:
            x0, x1, y0, y1 = x0 * image.width, x1 * image.width, y0 * image.height, y1 * image.height
        draw.rectangle((x0, y0, x1, y1), fill=(0, 0, 0, 150), outline=(255, 80, 80, 255), width=max(2, image.width // 480))
    save_jpeg(image, path, max_side=1280)


def run(args: argparse.Namespace) -> dict:
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    ref_full, cap_full = load_rgb(args.reference), load_rgb(args.capture)
    ref, cap = work_size(ref_full, args.work), work_size(cap_full, args.work)
    ref_stats = stats(ref, include_mask(ref.shape[:2], args.exclude_ref))
    cap_stats = stats(cap, include_mask(cap.shape[:2], args.exclude_cap))
    palette = palette_match(ref_stats["palette"], cap_stats["palette"])
    iou = None
    ref_mask, cap_mask = mask_of(args.ref_mask, args.reference, (256, 256)), mask_of(args.cap_mask, args.capture, (256, 256))
    if ref_mask is not None and cap_mask is not None:
        union = np.logical_or(ref_mask, cap_mask).sum()
        iou = float(np.logical_and(ref_mask, cap_mask).sum() / union) if union else None
    gates = [gate("meanLuma", ref_stats["meanLuma"], cap_stats["meanLuma"], cap_stats["meanLuma"] - ref_stats["meanLuma"]),
             gate("contrast", ref_stats["contrast"], cap_stats["contrast"], cap_stats["contrast"] - ref_stats["contrast"]),
             gate("histogramEmd", None, None, emd(ref_stats["histogram"], cap_stats["histogram"])),
             gate("saturation", ref_stats["saturation"], cap_stats["saturation"], cap_stats["saturation"] - ref_stats["saturation"]),
             gate("paletteDeltaE00", None, None, palette["weightedMean"]),
             gate("silhouetteIoU", None, None, iou)]
    automatic = [g for g in gates if g["status"] != "N/A"]
    verdict = "PASS" if all(g["status"] == "PASS" for g in automatic) else "FAIL"
    preview(ref_full, args.exclude_ref, out / "reference.jpg")
    preview(cap_full, args.exclude_cap, out / "capture.jpg")
    report = {"schema": "xexoria-refmatch/1", "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"), "title": args.title,
              "reference": str(args.reference), "capture": str(args.capture), "workWidth": args.work, "excludeRef": args.exclude_ref, "excludeCap": args.exclude_cap,
              "verdict": verdict, "gates": gates, "rubric": "Art rubric (shape, value, colour, material read, detail density, readability at 13 m): manual, ≥ 85/100 and every line ≥ 4/5",
              "palette": palette, "referenceStats": {k: v for k, v in ref_stats.items() if k != "histogram"}, "captureStats": {k: v for k, v in cap_stats.items() if k != "histogram"},
              "histograms": {"bins": BINS, "reference": ref_stats["histogram"], "capture": cap_stats["histogram"]}}
    (out / "refmatch.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out / "report.html").write_text(render(report), encoding="utf-8")
    return report


def histogram_svg(ref: list[float], cap: list[float]) -> str:
    peak = max(max(ref), max(cap), 1e-9)
    def path(values):
        return " ".join(f"{i / (len(values) - 1) * 600:.1f},{200 - v / peak * 190:.1f}" for i, v in enumerate(values))
    return (f"<svg viewBox='0 0 600 220' role='img' aria-label='Luma histograms'><rect x='0' y='0' width='600' height='200' fill='none' stroke='var(--line)'/>"
            f"<polyline points='{path(ref)}' fill='none' stroke='var(--ref)' stroke-width='2.5'/><polyline points='{path(cap)}' fill='none' stroke='var(--cap)' stroke-width='2.5'/>"
            "<text x='0' y='216' font-size='12' fill='var(--muted)'>0 (dark)</text><text x='600' y='216' font-size='12' fill='var(--muted)' text-anchor='end'>1 (bright)</text></svg>")


def swatches(palette: list[dict]) -> str:
    return "".join(f"<span class='sw' style='background:{p['hex']};flex:{max(0.05, p['share'])}' title='{p['hex']} · {p['share'] * 100:.1f} %'><i>{p['share'] * 100:.0f}%</i></span>" for p in palette)


def render(report: dict) -> str:
    rows = "".join(f"<tr><td>{html.escape(g['label'])}</td><td class='{g['status'].lower().replace('/', '')}'>{g['status']}</td><td>{'–' if g['value'] is None else g['value']}</td><td>{html.escape(g['gate'])}</td>"
                   f"<td>{'–' if g['ref'] is None else g['ref']}</td><td>{'–' if g['capture'] is None else g['capture']}</td></tr>" for g in report["gates"])
    pairs = "".join(f"<tr><td><span class='dot' style='background:{p['ref']}'></span>{p['ref']} ({p['refShare'] * 100:.0f} %)</td><td><span class='dot' style='background:{p['cap']}'></span>{p['cap']} ({p['capShare'] * 100:.0f} %)</td><td>{p['deltaE00']}</td></tr>"
                    for p in report["palette"]["pairs"])
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Reference match</title><style>
:root{{--bg:#f6f4ef;--fg:#1d2329;--muted:#5c6670;--card:#fff;--line:#d9d4c7;--pass:#1f7a43;--fail:#b3261e;--ref:#2a6fdb;--cap:#d9822b}}
@media (prefers-color-scheme: dark){{:root:not([data-theme=light]){{--bg:#11161b;--fg:#e8e4da;--muted:#9aa6b1;--card:#1a2128;--line:#2c3640;--pass:#5ccf8a;--fail:#ff8a80;--ref:#7fb0ff;--cap:#ffb366}}}}
:root[data-theme=dark]{{--bg:#11161b;--fg:#e8e4da;--muted:#9aa6b1;--card:#1a2128;--line:#2c3640;--pass:#5ccf8a;--fail:#ff8a80;--ref:#7fb0ff;--cap:#ffb366}}
*{{box-sizing:border-box}}body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}h1{{font-size:20px;margin:0 0 4px}}h2{{font-size:16px;margin:18px 0 8px}}
.grid{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr))}}figure{{margin:0}}img{{width:100%;height:auto;border-radius:6px;display:block}}figcaption,.muted{{color:var(--muted);font-size:12.5px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}}.wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%}}td,th{{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap;font-variant-numeric:tabular-nums}}
.pass{{color:var(--pass);font-weight:700}}.fail{{color:var(--fail);font-weight:700}}.na{{color:var(--muted)}}.big{{font-size:18px}}.bar{{display:flex;height:40px;border-radius:6px;overflow:hidden;margin:4px 0 10px}}
.sw{{position:relative;min-width:18px}}.sw i{{position:absolute;bottom:2px;left:3px;font:10px system-ui;color:#fff;text-shadow:0 0 3px #000}}.dot{{display:inline-block;width:14px;height:14px;border-radius:3px;margin-right:6px;vertical-align:-2px;border:1px solid var(--line)}}
.legend b{{display:inline-block;width:18px;height:4px;margin:0 6px 3px 12px;vertical-align:middle}}svg{{width:100%;height:auto}}
</style></head><body>
<h1>Reference match{(': ' + html.escape(report['title'])) if report.get('title') else ''}</h1>
<p class='big'>Verdict: <span class='{report['verdict'].lower()}'>{report['verdict']}</span> <span class='muted'>(automatic gates only; the art rubric is scored by a reviewer)</span></p>
<div class='grid'><figure class='card'><img src='reference.jpg' alt='reference'><figcaption>Reference · {html.escape(Path(report['reference']).name)} · excluded boxes shaded red</figcaption></figure>
<figure class='card'><img src='capture.jpg' alt='capture'><figcaption>Capture · {html.escape(Path(report['capture']).name)}</figcaption></figure></div>
<h2>Gates</h2><div class='card wrap'><table><tr><th>metric</th><th>result</th><th>value</th><th>gate</th><th>reference</th><th>capture</th></tr>{rows}
<tr><td>Art rubric</td><td class='na'>MANUAL</td><td colspan='4' class='muted' style='white-space:normal'>{html.escape(report['rubric'])}</td></tr></table></div>
<div class='grid'><div class='card'><h2>Luma histograms</h2><p class='legend muted'><b style='background:var(--ref)'></b>reference<b style='background:var(--cap)'></b>capture · EMD {report['gates'][2]['value']}</p>{histogram_svg(report['histograms']['reference'], report['histograms']['capture'])}</div>
<div class='card'><h2>Palettes (6 dominant colours, CIELAB k-means)</h2><p class='muted'>Reference</p><div class='bar'>{swatches(report['referenceStats']['palette'])}</div>
<p class='muted'>Capture</p><div class='bar'>{swatches(report['captureStats']['palette'])}</div>
<div class='wrap'><table><tr><th>reference</th><th>matched capture</th><th>ΔE00</th></tr>{pairs}</table></div><p class='muted'>Share-weighted mean ΔE00 {report['palette']['weightedMean']} · worst pair {report['palette']['max']}</p></div></div>
<p class='muted'>Luma = Rec.709 Y' of gamma-encoded sRGB; saturation = HSV S; both images analysed at {report['workWidth']} px wide. Generated {html.escape(report['createdAt'])}. Gates: docs/plans/2026-10-02-reference-gauntlet-loop.md (Stage C).</p>
</body></html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exclude-ref", type=parse_box, nargs="*", default=[])
    parser.add_argument("--exclude-cap", type=parse_box, nargs="*", default=[])
    parser.add_argument("--ref-mask", type=Path)
    parser.add_argument("--cap-mask", type=Path)
    parser.add_argument("--work", type=int, default=960)
    parser.add_argument("--title")
    result = run(parser.parse_args())
    for item in result["gates"]:
        print(f"{item['label']:44s} value {item['value']!s:>8}  gate {item['gate']:>7}  {item['status']}")
    print(f"verdict {result['verdict']}")
