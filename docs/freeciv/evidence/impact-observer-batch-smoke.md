# Batched impact-observer pruning smoke

Date: 2026-07-26

Status: retained single-seed engine smoke with exact ordered-action replay.
This is mechanism evidence for a bounded CPU optimization, not a gameplay-score,
win-rate, or statistically powered latency claim.

## Change

The engine-live impact observer previously traversed the authoritative legal
action catalog independently for capability, non-progress, founder reachability,
founder-cycle, and founder-attrition diagnostics. The batched path now:

- decodes founder capability once;
- traverses the legal-action catalog once;
- reuses the canonical action key carried by the snapshot; and
- returns the same five read-only diagnostic key sets.

The individual helpers remain unchanged as the behavioral oracle. Regression
coverage compares every batched output with its corresponding helper.

## Engine result

The fresh treatment trace is
`artifacts/freeciv/impact-observer-batch-20260726-a/games/impact_pair/development/treatment/e_full_loop/104729-00/events.jsonl`.
It was compared with the same-seed treatment trace from
`artifacts/freeciv/impact-execution-attribution-20260726-a`.

| Metric | Control | Batched | Change |
|---|---:|---:|---:|
| Post-refresh observer/pruning | 1.412 ms/turn | 1.368 ms/turn | -3.14% |
| Ordered canonical actions | 48 | 48 | exact match |
| Score at turn 30 | 107 | 107 | identical |
| Score margin at turn 30 | -2 | -2 | identical |
| Engine rejection rate | 0 | 0 | identical |
| Confirmation timeouts | 0 | 0 | identical |

The complete `run_completed.summary`, including all five pruning counts, is
identical. Full action-phase latency was noisier in the fresh run, so no outer
latency reduction is claimed from this single seed.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 362 passed.
- Complete impact-planner test file: 62 passed.
- Batched-versus-individual pruning equivalence regression: passed.
- Fresh paired engine smoke: 2 completed, 0 infrastructure failures.
- Treatment trace release audit: all 10 applicable top-level checks passed.
- Exact ordered canonical action comparison: empty.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.

Python 3.8 is the current canonical evidence runtime: the checked-in PF-PLN
floating-point fingerprints reproduce there. Python 3.12 and 3.14 preserve the
acceptance results but serialize several last-bit floating-point differences,
so those runtimes cannot validate the existing evidence hashes byte-for-byte.
