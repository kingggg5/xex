# Stage C plan: bovine shaman as a map NPC (for Claude)

Date: 2026-10-02 · Drafted by: C-PRODUCER (planning only) · Owner decision (relayed 19:50): `boss\bovine-shaman` is an NPC for the map, not a boss.

> **สรุปภาษาไทย:** ตัววัว (bovine shaman) เป็น NPC ไม่ใช่บอส โมเดลทำเสร็จแล้ว (rig 32 ข้อต่อ, 8 ท่ารวม Idle และ Talk) แต่ยังหนักเกินงบ NPC มาก (54k triangles เทียบกับงบ 8k) และมีแค่ texture สี ไม่มี normal map งานที่ต้องทำ: ลดโพลีเป็น 8k/4k/1.5k, bake normal และ AO จากโมเดลละเอียด, texture 1024, เก็บท่า Idle/Talk (+ ท่าทักทาย), export แล้วตรวจในเกม ไม่ใช้เครดิต Tripo เพิ่ม ต้องตัดสินใจก่อนว่าจะวางไว้ที่ Rimecrest, ในเมือง (ตอนนี้ลงทะเบียนเป็น Ruun ผู้อาวุโสของเมือง) หรือทั้งสองที่

## 1. What exists

| Part | State |
|---|---|
| Tripo | P2.0 multi-view, job `d8cbe7d6-7373-4b69-bfa6-47676945b149`: quad 25,000 requested, 32,348 faces = 54,011 triangles; 100 credits; Smart UV free trial, 74.7 % utilisation; texture-only stage (base colour 8K source, no normal, no roughness) |
| Rig v1 | `assets/characters/bovine-shaman/rig-v1/`: Rigify fitted, 32 deform joints, rigid staff, robe and beard controls; clips Idle, Walk, Run, Talk, StaffCast, StaffStrike, HitReact, Death; LODs 54,011 / 27,005 / 11,882 with base colour 4096 / 2048 / 1024 JPEG; review R3 PASS_WITH_LIMITS (Blender renders only) |
| Placement today | Registered as **Ruun, City Elder** at city X20, Z156 (rig-v1 README), Idle/Talk, 3 m interaction |
| Retro QA of the reference views | REGEN (staff thin parts 2.1-2.4 %, left/right IoU 0.829, front/back IoU 0.870): record only, the model exists |

## 2. Decision first (owner or Claude)

Where does he live? (a) Rimecrest only, as the yak-herder elder at the arrival camp (fits the snow region's culture and gives the region its quest hub); (b) the city only, as Ruun; (c) both, as the same travelling character. One face for two different named NPCs would confuse players; (a) or (c) is recommended.

## 3. Tasks (Claude; 0 Tripo credits)

1. **Budget class: NPC** (art plan section 2): LOD0 8k / LOD1 4k / LOD2 1.5k, 1024 maps. If the 8k bake loses the beard, beads and face at the dialogue camera (2-4 m), ask the owner for a hero-class exception (12k, 2048).
2. **LODs** from the 54k source: UV-preserving decimation protecting the face, beard, horns, hands and the staff crook; same UVs and skeleton across LODs; triangles counted after export.
3. **Weights**: transfer from rig v1 to each new LOD; keep the audited rigid masks (staff, hooves, hands); at most 4 influences.
4. **Bakes**: map set A (normal + AO from the 54k source onto LOD0, 1024 and 2048 masters) and map set B (onto LOD1 at 1K/512); form AO into the albedo. This adds the normal map the package never had.
5. **Albedo and ORM**: downsample the 4096 base colour to 1024 (+512), check the painted top-light/AO read against the look target, add painted edge highlights on the brass; ORM: cloth roughness about 0.8, brass metallic via a mask.
6. **Clips (NPC set)**: Idle and Talk (exist), Walk (exists, for a short patrol), add a short Greet/Bow (about 1.5 s) and an idle variant (look around); keep the combat clips out of the NPC runtime file. Play by name with `animationStartMode: NONE`.
7. **Rimecrest dressing (if placed there)**: a snow-dust mask on the shoulders and hood top as a material variant; no new mesh.
8. **Originality guard** in any texture change: keep the yak mane, Himalayan-style textiles and prayer beads; no totems, feathers or war paint (avoids the tauren archetype).
9. **Export** with `assets/blender/tools/export_helper.py` (`character_skinned`); glTF validator 0 errors; NullEngine AnimationGroup check.
10. **Review**: BLENDER REVIEW with the 1.8 m witness (he stands 2.4 m), dialogue-distance close-up and the 13 m game camera; then the Stage C loop in the chosen map against the owner's four reference views (silhouette IoU ≥ 0.85, rubric ≥ 85).
11. **Receipt**: hashes, triangles per LOD, maps, clips, the Tripo job ID and the 100 credits spent earlier.
