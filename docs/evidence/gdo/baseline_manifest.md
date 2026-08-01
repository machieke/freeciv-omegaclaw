# GDO Baseline Manifest Status

The grounded-domain program starts from commit
`87f3482e631b0713378e69b350e460d4c6a310b7` on
`experimental/pln-pressure–bridge–fluid`.

Status: frozen and complete for every supported program scope

The first targeted regression run was clean:

```text
PYTHONPATH=.:src:benchmarks pytest -q \
  Autotests/test_freeciv_transitions.py \
  Autotests/test_freeciv_teleology.py \
  Autotests/test_freeciv_pf_runtime.py \
  Autotests/test_freeciv_adapter.py

40 passed in 16.49s
```

After the GDO-1 asynchronous readout, final-drain, and generated event-type
changes, the complete FreeCiv test family passed:

```text
820 passed in 327.98s
```

The final source state was rechecked with the same subsystem-wide command:

```text
PYTHONPATH=.:src:benchmarks python3 -m pytest -q Autotests/test_freeciv_*.py

1063 passed in 346.23s
```

The repository's Slack, Telegram, and generic agent integration tests are
separate container-backed CI phases and are not part of this FreeCiv program
manifest. Collecting all of their mock directories in one Python process is
not a supported test topology because each suite deliberately supplies
suite-local top-level driver modules.

## Frozen comparator identities

- `B0`: canonical Impact ordering and execution path at the review commit.
- `B1`: scalar PF-v2 plus the existing v1 whole-packet scheduler, with bridge,
  source–sink flow, generic path persistence, and grounded-domain authority
  disabled.

The byte-exact scalar comparator manifest and its nine retained golden
artifacts are frozen separately in
`benchmarks/freeciv/pf_unified/baseline_manifest.yaml`. GDO-1 replay preserves
the B1 live trace and schedule while emitting typed shadow estimates.

## Closure evidence

- The GDO-4 city-defence confirmation contains 30 complete paired seeds,
  source and trace hashes, controller-inclusive latency distributions, and a
  passing mechanism/safety gate.
- The GDO-5 atomic-combat confirmation supplies a second fresh source-frozen
  engine cohort and a passing operation mechanism gate.
- The GDO-8 training and disjoint holdout cohorts supply 120 clean engine arms
  and a frozen contextual-calibration audit.
- Retained engine snapshots cover city defence, movement, attack, production,
  and research. GDO-6 records the transport boundary explicitly: its
  founder/ferry contract and lifecycle fixtures are reproducible, but the
  retained engine corpus contains no advertised embark sequence. Transport
  therefore remains default-off and makes no engine-backed claim.
- Ruleset source and compiled-IR identities are inherited from the verified
  scalar baseline manifest and copied into the machine-readable GDO manifest.

The supported comparator and program artifacts are therefore reproducible and
frozen. “Complete” here does not promote unsupported transport or bridge/flow
authority; those negative boundaries are part of the frozen result.

The machine-readable status is
[`benchmarks/gdo/baseline_manifest.json`](../../../benchmarks/gdo/baseline_manifest.json).
Regeneration tooling is provided by
[`scripts/run_gdo_baseline.py`](../../../scripts/run_gdo_baseline.py).

No gameplay or score claim is authorized by this baseline.
