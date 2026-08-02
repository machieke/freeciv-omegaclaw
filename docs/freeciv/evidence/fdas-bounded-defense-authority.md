# FDAS bounded defense-fortification authority

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Machine-readable replay evidence:
`fdas-bounded-defense-authority-replay.json`

## Realized boundary

This is the first PR 15 authority slice. It is deliberately restricted to an
exact `unit_fortify` action already selected by the legacy city-defense
planner. The frozen corpus showed 13 such legacy winners and no selected
reinforcement move, so fortification provides an evidence-backed one-step
boundary without inventing a synthetic-only live opportunity.

An action is authorized only when all of the following hold:

1. the global authority gate and only the `city_defense` domain flag are on;
2. the legacy winner category is exactly `city_defense`;
3. the shadow evaluation and dependent revision match the current snapshot;
4. exactly one FDAS candidate binds the byte-identical current legal action to
   a `unit-fortification-opportunity` goal;
5. the action has only `action_type=unit_fortify` and an integer actor ID;
6. the actor is currently present in the named city and is not already
   fortifying or fortified;
7. the exact opportunity atom has dependency-backed support from the current
   unit, city, persistent-defender grounding, and legal-action identity;
8. the only resource identity is the current unit actor;
9. a fresh one-candidate pressure readout selects the route;
10. exact actor-resource scheduling and whole action/CPU packets commit
    together;
11. `FDASCommitValidator` revalidates snapshot, legal-action digest, revision,
    supports, candidate identity, causal firewall, and domain authority;
12. the existing `ExecutionGate` remains downstream and solely responsible for
    submission.

FDAS cannot select a different action in this slice. A missing category,
opportunity, current identity, exact action, resource, pressure selection, or
commit check produces a named fallback and leaves the legacy path unchanged.

## Activation and rollback

The checked defaults remain non-authoritative. Activation requires both:

- `profile/dependent_atomspace_defense_authority.yaml`;
- `profile/fdas_manifest_defense_authority.json`.

The manifest promotes only the unit, operation, defense requirement,
pressure, resource/packet, and exact-commit capabilities needed by this slice
to `bounded-authority`. Region and the remaining defense substrate stay
`shadow-live`. Episode attribution and contextual control learning are also
`shadow-live`, while contextual conductance authority remains disabled.
Removing the overrides returns to the default legacy path, and a one-sided or
partially promoted declaration fails validation.

## Captured replay

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
python3 scripts/freeciv/run_fdas_bounded_authority_replay.py \
  --authority-domain city-defense \
  --config profile/dependent_atomspace_defense_authority.yaml \
  --manifest profile/fdas_manifest_defense_authority.json \
  --output docs/freeciv/evidence/fdas-bounded-defense-authority-replay.json
```

| Measure | Result |
|---|---:|
| Unique captures / replayable captures | 47 / 38 |
| Explicit historical data gaps | 9 |
| Authorized exact fortifications | 13 |
| Explicit fallbacks | 25 |
| Policy winner changes | 0 |
| Replay failures | 0 |
| Authority readout p50 / p95 | 0.552 / 18.695 ms |

All twelve gates passed in two deterministic runs. Every authorization was an
exact legacy-selected `unit_fortify`, received the exact actor resource and
complete packets, and committed only plan materialization. Every commit record
retained `execution_authority: false`. The 25 fallbacks were all legacy winners
outside the city-defense category.

The report hash is
`6941b95de2ddd9b346b40a774c0a7c265e1acb9befec8f64a11a7b6d0e7c0a41`;
its implementation digest is
`e31be2a2b6f74fcb5384013eb935cf3fbecde4d980c1dfb1068905e82c035e5f`.

## Episode boundary

The authorized operation is now wired to a durable compact defense episode
store. A deterministic acceptance fixture proves three separate states:

1. server acceptance records no effect and no goal relief;
2. an authoritative after-snapshot showing `fortifying` records the exact
   `actor-fortified` effect;
3. only that after-state records realized relief for the bound fortification
   goal.

The engine opens an episode only after server acceptance, persists it with an
atomic replacement, projects it into an episode scope, and observes subsequent
revision-current snapshots. Terminal attributable outcomes create a
contextual conductance sample in an isolated control store. That sample is
explicitly read-only: it has no policy authority and cannot mutate truth.
Prediction identities are reconstructable from durable episode fields so a
retry can rebuild the same isolated control state. Fresh engine confirmation
of this wiring is still required before it becomes an accepted live claim.

The complete explicit FDAS suite passes 213 tests with the live episode and
read-only learning bridge implementation; the replay reports were regenerated
against the exact current source.

## Fresh engine-backed safety confirmation

The authority implementation and incremental-projection repair were committed
before a fresh 160-turn run on pinned seed `4543804`. The run used clean source
commit `f37b8aa821c1287550abb36203abc5c1df905596`:

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_authority.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_authority.json \
python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --out artifacts/freeciv/fdas-defense-authority-live-160-v2 \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume

python3 scripts/freeciv/audit_fdas_authority_live.py \
  --game-dir artifacts/freeciv/fdas-defense-authority-live-160-v2/games/main/e_full_loop/4543804-00 \
  --output docs/freeciv/evidence/fdas-bounded-defense-authority-engine-live.json
```

| Measure | Result |
|---|---:|
| Horizon / completed games / run failures | 160 / 1 / 0 |
| Authority opportunities | 364 |
| Authorized exact fortifications | 5 |
| Authorization turns | 1, 24, 32, 38, 47 |
| Explicit fallbacks | 359 |
| Engine actions / results / rejections | 367 / 367 / 0 |
| Sampled cold verifications / mismatches | 8 / 0 |
| Deterministic live-audit gates | 17 / 17 |
| FDAS projection p50 / p95 | 195.57 / 284.31 ms |
| FDAS shadow readout p50 / p95 | 48.03 / 85.57 ms |
| Full-loop p50 / p95 | 503.86 / 3233.09 ms |

Every authorized readout ran all eight declared authority checks and all seven
commit checks. Each exact actor-resource schedule and action/CPU packet
schedule was conserved and non-authoritative; every commit retained
`execution_authority: false`; and each authority event had exactly one causal
`action_sent` followed by an accepted `action_result`. Fallbacks were fully
classified: 199 winners outside city defense, 159 snapshots without a selected
candidate, and one winner without a unique fortification route.

The deterministic audit structural hash is
`86f9ee062de1442d591509a66b86cf2333c917da32956e9b7bd784a2c25419af`
and its file SHA-256 is
`62f943a968b3395f58d55cd42fe0f884c9edacd6d446ebe658bf783bd36b70db`.
The run manifest records implementation SHA-256
`84966631e538be147617a8ef6f23427b74127ae24d38ce0969bd8d3e0f942faf`.

The run also exposed and then confirmed a corrected incremental-projection
invariant. `terrain-kind` previously hashed an undeclared whole-tile witness
even though its support depended only on exact terrain. A sampled cold build
therefore disagreed when owner/resource/worked state changed without a terrain
change. The witness is now restricted to tile and terrain, differential
verification reports bounded atom-level diagnostics, and a separate unit
grounding fix prevents fortification support from referring to the final unit
visited by the projector. The complete FDAS suite now passes 212 tests.

This is an engine-backed causal and safety confirmation, not a production
latency promotion. The late-game every-snapshot profile exceeded the proposed
150 ms FDAS and 500 ms full-controller p95 targets. Those measurements require
optimization and a clean paired confirmation before the profile can be called
production-safe.

## Claim boundary

This evidence supports one default-off, non-divergent fortification authority
slice and fresh clean-source execution of that slice. It does not support
reinforcement movement authority, policy winner changes, conductance-based
policy changes, a score/win-rate claim, a production-latency claim, acceptance
of the newly wired live episodes before fresh confirmation, or promotion of
the default manifest.
