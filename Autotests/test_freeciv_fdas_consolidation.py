import copy
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import structural_hash  # noqa: E402
from freeciv_agent.planning import LegacyConsolidationAudit  # noqa: E402


def _json(name):
    with open(os.path.join(REPO, "profile", name), encoding="utf-8") as stream:
        return json.load(stream)


def test_checked_manifest_retains_every_legacy_branch_without_live_evidence():
    fdas = _json("fdas_manifest.json")
    replacements = _json("fdas_legacy_replacements.json")
    report = LegacyConsolidationAudit.evaluate(fdas, replacements)

    assert report.removal_authorized is False
    assert report.removable_count == 0
    assert report.retained_count == len(replacements["branches"])
    assert all(value.disposition == "retained-by-manifest"
               for value in report.decisions)
    semantic = {
        "audit_identity": LegacyConsolidationAudit.AUDIT_IDENTITY,
        "decisions": [value.to_dict() for value in report.decisions],
        "removable_count": report.removable_count,
        "removal_authorized": report.removal_authorized,
        "retained_count": report.retained_count,
        "schema_version": report.schema_version,
    }
    assert report.report_hash == structural_hash(semantic)


def test_requested_removal_needs_engine_live_tests_and_rollback_together():
    fdas = _json("fdas_manifest.json")
    replacements = _json("fdas_legacy_replacements.json")
    replacements = copy.deepcopy(replacements)
    row = replacements["branches"][0]
    row["requested_action"] = "remove"

    blocked = LegacyConsolidationAudit.evaluate(fdas, replacements)
    decision = next(value for value in blocked.decisions
                    if value.branch_id == row["branch_id"])
    assert decision.disposition == "removal-blocked"
    assert any(value.startswith("capability:") for value in decision.blockers)
    assert any(value.startswith("replacement-test-not-passing:")
               for value in decision.blockers)
    assert any(value.startswith("rollback-unavailable:")
               for value in decision.blockers)

    promoted = copy.deepcopy(fdas)
    for capability in row["replacement_capabilities"]:
        promoted["capabilities"][capability] = "engine-live"
    accepted = LegacyConsolidationAudit.evaluate(
        promoted, replacements,
        passing_test_ids=row["replacement_test_ids"],
        available_rollback_ids=(row["rollback_id"],))
    decision = next(value for value in accepted.decisions
                    if value.branch_id == row["branch_id"])
    assert decision.disposition == "removal-authorized"
    assert decision.blockers == ()
    assert accepted.removable_count == 1


def test_passing_tests_alone_never_override_component_only_capabilities():
    fdas = _json("fdas_manifest.json")
    replacements = _json("fdas_legacy_replacements.json")
    replacements = copy.deepcopy(replacements)
    row = replacements["branches"][2]
    row["requested_action"] = "remove"
    report = LegacyConsolidationAudit.evaluate(
        fdas, replacements,
        passing_test_ids=row["replacement_test_ids"],
        available_rollback_ids=(row["rollback_id"],))
    decision = next(value for value in report.decisions
                    if value.branch_id == row["branch_id"])

    assert decision.disposition == "removal-blocked"
    assert decision.verified_test_ids == tuple(sorted(
        row["replacement_test_ids"]))
    assert all(value.startswith("capability:")
               for value in decision.blockers)
