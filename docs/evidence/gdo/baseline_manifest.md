# GDO Baseline Manifest Status

The grounded-domain program starts from commit
`87f3482e631b0713378e69b350e460d4c6a310b7` on
`experimental/pln-pressure–bridge–fluid`.

The baseline is intentionally marked **in progress**. The first targeted
regression run is clean:

```text
PYTHONPATH=.:src:benchmarks pytest -q \
  Autotests/test_freeciv_transitions.py \
  Autotests/test_freeciv_teleology.py \
  Autotests/test_freeciv_pf_runtime.py \
  Autotests/test_freeciv_adapter.py

40 passed in 16.49s
```

This is sufficient to begin the default-off GDO-1 schema work, but it does not
close GDO-0. The following baseline gates remain open:

- complete non-FreeCiv repository test suite;
- two repeat runs of each frozen comparator;
- controller-inclusive latency distribution;
- engine-live baseline cohort;
- captured snapshots for defence, attack, transport, production, and research;
- engine and ruleset binary identities.

After the GDO-1 asynchronous readout, final-drain, and generated event-type
changes, the complete FreeCiv test family passed:

```text
820 passed in 327.98s
```

## Frozen comparator identities

- `B0`: canonical Impact ordering and execution path at the review commit.
- `B1`: scalar PF-v2 plus the existing v1 whole-packet scheduler, with bridge,
  source–sink flow, generic path persistence, and grounded-domain authority
  disabled.

The machine-readable status is
[`benchmarks/gdo/baseline_manifest.json`](../../../benchmarks/gdo/baseline_manifest.json).
Regeneration tooling is provided by
[`scripts/run_gdo_baseline.py`](../../../scripts/run_gdo_baseline.py).

No gameplay or score claim is authorized by this partial baseline.
