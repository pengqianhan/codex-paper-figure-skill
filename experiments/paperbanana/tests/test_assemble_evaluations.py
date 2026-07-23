from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from experiments.paperbanana.scripts.assemble_evaluations import DIMENSIONS, assemble


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


class AssembleEvaluationTests(unittest.TestCase):
    def test_join_is_case_keyed_and_missing_judge_can_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_ids = ["case_0000000000000001", "case_0000000000000002"]
            executor = root / "executor.jsonl"
            judge = root / "judge.jsonl"
            write_jsonl(executor, [{"case_id": case_id} for case_id in case_ids])
            write_jsonl(
                judge,
                [
                    {
                        "case_id": case_id,
                        "category": "vision_perception",
                        "ground_truth_image": str(root / f"human-{case_id}.png"),
                    }
                    for case_id in reversed(case_ids)
                ],
            )
            job = {
                "action": "evaluate",
                "job_id": "1" * 24,
                "skill_sha256": "2" * 64,
                "executor_manifest_sha256": hashlib.sha256(
                    executor.read_bytes()
                ).hexdigest(),
                "judge_manifest_sha256": hashlib.sha256(judge.read_bytes()).hexdigest(),
            }
            for case_id in case_ids:
                (root / f"human-{case_id}.png").write_bytes(
                    f"human-{case_id}".encode()
                )
                case_output = root / "outputs" / case_id
                validation = case_output / "validation.json"
                validation.parent.mkdir(parents=True)
                validation.write_text(json.dumps({"passed": True}))
                model = case_output / "figure.png"
                model.write_bytes(f"model-{case_id}".encode())
                (case_output / "status.json").write_text(
                    json.dumps(
                        {
                            "case_id": case_id,
                            "job_id": job["job_id"],
                            "skill_sha256": job["skill_sha256"],
                            "executor_manifest_sha256": job[
                                "executor_manifest_sha256"
                            ],
                            "status": "complete",
                            "artifact_sha256": {
                                "png": hashlib.sha256(model.read_bytes()).hexdigest()
                            },
                        }
                    )
                )
            paths = {}
            for dimension in DIMENSIONS:
                path = root / f"{dimension}.jsonl"
                rows = [
                    {
                        "case_id": case_id,
                        "dimension": dimension,
                        "winner": "Model",
                        "comparison_reasoning": "clear",
                        "evaluation_job_id": job["job_id"],
                        "skill_sha256": job["skill_sha256"],
                        "human_image_sha256": hashlib.sha256(
                            (root / f"human-{case_id}.png").read_bytes()
                        ).hexdigest(),
                        "model_image_sha256": hashlib.sha256(
                            (root / "outputs" / case_id / "figure.png").read_bytes()
                        ).hexdigest(),
                    }
                    for case_id in reversed(case_ids)
                ]
                if dimension == "aesthetics":
                    rows.pop()
                write_jsonl(path, rows)
                paths[dimension] = path
            with self.assertRaises(ValueError):
                assemble(executor, judge, root / "outputs", paths, job)
            bundles, scoring = assemble(
                executor,
                judge,
                root / "outputs",
                paths,
                job,
                fail_closed_errors=True,
            )
            self.assertEqual([row["case_id"] for row in bundles], case_ids)
            self.assertFalse(bundles[0]["hard_gate_passed"])
            self.assertEqual(scoring[0]["aesthetics"], "Both are bad")


if __name__ == "__main__":
    unittest.main()
