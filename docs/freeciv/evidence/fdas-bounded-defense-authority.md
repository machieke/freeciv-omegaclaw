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
to `bounded-authority`. The live authority profile materializes only unit,
operation, and episode domain projectors; unused city/economy and region views
remain available as substrate capabilities but are not paid for on every
action refresh. The `authority-domain-before-readout` policy materializes a
fresh rich revision only before a legacy-selected defense winner and while a
causal outcome episode is pending; turn boundaries remain current, and every
unrelated winner stays on the exact legacy execution path. Its explicit
`legacy_compatibility: false` switch also omits
the duplicate flat compatibility atoms; every default, shadow, city-authority,
and rollback profile retains that facade. With that switch off, snapshot
preparation is bounded to the union of access-audited projector dependency
roots, so unrelated map, research, economy, and belief fields are not
canonicalized for this defense-only slice. Support provenance remains in each
immutable revision while
redundant per-support event expansion is disabled. Episode attribution and
contextual control learning are `shadow-live`, while contextual conductance
authority remains disabled. Removing the overrides returns to the default
legacy path, and a one-sided or partially promoted declaration fails
validation.

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
| Authority readout p50 / p95 | 0.605 / 2.292 ms |

All twelve gates passed in two deterministic runs. Every authorization was an
exact legacy-selected `unit_fortify`, received the exact actor resource and
complete packets, and committed only plan materialization. Every commit record
retained `execution_authority: false`. The 25 fallbacks were all legacy winners
outside the city-defense category.

The report hash is
`e4cce97983881eef20a661fde44a4a89853c9a07644f729e1397af40b1015253`;
its implementation digest is
`f8c0da8b4c17f2c5316248204b445cb47935c7016b5a383a1303d4f23951bf87`.

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
now confirms that boundary with five independent accepted fortifications.

The complete explicit FDAS suite passes 219 tests with the live episode and
read-only learning bridge implementation; the replay reports were regenerated
against the exact current source.

## Fresh engine-backed safety confirmation

The authority, episode, dependency-bounded preparation, legacy compatibility
switch, and domain-scoped refresh implementations were committed before two
fresh engine runs. Both used clean source commit
`c101bf9c50df2d12891d8a7a933633d71bb0842a`.

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_authority.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_authority.json \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-defense-domain-refresh-live-30-v1 \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume

python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --out artifacts/freeciv/fdas-defense-domain-refresh-live-160-v1 \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume

python3 scripts/freeciv/audit_fdas_authority_live.py \
  --game-dir artifacts/freeciv/fdas-defense-domain-refresh-live-160-v1/games/main/e_full_loop/4543804-00 \
  --output docs/freeciv/evidence/fdas-bounded-defense-authority-engine-live.json
```

### Ordinary 30-turn latency cohort

| Measure | Result |
|---|---:|
| Horizon / completed games / run failures | 30 / 1 / 0 |
| Domain authority opportunities / authorized / fallback | 2 / 2 / 0 |
| Engine actions / results / rejections | 52 / 52 / 0 |
| Complete episode chains / conductance samples | 2 / 2 |
| Deterministic live-audit gates | 23 / 23 |
| FDAS projection p50 / p95 | 22.40 / 27.00 ms |
| FDAS shadow readout p50 / p95 | 2.12 / 2.28 ms |
| Full-loop p50 / p95 | 26.76 / 447.32 ms |
| Event count | 1,814 |

This cohort passes both proposed ordinary gates: FDAS is below 150 ms p95 and
the complete existing controller is below 500 ms p95. Its deterministic audit
is `fdas-bounded-defense-authority-engine-live-30.json`, with structural hash
`fdb7b5527e2a14278d8aef719ebc5aedf988e2ae5aae03bd52bde6bab2f774d5`
and file SHA-256
`03f3b052fda6cbcdc2941687882e65387470adf0846e6b0c1492ea36d8432859`.

### 160-turn late-game stress cohort

| Measure | Result |
|---|---:|
| Horizon / completed games / run failures | 160 / 1 / 0 |
| Domain authority opportunities / authorized / fallback | 6 / 5 / 1 |
| Authorization turns | 1, 24, 32, 38, 47 |
| Engine actions / results / rejections | 367 / 367 / 0 |
| Complete episode chains / conductance samples | 5 / 5 |
| Sampled cold verifications / mismatches | 8 / 0 |
| Deterministic live-audit gates | 23 / 23 |
| FDAS projection p50 / p95 | 57.85 / 101.16 ms |
| FDAS shadow readout p50 / p95 | 44.47 / 82.64 ms |
| Full-loop p50 / p95 | 264.02 / 1,348.97 ms |
| Event count | 31,009 |

Every authorized readout ran all eight declared authority checks and all seven
commit checks. Each exact actor-resource schedule and action/CPU packet
schedule was conserved and non-authoritative; every commit retained
`execution_authority: false`; and each authority event had exactly one causal
`action_sent` followed by an accepted `action_result`. The one evaluated
in-domain fallback retained the legacy winner; out-of-domain winners bypassed
rich materialization by construction and remained under the existing exact
execution gate.

The deterministic audit structural hash is
`65bfde91ffcfc8cf033ff348106af2d3f0c1b77150511e8acfd4aea9f3a5a2a0`
and its file SHA-256 is
`64a6091fb9115b7a984e9e9220bc0078281e1fcf9e3bb4eebeb8ec2035e35d46`.
The run manifest records implementation SHA-256
`1577ff0a673d4a9b28e06b6986f86c48853babe3caed180ccaa5e1818e048b18`.

The stress cohort keeps FDAS itself below 150 ms p95, but the complete
late-game controller remains above 500 ms p95. This is therefore an ordinary
bounded-slice latency promotion, not evidence that all late-game controller
workloads satisfy the production envelope.

## Claim boundary

This evidence supports one default-off, non-divergent fortification authority
slice and fresh clean-source execution of that slice. It does not support
reinforcement movement authority, policy winner changes, conductance-based
policy changes, a score/win-rate claim, a universal late-game latency claim, or
promotion of the default manifest.
