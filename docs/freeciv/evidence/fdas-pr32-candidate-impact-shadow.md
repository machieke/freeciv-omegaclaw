# FDAS PR32 promoted-rule candidate-impact shadow

Status: live mechanism implemented and deterministic frozen replay accepted;
contextual transition-value deltas are measurable, but the approved rule basis
does not change a fortification winner; no intervention, gameplay, score, or
win-rate claim.

## What changed

PR32 joins the four-rule PR30 basis to exact snapshot-bound FDAS
`unit_fortify` candidates before outcomes are known. The join is deliberately
non-authorizing:

- feature queries contain context and provenance but no outcome;
- approved and consolidated reports are loaded only after structural-hash,
  file-hash, acceptance, cohort-completeness, and authority checks;
- comparison is confined to the approved action category;
- the global FDAS winner and category-local baseline winner are recorded
  separately;
- incomplete prediction coverage withholds a hypothetical winner;
- truth, readout, policy, and action-selection authority are always false.

The live profile is
`profile/fdas_manifest_defense_actor_persistence_candidate_impact_shadow.json`.
It adds only the versioned
`induced_rule_candidate_impact_shadow: shadow-live` capability and exact input
artifact identities. The existing learning configuration still has
`induced_rule_readout_enabled: false`.

## Diagnostic action-effect boundary

The replay exposed an existing semantic boundary: FreeCiv's compiled ruleset
does not declare an exact `unit_fortify` action effect. FDAS therefore marks
the candidate with the sole blocker `uncompiled-action-effect`, routes its
nonzero achievement pressure through `expand`, and gives it zero assumed
action success.

PR32 does not relabel that effect as ruleset truth. For a snapshot-current,
exact legal candidate whose *only* blocker is `uncompiled-action-effect`, the
shadow analyzer may use:

```text
diagnostic pressure × declared goal effect × approved outcome probability
```

as a counterfactual transition-value component. Any additional blocker keeps
the component unavailable. This bridge exists only in the candidate-impact
diagnostic and cannot alter the emitted PF schedule or downstream action.

## Frozen replay result

The clean-source runner evaluated all 38 replayable captured snapshots twice.
Both passes were byte-identical and all ten acceptance checks passed.

| Measure | Result |
|---|---:|
| Replay evaluations | 38 |
| Candidate rows | 101 |
| Multi-candidate category evaluations | 29 |
| Complete prediction coverage | 21 / 38 |
| Candidate rows with nonzero contextual priority delta | 80 / 101 |
| Approved single-rule readouts | 53 |
| Compatible overlapping-rule readouts | 27 |
| Explicit no-match abstentions | 21 |
| Counterfactual category-winner changes | 0 |
| Truth/readout/policy/action changes | 0 |

Thirteen category-local baseline winners were also the global FDAS winner;
in 25 evaluations another action category won globally. The latter cases are
still scientifically useful category comparisons and are not represented as
global action changes.

## Interpretation

The approved model changes estimated transition value, but not candidate
ordering. This is not a controller failure. The retained PR30 rules are
dominated by city production, city size, economy, and visible-threat context.
Candidates in the same decision often share those features, so they receive
the same calibrated delta. The earlier actor-specific conjunctions were
structurally redundant on their training population and correctly removed;
the data did not establish actor-level differentiation.

The next calibration increment therefore needs candidate-specific evidence,
not flow retuning. It should record complete choice sets, keep nonselected
outcomes censored rather than treating them as failures, stratify by lifecycle
and action category, and gather enough independent selected-actor variation to
estimate actor-specific realized relief with uncertainty. Only then can a
fresh preregistered cohort meaningfully test candidate recall and rank changes.

## Reproduction

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
PYTHONPATH=src:benchmarks:scripts/freeciv \
python3 scripts/freeciv/evaluate_fdas_candidate_impact_replay.py \
  --require-clean-source \
  --output docs/freeciv/evidence/fdas-pr32-candidate-impact-replay.json
```

The machine-readable report has structural hash
`17f9c970dcf2fedc00e1e9ad4cf30ea8d4dca423e20e54a3e9d42ba6872826ff`
and was produced from clean commit
`75b907e1191a4b9d262b2ae2d320bc3618d6ff9d`.
