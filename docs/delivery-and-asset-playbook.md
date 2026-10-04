# Delivery and asset playbook

Status: proposed operating contract; capability observations dated 2026-09-23; production pipeline (§5) added 2026-09-25. This file describes future production steps. No paid generation, cloud scene edit, asset upload, or game deployment was performed while writing the plan.

Current asset continuation (2026-09-30): finish Sunmeadow before the lava region. The user generates new candidates using the [12 standalone English prop prompts](asset-prompts/sunmeadow-props-v1.md). Keep one fantasy style and reusable mesh/material families; Blender handles exact openings and foliage assembly. [LOD/texture research and visual findings](reviews/2026-09-30-assets-lod-texture-research.md) distinguish actual receipts from proposals. [Outdoor streaming and dungeon instances](region-loading-and-dungeons.md) define the delivery design before expansion.

The P2.0 oak's data pipeline passes geometry/compression checks, but its multiangle art review fails. It stays in a development-only comparison; authored trees remain in the normal game. Generated models, high polygon counts and offline renders do not close the Babylon player-camera gate. Four review images and the frozen source manifest live under `assets/models/hero-oak/v1/review/`; no further paid generation was submitted for the user-owned candidate batch.

## 1. Harness working contract

The workspace has a project-pinned Harness runtime initialized from the user-selected local plugin. Start with `.harness/INDEX.md`, `STATE.json`, the active `WORKFLOW.md`, and task-relevant records. Canonical memory is `MEMORY.json`; readable context/preference/decision files are generated views. Planning documents are not a second memory database.

For each implementation slice, record:

1. One observable outcome, in/out scope, input artifacts and known assumptions.
2. Owned files and interfaces, exact versioned dependency/tool documentation, and resource budgets.
3. Focused correctness checks plus only the relevant integration/device/performance checks.
4. A reversible implementation, reviewable diff, evidence location and rollback procedure.
5. One next action. Report limitations instead of treating unavailable tools as passing checks.

Full route applies to networking ownership, economy, schema, external effects and performance claims. A simple isolated UI copy change can use quick. Do not launch seven agents by default. Keep primary model/effort fixed per task; low-risk summarization can use one bounded fast worker. Parallel code writers need separate worktrees, disjoint files and one integration owner; two agents sharing a directory are not isolated writers.

The current planning pass used one read-only source-summary worker. It did not delegate architecture decisions. Future QA should receive artifacts and acceptance criteria in a fresh context; report same-agent inspection as self-review when that is what occurred.

Harness lifecycle for a delivered artifact finishes technical verification at `WAITING_ACCEPTANCE`. Its `DONE` state requires human acceptance. That does not require another permission question before doing already-authorized work. Plans, prototypes, deployment and paid batches remain distinct scopes.

### Durable long-running work

Use one bounded implementation goal per milestone. Before a repeated optimizer, define a real baseline, immutable workload, exact correctness/performance verifier, limited iterations, owned paths, rollback revision, elapsed/call/cost limits and a no-progress stop. Stop after two no-progress cycles or three repeated failures. If the host cannot meter/enforce a budget, label it unavailable and run one supervised iteration.

No automated schedule or unattended development loop was created for this planning task. Do not invent a Git rollback commit: the workspace began as a directory, not a Git repository. Initialize version control deliberately during P0 and reconcile Harness identity through its documented workflow before binding any Git-backed execution contract.

## 2. Jev: two integrations, separate evidence

### Browser research

Use the shipped `jev-browser` runtime in the existing CUA browser session. Supply a public starting URL, observed destination, a bounded goal, one or two directional sentences, same-origin/path scope and a small hop budget. The runtime selects from observed links and checks the destination. Forms require its prepared workflow interface, not guessed link navigation.

Live smoke completed in this session: public TypeSafe introduction → public coding-agent documentation, one selection request, approximately 827 ms runner time. This excludes browser setup, planning and tool handoff. It proves that one navigation worked, not a general latency or task-success guarantee.

Use a configured credential path or ephemeral session handle. Never put credentials in prompts, Markdown artifacts, screenshots, Git, query strings, plan fixtures or telemetry. This session's credential was used in the browser runtime and was not intentionally written into project files.

### Harness context selection

The pinned Harness includes query-time `hide/short/long/full` projection, pinned instructions, tool disclosure and scope/byte limits. Its default is local extractive selection. Optional remote `jev-public` must only receive explicitly public eligible content and public queries, with verified rates and call budgets; private project documents are not automatically public because they sit in a local folder.

Use local projection for the private planning snapshot. Preserve exact source paths/digests in evidence. A selected excerpt does not replace the original file or override instructions. Low-confidence or malformed remote results must not silently authorize tools or switch the primary model. Deterministic code enforces permissions, and the writer owns architecture and security decisions.

Recommended evaluation fixture before relying on remote ranking: 20 public queries with known relevant chunks, including ambiguous names, stale evidence and injected instructions. Compare required-chunk recall, policy failures, context bytes, total task success, elapsed time and provider-reported cost. Never equate fewer serialized bytes with billed-token savings.

## 3. Relevant skills by milestone

Load only the skill that matches the concrete deliverable. Availability does not mean activation, integration, or correctness.

| Capability / skill | Trigger | Expected output |
|---|---|---|
| Harness `best-in-code` | Delivery, review or resume of a defined task | Scope, state, checks, evidence and handoff |
| `engineer-production-systems` | Production architecture or code | Invariants, bounded work, recovery and measurable contracts |
| `context7-mcp` | Current library/API/CLI question | Resolved library ID and focused current docs |
| `jev-browser` | Bounded public research journey or prepared UI workflow | Verified destination/result and limits |
| `impeccable` or `ui-ux-pro-max` | Actual HUD/menu/mobile UX design or review | Input states, readability, accessibility and device checks |
| `game-asset-production` | Asset normalization, Blender/export production | Versioned source, runtime package and quality evidence |
| `game-asset-vendoring` | Admit external/generated packages into the game | Provenance/license decision, integrity and lock receipt |
| `build-3d-game-rooms` | Actual room construction, Meshy props, Boolean openings | Geometry and camera/scale inspection with export gates |
| `game-visual-debugging` | Rendering regression needing more than a screenshot | Reproducible adapter, structured capture and comparison |
| `game-performance-optimization` | Reproducible scenario with a named metric | Comparable baseline/candidate evidence within limits |
| `audit-production-readiness` | Pre-alpha/launch or high-risk release review | Evidence-backed findings and release blockers |
| Higgsfield direct MCP | Model search, constraints, generation or scene operations | Actual model/project/job IDs and artifacts |

The Higgsfield preset skill is for named presets; it is not needed merely because Higgsfield is mentioned. Its hosted website-builder workflow would create a different hosted stack and is not a substitute for this custom Babylon/Rust game repository. Video, YouTube, spreadsheet and document-production skills are not dependencies of an ordinary Markdown game plan.

## 4. Art direction and generation briefs

Visual goal: original stylized anime fantasy, broad readable forms, limited material families, expressive characters and strong combat silhouettes. Preserve exploration and settlement mood without copying named characters or recognizable maps. Mobile readability is a production constraint, not a final optimization pass.

Every brief includes asset ID, gameplay role, physical dimensions, camera distance, silhouette, approved palette/materials, animation/collision requirements, texture/material/triangle targets, rights source, and the maximum spend/attempts for that batch.

Example **proposed** prop brief:

```text
Asset: village_lantern_01
Role: reusable landmark accent, no combat collision
Original stylized fantasy lantern; warm painted wood, pale linen, muted brass.
Show the entire object, isolated against a plain neutral background.
Provide consistent front/side/back proportions; no text, logos, scenery or strong baked shadows.
Physical height: 1.2 m. Clear base pivot. Avoid thin dangling geometry.
Runtime target: <=1,500 triangles at LOD0, 1 material, 512 texture, two cheaper LODs.
Review readability at gameplay distance before approving model production.
```

Separate images/views are preferable when the chosen 3D model expects separate views; a collage is not automatically a multi-view input. AI front/side/back views can contradict one another. Approve silhouette and measurements manually before paying for mesh production.

## 5. Production pipeline by asset type

Budgets per asset class are in [plan v5 §14](browser_ragnarok_babylon_rust_10k_plan_v5.md); this section says how to meet them. Every asset ends in the same checklist (§8) and package (§9).

**Free first:** every step has a free route, and it's the default. Tools that cost money or credits are optional extras that need the owner's approval under the 0 THB rule (plan §14).

### 5.1 Tools and free sources

| Step | Free route (default) | Optional, costs money or credits |
|---|---|---|
| Concept and reference | Sketches, Krita, photos of real objects; front, side and back views plus a palette strip | AI image models through Higgsfield (§5.9) |
| Ready-made assets | CC0 packs: Kenney, Quaternius and KayKit models; Poly Haven and ambientCG textures | None; no asset purchases (plan §14) |
| Modeling, UVs, rigging | Blender, version pinned in each manifest; Remesh and Decimate clean up drafts | — |
| Animation | Blender; Quaternius's Universal Animation Library (CC0, free Standard version); Mixamo (free with an Adobe account, humanoids only) | — |
| Texturing | Blender texture paint, Krita, Material Maker | — |
| Effects | Babylon particle systems with the Node Particle Editor, the Node Material Editor, `TrailMesh`; Blender for flipbooks; Krita; Kenney's CC0 particle textures | — |
| Sound | Kenney's CC0 audio, jsfxr, Freesound filtered to CC0 | — |
| Mesh drafts | Open-source image-to-3D models run locally, only on a capable NVIDIA GPU and after a license check | Meshy or SAM 3D through Higgsfield (§6) |
| Export | Blender glTF exporter (GLB) | — |
| Optimize and check | glTF-Transform CLI, KTX-Software, Khronos glTF Validator | — |
| Runtime check | The game client on WebGPU and forced WebGL2; Babylon Inspector | — |

Read each pack's license file when it's added, even from a CC0 source, and record it (§9). Mixamo clips may ship inside the game but may not be redistributed as raw files.

### 5.2 Rules for every asset

- **Units and axes:** 1 Blender unit is 1 m, Z-up in Blender; the exporter converts to glTF's Y-up. Check each new kit against the [coordinate fixture](../apps/protocol/coordinate-fixture-v1.json) (one-meter cube, capsule, doorway).
- **Pivots:** characters and props at the base center; kit pieces at a grid corner, one convention per kit.
- **Names:** assets `chr_`, `npc_`, `mon_`, `env_`, `prop_`, `itm_` plus a name (`mon_puddlekin`, `env_meadow_wall_2m`); `COL_` for collision proxies, `SOCKET_` for attachment points, `POI_`, `SPAWN_` and `NPC_` for map markers.
- **Topology:** quads and edge loops where the mesh bends (shoulders, elbows, knees, hips); triangles are fine on static props. No hidden interior faces; merge by distance; apply scale before export.
- **UVs and texel density:** one density per class, about 256 px per meter for the environment and 512 for characters (seed values), so no asset looks blurrier than its neighbors.
- **Materials:** glTF metallic-roughness or `KHR_materials_unlit`. One material per character where possible; each biome's kit shares one atlas or trim sheet. Blender-only shader nodes don't export.
- **Palette:** paint or recolor everything to the art bible palette (before it exists, the CC0 family's). A shared palette does more for a professional look than extra detail.
- **Provenance:** record the source, license or generation receipt when the asset is made, not afterwards (§9).

### 5.3 Characters and monsters

1. Brief (§4) and concept: front, side and back at one scale beside a 1 m reference. Approve the silhouette at gameplay distance before modeling.
2. Start from the chosen CC0 family's rigged base when it fits the art bible, or model from scratch. Players and humanoid NPCs share one humanoid skeleton (about 50–70 bones) so every clip works on every body; the CC0 family's skeleton is a sensible first choice.
3. Model the low-poly mesh straight to budget. From an AI draft (§5.9), remesh or retopologize to clean quads, then bake the draft's color onto the new UVs.
4. Unwrap with seams in hidden places; mirror symmetric parts to save texture space.
5. Paint base color in the palette, with a gradient or baked ambient occlusion for form. Add normal maps only for detail the game camera shows.
6. Rig creatures with a small custom skeleton. At most 4 bone influences per vertex. Add `SOCKET_` bones for the weapon hands, head and back. Export deform bones only, and check the hierarchy in the validator and in Babylon.
7. Animate (§5.4).
8. Export, optimize and validate (§5.10), then check in the game at the gameplay camera on the Medium preset and on a phone before admission (§8).

### 5.4 Animation

1. **Sources, cheapest first:** the CC0 library that matches the shared skeleton, then Mixamo for humanoid clips it lacks, then hand-keying in Blender. Creature clips (Puddlekin) are hand-keyed, because libraries rarely fit a creature rig.
2. **Retarget** each library clip onto the shared skeleton in Blender, then fix foot sliding, hand contacts and the weapon grip by hand.
3. **In place, 30 fps:** the server moves characters, so clips carry no root motion. `idle`, `run`, `move`, `guard` and `down` loop; everything else plays once.
4. **Timing matches the game data:** attack clips' windup, active and recovery phases are as long as the content bundle's values. The monster's `windup` lasts as long as its telegraph. Record each attack's impact time in the manifest; the client plays the swing at once and the impact effects on the server's event (plan §10.2).
5. **Game feel:** clear anticipation before an attack, a short sharp contact, and a readable recovery. The game adds hit-stop (60–80 ms) and knockback (plan §10.4); they aren't baked into clips.
6. **Blending:** clips crossfade through Babylon's animation-group blending, about 100–150 ms between locomotion clips and shorter into attacks and dodges, so input feels immediate.
7. **Budget:** only the clips below. Remove tracks for bones that don't move; `meshopt` also compresses animation data (§5.10).

| Rig | Clips |
|---|---|
| Humanoid (players, NPCs) | `idle`, `run`, `attack_1`, `arc_slash`, `dodge`, `guard`, `guard_counter`, `hit`, `down`, `channel`, `interact` |
| Monster (Puddlekin) | `spawn`, `idle`, `move`, `windup`, `active`, `recovery`, `hit`, `stagger`, `death` |

### 5.5 Environment kits and props

1. **Grid:** kit pieces fit a 1 m grid in 2 m and 4 m modules, so walls, floors and fences snap without gaps. Doorways fit the fixture's player capsule with clearance.
2. **Blockout first:** gray pieces with final dimensions and collision, used to build and playtest the zone (§5.6) before any art.
3. **Shared materials:** one atlas or trim sheet per biome, so dozens of pieces share one material and batch into few draw calls.
4. **Collision:** simple `COL_` boxes or cylinders per piece, authored in Blender. The render mesh is never server collision.
5. **LOD:** landmarks and large pieces seen from far get LOD1 (about 50% of the triangles) and LOD2 (about 20%); small props rely on distance culling.
6. **Foliage:** alpha-tested cards from an atlas, never alpha-blended; density follows the graphics preset (plan §11.6).
7. **Props** follow the character steps without rig and animation. AI drafts help most here (§5.9).

### 5.6 Maps (zones)

1. Lay out the route on paper from [catalog §5](system-design-catalog.md): entry → Sella → windmarks → hunt clearing → lookout → return. Size it by walking time at 4.5 m/s and by sightlines from each decision point to the next landmark.
2. Graybox in Blender with blockout pieces at real scale, placed as linked duplicates (collection instances) so each placement stays a reference to one kit piece.
3. Mark gameplay points with empties: `POI_<id>`, `SPAWN_<enemy>_<nn>`, `NPC_<id>`.
4. Export the zone as data, not one merged mesh: a layout (kit asset ID plus position, rotation and scale per placement), world-space colliders from each placement's `COL_` proxies, and the POI and spawn points. A Blender export script, written with the first kit, feeds the content bundle's zone record (catalog §5); today [zones.json](../content/source/zones.json) holds hand-typed POIs. The client draws repeated pieces as instances, and the server loads the same colliders.
5. Keep gameplay on one walkable layer (plan §14): no bridges, overlapping floors or walkable cliffs.
6. Walk it in the game with the real camera and on a phone, then run the catalog §5 acceptance (boundaries, doors, continuous pressure).
7. Art pass: swap blockout pieces for final pieces with the same IDs and footprints, so layout and colliders don't change. Add baked ambient occlusion or vertex color, landmarks and set dressing, and check telegraph readability on every ground material.

### 5.7 Items and icons

1. **Icons:** every item needs one (bag, drops, rewards). Model a simple 3D version, or reuse the drop mesh, and render it with one fixed icon rig in Blender: the same camera angle, lights, outline and transparent background at 256 px, downscaled to 128 px and packed into an atlas. P1 needs three: Trail Potion, Dew Bead and Gale Seed.
2. **Type and rarity** show by frame shape and a small symbol as well as color (plan §14 readability rule).
3. **Ground drops:** a small mesh or icon billboard with the drop sparkle (plan §10.4).
4. **Equipment (P2):** model each weapon or headgear around its socket's origin and axes, share an atlas, and check for clipping on the character in every clip.
5. **Content:** item records gain an `icon` asset ID (and `mesh` for equipment), and the content validator checks that each referenced package was admitted.

### 5.8 Effects

Every combat moment in plan §10.4 gets an effect, a sound and a timing, built in Babylon from free parts:

| Effect | How | Notes |
|---|---|---|
| Telegraph (Splash Hop circle) | Ground decal or flat mesh with a Node Material shader that fills over the windup | Shape, timer and sound, never color alone; drawn from the newest snapshot (plan §10.3) |
| Swing trail | `TrailMesh` following a `SOCKET_` point on the weapon, additive material | Starts with the swing, fades during recovery |
| Hit spark and damage number | Short particle burst; the number as a pooled sprite or DOM element | Waits for the server's event (plan §10.2) |
| Dodge and guard | Brief afterimage or dust puff; a flash on block and a distinct burst on perfect guard | Perfect guard also has its own sound and the "Counter!" prompt |
| Monster defeat and drop | Pop burst, then a drop sparkle | The sparkle loops until the drop is taken |
| Windmark channel | Rising particles during the 1 s channel, a ring burst when it completes | Stops if the channel is interrupted |
| Ambient (dust, leaves, fireflies) | GPU particles | The first thing lower presets cut |

- **Tools:** Babylon particle systems, edited in the Node Particle Editor (a free web tool that also opens from the Inspector); the Node Material Editor for telegraph fills, dissolves and flashes; `TrailMesh` for swing trails. Textures come from Kenney's CC0 particle pack or are painted in Krita; animated flipbooks are rendered in Blender and packed into sprite sheets.
- **Phones:** GPU particles need WebGL2 or WebGPU, and the CPU fallback needs a much smaller capacity. Keep particles small, because overdraw from large translucent quads costs phones more than the particle count does. Pack every effect texture into one shared atlas.
- **Presets:** Low halves particle counts and drops ambient effects; High and Ultra add glow. Telegraphs and hit signals look the same in every preset (plan §11.6).
- **Accessibility:** the reduced shake and flash settings (plan §11.4) turn off screen shake and full-screen flashes; gameplay signals stay.
- **Pooling:** effects are reused and restarted, not created for each hit, so combat doesn't allocate every frame.
- **Budget:** plan §14.

### 5.9 AI generation (free first)

- **Free routes first:** open-source image-to-3D models run locally at no cost if the machine has a capable NVIDIA GPU; check each model's license, because some restrict regions or revenue. Free tiers of hosted tools usually limit licensing (attribution, public outputs), so read the terms before use. Higgsfield credits are the paid route.
- **Good uses:** concept sheets and mood boards, texture ideas, icon drafts, and mesh drafts for props and simple creatures, through a local model or through Meshy or SAM 3D on Higgsfield (§6).
- **Poor uses:** final topology, UVs and rigs; combat characters' skeletons and animation; kit pieces that must snap to the grid; collision; anything that needs exact dimensions.
- **Every output is a draft:** remesh or retopologize, bake to clean UVs, repaint to the palette, set scale and pivot, then the normal export and checks.
- **Original inputs only:** own sketches or own concepts. Never Ragnarok Online's or any other game's images or names, and no "in the style of" prompts (plan §4).
- **Provenance:** record the provider, model and version, prompt, seed, job ID, input and output hashes, and the license terms of the plan tier used. Free tiers can require attribution or make outputs public; admit only terms that allow commercial use.
- **Spend:** generation uses paid credits, so each batch needs the owner's approval under the 0 THB rule (plan §14, §20) and a batch budget (§6). The pipeline works without AI: CC0 plus Blender covers every asset type.

### 5.10 Export and optimization

1. **Blender export:** GLB, selected collection only, modifiers applied, +Y up, deform bones only, actions exported as clips, no cameras or lights (the game sets lighting).
2. **glTF-Transform CLI**, version pinned in the manifest: `dedup`, `prune` and `weld`; `resize` to the class budget; KTX2 textures, `etc1s` for color maps and `uastc` for normal and ORM maps; `meshopt` last; `validate` and `inspect` for the report.
3. **Loading:** `@babylonjs/loaders` pinned to the engine version. Self-host the meshopt and KTX2 decoders instead of Babylon's CDN defaults, so single-origin playtests make no outside requests. Vite `?url` imports emit content-hashed decoder URLs; KTX2 transcoders run in a bounded local worker pool. The client waits for its scene assets, then compiles unique visible material variants in batches of two before starting the render loop. See `apps/client/src/asset-codecs.ts`, `apps/client/src/ktx2decoder.worker.ts` and `apps/client/src/scene.ts`.
4. **Low preset:** if it needs smaller textures, generate a half-size set with `resize` at build time.

The first measured runtime package is the CC0 Quaternius Warrior. Its original glTF and license remain under `assets/characters/quaternius-rpg/`; `npm run assets:warrior` converts color maps to ETC1S first, then applies Meshopt last so the final GLB retains both `KHR_texture_basisu` and `EXT_meshopt_compression`. All 13 animation clips remain. Exact tool versions, source/output hashes and sizes are in `assets/characters/quaternius-rpg/runtime-manifest.json`. Local Node Brotli-q6 estimate: model 1,242,925 → 442,236 bytes; the cold model plus its required decoder resources is about 683,469 bytes. These numbers exclude the application bundle and other world assets, and are not a Vercel transfer capture or a mobile FPS/RAM measurement. `apps/client/vercel.json` gives `/assets/*` a one-year immutable cache policy, and client-loaded static models and decoder resources use Vite content-hashed URLs.

Code-generated ground and water textures in this client are drawn once while the scene initializes; they are not redrawn every frame. Keep those procedural textures until profiling or a device memory budget demonstrates a reason to replace them. Asset files and code are complementary choices, not a universal rule that one always runs faster.

For this scene, the six dynamic textures are one 16×256, three 256×256 and two 512×512 base levels. At RGBA8 this is about 2.77 MiB before driver overhead, with mipmaps disabled. That is an estimate from the current sizes, not a device memory capture; replacing them with KTX2 has no measured payoff yet.

### 5.11 What makes it look professional

- **One style, strictly applied:** palette, proportions, edge softness and texel density agree across every asset. Consistency reads as quality more than polygon count does.
- **Silhouette test:** filled black at gameplay distance, every character, monster and landmark is still recognizable.
- **Value test:** in grayscale, characters and telegraphs stand out from the ground.
- **Light and color:** one directional light plus ambient, baked ambient occlusion on the environment, and a color grade on High and Ultra.
- **Motion and effects:** anticipation and follow-through (§5.4) and crisp hit effects (§5.8) matter more than mesh detail.
- **Review in context:** every asset at the game camera beside the reference crop and the CC0 baseline, on a phone at the Medium preset, before admission.

## 6. Higgsfield MCP production sequence

Observed catalog candidates include Meshy `image_to_3d`, `multi_image_to_3d`, and Meta `sam_3_3d`. The recommendation query returned cinematic image candidates; this is retrieval output, not proof of suitability for game assets. Run a small acceptance comparison rather than selecting a model by name alone.

1. Resolve/recheck the model's live constraints through `models_search` and `models_get`. Verify input media roles, output type, parameters, supported views and actual callable generation route.
2. Estimate the exact request with the appropriate supported estimate tool. If a 3D cost cannot be estimated through an available route, obtain a concrete quote before submitting. Do not substitute image/video pricing for 3D work.
3. Apply the approved batch budget: cost ceiling, number of candidates, retry limit, required deliverables. A reasonable first proposal is three prop candidates and at most two mesh attempts for the selected prop; this is not spending authorization from the current planning request.
4. Upload only the chosen authorized input files using the supported media flow. Record provider IDs and hashes; do not put expiring URLs into permanent manifests.
5. Submit once; persist the returned job ID before polling. After a timeout, query that job rather than issuing an uncertain duplicate charge. A new attempt gets its own ID and explicit budget accounting.
6. Inspect candidates, choose one on silhouette/topology/cleanup effort, retain provenance and download only through the supported artifact path.
7. Normalize in Blender and run the acceptance checks below. Reject assets that fail the game budget even if the provider labels them complete.

Generated topology, auto-rigging, UVs and PBR maps are candidates requiring QA. Humanoid auto-rigging is not a reliable substitute for creature rigs or combat animation design. Provider seeds assist reproducibility but do not guarantee identical regeneration across model versions.

## 7. Blender MCP and 3D Jutsu integration

Two routes must remain distinct:

| Route | Current evidence | Appropriate role |
|---|---|---|
| Dedicated Blender MCP attached to a local Blender session | No callable tool found in this session; `blender` also not on shell PATH | Future local authoring adapter once connected and probed; not tested here |
| Higgsfield Blender-backed 3D Jutsu tools | Tool contracts exposed and authenticated project listing succeeded; list empty | Remote scene inspection/edit workflow once a project is deliberately created/selected |

No local connector was installed and no cloud scene was created merely to claim Blender use. A Blender installation may exist outside PATH; that was not exhaustively searched. The first production task should resolve the desired route before authoring files.

### Remote 3D Jutsu procedure

Use project listing or an explicitly created project ID. Read the project revision/scene sequence and settle any active operation. Run `scene_builder_3d_query_python` to inspect actual objects, dimensions, transforms, collections, materials, cameras and Blender RNA. It is inspection; temporary changes are discarded.

For a coherent edit use `scene_builder_3d_run_python` with the exact returned revision and scene-sequence guards, a stable operation ID and a bounded code change. Reuse that ID only for the identical request. A stale revision means inspect again, not overwrite blindly. Poll the specific operation to a terminal result before another mutation.

Catalog assets enter through `scene_builder_3d_search_assets` then `scene_builder_3d_import_asset`. The exposed Python contract forbids downloading arbitrary model URLs or embedding model bytes. Therefore **do not assume a generated Meshy GLB can automatically be imported into remote 3D Jutsu**. Use a verified supported import path or the local Blender route for arbitrary authorized GLBs; treat this gap as an integration task.

After editing, inspect geometry and render evidence, resolve committed `.blend`/GLB artifacts, then call `scene_builder_3d_show_scene` once as the final scene tool using the actual committed revision. Save artifact IDs, revisions and file hashes. Scene preview demonstrates appearance, not game runtime performance.

### Local Blender procedure once available

Read-only handshake first: report Blender version, active file path, scene units, object count and connector version. Use an isolated source copy or new task file. Run a small deterministic script against the intended file, save an explicit revision, render/inspect, export, and verify in Babylon. Never assume an MCP Python execution tool is limited to harmless mesh operations; scripts have a narrow file/network scope and reviewed inputs.

## 8. Asset acceptance checklist

| Area | Required evidence |
|---|---|
| Provenance | Source/license or generation receipt; approved use; input/output hashes; no unexplained copied asset |
| Geometry | Finite bounds, intended scale, sensible pivot, no unintended isolated pieces, normals/UVs, exported vertex count |
| Topology | Budgeted triangles/vertices after export; no accidental interior geometry; necessary manifold/collision checks |
| Materials | Approved PBR/unlit subset, material count, texture dimensions/alpha, correct color spaces |
| Rig | Expected skeleton, bone budget, weights, no extreme deformations, agreed root motion, attachment sockets |
| Animation | Required clip names/durations/loops; attack event alignment; idle/move/turn/death transitions |
| LOD | Actual authored/reduced variants, distance transitions, silhouette retention, no giant texture residency |
| Collision | Separate simplified collider, coordinate conversion, capsule clearance, doors/stairs/slopes |
| Packaging | Versioned GLB, texture references, manifest, collision/navmesh outputs, bounded sizes, reproducible commands |
| Runtime | Babylon import on WebGPU and WebGL2, material/clip verification, real-phone capture and memory check |

Blender's glTF path supports mesh/material/skin/animation export but not every Blender behavior. Bake necessary behavior into supported data; arbitrary shader graphs, physics and material/light animation are not automatically a portable game implementation. [Blender glTF export](https://docs.blender.org/manual/en/latest/addons/scene_gltf2.html)

Canonical authored space: meters, Blender Z-up. Export conversion to runtime glTF coordinates is explicit; client/server loaders must agree on handedness, winding, origins and collision transforms. The first fixture includes a one-meter cube, doorway, slope, marker axes and spawn. Verify them in Blender, Babylon and server collision before constructing a whole town.

Do not validate collision merely by looking at a rendered doorway. Walk the server-authoritative capsule through it, test camera collision from both sides, and verify navmesh connectivity. The source scene, visual export and collider/navmesh hashes travel together.

## 9. Versioned handoff package

Each accepted asset package includes:

```text
<asset-id>/<revision>/
  manifest.json
  model.glb
  textures/                  if external textures are used
  collision.json             or a versioned supported collider format
  previews/                  front, side, game-camera views
  provenance.json            provider/job/version, source license and hashes
  validation.json            geometry, rig, export and runtime results
```

Editable `.blend` masters live separately with revision identity. Large binaries use suitable artifact/LFS storage after repository policy is chosen. Catalog only admitted packages. Reject missing provenance, mismatched collision hashes, external arbitrary URLs and unsupported extensions before a package reaches CDN publication.

Track cost per **accepted** asset: generation attempts + download/processing + artist cleanup + retopology/rig fixes + review. Use manual modular modeling when it wins on reuse and predictability. Reserve generated detail for assets that benefit from it.

## 10. Project example: reference city r1

The user-selected image in `docs/ui/ChatGPT Image Sep 27, 2026, 08_38_17 PM-1.png`
informs the layout only; the exported model does not contain its pixels. The
Blender master at `assets/models/reference-city/r1/reference_city.blend` keeps
the authored pieces separate. `assets/blender/build_reference_city.py` builds
the gate, bridge, market street, fountain plaza, timber shops, observatory,
windmill, garden and castle from original geometry and PBR materials. Rebuild
and pack with `npm --prefix apps/client run assets:city`.

Blender 5.2.2 exports a 5,284,080-byte source GLB with 73,996 triangles and 17
material groups. glTF Transform 4.5.0 Meshopt produces the 1,677,480-byte
runtime GLB at `apps/client/src/assets/models/env_reference_city.glb`;
Khronos validation reported no errors or warnings. The all-mesh attribute
check requires matching POSITION, NORMAL and TEXCOORD_0 data so Babylon can
merge the static import. No textures are used.

The asset is scenic at world Z≈62, outside the server zone's ±28 m limit.
Visual import evidence does not close server collision, navmesh, mobile-memory,
or phone-FPS acceptance; those require separate gameplay and device evidence.
See [E08 city visual r1 receipt](../planning/evidence/e08-city-visual-r1.json).

### Current city iteration: r3

The r1 source remains preserved. R3 is the current authored model and fixes an
out-of-range vertex-index error in the lower cliff mesh, lowers the entrance
wall to reveal the inner roofs, and adds locally generated repeatable PBR color
and normal maps for stone, plaster, wood, roof palettes, cobblestone, grass and
water. The development-only Blender review scene uses separate meadow, trail,
tree and ridge meshes to frame the arrival; those presentation objects are not
included in the runtime city GLB.

The normal meadow preview also extends its dirt trail behind the spawn/camera,
so the near edge no longer opens as a sharp wedge beneath the character.

- Master/source: `assets/models/reference-city/r3/reference_city.blend` and
  `assets/blender/build_reference_city_r3.py`.
- Texture source: `assets/blender/generate_reference_city_textures_r3.py`; all
  resulting PNG maps are persisted under
  `assets/models/reference-city/r3/textures/` and packed into the master/GLB.
- Rebuild: `npm --prefix apps/client run assets:city`. The revision-specific
  r1/r2 recipes remain available.
- Receipt: 134,504 triangles, 21 material groups, 24 embedded PNG textures,
  10,673,244-byte source GLB and 4,676,836-byte Meshopt runtime GLB.
- Validation: the build and `gltf-transform validate` report no errors. The
  validator still reports unused UV attributes on untextured groups; repeated
  UVs outside 0..1 are intentionally left unquantized. Geometry is Meshopt
  compressed, but KTX2 texture compression is not applied to this city asset.

R3 visibly improves the local overview and normal offline game preview, but it
does not match the supplied image's visual quality. It remains scenic at world
Z≈62 m; the server zone is ±28 m. City collision, navigation, a continuous
field-to-city route, real-phone budgets and style/detail parity remain open.
See [E08 city visual r3 receipt](../planning/evidence/e08-city-visual-r3.json).
