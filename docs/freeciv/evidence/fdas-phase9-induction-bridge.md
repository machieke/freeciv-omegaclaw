# FDAS Phase 9 episode/induction bridge evidence

Status: episode encoding and quarantine lifecycle `shadow-live`; held-out
validation and rule readout `component-only`; no induction policy authority.

`FdasEpisodeInductionAdapter` is the fail-closed seam between durable FDAS
decision episodes and the existing bounded induction engine. It accepts only
goal-relief, effect-without-relief, and closed no-effect terminal outcomes.
Pending, contradicted, expired, and confounded episodes abstain.

Every sample uses explicitly selected episode context keys. Additional feature
IDs must cite evidence already linked by the episode. Shared execution-event
lineage is retained in induction provenance, so two rows from the same causal
event fail the independence check rather than inflating support. The adapter
does not mutate truth and exposes no action or policy authority.

Encoded samples enter the existing bounded `PatternMiner`. Every proposal is
created outside executable rule graphs, enters `InductionLedger` as
`quarantined`, and is invisible through `promoted_rules()` until disjoint
held-out replay records a promotion verdict. Promotion now additionally
requires a deterministic `InductionPromotionApproval` at schema version 1.0.
The approval binds the proposal, validation result hash, exact training and
validation episode IDs, and distinct training/holdout artifact hashes. It
explicitly records `policy_authority=false` and `readout_authority=false`.
Persisted promoted rows without this approval fail closed on load. Exact
prerequisites, legal-action binding, resource claims, commit validation, and
downstream execution remain outside and downstream of this learning bridge.

`FdasEpisodeInductionHeldoutGate` now implements the complete component-level
train/holdout lifecycle over two immutable `DecisionEpisodeStore` partitions.
It rejects shared store identities, content digests, episode IDs, or causal
provenance before mining. Every candidate is first persisted in quarantine,
then receives a deterministic replay verdict. A passing verdict gets the
versioned non-authorizing approval; a failing verdict is persisted as demoted
without an approval. Replaying the same partitions is ledger-idempotent.
Component fixtures exercise both a stable correlated promotion and a reversed
holdout demotion. These synthetic fixtures prove lifecycle correctness, not
that a useful FreeCiv rule has been discovered.

`FdasEpisodeInductionShadow` now runs this seam over durable engine episodes.
It emits causal encoding/mining latency and durable quarantine events, rejects
any promoted ledger state, and persists an empty hash-bound ledger when no
candidate clears the support/residual gate. The clean 160-turn confirmation
encoded five independent attributable outcomes in five evaluations at 0.502
ms maximum latency. All outcomes were positive, so no contextual residual was
available and the bounded result was zero proposals and zero promotions. See
`fdas-pr19-induction-shadow.md`.

Coverage is in `Autotests/test_freeciv_fdas_episode_induction.py`,
`Autotests/test_freeciv_fdas_induction_live.py`, and the existing
`Autotests/test_freeciv_pressure_induction.py` lifecycle suite.

The operational multi-store runner is
`scripts/freeciv/run_fdas_induction_holdout.py`. Its first strict engine-backed
split passed all mechanism and source gates but rejected the scientific
proposal gate because all 17 eligible outcomes were positive. See
[`fdas-pr22-induction-holdout.md`](fdas-pr22-induction-holdout.md). Held-out
promotion/readout therefore remains `component-only`.

The next component increment removes the immediate-relief target limitation.
`EpisodeInductionOutcomeLabelStore` durably records revision-bound delayed
labels without changing the source episode. The first declared target asks
whether an owned city still has authoritative own-unit coverage eight turns
after immediate fortification relief. Pending labels abstain; due-turn coverage
may resolve true or false; identity, episode digest, relief/assessment
revisions, observed value, and provenance survive atomic restart. Labels state
`truth_mutated=false` and `policy_authority=false`.

`FdasEpisodeInductionAdapter` can consume this label only when its target and
episode digest match and status is `observed`. Delayed target identity enters
the induction context and the combined episode/label artifact hashes enter any
promotion approval. Component train/holdout fixtures exercise a stable delayed
promotion with generalizable feature-v2 inputs.

Engine scheduling is now available only through the dedicated
`dependent_atomspace_defense_delayed_induction_shadow.yaml` profile and its
matching manifest. Activation requires the exact target ID, eight-turn window,
`policy_authority=false`, `induced_rule_readout=false`, and the
`delayed_induction_outcome_labels=shadow-live` capability. The live loop opens
one persistent label after authoritative immediate goal relief, resolves only
pending labels at or after their due turn from current authoritative own city
and unit state, and emits schema-validated lifecycle events and counters. A
separate auditor rejects identity/hash drift, early observation, missing
episode links, counter/event disagreement, source contamination, incomplete
horizons, or authority escape. This changes no candidate selection and does not
feed the label into engine rule mining or readout. A fresh clean 160-turn cohort
subsequently confirmed five exact due-turn observations with a schema-valid
31,066-event ledger and all audit gates accepted; see
[`fdas-pr23-delayed-induction-live.md`](fdas-pr23-delayed-induction-live.md).
All five delayed outcomes remained positive, so the lifecycle is empirically
confirmed `shadow-live` but discriminative delayed induction remains unproven.

The offline `run_fdas_induction_holdout.py` runner now accepts an explicit
`--outcome-target` plus independently repeated training/holdout outcome-label
stores. Delayed targets require both label partitions; immediate targets reject
label arguments. Source stores are hash-verified before they are combined, and
the runner rejects overlapping identities, artifacts, label IDs, episode-target
pairs, missing goal-relief labels, target drift, or empty accepted train/holdout
populations. The label artifact digests and target are included in the ledger
identity and any promotion approval. This exposes the delayed component gate
without activating live mining or readout.

The first strict delayed held-out split then encoded 17 engine-backed rows, all
positive, and rejected only its required proposal gate. See
[`fdas-pr24-delayed-induction-holdout.md`](fdas-pr24-delayed-induction-holdout.md).
This establishes that the eight-turn “any own unit coverage” target is too weak
for discovery in the measured regime; it does not justify weakening the
residual gate or manufacturing negative examples.

The next target is separately versioned as
`durable-attributed-actor-city-defense/32-turn/1.0` and has its own default-off
profile/manifest pair. It is eligible only for an attributable fortification
episode and resolves true only when, 32 turns after immediate relief, the same
actor remains present, owned, non-transported, on the still-owned city tile,
and in a fortified activity. Actor disappearance, reassignment, transport, or
loss of fortified state are distinct observed negative reasons. This target was
chosen from the explicitly exploratory window analysis in PR24; its component
implementation does not reuse those rows as confirmation and still has zero
live mining/readout authority.
