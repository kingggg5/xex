"""Deterministic original craft spec; no third-party or generated-provider source."""
def assets():
    out=[]
    def add(id,recipe,group,budget,params=None,tags=()):
        out.append(dict(id='sm_'+id,family='craft',recipe='craft.'+recipe+'/1',group=group,
            seed=2026100300+len(out),params=params or {},lod0_tris=budget,atlas='sm_craft',
            budget_class='building_module' if budget>2000 else 'prop',tags=list(tags),
            collider={'class':'solid'}))
    add('croft_hut','hut','croft',4000,{'radius':3,'door_width':1.9,'door_height':2.15,'chimney':True},['COMPOUND_OPENING'])
    for shape in ('straight','corner','gate'):add('croft_wall_'+shape,'wall','croft',400,{'shape':shape,'length':3,'height':1.1},['COMPOUND_OPENING'] if shape=='gate' else [])
    add('croft_well','well','croft',1200,{'radius':.8,'height':2.7})
    for i,h in enumerate((1.1,1.6),1):add('croft_skep_'+str(i),'skep','croft',300,{'height':h,'radius':h*.45})
    add('croft_campfire','campfire','croft',1200,{},['VFX_FIRE_ANCHOR'])
    add('croft_fence','fence','croft',400,{'length':2.5})
    add('croft_firewood','firewood','croft',500)
    add('croft_trough','trough','croft',400)
    for end in (False,True):add('pier_'+('end' if end else 'straight'),'pier','pier',800,{'length':4,'width':2,'end':end,'top_y':.12},['REQUIRES_WALK_SURFACE','DECK_Y_0.12'])
    for item in ('post','ladder','bollard'):add('pier_'+item,item,'pier',400)
    add('cove_rowboat','boat','pier',1200,{'length':3.2,'beam':1.25})
    for i,l in enumerate((1.2,1.8,2.6),1):add('cove_driftwood_'+str(i),'driftwood','pier',300,{'length':l})
    add('cove_rod_rack','rod_rack','pier',600,{},['cove_fishing_spot'])
    add('bridge_deck','bridge','threshold',1800,{'length':4,'width':3,'plank_width':4/15,'parapet_height':.95,'top_y':.12},['REQUIRES_WALK_SURFACE','COMPOUND_PARAPET'])
    add('threshold_gate','gate','threshold',2400,{'opening':3,'height':3.8},['COMPOUND_OPENING'])
    for shape in ('pillar','tripod','cresset'):add('brazier_'+shape,'brazier','threshold',1500,{'shape':shape},['VFX_FIRE_ANCHOR','NO_GEOMETRY_FLAMES'])
    for shape in ('A','B','C'):add('market_stall_'+shape.lower(),'stall','market',4000,{'shape':shape,'width':2.4 if shape=='A' else 3 if shape=='B' else 2,'height':2.6,'stripe_m':.3})
    for shape in ('apples','carrots','bread','jars','fish'):add('market_goods_'+shape,'goods','market',1200,{'shape':shape})
    add('cove_sailing_skiff','skiff','skiff',4000,{'length':6,'beam':1.9,'mast_height':5.5},['BOB_ROLL_RUNTIME','VFX_LANTERN_ANCHOR'])
    return out
