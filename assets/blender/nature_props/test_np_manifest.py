"""Tests for the serialized nature-props manifest update helper."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from np_manifest import ManifestError, SCHEMA, merge_family


class ManifestMergeTests(unittest.TestCase):
    def test_replaces_only_requested_family_and_preserves_other_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            original = {
                "schema": SCHEMA,
                "families": {
                    "stone": [{"id": "old-stone"}],
                    "craft": [{"id": "craft-1", "nested": {"keep": [1, "x"]}}],
                    "flora": [{"id": "flora-1"}],
                    "future-family": {"opaque": [False, None, 4.5]},
                },
                "metadata": {"keep": True},
            }
            path.write_text(json.dumps(original), encoding="utf-8")

            merge_family(path, "stone", [{"id": "stone-a"}, {"id": "stone-b"}])

            updated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(updated["families"]["stone"], [{"id": "stone-a"}, {"id": "stone-b"}])
            self.assertEqual(updated["families"]["craft"], original["families"]["craft"])
            self.assertEqual(updated["families"]["flora"], original["families"]["flora"])
            self.assertEqual(updated["families"]["future-family"], original["families"]["future-family"])
            self.assertEqual(updated["metadata"], original["metadata"])

    def test_invalid_schema_leaves_file_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            original = b'{"schema":"wrong","families":{"stone":[],"craft":[],"flora":[]}}\n'
            path.write_bytes(original)

            with self.assertRaises(ManifestError):
                merge_family(path, "stone", [{"id": "stone-a"}])

            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(path.with_name(path.name + ".lock").exists())

    def test_malformed_families_leave_file_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            original = json.dumps({"schema": SCHEMA, "families": {
                "stone": [], "craft": {}, "flora": [],
            }}).encode("utf-8")
            path.write_bytes(original)

            with self.assertRaises(ManifestError):
                merge_family(path, "stone", [{"id": "stone-a"}])

            self.assertEqual(path.read_bytes(), original)

    def test_duplicate_entry_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            original = {"schema": SCHEMA, "families": {
                "stone": [], "craft": [], "flora": [],
            }}
            path.write_text(json.dumps(original), encoding="utf-8")

            with self.assertRaises(ManifestError):
                merge_family(path, "stone", [{"id": "same"}, {"id": "same"}])

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)

    def test_concurrent_subprocess_updates_all_families_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({"schema": SCHEMA, "families": {
                "stone": [], "craft": [], "flora": [],
            }}), encoding="utf-8")
            module_dir = str(Path(__file__).resolve().parent)
            script = (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from np_manifest import merge_family; "
                "merge_family(sys.argv[2], sys.argv[3], [{'id': sys.argv[3] + '-child'}])"
            )
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", script, module_dir, str(path), family],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                for family in ("stone", "craft", "flora")
            ]
            results = [process.communicate(timeout=20) + (process.returncode,) for process in processes]
            failures = [stderr.decode("utf-8", errors="replace") for _, stderr, code in results if code]
            self.assertEqual(failures, [])
            updated = json.loads(path.read_text(encoding="utf-8"))
            for family in ("stone", "craft", "flora"):
                self.assertEqual(updated["families"][family], [{"id": family + "-child"}])
            self.assertFalse(path.with_name(path.name + ".lock").exists())


if __name__ == "__main__":
    unittest.main()
