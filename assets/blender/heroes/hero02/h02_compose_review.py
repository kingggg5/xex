"""Compose labelled evidence sheets; retains source frames unchanged apart from uniform scaling."""
import json,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[4];EV=ROOT/'planning/evidence/hero02-witch-20261002';OUT=EV/'review-sheets';OUT.mkdir(exist_ok=True)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20);bold=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',23)
def cell(p,w,h,label):
    im=Image.open(p).convert('RGB');im.thumbnail((w,h-48));out=Image.new('RGB',(w,h),(24,27,34));out.paste(im,((w-im.width)//2,48+(h-48-im.height)//2));ImageDraw.Draw(out).text((12,12),label,font=font,fill=(239,227,201));return out
items=[('Idle','BLENDER_REVIEW_front.png'),('Walk','BLENDER_REVIEW_deform_base_walk_f10.png'),('Run','BLENDER_REVIEW_deform_base_run_f6.png'),('Basic1','BLENDER_REVIEW_deform_caster_attack_1_f3.png'),('Basic2','BLENDER_REVIEW_deform_caster_attack_2_f3.png'),('Gale f6','BLENDER_REVIEW_deform_mage_skill_gale_f6.png'),('Nova f6','BLENDER_REVIEW_deform_mage_skill_nova_f6.png'),('Hollow f18','BLENDER_REVIEW_deform_mage_skill_rift_f18.png'),('Lance f14','BLENDER_REVIEW_deform_mage_skill_bolt_f14.png'),('Ward f9','BLENDER_REVIEW_deform_mage_skill_ward_f9.png'),('Orrery f27','BLENDER_REVIEW_deform_mage_skill_starfall_f27.png'),('Hit','BLENDER_REVIEW_deform_base_hit_light_f5.png'),('Dodge','BLENDER_REVIEW_deform_base_dodge_f6.png'),('Death','BLENDER_REVIEW_deform_base_death_f71.png')]
sheet=Image.new('RGB',(4*430,4*550+70),(24,27,34));ImageDraw.Draw(sheet).text((15,17),'BLENDER REVIEW | Pass3 | 14 clips | 30fps | CPU6 / Cycles16',font=bold,fill=(234,192,100));sources=[]
for i,(name,file) in enumerate(items):
    p=EV/'renders/pass3'/file
    if not p.exists():raise FileNotFoundError(p)
    sheet.paste(cell(p,430,550,name),((i%4)*430,70+(i//4)*550));sources.append({'file':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
sheet.save(OUT/'BLENDER_REVIEW_pass3_all14clips.png',optimize=True)
comparisons=[('Run / shoulder seam','BLENDER_REVIEW_deform_base_run_f6.png'),('Orrery / hair and hem','BLENDER_REVIEW_deform_mage_skill_starfall_f27.png'),('Owner LEFT vs SC3r2 RIGHT','BLENDER_REVIEW_staff_owner_LEFT_sc3_r2_RIGHT.png')]
sheet=Image.new('RGB',(3*650,3*740+70),(24,27,34));ImageDraw.Draw(sheet).text((15,17),'BLENDER REVIEW | Locked-camera passes 1 -> 2 -> 3 | Self-review evidence',font=bold,fill=(234,192,100))
for row,(name,file) in enumerate(comparisons):
    for col,tag in enumerate(('pass1','pass2','pass3')):
        p=EV/'renders'/tag/file;sheet.paste(cell(p,650,740,f'{tag}: {name}'),(col*650,70+row*740));sources.append({'file':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
sheet.save(OUT/'BLENDER_REVIEW_three_pass_comparison.png',optimize=True)
(OUT/'receipt.json').write_text(json.dumps({'label':'BLENDER REVIEW CONTACT SHEETS','note':'source images only uniformly scaled, never retouched; all underlying frames retained','sources':sources},indent=2)+'\n',encoding='utf8')
print('composed two review sheets',len(sources),'source frames')
