"""Lossless state-snapshot replay and captured FDAS regressions."""

import glob
import json
import os
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.rulesets.compiler import compile_ruleset  # noqa: E402
from freeciv_agent.state import (  # noqa: E402
    ProxyStateDTO,
    SnapshotReplayError,
    snapshot_from_event,
)
from freeciv_agent.state.atomspace import (  # noqa: E402
    CityEconomyProjector,
    DependentAtomSpaceStore,
    ruleset_digest,
)


CONTRACT = os.path.join(
    REPO, "contracts", "freeciv-proxy", "v2",
    "authoritative-state.fixture.json")
CAPTURED = os.path.join(REPO, "benchmarks", "gdo", "captured_snapshots")
DISPLAY_ALIAS_FIXTURE = os.path.join(
    CAPTURED, "city_defense_grounded_160",
    "turn-130-53e17615bdbbb5bb.json")


def _ruleset_root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append(
        "/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data")
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(
                candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT for captured FDAS replay")


def _event(snapshot):
    return {
        "game_id": snapshot.identity.game_id,
        "payload": snapshot.event_payload(),
        "turn": snapshot.turn,
    }


def _captured_fixture_paths():
    paths = set()
    for manifest_path in glob.glob(
            os.path.join(CAPTURED, "*_manifest.json")):
        with open(manifest_path, encoding="utf-8") as stream:
            manifest = json.load(stream)
        paths.update(
            os.path.join(REPO, row["path"])
            for row in manifest.get("fixtures", ()))
    return tuple(sorted(paths))


def test_current_state_event_roundtrips_without_semantic_loss():
    with open(CONTRACT, encoding="utf-8") as stream:
        payload = json.load(stream)
    original = ProxyStateDTO.parse(
        "fdas-state-replay", 701, payload).to_snapshot()

    assert snapshot_from_event(_event(original)) == original


def test_state_event_replay_rejects_identity_and_legal_catalog_tampering():
    with open(CONTRACT, encoding="utf-8") as stream:
        payload = json.load(stream)
    original = ProxyStateDTO.parse(
        "fdas-state-replay-tamper", 702, payload).to_snapshot()
    event = _event(original)
    event["payload"]["snapshot_id"] = "snapshot-" + "0" * 32
    with pytest.raises(SnapshotReplayError, match="identity mismatch"):
        snapshot_from_event(event)

    event = _event(original)
    event["payload"]["grounded_context"]["legal_actions"].append({
        "action_type": "fabricated-action",
    })
    with pytest.raises(SnapshotReplayError, match="legal action digest"):
        snapshot_from_event(event)


def test_frozen_captured_corpus_has_explicit_replay_coverage():
    replayable = []
    gaps = []
    paths = _captured_fixture_paths()
    for path in paths:
        with open(path, encoding="utf-8") as stream:
            event = json.load(stream)["snapshot_event"]
        try:
            replayable.append(snapshot_from_event(event))
        except SnapshotReplayError as error:
            gaps.append(str(error))

    assert len(paths) == 47
    assert len(replayable) == 38
    assert gaps == [
        "state snapshot lacks replayable grounded legal actions",
    ] * 9


def test_display_named_improvement_has_current_ruleset_support():
    with open(DISPLAY_ALIAS_FIXTURE, encoding="utf-8") as stream:
        snapshot = snapshot_from_event(json.load(stream)["snapshot_event"])
    ir = compile_ruleset(_ruleset_root(), "civ2civ3")
    store = DependentAtomSpaceStore(
        domain_projector=CityEconomyProjector(ir, ruleset_digest(ir)))

    revision = store.build(snapshot)

    queue_records = tuple(
        value for value in revision.records
        if value.key.predicate in ("city-queue-funded", "city-queue-unfunded"))
    assert queue_records
    assert any(
        any(
            dependency.key.path == "target:improvement:Amphitheater"
            for support in record.supports
            for dependency in support.dependencies)
        for record in queue_records)
