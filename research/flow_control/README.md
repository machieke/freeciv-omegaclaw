# Unified PF/bridge/flow Stage-0 sandbox

This directory is an independent reference model for Gate G4. It is not
imported by the live FreeCiv planner and cannot authorize actions or write
evidence.

The sandbox exposes every synthetic route field and evaluates seed-disjoint
training and held-out cohorts across the preregistered graph, packet,
capacity, topology-failure, and evidence-selection families. It includes the
strong smoothed scalar comparator, the complete baseline set, the 14-stage
ablation ladder, exact small packet oracle, conservative transport checks,
and the full eight-dimensional stability map. Negative and fixed-point
regions are retained in the output.

Run the gate through:

```bash
python3 scripts/freeciv/run_pf_unified_baseline.py g4-sandbox
```

The resulting claim is synthetic controller evidence only. It is not a
FreeCiv gameplay score or win-rate claim.
