"""XS1 skeleton definition for hero 02 (docs/reviews/2026-10-02-heroes-rig-and-animation.md section 3.2).

43 core joints in the fixed contract order + 16 hero-02 secondary joints (skirt 8, sleeve 2, hair 3, hat 3) = 59.
Joint positions come from the Tripo Mixamo auto-rig (used as the measuring tool, rig doc H2), converted to metres;
secondary joints are fitted to the measured garment pieces in h02_build_lods_rig.py.
"""
CORE = [
    "root", "hips", "spine", "chest", "upper_chest", "neck", "head",
    "shoulder.L", "upper_arm.L", "upper_arm_twist.L", "forearm.L", "forearm_twist.L", "hand.L",
    "thumb.01.L", "thumb.02.L", "index.01.L", "index.02.L", "grip.01.L", "grip.02.L", "socket_weapon_L", "pauldron.L",
    "shoulder.R", "upper_arm.R", "upper_arm_twist.R", "forearm.R", "forearm_twist.R", "hand.R",
    "thumb.01.R", "thumb.02.R", "index.01.R", "index.02.R", "grip.01.R", "grip.02.R", "socket_weapon_R", "pauldron.R",
    "thigh.L", "shin.L", "foot.L", "toe.L", "thigh.R", "shin.R", "foot.R", "toe.R",
]
SECONDARY = [
    "skirt.F.01", "skirt.F.02", "skirt.B.01", "skirt.B.02", "skirt.L.01", "skirt.L.02", "skirt.R.01", "skirt.R.02",
    "sleeve.L.01", "sleeve.R.01",
    "hair.01", "hair.02", "hair.03",
    "hat.01", "hat.02", "hat.03",
]
JOINTS = CORE + SECONDARY
assert len(CORE) == 43 and len(JOINTS) == 59

PARENT = {
    "root": None, "hips": "root", "spine": "hips", "chest": "spine", "upper_chest": "chest", "neck": "upper_chest",
    "head": "neck",
    "thigh.L": "hips", "shin.L": "thigh.L", "foot.L": "shin.L", "toe.L": "foot.L",
    "thigh.R": "hips", "shin.R": "thigh.R", "foot.R": "shin.R", "toe.R": "foot.R",
    "skirt.F.01": "hips", "skirt.F.02": "skirt.F.01", "skirt.B.01": "hips", "skirt.B.02": "skirt.B.01",
    "skirt.L.01": "hips", "skirt.L.02": "skirt.L.01", "skirt.R.01": "hips", "skirt.R.02": "skirt.R.01",
    "hair.01": "head", "hair.02": "hair.01", "hair.03": "hair.02",
    "hat.01": "head", "hat.02": "hat.01", "hat.03": "hat.02",
}
for s in ("L", "R"):
    PARENT.update({
        f"shoulder.{s}": "upper_chest", f"upper_arm.{s}": f"shoulder.{s}", f"upper_arm_twist.{s}": f"upper_arm.{s}",
        f"forearm.{s}": f"upper_arm.{s}", f"forearm_twist.{s}": f"forearm.{s}", f"hand.{s}": f"forearm.{s}",
        f"thumb.01.{s}": f"hand.{s}", f"thumb.02.{s}": f"thumb.01.{s}", f"index.01.{s}": f"hand.{s}",
        f"index.02.{s}": f"index.01.{s}", f"grip.01.{s}": f"hand.{s}", f"grip.02.{s}": f"grip.01.{s}",
        f"socket_weapon_{s}": f"hand.{s}", f"pauldron.{s}": f"shoulder.{s}", f"sleeve.{s}.01": f"forearm.{s}",
    })

# Mixamo (Tripo humanoid preset) -> XS1 skin-weight merge map (rig doc section 3.2: ring/pinky merge into grip,
# Thumb2-4 into thumb.02, Index2-4 into index.02, HeadTop_End into head, Toe_End into toe).
MIXAMO_TO_XS1 = {"Hips": "hips", "Spine": "spine", "Spine1": "chest", "Spine2": "upper_chest", "Neck": "neck",
                 "Head": "head", "HeadTop_End": "head"}
for side, s in (("Left", "L"), ("Right", "R")):
    MIXAMO_TO_XS1.update({
        f"{side}Shoulder": f"shoulder.{s}", f"{side}Arm": f"upper_arm.{s}", f"{side}ForeArm": f"forearm.{s}",
        f"{side}Hand": f"hand.{s}", f"{side}HandThumb1": f"thumb.01.{s}", f"{side}HandThumb2": f"thumb.02.{s}",
        f"{side}HandThumb3": f"thumb.02.{s}", f"{side}HandThumb4": f"thumb.02.{s}",
        f"{side}HandIndex1": f"index.01.{s}", f"{side}HandIndex2": f"index.02.{s}",
        f"{side}HandIndex3": f"index.02.{s}", f"{side}HandIndex4": f"index.02.{s}",
        f"{side}UpLeg": f"thigh.{s}", f"{side}Leg": f"shin.{s}", f"{side}Foot": f"foot.{s}",
        f"{side}ToeBase": f"toe.{s}", f"{side}Toe_End": f"toe.{s}",
    })
    for finger in ("Middle", "Ring", "Pinky"):
        MIXAMO_TO_XS1[f"{side}Hand{finger}1"] = f"grip.01.{s}"
        for k in (2, 3, 4):
            MIXAMO_TO_XS1[f"{side}Hand{finger}{k}"] = f"grip.02.{s}"

# Mixamo -> XS1 for retargeting the Tripo clips (pose transfer; same mesh, so the same joint positions)
MIXAMO_POSE = {"Hips": "hips", "Spine": "spine", "Spine1": "chest", "Spine2": "upper_chest", "Neck": "neck",
               "Head": "head"}
for side, s in (("Left", "L"), ("Right", "R")):
    MIXAMO_POSE.update({f"{side}Shoulder": f"shoulder.{s}", f"{side}Arm": f"upper_arm.{s}",
                        f"{side}ForeArm": f"forearm.{s}", f"{side}Hand": f"hand.{s}",
                        f"{side}HandThumb1": f"thumb.01.{s}", f"{side}HandThumb3": f"thumb.02.{s}",
                        f"{side}HandIndex1": f"index.01.{s}", f"{side}HandIndex3": f"index.02.{s}",
                        f"{side}HandMiddle1": f"grip.01.{s}", f"{side}HandMiddle3": f"grip.02.{s}",
                        f"{side}UpLeg": f"thigh.{s}", f"{side}Leg": f"shin.{s}", f"{side}Foot": f"foot.{s}",
                        f"{side}ToeBase": f"toe.{s}"})

# Quaternius UAL1 (2025-06-10, v1 Rigify-style names) -> XS1 for retargeting (rig doc table, column "From UAL v1")
UAL_POSE = {"DEF-hips": "hips", "DEF-spine.001": "spine", "DEF-spine.002": "chest", "DEF-spine.003": "upper_chest",
            "DEF-neck": "neck", "DEF-head": "head"}
for s in ("L", "R"):
    UAL_POSE.update({f"DEF-shoulder.{s}": f"shoulder.{s}", f"DEF-upper_arm.{s}": f"upper_arm.{s}",
                     f"DEF-forearm.{s}": f"forearm.{s}", f"DEF-hand.{s}": f"hand.{s}",
                     f"DEF-thumb.01.{s}": f"thumb.01.{s}", f"DEF-thumb.03.{s}": f"thumb.02.{s}",
                     f"DEF-f_index.01.{s}": f"index.01.{s}", f"DEF-f_index.03.{s}": f"index.02.{s}",
                     f"DEF-f_middle.01.{s}": f"grip.01.{s}", f"DEF-f_middle.03.{s}": f"grip.02.{s}",
                     f"DEF-thigh.{s}": f"thigh.{s}", f"DEF-shin.{s}": f"shin.{s}", f"DEF-foot.{s}": f"foot.{s}",
                     f"DEF-toe.{s}": f"toe.{s}"})

STATIC_NODES = {  # empties exported as child nodes of joints (rig doc section 3.4)
    "socket_back": "upper_chest", "socket_hip_L": "hips", "socket_hip_R": "hips", "socket_head": "head",
    "socket_face": "head", "socket_mouth": "head", "fx_head": "head", "fx_chest": "upper_chest",
    "fx_hand_L": "hand.L", "fx_hand_R": "hand.R", "fx_feet": "root",
}
