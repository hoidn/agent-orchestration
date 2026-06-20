"""Frontend-owned build and artifact helpers for Workflow Lisp entrypoints."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.core_ast import build_core_workflow_ast, workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_boundary_projection
from orchestrator.workflow.references import MaterializeViewBindingReference
from orchestrator.workflow.runtime_plan import enrich_workflow_runtime_plan
from orchestrator.workflow.semantic_ir import derive_workflow_semantic_ir, workflow_semantic_ir_to_json
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

from .command_boundaries import (
    CertifiedAdapterBinding,
    CertifiedAdapterInputField,
    ExternalToolBinding,
    PROMOTED_CALL_REQUIRED_METADATA_FIELDS,
    TransitionBindingMetadata,
    ViewBindingMetadata,
)
from .compiler import LinkedStage3CompileResult, compile_stage3_entrypoint
from .consumer_rendering_census import (
    build_consumer_rendering_census_report,
    extract_materialize_view_effects,
    load_consumer_rendering_census,
)
from .compatibility_bridges import (
    build_compatibility_bridge_report,
    load_compatibility_bridge_manifest,
)
from .debug_yaml import render_debug_yaml
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic, serialize_diagnostics
from .entry_publication import (
    compatibility_reason_for_selected_row,
    select_entry_publication_rows,
    serialize_entry_publication_policy,
    serialize_entry_publication_report,
)
from .form_registry import get_form_spec
from .lints import LINT_PROFILE_DEFAULT
from .lexical_checkpoints import (
    CHECKPOINT_POINTS_SCHEMA_VERSION,
    CHECKPOINT_RECORD_SCHEMA_VERSION,
    CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION,
    canonical_json_dumps,
)
from .phase_family_boundary import (
    build_design_delta_boundary_authority_expected_rows,
    is_structural_pure_projection_effect_summary,
    is_design_delta_parent_drain_target_workflow,
    load_design_delta_boundary_authority_registry,
)
from .observability_summaries import (
    OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID,
    build_observability_pair_report,
    load_old_writer_pair_manifest,
    row_requires_old_writer_contract_evidence,
)
from . import lexical_checkpoint_default_resume
from . import resume_plumbing_retirement
from .source_map import SOURCE_MAP_COVERAGE, SOURCE_MAP_SCHEMA_VERSION, build_source_map_document
from .spans import SourcePosition, SourceSpan
from .typed_prompt_inputs import (
    build_typed_prompt_input_report,
    normalize_typed_prompt_input_entry,
)
from .rendering_cleanup import (
    build_rendering_cleanup_report,
    load_rendering_cleanup_manifest,
)
from .rendering_ergonomics import (
    build_rendering_ergonomics_report,
    load_rendering_ergonomics_policy,
)
from .transition_authoring import (
    build_transition_authoring_report,
    load_transition_authoring_manifest,
)
from .type_env import UnionTypeRef
from .value_flow_census import (
    load_value_flow_census,
    reconcile_value_flow_census,
)
from .workflows import (
    normalize_public_prompt_extern_binding,
    prompt_extern_source_bindings_payload,
    prompt_extern_source_payload,
)
from .wcc.route import LoweringRoute


BUILD_SCHEMA_VERSION = "workflow_lisp_build.v1"
DESIGN_DELTA_PARENT_DRAIN_COMMAND_BOUNDARIES_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)
DESIGN_DELTA_PARENT_DRAIN_BOUNDARY_AUTHORITY_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.boundary_authority.json"
)
DESIGN_DELTA_PARENT_DRAIN_VALUE_FLOW_CENSUS_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.value_flow_census.json"
)
DESIGN_DELTA_PARENT_DRAIN_CONSUMER_RENDERING_CENSUS_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.consumer_rendering_census.json"
)
DESIGN_DELTA_PARENT_DRAIN_COMPATIBILITY_BRIDGES_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.compatibility_bridges.json"
)
DESIGN_DELTA_PARENT_DRAIN_RENDERING_CLEANUP_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.rendering_cleanup.json"
)
DESIGN_DELTA_PARENT_DRAIN_RENDERING_ERGONOMICS_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.rendering_ergonomics.json"
)
DESIGN_DELTA_PARENT_DRAIN_TRANSITION_AUTHORING_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.transition_authoring.json"
)
DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_VECTORS_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_view_dual_run_vectors.json"
)
DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_REPORT_PATH = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "work"
    / "LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN"
    / "migration-parity"
    / "design_delta_parent_drain_view_dual_run_report.json"
)
DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.resume_plumbing_retirement.json"
)
DESIGN_DELTA_PARENT_DRAIN_OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.observability_old_writer_comparisons.json"
)
DESIGN_DELTA_PARENT_DRAIN_BLOCKED_IMPLEMENTATION_CHECKS_REPORT_LEGACY_PAYLOAD_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.blocked_implementation_checks_report.legacy_writer_payload.json"
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
FRONTEND_ARTIFACT_EXPORT_FILENAMES = {
    "executable_ir": "executable_ir.json",
    "core_workflow_ast": "core_workflow_ast.json",
    "runtime_plan": "runtime_plan.json",
    "semantic_ir": "semantic_ir.json",
    "source_map": "source_map.json",
    "lexical_checkpoint_points": "lexical_checkpoint_points.json",
    "lexical_checkpoint_shadow_report": "lexical_checkpoint_shadow_report.json",
    "lexical_checkpoint_default_resume_report": "lexical_checkpoint_default_resume_report.json",
    "expanded_debug_yaml": "expanded.debug.yaml",
}


@dataclass(frozen=True)
class FrontendBuildRequest:
    """Operator-facing compile request for one `.orc` entrypoint.

    The request keeps source discovery, extern manifests, imported YAML bundle
    bindings, and optional debug emission together so the build fingerprint can
    reflect every input that affects the lowered workflow bundle.
    """

    source_path: Path
    source_roots: tuple[Path, ...] = ()
    entry_workflow: str | None = None
    provider_externs_path: Path | None = None
    prompt_externs_path: Path | None = None
    imported_workflow_bundles_path: Path | None = None
    command_boundaries_path: Path | None = None
    emit_debug_yaml: bool = False
    workspace_root: Path | None = None
    lint_profile: str = LINT_PROFILE_DEFAULT
    lowering_route: LoweringRoute | str | None = None


@dataclass(frozen=True)
class FrontendEntrySelection:
    """Chosen exported workflow after resolving an optional CLI selection.

    `selected_name` is the user-facing export name while `canonical_name` is the
    module-qualified key used by the compiler and validated bundle maps.
    """

    requested_name: str | None
    selected_name: str
    canonical_name: str
    exported_names: tuple[str, ...]


@dataclass(frozen=True)
class ImportedWorkflowBundleBinding:
    """One existing workflow bundle linked into Lisp as a callable boundary.

    This is the compatibility bridge that lets a Lisp workflow call a validated
    YAML workflow without treating YAML as the frontend compiler target.
    """

    canonical_key: str
    manifest_entry_path: str
    resolved_bundle_path: Path
    bundle_kind: str
    workflow_name: str | None
    bundle_fingerprint: str | None
    load_status: str
    bundle: LoadedWorkflowBundle


@dataclass(frozen=True)
class FrontendBuildManifest:
    """Serializable index for the artifacts emitted by one frontend build.

    The manifest is the durable audit surface for source inputs, imported
    bundles, selected entrypoint, validation status, and emitted debug files.
    """

    schema_version: str
    fingerprint: str
    source_path: str
    source_roots: tuple[str, ...]
    entry_module: str
    entry_workflow: str
    imported_workflow_bundle_manifest_path: str | None
    imported_workflow_bundles: tuple[dict[str, object], ...]
    compiled_module_names: tuple[str, ...]
    validated_bundle_names: tuple[str, ...]
    artifact_paths: Mapping[str, str]
    artifact_status: Mapping[str, str]
    diagnostic_count: int
    shared_validation_status: str
    debug_yaml_status: str
    source_map_schema_version: str | None = None
    source_map_coverage: Mapping[str, str] | None = None
    lowering_schema_version: int = 1
    boundary_authority_registry: Mapping[str, object] | None = None
    value_flow_census: Mapping[str, object] | None = None
    consumer_rendering_census: Mapping[str, object] | None = None
    observability_old_writer_pair_evidence: Mapping[str, object] | None = None


@dataclass(frozen=True)
class FrontendSourceTrace:
    """Source-map projection for generated workflow nodes and artifacts.

    Runtime diagnostics and dashboard views use this compact projection to walk
    from shared workflow steps back to the `.orc` form that produced them.
    """

    workflow_name: str
    step_ids: Mapping[str, dict[str, object]]
    generated_inputs: Mapping[str, dict[str, object]]
    generated_outputs: Mapping[str, dict[str, object]]
    generated_paths: Mapping[str, dict[str, object]]


@dataclass(frozen=True)
class FrontendBuildResult:
    """In-memory and on-disk result of compiling one entry workflow.

    The validated bundle is what the runtime executes; the surrounding manifest,
    source trace, and optional debug YAML are inspection artifacts.
    """

    build_root: Path
    manifest_path: Path
    selected_workflow_name: str
    validated_bundle: LoadedWorkflowBundle
    diagnostics: tuple[LispFrontendDiagnostic, ...]
    artifact_paths: Mapping[str, Path]
    manifest: FrontendBuildManifest
    entry_selection: FrontendEntrySelection
    imported_workflow_bundles: tuple[ImportedWorkflowBundleBinding, ...]
    compile_result: LinkedStage3CompileResult


@dataclass(frozen=True)
class FrontendArtifactExportRequest:
    """One caller-requested convenience export of a canonical build artifact."""

    artifact_name: str
    destination: Path


def build_frontend_bundle(request: FrontendBuildRequest) -> FrontendBuildResult:
    """Compile one `.orc` entrypoint, validate it, and write build artifacts.

    This is the CLI/dashboard boundary for the frontend. It loads extern and
    imported-bundle manifests, runs the executable compile path, selects the
    requested exported workflow, reattaches source-map data to the validated
    bundle, and writes the manifest/source-map/debug artifacts under
    `.orchestrate/build`.
    """

    resolved_request = _resolve_request(request)
    provider_externs = _load_string_mapping(
        resolved_request.provider_externs_path,
        label="provider externs manifest",
    )
    prompt_externs = _load_prompt_extern_mapping(resolved_request.prompt_externs_path)
    command_boundary_manifest = _load_command_boundaries_manifest_payload(
        resolved_request.command_boundaries_path,
    )
    command_boundaries = _parse_command_boundaries_manifest(
        command_boundary_manifest,
        manifest_path=resolved_request.command_boundaries_path,
    )
    imported_bindings = load_imported_workflow_bundle_manifest(
        resolved_request.imported_workflow_bundles_path,
        workspace_root=resolved_request.workspace_root,
        source_roots=resolved_request.source_roots,
        provider_externs_path=resolved_request.provider_externs_path,
        prompt_externs_path=resolved_request.prompt_externs_path,
        command_boundaries_path=resolved_request.command_boundaries_path,
        lowering_route=resolved_request.lowering_route,
    )
    imported_workflow_bundles = {
        binding.canonical_key: binding.bundle
        for binding in imported_bindings
    }

    compile_result = compile_stage3_entrypoint(
        resolved_request.source_path,
        source_roots=resolved_request.source_roots,
        entry_workflow=resolved_request.entry_workflow,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles=imported_workflow_bundles,
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=resolved_request.workspace_root,
        lint_profile=resolved_request.lint_profile,
        lowering_route=resolved_request.lowering_route,
    )

    entry_selection = _select_entry_workflow(
        compile_result,
        requested_name=resolved_request.entry_workflow,
        source_path=resolved_request.source_path,
    )
    boundary_authority_registry = _maybe_load_design_delta_boundary_authority_registry(
        entry_workflow=entry_selection.canonical_name,
    )
    value_flow_census = _maybe_load_design_delta_value_flow_census(
        entry_workflow=entry_selection.canonical_name,
    )
    consumer_rendering_census = _maybe_load_design_delta_consumer_rendering_census(
        entry_workflow=entry_selection.canonical_name,
        value_flow_census=value_flow_census,
    )
    observability_old_writer_pair_manifest = (
        _maybe_load_design_delta_observability_old_writer_pair_manifest(
            entry_workflow=entry_selection.canonical_name,
            consumer_rendering_census=consumer_rendering_census,
        )
    )
    compatibility_bridge_manifest = None
    if consumer_rendering_census is not None and value_flow_census is not None:
        compatibility_bridge_manifest = (
            _maybe_load_design_delta_compatibility_bridge_manifest(
                entry_workflow=entry_selection.canonical_name,
                value_flow_census=value_flow_census,
                consumer_rendering_census=consumer_rendering_census,
                command_boundary_manifest=command_boundary_manifest,
            )
        )
    resume_plumbing_retirement_manifest = (
        _maybe_load_design_delta_resume_plumbing_retirement_manifest(
            entry_workflow=entry_selection.canonical_name,
        )
    )
    selected_bundle = compile_result.validated_bundles_by_name[
        entry_selection.canonical_name
    ]
    source_map_payload = _serialize_source_map(
        compile_result,
        selected_name=entry_selection.canonical_name,
    )
    workflow_boundary_projection_payload = _serialize_workflow_boundary_projection(
        compile_result,
        selected_name=entry_selection.canonical_name,
    )
    fingerprint = _fingerprint_build(
        request=resolved_request,
        compile_result=compile_result,
        imported_bindings=imported_bindings,
        entry_selection=entry_selection,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundary_manifest=command_boundary_manifest,
        boundary_authority_registry=boundary_authority_registry,
        value_flow_census=value_flow_census,
        consumer_rendering_census=consumer_rendering_census,
        observability_old_writer_pair_manifest=observability_old_writer_pair_manifest,
        resume_plumbing_retirement_manifest=resume_plumbing_retirement_manifest,
    )
    build_root = resolved_request.workspace_root / ".orchestrate" / "build" / fingerprint
    build_root.mkdir(parents=True, exist_ok=True)

    diagnostics = compile_result.diagnostics
    source_map_path = build_root / "source_map.json"
    provenance = replace(
        selected_bundle.provenance,
        frontend_kind="workflow_lisp",
        frontend_build_root=build_root,
        frontend_source_trace_path=source_map_path,
        frontend_entry_workflow=entry_selection.selected_name,
        frontend_source_map_schema_version=SOURCE_MAP_SCHEMA_VERSION,
        frontend_source_map_coverage=dict(SOURCE_MAP_COVERAGE),
    )
    validated_bundle, validated_bundles_by_name = (
        _materialize_design_delta_compatibility_bridge_bundles(
            selected_bundle=selected_bundle,
            validated_bundles_by_name=compile_result.validated_bundles_by_name,
            selected_provenance=replace(
                provenance,
                frontend_source_trace_path=None,
                frontend_source_map_schema_version=None,
                frontend_source_map_coverage=None,
            ),
            compatibility_bridge_manifest=compatibility_bridge_manifest,
        )
    )
    validated_bundle = _reattach_bundle_provenance(
        bundle=validated_bundle,
        provenance=provenance,
    )
    runtime_plan = enrich_workflow_runtime_plan(
        validated_bundle.runtime_plan,
        command_boundary_metadata=_command_boundary_metadata_for_workflow(
            source_map_payload,
            workflow_name=entry_selection.canonical_name,
        ),
        has_compiled_frontend_lineage=True,
    )
    validated_bundle = replace(validated_bundle, runtime_plan=runtime_plan)
    source_map_path.write_text(
        json.dumps(_json_data(source_map_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    runtime_plan_payload = _public_runtime_plan_payload(validated_bundle.runtime_plan)
    semantic_ir_payload = workflow_semantic_ir_to_json(validated_bundle.semantic_ir)
    executable_ir_payload = workflow_executable_ir_to_json(validated_bundle.ir)
    adapter_census_payload = None
    boundary_authority_report_payload = None
    value_flow_census_report_payload = None
    consumer_rendering_census_report_payload = None
    typed_prompt_input_report_payload = None
    observability_summary_report_payload = None
    entry_publication_report_payload = None
    compatibility_bridge_report_payload = None
    compatibility_bridge_generated_steps: list[dict[str, Any]] = []
    rendering_cleanup_report_payload = None
    rendering_ergonomics_report_payload = None
    transition_authoring_report_payload = None
    resume_plumbing_retirement_report_payload = None
    default_resume_report_payload = None
    checkpoint_points_payload = None
    checkpoint_shadow_report_payload = None
    g8_deletion_evidence_payload = None
    view_dual_run_vectors = None
    view_dual_run_report = None
    if boundary_authority_registry is not None:
        view_dual_run_vectors = _maybe_load_design_delta_view_dual_run_vectors(
            entry_workflow=entry_selection.canonical_name,
        )
        view_dual_run_report = _maybe_load_design_delta_view_dual_run_report(
            entry_workflow=entry_selection.canonical_name,
        )
        adapter_census_payload = _serialize_design_delta_adapter_census(
            command_boundaries=command_boundaries,
            command_boundary_manifest=command_boundary_manifest,
            source_map_payload=source_map_payload,
        )
        transition_authoring_manifest = _maybe_load_design_delta_transition_authoring_manifest(
            entry_workflow=entry_selection.canonical_name,
        )
        if transition_authoring_manifest is not None:
            transition_authoring_report_payload = build_transition_authoring_report(
                workflow_family="design_delta_parent_drain",
                checked_manifest=transition_authoring_manifest,
                source_map_payload=source_map_payload,
            )
            if transition_authoring_report_payload.get("status") != "pass":
                reasons: list[str] = []
                for bucket_name in (
                    "ordinary_body_violations",
                    "extra_origins",
                    "stale_allowed_origins",
                    "invalid_allowed_origins",
                    "source_shape_violations",
                ):
                    bucket = transition_authoring_report_payload.get(bucket_name)
                    if isinstance(bucket, list) and bucket:
                        reasons.append(bucket_name)
                raise LispFrontendCompileError(
                    (
                        _cli_request_diagnostic(
                            code="transition_authoring_invalid",
                            message=(
                                "design-delta transition authoring report failed: "
                                + ", ".join(reasons or ("unknown_failure",))
                            ),
                            path=DESIGN_DELTA_PARENT_DRAIN_TRANSITION_AUTHORING_PATH,
                        ),
                    )
                )
            transition_authoring_report_payload = _with_report_path(
                transition_authoring_report_payload,
                str(build_root / "transition_authoring_report.json"),
            )
        boundary_authority_report_payload = _serialize_design_delta_boundary_authority_report(
            boundary_projection_payload=workflow_boundary_projection_payload,
            boundary_authority_registry=boundary_authority_registry,
            source_map_payload=source_map_payload,
            value_flow_census=value_flow_census,
        )
        if value_flow_census is not None:
            materialize_view_effects = _collect_materialize_view_effects(
                validated_bundles_by_name
            )
            value_flow_census_report_payload = reconcile_value_flow_census(
                census=value_flow_census,
                checked_census_path=Path(str(value_flow_census.get("__census_path__", ""))),
                checked_census_sha256=str(value_flow_census.get("__census_sha256__", "")),
                boundary_authority_report=boundary_authority_report_payload,
                boundary_authority_registry=boundary_authority_registry,
                source_map_payload=source_map_payload,
                prompt_externs=prompt_externs,
                provider_externs=provider_externs,
                command_boundary_manifest=command_boundary_manifest,
            )
            failure_reasons: list[str] = []
            for bucket_name in (
                "missing_rows",
                "stale_rows",
                "invalid_rows",
                "extra_compiled_rows",
            ):
                bucket = value_flow_census_report_payload.get(bucket_name)
                if isinstance(bucket, list) and bucket:
                    first = bucket[0]
                    if isinstance(first, Mapping) and isinstance(first.get("row_id"), str):
                        reason_label = {
                            "missing_rows": "missing checked row",
                            "stale_rows": "stale checked row",
                            "invalid_rows": "invalid row",
                            "extra_compiled_rows": "unclassified compiled row",
                        }.get(bucket_name, bucket_name)
                        failure_reasons.append(
                            f"{reason_label}: {first['row_id']}"
                        )
                    else:
                        failure_reasons.append(bucket_name)
            if failure_reasons:
                raise LispFrontendCompileError(
                    (
                        _cli_request_diagnostic(
                            code="value_flow_census_invalid",
                            message=(
                                "design-delta value-flow census does not match compiled evidence: "
                                + "; ".join(failure_reasons)
                            ),
                            path=Path(str(value_flow_census.get("__census_path__", ""))),
                        ),
                    )
                )
            if consumer_rendering_census is not None:
                consumer_rendering_census_report_payload = (
                    build_consumer_rendering_census_report(
                        manifest=consumer_rendering_census,
                        value_flow_census=value_flow_census,
                        materialize_view_effects=materialize_view_effects,
                        command_boundary_manifest=command_boundary_manifest,
                        boundary_authority_report=boundary_authority_report_payload,
                        boundary_authority_report_path=str(
                            build_root / "boundary_authority_report.json"
                        ),
                        prompt_externs=prompt_externs,
                        prompt_externs_path=(
                            str(resolved_request.prompt_externs_path)
                            if resolved_request.prompt_externs_path
                            else None
                        ),
                        provider_externs=provider_externs,
                        provider_externs_path=(
                            str(resolved_request.provider_externs_path)
                            if resolved_request.provider_externs_path
                            else None
                        ),
                        command_boundaries_path=(
                            str(resolved_request.command_boundaries_path)
                            if resolved_request.command_boundaries_path
                            else None
                        ),
                        view_dual_run_vectors=view_dual_run_vectors,
                        view_dual_run_vectors_path=str(
                            DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_VECTORS_PATH
                        ),
                        view_dual_run_report=view_dual_run_report,
                        view_dual_run_report_path=str(
                            DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_REPORT_PATH
                        ),
                    )
                )
                if consumer_rendering_census_report_payload.get("status") != "pass":
                    first = {}
                    diagnostics_bucket = consumer_rendering_census_report_payload.get(
                        "diagnostics", []
                    )
                    if isinstance(diagnostics_bucket, list) and diagnostics_bucket:
                        first = diagnostics_bucket[0]
                    first_code = (
                        str(first.get("code"))
                        if isinstance(first, Mapping) and first.get("code")
                        else "consumer_rendering_census_invalid"
                    )
                    first_row_id = (
                        str(first.get("row_id"))
                        if isinstance(first, Mapping) and first.get("row_id")
                        else "unknown_row"
                    )
                    raise LispFrontendCompileError(
                        (
                            _cli_request_diagnostic(
                                code="consumer_rendering_census_invalid",
                                message=(
                                    "design-delta consumer rendering census report failed: "
                                    f"{first_code}: {first_row_id}"
                                ),
                                path=Path(
                                    str(
                                        consumer_rendering_census.get(
                                            "__manifest_path__", ""
                                        )
                                    )
                                ),
                            ),
                        )
                    )
                typed_prompt_input_report_payload = build_typed_prompt_input_report(
                    workflow_family="design_delta_parent_drain",
                    checked_manifest=consumer_rendering_census,
                    checked_manifest_path=str(
                        consumer_rendering_census.get("__manifest_path__", "")
                    ),
                    checked_manifest_sha256=str(
                        consumer_rendering_census.get("__manifest_sha256__", "")
                    ),
                    validated_bundles_by_name=validated_bundles_by_name,
                )
                if typed_prompt_input_report_payload.get("status") != "pass":
                    diagnostics_bucket: list[dict[str, Any]] = []
                    for bucket_name in ("missing_rows", "stale_rows", "invalid_rows"):
                        bucket = typed_prompt_input_report_payload.get(bucket_name)
                        if isinstance(bucket, list):
                            diagnostics_bucket.extend(
                                item for item in bucket if isinstance(item, Mapping)
                            )
                    first = diagnostics_bucket[0] if diagnostics_bucket else {}
                    first_code = (
                        str(first.get("code"))
                        if isinstance(first, Mapping) and first.get("code")
                        else "typed_prompt_input_row_missing"
                    )
                    first_row_id = (
                        str(first.get("c0_row_id"))
                        if isinstance(first, Mapping) and first.get("c0_row_id")
                        else "unknown_row"
                    )
                    raise LispFrontendCompileError(
                        (
                            _cli_request_diagnostic(
                                code="typed_prompt_input_invalid",
                                message=(
                                    "design-delta typed prompt-input report failed: "
                                    f"{first_code}: {first_row_id}"
                                ),
                                path=Path(
                                    str(
                                        consumer_rendering_census.get(
                                            "__manifest_path__", ""
                                        )
                                    )
                                ),
                            ),
                        )
                    )
                observability_summary_report_payload = (
                    _build_design_delta_observability_summary_prerequisite_report(
                        consumer_rendering_census=consumer_rendering_census,
                        old_writer_pair_manifest=observability_old_writer_pair_manifest,
                        materialize_view_effects=materialize_view_effects,
                    )
                )
                if observability_summary_report_payload.get("status") != "pass":
                    diagnostics_bucket = observability_summary_report_payload.get(
                        "diagnostics", {}
                    )
                    errors = (
                        diagnostics_bucket.get("errors", [])
                        if isinstance(diagnostics_bucket, Mapping)
                        else []
                    )
                    first = (
                        errors[0]
                        if isinstance(errors, list) and errors
                        else {}
                    )
                    first_code = (
                        str(first.get("code"))
                        if isinstance(first, Mapping) and first.get("code")
                        else "observability_summary_c0_row_missing"
                    )
                    first_row_id = (
                        str(first.get("c0_row_id"))
                        if isinstance(first, Mapping) and first.get("c0_row_id")
                        else "unknown_row"
                    )
                    raise LispFrontendCompileError(
                        (
                            _cli_request_diagnostic(
                                code=first_code,
                                message=(
                                    "design-delta observability summary evidence failed: "
                                    f"{first_code}: {first_row_id}"
                                ),
                                path=Path(
                                    str(
                                        consumer_rendering_census.get(
                                            "__manifest_path__", ""
                                        )
                                    )
                                ),
                            ),
                        )
                    )
                entry_publication_report_payload = _build_entry_publication_report(
                    compile_result=compile_result,
                    entry_workflow_name=entry_selection.canonical_name,
                    workflow_boundary_projection_payload=workflow_boundary_projection_payload,
                    source_map_payload=source_map_payload,
                    consumer_rendering_census=consumer_rendering_census,
                )
                if entry_publication_report_payload.get("status") != "pass":
                    diagnostics_bucket = entry_publication_report_payload.get(
                        "diagnostics", []
                    )
                    first = (
                        diagnostics_bucket[0]
                        if isinstance(diagnostics_bucket, list) and diagnostics_bucket
                        else {}
                    )
                    first_code = (
                        str(first.get("code"))
                        if isinstance(first, Mapping) and first.get("code")
                        else "entry_publication_c0_row_missing"
                    )
                    first_row_id = (
                        str(first.get("row_id"))
                        if isinstance(first, Mapping) and first.get("row_id")
                        else "unknown_row"
                    )
                    raise LispFrontendCompileError(
                        (
                            _cli_request_diagnostic(
                                code=first_code,
                                message=(
                                    "design-delta entry publication report failed: "
                                    f"{first_code}: {first_row_id}"
                                ),
                                path=Path(
                                    str(
                                        consumer_rendering_census.get(
                                            "__manifest_path__", ""
                                        )
                                    )
                                ),
                            ),
                        )
                    )
                if compatibility_bridge_manifest is not None:
                    compatibility_bridge_generated_steps = (
                        _augment_design_delta_compatibility_bridge_lineage(
                            source_map_payload=source_map_payload,
                            selected_workflow_name=entry_selection.canonical_name,
                            compatibility_bridge_manifest=compatibility_bridge_manifest,
                            validated_bundles_by_name=validated_bundles_by_name,
                        )
                    )
                    compatibility_bridge_report_payload = (
                        build_compatibility_bridge_report(
                            workflow_family="design_delta_parent_drain",
                            manifest=compatibility_bridge_manifest,
                            consumer_rendering_census=consumer_rendering_census,
                            command_boundary_manifest=command_boundary_manifest,
                            workflow_boundary_projection=workflow_boundary_projection_payload,
                            source_map_payload=source_map_payload,
                            materialize_view_effects=materialize_view_effects,
                        )
                    )
                    if compatibility_bridge_report_payload.get("status") != "pass":
                        diagnostics_bucket = compatibility_bridge_report_payload.get(
                            "diagnostics", []
                        )
                        first = (
                            diagnostics_bucket[0]
                            if isinstance(diagnostics_bucket, list) and diagnostics_bucket
                            else {}
                        )
                        first_code = (
                            str(first.get("code"))
                            if isinstance(first, Mapping) and first.get("code")
                            else "compatibility_bridge_metadata_invalid"
                        )
                        first_row_id = (
                            str(first.get("c0_row_id"))
                            if isinstance(first, Mapping) and first.get("c0_row_id")
                            else "unknown_row"
                        )
                        raise LispFrontendCompileError(
                            (
                                _cli_request_diagnostic(
                                    code=first_code,
                                    message=(
                                        "design-delta compatibility bridge report failed: "
                                        f"{first_code}: {first_row_id}"
                                    ),
                                    path=Path(
                                        str(
                                            compatibility_bridge_manifest.get(
                                                "__manifest_path__", ""
                                            )
                                        )
                                    ),
                            ),
                        )
                    )
                report_paths = _design_delta_prerequisite_report_paths(
                    build_root=build_root,
                    workspace_root=resolved_request.workspace_root,
                )
                typed_prompt_input_report_payload = _with_report_path(
                    typed_prompt_input_report_payload,
                    report_paths["typed_prompt_input_report"],
                )
                observability_summary_report_payload = _with_report_path(
                    observability_summary_report_payload,
                    report_paths["observability_summary_report"],
                )
                entry_publication_report_payload = _with_report_path(
                    entry_publication_report_payload,
                    report_paths["entry_publication_report"],
                )
                compatibility_bridge_report_payload = _with_report_path(
                    compatibility_bridge_report_payload,
                    report_paths["compatibility_bridge_report"],
                )
                rendering_cleanup_manifest = (
                    _maybe_load_design_delta_rendering_cleanup_manifest(
                        entry_workflow=entry_selection.canonical_name,
                        consumer_rendering_census=consumer_rendering_census,
                    )
                )
                if rendering_cleanup_manifest is not None:
                    rendering_cleanup_report_payload = (
                        build_rendering_cleanup_report(
                            workflow_family="design_delta_parent_drain",
                            manifest=rendering_cleanup_manifest,
                            consumer_rendering_census=consumer_rendering_census,
                            typed_prompt_input_report=typed_prompt_input_report_payload,
                            observability_summary_report=observability_summary_report_payload,
                            entry_publication_report=entry_publication_report_payload,
                            compatibility_bridge_report=compatibility_bridge_report_payload,
                            materialize_view_effects=materialize_view_effects,
                            workflow_boundary_projection=workflow_boundary_projection_payload,
                            source_map_payload=source_map_payload,
                        )
                    )
                    if rendering_cleanup_report_payload.get("status") != "pass":
                        diagnostics_bucket = rendering_cleanup_report_payload.get(
                            "diagnostics", []
                        )
                        first = (
                            diagnostics_bucket[0]
                            if isinstance(diagnostics_bucket, list) and diagnostics_bucket
                            else {}
                        )
                        first_code = (
                            str(first.get("code"))
                            if isinstance(first, Mapping) and first.get("code")
                            else "rendering_cleanup_manifest_invalid"
                        )
                        first_row_id = (
                            str(first.get("c0_row_id"))
                            if isinstance(first, Mapping) and first.get("c0_row_id")
                            else "unknown_row"
                        )
                        raise LispFrontendCompileError(
                            (
                                _cli_request_diagnostic(
                                    code=first_code,
                                    message=(
                                        "design-delta rendering cleanup report failed: "
                                        f"{first_code}: {first_row_id}"
                                    ),
                                    path=Path(
                                        str(
                                            rendering_cleanup_manifest.get(
                                                "__manifest_path__", ""
                                            )
                                        )
                                    ),
                                ),
                            )
                        )
                rendering_ergonomics_policy = (
                    _maybe_load_design_delta_rendering_ergonomics_manifest(
                        entry_workflow=entry_selection.canonical_name,
                    )
                )
                if rendering_ergonomics_policy is not None:
                    provider_input_observations = (
                        _collect_provider_input_shape_observations(
                            validated_bundles_by_name=compile_result.validated_bundles_by_name,
                            rendering_ergonomics_policy=rendering_ergonomics_policy,
                        )
                    )
                    rendering_ergonomics_report_payload = (
                        build_rendering_ergonomics_report(
                            policy=rendering_ergonomics_policy,
                            prerequisite_reports={
                                "consumer_rendering_census_report": consumer_rendering_census_report_payload,
                                "typed_prompt_input_report": typed_prompt_input_report_payload,
                                "observability_summary_report": observability_summary_report_payload,
                                "entry_publication_report": entry_publication_report_payload,
                                "compatibility_bridge_report": compatibility_bridge_report_payload,
                                "rendering_cleanup_report": rendering_cleanup_report_payload,
                            },
                            provider_input_observations=provider_input_observations,
                        )
                    )
                    if rendering_ergonomics_report_payload.get("status") != "pass":
                        diagnostics_bucket = rendering_ergonomics_report_payload.get(
                            "diagnostics", []
                        )
                        first = (
                            diagnostics_bucket[0]
                            if isinstance(diagnostics_bucket, list) and diagnostics_bucket
                            else {}
                        )
                        first_code = (
                            str(first.get("code"))
                            if isinstance(first, Mapping) and first.get("code")
                            else "rendering_ergonomics_report_invalid"
                        )
                        first_slot = (
                            str(
                                first.get("slot_id")
                                or first.get("c0_row_id")
                                or first.get("report")
                                or "unknown_slot"
                            )
                            if isinstance(first, Mapping)
                            else "unknown_slot"
                        )
                        raise LispFrontendCompileError(
                            (
                                _cli_request_diagnostic(
                                    code=first_code,
                                    message=(
                                        "design-delta rendering ergonomics report failed: "
                                        f"{first_code}: {first_slot}"
                                    ),
                                    path=DESIGN_DELTA_PARENT_DRAIN_RENDERING_ERGONOMICS_PATH,
                                ),
                            )
                        )
            candidate_rows = resume_plumbing_retirement.select_resume_plumbing_retirement_candidates(
                value_flow_census
            )
            try:
                checkpoint_workflow_names = {
                    str(row.get("workflow_surface"))
                    for row in candidate_rows
                    if isinstance(row, Mapping) and isinstance(row.get("workflow_surface"), str)
                }
                checkpoint_points_payload = _serialize_lexical_checkpoint_points_for_retirement(
                    validated_bundles_by_name=compile_result.validated_bundles_by_name,
                    workflow_names=checkpoint_workflow_names,
                    selected_workflow_name=entry_selection.canonical_name,
                )
                checkpoint_shadow_report_payload = _serialize_lexical_checkpoint_shadow_reports_for_retirement(
                    validated_bundles_by_name=compile_result.validated_bundles_by_name,
                    workflow_names=checkpoint_workflow_names,
                    selected_workflow_name=entry_selection.canonical_name,
                    source_map_payload=source_map_payload,
                )
                compiled_retirement_rows = (
                    resume_plumbing_retirement.normalize_resume_plumbing_retirement_compiled_rows(
                        candidate_rows,
                        boundary_authority_report=boundary_authority_report_payload,
                        source_text_by_surface=_resume_plumbing_retirement_source_texts(),
                    )
                )
                resume_plumbing_retirement_report_payload = (
                    resume_plumbing_retirement.build_resume_plumbing_retirement_report(
                        workflow_family="design_delta_parent_drain",
                        census=value_flow_census,
                        census_fingerprint=(
                            f"sha256:{value_flow_census.get('__census_sha256__', '')}"
                        ),
                        compiled_rows=compiled_retirement_rows,
                        manifest=resume_plumbing_retirement_manifest,
                        manifest_fingerprint=(
                            f"sha256:{resume_plumbing_retirement_manifest.get('__manifest_sha256__', '')}"
                            if resume_plumbing_retirement_manifest is not None
                            else None
                        ),
                        checkpoint_points_payload=checkpoint_points_payload,
                        checkpoint_shadow_report_payload=checkpoint_shadow_report_payload,
                    )
                )
                default_resume_report_payload = (
                    lexical_checkpoint_default_resume.build_default_resume_report(
                        workflow_family="design_delta_parent_drain",
                        workflow_name=entry_selection.canonical_name,
                        lowering_schema_version=compile_result.entry_result.lowering_schema_version,
                        checkpoint_points_payload=checkpoint_points_payload,
                        checkpoint_shadow_report_payload=checkpoint_shadow_report_payload,
                        resume_plumbing_retirement_report_payload=resume_plumbing_retirement_report_payload,
                    )
                )
            except ValueError as exc:
                raise LispFrontendCompileError(
                    (
                        _cli_request_diagnostic(
                            code="resume_plumbing_retirement_invalid",
                            message=str(exc),
                            path=Path(str(value_flow_census.get("__census_path__", ""))),
                        ),
                    )
                ) from exc
            default_resume_diagnostics = default_resume_report_payload.get(
                "diagnostics", []
            )
            if default_resume_report_payload.get("status") == "fail":
                first = {}
                if isinstance(default_resume_diagnostics, list) and default_resume_diagnostics:
                    prioritized = next(
                        (
                            item
                            for item in default_resume_diagnostics
                            if isinstance(item, Mapping)
                            and item.get("code")
                            == "lexical_default_resume_step_granular_bypass"
                        ),
                        None,
                    )
                    first = (
                        prioritized
                        if prioritized is not None
                        else default_resume_diagnostics[0]
                    )
                first_code = (
                    str(first.get("code"))
                    if isinstance(first, Mapping) and first.get("code")
                    else "lexical_default_resume_invalid"
                )
                first_row_id = (
                    str(first.get("row_id"))
                    if isinstance(first, Mapping) and first.get("row_id")
                    else "unknown_row"
                )
                raise LispFrontendCompileError(
                    (
                        _cli_request_diagnostic(
                            code="lexical_default_resume_invalid",
                            message=(
                                "design-delta default resume report failed: "
                                f"{first_code}: {first_row_id}"
                            ),
                            path=Path(str(value_flow_census.get("__census_path__", ""))),
                        ),
                    )
                )
            diagnostics_bucket = resume_plumbing_retirement_report_payload.get(
                "diagnostics", []
            )
            if isinstance(diagnostics_bucket, list) and diagnostics_bucket:
                first = diagnostics_bucket[0]
                first_code = (
                    str(first.get("code"))
                    if isinstance(first, Mapping) and first.get("code")
                    else "resume_plumbing_retirement_invalid"
                )
                first_row_id = (
                    str(first.get("row_id"))
                    if isinstance(first, Mapping) and first.get("row_id")
                    else "unknown_row"
                )
                raise LispFrontendCompileError(
                    (
                        _cli_request_diagnostic(
                            code="resume_plumbing_retirement_invalid",
                            message=(
                                "design-delta resume plumbing retirement report failed: "
                                f"{first_code}: {first_row_id}"
                            ),
                            path=Path(str(value_flow_census.get("__census_path__", ""))),
                        ),
                    )
                )
        if boundary_authority_registry.get("workflow_family") == "design_delta_parent_drain":
            g8_deletion_evidence_payload = _serialize_design_delta_g8_deletion_evidence(
                command_boundary_manifest=command_boundary_manifest,
            )
    artifact_paths = _write_build_artifacts(
        build_root=build_root,
        compile_result=compile_result,
        validated_bundle=validated_bundle,
        entry_selection=entry_selection,
        diagnostics=diagnostics,
        emit_debug_yaml=resolved_request.emit_debug_yaml,
        executable_ir_payload=executable_ir_payload,
        semantic_ir_payload=semantic_ir_payload,
        source_map_payload=source_map_payload,
        workflow_boundary_projection_payload=workflow_boundary_projection_payload,
        adapter_census_payload=adapter_census_payload,
        boundary_authority_report_payload=boundary_authority_report_payload,
        value_flow_census_report_payload=value_flow_census_report_payload,
        consumer_rendering_census_report_payload=consumer_rendering_census_report_payload,
        typed_prompt_input_report_payload=typed_prompt_input_report_payload,
        observability_summary_report_payload=observability_summary_report_payload,
        entry_publication_report_payload=entry_publication_report_payload,
        compatibility_bridge_report_payload=compatibility_bridge_report_payload,
        compatibility_bridge_generated_steps=compatibility_bridge_generated_steps,
        rendering_cleanup_report_payload=rendering_cleanup_report_payload,
        rendering_ergonomics_report_payload=rendering_ergonomics_report_payload,
        transition_authoring_report_payload=transition_authoring_report_payload,
        resume_plumbing_retirement_report_payload=resume_plumbing_retirement_report_payload,
        default_resume_report_payload=default_resume_report_payload,
        g8_deletion_evidence_payload=g8_deletion_evidence_payload,
    )
    manifest = _build_manifest(
        request=resolved_request,
        compile_result=compile_result,
        entry_selection=entry_selection,
        imported_bindings=imported_bindings,
        artifact_paths=artifact_paths,
        fingerprint=fingerprint,
        diagnostics=diagnostics,
        build_root=build_root,
        emit_debug_yaml=resolved_request.emit_debug_yaml,
        boundary_authority_registry=boundary_authority_registry,
        value_flow_census=value_flow_census,
        consumer_rendering_census=consumer_rendering_census,
        observability_old_writer_pair_manifest=observability_old_writer_pair_manifest,
        resume_plumbing_retirement_manifest=resume_plumbing_retirement_manifest,
    )
    manifest_path = build_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(_json_data(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact_paths = dict(artifact_paths)
    artifact_paths["manifest"] = manifest_path

    return FrontendBuildResult(
        build_root=build_root,
        manifest_path=manifest_path,
        selected_workflow_name=entry_selection.selected_name,
        validated_bundle=validated_bundle,
        diagnostics=diagnostics,
        artifact_paths=artifact_paths,
        manifest=manifest,
        entry_selection=entry_selection,
        imported_workflow_bundles=imported_bindings,
        compile_result=compile_result,
    )


def normalize_frontend_artifact_exports(
    raw_requests: Mapping[str, list[str | None] | tuple[str | None, ...]],
    *,
    cwd: Path,
    source_path: Path,
) -> dict[str, FrontendArtifactExportRequest]:
    """Resolve CLI emit flags into concrete export requests.

    Export paths are convenience destinations only and must stay outside build
    fingerprinting and manifest authority.
    """

    normalized: dict[str, FrontendArtifactExportRequest] = {}
    resolved_cwd = cwd.resolve()
    for artifact_name, default_filename in FRONTEND_ARTIFACT_EXPORT_FILENAMES.items():
        values = list(raw_requests.get(artifact_name, ()))
        if not values:
            continue
        if len(values) > 1:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="artifact_export_requested_multiple_times",
                        message=f"artifact export `{artifact_name}` was requested more than once",
                        path=source_path,
                    ),
                )
            )
        raw_destination = values[0]
        destination = Path(raw_destination) if raw_destination is not None else Path(default_filename)
        if not destination.is_absolute():
            destination = resolved_cwd / destination
        destination = destination.resolve()
        if destination.exists() and destination.is_dir():
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="artifact_export_destination_is_directory",
                        message=f"artifact export destination `{destination}` resolves to an existing directory",
                        path=source_path,
                    ),
                )
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        normalized[artifact_name] = FrontendArtifactExportRequest(
            artifact_name=artifact_name,
            destination=destination,
        )
    return normalized


def emit_requested_frontend_artifact_exports(
    *,
    result: FrontendBuildResult,
    export_requests: Mapping[str, FrontendArtifactExportRequest],
) -> dict[str, Path]:
    """Copy canonical build artifacts to requested convenience destinations."""

    exported: dict[str, Path] = {}
    for artifact_name, request in sorted(export_requests.items()):
        canonical_path = result.artifact_paths.get(artifact_name)
        if canonical_path is None:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="artifact_export_unavailable",
                        message=f"canonical artifact `{artifact_name}` is not available for export",
                        path=Path(result.manifest.source_path),
                    ),
                )
            )
        try:
            shutil.copyfile(canonical_path, request.destination)
        except OSError as exc:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="artifact_export_failed",
                        message=f"failed to export `{artifact_name}` to `{request.destination}`: {exc}",
                        path=request.destination,
                        notes=(f"canonical artifact: {canonical_path}",),
                    ),
                )
            ) from exc
        exported[artifact_name] = request.destination
    return exported


def load_imported_workflow_bundle_manifest(
    manifest_path: Path | None,
    *,
    workspace_root: Path,
    source_roots: tuple[Path, ...] = (),
    provider_externs_path: Path | None = None,
    prompt_externs_path: Path | None = None,
    command_boundaries_path: Path | None = None,
    lowering_route: LoweringRoute | str | None = None,
) -> tuple[ImportedWorkflowBundleBinding, ...]:
    """Load imported workflow bundles from one explicit manifest file."""

    if manifest_path is None:
        return ()
    payload = _load_json_file(manifest_path, label="imported workflow bundle manifest")
    if not payload:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="imported_workflow_bundle_manifest_empty",
                    message="imported workflow bundle manifest must declare at least one bundle",
                    path=manifest_path,
                ),
            )
        )
    if not isinstance(payload, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="imported_workflow_bundle_manifest_invalid",
                    message="imported workflow bundle manifest must be a JSON object",
                    path=manifest_path,
                ),
            )
        )

    bindings: list[ImportedWorkflowBundleBinding] = []
    loader = WorkflowLoader(workspace_root)
    for canonical_key, raw_entry in payload.items():
        if not isinstance(canonical_key, str) or not canonical_key:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="imported_workflow_bundle_key_invalid",
                        message="imported workflow bundle keys must be non-empty strings",
                        path=manifest_path,
                    ),
                )
            )
        if not isinstance(raw_entry, Mapping):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="imported_workflow_bundle_manifest_invalid",
                        message=f"manifest entry for `{canonical_key}` must be a JSON object",
                        path=manifest_path,
                    ),
                )
            )
        bundle_kind = str(raw_entry.get("kind", "yaml"))
        raw_path = raw_entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="imported_workflow_bundle_path_missing",
                        message=f"manifest entry for `{canonical_key}` must declare `path`",
                        path=manifest_path,
                    ),
                )
            )
        resolved_bundle_path = _resolve_manifest_relative_path(manifest_path, raw_path)
        if bundle_kind == "yaml":
            bundle = loader.load_bundle(resolved_bundle_path)
            workflow_name = bundle.surface.name
            bundle_fingerprint = _sha256_path(resolved_bundle_path)
            load_status = "loaded"
        elif bundle_kind == "compiled":
            compiled_result = build_frontend_bundle(
                FrontendBuildRequest(
                    source_path=resolved_bundle_path,
                    source_roots=source_roots,
                    entry_workflow=(
                        raw_entry.get("entry_workflow")
                        if isinstance(raw_entry.get("entry_workflow"), str)
                        else None
                    ),
                    provider_externs_path=provider_externs_path,
                    prompt_externs_path=prompt_externs_path,
                    imported_workflow_bundles_path=None,
                    command_boundaries_path=command_boundaries_path,
                    emit_debug_yaml=False,
                    workspace_root=workspace_root,
                    lowering_route=lowering_route,
                )
            )
            bundle = compiled_result.validated_bundle
            workflow_name = compiled_result.selected_workflow_name
            bundle_fingerprint = compiled_result.manifest.fingerprint
            load_status = "compiled"
        else:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="imported_workflow_bundle_kind_invalid",
                        message=f"unsupported imported workflow bundle kind `{bundle_kind}` for `{canonical_key}`",
                        path=manifest_path,
                    ),
                )
            )
        bindings.append(
            ImportedWorkflowBundleBinding(
                canonical_key=canonical_key,
                manifest_entry_path=raw_path,
                resolved_bundle_path=resolved_bundle_path,
                bundle_kind=bundle_kind,
                workflow_name=workflow_name,
                bundle_fingerprint=bundle_fingerprint,
                load_status=load_status,
                bundle=bundle,
            )
        )
    return tuple(bindings)


def _resolve_request(request: FrontendBuildRequest) -> FrontendBuildRequest:
    workspace_root = (request.workspace_root or Path.cwd()).resolve()
    source_path = request.source_path.resolve()
    if not source_path.exists():
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_cli_input_missing",
                    message="workflow Lisp entrypoint does not exist",
                    path=source_path,
                ),
            )
        )
    source_roots = tuple(root.resolve() for root in request.source_roots)
    return FrontendBuildRequest(
        source_path=source_path,
        source_roots=source_roots,
        entry_workflow=request.entry_workflow,
        provider_externs_path=request.provider_externs_path.resolve() if request.provider_externs_path else None,
        prompt_externs_path=request.prompt_externs_path.resolve() if request.prompt_externs_path else None,
        imported_workflow_bundles_path=request.imported_workflow_bundles_path.resolve()
        if request.imported_workflow_bundles_path
        else None,
        command_boundaries_path=request.command_boundaries_path.resolve() if request.command_boundaries_path else None,
        emit_debug_yaml=request.emit_debug_yaml,
        workspace_root=workspace_root,
        lint_profile=request.lint_profile,
        lowering_route=request.lowering_route,
    )


def _load_string_mapping(
    manifest_path: Path | None,
    *,
    label: str,
) -> Mapping[str, str]:
    if manifest_path is None:
        return {}
    payload = _load_json_file(manifest_path, label=label)
    if not isinstance(payload, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_manifest_invalid",
                    message=f"{label} must be a JSON object",
                    path=manifest_path,
                ),
            )
        )
    entries: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key or not isinstance(value, str):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="workflow_lisp_manifest_invalid",
                        message=f"{label} entries must map non-empty string names to string values",
                        path=manifest_path,
                    ),
                )
            )
        entries[key] = value
    return entries


def _load_prompt_extern_mapping(
    manifest_path: Path | None,
) -> Mapping[str, str | dict[str, str]]:
    if manifest_path is None:
        return {}
    payload = _load_json_file(manifest_path, label="prompt externs manifest")
    if not isinstance(payload, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_manifest_invalid",
                    message="prompt externs manifest must be a JSON object",
                    path=manifest_path,
                ),
            )
        )
    entries: dict[str, str | dict[str, str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not key:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="workflow_lisp_manifest_invalid",
                        message="prompt externs manifest entries must use non-empty string names",
                        path=manifest_path,
                    ),
                )
            )
        try:
            binding = normalize_public_prompt_extern_binding(key, value)
        except (TypeError, ValueError):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="workflow_lisp_manifest_invalid",
                        message=(
                            "prompt externs manifest entries must map non-empty string names to string values "
                            "or objects with exactly one of `asset_file` or `input_file`"
                        ),
                        path=manifest_path,
                    ),
                )
            ) from None
        entries[key] = binding.path if binding.source_kind == "asset_file" and isinstance(value, str) else prompt_extern_source_payload(binding)
    return entries


def _load_command_boundaries_manifest_payload(
    manifest_path: Path | None,
) -> Mapping[str, object]:
    if manifest_path is None:
        return {}
    payload = _load_json_file(manifest_path, label="command boundaries manifest")
    if not isinstance(payload, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message="command boundaries manifest must be a JSON object",
                    path=manifest_path,
                ),
            )
        )
    entries: dict[str, object] = {}
    for name, raw_entry in payload.items():
        if not isinstance(name, str) or not name:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message="command boundaries manifest entries must use non-empty string names",
                        path=manifest_path,
                    ),
                )
            )
        entries[name] = raw_entry
    return entries


def _parse_command_boundaries_manifest(
    payload: Mapping[str, object],
    *,
    manifest_path: Path | None,
) -> Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]:
    bindings: dict[str, ExternalToolBinding | CertifiedAdapterBinding] = {}
    for name, raw_entry in payload.items():
        if not isinstance(raw_entry, Mapping):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message=f"manifest entry for `{name}` must be a JSON object",
                        path=manifest_path or Path(name),
                    ),
                )
            )
        stable_command = _require_string_array(
            raw_entry.get("stable_command", ()),
            field_name="stable_command",
            binding_name=name,
            manifest_path=manifest_path,
        )
        kind = raw_entry.get("kind", "external_tool")
        if not isinstance(kind, str) or not kind:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message=f"`kind` for `{name}` must be a non-empty string",
                        path=manifest_path or Path(name),
                    ),
                )
            )
        if kind == "external_tool":
            bindings[name] = ExternalToolBinding(
                name=name,
                stable_command=stable_command,
                retirement_class=_require_optional_string_field(
                    raw_entry.get("retirement_class"),
                    field_name="retirement_class",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                retirement_label=_require_optional_string_field(
                    raw_entry.get("retirement_label"),
                    field_name="retirement_label",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                replacement_surface=_require_optional_string_field(
                    raw_entry.get("replacement_surface"),
                    field_name="replacement_surface",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                bridge_owner=_require_optional_string_field(
                    raw_entry.get("bridge_owner"),
                    field_name="bridge_owner",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                expiry_condition=_require_optional_string_field(
                    raw_entry.get("expiry_condition"),
                    field_name="expiry_condition",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                evidence_refs=_require_optional_string_array(
                    raw_entry.get("evidence_refs"),
                    field_name="evidence_refs",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                retirement_status=_require_optional_string_field(
                    raw_entry.get("retirement_status"),
                    field_name="retirement_status",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
            )
            continue
        if kind == "certified_adapter":
            declared_promoted_fields = frozenset(
                key
                for key in PROMOTED_CALL_REQUIRED_METADATA_FIELDS
                if key in raw_entry
            )
            bindings[name] = CertifiedAdapterBinding(
                name=name,
                stable_command=stable_command,
                input_contract=_require_mapping_field(
                    raw_entry.get("input_contract", {}),
                    field_name="input_contract",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                output_type_name=_require_string_field(
                    raw_entry.get("output_type_name", ""),
                    field_name="output_type_name",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                effects=_require_string_array(
                    raw_entry.get("effects", ()),
                    field_name="effects",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                path_safety=_require_mapping_field(
                    raw_entry.get("path_safety", {}),
                    field_name="path_safety",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                source_map_behavior=_require_string_field(
                    raw_entry.get("source_map_behavior", ""),
                    field_name="source_map_behavior",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                fixture_ids=_require_string_array(
                    raw_entry.get("fixture_ids", ()),
                    field_name="fixture_ids",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                negative_fixture_ids=_require_string_array(
                    raw_entry.get("negative_fixture_ids", ()),
                    field_name="negative_fixture_ids",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                behavior_class=_require_optional_string_field(
                    raw_entry.get("behavior_class"),
                    field_name="behavior_class",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                input_signature=_require_input_signature(
                    raw_entry.get("input_signature", ()),
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                artifact_contracts=_require_string_array(
                    raw_entry.get("artifact_contracts", ()),
                    field_name="artifact_contracts",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                state_writes=_require_string_array(
                    raw_entry.get("state_writes", ()),
                    field_name="state_writes",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                error_codes=_require_string_array(
                    raw_entry.get("error_codes", ()),
                    field_name="error_codes",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                owner_module=_require_optional_string_field(
                    raw_entry.get("owner_module"),
                    field_name="owner_module",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                replacement_path=_require_optional_string_field(
                    raw_entry.get("replacement_path"),
                    field_name="replacement_path",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                invocation_protocol=_require_optional_string_field(
                    raw_entry.get("invocation_protocol"),
                    field_name="invocation_protocol",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                transition_binding=_require_transition_binding(
                    raw_entry.get("transition_binding"),
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                view_binding=_require_view_binding(
                    raw_entry.get("view_binding"),
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                declared_promoted_fields=declared_promoted_fields,
                retirement_class=_require_optional_string_field(
                    raw_entry.get("retirement_class"),
                    field_name="retirement_class",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                retirement_label=_require_optional_string_field(
                    raw_entry.get("retirement_label"),
                    field_name="retirement_label",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                replacement_surface=_require_optional_string_field(
                    raw_entry.get("replacement_surface"),
                    field_name="replacement_surface",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                bridge_owner=_require_optional_string_field(
                    raw_entry.get("bridge_owner"),
                    field_name="bridge_owner",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                expiry_condition=_require_optional_string_field(
                    raw_entry.get("expiry_condition"),
                    field_name="expiry_condition",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                evidence_refs=_require_optional_string_array(
                    raw_entry.get("evidence_refs"),
                    field_name="evidence_refs",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
                retirement_status=_require_optional_string_field(
                    raw_entry.get("retirement_status"),
                    field_name="retirement_status",
                    binding_name=name,
                    manifest_path=manifest_path,
                ),
            )
            continue
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"unsupported command boundary kind `{kind}` for `{name}`",
                    path=manifest_path,
                ),
            )
        )
    return bindings


def _require_string_array(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`{field_name}` for `{binding_name}` must be an array of strings",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return tuple(value)


def _require_optional_string_array(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> tuple[str, ...]:
    if value is None:
        return ()
    return _require_string_array(
        value,
        field_name=field_name,
        binding_name=binding_name,
        manifest_path=manifest_path,
    )


def _require_mapping_field(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`{field_name}` for `{binding_name}` must be a JSON object",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return dict(value)


def _require_string_field(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> str:
    if not isinstance(value, str):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`{field_name}` for `{binding_name}` must be a string",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return value


def _require_optional_string_field(
    value: object,
    *,
    field_name: str,
    binding_name: str,
    manifest_path: Path | None,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`{field_name}` for `{binding_name}` must be a string or null",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return value


def _require_input_signature(
    value: object,
    *,
    binding_name: str,
    manifest_path: Path | None,
) -> tuple[CertifiedAdapterInputField, ...]:
    if not isinstance(value, (list, tuple)):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`input_signature` for `{binding_name}` must be an array of objects",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    fields: list[CertifiedAdapterInputField] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message=f"`input_signature[{index}]` for `{binding_name}` must be a JSON object",
                        path=manifest_path or Path(binding_name),
                    ),
                )
            )
        name = _require_string_field(
            item.get("name", ""),
            field_name=f"input_signature[{index}].name",
            binding_name=binding_name,
            manifest_path=manifest_path,
        )
        type_name = _require_string_field(
            item.get("type_name", ""),
            field_name=f"input_signature[{index}].type_name",
            binding_name=binding_name,
            manifest_path=manifest_path,
        )
        required = item.get("required", True)
        if not isinstance(required, bool):
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="command_boundary_manifest_invalid",
                        message=f"`input_signature[{index}].required` for `{binding_name}` must be a boolean",
                        path=manifest_path or Path(binding_name),
                    ),
                )
            )
        transport_key = _require_string_field(
            item.get("transport_key", ""),
            field_name=f"input_signature[{index}].transport_key",
            binding_name=binding_name,
            manifest_path=manifest_path,
        )
        fields.append(
            CertifiedAdapterInputField(
                name=name,
                type_name=type_name,
                required=required,
                transport_key=transport_key,
            )
        )
    return tuple(fields)


def _require_transition_binding(
    value: object,
    *,
    binding_name: str,
    manifest_path: Path | None,
) -> TransitionBindingMetadata | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`transition_binding` for `{binding_name}` must be an object",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return TransitionBindingMetadata(
        transition_name=_require_string_field(
            value.get("transition_name", ""),
            field_name="transition_binding.transition_name",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        resource_kind=_require_string_field(
            value.get("resource_kind", ""),
            field_name="transition_binding.resource_kind",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        contract_role=_require_string_field(
            value.get("contract_role", ""),
            field_name="transition_binding.contract_role",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        backend_selector=_require_string_field(
            value.get("backend_selector", ""),
            field_name="transition_binding.backend_selector",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
    )


def _require_view_binding(
    value: object,
    *,
    binding_name: str,
    manifest_path: Path | None,
) -> ViewBindingMetadata | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`view_binding` for `{binding_name}` must be an object",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    renderer_version = value.get("renderer_version")
    if not isinstance(renderer_version, int):
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="command_boundary_manifest_invalid",
                    message=f"`view_binding.renderer_version` for `{binding_name}` must be an integer",
                    path=manifest_path or Path(binding_name),
                ),
            )
        )
    return ViewBindingMetadata(
        view_name=_require_string_field(
            value.get("view_name", ""),
            field_name="view_binding.view_name",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        renderer_id=_require_string_field(
            value.get("renderer_id", ""),
            field_name="view_binding.renderer_id",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
        renderer_version=renderer_version,
        contract_role=_require_string_field(
            value.get("contract_role", ""),
            field_name="view_binding.contract_role",
            binding_name=binding_name,
            manifest_path=manifest_path,
        ),
    )


def _select_entry_workflow(
    compile_result: LinkedStage3CompileResult,
    *,
    requested_name: str | None,
    source_path: Path,
) -> FrontendEntrySelection:
    export_surface = compile_result.graph.export_surfaces_by_name[compile_result.graph.entry_module_name]
    exported_workflows = tuple(sorted(export_surface.workflows_by_name))
    if requested_name:
        binding = export_surface.workflows_by_name.get(requested_name)
        canonical_name = binding.canonical_name if binding is not None else requested_name
        if canonical_name not in compile_result.entry_result.validated_bundles:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="entry_workflow_unknown",
                        message=f"entry workflow `{requested_name}` is not exported by the entry module",
                        path=source_path,
                    ),
                )
            )
        return FrontendEntrySelection(
            requested_name=requested_name,
            selected_name=canonical_name,
            canonical_name=canonical_name,
            exported_names=exported_workflows,
        )
    if len(exported_workflows) != 1:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="entry_workflow_required",
                    message="`--entry-workflow` is required when the entry module exports multiple workflows",
                    span=compile_result.graph.modules_by_name[compile_result.graph.entry_module_name].syntax_module.span,
                    form_path=("workflow-lisp",),
                    phase="cli_request",
                ),
            )
        )
    selected_name = exported_workflows[0]
    canonical_name = export_surface.workflows_by_name[selected_name].canonical_name
    return FrontendEntrySelection(
        requested_name=None,
        selected_name=canonical_name,
        canonical_name=canonical_name,
        exported_names=exported_workflows,
    )


def _maybe_load_design_delta_boundary_authority_registry(
    *,
    entry_workflow: str,
) -> Mapping[str, object] | None:
    if entry_workflow != "lisp_frontend_design_delta/drain::drain":
        return None
    try:
        payload = load_design_delta_boundary_authority_registry(
            DESIGN_DELTA_PARENT_DRAIN_BOUNDARY_AUTHORITY_PATH
        )
    except (OSError, ValueError) as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="boundary_authority_registry_invalid",
                    message=f"design-delta boundary authority registry is invalid: {exc}",
                    path=DESIGN_DELTA_PARENT_DRAIN_BOUNDARY_AUTHORITY_PATH,
                ),
            )
        ) from exc
    return {
        **payload,
        "__registry_path__": str(DESIGN_DELTA_PARENT_DRAIN_BOUNDARY_AUTHORITY_PATH),
        "__registry_sha256__": _sha256_path(DESIGN_DELTA_PARENT_DRAIN_BOUNDARY_AUTHORITY_PATH),
        "workflow_family": "design_delta_parent_drain",
    }


def _maybe_load_design_delta_value_flow_census(
    *,
    entry_workflow: str,
) -> Mapping[str, object] | None:
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


def _collect_materialize_view_effects(
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen_effect_ids: set[str] = set()
    for bundle in validated_bundles_by_name.values():
        semantic_ir_payload = workflow_semantic_ir_to_json(bundle.semantic_ir)
        for effect in extract_materialize_view_effects(semantic_ir_payload):
            effect_id = str(effect.get("effect_id", ""))
            if effect_id:
                if effect_id in seen_effect_ids:
                    continue
                seen_effect_ids.add(effect_id)
            collected.append(effect)
    return collected


def _bundle_index_by_surface_name(
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
) -> dict[str, LoadedWorkflowBundle]:
    indexed: dict[str, LoadedWorkflowBundle] = {}
    visited_bundle_ids: set[int] = set()

    def visit(bundle: LoadedWorkflowBundle) -> None:
        bundle_id = id(bundle)
        if bundle_id in visited_bundle_ids:
            return
        visited_bundle_ids.add(bundle_id)

        surface_name = getattr(bundle.surface, "name", None)
        if isinstance(surface_name, str) and surface_name:
            indexed.setdefault(surface_name, bundle)

        for imported_bundle in bundle.imports.values():
            visit(imported_bundle)

    for bundle in validated_bundles_by_name.values():
        visit(bundle)
    return indexed


def _iter_surface_steps(steps: Sequence[SurfaceStep]) -> Sequence[SurfaceStep]:
    flat_steps: list[SurfaceStep] = []

    def visit(step: SurfaceStep) -> None:
        flat_steps.append(step)

        repeat_until = getattr(step, "repeat_until", None)
        if repeat_until is not None:
            for child in getattr(repeat_until, "steps", ()) or ():
                visit(child)

        then_branch = getattr(step, "then_branch", None)
        if then_branch is not None:
            for child in getattr(then_branch, "steps", ()) or ():
                visit(child)

        else_branch = getattr(step, "else_branch", None)
        if else_branch is not None:
            for child in getattr(else_branch, "steps", ()) or ():
                visit(child)

        for child in getattr(step, "for_each_steps", ()) or ():
            visit(child)

        match_cases = getattr(step, "match_cases", None)
        if isinstance(match_cases, Mapping):
            for case in match_cases.values():
                for child in getattr(case, "steps", ()) or ():
                    visit(child)

    for step in steps:
        visit(step)
    return flat_steps


def _provider_request_field_observation(
    entry: Mapping[str, Any],
) -> dict[str, Any]:
    value_source = entry.get("value_source")
    if not isinstance(value_source, Mapping):
        return {}
    binding = value_source.get("binding")
    if not isinstance(binding, Mapping):
        return {}
    compiled_request_fields = (
        dict(entry.get("request_fields", {}))
        if isinstance(entry.get("request_fields"), Mapping)
        else {}
    )
    field_names = [str(name) for name in binding if isinstance(name, str)]
    subject = binding.get("subject")
    targets = binding.get("targets")
    observation = {
        "field_names": sorted(field_names),
        "has_subject": "subject" in binding,
        "has_targets": "targets" in binding,
        "semantic_field_count": len(subject) if isinstance(subject, Mapping) else 0,
        "write_target_field_count": len(targets) if isinstance(targets, Mapping) else 0,
    }
    for nested_type_key in ("subject_type_name", "targets_type_name"):
        nested_type_name = compiled_request_fields.get(nested_type_key)
        if isinstance(nested_type_name, str) and nested_type_name:
            observation[nested_type_key] = nested_type_name
    return observation


def _collect_provider_input_shape_observations(
    *,
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    rendering_ergonomics_policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    slots = [
        slot
        for slot in rendering_ergonomics_policy.get("consumer_slots", [])
        if isinstance(slot, Mapping)
        and isinstance(slot.get("source_form"), Mapping)
        and slot["source_form"].get("kind") == "provider_input"
    ]
    if not slots:
        return []

    bundle_index = _bundle_index_by_surface_name(validated_bundles_by_name)
    observations: list[dict[str, Any]] = []
    for slot in slots:
        workflow_surface = str(slot.get("workflow_surface", ""))
        c0_row_id = str(slot.get("c0_row_id", ""))
        if not workflow_surface or not c0_row_id:
            continue
        bundle = bundle_index.get(workflow_surface)
        if bundle is None:
            continue
        provider_call_locator = str(slot["source_form"].get("provider_call_locator", ""))
        for step in _iter_surface_steps(bundle.surface.steps):
            if getattr(step, "kind", None) is not SurfaceStepKind.PROVIDER:
                continue
            normalized_entries: list[dict[str, Any]] = []
            for entry in getattr(step, "typed_prompt_inputs", ()) or ():
                if not isinstance(entry, Mapping):
                    continue
                try:
                    normalized_entries.append(normalize_typed_prompt_input_entry(entry))
                except ValueError:
                    continue
            row_entries = [
                entry for entry in normalized_entries if entry.get("c0_row_id") == c0_row_id
            ]
            if not row_entries:
                continue
            observations.append(
                {
                    "workflow_surface": workflow_surface,
                    "provider_call_locator": provider_call_locator,
                    "provider_step_id": str(getattr(step, "step_id", "")),
                    "c0_row_id": c0_row_id,
                    "binding_names": [
                        str(entry.get("binding_name", "")) for entry in row_entries
                    ],
                    "binding_count": len(row_entries),
                    "value_type_name": str(row_entries[0].get("value_type_name", "")),
                    "request_fields": _provider_request_field_observation(row_entries[0])
                    if len(row_entries) == 1
                    else {},
                }
            )
    return observations


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

    def transform_bundle(
        workflow_name: str,
        *,
        provenance_override: WorkflowProvenance | None = None,
    ) -> LoadedWorkflowBundle:
        if provenance_override is None and workflow_name in memo:
            return memo[workflow_name]
        bundle = original_by_name[workflow_name]
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


def _reattach_bundle_provenance(
    *,
    bundle: LoadedWorkflowBundle,
    provenance: WorkflowProvenance,
) -> LoadedWorkflowBundle:
    return replace(
        bundle,
        surface=replace(bundle.surface, provenance=provenance),
        core_workflow_ast=replace(bundle.core_workflow_ast, provenance=provenance),
        ir=replace(bundle.ir, provenance=provenance),
        provenance=provenance,
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


def _build_entry_publication_report(
    *,
    compile_result: LinkedStage3CompileResult,
    entry_workflow_name: str,
    workflow_boundary_projection_payload: Mapping[str, object],
    source_map_payload: Mapping[str, object],
    consumer_rendering_census: Mapping[str, object],
) -> Mapping[str, object]:
    target_family = str(consumer_rendering_census.get("target_family", ""))
    typed_workflows_by_name = {
        workflow.definition.name: workflow
        for compiled_result in compile_result.compiled_results_by_name.values()
        for workflow in compiled_result.typed_workflows
    }
    entry_workflow = typed_workflows_by_name.get(entry_workflow_name)
    selected_rows = select_entry_publication_rows(consumer_rendering_census)
    compatibility_reasons: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    lowered_publications = _collect_entry_publication_lowerings(
        compile_result,
        source_map_payload=source_map_payload,
    )
    materialize_view_effects = _collect_materialize_view_effects(
        compile_result.validated_bundles_by_name
    )
    materialize_view_workflows = {
        str(effect.get("workflow_surface", ""))
        for effect in materialize_view_effects
        if isinstance(effect.get("workflow_surface"), str)
        and str(effect.get("authority_class", "materialized_view"))
        == "materialized_view"
    }
    published_variants: set[str] = set()
    policy_rows = ()
    if entry_workflow is not None and entry_workflow.definition.publication_policy is not None:
        policy_rows = entry_workflow.definition.publication_policy.rows
        published_variants = {row.variant for row in policy_rows}
    for row in selected_rows:
        workflow_surface = row.get("workflow_surface")
        workflow_name = workflow_surface if isinstance(workflow_surface, str) else None
        typed_workflow = (
            typed_workflows_by_name.get(workflow_name) if workflow_name is not None else None
        )
        return_kind = None
        if typed_workflow is not None and isinstance(
            typed_workflow.signature.return_type_ref, UnionTypeRef
        ):
            return_kind = "union"
        elif typed_workflow is not None:
            return_kind = "non_union"
        row_variant = row.get("variant")
        row_is_legal_entry_candidate = (
            workflow_name == entry_workflow_name
            and return_kind == "union"
            and row.get("typed_value_surface") == "terminal_result_variant"
            and row.get("value_kind") == "union_variant"
            and isinstance(row_variant, str)
        )
        if row_is_legal_entry_candidate and row_variant not in published_variants:
            diagnostics.append(
                {
                    "code": "entry_publication_c0_row_missing",
                    "row_id": str(row.get("row_id", "")),
                    "u0_row_id": str(row.get("u0_row_id", "")),
                    "workflow_name": workflow_name,
                    "variant": row_variant,
                    "message": (
                        "selected C0 entry-publication row is legal for C3 but has no "
                        "matching `:publish` policy row"
                    ),
                }
            )
            continue
        if row_is_legal_entry_candidate:
            continue
        if (
            workflow_name is not None
            and workflow_name != entry_workflow_name
            and workflow_name in materialize_view_workflows
        ):
            diagnostics.append(
                {
                    "code": "interior_publication",
                    "row_id": str(row.get("row_id", "")),
                    "u0_row_id": str(row.get("u0_row_id", "")),
                    "workflow_name": workflow_name,
                    "message": (
                        "selected non-entry C3 candidate still lowers authored "
                        "body-level materialize_view effects"
                    ),
                }
            )
        compatibility_reasons.append(
            compatibility_reason_for_selected_row(
                row,
                workflow_surface=workflow_name,
                is_entry_workflow=workflow_name == entry_workflow_name,
                return_kind=return_kind,
            )
        )
    omitted_variants: list[str] = []
    if (
        entry_workflow is not None
        and entry_workflow.definition.publication_policy is not None
        and isinstance(entry_workflow.signature.return_type_ref, UnionTypeRef)
    ):
        omitted_variants = [
            variant.name
            for variant in entry_workflow.signature.return_type_ref.definition.variants
            if variant.name not in published_variants
        ]
        lowered_publications_for_entry = [
            row
            for row in lowered_publications
            if row.get("workflow_name") == entry_workflow_name
        ]
        lowered_publication_row_ids = {
            str(row.get("row_id", ""))
            for row in lowered_publications_for_entry
            if isinstance(row.get("row_id"), str)
        }
        source_map_generated_effect_step_ids = _entry_publication_source_map_step_ids(
            source_map_payload,
            workflow_name=entry_workflow_name,
        )
        for policy_row in policy_rows:
            if policy_row.row_id not in lowered_publication_row_ids:
                diagnostics.append(
                    {
                        "code": "entry_publication_lowering_missing",
                        "row_id": policy_row.row_id,
                        "workflow_name": entry_workflow_name,
                        "variant": policy_row.variant,
                        "role": policy_row.role,
                        "message": "publication policy row did not lower to a generated materialize_view step",
                    }
                )
                continue
            matching_step_ids = {
                str(row.get("step_id", ""))
                for row in lowered_publications_for_entry
                if row.get("row_id") == policy_row.row_id and isinstance(row.get("step_id"), str)
            }
            if not matching_step_ids or not matching_step_ids.issubset(source_map_generated_effect_step_ids):
                diagnostics.append(
                    {
                        "code": "entry_publication_source_map_missing",
                        "row_id": policy_row.row_id,
                        "workflow_name": entry_workflow_name,
                        "variant": policy_row.variant,
                        "role": policy_row.role,
                        "message": "publication policy row is missing generated source-map effect lineage",
                    }
                )
        for lowered in lowered_publications_for_entry:
            lowered_variant = lowered.get("variant")
            if not isinstance(lowered_variant, str) or lowered_variant not in omitted_variants:
                continue
            diagnostics.append(
                {
                    "code": "entry_publication_omitted_variant_published",
                    "row_id": str(lowered.get("row_id", "")),
                    "workflow_name": entry_workflow_name,
                    "variant": lowered_variant,
                    "role": str(lowered.get("role", "")),
                    "message": "omitted entry-publication variant lowered a publication view",
                }
            )
    contract_isolation = {
        "workflow_signature_unchanged": entry_workflow is None
        or not hasattr(entry_workflow.signature, "publication_policy"),
        "call_contract_unchanged": entry_workflow is None
        or not hasattr(entry_workflow.signature, "publication_policy"),
        "boundary_projection_public_inputs_unchanged": all(
            "publication" not in input_name
            for workflow in workflow_boundary_projection_payload.get("workflows", [])
            if isinstance(workflow, Mapping)
            for input_name in workflow.get("boundary", {}).get("public_input_names", [])
            if isinstance(workflow.get("boundary", {}), Mapping) and isinstance(input_name, str)
        ),
        "semantic_call_edges_hide_publish_policy": all(
            "publication" not in json.dumps(_json_data(bundle.semantic_ir.call_edges), sort_keys=True)
            for bundle in compile_result.validated_bundles_by_name.values()
        ),
    }
    for check_name, passed in contract_isolation.items():
        if passed:
            continue
        diagnostics.append(
            {
                "code": "entry_publication_contract_leak",
                "row_id": check_name,
                "workflow_name": entry_workflow_name,
                "message": f"publication policy leaked into `{check_name}`",
            }
        )
    return {
        **serialize_entry_publication_report(
            target_family=target_family,
            workflow_name=entry_workflow_name,
            source_census=_json_data(consumer_rendering_census.get("source_census", {}))
            if isinstance(consumer_rendering_census.get("source_census"), Mapping)
            else {},
            consumer_rendering_census={
                "path": str(consumer_rendering_census.get("__manifest_path__", "")),
                "sha256": (
                    f"sha256:{consumer_rendering_census.get('__manifest_sha256__', '')}"
                    if consumer_rendering_census.get("__manifest_sha256__")
                    else ""
                ),
                "schema_version": str(consumer_rendering_census.get("schema_version", "")),
            },
            publication_policy=serialize_entry_publication_policy(
                entry_workflow.definition.publication_policy if entry_workflow is not None else None
            ),
            selected_c0_rows=selected_rows,
            lowered_publications=lowered_publications,
            compatibility_reasons=compatibility_reasons,
            omitted_variants=omitted_variants,
            contract_isolation=contract_isolation,
            diagnostics=diagnostics,
        ),
    }


def _collect_entry_publication_lowerings(
    compile_result: LinkedStage3CompileResult,
    *,
    source_map_payload: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    for workflow_name, bundle in sorted(compile_result.validated_bundles_by_name.items()):
        for step in _iter_surface_steps(bundle.surface.steps):
            materialize_view = getattr(step, "materialize_view", None)
            if not isinstance(materialize_view, Mapping):
                continue
            publication = materialize_view.get("publication")
            if not isinstance(publication, Mapping):
                continue
            collected.append(
                {
                    "workflow_name": workflow_name,
                    "step_id": step.step_id,
                    "step_name": step.name,
                    "row_id": str(publication.get("row_id", "")),
                    "role": str(publication.get("role", "")),
                    "variant": str(publication.get("variant", "")),
                    "renderer_id": str(materialize_view.get("renderer_id", "")),
                    "renderer_version": materialize_view.get("renderer_version"),
                    "target_path": materialize_view.get("target_path"),
                }
            )
    workflows = source_map_payload.get("workflows") if isinstance(source_map_payload, Mapping) else None
    if isinstance(workflows, Mapping):
        for workflow_name, workflow_payload in sorted(workflows.items()):
            if not isinstance(workflow_name, str) or not isinstance(workflow_payload, Mapping):
                continue
            generated_effects = workflow_payload.get("generated_semantic_effects")
            if not isinstance(generated_effects, list):
                continue
            for effect in generated_effects:
                if not isinstance(effect, Mapping) or effect.get("effect_kind") != "materialize_view":
                    continue
                details = effect.get("details")
                if not isinstance(details, Mapping):
                    continue
                role = details.get("publication_role")
                value_type = details.get("value_type")
                variant = value_type.get("variant") if isinstance(value_type, Mapping) else None
                step_id = effect.get("step_id")
                if not isinstance(role, str) or not role or not isinstance(variant, str) or not variant:
                    continue
                collected.append(
                    {
                        "workflow_name": workflow_name,
                        "step_id": str(step_id or ""),
                        "step_name": str(step_id or ""),
                        "row_id": _entry_publication_policy_row_id(
                            workflow_name=workflow_name,
                            variant=variant,
                            role=role,
                        ),
                        "role": role,
                        "variant": variant,
                        "renderer_id": str(details.get("renderer_id", "")),
                        "renderer_version": details.get("renderer_version"),
                        "target_path": details.get("target_path"),
                    }
                )
    deduped: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in collected:
        key = (
            str(row.get("workflow_name", "")),
            str(row.get("row_id", "")),
            str(row.get("step_id", "")),
        )
        deduped[key] = row
    return [deduped[key] for key in sorted(deduped)]


def _entry_publication_policy_row_id(
    *,
    workflow_name: str,
    variant: str,
    role: str,
) -> str:
    workflow_slug_source = workflow_name.rsplit("::", 1)[-1]
    return (
        f"publish.{_entry_publication_slug(workflow_slug_source)}."
        f"{variant.lower()}.{_entry_publication_slug(role)}"
    )


def _entry_publication_slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def _entry_publication_source_map_step_ids(
    source_map_payload: Mapping[str, object],
    *,
    workflow_name: str,
) -> set[str]:
    workflows = source_map_payload.get("workflows")
    if not isinstance(workflows, Mapping):
        return set()
    workflow_payload = workflows.get(workflow_name)
    if not isinstance(workflow_payload, Mapping):
        return set()
    generated_effects = workflow_payload.get("generated_semantic_effects")
    if not isinstance(generated_effects, list):
        return set()
    step_ids: set[str] = set()
    for effect in generated_effects:
        if not isinstance(effect, Mapping):
            continue
        step_id = effect.get("step_id")
        if isinstance(step_id, str) and step_id:
            step_ids.add(step_id)
    return step_ids


def _iter_surface_steps(steps: Any) -> tuple[Any, ...]:
    collected: list[Any] = []
    if not isinstance(steps, tuple):
        steps = tuple(steps)
    for step in steps:
        collected.append(step)
        match_block = getattr(step, "match", None)
        if isinstance(match_block, Mapping):
            cases = match_block.get("cases", {})
            if isinstance(cases, Mapping):
                for case in cases.values():
                    nested_steps = getattr(case, "steps", None)
                    if nested_steps:
                        collected.extend(_iter_surface_steps(nested_steps))
        for attr_name in ("then_steps", "else_steps", "repeat_until_steps", "for_each_steps"):
            nested_steps = getattr(step, attr_name, None)
            if nested_steps:
                collected.extend(_iter_surface_steps(nested_steps))
    return tuple(collected)


def _serialize_design_delta_adapter_census(
    *,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding],
    command_boundary_manifest: Mapping[str, object],
    source_map_payload: Mapping[str, object],
) -> dict[str, object]:
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
) -> dict[str, object]:
    expected_rows = build_design_delta_boundary_authority_expected_rows(dict(boundary_projection_payload))
    expected_row_keys = {
        (workflow_name, field_name, str(row["surface_kind"])): row
        for (workflow_name, field_name), row in expected_rows.items()
    }
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
        and is_design_delta_parent_drain_target_workflow(str(row.get("workflow_name", "")))
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
            generated_internal_entries = {
                str(field.get("generated_name")): field
                for field in projection_workflow.get("generated_internal_inputs", [])
                if isinstance(field, Mapping) and isinstance(field.get("generated_name"), str)
            }
            generated_internal_path_like_inputs = sorted(
                name
                for name, field in generated_internal_entries.items()
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


def _fingerprint_build(
    *,
    request: FrontendBuildRequest,
    compile_result: LinkedStage3CompileResult,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    entry_selection: FrontendEntrySelection,
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundary_manifest: Mapping[str, object],
    boundary_authority_registry: Mapping[str, object] | None,
    value_flow_census: Mapping[str, object] | None,
    consumer_rendering_census: Mapping[str, object] | None,
    observability_old_writer_pair_manifest: Mapping[str, object] | None,
    resume_plumbing_retirement_manifest: Mapping[str, object] | None,
) -> str:
    source_payload = {
        "schema_version": BUILD_SCHEMA_VERSION,
        "source_files": {
            module_name: _sha256_path(module_source.path)
            for module_name, module_source in sorted(compile_result.graph.modules_by_name.items())
        },
        "source_roots": [str(path) for path in request.source_roots],
        "entry_workflow": entry_selection.canonical_name,
        "lowering_schema_version": compile_result.entry_result.lowering_schema_version,
        "provider_externs": dict(sorted(provider_externs.items())),
        "prompt_externs": prompt_extern_source_bindings_payload(prompt_externs),
        "command_boundaries": _json_data(dict(sorted(command_boundary_manifest.items()))),
        "imported_workflow_bundles": [
            {
                "canonical_key": binding.canonical_key,
                "manifest_entry_path": binding.manifest_entry_path,
                "resolved_bundle_path": str(binding.resolved_bundle_path),
                "bundle_kind": binding.bundle_kind,
                "bundle_fingerprint": binding.bundle_fingerprint,
            }
            for binding in imported_bindings
        ],
        "boundary_authority_registry": _json_data(boundary_authority_registry)
        if boundary_authority_registry is not None
        else None,
        "value_flow_census": _json_data(value_flow_census)
        if value_flow_census is not None
        else None,
        "consumer_rendering_census": _json_data(consumer_rendering_census)
        if consumer_rendering_census is not None
        else None,
        "observability_old_writer_pair_manifest": _json_data(
            observability_old_writer_pair_manifest
        )
        if observability_old_writer_pair_manifest is not None
        else None,
        "resume_plumbing_retirement_manifest": _json_data(
            resume_plumbing_retirement_manifest
        )
        if resume_plumbing_retirement_manifest is not None
        else None,
    }
    encoded = json.dumps(source_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _write_build_artifacts(
    *,
    build_root: Path,
    compile_result: LinkedStage3CompileResult,
    validated_bundle: LoadedWorkflowBundle,
    entry_selection: FrontendEntrySelection,
    diagnostics: tuple[LispFrontendDiagnostic, ...],
    emit_debug_yaml: bool,
    executable_ir_payload: Mapping[str, object],
    semantic_ir_payload: Mapping[str, object],
    source_map_payload: Mapping[str, object],
    workflow_boundary_projection_payload: Mapping[str, object],
    adapter_census_payload: Mapping[str, object] | None,
    boundary_authority_report_payload: Mapping[str, object] | None,
    value_flow_census_report_payload: Mapping[str, object] | None,
    consumer_rendering_census_report_payload: Mapping[str, object] | None,
    typed_prompt_input_report_payload: Mapping[str, object] | None,
    observability_summary_report_payload: Mapping[str, object] | None,
    entry_publication_report_payload: Mapping[str, object] | None,
    compatibility_bridge_report_payload: Mapping[str, object] | None,
    compatibility_bridge_generated_steps: Sequence[Mapping[str, object]],
    rendering_cleanup_report_payload: Mapping[str, object] | None,
    rendering_ergonomics_report_payload: Mapping[str, object] | None,
    transition_authoring_report_payload: Mapping[str, object] | None,
    resume_plumbing_retirement_report_payload: Mapping[str, object] | None,
    default_resume_report_payload: Mapping[str, object] | None,
    g8_deletion_evidence_payload: Mapping[str, object] | None,
) -> Mapping[str, Path]:
    debug_yaml_path = build_root / "expanded.debug.yaml"
    artifact_paths = {
        "frontend_ast": build_root / "frontend_ast.json",
        "expanded_frontend_ast": build_root / "expanded_frontend_ast.json",
        "typed_frontend_ast": build_root / "typed_frontend_ast.json",
        "lowered_workflows": build_root / "lowered_workflows.json",
        "executable_ir": build_root / "executable_ir.json",
        "core_workflow_ast": build_root / "core_workflow_ast.json",
        "semantic_ir": build_root / "semantic_ir.json",
        "runtime_plan": build_root / "runtime_plan.json",
        "source_map": build_root / "source_map.json",
        "lexical_checkpoint_points": build_root / "lexical_checkpoint_points.json",
        "lexical_checkpoint_shadow_report": build_root / "lexical_checkpoint_shadow_report.json",
        "workflow_boundary_projection": build_root / "workflow_boundary_projection.json",
        "diagnostics": build_root / "diagnostics.json",
    }
    runtime_plan_payload = _public_runtime_plan_payload(validated_bundle.runtime_plan)
    source_map_json = _json_data(source_map_payload)
    if adapter_census_payload is not None:
        artifact_paths["adapter_census"] = build_root / "adapter_census.json"
    if boundary_authority_report_payload is not None:
        artifact_paths["boundary_authority_report"] = build_root / "boundary_authority_report.json"
    if value_flow_census_report_payload is not None:
        artifact_paths["value_flow_census_report"] = build_root / "value_flow_census_report.json"
    if consumer_rendering_census_report_payload is not None:
        artifact_paths["consumer_rendering_census_report"] = (
            build_root / "consumer_rendering_census_report.json"
        )
    if typed_prompt_input_report_payload is not None:
        artifact_paths["typed_prompt_input_report"] = (
            build_root / "typed_prompt_input_report.json"
        )
    if observability_summary_report_payload is not None:
        artifact_paths["observability_summary_report"] = (
            build_root / "observability_summary_report.json"
        )
    if entry_publication_report_payload is not None:
        artifact_paths["entry_publication_report"] = (
            build_root / "entry_publication_report.json"
        )
    if compatibility_bridge_report_payload is not None:
        artifact_paths["compatibility_bridge_report"] = (
            build_root / "compatibility_bridge_report.json"
        )
    if rendering_cleanup_report_payload is not None:
        artifact_paths["rendering_cleanup_report"] = (
            build_root / "rendering_cleanup_report.json"
        )
    if rendering_ergonomics_report_payload is not None:
        artifact_paths["rendering_ergonomics_report"] = (
            build_root / "rendering_ergonomics_report.json"
        )
    if transition_authoring_report_payload is not None:
        artifact_paths["transition_authoring_report"] = (
            build_root / "transition_authoring_report.json"
        )
    if resume_plumbing_retirement_report_payload is not None:
        artifact_paths["resume_plumbing_retirement_report"] = (
            build_root / "resume_plumbing_retirement_report.json"
        )
    if default_resume_report_payload is not None:
        artifact_paths["lexical_checkpoint_default_resume_report"] = (
            build_root / "lexical_checkpoint_default_resume_report.json"
        )
    if g8_deletion_evidence_payload is not None:
        artifact_paths["g8_deletion_evidence"] = build_root / "g8_deletion_evidence.json"
    payloads = {
        "frontend_ast": _serialize_frontend_ast(compile_result),
        "expanded_frontend_ast": _serialize_expanded_frontend_ast(compile_result),
        "typed_frontend_ast": _serialize_typed_frontend_ast(compile_result),
        "lowered_workflows": _serialize_lowered_workflows(
            compile_result,
            extra_compatibility_bridge_steps=compatibility_bridge_generated_steps,
        ),
        "executable_ir": executable_ir_payload,
        "core_workflow_ast": workflow_core_ast_to_json(validated_bundle.core_workflow_ast),
        "semantic_ir": semantic_ir_payload,
        "runtime_plan": runtime_plan_payload,
        "source_map": source_map_json,
        "lexical_checkpoint_points": _serialize_lexical_checkpoint_points(
            validated_bundle,
            runtime_plan_payload=runtime_plan_payload,
            semantic_ir_payload=semantic_ir_payload,
        ),
        "lexical_checkpoint_shadow_report": _serialize_lexical_checkpoint_shadow_report(
            validated_bundle,
            semantic_ir_payload=semantic_ir_payload,
            runtime_plan_payload=runtime_plan_payload,
            source_map_payload=source_map_json,
        ),
        "workflow_boundary_projection": _json_data(workflow_boundary_projection_payload),
        "diagnostics": serialize_diagnostics(diagnostics),
    }
    if adapter_census_payload is not None:
        payloads["adapter_census"] = _json_data(adapter_census_payload)
    if boundary_authority_report_payload is not None:
        payloads["boundary_authority_report"] = _json_data(boundary_authority_report_payload)
    if value_flow_census_report_payload is not None:
        payloads["value_flow_census_report"] = _json_data(value_flow_census_report_payload)
    if consumer_rendering_census_report_payload is not None:
        payloads["consumer_rendering_census_report"] = _json_data(
            consumer_rendering_census_report_payload
        )
    if typed_prompt_input_report_payload is not None:
        payloads["typed_prompt_input_report"] = _json_data(
            typed_prompt_input_report_payload
        )
    if observability_summary_report_payload is not None:
        payloads["observability_summary_report"] = _json_data(
            observability_summary_report_payload
        )
    if entry_publication_report_payload is not None:
        payloads["entry_publication_report"] = _json_data(
            entry_publication_report_payload
        )
    if compatibility_bridge_report_payload is not None:
        payloads["compatibility_bridge_report"] = _json_data(
            compatibility_bridge_report_payload
        )
    if rendering_cleanup_report_payload is not None:
        payloads["rendering_cleanup_report"] = _json_data(
            rendering_cleanup_report_payload
        )
    if rendering_ergonomics_report_payload is not None:
        payloads["rendering_ergonomics_report"] = _json_data(
            rendering_ergonomics_report_payload
        )
    if transition_authoring_report_payload is not None:
        payloads["transition_authoring_report"] = _json_data(
            transition_authoring_report_payload
        )
    if resume_plumbing_retirement_report_payload is not None:
        payloads["resume_plumbing_retirement_report"] = _json_data(
            resume_plumbing_retirement_report_payload
        )
    if default_resume_report_payload is not None:
        payloads["lexical_checkpoint_default_resume_report"] = _json_data(
            default_resume_report_payload
        )
    if g8_deletion_evidence_payload is not None:
        payloads["g8_deletion_evidence"] = _json_data(g8_deletion_evidence_payload)
    for name, path in artifact_paths.items():
        path.write_text(json.dumps(payloads[name], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if emit_debug_yaml:
        debug_yaml_path.write_text(
            render_debug_yaml(
                validated_bundle,
                source_trace_path=artifact_paths["source_map"],
            ),
            encoding="utf-8",
        )
        artifact_paths["expanded_debug_yaml"] = debug_yaml_path
    elif debug_yaml_path.exists():
        debug_yaml_path.unlink()
    return artifact_paths


def _public_runtime_plan_payload(
    runtime_plan: Any,
    *,
    extra_compatibility_bridge_steps: Sequence[Mapping[str, object]] = (),
) -> Mapping[str, Any]:
    """Serialize runtime-plan build output without private checkpoint identity."""

    payload = _json_data(runtime_plan)
    lexical_points = payload.get("lexical_checkpoint_points")
    if isinstance(lexical_points, list):
        sanitized_points: list[Any] = []
        for point in lexical_points:
            if not isinstance(point, Mapping):
                sanitized_points.append(point)
                continue
            details = point.get("details")
            if not isinstance(details, Mapping):
                sanitized_points.append(point)
                continue
            sanitized_points.append(
                {
                    **point,
                    "details": {
                        str(key): value
                        for key, value in details.items()
                        if key != "runtime_program_identity"
                    },
                }
            )
        payload = {
            **payload,
            "lexical_checkpoint_points": sanitized_points,
        }

    workflow_name = payload.get("workflow_name")
    if not isinstance(workflow_name, str) or not workflow_name:
        return payload
    nodes = payload.get("nodes")
    if not isinstance(nodes, dict):
        return payload
    observability = payload.get("observability")
    observability_nodes = (
        observability.get("nodes")
        if isinstance(observability, dict)
        and isinstance(observability.get("nodes"), dict)
        else None
    )
    ordered_node_ids = payload.get("ordered_node_ids")
    if not isinstance(ordered_node_ids, list):
        ordered_node_ids = []
        payload["ordered_node_ids"] = ordered_node_ids
    existing_step_ids = {
        str(node.get("step_id", ""))
        for node in nodes.values()
        if isinstance(node, Mapping) and isinstance(node.get("step_id"), str)
    }
    execution_indexes = [
        int(node.get("execution_index"))
        for node in nodes.values()
        if isinstance(node, Mapping) and isinstance(node.get("execution_index"), int)
    ]
    next_execution_index = max(execution_indexes) + 1 if execution_indexes else 0
    for row in extra_compatibility_bridge_steps:
        if not isinstance(row, Mapping) or row.get("workflow_name") != workflow_name:
            continue
        step_id = row.get("step_id")
        node_id = row.get("node_id")
        if not isinstance(step_id, str) or not isinstance(node_id, str):
            continue
        if step_id in existing_step_ids:
            continue
        display_name = step_id.replace("__", " ")
        node_payload = {
            "node_id": node_id,
            "step_id": step_id,
            "presentation_key": step_id,
            "display_name": display_name,
            "kind": "materialize_view",
            "region": "top_level",
            "execution_index": next_execution_index,
            "lexical_scope": [],
            "fallthrough_node_id": None,
            "routed_transfer_targets": {},
            "dependency_node_ids": [],
            "nested_body_node_ids": [],
            "call_alias": None,
            "command_boundary_kind": None,
            "command_boundary_name": None,
        }
        nodes[node_id] = node_payload
        ordered_node_ids.append(node_id)
        if observability_nodes is not None:
            observability_nodes[node_id] = {
                "node_id": node_id,
                "step_id": step_id,
                "presentation_key": step_id,
                "display_name": display_name,
                "kind": "materialize_view",
                "region": "top_level",
            }
            top_level = observability.get("top_level_ordered_node_ids")
            if isinstance(top_level, list):
                top_level.append(node_id)
        existing_step_ids.add(step_id)
        next_execution_index += 1
    return payload


def _build_manifest(
    *,
    request: FrontendBuildRequest,
    compile_result: LinkedStage3CompileResult,
    entry_selection: FrontendEntrySelection,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    artifact_paths: Mapping[str, Path],
    fingerprint: str,
    diagnostics: tuple[LispFrontendDiagnostic, ...],
    build_root: Path,
    emit_debug_yaml: bool,
    boundary_authority_registry: Mapping[str, object] | None,
    value_flow_census: Mapping[str, object] | None,
    consumer_rendering_census: Mapping[str, object] | None,
    observability_old_writer_pair_manifest: Mapping[str, object] | None,
    resume_plumbing_retirement_manifest: Mapping[str, object] | None,
) -> FrontendBuildManifest:
    return FrontendBuildManifest(
        schema_version=BUILD_SCHEMA_VERSION,
        fingerprint=fingerprint,
        source_path=str(request.source_path),
        source_roots=tuple(str(path) for path in request.source_roots),
        entry_module=compile_result.graph.entry_module_name,
        entry_workflow=entry_selection.canonical_name,
        imported_workflow_bundle_manifest_path=(
            str(request.imported_workflow_bundles_path)
            if request.imported_workflow_bundles_path is not None
            else None
        ),
        imported_workflow_bundles=tuple(
            {
                "canonical_key": binding.canonical_key,
                "manifest_entry_path": binding.manifest_entry_path,
                "resolved_bundle_path": str(binding.resolved_bundle_path),
                "resolved_workflow_name": binding.workflow_name,
                "bundle_kind": binding.bundle_kind,
                "bundle_fingerprint": binding.bundle_fingerprint,
                "load_status": binding.load_status,
            }
            for binding in imported_bindings
        ),
        compiled_module_names=tuple(sorted(compile_result.compiled_results_by_name)),
        validated_bundle_names=tuple(sorted(compile_result.validated_bundles_by_name)),
        artifact_paths={
            name: str(path.relative_to(build_root.parent.parent))
            for name, path in artifact_paths.items()
        },
        artifact_status={
            **{name: "emitted" for name in artifact_paths},
            "executable_ir": "emitted",
            "core_workflow_ast": "emitted",
            "runtime_plan": "emitted",
            "semantic_ir": "emitted",
        },
        diagnostic_count=len(diagnostics),
        shared_validation_status="validated",
        debug_yaml_status="emitted" if emit_debug_yaml else "not_requested",
        source_map_schema_version=SOURCE_MAP_SCHEMA_VERSION,
        source_map_coverage=dict(SOURCE_MAP_COVERAGE),
        lowering_schema_version=compile_result.entry_result.lowering_schema_version,
        boundary_authority_registry=_boundary_authority_registry_provenance(
            boundary_authority_registry
        ),
        value_flow_census=_value_flow_census_provenance(value_flow_census),
        consumer_rendering_census=_consumer_rendering_census_provenance(
            consumer_rendering_census
        ),
        observability_old_writer_pair_evidence=_observability_old_writer_pair_provenance(
            observability_old_writer_pair_manifest
        ),
    )


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


def _collect_origin_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "origin_key" and isinstance(item, str):
                keys.add(item)
            keys.update(_collect_origin_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_origin_keys(item))
    return keys


def _checkpoint_program_identity(
    validated_bundle: LoadedWorkflowBundle,
    *,
    runtime_plan_payload: Mapping[str, Any],
    semantic_ir_payload: Mapping[str, Any],
) -> dict[str, str]:
    workflow_path = validated_bundle.provenance.workflow_path
    source_module_digest = f"sha256:{hashlib.sha256(workflow_path.read_bytes()).hexdigest()}"
    return {
        "source_module_digest": source_module_digest,
        "executable_ir_digest": f"sha256:{hashlib.sha256(canonical_json_dumps(runtime_plan_payload).encode('utf-8')).hexdigest()}",
        "semantic_ir_digest": f"sha256:{hashlib.sha256(canonical_json_dumps(semantic_ir_payload).encode('utf-8')).hexdigest()}",
    }


def _serialize_lexical_checkpoint_points(
    validated_bundle: LoadedWorkflowBundle,
    *,
    runtime_plan_payload: Mapping[str, Any],
    semantic_ir_payload: Mapping[str, Any],
) -> dict[str, object]:
    from orchestrator.workflow_lisp.lexical_checkpoint_restore import public_restore_metadata

    points = [
        {
            "checkpoint_id": point.checkpoint_id,
            "program_point_id": point.program_point_id,
            "point_kind": point.point_kind,
            "workflow_name": point.workflow_name,
            "wcc_identity": point.details.get("wcc_identity"),
            "executable_identity": {
                "node_id": point.node_id,
                "step_id": point.step_id,
                "presentation_key": point.presentation_key,
            },
            "source_lineage": {
                "origin_key": point.origin_key,
            },
            "binding_schema": point.details.get("binding_schema"),
            "storage": point.details.get("storage"),
            "effect_boundary": point.details.get("effect_boundary"),
            "loop_back_edge": point.details.get("loop_back_edge"),
            "restore": public_restore_metadata(point.details.get("restore", {})),
        }
        for point in validated_bundle.runtime_plan.lexical_checkpoint_points
    ]
    return {
        "schema_version": CHECKPOINT_POINTS_SCHEMA_VERSION,
        "workflow_name": validated_bundle.surface.name,
        "checkpoint_schema_version": CHECKPOINT_RECORD_SCHEMA_VERSION,
        "program_identity": _checkpoint_program_identity(
            validated_bundle,
            runtime_plan_payload=runtime_plan_payload,
            semantic_ir_payload=semantic_ir_payload,
        ),
        "points": points,
    }


def _serialize_lexical_checkpoint_points_for_retirement(
    *,
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    workflow_names: set[str],
    selected_workflow_name: str,
) -> dict[str, object]:
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


def _validate_lexical_checkpoint_artifacts(
    points_payload: Mapping[str, Any],
    *,
    validated_bundle: LoadedWorkflowBundle | None = None,
    semantic_ir_payload: Mapping[str, Any],
    runtime_plan_payload: Mapping[str, Any],
    source_map_payload: Mapping[str, Any],
) -> None:
    from orchestrator.workflow_lisp.lexical_checkpoint_effect_policies import validate_effect_boundary_payload

    if points_payload.get("schema_version") != CHECKPOINT_POINTS_SCHEMA_VERSION:
        raise ValueError("lexical checkpoint points schema mismatch")
    if points_payload.get("checkpoint_schema_version") != CHECKPOINT_RECORD_SCHEMA_VERSION:
        raise ValueError("lexical checkpoint points checkpoint schema mismatch")
    runtime_node_ids = set(runtime_plan_payload.get("nodes", {}))
    origin_keys = _collect_origin_keys(source_map_payload) | _collect_origin_keys(semantic_ir_payload)
    program_identity = dict(points_payload.get("program_identity", {}))
    expected_runtime_program_identity = {
        "executable_ir_digest": f"sha256:{hashlib.sha256(canonical_json_dumps(runtime_plan_payload).encode('utf-8')).hexdigest()}",
        "semantic_ir_digest": f"sha256:{hashlib.sha256(canonical_json_dumps(semantic_ir_payload).encode('utf-8')).hexdigest()}",
    }
    for key, expected_value in expected_runtime_program_identity.items():
        if program_identity.get(key) != expected_value:
            raise ValueError("lexical checkpoint program identity drift")
    if validated_bundle is not None:
        expected_program_identity = _checkpoint_program_identity(
            validated_bundle,
            runtime_plan_payload=runtime_plan_payload,
            semantic_ir_payload=semantic_ir_payload,
        )
        if program_identity.get("source_module_digest") != expected_program_identity["source_module_digest"]:
            raise ValueError("lexical checkpoint program identity drift")
    for point in points_payload.get("points", []):
        if not isinstance(point.get("wcc_identity", {}), Mapping):
            raise ValueError("lexical checkpoint point missing WCC identity")
        if not point.get("binding_schema", {}).get("schema_digest"):
            raise ValueError("lexical checkpoint point missing binding schema digest")
        if not point.get("storage", {}).get("allocation_id"):
            raise ValueError("lexical checkpoint point missing storage allocation")
        if point.get("executable_identity", {}).get("node_id") not in runtime_node_ids:
            raise ValueError("lexical checkpoint point missing executable node linkage")
        if point.get("source_lineage", {}).get("origin_key") not in origin_keys:
            raise ValueError("lexical checkpoint point missing source-map origin coverage")
        if point.get("point_kind") == "effect_boundary":
            validate_effect_boundary_payload(
                dict(point.get("effect_boundary", {})),
                expected_origin_key=str(point.get("source_lineage", {}).get("origin_key") or ""),
            )


def _serialize_lexical_checkpoint_shadow_report(
    validated_bundle: LoadedWorkflowBundle,
    *,
    semantic_ir_payload: Mapping[str, Any],
    runtime_plan_payload: Mapping[str, Any],
    source_map_payload: Mapping[str, Any],
) -> dict[str, object]:
    points_payload = _serialize_lexical_checkpoint_points(
        validated_bundle,
        runtime_plan_payload=runtime_plan_payload,
        semantic_ir_payload=semantic_ir_payload,
    )
    _validate_lexical_checkpoint_artifacts(
        points_payload,
        validated_bundle=validated_bundle,
        semantic_ir_payload=semantic_ir_payload,
        runtime_plan_payload=runtime_plan_payload,
        source_map_payload=source_map_payload,
    )
    return {
        "schema_version": CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION,
        "workflow_name": validated_bundle.surface.name,
        "status": "pass",
        "checked_points": len(points_payload["points"]),
        "checked_records": 0,
        "missing_points": [],
        "invalid_records": [],
        "stale_records": [],
        "diagnostics": [],
    }


def _serialize_lexical_checkpoint_shadow_reports_for_retirement(
    *,
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    workflow_names: set[str],
    selected_workflow_name: str,
    source_map_payload: Mapping[str, Any],
) -> dict[str, object]:
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


def _serialize_frontend_ast(compile_result: LinkedStage3CompileResult) -> dict[str, object]:
    return {
        "entry_module": compile_result.graph.entry_module_name,
        "modules": {
            module_name: _json_data(module_source.syntax_module)
            for module_name, module_source in sorted(compile_result.graph.modules_by_name.items())
        },
    }


def _serialize_expanded_frontend_ast(compile_result: LinkedStage3CompileResult) -> dict[str, object]:
    return {
        "modules": {
            module_name: {
                "definitions": _json_data(compiled_result.module),
                "typed_workflow_names": [
                    workflow.definition.name
                    for workflow in compiled_result.typed_workflows
                ],
                "typed_procedure_names": [
                    procedure.definition.name
                    for procedure in compiled_result.typed_procedures
                ],
            }
            for module_name, compiled_result in sorted(compile_result.compiled_results_by_name.items())
        }
    }


def _serialize_typed_frontend_ast(compile_result: LinkedStage3CompileResult) -> dict[str, object]:
    return {
        "modules": {
            module_name: {
                "typed_workflows": _json_data(compiled_result.typed_workflows),
                "typed_procedures": _json_data(compiled_result.typed_procedures),
                "workflow_catalog": {
                    "signatures": sorted(compiled_result.workflow_catalog.signatures_by_name),
                },
            }
            for module_name, compiled_result in sorted(compile_result.compiled_results_by_name.items())
        }
    }


def _serialize_lowered_workflows(
    compile_result: LinkedStage3CompileResult,
    *,
    extra_compatibility_bridge_steps: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    step_ids_by_workflow: dict[str, set[str]] = {}
    for row in extra_compatibility_bridge_steps:
        if not isinstance(row, Mapping):
            continue
        workflow_name = row.get("workflow_name")
        step_id = row.get("step_id")
        if not isinstance(workflow_name, str) or not isinstance(step_id, str):
            continue
        step_ids_by_workflow.setdefault(workflow_name, set()).add(step_id)
    return {
        "modules": {
            module_name: {
                "workflows": [
                    {
                        "workflow_name": lowered.typed_workflow.definition.name,
                        "display_name": _display_workflow_name(lowered.typed_workflow.definition.name),
                        "authored_mapping": _json_data(lowered.authored_mapping),
                        "step_ids": sorted(
                            set(lowered.origin_map.step_spans)
                            | step_ids_by_workflow.get(
                                lowered.typed_workflow.definition.name, set()
                            )
                        ),
                    }
                    for lowered in compiled_result.lowered_workflows
                ],
            }
            for module_name, compiled_result in sorted(compile_result.compiled_results_by_name.items())
        }
    }


def _serialize_source_map(
    compile_result: LinkedStage3CompileResult,
    *,
    selected_name: str,
) -> dict[str, object]:
    return _json_data(
        build_source_map_document(
            compile_result,
            selected_name=selected_name,
            display_name_resolver=_display_workflow_name,
        )
    )


def _serialize_workflow_boundary_projection(
    compile_result: LinkedStage3CompileResult,
    *,
    selected_name: str,
) -> dict[str, object]:
    workflows: list[dict[str, object]] = []
    for compiled_result in compile_result.compiled_results_by_name.values():
        for lowered in compiled_result.lowered_workflows:
            projection = lowered.boundary_projection
            allocation_by_input_name: dict[str, object] = {}
            for allocation in lowered.generated_path_allocations:
                if not isinstance(allocation.generated_input_name, str):
                    continue
                current = allocation_by_input_name.get(allocation.generated_input_name)
                if current is None:
                    allocation_by_input_name[allocation.generated_input_name] = allocation
                    continue
                if (
                    getattr(current, "semantic_role", None)
                    == GeneratedPathSemanticRole.ENTRYPOINT_MANAGED_WRITE_ROOT
                    and allocation.semantic_role
                    != GeneratedPathSemanticRole.ENTRYPOINT_MANAGED_WRITE_ROOT
                ):
                    allocation_by_input_name[allocation.generated_input_name] = allocation
            bundle = compile_result.validated_bundles_by_name.get(
                lowered.typed_workflow.definition.name
            )
            if bundle is not None:
                boundary = workflow_boundary_projection(bundle)
                boundary_payload = {
                    "public_input_names": sorted(boundary.public_input_contracts),
                    "private_runtime_context_bindings": [
                        {
                            "binding_id": binding.binding_id,
                            "source_param_name": binding.source_param_name,
                            "context_family": binding.context_family,
                            "bridge_class": binding.bridge_class,
                            "derived_phase_identity": binding.derived_phase_identity,
                            "generated_input_names": sorted(binding.generated_input_names),
                            "projection_hints": _json_data(binding.projection_hints),
                            "source_provenance": _json_data(binding.source_provenance),
                        }
                        for binding in boundary.private_runtime_context_bindings
                    ],
                    "private_managed_write_root_inputs": sorted(
                        name
                        for name in boundary.private_managed_write_root_inputs
                        if isinstance(name, str)
                    ),
                    "private_compatibility_bridge_inputs": sorted(
                        name
                        for name in boundary.private_compatibility_bridge_inputs
                        if isinstance(name, str)
                    ),
                    "pure_projection_classification": {
                        "structural": is_structural_pure_projection_effect_summary(
                            lowered.typed_workflow.effect_summary
                        )
                    },
                }
            else:
                boundary_payload = {
                    "public_input_names": sorted(
                        field.generated_name
                        for field in projection.flattened_inputs
                        if field.generated_name
                        not in {
                            internal.generated_name
                            for internal in projection.generated_internal_inputs
                        }
                    ),
                    "private_runtime_context_bindings": [
                        {
                            "binding_id": binding.binding_id,
                            "source_param_name": binding.source_param_name,
                            "context_family": binding.context_family,
                            "bridge_class": binding.bridge_class,
                            "derived_phase_identity": binding.derived_phase_identity,
                            "generated_input_names": sorted(binding.generated_input_names),
                            "projection_hints": _json_data(binding.projection_hints),
                            "source_provenance": _json_data(binding.source_provenance),
                        }
                        for binding in lowered.private_exec_context_bindings
                    ],
                    "private_managed_write_root_inputs": sorted(
                        field.generated_name
                        for field in projection.generated_internal_inputs
                        if field.reason == "managed_write_root"
                    ),
                    "private_compatibility_bridge_inputs": sorted(
                        name
                        for name in lowered.compatibility_bridge_inputs
                        if isinstance(name, str)
                    ),
                    "pure_projection_classification": {
                        "structural": is_structural_pure_projection_effect_summary(
                            lowered.typed_workflow.effect_summary
                        )
                    },
                }
            workflows.append(
                {
                    "workflow_name": projection.workflow_name,
                    "display_name": projection.display_name,
                    "boundary": boundary_payload,
                    "params": [
                        {"name": param.name, "type_kind": param.type_kind}
                        for param in projection.params
                    ],
                    "return_kind": projection.return_kind,
                    "flattened_inputs": [
                        {
                            "generated_name": field.generated_name,
                            "source_path": list(field.source_path),
                            "contract_definition": _json_data(field.contract_definition),
                        }
                        for field in sorted(projection.flattened_inputs, key=lambda field: field.generated_name)
                    ],
                    "flattened_outputs": [
                        {
                            "generated_name": field.generated_name,
                            "source_path": list(field.source_path),
                            "contract_definition": _json_data(field.contract_definition),
                            **(
                                {
                                    "projection": _json_data(output_definition.get("projection"))
                                }
                                if isinstance(
                                    (lowered.authored_mapping.get("outputs", {}) or {}).get(field.generated_name),
                                    Mapping,
                                )
                                and isinstance(
                                    (
                                        (lowered.authored_mapping.get("outputs", {}) or {}).get(field.generated_name)
                                    ).get("projection"),
                                    Mapping,
                                )
                                else {}
                            ),
                        }
                        for field in sorted(projection.flattened_outputs, key=lambda field: field.generated_name)
                        for output_definition in [
                            (lowered.authored_mapping.get("outputs", {}) or {}).get(field.generated_name, {})
                        ]
                    ],
                    "generated_internal_inputs": [
                        {
                            "generated_name": field.generated_name,
                            "reason": field.reason,
                            "allocation_id": (
                                allocation_by_input_name[field.generated_name].allocation_id
                                if field.generated_name in allocation_by_input_name
                                else None
                            ),
                            "semantic_role": (
                                allocation_by_input_name[field.generated_name].semantic_role.value
                                if field.generated_name in allocation_by_input_name
                                else None
                            ),
                        }
                        for field in sorted(
                            projection.generated_internal_inputs,
                            key=lambda field: field.generated_name,
                        )
                    ],
                    "generated_path_allocations": [
                        {
                            "allocation_id": allocation.allocation_id,
                            "semantic_role": allocation.semantic_role.value,
                            "privacy": allocation.privacy.value,
                            "resume_scope": allocation.resume_scope.value,
                            "stable_identity": allocation.stable_identity,
                            "concrete_path_template": allocation.concrete_path_template,
                            "generated_input_name": allocation.generated_input_name,
                            "path_safety_policy": allocation.path_safety_policy,
                        }
                        for allocation in lowered.generated_path_allocations
                    ],
                }
            )
    workflows.sort(key=lambda workflow: str(workflow["workflow_name"]))
    return {
        "schema_version": "workflow_lisp_boundary_projection.v1",
        "entry_workflow": selected_name,
        "workflows": workflows,
    }


def _origin_payload(origin: object) -> dict[str, object]:
    span = getattr(origin, "span")
    return {
        "origin_key": getattr(origin, "origin_key", ""),
        "path": span.start.path,
        "line": span.start.line,
        "column": span.start.column,
        "form_path": list(getattr(origin, "form_path", ()) or ()),
        "notes": list(getattr(origin, "notes", ()) or ()),
    }


def _display_workflow_name(name: str) -> str:
    return name.split("::", 1)[-1]


def _command_boundary_metadata_for_workflow(
    source_map_payload: Mapping[str, object],
    *,
    workflow_name: str,
) -> Mapping[str, tuple[str, str]]:
    workflows = source_map_payload.get("workflows")
    if not isinstance(workflows, Mapping):
        return {}
    workflow_payload = workflows.get(workflow_name)
    if not isinstance(workflow_payload, Mapping):
        return {}
    command_boundaries = workflow_payload.get("command_boundaries")
    if not isinstance(command_boundaries, list):
        return {}
    metadata: dict[str, tuple[str, str]] = {}
    for boundary in command_boundaries:
        if not isinstance(boundary, Mapping):
            continue
        step_id = boundary.get("step_id")
        boundary_kind = boundary.get("boundary_kind")
        boundary_name = boundary.get("adapter_name") or boundary.get("command_name")
        if (
            isinstance(step_id, str)
            and step_id
            and isinstance(boundary_kind, str)
            and boundary_kind
            and isinstance(boundary_name, str)
            and boundary_name
        ):
            metadata[step_id] = (boundary_kind, boundary_name)
            if not step_id.startswith("root."):
                metadata[f"root.{step_id}"] = (boundary_kind, boundary_name)
    return metadata


def _load_json_file(path: Path, *, label: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_manifest_missing",
                    message=f"{label} does not exist",
                    path=path,
                ),
            )
        ) from exc
    except json.JSONDecodeError as exc:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="workflow_lisp_manifest_invalid_json",
                    message=f"{label} must contain valid JSON",
                    path=path,
                    line=exc.lineno,
                    column=exc.colno,
                    offset=exc.pos,
                    notes=(exc.msg,),
                ),
            )
        ) from exc


def _resolve_manifest_relative_path(manifest_path: Path, entry_path: str) -> Path:
    candidate = Path(entry_path)
    if not candidate.is_absolute():
        candidate = (manifest_path.parent / candidate).resolve()
    return candidate


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cli_request_diagnostic(
    *,
    code: str,
    message: str,
    path: Path,
    line: int = 1,
    column: int = 1,
    offset: int = 0,
    notes: tuple[str, ...] = (),
) -> LispFrontendDiagnostic:
    return LispFrontendDiagnostic(
        code=code,
        message=message,
        span=SourceSpan(
            start=SourcePosition(path=str(path), line=line, column=column, offset=offset),
            end=SourcePosition(path=str(path), line=line, column=column, offset=offset),
        ),
        notes=notes,
        phase="cli_request",
    )


def _json_data(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_data(item) for item in value]
    if isinstance(value, list):
        return [_json_data(item) for item in value]
    if is_dataclass(value):
        return {
            field.name: _json_data(getattr(value, field.name))
            for field in fields(value)
        }
    if hasattr(value, "__dict__"):
        return {
            key: _json_data(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return repr(value)
