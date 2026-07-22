#!/usr/bin/env python3
"""Create executor-safe PaperBanana cases without ground-truth leakage."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\([^\n]*?\.(?:jpe?g|png|gif|svg|webp)(?:\?[^\n)]*)?\)",
    flags=re.IGNORECASE,
)
_REFERENCE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\[[^\]]+\]", flags=re.IGNORECASE)
_REFERENCE_DEFINITION_RE = re.compile(
    r"^\s*\[[^\]]+\]:\s*<?[^\n>]*?\.(?:jpe?g|png|gif|svg|webp)>?(?:\s+.*)?$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", flags=re.IGNORECASE | re.DOTALL)
_IMAGE_PATH_RE = re.compile(
    r"(?:[^\s\]\[<>]*/)?images/[^\s\]\[<>]*?\.(?:jpe?g|png|gif|svg|webp)",
    flags=re.IGNORECASE,
)
_EXCESS_BLANKS_RE = re.compile(r"\n{3,}")


FORBIDDEN_EXECUTOR_TOKENS = (
    "path_to_gt_image",
    "additional_info",
    "file_path",
    "diagram_page_num",
)


def opaque_case_id(source_id: str, split: str, seed: int) -> str:
    """Return a stable opaque identifier that does not expose the source ID."""

    payload = f"{seed}:{split}:{source_id}".encode("utf-8")
    return f"case_{hashlib.sha256(payload).hexdigest()[:16]}"


def sanitize_content(content: Any) -> str:
    """Remove embedded ground-truth image references while preserving prose."""

    text = "" if content is None else str(content)
    text = _MARKDOWN_IMAGE_RE.sub("\n[image removed]\n", text)
    text = _REFERENCE_IMAGE_RE.sub("[image removed]", text)
    text = _REFERENCE_DEFINITION_RE.sub("", text)
    text = _HTML_IMAGE_RE.sub("\n[image removed]\n", text)
    text = _IMAGE_PATH_RE.sub("[image path removed]", text)
    text = _EXCESS_BLANKS_RE.sub("\n\n", text)
    return text.strip()


def executor_case(item: dict[str, Any], split: str, seed: int) -> dict[str, Any]:
    """Project a raw dataset item onto the executor-visible schema."""

    source_id = str(item.get("id", ""))
    content = sanitize_content(item.get("content", ""))
    case = {
        "case_id": opaque_case_id(source_id, split, seed),
        "content": content,
        "visual_intent": sanitize_content(item.get("visual_intent", "")),
        "empty_content": not bool(content),
    }
    assert_executor_safe(case)
    return case


def judge_case(
    item: dict[str, Any], split: str, seed: int, dataset_root: str
) -> dict[str, Any]:
    """Create the judge-only projection, including the reference image path."""

    safe = executor_case(item, split=split, seed=seed)
    relative_gt = str(item.get("path_to_gt_image", ""))
    return {
        **safe,
        "source_id": str(item.get("id", "")),
        "category": str(item.get("category", "unknown")),
        "ground_truth_image": f"{dataset_root.rstrip('/')}/{relative_gt}",
    }


def assert_executor_safe(case: dict[str, Any]) -> None:
    """Raise if an executor projection contains obvious answer leakage."""

    serialized = repr(case).lower()
    for token in FORBIDDEN_EXECUTOR_TOKENS:
        if token in serialized:
            raise ValueError(f"executor case contains forbidden token: {token}")
    if _IMAGE_PATH_RE.search(serialized):
        raise ValueError("executor case contains a ground-truth image path")
    if re.search(r"\.(?:jpe?g|png|gif|svg|webp)\b", serialized):
        raise ValueError("executor case contains an image filename")


def assert_manifest_safe(
    cases: list[dict[str, Any]],
    *,
    dataset_root: str,
    ground_truth_basenames: set[str],
) -> None:
    """Scan a complete executor manifest for cross-record leakage."""

    serialized = json.dumps(cases, ensure_ascii=False).lower()
    if dataset_root.lower() in serialized:
        raise ValueError("executor manifest contains the dataset root")
    if "images/" in serialized or "path_to_gt_image" in serialized:
        raise ValueError("executor manifest contains a GT path marker")
    if "![" in serialized or "<img" in serialized:
        raise ValueError("executor manifest contains an unresolved image reference")
    leaked = [name for name in ground_truth_basenames if name and name.lower() in serialized]
    if leaked:
        raise ValueError(f"executor manifest contains GT basenames: {leaked[:3]}")


__all__ = [
    "FORBIDDEN_EXECUTOR_TOKENS",
    "assert_manifest_safe",
    "assert_executor_safe",
    "executor_case",
    "judge_case",
    "opaque_case_id",
    "sanitize_content",
]
