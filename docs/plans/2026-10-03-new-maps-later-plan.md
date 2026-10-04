# New maps: plan for later (parked 2026-10-03 11:20)

**Owner (11:15–11:20):**
> "focus main map make like bluep[rint]"
> "just write plan for later about other thing new map"

Everything below is **parked** until the Sunmeadow main map matches `docs/levels/2026-10-03-sunmeadow-blueprint-v1.md`. Nothing here is being built now.

## สรุปสำหรับเจ้าของ

- **ตอนนี้ทำแค่แมพหลัก (Sunmeadow) ให้เหมือน blueprint** ส่วนแมพใหม่ทั้งหมดพักไว้ก่อน ไฟล์จาก froggy เก็บไว้ครบแล้ว
- **แผนโลกของ froggy (36 โซน):**
  - 6 ภูมิภาค, Lv 1–50, มีเมืองปลอดภัยภูมิภาคละ 1 เมือง
  - เชื่อมกับของเดิมครบ: Sunmeadow, Rimecrest, Southreach, Ashveil Caldera และ dungeon ทั้ง 4
- **แมพใหม่แมพแรกคือ Tidemill Cove** (Lv 10–14) ต่อถนนจาก Southreach froggy ทำ concept 3 แบบ (เลือก B), layout 128 m และฉากทดลองใน Blender ที่ใช้ asset CC0 ไว้แล้ว
- **เมื่อแมพหลักเสร็จ:**
  1. แปลง layout ของ froggy ให้เข้าระบบเรา แล้วตรวจด้วยเครื่องมือของเรา
  2. ทำ blueprint ของตกแต่งตั้งแต่วันแรก
  3. ส่งงานให้ Codex สร้าง

## 1. Inputs already on disk

All under `Downloads\Xexoria-Game\sources\froggy\` (SHA256SUMS in each folder).

**`world-20261003\worldplan\`: world plan v-sync**
- `xexoria_world_plan.md`, `xexoria_36_zone_catalog.json`, `xexoria_36_zone_index.csv`;
- `xexoria_worldplan_36_zone_table.md`, `xexoria_reference_audit.md`, `xexoria_design_validation.json`;
- `WORLDPLAN_SYNC_README.md`, which records the migration decisions.

**`world-20261003\tidemill\`: Tidemill Cove**
- concepts `SM04_{A,B,C}_Tidemill_Cove.png` (B chosen);
- `Tidemill_Cove_B_128m_Layout_Pack.zip`: `tidemill_cove_layout.json`, plan PNG/SVG, `validation_2d.json`, `build_plan.py`;
- `SM04_Tidemill_Blender_Pilot.zip`: `.blend`, LOD0 GLB 9.8 MB, collision GLB, 13 m / 1.8 m previews;
- `SM04_Tidemill_Reusable_LOD_Kit.zip` and `SM04_Tidemill_CC0_Rebuild_Inputs.zip`.
- **Licences:** Kenney Nature Kit 2.1 (CC0) and Quaternius Stylized Nature MegaKit Standard FREE (CC0). Verified by Claude from the licence files and receipts.

**`world-20261003\` (other zone and asset files):**
- `ML01_Mirelight_Quay_3_concepts.zip`, `EW06_Furnace_of_Echoes_3_concepts.zip`, `Xexoria_NPC_and_Prop_Concepts.zip`;
- `asset_catalog.csv`, `asset_selection.md`, `licensesources.json`: 28 free assets, top 12 ranked. **Re-check every licence before use.**

**Region key art:** `rimecrest-keyart-F10-20261003\`, `keyart-windstone-F8-20261003\`, `dungeons-20261001\` (packs A–D), `snow-reviews-20261003\`.

**Started, then paused at 11:15:** Claude's Tidemill layout agent. Its journal is `planning/evidence/tidemill-v1/PROGRESS.md`, if it got that far. Brief: `Downloads\Xexoria-Game\agent-output\20261002-claude-handoff\briefs\resume-2230\12-tidemill-layout-v1.md`. It had been told to build on froggy's layout pack.

## 2. World structure, reconciled with what exists

| Region (froggy) | Zones (examples) | Level | Hub | Existing pieces kept |
|---|---|---|---|---|
| Sunmeadow Reach | sunmeadow, whisperwood, **tidemill_cove**, southreach_field, sunken_temple_aurel (D) | 1–24 | the city (ID pending) | Sunmeadow (no redesign), Southreach, Sunken Temple |
| Rimecrest | rimecrest_snow, lanternmelt_refuge, blueglass_vale, whitewake_coast, snowbound_archive, frost_jarl (D) | 6–26 | Lanternmelt Refuge | Rimecrest v1 layout (Mirun, Solar Scorpion), Frost Jarl |
| Highsail | highsail_exchange, sailgrass_steps, chime_quarry, whisperwood_hollow (D), cloudshoal_isles, gloamcrystal (D) | 10–28 | Highsail Exchange | Whisperwood Hollow, Cloudshoal Isles, Gloamcrystal |
| Mirelight | mirelight_quay, reedglass_delta, rootvault_canopy, candlefen, sunken_loom, bloomheart_basin | 18–30 | Mirelight Quay | — |
| Emberwake | emberwake_caravanserai, copperwind_mesa, cinderstep_foundry, saffron_glass_dunes, obsidian_orchard, ashveil_caldera | 28–40 | Emberwake Caravanserai | Ashveil Caldera (boss Emberwright); Furnace of Echoes becomes a subarea |
| Asterfall | asterfall_anchorage, argent_tides, archive_of_unmade_roads, starroot_terraces, hollow_horizon, crown_of_returning_dawn | 38–50 | Asterfall Anchorage | — |

**Rules that carry over:**
- The city's portal dais is the warp hub and lists discovered warps only.
- New IDs stay *proposed* until the owner confirms them.
- Every zone is about 128 × 128 m (2 × 2 cells of 64 m), with flat Y = 0 physical support until the server gets terrain height.

## 3. Order when the main map is done

1. **Tidemill Cove v1:**
   - convert froggy's 128 m layout into `planning/levels/tidemill-v1-layout.json` and `-monsters.json` (Rimecrest v1 schema);
   - run our region checks, keeping Sunmeadow and Rimecrest byte-identical;
   - write `tidemill-blueprint-v1.json` from day one (0 conflicts);
   - write the level-design doc with a Thai summary;
   - route `codex-requests.md`: the server zone, the road from Southreach, spawns, colliders, and the dungeon door.
2. **Southreach Field v1:** the existing brief is in asset board §3.2. It is the gate to Tidemill and Highsail.
3. **Rimecrest v1 runtime:** the layout is already done. Codex A35/A36 cover the warps and the Solar Scorpion arena, then Stage C for the scorpion.
4. **Then one region at a time, by player level:**
   - Whisperwood + Whisperwood Hollow;
   - the Lanternmelt Refuge hub;
   - Highsail Exchange.
5. **Asset reuse:** use froggy's reusable LOD kit and the CC0 picks from `asset_selection.md`. Licences are re-checked per asset, Quaternius QAL packs need the owner's approval, and trees come only from the CC0 kit route.

## 4. Open owner decisions for later

1. Confirm the city ID and the warp registry; froggy has it as `city_id_pending`.
2. Confirm the proposed zone IDs and names, in particular `ashveil_caldera` and the hub names.
3. Tripo budget for new-zone monsters and bosses: there is no approved pot beyond heroes and weapons.
4. When to unpark: the trigger is the owner accepting Sunmeadow against its blueprint.
