# GDO-5 combat operation lifecycle

Status: shadow lifecycle mechanism gate passed; live execution gate remains
closed

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

## Question and claim boundary

Can a selected atomic combat operation preserve explicit progress, re-estimate
its next step from a newer authoritative snapshot, reserve only the current
step, and release every stale or terminal claim?

The synthetic mechanism gate passes, and a fresh 160-turn engine trace
validates reservation, refresh, expiry, and release behavior on genuine joint
combat opportunities. The frozen scalar policy did not independently execute
any reserved attack, so this increment makes no target-neutralization,
material-loss, score, or win-rate claim.

## Implementation

`CombatOperationLifecycle` owns one operation store and one identity-resource
ledger per game. It remains shadow-only and has no action submission method.
An operation can enter the lifecycle only after the existing exact scheduler
selects its complete two-actor request.

For each real action submitted by the frozen policy, the observer:

1. matches canonical action bytes against the currently reserved step;
2. revalidates current legality and native combat support;
3. attributes an accepted or rejected result without changing the policy;
4. releases the previous whole-operation reservation;
5. waits for a newer authoritative snapshot;
6. resolves target neutralization, participant loss, expiry, or no effect;
7. if the target survives, re-estimates the next step from current native
   probabilities and legal actions;
8. reserves exactly the next actor, its movement point, one target slot, and
   one action-budget unit.

The follow-up request therefore has four claims and an action-budget quantity
of one. It never reuses the first snapshot's probability interval. A blocked
step releases its claims and may return through the explicit
`blocked -> reservable -> reserved` repair path. Terminal and externally
satisfied operations release any still-active claims. Operation-store
transitions now permit completion from pre-active states because another
actor can satisfy the target before a reserved step executes.

## Synthetic lifecycle diagnostic

The retained command is:

```bash
python3 scripts/run_gdo_combat_lifecycle_replay.py \
  --corpus benchmarks/gdo/combat_operation_scenarios_v1.json \
  --iterations 100 \
  --output benchmarks/gdo/gdo5_combat_operation_lifecycle_diagnostic.json
```

The report hash is:

```text
528bd40137ef55c3b4ad0cc58564b4f0a69786ba0bf4279099fc17c32defb3af
```

Nine labeled flows cover:

- neutralization by the first step;
- neutralization by the follow-up;
- both attacks resolving while the target survives;
- blocked-step repair;
- required-participant removal;
- engine action rejection;
- uncommitted expiry;
- external neutralization before commit;
- unavailable follow-up movement capacity.

All declared gates pass over 100 iterations. Every final or attributable
blocked state has zero active claims. A target surviving both accepted attacks
is classified as `failed` with no effect, not as successful completion.
Controller-inclusive lifecycle replay over 900 samples was 1.14 ms mean,
1.51 ms p95, and 10.08 ms maximum. This corpus is explicitly synthetic and
does not support an outcome claim.

## Fresh engine-backed pilot

The retained run uses the known joint-opportunity seed:

```bash
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN=test-token-fc3d-001 \
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_SERVER_CONTAINER=fciv-net \
OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/gdo5-combat-lifecycle-pilot-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6100 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume
```

For this run only, seed `104743` was moved to the front of the unchanged
profile seed list; the checked-in profile order was restored immediately
after launch.

The game completed 160 turns with zero experiment failures, zero
infrastructure failures, and zero rejected engine actions. The validated
7,521-event trace has SHA-256:

```text
77473a0f410061d7afb3f53e9048f2a590c03fe2048b186f3300a1c92ca8ac49
```

| Diagnostic | Result |
| --- | ---: |
| Atomic operation proposals | 15 |
| Selected shadow observations | 5 |
| Unique complete operations reserved | 4 |
| Same-turn whole-operation revalidations | 1 |
| Operations activated by a matching policy action | 0 |
| Operations expired uncommitted | 4 |
| Claims released on expiry | 24 |
| Claims released on snapshot refresh | 6 |
| Remaining active combat claims | 0 |

The five selected observations include two exact snapshots of the same
turn-72 operation, hence four stable operation identities. The refresh
released all six old claims and replaced them from the newer exact snapshot;
the next turn expired the still-uncommitted operation and released its six
current claims. Across the trace, every unique reservation reached an
attributable terminal state and no resource remained held.

The frozen policy submitted no `unit_attack` action during the run. Therefore
zero activations are expected and are not a lifecycle failure. They expose
the next research boundary: the atomic candidate can be assembled and safely
tracked, but the supported scalar readout does not choose it. The observed
score was 127 versus 244 at turn 160. This is a single shadow-only diagnostic,
not a paired outcome comparison.

## Verification and decision

- 33 focused combat, lifecycle, operation-store, replay, and release tests
  pass.
- 119 combat/operation/resource/harness integration tests pass.
- The emitted lifecycle and release event sequence validates against the
  versioned event schema.
- The fresh engine trace validates with zero event errors.
- New behavior remains behind the existing default-off combat-operation
  dependency gate and declares no policy authority.

This closes GDO-5 tasks for post-step re-estimation, explicit completion,
blocking, repair, abandonment, expiry, and claim release at the shadow
mechanism level. It does not close the GDO-5 live pilot gate. The subsequent
candidate-readout correction is documented in
`docs/evidence/gdo/gdo5_combat_candidate_readout.md`; actual step execution is
still required before evaluating target neutralization, friendly loss,
abandoned partial attacks, or score.
