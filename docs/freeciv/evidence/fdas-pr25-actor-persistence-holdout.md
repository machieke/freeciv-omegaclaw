# FDAS PR25 attributed-defense held-out discovery gate

Status: source, delayed-label, proposal, and authority-safety gates accepted;
all proposals demoted for insufficient held-out samples; no promotion, readout,
score, or gameplay-improvement claim.

## Frozen cohort and eligibility

The fresh engine-backed evaluation used the versioned delayed target
`durable-attributed-actor-city-defense/32-turn/1.0`. A positive label requires
the exact actor attributed to a fortification relief episode to remain owned,
non-transported, on a still-owned city tile, and fortified 32 turns later.

The planned seed `104761` completed naturally at turn 153 and therefore failed
the predeclared fixed 160-turn horizon gate. It is retained as non-confirmatory
evidence and was replaced only for horizon eligibility by the next untouched
pinned seed, `104789`; no outcome was consulted when choosing the replacement.
The frozen eligible split was:

- training: seeds `104773` and `104779`;
- holdout: seed `104789`;
- strict requirements: clean engine sources, completed horizons, exact delayed
  outcome target, nonempty accepted populations, and at least one proposal.

All eligible games completed from clean commit
`5dc84b89d88800f695a31246bc3fd78e7e1c06e3`. Their event ledgers validated
without errors or warnings, and their per-game delayed-label audits passed.

| Partition | Seed | Horizon | Opened | Positive | Negative | Pending |
|---|---:|---:|---:|---:|---:|---:|
| Ineligible | 104761 | 153 / 160 | 3 | 3 | 0 | 0 |
| Training | 104773 | 160 / 160 | 2 | 2 | 0 | 0 |
| Training | 104779 | 160 / 160 | 8 | 5 | 2 | 1 |
| Holdout | 104789 | 160 / 160 | 2 | 2 | 0 | 0 |

The pending training label was due after the fixed horizon and correctly
abstained from induction. Thus the miner received nine resolved training
examples (`7` positive, `2` negative) and two resolved positive holdout
examples.

## Result

Observed contrast allowed the bounded miner to produce eight quarantined
contextual proposals. This is the capability the earlier all-positive 8-turn
target could not exercise. Every proposal received a held-out verdict, and all
eight were demoted with `insufficient_validation_samples`: the frozen holdout
contains two examples while the predeclared validation minimum is eight.

The gate report itself is accepted because it verifies that proposal mining,
held-out adjudication, persistence/hash binding, and fail-closed authority
behavior all ran as specified. Acceptance is not promotion. There were zero
approvals and zero promoted rules; truth, policy, and readout authority all
remained false. The report structural hash is
`635d63577e6f6be963dc88456aca5b126adeab7fa9fef2362d00aec90ebb2518`.
The machine-readable report is
[`fdas-pr25-actor-persistence-holdout-engine.json`](fdas-pr25-actor-persistence-holdout-engine.json).

## Interpretation and next gate

The 32-turn attributed-actor target fixes the earlier semantic ceiling: it
produced real failures and consequently real candidate rules. The present
cohort is still too small to test those candidates. The next valid step is to
freeze the training data, target, features, thresholds, and mined proposal
identities, then collect additional untouched engine-backed holdout seeds until
at least eight resolved holdout labels are available. Changing the minimum
sample threshold or moving held-out examples into training would invalidate
the confirmation boundary.

Even a subsequent promotion would establish only held-out predictive utility
for this delayed target. Live readout authority and any score or win-rate claim
remain separate experiments.

## Reproduction

```bash
TRAIN=artifacts/freeciv/fdas-actor-persistence-population-live-160-v1/games/main/e_full_loop
HOLDOUT=artifacts/freeciv/fdas-actor-persistence-replacement-live-160-v1/games/main/e_full_loop
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_fdas_induction_holdout.py \
  --training-store "$TRAIN/104773-00/fdas-decision-episodes.json" \
  --training-store "$TRAIN/104779-00/fdas-decision-episodes.json" \
  --holdout-store "$HOLDOUT/104789-00/fdas-decision-episodes.json" \
  --training-outcome-label-store "$TRAIN/104773-00/fdas-induction-outcome-labels.json" \
  --training-outcome-label-store "$TRAIN/104779-00/fdas-induction-outcome-labels.json" \
  --holdout-outcome-label-store "$HOLDOUT/104789-00/fdas-induction-outcome-labels.json" \
  --outcome-target durable-attributed-actor-city-defense/32-turn/1.0 \
  --ledger artifacts/freeciv/fdas-actor-persistence-holdout-v1/actor-persistence-holdout-ledger.json \
  --output docs/freeciv/evidence/fdas-pr25-actor-persistence-holdout-engine.json \
  --require-engine-source --require-horizon --require-proposal
```

The expected exit code is `0`: all mechanism and safety requirements pass,
while the report records every proposal's fail-closed demotion.
