# Cognitive-stage attribution and parser-reuse smoke

Date: 2026-07-26

Status: focused parser/policy coverage, one two-seed attribution control, two
independent two-seed engine treatments, and exact-behavior replay passed. This
is a host-planner throughput result, not a gameplay-score or win-rate claim.

## Attribution and root cause

The live harness now splits cognition into authoritative summary construction,
target/setup work, proposal generation/validation, and final
verification/planning. `model_latency_ms` remains separate, so subtracting it
from proposal and total cognition isolates host work.

The attribution control showed that the one real model selection, amortized
over 30 turns, was 86.817 ms/turn of the 92.558 ms/turn cognitive total. Of the
remaining host work, proposal handling was the largest component at
3.312 ms/turn.

Every active-research continuation constructed a new `ConstrainedProposer`.
That reloaded the immutable proposal schema, rebuilt its JSON Schema validator,
and deep-copied a complete LLM input document for a canonical path whose static
client did not invoke a model. The symbol catalog, schema, and validator share
the lifetime of the cognitive stack, so rebuilding them could not add a
correctness check.

The cognitive stack now constructs one production `ProposalParser`, while the
existing query-summary type boundary is checked without building a discarded
LLM request document. Every model and canonical proposal still passes through
the JSON parser, complete schema validator, goal/claim identifier checks, and
symbol-catalog gates. Per-turn proposal IDs, events, and causal ancestry remain
distinct.

## Engine comparison

All cohorts used seeds 104729 and 104743, a serial 30-turn topology, the
retained proxy digest
`72813abbb7c45be3cc357592dd0bba33ca3537178cd7c34482f5c5033c5e5dd5`,
and otherwise identical configuration:

- attribution control: `artifacts/freeciv/cognitive-attribution-20260726-a`;
- treatments: `artifacts/freeciv/proposal-parser-reuse-20260726-a` and
  `artifacts/freeciv/proposal-parser-reuse-20260726-b`.

The treatment column is the mean of both independent treatment cohorts.

| Measure | Control | Treatment mean | Change |
|---|---:|---:|---:|
| Summary construction | 0.822 ms/turn | 0.813 ms/turn | -1.07% |
| Cognitive setup | 0.560 ms/turn | 0.552 ms/turn | -1.39% |
| Proposal including model | 90.130 ms/turn | 87.145 ms/turn | -3.31% |
| Model latency | 86.817 ms/turn | 85.956 ms/turn | -0.99% |
| Host proposal work | 3.312 ms/turn | 1.189 ms/turn | -64.10% |
| Cognitive finalization | 1.017 ms/turn | 1.068 ms/turn | +5.03% |
| Non-model cognition | 5.741 ms/turn | 3.652 ms/turn | -36.38% |
| Total cognition | 92.558 ms/turn | 89.609 ms/turn | -3.19% |
| Complete full-turn work | 241.512 ms/turn | 240.374 ms/turn | -0.47% |
| Mean turn loop | 400.693 ms/turn | 398.296 ms/turn | -0.60% |

The two treatment repeats independently measured host proposal work at 1.176
and 1.202 ms/turn. Their total loop means were likewise nearly identical at
398.301 and 398.291 ms/turn.

## Behavioral acceptance

All four treatment games retained, relative to the attribution control:

- exact ordered canonical action payloads;
- scores and margins 107/-2 and 112/-3;
- one necessary model selection and 29 canonical avoidances per game;
- the same per-turn proposal and continuation-verification events; and
- zero infrastructure failures.

## Verification

- Complete repository FreeCiv lane: 356 passed.
- Focused singleton, multi-candidate, and active-research tests passed.
- Both two-game treatment cohorts completed without infrastructure failures.
- Four treatment traces passed all 13 top-level release-audit checks.
- Exact ordered-action comparison was empty for both seeds in both cohorts.
- Scores, opponent scores, and margins were identical in all comparisons.
- Static compilation and whitespace checks passed.
