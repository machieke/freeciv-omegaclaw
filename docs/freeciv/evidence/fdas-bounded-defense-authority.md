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
`shadow-live`; episodes remain component-only. Removing the overrides returns
to the default legacy path, and a one-sided or partially promoted declaration
fails validation.

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
| Authority readout p50 / p95 | 0.532 / 18.145 ms |

All twelve gates passed in two deterministic runs. Every authorization was an
exact legacy-selected `unit_fortify`, received the exact actor resource and
complete packets, and committed only plan materialization. Every commit record
retained `execution_authority: false`. The 25 fallbacks were all legacy winners
outside the city-defense category.

The report hash is
`101ed7730fb1ea3786c2813f23b2ccdf3fea1a3e5683c03b592f4f5c5b431099`;
its implementation digest is
`0d4c0029153728c029a9a10b6301a4da51586fb731afbe5fc2ffe0d8f1568e33`.

## Episode boundary

The authorized operation is now compatible with the existing defense episode
recorder. A deterministic acceptance fixture proves three separate states:

1. server acceptance records no effect and no goal relief;
2. an authoritative after-snapshot showing `fortifying` records the exact
   `actor-fortified` effect;
3. only that after-state records realized relief for the bound fortification
   goal.

The episode recorder also normalizes generic FDAS unit participants to the
same `unit:<id>` identity used by durable defense operations. This is an exact
replay/component bridge; persistence and engine event wiring remain required
before `episode_attribution` can be promoted from `component-only`.

The focused authority/config/runtime/unit/replay suite passed 82 tests before
the episode link was added. The complete FDAS suite passed 211 tests with the
final support and episode hardening.

## Claim boundary

This evidence supports one default-off, non-divergent fortification authority
slice. It does not support reinforcement movement authority, policy winner
changes, online conductance updates, a score/win-rate claim, or promotion of
the default manifest. Fresh clean-source engine confirmation is still
required before PR 15 authority is considered live-accepted.
