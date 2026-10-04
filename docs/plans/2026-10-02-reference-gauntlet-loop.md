# Art-director reference + gauntlet loop (standard for new monsters, bosses and scenes)

Date: 2026-10-02. Owner: Claude (supervisor). Applies to froggy (ImageGen), Tripo, Blender agents and in-engine work.

Source: the owner's shared guide (2026-10-02):
- treat AI as the artist and us as the art director;
- start from a clean, high-quality 16:9 reference;
- make 2-3 variants and pick the best;
- then run a gauntlet loop: inspect, list problems, fix, inspect again, and reject anything that does not match the reference.

> **สรุปภาษาไทย:**
> ทุกมอนสเตอร์ บอส และฉากใหม่ใช้ขั้นตอนเดียวกัน 3 ช่วง
> 1. **ภาพ ref คุณภาพสูง:** ภาพ 16:9 ที่รูปทรงชัด แสงเงาชัด ไม่รก ให้ froggy ทำ 3 แบบ แล้ว Claude เลือก
> 2. **ภาพ 4 ด้านสำหรับโมเดล:** ผ่านเครื่องมือตรวจภาพและการรีวิวดีไซน์ ถ้าไม่ผ่านให้ gen ใหม่ได้สูงสุด 3 รอบ ผ่านแล้วค่อยส่ง Tripo
> 3. **gauntlet loop ในเกมจริง:** ถ่ายภาพจากเกมที่มุมกล้องเดียวกับ ref → วัดค่าความสว่าง คอนทราสต์ สี และรูปทรงเงา → แก้ → ถ่ายใหม่ ทำซ้ำจนผ่านเกณฑ์ แล้วค่อยแก้เฉพาะจุด โดยวงจุดที่ต้องแก้บนภาพ

## Stage A: reference (froggy)

1. **Brief.** Write it from the design docs: roster, scale, palette, telegraph, phase look.
2. **Prompt core** (from the owner's guide, adapted):
   - "Make this a high-quality AAA stylised hand-painted render, 16:9, Xexoria look target attached. Keep the design clean for 3D generation: clear shapes, clear light and shadow, uncluttered background, nothing too dark."
   - Ask for **3 variants** (separate generations).
3. **Claude picks** with this checklist:
   - shape reads in greyscale at game distance;
   - light and shadow are clear;
   - not blurry, not cluttered, not too dark;
   - original (no IP look-alikes);
   - buildable (no ambiguous overlaps, no hair-thin parts).

   Rejected variants are listed with reasons.

## Stage B: model sheets → Tripo (already built)

1. The F6 turnaround format: front, back, left, right; 2048², orthographic, white background, A-pose.
2. The automatic gate: `python tools/art/turnaround_qa.py <set> --out <dir>`, which gives PASS or REGEN plus `regen_notes.md` with a paste-ready froggy prompt.
3. Claude's design review, then `--prep ... --design-review PASS --reviewer Claude`.
4. **Regen loop:** at most 3 rounds, then report to the owner.
5. Tripo, per `docs/plans/2026-10-02-tripo-job-card.md` (staged spend, credit guard).

## Stage C: in-engine gauntlet loop (the Oriverse-style loop, in our engine)

**Loop** (each pass is one iteration; at most 6 per asset or scene before escalating):
1. **Capture** the asset or scene in Babylon (both renderers) at a camera matched to the reference, using `tools/capture/` (capture harness).
2. **Compare** to the reference (`tools/capture/` reference-match mode). Global metrics, because the composition is never pixel-identical:

   | Metric | Gate |
   |---|---|
   | Mean luminance | ±0.05 |
   | Contrast (luma p90 − p10) | ±0.05 |
   | Luminance-histogram distance (EMD) | ≤ 0.06 |
   | Saturation mean | ±0.06 |
   | Palette ΔE00 (6 dominant colours, matched) | ≤ 8 |
   | Silhouette IoU at the matched view (assets only) | ≥ 0.85 |
   | Art rubric (shape, value, colour, material read, detail density, readability at 13 m) | ≥ 85/100, every line ≥ 4/5 |

3. **List** the remaining problems, strongest first: max 5 per pass, each with where, what and why.
4. **Fix** only those, in Blender, the material, or lighting.
5. **Re-capture** with the same camera and compare again. If the result is worse, revert.
6. **Reject** any pass that does not improve the metrics or the rubric. After 2 unproductive passes on the same problem family, change the method and say why.
7. **Targeted fixes:** once the global gates pass, circle the regions still wrong on the capture (annotated PNG) and fix those spots only.

**Budgets always apply** (master plan P10 and the device-tier plan). A match bought by breaking the budget is a reject.

**Prompt template for our agents** (from the owner's guide, adapted to our stack):

```text
Build <asset/scene> in Xexoria (Babylon 9.27.1, Blender 5.2) to match the attached reference: same lighting, value and contrast; textures with roughness variation, occlusion, normal detail and noise; correct reflections. Within budgets: <tier budgets>.
Run a gauntlet loop:
- capture at the matched camera;
- compare with tools/capture reference-match;
- list the 5 worst problems;
- fix only those;
- re-capture.
Inspect each prop individually and raise its geometry and detail to the bar; refine lighting.
Reject passes that don't improve the metrics. Stop when every gate passes or after 6 passes, and report with images and numbers.
```

## Worked sample (real results, 2026-10-02)

- **Stage B loop, round 1** (`planning/evidence/turnaround-qa-20261002/`):

  | Hero | Result | Reason |
  |---|---|---|
  | 01 | PASS + design PASS → Tripo-ready | — |
  | 04 | PASS + design PASS → Tripo-ready | — |
  | 06 | PASS + design PASS → Tripo-ready | — |
  | 02 | REGEN | Left/right profiles differ: IoU 0.77, left view 15 % wider |
  | 03 | REGEN | Arms touch the body; the side views are 3/4, not profiles |
  | 05 | REGEN | Front/back outline mismatch: IoU 0.875 |

  Round 2 prompts for 03 and 05 go to froggy (02 is already built and is regenerated only if we rebuild it).
- **Stage A, monsters:** the Mossling concept passed the design review with two optional notes:
  - a slightly fiercer attack read;
  - thicker sprout leaves.

  The turnaround set comes next, then Stage B.
- **Stage A, boss:** Galehorn 16:9 key art (3 variants) and a Windstone Circle arena key art (3 variants) are requested from froggy (task F8). The arena art becomes the scene reference for the first Stage C loop on Sunmeadow.
