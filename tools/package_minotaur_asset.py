"""Package reviewed source/editor/runtime bytes with reproducible hash receipts."""
import argparse,hashlib,json,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True)
a=p.parse_args();root=a.root.resolve();evidence=a.evidence.resolve()
assert root.name=='rig-v1' and root.parent.name=='bovine-shaman'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
build=json.loads((root/'rig-build.json').read_text(encoding='utf-8'))
motion=json.loads((root/'review/motion-check.json').read_text(encoding='utf-8'))
assert motion['weights']['unweighted']==0 and motion['weights']['max_influences']<=4
assert all(c['finite'] and c['max_staff_distance_error_m']<.0001 for c in motion['clips'])
assert all(c['loop_endpoint_delta_m']<.001 for c in motion['clips'] if c['loop'])
files=[root/'minotaur_rig.blend',root/'rig-build.json',root/'runtime/lod-export.json',root/'animation-events.json',root/'README.md']
for i in range(3):
    raw=root/f'runtime/minotaur_lod{i}.glb'
    codec='uastc' if i==0 else 'etc1s'
    opt=root/f'runtime/optimized/minotaur_lod{i}.{codec}-meshopt.glb'
    assert raw.is_file() and opt.is_file(), f'Missing reviewed LOD{i}'
    for filename in (f'minotaur-runtime-20261001-lod{i}.json',f'minotaur-runtime-20261001-lod{i}-optimized.json'):
        report=evidence/filename
        data=json.loads(report.read_text(encoding='utf-8'))
        assert data['status']=='PASS',filename
        copy=root/'review'/filename
        copy.write_bytes(report.read_bytes());files.append(copy)
    files.extend([raw,opt])
for filename in ('minotaur-visual-review-20261001.json',):
    (root/'review'/filename).write_bytes((evidence/filename).read_bytes())
files.extend(path for path in (root/'review').glob('*') if path.suffix in ('.png','.json') and path not in files)
files.append(root/'runtime/optimized/optimization-receipt.json')
files.append(root/'runtime/optimized/minotaur_lod0.etc1s-meshopt.glb')
source=root.parent/'source/bovine_shaman_p20_smartuv_texture_source.glb'
assert digest(source)==build['source_sha256']
manifest={'schema_version':1,'asset':'bovine_shaman_minotaur_rig_v1','provider_job':'d8cbe7d6-7373-4b69-bfa6-47676945b149',
    'source_url':'https://studio.tripo3d.ai/workspace/texture/d8cbe7d6-7373-4b69-bfa6-47676945b149',
    'source_sha256':digest(source),'source_bytes':source.stat().st_size,'height_m':2.4,'deform_joints':32,
    'blender':'5.2.2 LTS','clip_fps':30,'clips':build['actions'],'provider_generation_credits_used_in_this_turn':0,
    'license_status':'User-supplied generated asset; public redistribution rights not independently established',
    'evidence_scope':'Blender review and CPU Babylon checks; browser evidence recorded separately. No phone/multiplayer qualification.',
    'files':[{'path':str(f.relative_to(root)).replace('\\','/'),'bytes':f.stat().st_size,'sha256':digest(f)} for f in files]}
(root/'asset-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
files.append(root/'asset-manifest.json')
package=root/'minotaur_rig_v1.zip'
with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for f in files:z.write(f,arcname=str(f.relative_to(root)).replace('\\','/'))
with zipfile.ZipFile(package) as z:
    assert z.testzip() is None
    for f in files:assert hashlib.sha256(z.read(str(f.relative_to(root)).replace('\\','/'))).hexdigest()==digest(f)
receipt={'status':'PASS','package':str(package),'bytes':package.stat().st_size,'sha256':digest(package),'files':len(files),
         'source_unchanged':True,'source_sha256':digest(source)}
(evidence/'minotaur-package-20261001.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
