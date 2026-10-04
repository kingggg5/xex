"""Import one local V0 evidence ZIP without external services, packages, overwrite or ZIP traversal."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import zipfile

MAX_BYTES = 48 * 1024 * 1024
NAME = re.compile(r"^lookdev/[a-z0-9][a-z0-9_-]{0,63}/[a-z0-9][a-z0-9_-]{0,63}/[AB]-(?:player\.png|side\.png|close\.png|elevated\.png|manifest\.json)$")

def collect(archive: Path, workspace: Path) -> dict:
    archive = archive.resolve(strict=True)
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir() or archive.stat().st_size > MAX_BYTES:
        raise ValueError("Workspace must be a directory; archive must be at most 48 MiB")
    evidence = (workspace / "planning" / "evidence").resolve()
    if not evidence.is_relative_to(workspace):
        raise ValueError("Evidence root redirects outside the workspace")
    evidence.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        records = package.infolist()
        if len(records) != 5 or len({entry.filename for entry in records}) != 5:
            raise ValueError("Expected exactly four PNGs and one manifest, without duplicates")
        if sum(entry.file_size for entry in records) > MAX_BYTES:
            raise ValueError("Unpacked evidence exceeds 48 MiB")
        for entry in records:
            if not NAME.fullmatch(entry.filename) or stat.S_ISLNK(entry.external_attr >> 16) or entry.is_dir() or entry.compress_type != zipfile.ZIP_STORED:
                raise ValueError("Unsafe or unexpected evidence entry")
        contents = {entry.filename: package.read(entry) for entry in records}
    manifest_names = [name for name in contents if name.endswith("-manifest.json")]
    if len(manifest_names) != 1:
        raise ValueError("Exactly one manifest is required")
    manifest_name = manifest_names[0]
    if len(contents[manifest_name]) > 128 * 1024:
        raise ValueError("Manifest exceeds 128 KiB")
    manifest = json.loads(contents[manifest_name])
    prefix = str(Path(manifest_name).parent).replace("\\", "/")
    variant = manifest.get("variant")
    if manifest.get("schema") != "xexoria-lookdev-v0" or variant not in ("A", "B") or prefix != f"lookdev/{manifest.get('pillar')}/{manifest.get('cycle')}" or not manifest_name.endswith(f"/{variant}-manifest.json"):
        raise ValueError("Manifest identity disagrees with package paths")
    captures = manifest.get("captures")
    if not isinstance(captures, list) or len(captures) != 4 or {entry.get("view") for entry in captures} != {"player", "side", "close", "elevated"}:
        raise ValueError("Manifest requires the four locked views")
    hashes = {}
    for entry in captures:
        filename = f"{variant}-{entry['view']}.png"
        if entry.get("image") != filename:
            raise ValueError("Unexpected image filename")
        data = contents.get(f"{prefix}/{filename}")
        if not data or len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise ValueError("Image is not a PNG with an IHDR header")
        width, height = struct.unpack(">II", data[16:24])
        if {"width": width, "height": height} != entry.get("imageSize") or not 1 <= width <= 1920 or not 1 <= height <= 1920 or len(data) != entry.get("bytes"):
            raise ValueError("Image size disagrees with manifest")
        digest = hashlib.sha256(data).hexdigest()
        if entry.get("sha256") is not None and entry.get("sha256") != digest:
            raise ValueError("Image hash disagrees with manifest")
        hashes[filename] = digest
    targets = []
    for name, data in contents.items():
        target = (evidence / name).resolve()
        if not target.is_relative_to(evidence) or target.exists():
            raise ValueError("Target escapes evidence root or already exists; choose a new cycle")
        targets.append((target, data))
    receipt_path = (evidence / prefix / f"{variant}-import-receipt.json").resolve()
    if not receipt_path.is_relative_to(evidence) or receipt_path.exists():
        raise ValueError("Import receipt target already exists or escapes evidence root")
    receipt = {"schema": "xexoria-lookdev-import-v0", "archive": str(archive), "archiveSha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
               "manifest": str(evidence / manifest_name), "imageHashes": hashes,
               "limits": "PNG headers/bytes/hashes verified. Pixel quality, host-reported asset/device identities and native gesture/performance acceptance are not established by import."}
    targets.append((receipt_path, (json.dumps(receipt, indent=2) + "\n").encode()))
    created = []
    try:
        for target, data in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.parent.resolve().is_relative_to(evidence):
                raise ValueError("Evidence parent redirected outside workspace")
            with target.open("xb") as output:
                created.append(target)
                output.write(data)
    except Exception:
        for target in created:
            target.unlink(missing_ok=True)
        raise
    return receipt

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(collect(args.archive, args.workspace), indent=2))
    except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
        parser.exit(1, f"Lookdev import refused: {error}\n")
