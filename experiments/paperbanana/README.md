# PaperBananaBench experiment scaffold

This directory contains the method-neutral experiment contract for optimizing
`codex-paper-figure-skill/SKILL.md` and evaluating frozen variants on
PaperBananaBench.

The first implementation target is SkillOpt-Lite. Meta-Harness is intentionally
deferred, but the data, executor, draw.io validation, judging, and reporting
interfaces are method-neutral so they can be reused later.

## Safety boundaries

- Optimizers may change only `codex-paper-figure-skill/SKILL.md`.
- Executors receive sanitized text and never receive ground-truth image paths.
- Proposers receive full train traces but only aggregate validation summaries.
- `test.json` is not materialized into jobs until both optimization and
  finalization are complete.
- Generated figures and traces live outside Git under
  `PaperBananaBench/diagram/experiments/<run-id>/`.

## Local checks

```bash
python3 -m unittest discover -s experiments/paperbanana/tests -v
python3 experiments/paperbanana/scripts/make_manifests.py \
  --dataset-root /Users/pengqianhan/Downloads/PaperBananaBench/diagram \
  --output-dir /tmp/paperbanana-manifests \
  --alias-map /path/to/private-reviewed-gt-aliases.json
```

The manifest command does not include the test split unless `--include-test`
is supplied explicitly. The alias map is stored outside Git because it maps
opaque jobs back to ground-truth filenames; every reviewed alias is pinned by
its exact declared path, resolved path, and SHA-256.

## Current phase

Only SkillOpt-Lite is enabled now. The final frozen comparison for this phase
is baseline versus SkillOpt-Lite (`292 x 2` executor jobs). Meta-Harness is
deferred and can reuse this scaffold later without changing the first-phase
results.
