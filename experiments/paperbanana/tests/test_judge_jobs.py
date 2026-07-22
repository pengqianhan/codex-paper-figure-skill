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
                {"case_id", "dimension", "visual_intent", "human_image", "model_image"},
            )


if __name__ == "__main__":
    unittest.main()
