"""Recover image-generation arguments only; never copy the surrounding chat."""
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
transcript = Path.home() / ".codex/sessions/2026/09/23/rollout-2026-09-23T15-20-21-01a0cd59-fa34-7332-bca0-6daa82d305d1.jsonl"
calls = []
for line in transcript.open(encoding="utf-8"):
    row = json.loads(line)
    payload = row.get("payload", {})
    if row.get("type") != "response_item" or payload.get("type") not in {"function_call", "custom_tool_call"}:
        continue
    name = payload.get("name", "")
    arguments = payload.get("arguments", payload.get("input", ""))
    if "image_gen__imagegen" in arguments or name.endswith("imagegen"):
        if any(word in arguments.lower() for word in ("oak", "clover", "leaf", "meadow")):
            # Extract only literal generator fields, not arbitrary executable
            # code, surrounding user messages, environment values or tool output.
            match = re.search(r'"?prompt"?\s*:\s*("(?:\\.|[^"\\])*")', arguments)
            if match:
                calls.append({"call_id": payload.get("call_id"), "tool": name,
                              "timestamp": row.get("timestamp"),
                              "prompt": json.loads(match.group(1))})
target = root / "assets/models/world-v2/image-generation-provenance.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({
    "schema": "aetherfield.original-image-provenance/1",
    "provider": "OpenAI host-native ImageGen", "calls": calls,
    "sources": ["textures/grass_meadow_v2_source.png", "textures/leaf_canopy_v2_source.png",
                "../hero-oak/v1/reference.png"],
    "license_note": "Original generated sources; do not label as CC0 or as hand-painted PBR bakes.",
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": "PASS", "generation_calls": len(calls), "artifact": str(target)}))
