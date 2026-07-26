# Action-planner founder-evidence reuse smoke

Date: 2026-07-26

Status: retained single-seed engine smoke with exact ordered-action replay.
This is local movement-enumeration throughput evidence, not a gameplay-score,
win-rate, or statistically powered outer latency claim.

## Change

Founder move evaluation previously derived the same grounded route evidence
once while checking recent-cycle alternatives and again while scoring the
surviving candidate. Alternative checks could also decode the authoritative
legal-action catalog again even though candidate enumeration already held that
exact catalog.

The movement path now derives each founder move's evidence once and passes it,
together with the decoded action tuple, into cycle and attrition checks. Direct
helper callers retain the original behavior through optional fallback inputs.
Route history, actor-local failure evidence, attrition rules, candidate
projections, ordering, and execution checks are unchanged. Regression coverage
asserts exactly one evidence derivation per evaluated founder move.

## Engine result

The fresh treatment
`artifacts/freeciv/impact-founder-evidence-reuse-20260726-a` was compared with
the same-seed `artifacts/freeciv/impact-production-prune-20260726-a` control:

| Metric | Control | Treatment | Change |
|---|---:|---:|---:|
| Movement evaluation | 0.842 ms/call | 0.784 ms/call | -6.87% |
| Complete candidate enumeration | 2.287 ms/call | 2.238 ms/call | -2.16% |
| Complete impact planning | 6.022 ms/turn | 5.994 ms/turn | -0.47% |
| Production evaluation | 0.907 ms/call | 0.920 ms/call | noise |
| Complete pressure ranking | 1.498 ms/call | 1.530 ms/call | noise |
| Score at turn 30 | 107 | 107 | identical |
| Score margin at turn 30 | -2 | -2 | identical |
| Engine rejection rate | 0 | 0 | identical |
| Confirmation timeouts | 0 | 0 | identical |

The treatment retained the exact ordered 48-action replay and complete
`run_completed.summary`. The retained claim is limited to movement evaluation;
the smaller candidate reduction is supporting evidence, while outer planning
is considered flat within single-run noise.

## Verification

- Complete canonical-runtime repository FreeCiv lane: 367 passed.
- Complete impact-planner regression lane: 65 passed.
- Fresh treatment engine trace: 1 completed, 0 infrastructure failures.
- Treatment trace release audit: all 10 applicable top-level checks passed.
- Exact ordered canonical action comparison: identical.
- Complete `run_completed.summary` comparison: identical.
- Static whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
