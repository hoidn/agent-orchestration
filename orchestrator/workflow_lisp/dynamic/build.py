"""Checked dynamic source builds using the established frontend request owners."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Mapping
from types import MappingProxyType
import json

from orchestrator.workflow.workspace_files import WorkspaceFiles
from ..build import FrontendBuildRequest, FrontendSourceReadTraceSnapshot, FrontendConfigurationTraceSnapshot
from ..build_manifest_io import (
    ConfigurationReadTrace, _cli_request_diagnostic, _load_string_mapping,
    _load_prompt_extern_mapping, _load_command_boundaries_manifest_payload,
    _parse_command_boundaries_manifest, _resolve_request, _require_build_path_within_workspace,
)
from orchestrator.contracts.closed_program.program import canonical_digest
from ..diagnostics import LispFrontendCompileError
from ..reader import SourceReadTrace
from .program import DynamicProgram
from .source import compile_source


@dataclass(frozen=True)
class DynamicProgramBuildResult:
    program: DynamicProgram
    build_key: str
    build_root: Path
    artifact_path: Path
    manifest_path: Path
    entry_workflow: str
    source_paths: Mapping[str, Path]
    source_read_trace: FrontendSourceReadTraceSnapshot
    configuration_trace: FrontendConfigurationTraceSnapshot
    lowerer: object | None = field(default=None, compare=False, repr=False)


def prepare_dynamic_program_bundle(request: FrontendBuildRequest, *, source_read_trace=None) -> DynamicProgramBuildResult:
    """Normalize, load, and admit without publishing or evaluating the program."""
    request = _resolve_request(request)
    if request.imported_workflow_bundles_path is not None:
        raise LispFrontendCompileError((_cli_request_diagnostic(
            code="dynamic_import_incompatible", message="dynamic source refuses every compiled import bundle; import source declarations or target 3.0 modules",
            path=request.imported_workflow_bundles_path,
        ),))
    if request.emit_debug_yaml or request.lowering_route is not None or request.boundary_admission_profile is not None:
        raise LispFrontendCompileError((_cli_request_diagnostic(
            code="workflow_lisp_cli_input_unsupported", message="dynamic source does not accept flat debug YAML, typed lowering or admission profiles",
            path=request.source_path,
        ),))
    trace = source_read_trace or SourceReadTrace()
    configuration = ConfigurationReadTrace()
    providers = _load_string_mapping(request.provider_externs_path, label="provider externs manifest", configuration_read_trace=configuration)
    prompts = _load_prompt_extern_mapping(request.prompt_externs_path, configuration_read_trace=configuration)
    commands_payload = _load_command_boundaries_manifest_payload(request.command_boundaries_path, configuration_read_trace=configuration)
    commands = _parse_command_boundaries_manifest(commands_payload, manifest_path=request.command_boundaries_path)
    compiled = compile_source(request.source_path, source_roots=request.source_roots, entry_workflow=request.entry_workflow,
                              provider_externs=providers, prompt_externs=prompts, command_boundaries=commands, source_read_trace=trace)
    read_back = DynamicProgram.from_artifact(compiled.program.artifact())
    if (read_back.semantic_digest, read_back.provenance_digest) != (compiled.program.semantic_digest, compiled.program.provenance_digest):
        raise RuntimeError("dynamic artifact readback differs from admitted source")
    build_key = canonical_digest({
        "program": read_back.semantic_digest, "provenance": read_back.provenance_digest,
        "configuration_revisions": {
            name: dict(configuration.revision_vector).get(getattr(request, name))
            for name in ("provider_externs_path", "prompt_externs_path", "command_boundaries_path")
        },
    }).removeprefix("sha256:")[:16]
    root = request.workspace_root / ".orchestrate" / "build" / build_key
    artifact, manifest = root / "dynamic_program.json", root / "manifest.json"
    for path in (root, artifact, manifest):
        _require_build_path_within_workspace(path, workspace_root=request.workspace_root)
    return DynamicProgramBuildResult(read_back, build_key, root, artifact, manifest, read_back.entry,
                                     MappingProxyType(dict(compiled.source_paths)),
                                     FrontendSourceReadTraceSnapshot(trace.records, trace.revision_vector, trace.raw_bytes_by_path),
                                     FrontendConfigurationTraceSnapshot(configuration.records, configuration.revision_vector), compiled.lowerer)


def build_dynamic_program_bundle(request: FrontendBuildRequest, *, source_read_trace=None) -> DynamicProgramBuildResult:
    """Atomically publish the checked program and its source/configuration evidence."""
    built = prepare_dynamic_program_bundle(request, source_read_trace=source_read_trace)
    manifest = {
        "schema_version": "dynamic-program-build/1", "target": "3.0", "representation": "dynamic/1",
        "build_key": built.build_key, "entry_workflow": built.entry_workflow,
        "program_digest": built.program.semantic_digest, "provenance_digest": built.program.provenance_digest,
        "source_path": str(request.source_path), "source_roots": [str(path) for path in request.source_roots],
        "source_revisions": [[str(path), revision] for path, revision in built.source_read_trace.revision_vector],
        "configuration_revisions": [[str(path), revision] for path, revision in built.configuration_trace.revision_vector],
        "artifact_paths": {"dynamic_program": f"build/{built.build_key}/dynamic_program.json"},
    }
    files = WorkspaceFiles(built.build_root.parents[2])
    try:
        files.write_atomic(built.artifact_path, built.program.artifact().encode("utf-8"))
        files.write_atomic(built.manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        persisted = DynamicProgram.from_artifact(files.read(built.artifact_path))
    finally:
        files.close()
    if (persisted.semantic_digest, persisted.provenance_digest) != (built.program.semantic_digest, built.program.provenance_digest):
        raise RuntimeError("published dynamic artifact readback differs from its build")
    return built
