#!/usr/bin/env python3
"""Build deterministic, leakage-resistant PaperBananaBench manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    from .sanitize_case import assert_manifest_safe, executor_case, judge_case
except ImportError:  # Direct script execution.
    from sanitize_case import assert_manifest_safe, executor_case, judge_case


SPLIT_SEED = 20260723
ORDER_SEED = 20260724
ANONYMIZATION_SEED = 20260725
CATEGORY_QUOTAS = {
    "agent_reasoning": {"train": 11, "validation": 7},
    "generative_learning": {"train": 9, "validation": 6},
    "science_applications": {"train": 6, "validation": 4},
    "vision_perception": {"train": 10, "validation": 7},
}
RATIO_ORDER = ("16:9", "21:9", "3:2")
TRAIN_BATCH_SEEDS = (1, 2, 3)


def _digest_key(seed: int, phase: str, item_id: str) -> str:
    return hashlib.sha256(f"{seed}|{phase}|{item_id}".encode()).hexdigest()


def _global_length_bins(items: list[dict[str, Any]]) -> dict[str, int]:
    ordered = sorted(
        items,
        key=lambda item: (len(str(item.get("content", ""))), str(item.get("id", ""))),
    )
    total = len(ordered)
    return {
        str(item.get("id", "")): min(2, (3 * rank) // total)
        for rank, item in enumerate(ordered)
    }


def _ratio(item: dict[str, Any]) -> str:
    return str((item.get("additional_info") or {}).get("rounded_ratio", "unknown"))


def _hamilton_take(
    items: list[dict[str, Any]],
    quota: int,
    phase: str,
    length_bins: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    buckets: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        buckets[(_ratio(item), length_bins[str(item.get("id", ""))])].append(item)
    total = len(items)
    allocation: dict[tuple[str, int], int] = {}
    remainders: list[tuple[float, int, int, tuple[str, int]]] = []
    allocated = 0
    for key, values in sorted(buckets.items()):
        ideal = quota * len(values) / total
        floor = int(ideal)
        allocation[key] = floor
        allocated += floor
        ratio_rank = RATIO_ORDER.index(key[0]) if key[0] in RATIO_ORDER else len(RATIO_ORDER)
        remainders.append((ideal - floor, ratio_rank, key[1], key))
    for _, _, _, key in sorted(remainders, key=lambda row: (-row[0], row[1], row[2]))[
        : quota - allocated
    ]:
        allocation[key] += 1
    selected: list[dict[str, Any]] = []
    for key, values in buckets.items():
        ordered = sorted(
            values,
            key=lambda item: _digest_key(SPLIT_SEED, phase, str(item.get("id", ""))),
        )
        selected.extend(ordered[: allocation[key]])
    selected_ids = {str(item.get("id", "")) for item in selected}
    remaining = [item for item in items if str(item.get("id", "")) not in selected_ids]
    if len(selected) != quota:
        raise AssertionError(f"Hamilton allocation failed for {phase}: {len(selected)}")
    return selected, remaining


def sample_train_batch(
    train_pool: list[dict[str, Any]], seed: int, batch_size: int = 12
) -> list[dict[str, Any]]:
    """Match SkillOpt-Lite's independently seeded sampling from one train pool."""

    ordered_pool = sorted(train_pool, key=lambda item: str(item.get("id", "")))
    if len(ordered_pool) < batch_size:
        raise ValueError("train pool is smaller than the requested batch")
    return random.Random(seed).sample(ordered_pool, batch_size)


def split_reference_items(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return train, validation, and unused items under fixed category quotas."""

    if len(items) != 298:
        raise ValueError(f"expected 298 ref items, found {len(items)}")
    ids = [str(item.get("id", "")) for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("ref IDs are not unique")
    ratios = {_ratio(item) for item in items}
    if ratios != set(RATIO_ORDER):
        raise ValueError(f"unexpected rounded ratios: {sorted(ratios)}")
    length_bins = _global_length_bins(items)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_category[str(item.get("category", "unknown"))].append(item)
    if set(by_category) != set(CATEGORY_QUOTAS):
        raise ValueError(
            f"unexpected categories: actual={sorted(by_category)}, "
            f"expected={sorted(CATEGORY_QUOTAS)}"
        )
    train: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    unused: list[dict[str, Any]] = []
    for category in sorted(CATEGORY_QUOTAS):
        category_items = by_category[category]
        val_part, remainder = _hamilton_take(
            category_items,
            CATEGORY_QUOTAS[category]["validation"],
            f"validation:{category}",
            length_bins,
        )
        train_part, remainder = _hamilton_take(
            remainder,
            CATEGORY_QUOTAS[category]["train"],
            f"train:{category}",
            length_bins,
        )
        train.extend(train_part)
        validation.extend(val_part)
        unused.extend(remainder)
    train.sort(
        key=lambda item: _digest_key(
            ORDER_SEED, "train-pool-order", str(item.get("id", ""))
        )
    )
    validation.sort(
        key=lambda item: _digest_key(
            ORDER_SEED, "validation-order", str(item.get("id", ""))
        )
    )
    unused.sort(key=lambda item: str(item.get("id", "")))
    if (len(train), len(validation), len(unused)) != (36, 24, 238):
        raise AssertionError("reference split sizes do not match the protocol")
    all_ids = [str(item.get("id", "")) for item in train + validation + unused]
    if len(all_ids) != len(set(all_ids)):
        raise AssertionError("reference split contains duplicate IDs")
    return train, validation, unused


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_alias_map(path: Path | None) -> tuple[dict[str, dict[str, str]], str | None]:
    if path is None:
        return {}, None
    payload = json.loads(path.read_text())
    aliases = payload.get("aliases")
    if not isinstance(aliases, dict):
        raise ValueError("alias map must contain an object named 'aliases'")
    normalized: dict[str, dict[str, str]] = {}
    for source_id, entry in aliases.items():
        if not isinstance(entry, dict):
            raise ValueError(f"alias entry must be an object: {source_id}")
        required = {"declared", "resolved", "sha256"}
        if set(entry) != required:
            raise ValueError(
                f"alias entry {source_id} must contain exactly {sorted(required)}"
            )
        normalized[str(source_id)] = {key: str(value) for key, value in entry.items()}
    return normalized, _sha256(path)


def resolve_ground_truth_paths(
    items: list[dict[str, Any]],
    dataset_root: Path,
    aliases: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Resolve every GT path exactly; never fuzzy-match a missing filename."""

    resolved: dict[str, str] = {}
    dataset_real = dataset_root.resolve()
    for item in items:
        source_id = str(item.get("id", ""))
        declared = str(item.get("path_to_gt_image", ""))
        relative = declared
        declared_path = dataset_root / declared
        if not declared_path.is_file():
            alias = aliases.get(source_id)
            if alias is None:
                raise FileNotFoundError(
                    f"missing GT for {source_id}: {declared}; provide a reviewed alias map"
                )
            if alias["declared"] != declared:
                raise ValueError(f"alias declared path mismatch for {source_id}")
            relative = alias["resolved"]
        target = (dataset_root / relative).resolve()
        if dataset_real not in target.parents or target.parent != (dataset_real / "images"):
            raise ValueError(f"GT path escapes dataset images directory: {source_id}")
        if not target.is_file():
            raise FileNotFoundError(f"resolved GT does not exist for {source_id}: {relative}")
        alias = aliases.get(source_id)
        if alias is not None:
            if alias["resolved"] != relative:
                raise ValueError(f"alias resolved path mismatch for {source_id}")
            if _sha256(target) != alias["sha256"]:
                raise ValueError(f"alias SHA-256 mismatch for {source_id}")
        resolved[source_id] = str(target)
    return resolved


def _judge_projection(
    item: dict[str, Any],
    split: str,
    dataset_root: Path,
    resolved_paths: dict[str, str],
) -> dict[str, Any]:
    row = judge_case(item, split, ANONYMIZATION_SEED, str(dataset_root))
    row["ground_truth_image"] = resolved_paths[str(item.get("id", ""))]
    return row


def build_manifests(
    dataset_root: Path,
    output_dir: Path,
    include_test: bool,
    alias_map_path: Path | None = None,
) -> None:
    ref_path = dataset_root / "ref.json"
    test_path = dataset_root / "test.json"
    aliases, alias_map_sha256 = load_alias_map(alias_map_path)
    ref_items = json.loads(ref_path.read_text())
    ref_resolved_paths = resolve_ground_truth_paths(ref_items, dataset_root, aliases)
    train, validation, unused = split_reference_items(ref_items)

    train_pool_rows = [
        executor_case(item, "train", ANONYMIZATION_SEED) for item in train
    ]
    train_pool_judge_rows = [
        _judge_projection(item, "train", dataset_root, ref_resolved_paths)
        for item in train
    ]
    validation_rows = [
        executor_case(item, "validation", ANONYMIZATION_SEED)
        for item in validation
    ]
    gt_basenames = {
        Path(str(item.get("path_to_gt_image", ""))).name for item in ref_items
    }
    assert_manifest_safe(
        train_pool_rows + validation_rows,
        dataset_root=str(dataset_root),
        ground_truth_basenames=gt_basenames,
    )
    validation_judge_rows = [
        _judge_projection(item, "validation", dataset_root, ref_resolved_paths)
        for item in validation
    ]

    train_executor_by_source = {
        str(item["id"]): row for item, row in zip(train, train_pool_rows)
    }
    train_judge_by_source = {
        str(item["id"]): row for item, row in zip(train, train_pool_judge_rows)
    }
    train_pool_source_order = sorted(
        (str(item["id"]) for item in train)
    )
    _write_jsonl(
        output_dir / "controller-only" / "train_pool_executor.jsonl",
        [train_executor_by_source[source_id] for source_id in train_pool_source_order],
    )
    _write_jsonl(
        output_dir / "controller-only" / "train_pool_judge.jsonl",
        [train_judge_by_source[source_id] for source_id in train_pool_source_order],
    )
    round_unique_ids: set[str] = set()
    for round_index, seed in enumerate(TRAIN_BATCH_SEEDS, start=1):
        batch = sample_train_batch(train, seed)
        source_ids = [str(item["id"]) for item in batch]
        round_unique_ids.update(source_ids)
        _write_jsonl(
            output_dir / f"train_round_{round_index}_executor.jsonl",
            [train_executor_by_source[source_id] for source_id in source_ids],
        )
        _write_jsonl(
            output_dir / "judge-only" / f"train_round_{round_index}.jsonl",
            [train_judge_by_source[source_id] for source_id in source_ids],
        )
    _write_jsonl(output_dir / "validation_executor.jsonl", validation_rows)
    _write_jsonl(
        output_dir / "judge-only" / "validation.jsonl", validation_judge_rows
    )

    test_count = None
    if include_test:
        test_items = json.loads(test_path.read_text())
        if len(test_items) != 292:
            raise ValueError(f"expected 292 test items, found {len(test_items)}")
        test_resolved_paths = resolve_ground_truth_paths(test_items, dataset_root, aliases)
        _write_jsonl(
            output_dir / "test_executor.jsonl",
            test_executor_rows := [
                executor_case(item, "test", ANONYMIZATION_SEED) for item in test_items
            ],
        )
        assert_manifest_safe(
            test_executor_rows,
            dataset_root=str(dataset_root),
            ground_truth_basenames={
                Path(str(item.get("path_to_gt_image", ""))).name
                for item in test_items
            },
        )
        _write_jsonl(
            output_dir / "judge-only" / "test.jsonl",
            [
                _judge_projection(item, "test", dataset_root, test_resolved_paths)
                for item in test_items
            ],
        )
        test_count = len(test_items)

    summary = {
        "protocol_seeds": {
            "split": SPLIT_SEED,
            "within_split_order": ORDER_SEED,
            "anonymization": ANONYMIZATION_SEED,
            "train_batches": list(TRAIN_BATCH_SEEDS),
        },
        "source": {
            "ref_json": str(ref_path),
            "ref_json_sha256": _sha256(ref_path),
            "test_json": str(test_path),
            "test_json_sha256": _sha256(test_path),
        },
        "counts": {
            "train": len(train),
            "train_unique_exposed_in_rounds": len(round_unique_ids),
            "validation": len(validation),
            "unused_reserve": len(unused),
            "test_materialized": test_count,
        },
        "test_included": include_test,
        "private_alias_map_sha256": alias_map_sha256,
        "unused_source_ids_sha256": hashlib.sha256(
            "\n".join(sorted(str(item.get("id", "")) for item in unused)).encode()
        ).hexdigest(),
    }
    _write_json(output_dir / "split_summary.json", summary)
    checksums = {
        str(path.relative_to(output_dir)): _sha256(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "checksums.json"
    }
    _write_json(output_dir / "checksums.json", checksums)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--include-test",
        action="store_true",
        help="Materialize the sealed test split. Never use during optimization.",
    )
    parser.add_argument(
        "--alias-map",
        type=Path,
        help="Private reviewed path alias map for dataset filename encoding defects.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_manifests(
        args.dataset_root,
        args.output_dir,
        args.include_test,
        alias_map_path=args.alias_map,
    )


if __name__ == "__main__":
    main()
