# GDO-2B Combat Input Audit

Status: blocking audit complete; deterministic combat subset not yet approved
Policy effect: none
Audited repository commit: `97ff07b`

## Decision

The current boundary has enough data to identify some exact advertised combat
actions and packet-visible attacker/target units. It does not have enough data
to reproduce Freeciv combat modifiers or defender selection. The current fixed
`tactical_attack` utility must not be exposed as a probability.

All combat estimates must abstain until the missing context for a declared
deterministic subset is supplied and parity-tested.

## Attacker and defender state

| Input | Own attacker | Visible defender | Current status |
|---|---:|---:|---|
| Stable unit ID/owner/type/type ID | yes | yes | retained |
| Tile/x/y | yes | yes | retained |
| Current HP | yes | yes | retained when packet supplies it |
| Movement points | yes | often absent | defender moves are irrelevant to immediate mechanics |
| Activity/fortification | yes | yes | string retained, but fortification duration/modifier is absent |
| Veteran level | input contains it | input contains it | retained after the audit correction |
| Transported/carrier state | input contains it | input may contain it | retained after the audit correction |
| Build/shield cost | ruleset IR | ruleset IR | available by normalized unit type |
| Attack/defence/HP/firepower | ruleset IR | ruleset IR | available by normalized unit type |

Short foreign-unit packets may omit movement and other fields. Missing values
must remain missing; they cannot be replaced by own-unit defaults.

## Terrain, city, and effect context

Known tile records may contain terrain and extra IDs, but the snapshot has no
authoritative ID-to-ruleset mapping. The current ruleset IR does not compile:

- terrain defence bonuses;
- city/fortification effects;
- building effects such as walls;
- river/base/extra modifiers;
- action enablers;
- unit-class combat flags;
- veterancy power and HP modifiers;
- nation/government or ruleset effect tables.

Only owned cities are retained, so an attacked foreign city and its buildings
cannot currently be reconstructed from `AuthoritativeSnapshot`.

## Action and target availability

Canonical legal actions may include:

- `unit_attack`;
- `unit_suicide_attack`;
- `unit_bombard`;
- `unit_capture`;
- `unit_conquer_city`;
- `unit_wipe`.

Targets may be expressed by target-unit ID or coordinates. The Impact planner
already requires a packet-visible target before producing
`tactical_attack`. That is a candidate-generation safety condition, not a
combat-outcome model.

The current legal action does not declare:

- selected defender when several defenders share a tile;
- combat power after all effects;
- number of rounds;
- bombard limits and collateral;
- capture eligibility after combat;
- post-combat movement or exposure.

## Retaliation and strategic exposure

Immediate one-versus-one mechanics and post-action strategic exposure must be
separate estimates. Counterattack risk depends on future and hidden opponent
actions, so it begins as heuristic/calibrated data with residual unknown mass;
it cannot be assigned deterministic combat authority.

## Initially supportable subset

A future deterministic open-field subset may be supported only when all of the
following are explicit:

- one advertised attacker and one selected packet-visible defender;
- attacker/defender base statistics and current HP;
- veteran levels and activity;
- target terrain and city/base/building context;
- all applicable effect multipliers, or an authoritative declaration that no
  modifiers apply;
- exact action kind and post-action location semantics;
- ruleset digest and snapshot validity.

No current captured GDO fixture proves that complete context. Current combat
candidates therefore remain `ABSTAIN`. Synthetic unmodified battles may test
the independently written probability core, but they are not engine parity
evidence.

## Correction status before parity work

1. Pass `RulesetIR` to domain models: complete.
2. Retain veteran and transport fields in `UnitState`: complete.
3. Add typed combat rule inputs rather than reading candidate utility:
   complete for the declared unmodified-duel subset.
4. Add deterministic mechanics separate from post-action risk and goal relief:
   clean-room finite-duel mechanics complete; post-action risk remains
   explicitly unmodelled.
5. Add explicit multi-defender and unsupported-action abstention codes:
   complete.
6. Add a native differential adapter and generated corpus with engine/ruleset
   identities: process boundary and runner complete; native executable/corpus
   pending.
7. Establish Brier/log-loss baselines from engine outcomes before any
   calibrated authority.

## Licensing boundary

The implementation may consume protocol facts and independently parse factual
ruleset data. It must not copy or mechanically translate Freeciv GPL combat or
pathfinding implementation code into this MIT repository. A native comparator,
if used, remains a separate installed process.

## Exit status

The audit and bounded clean-room finite-duel shadow kernel are complete.
GDO-2B parity and calibration gates remain open. Its mapping to Freeciv is
therefore labelled `HEURISTIC`; unsupported current candidates abstain, and
live combat ordering is unchanged.
