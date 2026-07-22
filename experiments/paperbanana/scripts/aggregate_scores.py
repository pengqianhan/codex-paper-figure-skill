#!/usr/bin/env python3
"""Aggregate per-case JSONL judge results into a compact summary."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from .scoring import numeric_overall, overall_outcome
except ImportError:
    from scoring import numeric_overall, overall_outcome


DIMENSIONS = ("faithfulness", "conciseness", "readability", "aesthetics")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dimension_counts = {dimension: Counter() for dimension in DIMENSIONS}
    overall_counts: Counter[str] = Counter()
    scores: list[float] = []
    categories: dict[str, list[float]] = defaultdict(list)
    hard_failures = 0
    enriched = []
    for row in rows:
        hard_pass = bool(row.get("hard_gate_passed", False))
        if not hard_pass:
            hard_failures += 1
            outcome, tier = "Human", "hard_gate"
        else:
            outcomes = {dimension: row[dimension] for dimension in DIMENSIONS}
            for dimension, value in outcomes.items():
                dimension_counts[dimension][value] += 1
            outcome, tier = overall_outcome(outcomes)
        score = numeric_overall(outcome, hard_gate_passed=hard_pass)
        overall_counts[outcome] += 1
        scores.append(score)
        categories[str(row.get("category", "unknown"))].append(score)
        enriched.append({**row, "overall_outcome": outcome, "overall_tier": tier, "score": score})
    total = len(rows)
    return {
        "count": total,
        "mean_overall_score": sum(scores) / total if total else 0.0,
        "hard_gate_failures": hard_failures,
        "overall_counts": dict(overall_counts),
        "dimension_counts": {
            dimension: dict(counts) for dimension, counts in dimension_counts.items()
        },
        "category_mean_scores": {
            category: sum(values) / len(values) for category, values in categories.items()
        },
        "rows": enriched,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = aggregate(load_jsonl(args.input))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()

