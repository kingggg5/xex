"""Before/after comparison of two capture runs (tools/capture/capture.mjs output).

python tools/capture/compare.py --before <runDir> --after <runDir> --out <reportDir>
                                [--noise <A/A report.json>] [--aa] [--title "..."] [--threshold 16]

Per shot: SSIM (luma, Gaussian window), PSNR, MAE/RMSE/max delta, changed area at two thresholds, an amplified
diff heatmap with hotspot boxes, the shape of the change (tie flip / scattered / solid), metric deltas, the
frame-p95 regression rule (worse by more than 10 % or 1 ms, after subtracting the A/A noise floor when given),
and temporal-burst deltas when both shots carry one. Writes report.json and a static report.html.
--aa marks an A/A self-compare: its per-shot values become the noise floor for later compares (--noise).
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from imaging import inferno_lut, load_rgb, luma, mask_shape, save_jpeg

DEFAULTS = {"threshold": 16, "strong": 48, "pct_over": 8, "same_changed_pct": 0.5, "same_ssim": 0.995, "minor_changed_pct": 2.0, "minor_ssim": 0.98,
            "perf_abs_ms": 1.0, "perf_rel": 0.10, "flake_changed_pct": 1.0, "flake_ssim": 0.99}
PERF_KEYS = ("frameP50", "frameP95", "frameP99", "cpuP50", "cpuP95", "gpuP50", "gpuP95", "drawCalls", "activeMeshes", "triangles", "particles", "heapMB", "fps")


def ssim_luma(a: np.ndarray, b: np.ndarray) -> float:
    """Wang et al. 2004 SSIM on Rec.709 luma (0..255), Gaussian window sigma 1.5."""
    x, y = luma(a).astype(np.float64) * 255, luma(b).astype(np.float64) * 255
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    blur = lambda image: ndimage.gaussian_filter(image, 1.5, truncate=3.5)
    mx, my = blur(x), blur(y)
    sxx, syy, sxy = blur(x * x) - mx * mx, blur(y * y) - my * my, blur(x * y) - mx * my
    value = ((2 * mx * my + c1) * (2 * sxy + c2)) / ((mx * mx + my * my + c1) * (sxx + syy + c2))
    return float(value.mean())


def pixel_metrics(a: np.ndarray, b: np.ndarray, options: dict) -> tuple[dict, np.ndarray]:
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    maxdiff = diff.max(axis=2).astype(np.uint8)
    mse = float((diff.astype(np.float64) ** 2).mean())
    blurred = ndimage.gaussian_filter(maxdiff.astype(np.float32), 4)
    worst = np.unravel_index(int(np.argmax(blurred)), blurred.shape)
    changed = maxdiff > options["threshold"]
    metrics = {
        "ssim": round(ssim_luma(a, b), 5), "psnr": None if mse == 0 else round(10 * math.log10(255 ** 2 / mse), 2),
        "mae": round(float(diff.mean()), 4), "rmse": round(math.sqrt(mse), 4), "maxDelta": int(maxdiff.max()),
        "pctOver8": round(float((maxdiff > options["pct_over"]).mean() * 100), 4), "changedPct": round(float(changed.mean() * 100), 4),
        "strongPct": round(float((maxdiff > options["strong"]).mean() * 100), 4), "worstAt": {"x": int(worst[1]), "y": int(worst[0])},
        "shape": mask_shape(changed),
    }
    return metrics, maxdiff


def heatmap(after: np.ndarray, maxdiff: np.ndarray, shape: dict, gain: float = 4.0) -> Image.Image:
    lut = inferno_lut()
    amplified = np.clip(maxdiff.astype(np.float32) * gain, 0, 255).astype(np.uint8)
    gray = (luma(after) * 255 * 0.3).astype(np.uint8)
    heat = lut[amplified].astype(np.float32)
    weight = (amplified.astype(np.float32) / 255.0)[..., None] ** 0.5
    out = gray[..., None].astype(np.float32) * (1 - weight) + heat * weight
    image = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image)
    width = max(2, image.width // 400)
    for index, box in enumerate(shape.get("hotspots", [])):
        draw.rectangle((box["x"] - 3, box["y"] - 3, box["x"] + box["w"] + 3, box["y"] + box["h"] + 3), outline=(80, 220, 255), width=width)
        draw.text((box["x"] + 2, max(0, box["y"] - 18)), str(index + 1), fill=(80, 220, 255))
    return image


def perf_block(before: dict, after: dict, noise: dict | None, options: dict) -> dict:
    delta = {key: None if not isinstance(before.get(key), (int, float)) or not isinstance(after.get(key), (int, float)) else round(after[key] - before[key], 3) for key in PERF_KEYS}
    base, change = before.get("frameP95"), delta["frameP95"]
    floor = (noise or {}).get("frameP95") or 0.0
    flagged, beyond = False, None
    if isinstance(base, (int, float)) and change is not None:
        beyond = round(math.copysign(max(0.0, abs(change) - floor), change), 3)
        flagged = beyond > options["perf_abs_ms"] or (base > 0 and beyond / base > options["perf_rel"])
    return {"before": {key: before.get(key) for key in PERF_KEYS}, "after": {key: after.get(key) for key in PERF_KEYS}, "delta": delta,
            "frameP95BeyondNoise": beyond, "noiseFrameP95": floor or None, "flagged": flagged,
            "rule": f"frame p95 worse by > {options['perf_rel'] * 100:.0f} % or > {options['perf_abs_ms']} ms" + (" after subtracting the A/A floor" if floor else "")}


def visual_verdict(metrics: dict | None, floor: dict | None, options: dict) -> str:
    if metrics is None:
        return "incomparable"
    if metrics["maxDelta"] == 0:
        return "identical"
    same_changed = options["same_changed_pct"] if not floor else max(options["same_changed_pct"], floor["changedPct"] * 1.5 + 0.05)
    same_ssim = options["same_ssim"] if not floor else min(options["same_ssim"], 1 - (1 - floor["ssim"]) * 1.5 - 0.001)
    if metrics["changedPct"] <= same_changed and metrics["ssim"] >= same_ssim:
        return "within noise"
    if metrics["changedPct"] <= options["minor_changed_pct"] and metrics["ssim"] >= options["minor_ssim"]:
        return "minor change"
    return "changed"


def temporal_block(run_before: Path, run_after: Path, detail_before: dict, detail_after: dict, out_dir: Path, shot_id: str, frame: np.ndarray) -> dict | None:
    tb, ta = detail_before.get("temporal"), detail_after.get("temporal")
    if not tb and not ta:
        return None
    block = {}
    for side, temporal, run in (("before", tb, run_before), ("after", ta, run_after)):
        if not temporal or temporal.get("error") or not temporal.get("togglesFile"):
            block[side] = {"error": (temporal or {}).get("error", "no temporal burst")}
            continue
        toggles = np.asarray(Image.open(run / temporal["togglesFile"]).convert("L"))
        shape = mask_shape(toggles >= 32, min_size=8)
        block[side] = {key: temporal.get(key) for key in ("frames", "width", "height", "meanEnvelope", "p99Envelope", "pctEnvelopeOver8", "pctTogglers")}
        block[side]["shape"] = shape
        if side == "after":
            small = np.asarray(Image.fromarray(frame).resize((toggles.shape[1], toggles.shape[0]), Image.Resampling.BILINEAR))
            lut = inferno_lut()
            weight = (np.clip(toggles.astype(np.float32) * 2, 0, 255) / 255)[..., None]
            overlay = (luma(small)[..., None] * 255 * 0.35) * (1 - weight) + lut[np.clip(toggles.astype(np.int32) * 2, 0, 255)].astype(np.float32) * weight
            overlay_image = Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8))
            draw = ImageDraw.Draw(overlay_image)
            for index, box in enumerate(shape.get("hotspots", [])):
                draw.rectangle((box["x"] - 2, box["y"] - 2, box["x"] + box["w"] + 2, box["y"] + box["h"] + 2), outline=(80, 220, 255), width=2)
                draw.text((box["x"] + 2, max(0, box["y"] - 14)), str(index + 1), fill=(80, 220, 255))
            save_jpeg(overlay_image, out_dir / "img" / f"{shot_id}-flicker.jpg", max_side=960)
            block["overlay"] = f"img/{shot_id}-flicker.jpg"
    if "pctTogglers" in block.get("before", {}) and "pctTogglers" in block.get("after", {}):
        before, after = block["before"]["pctTogglers"], block["after"]["pctTogglers"]
        block["deltaPctTogglers"] = round(after - before, 3)
        block["flagged"] = after - before > max(0.5, before * 0.5)
    return block


def machine_busy(run: dict, shot: dict) -> bool:
    load = (run.get("loads") or {}).get(shot.get("load")) or {}
    if "machineBusy" in load:
        return bool(load["machineBusy"])
    start, end = load.get("machineLoad") or {}, load.get("machineLoadEnd") or {}
    return bool(start.get("blenderRunning") or end.get("blenderRunning") or (start.get("cpuBusyPct") or 0) >= 60)


def machine_note(run: dict, shot: dict) -> str:
    load = (run.get("loads") or {}).get(shot.get("load")) or {}
    start, end = load.get("machineLoad") or {}, load.get("machineLoadEnd") or {}
    return f"CPU {start.get('cpuBusyPct')} % at start, Blender {'running' if start.get('blenderRunning') or end.get('blenderRunning') else 'off'}"


def load_run(path: Path) -> dict:
    run = json.loads((path / "run.json").read_text(encoding="utf-8"))
    run["_dir"] = path
    return run


def detail_of(run: dict, shot_id: str) -> dict:
    path = run["_dir"] / "shots" / f"{shot_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def compare(before_dir: Path, after_dir: Path, out_dir: Path, noise_path: Path | None, is_aa: bool, title: str | None, options: dict) -> dict:
    before, after = load_run(before_dir), load_run(after_dir)
    noise = json.loads(noise_path.read_text(encoding="utf-8")) if noise_path else None
    floors = {shot["id"]: shot for shot in (noise or {}).get("shots", [])}
    def median_floor(renderer):
        values = [shot.get("perf", {}).get("noiseFrameP95Measured") for shot in floors.values()
                  if shot.get("renderer") == renderer and not shot.get("perf", {}).get("invalidCapture")]
        values = [value for value in values if isinstance(value, (int, float))]
        return float(np.median(values)) if values else None
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = [shot_id for shot_id in before["shots"] if shot_id in after["shots"]]
    results = []
    for shot_id in ids:
        sb, sa = before["shots"][shot_id], after["shots"][shot_id]
        db, da = detail_of(before, shot_id), detail_of(after, shot_id)
        a, b = load_rgb(before_dir / sb["image"]), load_rgb(after_dir / sa["image"])
        files = {"before": f"img/{shot_id}-before.jpg", "after": f"img/{shot_id}-after.jpg", "diff": f"img/{shot_id}-diff.jpg",
                 "beforePng": os.path.relpath(before_dir / sb["image"], out_dir).replace("\\", "/"), "afterPng": os.path.relpath(after_dir / sa["image"], out_dir).replace("\\", "/")}
        save_jpeg(a, out_dir / files["before"]); save_jpeg(b, out_dir / files["after"])
        floor_shot = floors.get(shot_id)
        floor_visual = floor_shot["visual"] if floor_shot and floor_shot.get("visual") else None
        phase = [(d.get("clock") or {}).get("frameAtShot") for d in (db, da)]
        phase_mismatch = None not in phase and phase[0] != phase[1]
        if a.shape != b.shape:
            metrics, verdict = None, "incomparable"
            Image.new("RGB", (640, 360), (40, 0, 0)).save(out_dir / files["diff"])
        else:
            metrics, maxdiff = pixel_metrics(a, b, options)
            verdict = visual_verdict(metrics, floor_visual, options)
            if phase_mismatch and verdict not in ("identical", "within noise"):
                verdict = "phase mismatch"  # animation state differs (other views, warm-up or sample counts): not evidence of a change
            save_jpeg(heatmap(b, maxdiff, metrics["shape"]), out_dir / files["diff"])
        shot_floor = (floor_shot or {}).get("perf", {}).get("noiseFrameP95Measured")
        perf = perf_block(sb, sa, {"frameP95": max(shot_floor or 0.0, median_floor(sb.get("renderer")) or 0.0)} if floor_shot else None, options)
        invalid = [f"before {sb.get('verdict')}" for _ in [0] if sb.get("verdict") not in (None, "OK")] + [f"after {sa.get('verdict')}" for _ in [0] if sa.get("verdict") not in (None, "OK")]
        if invalid:  # a blank / GPU-invalid / hidden capture has no meaningful frame time
            perf["invalidCapture"] = ", ".join(invalid)
            perf["flagged"] = False
        perf["spread"] = {"before": sb.get("frameP95Spread"), "after": sa.get("frameP95Spread")}
        busy = [f"{side}: {machine_note(run, shot)}" for side, run, shot in (("before", before, sb), ("after", after, sa)) if machine_busy(run, shot)]
        if busy and not perf.get("invalidCapture"):  # another heavy job shared the PC: the delta is not evidence of a regression
            perf["unqualified"] = "; ".join(busy)
            perf["wouldFlag"] = perf["flagged"]
            perf["flagged"] = False
        temporal = temporal_block(before_dir, after_dir, db, da, out_dir, shot_id, b)
        flake = None
        if is_aa and metrics and (metrics["changedPct"] > options["flake_changed_pct"] or metrics["ssim"] < options["flake_ssim"]):
            flake = f"A/A noise above the declared floor: changed {metrics['changedPct']} %, SSIM {metrics['ssim']} ({metrics['shape']['kind']})"
        if is_aa:
            perf["noiseFrameP95Measured"] = abs(perf["delta"]["frameP95"]) if perf["delta"]["frameP95"] is not None else None
        results.append({"id": shot_id, "scene": sb.get("scene"), "view": sb.get("view"), "time": sb.get("time"), "renderer": sb.get("renderer"),
                        "size": f"{a.shape[1]}x{a.shape[0]}", "visual": metrics, "visualVerdict": verdict, "noiseFloor": floor_visual, "knownFlake": flake or (floor_shot or {}).get("knownFlake"),
                        "perf": perf, "temporal": temporal, "files": files, "frameAtShot": {"before": phase[0], "after": phase[1]},
                        "settled": {"before": (db.get("settled") or {}).get("settled"), "after": (da.get("settled") or {}).get("settled")},
                        "method": {"before": sb.get("method"), "after": sa.get("method")}, "blank": {"before": sb.get("blank"), "after": sa.get("blank")}})
        print(f"{shot_id:48s} ssim {metrics['ssim'] if metrics else '-':>8} changed {metrics['changedPct'] if metrics else '-':>7} % {verdict:13s} p95 {sb.get('frameP95')} -> {sa.get('frameP95')}{'  FLAG' if perf['flagged'] else ''}")
    counts = {}
    for result in results:
        counts[result["visualVerdict"]] = counts.get(result["visualVerdict"], 0) + 1
    ssims = [r["visual"]["ssim"] for r in results if r["visual"]]
    changed = [r["visual"]["changedPct"] for r in results if r["visual"]]
    summary = {"shots": len(results), "visual": counts, "perfFlags": sum(1 for r in results if r["perf"]["flagged"]),
               "perfUnqualified": sum(1 for r in results if r["perf"].get("unqualified")), "perfInvalid": sum(1 for r in results if r["perf"].get("invalidCapture")),
               "perfQualified": sum(1 for r in results if not r["perf"].get("unqualified") and not r["perf"].get("invalidCapture")),
               "temporalFlags": sum(1 for r in results if r.get("temporal") and r["temporal"].get("flagged")),
               "minSsim": min(ssims) if ssims else None, "medianSsim": float(np.median(ssims)) if ssims else None, "maxChangedPct": max(changed) if changed else None,
               "medianChangedPct": float(np.median(changed)) if changed else None, "knownFlakes": [r["id"] for r in results if r.get("knownFlake")],
               "onlyBefore": [i for i in before["shots"] if i not in after["shots"]], "onlyAfter": [i for i in after["shots"] if i not in before["shots"]]}
    report = {"schema": "xexoria-capture-compare/1", "kind": "aa" if is_aa else "ab", "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
              "title": title or f"{before['label']} vs {after['label']}",
              "before": {"label": before["label"], "build": before.get("build"), "git": before.get("git"), "browser": (before.get("browser") or {}).get("version"), "dir": str(before_dir)},
              "after": {"label": after["label"], "build": after.get("build"), "git": after.get("git"), "browser": (after.get("browser") or {}).get("version"), "dir": str(after_dir)},
              "options": options, "noiseSource": str(noise_path) if noise_path else None, "summary": summary, "shots": results}
    if is_aa:
        for result in report["shots"]:
            result["noiseFloor"] = result["visual"]
    (out_dir / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out_dir / "report.html").write_text(render_html(report), encoding="utf-8")
    return report


def fmt(value, digits=2, suffix=""):
    if value is None:
        return "–"
    if isinstance(value, float) and math.isinf(value):
        return "∞"
    return f"{value:.{digits}f}{suffix}" if isinstance(value, (int, float)) else html.escape(str(value))


def signed(value, digits=2, suffix=""):
    return "–" if value is None else f"{value:+.{digits}f}{suffix}"


def render_html(report: dict) -> str:
    s = report["summary"]
    chips = [f"<span class='chip'>{s['shots']} shots</span>"] + [f"<span class='chip v-{k.replace(' ', '-')}'>{v} {html.escape(k)}</span>" for k, v in s["visual"].items()]
    chips.append(f"<span class='chip {'bad' if s['perfFlags'] else 'good'}'>{s['perfFlags']} perf flags</span>")
    chips.append(f"<span class='chip'>{s.get('perfQualified', 0)} perf qualified · {s.get('perfUnqualified', 0)} machine-busy · {s.get('perfInvalid', 0)} invalid</span>")
    if s["temporalFlags"]:
        chips.append(f"<span class='chip bad'>{s['temporalFlags']} flicker flags</span>")
    rows, cards = [], []
    for r in report["shots"]:
        v, p = r["visual"] or {}, r["perf"]
        flag = "<b class='flag'>p95 ▲</b>" if p["flagged"] else "<span class='muted'>invalid capture</span>" if p.get("invalidCapture") else "<span class='warn'>unqualified</span>" if p.get("unqualified") else ""
        rows.append(f"<tr><td><a href='#{r['id']}'>{html.escape(r['id'])}</a></td><td class='v-{r['visualVerdict'].replace(' ', '-')}'>{html.escape(r['visualVerdict'])}</td><td>{flag or '–'}</td>"
                    f"<td>{fmt(v.get('ssim'), 4)}</td><td>{fmt(v.get('changedPct'), 2, ' %')}</td><td>{fmt(v.get('psnr'), 1) if v.get('psnr') is not None else ('∞' if v else '–')}</td>"
                    f"<td>{fmt(p['before']['frameP95'])} → {fmt(p['after']['frameP95'])}</td><td>{signed(p['delta']['frameP95'])}</td><td>{signed(p['delta']['cpuP95'])}</td></tr>")
        metric_rows = "".join(f"<tr><th>{label}</th><td>{fmt(p['before'][key], d)}</td><td>{fmt(p['after'][key], d)}</td><td>{signed(p['delta'][key], d)}</td></tr>"
                              for key, label, d in (("frameP50", "frame p50 ms", 2), ("frameP95", "frame p95 ms", 2), ("cpuP50", "CPU p50 ms", 2), ("cpuP95", "CPU p95 ms", 2),
                                                    ("gpuP50", "GPU p50 ms", 2), ("gpuP95", "GPU p95 ms", 2), ("drawCalls", "draw calls", 0), ("activeMeshes", "active meshes", 0),
                                                    ("triangles", "triangles", 0), ("heapMB", "JS heap MB", 1), ("fps", "fps", 1)))
        shape = v.get("shape") or {}
        temporal = r.get("temporal") or {}
        temporal_html = ""
        if temporal:
            tb, ta = temporal.get("before", {}), temporal.get("after", {})
            temporal_html = (f"<p class='muted'>Flicker burst ({fmt(ta.get('frames'), 0)} frames): toggling pixels {fmt(tb.get('pctTogglers'), 3, ' %')} → {fmt(ta.get('pctTogglers'), 3, ' %')}"
                             f"{' <b class=flag>▲</b>' if temporal.get('flagged') else ''}; envelope p99 {fmt(tb.get('p99Envelope'), 0)} → {fmt(ta.get('p99Envelope'), 0)}; "
                             f"shape {html.escape(str((ta.get('shape') or {}).get('kind', '–')))}</p>"
                             + (f"<figure><img loading='lazy' src='{temporal['overlay']}' alt='flicker overlay'><figcaption>Flicker (after): direction reversals per pixel</figcaption></figure>" if temporal.get("overlay") else ""))
        flake = f"<p class='warn'>Known flake: {html.escape(r['knownFlake'])}</p>" if r.get("knownFlake") else ""
        cards.append(f"""<section class='card' id='{r['id']}'>
<h3>{html.escape(r['id'])} <small class='v-{r['visualVerdict'].replace(' ', '-')}'>{html.escape(r['visualVerdict'])}</small> {flag}</h3>
<div class='grid'>
<figure><div class='cmp' style='--pos:50%'><img loading='lazy' src='{r['files']['after']}' alt='after'><img loading='lazy' class='top' src='{r['files']['before']}' alt='before'>
<input type='range' min='0' max='100' value='50' aria-label='Before/after split' oninput="this.parentNode.style.setProperty('--pos', this.value + '%')"></div>
<figcaption>◀ before · after ▶ · <a href='{html.escape(r['files']['beforePng'])}'>before PNG</a> · <a href='{html.escape(r['files']['afterPng'])}'>after PNG</a></figcaption></figure>
<figure><img loading='lazy' src='{r['files']['diff']}' alt='diff heatmap'><figcaption>Diff ×4 heatmap · max Δ {fmt(v.get('maxDelta'), 0)} · worst at {html.escape(str(v.get('worstAt', '–')))} · shape {html.escape(str(shape.get('kind', '–')))} (coherence {fmt(shape.get('coherence'), 2)})</figcaption></figure>
<div><table class='m'><tr><th></th><th>before</th><th>after</th><th>Δ</th></tr>{metric_rows}</table>
<p class='muted'>SSIM {fmt(v.get('ssim'), 5)} · PSNR {fmt(v.get('psnr'), 2) if v.get('psnr') is not None else '∞'} dB · MAE {fmt(v.get('mae'), 3)} · changed {fmt(v.get('changedPct'), 3, ' %')} (Δ&gt;{report['options']['threshold']}) · strong {fmt(v.get('strongPct'), 3, ' %')} · over 8/255 {fmt(v.get('pctOver8'), 3, ' %')}</p>
<p class='muted'>{html.escape(p['rule'])}: Δ {signed(p['delta']['frameP95'])} ms{'' if p['frameP95BeyondNoise'] is None else f", beyond noise {signed(p['frameP95BeyondNoise'])} ms"}. Sub-window p95 spread {fmt((p.get('spread') or {}).get('before'), 1)} / {fmt((p.get('spread') or {}).get('after'), 1)} ms.{' Not flagged: ' + html.escape(p['invalidCapture']) + ' (no meaningful frame time).' if p.get('invalidCapture') else ''}{' Unqualified, machine busy (' + html.escape(p['unqualified']) + ')' + ('; the raw rule would have flagged it.' if p.get('wouldFlag') else '.') if p.get('unqualified') else ''}</p>{temporal_html}{flake}</div>
</div></section>""")
    b, a = report["before"], report["after"]
    def ident(side):
        build = side.get("build") or {}
        git = side.get("git") or {}
        return f"<b>{html.escape(side['label'])}</b> · build {html.escape(str(build.get('hash')))} · git {html.escape(str(git.get('head', ''))[:10])}{' (dirty)' if git.get('dirtyFiles') else ''} · Chrome {html.escape(str(side.get('browser')))}"
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Capture compare</title><style>
:root{{--bg:#f6f4ef;--fg:#1d2329;--muted:#5c6670;--card:#fff;--line:#d9d4c7;--good:#1f7a43;--bad:#b3261e;--warn:#8a5a00;--accent:#2a5d8f}}
@media (prefers-color-scheme: dark){{:root:not([data-theme=light]){{--bg:#11161b;--fg:#e8e4da;--muted:#9aa6b1;--card:#1a2128;--line:#2c3640;--good:#5ccf8a;--bad:#ff8a80;--warn:#f0c060;--accent:#8fc1ff}}}}
:root[data-theme=dark]{{--bg:#11161b;--fg:#e8e4da;--muted:#9aa6b1;--card:#1a2128;--line:#2c3640;--good:#5ccf8a;--bad:#ff8a80;--warn:#f0c060;--accent:#8fc1ff}}
*{{box-sizing:border-box}}body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
h1{{font-size:20px;margin:0 0 6px}}h3{{font-size:15px;margin:0 0 10px;word-break:break-all}}a{{color:var(--accent)}}
.chip{{display:inline-block;padding:2px 10px;margin:2px;border-radius:999px;border:1px solid var(--line);background:var(--card)}}.good{{color:var(--good)}}.bad,.flag{{color:var(--bad)}}
.v-identical,.v-within-noise{{color:var(--good)}}.v-minor-change,.v-phase-mismatch{{color:var(--warn)}}.v-changed,.v-incomparable{{color:var(--bad)}}.warn{{color:var(--warn)}}.muted{{color:var(--muted);font-size:12.5px}}
.wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}}table{{border-collapse:collapse;width:100%}}td,th{{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap;font-variant-numeric:tabular-nums}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin:14px 0}}.grid{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr))}}
figure{{margin:0}}figure img{{width:100%;height:auto;display:block;border-radius:6px}}figcaption{{font-size:12px;color:var(--muted);margin-top:4px}}
.cmp{{position:relative;line-height:0}}.cmp img{{width:100%;border-radius:6px}}.cmp .top{{position:absolute;inset:0;clip-path:inset(0 calc(100% - var(--pos)) 0 0)}}
.cmp input{{position:absolute;left:0;right:0;bottom:6px;width:100%;margin:0;min-height:32px;accent-color:#f0c060}}table.m td,table.m th{{padding:3px 6px;font-size:12.5px}}
</style></head><body>
<h1>{html.escape(report['title'])}</h1>
<p>Before: {ident(b)}<br>After: {ident(a)}</p>
<p>{''.join(chips)}</p>
<p class='muted'>{'A/A self-compare: these values are the noise floor for later compares. ' if report['kind'] == 'aa' else ''}Verdicts: identical · within noise (changed ≤ {report['options']['same_changed_pct']} % and SSIM ≥ {report['options']['same_ssim']}, raised to the A/A floor ×1.5 when --noise is given) · minor change · changed · phase mismatch (the two shots were taken at different animation frames; re-capture with the baseline's views, warm-up and sample counts). Generated {html.escape(report['createdAt'])}{' · noise floor ' + html.escape(report['noiseSource']) if report.get('noiseSource') else ''}.</p>
<div class='wrap'><table><tr><th>shot</th><th>visual</th><th>perf</th><th>SSIM</th><th>changed</th><th>PSNR</th><th>frame p95 ms</th><th>Δ p95</th><th>Δ CPU p95</th></tr>{''.join(rows)}</table></div>
{''.join(cards)}
</body></html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--noise", type=Path)
    parser.add_argument("--aa", action="store_true", help="A/A self-compare (same build twice)")
    parser.add_argument("--title")
    parser.add_argument("--threshold", type=int, default=DEFAULTS["threshold"])
    args = parser.parse_args()
    options = {**DEFAULTS, "threshold": args.threshold}
    report = compare(args.before.resolve(), args.after.resolve(), args.out.resolve(), args.noise.resolve() if args.noise else None, args.aa, args.title, options)
    print(json.dumps(report["summary"], indent=1))
    print(args.out.resolve() / "report.html")
