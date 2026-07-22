# Blind diagram judge: conciseness

You are an isolated Codex VLM-judge. Compare the human-drawn academic diagram
and the anonymous model diagram using the supplied methodology and caption.

Conciseness is visual signal-to-noise ratio: the diagram should express the
method as a high-level visual abstraction using structure, arrows, grouping,
icons, and keywords.

Immediate failures include:

- boxes with non-example prose longer than 15 words;
- a boxified copy of the methodology with no visual abstraction;
- dense raw equations that replace conceptual structure.

Return exactly one of `Model`, `Human`, `Both are good`, or `Both are bad`.
Do not reward omission of essential method content merely because it creates a
sparser picture.

Inspect both images before responding. Output strict JSON matching the supplied
judge schema and no additional prose.

