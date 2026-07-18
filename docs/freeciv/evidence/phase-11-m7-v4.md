# Phase 11 / M7 and V4 metrics evidence

Date: 2026-07-18 UTC

## Harness implementation

All five conditions are capability manifests over one runner and one event contract;
there are no condition-specific code forks. The controller assigns the pinned seed
list deterministically, isolates game IDs and worker ports, persists manifest/status/
event files per game, resumes only when the persisted configuration identity matches,
and classifies infrastructure failures separately from game losses. Aggregation reads
only schema- and causally-valid metric events.

The predeclared statistics are Wilson intervals for binary rates and a deterministic
percentile bootstrap of paired seed deltas for continuous metrics. Calibration uses
declared 0.1 buckets, a 10-sample sufficiency threshold, and +/-0.15 tolerance.

## Current-configuration representative matrix

`artifacts/freeciv/m7-representative-current` is the complete deterministic release
fixture for configuration
`e92fe9c4e0013df320d9b5a393b04bd4e53198efebca50ec9201335566d58400`:

- 250/250 jobs completed and zero infrastructure failures;
- 30 games on the same seeds for each of all five conditions;
- 20 sequential same-opponent games for each induction-enabled condition;
- 30 graded plus 30 ungraded games;
- losses, null effects, and negative marginal effects remain in the report;
- all 250 manifests record repository/source identity, the pinned compiler and
  ruleset source/IR/Atomese hashes, event schema, and start/end times;
- all 250 manifests carry implementation identity
  `780d9146dd462d10d1767fe8bd1a08c707668a38ff6db597323ac264fddfc0d4`;
- aggregate SHA-256
  `44bca7d2cd5087c61d69d38dd17b50172197b76883d21beee0ee49dfa72778f4`.

Re-running aggregation produced a byte-identical `aggregate.json`. The explicit
oracle score delta is `+4.7831` (95% paired-bootstrap interval
`[1.7375, 7.8955]`); the induction accuracy delta is `+0.1575`
(`[0.1215, 0.19425]`). The grading A/B result is retained as a null result:
win-rate and score deltas are both zero. This passes the implementation plan's
P10.A3 infrastructure/result-retention criterion; it does not claim the positive
effect required by the older agent-spec A6.3 wording.

## Engine-backed release matrix

The canonical proxy/FreeCiv/Ollama run is retained under
`artifacts/freeciv/m7-engine-release-current-20260718`. It uses three dedicated
engine ports; `controller_workers: 3` is part of behavioral identity because model
queueing can affect bounded fallbacks. Every accepted manifest records configuration
hash `e92fe9c4e0013df320d9b5a393b04bd4e53198efebca50ec9201335566d58400`
and implementation hash
`780d9146dd462d10d1767fe8bd1a08c707668a38ff6db597323ac264fddfc0d4`.

Final engine results are:

- 250/250 current-identity jobs completed and zero current failures;
- 30 games for each of the five main conditions on the identical seed set;
- 20 ordered same-opponent games for each of D and E induction;
- 30 graded and 30 ungraded games;
- zero engine-rejected-action rate and zero confabulation write-through in every
  main condition;
- all main-condition full-loop-under-30-second rates equal 1.0;
- D/E pooled calibration has 285 samples in the populated 0.9 bucket, empirical
  frequency 1.0, absolute error 0.05, and passes the 0.15 tolerance;
- E abduction truth accuracy is 0.8333 and D is 0.8 over 30 games each;
- oracle score delta is 0.0 over 30 paired seeds; induction accuracy delta is
  +0.45 with paired-bootstrap interval [0.35, 0.50] over 20 games, and
  `prediction_assumed=false`;
- graded-minus-ungraded win point estimate is +0.0333 (one game; interval
  [0.0, 0.1]), while score delta is 0.0. This is a small positive point estimate,
  not a conclusive score improvement; the older A6.3 result remains reported as
  not met rather than being promoted beyond the evidence.

The first pass retained all 13 pre-turn infrastructure exclusions rather than
relabeling them as losses. Their manifests, event prefixes, statuses, and the
13-failure first-pass report are under `attempt-history/first-pass`; its aggregate
SHA-256 is `49a50a0bab95f7cf448bd97b0efd7ccfc8b201a0d00d3c1067897b4914dfb4f4`.
Sparse fresh-attempt resumes filled those slots without rerunning completed games.
The final current aggregate has SHA-256
`93e6b46096cc54e67623b4d17ee3b437deb66eb68a50057bd1d784198dc32411`;
two aggregate-only runs were byte-identical. The human report SHA-256 is
`6407a0188c78cefb9a279979cec8ba1c2f6106410be4fdd7babaf72c86664f76`.

## Acceptance results

- P11.A1/P11.A5: all five engine conditions have 30 identical-seed games; both
  induction arms have 20 ordered games, and both grading arms have 30 games.
- P11.A2: every declared metric has per-condition intervals and paired marginal
  deltas with sample counts.
- P11.A3: oracle and induction deltas are explicit and `prediction_assumed=false`.
- P11.A4: losses and infrastructure failures have separate fields; the first-pass
  exclusions and null/negative results are retained at per-attempt fidelity.
- P11.A6: the metrics UI reads the aggregate event stream and DOM tests match the
  logged estimate/bounds/count values exactly.
- P11.A7: unchanged input logs produce byte-identical aggregate output.
- P11.A8: runtime capability assertions reject every disallowed access; condition
  boundary tests cover the complete matrix.

## Repeatable commands

```bash
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/m7-representative-current \
  --backend representative --workers 3 --no-resume
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/m7-representative-current \
  --backend representative --aggregate-only
FREECIV_RULESET_ROOT=... FREECIV_LLM_ROOT=... PYTHONPATH=src:benchmarks \
  python3 scripts/freeciv/run_harness.py \
    --out artifacts/freeciv/m7-engine-release-current-20260718 \
    --backend engine-live --workers 3
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/m7-engine-release-current-20260718 \
  --backend engine-live --workers 3 --aggregate-only
pytest -q Autotests/test_freeciv_harness.py
npm --prefix apps/freeciv-observability test -- --run
```
