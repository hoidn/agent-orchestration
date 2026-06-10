"""Frontend-owned build and artifact helpers for Workflow Lisp entrypoints."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.core_ast import build_core_workflow_ast, workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_boundary_projection
from orchestrator.workflow.runtime_plan import enrich_workflow_runtime_plan
from orchestrator.workflow.semantic_ir import derive_workflow_semantic_ir, workflow_semantic_ir_to_json
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole
from orchestrator.workflow.surface_ast import WorkflowProvenance

from .command_boundaries import (
    CertifiedAdapterBinding,
    CertifiedAdapterInputField,
    ExternalToolBinding,
    PROMOTED_CALL_REQUIRED_METADATA_FIELDS,
)
from .compiler import LinkedStage3CompileResult, compile_stage3_entrypoint
from .debug_yaml import render_debug_yaml
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic, serialize_diagnostics
from .lints import LINT_PROFILE_DEFAULT
from .source_map import SOURCE_MAP_COVERAGE, SOURCE_MAP_SCHEMA_VERSION, build_source_map_document
from .spans import SourcePosition, SourceSpan
from .workflows import (
    normalize_public_prompt_extern_binding,
    prompt_extern_source_bindings_payload,
    prompt_extern_source_payload,
)


BUILD_SCHEMA_VERSION = "workflow_lisp_build.v1"
FRONTEND_ARTIFACT_EXPORT_FILENAMES = {
    "executable_ir": "executable_ir.json",
    "core_workflow_ast": "core_workflow_ast.json",
    "runtime_plan": "runtime_plan.json",
    "semantic_ir": "semantic_ir.json",
    "source_map": "source_map.json",
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
    )
    imported_workflow_bundles = {
        binding.canonical_key: binding.bundle
        for binding in imported_bindings
    }

    compile_result = compile_stage3_entrypoint(
        resolved_request.source_path,
        source_roots=resolved_request.source_roots,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles=imported_workflow_bundles,
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=resolved_request.workspace_root,
        lint_profile=resolved_request.lint_profile,
    )

    entry_selection = _select_entry_workflow(
        compile_result,
        requested_name=resolved_request.entry_workflow,
        source_path=resolved_request.source_path,
    )
    selected_bundle = compile_result.entry_result.validated_bundles[entry_selection.canonical_name]
    source_map_payload = _serialize_source_map(
        compile_result,
        selected_name=entry_selection.canonical_name,
    )
    runtime_plan = enrich_workflow_runtime_plan(
        selected_bundle.runtime_plan,
        command_boundary_metadata=_command_boundary_metadata_for_workflow(
            source_map_payload,
            workflow_name=entry_selection.canonical_name,
        ),
        has_compiled_frontend_lineage=True,
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
    validated_surface = replace(selected_bundle.surface, provenance=provenance)
    source_map_path.write_text(
        json.dumps(_json_data(source_map_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    core_workflow_ast = build_core_workflow_ast(validated_surface, selected_bundle.imports, provenance)
    validated_bundle = LoadedWorkflowBundle(
        surface=validated_surface,
        core_workflow_ast=core_workflow_ast,
        semantic_ir=derive_workflow_semantic_ir(
            core_workflow_ast=core_workflow_ast,
            surface=validated_surface,
            ir=selected_bundle.ir,
            projection=selected_bundle.projection,
            runtime_plan=runtime_plan,
            imports=selected_bundle.imports,
            provenance=provenance,
        ),
        ir=selected_bundle.ir,
        projection=selected_bundle.projection,
        runtime_plan=runtime_plan,
        imports=selected_bundle.imports,
        provenance=provenance,
    )
    artifact_paths = _write_build_artifacts(
        build_root=build_root,
        compile_result=compile_result,
        validated_bundle=validated_bundle,
        entry_selection=entry_selection,
        diagnostics=diagnostics,
        emit_debug_yaml=resolved_request.emit_debug_yaml,
        source_map_payload=source_map_payload,
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
            bindings[name] = ExternalToolBinding(name=name, stable_command=stable_command)
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
                declared_promoted_fields=declared_promoted_fields,
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


def _fingerprint_build(
    *,
    request: FrontendBuildRequest,
    compile_result: LinkedStage3CompileResult,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    entry_selection: FrontendEntrySelection,
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundary_manifest: Mapping[str, object],
) -> str:
    source_payload = {
        "schema_version": BUILD_SCHEMA_VERSION,
        "source_files": {
            module_name: _sha256_path(module_source.path)
            for module_name, module_source in sorted(compile_result.graph.modules_by_name.items())
        },
        "source_roots": [str(path) for path in request.source_roots],
        "entry_workflow": entry_selection.canonical_name,
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
    source_map_payload: Mapping[str, object],
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
        "workflow_boundary_projection": build_root / "workflow_boundary_projection.json",
        "diagnostics": build_root / "diagnostics.json",
    }
    payloads = {
        "frontend_ast": _serialize_frontend_ast(compile_result),
        "expanded_frontend_ast": _serialize_expanded_frontend_ast(compile_result),
        "typed_frontend_ast": _serialize_typed_frontend_ast(compile_result),
        "lowered_workflows": _serialize_lowered_workflows(compile_result),
        "executable_ir": workflow_executable_ir_to_json(validated_bundle.ir),
        "core_workflow_ast": workflow_core_ast_to_json(validated_bundle.core_workflow_ast),
        "semantic_ir": workflow_semantic_ir_to_json(validated_bundle.semantic_ir),
        "runtime_plan": _json_data(validated_bundle.runtime_plan),
        "source_map": _json_data(source_map_payload),
        "workflow_boundary_projection": _serialize_workflow_boundary_projection(
            compile_result,
            selected_name=entry_selection.canonical_name,
        ),
        "diagnostics": serialize_diagnostics(diagnostics),
    }
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
    )


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


def _serialize_lowered_workflows(compile_result: LinkedStage3CompileResult) -> dict[str, object]:
    return {
        "modules": {
            module_name: {
                "workflows": [
                    {
                        "workflow_name": lowered.typed_workflow.definition.name,
                        "display_name": _display_workflow_name(lowered.typed_workflow.definition.name),
                        "authored_mapping": _json_data(lowered.authored_mapping),
                        "step_ids": sorted(lowered.origin_map.step_spans),
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
