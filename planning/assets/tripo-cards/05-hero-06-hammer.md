# Tripo job card: Hero 06 hammer (weapon) (2026-10-02)

**Status: NOT READY.** QA PASS on the single image (`planning/evidence/turnaround-qa-20261002/hero-06/weapon/`). Missing: `--prep` with the design review. Run after hero 06 passes its geometry review.

Asset `hero06_hammer` · class weapon · region global (hero 06) · runtime budget 2.5k / 1.2k / 400, 1024 · rules: `docs/reviews/2026-10-02-tripo-credit-guard.md` · credit pot: hero ceiling (2,500)

> **วิธีทำ (เจ้าของทำเองใน Tripo Studio):**
> 0. **ยังไม่ต้องทำ** จนกว่า Claude แจ้งว่าภาพผ่านทั้งเครื่องตรวจและการรีวิวดีไซน์ (ใน receipt ต้องเป็น `eligible_for_tripo: true`)
> 1. Tripo Studio → Image to 3D → **Single image (ใส่รูปเดียว)** → รุ่น **P2.0**
> 2. ใช้รูปจากโฟลเดอร์ `planning\evidence\turnaround-qa-20261002\hero-06\weapon\tripo-prep\ (to be created by --prep)`
> 3. ขั้นแรกสร้าง **เฉพาะรูปทรง** (Triangle เปิด, 2,100 faces, ยังไม่ทำ texture) = 100 เครดิต แล้วให้ Claude ดูก่อน
> 4. ถ้ารูปทรงผ่าน ค่อยกด **Smart UV** (20) แล้ว **Texture 2K** (10) โดย **Remove Lighting เปิด** และ **PBR** (+5); ไม่ทำ auto-rig
> 5. ดาวน์โหลด GLB ไปไว้ที่ `Downloads\Xexoria-Game\sources\tripo\hero06_hammer\` แล้วจด job ID กับเครดิตที่ใช้
> รวมประมาณ **135 เครดิต** (ถ้าต้องสร้างรูปทรงใหม่ 1 ครั้งตามกฎ: 235)

## Inputs

| Item | Value |
|---|---|
| Mode | P2.0, single image |
| Upload folder | `planning\evidence\turnaround-qa-20261002\hero-06\weapon\tripo-prep\ (to be created by --prep)` |
| Slots | front.png → the single image slot |
| Gate | QA PASS (`tools/art/turnaround_qa.py`) + Claude design review PASS, so the prep receipt says `eligible_for_tripo: true`. No `--force` set is ever uploaded. |

## Stages (pay in stages; stop on failure)

| # | Stage | Settings | Credits | Check before paying for the next stage |
|---|---|---|---|---|
| 1 | Geometry | P2.0, single image, **triangle on, face limit 2,100** (about 2,500 triangles), no texture. If the 4-variant pass bills once, use the target, -15 % and +15 % and keep the best shape | 100 | One object; head and haft joint intact; no holes; near 2.5k triangles. If it fails, one retry; after 2 failed jobs stop and report (credit guard rule 5) |
| 2 | Smart UV | Studio Smart UV (removes any texture, so it runs before texturing); free trials are used up on this account, so assume 20 | 20 | Utilisation at least 70 % (use a free retry if lower); sane islands; no stretched face or hands. |
| 3 | Texture | **2K, Remove Lighting ON (the source is a lit ChatGPT render)**, alignment `original_image` | 10 | Painted look kept; no baked shadow on one side; colours match the palette strip. |
| 4 | PBR | On | 5 | Metal only where the concept shows metal; cloth, stone and skin non-metallic |
| 5 | Rig | None | 0 | n/a |

**Credits:** planned **135**; worst case **235** with the one allowed geometry retry; pot: hero ceiling (2,500). Failed or cancelled Tripo tasks are refunded and do not count as failed jobs.

## After download (Claude)

1. Record the job ID, settings and credits in the weapon's `tripo-prep/receipt.json`.
2. Blender cleanup: metres to the hero scale, pivot at the grip, blade edge and fuller intact, no pinched grip cylinder (rebuild the grip as a Blender cylinder if pinched).
3. Add the trail empties at the blade tip and base (heroes decisions section 6), LOD0 <= 2.5k / LOD1 1.2k / LOD2 400, one 512-1024 map set.
4. Export as its own GLB with `export_helper.py`; attach to the hand socket in the hero's review scene; captures at 2 m and 13 m.

## Notes

- If the haft comes out pinched, keep the Tripo head and rebuild the haft as a Blender cylinder (credit guard section 8).
