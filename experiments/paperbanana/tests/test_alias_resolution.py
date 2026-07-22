from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from experiments.paperbanana.scripts.make_manifests import (
    load_alias_map,
    resolve_ground_truth_paths,
)


class AliasResolutionTests(unittest.TestCase):
    def test_missing_filename_requires_exact_reviewed_sha_pinned_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / "images"
            images.mkdir()
            resolved = images / "mojibake.jpg"
            resolved.write_bytes(b"image-bytes")
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
            item = {"id": "ref_1", "path_to_gt_image": "images/intended.jpg"}
            with self.assertRaises(FileNotFoundError):
                resolve_ground_truth_paths([item], root, {})
            alias_path = root / "aliases.json"
            alias_path.write_text(
                json.dumps(
                    {
                        "aliases": {
                            "ref_1": {
                                "declared": "images/intended.jpg",
                                "resolved": "images/mojibake.jpg",
                                "sha256": digest,
                            }
                        }
                    }
                )
            )
            aliases, alias_sha = load_alias_map(alias_path)
            self.assertEqual(
                resolve_ground_truth_paths([item], root, aliases)["ref_1"],
                str(resolved.resolve()),
            )
            self.assertRegex(str(alias_sha), r"^[0-9a-f]{64}$")
            aliases["ref_1"]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                resolve_ground_truth_paths([item], root, aliases)


if __name__ == "__main__":
    unittest.main()
