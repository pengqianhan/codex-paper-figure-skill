#!/usr/bin/env python3
"""Build dimension-isolated Codex VLM-judge packets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


DIMENSION_FIELDS = {
    "faithfulness": ("content", "visual_intent"),
    "conciseness": ("content", "visual_intent"),
    "readability": ("visual_intent",),
    "aesthetics": ("visual_intent",),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
        rows.append(row)
    return rows


def build_jobs(
    judge_rows: Iterable[dict[str, Any]],
    model_output_root: Path,
    *,
    require_images: bool = True,
    evaluation_job: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if require_images and evaluation_job is None:
        raise ValueError("a prepared evaluation job is required for provenance")
    jobs = {dimension: [] for dimension in DIMENSION_FIELDS}
    seen: set[str] = set()
    for row in judge_rows:
        case_id = str(row.get("case_id", ""))
        if not case_id or case_id in seen:
            raise ValueError(f"missing or duplicate case_id: {case_id!r}")
        seen.add(case_id)
        human_image = Path(str(row.get("ground_truth_image", "")))
        case_output = model_output_root / case_id
        model_image = case_output / "figure.png"
        if require_images:
            if not human_image.is_file():
                raise FileNotFoundError(f"missing human image for {case_id}: {human_image}")
            status_path = case_output / "status.json"
            if not status_path.is_file():
                raise FileNotFoundError(f"missing executor status for {case_id}: {status_path}")
            status = json.loads(status_path.read_text())
            expected_status = {
                "case_id": case_id,
                "job_id": evaluation_job["job_id"],
                "skill_sha256": evaluation_job["skill_sha256"],
                "executor_manifest_sha256": evaluation_job[
                    "executor_manifest_sha256"
                ],
            }
            for key, expected in expected_status.items():
                if status.get(key) != expected:
                    raise ValueError(f"executor status provenance mismatch for {case_id}: {key}")
            validation_path = case_output / "validation.json"
            if not validation_path.is_file():
                if status.get("status") in {"infrastructure_failed", "invalid_output"}:
                    continue
                raise FileNotFoundError(
                    f"missing deterministic validation for {case_id}: {validation_path}"
                )
            if not bool(json.loads(validation_path.read_text()).get("passed", False)):
                # Hard-gate failures score zero and bypass visual judging.
                continue
            if not model_image.is_file():
                raise FileNotFoundError(f"missing model image for {case_id}: {model_image}")
            if status.get("status") != "complete":
                raise ValueError(f"non-complete executor status has judgeable output: {case_id}")
            if status.get("artifact_sha256", {}).get("png") != sha256(model_image):
                raise ValueError(f"model image SHA mismatch for {case_id}")
        shared = {
            "case_id": case_id,
            "evaluation_job_id": (
                evaluation_job["job_id"] if evaluation_job else "0" * 24
            ),
            "skill_sha256": (
                evaluation_job["skill_sha256"] if evaluation_job else "0" * 64
            ),
            "human_image": str(human_image),
            "human_image_sha256": sha256(human_image) if human_image.is_file() else "0" * 64,
            "model_image": str(model_image),
            "model_image_sha256": sha256(model_image) if model_image.is_file() else "0" * 64,
        }
        for dimension, visible_fields in DIMENSION_FIELDS.items():
            job = {**shared, "dimension": dimension}
            for field in visible_fields:
                job[field] = str(row.get(field, ""))
            jobs[dimension].append(job)
    return jobs


def write_jobs(output_dir: Path, jobs: dict[str, list[dict[str, Any]]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for dimension, rows in jobs.items():
        payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        (output_dir / f"{dimension}.jsonl").write_text(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-manifest", type=Path, required=True)
    parser.add_argument("--model-output-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    jobs = build_jobs(
        load_jsonl(args.judge_manifest),
        args.model_output_root,
        evaluation_job=json.loads(args.job.read_text()),
    )
    write_jobs(args.output_dir, jobs)


if __name__ == "__main__":
    main()
