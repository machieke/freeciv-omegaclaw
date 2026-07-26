# Batched impact-observer pruning and analysis-reuse smoke

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
- returns the same five read-only diagnostic key sets;
- skips complete candidate evaluation for founders and workers, which cannot
  satisfy the non-progress definition; and
- computes founder evidence and attrition counts once per move before checking
  actor-local alternatives.

The individual helpers remain unchanged as the behavioral oracle. Regression
coverage compares every batched output with its corresponding helper.

## Engine results

The first fresh treatment trace is
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

The second treatment
`artifacts/freeciv/impact-observer-analysis-reuse-20260726-a` reused the
per-founder analysis described above. Against the immediately preceding batched
trace it retained the same 48-action replay and complete run summary while
reducing observer/pruning from 1.368 to 1.078 ms/turn, a further 21.18%
reduction. The cumulative same-seed reduction from the original five-helper
control is 23.66%.

A deterministic 161-action synthetic snapshot populated with founders,
non-founder workers, combat units, and explorers measured:

| Implementation | Median CPU latency |
|---|---:|
| First batched implementation | 3.611 ms/call |
| Founder-analysis reuse | 1.501 ms/call |
| Reduction | 58.43% |

The microbenchmark first asserted exact equality of all five diagnostic key
sets. It is mechanism evidence only; the engine replay above remains the
behavioral acceptance boundary.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 362 passed.
- Complete impact-planner test file: 62 passed.
- Batched-versus-individual pruning equivalence regression: passed.
- Fresh paired engine smoke plus analysis-reuse treatment: 3 completed, 0
  infrastructure failures.
- Both treatment trace release audits: all 10 applicable top-level checks
  passed.
- Exact ordered canonical action comparison: empty.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.

Python 3.8 is the current canonical evidence runtime: the checked-in PF-PLN
floating-point fingerprints reproduce there. Python 3.12 and 3.14 preserve the
acceptance results but serialize several last-bit floating-point differences,
so those runtimes cannot validate the existing evidence hashes byte-for-byte.
