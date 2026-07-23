#!/usr/bin/env python3
"""Join deterministic gates and four Codex judge outputs by opaque case ID."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DIMENSIONS = ("faithfulness", "conciseness", "readability", "aesthetics")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"row must be an object at {path}:{line_number}")
        rows.append(row)
    return rows


def by_case(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed = {}
    for row in rows:
        case_id = str(row.get("case_id", ""))
        if not case_id or case_id in indexed:
            raise ValueError(f"missing or duplicate {label} case_id: {case_id!r}")
        indexed[case_id] = row
    return indexed


def assemble(
    executor_manifest: Path,
    judge_manifest: Path,
    model_output_root: Path,
    judge_results: dict[str, Path],
    prepared_job: dict[str, Any],
    *,
    fail_closed_errors: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if prepared_job.get("action") != "evaluate":
        raise ValueError("prepared job is not an evaluation")
    if sha256(executor_manifest) != prepared_job["executor_manifest_sha256"]:
        raise ValueError("executor manifest does not match prepared job")
    if sha256(judge_manifest) != prepared_job["judge_manifest_sha256"]:
        raise ValueError("judge manifest does not match prepared job")
    executor_rows = load_jsonl(executor_manifest)
    executor = by_case(executor_rows, "executor")
    judge_only = by_case(load_jsonl(judge_manifest), "judge manifest")
    if set(executor) != set(judge_only):
        raise ValueError("executor and judge manifests do not align")
    per_dimension: dict[str, dict[str, dict[str, Any]]] = {}
    for dimension in DIMENSIONS:
        rows = load_jsonl(judge_results[dimension])
        for row in rows:
            if row.get("dimension") != dimension:
                raise ValueError(f"judge row in {dimension} file has wrong dimension")
        per_dimension[dimension] = by_case(rows, f"{dimension} judge")
        extra = set(per_dimension[dimension]) - set(executor)
        if extra:
            raise ValueError(f"{dimension} judge contains unexpected cases: {sorted(extra)}")

    bundles = []
    scoring_rows = []
    for case_id in executor:
        errors: list[str] = []
        status_path = model_output_root / case_id / "status.json"
        status: dict[str, Any] = {}
        if status_path.is_file():
            status = json.loads(status_path.read_text())
            expected_status = {
                "case_id": case_id,
                "job_id": prepared_job["job_id"],
                "skill_sha256": prepared_job["skill_sha256"],
                "executor_manifest_sha256": prepared_job[
                    "executor_manifest_sha256"
                ],
            }
            for key, expected in expected_status.items():
                if status.get(key) != expected:
                    raise ValueError(f"executor status provenance mismatch for {case_id}: {key}")
        elif not fail_closed_errors:
            raise FileNotFoundError(status_path)
        else:
            errors.append("missing_executor_status")
        validation_path = model_output_root / case_id / "validation.json"
        status_value = status.get("status")
        if not status:
            hard_gate_passed = False
        elif status_value in {"infrastructure_failed", "invalid_output"}:
            hard_gate_passed = False
            errors.append(str(status_value))
        elif validation_path.is_file():
            validation = json.loads(validation_path.read_text())
            hard_gate_passed = bool(validation.get("passed", False))
            if not hard_gate_passed:
                errors.extend(str(error) for error in validation.get("errors", []))
        elif fail_closed_errors:
            hard_gate_passed = False
            errors.append("missing_deterministic_validation")
        else:
            raise FileNotFoundError(validation_path)

        dimensions = {}
        model_image = model_output_root / case_id / "figure.png"
        model_image_sha256 = sha256(model_image) if model_image.is_file() else None
        human_image = Path(str(judge_only[case_id].get("ground_truth_image", "")))
        if not human_image.is_file():
            raise FileNotFoundError(f"missing human image for {case_id}: {human_image}")
        human_image_sha256 = sha256(human_image)
        if (
            status_value == "complete"
            and model_image_sha256 is not None
            and status.get("artifact_sha256", {}).get("png") != model_image_sha256
        ):
            raise ValueError(f"model image SHA mismatch for {case_id}")
        if hard_gate_passed:
            if status_value != "complete":
                raise ValueError(f"judgeable case is not complete: {case_id}")
            if model_image_sha256 is None:
                raise FileNotFoundError(model_image)
            for dimension in DIMENSIONS:
                row = per_dimension[dimension].get(case_id)
                if row is None:
                    if fail_closed_errors:
                        hard_gate_passed = False
                        errors.append(f"missing_{dimension}_judge")
                        continue
                    raise ValueError(f"missing {dimension} judge result for {case_id}")
                expected_provenance = {
                    "evaluation_job_id": prepared_job["job_id"],
                    "skill_sha256": prepared_job["skill_sha256"],
                    "human_image_sha256": human_image_sha256,
                    "model_image_sha256": model_image_sha256,
                }
                for key, expected in expected_provenance.items():
                    if row.get(key) != expected:
                        raise ValueError(
                            f"{dimension} judge provenance mismatch for {case_id}: {key}"
                        )
                dimensions[dimension] = {
                    "winner": str(row.get("winner", "")),
                    "comparison_reasoning": str(row.get("comparison_reasoning", "")),
                }
        bundle = {
            "case_id": case_id,
            "evaluation_job_id": prepared_job["job_id"],
            "skill_sha256": prepared_job["skill_sha256"],
            "executor_manifest_sha256": prepared_job[
                "executor_manifest_sha256"
            ],
            "judge_manifest_sha256": prepared_job["judge_manifest_sha256"],
            "executor_status_sha256": sha256(status_path) if status_path.is_file() else None,
            "model_image_sha256": model_image_sha256,
            "human_image_sha256": human_image_sha256,
            "category": judge_only[case_id].get("category", "unknown"),
            "hard_gate_passed": hard_gate_passed,
            "dimensions": dimensions,
            "errors": sorted(set(errors)),
        }
        score_row = {
            "case_id": case_id,
            "evaluation_job_id": bundle["evaluation_job_id"],
            "skill_sha256": bundle["skill_sha256"],
            "executor_manifest_sha256": bundle["executor_manifest_sha256"],
            "judge_manifest_sha256": bundle["judge_manifest_sha256"],
            "executor_status_sha256": bundle["executor_status_sha256"],
            "model_image_sha256": bundle["model_image_sha256"],
            "category": bundle["category"],
            "hard_gate_passed": hard_gate_passed,
        }
        for dimension in DIMENSIONS:
            score_row[dimension] = dimensions.get(dimension, {}).get(
                "winner", "Both are bad"
            )
        bundles.append(bundle)
        scoring_rows.append(score_row)
    return bundles, scoring_rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor-manifest", type=Path, required=True)
    parser.add_argument("--judge-manifest", type=Path, required=True)
    parser.add_argument("--model-output-root", type=Path, required=True)
    for dimension in DIMENSIONS:
        parser.add_argument(f"--{dimension}", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument(
        "--fail-closed-errors",
        action="store_true",
        help="Score confirmed missing judge/validation artifacts as zero instead of aborting.",
    )
    args = parser.parse_args()
    bundles, scoring = assemble(
        args.executor_manifest,
        args.judge_manifest,
        args.model_output_root,
        {dimension: getattr(args, dimension) for dimension in DIMENSIONS},
        json.loads(args.job.read_text()),
        fail_closed_errors=args.fail_closed_errors,
    )
    write_jsonl(args.output_dir / "evaluation_bundles.jsonl", bundles)
    write_jsonl(args.output_dir / "scoring_rows.jsonl", scoring)


if __name__ == "__main__":
    main()
