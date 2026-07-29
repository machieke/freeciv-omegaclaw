"""Reference-only unified PF/bridge/flow experiments."""

from .reference_model import (
    ABLATION_NAMES,
    BASELINE_NAMES,
    SYNTHETIC_FAMILIES,
    build_cohort,
    evaluate_selector,
    reference_invariants,
    selector_registry,
    stability_map,
    transport_latency,
)

__all__ = [
    "ABLATION_NAMES",
    "BASELINE_NAMES",
    "SYNTHETIC_FAMILIES",
    "build_cohort",
    "evaluate_selector",
    "reference_invariants",
    "selector_registry",
    "stability_map",
    "transport_latency",
]
