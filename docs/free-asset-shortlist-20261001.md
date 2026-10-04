# Xexoria free asset shortlist — 2026-10-01

34 specific models, materials and packs, curated against `docs/ui/blueprint.png` and `docs/ui/xexoria-town-art-target-20261001.png`. The target is a grounded fantasy MMO town with warm sandstone, blue slate roofs, readable timber construction, lush plants, small market details and restrained magical light.

The strongest approach is a coordinated material pass plus selected detailed props. Poly Haven assets are photographic/PBR source material; they need a shared color, roughness and contrast treatment to read like the target. Quaternius is a coherent textured alternative with a more stylized shape language. Neither source automatically reproduces the target image.

**Rank A:** prioritize for this town after ordinary material/scale integration. **B:** useful alternative or stronger adaptation needed. **C:** attractive source needing substantial mesh reduction. These are editorial judgments, not benchmark results. No files were downloaded, unpacked, admitted into the game, or performance-tested.

## Best five for the first batch

1. [Roof Slates 02](https://polyhaven.com/a/roof_slates_02): make the town's blue roof family coherent with one recolored slate base.
2. [Medieval Blocks 02](https://polyhaven.com/a/medieval_blocks_02): unify bridge piers, lower walls and tower bases with warm sandstone.
3. [Rock Moss Set 01](https://polyhaven.com/a/rock_moss_set_01): six natural boulder silhouettes improve the foreground and creek banks.
4. [Flower Empodium](https://polyhaven.com/a/flower_empodium): yellow flower variants, 5,820 source triangles; the 1K glTF dependency set is about 0.90 MB.
5. [Wooden Lantern 01](https://polyhaven.com/a/wooden_lantern_01): 8,321 triangles; a detailed timber-and-glass prop that can receive the town's blue light treatment.

All five are [Poly Haven CC0](https://polyhaven.com/license). The flower and rock counts refer to the complete supplied asset/variation layout, not a promised per-instance cost.

## Files, licensing and availability

- **Poly Haven:** the selected models list glTF, FBX, Blend and USD; the selected materials list Blend, glTF and MaterialX. Public files are listed without an account. [CC0](https://polyhaven.com/license). Model maps vary by asset; exact map names and free file manifests are saved in the evidence JSON. The selected PH materials offer diffuse/base color, DX/GL normals, roughness, AO, displacement and packed ARM maps; some also include bump/specular. PNG/JPG/EXR variants are available on the asset pages. Public files are free; supporter products are optional.
- **ambientCG:** public JPG/PNG PBR-map ZIP downloads, with sizes explicitly listed below; no account needed for these public links. [CC0](https://docs.ambientcg.com/license/). Individual map filenames were not inspected.
- **Quaternius:** recommend only the **Standard** file on the creator's itch page. The advertised full-kit count includes models beyond that free subset. Pro ($9.99+) and Source ($14.99+) are paid upsells; assembled scenes, custom shaders and some collision/worn-material features belong to those editions. The public free file listing was checked, but no download/account interaction was exercised.
- **OpenGameArt:** only creator-authored pages are included. Direct public file links are listed in the evidence JSON. For the two sign sets, select the offered CC-BY 3.0 option and preserve attribution; the other offered licenses need not be chosen. The rope fence creator explicitly confirms the current CC0 release despite old text in its Blend file.

PH sizes below are **the sum of bytes in the listed 1K glTF file plus all dependencies**, rounded to decimal MB. They are source transfer sizes, not a compressed GLB, final ZIP, or measured runtime memory. Source triangle counts come from the official metadata; lower-LOD counts remain unknown even where LODs are advertised. PBR materials are surface data, not finished roof/wall/ground geometry.


## Trees and shrubs

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| B | [Jacaranda Tree](https://polyhaven.com/a/jacaranda_tree) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/jacaranda_tree.png?width=256&height=256&v=935ab3ba) / [license](https://polyhaven.com/license) | 312,356 source tris; 214.61 MB at 1K. blend/fbx/gltf/usd; max 8K; LODs advertised, counts unknown | Broad spreading green canopy beside the plaza; organic branches look stronger than cone-shaped placeholders. **Caveat:** 312,356 source tris; advertised LODs, individual LOD counts unknown. Green foliage, not the target's pink cherry blossoms; 1K glTF payload about 214.61 MB. |
| C | [Pine Sapling Small](https://polyhaven.com/a/pine_sapling_small) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/pine_sapling_small.png?width=256&height=256&v=2f751975) / [license](https://polyhaven.com/license) | 398,144 source tris; 21.89 MB at 1K. blend/gltf/usd/fbx; max 8K | Young conifers along the entrance path and creek edges. **Caveat:** 398,144 source tris; no LOD advertised. Extract a small variation and reduce it before runtime; about 21.89 MB at 1K. |
| B | [Wild Rooibos Bush](https://polyhaven.com/a/wild_rooibos_bush) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/wild_rooibos_bush.png?width=256&height=256&v=17366077) / [license](https://polyhaven.com/license) | 76,521 source tris; 2.46 MB at 1K. blend/gltf/usd/fbx; max 8K; LODs advertised, counts unknown | Fine-leaf ground shrubs around rocks, cottage edges and planted beds. **Caveat:** 76,521 source tris for the supplied asset/set; LODs advertised, counts unknown. Check silhouette against the camera; about 2.46 MB at 1K. |

## Flower beds

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Flower Ursinia](https://polyhaven.com/a/flower_ursinia) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/flower_ursinia.png?width=256&height=256&v=c4c93353) / [license](https://polyhaven.com/license) | 44,360 source tris; 2.10 MB at 1K. blend/gltf/usd/fbx; max 4K; LODs advertised, counts unknown | Small yellow/orange flowers around the fountain and in planters. **Caveat:** 44,360 source tris for the supplied variations; LODs advertised. Scatter selected clumps, not the whole source layout. |
| A | [Flower Gazania](https://polyhaven.com/a/flower_gazania) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/flower_gazania.png?width=256&height=256&v=1daefbfc) / [license](https://polyhaven.com/license) | 25,819 source tris; 2.85 MB at 1K. blend/gltf/usd/fbx; max 8K; LODs advertised, counts unknown | Orange daisy-like accents in roadside beds and market planters. **Caveat:** 25,819 source tris; LODs advertised. Botanical detail benefits from simpler shading and controlled saturation. |
| A | [Flower Empodium](https://polyhaven.com/a/flower_empodium) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/flower_empodium.png?width=256&height=256&v=0ea6897e) / [license](https://polyhaven.com/license) | 5,820 source tris; 0.90 MB at 1K. blend/gltf/usd/fbx; max 4K; LODs advertised, counts unknown | Yellow flower clumps for the foreground meadow and low garden borders. **Caveat:** 5,820 source tris; LODs advertised. Strong first-batch option; 1K glTF plus dependencies is about 0.90 MB. |

## Rocks and creek dressing

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Rock Moss Set 01](https://polyhaven.com/a/rock_moss_set_01) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/rock_moss_set_01.png?width=256&height=256&v=e99703c4) / [license](https://polyhaven.com/license) | 63,127 source tris; 1.94 MB at 1K. blend/gltf/usd/fbx; max 8K | Six weathered mossy stones for creek banks, gate approach and planting beds. **Caveat:** 63,127 source tris for the full set, not each rock. Separate rocks and create distant LODs before repeated placement. |
| A | [Rock Moss Set 02](https://polyhaven.com/a/rock_moss_set_02) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/rock_moss_set_02.png?width=256&height=256&v=2acc6bcd) / [license](https://polyhaven.com/license) | 57,647 source tris; 1.94 MB at 1K. blend/gltf/usd/fbx; max 8K | A second silhouette set to avoid repeating the same foreground boulder. **Caveat:** 57,647 source tris for the full set. Pair its moss tint with Set 01 and use only selected stones. |

## Roof materials

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Roof Slates 02](https://polyhaven.com/a/roof_slates_02) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/roof_slates_02.png?width=256&height=256&v=7c21979b) / [license](https://polyhaven.com/license) | PBR material; blend/gltf/mtlx; PNG/JPG/EXR maps; max 8K | Overlapping flat slate tiles for blue cottage and castle roofs. **Caveat:** Grey-brown source needs a deliberate blue recolor. PBR material, not roof geometry; keep tile scale readable. |
| B | [Grey Roof Tiles](https://polyhaven.com/a/grey_roof_tiles) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/grey_roof_tiles.png?width=256&height=256&v=6977cacb) / [license](https://polyhaven.com/license) | PBR material; blend/gltf/mtlx; PNG/JPG/EXR maps; max 8K | Alternative roof profile for secondary shops or a potion-house roof. **Caveat:** Ceramic curved tiles differ from flat slate. Choose deliberately; do not use on every building. |
| A | [Roofing Tiles 001](https://ambientcg.com/view?id=RoofingTiles001) / [preview](https://acg-media.struffelproductions.com/file/ambientCG-Web/media/thumbnail/2048-WEBP/RoofingTiles001.webp) / [license](https://docs.ambientcg.com/license/) | JPG ZIP/PNG ZIP | Slate roof alternative with an old-house profile; recolor toward the target's blue palette. **Caveat:** Texture/PBR maps only; no roof mesh. 1K-JPG ZIP 7 MB, 2K-JPG 23 MB, 4K-JPG 83 MB; PNG variants also available. |

## Stone materials

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Medieval Blocks 02](https://polyhaven.com/a/medieval_blocks_02) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/medieval_blocks_02.png?width=256&height=256&v=01dc0163) / [license](https://polyhaven.com/license) | PBR material; blend/gltf/mtlx; PNG/JPG/EXR maps; max 8K | Weathered sandstone blocks for pale bridge piers, walls and tower bases. **Caveat:** Warm sandy source with orange staining needs a lighter, cleaner plaza grade. PBR material, not a modular wall. |

## Wood materials

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Wood Planks](https://polyhaven.com/a/wood_planks) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/wood_planks.png?width=256&height=256&v=da0c3e1b) / [license](https://polyhaven.com/license) | PBR material; blend/gltf/mtlx; PNG/JPG/EXR maps; max 8K | Warm timber doors, stalls, crates and bridge decking. **Caveat:** Use grain direction along each board; reduce busy contrast at the MMO camera distance. |
| B | [Medieval Wood](https://polyhaven.com/a/medieval_wood) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/medieval_wood.png?width=256&height=256&v=17b0a7e3) / [license](https://polyhaven.com/license) | PBR material; blend/gltf/mtlx; PNG/JPG/EXR maps; max 8K | Riveted old doors, blacksmith surfaces and rough stall panels. **Caveat:** Deep grooves and iron rivets are distinctive; reserve for appropriate worn surfaces. |

## Ground materials

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Patterned Cobblestone](https://polyhaven.com/a/patterned_cobblestone) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/patterned_cobblestone.png?width=256&height=256&v=8dac72aa) / [license](https://polyhaven.com/license) | PBR material; blend/gltf/mtlx; PNG/JPG/EXR maps; max 8K | Patterned paving around the fountain, main plaza and shop fronts. **Caveat:** 2.5 m source scale. PBR does not create the target's radial paving geometry; model or map the plaza pattern separately. |
| A | [Ground 037](https://ambientcg.com/view?id=Ground037) / [preview](https://acg-media.struffelproductions.com/file/ambientCG-Web/media/thumbnail/2048-WEBP/Ground037.webp) / [license](https://docs.ambientcg.com/license/) | JPG ZIP/PNG ZIP | Mossy woodland soil between boulders and grass near the creek. **Caveat:** Scanned damp/overgrown earth, about 2.1 m square. 1K-JPG ZIP 10 MB, 2K-JPG 36 MB. Blend with dry paths rather than cover the whole town. |
| B | [Grass 004](https://ambientcg.com/view?id=Grass004) / [preview](https://acg-media.struffelproductions.com/file/ambientCG-Web/media/thumbnail/2048-WEBP/Grass004.webp) / [license](https://docs.ambientcg.com/license/) | JPG ZIP/PNG ZIP | Green lawn base beneath meadow flowers and along cottage gardens. **Caveat:** Short lush grass material, about 1.4 m square. 1K-JPG ZIP 10 MB, 2K-JPG 38 MB. A flat material needs separate clumps for a convincing foreground silhouette. |

## Town lighting

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Wooden Lantern 01](https://polyhaven.com/a/wooden_lantern_01) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/wooden_lantern_01.png?width=256&height=256&v=ddb2c1b6) / [license](https://polyhaven.com/license) | 8,321 source tris; 3.77 MB at 1K. blend/gltf/usd/fbx; max 8K | Candle lanterns hanging from stalls, doors and the tavern. **Caveat:** 8,321 tris; about 3.77 MB for 1K glTF dependencies. Replace glass/light treatment with the target's blue glow; instancing still needs a practical repetition budget. |
| A | [Lantern Chandelier 01](https://polyhaven.com/a/lantern_chandelier_01) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/lantern_chandelier_01.png?width=256&height=256&v=316ffada) / [license](https://polyhaven.com/license) | 5,971 source tris; 1.48 MB at 1K. blend/gltf/usd/fbx; max 8K | Warm lantern fixture for a tavern porch, guild hall and covered market. **Caveat:** 5,971 tris; about 1.48 MB at 1K. Indoor/covered use fits better than turning it into a road pole. |
| B | [Street Lamp 02](https://polyhaven.com/a/street_lamp_02) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/street_lamp_02.png?width=256&height=256&v=addeb46b) / [license](https://polyhaven.com/license) | 20,338 source tris; 1.87 MB at 1K. blend/gltf/usd/fbx; max 8K | Ornate wall brackets for cottage corners and shop entries. **Caveat:** 20,338 tris. Victorian fixture has exposed bulb detail; hide/replace it with a fantasy crystal and simplify before repeating. |

## Market containers

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Wooden Barrels 01](https://polyhaven.com/a/wooden_barrels_01) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/wooden_barrels_01.png?width=256&height=256&v=2f6882ae) / [license](https://polyhaven.com/license) | 33,142 source tris; 7.49 MB at 1K. blend/usd/gltf/fbx; max 8K | Weathered barrels and loose stave pieces beside market stalls and the blacksmith. **Caveat:** 33,142 tris for the whole set; about 7.49 MB at 1K. Use selected barrels and reduce grime to match the town palette. |
| A | [Wooden Crate 02](https://polyhaven.com/a/wooden_crate_02) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/wooden_crate_02.png?width=256&height=256&v=067477fc) / [license](https://polyhaven.com/license) | 5,176 source tris; 2.24 MB at 1K. blend/gltf/usd/fbx; max 8K | Produce and supply crates in stalls, carts and shop doorways. **Caveat:** 5,176 tris; about 2.24 MB at 1K. A practical first prop set after the five visual foundation choices. |
| A | [Wicker Basket 02](https://polyhaven.com/a/wicker_basket_02) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/wicker_basket_02.png?width=256&height=256&v=2c42d656) / [license](https://polyhaven.com/license) | 17,850 source tris; 3.06 MB at 1K. blend/gltf/usd/fbx; max 8K | Fruit, herbs and flower displays under cloth awnings. **Caveat:** 17,850 tris; about 3.06 MB at 1K. Woven detail may be expensive when repeated; use a reduced version for background stalls. |

## Planters and vessels

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Jug 01](https://polyhaven.com/a/jug_01) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/jug_01.png?width=256&height=256&v=accaeb42) / [license](https://polyhaven.com/license) | 5,770 source tris; 1.23 MB at 1K. blend/gltf/usd/fbx; max 8K | Clay vessels for a pottery merchant and potion-shop shelf. **Caveat:** 5,770 tris; about 1.23 MB at 1K. Keep as a close prop; rescale only after checking its intended dimensions. |
| A | [Planter Pot Clay](https://polyhaven.com/a/planter_pot_clay) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/planter_pot_clay.png?width=256&height=256&v=f6d6a277) / [license](https://polyhaven.com/license) | 3,080 source tris; 1.80 MB at 1K. blend/gltf/usd/fbx; max 4K | Small terracotta pots filled with the flower clumps above. **Caveat:** 3,080 tris; about 1.80 MB at 1K. Source is aged/dirty; clean up the palette for colorful plaza plantings. |
| A | [Planter Box 02](https://polyhaven.com/a/planter_box_02) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/planter_box_02.png?width=256&height=256&v=f50dc7a1) / [license](https://polyhaven.com/license) | 10,944 source tris; 2.47 MB at 1K. blend/gltf/usd/fbx; max 8K | Long timber planting boxes at cottage windows or market edges. **Caveat:** 10,944 tris; about 2.47 MB at 1K. Includes a metal liner; hide it if a simpler medieval planter reads better. |

## Sculpture

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [Gothic Statue](https://polyhaven.com/a/gothic_statue) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/gothic_statue.png?width=256&height=256&v=10aaa08d) / [license](https://polyhaven.com/license) | 27,739 source tris; 3.98 MB at 1K. blend/fbx/gltf/usd; max 8K | Robed stone figure as a gate guardian or a side shrine. **Caveat:** 27,739 tris; about 3.98 MB at 1K. Crown, chains, sword and book give it a darker mood than the fountain's angel; not a direct fountain replacement. |
| B | [Horse Statue 01](https://polyhaven.com/a/horse_statue_01) / [preview](https://cdn.polyhaven.com/asset_img/thumbs/horse_statue_01.png?width=256&height=256&v=f1b16d81) / [license](https://polyhaven.com/license) | 22,388 source tris; 1.28 MB at 1K. blend/gltf/usd/fbx; max 8K | Secondary guild monument or decorative courtyard sculpture. **Caveat:** 22,388 tris; about 1.28 MB at 1K. Use as its own civic motif instead of forcing it into the angel fountain design. |

## Fences and readable shop signs

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| A | [12 Medieval Signs](https://opengameart.org/content/12-medieval-signs) / [preview](https://opengameart.org/sites/default/files/12-medieval-signs-preview.jpg) / [license](https://creativecommons.org/licenses/by/3.0/) | 12-medieval-signs_0.zip; 512x512 raster textures in ZIP; internal image extension not verified; 8.4 MB | Painted pictorial shop signs for blacksmith, weapon shop, magic shop and inn; readable without lettering. **Caveat:** 2D sign art, not a notice-board mesh. Mount on a modeled board; credit the author under the selected CC-BY license. |
| A | [4 Medieval Inn Signs](https://opengameart.org/content/4-medieval-inn-signs) / [preview](https://opengameart.org/sites/default/files/4%20signs-sml.jpg) / [license](https://creativecommons.org/licenses/by/3.0/) | 4-inn-signs.zip; 512x512 raster textures in ZIP; internal image extension not verified; 1.8 MB | Painterly identity for the tavern, inn and guild-side meeting house. **Caveat:** 2D artwork; use simple board geometry. Complements the 12-sign set because it is the same artist. |
| B | [Rope Fence](https://opengameart.org/content/rope-fence) / [preview](https://opengameart.org/sites/default/files/rope_fence.jpg) / [license](https://opengameart.org/content/rope-fence) | rope_fence.zip; ZIP; discussion identifies a .blend file; internal export formats not inspected; 296.7 KB | Low-cost rope boundary around garden beds or a creek path; includes three fences plus separate posts/rope segments. **Caveat:** 64x64 rope diffuse/normal maps are old and low resolution. Rework posts/materials for close views. In-file old license text was explicitly superseded by the creator's 2016 CC0 clarification on the page. |

## Large coherent packs

| Rank | Specific asset and official preview | Verified files / density | Where it helps / caveat |
| --- | --- | --- | --- |
| B | [Stylized Nature MegaKit — Standard](https://quaternius.com/packs/stylizednaturemegakit.html) / [preview](https://quaternius.com/assets/images/fullres/stylizednaturemegakit/standard.jpg) / [license](https://quaternius.com/packs/stylizednaturemegakit.html) | Stylized Nature MegaKit[Standard].zip; FBX/OBJ/glTF; 99 MB; [free-file listing](https://quaternius.itch.io/stylized-nature-megakit) | A coordinated textured nature alternative: trees, flowers, bushes, grass and rocks; useful where photographic detail is too fine at the MMO camera. **Caveat:** Ghibli-inspired shapes are more stylized than the target. 116 is the complete advertised count, not a verified free-edition count. Standard is the free subset; Source shaders and extra models are paid. |
| A | [Fantasy Props MegaKit — Standard](https://quaternius.com/packs/fantasypropsmegakit.html) / [preview](https://quaternius.com/assets/images/fullres/fantasypropsmegakit/standard.jpg) / [license](https://quaternius.com/packs/fantasypropsmegakit.html) | Fantasy Props MegaKit[Standard].zip; FBX/OBJ/glTF; 143 MB; [free-file listing](https://quaternius.itch.io/fantasy-props-megakit) | Coherent town dressing for furniture, tools, vegetables, potions and containers; a strong way to fill stalls while sharing texture sets. **Caveat:** 211/200+ is the full advertised kit, not all-free content. Creator's older OGA Standard upload explicitly contains 94. Free kit contents must be checked before promising a particular market stall; Pro collisions/worn variants and Source scenes are paid. |
| B | [Medieval Village MegaKit — Standard](https://quaternius.com/packs/medievalvillagemegakit.html) / [preview](https://quaternius.com/assets/images/fullres/medievalvillagemegakit/standard.jpg) / [license](https://quaternius.com/packs/medievalvillagemegakit.html) | Medieval Village MegaKit[Standard].zip; FBX/OBJ/glTF; 153 MB; [free-file listing](https://quaternius.itch.io/medieval-village-megakit) | Modular cottage shells, stairs, roofs, windows and wall pieces if building forms also need improvement. **Caveat:** Free Standard is only part of the kit; 304 is the full advertised count. Keep Xexoria's silhouettes and blue-roof palette. Custom collisions, shaders and fully assembled engine projects are Source-tier features. |

## Gaps and exclusions

- The blueprint notice board, gold-trimmed banner posts, angel fountain, bridge arch modules, and specific market-stall shape still need exact matched modeling or a separately verified pack. The sign textures above supply shop identity; they are not a completed notice-board mesh. Do not claim that every pictured Quaternius prop exists in Standard without inspecting that free archive.
- Tree Small 02 was excluded from direct runtime picks: 4,652,585 source triangles. LODs are advertised, but their counts were not verified. An attractive preview does not establish a practical repeated tree.
- Basic Wooden Fence was rejected for this quality brief; its creator-page discussion reports old texture/pivot and high-vertex concerns. Rope Fence is the stronger bounded free fallback, with a clear age/material caveat.
- Lava001, Fir Tree 01 and ModularTree are existing examples and are not counted as new discoveries here.

## Attribution for the sign textures

J. W. Bjerk (eleazzaar) — www.jwbjerk.com/art. Include each source page and a link to CC-BY 3.0; indicate any edits. Source pages provide CC-BY 3.0 as one of their offered license alternatives.

## Evidence

Machine-readable source records, exact PH free-file manifests, maps, triangle counts, preview URLs and acquisition notes: `planning/evidence/free-asset-shortlist-20261001.json`. This is a curation record only, not an asset admission or a download receipt.
