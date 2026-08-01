import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.state.atomspace import (  # noqa: E402
    AtomKey,
    AtomNamespace,
    AtomRecord,
    AtomQuery,
    AtomSpaceDiagnostics,
    AtomSpaceTransaction,
    AuthorityClass,
    DependencyKey,
    DependencyRef,
    DependentAtomSpaceRevision,
    EntityRef,
    ScopeSpec,
    SupportRecord,
    SymbolRef,
    ValidityInterval,
    legacy_predicate_registry,
)


def _revision(activity="fortified"):
    validity = ValidityInterval("diagnostic-snapshot", 4, 4, 1)
    scope = ScopeSpec(
        "scope:diagnostic:empire", "empire", 0,
        (EntityRef("player", "0"),), (), (),
        ("unit-activity",), frozenset((AtomNamespace.AUTHORITATIVE,)),
        20, 20, 20, 2, "snapshot", validity)
    key = AtomKey(
        AtomNamespace.AUTHORITATIVE, "unit-activity",
        (EntityRef("unit", "7"), SymbolRef("activity", activity)),
        scope.scope_id)
    dependency = DependencyRef(
        DependencyKey("snapshot-field", "unit:7", "activity"),
        structural_hash({"activity": activity}))
    support = SupportRecord.create(
        "diagnostic-projector", "1.0", key.to_dict(), (dependency,),
        {"activity": activity}, ("snapshot:diagnostic",))
    record = AtomRecord.create(
        key, AuthorityClass.ENGINE_AUTHORITATIVE,
        {"crisp": True}, validity, (support,), ("snapshot:diagnostic",))
    transaction = AtomSpaceTransaction(
        "diagnostic-snapshot", legacy_predicate_registry(), (scope,))
    transaction.apply(record)
    revision_id = transaction.commit()
    return DependentAtomSpaceRevision(
        revision_id, "diagnostic-snapshot", transaction.records,
        transaction.scopes, revision_id.split("fdas-revision-", 1)[1],
        transaction.dependency_index)


def test_operator_stats_scopes_explain_and_dependency_views_are_deterministic():
    revision = _revision()
    atom = revision.records[0]
    diagnostics = AtomSpaceDiagnostics(revision, ({
        "turn": 4, "selected_operation_id": "operation-shadow",
        "authority": "diagnostic-only",
    },))

    stats = diagnostics.stats()
    assert stats["atom_count"] == 1
    assert stats["support_count"] == 1
    assert stats["atoms_by_namespace"] == {"authoritative": 1}
    assert stats["structural_hash"] == structural_hash(
        dict((key, value) for key, value in stats.items()
             if key != "structural_hash"))
    assert diagnostics.scopes()[0]["atom_ids"] == [atom.atom_id]
    assert diagnostics.explain(atom.atom_id)["atom_id"] == atom.atom_id
    assert diagnostics.dependencies(atom.atom_id)[0][
        "derivation_id"] == "diagnostic-projector"
    dependency = atom.supports[0].dependencies[0].key
    assert diagnostics.dependents(dependency)[0][
        "output_atom_ids"] == [atom.atom_id]
    assert diagnostics.shadow_decision(4)[
        "selected_operation_id"] == "operation-shadow"
    with pytest.raises(KeyError, match="no FDAS shadow decision"):
        diagnostics.shadow_decision(5)


def test_operator_why_not_and_revision_diff_do_not_invent_truth():
    first = _revision("fortified")
    second = _revision("idle")
    diagnostics = AtomSpaceDiagnostics(first)
    proved = diagnostics.why_not(AtomQuery(
        predicate="unit-activity",
        namespace=AtomNamespace.AUTHORITATIVE,
        arguments=(EntityRef("unit", "7"),
                   SymbolRef("activity", "fortified")),
        scope_id="scope:diagnostic:empire"))
    unknown = diagnostics.why_not(AtomQuery(
        predicate="unit-activity",
        namespace=AtomNamespace.AUTHORITATIVE,
        arguments=(EntityRef("unit", "7"), SymbolRef("activity", "idle")),
        scope_id="scope:diagnostic:empire"))
    difference = diagnostics.diff(second)

    assert proved["status"] == "PROVED"
    assert unknown["status"] == "UNKNOWN"
    assert unknown["unknown"] is True
    assert len(difference["added_atom_ids"]) == 1
    assert len(difference["removed_atom_ids"]) == 1
    assert difference["changed_atom_ids"] == []


def test_operator_rejects_untyped_queries_and_dependencies():
    diagnostics = AtomSpaceDiagnostics(_revision())
    with pytest.raises(TypeError, match="AtomQuery"):
        diagnostics.why_not("unit-activity")
    with pytest.raises(TypeError, match="atom ID or DependencyKey"):
        diagnostics.dependents(object())
