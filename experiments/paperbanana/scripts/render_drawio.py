#!/usr/bin/env python3
"""Render an uncompressed draw.io file with the locked desktop CLI."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


DEFAULT_DRAWIO = Path("/Applications/draw.io.app/Contents/MacOS/draw.io")


def render_drawio(
    source: Path,
    output: Path,
    *,
    drawio_cli: Path = DEFAULT_DRAWIO,
    timeout_seconds: int = 180,
    border: int = 10,
) -> subprocess.CompletedProcess[str]:
    if not source.is_file():
        raise FileNotFoundError(source)
    if not os.access(drawio_cli, os.X_OK):
        raise FileNotFoundError(f"draw.io CLI is not executable: {drawio_cli}")
    output.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DRAWIO_DISABLE_UPDATE"] = "true"
    command = [
        str(drawio_cli),
        "-x",
        "-f",
        "png",
        "-e",
        "-b",
        str(border),
        "-o",
        str(output),
        str(source),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"draw.io export failed ({result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("draw.io reported success but produced no PNG")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--drawio-cli", type=Path, default=DEFAULT_DRAWIO)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    render_drawio(
        args.source,
        args.output,
        drawio_cli=args.drawio_cli,
        timeout_seconds=args.timeout,
    )


if __name__ == "__main__":
    main()

