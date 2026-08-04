# FDAS PR82 audit composition correction

Date: 2026-08-04

The frozen PR82 engine run completed before this correction. Its immutable
event ledger, manifest, stores, status, and source identity are unchanged.
The first deterministic audit returned false on two mechanical checks even
though the underlying evidence satisfied them:

- the inherited PR77 lifecycle audit counted the PR82 `execution-*` lifecycle
  events as adapter reconciliation passes, while the established
  `fdas_replacement_reconciliations` counter intentionally counts only calls
  emitted by ordinary lifecycle reconciliation; and
- the PR82 audit required `rejected_actions` in the terminal `run_completed`
  summary, but that schema records terminal `actions` and keeps
  `rejected_actions` in `status.json`.

The corrected audit keeps all execution lifecycle events in the validated
ledger and disposition inventory, but excludes their explicitly prefixed
dispositions only from the legacy reconciliation-counter comparison. It also
proves rejection freedom directly from every `action_result`, reconciles that
inventory to `status.engine_actions` and terminal `actions`, and requires the
status rejection counter to be zero.

This is an audit-composition repair, not a treatment, seed, horizon, outcome,
or acceptance change. The engine run is not rerun and no failed treatment is
discarded. A regression fixture covers the mixed lifecycle stream.
