"""Seal selected technical candidates, hashes and remaining integration gates."""
import argparse,hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]

def glb_json(path):
 data=path.read_bytes();magic,version,length=struct.unpack_from('<III',data)
 assert magic==0x46546c67 and version==2 and length==len(data)
 size,kind=struct.unpack_from('<II',data,12);assert kind==0x4e4f534a
 return json.loads(data[20:20+size])

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--jobs',required=True);parser.add_argument('--label',required=True);args=parser.parse_args()
 target=ROOT/'planning/evidence/hero-weapons-20261002'/('delivery-'+args.label+'.json')
 if target.exists():raise RuntimeError('Delivery receipt exists; use a new label')
 weapons=[]
 for job in args.jobs.split(','):
  hero,revision=job.split(':',1);evidence=ROOT/'planning/evidence/hero-weapons-20261002'/('hero-'+hero)/revision
  recipe=json.loads((evidence/'receipt.json').read_text(encoding='utf8'));validation=json.loads((evidence/'reimport-validation.json').read_text(encoding='utf8'));assert validation['status']=='PASS'
  packages=[]
  for package in validation['packages']:
   runtime=Path(package.get('runtime_file',package['file']));document=glb_json(runtime)
   for material in document.get('materials',[]):
    assert material.get('alphaMode','OPAQUE')=='OPAQUE' and not material.get('doubleSided',False)
   if 'runtime_file' in package:
    names={n.get('name') for n in document.get('nodes',[])};assert set(recipe['source']['markers']).issubset(names)
    assert len(document.get('textures',[]))<=1
   external=[]
   for image in document.get('images',[]):
    if 'uri' in image:
     imagepath=runtime.parent/image['uri'];assert imagepath.is_file()
     external.append({'file':str(imagepath.relative_to(ROOT)),'bytes':imagepath.stat().st_size,'sha256':hashlib.sha256(imagepath.read_bytes()).hexdigest()})
   packages.append({'file':str(runtime.relative_to(ROOT)),'sha256':hashlib.sha256(runtime.read_bytes()).hexdigest(),'bytes':runtime.stat().st_size,'triangles':package['triangles'],'material_primitives':sum(len(m.get('primitives',[]))for m in document.get('meshes',[])),'textures':external,'extensions_required':document.get('extensionsRequired',[]),'decoded_review_capture':package.get('capture')})
  weapons.append({'hero':hero,'revision':revision,'status':'TECHNICAL_CANDIDATE_PASS','editable_blend':recipe['source_blend'],'lod_ratio':recipe['lod1']['ratio'],'source_reference_hashes':recipe['references'],'packages':packages,'review_captures':recipe['captures'],'validation':str(evidence/'reimport-validation.json')})
 report={'schema':'xexoria.hero-weapons-delivery/1','status':'CANDIDATES_NOT_PROMOTED','weapons':weapons,'remaining_gates':['Native Babylon 13m camera: day/night, both renderers','Final hero grip/contact and arrow draw animation','Combat trail B7 reads fx_base/fx_tip','Owner/Claude art acceptance; silhouettes and fine reference ornament remain simplified'],'source_scope':'Only weapon scripts/models/evidence and the single attachment document. No client/server/Tripo/commit changes.'}
 target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({'receipt':str(target),'weapons':len(weapons)}))
if __name__=='__main__':main()
