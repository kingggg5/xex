/** A paid failed refinement is a committed outcome, not a loot grant. */
export function refinementNotice(status,reason,language='en'){
 if(status!=='accepted')return null;
 if(reason==='refine_failed')return language==='th'?'ตีบวกไม่สำเร็จ ตรวจระดับอุปกรณ์และทองที่อัปเดตแล้ว':'Refinement failed. Equipment level and gold have been updated.';
 if(reason==='refine_success')return language==='th'?'ตีบวกสำเร็จ ตรวจอุปกรณ์ที่อัปเดตแล้ว':'Refinement succeeded. Your equipment has been updated.';
 return null;
}
