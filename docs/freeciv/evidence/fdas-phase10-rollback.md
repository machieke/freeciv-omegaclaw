# FDAS Phase 10 rollback contract

Status: tested and available through the declared 2.0 schema boundary.

`SnapshotStore` now accepts an immutable construction-time `atomspace_mode`:

- `dependent` is the unchanged default. It atomically publishes the snapshot,
  typed dependent revision, and exact legacy compatibility view.
- `legacy` bypasses dependent revision construction/publication and invokes the
  frozen historical projection directly.

Both modes produce the identical public `SnapshotAtomspaces` view. Legacy mode
has no dependent revision to lease or query, making its reduced capability
explicit rather than fabricating an FDAS revision. The rollback contract and
identities are versioned in `profile/fdas_rollback.json`.

Coverage in `Autotests/test_freeciv_state_bridge.py` proves byte-compatible
projection output, dependent-revision presence in the default mode, absence in
rollback mode, lease failure, and rejection of unknown modes.
