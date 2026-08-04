# FDAS PR80 replacement terminal-reproposal hardening preregistration

Date: 2026-08-04

## Problem

PR79 seed `109633` exposed repeated recreation of the same logical
coordinated-replacement chain immediately after expiration. Active lifecycle
deduplication remained correct, but 56 logical chains expanded into 208
durable records, 729 grounded pair rows, and 508,032 events. The event ledger
grew to approximately 511 MB and engine gameplay took 1,595.06 seconds.

PR80 is a lifecycle-efficiency correction. It does not change candidate
generation, transition value, preference, action authority, or terminal
evidence retention.

## Frozen correction

After any operation reaches a terminal state, the same logical replacement
key—replacement actor, reinforcement actor, source city, and target city—is
ineligible for reproposal for 32 turns after the terminal observation. The
32-turn interval is reused from the already frozen delayed-outcome observation
window; it is not fitted to this seed. Active operations continue to suppress
duplicates without a time limit.

The cooldown is derived exclusively from persisted `OperationStore` records,
so restart cannot clear it. Terminal records remain immutable and durable.
Different actor/source/target tuples remain independent. When the cooldown
ends, a newly exact, current candidate may create a new operation.

The adapter exposes aggregate suppressed-candidate counts in terminal status.
It does not emit one suppression event per rapidly changing snapshot because
that would recreate the evidence-amplification problem the correction is
intended to bound.

## Frozen confirmation

Seed `109633` is deliberately reused as the known pathological integration
case. The source implementation commit must be clean and the run must start
without resume:

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr80-replacement-terminal-reproposal-v1 \
  --config profile/freeciv_harness_fdas_pr79_replacement_readout_fresh_cohort_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 11 --limit-seeds 1 \
  --no-resume
```

## Acceptance

- focused adapter tests prove active deduplication, within-window suppression,
  exact boundary release, restart persistence, and independent logical keys;
- seed `109633` completes the 160-turn horizon with zero rejected actions;
- the unchanged PR77 lifecycle and PR78 readout audits pass;
- at least one grounded replacement pair remains observable;
- at least one candidate is reported as cooldown-suppressed;
- durable replacement records are at most 80, versus the frozen baseline 208;
- event count is at most 300,000, versus the frozen baseline 508,032; and
- the final report is deterministic byte-for-byte.

Gameplay time and ledger bytes are reported descriptively because they depend
on host load and serialization details. The structural gates are record and
event counts.

## Claim boundary

A pass establishes bounded terminal-chain reproposal and lower evidence
amplification on one known pathological seed. It makes no gameplay-performance,
transition-value, preference, score, or win-rate claim.
