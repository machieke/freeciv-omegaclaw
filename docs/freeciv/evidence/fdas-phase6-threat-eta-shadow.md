# FDAS Phase 6 evidence: uncertainty-preserving threat ETA

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `unit_domain_projection=component-only`  
Policy authority: disabled

## Realized scope

This increment adds deadline context without promoting a geometric estimate to
authoritative truth:

- `defense.visible-threat-eta(city, enemy-unit)` is a typed `control_model`
  grounding with a 0.45 confidence cap and mandatory residual unknown mass;
- the estimate uses exact current coordinates/topology and the compiled ruleset
  movement rate, but labels its basis as a geometric lower bound rather than a
  server path result;
- the grounding returns earliest modeled attack turn, ETA, distance, movement
  rate, confidence, and 0.55 unknown mass with field- and ruleset-level
  dependencies;
- `city-threat-arrival-estimate` is projected in the belief namespace with
  `uncertain_belief` authority, never in authoritative or deterministic state;
- exact-topology absence suppresses both visible-threat distance and ETA
  estimate instead of manufacturing a fallback fact;
- where an exact native friendly reinforcement ETA also exists, a positive
  `city-threat-arrives-before-defense(city, enemy, defender)` belief is emitted
  only when the modeled enemy lower bound precedes the server-backed friendly
  arrival;
- the deadline comparison retains the threat model's confidence cap/unknown
  mass and combines exact route plus modeled threat dependencies;
- absence of that positive comparison is not represented as safety or as proof
  that defense arrives first.

## Verification

Focused tests verify the control-model grounding contract, exact expected ETA,
belief namespace/authority, confidence cap, residual unknown mass, topology
refusal, and a modeled threat-before-exact-reinforcement relation. The complete
FDAS regression is run before committing this increment.

## Claim boundary

The ETA is a conservative decision input, not a fact about hidden enemy intent,
terrain reachability, or actual arrival. It cannot authorize an action and does
not establish defense effectiveness or score improvement.
