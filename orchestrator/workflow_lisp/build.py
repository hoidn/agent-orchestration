"""Frontend-owned build and artifact helpers for Workflow Lisp entrypoints."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

from orchestrator.workflow.core_ast import (
    _load_command_boundary_metadata,
    build_core_workflow_ast,
    workflow_core_ast_to_json,
)
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.run_ref.bundle_transport import (
    EncodedBundleCapsule,
    write_bundle_capsule_directory,
)
from orchestrator.workflow.run_ref.capsule_build import assemble_bundle_capsule
from orchestrator.workflow.persisted_surface import (
    PERSISTED_WORKFLOW_SURFACE_FILENAME,
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    persisted_surface_sha256,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.runtime_plan import (
    derive_workflow_runtime_plan,
    enrich_workflow_runtime_plan,
)
from orchestrator.workflow.semantic_ir import derive_workflow_semantic_ir, workflow_semantic_ir_to_json
from orchestrator.workflow.surface_ast import WorkflowProvenance

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
    _resolve_manifest_relative_path,
    _resolve_request,
)
from .build_artifacts import (
    _build_manifest,
    _checkpoint_program_identity,
    _collect_origin_keys,
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
from .compiler import (
    LinkedStage3CompileResult,
    Stage3ValidationProfile,
    compile_stage3_entrypoint,
)
from .compiler_session import CompilerSession
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .lints import LINT_PROFILE_DEFAULT
from .reader import SourceReadRecord, SourceReadTrace
from .source_map import SOURCE_MAP_COVERAGE, SOURCE_MAP_SCHEMA_VERSION
from .wcc.route import LoweringRoute, normalize_lowering_route


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

BUILD_SCHEMA_VERSION = "workflow_lisp_build.v2"
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

    The request keeps source discovery, extern manifests, imported `.orc` bundle
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


@dataclass(frozen=True, slots=True)
class FrontendCompileRequestCapture:
    """Exact production-normalized compile identity before entry selection."""

    source_path: Path
    workspace_root: Path
    source_roots: tuple[Path, ...]
    entry_workflow: str | None
    validation_profile: Stage3ValidationProfile
    lint_profile: str
    lowering_route: LoweringRoute
    provider_externs: Mapping[str, str]
    prompt_externs: Mapping[str, object]
    command_boundaries: Mapping[
        str,
        ExternalToolBinding | CertifiedAdapterBinding,
    ]
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle]


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

    Each binding is compiled from an explicit `.orc` source before linking.
    """

    canonical_key: str
    manifest_entry_path: str
    resolved_bundle_path: Path
    bundle_kind: str
    workflow_name: str | None
    bundle_fingerprint: str | None
    load_status: str
    bundle: LoadedWorkflowBundle
    bundle_catalog: Mapping[str, LoadedWorkflowBundle]


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
    persisted_workflow_surface: Mapping[str, str]
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
    run_ref_bundle_capsule: EncodedBundleCapsule | None
    diagnostics: tuple[LispFrontendDiagnostic, ...]
    artifact_paths: Mapping[str, Path]
    manifest: FrontendBuildManifest
    entry_selection: FrontendEntrySelection
    imported_workflow_bundles: tuple[ImportedWorkflowBundleBinding, ...]
    compile_result: LinkedStage3CompileResult
    compile_request_capture: FrontendCompileRequestCapture
    resolved_request: FrontendBuildRequest
    source_read_trace: FrontendSourceReadTraceSnapshot
    configuration_trace: FrontendConfigurationTraceSnapshot


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
    """Read-only value prefix shared by persistent builds and LSP consumers."""

    build_root: Path | None
    manifest_path: Path | None
    resolved_request: FrontendBuildRequest
    selected_workflow_name: str | None
    validated_bundle: LoadedWorkflowBundle | None
    run_ref_bundle_capsule: EncodedBundleCapsule | None
    diagnostics: tuple[LispFrontendDiagnostic, ...]
    entry_selection: FrontendEntrySelection | None
    imported_workflow_bundles: tuple[ImportedWorkflowBundleBinding, ...]
    compile_result: LinkedStage3CompileResult
    fingerprint: str | None
    source_map_payload: Mapping[str, object] | None
    workflow_boundary_projection_payload: Mapping[str, object] | None
    persisted_surface_payload: Mapping[str, object] | None
    semantic_ir_payload: Mapping[str, object] | None
    core_workflow_ast_payload: Mapping[str, object] | None
    executable_ir_payload: Mapping[str, object] | None
    runtime_plan_payload: Mapping[str, object] | None
    source_read_trace: FrontendSourceReadTraceSnapshot
    configuration_trace: FrontendConfigurationTraceSnapshot
    compile_request_capture: FrontendCompileRequestCapture


@dataclass(frozen=True)
class FrontendArtifactExportRequest:
    """One caller-requested convenience export of a canonical build artifact."""

    artifact_name: str
    destination: Path


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

    canonical_workspace_root = workspace_root.resolve()
    canonical_source_roots = tuple(root.resolve() for root in source_roots)
    canonical_provider_path = (
        provider_externs_path.resolve() if provider_externs_path is not None else None
    )
    canonical_prompt_path = (
        prompt_externs_path.resolve() if prompt_externs_path is not None else None
    )
    canonical_command_path = (
        command_boundaries_path.resolve()
        if command_boundaries_path is not None
        else None
    )
    canonical_imported_path = (
        imported_workflow_bundles_path.resolve()
        if imported_workflow_bundles_path is not None
        else None
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
        imported_workflow_bundles=tuple(
            _freeze_imported_workflow_binding(binding)
            for binding in imported_workflow_bundles
        ),
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


def _freeze_imported_workflow_bundle(
    bundle: LoadedWorkflowBundle,
    *,
    imports: Mapping[str, LoadedWorkflowBundle],
) -> LoadedWorkflowBundle:
    """Freeze one catalog bundle and its reproduced provenance payload."""

    coverage = bundle.provenance.frontend_source_map_coverage
    provenance = (
        bundle.provenance
        if coverage is None
        else replace(
            bundle.provenance,
            frontend_source_map_coverage=_freeze_configuration_mapping(coverage),
        )
    )
    surface = (
        replace(bundle.surface, provenance=provenance)
        if bundle.surface.provenance is bundle.provenance
        else bundle.surface
    )
    core_workflow_ast = bundle.core_workflow_ast
    retained_surface = core_workflow_ast._surface_workflow
    if (
        retained_surface is not None
        and retained_surface.provenance is bundle.provenance
    ):
        core_workflow_ast = replace(
            core_workflow_ast,
            _surface_workflow=replace(
                retained_surface,
                provenance=provenance,
            ),
        )
    if core_workflow_ast.provenance is bundle.provenance:
        core_workflow_ast = replace(
            core_workflow_ast,
            provenance=provenance,
        )
    executable_ir = (
        replace(bundle.ir, provenance=provenance)
        if bundle.ir.provenance is bundle.provenance
        else bundle.ir
    )
    return replace(
        bundle,
        surface=surface,
        core_workflow_ast=core_workflow_ast,
        ir=executable_ir,
        imports=imports,
        provenance=provenance,
    )


def _freeze_imported_bundle_catalog(
    bundle_catalog: Mapping[str, LoadedWorkflowBundle],
) -> Mapping[str, LoadedWorkflowBundle]:
    """Rebuild one canonical catalog with shared immutable import identities."""

    source_catalog = dict(bundle_catalog)
    import_storage_by_name: dict[str, dict[str, LoadedWorkflowBundle]] = {
        canonical_name: {} for canonical_name in source_catalog
    }
    frozen_by_name: dict[str, LoadedWorkflowBundle] = {}

    for canonical_name in sorted(source_catalog):
        frozen_by_name[canonical_name] = _freeze_imported_workflow_bundle(
            source_catalog[canonical_name],
            imports=MappingProxyType(import_storage_by_name[canonical_name]),
        )
    for canonical_name in sorted(source_catalog):
        import_storage = import_storage_by_name[canonical_name]
        for alias, imported_bundle in source_catalog[canonical_name].imports.items():
            imported_name = imported_bundle.surface.name
            import_storage[alias] = frozen_by_name.get(
                imported_name,
                imported_bundle,
            )
    return MappingProxyType(
        {
            canonical_name: frozen_by_name[canonical_name]
            for canonical_name in sorted(frozen_by_name)
        }
    )


def _freeze_imported_workflow_binding(
    binding: ImportedWorkflowBundleBinding,
) -> ImportedWorkflowBundleBinding:
    """Freeze a retained bundle catalog while preserving canonical identity."""

    bundle_catalog = _freeze_imported_bundle_catalog(binding.bundle_catalog)
    workflow_name = binding.workflow_name
    if workflow_name is None or workflow_name not in bundle_catalog:
        raise RuntimeError(
            "compiled imported workflow is missing from its bundle catalog"
        )
    return replace(
        binding,
        bundle=bundle_catalog[workflow_name],
        bundle_catalog=bundle_catalog,
    )


def _flatten_compiled_bundle_catalog(
    compile_result: LinkedStage3CompileResult,
) -> Mapping[str, LoadedWorkflowBundle]:
    """Flatten every module's validated workflows by canonical name."""

    bundle_catalog: dict[str, LoadedWorkflowBundle] = {}
    compiled_results_by_name = dict(compile_result.compiled_results_by_name)
    graph = getattr(compile_result, "graph", None)
    entry_module_name = getattr(graph, "entry_module_name", None)
    entry_result = getattr(compile_result, "entry_result", None)
    # The shared-validation pass replaces `entry_result` after the linked
    # module map is built, so flatten the current entry object rather than its
    # pre-pass value retained in that map.
    if entry_module_name in compiled_results_by_name and entry_result is not None:
        compiled_results_by_name[entry_module_name] = entry_result
    for compiled_result in compiled_results_by_name.values():
        for canonical_name, bundle in compiled_result.validated_bundles.items():
            if canonical_name in bundle_catalog:
                raise RuntimeError(
                    "imported workflow bundle catalog canonical-name conflict for "
                    f"`{canonical_name}`"
                )
            bundle_catalog[canonical_name] = bundle
    return MappingProxyType(
        {
            canonical_name: bundle_catalog[canonical_name]
            for canonical_name in sorted(bundle_catalog)
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

    frozen_imported_bindings = tuple(
        _freeze_imported_workflow_binding(binding)
        for binding in imported_bindings
    )
    return (
        FrontendCompileRequestCapture(
            source_path=resolved_request.source_path,
            workspace_root=resolved_request.workspace_root,
            source_roots=resolved_request.source_roots,
            entry_workflow=resolved_request.entry_workflow,
            validation_profile=Stage3ValidationProfile.SHARED_CALLABLE,
            lint_profile=resolved_request.lint_profile,
            lowering_route=normalize_lowering_route(
                resolved_request.lowering_route
            ),
            provider_externs=_freeze_configuration_mapping(provider_externs),
            prompt_externs=_freeze_configuration_mapping(prompt_externs),
            command_boundaries=_freeze_command_boundaries(command_boundaries),
            imported_workflow_bundles=MappingProxyType(
                {
                    binding.canonical_key: binding.bundle
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

    in_memory = build_frontend_bundle_in_memory(request)
    try:
        (
            validated_bundle,
            build_root,
            entry_selection,
            fingerprint,
            semantic_ir_payload,
            executable_ir_payload,
            source_map_payload,
            workflow_boundary_projection_payload,
            persisted_surface_payload,
        ) = _require_runnable_in_memory_build(in_memory)
        return _emit(
            validated_bundle,
            build_root=build_root,
            compile_result=in_memory.compile_result,
            entry_selection=entry_selection,
            resolved_request=in_memory.resolved_request,
            imported_bindings=in_memory.imported_workflow_bundles,
            fingerprint=fingerprint,
            semantic_ir_payload=semantic_ir_payload,
            executable_ir_payload=executable_ir_payload,
            source_map_payload=source_map_payload,
            workflow_boundary_projection_payload=workflow_boundary_projection_payload,
            persisted_surface_payload=persisted_surface_payload,
            compile_request_capture=in_memory.compile_request_capture,
            source_read_trace=in_memory.source_read_trace,
            configuration_trace=in_memory.configuration_trace,
            run_ref_bundle_capsule=in_memory.run_ref_bundle_capsule,
        )
    except LispFrontendCompileError as error:
        _attach_compile_request_capture(
            error,
            in_memory.compile_request_capture,
        )
        raise


def build_frontend_bundle_in_memory(
    request: FrontendBuildRequest,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> FrontendInMemoryBuildResult:
    """Compile, select, and reattach one entry workflow without emitting files."""

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
    if entry_selection is None:
        return FrontendInMemoryBuildResult(
            build_root=None,
            manifest_path=None,
            resolved_request=resolved_request,
            selected_workflow_name=None,
            validated_bundle=None,
            run_ref_bundle_capsule=None,
            diagnostics=compile_result.diagnostics,
            entry_selection=None,
            imported_workflow_bundles=imported_bindings,
            compile_result=compile_result,
            fingerprint=None,
            source_map_payload=None,
            workflow_boundary_projection_payload=None,
            persisted_surface_payload=None,
            semantic_ir_payload=None,
            core_workflow_ast_payload=None,
            executable_ir_payload=None,
            runtime_plan_payload=None,
            source_read_trace=source_read_snapshot,
            configuration_trace=configuration_snapshot,
            compile_request_capture=compile_request_capture,
        )
    try:
        reattached = _select_and_reattach(
            compile_result,
            entry_selection,
            resolved_request=resolved_request,
            imported_bindings=imported_bindings,
            provider_externs=compile_request_capture.provider_externs,
            prompt_externs=compile_request_capture.prompt_externs,
            command_boundary_manifest=command_boundary_manifest,
            source_read_trace=source_read_snapshot,
        )
    except LispFrontendCompileError as error:
        _attach_compile_request_capture(error, compile_request_capture)
        raise
    semantic_ir_payload = workflow_semantic_ir_to_json(reattached.validated_bundle.semantic_ir)
    core_workflow_ast_payload = workflow_core_ast_to_json(
        reattached.validated_bundle.core_workflow_ast
    )
    executable_ir_payload = workflow_executable_ir_to_json(reattached.validated_bundle.ir)
    runtime_plan_payload = _public_runtime_plan_payload(
        reattached.validated_bundle.runtime_plan
    )

    return FrontendInMemoryBuildResult(
        build_root=reattached.build_root,
        manifest_path=reattached.build_root / "manifest.json",
        resolved_request=resolved_request,
        selected_workflow_name=entry_selection.selected_name,
        validated_bundle=reattached.validated_bundle,
        run_ref_bundle_capsule=reattached.run_ref_bundle_capsule,
        diagnostics=compile_result.diagnostics,
        entry_selection=entry_selection,
        imported_workflow_bundles=imported_bindings,
        compile_result=compile_result,
        fingerprint=reattached.fingerprint,
        source_map_payload=reattached.source_map_payload,
        workflow_boundary_projection_payload=reattached.workflow_boundary_projection_payload,
        persisted_surface_payload=reattached.persisted_surface_payload,
        semantic_ir_payload=semantic_ir_payload,
        core_workflow_ast_payload=core_workflow_ast_payload,
        executable_ir_payload=executable_ir_payload,
        runtime_plan_payload=runtime_plan_payload,
        source_read_trace=source_read_snapshot,
        configuration_trace=configuration_snapshot,
        compile_request_capture=compile_request_capture,
    )


def _require_runnable_in_memory_build(
    result: FrontendInMemoryBuildResult,
) -> tuple[
    LoadedWorkflowBundle,
    Path,
    FrontendEntrySelection,
    str,
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
]:
    """Return selected build values or preserve the persistent rejection."""

    if result.entry_selection is None:
        _select_entry_workflow(
            result.compile_result,
            requested_name=result.resolved_request.entry_workflow,
            source_path=result.resolved_request.source_path,
        )
        raise RuntimeError("library-only build unexpectedly selected a workflow")

    required_values = (
        result.validated_bundle,
        result.build_root,
        result.fingerprint,
        result.semantic_ir_payload,
        result.executable_ir_payload,
        result.source_map_payload,
        result.workflow_boundary_projection_payload,
        result.persisted_surface_payload,
    )
    if any(value is None for value in required_values):
        raise RuntimeError("selected in-memory build is missing a required value")

    return (
        result.validated_bundle,
        result.build_root,
        result.entry_selection,
        result.fingerprint,
        result.semantic_ir_payload,
        result.executable_ir_payload,
        result.source_map_payload,
        result.workflow_boundary_projection_payload,
        result.persisted_surface_payload,
    )


def _compile_entry(
    compile_request_capture: FrontendCompileRequestCapture,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> tuple[LinkedStage3CompileResult, FrontendEntrySelection | None]:
    """Compile the entry module graph and select the requested export.

    Stage 1 of `build_frontend_bundle` (see its docstring for the full
    pipeline): `compile_stage3_entrypoint` + `_select_entry_workflow`.
    """

    compiler_session = CompilerSession()
    compile_result = compile_stage3_entrypoint(
        compile_request_capture.source_path,
        source_roots=compile_request_capture.source_roots,
        entry_workflow=compile_request_capture.entry_workflow,
        provider_externs=compile_request_capture.provider_externs,
        prompt_externs=compile_request_capture.prompt_externs,
        imported_workflow_bundles=(
            compile_request_capture.imported_workflow_bundles
        ),
        command_boundaries=compile_request_capture.command_boundaries,
        validation_profile=compile_request_capture.validation_profile,
        workspace_root=compile_request_capture.workspace_root,
        lint_profile=compile_request_capture.lint_profile,
        lowering_route=compile_request_capture.lowering_route,
        source_read_trace=source_read_trace,
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


@dataclass(frozen=True)
class _SelectAndReattachResult:
    """Return bundle for `_select_and_reattach`.

    The dataclass keeps the five stage outputs named at the pipeline boundary;
    see `build_frontend_bundle`'s stage-pipeline docstring.
    """

    validated_bundle: LoadedWorkflowBundle
    run_ref_bundle_capsule: EncodedBundleCapsule | None
    source_map_payload: Mapping[str, object]
    workflow_boundary_projection_payload: Mapping[str, object]
    build_root: Path
    fingerprint: str
    persisted_surface_payload: Mapping[str, object]


def _select_and_reattach(
    compile_result: LinkedStage3CompileResult,
    entry_selection: FrontendEntrySelection,
    *,
    resolved_request: FrontendBuildRequest,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundary_manifest: Mapping[str, object],
    source_read_trace: FrontendSourceReadTraceSnapshot,
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
        source_read_records=source_read_trace.records,
        source_revision_vector=source_read_trace.revision_vector,
    )
    build_root = resolved_request.workspace_root / ".orchestrate" / "build" / fingerprint

    assembled_capsule = assemble_bundle_capsule(
        selected_bundle,
        local_catalog=compile_result,
        imported_catalogs=imported_bindings,
        raw_bytes_by_path=source_read_trace,
        lowering_schema_version=(
            compile_result.entry_result.lowering_schema_version
        ),
    )
    if assembled_capsule is not None:
        selected_bundle = assembled_capsule.bound_controller

    source_map_path = build_root / "source_map.json"
    persisted_surface_payload = serialize_persisted_workflow_surface_graph(selected_bundle)
    persisted_surface_bytes = canonical_persisted_surface_bytes(persisted_surface_payload)
    persisted_surface_graph = decode_persisted_workflow_surface_graph(
        persisted_surface_bytes
    )
    persisted_surface_relative_path = (
        Path("build") / fingerprint / PERSISTED_WORKFLOW_SURFACE_FILENAME
    )
    provenance = replace(
        selected_bundle.provenance,
        frontend_build_root=build_root,
        frontend_source_trace_path=source_map_path,
        frontend_entry_workflow=entry_selection.canonical_name,
        frontend_source_map_schema_version=SOURCE_MAP_SCHEMA_VERSION,
        frontend_source_map_coverage=dict(SOURCE_MAP_COVERAGE),
        frontend_persisted_surface_path=persisted_surface_relative_path,
        frontend_persisted_surface_schema_version=persisted_surface_graph.schema_version,
        frontend_persisted_surface_entry_workflow=entry_selection.canonical_name,
        frontend_persisted_surface_sha256=persisted_surface_sha256(
            persisted_surface_bytes
        ),
    )
    validated_bundle = _reattach_bundle_provenance(
        bundle=selected_bundle,
        provenance=provenance,
        source_map_payload=source_map_payload,
    )
    validated_bundle = _reattach_bundle_semantic_ir(
        validated_bundle,
        source_map_payload=source_map_payload,
    )
    return _SelectAndReattachResult(
        validated_bundle=validated_bundle,
        run_ref_bundle_capsule=(
            assembled_capsule.encoded
            if assembled_capsule is not None
            else None
        ),
        source_map_payload=source_map_payload,
        workflow_boundary_projection_payload=workflow_boundary_projection_payload,
        build_root=build_root,
        fingerprint=fingerprint,
        persisted_surface_payload=persisted_surface_payload,
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
    persisted_surface_payload: Mapping[str, object],
    compile_request_capture: FrontendCompileRequestCapture,
    source_read_trace: FrontendSourceReadTraceSnapshot,
    configuration_trace: FrontendConfigurationTraceSnapshot,
    run_ref_bundle_capsule: EncodedBundleCapsule | None,
) -> FrontendBuildResult:
    """Write build artifacts and the manifest, and assemble the build result.

    Stage 4 of `build_frontend_bundle` (see its docstring for the full
    pipeline): `_write_build_artifacts` + `_build_manifest` + manifest write +
    `FrontendBuildResult` construction.
    """

    diagnostics = compile_result.diagnostics
    build_root.mkdir(parents=True, exist_ok=True)
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
        persisted_surface_payload=persisted_surface_payload,
    )
    if run_ref_bundle_capsule is not None:
        capsule_root = build_root / "run_ref_bundle_capsule.v1"
        write_bundle_capsule_directory(
            capsule_root,
            run_ref_bundle_capsule,
        )
        artifact_paths = dict(artifact_paths)
        artifact_paths.update(
            {
                "run_ref_bundle_capsule_manifest": (
                    capsule_root / "manifest.json"
                ),
                "run_ref_bundle_capsule_pickle": (
                    capsule_root / "bundles.pkl"
                ),
            }
        )
    persisted_surface_path = artifact_paths["persisted_workflow_surface"]
    persisted_surface_bytes = persisted_surface_path.read_bytes()
    decoded_surface = decode_persisted_workflow_surface_graph(persisted_surface_bytes)
    expected_surface_digest = validated_bundle.provenance.frontend_persisted_surface_sha256
    if (
        decoded_surface.entry_workflow != entry_selection.canonical_name
        or persisted_surface_sha256(persisted_surface_bytes) != expected_surface_digest
    ):
        raise ValueError("persisted workflow surface production validation failed")
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
    provenance = validated_bundle.provenance
    expected_manifest_anchor = {
        "schema_version": provenance.frontend_persisted_surface_schema_version,
        "path": (
            provenance.frontend_persisted_surface_path.as_posix()
            if isinstance(provenance.frontend_persisted_surface_path, Path)
            else None
        ),
        "entry_workflow": provenance.frontend_persisted_surface_entry_workflow,
        "sha256": provenance.frontend_persisted_surface_sha256,
    }
    if dict(manifest.persisted_workflow_surface) != expected_manifest_anchor:
        raise ValueError(
            "persisted workflow surface manifest anchor mismatches selected bundle provenance"
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
        run_ref_bundle_capsule=run_ref_bundle_capsule,
        diagnostics=diagnostics,
        artifact_paths=artifact_paths,
        manifest=manifest,
        entry_selection=entry_selection,
        imported_workflow_bundles=imported_bindings,
        compile_result=compile_result,
        compile_request_capture=compile_request_capture,
        resolved_request=resolved_request,
        source_read_trace=source_read_trace,
        configuration_trace=configuration_trace,
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
    """Internal imported-bundle loader sharing one configuration trace."""

    if manifest_path is None:
        return ()
    payload = _load_json_file(
        manifest_path,
        label="imported workflow bundle manifest",
        configuration_read_trace=configuration_read_trace,
    )
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
        bundle_kind = raw_entry.get("kind")
        if bundle_kind != "compiled":
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
        resolved_bundle_path = _resolve_manifest_relative_path(manifest_path, raw_path)
        if resolved_bundle_path.suffix.lower() != ".orc":
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
        compiled_result = _build_frontend_bundle_in_memory(
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
            ),
            source_read_trace=source_read_trace,
            configuration_read_trace=configuration_read_trace,
        )
        try:
            (
                bundle,
                _,
                _,
                bundle_fingerprint,
                _,
                _,
                _,
                _,
                _,
            ) = _require_runnable_in_memory_build(compiled_result)
        except LispFrontendCompileError as error:
            _attach_compile_request_capture(
                error,
                compiled_result.compile_request_capture,
            )
            raise
        workflow_name = compiled_result.selected_workflow_name
        if workflow_name is None:
            raise RuntimeError("compiled imported workflow is missing its selected name")
        bundle_catalog = dict(
            _flatten_compiled_bundle_catalog(compiled_result.compile_result)
        )
        if workflow_name not in bundle_catalog:
            raise RuntimeError(
                "compiled imported workflow is missing from its bundle catalog"
            )
        bundle_catalog[workflow_name] = bundle
        frozen_bundle_catalog = _freeze_imported_bundle_catalog(bundle_catalog)
        load_status = "compiled"
        bindings.append(
            ImportedWorkflowBundleBinding(
                canonical_key=canonical_key,
                manifest_entry_path=raw_path,
                resolved_bundle_path=resolved_bundle_path,
                bundle_kind=bundle_kind,
                workflow_name=workflow_name,
                bundle_fingerprint=bundle_fingerprint,
                load_status=load_status,
                bundle=frozen_bundle_catalog[workflow_name],
                bundle_catalog=frozen_bundle_catalog,
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
    source_map_payload: Mapping[str, object] | None = None,
) -> LoadedWorkflowBundle:
    surface = replace(bundle.surface, provenance=provenance)
    core_workflow_ast = build_core_workflow_ast(
        surface,
        bundle.imports,
        provenance,
        source_map_payload=source_map_payload,
    )
    ir = replace(bundle.ir, provenance=provenance)
    runtime_plan = derive_workflow_runtime_plan(
        ir,
        bundle.projection,
        provenance,
    )
    runtime_plan = enrich_workflow_runtime_plan(
        runtime_plan,
        command_boundary_metadata=_load_command_boundary_metadata(
            provenance,
            workflow_name=surface.name or "",
            source_map_payload=source_map_payload,
        ),
        has_compiled_frontend_lineage=True,
    )
    return replace(
        bundle,
        surface=surface,
        core_workflow_ast=core_workflow_ast,
        ir=ir,
        runtime_plan=runtime_plan,
        provenance=provenance,
    )


def _reattach_bundle_semantic_ir(
    bundle: LoadedWorkflowBundle,
    *,
    source_map_payload: Mapping[str, object] | None = None,
) -> LoadedWorkflowBundle:
    semantic_ir = derive_workflow_semantic_ir(
        core_workflow_ast=bundle.core_workflow_ast,
        surface=bundle.surface,
        ir=bundle.ir,
        projection=bundle.projection,
        runtime_plan=bundle.runtime_plan,
        imports=bundle.imports,
        provenance=bundle.provenance,
        source_map_payload=source_map_payload,
    )
    return replace(bundle, semantic_ir=semantic_ir)
