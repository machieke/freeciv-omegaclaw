"""M2 authoritative snapshots, atom synchronization, and grounded accessors."""
"""Authoritative FreeCiv snapshot bridge and crisp state namespaces."""

from .atoms import Atom, SnapshotAtomspaces, build_atomspaces
from .dto import ContractError, ProxyStateDTO
from .grounded import GroundedCheck, GroundedRegistry
from .snapshot import (AuthoritativeSnapshot, CityState, EconomicState,
                       CombatActionProbabilityState, CombatProbabilityState,
                       MovementRouteState, ResearchState, SnapshotIdentity,
                       ResearchOptionState, UnitState)
from .store import SnapshotConflict, SnapshotStore
from .replay import SnapshotReplayError, snapshot_from_event
from .summary import QueryStateSummary, StateSummaryService

__all__ = [
    "Atom", "AuthoritativeSnapshot", "CityState", "ContractError",
    "EconomicState", "GroundedCheck", "GroundedRegistry",
    "CombatActionProbabilityState", "CombatProbabilityState",
    "MovementRouteState", "ProxyStateDTO",
    "QueryStateSummary", "ResearchOptionState", "ResearchState", "SnapshotAtomspaces",
    "SnapshotConflict", "SnapshotIdentity", "SnapshotStore",
    "SnapshotReplayError", "snapshot_from_event",
    "StateSummaryService", "UnitState", "build_atomspaces",
]
