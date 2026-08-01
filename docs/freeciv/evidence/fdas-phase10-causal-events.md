# FDAS causal event stream evidence

Status: component-only; bounded and opt-in.

The published V1 event schema now includes the complete FDAS causal event
vocabulary for revision, delta, projection, support, invalidation,
materialization, grounding, derivation, completeness, goals, operations,
pressure, shadow decisions, episodes, conductance, and induced-rule lifecycle.
Every payload carries revision, snapshot, ruleset, component/version, details,
and a structural hash; causal parents remain in the common event envelope.

`AtomSpaceEventEmitter.emit_revision()` emits a bounded revision trace with
explicit start/delta/projection/commit ancestry. Scope activation and budget
rejections can be attached. Atom/support/derivation, operation, and episode
details are capped by `maximum_detail_events`; exhaustion emits an explicit
budget event rather than silently producing an unbounded log.

`emit_component()` exposes the same strict envelope to grounding, goal,
pressure, episode-attribution, conductance, and induction components. It
accepts only registered FDAS event types and an immutable revision. Event
generation observes but does not mutate the revision or grant policy authority.
