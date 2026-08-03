# FDAS PR61 candidate-transition calibration replication preregistration

Date: 2026-08-03

## Question and immutable boundary

PR60 confirmation passed every predictive-quality threshold but failed its
primary verdict because only four of 12 games contributed selected move
outcomes and those observations collapsed to 10 rather than 12 held-out
lineages. PR61 asks whether the exact frozen PR60 model passes the exact frozen
confirmation gates in a new, disjoint cohort prospectively sized for that
independent-game yield.

This is a replication, not model development. PR61 does not change the feature
schema, outcome target, lineage definition, model hierarchy, shrinkage,
minimum bin support, prediction algorithm, validation metrics, thresholds, or
scalar controller. It does not refit the model. The PR60 discovery and failed
confirmation remain immutable evidence and cannot be pooled into PR61.

## Prospective cohort size

The only PR60 confirmation result used for sizing is the mechanical
contributing-game rate: four of 12 games, or `1/3`. At that observed rate, 18
games would supply six contributing games only in expectation and would have
about 58.8% binomial probability of reaching the frozen six-game minimum.

PR61 freezes 30 games. Under the same `1/3` planning rate, the binomial
probability of at least six contributing games is approximately 96.5%. The
expected 25 move lineages at the observed `10/12` per-game rate also exceeds
the frozen 12-lineage minimum. These calculations size collection only; they
do not use PR60 outcome direction or predictive metrics and do not alter a
gate.

## Fresh seeds

The complete cohort is fixed in
`profile/freeciv_harness_fdas_pr61_transition_calibration_replication_160_turn.yaml`:

`108343, 108347, 108359, 108377, 108379, 108401, 108413, 108421, 108439,
108457, 108461, 108463, 108497, 108499, 108503, 108517, 108529, 108533,
108541, 108553, 108557, 108571, 108587, 108631, 108637, 108643, 108649,
108677, 108707, 108709`.

None appears in PR59, PR60 discovery, PR60 confirmation, or PR60's six
reserved seeds. No seed may be replaced, added, or removed after execution
starts. Every game must originate from one clean source commit and run to the
same terminal-aware 160-turn harness endpoint without resume.

## Frozen model and gates

The only allowed model is the hash-verified PR60 artifact
`fdas-pr60-candidate-transition-calibration-discovery.json`, whose model result
hash is
`edca977ffc87f9e731e00d5b5bacf3be03e1d5f28887e51e86966cb975ee3aa5`.

PR61 must first pass the unchanged PR60 feature and outcome-yield gates:

- at least 12 observed selected move outcomes;
- at least 3 positive and 8 negative move outcomes;
- at least 8 independent observed move lineages;
- at least 6 games with an observed move outcome;
- at least 6 selected grounded transition signatures; and
- at least 12 multi-move choice sets with distinct grounded signatures.

It then must pass the unchanged PR60 validation gates:

- at least 80% prediction coverage;
- at least 12 held-out effective lineages;
- at least 25% candidate-specific predictions;
- at least 2 distinct prediction values;
- Brier score at most `0.30`;
- log loss at most `0.85`;
- calibration error at most `0.20`;
- predicted mean inside the empirical Wilson 95% interval; and
- game-clustered Brier improvement over action-only with 95% interval lower
  bound at least `-0.05`, using 2,000 samples and bootstrap seed `16061`.

The report passes only if all mechanical, yield, and predictive gates pass.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr61-transition-calibration-replication-v1 \
  --config profile/freeciv_harness_fdas_pr61_transition_calibration_replication_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/validate_fdas_candidate_transition_calibration.py \
  artifacts/freeciv/fdas-pr61-transition-calibration-replication-v1 \
  --model docs/freeciv/evidence/fdas-pr60-candidate-transition-calibration-discovery.json \
  --output docs/freeciv/evidence/fdas-pr61-candidate-transition-calibration-replication.json \
  --confirmation-id fdas_candidate_transition_calibration_replication_v1 \
  --expected-source-commit "$SOURCE_COMMIT" \
  $(for seed in 108343 108347 108359 108377 108379 108401 108413 108421 108439 108457 108461 108463 108497 108499 108503 108517 108529 108533 108541 108553 108557 108571 108587 108631 108637 108643 108649 108677 108707 108709; do printf ' --expected-seed %s' "$seed"; done)
```

## Stop rules and claim boundary

- Preserve a failed run or report as failed evidence.
- Do not inspect partial outcomes, tune the model, or change thresholds while
  collection is active.
- Do not pool PR60 or any earlier cohort into PR61.
- Do not retry, replace, or reclassify a failed or terminal seed.
- Do not load the model into PR58 or any other live readout during PR61.

A pass permits only a separately implemented, default-off shadow readout-yield
experiment. Selected-only observational calibration does not establish the
counterfactual value of censored alternatives and grants no truth, policy,
readout, gameplay, score, or win-rate authority.
