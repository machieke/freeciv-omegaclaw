# FDAS PR78 coordinated-replacement candidate-readout preregistration

Date: 2026-08-04

## Frozen correction

PR77 proves that coordinated-replacement candidates and persistent lifecycle
mechanics are live, but none of those candidates appears in the existing
direct move/fortify scalar readout. PR78 adds a separate protected recall
readout rather than changing that calibrated surface.

For each current replacement candidate, the readout requires:

- one unambiguous direct move by the operation's reinforcement actor to the
  same deficit city;
- the direct move to carry the exact `protected-source-garrison` blocker;
- one nonterminal logical replacement lifecycle in `reservable` state;
- a current exact legal binding and unblocked RequirementSet context;
- the reinforcement actor to remain at the source city;
- current authoritative server routes for replacement-to-source and
  reinforcement-to-target; and
- exact combined ETA and movement cost equal to the sum of both routes.

The output says only that a safe chain is grounded and recalled. It explicitly
sets transition-value estimation, readout authority, policy authority, action
selection change, and truth mutation to false. It does not feed the existing
candidate union or declare that the first move relieves the target deficit.

## Known-opportunity integration gate

Seed `109459` is deliberately reused because PR77 observed 33 candidate rows
and 15 persistent operations there. The run is accepted only if the full PR77
lifecycle audit passes and the new audit finds at least one hash-valid grounded
pair, exact lifecycle references and route sums, revision-current
non-authorizing events, and status/terminal counters equal to durable evidence.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr78-coordinated-replacement-candidate-readout-v1 \
  --config profile/freeciv_harness_fdas_pr78_replacement_candidate_readout_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 43 --limit-seeds 1 --no-resume

GAME_DIR=artifacts/freeciv/fdas-pr78-coordinated-replacement-candidate-readout-v1/games/main/e_full_loop/109459-00
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_replacement_readout_live.py \
  --game-dir "$GAME_DIR" \
  --output docs/freeciv/evidence/fdas-pr78-coordinated-replacement-candidate-readout.json
```

The audit is rerun to a temporary output and compared byte-for-byte.

## Claim boundary

A pass establishes grounded candidate recall on a known opportunity. It does
not establish calibrated transition value, a decision-safe preference, action
execution, causal relief, score improvement, or win rate. Fresh-seed recall and
subsequent outcome calibration remain separate gates.
