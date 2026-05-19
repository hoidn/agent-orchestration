"""Pure Stage 1 compiler pipeline for the workflow Lisp frontend."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle

from .definitions import (
    EnumDef,
    PathDef,
    RecordDef,
    RecordField,
    UnionDef,
    UnionVariant,
    WorkflowLispModule,
    elaborate_definition_module,
)
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .lowering import lower_workflow_definitions, validate_lowered_workflows
from .reader import read_sexpr_file
from .sexpr import ListExpr, SymbolAtom
from .syntax import WorkflowLispSyntaxModule, build_syntax_module
from .type_env import PRELUDE_TYPE_NAMES, FrontendTypeEnvironment
from .workflows import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    Stage3CompileResult,
)
from .workflows import (
    build_command_boundary_environment,
    build_extern_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)

def compile_stage3_module(
    path: Path,
    *,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
    validate_shared: bool = True,
    workspace_root: Path | None = None,
) -> Stage3CompileResult:
    """Compile one `.orc` file through the additive Stage 3 pipeline."""

    parse_tree = read_sexpr_file(path)
    syntax_module = build_syntax_module(parse_tree)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    extern_environment = build_extern_environment(
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
    )
    command_boundary_environment = build_command_boundary_environment(command_boundaries)
    typed_workflows = typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
    )
    lowered_workflows = lower_workflow_definitions(
        typed_workflows,
        workflow_path=path,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
    )
    validated_bundles: Mapping[str, LoadedWorkflowBundle]
    if validate_shared:
        validated_bundles = validate_lowered_workflows(
            lowered_workflows,
            workspace_root=workspace_root or path.parent,
        )
    else:
        validated_bundles = {}
    return Stage3CompileResult(
        module=module,
        workflow_catalog=workflow_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        typed_workflows=typed_workflows,
        lowered_workflows=lowered_workflows,
        validated_bundles=validated_bundles,
    )


def compile_stage1_module(path: Path) -> WorkflowLispModule:
    """Compile one `.orc` file through the Stage 1 frontend pipeline."""

    parse_tree = read_sexpr_file(path)
    syntax_module = build_syntax_module(parse_tree)
    module = elaborate_definition_module(syntax_module)
    _validate_definition_module(module)
    return module


def _validate_definition_module(module: WorkflowLispModule) -> None:
    diagnostics: list[LispFrontendDiagnostic] = []
    definition_names: dict[str, object] = {}
    for definition in module.definitions:
        if definition.name in definition_names:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="definition_duplicate",
                    message=f"duplicate definition `{definition.name}`",
                    span=definition.span,
                    form_path=_definition_form_path(definition),
                )
            )
        else:
            definition_names[definition.name] = definition

    available_type_names = PRELUDE_TYPE_NAMES | frozenset(definition_names)
    for definition in module.definitions:
        if isinstance(definition, RecordDef):
            diagnostics.extend(_validate_field_list(definition.fields, _definition_form_path(definition)))
            diagnostics.extend(_validate_field_types(definition.fields, _definition_form_path(definition), available_type_names))
        elif isinstance(definition, UnionDef):
            diagnostics.extend(_validate_union_definition(definition, available_type_names))

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))


def _validate_union_definition(
    definition: UnionDef,
    available_type_names: frozenset[str],
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    seen_variants: set[str] = set()
    form_path = _definition_form_path(definition)
    for variant in definition.variants:
        if variant.name in seen_variants:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="union_variant_duplicate",
                    message=f"duplicate union variant `{variant.name}`",
                    span=variant.span,
                    form_path=form_path,
                )
            )
        else:
            seen_variants.add(variant.name)
        diagnostics.extend(
            _validate_field_list(
                variant.fields,
                form_path,
                scope_label=f"union variant `{variant.name}`",
            )
        )
        diagnostics.extend(_validate_field_types(variant.fields, form_path, available_type_names))
    return diagnostics


def _validate_field_list(
    fields: tuple[RecordField, ...],
    form_path: tuple[str, ...],
    *,
    scope_label: str = "record",
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    seen_fields: set[str] = set()
    for field in fields:
        if field.name in seen_fields:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="record_field_duplicate",
                    message=f"duplicate field `{field.name}` in {scope_label}",
                    span=field.span,
                    form_path=form_path,
                )
            )
        else:
            seen_fields.add(field.name)
    return diagnostics


def _validate_field_types(
    fields: tuple[RecordField, ...],
    form_path: tuple[str, ...],
    available_type_names: frozenset[str],
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    for field in fields:
        if field.type_name not in available_type_names:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="type_unknown",
                    message=f"unknown type `{field.type_name}`",
                    span=field.span,
                    form_path=form_path,
                )
            )
    return diagnostics


def _definition_form_path(definition: EnumDef | PathDef | RecordDef | UnionDef) -> tuple[str, ...]:
    if isinstance(definition, EnumDef):
        return ("workflow-lisp", "defenum", definition.name)
    if isinstance(definition, PathDef):
        return ("workflow-lisp", "defpath", definition.name)
    if isinstance(definition, RecordDef):
        return ("workflow-lisp", "defrecord", definition.name)
    return ("workflow-lisp", "defunion", definition.name)


def _definition_only_syntax_module(module_syntax: WorkflowLispSyntaxModule) -> WorkflowLispSyntaxModule:
    definition_forms = []
    for form in module_syntax.forms:
        datum = form.datum
        if not isinstance(datum, ListExpr) or not datum.items:
            continue
        head = datum.items[0]
        if isinstance(head, SymbolAtom) and head.value == "defworkflow":
            continue
        definition_forms.append(form)
    return WorkflowLispSyntaxModule(
        language_version=module_syntax.language_version,
        target_dsl_version=module_syntax.target_dsl_version,
        forms=tuple(definition_forms),
        span=module_syntax.span,
        module_path=module_syntax.module_path,
    )
