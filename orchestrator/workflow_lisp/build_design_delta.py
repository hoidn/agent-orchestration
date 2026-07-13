"""Temporary G8 deletion-evidence plumbing retained until Phase 4.

The Design Delta certification lane was retired after the family moved to its
generic Workflow Lisp route.  Only the G8 deletion proof remains here because
the parity machinery still consumes that artifact through the Phase-4 gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .build_manifest_io import _cli_request_diagnostic
from .diagnostics import LispFrontendCompileError
from .form_registry import get_form_spec


REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_DELTA_PARENT_DRAIN_COMMAND_BOUNDARIES_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)

DESIGN_DELTA_G8_REMOVED_MANIFEST_ROWS = (
    "classify_lisp_frontend_work_item_terminal",
    "select_lisp_frontend_blocked_recovery_route",
    "record_terminal_work_item",
    "record_blocked_recovery_outcome",
    "write_lisp_frontend_drain_status",
    "finalize_lisp_frontend_drain_summary",
)
DESIGN_DELTA_G8_REMOVED_SCRIPT_PATHS: tuple[str, ...] = ()
DESIGN_DELTA_G8_REMOVED_PYTHON_SYMBOLS = (
    "_ALLOWED_CONTEXT_RECORD_TYPES",
    "_STRUCTURAL_CONTEXT_RECORD_NAMES",
    "record_name_lane_fallback",
    "name_lane_fallback_counts",
    "clear_name_lane_fallback_counts",
)
DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS = (
    "with-phase",
    "finalize-selected-item",
    "backlog-drain",
)
DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS = ("with-phase", "backlog-drain")
DESIGN_DELTA_G8_RETAINED_BRIDGES = ("materialize_lisp_frontend_work_item_inputs",)
DESIGN_DELTA_G8_PRECONDITION_EVIDENCE_REFS = (
    "design_delta_work_item_terminal_ok",
    "design_delta_blocked_recovery_route_ok",
    "design_delta_record_terminal_ok",
    "design_delta_record_terminal_work_item_enum_bridge",
    "design_delta_record_blocked_recovery_ok",
    "design_delta_record_blocked_recovery_outcome_enum_bridge",
    "design_delta_drain_status_ok",
    "design_delta_drain_summary_ok",
)
DESIGN_DELTA_G8_GREP_GUARDS = (
    'rg -n "_ALLOWED_CONTEXT_RECORD_TYPES|_STRUCTURAL_CONTEXT_RECORD_NAMES|record_name_lane_fallback|name_lane_fallback_counts|clear_name_lane_fallback_counts" orchestrator/workflow_lisp orchestrator/workflow',
    'rg -n "TEMP_COMPILER_INTRINSIC" orchestrator/workflow_lisp',
    'rg -n "with-phase|finalize-selected-item|backlog-drain" orchestrator/workflow_lisp/form_registry.py orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/wcc',
    'rg -n "classify_lisp_frontend_work_item_terminal|select_lisp_frontend_blocked_recovery_route|record_terminal_work_item|record_blocked_recovery_outcome|write_lisp_frontend_drain_status|finalize_lisp_frontend_drain_summary" workflows/examples/inputs/workflow_lisp_migrations tests workflows/library',
)
DESIGN_DELTA_G8_VERIFICATION_COMMANDS = (
    "python -m pytest tests/test_workflow_lisp_context_classification.py -q",
    "python -m pytest tests/test_workflow_lisp_stdlib_form_migration.py -q",
    'python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_parent_drain or boundary_authority or adapter_census" -q',
    'python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_family_commands_use_production_adapter_interfaces or design_delta_parent_drain" -q',
    'python -m pytest tests/test_workflow_lisp_migration_parity.py -k "design_delta_parent_drain or adapter_census or boundary_authority" -q',
    'python -m pytest tests/test_workflow_lisp_command_adapters.py -k "design_delta_parent_drain or retirement" -q',
    "python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json",
)


def serialize_design_delta_g8_deletion_evidence(
    *,
    command_boundary_manifest: Mapping[str, object],
) -> dict[str, object]:
    """Serialize the temporary G8 proof without loading certification inputs."""

    present_deleted_rows = sorted(
        row_name
        for row_name in DESIGN_DELTA_G8_REMOVED_MANIFEST_ROWS
        if row_name in command_boundary_manifest
    )
    if present_deleted_rows:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="design_delta_g8_deleted_manifest_row_present",
                    message=(
                        "design-delta G8 deletion evidence cannot pass while deleted manifest "
                        f"rows remain active: {', '.join(present_deleted_rows)}"
                    ),
                    path=DESIGN_DELTA_PARENT_DRAIN_COMMAND_BOUNDARIES_PATH,
                ),
            )
        )
    missing_retained_bridges = sorted(
        bridge_name
        for bridge_name in DESIGN_DELTA_G8_RETAINED_BRIDGES
        if bridge_name not in command_boundary_manifest
    )
    if missing_retained_bridges:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="design_delta_g8_retained_bridge_missing",
                    message=(
                        "design-delta G8 deletion evidence requires retained bridge rows to "
                        f"remain explicit: {', '.join(missing_retained_bridges)}"
                    ),
                    path=DESIGN_DELTA_PARENT_DRAIN_COMMAND_BOUNDARIES_PATH,
                ),
            )
        )
    present_removed_heads = []
    for head_name in DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS:
        spec = get_form_spec(head_name)
        if spec is None:
            continue
        if "compatibility_route_only" in getattr(spec, "feature_tags", frozenset()):
            continue
        if (
            head_name in DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS
            and getattr(spec, "macro_bindable", False)
        ):
            continue
        present_removed_heads.append(head_name)
    present_removed_heads.sort()
    if present_removed_heads:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="design_delta_g8_removed_registry_head_present",
                    message=(
                        "design-delta G8 deletion evidence cannot pass while deleted public "
                        f"registry heads remain callable: {', '.join(present_removed_heads)}"
                    ),
                    path=DESIGN_DELTA_PARENT_DRAIN_COMMAND_BOUNDARIES_PATH,
                ),
            )
        )
    return {
        "schema_version": "workflow_lisp_design_delta_g8_deletion_evidence.v1",
        "workflow_family": "design_delta_parent_drain",
        "removed_manifest_rows": list(DESIGN_DELTA_G8_REMOVED_MANIFEST_ROWS),
        "removed_script_paths": list(DESIGN_DELTA_G8_REMOVED_SCRIPT_PATHS),
        "removed_python_symbols": list(DESIGN_DELTA_G8_REMOVED_PYTHON_SYMBOLS),
        "removed_registry_heads": list(DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS),
        "retained_bridges": list(DESIGN_DELTA_G8_RETAINED_BRIDGES),
        "precondition_evidence_refs": list(DESIGN_DELTA_G8_PRECONDITION_EVIDENCE_REFS),
        "grep_guards": list(DESIGN_DELTA_G8_GREP_GUARDS),
        "verification_commands": list(DESIGN_DELTA_G8_VERIFICATION_COMMANDS),
        "line_count_delta": {
            "removed_manifest_row_count": len(DESIGN_DELTA_G8_REMOVED_MANIFEST_ROWS),
            "removed_script_path_count": len(DESIGN_DELTA_G8_REMOVED_SCRIPT_PATHS),
            "removed_python_symbol_count": len(DESIGN_DELTA_G8_REMOVED_PYTHON_SYMBOLS),
            "removed_registry_head_count": len(DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS),
        },
        "hook_surface_delta": {
            "removed_registry_heads": list(DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS),
            "imported_only_registry_heads": list(
                DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS
            ),
            "name_lane_fallback_removed": True,
            "literal_executor_family_allowlist_removed": True,
        },
        "adapter_surface_delta": {
            "removed_manifest_rows": list(DESIGN_DELTA_G8_REMOVED_MANIFEST_ROWS),
            "retained_bridges": list(DESIGN_DELTA_G8_RETAINED_BRIDGES),
            "removed_manifest_row_count": len(DESIGN_DELTA_G8_REMOVED_MANIFEST_ROWS),
        },
        "status": "pass",
    }
