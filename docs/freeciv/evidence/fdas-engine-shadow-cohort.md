# FDAS paired engine-shadow cohort

Date: 2026-08-02  
Branch: `experimental/functional-dependent-atomspace`  
Claim scope: live integration, behavioral parity, boundedness, and latency only

## Frozen design

This cohort closes the multi-seed engine evidence gate without enabling FDAS
authority or making a gameplay outcome claim. It uses fresh engine executions
of the first three pinned harness seeds, `104729`, `104743`, and `104759`, at
the versioned 30-turn horizon. The seeds are intentionally reused because this
is a deterministic integration/parity test, not a seed-disjoint score or
win-rate experiment.

Each seed has two runs over the same clean source commit:

- control: the checked `profile/dependent_atomspace.yaml`, with rich FDAS
  construction disabled;
- shadow: `profile/dependent_atomspace_shadow_sampled.yaml`, with rich
  projection, all domain slices, shadow readout, and deterministic 5% cold
  verification enabled.

Both declarations keep aggregate authority, all domain authority, and manifest
policy authority false. The harness condition is `e_full_loop`, workers are
fixed at one, and induction/grading tracks are excluded.

The acceptance contract is frozen in
`benchmarks/freeciv/harness/fdas_shadow_cohort.py` and covered by
`Autotests/test_freeciv_fdas_shadow_cohort.py`. A pair passes only when:

1. both runs complete and both event streams validate;
2. source commit and implementation digest are identical and clean;
3. every non-FDAS behavioral manifest field is identical;
4. ordered canonical `action_sent` payloads, action-result statuses, and
   behavioral completion summaries are exact matches;
5. FDAS emits shadow decisions but no authority-eligible decision;
6. missing legacy candidates, legal-binding failures, safety downgrades,
   authority violations, detail omissions, and sampled cold mismatches are all
   zero;
7. atom materialization remains below the declared global cap;
8. the measured FDAS projection-plus-readout contribution per turn has p95 at
   or below 150 ms; and
9. the shadow run's complete controller p95 remains below 500 ms.

Any failed target remains a blocking diagnostic; it is not averaged away
across pairs.

## Commands

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN='<local proxy token>' \
FREECIV_SERVER_CONTAINER=fciv-net \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness.yaml \
  --out artifacts/freeciv/fdas-engine-shadow-control-20260802 \
  --backend engine-live --workers 1 --limit-seeds 3 \
  --main-only --condition e_full_loop --no-resume

FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_shadow_sampled.yaml \
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN='<local proxy token>' \
FREECIV_SERVER_CONTAINER=fciv-net \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness.yaml \
  --out artifacts/freeciv/fdas-engine-shadow-treatment-20260802 \
  --backend engine-live --workers 1 --limit-seeds 3 \
  --main-only --condition e_full_loop --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_engine_shadow_cohort.py \
  --control artifacts/freeciv/fdas-engine-shadow-control-20260802 \
  --shadow artifacts/freeciv/fdas-engine-shadow-treatment-20260802 \
  --minimum-pairs 3 \
  --output artifacts/freeciv/fdas-engine-shadow-cohort-20260802/report.json
```

## Result

Pending fresh engine execution from the frozen checkpoint.

