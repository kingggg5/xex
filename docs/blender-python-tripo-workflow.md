# Blender Python + Tripo — workflow ที่ทำซ้ำและตรวจคุณภาพได้

ปรับปรุง: 2026-10-01 · ประกอบกับ [มาตรฐานคุณภาพ](production-quality-standard.md) และ [llm.txt](../llm.txt)

ขอบเขตรอบนี้: ศึกษาเอกสารทางการและประสบการณ์ชุมชน แล้วปรับคู่มือ ไม่ได้ติดตั้ง Bridge, รัน inference, สร้างโมเดลใหม่ หรือทดสอบการเชื่อมต่อกับ Blender ในเครื่อง

## 1. ข้อสรุปสำหรับ Xexoria

**ให้ Blender Python เป็นวิธีหลักของงานที่ต้องสร้างซ้ำ วัดได้ และตรวจย้อนหลังได้** โดยใช้ Blender/Geometry Nodes/add-on ที่เหมาะเป็นเครื่องมือทำงานจริง ส่วนการกำหนดรูปทรง วัสดุและ motion ต้องผ่านการตรวจเชิงศิลป์

ข้อเสนอการแบ่งงานนี้เป็นการตัดสินใจสำหรับโปรเจกต์ ไม่ใช่ผล benchmark ว่า Python ชนะทุกวิธี:

| งาน | วิธีเริ่มต้น | งานตรวจ/เก็บรายละเอียดที่ยังจำเป็น |
|---|---|---|
| บ้าน ผนัง หน้าต่าง ประตู รั้ว | Python ประกอบ modular kit จากข้อมูลขนาดและตำแหน่ง | สัดส่วน ความหนา ทิศผนัง รอยต่อ และความซ้ำที่เห็นชัด |
| บันได สะพาน พื้น ทางลาด | Python สร้างจาก dimension/height contract เดียวกับข้อมูลเดิน | ชานต้น–ปลาย step/rise, ราว, clearance และการเดินจริงทั้งสองทิศ |
| ต้นไม้/พืช | เรียก generator ที่เหมาะ เช่น MTree/Geometry Nodes; Python คุม seed และแพ็ก | กายวิภาคต้นไม้ ช่องว่างพุ่ม ขนาดใบ ลม เงา alpha และ LOD |
| Hero prop/รูปปั้น/ตัวละคร | source mesh หรือ Tripo ที่เหมาะ แล้ว cleanup/sculpt/retopo ใน Blender | หน้า มือ รอยเชื่อม รายละเอียดสำคัญ ด้านที่ภาพต้นแบบไม่เห็น |
| Rig/animation | Rigify/เครื่องมือที่เลือก + Python ตั้งค่า bake/export/ตรวจคลิป | skin weights, contact, grip, จังหวะและการเปลี่ยนท่าด้วยสายตา |
| UV/bake/material families | Python จัดและตรวจซ้ำ; ใช้ unwrap/bake tools ของ Blender | seams, distortion, padding, texel density และ response ต่อแสง |
| LOD/แพ็ก/QA | Python และ CLI ที่ pin รุ่นเพื่อทำงานเป็น batch | silhouette และวัสดุหลัง export/compression ใน engine |
| VFX น้ำ/ลม/สกิล | author source/anchors ใน Blender; ให้ Babylon เล่น shader/particles/trail | timing, ownership, cancellation, การมองเห็นและต้นทุนในเกม |

Python เป็นชั้นควบคุม pipeline ไม่ใช่เหตุผลให้เขียนทุกใบ ทุกกิ่ง หรือทุกเอฟเฟกต์ใหม่ด้วย primitives ห้ามแทนการแก้ทรงที่ผิดด้วยการเพิ่ม subdivisions หรือเพิ่ม noise อย่างเดียว

## 2. Tripo DCC Bridge: ข้อมูลที่ยืนยันจากต้นทาง

[คู่มือ Tripo DCC Bridge](https://www.tripo3d.ai/blog/tripo-dcc-bridge-for-blender) ระบุการส่งโมเดลจาก Studio เข้า Blender และให้เลือก animation ที่จะส่ง มีข้อกำหนด Windows/macOS, Blender ≥4.1 และ browser ที่ระบุคือ Chrome/Edge ≥116 หรือ Opera ≥102; การใช้รุ่นที่ใหม่กว่ายังต้องตรวจจริงกับ add-on ที่ติดตั้ง

ค่า default ที่บทความระบุ:

| ค่า | ค่าในบทความ |
|---|---|
| `pack_uv` | `false` |
| `export_vertex_colors` | `false` |
| `pivot_to_center_bottom` | `true` |
| Texture | Current Maximum |

FAQ ระบุว่า connection ใช้ Blender instance แรกที่เปิด และหลาย instance อาจทำให้พอร์ตชนกัน ข้อเท็จจริงส่วนนี้มาจากเอกสารผู้ให้บริการ ไม่ใช่ผลทดสอบ Bridge บนเครื่องนี้. [Tripo requirements/defaults/FAQ](https://www.tripo3d.ai/blog/tripo-dcc-bridge-for-blender)

### ความหมายต่อ pipeline ของเรา

รายการต่อไปนี้เป็นข้อกำหนด QA ของ Xexoria ที่อนุมานจากค่าเหล่านั้นและโครงสร้างเกม:

- ตรวจ UV จริงทั้งก่อน/หลังส่ง ไม่สมมุติว่า `pack_uv=false` รับรอง UV จากทุกขั้นก่อนหน้า
- ถ้า asset ใช้ vertex color เป็นสี, AO หรือ mask ต้องตรวจว่าข้อมูลที่จำเป็นยังอยู่ ถ้าขาดให้เลือกเส้นทาง export ที่รักษาข้อมูลนั้นได้
- เมื่อ pivot เปลี่ยน ต้องตรวจจุดวาง collider, root, sockets และ bind pose ไม่ชดเชยด้วยการเดา offset ในเกม
- เก็บ texture ต้นฉบับที่ได้รับไว้ แล้วทำ runtime variant; ค่า maximum ไม่ใช่งบ texture ของมือถือ
- เปรียบเทียบจำนวน mesh/material, bounds, triangles, texture dimensions, skeleton และชื่อ/ช่วงคลิปกับ asset ที่เลือกใน Studio
- Bridge ช่วยขั้นรับไฟล์ ไม่ได้พิสูจน์ topology, PBR maps, collision หรือ visual acceptance

### เส้นทางรับไฟล์ที่แนะนำ

`Studio asset ที่เลือก → Bridge receiver ที่ระบุได้ → ingest candidate → บันทึก source → Python cleanup/validation → runtime export → Babylon review`

1. ระบุ asset/job ID และ revision ที่จะรับก่อนส่ง ป้องกันสับสนระหว่างตัวละครหรือ texture take
2. มีเจ้าของ Bridge receiver หนึ่งคน/งาน บันทึก Blender process/session และ collection ที่รับ ไม่ปล่อยหลาย worker แย่งแก้ไฟล์เดียว
3. ถ้าต้องแก้ปัญหาพอร์ต ให้ตรวจ log และสถานะจริงก่อน ไม่ปิดหรือ restart Blender ของงานอื่นโดยพลการ
4. หลังรับสำเร็จ บันทึก source copy/metadata ลงที่ใหม่ก่อน cleanup; อย่านำเข้าทับ rig หรือ master ที่เก็บงานแล้ว
5. หาก Bridge ใช้ไม่ได้ ให้ export ไฟล์จาก Studio และผ่าน intake gate เดิมต่อได้ ไม่ต้อง generate งานใหม่เพียงเพื่อย้ายไฟล์
6. Generation, retexture, remesh หรือ rigging ที่ใช้บริการยังต้องอยู่ในขอบเขตการอนุญาต/งบของงาน การเชื่อม Bridge ไม่ใช่การอนุญาตใช้เครดิตเพิ่ม

ไม่ใส่ API key, token, signed URL หรือข้อมูลล็อกอินลงใน script, asset manifest หรือเอกสาร handoff

## 3. แยกชั้นข้อมูลก่อนเขียน script

ใช้ที่เก็บเดิมของโครงการก่อน โครงสร้างต่อไปนี้เป็น logical stages ไม่ใช่คำสั่งให้ย้ายไฟล์ที่ใช้อยู่:

| ชั้น | เนื้อหา | กฎ |
|---|---|---|
| Reference | ภาพ/brief/สัดส่วนและภาพเกม baseline | ระบุว่าอะไรสังเกตจากภาพ อะไรเป็นการอนุมาน |
| Source | provider export, asset ฟรี หรือ master ที่รับมา | immutable; hash และ provenance |
| Recipe | Python, parameter JSON, seeds, texture/rig dependencies | ตรวจรุ่น Blender และ API ที่ใช้ |
| Artist overrides | งานแก้มือที่ยอมรับแล้ว | แยกจาก generated collection; rebuild ต้องไม่ลบทิ้ง |
| Candidate | editable blend, GLB/texture/collision และ metadata | review ได้; ไม่เขียนทับ accepted package อัตโนมัติ |
| Evidence | ภาพ/คลิป/ตรวจโครงสร้าง/ทางเดิน/อุปกรณ์ | ใช้ revision เดียวกับของที่ส่ง |

Stable ID ของวัตถุควรเป็น custom property หรือข้อมูลกำกับที่ชัด เช่น `asset_id`, `part_id`, `source_revision`, `generated_by` อย่าอาศัยชื่อ auto suffix อย่าง `.001` เป็นตัวตนเพียงอย่างเดียว

## 4. สัญญาของ Blender Python script

ทุก recipe ที่จะใช้ซ้ำควรมีข้อกำหนดต่อไปนี้:

1. **Input ชัด:** source/spec/seed/tool version/output directory และขั้นงานที่จะทำ ห้ามเดาว่าฉากหรือ selection ปัจจุบันเป็นของงานนี้
2. **Preflight:** ตรวจ source hash, dependency paths, หน่วย/axes, output ownership และข้อกำหนด asset ก่อนเริ่มเขียน
3. **Reproducibility:** เก็บ seed และเรียง input อย่างคงที่; เปรียบเทียบ topology/bounds/material/clip invariants ไม่รับรองว่า `.blend` จะ byte-identical เสมอ
4. **Idempotence:** รัน recipe เดิมแล้วไม่เพิ่มวัตถุซ้ำ ไม่สะสมวัสดุ/texture/action ซ้ำใน collection ของงาน ทดสอบทั้ง clean run และ rerun บน candidate
5. **Scope:** สร้าง/แก้เฉพาะ collection หรือ IDs ที่เป็นเจ้าของ ยืนยันรายการที่จะเปลี่ยนก่อนทำ destructive mesh operation ไม่ใช้ select-all/delete กับฉากที่ไม่รู้สถานะ
6. **Artist edits:** ใช้ source revision และ override layer ที่ตรวจได้ ถ้า source เปลี่ยนให้ reconcile ก่อน ไม่ regenerate กลบทับงานเก็บมือ
7. **Exact transforms:** บันทึกการแปลง units/axes/handedness/pivots; ประเมิน world matrix ก่อนและหลังเปลี่ยน parent ไม่ใช้ object location อย่างเดียวแทน world placement
8. **Data layers:** รักษา UV, color attributes, normals, shape keys, weights และ material bindings ที่เกี่ยวข้อง ข้อมูลที่ intentionally เปลี่ยนต้องมีเหตุผลและการตรวจ
9. **Stages:** แยก build/cleanup/rig/bake/export/validate/render ให้ตรวจทีละขั้นได้ แต่ใช้ spec และ source ชุดเดียวกัน
10. **Failure:** ถ้า invariant สำคัญไม่ผ่าน ให้หยุดและส่ง error จริง ไม่ catch แล้วรายงานสำเร็จ ไม่เขียน receipt PASS ก่อนตรวจ output bytes
11. **Outputs:** ระบุไฟล์ที่สร้างจริง ขนาด hash bounds จำนวน geometry/material/texture/skin/clip และการเปลี่ยนแปลงจาก baseline
12. **Resource limits:** จำกัดจำนวนวัตถุ geometry, texture sizes, recursion และระยะเวลา เปิดหลาย Blender process ตาม RAM/VRAM ที่วัดได้ ไม่ตามจำนวน agent ที่ต้องการอย่างเดียว

ควรมีตัวอย่าง input ที่ทำให้ script ปฏิเสธได้ถูก เช่น source hash เปลี่ยน, ไม่มี texture, joint เปลี่ยนชื่อ, จำนวนหน้าต่างผิด, ไม่มี landing หรือ output ชี้กลับไป source

## 5. ใช้ Python API ให้เหมาะกับงาน

- ใช้ `bpy.data` เมื่อระบุ datablock/วัตถุได้ชัดและต้องการ automation ที่ไม่ขึ้นกับ selection; ใช้ BMesh สำหรับงานแก้โครงสร้าง mesh ที่เหมาะสม. [Data access](https://docs.blender.org/api/current/info_api_reference.html), [BMesh](https://docs.blender.org/api/current/bmesh.html)
- `bpy.ops` ไม่ได้ผิด แต่หลาย operator ต้องการ context/mode ที่ถูก ตรวจ `poll()` และกำหนด active/selected objects หรือ context override ที่เกี่ยวข้อง ห้ามแก้ด้วยการทำให้ทั้งฉาก selected โดยไม่ทราบผล. [Operators](https://docs.blender.org/api/current/bpy.ops.html)
- ตรวจ mesh ที่ถูกประเมินหลัง modifiers/constraints/animation ผ่าน depsgraph เมื่อวัดผลที่ผู้เล่นจะเห็น และคืน temporary mesh หลังตรวจ. [Evaluated data](https://docs.blender.org/api/current/bpy.types.Depsgraph.html)
- เลือก API ตาม Blender/add-on รุ่นที่ใช้งานจริง ไม่ยก API ของรุ่นเก่ามาใช้แล้วเงียบข้ามสิ่งที่ error
- ใช้ native tools เช่น bevel, unwrap, bake, decimate, Rigify, Geometry Nodes และ generator ที่ผ่านการตรวจ แทนการสร้างกลไกซ้ำโดยไม่มีประโยชน์ต่อคุณภาพ

ตัวอย่างการเรียก batch **เป็นแม่แบบเท่านั้น**; `<...>` ต้องแทนด้วย paths ของ script/spec ที่ผ่าน review ไม่ได้สร้าง script ตามชื่อนี้ไว้ในการปรับเอกสาร:

```powershell
& '<Blender executable>' --background --factory-startup --disable-autoexec --python-exit-code 1 --python '<reviewed recipe.py>' -- --source '<source file>' --spec '<spec.json>' --out '<candidate directory>'
```

Blender ประมวลผล arguments ตามลำดับ ตั้งค่าการจัดการ exception ก่อนเรียก Python และแยก arguments ของ recipe หลัง `--`; recipe เป็นผู้ parse เอง `--disable-autoexec` ไม่ได้ทำให้ script ที่สั่งผ่าน `--python` กลายเป็น sandbox จึงยังต้องตรวจ script และขอบเขตไฟล์. [Blender CLI](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html), [script execution](https://docs.blender.org/manual/en/latest/advanced/scripting/security.html)

หลังจบ process ให้ตรวจ error, output ใหม่และ manifest จริงอีกชั้น อย่าถือว่าไฟล์เก่าที่ค้างอยู่หรือ exit code อย่างเดียวพิสูจน์ว่ารอบนี้สำเร็จ

## 6. กระบวนการสร้างโมเดลที่กันงานดูหยาบ

| Pass | สิ่งที่ทำ | เกณฑ์ให้ไปต่อ |
|---|---|---|
| 0 Reference | แยกรูปทรงและวัสดุ กำหนด dimensions และ features ที่ห้ามผิด | brief มีภาพ/ข้อมูลพอสำหรับงานนั้น |
| 1 Blockout | มวลใหญ่ สัดส่วน ช่องเปิด พื้นที่เดิน | player/front/side เห็นหน้าที่และสัดส่วนถูก |
| 2 Construction | ฐาน เสาค้ำ กรอบ ชายคา รอยต่อ บันได/landing | ประกอบอย่างน่าเชื่อถือและเดินได้ |
| 3 Form | เก็บ silhouette/โค้ง/bevel/ข้อต่อและความไม่สมมาตรที่ตั้งใจ | ไม่ใช่กล่อง/กรวยหยาบที่ใช้ texture ซ่อน |
| 4 Surface | UV/trim/bake/material scale; wear ตามเหตุผล | วัสดุแยกกันชัด ไม่มีรอยยืดหรือ repeating dirt เด่น |
| 5 Motion | rig/wind/clip/VFX anchors ตามบทบาท | จุดสัมผัสและการเคลื่อนไหวไม่พัง |
| 6 Runtime | export + compression + reimport + integration | ภาพ/ข้อมูลหลังส่งออกตรงกับสิ่งที่รับรอง |
| 7 Review | เปรียบเทียบกล้องเดิม แสงเดิม และสถานการณ์เล่นจริง | ผ่าน gate ของงานนั้น พร้อมรายการสิ่งที่ยังไม่ผ่าน |

การเปลี่ยนค่ารายละเอียดต้องตอบ defect ที่ระบุได้ เช่น “กรอบหน้าต่างหันผิดด้าน” ต้องแก้ local basis/assembly orientation ไม่ใช่เพิ่มความละเอียด texture; “ต้นดูเป็นก้อนทึบ” ต้องแก้ branching/leaf distribution ไม่ใช่เพิ่มจำนวนใบอย่างเดียว

สำหรับ hero character, ใบหน้า, มือ, ผ้า และชิ้นส่วนออร์แกนิกซับซ้อน ให้ยอมใช้ sculpt/retopo/weight painting และแก้ motion โดยตรงเมื่อได้ผลดีกว่า แล้วเก็บขั้น bake/export/QA ให้ทำซ้ำได้ด้วย Python

## 7. จาก Blueprint และ Tripo ไปเป็นแพ็กที่เล่นได้

เส้นทางมาตรฐาน:

```text
Reference + metric spec
   -> choose existing/free asset, procedural kit, manual build or Tripo draft
   -> immutable source + editable candidate
   -> geometry/UV/rig/art correction
   -> runtime mesh/material/collision/clip package
   -> reimport the delivered files into a clean scene
   -> Babylon player-camera and traversal/combat review
   -> device qualification where the scope requires it
```

ใช้ script ประกอบเมืองจากโมดูลที่ผ่านแล้ว และคงการแก้แต่ละอาคารแยกได้ Hero statue หรือ prop จาก Tripo ควรเป็นหนึ่งชิ้นที่เปลี่ยนแทนได้ ไม่ผูกทั้งเมืองเป็นก้อนที่ทุกการแก้ต้อง generate ใหม่

glTF รองรับชุดข้อมูลเฉพาะ รวมถึง mesh/material/texture/skin/animation และตัวเลือกส่ง vertex colors แต่ไม่ได้รับรองว่า Blender graph หรือผลทุกชนิดจะมีความหมายเท่าเดิมในเกม ตรวจไฟล์ที่ exporter สร้างจริงและการนำเข้า. [Blender glTF documentation](https://docs.blender.org/manual/en/latest/addons/scene_gltf2.html)

สิ่งที่ต้องเทียบก่อน/หลัง Bridge, cleanup และ export:

- shape/bounds และ scale เทียบกับตัวละครหนึ่งเมตร/ความสูงที่กำหนด
- ช่องเปิดและจุดชน ตำแหน่ง anchors และชิ้นส่วนที่ต้องแข็ง
- triangle/vertex counts, UV sets, normals/tangents และ color attributes ที่ต้องใช้
- material slots, texture dimensions, channel packing และ alpha
- จำนวน/ตัวตน joint, weights, bind basis, loop duration และ gameplay markers
- dependency ที่ต้องแพ็ก ไม่มี texture ที่อ้างถึงเฉพาะเครื่องผู้สร้างโดยไม่ตั้งใจ

ถ้า vertex count เปลี่ยนจาก UV/normal seams อย่าตัดสินว่า geometry เสียจากจำนวนอย่างเดียว ใช้การตรวจที่ตรงกับ invariant ที่ต้องการ เช่น shape, UV mapping, skin และผลในเกม

## 8. สิ่งที่ Reddit ช่วยตั้งคำถามให้ตรวจ

ค้นวันที่ 2026-10-01 เน้นตัวอย่างปี 2026 และใช้โพสต์เก่าเพื่อดูวิธีคิดที่ยังเกี่ยวข้องเท่านั้น ความเห็น/การเล่าผลงานอาจมีการโปรโมตและไม่มีไฟล์หรือ benchmark ให้ตรวจ ไม่ถือเป็นฉันทามติหรือคำรับรองคุณภาพ ไม่ใช้จำนวนโหวตเลือกเครื่องมือ

| แหล่ง | สิ่งที่พบในโพสต์ | ข้อทดสอบที่เรานำมาใช้ |
|---|---|---|
| [UE5 stylized environment workflow](https://www.reddit.com/r/TopologyAI/comments/1rucklz/how_i_built_a_ue5_stylized_environment_with_3d_ai/), 2026-03-15 | ผู้สร้างเล่าว่าแยก concept เป็น props แล้ว cleanup, UV/texture, emission และจัดแสง | ตรวจทีละ asset และแสงในฉากจริง; การ generate เป็นเพียงหนึ่งขั้น ไม่ใช่ pipeline ทั้งชุด |
| [AI headgear workflow](https://www.reddit.com/r/TopologyAI/comments/1v31ibh/i_made_gameready_assets_for_my_game_in_just_two/), 2026-07-22 | มีทั้งรายงานผลเร็วและคำถามเรื่อง faces/8K texture/การวางหลายชิ้น | วัด triangles หลัง export และทดสอบจำนวนพร้อมกันจริง; ไม่ใช้ 8K หรือเวลาที่ผู้โพสต์อ้างเป็นเป้าความสำเร็จ |
| [Trim sheets / scanned materials](https://www.reddit.com/r/gamedev/comments/1woum3v/megascans_textures_or_trim_sheets/), 2026-09-24 | ผู้ร่วมคุยแยกประโยชน์การใช้ texture ร่วมจากคำกล่าวว่าเร็วกว่าเสมอ | เทียบ material/texture residency และ draw cost จริงของชุดซ้ำกับชิ้นเด่น ไม่เปลี่ยนทั้งเมืองเป็น unique maps |
| [Animator to technical-art workflow](https://www.reddit.com/r/TechnicalArtist/comments/1vqbke8/feedback_on_my_workflow_transition_3d_animator/), หน้าแสดงประมาณหนึ่งเดือนก่อนตรวจ | ผู้ร่วมคุยขอหลักฐาน rig scripts, pipeline และ game-engine work นอกเหนือจาก reel | ส่ง recipe, ผลที่ทำซ้ำได้ และ native capture ควบคู่ภาพสวย; ไม่อ้างคุณวุฒิผู้โพสต์เป็นการตรวจโค้ด |
| [Procedural Blender community examples](https://www.reddit.com/r/blender/comments/kd0tg4/), 2020-12-14 | มีตัวอย่างผู้ใช้ Blender/Python สร้าง procedural geometry | ใช้หาแนวคิดเท่านั้น; API และความเข้ากันได้ต้องกลับไปตรวจเอกสารปัจจุบัน |
| [Modular asset tradeoffs](https://www.reddit.com/r/gamedev/comments/1bszto7/), 2024-04-01 | มีการคุยเรื่องการใช้โมดูลร่วม การประกอบเป็นชิ้นใหญ่ และการมองเห็น | ทดสอบทั้ง authoring modularity กับ runtime grouping/culling ไม่สรุปว่าหนึ่งบ้านหนึ่ง mesh หรือแยกทุกชิ้นดีที่สุดเสมอ |

โพสต์เหล่านี้ให้แนวคิดและ failure cases; ข้อกำหนด API ใช้เอกสารทางการ ความเหมาะสมกับ Xexoria ต้องยืนยันจากแพ็กและการวัดของเราเอง รอบค้นนี้ยังไม่พบหลักฐาน Reddit ที่น่าใช้ยืนยันความเสถียรเฉพาะ Tripo DCC Bridge จึงใช้คู่มือ Tripo เป็นข้อมูลการเชื่อมต่อ และคงสถานะ runtime compatibility เป็น UNVERIFIED

## 9. การทดลองขนาดเล็กก่อนขยาย pipeline

ใช้สามชิ้นที่ตอบปัญหาคนละแบบ โดยไม่เปลี่ยนเกมทั้งระบบพร้อมกัน:

1. **Window bay / stair module:** Python สร้างหลาย orientation/ขนาดจาก spec; ตรวจกรอบที่หันตามผนัง รอยต่อพื้น ช่องเดิน และ rerun ที่ไม่ซ้ำวัตถุ
2. **Hero prop จาก Tripo:** รับผ่าน Bridge หรือ file export, เก็บ source แล้วทำ cleanup/LOD; เทียบ silhouette/UV/สี/ข้อมูลที่ส่งต่อใน Babylon จากมุมเดิม
3. **ต้นไม้หนึ่งต้น:** ใช้ generator ที่เลือกและ Python wrapper; ตรวจ player/side/elevated view, ลม เงา LOD และ repeated instances

ระบุเวลาแต่ละช่วงแยกกัน: เตรียมภาพ/รอ generate/แก้ geometry/วัสดุ/rig/รับเข้า engine/แก้หลัง review ประเมินต้นทุนต่อ **ชิ้นที่ผ่านจริง** หากใช้ Bridge ลดเวลารับไฟล์ ให้รายงานช่วงนั้น ไม่อ้างว่าลดเวลาสร้าง asset ทั้งหมดโดยยังไม่วัด

ผ่าน recipe เมื่อ source/artist overrides ปลอดภัย การรันซ้ำไม่สะสม geometry ข้อมูลส่งออกครบ และแก้ defect เป้าหมายได้จริง ผ่านงานภาพเมื่อเทียบ reference และ engine capture ตาม [quality gates](production-quality-standard.md#16-%E0%B9%80%E0%B8%81%E0%B8%93%E0%B8%91%E0%B9%8C%E0%B8%9C%E0%B9%88%E0%B8%B2%E0%B8%99%E0%B8%97%E0%B8%B5%E0%B9%88%E0%B8%95%E0%B8%A3%E0%B8%A7%E0%B8%88%E0%B8%A2%E0%B9%89%E0%B8%AD%E0%B8%99%E0%B8%AB%E0%B8%A5%E0%B8%B1%E0%B8%87%E0%B9%84%E0%B8%94%E0%B9%89) ไม่เปลี่ยนสองคำนี้ให้เป็นความหมายเดียวกัน

## 10. Prompt สำหรับสั่งงาน Blender Python

```text
Read llm.txt, the quality standard, and this Blender Python workflow.
Task: [one asset or bounded scene change]. Target engine: Babylon.js.
Source/reference: [paths + known revision]. Owned outputs: [candidate paths].
Important invariants: [metres, axes, dimensions, openings, materials, contacts].
First inspect existing geometry, UVs, rigs, actions and dependencies.
Prefer a reviewed Python recipe using Blender data/BMesh/native tools and
existing generators for repeatable operations. Use manual sculpt/retopo or
artist overrides where they produce better forms; preserve those edits.
Do not regenerate unrelated work. Build in passes, verify each pass, and
compare the actual exported asset at the player's camera, side and close views.
Record input/output hashes, parameters, tool versions and the observed defects.
Test rerun behavior and a clean reimport. If a pass fails, repair its cause.
Return technical, visual, gameplay and device verdicts separately. Missing
evidence stays UNVERIFIED. Do not infer AAA quality from script execution.
```

## 11. แหล่งทางการและขอบเขตหลักฐาน

อ่าน Context7 สำหรับ Blender API/manual ปัจจุบัน และเปิดแหล่ง Reddit ตามคำขอโดยตรง แหล่งสำคัญอ้างไว้ใกล้ข้อความด้านบน วันที่ตรวจไม่ได้แปลว่าทุกเครื่องมือมีรุ่นเดียวกันกับเครื่องเรา

สิ่งที่ยังไม่ได้พิสูจน์ในรอบเอกสาร: Bridge ติดตั้ง/ต่อได้บนเครื่องนี้หรือไม่, รูปทรง/ข้อมูลของไฟล์ที่ส่งจริง, การทำงานกับ Blender instance หลายตัว, คุณภาพภาพหลัง export และ FPS บนอุปกรณ์เป้าหมาย ไม่มีการเริ่มหรือหยุด process ของงานหลักเพื่อทำการศึกษานี้
