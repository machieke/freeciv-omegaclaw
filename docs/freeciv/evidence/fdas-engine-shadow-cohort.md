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

The sampled verifier hashes stable game/player/turn identity, not proxy source
sequence or transport timing. A selected semantic turn is verified at most
once at rates below 100%; a 100% diagnostic profile continues to verify every
revision. The resulting five-turn v8 schedule is reproducible across otherwise
identical engine runs.

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
  --out artifacts/freeciv/fdas-engine-shadow-control-20260802-v8 \
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
  --out artifacts/freeciv/fdas-engine-shadow-treatment-20260802-v8 \
  --backend engine-live --workers 1 --limit-seeds 3 \
  --main-only --condition e_full_loop --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_engine_shadow_cohort.py \
  --control artifacts/freeciv/fdas-engine-shadow-control-20260802-v8 \
  --shadow artifacts/freeciv/fdas-engine-shadow-treatment-20260802-v8 \
  --minimum-pairs 3 \
  --output artifacts/freeciv/fdas-engine-shadow-cohort-20260802-v8/report.json
```

## Result

Accepted. The final cohort ran from clean source commit
`0412a0513ce926f0dedb163978a3bcb3e628ef14`, implementation digest
`8c9d4087548ab5cb2dea51bd1c51a6bd974ea993912fd99bb0b69700edff25cb`,
and shadow declaration hash
`f7b2b3df75b0fa6f905a730aeed75546325c239c86cf24cfca4265b69fbf83c1`.
The audit structural hash is
`5e6f13d1e7194acee4fd28f5537ed02e9af91aeb57e37ff3110ee545e38d857c`.

| Acceptance measurement | Result |
|---|---:|
| Paired seeds / decision turns | 3 / 90 |
| Ordered action payloads | 188 / 188 exact |
| Action-result traces | 188 / 188 exact |
| Behavioral completion summaries | 3 / 3 exact |
| Valid shadow event streams | 3 / 3 |
| Cold verifications / mismatches | 5 / 0 |
| Missing legacy / explained legacy | 0 / 62 |
| Legal-binding failures / safety downgrades | 0 / 0 |
| Authority-eligible decisions / authority violations | 0 / 0 |
| Detail omissions | 0 |
| Maximum atoms / scopes / supports | 1,196 / 12 / 659 |
| Maximum events in one shadow pair | 5,727 |
| FDAS projection p50 / p95 / max | 93.08 / 139.75 / 181.06 ms |
| Shadow readout p50 / p95 / max | 2.15 / 5.72 / 7.06 ms |
| Total FDAS contribution p50 / p95 / max | 97.71 / 147.31 / 184.39 ms |
| Full controller p50 / p95 / max | 156.78 / 444.41 / 703.08 ms |

The maximum values are retained rather than hidden. The acceptance contract is
p95: the FDAS contribution passes its 150 ms target by 2.69 ms, and the full
controller passes its 500 ms target by 55.59 ms. This is enough to close the
declared engineering gate, but the narrow FDAS margin remains a reason to keep
the checked profile sampled, read-only, and bounded.

Per-seed outcomes also remained byte-for-byte behaviorally paired: seed
`104729` completed at score 108 versus 109, seed `104743` at 109 versus 115,
and seed `104759` at 117 versus 110. These scores describe the frozen
integration fixtures; because FDAS had no authority and emitted the exact same
actions as control, they are not evidence of gameplay improvement.

## Hardening trail

The first clean, semantically corrected cohort still missed only the FDAS
latency target. Each subsequent run followed a code change derived from the
preceding profile; no unchanged cohort was rerun merely to seek a favorable
timing pass.

| Cohort | Source commit | FDAS p95 | Controller p95 | Outcome |
|---|---|---:|---:|---|
| v2 | `03fbab8` | 174.91 ms | 454.66 ms | failed FDAS latency |
| v3 | `781dee4` | 157.81 ms | 497.10 ms | failed FDAS latency |
| v4 | `6e484eb` | 152.99 ms | 459.97 ms | failed FDAS latency |
| v5 | `de0a8b8` | 162.48 ms | 440.81 ms | failed FDAS latency |
| v6 | `74a703d` | 155.41 ms | 449.08 ms | failed FDAS latency |
| v7 | `dba7ef0` | 160.28 ms | 494.59 ms | exposed unstable sample identity |
| v8 | `0412a05` | 147.31 ms | 444.41 ms | accepted |

The material changes were conservative shard reuse, faster deterministic
identity construction, shared exact world topology/terrain for overlapping
regions, reuse of immutable paired-verification inputs, and stable semantic
cold-sample identity. The last change corrected measurement reproducibility;
it did not change the 5% rate, omit selected cold work, relax either latency
threshold, or enable FDAS authority.
