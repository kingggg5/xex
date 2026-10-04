"""Sunmeadow v2 terrain surfaces: the single source of constants (terrain spec §6 script 0).

Every terrain script imports this module: the forge (script 1), the mask builder (script 3), the
texture packer/KTX2 exporter (script 5, through terrain-spec.json) and the checker (script 6).
The runtime mirror lives in apps/client/src/terrain-surface-math.mjs; tests assert that its
constants equal the emitted JSON, so any change here must be re-emitted:

    python assets/blender/sunmeadow_v2/terrain/terrain_spec.py --emit-json

Spec: docs/reviews/2026-10-02-map-terrain-spec.md (§2.2 palette, §3 splat, §4 paths, §6 pipeline,
§7 budgets). Pure Python (no numpy) so Blender's interpreter and system Python share it.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

SCHEMA = 'xexoria.terrain-spec/1'
SPEC_DOC = 'docs/reviews/2026-10-02-map-terrain-spec.md'
ROOT = Path(__file__).resolve().parents[4]
SEED = 20261002

# ----------------------------------------------------------------------------
# Folders (spec §6)
# ----------------------------------------------------------------------------
SCRIPTS_DIR = 'assets/blender/sunmeadow_v2/terrain'
SOURCE_DIR = 'assets/models/sunmeadow-v2/terrain'
LAYER_SOURCE_DIR = SOURCE_DIR + '/layers-r7'
CELL_SOURCE_DIR = SOURCE_DIR + '/cells'
RUNTIME_DIR = 'apps/client/src/assets/world/terrain'
EVIDENCE_DIR = 'planning/evidence/terrain-splat-v1'
SPEC_JSON = SOURCE_DIR + '/terrain-spec.json'

# ----------------------------------------------------------------------------
# Cells and coordinates (spec §3.1, §3.4)
# ----------------------------------------------------------------------------
CELL_M = 64.0
# n texel intervals per cell; the map holds (n + 1)^2 corner-aligned texels (centres on the borders).
CELL_N = {'high': 256, 'low': 128}
CELL_TEXELS = {k: n + 1 for k, n in CELL_N.items()}
CELL_ORIGIN_M = -512.0  # cN_rM: c = (minX + 512) / 64, r = (minZ + 512) / 64 (assumption, spec §3.1)


def cell_id(min_x: float, min_z: float, prefix: str = 'sunmeadow') -> str:
    c = int(round((min_x - CELL_ORIGIN_M) / CELL_M))
    r = int(round((min_z - CELL_ORIGIN_M) / CELL_M))
    return f'{prefix}_c{c}_r{r}'


def cell_bounds(cid: str) -> tuple[float, float, float, float]:
    """[minX, maxX, minZ, maxZ] for a cN_rM id (any prefix)."""
    tail = cid.rsplit('_c', 1)[1]
    c, r = tail.split('_r')
    min_x = CELL_ORIGIN_M + int(c) * CELL_M
    min_z = CELL_ORIGIN_M + int(r) * CELL_M
    return (min_x, min_x + CELL_M, min_z, min_z + CELL_M)


# ----------------------------------------------------------------------------
# Per-cell map encodings (spec §3.4). PNG RGB8, linear, no alpha, no colour chunks.
# ----------------------------------------------------------------------------
SPLAT_ENCODING = {
    'format': 'png-rgb8-linear',
    'channels': {'r': 'L0 lush', 'g': 'L1 dry', 'b': 'L2 dirt'},
    'derived': 'L3 mud/moss = 255 - r - g - b (largest-remainder rounding keeps the sum exact)',
}
SDF_MIN_M = -2.0
SDF_RANGE_M = 6.0          # d = v / 255 * 6 - 2  (-2 .. +4 m, 2.35 cm steps), negative inside the path
RUT_MIN_M = -3.0
RUT_RANGE_M = 6.0          # L = v / 254 * 6 - 3; 255 = no rut
RUT_SENTINEL = 255
RUT_EVAL_MAX_M = 1.3       # the shader evaluates ruts only for |L| < 1.3 m
DATA_ENCODING = {
    'format': 'png-rgb8-linear',
    'channels': {'r': f'path-edge SDF d = v/255*{SDF_RANGE_M} + ({SDF_MIN_M}) m',
                 'g': f'rut lateral L = v/254*{RUT_RANGE_M} + ({RUT_MIN_M}) m; {RUT_SENTINEL} = no rut',
                 'b': 'baked ground AO 0..1'},
}
FORBIDDEN_PNG_CHUNKS = ('gAMA', 'cHRM', 'sRGB', 'iCCP')


def encode_sdf(d_m: float) -> int:
    return int(min(255, max(0, round((d_m - SDF_MIN_M) / SDF_RANGE_M * 255.0))))


def decode_sdf(v: float) -> float:
    return v / 255.0 * SDF_RANGE_M + SDF_MIN_M


def encode_rut(l_m: float | None) -> int:
    if l_m is None:
        return RUT_SENTINEL
    return int(min(254, max(0, round((l_m - RUT_MIN_M) / RUT_RANGE_M * 254.0))))


def decode_rut(v: float) -> float | None:
    return None if v >= RUT_SENTINEL else v / 254.0 * RUT_RANGE_M + RUT_MIN_M


# ----------------------------------------------------------------------------
# Layers (spec §3.2, §3.3, §2.2)
# ----------------------------------------------------------------------------

def _layer(lid, name, role, tile_m, res, height_range_m, palette, normal, rough, ao, albedo, channel=None,
           kind='ground'):
    return dict(id=lid, name=name, role=role, channel=channel, kind=kind, tile_m=tile_m, res=res,
                height_range_m=height_range_m, palette=palette, targets=dict(normal=normal, rough=rough, ao=ao,
                                                                              albedo=albedo))


LAYERS = [
    _layer('L0', 'terrain_meadow_lush', 'default meadow, shade, water band', 6.0,
           {'high': 1024, 'medium': 1024, 'low': 512}, 0.10,
           {'base': ['#3f6b2a', '#4c7a2f'], 'light': ['#9fbe55', '#b9cc6a'], 'shadow': ['#23401c'], 'accent': ['#5f8a38']},
           normal=dict(flat_max=0.15, mean=(8.0, 16.0), p50_min=6.0, p95_max=38.0, mip2_mean_min=4.0),
           rough=dict(p5=0.72, p95=0.94, mean=0.84, span_min=0.12, corr_sign=-1),
           ao=dict(mean=(0.80, 0.92)),
           albedo=dict(lum_mean=(0.30, 0.36), sat_mean=(0.45, 0.60), p2_min=0.06, p98_max=0.70), channel='R'),
    _layer('L1', 'terrain_meadow_dry', 'sunny patches, worn verges, camp, sun-facing slopes', 5.0,
           {'high': 1024, 'medium': 512, 'low': 512}, 0.08,
           {'base': ['#8a9a3f', '#a5a14a'], 'light': ['#c4b066'], 'shadow': ['#6b5a35'], 'accent': ['#9a6a3a']},
           normal=dict(flat_max=0.18, mean=(7.0, 14.0), p95_max=36.0, mip2_mean_min=3.5),
           rough=dict(p5=0.80, p95=0.97, mean=0.89, span_min=0.10, corr_sign=-1),
           ao=dict(mean=(0.82, 0.94)),
           albedo=dict(lum_mean=(0.40, 0.48), sat_mean=(0.35, 0.50), p2_min=0.12, p98_max=0.78), channel='G'),
    _layer('L2', 'terrain_path_dirt', 'paths, scree toes, erosion, aprons', 4.0,
           {'high': 1024, 'medium': 1024, 'low': 512}, 0.06,
           {'base': ['#b08a5a'], 'light': ['#c49a64'], 'shadow': ['#8a6a45', '#7a5c3c'],
            'accent': ['#9c958a', '#b7ae9e', '#7c7569']},
           normal=dict(flat_max=0.20, mean=(6.0, 12.0), p95_range=(25.0, 40.0), mip2_mean_min=3.0),
           rough=dict(p5=0.62, p95=0.97, mean=0.86, span_min=0.18, corr_sign=-1),
           ao=dict(mean=(0.80, 0.93)),
           albedo=dict(lum_mean=(0.42, 0.52), sat_mean=(0.25, 0.42), p2_min=0.18, p98_max=0.78), channel='B'),
    _layer('L3', 'terrain_bank_mudmoss', 'banks, spray, shade moss, stream bed', 3.0,
           {'high': 512, 'medium': 512, 'low': 512}, 0.05,
           {'base': ['#4a3a28'], 'light': ['#7d9a3a'], 'shadow': ['#2f251a'], 'accent': ['#4f6b2c', '#5d625e']},
           normal=dict(flat_max=0.30, mean=(4.0, 10.0), p95_max=32.0, mip2_mean_min=2.5),
           rough=dict(p5=0.30, p95=0.92, mean=0.62, span_min=0.30, corr_sign=+1),
           ao=dict(mean=(0.78, 0.92)),
           albedo=dict(lum_mean=(0.20, 0.28), sat_mean=(0.30, 0.50), p2_min=0.06, p98_max=0.48), channel='A'),
]
RELIEF_LAYERS = [
    _layer('R0', 'relief_rock_layered', 'shared bluff/cliff/outcrop detail (tinted at runtime)', 4.0,
           {'high': 1024, 'medium': 512, 'low': 512}, 0.12,
           {'base': ['#a08f78', '#8a7c68'], 'light': ['#c2ae8e'], 'shadow': ['#4a4034'], 'accent': ['#958673', '#6f6556']},
           normal=dict(flat_max=0.05, mean=(10.0, 18.0), p95_max=42.0, mip2_mean_min=6.0),
           rough=dict(p5=0.55, p95=0.95, mean=0.82, span_min=0.20, corr_sign=-1),
           ao=dict(mean=(0.75, 0.92)),
           albedo=dict(lum_mean=(0.40, 0.52), sat_max=0.25, p2_min=0.15, p98_max=0.78), kind='relief'),
    _layer('R1', 'relief_moss_top', 'moss cushions on ledges and tops', 3.0,
           {'high': 512, 'medium': 256, 'low': 256}, 0.05,
           {'base': ['#4f6b2c', '#5a7a30'], 'light': ['#7d9a3a', '#93ad48'], 'shadow': ['#2c3d1a'], 'accent': ['#6b5a35']},
           normal=dict(flat_max=0.15, mean=(8.0, 14.0), mip2_mean_min=4.0),
           rough=dict(p5=0.70, p95=0.92, mean=0.82, span_min=0.12, corr_sign=-1),
           ao=dict(mean=(0.80, 0.92)),
           albedo=dict(lum_mean=(0.28, 0.36), sat_mean=(0.45, 0.62), p2_min=0.08, p98_max=0.62), kind='relief'),
]
ALL_LAYERS = LAYERS + RELIEF_LAYERS
LAYER_BY_ID = {layer['id']: layer for layer in ALL_LAYERS}

# Gates for every layer (spec §3.3 "Gates for every layer").
GATES = dict(
    albedo_channel_p01_min=0.04, albedo_channel_p999_max=0.90,
    rough_adjacent_p95_max=0.05,
    rough_form_corr_min=0.20,
    lum_height_corr_min=0.25,
    lum_gradient_corr_max=0.10,
    height_p1_max=0.10, height_p99_min=0.90,
    normal_height_corr_min=0.85,
    seam_max=1.15,
    flat_deg=1.0,
    # Decoded KTX2 (spec §6.2 item 6).
    ah_psnr_mip0_min=38.0, ah_psnr_mip2_min=36.0,
    height_err_max=6, height_err_mean_max=1.5,
    normal_err_mean_max_deg=1.0, normal_err_p99_max_deg=4.0,
    rough_ao_err_p99_max=5,
    seam_mips_max=1.2,
    normal_y_corr_min=0.5,
    size_1024_max_bytes=900_000, size_512_max_bytes=250_000,
)

# ----------------------------------------------------------------------------
# Paths (spec §4.1); layout path ids map to classes. Extra v2 paths get the nearest class.
# ----------------------------------------------------------------------------
PATH_CLASSES = {
    'gate_road': dict(s_c=1.00, e_c=0.90, worn=0.75, worn_peak_m=0.4, worn_end_m=1.4, ruts=True, rut_gauge_m=1.56,
                      dirt_min_core=0.85, mud=0.0),
    'southbound_trail': dict(s_c=0.95, e_c=0.70, worn=0.60, worn_peak_m=0.4, worn_end_m=1.4, ruts=False,
                             tufts_inner_m=0.4, tufts_weight=(0.2, 0.4), dirt_min_core=0.85, mud=0.0),
    'east_return_path': dict(s_c=0.60, e_c=0.50, worn=0.50, worn_peak_m=0.35, worn_end_m=1.2, ruts=False,
                             track_m=1.4, dirt_min_core=0.50, mud=0.0),
    'camp_spur': dict(s_c=0.40, e_c=0.60, worn=0.90, worn_peak_m=0.3, worn_end_m=1.2, ruts=True, rut_faint=True,
                      inner_dry=0.6, dirt_min_core=0.30, mud=0.0),
    # v2 layout additions (not in the spec's class table; nearest class with the layout's surface note).
    'boar_trail': dict(s_c=0.45, e_c=0.60, worn=0.70, worn_peak_m=0.3, worn_end_m=1.2, ruts=False, inner_dry=0.35,
                       dirt_min_core=0.30, mud=0.25, note='trampled mud-and-grass (layout); camp_spur-like + mud'),
}
PATH_CLASS_OF = {'gate_road': 'gate_road', 'gate_road_east': 'gate_road', 'southbound_trail': 'southbound_trail',
                 'east_return_path': 'east_return_path', 'camp_spur': 'camp_spur', 'boar_trail': 'boar_trail'}
# gate_road_east carries no ruts (joins the main road); the spec's rut list names the gate road and the spur only.
PATH_NO_RUTS = {'gate_road_east'}
RUT = dict(centre_m=0.78, width_m=0.26, profile_half_m=0.15, depth_m=0.045, wander_m=0.10, wander_freq=0.11,
           floor_albedo=0.86, floor_rough=0.85, puddle_rough=0.25, crown_grass=0.35, junction_fade_m=3.0)
BERM = dict(d_min=0.05, d_max=0.45, height_m=0.012, inner_ao=0.08)
EDGE_IRREGULARITY_MIN_M = 0.12

# ----------------------------------------------------------------------------
# Mask rules (spec §3.5)
# ----------------------------------------------------------------------------
MASK = dict(
    edge_noise_m=0.7, edge_noise_amp=0.30,
    macro_scales_m=(32.0, 12.0), macro_weights=(0.65, 0.35), macro_warp_m=6.0,
    # M normalisation (P1 fix): Phi((M - mean) / std) with the field's measured world statistics (v2 stage,
    # 0.5 m grid) - a pure function of world XZ, ~uniform 0..1, no hard clip (the old 3x stretch clipped 10.6 %
    # of the stage flat and made 0 / 0.55 dry plateaus). Breathing: dry share x (1 +- 0.15) at 6 m inside patches.
    macro_mean=0.479, macro_std=0.102, dry_breath=(6.0, 0.15),
    # Erosion scars (§5.4): slope dirt is gated by 2.5 m noise so slope bands break into scars, not rings.
    slope_scar_m=2.5, slope_scar_edges=(0.38, 0.62),
    dirt_slope=(24.0, 32.0, 0.35), scree_toe=0.62, toe_band_m=(0.6, 1.2), toe_moss=0.20,
    stone_base_extra_m=0.9, stone_base_dirt=0.50, altar_apron_m=0.6, altar_apron_dirt=0.60,
    camp_bounds=(19.0, 31.0, -16.0, -3.0), camp_patch=0.35, camp_noise=(0.55, 0.75),
    bank=(0.1, 1.5), bank_noise=0.35, bank_slope_deg=22.0, bank_slope_mud=0.3, bank_slope_reach_m=3.0,
    spray_r=(2.5, 4.5), spray=0.55, shade_ao=0.65, shade_moss=0.35,
    dry_macro=(0.42, 0.72), dry_aspect=(0.55, 0.45), dry_slope=(12.0, 30.0, 0.25), dry_convex=0.15,
    lush_suppress=0.6, lush_band_m=(1.5, 4.0),
    mud_dirt_suppress=0.85, bridge_apron_m=3.5,
    combat_dry=(0.20, 0.70), combat_dirt_max=0.08, combat_std_max=0.07,
    border_default=(0.65, 0.35), border_blend_m=4.0,
    canopy_fade_m=1.2, canopy_strength=0.55,
)
VALIDATION = dict(
    dirt_core=0.85, dirt_core_d=-0.4, dirt_core_paths=('gate_road', 'southbound_trail'),
    dirt_min=dict(east_return_path=0.50, camp_spur=0.30),
    water_dirt_max=0.2, water_dirt_reach_m=1.5, bridge_centre=(-14.0, -50.0), bridge_exempt_m=3.5,
    bank_mud_min=0.6, bank_mud_reach_m=0.4, far_mud_max=0.15, far_mud_reach_m=2.5,
    toe_coverage_min=0.90, toe_band_min=0.5,
    sdf_err_max_m=0.013, sdf_err_reach_m=2.0,
)
STAGE_COVERAGE_EXPECT = dict(dirt=(0.07, 0.12), mud=(0.03, 0.07), dry=(0.20, 0.35), lush=(0.50, 0.65))
SUN_XZ = (0.55 / math.hypot(0.55, -0.35), -0.35 / math.hypot(0.55, -0.35))  # toward-sun, noon SE (§3.5)

# ----------------------------------------------------------------------------
# Runtime shading (spec §3.6) — mirrored by terrain-surface-math.mjs.
# ----------------------------------------------------------------------------
RUNTIME = dict(
    plugin_priority=186, rock_plugin_priority=187,
    height_blend=dict(lam=0.60, delta=0.12, ramp=0.3, h_scale=[1.0, 1.0, 1.0, 0.5], h_bias=[0.0, 0.0, 0.0, 0.0]),
    edge_breakup=dict(band_m=0.7, amp=0.9, freqs=(1.3, 3.1), weights=(0.55, 0.25, 0.2)),
    anti_tiling=dict(rot_cos=0.8, rot_sin=0.6, offset=(0.37, 0.71), mask_period_m=7.3, mask_edges=(0.3, 0.7),
                     height_gain=1.2),
    macro=dict(periods_m=(31.0, 13.0), weights=(0.65, 0.35), value=(0.90, 1.08), cool=(0.97, 1.00, 1.04),
               warm=(1.04, 1.00, 0.94), hue_edges=(0.35, 0.75)),
    rough=dict(ao_term=0.08, wet_dirt=0.45, wet_grass=0.8, clamp=(0.22, 1.0), weather_base=0.94),
    albedo=dict(wet_dirt=0.72, wet_grass=0.86, cell_ao=0.75, dry_tint=(0.914, 0.941, 0.863)),
    wet=dict(mud_edges=(0.25, 0.85), rain_base=0.4, rain_low=0.6, rain_span=0.22),
    far_fade={'2': (70.0, 90.0), '1': (60.0, 80.0), '0': (45.0, 60.0)},
    branch_eps=0.004, tier0_nro_min=0.15,
)
TIERS = {
    '2': dict(presets=['high', 'ultra'], anti_tiling=['L0', 'L1'], berm=True, ruts=True, anisotropy=8, res='high'),
    '1': dict(presets=['medium'], anti_tiling=['L0'], berm=False, ruts=True, anisotropy=4, res='medium'),
    '0': dict(presets=['low'], anti_tiling=[], berm=False, ruts=True, anisotropy=2, res='low'),
}
SAMPLERS = dict(base_pbr=3, limit=16, cell_custom=10, far_custom=2, hero_rock_custom=6, generic_rock_custom=4,
                decal_custom=2)

# Rock plugin (spec §5.1).
ROCK = dict(
    tile_m=4.0, moss_tile_m=3.0, moss_edges=(0.50, 0.82), moss_noise=0.10, moss_allow=0.25, north_shade=0.05,
    convex=(0.58, 0.85, 0.18, '#e8d8b0', -0.05), concave=(0.18, 0.42, 0.25, 0.05), ao_mix=0.7,
    wet_albedo=0.72, wet_rough=0.35, contact_m=0.6,
    strata=dict(bluff=dict(period_m=0.85, dip_deg=4.0, dip_dir='SW'), cliffs=dict(period_m=1.8, dip_deg=7.0, dip_dir='S'),
                value_jitter=0.06, bedding=0.8, bedding_frac=0.04),
    palettes=dict(sandstone=['#a08f78', '#8a7c68', '#c2ae8e', '#4a4034'], granite=['#7d7f80', '#8f8c86', '#a9a59b', '#4b4f53']),
)

# ----------------------------------------------------------------------------
# KTX2 (spec §6.2) and budgets (§7)
# ----------------------------------------------------------------------------
KTX = dict(
    version='4.4.2', pinned='.harness/.cache/toolchains/ktx-4.4.2/portable/bin/ktx.exe', env='KTX_SOFTWARE_BIN',
    ah=['--format', 'R8G8B8A8_UNORM', '--assign-tf', 'linear', '--encode', 'uastc', '--uastc-quality', '2',
        '--uastc-rdo', '--uastc-rdo-l', '1.0', '--zstd', '18'],
    nro=['--format', 'R8G8B8A8_UNORM', '--assign-tf', 'linear', '--encode', 'uastc', '--uastc-quality', '3',
         '--zstd', '18'],
    mip_generate=['--generate-mipmap', '--mipmap-filter', 'lanczos4', '--mipmap-wrap', 'wrap'],
    # The KTX2 upload path ignores Texture.invertY (rows are uploaded as stored); storing a bottom-left origin makes
    # KTX2 sample like a PNG loaded with Babylon's default invertY = true (spec §6.2 item 8: fix orientation in the
    # exporter). The packer writes the KTX inputs bottom row first and ktx only records the origin, because
    # ktx 4.4.2 --convert-texcoord-origin segfaults with many explicit mip levels (seen on the NRO chains).
    origin=['--assign-texcoord-origin', 'bottom-left'],
    nro_mips='explicit levels from the packer (decoded-vector average, renormalise, Toksvig roughness)',
    albedo_encoding='srgb-bytes-in-unorm',
)
BUDGET_MIB = {'high': 24.0, 'medium': 16.0, 'low': 8.0}
RESIDENT_CELLS = 6
ALBEDO_ENCODING = 'srgb-bytes-in-unorm'

# Forge (script 1)
# id renders at 1 spp so kind codes never blend at edges (box-down to the final size gives coverage instead).
FORGE = dict(render_scale=2, device_default='cpu', samples=dict(albedo=8, height=8, normal=6, id=1, ao=48, edge=16))


def as_json() -> dict:
    return dict(schema=SCHEMA, spec=SPEC_DOC, seed=SEED,
                folders=dict(scripts=SCRIPTS_DIR, sources=SOURCE_DIR, layers=LAYER_SOURCE_DIR, cells=CELL_SOURCE_DIR,
                             runtime=RUNTIME_DIR, evidence=EVIDENCE_DIR),
                cell=dict(size_m=CELL_M, n=CELL_N, texels=CELL_TEXELS, origin_m=CELL_ORIGIN_M),
                encodings=dict(splat=SPLAT_ENCODING, data=DATA_ENCODING, sdf=dict(min_m=SDF_MIN_M, range_m=SDF_RANGE_M),
                               rut=dict(min_m=RUT_MIN_M, range_m=RUT_RANGE_M, sentinel=RUT_SENTINEL,
                                        eval_max_m=RUT_EVAL_MAX_M),
                               forbidden_png_chunks=list(FORBIDDEN_PNG_CHUNKS), albedo=ALBEDO_ENCODING),
                layers=LAYERS, relief_layers=RELIEF_LAYERS, gates=GATES,
                path_classes=PATH_CLASSES, path_class_of=PATH_CLASS_OF, path_no_ruts=sorted(PATH_NO_RUTS),
                rut=RUT, berm=BERM, mask=MASK, validation=VALIDATION, stage_coverage_expect=STAGE_COVERAGE_EXPECT,
                sun_xz=SUN_XZ, runtime=RUNTIME, tiers=TIERS, samplers=SAMPLERS, rock=ROCK, ktx=KTX,
                budget_mib=BUDGET_MIB, resident_cells=RESIDENT_CELLS, forge=FORGE)


def emit_json(path: Path | None = None) -> Path:
    path = path or ROOT / SPEC_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(as_json(), indent=1, sort_keys=False) + '\n'
    path.write_text(text, encoding='utf-8')
    return path


if __name__ == '__main__':
    if '--emit-json' in sys.argv:
        out = emit_json()
        print(f'wrote {out.relative_to(ROOT).as_posix()}')
    else:
        print(json.dumps(as_json(), indent=1)[:2000])
