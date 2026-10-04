"""Sunmeadow resume: 23 rocks, six cliffs, six grotto, nine ruins (44).

Organic forms retain the original seeded np_rock recipes. The two shared tiled
atlases have a 2.5 m period (409.6 source pixels/metre). Candidate only.
"""
from __future__ import annotations


def assets():
    out = []
    def add(aid, group, recipe, seed, params, budget, moss=.5):
        out.append(dict(id=aid, name=aid.replace("sm_", "").replace("_", " "),
                        group=group, family="stone", recipe=recipe, seed=seed, params=params,
                        atlas="sm_ruin" if group == "ruins" else "sm_stone",
                        lod0_tris=budget, budget_class="prop" if budget <= 1500 else "building_module",
                        paint={"moss": moss}, collider={"class": "none" if "pebble" in aid else "solid"},
                        tags=[group, "candidate", "original-procedural", "painted"]))
    for group, sizes, budget in (
        ("small", [.34,.43,.51,.60,.68,.78], 300),
        ("medium", [.86,1.02,1.18,1.37,1.56,1.76], 700),
        ("boulder", [1.9,2.5,3.15,3.9], 1500),
    ):
        for i, size in enumerate(sizes):
            add(f"sm_{group}_{i+1:02d}", "rocks", "rock.boulder/1", 2026100500+len(out),
                dict(size=[size, size*(.62+.06*(i%4)), size*(.56+.13*(i%3))], embed=0,
                     cuts=8+i%4, chips=10+i*2, flat_top=.42 if i%3==0 else .12,
                     top_level=.8, lean_deg=(-7,4,0,8,-3,5)[i], round_bias=.12,
                     detail_amp=.0012, pit_amp=.0012, crack=.23, lump_amp=.020), budget,
                moss=(.3,.48,.62,.4,.72,.5)[i])
    for i in range(4):
        size=.68+i*.22
        add(f"sm_stepstone_{i+1:02d}","rocks","rock.boulder/1",2026100600+i,
            dict(size=[size,size*(.78+.04*i),.14+.035*i],embed=0,flat_top=.85,cuts=8,chips=8,
                 detail_amp=.001,pit_amp=.001,crack=.1,round_bias=.05),200,.24)
    for i in range(3):
        add(f"sm_pebbles_{i+1:02d}","rocks","rock.pebbles/1",2026100700+i,
            dict(count=5+i,radius=.32+i*.07,embed=0),300,.12)
    for i,(kind,size) in enumerate([
        ("wall",[4.2,1.9,3.2]),("wall",[6.0,2.1,4.4]),("wall",[7.6,2.5,5.6]),
        ("corner",[4.8,3.4,4.1]),("corner",[5.4,3.8,4.8]),("cap",[5.6,3.6,1.2])]):
        add(f"sm_cliff_{kind}_{i+1:02d}","cliffs","rock.cliff/1",2026100800+i,
            dict(size=size,embed=0,back_flat=.35,flat_top=.72,strata=.025,strata_spacing=.58,
                 detail_amp=.0009,pit_amp=.0008,chips=25,crack=.35),3000,.65)
        if kind=="corner":
            out[-1]["params"]["blobs"]=[{"c":[-.35,0,0],"r":[.58,1,1]},
                                         {"c":[.35,.40,-.10],"r":[.75,.53,.92]}]
        elif kind=="cap":
            out[-1]["params"].update(blobs=[{"c":[0,0,0],"r":[1,1,1]}],flat_top=.86)
    add("sm_grotto_mouth","grotto","stone.arch/2",2026100901,
        dict(opening=[4.5,5.0],depth=1.5,thickness=.88),4000,.65)
    add("sm_grotto_tunnel","grotto","stone.tunnel/2",2026100902,
        dict(opening=[4.8,5.1],length=4.6,thickness=.62),3000,.32)
    add("sm_grotto_rim","grotto","stone.rim/2",2026100903,
        dict(radius=6.0,arc_degrees=90,height=3.1,thickness=1.05),3000,.7)
    for i in range(3):
        add(f"sm_crystals_{i+1:02d}","grotto","stone.crystals/2",2026100920+i,
            dict(count=5+i,height=1.05+i*.22),900,0)
    for i,kind in enumerate(("intact","broken","toppled")):
        add(f"sm_column_{kind}","ruins","ruin.column/2",2026101000+i,
            dict(kind=kind,height=3.0 if i==0 else 1.85 if i==1 else 2.65),1200,.58)
    for i in range(2):
        add(f"sm_ruin_steps_{i+1:02d}","ruins","ruin.steps/2",2026101020+i,
            dict(width=2.7+i*.45,steps=3+i,rise=.18,tread=.38),1000,.4)
    add("sm_ruin_arch_fragment","ruins","stone.arch/2",2026101040,
        dict(opening=[2.5,3.2],depth=.62,thickness=.48,broken=True),1500,.58)
    for i in range(3):
        add(f"sm_ruin_slab_{i+1:02d}","ruins","ruin.slab/2",2026101050+i,
            dict(size=[1.7+.15*i,1.7,.18],chip=.10+i*.035),400,.4)
    for spec in out:
        if spec["id"].startswith("sm_stepstone_") or spec["recipe"]=="ruin.steps/2":
            spec["tags"].append("REQUIRES_WALK_SURFACE")
    assert len(out)==44
    return out
