"""Frontend-owned build and artifact helpers for Workflow Lisp entrypoints."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.runtime_plan import enrich_workflow_runtime_plan
from orchestrator.workflow.semantic_ir import derive_workflow_semantic_ir, workflow_semantic_ir_to_json
from orchestrator.workflow.surface_ast import SurfaceStep, SurfaceStepKind, WorkflowProvenance

from .build_manifest_io import (
    _cli_request_diagnostic,
    _json_data,
    _load_command_boundaries_manifest_payload,
    _load_json_file,
    _load_prompt_extern_mapping,
    _load_string_mapping,
    _parse_command_boundaries_manifest,
    _resolve_manifest_relative_path,
    _resolve_request,
    _sha256_path,
)
from .build_design_delta import (
    DesignDeltaEvidence,
    DesignDeltaReportPayloads,
    _allowed_resume_plumbing_retirement_registry_rows,
    _augment_design_delta_compatibility_bridge_lineage,
    _build_design_delta_observability_summary_prerequisite_report,
    _build_slug,
    _compatibility_bridge_manifest_value_document,
    _compatibility_bridge_surface_step,
    _compatibility_bridge_target_binding,
    _compatibility_bridge_value_document,
    _design_delta_contract_is_path_like,
    _design_delta_generated_internal_entry_is_path_like,
    _design_delta_prerequisite_report_paths,
    _family_profile_metadata_for_entry,
    _is_design_delta_family_profile_candidate,
    _materialize_design_delta_compatibility_bridge_bundles,
    _maybe_load_design_delta_boundary_authority_registry,
    _maybe_load_design_delta_compatibility_bridge_manifest,
    _maybe_load_design_delta_consumer_rendering_census,
    _maybe_load_design_delta_family_profile_catalog,
    _maybe_load_design_delta_observability_old_writer_pair_manifest,
    _maybe_load_design_delta_rendering_cleanup_manifest,
    _maybe_load_design_delta_rendering_ergonomics_manifest,
    _maybe_load_design_delta_resume_plumbing_retirement_manifest,
    _maybe_load_design_delta_transition_authoring_manifest,
    _maybe_load_design_delta_value_flow_census,
    _maybe_load_design_delta_view_dual_run_report,
    _maybe_load_design_delta_view_dual_run_vectors,
    _resume_plumbing_retirement_source_texts,
    _serialize_design_delta_adapter_census,
    _serialize_design_delta_boundary_authority_report,
    _serialize_design_delta_g8_deletion_evidence,
    _serialize_lexical_checkpoint_points_for_retirement,
    _serialize_lexical_checkpoint_shadow_reports_for_retirement,
    _surface_with_compatibility_bridge_steps,
    _with_report_path,
    load_design_delta_evidence,
    load_design_delta_family_catalog,
    serialize_design_delta_reports,
)
from .build_artifacts import (
    _build_entry_publication_report,
    _build_manifest,
    _checkpoint_program_identity,
    _collect_entry_publication_lowerings,
    _collect_origin_keys,
    _command_boundary_metadata_for_workflow,
    _display_workflow_name,
    _entry_publication_policy_row_id,
    _entry_publication_slug,
    _entry_publication_source_map_step_ids,
    _fingerprint_build,
    _origin_payload,
    _public_runtime_plan_payload as _public_runtime_plan_payload_export,
    _serialize_expanded_frontend_ast,
    _serialize_frontend_ast,
    _serialize_lexical_checkpoint_points,
    _serialize_lexical_checkpoint_shadow_report,
    _serialize_lowered_workflows,
    _serialize_source_map,
    _serialize_typed_frontend_ast,
    _serialize_workflow_boundary_projection,
    _validate_lexical_checkpoint_artifacts,
    _validate_selected_workflow_hidden_compatibility_bridge_public_boundary,
    _write_build_artifacts,
)

_public_runtime_plan_payload = _public_runtime_plan_payload_export

from .command_boundaries import CertifiedAdapterBinding, ExternalToolBinding
from .compiler import LinkedStage3CompileResult, compile_stage3_entrypoint
from .consumer_rendering_census import (
    build_consumer_rendering_census_report,
    extract_materialize_view_effects,
)
from .compatibility_bridges import build_compatibility_bridge_report
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .family_profiles import WorkflowFamilyProfileCatalog
from .form_registry import get_form_spec
from .lints import LINT_PROFILE_DEFAULT
from .parent_drain_census_alignment import (
    build_parent_drain_census_alignment_report,
)
from . import lexical_checkpoint_default_resume
from . import resume_plumbing_retirement
from .source_map import SOURCE_MAP_COVERAGE, SOURCE_MAP_SCHEMA_VERSION
from .typed_prompt_inputs import (
    build_typed_prompt_input_report,
    normalize_typed_prompt_input_entry,
)
from .reference_family_conformance import (
    build_reference_family_conformance_profile,
)
from .rendering_cleanup import build_rendering_cleanup_report
from .rendering_ergonomics import build_rendering_ergonomics_report
from .transition_authoring import build_transition_authoring_report
from .value_flow_census import reconcile_value_flow_census
from .wcc.route import LoweringRoute


# Names below are not referenced elsewhere in this module (they are read by
# build_design_delta.py, either as re-exports or via a deferred, function-body
# import; or by build_artifacts.py, whose serializers/writers are re-exported
# here so test monkeypatches and deferred `from .build import ...` lookups of
# `build.<name>` remain observable). They must stay resolvable as
# `build.<name>`, which would otherwise read as unused imports.
__all__ = [
    "_allowed_resume_plumbing_retirement_registry_rows",
    "_augment_design_delta_compatibility_bridge_lineage",
    "_build_design_delta_observability_summary_prerequisite_report",
    "_build_entry_publication_report",
    "_build_slug",
    "_checkpoint_program_identity",
    "_collect_entry_publication_lowerings",
    "_collect_origin_keys",
    "_compatibility_bridge_manifest_value_document",
    "_compatibility_bridge_surface_step",
    "_compatibility_bridge_target_binding",
    "_compatibility_bridge_value_document",
    "_design_delta_contract_is_path_like",
    "_design_delta_generated_internal_entry_is_path_like",
    "_design_delta_prerequisite_report_paths",
    "_display_workflow_name",
    "_entry_publication_policy_row_id",
    "_entry_publication_slug",
    "_entry_publication_source_map_step_ids",
    "_family_profile_metadata_for_entry",
    "_is_design_delta_family_profile_candidate",
    "_maybe_load_design_delta_boundary_authority_registry",
    "_maybe_load_design_delta_compatibility_bridge_manifest",
    "_maybe_load_design_delta_consumer_rendering_census",
    "_maybe_load_design_delta_family_profile_catalog",
    "_maybe_load_design_delta_observability_old_writer_pair_manifest",
    "_maybe_load_design_delta_rendering_cleanup_manifest",
    "_maybe_load_design_delta_rendering_ergonomics_manifest",
    "_maybe_load_design_delta_resume_plumbing_retirement_manifest",
    "_maybe_load_design_delta_transition_authoring_manifest",
    "_maybe_load_design_delta_value_flow_census",
    "_maybe_load_design_delta_view_dual_run_report",
    "_maybe_load_design_delta_view_dual_run_vectors",
    "_origin_payload",
    "_resume_plumbing_retirement_source_texts",
    "_serialize_design_delta_adapter_census",
    "_serialize_design_delta_boundary_authority_report",
    "_serialize_design_delta_g8_deletion_evidence",
    "_serialize_expanded_frontend_ast",
    "_serialize_frontend_ast",
    "_serialize_lexical_checkpoint_points",
    "_serialize_lexical_checkpoint_points_for_retirement",
    "_serialize_lexical_checkpoint_shadow_report",
    "_serialize_lexical_checkpoint_shadow_reports_for_retirement",
    "_serialize_lowered_workflows",
    "_serialize_typed_frontend_ast",
    "_surface_with_compatibility_bridge_steps",
    "_validate_lexical_checkpoint_artifacts",
    "_with_report_path",
    "build_compatibility_bridge_report",
    "build_consumer_rendering_census_report",
    "build_parent_drain_census_alignment_report",
    "build_reference_family_conformance_profile",
    "build_rendering_cleanup_report",
    "build_rendering_ergonomics_report",
    "build_transition_authoring_report",
    "build_typed_prompt_input_report",
    "get_form_spec",
    "lexical_checkpoint_default_resume",
    "reconcile_value_flow_census",
    "resume_plumbing_retirement",
]


BUILD_SCHEMA_VERSION = "workflow_lisp_build.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DESIGN_DELTA_PARENT_DRAIN_COMMAND_BOUNDARIES_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)
DESIGN_DELTA_PARENT_DRAIN_FAMILY_PROFILE_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.family_profile.json"
)
DESIGN_DELTA_PARENT_DRAIN_BOUNDARY_AUTHORITY_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.boundary_authority.json"
)
DESIGN_DELTA_PARENT_DRAIN_VALUE_FLOW_CENSUS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.value_flow_census.json"
)
DESIGN_DELTA_PARENT_DRAIN_CONSUMER_RENDERING_CENSUS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.consumer_rendering_census.json"
)
DESIGN_DELTA_PARENT_DRAIN_COMPATIBILITY_BRIDGES_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.compatibility_bridges.json"
)
DESIGN_DELTA_PARENT_DRAIN_RENDERING_CLEANUP_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.rendering_cleanup.json"
)
DESIGN_DELTA_PARENT_DRAIN_RENDERING_ERGONOMICS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.rendering_ergonomics.json"
)
DESIGN_DELTA_PARENT_DRAIN_TRANSITION_AUTHORING_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.transition_authoring.json"
)
DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_VECTORS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_view_dual_run_vectors.json"
)
DESIGN_DELTA_PARENT_DRAIN_VIEW_DUAL_RUN_REPORT_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN"
    / "migration-parity"
    / "design_delta_parent_drain_view_dual_run_report.json"
)
DESIGN_DELTA_PARENT_DRAIN_RESUME_PLUMBING_RETIREMENT_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.resume_plumbing_retirement.json"
)
DESIGN_DELTA_PARENT_DRAIN_OBSERVABILITY_OLD_WRITER_COMPARISONS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.observability_old_writer_comparisons.json"
)
DESIGN_DELTA_PARENT_DRAIN_BLOCKED_IMPLEMENTATION_CHECKS_REPORT_LEGACY_PAYLOAD_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.blocked_implementation_checks_report.legacy_writer_payload.json"
)
REFERENCE_FAMILY_RUN_STATE_PATH = (
    REPO_ROOT
    / "state"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "drain"
    / "run_state.json"
)
REFERENCE_FAMILY_DRAIN_SUMMARY_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "drain-summary.json"
)
REFERENCE_FAMILY_DESIGN_GAP_SUMMARY_ROOT = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "design-gaps"
)
REFERENCE_FAMILY_IMPLEMENTATION_ARCHITECTURE_ROOT = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "design-gaps"
)
REFERENCE_FAMILY_ARCHITECTURE_INDEX_PATH = (
    REPO_ROOT
    / "state"
    / "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN"
    / "drain"
    / "iterations"
    / "12"
    / "done-review"
    / "design-gap-architect"
    / "existing-architecture-index.md"
)
REFERENCE_FAMILY_TARGET_DESIGN_PATH = (
    REPO_ROOT / "docs" / "design" / "workflow_lisp_runtime_native_drain_authoring.md"
)
REFERENCE_FAMILY_BASELINE_DESIGN_PATH = (
    REPO_ROOT / "docs" / "design" / "workflow_lisp_frontend_specification.md"
)
REFERENCE_FAMILY_COMMAND_ADAPTER_CONTRACT_PATH = (
    REPO_ROOT / "docs" / "design" / "workflow_command_adapter_contract.md"
)
REFERENCE_FAMILY_PARITY_TARGETS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "parity_targets.json"
)
REFERENCE_FAMILY_PARITY_REPORT_JSON_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "review-parity-check"
    / "design_delta_parent_drain.json"
)
REFERENCE_FAMILY_PARITY_REPORT_MARKDOWN_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "review-parity-check"
    / "design_delta_parent_drain.md"
)
REFERENCE_FAMILY_PARITY_INDEX_PATH = (
    REPO_ROOT / "artifacts" / "work" / "review-parity-check" / "index.json"
)


@dataclass(frozen=True)
class ReferenceFamilyEvidencePaths:
    run_state_path: Path
    drain_summary_path: Path
    design_gap_summary_root: Path
    implementation_architecture_root: Path
    architecture_index_path: Path
    target_design_path: Path
    baseline_design_path: Path
    command_adapter_contract_path: Path
    parity_targets_path: Path
    parity_report_json_path: Path
    parity_report_markdown_path: Path
    parity_index_path: Path


def _reference_family_versioned_roots() -> list[tuple[int, str, Path, Path]]:
    candidates: list[tuple[int, str, Path, Path]] = []
    for run_state_path in (REPO_ROOT / "state").glob(
        "LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*/drain/run_state.json"
    ):
        root_name = run_state_path.parents[1].name
        if "-R" not in root_name:
            continue
        try:
            version = int(root_name.rsplit("-R", 1)[1])
        except ValueError:
            continue
        artifact_root = REPO_ROOT / "artifacts" / "work" / root_name
        drain_summary_path = artifact_root / "drain-summary.json"
        design_gap_summary_root = artifact_root / "design-gaps"
        if drain_summary_path.is_file() and design_gap_summary_root.is_dir():
            candidates.append((version, root_name, run_state_path, artifact_root))
    return sorted(candidates)


def _reference_family_implementation_root_from_run_state(
    run_state_payload: Mapping[str, object],
    *,
    default_root_name: str,
) -> Path:
    candidate_roots: list[Path] = []
    stack: list[object] = [run_state_payload]
    while stack:
        current = stack.pop(0)
        if isinstance(current, Mapping):
            architecture_path = current.get("architecture_path")
            if isinstance(architecture_path, str):
                path_parts = Path(architecture_path).parts
                if (
                    len(path_parts) >= 4
                    and path_parts[0] == "docs"
                    and path_parts[1] == "plans"
                    and path_parts[3] == "design-gaps"
                ):
                    candidate_roots.append(REPO_ROOT.joinpath(*path_parts[:4]))
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    for root in candidate_roots:
        if root.is_dir():
            return root
    versioned_root = REPO_ROOT / "docs" / "plans" / default_root_name / "design-gaps"
    if versioned_root.is_dir():
        return versioned_root
    return REFERENCE_FAMILY_IMPLEMENTATION_ARCHITECTURE_ROOT


def _resolve_reference_family_architecture_index(root_name: str) -> Path:
    versioned_iterations_root = REPO_ROOT / "state" / root_name / "drain" / "iterations"
    candidates = sorted(
        versioned_iterations_root.glob("*/done-review/design-gap-architect/existing-architecture-index.md")
    )
    if not candidates:
        candidates = sorted(
            versioned_iterations_root.glob("*/design-gap-architect/existing-architecture-index.md")
        )
    if candidates:
        return candidates[-1]
    if versioned_iterations_root.exists():
        return versioned_iterations_root / "existing-architecture-index.md"
    return REFERENCE_FAMILY_ARCHITECTURE_INDEX_PATH


def _resolve_reference_family_evidence_paths() -> ReferenceFamilyEvidencePaths:
    versioned_roots = _reference_family_versioned_roots()
    if versioned_roots:
        _version, root_name, run_state_path, artifact_root = versioned_roots[-1]
        run_state_payload = json.loads(run_state_path.read_text(encoding="utf-8"))
        implementation_architecture_root = _reference_family_implementation_root_from_run_state(
            run_state_payload,
            default_root_name=root_name,
        )
        return ReferenceFamilyEvidencePaths(
            run_state_path=run_state_path,
            drain_summary_path=artifact_root / "drain-summary.json",
            design_gap_summary_root=artifact_root / "design-gaps",
            implementation_architecture_root=implementation_architecture_root,
            architecture_index_path=_resolve_reference_family_architecture_index(root_name),
            target_design_path=REFERENCE_FAMILY_TARGET_DESIGN_PATH,
            baseline_design_path=REFERENCE_FAMILY_BASELINE_DESIGN_PATH,
            command_adapter_contract_path=REFERENCE_FAMILY_COMMAND_ADAPTER_CONTRACT_PATH,
            parity_targets_path=REFERENCE_FAMILY_PARITY_TARGETS_PATH,
            parity_report_json_path=REFERENCE_FAMILY_PARITY_REPORT_JSON_PATH,
            parity_report_markdown_path=REFERENCE_FAMILY_PARITY_REPORT_MARKDOWN_PATH,
            parity_index_path=REFERENCE_FAMILY_PARITY_INDEX_PATH,
        )
    return ReferenceFamilyEvidencePaths(
        run_state_path=REFERENCE_FAMILY_RUN_STATE_PATH,
        drain_summary_path=REFERENCE_FAMILY_DRAIN_SUMMARY_PATH,
        design_gap_summary_root=REFERENCE_FAMILY_DESIGN_GAP_SUMMARY_ROOT,
        implementation_architecture_root=REFERENCE_FAMILY_IMPLEMENTATION_ARCHITECTURE_ROOT,
        architecture_index_path=REFERENCE_FAMILY_ARCHITECTURE_INDEX_PATH,
        target_design_path=REFERENCE_FAMILY_TARGET_DESIGN_PATH,
        baseline_design_path=REFERENCE_FAMILY_BASELINE_DESIGN_PATH,
        command_adapter_contract_path=REFERENCE_FAMILY_COMMAND_ADAPTER_CONTRACT_PATH,
        parity_targets_path=REFERENCE_FAMILY_PARITY_TARGETS_PATH,
        parity_report_json_path=REFERENCE_FAMILY_PARITY_REPORT_JSON_PATH,
        parity_report_markdown_path=REFERENCE_FAMILY_PARITY_REPORT_MARKDOWN_PATH,
        parity_index_path=REFERENCE_FAMILY_PARITY_INDEX_PATH,
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
    source_sha256: str
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
    family_profile: Mapping[str, object] | None = None
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

    Stage pipeline (each stage is a private helper defined immediately below):
    `_compile_entry` (manifest-fed compile + entry selection) ->
    `_select_and_reattach` (bridge materialization, provenance/semantic-IR
    reattach, fingerprint, build_root) -> `serialize_design_delta_reports` ->
    `_emit` (artifact/manifest writes + `FrontendBuildResult` construction).
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
    family_profile_catalog = load_design_delta_family_catalog(
        entry_workflow=resolved_request.entry_workflow,
        source_path=resolved_request.source_path,
    )

    compile_result, entry_selection = _compile_entry(
        resolved_request,
        family_catalog=family_profile_catalog,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles=imported_workflow_bundles,
        command_boundaries=command_boundaries,
    )
    design_delta = load_design_delta_evidence(
        family_profile_catalog,
        entry_workflow=resolved_request.entry_workflow,
        canonical_entry_name=entry_selection.canonical_name,
        source_path=resolved_request.source_path,
        command_boundary_manifest=command_boundary_manifest,
    )

    reattached = _select_and_reattach(
        compile_result,
        entry_selection,
        resolved_request=resolved_request,
        design_delta=design_delta,
        imported_bindings=imported_bindings,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundary_manifest=command_boundary_manifest,
        family_profile_catalog=family_profile_catalog,
    )
    semantic_ir_payload = workflow_semantic_ir_to_json(reattached.validated_bundle.semantic_ir)
    executable_ir_payload = workflow_executable_ir_to_json(reattached.validated_bundle.ir)

    report_payloads = serialize_design_delta_reports(
        design_delta,
        compile_result=compile_result,
        entry_selection=entry_selection,
        validated_bundles_by_name=reattached.validated_bundles_by_name,
        workflow_boundary_projection_payload=reattached.workflow_boundary_projection_payload,
        source_map_payload=reattached.source_map_payload,
        command_boundaries=command_boundaries,
        command_boundary_manifest=command_boundary_manifest,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        resolved_request=resolved_request,
        build_root=reattached.build_root,
    )

    return _emit(
        reattached.validated_bundle,
        report_payloads,
        build_root=reattached.build_root,
        compile_result=compile_result,
        entry_selection=entry_selection,
        resolved_request=resolved_request,
        imported_bindings=imported_bindings,
        fingerprint=reattached.fingerprint,
        semantic_ir_payload=semantic_ir_payload,
        executable_ir_payload=executable_ir_payload,
        source_map_payload=reattached.source_map_payload,
        workflow_boundary_projection_payload=reattached.workflow_boundary_projection_payload,
        design_delta=design_delta,
    )


def _compile_entry(
    resolved_request: FrontendBuildRequest,
    *,
    family_catalog: WorkflowFamilyProfileCatalog | None,
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle],
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding],
) -> tuple[LinkedStage3CompileResult, FrontendEntrySelection]:
    """Compile the entry module graph and select the requested export.

    Stage 1 of `build_frontend_bundle` (see its docstring for the full
    pipeline): `compile_stage3_entrypoint` + `_select_entry_workflow`.
    """

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
        family_profile_catalog=family_catalog,
    )

    entry_selection = _select_entry_workflow(
        compile_result,
        requested_name=resolved_request.entry_workflow,
        source_path=resolved_request.source_path,
    )
    return compile_result, entry_selection


@dataclass(frozen=True)
class _SelectAndReattachResult:
    """Return bundle for `_select_and_reattach`.

    A plain tuple would exceed the ~5-element readability threshold (7 fields),
    so this groups them; see `build_frontend_bundle`'s stage-pipeline docstring.
    """

    validated_bundle: LoadedWorkflowBundle
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle]
    source_map_payload: Mapping[str, object]
    workflow_boundary_projection_payload: Mapping[str, object]
    build_root: Path
    fingerprint: str
    provenance: WorkflowProvenance


def _select_and_reattach(
    compile_result: LinkedStage3CompileResult,
    entry_selection: FrontendEntrySelection,
    *,
    resolved_request: FrontendBuildRequest,
    design_delta: DesignDeltaEvidence,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundary_manifest: Mapping[str, object],
    family_profile_catalog: WorkflowFamilyProfileCatalog | None,
) -> _SelectAndReattachResult:
    """Materialize compatibility-bridge bundles and reattach provenance/semantic IR.

    Stage 2 of `build_frontend_bundle` (see its docstring for the full
    pipeline): selects the validated bundle for the entry workflow, serializes
    the source map and workflow-boundary projection, validates the
    hidden-bridge public boundary, computes the content-addressed fingerprint
    and build_root, materializes compatibility-bridge bundles, and reattaches
    provenance/runtime-plan/semantic-IR to the validated bundle.
    """

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
        boundary_authority_registry=design_delta.boundary_authority_registry,
    )
    _validate_selected_workflow_hidden_compatibility_bridge_public_boundary(
        workflow_boundary_projection_payload,
        selected_name=entry_selection.canonical_name,
        boundary_authority_registry=design_delta.boundary_authority_registry,
        family_profile_catalog=family_profile_catalog,
    )
    fingerprint = _fingerprint_build(
        request=resolved_request,
        compile_result=compile_result,
        imported_bindings=imported_bindings,
        entry_selection=entry_selection,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundary_manifest=command_boundary_manifest,
        family_profile_catalog=family_profile_catalog,
        boundary_authority_registry=design_delta.boundary_authority_registry,
        value_flow_census=design_delta.value_flow_census,
        consumer_rendering_census=design_delta.consumer_rendering_census,
        observability_old_writer_pair_manifest=design_delta.observability_old_writer_pair_manifest,
        resume_plumbing_retirement_manifest=design_delta.resume_plumbing_retirement_manifest,
    )
    build_root = resolved_request.workspace_root / ".orchestrate" / "build" / fingerprint
    build_root.mkdir(parents=True, exist_ok=True)

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
            compatibility_bridge_manifest=design_delta.compatibility_bridge_manifest,
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
    validated_bundle = _reattach_bundle_semantic_ir(validated_bundle)
    validated_bundles_by_name = {
        **dict(validated_bundles_by_name),
        entry_selection.canonical_name: validated_bundle,
    }
    return _SelectAndReattachResult(
        validated_bundle=validated_bundle,
        validated_bundles_by_name=validated_bundles_by_name,
        source_map_payload=source_map_payload,
        workflow_boundary_projection_payload=workflow_boundary_projection_payload,
        build_root=build_root,
        fingerprint=fingerprint,
        provenance=provenance,
    )


def _emit(
    validated_bundle: LoadedWorkflowBundle,
    report_payloads: DesignDeltaReportPayloads,
    *,
    build_root: Path,
    compile_result: LinkedStage3CompileResult,
    entry_selection: FrontendEntrySelection,
    resolved_request: FrontendBuildRequest,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    fingerprint: str,
    semantic_ir_payload: Mapping[str, object],
    executable_ir_payload: Mapping[str, object],
    source_map_payload: Mapping[str, object],
    workflow_boundary_projection_payload: Mapping[str, object],
    design_delta: DesignDeltaEvidence,
) -> FrontendBuildResult:
    """Write build artifacts and the manifest, and assemble the build result.

    Stage 4 of `build_frontend_bundle` (see its docstring for the full
    pipeline): `_write_build_artifacts` + `_build_manifest` + manifest write +
    `FrontendBuildResult` construction.
    """

    diagnostics = compile_result.diagnostics
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
        design_delta_reports=report_payloads,
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
        family_profile=design_delta.family_profile_metadata,
        boundary_authority_registry=design_delta.boundary_authority_registry,
        value_flow_census=design_delta.value_flow_census,
        consumer_rendering_census=design_delta.consumer_rendering_census,
        observability_old_writer_pair_manifest=design_delta.observability_old_writer_pair_manifest,
        resume_plumbing_retirement_manifest=design_delta.resume_plumbing_retirement_manifest,
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
    field_authority = (
        dict(compiled_request_fields.get("field_authority", {}))
        if isinstance(compiled_request_fields.get("field_authority"), Mapping)
        else {}
    )
    hidden_bridge_fields = [
        {
            "field_path": field_path,
            **{
                key: value
                for key, value in metadata.items()
                if key
                in {
                    "authority_class",
                    "source_binding",
                    "bridge_field_name",
                    "checked_row_id",
                }
            },
        }
        for field_path, metadata in sorted(field_authority.items())
        if isinstance(field_path, str)
        and isinstance(metadata, Mapping)
        and metadata.get("authority_class") == "compatibility_bridge"
    ]
    if hidden_bridge_fields:
        observation["hidden_bridge_fields"] = hidden_bridge_fields
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


def _reattach_bundle_semantic_ir(bundle: LoadedWorkflowBundle) -> LoadedWorkflowBundle:
    semantic_ir = derive_workflow_semantic_ir(
        core_workflow_ast=bundle.core_workflow_ast,
        surface=bundle.surface,
        ir=bundle.ir,
        projection=bundle.projection,
        runtime_plan=bundle.runtime_plan,
        imports=bundle.imports,
        provenance=bundle.provenance,
    )
    return replace(bundle, semantic_ir=semantic_ir)
