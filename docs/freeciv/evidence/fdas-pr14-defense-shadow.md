# FDAS PR 14: defense-focused shadow activation

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Status: declared `shadow-live`; policy authority disabled
Machine-readable engine evidence: `fdas-pr14-defense-shadow-engine.json`

## Acceptance boundary

PR 14 does not require a new defense model. The Phase 6 increments already
implement the required unit and region projectors, exact native movement and
defense groundings, persistent reinforcement/replacement operation
reconciliation, current requirements/resource claims, and focused region
activation. Their detailed fixtures and limitations remain recorded in the
`fdas-phase6-*.md` evidence series.

The remaining integration gap was an activation pair whose declared boundary
matches that realized code. This increment adds:

- `profile/dependent_atomspace_defense_shadow.yaml`, which enables only the
  ruleset, city/economy, unit, bounded region, and durable operation
  projections needed by the defense slice;
- `profile/fdas_manifest_defense_shadow.json`, which promotes only the
  exercised dependency, projection, reconciliation, pressure, causal-event,
  and rollback capabilities to `shadow-live`;
- an explicit 5% deterministic cold-verification sample at turn-boundary
  readout;
- selected-support explanation capture and shadow divergence events;
- a configuration fixture proving that all policy, learning, and domain
  authority flags remain false.

The profile deliberately leaves route corridors, settlement, recovery,
transport, combat, opponent belief, episodes, contextual conductance, generic
rules, and every authority slice outside this activation. This keeps PR 14
separate from PR 15 defense authority and episode rollout.

## Acceptance criteria

The defense shadow declaration is acceptable when:

1. the config and manifest validate as an exact schema pair;
2. the runtime contains the city/economy, unit-defense, region, and operation
   projectors and no unrelated focused-domain projector;
3. engine shadow readouts preserve the legacy action trace exactly;
4. sampled cold revisions are equivalent;
5. unit/region/operation scopes and events remain within declared budgets;
6. no FDAS authority event or FDAS-authorized action occurs;
7. rollback to the checked default profile remains configuration-only.

## Fresh paired engine confirmation

The activation was committed before execution, then compared with the checked
legacy-control profile on the same pinned seed and source commit
`f00a13cd4c4ec3d498088780b022263f86fc095e`:

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_shadow.json \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr14-defense-shadow-live-v1 \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume

FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest.json \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr14-defense-control-live-v1 \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume

python3 scripts/freeciv/audit_fdas_engine_shadow_cohort.py \
  --control artifacts/freeciv/fdas-pr14-defense-control-live-v1 \
  --shadow artifacts/freeciv/fdas-pr14-defense-shadow-live-v1 \
  --minimum-pairs 1 \
  --output docs/freeciv/evidence/fdas-pr14-defense-shadow-engine.json
```

Results on seed `104729`:

| Measure | Result |
|---|---:|
| Paired arms completed / audit failures | 2 / 0 |
| Exact ordered action/result matches | 52 / 52 |
| Exact behavioral completion match | yes |
| Shadow decisions / explained legacy candidates | 30 / 21 |
| Missing legacy / extra FDAS candidates | 0 / 0 |
| Authority violations / eligible actions / authority events | 0 / 0 / 0 |
| Sampled cold verifications / failures | 1 / 0 |
| Maximum atoms / scopes / supports | 609 / 7 / 424 |
| FDAS contribution p50 / p95 | 75.80 / 127.98 ms |
| Full controller p50 / p95 | 25.31 / 443.21 ms |

Both declared latency gates passed: FDAS p95 remained at or below 150 ms and
full-controller p95 remained below 500 ms. The run manifest recorded clean
source, the pinned commit above, and implementation hash
`d560ee98c1c225f23c00f1f217666fdedb9ca8c533a32c46b3dad4d350a21277`.
The deterministic audit structural hash is
`986a3081c99b799e685d39e45ccb8c41b5bd8cf30998f1b92a055c62d21ba9d6`.

This one-pair cohort is a mechanism and behavior-preservation confirmation,
not an outcome experiment. It is sufficient for the narrowly declared PR 14
shadow activation because the checked action path is unchanged; it is not
large enough for a gameplay efficacy claim.

The focused configuration/runtime/unit/region/operation/lifecycle suite passed
81 tests. The complete FDAS suite passed 205 tests after this activation was
added.

## Claim boundary

`shadow-live` means the defense substrate may be constructed, queried,
compared, and explained during an engine game. It does not reserve a unit,
change a planner winner, submit an action, update conductance, attribute an
episode, or support a score/win-rate claim.
