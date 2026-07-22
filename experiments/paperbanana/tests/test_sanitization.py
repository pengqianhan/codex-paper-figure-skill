from __future__ import annotations

import unittest

from experiments.paperbanana.scripts.sanitize_case import (
    assert_executor_safe,
    executor_case,
    opaque_case_id,
    sanitize_content,
)


class SanitizationTests(unittest.TestCase):
    def test_removes_markdown_html_and_residual_image_paths(self) -> None:
        source = (
            "Before\n![](images/paper (draft)_diagram.jpg)\n"
            "![reference][answer]\n[answer]: images/answer.svg 'title'\n"
            '<img src="images/secret.png">\n'
            "See images/another-result.webp for details.\nAfter"
        )
        cleaned = sanitize_content(source)
        lowered = cleaned.lower()
        self.assertNotIn("images/", lowered)
        self.assertNotIn(".jpg", lowered)
        self.assertNotIn(".png", lowered)
        self.assertNotIn(".webp", lowered)
        self.assertNotIn("![", cleaned)
        self.assertIn("Before", cleaned)
        self.assertIn("After", cleaned)

    def test_executor_projection_is_minimal_and_safe(self) -> None:
        raw = {
            "id": "test_9",
            "content": "Method\n![](images/answer.jpg)",
            "visual_intent": "Figure 1: pipeline",
            "path_to_gt_image": "images/answer.jpg",
            "additional_info": {"file_path": "pdfs/source.pdf"},
        }
        case = executor_case(raw, split="test", seed=20260723)
        self.assertEqual(
            set(case), {"case_id", "content", "visual_intent", "empty_content"}
        )
        assert_executor_safe(case)

    def test_opaque_id_is_deterministic_and_split_specific(self) -> None:
        first = opaque_case_id("item_1", "train", 7)
        self.assertEqual(first, opaque_case_id("item_1", "train", 7))
        self.assertNotEqual(first, opaque_case_id("item_1", "test", 7))
        self.assertRegex(first, r"^case_[0-9a-f]{16}$")


if __name__ == "__main__":
    unittest.main()
