from __future__ import annotations

import unittest
from collections import Counter
import random

from experiments.paperbanana.scripts.make_manifests import (
    CATEGORY_QUOTAS,
    TRAIN_BATCH_SEEDS,
    sample_train_batch,
    split_reference_items,
)


SOURCE_COUNTS = {
    "agent_reasoning": 91,
    "generative_learning": 77,
    "science_applications": 50,
    "vision_perception": 80,
}


def synthetic_items() -> list[dict]:
    rows = []
    index = 0
    ratios = ["16:9", "21:9", "3:2"]
    for category, count in SOURCE_COUNTS.items():
        for local_index in range(count):
            rows.append(
                {
                    "id": f"ref_{index}",
                    "category": category,
                    "content": "x" * (100 + local_index * 17),
                    "visual_intent": "diagram",
                    "path_to_gt_image": f"images/{index}.jpg",
                    "additional_info": {
                        "rounded_ratio": ratios[local_index % len(ratios)]
                    },
                }
            )
            index += 1
    return rows


class SplitTests(unittest.TestCase):
    def test_pool_split_is_deterministic_disjoint_and_quota_exact(self) -> None:
        rows = synthetic_items()
        first = split_reference_items(rows)
        second = split_reference_items(rows)
        self.assertEqual(
            [[item["id"] for item in part] for part in first],
            [[item["id"] for item in part] for part in second],
        )
        train, validation, unused = first
        self.assertEqual((len(train), len(validation), len(unused)), (36, 24, 238))
        all_ids = [item["id"] for item in train + validation + unused]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        shuffled = list(rows)
        random.Random(99).shuffle(shuffled)
        shuffled_split = split_reference_items(shuffled)
        self.assertEqual(
            [[item["id"] for item in part] for part in first],
            [[item["id"] for item in part] for part in shuffled_split],
        )
        train_counts = Counter(item["category"] for item in train)
        val_counts = Counter(item["category"] for item in validation)
        for category, quota in CATEGORY_QUOTAS.items():
            self.assertEqual(train_counts[category], quota["train"])
            self.assertEqual(val_counts[category], quota["validation"])
        batches = [sample_train_batch(train, seed) for seed in TRAIN_BATCH_SEEDS]
        for seed, batch in zip(TRAIN_BATCH_SEEDS, batches):
            self.assertEqual(len(batch), 12)
            self.assertEqual(len({item["id"] for item in batch}), 12)
            self.assertEqual(
                [item["id"] for item in batch],
                [item["id"] for item in sample_train_batch(train, seed)],
            )
        exposed = {item["id"] for batch in batches for item in batch}
        self.assertLess(len(exposed), 36)


if __name__ == "__main__":
    unittest.main()
