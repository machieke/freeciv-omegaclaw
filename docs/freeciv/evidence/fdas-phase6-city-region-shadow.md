# FDAS Phase 6 evidence: bounded city-centered regions

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `region_domain_projection=component-only`  
Policy authority: disabled

## Realized scope

This increment implements the focused region substrate for local defense:

- city-centered region scopes are opened only when exact topology is available
  and either a visible enemy is within the configured radius or a validated
  native movement route names the city as its destination;
- activation is deterministic, capped at eight regions by default, and records
  its policy reason in the diagnostic namespace rather than as world truth;
- each active region has a hard 3,000-atom budget and a deterministic identity
  containing its anchor city, radius, and schema version;
- `tile-in-region` and directed `tile-adjacent` relations use exact wrapped map
  topology and remain local to the focused scope;
- remembered/known map terrain is projected separately as engine-authoritative
  `terrain-kind` data with field-level dependencies;
- `visible-threat-near` remains a positive observation-qualified relation; no
  region or safety fact is produced from enemy absence;
- removing the last activation witness retracts the entire focused scope, and
  incremental materialization remains byte-equivalent to a cold rebuild.

## Verification

The region/unit focused suite passed:

```text
15 passed
```

Fixtures cover missing-topology refusal, a 49-tile wrapped radius-three region,
scope and atom budgets, deterministic active-region limiting, visible-threat
dependencies, native-route activation, and complete incremental retraction.

## Claim boundary

These regions provide bounded causal context only. They do not infer fogged
enemy absence, threat arrival certainty, settlement safety, operation success,
or action authority. Route-corridor and settlement-focused regions remain Phase
7 work.
