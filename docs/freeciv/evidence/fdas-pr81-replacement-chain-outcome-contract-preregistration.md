# FDAS PR81 replacement-chain outcome contract preregistration

Date: 2026-08-04

## Problem

PR78 and PR79 establish grounded coordinated-replacement recall, and PR80
bounds its evidence amplification. The existing defense outcome target begins
at an accepted one-step move or fortify action. Applying it to a two-step chain
would attribute target relief before the replacement covers the source and the
reinforcement reaches the target.

PR80 observed zero replacement step advances or completions because the chain
remains shadow-only. PR81 therefore implements the correct outcome contract
without pretending that live training data already exists and without adding
execution authority.

## Frozen target

Target ID:
`durable-completed-coordinated-replacement/32-turn/1.0`.

The observation window starts only when the persistent operation reaches
`completed` after both authoritative step predicates are satisfied. The label
is bound to:

- operation ID and immutable specification digest;
- game/player identity;
- replacement and reinforcement actor IDs;
- source and target city IDs;
- authoritative completion turn and snapshot ID; and
- a due turn exactly 32 turns after completion.

At the due turn, the outcome is positive only when both cities remain owned
and present, the replacement actor is an own non-transported unit at the
source, and the reinforcement actor is an own non-transported unit at the
target. Each failed conjunct is retained in the observed value and reason.

The label store is atomic, identity-bound, immutable after terminal
observation, and recoverable from completed operation records after restart.
It has no truth, policy, readout, transition-value, or induction authority.

## Manifest boundary

A new `coordinated_replacement_chain_outcome=shadow-live` capability freezes:

- the exact target and 32-turn completion-indexed window;
- authoritative completed-operation indexing;
- no action-selection change;
- no transition-value estimate;
- no induction readout; and
- no policy, readout, or truth authority.

Existing delayed episode labels remain unchanged and separate.

## Acceptance

- component tests prove exact completion-only opening, due-turn observation,
  positive and negative conjuncts, idempotence, terminal immutability, atomic
  restart recovery, and operation/spec identity rejection;
- event and audit tests prove revision-current, non-authorizing open/observe
  evidence and exact status/terminal counters;
- a clean seed `109633` engine run completes 160 turns with zero rejected
  actions and passes the unchanged replacement lifecycle/readout audit;
- every completed replacement operation has exactly one matching label;
- no non-completed operation has a label;
- zero completed operations and zero labels are accepted and reported rather
  than relabelled as outcome evidence; and
- the final report is deterministic byte-for-byte.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr81-replacement-chain-outcome-v1 \
  --config profile/freeciv_harness_fdas_pr81_replacement_chain_outcome_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 1 --no-resume
```

## Claim boundary

A pass establishes a mechanically correct completion-indexed label lifecycle.
If the engine run contains no completed chains, it supplies activation evidence
only. It makes no transition-value, preference, action, causal relief, score,
or win-rate claim and does not authorize calibration from zero outcomes.
