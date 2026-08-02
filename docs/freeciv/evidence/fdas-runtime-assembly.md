# FDAS runtime assembly and engine shadow seam

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Activation level: component-only; checked profile disabled; no policy authority

## Realized boundary

The rich FDAS components now have one fail-closed application construction
path instead of being assembled only by tests:

- `load_runtime_declaration()` loads and validates the exact FDAS profile and
  capability manifest, then gives the pair a structural declaration hash.
- Every FreeCiv harness manifest carries that complete declaration, so changing
  an FDAS flag, capability level, or profile source changes the behavioral run
  identity.
- `build_runtime()` constructs the exact configured projector set. It refuses
  enabled ruleset, operation, belief, or episode projection when the associated
  compiled IR or durable store source is absent.
- Ruleset projection is materialized once into an immutable digest-bound static
  revision. Snapshot projection remains a separate coordinated revision over
  authoritative state and declared durable sources.
- The enabled checked projector set consists of city/economy/research plus the
  read-only durable operation view. Unit, region, belief, learning, and every
  authority slice remain independently configurable and off in the checked
  profile.
- Focused scopes pass through the deterministic `ScopeActivator`; each opened
  detail scope records its reason, funding identity, priority, and snapshot
  parent.
- Global and per-scope atom caps, rule-fire caps, grounding caps, expansion
  depth, retention, and focused-scope TTL are applied from the validated
  configuration. An over-budget transaction is rejected before publication.
- `SnapshotStore` can atomically rematerialize a current snapshot when durable
  operation, belief, or episode sources advance without a new engine packet.
- Planner operation stores expose one immutable, deduplicated read-only record
  view. Reading it cannot create a lifecycle or alter planner behavior.
- Enabled engine runs publish bounded causal revision events and atom/scope
  counts plus projection latency. Revision-start events are causally linked to
  the authoritative `state_snapshot` event.
- Deterministically sampled incremental/cold verification fails the runtime
  closed on any canonical mismatch.

## Checked default

`profile/dependent_atomspace.yaml` remains:

```text
enabled: false
shadow_enabled: true
authority_enabled: false
all domain_authority flags: false
all learning flags: false
```

Consequently, ordinary checked runs retain the legacy decision path and do not
emit rich FDAS revision events. The runtime seam is present and manifest-bound,
but activation remains an explicit experiment/deployment step.

## Verification

- Complete FreeCiv suite: `1,258 passed in 377.13s`.
- All FDAS tests: `166 passed in 38.29s`.
- Runtime, events, configuration, state bridge, and harness integration:
  `166 passed in 296.84s`.
- Focused runtime/store/event regression: `61 passed in 20.94s`.
- Enabled checked projector assembly was exercised against the compiled
  Civ2Civ3 ruleset and authoritative contract fixture.
- `git diff --check`: clean.

## Remaining empirical gates

This wiring does not promote the manifest to `shadow-live`. Promotion still
requires an enabled captured/engine run that demonstrates:

1. ordinary-turn and tail projection latency within the controller gate;
2. stable atom, support, scope, grounding, and event volumes;
3. zero cold/incremental mismatches and stale-dependency attempts;
4. complete candidate/safety divergence reports for each activated slice; and
5. no action-selection or execution-gate change while authority is disabled.

No score, win-rate, gameplay-improvement, bounded-authority, or engine-live
claim is made by this component acceptance.
