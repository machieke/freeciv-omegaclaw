# FDAS PR82 bounded replacement-execution pilot preregistration

Date: 2026-08-04

## Problem

PR81 installs the correct completion-indexed outcome target, but its clean
shadow run produced zero completed chains and therefore zero labels. A
coordinated replacement cannot complete unless the controller commits to both
movement steps across multiple authoritative snapshots.

PR82 is the first execution-capable mechanics pilot. It deliberately reuses a
known-opportunity seed, forces treatment, and is permanently claim-ineligible.
Its only purpose is to prove that one grounded chain can be durably owned,
revalidated, executed through the existing planner and final execution gate,
completed from authoritative placement predicates, and connected to the PR81
outcome lifecycle.

## Frozen treatment

Treatment ID:
`fdas-coordinated-replacement-bounded-execution-pilot/1.0`.

Assignment unit:
`game-first-grounded-coordinated-replacement-chain/1.0`.

At the first snapshot with one or more PR78 grounded safe-chain pairs, the
pilot deterministically selects the lexicographically first lifecycle
operation ID and persists exactly one treatment assignment for the game. It
does not randomize and cannot assign another operation after the selected
operation becomes terminal.

The selected operation may gain action authority only while all of these are
current and exact:

- the persistent assignment matches the operation and immutable spec digest;
- lifecycle state is `active` (after explicit `reservable -> reserved ->
  active` transitions), or is safely reactivated after a temporary block;
- the current step binding names the selected operation, current snapshot,
  current legal-action digest, and byte-identical advertised action;
- the current RequirementSet has no blocked premise and its actor/move-point
  claims name the current step;
- the source city remains owned, present, and covered by the non-moving chain
  participant;
- the native server route is current, authoritative, and reaches the exact
  step target before the operation deadline; and
- the ordinary impact-planner materialization and final execution gate both
  accept the exact action.

Every submitted chain step records its attempt and accepted/rejected result
against assignment, operation, spec, step, snapshot, legal-action digest,
action key, and engine result event. A rejected action terminates the pilot
fail closed. Temporary loss of movement or route availability grants no
authority; it may resume only after a later authoritative snapshot restores
all prerequisites.

## Durable boundary

A new atomic, identity-bound pilot store persists the single assignment and
its step attempts. Restart must recover the same assignment and may neither
redraw nor select another operation. Tampered game, player, experiment,
operation, spec, action, or result identity quarantines or rejects the store.

The existing replacement operation store remains the lifecycle authority. The
pilot store may record treatment ownership and execution evidence, but cannot
assert step satisfaction or completion. Only the existing adapter's
authoritative placement predicates may advance or complete the operation.

## Manifest boundary

A separate manifest capability,
`coordinated_replacement_execution=bounded-pilot`, freezes:

- the treatment and assignment-unit identities above;
- forced treatment and maximum one assigned operation per game;
- exact PR78 grounded-pair eligibility for initial assignment;
- current-step revalidation on every action;
- existing planner and final-gate enforcement;
- PR81 target `durable-completed-coordinated-replacement/32-turn/1.0`;
- `claim_eligible=false`, `randomized=false`, and no transition-value or
  induction readout; and
- no truth authority, flow retuning, scalar calibration change, or unrelated
  policy change.

## Frozen engine pilot

- engine seed: `109459` (known opportunity; not fresh);
- horizon: 160 turns;
- backend: `engine-live`;
- workers: one;
- resume: disabled for the confirmation run;
- maximum assigned chains: one; and
- output:
  `artifacts/freeciv/fdas-pr82-bounded-replacement-execution-pilot-v1`.

The known seed and forced treatment intentionally make the result unsuitable
for causal or gameplay inference.

## Acceptance

- component tests prove deterministic single assignment, atomic restart,
  terminal no-reassignment, identity/tamper rejection, exact activation,
  temporary-block abstention/reactivation, attempt accounting, and rejection
  failure;
- authority tests prove that stale snapshot, legal digest, binding,
  RequirementSet, source coverage, native route, deadline, operation, or spec
  evidence fails closed;
- the existing final execution gate remains downstream and every submitted
  action is accepted;
- the clean known-seed run assigns exactly one grounded chain and changes only
  exact actions attributed to that chain;
- the assigned operation records at least one accepted step attempt and reaches
  `completed` only through authoritative placement reconciliation;
- exactly one PR81 label opens for that completion; if its due turn is within
  the captured horizon it is observed exactly once, otherwise it remains an
  explicitly censored pending label;
- all operation, assignment, outcome, event, status, manifest, and source
  identities reconcile; and
- the final audit report is deterministic byte-for-byte.

If no chain completes or any gate fails, preserve the run as a failed pilot.
Do not widen authority, try another seed, or reinterpret accepted first-step
movement as chain success.

## Next decision boundary

A pass permits a separately preregistered fresh-seed experiment with treatment
assigned at the game level before gameplay. It does not permit opportunity-
conditioned causal claims, calibration fitting from this known seed, or a score
claim. A fresh design must define control behavior, clustering, missingness,
stopping, effective sample size, and outcome intervals before execution.

## Claim boundary

PR82 can establish multi-snapshot execution, lifecycle completion, and outcome
linkage mechanics for one deliberately selected known game. It cannot establish
beneficial chain value, candidate quality, policy improvement, score impact, or
win rate.
