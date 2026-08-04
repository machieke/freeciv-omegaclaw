# FDAS PR83 replacement-chain consequence diagnostic specification

Date: 2026-08-04

## Status and scope

This is an explicitly retrospective diagnostic over the already inspected
PR82 known-seed run. It is not a preregistered outcome analysis and cannot
change PR82's negative durability label or create a treatment-effect claim.

PR82 exposed a semantic distinction that its deliberately strict binary target
does not represent: both assigned actors were absent at observation, but both
cities remained owned, and the existing unit-lifecycle ledger attributes both
removals exactly to combat while defending. Before a fresh randomized design,
that distinction must be represented as an outcome vector rather than hidden
inside one Boolean.

## Frozen input

- parent report:
  `docs/freeciv/evidence/fdas-pr82-bounded-replacement-execution-pilot.json`;
- expected parent structural hash:
  `d5e51d12f87d5ab6ee656977dc80e7ea2df96bccb16781b075beb15b3264d3ea`;
- immutable game directory:
  `artifacts/freeciv/fdas-pr82-bounded-replacement-execution-pilot-v1/games/main/e_full_loop/109459-00`;
- exactly one completed assignment and one observed PR81 label; and
- authoritative `unit_lifecycle` events already present in that ledger.

## Consequence vector

For the completed assignment, the diagnostic will report these components
without combining them into a utility score:

- source city retained at observation;
- target city retained at observation;
- replacement actor present and at the source;
- reinforcement actor present and at the target;
- replacement and reinforcement transport status;
- exact first disappearance transition for each absent assigned actor between
  completion and observation;
- disappearance cause, evidence quality, turn, last position, lifecycle ID,
  and causal evidence-event IDs;
- assigned-actor survival count;
- city-retention count;
- exact combat-attributed loss count; and
- the unchanged original durability outcome and reason.

No weighted score, counterfactual value, causal relief, or preferred action is
derived.

## Consistency gates

The deterministic audit must require:

- the parent PR82 audit passes with the frozen structural hash;
- assignment, operation, label, actor, source-city, and target-city identities
  match exactly;
- the label is observed and remains byte-semantically unchanged;
- every actor marked absent has exactly one first disappearance event after
  completion and no later reappearance before observation;
- every actor marked present has no unexplained disappearance at observation;
- lifecycle evidence is causally linked, has a declared quality, and names a
  nonempty cause and detail;
- city and actor component counts reconcile to the original label fields; and
- the report is deterministic byte-for-byte.

## Interpretation boundary

The vector may reveal whether a negative durability label reflects city loss,
actor attrition, transport, placement drift, or unattributed disappearance. It
cannot say whether treatment caused any component, whether the combat losses
were beneficial trades, or whether the operation improved score or win rate.

## Next decision

A future fresh game-cluster experiment should retain the strict PR81 durability
target as one registered endpoint while separately registering city retention,
assigned-actor attrition, and exact combat-attributed loss as noninterchangeable
components. Any scalar utility or policy promotion rule must be specified and
calibrated independently before looking at fresh outcomes.
