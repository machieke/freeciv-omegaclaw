# FDAS PR101 retained-capacity decision-safe readout preregistration

Date: 2026-08-06

## Question

PR101 asks whether the exact PR99 retained-capacity transition model, after its
PR100 out-of-sample confirmation, is sufficient to support a protected,
decision-safe comparison between the scalar-PF selected retained queue and a
different current retained-queue candidate.

This is a feasibility and mechanics gate, not a gameplay experiment.  It is
fixed before implementing the readout or inspecting any new engine outcome.
No engine cohort will start unless the frozen evidence can support at least
one decision-safe comparison in principle.

## Frozen inputs

- PR99 model report:
  `docs/freeciv/evidence/fdas-pr99-retained-capacity-transition-model.json`;
- model result hash:
  `909e8170d9dc797f69b71337243633ddd5fd5e007a7627c44e150d0a05439a6f`;
- PR100 confirmation report:
  `docs/freeciv/evidence/fdas-pr100-retained-capacity-transition-confirmation.json`;
- confirmation structural hash:
  `4f977bc166836202fe70273fbb7ded843f2500bfc39992e22ddd52654264d829`;
- confirmation report SHA-256:
  `5587d5a9fd14c87b690a627d56886768b43decee9ca092da8546782c47b8b2a3`.

The model may only be loaded from the exact frozen report.  PR101 may not
refit it, change its hierarchy, narrow an interval, pool discovery and
confirmation rows, or reinterpret a censored row.

## Required readout semantics

The implementation will introduce a typed shadow-only readout over exact
retained-authoritative-queue candidates.  It must:

- preserve the scalar-PF selected operation and candidate surface;
- require the baseline and every potentially preferred alternative to be a
  current, byte-identical legal production binding whose grounded production
  assembly starts at the completion-observation step;
- use durable goal relief as the controller-facing value and exact-product
  effect only as a non-inferiority guard;
- require numerical estimates for both targets on every compared candidate;
- require the alternative durable-relief lower bound to be strictly greater
  than the baseline durable-relief upper bound;
- require the alternative exact-product lower bound to be no lower than the
  baseline exact-product lower bound;
- rank separated alternatives deterministically by relief lower bound,
  relief point estimate, product lower bound, scalar priority, then operation
  identity;
- expose selection role explicitly; and
- abstain when transition value for nonselected candidates has not been
  independently validated.

The readout is diagnostic only.  `action_selection_changed`,
`pressure_selection_changed`, `policy_authority`, `readout_authority`, and
`truth_mutated` must remain false.  A counterfactual preference is not an
authorization.

## Frozen feasibility audit

The audit independently reloads and validates both frozen reports, enumerates
every numerically usable PR99 interval for both targets, and checks all ordered
pairs of durable-relief intervals.  It also verifies whether the frozen
discovery and confirmation evidence contains an explicit nonselected-candidate
selection role and outcome population.

The progression gate requires all of the following:

1. both source artifacts match their frozen identities and PR100 is accepted;
2. at least two numerically usable durable-relief bins exist;
3. at least one ordered pair has strict durable-relief interval separation;
4. at least one separated pair also passes exact-product lower-bound
   non-inferiority at a compatible hierarchy signature; and
5. a disjoint, explicitly labeled nonselected-candidate outcome population has
   passed calibration and coverage gates.

The report must retain counts and identities for all usable bins, all ordered
pair checks, and the exact failed requirements.  Two complete invocations must
be byte-identical.

## Stop rule and claim boundary

If either interval separation or nonselected-candidate validation is absent,
PR101 must return `not-ready`, the live engine gate stays closed, and the
readout must abstain for every policy-divergent comparison.  The next admissible
research step would be a separately preregistered observation-only candidate
surface and outcome collection with selection roles recorded prospectively.

A passing mechanics audit would authorize only a fresh claim-ineligible
shadow opportunity cohort.  PR101 cannot authorize a pressure selection,
production action, policy change, score claim, or win-rate claim.
