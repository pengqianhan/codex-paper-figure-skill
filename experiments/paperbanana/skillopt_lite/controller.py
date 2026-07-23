#!/usr/bin/env python3
"""Audit-friendly SkillOpt-Lite state machine for Codex subagent orchestration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import random
import shutil
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any


ROUNDS = 3
TRAIN_SIZE = 12
VALIDATION_SIZE = 24
DEAD_BAND = 0.01
MAX_EDITS = 4
MAX_SKILL_BYTES = 20_000
POST_FINAL_SEED = 4
SKILL_RELATIVE_PATH = "codex-paper-figure-skill/SKILL.md"
STATE_FILE = "state.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def load_state(run_dir: Path) -> dict[str, Any]:
    path = run_dir / STATE_FILE
    if not path.is_file():
        raise FileNotFoundError(f"run is not initialized: {path}")
    return read_json(path)


def save_state(run_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now()
    write_json(run_dir / STATE_FILE, state)


def git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    # Preserve the leading status column from `git status --porcelain`.
    return result.stdout.rstrip("\n")


def assert_only_skill_mutable(state: dict[str, Any], *, allow_clean: bool = True) -> None:
    repo_root = Path(state["repo_root"])
    skill_relative = state["skill_relative_path"]
    entries = git(repo_root, "status", "--porcelain", "--untracked-files=all").splitlines()
    unexpected = []
    skill_seen = False
    for entry in entries:
        path = entry[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        if path == skill_relative and entry[:2] in {" M", "M "}:
            skill_seen = True
        else:
            unexpected.append(entry)
    if unexpected:
        raise RuntimeError(f"immutable experiment files changed: {unexpected}")
    if not allow_clean and not skill_seen:
        raise RuntimeError("expected the candidate skill to be the only modified file")


def verify_manifest_root(manifest_root: Path) -> str:
    forbidden = [
        path
        for path in manifest_root.rglob("*")
        if path.is_file() and "test" in path.name.lower()
    ]
    if forbidden:
        raise RuntimeError(f"test artifacts were materialized before freeze: {forbidden}")
    checksums_path = manifest_root / "checksums.json"
    if not checksums_path.is_file():
        raise FileNotFoundError(checksums_path)
    expected = read_json(checksums_path)
    actual_paths = {
        str(path.relative_to(manifest_root)): path
        for path in manifest_root.rglob("*")
        if path.is_file() and path != checksums_path
    }
    if set(expected) != set(actual_paths):
        raise RuntimeError(
            "manifest file set differs from checksums.json: "
            f"expected={sorted(expected)}, actual={sorted(actual_paths)}"
        )
    mismatched = [
        relative
        for relative, path in actual_paths.items()
        if expected[relative] != sha256(path)
    ]
    if mismatched:
        raise RuntimeError(f"manifest checksum mismatch: {mismatched}")
    return sha256(checksums_path)


def assert_environment_locked(state: dict[str, Any]) -> None:
    if sha256(Path(state["protocol_path"])) != state["protocol_sha256"]:
        raise RuntimeError("protocol changed after SkillOpt-Lite initialization")
    if (
        verify_manifest_root(Path(state["manifest_root"]))
        != state["manifest_checksums_sha256"]
    ):
        raise RuntimeError("manifest checksum lock changed after initialization")


def append_event(
    run_dir: Path,
    state: dict[str, Any],
    kind: str,
    payload: dict[str, Any],
) -> None:
    event = {
        "index": int(state.get("event_count", 0)),
        "timestamp": now(),
        "kind": kind,
        "payload": payload,
        "previous_event_sha256": state.get("event_head_sha256"),
    }
    event["event_sha256"] = canonical_sha(event)
    with (run_dir / "events.jsonl").open("a") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    state["event_count"] = event["index"] + 1
    state["event_head_sha256"] = event["event_sha256"]
    save_state(run_dir, state)


def filtered_validation_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": summary.get("count"),
        "mean_overall_score": summary.get("mean_overall_score"),
        "hard_gate_failures": summary.get("hard_gate_failures"),
        "overall_counts": summary.get("overall_counts", {}),
        "dimension_counts": summary.get("dimension_counts", {}),
    }


def load_pending_job(state: dict[str, Any]) -> dict[str, Any]:
    pending_path = state.get("pending_job")
    if not pending_path:
        raise RuntimeError("no pending job")
    path = Path(pending_path)
    if sha256(path) != state.get("pending_job_sha256"):
        raise RuntimeError("pending job file changed after publication")
    return read_json(path)


def validate_evaluation_receipt(
    state: dict[str, Any], summary: dict[str, Any]
) -> dict[str, Any]:
    job = load_pending_job(state)
    if job.get("action") != "evaluate":
        raise RuntimeError("pending job is not an evaluation")
    receipt = summary.get("evaluation_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("evaluation summary is missing its bound receipt")
    expected = {
        "job_id": job["job_id"],
        "skill_sha256": job["skill_sha256"],
        "executor_manifest_sha256": job["executor_manifest_sha256"],
        "judge_manifest_sha256": job["judge_manifest_sha256"],
        "completed_count": job["expected_count"],
        "status": "complete",
    }
    if receipt != expected:
        raise ValueError(f"evaluation receipt mismatch: expected {expected}, found {receipt}")
    rows = summary.get("rows")
    if not isinstance(rows, list):
        raise ValueError("evaluation summary must retain provenance-bearing rows")
    expected_case_ids = {
        str(row["case_id"]) for row in _read_jsonl(Path(job["executor_manifest"]))
    }
    actual_case_ids = [str(row.get("case_id", "")) for row in rows]
    if len(actual_case_ids) != len(set(actual_case_ids)) or set(
        actual_case_ids
    ) != expected_case_ids:
        raise ValueError("evaluation summary rows do not match the pending job cases")
    expected_provenance = {
        "evaluation_job_id": job["job_id"],
        "skill_sha256": job["skill_sha256"],
        "executor_manifest_sha256": job["executor_manifest_sha256"],
        "judge_manifest_sha256": job["judge_manifest_sha256"],
    }
    for row in rows:
        for key, value in expected_provenance.items():
            if row.get(key) != value:
                raise ValueError(
                    f"evaluation row provenance mismatch for {row.get('case_id')}: {key}"
                )
        status_sha = row.get("executor_status_sha256")
        if not isinstance(status_sha, str) or len(status_sha) != 64:
            raise ValueError("evaluation row is missing executor status provenance")
    return job


def load_score_summary(
    path: Path, expected_count: int
) -> tuple[dict[str, Any], float, int]:
    summary = read_json(path)
    if int(summary.get("count", -1)) != expected_count:
        raise ValueError(
            f"expected {expected_count} evaluated cases, found {summary.get('count')}"
        )
    counts = summary.get("overall_counts")
    if not isinstance(counts, dict):
        raise ValueError("summary must contain overall_counts")
    normalized_counts = {
        outcome: int(counts.get(outcome, 0)) for outcome in ("Human", "Tie", "Model")
    }
    if sum(normalized_counts.values()) != expected_count:
        raise ValueError(
            f"overall_counts must sum to {expected_count}, found {normalized_counts}"
        )
    half_units = 2 * normalized_counts["Model"] + normalized_counts["Tie"]
    exact_score = Fraction(half_units, 2 * expected_count)
    score = float(exact_score)
    reported_score = float(summary.get("mean_overall_score", -1.0))
    if abs(reported_score - score) > 1e-12:
        raise ValueError(
            "mean_overall_score disagrees with exact outcome half-units: "
            f"reported={reported_score}, exact={score}"
        )
    return summary, score, half_units


def validate_samples(
    samples_dir: Path,
    job: dict[str, Any],
    summary_path: Path,
    evaluations_path: Path,
    expected_count: int = TRAIN_SIZE,
) -> tuple[dict[str, int], list[str]]:
    files = {
        label: list((samples_dir / label).glob("*.md"))
        for label in ("failed", "passed")
    }
    counts = {label: len(paths) for label, paths in files.items()}
    if sum(counts.values()) != expected_count:
        raise ValueError(f"expected {expected_count} train samples, found {counts}")
    case_ids = sorted(path.stem for paths in files.values() for path in paths)
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("train samples contain duplicate case IDs")
    if any(
        len(case_id) != len("case_") + 16
        or not case_id.startswith("case_")
        or any(character not in "0123456789abcdef" for character in case_id[5:])
        for case_id in case_ids
    ):
        raise ValueError("train sample filenames must be opaque case IDs")
    expected_case_ids = {
        str(row["case_id"]) for row in _read_jsonl(Path(job["executor_manifest"]))
    }
    if set(case_ids) != expected_case_ids:
        raise ValueError("train sample IDs do not match the pending executor manifest")
    evaluations = _read_jsonl(evaluations_path)
    if {str(row.get("case_id", "")) for row in evaluations} != expected_case_ids:
        raise ValueError("train evaluation bundles do not match the pending job cases")
    expected_provenance = {
        "evaluation_job_id": job["job_id"],
        "skill_sha256": job["skill_sha256"],
        "executor_manifest_sha256": job["executor_manifest_sha256"],
        "judge_manifest_sha256": job["judge_manifest_sha256"],
    }
    for row in evaluations:
        for key, value in expected_provenance.items():
            if row.get(key) != value:
                raise ValueError(
                    f"train evaluation provenance mismatch for {row.get('case_id')}: {key}"
                )
    receipt_path = samples_dir / "_receipt.json"
    if not receipt_path.is_file():
        raise FileNotFoundError(f"train samples are missing a bound receipt: {receipt_path}")
    receipt = read_json(receipt_path)
    sample_hashes = {
        str(path.relative_to(samples_dir)): sha256(path)
        for paths in files.values()
        for path in paths
    }
    expected_receipt = {
        "job_id": job["job_id"],
        "skill_sha256": job["skill_sha256"],
        "executor_manifest_sha256": job["executor_manifest_sha256"],
        "judge_manifest_sha256": job["judge_manifest_sha256"],
        "evaluation_summary_sha256": sha256(summary_path),
        "evaluation_bundles_sha256": sha256(evaluations_path),
        "sample_files": sample_hashes,
    }
    if receipt != expected_receipt:
        raise ValueError("train sample receipt does not match the pending job and files")
    return counts, case_ids


def apply_edits(skill: str, edits: list[dict[str, Any]]) -> str:
    if len(edits) > MAX_EDITS:
        raise ValueError(f"at most {MAX_EDITS} edits are allowed")
    updated = skill
    for index, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            raise ValueError(f"edit {index} must be an object")
        op = str(edit.get("op", ""))
        target = str(edit.get("target", ""))
        content = str(edit.get("content", ""))
        if op == "append":
            if target or not content.strip():
                raise ValueError(f"append edit {index} requires content and no target")
            updated = updated.rstrip() + "\n\n" + content.strip() + "\n"
            continue
        if op not in {"insert_after", "replace", "delete"}:
            raise ValueError(f"unsupported edit operation at {index}: {op!r}")
        if not target:
            raise ValueError(f"edit {index} requires an exact target")
        occurrences = updated.count(target)
        if occurrences != 1:
            raise ValueError(
                f"edit {index} target must occur exactly once, found {occurrences}"
            )
        if op == "insert_after":
            if not content.strip():
                raise ValueError(f"insert_after edit {index} requires content")
            updated = updated.replace(target, target + "\n" + content.strip(), 1)
        elif op == "replace":
            if not content:
                raise ValueError(f"replace edit {index} requires content")
            updated = updated.replace(target, content, 1)
        else:
            if content:
                raise ValueError(f"delete edit {index} must not contain content")
            updated = updated.replace(target, "", 1)
    if not updated.strip():
        raise ValueError("edits produced an empty skill")
    validate_skill_document(updated)
    return updated


def validate_skill_document(skill: str) -> None:
    if len(skill.encode()) > MAX_SKILL_BYTES:
        raise ValueError(f"candidate skill exceeds {MAX_SKILL_BYTES} bytes")
    if not skill.startswith("---\n") or "\n---\n" not in skill[4:]:
        raise ValueError("candidate skill must retain YAML frontmatter")
    frontmatter = skill.split("\n---\n", 1)[0][4:]
    fields = {}
    for line in frontmatter.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    if fields.get("name") != "codex-paper-figure-skill":
        raise ValueError("candidate skill must retain its name")
    if not fields.get("description"):
        raise ValueError("candidate skill must retain a non-empty description")
    lowered = skill.lower()
    forbidden = (
        "paperbananabench",
        "/users/pengqianhan/downloads/",
        "path_to_gt_image",
        "judge-only",
    )
    leaked = [token for token in forbidden if token in lowered]
    if leaked or re.search(r"\b(?:case_[0-9a-f]{16}|(?:ref|test)_\d+)\b", lowered):
        raise ValueError("candidate skill contains benchmark-specific leakage")


def validate_proposal(
    proposal: dict[str, Any],
    round_index: int,
    sample_counts: dict[str, int],
    sample_case_ids: list[str],
) -> list[dict[str, Any]]:
    required = {
        "round",
        "job_id",
        "base_skill_sha256",
        "sampling_report",
        "diagnosis",
        "edits",
        "expected_impact",
        "regressions_to_watch",
    }
    if set(proposal) != required:
        raise ValueError(f"proposal keys must be exactly {sorted(required)}")
    if int(proposal.get("round", -1)) != round_index:
        raise ValueError("proposal round does not match controller state")
    report = proposal.get("sampling_report")
    if not isinstance(report, dict):
        raise ValueError("sampling_report must be an object")
    expected_report = {
        "failed_read": sample_counts["failed"],
        "failed_total": sample_counts["failed"],
        "passed_read": sample_counts["passed"],
        "passed_total": sample_counts["passed"],
    }
    if report != expected_report:
        raise ValueError(
            "the proposer must read the complete 12-case batch; "
            f"expected {expected_report}, found {report}"
        )
    diagnosis = proposal.get("diagnosis")
    if not isinstance(diagnosis, list) or len(diagnosis) > 4:
        raise ValueError("diagnosis must be an array with at most four entries")
    edits = proposal.get("edits")
    if not isinstance(edits, list) or len(edits) > MAX_EDITS:
        raise ValueError(f"edits must be an array with at most {MAX_EDITS} entries")
    for label, entries in (("diagnosis", diagnosis), ("edits", edits)):
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"{label} entry {index} must be an object")
            expected_keys = (
                {"pattern", "support_case_ids"}
                if label == "diagnosis"
                else {"op", "target", "content", "support_case_ids"}
            )
            if set(entry) != expected_keys:
                raise ValueError(
                    f"{label} entry {index} keys must be exactly {sorted(expected_keys)}"
                )
            support = entry.get("support_case_ids")
            if not isinstance(support, list) or len(set(support)) < 2:
                raise ValueError(f"{label} entry {index} needs at least two supporting cases")
            unknown = sorted(set(str(case_id) for case_id in support) - set(sample_case_ids))
            if unknown:
                raise ValueError(
                    f"{label} entry {index} cites cases outside the latest train batch: {unknown}"
                )
    if not str(proposal.get("expected_impact", "")).strip():
        raise ValueError("expected_impact must not be empty")
    if not isinstance(proposal.get("regressions_to_watch"), list):
        raise ValueError("regressions_to_watch must be an array")
    return edits


def decide_gate(
    candidate_half_units: int,
    current_half_units: int,
    best_half_units: int,
    count: int = VALIDATION_SIZE,
) -> str:
    delta = Fraction(candidate_half_units - current_half_units, 2 * count)
    dead_band = Fraction(1, 100)
    if delta >= dead_band:
        return (
            "accept_new_best"
            if candidate_half_units > best_half_units
            else "accept"
        )
    if delta <= -dead_band:
        return "reject"
    return "flat"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
        rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def build_post_final_manifests(
    manifest_root: Path, private_output_dir: Path
) -> tuple[Path, Path]:
    executor_pool = _read_jsonl(
        manifest_root / "controller-only" / "train_pool_executor.jsonl"
    )
    executor_rows = {str(row["case_id"]): row for row in executor_pool}
    judge_rows = {
        str(row["case_id"]): row
        for row in _read_jsonl(
            manifest_root / "controller-only" / "train_pool_judge.jsonl"
        )
    }
    if len(executor_rows) != 36 or set(executor_rows) != set(judge_rows):
        raise ValueError("expected 36 aligned train rows before post-final sampling")
    selected_ids = [
        str(row["case_id"])
        for row in random.Random(POST_FINAL_SEED).sample(
            executor_pool, TRAIN_SIZE
        )
    ]
    executor_path = private_output_dir / "post_final_train_executor.jsonl"
    judge_path = private_output_dir / "judge-only" / "post_final_train.jsonl"
    _write_jsonl(executor_path, [executor_rows[case_id] for case_id in selected_ids])
    _write_jsonl(judge_path, [judge_rows[case_id] for case_id in selected_ids])
    return executor_path, judge_path


def initialize(
    run_dir: Path,
    repo_root: Path,
    manifest_root: Path,
    protocol_path: Path,
    common_scaffold_commit: str,
) -> dict[str, Any]:
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"run directory is not empty: {run_dir}")
    if git(repo_root, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("SkillOpt-Lite worktree must be clean at initialization")
    skill_path = repo_root / SKILL_RELATIVE_PATH
    if not skill_path.is_file():
        raise FileNotFoundError(skill_path)
    validate_skill_document(skill_path.read_text())
    for required in (
        manifest_root / "validation_executor.jsonl",
        manifest_root / "judge-only" / "validation.jsonl",
    ):
        if not required.is_file():
            raise FileNotFoundError(required)
    manifest_checksums_sha256 = verify_manifest_root(manifest_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    history = run_dir / "history"
    history.mkdir()
    baseline = history / "round0__best.md"
    shutil.copy2(skill_path, baseline)
    state = {
        "schema_version": 1,
        "method": "SkillOpt-Lite",
        "status": "active",
        "phase": "baseline_validation",
        "round": 0,
        "rounds": ROUNDS,
        "dead_band": DEAD_BAND,
        "max_edits": MAX_EDITS,
        "repo_root": str(repo_root.resolve()),
        "skill_relative_path": SKILL_RELATIVE_PATH,
        "skill_path": str(skill_path.resolve()),
        "manifest_root": str(manifest_root.resolve()),
        "manifest_checksums_sha256": manifest_checksums_sha256,
        "protocol_path": str(protocol_path.resolve()),
        "protocol_sha256": sha256(protocol_path),
        "adapter_commit": git(repo_root, "rev-parse", "HEAD"),
        "common_scaffold_commit": common_scaffold_commit,
        "baseline_skill_sha256": sha256(skill_path),
        "active_skill_sha256": sha256(skill_path),
        "current_score": None,
        "current_half_units": None,
        "active_last_observed_score": None,
        "active_last_observed_half_units": None,
        "best_score": None,
        "best_half_units": None,
        "best_round": 0,
        "best_snapshot": str(baseline.resolve()),
        "best_skill_sha256": sha256(baseline),
        "noop_streak": 0,
        "regression_streak": 0,
        "latest_samples_dir": None,
        "latest_sample_counts": None,
        "latest_sample_case_ids": None,
        "round_records": [],
        "created_at": now(),
        "updated_at": now(),
        "event_count": 0,
        "event_head_sha256": None,
        "pending_job": None,
        "pending_job_sha256": None,
    }
    save_state(run_dir, state)
    append_event(
        run_dir,
        state,
        "initialized",
        {
            "adapter_commit": state["adapter_commit"],
            "common_scaffold_commit": common_scaffold_commit,
            "baseline_skill_sha256": state["baseline_skill_sha256"],
        },
    )
    return state


def _action_for_evaluation(
    state: dict[str, Any], split: str, executor_manifest: Path, judge_manifest: Path
) -> dict[str, Any]:
    expected_count = VALIDATION_SIZE if split == "validation" else TRAIN_SIZE
    return {
        "action": "evaluate",
        "split": split,
        "round": state["round"],
        "skill_path": state["skill_path"],
        "skill_sha256": sha256(Path(state["skill_path"])),
        "executor_manifest": str(executor_manifest),
        "executor_manifest_sha256": sha256(executor_manifest),
        "judge_manifest": str(judge_manifest),
        "judge_manifest_sha256": sha256(judge_manifest),
        "expected_count": expected_count,
        "roles": [
            {
                "role": "executor",
                "codex_subagent": True,
                "model": "gpt-5.6-sol",
                "reasoning_effort": "medium",
                "fork_turns": "none",
            },
            {
                "role": "judge",
                "codex_subagent": True,
                "model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "fork_turns": "none",
            },
        ],
    }


def publish_job(
    run_dir: Path, state: dict[str, Any], action: dict[str, Any]
) -> dict[str, Any]:
    pending = state.get("pending_job")
    if pending:
        return load_pending_job(state)
    job = dict(action)
    job["phase"] = state["phase"]
    job["job_id"] = canonical_sha(job)[:24]
    job_path = run_dir / "jobs" / f"{job['job_id']}.json"
    write_json(job_path, job)
    state["pending_job"] = str(job_path.resolve())
    state["pending_job_sha256"] = sha256(job_path)
    append_event(
        run_dir,
        state,
        "job_prepared",
        {
            "job_id": job["job_id"],
            "action": job["action"],
            "phase": state["phase"],
            "job_sha256": sha256(job_path),
        },
    )
    return job


def write_proposer_packet(state: dict[str, Any], job: dict[str, Any]) -> None:
    packet = Path(job["packet"])
    proposal_output = Path(job["proposal_output"])
    packet.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "# SkillOpt-Lite improve round\n\n"
        "Run this as a fresh Codex proposer subagent with `fork_turns=none`.\n\n"
        f"- Round: {job['round']}/{ROUNDS}\n"
        f"- Job ID: `{job['job_id']}`\n"
        f"- Base skill SHA-256: `{job['base_skill_sha256']}`\n"
        f"- Current skill: `{state['skill_path']}`\n"
        f"- Latest samples: `{state['latest_samples_dir']}`\n"
        f"- Static proposer instructions: `{Path(state['repo_root']) / 'experiments/paperbanana/prompts/skillopt_lite_proposer.md'}`\n"
        f"- Proposal schema: `{Path(state['repo_root']) / 'experiments/paperbanana/schemas/skillopt_proposal.schema.json'}`\n"
        f"- Write strict JSON proposal to: `{proposal_output}`\n"
        f"- Current validation score: {state['current_score']}\n"
        f"- Best validation score: {state['best_score']} at round {state['best_round']}\n\n"
        "Do not read validation jobs, judge-only manifests, test data, another worktree, "
        "or any proposal from an earlier round. Do not edit the repository directly.\n"
    )
    temporary = packet.with_suffix(packet.suffix + ".tmp")
    temporary.write_text(payload)
    temporary.replace(packet)


def prepare_next(run_dir: Path) -> dict[str, Any]:
    state = load_state(run_dir)
    assert_only_skill_mutable(state)
    assert_environment_locked(state)
    if state.get("pending_job"):
        job = load_pending_job(state)
        if job.get("action") == "propose":
            write_proposer_packet(state, job)
        return job
    manifest_root = Path(state["manifest_root"])
    phase = state["phase"]
    if phase in {"baseline_validation", "candidate_validation"}:
        return publish_job(
            run_dir,
            state,
            _action_for_evaluation(
                state,
                "validation",
                manifest_root / "validation_executor.jsonl",
                manifest_root / "judge-only" / "validation.jsonl",
            ),
        )
    if phase == "train":
        round_index = int(state["round"])
        return publish_job(
            run_dir,
            state,
            _action_for_evaluation(
                state,
                "train",
                manifest_root / f"train_round_{round_index}_executor.jsonl",
                manifest_root / "judge-only" / f"train_round_{round_index}.jsonl",
            ),
        )
    if phase == "post_final_train":
        executor, judge = build_post_final_manifests(
            manifest_root, run_dir / "private" / "post_final"
        )
        action = _action_for_evaluation(state, "post_final_train", executor, judge)
        action["consumed_by_future_proposal"] = False
        action["method_fidelity_note"] = (
            "SkillOpt-Lite always performs the next train rollout after every gate, "
            "including the final round. This deterministic seed-4 batch is archived "
            "but not consumed by another proposal."
        )
        return publish_job(run_dir, state, action)
    if phase == "proposal":
        round_index = int(state["round"])
        packet = run_dir / "packets" / f"round_{round_index}_proposer.md"
        proposal_output = run_dir / "proposals" / f"round_{round_index}.json"
        action = {
            "action": "propose",
            "round": round_index,
            "base_skill_sha256": sha256(Path(state["skill_path"])),
            "packet": str(packet),
            "proposal_output": str(proposal_output),
            "role": {
                "role": "proposer",
                "codex_subagent": True,
                "model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "fork_turns": "none",
            },
        }
        job = publish_job(run_dir, state, action)
        write_proposer_packet(state, job)
        return job
    if phase == "ready_to_finalize":
        return {"action": "finalize", "test_is_still_sealed": True}
    if phase == "frozen":
        return {"action": "none", "status": "frozen"}
    raise ValueError(f"unknown phase: {phase}")


def ingest_train(
    run_dir: Path,
    summary_path: Path,
    samples_dir: Path,
    evaluations_path: Path,
) -> dict[str, Any]:
    state = load_state(run_dir)
    assert_only_skill_mutable(state)
    assert_environment_locked(state)
    if state["phase"] not in {"train", "post_final_train"}:
        raise RuntimeError(f"cannot ingest train results during {state['phase']}")
    summary, incidental_score, incidental_half_units = load_score_summary(
        summary_path, TRAIN_SIZE
    )
    job = validate_evaluation_receipt(state, summary)
    counts, sample_case_ids = validate_samples(
        samples_dir, job, summary_path, evaluations_path
    )
    post_final = state["phase"] == "post_final_train"
    record = {
        "round": state["round"],
        "job_id": job["job_id"],
        "post_final": post_final,
        "summary_sha256": sha256(summary_path),
        "samples_dir": str(samples_dir.resolve()),
        "evaluation_bundles_sha256": sha256(evaluations_path),
        "sample_counts": counts,
        "incidental_train_score": incidental_score,
        "incidental_train_half_units": incidental_half_units,
    }
    state["latest_samples_dir"] = str(samples_dir.resolve())
    state["latest_sample_counts"] = counts
    state["latest_sample_case_ids"] = sample_case_ids
    state["phase"] = "ready_to_finalize" if post_final else "proposal"
    state["pending_job"] = None
    state["pending_job_sha256"] = None
    append_event(run_dir, state, "train_ingested", record)
    return record


def ingest_proposal(run_dir: Path, proposal_path: Path) -> dict[str, Any]:
    state = load_state(run_dir)
    assert_only_skill_mutable(state)
    assert_environment_locked(state)
    if state["phase"] != "proposal":
        raise RuntimeError(f"cannot ingest a proposal during {state['phase']}")
    if not state.get("pending_job"):
        raise RuntimeError("no pending proposer job")
    job = load_pending_job(state)
    if job.get("action") != "propose":
        raise RuntimeError("pending job is not a proposer job")
    proposal = read_json(proposal_path)
    if proposal.get("job_id") != job["job_id"]:
        raise ValueError("proposal job_id does not match the pending job")
    if proposal.get("base_skill_sha256") != job["base_skill_sha256"]:
        raise ValueError("proposal base_skill_sha256 does not match the pending job")
    edits = validate_proposal(
        proposal,
        int(state["round"]),
        dict(state["latest_sample_counts"]),
        list(state["latest_sample_case_ids"]),
    )
    skill_path = Path(state["skill_path"])
    history = run_dir / "history"
    round_index = int(state["round"])
    before = history / f"round{round_index}__before.md"
    candidate = history / f"round{round_index}__candidate.md"
    shutil.copy2(skill_path, before)
    updated = apply_edits(skill_path.read_text(), edits)
    skill_path.write_text(updated)
    shutil.copy2(skill_path, candidate)
    if sha256(before) == sha256(candidate) and edits:
        raise ValueError("proposal claimed edits but did not change the skill")
    archive = run_dir / "proposals" / f"round_{round_index}.json"
    write_json(archive, proposal)
    state["pending_before_snapshot"] = str(before.resolve())
    state["pending_candidate_snapshot"] = str(candidate.resolve())
    state["pending_proposal_sha256"] = sha256(archive)
    state["pending_before_observed_score"] = state["active_last_observed_score"]
    state["pending_before_observed_half_units"] = state[
        "active_last_observed_half_units"
    ]
    state["active_last_observed_score"] = None
    state["active_last_observed_half_units"] = None
    state["active_skill_sha256"] = sha256(skill_path)
    state["phase"] = "candidate_validation"
    state["pending_job"] = None
    state["pending_job_sha256"] = None
    assert_only_skill_mutable(state, allow_clean=not bool(edits))
    append_event(
        run_dir,
        state,
        "proposal_applied",
        {
            "round": round_index,
            "proposal_sha256": state["pending_proposal_sha256"],
            "before_sha256": sha256(before),
            "candidate_sha256": sha256(candidate),
            "edit_count": len(edits),
        },
    )
    return proposal


def ingest_validation(run_dir: Path, summary_path: Path) -> dict[str, Any]:
    state = load_state(run_dir)
    assert_only_skill_mutable(state)
    assert_environment_locked(state)
    if state["phase"] not in {"baseline_validation", "candidate_validation"}:
        raise RuntimeError(f"cannot ingest validation during {state['phase']}")
    summary, score, half_units = load_score_summary(summary_path, VALIDATION_SIZE)
    job = validate_evaluation_receipt(state, summary)
    safe_summary = filtered_validation_summary(summary)
    safe_summary_sha = canonical_sha(safe_summary)
    skill_path = Path(state["skill_path"])
    if state["phase"] == "baseline_validation":
        state["round"] = 1
        state["current_score"] = score
        state["current_half_units"] = half_units
        state["active_last_observed_score"] = score
        state["active_last_observed_half_units"] = half_units
        state["best_score"] = score
        state["best_half_units"] = half_units
        state["phase"] = "train"
        state["baseline_validation_summary"] = safe_summary
        state["baseline_validation_summary_sha256"] = safe_summary_sha
        result = {
            "round": 0,
            "job_id": job["job_id"],
            "score": score,
            "half_units": half_units,
            "n": VALIDATION_SIZE,
            "action": "baseline",
        }
        state["pending_job"] = None
        state["pending_job_sha256"] = None
        append_event(run_dir, state, "baseline_validation_ingested", result)
        return result

    round_index = int(state["round"])
    current_score = float(state["current_score"])
    best_score = float(state["best_score"])
    current_half_units = int(state["current_half_units"])
    best_half_units = int(state["best_half_units"])
    action = decide_gate(
        half_units, current_half_units, best_half_units, VALIDATION_SIZE
    )
    delta_fraction = Fraction(
        half_units - current_half_units, 2 * VALIDATION_SIZE
    )
    delta = float(delta_fraction)
    before = Path(state["pending_before_snapshot"])
    candidate = Path(state["pending_candidate_snapshot"])
    best_snapshot = Path(state["best_snapshot"])
    if action == "reject":
        shutil.copy2(before, skill_path)
        state["active_last_observed_score"] = state[
            "pending_before_observed_score"
        ]
        state["active_last_observed_half_units"] = state[
            "pending_before_observed_half_units"
        ]
        state["regression_streak"] += 1
        state["noop_streak"] = 0
    elif action == "flat":
        state["active_last_observed_score"] = score
        state["active_last_observed_half_units"] = half_units
        state["noop_streak"] += 1
        state["regression_streak"] = 0
    else:
        state["current_score"] = score
        state["current_half_units"] = half_units
        state["active_last_observed_score"] = score
        state["active_last_observed_half_units"] = half_units
        state["noop_streak"] = 0
        state["regression_streak"] = 0
        if action == "accept_new_best":
            best_snapshot = run_dir / "history" / f"round{round_index}__best.md"
            shutil.copy2(candidate, best_snapshot)
            state["best_score"] = score
            state["best_half_units"] = half_units
            state["best_round"] = round_index
            state["best_snapshot"] = str(best_snapshot.resolve())
            state["best_skill_sha256"] = sha256(best_snapshot)
    after = run_dir / "history" / f"round{round_index}__after.md"
    shutil.copy2(skill_path, after)
    state["active_skill_sha256"] = sha256(skill_path)
    record = {
        "round": round_index,
        "job_id": job["job_id"],
        "candidate_score": score,
        "candidate_half_units": half_units,
        "reference_score": current_score,
        "reference_half_units": current_half_units,
        "delta": delta,
        "delta_fraction": f"{delta_fraction.numerator}/{delta_fraction.denominator}",
        "action": action,
        "validation_summary": safe_summary,
        "validation_summary_sha256": safe_summary_sha,
        "before_sha256": sha256(before),
        "candidate_sha256": sha256(candidate),
        "after_sha256": sha256(after),
        "best_score_after": state["best_score"],
        "best_half_units_after": state["best_half_units"],
        "best_round_after": state["best_round"],
        "active_last_observed_score_after": state["active_last_observed_score"],
        "active_last_observed_half_units_after": state[
            "active_last_observed_half_units"
        ],
    }
    state["round_records"].append(record)
    for key in (
        "pending_before_snapshot",
        "pending_candidate_snapshot",
        "pending_proposal_sha256",
        "pending_before_observed_score",
        "pending_before_observed_half_units",
    ):
        state.pop(key, None)
    if round_index == ROUNDS:
        state["phase"] = "post_final_train"
    else:
        state["round"] = round_index + 1
        state["phase"] = "train"
    state["pending_job"] = None
    state["pending_job_sha256"] = None
    append_event(run_dir, state, "validation_gate_applied", record)
    return record


def finalize(run_dir: Path) -> dict[str, Any]:
    state = load_state(run_dir)
    assert_only_skill_mutable(state)
    assert_environment_locked(state)
    if state["phase"] != "ready_to_finalize":
        raise RuntimeError(f"cannot finalize during {state['phase']}")
    skill_path = Path(state["skill_path"])
    best_snapshot = Path(state["best_snapshot"])
    shutil.copy2(best_snapshot, skill_path)
    final_skill = run_dir / "final" / "SKILL.md"
    final_skill.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_path, final_skill)
    final_lock = {
        "method": "SkillOpt-Lite",
        "frozen_at": now(),
        "final_skill_sha256": sha256(final_skill),
        "best_validation_score": state["best_score"],
        "best_validation_half_units": state["best_half_units"],
        "best_round": state["best_round"],
        "protocol_sha256": state["protocol_sha256"],
        "adapter_commit": state["adapter_commit"],
        "common_scaffold_commit": state["common_scaffold_commit"],
        "test_materialized": False,
    }
    write_json(run_dir / "final" / "lock.json", final_lock)
    state["active_skill_sha256"] = final_lock["final_skill_sha256"]
    state["active_last_observed_score"] = state["best_score"]
    state["active_last_observed_half_units"] = state["best_half_units"]
    state["final_skill"] = str(final_skill.resolve())
    state["final_lock"] = str((run_dir / "final" / "lock.json").resolve())
    state["phase"] = "frozen"
    state["status"] = "complete"
    append_event(run_dir, state, "finalized", final_lock)
    return final_lock


def audit(run_dir: Path) -> dict[str, Any]:
    state = load_state(run_dir)
    assert_only_skill_mutable(state)
    errors: list[str] = []
    try:
        assert_environment_locked(state)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        errors.append(str(exc))
    previous = None
    events = []
    for line_number, line in enumerate((run_dir / "events.jsonl").read_text().splitlines(), 1):
        event = json.loads(line)
        claimed = event.pop("event_sha256", None)
        if event.get("previous_event_sha256") != previous:
            errors.append(f"event {line_number} has a broken previous hash")
        computed = canonical_sha(event)
        if claimed != computed:
            errors.append(f"event {line_number} hash mismatch")
        previous = claimed
        event["event_sha256"] = claimed
        events.append(event)
    if len(events) != state["event_count"]:
        errors.append("event count mismatch")
    if previous != state["event_head_sha256"]:
        errors.append("event head mismatch")
    skill_sha = sha256(Path(state["skill_path"]))
    if skill_sha != state["active_skill_sha256"]:
        errors.append("active skill hash mismatch")
    if sha256(Path(state["best_snapshot"])) != state["best_skill_sha256"]:
        errors.append("best snapshot hash mismatch")
    if state.get("pending_job"):
        try:
            load_pending_job(state)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            errors.append(str(exc))
    return {
        "passed": not errors,
        "errors": errors,
        "phase": state["phase"],
        "event_count": len(events),
        "active_skill_sha256": skill_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--run-dir", type=Path, required=True)
    init_parser.add_argument("--repo-root", type=Path, required=True)
    init_parser.add_argument("--manifest-root", type=Path, required=True)
    init_parser.add_argument("--protocol", type=Path, required=True)
    init_parser.add_argument("--common-scaffold-commit", required=True)

    for name in ("prepare-next", "status", "audit", "finalize"):
        command = subparsers.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)

    train_parser = subparsers.add_parser("ingest-train")
    train_parser.add_argument("--run-dir", type=Path, required=True)
    train_parser.add_argument("--summary", type=Path, required=True)
    train_parser.add_argument("--samples-dir", type=Path, required=True)
    train_parser.add_argument("--evaluations", type=Path, required=True)

    proposal_parser = subparsers.add_parser("ingest-proposal")
    proposal_parser.add_argument("--run-dir", type=Path, required=True)
    proposal_parser.add_argument("--proposal", type=Path, required=True)

    validation_parser = subparsers.add_parser("ingest-validation")
    validation_parser.add_argument("--run-dir", type=Path, required=True)
    validation_parser.add_argument("--summary", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "init":
        result = initialize(
            args.run_dir,
            args.repo_root,
            args.manifest_root,
            args.protocol,
            args.common_scaffold_commit,
        )
    elif args.command == "prepare-next":
        result = prepare_next(args.run_dir)
    elif args.command == "ingest-train":
        result = ingest_train(
            args.run_dir, args.summary, args.samples_dir, args.evaluations
        )
    elif args.command == "ingest-proposal":
        result = ingest_proposal(args.run_dir, args.proposal)
    elif args.command == "ingest-validation":
        result = ingest_validation(args.run_dir, args.summary)
    elif args.command == "finalize":
        result = finalize(args.run_dir)
    elif args.command == "audit":
        result = audit(args.run_dir)
    else:
        result = load_state(args.run_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "audit" and not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
