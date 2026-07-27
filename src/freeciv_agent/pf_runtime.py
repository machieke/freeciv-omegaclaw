"""Declared and observed PF-PLN runtime activation.

Canonical phase acceptance and live-engine activation are separate claims.
This module makes that boundary machine-readable, includes it in harness
identity, and emits it into every harness event stream.
"""

import copy

from .events.schema import structural_hash


SCHEMA_VERSION = "1.0"
LIVE_ADAPTER = "grounded-impact-planner/1.19"
SUPPORT_ENGINE_LIVE = "engine-live"
SUPPORT_COMPONENT_ONLY = "component-only"

PHASE_SPECS = (
    {
        "component": "executable_semantics",
        "phase": 0,
        "support": SUPPORT_ENGINE_LIVE,
        "capabilities": ("scheduler",),
        "policy_flags": ("pressure_enabled",),
    },
    {
        "component": "goal_regression_planner",
        "phase": 1,
        "support": SUPPORT_ENGINE_LIVE,
        "capabilities": ("scheduler",),
        "policy_flags": ("pressure_enabled",),
    },
    {
        "component": "provenance_contradiction",
        "phase": 2,
        "support": SUPPORT_COMPONENT_ONLY,
        "capabilities": (),
        "policy_flags": (),
    },
    {
        "component": "observation_simulation_pressure",
        "phase": 3,
        "support": SUPPORT_COMPONENT_ONLY,
        "capabilities": (),
        "policy_flags": (),
    },
    {
        "component": "conductance_learning",
        "phase": 4,
        "support": SUPPORT_ENGINE_LIVE,
        "capabilities": ("scheduler",),
        "policy_flags": (
            "pressure_enabled", "pressure_learning_enabled"),
    },
    {
        "component": "lifecycle_clones",
        "phase": 5,
        "support": SUPPORT_COMPONENT_ONLY,
        "capabilities": (),
        "policy_flags": (),
    },
    {
        "component": "induction_analogy",
        "phase": 6,
        "support": SUPPORT_COMPONENT_ONLY,
        "capabilities": (),
        "policy_flags": (),
    },
    {
        "component": "llm_gateway",
        "phase": 7,
        "support": SUPPORT_COMPONENT_ONLY,
        "capabilities": (),
        "policy_flags": (),
    },
    {
        "component": "differentiable_execution",
        "phase": 8,
        "support": SUPPORT_COMPONENT_ONLY,
        "capabilities": (),
        "policy_flags": (),
    },
    {
        "component": "multi_goal_field",
        "phase": 9,
        "support": SUPPORT_ENGINE_LIVE,
        "capabilities": ("scheduler",),
        "policy_flags": ("pressure_enabled",),
    },
)

_SPEC_BY_COMPONENT = {
    row["component"]: row for row in PHASE_SPECS}


class PFRuntimeConfigurationError(ValueError):
    """A PF-PLN support declaration or activation report is inconsistent."""


def canonical_declaration():
    return {
        "adapter": LIVE_ADAPTER,
        "components": {
            row["component"]: {
                "phase": row["phase"],
                "support": row["support"],
            }
            for row in PHASE_SPECS
        },
        "schema_version": SCHEMA_VERSION,
    }


def validate_declaration(value):
    if not isinstance(value, dict):
        raise PFRuntimeConfigurationError(
            "pf_pln_runtime must be an object")
    if set(value) != {"adapter", "components", "schema_version"}:
        raise PFRuntimeConfigurationError(
            "pf_pln_runtime fields must be adapter, components, "
            "and schema_version")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise PFRuntimeConfigurationError(
            "pf_pln_runtime.schema_version must be 1.0")
    if value.get("adapter") != LIVE_ADAPTER:
        raise PFRuntimeConfigurationError(
            "pf_pln_runtime.adapter must be {}".format(LIVE_ADAPTER))
    components = value.get("components")
    if not isinstance(components, dict):
        raise PFRuntimeConfigurationError(
            "pf_pln_runtime.components must be an object")
    missing = sorted(set(_SPEC_BY_COMPONENT) - set(components))
    extra = sorted(set(components) - set(_SPEC_BY_COMPONENT))
    if missing or extra:
        raise PFRuntimeConfigurationError(
            "PF-PLN component set mismatch: missing={} extra={}".format(
                missing, extra))
    for component, spec in _SPEC_BY_COMPONENT.items():
        row = components[component]
        if not isinstance(row, dict) or set(row) != {"phase", "support"}:
            raise PFRuntimeConfigurationError(
                "{} must declare only phase and support".format(component))
        if row["phase"] != spec["phase"]:
            raise PFRuntimeConfigurationError(
                "{} must map to phase {}".format(
                    component, spec["phase"]))
        if row["support"] != spec["support"]:
            raise PFRuntimeConfigurationError(
                "{} support must be {}".format(
                    component, spec["support"]))
    return copy.deepcopy(value)


def build_runtime_activation(
        declaration, backend, capabilities, impact_policy):
    """Derive the exact per-game activation matrix."""
    declaration = validate_declaration(declaration)
    if backend not in ("engine-live", "representative"):
        raise PFRuntimeConfigurationError(
            "unsupported PF-PLN runtime backend {}".format(backend))
    if not isinstance(capabilities, dict):
        raise PFRuntimeConfigurationError(
            "runtime capabilities must be an object")
    if not isinstance(impact_policy, dict):
        raise PFRuntimeConfigurationError(
            "impact policy must be an object")

    components = {}
    for spec in PHASE_SPECS:
        missing_capabilities = [
            name for name in spec["capabilities"]
            if capabilities.get(name) is not True
        ]
        disabled_flags = [
            name for name in spec["policy_flags"]
            if impact_policy.get(name) is not True
        ]
        enabled = (
            spec["support"] == SUPPORT_ENGINE_LIVE
            and backend == "engine-live"
            and not missing_capabilities
            and not disabled_flags
        )
        if spec["support"] == SUPPORT_COMPONENT_ONLY:
            reason = "no-engine-live-adapter"
        elif backend != "engine-live":
            reason = "backend-not-engine-live"
        elif missing_capabilities:
            reason = "capability-disabled:{}".format(
                ",".join(missing_capabilities))
        elif disabled_flags:
            reason = "policy-disabled:{}".format(
                ",".join(disabled_flags))
        else:
            reason = "enabled"
        components[spec["component"]] = {
            "enabled": enabled,
            "phase": spec["phase"],
            "reason": reason,
            "support": declaration["components"][
                spec["component"]]["support"],
        }
    report = {
        "adapter": declaration["adapter"],
        "backend": backend,
        "components": components,
        "schema_version": SCHEMA_VERSION,
    }
    report["activation_hash"] = structural_hash(report)
    return report


def validate_runtime_activation(
        report, backend, capabilities, impact_policy):
    expected = build_runtime_activation(
        canonical_declaration(), backend, capabilities, impact_policy)
    if report != expected:
        raise PFRuntimeConfigurationError(
            "PF-PLN runtime activation report mismatch")
    return copy.deepcopy(report)


def enabled_phases(report):
    return tuple(sorted(
        row["phase"] for row in report["components"].values()
        if row["enabled"]))


def emit_runtime_activation(
        writer, turn, parent, report, condition_id, track):
    """Append a causal declaration for every PF-PLN phase."""
    current = parent
    events = []
    for component, row in sorted(
            report["components"].items(),
            key=lambda item: item[1]["phase"]):
        event = writer.emit("metric_sample", turn, {
            "labels": {
                "backend": report["backend"],
                "component": component,
                "condition": str(condition_id),
                "declaration": "pf_pln_runtime_activation",
                "phase": str(row["phase"]),
                "reason": row["reason"],
                "support": row["support"],
                "track": str(track),
            },
            "name": "pf_pln_phase_enabled",
            "unit": "ratio",
            "value": float(row["enabled"]),
        }, caused_by=[current])
        events.append(event)
        current = event["event_id"]
    return current, tuple(events)
