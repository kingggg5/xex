# Xexoria: local image-to-3D and animation tools

Reviewed 2026-10-01 against pinned upstream code. This is an adoption decision and bounded CPU verification, not proof of generated game-ready characters.

## Decision

Use `image-to-3dlab` Pixel Match as an optional **offline static-prop texture projection** experiment. It can preserve source lettering on visible surfaces with a known camera and compatible UVs. Preserve authoritative logos as separate textures/decals when practical.

Evaluate **UniMate generic v2** later on one existing licensed, rigged character with one valid animation clip. Use it offline to produce baked animation; Babylon plays the exported GLB. Runtime gameplay movement and hit timing remain server controlled.

Continue Sunmeadow composition and asset optimization independently of these AI experiments. No inference weights, installers, driver changes or production animation packages were installed during this review.

## Hardware actually observed

- Windows host: NVIDIA GeForce GTX 1050, **2048 MiB VRAM**, driver **560.94**; system RAM **15.8 GiB**.
- Blender 5.2.2 and existing NumPy 2.4.4 / Pillow 12.2.0 support a bounded CPU postprocessing test.
- The image-to-3dlab Windows Pixal3D prebuilt requires driver >=575 / CUDA support >=12.9. Its author's successful generation examples use substantially larger GPUs. Do not treat a driver upgrade as sufficient to make a 2 GiB GPU suitable.
- UniMate has inspected CPU paths but no verified speed or minimum-memory guarantee on this machine. Its dataset text encoder chooses CUDA independently, so a CPU experiment must hide CUDA as well as selecting `sampling.device=cpu`.

## image-to-3dlab

- Repository: https://github.com/Bingeljell/image-to-3dlab
- Pin: `5ed8e9850d23515c424abc62fbca498e6da52f27` (2026-09-30, release 0.3.6).
- Own code: Apache-2.0. Each inference backend and image encoder has its own license. This is not a blanket commercial license for every model route.
- Pixel Match is implemented in `image_to_3dlab/photo_paint.py`: photo/camera projection, visibility depth buffer, facing/matte/edge weights, bilinear sampling and blending into UV texels. Unseen surfaces do not obtain missing source detail; default palette matching can also alter their existing paint.
- Automatic camera lookup uses a matching Pixal3D generation sidecar, not general camera calibration of arbitrary imported meshes.
- The provided GLB path accepts one primitive/material, UV0, indexed triangles and an embedded base-colour image; node transforms and interleaved buffers are refused. It is unsuitable as-is for the merged 45-material city or a finished skinned character.
- Finish defaults to 40k faces. QuadriFlow face counts and decimation triangle targets are different; inspect the actual exported triangle count. Voxel remeshing can remove detail and data layers. The pipeline does not itself prove deformation-ready edge flow or skin-weight transfer.
- Default compression downsizes/re-encodes textures and can soften lettering. JPEG file compression does not establish GPU block compression; retain the game's KTX2 delivery path.

### Executed CPU evidence

`planning/evidence/pixel-match-cpu-probe-20261001.json` records the actual pinned library run with a synthetic RGBA coordinate grid, a manually aligned camera and a planar UV surface. No user artwork or game asset was modified.

- The 2-triangle and 5,000-triangle fixtures both reproduced all 4,096 tested source texels with zero RGB error and identical outputs, using `match_colour=false`, a one-pixel edge setting and no gutters.
- This did **not** run image-to-3D inference or retopology, and does not establish correctness for arbitrary cameras or surfaces.
- A slanted-overlap fixture reproduced an occlusion limitation: screen-space affine depth selected the hidden triangle at depth 1.6 instead of the visible perspective depth 1.5. Do not advertise universal pixel-perfect preservation. Upstream source was not patched.

## UniMate

- Repository: https://github.com/Friedrich-M/UniMate
- Pin: `2c5b384715aa63d8639b1ed7eb74bfe614570c7a`.
- Checkpoints: https://huggingface.co/Linzhan/UniMate/tree/92710b30abc0a7708c9f280f38fd7e65448c4f95
- Code and published checkpoints carry MIT. Dataset assets retain their individual licenses; the dataset is not a uniform free production-asset pack.
- Generic v2 checkpoint: 1,185,827,848 bytes (~1.10 GiB); FLAN-T5-base adds 990,345,061 bytes (~0.92 GiB). Environment/cache and character inputs are additional. There is no reason to download the complete 57.8 GB dataset for a single-character experiment.
- UniMate generates motion for an existing skeleton. It does not construct the mesh, rig or skin weights. Stock inference requires at least one valid animation clip despite a rest-only preprocessing fallback. The official new/OOD rig pipeline is still marked forthcoming in the inspected README.
- Generic v2 is distinct from the specialized 22-joint Mixamo checkpoint. Bone naming, skeleton size and 30 fps canonicalization must be verified.
- GLB/FBX export is implemented through a Blender bridge. Missing animation bones can be skipped and extra bones can be merged into ancestors, so preserving finger, cloth, weapon and facial bones needs explicit checks.
- Sliding and coarse spatial control remain documented limitations. Inspect feet/contact, weapon arcs, return-to-ready pose, root displacement and server hit timing before admission.

## Compact-region production rule

The user's current direction is compact adventures with dense detail at focal points. Keep two combat clearings, shorten empty connectors and use curved approaches/terrain silhouettes to separate sightlines. Preserve metre scale and player clearance; changing an object's visual scale alone does not reduce its geometry cost.

Near-player assets receive the detail budget. Distant mountain, temple and forest silhouettes use LOD/HLOD and independently streamed packages. Limit simultaneous shadows, particles and active encounters. Sunmeadow remains first; lava follows it. City blueprint placement and terrace traversal still require native gameplay validation, including authoritative height support.

## Evidence boundaries

Source review and a synthetic CPU projection test are complete. Full local 3D inference, UniMate motion generation, character rigging, retopology, GPU artifact import and iPhone performance have not been verified by this review. Context7 returned unrelated projects for both exact repositories; no APIs from those unrelated matches were used.

Raw source snapshots, commit pins and file hashes live under `.harness/.cache/ai-tool-review/`. They are review inputs, not installed runtime dependencies.
