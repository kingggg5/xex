# Xexoria — มาตรฐานงานภาพและเกมที่เล่นได้จริง

วันที่: 2026-10-01 · เอกสารกำกับคุณภาพสำหรับ LLM, ผู้สร้าง asset และผู้ตรวจงาน

จุดเริ่มอ่านสำหรับงานใหม่: [llm.txt](../llm.txt)

## 1. เป้าหมายและอำนาจของเอกสาร

ผู้ใช้ระบุว่างานภาพ โมเดล รายละเอียด และความใกล้ต้นแบบยังไม่ผ่าน แม้มีแผนระยะยาวแล้ว เอกสารนี้เปลี่ยนคำว่า “ทำให้สวยขึ้น” เป็นวิธีผลิต ตรวจ และแก้ที่พิสูจน์ได้ เป็นข้อกำหนดสำหรับงานต่อไป ไม่ใช่คำรับรองว่างานปัจจุบันสวยหรือเสร็จแล้ว

ยึด Ragnarok เป็นแกนประสบการณ์ MMO: สำรวจ ต่อสู้ เติบโต เลือกอาชีพ ปรับอุปกรณ์ กลับเมือง และเล่นกับผู้อื่น ใช้คุณภาพด้านการประกอบฉาก วัสดุ แสง และน้ำหนักการเคลื่อนไหวจากเกมระดับสูงเป็นมาตรฐานความประณีต

- **God of War:** ศึกษามวลอาคาร ความน่าเชื่อถือของวัสดุ การนำสายตา น้ำหนักตัวละคร และจังหวะเปิดเผยพื้นที่
- **Warcraft:** ศึกษาเงาร่างที่อ่านง่าย สัดส่วนแฟนตาซี เอกลักษณ์ย่านและแลนด์มาร์ก และความชัดเจนระหว่างต่อสู้
- **Ragnarok:** รักษาความรู้สึกของโลก การเติบโต การเลือก build และความสำคัญของเมือง
- รวมคุณสมบัติเหล่านี้ภายใต้ art direction ของ Xexoria ชุดเดียว ห้ามให้แต่ละ asset เปลี่ยนแนวภาพเอง

คำว่า AAA หมายถึงความประณีตและวินัยการผลิตที่ต้องการ ไม่ได้หมายความว่ามีงบ ทีม หรือผลลัพธ์เทียบเท่าเกมเหล่านั้นแล้ว ไม่รับรองคุณภาพด้วยระยะเวลาที่ใช้ จำนวน agent จำนวน polygon หรือคำอธิบายที่ดูซับซ้อน

คำสั่งผู้ใช้ล่าสุดและข้อกำหนดระดับระบบมีลำดับเหนือเอกสารนี้ เอกสารอ้างอิงไม่อนุญาตให้ซื้อ ใช้เครดิต เผยแพร่ ลบงาน หรือติดตั้งเครื่องมือเอง การอนุญาตที่มีอยู่ใช้ต่อได้ภายในขอบเขตเดิม งานนี้ยังต้องเคารพข้อจำกัดเครื่องมือและการแบ่งเจ้าของไฟล์จริง

เอกสารนี้ไม่ได้ปรับสถานะงานในแชตหลัก ไม่ได้สร้าง agent และไม่ได้ติดตั้งระบบบังคับอ่านอัตโนมัติ ให้ผู้รับงานอ่านไฟล์นี้ก่อนเริ่มงานที่เกี่ยวข้อง

## 2. ลำดับการตัดสินใจ: คุณภาพก่อนการขยาย

ลำดับแก้ไขมาตรฐาน:

1. เกมเล่นได้และข้อมูลตรงกัน: ทางเดิน พื้น บันได ประตู collision การโต้ตอบและรางวัล
2. องค์ประกอบฉาก สเกล เงาร่าง และการนำสายตา
3. วัสดุ แสง เงาสัมผัส และความกลมกลืน
4. การเคลื่อนไหว VFX เสียง และการตอบสนอง
5. รายละเอียดเล็กและการแต่งฉากเฉพาะจุด
6. ปรับการส่งไฟล์และต้นทุนในเกม โดยรักษาภาพที่ผ่านแล้ว

หยุดเพิ่มพื้นที่หรือจำนวนแบบ asset หากพื้นที่มาตรฐานยังมีข้อบกพร่องสำคัญ งานที่อนุญาตให้ทำคู่กันได้คือการแก้ระบบ การค้นหาทางเลือกที่มีขอบเขต และการเตรียมชิ้นส่วนที่ไม่ชนกัน ไม่ใช้การเพิ่มบ้าน ต้นไม้ หญ้า แสง หรือเอฟเฟกต์เพื่อกลบปัญหาขององค์ประกอบหลัก

**Sunmeadow เป็นพื้นที่มาตรฐานแรก; ลาวาตามมาเมื่อวงจรผลิตและคุณภาพแรกพิสูจน์แล้ว** เป้าหมายระยะยาวยังคงอยู่ แต่จำนวนระบบใน roadmap ไม่ใช่หลักฐานความสำเร็จของฉากที่กำลังทำ

## 3. แปลงภาพต้นแบบเป็นข้อกำหนดที่สร้างได้

ก่อนสร้างหรือแก้ทุกชิ้น ให้ทำ reference breakdown สั้น ๆ:

| หัวข้อ | ต้องระบุ |
|---|---|
| บทบาท | ผู้เล่นทำอะไรกับสิ่งนี้ เห็นจากที่ใด และใช้เป็นจุดสังเกตหรือไม่ |
| รูปทรงหลัก | สัดส่วน ความสูง ความกว้าง เส้นขอบ มวลใหญ่และพื้นที่ว่าง |
| การประกอบ | จำนวนชิ้น จุดยึด ความหนา ช่องเปิด และส่วนที่เคลื่อนไหว |
| วัสดุ | ชนิดวัสดุหลัก สี ความหยาบ ขนาดลาย และตำแหน่งการสึก |
| แสง | ทิศของแสงหลัก สีแสงเติม ความอ่อนของเงา จุดเรืองแสง |
| มุมตรวจ | กล้องผู้เล่น มุมข้าง มุมใกล้ มุมสูง พร้อมขนาดตัวละครอ้างอิง |
| สิ่งที่ต้องตรง | เช่น ตำแหน่งแลนด์มาร์ก รอยต่อบันได รูปทรงใบไม้ หรือการจับอาวุธ |
| สิ่งที่ยอมปรับ | รายละเอียดย่อยที่ลดต้นทุนได้โดยไม่เปลี่ยนสิ่งสำคัญ |

ภาพ diorama หรือ collage อาจมีสเกลและมุมมองที่ไม่สอดคล้องกัน ต้องแปลงเป็นผังหน่วยเมตรที่เดินได้ ไม่ย่อเมืองทั้งเมืองเพื่อให้จัดเฟรมได้ง่าย ไม่บังคับให้มุม top view และมุม perspective ที่ขัดกันกลายเป็นข้อมูลวัดเดียวกัน

เปรียบเทียบภาพที่ขนาดแสดงผลเท่ากันและใกล้กล้องเดียวกัน ใช้ภาพ concept เป็นเป้าหมาย ใช้ภาพจากเกมเป็นหลักฐานผลลัพธ์ ระบุที่มาบนภาพทุกครั้ง: `CONCEPT`, `BLENDER REVIEW`, `BABYLON CAPTURE`

## 4. Art direction ร่วมของ Xexoria

ฐานภาพคือแฟนตาซีที่มีรูปทรงอ่านง่ายและวัสดุมีน้ำหนัก มีความอบอุ่นของเมืองและความน่าค้นหาของธรรมชาติ

- หินโทนอุ่น ปูนสีอ่อน ไม้เข้ม หลังคาน้ำเงิน และโลหะเน้นสีที่ใช้เท่าที่จำเป็น
- รูปทรงใหญ่สื่อหน้าที่ก่อน: หลังคา ผนัง ฐาน บันได สะพาน กิ่งหลัก และเงาร่างตัวละคร
- ใช้รอยต่อ ร่อง เงาสัมผัส สีและ roughness variation อย่างมีเหตุผล รอยสึกเกิดตามขอบสัมผัส น้ำไหล และจุดใช้งาน
- รักษาพื้นผิวกว้างบางส่วนให้สงบเพื่อให้รายละเอียดเด่นขึ้น ไม่ใส่ noise เท่ากันทุกตารางนิ้ว
- ความหนาของประตู กรอบหน้าต่าง เสาค้ำ ชายคาและราวต้องน่าเชื่อถือจากด้านข้าง
- พื้นหน้า กลาง และฉากไกลมี contrast และรายละเอียดต่างกัน ตัวละครกับพื้นที่ต่อสู้ต้องอ่านง่าย
- ใช้ชุดวัสดุและ texel density ที่สอดคล้องกัน ห้ามให้ asset เดียวคมจัดหรือสมจริงผิดกลุ่มโดยไม่มีเจตนา

หากจะเปลี่ยน art direction ให้แสดงภาพเปรียบเทียบอย่างเป็นระบบและบันทึกการตัดสินใจ อย่าปล่อยให้การเลือก asset ฟรีทีละชิ้นเปลี่ยนหน้าตาของเกมไปเอง

## 5. Workflow สอง AI / สองบทบาท

กรอบการทำงานบังคับคือ **Harness best-in-code + GPT + Jev + CUA/DOM/computer use + Fast Jev context carryover** ตาม [ข้อกำหนดชุดเครื่องมือ](harness-jev-gpt-toolchain.md) ใช้ทุกส่วนที่เกี่ยวข้องและพร้อมจริง พร้อมบันทึกเหตุผลเมื่อใช้ไม่ได้หรือไม่เกี่ยวกับขั้นงาน จำนวนเครื่องมือไม่ทดแทนคุณภาพ และ policy ในเอกสารไม่ถือว่าเปิด hook/connection แล้ว

ผู้ใช้ย้ำให้ **Jev เป็น always-on companion ทุก task** สำหรับคัดบริบท/เลือกขั้นถัดไป ใช้ผลเดิมต่อและอัปเดตเมื่อข้อมูลสำคัญเปลี่ยน ห้ามข้ามเพียงเพราะงานเล็ก ถ้าใช้ไม่ได้ต้องระบุเหตุผลจริง การเรียกถี่โดยไม่มีข้อมูลใหม่ไม่ใช่หลักฐานความเร็วหรือการประหยัด

ใช้สองบทบาทเป็นแกน ไม่ผูกกับยี่ห้อโมเดลหรือจำนวน worker:

| บทบาท | ความรับผิดชอบ | สิ่งที่ส่งต่อ |
|---|---|---|
| A — Art Director / Concept / Reviewer | วิเคราะห์ภาพ ออกแบบองค์ประกอบ เตรียมภาพและ brief ตรวจผลจริง จัดลำดับข้อบกพร่อง | ภาพเป้าหมาย ข้อกำหนดทางรูปทรงและรายการแก้พร้อมตำแหน่งในภาพ |
| B — Builder / Technical Artist / Engineer | เลือก asset/tool ที่เหมาะ สร้าง/แก้ Blender, UV, rig, VFX, collision, export และนำเข้าเกม | ไฟล์แก้ไขได้ runtime asset การวัด และภาพ/คลิปในเกม |

วงจรต่อหนึ่งชิ้นหรือหนึ่งพื้นที่:

1. A ระบุเป้าหมายที่ตรวจได้และช็อตเปรียบเทียบก่อน
2. ค้นหาของเดิมและของฟรีที่เหมาะ เลือกวิธีทำโดยเปรียบเทียบคุณภาพ เวลาซ่อม ความเข้ากันได้ และต้นทุนในเกม
3. A สร้างภาพ concept เมื่อภาพช่วยตัดสินใจจริง ล็อกข้อกำหนดสำคัญก่อนสร้าง mesh
4. B ทำ blockout และทางเดินในขนาดจริง ตรวจผู้เล่นและ collision ก่อนลงรายละเอียดหนัก
5. B ทำ asset candidate และส่งเข้า Babylon พร้อมวัสดุ/แสงเป้าหมาย
6. A ตรวจภาพและคลิปจริง ระบุข้อเสีย 3–5 ข้อที่มีผลมากที่สุด พร้อมระดับความรุนแรง
7. B แก้สาเหตุ แล้วส่งหลักฐานเปรียบเทียบจากช็อตเดิม
8. ตรวจสี่ด้านแยกกัน: ระบบ ภาพ การเล่น และประสิทธิภาพ ก่อนยกระดับสถานะ

หากไม่มี agent แยกจริง ให้ทำบทบาทตามลำดับและระบุว่าเป็น self-review ห้ามเรียกว่าการตรวจอิสระ หากใช้หลาย agent ให้มีเจ้าของไฟล์ งานส่งต่อ และจุดรวมงานชัดเจน จำนวน agent ที่ร้องขอไม่ได้เพิ่มความสามารถในการทำงานพร้อมกันของเครื่องมือ

เมื่อแก้แล้วสองรอบยังผิดรูปแบบเดิม ให้ทบทวนวิธี: เปลี่ยน generator, เปลี่ยนฐานโมเดล, ใช้ modular modeling หรือ hand cleanup แทนการสุ่ม prompt ต่อ ไม่มีจำนวนรอบใดที่ทำให้ของที่ยังไม่ผ่านกลายเป็นผ่านได้

นำโครงงานจาก [Mr. Mak Workspace ที่ตรวจแล้ว](mr-mak-adoption-review-20261001.md) มาใช้เพิ่ม: แยก source snapshot ออกจาก layout proposal, เก็บ accepted/rejected take พร้อมเหตุผล, รักษา stable asset IDs และให้ review scene ใช้ production code path เดียวกับเกมจริง รายงานสวยหรือภาพทดลองแยกไม่ทดแทนผลจากเกม

## 6. Level Design: ด่านกระชับและรายละเอียดสูงเฉพาะจุด

แผนที่ต้องมีการเดินทางที่ผู้เล่นเข้าใจได้:

`จุดพัก/เข้าเมือง → ทางสำรวจ → ลานต่อสู้ A → ทางเชื่อมมีจังหวะ → ลานต่อสู้ B → จุดหมาย/รางวัล → ทางกลับ`

- เก็บสองลานมอนสเตอร์ ลดช่วงเดินว่าง ใช้ทางโค้ง เนิน หน้าผา พืช และประตูแบ่งมุมมอง
- ให้แต่ละลานมีเหตุผลด้านการเล่นที่ต่างกัน เช่น พื้นที่ฝึกอ่านท่า กับพื้นที่ใช้การเคลื่อนที่และเส้นทางหลบ
- มี optional discovery ที่มองเห็นเบาะแสได้ และมีเส้นทางกลับที่ไม่สับสน
- แลนด์มาร์กทุกจุดมีหน้าที่: บอกทิศทาง รับงาน พัก เตรียมตัว เปิดเส้นทาง ต่อสู้ หรือรับรางวัล
- ทุ่มรายละเอียดให้สิ่งที่อยู่ใกล้ตัวละคร บริเวณหยุดมอง ทางแยก และจุดต่อสู้; ฉากไกลใช้ silhouette และ LOD/HLOD
- เว้นพื้นที่โล่งให้การเคลื่อนไหวและ telegraph ใบไม้หรือของตกแต่งไม่บังเส้นทางและศัตรู
- เมืองมีศูนย์กลางและย่านที่แยกออก: ประตู คลอง/สะพาน ลานน้ำพุ ตลาด ร้านค้า ที่พัก และเส้นทางขึ้นปราสาท
- ไม่วางของแบบสุ่มทั่วพื้นที่ ใช้กฎตามเรื่องราว: สินค้าใกล้ร้าน คนใกล้บริการ น้ำและตะไคร่ตามความชื้น รอยเท้าตามทางเดิน
- จัดแนวสายตาจากระดับผู้เล่นก่อนมุมบิน ไม่ให้ความสวยของภาพรวมแลกกับการเดินชนผนังหรือหาเส้นทางไม่เจอ

**การตรวจทางเดินบังคับ:** เดินไป–กลับทุกเส้นทาง ขึ้น–ลงบันได ข้ามสะพาน เข้า–ออกประตู และวนรอบวัตถุที่ควรชน ตรวจทั้งขอบ จุดเริ่ม จุดสิ้น และรอยต่อชิ้นงาน

เมื่อมีปัญหาพื้นจม/บันไดขาด ให้ตรวจหน่วย จุดอ้างอิง transform ผิวรองรับ ระดับ landing และ collision ก่อน ปรับรูปทรงที่ผิด ไม่เพิ่ม step height จนผู้เล่นขึ้นกำแพงได้ ไม่ใส่พื้นชนล่องหนเหนือผิวน้ำเพื่อให้ test ผ่าน

หากยังไม่รองรับพื้นซ้อนหรือการกระโดด ให้ระบุขอบเขตของ movement ตามที่มีจริง ห้ามใช้ height query แบบเลือกพื้นสูงสุดแทนระบบหลายชั้นโดยไม่ทดสอบใต้สะพาน/ในอาคาร

## 7. ใช้ของฟรีและเครื่องมือที่พิสูจน์แล้วก่อน

เลือกจากคุณภาพที่เข้ากับงาน ไม่ใช่เพียงป้าย free หรือจำนวน downloads:

| ประเภทงาน | ทางเลือกเริ่มต้น | ต้องทำเพิ่มก่อนรับเข้าเกม |
|---|---|---|
| ต้นไม้/กิ่ง | Procedural Tree Generator, MTree, Geometry Nodes หรือชุดต้นไม้ที่มีสิทธิ์ใช้ | คุมรูปทรง ปรับใบ วัสดุ LOD ลม เงา และตรวจหลายมุม |
| หิน/พื้น/เปลือกไม้/ลาวา | วัสดุ PBR ที่เหมาะจาก ambientCG / Poly Haven | ปรับ palette/scale, ลดชุดแผนที่ที่ไม่ใช้, compression และตรวจรอยต่อ |
| อาคาร/บันได/สะพาน | ชุด modular ที่ดี หรือ Blender mesh ที่วัดขนาดได้ | จุด snap ช่องเปิด collision ทางเดิน และแสงในเกม |
| ของใช้ซ้ำ | ชุดที่มี provenance เช่นจาก Kenney/Quaternius/KayKit โดยตรวจแพ็กจริง | เลือกชิ้นที่เข้ากัน ปรับสเกล/วัสดุ และทำ variant จากฐานร่วม |
| ตัวละคร/สัตว์ | ฐาน rig ที่เหมาะ, Blender และ animation library ที่สิทธิ์ครบ | skin weights, จุดสัมผัส อาวุธและการเปลี่ยนท่า |
| Hero prop | ภาพออกแบบที่ชัด → Blender หรือ image-to-3D ที่เหมาะ | ตรวจด้านหลัง topology, UV, รายละเอียดและการใช้งานจริง |
| VFX | ความสามารถของ engine, material/particle editor, trail/ribbon, atlas/flipbook | ขอบเขต จำนวนพร้อมกัน การ pooling และเวลาที่ตรง gameplay |

ค้นหาเป็นรอบเล็ก เลือก 3–5 ตัวเลือกที่ตอบโจทย์ แล้วเปรียบเทียบ 1–2 ชิ้นในเกม ไม่ดาวน์โหลดคลังใหญ่เพียงเพื่อให้มี asset มาก การรับเข้าเกมใช้เฉพาะแพ็กที่มีสิทธิ์ชัดและหลักฐานคุณภาพ

### แหล่งที่ตรวจในวันที่จัดทำเอกสาร

- [ambientCG Lava001](https://ambientcg.com/view?id=Lava001) มีชุด PBR หลายความละเอียด และหน้าเว็บระบุ CC0 เลือกความละเอียดตามฉากจริง เก็บไว้สำหรับลาวาภายหลัง ไม่ให้การเตรียมวัสดุดึงงานออกจาก Sunmeadow
- [Poly Haven Fir Tree 01](https://polyhaven.com/a/fir_tree_01) เป็นแหล่งต้นไม้ที่มีรายละเอียด แต่หน้ารายการแสดง source ระดับประมาณ 8 ล้าน triangles ต้องตรวจ variant และทำแพ็ก runtime ก่อนใช้งาน สิทธิ์ asset ของเว็บอธิบายแยกใน [Poly Haven License](https://polyhaven.com/license)
- [Modular Tree บน Blender Extensions](https://extensions.blender.org/add-ons/modular-tree/) เป็น maintained fork มีระบบ node สำหรับกิ่งและใบ [ประวัติรุ่น](https://extensions.blender.org/add-ons/modular-tree/versions/) ระบุรุ่น 5.5.2, GPL-3.0-or-later และ compatibility ของรุ่น ต้องทดสอบกับ Blender ที่ใช้อยู่จริง; Pivot Painter export ไม่ได้แปลว่าลมจะทำงานใน Babylon โดยอัตโนมัติ

ข้อมูลเหล่านี้เป็นการตรวจแหล่งต้นทาง ไม่ใช่การติดตั้ง ดาวน์โหลดหรือรับ asset ใหม่ทุกตัวเข้าเกมในการจัดทำเอกสารนี้

## 8. มาตรฐานต้นไม้และธรรมชาติ

สำหรับงานสร้างซ้ำและตรวจ asset ให้ใช้ [Blender Python workflow](blender-python-tripo-workflow.md) ประกอบ: ให้ Python คุม spec, seed, generator, export และการตรวจ โดยคงการตัดสินรูปทรง/วัสดุจากภาพจริง กฎนี้ไม่ได้บังคับให้เขียนระบบต้นไม้หรือปั้นรายละเอียดทุกชิ้นเอง

ใช้ระบบสร้างกิ่งที่มีอยู่ก่อนงานเขียน generator ใหม่ แนวคิด procedural มีหลายวิธี เช่น L-systems และแบบจำลองรูปทรงพุ่ม ไม่ใช่สูตรเดียวที่ทำให้ต้นไม้ทุกชนิดสวยเอง งานวิจัยพื้นฐานอ่านได้จาก [Algorithmic Botany](https://algorithmicbotany.org/papers/)

สิ่งที่ต้องคุมหลัง generation:

- ลำต้นมี taper, root flare และรอยต่อกิ่งที่น่าเชื่อถือ แยกกิ่งหลัก–รอง–กิ่งปลาย
- Crown มีโครงสร้างและช่องว่าง เห็นการซ้อนชั้นและแสงลอดได้ตามพันธุ์ไม้
- ใบมีขนาด ทิศทาง ความหนาแน่น และเงาร่างสัมพันธ์กับชนิดต้นไม้ ใช้ leaf/twig cards หรือ cluster meshes อย่างมีเหตุผล ไม่ต้องปั้นใบทุกใบด้วยมือ
- พุ่มไม่กลายเป็นลูกบอลทึบ จานกลม หรือก้อนพับ ถ้าต้นแบบมีใบและกิ่งที่อ่านออก
- เปลือกไม้ไม่ยืด รอยต่อ UV ไม่เด่น โคนต้นแตะพื้นและมีวัสดุ/พืชรองรับ
- ลมมีลำดับ: ลำต้นคงฐาน กิ่งหลักแกว่งช้า กิ่งปลายและใบตอบสนองเล็กกว่า/เร็วกว่า มี phase ต่างกัน
- เงาและขอบเขต culling ต้องรองรับการเคลื่อนไหว ไม่เห็นเงานิ่งใต้ต้นที่กำลังแกว่ง หรือใบหายเมื่อแกว่งพ้น bounds
- ตรวจใบด้านหลัง alpha fringe, mipmap และ overdraw ทั้งตอนนิ่งและตอนแพนกล้อง
- ภูเขาและป่าไกลใช้รายละเอียดลดลง แต่ยังรักษารูปทรง สี และระดับหมอกที่สอดคล้องกับของใกล้

ต้นไม้หนึ่งชนิดที่ผ่านทุกมุมมีค่ากว่าต้นไม้หลายสิบแบบที่ผิดรูปแบบเดียวกัน ล็อกต้นตัวอย่างหนึ่งต้นก่อนทำชุด variant

## 9. โมเดล วัสดุ และรายละเอียด

**Geometry:** สเกลเป็นเมตร, pivot มีเหตุผล, normals ถูก, ไม่มีผิวซ้อนจนกระพริบ, ช่องประตู/หน้าต่างเป็นช่องที่อ่านออก, UV และ topology รองรับการใช้งาน ตรวจจำนวน triangles หลัง export ไม่ใช้จำนวน quads จากผู้ให้บริการแทน

**Architecture:** กรอบหน้าต่างต้องหันตามผนังทั้งด้านหน้า/ข้าง sill ไม่ทะลุผนัง บันได landing และชานต่อถึงกัน ชายคามีความหนา และฐานอาคารไม่ลอย/จมจนเสียหน้าที่

**Materials:** แยกหิน ไม้ ผ้า โลหะ ใบไม้และน้ำด้วย response ต่อแสง ไม่ใช่เปลี่ยนสีอย่างเดียว ตรวจ color space ของ color/data maps, normal orientation, ORM channels, roughness และ alpha ใช้ trim/atlas ร่วมเมื่อเหมาะ

**Detail:** รูปทรงหลัก → ชิ้นส่วนที่มีหน้าที่ → ร่องและขอบ → คราบ/รอยเล็ก รายละเอียดเล็กที่ไม่กระทบ silhouette ควรอยู่ในวัสดุหรือ bake มากกว่าเพิ่ม mesh จำนวนมาก เก็บความละเอียด source ไว้ แต่ส่ง runtime เท่าที่กล้องเห็นประโยชน์

**AI mesh:** ตรวจด้านหลัง ด้านล่าง รอยเชื่อม ชิ้นส่วนหลอมรวม ตัวอักษรผิด มือ/นิ้วผิด และรายละเอียดที่หายไป การเขียนว่า game-ready ในชื่อเครื่องมือไม่ข้ามการตรวจนี้

## 10. ภาพ concept → 3D: ใช้เมื่อมีข้อได้เปรียบจริง

Tripo DCC Bridge ใช้เป็นทางรับโมเดลเข้า Blender ได้เมื่อเชื่อมต่อและตรวจแล้ว ก่อนใช้ให้อ่าน [ข้อกำหนด Bridge และ intake checks](blender-python-tripo-workflow.md#2-tripo-dcc-bridge-%E0%B8%82%E0%B9%89%E0%B8%AD%E0%B8%A1%E0%B8%B9%E0%B8%A5%E0%B8%97%E0%B8%B5%E0%B9%88%E0%B8%A2%E0%B8%B7%E0%B8%99%E0%B8%A2%E0%B8%B1%E0%B8%99%E0%B8%88%E0%B8%B2%E0%B8%81%E0%B8%95%E0%B9%89%E0%B8%99%E0%B8%97%E0%B8%B2%E0%B8%87) โดยเฉพาะ receiver, pivot, vertex colors, UV และขนาด texture การปรับเอกสารนี้ยังไม่ได้ติดตั้งหรือทดสอบ Bridge

แยกภาพสองประเภท:

1. **ภาพทิศทางฉาก:** แสดงองค์ประกอบ แสง สเกล จุดสนใจและเส้นทาง ใช้ตัดสินใจงานภาพ ไม่ส่งทั้งเมืองที่ซับซ้อนให้ image-to-3D แล้วคาดหวัง topology/collision ที่ถูกต้อง
2. **ภาพสร้าง asset:** หนึ่งวัตถุครบชิ้น มุมหน้าเฉียง แสงเป็นกลาง พื้นหลังเรียบ เห็นความหนาและช่องเปิด ไม่มีกล้องที่บิดสัดส่วนหรือวัตถุซ้อนบัง

ใช้ภาพหลายด้านได้เมื่อ workflow รองรับ แต่ต้องตรวจว่าแต่ละด้านเป็นวัตถุเดียวกันจริง จำนวนชิ้นและตำแหน่งรอยต่อห้ามเปลี่ยนข้ามภาพ ให้ข้อมูลขนาดเป็นตัวกำกับอีกชั้น

### image-to-3dlab / Pixel Match

[ผู้พัฒนาอธิบาย Pixel Match](https://github.com/Bingeljell/image-to-3dlab) ว่าใช้พิกเซลต้นฉบับกลับลงบนผิวที่ภาพมองเห็น จึงเป็นตัวเลือกทดลองสำหรับ texture projection ไม่ใช่หลักฐานว่ารูปทรง ด้านที่มองไม่เห็น UV ทุกจุด หรือ deformation จะถูกต้องเอง ตรวจ backend, camera alignment, licence และ hardware ของรุ่นที่ใช้ก่อน

งานตรวจในโครงการมีข้อจำกัดจาก fixture ของตัวเอง อ่าน [ผลตรวจ local AI tools](local-ai-asset-tools-20261001.md) ก่อนอ้างว่า pixel-perfect กับ asset ใด ๆ ตัวอักษร/สัญลักษณ์สำคัญควรเก็บ source และ decal ที่แก้ได้ ไม่ผูกกับผล generate เพียงอย่างเดียว

### UniMate

[UniMate](https://github.com/Friedrich-M/UniMate) เป็นทางเลือกสร้าง motion สำหรับ rig ที่มีอยู่ มีทางส่งออก animated GLB/FBX ผ่าน pipeline ของโครงการต้นทาง หน้า README ที่ตรวจยังระบุว่างานเตรียม rig ใหม่บางส่วนกำลังจะเผยแพร่ โค้ด MIT ไม่ได้ทำให้ dataset ทุกชุดมีสิทธิ์เดียวกัน

ทดลองกับตัวละครหนึ่งตัวและคลิปหนึ่งชุดก่อน ตรวจ skeleton mapping, timing, feet, weapon grip และผล reimport ตาม [asset motion workflow](asset-motion-trial-workflow.md) ไม่เปลี่ยน pipeline ที่ทำงานอยู่เพียงเพราะมีเครื่องมือใหม่

ข้อมูล GPU ในรายงานเก่าเป็นเพียง checkpoint ต้องตรวจเครื่องปัจจุบันอีกครั้งก่อน inference หรือดาวน์โหลด weights ไม่ตีความ “ทำบนเครื่องฟรี” ว่าเครื่องนี้มีหน่วยความจำเพียงพอแน่นอน

## 11. Rig และแอนิเมชัน

- เลือก humanoid rig ร่วมเมื่อสัดส่วนเหมาะ; สัตว์หรือบอสใช้โครงกระดูกตามกายวิภาคจริง
- มีการควบคุมส่วนที่จำเป็น เช่น มือ อาวุธ ชายผ้า หาง ปีก เครา แต่ไม่เพิ่ม bone โดยไร้ประโยชน์จากกล้อง
- น้ำหนักผิวต้อง normalized และอยู่ภายในขอบเขต pipeline ตรวจสิ่งแนบแข็งแยกจากส่วนที่ควรยืด
- ตรวจ idle, walk/run, turn, anticipation, attack, recovery, hit และ death ตามบทบาทของตัวนั้น NPC ไม่จำเป็นต้องเล่นทุกท่าต่อสู้ในเมือง
- ตรวจ foot sliding, มือหลุดอาวุธ, เสื้อยืด, หางทะลุลำตัว และการเปลี่ยนท่าที่กระตุก
- ตรวจอาวุธตลอดช่วง swing ไม่ใช้เพียงภาพเริ่ม/จบ; ท่าล้มต้องสัมผัสพื้นและไม่ค้างลอย
- ใช้ in-place motion เมื่อ server เป็นเจ้าของการเคลื่อนที่ หากเลือก root motion ต้องมีสัญญากับ gameplay ที่ชัดเจน
- เวลาปะทะ/telegraph ต้องมาจาก contract เดียวกับระบบต่อสู้; อย่าเร่งคลิปเพื่อปิดช่องว่างของ state machine
- Reimport ไฟล์ที่ส่งจริงและเล่นทุกคลิป ไม่มีการถือว่า .blend เล่นได้จึงหมายความว่า GLB ใช้ได้

เพิ่มจาก workflow ที่ตรวจ: บันทึกช่วงคลิปและ fps โดย `duration = (last_frame - first_frame) / fps`; เปลี่ยน fps ด้วยการ resample ไม่ใช่เปลี่ยนป้ายกำกับอย่างเดียว แยก controller yaw ออกจากการหมุนในคลิปเพื่อป้องกันหมุนซ้ำ และตรวจ gait phase/เท้าที่รับน้ำหนักเมื่อเลิกเลี้ยวกลางท่าแล้วเข้าสู่ Walk/Run พร้อมตรวจไฟล์ authoring หลัง save/reopen

## 12. แสง กล้อง และการ render

ล็อกกล้องใช้งานก่อนเก็บรายละเอียด แสงหลัก แสงเติมจากท้องฟ้า exposure, tone mapping, หมอกและ bloom ต้องทำงานเป็นชุดเดียว

**ชุดช็อตตรวจ:** กลางวันเป็นกลาง, แสงอุ่นช่วงเย็น, กลางคืน และสภาพเปียก/ฝนที่เกมรองรับจริง รักษาจุดยืนและกล้องเดียวกันเมื่อเทียบ revision

- หิน ไม้ ผ้า และใบไม้ต้องยังมีเนื้อวัสดุทั้งในแสงและเงา
- หน้าต่าง โคมไฟ คริสตัล และ portal รักษาสี/รูปทรงภายใน ไม่กลายเป็นก้อนขาวเพราะ emissive/bloom
- เงาสัมผัสทำให้วัตถุติดพื้น; เงานุ่มหรือแข็งมีเหตุผลตามขนาด/ทิศของแสง
- หมอกสร้างระยะ ไม่ล้างฉากทั้งหมดจนแบน ไม่ซ่อนข้อบกพร่องด้วยความมืดหรือ blur
- ตำแหน่งดวงอาทิตย์ แสงที่ส่องวัตถุและเงาต้องสัมพันธ์กัน การปรับเชิงศิลป์ต้องมีเหตุผลและไม่ทำให้ภาพขัดกัน
- ตัวละครและ telegraph อ่านออกใน grayscale และฉากหลังหลายแบบ
- แสงกลางวัน/กลางคืนเปลี่ยนจาก clock ร่วม; ห้ามมีหลายระบบเปลี่ยนค่าเดียวกันจนสั่นหรือสลับสี
- ตรวจ WebGPU และ WebGL2 แยกกัน หาก renderer หนึ่งว่าง/หาย/ผิดสี ให้บันทึกว่าไม่ผ่านหรือยังพิสูจน์ไม่ได้ อย่าใช้ภาพจากอีก renderer อ้างแทน

สิ่งที่ศึกษาได้จาก reference ในเครื่อง: `summer-cycle` จัด preset ท้องฟ้า หมอก เงาและ grading ร่วมกัน; `shinobi-duel` ใช้แสงขอบและหมอกช่วยแยกตัวละครจากฉาก ทั้งคู่เป็นตัวอย่างวิธีคิด ต้องประเมินวิธีนำมาใช้กับ engine และกลุ่มอุปกรณ์ของเรา

## 13. VFX น้ำ และเอฟเฟกต์การต่อสู้

VFX ต้องบอกเหตุการณ์และทิศทางก่อนตกแต่ง มีจังหวะเตรียม → เกิดผล → สลาย และมีขอบเขตอายุ/จำนวนพร้อมกัน

| ระบบ | เกณฑ์คุณภาพ |
|---|---|
| Slash / trail | ติด socket และแนวอาวุธจริง ribbon แคบ–กว้างตามจังหวะ ไม่ตัดขาด ไม่ค้าง ไม่บังศัตรู/telegraph |
| Hit / magic | ปะทะตรงตำแหน่งที่ยืนยัน มีชั้น core/เส้น/เศษเท่าที่จำเป็น สีและแสงยังอ่านออกเมื่อซ้อนกัน |
| Fountain | น้ำเริ่มจากหัวจ่าย/ขอบที่มีจริง ลงอ่างถูกระดับ มี normal motion, highlight, จุดกระทบ/ripples และการไหลต่อระหว่างชั้น |
| River / waterfall | ทิศการไหลตามรูปทรง มีขอบน้ำและโฟมตามจุดกระทบ ปลายสายน้ำไม่ลอย ไม่เห็นรอยต่อ texture เด่น |
| Fire / smoke | มีที่มา ลอย/ลอยตัวและจางตามเหตุผล ไม่ให้ควันบดบังการเล่นตลอดเวลา |
| Weather | ความเข้มฝน ลม น้ำและเมฆสัมพันธ์กัน ลดความหนาแน่นได้โดยคงข้อมูลการต่อสู้ |

น้ำใช้ geometry, shader normals, flow, Fresnel และ reflection ตามงบที่วัดได้ ภาพ normal/foam/flipbook เป็นส่วนหนึ่งของระบบได้ แต่ภาพผิวน้ำนิ่งเพียงแผ่นเดียวไม่พอสำหรับคุณภาพที่ผู้ใช้ต้องการ และไม่จำเป็นต้องใช้ fluid simulation เต็มรูปแบบถ้าไม่มีการโต้ตอบที่ต้องใช้

ใช้ native engine particle/trail/material capabilities และ pooling ก่อนเขียนระบบใหม่ หลีกเลี่ยงไฟหนึ่งดวงต่อประกายหรือ reflection pass ต่อแอ่ง ทดสอบช่วงเอฟเฟกต์ซ้อนหนักที่สุดพร้อมศัตรูและ UI; ปรับลดของตกแต่งก่อนลด telegraph ที่จำเป็น

กรณี lifecycle ที่ต้องทดสอบเมื่อเกี่ยวข้อง: ยกเลิก windup แล้วไม่มี impact ตามมา, เป้าหมายเคลื่อนหลัง release แล้ว travel ยังตรงระบบจริง, refresh status ไม่ซ้อน emitter เกินเจตนา, เจ้าของตาย/despawn แล้วจบถูกต้อง และ teleport/pool reuse ไม่ลาก trail จากตำแหน่งเก่า แยก local socket space กับ world space; การย้าย emitter ไม่ควรย้ายควันเก่าทั้งก้อนตามไปด้วย

## 14. คุณภาพด้านระบบและ UI

ภาพสวยต้องเป็นส่วนของเกมที่ทำงานได้:

- Server เป็นเจ้าของการเคลื่อนที่ที่มีผลจริง การโจมตี HP สินค้า เงิน และรางวัล Client แสดงผล/ทำนายภายใต้ข้อจำกัดเดียวกัน
- Render geometry, ground query, collider และ navigation มาจาก source/coordinate contract เดียวกัน การเปลี่ยน layout ต้องเปลี่ยน POI, spawn, quest approach และข้อมูลชนที่เกี่ยวข้องด้วย
- ทดสอบ retry, reconnect, duplicate operation และข้อความผิดลำดับในระบบที่ได้รับผล ไม่ให้กดซ้ำแล้วได้รางวัลซ้ำ
- NPC เข้าถึงได้ มีชื่อ ตำแหน่งและบทสนทนาตรงข้อมูล การคุยกับ NPC ทั่วไปไม่เปิดช่องรับเควสต์/รางวัลของอีกตัว
- เมือง/ทุ่งใช้การโหลดล่วงหน้าตามความเหมาะสม; dungeon/instance มี preparation, loading, spawn confirmation และทางคืนตัวเมื่อโหลดล้มเหลว
- Svelte/HTML รับข้อมูลธรรมดาที่ตรวจแล้ว ไม่เก็บ Scene/Mesh ใน reactive state แสดงภาษาไทยและรองรับเมาส์/คีย์บอร์ด/สัมผัส
- UI อัปเดตเมื่อข้อมูลเปลี่ยน นาฬิกาคูลดาวน์มีข้อตกลง clock ที่ตรงกัน ไม่ส่งความคืบหน้าทุกเฟรมจาก server
- Minimap แสดงผัง/POI/ผู้เล่นจากข้อมูลจริง กรอบมุมมนเป็นส่วนงาน UI; texture แผนที่ที่ bake จากโลกจริงใช้ได้เมื่อพิกัดตรง ไม่วาดอาคารหรือทางหลอกเพื่อให้ดูแน่น
- หน้าจอมือถือไม่ทับ joystick ปุ่มสกิล interaction หรือข้อความสำคัญ ตรวจจอแนวนอนเตี้ย safe area และข้อความยาว
- เมนูที่ยังไม่มีระบบจริงต้องสื่อสถานะตามจริง ไม่ใช้ภาพ UI ทำให้ดูเหมือนระบบเสร็จแล้ว

## 15. Performance: วัดภาระที่เกิดพร้อมกัน

สามเรื่องนี้แยกกัน:

- ย่อสเกลโมเดลไม่ได้ลดจำนวนหน้าโดยตัวมันเอง
- ลดไฟล์ช่วยการดาวน์โหลด/cache แต่ยังมี decode, shader compile, GPU upload และ resident memory
- FPS ขึ้นกับงานที่ทำพร้อมกัน เช่น draw submissions, visible geometry, skinning, transparency, shadows, particles, CPU logic และความละเอียดภาพ

ใช้รายละเอียดใกล้ผู้เล่น, material sharing, instancing, culling, LOD/HLOD, streaming และอายุทรัพยากรที่ชัดเจน ทดสอบ impostor กับ mesh LOD ก่อนเลือก; impostor อาจเพิ่ม alpha overdraw หรือ texture cost ไม่ควรแทนวัตถุใกล้ที่ต้องดูรอบได้

แยก source ที่ละเอียดออกจาก runtime ใช้ GLB/mesh compression และ KTX2 เมื่อเหมาะ ตรวจหลัง compression ว่าสี normals alpha และแอนิเมชันยังถูก การสุ่มโลกหรือสร้าง mesh หนักควรทำตอน authoring หรือในงานเบื้องหลังที่มีขอบเขต ไม่ทำซ้ำหนักบน main thread ระหว่างเล่น

**ตั้งงบก่อนแต่ละ slice:** ให้ระบุ device, renderer, resolution, quality preset, เส้นทางและสถานการณ์ทดสอบ เลือกเป้าหมายจากเอกสารอุปกรณ์ปัจจุบัน ไม่ปะปนตัวเลขจากแผนหลายรุ่น ตัวอย่างเป้าหมายเริ่มต้นคือ 30fps/33.3ms บนมือถือฐานและ 60fps/16.7ms บน PC ที่ระบุรุ่น; ยังไม่ถือว่าผ่านจนวัดจริง

เก็บอย่างน้อย frame-time p50/p95/p99, ช่วงสะดุดที่ผู้เล่นเห็น, cold/warm load, bytes ต่อแพ็ก, texture residency ที่วัดหรือประมาณพร้อมวิธี, mesh/material/particle counts และ memory หลังเข้า–ออกพื้นที่หลายรอบ บันทึก idle/เดิน/ต่อสู้/มุมหนักแยกกัน การย่อ viewport บน PC ไม่ใช่การทดสอบ iPhone

Low/Medium/High/Ultra คงเส้นทาง collision NPC และข้อมูลต่อสู้เดียวกัน เปลี่ยนคุณภาพการแสดงผลเป็นหลัก 500 คนต่อแมพและ 10,000 CCU ทั้งระบบเป็นการทดสอบคนละระดับและยังต้องมีหลักฐานของตัวเอง

## 16. เกณฑ์ผ่านที่ตรวจย้อนหลังได้

งานต้องมีสถานะด้านต่อไปนี้แยกกัน: `technical`, `visual`, `gameplay`, `device` แต่ละด้านใช้ `PASS`, `FAIL`, `UNVERIFIED`, หรือ `N/A` พร้อมเหตุผล ไม่ใช้ค่าเฉลี่ยข้ามด้าน

| Gate | หลักฐานขั้นต่ำ | เงื่อนไขที่ต้องตีกลับ |
|---|---|---|
| G0 — Brief / source | ภาพเป้าหมาย สัดส่วน กล้อง สิทธิ์/ที่มาและงบ | ไม่รู้สิ่งที่ต้องตรง หรือเลือก source ที่ยังนำมาใช้ไม่ได้ |
| G1 — Playable blockout | เดิน route ไป–กลับ กล้อง/ช่องเปิด/บันได/collider | ทางตันผิดเจตนา พื้นจม วัตถุที่ต้องชนเดินทะลุได้ |
| G2 — Asset craft | หน้า/ข้าง/หลัง/ใกล้ เทียบ source; UV/material/rig | รูปทรงผิด ชิ้นส่วนหลอมรวม มือ/ใบไม้ผิดชนิด ข้อต่อยืด |
| G3 — Integrated art | ภาพและคลิป Babylon มุมผู้เล่น มีตัวละครและแสงจริง | ดูดีเฉพาะ Blender, emissive ขาวล้น, ไม่เข้าชุดกับฉาก |
| G4 — Gameplay/system | interaction/combat/reward/reconnect ตาม scope | ข้อมูลแสดงผลไม่ตรงผลจริง, reward ซ้ำ, movement ไม่ตรงกัน |
| G5 — Device/delivery | อุปกรณ์และ build ระบุชัด เส้นทางวัดซ้ำได้ | เกินงบที่กำหนด, โหลดสะดุด/ทรัพยากรสะสม, ใช้ FPS ภาพเดียวอ้างผล |
| G6 — Acceptance | รายการแก้ครบ ภาพ/คลิป และการยอมรับตาม scope | ผู้ใช้ยังระบุว่าไม่เหมือน/ไม่สวย หรือมีข้อบกพร่องสำคัญค้าง |

สถานะ “ต้นแบบ”, “technical pass”, “art candidate”, “เล่นได้ตาม scope” และ “พร้อมใช้งานตาม device gate” ต้องใช้ตามหลักฐาน ไม่เรียกทุกอย่างว่าเสร็จ

### Rubric ภายในสำหรับคัด art candidate

คะแนนนี้เป็นกติกาการตรวจที่เสนอในเอกสาร ไม่ใช่คะแนนจากผู้ใช้ ไม่ใช่มาตรฐานรับรอง AAA และไม่ยกเลิกข้อบกพร่องบังคับแก้

| ด้าน | น้ำหนัก |
|---|---:|
| องค์ประกอบและความตรง reference | 20 |
| สัดส่วน/เงาร่าง/การประกอบ | 15 |
| วัสดุ/UV/รายละเอียดที่มีเหตุผล | 15 |
| แสง/เงา/สี/ความลึก | 15 |
| การเคลื่อนไหวและ VFX | 10 |
| การแต่งฉากและรอยต่อสิ่งแวดล้อม | 10 |
| ความชัดเจนจากกล้องผู้เล่น/UI | 10 |
| ความสม่ำเสมอของสไตล์ | 5 |
| **รวม** | **100** |

ให้แต่ละด้าน 0–5 พร้อมหลักฐาน; คะแนนรวม = ผลรวม `(น้ำหนัก × คะแนน / 5)` รับเป็น candidate ที่แข็งแรงเมื่อ ≥85/100, ทุกด้านที่เกี่ยวข้อง ≥4/5 และไม่มี blocker หากด้านใด N/A ให้ประกาศน้ำหนักใหม่ก่อน review ห้ามเพิ่มคะแนนโดยเงียบ ๆ ผู้ใช้เป็นผู้ตัดสินความพอใจสุดท้าย

**Blocker ที่คะแนนชดเชยไม่ได้:** ทางเดิน/บันไดเสีย, เดินทะลุของที่ควรชน, ไม่มีภาพเกมจริง, ตัวละครหาย/ยืดหนัก, telegraph อ่านไม่ได้, shader ผิด, ต้นแบบหลักผิดรูปชัดเจน หรือสิทธิ์ asset ไม่เพียงพอสำหรับวิธีใช้นั้น

## 17. รูปแบบหลักฐานและการแก้ซ้ำ

ต่อหนึ่ง revision ต้องเก็บ source/master, runtime, material/collision/clip metadata และ hash ที่สัมพันธ์กัน โดยใช้ตำแหน่งแพ็ก/หลักฐานเดิมของโครงการเมื่อมี ไม่สร้างระบบจัดเก็บใหม่ซ้ำซ้อน

ภาพเปรียบเทียบขั้นต่ำ: player/front, side, close, elevated พร้อม before/after ที่ lock camera/light/preset เหมือนกัน เพิ่มคลิปเมื่อคุณภาพขึ้นกับเวลา เช่น ลม น้ำ การโจมตี LOD หรือการโหลดพื้นที่ ระบุ reference เป็นคนละช่องชัดเจน

ตัวอย่าง review record:

```yaml
asset_or_region: sunmeadow_fountain
revision: candidate_03
scope: upper jets and two receiving basins
reference: docs/ui/city-layout-target-20260928.png
build_and_asset_hashes: REQUIRED
camera_light_preset_device: REQUIRED
technical: PASS_or_FAIL_or_UNVERIFIED
visual: PASS_or_FAIL_or_UNVERIFIED
gameplay: PASS_or_FAIL_or_UNVERIFIED_or_NA_with_reason
device: PASS_or_FAIL_or_UNVERIFIED
evidence: [player_capture, side_capture, close_capture, motion_clip]
defects:
  - severity: major
    location: upper_bowl_outlets
    observation: describe what is visibly wrong
    cause_hypothesis: distinguish hypothesis from measured fact
    repair: concrete change
    retest: exact view_or_route
decision: repair_or_next_gate_or_scope_accepted
```

ทำ triage จาก defect ที่มองเห็น/ทำซ้ำได้ เลือกแก้ 3–5 ข้อสำคัญต่อรอบแล้วตรวจใหม่ อย่าแค่เพิ่มตัวเลข detail หรือ noise และใช้ภาพหลังแก้ที่เปลี่ยนกล้องจนเทียบไม่ได้ หากทดสอบไม่ได้ให้บันทึกสิ่งที่ขาดและรักษางานเป็น candidate

## 18. Prompt templates ที่ใช้ต่อได้

### A. Brief สำหรับภาพทิศทางฉาก

```text
Create an original Xexoria fantasy MMO environment concept for [LOCATION].
Use the approved shared palette and construction language: warm stone,
dark timber, blue roof accents, grounded material scale and restrained magic.
Player experience: [ARRIVAL -> EXPLORATION -> ENCOUNTER -> DISCOVERY -> RETURN].
Show [CAMERA HEIGHT / FOV / DIRECTION] with a [HEIGHT]-metre character for scale.
Preserve these landmark positions and traversable connections: [LIST].
Use a clear foreground, middle distance and background, with one primary focal
point. Reserve readable combat space and purposeful quiet areas. Concentrate
fine detail at [FOCAL LOCATIONS]. Light the scene with [KEY/FILL/TIME], retaining
material detail in highlights and shadows. No arbitrary clutter or blown-out
glowing windows. This is a concept target, not a claim of playable geometry.
```

### B. Brief สำหรับภาพ prop → 3D

```text
Create ONE isolated original game-prop reconstruction reference.
PROP / GAMEPLAY PURPOSE: [VALUE]
DIMENSIONS IN METRES: [VALUE]
CONSTRUCTION: [MAIN SHAPES, EXACT COUNTS, JOINTS, THICKNESS, OPENINGS]
MATERIALS: [TWO OR THREE MATERIALS, COLOURS, ROUGHNESS CHARACTER]
SHARED ART DIRECTION: [UNCHANGED APPROVED BLOCK]
Show one complete object in a front three-quarter view, a little top visible,
minimal perspective distortion, approximately 80% image coverage and clear margins.
Use neutral diffuse lighting and a plain light-gray background. Keep silhouette,
functional openings and material boundaries clear. Fine grain and shallow wear
belong in material detail. No environment, text, watermark, pedestal, collage,
dramatic bloom, depth of field or hidden/cropped components.
This image does not guarantee topology, UVs, material slots, rigging or performance.
```

### C. งานส่งต่อจาก Concept ไป Builder

```text
Read llm.txt and docs/production-quality-standard.md.
Implement only [ASSET/REGION SCOPE] from [REFERENCE + BREAKDOWN].
First compare suitable existing/free assets and mature tools with manual creation.
Preserve [DIMENSIONS / CONNECTIONS / MATERIAL FAMILY / GAMEPLAY CONTRACT].
Own only [FILES]; do not overwrite another worker's files or canonical source.
Build an editable candidate and the actual engine export. Capture player, side,
close and elevated views; add motion and traversal evidence where applicable.
Return measured defects and technical/visual/gameplay/device verdicts separately.
Fix the strongest defects and repeat the same comparison. No success claim from
file creation, screenshots of a different build, high polycount or tests alone.
```

### D. งานตรวจจากภาพในเกม

```text
Judge the actual supplied runtime captures against [REFERENCE/BREAKDOWN].
Identify the five most consequential differences. For each, record the image
location, observable defect, suspected cause, concrete repair and retest view.
Evaluate silhouette, scale, construction, material response, lighting, motion,
composition and player readability. Treat missing evidence as UNVERIFIED.
Do not invent what is outside the images, and do not treat a visual inspection
as proof of collision, networking, GPU memory or phone performance.
```

## 19. บทเรียนจาก `Downloads/warz`

ตรวจแบบอ่านอย่างเดียวจาก `%USERPROFILE%/Downloads/warz` ในวันที่จัดทำ (ย้ายไป `%USERPROFILE%/Downloads/Xexoria-Game/references/warz` เมื่อ 2026-10-02): พบโฟลเดอร์ Water, Grass, Shaders, TerrainData, Prefabs, ObjectsDepot, SkyDome และ Decals รวมถึงไฟล์ DDS, mesh, material และ physics หลายประเภท

ตัวอย่างที่อ่านจริง: `Prefabs/X_Settlement_Sml_01.xml` ผูก asset กับ position/rotation และ flag เช่น `PhysEnable` / `MinQuality`; ใน Water มี `waves_01.dds` ถึงชุดลำดับคลื่น, `Foam01.dds`, `LakeMask.dds`, normal/gloss และ ripples; Shaders มีชุดสำหรับหญ้าและท้องฟ้า

บทเรียนที่นำมาออกแบบเองได้: แยก source/runtime, ทำ prefab ที่มีตำแหน่งและข้อมูลชน, แยกชุด texture ตามหน้าที่ และปรับคุณภาพตามอุปกรณ์ การพบชื่อไฟล์เป็นเพียง inventory ไม่ใช่การตรวจ shader ทั้งระบบ และไม่ใช่หลักฐานว่าไฟล์เก่าแปลงเข้า Babylon แล้วใช้ได้ทันที

ยังไม่พบหลักฐาน licence ที่ยืนยันสิทธิ์ใช้ในส่วนที่ตรวจ อย่ารวม texture/mesh/shader จากคลังนี้ลงเกมเพียงเพราะอยู่ในเครื่อง ให้ใช้ศึกษาโครงสร้างก่อนจนทราบสิทธิ์ของชิ้นที่จะนำมาใช้

## 20. เอกสารประกอบและวิธีเริ่มงานรอบถัดไป

- [Delivery and asset playbook](delivery-and-asset-playbook.md)
- [City art roadmap](city-art-roadmap.md) และ [ภาพเป้าหมายเมือง](ui/xexoria-town-art-target-20261001.png)
- [Region loading / dungeons](region-loading-and-dungeons.md)
- [Compact Sunmeadow proposal](sunmeadow-compact-layout.md)
- [UI runtime architecture](ui-runtime-architecture.md)
- [LOD / texture research](reviews/2026-09-30-assets-lod-texture-research.md)
- [Local AI tool audit](local-ai-asset-tools-20261001.md) และ [motion trial](asset-motion-trial-workflow.md)
- [Mr. Mak adoption review](mr-mak-adoption-review-20261001.md) — clone pin, workflow ที่เลือกใช้ และส่วนที่ต้องดัดแปลง
- [Blender Python + Tripo workflow](blender-python-tripo-workflow.md) — recipe contract, staged modeling, intake และ Reddit research ที่แยกจากหลักฐานทางการ
- [Harness + GPT + Jev + CUA/DOM](harness-jev-gpt-toolchain.md) — mandatory routing, context carryover และหลักฐานการใช้เครื่องมือ
- [Ragnarok research](../references/ro-research/ragnarok-complete-research.md)

แผนเก่าบางส่วนพูดถึงโลกที่กว้างมาก บางส่วนจำกัดการเดินไว้ที่พื้นราบ และตัวเลขงบต่างรุ่นไม่เหมือนกัน อ่านวันที่และขอบเขต แล้วตรวจ code/asset ปัจจุบันก่อนตัดสินใจ เอกสารใหม่นี้กำหนดคุณภาพและวิธีรับงาน ไม่ยืนยันว่าปัญหาทางเดินหรือ renderer ในงานที่กำลังทำถูกแก้แล้ว

เริ่มรอบถัดไปด้วยหนึ่ง slice ที่ชัด เช่น **ทางเข้าเมือง → ลานน้ำพุ → NPC → บันได/ชาน → ทางกลับ** ถ่าย baseline จัด defect ตามความสำคัญ แก้รูปทรงและระบบให้เดินได้ก่อน เก็บแสง วัสดุ น้ำและพืชในบริเวณเดียวกัน แล้วตรวจทุก gate ที่เกี่ยวข้อง ใช้ slice ที่ผ่านเป็นตัวอย่างคุณภาพสำหรับเมืองและด่านอื่นต่อไป
