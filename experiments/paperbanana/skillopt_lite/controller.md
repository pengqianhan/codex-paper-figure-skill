# SkillOpt-Lite controller contract

This adapter preserves the official slash-loop order while replacing its
benchmark-specific shell runner with Codex subagent job packets:

```text
baseline full validation -> train batch 1
for rounds 1..3:
  fresh proposer -> one <=4-edit patch -> full validation gate
  -> always run the next train rollout
restore best -> freeze -> one-shot final test (started separately)
```

The train rollout after round 3 is intentionally retained even though no later
proposal consumes it. Matching the official slash loop, rounds 1–3 and the
post-final rollout independently sample 12 cases from the fixed 36-case train
pool with seeds 1, 2, 3, and 4. Cases may repeat across rounds. This never
accesses the 238-case reserve or the sealed test split.

The optimization phase therefore contains 144 figure-executor cases: baseline
validation `24`, initial train `12`, then three rounds of validation `24` plus
next-train `12`. There are three proposer calls. The later frozen comparison is
separate: baseline and SkillOpt-Lite each run the 292-case test exactly once.

This implements the official Copilot `skillopt-loop.prompt.md` gate policy:
`delta >= 0.01` improves, `delta <= -0.01` rejects and restores `before`, and
`abs(delta) < 0.01` is flat. Flat keeps the candidate on disk but does not
update the comparison score or best snapshot. The core Python `gate.py` has no
dead-band/flat action; that distinction is recorded explicitly. After all
three rounds the best snapshot is restored.

The controller never invokes an LLM. `prepare-next` emits the next role packet;
the root Codex task launches fresh proposer, executor, and judge subagents with
the locked model/effort settings, then ingests their structured artifacts.
Validation is reduced to aggregate statistics before it is recorded in
proposer-visible state. Train samples retain complete per-case traces.

Typical command sequence:

```bash
python3 -m experiments.paperbanana.skillopt_lite.controller init ...
python3 -m experiments.paperbanana.skillopt_lite.controller prepare-next --run-dir ...
python3 -m experiments.paperbanana.skillopt_lite.controller ingest-validation ...
python3 -m experiments.paperbanana.skillopt_lite.controller ingest-train ...
python3 -m experiments.paperbanana.skillopt_lite.controller ingest-proposal ...
python3 -m experiments.paperbanana.skillopt_lite.controller audit --run-dir ...
python3 -m experiments.paperbanana.skillopt_lite.controller finalize --run-dir ...
```

`finalize` only freezes the skill and writes its lock. It does not materialize
or run test data.
