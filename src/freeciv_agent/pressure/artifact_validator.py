"""Fail-closed structural validation for v1/v2 pressure artifacts."""

from ..events.schema import structural_hash


class PressureArtifactValidationError(ValueError):
    pass


_CHANNELS = frozenset(("infer", "observe", "act", "expand", "retain"))


def pressure_dependency_view(value):
    """Return the action-bearing dependency rail for v1 or v2 artifacts."""
    if not isinstance(value, dict):
        raise PressureArtifactValidationError(
            "pressure artifact must be an object")
    version = value.get(
        "pressure_artifact_schema", "1.0")
    if version not in ("1.0", "2.0"):
        raise PressureArtifactValidationError(
            "unsupported pressure artifact schema {}".format(
                version))
    name = (
        "action_dependency"
        if version == "2.0"
        else "dependency")
    dependency = value.get(name)
    if not isinstance(dependency, dict):
        raise PressureArtifactValidationError(
            "{} pressure artifact requires {}".format(
                version, name))
    return dependency


def active_pressure_goal_count(value):
    """Count goals with positive action-bearing dependency demand."""
    dependency = pressure_dependency_view(value)
    count = 0
    for atoms in dependency.values():
        if not isinstance(atoms, dict):
            raise PressureArtifactValidationError(
                "pressure dependency rows must be objects")
        if any(
                isinstance(amount, bool)
                or not isinstance(
                    amount, (int, float))
                for amount in atoms.values()):
            raise PressureArtifactValidationError(
                "pressure dependency demand must be numeric")
        if any(
                float(amount) > 0.0
                for amount in atoms.values()):
            count += 1
    return count


def _validate_magnitude(value, path):
    if not isinstance(value, dict) or set(value) != _CHANNELS:
        raise PressureArtifactValidationError(
            "{} must contain exactly the five pressure channels".format(
                path))
    if any(isinstance(amount, bool)
           or not isinstance(amount, (int, float))
           or float(amount) < 0.0
           for amount in value.values()):
        raise PressureArtifactValidationError(
            "{} channel pressure must be non-negative numeric".format(path))


def _validate_v1_vector(value, path):
    if not isinstance(value, dict) or set(value) != (
            _CHANNELS | {"direction"}):
        raise PressureArtifactValidationError(
            "{} is not a v1 pressure vector".format(path))
    _validate_magnitude(
        dict((key, value[key]) for key in _CHANNELS), path)
    if not -1.0 <= float(value["direction"]) <= 1.0:
        raise PressureArtifactValidationError(
            "{} direction must be in [-1,1]".format(path))


def _validate_v2_vector(value, path):
    if not isinstance(value, dict) or set(value) != {
            "positive", "negative"}:
        raise PressureArtifactValidationError(
            "{} is not a signed v2 pressure vector".format(path))
    _validate_magnitude(value["positive"], path + ".positive")
    _validate_magnitude(value["negative"], path + ".negative")


def validate_pressure_artifact(value):
    if not isinstance(value, dict):
        raise PressureArtifactValidationError(
            "pressure artifact must be an object")
    version = value.get("pressure_artifact_schema", "1.0")
    if version not in ("1.0", "2.0"):
        raise PressureArtifactValidationError(
            "unsupported pressure artifact schema {}".format(version))
    pressure = value.get("pressure")
    if not isinstance(pressure, dict):
        raise PressureArtifactValidationError(
            "pressure artifact requires pressure rows")
    validator = (
        _validate_v1_vector if version == "1.0"
        else _validate_v2_vector)
    for goal_id, atoms in pressure.items():
        if not isinstance(goal_id, str) or not isinstance(atoms, dict):
            raise PressureArtifactValidationError(
                "pressure rows must map goal and atom IDs")
        for atom_id, vector in atoms.items():
            validator(
                vector, "pressure.{}.{}".format(goal_id, atom_id))
    if version == "2.0":
        required = {
            "achievement_dependency", "achievement_pressure",
            "coalition_semantics", "demands",
            "epistemic_dependency", "epistemic_pressure",
            "pressure_representation", "teleology_semantics",
        }
        missing = sorted(required - set(value))
        if missing:
            raise PressureArtifactValidationError(
                "v2 pressure artifact missing {}".format(missing))
        if value["pressure_representation"] != (
                "signed-channel-rails/1.0"):
            raise PressureArtifactValidationError(
                "unsupported v2 pressure representation")
    return {
        "artifact_hash": structural_hash(value),
        "pressure_artifact_schema": version,
        "valid": True,
    }


def validate_packet_schedule(value):
    if not isinstance(value, dict):
        raise PressureArtifactValidationError(
            "packet schedule must be an object")
    required = {
        "accounting", "budgets", "committed_operation_ids",
        "committed_value", "conserved", "integrality_gap",
        "relaxed_value", "reservations", "scheduler_identity",
        "stranded_quanta",
    }
    missing = sorted(required - set(value))
    if missing:
        raise PressureArtifactValidationError(
            "packet schedule missing {}".format(missing))
    if value["scheduler_identity"] != "pf-pln-packet-scheduler/2.0":
        raise PressureArtifactValidationError(
            "unsupported packet scheduler identity")
    if value["conserved"] is not True:
        raise PressureArtifactValidationError(
            "packet accounting is not conserved")
    committed = tuple(value["committed_operation_ids"])
    reservation_committed = tuple(
        row["operation_id"] for row in value["reservations"]
        if row.get("state") == "committed")
    if committed != reservation_committed:
        raise PressureArtifactValidationError(
            "packet committed IDs do not match reservations")
    return {
        "artifact_hash": structural_hash(value),
        "scheduler_identity": value["scheduler_identity"],
        "valid": True,
    }
