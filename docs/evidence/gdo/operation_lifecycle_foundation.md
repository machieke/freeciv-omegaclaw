# Grounded operation lifecycle foundation

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

Authority: disabled by default; city-defence integration remains shadow-only

## Result

This checkpoint implements the operation-contract portion of the grounded
plan without giving operation assignments policy authority:

- immutable `OperationParticipant`, `OperationStep`, and `OperationSpec`
  contracts;
- stable operation identity material that excludes volatile utility/pressure;
- explicit proposed, reservable, reserved, active, blocked, suspended, and
  terminal states;
- a guarded transition graph with mandatory blocked/terminal reason codes;
- per-step attempt limits and one-step-at-a-time advancement;
- deterministic expiry after, not at, the declared deadline;
- versioned store serialization with structural digests;
- atomic durable replacement on save;
- restart loading that preserves active step/attempt progress;
- fail-closed quarantine for corrupt, unknown-schema, digest-mismatched, or
  wrong-game stores without rewriting the source record;
- deterministic conversion of city-defence domain edges into participant,
  requirement, step, target, deadline, and completion-predicate contracts;
- a default-off `pressure_operation_lifecycle_enabled` runtime flag.

Startup permits operation lifecycle only with:

- scalar PF-v2;
- grounded domain estimates;
- packet and identity-resource scheduling;
- exact commit revalidation.

City-defence operations now require operation lifecycle. This makes the
previously implicit dependencies explicit and rejects partial configurations.

## Selected assignment versus committed action

The event path now enforces four distinct facts:

```text
exact shadow assignment
    -> operation_reserved
    -> operation_step_selected
    -> byte-identical current runtime action accepted by existing gate
    -> operation_activated
    -> operation_step_revalidated
    -> operation_step_committed
    -> later authoritative snapshot
    -> operation_completed / operation_failed / operation_expired
```

An assignment alone never emits a committed event. At most one pending
operation may be activated by one engine action. Matching is over the complete
canonical action, not just action type or actor.

For the first bounded completion subset:

- a move-to-defend step completes when the required participant is
  authoritatively present at the target city;
- a fortify step completes when the participant remains at the city and its
  authoritative activity is fortify/fortified;
- a missing required participant or unavailable target city fails;
- an accepted step with no grounded completion proof by the deadline expires
  as `unresolved_unknown`;
- a selected step that was never committed expires as a censored operation,
  not a failed action.

Intercept disappearance and production completion are deliberately not
credited yet. Visible enemy disappearance may be fog-of-war rather than
destruction, and a production change is not a completed defender. Those cases
remain unresolved until combat/unit-lifecycle and production-completion
evidence is attached.

## Verification

The tests cover:

- stable identity under participant/goal permutation;
- digest-checked specification round trip;
- valid/invalid transition boundaries;
- attempt and terminal enforcement;
- identity-collision and stale-progress rejection;
- active-operation restart recovery;
- non-destructive quarantine of corrupt and wrong-identity stores;
- deterministic deadline behavior;
- typed city-defence assembly;
- schema-valid proposal, reservation, one-action activation, revalidation,
  commit, and authoritative move completion.

The focused operation/runtime/city-defence result is `38 passed`.

## Limits

This is a lifecycle foundation, not the GDO-4 exit gate:

- the live harness currently owns an in-memory operation store; durable
  per-game store injection/recovery is implemented by the core store but is
  not yet wired into harness restart;
- only a current action identical to the selected shadow step can activate it;
- no city-defence ordering changes;
- no multi-turn route repair;
- no authoritative movement ETA/native parity;
- no combat-attributed intercept outcome;
- no production-completion resolver;
- no resource-release event is yet linked to each operation terminal path;
- no replay or engine completion-rate delta has been measured with the new
  events.

## Fresh engine lifecycle diagnostic

The fresh seed-`4543804`, 160-turn engine trace completed without
infrastructure failure. Its raw 14,647-event trace validates with zero errors
and zero warnings. The retained diagnostic is
`benchmarks/gdo/gdo4_operation_lifecycle_160_diagnostic.json`, report hash:

```text
1bef9f80e60a417104aadda97369b06b5ce4a497211988f88e261a1e33abbc75
```

The lifecycle funnel is:

| Stage | Events | Unique operations |
| --- | ---: | ---: |
| Proposed | 552 | 445 |
| Reserved | 16 | 12 |
| Selected current step | 16 | 12 |
| Activated/revalidated/committed | 0 | 0 |
| Completed/failed | 0 | 0 |
| Expired | 12 | 12 |

All 12 unique selected operations received a terminal observation. Every one
expired as `censored_operation_abort`: it was selected by the asynchronous
shadow analyzer, but the frozen B1 controller did not subsequently execute
that byte-identical action before the operation deadline. One byte-identical
action had executed earlier in the same turn, before the shadow result was
emitted; the report records this as late diagnostic overlap and does not
retroactively call it a commit.

This is the correct null result for a non-authoritative shadow controller. It
does not prove a positive completion delta, and it also does not imply that an
accepted selected step failed. No selected step entered the committed
denominator.

The analyzer is
`scripts/analyze_gdo_operation_lifecycle.py`. Its tests enforce the ordering
boundary: an action before selection cannot be credited as a commit, while an
exact action after selection can enter the causal funnel.

## Next scientific step

Do not weaken action matching and do not count B1 coincidences as B4
completion. GDO-4 still needs authoritative movement ETA and at least 90%
supported winner-changing operation edges. After that gate, use bounded
engine-fork replays from retained snapshots to execute B1 and B4 current steps
in isolated copies and resolve both at the same deadline. This can measure an
operation-completion delta before granting persistent live policy authority.
