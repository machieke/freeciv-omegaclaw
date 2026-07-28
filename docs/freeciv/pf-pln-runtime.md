# PF-PLN runtime activation

Canonical phase acceptance and live gameplay activation are separate claims.
All phases 0-9 have deterministic acceptance evidence, but only phases with an
engine adapter may affect a live harness game. The versioned support declaration
is `pf_pln_runtime` in `profile/freeciv_agent.yaml`.

The current engine adapter is `grounded-impact-planner/1.25`. Its score-alignment
guard changes how the already-live phases 0, 1, 4, and 9 rank grounded
operations. It also exposes a bounded post-settlement-runway gate for
score-bearing founder production and carries that deadline through settlement
or exact ruleset population recovery for an existing founder. It does not
activate any component-only phase. Two separate turn-60 expansion claims are
supported: adapter 1.5's frozen three-to-four-city confirmation improved score
by `+2.66`, and adapter 1.17's frozen four-to-five-city confirmation improved
score by `+1.56`. They are not pooled or added into a direct
three-to-five-city claim. Adapter 1.6 and the later route/escort changes remain
post-confirmation correctness hardening except where the adapter-1.17
fifth-city cohort explicitly holds them constant.

Adapter 1.25 also adds opt-in, ruleset-derived strategic production routes to
the existing live multi-goal field. Authoritative score deficit and bounded
visible naval-threat memory route pressure toward modernization, fleet
readiness, coastal response, and industrial/research/commerce infrastructure.
The routes remain constrained by the server legal set, exact prerequisite
proofs, upkeep reserves, and remaining-horizon gates; they do not activate a
component-only phase or revise any existing score claim.
Adapter 1.7 additionally consumes an optional, packet-grounded
`settlement_site_eligible` fact on founder moves and prefers a directly
reachable valid site over continued frontier wandering. Unknown destinations
retain adapter-1.6 behavior, the move remains subject to all route and
execution gates, and an already advertised Found City action remains higher
priority. This is pending selected-seed engine mechanism validation and does
not revise the adapter-1.5 score claim.
Adapter 1.8 adds an opt-in settlement-retention boundary. A current legal
Found City action can be deferred until a grounded combat unit occupies the
same tile. The founder holds that exact site; only a non-required combat unit
may take a legal move that strictly reduces its distance to the founder.
Existing city-defender preservation, deadline recovery, legal-action
membership, and exact post-action verification remain in force. Deferral
snapshots, escort move attempts/successes, and escorted settlement
attempts/completions are exported independently.
The selected adapter-1.8 replay rejected its initial escort classifier:
Diplomat movement was admitted before explorer exclusion, while the sole real
defender remained protected and no settlement completed. Adapter 1.9 requires
escort actors to belong to the grounded combat set and turns an unescorted
legal site without spare combat capacity into a production-defense deficit.
A population-costing founder queue may be repurposed into a declared defender,
with exact production installation exposed independently.
The selected ten-pair generalization then rejected unconditional escort
co-location as an own-score optimization. Adapter 1.10 can require the same
escort only when an exact packet-visible opponent lies inside the configured
radius of the founder. Safe sites bypass the wait immediately; threatened
sites retain defender production, combat-only movement, and the existing
settlement-runway deadline. Threat deferrals and safe unescorted settlements
are separate metrics. This opt-in correction is pending engine mechanism
validation and does not revise the adapter-1.5 score claim.
The selected adapter-1.10 replay classified all three exposed settlements as
safe because the approaching rival disappeared before the exact founding
snapshot. Adapter 1.11 can retain an exact local threat observation for that
founder's route lifetime. The evidence is cleared when the founder settles,
recovers population, or disappears and is never transferred to another
actor. It requires an escort only while the founder remains inside the radius
of exact last-seen opponent geometry; otherwise a legal strictly
distance-increasing move can relocate the founder. A persisted contested route
may ground an empty-stock defender build when completed combat capacity has no
spare unit. This correction is also opt-in and pending engine mechanism
validation.
The adapter-1.11 mechanism replay passed every audit gate but did not activate:
no packet-visible opponent entered the three-tile founder-local radius. Adapter
1.12 targets the deterministic preparation gap exposed by the same trace.
When `expansion_final_settlement_escort_enabled` is true, a redundant founder
queue can retain same-kind unit shield carry-over for one early defender. That
defender follows only the newest founder assigned to the final expansion slot,
and co-location is required only for the settlement that completes the city
target. Earlier safe settlements retain immediate founding. Timely existing
defender queues suppress duplicate preparation. This correction is opt-in,
claim-ineligible, and pending engine mechanism validation. The adapter-1.12
selected replay installed the defender and improved own score by eight, but
the same-speed escort never caught the moving founder and no final settlement
was attempted. Adapter 1.13 holds only that assigned final founder while an
available spare combat unit closes the gap. Recovery and remembered-threat
avoidance still run first; normal founder routing resumes at co-location.
Rendezvous holds are exported separately, and the correction receives a
source-fresh selected replay before any generalization.
The adapter-1.13 ten-seed generalization improved mean own score by 1.9 but
exposed two founders held for 10 and 17 snapshots without one legal escort
move. Adapter 1.14 now requires the authoritative action set to contain an
exact distance-reducing move for a non-garrison combat unit before suppressing
the founder route. Otherwise the founder remains movable and a separate
no-progress snapshot counter records the bypass. The correction remains
opt-in through the parent final-settlement switch and is pending source-fresh
mechanism and generalization replays.
The adapter-1.14 exposed replay removed explicit holds but did not remove the
score harm: seven unprepared escort candidates still outranked founder
routing. Adapter 1.15 requires at least one authoritatively successful early
preparation installation before enabling final-route escort candidates,
rendezvous holds, or mandatory final co-location. The preparation projection
itself remains available so the mechanism can activate. Unprepared route
bypasses are exported separately.
The fresh 40-pair adapter-1.15 pilot then rejected that installation signal as
too broad. Every point of aggregate score loss occurred in preparation-active
games, and prepared games without a completed final escorted settlement lost
1.38 points on average. Adapter 1.16 admits final preparation only when a
same-kind redundant-founder switch retains its shields, completes immediately,
and occurs in a city that already has a grounded defender, making the delivered
unit spare rather than a new garrison. At most one confirmed preparation may
activate the route. Final-route pursuit, rendezvous holds, and mandatory
co-location additionally require exact visible or actor-scoped remembered
threat evidence. Unthreatened route bypasses are exported separately. This is
claim-ineligible development hardening; the frozen adapter-1.15 confirmatory
cohort remains prohibited.
The complete adapter-1.16 development replay exposed two zero-preparation
control-path defects. Adapter 1.17 makes a locally ineligible preparation
behaviorally inert, so it cannot suppress ordinary production. Accepted
terminal actions use a separately configured one-second authoritative refresh
barrier; if that barrier still expires, the loop records the deferred outcome
and ends same-turn impact planning rather than selecting another action from
the unchanged pre-action snapshot. The general 300 ms refresh remains
unchanged for non-terminal actions. This is correctness hardening and creates
no score or win-rate claim.
Adapter 1.19 adds three factual safety dimensions to the live multi-goal field:
city food reserve, net treasury plus turn-start upkeep reserve, and city-local
garrison coverage. Grounded operations include queue interruption, bounded
tax/science shifts and restoration, exact support rehoming or disbanding, and
replacement-garrison movement. A required city defender is excluded from every
offensive action. These are correctness and survival hardening changes; they do
not revise any frozen score or win-rate claim until a new paired engine cohort
is completed.

Adapter 1.21 added the missing stable-government initiation path. The proxy
projects every exact requirements-satisfied target, while the planner admits
only the configured preferred target and only when the declared horizon has at
least `government_minimum_remaining_turns` left. Its `governance` pressure goal
is ordinary during initiation, but becomes a safety goal after revolution so
food, treasury, and production work cannot strand the player in Anarchy. Exact
post-revolution intent outranks the configured preference, preserving the
destination already sent to the server. The live policy leaves
`preferred_government` empty: same-seed 480-turn Monarchy cohorts scored 205
and 187 versus the established 319 Despotism cohort, so transition initiation
is disabled while mandatory recovery from an already-started revolution
remains enabled.

Adapters 1.22-1.24 add founder-attrition bounds, treasury-release hysteresis,
restored packet-mood martial-law requirements, exact player-rate normalization,
and optional city-local happiness control. Both disorder recovery experiments
are disabled in live profiles. Global luxury reached 50-60%, drove science to
zero, and scored 205/214. `require_happy` CMA requests were packet-valid but
server-infeasible in the examined game: they were accepted without enabling the
governor or changing city state. Keeping both surfaces opt-in prevents an
unverified recovery mechanism from changing the established live policy.

The live harness explicitly enables
`expansion_settlement_deadline_recovery_enabled`. Its false setting is a
diagnostic ablation of existing-founder deadline handling; it does not
activate or disable any PF-PLN phase.
The completed 40-pair ablation activated recovery in 10 treatment games and
restored 28 population, while paired score remained neutral at -0.075
[-0.400, +0.250], exact `p=0.765625`. It validates the live lifecycle path
without creating a new score or win-rate claim.

## Current engine boundary

| Phase | Component | Declared support | Live enablement condition |
|---|---|---|---|
| 0 | executable semantics | engine-live | engine backend, scheduler capability, and `pressure_enabled` |
| 1 | goal regression planner | engine-live | engine backend, scheduler capability, and `pressure_enabled` |
| 2 | provenance and contradiction | component-only | Never enabled by a profile toggle |
| 3 | observation and simulation pressure | component-only | Never enabled by a profile toggle |
| 4 | conductance learning | engine-live | Phase 0/1 conditions plus `pressure_learning_enabled` |
| 5 | lifecycle clones | component-only | Never enabled by a profile toggle |
| 6 | induction and analogy | component-only | Never enabled by a profile toggle |
| 7 | LLM gateway | component-only | Never enabled by a profile toggle |
| 8 | differentiable execution | component-only | Never enabled by a profile toggle |
| 9 | multi-goal field | engine-live | engine backend, scheduler capability, and `pressure_enabled` |

`component-only` means the implementation and canonical benchmark exist, but
the engine-live loop has no adapter for that component. In particular, the
existing sequential `OpponentMemory` harness track is not PF-PLN Phase 6
contextual induction, and the live `ConstrainedProposer` path is not the
Phase 7 pressure-gated LLM gateway.

The engine loop does apply the narrower
`canonical-singleton-bypass-v1` selection policy. When the mechanically
generated constrained catalog contains exactly one selectable goal, the host
constructs that proposal, sends it through the same strict proposal parser and
symbol-catalog gates, emits `goal_selection`, and does not invoke the model.
An active research target is that single necessary goal while the exact proxy
legal set advertises no new research choice; reselecting between unrelated
technologies cannot produce an engine action on such a turn.
After the canonical proposal passes the strict parser and symbol catalog, a
verification event records that the engine is already executing it. Goal
grading, dependency expansion, and scheduling are deferred until a new
research action is actually advertised. The immutable schema validator and
symbol-catalog parser are constructed once with the cognitive stack and reused;
every proposal is still parsed and catalog-checked.
The crisp and numeric planning views are constructed only after this
continuation gate, so an unexecutable research plan cannot allocate scheduler
inputs that the turn will not consume.
Two or more candidates still use `llm_proposal`. This necessity optimization
does not inspect pressure, admit an expansion request, or activate the Phase 7
gateway, so Phase 7 remains correctly declared `component-only`.

Changing a component-only row to `engine-live` fails configuration validation.
Enabling it requires an actual engine adapter, manifest and event integration,
new fail-closed tests, and an updated canonical declaration.

## Per-game derivation

The harness derives `manifest.json` → `pf_pln_runtime` from four inputs:

1. the checked support declaration;
2. the selected backend;
3. the condition capability matrix; and
4. the effective impact policy after paired-arm overrides.

The derived report contains each phase's support, enabled state, and reason,
plus a structural activation hash. It is part of `manifest_identity`, so a run
cannot resume across an activation change. The engine validates the report
again before opening the live connection.

The pressure-ablation baseline therefore records no enabled PF-PLN phases. Its
treatment records phases 0, 1, 4, and 9. The representative backend records no
live phases because it tests orchestration and statistics rather than engine
execution.

## Event evidence

Every harness event stream emits ten causal `metric_sample` declarations at
turn 0:

- `name=pf_pln_phase_enabled`;
- `value=1` only for an enabled phase;
- `declaration=pf_pln_runtime_activation`; and
- labels for phase, component, support, reason, backend, condition, and track.

These events are derived from the same checked report as the manifest. They let
replay and audit consumers distinguish accepted-but-unwired components from
components that could influence a particular game.

Run the complete boundary audit with:

```bash
python3 scripts/freeciv/audit_pf_pln.py --workers 4
```

The audit requires the default engine-live treatment to enable exactly phases
0, 1, 4, and 9, requires the pressure-off and representative configurations to
enable none, and requires every component-only phase to remain disabled.
