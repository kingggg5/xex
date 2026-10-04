"""Atlas layouts for the painted flora atlases (pure Python; shared by the Blender recipes and the numpy painter).

Rects are (x, y, w, h) in pixels with the origin at the TOP-LEFT of the image (PNG rows). uv_rect() converts to
Blender UV space (origin bottom-left) as (u0, v0, du, dv).
"""

WATER = {
    "id": "sm_flora_water",
    "size": 1024,
    "rects": {
        "pad_a": (0, 0, 256, 256), "pad_b": (256, 0, 256, 256), "pad_c": (512, 0, 256, 256),
        "lotus_leaf": (768, 0, 256, 256),
        "petal_pink_outer": (0, 256, 128, 256), "petal_pink_inner": (128, 256, 128, 256),
        "petal_white_outer": (256, 256, 128, 256), "petal_white_inner": (384, 256, 128, 256),
        "pod_top": (512, 256, 128, 128), "cattail": (512, 384, 128, 128),
        "stamens": (640, 256, 384, 64), "stem": (640, 320, 384, 64),
        "stem_reed": (640, 384, 384, 64), "pod_side": (640, 448, 384, 64),
        "reeds_tall": (0, 512, 256, 512), "reeds_sedge": (256, 512, 256, 512),
        "reeds_short": (512, 512, 256, 512), "reeds_mixed": (768, 512, 256, 512),
    },
}

MEADOW = {
    "id": "sm_flora_meadow",
    "size": 1024,
    "rects": {
        "wf_orange": (0, 0, 256, 512), "wf_red": (256, 0, 256, 512), "wf_white": (512, 0, 256, 512),
        "wf_yellow": (768, 0, 256, 512), "wf_blue": (0, 512, 256, 512),
        "mush_cap_red": (256, 512, 128, 128), "mush_cap_brown": (384, 512, 128, 128),
        "mush_cap_cream": (256, 640, 128, 128), "mush_stem": (384, 640, 128, 128),
        "leafy_tuft": (512, 512, 256, 512), "veg_cabbage": (768, 512, 128, 128),
        "veg_leaf": (896, 512, 128, 128), "veg_carrot": (768, 640, 128, 128), "veg_soil": (896, 640, 128, 128),
        "veg_stake": (768, 768, 256, 64), "veg_twine": (768, 832, 256, 64), "spare": (256, 768, 256, 256),
    },
}


def uv_rect(layout, name, inset_px=1.5):
    x, y, w, h = layout["rects"][name]
    S = float(layout["size"])
    return ((x + inset_px) / S, 1.0 - (y + h - inset_px) / S, (w - 2 * inset_px) / S, (h - 2 * inset_px) / S)
