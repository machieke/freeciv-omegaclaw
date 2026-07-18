"""Runtime capability gates shared by the agent and evaluation harness."""

from .config import condition


class CapabilityDisabled(RuntimeError):
    pass


def require(condition_id, capability, config_path=None):
    row = condition(condition_id, config_path)
    if capability not in row["capabilities"]:
        raise ValueError("unknown capability: {}".format(capability))
    if not row["capabilities"][capability]:
        raise CapabilityDisabled(
            "condition {} disables capability {}".format(condition_id, capability))
    return True


def assert_only(condition_id, requested, config_path=None):
    """Reject code paths not allowed by a condition's immutable capability row."""
    row = condition(condition_id, config_path)
    requested = set(requested)
    unknown = requested - set(row["capabilities"])
    if unknown:
        raise ValueError("unknown capabilities: {}".format(sorted(unknown)))
    denied = sorted(name for name in requested if not row["capabilities"][name])
    if denied:
        raise CapabilityDisabled(
            "condition {} denies requested capabilities {}".format(condition_id, denied))
    return True

