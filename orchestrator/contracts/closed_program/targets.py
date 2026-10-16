"""Existing target admission and lowering schema facts shared without source access."""

EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION = "2.35"
LOWERING_SCHEMA_LEGACY = 1
LOWERING_SCHEMA_WCC = 2
DEFAULT_LOWERING_SCHEMA = LOWERING_SCHEMA_WCC

SUPPORTED_TARGET_DSL_VERSIONS = frozenset(
    {
        "2.14",
        "2.15",
        "2.16",
        "2.17",
        "2.18",
        "2.19",
        "2.20",
        "2.21",
        "2.22",
        "2.23",
        "2.24",
        "2.25",
        "2.26",
        "2.27",
        "2.28",
        "2.29",
        "2.30",
        "2.31",
        "2.32",
        "2.33",
        "2.34",
        "2.35",
        "2.36",
        "3.0",
    }
)


NESTED_STRUCTURAL_TRANSPORT_MIN_TARGET_DSL_VERSION = "2.25"


FINITE_FLOAT_BOUNDARY_MIN_TARGET_DSL_VERSION = "2.34"


def target_dsl_refuses_non_finite_floats(target_dsl_version: str) -> bool:
    """Return whether a target refuses a non-finite `Float` where it enters a run."""

    try:
        target = tuple(int(part) for part in target_dsl_version.split("."))
        minimum = tuple(
            int(part)
            for part in FINITE_FLOAT_BOUNDARY_MIN_TARGET_DSL_VERSION.split(".")
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return target >= minimum


def target_dsl_uses_evaluated_execution(target_dsl_version: str) -> bool:
    """Return whether a target routes execution through the evaluated runtime."""
    return target_dsl_version in {"2.35", "2.36"}


def target_dsl_supports_nested_structural_transport(
    target_dsl_version: str,
) -> bool:
    """Return whether authored nested record/union transport is available."""

    try:
        target = tuple(int(part) for part in target_dsl_version.split("."))
        minimum = tuple(
            int(part)
            for part in NESTED_STRUCTURAL_TRANSPORT_MIN_TARGET_DSL_VERSION.split(
                "."
            )
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return target >= minimum
