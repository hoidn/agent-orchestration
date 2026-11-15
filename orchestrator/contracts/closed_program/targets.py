"""Existing target admission and compiler schema facts shared without source access."""

CURRENT_TARGET_DSL_VERSION = "2.40"
EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION = "2.35"
# A wire value, not a source target: every path-mode run-reference config records this string, and the
# checker requires it. It is spelled on its own so that moving the evaluated-execution floor does not
# change recorded config bytes.
PATH_MODE_RUN_REF_TARGET_DSL_VERSION = "2.35"
PARALLEL_MAP_MIN_TARGET_DSL_VERSION = "2.37"
RUN_REF_CONFINED_MIN_TARGET_DSL_VERSION = "2.38"
AGENT_SESSIONS_MIN_TARGET_DSL_VERSION = "2.38"
DEFAULT_LOWERING_SCHEMA = 2

# Source admission (lane D stage 4, ruling R2): every module of a source graph declares the current target.
SUPPORTED_TARGET_DSL_VERSIONS = frozenset({CURRENT_TARGET_DSL_VERSION})
# Read-only labels (ruling R3): the checker reads a stored program at any of these targets, so `report`, the
# dashboard and the monitor read every recorded run; only a run at the current target is continued or rewritten.
READABLE_PROGRAM_TARGET_DSL_VERSIONS = frozenset({"2.35", "2.36", "2.37", "2.38", "2.39", CURRENT_TARGET_DSL_VERSION})
# The last release that compiles 2.35-2.39 source and continues runs recorded at those targets.
RETIRED_TARGETS_RELEASE = "v0.2.1"
MIGRATION_SECTION = "docs/lisp_workflow_drafting_guide.md#migrating-from-an-older-target"


def target_dsl_is_retired_label(target: object) -> bool:
    """Whether `target` is an older target this release reads in a stored program but no longer compiles."""

    return target in READABLE_PROGRAM_TARGET_DSL_VERSIONS and target != CURRENT_TARGET_DSL_VERSION


def retired_target_migration(target: str) -> str:
    """The sentence a refusal of 2.35-2.39 source adds: how to migrate, and which release still compiles it."""

    return (f"target DSL {target} is no longer compiled; migrate the source to {CURRENT_TARGET_DSL_VERSION} "
            f"({MIGRATION_SECTION}), or use the release tagged {RETIRED_TARGETS_RELEASE}")


def target_dsl_supports_parallel_map(target_dsl_version: str) -> bool:
    """Return whether a registered target admits the parallel map frontend."""

    return target_dsl_version in READABLE_PROGRAM_TARGET_DSL_VERSIONS and tuple(
        map(int, target_dsl_version.split("."))
    ) >= (2, 37)


def target_dsl_supports_run_ref_confined(target_dsl_version: str) -> bool:
    """Return whether a registered target admits `run-ref :program (:workflow ...)`."""

    return target_dsl_version in READABLE_PROGRAM_TARGET_DSL_VERSIONS and tuple(
        map(int, target_dsl_version.split("."))
    ) >= (2, 38)


def target_dsl_supports_agent_sessions(target_dsl_version: str) -> bool:
    """Return whether a registered target admits `agent`, `Agent` and agent turns."""

    return target_dsl_version in READABLE_PROGRAM_TARGET_DSL_VERSIONS and tuple(
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
    return target_dsl_version in READABLE_PROGRAM_TARGET_DSL_VERSIONS and tuple(map(int, target_dsl_version.split("."))) >= (2, 39)
