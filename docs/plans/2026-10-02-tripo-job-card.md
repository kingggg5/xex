# Tripo job card: heroes 01, 04, 06 (2026-10-02)

These are QA PASS sets with Claude's design-review PASS; each receipt says `eligible_for_tripo: true`. Rules: `docs/reviews/2026-10-02-tripo-credit-guard.md`. The budget is stage 1 (600 credits). These three heroes cost about 435.

> **วิธีทำ (เจ้าของทำเองได้ใน 3 นาทีต่อตัว หรือเปิด Tripo Studio ค้างไว้ใน Edge แล้วไม่ใช้เครื่องสักพัก ให้ Claude ทำให้):**
> 1. Tripo Studio → Image to 3D → **Multi-view** → รุ่น **P2.0**
> 2. ใส่รูป 4 ช่องจากโฟลเดอร์ด้านล่าง: Front, Back, Left, Right
> 3. ขั้นแรกสร้าง **เฉพาะรูปทรง** (Quad เปิด, **11,800 faces**, ยังไม่ทำ texture) = 100 เครดิต แล้วดูผลก่อน (โมเดลละเอียดกว่าที่ใช้ในเกม 2 เท่า เพื่อ bake ลง LOD)
> 4. ถ้ารูปทรงดี ค่อยกด **Smart UV** (20) แล้ว **Texture 4K** (20) โดย **Remove Lighting ปิด** และไม่ต้องทำ auto-rig
> 5. ดาวน์โหลด FBX กับ GLB ไปไว้ที่ `Downloads\Xexoria-Game\sources\tripo\hero-0X\` แล้วจด job ID กับเครดิตที่ใช้

## Inputs

| Hero | Class | Folder (upload these 4 files) |
|---|---|---|
| 01 (orc) | Swordsman | `%USERPROFILE%\Documents\game\planning\evidence\turnaround-qa-20261002\hero-01\tripo-prep\` |
| 04 (bull-kin) | Acolyte | `...\hero-04\tripo-prep\` |
| 06 (tinker) | Merchant | `...\hero-06\tripo-prep\` |

Slots:
- `front.png` → Front, `back.png` → Back, `left.png` → Left, `right.png` → Right.
- Left means the character's own left side (credit guard §5.1). On the first job, check this against an asymmetric detail such as the belt pouches.

## Stages (pay in stages; stop on failure)

| # | Stage | Settings | Credits | Check before paying for the next stage |
|---|---|---|---|---|
| 1 | Geometry | P2.0, multi-view, **quad on, face limit 11,800** (about 24k triangles = 2× the 12k LOD0, so Blender bakes normal + AO onto LOD0/1/2; decision 2026-10-02 resolving the job-card vs device-tier §6.2 conflict; same 100 credits), no texture | 100 | No fused fingers or straps, a plausible back, no floating parts, the weapon hand open. If it fails, retry once; after 2 failed jobs, stop and report |
| 2 | Smart UV | Studio Smart UV (it removes any texture, so run it before texturing) | 20 (first 2 models free) | Islands are sane |
| 3 | Texture | **4K, Remove Lighting OFF** (hand-painted style), PBR optional (+5) | 20 | Painted look kept, no baked shadows on one side |
| 4 | Rig | **Skip.** Claude rigs to the shared XS1 skeleton | 0 | n/a |

## After download (Claude)
1. Record the job ID, settings and credits in `hero-0X/tripo-prep/receipt.json` → `tripo`.
2. **Blender:**
   - cleanup, LOD0 for Ultra and mobile-high, LOD1-2 by decimation;
   - normal + AO bake from the Tripo high-poly onto LOD1/LOD2;
   - the XS1 rig and UAL CC0 clips;
   - export with `assets/blender/tools/export_helper.py` (`character_skinned`).
3. Show it in game next to the 1.8 m witness. Native acceptance gives the owner a keep/drop.

Weapons (sword, hammer: QA PASS) come later as single-image prop jobs, about 135 credits each. Staffs and the bow are built in Blender, because their shafts are too thin for Tripo.

## Face-target rule (decision 2026-10-02)

Generate at **about 2× the runtime LOD0** and bake the detail down. Geometry costs 100 credits whatever the face count.

| Class | Runtime LOD0 (triangles) | Tripo target |
|---|---|---|
| Hero | 12k | quad 11,800 (≈ 24k triangles) |
| Monster | 4-8k | quad 5,900 |
| Boss | 15-25k | quad 19,600 (≤ 25k quads) |
| Weapon | 2.5k | triangles 4,200 |

The Solar Scorpion (51k triangles, owner-made) is the reference case: decimate it to ≤ 25k with a bake.
