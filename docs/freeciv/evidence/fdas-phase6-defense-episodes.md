# FDAS Phase 6 evidence: compact defense episodes

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `episode_attribution=component-only`  
Policy authority: disabled

## Realized scope

This increment implements the compact before/after evidence boundary for
city-defense operations:

- `DecisionEpisode` carries operation/action identity, before/after FDAS
  revisions, goals, context, source atoms/supports, grounding/prediction/resource
  identities, validation hash, execution event, observed delta, attributed
  effects, realized relief, outcome status, and provenance;
- `DecisionEpisodeStore` provides deterministic ordering/digests, guarded
  lifecycle transitions, idempotent identical replay, atomic persistence, and
  quarantine on corrupt or wrong-identity loads;
- immutable identity covers every causal input, not only the operation/action,
  so changed validation or source evidence cannot overwrite an episode;
- `FdasDefenseEpisodeRecorder` starts only from a current legal-bound defense
  action and an existing operation record;
- server acceptance is recorded without claiming an effect;
- a changed actor tile is an immediate effect without automatic goal relief;
- exact occupation of the intended city (or exact fortification state for that
  schema) can produce positive goal relief;
- unchanged state remains `delayed-effect-pending` until the caller explicitly
  closes the observation window, after which it can become
  `no-effect-observed`;
- actor disappearance is `confounded-unattributable`, never successful defense;
- terminal replay is idempotent only for the same after revision and rejects a
  conflicting revision;
- `EpisodeProjector` materializes bounded, durable-compact episode scopes with
  control-model authority and exact episode-revision dependencies;
- projected relations expose before/after revisions, action, operation,
  validation, execution event, source evidence, groundings, resource claims,
  attributed effects, outcome, and goal relief without putting numeric relief
  into ordinary atom terms.

## Verification

Focused episode and manifest/operation projection tests cover:

- acceptance/effect/relief separation;
- multi-observation progression and terminal idempotency;
- pending versus closed-window no-effect;
- unattributable actor disappearance;
- persistence round trip and corruption quarantine;
- bounded episode scope projection and catalog parity.

The complete FDAS regression is run before committing this increment.

## Claim boundary

Episodes are evidence records, not truth mutation or learning authority. This
increment does not update conductance, train transition models, induce rules,
authorize actions, or support a gameplay/score claim.
