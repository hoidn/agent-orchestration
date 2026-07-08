"""Design-delta certification lane: loaders, provenance, compatibility-bridge
materialization, and report serializers for the Workflow Lisp build.

Extracted from build.py. Every function here is gated on the design-delta family
or the `lisp_frontend_design_delta/drain::drain` entry; this module is the excision
unit for retiring the certification lane (delete the file + its two call sites in
build_frontend_bundle + one DesignDeltaEvidence field).

Behavior is byte-identical to the pre-split build.py definitions — no gate or raise
was edited during the move; the only textual addition versus the pre-split bodies
is the deferred imports described below. See CLAUDE.md frozen-surface rules.

May import build_manifest_io; must not create a top-level import against build
(one-way dependency: build -> build_design_delta -> build_manifest_io). The
DESIGN_DELTA_PARENT_DRAIN_*_PATH constants (used by both this module's loaders and
build.py's build_frontend_bundle) and get_form_spec stay defined in build.py because
tests monkeypatch them as `build.<name>`; a handful of functions below read them via
a deferred, function-body `from .build import ...` so those monkeypatches remain
observable (mirrors the precedent set by build_manifest_io._resolve_request's
deferred FrontendBuildRequest import). The two retirement-serializer functions use
the same deferred-import technique to reach two general per-build helpers
(`_public_runtime_plan_payload`, `_serialize_lexical_checkpoint_points`/
`_serialize_lexical_checkpoint_shadow_report`) that stay in build.py because every
build (not just design-delta) uses them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.references import MaterializeViewBindingReference
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow.state_layout import (
    GeneratedPathAllocation,
    GeneratedPathPrivacy,
    GeneratedPathResumeScope,
    GeneratedPathSemanticRole,
)
from orchestrator.workflow.surface_ast import SurfaceStep, SurfaceStepKind, WorkflowProvenance
from orchestrator.workflow.view_renderer import (
    VIEW_RENDERER_SCHEMA_VERSION,
    resolve_view_renderer,
)

from .build_manifest_io import (
    _cli_request_diagnostic,
    _json_data,
    _load_json_file,
    _sha256_path,
)
from .command_boundaries import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
)
from .consumer_rendering_census import load_consumer_rendering_census
from .compatibility_bridges import load_compatibility_bridge_manifest
from .diagnostics import LispFrontendCompileError
from .family_profiles import (
    WorkflowFamilyProfileCatalog,
    load_workflow_family_profile_catalog,
)
from .lexical_checkpoints import (
    CHECKPOINT_POINTS_SCHEMA_VERSION,
    CHECKPOINT_RECORD_SCHEMA_VERSION,
    CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION,
)
from .phase_family_boundary import (
    build_design_delta_boundary_authority_expected_rows,
    is_design_delta_parent_drain_target_workflow,
    load_design_delta_boundary_authority_registry,
)
from .observability_summaries import (
    OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID,
    build_observability_pair_report,
    load_old_writer_pair_manifest,
    row_requires_old_writer_contract_evidence,
)
from . import resume_plumbing_retirement
from .rendering_cleanup import load_rendering_cleanup_manifest
from .rendering_ergonomics import load_rendering_ergonomics_policy
from .transition_authoring import load_transition_authoring_manifest
from .value_flow_census import load_value_flow_census


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
DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS = ("with-phase",)
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
    "rg -n \"_ALLOWED_CONTEXT_RECORD_TYPES|_STRUCTURAL_CONTEXT_RECORD_NAMES|record_name_lane_fallback|name_lane_fallback_counts|clear_name_lane_fallback_counts\" orchestrator/workflow_lisp orchestrator/workflow",
    "rg -n \"TEMP_COMPILER_INTRINSIC\" orchestrator/workflow_lisp",
    "rg -n \"with-phase|finalize-selected-item|backlog-drain\" orchestrator/workflow_lisp/form_registry.py orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/wcc",
    "rg -n \"classify_lisp_frontend_work_item_terminal|select_lisp_frontend_blocked_recovery_route|record_terminal_work_item|record_blocked_recovery_outcome|write_lisp_frontend_drain_status|finalize_lisp_frontend_drain_summary\" workflows/examples/inputs/workflow_lisp_migrations tests workflows/library",
)
DESIGN_DELTA_G8_VERIFICATION_COMMANDS = (
    "python -m pytest tests/test_workflow_lisp_context_classification.py -q",
    "python -m pytest tests/test_workflow_lisp_stdlib_form_migration.py -q",
    "python -m pytest tests/test_workflow_lisp_build_artifacts.py -k \"design_delta_parent_drain or boundary_authority or adapter_census\" -q",
    "python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k \"design_delta_parent_family_commands_use_production_adapter_interfaces or design_delta_parent_drain\" -q",
    "python -m pytest tests/test_workflow_lisp_migration_parity.py -k \"design_delta_parent_drain or adapter_census or boundary_authority\" -q",
    "python -m pytest tests/test_workflow_lisp_command_adapters.py -k \"design_delta_parent_drain or retirement\" -q",
    "python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json",
)


def _maybe_load_design_delta_family_profile_catalog(
    *,
    entry_workflow: str | None,
    source_path: Path,
) -> WorkflowFamilyProfileCatalog | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE_PATH

    if not _is_design_delta_family_profile_candidate(
        entry_workflow=entry_workflow,
        source_path=source_path,
    ):
        return None
    try:
        return load_workflow_family_profile_catalog(
            (DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE_PATH,)
        )
    except LispFrontendCompileError as exc:
        raise exc
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_family_profile_schema_invalid",
                    message=f"design-delta family profile is invalid: {exc}",
                    path=DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE_PATH,
                ),
            )
        ) from exc


def _is_design_delta_family_profile_candidate(
    *,
    entry_workflow: str | None,
    source_path: Path,
) -> bool:
    if entry_workflow is not None and entry_workflow.startswith(
        "lisp_frontend_design_delta/"
    ):
        return True
    if "lisp_frontend_design_delta" in source_path.parts:
        return True
    try:
        return "lisp_frontend_design_delta/" in source_path.read_text(encoding="utf-8")
    except OSError:
        return False


def _family_profile_metadata_for_entry(
    family_profile_catalog: WorkflowFamilyProfileCatalog | None,
    entry_workflow: str,
) -> Mapping[str, object] | None:
    if family_profile_catalog is None:
        return None
    profile = family_profile_catalog.profile_for_workflow(entry_workflow)
    if profile is None:
        return None
    return {
        "family_id": profile.family_id,
        "path": str(profile.source_path),
        "digest": _sha256_path(profile.source_path),
    }


def _maybe_load_design_delta_boundary_authority_registry(
    *,
    entry_workflow: str,
    family_profile_catalog: WorkflowFamilyProfileCatalog | None,
) -> Mapping[str, object] | None:
    if family_profile_catalog is None or not is_design_delta_parent_drain_target_workflow(
        entry_workflow,
        family_profile_catalog=family_profile_catalog,
    ):
        return None
    profile = family_profile_catalog.profile_for_workflow(entry_workflow)
    if profile is None or profile.boundary_authority_registry_path is None:
        return None
    try:
        payload = load_design_delta_boundary_authority_registry(
            profile.boundary_authority_registry_path,
            target_workflows=profile.target_workflows,
        )
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_family_profile_boundary_registry_invalid",
                    message=f"design-delta boundary authority registry is invalid: {exc}",
                    path=profile.boundary_authority_registry_path,
                ),
            )
        ) from exc
    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        payload = {
            **payload,
            "rows": [
                row
                for row in payload.get("rows", [])
                if isinstance(row, Mapping)
                and row.get("workflow_name") == entry_workflow
            ],
        }
    return {
        **payload,
        "__registry_path__": str(profile.boundary_authority_registry_path),
        "__registry_sha256__": _sha256_path(profile.boundary_authority_registry_path),
        "workflow_family": profile.family_id,
    }


def _maybe_load_design_delta_value_flow_census(
    *,
    entry_workflow: str,
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_VALUE_FLOW_CENSUS_PATH

    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    try:
        payload = load_value_flow_census(DESIGN_DELTA_PARENT_DRAIN_VALUE_FLOW_CENSUS_PATH)
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="value_flow_census_invalid",
                    message=f"design-delta value-flow census is invalid: {exc}",
                    path=DESIGN_DELTA_PARENT_DRAIN_VALUE_FLOW_CENSUS_PATH,
                ),
            )
        ) from exc
    return {
        **payload,
        "__census_path__": str(DESIGN_DELTA_PARENT_DRAIN_VALUE_FLOW_CENSUS_PATH),
        "__census_sha256__": _sha256_path(DESIGN_DELTA_PARENT_DRAIN_VALUE_FLOW_CENSUS_PATH),
    }


def _maybe_load_design_delta_transition_authoring_manifest(
    *,
    entry_workflow: str,
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_TRANSITION_AUTHORING_PATH

    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    try:
        return load_transition_authoring_manifest(
            DESIGN_DELTA_PARENT_DRAIN_TRANSITION_AUTHORING_PATH
        )
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="transition_authoring_manifest_invalid",
                    message=f"design-delta transition authoring manifest is invalid: {exc}",
                    path=DESIGN_DELTA_PARENT_DRAIN_TRANSITION_AUTHORING_PATH,
                ),
            )
        ) from exc


def _maybe_load_design_delta_consumer_rendering_census(
    *,
    entry_workflow: str,
    value_flow_census: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_CONSUMER_RENDERING_CENSUS_PATH

    if value_flow_census is None:
        return None
    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    try:
        return load_consumer_rendering_census(
            DESIGN_DELTA_PARENT_DRAIN_CONSUMER_RENDERING_CENSUS_PATH,
            value_flow_census=value_flow_census,
        )
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="consumer_rendering_census_invalid",
                    message=f"design-delta consumer rendering census is invalid: {exc}",
                    path=DESIGN_DELTA_PARENT_DRAIN_CONSUMER_RENDERING_CENSUS_PATH,
                ),
            )
        ) from exc


def _maybe_load_design_delta_observability_old_writer_pair_manifest(
    *,
    entry_workflow: str,
    consumer_rendering_census: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH

    if consumer_rendering_census is None:
        return None
    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    try:
        return load_old_writer_pair_manifest(
            DESIGN_DELTA_PARENT_DRAIN_OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH,
            consumer_rendering_census=consumer_rendering_census,
        )
    except (OSError, ValueError) as exc:
        message = str(exc)
        error_code = message.split(":", 1)[0] if ":" in message else message
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code=error_code or "observability_summary_old_writer_evidence_stale",
                    message=(
                        "design-delta observability old-writer pair evidence is invalid: "
                        f"{exc}"
                    ),
                    path=DESIGN_DELTA_PARENT_DRAIN_OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH,
                ),
            )
        ) from exc


def _maybe_load_design_delta_compatibility_bridge_manifest(
    *,
    entry_workflow: str,
    value_flow_census: Mapping[str, object] | None,
    consumer_rendering_census: Mapping[str, object] | None,
    command_boundary_manifest: Mapping[str, object],
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_COMPATIBILITY_BRIDGES_PATH

    if value_flow_census is None or consumer_rendering_census is None:
        return None
    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    try:
        return load_compatibility_bridge_manifest(
            DESIGN_DELTA_PARENT_DRAIN_COMPATIBILITY_BRIDGES_PATH,
            value_flow_census=value_flow_census,
            consumer_rendering_census=consumer_rendering_census,
            command_boundary_manifest=command_boundary_manifest,
        )
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="compatibility_bridge_metadata_invalid",
                    message=f"design-delta compatibility bridge metadata is invalid: {exc}",
                    path=DESIGN_DELTA_PARENT_DRAIN_COMPATIBILITY_BRIDGES_PATH,
                ),
            )
        ) from exc


def _maybe_load_design_delta_rendering_cleanup_manifest(
    *,
    entry_workflow: str,
    consumer_rendering_census: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_RENDERING_CLEANUP_PATH

    if consumer_rendering_census is None:
        return None
    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    try:
        return load_rendering_cleanup_manifest(
            DESIGN_DELTA_PARENT_DRAIN_RENDERING_CLEANUP_PATH,
            consumer_rendering_census=consumer_rendering_census,
        )
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="rendering_cleanup_manifest_invalid",
                    message=f"design-delta rendering cleanup manifest is invalid: {exc}",
                    path=DESIGN_DELTA_PARENT_DRAIN_RENDERING_CLEANUP_PATH,
                ),
            )
        ) from exc


def _maybe_load_design_delta_rendering_ergonomics_manifest(
    *,
    entry_workflow: str,
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_RENDERING_ERGONOMICS_PATH

    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    try:
        return load_rendering_ergonomics_policy(
            DESIGN_DELTA_PARENT_DRAIN_RENDERING_ERGONOMICS_PATH,
        )
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="rendering_ergonomics_policy_schema_invalid",
                    message=(
                        "design-delta rendering ergonomics manifest is invalid: "
                        f"{exc}"
                    ),
                    path=DESIGN_DELTA_PARENT_DRAIN_RENDERING_ERGONOMICS_PATH,
                ),
            )
        ) from exc


def _maybe_load_design_delta_view_dual_run_vectors(
    *,
    entry_workflow: str,
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_VECTORS_PATH

    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    if not DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_VECTORS_PATH.is_file():
        return None
    payload = _load_json_file(
        DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_VECTORS_PATH,
        label="design-delta view dual-run vectors",
    )
    if not isinstance(payload, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="consumer_rendering_census_invalid",
                    message="design-delta view dual-run vectors must be a JSON object",
                    path=DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_VECTORS_PATH,
                ),
            )
        )
    return dict(payload)


def _maybe_load_design_delta_view_dual_run_report(
    *,
    entry_workflow: str,
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_REPORT_PATH

    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    if not DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_REPORT_PATH.is_file():
        return None
    payload = _load_json_file(
        DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_REPORT_PATH,
        label="design-delta view dual-run report",
    )
    if not isinstance(payload, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="consumer_rendering_census_invalid",
                    message="design-delta view dual-run report must be a JSON object",
                    path=DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_REPORT_PATH,
                ),
            )
        )
    return dict(payload)


def _maybe_load_design_delta_resume_plumbing_retirement_manifest(
    *,
    entry_workflow: str,
) -> Mapping[str, object] | None:
    from .build import DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH

    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    if not DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH.is_file():
        return None
    try:
        payload = resume_plumbing_retirement.load_resume_plumbing_retirement_manifest(
            DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH
        )
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="resume_plumbing_retirement_invalid",
                    message=(
                        "design-delta resume plumbing retirement manifest is invalid: "
                        f"{exc}"
                    ),
                    path=DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH,
                ),
            )
        ) from exc
    return {
        **payload,
        "__manifest_path__": str(
            DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH
        ),
        "__manifest_sha256__": _sha256_path(
            DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH
        ),
    }


def _boundary_authority_registry_provenance(
    boundary_authority_registry: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if boundary_authority_registry is None:
        return None
    return {
        "workflow_family": str(boundary_authority_registry.get("workflow_family", "")),
        "path": str(boundary_authority_registry.get("__registry_path__", "")),
        "sha256": f"sha256:{boundary_authority_registry.get('__registry_sha256__', '')}",
        "schema_version": str(boundary_authority_registry.get("schema_version", "")),
    }


def _value_flow_census_provenance(
    value_flow_census: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if value_flow_census is None:
        return None
    return {
        "workflow_family": "design_delta_parent_drain",
        "path": str(value_flow_census.get("__census_path__", "")),
        "sha256": f"sha256:{value_flow_census.get('__census_sha256__', '')}",
        "schema_version": str(value_flow_census.get("schema_version", "")),
    }


def _consumer_rendering_census_provenance(
    consumer_rendering_census: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if consumer_rendering_census is None:
        return None
    return {
        "workflow_family": "design_delta_parent_drain",
        "path": str(consumer_rendering_census.get("__manifest_path__", "")),
        "sha256": f"sha256:{consumer_rendering_census.get('__manifest_sha256__', '')}",
        "schema_version": str(consumer_rendering_census.get("schema_version", "")),
    }


def _observability_old_writer_pair_provenance(
    observability_old_writer_pair_manifest: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if observability_old_writer_pair_manifest is None:
        return None
    legacy_payload_sources: list[dict[str, object]] = []
    for row in observability_old_writer_pair_manifest.get("row_pairs", []):
        if not isinstance(row, Mapping):
            continue
        legacy_source = row.get("legacy_payload_source")
        if not isinstance(legacy_source, Mapping):
            continue
        legacy_payload_sources.append(_json_data(legacy_source))
    return {
        "workflow_family": "design_delta_parent_drain",
        "path": str(observability_old_writer_pair_manifest.get("__manifest_path__", "")),
        "sha256": (
            f"sha256:{observability_old_writer_pair_manifest.get('__manifest_sha256__', '')}"
            if observability_old_writer_pair_manifest.get("__manifest_sha256__")
            else ""
        ),
        "schema_version": str(
            observability_old_writer_pair_manifest.get("schema_version", "")
        ),
        "legacy_payload_sources": legacy_payload_sources,
    }


def _materialize_design_delta_compatibility_bridge_bundles(
    *,
    selected_bundle: LoadedWorkflowBundle,
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    selected_provenance: WorkflowProvenance,
    compatibility_bridge_manifest: Mapping[str, Any] | None,
) -> tuple[LoadedWorkflowBundle, Mapping[str, LoadedWorkflowBundle]]:
    if not isinstance(compatibility_bridge_manifest, Mapping):
        return (
            build_loaded_workflow_bundle(
                replace(selected_bundle.surface, provenance=selected_provenance),
                imports=selected_bundle.imports,
                private_artifact_ids=tuple(selected_bundle.ir.private_artifacts),
            ),
            dict(validated_bundles_by_name),
        )

    rows_by_workflow: dict[str, list[Mapping[str, Any]]] = {}
    for raw_row in compatibility_bridge_manifest.get("bridges", []):
        if not isinstance(raw_row, Mapping):
            continue
        if isinstance(raw_row.get("command_boundary"), Mapping):
            continue
        workflow_name = str(raw_row.get("workflow_surface", ""))
        if not workflow_name:
            continue
        rows_by_workflow.setdefault(workflow_name, []).append(raw_row)

    original_by_name = {
        str(name): bundle for name, bundle in validated_bundles_by_name.items() if isinstance(name, str)
    }
    memo: dict[str, LoadedWorkflowBundle] = {}
    visiting: set[str] = set()

    def transform_bundle(
        workflow_name: str,
        *,
        provenance_override: WorkflowProvenance | None = None,
    ) -> LoadedWorkflowBundle:
        if provenance_override is None and workflow_name in memo:
            return memo[workflow_name]
        bundle = original_by_name[workflow_name]
        if workflow_name in visiting:
            return bundle
        visiting.add(workflow_name)
        transformed_imports = {
            alias: (
                transform_bundle(imported.surface.name)
                if isinstance(imported.surface.name, str)
                and imported.surface.name in original_by_name
                else imported
            )
            for alias, imported in bundle.imports.items()
        }
        surface = replace(
            bundle.surface,
            provenance=provenance_override or bundle.provenance,
        )
        bridge_rows = rows_by_workflow.get(workflow_name, [])
        if bridge_rows:
            surface = _surface_with_compatibility_bridge_steps(
                surface=surface,
                bridge_rows=bridge_rows,
            )
        rebuilt = build_loaded_workflow_bundle(
            surface,
            imports=transformed_imports,
            private_artifact_ids=tuple(bundle.ir.private_artifacts),
        )
        if provenance_override is None:
            memo[workflow_name] = rebuilt
        visiting.discard(workflow_name)
        return rebuilt

    selected_name = str(selected_bundle.surface.name or "")
    transformed_selected = transform_bundle(
        selected_name,
        provenance_override=selected_provenance,
    )
    memo[selected_name] = transformed_selected
    transformed_by_name = {
        workflow_name: memo.get(workflow_name, bundle)
        for workflow_name, bundle in original_by_name.items()
    }
    return transformed_selected, transformed_by_name


def _surface_with_compatibility_bridge_steps(
    *,
    surface,
    bridge_rows: Sequence[Mapping[str, Any]],
):
    existing_allocations = {
        allocation.allocation_id
        for allocation in surface.provenance.generated_path_allocations
    }
    existing_step_ids = {
        step.step_id
        for step in surface.steps
        if isinstance(getattr(step, "step_id", None), str)
    }
    allocations = list(surface.provenance.generated_path_allocations)
    steps = list(surface.steps)
    for row in bridge_rows:
        step, allocation = _compatibility_bridge_surface_step(
            workflow_name=str(surface.name or ""),
            row=row,
        )
        if step.step_id not in existing_step_ids:
            steps.append(step)
            existing_step_ids.add(step.step_id)
        if allocation.allocation_id not in existing_allocations:
            allocations.append(allocation)
            existing_allocations.add(allocation.allocation_id)
    return replace(
        surface,
        steps=tuple(steps),
        provenance=replace(
            surface.provenance,
            generated_path_allocations=tuple(allocations),
        ),
    )


def _compatibility_bridge_surface_step(
    *,
    workflow_name: str,
    row: Mapping[str, Any],
) -> tuple[SurfaceStep, GeneratedPathAllocation]:
    bridge_id = str(row.get("bridge_id", ""))
    bridge_slug = _build_slug(bridge_id)
    workflow_slug = _build_slug(workflow_name)
    renderer = row.get("renderer", {})
    renderer_id = str(renderer.get("renderer_id", ""))
    renderer_version = int(renderer.get("renderer_version", 0))
    renderer_descriptor = resolve_view_renderer(renderer_id, renderer_version)
    target_binding = _compatibility_bridge_target_binding(
        bridge_id=bridge_id,
        workflow_slug=workflow_slug,
        bridge_slug=bridge_slug,
        file_extension=renderer_descriptor.file_extension,
        row=row,
    )
    target_path = str(target_binding["path_template"])
    allocation_id = f"alloc:design_delta_compatibility_bridge:{workflow_slug}:{bridge_slug}"
    step_id = f"compatibility_bridge__{bridge_slug}"
    value_document = _compatibility_bridge_value_document(
        bridge_id=bridge_id,
        row=row,
    )
    output_under = Path(target_path).parent.as_posix()
    allocation = GeneratedPathAllocation(
        allocation_id=allocation_id,
        workflow_name=workflow_name,
        semantic_role=GeneratedPathSemanticRole.MATERIALIZED_VALUE_VIEW,
        privacy=GeneratedPathPrivacy.COMPATIBILITY_VIEW,
        resume_scope=GeneratedPathResumeScope.NONE,
        stable_identity=f"schema:2/{workflow_name}/compatibility_bridge/{bridge_id}",
        concrete_path_template=target_path,
    )
    return (
        SurfaceStep(
            name=step_id,
            step_id=step_id,
            kind=SurfaceStepKind.MATERIALIZE_VIEW,
            materialize_view={
                "renderer_id": renderer_id,
                "renderer_version": renderer_version,
                "view_renderer_schema_version": VIEW_RENDERER_SCHEMA_VERSION,
                "value_type": {
                    "kind": "compatibility_bridge",
                    "name": bridge_id,
                },
                "value_document": value_document,
                "target_path": target_binding["runtime_target"],
                "target_allocation_id": allocation_id,
                "authority_class": "compatibility_bridge",
                "bridge_id": bridge_id,
                "c0_row_id": str(row.get("c0_row_id", "")),
                "output_contracts": {
                    "return": {
                        "kind": "relpath",
                        "type": "relpath",
                        "under": output_under,
                        "must_exist_target": True,
                    }
                },
            },
        ),
        allocation,
    )


def _compatibility_bridge_target_binding(
    *,
    bridge_id: str,
    workflow_slug: str,
    bridge_slug: str,
    file_extension: str,
    row: Mapping[str, Any],
) -> dict[str, object]:
    target = row.get("target")
    if isinstance(target, Mapping):
        path_template = target.get("path_template")
        runtime_target = target.get("runtime_target")
        if isinstance(path_template, str) and path_template:
            return {
                "runtime_target": (
                    runtime_target if runtime_target is not None else path_template
                ),
                "path_template": path_template,
            }
    path_template = (
        ".orchestrate/workflow_lisp/compatibility_bridges/"
        f"{workflow_slug}/{bridge_slug}{file_extension}"
    )
    return {
        "runtime_target": path_template,
        "path_template": path_template,
    }


def _compatibility_bridge_value_document(
    *,
    bridge_id: str,
    row: Mapping[str, Any],
) -> Any:
    from .build import DESIGN_DELTA_PARENT_DRAIN_COMPATIBILITY_BRIDGES_PATH

    typed_value_source = row.get("typed_value_source")
    if isinstance(typed_value_source, Mapping):
        value_document = typed_value_source.get("value_document")
        if value_document is not None:
            return _compatibility_bridge_manifest_value_document(value_document)
    source_ref = (
        str(typed_value_source.get("ref", ""))
        if isinstance(typed_value_source, Mapping)
        else ""
    )
    if source_ref:
        known_refs = {
            "drain.architecture_bundle": "inputs.architecture_bundle_path",
            "drain.manifest_bundle": "inputs.manifest_path",
            "drain.progress_ledger_path": "inputs.progress_ledger_path",
            "design_gap_architect.progress_ledger": "inputs.progress_ledger",
            "plan_phase.progress_ledger": "inputs.progress_ledger",
            "work_item.architecture_bundle": "inputs.architecture_bundle_path",
            "work_item.manifest_bundle": "inputs.manifest_path",
            "work_item.progress_ledger_path": "inputs.progress_ledger_path",
            "work_item.summary": "self.outputs.return__summary",
            "work_item.selection_bundle_pointer": "inputs.selection_bundle_path",
            "work_item.selection_bundle_command_input": "inputs.selection_bundle_path",
        }
        if source_ref in known_refs:
            return MaterializeViewBindingReference(ref=known_refs[source_ref])
    field_name = {
        "bridge.drain.architecture_bundle": "inputs.architecture_bundle_path",
        "bridge.drain.manifest": "inputs.manifest_path",
        "bridge.drain.progress_ledger": "inputs.progress_ledger_path",
        "bridge.work_item.architecture_bundle": "inputs.architecture_bundle_path",
        "bridge.work_item.manifest": "inputs.manifest_path",
        "bridge.work_item.progress_ledger": "inputs.progress_ledger_path",
        "bridge.work_item.summary": "self.outputs.return__summary",
        "bridge.work_item.summary.compiled_boundary": "self.outputs.return__summary",
        "bridge.work_item.pointer.selection_bundle": "inputs.selection_bundle_path",
        "bridge.work_item.command.selection_bundle": "inputs.selection_bundle_path",
    }.get(bridge_id)
    if field_name is not None:
        return MaterializeViewBindingReference(ref=field_name)
    raise LispFrontendCompileError(
        (
            _cli_request_diagnostic(
                code="compatibility_bridge_typed_source_missing",
                message=(
                    "design-delta compatibility bridge value source is not mapped "
                    f"for `{bridge_id}`"
                ),
                path=DESIGN_DELTA_PARENT_DRAIN_COMPATIBILITY_BRIDGES_PATH,
            ),
        )
    )


def _compatibility_bridge_manifest_value_document(value: Any) -> Any:
    if isinstance(value, Mapping):
        ref = value.get("ref")
        if isinstance(ref, str) and set(value) == {"ref"}:
            return MaterializeViewBindingReference(ref=ref)
        return {
            str(key): _compatibility_bridge_manifest_value_document(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_compatibility_bridge_manifest_value_document(item) for item in value]
    return value


def _augment_design_delta_compatibility_bridge_lineage(
    *,
    source_map_payload: dict[str, Any],
    selected_workflow_name: str,
    compatibility_bridge_manifest: Mapping[str, Any] | None,
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
) -> list[dict[str, Any]]:
    from .build import DESIGN_DELTA_PARENT_DRAIN_COMPATIBILITY_BRIDGES_PATH

    if not isinstance(compatibility_bridge_manifest, Mapping):
        return []
    workflows = source_map_payload.get("workflows")
    if not isinstance(workflows, dict):
        return []
    generated_steps: list[dict[str, Any]] = []
    for raw_row in compatibility_bridge_manifest.get("bridges", []):
        if not isinstance(raw_row, Mapping):
            continue
        if isinstance(raw_row.get("command_boundary"), Mapping):
            continue
        workflow_name = str(raw_row.get("workflow_surface", ""))
        workflow = workflows.get(workflow_name)
        if not isinstance(workflow, dict):
            continue
        bridge_id = str(raw_row.get("bridge_id", ""))
        renderer = raw_row.get("renderer")
        if not bridge_id or not isinstance(renderer, Mapping):
            continue
        renderer_id = str(renderer.get("renderer_id", ""))
        renderer_version = renderer.get("renderer_version")
        if not renderer_id or not isinstance(renderer_version, int):
            continue
        renderer_descriptor = resolve_view_renderer(renderer_id, renderer_version)
        bridge_slug = _build_slug(bridge_id)
        workflow_slug = _build_slug(workflow_name)
        allocation_id = (
            f"alloc:design_delta_compatibility_bridge:{workflow_slug}:{bridge_slug}"
        )
        target_path = (
            ".orchestrate/workflow_lisp/compatibility_bridges/"
            f"{workflow_slug}/{bridge_slug}{renderer_descriptor.file_extension}"
        )
        step_id = f"compatibility_bridge__{bridge_slug}"
        c0_row_id = str(raw_row.get("c0_row_id", ""))
        origin_key = f"{workflow_name}::step_id::{step_id}"
        step_ids = workflow.setdefault("step_ids", {})
        if isinstance(step_ids, dict) and step_id not in step_ids:
            step_ids[step_id] = {
                "origin_key": origin_key,
                "entity_kind": "step_id",
                "workflow_name": workflow_name,
                "path": str(DESIGN_DELTA_PARENT_DRAIN_COMPATIBILITY_BRIDGES_PATH),
                "line": 1,
                "column": 1,
                "end_line": 1,
                "end_column": 1,
                "form_path": ["compatibility_bridge", bridge_id],
                "notes": ["generated compatibility bridge materialize_view"],
            }
        generated_allocations = workflow.setdefault("generated_path_allocations", [])
        if isinstance(generated_allocations, list) and not any(
            isinstance(allocation, Mapping)
            and allocation.get("allocation_id") == allocation_id
            for allocation in generated_allocations
        ):
            generated_allocations.append(
                {
                    "allocation_id": allocation_id,
                    "semantic_role": "materialized_value_view",
                    "privacy": "compatibility_view",
                    "resume_scope": "none",
                    "stable_identity": (
                        "schema:2/"
                        f"{workflow_name}/compatibility_bridge/{bridge_id}"
                    ),
                    "concrete_path_template": target_path,
                    "generated_input_name": None,
                    "path_safety_policy": "workspace_relative",
                    "origin_key": origin_key,
                }
            )
        generated_effects = workflow.setdefault("generated_semantic_effects", [])
        if isinstance(generated_effects, list) and not any(
            isinstance(effect, Mapping)
            and effect.get("effect_kind") == "materialize_view"
            and isinstance(effect.get("details"), Mapping)
            and (
                effect["details"].get("target_allocation_id")
                or effect["details"].get("allocation_id")
            )
            == allocation_id
            for effect in generated_effects
        ):
            generated_effects.append(
                {
                    "effect_key": f"materialize_view:{step_id}",
                    "step_id": step_id,
                    "effect_kind": "materialize_view",
                    "origin_key": origin_key,
                    "details": {
                        "renderer_id": renderer_id,
                        "renderer_version": renderer_version,
                        "value_type": {
                            "kind": "compatibility_bridge",
                            "name": bridge_id,
                        },
                        "target_path": target_path,
                        "target_allocation_id": allocation_id,
                        "authority_class": "compatibility_bridge",
                        "bridge_id": bridge_id,
                        "c0_row_id": c0_row_id,
                    },
                }
            )
        if workflow_name != selected_workflow_name:
            continue
        bundle = validated_bundles_by_name.get(workflow_name)
        if bundle is None:
            continue
        generated_steps.append(
            {
                "workflow_name": workflow_name,
                "bridge_id": bridge_id,
                "c0_row_id": c0_row_id,
                "step_id": step_id,
                "target_path": target_path,
                "target_allocation_id": allocation_id,
                "renderer_id": renderer_id,
                "renderer_version": renderer_version,
                "authority_class": "compatibility_bridge",
            }
        )

    generated_steps.sort(
        key=lambda row: (str(row.get("workflow_name", "")), str(row.get("bridge_id", "")))
    )
    return generated_steps


def _build_slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-") or "bridge"


def _design_delta_prerequisite_report_paths(
    *,
    build_root: Path,
    workspace_root: Path,
) -> dict[str, str]:
    relative = build_root.relative_to(workspace_root)
    return {
        "typed_prompt_input_report": str(relative / "typed_prompt_input_report.json"),
        "observability_summary_report": str(relative / "observability_summary_report.json"),
        "entry_publication_report": str(relative / "entry_publication_report.json"),
        "compatibility_bridge_report": str(relative / "compatibility_bridge_report.json"),
        "parent_drain_census_alignment_report": str(
            relative / "parent_drain_census_alignment_report.json"
        ),
        "reference_family_conformance_profile": str(
            relative / "reference_family_conformance_profile.json"
        ),
    }


def _with_report_path(
    payload: Mapping[str, Any] | None,
    path: str,
) -> Mapping[str, Any] | None:
    if payload is None:
        return None
    return {
        **dict(payload),
        "path": path,
    }


def _build_design_delta_observability_summary_prerequisite_report(
    *,
    consumer_rendering_census: Mapping[str, object],
    old_writer_pair_manifest: Mapping[str, object] | None,
    materialize_view_effects: Sequence[Mapping[str, Any]],
) -> Mapping[str, object]:
    selected_row_ids: set[str] = set()
    diagnostics_errors: list[dict[str, object]] = []
    diagnostics_warnings: list[dict[str, object]] = []
    pair_report = (
        build_observability_pair_report(
            consumer_rendering_census=consumer_rendering_census,
            pair_manifest=old_writer_pair_manifest,
            materialize_view_effects=materialize_view_effects,
        )
        if old_writer_pair_manifest is not None
        else None
    )
    if pair_report is not None and pair_report.get("status") == "pass":
        selected_row_ids.update(
            row_id
            for row_id in pair_report.get("selected_c0_row_ids", [])
            if isinstance(row_id, str)
        )
    elif pair_report is not None:
        diagnostics = pair_report.get("diagnostics", {})
        errors = diagnostics.get("errors", []) if isinstance(diagnostics, Mapping) else []
        warnings = (
            diagnostics.get("warnings", [])
            if isinstance(diagnostics, Mapping)
            else []
        )
        diagnostics_errors.extend(
            error for error in errors if isinstance(error, Mapping)
        )
        diagnostics_warnings.extend(
            warning for warning in warnings if isinstance(warning, Mapping)
        )
    for row in consumer_rendering_census.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        row_id = row.get("row_id")
        if not isinstance(row_id, str):
            continue
        if row.get("consumer_lane") != "human_observability" and row.get(
            "track_c_decision"
        ) != "RETIRE_TO_OBSERVABILITY":
            continue
        if row_id in selected_row_ids:
            continue
        selected_row_ids.add(row_id)
        compiled_effect = row.get("compiled_effect_match")
        if not isinstance(compiled_effect, Mapping):
            continue
        suffix = compiled_effect.get("step_id_suffix")
        workflow_surface = row.get("workflow_surface")
        if not isinstance(suffix, str) or not suffix:
            continue
        if any(
            isinstance(effect.get("step_id"), str)
            and effect["step_id"].endswith(suffix)
            and str(effect.get("authority_class", "materialized_view"))
            == "materialized_view"
            and (
                not isinstance(workflow_surface, str)
                or effect.get("workflow_surface") == workflow_surface
            )
            for effect in materialize_view_effects
        ):
            diagnostic = {
                    "code": "observability_summary_old_writer_comparison_missing",
                    "c0_row_id": row_id,
                    "message": "observability row still lowers a body materialize_view effect",
                }
            if row_requires_old_writer_contract_evidence(row):
                diagnostics_errors.append(diagnostic)
            else:
                diagnostics_warnings.append(
                    {
                        **diagnostic,
                        "code": "observability_summary_old_writer_mechanics_not_contract",
                    }
                )
    return {
        "schema_id": OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID,
        "workflow_family": "design_delta_parent_drain",
        "status": "fail" if diagnostics_errors else "pass",
        "selected_c0_row_ids": sorted(selected_row_ids),
        "diagnostics": {
            "errors": diagnostics_errors,
            "warnings": diagnostics_warnings,
        },
        "pair_manifest_provenance": (
            pair_report.get("pair_manifest_provenance", {})
            if isinstance(pair_report, Mapping)
            else {}
        ),
        "pair_results": (
            pair_report.get("pair_results", [])
            if isinstance(pair_report, Mapping)
            else []
        ),
    }


def _serialize_design_delta_adapter_census(
    *,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding],
    command_boundary_manifest: Mapping[str, object],
    source_map_payload: Mapping[str, object],
) -> dict[str, object]:
    from .build import DESIGN_DELTA_PARENT_DRAIN_COMMAND_BOUNDARIES_PATH

    workflows = source_map_payload.get("workflows")
    lineage_by_name: dict[str, list[dict[str, object]]] = {}
    if isinstance(workflows, Mapping):
        for workflow_name, workflow_payload in workflows.items():
            if not isinstance(workflow_payload, Mapping):
                continue
            boundaries = workflow_payload.get("command_boundaries")
            if not isinstance(boundaries, list):
                continue
            for boundary in boundaries:
                if not isinstance(boundary, Mapping):
                    continue
                command_name = boundary.get("command_name")
                if not isinstance(command_name, str) or not command_name:
                    continue
                lineage_by_name.setdefault(command_name, []).append(
                    {
                        "workflow_name": workflow_name,
                        "step_id": boundary.get("step_id"),
                        "boundary_kind": boundary.get("boundary_kind"),
                    }
                )
    rows: list[dict[str, object]] = []
    for name, raw_entry in sorted(command_boundary_manifest.items()):
        binding = command_boundaries.get(name)
        if binding is None:
            continue
        fixture_ids = tuple(getattr(binding, "fixture_ids", ()) or ())
        negative_fixture_ids = tuple(getattr(binding, "negative_fixture_ids", ()) or ())
        replacement_path = getattr(binding, "replacement_path", None)
        liveness = "live" if lineage_by_name.get(name) else "unreferenced"
        retirement_status = getattr(binding, "retirement_status", None)
        if retirement_status == "retired" and liveness != "unreferenced":
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_adapter_retired_while_live",
                        message=(
                            "design-delta command boundary is marked retired but still has compiled "
                            f"invocation lineage: {name}"
                        ),
                        path=DESIGN_DELTA_PARENT_DRAIN_COMMAND_BOUNDARIES_PATH,
                    ),
                )
            )
        rows.append(
            {
                "workflow_family": "design_delta_parent_drain",
                "binding_name": name,
                "binding_kind": "certified_adapter"
                if isinstance(binding, CertifiedAdapterBinding)
                else "external_tool",
                "stable_command": list(binding.stable_command),
                "behavior_class": getattr(binding, "behavior_class", None),
                "retirement_class": getattr(binding, "retirement_class", None),
                "retirement_label": getattr(binding, "retirement_label", None),
                "replacement_surface": getattr(binding, "replacement_surface", None),
                "bridge_owner": getattr(binding, "bridge_owner", None),
                "expiry_condition": getattr(binding, "expiry_condition", None),
                "evidence_refs": list(getattr(binding, "evidence_refs", ()) or ()),
                "retirement_status": retirement_status,
                "fixture_ids": list(fixture_ids),
                "negative_fixture_ids": list(negative_fixture_ids),
                "owner_module": getattr(binding, "owner_module", None),
                "replacement_path": replacement_path,
                "transition_binding": (
                    {
                        "transition_name": binding.transition_binding.transition_name,
                        "resource_kind": binding.transition_binding.resource_kind,
                        "contract_role": binding.transition_binding.contract_role,
                        "backend_selector": binding.transition_binding.backend_selector,
                    }
                    if isinstance(binding, CertifiedAdapterBinding)
                    and binding.transition_binding is not None
                    else None
                ),
                "view_binding": (
                    {
                        "view_name": binding.view_binding.view_name,
                        "renderer_id": binding.view_binding.renderer_id,
                        "renderer_version": binding.view_binding.renderer_version,
                        "contract_role": binding.view_binding.contract_role,
                    }
                    if isinstance(binding, CertifiedAdapterBinding)
                    and binding.view_binding is not None
                    else None
                ),
                "invocation_sites": lineage_by_name.get(name, []),
                "liveness": liveness,
            }
        )
    return {
        "workflow_family": "design_delta_parent_drain",
        "schema_version": "workflow_lisp_design_delta_adapter_census.v1",
        "rows": rows,
    }


def _serialize_design_delta_boundary_authority_report(
    *,
    boundary_projection_payload: Mapping[str, object],
    boundary_authority_registry: Mapping[str, object],
    source_map_payload: Mapping[str, object],
    value_flow_census: Mapping[str, object] | None = None,
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None,
) -> dict[str, object]:
    expected_rows = build_design_delta_boundary_authority_expected_rows(
        dict(boundary_projection_payload),
        boundary_authority_registry=boundary_authority_registry,
        family_profile_catalog=family_profile_catalog,
    )
    allowed_stale_registry_rows = _allowed_resume_plumbing_retirement_registry_rows(
        value_flow_census
    )
    registry_rows = {
        (
            str(row["workflow_name"]),
            str(row["field_name"]),
            str(row["surface_kind"]),
        ): row
        for row in boundary_authority_registry.get("rows", [])
        if isinstance(row, Mapping)
        and is_design_delta_parent_drain_target_workflow(
            str(row.get("workflow_name", "")),
            family_profile_catalog=family_profile_catalog,
        )
    }
    registry_workflow_names = {
        workflow_name for workflow_name, _field_name, _surface_kind in registry_rows
    }
    expected_row_keys = {
        (workflow_name, field_name, str(row["surface_kind"])): row
        for (workflow_name, field_name), row in expected_rows.items()
        if not registry_workflow_names or workflow_name in registry_workflow_names
    }
    stale_rows = sorted(
        key
        for key in registry_rows
        if key not in expected_row_keys and key not in allowed_stale_registry_rows
    )
    if stale_rows:
        workflow_name, field_name, surface_kind = stale_rows[0]
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_boundary_authority_unclassified",
                    message=(
                        "stale boundary authority registry row does not match compiled evidence: "
                        f"{workflow_name} / {field_name} / {surface_kind}"
                    ),
                    path=Path(str(boundary_authority_registry.get("__registry_path__", ""))),
                ),
            )
        )
    path_like_mismatches = sorted(
        key
        for key, expected_row in expected_row_keys.items()
        if key in registry_rows
        and bool(registry_rows[key].get("path_like")) != bool(expected_row["path_like"])
    )
    if path_like_mismatches:
        workflow_name, field_name, surface_kind = path_like_mismatches[0]
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_boundary_authority_unclassified",
                    message=(
                        "boundary authority registry path_like does not match compiled evidence: "
                        f"{workflow_name} / {field_name} / {surface_kind}"
                    ),
                    path=Path(str(boundary_authority_registry.get("__registry_path__", ""))),
                ),
            )
        )

    projection_workflows = {
        str(workflow["workflow_name"]): workflow
        for workflow in boundary_projection_payload.get("workflows", [])
        if isinstance(workflow, Mapping)
        and isinstance(workflow.get("workflow_name"), str)
    }
    source_map_workflows = source_map_payload.get("workflows")
    if not isinstance(source_map_workflows, Mapping):
        source_map_workflows = {}

    def _compiled_evidence_for_projection_workflow(
        workflow_name: str,
        projection_workflow: Mapping[str, object] | None,
        source_map_workflow: Mapping[str, object] | None,
    ) -> dict[str, object]:
        flattened_inputs_by_name: dict[str, Mapping[str, object]] = {}
        generated_internal_path_like_inputs: list[str] = []
        runtime_context_path_inputs: list[str] = []
        compatibility_bridge_path_inputs: list[str] = []
        managed_write_root_inputs: list[str] = []
        flattened_output_names: list[str] = []
        pure_projection_classification: dict[str, object] = {
            "structural": False,
        }
        if isinstance(projection_workflow, Mapping):
            flattened_inputs_by_name = {
                str(field.get("generated_name")): field
                for field in projection_workflow.get("flattened_inputs", [])
                if isinstance(field, Mapping) and isinstance(field.get("generated_name"), str)
            }
            public_input_names = {
                str(name)
                for name in projection_workflow.get("boundary", {}).get(
                    "public_input_names", []
                )
                if isinstance(name, str)
            }
            generated_internal_entries = {
                str(field.get("generated_name")): field
                for field in projection_workflow.get("generated_internal_inputs", [])
                if isinstance(field, Mapping) and isinstance(field.get("generated_name"), str)
            }
            generated_internal_path_like_inputs = sorted(
                name
                for name, field in generated_internal_entries.items()
                if name not in public_input_names
                if _design_delta_generated_internal_entry_is_path_like(
                    name,
                    field,
                    flattened_inputs_by_name=flattened_inputs_by_name,
                )
            )
            flattened_output_names = sorted(
                str(field.get("generated_name"))
                for field in projection_workflow.get("flattened_outputs", [])
                if isinstance(field, Mapping)
                and isinstance(field.get("generated_name"), str)
                and _design_delta_contract_is_path_like(field.get("contract_definition"))
            )
            compatibility_bridge_path_inputs = sorted(
                name
                for name in projection_workflow.get("boundary", {}).get(
                    "private_compatibility_bridge_inputs", []
                )
                if isinstance(name, str)
                and _design_delta_generated_internal_entry_is_path_like(
                    name,
                    generated_internal_entries.get(name, {}),
                    flattened_inputs_by_name=flattened_inputs_by_name,
                )
            )
            managed_write_root_inputs = sorted(
                name
                for name in projection_workflow.get("boundary", {}).get(
                    "private_managed_write_root_inputs", []
                )
                if isinstance(name, str)
                and _design_delta_generated_internal_entry_is_path_like(
                    name,
                    generated_internal_entries.get(name, {}),
                    flattened_inputs_by_name=flattened_inputs_by_name,
                )
            )
            runtime_context_generated_names = {
                name
                for binding in projection_workflow.get("boundary", {}).get(
                    "private_runtime_context_bindings", []
                )
                if isinstance(binding, Mapping)
                for name in binding.get("generated_input_names", [])
                if isinstance(name, str)
            }
            runtime_context_path_inputs = sorted(
                name
                for name in runtime_context_generated_names
                if _design_delta_generated_internal_entry_is_path_like(
                    name,
                    generated_internal_entries.get(name, {}),
                    flattened_inputs_by_name=flattened_inputs_by_name,
                )
            )
            raw_classification = projection_workflow.get("boundary", {}).get(
                "pure_projection_classification"
            )
            if isinstance(raw_classification, Mapping):
                pure_projection_classification = {
                    "structural": bool(raw_classification.get("structural")),
                }
        generated_path_allocations: list[dict[str, object]] = []
        if isinstance(projection_workflow, Mapping):
            for allocation in projection_workflow.get("generated_path_allocations", []):
                if not isinstance(allocation, Mapping):
                    continue
                generated_path_allocations.append(
                    {
                        "generated_input_name": allocation.get("generated_input_name"),
                        "allocation_id": allocation.get("allocation_id"),
                        "semantic_role": allocation.get("semantic_role"),
                        "privacy": allocation.get("privacy"),
                    }
                )
        source_map_command_boundaries: list[dict[str, object]] = []
        source_map_generated_allocations: list[dict[str, object]] = []
        if isinstance(source_map_workflow, Mapping):
            for boundary in source_map_workflow.get("command_boundaries", []):
                if not isinstance(boundary, Mapping):
                    continue
                source_map_command_boundaries.append(
                    {
                        "command_name": boundary.get("command_name"),
                        "boundary_kind": boundary.get("boundary_kind"),
                        "step_id": boundary.get("step_id"),
                    }
                )
            for allocation in source_map_workflow.get("generated_path_allocations", []):
                if not isinstance(allocation, Mapping):
                    continue
                source_map_generated_allocations.append(
                    {
                        "generated_input_name": allocation.get("generated_input_name"),
                        "allocation_id": allocation.get("allocation_id"),
                        "semantic_role": allocation.get("semantic_role"),
                        "origin_key": allocation.get("origin_key"),
                    }
                )
        return {
            "workflow_boundary_projection": {
                "artifact": "workflow_boundary_projection.json",
                "workflow_name": workflow_name,
            },
            "generated_path_allocations": {
                "artifact": "workflow_boundary_projection.json",
                "rows": generated_path_allocations,
            },
            "source_map_provenance": {
                "artifact": "source_map.json",
                "workflow_names": [workflow_name]
                if isinstance(source_map_workflow, Mapping)
                else [],
                "command_boundaries": source_map_command_boundaries,
                "generated_path_allocations": source_map_generated_allocations,
            },
            "generated_internal_inputs": generated_internal_path_like_inputs,
            "flattened_outputs": flattened_output_names,
            "private_runtime_context_bindings": runtime_context_path_inputs,
            "private_compatibility_bridge_inputs": compatibility_bridge_path_inputs,
            "private_managed_write_root_inputs": managed_write_root_inputs,
            "pure_projection_classification": pure_projection_classification,
        }

    workflow_rows: dict[str, dict[str, object]] = {}
    for (workflow_name, field_name, surface_kind), expected in sorted(expected_row_keys.items()):
        projection_workflow = projection_workflows.get(workflow_name, {})
        source_map_workflow = source_map_workflows.get(workflow_name, {})
        row = workflow_rows.setdefault(
            workflow_name,
            {
                "workflow_name": workflow_name,
                "public_authored": [],
                "compatibility_bridge": [],
                "runtime_derived": [],
                "generated_internal": [],
                "materialized_view": [],
                "public_artifact": [],
                "unclassified": [],
                "public_leaks": [],
                "compiled_evidence": _compiled_evidence_for_projection_workflow(
                    workflow_name,
                    projection_workflow if isinstance(projection_workflow, Mapping) else None,
                    source_map_workflow if isinstance(source_map_workflow, Mapping) else None,
                ),
            },
        )
        registry_row = registry_rows.get((workflow_name, field_name, surface_kind))
        if registry_row is None:
            row["unclassified"].append(field_name)
            continue
        else:
            authority_class = str(registry_row["authority_class"])
        row[authority_class].append(field_name)
        if surface_kind == "public_input" and authority_class != "public_authored":
            row["public_leaks"].append(field_name)
        elif surface_kind == "runtime_context_input" and authority_class != "runtime_derived":
            row["public_leaks"].append(field_name)
        elif surface_kind == "compatibility_bridge_input" and authority_class != "compatibility_bridge":
            row["public_leaks"].append(field_name)
        elif surface_kind in {"generated_internal_input", "managed_write_root"} and authority_class != "generated_internal":
            row["public_leaks"].append(field_name)
        elif surface_kind == "flattened_output" and authority_class not in {"materialized_view", "public_artifact"}:
            row["public_leaks"].append(field_name)

    for workflow_name, projection_workflow in projection_workflows.items():
        if workflow_name in workflow_rows:
            continue
        if not isinstance(projection_workflow, Mapping):
            continue
        classification = projection_workflow.get("boundary", {}).get("pure_projection_classification")
        if not isinstance(classification, Mapping) or not bool(classification.get("structural")):
            continue
        source_map_workflow = source_map_workflows.get(workflow_name)
        workflow_rows[workflow_name] = {
            "workflow_name": workflow_name,
            "public_authored": [],
            "compatibility_bridge": [],
            "runtime_derived": [],
            "generated_internal": [],
            "materialized_view": [],
            "public_artifact": [],
            "unclassified": [],
            "public_leaks": [],
            "compiled_evidence": _compiled_evidence_for_projection_workflow(
                workflow_name,
                projection_workflow,
                source_map_workflow if isinstance(source_map_workflow, Mapping) else None,
            ),
        }

    for row in workflow_rows.values():
        for key, value in tuple(row.items()):
            if isinstance(value, list):
                value.sort()
        if row["unclassified"]:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="workflow_boundary_authority_unclassified",
                        message=(
                            "unclassified path-like boundary values remain for "
                            f"{row['workflow_name']}: {', '.join(row['unclassified'])}"
                        ),
                        path=Path(str(boundary_authority_registry.get("__registry_path__", ""))),
                    ),
                )
            )
        if row["public_leaks"]:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="workflow_boundary_private_class_exposed_publicly",
                        message=(
                            "public boundary exposes private authority classes for "
                            f"{row['workflow_name']}: {', '.join(row['public_leaks'])}"
                        ),
                        path=Path(str(boundary_authority_registry.get("__registry_path__", ""))),
                    ),
                )
            )

    return {
        "workflow_family": "design_delta_parent_drain",
        "schema_version": "workflow_lisp_design_delta_boundary_authority_report.v1",
        "registry_provenance": _boundary_authority_registry_provenance(boundary_authority_registry),
        "workflows": sorted(workflow_rows.values(), key=lambda row: str(row["workflow_name"])),
    }


def _allowed_resume_plumbing_retirement_registry_rows(
    value_flow_census: Mapping[str, object] | None,
) -> set[tuple[str, str, str]]:
    if not isinstance(value_flow_census, Mapping):
        return set()
    allowed_rows: set[tuple[str, str, str]] = set()
    for row in value_flow_census.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        if (
            row.get("plumbing_class") != "resume_only"
            or row.get("current_consumer") != "runtime_resume"
            or row.get("boundary_authority_class") != "compatibility_bridge"
        ):
            continue
        workflow_surface = row.get("workflow_surface")
        field_name = row.get("symbol_or_field")
        if not isinstance(workflow_surface, str) or not isinstance(field_name, str):
            continue
        allowed_rows.add(
            (workflow_surface, field_name, "compatibility_bridge_input")
        )
    return allowed_rows


def _serialize_design_delta_g8_deletion_evidence(
    *,
    command_boundary_manifest: Mapping[str, object],
) -> dict[str, object]:
    from .build import DESIGN_DELTA_PARENT_DRAIN_COMMAND_BOUNDARIES_PATH, get_form_spec

    present_deleted_rows = sorted(
        row_name for row_name in DESIGN_DELTA_G8_REMOVED_MANIFEST_ROWS if row_name in command_boundary_manifest
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
    present_removed_heads = sorted(present_removed_heads)
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
            "imported_only_registry_heads": list(DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS),
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


def _design_delta_contract_is_path_like(contract_definition: object) -> bool:
    return isinstance(contract_definition, Mapping) and contract_definition.get("type") == "relpath"


def _design_delta_generated_internal_entry_is_path_like(
    field_name: str,
    field: Mapping[str, object],
    *,
    flattened_inputs_by_name: Mapping[str, Mapping[str, object]],
) -> bool:
    flattened_input = flattened_inputs_by_name.get(field_name)
    if isinstance(flattened_input, Mapping) and _design_delta_contract_is_path_like(
        flattened_input.get("contract_definition")
    ):
        return True
    return field.get("reason") in {"managed_write_root", "compatibility_bridge"}


def _resume_plumbing_retirement_source_texts() -> Mapping[str, str]:
    root = Path(__file__).resolve().parents[2] / "workflows" / "library" / "lisp_frontend_design_delta"
    return {
        "lisp_frontend_design_delta/types": (root / "types.orc").read_text(
            encoding="utf-8"
        ),
        "lisp_frontend_design_delta/drain::drain": (root / "drain.orc").read_text(
            encoding="utf-8"
        ),
        "lisp_frontend_design_delta/work_item::run-work-item": (
            root / "work_item.orc"
        ).read_text(encoding="utf-8"),
        "lisp_frontend_design_delta/transitions": (
            root / "transitions.orc"
        ).read_text(encoding="utf-8"),
    }


def _serialize_lexical_checkpoint_points_for_retirement(
    *,
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    workflow_names: set[str],
    selected_workflow_name: str,
) -> dict[str, object]:
    from .build import _public_runtime_plan_payload, _serialize_lexical_checkpoint_points

    points: list[dict[str, object]] = []
    for workflow_name in sorted(workflow_names):
        bundle = validated_bundles_by_name.get(workflow_name)
        if bundle is None:
            continue
        payload = _serialize_lexical_checkpoint_points(
            bundle,
            runtime_plan_payload=_public_runtime_plan_payload(bundle.runtime_plan),
            semantic_ir_payload=workflow_semantic_ir_to_json(bundle.semantic_ir),
        )
        bundle_points = payload.get("points")
        if isinstance(bundle_points, list):
            points.extend(
                point for point in bundle_points if isinstance(point, dict)
            )
    return {
        "schema_version": CHECKPOINT_POINTS_SCHEMA_VERSION,
        "workflow_name": selected_workflow_name,
        "checkpoint_schema_version": CHECKPOINT_RECORD_SCHEMA_VERSION,
        "points": points,
    }


def _serialize_lexical_checkpoint_shadow_reports_for_retirement(
    *,
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    workflow_names: set[str],
    selected_workflow_name: str,
    source_map_payload: Mapping[str, Any],
) -> dict[str, object]:
    from .build import _public_runtime_plan_payload, _serialize_lexical_checkpoint_shadow_report

    workflow_reports: list[dict[str, object]] = []
    diagnostics: list[object] = []
    total_checked_points = 0
    total_checked_records = 0
    aggregate_status = "pass"
    for workflow_name in sorted(workflow_names):
        bundle = validated_bundles_by_name.get(workflow_name)
        if bundle is None:
            continue
        report = _serialize_lexical_checkpoint_shadow_report(
            bundle,
            semantic_ir_payload=workflow_semantic_ir_to_json(bundle.semantic_ir),
            runtime_plan_payload=_public_runtime_plan_payload(bundle.runtime_plan),
            source_map_payload=source_map_payload,
        )
        workflow_reports.append(report)
        total_checked_points += int(report.get("checked_points", 0) or 0)
        total_checked_records += int(report.get("checked_records", 0) or 0)
        if report.get("status") != "pass":
            aggregate_status = "fail"
        report_diagnostics = report.get("diagnostics")
        if isinstance(report_diagnostics, list):
            diagnostics.extend(report_diagnostics)
    return {
        "schema_version": CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION,
        "workflow_name": selected_workflow_name,
        "status": aggregate_status,
        "checked_points": total_checked_points,
        "checked_records": total_checked_records,
        "missing_points": [],
        "invalid_records": [],
        "stale_records": [],
        "diagnostics": diagnostics,
        "workflow_reports": workflow_reports,
    }
