"""Safe, serialized updates to the shared nature-props manifest."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any


SCHEMA = "xexoria.props-manifest/1"
FAMILIES = ("stone", "craft", "flora")
LOCK_WAIT_SECONDS = 15.0


class ManifestError(ValueError):
    """The existing manifest or requested update does not match the contract."""


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": SCHEMA, "families": {name: [] for name in FAMILIES}}

    try:
        with path.open("r", encoding="utf-8") as source:
            manifest = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read a valid manifest at {path}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be a JSON object")
    if manifest.get("schema") != SCHEMA:
        raise ManifestError(f"manifest schema must be {SCHEMA!r}")
    families = manifest.get("families")
    if not isinstance(families, dict):
        raise ManifestError("manifest 'families' must be a JSON object")
    for name in FAMILIES:
        if name not in families or not isinstance(families[name], list):
            raise ManifestError(f"manifest family {name!r} must be a JSON array")
    return manifest


def _acquire_lock(lock_path: Path) -> int:
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for manifest lock {lock_path}")
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def merge_family(path: os.PathLike[str] | str, family: str, entries: list[Any]) -> dict[str, Any]:
    """Replace one complete family under a lock and atomically replace the file.

    A missing manifest is initialized with the supported schema. Existing malformed
    manifests are rejected, so an update can never silently replace their contents.
    """
    if family not in FAMILIES:
        raise ManifestError(f"family must be one of {', '.join(FAMILIES)}")
    if not isinstance(entries, list):
        raise TypeError("entries must be a list of JSON-serializable values")
    try:
        # Validate each entry before acquiring the lock or changing the manifest.
        json.dumps(entries, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"entries must contain only JSON-serializable values: {exc}") from exc
    seen_ids: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict) and "id" in entry:
            entry_id = entry["id"]
            if not isinstance(entry_id, str):
                raise ManifestError("entry ids must be strings")
            if entry_id in seen_ids:
                raise ManifestError(f"duplicate entry id {entry_id!r} in family {family!r}")
            seen_ids.add(entry_id)

    target = Path(path)
    lock_path = target.with_name(target.name + ".lock")
    lock_fd = _acquire_lock(lock_path)
    temp_path: str | None = None
    try:
        manifest = _read_manifest(target)
        manifest["families"][family] = entries
        # Validate the complete document as strict JSON before creating a replacement.
        serialized = json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temp_path = temporary.name
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temp_path, target)
        temp_path = None
        return manifest
    finally:
        os.close(lock_fd)
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
        os.unlink(lock_path)


__all__ = ["FAMILIES", "LOCK_WAIT_SECONDS", "ManifestError", "SCHEMA", "merge_family"]
