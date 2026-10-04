# Tripo job card: Windstone ring stone master (Sunmeadow hero prop, reused about 11 times) (2026-10-02)

**Status: NOT READY.** Stage A draft F09 is ready to send. Order: F09 Part 1 (3 variants) → Claude picks → F09 Part 2 (F6 4-view, no cloth) → QA `--kind prop` → design review.

Asset `windstone_ring_stone` · class hero prop (landmark stone) · region sunmeadow (+ warp network) · runtime budget 3-6k / 50 % / 25 %, 1024 · rules: `docs/reviews/2026-10-02-tripo-credit-guard.md` · credit pot: proposed stage 2, Sunmeadow slice (needs the owner's OK)

> **วิธีทำ (เจ้าของทำเองใน Tripo Studio):**
> 0. **ยังไม่ต้องทำ** จนกว่า Claude แจ้งว่าภาพผ่านทั้งเครื่องตรวจและการรีวิวดีไซน์ (ใน receipt ต้องเป็น `eligible_for_tripo: true`)
> 1. Tripo Studio → Image to 3D → **Multi-view (ใส่ 4 ช่อง Front/Back/Left/Right)** → รุ่น **P2.0**
> 2. ใช้รูปจากโฟลเดอร์ `planning\evidence\turnaround-qa-<date>\windstone-ring-stone\tripo-prep\ (created when the set passes)`
> 3. ขั้นแรกสร้าง **เฉพาะรูปทรง** (Triangle เปิด, 4,200 faces, ยังไม่ทำ texture) = 100 เครดิต แล้วให้ Claude ดูก่อน
> 4. ถ้ารูปทรงผ่าน ค่อยกด **Smart UV** (20) แล้ว **Texture 4K** (20) โดย **Remove Lighting ปิด** และ **PBR** (+5); ไม่ทำ auto-rig
> 5. ดาวน์โหลด GLB ไปไว้ที่ `Downloads\Xexoria-Game\sources\tripo\windstone_ring_stone\` แล้วจด job ID กับเครดิตที่ใช้
> รวมประมาณ **145 เครดิต** (ถ้าต้องสร้างรูปทรงใหม่ 1 ครั้งตามกฎ: 245)

## Inputs

| Item | Value |
|---|---|
| Mode | P2.0, multi-view |
| Upload folder | `planning\evidence\turnaround-qa-<date>\windstone-ring-stone\tripo-prep\ (created when the set passes)` |
| Slots | front/back/left/right; the glyph is on the front face only (declared) |
| Gate | QA PASS (`tools/art/turnaround_qa.py`) + Claude design review PASS, so the prep receipt says `eligible_for_tripo: true`. No `--force` set is ever uploaded. |

## Stages (pay in stages; stop on failure)

| # | Stage | Settings | Credits | Check before paying for the next stage |
|---|---|---|---|---|
| 1 | Geometry | P2.0, multi-view, **triangle on, face limit 4,200** (about 5,000 triangles after export (0.84 x the 5k budget), parts off so Smart UV works), no texture. If the 4-variant pass bills once, use the target, -15 % and +15 % and keep the best shape | 100 | One solid monolith; no holes; base flat; glyph grooves still readable (if lost, Claude re-cuts them with a baked height map); triangle count near 5k. If it fails, one retry; after 2 failed jobs stop and report (credit guard rule 5) |
| 2 | Smart UV | Studio Smart UV (removes any texture, so it runs before texturing); free trials are used up on this account, so assume 20 | 20 | Utilisation at least 70 % (use a free retry if lower); sane islands; no stretched face or hands. |
| 3 | Texture | **4K, Remove Lighting OFF (the F6 set is flat-lit)**, alignment `original_image` | 20 | Painted sandstone kept; groove glow is NOT baked bright (emission comes from a mask in Blender). |
| 4 | PBR | On | 5 | Metal only where the concept shows metal; cloth, stone and skin non-metallic |
| 5 | Rig | None (static prop) | 0 | n/a |

**Credits:** planned **145**; worst case **245** with the one allowed geometry retry; pot: proposed stage 2, Sunmeadow slice (needs the owner's OK). Failed or cancelled Tripo tasks are refunded and do not count as failed jobs.

## After download (Claude)

1. Record the job ID, settings and credits in the prop's `tripo-prep/receipt.json` (`tripo` block); keep the download untouched as the source.
2. Blender cleanup on a copy: metres, pivot at the base centre, transforms applied, merge by distance, no interior faces, base sunk 5-10 cm so it never floats on uneven ground.
3. LOD0 at the budget, LOD1 50 %, LOD2 25 % (same UVs); a simple box or capsule collider that matches the visible base.
4. Bake map set A (normal + AO) from the Tripo source onto LOD0 and map set B onto LOD1; re-cut any lost groove with a Blender height map baked into the normal.
5. Hand-painted albedo pass to the look target; ORM pack (R AO, G roughness, B metallic).
6. Export with `assets/blender/tools/export_helper.py` (static prop), glTF validator 0 errors; BLENDER REVIEW with the 1.8 m witness and the 13 m camera; Stage C loop in the scene that uses it.

## Notes

- **Why Tripo here (and only here among the Sunmeadow props):** this is a large sculpted organic form (wind erosion, scooped hollows, carved glyph) that headless Blender Python does poorly; procedural noise rocks read as the 'egg rocks' the prop audit removed. One master is reused for 6 ring stones, 2 gate-stone restyles, 3 quest windmarks and the arrival rings of the warp network, so 145 credits buy about 11 placements and the boss arena's landmark.
- Variation without new jobs: rotate, scale 0.7-1.15, mirror, and vary the streamer colour and the moss mask per instance.
- Budget: 3-6k / 50 % / 25 %, 1024 maps (2048 only if the arena close-up shows blur); six stones in one 64 m cell stay far under the 120k cell budget.
