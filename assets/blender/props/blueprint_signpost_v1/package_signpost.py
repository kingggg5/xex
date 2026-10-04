"""Seal owned candidate handoff from actual helper/postprocess receipts; no admission."""
from pathlib import Path
import hashlib,json,struct
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'assets/models/props/blueprint-signpost-v1-candidate/r01'
EV=ROOT/'planning/evidence/blueprint-semantic-props-20261003'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def glb(p):
    data=p.read_bytes();magic,version,size=struct.unpack_from('<III',data);assert magic==0x46546c67 and version==2 and size==len(data)
    length,kind=struct.unpack_from('<II',data,12);assert kind==0x4e4f534a;return json.loads(data[20:20+length])
def write(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
candidate=read(OUT/'candidate.json');intake=read(EV/'source-intake.json');unchanged=[]
for row in intake['protected_sources']:
    check={**row,'unchanged':sha(ROOT/row['path'])==row['sha256']};assert check['unchanged'],row['path'];unchanged.append(check)
rows={}
for suffix in ('lod0','lod1','lod2','collider','shadow_proxy'):
    name=f'sm_blueprint_signpost_{suffix}';p=OUT/'runtime'/f'{name}.glb';j=glb(p);rep=read(p.with_suffix('.report.json'));helper=read(OUT/'source'/f'{name}.receipt.json')
    assert rep['status']=='PASS' and helper['status']=='PASS' and rep['validator']['errors']==0
    assert not set(j.get('extensionsUsed',[]))&{'KHR_meshopt_compression','KHR_draco_mesh_compression','KHR_lights_punctual'}
    for image in j.get('images',[]):assert (p.parent/image['uri']).is_file()
    rows[suffix]={'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sha(p),'bytes':p.stat().st_size,'metrics':rep['metrics'],'extensionsUsed':j.get('extensionsUsed',[]),'validator':rep['validator'],'source_reimport':'PASS'}
texture_rows=read(OUT/'runtime/sm_blueprint_signpost_lod0.report.json')['textures']
assert all(row['cache']=='hit' for row in texture_rows)
runtime_bytes=sum(row['bytes'] for row in rows.values());textures_bytes=sum(row['bytes'] for row in texture_rows)
asset={'id':'sm_blueprint_signpost','family':'craft','file':rows['lod0']['path'],'lods':[rows[f'lod{i}']['path'] for i in range(3)],'bounds':{'min':[-.8,0,-.075],'max':[.8,2.2,.193]},'pivot':[0,0,0],'collider':{'file':rows['collider']['path'],**candidate['collider']},'shadow_proxy':rows['shadow_proxy']['path'],'material_slots':['sm_craft_timber'],'atlas_family':'sm_craft','authoring_texel_density_px_m':360,'units':'metres','front':'Blender -Y / glTF +Z; root aligns world-authored glTF','labels':'No baked text; root data/HTML labels later','anchor_reference':'planning/evidence/blueprint-p1-20261003/st8-root-anchors.json','expected_instances':4,'license':'Owner-authored original procedural sign and existing owner craft maps','source':'assets/blender/props/blueprint_signpost_v1/sources/sm_blueprint_signpost_r01.blend','status':'SOURCE_REVIEW_AND_STATIC_PASS_NATIVE_UNVERIFIED'}
manifest={'schema':'xexoria.semantic-prop-candidate-manifest/1','status':asset['status'],'assets':[asset],'files':rows,'textures':texture_rows,'do_not_promote':'Root owns native import, terrain/physical admission and overlay placement; no default promotion'}
write(OUT/'candidate-manifest.json',manifest)
receipt={'schema':'xexoria.semantic-prop-final/1','started_ict':intake['started_ict'],'status':'TECHNICAL_PASS_SOURCE_ART_PASS_GAMEPLAY_UNVERIFIED','signpost':asset,'runtime':rows,'source_reviews':read(EV/'signpost/r01/source-views.json'),'source_critique':{'pass':'r01; one actual build/capture pass','player_13m':'opposing arrows and grounded pole remain recognizable','front':'bevels, thick boards and four pegs visible; no text baked','side':'boards touch pole and pegs penetrate the joint; broad shadow shape','limits':['Inherited craft wood tile has painted stud marks; no unique texture pass','Fine grain is subdued at13m; shape carries route-sign recognition','Human-readable destination labels remain root data/HTML work','Native both-renderer import and performance, physical pole/board clearance and terrain support remain unverified']},'head':{'status':'MISSING','feasibility':read(EV/'signpost/r01/guardian-head-feasibility.json'),'reason':'Raised arms overlap head height in this licensed posed anatomy; a height crop would retain hands/arms. No independently validated vertex-group neck cut/cap was made in this bounded sign window. No substitute anatomy was invented.'},'budget':{'lod_triangles':[rows[f'lod{i}']['metrics']['triangles'] for i in range(3)],'four_signs_lod0_triangles':4*rows['lod0']['metrics']['triangles'],'runtime_glb_bytes':runtime_bytes,'shared_texture_bytes':textures_bytes,'candidate_transfer_bytes':runtime_bytes+textures_bytes,'referenced_shared_atlas_gpu_mib':rows['lod0']['metrics']['texture_mib'],'added_frame_cost':'UNVERIFIED','textures':'Three byte-identical verified existing KTX2 cache hits; no encoder/map texture pass','validator':'All five files0errors; textured LODs each6warnings from validator image/ktx2 recognition, retained in per-file receipts'},'protected_sources':unchanged,'resources':{'source_cpu_slot_ict':['19:31:18','19:31:41'],'export_cpu_slot_ict':['19:32:31','19:32:35'],'heavy_work_release_ict':'19:32:48','state':'QUIESCED','gpu_capture':'NONE','blender_threads':6},'jeV':'Reused root verified intake advisory verify_then_integrate; no new call/savings claim'}
write(EV/'FINAL-RECEIPT.json',receipt);write(OUT/'handoff.json',receipt)
print('SIGNPOST_PACKAGE_PASS',runtime_bytes,textures_bytes,'HEAD_MISSING')
