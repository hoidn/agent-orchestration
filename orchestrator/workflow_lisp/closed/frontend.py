"""Typed source programs for Workflow Lisp evaluated execution."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

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
from ..workflows import (
    ExternEnvironment,
    ProviderExtern,
    PromptExtern,
    TypedWorkflowDef,
    WorkflowSignature,
)
from .. import syntax

if TYPE_CHECKING:
    from orchestrator.workflow.loaded_bundle import WorkflowBoundaryProjectionView


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
    imported_programs: Mapping[str, "TypedProgram"]
    module_workflow_signatures: Mapping[str, Mapping[str, WorkflowSignature]]
    _compiled_bundle_boundaries: Mapping[
        str,
        tuple[
            Mapping[str, Mapping[str, object]],
            Mapping[str, Mapping[str, object]],
            "WorkflowBoundaryProjectionView",
        ],
    ] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        from ..build import _freeze_configuration_value

        immutable_value = _freeze_configuration_value

        for name in (
            "workflows",
            "procedures",
            "procedure_type_envs",
            "workflow_type_envs",
            "module_type_envs",
            "command_boundaries",
            "command_boundary_origins",
            "externs",
            "configuration_bindings",
            "source_file_digests",
            "local_definition_keys",
            "imported_programs",
        ):
            value = getattr(self, name)
            object.__setattr__(self, name, MappingProxyType(dict(value)))
        object.__setattr__(
            self,
            "module_externs",
            immutable_value(self.module_externs),
        )
        object.__setattr__(
            self,
            "configuration_bindings",
            immutable_value(self.configuration_bindings),
        )
        object.__setattr__(
            self,
            "module_workflow_signatures",
            immutable_value(self.module_workflow_signatures),
        )
        from orchestrator.workflow.loaded_bundle import WorkflowBoundaryProjectionView

        frozen_boundaries = {}
        for workflow_name, facts in self._compiled_bundle_boundaries.items():
            input_contracts, output_contracts, projection = facts
            if not isinstance(projection, WorkflowBoundaryProjectionView):
                continue
            frozen_bindings = tuple(
                replace(
                    binding,
                    projection_hints=immutable_value(binding.projection_hints),
                    source_provenance=immutable_value(binding.source_provenance),
                )
                for binding in projection.private_runtime_context_bindings
            )
            frozen_projection = replace(
                projection,
                public_input_contracts=immutable_value(
                    projection.public_input_contracts
                ),
                private_runtime_context_bindings=frozen_bindings,
                private_managed_write_root_inputs=tuple(
                    projection.private_managed_write_root_inputs
                ),
                private_compatibility_bridge_inputs=tuple(
                    projection.private_compatibility_bridge_inputs
                ),
            )
            frozen_boundaries[workflow_name] = (
                immutable_value(input_contracts),
                immutable_value(output_contracts),
                frozen_projection,
            )
        object.__setattr__(
            self,
            "_compiled_bundle_boundaries",
            immutable_value(frozen_boundaries),
        )

    def workflow_type_env(self, name: str) -> FrontendTypeEnvironment:
        return self.workflow_type_envs[name]

    def _workflow_type_env_with_retained_nominal_names(
        self, name: str
    ) -> FrontendTypeEnvironment:
        """Resolve descriptors from the retained module owners without source reads."""

        from copy import copy

        environment = copy(self.workflow_type_env(name))
        nominal_names = dict(
            getattr(
                environment,
                "_nominal_descriptor_names_by_definition_id",
                {},
            )
        )
        for module_env in self.module_type_envs.values():
            nominal_names.update(
                getattr(
                    module_env,
                    "_nominal_descriptor_names_by_definition_id",
                    {},
                )
            )
        environment._nominal_descriptor_names_by_definition_id = nominal_names
        return environment

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
    imported_programs: Mapping[str, TypedProgram] | None = None,
    module_workflow_signatures: Mapping[str, Mapping[str, WorkflowSignature]] | None = None,
) -> TypedProgram:
    from ..build import _freeze_command_boundaries, _freeze_configuration_mapping

    direct_imported_programs = dict(imported_programs or {})
    imported_snapshots = []
    pending_imports = list(direct_imported_programs.values())
    seen_imports: set[int] = set()
    while pending_imports:
        imported = pending_imports.pop()
        if id(imported) in seen_imports:
            continue
        seen_imports.add(id(imported))
        imported_snapshots.append(imported)
        pending_imports.extend(imported.imported_programs.values())

    workflows = {
        **dict(typed_workflows_by_name),
        **{workflow.definition.name: workflow for workflow in typed_workflows},
    }
    for imported in imported_snapshots:
        for name, workflow in imported.workflows.items():
            workflows.setdefault(name, workflow)
    procedures = {
        procedure.definition.name: procedure
        for procedure in resolved_combined_procedures
    }
    for imported in imported_snapshots:
        for name, procedure in imported.procedures.items():
            procedures.setdefault(name, procedure)
    procedure_type_envs = dict(combined_procedure_type_envs)
    for imported in imported_snapshots:
        for name, procedure_type_env in imported.procedure_type_envs.items():
            procedure_type_envs.setdefault(name, procedure_type_env)
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
    module_type_envs = dict(module_type_envs)
    module_externs = {name: dict(bindings) for name, bindings in module_externs.items()}
    local_definition_keys = dict(local_definition_keys)
    module_workflow_signatures = {
        name: dict(signatures)
        for name, signatures in (module_workflow_signatures or {}).items()
    }
    for imported in imported_snapshots:
        for name, owner_env in imported.workflow_type_envs.items():
            workflow_type_envs.setdefault(name, owner_env)
        for name, owner_env in imported.module_type_envs.items():
            module_type_envs.setdefault(name, owner_env)
        for name, owner_externs in imported.module_externs.items():
            module_externs.setdefault(name, dict(owner_externs))
        for name, key in imported.local_definition_keys.items():
            local_definition_keys.setdefault(name, key)
        for module_name, signatures in imported.module_workflow_signatures.items():
            module_workflow_signatures.setdefault(module_name, dict(signatures))
    command_boundaries = _freeze_command_boundaries(
        command_boundary_environment.bindings_by_name
    )
    frozen_configuration = dict(configuration_bindings or {})
    configured_boundaries = frozen_configuration.get("command_boundaries")
    if isinstance(configured_boundaries, Mapping):
        frozen_configuration["command_boundaries"] = _freeze_command_boundaries(
            configured_boundaries
        )
    used_boundaries = frozen_configuration.get("used_command_boundaries")
    if isinstance(used_boundaries, Mapping):
        frozen_configuration["used_command_boundaries"] = {
            module_name: _freeze_command_boundaries(bindings)
            for module_name, bindings in used_boundaries.items()
            if isinstance(bindings, Mapping)
        }
    return TypedProgram(
        entry=None,
        workflows=workflows,
        procedures=procedures,
        type_env=type_env,
        procedure_type_envs=procedure_type_envs,
        workflow_type_envs=workflow_type_envs,
        module_type_envs=module_type_envs,
        command_boundaries=command_boundaries,
        command_boundary_origins=dict(command_boundary_origins or {}),
        externs=dict(extern_environment.bindings_by_name),
        module_externs=module_externs,
        configuration_bindings=_freeze_configuration_mapping(frozen_configuration),
        target=target,
        entry_module=entry_module,
        entry_dir=entry_dir,
        source_file_digests={},
        local_definition_keys=local_definition_keys,
        imported_programs=direct_imported_programs,
        module_workflow_signatures=module_workflow_signatures,
    )


def compile_typed_program(
    entry_path: Path,
    *,
    entry_workflow: str,
    source_roots: tuple[Path, ...],
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding],
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, PromptExtern | str | Mapping[str, object]] | None = None,
    imported_workflow_bundles: Mapping[str, object] | None = None,
    imported_programs: Mapping[str, TypedProgram] | None = None,
    workspace_root: Path | None = None,
    source_read_trace: SourceReadTrace | None = None,
) -> TypedProgram:
    from .. import compiler
    from ..build import _select_entry_workflow_from_surface
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
        imported_workflow_bundles=imported_workflow_bundles,
        imported_programs=imported_programs,
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=workspace_root,
        lowering_route=None,
        source_read_trace=trace,
        _standalone_entry_namespace=(None if source_syntax.module_name is not None else "entry"),
    )
    entry_module_name = result.graph.entry_module_name
    export_surface = result.graph.export_surfaces_by_name[entry_module_name]
    entry_module = result.graph.modules_by_name[entry_module_name]
    entry_workflow_names = {
        workflow.definition.name for workflow in result.entry_result.typed_workflows
    }
    if source_syntax.module_name is None:
        canonical_name = (
            entry_workflow
            if "::" in entry_workflow
            else f"entry::{entry_workflow}"
        )
        if canonical_name not in entry_workflow_names:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="entry_workflow_unknown",
                        message=f"entry workflow `{entry_workflow}` is not present in the typed program",
                        path=entry_path,
                    ),
                )
            )
    else:
        entry_selection = _select_entry_workflow_from_surface(
            export_surface,
            requested_name=entry_workflow,
            available_names=entry_workflow_names,
            source_path=entry_path,
            entry_span=entry_module.syntax_module.span,
        )
        canonical_name = entry_selection.canonical_name
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
