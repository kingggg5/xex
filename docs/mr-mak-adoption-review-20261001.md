# Mr. Mak Workspace — ส่วนที่ใช้กับ Xexoria ได้

ตรวจวันที่ 2026-10-01 · ขอบเขต: clone, อ่าน source/workflow/licence และนำหลักการมาใส่คู่มือคุณภาพ

## Checkout และขอบเขตที่ตรวจ

- Repository: [witnesstodark/mr-mak-workspace](https://github.com/witnesstodark/mr-mak-workspace)
- Local checkout: [references/mr-mak-workspace](../references/mr-mak-workspace)
- Clone แบบ shallow, single branch จาก `main`; commit `f122637a26c584ae1d3e48470d11874517913748`
- Commit date 2026-09-30; release/package version `0.4.15`
- ตรวจ README, LICENSE, THIRD_PARTY_NOTICES, creative production process, workflow ที่เกี่ยวข้อง และบางส่วนของ `img2threejs/forge/next.py` / `state.py`
- ไม่ได้ audit application ทุกบรรทัด และไม่ได้ทดสอบ desktop app, inference, editor bridge หรือ provider jobs
- ไม่ได้รัน Setup, npm install, postinstall, scripts ของ repo, voice, MCP setup หรือเปลี่ยนค่าของแชตหลัก

Checkout นี้ใช้เป็น reference ที่ระบุ revision ได้ การมีโค้ดอยู่ในเครื่องไม่เท่ากับติดตั้ง skill หรือเชื่อมบริการแล้ว

## ข้อสรุป

ส่วนที่เหมาะที่สุดคือ **กระบวนการสร้างและตรวจงานอย่างเป็นขั้นตอน**: แยกภาพเป้าหมายออกจาก mesh, ใช้ข้อมูล scene จริง, มี contract สำหรับการเคลื่อนไหวและเอฟเฟกต์ และให้ภาพจาก engine เป็นหลักฐาน

ตัว workspace เป็นแอปจัดงาน/รายงานและ CLI conversations ไม่ใช่ game engine หรือแพ็กที่ทำให้เมืองสวยโดยอัตโนมัติ ตัวอย่าง Mr. Mak 64 มี concept และภาพจาก Unity; [README ของตัวอย่าง](../references/mr-mak-workspace/projects/my-dream-game/README.md) ระบุว่าไม่มี Unity project หรือ playable build แนบมา และการตรวจ tracked files ที่ลงท้าย `.unity`, `.blend`, `.glb`, `.fbx` ไม่พบไฟล์ใน checkout นี้

## เลือกใช้กับโปรเจกต์นี้

| Workflow ที่อ่าน | สิ่งที่มีประโยชน์ | การใช้ใน Xexoria |
|---|---|---|
| [creative-production](../references/mr-mak-workspace/processes/creative-production.md) | เก็บต้นฉบับ accepted/rejected takes และแยกผลรันจากการยอมรับงานภาพ | ใช้เป็นวงจร A/B ในมาตรฐานคุณภาพ; report อยู่กับระบบเอกสารเดิม |
| [3d-production-routing](../references/mr-mak-workspace/.agents/skills/3d-production-routing/SKILL.md) | เลือกเส้นทางตาม deliverable: concept, mesh, material, rig, animation หรือ VFX | เลือกเครื่องมือเป็นรายงาน ไม่บังคับ AI mesh กับบันไดหรือ kit ที่ต้องวัดแม่น |
| [game-level-design](../references/mr-mak-workspace/.agents/skills/game-level-design/SKILL.md) | source snapshot, proposal แยก, markers, units, clearances, routes และป้องกัน stale revision | ใช้กับการแก้พื้น บันได สะพานและทางเข้า; art/collision/POI เดินทางด้วย revision เดียวกัน |
| [materials-to-game](../references/mr-mak-workspace/.agents/skills/materials-to-game/SKILL.md) | high-to-low, bake cage, UV padding, channels, color space, reimport | ใช้กับชุดหิน/ไม้/หลังคาและ source mesh ที่หนัก; คง KTX2/Meshopt pipeline เดิม |
| [blender-game-animation](../references/mr-mak-workspace/.agents/skills/blender-game-animation/SKILL.md) | กายวิภาค น้ำหนักผิว rigid items, contact, action/slot/fps, runtime skeleton | เสริมการตรวจ Minotaur และตัวละครต่อไป; ไม่ generate supplied character ใหม่โดยไม่จำเป็น |
| [game-animation-integration](../references/mr-mak-workspace/.agents/skills/game-animation-integration/SKILL.md) | แยก controller yaw/root motion, phase ที่เท้ารับน้ำหนัก, interruption และ markers | ปรับเป็น Babylon AnimationGroups และ authoritative events; ไม่คัด Unity Animator/GUID assumptions มาใช้ตรง ๆ |
| [game-vfx-workflow](../references/mr-mak-workspace/.agents/skills/game-vfx-workflow/SKILL.md) + [implementation checks](../references/mr-mak-workspace/.agents/skills/game-vfx-workflow/references/implementation.md) | local/world space, release/contact, cancel, refresh, death, teleport, reuse, cleanup | ใช้กับ slash, น้ำพุ, status effects และอนุภาค; ต้นทุนและ timing ตรวจในฉากจริง |
| [game-ui-workflow](../references/mr-mak-workspace/.agents/skills/game-ui-workflow/SKILL.md) | UI บนภาพเกมเดิม, live data, input blocking, panel/icon consistency | ใช้กับ Svelte/HTML และ minimap มุมมน; คงข้อมูลจริงและตรวจมือถือ |
| [gameplay-visual-review](../references/mr-mak-workspace/.agents/skills/gameplay-visual-review/SKILL.md) | controlled before/after, normal playback, review ผ่าน production code path | เพิ่มเป็นข้อบังคับของการตรวจภาพ; demo แยกที่สวยกว่าไม่ใช้ยืนยันเกม |
| [feature-handoff](../references/mr-mak-workspace/.agents/skills/feature-handoff/SKILL.md) | ขอบเขตไฟล์ revision หลักฐานปัจจุบัน สิ่งที่เหลือ และไม่ชนผู้ร่วมงาน | ใช้รูปแบบ handoff ในงานหลักเมื่อได้รับสิทธิ์ดำเนินงานนั้น |
| [image-reference-workflow](../references/mr-mak-workspace/.agents/skills/image-reference-workflow/SKILL.md) | แยก exploration กับ faithful edit, รักษาภาพที่เลือก, prompt/seed/receipt | ใช้เมื่อผู้ใช้ขอ concept/แก้ภาพจริง ไม่สร้างภาพเพิ่มเพียงให้รายงานดูครบ |

การใช้ในเอกสารรอบนี้คือปรับหลักการเหล่านี้เป็นกติกาและแม่แบบใน [production-quality-standard.md](production-quality-standard.md) และเพิ่มเส้นทางอ่านใน [llm.txt](../llm.txt) ไม่ใช่การรายงานว่าได้ติดตั้งหรือทดสอบ workflows ทั้งหมดแล้ว

## ส่วนที่ต้องดัดแปลงหรือพักไว้

### img2threejs

[skill นี้](../references/mr-mak-workspace/.agents/skills/img2threejs/SKILL.md) เน้นสร้าง procedural Three.js model จากภาพ มี workflow state, pass order และ evidence gates โค้ด `forge/next.py` ที่อ่านจริงตรวจสถานะและบอกขั้นถัดไป/เหตุผลหยุด มันไม่ใช่ตัวตัดสินความสวยอัตโนมัติ

นำแนวคิด blockout → structure → form → material → lighting → interaction → optimization มาใช้ได้ ส่วน code-only Three.js output ต้องประเมินใหม่สำหรับ Babylon/GLB ของเรา โดยเฉพาะใบไม้ ผิวตัวละคร rig และโมเดลรายละเอียดสูง ไม่ตั้งเป็นเส้นทางหลักสำหรับทุก asset ไม่เรียกสคริปต์ upstream โดยอาศัยคำสั่งใน README เพียงอย่างเดียว

หากจะย้าย skill ในอนาคต ต้องรักษา resources/forge/registry ที่มันอ้างถึงและใบอนุญาตให้ครบ การคัดเฉพาะ SKILL.md จะทำให้คำสั่งภายในขาด dependency

### Desktop / reports

ตัวอย่างบอร์ด project/version/prompt และการเก็บ media มีประโยชน์ทางการจัดงาน เลือกทำ report แบบเดียวกันในพื้นที่เดิมได้โดยไม่จำเป็นต้องย้ายเกมเข้าตัว desktop app

การติดตั้งแอปเป็นงานแยก: `package.json` มี postinstall ที่เรียกติดตั้ง service อีกชุด และมีคำสั่งเตรียม desktop/skills sync ต้องตรวจผลต่อระบบและขอบเขตก่อนรัน ไม่ใช่ขั้นจำเป็นของการทำคุณภาพเกมในรอบนี้

### Voice / providers / accounts

Optional voice, fal.ai และ Higgsfield ไม่ใช่ dependency ของคุณภาพเกม และ clone ไม่ได้ทำให้บัญชีหรือสิทธิ์เข้าถึงพร้อมใช้งาน เก็บ credentials และ provider configuration ออกจากเอกสาร/แพ็กที่ส่งต่อ

## ใบอนุญาตและ sample media

[LICENSE](../references/mr-mak-workspace/LICENSE) ใช้ MIT สำหรับ application และ original workflow documentation; การนำส่วนสำคัญไปแจกต่อให้คง notice ตาม licence

[THIRD_PARTY_NOTICES](../references/mr-mak-workspace/THIRD_PARTY_NOTICES.md) แยก `img2threejs` เป็น Apache-2.0 และแยกเงื่อนไขของ dependency/บริการอื่น ตัวอย่าง Arachne/Mr. Mak 64 อนุญาตใช้เรียนรู้และปรับกับ template ตาม notice ของผู้สร้าง แต่ไม่รับรองสิทธิ์ของตัวละครจากบุคคลที่สามหรือคุณภาพ asset พร้อมเล่น

รอบนี้ไม่มีการคัด sample character, photograph, concept image หรือ game art เข้า runtime ของ Xexoria ใช้ศึกษา workflow และวิธีเก็บหลักฐาน พร้อมพัฒนาเอกลักษณ์ของเกมเอง

## Checklist สำหรับการนำ workflow ไปใช้จริงภายหลัง

1. อ่าน `llm.txt` และเลือกงานที่มี scope ชัด เช่น น้ำพุหนึ่งจุดหรือบันไดหนึ่งเส้นทาง
2. อ่าน workflow ที่ตรงงานพร้อม resource ที่อ้างถึง ตรวจเครื่องมือจริงและ source revision
3. ใช้ข้อมูลหน่วย/axes/material/animation/server authority ของ Babylon/Rust/Svelte ปัจจุบัน
4. ระบุไฟล์เจ้าของ แพ็ก candidate และหลักฐานก่อน/หลัง ใช้ permission ที่ผู้ใช้ให้ภายในขอบเขตเดิม
5. ทำงานจนถึง native engine review และการเล่นจริงตามที่เกี่ยวข้อง พร้อมแก้ defect ที่พบ
6. รายงาน technical/visual/gameplay/device verdict แยกกัน และแยก user acceptance จากผลตรวจของ agent

ไม่ต้องรื้อ project structure หรือเครื่องมือเดิมทั้งชุดเพื่อใช้แนวทางเหล่านี้
