# Xexoria Minotaur / Bovine Shaman — rig v1

Local rig and authored animation package derived from the supplied Tripo character. This is a separate character from Solar Scorpion.

Source: Tripo job `d8cbe7d6-7373-4b69-bfa6-47676945b149`, exported textured GLB. Original 8K source is preserved at `../source/bovine_shaman_p20_smartuv_texture_source.glb`; SHA256 `f517f94f8583eec2851035315f310359087c89b170d406a565b0dbbeafe3cf13`.

## What is included

- `minotaur_rig.blend`: editable fitted Blender Rigify rig, IK legs, IK/FK arms, six robe controls, beard controls and rigid staff control. Blender 5.2.2 LTS; bundled Rigify. The normal trusted Rigify panel is available when that add-on is enabled; model/actions remain usable with auto-execution disabled.
- Eight authored clips at 30fps: **Idle, Walk, Run, Talk, StaffCast, StaffStrike, HitReact, Death**. Walk and Run are in-place; translation is controlled by gameplay. Death releases the staff beside the corpse.
- Three plain JPEG GLBs, plus three optimized KTX2/Meshopt GLBs under `runtime/optimized/`. Runtime exports retain **32 deform joints**; Babylon adds its loader root, reporting 33 bones. Editor control/mechanism bones are omitted from the runtime.
- `review/`: front, side, close, player, stride, cast, strike, death and death midpoint images, plus all-frame motion checks. These are Blender reviews, not screenshots of the MMO.
- Hash manifest, export receipt, optimization receipt, candidate event timings and verified ZIP.

## Runtime use

Use LOD1 at ordinary gameplay distance, LOD0 for close character inspection, and LOD2 for distant characters. These are candidate distance tiers; determine actual thresholds in the scene. All tiers share clip names, proportions and bind skeleton. GLBs use glTF Y-up metres, with the character facing Babylon +Z. Rest-pose model height is approximately 2.4m; the far LOD changes bounds by about 1cm.

| Tier | Triangles | Base color |
|---|---:|---:|
| LOD0 | 54,011 | 4096² |
| LOD1 | 27,005 | 2048² |
| LOD2 | 11,882 | 1024² |

Configure the project's existing local Meshopt/KTX2 decoders before importing optimized GLBs. The plain exports are useful for Blender/interchange and contain embedded JPEGs. Load only one tier per character; do not retain all three by default. Texture compression improves residency; it does not certify crowd/FPS performance.

Review page: run the existing client dev server and open `http://127.0.0.1:5173/minotaur-review.html`. It provides clip selection, pause/frame scrubbing, three camera angles and LOD selection, using ETC1S/Meshopt variants. The 4k UASTC copy is an optional 19.9MB quality reference; ordinary 4k ETC1S is 3.90MB, 2k is 1.59MB and 1k is 0.77MB.

The user subsequently requested a city NPC. `bovine_shaman` is registered as Ruun / City Elder at X20,Z156, facing west beside the southern fountain approach. The client loads one tier on approach, warms shaders before reveal and uses Idle/Talk; the server validates zone, session and 3m interaction distance. Greeting has no quest/reward choices. A generic NPC token cannot accept Sella's quest. Close review camera: `http://127.0.0.1:5173/?cityOverview=1&cityView=npc` (development art preview). This does not qualify the unfinished city/world milestone.

## Validation and quality limits

The original generated source had no skeleton or animation. Its UV seam vertices cannot be trusted as separate physical parts. The rig uses a disposable native voxel remesh surface for Blender bone-heat weighting, followed by native nearest-face interpolation back to the unchanged source mesh. No vertex uses a nearest-bone fallback. Exact audited staff, hands and hoof masks protect rigid shapes; skin weights are normalized with a maximum of four influences.

All eight clips are checked over 538 Blender frame samples. Staff lengths remain rigid; loop endpoints match. Death body and staff finish 1mm /15mm above the floor. Idle/Talk staff motion has up to about 5mm floor contact overlap, suitable for tolerance review rather than claiming perfect physical contact. The imported Babylon validator samples actual weighted-bone motion, checks all clip names, normalized weights and textures, and rejects unrigged or frozen-animation controls.

**This is an authored first animation pass, not final AAA character animation.** Death remains somewhat stiff and the hand keeps the source clenched fingers after releasing the staff. There is no individual finger/facial rig, simulated cloth, ragdoll, spell VFX, sound or collision mesh. Long robe motion uses bounded bone controls. Knees beneath the robe are fitted estimates. Source supplies only base color; normal/metallic/roughness textures were not present, so the package does not invent PBR map provenance. Physical response uses a nonmetallic rough surface.

CPU validation does not prove GPU appearance or phone performance. Browser capture records the observed desktop rendering separately; phone, multiplayer and live game-camera validation remain required before game admission. Source texture/shape is preserved, but automatic generation has already softened some fine embroidery and facial details relative to the supplied images.

## Provenance and rebuild

No new paid Tripo job or provider credit expenditure was used for this local rig/LOD/animation work. Public redistribution rights for this user-supplied generated asset are not independently established; this package is for local project review.

Rebuild scripts in the game workspace: `tools/build_minotaur_rig.py`, `tools/export_minotaur_lods.py`, `tools/review_minotaur_motion.py`, `tools/validate-minotaur-runtime.mjs`, and `tools/package_minotaur_asset.py`. The optimized builder is recorded next to its receipt. Preserve the source hash and source indices when rebuilding part masks; topology-changing edits invalidate those masks.
