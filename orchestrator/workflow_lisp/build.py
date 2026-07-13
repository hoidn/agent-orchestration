"""Frontend-owned build and artifact helpers for Workflow Lisp entrypoints."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.runtime_plan import enrich_workflow_runtime_plan
from orchestrator.workflow.semantic_ir import derive_workflow_semantic_ir, workflow_semantic_ir_to_json
from orchestrator.workflow.surface_ast import WorkflowProvenance

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
from .build_design_delta import serialize_design_delta_g8_deletion_evidence
from .build_artifacts import (
    _build_manifest,
    _checkpoint_program_identity,
    _collect_origin_keys,
    _command_boundary_metadata_for_workflow,
    _display_workflow_name,
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
    _write_build_artifacts,
)

_public_runtime_plan_payload = _public_runtime_plan_payload_export

from .command_boundaries import CertifiedAdapterBinding, ExternalToolBinding
from .compiler import LinkedStage3CompileResult, compile_stage3_entrypoint
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .lints import LINT_PROFILE_DEFAULT
from .source_map import SOURCE_MAP_COVERAGE, SOURCE_MAP_SCHEMA_VERSION
from .wcc.route import LoweringRoute


# Artifact helpers remain re-exported from this historical module boundary so
# existing callers and monkeypatch-based tests do not depend on the file split.
__all__ = [
    "_checkpoint_program_identity",
    "_collect_origin_keys",
    "_display_workflow_name",
    "_origin_payload",
    "_serialize_expanded_frontend_ast",
    "_serialize_frontend_ast",
    "_serialize_lexical_checkpoint_points",
    "_serialize_lexical_checkpoint_shadow_report",
    "_serialize_lowered_workflows",
    "_serialize_typed_frontend_ast",
    "_validate_lexical_checkpoint_artifacts",
]

BUILD_SCHEMA_VERSION = "workflow_lisp_build.v1"
FRONTEND_ARTIFACT_EXPORT_FILENAMES = {
    "executable_ir": "executable_ir.json",
    "core_workflow_ast": "core_workflow_ast.json",
    "runtime_plan": "runtime_plan.json",
    "semantic_ir": "semantic_ir.json",
    "source_map": "source_map.json",
    "lexical_checkpoint_points": "lexical_checkpoint_points.json",
    "lexical_checkpoint_shadow_report": "lexical_checkpoint_shadow_report.json",
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
    `_select_and_reattach` (provenance/semantic-IR reattach, fingerprint,
    build_root) -> `_emit` (artifact/manifest writes + result construction).
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
    compile_result, entry_selection = _compile_entry(
        resolved_request,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles=imported_workflow_bundles,
        command_boundaries=command_boundaries,
    )
    reattached = _select_and_reattach(
        compile_result,
        entry_selection,
        resolved_request=resolved_request,
        imported_bindings=imported_bindings,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundary_manifest=command_boundary_manifest,
    )
    semantic_ir_payload = workflow_semantic_ir_to_json(reattached.validated_bundle.semantic_ir)
    executable_ir_payload = workflow_executable_ir_to_json(reattached.validated_bundle.ir)

    g8_deletion_evidence = (
        serialize_design_delta_g8_deletion_evidence(
            command_boundary_manifest=command_boundary_manifest,
        )
        if entry_selection.canonical_name == "lisp_frontend_design_delta/drain::drain"
        else None
    )

    return _emit(
        reattached.validated_bundle,
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
        g8_deletion_evidence=g8_deletion_evidence,
    )


def _compile_entry(
    resolved_request: FrontendBuildRequest,
    *,
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

    The dataclass keeps the five stage outputs named at the pipeline boundary;
    see `build_frontend_bundle`'s stage-pipeline docstring.
    """

    validated_bundle: LoadedWorkflowBundle
    source_map_payload: Mapping[str, object]
    workflow_boundary_projection_payload: Mapping[str, object]
    build_root: Path
    fingerprint: str


def _select_and_reattach(
    compile_result: LinkedStage3CompileResult,
    entry_selection: FrontendEntrySelection,
    *,
    resolved_request: FrontendBuildRequest,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundary_manifest: Mapping[str, object],
) -> _SelectAndReattachResult:
    """Reattach provenance and semantic IR to the selected compiled bundle.

    Stage 2 of `build_frontend_bundle` (see its docstring for the full
    pipeline): selects the validated bundle for the entry workflow, serializes
    the source map and workflow-boundary projection, validates the
    computes the content-addressed fingerprint and build root, and reattaches
    provenance, runtime-plan metadata, and semantic IR.
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
    )
    fingerprint = _fingerprint_build(
        request=resolved_request,
        compile_result=compile_result,
        imported_bindings=imported_bindings,
        entry_selection=entry_selection,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundary_manifest=command_boundary_manifest,
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
    validated_bundle = _reattach_bundle_provenance(
        bundle=selected_bundle,
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
    return _SelectAndReattachResult(
        validated_bundle=validated_bundle,
        source_map_payload=source_map_payload,
        workflow_boundary_projection_payload=workflow_boundary_projection_payload,
        build_root=build_root,
        fingerprint=fingerprint,
    )


def _emit(
    validated_bundle: LoadedWorkflowBundle,
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
    g8_deletion_evidence: Mapping[str, object] | None,
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
        g8_deletion_evidence=g8_deletion_evidence,
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
