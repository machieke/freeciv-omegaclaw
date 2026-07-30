# GDO-1 Grounded Transition Shadow

Status: shadow exit gate passed
Policy effect: none
Live authority: unavailable and rejected at configuration time

## Implemented boundary

The shadow path wraps the existing canonical `ExpectedTransition` and
`PredictedOutcome` types in a `GroundedTransitionEstimate` containing:

- explicit authority;
- normalized transition context;
- snapshot, legal-action, ruleset, and turn validity;
- estimator identity and version;
- confidence and provenance;
- an explicit abstention reason when unsupported.

The compatibility estimator is named `legacy_projection/1.0` and always emits
`LEGACY_PROXY` authority. It is observable but cannot authorize a decision.
An unregistered model emits `ABSTAIN` with all probability mass explicitly
unknown.

## Transition-to-relief derivation

For current goal loss \(L_g(s)\) and modeled outcome \(o\):

```text
outcome relief = L_g(s) - L_g(s_o) - adverse_loss(o)
expected relief = sum(P(o | s,a) * outcome relief)
```

`ExpectedTransition` already owns `P(o | s,a)`. The typed path therefore does
not multiply by `Operation.success_probability` again. Unknown probability
mass receives zero positive relief in neutral mode. Conservative callers may
charge the declared residual loss in adverse mode.

The existing scalar and teleological ordering remain unchanged. Requests are
formed after operation construction, but estimate computation starts only
after the live ordering, schedule, and decision artifact are complete. One
bounded single-worker queue computes immutable, snapshot-pinned batches.

Completed observations are read without waiting on a later decision. A
run-scoped emitter deduplicates request identities, and the engine harness
drains the retained final batches before `run_completed`. Queue saturation,
worker failure, and completion timing remain observational and cannot change
the selected action.

## Candidate invariance

The shadow request and operation identities are based on:

- authoritative snapshot identity;
- legal-actions digest;
- full ruleset-IR digest;
- legal action;
- category and applicable goal context.

They do not include candidate position or utility. Tests cover:

- unrelated candidate insertion;
- candidate duplication;
- candidate permutation;
- positive scaling of legacy utility;
- deterministic semantic hashes that exclude wall timing.

## Fail-closed behavior

- New flags default to false.
- Authority requires estimate generation, scalar-v2 semantics, and commit
  revalidation.
- During GDO-1, authority is rejected even when those prerequisites are
  declared because no grounded domain model has passed a live support gate.
- Snapshot, legal-action, ruleset, or turn changes invalidate the estimate.
- Exact authority cannot retain unexplained unknown probability mass.

## Events

The event contract adds:

- `domain_estimate_emitted`;
- `domain_estimate_abstained`.

Events include transition/context/validity data, expected relief, adverse risk,
provenance, and observed estimator latency. Wall timing is excluded from
semantic decision and artifact hashes. The entire asynchronous
`domain_estimates` readout is excluded from the decision hash because a
pending-versus-completed observation is not decision semantics.

## Current verification

- Grounded-domain, controller, runtime, and harness tests after the asynchronous
  readout change: 165 passing in 287.69s.
- Complete post-change FreeCiv test-family run: 820 passing in 327.98s.
- Shadow candidate order: identical to the comparator.
- Canonical action trace bytes: identical to the comparator.
- Shadow scheduler artifact: identical to the comparator.
- Versioned event payload validation: passing.
- Paired 200-iteration replay on the 34-candidate captured state, with a fresh
  snapshot identity and fresh estimate batch for every pair:
  - candidate coverage: 100%;
  - completed measured batches: 200/200;
  - worker failures and queue-capacity rejections: zero;
  - deterministic semantic estimates: pass;
  - baseline decision-path p95: 11.98 ms;
  - shadow decision-path p95: 11.90 ms;
  - measured p95 overhead: -0.66%, treated as parity/no regression;
  - required decision-path overhead: at most 5%, therefore **passed**;
  - worker-compute p95: 12.56 ms;
  - shadow rank-plus-drain p95: 24.53 ms;
  - full shadow-loop p95 overhead: 104.76%.

The worker result is deliberately not awaited by live action selection, which
closes the stated planning-latency gate. The extra computation has not
disappeared: the diagnostic separately reports its queue, worker, and
rank-plus-drain distributions. GDO-2 engine evaluation must continue to report
full-turn latency and queue saturation so that background contention cannot be
misrepresented as free.

## Exit decision

All explicit GDO-1 shadow gates now pass. This permits GDO-2 implementation in
default-off shadow mode. It does not authorize grounded estimates, establish
gameplay value, or close the still-open GDO-0 engine cohort and repository-wide
baseline gates.

The checked diagnostic is
[`benchmarks/gdo/gdo1_shadow_diagnostic.json`](../../../benchmarks/gdo/gdo1_shadow_diagnostic.json).
No live authority may be enabled until a later grounded model passes its own
parity, support, calibration, safety, and engine-evaluation gates.
