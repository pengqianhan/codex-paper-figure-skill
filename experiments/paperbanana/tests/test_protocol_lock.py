from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProtocolLockTests(unittest.TestCase):
    def test_protocol_and_locked_inputs_are_consistent(self) -> None:
        protocol_path = ROOT / "experiments/paperbanana/protocol.yaml"
        protocol = yaml.safe_load(protocol_path.read_text())
        self.assertEqual(protocol["data"]["train_size"], 36)
        self.assertEqual(protocol["data"]["validation_size"], 24)
        self.assertFalse(protocol["data"]["include_test_during_optimization"])
        lock = json.loads(
            (ROOT / "experiments/paperbanana/locks/toolchain.json").read_text()
        )
        skill = ROOT / "codex-paper-figure-skill/SKILL.md"
        self.assertEqual(sha256(skill), lock["inputs"]["baseline_skill_sha256"])


if __name__ == "__main__":
    unittest.main()

