"""Create native sRGB UASTC KTX2 with coverage-preserving supplied mip images; no downloads."""
from pathlib import Path
import importlib.util, json, hashlib, subprocess, argparse
import numpy as np
from PIL import Image

ap=argparse.ArgumentParser();ap.add_argument('--assets',required=True);ap.add_argument('--evidence',required=True);ap.add_argument('--ktx',required=True);args=ap.parse_args()
assets=Path(args.assets).resolve();evidence=Path(args.evidence).resolve();evidence.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('grass_painter',Path(__file__).with_name('paint_grass_atlas.py'));painter=importlib.util.module_from_spec(spec);spec.loader.exec_module(painter)
manifest=json.loads((assets/'grass_atlas_v1.json').read_text());records=[]
for name in ['grass_atlas_v1_albedo','grass_atlas_v1_1024_albedo']:
    base=np.array(Image.open(assets/(name+'.png')).convert('RGBA'));h,w=base.shape[:2];files=[];coverage=[]
    for level in range(6):
        image=painter.premul_resize(base,(max(1,w>>level),max(1,h>>level))) if level else base.copy()
        # Each cell has its own target coverage and alpha scale; preserve thin tips without tinting transparent edges.
        for cell in manifest['cells']:
            x,y,cw,ch=cell['rect_px'];factor=w/2048/(2**level);x,y,cw,ch=[int(round(v*factor)) for v in (x,y,cw,ch)]
            if not cw or not ch:continue
            alpha=image[y:y+ch,x:x+cw,3].astype(np.float32)/255;target=cell['coverage_mip0']
            if target<=0:continue
            # Target is relative to content rect, so measure a cell's original full-cell binary coverage instead.
            bx,by,bw,bh=cell['rect_px'];full=np.array(Image.open(assets/'grass_atlas_v1_albedo.png'))[by:by+bh,bx:bx+bw,3];target=float((full>=128).mean())
            lo,hi=.1,5
            for _ in range(20):
                mid=(lo+hi)/2
                if (alpha*mid>=.5).mean()<target:lo=mid
                else:hi=mid
            scale=(lo+hi)/2 if level else 1
            image[y:y+ch,x:x+cw,3]=np.clip(np.round(alpha*scale*255),0,255).astype(np.uint8)
            coverage.append({'cell':cell['id'],'mip':level,'scale':round(scale,5),'target':round(target,5),'measured':round(float((alpha*scale>=.5).mean()),5)})
        path=evidence/(name+f'-mip{level}.png');Image.fromarray(image).save(path);files.append(str(path))
    output=assets/(name+'.ktx2')
    cmd=[args.ktx,'create','--format','R8G8B8A8_SRGB','--assign-tf','srgb','--assign-primaries','bt709','--levels','6','--encode','uastc','--uastc-quality','2','--zstd','9','--threads','2',*files,str(output)]
    result=subprocess.run(cmd,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr[-2000:])
    validate=subprocess.run([args.ktx,'validate',str(output)],capture_output=True,text=True)
    if validate.returncode:raise RuntimeError(validate.stderr[-2000:])
    records.append({'file':output.name,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bytes':output.stat().st_size,'coverage':coverage,'command':cmd,'validation':'PASS'})
(evidence/'ktx2-receipt.json').write_text(json.dumps({'schema':'xexoria.grass-ktx2/1','records':records},indent=2))
print(json.dumps([{'file':r['file'],'bytes':r['bytes'],'validation':r['validation']} for r in records]))
