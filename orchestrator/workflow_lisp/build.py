"""Frontend-owned build and artifact helpers for Workflow Lisp entrypoints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.surface_ast import WorkflowProvenance

from .compiler import LinkedStage3CompileResult, compile_stage3_entrypoint
from .debug_yaml import render_debug_yaml
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic, serialize_diagnostics
from .spans import SourcePosition, SourceSpan
from .workflows import CertifiedAdapterBinding, ExternalToolBinding


BUILD_SCHEMA_VERSION = "workflow_lisp_build.v1"


@dataclass(frozen=True)
class FrontendBuildRequest:
    source_path: Path
    source_roots: tuple[Path, ...] = ()
    entry_workflow: str | None = None
    provider_externs_path: Path | None = None
    prompt_externs_path: Path | None = None
    imported_workflow_bundles_path: Path | None = None
    command_boundaries_path: Path | None = None
    emit_debug_yaml: bool = False
    workspace_root: Path | None = None


@dataclass(frozen=True)
class FrontendEntrySelection:
    requested_name: str | None
    selected_name: str
    canonical_name: str
    exported_names: tuple[str, ...]


@dataclass(frozen=True)
class ImportedWorkflowBundleBinding:
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


@dataclass(frozen=True)
class FrontendSourceTrace:
    workflow_name: str
    step_ids: Mapping[str, dict[str, object]]
    generated_inputs: Mapping[str, dict[str, object]]
    generated_outputs: Mapping[str, dict[str, object]]
    generated_paths: Mapping[str, dict[str, object]]


@dataclass(frozen=True)
class FrontendBuildResult:
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


def build_frontend_bundle(request: FrontendBuildRequest) -> FrontendBuildResult:
    """Compile one `.orc` entrypoint and emit deterministic frontend artifacts."""

    resolved_request = _resolve_request(request)
    provider_externs = _load_string_mapping(
        resolved_request.provider_externs_path,
        label="provider externs manifest",
    )
    prompt_externs = _load_string_mapping(
        resolved_request.prompt_externs_path,
        label="prompt externs manifest",
    )
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
    )

    entry_selection = _select_entry_workflow(
        compile_result,
        requested_name=resolved_request.entry_workflow,
        source_path=resolved_request.source_path,
    )
    selected_bundle = compile_result.entry_result.validated_bundles[entry_selection.canonical_name]
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

    diagnostics: tuple[LispFrontendDiagnostic, ...] = ()
    source_map_path = build_root / "source_map.json"
    provenance = replace(
        selected_bundle.provenance,
        frontend_kind="workflow_lisp",
        frontend_build_root=build_root,
        frontend_source_trace_path=source_map_path,
        frontend_entry_workflow=entry_selection.selected_name,
    )
    validated_bundle = LoadedWorkflowBundle(
        surface=replace(selected_bundle.surface, provenance=provenance),
        ir=selected_bundle.ir,
        projection=selected_bundle.projection,
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
    source_roots = tuple(root.resolve() for root in request.source_roots) or (source_path.parent,)
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
    prompt_externs: Mapping[str, str],
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
        "prompt_externs": dict(sorted(prompt_externs.items())),
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
) -> Mapping[str, Path]:
    debug_yaml_path = build_root / "expanded.debug.yaml"
    artifact_paths = {
        "frontend_ast": build_root / "frontend_ast.json",
        "expanded_frontend_ast": build_root / "expanded_frontend_ast.json",
        "typed_frontend_ast": build_root / "typed_frontend_ast.json",
        "lowered_workflows": build_root / "lowered_workflows.json",
        "executable_ir": build_root / "executable_ir.json",
        "source_map": build_root / "source_map.json",
        "diagnostics": build_root / "diagnostics.json",
    }
    payloads = {
        "frontend_ast": _serialize_frontend_ast(compile_result),
        "expanded_frontend_ast": _serialize_expanded_frontend_ast(compile_result),
        "typed_frontend_ast": _serialize_typed_frontend_ast(compile_result),
        "lowered_workflows": _serialize_lowered_workflows(compile_result),
        "executable_ir": _json_data(validated_bundle.ir),
        "source_map": _serialize_source_map(
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
            "core_workflow_ast": "deferred_shared_contract",
            "semantic_ir": "deferred_shared_contract",
        },
        diagnostic_count=len(diagnostics),
        shared_validation_status="validated",
        debug_yaml_status="emitted" if emit_debug_yaml else "not_requested",
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
    workflows: dict[str, dict[str, object]] = {}
    for compiled_result in compile_result.compiled_results_by_name.values():
        for lowered in compiled_result.lowered_workflows:
            workflow_name = lowered.typed_workflow.definition.name
            display_name = _display_workflow_name(workflow_name)
            workflows[workflow_name] = {
                "display_name": display_name,
                "selected_entry_workflow": workflow_name == selected_name,
                "workflow_name": workflow_name,
                "workflow_origin": _origin_payload(lowered.origin_map.workflow_origin),
                "step_ids": {
                    step_id: _origin_payload(origin)
                    for step_id, origin in sorted(lowered.origin_map.step_spans.items())
                },
                "generated_inputs": {
                    name: _origin_payload(origin)
                    for name, origin in sorted(lowered.origin_map.generated_input_spans.items())
                },
                "generated_outputs": {
                    name: _origin_payload(origin)
                    for name, origin in sorted(lowered.origin_map.generated_output_spans.items())
                },
                "generated_paths": {
                    name: _origin_payload(origin)
                    for name, origin in sorted(lowered.origin_map.generated_path_spans.items())
                },
            }
    return {"workflows": workflows}


def _origin_payload(origin: object) -> dict[str, object]:
    span = getattr(origin, "span")
    return {
        "path": span.start.path,
        "line": span.start.line,
        "column": span.start.column,
        "form_path": list(getattr(origin, "form_path", ()) or ()),
        "notes": list(getattr(origin, "notes", ()) or ()),
    }


def _display_workflow_name(name: str) -> str:
    return name.split("::", 1)[-1]


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
