# FDAS PR86 isolated-launch paired replacement preregistration

Date: 2026-08-04

## Purpose and boundary

PR86 is a fresh, descriptive engine-backed replication of the corrected
coordinated-replacement intention pilot. It tests whether the V2 logical tuple
selection, native-route attempt budget, baseline-absence materialization, and
exact-action rematerialization corrections can produce mechanically valid
paired observations when every concurrent controller has a dedicated engine
port.

PR85 is permanently launch-invalid. Its seven attempted arms will not be
resumed, overwritten, or counted. None of its 16 registered seeds is reused.
PR86 has a new experiment identity:
`fdas-replacement-intention-isolated-launch-paired-pilot-v3`.

This remains a claim-ineligible mechanism pilot. It cannot establish a score,
win-rate, calibrated transition-value, or general policy claim.

## Frozen cohort

The 16 fixed seeds are:

`110161, 110183, 110221, 110233, 110237, 110251, 110261, 110269, 110273, 110281, 110291, 110311, 110321, 110323, 110339, 110359`.

Every seed has exactly one control arm and one treatment arm. Within-pair arm
order is the low bit of SHA-256 over `<experiment-id>:<seed>`. A seed pair is
assigned to worker `seed_offset mod worker_count`; both arms execute serially
on that worker. Independent pairs may execute concurrently.

- Control records the first lexicographically minimal grounded logical tuple
  without replacement execution authority.
- Treatment records the same intention rule and grants bounded execution
  authority to that one assigned operation.
- Each arm runs `e_full_loop` for the profile's fixed 160-turn horizon.
- The first intention has a fixed 32-turn outcome window.
- No arm is resumed or retried after engine execution starts.

## Launch safety contract

The checked-in launcher
`scripts/freeciv/run_fdas_replacement_intention_pairs.py` must complete all
preflight checks before creating the output root or starting an engine:

1. the source tree is clean and has a readable commit;
2. the output root does not exist, even if an existing directory is empty;
3. both profiles declare this exact experiment, seed list, arm lock, and
   claim-ineligible cohort;
4. worker count is between one and nine;
5. every worker has exactly one unique explicit port in 6001–6009; and
6. control and treatment configurations are distinct.

The registered run uses four process workers and ports 6001, 6002, 6003, and
6004. `HarnessRunner` receives a one-element `server_ports` tuple in every arm,
so a profile default cannot silently replace the dedicated port. The global
engine lock is located beside the shared output root, including when execution
uses a detached frozen worktree.

The intended output root is
`artifacts/freeciv/fdas-pr86-isolated-launch-paired-v3`. The launch manifest is
written before the workers start; the final launch summary preserves every
arm's seed, order, worker, port, timestamps, and terminal class.

## Exact analysis

The deterministic cohort audit must bind each assignment to its direct
candidate-readout parent and confirm that the selected tuple is the
lexicographic minimum of the readout's grounded logical surface. Pair classes
are fixed as `matched-observed`, `matched-censored`, `no-opportunity`,
`opportunity-mismatch`, `outcome-mismatch`, or `incomplete-pair`.

For matched observed pairs, the primary descriptive endpoint is the paired
risk difference for retaining both source and target cities at the intention
outcome turn. Secondary paired deltas are city-retention count, defended-city
count, assigned-actor survival count, and exact combat-attributed actor losses.
The audit also reports replacement execution attempts, accepted actions,
completion turns, unexplained removals, and candidate-surface agreement.

## Acceptance and progression criteria

The cohort audit accepts only if:

- all 32 fixed arms are present;
- every arm completed with a valid, warning-free ledger on one clean source
  commit;
- every manifest matches its frozen V3 arm contract;
- assignment, outcome, operation, and execution identities are valid;
- every assignment is bound to its candidate readout and obeys logical tuple
  ordering;
- all submitted engine actions were accepted;
- within-pair launch order matches the frozen order; and
- at least four pairs are matched and observed with no mechanical failures.

Progression additionally requires at least two treatment operation
completions, no excess unexplained treatment actor removal, and a nonnegative
point estimate on the primary city-retention endpoint. Failure of any
criterion is preserved as evidence and cannot be repaired by retrying a seed.
