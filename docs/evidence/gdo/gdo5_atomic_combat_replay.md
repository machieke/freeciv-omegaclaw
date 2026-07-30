# GDO-5 atomic combat replay

Status: mechanism gate passed in synthetic and captured replay; shadow-only

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

## Question and claim boundary

Does the initial two-actor combat-operation scheduler preserve complete
operations and prevent duplicate targeting when it is replayed on genuine
joint-combat states?

The answer is yes for the five retained, exact player-visible snapshots and
the eight synthetic mechanism scenarios. This is a coordination-mechanism
result, not a gameplay-outcome, score, or win-rate result. The operation path
remains shadow-only and executed no game action.

## Discovery and repairs

The first 160-turn engine pilot, seed `4543804-00`, contained native combat
probabilities but no state with two supported own actors against one visible
defender. A six-seed discovery continuation found joint states in four seeds:

| Seed | Joint states | Pre-repair proposals |
| --- | ---: | ---: |
| `104743` | 5 | 15 |
| `104759` | 6 | 16 |
| `104773` | 13 | 37 |
| `104779` | 2 | 6 |

Those states exposed two correctness gaps:

1. Freeciv may use target unit ID `0` as a tile-query sentinel. Candidate
   assembly could resolve an exact one-unit visible stack, but commit readout
   compared the resolved operation target with the raw sentinel and therefore
   rejected the same operation as incomplete. Assembly and readout now apply
   the same rule: resolve only a one-unit exact visible stack, and abstain for
   an ambiguous stack.
2. A two-step operation claimed both actor identities and movement resources
   but did not claim two controller actions. It now claims exactly two
   `ACTION_BUDGET` units. An available budget of one selects no part of the
   operation.

A bounded native interval whose upper probability is zero is also excluded
from combat support.

## Fresh engine-backed source trace

After those repairs, seed `104743` was replayed for 160 turns with the GDO-5
shadow path enabled:

```text
artifacts/freeciv/gdo5-joint-positive-replay-v1
```

The run completed all 160 turns with zero experiment failures and zero
infrastructure failures. Its `events.jsonl` SHA-256 is:

```text
f67eaa6a4f38ffc3d4c21b345ae92032b4cd92b546852cc230b0f2ff7520f597
```

It emitted 15 atomic proposals and five selected shadow schedules over five
exact snapshots. Nine alternatives were rejected for an exclusive-resource
conflict and one for a non-positive operation bid. Every selected operation
claimed two action-budget units. At most one operation was selected per exact
snapshot; the two observations on turn 72 have distinct source sequence and
state identities.

The source trace is retained as an experiment artifact, while the checked-in
corpus contains the five smallest sufficient player-visible snapshot
projections.

## Captured exact replay

The extraction command is:

```bash
python3 scripts/extract_gdo_combat_replays.py \
  --events artifacts/freeciv/gdo5-joint-positive-replay-v1/games/main/e_full_loop/104743-00/events.jsonl \
  --run-manifest artifacts/freeciv/gdo5-joint-positive-replay-v1/games/main/e_full_loop/104743-00/manifest.json \
  --ruleset-digest 6f2283982e2a3ee0a4fd1a50a74ac9af4a3d00bed1fad879931ce82000daa1ea \
  --output-directory benchmarks/gdo/captured_snapshots/combat_operations_native_160 \
  --output-manifest benchmarks/gdo/captured_snapshots/combat_operations_native_160_manifest.json
```

The corpus records only authoritative player-visible event fields and binds
each fixture to its source event, source event-stream hash, source manifest,
and structural ruleset digest.

| Item | SHA-256 |
| --- | --- |
| Fixture manifest | `29c56af71e0245f9bdde6f7675814e7335a3da5fa1e08e8f401c2b1819ddd5a3` |
| Ruleset structural digest | `6f2283982e2a3ee0a4fd1a50a74ac9af4a3d00bed1fad879931ce82000daa1ea` |
| Source event stream | `f67eaa6a4f38ffc3d4c21b345ae92032b4cd92b546852cc230b0f2ff7520f597` |

The replay command is:

```bash
python3 scripts/run_gdo_combat_captured_replay.py \
  --manifest benchmarks/gdo/captured_snapshots/combat_operations_native_160_manifest.json \
  --iterations 100 \
  --output benchmarks/gdo/gdo5_combat_operation_captured_diagnostic.json
```

The retained report hash is:

```text
28ebbc95679832541c1dcd16f3c75bcdfc2960c6c21c4cc3a6f44dc33524cdf0
```

All five fixtures reproduce the source candidate IDs, selected operation IDs,
and per-operation reason map. The deliberately uncoordinated comparator
selects multiple actions against the same target on 5/5 fixtures. Atomic
scheduling reduces that diagnostic duplicate-target count from five to zero,
with complete reservations and no action-budget excess. The result is
deterministic over 100 iterations. Controller-inclusive replay latency over
500 samples was 2.92 ms mean, 2.97 ms p95, and 13.32 ms maximum.

## Synthetic mechanism coverage

The labeled synthetic corpus is
`benchmarks/gdo/combat_operation_scenarios_v1.json`; it is not represented as
engine evidence. It contains eight scenarios covering:

- two and three attackers competing for one target;
- two disjoint targets that can be scheduled together;
- one actor shared across targets;
- insufficient action budget;
- ambiguous and unambiguous target sentinels;
- zero-upper-probability native intervals.

The replay command is:

```bash
python3 scripts/run_gdo_combat_operation_replay.py \
  --scenarios benchmarks/gdo/combat_operation_scenarios_v1.json \
  --iterations 100 \
  --output benchmarks/gdo/gdo5_combat_operation_synthetic_diagnostic.json
```

All declared gates pass. Its report hash is:

```text
ce668b07417303328396744559e2f789317d049eb95d666e20f91da059836934
```

Controller-inclusive latency over 800 samples was 0.84 ms mean, 1.50 ms p95,
and 10.19 ms maximum.

## Verification and decision

Automated checks verify fixture and report self-hashes, exact captured replay,
determinism, complete atomic claims, action-budget accounting, conflict
exclusion, sentinel handling, and the absence of policy authority.

This closes the atomic-versus-independent replay item in GDO-5. It does not
open live authority. The remaining GDO-5 exit work is:

1. actual live step execution;
2. target capture, retention, and material-loss accounting;
3. the remaining combat-operation catalogue;
4. a frozen disjoint engine pilot with actual execution and a directional
   outcome gate.

Post-step re-estimation and terminal lifecycle/release semantics are now
implemented and tested; see `docs/evidence/gdo/gdo5_combat_lifecycle.md`.
