from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from experiments.paperbanana.scripts.validate_drawio import (
    inspect_drawio,
    validate_artifacts,
)


VALID_DRAWIO = """<mxGraphModel pageWidth="800" pageHeight="600">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="a" value="Input" vertex="1" parent="1"><mxGeometry x="20" y="20" width="120" height="60" as="geometry"/></mxCell>
    <mxCell id="b" value="Encoder" vertex="1" parent="1"><mxGeometry x="200" y="20" width="120" height="60" as="geometry"/></mxCell>
    <mxCell id="c" value="Latent" vertex="1" parent="1"><mxGeometry x="380" y="20" width="120" height="60" as="geometry"/></mxCell>
    <mxCell id="d" value="Output" vertex="1" parent="1"><mxGeometry x="560" y="20" width="120" height="60" as="geometry"/></mxCell>
    <mxCell id="e" edge="1" source="a" target="b" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
  </root>
</mxGraphModel>
"""


class DrawioValidationTests(unittest.TestCase):
    def test_valid_native_diagram_and_nonblank_png_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            drawio = root / "figure.drawio"
            png = root / "figure.png"
            drawio.write_text(VALID_DRAWIO)
            image = Image.new("RGB", (800, 600), "white")
            canvas = ImageDraw.Draw(image)
            canvas.rectangle((50, 50, 750, 550), outline="navy", width=8)
            canvas.line((100, 300, 700, 300), fill="navy", width=8)
            image.save(png)
            result = validate_artifacts(drawio, png)
            self.assertTrue(result["passed"], result)

    def test_full_canvas_raster_and_blank_png_fail(self) -> None:
        bad_xml = VALID_DRAWIO.replace(
            '<mxCell id="d" value="Output" vertex="1" parent="1">',
            '<mxCell id="d" value="Output" vertex="1" parent="1" style="shape=image;image=data:image/png;base64,abc">',
        ).replace(
            '<mxGeometry x="560" y="20" width="120" height="60" as="geometry"/>',
            '<mxGeometry x="0" y="0" width="800" height="600" as="geometry"/>',
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            drawio = root / "figure.drawio"
            png = root / "figure.png"
            drawio.write_text(bad_xml)
            Image.new("RGB", (800, 600), "white").save(png)
            result = validate_artifacts(drawio, png)
            self.assertFalse(result["passed"])
            self.assertIn(
                "single_raster_covers_too_much_canvas",
                result["drawio"]["errors"],
            )
            self.assertIn("png_nearly_blank", result["png"]["errors"])

    def test_external_image_is_hard_failure_and_total_coverage_is_warning(self) -> None:
        external = VALID_DRAWIO.replace(
            'id="a" value="Input" vertex="1" parent="1"',
            'id="a" value="Input" vertex="1" parent="1" '
            'style="shape=image;image=https://example.com/icon.png"',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "external.drawio"
            path.write_text(external)
            result = inspect_drawio(path)
        self.assertFalse(result["passed"])
        self.assertIn("external_raster_url:a", result["errors"])

        tiled = VALID_DRAWIO
        for cell_id in ("a", "b", "c", "d"):
            tiled = tiled.replace(
                f'id="{cell_id}" value=',
                f'id="{cell_id}" style="shape=image;image=data:image/png;base64,abc" value=',
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tiled.drawio"
            path.write_text(tiled)
            result = inspect_drawio(
                path,
                {"max_total_raster_canvas_ratio": 0.01},
            )
        self.assertTrue(result["passed"], result)
        self.assertIn("high_total_raster_canvas_ratio", result["warnings"])


if __name__ == "__main__":
    unittest.main()
