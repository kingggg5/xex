# Tripo job card: Rimecrest lv1 bone raptor (2026-10-02)

**Status: NOT READY.** Design KEEP (owner). The current set FAILs QA (views at different scales, front/back IoU 0.405, left/right IoU 0.649). Froggy draft F14.

Asset `snow_bone_raptor` · class regular monster · region rimecrest_snow (lv1 band) · runtime budget 6.5-8k / 2.5k / 1k, 1024 · rules: `docs/reviews/2026-10-02-tripo-credit-guard.md` · credit pot: proposed stage 3, Rimecrest

> **วิธีทำ (เจ้าของทำเองใน Tripo Studio):**
> 0. **ยังไม่ต้องทำ** จนกว่า Claude แจ้งว่าภาพผ่านทั้งเครื่องตรวจและการรีวิวดีไซน์ (ใน receipt ต้องเป็น `eligible_for_tripo: true`)
> 1. Tripo Studio → Image to 3D → **Multi-view (ใส่ 4 ช่อง Front/Back/Left/Right)** → รุ่น **P2.0**
> 2. ใช้รูปจากโฟลเดอร์ `planning\evidence\turnaround-qa-<date>\snow-bone-raptor\tripo-prep\ (created when the F14 set passes)`
> 3. ขั้นแรกสร้าง **เฉพาะรูปทรง** (Quad เปิด, 3,700 faces, ยังไม่ทำ texture) = 100 เครดิต แล้วให้ Claude ดูก่อน
> 4. ถ้ารูปทรงผ่าน ค่อยกด **Smart UV** (20) แล้ว **Texture 2K** (10) โดย **Remove Lighting ปิด** และ **PBR** (+5); ไม่ทำ auto-rig
> 5. ดาวน์โหลด FBX กับ GLB ไปไว้ที่ `Downloads\Xexoria-Game\sources\tripo\snow_bone_raptor\` แล้วจด job ID กับเครดิตที่ใช้
> รวมประมาณ **135 เครดิต** (ถ้าต้องสร้างรูปทรงใหม่ 1 ครั้งตามกฎ: 235)

## Inputs

| Item | Value |
|---|---|
| Mode | P2.0, multi-view |
| Upload folder | `planning\evidence\turnaround-qa-<date>\snow-bone-raptor\tripo-prep\ (created when the F14 set passes)` |
| Slots | front/back/left/right |
| Gate | QA PASS (`tools/art/turnaround_qa.py`) + Claude design review PASS, so the prep receipt says `eligible_for_tripo: true`. No `--force` set is ever uploaded. |

## Stages (pay in stages; stop on failure)

| # | Stage | Settings | Credits | Check before paying for the next stage |
|---|---|---|---|---|
| 1 | Geometry | P2.0, multi-view, **quad on, face limit 3,700** (about 7,500 triangles), no texture. If the 4-variant pass bills once, use the target, -15 % and +15 % and keep the best shape | 100 | The ribcage a closed ice core (no gaps); tail separate from the legs; spine spikes kept as a readable top line. Proportions within +/-5 % of the turnaround; no fused legs, claws or jaw; a plausible back; no holes or floating shells; face count near the target. If it fails, one retry; after 2 failed jobs stop and report (credit guard rule 5) |
| 2 | Smart UV | Studio Smart UV (removes any texture, so it runs before texturing); free trials are used up on this account, so assume 20 | 20 | Utilisation at least 70 % (use a free retry if lower); sane islands; no stretched face or hands. |
| 3 | Texture | **2K, Remove Lighting OFF if the delivered set is flat-lit (F6 format); ON if the QA `lighting` check shows directional light above 8 %**, alignment `original_image` | 10 | Painted look kept; no baked shadow on one side; colours match the palette strip. |
| 4 | PBR | On | 5 | Metal only where the concept shows metal; cloth, stone and skin non-metallic |
| 5 | Rig | **Skip.** Claude rigs in Blender (Rigify quadruped/biped hybrid with a 6-8 bone tail chain) | 0 | n/a |

**Credits:** planned **135**; worst case **235** with the one allowed geometry retry; pot: proposed stage 3, Rimecrest. Failed or cancelled Tripo tasks are refunded and do not count as failed jobs.

## After download (Claude)

1. Record the job ID, every setting and the credits per stage in the asset's `tripo-prep/receipt.json` (`tripo` block); keep the download untouched as the source (SHA-256).
2. Blender cleanup on a copy (credit guard section 7): metres and the concept height, pivot at the feet, front = +Z in glTF, merge by distance, remove loose and interior pieces, separate rigid parts that must stay rigid (tusks, claws, shell), three edge loops at each deforming joint.
3. Smart UV texel check (regular monster about 512 px/m at 1024; boss 256-400 px/m at 2048); flag islands outside +/-30 % of the median, use under 70 %, padding under 8 px.
4. LOD0 at the runtime budget, LOD1/LOD2 by decimation with the same UVs (`tools/lod-pipeline.mjs` or Decimate with UV seams delimited); count triangles after triangulated export.
5. Bakes (device-tier plan section 6.2): map set A (normal + AO from the Tripo source onto LOD0) and map set B (onto LOD1, 1K and 512) for the Low/Medium tiers; form AO also into the albedo.
6. Hand-painted albedo pass (monsters doc section 4): top-light gradient, painted AO, crisp edge highlights, hue variation, values 0.04-0.92.
7. Rig and clips per the monsters doc sections 3.5 and 7 (Rigify family below), clip names and timings from the server row, 4 influences, deform bones only.
8. Export with `assets/blender/tools/export_helper.py` (`character_skinned`), glTF validator 0 errors, NullEngine AnimationGroup check (monsters doc section 7.7).
9. BLENDER REVIEW renders with the 1.8 m witness and the 13 m game camera, then the Stage C gauntlet loop in Babylon (reference-gauntlet-loop doc).

## Notes

- Mesh2Motion CC0 creature clips can serve as a first pass for the gait (monsters doc section 3.2).
