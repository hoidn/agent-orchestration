"""Typed source programs for Workflow Lisp evaluated execution."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from ..command_boundaries import CertifiedAdapterBinding, ExternalToolBinding
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..procedures import GeneratedLocalProcedure, TypedProcedureDef, procedure_type_env_for
from ..reader import SourceReadTrace, read_sexpr_file
from ..spans import SourceSpan
from ..syntax import (
    SyntaxIdentifier,
    SyntaxList,
    syntax_node_datum,
)
from ..type_env import FrontendTypeEnvironment
from ..workflows import ExternEnvironment, ProviderExtern, PromptExtern, TypedWorkflowDef
from .. import syntax


@dataclass(frozen=True)
class TypedProgram:
    entry: TypedWorkflowDef | None
    workflows: Mapping[str, TypedWorkflowDef]
    procedures: Mapping[str, TypedProcedureDef]
    type_env: FrontendTypeEnvironment
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment]
    workflow_type_envs: Mapping[str, FrontendTypeEnvironment]
    module_type_envs: Mapping[str, FrontendTypeEnvironment]
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]
    command_boundary_origins: Mapping[str, str]
    externs: Mapping[str, ProviderExtern | PromptExtern]
    module_externs: Mapping[str, Mapping[str, ProviderExtern | PromptExtern]]
    configuration_bindings: Mapping[str, object]
    target: str
    entry_module: str
    entry_dir: str
    source_file_digests: Mapping[str, str]
    local_definition_keys: Mapping[str, object]

    def workflow_type_env(self, name: str) -> FrontendTypeEnvironment:
        return self.workflow_type_envs[name]

    def procedure_type_env(self, procedure: TypedProcedureDef) -> FrontendTypeEnvironment:
        return procedure_type_env_for(
            procedure,
            procedure_type_envs=self.procedure_type_envs,
            default=self.type_env,
        )


def local_definition_keys_for_module(
    module_name: str,
    expanded_syntax,
    typed_procedures: tuple[TypedProcedureDef, ...],
) -> dict[str, object]:
    """Build position-free lexical identities for generated local procedures."""

    declaration_ordinals: dict[tuple[str, str], int] = defaultdict(int)
    declarations_by_origin: dict[
        tuple[tuple[str, int, int, int, int], str, str], list[int]
    ] = defaultdict(list)
    declarations_consumed: dict[
        tuple[tuple[str, int, int, int, int], str, str], int
    ] = defaultdict(int)

    def span_key(span: SourceSpan) -> tuple[str, int, int, int, int]:
        return (
            span.start.path,
            span.start.line,
            span.start.column,
            span.end.line,
            span.end.column,
        )

    def walk(datum, owner: str | None = None) -> None:
        if not isinstance(datum, SyntaxList) or not datum.items:
            return
        head = datum.items[0]
        head_name = head.resolved_name if isinstance(head, SyntaxIdentifier) else None
        if head_name in {"defworkflow", "defproc"} and len(datum.items) > 1:
            name = datum.items[1]
            callable_owner = name.resolved_name if isinstance(name, SyntaxIdentifier) else owner
            for item in datum.items[1:]:
                walk(item, callable_owner)
            return
        if head_name == "let-proc" and len(datum.items) > 1:
            binding = datum.items[1]
            if isinstance(binding, SyntaxList) and binding.items:
                name = binding.items[0]
                if isinstance(name, SyntaxIdentifier) and owner is not None:
                    ordinal_key = (owner, name.resolved_name)
                    ordinal = declaration_ordinals[ordinal_key]
                    declaration_ordinals[ordinal_key] += 1
                    declarations_by_origin[
                        (span_key(binding.span), owner, name.resolved_name)
                    ].append(ordinal)
            for item in datum.items[1:]:
                walk(item, owner)
            return
        for item in datum.items:
            walk(item, owner)

    for form in expanded_syntax.forms:
        walk(syntax_node_datum(form))

    local_keys: dict[str, object] = {}
    for procedure in typed_procedures:
        metadata = procedure.definition.generated_local_procedure
        if not isinstance(metadata, GeneratedLocalProcedure):
            continue
        declaration_key = (
            span_key(metadata.origin_span),
            metadata.owner_callable_name,
            metadata.authored_local_name,
        )
        matching_ordinals = declarations_by_origin.get(declaration_key, ())
        consumed = declarations_consumed[declaration_key]
        if consumed >= len(matching_ordinals):
            raise RuntimeError(
                "generated local procedure has no matching expanded declaration"
            )
        declarations_consumed[declaration_key] += 1
        owner = metadata.owner_callable_name
        local_name = metadata.authored_local_name
        ordinal = matching_ordinals[consumed]
        canonical_owner = (
            owner
            if "::" in owner
            else f"{module_name}::{metadata.owner_callable_name}"
        )
        capture_count = len(metadata.capture_names)
        capture_schema = tuple(
            (parameter.name, parameter.type_name)
            for parameter in procedure.definition.params[:capture_count]
        )
        local_keys[procedure.definition.name] = (
            canonical_owner,
            local_name,
            ordinal,
            capture_schema,
            metadata.residual_params,
            metadata.return_type_name,
        )
    return local_keys


def typed_program_from_graph(
    *,
    target: str,
    entry_module: str,
    entry_dir: str,
    type_env: FrontendTypeEnvironment,
    extern_environment: ExternEnvironment,
    command_boundary_environment,
    typed_workflows,
    resolved_combined_procedures,
    typed_workflows_by_name: Mapping[str, TypedWorkflowDef],
    combined_procedure_type_envs: Mapping[str, FrontendTypeEnvironment],
    workflow_type_envs_by_name: Mapping[str, FrontendTypeEnvironment],
    module_type_envs: Mapping[str, FrontendTypeEnvironment],
    module_externs: Mapping[str, Mapping[str, object]],
    local_definition_keys: Mapping[str, object],
    command_boundary_origins: Mapping[str, str] | None = None,
    configuration_bindings: Mapping[str, object] | None = None,
) -> TypedProgram:
    workflows = {
        **dict(typed_workflows_by_name),
        **{workflow.definition.name: workflow for workflow in typed_workflows},
    }
    procedures = {
        procedure.definition.name: procedure
        for procedure in resolved_combined_procedures
    }
    procedure_type_envs = dict(combined_procedure_type_envs)
    for procedure in procedures.values():
        procedure_type_envs.setdefault(
            procedure.definition.name,
            procedure_type_env_for(
                procedure,
                procedure_type_envs=procedure_type_envs,
                default=type_env,
            ),
        )
    workflow_type_envs = {
        **dict(workflow_type_envs_by_name),
        **{workflow.definition.name: type_env for workflow in typed_workflows},
    }
    return TypedProgram(
        entry=None,
        workflows=workflows,
        procedures=procedures,
        type_env=type_env,
        procedure_type_envs=procedure_type_envs,
        workflow_type_envs=workflow_type_envs,
        module_type_envs=dict(module_type_envs),
        command_boundaries=dict(command_boundary_environment.bindings_by_name),
        command_boundary_origins=dict(command_boundary_origins or {}),
        externs=dict(extern_environment.bindings_by_name),
        module_externs={name: dict(bindings) for name, bindings in module_externs.items()},
        configuration_bindings=dict(configuration_bindings or {}),
        target=target,
        entry_module=entry_module,
        entry_dir=entry_dir,
        source_file_digests={},
        local_definition_keys=dict(local_definition_keys),
    )


def compile_typed_program(
    entry_path: Path,
    *,
    entry_workflow: str,
    source_roots: tuple[Path, ...],
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding],
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, PromptExtern | str | Mapping[str, object]] | None = None,
    workspace_root: Path | None = None,
    source_read_trace: SourceReadTrace | None = None,
) -> TypedProgram:
    from .. import compiler
    from ..build_artifacts import _source_file_digests_from_trace
    from ..build_manifest_io import _cli_request_diagnostic
    from .target import _entry_target_header_from_tree

    trace = source_read_trace or SourceReadTrace()
    parse_tree = read_sexpr_file(entry_path, source_read_trace=trace)
    target, target_span = _entry_target_header_from_tree(parse_tree)
    if not syntax.target_dsl_uses_evaluated_execution(target):
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="evaluated_execution_target_required",
                    message=(
                        f"typed-program compilation requires target DSL "
                        f"{syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION} or newer; "
                        f"the entry declares {target}"
                    ),
                    span=target_span,
                    phase="typecheck",
                ),
            )
        )
    source_syntax = syntax.build_syntax_module(parse_tree)
    result = compiler.compile_stage3_entrypoint(
        entry_path,
        entry_workflow=entry_workflow,
        source_roots=source_roots,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=workspace_root,
        lowering_route=None,
        source_read_trace=trace,
        _standalone_entry_namespace=(None if source_syntax.module_name is not None else "entry"),
    )
    entry_module_name = result.graph.entry_module_name
    export_surface = result.graph.export_surfaces_by_name[entry_module_name]
    binding = export_surface.workflows_by_name.get(entry_workflow)
    canonical_name = binding.canonical_name if binding is not None else entry_workflow
    if source_syntax.module_name is None and "::" not in canonical_name:
        canonical_name = f"entry::{canonical_name}"
    program = result.entry_result.typed_program
    if not isinstance(program, TypedProgram):
        raise RuntimeError("evaluated-entry compilation did not produce a TypedProgram")
    workflow = program.workflows.get(canonical_name)
    if workflow is None:
        raise LispFrontendCompileError(
            (
                _cli_request_diagnostic(
                    code="entry_workflow_unknown",
                    message=f"entry workflow `{entry_workflow}` is not present in the typed program",
                    path=entry_path,
                ),
            )
        )
    digests = _source_file_digests_from_trace(
        compile_result=result,
        source_read_records=trace.records,
        source_revision_vector=trace.revision_vector,
    )
    return replace(
        program,
        entry=workflow,
        source_file_digests=digests,
    )
