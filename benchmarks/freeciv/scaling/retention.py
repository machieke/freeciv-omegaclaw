"""Retained-revision, expiry-cycle, GC, and current-RSS diagnostics."""

import gc
import os
from dataclasses import dataclass
from types import SimpleNamespace

from freeciv_agent.state.atomspace.store import (
    DependentAtomSpaceRevision,
    DependentAtomSpaceStore,
)

from .atomspace_generator import benchmark_registry, build_atomspace_case


def current_rss_bytes():
    """Read current RSS rather than the monotone ru_maxrss high-water mark."""
    try:
        with open("/proc/self/statm", "r") as handle:
            resident_pages = int(handle.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return None


@dataclass(frozen=True)
class RetentionCycleResult:
    cycles: int
    retention: int
    retained_revision_counts: tuple
    retained_scope_counts: tuple
    post_gc_rss_bytes: tuple
    maximum_retained_revisions: int
    maximum_retained_scopes: int
    revision_leak: bool
    scope_leak: bool
    plateau_rss_drift_fraction: object
    rss_plateau_within_5_percent: object


def _snapshot(case, cycle):
    return SimpleNamespace(
        identity=SimpleNamespace(
            game_id="scaling-retention",
            source_seq=cycle),
        player_id=0,
        snapshot_id=case.snapshot_id,
        turn=cycle,
    )


def run_retention_cycles(
        atom_count, scope_count, cycles=100, retention=4,
        seed=1729, topology="local"):
    for value, name in (
            (cycles, "retention cycles"),
            (retention, "revision retention")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("{} must be positive".format(name))
    store = DependentAtomSpaceStore(
        predicate_registry=benchmark_registry(),
        revision_retention=retention,
        maximum_atoms=atom_count,
    )
    revision_counts = []
    scope_counts = []
    rss_values = []
    for cycle in range(cycles):
        case = build_atomspace_case(
            atom_count, scope_count, 1, topology,
            seed=seed + cycle, insertion_order="canonical")
        revision = DependentAtomSpaceRevision(
            revision_id=case.revision_id,
            snapshot_id=case.snapshot_id,
            records=case.records,
            scopes=case.scopes,
            build_hash=case.revision_id[len("fdas-revision-"):],
            dependency_index=case.dependency_index,
        )
        store.publish(_snapshot(case, cycle), revision)
        del case
        del revision
        gc.collect()
        revision_counts.append(store.retained_revision_count)
        scope_counts.append(store.retained_scope_count)
        rss_values.append(current_rss_bytes())
    maximum_revisions = max(revision_counts)
    maximum_scopes = max(scope_counts)
    plateau = tuple(value for value in rss_values[max(retention, cycles // 2):]
                    if value is not None)
    if len(plateau) >= 2:
        baseline = float(min(plateau))
        drift = (max(plateau) - min(plateau)) / max(1.0, baseline)
        within = drift < 0.05
    else:
        drift = None
        within = None
    return RetentionCycleResult(
        cycles=cycles,
        retention=retention,
        retained_revision_counts=tuple(revision_counts),
        retained_scope_counts=tuple(scope_counts),
        post_gc_rss_bytes=tuple(rss_values),
        maximum_retained_revisions=maximum_revisions,
        maximum_retained_scopes=maximum_scopes,
        revision_leak=maximum_revisions > retention,
        scope_leak=maximum_scopes > retention * scope_count,
        plateau_rss_drift_fraction=drift,
        rss_plateau_within_5_percent=within,
    )
