# FDAS Phase 10 activation hardening

Status: passed; default remains component-only with no policy authority.

The strict configuration validator now requires both an exact capability and
an aggregate manifest promotion before accepting authority. A synthetic
bounded profile must set `policy_authority=true` and aggregate status at least
`bounded-authority`; changing individual capability strings is insufficient.

Domain authority additionally requires world, empire, operation, explanation,
and domain-specific projection flags. Schema 1.1 gives city-region,
route-corridor, settlement-site, population-recovery, transport, and combat
their own projection switches and manifest capability checks; the former
region umbrella no longer enables all six. Expansion, transport, combat, local
movement, and research fail closed when any exact projection is absent. Local
movement requires both region and corridor capability at bounded authority,
and expansion additionally requires region, corridor, settlement, and recovery
capabilities. Research also requires the generic engine, technology
compatibility path, ruleset projection, and both generic/ruleset capabilities
at bounded authority.

Cold verification cannot be set to zero before aggregate `engine-live`
acceptance. Contextual conductance and induced-rule readout retain their
independent attribution, holdout, quarantine, and bounded-capability gates.

Coverage is in `Autotests/test_freeciv_fdas_config.py`; 24 focused
configuration/manifest tests passed at this boundary.
