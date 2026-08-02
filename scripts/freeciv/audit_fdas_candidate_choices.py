#!/usr/bin/env python3
"""Audit an FDAS candidate choice store and selected-only calibration export."""

import argparse
import hashlib
import json
import os
import sys


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.schema import (  # noqa: E402
    canonical_json_bytes,
    structural_hash,
)
from freeciv_agent.planning import (  # noqa: E402
    FdasCandidateChoiceSetStore,
    combine_candidate_choice_stores,
    export_candidate_choice_calibration,
)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_source(path):
    path = os.path.abspath(path)
    with open(path, encoding="utf-8") as stream:
        raw = json.load(stream)
    store = FdasCandidateChoiceSetStore.load(
        path, raw["persistence_identity"])
    return path, raw, store


def audit(paths):
    if isinstance(paths, str):
        paths = (paths,)
    sources = tuple(_load_source(path) for path in paths)
    if not sources:
        raise ValueError("candidate choice audit requires a source store")
    quarantined = tuple(
        store for _path, _raw, store in sources if store.quarantined)
    if quarantined:
        raise ValueError(
            "candidate choice store is quarantined: {}".format(
                quarantined[0].quarantine_reason))
    if len(sources) == 1:
        path, raw, store = sources[0]
        artifact = {
            "path": os.path.relpath(path, REPO).replace(os.sep, "/"),
            "persistence_identity": store.persistence_identity,
            "sha256": _sha256(path),
            "store_digest": store.store_digest,
        }
    else:
        source_rows = tuple({
            "path": os.path.relpath(path, REPO).replace(os.sep, "/"),
            "persistence_identity": store.persistence_identity,
            "sha256": _sha256(path),
            "store_digest": store.store_digest,
        } for path, _raw, store in sources)
        cohort_identity = structural_hash({
            "source_store_digests": [
                value["store_digest"] for value in source_rows],
            "source_store_identities": [
                value["persistence_identity"] for value in source_rows],
        })
        store = combine_candidate_choice_stores(
            tuple(value[2] for value in sources), cohort_identity)
        raw = {"store_digest": store.store_digest}
        artifact = {
            "cohort_persistence_identity": cohort_identity,
            "source_count": len(source_rows),
            "sources": list(source_rows),
            "store_digest": store.store_digest,
        }
    choice_sets = store.choice_sets()
    scopes = tuple(sorted(set(
        (value.operation_type, value.outcome_target)
        for value in choice_sets)))
    if len(scopes) != 1:
        raise ValueError("candidate choice audit requires one exact scope")
    operation_type, outcome_target = scopes[0]
    exported = export_candidate_choice_calibration(
        store, operation_type, outcome_target)
    all_choices = tuple(
        row for value in choice_sets for row in value.choices)
    selected_choices = tuple(
        row for row in all_choices if row.selection_role == "selected")
    nonselected_choices = tuple(
        row for row in all_choices
        if row.selection_role == "nonselected-censored")
    observed_sets = tuple(
        value for value in choice_sets
        if value.outcome_status == "observed")
    gates = {
        "all_feature_queries_are_outcome_free": all(
            "outcome" not in row.feature_query.to_dict()
            for row in all_choices),
        "all_nonselected_candidates_are_explicitly_censored": all(
            row.selection_role == "nonselected-censored"
            for row in nonselected_choices),
        "observed_outcomes_have_exact_selected_rows": all(
            len(tuple(
                row for row in value.choices
                if row.selection_role == "selected")) == 1
            and value.selected_episode_id is not None
            and value.outcome_label_id is not None
            and isinstance(value.observed_outcome, bool)
            for value in observed_sets),
        "selected_only_export_is_complete": (
            len(exported.examples) == len(observed_sets)),
        "store_digest_is_current": raw.get("store_digest") == (
            store.store_digest),
        "store_is_not_quarantined": not store.quarantined,
    }
    semantic = {
        "artifact": artifact,
        "calibration_export": exported.to_dict(),
        "claim_scope": (
            "selected-only candidate calibration evidence; rejected or "
            "out-of-scope alternatives are censored, not negative; no truth, "
            "readout, policy, action, gameplay, score, or win-rate claim"),
        "counts": {
            "choice_sets": len(choice_sets),
            "choices": len(all_choices),
            "no_in_scope_selection_sets": sum(
                value.selected_operation_id is None
                for value in choice_sets),
            "nonselected_censored_choices": len(nonselected_choices),
            "observed_negative_selected_outcomes": sum(
                value.observed_outcome is False for value in observed_sets),
            "observed_positive_selected_outcomes": sum(
                value.observed_outcome is True for value in observed_sets),
            "observed_selected_outcomes": len(observed_sets),
            "selected_choices": len(selected_choices),
            "selected_pending_or_censored": (
                exported.selected_pending_or_censored_count),
        },
        "gates": gates,
        "operation_type": operation_type,
        "outcome_target": outcome_target,
        "passed": all(gates.values()),
        "policy_authority": False,
        "readout_authority": False,
        "schema_version": "fdas-candidate-choice-audit/1.0",
        "truth_mutated": False,
    }
    semantic["report_hash"] = structural_hash(semantic)
    return semantic


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("choice_store", nargs="+")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = audit(args.choice_store)
    payload = canonical_json_bytes(report) + b"\n"
    if args.output:
        output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "wb") as stream:
            stream.write(payload)
    else:
        sys.stdout.buffer.write(payload)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
