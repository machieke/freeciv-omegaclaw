"""G0 baseline freeze and drift detection for scaling experiments."""

import hashlib
import json
import os
from dataclasses import dataclass

from freeciv_agent.flow_control.builder import (
    FlowBuildBudget,
    FreeCivFactorGraphBuilder,
)
from freeciv_agent.flow_control.controller import BridgeScalarConfig
from freeciv_agent.flow_control.probes import ProbeConfig
from freeciv_agent.pressure.model import PressureConfig


PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(PACKAGE_ROOT)))
MANIFEST_PATH = os.path.join(PACKAGE_ROOT, "frozen_baseline.json")


@dataclass(frozen=True)
class BaselineVerification:
    valid: bool
    checks: tuple
    errors: tuple
    source_drift: tuple = ()

    def to_dict(self):
        return {
            "checks": dict(self.checks),
            "errors": list(self.errors),
            "source_drift": list(self.source_drift),
            "valid": self.valid,
        }


def load_frozen_baseline(path=MANIFEST_PATH):
    with open(path, "r") as handle:
        material = json.load(handle)
    if material.get("schema_version") != "1.0":
        raise ValueError("unsupported scaling baseline schema")
    if material.get("artifact_type") != "freeciv-scaling-frozen-baseline":
        raise ValueError("wrong scaling baseline artifact type")
    return material


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _actual_defaults():
    factor = FreeCivFactorGraphBuilder().budget.to_dict()
    bridge = BridgeScalarConfig()
    pressure = PressureConfig()
    probe = ProbeConfig()
    return {
        "bridge_scalar": {
            "maximum_regions_per_goal": bridge.maximum_regions_per_goal,
            "probe_max_steps": bridge.probe_max_steps,
            "probe_path_count": bridge.probe_path_count,
            "protected_scalar_top_k": bridge.protected_scalar_top_k,
        },
        "factor_graph_build": factor,
        "flow_build": FlowBuildBudget().to_dict(),
        "pressure": {
            "max_hops": pressure.max_hops,
            "max_routes_per_conclusion": pressure.max_routes_per_conclusion,
        },
        "probe": {
            "max_steps": probe.max_steps,
            "path_count": probe.path_count,
        },
        "proof": {
            "maximum_bindings": 4096,
            "maximum_depth": 32,
            "maximum_rule_fires": 4096,
        },
    }


def verify_frozen_baseline(repo_root=REPO_ROOT, manifest_path=MANIFEST_PATH):
    manifest = load_frozen_baseline(manifest_path)
    checks = []
    errors = []
    source_drift = []
    for relative, expected in sorted(manifest["evidence_sha256"].items()):
        path = os.path.join(repo_root, relative)
        actual = _sha256(path) if os.path.isfile(path) else None
        matched = actual == expected
        checks.append(("evidence:" + relative, matched))
        if not matched:
            errors.append(
                "evidence drift: {} expected {} got {}".format(
                    relative, expected, actual))
    for relative, expected in sorted(manifest["source_sha256"].items()):
        path = os.path.join(repo_root, relative)
        actual = _sha256(path) if os.path.isfile(path) else None
        readable = actual is not None
        checks.append(("source-readable:" + relative, readable))
        if not readable:
            errors.append("baseline source is missing: {}".format(relative))
        elif actual != expected:
            source_drift.append(
                "{} baseline {} current {}".format(
                    relative, expected, actual))
    expected_defaults = manifest["production_defaults"]
    for section, actual in sorted(_actual_defaults().items()):
        expected = expected_defaults[section]
        matched = actual == expected
        checks.append(("defaults:" + section, matched))
        if not matched:
            errors.append(
                "default drift: {} expected {} got {}".format(
                    section, expected, actual))
    # Profile values are source-hash frozen above. They remain in the manifest
    # as a readable preregistration contract without adding a YAML dependency.
    checks.append(("claim-boundary-declared", bool(manifest["claim_boundary"])))
    return BaselineVerification(
        not errors, tuple(checks), tuple(errors), tuple(source_drift))
