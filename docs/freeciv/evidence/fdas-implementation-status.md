# Functional Dependent AtomSpace implementation status

Date: 2026-08-02
Plan: `agent-instructions/functional-dependent-atomspace-implementation-plan.md`

| Phase | Realized component boundary | Evidence |
|---|---|---|
| 0 | Contract/catalog freeze and reproducible baseline | `fdas-phase0-baseline.md` |
| 1 | Typed atoms, predicates, scopes, transactions, compatibility facade | `fdas-phase1-typed-core.md` |
| 2 | Dependency indexes, support-aware invalidation, compatibility-record, rich-component, city/unit entity and exact legal-action incrementality, incremental/cold parity, leases | `fdas-phase2-dependency-materializer.md` |
| 3 | Ruleset IR 2.0, capability projection, typed grounding, bounded generic proof parity | `fdas-phase3-ruleset-proof-foundation.md` |
| 4 | City/economy/research projection, local goals, shadow candidates | `fdas-phase4-city-economy-shadow.md` |
| 5 | FDAS pressure routes, exact resources/packets, canonical selected-operation explanations, commit revalidation and authority gates | `fdas-phase5-pressure-shadow.md`, `fdas-phase5-operation-resource-commit.md` |
| 6 | Unit/region/defense projection, movement, persistent operations, episodes | `fdas-phase6-*.md` |
| 7 | Expansion, recovery, settlement, corridors, transport, combat/task forces | `fdas-phase7-acceptance.md` |
| 8 | Opponent beliefs, contradiction quarantine, decision-sensitive observation | `fdas-phase8-acceptance.md` |
| 9 | Delayed attribution, contextual conductance, bounded induction, diagnostics, activation gates | `fdas-phase9-acceptance.md` |
| 10 | Legacy audit, facades, focused scopes, operator tooling, causal events, rollback, hardening | `fdas-phase10-acceptance.md` |

All phases are implemented and verified at the declared `component-only`
boundary. The rich construction path is now wired into reproducible harness
manifests and the engine adapter, with the checked profile still disabled; see
`fdas-runtime-assembly.md`. Captured replay and an accepted paired three-seed
engine-live cohort now exercise that seam, including post-legacy candidate
protection, bounded PF-v2 readout, stable sampled cold verification, and causal
evidence. The versioned manifest remains `component-only`: the empirical work
is diagnostic validation, not action authority or a gameplay-improvement
claim.

The strict captured replay additionally proves 37/37 incremental/cold
equivalence and validates canonical revision-bound explanations for all 38
shadow readouts. Grounded, gap, and not-applicable routes are explicit; this
closes the component-level selected-operation explanation requirement without
granting those explanations control authority.

The fresh engine cohort closes the declared component-level empirical gate:
188/188 actions and results were exact control matches, all five sampled cold
proofs were equivalent, FDAS contribution measured 147.31 ms p95 against the
150 ms gate, and full-controller latency measured 444.41 ms p95 against the
500 ms gate. See `fdas-engine-shadow-cohort.md` for the frozen design,
hardening trail, hashes, limitations, and non-claims.

## Post-substrate bounded authority

PR 13 now has a separate, default-off city-stability activation declaration.
The bounded readout can authorize only a byte-identical city-governor action
already selected by the legacy controller and backed by a current FDAS food
deficit. Captured replay exercised four authorized pass-through actions and 34
explicit fallbacks with zero winner changes and no replay failures. The
checked default manifest remains `component-only`; see
`fdas-bounded-city-authority.md` for the activation, rollback, exact commit,
and non-claim boundary.

A clean-source 160-turn engine confirmation on pinned seed `4543804` then
exercised 28 causally complete authorized pass-throughs and 336 explicit
fallbacks. All 367 engine actions received results, no action was rejected,
the terminal counters matched the event inventory, and all seventeen live
safety gates passed. This promotes PR 13's evidence from captured replay to
fresh bounded-authority engine execution, but it does not broaden the checked
default, change a legacy winner, or establish a score-improvement claim.

## Post-substrate defense shadow

PR 14 now has a defense-focused `shadow-live` config/manifest pair over the
existing unit, city-centered region, native-route, persistent operation, and
requirement substrate. A clean paired 30-turn engine check matched all 52
ordered actions and results plus terminal behavior, completed one sampled cold
verification, emitted no authority event, and passed the 150 ms FDAS and 500 ms
controller p95 gates. See `fdas-pr14-defense-shadow.md`. PR 15 bounded defense
authority and live episode attribution remain separate and are not implied by
this promotion.

## Post-substrate bounded defense authority

PR 15 now has a default-off bounded fortification implementation and accepted
captured replay. It can authorize only an exact legacy-selected
`unit_fortify` backed by a current FDAS fortification opportunity, exact actor
resource/packet scheduling, and commit revalidation. The frozen corpus
exercised 13 authorizations and 25 explicit fallbacks with zero winner changes
or replay failures. A linked episode fixture separates server acceptance from
the authoritative fortified effect and realized goal relief. See
`fdas-bounded-defense-authority.md`.

Fresh clean-source engine execution now exercises five causally complete
authorized fortifications and one evaluated in-domain fallback over a
160-turn horizon. All 367 engine actions received results, zero were rejected,
eight sampled cold verifications were equivalent, five durable episode chains
produced five isolated read-only conductance samples, terminal counters
matched, and all 23 live safety gates passed. Out-of-domain winners remain on
the exact legacy path without paying for an unused rich refresh.

PR 15 now passes the ordinary production-latency boundary in a separate clean
30-turn cohort: 27.00 ms FDAS projection p95 and 447.32 ms full-controller p95,
with two complete authorized episode chains and all 23 audit gates. The
160-turn stress cohort keeps FDAS below its budget at 101.16 ms p95, while the
broader late-game controller still measures 1,348.97 ms p95. This closes PR
15's implementation, safety, causal learning, and ordinary latency gates, but
does not establish a universal late-game latency or score claim and does not
activate the default profile. See `fdas-bounded-defense-authority.md` for exact
hashes and claim boundaries.

## Post-substrate expansion shadow

The expansion sub-slice of PR 16 now has an independent `shadow-live`
activation and clean engine evidence. It projects exact settlement,
population-recovery, corridor, requirement, resource-claim, and persistent
operation state while the legacy controller retains all action authority.
One clean 30-turn run exercised an exact founding action from proposal through
server acceptance to a later authoritative city effect, plus one explicitly
unattempted expiration. All 52 actions were accepted, no FDAS authority event
occurred, sampled cold verification was equivalent, and all 15 deterministic
audit gates passed.

Action-scoped refresh reduced unnecessary rich work while retaining the exact
same-snapshot founding binding. The accepted cohort measured 118.39 ms FDAS
projection p95 and 490.65 ms full-controller p95. See
`fdas-pr16-expansion-shadow.md`. This is a mechanism and preservation result,
not expansion authority or a gameplay-improvement claim; transport and combat
remain separate PR 16+ increments.

## Post-substrate transport capability shadow

The transport-capability sub-slice of PR 16 now has its own capability-only
`shadow-live` profile and accepted paired engine evidence. Protocol review
corrected a material state-contract error: FreeCiv's packet `carrying` member
is trade-goods metadata, while passenger load must be derived from complete
own-unit `transported_by` relations. In the clean paired 30-turn confirmation,
both arms materialized an empty Trireme scope on every FDAS refresh and emitted
62 total seat-resource plus 62 seat-available records. All 150 actions were
accepted, four sampled cold checks were equivalent, no authority or transport
operation event occurred, and FDAS projection p95 remained below 32 ms.

The accepted-action refresh quiet interval was then reduced from 50 ms to
20 ms without weakening the source-sequence lock, two-sample stability proof,
effect predicate, or fail-closed retry. A clean paired rerun brought
full-controller p95 to 412.68 ms baseline and 449.86 ms treatment, closing the
500 ms ordinary-latency gate while preserving all action and cold-parity
checks. See `fdas-pr16-transport-capability-shadow.md`. Transport operation
intent, lifecycle activation, replay/rollback, and bounded authority remain
`component-only`; this acceptance does not imply embark execution or gameplay
improvement.
