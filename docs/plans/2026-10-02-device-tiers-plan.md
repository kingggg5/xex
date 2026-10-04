# Device tiers and scalable content: the definitive plan

Date: 2026-10-02 · Author: Claude Opus 5.5 (graphics and performance lead) · Status: PLAN. Docs only: no code, asset or setting was changed, nothing was installed, and no browser GPU session was run.
Scope: every renderer setting that scales by device, how Auto picks a tier, how the player overrides it, and what the asset pipeline must ship so that every tier keeps the look.
Related: [Visual detail master plan](2026-10-02-visual-detail-master-plan.md) (MP: §1 budgets, P10 "Performance and mobile") · [iPhone 11 + Safari target](../reviews/2026-10-02-iphone11-safari-target.md) ("iPhone 11 target doc") · [Fast loading and low RAM](../reviews/2026-10-02-fastload-research.md) ("fast-load") · [Auto FPS and frame pacing](../reviews/2026-10-02-auto-fps-frame-pacing.md) ("auto-fps") · [PC-level detail on mobile](../reviews/2026-10-02-mobile-pc-detail-research.md) (C-R-MOB) · [Babylon community practice](../reviews/2026-10-02-babylon-community-practice.md) (CP) · [Babylon docs recheck](../reviews/2026-10-02-babylon-docs-recheck.md) · [Sky and light spec](../reviews/2026-10-02-map-sky-light-spec.md) (SKY) · [Terrain spec](../reviews/2026-10-02-map-terrain-spec.md) (TER) · [Grass spec](../reviews/2026-10-02-map-grass-spec.md) (GRS) · [Water spec](../reviews/2026-10-02-map-water-spec.md) (WAT) · [VFX quality bar](../reviews/2026-10-02-vfx-quality-bar.md) (VFX) · [Heroes rig and animation](../reviews/2026-10-02-heroes-rig-and-animation.md) (HRA) · [Monster art pipeline](../reviews/2026-10-02-monsters-art-pipeline-and-sources.md) (MON) · [MMO master plan 2027](../mmo-master-plan-2027.md) §6–7 (MMP) · [Program task graph](2026-10-02-program-task-graph.md)

> **สรุปภาษาไทย (สำหรับเจ้าของ)**
> 1. **มี 5 ระดับ + อัตโนมัติ:** ต่ำ / ปานกลาง / สูง / สูงมาก (Ultra) / สูงสุด (Epic, เฉพาะ PC) ทุกระดับใช้แสง หมอก สี และ shader ชุดเดียวกัน ภาพจึงเป็นสไตล์ hand-painted เดียวกันทุกเครื่อง ต่างกันแค่ความละเอียด ระยะมองเห็น ความหนาแน่นหญ้า เงา และ fps
> 2. **iPhone 11 ได้ "ปานกลาง" 30 fps:** ใช้โมเดล LOD1 ที่ bake normal + AO จากโมเดลละเอียด (Tripo) ไว้ในเท็กซ์เจอร์ จึงยังเห็นรายละเอียดแบบ PC แต่ใช้ GPU น้อย มีเงา 2 ชั้นถึง 55 m หญ้าถึง 38 m และวาดภาพ 3D ที่ 1052×486 (ราว 0.5 ล้านพิกเซล ความคมต่อองศาสายตาพอ ๆ กับจอ PC 1080p) พร้อม MSAA 4× ซึ่งถูกบน GPU มือถือ ส่วน FSR จะใช้ก็ต่อเมื่อทดสอบบนเครื่องจริงแล้วสวยกว่าที่ต้นทุนเท่ากัน
> 3. **iPhone 16 Pro Max ได้ "สูง" (High) 60 fps** ระดับเดียวกับ PC ที่ใช้ GTX 1050 แต่ปรับให้เหมาะกับมือถือ: เงา 2 ชั้น 2048 ถึง 85 m, เท็กซ์เจอร์ 2K, หญ้าถึง 51 m และภาพ 3D ราว 0.75 ล้านพิกเซล ถ้าเครื่องร้อนจะลดเป็น 30 fps เอง ส่วน Safari ล็อก 60 fps เป็นค่าเริ่มต้น เราจึงไม่สัญญา 120 fps บน iPhone
> 4. **RTX 5060 ได้ "สูงสุด (Epic)":** 1440p เต็มพร้อม supersampling 1.25× และ MSAA 4×, เงา 4 ชั้น 4096 ถึง 250 m, หญ้าถึง 90 m, มองไกล 360 m, เท็กซ์เจอร์ 4K ในจุดที่ทำไว้, ตัวละครละเอียด 30 ตัว และได้ 120 fps เมื่อจอรองรับและเครื่องไหว
> 5. **Auto เลือกให้เอง:** ครั้งแรกที่เข้าเกม ระบบอ่านข้อมูลเครื่อง (การ์ดจอ, RAM, ขนาดจอ, refresh rate) แล้ววัดจริง 1.5–3 วินาทีในหน้าโหลด จากนั้นจำผลไว้ในเครื่อง ครั้งต่อไปจึงไม่ต้องวัดซ้ำ
> 6. **ระหว่างเล่น:** ถ้าเครื่องเริ่มหนัก เกมจะลดความละเอียด (FSR) ก่อน แล้วลด fps แล้วจึงแนะนำให้ลดระดับ การเปลี่ยนระดับเกิดตอนโหลดฉากเท่านั้น ไม่เกิดกลางการต่อสู้ ผู้เล่นเลือกระดับเองได้เสมอ และมีตั้งค่าขั้นสูงเป็นภาษาไทย
> 7. **สถานะ:** ทุกตัวเลขยังเป็นค่าตั้งต้น (P) จนกว่าจะวัดบนเครื่องจริง ขอให้เจ้าของทดสอบบน iPhone 11 และยืนยันว่ามี iPhone 16 Pro Max และ PC ที่ใช้ RTX 5060 ให้ทดสอบหรือไม่

---

## 0. How to read this plan

**Value marks.** Every number in §3, §4 and §6 carries one mark. A cell without a mark is P, and frame-time gates are targets, not values:
- **M** (measured): a measurement exists, and its source is named.
- **P** (provisional until a device run): a decision or estimate. Nothing in this repository has yet been measured on a phone, an RTX card or an iPhone 16 Pro Max (MMP §1: "Nothing in this repository has ever been measured on a phone"). Almost every value is therefore P.

**Where the numbers come from.** Where a spec already set a value, this plan uses it and cites the spec line (SKY, TER, GRS, WAT, VFX, HRA, MON, MMP). This plan adds:
- the device classes and their ceilings;
- the Epic tier;
- the Auto design;
- the content and variant rules.

**PENDING.** Six inputs were being written in parallel. Four landed in time and are integrated:
- the fast-load research;
- the iPhone 11 target doc;
- the auto-fps frame-pacing doc, whose module and tests are already in `apps/client/src/frame-rate-policy.*`;
- the mobile PC-detail research (C-R-MOB).

The FSR doc and the environment quick-wins doc were still missing when this plan was finished (§11), and each will replace specific P values.

**Tier names.** "Tier" or "preset" means Low / Medium / High / Ultra / Epic. "Class" means the seven device classes in §2. A class does not equal a tier: a class sets the Auto range, the hard ceilings and the subsystem rows, and the preset sets everything else.

---

## 1. The tier ladder

### 1.1 Five presets plus Auto

| Preset (Thai label) | Who it is for | What it looks like | Frame target |
|---|---|---|---|
| **Low** (ต่ำ) | mobile-low; weak iGPUs | The same painted albedo, lighting, fog and grade as every tier. Baked detail (normal + AO from the high-poly) on LOD1 meshes. One 512 shadow map around the player. Grass to 30 m. Proxy ring on the horizon | 30 fps |
| **Medium** (ปานกลาง) | iPhone 11 class (mobile-mid); iGPUs | Adds 2 shadow cascades to 85 m (55 m on phones), grass to 45 m (38 m on phones), glow on registered emitters and 1K textures | 30 fps on phones, 60 on desktop |
| **High** (สูง) | GTX 1050 (the master-plan gate); iPhone 15 Pro and 16 Pro Max (mobile-high) | 3 × 2048 cascades to 130 m (2 × 2048 to 85 m on phones), grass to 60 m (51 m on phones), runtime procedural rock and water detail, canopy translucency, 2K terrain and character textures | 60 fps |
| **Ultra** (สูงมาก) | RTX 3060 / 4060 class (desktop-high) | 4 × 2048 cascades to 190 m, full art-directed grass density to 75 m, 2K everywhere, 280 m detail distance, alpha-to-coverage foliage | 60 fps at 1440p; Auto climbs toward the display refresh when there is headroom |
| **Epic** (สูงสุด) | RTX 5060 and up (desktop-ultra); desktop only | 4 × 4096 cascades to 250 m, grass to 90 m with a fuller far band, 360 m detail distance, 4K where authored, MSAA 4× plus 1.25× supersampling, more full-detail characters, and the gated extras of §4 | 60 fps base; Auto climbs to the display refresh when there is headroom at full resolution |
| **Auto** (อัตโนมัติ) | Default | Picks one preset inside the class's Auto range (§5), then adapts resolution and the frame cap at runtime | — |

**Why Epic is justified** (the brief allowed it "if justified"):
1. **It stays one feature set.** CP §4.1 (PatrickRyan [Team], t/55545, 2025-01-06) advises spending high-end headroom on texture size, LOD and distance rather than on new effects. Epic is mostly "more of the same": density, distance, texels, samples and fps. The two new effects (contact shadows, SSAO) are gated experiments that stay off until measured (§4).
2. **Ultra must stay holdable on its own class.** SKY L673 already makes Ultra a 45 fps opt-in on the GTX 1050. If the RTX 5060 extras were folded into Ultra, RTX 3060 / 4060 owners would fall back to High at 1440p.
3. **The owner asked for "much more" on the RTX 5060.** A named top step makes that visible in the menu.
4. **The cost is bounded.** It adds one preset column to the capture matrix, and that column is captured only on desktop-ultra. Mobile menus never list Epic, and Auto never picks it on a phone.

### 1.2 Class → Auto range and default (summary)

| Class | Reference devices | Auto range | Default if the benchmark is inconclusive | Auto frame cap: base → ceiling | Renderer (Auto) |
|---|---|---|---|---|---|
| mobile-low | iPhone X / XR (WebGL2 only), Android with Mali-G57 / Adreno 610 class | Low – Low (Medium manual) | Low | 30 → 30 | WebGL2 |
| mobile-mid | **iPhone 11** (A13); Snapdragon 7-series | Low – Medium | Medium | 30 → 60, in practice 30 on Safari (60 is an opt-in) | WebGL2; WebGPU after A/B |
| mobile-high | **iPhone 15 Pro / 16 Pro Max** (A17 Pro / A18 Pro), iPhone 17 family; Snapdragon 8 Gen 2+ | Medium – High | Medium | 60 with benchmark headroom, else 30 → 60 | WebGL2; WebGPU A/B first |
| desktop-low | Intel UHD / Iris Xe, Radeon Vega iGPUs | Low – Medium | Low | 60 → 60 (30 by step-down) | WebGL2 |
| desktop-mid | GTX 1050 2 GB, GTX 1650, Radeon 780M, Apple M1 / M2 | Medium – High | High | 60 → display refresh | WebGL2 until A/B |
| desktop-high | RTX 3060 / 4060 | High – Ultra | High | 60 → display refresh | WebGL2 until A/B |
| desktop-ultra | **RTX 5060** and up | Ultra – Epic | Ultra | 60 → display refresh | WebGL2 until A/B |

An inconclusive benchmark (hidden tab, rAF stalls, context loss, time cap) uses this default and retries next session. The default is the tier the class's reference device is expected to hold (iPhone 11 Medium, GTX 1050 High), or one tier lower where the class spans fast and slow devices (mobile-high, desktop-high, desktop-ultra). It is never a stretch tier.

### 1.3 Conflicts between docs, resolved here

1. **Which tier a phone runs.** TER (L756, L793) and WAT (L551) budget phones at Low. GRS (L876) and SKY (L675) budget phones at Medium.
   - Resolution: the phone runs the **Medium preset** (mobile-mid) with class subsystem rows.
   - Each subsystem reads the row its own spec budgeted for phones: terrain tier 1 (fallback 0, §3.3), water Low, the grass "Mobile (Medium on a phone)" row and the SKY "Phone, Medium" row.
   - No spec has to be re-budgeted.
2. **Triangles per 64 m cell.** MMP §6 says ≤ 40k per detail cell. The master plan's P1 gate (≤ 120k triangles and ≤ 40 materials per cell) and the prop audit (L403: 120k LOD0 triangles excluding vegetation, 40 draw calls) allow far more.
   - Resolution: every cell ships three representations: **C0** ≤ 120k / 40 draws, **C1** ≤ 60k / 24, **C2** ≤ 40k / 16 (= MMP).
   - Tiers choose C0–C2 by ring (§6.4).
3. **Reference phone.** The iPhone X is the reference iPhone in owner decision D-01 (`docs/execution-backlog.md` L44, 2026-09-24) and in the v5 plan §11.2 (`docs/browser_ragnarok_babylon_rust_10k_plan_v5.md` L319). The 2026-10-02 task graph and froggy pack (L56–57) name the iPhone 11.
   - Resolution: the iPhone 11 is the mobile-mid reference, and the owner runs it (job O-IPH).
   - The iPhone X (iOS 16 at most, so no WebGPU) becomes the mobile-low WebGL2 floor device, if the owner still has it.
4. **Frame-cap policy.** v5 L358 says "no uncapped mode". The task graph has Auto / 30 / 60 / 90 / 120 / Max.
   - Resolution, as in the auto-fps doc (§4.3), which also asks the owner to amend D-10:
     - "Max" means the display refresh, because rAF is vsync-bound;
     - Auto climbs above the tier's base only at full resolution with spare headroom;
     - caps are refresh / n and never below 30.
   - Phones start at 30 (60 on mobile-high with benchmark headroom). Battery saver forces 30.
5. **Phone render size.** GRS L876 assumes 0.45 Mpx: an 844 × 390 phone at today's Medium. SKY L675's "≤ 2.62 MP" is Medium's pixel cap, not a render size. The code's mobile cap is 3 Mpx.
   - Resolution: the class pixel rows in §3.1. On the iPhone 11 the 3D renders at 0.51 Mpx (1052 × 486 at DPR 1.175; §1.3 item 13), close to GRS's budget assumption.
6. **Ultra shadows.** SKY R5 and inbox A14 move Ultra from 4096 to 2048, because 4096 × 4 is ≈ 403 MB on a 2 GB GTX 1050 (SKY L28, L492).
   - Accepted. 4096 moves to Epic, which only desktop-ultra reaches in Auto.
7. **Renderer default.** `scene.ts` `createRenderer` (lines 97–108 at 16:30 on 2026-10-02; other lanes are editing the file) uses WebGPU whenever `navigator.gpu` exists. The only measurement favours WebGL2 (`docs/tools/impostor-cards.md` L74; the device and resolution were not recorded).
   - Until R-A12 ships, WebGPU also decodes every KTX2 texture to RGBA (about 4× the VRAM; CP §3.1). On an iPhone 11 with iOS 26 the code takes this WebGPU path today, so the city's textures cost **432 MiB instead of 90–108 MiB**, and the city totals ≈ 686 MiB steady and ≈ 890 MiB peak ([fast-load research](../reviews/2026-10-02-fastload-research.md) §1.6, a static estimate).
   - Resolution: WebGL2 is the provisional Auto renderer on every class. A class flips to WebGPU only through the A/B in §8.3. The iPhone 11 target doc reaches the same rule for iOS (§4.1).
8. **Form-factor detection.** Four call sites disagree:
   - `scene.ts` `resolveQuality` (line 212) and the environment setup (`environment.ts` line 176) count `pointer: coarse` or a canvas ≤ 1000 × 900 CSS px as mobile, so a small desktop window gets phone ceilings;
   - `settings.ts:165` and `ui/panel-data.ts:101` use a different media query.

   Resolution: one device profile (§5), read by every call site.
9. **Character LOD distances.** HRA L718–721 (bands at 15 / 35 / 60 m), MON L637 (LOD1 15 m, LOD2 35 m, cull about 90 m) and the visual-language T1 row (22 / 38 m) are close at High.
   - Resolution: HRA's and MON's 15 / 35 m are the High baseline, scaled per tier by `lodDistanceScale` (§3.4). Static meshes switch by screen coverage, equalised for pixels per triangle (§3.3).
10. **Phone shadow distance.** SKY's Medium row is 1024 × 2 to 85 m for desktop and mobile alike. The iPhone 11 target doc recommends 60 m on the phone (§4.1), and the mobile PC-detail research (C-R-MOB) about 55 m (§8.2).
   - Resolution: mobile-mid uses 55 m, and 40 m when hot. mobile-high uses 85 m, and desktop Medium keeps 85 m. Cascade 0 still ends at 24 m everywhere (SKY L509).
11. **Phone memory.** MMP §7 says ≤ 350 MB. The fast-load research proposes ≤ 500 MiB steady and ≤ 700 MiB peak (§1.6). The iPhone 11 target doc plans ≤ 1.0 GiB with a 1.25 GiB red line (§2.1), and C-R-MOB ≤ 900 MiB (§8.4). None of them is measured.
   - Resolution: MMP stays the target and the fast-load numbers are the gate. The kill point measured by O-IPH test T16 replaces all of them, at 60 % of that point.
12. **Desktop base frame rate at Low and Medium.** The auto-fps doc (§2.5) starts desktop Low and Medium at 30, because today's presets set `targetFps` 30 for both form factors.
   - Resolution: desktop classes use a base of 60 at every tier. The frame-rate policy steps down to 30 only when resolution is already at its floor (§5.6).
13. **Phone upscaling.** Both phone docs render the 3D at about 0.51 Mpx, but they upscale differently:
   - the iPhone 11 target doc (§4.1) proposes FSR 1.7× up to the native 1792 × 828;
   - C-R-MOB (§8.2, §9 item 3) proposes plain canvas scaling at DPR 1.175, keeping FSR only if a device A/B at equal GPU time shows a visible gain.
   - Resolution: canvas scaling is the phone default. It adds no passes and no stored MSAA target, and MSAA resolves on tile. O-IPH T13 runs `?fsr=1.7` against off, and the pending FSR doc (§11) decides. If FSR wins, the mobile rows switch to the iPhone 11 target doc's values.
14. **Model detection on iPhones.** C-R-MOB (§8.1) says faster phones should climb through measurement, never through model detection.
   - Resolution: screen size only sets the class prior and its ceilings; the tier always comes from XB1 and the runtime controllers. An @3 phone that fails S3 stays at Medium.

---

## 2. Device classes

Every number in this section has a dated source (§2.6). Apple publishes no RAM figures, so iPhone RAM comes from GSMArena (secondary). TFLOPS are FP32 at boost clock.

### 2.1 The seven classes

| Class | Example devices | GPU | Memory | Refresh | DPR | Browser graphics | Expected Auto tier |
|---|---|---|---|---|---|---|---|
| **mobile-low** | iPhone X / XS / XR (A11 / A12; none runs iOS 26, so Safari offers WebGL2 only). Galaxy A15 (Helio G99, Mali-G57 MC2, 90 Hz, 4–8 GB). Redmi 12 (Helio G88, Mali-G52 MC2, 90 Hz) | Mali-G52 / G57 class, Adreno 610–619, Apple A11 / A12 | 3–4 GB | 60–90 Hz | 2–3 (Galaxy A15: about 891 × 411 CSS, assuming DPR 2.625) | WebGL2. Chrome on Android 12+ has WebGPU on Qualcomm and ARM GPUs, but results vary by device | Low |
| **mobile-mid** | **iPhone 11** (A13, 4-core GPU, 4 GB, 1792 × 828 at 326 ppi, so 896 × 414 CSS at DPR 2; 60 Hz). Other A13–A16 iPhones. Poco X6 (7s Gen 2, Adreno 710, 120 Hz). Motorola Edge 50 Pro (7 Gen 3, Adreno 720, 144 Hz). Xiaomi Civi 2 and Motorola Razr 40 (7 Gen 1, Adreno 644) | Apple A13–A16; Adreno 644 / 710 / 720; Mali-G610–G715 | 4–12 GB | iPhone 60 Hz; Android 90–144 Hz | 2–3 | Safari 26/27: WebGPU and WebGL2. Chrome Android: WebGPU (Android 12+, Qualcomm/ARM) and WebGL2 | Medium |
| **mobile-high** | **iPhone 15 Pro / 15 Pro Max** (A17 Pro, 6-core GPU, 8 GB). **iPhone 16 Pro Max** (A18 Pro, 6-core GPU with hardware ray tracing, 8 GB, 2868 × 1320 at 460 ppi, so 956 × 440 CSS at DPR 3; ProMotion up to 120 Hz; released 2024-09-20). iPhone 17 (A19, 5-core GPU, 8 GB), iPhone Air (A19 Pro, 5-core GPU, 12 GB), 17 Pro / 17 Pro Max (A19 Pro, 6-core GPU, 12 GB); every iPhone 17 model has ProMotion. Galaxy S23 (8 Gen 2, Adreno 740), S24 Ultra (8 Gen 3, Adreno 750), S25 and OnePlus 13 (8 Elite, Adreno 830). M-series iPads | Apple A17 Pro – A19 Pro; Adreno 740–830 | 8–16 GB | 120 Hz panels. Safari still renders near 60 (§2.3); Chrome follows the panel | 3 | As mobile-mid | High |
| **desktop-low** | Laptops with Intel UHD 620 (0.42–0.44 TFLOPS) or Iris Xe with 96 EU (1.69–2.23 TFLOPS); Radeon Vega iGPUs | Integrated, on shared system memory | 8–16 GB system | 60 Hz | 1–1.5 | Chrome / Edge: WebGPU (D3D12) and WebGL2 (ANGLE on D3D11) | Low (Medium if XB1 passes S2) |
| **desktop-mid** | **GTX 1050 2 GB** (1.86 TFLOPS; the dev workstation and the master-plan gate). GTX 1050 3 GB (2.33). GTX 1650 4 GB (2.98). GTX 1660. Radeon 680M (3.07–3.38). Radeon 780M (8.6 counting RDNA 3 dual-issue, about half that in practice). Apple M1 (2.6) and M2 (3.6) | 1.5–6 TFLOPS | 2–4 GB VRAM, or shared | 60–144 Hz | 1–2 | As above. Mac Safari has WebGPU on macOS 26 and later only | High |
| **desktop-high** | **RTX 3060** (12.7 TFLOPS; 12 GB, or the 8 GB variant). **RTX 4060** (15.1 TFLOPS, 8 GB). RTX 2060–2080, GTX 1070 / 1080, RX 6600–6700, RX 7600, Arc A750 / B580, M-Pro Macs | 6–16 TFLOPS | 8–12 GB VRAM | 60–165 Hz | 1–1.5 | As above | Ultra |
| **desktop-ultra** | **RTX 5060** (3,840 CUDA cores, 8 GB GDDR7 on a 128-bit bus at 448 GB/s, about 19.2 TFLOPS; launched 2025-05-19 at $299) and up: 5060 Ti, 5070 and higher, 4060 Ti / 4070 and higher, 3070 and higher, RX 6800+, 7700 XT+, 9060 XT+. The RTX 5060 Laptop GPU (3,328 CUDA cores, 8 GB GDDR7) also lands here, and XB1 sets its tier | ≥ 16 TFLOPS | 8–16+ GB VRAM | 120–240 Hz | 1–2 | As above | Epic |

### 2.2 What a web page can learn about the device (October 2026)

| Signal | Chrome / Edge | Safari 26 / 27 | Firefox |
|---|---|---|---|
| GPU model through WebGL (`UNMASKED_RENDERER_WEBGL`) | The real ANGLE string, e.g. "ANGLE (NVIDIA, NVIDIA GeForce RTX 5060 … Direct3D11 …)" | Always "Apple GPU" | Bucketed to a representative model plus ", or similar" (an RTX 3090 reads "GeForce GTX 980"); turned off under resistFingerprinting |
| GPU through WebGPU `adapter.info` | `vendor` and `architecture` only (Dawn's family, such as Lovelace or Blackwell). `device` and `description` need the developer flag | "apple" in all four fields | Not checked |
| WebGPU availability | Desktop. Android 12+ on Qualcomm and ARM GPUs since Chrome 121 (2024-01). Opt-in compatibility mode on OpenGL ES 3.1 since Chrome 146 (2026-02-25) | On by default on iOS / iPadOS 26+ and on macOS 26+ (not on Sonoma or Sequoia). Secure contexts only; off in Lockdown Mode. Safari 27 (2026-09-14) keeps it on | — |
| `navigator.deviceMemory` | Chrome 147+ (2026-04-07): desktop 2 / 4 / 8 / 16 / 32, Android 1 / 2 / 4 / 8 (previously 0.25–8). Secure contexts only | Absent | Absent |
| `navigator.hardwareConcurrency` | The real core count | 4 below 8 cores, otherwise 8; every iPhone reports 4 | The real count (≤ 128); 4 or 8 under resistFingerprinting |
| UA Client Hints (`mobile`, `model`, `formFactors`) | Chrome 90+ (`formFactors` 124+). Since Chrome 144 a permissions policy can withhold high-entropy values | Absent. Since Safari 26 the iOS version in the UA is frozen at 18_6 | Absent |
| Display refresh rate | No API; rAF generally follows the display. Energy Saver can lower it | No API; rAF near 60 even on 120 Hz screens (§2.3) | No API |
| GPU timing | WebGPU `timestamp-query`, quantised to 100 µs unless the developer flag is on. WebGL2 `EXT_disjoint_timer_query_webgl2` | WebGPU `timestamp-query` only where Metal samples counters at stage boundaries (A13 UNVERIFIED); no WebGL2 timer | — |
| Compressed textures on WebGPU | BC on desktop GPUs; ETC2 and ASTC on Android | ETC2 and ASTC on Apple GPUs; BC only where Metal supports it (M-series, Apple9) | — |

The WebGPU spec guarantees that every adapter supports BC, or else both ETC2 and ASTC.

**Consequence.**
- On Chromium the GPU string is a strong prior.
- Through the APIs, every Apple device looks the same: "Apple GPU", "apple", 4 cores, no memory figure, no hints and a frozen iOS version.
- Apple devices are therefore classified by WebGPU presence, screen size and DPR, plus XB1 (§5.2).

### 2.3 Frame rate and refresh

- **Safari keeps rAF near 60 Hz on 120 Hz screens.**
  - WebKit's `PreferPageRenderingUpdatesNear60FPSEnabled` defaults to true everywhere except visionOS. This holds in both the Safari 26 and Safari 27 release branches.
  - Its description reads: "Prefer page rendering updates near 60 frames per second rather than using the display's refresh rate".
  - WebKit's stated reasons: "we measured a significant increase in power usage, and second, we found several examples of web pages that had incorrect behavior when requestAnimationFrame() callbacks were fired at a non-60Hz frequency" (explainer, 2021-12-14).
  - The bug to lift the cap, WebKit 173434, is still open. An Apple engineer saw 120 fps on an iPad Pro only after turning the setting off (2025-11-05).
  - Safari 27 did not change this.
  - **Conclusion:** an iPhone 16 Pro Max renders near 60 in Safari unless its owner turns the feature flag off. The plan does not promise 120 on iOS.
- **Safari halves rAF to 30** in these cases (WebKit `AnimationFrameRate.cpp`, `Page.cpp`, `Document.cpp`; iPhone 11 target doc §2.3):
  - Low Power Mode;
  - a page marked visually idle;
  - a cross-origin iframe the user has not interacted with;
  - an active `<audio>` or `<video>` element (Babylon PR #18366, 2026-04-22).

  Aggressive thermal mitigation is in the same list but is off by default (`RespondToThermalPressureAggressively` is false).
- **Chrome follows the display.** rAF "will generally match the display refresh rate … though 75hz, 120hz, and 144hz are also widely used" (MDN, 2026-08-21). Chrome's Energy Saver can lower it.
- **There is no refresh-rate API.** "There is no dedicated web API to measure display refresh rate … compare the timestamps between successive requestAnimationFrame() callbacks" (Chrome blog, 2022-12-08). The loading screen samples rAF intervals instead (§5.1).
- **Divisors.** WebKit rounds to the nearest whole divisor of the display rate. A 144 Hz external display therefore gives about 72 fps in Safari (derived from `AnimationFrameRate.cpp`). Our caps follow the same rule (§3.1).
- **Thermals.**
  - The A13 sustains about 50–77 % of its peak GPU throughput once warm (AnandTech 2019, via iPhone 11 target doc §2.4).
  - Newer iPhones heat quickly at 120 fps (r/Genshin_Impact, 2026-02-23 [Single]).
  - Phone gates therefore read minutes 15–20.

### 2.4 Memory ceilings

- **iOS publishes no per-page limit.** iOS ends the WebContent process through jetsam. An Apple reply confirms it "actually is a jetsam (running over memory limit for the process)" (WebKit bug 312727, 2026). GPU allocations are charged to the page (iPhone 11 target doc §2.1).
- **The old total-canvas-memory limit is gone.** It existed through Safari 16, at RAM/4 on iOS. From Safari 17 on, the only iOS limit is a canvas area of 8192 × 8192 device pixels, which our canvases never approach.
- **WebGPU before R-A12 costs 4× in texture memory.** KTX2 decodes to RGBA, so the city's textures need 432 MiB instead of 90–108 MiB, about 686 MiB steady in all on an iPhone 11 (fast-load §1.6; iPhone 11 target doc §2.2). This is the main reason WebGL2 is the provisional Auto renderer (§1.3 item 7).

### 2.5 The desktop audience (Steam, September 2026)

- **GPUs:**
  - RTX 5070 6.15 % (it rose 2.38 points in one month, so treat it with care);
  - RTX 5060 4.40 %;
  - RTX 5060 Ti 4.06 %;
  - RTX 4060 3.89 %;
  - RTX 3060 3.66 %;
  - RTX 4060 Laptop 3.50 %;
  - RTX 3050 2.90 %;
  - GTX 1650 2.19 %.
- **VRAM:** 16 GB 27.21 %, 8 GB 26.71 %, 12 GB 13.06 %, 4 GB 5.13 %, 6 GB 5.12 %, 2 GB 3.69 %.
- **Displays:** 1080p is 47.91 % of primary displays.
- **What it means:**
  - desktop-ultra is a mainstream Steam class, not a niche;
  - most desktops render at 1080p, where Epic is cheaper than at the 1440p used in this plan's examples;
  - the GTX 1050 2 GB sits in the 3.69 % 2 GB bucket.

  Steam measures PC gamers, not our Thai browser audience. Phone and desktop shares must come from our own telemetry (MMP M4.3).

### 2.6 Sources for §2

All were fetched on 2026-10-02 unless a date is given. WebKit file paths refer to the `safari-7622-branch` (Safari 26.0) and `safari-7625-branch` (Safari 27.0). Matching Safari build numbers to branches is the research pass's inference.

- **Apple:**
  - support.apple.com/en-us/121032 (iPhone 16 Pro Max), 111829 (15 Pro), 111828 (15 Pro Max), 111865 (iPhone 11), 125090 and 125091 (17 Pro, 17 Pro Max);
  - apple.com/iphone-17/specs and apple.com/iphone-air/specs;
  - apple.com/os/ios ("iOS 27 is compatible with these devices", including iPhone 11);
  - newsroom: iOS 26 (2025-06-09), iPhone 16 Pro (2024-09-09), M1 (2020-11-10);
  - developer.apple.com: Safari 27 release notes (2026-09-14) and `MTLGPUFamily.apple6` ("correspond to the Apple A13 GPUs").
- **iPhone RAM:** GSMArena pages for the iPhone 11, 15 Pro, 16 Pro Max, 17, 17 Pro and Air.
- **WebKit:**
  - files: `UnifiedWebPreferences.yaml`, `AnimationFrameRate.cpp`, `Page.cpp`, `Document.cpp`, `HardwareCapabilities.mm`, `GPUAdapterInfo.h`, `WebGLRenderingContextBase.cpp`, `NavigatorBase.cpp`, `CanvasBase.cpp`, `PlatformEnable.h`;
  - bugs 173434, 272226, 278542 (2024-08-22) and 312727;
  - blog posts webkit.org/blog/17333 (2025-09-15) and 18325 (2026-09-17);
  - the "animation-frame-rate" explainer (2021-12-14).
- **Chromium and Chrome:**
  - `gpu_adapter.cc` and `webgl_rendering_context_base.cc`; Dawn `gpu_info.json`;
  - developer.chrome.com: "New in WebGPU" 121 (2024-01-18) and 146 (2026-02-25); WebGPU developer features (2025-06-03); Chrome 147 release notes (2026-04-07); memory and energy saver mode (2022-12-08);
  - chromestatus feature 6330376953921536.
- **Specs and compatibility data:**
  - W3C WebGPU Candidate Recommendation Draft (2026-09-15) and Device Memory Working Draft (2026-03-30);
  - MDN pages on `deviceMemory`, `getHighEntropyValues` and `requestAnimationFrame`;
  - MDN browser-compat-data;
  - caniuse "webgpu" (2026-09-30).
- **Mozilla:** `SanitizeRenderer.cpp` and `RuntimeService.cpp`.
- **GPUs:**
  - nvidia.com: RTX 5060 family, 50-series laptops, RTX 3060 and 4060 pages, and the compare page;
  - TechSpot RTX 5060 review (2025-05-22);
  - Wikipedia: GeForce 10 and RTX 50 series, the list of Nvidia GPUs, Intel Graphics Technology, RDNA 2, RDNA 3 and Apple M2.
- **Android:**
  - GSMArena pages for the Galaxy S23, S24 Ultra, S25, A15, Xiaomi 14, OnePlus 13, Civi 2, Razr 40, Poco X6, Edge 50 Pro and Redmi 12;
  - developer.android.com: texture compression (2025-07-21) and the Android baseline profile (2026-03-06).
- **Steam:** store.steampowered.com/hwsurvey ("Steam Hardware & Software Survey: September 2026").
- **Not verified:**
  - mesh shading on the A18 Pro;
  - M3 and M4 TFLOPS;
  - a numeric tab-kill threshold on 4 GB iPhones;
  - a Chrome-specific statement about 90–165 Hz rAF on Android.

---

## 3. Settings matrix per class

Each column shows what the class gets at its **expected Auto tier**, the tier XB1 should select on the class's reference device: Low, Medium, High, Low (Medium in brackets), High, Ultra and Epic, from left to right. §1.2 gives the safer tier used when the benchmark is inconclusive. A user-chosen preset is resolved through the same class ceilings (§7.1). Where a rule applies to every class, it follows the table.

### 3.1 Renderer, resolution, frame rate, anti-aliasing

| Row | mobile-low | mobile-mid | mobile-high | desktop-low | desktop-mid | desktop-high | desktop-ultra |
|---|---|---|---|---|---|---|---|
| Expected Auto tier | Low P | Medium P (Low if XB1 fails S2) | High P | Low (Medium if S2 passes) P | High P (MP §1 gate) | Ultra P | Epic P |
| Renderer (Auto) | WebGL2 P | WebGL2 P; WebGPU A/B on iOS 26/27 | WebGL2 P; WebGPU A/B **first** (iOS 26/27, Snapdragon 8 Gen 2+) | WebGL2 P | WebGL2 P. M: the 400-tree test gave WebGL2 0.82 ms vs WebGPU 3.23 ms (impostor-cards L74) | WebGL2 P; A/B after R-A12 | WebGL2 P; A/B after R-A12 |
| `powerPreference` | `"default"` P (CP §7.2) | `"default"` P | `"default"` P | `"high-performance"` P | `"high-performance"` P | `"high-performance"` P | `"high-performance"` P |
| Canvas DPR cap | 1.0 P | 1.175 (C-R-MOB §8.2); 2.0 native only if FSR wins its A/B (iPhone 11 target doc §4.1) P | 1.5 (of the 16 Pro Max's 3) P | 1.0 P | 1.25 P | 1.5 P | 2.0 P |
| 3D scale at start (FSR1 factor) | 0.88 by hardware scaling, no FSR P | 1.0 at DPR 1.175 by canvas scaling; no FSR by default (§1.3 item 13) P | 0.89, i.e. DPR 1.33, by canvas scaling P | 0.67 (FSR 1.5) P | 1.0 (off) P | 1.0 P | 1.0, plus SSAA 1.25 at ≤ 1440p P |
| Adaptive 3D scale range | 0.75–1.0 (hardware scaling) P | DPR 0.9–1.175 by canvas scaling, at most 5 sizes, each held ≥ 4 s (C-R-MOB §8.5; iPhone 11 target doc §4.2) P | DPR 1.0–1.5 by canvas scaling P | 0.50–0.77 P | 0.67–1.0 P | 0.77–1.0 P | 0.83–1.0 P |
| Example 3D render (canvas) | Galaxy A15, CSS 891 × 411 → 784 × 361 = 0.28 Mpx P | iPhone 11, CSS 896 × 414 → canvas = 3D 1052 × 486 = 0.51 Mpx at DPR 1.175 (today's mobile Medium); the browser scales it to 1792 × 828 P | iPhone 16 Pro Max, CSS 956 × 440 → canvas = 3D 1274 × 586 = 0.75 Mpx at DPR 1.33 P | 1080p → 3D 1280 × 720 = 0.92 Mpx P | 1080p native, 2.07 Mpx P | 1440p native, 3.69 Mpx P | 1440p × 1.25² = 5.76 Mpx; at 4K, FSR 1.3 → 4.9 Mpx P |
| `maxRenderPixels` (canvas) | 1.0 M P | 0.6 M P | 1.5 M (M-series iPads reach about 1.5 Mpx) P | 2.1 M P | 3.7 M P | 8.3 M P | 12.0 M P |
| Auto frame cap: base → ceiling (`frame-rate-policy.mjs`; auto-fps doc §2.4–2.5) | 30 → 30 P | 30 → 60. Auto climbs only with GPU-inclusive headroom, which Safari does not expose, so in practice 30; "60" stays a user opt-in (iPhone 11 target doc §4.1). Never 40 or 45 on a 60 Hz panel P | 60 when XB1's GPU-inclusive cost shows headroom (`higherCapOk`), else 30 → 60. Safari keeps rAF near 60 even on ProMotion (§2.3) P | 60 → 60; the policy steps down to 30 only at the resolution floor P | 60 (72 on a 144 Hz display) → display refresh P | 60 → display refresh P | 60 → display refresh P |
| MSAA / AA | none (no FSR, so no anti-aliased input is needed) P | MSAA 4× on the canvas, resolved on tile (C-R-MOB §8.2). If FSR wins its A/B, MSAA 4× moves to the FSR target and the context uses `antialias: false` (iPhone 11 target doc §4.1) P | MSAA 4× on the canvas, resolved on tile P | MSAA 4× on the small FSR target; context `antialias: false` P | MSAA 4× (today's `antialias: true`) P | MSAA 4× + A2C foliage P | MSAA 4× + A2C + SSAA 1.25; MSAA 8× WebGL2-only option P |
| FSR sharpness | — | — (FSR off by default) P | — P | 0.2 stops (code default) P | 0.2 P | 0.2 P | 0.2 P |

Rules for every class:
- **WebGPU MSAA.** WebGPU render targets accept 1 or 4 samples only (`render-scaling.ts:113–114`). "8×" exists only on WebGL2.
- **FSR replaces hardware scaling.** When FSR is active, the canvas stays at the class DPR cap and FSR does the scaling, so the DOM UI stays sharp.
- **How SSAA works.** Epic's SSAA is hardware scaling below 1/DPR with FSR off: `hardwareScalingLevel = 1 / (DPR × 1.25)`, and the browser's downscale resolves it. FSR1 cannot supersample, because its scale factor is ≥ 1 (`render-scale-controller.mjs` clamps to 1–3).
- **No FSR on mobile-low.** The FSR pass cost on Mali-G57-class GPUs is unknown, so mobile-low keeps today's bilinear hardware scaling. It switches to FSR only if the PENDING FSR doc shows the pass under 1.0 ms there.
- **Caps are refresh / n, never below 30** (`allowedFrameCaps` in `frame-rate-policy.mjs`; auto-fps doc §2.1).
  - 120 Hz allows 120 / 60 / 40 / 30; 144 Hz allows 144 / 72 / 48 / 36; 60 Hz allows 60 / 30.
  - Babylon's `maxFPS` accumulator gets the average right but paces unevenly (`abstractEngine.pure.js:417–431`). In the auto-fps simulation about half the frames at a 30 cap came at 16 or 50 ms.
  - Pacing therefore moves to `createPacedFrameRequester` on `engine.customAnimationFrameRequester`, and `engine.maxFPS` stays unset (auto-fps doc §2.3, §4.1).
- **Never set `maxFPS` to 0.** In 9.27.1, `maxFPS ≤ 0` sets `_minFrameTime = Number.MAX_VALUE` (`:411–413`), and the engine never renders again. "Uncapped" must be `undefined`.
- **A browser cap at 30 is detected, not fought.** The policy's `throttled` / `lowPowerSuspected` state (shown as `browserCap30` in the perf overlay) locks the cap at 30. It also withholds frame samples from the scale controller, so resolution does not drop for nothing (auto-fps doc §1.5; iPhone 11 target doc §2.3).
- **Context anti-aliasing is fixed at engine creation.** Classes that start with FSR active (desktop-low; the phone classes only if FSR wins its A/B) create the engine with `antialias: false`; FSR's reduced target carries its own MSAA (`render-scaling.ts` `samples`). The device class must therefore be known before `createRenderer` (§7.2; iPhone 11 target doc §4.1). While the class is still an undecided candidate set on a first run, create the engine with `antialias: false` and keep the FSR pipeline attached, at factor 1.0 if no upscaling is needed, so that MSAA still comes from FSR's target. The next session uses the persisted class.

### 3.2 Shadows, lighting, post

| Row | mobile-low | mobile-mid | mobile-high | desktop-low | desktop-mid | desktop-high | desktop-ultra |
|---|---|---|---|---|---|---|---|
| Shadow map × cascades / distance | 512 single map / 30 m (the iPhone 11 doc's phone Low; SKY's desktop Low is a fixed 40 m ortho frustum) P | 1024 × 2 / 55 m, λ re-solved so C0 still ends at 24 m; 40 m when hot (C-R-MOB §8.2, §8.5; the iPhone 11 target doc says 60 m, SKY's Medium row 85 m) P | 2048 × 2 / 85 m: SKY's Medium splits at 4× the texels P | 512 single / 40 m; Medium: 1024 × 2 / 85 m P | 2048 × 3 / 130 m, splits 24 / 55.5 / 130 P | 2048 × 4 / 190 m (SKY L492) P | 4096 × 4 / 250 m (fallback 3072 × 4); λ re-solved so C0 ends at 24 m P |
| PCF | LOW P | LOW, A/B against MEDIUM (iPhone 11 doc §4.1) P | MEDIUM P | LOW P | MEDIUM (PCF3) P | HIGH (PCF5) P | HIGH (PCF5) P |
| Shadow VRAM (SKY model: 6 B per texel; an estimate) | 1.6 MB P | 12.6 MB P | 50.3 MB P | 1.6 / 12.6 MB P | 75.5 MB P | 100.7 MB P | ≈ 403 MB (3072: ≈ 227 MB) P |
| Tree shadows | dapple cookies (SKY L546) P | cookies P | canopy proxies in C0 only. A stretch: SKY's phone column uses cookies; gate ≤ +0.7 ms (SKY L545 phone estimate) P | cookies P | proxies in C0 + C1 (SKY L545) P | proxies in C0 + C1 P | proxies in C0–C2 P |
| Glow: opt-in emitters only (ratio / kernel) | off P | 0.25 / 16 (SKY L578) with `mainTextureSamples: 1`; off when hot (C-R-MOB §8.2, §8.5, §9 item 5) P | 0.25 / 16, `mainTextureSamples: 1` P | off; Medium: 0.33 / 24 P | 0.5 / 32 (SKY L576) P | 0.5 / 32; HDR bloom candidate P | 0.5 / 32, or HDR bloom (kernel 64, scale 0.5) if its A/B passes P |
| Procedural surface detail (rock rules, water foam) | Blender bakes P | bakes P | bakes P | bakes P | runtime plugin (P10 rule 9) P | runtime P | runtime P |
| Canopy translucency (SKY L662) | off P | off P | on P | off P | on P | on P | on P |
| Clustered night lights | fallback: no hero lantern, hemi +35 %, painted pools (SKY L631–633) P | clustered if `isSupported` (batch 8 on mobile WebGL2) P | clustered; mushroom and wisp lights only if ≤ 1.0 ms (SKY L696) P | clustered P | clustered + High lights P | all lights P | all lights P |
| Cloud layers (SKY L689) | L1 P | L1 + L2 P | L1 + L2 P | L1 + L2 P | L1–L3 P | L1–L3 P | L1–L3 P |

Rules for every class:
- **Character contact.** AO blobs (1 draw) go under every character, and ground-contact AO is baked into the cell maps (SKY L533–538).
- **Grade.** ACES, with per-time-of-day ColorCurves, contrast and vignette (SKY §5.3: "LDR path, all tiers"). There is no LUT texture: Babylon has one LUT slot (recheck 16.2) and curves do the job.
- **SSAO and contact shadows.** Off on every class. SSAO2 is a candidate on Ultra and Epic only (SKY L539), and contact shadows on Epic only. Both are gated (§4).

### 3.3 Textures, LOD, impostors, vegetation, water, distance

| Row | mobile-low | mobile-mid | mobile-high | desktop-low | desktop-mid | desktop-high | desktop-ultra |
|---|---|---|---|---|---|---|---|
| Texture max size (KTX2 variant) | 512; own hero 1K P | 1K for everything, the own hero included (iPhone 11 doc §4.1: at most 1024² on phones) P | 2K terrain and characters, 1K props P | 1K P | 2K terrain and characters, 1K props (2 GB VRAM) P | 2K everywhere P | 2K everywhere + 4K where authored (terrain macro, landmarks, hero tree) P |
| GPU format after transcode (Babylon picks it from the caps, recheck 1.2) | UASTC → ASTC 4×4; ETC1S → ETC2 P | same P | same P | UASTC → BC7; ETC1S → BC7 or BC1/BC3 P | same P | same P | same P |
| Anisotropy (the "mip bias" knob, see note) | 2 P | 2, and 4 on terrain layers; 1 when hot (C-R-MOB §8.2, §8.5) P | 4 P | 4 P | 8 (TER tier 2) P | 8 P | 16 P |
| Terrain tier (TER L470–476) | 0 P | 1, fallback 0 (gate: Δ ≤ +1.5 ms, TER L793) P | 1 P | 0; Medium: 1 P | 2 P | 2 P | 2 P |
| Resident texture budget | 64 MiB (MMP §7) P | 110 MiB target (MMP); 256 MiB hard (iPhone 11 doc §4.1) P | 192 MiB P | 160 MiB P | 400 MiB (MMP desktop High) P | 640 MiB P | 1,024 MiB P |
| `lodDistanceScale` s, for characters: HRA bands and monster LOD distances × s (§3.4) | 0.6 P | 0.8 P | 1.0 P | 0.6 (0.8) P | 1.0 P | 1.25 P | 1.5 P |
| Static-mesh LOD1 / LOD2 coverage thresholds: base 0.035 / 0.006 (the oak, assets research L22) × `coverageScale` = clamp(2.07 Mpx ÷ the class's 3D Mpx, 0.36, 4), so a triangle covers about the same pixels on every class (C-R-MOB §8.2 uses × 4 on the iPhone 11) | × 4: 0.140 / 0.024 P | × 4: 0.140 / 0.024 P | × 2.8: 0.098 / 0.017 P | × 2.25: 0.079 / 0.014 P | × 1: 0.035 / 0.006 P | × 0.56 at 1440p: 0.020 / 0.003 P | × 0.36 at 1440p with SSAA: 0.013 / 0.002 P |
| Top LOD for props and monsters (heroes are always LOD0 in band A) | LOD1 P | LOD1 (bosses LOD0) P | LOD0 P | LOD1 P | LOD0 P | LOD0 P | LOD0 P |
| Cell representation (own / ring 1 / ring 2) | C2 / C2 / HLOD P | C1 / C2 / HLOD P | C0 / C1 / C2 P | C2 / C2 / HLOD P | C0 / C1 / C2 P | C0 / C0 / C1 P | C0 / C0 / C0 P |
| Tree impostor swap (shadow distance + 10 m; 10 m dithered band) | 40 m P | 65 m P | 95 m P | 50 m (95 m) P | 140 m P | 200 m P | 260 m P |
| Detail draw distance (cells, impostor end) | 150 m P | 180 m P | 230 m P | 150 m (180 m) P | 230 m (belts 90–220 m) P | 280 m P | 360 m P |
| Grass: f_tier / d_near · d_mid · d_end / visible clumps | 0.26 / 11.1 · 17.9 · 25.5 m / ≈ 110 P | 0.40 / 16.6 · 26.8 · 38.3 m / ≈ 420 (GRS L876) P | 0.58 / 22.1 · 35.7 · 51.0 m / ≈ 1,000 P | 0.36 / 13 · 21 · 30 m / ≈ 210 (GRS L872) P | 0.80 / 26 · 42 · 60 m / ≈ 2,000 (GRS L874) P | 1.00 / 32.5 · 52.5 · 75 m / ≈ 4,000 (GRS L875) P | near 1.00, far band 0.60 / 39 · 63 · 90 m / ≈ 7,000 (estimate) P |
| Grass draws (cap) / benders | 6 (8) / 1 P | 8 (10) / 1 P | 16 (20) / 2 P | 6 (8) / 1 P | 20 (24) / 4 P | 28 (32) / 4 P | 37 (40) / 6 P |
| Trees and flowers: `vegetationDensity` / `vegetationDistanceFactor` | 0.45 × 0.72 / 0.5 × 0.85 P | 0.7 × 0.72 / 0.75 × 0.85 P | 1.0 × 0.72 / 1.0 × 0.85 P | 0.45 / 0.5 P | 1.0 / 1.0 P | 1.25 / 1.25 P | 1.25 / 1.5 P |
| Water tier (WAT L551–563) | Low P | Low (Medium if ≤ 1.0 ms on the device) P | Medium P | Low (Medium at the Medium preset) P | High P | Ultra P | Ultra + foam detail (P4 option) P |

Rules for every class:
- **Far horizon.** The 512 m proxy ring and the 256 m macro HLOD (MMP §6) render on every class. A short detail distance therefore never shows a cut-off.
- **Phones and the detailed city.** The detailed city (about 900k triangles) has no phone variant yet. Phones keep the city HLOD until one exists (C-R-MOB §8.2; fast-load actions 3 and 13).
- **Fog.** It is identical on every class: the per-time art-directed fog, `amount = M·(1 − exp(−D·max(0, d − S)))·exp(−k·y)` (SKY L287–291, L383). Fog is look, not a performance knob.

Notes on §3.3:
- **No sampler mip bias.** 9.27.1 has no per-texture LOD bias (Local check: no `lodBias` in `Materials/Textures/*.d.ts`), and WebGL2 has no sampler bias. "Mip bias" is therefore implemented as:
  - variant selection: 2K → 1K is +1 mip, 1K → 512 is +2 mips;
  - `anisotropicFilteringLevel` (Babylon default 4).

  Alpha-tested cards that need sharper mips use the grass spec's baked coverage mips (`GRASS_MIPS_BAKED`, GRS L341).
- **Mobile grass factors.** Grass on mobile classes applies GRS's factors (density × 0.72, distances × 0.85, `f_far` 0.35; GRS L611, L656, L665). The mobile-low and mobile-high rows extend GRS's mobile rule to Low and High; they are not in GRS.
- **Epic grass keeps the art direction.** GRS generates the full Ultra set "so receipts and tests are identical across tiers" (L615). Ultra's near density is the art-directed maximum, with clustered tufts and real gaps (P3). Epic therefore does not raise near density: it extends the bands to the 90 m cap (GRS L655) and raises the far band from 0.40 to 0.60, so it is denser at distance. A 1.25× "lush" near-density variant needs the art gate first (§4).
- **Impostor swap.** The swap distance follows the trees decision rule "swap = shadowDistance + 10 with a 10 m crossfade band" (trees decision L166; impostor-cards L46). Impostors cast no shadows, so a tree keeps its shadow as long as it is a mesh.

### 3.4 Characters, effects, budgets

| Row | mobile-low | mobile-mid | mobile-high | desktop-low | desktop-mid | desktop-high | desktop-ultra |
|---|---|---|---|---|---|---|---|
| HRA character bands A / B / C (D beyond), × `lodDistanceScale` | < 9 / 9–21 / 21–36 m P | < 12 / 12–28 / 28–48 m P | < 15 / 15–35 / 35–60 m (HRA) P | as mobile-low (mobile-mid) P | < 15 / 15–35 / 35–60 m P | < 19 / 19–44 / 44–75 m P | < 22.5 / 22.5–52.5 / 52.5–90 m P |
| Monster LOD1 / LOD2 / cull (MON L637 × s) | 9 / 21 / 54 m P | 12 / 28 / 72 m P | 15 / 35 / 90 m P | 9 / 21 / 54 m P | 15 / 35 / 90 m P | 19 / 44 / 112 m P | 22.5 / 52.5 / 135 m P |
| Full-detail characters (bands A + B): players / monsters | 4 / 6 P | 6 / 8 P | 10 / 12 P | 6 / 8 P | 12 / 16 P | 20 / 24 P | 30 / 32 P |
| Animated characters (any band) | 20 P | 30 P | 40 P | 30 P | 50 (HRA L724 gate: ≤ 2.0 ms p95) P | 64 P | 100 P |
| Monster shadows | none (monsters code audit L593: none on Low) P | ≤ 15 m P | ≤ 30 m P | none P | ≤ 30 m (monsters code audit L593) P | ≤ 45 m P | ≤ 60 m P |
| Nameplates / damage numbers on screen | 6 / 20 (monster combat decisions L148, L155) P | 6 / 20 P | 6 / 20 P | 10 / 32 P | 10 / 32 P | 10 / 32 P | 10 / 32 P |
| Particle scale (VFX tiers) | 0.25: no lights, no lightning (vfx-sample-set-v1 L44) P | 0.5 P | 1.0 P | 0.25 P | 1.0 P | 1.0 P | 1.0 P |
| Live particles, all systems | 200 P | 300 target (v5 plan L501); hard cap 600, at most 120 per effect (C-R-MOB §8.2) P | 600 P | 600 P | 1,200 P | 2,000 (v5 L501: desktop High) P | 3,000 P |
| Weather particle budget (`weatherParticleBudget`) | 24 P | 64 P | 144 P | 24 P | 144 P | 288 P | 384 P |
| Waterfall mist + spray (WAT L563) | 8 + 12 P | 8 + 12 P | 12 + 24 P | 8 + 12 (12 + 24 at Medium) P | 16 + 40 P | 20 + 56 P | 20 + 56 P |
| Main-pass draw calls (view) | 80 (MMP) P | 100 main, ≤ 150 over all passes (shadows ≤ 40; glow, post and FSR ≤ 10), hard cap 200 (iPhone 11 target doc §4.1; MMP says 110; C-R-MOB allows ≤ 300 including shadows) P | 180 (MMP) P | 150 P | 250 (MMP) P | 350 P | 450 P |
| Visible triangles (view) | 150k (MMP) P | 350k main; ≤ 600k with the shadow passes (MMP; iPhone 11 target doc §4.1; C-R-MOB says about 400k including shadows) P | 900k (MMP) P | 500k P | 1.5M (MMP) P | 2.5M P | 4.0M P |
| Whole-page memory | ≤ 350 MB (MMP) P | target ≤ 350 MB (MMP); gate ≤ 500 MiB steady / ≤ 700 MiB peak (fast-load §1.6) until O-IPH T16 measures the kill point, then 60 % of that point (§1.3 item 11; C-R-MOB plans ≤ 900 MiB) P | target ≤ 500 MB (MMP); gate ≤ 1.0 GiB steady until a T16-style run on the device P | — | — | — | — |
| Frame-time gate (p95), a target and not a value | 33.3 ms | 33.3 ms | 16.7 ms | 16.7 ms (33.3 at 30 fps) | 16.7 ms (MP §1) | 16.7 ms at 1440p Ultra | 16.7 ms at Epic; 8.3 ms when the cap is 120 |

Rules for every class:
- **Animation LOD.** HRA L718–721 applies on every class: A is full rate; B is full rate with fingers, twists and pauldrons masked; C is paused groups plus `goToFrame` every 2nd–3rd frame (every 4th on mobile-low); D is paused.
- **Never reduced.** Telegraphs, party members, the current target and HP plates stay on every tier (inbox B10). The party and the target are always band A.
- **The VFX bar still caps every effect.** At full scale an effect gets ≤ 10 draw calls, ≤ 250 particles and ≤ 5 ms CPU p95 on the GTX 1050 (VFX L37; inbox B1). This supersedes the 12-draw / 300-particle budget (handoff L9), and an effect owns at most one pooled light. Ultra and Epic never author bigger effects: their headroom only raises the number of concurrent effects (the live cap above). Low drops secondary particles first and never the telegraph (vfx-sample-set-v1 L37).

---

## 4. Ultra and Epic extras

Each extra ships off by default unless its gate has passed on the named class. The gates use the capture harness (C-P0-CAP): the four locked views, four times of day and both renderers, with p50/p95 over 600 frames after 120 warm-up frames (SKY L849).

| Extra | Tier | Expected cost (P) | Gate that proves it |
|---|---|---|---|
| **Denser grass**: the full art-directed density (Ultra), then the bands extended to 90 m with a 0.60 far band (Epic) | Ultra, Epic | Ultra +0.7 ms over High on the GTX 1050 (GRS L874–875: 2.2 vs 1.5 ms). Epic ≈ +0.5–0.9 ms over Ultra at 1440p on RTX 4060-class GPUs (estimate from fragment count) | Grass GPU p95 ≤ 2.2 ms at Ultra on desktop-high at 1440p, and ≤ 2.5 ms at Epic on desktop-ultra. Submitted ≤ 12k (Ultra) and ≤ 18k (Epic). No shimmer beyond d_mid in the motion capture. A 1.25× near "lush" density also needs the art review (clusters with real gaps, P3) |
| **Longer view distance**: detail cells to 280 m (Ultra) and 360 m (Epic), with impostor ends and residency to match | Ultra, Epic | +4–8 resident cells: +60–120 MiB GPU, +0.2–0.4 ms CPU culling (estimate) | p95 inside budget on the elevated view. Residency inside the class texture budget. No streaming hitch > 50 ms (MMP: ≤ 100 ms at Medium) |
| **Higher-resolution textures**: 2K everywhere (Ultra); 4K terrain macro, landmarks and hero tree where authored (Epic) | Ultra, Epic | +150–300 MiB VRAM; +20–40 MB downloaded after spawn, never before | Texture MiB ≤ class budget, measured by `render-diagnostics`. KTX2 quality gates (TER L698–703). The upgrade pass never causes a frame > 2× budget |
| **More cascades and resolution**: 2048 × 4 to 190 m (Ultra), 4096 × 4 to 250 m (Epic) | Ultra, Epic | Ultra 100.7 MB and Epic ≈ 403 MB VRAM (SKY model). Shadow render: SKY L691 gives 1.8 ms for 3 × 2048 on the GTX 1050; Epic is estimated at +0.8–1.5 ms on desktop-ultra | Shadow-pass GPU ≤ 2.5 ms at 1440p on desktop-ultra. C0 ends at 24 m (SKY L509). No cascade shimmer in the walk capture. Total GPU memory ≤ 3 GiB |
| **Contact shadows**: a screen-space ray march toward the sun over the depth buffer, about 0.5 m long, applied to characters and props | Epic (experiment) | +0.6–1.2 ms at 1440p, plus depth from the prepass renderer (MRT) rather than a second scene pass (estimate). Not in Babylon 9.27.1 core (Local check: no contact-shadow class), so it is custom GLSL + WGSL | A blind A/B passes at 3 of the 4 locked views (feet, props on grass, the altar). ≤ 1.0 ms. No halos at depth edges. Both renderers. No CDN shader fetch (recheck N1) |
| **SSAO2**: only if measured worth it | Ultra, Epic candidate (SKY L539) | 1.5–2.2 ms on the GTX 1050 (SKY L539); estimated 0.6–1.0 ms on desktop-ultra at 1440p | The A/B beats the baked AO (TER L455, SKY L538). ≤ 1.0 ms. No WebGPU sky darkening (CP §3.13, t/63942). Otherwise it stays off: baked AO remains the default everywhere |
| **Higher MSAA / supersampling** | Epic | MSAA 4× is already on. SSAA 1.25 renders 1.56× the pixels (+40–60 % GPU). MSAA 8× exists on WebGL2 only | p95 inside budget at 1440p. Foliage edge-shimmer metric (frame-to-frame luminance delta on alpha edges) improves by ≥ 25 % against MSAA 4× alone |
| **Alpha-to-coverage foliage** | Ultra, Epic | ≤ +0.1 ms (GRS L746 gate) | GRS §6.4 gate. Needs an MSAA target, so it conflicts with the HDR candidate's `samples = 1` unless that pipeline uses `samples = 4` (recheck C13, N7) |
| **HDR bloom pipeline** | Ultra, Epic candidate | +2.0 ms, −1.0 ms glow (SKY L698) | SKY L584 A/B. On Epic it must keep `samples = 4` so that A2C survives |
| **120 fps and more** where the platform allows | Every desktop class in Auto, through the frame-rate policy's probes at full resolution | A CPU frame of 6–7 ms or less at 144 Hz | The policy's own probation: 6 s at max scale, credited after 60 s (auto-fps doc §2.4). Plan gate on desktop-ultra: p95 ≤ 8.3 ms on the solo walk and ≤ 11.1 ms in the party fight at a 120 cap. Phones never go above 60 in Auto: 90 and 120 are user choices on Android, and on iOS only when rAF measures ≥ 100 Hz (§2.3) |
| **More full-detail characters**: 30 players and 32 monsters | Epic | +1–2 ms CPU (estimate from HRA L714) | HRA L724 scaled: ≤ 3.0 ms p95 for 100 animated characters on desktop-ultra |

---

## 5. Auto-detect design

### 5.1 Signals

| Signal | API | Where it exists | Used for | Weight |
|---|---|---|---|---|
| WebGPU adapter | `navigator.gpu.requestAdapter({ powerPreference })`: `adapter.info` (vendor, architecture), `adapter.features`, `adapter.limits`, fallback flag | Chrome/Edge desktop; Chrome Android 12+ on Qualcomm/ARM; Safari 26/27 on iOS, iPadOS and macOS 26+. Secure contexts only; off in Lockdown Mode. `adapter.info`: Safari says "apple" in every field, Chrome gives vendor and architecture only (§2.2) | GPU family prior; software-adapter detection; `texture-compression-bc` present = desktop-class GPU | High on Chrome, low on Safari |
| WebGL renderer string | `WEBGL_debug_renderer_info` → `UNMASKED_RENDERER_WEBGL` | Chrome/Edge: the real ANGLE string. Safari: always "Apple GPU". Firefox: bucketed to a similar model (§2.2) | GPU model regex table (§5.2) | High where unmasked |
| Device memory | `navigator.deviceMemory` | Chromium only, secure contexts. Chrome 147+: desktop 2–32, Android 1–8 (§2.2) | Caps the class: ≤ 2 GB → at most low; 4 GB → at most mid | Medium |
| CPU cores | `navigator.hardwareConcurrency` | Chrome: the real count. Safari: 4 or 8. Firefox with resistFingerprinting: 4 or 8 (§2.2) | < 4 cores → low class | Low |
| Screen | `screen.width/height`, `devicePixelRatio`, `matchMedia('(pointer: coarse)')`, `(hover: none)`, `navigator.maxTouchPoints`; iPad shows as `MacIntel` with touch points > 1 | All | Form factor (mobile vs desktop); iPhone model family from CSS size × DPR (§5.2); pixel budget | Medium |
| Client Hints | `navigator.userAgentData.mobile`; `getHighEntropyValues(["model", "platform", "platformVersion", "formFactors"])`; `Sec-CH-UA-Model` | Chromium only. Safari freezes the iOS version in its UA (§2.2) | Android model string → class table; form factor | Medium on Android |
| Refresh rate | Median rAF interval over 30–60 idle frames in the loading screen (no API exists, §2.3) | All | Frame-cap options; browser-cap detection (`browserCap30`, §5.6) | High |
| Micro-benchmark | XB1 (§5.3) | All | The tier inside the class range | **Decisive** |

**Policy change for root to approve.** `graphics-quality.mjs` says "model names are not detected" (L18–19) and "does not infer hardware from user-agent strings" (L8–9). This plan keeps that module pure. Hardware inference moves to a separate `device-class.mjs`, which uses GPU strings and Client Hints as **priors only**: they choose the class and its Auto range, and the benchmark chooses the tier. Safari exposes no GPU model at all, so an Apple device is always decided by screen, features and benchmark.

### 5.2 Classification (pure function, unit-tested)

```text
classify(signals) -> { deviceClass | candidates[2], confidence: "high"|"medium"|"low", reasons[] }

1. formFactor:
   mobile  if userAgentData.mobile === true
           or the UA has iPhone|iPod|Android…Mobile
           or (iPad: platform "MacIntel" and maxTouchPoints > 1)
           or (pointer: coarse and hover: none and max(screen.w, screen.h) ≤ 1366 CSS px)
   desktop otherwise. Window size never decides form factor; it only sets the pixel budget.
2. Software or fallback GPU (adapter fallback flag, or a renderer matching
   /SwiftShader|llvmpipe|Basic Render|Software/i):
   -> desktop-low / mobile-low, confidence high, Low preset, warning toast (§5.8).
3. GPU-string table (first match wins). It is data, versioned with XB1, and owned by fixture tests.
   Boundaries by FP32 throughput: mid ≈ 1.5–6 TFLOPS, high ≈ 6–16, ultra ≥ 16.
   Illustrative v1:
   desktop-ultra  /RTX 50[6-9]0|RTX 4060 Ti|RTX 40[7-9]0|RTX 30[7-9]0|RX 6[89]\d0|RX 7[7-9]00|RX 90\d0/
   desktop-high   /RTX (20[6-8]0|3050|3060|4050|4060)|GTX (1070|1080)|RX (5[67]00|6[67]\d0|76\d0)|Arc\(TM\) (A7|B5)|Apple M\d (Pro|Max|Ultra)/
   desktop-mid    /GTX (1050|1060|1630|1650|1660)|RX (4[6-8]0|5[5-9]0)|Radeon (680M|760M|780M|880M|890M)|Intel\(R\) Arc\(TM\) Graphics|Adreno.*X1|Apple M\d\b/
   desktop-low    /Intel.*(UHD|HD Graphics|Iris)|Radeon( TM)? (Vega|Graphics)/
   mobile-high    /Adreno \(TM\) (7[3-9]\d|8\d\d)|Immortalis|Mali-G(71[05]|72\d) MC(9|1\d)|Xclipse 9/
   mobile-mid     /Adreno \(TM\) (6[4-9]\d|7[0-2]\d)|Mali-G(61\d|6[89]|7[6-9]|71\d)|Xclipse [5-8]/
   mobile-low     /Adreno \(TM\) ([1-5]\d\d|6[0-3]\d)|Mali-G([0-5]\d|6[0-7]|7[0-2])|PowerVR/
4. Apple (WebGL "Apple GPU", or WebGPU adapter info "apple"). Safari reveals no model (§2.2), so the
   key is WebGPU presence plus the portrait CSS screen size and DPR (min × max, so orientation does not matter):
   - no WebGPU on a secure origin -> candidates [mobile-low, mobile-mid]; XB1 decides.
     A11/A12 iPhones stay below iOS 26, and Lockdown Mode also removes WebGPU.
     On an insecure origin (a LAN http test) WebGPU is always absent, so the screen rules below apply instead;
   - 414 × 896 @2 -> mobile-mid, confidence high (the iPhone 11; the XR cannot run iOS 26);
   - 440 × 956 @3 -> mobile-high, confidence high (only the 16 Pro Max and 17 Pro Max have this screen);
   - 402 × 874 @3 (16 Pro, 17, 17 Pro) and 420 × 912 @3 (Air) -> mobile-high;
   - 393 × 852 @3 and 430 × 932 @3 (A16, A17 Pro and A18 phones share them) -> candidates [mobile-mid, mobile-high];
   - any other iPhone screen (A13–A15 models) -> mobile-mid;
   - `texture-compression-bc` on a touch device (M-series iPad) -> candidates [mobile-high, desktop-mid];
   - Mac Safari -> candidates [desktop-mid, desktop-high].
   The size table is data with fixture tests. The 11, 15 Pro, 15 Pro Max, 16 Pro Max, 17, Air, 17 Pro and 17 Pro Max
   sizes come from Apple's published resolutions (§2.6); fill in the remaining models from Apple's spec pages.
   Display Zoom shrinks the CSS size, so a zoomed phone reads as a smaller class; XB1 and promotion (§5.6) recover [Inference].
5. Caps from the browser's own numbers (Chromium only, §2.2):
   - deviceMemory ≤ 2 -> at most *-low; deviceMemory 4 -> at most *-mid
     (Chrome 147+ reports 2–32 on desktop and 1–8 on Android);
   - hardwareConcurrency < 4 -> at most *-low (Safari reports 4 or 8, so this never fires on Apple devices).
6. Nothing matched (for example a GPU newer than the table) -> every class of that form factor is a candidate, confidence low;
   XB1 runs all of its steps (S1–S5 on desktop, S1–S3 on mobile).
7. Whenever the result is a candidate pair, XB1's highest passing step picks the class:
   - desktop: S1–S2 -> desktop-low, S3 -> desktop-mid, S4 -> desktop-high, S5 -> desktop-ultra;
   - mobile: S1 -> mobile-low, S2 -> mobile-mid, S3 -> mobile-high;
   - the result is clamped to the candidates. An inconclusive XB1 keeps the lowest candidate.
```

### 5.3 The first-run micro-benchmark (XB1)

**When it runs:**
- the first session on a device;
- on "Re-detect" (ตรวจเครื่องใหม่);
- when the fingerprint changes (§5.5);
- once the profile is 30 days old;
- at the next load after sustained headroom asks for a promotion (§5.6).

It never runs on a return visit with a valid profile, so it costs 0 s there.

**Where it runs:**
- in the `renderer` bootstrap phase, after the engine is created (`bootstrap-progress.mjs` phases: content → renderer → codecs → assets → …);
- on the real game canvas, behind the opaque loading overlay, so the present path and pipeline formats are the real ones;
- GLB and manifest downloads may proceed in parallel. KTX2 transcode workers are held until XB1 ends, so that CPU contention does not skew a 4-core phone.

**Duration:** 1.5–3.0 s, hard cap 3.0 s.
- About 0.4–0.8 s is setup and shader compilation. These are the same PBR + CSM + plugin variants the zone uses, so the compile doubles as warm-up (CP §6.1).
- Then 3–5 load steps of about 0.3 s each.

**Content.** Everything is procedural: no download, ≤ 24 MiB GPU.
- A 64 m terrain patch: 1 draw, PBR with the terrain plugin at the step's terrain tier, layers generated on the CPU.
- Grass: one thin-instance batch of the GRS clump (12 triangles), alpha test, wind plugin.
- Trees: LOD1-like proxies (1.6k triangles, alpha-tested card crown), thin instances, casting into the CSM.
- Characters: skinned capsules (2.5k triangles, a 43-joint chain animated procedurally), so skinning and bone textures are exercised.
- Sun CSM; 4 registered glow emitters; ACES; FSR1 at the class start scale where the class uses it.
- All cascade-count variants compile during setup (`SHADOWCSMNUM_CASCADES` is a define).
- XB1 renders on the real canvas with each tier's sample count, so on WebGPU it also creates the render pipelines the zone needs. `forceCompilationAsync` alone does not create pipelines (fast-load §2.7); where XB1's meshes differ from the zone's, use `createRenderPipelineAsync`. The reveal gate is `WebGPUCacheRenderPipeline.NumPipelineCreationLastFrame` = 0 on every frame after the loading screen.

**Load steps.** The grass counts are GRS's "submitted" estimates:

| Step | Probes | Grass instances | Trees | Characters | Shadows before class ceilings |
|---|---|---|---|---|---|
| S1 | Low | 500 | 20 | 4 | 512 single |
| S2 | Medium | 1,700 | 40 | 8 | 1024 × 2 |
| S3 | High | 4,500 | 60 | 12 | 2048 × 3 |
| S4 | Ultra | 9,000 | 90 | 20 | 2048 × 4 |
| S5 | Epic | 16,000 | 120 | 30 | 4096 × 4 |

Each step renders its preset as resolved for this class and screen (§7.1): canvas size, FSR scale, MSAA and the class's shadow ceilings. On an iPhone 11, S2 is therefore 1052 × 486 by canvas scaling, with MSAA 4× and 1024 × 2 shadows to 55 m.

- mobile-low and mobile-mid run S1–S2, plus S3 when the class is a candidate pair (Apple @3). mobile-high runs S1–S3.
- Desktop classes run S2–S5, starting at S1 only when the GPU string is unknown or integrated.
- The run stops at the first failing step.

**Timing.** For each frame:

```text
t0 = performance.now(); scene.render(); sync(); cost = performance.now() − t0
```

- `sync()` is a 1-pixel `gl.readPixels` on WebGL2, or `await device.queue.onSubmittedWorkDone()` on WebGPU.
- The sync makes the cost independent of vsync and of the 60 Hz rAF cap. It serialises CPU and GPU, so it overestimates. The pass factor k absorbs that bias, calibrated per renderer.
- When a GPU timer exists, its value is recorded too, but only as telemetry. Timer sources: `EXT_disjoint_timer_query_webgl2` (Chrome; Safari's WebGL2 has none), or WebGPU `timestamp-query` after R-A12. Chrome quantises WebGPU timestamps to 100 µs unless its developer flag is on. Safari exposes `timestamp-query` only where the GPU samples counters at stage boundaries; for the A13 that stays UNVERIFIED until O-IPH T0 (§2.2). Scoring always uses the same sync method on every device.
- The first 4 frames of each step are discarded (pipeline creation); at least 12 frames are kept; the statistic is p75.

**Pass rule.** Step *s* passes when:

```text
p75(cost_s) ≤ k × 1000 / fps_s
```

- `fps_s` is the class's base cap: 30 on phones, 60 on desktop.
- k = 0.60 reserves 40 % for game work the benchmark does not run: network, UI, animation sampling, GC.
- Per-class k values are calibrated in the device lab (§8.4), then from telemetry.

| Class | Steps | Budget per step (p75 ≤) |
|---|---|---|
| mobile-low, mobile-mid | S1–S2 (S3 for a candidate pair) | 20.0 ms (30 fps × 0.6). mobile-mid's "Smooth" 60 is never switched on automatically (iPhone 11 target doc §4.1) |
| mobile-high | S1–S3 | 20.0 ms per step. Then `higherCapOk` when the chosen step's p75 ≤ 10.0 ms. XB1's synced cost is GPU-inclusive, which is the evidence the frame-rate policy needs before a phone may run above 30 (auto-fps doc §1.5 item 4); the class base then becomes 60 |
| desktop-low | S1–S2 | 10.0 ms at 60 fps; when S1 fails at 10 ms but passes at 20 ms, the result is Low at 30 fps |
| desktop-mid, desktop-high, desktop-ultra | S2–S5 | 10.0 ms at 60 fps. Caps above 60 are left to the frame-rate policy's runtime probes (auto-fps doc §2.4) |

**Result:**

```text
benchTier     = highest passing step
tier          = clamp(benchTier, class.auto[0], class.auto[1])
higherCapOk   = mobile-high only (table above)
```

The raw per-step p75 values are stored for calibration.

**Inconclusive.** These cases use the class default from §1.2, do not persist a tier, and retry next session:
- the page goes hidden;
- a rAF interval exceeds 100 ms three times;
- context loss;
- the time cap is reached.

**Throttled.** A rAF of about 30 Hz on a display of 60 Hz or more means a browser throttle (§2.3, §5.6). On Safari that is Low Power Mode, a media session, visual idleness or a non-interacted cross-origin iframe; on Chrome it can be Energy Saver. XB1's timing does not depend on rAF, so the tier result is still valid for this session, but it is not persisted. The cap stays at 30, and the toast in §5.8 explains it.

### 5.4 Scores to tiers, in one line per class

| Class | No step passes | Highest step passed: S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|---|
| mobile-low | Low at the lowest 3D scale | Low | Low (Medium manual) | — | — | — |
| mobile-mid | Low at the lowest 3D scale | Low | Medium | Medium. For an Apple candidate pair, the class becomes mobile-high at High | — | — |
| mobile-high | Medium at the lowest 3D scale | Medium | Medium | High | — | — |
| desktop-low | Low at 30 fps | Low | Medium | Medium (High manual) | — | — |
| desktop-mid | Medium at the lowest 3D scale | — | Medium | High | High (Ultra manual: the SKY 45 fps opt-in) | High |
| desktop-high | High at the lowest 3D scale | — | High | High | Ultra | Ultra (Epic manual) |
| desktop-ultra | Ultra at the lowest 3D scale | — | Ultra | Ultra | Ultra | Epic |

Desktop classes start at S2 when the GPU string is known to be discrete, which is why their S1 column is "—".

"At the lowest 3D scale" means the adaptive controller starts at the bottom of the class range (§3.1).

### 5.5 Persistence per device

The profile lives in localStorage under a new key, next to the existing preference key (`aetherfield_graphics_quality_v1`). It keeps the existing `aetherfield_` prefix:

```json
{
  "key": "aetherfield_device_profile_v1",
  "version": 1, "benchVersion": "xb1",
  "fingerprint": "hash(GPU renderer | adapter vendor+architecture | UA brand+major | platform | CSS screen @ DPR bucket | deviceMemory | cores)",
  "deviceClass": "mobile-high", "confidence": "medium", "reasons": ["apple-gpu", "screen-956x440@3", "xb1-s3-pass"],
  "renderer": "webgl2", "refreshHz": 60, "throttled": false,
  "bench": { "renderer": "webgl2", "timer": "sync", "ms": 2140, "tier": "high", "higherCapOk": false,
             "steps": [{ "id": "S1", "p75": 6.1, "n": 14 }, { "id": "S2", "p75": 8.0, "n": 13 }, { "id": "S3", "p75": 9.4, "n": 12 }] },
  "autoTier": "high", "autoTierCap": null, "stepDowns": [], "createdAt": "2026-10-02T09:00:00Z", "validatedAt": "2026-10-02T09:00:00Z"
}
```

- **Per device.** localStorage is per origin and per browser profile, so each device and browser keeps its own profile. Graphics settings are never synced to the account. When account preferences sync later, the graphics keys stay excluded.
- **Invalidation.** Any of these re-runs XB1 at the next load:
  - a fingerprint change (new GPU, driver string, browser major version or screen class);
  - a `benchVersion` change;
  - age over 30 days;
  - "Re-detect".
- **Storage failure.** If storage is blocked, the profile is session-only, as the preference already is (`graphics-quality.mjs:110–117`).

### 5.6 Re-evaluation through sustained performance

The ladder is the brief's order: **resolution first, then the frame cap, then a tier step-down suggestion**. It reuses `render-scale-controller.mjs`, whose state already exposes `deficitMs`, `surplusMs`, `bound`, `atMin` and `atMax`.

| Stage | Trigger | Action | Limits |
|---|---|---|---|
| 1. Resolution | The controller's own windows (1 s, miss ratio and GPU load) | Desktop: the FSR scale moves inside the class range (§3.1). Phones step one rung at a time (C-R-MOB §8.5): DPR 1.175 → 1.0; glow off; `shadowMaxZ` 55 → 40 m; vegetation −30 % (prefix count); anisotropy 2× → 1×; DPR 1.0 → 0.9. Each rung changes only uniforms, sizes or CPU work, never a shader define | Quantum 0.05, warm-up 12 frames (code defaults). On iOS: at most 5 sizes, each held ≥ 4 s, because Babylon keeps old post-process targets for 100 renders (iPhone 11 target doc §4.2 item 3; t/52502). Phones step back up in reverse only with ≥ 25 % headroom for 10 s, outside combat, at most once every 30 s (C-R-MOB §8.5) |
| 2. Frame cap | `deficitMs ≥ 3 s` with `atMin`, or a CPU-bound deficit that resolution cannot fix | The frame-rate policy drops to the highest allowed cap ≤ 1.05 × the achieved fps (auto-fps doc §2.4) | 3 s minimum dwell. On desktop, a cap held below the class base for ≥ 60 s also counts toward stage 3, so the player is offered a lower tier instead of staying at 30 |
| 3. Tier step-down suggestion | Stage 2 at its floor and still `deficitMs ≥ 30 s` | Auto: a toast (§5.8), then the lower tier applies at the next loading screen or zone change, never mid-fight. `autoTierCap` is stored with a 7-day expiry. Manual: the toast only suggests | At most one tier change per session |
| 4. Promotion | `atMax` and `surplusMs ≥ 5 min` at load < 0.6, in a session without a step-down | The frame-rate policy climbs back first, probing at max scale (auto-fps doc §2.4). After 10 more minutes, schedule XB1 at the next load to try the next tier | No promotion within 3 sessions of a step-down |

**Browser throttles are not overload.** A median rAF interval near twice the display interval while the CPU frame time stays low (`browserCap30` in the overlay; `throttled` / `lowPowerSuspected` in `frame-rate-policy.mjs`) is a browser cap, not a slow GPU (§2.3). The policy proves it with idle-frame probes and locks the cap at 30. It withholds frame samples from the scale controller, so neither resolution nor tier changes (auto-fps doc §1.5, §2.2; iPhone 11 target doc §2.3, §4.3).

Thermal handling on phones: a slow decay of `loadRatio` at constant scene content is thermal, not content. The A13 sustains about 50–77 % of its peak GPU throughput after a few minutes (§2.3), which is why phone gates use minutes 15–20. Stage 1 absorbs it. A thermal step-down is persisted only if it repeats in two sessions.

### 5.7 User override

- Auto never changes an explicit choice. It only suggests: "เครื่องยังมีกำลังเหลือ" or "เครื่องทำงานหนัก".
- An explicit preset is resolved through the class ceilings.
  - The memory-heavy ceilings (`maxRenderPixels`, `shadowMapSize`, `cascades`, `textureMaxSize`) are hard on every class. They are sized to the class's memory: on phones they prevent tab kills (O-IPH gate: "no tab kill in 20 min"); on a 2 GB GTX 1050 they prevent VRAM thrash.
  - Everything else follows the chosen preset: density, distances, counts, effects and post. Epic chosen on a GTX 1050 is Epic density and distance with 2048 shadows and 2K textures, plus a warning line.
  - The menu offers presets up to the class's `manualMax`. Above the Auto range, the summary shows "อาจไม่ลื่นบนเครื่องนี้" (may not run smoothly on this device).
- Advanced toggles are stored as `overrides` in the v2 preference record (§7.1). Any override turns the preset label into "กำหนดเอง (Custom)".
- "รีเซ็ตเป็นอัตโนมัติ" (Reset to Auto) clears the preset and the overrides. It keeps the device profile.

### 5.8 Settings UI (for the UI thread)

| Row | Thai label | English | Values | Applies |
|---|---|---|---|---|
| Graphics quality | คุณภาพกราฟิก | Graphics quality | อัตโนมัติ (แนะนำ) / ต่ำ / ปานกลาง / สูง / สูงมาก / สูงสุด (desktop only) | Now, except texture size (at the next zone load) |
| Summary line | เครื่องนี้: มือถือระดับสูง · แนะนำ: สูง · 60 FPS · WebGL2 | This device: High-end phone · Recommended: High · 60 FPS · WebGL2 | read-only | — |
| Re-detect | ตรวจประสิทธิภาพเครื่องใหม่ | Re-detect device | button; runs XB1 at the next load | Next load |
| Advanced (collapsed) | ตั้งค่าขั้นสูง | Advanced | — | — |
| Frame rate | อัตราเฟรม (FPS) | Frame rate (FPS) | The auto-fps doc §4.4 row and status lines, verbatim: อัตโนมัติ (แนะนำ) / 30 · ประหยัดแบต / 60 / 90 / 120 / สูงสุดตามจอ. An option that is not exact on this display shows its real cap, e.g. "60 (จอนี้ใช้ 72)" | Now |
| Dynamic resolution | ปรับความละเอียดอัตโนมัติ | Dynamic resolution | เปิด / ปิด | Now |
| 3D resolution | ความละเอียดภาพ 3 มิติ | 3D resolution | 50–100 %, clamped to the class range of §3.1 (fixed when dynamic is off) | Now |
| Sharpness | ความคมชัด (FSR) | Sharpness (FSR) | 0–1 | Now |
| Anti-aliasing | การลบรอยหยัก | Anti-aliasing | ปิด / MSAA 4× / MSAA 4× + SSAA (Epic) | Now for the FSR target; the canvas setting changes at the next reload (§3.1) |
| Shadows | คุณภาพเงา | Shadow quality | ต่ำ / ปานกลาง / สูง / สูงมาก / สูงสุด | Now (rebuilds the generator, as `applyGraphics` does) |
| View distance | ระยะการมองเห็น | View distance | ใกล้ / ปานกลาง / ไกล / ไกลมาก / ไกลสุด | Now |
| Grass and foliage | ความหนาแน่นหญ้าและต้นไม้ | Grass and foliage | ต่ำ – สูงสุด | Now (prefix count, GRS L612) |
| Texture quality | คุณภาพพื้นผิว | Texture quality | 512 / 1K / 2K / 4K (4K on Epic only), never above the class ceiling | Next zone load ("มีผลเมื่อโหลดพื้นที่ใหม่") |
| Glow | แสงเรืองรอง | Glow | เปิด / ปิด | Now |
| Effects | เอฟเฟกต์ | Effects | เต็ม / ลดลง ("telegraph, ปาร์ตี้ และหลอด HP แสดงครบเสมอ") | Now |
| Detailed characters | ตัวละครที่แสดงแบบละเอียด | Detailed characters | 4 – 32 | Now |
| Renderer | ตัวเรนเดอร์ | Renderer | อัตโนมัติ / WebGPU / WebGL2 ("ต้องโหลดเกมใหม่") | Reload |
| Battery saver (mobile) | โหมดประหยัดแบตเตอรี่ | Battery saver | เปิด / ปิด (30 fps, 3D scale −15 %) | Now |
| Performance overlay | แสดง FPS | Show FPS | เปิด / ปิด (R-PERF `?perf=1` panel) | Now |

Toasts:
- **Step-down.** "เครื่องทำงานหนักต่อเนื่อง แนะนำลดคุณภาพเป็น «ปานกลาง» เพื่อให้ลื่นขึ้น", with buttons [ลดเลย] [ไว้ทีหลัง].
- **Auto applied.** "ปรับคุณภาพอัตโนมัติเป็น «ปานกลาง» แล้ว เปลี่ยนได้ในหน้าตั้งค่า".
- **Promotion.** "เครื่องยังมีกำลังเหลือ ลองเพิ่มคุณภาพเป็น «สูง» ไหม?"
- **Browser cap at 30.** Use the auto-fps doc's `lowPowerSuspected` status line (§4.4): "เครื่องจำกัดไว้ที่ 30 FPS (โหมดประหยัดพลังงานหรือประหยัดแบตของเบราว์เซอร์)". The page cannot tell Low Power Mode from the other browser caps (iPhone 11 target doc §2.3).
- **Software GPU.** "ไม่พบการเร่งกราฟิกด้วยการ์ดจอ เกมจะทำงานช้า ลองเปิด Hardware acceleration ในเบราว์เซอร์".

Device class names in Thai, for the summary line:

| Class | Thai name |
|---|---|
| mobile-low | มือถือรุ่นเริ่มต้น |
| mobile-mid | มือถือระดับกลาง |
| mobile-high | มือถือระดับสูง |
| desktop-low | คอมพิวเตอร์ (การ์ดจอออนบอร์ด) |
| desktop-mid | คอมพิวเตอร์ระดับกลาง |
| desktop-high | คอมพิวเตอร์ระดับสูง |
| desktop-ultra | คอมพิวเตอร์ระดับสูงสุด |

---

## 6. Content requirements for the asset pipeline

### 6.1 LOD chain per asset class

Each LOD0 keeps the full authored detail; it is what Ultra, Epic and (for characters and near objects) mobile-high draw.

| Asset class | LOD0 | LOD1 | LOD2 | Far form | Textures (2K / 1K / 512 variants) | Source |
|---|---|---|---|---|---|---|
| Hero body + armour | 12k tris | 6k | 2.5k | — (party and target always band A) | 2048 atlas; 1K and 512 variants | HRA L76; heroes decisions L71–72 |
| Hero weapon | 2.5k | 1.2k | 400 (dagger 1.2k / 600 / 250) | — | 1024 (512 for daggers) | heroes inventory L679–680 |
| Regular monster | 4–8k (e.g. boar 6–8k) | 2.5k | 1k | VAT crowd for NPCs only (HRA band D) | 1024 albedo, 512 ORM | MON L108, L314–320 |
| Elite | 8–12k | 4k | 1.5k | — | 2048 albedo, 1024 others | MON L319 |
| Boss | 18–25k | 8k | 3k | — | 2048 | MON L320 |
| Broadleaf tree | 4–6k | ≤ 1.6k | impostor (8 az × 4 el, 256 px frames, 2048 page) | impostor belts | 1024 shared atlas (2048 hero tree) | trees decision L148, L165; impostor-cards L24–25 |
| Conifer / bush / hero tree | 2.5–5k / 300–900 / ≤ 9k | ≤ 1.4k / 50 % / 50 % | impostor / cull / impostor | — | shared atlas | trees decision L165 |
| Prop (cart, barrel, crate) | 300–2k | 50 % | 20 %, or culled at 35–40 m when < 1 m | — | shared 1024 trim or atlas | froggy art plan L46 (LOD0, LOD1); open-world plan L105 (LOD2 20 %); prop audit L173, L231 (culling) |
| Landmark | ≤ 15k | 50 % | 20 % | cell HLOD | ≤ 3 MiB file (MMP) | MMP §6; open-world plan L105 |
| Terrain cell | ground ≤ 12k, rock ≤ 16k bluff / ≤ 10k chunk, decals ≤ 4k | far path (layer means) | 256 m macro HLOD ≤ 25k; 512 m proxy ≤ 8k | always resident | TER layer sets 1024 / 512 | TER L799–806; MMP §6 |

On phones, triangles should stay at least 4–20 px (Arm, Qualcomm; C-R-MOB §4.4). Flowers therefore drop their centres and become thin-instanced clumps (C-R-MOB §8.2), and every static mesh uses the pixel-equalised LOD rule of §3.3.

Decimation follows `docs/reviews/2026-10-01-triangle-optimization-research.md` L38: LOD1 is permissive at about 35–50 % with error ≤ 0.5 %, and LOD2 is permissive or sloppy at about 10–15 %. LOD0 must be checked against its budget after export, in triangles (monster combat decisions L136; MON L662).

### 6.2 Tripo high-detail models and the bakes that let low tiers keep the look

1. **Generate at twice LOD0.** The source has about 2× the LOD0 budget: heroes at a 12,000-face quad target give 21–26k triangles (heroes inventory L546). Set monster `face_limit` in triangles (MON L373, L404, L503). The Tripo mesh is kept as the **bake source** and never shipped.
2. **LOD0** is a UV-preserving collapse decimation of the source, with face, hands and silhouette edges protected (heroes inventory L624). It keeps the Tripo detail that reads at gameplay distance.
3. **Map set A (bake onto LOD0).** Normal (OpenGL +Y) from the source, AO at 128 samples, and curvature and cavity masks, in Cycles on the CPU at 2048 (heroes inventory L630–632; MON L282–284). Form AO also goes into `COLOR_0` or the albedo, because ORM AO hardly shows under one sun (blender official docs L104).
4. **Map set B (bake onto LOD1)**, for props and monsters only. LOD1 and LOD2 are decimated from LOD0 with the same UVs. Map set B is a second bake from the **high-poly source onto LOD1**, at 1K and 512.
   - Why: a tangent-space map baked onto LOD0 encodes LOD0's surface, so on LOD1 it shades wrongly where the decimation changed the normals.
   - Why it matters: on mobile-low, mobile-mid and desktop-low, LOD1 is the closest LOD for props and monsters (§3.3), often at 3 m in combat. Those tiers must get a bake made for LOD1, or "PC-like detail" fails exactly where the owner looks.
5. **Which set loads.** The tier's **top LOD** decides it. With top LOD0, set A serves LOD0–LOD2 (LOD2 samples a lower mip, as heroes inventory L669 allows). With top LOD1, set B serves LOD1–LOD2, and set A is never downloaded. One set is resident at a time, so memory stays at one set per asset.
6. **Impostors** come from LOD0 renders (impostor-cards L24–35), with normals at half resolution and no shadow casting (impostor-cards L93).
7. **Procedural surface rules** become bakes for phones and low tiers (P10 rule 9). The rock rules from MountainRIver are evaluated in Blender into map sets A and B; the runtime plugin runs only on High and above.

### 6.3 Textures: sizes and KTX2 formats per map type

Every map ships at **2K, 1K and 512** (4K only for the Epic list in §3.3), as KTX2 with a full mip pyramid and dimensions that are multiples of 4 (blender official docs L374, L378). Never JPEG before KTX2 (L137).

| Map type | Encoding | Settings | Transcode target (desktop / iOS / Android) | Why |
|---|---|---|---|---|
| Opaque base colour, emissive | ETC1S (BasisLZ) | Quality per asset. No zstd: it "cannot be used with ETC1S" (blender official docs L385) | BC7 (or BC1/BC3) / ETC2 / ETC2: Babylon's ETC1S order is ETC2 → ETC1 → BC7 → BC3/BC1 (recheck 1.2) | Smallest download for large, low-detail colour (CP §3.4; blender official docs L368) |
| Painted character, foliage and terrain albedo with gradients | UASTC + RDO + zstd | `--uastc-quality 2 --uastc-rdo-l 1.0 --zstd 18` (TER L682) | BC7 / ASTC 4×4 / ASTC 4×4 | ETC1S blocks painted gradients (MON L306) |
| Alpha-tested cards (grass, leaves, impostors) | UASTC | Baked coverage mips (GRS L339–341) | BC7 / ASTC / ASTC | Alpha edge quality |
| Normal | UASTC, no RDO | Tangent space +X +Y +Z; no `--normal-mode` for glTF (blender official docs L248, L389); export tangents | BC7 / ASTC / ASTC | ETC1S is blocky on normals (CP §3.4) |
| ORM and data packs (NRO, AH) | UASTC, quality 3, no RDO for NRO | Linear; never `--normalize` (TER L686–687) | BC7 / ASTC / ASTC | Packed channels |
| Splat, SDF and control maps | Lossless PNG or raw | Never block-compressed (TER L334) | RGBA8 | Compression corrupts weights |
| Water data (flow, masks) | Raw RGBA8 `.bin` | No mips (WAT L542) | RGBA8 | Data, not colour |

GAP-1 and GAP-2 (R-A12) are prerequisites on WebGPU. Without them every KTX2 file decodes to RGBA8: a 2048² map with mips is 21.3 MiB instead of 5.3 MiB (CP §3.1).

### 6.4 Budgets per 64 m cell and per character, per tier

**Cell representations.** Every cell ships C0–C2 (§1.3). Vegetation has its own per-view budgets (GRS, trees decision).

| Representation | Triangles (excluding vegetation) | Draws | Unique texture per cell | Used by (own cell / ring 1 / ring 2) |
|---|---|---|---|---|
| C0, LOD0 set | ≤ 120k (prop audit L403) | ≤ 40 | ≤ 4 MiB, excluding shared kits and terrain layers | High and above: own cell; Ultra: rings 0–1; Epic: rings 0–2 |
| C1, LOD1 set | ≤ 60k | ≤ 24 | ≤ 2 MiB | Medium: own cell; High: ring 1; Ultra: ring 2 |
| C2, cell merge of LOD2 + terrain (= MMP 64 m cell) | ≤ 40k | ≤ 16 | ≤ 1 MiB | Low: own cell; Medium and High: ring 2 |
| 256 m macro HLOD / 512 m proxy | ≤ 25k / ≤ 8k | ≤ 8 / ≤ 2 | ≤ 4 / ≤ 1.5 MiB file | every tier (MMP §6) |

Per-view totals are in §3.4: triangles, draws, texture MiB.

**Per character**, as drawn at the tier's top LOD:

| Character | Low | Medium | High | Ultra | Epic |
|---|---|---|---|---|---|
| Own hero | LOD0 12k, 1K maps (4 MiB) | LOD0, 2K (16 MiB: 3 maps × 2048² × 1 B × 4/3) | LOD0, 2K | LOD0, 2K | LOD0, 2K |
| Party and target player | LOD0, 1K | LOD0, 1K | LOD0, 2K | LOD0, 2K | LOD0, 2K |
| Other players (band A LOD0, band B LOD1) | 512; at most 4 at full detail | 1K; ≤ 6 | 1K; ≤ 12 | 2K; ≤ 20 | 2K; ≤ 30 |
| Regular monster | LOD1 2.5k, 512, set B (also when targeted) | LOD1, 1K, set B | LOD0 4–8k, 1K | LOD0, 1K | LOD0, 1K (2K if authored) |
| Boss | LOD1 8k, 1K, set B | LOD0 18–25k, 1K | LOD0, 2K | LOD0, 2K | LOD0, 2K |

Class texture ceilings apply on top of this table; on mobile-mid, for example, everything is clamped to 1K (iPhone 11 target doc §4.1).

The 512 / 1K / 2K variants of one map set are the same bake downsampled. Heroes ship set A only: they are always LOD0 inside band A, and their LOD1 and LOD2 are seen only beyond 15–35 m, where set A's error is invisible.

Bone counts follow HRA: ≤ 60 joints (L367), well inside the texture path (L335–336).

Draws and shadows per character:
- **Draws.** ≤ 3 per character on every tier: body and armour (≤ 2 materials, MON L551), plus the weapon GLB (HRA L76). The contact AO blob is one shared thin-instance draw for everyone (SKY L535).
- **Shadow casting.** LOD0 and LOD1 cast; LOD2 never does (MON L638). Within the class's monster-shadow distance (§3.4) a cast adds one more draw per cascade the character falls in.

### 6.5 Variant selection at runtime

- **Manifest.** Each asset publishes `lods[]` (URI, triangles, coverage threshold), `mapSets` ({A, B} × {2k, 1k, 512, 4k?}), `impostor` and `collider`. The city residency planner already takes per-LOD `residentBytes` (`city-residency.mjs`). Extend the same records rather than adding a second catalogue.
- **Choosing the LOD.** Static meshes multiply every coverage threshold by the class's `coverageScale` when the LOD levels are built (`useLODScreenCoverage = true`; CP §4.12). Characters use `lodDistanceScale` on their distance bands. Babylon has no global LOD bias, so a tier change rebuilds the levels at the next load.
- **Cross-fades.** LOD1 → impostor fades use `DitheredTileFadeMaterialPlugin` (recheck C14) in the colour pass.
- **Choosing textures.** The loader's `preprocessUrlAsync` (`glTFFileLoader.pure.d.ts:298`) rewrites `*_2k.ktx2` URIs to the tier's size and map set. One GLB therefore serves every tier. A texture setting change applies at the next zone load.
- **Fast start.** The spawn area loads LOD1 + 512 first; the tier's top LOD and texture size stream in after the first frame, never before it.
  - Uploads are staged on iOS: Safari can crash when many textures are created at once, so upload in batches of 3–4 (fast-load §2.6, roland, t/53242, 2024-09-06).
  - Variants are separate files per size, because the KTX2 loader cannot skip a top mip (fast-load §2.2).
  - Cells stream with eviction under the class texture budget (fast-load action 13).

---

## 7. Proposed changes for Codex root (not applied)

### 7.1 `graphics-quality.mjs`: diff sketch

```diff
--- a/apps/client/src/graphics-quality.mjs
+++ b/apps/client/src/graphics-quality.mjs
@@ header
- * Callers supply form factor explicitly; this module does not infer hardware
- * from user-agent strings.
+ * Callers supply a device class (from device-class.mjs) or, for legacy callers,
+ * a form factor. This module never reads navigator, user-agent strings or GPU
+ * names itself; classification and benchmarking live in device-class.mjs.
-export const GRAPHICS_PRESET_NAMES = Object.freeze(["low", "medium", "high", "ultra"]);
+export const GRAPHICS_PRESET_NAMES = Object.freeze(["low", "medium", "high", "ultra", "epic"]);
+export const DEVICE_CLASS_NAMES = Object.freeze([
+	"mobile-low", "mobile-mid", "mobile-high", "desktop-low", "desktop-mid", "desktop-high", "desktop-ultra",
+]);
-const STORAGE_VERSION = 1;
+const STORAGE_VERSION = 2; // v2 adds "epic" and `overrides`; v1 records are still read.
-const MOBILE_RESOLUTION_SCALES = Object.freeze({ low: 0.88, medium: 0.94, high: 0.94, ultra: 1 });
+const MOBILE_RESOLUTION_SCALES = Object.freeze({ low: 0.88, medium: 0.94, high: 0.94, ultra: 1, epic: 1 }); // legacy path
@@ presets (one shown; every preset gains the same fields)
 	low: Object.freeze({
 		label: "Low",
+		labelTh: "ต่ำ",
 		maxDpr: 1,
 		resolutionScale: 0.88,
 		targetFps: 30,
+		autoCeilingFps: 60, // auto-fps doc §4.3; 0 = the display refresh
+		renderScale: Object.freeze({ start: 0.88, min: 0.5, max: 1 }), // FSR1 linear scale; 1 = native
+		msaaSamples: 1, alphaToCoverage: false, ssaaScale: 1,
 		shadowMapSize: 512,
 		cascades: 1,
-		shadowDistance: 55,
+		shadowDistance: 40, // SKY §8.1: a fixed 40 m ortho frustum around the player
+		shadowFilter: "low",
 		glowEnabled: false,
+		glowRatio: 0, glowKernel: 0,
 		vegetationDensity: 0.45,
 		vegetationDistanceFactor: 0.5,
+		grassFarFraction: 0.40, grassBenders: 1,
 		weatherParticleBudget: 24,
 		waterDetail: 0.3,
+		subsystemTiers: Object.freeze({ terrain: 0, water: "low", sky: "low", grass: "low" }),
+		textureMaxSize: 512, anisotropy: 2,
+		lodDistanceScale: 0.6, detailDrawDistance: 150,
+		particleScale: 0.25, liveParticleCap: 300,
+		fullDetailPlayers: 4, fullDetailMonsters: 6, animatedCap: 20,
+		proceduralSurfaceDetail: false, canopyTranslucency: false,
+		contactShadows: false, ssao: false,
 		maxRenderPixels: 1_310_720,
 	}),
@@ the other presets: changed or new values only
 	medium: { …, labelTh: "ปานกลาง", targetFps: 30 /* desktop classes use fpsBase 60 */, autoCeilingFps: 60,
+		renderScale: { start: 1, min: 0.59, max: 1 }, msaaSamples: 1, glowRatio: 0.33, glowKernel: 24,
+		subsystemTiers: { terrain: 1, water: "medium", sky: "medium", grass: "medium" },
+		textureMaxSize: 1024, anisotropy: 4, lodDistanceScale: 0.8, detailDrawDistance: 180,
+		particleScale: 0.5, liveParticleCap: 600, fullDetailPlayers: 6, fullDetailMonsters: 8, animatedCap: 30, grassBenders: 2 },
 	high: { …, labelTh: "สูง", autoCeilingFps: 0,
+		renderScale: { start: 1, min: 0.67, max: 1 }, msaaSamples: 4, shadowFilter: "medium", glowRatio: 0.5, glowKernel: 32,
+		subsystemTiers: { terrain: 2, water: "high", sky: "high", grass: "high" },
+		textureMaxSize: 2048, anisotropy: 8, lodDistanceScale: 1, detailDrawDistance: 230,
+		particleScale: 1, liveParticleCap: 1200, fullDetailPlayers: 12, fullDetailMonsters: 16, animatedCap: 50, grassBenders: 4,
+		proceduralSurfaceDetail: true, canopyTranslucency: true },
 	ultra: { …, labelTh: "สูงมาก", autoCeilingFps: 0,
-		shadowMapSize: 4096,
+		shadowMapSize: 2048, // SKY R5 / inbox A14: 4096 × 4 ≈ 403 MB does not fit a 2 GB GPU
+		renderScale: { start: 1, min: 0.77, max: 1 }, msaaSamples: 4, alphaToCoverage: true, shadowFilter: "high",
+		subsystemTiers: { terrain: 2, water: "ultra", sky: "ultra", grass: "ultra" },
+		textureMaxSize: 2048, anisotropy: 8, lodDistanceScale: 1.25, detailDrawDistance: 280,
+		liveParticleCap: 2000, fullDetailPlayers: 20, fullDetailMonsters: 24, animatedCap: 64 },
+	epic: Object.freeze({
+		label: "Epic", labelTh: "สูงสุด",
+		maxDpr: 2, resolutionScale: 1, targetFps: 60, autoCeilingFps: 0,
+		renderScale: Object.freeze({ start: 1, min: 0.83, max: 1 }),
+		msaaSamples: 4, alphaToCoverage: true, ssaaScale: 1.25,
+		shadowMapSize: 4096, cascades: 4, shadowDistance: 250, shadowFilter: "high",
+		glowEnabled: true, glowRatio: 0.5, glowKernel: 32,
+		vegetationDensity: 1.25, vegetationDistanceFactor: 1.5, grassFarFraction: 0.6, grassBenders: 6,
+		weatherParticleBudget: 384, waterDetail: 1.5,
+		subsystemTiers: Object.freeze({ terrain: 2, water: "ultra", sky: "ultra", grass: "epic" }),
+		textureMaxSize: 4096, anisotropy: 16, lodDistanceScale: 1.5, detailDrawDistance: 360,
+		particleScale: 1, liveParticleCap: 3000, fullDetailPlayers: 30, fullDetailMonsters: 32, animatedCap: 100,
+		proceduralSurfaceDetail: true, canopyTranslucency: true,
+		contactShadows: false, ssao: false, // §4 gated experiments; the flags flip only after their A/B
+		maxRenderPixels: 12_000_000,
+	}),
@@ class policy replaces the MOBILE_* constants (the legacy path is kept for callers without a class)
+const DEVICE_CLASS_POLICY = Object.freeze({
+	"mobile-low":    { formFactor: "mobile",  auto: ["low", "low"],      defaultTier: "low",    manualMax: "medium",
+		maxDpr: 1,    maxRenderPixels: 1_000_000,  useFsr: false, renderScale: { start: 0.88, min: 0.75, max: 1 },
+		fpsBase: 30, autoCeilingFps: 30, contextAntialias: false, shadowMapSize: 512, cascades: 1, shadowDistanceMax: 30,
+		msaaSamples: 1, textureMaxSize: 512, anisotropy: 2, glowSamples: 1,
+		vegetationDensityScale: 0.72, vegetationDistanceScale: 0.85, subsystemMax: { terrain: 0, water: "low",    sky: "low"    },
+		liveParticleCap: 200,  fullDetailPlayers: 4,  fullDetailMonsters: 6,  animatedCap: 20 },
+	"mobile-mid":    { formFactor: "mobile",  auto: ["low", "medium"],   defaultTier: "medium", manualMax: "high",
+		maxDpr: 1.175, maxRenderPixels: 600_000, useFsr: false, renderScale: { start: 1, min: 0.77, max: 1 }, // DPR 1.175 → 0.9 (§1.3 item 13)
+		fpsBase: 30, autoCeilingFps: 60, contextAntialias: true, shadowMapSize: 1024, cascades: 2, shadowDistanceMax: 55,
+		msaaSamples: 4, textureMaxSize: 1024, anisotropy: 2, terrainAnisotropy: 4, glowSamples: 1,
+		vegetationDensityScale: 0.72, vegetationDistanceScale: 0.85, subsystemMax: { terrain: 1, water: "low",    sky: "phone-medium" },
+		liveParticleCap: 300,  fullDetailPlayers: 6,  fullDetailMonsters: 8,  animatedCap: 30 },
+	"mobile-high":   { formFactor: "mobile",  auto: ["medium", "high"],  defaultTier: "medium", manualMax: "ultra",
+		maxDpr: 1.5,  maxRenderPixels: 1_500_000, useFsr: false, renderScale: { start: 0.89, min: 0.67, max: 1 }, // DPR 1.33, adaptive 1.0–1.5
+		fpsBase: 30, fpsBaseWithHeadroom: 60, autoCeilingFps: 60, contextAntialias: true, shadowMapSize: 2048, cascades: 2, shadowDistanceMax: 85,
+		msaaSamples: 4, textureMaxSize: 2048, anisotropy: 4, glowSamples: 1,
+		vegetationDensityScale: 0.72, vegetationDistanceScale: 0.85, subsystemMax: { terrain: 1, water: "medium", sky: "phone-high" },
+		liveParticleCap: 600,  fullDetailPlayers: 10, fullDetailMonsters: 12, animatedCap: 40 },
+	"desktop-low":   { formFactor: "desktop", auto: ["low", "medium"],   defaultTier: "low",    manualMax: "high",
+		maxDpr: 1,    maxRenderPixels: 2_100_000,  useFsr: true,  renderScale: { start: 0.67, min: 0.5, max: 0.77 },
+		fpsBase: 60, autoCeilingFps: 60, contextAntialias: false, shadowMapSize: 1024, cascades: 2, msaaSamples: 4, textureMaxSize: 1024, anisotropy: 4,
+		subsystemMax: { terrain: 1, water: "medium", sky: "medium" }, liveParticleCap: 600, fullDetailPlayers: 6, fullDetailMonsters: 8, animatedCap: 30 },
+	"desktop-mid":   { formFactor: "desktop", auto: ["medium", "high"],  defaultTier: "high",   manualMax: "epic",
+		maxDpr: 1.25, maxRenderPixels: 3_700_000,  useFsr: true,  renderScale: { start: 1, min: 0.67, max: 1 },
+		fpsBase: 60, autoCeilingFps: 0 /* refresh */, contextAntialias: true, shadowMapSize: 2048, cascades: 4, msaaSamples: 4, textureMaxSize: 2048, anisotropy: 8,
+		subsystemMax: { terrain: 2, water: "high", sky: "ultra" }, liveParticleCap: 1200, fullDetailPlayers: 12, fullDetailMonsters: 16, animatedCap: 50 },
+	"desktop-high":  { formFactor: "desktop", auto: ["high", "ultra"],   defaultTier: "high",   manualMax: "epic",
+		maxDpr: 1.5,  maxRenderPixels: 8_300_000,  useFsr: true,  renderScale: { start: 1, min: 0.77, max: 1 },
+		fpsBase: 60, autoCeilingFps: 0, contextAntialias: true, shadowMapSize: 4096, cascades: 4, msaaSamples: 4, textureMaxSize: 4096, anisotropy: 16,
+		subsystemMax: { terrain: 2, water: "ultra", sky: "ultra" }, liveParticleCap: 2000, fullDetailPlayers: 20, fullDetailMonsters: 24, animatedCap: 64 },
+	"desktop-ultra": { formFactor: "desktop", auto: ["ultra", "epic"],   defaultTier: "ultra",  manualMax: "epic",
+		maxDpr: 2,    maxRenderPixels: 12_000_000, useFsr: true,  renderScale: { start: 1, min: 0.83, max: 1 },
+		fpsBase: 60, autoCeilingFps: 0, contextAntialias: true,
+		shadowMapSize: 4096, cascades: 4, msaaSamples: 4, textureMaxSize: 4096, anisotropy: 16,
+		subsystemMax: { terrain: 2, water: "ultra", sky: "ultra" }, liveParticleCap: 3000, fullDetailPlayers: 30, fullDetailMonsters: 32, animatedCap: 100 },
+});
@@ resolveGraphicsPreset
 export function resolveGraphicsPreset(preset, deviceContext = {}) {
 	assertPreference(preset);
 	const context = typeof deviceContext === "object" && deviceContext !== null ? deviceContext : {};
-	const formFactor = normalizeFormFactor(context.formFactor);
-	const recommendedPreset = recommendPreset(formFactor);
+	const deviceClass = normalizeDeviceClass(context.deviceClass); // null when absent
+	const formFactor = deviceClass ? DEVICE_CLASS_POLICY[deviceClass].formFactor : normalizeFormFactor(context.formFactor);
+	const recommendedPreset = recommendPreset({ deviceClass, formFactor,
+		benchmarkTier: context.benchmarkTier, autoTierCap: context.autoTierCap });
 	const selectedPreset = preset ?? recommendedPreset;
-	const spec = applyPlatformCeilings(GRAPHICS_PRESETS[selectedPreset], selectedPreset, formFactor);
+	const spec = deviceClass
+		? applyClassPolicy(GRAPHICS_PRESETS[selectedPreset], selectedPreset, deviceClass, context.overrides)
+		: applyPlatformCeilings(GRAPHICS_PRESETS[selectedPreset], selectedPreset, formFactor); // unchanged legacy path
+	// Frame-rate base and Auto ceiling for frame-rate-policy.mjs (auto-fps doc §2.4, §4.3): targetFps = the class fpsBase
+	// (mobile-high: fpsBaseWithHeadroom when XB1 reports higherCapOk); autoCeilingFps = min(preset, class), 0 = refresh.
+	// The policy paces through engine.customAnimationFrameRequester; engine.maxFPS stays unset.
+	// Static-mesh LOD: coverageScale = clamp(2_073_600 / the class's start 3D pixels, 0.36, 4), fixed at load (§3.3).
+	// Snapping to a refresh divisor is owned by the C-P0-FPS policy module (PENDING). "max" means the display refresh.
+	// Never 0: Babylon's maxFPS ≤ 0 stops rendering (abstractEngine.pure.js:411-413).
+	const frameRate = { targetFps: classBaseFps(deviceClass, spec, context.higherCapOk), autoCeilingFps: classAutoCeiling(deviceClass, spec) };
 	…
-	return Object.freeze({ ...spec, preset: selectedPreset, preference: preset, recommendedPreset, formFactor, … });
+	return Object.freeze({ ...spec, ...frameRate, deviceClass, preset: selectedPreset, preference: preset, recommendedPreset, formFactor, … });
 }
+
+/** Auto: the benchmark tier, clamped to the class range and any stored step-down cap. */
+function recommendPreset({ deviceClass, formFactor, benchmarkTier, autoTierCap }) {
+	if (!deviceClass) return formFactor === "desktop" ? "high" : "medium"; // legacy behaviour
+	const policy = DEVICE_CLASS_POLICY[deviceClass];
+	const ceiling = autoTierCap && rank(autoTierCap) < rank(policy.auto[1]) ? autoTierCap : policy.auto[1];
+	const wanted = isGraphicsPreset(benchmarkTier) ? benchmarkTier : policy.defaultTier;
+	return clampPreset(wanted, policy.auto[0], ceiling);
+}
+
+/** min() of preset and class ceilings. Memory ceilings stay hard under overrides on every class (§5.7).
+ *  When the class uses FSR, resolutionScale becomes 1 (the canvas stays at maxDpr) and renderScale
+ *  = { start: min(preset, class), min: max(preset, class), max: min(preset, class) }. */
+function applyClassPolicy(spec, preset, deviceClass, overrides) { … }
@@ readStoredPreference: keep v1 records (Auto or a preset) valid
-		if (typeof parsed !== "object" || parsed === null || parsed.version !== STORAGE_VERSION) return null;
+		if (typeof parsed !== "object" || parsed === null || (parsed.version !== 1 && parsed.version !== STORAGE_VERSION)) return null;
+		// v2: { version: 2, preference, overrides? } — overrides validated field by field; unknown keys dropped.
@@ new export for the Advanced rows (§5.8)
+export function setGraphicsOverrides(partial) { … } // persists `overrides`; emits the same aetherfield:graphics-preference-change event
```

Also:
- **`graphics-quality.d.mts`.** Add `GraphicsPreset | "epic"`, `DeviceClass`, the new spec fields, `GraphicsDeviceContext.deviceClass | benchmarkTier | higherCapOk | autoTierCap | overrides`, and `ResolvedGraphicsPreset.deviceClass | autoCeilingFps | coverageScale`. The refresh rate, the throttle state and the player's frame-rate choice live in `frame-rate-policy.mjs`.
- **Legacy path and Epic.** Add `epic: 1` to `MOBILE_RESOLUTION_SCALES` (`graphics-quality.mjs:25`). The legacy mobile test at `apps/client/tests/graphics-quality.test.mjs` L119 loops over every preset, and `MOBILE_RESOLUTION_SCALES["epic"]` would otherwise be `undefined`, giving `Math.min(1, undefined) = NaN`.
- **Tests.** Callers that pass a form factor without a class keep today's behaviour, with two deliberate expectation updates:
  - L35: the `maxDpr` list gains Epic's 2;
  - L147–156: Ultra's `shadowMapSize` becomes 2048 (SKY R5).

  New tests:
  - every class × preset stays under its pixel and memory ceilings;
  - Auto clamps to the class range;
  - `autoTierCap` is honoured;
  - v1 records read as v2;
  - "epic" is rejected by the mobile resolver unless chosen manually under `manualMax`.

### 7.2 Device-class detection module

| File | Kind | Contents |
|---|---|---|
| `apps/client/src/device-class.mjs` (+ `.d.mts`, `.test.mjs`) | Pure | `classify(signals)`: the §5.2 rules and the versioned GPU regex table; `scoreBenchmark(steps, deviceClass, refreshHz)`: the §5.3–5.4 pass rule; `fingerprint(signals)`; `CLASS_ENGINE_DEFAULTS` (renderer, `powerPreference`). No DOM, no Babylon |
| `apps/client/src/device-profile-store.mjs` (+ tests) | Pure + storage | Read and write `aetherfield_device_profile_v1`; invalidation (§5.5); session fallback; `subscribeDeviceProfile` |
| `apps/client/src/device-probe.ts` | Browser | Collects signals before engine creation: Client Hints, screen, `deviceMemory`, cores, a probe `requestAdapter()`, and the WebGL renderer from a throwaway 1 × 1 context; refresh-rate sampling during the loading screen |
| `apps/client/src/device-benchmark.ts` | Babylon | XB1 (§5.3) on the real engine and canvas; returns step p75 values; never throws (returns "inconclusive") |
| Fixture tests | Data | Real renderer strings (ANGLE NVIDIA RTX 5060 / 4060 / 3060 / GTX 1050 / Intel Iris Xe / UHD 620, Adreno 740 / 644 / 610, Mali-G57 / G715, "Apple GPU") → expected class |

**Boot order in `main.ts` / `scene.ts`:**
1. `content` phase: read the device profile.
2. `renderer` phase:
   - `device-probe` (≤ 50 ms);
   - `createRenderer(canvas, { renderer, powerPreference, antialias })`, where the profile or class picks WebGL2 or WebGPU and the context anti-aliasing (§3.1), and the fallback order becomes "chosen, then the other";
   - XB1 if needed;
   - `resolveGraphicsPreset(pref, { deviceClass, benchmarkTier, refreshHz, … })`.
3. `codecs` phase: KTX2 workers start.

**Call sites to replace.** The four formFactor checks (`scene.ts` `resolveQuality`, the `environment.ts` setup, `settings.ts:165`, `ui/panel-data.ts:101`) all read `getDeviceProfile()`.

**Frame pacing** goes through `frame-rate-policy.mjs` (`createPacedFrameRequester` on `engine.customAnimationFrameRequester`; auto-fps doc §4.1), fed with `resolved.targetFps` and `resolved.autoCeilingFps`. `engine.maxFPS` stays unset.

### 7.3 Settings UI for the UI thread (job U-GFX)

- The rows, labels and toasts are in §5.8. The current `settings.ts` `renderEnvironmentControls` and `ui/panel-data.ts` `settingsPanelData` already render a preset select plus a summary. Extend them; do not fork them.
- The select gets Epic only when `deviceClass` is desktop-*. The summary line shows the class name, the recommended tier, the cap with the detected Hz, and the renderer.
- Advanced rows write `overrides` through a new `setGraphicsOverrides(partial)` in `graphics-quality.mjs`, which emits the same `aetherfield:graphics-preference-change` event.
- Thai copy goes into the existing `THAI ? … : …` pattern. Every value the summary shows comes from `resolveGraphicsPreset`; the UI never computes tiers itself.

---

## 8. Test plan

### 8.1 Devices

| Class | Device | Source | Status |
|---|---|---|---|
| desktop-mid | GTX 1050 2 GB workstation, 1080p | Dev machine (current harness target) | Available. GPU sessions are queued behind the other agents' lock (`gpu-measure.lock`) |
| mobile-mid | iPhone 11 | Owner (job O-IPH; task graph: "เจ้าของ: เทสบน iPhone 11"). Tests T0–T16 are in the iPhone 11 target doc §8. No cloud service offers an iPhone 11 on iOS 26/27 (same doc, §1) | Available on the owner's schedule |
| mobile-high | iPhone 16 Pro Max (or 15 Pro) | Owner to confirm whether one is available. Otherwise a cloud session: BrowserStack Live runs iOS 26/27 on the iPhone 14 and newer (iPhone 11 target doc §1) | **Owner decision** |
| desktop-ultra | RTX 5060 PC | Owner to confirm. Otherwise a friend's PC or a cloud GPU desktop (results indicative only) | **Owner decision** |
| desktop-high | RTX 3060 or 4060 | Owner or community playtester | Open |
| desktop-low | Intel Iris Xe or UHD laptop | Owner or playtester | Open |
| mobile-low | iPhone X (the owner's D-01 device; iOS 16, WebGL2 only) and a 4 GB Android with Mali-G57 or Adreno 610 (D-01: the owner has a qualifying Android and will give the model) | Owner; otherwise a cloud real device or a playtester | Owner to confirm both |
| Android mobile-mid / high | Snapdragon 7-series, 8 Gen 2+ | Cloud real devices | Open |

**Cloud real-device services:** BrowserStack Live, LambdaTest Real Devices, AWS Device Farm (remote access) and Sauce Labs. They are paid beyond trials, so the "0 THB of paid services until P3" rule (MMP §1) means each needs owner approval.
- They stream the screen through the device's video encoder, which adds GPU and thermal load. Their numbers are indicative; owned devices decide.
- Before booking, check that the service exposes Safari 26/27 with WebGPU and allows a 20-minute session (needed for the thermal gate).

### 8.2 What to measure per class

For each class, at the expected Auto tier and one tier below it, on both renderers:

1. **Frame time.** The three capture scenes (solo walk, party of 5 fighting, dense effects; MP §1), plus the four locked views at noon and at night: p50, p95 and p99, with GPU ms where a timer exists (`render-diagnostics`, R-PERF overlay).
2. **Load.** Draw calls, active meshes, visible triangles, texture MiB, total GPU MiB (where measurable), JS heap, and process memory (Safari Web Inspector timeline on iOS). Texture and buffer MiB use the engine-side estimate of fast-load step 0: Σ textures × format bytes, plus vertex and index buffers. The same step gives per-phase load times and peak memory.
3. **Sustained.** A 20-minute soak on phones: p95 drift, controller scale over time, thermal state (when the device reports it), battery % used, tab kills and context losses (O-IPH gate).
4. **XB1 itself.** 10 cold runs per device: run time, per-step p75, the spread across runs, and the chosen tier.
5. **Auto correctness.** The tier Auto picks against the tier that actually holds the gate in item 1.
6. **Renderer A/B** (§8.3).
7. **Ultra and Epic extras.** Each extra's gate from §4, on desktop-high and desktop-ultra.

### 8.3 Renderer A/B rule

A class flips its Auto renderer to WebGPU only when all of these hold:
- R-A12 (GAP-1 + GAP-2) has shipped;
- on that class's reference device, WebGPU's p95 is within 5 % of WebGL2's (or better) in all three capture scenes, its texture memory is no more than 10 % above WebGL2's, and it has no device loss in a 20-minute soak. This is the iPhone 11 target doc's rule (§4.1), applied to every class. Parity is enough, because WebKit says WebGPU "maps better to Metal" than WebGL's translation layer (same doc), and WebGPU brings GPU timing where `timestamp-query` exists;
- there are no correctness regressions in the locked-view captures;
- there are no CDN shader fetches (recheck N1).

Otherwise WebGL2 stays the class default. The result is recorded in `CLASS_ENGINE_DEFAULTS` with its numbers. The 400-tree number (WebGL2 0.82 ms vs WebGPU 3.23 ms) must be re-run with its device and resolution recorded; impostor-cards does not record them.

### 8.4 Pass / fail

| Class | Must pass at the expected Auto tier (§3) | Fails if |
|---|---|---|
| mobile-low | p95 ≤ 33.3 ms in all three scenes at Low; 20 min with no tab kill | Any scene above 33.3 ms after the controller reaches its floor; a tab kill; telegraphs or HP unreadable |
| mobile-mid (iPhone 11) | The O-IPH gate (iPhone 11 target doc §8.4): T1, plus T2 if WebGPU is the candidate; T3 (p95 ≤ 33.3 ms in every minute from 15 to 20, with the scale at or above the 2.0× floor); T4 and T5; no reload in 20 minutes. Also terrain Δ ≤ +1.5 ms (TER L793) and grass ≤ 2.5 ms (GRS L876), read from T13 | Any of these; or the side-by-side look review fails against desktop High at the 4 locked views (the "PC-like detail" gate) |
| mobile-high (16 Pro Max) | At High: p95 ≤ 16.7 ms in the solo walk when Auto chose 60 (≤ 33.3 ms when it chose 30); ≤ 33.3 ms in the dense-effects scene in minutes 15–20 | Above that; a tab kill; whole-page memory above 1.0 GiB steady |
| desktop-low | p95 ≤ 16.7 ms at Low, 1080p, FSR 1.5 | Above that at the scale floor |
| desktop-mid (GTX 1050) | p95 ≤ 16.7 ms at High, 1080p (MP §1); sky + light + post ≤ 5 ms (SKY L672) | Above that |
| desktop-high | p95 ≤ 16.7 ms at Ultra, 1440p | Above that |
| desktop-ultra (RTX 5060) | p95 ≤ 16.7 ms at Epic, 1440p, with every adopted extra; p95 ≤ 8.3 ms at Ultra with a 120 cap on a 120 Hz+ display | Above that |
| XB1, every class | Runs ≤ 3.0 s; picks the same tier in ≥ 9 of 10 cold runs; never picks a tier that fails its frame-time gate on that device | Otherwise: recalibrate k or the step loads |
| Re-evaluation, every class | Forced overload (`?stress=…` dev flag) produces resolution, then cap, then the toast, in that order, with ≤ 1 tier change per session | Wrong order; oscillation; a change mid-fight |

### 8.5 Unit tests (no GPU needed)

- `device-class.test.mjs`: the fixture strings → class; the deviceMemory and core caps; iPad detection; software GPU.
- Scoring: synthetic step costs → tier for every class, the throttled and inconclusive paths, and `higherCapOk`.
- `device-profile-store.test.mjs`: fingerprint invalidation, the 30-day expiry, and blocked storage.
- `graphics-quality.test.mjs`: the new class and Epic cases (§7.1).

---

## 9. Risks (ranked)

1. **The benchmark persists a wrong tier.** Noise, a hot phone, Low Power Mode or background tabs can all cause it. Mitigations:
   - p75 statistics, with the first 4 frames of each step discarded;
   - the throttle and inconclusive paths never persist;
   - a re-run on disagreement;
   - promotion and step-down through sustained data (§5.6);
   - the ≥ 9/10 repeatability gate.
2. **Safari reveals no GPU model** (§2.2). The two named phones are still unambiguous by screen: the iPhone 11 is 414 × 896 @2 with WebGPU, and the 16 Pro Max is 440 × 956 @3. A16–A18 phones share 393 × 852 and 430 × 932 and need XB1; if it is inconclusive, they start as mobile-mid at Medium, which is the safe side, and promotion recovers. Display Zoom makes a phone look smaller than it is.
3. **WebGL2 as the provisional default inverts today's order.** It could expose WebGL2-only bugs, for example on Safari's ANGLE-on-Metal path. Mitigation: the §8.3 A/B per class, the `?renderer=` override and the Renderer setting.
4. **Memory on 4 GB phones (iPhone 11).** Before R-A12, the WebGPU path holds the city's textures as RGBA at 432 MiB (fast-load §1.6); hence the WebGL2 rule. Mitigations: hard ceilings for textures, shadows and pixels; the 20-minute no-tab-kill gate; context-loss rebuild paths (CP §3.6).
5. **Content cost.** Two map sets × three sizes × LOD0–2 × impostors per asset multiply bake and export time. Blender is single-process (MP §5). Mitigation: one automated `bake_asset` command per asset (open-world plan L156), and set B only for assets whose top LOD is LOD1 on some class (props and monsters).
6. **Epic widens the test matrix.** Mitigation: Epic is captured only on desktop-ultra, and its extras are default-off until their gates pass.
7. **Safari's 60 fps rAF preference.** iPhone 16 Pro Max owners cannot get 120 fps in Safari unless they change a feature flag themselves (§2.3). The plan does not promise it.
8. **Frame pacing.** Babylon's `maxFPS` accumulator paces unevenly, and `maxFPS = 0` stops rendering. The fix has landed as `apps/client/src/frame-rate-policy.mjs` (39/39 tests, simulation only, not yet run on a device). Root still has to integrate it (R-LOOP; auto-fps doc §4.1).
9. **Policy change.** GPU-string priors reverse a stated module rule (§5.1). Root must accept it, or every non-Apple device falls back to benchmark-only.
10. **Spec drift.** TER and WAT still say "phones = Low". Their owners should add the class rows of §1.3 so the next reader does not re-open the conflict.
11. **The two phone research docs disagree** on upscaling and shadow distance (§1.3 items 10 and 13). O-IPH T13 settles both on the device.

---

## 10. New jobs for the task graph (proposed)

| ID | Job | Owner | Depends on | Gate |
|---|---|---|---|---|
| R-TIER | `graphics-quality.mjs` v2: Epic, class policy, new fields, overrides, d.mts and tests (§7.1) | codex-root | C-P0-FSR, C-P0-FPS | Old tests pass with the two §7.1 expectation updates, and the new tests pass. No behaviour change for callers without a class, except SKY R5 (Ultra shadows at 2048) |
| R-DETECT | `device-class.mjs`, `device-profile-store.mjs`, `device-probe.ts`, renderer order and `powerPreference` (§7.2) | codex-root | R-TIER | Fixture tests; the 4 call sites unified |
| C-XB1 | XB1 benchmark implementation and calibration of k on the GTX 1050 and the iPhone 11 | claude | R-DETECT, C-P0-CAP | §8.4 XB1 row |
| U-GFX | Settings UI rows, Thai copy, toasts (§5.8) | codex-ui | R-TIER, U-FPS | Persists; Auto summary correct on every class |
| C-VAR | Asset variant manifest, map sets A and B, `preprocessUrlAsync` texture tiering (§6) | claude | C-P0-EXP | One GLB serves every tier; set B on props and monsters |
| O-DEV | Owner confirms iPhone 16 Pro Max and RTX 5060 access (or approves a cloud session) | owner | — | Devices named |
| C-AB | Renderer A/B per class (§8.3) | claude | R-A12, C-XB1 | `CLASS_ENGINE_DEFAULTS` updated with numbers |
| C-SPECS | Add the class rows of §1.3 and §3 to TER, WAT, GRS and SKY, so that "phones = Low" stops conflicting with "phones = Medium" | claude | — | Each spec names its mobile-low, mobile-mid and mobile-high row |

---

## 11. Inputs written in parallel: four integrated, two PENDING

Four of the six inputs landed while this plan was being written, and all four are integrated:
- `2026-10-02-fastload-research.md` (16:24): §1.3 items 7 and 11, §2.4, §3.4 memory, §5.3, §6.5 and §8.2;
- `2026-10-02-iphone11-safari-target.md` (16:36): the mobile-mid column of §3, §1.3 items 10 and 11, §2, §5.3, §5.6, §8.1, §8.3 and §8.4;
- `2026-10-02-auto-fps-frame-pacing.md` (16:40; module and tests in `apps/client/src/frame-rate-policy.*`): §1.2, §1.3 items 4 and 12, the §3.1 frame-cap row and rules, §4, §5.3, §5.6, §5.8, §7.1, §7.2 and §9;
- `2026-10-02-mobile-pc-detail-research.md` (16:49): §1.3 items 10, 11, 13 and 14, the phone columns of §3.1–§3.4, §5.6 stage 1 and §6.1.

At 16:57 on 2026-10-02 the other two did not exist in `docs/reviews/`. This plan was not built on drafts from other agents' working folders, because those are not reviewed documents. Each row names the values the doc replaces or confirms when it lands:

| Doc | Task-graph job | Values in this plan it will replace or confirm |
|---|---|---|
| `2026-10-02-render-scaling-fsr1.md` | C-P0-FSR | FSR start scales and adaptive ranges per class (§3.1). FSR on phones against canvas scaling (§1.3 item 13). FSR pass cost, which decides FSR on mobile-low. Sharpness. MSAA samples on the reduced target. The per-tier table including the iPhone 11 (its gate) |
| ~~`2026-10-02-auto-fps-frame-pacing.md`~~ **integrated** | C-P0-FPS → R-LOOP → U-FPS | Cap snapping to refresh divisors (§3.1, §5.6 stage 2). The refresh-rate measurement. Low Power Mode at 30 Hz. The limiter that replaces bare `engine.maxFPS`. The Auto / 30 / 60 / 90 / 120 / Max options |
| ~~`2026-10-02-mobile-pc-detail-research.md`~~ **integrated** | C-R-MOB | The technique list behind "PC-like on iPhone 11": map set B (§6.2), mobile terrain tier 1 against 0 (§3.3), canopy cookies against proxies |
| ~~`2026-10-02-iphone11-safari-target.md`~~ **integrated** | C-R-IOS → R-PERF → O-IPH | The verified iPhone 11 profile: Safari memory behaviour, WebGPU on iOS 26/27, rAF behaviour. The mobile-mid ceilings (§3, §7.1). The owner's test steps (§8) |
| ~~`2026-10-02-fastload-research.md`~~ **integrated** | — | Variant streaming order (§6.5 "fast start"). Whether XB1 may overlap downloads (§5.3). The first-download budget against map sets |
| `2026-10-02-env-perf-quickwins.md` | C-P0-ENV | Opt-in glow (`env-glow` cost per tier, §3.2). Cloud casters removed from the shadow map. Freezing static meshes. These change the shadow and glow costs that XB1's steps model |
