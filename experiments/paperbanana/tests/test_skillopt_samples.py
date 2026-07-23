from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.paperbanana.skillopt_lite.build_train_samples import build_samples


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


class SkillOptSampleTests(unittest.TestCase):
    def test_hard_failure_and_human_outcome_are_failed_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = []
            judge = []
            evaluations = []
            winners = ("Model", "Human", "Both are good")
            for index, winner in enumerate(winners):
                case_id = f"case_{index:016x}"
                executor.append(
                    {"case_id": case_id, "content": "method", "visual_intent": "caption"}
                )
                judge.append({"case_id": case_id, "ground_truth_image": f"/gt/{index}.png"})
                evaluations.append(
                    {
                        "case_id": case_id,
                        "hard_gate_passed": index != 2,
                        "dimensions": {
                            dimension: {
                                "winner": winner,
                                "comparison_reasoning": f"reason {dimension}",
                            }
                            for dimension in (
                                "faithfulness",
                                "conciseness",
                                "readability",
                                "aesthetics",
                            )
                        },
                    }
                )
            executor_path = root / "executor.jsonl"
            judge_path = root / "judge.jsonl"
            evaluation_path = root / "evaluations.jsonl"
            write_jsonl(executor_path, executor)
            write_jsonl(judge_path, judge)
            write_jsonl(evaluation_path, evaluations)
            counts = build_samples(
                executor_path,
                judge_path,
                evaluation_path,
                root / "outputs",
                root / "samples",
                expected_count=3,
            )
            self.assertEqual(counts, {"failed": 2, "passed": 1})
            failed_text = "\n".join(
                path.read_text() for path in (root / "samples/failed").glob("*.md")
            )
            self.assertIn("Human", failed_text)
            self.assertIn("Hard gate passed: False", failed_text)


if __name__ == "__main__":
    unittest.main()

