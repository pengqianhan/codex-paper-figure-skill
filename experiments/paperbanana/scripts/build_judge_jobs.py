#!/usr/bin/env python3
"""Build dimension-isolated Codex VLM-judge packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


DIMENSION_FIELDS = {
    "faithfulness": ("content", "visual_intent"),
    "conciseness": ("content", "visual_intent"),
    "readability": ("visual_intent",),
    "aesthetics": ("visual_intent",),
}


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
) -> dict[str, list[dict[str, Any]]]:
    jobs = {dimension: [] for dimension in DIMENSION_FIELDS}
    seen: set[str] = set()
    for row in judge_rows:
        case_id = str(row.get("case_id", ""))
        if not case_id or case_id in seen:
            raise ValueError(f"missing or duplicate case_id: {case_id!r}")
        seen.add(case_id)
        human_image = Path(str(row.get("ground_truth_image", "")))
        model_image = model_output_root / case_id / "figure.png"
        if require_images:
            if not human_image.is_file():
                raise FileNotFoundError(f"missing human image for {case_id}: {human_image}")
            if not model_image.is_file():
                raise FileNotFoundError(f"missing model image for {case_id}: {model_image}")
        shared = {
            "case_id": case_id,
            "human_image": str(human_image),
            "model_image": str(model_image),
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
    args = parser.parse_args()
    jobs = build_jobs(load_jsonl(args.judge_manifest), args.model_output_root)
    write_jobs(args.output_dir, jobs)


if __name__ == "__main__":
    main()
