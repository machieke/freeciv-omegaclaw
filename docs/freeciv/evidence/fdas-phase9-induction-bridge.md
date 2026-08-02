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
held-out replay records a promotion verdict. Exact prerequisites, legal-action
binding, resource claims, commit validation, and downstream execution remain
outside and downstream of this learning bridge.

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
