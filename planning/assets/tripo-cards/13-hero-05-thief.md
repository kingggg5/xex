# Tripo job card: Hero 05 Thief (rogue) (2026-10-02)

**Status: NOT READY.** Round-2 regeneration (cape side views that match front and back) is with froggy (F8 / F-HREGEN). Run after QA PASS + design review and after hero 01 passes its review (hero ceiling).

Asset `hero05_thief` · class hero · region global · runtime budget 12k / 6k / 2.5k, 2048 · rules: `docs/reviews/2026-10-02-tripo-credit-guard.md` · credit pot: hero ceiling (2,500)

> **วิธีทำ (เจ้าของทำเองใน Tripo Studio):**
> 0. **ยังไม่ต้องทำ** จนกว่า Claude แจ้งว่าภาพผ่านทั้งเครื่องตรวจและการรีวิวดีไซน์ (ใน receipt ต้องเป็น `eligible_for_tripo: true`)
> 1. Tripo Studio → Image to 3D → **Multi-view (ใส่ 4 ช่อง Front/Back/Left/Right)** → รุ่น **P2.0**
> 2. ใช้รูปจากโฟลเดอร์ `planning\evidence\turnaround-qa-<date>\hero-05\tripo-prep\ (created when round 2 passes)`
> 3. ขั้นแรกสร้าง **เฉพาะรูปทรง** (Quad เปิด, 5,900 faces, ยังไม่ทำ texture) = 100 เครดิต แล้วให้ Claude ดูก่อน
> 4. ถ้ารูปทรงผ่าน ค่อยกด **Smart UV** (20) แล้ว **Texture 4K** (20) โดย **Remove Lighting เปิด** และ **PBR** (+5); ไม่ทำ auto-rig
> 5. ดาวน์โหลด FBX กับ GLB ไปไว้ที่ `Downloads\Xexoria-Game\sources\tripo\hero05_thief\` แล้วจด job ID กับเครดิตที่ใช้
> รวมประมาณ **145 เครดิต** (ถ้าต้องสร้างรูปทรงใหม่ 1 ครั้งตามกฎ: 245)

## Inputs

| Item | Value |
|---|---|
| Mode | P2.0, multi-view |
| Upload folder | `planning\evidence\turnaround-qa-<date>\hero-05\tripo-prep\ (created when round 2 passes)` |
| Slots | front/back/left/right (in round 1 image #2 faced screen-right: check the order on delivery) |
| Gate | QA PASS (`tools/art/turnaround_qa.py`) + Claude design review PASS, so the prep receipt says `eligible_for_tripo: true`. No `--force` set is ever uploaded. |

## Stages (pay in stages; stop on failure)

| # | Stage | Settings | Credits | Check before paying for the next stage |
|---|---|---|---|---|
| 1 | Geometry | P2.0, multi-view, **quad on, face limit 5,900** (about 12,000 triangles), no texture. If the 4-variant pass bills once, use the target, -15 % and +15 % and keep the best shape | 100 | No fused fingers or straps; the cape not merged into the legs; a plausible back; weapon hand open. If it fails, one retry; after 2 failed jobs stop and report (credit guard rule 5) |
| 2 | Smart UV | Studio Smart UV (removes any texture, so it runs before texturing); free trials are used up on this account, so assume 20 | 20 | Utilisation at least 70 % (use a free retry if lower); sane islands; no stretched face or hands. |
| 3 | Texture | **4K, Remove Lighting ON for lit ChatGPT renders, OFF if froggy delivers a flat-lit F6 set**, alignment `original_image` | 20 | Painted look kept; the near-black palette lifted per the heroes decisions (value and rim contrast). |
| 4 | PBR | On | 5 | Metal only where the concept shows metal; cloth, stone and skin non-metallic |
| 5 | Rig | **Skip.** Claude rigs to the shared XS1 skeleton | 0 | n/a |

**Credits:** planned **145**; worst case **245** with the one allowed geometry retry; pot: hero ceiling (2,500). Failed or cancelled Tripo tasks are refunded and do not count as failed jobs.

## After download (Claude)

1. Record the job ID, settings and credits in `hero-0X/tripo-prep/receipt.json` (`tripo` block).
2. Blender: cleanup, LOD0 12k / LOD1 6k / LOD2 2.5k, normal + AO bake from the Tripo high-poly onto LOD1/LOD2, the readability pass of the heroes decisions (head +10-15 %, hands +20 %), XS1 rig and UAL CC0 clips, export with `export_helper.py` (`character_skinned`).
3. In-game proof next to the 1.8 m witness; native acceptance gives the owner a keep/drop (same as `docs/plans/2026-10-02-tripo-job-card.md`).

## Notes

- Same settings as `docs/plans/2026-10-02-tripo-job-card.md`.
