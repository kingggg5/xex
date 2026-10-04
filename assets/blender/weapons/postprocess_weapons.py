"""Run the existing postprocessor with task-local budgets, texture cache and temporary files."""
import argparse, json, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser();p.add_argument('--hero',choices=['02','03','04'],required=True);p.add_argument('--revision',required=True);args=p.parse_args()
 directory=ROOT/'assets/models/weapons'/('hero-'+args.hero)/args.revision
 evidence=ROOT/'planning/evidence/hero-weapons-20261002'/('hero-'+args.hero)/args.revision
 if not directory.is_dir():raise RuntimeError('Build the versioned source first')
 budget=json.loads((ROOT/'tools/asset-budgets.json').read_text(encoding='utf8'))
 budget['classes']={'weapon_lod0':{'profile':'prop','source':'Owner weapon brief: <=2500 tris, one512–1024atlas; two body materials plus bow string.',
   'limits':{'triangles':2500,'draw_calls':3,'materials':3,'texture_mib':2,'glb_kib':256,'vertex_attributes':8},'policy':{'double_sided':'explicit'}},
  'weapon_lod1':{'profile':'prop','source':'Owner weapon brief: 50% LOD1; same texture.',
   'limits':{'triangles':1250,'draw_calls':3,'materials':3,'texture_mib':2,'glb_kib':160,'vertex_attributes':8},'policy':{'double_sided':'explicit'}},
  'bow_string':{'profile':'prop','source':'Separate drawn string pose, no rig or morph required in runtime prop profile.',
   'limits':{'triangles':32,'draw_calls':1,'materials':1,'texture_mib':0,'glb_kib':32,'vertex_attributes':8},'policy':{'double_sided':'explicit'}}}
 budget_file=directory/'weapon-budgets.json';budget_file.write_text(json.dumps(budget,indent=2)+'\n',encoding='utf8')
 temp=evidence/'work-temp';temp.mkdir(parents=True,exist_ok=True)
 env=os.environ.copy();env['TEMP']=str(temp);env['TMP']=str(temp);env['TMPDIR']=str(temp)
 jobs=[]
 for source in sorted(directory.glob('*.glb')):
  if source.name.endswith('.runtime.glb'):continue
  class_name='bow_string' if 'string_drawn' in source.name else 'weapon_lod1' if 'lod1' in source.name else 'weapon_lod0'
  output=directory/(source.stem+'.runtime.glb');report=evidence/(source.stem+'.postprocess.json')
  command=['node',str(ROOT/'apps/client/scripts/gltf-postprocess.mjs'),str(source),'--out',str(output),'--class',class_name,'--budgets',str(budget_file),
   '--texture-out',str(directory/'runtime-textures'),'--report',str(report),'--review-out',str(evidence/'reimport-review'/source.stem)]
  result=subprocess.run(command,cwd=ROOT/'apps/client',env=env,capture_output=True,text=True)
  (evidence/(source.stem+'.postprocess.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
  print(json.dumps({'source':source.name,'exit_code':result.returncode,'report':str(report)}))
  jobs.append({'source':str(source),'output':str(output),'report':str(report),'exit_code':result.returncode})
  if result.returncode:raise RuntimeError('Postprocess policy failed; see the scoped log, source remains intact')
 (evidence/'postprocess-summary.json').write_text(json.dumps(jobs,indent=2)+'\n',encoding='utf8')
if __name__=='__main__':main()
