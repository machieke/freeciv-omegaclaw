# GDO captured snapshots

This directory will contain sanitized authoritative snapshot, legal-action, and
ruleset-digest fixtures for the grounded-domain replay corpus.

Required fixture classes:

- immediate city threat;
- multiple cities competing for defenders;
- legal tactical attacks;
- founder/ferry rendezvous;
- production choices;
- research choices.

Implemented corpora:

- `combat_operations_native_160/`: five exact player-visible native-combat
  snapshots with eligible two-actor operations, source identities, native
  probability intervals, and expected shadow schedule decisions. Its sibling
  manifest binds every fixture to the source event stream and structural
  ruleset digest.

Fixtures must contain only information available to the player, record their
source engine/ruleset identity, and include a checksum manifest. No placeholder
fixture is treated as evidence.
