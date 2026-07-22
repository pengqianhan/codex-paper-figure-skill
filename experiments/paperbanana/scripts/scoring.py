"""PaperBanana-compatible categorical outcome aggregation."""

from __future__ import annotations

from typing import Mapping


DIMENSION_OUTCOMES = {"Human", "Model", "Both are good", "Both are bad"}
OVERALL_OUTCOMES = {"Human", "Model", "Tie"}
NUMERIC_OVERALL = {"Human": 0.0, "Tie": 0.5, "Model": 1.0}


def determine_tier_outcome(first: str, second: str) -> str:
    """Reproduce PaperBanana's two-dimension tier decision."""

    if first not in DIMENSION_OUTCOMES or second not in DIMENSION_OUTCOMES:
        raise ValueError(f"invalid tier outcomes: {first!r}, {second!r}")
    if first == second:
        if first in {"Both are good", "Both are bad"}:
            return "Tie"
        return first
    neutral = {"Both are good", "Both are bad"}
    if first == "Model" and second in neutral:
        return "Model"
    if second == "Model" and first in neutral:
        return "Model"
    if first == "Human" and second in neutral:
        return "Human"
    if second == "Human" and first in neutral:
        return "Human"
    return "Tie"


def overall_outcome(dimensions: Mapping[str, str]) -> tuple[str, str]:
    required = {"faithfulness", "conciseness", "readability", "aesthetics"}
    missing = required - set(dimensions)
    if missing:
        raise ValueError(f"missing dimensions: {sorted(missing)}")
    tier_one = determine_tier_outcome(
        dimensions["faithfulness"], dimensions["readability"]
    )
    if tier_one in {"Model", "Human"}:
        return tier_one, "tier1"
    tier_two = determine_tier_outcome(
        dimensions["conciseness"], dimensions["aesthetics"]
    )
    return tier_two, "tier2"


def numeric_overall(outcome: str, *, hard_gate_passed: bool = True) -> float:
    if not hard_gate_passed:
        return 0.0
    if outcome not in NUMERIC_OVERALL:
        return 0.0
    return NUMERIC_OVERALL[outcome]


__all__ = [
    "DIMENSION_OUTCOMES",
    "NUMERIC_OVERALL",
    "OVERALL_OUTCOMES",
    "determine_tier_outcome",
    "numeric_overall",
    "overall_outcome",
]

