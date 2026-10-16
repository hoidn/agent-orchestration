"""Content-addressed on-disk builds for checked closed programs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path

from orchestrator._common.io_atomic import atomic_write_text
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes

from ..build import FrontendBuildRequest
from ..build import _load_imported_workflow_bundle_manifest
from ..build_manifest_io import (
    ConfigurationReadTrace,
    _json_data,
    _load_command_boundaries_manifest_payload,
    _load_prompt_extern_mapping,
    _load_string_mapping,
    _parse_command_boundaries_manifest,
    _require_build_path_within_workspace,
    _resolve_request,
)
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..effects import EffectSummary
from ..workflows import Stage3CompileResult
from ..reader import SourceReadTrace
from .build import Builder, build_closed_program
from .effects import require_command_closures
from orchestrator.workflow.evaluated.provider_io import ProviderIOContext
from orchestrator.contracts.closed_program.program import ClosedProgram, REPRESENTATION, SCHEMA
from .frontend import (
    TypedProgram,
    compile_typed_program_with_result,
)


@dataclass(frozen=True)
class ClosedProgramBuildResult:
    build_root: Path
    build_key: str
    program: ClosedProgram
    artifact_path: Path
    manifest_path: Path
    entry_workflow: str
    provider_io: ProviderIOContext
    compile_diagnostics: tuple[LispFrontendDiagnostic, ...] | None
    entry_effect_summary: EffectSummary
    typed_program: TypedProgram | None = field(default=None, compare=False, repr=False)
    stage3: Stage3CompileResult | None = field(default=None, compare=False, repr=False)
    builder: Builder | None = field(default=None, compare=False, repr=False)


class ConfinedRunRefUnavailable(ValueError):
    """A checked program has a confined run-ref child this release cannot run."""

    code = "run_ref_provider_transport_unavailable"


def _performs_provider(value: object) -> bool:
    if isinstance(value, Mapping):
        if value.get("k") == "perform" and value.get("class") in {"provider", "provider_phased"}:
            return True
        return any(_performs_provider(item) for item in value.values())
    if isinstance(value, list):
        return any(_performs_provider(item) for item in value)
    return False


def refuse_confined_run_ref_sites(program: ClosedProgram) -> None:
    """Refuse execution before any run state or child provisioning (Rulings P11, P33).

    Confined children whose effects are commands run; a child with a provider site
    waits for the confined provider transport (Task 10).
    """

    children = program.tree.get("children", {})
    names = sorted(child["entry"].removeprefix("workflow:") for child in children.values()
                   if _performs_provider(child))
    if names:
        raise ConfinedRunRefUnavailable(
            "confined run-ref children with provider effects have no qualified transport yet: "
            + ", ".join(names)
        )


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


def _prepare_closed_program_bundle(
    request: FrontendBuildRequest,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> ClosedProgramBuildResult:
    """Prepare a checked program and carrier in memory, without cache writes."""

    from .target import refuse_retired_entry_target

    resolved = request
    refuse_retired_entry_target(resolved.source_path, source_read_trace=source_read_trace)
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
    programs_by_binding = _load_closed_imports(
        resolved,
        configuration_trace=configuration_trace,
    )
    trace = source_read_trace or SourceReadTrace()
    try:
        typed, stage3 = compile_typed_program_with_result(
            resolved.source_path,
            entry_workflow=resolved.entry_workflow,
            source_roots=resolved.source_roots,
            command_boundaries=command_boundaries,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            imported_programs=programs_by_binding,
            workspace_root=resolved.workspace_root,
            source_read_trace=trace,
        )
    except LispFrontendCompileError as exc:
        if any(
            diagnostic.code == "target_dsl_unsupported"
            for diagnostic in exc.diagnostics
        ):
            source_bytes = trace.raw_bytes_by_path.get(resolved.source_path)
            if source_bytes is not None:
                from .target import refuse_retired_entry_target_from_bytes

                try:
                    refuse_retired_entry_target_from_bytes(
                        resolved.source_path, source_bytes
                    )
                except LispFrontendCompileError as admission_error:
                    if any(
                        diagnostic.code == "workflow_execution_target_retired"
                        for diagnostic in admission_error.diagnostics
                    ):
                        raise
        raise
    builder = Builder(typed)
    _require_program_closures(
        typed, builder=builder, manifest_path=resolved.command_boundaries_path
    )
    configuration = builder.configuration_for(typed, typed.entry_module)
    program = build_closed_program(typed, builder=builder)
    entry_workflow = typed.entry.definition.name
    imported_contributions = {}
    for binding_name, producer in sorted(programs_by_binding.items()):
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
        (read_back.digest, read_back.tree["entry"], read_back.tree["target"],
         read_back.tree["schema"], read_back.tree["representation"], read_back.sites)
        != (program.digest, program.tree["entry"], typed.target, SCHEMA, REPRESENTATION, program.sites)
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
    return ClosedProgramBuildResult(
        build_root=build_root,
        build_key=build_key,
        program=read_back,
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        entry_workflow=entry_workflow,
        provider_io=builder.provider_io.bind(read_back),
        compile_diagnostics=typed.compile_diagnostics,
        entry_effect_summary=typed.entry.effect_summary,
        typed_program=typed,
        stage3=stage3,
        builder=builder,
    )


def prepare_closed_program_bundle(
    request: FrontendBuildRequest,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> ClosedProgramBuildResult:
    """Resolve once and prepare a checked program without cache publication."""
    return _prepare_closed_program_bundle(_resolve_request(request), source_read_trace=source_read_trace)


def build_closed_program_bundle(
    request: FrontendBuildRequest,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> ClosedProgramBuildResult:
    """Prepare, validate and atomically publish a closed-program artifact."""
    resolved = _resolve_request(request)
    built = _prepare_closed_program_bundle(resolved, source_read_trace=source_read_trace)
    built.artifact_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(built.artifact_path, built.program.artifact())
    manifest = {
        "schema_version": "closed-program-build/1",
        "build_key": built.build_key,
        "program_digest": built.program.digest,
        "representation": REPRESENTATION,
        "target": built.program.tree["target"],
        "entry_workflow": built.entry_workflow,
        "source_path": str(resolved.source_path),
        "source_roots": [str(path) for path in resolved.source_roots],
        "sites": len(built.program.sites),
        "artifact_paths": {
            "closed_program": f"build/{built.build_key}/closed_program.json"
        },
    }
    atomic_write_text(built.manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return built


def _load_closed_imports(
    request: FrontendBuildRequest,
    *,
    configuration_trace: ConfigurationReadTrace,
) -> dict[str, TypedProgram]:
    bindings = _load_imported_workflow_bundle_manifest(
        request.imported_workflow_bundles_path,
        workspace_root=request.workspace_root,
        source_roots=request.source_roots,
        provider_externs_path=request.provider_externs_path,
        prompt_externs_path=request.prompt_externs_path,
        command_boundaries_path=request.command_boundaries_path,
        source_read_trace=None,
        configuration_read_trace=configuration_trace,
    )
    return {binding.canonical_key: binding.typed_program for binding in bindings}


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
