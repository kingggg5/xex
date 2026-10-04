# Sunken Temple of Aurel — level design (D2 blockout)

Date: 2026-10-01 · Level designer: Claude · Status: blockout design; not playable until the D1 transition system exists

> **สรุปภาษาไทย:** ด่านต้นแบบแบบวิหารจมอยู่ในหุบผา เปิดรับแสงจากด้านบน เดินลงลึกไปเรื่อย ๆ ผ่านห้องโถงทางเข้า ระเบียงเสาน้ำท่วม ห้องประตูสุริยะ (ปริศนาแสง) โดมถล่ม และห้องบอส แล้วมีห้องรางวัลกับประตูกลับ ใช้สเกลเมตรจริง ทางเดินกว้างอย่างน้อย 4 m บันไดสูงขั้นละ 0.16 m

## Intent

A ruined sun temple sunk into a ravine, partly open to the sky so the third-person camera always has space and shafts of daylight guide the player downward. Warm sandstone and blue-grey masonry follow the city's art direction, so the [texture forge](../../assets/blender/city_r5/forge/forge_textures_r6.py) library is reused directly.

Mood arc: bright arrival → reflective, watery colonnade → quiet puzzle room → dusty, dramatic collapsed dome → a cool blue sanctum lit from above.

## Metric layout (Blender Z-up, metres; +Y is deeper into the temple)

| # | Space | Bounds (x, y) | Floor z | Purpose |
|---|---|---|---|---|
| 1 | Entrance Hall | x −8…8, y −8…8 | 0.0 | Safe arrival, return portal dais at the south wall, first light shaft |
| 2 | Descent stair | x −3…3, y 8…16 | 0 → −3.2 | 20 risers × 0.16 m, 0.32 m treads, landing at both ends |
| 3 | Flooded Colonnade | x −12…12, y 16…48 | −3.2 walkway; −3.6 channels | Combat room 1. Pillar rows at x = ±6 every 6.4 m. Wading channels (water surface −3.3) slow movement and frame the walkway. |
| 4 | Short corridor | x −3…3, y 48…56 | −3.2 | Breather; sightline to the sun gate |
| 5 | Gate of the Sun | x −8…8, y 56…72 | −3.2 | Light puzzle: three mirror pedestals at (−5, 64), (5, 64) and (0, 69) open the north gate (x −2.5…2.5) |
| 6 | Dome ramp | x −3…3, y 72…84 | −3.2 → −6.4 | 15° ramp; first view of the collapsed dome |
| 7 | Collapsed Dome | circle at (0, 100), r = 14 | −6.4 floor; −4.0 ring ledge | Combat room 2 on two levels. Two ramps up to the ledge, rubble for cover, a broken dome ring open to the sky. |
| 8 | Sanctum stair | x −3…3, y 114…124 | −6.4 → −8.0 | 10 risers |
| 9 | Sanctum (boss) | x −16…16, y 124…156 | −8.0 | Central dais r = 4 (three steps), four cover pillars at (±8, 132) and (±8, 148), pools along the east and west edges |
| 10 | Reward alcove | x −4…4, y 156…164 | −8.0 | Chest and return portal |

Walls are 7 m tall and 1.2 m thick, with a foundation course on the bottom 0.8 m and a trim cornice on top. Corridors are 6 m wide, more than the 4 m minimum. Every room has two exits or a dead end that is clearly signposted as a reward.

## Encounters (for the systems/VFX lanes)

- **Colonnade:** 2 statue sentinels (slow, wide telegraphs) and 3 water slimes (splash hop) that use the channels.
- **Gate room:** no combat. Pedestals light up in sequence; failure is safe.
- **Dome:** 4 mixed enemies, plus 1 ranged enemy on the ledge to teach verticality.
- **Sanctum:** Guardian of Aurel (stone colossus). Phase 1 uses ground slams with ring telegraphs; phase 2 floods the pools, which push telegraphs to the dry centre. Reward is server-awarded in the alcove.

## Evidence plan

Blender blockout renders (`BLENDER REVIEW`) from the player camera in every room plus an overview. Babylon capture (`BABYLON CAPTURE`) waits for the D1 transition system or a DEV preview route. Walk both ways along the route, and confirm stair/ramp slopes and the colliders match the traversal export.
