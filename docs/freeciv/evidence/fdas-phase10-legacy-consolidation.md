# FDAS Phase 10 legacy consolidation audit

Status: all legacy behavior retained; no removal is authorized.

`profile/fdas_legacy_replacements.json` inventories the legacy Impact and atom
projection branches, their exact replacement capabilities, replacement tests,
strategic policy defaults, and rollback contracts. The checked-in manifest
requests `retain` for every branch because all FDAS capabilities remain
`component-only`.

`LegacyConsolidationAudit` fails closed if removal is requested without every
replacement capability at `engine-live`, every named replacement test in the
verified passing set, and an available rollback identity. Passing tests alone
cannot override an insufficient capability status, and promoted capability
strings alone cannot override missing tests or rollback.

The current result is therefore deliberate: no priority table, research path,
action branch, exact grounding, safety check, or legacy projection is deleted.
This preserves the legacy rollback path while shadow and empirical evidence
are still absent. Structural file decomposition may proceed independently, but
semantic behavior removal remains blocked by this audit.

Coverage is in `Autotests/test_freeciv_fdas_consolidation.py`.
