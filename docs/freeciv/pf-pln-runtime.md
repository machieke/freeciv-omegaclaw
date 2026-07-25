# PF-PLN runtime activation

Canonical phase acceptance and live gameplay activation are separate claims.
All phases 0-9 have deterministic acceptance evidence, but only phases with an
engine adapter may affect a live harness game. The versioned support declaration
is `pf_pln_runtime` in `profile/freeciv_agent.yaml`.

## Current engine boundary

| Phase | Component | Declared support | Live enablement condition |
|---|---|---|---|
| 0 | executable semantics | engine-live | engine backend, scheduler capability, and `pressure_enabled` |
| 1 | goal regression planner | engine-live | engine backend, scheduler capability, and `pressure_enabled` |
| 2 | provenance and contradiction | component-only | Never enabled by a profile toggle |
| 3 | observation and simulation pressure | component-only | Never enabled by a profile toggle |
| 4 | conductance learning | engine-live | Phase 0/1 conditions plus `pressure_learning_enabled` |
| 5 | lifecycle clones | component-only | Never enabled by a profile toggle |
| 6 | induction and analogy | component-only | Never enabled by a profile toggle |
| 7 | LLM gateway | component-only | Never enabled by a profile toggle |
| 8 | differentiable execution | component-only | Never enabled by a profile toggle |
| 9 | multi-goal field | engine-live | engine backend, scheduler capability, and `pressure_enabled` |

`component-only` means the implementation and canonical benchmark exist, but
the engine-live loop has no adapter for that component. In particular, the
existing sequential `OpponentMemory` harness track is not PF-PLN Phase 6
contextual induction, and the live `ConstrainedProposer` path is not the
Phase 7 pressure-gated LLM gateway.

Changing a component-only row to `engine-live` fails configuration validation.
Enabling it requires an actual engine adapter, manifest and event integration,
new fail-closed tests, and an updated canonical declaration.

## Per-game derivation

The harness derives `manifest.json` → `pf_pln_runtime` from four inputs:

1. the checked support declaration;
2. the selected backend;
3. the condition capability matrix; and
4. the effective impact policy after paired-arm overrides.

The derived report contains each phase's support, enabled state, and reason,
plus a structural activation hash. It is part of `manifest_identity`, so a run
cannot resume across an activation change. The engine validates the report
again before opening the live connection.

The pressure-ablation baseline therefore records no enabled PF-PLN phases. Its
treatment records phases 0, 1, 4, and 9. The representative backend records no
live phases because it tests orchestration and statistics rather than engine
execution.

## Event evidence

Every harness event stream emits ten causal `metric_sample` declarations at
turn 0:

- `name=pf_pln_phase_enabled`;
- `value=1` only for an enabled phase;
- `declaration=pf_pln_runtime_activation`; and
- labels for phase, component, support, reason, backend, condition, and track.

These events are derived from the same checked report as the manifest. They let
replay and audit consumers distinguish accepted-but-unwired components from
components that could influence a particular game.

Run the complete boundary audit with:

```bash
python3 scripts/freeciv/audit_pf_pln.py --workers 4
```

The audit requires the default engine-live treatment to enable exactly phases
0, 1, 4, and 9, requires the pressure-off and representative configurations to
enable none, and requires every component-only phase to remain disabled.
