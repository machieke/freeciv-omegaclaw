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

PRs 23–26 add revision-bound delayed outcomes and close two complete discovery
cycles. The original 8-turn city-coverage target produced 17/17 positives and
was rejected as non-discriminating. The replacement 32-turn exact-actor target
produced real contrast and eight quarantined proposals. An expanded untouched
15-example holdout demoted all eight: four never activated and four worsened
out-of-sample Brier score and calibration. This proves fail-closed held-out
adjudication, not useful learned rules; see `fdas-pr23-*` through
`fdas-pr26-*`.

PR 27 introduces the opt-in `defense-episode-features/3.0` discovery schema.
It removes exact unit type from mined features and adds bounded lifecycle,
local redundancy, economy, production-class, and explicitly visible-threat
context. Existing `2.0` profiles are unchanged, schema/profile mismatches fail
closed, and induced readout remains disabled. All earlier inspected cohorts
are excluded from confirmation; see `fdas-pr27-causal-induction-features.md`.

PRs 28–29 complete that fresh discovery/confirmation cycle. Nineteen clean
discovery labels produced 32 frozen quarantined proposals; a separate 14-label
untouched confirmation cohort promoted 13 syntactic rules across four distinct
activation signatures and demoted 19. Exact unit type is absent, while compact
city size and unit-production context transferred. Promotions remain
artifact-bound and non-authorizing because induced readout is disabled. See
`fdas-pr28-causal-induction-discovery.md` and
`fdas-pr29-causal-induction-holdout.md`.

PR30 adds an approval-bound, deterministic structural-subsumption layer. It
uses no held-out outcomes or metrics and reduces the 13 PR29 promotions to a
four-rule diagnostic basis by suppressing nine stricter conjunctions with the
same training population and calibrated prediction as a retained singleton.
Different predictions and incomparable rules remain distinct. Because the
policy was designed after PR29, this is a retrospective mechanics audit, not a
readout or gameplay confirmation; truth, policy, and induced-rule readout
authority remain false. See `fdas-pr30-promoted-rule-consolidation.md`.

PR31 adds an outcome-blind, uncertainty-aware shadow readout and evaluates it
on six preregistered fresh 160-turn games. All 20 delayed labels and source
audits passed; 19 episodes received predictions, one abstained for no matching
operation scope, and none conflicted. Conditional Brier score improved by
`0.00771` and log loss by `0.02081`, but the paired 95% Brier-improvement
interval `[-0.01402, +0.02530]` crosses zero. This repeats the directional
point improvement without establishing statistical superiority, intervention
value, gameplay impact, score, or win rate. Induced readout remains entirely
non-authorizing. See `fdas-pr31-promoted-rule-shadow.md`.

PR32 joins that exact approved basis to snapshot-bound fortification choice
sets and reconstructs the typed PF scores behind the emitted schedule. A
clean, deterministic 38-snapshot replay evaluated 101 candidates, produced 80
nonzero contextual priority deltas, and had complete prediction coverage in
21 evaluations. Twenty-nine evaluations contained multiple same-category
candidates, but none changed the category-local winner because the retained
rules do not differentiate actors within those choice sets. The live
capability remains shadow-only and changes no truth, schedule, authority, or
action. See `fdas-pr32-candidate-impact-shadow.md`.

PR33 makes those category-local choice sets durable and outcome-safe. Exact
outcome-free queries, priorities, ranks, legal action keys, and the actual
in-scope selection are hash-bound per decision. Only a selected, executed,
episode-linked candidate may receive its delayed label; every nonselected,
out-of-scope, rejected, or unlinked row remains explicitly censored and cannot
be exported as a negative training example. A 160-turn diagnostic smoke
completed 367 actions with zero rejections, validated all 31,103 events, and
resolved five selected positive outcomes across six choice sets; the sixth set
had no in-scope selection and remained censored. The seed had neither outcome
contrast nor multi-candidate live decisions, so candidate-specific calibration
and rank improvement remain open. See
`fdas-pr33-candidate-choice-calibration.md`.

PR34 preregistered three clean 160-turn games to measure whether that exact
fortification slice yields usable candidate competition. All 62,676 events,
stores, censorship rules, and non-authority checks passed, with 15 observed
selected outcomes and real 11/4 positive/negative contrast. The pilot still
failed mechanically because one seed was eliminated at turn 153, and it failed
the scientific progression gate because all 15 choice sets contained exactly
one candidate. Live graph RCA found no truncation: each exact `(unit, city)`
fortification-opportunity atom admitted one matching legal action while other
defense operations were garrison moves outside the frozen rule scope. More
sampling cannot create an actor-ranking comparison in this sequential slice;
the next bounded target is an action-stratified competitive defense choice
surface with observational episodes for accepted legacy-selected actions. See
`fdas-pr34-candidate-choice-yield-pilot.md`.

PR35 implements the bounded correction identified by that failure. A distinct
non-authorizing defense choice surface records exact legal garrison moves and
fortifications in one observational decision set, while keeping action and
lifecycle strata in every outcome-free feature query. The legacy planner
still selects every action; only its accepted exact selection can open an
episode and receive the new 32-turn selected-actor persistence label.
Contextual conductance, promoted-rule readout, transition estimates, and
nonselected labels are all disabled. One 160-turn engineering smoke produced
15 selected sets, 71 choices, 13 multi-candidate sets, and seven observed
outcomes with 4/3 positive/negative contrast, with zero rejected actions and
30,159 valid events. This repairs candidate-choice yield, not calibration or
ranking. The smoke was intentionally treated as claim-ineligible because
regenerated replay reports made its source worktree dirty; a fresh
preregistered clean-source yield cohort remains the next gate. See
`fdas-pr35-defense-choice-surface-smoke.md`.

PR36 froze and executed three fresh clean 160-turn seeds before inspecting
their outcomes. All 52,666 events and all store/non-authority checks passed,
and the cohort contained real 9/2 delayed positive/negative contrast. The
scientific progression gate nevertheless failed: it produced 11 rather than
12 observed outcomes, only two rather than three mixed-action sets, and zero
selected garrison moves. RCA found nine legal move alternatives but all were
censored; surface sampling was incorrectly coupled to the narrow legacy
candidate category. PR35's ten selected moves were also one actor's sequential
relocation in one seed, not broad independent support. The next bounded
correction is exact selected-action-family sampling plus later
game/actor/lifecycle grouping. No transition model may be fitted on PR36. See
`fdas-pr36-defense-choice-surface-yield.md`.

PR37 removes that legacy-category coupling and samples exact selected unit
move/fortify action families. A fail-closed engineering sequence additionally
found and fixed ambiguous one-action/multiple-city bindings and made
multi-turn move attribution use the inclusive authoritative server route ETA.
On the final clean 160-turn differential, the surface produced 86 opportunity
sets, 300 choices, 12 selections across both action strata, and eight observed
outcomes with 6/2 contrast. Three move rows were labeled, but they correctly
collapse to one observed actor/route lineage. The audit now requires observed
lineages as well as raw rows, so this engineering smoke remains ineligible for
discovery. See `fdas-pr37-action-family-route-smoke.md`.

PR38 passed a stricter preregistered four-seed independent-yield gate from one
clean commit. Across 78,700 valid events it produced 25 observed selected
outcomes with 19/6 contrast, 109 multi-candidate sets, 15 mixed-action sets,
two independent observed move lineages, and 17 fortification lineages. Every
mechanical, source, censorship, non-authority, stratum, contrast, and lineage
gate passed. This permits a fresh, action-stratified, lineage-clustered
calibration discovery design; PR38 remains excluded from fitting and does not
establish calibration, ranking, gameplay, score, or win rate. See
`fdas-pr38-action-family-yield.md`.

PR39 implements the permitted non-authorizing calibration substrate without
fitting the inspected PR38 cohort. New choices carry durable game-local
actor/target/action lineages, and selected-only exports preserve those
lineages while all alternatives remain censored. A typed action/lifecycle
model collapses sequential rows to effective lineage contributions, reports
Wilson 95% intervals, backs off only within the same action stratum, and
abstains below frozen support. Export, bin, model, and prediction hashes are
recomputed on load; every artifact explicitly denies truth, policy, and
readout authority. The fitting command refuses dirty, overlapping,
quarantined, mechanically invalid, or progression-inadequate discovery data.
This establishes implementation safety, not calibration or decision value;
fresh discovery and disjoint confirmation remain required. See
`fdas-pr39-candidate-calibration-artifact.md`.

PR40 executed the first eligible ten-game calibration discovery cohort after
freezing its seeds and gates. A discarded partial attempt exposed and repaired
a monotonic episode-evidence bug; the complete cohort was then restarted from
one clean corrected commit and contains 268,617 valid events with zero
warnings, rejections, or failures. All progression gates passed: 73 selected
outcomes have 46/27 contrast and collapse to 11 observed move plus 44 observed
fortification lineages. The fitted action-level move estimate is `0.534` with
a wide Wilson interval `[0.280, 0.787]`; fortify is `0.709` with interval
`[0.582, 0.837]`. Sparse lifecycle bins remain wide and use frozen within-
action backoff. This is an in-sample descriptive model only; it remains
non-authorizing and may not rank candidates until a disjoint confirmation
gate passes. See `fdas-pr40-candidate-calibration-discovery.md`.

PR41 implements the disjoint confirmation evaluator without inspecting the
reserved seeds. It validates the frozen model and source independence,
collapses route rows to durable lineages, and reports action-stratified Brier,
log loss, calibration-in-the-large, empirical Wilson intervals, and a
game-clustered lifecycle-versus-action-only bootstrap. All artifacts remain
selected-only and non-authorizing, and the evaluator fails closed on overlap,
missing provenance, insufficient support, threshold failure, or model hash
mismatch. Confirmation remains the next gate. See
`fdas-pr41-calibration-confirmation-evaluator.md`.

PR42 passed its preregistered eight-game held-out confirmation. All 203,909
events validate without warnings; source, store, censorship, lineage, outcome,
and action-stratum gates passed with zero failures or rejections. The frozen
model covered all 43 effective lineages, with Brier `0.200`, log loss `0.585`,
and calibration error `0.023`. Lifecycle conditioning improved Brier by
`0.0069`; its game-clustered 95% interval `[-0.0267, +0.0296]` establishes
frozen noninferiority, not superiority. Move remains weak at six lineages,
Brier `0.275`, and calibration error `0.236`; fortify has 37 lineages and
Brier `0.188`. This permits only a protected shadow candidate-union readout,
with uncertainty and same-action abstention intact. It does not establish
counterfactual ranking value, gameplay impact, score, or win rate. See
`fdas-pr42-candidate-calibration-confirmation.md`.

PR43 implements the permitted calibrated protected-union shadow. Scalar top-1
is always protected, calibration may add at most one confidence-eligible
candidate per action family, and wide or unsupported intervals abstain. The
calibrated estimate never enters the final score and the event surface denies
selection, truth, policy/readout, advection, and capacity authority. An
outcome-blind replay over prior choice stores established useful engineering
yield only. See `fdas-pr43-calibrated-candidate-union-shadow.md`.

PR44 was the first fresh protected-union cohort and passed its progression
counts, but it remains mechanically rejected because one genuine player
elimination ended before the preregistered fixed horizon. Its 329 unions and
20 additions cannot support the claim. See
`fdas-pr44-calibrated-candidate-union.md`.

PR45 repeated the cohort with terminal-aware completion frozen in advance and
passed every gate. Across 390 unions it produced 15 calibrated additions in
five of eight games, with a Wilson game-level lower bound of `0.306`, zero
selection changes, and zero authority leakage. This establishes recurrent
calibrated recall beyond scalar top-1, not ranking quality or gameplay. See
`fdas-pr45-calibrated-candidate-union.md`.

PR46 implements corrected forward/backward probes over an exact legal-action
factor graph as a second membership-only layer. Graph, batch, selection,
signal-ledger, revision, and result hashes are explicit; incomplete or
unhealthy probes return the calibrated union unchanged. A claim-ineligible
engineering smoke motivated tightening the live cap from four probe regions
to one before confirmation. See `fdas-pr46-probe-candidate-union-shadow.md`.

PR47 passed the preregistered eight-game corrected-probe confirmation. All 445
probe evaluations were healthy and all factor graphs complete; 949 readouts
produced 161 bounded additions in all eight games. The Wilson game-level lower
bound was `0.676`, with zero fallbacks, rejections, or selection changes. This
establishes recurrent probe-informed candidate recall beyond the calibrated
union while preserving scalar authority. It does not establish candidate
precision, ranking, score, or win rate. See
`fdas-pr47-probe-candidate-union.md`.

PR48 implements path persistence as a third membership-only layer rather than
reviving the historically adverse CT4 ranking authority. Stable current
corridors use smoothing, bounded momentum, dwell, hysteresis, immediate expiry,
and a maximum reachability-regret gate. A clean 160-turn engineering smoke
produced 11 temporal additions, 18 smoothing retentions, 12 regret reanchors,
and 9 expiries, with zero fallback or authority leakage. The smoke and its seed
are claim-ineligible; a fresh cohort remains required. See
`fdas-pr48-path-persistence-union-shadow.md`.

PR49 passed the preregistered eight-game path-persistence confirmation. Across
654 unions, 1,613 readouts produced 162 temporal retentions and 105 additions
in seven of eight games. The Wilson game-level lower bound was `0.529`; the
regret gate reanchored 91 proposals and 130 absent routes expired. There were
zero fallbacks, rejected actions, selection changes, or authority leaks. Audit
version 1.1 corrected an unpreregistered positive-regret assumption while
strengthening exact-regret and route-continuity checks; the initial rejection
is preserved in Git. This establishes bounded temporal candidate recall, not
precision, gameplay, score, or win rate. See
`fdas-pr49-path-persistence-union.md`.

PR50 adds an exploratory delayed-relevance comparator for first unique
persistence-only corridors. Against deterministic within-decision near-tied
non-probe controls, persistence was not incrementally predictive within eight
decisions: probe re-entry was 12/15 versus 13/15 and future scalar-winner status
was 10/15 versus 11/15, both paired deltas `-0.0667`. Only 17/30 routes had a
valid control, so the result is imprecise and claim-ineligible, but its direction
fails the source--sink-flow entry gate. The next bottleneck is authoritative
alternative-candidate value, not faster transport. See
`fdas-pr50-path-persistence-relevance-discovery.md`.

PR51 begins that alternative-value program with a strictly non-executing,
propensity-recorded assignment shadow. Persistence-only alternatives produced
zero eligible interventions in the engineering smoke, so the frozen
correction uses an exact bounded nearest-score garrison alternative. One clean
160-turn game produced one fully preflighted pair across 166 evaluations: both
arms shared unit class, movement cost, destination, target city, deficit atom,
priority, and risk while retaining distinct actor resources and independent
pressure/packet/commit proofs. The stable 50/50 draw selected control; no
assignment was executed, no winner changed, and all 406 engine actions were
accepted. The observed yield is about one opportunity per game and is far too
sparse for a score claim. A small claim-ineligible execution-and-attribution
pilot is the next gate; see `fdas-pr51-safe-alternative-shadow.md`.

PR52 through PR52d exercised the first bounded randomized alternative action
through progressively hardened startup, authority-event, and episode-revision
ordering. PR52d finally completed the 160-turn game with one accepted treatment
selection and exact assignment/action/episode/choice linkage, but exposed a
scientifically consequential label defect: the alternative's first movement
effect had no immediate goal relief, so it received no delayed label and its
choice remained pending without a due turn. PR52d is mechanically rejected and
excluded from fitting. Commit `6774edd` now indexes the selected-actor outcome
at accepted selection for both relief and no-relief actions, persists its turn
for restart recovery, and opens the 32-turn label immediately. The frozen PR52e
retry is the next gate; see
`fdas-pr52e-randomized-execution-pilot-preregistration.md`.

PR52e proved the corrected label lifecycle: its accepted randomized episode
opened at turn 17, received a due-turn-49 selected-actor label despite having
effect without immediate relief, resolved that label as negative at turn 49,
and propagated the result to the exact choice set. However, it exercised the
control arm because the old randomization key included revision and diagnostic
hashes changed by the new provenance. It is therefore mechanically rejected.
Commit `1a14afd` isolates assignment to the exogenous game-turn exact-action
pair, experiment, policy, and seed; bookkeeping-hash invariance is unit-tested.
The frozen, claim-ineligible PR52f treatment retry is the next and final
mechanics gate; see
`fdas-pr52f-exogenous-assignment-pilot-preregistration.md`.

PR52f passed the final randomized mechanics gate. The exogenous turn-17 draw
selected treatment actor `117`; the exact action was accepted and linked once,
its selection-indexed label opened immediately with due turn 49, and the label
resolved negative at turn 49 into the linked choice set. All 406 engine actions
were accepted, and a new reusable auditor verifies source/store hashes,
assignment reconstruction, propensity, preflight evidence, causal ancestry,
episode/label/choice linkage, missingness, and authority isolation. This is
still a targeted one-opportunity pilot and makes no value or score claim. The
next gate is a separately preregistered fresh-seed randomized outcome cohort;
see `fdas-pr52f-exogenous-assignment-pilot-preregistration.md` and
`fdas-pr52f-exogenous-assignment-pilot.json`.

PR53's 12-game fresh-seed launch was rejected before gameplay because the
required local ruleset binding was omitted. PR53b supplied only that
environment correction and exposed two multi-game defects that the targeted
pilot could not reveal: three choice-set identity collisions and one exact
rematerialization failure. Eight games completed, seven reached the fixed
endpoint, and the cohort is mechanically rejected. Of three raw treatment
events, two belonged to the failed rematerialization game and audit 1.3
correctly excludes them. The sole analyzable turn-111 treatment was accepted
and resolved positive at turn 143, but there were zero control outcomes and no
effect estimate. See `fdas-pr53b-randomized-outcome-yield-preregistration.md`
and `fdas-pr53b-randomized-outcome-yield.json`.

Commit `db11226` hardens decision-safe readout. Candidate choice IDs now bind
the complete immutable record, including game, snapshot, choices, and
selection provenance. Exact bounded city-defense authority prefers the cached
catalog but can reproject only its byte-identical current move/fortify action
through the existing operation-authority candidate path when the legacy
catalog is narrower; unrelated action types fail closed. Audit 1.3 also
preserves incomplete failed games and separates raw assignment events from
mechanically analyzable outcomes. The exact four failure seeds are frozen for
the claim-ineligible PR54 mechanics replay before another fresh cohort.

PR54 completed all four historical failure seeds to the 160-turn fixed endpoint
with zero infrastructure failures, zero engine rejections, and no recurrence of
the three identity collisions or exact-rematerialization exception. Seven
assignments completed their exact action, episode, choice, and due-turn outcome
lifecycles. The frozen progression rule nevertheless failed: designated seed
`105529` drew two controls and no treatment, so it could not prove that seed's
formerly failing broader action. Audit 1.4 now supports seed-scoped treatment
and reprojection requirements. Alternative execution events version 1.1 also
carry a typed `authority_catalog_reprojected` field, backed by an exact
per-decision diagnostic delta and aggregate status counter. This closes the
observability ambiguity for a targeted, claim-ineligible reprojection retry;
fresh unseen-seed outcome-yield evaluation remains downstream of that proof.

PR54b supplied that proof. On historical seed `105529`, a frozen post-hoc
assignment kept turn 37 on control and selected treatment at turn 39. The
treatment's exact move was absent from the cached legacy catalog, was
reprojected once through bounded city-defense authority, accepted by the
engine, linked to one episode and selected choice, and resolved its turn-71
label. Event version 1.1 and the aggregate status counter both record exactly
one reprojection; audit 1.4 passes every ledger, store, source, endpoint,
authority, treatment, and reprojection gate. PR54b remains claim-ineligible and
its negative outcomes are not evidence of value. The engineering blocker is
closed, so the next gate is an unseen-seed opportunity-yield cohort using the
same frozen controller and provenance contract.

PR55 then supplied a clean 12-seed unseen-gameplay yield cohort. Eight exact
assignments completed—four per arm—with four observed outcomes and two
independent game clusters per arm, satisfying the frozen yield-only progression
threshold. Eleven games reached turn 161; seed `105667` was authoritatively
eliminated at turn 138 with terminal-absorbing score carry-forward and zero
randomized assignments. Because the preregistration required every row's
`horizon_reached` flag, the primary audit is mechanically rejected despite all
ledger, store, source, authority, execution-version, outcome, propensity, and
counter gates passing. The descriptive treatment-minus-control durable-defense
risk difference is `-0.75` with interval `[-0.9544, 0.1892]`; it is sparse,
clustered, claim-ineligible, and cannot tune the next design. The next
hardening task is to preregister terminal absorbing endpoints explicitly, then
size a powered candidate-value cohort solely from observed assignment and game-
cluster yield.

Audit 1.5 now exposes that contract as an explicit opt-in rather than silently
equating early completion with a fixed horizon. A terminal endpoint is accepted
only when the game completed without infrastructure failure, an authoritative
game-over or player-elimination flag exists, observer score authority and turn
match the final observed turn, the score declares absorbing carry-forward, and
no randomized assignment remains pending. A post-hoc sensitivity audit passes
the immutable PR55 artifact under this rule, while the preregistered audit 1.4
failure remains the primary verdict. Future powered work can preregister audit
1.5 and avoid treating legitimate terminal absorption as missingness.

An outcome-blind power planner now consumes only the passed terminal-aware
yield material: 12 games, 3 opportunity games, 8 assignments, and 2 arm-bearing
game clusters per arm. It cannot read positive counts, rates, or the observed
risk difference, and mutation tests prove outcome-direction invariance. For a
predeclared material risk difference of `0.35`, two-sided alpha `0.05`, power
`0.80`, planning ICC `0.25`, 20 game clusters per arm, and a 25% yield safety
factor, it requires 44 assignments per arm and 168 games. Estimated engine time
is 13.71 hours, about 3.43 wall hours on four workers at PR55 throughput. A
separate game-cluster bootstrap discovery analyzer requires the planned counts
and advances only when its 95% interval lower bound is above zero; even then a
same-sized held-out confirmation remains mandatory. The frozen power plan is
`fdas-pr56-candidate-value-power-plan.json`, plan hash
`ba88a0c89575dfde0bc5ba3a7c4836ab20e6361a31baaea0844acd9f9b4c4d89`.

PR56 then executed the fixed 168-game powered discovery design. It closed 166
games and preserved two engine-rejection failures. Seed `106417` selected an
off-map move that the proxy had incorrectly advertised as valid; seed `107123`
replayed an already accepted randomized move after the authoritative refresh
timed out and the stale legal catalog remained visible. Audit 1.5 rejects the
cohort and preserves both rows. Yield independently missed power: 30 observed
control outcomes in 18 game clusters and 27 observed treatment outcomes in 20
clusters, below the required 44 and 20 per arm. The invalid descriptive risk
difference was `-0.20` with interval `[-0.5112, 0.1603]`, so the frozen positive
discovery rule does not permit confirmation even aside from mechanics and
yield. See `fdas-pr56-candidate-value-discovery-preregistration.md` and
`fdas-pr56-candidate-value-discovery-mechanical.json`.

PR57 hardens both failures without retuning the intervention. Spatial actions
outside authoritative map dimensions are removed before entering the canonical
legal digest. Any accepted unit action whose authoritative refresh times out
now ends the same-snapshot action phase, preventing both legacy and FDAS
authority from replaying stale unit scope. A 294-test state/harness/Impact suite
passes. The exact two known failure seeds are preregistered for a permanently
claim-ineligible engineering replay before further candidate-value design; see
`fdas-pr57-execution-hardening-replay-preregistration.md`.

PR57c closes that engineering replay after two intentionally preserved launch
corrections: PR57 omitted the local ruleset binding, and PR57b exposed that the
randomized FDAS paths had also been ambient rather than configuration-bound.
Strict seed overlay 1.1 now permits only the exact FDAS config/manifest path
pair, and the replay profile declares both. From clean commit `1091c93`, both
known seeds reached turn 161 with no failure or rejection. Audit 1.5 passes all
randomized lifecycle gates across 17 resolved assignments. A separate trace
audit checks 640 snapshots, 86,166 spatial legal actions, and 640 accepted
submissions: no coordinate is off-map, no accepted snapshot/action pair is
replayed, and no unit action follows an accepted unit action on the same
snapshot. All 142 spatial actions at seed `106417` turn 135 are canonical.
Seed `107123` completed three safe catalog reprojections, although its
non-deterministic refresh timeout did not recur and therefore did not increment
the new guard counter. This closes the frozen engineering gate only. PR56's
adverse, under-yield candidate-value result remains unchanged; the next
scientific task is a mechanically defined alternative whose grounded
transition-value criterion differs from bounded nearest scalar score, not a
repeat of that intervention. See
`fdas-pr57c-execution-hardening-replay-preregistration.md`,
`fdas-pr57c-execution-hardening-replay.json`, and
`fdas-pr57c-execution-hardening-trace.json`.

PR58 begins the separate semantic correction without retuning or reusing the
failed nearest-score intervention. A new shadow-only readout compares the
active control with calibrated alternatives and emits a counterfactual
preference only when the alternative lower confidence bound strictly clears
the control upper bound and exact native route, source-garrison, target,
resource, unit-type, health, mobility, veteran, and home-city facts are all
non-inferior. Missing groundings, interval overlap, and any mechanical
regression abstain with an explicit reason. The component cannot change the
selected action or truth and has a separately bound manifest/profile. Unit
tests cover separated acceptance, interval-overlap abstention, and native-route
inferiority abstention. The clean engine mechanics smoke from commit `5c0bccb`
reached observed turn 161 with zero failures, rejections, or resumes, and its
audit passes all gates. All 95 shadow evaluations correctly abstained. Only two
were matched in-slice choices; every candidate in each choice set received the
same broad lifecycle-backoff estimate and interval from three effective
lineages, making safe interval separation impossible. Relaxing the interval
width would not change that result. The next gate is therefore a separately
specified candidate-specific calibration design with fresh held-out evidence,
not a looser PR58 readout. See
`fdas-pr58-decision-safe-candidate-readout.md` and
`fdas-pr58-decision-safe-readout-smoke.json`.

PR59 repairs the identified information boundary without changing the frozen
model or readout. Reinforcement-move choice queries now append outcome-free,
exact-revision transition features for actor HP/type, native route time/cost/
length, source-city relation, and source-tile own/fortified support. Route
turn/non-future source sequence, actor origin/moves/transport state,
first-step tile, and
action cost must agree; otherwise the query records a bounded missingness
reason and unknown mechanics rather than imputing them. The PR40 model remains
byte-identical on enriched queries, fortification stays on its frozen schema,
and all authority remains false. Twenty focused and 180 broader tests pass.

The first PR59 integration smoke from `24ee0b3` failed that gate despite a
clean turn-161 endpoint: all 436 move queries were marked stale because the new
projection required route/source-sequence equality. Native route queries are
earlier responses within the same aggregate snapshot; established bounded
movement semantics require an exact turn and a non-future sequence while also
revalidating actor and first-step facts. PR59 and the latent identical PR58
check now use that rule, with unit coverage for accepted earlier and rejected
future route revisions. The failed feature-yield attempt remains excluded.

The corrected clean PR59 smoke from `6029496` passes. Seed `108013` reached
observed turn 161 with no infrastructure failure, resume, or rejected action.
All 435 move rows are completely grounded and expose 22 distinct transition
signatures; 65 of 75 multi-move sets contain more than one signature. All 19
fortify rows remain frozen, and all 435 enriched queries reproduce the exact
PR40 prediction. The parent PR58 mechanics also remains unchanged at 95
abstentions and zero preferences or action changes. This closes transition-
feature collection only. Candidate-specific fitting still requires a separate
preregistered discovery and untouched confirmation design; see
`fdas-pr59-candidate-transition-features.md` and
`fdas-pr59-candidate-transition-feature-smoke.json`.

PR60 freezes the next non-authorizing scientific gate before collecting any
new outcomes. A separate move-only model fits ten hierarchical levels from
action through full transition signature + lifecycle, collapses repeated rows
to durable lineages, shrinks child centers toward exact parents with a fixed
strength of four, and keeps interval width at actual child N. Unsupported,
incomplete, non-move, and unseen strata abstain or back off explicitly. A
disjoint held-out evaluator freezes coverage, discrimination, Brier, log-loss,
calibration, empirical-interval, and game-clustered noninferiority gates.
Synthetic tests prove separated supported strata, sparse backoff, lineage
collapse, abstention, artifact tamper rejection, discovery/confirmation source
separation, passing aligned holdout, and failing adverse holdout. No model is
loaded into live readout. See
`fdas-pr60-candidate-transition-calibration-preregistration.md`.

PR60 discovery passed from clean commit `67c3c0e`. All 12 games reached turn
161 with zero failures, rejections, or resumes. The feature audit validated
716 choice sets, 1,520 completely grounded moves, 83 transition signatures,
343 diverse multi-move sets, and byte-identical PR40 predictions. All frozen
yield gates passed: 48 selected move outcomes (25 positive, 23 negative)
collapsed to 17 lineages across six games and 14 selected signatures. The
fitted 102-bin model estimates all discovery moves, with 970/1,520 using a
candidate-specific level and 12 distinct prediction triples, but intervals
remain broad. This remains in-sample and non-authorizing; the untouched
confirmation cohort is the next gate. See
`fdas-pr60-candidate-transition-calibration-discovery.md` and
`fdas-pr60-candidate-transition-calibration-discovery.json`.

PR60's untouched 12-game confirmation is preserved as a failed primary result.
All games reached turn 161 with zero failures, resumes, or rejected actions,
and the model passed every frozen predictive-quality gate: coverage `1.000`,
candidate-specific fraction `0.700`, Brier `0.216`, log loss `0.624`,
calibration error `0.013`, and a game-clustered Brier-improvement interval of
`[+0.0063, +0.1005]`. The cohort nevertheless supplied only 10 held-out move
lineages from four games, below the frozen minima of 12 lineages and six games.
Neither favorable metrics nor sequential rows override those independent-yield
requirements. The model remains excluded from live readout. The next gate is a
new disjoint, prospectively sized replication that freezes the same model and
thresholds; PR60's reserved seeds cannot be added post hoc. See
`fdas-pr60-candidate-transition-calibration-confirmation.md` and
`fdas-pr60-candidate-transition-calibration-confirmation.json`.

PR61 prospectively freezes the required independent replication without
changing or refitting the PR60 model. Thirty new seeds are sized from the
mechanical four-of-twelve contributing-game rate; at that planning rate they
have approximately 96.5% binomial probability of supplying the unchanged
six-game minimum. All PR60 model, yield, validation, endpoint, and non-authority
contracts remain fixed. PR60 data cannot be pooled, and its reserved seeds stay
excluded. See
`fdas-pr61-candidate-transition-calibration-replication-preregistration.md`.

PR61 is preserved as a failed primary replication despite passing every
outcome-yield and predictive gate. The 30 clean games supplied 75 outcomes, 32
lineages across 14 games, 100% coverage, Brier `0.243`, log loss `0.679`, and a
clustered Brier-improvement interval `[-0.0024, +0.0139]`. Feature audit 1.0
rejected four mechanically valid sparse games because each game, including one
with only fortify choices, was required to contain a multi-move choice and
multiple grounded signatures. Cohort-wide mechanics were strong: all 2,951
move rows were completely grounded and frozen-model compatible, with 640
diverse multi-move sets and no feature errors. Because the per-game audit rule
was frozen, this cannot be repaired post hoc. The next step is a versioned
prospective audit that keeps row invariants per-game and moves opportunity
yield to cohort scope, followed by another disjoint replication. See
`fdas-pr61-candidate-transition-calibration-replication.md` and
`fdas-pr61-candidate-transition-calibration-replication.json`.

PR62 versions the audit correction prospectively. Audit 2.0 keeps store,
schema, grounding, frozen-prediction, fortify, error, and parent-mechanics
requirements per game while measuring chance move competition and signature
diversity across the complete cohort. It consumes and hash-binds the full 1.0
report, and the original validator remains unchanged by default. An explicitly
post-hoc PR61 sensitivity passes audit 2.0 plus every frozen yield and
predictive gate, confirming the implementation but not changing PR61's primary
failure or granting activation. Fresh disjoint evidence remains required. See
`fdas-pr62-transition-feature-cohort-audit.md` and
`fdas-pr61-candidate-transition-calibration-cohort-audit-sensitivity.json`.

PR63 freezes the required fresh confirmation after audit 2.0. It retains the
same 30-game size, PR60 model, selected-action label, lineage semantics, yield
thresholds, predictive thresholds, endpoint rules, and scalar controller. All
30 seeds are new and disjoint from PR59–PR61, including PR60 reserves. No model
is loaded into live readout during collection. See
`fdas-pr63-candidate-transition-calibration-confirmation-preregistration.md`.

PR63 passes the fresh audit-2.0 confirmation from clean commit `bd6fe7b`. All
30 games completed without failure, resume, or rejected action. The cohort
supplied 70 selected move outcomes, 26 lineages across 12 games, and 742
diverse multi-move sets. The frozen model achieved 100% coverage, 84.6%
candidate-specific predictions, Brier `0.222`, log loss `0.655`, calibration
error `0.027`, and a game-clustered Brier-improvement interval of
`[-0.0049, +0.0332]`; every preregistered mechanics, yield, and predictive gate
passed. This establishes held-out selected-action calibration and permits only
a separate default-off shadow readout-yield experiment. It does not establish
censored counterfactual value, ranking quality, gameplay, score, or win rate.
See `fdas-pr63-candidate-transition-calibration-confirmation.md` and
`fdas-pr63-candidate-transition-calibration-confirmation.json`.

PR64 implements the separately permitted default-off grounded-transition
shadow readout without changing the confirmed model or the scalar controller.
The activating manifest hash-binds the PR60 discovery model and PR63
confirmation, protects scalar top-1, may recall at most one confidence-eligible
candidate per action category, and retains the existing strict interval-
separation plus exact grounded-noninferiority gate. Runtime events distinguish
candidate-specific transition predictions from broad action/lifecycle backoff,
calibrated additions, uncertainty abstentions, and decision-safe interval
overlap. All policy, readout, truth, flow, capacity, and action-selection
authority remains false. A fresh seed-`109007` engine smoke and its audit are
preregistered before collection; see
`fdas-pr64-grounded-transition-readout-smoke-preregistration.md`.

PR64's first command from `a9ac5d9` stopped in profile loading before a run
directory or game existed because the one-seed overlay violated the shared
30-seed profile schema. PR64a records this pre-collection failure, adds 29
unused seeds after fixed first seed `109007`, and explicitly executes only the
first seed with `--limit-seeds 1`. No model, threshold, auditor, authority, or
evidence was observed or changed; see
`fdas-pr64a-grounded-transition-readout-launch-correction.md`.

The corrected PR64 smoke passes from clean commit `d33bea6`. Seed `109007`
reached turn 161 with no failure, resume, or rejected action. Across 135 unions,
the confirmed model produced 458 estimates, all candidate-specific, and added
20 protected candidates beyond scalar top-1. All 124 fortify candidates
correctly abstained outside the move-only domain, and two move intervals were
too wide. The decision-safe layer nevertheless abstained 135 times: 128 active
legacy actions had no unique matching FDAS reinforcement route, four were not
reinforcement moves, two lacked complete control grounding, and one control
was out of slice. No comparison reached interval separation, and no action
changed. This closes model loading and protected candidate-yield mechanics but
identifies control alignment—not calibration coverage or uncertainty width—as
the next semantic bottleneck. See
`fdas-pr64-grounded-transition-readout-smoke.md` and
`fdas-pr64-grounded-transition-readout-smoke.json`.

PR65 implements a separate control-aligned readout rather than weakening the
failed PR64 comparison contract. Its frozen control is the protected union's
scalar top-1 FDAS candidate, and it considers only protected alternatives with
the same reinforcement operation type and target, disjoint resources, strict
interval separation, and exact grounded non-inferiority. The live selected
action remains untouched, PR58's legacy-control component remains unchanged,
and the two readout semantics are mutually exclusive in a manifest. Distinct
events and counters expose evaluations, grounded alternatives, interval
overlaps, abstentions, and shadow preferences. Eighty-four focused tests pass.
Fresh seed `109009` is preregistered for a clean mechanics smoke that requires
at least one grounded protected comparison but not a preference; see
`fdas-pr65-scalar-baseline-readout-smoke-preregistration.md`.

PR65 is mechanically accepted but fails its frozen grounded-comparison yield
gate. Clean seed `109009` ended genuinely at turn 152 with no failure, resume,
rejected action, event error, warning, or authority leak. All 82 unions had
only their scalar member, so there were no additions or alternatives. The
model nevertheless supplied 73 candidate-specific move estimates (47 full,
24 ETA, and two route); all later control groundings returned the generic
`control-grounded-transition-input-unavailable`, while nine fortify baselines
correctly abstained outside domain. The failed primary result is preserved.
Before a larger opportunity cohort, the strict grounding layer must expose the
exact predicate behind this PR59-complete/readout-unavailable mismatch so
opportunity and grounding yield are not confounded. See
`fdas-pr65-scalar-baseline-readout-smoke.md` and
`fdas-pr65-scalar-baseline-readout-smoke.json`.

PR66 prospectively separates the scalar-baseline grounding diagnostic without
changing a safety decision. PR58 retains its historical generic reason; PR65's
separate evaluator now identifies the exact bounded-validator, deficit-record,
actor, city, route, revision, ETA, or unit-field predicate before abstaining.
The model, union, eligibility, non-inferiority, action output, and authority
surface are unchanged. Fresh seed `109021` is preregistered to require parent
mechanical acceptance, candidate-specific prediction yield, at least one exact
failure, and zero generic failures; see
`fdas-pr66-scalar-baseline-grounding-diagnostic-preregistration.md`.

PR66 passes from clean commit `b2e518c` and identifies the exact mismatch.
Seed `109021` reached turn 161 cleanly. Fifty-six move controls failed the
bounded validator because every candidate carried
`protected-source-garrison` plus the already permitted
`uncompiled-action-effect`; two controls grounded, and eight fortify baselines
abstained outside the move domain. The former blocker is an exact proof that
moving the actor creates a source-city defense deficit and must not be
allowlisted. PR59 transition completeness described observed movement
mechanics, not source-release safety. The next correction must retain these
candidates for observation while excluding them from the decision-safe scalar
baseline and calibrated recall surface with explicit reasons. See
`fdas-pr66-scalar-baseline-grounding-diagnostic.md` and
`fdas-pr66-scalar-baseline-grounding-diagnostic.json`.

PR67 implements the required safety boundary before the candidate union.
Every original choice remains in the observational store, while a distinct
revision-bound event records exact blocker sets, bounded-validator status, and
support for each input. Only eligible operations reach scalar top-1 or
calibrated recall; `protected-source-garrison` remains excluded, and an empty
safe surface emits no union. Union events are causally bound to their filter,
and all filter/readout authority is false. Eighty-seven focused planner,
runtime, config, and audit tests pass. Fresh seed `109031` is preregistered to
require an observed source-garrison exclusion, a safe candidate-specific union,
and a fully grounded safe scalar control; see
`fdas-pr67-safe-filtered-scalar-readout-preregistration.md`.

PR67 is mechanically accepted but fails its safe-move and grounded-control
yield gates. Clean seed `109031` reached turn 161 with no failure, resume,
rejection, warning, or authority leak. Across 80 filters, all 122 move
candidates carried `protected-source-garrison` and were excluded; four safe
fortify candidates formed one-member unions and abstained outside the move
domain. Thus the filter fixed correctness but the game offered no safe
reinforcement control or candidate-specific safe union. Using the descriptive
one-of-three safe-control game rate across PR65–PR67, eight fresh games give
about 96.1% probability of at least one contributing game under that planning
assumption. The next gate is a prospectively fixed eight-game opportunity
cohort, not a seed retry. See
`fdas-pr67-safe-filtered-scalar-readout-smoke.md` and
`fdas-pr67-safe-filtered-scalar-readout-smoke.json`.

PR68 prospectively freezes that eight-game opportunity cohort without changing
the PR67 implementation. Fixed fresh seeds `109037, 109049, 109063, 109073,
109097, 109103, 109111, 109121` must all pass the full safety-filter audit.
The cohort must contain a calibrated union addition and at least one genuinely
grounded protected alternative comparison in at least one game; preference is
not required. Prior games cannot be pooled, and no seed can be replaced or
retried. This remains an outcome-free readout-yield gate with no ranking,
gameplay, score, or win-rate claim. See
`fdas-pr68-safe-filtered-scalar-readout-opportunity-preregistration.md`.

PR68 is preserved as a failed primary opportunity cohort from clean commit
`66d153f`. All eight games and the parent PR67 safety-filter audit pass. The
cohort admitted 390 safe candidates, grounded 50 scalar controls across five
games, generated 43 candidate-specific estimates, and recalled 27 calibrated
additions. It nevertheless produced zero grounded alternatives. Six additions
coincided with a grounded move control, and every one was rejected before
grounding by the aggregate `pair-scope-mismatch` predicate. Event inspection
shows the readout's disjoint-resource rule structurally rejects same-actor
substitute moves even when they are different actions for the same grounded
reinforcement decision. The next correction must expose each scope predicate
and permit only explicitly protected same-actor action substitution while
keeping every other shared resource fail-closed. See
`fdas-pr68-safe-filtered-scalar-readout-opportunity.md` and
`fdas-pr68-safe-filtered-scalar-readout-opportunity.json`.

PR69 versions only the scalar-baseline pair-scope diagnostic. Every predicate
that formerly produced aggregate `pair-scope-mismatch` now emits exact
duplicate-action, operation-type, target-ref, identical-resource-set, and
per-resource overlap reasons while retaining identical fail-closed eligibility.
Eight fresh seeds are sized from PR68's descriptive three-of-eight scope-event
rate and frozen before collection. The gate requires full parent safety-filter
acceptance, at least one exact overlap, no generic reason, and no malformed
reason; it does not relax scope or require a preference. See
`fdas-pr69-pair-scope-diagnostic-preregistration.md`.

PR69 is preserved as a failed primary diagnostic cohort from clean commit
`5b854f5`. All eight games and the parent safety-filter audit pass, and the
cohort generated four calibrated additions plus five grounded scalar controls.
They never coincided in one readout, so no pair-scope predicate was exercised:
zero exact reasons and zero resource overlaps were observed. The descriptive
PR68 three-of-eight opportunity rate therefore did not replicate in the next
eight games. No games will be appended. A separately labeled post-hoc
sensitivity may deterministically reconstruct PR68's six stored candidate
pairs, but it cannot change either primary result. See
`fdas-pr69-pair-scope-diagnostic.md` and
`fdas-pr69-pair-scope-diagnostic.json`.

PR70 specifies a deterministic, explicitly post-hoc sensitivity over PR68's
six aggregate scope rows. It hash-binds the original failed report, joins each
readout to its protected union and causal safety-filter parent, and reconstructs
ordinary unit resources using the committed actor-resource rule. This avoids
consuming more fresh seeds merely to reproduce a sparse diagnostic event. A
pass can identify the stored conjuncts and motivate a future contract, but it
cannot repair PR68 or PR69 or establish alternative value. See
`fdas-pr70-pr68-pair-scope-sensitivity-specification.md`.
