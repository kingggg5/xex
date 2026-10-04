# Hero skills and VFX design: 6 heroes × (6 skills + basic attack)

Date: 2026-10-02 · Author: Claude (lead combat and VFX design) · For: the owner, the VFX lane (Codex, inbox B12/B13), Codex root (A31), animation (Claude), froggy, the UI thread (C8) · Status: **DESIGN DRAFT**. Every number is proposed and tunable; the server stays authoritative. Planning only: no code, UI automation or messages.

Companion files (generated from the same data, so they agree with this doc):
- data stub `planning/assets/hero-skills.json` (schema `xexoria.hero-skills/1`) for Codex A31 and the VFX lane;
- froggy key-frame drafts in `planning/assets/froggy-drafts/skills/`, one per hero, witch first.

> **สรุปภาษาไทยสำหรับเจ้าของ**
> 1. ออกแบบครบ 42 ท่า: ฮีโร่ 6 ตัว × (สกิล 6 + ตีปกติ 1) ทุกท่ามีชื่อไทย/อังกฤษ เวลาเป็น ms เฟรมปล่อยท่า (30 fps) คูลดาวน์ ค่า SP สถานะ คอมโบ telegraph และ VFX 5 ชั้นตาม Look v2 พร้อมชื่อเสียง SFX
> 2. บทบาท: 01 ออร์ค = แทงก์, 02 แม่มด = คุมฝูง + เวทวงกว้าง, 03 หมาป่า = ยิงไกล, 04 วัว = ฮีลเลอร์, 05 โจร = DPS ประชิด, 06 ช่างกล = ยูทิลิตี้ (ป้อมยิง บ่อจาระบี เสาซ่อมเกราะ) แต่ละตัวมีชุดสีและรูปทรงของตัวเอง ไม่ซ้ำกัน
> 3. คอมโบปาร์ตี้ 8 แบบ (สถานะจากฮีโร่ 2 ตัวรวมกันเกิดปฏิกิริยา) เช่น เปียก + ประจุไฟฟ้า = "แส้อัสนีสายฝน" ตามตัวอย่างของคุณ และแสงตะวัน + เงา = "ราหูอมตะวัน" ปาร์ตี้ 4 คนแบบไหนก็มีคอมโบให้ใช้ 2-4 แบบ และฮีโร่ใหม่ทุกตัวที่ออกจะเพิ่มคอมโบใหม่ทันที (แม่มด + ออร์คที่ออกก่อนคอมโบกันได้ตั้งแต่วันแรก)
> 4. แม่มดใช้ตัวอย่างเดิม 3 ท่า (Nova, Gale, Rift ปรับแกนและสีให้เป็นผลึกน้ำแข็ง จันทร์เสี้ยว และหลุมดารา) + ท่าใหม่ 3 ท่าที่ต่อยอดจากงาน lance / aegis / orrery ที่มีไฟล์ Blender อยู่แล้ว ส่วนแบบดาบและฝ่ามือของตัวอย่างเดิมนำไปใช้กับออร์คและนักบวชวัว
> 5. ชุด VFX กลาง: ของเดิม 21 ชิ้น + ของใหม่ 28 ชิ้น (mesh 12, decal/sigil 8, flipbook/sprite 6, atlas 2) ใช้ซ้ำข้ามฮีโร่ด้วยการเปลี่ยนแถวสี จึงคุม draw call ไม่เกิน 10 ได้
> 6. อาวุธ: Tripo 3 ชิ้น (ดาบ ค้อนประแจ มีด ประมาณ 405 เครดิต) และ Blender 3 ชิ้น (คทาคริสตัล ธนู คทาวงตะวัน ไม่ใช้เครดิต)
> 7. ส่งต่อได้ทันที: ร่างคำสั่ง froggy ภาพ key-frame 8 เฟรมต่อสกิล ไฟล์ละฮีโร่ (แม่มดก่อน) และไฟล์ข้อมูล `hero-skills.json` ให้ Codex นำเข้า
> 8. รอคุณตัดสินใจ: ชื่อสกิล ค่า SP/คูลดาวน์ คอมโบใน PvP และขนาดเอฟเฟกต์ของสกิลเป้าหมายเดี่ยว 6 ท่าที่ตั้งไว้ 10-14% ของจอ (ต่ำกว่าเกณฑ์ 15%) เพื่อไม่ให้จอรกเวลาเล่นปาร์ตี้

## Contents

- 0. Scope, sources and what this replaces
- 1. Rules every skill follows
- 2. Statuses and the 8 party combos
- 3. The three existing samples, mapped onto heroes
- 4. Heroes and their skills (production order)
- 5. Shared VFX kit
- 6. Weapons
- 7. Animation needs per hero
- 8. Production order
- 9. Hand-offs: froggy drafts and the data stub
- 10. Owner decisions
- 11. Self-review against the brief

## 0. Scope, sources and what this replaces

**Inputs read:** heroes decisions (classes; item 8: 6 skills + basic, clip list), heroes inventory and plan (looks, palettes, weapons, budgets), heroes rig and animation (clip ids, events, stance sets, UAL inspection), monster combat decisions (crit = punish window, miss rule, telegraph shapes, hit feedback), combo input window table v1, the owner's deep review §4.2-4.3 and §8 P1-05 (principles only), VFX quality bar §2 and §4 (Look v2), VFX sample set v1 and the quality hand-off, the reference-gauntlet loop, the claude-to-codex inbox (A8, A31, B3, B10, B12, B13, C8), `content/source/abilities.json`, the owner's three VFX sheets, all six hero front concepts, and the hero 02 mage VFX prior art (lance, aegis, orrery).

**What is fixed and what is proposed:**
- Fixed by earlier decisions and reused unchanged: the basic attack contract (25 damage, 100 / 60 / 200 ms, 400 ms, 400-650 ms links) and `arc_slash` (45, 3 targets, 4 m, 120°, 250 / 100 / 350 ms, 5 s) for hero 01; the `xs_bladeward_nova`, `xs_gale_palm` and `xs_void_rift` timelines; the telegraph semantics in B3; the tier budgets; the 2-light pool.
- Proposed here: everything else (36 skills, numbers, statuses, reactions, kit v2). The server owns damage, movement, cast success and reaction resolution; clip events only time the presentation, and damage FX still wait for the confirmed hit.
- Not done here: no code, no art, no clips. Names are placeholders until the owner names them.

**Originality.** Every skill, status, reaction and glyph name is original. Names that collide with known games were changed during design (for example the void rift is called Starless Hollow in game; the wind-spread and freeze-shatter patterns were avoided). Rahu's Bite draws on Thai folk astronomy, not on any game.

## 1. Rules every skill follows

### 1.1 Timing model

- **Phases:** wind-up (anticipation; the telegraph is visible) → active (the hit or release window) → recovery. All in ms.
- **Release frame** = the frame index at 30 fps where the hit or release happens: `round(windup_ms × 0.03)`. New skills put their release on the 33.3 ms grid (100, 133, 167, 200, 233, 267, 300, 333, 400, 467, 600, 667, 800, 900 ms). The legacy 250 ms `arc_slash` release is 7.5 frames: its event stays at 250 ms and the contact pose is authored on f8.
- **Links:** basics chain I → II within the existing 400-650 ms window (two clips, alternating). Any skill may follow a basic 400-750 ms after the accepted basic, as Basic → Arc does today, and must still pass its own cooldown. Dodge interrupts presentation; it adds no invulnerability.
- **Zones and summons** keep running after the hero's recovery (Hollow, Orrery, Rain, Sanctum, Sentry, Anvil, Hammerfall); the hero can act again when the clip ends.
- **Authority:** clip events (`hit`, `release`) time VFX, SFX and hit-stop; damage, statuses and reactions come from the server's confirmed events only. Cancelled, rejected or stale casts remove their pending effects (combo table v1).
- **Hit feedback (B3):** flash 40 + 80 ms; hit-stop 50 / 70 / 85 / 110 ms by strength (own hits only); knockback 0.12-0.35 m cosmetic unless the skill lists a gameplay knockback; crit shake +0.42 trauma at most once per 250 ms.
- **Heavy hits** (flag `heavy` in the blocks and the JSON) use the 85 / 110 ms hit-stop tiers and stagger non-boss targets. Only the offensive ultimates and Ironfall Cleave are also unguardable, and only those draw the HEAVY telegraph.
- **Damage type and element:** every skill carries a damage type (physical against DEF, magical against MDEF) and an element tag for future resistances. Element tags are separate from status tags, as the deep review §4.3 advises; reactions only read statuses.

### 1.2 Telegraph language (shape first, colour second)

The ring band carries the response; hero tint appears only in fills and particles (combat UI spec §6.4). Teeth always mean danger, dashes always mean benefit, a single smooth line is a normal hostile area. Every kind reads in greyscale and in low-effects mode.

| Kind | Meaning | Shape (non-colour cue) | Colours |
|---|---|---|---|
| `AREA_CIRCLE` | normal hostile area | single smooth ring; radial fill grows from the centre over the wind-up | core #FFF3C4 / band #FFBA4B / rim #080C12 at 95 % / fill = hero tint at 22-28 % |
| `AREA_FAN` | normal hostile cone | single smooth wedge outline; fill grows from the apex | as AREA_CIRCLE |
| `AREA_LANE` | normal hostile line, dash or skillshot | rectangle outline with chevrons moving 4 m/s toward the far end | as AREA_CIRCLE |
| `HEAVY_CIRCLE` | heavy: cannot be guarded (ultimates, guard-breakers) | double ring with 8 inward teeth; diagonal hatch fill instead of a smooth fill | core #FFF0E8 / band #FF4F3A (colour-blind mode #CC79A7) / rim #080C12 |
| `HEAVY_LANE` | heavy line | double toothed outline with hatch fill; may end in a HEAVY ring | as HEAVY_CIRCLE |
| `SAFE_CIRCLE` | ally benefit zone (heal, ward, buff): come in | dashed ring with an inward glow; never teeth | #DFFFF0 dashes; fill = hero tint at 15 % |
| `SAFE_CIRCLE_ULT` | ally ultimate zone | double dashed ring with an inward glow; never teeth | as SAFE_CIRCLE |
| `SAFE_BRACKET` | single ally target | 4 dashed corner brackets at the ally's feet | #DFFFF0 |
| `TARGET_BRACKET` | single hostile target | 4 solid corner brackets at the enemy's feet | AREA band and rim |
| `CAST_RING` | deploy / channel source | thin ring at the spot (r = body radius + 0.3 m), rotating 20°/s; static under reduce motion | hero tint at 40 % |
| `NONE_BASIC` | basic attack | no area telegraph; the current-target bracket only | - |

- **Who sees what:** your own skills: full telegraph. Party members' skills: full outline and fill at 50 %, so partners can line up combos. Other players: outline only at 60 % when "dim other players' effects" is on (B10). Telegraphs are never hidden, in any tier.
- The ring radius equals the gameplay radius within 2 %. Pulse ≤ 4 Hz, steady under reduce motion. Telegraph meshes are excluded from glow and draw above every effect layer.
- HEAVY is used by offensive ultimates and the one guard-breaker (Ironfall Cleave). The healer's ultimate uses the double dashed SAFE ring instead, because teeth would tell allies to run away.

### 1.3 Look v2 targets and the coverage calculator

- **Bigger:** peak coverage 15-35 % for heroic skills and 35-50 % for ultimates at the 13 m camera; a 120-250 ms hold at peak; the impact radius reads at 30 m. **Measure coverage** as the share of frame pixels whose colour differs from the effect-off frame by ΔE00 > 5, light spill included.
- **Calculator for designers:** the camera sits about 22° above the horizon with a 58° vertical FOV, so at the hero (≈ 11.4 m deep) the view plane is about 12.8 × 22.7 m ≈ 290 m², and 1 % ≈ 2.9 m². A ground disc of radius r projects to only ≈ 1.19 r² m² (it is squashed to 0.38 of its depth): a 4 m ring alone is ≈ 7 %. A vertical element w × h projects at ≈ w × h. So Look v2 size must come from vertical masses (blades, crystals, pillars, funnels, walls, clouds) and from the coloured light on the ground. That is why every skill pairs its ground layer with a vertical one.
- **More colourful:** every skill has a 2-3 hue palette (core, body, complementary accent), saturated mid-tones with value-graded edges, a coloured pooled light on heroic skills, and a peak-frame colourfulness M ≥ 45 (Hasler-Süsstrunk) against the background frame.
- **More detail:** at least 5 layers per skill: anticipation, mesh core, secondaries, ground layer, after-effect (0.5-1.5 s). Light and Epic-only distortion come on top.
- **Deliberate exceptions (owner decision D4):** basics stay at 3-4 % because four players spam them; 6 single-target or deploy skills sit at 10-14 % so party fights do not bury telegraphs: `h02_moonveil_ward` 12 %, `h05_adders_kiss` 10 %, `h05_fangfall` 14 %, `h06_cog_sentry` 12 %, `h04_dawn_mend` 12 %, `h03_amberwatch_arrow` 12 %.

### 1.4 Readability at the peak frame

1. Vertical masses stand on the perimeter of an area (blades at 2.9-3.5 m, shields on the ring, orrery rings 4-6 m up); centres stay clear where characters stand.
2. Additive bodies over characters stay at alpha ≤ 0.6; alpha-blended darkness (abyss, smoke, oil, shadow) stays ≤ 0.5 and is value-lifted to sRGB ≥ 40 (L* ≥ 25) under characters. No opaque mesh covers a character for more than 200 ms (only the Hammerfall head is opaque, and only while it falls onto the HEAVY ring).
3. Ground layers render under characters (decal stack with depth fade); the pooled light rims characters in the effect colour, which keeps dark silhouettes separate.
4. No white clipping: cores are near-white tints (for example `#F4FBFF`), emissive is capped, and the glow never plateaus. HP bars, damage numbers and nameplates stay readable through the peak.
5. Other players' effects can be dimmed (B10): party secondaries ×0.7, non-party ×0.4 with no light; telegraphs, party members and plates are never hidden.

### 1.5 Tiers, budgets and how the kit stays under them

| Tier | Draws | Particles | CPU p95 | Rule in this design |
|---|---|---|---|---|
| epic | ≤ 16 | ≤ 400 CPU or ≤ 2,000 GPU | ≤ 5 ms | every layer, including layers marked epic (distortion, extra GPU secondaries ×2) |
| high | ≤ 10 | ≤ 250 CPU or ≤ 1,000 GPU | ≤ 5 ms | every layer except epic ones; 1 pooled light per effect (2 in the pool) |
| medium | ≤ 8 | ≤ 120 | ≤ 3 ms | same shapes and palette; drops layers marked high; scales secondaries by medium_scale (default 0.5); ribbons ≤ 2; no distortion; lights only on ultimates |
| low | ≤ 5 | ≤ 60 | ≤ 2 ms | only layers marked low (core shape + ground layer) plus the telegraph; no light |

Budget classes per skill: **basic**: High ≤ 4 draws, ≤ 40 particles, no light (basics are frequent and overlap in a party of 4); **heroic**: the bar per tier (High ≤ 10 draws, ≤ 250 particles, ≤ 5 ms CPU p95); **ultimate**: the bar per tier; Epic may add distortion and GPU secondaries ×2.

Every layer below carries a minimum tier (all tiers, Medium+, High+ or Epic only), and secondaries carry a Medium scale. The JSON stores them as `min_tier` and `medium_scale`, so the pool can drop layers by data alone (B13). Merge rules that keep a skill at ≤ 10 draws on High:
- One thin-instanced draw per mesh type per effect (12 crystals = 1 draw).
- One particle system per blend mode per effect for vfx_motes; secondary shapes are sub-emitters of it.
- One decal stack per effect: up to 3 ground layers share M_decal_stack.
- The telegraph draws in the shared warning pool (64 pooled slots in combat-fx) and is not counted against the effect.
- Status markers: one global thin-instanced draw (vfx_sigil_atlas) plus one global motes system for every status on screen.
- Small, frequent skills (single target, cooldown ≤ 5 s) use an emissive ground flash instead of a PointLight, which protects the 2-light pool.

### 1.6 Cooldowns and SP

Proposed SP pool 100, regen 2/s in combat and 6/s out of combat (the HUD already has an SP bar). Slot pattern, the same for every hero so the skill bar (C8) teaches itself: slot 1 bread-and-butter (4-12 s, 8-18 SP), slot 2 area or secondary (7-10 s), slot 3 signature (8-18 s), slot 4 mobility (8-12 s; the witch's is her damage lance), slot 5 party utility (14-24 s), slot 6 ultimate (80-90 s, 40 SP). Basic attacks are free. Power numbers use the same units as `abilities.json` (attack = 25). Tune so a full rotation from 100 SP lasts about 15-20 s before SP starts to gate it; free basics mean a hero is never idle.

## 2. Statuses and the 8 party combos

Principles taken from the owner's deep review (§4.3, §8 P1-05) and applied in Xexoria's own way: status tags are separate from elements; two statuses from two different heroes make a reaction; the server resolves collisions deterministically; members see every status and its remaining time; the player who completes a combo gets clear feedback. Each hero owns exactly two statuses, every ultimate applies both of its hero's statuses, and basic attacks apply none. No status adds random misses, in line with the miss rule (misses only at a gap of 10 or more levels).

### 2.1 The 12 statuses

| Status | Hero | Lasts | Effect on its own | Glyph (shape cue) | World marker | Reactions | Applied by |
|---|---|---|---|---|---|---|---|
| **Charged** (ประจุอัสนี) `#7FD3FF` | 01 | 6 s | the target's wind-ups take 10 % longer (static jitter) | zig-zag bolt in a circle | 3 cyan-gold sparks orbit the shoulders; a crackle every 0.8 s | C1, C4 | `h01_lodestar_arc`, `h01_bladeward_nova`, `h01_stormfall_cleave` |
| **Cracked** (เกราะร้าว) `#FFC94A` | 01 | 6 s | -20 % DEF | shield with a split line | 3 plate shards circle the waist; a gold seam glints | C7 | `h01_ironfall_cleave`, `h01_stormfall_cleave` |
| **Chilled** (หนาวเหน็บ) `#A9C8FF` | 02 | 6 s | -25 % move speed | six-point snow crystal | rime on the feet and slow falling ice motes | C2, C3 | `h02_hoarfrost_gale`, `h02_rimeshard_nova`, `h02_moonveil_ward`, `h02_celestial_orrery` |
| **Anchored** (แรงถ่วง) `#B07CFF` | 02 | 4 s | -20 % move speed; allies' knockbacks become a 0.3 s stagger, so grouped packs stay grouped (lasts while inside the Hollow and 4 s after) | three downward chevrons | a violet weight ring at the feet that pulls dust inward | C1 | `h02_starless_hollow`, `h02_celestial_orrery` |
| **Marked** (ตราล่า) `#FFB84A` | 03 | 8 s | +10 % damage taken from every source; party members see it through walls and on the minimap | arrowhead inside a diamond | an amber diamond sigil above the head with 4 ticks (1 Hz pulse cap) | C7 | `h03_amberwatch_arrow`, `h03_featherstorm` |
| **Gusted** (ต้องลม) `#5CE6A0` | 03 | 4 s | -15 % move speed; ranged hits on it deal +10 % | spiral curl | two jade wind ribbons spiral around the body | C8 | `h03_featherfan_volley`, `h03_brushtail_vault`, `h03_featherstorm` |
| **Soaked** (เปียกโชก) `#3FE0C5` | 04 | 6 s | -10 % move speed | water drop | drips and a small ripple decal under the feet | C4, C6 | `h04_springwell_rain`, `h04_noonspring_covenant` |
| **Sunlit** (ตราตะวัน) `#FFC94A` | 04 | 6 s | allies hitting it heal 3 % of the damage they deal | sun-wheel (circle with 8 spokes) | a gold halo with turning spokes above the head | C5 | `h04_sunpalm_wave`, `h04_sunwheel_sanctum`, `h04_noonspring_covenant` |
| **Venom** (พิษ) `#B6F23A` | 05 | 6 s, stacks to 3 | 4 power per second per stack; a new stack refreshes the duration | drop with 1-3 pips | lime drips and bubbles; pips show the stacks | C2, C8 | `h05_adders_kiss`, `h05_diamond_scatter`, `h05_violet_masquerade` |
| **Shadowed** (เงาครอบ) `#C83C9E` | 05 | 5 s | +20 % damage taken from behind; the applier's threat on it -50 % | diamond with a smoke wisp | plum smoke wisps trail from the target | C5 | `h05_duskstep`, `h05_nightbloom_smoke`, `h05_violet_masquerade` |
| **Oiled** (เปื้อนน้ำมัน) `#8A5A1E` | 06 | 8 s | -20 % move speed | drop with a sheen ring | dark drips with an iridescent sheen and a small puddle | C6 | `h06_grease_flask`, `h06_gearstorm_hammerfall` |
| **Scorched** (ไหม้เกรียม) `#FF7A1A` | 06 | 4 s | 5 power per second burn | flame tongue | small flames and embers (vfx_fb_flame) | C3 | `h06_forgeheart_slam`, `h06_gearstorm_hammerfall` |

Derived states made by reactions: **Stunned** (มึนงง): cannot act; **Jolted** (ไฟช็อต): boss version of a stun: wind-ups +20 %; **Dazed** (เปิดช่อง ×1.5): the existing ×1.5 punish window; hits on it are flagged crit (monster combat decisions §1); **Exposed** (เปิดจุดอ่อน): +25 % damage taken from every source; **Scalded** (ลวกไอน้ำ): -20 % damage dealt; **Slowed** (ช้าลง): move speed reduced as listed; **Knocked down** (ล้ม): on the ground; cannot act; **Rooted** (ถูกตรึง): cannot move; can still attack; **Taunted** (ถูกยั่วยุ): forced to attack the taunter. All of them use chips in `vfx_sigil_atlas`.

### 2.2 The 8 combos

| Code | Reaction (Thai / English) | Statuses (heroes) | Effect | Elite / boss | Unlocks at step |
|---|---|---|---|---|---|
| **C1** | แม่เหล็กดาวเหนือ / **Lodestone Snap** · pop `ดูดติด!` | Charged (01) + Anchored (02) | A magnetic pulse at the target: every enemy within 6 m that carries Charged or Anchored is yanked to within 1.5 m of the target over 200 ms, takes 30 power and is Stunned 0.8 s. | Elites: pulled, stun 0.4 s. Bosses: not pulled; Jolted 1.2 s. | 2 (01 Orc Swordsman) |
| **C2** | เข็มพิษเยือกแข็ง / **Needlefrost** · pop `เข็มเยือก!` | Chilled (02) + Venom (05) | Consumes all Venom stacks and the chill: frozen venom needles burst 3 m around the target for 20 + 12 per stack power to every enemy inside, and Slow them 40 % for 3 s. | Bosses: full damage, slow 20 %. | 3 (05 Rogue Thief) |
| **C3** | ไอน้ำระเบิด / **Steamburst** · pop `ไอระเบิด!` | Chilled (02) + Scorched (06) | A 3.5 m scalding steam explosion: 45 power to every enemy inside, and Scalded 4 s (-20 % damage dealt). | Bosses: full. | 4 (06 Tinker Merchant) |
| **C4** | แส้อัสนีสายฝน / **Rainlash** · pop `อัสนีฝน!` | Charged (01) + Soaked (04) | Lightning leaps from the target to up to 4 more enemies within 6 m, preferring Soaked ones and any standing in a Springwell Rain zone: 30 power each and Stunned 1.0 s. | Elites: stun 0.5 s. Bosses: no stun; Jolted 2 s. | 5 (04 Bull-kin Acolyte) |
| **C5** | ราหูอมตะวัน / **Rahu's Bite** · pop `ราหูอม!` | Sunlit (04) + Shadowed (05) | Interrupts the target's current wind-up and Dazes it for 2.5 s: the existing ×1.5 punish window, so every party hit on it is a crit. | Bosses: no interrupt; Dazed 1.2 s; 10 s lockout per boss. | 5 (04 Bull-kin Acolyte) |
| **C6** | คราบลื่นปรื๊ด / **Slipslick** · pop `ลื่นปรื๊ด!` | Soaked (04) + Oiled (06) | Oil floats on the water: a 3 m rainbow slick for 3 s at the target. Non-boss enemies inside are Knocked down 1.2 s (once per reaction), then Slowed 40 % while inside. | Bosses: slowed 30 % while inside; no knock-down. | 5 (04 Bull-kin Acolyte) |
| **C7** | รอยแยกเกราะ / **Faultline** · pop `เกราะแตก!` | Cracked (01) + Marked (03) | The armour splits along a glowing fault line: Exposed 5 s (+25 % damage taken from every source), and the first hit from each party member during Exposed deals +40 bonus power. | Bosses: Exposed 3 s. | 6 (03 Wolf-kin Archer) |
| **C8** | ลมพิษระบาด / **Plaguewind** · pop `ลมพิษ!` | Gusted (03) + Venom (05) | Consumes the Venom stacks: a toxic gale (r 4 m) whirls at the target for 3 s; enemies inside take 6 power per consumed stack per second. The gale applies no status. | Bosses: full. | 6 (03 Wolf-kin Archer) |

Why each one exists:
- **C1 Lodestone Snap:** Groups a pack for the witch's and the orc's AoE. The orc's lodestar compass meets her gravity, so the two heroes that ship first can combo on day one.
- **C2 Needlefrost:** Turns the thief's single-target venom into pack damage; a choice against spending the stacks on Fangfall.
- **C3 Steamburst:** A defensive payoff: the party takes less damage while the steam hangs.
- **C4 Rainlash:** The owner's wet + electric example: the healer soaks a pack while healing, the tank's storm-steel conducts.
- **C5 Rahu's Bite:** Light meets shadow, after the Thai eclipse story of Rahu swallowing the sun. It hands the whole party a crit window, which is exactly how crits work in Xexoria.
- **C6 Slipslick:** Oil and water don't mix: a funny, readable crowd-control zone made by a healer and a tinker.
- **C7 Faultline:** The tank cracks, the hunter finds the crack: a burst window for the whole party on a priority target.
- **C8 Plaguewind:** The wind carries the poison into a damage zone. It deliberately does not copy statuses to other enemies, so it is not a spread mechanic.

### 2.3 Reaction rules (server-authoritative)

1. **Trigger.** A reaction fires when a skill hit applies status B to a target that already holds status A, and {A, B} is a listed pair. Order does not matter.
2. **Cross-hero by construction.** Each status belongs to one hero, and no hero's two statuses form a pair, so nobody can combo alone. Two players of the same hero cannot combo with each other either.
3. **Consumption.** The reacting target's two statuses are removed and the reaction applies its own effect; other enemies caught by the reaction (pulled, chained, splashed) keep their own statuses. The triggering hit still deals its normal damage. Multi-hit skills cannot farm repeats.
4. **Lockout.** After any reaction, that target cannot react again for 1.5 s. This covers multi-hits and simultaneous arrivals.
5. **Ancestry.** Skill hits trigger reactions. A skill zone (Starless Hollow, Springwell Rain, Grease Flask, Nightbloom Smoke, Sunwheel Sanctum) counts as a skill hit when it first applies its status to a target; its later ticks and refreshes do not trigger. Reaction damage, DoT ticks (Venom, Scorched, slag) and reaction zones (Plaguewind, Slipslick) carry can_trigger_reaction = false, and so do statuses created by reactions. Basic attacks never apply statuses.
6. **Ordering.** If several pairs are possible, the oldest matching status on the target pairs first (FIFO; the target frame shows statuses oldest-left). Simultaneous events resolve by server tick, then event sequence id, so the result is deterministic.
7. **Credit.** Reaction damage counts 50/50 toward both contributors for the MVP score (inbox A8). Both get a 4 s refund on their ultimate cooldown, at most once per 6 s per player.
8. **Scaling.** Elites take half the CC duration. Bosses turn hard CC into Jolted or a slow, as listed. Reaction damage is not scaled down.
9. **PvP.** Reactions are off in PvP until a PvP balance pass (owner decision D3).
10. **Feedback.** A Thai reaction word pops (pre-shaped word sprite in the damage-number atlas), plus a unique VFX and SFX, and a 1.2 s party banner naming both players. The skill bar shows a small reaction glyph on any skill whose status would react with the current target. The target frame shows each status with a remaining-time ring (deep review §8 P1-05 pass criteria).
11. **Durations.** Statuses last 6 s unless listed. Re-applying refreshes. Venom stacks to 3. A target holds at most 4 statuses; the oldest drops.

### 2.4 Who combos with whom

| | 01 Swordsman | 02 Mage | 03 Archer | 04 Acolyte | 05 Thief | 06 Merchant |
|---|---|---|---|---|---|---|
| **01 Swordsman** | · | C1 Lodestone Snap | C7 Faultline | C4 Rainlash |  |  |
| **02 Mage** | C1 Lodestone Snap | · |  |  | C2 Needlefrost | C3 Steamburst |
| **03 Archer** | C7 Faultline |  | · |  | C8 Plaguewind |  |
| **04 Acolyte** | C4 Rainlash |  |  | · | C5 Rahu's Bite | C6 Slipslick |
| **05 Thief** |  | C2 Needlefrost | C8 Plaguewind | C5 Rahu's Bite | · |  |
| **06 Merchant** |  | C3 Steamburst |  | C6 Slipslick |  | · |

Every one of the 15 possible four-hero parties has **2 to 4** reactions available (the party limit is 4). Only 2 three-hero groups have none: {01, 05, 06}; {02, 03, 04}.

| Party of 4 | Reactions available | Count |
|---|---|---|
| 01, 03, 05, 06 | C7, C8 | 2 |
| 02, 03, 04, 06 | C3, C6 | 2 |
| 01, 02, 03, 04 | C1, C4, C7 | 3 |
| 01, 02, 03, 06 | C1, C3, C7 | 3 |
| 01, 02, 05, 06 | C1, C2, C3 | 3 |
| 01, 03, 04, 06 | C4, C6, C7 | 3 |
| 01, 04, 05, 06 | C4, C5, C6 | 3 |
| 02, 03, 04, 05 | C2, C5, C8 | 3 |
| 02, 03, 05, 06 | C2, C3, C8 | 3 |
| 03, 04, 05, 06 | C5, C6, C8 | 3 |
| 01, 02, 03, 05 | C1, C2, C7, C8 | 4 |
| 01, 02, 04, 05 | C1, C2, C4, C5 | 4 |
| 01, 02, 04, 06 | C1, C3, C4, C6 | 4 |
| 01, 03, 04, 05 | C4, C5, C7, C8 | 4 |
| 02, 04, 05, 06 | C2, C3, C5, C6 | 4 |

**Unlocks by release step** (production order 02 → 01 → 05 → 06 → 04 → 03): every new hero adds at least one combo with heroes already out, so combos exist from the second hero onward.

- Step 1 (02 Witch): no partner yet; statuses and markers ship with the hero.
- Step 2 (01 Orc Swordsman): C1 Lodestone Snap.
- Step 3 (05 Rogue Thief): C2 Needlefrost.
- Step 4 (06 Tinker Merchant): C3 Steamburst.
- Step 5 (04 Bull-kin Acolyte): C4 Rainlash, C5 Rahu's Bite, C6 Slipslick.
- Step 6 (03 Wolf-kin Archer): C7 Faultline, C8 Plaguewind.

### 2.5 Reaction VFX

Each reaction is a pooled preset (≤ 8 draws on High) built from the shared kit, with a Thai pop word and a party banner. Palettes mix the two contributing heroes.

- **C1 Lodestone Snap** · coverage 18 % · palette core `#FFF6DA` · body `#FFC94A` · edge `#B07CFF` · accent `#2B6CFF` · `sfx.rx.lodestone_snap`. Anticipation (0-100 ms): a gold compass star flashes on the target and a violet gravity ring snaps in. Core: 6-12 magnetic field-line arcs (vfx_fb_lightning, gold core, violet edge) converge from the pulled enemies; a collapsing ring wall (vfx_ring_wall r 6 → 1.5 m). Secondaries: dust and spark streaks sucked inward (vfx_motes), gold sparks at each snap. Ground: vfx_rune_compass flash r 2 m plus an inward vfx_shock_ring. After-effect: small compass needles orbit stunned heads for 0.8 s.
- **C2 Needlefrost** · coverage 16 % · palette core `#F6FFE8` · body `#B6F23A` · edge `#6A5CFF` · accent `#A9C8FF` · `sfx.rx.needlefrost`. Anticipation: the venom drips on the target freeze from lime into lilac crystal (100 ms). Core: 18-24 needle crystals (vfx_crystal_shard stretched thin, lime core, ice-lilac edge) radiate out. Secondaries: frozen lime glitter and ice motes. Ground: a frost-venom splatter (vfx_liquid_pool) r 3 m plus vfx_shock_ring. After-effect: needles stuck in the ground melt over 1 s in a lime mist.
- **C3 Steamburst** · coverage 22 % · palette core `#FFF1DE` · body `#E6EEF0` · edge `#FF7A1A` · accent `#A9C8FF` · `sfx.rx.steamburst`. Anticipation: frost and flame flicker against each other on the target, with a hiss (120 ms). Core: an upright vfx_funnel burst of pearl steam plus vfx_fb_smoke billows to 3 m tall (orange core, lilac rim). Secondaries: boiling droplets, orange embers, ice glitter. Ground: a scald ring (vfx_shock_ring) and a wet decal (vfx_liquid_pool) r 3.5 m. After-effect: steam drifts low and fades over 1.5 s at alpha ≤ 0.35.
- **C4 Rainlash** · coverage 20 % · palette core `#F4FBFF` · body `#7FD3FF` · edge `#3FE0C5` · accent `#FFC94A` · `sfx.rx.rainlash`. Anticipation: the droplets on the target light up cyan (100 ms). Core: chained bolts (vfx_fb_lightning stretched, cyan core, gold edge) hop target to target, 60 ms per hop. Secondaries: water splash crowns (vfx_fb_splash) at each struck target, sparks, glittering droplets. Ground: ripple rings (vfx_fb_ripple) and small wet decals under each target. After-effect: static crackle on the wet ground and steam wisps for 0.8 s.
- **C5 Rahu's Bite** · coverage 14 % · palette core `#FFF8E1` · body `#FFC94A` · edge `#5E1150` · accent `#C83C9E` · `sfx.rx.rahus_bite`. Anticipation: the Sunlit halo above the target brightens while plum smoke climbs it (100 ms). Core: a sun disc (vfx_rune_sunwheel, 1.8 m) is bitten: a dark plum crescent sweeps across it and leaves a gold corona ring (vfx_shock_ring) with 8 bead glints. Secondaries: plum smoke tendrils, dripping gold sparks, a few magenta petals. Ground: an eclipse-shadow disc on the ground (r 1.5 m, value-lifted plum with a gold rim). After-effect: the amber '×1.5' Dazed chip and slow gold motes for the window.
- **C6 Slipslick** · coverage 15 % · palette core `#FFE7A3` · body `#8A5A1E` · edge `#2FD4C4` · accent `#E05AD0` · `sfx.rx.slipslick`. Anticipation: oil drips spread on contact with the water (100 ms). Core: a thin-film slick decal (vfx_liquid_pool with an iridescent ramp sweeping teal → magenta → gold) grows r 0 → 3 m. Secondaries: splash crowns (vfx_fb_splash), iridescent bubbles, droplets; enemies play the knock-down reaction. Ground: the slick itself plus ripple rings (vfx_fb_ripple). After-effect: the sheen keeps cycling softly until it ends, then evaporates over 0.6 s.
- **C7 Faultline** · coverage 12 % · palette core `#FFF6E0` · body `#FFB84A` · edge `#2B6CFF` · accent `#FFC94A` · `sfx.rx.faultline`. Anticipation: the amber mark sigil slams into the target's chest (80 ms). Core: a vertical fault-line crack on the target (vfx_ground_split as a billboard, gold seam) and a vermilion-gold crosshair star (vfx_impact_star). Secondaries: steel-gold armour shards burst (vfx_shards), amber sparks. Ground: a cracked-ground decal (vfx_ground_cracks, gold seam) r 1.5 m. After-effect: the seam on the target glows amber for the 5 s at low intensity (1 Hz pulse cap).
- **C8 Plaguewind** · coverage 20 % · palette core `#F6FFE8` · body `#B6F23A` · edge `#5E1150` · accent `#5CE6A0` · `sfx.rx.plaguewind`. Anticipation: venom drips lift into the wind (100 ms). Core: a lime-plum toxic whirl (vfx_funnel upright, 3 m, lime ramp) over a turning vfx_swirl_arms decal. Secondaries: lime droplets, leaf bits, plum spores and green bubbles caught in the whirl. Ground: vfx_swirl_arms plus a splatter (vfx_liquid_pool). After-effect: the whirl unwinds and a low toxic mist fades over 1 s.

Status markers: the 12 statuses draw as small world markers (≤ 0.35 m, above the head or at the feet) from one thin-instanced draw on `vfx_sigil_atlas` plus one global motes system. The target frame (C6) and the party frames show the glyphs with remaining-time rings, oldest on the left.

## 3. The three existing samples, mapped onto heroes

The owner's rule (heroes decisions item 8) counts Nova, Gale and Rift toward the witch's six. Their original skins also fit hero 01 and hero 04, so each timeline is built once and skinned by data: a preset variant `@name` swaps the core mesh or billboard and the ramp row, and keeps the timeline, layers and budgets.

| Sample | Original tag | Witch variant (her six) | Other hero variant | Build order |
|---|---|---|---|---|
| `xs_bladeward_nova` | swordsman | `xs_bladeward_nova@crystal` → `h02_rimeshard_nova`: 12 hex ice crystals 2.6 m, frost palette, Chilled | original blades → `h01_bladeward_nova`: Look v2 blades 2.7 m with gold guards, taunt + Charged | fix the blade skin first against `sw_iron_rebuke` (hand-off upgrade #1), then skin it |
| `xs_gale_palm` | monk / acolyte | `xs_gale_palm@frost` → `h02_hoarfrost_gale`: crescent-moon hex sigil (`vfx_hex_sigil`), frost palette, Chilled | `xs_gale_palm@sun` → `h04_sunpalm_wave`: the palm sigil kept and enlarged to 1.8 m, sun palette, heals allies it passes, Sunlit | fix the palm skin first against `fs_palm_wave` (upgrade #2, ≤ 10 draws), then skin it |
| `xs_void_rift` | sorcerer | itself → `h02_starless_hollow` (player-facing name changed for originality), Anchored | - (its funnel, swirl and rune assets are reused by C8, `h03_featherstorm`, `h04_noonspring_covenant`) | fix against `st_underworld_gate` (upgrade #3) |

**Witch prior art for the three new skills.** `Downloads\hero\02\vfx-blender-samples\ (also packaged as hero02_original_mage_vfx_review_v2.zip; the inventory plans a move to Downloads\Xexoria-Game\agent-output\20261001-mage-vfx-samples\)`: `lance` Sapphire Star Lance (1.65 s) → `h02_star_lance`; `aegis` Royal Star Aegis (1.85 s) → `h02_moonveil_ward`; `orrery` Celestial Orrery Nova (3.25 s) → `h02_celestial_orrery`. Editable Blender 5.2 sources with Geometry Nodes rings, star arrays and crystal arrangements. They are review candidates and below Look v2: thin line work, about 5-8 % coverage, no ground mass and few secondaries. Reuse their structure, rings and star arrays; add the masses, fills, ground layers and after-effects listed here.

## 4. Heroes and their skills (production order)

Per hero: identity, a one-screen skill table, then one block per skill. In the blocks, time ranges are in ms from cast start; `hit` is the confirmed hit or impact and `end` is the zone or shield end.

### 4.0 Identity at a glance

| Hero | Role | Element | Palette (hues) | Shape language | Statuses |
|---|---|---|---|---|---|
| 01 Orc Swordsman · ออร์คนักดาบ | Tank | Storm-steel (thunder + steel) | body `#7FD3FF` · edge `#2B6CFF` · accent `#FFC94A` (storm blue / sky cyan + compass gold) | Heavy crescents and arcs, ground cracks and splits, spectral blades, the four-point stars and eight-point compass from his armour, lightning forks | Charged, Cracked |
| 02 Witch · แม่มด | Control + ranged AoE | Astral frost and hollow (starlight, crystal ice, gravity) | body `#B07CFF` · edge `#5A1FD1` · accent `#FFD36E` (violet, frost lilac-ice and star gold; a teal rim only on the Hollow) | Four-point sparkle stars (from her robe), heptagram rune circles, crescent moons, spirals and orbits, hexagonal crystal shards | Chilled, Anchored |
| 03 Wolf-kin Archer · นักธนูหมาป่า | Ranged DPS | Gale and wild (wind, leaves, the moonlit hunt) | body `#5CE6A0` · edge `#1F9E86` · accent `#FFB84A` (wind jade and the hunter's amber of her eyes) | Arrowheads and chevrons, feathers and leaf blades (from her cape's gold leaves), wind streaks and spiral curls, crescent fangs | Marked, Gusted |
| 04 Bull-kin Acolyte · นักบวชวัว | Healer-support | Sun and spring (holy sunlight, healing water) | body `#FFC94A` · edge `#E07A1F` · accent `#3FE0C5` (sun gold + spring turquoise) | Sun-wheels with spokes (his shoulder emblems), halos and rays, rings of water, droplets and ripples, horn-like arcs | Soaked, Sunlit |
| 05 Rogue Thief · โจร | Melee DPS | Shadow and venom | body `#C83C9E` · edge `#5E1150` · accent `#B6F23A` (shadow magenta-plum + venom lime) | Diamonds (his cape's diamond-cut hem), X-crosses, thin crescents, smoke petals and drips | Venom, Shadowed |
| 06 Tinker Merchant · ช่างกลพ่อค้า | Utility | Forge and steam (heat, oil, clockwork) | body `#FF7A1A` · edge `#C2361B` · accent `#2FD4C4` (molten orange + brass + lens teal) | Gears and cog teeth (her choker and studs), rivets, pistons, steam puffs, sparks, hex nuts | Oiled, Scorched |

Hue separation was checked on purpose: the witch's violet (≈ 266°) and the thief's magenta-plum (≈ 318°) stay about 50° apart; the archer's jade (≈ 150°) and the thief's lime (≈ 82°) about 70° apart; the orc's cyan arcs and the witch's lilac frost share a hue family but differ by value, accent (gold sparks vs violet edges) and shape (lightning forks vs hex crystals); the tinker's orange and the acolyte's gold differ by value and shape (soot, gears, sparks vs halos, spokes, water). Telegraph colours are reserved and never used as a hero body colour.

### 4.1 Hero 02: Witch · แม่มด

| Field | Spec |
|---|---|
| Party role | **Control + ranged AoE** (คุมฝูง + เวทวงกว้าง) |
| Party job | Groups and holds packs (Starless Hollow, Rimeshard Nova), peels with knockbacks (Hoarfrost Gale), shields one ally (Moonveil Ward), and primes Chilled and Anchored. |
| Element | Astral frost and hollow (starlight, crystal ice, gravity) |
| Palette (violet, frost lilac-ice and star gold; a teal rim only on the Hollow) | core `#FFF0FF` · body `#B07CFF` · frost `#A9C8FF` · edge `#5A1FD1` · accent `#FFD36E` · rim `#5FF2D8` · abyss `#12052B` |
| Shape language | Four-point sparkle stars (from her robe), heptagram rune circles, crescent moons, spirals and orbits, hexagonal crystal shards. Curved, orbiting, layered rings. |
| Statuses | Chilled (หนาวเหน็บ), Anchored (แรงถ่วง) |
| Combos | C1 Lodestone Snap (with 01); C2 Needlefrost (with 05); C3 Steamburst (with 06) |
| Weapon | Crystal staff (blue crystal, gold ribbons) · Blender · 1.80 m → 2.00 m (cap: no taller than crown + 0.25 m) |
| Sockets | socket_weapon_R (staff; left hand on grip_secondary), socket_back |
| Trail and VFX markers | grip origin, +Y; fx_base (heel), fx_tip (crystal top), fx_head (crystal centre = cast origin). every spell casts from fx_head; a crystal-arc ribbon fx_base → fx_tip (10 segments, 200 ms) only on the Rimeshard Nova slam and basic link 2. |
| Rig sets | base + caster + mage · display_scale 1.000 · crown 1.80 m (without the hat) |

| Slot | Id | Thai / English | Type | Telegraph | Range / radius | Timing (w / a / r) · release | CD · SP | Status → combo |
|---|---|---|---|---|---|---|---|---|
| basic | `h02_basic` | กระสุนละอองดาว / Starmote Bolts | damage | **none (target bracket only)** | range 12 m · 22 m/s | 100 / 67 / 233 · f3 | 0.4 s · 0 | none |
| 1 | `h02_hoarfrost_gale` | ลมเหมันต์สะกด / Hoarfrost Gale | damage + control | **AREA lane** 1.5 × 10 m | range 10 m · r 2.2 m · 16 m/s · knockback 1.5 m | 200 / 67 / 200 · f6 | 7 s · 14 | Chilled 6 s → C2 Needlefrost (+ Venom from 05); C3 Steamburst (+ Scorched from 06) |
| 2 | `h02_rimeshard_nova` | วงผลึกเหมันต์ / Rimeshard Nova | control + damage | **AREA ring** r 4 m | self · r 4 m · knock-up 0.4 m | 200 / 100 / 300 · f6 | 10 s · 16 | Chilled 6 s → C2 Needlefrost (+ Venom from 05); C3 Steamburst (+ Scorched from 06) |
| 3 | `h02_starless_hollow` | หลุมดาราดับ / Starless Hollow | control + damage | **AREA ring** r 4.5 m | range 12 m · r 4.5 m · pull 1.2 m/s | 600 / 100 / 200 · f18 | 14 s · 22 | Anchored 4 s → C1 Lodestone Snap (+ Charged from 01) |
| 4 | `h02_star_lance` | หอกดาราไพลิน / Sapphire Star Lance | damage | **AREA lane** 1.2 × 16 m | range 16 m · 40 m/s · pierces 3 | 467 / 67 / 300 · f14 | 6 s · 16 | none |
| 5 | `h02_moonveil_ward` | ม่านจันทราพิทักษ์ / Moonveil Ward | buff | **SAFE brackets** | range 14 m · r 3 m | 300 / 67 / 300 · f9 | 16 s · 18 | Chilled 6 s → C2 Needlefrost (+ Venom from 05); C3 Steamburst (+ Scorched from 06) |
| 6 | `h02_celestial_orrery` | จักรดาราโคจร / Celestial Orrery | ultimate + control | **HEAVY ring** r 7 m | range 14 m · r 7 m · knock-up 0.6 m | 900 / 100 / 300 · f27 | 90 s · 40 | Chilled → C2, C3; Anchored → C1 |

#### 02.0 `h02_basic` · กระสุนละอองดาว · Starmote Bolts
*Basic attack · damage · VFX preset `xs_h02_basic` · budget class basic*

Two quick bolts from the staff crystal: a spinning four-point star mote, then a small crescent.

| Field | Spec |
|---|---|
| Targeting · telegraph | auto-target projectile (current target, else straight ahead) · **none (target bracket only)** |
| Range · radius | range 12 m · 22 m/s |
| Timing | 100 / 67 / 233 ms · **release f3** (100 ms) · clip `caster.attack_1 / caster.attack_2` 400 ms (12 f) |
| Clip events (ms) | charge_start 0, release 100, link_open 400 |
| Cooldown · cost · power | 0.4 s · 0 SP · 25 per link · magical · element `astral_frost` |
| Status → combo | none |
| Palette | core `#FFF0FF` · body `#B07CFF` · edge `#5A1FD1` · accent `#FFD36E` |
| Peak coverage | 3 % at the 13 m camera |
| SFX | `sfx.h02.basic` · .cast / .impact |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–100 | `vfx_motes` | A gold four-point glint swells on fx_head; 4 motes converge. | Medium+ |
| Mesh core | 100 → hit | `vfx_motes`, `vfx_crescent_slash` | Link 1: a spinning four-point crystal star (0.45 m) with a short violet ribbon. Link 2: a small 60° crescent bolt (0.6 m). | all tiers |
| Secondaries | 100 → hit+200 | `vfx_motes` | 8 sparkle motes shed along the path, gold accent. | Medium+ (×0.5 on Medium) |
| Ground layer | hit → hit+300 | `vfx_impact_star` | A 0.8 m star flash under the target. | Medium+ |
| After-effect | hit → hit+300 | `vfx_motes` | 6 glitter motes fade. | High+ |

**Tiers:** Medium: same shapes and palette; drops after-effect; secondaries ×0.5. Low: mesh core + telegraph; no light.

#### 02.1 `h02_hoarfrost_gale` · ลมเหมันต์สะกด · Hoarfrost Gale
*Skill 1 · damage + control · VFX preset `xs_gale_palm@frost` · reuses `xs_gale_palm` · budget class heroic*

A crescent-moon hex rides a frost gale; it blasts the first enemy and everything within 2.2 m back 1.5 m and Chills them.

| Field | Spec |
|---|---|
| Targeting · telegraph | skillshot, first enemy hit · **AREA lane** 1.5 × 10 m; then an AREA ring r 2.2 m at the impact point for 200 ms |
| Range · radius | range 10 m · r 2.2 m · 16 m/s · knockback 1.5 m |
| Timing | 200 / 67 / 200 ms · **release f6** (200 ms) · clip `mage.skill_gale` 467 ms (14 f) |
| Clip events (ms) | charge_start 0, release 200 |
| Cooldown · cost · power | 7 s · 14 SP · 40 · magical · element `astral_frost` |
| Effects | knockback 1.5 m |
| Status → combo | Chilled 6 s → C2 Needlefrost (+ Venom from 05); C3 Steamburst (+ Scorched from 06) |
| Palette | core `#F4F7FF` · body `#A9C8FF` · edge `#6A5CFF` · accent `#FFD36E` |
| Peak coverage | 18 % at the 13 m camera |
| SFX | `sfx.h02.hoarfrost_gale` · .cast / .travel_loop / .impact |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–200 | `vfx_fb_swirl`, `vfx_streak`, `vfx_motes` | Two counter-rotating frost swirls on fx_head grow 0.4 → 1.0 m; 12 ice streaks converge; hoarfrost creeps up the staff. | Medium+ |
| Mesh core | 200 → hit | `vfx_hex_sigil`, `vfx_cone_burst` | vfx_hex_sigil billboard 1.6 m (a crescent moon cradling a snow crystal in a rune disc) wobbling ±6° at 9 Hz with a pale core; a frost release cone 200-320 ms. The broad crescent silhouette fixes the hand-off's 'tiny circular sigil' defect. | all tiers |
| Secondaries | 200 → hit+250 | `vfx_motes`, `vfx_streak` | 3 lilac → violet helix ribbons (TrailMesh; 2 on Medium), shed frost streaks at 60/s, gold glints. | Medium+ (×0.5 on Medium) |
| Ground layer | hit → hit+1,400 | `vfx_swirl_arms`, `vfx_ground_cracks` | A frost vortex decal r 0 → 2.6 m spinning 2.4 → 0.6 rad/s, a lilac frost-crack ring, and a dust ring under the caster at release. | all tiers |
| After-effect | hit → hit+1,200 | `vfx_funnel`, `vfx_motes` | A 2.5 m frost funnel twists up while 24 ice-glitter bits spiral up and settle as rime. | Medium+ (×0.5 on Medium) |
| Light | 0 → hit+300 | pooled `PointLight` | #A9C8FF, range 7 m: charge 0 → 2, travel 2, impact 5 → 0. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries, after-effect ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** Core alpha 0.85, rim 0.5; the funnel is thin and translucent, so pushed enemies stay visible.

#### 02.2 `h02_rimeshard_nova` · วงผลึกเหมันต์ · Rimeshard Nova
*Skill 2 · control + damage · VFX preset `xs_bladeward_nova@crystal` · reuses `xs_bladeward_nova` · budget class heroic*

Twelve hexagonal ice crystals erupt in a ring around her and knock nearby enemies up: her get-off-me button.

| Field | Spec |
|---|---|
| Targeting · telegraph | self AoE · **AREA ring** r 4 m (radial wipe over the 150 ms cast) |
| Range · radius | self · r 4 m · knock-up 0.4 m |
| Timing | 200 / 100 / 300 ms · **release f6** (200 ms) · clip `mage.skill_nova` 600 ms (18 f) |
| Clip events (ms) | charge_start 0, plant 150, hit 200 |
| Cooldown · cost · power | 10 s · 16 SP · 35 · magical · element `astral_frost` |
| Effects | knock-up 0.4 m |
| Status → combo | Chilled 6 s → C2 Needlefrost (+ Venom from 05); C3 Steamburst (+ Scorched from 06) |
| Palette | core `#F4F7FF` · body `#A9C8FF` · edge `#6A5CFF` · accent `#FFD36E` |
| Peak coverage | 22 % at the 13 m camera |
| SFX | `sfx.h02.rimeshard_nova` · .cast / .erupt / .shatter |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–150 | `vfx_rune_ring_blade`, `vfx_motes` | The notched ring (crystal notches) draws clockwise at r 4.0 m; 16 frost motes spiral from the ring into the staff heel. | Medium+ |
| Mesh core | 150–1,200 | `vfx_crystal_shard` | 12 hex crystals, 2.6 m tall (taller than the 2.1 m blades for Look v2), rise from -1.7 m with back-out over 110 ms at radii 2.9 / 3.5 m, staggered 8 ms clockwise, tilted out 10-22°; lilac fresnel rim, violet body; erode tip → base from 700 ms. | all tiers |
| Secondaries | 150–900 | `vfx_shards`, `vfx_fb_dust`, `vfx_fb_lightning` | Ice shards thrown out under gravity, snow-dust puffs at 45 %, and 4-6 gold star-threads arcing between neighbouring crystals. | Medium+ (×0.5 on Medium) |
| Ground layer | 150–2,500 | `vfx_impact_star`, `vfx_shock_ring`, `vfx_ring_wall`, `vfx_ground_cracks` | A 3.2 m ground flash, a shock ring and 0.6 m ring wall r 0.5 → 4.6 m, then a frost crack per crystal cooling lilac → indigo. | all tiers |
| After-effect | 260–1,500 | `vfx_fb_dust`, `vfx_motes` | Low frost mist at 12 % drifting outward; falling ice glitter. | Medium+ |
| Light | 150–600 | pooled `PointLight` | #A9C8FF, range 9 m, 0 → 6 → 0, peak at 190 ms. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** Crystals stand on the 2.9-3.5 m perimeter; the witch and enemies inside stay visible.

#### 02.3 `h02_starless_hollow` · หลุมดาราดับ · Starless Hollow
*Skill 3 · control + damage · VFX preset `xs_void_rift` · reuses `xs_void_rift` · budget class heroic*

She tears a starless hole in the ground: a 4.5 m gravity well that drags enemies in for six beats and then implodes.

| Field | Spec |
|---|---|
| Targeting · telegraph | ground target within 12 m · **AREA ring** r 4.5 m (the ring stays for the zone's life) |
| Range · radius | range 12 m · r 4.5 m · pull 1.2 m/s |
| Timing | 600 / 100 / 200 ms · **release f18** (600 ms) · clip `mage.skill_hollow` 900 ms (27 f) |
| Zone / follow-up | 900-3050 ms; collapse burst at 3050 ms |
| Clip events (ms) | rune 0, slam 600, pulse 900 |
| Cooldown · cost · power | 14 s · 22 SP · 6 × 12 + 30 collapse · magical · element `astral_frost` |
| Effects | pull 1.2 m/s toward the centre |
| Status → combo | Anchored 4 s → C1 Lodestone Snap (+ Charged from 01) |
| Palette | core `#FFF0FF` · body `#B07CFF` · edge `#5A1FD1` · accent `#5FF2D8` · abyss `#12052B` |
| Peak coverage | 30 % at the 13 m camera |
| SFX | `sfx.h02.starless_hollow` · .cast / .open / .tick / .collapse |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–600 | `vfx_rune_circle_outer`, `vfx_rune_circle_inner`, `vfx_fb_lightning`, `vfx_motes` | The outer rune circle wipes in over 450 ms turning +10°/s; the inner heptagram (r 3.0 m) fades in turning -20°/s; 3 arcs crawl along the ring; rim motes rise 0.6 m. | Medium+ |
| Mesh core | 600–3,050 | `vfx_swirl_arms`, `vfx_funnel`, `vfx_ring_wall` | Abyss disc (alpha-blended, not additive) r 0 → 4.2 m with back-out, spin 1.2 → 2.0 rad/s; an inverted depth funnel below the ground; a broken teal rim pulsing (width ×1.4, brightness ×2 for 120 ms) on each tick. Hand-off upgrade #3: a darker visible centre and multi-scale painterly violet bands. | all tiers |
| Secondaries | 900–2,700 | `vfx_motes`, `vfx_shock_ring`, `vfx_fb_impact` | 40 pull motes born at the rim spiral in and down; each tick sends an inward shock ring 4.5 → 1 m and a violet impact on every enemy. | Medium+ (×0.5 on Medium) |
| Ground layer | 3,050–4,500 | `vfx_fb_lightning`, `vfx_shock_ring`, `vfx_scorch` | Implosion at 3050 ms: 8 radial arcs, an outward shock ring r 0 → 5 m and debris, then an abyss-violet scorch. | all tiers |
| After-effect | 3,050–4,500 | `vfx_motes` | Embers and violet motes drift up while the scorch cools. | Medium+ |
| Light | 600–3,400 | pooled `PointLight` | #B07CFF, range 10 m: opening 0 → 4, +2 on each tick, collapse flash 8 → 0. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** The abyss is value-lifted to L* ≥ 25 under enemies and the violet light rims them; the broken teal rim never competes with the smooth amber band.

#### 02.4 `h02_star_lance` · หอกดาราไพลิน · Sapphire Star Lance
*Skill 4 · damage · VFX preset `xs_h02_star_lance` · prior art: hero02 package 'lance' · budget class heroic*

A heptagram opens before the staff and fires a faceted sapphire lance that pierces three enemies in a 16 m line.

| Field | Spec |
|---|---|
| Targeting · telegraph | aimed line, pierces up to 3 · **AREA lane** 1.2 × 16 m |
| Range · radius | range 16 m · 40 m/s · pierces 3 |
| Timing | 467 / 67 / 300 ms · **release f14** (467 ms) · clip `mage.skill_lance` 833 ms (25 f) |
| Clip events (ms) | charge_start 0, release 467 |
| Cooldown · cost · power | 6 s · 16 SP · 90 (×1.3 against Anchored targets) · heavy · magical · element `astral_frost` |
| Effects | pierces 3 |
| Status → combo | none |
| Palette | core `#F2F8FF` · body `#4FA8FF` · edge `#6A4CFF` · accent `#FFD36E` |
| Peak coverage | 16 % at the 13 m camera |
| SFX | `sfx.h02.star_lance` · .charge / .release / .pierce |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–467 | `vfx_rune_circle_inner`, `vfx_motes` | A vertical heptagram disc (1.4 m) unfolds in front of fx_head; 12 crystal motes converge; 3 gold four-point stars orbit the disc; sapphire light ramps 0 → 3. | Medium+ |
| Mesh core | 467–900 | `vfx_crystal_lance` | A 2.6 m faceted sapphire spear with a star head and gold inlay, plus a 2-ribbon spiral (TrailMesh). | all tiers |
| Secondaries | 467–1,100 | `vfx_motes`, `vfx_ring_wall`, `vfx_fb_impact` | Shed crystal glitter, 3 thin sonic rings stamped along the path, star sparks at each pierce. | Medium+ (×0.5 on Medium) |
| Ground layer | 467–1,700 | `vfx_streak`, `vfx_impact_star` | A lilac frost streak along the lane and a star flash under each pierced enemy. | all tiers |
| After-effect | 700–2,000 | `vfx_motes` | The heptagram erodes away; sapphire motes hang along the lane. | Medium+ |
| Light | 300–700 | pooled `PointLight` | #4FA8FF, range 8 m, travelling with the lance. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 02.5 `h02_moonveil_ward` · ม่านจันทราพิทักษ์ · Moonveil Ward
*Skill 5 · buff · VFX preset `xs_h02_moonveil_ward` · prior art: hero02 package 'aegis' · budget class heroic*

A faceted moon-crystal dome shields one ally (or herself) for 40 damage over 5 s; when it breaks or ends it pulses frost 3 m.

| Field | Spec |
|---|---|
| Targeting · telegraph | ally or self within 14 m · **SAFE brackets**; then an AREA ring r 3 m at the ally when the pulse fires for 200 ms |
| Range · radius | range 14 m · r 3 m |
| Timing | 300 / 67 / 300 ms · **release f9** (300 ms) · clip `mage.skill_ward` 667 ms (20 f) |
| Clip events (ms) | charge_start 0, release 300 |
| Cooldown · cost · power | 16 s · 18 SP · shield 40; break pulse 20 · magical · element `astral_frost` |
| Effects | shield 40 for 5 s; frost pulse r 3 m on break or expiry |
| Status → combo | Chilled 6 s → C2 Needlefrost (+ Venom from 05); C3 Steamburst (+ Scorched from 06) |
| Palette | core `#F4F7FF` · body `#A9C8FF` · edge `#8A5CFF` · accent `#FFD36E` |
| Peak coverage | 12 % at the 13 m camera |
| SFX | `sfx.h02.moonveil_ward` · .cast / .absorb / .break |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–300 | `vfx_crystal_shard`, `vfx_sigil_atlas` | Two crescent moons orbit in from 2 m and lock above the ally; the aegis star-plate glyph flickers on. | Medium+ |
| Mesh core | 300–5,300 | `vfx_hex_dome` | A geodesic hex-crystal dome r 1.2 m, alpha 0.35 body / 0.7 rim, scrolling star sparkle; each absorbed hit flashes the struck facet gold. | all tiers |
| Secondaries | 300–5,300 | `vfx_crystal_shard`, `vfx_motes` | 3 orbiting diamond crystals and gold four-point glints on the facets. | Medium+ (×0.5 on Medium) |
| Ground layer | 300–5,300 | `vfx_rune_circle_inner` | A moon-phase heptagram r 1.2 m under the ally. | all tiers |
| After-effect | end → end+1,200 | `vfx_shards`, `vfx_shock_ring`, `vfx_ground_cracks` | On break or expiry the dome shatters into hex shards, a frost pulse ring races to 3 m, and a rime decal spreads. | all tiers |
| Light | end → end+300 | pooled `PointLight` | #A9C8FF 0 → 3 → 0 at the break. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer, after-effect + telegraph; no light.
**Readability:** Dome alpha caps keep the ally's silhouette and HP plate visible; a refresh replaces the old dome, so there is never a double dome.
**Note:** Coverage 12 % while warding and 16 % at the break pulse: below the 15 % heroic floor on purpose (single target; owner decision D4).

#### 02.6 `h02_celestial_orrery` · จักรดาราโคจร · Celestial Orrery
*Skill 6 · ultimate + control · VFX preset `xs_h02_celestial_orrery` · prior art: hero02 package 'orrery' · budget class ultimate*

She conjures a sky orrery over a 7 m field: three gold rings and seven crystal moons orbit and sweep beams that Chill and Anchor, then collapse into a star-nova.

| Field | Spec |
|---|---|
| Targeting · telegraph | ground target within 14 m · **HEAVY ring** r 7 m |
| Range · radius | range 14 m · r 7 m · knock-up 0.6 m |
| Timing | 900 / 100 / 300 ms · **release f27** (900 ms) · clip `mage.skill_orrery` 1,300 ms (39 f) |
| Zone / follow-up | 900-3300 ms autonomous orrery (she can act after 1300 ms); nova at 3300 ms |
| Clip events (ms) | charge_start 0, release 900 |
| Cooldown · cost · power | 90 s · 40 SP · 8 × 15 + 120 nova · heavy · magical · element `astral_frost` |
| Effects | knock-up 0.6 m on the nova |
| Status → combo | Chilled 6 s → C2 Needlefrost (+ Venom from 05); C3 Steamburst (+ Scorched from 06) · Anchored 4 s → C1 Lodestone Snap (+ Charged from 01) |
| Palette | core `#FFF4FF` · body `#B07CFF` · edge `#5A1FD1` · accent `#FFD36E` · rim `#5FF2D8` |
| Peak coverage | 45 % at the 13 m camera |
| SFX | `sfx.h02.celestial_orrery` · .cast / .ring_lock / .beam_tick / .nova |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–900 | `vfx_rune_circle_outer`, `vfx_rune_circle_inner`, `vfx_orbit_ring`, `vfx_motes` | The 7 m outer rune circle (gold-violet) and inner heptagram wipe in; 3 gold orbit rings assemble 4-6 m above the field; starfield motes rise from the ground. | Medium+ |
| Mesh core | 900–3,300 | `vfx_orbit_ring`, `vfx_crystal_shard` | 7 crystal moons (0.6 m) ride the tilted, precessing rings, each casting a thin value-graded beam (0.3 m) that sweeps the ground. Low keeps the rings and 3 moons. | all tiers |
| Secondaries | 900–3,300 | `vfx_fb_lightning`, `vfx_motes` | Comet trails behind the moons (3 TrailMesh), violet arcs linking the rings, falling star glints. | Medium+ (×0.5 on Medium) |
| Ground layer | 900–4,800 | `vfx_rune_circle_inner`, `vfx_impact_star`, `vfx_shock_ring`, `vfx_scorch` | Turning circles and beam scorch dots; at 3300 ms the star-nova: an 8 m star flash, a shock ring r 0 → 7.5 m and a violet-gold star scorch. | all tiers |
| After-effect | 3,300–4,800 | `vfx_motes` | The rings erode away; star motes fall slowly; teal rim motes. | Medium+ |
| Light | 900–3,600 | pooled `PointLight` | #B07CFF range 12 m sustained at 3; a burst 9 → 0 at 3300 ms shifting to #FFD36E. | High+ |
| Distortion | 3,300–3,500 | post | Radial heat-shimmer ring with the nova. | Epic only |

**Tiers:** Epic adds distortion. Medium: same shapes and palette; drops light, distortion; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** Rings and moons sit 4-6 m up, above every head; beams are thin; the toothed HEAVY band draws above every layer.

### 4.2 Hero 01: Orc Swordsman · ออร์คนักดาบ

| Field | Spec |
|---|---|
| Party role | **Tank** (แทงก์แนวหน้า) |
| Party job | Holds aggro (Bladeward Nova taunts), cuts party damage (Eightfold Ward), breaks guards and armour (Ironfall Cleave), and primes Charged and Cracked for partners. |
| Element | Storm-steel (thunder + steel) |
| Palette (storm blue / sky cyan + compass gold) | core `#F4FBFF` · body `#7FD3FF` · edge `#2B6CFF` · accent `#FFC94A` · dark `#0E1F4D` |
| Shape language | Heavy crescents and arcs, ground cracks and splits, spectral blades, the four-point stars and eight-point compass from his armour, lightning forks. Angular and heavy; everything lands on the ground. |
| Statuses | Charged (ประจุอัสนี), Cracked (เกราะร้าว) |
| Combos | C1 Lodestone Snap (with 02); C4 Rainlash (with 04); C7 Faultline (with 03) |
| Weapon | Longsword (gold hilt, blue gems) · Tripo P2.0 single image · 1.10 m → 1.32 m (+20 %) |
| Sockets | socket_weapon_R (one-hand; two-hand option via grip_secondary), sheath on socket_back |
| Trail and VFX markers | grip origin, +Y; fx_base (guard), fx_tip (point). fx_base (guard) → fx_tip (point): ribbon 12 segments, life 160 ms on basics and 240 ms on skills, width = blade length, ramp core → body → edge with a gold rim; gold sparks emit from fx_tip during skills. |
| Rig sets | base + blade_1h + swordsman · display_scale 1.111 · crown 2.00 m |

| Slot | Id | Thai / English | Type | Telegraph | Range / radius | Timing (w / a / r) · release | CD · SP | Status → combo |
|---|---|---|---|---|---|---|---|---|
| basic | `h01_basic` | ฟันเหล็กพายุ / Stormsteel Strikes | damage | **none (target bracket only)** | range 3 m · 90° | 100 / 60 / 200 · f3 | 0.4 s · 0 | none |
| 1 | `h01_lodestar_arc` | ฟันโค้งดาวเหนือ / Lodestar Arc | damage | **AREA fan** r 4 m, 120° | range 4 m · 120° | 250 / 100 / 350 · f7.5 | 5 s · 10 | Charged 6 s → C1 Lodestone Snap (+ Anchored from 02); C4 Rainlash (+ Soaked from 04) |
| 2 | `h01_bladeward_nova` | วงดาบพิทักษ์ / Bladeward Nova | control + damage | **AREA ring** r 4 m | self · r 4 m · knock-up 0.4 m · taunt 3,000 ms | 200 / 100 / 300 · f6 | 9 s · 16 | Charged 6 s → C1 Lodestone Snap (+ Anchored from 02); C4 Rainlash (+ Soaked from 04) |
| 3 | `h01_ironfall_cleave` | ผ่าเหล็กถล่ม / Ironfall Cleave | debuff + damage | **HEAVY lane** 1.6 × 5 m | range 5 m | 333 / 100 / 400 · f10 | 8 s · 14 | Cracked 6 s → C7 Faultline (+ Marked from 03) |
| 4 | `h01_compass_rush` | พุ่งทะลวงเข็มทิศ / Compass Rush | mobility | **AREA lane** 2 × 8 m | range 8 m · dash 400 ms | 133 / 400 / 233 · f4 | 10 s · 12 | none |
| 5 | `h01_eightfold_ward` | ปราการแปดทิศ / Eightfold Ward | buff | **SAFE ring** r 5 m | self · r 5 m · zone 6,000 ms | 300 / 100 / 300 · f9 | 20 s · 20 | none |
| 6 | `h01_stormfall_cleave` | ดาบพายุถล่มฟ้า / Stormfall Cleave | ultimate + damage | **HEAVY lane** 3 × 10 m | range 10 m · r 4 m | 667 / 200 / 500 · f20 | 80 s · 40 | Charged → C1, C4; Cracked → C7 |

#### 01.0 `h01_basic` · ฟันเหล็กพายุ · Stormsteel Strikes
*Basic attack · damage · VFX preset `xs_h01_basic` · budget class basic*

Two heavy one-handed cuts; the second throws a short gold-rimmed crescent.

| Field | Spec |
|---|---|
| Targeting · telegraph | melee fan 3 m, 90° · **none (target bracket only)** |
| Range · radius | range 3 m · 90° |
| Timing | 100 / 60 / 200 ms · **release f3** (100 ms) · clip `blade_1h.attack_1 / blade_1h.attack_2` 400 ms (12 f) |
| Clip events (ms) | swing_start 0, trail_on 67, hit 100, trail_off 167, link_open 400 |
| Cooldown · cost · power | 0.4 s · 0 SP · 25 per link · physical · element `storm` |
| Status → combo | none |
| Palette | core `#F4FBFF` · body `#7FD3FF` · edge `#2B6CFF` · accent `#FFC94A` |
| Peak coverage | 3 % at the 13 m camera |
| SFX | `sfx.h01.basic` · .swing / .impact |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–100 | `vfx_motes` | A steel glint travels base → tip along the blade. | Medium+ |
| Mesh core | 100–260 | `vfx_crescent_slash` | The weapon ribbon (sky-cyan core, storm-blue edge, 160 ms); link 2 adds a 90° crescent (1.2 m) with a gold rim. | all tiers |
| Secondaries | hit → hit+200 | `vfx_motes`, `vfx_fb_lightning` | 6 gold sparks and 2 tiny static forks. | Medium+ (×0.5 on Medium) |
| Ground layer | hit → hit+400 | `vfx_fb_dust` | Boot-scuff dust on link 2. | Medium+ |
| After-effect | hit → hit+250 | `vfx_motes` | Static crackle on the blade. | High+ |

**Tiers:** Medium: same shapes and palette; drops after-effect; secondaries ×0.5. Low: mesh core + telegraph; no light.

#### 01.1 `h01_lodestar_arc` · ฟันโค้งดาวเหนือ · Lodestar Arc
*Skill 1 · damage · VFX preset `xs_h01_lodestar_arc` · budget class heroic*

A wide 120° storm-steel crescent that hits up to three enemies and leaves them Charged.

| Field | Spec |
|---|---|
| Targeting · telegraph | melee fan 4 m, 120°, up to 3 targets · **AREA fan** r 4 m, 120° |
| Range · radius | range 4 m · 120° |
| Timing | 250 / 100 / 350 ms · **release 250 ms = f7.5**: event at 250 ms, contact pose on f8 · clip `swordsman.skill_arc` 700 ms (21 f) |
| Clip events (ms) | swing_start 0, trail_on 200, hit 250, trail_off 350 |
| Cooldown · cost · power | 5 s · 10 SP · 45 · physical · element `storm` |
| Status → combo | Charged 6 s → C1 Lodestone Snap (+ Anchored from 02); C4 Rainlash (+ Soaked from 04) |
| Palette | core `#F4FBFF` · body `#7FD3FF` · edge `#2B6CFF` · accent `#FFC94A` |
| Peak coverage | 16 % at the 13 m camera |
| SFX | `sfx.h01.lodestar_arc` · .swing / .thunder_hit |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–250 | `vfx_motes` | A gold four-point star gathers on fx_tip; 6 static sparks crawl up the blade; dust grinds under the back foot. | Medium+ |
| Mesh core | 250–400 | `vfx_crescent_slash` | A 120° x 4 m storm-steel crescent (scrolling storm streaks, cyan core → storm-blue edge, gold rim) sweeps with the weapon ribbon. | all tiers |
| Secondaries | 250–600 | `vfx_fb_lightning`, `vfx_motes`, `vfx_shards` | 3 lightning forks peel off the crescent edge; 12 gold sparks; 6 steel shards. | Medium+ (×0.5 on Medium) |
| Ground layer | 250–1,400 | `vfx_ground_cracks`, `vfx_fb_dust` | An arc-masked crack along the swing and dust puffs. | all tiers |
| After-effect | 400–1,200 | `vfx_motes` | Blue haze cools; Charged crackle markers appear on hit enemies. | Medium+ |
| Light | 250–600 | pooled `PointLight` | #8FD0FF, range 7 m, 0 → 4 → 0, peak at 290 ms. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Note:** Keeps the existing arc_slash contract (45 damage, 3 targets, 4 m, 120°, 250/100/350, 5 s). The 250 ms release is 7.5 frames: put the event at 250 ms and author the contact pose on f8.

#### 01.2 `h01_bladeward_nova` · วงดาบพิทักษ์ · Bladeward Nova
*Skill 2 · control + damage · VFX preset `xs_bladeward_nova` · reuses `xs_bladeward_nova` · budget class heroic*

Twelve spectral swords erupt around the orc, knock enemies up and taunt them onto him.

| Field | Spec |
|---|---|
| Targeting · telegraph | self AoE · **AREA ring** r 4 m (radial wipe over the 150 ms cast) |
| Range · radius | self · r 4 m · knock-up 0.4 m · taunt 3,000 ms |
| Timing | 200 / 100 / 300 ms · **release f6** (200 ms) · clip `swordsman.skill_nova` 600 ms (18 f) |
| Clip events (ms) | charge_start 0, plant 150, hit 200 |
| Cooldown · cost · power | 9 s · 16 SP · 35 · physical · element `storm` |
| Effects | knock-up 0.4 m; Taunted 3 s (bosses: threat ×3 for 3 s) |
| Status → combo | Charged 6 s → C1 Lodestone Snap (+ Anchored from 02); C4 Rainlash (+ Soaked from 04) |
| Palette | core `#F4FBFF` · body `#7FD3FF` · edge `#2B6CFF` · accent `#FFC94A` · scorch `#0E1F4D` |
| Peak coverage | 22 % at the 13 m camera |
| SFX | `sfx.h01.bladeward_nova` · .plant / .erupt / .taunt_roar |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–150 | `vfx_rune_ring_blade`, `vfx_motes` | The sword-notched ring draws clockwise at r 4.0 m; 16 charge sparks spiral from the ring into the hilt. | Medium+ |
| Mesh core | 150–1,200 | `vfx_spectral_blade` | 12 spectral blades, scaled 1.3 to 2.7 m for Look v2, rise at radii 2.9 / 3.5 m, staggered clockwise, with a fresnel rim, a glowing fuller and gold guards; erode tip → hilt from 700 ms. Hand-off upgrade #1: restore the full ring at the live camera. | all tiers |
| Secondaries | 150–900 | `vfx_fb_dust`, `vfx_shards`, `vfx_fb_lightning` | Dust puffs at the blade bases, shards thrown out, and 4-6 lightning arcs between neighbouring blades (260-700 ms). | Medium+ (×0.5 on Medium) |
| Ground layer | 150–2,500 | `vfx_impact_star`, `vfx_shock_ring`, `vfx_ring_wall`, `vfx_ground_cracks` | A 3.2 m ground flash, a shock ring and 0.6 m ring wall r 0.5 → 4.6 m, and base cracks per blade cooling to #0E1F4D. | all tiers |
| After-effect | 260–1,500 | `vfx_fb_dust` | Frost-blue mist cards drifting outward. | Medium+ |
| Light | 150–600 | pooled `PointLight` | #8FD0FF, range 9 m, peak 6 at 190 ms. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** Blades stand on the 2.9-3.5 m perimeter; the orc and the taunted enemies inside stay readable.

#### 01.3 `h01_ironfall_cleave` · ผ่าเหล็กถล่ม · Ironfall Cleave
*Skill 3 · debuff + damage · VFX preset `xs_h01_ironfall_cleave` · budget class heroic*

A two-handed overhead cleave that splits the ground in a 5 m line, staggers, breaks guards and Cracks armour.

| Field | Spec |
|---|---|
| Targeting · telegraph | line from the caster (guard-breaker) · **HEAVY lane** 1.6 × 5 m |
| Range · radius | range 5 m |
| Timing | 333 / 100 / 400 ms · **release f10** (333 ms) · clip `swordsman.skill_ironfall` 833 ms (25 f) |
| Clip events (ms) | swing_start 0, trail_on 300, hit 333, trail_off 433 |
| Cooldown · cost · power | 8 s · 14 SP · 70 · heavy · physical · element `storm` |
| Effects | stagger; cannot be guarded |
| Status → combo | Cracked 6 s → C7 Faultline (+ Marked from 03) |
| Palette | core `#F4FBFF` · body `#7FD3FF` · edge `#2B6CFF` · accent `#FFC94A` |
| Peak coverage | 15 % at the 13 m camera |
| SFX | `sfx.h01.ironfall_cleave` · .lift / .slam / .crack |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–333 | `vfx_motes` | The sword lifts two-handed; gold light runs down the fuller; grit lifts off the ground along the lane. | Medium+ |
| Mesh core | 333–500 | `vfx_crescent_slash`, `vfx_spectral_blade` | A tall vertical 180° crescent (3 m) and a falling spectral blade ghost (×1.4) slam down at 333 ms. | all tiers |
| Secondaries | 333–900 | `vfx_shards`, `vfx_motes`, `vfx_fb_dust` | Rock chunks (earth-tinted shards), a spark burst, and dust walls along both sides of the split. | Medium+ (×0.5 on Medium) |
| Ground layer | 333–2,000 | `vfx_ground_split` | A 5 m ground split with a cyan-gold emissive seam cooling to scorch. | all tiers |
| After-effect | 500–1,500 | `vfx_motes` | Seam embers and settling dust; Cracked shard markers orbit hit enemies. | Medium+ |
| Light | 333–600 | pooled `PointLight` | #FFC94A, range 6 m, 0 → 5 → 0. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 01.4 `h01_compass_rush` · พุ่งทะลวงเข็มทิศ · Compass Rush
*Skill 4 · mobility · VFX preset `xs_h01_compass_rush` · budget class heroic*

Behind a spectral compass shield the orc charges 8 m, shouldering enemies aside; he stops at the first elite or boss and staggers it.

| Field | Spec |
|---|---|
| Targeting · telegraph | dash · **AREA lane** 2 × 8 m |
| Range · radius | range 8 m · dash 400 ms |
| Timing | 133 / 400 / 233 ms · **release f4** (133 ms) · clip `swordsman.skill_rush` 767 ms (23 f) |
| Clip events (ms) | whoosh 0, release 133, hit 300 |
| Cooldown · cost · power | 10 s · 12 SP · 30 · physical · element `storm` |
| Effects | -30 % damage taken during the dash; stops at elites and bosses and staggers them |
| Status → combo | none |
| Palette | core `#FFF6DA` · body `#FFC94A` · edge `#2B6CFF` · accent `#7FD3FF` |
| Peak coverage | 15 % at the 13 m camera |
| SFX | `sfx.h01.compass_rush` · .brace / .charge_loop / .impact |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–133 | `vfx_shield_sigil`, `vfx_motes` | A compass-star shield sigil (2 m) blooms in front; 8 gold motes snap into its points. | Medium+ |
| Mesh core | 133–533 | `vfx_shield_sigil`, `vfx_cone_burst` | The sigil leads the charge with a gold → blue bow wave. | all tiers |
| Secondaries | 133–600 | `vfx_motes`, `vfx_streak` | Pauldron ribbons (2 TrailMesh), ground-skid sparks, dust streaks. | Medium+ (×0.5 on Medium) |
| Ground layer | 133–1,400 | `vfx_ground_split`, `vfx_fb_dust` | Two parallel scorched skid lines and dust puffs. | all tiers |
| After-effect | 533–1,300 | `vfx_shards` | The sigil breaks into 8 gold shards that fade as the dust settles. | Medium+ |
| Light | 133–533 | pooled `PointLight` | #FFC94A, range 5 m, travelling. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 01.5 `h01_eightfold_ward` · ปราการแปดทิศ · Eightfold Ward
*Skill 5 · buff · VFX preset `xs_h01_eightfold_ward` · budget class heroic*

He plants the sword: eight spectral shields circle a 5 m compass, and allies inside take 25 % less damage for 6 s.

| Field | Spec |
|---|---|
| Targeting · telegraph | zone at the cast spot · **SAFE ring** r 5 m |
| Range · radius | self · r 5 m · zone 6,000 ms |
| Timing | 300 / 100 / 300 ms · **release f9** (300 ms) · clip `swordsman.skill_ward` 700 ms (21 f) |
| Zone / follow-up | 300-6300 ms |
| Clip events (ms) | charge_start 0, plant 300 |
| Cooldown · cost · power | 20 s · 20 SP · - · none · element `storm` |
| Effects | allies inside: -25 % damage taken for 6 s |
| Status → combo | none |
| Palette | core `#FFF6DA` · body `#FFC94A` · edge `#2B6CFF` · accent `#7FD3FF` |
| Peak coverage | 22 % at the 13 m camera |
| SFX | `sfx.h01.eightfold_ward` · .plant / .hum_loop / .shield_flare / .end |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–300 | `vfx_ring_wall` | The sword plants; 8 thin gold light pillars rise at the compass points. | Medium+ |
| Mesh core | 300–6,300 | `vfx_shield_sigil` | 8 shield sigils (1.4 m) orbit the 5 m ring at 15°/s; when an ally inside is hit, the nearest shield flares. | all tiers |
| Secondaries | 300–6,300 | `vfx_motes`, `vfx_fb_lightning` | Gold motes rising along the rim; slow gold threads linking neighbouring shields. | Medium+ (×0.5 on Medium) |
| Ground layer | 300–6,300 | `vfx_rune_compass` | An eight-point compass decal r 5 m, slowly turning. | all tiers |
| After-effect | 6,300–7,300 | `vfx_shock_ring`, `vfx_motes` | The shields fold into the ground with a ring wave and motes. | Medium+ |
| Light | 300–700 | pooled `PointLight` | #FFC94A, range 8 m flash at the cast only (protects the light pool). | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** Shields stand on the perimeter; the centre stays clear for allies.

#### 01.6 `h01_stormfall_cleave` · ดาบพายุถล่มฟ้า · Stormfall Cleave
*Skill 6 · ultimate + damage · VFX preset `xs_h01_stormfall_cleave` · budget class ultimate*

The orc leaps, calls the storm into a 6 m spectral greatsword and brings it down along a 10 m line that ends in a thunder crater.

| Field | Spec |
|---|---|
| Targeting · telegraph | line from the caster + crater · **HEAVY lane** 3 × 10 m; then a HEAVY ring r 4 m at the far end of the lane |
| Range · radius | range 10 m · r 4 m |
| Timing | 667 / 200 / 500 ms · **release f20** (667 ms) · clip `swordsman.skill_stormfall` 1,367 ms (41 f) |
| Clip events (ms) | charge_start 0, takeoff 300, hit 667, land 700 |
| Cooldown · cost · power | 80 s · 40 SP · 200 line + 80 crater · heavy · physical · element `storm` |
| Effects | knock-down 1.0 s (non-boss) |
| Status → combo | Charged 6 s → C1 Lodestone Snap (+ Anchored from 02); C4 Rainlash (+ Soaked from 04) · Cracked 6 s → C7 Faultline (+ Marked from 03) |
| Palette | core `#F4FBFF` · body `#7FD3FF` · edge `#2B6CFF` · accent `#FFC94A` · dark `#0E1F4D` |
| Peak coverage | 42 % at the 13 m camera |
| SFX | `sfx.h01.stormfall_cleave` · .gather / .leap / .slam / .thunder_tail |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–667 | `vfx_fb_cloud`, `vfx_rune_compass`, `vfx_fb_lightning` | A storm-cloud disc forms 8 m above the line; the compass ring flashes under him; lightning crawls up the sword as he leaps 1.5 m. | Medium+ |
| Mesh core | 667–1,100 | `vfx_spectral_blade`, `vfx_impact_star` | A 6 m spectral greatsword (vfx_spectral_blade ×3) falls along the line; a 6 m crater flash at 700 ms. | all tiers |
| Secondaries | 667–1,600 | `vfx_fb_lightning`, `vfx_shards`, `vfx_motes` | 6 vertical bolts strike along the line, debris and gold sparks (GPU 800 on Epic). | Medium+ (×0.5 on Medium) |
| Ground layer | 667–3,000 | `vfx_ground_split`, `vfx_ground_cracks`, `vfx_shock_ring`, `vfx_scorch` | A 10 m ground split, crater cracks, a shock ring r 0 → 5 m and scorch. | all tiers |
| After-effect | 1,100–3,000 | `vfx_fb_lightning`, `vfx_fb_smoke` | Static arcs crawl over the scorched line for 1.5 s; blue smoke; embers. | Medium+ |
| Light | 667–1,200 | pooled `PointLight` | #8FD0FF, range 14 m, 0 → 9 → 0. | High+ |
| Distortion | 700–900 | post | Shock-ring heat shimmer. | Epic only |

**Tiers:** Epic adds distortion. Medium: same shapes and palette; drops light, distortion; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

### 4.3 Hero 05: Rogue Thief · โจร

| Field | Spec |
|---|---|
| Party role | **Melee DPS** (DPS ประชิด) |
| Party job | Single-target burst (Adder's Kiss, Fangfall), threat drop for allies (Nightbloom Smoke), and primes Venom and Shadowed. |
| Element | Shadow and venom |
| Palette (shadow magenta-plum + venom lime) | core `#FFE6F6` · body `#C83C9E` · edge `#5E1150` · accent `#B6F23A` |
| Shape language | Diamonds (his cape's diamond-cut hem), X-crosses, thin crescents, smoke petals and drips. Sharp, quick, low to the ground. |
| Statuses | Venom (พิษ), Shadowed (เงาครอบ) |
| Combos | C2 Needlefrost (with 02); C5 Rahu's Bite (with 04); C8 Plaguewind (with 03) |
| Weapon | Curved dagger ×2 (purple gem); off-hand is a mirrored copy · Tripo P2.0 single image · 0.40 m → 0.48 m (+20 %) |
| Sockets | socket_weapon_R and socket_weapon_L (forward and reverse grips), sheaths on socket_hip_L / socket_hip_R |
| Trail and VFX markers | grip origin, +Y; fx_base, fx_tip (the runtime adds _R / _L per socket). two thin ribbons, one per dagger (fx_base → fx_tip, 8 segments, 100 ms), magenta core → plum edge with a lime rim while Venom is up (cosmetic). |
| Rig sets | base + dual_dagger + thief · display_scale 0.989 · crown 1.78 m |

| Slot | Id | Thai / English | Type | Telegraph | Range / radius | Timing (w / a / r) · release | CD · SP | Status → combo |
|---|---|---|---|---|---|---|---|---|
| basic | `h05_basic` | ฟันสนธยา / Dusk Cuts | damage | **none (target bracket only)** | range 2.5 m · 80° | 67 / 60 / 273 · f2 | 0.4 s · 0 | none |
| 1 | `h05_adders_kiss` | จุมพิตอสรพิษ / Adder's Kiss | damage | **TARGET brackets** | range 2.5 m | 133 / 100 / 267 · f4 | 4 s · 8 | Venom 6 s → C2 Needlefrost (+ Chilled from 02); C8 Plaguewind (+ Gusted from 03) |
| 2 | `h05_diamond_scatter` | พายุมีดเพชร / Diamond Scatter | damage | **AREA fan** r 8 m, 70° | range 8 m | 200 / 67 / 300 · f6 | 7 s · 14 | Venom 6 s → C2 Needlefrost (+ Chilled from 02); C8 Plaguewind (+ Gusted from 03) |
| 3 | `h05_fangfall` | เขี้ยวปลิดชีพ / Fangfall | damage | **TARGET brackets** | range 2.5 m | 200 / 100 / 367 · f6 | 10 s · 16 | consumes Venom (no new status) |
| 4 | `h05_duskstep` | ก้าวสนธยา / Duskstep | mobility | **AREA lane** 1.5 × 6 m | range 6 m · dash 200 ms | 67 / 200 / 200 · f2 | 8 s · 10 | Shadowed 5 s → C5 Rahu's Bite (+ Sunlit from 04) |
| 5 | `h05_nightbloom_smoke` | ควันบุปผาราตรี / Nightbloom Smoke | control | **AREA ring** r 4 m | range 10 m · r 4 m · zone 4,000 ms | 233 / 67 / 267 · f7 | 16 s · 18 | Shadowed 5 s → C5 Rahu's Bite (+ Sunlit from 04) |
| 6 | `h05_violet_masquerade` | ระบำหน้ากากม่วง / Violet Masquerade | ultimate + damage | **HEAVY ring** r 8 m | range 8 m · r 8 m | 300 / 1500 / 400 · f9 | 80 s · 40 | Venom → C2, C8; Shadowed → C5 |

#### 05.0 `h05_basic` · ฟันสนธยา · Dusk Cuts
*Basic attack · damage · VFX preset `xs_h05_basic` · budget class basic*

Right then left: two fast reverse-grip cuts.

| Field | Spec |
|---|---|
| Targeting · telegraph | melee fan 2.5 m, 80° · **none (target bracket only)** |
| Range · radius | range 2.5 m · 80° |
| Timing | 67 / 60 / 273 ms · **release f2** (67 ms) · clip `dual_dagger.attack_1 (R) / dual_dagger.attack_2 (L)` 400 ms (12 f) |
| Clip events (ms) | swing_start 0, trail_on 33, hit 67, trail_off 133, link_open 400 |
| Cooldown · cost · power | 0.4 s · 0 SP · 25 per link (12 + 13) · physical · element `shadow_venom` |
| Status → combo | none |
| Palette | core `#FFE6F6` · body `#C83C9E` · edge `#5E1150` · accent `#B6F23A` |
| Peak coverage | 3 % at the 13 m camera |
| SFX | `sfx.h05.basic` · .slice / .impact |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–67 | `vfx_motes` | A plum glint on the leading blade. | Medium+ |
| Mesh core | 67–170 | `vfx_crescent_slash` | A thin dagger ribbon per hand (100 ms; magenta core → plum edge, lime rim). | all tiers |
| Secondaries | hit → hit+200 | `vfx_motes`, `vfx_crescent_slash` | 4 sparks and a small X-diamond slash mark. | Medium+ (×0.5 on Medium) |
| Ground layer | hit → hit+300 | `vfx_fb_dust` | A tiny dust tick on link 2. | Medium+ |
| After-effect | hit → hit+250 | `vfx_fb_smoke` | One plum smoke wisp. | High+ |

**Tiers:** Medium: same shapes and palette; drops after-effect; secondaries ×0.5. Low: mesh core + telegraph; no light.

#### 05.1 `h05_adders_kiss` · จุมพิตอสรพิษ · Adder's Kiss
*Skill 1 · damage · VFX preset `xs_h05_adders_kiss` · budget class heroic*

A double stab that injects Venom: one stack, or two from behind.

| Field | Spec |
|---|---|
| Targeting · telegraph | single target, melee 2.5 m · **TARGET brackets** |
| Range · radius | range 2.5 m |
| Timing | 133 / 100 / 267 ms · **release f4** (133 ms) · clip `thief.skill_kiss` 500 ms (15 f) |
| Clip events (ms) | swing_start 0, hit 133, hit 233 |
| Cooldown · cost · power | 4 s · 8 SP · 50 · physical · element `shadow_venom` |
| Effects | Venom +1 (+2 from behind) |
| Status → combo | Venom 6 s → C2 Needlefrost (+ Chilled from 02); C8 Plaguewind (+ Gusted from 03) |
| Palette | core `#FFE6F6` · body `#C83C9E` · edge `#5E1150` · accent `#B6F23A` |
| Peak coverage | 10 % at the 13 m camera |
| SFX | `sfx.h05.adders_kiss` · .stab / .stab / .venom_hiss |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–133 | `vfx_motes` | Lime venom beads run along both blades. | Medium+ |
| Mesh core | 133–300 | `vfx_crescent_slash` | A crossed pair of thin crescents (X-diamond) at the target, magenta-plum. | all tiers |
| Secondaries | 133–600 | `vfx_fb_splash`, `vfx_motes` | A small lime droplet spray and 8 bubbles. | Medium+ (×0.5 on Medium) |
| Ground layer | 133–1,500 | `vfx_liquid_pool` | A 0.9 m lime splatter under the target. | all tiers |
| After-effect | 300–1,300 | `vfx_motes` | Venom drips and pips on the target; green bubbles rising. | Medium+ |

**Tiers:** Medium: same shapes and palette; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Note:** Small and frequent: no PointLight (emissive splatter flash instead). Coverage 10 % is below the heroic floor on purpose (single target; D4).

#### 05.2 `h05_diamond_scatter` · พายุมีดเพชร · Diamond Scatter
*Skill 2 · damage · VFX preset `xs_h05_diamond_scatter` · budget class heroic*

Six venom-coated diamond knives fan across a 70° cone.

| Field | Spec |
|---|---|
| Targeting · telegraph | cone 8 m, 70° · **AREA fan** r 8 m, 70° |
| Range · radius | range 8 m |
| Timing | 200 / 67 / 300 ms · **release f6** (200 ms) · clip `thief.skill_scatter` 567 ms (17 f) |
| Clip events (ms) | charge_start 0, release 200 |
| Cooldown · cost · power | 7 s · 14 SP · 6 × 28 (max 2 knives per target) · physical · element `shadow_venom` |
| Effects | Venom +1 per knife hit (max +2 per cast per target) |
| Status → combo | Venom 6 s → C2 Needlefrost (+ Chilled from 02); C8 Plaguewind (+ Gusted from 03) |
| Palette | core `#FFE6F6` · body `#C83C9E` · edge `#5E1150` · accent `#B6F23A` |
| Peak coverage | 16 % at the 13 m camera |
| SFX | `sfx.h05.diamond_scatter` · .fan / .throw / .thunk |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–200 | `vfx_diamond_knife`, `vfx_motes` | Six knives fan between his fingers with glints; lime drips. | Medium+ |
| Mesh core | 200–500 | `vfx_diamond_knife` | 6 spinning diamond knives with thin magenta ribbons. | all tiers |
| Secondaries | 200–700 | `vfx_motes`, `vfx_fb_splash` | Lime droplets, sparks at impacts, diamond glints. | Medium+ (×0.5 on Medium) |
| Ground layer | 200–1,500 | `vfx_liquid_pool` | Six small diamond knife marks and a fan-shaped lime splatter. | all tiers |
| After-effect | 500–1,500 | `vfx_motes` | Venom bubbles on hit targets; the marks fade. | Medium+ |
| Light | 200–400 | pooled `PointLight` | #C83C9E, range 6 m, 0 → 3 → 0. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 05.3 `h05_fangfall` · เขี้ยวปลิดชีพ · Fangfall
*Skill 3 · damage · VFX preset `xs_h05_fangfall` · budget class heroic*

A leaping cross-cut that detonates every Venom stack on the target; brutal on wounded prey.

| Field | Spec |
|---|---|
| Targeting · telegraph | single target, melee 2.5 m · **TARGET brackets** |
| Range · radius | range 2.5 m |
| Timing | 200 / 100 / 367 ms · **release f6** (200 ms) · clip `thief.skill_fangfall` 667 ms (20 f) |
| Clip events (ms) | takeoff 0, hit 200 |
| Cooldown · cost · power | 10 s · 16 SP · 40 + 45 per consumed Venom stack; ×1.5 below 30 % HP (non-boss) · heavy · physical · element `shadow_venom` |
| Effects | consumes Venom (this prevents Needlefrost and Plaguewind: a choice) |
| Status → combo | consumes Venom (no new status) |
| Palette | core `#FFE6F6` · body `#C83C9E` · edge `#5E1150` · accent `#B6F23A` |
| Peak coverage | 14 % at the 13 m camera |
| SFX | `sfx.h05.fangfall` · .leap / .cross_cut / .venom_pop |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–200 | `vfx_motes` | The blades cross overhead; lime venom swirls up both arms. | Medium+ |
| Mesh core | 200–400 | `vfx_crescent_slash`, `vfx_impact_star` | A large X-diamond slash (2 × 120°, 2 m) and a vertical fang spike. | all tiers |
| Secondaries | 200–700 | `vfx_fb_splash`, `vfx_motes` | A venom burst scaled by stacks (1-3 rings of lime droplets) and magenta sparks. | Medium+ (×0.5 on Medium) |
| Ground layer | 200–1,500 | `vfx_liquid_pool` | A diamond splatter r 1.2 m. | all tiers |
| After-effect | 400–1,200 | `vfx_fb_smoke` | A lime mist lingers. | Medium+ |
| Light | 200–500 | pooled `PointLight` | #B6F23A, range 6 m, 0 → 4 → 0. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** Coverage grows +3 % per consumed stack, so a big detonation reads as big.
**Note:** Coverage 14 % (up to 20 % with 3 stacks); single target (D4).

#### 05.4 `h05_duskstep` · ก้าวสนธยา · Duskstep
*Skill 4 · mobility · VFX preset `xs_h05_duskstep` · budget class heroic*

A 6 m smoke dash through enemies; everyone passed is Shadowed, and ending behind a target sets up a from-behind Adder's Kiss.

| Field | Spec |
|---|---|
| Targeting · telegraph | dash · **AREA lane** 1.5 × 6 m |
| Range · radius | range 6 m · dash 200 ms |
| Timing | 67 / 200 / 200 ms · **release f2** (67 ms) · clip `thief.skill_duskstep` 467 ms (14 f) |
| Clip events (ms) | whoosh 0, release 67 |
| Cooldown · cost · power | 8 s · 10 SP · 15 · physical · element `shadow_venom` |
| Effects | untargetable during the 200 ms dash |
| Status → combo | Shadowed 5 s → C5 Rahu's Bite (+ Sunlit from 04) |
| Palette | core `#FFE6F6` · body `#C83C9E` · edge `#5E1150` · accent `#B6F23A` |
| Peak coverage | 15 % at the 13 m camera |
| SFX | `sfx.h05.duskstep` · .vanish / .whoosh / .appear |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–67 | `vfx_fb_smoke` | His silhouette smears; plum smoke gathers at the feet. | Medium+ |
| Mesh core | 67–267 | `vfx_fb_smoke` | A wide plum smoke ribbon (1 m TrailMesh) with diamond smoke puffs at the start and end. | all tiers |
| Secondaries | 67–600 | `vfx_motes` | Diamond smoke petals and lime sparks. | Medium+ (×0.5 on Medium) |
| Ground layer | 67–1,300 | `vfx_streak` | A plum shadow streak along the path (alpha-blended, value-lifted). | all tiers |
| After-effect | 267–1,300 | `vfx_fb_smoke` | Lingering smoke wisps; Shadowed wisps trail from the passed enemies. | Medium+ |

**Tiers:** Medium: same shapes and palette; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 05.5 `h05_nightbloom_smoke` · ควันบุปผาราตรี · Nightbloom Smoke
*Skill 5 · control · VFX preset `xs_h05_nightbloom_smoke` · budget class heroic*

A bomb blooms into a 4 m flower of plum smoke for 4 s: enemies inside are Shadowed and slowed; allies inside shed threat.

| Field | Spec |
|---|---|
| Targeting · telegraph | ground target within 10 m · **AREA ring** r 4 m |
| Range · radius | range 10 m · r 4 m · zone 4,000 ms |
| Timing | 233 / 67 / 267 ms · **release f7** (233 ms) · clip `thief.skill_smoke` 567 ms (17 f) |
| Zone / follow-up | 633-4633 ms |
| Clip events (ms) | charge_start 0, release 233 |
| Cooldown · cost · power | 16 s · 18 SP · - · none · element `shadow_venom` |
| Effects | enemies inside: -25 % move speed; allies inside: -50 % threat generated |
| Status → combo | Shadowed 5 s → C5 Rahu's Bite (+ Sunlit from 04) |
| Palette | core `#FFE6F6` · body `#C83C9E` · edge `#5E1150` · accent `#B6F23A` |
| Peak coverage | 26 % at the 13 m camera |
| SFX | `sfx.h05.nightbloom_smoke` · .throw / .bloom / .smoke_loop |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–633 | `vfx_flask`, `vfx_fb_smoke` | A plum smoke bomb (vfx_flask, plum ramp) arcs to the point, trailing smoke. | Medium+ |
| Mesh core | 633–4,633 | `vfx_fb_smoke` | 8 smoke petals unfold from the impact around a central bloom with a magenta core. | all tiers |
| Secondaries | 633–4,633 | `vfx_motes` | Magenta glitter, lime pollen sparks, swirling wisps. | Medium+ (×0.5 on Medium) |
| Ground layer | 633–4,633 | `vfx_rune_diamond` | A shadow-flower decal r 4 m (alpha-blended plum, value-lifted). | all tiers |
| After-effect | 4,633–5,600 | `vfx_motes` | The petals dissolve into motes. | Medium+ |
| Light | 633–900 | pooled `PointLight` | #C83C9E, range 7 m burst. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** Smoke stays ≤ 1.2 m tall at alpha ≤ 0.45: heads, nameplates and the amber ring stay visible.

#### 05.6 `h05_violet_masquerade` · ระบำหน้ากากม่วง · Violet Masquerade
*Skill 6 · ultimate + damage · VFX preset `xs_h05_violet_masquerade` · budget class ultimate*

He vanishes behind a diamond mask and blinks between up to six enemies within 8 m, cutting each twice, then reappears in a diamond burst.

| Field | Spec |
|---|---|
| Targeting · telegraph | self-centred, up to 6 enemies within 8 m · **HEAVY ring** r 8 m |
| Range · radius | range 8 m · r 8 m |
| Timing | 300 / 1500 / 400 ms · **release f9** (300 ms) · clip `thief.skill_masquerade` 2,200 ms (66 f) |
| Clip events (ms) | charge_start 0, hit 300, hit 550, hit 800, hit 1050, hit 1300, hit 1550, hit 1800 |
| Cooldown · cost · power | 80 s · 40 SP · 6 × 2 x 50 + 60 finale · heavy · physical · element `shadow_venom` |
| Effects | untargetable during the active phase |
| Status → combo | Venom ×2 6 s → C2 Needlefrost (+ Chilled from 02); C8 Plaguewind (+ Gusted from 03) · Shadowed 5 s → C5 Rahu's Bite (+ Sunlit from 04) |
| Palette | core `#FFE6F6` · body `#C83C9E` · edge `#5E1150` · accent `#B6F23A` |
| Peak coverage | 38 % at the 13 m camera |
| SFX | `sfx.h05.violet_masquerade` · .mask / .blink / .cut / .finale |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–300 | `vfx_sigil_atlas`, `vfx_shards`, `vfx_fb_smoke` | A diamond mask glyph flashes; the cape bursts into diamond shards; smoke engulfs him. | Medium+ |
| Mesh core | 300–1,800 | `vfx_crescent_slash`, `vfx_fb_smoke` | At each victim an X-diamond slash pair and a smoke-blink portal; an afterimage ribbon (TrailMesh path) links the blink points. | all tiers |
| Secondaries | 300–1,800 | `vfx_motes`, `vfx_fb_splash` | Lime venom spray, magenta petals, plum glitter. | Medium+ (×0.5 on Medium) |
| Ground layer | 0–3,000 | `vfx_rune_diamond`, `vfx_liquid_pool` | A diamond rune circle r 8 m and a splatter under each victim. | all tiers |
| After-effect | 1,800–3,300 | `vfx_shock_ring`, `vfx_diamond_knife`, `vfx_motes` | The finale diamond burst: a shock ring r 0 → 3 m and 8 diamond knives flung outward, then falling smoke petals and motes. | all tiers |
| Light | 300–1,900 | pooled `PointLight` | #C83C9E, range 6 m: one pooled light hopping with each strike. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer, after-effect + telegraph; no light.

### 4.4 Hero 06: Tinker Merchant · ช่างกลพ่อค้า

| Field | Spec |
|---|---|
| Party role | **Utility** (ยูทิลิตี้) |
| Party job | Zone control and deployables (Grease Flask, Cog Sentry pulls threat, Mending Anvil armours the party) and primes Oiled and Scorched. |
| Element | Forge and steam (heat, oil, clockwork) |
| Palette (molten orange + brass + lens teal) | core `#FFE7A3` · body `#FF7A1A` · edge `#C2361B` · brass `#D9A441` · accent `#2FD4C4` · steam `#E6EEF0` |
| Shape language | Gears and cog teeth (her choker and studs), rivets, pistons, steam puffs, sparks, hex nuts. Chunky, mechanical, stepped. |
| Statuses | Oiled (เปื้อนน้ำมัน), Scorched (ไหม้เกรียม) |
| Combos | C3 Steamburst (with 02); C6 Slipslick (with 04) |
| Weapon | Wrench-head war hammer (brass and steel) · Tripo P2.0 single image (the 3/4 view is accepted) · 0.90 m → 1.08 m (+20 %) |
| Sockets | socket_weapon_R (hammer; socket_weapon_L for two-handed swings), wrench prop on socket_hip_R, socket_back |
| Trail and VFX markers | grip origin, +Y; fx_base (haft collar), fx_tip (striking face), fx_head (head centre = spark and steam origin). chunky arc ribbon fx_base → fx_tip (12 segments, 180 ms), orange core → brass edge; a heat-glow uniform on the head during Forgeheart Slam. |
| Rig sets | base + heavy_1h + merchant · display_scale 0.956 · crown 1.72 m |

| Slot | Id | Thai / English | Type | Telegraph | Range / radius | Timing (w / a / r) · release | CD · SP | Status → combo |
|---|---|---|---|---|---|---|---|---|
| basic | `h06_basic` | ประแจกระหน่ำ / Wrench & Clang | damage | **none (target bracket only)** | range 3 m · 100° | 100 / 60 / 200 · f3 | 0.4 s · 0 | none |
| 1 | `h06_forgeheart_slam` | ทุบหัวใจเตาหลอม / Forgeheart Slam | damage | **AREA ring** r 2.5 m | range 1.5 m · r 2.5 m | 267 / 100 / 333 · f8 | 5 s · 10 | Scorched 4 s → C3 Steamburst (+ Chilled from 02) |
| 2 | `h06_grease_flask` | ขวดจาระบี / Grease Flask | debuff + control | **AREA ring** r 3.5 m | range 12 m · r 3.5 m · zone 6,000 ms | 233 / 67 / 267 · f7 | 10 s · 14 | Oiled 8 s → C6 Slipslick (+ Soaked from 04) |
| 3 | `h06_cog_sentry` | ป้อมเฟืองยาม / Cog Sentry | damage | **CAST ring** r 1 m | range 6 m · sentry range 10 m | 400 / 67 / 300 · f12 | 18 s · 18 | none |
| 4 | `h06_boiler_leap` | กระโดดหม้อไอน้ำ / Boiler Leap | mobility | **AREA ring** r 2.5 m | range 8 m · r 2.5 m · knockback 1 m · airborne 600 ms | 133 / 600 / 200 · f4 | 11 s · 12 | none |
| 5 | `h06_mending_anvil` | ทั่งซ่อมสนาม / Mending Anvil | buff | **SAFE ring** r 5 m | range 6 m · r 5 m · zone 10,000 ms | 467 / 67 / 366 · f14 | 24 s · 22 | none |
| 6 | `h06_gearstorm_hammerfall` | ค้อนพายุเฟือง / Gearstorm Hammerfall | ultimate + damage | **HEAVY ring** r 6 m | range 14 m · r 6 m | 400 / 67 / 400 · f12 | 85 s · 40 | Scorched → C3; Oiled → C6 |

#### 06.0 `h06_basic` · ประแจกระหน่ำ · Wrench & Clang
*Basic attack · damage · VFX preset `xs_h06_basic` · budget class basic*

Two chunky two-handed swings of the wrench-hammer.

| Field | Spec |
|---|---|
| Targeting · telegraph | melee fan 3 m, 100° · **none (target bracket only)** |
| Range · radius | range 3 m · 100° |
| Timing | 100 / 60 / 200 ms · **release f3** (100 ms) · clip `heavy_1h.attack_1 / heavy_1h.attack_2` 400 ms (12 f) |
| Clip events (ms) | swing_start 0, trail_on 67, hit 100, trail_off 167, link_open 400 |
| Cooldown · cost · power | 0.4 s · 0 SP · 25 per link · physical · element `forge` |
| Status → combo | none |
| Palette | core `#FFE7A3` · body `#FF7A1A` · edge `#C2361B` · accent `#2FD4C4` |
| Peak coverage | 4 % at the 13 m camera |
| SFX | `sfx.h06.basic` · .swing / .clang |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–100 | `vfx_motes` | The hammer head flushes brass → warm orange (emissive uniform). | Medium+ |
| Mesh core | 100–280 | `vfx_crescent_slash` | A chunky arc ribbon (orange core → brass edge, 180 ms). | all tiers |
| Secondaries | hit → hit+250 | `vfx_motes` | 8 forge sparks and a gear-shaped glint. | Medium+ (×0.5 on Medium) |
| Ground layer | hit → hit+600 | `vfx_scorch` | A 0.6 m scorch tap mark on link 2. | Medium+ |
| After-effect | hit → hit+300 | `vfx_fb_smoke` | A soot puff. | High+ |

**Tiers:** Medium: same shapes and palette; drops after-effect; secondaries ×0.5. Low: mesh core + telegraph; no light.

#### 06.1 `h06_forgeheart_slam` · ทุบหัวใจเตาหลอม · Forgeheart Slam
*Skill 1 · damage · VFX preset `xs_h06_forgeheart_slam` · budget class heroic*

The hammer head glows forge-hot and slams a 2.5 m gear-shock that Scorches.

| Field | Spec |
|---|---|
| Targeting · telegraph | circle 2.5 m centred 1.5 m in front · **AREA ring** r 2.5 m |
| Range · radius | range 1.5 m · r 2.5 m |
| Timing | 267 / 100 / 333 ms · **release f8** (267 ms) · clip `merchant.skill_slam` 700 ms (21 f) |
| Clip events (ms) | swing_start 0, trail_on 233, hit 267, trail_off 367 |
| Cooldown · cost · power | 5 s · 10 SP · 55 · heavy · physical · element `forge` |
| Effects | stagger |
| Status → combo | Scorched 4 s → C3 Steamburst (+ Chilled from 02) |
| Palette | core `#FFE7A3` · body `#FF7A1A` · edge `#C2361B` · accent `#2FD4C4` |
| Peak coverage | 17 % at the 13 m camera |
| SFX | `sfx.h06.forgeheart_slam` · .heat_hiss / .slam / .clang_ring |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–267 | `vfx_fb_smoke`, `vfx_motes` | The head heats brass → glowing orange; 3 steam jets from the vents; sparks drip. | Medium+ |
| Mesh core | 267–450 | `vfx_impact_star`, `vfx_gear_ring` | An orange anvil-star flash and a gear-tooth shock ring r 0 → 2.5 m. | all tiers |
| Secondaries | 267–900 | `vfx_motes`, `vfx_shards`, `vfx_fb_smoke` | A forge-spark fountain (GPU 600 on High, 120 CPU), ember chunks, steam puffs. | Medium+ (×0.5 on Medium) |
| Ground layer | 267–2,500 | `vfx_scorch`, `vfx_ground_cracks` | A soot-and-orange scorch with molten cracks cooling. | all tiers |
| After-effect | 450–1,500 | `vfx_fb_smoke`, `vfx_fb_flame`, `vfx_motes` | Soot smoke, small flames licking the scorch, embers; heat shimmer on High. | Medium+ |
| Light | 267–600 | pooled `PointLight` | #FF8A3D, range 7 m, 0 → 5 → 0. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 06.2 `h06_grease_flask` · ขวดจาระบี · Grease Flask
*Skill 2 · debuff + control · VFX preset `xs_h06_grease_flask` · budget class heroic*

A lobbed flask bursts into a 3.5 m puddle of glossy grease that Oils and slows enemies for 6 s.

| Field | Spec |
|---|---|
| Targeting · telegraph | ground target within 12 m · **AREA ring** r 3.5 m |
| Range · radius | range 12 m · r 3.5 m · zone 6,000 ms |
| Timing | 233 / 67 / 267 ms · **release f7** (233 ms) · clip `merchant.skill_flask` 567 ms (17 f) |
| Zone / follow-up | 733-6733 ms |
| Clip events (ms) | charge_start 0, release 233 |
| Cooldown · cost · power | 10 s · 14 SP · - · none · element `forge` |
| Effects | -30 % move speed inside |
| Status → combo | Oiled 8 s → C6 Slipslick (+ Soaked from 04) |
| Palette | core `#FFE7A3` · body `#8A5A1E` · edge `#2FD4C4` · accent `#E05AD0` |
| Peak coverage | 16 % at the 13 m camera |
| SFX | `sfx.h06.grease_flask` · .cork / .throw / .splat |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–233 | `vfx_flask`, `vfx_motes` | She pops the cork; the brass flask glints; a drip falls. | Medium+ |
| Mesh core | 233–733 | `vfx_flask`, `vfx_fb_splash` | The flask arcs with a dripping trail; at 733 ms an oil crown splash. | all tiers |
| Secondaries | 733–1,500 | `vfx_motes` | Oil droplets with an iridescent rim; bubbles. | Medium+ (×0.5 on Medium) |
| Ground layer | 733–6,733 | `vfx_liquid_pool` | The puddle r 3.5 m: dark amber body lifted to sRGB ≥ 60, with a slow teal → magenta → gold sheen sweep. | all tiers |
| After-effect | 5,733–6,733 | `vfx_motes` | The puddle shrinks and dulls; drips on Oiled enemies. | Medium+ |

**Tiers:** Medium: same shapes and palette; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** The puddle body stays at sRGB ≥ 60 so dark enemies remain readable on it; the sheen carries the colour, so no PointLight.

#### 06.3 `h06_cog_sentry` · ป้อมเฟืองยาม · Cog Sentry
*Skill 3 · damage · VFX preset `xs_h06_cog_sentry` · budget class heroic*

A clockwork turret unfolds and fires brass bolts at the nearest enemy for 12 s, pulling threat off the back line.

| Field | Spec |
|---|---|
| Targeting · telegraph | place within 6 m · **CAST ring** r 1 m (while deploying) |
| Range · radius | range 6 m · sentry range 10 m |
| Timing | 400 / 67 / 300 ms · **release f12** (400 ms) · clip `merchant.skill_sentry` 767 ms (23 f) |
| Zone / follow-up | 400-12400 ms |
| Clip events (ms) | charge_start 0, release 400 |
| Cooldown · cost · power | 18 s · 18 SP · 20 shots x 10, range 10 m · physical · element `forge` |
| Effects | its hits generate +50 % threat; sentry HP 60 |
| Status → combo | none |
| Palette | core `#FFE7A3` · body `#D9A441` · edge `#FF7A1A` · accent `#2FD4C4` |
| Peak coverage | 12 % at the 13 m camera |
| SFX | `sfx.h06.cog_sentry` · .unfold / .shot / .fold |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–400 | `prop_cog_sentry`, `vfx_gear_ring` | A brass case unfolds with spinning gears over a 1 m gear-ring decal. | Medium+ |
| Mesh core | 400–12,400 | `prop_cog_sentry`, `vfx_cone_burst`, `vfx_streak` | The sentry (teal lens eye, spinning gear); each shot is a muzzle cone and a brass bolt tracer. | all tiers |
| Secondaries | 400–12,400 | `vfx_motes`, `vfx_fb_smoke` | Spark casings and steam puffs per shot. | Medium+ (×0.5 on Medium) |
| Ground layer | 400–12,400 | `vfx_gear_ring`, `vfx_scorch` | The gear ring under it and small scorch ticks where bolts hit. | all tiers |
| After-effect | 12,400–13,200 | `vfx_fb_smoke` | It folds, puffs steam and dissolves. | Medium+ |

**Tiers:** Medium: same shapes and palette; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** Persistent effects stay small: about 4 % sustained.
**Note:** The sentry is a gameplay actor with its own budget (prop_cog_sentry), not a VFX mesh. Coverage 12 % at deploy (D4).

#### 06.4 `h06_boiler_leap` · กระโดดหม้อไอน้ำ · Boiler Leap
*Skill 4 · mobility · VFX preset `xs_h06_boiler_leap` · budget class heroic*

A steam canister blasts her 8 m through the air; the takeoff blast knocks enemies back.

| Field | Spec |
|---|---|
| Targeting · telegraph | ground target or direction within 8 m · **AREA ring** r 2.5 m (at the takeoff point) |
| Range · radius | range 8 m · r 2.5 m · knockback 1 m · airborne 600 ms |
| Timing | 133 / 600 / 200 ms · **release f4** (133 ms) · clip `merchant.skill_leap` 933 ms (28 f) |
| Clip events (ms) | charge_start 0, takeoff 133, land 733 |
| Cooldown · cost · power | 11 s · 12 SP · 20 · physical · element `forge` |
| Effects | knockback 1.0 m at takeoff |
| Status → combo | none |
| Palette | core `#FFE7A3` · body `#FF7A1A` · edge `#C2361B` · accent `#2FD4C4` · steam `#E6EEF0` |
| Peak coverage | 16 % at the 13 m camera |
| SFX | `sfx.h06.boiler_leap` · .hiss / .blast / .land |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–133 | `vfx_motes` | The back canister hisses; its valves glow orange. | Medium+ |
| Mesh core | 133–400 | `vfx_funnel`, `vfx_ring_wall` | An upright steam blast funnel (pearl, orange core) and a ring wall burst r 0 → 2.5 m. | all tiers |
| Secondaries | 133–900 | `vfx_fb_smoke`, `vfx_motes` | Steam puffs, sparks, rivet glints; a steam contrail from the canister (TrailMesh). | Medium+ (×0.5 on Medium) |
| Ground layer | 133–1,500 | `vfx_shock_ring`, `vfx_fb_dust` | A scald ring at takeoff and a landing dust ring. | all tiers |
| After-effect | 733–1,900 | `vfx_fb_smoke` | Low steam lingers and fades at alpha ≤ 0.3. | Medium+ |
| Light | 133–400 | pooled `PointLight` | #FF8A3D, range 6 m. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 06.5 `h06_mending_anvil` · ทั่งซ่อมสนาม · Mending Anvil
*Skill 5 · buff · VFX preset `xs_h06_mending_anvil` · budget class heroic*

She hammers an anvil-pylon into the ground: for 10 s it welds 12 HP of armour onto allies within 5 m every 2 s (max 36) and gives +10 % DEF.

| Field | Spec |
|---|---|
| Targeting · telegraph | place within 6 m · **SAFE ring** r 5 m |
| Range · radius | range 6 m · r 5 m · zone 10,000 ms |
| Timing | 467 / 67 / 366 ms · **release f14** (467 ms) · clip `merchant.skill_anvil` 900 ms (27 f) |
| Zone / follow-up | 467-10467 ms |
| Clip events (ms) | hit 133, hit 300, release 467 |
| Cooldown · cost · power | 24 s · 22 SP · - · none · element `forge` |
| Effects | allies inside: +12 shield every 2 s (cap 36), +10 % DEF |
| Status → combo | none |
| Palette | core `#FFE7A3` · body `#D9A441` · edge `#FF7A1A` · accent `#2FD4C4` |
| Peak coverage | 18 % at the 13 m camera |
| SFX | `sfx.h06.mending_anvil` · .tap / .pulse / .weld / .fold |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–467 | `vfx_motes` | Three hammer taps with spark bursts as the pylon drives in. | Medium+ |
| Mesh core | 467–10,467 | `prop_anvil_pylon`, `vfx_gear_ring` | The pylon (anvil on a brass tripod, teal lens, spinning gear ring); a gear-tooth pulse ring every 2 s. | all tiers |
| Secondaries | 467–10,467 | `vfx_fb_lightning`, `vfx_motes` | Welding arcs (thin teal-orange beams) to each ally on every pulse; floating rivet and bolt motes. | Medium+ (×0.5 on Medium) |
| Ground layer | 467–10,467 | `vfx_gear_ring` | A gear-ring decal r 5 m under the dashed ring. | all tiers |
| After-effect | 467–11,200 | `vfx_hex_dome`, `vfx_fb_smoke` | Allies wear a brass-hex shimmer (alpha 0.25) while shielded; at the end the pylon folds with a steam puff. | Medium+ |
| Light | 467–800 | pooled `PointLight` | #2FD4C4, range 6 m flash at the cast. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 06.6 `h06_gearstorm_hammerfall` · ค้อนพายุเฟือง · Gearstorm Hammerfall
*Skill 6 · ultimate + damage · VFX preset `xs_h06_gearstorm_hammerfall` · budget class ultimate*

She hurls a beacon; a ring of spinning gears opens in the sky and a giant brass forge-hammer slams a 6 m crater of molten slag.

| Field | Spec |
|---|---|
| Targeting · telegraph | ground target within 14 m · **HEAVY ring** r 6 m |
| Range · radius | range 14 m · r 6 m |
| Timing | 400 / 67 / 400 ms · **release f12** (400 ms) · clip `merchant.skill_hammerfall` 867 ms (26 f) |
| Zone / follow-up | 700-5900 ms; impact at 1900 ms (she can act after 867 ms) |
| Clip events (ms) | charge_start 0, release 400 |
| Cooldown · cost · power | 85 s · 40 SP · 220 + slag 8/s for 4 s (the slag applies no status) · heavy · physical · element `forge` |
| Effects | knock-down 1.2 s (non-boss) |
| Status → combo | Scorched 4 s → C3 Steamburst (+ Chilled from 02) · Oiled 8 s → C6 Slipslick (+ Soaked from 04) |
| Palette | core `#FFE7A3` · body `#FF7A1A` · edge `#C2361B` · accent `#2FD4C4` · brass `#D9A441` |
| Peak coverage | 48 % at the 13 m camera |
| SFX | `sfx.h06.gearstorm_hammerfall` · .beacon / .gears_spin / .drop_whistle / .impact / .sizzle |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–1,900 | `vfx_flask`, `vfx_orbit_ring`, `vfx_gear_ring`, `vfx_fb_smoke` | The beacon (vfx_flask with a teal lens) blinks; 3 gear rings (vfx_orbit_ring with the vfx_gear_ring texture) assemble 8 m up and spin; steam jets and falling sparks. | Medium+ |
| Mesh core | 1,700–2,100 | `vfx_forge_hammer` | A 5 m brass forge-hammer with glowing orange vents drops with ease-in; impact at 1900 ms. | all tiers |
| Secondaries | 1,900–3,000 | `vfx_motes`, `vfx_shards`, `vfx_fb_smoke` | Spark fountains (GPU 1,200 on High, 200 CPU), molten droplets, steam bursts, flying gear teeth and rivets. | Medium+ (×0.5 on Medium) |
| Ground layer | 1,900–5,900 | `vfx_ground_cracks`, `vfx_gear_ring`, `vfx_scorch` | Molten cracks r 6 m with an orange seam, a gear-tooth imprint and scorch. | all tiers |
| After-effect | 2,100–5,900 | `vfx_fb_flame`, `vfx_fb_smoke` | The slag cools orange → soot with small flames; a smoke column; heat shimmer on High. | Medium+ |
| Light | 1,900–2,400 | pooled `PointLight` | #FF8A3D, range 14 m, 0 → 9 → 0. | High+ |
| Distortion | 1,900–2,100 | post | Shock heat shimmer. | Epic only |

**Tiers:** Epic adds distortion. Medium: same shapes and palette; drops light, distortion; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** The hammer is opaque for only 200 ms and lands on the HEAVY ring, which stays on top; the slag is a decal under characters.

### 4.5 Hero 04: Bull-kin Acolyte · นักบวชวัว

| Field | Spec |
|---|---|
| Party role | **Healer-support** (ฮีลเลอร์-ซัพพอร์ต) |
| Party job | Heals (Springwell Rain, Dawn Mend, Noonspring Covenant revive), mitigates (Sunwheel Sanctum), and primes Soaked and Sunlit while doing it. |
| Element | Sun and spring (holy sunlight, healing water) |
| Palette (sun gold + spring turquoise) | core `#FFF8E1` · body `#FFC94A` · edge `#E07A1F` · accent `#3FE0C5` · deep `#167A8C` |
| Shape language | Sun-wheels with spokes (his shoulder emblems), halos and rays, rings of water, droplets and ripples, horn-like arcs. Round, radiant, calm. |
| Statuses | Soaked (เปียกโชก), Sunlit (ตราตะวัน) |
| Combos | C4 Rainlash (with 01); C5 Rahu's Bite (with 05); C6 Slipslick (with 06) |
| Weapon | Sun-ring sceptre (gold ring, cyan crystal) · Blender · 1.55 m → 1.86 m (+20 %) |
| Sockets | socket_weapon_R (sceptre; socket_weapon_L as the two-hand cast target), socket_back |
| Trail and VFX markers | grip origin, +Y; fx_base, fx_tip (ring top), fx_head (crystal in the ring = heal and beam origin). short gold arc ribbon fx_base → fx_tip on basics (10 segments, 140 ms); heals and beams leave from fx_head. |
| Rig sets | base + caster + heavy_1h + acolyte · display_scale 1.139 · crown 2.05 m |

| Slot | Id | Thai / English | Type | Telegraph | Range / radius | Timing (w / a / r) · release | CD · SP | Status → combo |
|---|---|---|---|---|---|---|---|---|
| basic | `h04_basic` | ทุบวงตะวัน / Sunring Strikes | damage | **none (target bracket only)** | range 3.5 m · 100° | 100 / 60 / 200 · f3 | 0.4 s · 0 | none |
| 1 | `h04_springwell_rain` | ฝนน้ำพุศักดิ์สิทธิ์ / Springwell Rain | heal + debuff | **SAFE ring** r 4 m | range 14 m · r 4 m · zone 4,000 ms | 333 / 67 / 300 · f10 | 12 s · 18 | Soaked 6 s → C4 Rainlash (+ Charged from 01); C6 Slipslick (+ Oiled from 06) |
| 2 | `h04_sunpalm_wave` | ฝ่ามือสุริยะ / Sunpalm Wave | damage + heal | **AREA lane** 2 × 10 m | range 10 m · r 2.2 m · 16 m/s · knockback 1.5 m | 200 / 67 / 233 · f6 | 8 s · 14 | Sunlit 6 s → C5 Rahu's Bite (+ Shadowed from 05) |
| 3 | `h04_dawn_mend` | แสงอรุณสมานแผล / Dawn Mend | heal | **SAFE brackets** | range 16 m | 400 / 67 / 233 · f12 | 6 s · 14 | none |
| 4 | `h04_pilgrims_horn` | พุ่งเขาผู้แสวงบุญ / Pilgrim's Horn Rush | mobility + buff | **AREA lane** 2 × 7 m | range 7 m · dash 350 ms | 167 / 350 / 250 · f5 | 12 s · 12 | none |
| 5 | `h04_sunwheel_sanctum` | วงจักรตะวันศักดิ์สิทธิ์ / Sunwheel Sanctum | buff | **SAFE ring** r 6 m | self · r 6 m · zone 8,000 ms | 300 / 67 / 300 · f9 | 22 s · 22 | Sunlit 6 s → C5 Rahu's Bite (+ Shadowed from 05) |
| 6 | `h04_noonspring_covenant` | พันธสัญญาตะวันเที่ยง / Noonspring Covenant | ultimate + heal | **SAFE double ring** r 8 m | self · r 8 m | 800 / 200 / 500 · f24 | 90 s · 40 | Soaked → C4, C6; Sunlit → C5 |

#### 04.0 `h04_basic` · ทุบวงตะวัน · Sunring Strikes
*Basic attack · damage · VFX preset `xs_h04_basic` · budget class basic*

Two sceptre strikes; each flashes a small sun-wheel on contact.

| Field | Spec |
|---|---|
| Targeting · telegraph | melee fan 3.5 m, 100° · **none (target bracket only)** |
| Range · radius | range 3.5 m · 100° |
| Timing | 100 / 60 / 200 ms · **release f3** (100 ms) · clip `heavy_1h.attack_1 / heavy_1h.attack_2 (acolyte variant)` 400 ms (12 f) |
| Clip events (ms) | swing_start 0, trail_on 67, hit 100, trail_off 167, link_open 400 |
| Cooldown · cost · power | 0.4 s · 0 SP · 25 per link · physical · element `sun_spring` |
| Status → combo | none |
| Palette | core `#FFF8E1` · body `#FFC94A` · edge `#E07A1F` · accent `#3FE0C5` |
| Peak coverage | 4 % at the 13 m camera |
| SFX | `sfx.h04.basic` · .swing / .chime_hit |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–100 | `vfx_motes` | The sun-ring flares gold. | Medium+ |
| Mesh core | 100–240 | `vfx_rune_sunwheel` | A short gold arc ribbon and a spoked sun-wheel flash (0.8 m billboard) on hit. | all tiers |
| Secondaries | hit → hit+250 | `vfx_motes` | 6 gold sparks and 4 turquoise droplets. | Medium+ (×0.5 on Medium) |
| Ground layer | hit → hit+400 | `vfx_shock_ring` | A small radiant ring r 1 m on link 2. | Medium+ |
| After-effect | hit → hit+300 | `vfx_motes` | Gold motes for 300 ms. | High+ |

**Tiers:** Medium: same shapes and palette; drops after-effect; secondaries ×0.5. Low: mesh core + telegraph; no light.

#### 04.1 `h04_springwell_rain` · ฝนน้ำพุศักดิ์สิทธิ์ · Springwell Rain
*Skill 1 · heal + debuff · VFX preset `xs_h04_springwell_rain` · budget class heroic*

A sunlit rain cloud blesses a 4 m circle for 4 s: allies heal and enemies get Soaked.

| Field | Spec |
|---|---|
| Targeting · telegraph | ground target within 14 m · **SAFE ring** r 4 m (persists for the zone) |
| Range · radius | range 14 m · r 4 m · zone 4,000 ms |
| Timing | 333 / 67 / 300 ms · **release f10** (333 ms) · clip `acolyte.skill_rain` 700 ms (21 f) |
| Zone / follow-up | 333-4333 ms; heal ticks every 500 ms from 600 ms |
| Clip events (ms) | charge_start 0, release 333 |
| Cooldown · cost · power | 12 s · 18 SP · heal 8 ticks x 4 · none · element `sun_spring` |
| Effects | allies inside heal 4 HP per tick |
| Status → combo | Soaked 6 s → C4 Rainlash (+ Charged from 01); C6 Slipslick (+ Oiled from 06) |
| Palette | core `#F2FFFD` · body `#3FE0C5` · edge `#167A8C` · accent `#FFC94A` |
| Peak coverage | 22 % at the 13 m camera |
| SFX | `sfx.h04.springwell_rain` · .raise / .cloud_form / .rain_loop |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–333 | `vfx_motes`, `vfx_fb_cloud` | Turquoise droplets spiral up from the sceptre ring; a cloud gathers 4 m above the target. | Medium+ |
| Mesh core | 333–4,333 | `vfx_fb_cloud`, `vfx_streak` | The cloud cluster with a sun-lit gold rim; rain streaks inside r 4 m (GPU 600 on High, 160 CPU; Low keeps 40); a small rainbow arc on the cloud edge (gradient quad). | all tiers |
| Secondaries | 333–4,333 | `vfx_fb_splash`, `vfx_motes` | Splash crowns, gold glints in the drops, heal motes rising from allies. | Medium+ (×0.5 on Medium) |
| Ground layer | 333–4,333 | `vfx_liquid_pool`, `vfx_fb_ripple` | Wet ground r 4 m with ripples under the dashed ring. | all tiers |
| After-effect | 4,333–5,500 | `vfx_liquid_pool`, `vfx_fb_smoke` | The puddle sheen and a low mist fade. | Medium+ |
| Light | 333–700 | pooled `PointLight` | #3FE0C5, range 8 m soft flash. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** The cloud sits 4 m up and the rain streaks are thin at alpha 0.35, so characters under it stay readable.

#### 04.2 `h04_sunpalm_wave` · ฝ่ามือสุริยะ · Sunpalm Wave
*Skill 2 · damage + heal · VFX preset `xs_gale_palm@sun` · reuses `xs_gale_palm` · budget class heroic*

A great sun-palm sigil flies 10 m: it heals each ally it passes through, then strikes the first enemy, blasting everything within 2.2 m back and leaving them Sunlit.

| Field | Spec |
|---|---|
| Targeting · telegraph | skillshot; passes through allies, stops at the first enemy · **AREA lane** 2 × 10 m; then an AREA ring r 2.2 m at the impact point for 200 ms |
| Range · radius | range 10 m · r 2.2 m · 16 m/s · knockback 1.5 m |
| Timing | 200 / 67 / 233 ms · **release f6** (200 ms) · clip `acolyte.skill_palm` 500 ms (15 f) |
| Clip events (ms) | charge_start 0, release 200 |
| Cooldown · cost · power | 8 s · 14 SP · 40; heals 15 per ally passed (once each) · magical · element `sun_spring` |
| Effects | knockback 1.5 m |
| Status → combo | Sunlit 6 s → C5 Rahu's Bite (+ Shadowed from 05) |
| Palette | core `#FFF8E1` · body `#FFC94A` · edge `#E07A1F` · accent `#3FE0C5` |
| Peak coverage | 18 % at the 13 m camera |
| SFX | `sfx.h04.sunpalm_wave` · .gather / .push / .impact |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–200 | `vfx_fb_swirl`, `vfx_streak`, `vfx_motes` | Two gold sun swirls at his open palm and the sceptre ring; 12 converging light streaks. | Medium+ |
| Mesh core | 200 → hit | `vfx_palm_sigil`, `vfx_cone_burst` | vfx_palm_sigil at 1.8 m (a broad open palm inside a sun-wheel disc; fixes the 'tiny sigil' defect) and a gold release cone. | all tiers |
| Secondaries | 200 → hit+250 | `vfx_motes`, `vfx_streak`, `vfx_fb_splash` | 3 gold / turquoise helix ribbons, shed light streaks and light petals; a turquoise heal splash on each ally passed. | Medium+ (×0.5 on Medium) |
| Ground layer | hit → hit+1,400 | `vfx_swirl_arms`, `vfx_impact_star` | A sun-flare vortex decal r 0 → 2.6 m and an impact flash decal. | all tiers |
| After-effect | hit → hit+900 | `vfx_funnel`, `vfx_motes` | A 2.5 m gold light funnel with lifted motes; Sunlit halos appear on the hit enemies. | Medium+ (×0.5 on Medium) |
| Light | 0 → hit+300 | pooled `PointLight` | #FFD873, range 7 m. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries, after-effect ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 04.3 `h04_dawn_mend` · แสงอรุณสมานแผล · Dawn Mend
*Skill 3 · heal · VFX preset `xs_h04_dawn_mend` · budget class heroic*

A column of dawn light heals one ally for 35 plus 20 over 5 s and lifts one debuff.

| Field | Spec |
|---|---|
| Targeting · telegraph | ally or self within 16 m · **SAFE brackets** |
| Range · radius | range 16 m |
| Timing | 400 / 67 / 233 ms · **release f12** (400 ms) · clip `acolyte.skill_mend` 700 ms (21 f) |
| Clip events (ms) | charge_start 0, release 400 |
| Cooldown · cost · power | 6 s · 14 SP · heal 35 + 4/s for 5 s · none · element `sun_spring` |
| Effects | cleanse 1 debuff |
| Status → combo | none |
| Palette | core `#FFF8E1` · body `#FFD873` · edge `#E9A23B` · accent `#3FE0C5` |
| Peak coverage | 12 % at the 13 m camera |
| SFX | `sfx.h04.dawn_mend` · .chant / .pillar / .hot_loop |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–400 | `vfx_rune_sunwheel`, `vfx_motes` | A sun-wheel spins up in fx_head; a thin light thread reaches toward the ally. | Medium+ |
| Mesh core | 400–900 | `vfx_ring_wall`, `vfx_rune_sunwheel` | A hollow light pillar (vfx_ring_wall, 4 m tall, r 1.0 m, gold fresnel, alpha 0.4) descends on the ally, with a halo above the head. | all tiers |
| Secondaries | 400–1,200 | `vfx_motes` | Rising gold motes and turquoise droplets. | Medium+ (×0.5 on Medium) |
| Ground layer | 400–1,500 | `vfx_rune_sunwheel` | A sun-wheel decal r 1.2 m with turning spokes. | all tiers |
| After-effect | 900–5,400 | `vfx_rune_sunwheel`, `vfx_motes` | HoT: a faint slow halo and a few rising motes for 5 s. | Medium+ |
| Light | 400–700 | pooled `PointLight` | #FFD873, range 5 m. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** The pillar is hollow, so the ally's silhouette shows through.
**Note:** cast_heal is retimed from the rig plan's 900/600 to 700/400 to keep heals responsive in action combat. Coverage 12 % (single target; D4).

#### 04.4 `h04_pilgrims_horn` · พุ่งเขาผู้แสวงบุญ · Pilgrim's Horn Rush
*Skill 4 · mobility + buff · VFX preset `xs_h04_pilgrims_horn` · budget class heroic*

Head down, horns first: a 7 m bull rush that shoulders enemies aside and gives each ally he passes a 25 HP shield.

| Field | Spec |
|---|---|
| Targeting · telegraph | dash in a direction, or to an ally within 9 m · **AREA lane** 2 × 7 m |
| Range · radius | range 7 m · dash 350 ms |
| Timing | 167 / 350 / 250 ms · **release f5** (167 ms) · clip `acolyte.skill_rush` 767 ms (23 f) |
| Clip events (ms) | whoosh 0, release 167, hit 330 |
| Cooldown · cost · power | 12 s · 12 SP · 25 · physical · element `sun_spring` |
| Effects | allies passed: 25 HP shield for 4 s |
| Status → combo | none |
| Palette | core `#FFF8E1` · body `#FFC94A` · edge `#E07A1F` · accent `#3FE0C5` |
| Peak coverage | 15 % at the 13 m camera |
| SFX | `sfx.h04.pilgrims_horn` · .snort / .charge_loop / .impact |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–167 | `vfx_fb_dust`, `vfx_rune_sunwheel` | Hooves scrape up dust; a sun-wheel spins between the horns (rig anchor fx_head on the skeleton, not the sceptre marker). | Medium+ |
| Mesh core | 167–517 | `vfx_cone_burst` | A radiant gold bow wave and 2 horn ribbons (TrailMesh from offsets of the rig anchor fx_head). | all tiers |
| Secondaries | 167–700 | `vfx_motes`, `vfx_fb_splash` | Hoof sparks and dust each step; a turquoise splash on each shielded ally. | Medium+ (×0.5 on Medium) |
| Ground layer | 167–1,500 | `vfx_scorch`, `vfx_fb_dust` | 4 glowing hoof prints and a dust trail. | all tiers |
| After-effect | 517–1,300 | `vfx_hex_dome`, `vfx_fb_dust` | Dust settles; a gold-hex shimmer (alpha 0.25) on shielded allies. | Medium+ |
| Light | 167–517 | pooled `PointLight` | #FFC94A, range 5 m, travelling. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 04.5 `h04_sunwheel_sanctum` · วงจักรตะวันศักดิ์สิทธิ์ · Sunwheel Sanctum
*Skill 5 · buff · VFX preset `xs_h04_sunwheel_sanctum` · budget class heroic*

A 6 m sun-wheel blazes on the ground for 8 s: allies inside take 15 % less damage and get 20 % more healing; enemies entering are Sunlit.

| Field | Spec |
|---|---|
| Targeting · telegraph | zone at the cast spot · **SAFE ring** r 6 m |
| Range · radius | self · r 6 m · zone 8,000 ms |
| Timing | 300 / 67 / 300 ms · **release f9** (300 ms) · clip `acolyte.skill_sanctum` 667 ms (20 f) |
| Zone / follow-up | 300-8300 ms |
| Clip events (ms) | charge_start 0, plant 300 |
| Cooldown · cost · power | 22 s · 22 SP · - · none · element `sun_spring` |
| Effects | allies inside: -15 % damage taken, +20 % healing received |
| Status → combo | Sunlit 6 s → C5 Rahu's Bite (+ Shadowed from 05) |
| Palette | core `#FFF8E1` · body `#FFC94A` · edge `#E07A1F` · accent `#3FE0C5` |
| Peak coverage | 28 % at the 13 m camera |
| SFX | `sfx.h04.sunwheel_sanctum` · .plant / .wheel_hum_loop / .end |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–300 | `vfx_rune_sunwheel` | 12 sun spokes wipe out along the ground from his hooves to r 6 m. | Medium+ |
| Mesh core | 300–8,300 | `vfx_rune_sunwheel`, `vfx_ring_wall` | The sun-wheel (12 spokes, double ring, sun glyphs) and a translucent gold rim wall (r 6 m, 1.2 m tall, alpha 0.35). | all tiers |
| Secondaries | 300–8,300 | `vfx_motes` | Gold motes rising along the rim, occasional turquoise droplets inside, slowly turning spoke beams. | Medium+ (×0.5 on Medium) |
| Ground layer | 300–8,300 | `vfx_soft_disc` | A warm ground tint under the wheel. | all tiers |
| After-effect | 8,300–9,300 | `vfx_motes` | The spokes retract into the centre; gold mist fades. | Medium+ |
| Light | 300–700 | pooled `PointLight` | #FFD873, range 9 m flash at the cast only (protects the pool). | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 04.6 `h04_noonspring_covenant` · พันธสัญญาตะวันเที่ยง · Noonspring Covenant
*Skill 6 · ultimate + heal · VFX preset `xs_h04_noonspring_covenant` · budget class ultimate*

He calls the noon sun down and a holy spring up: allies within 8 m heal 50, shed every debuff, and downed allies rise at 30 % HP; enemies inside are Soaked and Sunlit.

| Field | Spec |
|---|---|
| Targeting · telegraph | self-centred 8 m · **SAFE double ring** r 8 m |
| Range · radius | self · r 8 m |
| Timing | 800 / 200 / 500 ms · **release f24** (800 ms) · clip `acolyte.skill_covenant` 1,500 ms (45 f) |
| Clip events (ms) | charge_start 0, release 800 |
| Cooldown · cost · power | 90 s · 40 SP · heal 50 + cleanse all; revive downed allies at 30 % HP · none · element `sun_spring` |
| Effects | Noon Grace: allies +20 % healing received for 6 s |
| Status → combo | Soaked 6 s → C4 Rainlash (+ Charged from 01); C6 Slipslick (+ Oiled from 06) · Sunlit 6 s → C5 Rahu's Bite (+ Shadowed from 05) |
| Palette | core `#FFF8E1` · body `#FFC94A` · edge `#E07A1F` · accent `#3FE0C5` |
| Peak coverage | 45 % at the 13 m camera |
| SFX | `sfx.h04.noonspring_covenant` · .invoke / .sun_descend / .geyser / .revive_chime |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–800 | `vfx_rune_sunwheel`, `vfx_motes` | A sun disc (vfx_rune_sunwheel, 3 m, turning spokes) descends to 10 m above him; turquoise water rises in a spiral from the ground. | Medium+ |
| Mesh core | 800–1,600 | `vfx_ring_wall`, `vfx_funnel` | A hollow central light pillar (r 2 m, 10 m tall), a turquoise geyser column and an expanding water ring wave (r 0 → 8 m, 0.8 m tall). | all tiers |
| Secondaries | 800–2,200 | `vfx_motes`, `vfx_fb_splash` | Sun sparks, water droplet arcs (GPU 800 on High, 150 CPU), a rainbow arc in the geyser spray. | Medium+ (×0.5 on Medium) |
| Ground layer | 800–3,000 | `vfx_rune_sunwheel`, `vfx_liquid_pool`, `vfx_fb_ripple` | The sun-wheel r 8 m and wet ripples. | all tiers |
| After-effect | 1,600–3,300 | `vfx_motes`, `vfx_fb_smoke` | A gentle gold mote rain, puddle sheen and mist. | Medium+ |
| Light | 800–1,600 | pooled `PointLight` | #FFD873 → #7FF0E0, range 14 m, 0 → 8 → 0. | High+ |
| Distortion | 800–1,400 | post | Heat shimmer inside the pillar. | Epic only |

**Tiers:** Epic adds distortion. Medium: same shapes and palette; drops light, distortion; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Readability:** The pillar is hollow and alpha-capped; the water ring is low (0.8 m) and fast; every ally stays visible; SAFE rings never get teeth.
**Note:** A beneficial ultimate uses the double dashed SAFE ring, not the HEAVY ring: teeth always mean danger.

### 4.6 Hero 03: Wolf-kin Archer · นักธนูหมาป่า

| Field | Spec |
|---|---|
| Party role | **Ranged DPS** (DPS ระยะไกล) |
| Party job | Marks priority targets for the whole party (Amberwatch Arrow), deletes lines (Crescent Howl), roots packs (Briar Snare), and primes Marked and Gusted. |
| Element | Gale and wild (wind, leaves, the moonlit hunt) |
| Palette (wind jade and the hunter's amber of her eyes) | core `#F0FFF6` · body `#5CE6A0` · edge `#1F9E86` · accent `#FFB84A` · leaf `#8EDB4F` · moon `#DDE6F2` |
| Shape language | Arrowheads and chevrons, feathers and leaf blades (from her cape's gold leaves), wind streaks and spiral curls, crescent fangs. Fast, directional, light. |
| Statuses | Marked (ตราล่า), Gusted (ต้องลม) |
| Combos | C7 Faultline (with 01); C8 Plaguewind (with 05) |
| Weapon | Recurve bow (teal and gold, horn tips) + arrows + quiver · Blender · 1.35 m → 1.62 m (+20 %) |
| Sockets | socket_weapon_L (bow grip), arrow on socket_weapon_R (nock), quiver on socket_back |
| Trail and VFX markers | grip origin; fx_tip (upper limb tip), fx_base (lower limb tip), fx_nock (string centre = arrow spawn), fx_head (arrow rest). arrows carry their own jade ribbons; a limb-arc ribbon fx_base → fx_tip only on Brushtail Vault; muzzle flashes at fx_nock. |
| Rig sets | base + bow + archer · display_scale measure (crown without ears) · crown 1.85 m (with the ears) |

| Slot | Id | Thai / English | Type | Telegraph | Range / radius | Timing (w / a / r) · release | CD · SP | Status → combo |
|---|---|---|---|---|---|---|---|---|
| basic | `h03_basic` | ศรขนนกฉับไว / Snapfeather Shots | damage | **none (target bracket only)** | range 16 m · 45 m/s | 100 / 67 / 233 · f3 | 0.4 s · 0 | none |
| 1 | `h03_amberwatch_arrow` | ศรเนตรอำพัน / Amberwatch Arrow | debuff + damage | **TARGET brackets** | range 20 m · 45 m/s | 233 / 67 / 267 · f7 | 6 s · 10 | Marked 8 s → C7 Faultline (+ Cracked from 01) |
| 2 | `h03_featherfan_volley` | ศรพัดขนนก / Featherfan Volley | damage + control | **AREA fan** r 12 m, 60° | range 12 m · knockback 0.5 m | 267 / 67 / 366 · f8 | 7 s · 14 | Gusted 4 s → C8 Plaguewind (+ Venom from 05) |
| 3 | `h03_crescent_howl` | ศรหอนจันทร์เสี้ยว / Crescent Howl | damage | **AREA lane** 1.2 × 24 m | range 24 m · hold ≤ 1,000 ms | 267 / 67 / 300 · f8 | 9 s · 16 | none |
| 4 | `h03_brushtail_vault` | ตีลังกาหางพู่ / Brushtail Vault | mobility + control | **AREA ring** r 2.5 m | range 7 m · r 2.5 m · knockback 1 m · airborne 400 ms | 100 / 400 / 200 · f3 | 10 s · 10 | Gusted 4 s → C8 Plaguewind (+ Venom from 05) |
| 5 | `h03_briar_snare` | บ่วงหนามป่า / Briar Snare | control | **AREA ring** r 3 m | range 16 m · r 3 m | 233 / 67 / 300 · f7 | 14 s · 16 | none |
| 6 | `h03_featherstorm` | ฝูงขนนกพายุ / Featherstorm Murmuration | ultimate + damage | **HEAVY ring** r 6 m | range 20 m · r 6 m | 600 / 100 / 300 · f18 | 85 s · 40 | Marked → C7; Gusted → C8 |

#### 03.0 `h03_basic` · ศรขนนกฉับไว · Snapfeather Shots
*Basic attack · damage · VFX preset `xs_h03_basic` · budget class basic*

Two quick snap shots.

| Field | Spec |
|---|---|
| Targeting · telegraph | auto-target arrow (current target, else straight ahead) · **none (target bracket only)** |
| Range · radius | range 16 m · 45 m/s |
| Timing | 100 / 67 / 233 ms · **release f3** (100 ms) · clip `bow.attack_1 / bow.attack_2` 400 ms (12 f) |
| Clip events (ms) | nock 0, release 100, link_open 400 |
| Cooldown · cost · power | 0.4 s · 0 SP · 25 per link · physical · element `gale` |
| Status → combo | none |
| Palette | core `#F0FFF6` · body `#5CE6A0` · edge `#1F9E86` · accent `#FFB84A` |
| Peak coverage | 3 % at the 13 m camera |
| SFX | `sfx.h03.basic` · .draw_snap / .release / .thunk |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–100 | `vfx_motes` | A jade flicker at fx_nock. | Medium+ |
| Mesh core | 100 → hit | `vfx_arrow` | The arrow with a thin jade wind ribbon (TrailMesh 0.08 m). | all tiers |
| Secondaries | 100 → hit | `vfx_motes` | 4 feather motes shed. | Medium+ (×0.5 on Medium) |
| Ground layer | hit → hit+300 | `vfx_fb_impact` | A small jade impact burst. | Medium+ |
| After-effect | hit → hit+400 | `vfx_motes` | A drifting feather. | High+ |

**Tiers:** Medium: same shapes and palette; drops after-effect; secondaries ×0.5. Low: mesh core + telegraph; no light.

#### 03.1 `h03_amberwatch_arrow` · ศรเนตรอำพัน · Amberwatch Arrow
*Skill 1 · debuff + damage · VFX preset `xs_h03_amberwatch_arrow` · budget class heroic*

An amber-sigil arrow Marks a target for 8 s: the whole party deals 10 % more to it and sees it through walls.

| Field | Spec |
|---|---|
| Targeting · telegraph | single target within 20 m · **TARGET brackets** |
| Range · radius | range 20 m · 45 m/s |
| Timing | 233 / 67 / 267 ms · **release f7** (233 ms) · clip `archer.skill_amberwatch` 567 ms (17 f) |
| Clip events (ms) | nock 0, release 233 |
| Cooldown · cost · power | 6 s · 10 SP · 40 · physical · element `gale` |
| Status → combo | Marked 8 s → C7 Faultline (+ Cracked from 01) |
| Palette | core `#FFF6E0` · body `#FFB84A` · edge `#C9731F` · accent `#5CE6A0` |
| Peak coverage | 12 % at the 13 m camera |
| SFX | `sfx.h03.amberwatch_arrow` · .draw / .release / .mark_lock |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–233 | `vfx_sigil_atlas`, `vfx_motes` | An amber diamond-eye glyph flares at the bow grip; 6 amber motes converge on the arrowhead. | Medium+ |
| Mesh core | 233 → hit+400 | `vfx_arrow`, `vfx_sigil_atlas` | The arrow wrapped in an amber spiral ribbon; on hit an amber diamond sigil (0.8 m) snaps above the target with 4 closing ticks. | all tiers |
| Secondaries | 233 → hit+400 | `vfx_motes` | Amber sparks and jade feathers. | Medium+ (×0.5 on Medium) |
| Ground layer | hit → hit+8,000 | `vfx_shock_ring` | A small amber ring r 0.8 m under the target, pulsing at ≤ 1 Hz. | all tiers |
| After-effect | hit → hit+8,000 | `vfx_sigil_atlas` | The mark holds at low intensity; party-only through-wall outline. | all tiers |

**Tiers:** Medium: same shapes and palette; secondaries ×0.5. Low: mesh core, ground layer, after-effect + telegraph; no light.
**Note:** No PointLight (emissive flash instead). Coverage 12 % (single target; D4).

#### 03.2 `h03_featherfan_volley` · ศรพัดขนนก · Featherfan Volley
*Skill 2 · damage + control · VFX preset `xs_h03_featherfan_volley` · budget class heroic*

Five wind-wrapped arrows fan across a 60° cone, push enemies back and Gust them.

| Field | Spec |
|---|---|
| Targeting · telegraph | cone 12 m, 60° · **AREA fan** r 12 m, 60° |
| Range · radius | range 12 m · knockback 0.5 m |
| Timing | 267 / 67 / 366 ms · **release f8** (267 ms) · clip `archer.skill_volley` 700 ms (21 f) |
| Clip events (ms) | nock 0, release 267 |
| Cooldown · cost · power | 7 s · 14 SP · 5 × 30 (max 2 arrows per target) · physical · element `gale` |
| Effects | knockback 0.5 m |
| Status → combo | Gusted 4 s → C8 Plaguewind (+ Venom from 05) |
| Palette | core `#F0FFF6` · body `#5CE6A0` · edge `#1F9E86` · accent `#FFB84A` |
| Peak coverage | 18 % at the 13 m camera |
| SFX | `sfx.h03.featherfan_volley` · .draw / .fan_release / .impacts |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–267 | `vfx_arrow`, `vfx_fb_swirl` | The bow tilts flat; 5 ghost arrows fan out as a preview; wind gathers on the string. | Medium+ |
| Mesh core | 267–600 | `vfx_arrow`, `vfx_crescent_slash` | 5 arrows with jade wind ribbons (5 TrailMesh; 3 on Medium) and a 60° x 3 m wind-fan crescent muzzle burst. | all tiers |
| Secondaries | 267–900 | `vfx_motes`, `vfx_fb_impact` | Leaves and feathers spiralling; gust puffs at impacts. | Medium+ (×0.5 on Medium) |
| Ground layer | 267–1,400 | `vfx_streak` | A fan-shaped wind-streak decal across the wedge. | all tiers |
| After-effect | 600–1,600 | `vfx_motes` | Leaves settle; Gusted ribbons on the hit enemies. | Medium+ |
| Light | 267–500 | pooled `PointLight` | #5CE6A0, range 7 m. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 03.3 `h03_crescent_howl` · ศรหอนจันทร์เสี้ยว · Crescent Howl
*Skill 3 · damage · VFX preset `xs_h03_crescent_howl` · budget class heroic*

Hold to draw (up to 1 s): the arrow grows a pair of crescent wind-fangs and pierces everything in a 24 m line.

| Field | Spec |
|---|---|
| Targeting · telegraph | aimed line, pierces all; hold to charge · **AREA lane** 1.2 × 24 m (the lane grows with the charge) |
| Range · radius | range 24 m · hold ≤ 1,000 ms |
| Timing | 267 / 67 / 300 ms · **release f8** (267 ms) · clip `bow.draw (267) + bow.aim_loop (1,000, loop) + bow.release (300)` 634 ms (19 f) |
| Clip events (ms) | nock 0, full_draw 233, release 267 |
| Cooldown · cost · power | 9 s · 16 SP · 70 at minimum charge → 150 at full (linear); +30 % against Marked · heavy · physical · element `gale` |
| Effects | full charge: knockback 1 m; heavy at ≥ 70 % charge |
| Status → combo | none |
| Palette | core `#F4FFF8` · body `#5CE6A0` · edge `#1F9E86` · accent `#FFB84A` · moon `#DDE6F2` |
| Peak coverage | 20 % at the 13 m camera |
| SFX | `sfx.h03.crescent_howl` · .draw / .charge_loop / .full_ting / .release_howl |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–1,267 | `vfx_crescent_slash`, `vfx_motes` | Two small crescents form at the arrowhead and widen with the charge; moonlight motes converge; at full charge a 'ting' glint and the crescents lock as fangs. | Medium+ |
| Mesh core | 1,267–1,900 | `vfx_arrow`, `vfx_crescent_slash`, `vfx_cone_burst` | The arrow becomes a 3 m crescent-fang wind spear with a muzzle cone, leaving a straight helix wake (2 TrailMesh). | all tiers |
| Secondaries | 1,267–2,000 | `vfx_shock_ring`, `vfx_motes`, `vfx_streak` | A vertical sonic ring at release, shed feathers, streaks. | Medium+ (×0.5 on Medium) |
| Ground layer | 1,267–2,500 | `vfx_streak`, `vfx_fb_dust` | A wind-scar decal along the lane and dust kicked up along the path. | all tiers |
| After-effect | 1,500–2,600 | `vfx_motes` | Jade and moon-silver motes hang along the path. | Medium+ |
| Light | 1,267–1,600 | pooled `PointLight` | #DDE6F2, range 8 m, travelling. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.
**Note:** Timings assume a full 1,000 ms hold, so the release is at 1,267 ms; at minimum charge the release is at 267 ms (f8). The release clip's frame 0 is the release.

#### 03.4 `h03_brushtail_vault` · ตีลังกาหางพู่ · Brushtail Vault
*Skill 4 · mobility + control · VFX preset `xs_h03_brushtail_vault` · budget class heroic*

A 7 m backflip; the takeoff leaves a gust that knocks enemies back and Gusts them.

| Field | Spec |
|---|---|
| Targeting · telegraph | backward, or a chosen direction, 7 m · **AREA ring** r 2.5 m (at the takeoff point) |
| Range · radius | range 7 m · r 2.5 m · knockback 1 m · airborne 400 ms |
| Timing | 100 / 400 / 200 ms · **release f3** (100 ms) · clip `archer.skill_vault` 700 ms (21 f) |
| Clip events (ms) | takeoff 100, land 500 |
| Cooldown · cost · power | 10 s · 10 SP · 15 · physical · element `gale` |
| Effects | knockback 1.0 m at takeoff |
| Status → combo | Gusted 4 s → C8 Plaguewind (+ Venom from 05) |
| Palette | core `#F0FFF6` · body `#5CE6A0` · edge `#1F9E86` · accent `#FFB84A` |
| Peak coverage | 15 % at the 13 m camera |
| SFX | `sfx.h03.brushtail_vault` · .gust / .flip_whoosh / .land |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–100 | `vfx_motes` | Wind coils around her legs and tail (2 ribbons). | Medium+ |
| Mesh core | 100–400 | `vfx_funnel`, `vfx_ring_wall` | A gust bloom at takeoff (squashed funnel) and a ring wall burst r 0.5 → 2.5 m. | all tiers |
| Secondaries | 100–800 | `vfx_motes` | Leaves and feathers burst; a limb-arc ribbon (fx_base → fx_tip) traces the flip. | Medium+ (×0.5 on Medium) |
| Ground layer | 100–1,300 | `vfx_swirl_arms`, `vfx_fb_dust` | A jade swirl decal r 2.5 m at takeoff and a landing dust ring. | all tiers |
| After-effect | 500–1,500 | `vfx_motes` | Drifting leaves. | Medium+ |
| Light | 100–300 | pooled `PointLight` | #5CE6A0, range 5 m. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 03.5 `h03_briar_snare` · บ่วงหนามป่า · Briar Snare
*Skill 5 · control · VFX preset `xs_h03_briar_snare` · budget class heroic*

An arrow bursts into a ring of thorned vines: enemies within 3 m are Rooted for 1.5 s.

| Field | Spec |
|---|---|
| Targeting · telegraph | ground target within 16 m · **AREA ring** r 3 m |
| Range · radius | range 16 m · r 3 m |
| Timing | 233 / 67 / 300 ms · **release f7** (233 ms) · clip `archer.skill_snare` 600 ms (18 f) |
| Clip events (ms) | nock 0, release 233 |
| Cooldown · cost · power | 14 s · 16 SP · 20 · physical · element `gale` |
| Effects | Rooted 1.5 s (elites 0.8 s; bosses -30 % move speed for 3 s) |
| Status → combo | none |
| Palette | core `#F6FFE8` · body `#8EDB4F` · edge `#6B4A2B` · accent `#FFB84A` |
| Peak coverage | 15 % at the 13 m camera |
| SFX | `sfx.h03.briar_snare` · .release / .burst / .creak |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–583 | `vfx_arrow`, `vfx_motes` | The arrowhead glows amber-green; seed motes trail the arrow. | Medium+ |
| Mesh core | 583–2,100 | `vfx_thorn_ring` | 10 thorned vine arcs burst up with back-out and coil around targets; amber thorn glints. | all tiers |
| Secondaries | 583–1,500 | `vfx_motes` | Leaf and petal particles; seed pods popping. | Medium+ (×0.5 on Medium) |
| Ground layer | 583–2,400 | `vfx_ground_cracks`, `vfx_rune_leaf` | Root cracks with a bark seam and a leaf-notch ring r 3 m. | all tiers |
| After-effect | 2,100–2,900 | `vfx_motes` | The vines wither with noise erosion; leaves fall. | Medium+ |
| Light | 583–800 | pooled `PointLight` | #8EDB4F, range 6 m. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer + telegraph; no light.

#### 03.6 `h03_featherstorm` · ฝูงขนนกพายุ · Featherstorm Murmuration
*Skill 6 · ultimate + damage · VFX preset `xs_h03_featherstorm` · budget class ultimate*

One great moon-arrow shot skyward bursts into a murmuration of 24 feather-blades that swirl and dive over a 6 m field in waves, ending in a crescent dive.

| Field | Spec |
|---|---|
| Targeting · telegraph | ground target within 20 m · **HEAVY ring** r 6 m |
| Range · radius | range 20 m · r 6 m |
| Timing | 600 / 100 / 300 ms · **release f18** (600 ms) · clip `archer.skill_featherstorm` 1,000 ms (30 f) |
| Zone / follow-up | 1000-2800 ms; final dive at 2800 ms (she can act after 1000 ms) |
| Clip events (ms) | nock 0, release 600 |
| Cooldown · cost · power | 85 s · 40 SP · 24 × 20 (max 8 hits per target = 160) + 60 dive · heavy · physical · element `gale` |
| Status → combo | Marked 8 s → C7 Faultline (+ Cracked from 01) · Gusted 4 s → C8 Plaguewind (+ Venom from 05) |
| Palette | core `#F4FFF8` · body `#5CE6A0` · edge `#1F9E86` · accent `#FFB84A` · moon `#DDE6F2` |
| Peak coverage | 40 % at the 13 m camera |
| SFX | `sfx.h03.featherstorm` · .sky_shot / .burst / .murmuration_loop / .dive |

| Layer | Time (ms) | Kit | What it does | Tier |
|---|---|---|---|---|
| Anticipation | 0–1,000 | `vfx_arrow`, `vfx_motes` | The moon-arrow streaks up with a jade-amber trail; a pale crescent-moon billboard (5 m, a vfx_motes crescent cell) appears 8 m above the field. | Medium+ |
| Mesh core | 1,000–2,800 | `vfx_feather_blade` | 24 feather-blades (thin-instanced, 1 draw) flock in a deterministic spiral murmuration and dive in waves; Low keeps 12. | all tiers |
| Secondaries | 1,000–2,800 | `vfx_motes`, `vfx_fb_impact` | Shed feathers, wind ribbons on 6 lead blades, impact puffs per dive. | Medium+ (×0.5 on Medium) |
| Ground layer | 1,000–3,800 | `vfx_swirl_arms`, `vfx_rune_leaf` | A large jade swirl r 6 m turning, feather-cut marks and the leaf ring. | all tiers |
| After-effect | 2,800–4,300 | `vfx_impact_star`, `vfx_shock_ring`, `vfx_motes` | The crescent dive impact (amber star and shock ring), then falling feathers and mist for 1.5 s. | all tiers |
| Light | 1,000–3,100 | pooled `PointLight` | #7DFFC8, range 12 m sustained at 2; amber flash 8 → 0 at 2800 ms. | High+ |

**Tiers:** Medium: same shapes and palette; drops light; secondaries ×0.5. Low: mesh core, ground layer, after-effect + telegraph; no light.
**Readability:** Blades are thin and dark-edged and dive in waves, never all at once; enemies inside stay visible.

## 5. Shared VFX kit

Kit v1 (21 assets, `assets/vfx/kit-v1/`) stays. Kit v2 adds 28 assets (12 meshes, 8 decals and sigils, 6 flipbooks and sprite sheets, 2 atlases) plus 2 gameplay props. Same recipe as v1: Blender 5.2 scripts, greyscale intensity in RGB plus coverage in A, so one texture serves every palette through `vfx_ramps`; meshes carry UVs for erosion and scrolling; every file gets a receipt entry. Each new asset is used by two or more skills or reactions, or is a hero signature (crystal lance, hex sigil, feather blade, thorn ring, forge hammer).

| Asset | Kind | Kit | Spec | Used by skills | Reactions | First needed |
|---|---|---|---|---|---|---|
| `vfx_spectral_blade` | mesh | v1 (exists) | ≤ 400 tris; chunky 2.1 m blade with fuller, guard and grip; UV0 v along the blade for erosion; vertex colour edge mask | 3: 1·bladeward_nova, 1·ironfall_cleave, 1·stormfall_cleave | - | step 2 (01) |
| `vfx_funnel` | mesh | v1 (exists) | ≤ 600 tris; funnel/cone with spiral UVs for scrolling; used upright (funnels, geysers, whirls) and inverted (depth) | 6: 2·hoarfrost_gale, 2·starless_hollow, 6·boiler_leap, 4·sunpalm_wave, 4·noonspring_covenant, 3·brushtail_vault | C3, C8 | step 1 (02) |
| `vfx_cone_burst` | mesh | v1 (exists) | ≤ 200 tris; open cone along +Z for release and muzzle bursts and bow waves | 6: 2·hoarfrost_gale, 1·compass_rush, 6·cog_sentry, 4·sunpalm_wave, 4·pilgrims_horn, 3·crescent_howl | - | step 1 (02) |
| `vfx_ring_wall` | mesh | v1 (exists) | ≤ 256 tris; open cylinder h 1 r 1, UV v along the height; also hollow light pillars (scaled tall) and water/steam rings | 10: 2·rimeshard_nova, 2·starless_hollow, 2·star_lance, 1·bladeward_nova, 1·eightfold_ward, 6·boiler_leap, 4·dawn_mend, 4·sunwheel_sanctum, 4·noonspring_covenant, 3·brushtail_vault | C1 | step 1 (02) |
| `vfx_rune_circle_outer` | decal | v1 (exists) | 2048²; double border, 48 ticks, 24 seeded-grammar glyphs | 2: 2·starless_hollow, 2·celestial_orrery | - | step 1 (02) |
| `vfx_rune_circle_inner` | decal | v1 (exists) | 1024²; heptagram, inner circle, 7 node glyphs (the witch's signature) | 4: 2·starless_hollow, 2·star_lance, 2·moonveil_ward, 2·celestial_orrery | - | step 1 (02) |
| `vfx_rune_ring_blade` | decal | v1 (exists) | 1024²; thin ring with 12 notches | 2: 2·rimeshard_nova, 1·bladeward_nova | - | step 1 (02) |
| `vfx_swirl_arms` | decal | v1 (exists) | 1024²; 6 tapered spiral arms, dark centre in A | 5: 2·hoarfrost_gale, 2·starless_hollow, 4·sunpalm_wave, 3·brushtail_vault, 3·featherstorm | C8 | step 1 (02) |
| `vfx_shock_ring` | decal | v1 (exists) | 512²; sharp outer edge, soft inner falloff, noise-broken rim | 13 skills: 02 ×4, 01 ×3, 05 ×1, 06 ×1, 04 ×1, 03 ×3 | C1, C2, C3, C5 | step 1 (02) |
| `vfx_impact_star` | decal | v1 (exists) | 512²; 8-12 uneven rays with a hot core (decal or billboard) | 10: 2·basic, 2·rimeshard_nova, 2·star_lance, 2·celestial_orrery, 1·bladeward_nova, 1·stormfall_cleave, 5·fangfall, 6·forgeheart_slam, 4·sunpalm_wave, 3·featherstorm | C7 | step 1 (02) |
| `vfx_ground_cracks` | decal | v1 (exists) | 1024²; radial branching cracks: R seam glow, G scorch darkening | 9: 2·hoarfrost_gale, 2·rimeshard_nova, 2·moonveil_ward, 1·lodestar_arc, 1·bladeward_nova, 1·stormfall_cleave, 6·forgeheart_slam, 6·gearstorm_hammerfall, 3·briar_snare | C7 | step 1 (02) |
| `vfx_scorch` | decal | v1 (exists) | 1024²; burn mark with ember speckle | 8: 2·starless_hollow, 2·celestial_orrery, 1·stormfall_cleave, 6·basic, 6·forgeheart_slam, 6·cog_sentry, 6·gearstorm_hammerfall, 4·pilgrims_horn | - | step 1 (02) |
| `vfx_streak` | scroll | v1 (exists) | 256×1024 tileable wind streaks for scrolling (also lane and wake decals) | 9: 2·hoarfrost_gale, 2·star_lance, 1·compass_rush, 5·duskstep, 6·cog_sentry, 4·springwell_rain, 4·sunpalm_wave, 3·featherfan_volley, 3·crescent_howl | - | step 1 (02) |
| `vfx_palm_sigil` | billboard | v1 (exists) | 1024²; original open-palm sigil in a rune disc | 1: 4·sunpalm_wave | - | step 5 (04) |
| `vfx_noise_erosion` | utility | v1 (exists) | 512² tileable fbm for every dissolve | every effect (implicit) | - | step 1 |
| `vfx_soft_disc` | utility | v1 (exists) | soft radial disc for fills, glows and shadow discs | 1: 4·sunwheel_sanctum | C5 | step 5 (04) |
| `vfx_fb_dust` | flipbook | v1 (exists) | 8×8 × 128; volumetric puff, 64 frames | 11 skills: 02 ×1, 01 ×5, 05 ×1, 06 ×1, 04 ×1, 03 ×2 | - | step 1 (02) |
| `vfx_fb_lightning` | flipbook | v1 (exists) | 4×4 × 256; 16 jagged arc variants (lightning, star-threads, magnetic lines by ramp) | 9: 2·rimeshard_nova, 2·starless_hollow, 2·celestial_orrery, 1·basic, 1·lodestar_arc, 1·bladeward_nova, 1·eightfold_ward, 1·stormfall_cleave, 6·mending_anvil | C1, C4 | step 1 (02) |
| `vfx_fb_impact` | flipbook | v1 (exists) | 4×4 × 256; radial streak burst, expand → thin → fade | 5: 2·starless_hollow, 2·star_lance, 3·basic, 3·featherfan_volley, 3·featherstorm | - | step 1 (02) |
| `vfx_fb_swirl` | flipbook | v1 (exists) | 4×4 × 256; rotating wind swirl | 3: 2·hoarfrost_gale, 4·sunpalm_wave, 3·featherfan_volley | - | step 1 (02) |
| `vfx_shards` | sprites | v1 (exists) | 4×4 × 128; 16 shard silhouettes with a bevel highlight (ice, steel, rock, gear teeth by ramp) | 10: 2·rimeshard_nova, 2·moonveil_ward, 1·lodestar_arc, 1·bladeward_nova, 1·ironfall_cleave, 1·compass_rush, 1·stormfall_cleave, 5·violet_masquerade, 6·forgeheart_slam, 6·gearstorm_hammerfall | C7 | step 1 (02) |
| `vfx_crescent_slash` | mesh | **v2 (new)** | ≤ 300 tris; crescent ribbon with 60/120/180° variants; UV u along the sweep (wipe), v across (core → edge); used flat and vertical, single and as X-pairs | 11 skills: 02 ×1, 01 ×3, 05 ×4, 06 ×1, 03 ×2 | - | step 1 (02) |
| `vfx_crystal_shard` | mesh | **v2 (new)** | ≤ 120 tris; hexagonal prism with a pointed tip (2.6 m at scale 1), UV v along the length; by scale it is a shard, moon, diamond or needle | 3: 2·rimeshard_nova, 2·moonveil_ward, 2·celestial_orrery | C2 | step 1 (02) |
| `vfx_crystal_lance` | mesh | **v2 (new)** | ≤ 400 tris; 2.6 m faceted spear with a four-point star head; gold inlay mask in vertex colour | 1: 2·star_lance | - | step 1 (02) |
| `vfx_hex_dome` | mesh | **v2 (new)** | ≤ 500 tris; geodesic hex dome r 1 with per-facet IDs in vertex colour for hit flashes; fresnel; also brass and gold shield shimmers | 3: 2·moonveil_ward, 6·mending_anvil, 4·pilgrims_horn | - | step 1 (02) |
| `vfx_shield_sigil` | mesh | **v2 (new)** | ≤ 160 tris; rounded shield plate 1.4 m with a compass-star relief (normal-faked) | 2: 1·compass_rush, 1·eightfold_ward | - | step 2 (01) |
| `vfx_orbit_ring` | mesh | **v2 (new)** | ≤ 256 tris; thin torus r 1 with a flat band face for tick or gear-tooth textures | 2: 2·celestial_orrery, 6·gearstorm_hammerfall | - | step 1 (02) |
| `vfx_arrow` | mesh | **v2 (new)** | ≤ 80 tris; arrow with leaf fletching matching hero 03 | 6: 3·basic, 3·amberwatch_arrow, 3·featherfan_volley, 3·crescent_howl, 3·briar_snare, 3·featherstorm | - | step 6 (03) |
| `vfx_feather_blade` | mesh | **v2 (new)** | ≤ 60 tris; curved 0.9 m feather blade, card with thickness | 1: 3·featherstorm | - | step 6 (03) |
| `vfx_thorn_ring` | mesh | **v2 (new)** | ≤ 600 tris; 10 thorned vine arcs on a ring r 1; UV v along each vine for grow-in | 1: 3·briar_snare | - | step 6 (03) |
| `vfx_diamond_knife` | mesh | **v2 (new)** | ≤ 60 tris; diamond-section throwing knife 0.35 m | 2: 5·diamond_scatter, 5·violet_masquerade | - | step 3 (05) |
| `vfx_flask` | mesh | **v2 (new)** | ≤ 120 tris; brass-capped flask; grease flask, smoke bomb and beacon variants by ramp and emissive | 3: 5·nightbloom_smoke, 6·grease_flask, 6·gearstorm_hammerfall | - | step 3 (05) |
| `vfx_forge_hammer` | mesh | **v2 (new)** | ≤ 1,200 tris; 5 m brass forge-hammer head with a vent emissive mask | 1: 6·gearstorm_hammerfall | - | step 4 (06) |
| `vfx_rune_compass` | decal | **v2 (new)** | 1024²; eight-point compass ring with four-point star ticks (from the orc's armour) | 2: 1·eightfold_ward, 1·stormfall_cleave | C1 | step 2 (01) |
| `vfx_rune_sunwheel` | decal | **v2 (new)** | 2048²; 12-spoke sun-wheel, double ring, sun glyphs (from the bull's emblems); also a sun-disc billboard | 5: 4·basic, 4·dawn_mend, 4·pilgrims_horn, 4·sunwheel_sanctum, 4·noonspring_covenant | C5 | step 5 (04) |
| `vfx_rune_diamond` | decal | **v2 (new)** | 1024²; diamond-lattice ring (from the rogue's cape hem) | 2: 5·nightbloom_smoke, 5·violet_masquerade | - | step 3 (05) |
| `vfx_gear_ring` | decal | **v2 (new)** | 1024²; gear-tooth ring with an inner rivet ring (from the tinker's choker); also the texture of the gear vfx_orbit_ring | 4: 6·forgeheart_slam, 6·cog_sentry, 6·mending_anvil, 6·gearstorm_hammerfall | - | step 4 (06) |
| `vfx_rune_leaf` | decal | **v2 (new)** | 1024²; leaf-notch ring (from the archer's cape leaves) | 2: 3·briar_snare, 3·featherstorm | - | step 6 (03) |
| `vfx_ground_split` | decal | **v2 (new)** | 1024×256 strip; long crack with an emissive seam (R) and scorch (G); also used vertically on targets | 3: 1·ironfall_cleave, 1·compass_rush, 1·stormfall_cleave | C7 | step 2 (01) |
| `vfx_liquid_pool` | decal | **v2 (new)** | 1024²; puddle and splatter mask (A) with ripple normals in RG; thin-film ramp option for oil | 7: 5·adders_kiss, 5·diamond_scatter, 5·fangfall, 5·violet_masquerade, 6·grease_flask, 4·springwell_rain, 4·noonspring_covenant | C2, C3, C4, C6, C8 | step 3 (05) |
| `vfx_hex_sigil` | billboard | **v2 (new)** | 1024²; a crescent moon cradling a six-point snow crystal inside a rune disc (the witch's gale sigil) | 1: 2·hoarfrost_gale | - | step 1 (02) |
| `vfx_fb_smoke` | flipbook | **v2 (new)** | 8×8 × 128; curling painterly puff: plum smoke, pearl steam or lime mist by ramp | 14 skills: 01 ×1, 05 ×5, 06 ×6, 04 ×2 | C2, C3, C5, C8 | step 2 (01) |
| `vfx_fb_flame` | flipbook | **v2 (new)** | 4×4 × 256; stylised flame tongues (Scorched marker, slag, forge heat) | 2: 6·forgeheart_slam, 6·gearstorm_hammerfall | - | step 4 (06) |
| `vfx_fb_splash` | flipbook | **v2 (new)** | 4×4 × 256; liquid crown splash (water, oil, venom by ramp) | 9: 5·adders_kiss, 5·diamond_scatter, 5·fangfall, 5·violet_masquerade, 6·grease_flask, 4·springwell_rain, 4·sunpalm_wave, 4·pilgrims_horn, 4·noonspring_covenant | C4, C6 | step 3 (05) |
| `vfx_fb_ripple` | flipbook | **v2 (new)** | 4×4 × 128; expanding ripple rings for wet ground | 2: 4·springwell_rain, 4·noonspring_covenant | C4, C6 | step 5 (04) |
| `vfx_fb_cloud` | flipbook | **v2 (new)** | 4×4 × 256; soft lit cloud puffs (rain cloud, storm cloud) | 2: 1·stormfall_cleave, 4·springwell_rain | - | step 2 (01) |
| `vfx_motes` | sprites | **v2 (new)** | 4×4 × 64 sprite atlas: 4-point star, 7-point star, crescent, snow crystal, leaf, feather, diamond petal, gear, droplet, ember, glint, rivet, bubble, thorn, spark, seed. Every hero's secondaries come from this one texture and one material | 42 skills: 02 ×7, 01 ×7, 05 ×7, 06 ×7, 04 ×7, 03 ×7 | C1, C2, C3, C4, C5, C6, C7, C8 | step 1 (02) |
| `vfx_ramps` | atlas | **v2 (new)** | 256×64 palette ramp atlas: one row per palette (6 heroes × 2 variants, 8 reactions, telegraph rows), sampled by every material via a per-instance row index | every effect (implicit) | - | step 1 |
| `vfx_sigil_atlas` | atlas | **v2 (new)** | 1024² atlas: 12 status glyphs, derived-state chips (Dazed, Exposed, Scalded, Jolted, Stunned, Rooted, Taunted) and the hero sigils (compass, heptagram, amber diamond-eye, sun-wheel, diamond mask, gear lens); all status markers draw in one thin-instanced call | 3: 2·moonveil_ward, 5·violet_masquerade, 3·amberwatch_arrow | C5 | step 1 (02) |
| `prop_cog_sentry` | prop | **v2 (new)** | gameplay actor, not VFX: ≤ 1,500 tris, 512² texture, LOD1 600; spinning gear and lens bones | 1: 6·cog_sentry | - | step 4 (06) |
| `prop_anvil_pylon` | prop | **v2 (new)** | gameplay actor, not VFX: ≤ 800 tris, 512² texture; anvil on a brass tripod with a teal lens and a gear ring | 1: 6·mending_anvil | - | step 4 (06) |

Skill ids in the usage column are written `hero·name` (for example `2·starless_hollow` = `h02_starless_hollow`); assets used by more than 10 skills show counts per hero.

### 5.1 Shared materials

- `M_add_ramp`: additive; greyscale texture x ramp row; most glows, motes and flipbooks.
- `M_alpha_ramp`: alpha-blended, value-lifted darkness (abyss, smoke, oil, shadow discs); never below sRGB 40 under characters.
- `M_fresnel_erosion`: mesh cores: fresnel rim + body ramp + noise-erosion dissolve + UV scroll.
- `M_decal_stack`: ground layers: up to 3 decal layers in one shader, depth-fade, conforms to terrain; renders under characters.
- `M_ribbon`: TrailMesh ribbons: ramp along the length, taper, soft edges.
- All five ship GLSL and WGSL, are compiled and prewarmed with the pool before the first cast (no first-use hitch), and read the palette from `vfx_ramps` by a per-instance row index, so 36 skills do not create 36 shader variants.

### 5.2 Data-driven pool (inbox B13)

- One scene-owned pool holds `ParticleSystem` / `GPUParticleSystem` / `NodeParticleSystemSet` snippets, thin-instanced meshes, decal stacks, ribbons and the 2 lights. A skill preset is data: its layers (kit ids, time window, min tier, Medium scale), its palette row and its telegraph. `hero-skills.json` already carries that data per skill.
- Variants (`@crystal`, `@frost`, `@sun`) are the same preset with a different core asset and ramp row. Reactions and status markers are presets in the same pool.
- `combat-vfx-skills.ts` (917 lines of per-skill code today) can shrink to a preset loader. The code change belongs to the VFX lane.

## 6. Weapons

| Hero | Weapon | Route | Source image | Credits | Length (base → readability target) | Tris LOD0 / 1 / 2 | Textures · emissive | Markers | Sockets | Trail |
|---|---|---|---|---|---|---|---|---|---|---|
| 01 Orc Swordsman | Longsword (gold hilt, blue gems) | **Tripo P2.0 single image** | `Downloads\hero\01\ChatGPT Image Oct 1, 2026, 01_15_52 PM.png` | 135 | 1.10 m → 1.32 m (+20 %) | 2,500 / 1,200 / 400 | 1024² albedo, normal, ORM · blue gems ≤ 0.3 (charge glow uniform) | grip origin, +Y; fx_base (guard), fx_tip (point) | socket_weapon_R; grip_secondary for two-hand skills; sheathed on socket_back | ribbon 12 segments, 160 ms basics / 240 ms skills, width = blade |
| 02 Witch | Crystal staff (blue crystal, gold ribbons) | **Blender** | `Downloads\hero\02\ChatGPT Image Oct 1, 2026, 01_15_58 PM.png; the Tripo staff GLB (hero02_staff_p20_smartuv_pbr_source_4k.glb, 15,423 tris) is the shape and bake reference only` | 0 | 1.80 m → 2.00 m (cap: no taller than crown + 0.25 m) | 2,500 / 1,200 / 400 | 1024² albedo, normal, ORM + emissive mask · crystal ≤ 0.9, never clipping under env-glow | grip origin, +Y; fx_base (heel), fx_tip (crystal top), fx_head (crystal centre = cast origin) | socket_weapon_R; left hand on grip_secondary; socket_back | crystal-arc ribbon 10 segments, 200 ms, only on the Nova slam and basic link 2 |
| 03 Wolf-kin Archer | Recurve bow (teal and gold, horn tips) + arrows + quiver | **Blender** | `Downloads\hero\03\ChatGPT Image Oct 1, 2026, 01_16_20 PM.png` | 0 | 1.35 m → 1.62 m (+20 %) | 2,500 / 1,200 / 400 including the string strip; arrow ≤ 80; quiver ≤ 1,200 | 1024² albedo, normal, ORM · none (the amber sigils are VFX) | grip origin; fx_tip (upper limb tip), fx_base (lower limb tip), fx_nock (string centre = arrow spawn), fx_head (arrow rest) | socket_weapon_L (bow); socket_weapon_R (arrow); socket_back (quiver with an arrow-draw marker) | limb-arc ribbon only on Brushtail Vault; arrows carry their own ribbons |
| 04 Bull-kin Acolyte | Sun-ring sceptre (gold ring, cyan crystal) | **Blender** | `Downloads\hero\04\ChatGPT Image Oct 1, 2026, 01_16_04 PM.png` | 0 | 1.55 m → 1.86 m (+20 %) | 2,500 / 1,200 / 400 | 1024² albedo, normal, ORM + emissive mask · cyan crystal ≤ 0.9 | grip origin, +Y; fx_base, fx_tip (ring top), fx_head (crystal in the ring = heal and beam origin) | socket_weapon_R; socket_weapon_L as the two-hand cast target; socket_back | short gold arc ribbon, 10 segments, 140 ms, on basics |
| 05 Rogue Thief | Curved dagger ×2 (purple gem); off-hand is a mirrored copy | **Tripo P2.0 single image** | `planning/evidence/turnaround-qa-20261002/hero-05/weapon-crop/dagger_left.png (turnaround QA PASS, 9 WARN)` | 135 | 0.40 m → 0.48 m (+20 %) | 1,200 / 600 / 250 each | 512² albedo, normal, ORM · purple gem ≤ 0.3 | grip origin, +Y; fx_base, fx_tip (the runtime adds _R / _L per socket) | socket_weapon_R and socket_weapon_L (forward and reverse grip); sheaths on socket_hip_L / socket_hip_R | two thin ribbons, 8 segments, 100 ms |
| 06 Tinker Merchant | Wrench-head war hammer (brass and steel) | **Tripo P2.0 single image (the 3/4 view is accepted)** | `Downloads\hero\06\ChatGPT Image Oct 1, 2026, 01_16_12 PM.png` | 135 | 0.90 m → 1.08 m (+20 %) | 2,500 / 1,200 / 400 | 1024² albedo, normal, ORM + small emissive mask in the head vents · vent heat ≤ 0.6 (Forgeheart uniform) | grip origin, +Y; fx_base (haft collar), fx_tip (striking face), fx_head (head centre = spark and steam origin) | socket_weapon_R; socket_weapon_L for two-handed swings; wrench prop on socket_hip_R | chunky ribbon 12 segments, 180 ms |

Tripo spend: 405 credits for three weapons at 135 each (100 generate + 20 Smart UV + 10 for a 2K texture + 5 PBR; credit guard §5.5 and §6: the runtime map is 1024², so 4K or 8K buys nothing), inside the 2,500 ceiling that opens once Claude passes hero 01's geometry; Blender weapons cost 0. The +20 % lengths follow the approved readability pass (weapons +15-25 %) and are confirmed on the 13 m greybox.

**Trail and socket spec (every weapon):**
- Origin at the grip centre, long axis +Y in Babylon. Child empties exported as glTF nodes: `fx_base` and `fx_tip` on every weapon; `fx_head` on the staff, sceptre and hammer; `fx_nock` on the bow. The names are a contract and the runtime validator checks them.
- **Name clash to avoid:** the rig also has a hero anchor called `fx_head` (with `fx_chest`, `fx_hand_L/R`, `fx_feet`). Resolve markers relative to their owner (`<weapon root>/fx_head` versus the skeleton's `fx_head`), never by a global name search. In this doc, `fx_head` in a weapon context means the weapon marker; the rig anchor is written "rig anchor fx_head".
- `combat-fx.ts` reads the markers' world matrices every frame instead of the hard-coded (0, -0.45, 0) → (0, 0.97, 0) Warrior points (a VFX-lane change).
- `TrailMesh`: segments and life per hero (see each hero's identity table); width = |tip - base| with a taper; colour from the hero's `vfx_ramps` row; switched by the clip sidecar's `trail_on` / `trail_off` events. At most 2 trails per hero (the daggers).
- Weapon emissive (gems, crystals, vents) is a per-instance uniform driven by skills, capped (metal gems ≤ 0.3, hammer vents ≤ 0.6, crystals ≤ 0.9) so it never clips under `env-glow`.
- Budgets: LOD0 / 1 / 2 at 2,500 / 1,200 / 400 tris (daggers 1,200 / 600 / 250); 1024² albedo, normal and ORM (512² for daggers); a separate GLB and material per weapon.

## 7. Animation needs per hero

Clip ids follow the rig contract (`<set>.<action>`, 30 fps, in place, root motion off, events as pose markers). The owner's list per hero is idle, walk, run, basic attack ×2, 6 skill clips, hit, dodge and death; guard and potion clips come from the stance and base templates. Release frames come from the timing above.

**Caution on UAL names:** the names below come from the UAL1 v1 inspection and the UAL2 free list in the rig doc. UAL v2.0 renamed the rig, so re-inspect the current download before writing bone maps. Retimes are non-linear (compress the wind-up, keep the active arc within ±30 %); never speed a clip up to hide a state gap. UAL's free tiers have no bow clips, so hero 03's bow set is authored.

### 7.02 Witch: sets base + caster + mage, display_scale 1.000

| Clip | Length ms (frames) | Release / events | Skill | First source to retarget |
|---|---|---|---|---|
| `base.idle (+ stance idle)` | 2,500 (75), loop | - | shared base set | UAL1 Idle_Loop; stance idle `caster.idle`: UAL1 Spell_Simple_Idle_Loop (staff held ready) |
| `base.walk` | ≈1,067 (32), loop | foot_l 0, foot_r 50 % | shared base set | UAL1 Walk_Loop (keep if the implied speed fits within 15 % retime) |
| `base.run` | 700 (21), loop | foot_l 0, foot_r 350 | shared base set | UAL1 Jog_Fwd_Loop or Sprint_Loop, whichever stride fits 4.5 m/s |
| `base.hit_light / base.hit_heavy` | 300 (9) / 600 (18) | body_impact 0 (heavy) | shared base set | UAL1 Hit_Chest / UAL2 KNOCKBACK |
| `base.dodge` | 400 (12) = 280 dash + 120 | whoosh 0, foot_l 233 | shared base set | author (a 1,458 ms roll cannot shrink to 280 ms) |
| `base.death` | 2,000-2,400 (60-72) | body_impact measured; ends grounded | shared base set | UAL1 Death01, Tier P per hero |
| `caster.attack_1 / caster.attack_2` | 400 (12) | **f3** · link_open f12 | basic ×2 | UAL1 Spell_Simple_Shoot (500 ms) retimed to 400 ms, release at 100; link 2 as a mirrored staff flick |
| `mage.skill_gale` | 467 (14) | **f6** | S1 Hoarfrost Gale | UAL1 Spell_Simple_Enter (cut) + Spell_Simple_Shoot, retimed to release at f6 |
| `mage.skill_nova` | 600 (18) | **f6** · plant f4 | S2 Rimeshard Nova | author (staff heel slammed into the ground); UAL1 Jump_Land as the weight reference |
| `mage.skill_hollow` | 900 (27) | **f18** · rune f0, slam f18, pulse f27 | S3 Starless Hollow | author caster.cast_ground from UAL1 Spell_Simple_Enter (staff raise) into a slam |
| `mage.skill_lance` | 833 (25) | **f14** | S4 Sapphire Star Lance | author (two-hand staff thrust); timing base UAL1 Spell_Simple_Shoot |
| `mage.skill_ward` | 667 (20) | **f9** | S5 Moonveil Ward | UAL1 Spell_Simple_Enter → Spell_Simple_Exit (pointing at the ally), retimed |
| `mage.skill_orrery` | 1,300 (39) | **f27** | S6 Celestial Orrery | UAL1 Spell_Simple_Idle_Loop (arms raised) as the hold, plus an authored release |

UAL CC0 clips to retarget: UAL1 Idle_Loop, UAL1 Spell_Simple_Idle_Loop, UAL1 Walk_Loop, UAL1 Jog_Fwd_Loop, UAL1 Sprint_Loop, UAL2 KNOCKBACK, UAL1 Hit_Chest, UAL1 Death01, UAL1 Spell_Simple_Shoot, UAL1 Spell_Simple_Enter, UAL1 Jump_Land, UAL1 Spell_Simple_Exit.

### 7.01 Orc Swordsman: sets base + blade_1h + swordsman, display_scale 1.111

| Clip | Length ms (frames) | Release / events | Skill | First source to retarget |
|---|---|---|---|---|
| `base.idle (+ stance idle)` | 2,500 (75), loop | - | shared base set | UAL1 Idle_Loop; stance idle `blade_1h.idle`: UAL1 Sword_Idle |
| `base.walk` | ≈1,067 (32), loop | foot_l 0, foot_r 50 % | shared base set | UAL1 Walk_Loop (keep if the implied speed fits within 15 % retime) |
| `base.run` | 700 (21), loop | foot_l 0, foot_r 350 | shared base set | UAL1 Jog_Fwd_Loop or Sprint_Loop, whichever stride fits 4.5 m/s |
| `base.hit_light / base.hit_heavy` | 300 (9) / 600 (18) | body_impact 0 (heavy) | shared base set | UAL1 Hit_Chest / UAL2 KNOCKBACK |
| `base.dodge` | 400 (12) = 280 dash + 120 | whoosh 0, foot_l 233 | shared base set | author (a 1,458 ms roll cannot shrink to 280 ms) |
| `base.death` | 2,000-2,400 (60-72) | body_impact measured; ends grounded | shared base set | UAL1 Death01, Tier P per hero |
| `blade_1h.attack_1 / blade_1h.attack_2` | 400 (12) | **f3** · trail_on f2, trail_off f5, link_open f12 | basic ×2 | UAL2 SWORD_REGULAR_A (+ _REC) for link 1, SWORD_REGULAR_A_COMBO split for link 2; wind-up compressed to 100 ms |
| `swordsman.skill_arc` | 700 (21) | **250 ms (f7.5; pose on f8)** · trail_on f6, trail_off f10 | S1 Lodestar Arc | UAL1 Sword_Attack (1,500 ms) non-linearly retimed to 700 ms, or UAL2 SWORD_REGULAR_A_COMBOB if its arc fits 120° |
| `swordsman.skill_nova` | 600 (18) | **f6** · plant f4 | S2 Bladeward Nova | author (two-hand sword plant); UAL2 IDLE_SHIELD as the brace pose |
| `swordsman.skill_ironfall` | 833 (25) | **f10** · trail_on f9, trail_off f13 | S3 Ironfall Cleave | author a two-hand overhead from the UAL2 SWORD_REGULAR_A_COMBOB end pose; UAL1 Jump_Land for the weight drop |
| `swordsman.skill_rush` | 767 (23) | **f4** · whoosh f0, hit f9 | S4 Compass Rush | UAL2 SWORD_DASH retimed to the 400 ms dash |
| `swordsman.skill_ward` | 700 (21) | **f9** · plant f9 | S5 Eightfold Ward | author (sword plant + roar); UAL2 IDLE_SHIELD for the hold |
| `swordsman.skill_stormfall` | 1,367 (41) | **f20** · takeoff f9, land f21 | S6 Stormfall Cleave | UAL1 Jump_Start + Jump_Land retimed, plus an authored two-hand slam |

UAL CC0 clips to retarget: UAL1 Idle_Loop, UAL1 Sword_Idle, UAL1 Walk_Loop, UAL1 Jog_Fwd_Loop, UAL1 Sprint_Loop, UAL2 KNOCKBACK, UAL1 Hit_Chest, UAL1 Death01, UAL2 SWORD_REGULAR_A_COMBO, UAL2 SWORD_REGULAR_A, UAL2 SWORD_REGULAR_A_REC, UAL2 SWORD_REGULAR_A_COMBOB, UAL1 Sword_Attack, UAL2 IDLE_SHIELD, UAL1 Jump_Land, UAL2 SWORD_DASH, UAL1 Jump_Start.

### 7.05 Rogue Thief: sets base + dual_dagger + thief, display_scale 0.989

| Clip | Length ms (frames) | Release / events | Skill | First source to retarget |
|---|---|---|---|---|
| `base.idle (+ stance idle)` | 2,500 (75), loop | - | shared base set | UAL1 Idle_Loop; stance idle `dual_dagger.idle`: authored (reverse-grip guard) |
| `base.walk` | ≈1,067 (32), loop | foot_l 0, foot_r 50 % | shared base set | UAL1 Walk_Loop (keep if the implied speed fits within 15 % retime) |
| `base.run` | 700 (21), loop | foot_l 0, foot_r 350 | shared base set | UAL1 Jog_Fwd_Loop or Sprint_Loop, whichever stride fits 4.5 m/s |
| `base.hit_light / base.hit_heavy` | 300 (9) / 600 (18) | body_impact 0 (heavy) | shared base set | UAL1 Hit_Chest / UAL2 KNOCKBACK |
| `base.dodge` | 400 (12) = 280 dash + 120 | whoosh 0, foot_l 233 | shared base set | author (a 1,458 ms roll cannot shrink to 280 ms) |
| `base.death` | 2,000-2,400 (60-72) | body_impact measured; ends grounded | shared base set | UAL1 Death01, Tier P per hero |
| `dual_dagger.attack_1 (R) / dual_dagger.attack_2 (L)` | 400 (12) | **f2** · trail_on f1, trail_off f4, link_open f12 | basic ×2 | UAL1 Punch_Jab / Punch_Cross with reverse-grip hand poses, or UAL2 MELEE_HOOK (+ _REC) |
| `thief.skill_kiss` | 500 (15) | **f4** · hit f7 | S1 Adder's Kiss | UAL1 Punch_Jab ×2 with dagger grips, retimed |
| `thief.skill_scatter` | 567 (17) | **f6** | S2 Diamond Scatter | UAL2 OVERHAND_THROW retimed to a flat side-arm throw |
| `thief.skill_fangfall` | 667 (20) | **f6** · takeoff f0 | S3 Fangfall | author (leap-spin) from UAL1 Jump_Start |
| `thief.skill_duskstep` | 467 (14) | **f2** · whoosh f0 | S4 Duskstep | UAL2 SLIDE (or SWORD_DASH) retimed to 200 ms |
| `thief.skill_smoke` | 567 (17) | **f7** | S5 Nightbloom Smoke | UAL2 OVERHAND_THROW (lob) |
| `thief.skill_masquerade` | 2,200 (66) | **f9** · hit f16, hit f24, hit f32, hit f39, hit f46, hit f54 | S6 Violet Masquerade | UAL2 MELEE_HOOK (+ _REC) per strike; authored vanish and appear poses |

UAL CC0 clips to retarget: UAL1 Idle_Loop, UAL1 Walk_Loop, UAL1 Jog_Fwd_Loop, UAL1 Sprint_Loop, UAL2 KNOCKBACK, UAL1 Hit_Chest, UAL1 Death01, UAL2 MELEE_HOOK, UAL2 MELEE_HOOK_REC, UAL1 Punch_Jab, UAL1 Punch_Cross, UAL2 OVERHAND_THROW, UAL1 Jump_Start, UAL2 SWORD_DASH, UAL2 SLIDE.

### 7.06 Tinker Merchant: sets base + heavy_1h + merchant, display_scale 0.956

| Clip | Length ms (frames) | Release / events | Skill | First source to retarget |
|---|---|---|---|---|
| `base.idle (+ stance idle)` | 2,500 (75), loop | - | shared base set | UAL1 Idle_Loop; stance idle `heavy_1h.idle`: authored (two-hand hammer rest) |
| `base.walk` | ≈1,067 (32), loop | foot_l 0, foot_r 50 % | shared base set | UAL1 Walk_Loop (keep if the implied speed fits within 15 % retime) |
| `base.run` | 700 (21), loop | foot_l 0, foot_r 350 | shared base set | UAL1 Jog_Fwd_Loop or Sprint_Loop, whichever stride fits 4.5 m/s |
| `base.hit_light / base.hit_heavy` | 300 (9) / 600 (18) | body_impact 0 (heavy) | shared base set | UAL1 Hit_Chest / UAL2 KNOCKBACK |
| `base.dodge` | 400 (12) = 280 dash + 120 | whoosh 0, foot_l 233 | shared base set | author (a 1,458 ms roll cannot shrink to 280 ms) |
| `base.death` | 2,000-2,400 (60-72) | body_impact measured; ends grounded | shared base set | UAL1 Death01, Tier P per hero |
| `heavy_1h.attack_1 / heavy_1h.attack_2` | 400 (12) | **f3** · trail_on f2, trail_off f5, link_open f12 | basic ×2 | UAL2 SWORD_REGULAR_A / _COMBO retimed heavier with a two-hand grip |
| `merchant.skill_slam` | 700 (21) | **f8** · trail_on f7, trail_off f11 | S1 Forgeheart Slam | author an overhead two-hand slam from the UAL2 SWORD_REGULAR_A_COMBOB end; UAL1 Jump_Land for weight |
| `merchant.skill_flask` | 567 (17) | **f7** | S2 Grease Flask | UAL2 OVERHAND_THROW |
| `merchant.skill_sentry` | 767 (23) | **f12** | S3 Cog Sentry | UAL1 Interact retimed (crank), or UAL1 PickUp_Table reversed (set down) |
| `merchant.skill_leap` | 933 (28) | **f4** · takeoff f4, land f22 | S4 Boiler Leap | UAL1 Jump_Start / Jump_Loop / Jump_Land retimed |
| `merchant.skill_anvil` | 900 (27) | **f14** · hit f4, hit f9 | S5 Mending Anvil | UAL1 Interact retimed (hammer taps) |
| `merchant.skill_hammerfall` | 867 (26) | **f12** | S6 Gearstorm Hammerfall | UAL2 OVERHAND_THROW (beacon) plus an authored point-up follow-through |

UAL CC0 clips to retarget: UAL1 Idle_Loop, UAL1 Walk_Loop, UAL1 Jog_Fwd_Loop, UAL1 Sprint_Loop, UAL2 KNOCKBACK, UAL1 Hit_Chest, UAL1 Death01, UAL2 SWORD_REGULAR_A, UAL2 SWORD_REGULAR_A_COMBOB, UAL1 Jump_Land, UAL2 OVERHAND_THROW, UAL1 Interact, UAL1 PickUp_Table, UAL1 Jump_Start, UAL1 Jump_Loop.

### 7.04 Bull-kin Acolyte: sets base + caster + heavy_1h + acolyte, display_scale 1.139

| Clip | Length ms (frames) | Release / events | Skill | First source to retarget |
|---|---|---|---|---|
| `base.idle (+ stance idle)` | 2,500 (75), loop | - | shared base set | UAL1 Idle_Loop; stance idle `caster.idle`: UAL1 Spell_Simple_Idle_Loop (sceptre held ready) |
| `base.walk` | ≈1,067 (32), loop | foot_l 0, foot_r 50 % | shared base set | UAL1 Walk_Loop (keep if the implied speed fits within 15 % retime) |
| `base.run` | 700 (21), loop | foot_l 0, foot_r 350 | shared base set | UAL1 Jog_Fwd_Loop or Sprint_Loop, whichever stride fits 4.5 m/s |
| `base.hit_light / base.hit_heavy` | 300 (9) / 600 (18) | body_impact 0 (heavy) | shared base set | UAL1 Hit_Chest / UAL2 KNOCKBACK |
| `base.dodge` | 400 (12) = 280 dash + 120 | whoosh 0, foot_l 233 | shared base set | author (a 1,458 ms roll cannot shrink to 280 ms) |
| `base.death` | 2,000-2,400 (60-72) | body_impact measured; ends grounded | shared base set | UAL1 Death01, Tier P per hero |
| `heavy_1h.attack_1 / heavy_1h.attack_2 (acolyte variant)` | 400 (12) | **f3** · trail_on f2, trail_off f5, link_open f12 | basic ×2 | UAL2 MELEE_HOOK (+ _REC) and SWORD_REGULAR_A retimed heavier |
| `acolyte.skill_rain` | 700 (21) | **f10** | S1 Springwell Rain | UAL1 Spell_Simple_Enter (sceptre raise) + Spell_Simple_Shoot |
| `acolyte.skill_palm` | 500 (15) | **f6** | S2 Sunpalm Wave | UAL1 Punch_Cross as an open-palm thrust, retimed |
| `acolyte.skill_mend` | 700 (21) | **f12** | S3 Dawn Mend | UAL1 Spell_Simple_Shoot (pointing) retimed |
| `acolyte.skill_rush` | 767 (23) | **f5** · whoosh f0, hit f10 | S4 Pilgrim's Horn Rush | UAL2 SWORD_DASH retimed, with an authored head-down pose |
| `acolyte.skill_sanctum` | 667 (20) | **f9** · plant f9 | S5 Sunwheel Sanctum | UAL1 Interact (sceptre plant) retimed, or authored |
| `acolyte.skill_covenant` | 1,500 (45) | **f24** | S6 Noonspring Covenant | UAL1 Spell_Simple_Idle_Loop (arms raised) + an authored sceptre raise |

UAL CC0 clips to retarget: UAL1 Idle_Loop, UAL1 Spell_Simple_Idle_Loop, UAL1 Walk_Loop, UAL1 Jog_Fwd_Loop, UAL1 Sprint_Loop, UAL2 KNOCKBACK, UAL1 Hit_Chest, UAL1 Death01, UAL2 SWORD_REGULAR_A, UAL2 MELEE_HOOK, UAL2 MELEE_HOOK_REC, UAL1 Spell_Simple_Enter, UAL1 Spell_Simple_Shoot, UAL1 Punch_Cross, UAL2 SWORD_DASH, UAL1 Interact.

### 7.03 Wolf-kin Archer: sets base + bow + archer, display_scale measure (crown without ears)

| Clip | Length ms (frames) | Release / events | Skill | First source to retarget |
|---|---|---|---|---|
| `base.idle (+ stance idle)` | 2,500 (75), loop | - | shared base set | UAL1 Idle_Loop; stance idle `bow.idle`: authored (bow held low) |
| `base.walk` | ≈1,067 (32), loop | foot_l 0, foot_r 50 % | shared base set | UAL1 Walk_Loop (keep if the implied speed fits within 15 % retime) |
| `base.run` | 700 (21), loop | foot_l 0, foot_r 350 | shared base set | UAL1 Jog_Fwd_Loop or Sprint_Loop, whichever stride fits 4.5 m/s |
| `base.hit_light / base.hit_heavy` | 300 (9) / 600 (18) | body_impact 0 (heavy) | shared base set | UAL1 Hit_Chest / UAL2 KNOCKBACK |
| `base.dodge` | 400 (12) = 280 dash + 120 | whoosh 0, foot_l 233 | shared base set | author (a 1,458 ms roll cannot shrink to 280 ms) |
| `base.death` | 2,000-2,400 (60-72) | body_impact measured; ends grounded | shared base set | UAL1 Death01, Tier P per hero |
| `bow.attack_1 / bow.attack_2` | 400 (12) | **f3** · nock f0, link_open f12 | basic ×2 | author (UAL free tiers have no bow clips; check UAL2 paid tiers only with owner approval) |
| `archer.skill_amberwatch` | 567 (17) | **f7** · nock f0 | S1 Amberwatch Arrow | author; timing base UAL1 Spell_Simple_Shoot |
| `archer.skill_volley` | 700 (21) | **f8** · nock f0 | S2 Featherfan Volley | author (bow); timing base UAL1 Spell_Simple_Shoot |
| `bow.draw (267) + bow.aim_loop (1,000, loop) + bow.release (300)` | 634 (19) | **f8** · nock f0, full_draw f7 | S3 Crescent Howl | author bow.draw / bow.aim_loop / bow.release |
| `archer.skill_vault` | 700 (21) | **f3** · takeoff f3, land f15 | S4 Brushtail Vault | author the backflip; UAL1 Jump_Start / Jump_Land as timing references (or UAL1 Roll reversed for the roll-out) |
| `archer.skill_snare` | 600 (18) | **f7** · nock f0 | S5 Briar Snare | author |
| `archer.skill_featherstorm` | 1,000 (30) | **f18** · nock f0 | S6 Featherstorm Murmuration | author the sky shot; UAL1 Jump_Start for the small hop |

UAL CC0 clips to retarget: UAL1 Idle_Loop, UAL1 Walk_Loop, UAL1 Jog_Fwd_Loop, UAL1 Sprint_Loop, UAL2 KNOCKBACK, UAL1 Hit_Chest, UAL1 Death01, UAL1 Spell_Simple_Shoot, UAL1 Jump_Start, UAL1 Jump_Land, UAL1 Roll.

## 8. Production order

Every skill runs the same loop: the froggy key-frame sheet (Stage A, 3 variants, Claude picks) → the VFX lane builds the preset → in-engine 8-frame contact sheet at the 13 m camera and at max zoom, day and night, over grass, stone and snow, in WebGPU and WebGL2 → compare with the froggy sheet (colourfulness M ≥ 45, coverage within ±5 points of the target, all 5 layers visible, telegraph radius within 2 %, silhouettes readable in greyscale, no white clipping, tier budgets measured with the full-scope method in the hand-off) → fix the 5 worst problems → re-capture; at least 3 passes, at most 6 before escalating.

### Step 1: hero 02 Witch

1. `xs_bladeward_nova`: fix the original blade skin against `sw_iron_rebuke` (hand-off upgrade #1: full circumferential ring at the live camera, blade and guard form, staggered rise), then add the `@crystal` skin → `h02_rimeshard_nova`. The blade skin is banked for `h01_bladeward_nova`.
2. `xs_gale_palm`: fix the palm skin against `fs_palm_wave` (upgrade #2: broad silhouette, volumetric wake, turbulent impact, 12 → ≤ 10 draws), then the `@frost` skin → `h02_hoarfrost_gale`. The palm skin is banked for `h04_sunpalm_wave`.
3. `xs_void_rift` → `h02_starless_hollow` (upgrade #3: darker centre, painterly violet bands, broken cyan rim, 6 readable beats, 11 → ≤ 10 draws).
4. `h02_star_lance`, 5. `h02_moonveil_ward`, 6. `h02_celestial_orrery`: new; start from the lance, aegis and orrery Blender sources, add the Look v2 masses.
7. `h02_basic`, plus the Chilled and Anchored markers and the status-marker system.

This order follows the owner's reference order (nova, palm, gate), so each fix is compared like with like (blades with blades, palm with palm) before it is re-skinned.

- **Kit v2 assets to build first at this step** (kit v1 is already on disk): `vfx_crescent_slash`, `vfx_crystal_shard`, `vfx_crystal_lance`, `vfx_hex_dome`, `vfx_orbit_ring`, `vfx_hex_sigil`, `vfx_motes`, `vfx_ramps`, `vfx_sigil_atlas`.
- **Reactions that become playable:** none yet (no partner released).
- **froggy draft:** `planning/assets/froggy-drafts/skills/1-SKILLS-02-witch.md`. **Animation:** §7.02. **Weapon:** Blender.

### Step 2: hero 01 Orc Swordsman

Skills in order: `h01_bladeward_nova` → `h01_lodestar_arc` → `h01_ironfall_cleave` → `h01_compass_rush` → `h01_eightfold_ward` → `h01_stormfall_cleave` → `h01_basic`. Statuses: Charged, Cracked (markers ship with the hero).

- **Kit v2 assets to build first at this step** (kit v1 is already on disk): `vfx_shield_sigil`, `vfx_rune_compass`, `vfx_ground_split`, `vfx_fb_smoke`, `vfx_fb_cloud`.
- **Reactions that become playable:** C1 Lodestone Snap.
- **froggy draft:** `planning/assets/froggy-drafts/skills/2-SKILLS-01-swordsman.md`. **Animation:** §7.01. **Weapon:** Tripo P2.0 single image.

### Step 3: hero 05 Rogue Thief

Skills in order: `h05_adders_kiss` → `h05_diamond_scatter` → `h05_fangfall` → `h05_duskstep` → `h05_nightbloom_smoke` → `h05_violet_masquerade` → `h05_basic`. Statuses: Venom, Shadowed (markers ship with the hero).

- **Kit v2 assets to build first at this step** (kit v1 is already on disk): `vfx_diamond_knife`, `vfx_flask`, `vfx_rune_diamond`, `vfx_liquid_pool`, `vfx_fb_splash`.
- **Reactions that become playable:** C2 Needlefrost.
- **froggy draft:** `planning/assets/froggy-drafts/skills/3-SKILLS-05-thief.md`. **Animation:** §7.05. **Weapon:** Tripo P2.0 single image.

### Step 4: hero 06 Tinker Merchant

Skills in order: `h06_forgeheart_slam` → `h06_grease_flask` → `h06_cog_sentry` → `h06_boiler_leap` → `h06_mending_anvil` → `h06_gearstorm_hammerfall` → `h06_basic`. Statuses: Oiled, Scorched (markers ship with the hero).

- **Kit v2 assets to build first at this step** (kit v1 is already on disk): `vfx_forge_hammer`, `vfx_gear_ring`, `vfx_fb_flame`, `prop_cog_sentry`, `prop_anvil_pylon`.
- **Reactions that become playable:** C3 Steamburst.
- **froggy draft:** `planning/assets/froggy-drafts/skills/4-SKILLS-06-tinker.md`. **Animation:** §7.06. **Weapon:** Tripo P2.0 single image (the 3/4 view is accepted).

### Step 5: hero 04 Bull-kin Acolyte

Skills in order: `h04_springwell_rain` → `h04_sunpalm_wave` → `h04_dawn_mend` → `h04_pilgrims_horn` → `h04_sunwheel_sanctum` → `h04_noonspring_covenant` → `h04_basic`. Statuses: Soaked, Sunlit (markers ship with the hero).

- **Kit v2 assets to build first at this step** (kit v1 is already on disk): `vfx_rune_sunwheel`, `vfx_fb_ripple`.
- **Reactions that become playable:** C4 Rainlash, C5 Rahu's Bite, C6 Slipslick.
- **froggy draft:** `planning/assets/froggy-drafts/skills/5-SKILLS-04-acolyte.md`. **Animation:** §7.04. **Weapon:** Blender.

### Step 6: hero 03 Wolf-kin Archer

Skills in order: `h03_amberwatch_arrow` → `h03_featherfan_volley` → `h03_crescent_howl` → `h03_brushtail_vault` → `h03_briar_snare` → `h03_featherstorm` → `h03_basic`. Statuses: Marked, Gusted (markers ship with the hero).

- **Kit v2 assets to build first at this step** (kit v1 is already on disk): `vfx_arrow`, `vfx_feather_blade`, `vfx_thorn_ring`, `vfx_rune_leaf`.
- **Reactions that become playable:** C7 Faultline, C8 Plaguewind.
- **froggy draft:** `planning/assets/froggy-drafts/skills/6-SKILLS-03-archer.md`. **Animation:** §7.03. **Weapon:** Blender.

Dependencies: the skill and combo data model and server validation (A31) and the 6-slot skill bar (C8) are needed before skills are playable; the VFX lane can build presets in the lab before that. Reaction presets are built in the step that unlocks them.

## 9. Hand-offs: froggy drafts and the data stub

**froggy** (`planning/assets/froggy-drafts/skills/`, send in this order, witch first):
1. `1-SKILLS-02-witch.md`: hero 02, 7 sheets (6 skills × 3 variants + the basic × 1 = 19 images).
2. `2-SKILLS-01-swordsman.md`: hero 01, 7 sheets (6 skills × 3 variants + the basic × 1 = 19 images).
3. `3-SKILLS-05-thief.md`: hero 05, 7 sheets (6 skills × 3 variants + the basic × 1 = 19 images).
4. `4-SKILLS-06-tinker.md`: hero 06, 7 sheets (6 skills × 3 variants + the basic × 1 = 19 images).
5. `5-SKILLS-04-acolyte.md`: hero 04, 7 sheets (6 skills × 3 variants + the basic × 1 = 19 images).
6. `6-SKILLS-03-archer.md`: hero 03, 7 sheets (6 skills × 3 variants + the basic × 1 = 19 images).

Each sheet is a 16:9 effect key-frame reference: 8 frames in a 4 × 2 grid (anticipation → peak → dissipation) in the Look v2 style, on a neutral grey stage, with the hero as a flat grey silhouette for scale, the exact telegraph shape, and frame times taken from this design. Outputs are CONCEPT and become the Stage A references for the gauntlet loop.

**Data stub** `planning/assets/hero-skills.json` (schema `xexoria.hero-skills/1`): resource, telegraph kinds, tiers, budget classes, the 12 statuses, derived states, the 8 reactions with rules (text and numeric), the 6 heroes, the 42 skills (id, hero, slot, type, names, targeting, telegraph, timing with release frame and clip events, cooldown, cost, power, heavy flag, statuses, combos, palette, VFX preset with layers, SFX, animation source, the 8 key-frame beats), the kit with reuse lists, the weapons, and the production order. It is a design stub: Codex root decides the server shape (A31), and the VFX lane decides the pool format (B13).

## 10. Owner decisions

| # | Decision | Default in this draft |
|---|---|---|
| D1 | Skill, status and combo names (Thai and English) | placeholders as written |
| D2 | SP pool, costs, cooldowns and power | proposed values; tune in playtests |
| D3 | Combos in PvP | off until a PvP balance pass |
| D4 | Coverage of the 6 single-target or deploy skills (10-14 %) and basics (3-4 %) below the 15 % heroic floor | keep them smaller for party readability; raise if you prefer spectacle |
| D5 | The witch has no mobility skill (dodge only; Rimeshard Nova is her escape) | keep; the prior-art Ward stays her slot 5 |
| D6 | Hero 01 taunts on Bladeward Nova (tank identity) | yes |
| D7 | Dawn Mend retimed from the rig plan's 900 / 600 to 700 / 400 ms | yes, for responsive heals |
| D8 | Reaction ultimate refund (4 s, once per 6 s) | yes, to reward cooperation |

## 11. Self-review against the brief

| Requirement | Where | Status |
|---|---|---|
| Thai summary for the owner at the top, 6-10 lines | 8 lines | done |
| Per hero: role, element, 2-3 hue palette with hex, shape language, weapon and trail sockets | §4.0 and each hero's identity table | done |
| All 36 skills plus each basic: id, Thai and English names, type | 42 entries, §4 | done |
| Targeting and telegraph shape (amber normal, double vermilion toothed heavy, never colour alone) | every block; §1.2 | done |
| Range and radius in metres; timing in ms with the release frame | every block; §7 | done |
| Cooldown and cost, proposed and tunable | every block; §1.6 | done |
| Status applied and combo enabled; 6-8 cross-hero combos of two statuses | 8 combos, §2; validator: no self-combo, every status used | done |
| VFX Look v2 layers (anticipation, core, secondaries, ground, after-effect), palette, peak coverage, tier note | every block; validator: all 5 roles present | done |
| SFX cue name | every block | done |
| Shared kit: mesh cores, flipbooks, decals, reuse map, low draws, B13 pool | §5 | done |
| Weapons table with routes, budgets and the trail and socket spec | §6 | done |
| Animation clip list per hero with release frames and UAL CC0 sources | §7 | done |
| Production order: witch (3 samples + 3 new), then 01, then 05 → 06 → 04 → 03 | §8 | done |
| froggy drafts, one per hero, witch first, header line, 16:9 8-frame strips | `planning/assets/froggy-drafts/skills/` | done |
| Data stub for Codex A31 and the VFX lane | `planning/assets/hero-skills.json` | done |
| Readability: telegraphs in low-effects mode; ally and enemy silhouettes visible at peak | §1.2, §1.4, per-skill readability notes; telegraph layers never drop | done |
| Originality: no names, icons or designs from WoW, Genshin, Ragnarok, Lumivara or others | §0; names checked and changed where they collided | done |

**Known limits:** coverage, colourfulness and budgets are design targets until the VFX lane measures them in engine; UAL clip names need a re-check against the current download; prices on Tripo must be read on the button before each paid click (stop rules); the combo numbers need playtests.
