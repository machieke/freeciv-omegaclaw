# GDO-5 combat candidate readout correction

Status: captured candidate-recall and fresh shadow-lifecycle gates passed;
causal policy and gameplay gates remain open

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

## Claim boundary

The corrected readout recovers safe, server-advertised attacks in all five
retained joint-combat snapshots that the prior garrison rule suppressed. A
fresh disjoint engine cohort also confirms that, when the supported scalar
planner independently chooses the scheduler's exact first action, the
shadow operation can reserve its participants, observe the accepted action,
commit the step, resolve target neutralization, and release its claims.

The operation still had `policy_authority=false`: it observed and attributed
the scalar planner's action but did not cause it. The evidence therefore
establishes candidate recall, exact scalar/operation alignment, and lifecycle
correctness. It does not establish causal policy benefit, material advantage,
score improvement, or win-rate improvement.

## Root cause

The planner formerly used the final mood value
`happy - unhappy - 2 * angry` as both a disorder margin and a proxy for the
number of defenders that had to remain in a city. A stable all-content city
has a final margin of zero. The old `margin <= 1` rule therefore classified
that healthy state as near disorder and reserved as many defenders as the
configured city limit.

In the retained turn-68 through turn-70 states, Roma had:

- six citizens;
- no disorder;
- final mood of zero happy, six content, zero unhappy, zero angry;
- three local attack-capable units;
- two unhappy citizens before the packet's martial-law stage and zero after.

The old rule required all three defenders and removed every exact visible
attack from the candidate set. This happened before scalar PF-v2 could score
the actions. Faster flow or different pressure weights could not repair the
missing candidates.

## Correction

`grounded-impact-planner/1.35` now reads the protocol-ordered citizen mood
stages:

- stage index 3: before martial-law effects;
- stage index 4: after martial-law effects;
- final stage: authoritative post-effect mood.

It measures the observed reduction in disorder burden across the martial-law
stage. Positive final mood margin offsets that burden. Each remaining relief
point conservatively reserves at most one defender, bounded by the existing
military-unit limit. Explicitly disordered cities retain the prior
fail-closed protection.

For the captured states:

| Turns | Local defenders | Prior requirement | Corrected requirement | Safe single-step attack recalled |
| --- | ---: | ---: | ---: | ---: |
| 68, 69, 70 | 3 | 3 | 2 | yes |
| 72, 72 refresh | 3 | 3 | 1 | yes |

The one-step condition is important. At every readout, removing one acting
unit still leaves at least the corrected required garrison. Later operation
steps remain subject to a new snapshot, new candidate enumeration, and exact
commit revalidation.

## Captured replay

The retained command is:

```bash
python3 scripts/run_gdo_combat_candidate_readout_replay.py \
  --manifest benchmarks/gdo/captured_snapshots/combat_operations_native_160_manifest.json \
  --iterations 100 \
  --output benchmarks/gdo/gdo5_combat_candidate_readout_diagnostic.json
```

The report hash is:

```text
e7c4375e906a1e1c1d9602ba881c0b07a11f9f96ff3f7a51528c9b6f357dde17
```

All nine declared gates pass. The previous rule suppresses all five retained
joint states; the corrected readout recalls at least one exact attack in all
five; every recalled single step preserves the grounded garrison requirement;
and readout digests are deterministic. The replay also runs the supported
scalar planner and exact atomic scheduler over the same immutable state. On
both retained turn-72 snapshots, scalar PF-v2 selects the exact first action
of the scheduler-selected operation: actor 108 attacks `(14, 13)`. On turns
68 through 70, the scalar planner instead prioritizes famine prevention; the
operation stays shadow-only and does not override that choice.

Across 500 combined candidate, scalar-plan, and exact-schedule samples,
latency was 9.14 ms mean, 10.95 ms p95, and 20.55 ms maximum. The p95 remains
below the declared 20 ms replay gate.

## Fresh engine pilot

A fresh 160-turn same-seed run was executed after the correction:

```bash
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN=test-token-fc3d-001 \
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_SERVER_CONTAINER=fciv-net \
OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/gdo5-combat-readout-pilot-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6100 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume
```

The run completed 160 turns with zero experiment failures, zero infrastructure
failures, zero rejected engine actions, and a valid 12,298-event trace. Its
`events.jsonl` SHA-256 is:

```text
574a07107236e74ca103eb1e2a61dca79a7cba9d1c3543ad33bda37e527cf918
```

The trace contained six native combat-probability rows, but never two actors
against the same target. It therefore contained zero eligible joint-combat
operations and cannot validate execution of the corrected joint readout. No
`unit_attack` action was submitted. This is an opportunity-absent pilot, not a
negative execution result and not an outcome comparison.

## Fresh disjoint opportunity search

Three further 160-turn engine-backed seeds were run with the corrected
readout:

| Seed | Trace events | Native combat rows | Joint operations | Selected operations | Real attacks | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 104773 | 7,259 | 16 | 0 | 0 | 0 | no same-target joint opportunity |
| 104759 | 14,704 | 13 | 0 | 0 | 0 | two simultaneous rows targeted different units |
| 104779 | 14,361 | 22 | 1 | 0 | 2 | joint operation correctly rejected as nonpositive |

All three games completed the 160-turn horizon with zero experiment,
infrastructure, or engine-action rejection failures. The trace hashes are,
respectively:

```text
a682b7ced6dbe89ed0ba76941ee688db5c2e27c1f799fda0550d6bae34148a2c
036e09f0895f78bba10cda9d46eaf7f78d8a716e7d6eee8d25f6899fd3d5086b
e03dbb176d658bef0d87df7a13a70569709d66a0f6a953a2f7ecdef75685061e
```

Seed 104779 is the informative rejection case. At turn 82 the engine exposed
two legal attacks on the same visible target, so the assembler created an
atomic two-participant operation. Both native action intervals were
`[0.000, 0.005]`; the exact scheduler rejected the zero lower-bound bid and
the scalar planner ended the turn. The two real attacks elsewhere in that
game occurred at turns 67 and 106 and were single-actor opportunities, so
they were not falsely attributed to the joint operation.

## Fresh ten-seed execution cohort

A second fresh disjoint cohort searched ten predeclared seeds through turn
160:

```bash
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN=test-token-fc3d-001 \
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_SERVER_CONTAINER=fciv-net \
OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/gdo5-combat-execution-disjoint-sweep-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6100 \
  --limit-seeds 10 --condition e_full_loop --main-only --no-resume
```

The harness configuration hash was
`2a205a6ee9edd49fa892024f77a2ee60c6669292e0724c77f49eafad8ed949f9`.
All ten games completed the 160-turn horizon with zero experiment failures,
zero infrastructure failures, and zero rejected engine actions. Every trace
passed `scripts/freeciv/validate_events.py` with zero errors and warnings.

| Seed | Events | Native rows | Joint operations | Selected | Scalar-aligned and completed | Real attacks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 104789 | 8,368 | 18 | 0 | 0 | 0 | 0 |
| 104801 | 14,575 | 56 | 0 | 0 | 0 | 2 |
| 104803 | 5,575 | 7 | 0 | 0 | 0 | 0 |
| 104827 | 8,631 | 5 | 0 | 0 | 0 | 0 |
| 104831 | 12,956 | 14 | 0 | 0 | 0 | 0 |
| 104849 | 11,555 | 15 | 0 | 0 | 0 | 0 |
| 104851 | 11,005 | 13 | 0 | 0 | 0 | 0 |
| 104869 | 21,552 | 55 | 11 | 4 | 3 | 10 |
| 104879 | 12,009 | 12 | 0 | 0 | 0 | 0 |
| 104891 | 8,188 | 9 | 0 | 0 | 0 | 0 |
| **Total** | **114,414** | **204** | **11** | **4** | **3** | **12** |

Seed 104869 supplied the positive execution opportunities:

- turn 46: actor 117 attacked `(6, 13)` with native interval `[1, 1]`;
- turn 110: actor 130 attacked `(9, 17)` with native interval
  `[0.505, 0.510]`;
- turn 160: actor 195 attacked `(9, 18)` with native interval
  `[0.910, 0.915]`.

For all three, the exact scheduler's `next_action` was byte-equivalent to the
supported scalar planner's submitted action. FreeCiv accepted each action,
the operation emitted `operation_activated` and
`operation_step_committed`, and it terminated as `operation_completed` with
reason `target-neutralized`. The fourth selected shadow operation, at turn
61, did not match the scalar winner; it did not activate and expired at its
deadline. This is the required fail-closed behavior, not a partial
activation.

The positive trace passed the complete release audit with cognitive tracing
required. Its six stable claim identities were refreshed as snapshots
changed, then all were released; there were no unreleased reservations,
repairs, blocked operations, or hard-resource conflicts.

The trace SHA-256 values are:

| Seed | `events.jsonl` SHA-256 |
| --- | --- |
| 104789 | `a8a1898337a3fcb4cc8e54bcbaea7ecfbb9bf6066d8fb10ccdea1baf52a8168a` |
| 104801 | `2aaae1f7a7e3e8a2dc507e45cbafe3570b4cfb1f388177e73b6366e8e2bdc00b` |
| 104803 | `e7b42a0f869d5f6b814f59aeeb1c7b306e35f5447f1822fb9be42ca14c81be8d` |
| 104827 | `ed8903dde48b473a5216cfdac56f64d31b5c994a0ebf936f1114ac3cafba8440` |
| 104831 | `230be2652b3dfbb98d276364264fb642ae8fdf2eb2f47faba017582713d9e0ec` |
| 104849 | `3f2e5e208b854073cf8751390775521663cf0f6832a8332326ba0c19a9a6c42a` |
| 104851 | `f4010a8d0e90dc6c3a1aeaeb3edcaa073b87f7a6919d47392ad4ae64dab59a3c` |
| 104869 | `a930fdca1883a8ee368d965e73d3fbf0a626320bc86fe94b1914eb949458f80f` |
| 104879 | `39b33a5ddba043bba9b29f32eb7965ac12d4ff912d065b916e4a6ac2daa9f547` |
| 104891 | `1c1f994b6f82a282c014b4b198d1a2c1925f199b2659d1e4c69620d643cdfa06` |

## Decision

The demonstrated pre-score suppression bug is fixed and protected by both a
small unit regression and a replay over all retained player-visible engine
fixtures. The captured replay now proves that the corrected scalar readout
and exact operation scheduler choose byte-identical first actions in two
high-confidence joint states without changing policy authority. The fresh
cohort closes the shadow execution and lifecycle-attribution question with
three accepted, target-neutralizing, scalar-aligned actions and one clean
non-aligned expiry.

Combat operations remain shadow-only. Establishing the GDO-5 causal mechanism
exit gate still requires a controlled comparator showing lower duplicated
targeting or abandoned partial attacks when bounded authority is enabled.
Score and win-rate claims remain unchanged.
