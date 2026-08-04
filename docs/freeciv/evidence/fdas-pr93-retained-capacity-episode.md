# PR93 retained-capacity decision episodes

## Result

The clean fixed-seed engine smoke confirms the observation-only bridge from
PR92 retained-capacity terminal labels into the common FDAS decision-episode
vocabulary. The run completed one of one games with no infrastructure failure
or resume. It encoded two terminal episodes: one exact product with durable
goal relief and one exact product without durable goal relief.

This is a component-mechanics result. It does not claim that the retained
queue caused the outcome, improved controller decisions, improved score, or
improved win rate.

## Frozen semantics

The bridge maps only terminal, exact labels:

- `terminal-no-progress` to `no-effect-observed`;
- durable negative relief to `effect-without-goal-relief`;
- durable positive relief to `goal-relief-observed`.

It records the exact proposal action key, operation digest, RequirementSet,
goal IDs, resource claims, deficit atom, before/after revisions, product
identity, observed conjuncts, and proposal/outcome provenance. It explicitly
records that no queue action was submitted. Prediction IDs are empty and the
execution event is absent.

The episodes are persisted in
`fdas-retained-capacity-decision-episodes.json`, separate from the defense
episode store consumed by contextual conductance and induction. This keeps the
new evidence available for later calibrated research without silently making
it a learning input.

## Engine evidence

- Artifact: `artifacts/freeciv/fdas-pr93-retained-capacity-episode-smoke-v2`
- Seed: `111539`
- Condition: `e_full_loop`
- Horizon: 160 turns
- Source commit: `deea2c1b2c25e7cbf773caaff0ec3fbc4106447f`
- Source dirty: `false`
- Games completed: 1/1
- Infrastructure failures: 0
- Resumed games: 0
- Terminal labels: 2
- Episodes encoded: 2
- `goal-relief-observed`: 1
- `effect-without-goal-relief`: 1
- `no-effect-observed`: 0
- Pending retained-capacity labels: 0

The first attempted smoke, `fdas-pr93-retained-capacity-episode-smoke-v1`, is
preserved as a turn-zero infrastructure failure. It exposed an initialization
ordering defect in which episode-bridge validation read the learning config
before assignment. Commit `deea2c1` moved the existing assignment ahead of
validation without changing gameplay or episode semantics. No evidence from
the failed attempt is used here.

## Strict audit

The PR93 auditor composes the passing PR92 delayed-outcome audit and then
requires all of the following:

1. a typed, manifest/attempt/game-bound separate episode store with a valid
   digest and no quarantine;
2. exactly one episode for every terminal retained-capacity label;
3. byte-exact recomputation of every episode from its proposal and label using
   the production bridge;
4. exactly one causal `episode_opened` event from the corresponding terminal
   outcome event;
5. exact revision, turn, snapshot, payload hash, counter, and incremental store
   digest agreement;
6. empty predictions, absent execution IDs, and false truth, learning, readout,
   transition-value, and policy authority;
7. no episode-ID overlap or downstream reference in the main learning and
   induction episode store.

Synthetic audit tests also reject an authority escape and contamination of the
main learning store. The live report passed twice byte-identically:

- Structural hash:
  `be3a3e511f6af619c11daadaf1bd37263f83b4f256570aa1d9cc7ee519a1a786`
- Report SHA-256:
  `8a6e965afad16b3ed99c2a5527ec1e7eca622c5396fe1ae598a2105014b18ed3`

The machine-readable report is
`docs/freeciv/evidence/fdas-pr93-retained-capacity-episode.json`.

## Validation

The audit-focused suite passed 35 tests. The preceding runtime/config/outcome
suite passed 104 tests after the startup-order correction.

## Next bounded target

Keep these episodes observation-only. Before any learning connection, define a
pre-registered offline dataset and assess whether the extra capacity episodes
improve category- and lifecycle-specific transition calibration on held-out
games. Any future adapter must retain prediction uncertainty and must not
change candidate readout until calibration and decision-safety gates pass.
