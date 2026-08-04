# FDAS PR94 retained-capacity episode dataset preregistration

Date: 2026-08-04

## Question

PR93 proved that retained-capacity terminal labels can be encoded in the common
decision-episode vocabulary while remaining isolated from live learning and
readout. PR94 asks a narrower offline question: does the existing fixed PR92
diagnostic cohort contain enough independent outcome diversity to justify
fitting or validating a retained-capacity transition-value model?

This is an evidence-adequacy audit, not an effectiveness experiment. The PR92
aggregate counts are already published, so no outcome in this exercise is
unseen. The purpose of freezing the audit before implementation is to prevent a
sparse dataset from being silently treated as adequate training evidence.

## Frozen source cohort

The only input is the immutable PR92 engine cohort:

- artifact root:
  `artifacts/freeciv/fdas-pr92-retained-capacity-outcome-v1`;
- source commit: `db96e2045a118d13747ca8da199f88cf1c5cf2f2`;
- parent report structural hash:
  `e061c529bb31153316ab7947810ae3e35f25c4fa76a04e49dd411e8cb008528f`;
- seeds: `111521, 111533, 111539, 111577, 111581, 111593, 111599,
  111611, 111623, 111637, 111641, 111653, 111659, 111667, 111697,
  111721`.

All 16 games remain in the dataset, including games with no retained queue and
no terminal episode. No seed may be replaced, retried, resumed, or omitted.

## Frozen export semantics

For each game, the exporter must:

1. rerun the complete strict PR92 live audit;
2. verify the clean source commit and evidence digests;
3. load the typed retained-capacity outcome store with its exact
   manifest/attempt/game identity;
4. retain every label and require all labels to be terminal;
5. bind every label to exactly one retained-queue proposal;
6. reconstruct the episode using the production PR93 bridge, not a parallel
   mapping implementation;
7. record the exact episode, proposal event ID, label ID, game ID, seed, and
   parent audit hash;
8. retain an explicit zero-episode game row where no label exists; and
9. produce a deterministic dataset hash and byte-identical second export.

The export is offline. It must not modify an engine artifact, manifest,
episode store, calibration model, conductance table, induced-rule ledger, or
controller configuration.

## Frozen descriptive summaries

The report will count independent games, terminal episodes, and the three
common terminal statuses:

- `no-effect-observed`;
- `effect-without-goal-relief`;
- `goal-relief-observed`.

It will also report 95% Wilson intervals for fixed-cohort descriptive rates:

- games with at least one episode / all fixed games;
- exact-product effects / terminal episodes; and
- durable goal relief / terminal episodes.

These intervals describe this reused diagnostic cohort only. They are not
population estimates and do not establish causal value.

## Frozen adequacy gates

Transition-value fitting and held-out confirmation remain prohibited unless
all of the following hold:

- at least 30 terminal episodes;
- at least 20 independent games with an episode;
- at least 10 `no-effect-observed` episodes;
- at least 10 `effect-without-goal-relief` episodes;
- at least 10 `goal-relief-observed` episodes;
- every episode has exact proposal, RequirementSet, resource-claim, deficit,
  revision, and terminal-label provenance;
- no duplicate operation, label, episode, or game/seed identity;
- no quarantine or parent-audit failure; and
- discovery and confirmation cohorts are both declared and disjoint.

Because the source has only 16 games, the independent-game threshold cannot
pass. This deliberate fail-closed gate quantifies what additional evidence is
needed and prevents retrospective fitting from being presented as validation.

## Acceptance criteria

PR94 mechanics pass if the exporter is deterministic, retains all fixed games,
recomputes every episode exactly, passes every parent audit, and produces the
frozen summaries and adequacy decision. The expected scientific decision is
allowed to be `insufficient-evidence`; that is not an implementation failure.

Synthetic tests must reject duplicate seeds, source-commit mismatch, missing
proposal evidence, nonterminal labels, tampered labels, duplicate operation
identity, and parent-audit rejection.

## Claim boundary

A mechanically accepted export establishes only that the existing PR92
diagnostic evidence can be transformed losslessly into a deterministic offline
episode dataset. It does not fit a model, validate calibration, update
conductance, authorize readout, estimate a population rate, or claim score or
win-rate improvement.
