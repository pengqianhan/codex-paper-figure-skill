#!/usr/bin/env python3
"""Convert complete train evaluation bundles into SkillOpt-Lite samples."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from ..scripts.scoring import overall_outcome
except ImportError:
    from experiments.paperbanana.scripts.scoring import overall_outcome


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


def _by_case(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id", ""))
        if not case_id or case_id in indexed:
            raise ValueError(f"missing or duplicate {label} case_id: {case_id!r}")
        indexed[case_id] = row
    return indexed


def classify(evaluation: dict[str, Any]) -> tuple[str, str, str]:
    if not bool(evaluation.get("hard_gate_passed", False)):
        return "failed", "Human", "hard_gate"
    dimensions = evaluation.get("dimensions")
    if not isinstance(dimensions, dict):
        raise ValueError("evaluation must contain a dimensions object")
    winners = {}
    for dimension in DIMENSIONS:
        value = dimensions.get(dimension)
        if not isinstance(value, dict):
            raise ValueError(f"missing evaluation dimension: {dimension}")
        winners[dimension] = str(value.get("winner", ""))
    outcome, tier = overall_outcome(winners)
    return ("failed" if outcome == "Human" else "passed"), outcome, tier


def render_sample(
    executor: dict[str, Any],
    judge: dict[str, Any],
    evaluation: dict[str, Any],
    executor_output_root: Path,
) -> tuple[str, str]:
    case_id = str(executor["case_id"])
    label, outcome, tier = classify(evaluation)
    case_output = executor_output_root / case_id
    lines = [
        f"# Train sample {case_id}",
        "",
        "## Input",
        "",
        f"Visual intent: {executor.get('visual_intent', '')}",
        "",
        str(executor.get("content", "")),
        "",
        "## Artifacts",
        "",
        f"- Model diagram: `{case_output / 'figure.png'}`",
        f"- Human reference: `{judge.get('ground_truth_image', '')}`",
        f"- Editable source: `{case_output / 'figure.drawio'}`",
        f"- Executor trace: `{case_output / 'trace.json'}`",
        f"- Deterministic validation: `{case_output / 'validation.json'}`",
        "",
        "## Evaluation",
        "",
        f"- Hard gate passed: {bool(evaluation.get('hard_gate_passed', False))}",
        f"- Overall: {outcome} ({tier})",
    ]
    errors = evaluation.get("errors", [])
    if errors:
        lines.append(f"- Errors: {json.dumps(errors, ensure_ascii=False)}")
    dimensions = evaluation.get("dimensions") or {}
    for dimension in DIMENSIONS:
        value = dimensions.get(dimension) or {}
        lines.extend(
            [
                "",
                f"### {dimension}",
                f"- Winner: {value.get('winner', 'not judged')}",
                f"- Reasoning: {value.get('comparison_reasoning', 'not available')}",
            ]
        )
    return label, "\n".join(lines).rstrip() + "\n"


def build_samples(
    executor_manifest: Path,
    judge_manifest: Path,
    evaluations: Path,
    executor_output_root: Path,
    output_dir: Path,
    *,
    expected_count: int = 12,
    job_path: Path | None = None,
    evaluation_summary_path: Path | None = None,
) -> dict[str, int]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"sample output directory is not empty: {output_dir}")
    executor = _by_case(load_jsonl(executor_manifest), "executor")
    judge = _by_case(load_jsonl(judge_manifest), "judge")
    evaluation = _by_case(load_jsonl(evaluations), "evaluation")
    if len(executor) != expected_count or set(executor) != set(judge) or set(executor) != set(evaluation):
        raise ValueError("train executor, judge, and evaluation case sets must align exactly")
    counts = {"failed": 0, "passed": 0}
    for case_id in executor:
        label, payload = render_sample(
            executor[case_id], judge[case_id], evaluation[case_id], executor_output_root
        )
        target = output_dir / label / f"{case_id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload)
        counts[label] += 1
    if (job_path is None) != (evaluation_summary_path is None):
        raise ValueError("job_path and evaluation_summary_path must be provided together")
    if job_path is not None and evaluation_summary_path is not None:
        job = json.loads(job_path.read_text())
        expected_provenance = {
            "evaluation_job_id": job["job_id"],
            "skill_sha256": job["skill_sha256"],
            "executor_manifest_sha256": job["executor_manifest_sha256"],
            "judge_manifest_sha256": job["judge_manifest_sha256"],
        }
        for row in evaluation.values():
            for key, value in expected_provenance.items():
                if row.get(key) != value:
                    raise ValueError(
                        f"evaluation bundle provenance mismatch for {row.get('case_id')}: {key}"
                    )
        receipt = {
            "job_id": job["job_id"],
            "skill_sha256": job["skill_sha256"],
            "executor_manifest_sha256": job["executor_manifest_sha256"],
            "judge_manifest_sha256": job["judge_manifest_sha256"],
            "evaluation_summary_sha256": sha256(evaluation_summary_path),
            "evaluation_bundles_sha256": sha256(evaluations),
            "sample_files": {
                str(path.relative_to(output_dir)): sha256(path)
                for label in ("failed", "passed")
                for path in sorted((output_dir / label).glob("*.md"))
            },
        }
        (output_dir / "_receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
        )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor-manifest", type=Path, required=True)
    parser.add_argument("--judge-manifest", type=Path, required=True)
    parser.add_argument("--evaluations", type=Path, required=True)
    parser.add_argument("--executor-output-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--evaluation-summary", type=Path, required=True)
    args = parser.parse_args()
    counts = build_samples(
        args.executor_manifest,
        args.judge_manifest,
        args.evaluations,
        args.executor_output_root,
        args.output_dir,
        job_path=args.job,
        evaluation_summary_path=args.evaluation_summary,
    )
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
