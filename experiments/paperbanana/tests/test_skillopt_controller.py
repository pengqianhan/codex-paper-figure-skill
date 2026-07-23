from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from experiments.paperbanana.skillopt_lite.controller import (
    apply_edits,
    audit,
    decide_gate,
    finalize,
    ingest_proposal,
    ingest_train,
    ingest_validation,
    initialize,
    prepare_next,
    validate_skill_document,
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def score_summary(path: Path, count: int, half_units: int, job: dict) -> None:
    model = min(half_units // 2, count)
    tie = half_units - 2 * model
    human = count - model - tie
    write_json(
        path,
        {
            "count": count,
            "mean_overall_score": half_units / (2 * count),
            "hard_gate_failures": 0,
            "overall_counts": {"Model": model, "Tie": tie, "Human": human},
            "dimension_counts": {},
            "rows": [
                {
                    "case_id": json.loads(line)["case_id"],
                    "evaluation_job_id": job["job_id"],
                    "skill_sha256": job["skill_sha256"],
                    "executor_manifest_sha256": job["executor_manifest_sha256"],
                    "judge_manifest_sha256": job["judge_manifest_sha256"],
                    "executor_status_sha256": "4" * 64,
                }
                for line in Path(job["executor_manifest"]).read_text().splitlines()
                if line.strip()
            ],
            "evaluation_receipt": {
                "job_id": job["job_id"],
                "skill_sha256": job["skill_sha256"],
                "executor_manifest_sha256": job["executor_manifest_sha256"],
                "judge_manifest_sha256": job["judge_manifest_sha256"],
                "completed_count": count,
                "status": "complete",
            },
        },
    )


def samples(
    path: Path,
    job: dict,
    summary_path: Path,
    evaluations_path: Path,
    failed: int = 6,
    passed: int = 6,
) -> None:
    case_ids = [
        json.loads(line)["case_id"]
        for line in Path(job["executor_manifest"]).read_text().splitlines()
        if line.strip()
    ]
    offset = 0
    for label, count in (("failed", failed), ("passed", passed)):
        (path / label).mkdir(parents=True, exist_ok=True)
        for index in range(count):
            (path / label / f"{case_ids[offset + index]}.md").write_text("sample")
        offset += count
    sample_paths = [
        file_path
        for label in ("failed", "passed")
        for file_path in sorted((path / label).glob("*.md"))
    ]
    write_json(
        path / "_receipt.json",
        {
            "job_id": job["job_id"],
            "skill_sha256": job["skill_sha256"],
            "executor_manifest_sha256": job["executor_manifest_sha256"],
            "judge_manifest_sha256": job["judge_manifest_sha256"],
            "evaluation_summary_sha256": hashlib.sha256(
                summary_path.read_bytes()
            ).hexdigest(),
            "evaluation_bundles_sha256": hashlib.sha256(
                evaluations_path.read_bytes()
            ).hexdigest(),
            "sample_files": {
                str(file_path.relative_to(path)): hashlib.sha256(
                    file_path.read_bytes()
                ).hexdigest()
                for file_path in sample_paths
            },
        },
    )


def proposal(
    path: Path, round_index: int, content: str, job: dict, sample_dir: Path
) -> None:
    support = sorted(
        sample_path.stem
        for label in ("failed", "passed")
        for sample_path in (sample_dir / label).glob("*.md")
    )[:2]
    write_json(
        path,
        {
            "round": round_index,
            "job_id": job["job_id"],
            "base_skill_sha256": job["base_skill_sha256"],
            "sampling_report": {
                "failed_read": 6,
                "failed_total": 6,
                "passed_read": 6,
                "passed_total": 6,
            },
            "diagnosis": [{"pattern": "recurring layout issue", "support_case_ids": support}],
            "edits": [
                {
                    "op": "append",
                    "target": "",
                    "content": content,
                    "support_case_ids": support,
                }
            ],
            "expected_impact": "improve recurring layouts",
            "regressions_to_watch": ["skill length"],
        },
    )


class SkillOptControllerTests(unittest.TestCase):
    def test_gate_dead_band_and_exact_edits(self) -> None:
        self.assertEqual(decide_gate(25, 24, 24), "accept_new_best")
        self.assertEqual(decide_gate(24, 24, 28), "flat")
        self.assertEqual(decide_gate(23, 24, 28), "reject")
        self.assertEqual(decide_gate(101, 100, 100, count=100), "flat")
        self.assertEqual(decide_gate(102, 100, 100, count=100), "accept_new_best")
        self.assertEqual(decide_gate(98, 100, 120, count=100), "reject")
        base = (
            "---\nname: codex-paper-figure-skill\ndescription: test\n---\n\n"
            "alpha\nbeta\n"
        )
        self.assertEqual(
            apply_edits(base, [{"op": "replace", "target": "beta", "content": "gamma"}]),
            base.replace("beta", "gamma"),
        )
        with self.assertRaises(ValueError):
            apply_edits("same same", [{"op": "delete", "target": "same", "content": ""}])
        with self.assertRaises(ValueError):
            validate_skill_document(
                "---\nname: codex-paper-figure-skill\ndescription: x\n---\n"
                "Memorize case_0123456789abcdef"
            )

    def test_three_round_flow_post_final_rollout_and_best_restore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            run = root / "run"
            manifests = root / "manifests"
            skill = repo / "codex-paper-figure-skill" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: codex-paper-figure-skill\ndescription: test\n---\n\n# Base\n"
            )
            protocol = repo / "experiments" / "paperbanana" / "protocol.yaml"
            protocol.parent.mkdir(parents=True)
            protocol.write_text("protocol_version: 1\n")
            validation_rows = [{"case_id": f"case_{index:016x}"} for index in range(24)]
            write_jsonl(manifests / "validation_executor.jsonl", validation_rows)
            write_jsonl(manifests / "judge-only" / "validation.jsonl", validation_rows)
            all_train = []
            for round_index in range(1, 4):
                rows = [
                    {"case_id": f"case_{100 * round_index + index:016x}"}
                    for index in range(12)
                ]
                all_train.extend(rows)
                write_jsonl(manifests / f"train_round_{round_index}_executor.jsonl", rows)
                write_jsonl(manifests / "judge-only" / f"train_round_{round_index}.jsonl", rows)
            write_jsonl(
                manifests / "controller-only" / "train_pool_executor.jsonl",
                all_train,
            )
            write_jsonl(
                manifests / "controller-only" / "train_pool_judge.jsonl",
                all_train,
            )
            checksums = {
                str(path.relative_to(manifests)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(manifests.rglob("*"))
                if path.is_file()
            }
            write_json(manifests / "checksums.json", checksums)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "-qm",
                    "baseline",
                ],
                check=True,
            )
            initialize(run, repo, manifests, protocol, "common-commit")
            baseline_job = prepare_next(run)
            self.assertEqual(baseline_job["split"], "validation")
            summary = root / "summary.json"
            score_summary(summary, 24, 24, baseline_job)
            stale = json.loads(summary.read_text())
            stale["rows"][0]["evaluation_job_id"] = "f" * 24
            summary.write_text(json.dumps(stale))
            with self.assertRaises(ValueError):
                ingest_validation(run, summary)
            score_summary(summary, 24, 24, baseline_job)
            ingest_validation(run, summary)

            round_half_units = (25, 25, 24)
            for round_index, candidate_half_units in enumerate(round_half_units, start=1):
                train_job = prepare_next(run)
                self.assertEqual(train_job["split"], "train")
                train_summary = root / f"train_{round_index}.json"
                score_summary(train_summary, 12, 12, train_job)
                train_evaluations = root / f"train_{round_index}_evaluations.jsonl"
                write_jsonl(
                    train_evaluations,
                    json.loads(train_summary.read_text())["rows"],
                )
                sample_dir = root / f"samples_{round_index}"
                samples(
                    sample_dir, train_job, train_summary, train_evaluations
                )
                ingest_train(
                    run, train_summary, sample_dir, train_evaluations
                )
                next_action = prepare_next(run)
                self.assertEqual(next_action["action"], "propose")
                proposal_path = root / f"proposal_{round_index}.json"
                proposal(
                    proposal_path,
                    round_index,
                    f"Round {round_index} rule.",
                    next_action,
                    sample_dir,
                )
                ingest_proposal(run, proposal_path)
                validation_job = prepare_next(run)
                score_summary(
                    summary, 24, candidate_half_units, validation_job
                )
                result = ingest_validation(run, summary)
                expected = ("accept_new_best", "flat", "reject")[round_index - 1]
                self.assertEqual(result["action"], expected)

            post_final = prepare_next(run)
            self.assertEqual(post_final["split"], "post_final_train")
            self.assertFalse(post_final["consumed_by_future_proposal"])
            self.assertEqual(
                len((run / "private/post_final/post_final_train_executor.jsonl").read_text().splitlines()),
                12,
            )
            post_summary = root / "post_summary.json"
            score_summary(post_summary, 12, 12, post_final)
            post_evaluations = root / "post_evaluations.jsonl"
            write_jsonl(
                post_evaluations,
                json.loads(post_summary.read_text())["rows"],
            )
            post_samples = root / "post_samples"
            samples(
                post_samples, post_final, post_summary, post_evaluations
            )
            ingest_train(
                run, post_summary, post_samples, post_evaluations
            )
            lock = finalize(run)
            self.assertEqual(lock["best_round"], 1)
            self.assertIn("Round 1 rule.", skill.read_text())
            self.assertNotIn("Round 2 rule.", skill.read_text())
            self.assertTrue(audit(run)["passed"])


if __name__ == "__main__":
    unittest.main()
