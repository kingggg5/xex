"""Flat greybox material colours by material type (sRGB hex, roughness), shared by Blender and review tools."""

MATS = {
    'grass': ('#7f9b58', 0.92), 'mud': ('#6a533a', 0.9), 'mud_puddle': ('#5b5040', 0.42), 'bank_mud': ('#6b5a44', 0.85), 'path_gate_road': ('#c4a273', 0.95),
    'path_gate_road_east': ('#cbb085', 0.95), 'path_cobble': ('#9d968a', 0.85), 'path_southbound_trail': ('#b18c5c', 0.95),
    'path_east_return_path': ('#a39a66', 0.95), 'path_camp_spur': ('#aaa070', 0.95), 'path_boar_trail': ('#8e7a52', 0.95),
    'water': ('#3a7cab', 0.05), 'waterfall': ('#d6ecf6', 0.35), 'foam': ('#eef6f8', 0.6), 'spring_dark': ('#2b2a28', 0.9),
    'rock_bluff': ('#a48c6e', 0.86), 'moss_top': ('#6f8c45', 0.92), 'cliff': ('#7e7266', 0.88), 'cliff_top': ('#6d8a4a', 0.92),
    'hill': ('#8fa86a', 0.92), 'palisade': ('#6f4e33', 0.85), 'gate_timber': ('#5d4129', 0.85), 'timber': ('#6b4b30', 0.8),
    'timber_light': ('#9a7550', 0.8), 'timber_dark': ('#4a3423', 0.85), 'rope': ('#c2a878', 0.9), 'iron': ('#4d4f52', 0.45),
    'stone_light': ('#b8ad98', 0.85), 'stone_carved': ('#c2b8a2', 0.8), 'stone_circle': ('#9a9b93', 0.85),
    'windstone': ('#8b8fa6', 0.75), 'stone_post': ('#a8a294', 0.85), 'stone_dark': ('#6e6a63', 0.9),
    'windmark_stone': ('#b6aa8e', 0.8), 'cloth': ('#d9c9a0', 0.9), 'cloth_red': ('#c0493a', 0.85),
    'cloth_yellow': ('#e3c35a', 0.85), 'hay': ('#d8b75a', 0.95), 'crate': ('#9b7448', 0.85), 'fire': ('#ff8a2a', 0.6),
    'roof': ('#7a5236', 0.85), 'chest': ('#8a5a32', 0.7), 'trunk': ('#5e4632', 0.9), 'trunk_hero': ('#5a4330', 0.9),
    'pine': ('#2f5c3b', 0.85), 'pine_ancient': ('#2a5237', 0.85), 'broadleaf_L': ('#4b7a36', 0.85),
    'broadleaf_M': ('#5a8a3d', 0.85), 'broadleaf_S': ('#6b9a45', 0.85), 'hero_canopy': ('#5f8f3a', 0.85),
    'bush': ('#4f7b3a', 0.85), 'bush_flowering': ('#5f8a44', 0.85), 'flower_yellow': ('#ecd04a', 0.7),
    'flower_white': ('#f2efe2', 0.7), 'flower_pink': ('#e79ab8', 0.7), 'flower_blue': ('#6f8fe0', 0.7),
    'reed': ('#7a9440', 0.85), 'fern': ('#4f8a3e', 0.85), 'mushroom_stem': ('#e3d8c6', 0.8),
    'mushroom_cap': ('#b4523f', 0.7), 'mushroom_glow': ('#7fd6dc', 0.6), 'rock_boulder': ('#8f877b', 0.88),
    'rock_painted': ('#a3907a', 0.85), 'rock_stream': ('#6f7a66', 0.85), 'context_ground': ('#87976a', 0.95),
    'context_hill': ('#93a372', 0.95), 'context_cliff': ('#857a6e', 0.9), 'context_city': ('#b9b2a6', 0.85),
    'context_water': ('#3a6f96', 0.08), 'context_paving': ('#a59d90', 0.85), 'witness': ('#d0352b', 0.6),
    'mark_spawn': ('#ff7a1a', 0.8), 'mark_home': ('#ffb347', 0.8), 'mark_poi': ('#8a3fd1', 0.8), 'collider': ('#ff2a2a', 0.5),
}
EMISSIVE = {'fire': 2.5, 'mark_spawn': 1.0, 'mark_poi': 1.0, 'mark_home': 0.8}
METAL = {'iron': 0.6}
