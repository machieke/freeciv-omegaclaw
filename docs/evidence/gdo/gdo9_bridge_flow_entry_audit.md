# GDO-9 bridge and flow re-entry audit

## Decision

The GDO-9 entry gate is closed. Bridge and source–sink flow remain available
only for offline, replay, and shadow research. They receive no new policy
authority.

GDO-9 is conditional: numerical flow work resumes only after all seven entry
conditions are proven against the grounded B4 scheduler. Implementing or
retuning another flow controller while five conditions remain false would
confound routing with unresolved calibration, lifecycle, and semantic errors.

## Entry conditions

| Condition | Result | Evidence |
|---|---|---|
| Candidate-invariant, calibrated typed estimates for target slice | blocked | GDO-8 passes only a synthetic mechanism gate; no disjoint engine-backed v2 training/holdout bundle exists |
| Zero hard identity/resource over-allocation | passed | GDO-3 reports no hard-capacity violations and deterministic exact scheduling |
| Stable operation completion/failure semantics | blocked | synthetic combat lifecycle passes, but retained engine replay has no committed or completed operation |
| Bounded exact operation scheduler as comparison baseline | passed | B4 is implemented and deterministic in captured shadow comparison |
| Residual error specifically caused by route allocation | blocked | no post-calibration B4 replay residual has been isolated |
| Residual is not semantic, stale, missing-candidate, or unsupported-estimate error | blocked | the prior engine failure was semantic terminal-action exclusion, and current contextual engine support is absent |
| Expected incremental value exceeds controller-inclusive cost | blocked | prior engine confirmation did not establish benefit and added substantial latency |

The canonical machine-readable audit is
`benchmarks/gdo/gdo9_bridge_flow_entry_audit.json`.

## Baseline ladder status

- `B0`: frozen canonical Impact exists.
- `B1`: frozen scalar PF-v2 plus v1 packets exists.
- `B2`: grounded estimates plus v1 scheduler exists in shadow.
- `B3`: grounded identity-aware greedy scheduling exists in shadow.
- `B4`: grounded bounded exact operation scheduling exists in shadow.
- `B5`: historical bridge shadow evidence has not been revalidated against
  B4.
- `B6`: historical source–sink flow evidence has not been revalidated against
  B4.

The historical protected bridge diagnostic added 226 candidate memberships
and passed its old recall mechanism gate. That does not satisfy the new bridge
claim: it predates B4 and cannot take credit for candidates now supplied by
grounded domain models.

The historical synthetic flow sandbox demonstrated strong numerical effects,
but its comparison baselines also predate grounded B4. Those synthetic effects
did not transfer to the prior engine confirmation.

## Historical engine result

The completed 100-pair flow-advisory confirmation reported:

- player score delta: +0.05;
- paired 95% interval: [-0.33, +0.43];
- primary endpoint: not met;
- Impact planning overhead: +219.75 ms/turn;
- full-loop overhead: +291.57 ms/turn.

Its diagnosed error was semantic: flow overlap excluded immediately legal city
founding and preferred another founder movement. All numerical projections
were healthy. This is precisely the kind of failure condition 6 excludes.

## Runtime consequence

`PairedCohortEvidence` now requires an explicit passed GDO-9 entry result and
its report hash before it can be eligible for limited live flow. Old paired
evidence cannot silently unlock the new grounded controller. The existing
scope, fresh-confirmation, calibration, safety, replay, and latency gates
remain in force as additional requirements.

The current audit has `entry_approved: false`, so it cannot be used as an
approval hash.

## Required evidence before re-entry

The next admissible sequence is:

1. collect clean, claim-ineligible engine outcomes using the v2 contextual
   schema;
2. fit on training seeds and pass a disjoint frozen engine holdout;
3. demonstrate committed and completed grounded operations in engine replay;
4. replay B4 and identify a residual error attributable only to route or
   bottleneck allocation;
5. show that solving that residual has expected value above measured
   controller-inclusive latency;
6. only then compare B5 with B4, followed by B6 with B5.

If no such residual exists, GDO-9 remains closed; that is a valid negative
result, not an implementation gap.

## Reproduction

```sh
PYTHONPATH=.:src:benchmarks \
  python3 scripts/run_gdo_bridge_flow_entry_audit.py

PYTHONPATH=.:src:benchmarks python3 -m pytest -q \
  Autotests/test_freeciv_gdo9_entry_audit.py \
  Autotests/test_freeciv_limited_live_activation.py
```

