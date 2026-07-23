from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.paperbanana.scripts.build_judge_jobs import build_jobs


class JudgeJobTests(unittest.TestCase):
    def test_dimension_inputs_match_official_information_boundaries(self) -> None:
        row = {
            "case_id": "case_0123456789abcdef",
            "content": "private methodology",
            "visual_intent": "Figure 2: method overview",
            "ground_truth_image": "/private/human.png",
            "source_id": "must-not-propagate",
            "category": "vision_perception",
        }
        with tempfile.TemporaryDirectory() as directory:
            jobs = build_jobs([row], Path(directory), require_images=False)
        for dimension in ("faithfulness", "conciseness"):
            self.assertEqual(jobs[dimension][0]["content"], "private methodology")
        for dimension in ("readability", "aesthetics"):
            self.assertNotIn("content", jobs[dimension][0])
        for rows in jobs.values():
            self.assertNotIn("source_id", rows[0])
            self.assertNotIn("category", rows[0])
            self.assertEqual(
                set(rows[0]) - {"content"},
                {
                    "case_id",
                    "dimension",
                    "evaluation_job_id",
                    "skill_sha256",
                    "visual_intent",
                    "human_image",
                    "human_image_sha256",
                    "model_image",
                    "model_image_sha256",
                },
            )

    def test_hard_gate_failure_bypasses_visual_judges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            human = root / "human.png"
            human.write_bytes(b"reference")
            case_id = "case_0123456789abcdef"
            case_output = root / "outputs" / case_id
            case_output.mkdir(parents=True)
            (case_output / "validation.json").write_text('{"passed": false}')
            (case_output / "status.json").write_text(
                '{"case_id":"case_0123456789abcdef",'
                '"job_id":"111111111111111111111111",'
                '"skill_sha256":"' + "2" * 64 + '",'
                '"executor_manifest_sha256":"' + "3" * 64 + '",'
                '"status":"invalid_output"}'
            )
            jobs = build_jobs(
                [
                    {
                        "case_id": case_id,
                        "content": "method",
                        "visual_intent": "caption",
                        "ground_truth_image": str(human),
                    }
                ],
                root / "outputs",
                evaluation_job={
                    "job_id": "1" * 24,
                    "skill_sha256": "2" * 64,
                    "executor_manifest_sha256": "3" * 64,
                },
            )
        self.assertTrue(all(not rows for rows in jobs.values()))


if __name__ == "__main__":
    unittest.main()
