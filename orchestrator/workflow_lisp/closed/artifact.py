"""Content-addressed on-disk builds for checked closed programs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from orchestrator._common.io_atomic import atomic_write_text
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes

from ..build import FrontendBuildRequest
from ..build import _build_frontend_bundle_in_memory, _require_runnable_in_memory_build
from ..build_manifest_io import (
    ConfigurationReadTrace,
    _load_json_file,
    _json_data,
    _load_command_boundaries_manifest_payload,
    _load_prompt_extern_mapping,
    _load_string_mapping,
    _parse_command_boundaries_manifest,
    _require_build_path_within_workspace,
    _resolve_request,
)
from .. import syntax
from ..diagnostics import LispFrontendCompileError
from ..build import _iter_compiled_import_entries
from ..reader import SourceReadTrace
from .target import entry_target_dsl_version
from .build import Builder, build_closed_program
from .effects import require_command_closures
from .frontend import ProviderIOContext, TypedProgram, compile_typed_program
from .program import ClosedProgram, REPRESENTATION, SCHEMA


@dataclass(frozen=True)
class ClosedProgramBuildResult:
    build_root: Path
    build_key: str
    program: ClosedProgram
    artifact_path: Path
    manifest_path: Path
    entry_workflow: str
    provider_io: ProviderIOContext


def closed_build_key(
    *,
    target: str,
    entry_workflow: str,
    source_file_digests: Mapping[str, str],
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundary_manifest: Mapping[str, object],
    source_module_configurations: Mapping[str, object],
    imported_programs: Mapping[str, object],
) -> str:
    """Return the portable identity of one exact typed source/configuration snapshot."""

    return hashlib.sha256(
        canonical_json_bytes(
            _json_data({
                "target": target,
                "entry_workflow": entry_workflow,
                "source_file_digests": source_file_digests,
                "provider_externs": provider_externs,
                "prompt_externs": prompt_externs,
                "command_boundary_manifest": command_boundary_manifest,
                "source_module_configurations": source_module_configurations,
                "imported_programs": imported_programs,
            })
        )
    ).hexdigest()[:16]


def build_closed_program_bundle(
    request: FrontendBuildRequest,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> ClosedProgramBuildResult:
    """Compile, validate and atomically publish a closed-program artifact."""

    resolved = _resolve_request(request)
    configuration_trace = ConfigurationReadTrace()
    provider_externs = _load_string_mapping(
        resolved.provider_externs_path,
        label="provider externs manifest",
        configuration_read_trace=configuration_trace,
    )
    prompt_externs = _load_prompt_extern_mapping(
        resolved.prompt_externs_path,
        configuration_read_trace=configuration_trace,
    )
    command_boundary_manifest = _load_command_boundaries_manifest_payload(
        resolved.command_boundaries_path,
        configuration_read_trace=configuration_trace,
    )
    command_boundaries = _parse_command_boundaries_manifest(
        command_boundary_manifest,
        manifest_path=resolved.command_boundaries_path,
    )
    require_command_closures(
        command_boundaries,
        manifest_path=resolved.command_boundaries_path,
    )
    bundles_by_binding, programs_by_binding = _load_closed_imports(
        resolved,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundaries=command_boundaries,
        configuration_trace=configuration_trace,
    )
    trace = source_read_trace or SourceReadTrace()
    typed = compile_typed_program(
        resolved.source_path,
        entry_workflow=resolved.entry_workflow,
        source_roots=resolved.source_roots,
        command_boundaries=command_boundaries,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles=bundles_by_binding,
        imported_programs=programs_by_binding,
        workspace_root=resolved.workspace_root,
        source_read_trace=trace,
    )
    builder = Builder(typed)
    _require_program_closures(
        typed, builder=builder, manifest_path=resolved.command_boundaries_path
    )
    configuration = builder.configuration_for(typed, typed.entry_module)
    program = build_closed_program(typed, builder=builder)
    entry_workflow = typed.entry.definition.name
    imported_contributions = {}
    for binding_name in sorted(set(bundles_by_binding) | set(programs_by_binding)):
        producer = programs_by_binding.get(binding_name)
        if producer is None:
            bundle = bundles_by_binding[binding_name]
            producer = getattr(bundle, "typed_program", None)
        if not isinstance(producer, TypedProgram):
            raise RuntimeError(
                f"compiled producer `{binding_name}` did not retain its typed source snapshot"
            )
        imported_contributions[binding_name] = _program_contribution(
            producer, builder=builder
        )
    build_key = closed_build_key(
        target=typed.target,
        entry_workflow=entry_workflow,
        source_file_digests=typed.source_file_digests,
        provider_externs=configuration["providers"],
        prompt_externs=configuration["prompts"],
        command_boundary_manifest=configuration["commands"],
        source_module_configurations=_source_module_configurations(
            typed, builder=builder
        ),
        imported_programs=imported_contributions,
    )
    read_back = ClosedProgram.from_artifact(program.artifact())
    if (
        read_back.digest != program.digest
        or read_back.tree["entry"] != program.tree["entry"]
        or read_back.tree["target"] != typed.target
        or read_back.tree["schema"] != SCHEMA
        or read_back.tree["representation"] != REPRESENTATION
        or read_back.sites != program.sites
    ):
        raise RuntimeError("closed program artifact readback did not match the validated build")

    build_root = resolved.workspace_root / ".orchestrate" / "build" / build_key
    artifact_path = build_root / "closed_program.json"
    manifest_path = build_root / "manifest.json"
    for path in (build_root, artifact_path, manifest_path):
        _require_build_path_within_workspace(
            path,
            workspace_root=resolved.workspace_root,
        )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(artifact_path, program.artifact())
    manifest = {
        "schema_version": "closed-program-build/1",
        "build_key": build_key,
        "program_digest": program.digest,
        "representation": REPRESENTATION,
        "target": typed.target,
        "entry_workflow": entry_workflow,
        "source_path": str(resolved.source_path),
        "source_roots": [str(path) for path in resolved.source_roots],
        "sites": len(program.sites),
        "artifact_paths": {
            "closed_program": f"build/{build_key}/closed_program.json"
        },
    }
    atomic_write_text(
        manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    return ClosedProgramBuildResult(
        build_root=build_root,
        build_key=build_key,
        program=read_back,
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        entry_workflow=entry_workflow,
        provider_io=builder.provider_io.bind(read_back),
    )


def _load_closed_imports(
    request: FrontendBuildRequest,
    *,
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundaries: Mapping[str, object],
    configuration_trace: ConfigurationReadTrace,
) -> tuple[dict[str, object], dict[str, TypedProgram]]:
    manifest_path = request.imported_workflow_bundles_path
    if manifest_path is None:
        return {}, {}
    payload = _load_json_file(
        manifest_path,
        label="imported workflow bundle manifest",
        configuration_read_trace=configuration_trace,
    )
    bundles: dict[str, object] = {}
    programs: dict[str, TypedProgram] = {}
    for binding_name, source_path, requested_entry in _iter_compiled_import_entries(
        payload, manifest_path=manifest_path
    ):
        source_trace = SourceReadTrace()
        try:
            target = entry_target_dsl_version(
                source_path, source_read_trace=source_trace
            )
        except (LispFrontendCompileError, OSError, UnicodeError):
            target = None
        if target is not None and syntax.target_dsl_uses_evaluated_execution(target):
            program = compile_typed_program(
                source_path,
                entry_workflow=requested_entry,
                source_roots=request.source_roots,
                command_boundaries=command_boundaries,
                provider_externs=provider_externs,
                prompt_externs=prompt_externs,
                workspace_root=request.workspace_root,
                source_read_trace=source_trace,
            )
            programs[binding_name] = program
            continue

        producer_request = FrontendBuildRequest(
            source_path=source_path,
            source_roots=request.source_roots,
            entry_workflow=requested_entry,
            provider_externs_path=request.provider_externs_path,
            prompt_externs_path=request.prompt_externs_path,
            imported_workflow_bundles_path=None,
            command_boundaries_path=request.command_boundaries_path,
            workspace_root=request.workspace_root,
            lint_profile=request.lint_profile,
            lowering_route=request.lowering_route,
        )
        in_memory = _build_frontend_bundle_in_memory(
            producer_request,
            source_read_trace=source_trace,
            configuration_read_trace=configuration_trace,
        )
        bundle, *_ = _require_runnable_in_memory_build(in_memory)
        bundles[binding_name] = bundle
    return bundles, programs


def _require_program_closures(
    typed: TypedProgram,
    *,
    builder: Builder,
    manifest_path: Path | None,
) -> None:
    for source_program in builder._programs():
        modules = set(source_program.source_file_digests) or {
            source_program.entry_module
        }
        for module in sorted(modules):
            bindings, _origins = builder._command_bindings(source_program, module)
            require_command_closures(bindings, manifest_path=manifest_path)


def _program_contribution(
    typed: TypedProgram,
    *,
    builder: Builder,
) -> dict[str, object]:
    entry = getattr(typed.entry, "definition", None)
    if entry is None:
        raise RuntimeError("compiled producer has no retained selected entry")
    return {
        "entry_workflow": entry.name,
        "target": typed.target,
        "source_file_digests": typed.source_file_digests,
        "configuration": builder.configuration_for(typed, typed.entry_module),
        "source_module_configurations": _source_module_configurations(
            typed, builder=builder
        ),
        "imported_programs": {
            alias: _program_contribution(program, builder=builder)
            for alias, program in sorted(typed.imported_programs.items())
        },
    }


def _source_module_configurations(
    typed: TypedProgram,
    *,
    builder: Builder,
) -> dict[str, dict[str, object]]:
    return {
        module: builder.configuration_for(typed, module)
        for module in sorted(typed.source_file_digests)
        if module != typed.entry_module
    }
