"""Bounded material repair from actual r03 review; immutable fresh destination only."""
from pathlib import Path
import argparse,json,hashlib,shutil
from PIL import Image
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args();src,out=Path(a.source),Path(a.out)
if out.exists():raise ValueError('Fresh immutable texture destination required')
shutil.copytree(src,out)
path=out/'market_hero_albedo.png';rgb=np.asarray(Image.open(path).convert('RGB'),np.float32)/255;h,w=rgb.shape[:2]
repairs={'apple':(.53,.03,(1.12,1.70,2.00)),'bread':(.76,.03,(1.18,1.16,1.20)),'clay':(.53,.26,(1.24,1.73,1.90)),'basket':(.76,.26,(1.08,1.10,1.20))}
for name,(u,v,mul) in repairs.items():
    x0,x1=int(u*w),int((u+.2)*w);y0,y1=int((1-v-.2)*h),int((1-v)*h);rgb[y0:y1,x0:x1]=np.clip(rgb[y0:y1,x0:x1]*np.array(mul),.105,.94)
Image.fromarray(np.round(rgb*255).astype(np.uint8),'RGB').save(path)
receipt={'schema':'xexoria.market-material-repair/1','sourceAlbedoSha256':hashlib.sha256((src/'market_hero_albedo.png').read_bytes()).hexdigest(),'outputAlbedoSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'observedDefect':'r03 goods under the canopy too dark and similar in value','repair':'moderate dusty red apples, warmer bread, cream-washed clay and light wicker; no emission; cloth/timber/baked normal/AO unchanged','source':'original procedural atlas and actual shared-trim bake r02','changes':repairs}
(out/'material-repair.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print('GOODS MATERIAL REPAIR',receipt['outputAlbedoSha256'])
