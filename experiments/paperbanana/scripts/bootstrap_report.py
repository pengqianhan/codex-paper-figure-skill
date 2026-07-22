#!/usr/bin/env python3
"""Compute a deterministic paired-bootstrap confidence interval."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def paired_bootstrap(
    left: list[float],
    right: list[float],
    *,
    samples: int = 10_000,
    seed: int = 20260723,
) -> dict[str, float | int]:
    if len(left) != len(right) or not left:
        raise ValueError("paired score lists must be non-empty and equal length")
    differences = [a - b for a, b in zip(left, right)]
    observed = sum(differences) / len(differences)
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        estimates.append(
            sum(differences[rng.randrange(len(differences))] for _ in differences)
            / len(differences)
        )
    estimates.sort()
    low = estimates[int(samples * 0.025)]
    high = estimates[min(int(samples * 0.975), samples - 1)]
    return {
        "n": len(differences),
        "bootstrap_samples": samples,
        "seed": seed,
        "mean_difference": observed,
        "ci95_low": low,
        "ci95_high": high,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path, help="JSON array of scores")
    parser.add_argument("right", type=Path, help="JSON array of paired scores")
    parser.add_argument("--samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260723)
    args = parser.parse_args()
    result = paired_bootstrap(
        json.loads(args.left.read_text()),
        json.loads(args.right.read_text()),
        samples=args.samples,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

