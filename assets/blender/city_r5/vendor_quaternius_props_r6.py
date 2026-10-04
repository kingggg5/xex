"""Vendor the CC0 Quaternius Fantasy Props MegaKit pieces used by the R6 dressing candidate.

Only props whose materials use the Metal, Furniture and Cloth trim sheets (plus MI_Banner)
are admitted: those nine textures are already vendored beside the featured stall cart and
their KTX2 copies are already part of the admitted city runtime, so the candidate adds no
new image. Image URIs are rewritten to the existing vendored PNGs (byte-identical, hashes
checked below). Writes assets/blender/city_r5/props_r6/quaternius/ and a provenance manifest.

  python assets/blender/city_r5/vendor_quaternius_props_r6.py
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ZIP = Path.home() / 'Downloads' / 'Xexoria-Game' / 'kits' / 'Fantasy Props MegaKit[Standard].zip'
ZIP_SHA = '8b6f7e806d222e585478f0e1bdc6b271bbc7bc6f84dd6af8ca703a7c64f0cb1e'
TEX_DIR = ROOT / 'assets/third-party/quaternius-fantasy-props-megakit/standard/stall-cart/glTF'
OUT = ROOT / 'assets/blender/city_r5/props_r6/quaternius'
PROPS = ['Bench', 'Barrel', 'Barrel_Holder', 'Bag', 'Banner_1_Cloth', 'Banner_2_Cloth', 'Bucket_Wooden_1',
         'Cauldron', 'Chest_Wood', 'Crate_Wooden', 'FarmCrate_Empty', 'Lantern_Wall', 'Pot_1', 'Rope_2',
         'Stall_Empty', 'Stool', 'Table_Large', 'Torch_Metal', 'WeaponStand', 'Workbench', 'Anvil', 'Shelf_Simple',
         'Chair_1', 'Mug', 'Bucket_Metal']
ALLOWED_IMAGES = {'T_Trim_Metal_BaseColor.png', 'T_Trim_Metal_Normal.png', 'T_Trim_Metal_ORM.png',
                  'T_Trim_Furniture_BaseColor.png', 'T_Trim_Furniture_Normal.png', 'T_Trim_Furniture_ORM.png',
                  'T_Trim_Cloth_BaseColor.png', 'T_Trim_Cloth_Normal.png', 'T_Trim_Cloth_ORM.png'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    data = ZIP.read_bytes()
    if sha(data) != ZIP_SHA:
        raise SystemExit('Quaternius archive hash changed; re-audit the licence and contents first.')
    z = zipfile.ZipFile(ZIP)
    OUT.mkdir(parents=True, exist_ok=True)
    rel_tex = Path('../../../../third-party/quaternius-fantasy-props-megakit/standard/stall-cart/glTF')
    records = []
    for name in PROPS:
        g = json.loads(z.read(f'Exports/glTF/{name}.gltf'))
        for img in g.get('images', []):
            uri = img['uri']
            if uri not in ALLOWED_IMAGES:
                raise SystemExit(f'{name} uses a non-admitted image {uri}')
            zbytes = z.read(f'Exports/glTF/{uri}')
            if sha(zbytes) != sha((TEX_DIR / uri).read_bytes()):
                raise SystemExit(f'{uri} differs from the vendored copy')
            img['uri'] = (rel_tex / uri).as_posix()
        bins = []
        for buf in g.get('buffers', []):
            b = z.read(f"Exports/glTF/{buf['uri']}")
            (OUT / buf['uri']).write_bytes(b)
            bins.append({'file': buf['uri'], 'sha256': sha(b), 'bytes': len(b)})
        text = json.dumps(g, indent=1)
        (OUT / f'{name}.gltf').write_text(text, encoding='utf-8')
        tris = 0
        for m in g['meshes']:
            for p in m['primitives']:
                acc = g['accessors'][p.get('indices', p['attributes']['POSITION'])]
                tris += acc['count'] // 3
        records.append({'prop': name, 'gltf_sha256': sha(text.encode('utf-8')), 'buffers': bins, 'triangles': tris,
                        'materials': [m.get('name') for m in g.get('materials', [])]})
    manifest = {'schema': 'xexoria.vendored-cc0-props/1', 'source_archive': str(ZIP), 'source_archive_sha256': ZIP_SHA,
                'source_url': 'https://quaternius.com/packs/fantasypropsmegakit.html', 'licence': 'CC0 1.0 Universal',
                'licence_text': 'assets/third-party/quaternius-fantasy-props-megakit/License_Standard.txt',
                'textures': 'reuses the nine byte-identical trim-sheet PNGs vendored with the featured stall cart',
                'props': records}
    (OUT / 'provenance.json').write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'props': len(records), 'out': str(OUT)}))


if __name__ == '__main__':
    main()
