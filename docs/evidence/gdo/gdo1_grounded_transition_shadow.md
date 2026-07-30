# GDO-1 Grounded Transition Shadow

Status: implementation complete; exit evidence in progress
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

The existing scalar and teleological ordering remain unchanged. The new result
is attached as a shadow artifact after operation construction and before the
existing scheduler.

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
semantic decision and artifact hashes.

## Current verification

- New grounded-domain and focused controller tests: 63 passing.
- Complete post-generation FreeCiv test-family run: 816 passing in 324.81s.
- Shadow candidate order: identical to the comparator.
- Canonical action trace bytes: identical to the comparator.
- Shadow scheduler artifact: identical to the comparator.
- Versioned event payload validation: passing.
- Paired 200-iteration replay on the 34-candidate captured snapshot:
  - candidate coverage: 100%;
  - deterministic semantic estimates: pass;
  - baseline p95: 10.46 ms;
  - shadow p95: 13.88 ms;
  - p95 overhead: 32.7%;
  - required overhead gate: at most 5%, therefore **failed**.

Open GDO-1 exit evidence:

- reduction of measured controller-inclusive p95 overhead from 32.7% to the
  required maximum of 5%.

The checked diagnostic is
[`benchmarks/gdo/gdo1_shadow_diagnostic.json`](../../../benchmarks/gdo/gdo1_shadow_diagnostic.json).
No live authority may be enabled while the latency gate remains open.
