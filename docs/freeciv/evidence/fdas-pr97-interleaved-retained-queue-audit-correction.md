# PR97 interleaved retained-queue audit correction

Date: 2026-08-04

## Trigger

Both first PR97 aggregate passes were byte-identical and rejected with
structural hash
`64544defb342ac5c4d8d122b8e60c2a657c6f5ec59250717fbc9a27b768c4c8a`.
The sole failing game was seed `130553`; every query/episode dataset gate
except the composed parent-audit gate passed.

The failure reduced to
`label_transitions_are_unique_ordered_and_causally_grounded` in the delayed
outcome audit. No store, event, counter, identity, source, terminal/censor
partition, or query/episode join failed.

## Root cause

Seed `130553` carried two retained-capacity operations concurrently. On turn
26, operation `operation-050e0e3b5d0f3924177e5472a34e987d` emitted its exact
terminal abandonment. The same action refresh then revalidated operation
`operation-1b5e2758f9029729fc55d7a9c9c6f6d7` before materializing the next FDAS
revision. That revalidation had exactly two parents:

1. the target terminal event; and
2. the other operation's immediately prior revalidation.

The terminal outcome observation was causally below the ensuing exact
four-event FDAS revision chain. The old audit accepted a terminal only as the
direct parent of that revision chain, so it rejected this valid, deterministic
multi-operation interleaving.

## Narrow correction

The audit still accepts the original linear terminal/revision chain. It now
also accepts one additional shape only:

- the event before the exact revision chain is
  `operation_step_revalidated`;
- it uses the retained-capacity mechanism and a different operation;
- it has exactly two unique parents;
- one parent is the exact target operation's terminal event;
- the other is the same interleaved operation's prior typed revalidation;
- the terminal, interleaved revalidation, and observed outcome share the exact
  turn; and
- the history event is no later than that turn.

There is no broad ancestor search. Wrong history operation, wrong mechanism,
wrong turn, extra parent, same-operation interleaving, unrelated terminal, and
cycles remain rejected.

## Verification and claim boundary

Two focused synthetic tests pass, including the original direct-chain
rejections and the new exact-interleaving positive/negative cases. The complete
seed-130553 PR95 audit changes from rejected to accepted with corrected
structural hash
`a8fcae6ee64f5eba8348a6b2fe430a364ab4ac327b6483c52b24d0785d8b02c8`.

This is an audit-only correction. It changes no engine artifact, event, store,
label, episode, query, controller configuration, outcome, threshold, or
authority. The initial rejected aggregate result remains part of the PR97
audit history.
