"""M2 authoritative snapshots, atom synchronization, and grounded accessors."""
"""Authoritative FreeCiv snapshot bridge and crisp state namespaces."""

from .atoms import Atom, SnapshotAtomspaces, build_atomspaces
from .dto import ContractError, ProxyStateDTO
from .grounded import GroundedCheck, GroundedRegistry
from .snapshot import (AuthoritativeSnapshot, CityState, EconomicState,
                       ResearchState, SnapshotIdentity, UnitState)
from .store import SnapshotConflict, SnapshotStore
from .summary import QueryStateSummary, StateSummaryService

__all__ = [
    "Atom", "AuthoritativeSnapshot", "CityState", "ContractError",
    "EconomicState", "GroundedCheck", "GroundedRegistry", "ProxyStateDTO",
    "QueryStateSummary", "ResearchState", "SnapshotAtomspaces",
    "SnapshotConflict", "SnapshotIdentity", "SnapshotStore",
    "StateSummaryService", "UnitState", "build_atomspaces",
]
