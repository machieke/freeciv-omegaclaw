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

All phases have a verified `component-only` substrate. Dedicated, default-off
profiles have since promoted selected slices to `shadow-live` or narrowly
bounded authority without broadening the checked default profile. The rich
construction path is wired into reproducible harness manifests and the engine
adapter; see `fdas-runtime-assembly.md`. Captured replay and engine-live
cohorts exercise post-legacy candidate protection, bounded PF-v2 readout,
sampled cold verification, causal episode attribution, uncertain belief
projection, observation-pressure selection, and quarantine-only induction.
The visibility-frontier continuation additionally binds packet-committed tests
to legacy-selected legal moves, revalidates them, and registers only fresh
authoritative returns through a no-write censoring firewall.
Each evidence report states its own authority and non-claim boundary; none of
these mechanism results alone establishes gameplay improvement.

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

The component-only transport lifecycle now also survives restart through one
atomic digest-verified bundle covering progress, canonical assemblies, the
one-repair budget, and pending settlement retention. Exact resource
reservations are never trusted across restart: the current authoritative
snapshot must reproduce the byte-identical legal step, claims, and capacity
before the reservation and binding return. Corruption or partially persisted
transitions quarantine/fail closed. This removes the persistence prerequisite
for live shadow operation activation.

## Post-substrate transport operation shadow

The founder/ferry operation is now grounded and `shadow-live` in a dedicated
profile. A clean paired 30-turn cohort produced the same durable operation in
both arms, including a current legal ferry move, all five resource kinds,
same-step re-estimation, structural projection, and fail-closed abandonment
when the legacy path removed the founder. It produced no exact legacy-action
match, commit, completion, or authority event. See
`fdas-pr16-transport-operation-shadow.md`. Bounded transport authority and
completed embark/disembark lifecycle evidence remain open.

## Post-substrate uncertain belief and observation pressure

PR 17 now projects real opponent observations and explicit confidence decay
into scoped, non-crisp AtomSpace revisions. Its clean paired 30-turn cohort
kept every live belief non-authoritative, invalidated expired supports instead
of inventing absence, preserved sampled cold parity, accepted all 135 actions,
and remained inside the 500 ms controller gate. No contradictory lineage
occurred in that cohort, so conflict/quarantine required the later independent
PR21 gate. See `fdas-pr17-belief-shadow.md`.

PR 18 routes one real opponent-presence uncertainty gap through bounded
value-of-information planning. A clean paired 30-turn cohort made two
decision-sensitive selections and two atomic CPU/observation packet commits
with zero evidence writes and zero policy authority. It did not execute an
observation or process an authoritative return. See
`fdas-pr18-observation-pressure-shadow.md`.

PR 20 closes a separate legacy-bound visibility execution path. A clean paired
30-turn cohort accepted all 149 actions, revalidated 72 exact scout-move
bindings, registered 70 fresh authoritative visibility returns, and censored
two accepted moves whose actors were no longer provable at the endpoint. The
censored returns wrote no evidence; all 13,892 events validated with zero
warnings and no policy authority. See `fdas-pr20-observation-return.md`.
This does not grant FDAS scouting choice or turn frontier visibility into
opponent-absence evidence.

PR 21 closes the remaining Phase 8 contradiction mechanism gate in a separate,
claim-ineligible diagnostic. Both clean 30-turn arms formed one conflict from
an explicitly capped model prior and an independent player-visible roster
lineage, partitioned both contexts, projected all four quarantines, accepted
all 114 engine actions, and emitted no authority. Both ledgers validate with
zero warnings. See `fdas-pr21-belief-conflict.md`. The synthetic prior is not a
calibrated opponent model and provides no score, win-rate, or belief-policy
claim.

## Post-substrate episode induction shadow

PR 19 now feeds durable attributable defense episodes into the bounded miner
in a dedicated `shadow-live` profile. A clean 160-turn run accepted all 353
actions, encoded five independent goal-relief episodes in five causal
evaluations, persisted a hash-valid ledger, and produced zero promotions at
0.502 ms maximum induction latency. Because every outcome was positive, no
contextual residual existed and the correct result was zero proposals. This
closes live episode encoding and quarantine persistence, not useful discovery,
held-out promotion, or induced-rule readout. See
`fdas-pr19-induction-shadow.md`.

PR 22 adds a fail-closed multi-store train/holdout runner and requires a
versioned, artifact-bound, explicitly non-authorizing approval for every
promotion. Its first frozen live split used 10 training and seven holdout
episodes from three clean horizon-complete games. All 17 outcomes were goal
relief, so the strict nonzero-proposal gate correctly failed with zero
candidates or promotions. See `fdas-pr22-induction-holdout.md`. More runs of
the same immediate-fortification target are unlikely to fix the missing
contrast; a non-tautological delayed outcome and generalizable features remain
the next Phase 9 scientific gate.
