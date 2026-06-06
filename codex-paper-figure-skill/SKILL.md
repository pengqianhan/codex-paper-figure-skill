---
name: codex-paper-figure-skill
description: Create editable academic-paper figures from natural-language figure descriptions, manuscript sections, methods/results text, graphical abstract ideas, or paper-specific visual concepts. Use when Codex needs to turn scientific text into a polished journal-style diagram by first generating a raster visual reference with the image generation tool, then recreating it directly as editable draw.io/.drawio mxGraphModel XML. Also use when a user asks for research figures, paper diagrams, mechanism figures, method overview figures, model architecture figures, workflow schematics, publication-ready editable diagrams, or Flaticon/icon-assisted paper figures using Codex's built-in Browser.
author: Pengqian Han
version: 0.0.1
---

# Codex Paper Figure Skill

## Overview

Transform paper text or a figure concept into a publication-style editable diagram. Use image generation to explore composition and visual style, then rebuild the figure as native draw.io XML so every label, shape, connector, and icon remains editable. This skill is self-contained: it embeds the draw.io generation rules it needs instead of depending on another local skill file.

## Workflow

1. Parse the user's text into a figure brief:
   - Scientific message: the single claim or workflow the figure should communicate.
   - Entities: molecules, cells, devices, models, datasets, modules, cohorts, assays, or variables.
   - Relationships: sequence, causality, comparison, hierarchy, feedback, input/output, or spatial organization.
   - Required labels: paper terms, abbreviations, axes, panel letters, conditions, and units that must appear verbatim.
   - Constraints: target journal style, aspect ratio, color palette, number of panels, export format, and whether the output must be editable.

2. Ask at most one concise clarification only when the missing detail changes the figure type or scientific meaning. Otherwise infer a sensible academic figure format from the source text.

3. Generate a raster reference with the Codex `image_gen` tool:
   - Prompt for a clean academic-paper figure, not a marketing illustration.
   - Include the exact figure structure, panel layout, visual hierarchy, palette, and domain-specific objects.
   - Request simple legible labels only when needed, but treat labels in the generated image as approximate because raster text may be imperfect.
   - Use the generated image as a composition guide only; do not deliver it as the sole final figure when the user asked for editable output.

4. Recreate the figure as draw.io:
   - Produce native `.drawio` mxGraphModel XML directly.
   - Use editable draw.io shapes, text, connectors, groups, and layers wherever possible.
   - Keep labels as real draw.io text, not embedded raster text.
   - If an exported PNG/SVG/PDF is requested, use the draw.io CLI export path below and embed the diagram XML where supported.

5. Validate before finishing:
   - Check the `.drawio` XML is well-formed and contains the required root cells.
   - Confirm all scientific entities and relationships from the brief are represented.
   - Confirm text is editable, legible, and not overlapping.
   - Confirm arrows and panel order match the paper logic.
   - If draw.io CLI is available, export a preview and inspect it for blank canvas, clipping, and layout issues.

## Figure Design Rules

- Prefer restrained publication styling: white or very light background, 2-4 accent colors, thin strokes, consistent typography, clear grouping, and generous whitespace.
- Use panel labels `A`, `B`, `C` only when the figure has multiple panels.
- Prefer left-to-right or top-to-bottom reading order unless the scientific process is cyclic.
- Encode meaning with layout first, then color; do not rely on color alone.
- Use colorblind-conscious palettes and avoid low-contrast text.
- Keep visual detail low enough that the final draw.io file is easy to edit.
- For biological figures, distinguish compartments, cells, molecules, and phenotypes with shape language and labels.
- For AI/model figures, distinguish data, model blocks, training/inference paths, losses, outputs, and evaluation with consistent containers and arrows.
- For workflow figures, use numbered steps or stage headings only when they improve scanability.

## Draw.io Generation Rules

- Always create a native `.drawio` file in mxGraphModel XML. Do not use Mermaid or CSV as the final editable format.
- Every diagram must include root cells:

```xml
<mxGraphModel adaptiveColors="auto">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
  </root>
</mxGraphModel>
```

- Add all normal diagram elements with `parent="1"` unless deliberately using multiple layers.
- Use unique `id` values for every `mxCell`.
- Escape special characters in XML attributes: `&amp;`, `&lt;`, `&gt;`, and `&quot;`.
- Do not include XML comments in generated `.drawio` files.
- Edges must contain a child geometry element such as `<mxGeometry relative="1" as="geometry"/>`.
- Use descriptive lowercase hyphenated filenames, for example `cell-state-pipeline.drawio`.
- If the user requests PNG, SVG, or PDF, first create the `.drawio` file, then export with draw.io CLI using embedded diagram XML when available.
- If draw.io CLI is not installed or cannot be found, keep the `.drawio` file and clearly report that export was skipped.

Common draw.io CLI locations:

- Windows: `C:\Program Files\draw.io\draw.io.exe`
- macOS: `/Applications/draw.io.app/Contents/MacOS/draw.io`
- Linux: `drawio` on `PATH`

Export command pattern:

```bash
drawio -x -f <png|svg|pdf> -e -b 10 -o <output> <input.drawio>
```

## Icon Workflow

Use icons only when they improve recognition or reduce clutter. If icons are needed, use Codex's built-in `Browser` plugin as the default Flaticon workflow so users do not need extra tools.

1. Use `Browser` to open `https://www.flaticon.com/` and search the exact concept plus a style term such as `line`, `outline`, `filled`, `flat`, or `science`.
2. Inspect candidate results in the browser. Prefer free, non-premium icons from one style family or author so the figure feels coherent.
3. Open the icon detail page and extract:
   - Icon page URL.
   - Icon title or concept.
   - Designer/author.
   - License and attribution requirement visible on the page.
   - Download URL or CDN image URL, if available.
4. Download the icon only after the license and attribution requirement are clear:
   - Prefer SVG/vector when available and permitted.
   - Use the browser download flow when the current Browser runtime can save the file.
   - If Browser can verify the icon page but cannot directly save the download, extract the official image/CDN URL and download it locally with a normal HTTP request.
   - Save project-bound icon files under the current figure output folder, preferably `icons/`, with descriptive lowercase filenames.
5. Avoid premium, locked, login-required, or unclear-license icons. If licensing is not usable or the icon cannot be downloaded reliably, create a simple editable draw.io shape instead.
6. In draw.io, keep each icon as a distinct movable image element. Do not flatten icons into a background image.
7. Record icon source URLs, author, and attribution/license notes in the final response and any README/example output that uses external icons.

## Output Contract

Deliver the editable `.drawio` file unless the user asks for another format. When helpful, also provide:

- The generated raster reference image path.
- An exported preview path such as `.drawio.png` or `.drawio.svg`.
- A short note listing assumptions, icon sources, and any unresolved fidelity limits.

Never present a raster-only image as complete when the user requested an editable academic figure.
