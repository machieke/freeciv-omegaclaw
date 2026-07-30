"""Declared and observed PF-PLN runtime activation.

Canonical phase acceptance and live-engine activation are separate claims.
This module makes that boundary machine-readable, includes it in harness
identity, and emits it into every harness event stream.
"""

import copy
import math

from .events.schema import structural_hash


SCHEMA_VERSION = "1.0"
LIVE_ADAPTER = "grounded-impact-planner/1.35"
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

CONTROLLER_SCHEMA_VERSION = "2.0"
PRESSURE_ARTIFACT_SCHEMAS = ("1.0", "2.0")
CONTROLLER_MODES = (
    "canonical",
    "legacy_scalar",
    "scalar_v2",
    "bridge_scalar",
    "unified_shadow",
    "bridge_scalar_advisory",
    "unified_flow_advisory",
    "unified_flow_live",
)
CONTROLLER_LAYER_SPECS = (
    {"layer": "scalar_pf_v1", "support": "engine-live"},
    {"layer": "scalar_pf_v2", "support": "experimental"},
    {"layer": "grounded_domain_estimates", "support": "experimental"},
    {"layer": "packet_scheduler", "support": "experimental"},
    {"layer": "identity_resource_scheduler", "support": "experimental"},
    {"layer": "operation_lifecycle", "support": "experimental"},
    {"layer": "city_defense_operations", "support": "experimental"},
    {"layer": "native_movement_routes", "support": "experimental"},
    {"layer": "native_combat_probabilities", "support": "experimental"},
    {"layer": "combat_operations", "support": "experimental"},
    {"layer": "transport_operations", "support": "experimental"},
    {"layer": "production_operations", "support": "experimental"},
    {"layer": "research_operations", "support": "experimental"},
    {"layer": "teleological_cost_to_go", "support": "experimental"},
    {"layer": "path_persistence", "support": "experimental"},
    {"layer": "bridge", "support": "experimental"},
    {"layer": "source_sink_flow", "support": "component-only"},
    {"layer": "bounded_staleness_view", "support": "experimental"},
    {"layer": "decision_explanations", "support": "experimental"},
    {"layer": "exact_commit_revalidation", "support": "experimental"},
    {"layer": "native_flowpack", "support": "not-built"},
)

CONTROLLER_POLICY_DEFAULTS = {
    "pressure_achievement_uncertainty_split_enabled": False,
    "pressure_bridge_enabled": False,
    "pressure_bridge_importance_corrected_enabled": False,
    "pressure_bridge_reference_likelihood_enabled": False,
    "pressure_bridge_estimator_policy": "holdout",
    "pressure_bridge_normalization_contract":
        "robust-feature-scales/1.0",
    "pressure_bridge_readout_policy":
        "corrected-probe-overlap",
    "pressure_distributional_risk_enabled": False,
    "pressure_domain_estimates_authority_enabled": False,
    "pressure_domain_estimates_enabled": False,
    "pressure_enabled": True,
    "pressure_flow_enabled": False,
    "pressure_flow_protected_candidate_union_enabled": False,
    "pressure_flow_research_entry_gate_required": False,
    "pressure_flow_live_enabled": False,
    "pressure_commit_revalidation_enabled": False,
    "pressure_city_defense_operations_enabled": False,
    "pressure_llm_expansion_enabled": False,
    "pressure_llm_validation_packet_budget": 0,
    "pressure_packet_scheduler_enabled": False,
    "pressure_resource_scheduler_enabled": False,
    "pressure_operation_lifecycle_enabled": False,
    "pressure_native_movement_routes_enabled": False,
    "pressure_native_combat_probabilities_enabled": False,
    "pressure_combat_operations_enabled": False,
    "pressure_transport_operations_enabled": False,
    "pressure_production_operations_enabled": False,
    "pressure_research_operations_enabled": False,
    "pressure_path_persistence_enabled": False,
    "pressure_requirement_sets_enabled": False,
    "pressure_scalar_fallback_enabled": True,
    "pressure_shaping_capacity_structural_updates_enabled": False,
    "pressure_signed_channels_enabled": False,
    "pressure_transition_value_authority_enabled": False,
    "pressure_transition_value_enabled": False,
    "pressure_transition_value_model_identity": "",
    "pressure_transition_value_model_path": "",
    "pressure_transition_value_read_only": False,
    "pressure_controller_mode": "auto",
    "pressure_semantics_version": "v1",
}

CONTROLLER_CONFIGURATION_DEFAULTS = {
    "domain_estimates": {
        "authority_enabled": False,
        "enabled": False,
    },
    "pressure_v2": {
        "achievement_uncertainty_split": False,
        "signed_channels": False,
        "distributional_risk": False,
        "requirement_sets": False,
        "packet_scheduler": False,
        "resource_scheduler": False,
    },
    "teleology": {
        "estimator": "immediate_loss",
        "max_horizon": 6,
        "calibration_required": False,
        "protect_uncalibrated_terminal_actions": True,
        "transition_value_authority_enabled": False,
        "transition_value_enabled": False,
        "transition_value_minimum_samples": 30,
        "transition_value_maximum_half_width": 0.50,
        "transition_value_alpha": 0.05,
        "path_persistence_enabled": False,
        "path_persistence_smoothing": 0.35,
        "path_persistence_route_momentum": 0.15,
        "path_persistence_minimum_dwell_steps": 2,
        "path_persistence_dwell_bonus": 0.05,
        "path_persistence_switch_margin": 0.01,
        "path_persistence_maximum_priority_regret": 0.05,
        "metacontrol_budget_fraction": 0.05,
    },
    "bridge": {
        "enabled": False,
        "estimator_policy": "holdout",
        # Production-safe deterministic defaults.  Larger probe blocks remain
        # opt-in experiment settings; the default must fit the live 500 ms
        # controller-inclusive latency gate on captured FreeCiv snapshots.
        "forward_depth": 16,
        "backward_depth": 16,
        "probe_count": 8,
        "reference_probe_fraction": 0.25,
        "max_importance_weight": 20.0,
        "minimum_ess": 0.8,
        "temperature": 1.0,
        "deposit_decay": 0.10,
        "current_following_gain": 0.0,
        "importance_corrected": False,
        "reference_likelihood_support": False,
        "normalization_contract": "robust-feature-scales/1.0",
        "readout_policy": "corrected-probe-overlap",
        "protected_scalar_top_k": 3,
    },
    "flow": {
        "enabled": False,
        "protected_candidate_union_enabled": False,
        "protected_scalar_top_k": 3,
        "research_entry_gate_required": False,
        "turnover_fraction": 0.25,
        "candidate_region_relative_overlap": 0.50,
        "maximum_candidate_regions_per_goal": 8,
        "time_step": 1.0,
        "cfl_limit": 0.90,
        "diffusion": 0.03,
        "projection_tolerance": 1.0e-8,
        "mass_tolerance": 1.0e-8,
        "maximum_microsteps": 8,
        "scalar_fallback": True,
        "shaping_capacity_structural_updates": False,
    },
    "packets": {
        "budgets": {
            "cpu": 64,
            "exact_rule": 8,
            "observation": 2,
            "simulation": 4,
            "action": 1,
            "expansion": 1,
            "llm_token": 0,
        },
        "reservation_ttl": 2,
        "backup_route_fraction": 0.10,
    },
    "safety": {
        "hard_tail_risk_gate": True,
        "commit_revalidation": False,
    },
}

_GROUP_TO_POLICY = {
    ("domain_estimates", "enabled"):
        "pressure_domain_estimates_enabled",
    ("domain_estimates", "authority_enabled"):
        "pressure_domain_estimates_authority_enabled",
    ("pressure_v2", "achievement_uncertainty_split"):
        "pressure_achievement_uncertainty_split_enabled",
    ("pressure_v2", "signed_channels"):
        "pressure_signed_channels_enabled",
    ("pressure_v2", "distributional_risk"):
        "pressure_distributional_risk_enabled",
    ("pressure_v2", "requirement_sets"):
        "pressure_requirement_sets_enabled",
    ("pressure_v2", "packet_scheduler"):
        "pressure_packet_scheduler_enabled",
    ("pressure_v2", "resource_scheduler"):
        "pressure_resource_scheduler_enabled",
    ("bridge", "enabled"):
        "pressure_bridge_enabled",
    ("bridge", "importance_corrected"):
        "pressure_bridge_importance_corrected_enabled",
    ("bridge", "reference_likelihood_support"):
        "pressure_bridge_reference_likelihood_enabled",
    ("bridge", "estimator_policy"):
        "pressure_bridge_estimator_policy",
    ("bridge", "normalization_contract"):
        "pressure_bridge_normalization_contract",
    ("bridge", "readout_policy"):
        "pressure_bridge_readout_policy",
    ("teleology", "transition_value_enabled"):
        "pressure_transition_value_enabled",
    ("teleology", "transition_value_authority_enabled"):
        "pressure_transition_value_authority_enabled",
    ("teleology", "path_persistence_enabled"):
        "pressure_path_persistence_enabled",
    ("flow", "enabled"):
        "pressure_flow_enabled",
    ("flow", "protected_candidate_union_enabled"):
        "pressure_flow_protected_candidate_union_enabled",
    ("flow", "research_entry_gate_required"):
        "pressure_flow_research_entry_gate_required",
    ("flow", "scalar_fallback"):
        "pressure_scalar_fallback_enabled",
    ("flow", "shaping_capacity_structural_updates"):
        "pressure_shaping_capacity_structural_updates_enabled",
    ("safety", "commit_revalidation"):
        "pressure_commit_revalidation_enabled",
}

_SPEC_BY_COMPONENT = {
    row["component"]: row for row in PHASE_SPECS}


class PFRuntimeConfigurationError(ValueError):
    """A PF-PLN support declaration or activation report is inconsistent."""


def _merged_controller_configuration(impact_policy):
    configuration = copy.deepcopy(
        CONTROLLER_CONFIGURATION_DEFAULTS)
    for group in configuration:
        declared = impact_policy.get(group)
        if declared is None:
            continue
        if not isinstance(declared, dict):
            raise PFRuntimeConfigurationError(
                "{} controller configuration must be an object".format(
                    group))
        unknown = sorted(
            set(declared) - set(configuration[group]))
        if unknown:
            raise PFRuntimeConfigurationError(
                "{} controller configuration has unknown fields: {}".format(
                    group, unknown))
        if group == "packets" and "budgets" in declared:
            budgets = declared["budgets"]
            if not isinstance(budgets, dict):
                raise PFRuntimeConfigurationError(
                    "packet budgets must be an object")
            unknown_budgets = sorted(
                set(budgets)
                - set(configuration[group]["budgets"]))
            if unknown_budgets:
                raise PFRuntimeConfigurationError(
                    "unknown packet resources: {}".format(
                        unknown_budgets))
            configuration[group]["budgets"].update(
                budgets)
            declared = dict(declared)
            declared.pop("budgets")
        configuration[group].update(declared)
    for (group, field), policy_name in (
            _GROUP_TO_POLICY.items()):
        if policy_name not in impact_policy:
            continue
        declared_group = impact_policy.get(group)
        if (isinstance(declared_group, dict)
                and field in declared_group
                and declared_group[field]
                != impact_policy[policy_name]):
            raise PFRuntimeConfigurationError(
                "conflicting flat and grouped settings for {}".format(
                    policy_name))
        configuration[group][field] = (
            impact_policy[policy_name])
    return configuration


def _policy_with_group_aliases(impact_policy, configuration):
    aliased = dict(impact_policy)
    for (group, field), policy_name in (
            _GROUP_TO_POLICY.items()):
        declared_group = impact_policy.get(group)
        if (not isinstance(declared_group, dict)
                or field not in declared_group):
            continue
        grouped_value = configuration[group][field]
        if (policy_name in impact_policy
                and impact_policy[policy_name]
                != grouped_value):
            raise PFRuntimeConfigurationError(
                "conflicting flat and grouped settings for {}".format(
                    policy_name))
        aliased[policy_name] = grouped_value
    return aliased


def _validate_controller_configuration(configuration):
    for group, names in (
            ("domain_estimates", (
                "enabled", "authority_enabled")),
            ("pressure_v2", (
                "achievement_uncertainty_split",
                "signed_channels",
                "distributional_risk",
                "requirement_sets",
                "packet_scheduler",
                "resource_scheduler")),
            ("bridge", (
                "enabled", "importance_corrected",
                "reference_likelihood_support")),
            ("flow", (
                "enabled", "scalar_fallback",
                "protected_candidate_union_enabled",
                "research_entry_gate_required",
                "shaping_capacity_structural_updates")),
            ("teleology", (
                "calibration_required",
                "protect_uncalibrated_terminal_actions",
                "path_persistence_enabled",
                "transition_value_enabled",
                "transition_value_authority_enabled")),
            ("safety", (
                "hard_tail_risk_gate",
                "commit_revalidation"))):
        if any(not isinstance(
                configuration[group][name], bool)
                for name in names):
            raise PFRuntimeConfigurationError(
                "{} boolean controller settings are invalid".format(
                    group))
    if configuration["teleology"]["estimator"] not in (
            "immediate_loss", "finite_horizon",
            "learned_value", "hybrid"):
        raise PFRuntimeConfigurationError(
            "unknown teleology estimator")
    if configuration["bridge"]["estimator_policy"] not in (
            "holdout", "importance_corrected", "mixed"):
        raise PFRuntimeConfigurationError(
            "unknown bridge estimator policy")
    for group, name, minimum, maximum, strict_minimum in (
            ("teleology", "max_horizon", 1, 1000, False),
            ("teleology", "transition_value_minimum_samples",
             1, 1000000, False),
            ("teleology", "path_persistence_minimum_dwell_steps",
             0, 1000000, False),
            ("bridge", "forward_depth", 1, 1000, False),
            ("bridge", "backward_depth", 1, 1000, False),
            ("bridge", "probe_count", 1, 10000000, False),
            ("bridge", "protected_scalar_top_k",
             1, 1000000, False),
            ("bridge", "minimum_ess", 0.0, 10000000.0, True),
            ("bridge", "max_importance_weight", 1.0, 1000000.0, False),
            ("bridge", "temperature", 0.0, 1000000.0, True),
            ("flow", "time_step", 0.0, 1.0, True),
            ("flow", "cfl_limit", 0.0, 1.0, True),
            ("flow", "projection_tolerance", 0.0, 1.0, True),
            ("flow", "mass_tolerance", 0.0, 1.0, True),
            ("flow", "maximum_microsteps", 1, 1000000, False),
            ("flow", "maximum_candidate_regions_per_goal",
             1, 1000000, False),
            ("flow", "protected_scalar_top_k",
             1, 1000000, False),
            ("packets", "reservation_ttl", 1, 1000000, False)):
        value = configuration[group][name]
        if isinstance(value, bool) or not isinstance(
                value, (int, float)):
            raise PFRuntimeConfigurationError(
                "{}.{} must be numeric".format(group, name))
        if (not math.isfinite(float(value))
                or (strict_minimum and value <= minimum)
                or (not strict_minimum and value < minimum)
                or value > maximum):
            raise PFRuntimeConfigurationError(
                "{}.{} is outside its valid range".format(
                    group, name))
    if (float(configuration["bridge"]["minimum_ess"])
            > int(configuration["bridge"]["probe_count"])):
        raise PFRuntimeConfigurationError(
            "bridge.minimum_ess cannot exceed probe_count")
    for group, name in (
            ("teleology", "metacontrol_budget_fraction"),
            ("teleology", "transition_value_maximum_half_width"),
            ("teleology", "transition_value_alpha"),
            ("teleology", "path_persistence_smoothing"),
            ("teleology", "path_persistence_route_momentum"),
            ("teleology", "path_persistence_dwell_bonus"),
            ("teleology", "path_persistence_switch_margin"),
            ("teleology", "path_persistence_maximum_priority_regret"),
            ("bridge", "reference_probe_fraction"),
            ("bridge", "deposit_decay"),
            ("flow", "turnover_fraction"),
            ("flow", "candidate_region_relative_overlap"),
            ("flow", "diffusion"),
            ("packets", "backup_route_fraction")):
        value = configuration[group][name]
        if (isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0):
            raise PFRuntimeConfigurationError(
                "{}.{} must be in [0, 1]".format(
                    group, name))
    for resource, quanta in (
            configuration["packets"]["budgets"].items()):
        if (isinstance(quanta, bool)
                or not isinstance(quanta, int)
                or quanta < 0):
            raise PFRuntimeConfigurationError(
                "packet budget {} must be a non-negative integer".format(
                    resource))
    for group, name in (
            ("bridge", "normalization_contract"),
            ("bridge", "readout_policy")):
        value = configuration[group][name]
        if not isinstance(value, str) or not value:
            raise PFRuntimeConfigurationError(
                "{}.{} is required".format(group, name))
    if configuration["bridge"]["readout_policy"] not in (
            "corrected-probe-overlap",
            "protected-message-union",
            "corrected-probe-union"):
        raise PFRuntimeConfigurationError(
            "unknown bridge readout policy")
    if (configuration["bridge"]["importance_corrected"]
            and not configuration["bridge"][
                "reference_likelihood_support"]):
        raise PFRuntimeConfigurationError(
            "importance-corrected probes require reference "
            "likelihood support")
    if (configuration["bridge"]["estimator_policy"]
            in ("importance_corrected", "mixed")
            and not configuration["bridge"][
                "reference_likelihood_support"]):
        raise PFRuntimeConfigurationError(
            "corrected bridge estimator requires reference "
            "likelihood support")
    gain = configuration["bridge"][
        "current_following_gain"]
    if (isinstance(gain, bool)
            or not isinstance(gain, (int, float))
            or not math.isfinite(float(gain))
            or gain < 0.0):
        raise PFRuntimeConfigurationError(
            "bridge.current_following_gain must be non-negative")
    if configuration["flow"][
            "shaping_capacity_structural_updates"]:
        raise PFRuntimeConfigurationError(
            "shaping capacities cannot authorize structural updates")
    if configuration["flow"][
            "research_entry_gate_required"]:
        if not configuration["flow"][
                "protected_candidate_union_enabled"]:
            raise PFRuntimeConfigurationError(
                "flow research gate requires protected candidate union")
        if not configuration["teleology"][
                "transition_value_authority_enabled"]:
            raise PFRuntimeConfigurationError(
                "flow research gate requires transition-value authority")
        if not configuration["teleology"][
                "path_persistence_enabled"]:
            raise PFRuntimeConfigurationError(
                "flow research gate requires path persistence comparator")
        if configuration["bridge"]["readout_policy"] == (
                "corrected-probe-overlap"):
            raise PFRuntimeConfigurationError(
                "flow research gate requires decision-safe bridge readout")
    if configuration["teleology"][
            "transition_value_authority_enabled"
            ] and not configuration["teleology"][
                "transition_value_enabled"]:
        raise PFRuntimeConfigurationError(
            "transition-value authority requires transition-value learning")
    if configuration["teleology"][
            "path_persistence_enabled"
            ] and not configuration["teleology"][
                "transition_value_authority_enabled"]:
        raise PFRuntimeConfigurationError(
            "path persistence requires transition-value authority")
    return configuration


def controller_declaration():
    return {
        "adapter": "impact-control-adapter/1.0",
        "artifact_schemas": {
            "control_query": "1.0",
            "control_decision": "1.0",
            "flow_patch": "1.0",
            "pressure": list(PRESSURE_ARTIFACT_SCHEMAS),
        },
        "fallback_modes": [
            "scalar_v2", "legacy_scalar", "canonical"],
        "layers": {
            row["layer"]: {"support": row["support"]}
            for row in CONTROLLER_LAYER_SPECS
        },
        "modes": list(CONTROLLER_MODES),
        "normalization_contract":
            "robust-feature-scales/1.0",
        "schema_version": CONTROLLER_SCHEMA_VERSION,
    }


def validate_controller_policy(impact_policy):
    if not isinstance(impact_policy, dict):
        raise PFRuntimeConfigurationError(
            "controller impact policy must be an object")
    configuration = _validate_controller_configuration(
        _merged_controller_configuration(impact_policy))
    impact_policy = _policy_with_group_aliases(
        impact_policy, configuration)
    policy = dict(CONTROLLER_POLICY_DEFAULTS)
    for name in CONTROLLER_POLICY_DEFAULTS:
        if name in impact_policy:
            policy[name] = impact_policy[name]
    if policy["pressure_semantics_version"] not in ("v1", "v2"):
        raise PFRuntimeConfigurationError(
            "pressure_semantics_version must be v1 or v2")
    if policy["pressure_bridge_readout_policy"] not in (
            "corrected-probe-overlap",
            "protected-message-union",
            "corrected-probe-union"):
        raise PFRuntimeConfigurationError(
            "unknown pressure bridge readout policy")
    if policy["pressure_controller_mode"] not in (
            ("auto",) + CONTROLLER_MODES):
        raise PFRuntimeConfigurationError(
            "unknown pressure_controller_mode")
    if policy["pressure_controller_mode"] == "auto":
        policy["pressure_controller_mode"] = (
            "bridge_scalar"
            if policy["pressure_bridge_enabled"]
            else "scalar_v2"
            if policy["pressure_semantics_version"] == "v2"
            else "legacy_scalar")
    boolean_names = tuple(
        name for name, value
        in CONTROLLER_POLICY_DEFAULTS.items()
        if isinstance(value, bool))
    if any(not isinstance(policy[name], bool) for name in boolean_names):
        raise PFRuntimeConfigurationError(
            "PF controller feature flags must be boolean")
    if (policy["pressure_semantics_version"] == "v1"
            and any(policy[name] for name in (
                "pressure_achievement_uncertainty_split_enabled",
                "pressure_distributional_risk_enabled",
                "pressure_signed_channels_enabled",
                "pressure_packet_scheduler_enabled",
                "pressure_resource_scheduler_enabled",
                "pressure_operation_lifecycle_enabled",
                "pressure_native_movement_routes_enabled",
                "pressure_native_combat_probabilities_enabled",
                "pressure_combat_operations_enabled",
                "pressure_transport_operations_enabled",
                "pressure_production_operations_enabled",
                "pressure_research_operations_enabled",
                "pressure_city_defense_operations_enabled",
                "pressure_requirement_sets_enabled",
                "pressure_domain_estimates_enabled",
                "pressure_bridge_enabled",
                "pressure_flow_enabled",
                "pressure_transition_value_enabled"))):
        raise PFRuntimeConfigurationError(
            "v2 controller features require pressure semantics v2")
    if (policy["pressure_transition_value_authority_enabled"]
            and not policy["pressure_transition_value_enabled"]):
        raise PFRuntimeConfigurationError(
            "transition-value authority requires transition-value learning")
    if (policy["pressure_domain_estimates_authority_enabled"]
            and not policy["pressure_domain_estimates_enabled"]):
        raise PFRuntimeConfigurationError(
            "domain-estimate authority requires domain estimates")
    if policy["pressure_domain_estimates_authority_enabled"]:
        if (policy["pressure_semantics_version"] != "v2"
                or not policy[
                    "pressure_commit_revalidation_enabled"]):
            raise PFRuntimeConfigurationError(
                "domain-estimate authority requires scalar-v2 semantics "
                "and commit revalidation")
        raise PFRuntimeConfigurationError(
            "domain-estimate authority is unavailable in shadow-only GDO-1")
    if (policy["pressure_transition_value_enabled"]
            and not policy["pressure_packet_scheduler_enabled"]):
        raise PFRuntimeConfigurationError(
            "transition-value calibration requires packet scheduling")
    if (policy["pressure_resource_scheduler_enabled"]
            and not policy["pressure_packet_scheduler_enabled"]):
        raise PFRuntimeConfigurationError(
            "identity resource scheduling requires packet scheduling")
    if (policy["pressure_operation_lifecycle_enabled"]
            and not (
                policy[
                    "pressure_resource_scheduler_enabled"]
                and policy[
                    "pressure_domain_estimates_enabled"]
                and policy[
                    "pressure_commit_revalidation_enabled"])):
        raise PFRuntimeConfigurationError(
            "operation lifecycle requires identity resource scheduling, "
            "grounded domain estimates, and commit revalidation")
    if (policy["pressure_native_movement_routes_enabled"]
            and not (
                policy["pressure_domain_estimates_enabled"]
                and (
                    policy[
                        "pressure_city_defense_operations_enabled"]
                    or policy[
                        "pressure_transport_operations_enabled"]))):
        raise PFRuntimeConfigurationError(
            "native movement routes require grounded domain estimates "
            "and a city-defence or transport operation consumer")
    if (policy[
            "pressure_native_combat_probabilities_enabled"]
            and not policy[
                "pressure_domain_estimates_enabled"]):
        raise PFRuntimeConfigurationError(
            "native combat probabilities require grounded domain estimates")
    if (policy[
            "pressure_combat_operations_enabled"]
            and not (
                policy[
                    "pressure_native_combat_probabilities_enabled"]
                and policy[
                    "pressure_operation_lifecycle_enabled"]
                and policy[
                    "pressure_resource_scheduler_enabled"]
                and policy[
                    "pressure_requirement_sets_enabled"])):
        raise PFRuntimeConfigurationError(
            "combat operations require native combat probabilities, "
            "operation lifecycle, identity resource scheduling, and "
            "RequirementSets")
    if (policy[
            "pressure_transport_operations_enabled"]
            and not (
                policy[
                    "pressure_operation_lifecycle_enabled"]
                and policy[
                    "pressure_resource_scheduler_enabled"]
                and policy[
                    "pressure_requirement_sets_enabled"]
                and policy[
                    "pressure_domain_estimates_enabled"]
                and policy[
                    "pressure_native_movement_routes_enabled"])):
        raise PFRuntimeConfigurationError(
            "transport operations require native movement routes, "
            "operation lifecycle, identity resource scheduling, "
            "RequirementSets, and grounded domain estimates")
    if (policy[
            "pressure_production_operations_enabled"]
            and not (
                policy[
                    "pressure_operation_lifecycle_enabled"]
                and policy[
                    "pressure_resource_scheduler_enabled"]
                and policy[
                    "pressure_requirement_sets_enabled"]
                and policy[
                    "pressure_domain_estimates_enabled"])):
        raise PFRuntimeConfigurationError(
            "production operations require operation lifecycle, "
            "identity resource scheduling, RequirementSets, and "
            "grounded domain estimates")
    if (policy[
            "pressure_research_operations_enabled"]
            and not (
                policy[
                    "pressure_operation_lifecycle_enabled"]
                and policy[
                    "pressure_resource_scheduler_enabled"]
                and policy[
                    "pressure_requirement_sets_enabled"]
                and policy[
                    "pressure_domain_estimates_enabled"])):
        raise PFRuntimeConfigurationError(
            "research operations require operation lifecycle, "
            "identity resource scheduling, RequirementSets, and "
            "grounded domain estimates")
    if (policy["pressure_city_defense_operations_enabled"]
            and not policy[
                "pressure_operation_lifecycle_enabled"]):
        raise PFRuntimeConfigurationError(
            "city-defence operations require operation lifecycle")
    for name in (
            "pressure_transition_value_model_identity",
            "pressure_transition_value_model_path"):
        if not isinstance(policy[name], str):
            raise PFRuntimeConfigurationError(
                "{} must be a string".format(name))
    explicit_model = bool(
        policy[
            "pressure_transition_value_model_path"])
    explicit_identity = bool(
        policy[
            "pressure_transition_value_model_identity"])
    if explicit_model != explicit_identity:
        raise PFRuntimeConfigurationError(
            "transition-value model path and identity must be declared together")
    if (policy["pressure_transition_value_read_only"]
            and (
                not policy["pressure_transition_value_enabled"]
                or not explicit_model)):
        raise PFRuntimeConfigurationError(
            "frozen transition-value evaluation requires an enabled "
            "explicit model path and identity")
    if (policy["pressure_path_persistence_enabled"]
            and not policy[
                "pressure_transition_value_authority_enabled"]):
        raise PFRuntimeConfigurationError(
            "path persistence requires transition-value authority")
    if (policy["pressure_bridge_enabled"]
            and not policy["pressure_packet_scheduler_enabled"]):
        raise PFRuntimeConfigurationError(
            "pressure bridge requires packet scheduling")
    if (policy["pressure_controller_mode"] == "legacy_scalar"
            and policy["pressure_semantics_version"] != "v1"):
        raise PFRuntimeConfigurationError(
            "legacy_scalar mode requires pressure semantics v1")
    if (policy["pressure_controller_mode"] == "scalar_v2"
            and policy["pressure_semantics_version"] != "v2"):
        raise PFRuntimeConfigurationError(
            "scalar_v2 mode requires pressure semantics v2")
    if (policy["pressure_controller_mode"] == "canonical"
            and policy["pressure_flow_live_enabled"]):
        raise PFRuntimeConfigurationError(
            "canonical mode cannot enable live flow")
    if (policy["pressure_controller_mode"] in (
            "bridge_scalar", "unified_shadow",
            "bridge_scalar_advisory",
            "unified_flow_advisory",
            "unified_flow_live")
            and (
                policy["pressure_semantics_version"] != "v2"
                or not policy["pressure_bridge_enabled"]
                or not policy[
                    "pressure_packet_scheduler_enabled"])):
        raise PFRuntimeConfigurationError(
            "{} mode requires v2 bridge and packet scheduling".format(
                policy["pressure_controller_mode"]))
    if (policy["pressure_controller_mode"] in (
            "unified_shadow",
            "unified_flow_advisory",
            "unified_flow_live")
            and not policy["pressure_flow_enabled"]):
        raise PFRuntimeConfigurationError(
            "{} requires pressure flow".format(
                policy["pressure_controller_mode"]))
    if (policy["pressure_controller_mode"] == "unified_flow_live"
            and (
                not policy["pressure_flow_live_enabled"]
                or not policy[
                    "pressure_commit_revalidation_enabled"])):
        raise PFRuntimeConfigurationError(
            "unified_flow_live requires explicit live enablement "
            "and commit revalidation")
    if (policy["pressure_flow_live_enabled"]
            and policy["pressure_controller_mode"]
            != "unified_flow_live"):
        raise PFRuntimeConfigurationError(
            "live flow enablement requires unified_flow_live mode")
    if (policy["pressure_flow_enabled"]
            and (not policy["pressure_bridge_enabled"]
                 or not policy["pressure_packet_scheduler_enabled"])):
        raise PFRuntimeConfigurationError(
            "pressure flow requires bridge and packet scheduling")
    if policy["pressure_flow_research_entry_gate_required"]:
        if not policy[
                "pressure_flow_protected_candidate_union_enabled"]:
            raise PFRuntimeConfigurationError(
                "flow research gate requires protected candidate union")
        if not policy[
                "pressure_transition_value_authority_enabled"]:
            raise PFRuntimeConfigurationError(
                "flow research gate requires transition-value authority")
        if not policy[
                "pressure_path_persistence_enabled"]:
            raise PFRuntimeConfigurationError(
                "flow research gate requires path persistence comparator")
        if policy["pressure_bridge_readout_policy"] == (
                "corrected-probe-overlap"):
            raise PFRuntimeConfigurationError(
                "flow research gate requires decision-safe bridge readout")
    if (policy[
            "pressure_bridge_importance_corrected_enabled"]
            and not policy[
                "pressure_bridge_reference_likelihood_enabled"]):
        raise PFRuntimeConfigurationError(
            "importance-corrected probes require reference "
            "likelihood support")
    if policy[
            "pressure_shaping_capacity_structural_updates_enabled"]:
        raise PFRuntimeConfigurationError(
            "shaping capacities cannot authorize structural updates")
    if (policy["pressure_llm_expansion_enabled"]
            and policy[
                "pressure_llm_validation_packet_budget"] < 1):
        raise PFRuntimeConfigurationError(
            "LLM expansion requires validation packet budget")
    if (isinstance(
            policy["pressure_llm_validation_packet_budget"], bool)
            or not isinstance(
                policy[
                    "pressure_llm_validation_packet_budget"], int)
            or policy[
                "pressure_llm_validation_packet_budget"] < 0):
        raise PFRuntimeConfigurationError(
            "LLM validation packet budget must be non-negative")
    for name in (
            "pressure_bridge_estimator_policy",
            "pressure_bridge_normalization_contract"):
        if not isinstance(policy[name], str) or not policy[name]:
            raise PFRuntimeConfigurationError(
                "{} must be nonempty".format(name))
    if (not policy["pressure_enabled"]
            and any(policy[name] for name in (
                "pressure_achievement_uncertainty_split_enabled",
                "pressure_distributional_risk_enabled",
                "pressure_signed_channels_enabled",
                "pressure_packet_scheduler_enabled",
                "pressure_resource_scheduler_enabled",
                "pressure_native_movement_routes_enabled",
                "pressure_native_combat_probabilities_enabled",
                "pressure_combat_operations_enabled",
                "pressure_transport_operations_enabled",
                "pressure_production_operations_enabled",
                "pressure_research_operations_enabled",
                "pressure_city_defense_operations_enabled",
                "pressure_requirement_sets_enabled",
                "pressure_domain_estimates_enabled",
                "pressure_bridge_enabled",
                "pressure_flow_enabled",
                "pressure_flow_live_enabled"))):
        raise PFRuntimeConfigurationError(
            "disabled pressure cannot enable controller layers")
    return policy


def build_controller_activation(impact_policy):
    configuration = _validate_controller_configuration(
        _merged_controller_configuration(impact_policy))
    policy = validate_controller_policy(impact_policy)
    pressure_enabled = policy["pressure_enabled"]
    v2 = policy["pressure_semantics_version"] == "v2"
    mode = policy["pressure_controller_mode"]
    enabled = {
        "scalar_pf_v1": (
            pressure_enabled and not v2
            and mode != "canonical"),
        "scalar_pf_v2": (
            pressure_enabled and v2
            and mode != "canonical"),
        "grounded_domain_estimates": (
            pressure_enabled and v2
            and mode != "canonical"
            and policy[
                "pressure_domain_estimates_enabled"]),
        "packet_scheduler": (
            pressure_enabled and v2
            and policy["pressure_packet_scheduler_enabled"]),
        "identity_resource_scheduler": (
            pressure_enabled and v2
            and policy[
                "pressure_resource_scheduler_enabled"]),
        "operation_lifecycle": (
            pressure_enabled and v2
            and policy[
                "pressure_operation_lifecycle_enabled"]),
        "city_defense_operations": (
            pressure_enabled and v2
            and policy[
                "pressure_city_defense_operations_enabled"]),
        "native_movement_routes": (
            pressure_enabled and v2
            and policy[
                "pressure_native_movement_routes_enabled"]),
        "native_combat_probabilities": (
            pressure_enabled and v2
            and policy[
                "pressure_native_combat_probabilities_enabled"]),
        "combat_operations": (
            pressure_enabled and v2
            and policy[
                "pressure_combat_operations_enabled"]),
        "transport_operations": (
            pressure_enabled and v2
            and policy[
                "pressure_transport_operations_enabled"]),
        "production_operations": (
            pressure_enabled and v2
            and policy[
                "pressure_production_operations_enabled"]),
        "research_operations": (
            pressure_enabled and v2
            and policy[
                "pressure_research_operations_enabled"]),
        "teleological_cost_to_go": (
            pressure_enabled
            and (
                policy["pressure_transition_value_enabled"]
                or mode in (
                "bridge_scalar", "unified_shadow",
                "bridge_scalar_advisory",
                "unified_flow_advisory",
                "unified_flow_live"))),
        "path_persistence": (
            pressure_enabled and v2
            and policy[
                "pressure_path_persistence_enabled"]),
        "bridge": (
            pressure_enabled and v2
            and policy["pressure_bridge_enabled"]
            and mode in (
                "bridge_scalar", "unified_shadow",
                "bridge_scalar_advisory",
                "unified_flow_advisory",
                "unified_flow_live")),
        "source_sink_flow": (
            pressure_enabled and v2
            and policy["pressure_flow_enabled"]),
        "bounded_staleness_view": (
            pressure_enabled and v2
            and policy["pressure_flow_enabled"]),
        "decision_explanations": (
            pressure_enabled and mode
            not in ("canonical", "legacy_scalar")),
        "exact_commit_revalidation": (
            pressure_enabled and policy[
                "pressure_commit_revalidation_enabled"]),
        "native_flowpack": False,
    }
    layers = {}
    for spec in CONTROLLER_LAYER_SPECS:
        layer = spec["layer"]
        if enabled[layer]:
            reason = "enabled"
        elif spec["support"] in ("component-only", "not-built"):
            reason = spec["support"]
        elif not pressure_enabled:
            reason = "pressure-disabled"
        elif layer == "scalar_pf_v1" and v2:
            reason = "v2-selected"
        elif layer == "scalar_pf_v2" and not v2:
            reason = "v1-selected"
        else:
            reason = "feature-disabled"
        layers[layer] = {
            "enabled": bool(enabled[layer]),
            "reason": reason,
            "support": spec["support"],
        }
    value = {
        "artifact_schema_versions": {
            "control_decision": "1.0",
            "control_query": "1.0",
            "flow_patch": "1.0",
            "pressure": (
                "2.0" if v2 else "1.0"),
        },
        "configuration_groups": configuration,
        "controller_policy": policy,
        "estimator_policy": configuration[
            "bridge"]["estimator_policy"],
        "fallback_available": {
            "canonical": True,
            "legacy_scalar": True,
            "scalar_v2": v2,
        },
        "layers": layers,
        "normalization_contract": configuration[
            "bridge"]["normalization_contract"],
        "schema_version": CONTROLLER_SCHEMA_VERSION,
    }
    value["activation_hash"] = structural_hash(value)
    return value


def canonical_declaration(adapter=None):
    return {
        "adapter": adapter or LIVE_ADAPTER,
        "components": {
            row["component"]: {
                "phase": row["phase"],
                "support": row["support"],
            }
            for row in PHASE_SPECS
        },
        "schema_version": SCHEMA_VERSION,
    }


def validate_declaration(value, expected_adapter=None):
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
    expected_adapter = expected_adapter or LIVE_ADAPTER
    if value.get("adapter") != expected_adapter:
        raise PFRuntimeConfigurationError(
            "pf_pln_runtime.adapter must be {}".format(expected_adapter))
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
        declaration, backend, capabilities, impact_policy,
        expected_adapter=None):
    """Derive the exact per-game activation matrix."""
    declaration = validate_declaration(
        declaration,
        expected_adapter=expected_adapter)
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
