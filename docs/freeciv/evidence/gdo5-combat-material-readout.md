# GDO-5 material-aware combat readout

Status: retained replay mechanism passed; fresh engine outcome claim pending.

## Correction

The first bounded combat authority ranked atomic attacks by the lower bound of
Freeciv's native attack-success interval. That interval is valid attacker-win
evidence for an attack, but win probability alone does not distinguish a good
trade from risking a high-value attacker for a low-value defender.

The corrected readout binds the native interval to:

- the exact selected defender;
- current attacker and defender HP;
- ruleset hit-point maxima; and
- ruleset shield build costs.

For attacker-win interval `[l, u]`, attacker remaining value `A`, and defender
remaining value `D`, the terminal-destruction intervals are:

```text
enemy terminal loss    = [lD, uD]
friendly terminal loss = [(1-u)A, (1-l)A]
terminal advantage     = [lD - (1-l)A, uD - (1-u)A]
```

The scheduler bid is `max(0, terminal_advantage.lower)`. A missing ruleset
value or non-positive refreshed bid fails closed before policy authority.
Damage retained by a surviving unit is not exposed by the native probability
packet, so the artifact labels survivor damage as unmodeled and makes only a
terminal-destruction-value claim.

## Retained replay result

The five captured, player-visible combat snapshots in
`combat_operations_native_160_manifest.json` were replayed with the frozen
Civ2Civ3 ruleset.

- all five material-aware decisions or rejection maps differ from the retained
  probability-only source;
- turns 68, 69, and 70 contain no positive atomic trade and select none;
- both turn-72 snapshots retain one positive atomic operation;
- non-positive operations selected: zero;
- duplicate target selections: zero;
- incomplete participant reservations: zero;
- material-aware captured-replay p95: below 20 ms;
- policy authority in replay: disabled.

This result supplies an evidence-backed explanation for part of the earlier
negative engine cohort: several attacks that had high enough win probability
to be selected did not have positive grounded terminal material value.

## Reproduction

```bash
python3 scripts/run_gdo_combat_operation_replay.py
python3 scripts/run_gdo_combat_lifecycle_replay.py
python3 scripts/run_gdo_combat_captured_replay.py
python3 scripts/run_gdo_combat_candidate_readout_replay.py
PYTHONPATH=src pytest -q Autotests/test_gdo_combat_operation_replay.py
```

The self-hashed reports are:

- `benchmarks/gdo/gdo5_combat_operation_synthetic_diagnostic.json`
- `benchmarks/gdo/gdo5_combat_operation_lifecycle_diagnostic.json`
- `benchmarks/gdo/gdo5_combat_operation_captured_diagnostic.json`
- `benchmarks/gdo/gdo5_combat_candidate_readout_diagnostic.json`

## Claim boundary

This is a retained replay mechanism and decision-safety result. It is not a
fresh gameplay, score, or win-rate claim. A fresh disjoint engine pilot must
confirm lower harmful partial attacks or improved target-neutralization value
without an adverse friendly-loss shift before the GDO-5 pilot gate can pass.
