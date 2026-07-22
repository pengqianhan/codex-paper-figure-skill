from __future__ import annotations

import unittest
from itertools import product

from experiments.paperbanana.scripts.scoring import (
    determine_tier_outcome,
    numeric_overall,
    overall_outcome,
)


class ScoringTests(unittest.TestCase):
    def test_all_tier_and_dimension_combinations(self) -> None:
        values = ("Human", "Model", "Both are good", "Both are bad")
        expected = {
            ("Human", "Human"): "Human",
            ("Human", "Model"): "Tie",
            ("Human", "Both are good"): "Human",
            ("Human", "Both are bad"): "Human",
            ("Model", "Human"): "Tie",
            ("Model", "Model"): "Model",
            ("Model", "Both are good"): "Model",
            ("Model", "Both are bad"): "Model",
            ("Both are good", "Human"): "Human",
            ("Both are good", "Model"): "Model",
            ("Both are good", "Both are good"): "Tie",
            ("Both are good", "Both are bad"): "Tie",
            ("Both are bad", "Human"): "Human",
            ("Both are bad", "Model"): "Model",
            ("Both are bad", "Both are good"): "Tie",
            ("Both are bad", "Both are bad"): "Tie",
        }
        for pair in product(values, repeat=2):
            self.assertEqual(determine_tier_outcome(*pair), expected[pair])
        checked = 0
        for faithfulness, conciseness, readability, aesthetics in product(
            values, repeat=4
        ):
            tier_one = expected[(faithfulness, readability)]
            expected_result = (
                (tier_one, "tier1")
                if tier_one != "Tie"
                else (expected[(conciseness, aesthetics)], "tier2")
            )
            self.assertEqual(
                overall_outcome(
                    {
                        "faithfulness": faithfulness,
                        "conciseness": conciseness,
                        "readability": readability,
                        "aesthetics": aesthetics,
                    }
                ),
                expected_result,
            )
            checked += 1
        self.assertEqual(checked, 256)

    def test_tier_rules_match_paperbanana(self) -> None:
        self.assertEqual(determine_tier_outcome("Model", "Both are good"), "Model")
        self.assertEqual(determine_tier_outcome("Human", "Both are bad"), "Human")
        self.assertEqual(determine_tier_outcome("Both are good", "Both are good"), "Tie")
        self.assertEqual(determine_tier_outcome("Model", "Human"), "Tie")

    def test_tier_one_has_priority(self) -> None:
        outcome, tier = overall_outcome(
            {
                "faithfulness": "Model",
                "readability": "Both are good",
                "conciseness": "Human",
                "aesthetics": "Human",
            }
        )
        self.assertEqual((outcome, tier), ("Model", "tier1"))

    def test_tier_two_breaks_tier_one_tie(self) -> None:
        outcome, tier = overall_outcome(
            {
                "faithfulness": "Model",
                "readability": "Human",
                "conciseness": "Model",
                "aesthetics": "Both are good",
            }
        )
        self.assertEqual((outcome, tier), ("Model", "tier2"))
        self.assertEqual(numeric_overall(outcome), 1.0)
        self.assertEqual(numeric_overall("Model", hard_gate_passed=False), 0.0)


if __name__ == "__main__":
    unittest.main()
