"""Expand the user's master template into copy-ready, standalone prop prompts."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
briefs = json.loads((root / "planning/asset-production/sunmeadow-prop-briefs-v1.json").read_text(encoding="utf-8"))
body = """Design a visually polished, believable asset with a strong silhouette, accurate proportions, clean primary forms, and carefully selected secondary details. Make the object recognizable at typical gameplay distance. Concentrate detail on functional features and visible edges. Keep broad surfaces clean and avoid unnecessary geometric complexity.

Use plausible construction. Give structural parts convincing thickness. Keep functional gaps and openings clearly visible. Avoid fragile protrusions, dense wires, tangled chains, excessive bolts, and arbitrary decorative greebles unless they are essential to this prop's identity. Represent fine scratches, subtle grain, and shallow surface wear as material detail rather than raised geometry.

Show exactly one complete object in a front three-quarter view, with a small amount of the top visible and minimal perspective distortion. Center it at approximately 80% of the image area, leaving clear margins. Nothing cropped or hidden behind another object.

Use soft, neutral, diffuse lighting with enough gentle shading to explain the form. Preserve readable colors and material boundaries. Avoid strong cast shadows, crushed blacks, blown highlights, mirror-like reflections, dramatic rim lighting, bloom, and depth of field.

Use a plain light-gray background. No environment, floor texture, pedestal, characters, extra props, labels, text, watermark, wireframe overlay, or multi-view collage.

Deliver one crisp, coherent reconstruction reference. Prioritize clear geometry, strong art direction, and restrained material detail suitable for a reusable real-time game asset."""
output = ["# Sunmeadow: 12 prop reference prompts", "",
    "Generation owner: you. These are candidate references, not approved runtime models. Finish Sunmeadow before the lava region.", "",
    "Generate SM01, SM03 and SM04 first. SM02 is a foliage-art reference. Review those before making the entire batch. No extra paid Tripo jobs were submitted for this pack.", "",
    "For items marked reference/Blender, use the image for form and materials; skip the Tripo conversion. The shared template names the downstream workflow but does not imply every prop should use it.", "",
    "## Shared art direction", "", briefs["shared_style"], "",
    "## How to return candidates", "",
    "Use IDs such as SM01-oak-trunk-A and SM01-oak-trunk-B. Keep the source image, prompt and provider settings. If you generate a model, preserve its original GLB/FBX and texture maps, including commercial-use provenance. Send the source versions; runtime compression and LOD will follow inspection. Front, side and close views help reject malformed parts early.", "",
    "A prompt does not guarantee topology, exact component count, openings, UV quality, material slots, triangles or browser performance. Don't approve a 3D result from one thumbnail. Proposed budgets below need calibration in the actual player scene.", ""]
for item in briefs["items"]:
    prompt = "\n".join([
        "Create ONE isolated game-prop reference image for an image-to-3D workflow using Tripo P2.0. The resulting asset will be used in a high-quality Babylon.js browser game with many props visible at once.",
        f"PROP: {item['name']}", f"DIMENSIONS: {item['dimensions']}",
        f"CONSTRUCTION: {item['construction']}", f"MATERIALS: {item['materials']}",
        f"ART DIRECTION: {briefs['shared_style']}", "", body])
    item["complete_prompt"] = prompt
    output.extend([f"## {item['id']} — {item['name']}", "",
        f"Method: {item['method']}. Family: {item['family']}.", "",
        item["reuse"], "", item["runtime_target"], "", "```text", prompt, "```", ""])
folder = root / "docs/asset-prompts"
folder.mkdir(parents=True, exist_ok=True)
(folder / "sunmeadow-props-v1.md").write_text("\n".join(output), encoding="utf-8")
(root / "planning/asset-production/sunmeadow-prop-prompts-v1.json").write_text(json.dumps(briefs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": "PASS", "standalone_prompts": len(briefs["items"]), "generation_owner": "user"}))
