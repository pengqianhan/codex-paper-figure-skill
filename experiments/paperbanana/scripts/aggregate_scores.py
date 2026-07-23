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
    parser.add_argument(
        "--job",
        type=Path,
        help="Prepared controller job whose hashes bind this aggregate receipt.",
    )
    args = parser.parse_args()
    rows = load_jsonl(args.input)
    result = aggregate(rows)
    if args.job:
        job = json.loads(args.job.read_text())
        if job.get("action") != "evaluate":
            raise ValueError("--job must refer to an evaluation job")
        if result["count"] != int(job["expected_count"]):
            raise ValueError("aggregate count does not match prepared job")
        expected_case_ids = {
            str(row["case_id"])
            for row in load_jsonl(Path(job["executor_manifest"]))
        }
        actual_case_ids = [str(row.get("case_id", "")) for row in rows]
        if len(actual_case_ids) != len(set(actual_case_ids)):
            raise ValueError("aggregate input contains duplicate case IDs")
        if set(actual_case_ids) != expected_case_ids:
            raise ValueError("aggregate case IDs do not match prepared job manifest")
        expected_provenance = {
            "evaluation_job_id": job["job_id"],
            "skill_sha256": job["skill_sha256"],
            "executor_manifest_sha256": job["executor_manifest_sha256"],
            "judge_manifest_sha256": job["judge_manifest_sha256"],
        }
        for row in rows:
            for key, expected in expected_provenance.items():
                if row.get(key) != expected:
                    raise ValueError(
                        f"scoring row provenance mismatch for {row.get('case_id')}: {key}"
                    )
            status_sha = row.get("executor_status_sha256")
            if status_sha is not None and (
                not isinstance(status_sha, str) or len(status_sha) != 64
            ):
                raise ValueError("invalid executor status provenance hash")
        result["evaluation_receipt"] = {
            "job_id": job["job_id"],
            "skill_sha256": job["skill_sha256"],
            "executor_manifest_sha256": job["executor_manifest_sha256"],
            "judge_manifest_sha256": job["judge_manifest_sha256"],
            "completed_count": result["count"],
            "status": "complete",
        }
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
