# Guardian + selected Forge R03 — review candidate

Runtime `city-runtime.meshopt.glb`: SHA256 `a8a8182e83a4ba6deefa38f223e3709a198770eef1981f33870b22b8d5d8cc7b`; 84,376,108 bytes; 915,073 triangles. **Not admitted. The 900,000 triangle gate still fails by 15,073; no waiver or default change.**

Geometry donor is immutable `../fountain-guardian-review-v2-candidate/city-runtime.meshopt.glb`, SHA256 `8e7668042f044ff175a2d2d3fc45cfedc1eb4fdd6c058be7150271d862d02f05`. It contains the existing guardian gown/sculpt and prior outlet/lamp repairs. Its receipts establish a geometry review candidate, not native art acceptance. This revision does not alter any donor geometry, UVs, normals, vertex colours, indices, material parameters, nodes, hooks, samplers or texture transforms.

Only `stone_wall_warm`, `stone_foundation`, `stone_trim_carved`, `stone_accent_bluegrey` and `plaster_cream` reuse their three existing encoded maps from immutable `../forge-r6-texture-review-candidate/city-runtime.meshopt.glb`, SHA256 `93910787c74e3655f40df4c8fb73630503d67e540d7fe98286febd0a1907fb61`. All 15 payloads match the Forge receipt. The other 39 maps, including roofs, paving, timber, grass and cliffs, remain exact donor bytes.

Contract: 1024×1024, 11 mips; sRGB albedo; linear OpenGL +Y normals; linear ORM channels AO/roughness/metal. No encoding, resize, normal flip, UV-repeat adjustment or tint correction. Existing material factors and vertex colours still multiply the maps. Correct hardware sRGB decoding may report `gammaSpace=false`; this package adds no texture loading code.

The packer `tools/city-quality-20261005/pack-guardian-selected-forge.mjs` copies the donor geometry tail and relocates physical container offsets. It proves normalized GLB metadata equality, every compressed stream, all 250 decoded logical views covering 297 accessors, and every image payload. Four focused synthetic guard tests passed. Observed own-process RSS was 463.215 MiB; this is a sampled CPU measurement, not GPU memory or whole-system RAM.

Active revision/runtime and authoritative traversal remain untouched. Parent owns DEV selection and matched native bridge/player/plaza/close review. No renderer, visual, performance or phone acceptance is established here.
