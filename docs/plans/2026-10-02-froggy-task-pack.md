# froggy task pack (2026-10-02)

From: Claude (supervisor). For: froggy, the GPT cloud agent. The owner pastes each task in.

Why froggy: it runs in the cloud, so it costs this PC no CPU, GPU or RAM, and it can browse sites that our local agents can't reach, such as Reddit.

> **วิธีส่งงาน (สำหรับเจ้าของ):**
> 1. copy กล่อง `TASK F1`–`F5` ไปวางใน froggy ทีละกล่อง เรียงตามลำดับ
> 2. ถ้ากล่องไหนบอกให้แนบรูป ให้แนบด้วย
> 3. ได้ zip กลับมาแล้ว ให้เก็บไว้ที่ `Downloads\Xexoria-Game\sources\froggy\<หมวด>-<วันที่>\` เช่น `sources\froggy\monsters-20261002\`
> 4. แจ้ง Claude เพื่อรีวิว แล้ว Codex จะเอาเข้าเกม
> 5. งานของ froggy เป็นแค่ concept ยังไม่ถือว่าผ่านจนกว่าจะเห็นในเกมจริง

Shared rules (they are in every task):
- **Originality:** every design is original to Xexoria. No Blizzard, WoW, Genshin, Ragnarok or Lumivara characters, names, logos or UI.
- **Look target:** stylised hand-painted MMO. Chunky readable shapes. The style lives in painted albedo: painted AO, top-light gradients and crisp edge highlights. Warm sun with blue fill. Saturated but harmonious colour.
- **Labels:** label every image `CONCEPT` or `PAINTED SOURCE`.
- **Delivery:**
  - one zip per task, named `<category>_<id>_v1.zip`;
  - it holds the files, a `README.md` (what is inside, prompts used, open issues) and a `receipt.json` (file list, pixel sizes, palette hex values, licence note "generated for Xexoria");
  - the README states what passes and what does not against the task's checklist.

## Image QA gate and regen loop (added 2026-10-02; applies to every froggy image)

The owner asked for this: froggy images go to 3D models (front/back/left/right), textures, props, characters and UI buttons, and every image must be checked before use. A bad image is regenerated, never "fixed later".

1. **Automatic pre-check** (Claude, `tools/art/turnaround_qa.py`, being built now). It checks:
   - resolution;
   - clean or transparent background;
   - subject centred and not cropped;
   - same height across views (±3 %);
   - front/back and left/right width match (±5 %);
   - left/right mirror consistency;
   - no strong cast shadows;
   - palette against the strip.
2. **Design review** (Claude looks at every image): style match to the look target, silhouette read at game distance, originality, consistency between views, and whether Tripo can build it (no ambiguous overlaps or floating parts).
3. **Verdict:**
   - **PASS:** goes to Tripo or texture use.
   - **REGEN:** Claude writes the exact regen prompt (what to change, what to keep), and the owner pastes it to froggy.
   - Max 3 regen rounds, then Claude reports the problem to the owner.
4. **Tripo credit guard:** nothing goes to Tripo P2.0 until its view set passes steps 1-2. Tripo credits cost money.

**Routing:**
- **Tripo P2.0 + Smart UV:** detailed organic assets: characters, monsters, hero props, statues.
- **Blender kits or CC0 (Quaternius/Kenney):** simple modular props (crates, barrels, fences, planks). That is cheaper and lighter on phones.
- **Detail on low tiers:** every Tripo high-poly is baked to normal/AO maps on a low-poly LOD, so phones keep the detail at low triangle cost.

---

## TASK F1: deep research, Reddit first (highest priority)

```
TASK F1 — Deep web research for Xexoria (browser MMO). Use your browsing. Reddit first, then other sources.

Context: Xexoria is a stylised hand-painted browser MMO built on Babylon.js 9.27.1. It renders with WebGPU and falls back to WebGL2; the client is TypeScript/Svelte and the server is Rust. Target devices:
- desktop GTX 1050 (2 GB VRAM) at 1080p, 60 fps;
- iPhone 11 (A13, 4 GB RAM, Safari/WebKit, 60 Hz), 30-60 fps;
- mid-range Android.
Goal from the owner: mobile must get PC-like detail at low CPU/GPU/RAM cost, and the fps should adapt automatically to the screen (30/60/90/120).
Our local agents could not reach Reddit, so this is your main job.

Find and summarise real practitioner experience (2022-2026) on:
1. Making browser 3D games (Babylon.js, three.js, PlayCanvas, WebGPU) look rich on iPhones and mid-range Android. What worked, what failed, measured numbers.
2. Safari iOS specifics:
   - WebGPU in Safari 26;
   - WebGL2 on ANGLE/Metal;
   - memory limits and tab kills;
   - Low Power Mode capping rAF at 30 fps;
   - thermal throttling;
   - home-screen web app mode.
3. Mobile-game techniques that give PC-like detail cheaply:
   - baked lighting and AO;
   - ASTC/KTX2;
   - normal maps vs geometry;
   - impostors and LOD;
   - foliage overdraw;
   - one shadow cascade;
   - LUT grading;
   - cheap bloom;
   - FSR1/upscaling on phones;
   - dynamic resolution;
   - frame pacing.
   Include how Genshin Impact, Honkai Star Rail, Wuthering Waves, Sky: Children of the Light and Diablo Immortal do it, from talks and interviews.
4. Fast loading for web games:
   - meshopt vs Draco;
   - KTX2 ETC1S vs UASTC;
   - brotli;
   - service workers;
   - shader warm-up;
   - web workers / job systems.
5. Auto fps: detecting 60/90/120 Hz displays from the browser, capping cleanly (divisors), and Babylon render-loop capping.

Subreddits to search (at least): r/babylonjs, r/threejs, r/webgpu, r/WebGL, r/gamedev, r/GraphicsProgramming, r/Unity3D, r/unrealengine, r/iOSProgramming, r/webdev, r/Android, r/MobileGaming.
Also use: the Babylon.js forum (forum.babylonjs.com), WebKit blog, Chrome developers blog, web.dev, GDC Vault / talk slides, Apple WWDC, the Arm Mali and Qualcomm Adreno guides, and GitHub issues.

Deliver research_mobile-detail_v1.zip with:
- report.md:
  - a 10-line executive summary;
  - then one section per topic. Each finding gives: the claim, the source URL, date, author type (engine team / vendor / studio / hobbyist), a short quote, and how much to trust it (high/med/low).
  - a final "Top 20 actions for Xexoria", ranked by impact/cost, each naming the Babylon.js feature or technique to use;
- links.csv (url, title, date, subreddit/site, topic).

Quality bar:
- at least 60 distinct sources, of which at least 25 are Reddit threads with real discussion (not just links);
- no invented sources;
- if Reddit blocks you, say so and use the archives;
- mark anything older than 2022 as possibly stale.
```

---

## TASK F2: Sunmeadow monster concept pack (unblocks sample S1)

```
TASK F2 — Concept pack: Sunmeadow monsters for Xexoria (CONCEPT).
Attach: the owner's look-target images (town art target and the VFX references).

Look: stylised hand-painted MMO, chunky readable silhouettes that read at 30 m, a bright meadow palette, cute-but-dangerous for the low levels, original designs.
For each monster deliver:
- a front / side / back / three-quarter turnaround on a neutral background, with a scale bar and a 1.8 m human silhouette;
- a palette strip of 6-8 hex colours;
- 2 key poses (attack windup, hit reaction);
- notes: materials (fur, moss, slime, bark), where the glow or element lives, and the attack telegraph shape. The telegraph is a ground marker: an amber ring for normal attacks and a double vermilion toothed ring for heavy ones.

Monsters (levels 1-12 meadow, original names):
1. Mossling: a small moss-and-pebble critter (0.6 m). S1 pipeline sample, so do it first and best.
2. Puddlekin: a water slime with a leaf hat (0.5 m). It replaces the old pink slime.
3. Thistle Boar: a thorn-maned boar (1.1 m at the shoulder), and its elite "Turfback Matriarch" (1.6 m, sod and flowers on its back, scarred tusks).
4. Glade Wisp: a floating light wisp for night (0.4 m core, trailing petals).
5. Galehorn: the field boss of the Windstone Circle. A large wind-horned stag-ram beast with a 2.0 m body radius and 3.2 m to the horn tips. Wind-carved horns and cloth-like streamers echo the circle's cloth-streamer windstones. It needs a phase-2 look (horns glow wind-teal, streamers torn).

Deliver monsters_sunmeadow_v1.zip, with one folder per monster plus a lineup contact sheet: all monsters next to the 1.8 m human, same light, labelled.

Checklist:
- greyscale silhouettes stay distinct from each other;
- no thin parts that will break at 4-8k triangles (regular) or 15-25k (boss);
- texture-friendly large shapes;
- consistent light direction (warm key from the upper left, blue fill).
```

---

## TASK F3: painted leaf-cluster sheet v2 and bark swatch (fixes the tree value range)

```
TASK F3 — PAINTED SOURCE: foliage atlas v2 for Xexoria's stylised trees.
Attach: the town art target image and the tree crops the owner selects.

Problem we are fixing: our broadleaf trees' foliage value range is too narrow, with not enough bright yellow-green highlights and not enough deep shadow (measured value range 0.46, need 0.60). Highlights sit 0.03-0.07 luma below the target's yellow.

Deliver foliage_atlas_v2.zip:
- leaf_clusters_2048.png:
  - 2048x2048 RGBA, transparent background;
  - 6 broadleaf clusters, 2 conifer tiers and 1 blossom cluster;
  - each cluster's painted value runs from a deep shadow core (about #23401A) to sunlit yellow-green rims (about #C9CF62);
  - painted top-light;
  - clean alpha edges (no fringe halos), and a 16 px gutter between clusters;
- leaf_clusters_mask.png: a binary alpha version (threshold 0.45) for alpha-tested rendering;
- bark_1024.png: a tileable (seamless) hand-painted bark, warm brown with lighter ridges, and a matching bark_normal_hint.png (a greyscale height hint is fine);
- palette.png plus the hex list;
- a one-page concept: 3 broadleaf and 2 conifer silhouettes beside a 1.8 m human.

Checklist:
- the clusters read as lumpy clumps with sky gaps, never flat cards or balls;
- the value range target is met (state the measured min/max luma);
- the bark is seamless when tiled 2x2;
- no photographic leaves.
```

---

## TASK F4: hand-painted terrain tileables (terrain splat P2)

```
TASK F4 — PAINTED SOURCE: terrain tile set for Xexoria (4-layer splat).
Attach: the town art target image.

Deliver terrain_tiles_v1.zip. Each tile is 1024x1024, seamless, hand-painted and stylised, with no photographic texture:
1. lush meadow grass (bright, small painted clumps; reads as grass at a 13 m camera);
2. dry grass (warmer, ochre highlights);
3. dirt path (packed earth with a few pebbles and wheel ruts as a subtle variant);
4. mud / moss (dark wet mud with moss patches, for stream banks).

Also deliver:
- a 512x512 macro variation sheet: a large soft painted noise used to break up tiling at 50-100 m;
- a contact sheet showing each tile at 3x3 repeats, plus a blend demo where all 4 meet.

Checklist:
- seams invisible at 3x3;
- no single feature that repeats obviously;
- the 4 tiles share one palette and light direction (top-light, no baked directional shadow);
- luma ranges noted per tile.
```

---

## TASK F5: painted cloud layers (VFX lane B5)

```
TASK F5 — PAINTED SOURCE: cloud layers for Xexoria's sky.
Attach: the owner's look-target images.

Deliver clouds_v1.zip. Each layer is RGBA and stylised hand-painted, with soft painted edges and no photographic clouds:
1. horizon band: 4096x512, tileable horizontally;
2. mid-deck puffy clouds: 2048x1024, 6-8 separate clouds on transparent with a 32 px gutter;
3. cirrus streaks: 2048x512, tileable horizontally.

Each layer needs two variants:
- noon: white body, blue-grey shadow undersides;
- dusk: peach and rose body, violet undersides.

Also deliver a mock-up of all three layers over a gradient sky at noon and at dusk.

Checklist:
- values never reach pure white (max about 245/255, so bloom does not clip);
- alpha edges are soft with no halos;
- the horizontal tiles have no seams.
```

---

## TASK F6: orthographic turnarounds for Tripo P2.0 multi-view (characters, monsters, hero props)

```
TASK F6 — CONCEPT turnaround sets for 3D modelling (Tripo P2.0 multi-view input) for Xexoria.
Attach: the approved concept for each asset (F2 monsters; the owner's hero designs; the prop list below).

For EACH asset deliver 4 separate PNG views plus 1 hero view:
- front, back, left and right;
- each view 2048x2048, the subject centred, filling about 80 % of the height, the feet or base on the same baseline in every view;
- the same scale in all 4 views;
- an orthographic look: no perspective, no foreshortening, camera at mid-height;
- a pure flat background (#FFFFFF or transparent);
- neutral flat lighting with no cast shadows, so it reads as an albedo-like reference;
- characters in an A-pose (arms about 30-45° down, legs slightly apart, hands open); monsters in a neutral standing pose;
- plus one 3/4 hero view in the game look (lit), for texture reference only.

Consistency rules (they will be checked automatically):
- height equal across views within 3 %;
- front/back widths match;
- left is the mirror silhouette of right, unless the design is asymmetric; list any asymmetry in the README;
- every part visible in one view appears consistently in the others;
- no parts float or merge ambiguously; thin parts (straps, horns, weapons) at least 3 % of the image width so they survive meshing.

Assets, in priority order:
1. Mossling (from F2), then Puddlekin, Thistle Boar, Turfback Matriarch, Glade Wisp and Galehorn.
2. Hero 02 Mage, then 01 Swordsman (orc), 05 Thief (rogue), 06 Merchant (tinker), 04 Acolyte (bull-kin), 03 Archer (wolf-kin). Match the owner's designs.
3. Hero props: the windstone altar (r 2.5 m flush platform with a central 0.8 m block), a standing stone (3-4.8 m), the broken cart, and the hunter-camp tent.

Deliver turnarounds_<asset>_v1.zip per asset: front.png, back.png, left.png, right.png, hero34.png, palette.png, README.md (pose, scale in metres, asymmetries, materials), receipt.json.
```

---

## TASK F7: UI button and control kit v2

```
TASK F7 — PAINTED SOURCE: UI control kit v2 for Xexoria (original MMO UI, gold/bronze frames, Warcraft-like readability, no copied UI).
Attach: froggy's earlier control atlases (sources/froggy/ui-controls-20261002) and the town art target.

Deliver ui_controls_v2.zip:
- buttons in 3 sizes (primary 240x72, secondary 180x56, icon 72x72), each with 4 states: normal, hover, pressed (darker, inset), disabled (desaturated, 50 % contrast);
- 9-slice-ready: 24 px corners and a plain stretchable centre; deliver slice margins in JSON;
- a frame/panel (9-slice), a tab (selected and unselected), a checkbox and a toggle (on/off), a slider track and knob, a scrollbar, a tooltip box, and a close X;
- the HP bar frame and fill (red, green, gold) at 96x8 and 64x6 sizes, with crisp 1 px edges;
- every asset at 2x scale for phones (DPR 2-3), PNG with alpha, no text baked in (Thai and English text is rendered live);
- a contact sheet on dark and light game backgrounds.

Checklist:
- states are distinguishable in greyscale;
- edges are crisp at 1x and 2x;
- no baked text;
- 9-slice corners don't distort when stretched to 3x width.
```

---

## After delivery (Claude)

- Review each zip against its checklist:
  - **F2:** goes to the sample S1 Tripo + Blender pipeline. Tripo needs the owner's login and credits.
  - **F3:** goes to the tree stylisation pass.
  - **F4:** goes to the terrain splat.
  - **F5:** goes to the VFX lane through the Codex inbox.
  - **F1:** goes into the mobile plan and the master plan P10.
- Report keep/drop per item to the owner the same day.
