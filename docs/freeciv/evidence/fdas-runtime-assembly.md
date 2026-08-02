# FDAS runtime assembly and engine shadow seam

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Activation level: component-only manifest; checked default disabled; no policy authority

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
- FDAS configuration/manifest schema 1.1 separates city-region,
  route-corridor, settlement-site, population-recovery, transport, and combat
  projection switches. Each switch is independently capability-bound; the
  former `region` umbrella no longer activates the other five projectors.
- Ruleset projection is materialized once into an immutable digest-bound static
  revision. Snapshot projection remains a separate coordinated revision over
  authoritative state and declared durable sources.
- The enabled checked projector set consists of city/economy/research plus the
  read-only durable operation view. Unit, all six focused projection domains,
  belief, learning, and every authority slice remain independently
  configurable and off in the checked profile.
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
- Enabled engine runs publish bounded causal revision and post-legacy shadow
  decision events, atom/scope counts, projection latency, and shadow-readout
  latency. Revision-start events are causally linked to the authoritative
  `state_snapshot` event. The readout returns no executable action.
- Deterministically sampled incremental/cold verification fails the runtime
  closed on any canonical mismatch.
- A successful sampled check publishes the already-verified incremental
  revision through an optimistic prior-revision guard. It no longer discards
  that revision and performs a third projection before publication.

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

`profile/dependent_atomspace_shadow_sampled.yaml` is the explicit engine
experiment profile. It enables all implemented rich projectors, verifies a
deterministic 5% transition sample against cold projection, and keeps every
authority flag false. `FREECIV_FDAS_CONFIG_PATH` selects it without editing the
base harness; the resolved declaration and hash are part of run identity.

## Verification

- Focused FDAS suite: `180 passed in 38.04s`.
- Configuration, runtime, and harness integration: `140 passed in 297.14s`.
- Complete FreeCiv acceptance suite: `1,277 passed in 380.54s`.
- Enabled checked projector assembly was exercised against the compiled
  Civ2Civ3 ruleset and authoritative contract fixture.
- Strict captured replay exercised 38 snapshots and 37 transitions with 100%
  cold verification and no mismatches.
- The schema-1.1 diagnostic replay retained 37/37 equivalence. Its strict
  incremental-plus-cold projection measured 471.55 ms mean and 846.20 ms p95;
  this path includes both builds by design and is not a live-controller timing.
- One predeclared engine-live shadow game completed 30 turns with 52 rich
  revisions and 51 non-authorizing shadow decisions.
- `git diff --check`: clean.

## Remaining empirical gates

This wiring does not promote the manifest to `shadow-live`. The diagnostic
captured run and one engine smoke demonstrate the seam, but promotion still
requires broader engine evidence that demonstrates:

1. ordinary-turn and tail projection latency within the controller gate;
2. stable atom, support, scope, grounding, and event volumes;
3. zero cold/incremental mismatches and stale-dependency attempts;
4. complete candidate/safety divergence reports for each activated slice; and
5. no action-selection or execution-gate change while authority is disabled.

No score, win-rate, gameplay-improvement, bounded-authority, or engine-live
claim is made by this component acceptance.
