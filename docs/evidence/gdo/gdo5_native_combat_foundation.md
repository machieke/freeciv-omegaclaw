# GDO-5 native combat and atomic-operation foundation

Status: first vertical subset and captured atomic replay verified in shadow
mode; GDO-5 exit gate remains closed

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

## Question

Can GDO-5 begin from server-authoritative combat probabilities and
identity-aware atomic reservations without reconstructing hidden combat rules
or changing live policy?

This increment implements the narrow `attack_then_conditional_attack` subset.
It does not claim the complete GDO-5 operation catalogue or a gameplay-score
improvement.

## Grounded input

Upstream proxy patch
`scripts/freeciv/upstream/0016-pln-native-combat-probabilities.patch`
uses Freeciv's background action-probability request and response packets. It
projects bounded results for the stable protocol action IDs for capture,
attack, suicide attack, conquer-city, and bombard.

Patch SHA-256:

```text
659627003f09f980692021bd27eff1620e805dbadd2e9b42faedc98329bcc59c
```

Ordered 16-patch series SHA-256:

```text
56f9ae36e3e985bc36c04600df294436498854321c2390d7e281b7a3071cd6ca
```

Every result is scoped to the requesting player, turn, actor revision, target
tile, and complete visible target-stack revision. Actor revisions require
movement state. Defender revisions retain short-packet omissions that cannot
change defender identity, while an incomplete combat-relevant defender
identity causes the query to abstain. A selected nonzero target must be in the
recorded visible stack. The local DTO repeats these checks and fails closed on
stale or malformed evidence. When the packet uses target ID `0` as a
tile-query sentinel, the assembler can resolve it only from a one-unit exact
visible stack. It abstains on an ambiguous stack.

The transition model labels accepted rows
`grounded_combat_transition/2.0`. It preserves native lower and upper bounds
and leaves unsupported outcome mass uncertain.

## Atomic shadow subset

`CombatOperationAssembler` forms a two-actor operation only when both own
actors have current native attack support for the same visible target. A
bounded interval with zero upper probability is not treated as attack support.
The operation has:

- deterministic operation and step identities;
- an AND `RequirementSet` for both actors and both native estimates;
- exclusive current-turn actor claims;
- current-turn movement-point claims;
- a target-tile occupancy claim;
- a primary attack followed by a second attack conditioned on the target
  surviving the first step.

The second step is not multiplied as an independent event. Its post-first-step
probability is deliberately unresolved, so the joint interval retains that
uncertainty. The bounded exact scheduler selects complete operations or none;
it cannot reserve a partial participant set or duplicate a target occupancy
claim.

The entire path is shadow-only. Both operation events and the runtime feature
manifest state `policy_authority=false`; existing action selection is
unchanged.

## Fresh engine pilot

The retained command was:

```text
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN=test-token-fc3d-001 \
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_SERVER_CONTAINER=fciv-net \
OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/gdo5-native-combat-pilot-v3 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6100 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume
```

Seed `4543804-00` completed 160 turns with zero infrastructure failures and
zero rejected engine actions. Raw event SHA-256:

```text
b90d2241a76e6caa87ade3b4841ea5f5adc53194eb4056e668855b0558cebd51
```

| Diagnostic | Result |
| --- | ---: |
| State snapshots containing native combat rows | 38 |
| Distinct combat-bearing state hashes | 35 |
| Accepted native actor/target rows | 86 |
| Positive native attack observations | 4 |
| Atomic two-actor candidates | 0 |
| Atomic selections | 0 |
| Engine rejected actions | 0 |

The positive observations involved only one eligible own actor at a time.
Consequently, the two-participant assembler correctly abstained. This is
useful fail-closed live evidence, but it is not live evidence of a completed
atomic attack. Synthetic and captured-state tests exercise supported
two-actor assembly, exact reservation, target conflicts, conditional
probability bounds, missing participants, target disappearance, and step
revalidation.

The observed score was 167 versus 333 at the fixed horizon. Because this is a
single shadow-policy mechanism pilot with no paired comparator, that value is
not a score or win-rate claim.

## Verification

- Clean pinned checkout: all 16 upstream patches applied and `git diff
  --check` passed.
- Proxy authoritative-state tests: 57 passed.
- FreeCiv repository suite: 938 passed; after the final sentinel hardening,
  the 140-test affected integration selection passed.
- Observability UI: typecheck, fixture validation, event-only boundary,
  41 tests, and production build passed.
- Post-fix browser proof:
  `apps/freeciv-observability/proofshot-artifacts/2026-07-30_18-33-46_post-fix-verification-that-native-combat/`;
  the real trace shows defender `unit:214` with the native 99.0–99.5% interval
  and reports zero console or server errors.
- Release audit: all checks passed, including the pinned external contract
  and generated event types.

The repository-wide `Autotests` collector remains independently blocked by
the existing Slack/Telegram mock import collision. The complete
`Autotests/test_freeciv*.py` selection is green. The proxy-wide collector is
also independently incompatible with the installed Tornado/Python test
combination in `test_state_extractor.py`; the changed authoritative-state
suite is green.

## Gate decision and next slices

GDO-5 is not complete and receives no live authority. Remaining work includes:

1. bombard-then-attack and weaken-then-capture role enumeration;
2. escort-to-staging, attack-then-occupy, and attack-then-hold;
3. sacrificial interception for a terminal goal;
4. live step execution with re-estimation after every outcome;
5. abandonment, repair, completion, and claim-release lifecycle rules;
6. a fresh disjoint pilot with actual execution and directional
   mechanism benefit.

The captured deterministic joint-combat corpus and its atomic-versus-
independent diagnostic are now complete; see
`docs/evidence/gdo/gdo5_atomic_combat_replay.md`. On five exact engine-backed
snapshots, uncoordinated readout duplicated a target in 5/5 cases and atomic
scheduling did so in 0/5 cases. This is a shadow mechanism result, not a score
claim. The next implementation slice is step-by-step operation re-estimation
and terminal lifecycle accounting before any live authority is considered.
