"""Existing target admission and compiler schema facts shared without source access."""

EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION = "2.35"
PARALLEL_MAP_MIN_TARGET_DSL_VERSION = "2.37"
RUN_REF_CONFINED_MIN_TARGET_DSL_VERSION = "2.38"
AGENT_SESSIONS_MIN_TARGET_DSL_VERSION = "2.38"
DEFAULT_LOWERING_SCHEMA = 2

SUPPORTED_TARGET_DSL_VERSIONS = frozenset(
    {"2.35", "2.36", "2.37", "2.38", "2.39", "2.40"}
)


def target_dsl_supports_parallel_map(target_dsl_version: str) -> bool:
    """Return whether a registered target admits the parallel map frontend."""

    return target_dsl_version in SUPPORTED_TARGET_DSL_VERSIONS and tuple(
        map(int, target_dsl_version.split("."))
    ) >= (2, 37)


def target_dsl_supports_run_ref_confined(target_dsl_version: str) -> bool:
    """Return whether a registered target admits `run-ref :program (:workflow ...)`."""

    return target_dsl_version in SUPPORTED_TARGET_DSL_VERSIONS and tuple(
        map(int, target_dsl_version.split("."))
    ) >= (2, 38)


def target_dsl_supports_agent_sessions(target_dsl_version: str) -> bool:
    """Return whether a registered target admits `agent`, `Agent` and agent turns."""

    return target_dsl_version in SUPPORTED_TARGET_DSL_VERSIONS and tuple(
        map(int, target_dsl_version.split("."))
    ) >= (2, 38)


def target_dsl_uses_evaluated_execution(target_dsl_version: str) -> bool:
    """Return whether a target routes execution through the evaluated runtime."""

    try:
        target = tuple(int(part) for part in target_dsl_version.split("."))
        minimum = tuple(
            int(part)
            for part in EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION.split(".")
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return target >= minimum


def target_dsl_supports_effect_ceilings(target_dsl_version: str) -> bool:
    """Whether authored procedures use inference-default optional restrictions."""
    return target_dsl_version in SUPPORTED_TARGET_DSL_VERSIONS and tuple(map(int, target_dsl_version.split("."))) >= (2, 39)
