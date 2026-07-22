#!/usr/bin/env python3
"""Deterministic editability and render checks for benchmark outputs."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image


DEFAULT_LIMITS = {
    "min_vertices": 4,
    "min_edges": 1,
    "min_editable_labels": 2,
    "max_single_raster_canvas_ratio": 0.50,
    "max_total_raster_canvas_ratio": 0.35,
    "min_png_width": 256,
    "min_png_height": 256,
    "min_foreground_ratio": 0.002,
    "max_foreground_ratio": 0.98,
}

_EXTERNAL_IMAGE_RE = re.compile(r"(?:^|;)image=(?:https?:)?//", re.IGNORECASE)


def _float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def inspect_drawio(path: Path, limits: dict[str, Any] | None = None) -> dict[str, Any]:
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return {
            "passed": False,
            "errors": [f"xml_parse_error: {exc}"],
            "warnings": [],
            "metrics": {},
        }
    if root.tag != "mxGraphModel":
        errors.append(f"root_must_be_mxGraphModel: {root.tag}")
    cells = root.findall("./root/mxCell")
    ids = [cell.get("id") for cell in cells]
    if "0" not in ids:
        errors.append("missing_root_cell_0")
    cell_one = next((cell for cell in cells if cell.get("id") == "1"), None)
    if cell_one is None or cell_one.get("parent") != "0":
        errors.append("missing_or_invalid_root_cell_1")
    nonempty_ids = [cell_id for cell_id in ids if cell_id is not None]
    duplicate_ids = [key for key, count in Counter(nonempty_ids).items() if count > 1]
    if duplicate_ids:
        errors.append(f"duplicate_cell_ids: {duplicate_ids[:5]}")

    vertices = [cell for cell in cells if cell.get("vertex") == "1"]
    edges = [cell for cell in cells if cell.get("edge") == "1"]
    labels = [
        cell
        for cell in cells
        if str(cell.get("value", "")).strip() and cell.get("id") not in {"0", "1"}
    ]
    metrics.update(
        {
            "cells": len(cells),
            "vertices": len(vertices),
            "edges": len(edges),
            "editable_labels": len(labels),
        }
    )
    if len(vertices) < int(limits["min_vertices"]):
        errors.append("too_few_native_vertices")
    if len(edges) < int(limits["min_edges"]):
        errors.append("too_few_native_edges")
    if len(labels) < int(limits["min_editable_labels"]):
        errors.append("too_few_editable_labels")

    id_set = set(nonempty_ids)
    for edge in edges:
        geometry = edge.find("mxGeometry")
        if geometry is None or geometry.get("relative") != "1":
            errors.append(f"invalid_edge_geometry:{edge.get('id')}")
        for attr in ("source", "target"):
            reference = edge.get(attr)
            if reference and reference not in id_set:
                errors.append(f"broken_{attr}:{edge.get('id')}->{reference}")

    canvas_area = max(
        _float(root.get("pageWidth"), 1.0) * _float(root.get("pageHeight"), 1.0),
        1.0,
    )
    raster_ratios: list[float] = []
    for cell in vertices:
        style = html.unescape(str(cell.get("style", ""))).lower()
        if "shape=image" not in style and "image=" not in style:
            continue
        if _EXTERNAL_IMAGE_RE.search(style):
            errors.append(f"external_raster_url:{cell.get('id')}")
        geometry = cell.find("mxGeometry")
        if geometry is None:
            continue
        area = max(_float(geometry.get("width")), 0.0) * max(
            _float(geometry.get("height")), 0.0
        )
        raster_ratios.append(area / canvas_area)
    metrics["raster_cells"] = len(raster_ratios)
    metrics["max_raster_canvas_ratio"] = max(raster_ratios, default=0.0)
    metrics["total_raster_canvas_ratio"] = sum(raster_ratios)
    if metrics["max_raster_canvas_ratio"] > float(
        limits["max_single_raster_canvas_ratio"]
    ):
        errors.append("single_raster_covers_too_much_canvas")
    if metrics["total_raster_canvas_ratio"] > float(
        limits["max_total_raster_canvas_ratio"]
    ):
        warnings.append("high_total_raster_canvas_ratio")

    return {
        "passed": not errors,
        "errors": sorted(set(errors)),
        "warnings": warnings,
        "metrics": metrics,
    }


def _color_distance(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    return math.sqrt(sum((int(x) - int(y)) ** 2 for x, y in zip(a[:3], b[:3])))


def inspect_png(path: Path, limits: dict[str, Any] | None = None) -> dict[str, Any]:
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    errors: list[str] = []
    warnings: list[str] = []
    try:
        with Image.open(path) as image:
            image = image.convert("RGBA")
            width, height = image.size
            thumbnail = image.copy()
            thumbnail.thumbnail((512, 512))
            pixels = list(thumbnail.getdata())
    except (OSError, ValueError) as exc:
        return {
            "passed": False,
            "errors": [f"png_read_error: {exc}"],
            "warnings": [],
            "metrics": {},
        }
    if width < int(limits["min_png_width"]):
        errors.append("png_too_narrow")
    if height < int(limits["min_png_height"]):
        errors.append("png_too_short")
    opaque = [pixel for pixel in pixels if pixel[3] > 8]
    if not opaque:
        errors.append("png_fully_transparent")
        foreground_ratio = 0.0
        dominant = (0, 0, 0, 0)
    else:
        dominant_rgb, _ = Counter(pixel[:3] for pixel in opaque).most_common(1)[0]
        dominant = (*dominant_rgb, 255)
        foreground = sum(_color_distance(pixel, dominant) > 24 for pixel in opaque)
        foreground_ratio = foreground / len(opaque)
    if foreground_ratio < float(limits["min_foreground_ratio"]):
        errors.append("png_nearly_blank")
    if foreground_ratio > float(limits["max_foreground_ratio"]):
        warnings.append("png_has_no_clear_background")
    metrics = {
        "width": width,
        "height": height,
        "foreground_ratio": foreground_ratio,
        "dominant_color": dominant,
    }
    return {
        "passed": not errors,
        "errors": sorted(set(errors)),
        "warnings": warnings,
        "metrics": metrics,
    }


def validate_artifacts(
    drawio_path: Path, png_path: Path, limits: dict[str, Any] | None = None
) -> dict[str, Any]:
    drawio = inspect_drawio(drawio_path, limits)
    png = inspect_png(png_path, limits)
    return {
        "passed": bool(drawio["passed"] and png["passed"]),
        "drawio": drawio,
        "png": png,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drawio", type=Path)
    parser.add_argument("png", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_artifacts(args.drawio, args.png)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload, end="")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
