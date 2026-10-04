# Building 3D Impostors from Blender for Babylon.js

Research date: 30 September 2026  
Purpose: reproduce the useful idea behind the “6,761 FACES → 1 FACE” demonstration, then evaluate it for a detailed, freely viewed 3D lava game.

## Recommendation

Keep the detailed source models. Use real meshes for characters, walkable structures, and nearby landmarks; evaluate impostors as the last visual LOD for distant static scenery. Start with one isolated rock formation and compare it against an ordinary low-poly mesh before converting a whole region.

The workflow below is an independent implementation plan. It is **not Thomas Murphy’s source code**, a reverse-engineered copy of his commercial add-on, or a claim that a Babylon implementation has already been tested. Code-like sections are implementation sketches unless stated otherwise.

## 1 What the demonstration actually means

The supplied screenshot labels the original toolbox as 6,761 faces and its replacement as one face. The visible surface detail is represented by captured images and a view-dependent shader instead of thousands of mesh faces.

A typical quad is one Blender polygon but becomes two rasterized triangles. It is still drawn in a 3D scene. The shader changes its appearance with the viewing direction so it can suggest a volume. This does not recover arbitrary hidden geometry or make the proxy equivalent to the original at every distance.

The screenshot establishes a geometry reduction in that example. It does **not** establish its GPU frame time, texture memory, shadow cost, correctness from every angle, or the savings in our game. The source mesh may contain mixed polygon types, so do not compare its Blender face count directly with an engine triangle count.

## 2 Verified origin and important corrections

The official Blender recording is [Imposter Syndrome — BCON26, Thomas R Murphy](https://video.blender.org/w/mbVcsaxyYYagE1FdNsGu3T). The conference took place on 23–25 September 2026. The creator’s product is [Imposter Cards by Feral 3D](https://superhivemarket.com/products/imposter-cards-nacho-time); the older name includes “Nacho Time.” The recording metadata and creator documentation were checked; this guide does not claim a complete transcript analysis.

The creator documents six-axis captures, different proxy arrangements, and view-dependent rendering. Current documentation lists one-, three-, and six-plane options, a distance-based switch, and joining proxies. Its quality settings reference multiple textures; a changelog mentions six atlas samples for a single-plane shader. Therefore “one texture sample” is not a safe universal description. One atlas, one bound texture, one sampling instruction, and one draw call are different quantities. See the [product documentation](https://superhivemarket.com/products/imposter-cards-nacho-time/docs).

The product lists Unity, Godot, and UPBGE export. Babylon.js is not a documented export target; parallax slices are described as Blender-only on the current product page. A Babylon port needs its own runtime shader and LOD behavior. This is separate from purchasing the add-on.

“Hungry Packer” and the exact simplified coordinate mathematics in the supplied article were not independently verified. Treat them as unconfirmed implementation details rather than dependencies.

## 3 Choose a representation before writing the shader

| Representation | Geometry | Appropriate first use | Main limitation |
|---|---:|---|---|
| Single fixed billboard | Usually 2 triangles | Very distant decoration seen over a narrow angle | Exposes flatness as the camera moves |
| Multi-view billboard | Usually 2 triangles | Distant rocks and trees viewed from changing directions | View switching, missing perspective depth |
| Crossed or multi-plane proxy | Commonly 6 or 12 triangles | A compromise for some silhouettes and alternate rays | More overdraw; not automatically correct shadows |
| Depth-aware multi-view proxy | Small proxy plus depth sampling | Greater parallax fidelity where it earns its cost | More shader work and difficult depth disocclusions |
| Octahedral impostor | Usually a compact proxy with many capture directions | Broader camera-angle coverage | Atlas memory and blending/reprojection complexity |
| Ordinary low-poly mesh LOD | Asset-dependent | Near/mid scenery, strong parallax, hard-surface objects | More vertices, but can be cheaper in pixels |

Six-axis captures and octahedral sampling are different schemes. Do not use the terms interchangeably. A view-direction atlas is also different from **triplanar material mapping**, which projects textures along axes onto real geometry.

An inspectable open-source reference is [Godot Octahedral Impostors](https://github.com/wojtekpil/Godot-Octahedral-Impostors), which describes a single-plane, multiple-angle approach. Its [MIT license](https://github.com/wojtekpil/Godot-Octahedral-Impostors/blob/v2.0-new-baker/LICENSE) requires retaining the notice in copied substantial code. It is a learning/porting reference, not a Babylon plug-in. Verify the particular files, dependencies, and versions before adopting code.

## 4 Prepare one good source asset in Blender

Start with a **static rock formation**, not the animated lava or the six character classes.

1. Preserve the detailed original in a source collection.
2. Check the mesh from front, back, both sides, above, and below. An incomplete source produces incomplete captures.
3. Work in metres. Establish a stable pivot and bounds. Apply or explicitly account for transforms in a duplicated capture object; do not modify the only source copy.
4. Make the silhouette and secondary fractures good before adding tiny surface noise.
5. Make a conventional mesh LOD too. It is the performance baseline, not a throwaway step.
6. Record source mesh and material hashes so an altered model invalidates its atlas.

Keep collision independent. A render impostor is not a collider and is unrelated to Babylon’s older `PhysicsImpostor` physics API.

## 5 Capture views with a documented coordinate convention

For a six-axis experiment, render along ±X, ±Y and ±Z around the same centre. For an upright object that the player never sees from underneath, an azimuth ring or hemisphere is another prototype option, but it must be named as such, not presented as Murphy’s exact method.

Use orthographic captures initially. Every view must use compatible framing, camera distance, near/far limits, and padding. A shared bounding-sphere diameter gives consistent framing at the expense of empty space; per-view tight bounds are possible only if their projection data is stored and respected.

For each capture store:

- camera position and orthographic scale;
- camera right, up and depth-axis vectors in object space;
- centre and asset bounds;
- image dimensions and atlas rectangle;
- depth encoding and near/far interval;
- whether vertical texture coordinates are flipped;
- colour-space and alpha conventions.

Do not hardcode a presumed Blender-to-Babylon axis flip. Blender authoring is Z-up; glTF is Y-up, and Babylon scenes can use different handedness. Convert positions, camera bases, normals and winding consistently, then verify with an asymmetric test asset carrying a temporary front/right/up marker.

### Capture channels

| Channel | Capture requirement |
|---|---|
| Base colour | Prefer unlit material colour for later relighting; avoid baking a dramatic key light into it |
| Alpha | Silhouette coverage with a clearly documented straight/premultiplied convention |
| Normal | Common object-space normals are convenient across views; encode and decode consistently |
| Depth | Linear depth in a declared capture coordinate system, not a display-tonemapped screenshot |
| Roughness and metallic | Add where relighting quality requires them |
| Emission | Separate from base colour when needed |
| AO | Optional; avoid multiplying the same occlusion contribution several times |

Blender’s compositor Z pass and a custom axial-depth bake are not interchangeable without checking their definitions. For a depth-aware version, define the exact reconstruction equation first and test near/far values on a calibration mesh.

Specify depth storage format, bit depth, scale and offset per view. An ordinary 8-bit channel over a six-metre interval has approximately 2.4 cm quantization steps, which may be too coarse for reprojection. Preserve higher-precision linear intermediates (for example EXR); deliberately choose and test the eventual GPU format or packed encoding. A PNG filename does not guarantee retained precision after browser decoding and texture upload. Do not sample depth through an sRGB conversion, and do not assume colour-style mipmaps are valid depth reductions.

For an initial visual proof, a lit RGBA atlas is simpler. Label it **baked-lighting**, keep scene light conditions consistent, and do not claim dynamic PBR lighting.

Blender’s glTF exporter supports defined PBR material arrangements, not arbitrary executable Blender shader graphs. Baking suitable texture channels and implementing view selection in Babylon are separate steps. See the [Blender glTF material guide](https://docs.blender.org/manual/en/4.0/addons/import_export/scene_gltf2.html).

## 6 Pack the atlas without creating seams

Use a fixed grid for the first implementation. Packing efficiency is less important than proving correct projection.

1. Save captures separately as lossless intermediate files.
2. Place them into a known grid and record rectangles.
3. Dilate valid edge colours into a padding gutter so filtering does not pull unrelated colours into the silhouette.
4. Protect tiles during mipmap generation. A small full-resolution gutter alone cannot prevent cross-tile contamination at every coarse mip.
5. Test normal/depth maps as data, without display gamma or colour grading.
6. Apply suitable runtime compression only after a correct uncompressed baseline. Inspect alpha and normal quality after compression.

Illustrative memory calculation: a 2048×2048 RGBA8 texture is 16 MiB without mips, approximately 21.3 MiB with a complete mip chain. Three such uncompressed textures are about 64 MiB. These are allocation estimates, not download size or a claim about a compressed device format.

Within one atlas, more views mean fewer pixels per view. Do not automatically increase both view count and resolution for every object.

### Suggested manifest

```json
{
  "schema": "visual-impostor-v1",
  "asset": "basalt_cluster_A",
  "units": "metres",
  "captureSpace": "asset-local",
  "sourceHash": "REPLACE_WITH_ACTUAL_HASH",
  "boundsCenter": [0, 0, 0],
  "boundsRadius": 3.0,
  "alphaConvention": "straight",
  "normalSpace": "object",
  "depthEncoding": "linear-capture-axis",
  "views": [],
  "atlases": {
    "colourAlpha": "basalt_A_colour.png",
    "normal": "basalt_A_normal.png",
    "depth": "basalt_A_depth.png"
  }
}
```

The numbers and filenames are illustrative. Fill `views` from the actual capture matrices and record depth sign/range/precision and GPU decoding; `depth.png` is only a placeholder, not a recommendation to use ordinary 8-bit colour depth. An empty view list is not a working asset.

## 7 Build the Babylon prototype in stages

### Stage A one view and a real 3D transform

Render one quad using a custom material and an RGBA image. Put it at the same pivot/scale as the source object. Verify texture orientation, alpha cutoff and silhouette before adding view selection.

### Stage B camera-facing proxy and nearest view

Keep two transforms: the logical asset placement and the camera-facing proxy orientation. Transform the camera using the **logical asset transform**, then subtract the asset centre:

```text
cameraOS = inverse(logicalAssetWorld) * cameraWorldPosition
viewDirectionOS = normalize(cameraOS - captureCenterOS)
chosenView = argmax(dot(viewDirectionOS, captureDirectionOS[i]))
```

Here captureDirection points from the centre towards the capture camera. Use the opposite sign if your manifest defines camera-forward instead. Never feed the billboard's camera-facing rotation back into atlas view selection or the captured object-space normal transform: that rotation is only for displaying the proxy. Test this explicitly rather than fixing mirrored results by trial-and-error flips.

For a single non-instanced prototype, orient the proxy towards the viewing camera. Avoid an unstable cross product when the view aligns with the chosen up axis; select a fallback up vector near the pole. Update its conservative bounds so frustum culling includes the complete apparent object.

### Stage C improve transitions

Nearest-view selection pops at capture boundaries. Blend adjacent views only after each is reprojected into a compatible local surface representation. Naively mixing the same UV location from unrelated views produces ghosted/double silhouettes.

For a very distant baseline, the quality/cost of a discrete atlas can still be acceptable. Test it before implementing the more expensive depth-aware variant. Use premultiplied colour during blending and handle alpha consistently to avoid dark outlines.

### Stage D depth and normals

Depth reprojection conceptually follows:

```text
For each selected capture:
  express a proxy fragment or viewing ray in that capture's basis
  sample capture depth
  reconstruct an approximate source-surface point
  refine projected UV / intersect the reconstructed surface as required
  sample colour, alpha and normal at the corrected position
combine valid samples, rejecting invalid/background samples
```

This is a design sketch, not a complete parallax shader. A reliable implementation must handle holes, occlusion order and pixels revealed between captures. A single depth layer cannot describe every hidden surface.

Decoded object-space normals must be transformed to world space correctly. With nonuniform scaling that requires the appropriate inverse-transpose normal transform, not the position matrix. Start with uniform scale to simplify validation.

If you write reconstructed fragment depth, check the depth convention and every affected pass. Leaving proxy-plane depth can create wrong intersections; writing depth may add cost and complicate early depth rejection. Measure both options.

### Stage E engine integration

Babylon integration needs a shader/material that receives the atlas, capture metadata, asset transform, active camera and any lighting inputs. Implement instanced transforms and per-instance asset metadata deliberately; a single global object transform will not work for thousands of independently placed proxies.

Maintain equivalent alpha silhouette/depth behavior for shadow/depth/reflection passes, or explicitly disable unsupported effects on the far proxy and use an approved fallback. A player-camera-facing card is not automatically correct from a light’s viewpoint.

Relevant engine starting points are [ShaderMaterial](https://doc.babylonjs.com/features/featuresDeepDive/materials/shaders/shaderMaterial/), [instances](https://doc.babylonjs.com/features/featuresDeepDive/mesh/copies/instances), and [mesh LOD](https://doc.babylonjs.com/features/featuresDeepDive/mesh/LOD/). Pin the project’s Babylon version and verify actual API behavior rather than using a moving CDN build.

## 8 LOD switching and spatial batching

Choose transition ranges by projected object size and acceptable visual error, not a universal distance such as “all objects after 50 metres.” A large titan and a small rock need different thresholds.

Add hysteresis: the threshold for switching into an impostor should differ from the threshold for returning to a mesh. If using a cross-fade, budget for both representations during the transition and check overdraw. Screen-door dithering has its own temporal and antialiasing considerations.

Group instances by compatible mesh/material and spatial cell. One shared atlas does not automatically make separate meshes a single draw. Combining a whole world into one giant batch can damage culling and streaming. Shadows, reflections, depth and multiple submeshes can add work beyond the visible colour pass.

Keep separately authored simple collision shapes; disable far decorative collision when the game does not need it. Never use the rotating visual plane as a walkable surface.

## 9 A repeatable performance experiment

Build a small dedicated test scene with the same asset in three modes:

1. original mesh instances;
2. ordinary reduced mesh LOD instances;
3. impostor instances.

Hold camera path, viewport, lights, shadows, resolution, object placement and renderer backend constant. Test 1, 100 and 1,000 placements as experimental workloads, not guaranteed supported counts. Include both sparse and overlapping configurations.

Warm up compilation/loading, then record an identical camera traversal. Capture CPU frame time, GPU time when reliable timer queries are supported, frame-time percentiles, actual draws/passes, texture allocations, download bytes, and visible artifacts. Flag unsupported/disjoint timing readings instead of turning them into benchmark results.

Repeat with shadows disabled/enabled and with a low angle plus a higher camera. Compare WebGL2 and WebGPU only where the target device genuinely supports both. Do not substitute software-renderer numbers for target-phone performance.

Accept the technique only if its visual quality is adequate **and** the measured bottleneck improves. Transparent empty pixels, many atlas samples, memory pressure or poor culling can outweigh saved vertices.

Reddit is useful for finding failure cases, not establishing a universal result. One developer describes [impostor lighting mismatches and worse performance](https://www.reddit.com/r/gamedev/comments/18trui5). Another shares an [Android octahedral-impostor comparison](https://www.reddit.com/r/godot/comments/hciguw). Their assets, hardware and shaders differ from ours.

## 10 Applying this to Titan’s Fall

| Asset or region | Initial treatment |
|---|---|
| Walkable causeway, court, stairs and railings | Real mesh plus collision and ordinary LOD |
| Near titan face, hand and explorable temple | Real geometry; preserve parallax and close silhouette |
| Distant repeated basalt formations | First impostor candidate |
| Far ruin clusters outside the playable route | Candidate after camera-angle and shadow testing |
| Distant caldera skyline | Compare simple mesh backdrop against impostor; mesh may already be cheap enough |
| Flowing lava and falls | Animated surface shader/geometry, not a static capture |
| Playable characters | Skinned meshes and animation LOD; a static impostor cannot reproduce changing poses |

Recommended sequence: finish the current detailed asset forms → preserve source → make one conventional rock LOD → bake the same rock into an atlas → test a Babylon proxy → compare visual/performance evidence → expand only to suitable scenery.

The current detailed Blender draft is not evidence of a working impostor pipeline. Neither a production Babylon impostor nor a target-device speed-up has been established yet.

## 11 Failure checklist

- [ ] Capture pivot, units and view bases agree with the runtime transform
- [ ] Rotating the camera through 360 degrees produces no flips or obvious missing faces
- [ ] Elevated views are covered; below-object views are intentionally supported or excluded
- [ ] Tile gutters and mips do not bleed into neighbouring views
- [ ] Alpha edges avoid dark fringes and uncontrolled overdraw
- [ ] View blending does not double silhouettes
- [ ] Normal maps are decoded in the documented space
- [ ] Colour, depth and shadow passes remain consistent
- [ ] Large-scale/nonuniform transforms are either tested or rejected
- [ ] LOD thresholds do not flicker and transitions are measured
- [ ] Culling uses appropriate bounds and spatial batches
- [ ] Collision and gameplay geometry remain independent
- [ ] Exported triangles, texture memory and actual draws are measured separately
- [ ] Original detailed source and capture metadata are retained

## 12 Sources and evidence boundaries

Primary sources checked:

1. [Official BCON26 recording](https://video.blender.org/w/mbVcsaxyYYagE1FdNsGu3T) and [conference page](https://conference.blender.org/2026/) — provenance, speaker and conference context.
2. [Feral 3D product](https://superhivemarket.com/products/imposter-cards-nacho-time), [documentation](https://superhivemarket.com/products/imposter-cards-nacho-time/docs), [FAQ](https://superhivemarket.com/products/imposter-cards-nacho-time/faq/new) — vendor-described features and limits, not independent benchmark proof.
3. [Godot Octahedral Impostors](https://github.com/wojtekpil/Godot-Octahedral-Impostors) and [license](https://github.com/wojtekpil/Godot-Octahedral-Impostors/blob/v2.0-new-baker/LICENSE) — inspectable alternate implementation.
4. [Blender glTF materials](https://docs.blender.org/manual/en/4.0/addons/import_export/scene_gltf2.html) — distinction between supported export material inputs and arbitrary Blender shaders.
5. [Babylon instances](https://doc.babylonjs.com/features/featuresDeepDive/mesh/copies/instances), [ShaderMaterial](https://doc.babylonjs.com/features/featuresDeepDive/materials/shaders/shaderMaterial/), [LOD](https://doc.babylonjs.com/features/featuresDeepDive/mesh/LOD/) — engine integration entry points. The latter two pages did not expose readable body text to the research fetch, so they are navigation references rather than evidence for an untested exact API signature.
6. [Babylon maintainer discussion of custom shadow-depth shaders](https://forum.babylonjs.com/t/custom-shadows-with-shadowdepthwrapper/9797) — reference when auditing custom-material passes.

The project recipe, proposed data contract, engineering sketches and test plan are recommendations synthesized for this game. They do not establish the private implementation details of the commercial add-on. No commercial add-on was installed or purchased to prepare this guide.
