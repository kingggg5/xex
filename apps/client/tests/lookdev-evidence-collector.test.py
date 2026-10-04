"""Local serialization/import checks; no native image or renderer quality claims."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

source = Path(__file__).resolve().parents[1] / "src" / "lookdev" / "collect_evidence.py"
spec = importlib.util.spec_from_file_location("lookdev_collector", source)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42EAAAAASUVORK5CYII=")

def package(path, *, tamper=False, escape=False):
    prefix = "lookdev/water/test-01"
    manifest = {"schema": "xexoria-lookdev-v0", "pillar": "water", "cycle": "test-01", "variant": "A", "captures": [
        {"view": view, "image": f"A-{view}.png", "bytes": len(PNG), "sha256": hashlib.sha256(PNG).hexdigest(), "imageSize": {"width": 1, "height": 1}}
        for view in ("player", "side", "close", "elevated")]}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for entry in manifest["captures"]:
            name = "../escape.png" if escape and entry["view"] == "player" else f"{prefix}/{entry['image']}"
            data = PNG[:-1] + b"x" if tamper and entry["view"] == "player" else PNG
            archive.writestr(name, data)
        archive.writestr(f"{prefix}/A-manifest.json", json.dumps(manifest))

class CollectorTests(unittest.TestCase):
    def test_valid_import_verifies_hashes_and_preserves_prior_cycle(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "game"; workspace.mkdir(); archive = Path(folder) / "capture.zip"; package(archive)
            receipt = collector.collect(archive, workspace)
            self.assertEqual(receipt["imageHashes"]["A-player.png"], hashlib.sha256(PNG).hexdigest())
            target = workspace / "planning/evidence/lookdev/water/test-01/A-player.png"
            self.assertEqual(target.read_bytes(), PNG)
            with self.assertRaises(ValueError): collector.collect(archive, workspace)
            self.assertEqual(target.read_bytes(), PNG)

    def test_path_traversal_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "game"; workspace.mkdir(); archive = Path(folder) / "capture.zip"; package(archive, escape=True)
            with self.assertRaises(ValueError): collector.collect(archive, workspace)
            self.assertFalse((workspace / "planning/escape.png").exists())
            self.assertFalse((workspace / "planning/evidence/lookdev/water/test-01/A-player.png").exists())

    def test_image_hash_mismatch_is_refused_before_admission(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "game"; workspace.mkdir(); archive = Path(folder) / "capture.zip"; package(archive, tamper=True)
            with self.assertRaises(ValueError): collector.collect(archive, workspace)
            self.assertFalse((workspace / "planning/evidence/lookdev/water/test-01/A-player.png").exists())

if __name__ == "__main__": unittest.main(verbosity=1)
