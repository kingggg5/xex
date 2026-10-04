"""Four approved ST8pole anchors, runtime semantic overlay; frozen datasets untouched."""
import json,math,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'planning/evidence/blueprint-p1-20261003/st8-root-anchors.json'
anchors=json.loads(source.read_text(encoding='utf-8'))['items']
if len(anchors)!=4 or anchors[0]['xz']!=[-10,-22]:raise ValueError('Four approvedanchorsincludingprimary required')
destinations=[[0,-24],[-10,-54],[0,-68],[0,-101]]
entries=[]
for i,(a,d) in enumerate(zip(anchors,destinations)):
 x,z=a['xz'];dx,dz=d[0]-x,d[1]-z
 entries.append({'id':'semantic_'+a['id'],'blueprint_id':'ST8','blueprint_wave':'P1','asset_id':'sm_blueprint_signpost','class':'blueprint','variant':1,'x':x,'y':0,'z':z,'yaw':round(math.atan2(-dz,dx),5),'scale':1,'target_height':2.2,'footprint_r':.35,'collider':'none','cell':f'{math.floor(x/64)},{math.floor(z/64)}','landmark':True,'shadow':True,'rule':'st8_root_approved_anchors','mask':'explicit','visual_base_y':0,'anchor_at_pivot':True,'standin':False,'destination_xz':d,'source_anchor_id':a['id']})
doc={'schema':'xexoria.semantic-dressing-overlay/1','id':'st8-four-posts-v1','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'wave_gates':['P1','P2'],'entries':entries,'replaces_visual_entries':['bp1_ST8_000'],'replace_reason':'Oldwellwayshrinestand-in occupies exactprimarypoleanchor; omit fromoverlay runtime only, frozenP1/P2JSON unchanged','item_patch':{'id':'ST8','status':'ARROW_BODIES_READY_LABELS_MISSING','assets':['sm_blueprint_signpost'],'remaining_components':['Readablefourdestinationlabels/text missing','Two distinctwayshrinesandcandles unbuilt'],'declared_standins':[]},'physical_admission':'UNVERIFIED_ROOT','native_admission':'UNVERIFIED','no_new_actor_or_terrain':True}
path=ROOT/'planning/levels/sunmeadow-st8-posts-v1.json';path.write_text(json.dumps(doc,indent=1)+'\n',encoding='utf-8')
print('wrote',path.name,'fourposts','sha256',hashlib.sha256(path.read_bytes()).hexdigest())
