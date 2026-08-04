# FDAS PR85 paired replacement launch failure

Date: 2026-08-04

## Result

PR85 is permanently rejected as a launch-invalid cohort. The process-isolated
launcher requested ports 6011 through 6014, but `HarnessRunner` correctly
applied the profile's configured `live.civserver_port=6001` because no explicit
`server_ports` tuple was supplied. All four workers therefore targeted the
same engine/proxy port.

The fault was detected during the first concurrent arm of four seed pairs.
Three arms had already terminated with pre-turn-1 infrastructure failures and
four were interrupted. One interrupted control arm reached event turn 18, so
the launch cannot be treated as a pregame smoke and cannot be retried under the
PR85 experiment ID. The remaining 12 seeds were never launched and are not
consumed by a gameplay result, but they will not be reused in the replacement
cohort.

The seven attempted arms, their event counts, maximum observed turns, and
terminal/interrupted statuses are preserved in the accompanying JSON report.
All manifests identify clean source commit
`55e84f7ceb8c9f78f9062195db0ae049f923b1d5` and all record port 6001. The
immutable artifact-tree digest at diagnosis was
`27b3874ed1a705fb9fcba96622755cec41db085e0096aa251c263c7dea076b0b`.

## Correction boundary

No PR85 arm will be resumed, overwritten, or counted. PR86 must use:

- a checked-in paired launcher rather than an inline orchestration command;
- an explicit one-element `server_ports` tuple for every process;
- unique ports within the runner's supported 6001–6009 range;
- an empty output-root preflight;
- a single clean source commit; and
- a new experiment ID and 16 entirely fresh seeds.

This is launcher evidence only. It says nothing about the logical-order,
attempt-budget, baseline-absence, or exact-rematerialization corrections.

