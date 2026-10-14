"""Frontend-owned build and artifact helpers for Workflow Lisp entrypoints."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING
from types import MappingProxyType

from orchestrator._common.safe_tree import resolve_path_preserving_fd

from .build_manifest_io import (
    ConfigurationReadRecord,
    ConfigurationReadTrace,
    _cli_request_diagnostic,
    _json_data,
    _load_command_boundaries_manifest_payload,
    _load_json_file,
    _load_prompt_extern_mapping,
    _load_string_mapping,
    _parse_command_boundaries_manifest,
    _require_build_path_within_workspace,
    _resolve_manifest_relative_path,
    _resolve_request,
)

from .command_boundaries import CertifiedAdapterBinding, ExternalToolBinding
from .compiler import (
    LinkedStage3CompileResult,
    Stage3ValidationProfile,
    WorkflowBoundaryAdmissionProfile,
    _normalize_workflow_boundary_admission_profile,
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from .compiler_session import CompilerSession
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .lints import LINT_PROFILE_DEFAULT
from .reader import SourceReadRecord, SourceReadTrace, read_sexpr_file
from .wcc.route import LoweringRoute, normalize_lowering_route


if TYPE_CHECKING:
    from .closed.frontend import TypedProgram


@dataclass(frozen=True)
class FrontendBuildRequest:
    """Operator-facing compile request for one `.orc` entrypoint.

    The request keeps source discovery, extern manifests, imported `.orc` bundle
    bindings, and optional debug emission together so the build fingerprint can
    reflect every input that affects the lowered workflow bundle.
    """

    source_path: Path
    source_roots: tuple[Path, ...] = ()
    entry_workflow: str | None = None
    boundary_admission_profile: WorkflowBoundaryAdmissionProfile | str | None = None
    provider_externs_path: Path | None = None
    prompt_externs_path: Path | None = None
    imported_workflow_bundles_path: Path | None = None
    command_boundaries_path: Path | None = None
    workspace_root: Path | None = None
    lint_profile: str = LINT_PROFILE_DEFAULT
    lowering_route: LoweringRoute | str | None = None


@dataclass(frozen=True, slots=True)
class FrontendCompileRequestCapture:
    """Exact production-normalized compile identity before entry selection."""

    source_path: Path
    workspace_root: Path
    source_roots: tuple[Path, ...]
    entry_workflow: str | None
    validation_profile: Stage3ValidationProfile
    boundary_admission_profile: WorkflowBoundaryAdmissionProfile
    lint_profile: str
    lowering_route: LoweringRoute
    provider_externs: Mapping[str, str]
    prompt_externs: Mapping[str, object]
    command_boundaries: Mapping[
        str,
        ExternalToolBinding | CertifiedAdapterBinding,
    ]
    imported_workflow_bundles: Mapping[str, "TypedProgram"]


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
    """One selected typed producer linked into Lisp as a callable boundary.

    Each binding is compiled from an explicit `.orc` source before linking.
    """

    canonical_key: str
    manifest_entry_path: str
    resolved_bundle_path: Path
    bundle_kind: str
    workflow_name: str | None
    load_status: str
    typed_program: "TypedProgram"


@dataclass(frozen=True)
class FrontendSourceReadTraceSnapshot:
    """Immutable source-read evidence captured at the build-core boundary."""

    records: tuple[SourceReadRecord, ...]
    revision_vector: tuple[tuple[Path, str], ...]
    raw_bytes_by_path: Mapping[Path, bytes]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "raw_bytes_by_path",
            MappingProxyType(dict(self.raw_bytes_by_path)),
        )


@dataclass(frozen=True)
class FrontendConfigurationTraceSnapshot:
    """Immutable JSON configuration-read evidence captured by one build."""

    records: tuple[ConfigurationReadRecord, ...]
    revision_vector: tuple[tuple[Path, str], ...]


@dataclass(frozen=True)
class FrontendInitializationConfiguration:
    """Production-loaded, immutable frontend context without an entry source."""

    workspace_root: Path
    source_roots: tuple[Path, ...]
    provider_externs_path: Path | None
    prompt_externs_path: Path | None
    command_boundaries_path: Path | None
    imported_workflow_bundles_path: Path | None
    lowering_route: LoweringRoute
    provider_externs: Mapping[str, str]
    prompt_externs: Mapping[str, object]
    command_boundary_manifest: Mapping[str, object]
    command_boundaries: Mapping[
        str,
        ExternalToolBinding | CertifiedAdapterBinding,
    ]
    imported_workflow_bundles: tuple[ImportedWorkflowBundleBinding, ...]
    source_read_trace: FrontendSourceReadTraceSnapshot
    configuration_trace: FrontendConfigurationTraceSnapshot


@dataclass(frozen=True)
class FrontendInMemoryBuildResult:
    """Read-only typed analysis with exact source and configuration evidence."""

    resolved_request: FrontendBuildRequest
    selected_workflow_name: str | None
    diagnostics: tuple[LispFrontendDiagnostic, ...]
    entry_selection: FrontendEntrySelection | None
    imported_workflow_bundles: tuple[ImportedWorkflowBundleBinding, ...]
    compile_result: LinkedStage3CompileResult
    source_read_trace: FrontendSourceReadTraceSnapshot
    configuration_trace: FrontendConfigurationTraceSnapshot
    compile_request_capture: FrontendCompileRequestCapture


def load_frontend_initialization_configuration(
    *,
    workspace_root: Path,
    source_roots: tuple[Path, ...] = (),
    provider_externs_path: Path | None = None,
    prompt_externs_path: Path | None = None,
    command_boundaries_path: Path | None = None,
    imported_workflow_bundles_path: Path | None = None,
    lowering_route: LoweringRoute | str | None = None,
) -> FrontendInitializationConfiguration:
    """Load one frontend context without requiring or compiling an entry source."""

    canonical_workspace_root = resolve_path_preserving_fd(workspace_root)
    canonical_source_roots = tuple(
        resolve_path_preserving_fd(root) for root in source_roots
    )
    canonical_provider_path = (
        resolve_path_preserving_fd(provider_externs_path)
        if provider_externs_path is not None else None
    )
    canonical_prompt_path = (
        resolve_path_preserving_fd(prompt_externs_path)
        if prompt_externs_path is not None else None
    )
    canonical_command_path = (
        resolve_path_preserving_fd(command_boundaries_path)
        if command_boundaries_path is not None else None
    )
    canonical_imported_path = (
        resolve_path_preserving_fd(imported_workflow_bundles_path)
        if imported_workflow_bundles_path is not None else None
    )
    normalized_lowering_route = normalize_lowering_route(lowering_route)
    source_read_trace = SourceReadTrace()
    configuration_read_trace = ConfigurationReadTrace()

    provider_externs = _load_string_mapping(
        canonical_provider_path,
        label="provider externs manifest",
        configuration_read_trace=configuration_read_trace,
    )
    prompt_externs = _load_prompt_extern_mapping(
        canonical_prompt_path,
        configuration_read_trace=configuration_read_trace,
    )
    command_boundary_manifest = _load_command_boundaries_manifest_payload(
        canonical_command_path,
        configuration_read_trace=configuration_read_trace,
    )
    command_boundaries = _parse_command_boundaries_manifest(
        command_boundary_manifest,
        manifest_path=canonical_command_path,
    )
    imported_workflow_bundles = _load_imported_workflow_bundle_manifest(
        canonical_imported_path,
        workspace_root=canonical_workspace_root,
        source_roots=canonical_source_roots,
        provider_externs_path=canonical_provider_path,
        prompt_externs_path=canonical_prompt_path,
        command_boundaries_path=canonical_command_path,
        lowering_route=normalized_lowering_route,
        source_read_trace=source_read_trace,
        configuration_read_trace=configuration_read_trace,
    )

    return FrontendInitializationConfiguration(
        workspace_root=canonical_workspace_root,
        source_roots=canonical_source_roots,
        provider_externs_path=canonical_provider_path,
        prompt_externs_path=canonical_prompt_path,
        command_boundaries_path=canonical_command_path,
        imported_workflow_bundles_path=canonical_imported_path,
        lowering_route=normalized_lowering_route,
        provider_externs=_freeze_configuration_mapping(provider_externs),
        prompt_externs=_freeze_configuration_mapping(prompt_externs),
        command_boundary_manifest=_freeze_configuration_mapping(
            command_boundary_manifest
        ),
        command_boundaries=_freeze_command_boundaries(command_boundaries),
        imported_workflow_bundles=imported_workflow_bundles,
        source_read_trace=FrontendSourceReadTraceSnapshot(
            records=source_read_trace.records,
            revision_vector=source_read_trace.revision_vector,
            raw_bytes_by_path=source_read_trace.raw_bytes_by_path,
        ),
        configuration_trace=FrontendConfigurationTraceSnapshot(
            records=configuration_read_trace.records,
            revision_vector=configuration_read_trace.revision_vector,
        ),
    )


def _freeze_configuration_mapping(
    value: Mapping[str, object],
) -> Mapping[str, object]:
    """Recursively freeze one already validated production configuration mapping."""

    return MappingProxyType(
        {
            key: _freeze_configuration_value(item)
            for key, item in value.items()
        }
    )


def _freeze_configuration_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_configuration_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_configuration_value(item) for item in value)
    return value


def _freeze_command_boundaries(
    value: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding],
) -> Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]:
    """Copy and freeze nested certified-adapter configuration payloads."""

    return MappingProxyType(
        {
            name: (
                replace(
                    binding,
                    input_contract=_freeze_configuration_mapping(
                        binding.input_contract
                    ),
                    path_safety=_freeze_configuration_mapping(
                        binding.path_safety
                    ),
                )
                if isinstance(binding, CertifiedAdapterBinding)
                else binding
            )
            for name, binding in value.items()
        }
    )


def _capture_frontend_compile_request(
    resolved_request: FrontendBuildRequest,
    *,
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundaries: Mapping[
        str,
        ExternalToolBinding | CertifiedAdapterBinding,
    ],
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
) -> tuple[
    FrontendCompileRequestCapture,
    tuple[ImportedWorkflowBundleBinding, ...],
]:
    """Copy and freeze the exact values that the production compiler consumes."""

    frozen_imported_bindings = imported_bindings
    return (
        FrontendCompileRequestCapture(
            source_path=resolved_request.source_path,
            workspace_root=resolved_request.workspace_root,
            source_roots=resolved_request.source_roots,
            entry_workflow=resolved_request.entry_workflow,
            validation_profile=Stage3ValidationProfile.SHARED_CALLABLE,
            boundary_admission_profile=(
                _normalize_workflow_boundary_admission_profile(
                    resolved_request.boundary_admission_profile
                )
            ),
            lint_profile=resolved_request.lint_profile,
            lowering_route=normalize_lowering_route(
                resolved_request.lowering_route
            ),
            provider_externs=_freeze_configuration_mapping(provider_externs),
            prompt_externs=_freeze_configuration_mapping(prompt_externs),
            command_boundaries=_freeze_command_boundaries(command_boundaries),
            imported_workflow_bundles=MappingProxyType(
                {
                    binding.canonical_key: binding.typed_program
                    for binding in frozen_imported_bindings
                }
            ),
        ),
        frozen_imported_bindings,
    )


def _attach_compile_request_capture(
    error: LispFrontendCompileError,
    capture: FrontendCompileRequestCapture,
) -> None:
    """Bind a post-capture language error to the exact attempted request."""

    existing = getattr(error, "compile_request_capture", None)
    if existing is not None and existing != capture:
        raise RuntimeError(
            "frontend compile error carries a different request capture"
        )
    error.compile_request_capture = capture


def build_frontend_bundle_in_memory(
    request: FrontendBuildRequest,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> FrontendInMemoryBuildResult:
    """Analyze one source graph with exact configuration and source evidence."""

    configuration_read_trace = ConfigurationReadTrace()
    try:
        return _build_frontend_bundle_in_memory(
            request,
            source_read_trace=source_read_trace,
            configuration_read_trace=configuration_read_trace,
        )
    except Exception as error:
        _attach_build_configuration_evidence(
            error,
            configuration_read_trace.revision_vector,
            configuration_read_trace.revision_conflict_paths,
        )
        raise


def _attach_build_configuration_evidence(
    error: Exception,
    revision_vector: tuple[tuple[Path, str], ...],
    revision_conflict_paths: tuple[Path, ...],
) -> None:
    """Bind one build attempt's structural configuration evidence to its error."""

    existing = getattr(error, "configuration_revision_vector", None)
    retained_vector = revision_vector
    existing_is_normalized = _configuration_revision_vector_is_normalized(
        existing
    )
    if existing_is_normalized:
        existing_by_path = dict(existing)
        observed_is_covered = all(
            existing_by_path.get(path) == revision
            for path, revision in revision_vector
        )
        if len(existing) >= len(revision_vector) and observed_is_covered:
            retained_vector = existing

    existing_conflicts = getattr(
        error,
        "configuration_revision_conflict_paths",
        None,
    )
    retained_conflicts = revision_conflict_paths
    if (
        retained_vector is existing
        and _configuration_conflict_paths_are_valid(
            existing_conflicts,
            revision_vector=retained_vector,
        )
    ):
        retained_conflicts = tuple(
            (
                *existing_conflicts,
                *(
                    path
                    for path in revision_conflict_paths
                    if path not in existing_conflicts
                ),
            )
        )

    error.configuration_revision_vector = retained_vector
    error.configuration_revision_conflict_paths = retained_conflicts


def _configuration_revision_vector_is_normalized(value: object) -> bool:
    if not isinstance(value, tuple):
        return False
    if any(
        not isinstance(item, tuple)
        or len(item) != 2
        or not isinstance(item[0], Path)
        or not isinstance(item[1], str)
        for item in value
    ):
        return False
    return (
        len(dict(value)) == len(value)
        and value == tuple(sorted(value, key=lambda item: item[0].as_posix()))
    )


def _configuration_conflict_paths_are_valid(
    value: object,
    *,
    revision_vector: tuple[tuple[Path, str], ...],
) -> bool:
    if (
        not isinstance(value, tuple)
        or any(not isinstance(path, Path) for path in value)
        or len(set(value)) != len(value)
    ):
        return False
    revision_paths = {path for path, _revision in revision_vector}
    return all(path in revision_paths for path in value)


def _build_frontend_bundle_in_memory(
    request: FrontendBuildRequest,
    *,
    source_read_trace: SourceReadTrace | None,
    configuration_read_trace: ConfigurationReadTrace,
) -> FrontendInMemoryBuildResult:
    """Internal build core sharing configuration evidence through recursion."""

    resolved_request = _resolve_request(request)
    active_source_read_trace = (
        source_read_trace if source_read_trace is not None else SourceReadTrace()
    )
    provider_externs = _load_string_mapping(
        resolved_request.provider_externs_path,
        label="provider externs manifest",
        configuration_read_trace=configuration_read_trace,
    )
    prompt_externs = _load_prompt_extern_mapping(
        resolved_request.prompt_externs_path,
        configuration_read_trace=configuration_read_trace,
    )
    command_boundary_manifest = _load_command_boundaries_manifest_payload(
        resolved_request.command_boundaries_path,
        configuration_read_trace=configuration_read_trace,
    )
    command_boundaries = _parse_command_boundaries_manifest(
        command_boundary_manifest,
        manifest_path=resolved_request.command_boundaries_path,
    )
    imported_bindings = _load_imported_workflow_bundle_manifest(
        resolved_request.imported_workflow_bundles_path,
        workspace_root=resolved_request.workspace_root,
        source_roots=resolved_request.source_roots,
        provider_externs_path=resolved_request.provider_externs_path,
        prompt_externs_path=resolved_request.prompt_externs_path,
        command_boundaries_path=resolved_request.command_boundaries_path,
        lowering_route=resolved_request.lowering_route,
        source_read_trace=active_source_read_trace,
        configuration_read_trace=configuration_read_trace,
    )
    compile_request_capture, imported_bindings = (
        _capture_frontend_compile_request(
            resolved_request,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            command_boundaries=command_boundaries,
            imported_bindings=imported_bindings,
        )
    )
    try:
        compile_result, entry_selection = _compile_entry(
            compile_request_capture,
            source_read_trace=active_source_read_trace,
        )
    except LispFrontendCompileError as error:
        _attach_compile_request_capture(error, compile_request_capture)
        raise
    source_read_snapshot = FrontendSourceReadTraceSnapshot(
        records=active_source_read_trace.records,
        revision_vector=active_source_read_trace.revision_vector,
        raw_bytes_by_path=active_source_read_trace.raw_bytes_by_path,
    )
    configuration_snapshot = FrontendConfigurationTraceSnapshot(
        records=configuration_read_trace.records,
        revision_vector=configuration_read_trace.revision_vector,
    )
    return FrontendInMemoryBuildResult(
        resolved_request=resolved_request,
        selected_workflow_name=(entry_selection.selected_name if entry_selection else None),
        diagnostics=compile_result.diagnostics,
        entry_selection=entry_selection,
        imported_workflow_bundles=imported_bindings,
        compile_result=compile_result,
        source_read_trace=source_read_snapshot,
        configuration_trace=configuration_snapshot,
        compile_request_capture=compile_request_capture,
    )


def _compile_entry(
    compile_request_capture: FrontendCompileRequestCapture,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> tuple[LinkedStage3CompileResult, FrontendEntrySelection | None]:
    """Compile the entry module graph and select the requested export.

    Uses the typed compiler and selects one exported workflow when present.
    """

    active_source_read_trace = (
        source_read_trace if source_read_trace is not None else SourceReadTrace()
    )
    compiler_session = CompilerSession()
    compile_result = compile_stage3_entrypoint(
        compile_request_capture.source_path,
        source_roots=compile_request_capture.source_roots,
        entry_workflow=compile_request_capture.entry_workflow,
        provider_externs=compile_request_capture.provider_externs,
        prompt_externs=compile_request_capture.prompt_externs,
        imported_programs=compile_request_capture.imported_workflow_bundles,
        command_boundaries=compile_request_capture.command_boundaries,
        validation_profile=compile_request_capture.validation_profile,
        boundary_admission_profile=(
            compile_request_capture.boundary_admission_profile
        ),
        workspace_root=compile_request_capture.workspace_root,
        lint_profile=compile_request_capture.lint_profile,
        lowering_route=compile_request_capture.lowering_route,
        source_read_trace=active_source_read_trace,
        compiler_session=compiler_session,
    )

    export_surface = compile_result.graph.export_surfaces_by_name[
        compile_result.graph.entry_module_name
    ]
    entry_selection = (
        None
        if compile_request_capture.entry_workflow is None
        and not export_surface.workflows_by_name
        else _select_entry_workflow(
            compile_result,
            requested_name=compile_request_capture.entry_workflow,
            source_path=compile_request_capture.source_path,
        )
    )
    return compile_result, entry_selection


def load_imported_workflow_bundle_manifest(
    manifest_path: Path | None,
    *,
    workspace_root: Path,
    source_roots: tuple[Path, ...] = (),
    provider_externs_path: Path | None = None,
    prompt_externs_path: Path | None = None,
    command_boundaries_path: Path | None = None,
    lowering_route: LoweringRoute | str | None = None,
    source_read_trace: SourceReadTrace | None = None,
) -> tuple[ImportedWorkflowBundleBinding, ...]:
    """Load imported workflow bundles from one explicit manifest file."""

    return _load_imported_workflow_bundle_manifest(
        manifest_path,
        workspace_root=workspace_root,
        source_roots=source_roots,
        provider_externs_path=provider_externs_path,
        prompt_externs_path=prompt_externs_path,
        command_boundaries_path=command_boundaries_path,
        lowering_route=lowering_route,
        source_read_trace=source_read_trace,
        configuration_read_trace=ConfigurationReadTrace(),
    )


def _iter_compiled_import_entries(
    payload: object,
    *,
    manifest_path: Path,
):
    """Validate shared manifest entry fields and yield binding/source/selection."""

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
        if raw_entry.get("kind") != "compiled":
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="imported_workflow_bundle_kind_invalid",
                        message=(
                            f"manifest entry for `{canonical_key}` must explicitly "
                            "declare `kind` as `compiled`"
                        ),
                        path=manifest_path,
                    ),
                )
            )
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
        resolved_source_path = _resolve_manifest_relative_path(
            manifest_path, raw_path
        )
        if resolved_source_path.suffix.lower() != ".orc":
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="imported_workflow_bundle_path_invalid",
                        message=(
                            f"compiled imported workflow bundle `{canonical_key}` "
                            "must reference a `.orc` source"
                        ),
                        path=manifest_path,
                    ),
                )
            )
        requested_entry = (
            raw_entry.get("entry_workflow")
            if isinstance(raw_entry.get("entry_workflow"), str)
            else None
        )
        yield canonical_key, resolved_source_path, requested_entry


def _load_imported_workflow_bundle_manifest(
    manifest_path: Path | None,
    *,
    workspace_root: Path,
    source_roots: tuple[Path, ...] = (),
    provider_externs_path: Path | None = None,
    prompt_externs_path: Path | None = None,
    command_boundaries_path: Path | None = None,
    lowering_route: LoweringRoute | str | None = None,
    source_read_trace: SourceReadTrace | None,
    configuration_read_trace: ConfigurationReadTrace,
) -> tuple[ImportedWorkflowBundleBinding, ...]:
    """Load selected typed producers while sharing configuration evidence."""

    if manifest_path is None:
        return ()
    payload = _load_json_file(
        manifest_path,
        label="imported workflow bundle manifest",
        configuration_read_trace=configuration_read_trace,
    )
    bindings: list[ImportedWorkflowBundleBinding] = []
    for canonical_key, resolved_bundle_path, requested_entry in _iter_compiled_import_entries(
        payload, manifest_path=manifest_path
    ):
        raw_entry = payload[canonical_key]
        raw_path = raw_entry["path"]
        bundle_kind = raw_entry["kind"]
        from .closed.frontend import _select_and_finalize_typed_program

        provider_externs = _load_string_mapping(
            provider_externs_path, label="provider externs manifest",
            configuration_read_trace=configuration_read_trace,
        )
        prompt_externs = _load_prompt_extern_mapping(
            prompt_externs_path, configuration_read_trace=configuration_read_trace,
        )
        command_manifest = _load_command_boundaries_manifest_payload(
            command_boundaries_path, configuration_read_trace=configuration_read_trace,
        )
        boundaries = _parse_command_boundaries_manifest(
            command_manifest, manifest_path=command_boundaries_path,
        )
        from .syntax import build_syntax_module

        trace = source_read_trace if source_read_trace is not None else SourceReadTrace()
        source_syntax = build_syntax_module(read_sexpr_file(
            resolved_bundle_path, source_read_trace=trace,
        ))
        compile_kwargs = dict(
            entry_workflow=requested_entry,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            command_boundaries=boundaries,
            workspace_root=workspace_root,
            lowering_route=lowering_route,
            validate_shared=True,
            source_read_trace=trace,
        )
        if source_syntax.module_name is not None:
            linked = compile_stage3_entrypoint(
                resolved_bundle_path, source_roots=source_roots, **compile_kwargs,
            )
            program = _select_and_finalize_typed_program(
                linked.entry_result, entry_path=resolved_bundle_path,
                entry_workflow=requested_entry,
                export_surface=linked.graph.export_surfaces_by_name[linked.graph.entry_module_name],
                diagnostics=linked.diagnostics,
            )
        else:
            result = compile_stage3_module(resolved_bundle_path, **compile_kwargs)
            program = _select_and_finalize_typed_program(
                result, entry_path=resolved_bundle_path, entry_workflow=requested_entry,
            )
        bindings.append(ImportedWorkflowBundleBinding(
            canonical_key=canonical_key,
            manifest_entry_path=raw_path,
            resolved_bundle_path=resolved_bundle_path,
            bundle_kind=bundle_kind,
            workflow_name=program.entry.definition.name,
            load_status="compiled",
            typed_program=program,
        ))
    return tuple(bindings)


def _select_entry_workflow(
    compile_result: LinkedStage3CompileResult,
    *,
    requested_name: str | None,
    source_path: Path,
) -> FrontendEntrySelection:
    export_surface = compile_result.graph.export_surfaces_by_name[compile_result.graph.entry_module_name]
    entry_module = compile_result.graph.modules_by_name[
        compile_result.graph.entry_module_name
    ]
    return _select_entry_workflow_from_surface(
        export_surface,
        requested_name=requested_name,
        available_names={workflow.definition.name for workflow in compile_result.entry_result.typed_workflows},
        source_path=source_path,
        entry_span=entry_module.syntax_module.span,
    )


def _select_entry_workflow_from_surface(
    export_surface,
    *,
    requested_name: str | None,
    available_names,
    source_path: Path,
    entry_span,
) -> FrontendEntrySelection:
    """Select one export while retaining the caller's owner-specific names."""

    exported_workflows = tuple(sorted(export_surface.workflows_by_name))
    if requested_name:
        binding = export_surface.workflows_by_name.get(requested_name)
        canonical_name = binding.canonical_name if binding is not None else requested_name
        if canonical_name not in available_names:
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
                    span=entry_span,
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
