# Free fountain water normal candidate

The selected small source is [ProcTexture Wave Normal Map](https://proctexture.com/textures/water/normal-maps/wave-normal-map). Its asset page and [official terms](https://proctexture.com/terms) identify exported texture outputs as CC0-1.0. The provider describes this as a directional water normal for game shaders, rather than a photograph to paste over the fountain. The terms distinguish exported textures from the site's code and documentation.

The unchanged 1024² normal PNG is staged at `assets/textures/fountain-water-cc0/water_wave_normal_1024.png` (821,327 bytes). One official source ZIP (2,707,134 bytes) is retained alongside the license note and hash roster. No account, payment, installer or cloud generation was used. A source candidate does not establish engine admission or final artistic quality.

Inspection confirms RGB-encoded unit normals: decoded vector lengths are 0.99434–1.00529, with mean 1.00039. The image contains directional wave bands and scattered flatter patches. It can provide fine lighting distortion while the water shader supplies movement, reflection, refraction, depth tint and jet-impact ripples. No base-color photo is extracted or proposed for the water surface.

The provider calls the pattern seamless, but opposite-edge RGB mean differences measure 4.64 left/right and 2.51 top/bottom on a 0–255 scale, against an ordinary neighbor difference of 0.34. This is a review limitation. Start with gentle normal strength, test a repeated surface from the player camera, and reject it if a repeat seam or overly regular pattern becomes visible. The file's OpenGL/DirectX orientation is not embedded or independently established; verify the green-channel convention under the intended shader. The provider's [normal-map guide](https://proctexture.com/learn/normal-maps) calls for data-space import rather than sRGB color.

The PNG is a compact download but normally decodes to approximately 4 MiB RGBA8 before mipmaps (about 5.33 MiB with a full chain). GPU compression is not yet produced or validated. Reuse one texture for moving samples rather than allocating independently decoded duplicates. Runtime shimmer, WebGPU/WebGL lighting and actual-phone cost remain unmeasured.

The official [BabylonJS waterbump asset](https://github.com/BabylonJS/Assets/blob/master/textures/waterbump.png) is a small alternative, but the [repository license](https://github.com/BabylonJS/Assets) is CC-BY-4.0 unless a folder says otherwise. It was not silently treated as CC0 or downloaded into this candidate. Poly Haven searches did not establish a dedicated water-normal candidate, and the attempted ambientCG water pages were unavailable. No guessed download was admitted from either catalog.

Hash receipts and measurements are in `planning/evidence/fountain-water-source-20261001.json` and the candidate folder's `source-manifest.json`. Final selection belongs to the in-game fountain review.
