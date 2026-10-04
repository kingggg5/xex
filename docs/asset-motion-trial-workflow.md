# Offline asset and motion trial workflow

The reusable checks are ready. Pixel Match's controlled CPU fixture passes; a
UniMate warrior trial is prepared for later execution. No models were downloaded,
no dependencies installed, and no canonical character, rig or game file changed.

## Reproduce the checks

Run from the repository root with the existing Python environment:

```powershell
python -B tools/local-ai-asset-preflight.py
python -B tools/pixel-match-probe.py
python -B tools/local-ai-asset-preflight.py --warrior-only
python -B -m unittest discover -s tests/local_ai_asset_tools -v
```

Both tools emit JSON to stdout. They do not create directories or receipts;
redirect stdout to a chosen trial directory when a saved run record is needed.
`--no-gpu-query` skips the preflight's five-second, read-only `nvidia-smi` query.
`--root` can inspect another checkout with the same audited pins. The probe's
`--source` can select another copy of the **exact** audited `photo_paint.py`.
Changed source is rejected before execution. Exit 2 means an integrity/input/
dependency error; probe exit 1 means the expected fixture behavior changed.
Preflight exit 0 means inspection completed, and does not imply inference ready.

Preflight imports standard-library modules only. It reports installed package
metadata without importing PyTorch or starting model runtimes. Anchored receipt
hashes verify the cached source files and declared license files. The cache is a
review snapshot, not a runnable installation. Two image-to-3dlab entries were
already unavailable in the review receipt and remain identified as unavailable.
No secrets or full environment values are enumerated, and no environment variable
is changed. Distribution metadata is a dependency inventory, not a complete
compatibility test. The pinned Blender bridge also remains untested.

The probe executes only SHA-verified standalone Pixel Match code. It uses a
64×64 synthetic RGBA coordinate grid, an aligned camera and 2/5,000-triangle
planes. Both runs reproduce all 4,096 texels with zero RGB error and the same
output SHA-256:
`74bc1f394723a260d6a8501fc2c499bc515588a915205c8ef01cfb5349d72f22`.
The slanted overlap also reproduces the known failure: affine front depth
1.6667 selects the rear triangle at 1.6 although the correct perspective front
depth is 1.5. The source is not patched. This is a projection control, not proof
of arbitrary camera accuracy, generated geometry quality or a game-ready asset.
The existing dated CPU receipt remains under
`planning/evidence/pixel-match-cpu-probe-20261001.json`.

## Warrior input readiness

The checked receipt is
`planning/evidence/warrior-motion-readiness-20261001.json`. Inspection reads the
licensed native `assets/characters/quaternius-rpg/Warrior.gltf` for actual channel
values and the existing compressed runtime GLB for primitive/skin/clip metadata.
No compressed runtime accessor data is decoded or rewritten.

- License: CC0-1.0; source and included license hashes verified.
- Skeleton: 32 skin joints, one `Root` under `CharacterArmature`.
- Mesh: five primitives, 5,402 source triangles, two materials. Only the body is
  skinned. Face → `Head`, shoulder pads → `UpperArm.L/R`, sword → `Weapon.R` are
  separate bone-parented attachments; verify all four survive any future export.
- All 13 native clips remain named in the runtime GLB. Selected trial input:
  `Idle_Weapon`, 3.125 seconds, 96 channels, finite channel values with consistent
  shapes, sampled at 24 fps. Its local root translation is constant. This does not
  establish world-space foot contact or animation quality.
- Generic v2's model card accepts 5–70 joints. Its resolved checkpoint config has
  padding width 71; retain the model config rather than replacing that width with
  the character's 32 joints. The 22-joint Mixamo checkpoint is a different route.
- **Resample to 30 fps before feature extraction.** Merely relabeling 24 fps as
  30 changes timing and per-frame motion scale. The inspected feature loader
  halves high-rate clips; it does not upsample this 24 fps source. Verify the
  Blender export's 30 fps bake and resulting feature `fps=30` explicitly.

This is a structural candidate. Stock sampling requires a valid clip and a
dataset conditioning entry, while the official new/OOD-rig workflow is still
forthcoming at the audited pin. No conditioning was created here. The preflight
found `transformers`, `tyro`, `loguru` and `torchdiffeq` absent in the inspected
environment. These are a partial inventory, not the full dependency list.

## One-character trial manifest for later use

Save a manifest like this in an isolated experiment folder only after preparing
the complete pinned environment and reviewing acquisitions. This is a manifest
template and execution contract, not an executable installer or launcher:

```json
{
  "schema": "xexoria.unimate-one-character-trial/1",
  "status": "prepared_only_not_executed",
  "source_commit": "2c5b384715aa63d8639b1ed7eb74bfe614570c7a",
  "model_revision": "92710b30abc0a7708c9f280f38fd7e65448c4f95",
  "model": "unimate_uniml3d_f60_v2",
  "character": "Quaternius_Warrior",
  "source_license": "CC0-1.0",
  "source_sha256": "2bab905ce12d279e1d099c2a8de0b1ef31c9f5e8d1959b41d24470b4f4181add",
  "input_clip": "Idle_Weapon",
  "character_count": 1,
  "clip_count": 1,
  "resample_fps": 30,
  "sampling.device": "cpu",
  "CUDA_VISIBLE_DEVICES": "",
  "HF_HUB_OFFLINE": "1",
  "TRANSFORMERS_OFFLINE": "1",
  "batch_size": 1,
  "num_repetitions": 1,
  "only_save_motion": true,
  "seed": 10,
  "generation_frames": 60,
  "prompt": "An object stands ready while breathing gently, with feet planted.",
  "output_directory": "planning/trials/warrior-unimate-20261001/output",
  "canonical_game_files_mutable": false,
  "root_policy": "preserve original input; inspect generated displacement before any in-place bake",
  "source_and_model_licenses_checked": false,
  "weight_hashes_recorded": false,
  "conditioning_and_30fps_features_verified": false
}
```

Keep the original source/rig/license intact. Any future preprocessing or
canonicalization must operate on an isolated copy. Inspect its complete joint
mapping, facing pair (`UpperLeg.L/R`, after verifying source names), bind pose,
skin weights and all bone-parented attachments. Do not accept automatic bone
pruning/merging without reviewing its effect. Stop if exact preservation cannot
be demonstrated; this task did not authorize rig edits.

The checkpoint is 1,185,827,848 bytes and FLAN-T5-base weights add 990,345,061 bytes:
about **2.03 GiB of weights**, excluding tokenizer/config/statistics, the Python
environment, intermediates and runtime memory. Use checkpoint config and saved
normalization statistics from that same revision. Record hashes of every acquired
file before use. Do not download the 57.8 GB dataset for one character.

When the conditioning path is implemented and verified, the pinned sampler's
relevant options are `--batch_size 1`, `--num_repetitions 1`, a fixed `--seed` and
`--only_save_motion`. `sampling.device=cpu` belongs in an isolated copy of the
model config. Hide CUDA in the **trial child process** as well: the dataset text
encoder independently selects CUDA. With required weights already local, offline
Hub flags prevent a surprise first-use fetch. Record wall time, peak RAM, finite
output values, shape `(60, J, 12)` and resolved configuration. CPU speed and memory
fit are unverified on this 15.84 GiB RAM host. The GTX 1050 has 2,048 MiB VRAM and
driver 560.94; Pixal3D generation remains blocked. A driver upgrade alone would
not validate this GPU's memory capacity.

Before a future GLB is admitted, inspect foot planting and sliding, knee/elbow
deformation, hand grip and sword arcs, first/last pose continuity, root displacement
and any in-place conversion. Compare the joint names/count, skin and attachment
hierarchy, materials and scale against the original. Align visible attack timing
with server-authoritative hit windows; generated root motion must not take over
server movement. Existing runtime clips are the baseline. This workflow does not
grant an asset an automatic production or game-ready status.
