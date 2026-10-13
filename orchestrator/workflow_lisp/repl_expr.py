"""Compile attached-run expressions through the ordinary Lisp frontend."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from orchestrator.workflow.evaluated.capture import CapturedRun, visible_bindings
from orchestrator.workflow.evaluated.machine import _Machine
from orchestrator.workflow.evaluated.values import (
    EvaluatedValue, EvaluatedValueError, evaluate_closed_value,
)
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes

from . import expressions, functions, syntax
from .closed.artifact import ClosedProgramBuildResult
from .closed.build import Builder, _strip_provenance
from .closed.frontend import TypedProgram
from .closed.names import canonical_type_descriptor
from orchestrator.contracts.closed_program.sites import _ast_nodes, _value_nodes
from .compiler_session import CompilerSession
from .diagnostics import LispFrontendCompileError
from .reader import read_sexpr_text
from .type_env import (
    DiscriminantTypeRef, FrontendTypeEnvironment, ListTypeRef, MapTypeRef,
    OptionalTypeRef, PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef,
    VariantCaseTypeRef,
)
from .typecheck_context import TypedExpr
from .typecheck_dispatch import typecheck_expression
from .workflows import ProviderExtern, Stage3CompileResult, WorkflowSignature


class ReplRefusal(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class LoadedModule:
    build: ClosedProgramBuildResult
    source_path: Path
    frontend_argv: tuple[str, ...] = ()
    source_snapshots: Mapping[Path, bytes] = field(default_factory=dict, compare=False, repr=False)
    source_revisions: tuple[tuple[Path, str], ...] = field(default=(), compare=False, repr=False)
    source_origin: Literal["loaded", "reconstructed"] = field(default="loaded", compare=False)
    typed_program: TypedProgram = field(init=False, repr=False)
    stage3: Stage3CompileResult = field(init=False, repr=False)
    builder: Builder = field(init=False, repr=False)
    type_env: FrontendTypeEnvironment = field(init=False, repr=False)
    _binding_refs: dict[bytes, TypeRef] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.source_snapshots = MappingProxyType(dict(self.source_snapshots))
        self.source_revisions = tuple(self.source_revisions)
        built = self.build
        if built.typed_program is None or built.stage3 is None or built.builder is None:
            raise ReplRefusal(
                "repl_module_context_missing", "load requires retained compiler context"
            )
        self.typed_program = built.typed_program
        self.stage3 = built.stage3
        self.type_env = self.typed_program.workflow_type_env(
            self.typed_program.entry.definition.name
        )
        self.builder = built.builder
        self._binding_refs = _descriptor_type_refs(self)


def _descriptor_key(descriptor: Mapping) -> bytes:
    return canonical_json_bytes(_strip_provenance(descriptor))


def _descriptor_type_refs(module: LoadedModule) -> dict[bytes, TypeRef]:
    result: dict[bytes, TypeRef] = {}
    seen: set[tuple[int, int]] = set()

    def visit(ref, program):
        key = id(ref), id(program)
        if key in seen:
            return
        seen.add(key)
        if isinstance(ref, (RecordTypeRef, PrimitiveTypeRef, PathTypeRef, UnionTypeRef,
                            VariantCaseTypeRef, DiscriminantTypeRef,
                            ListTypeRef, OptionalTypeRef, MapTypeRef)):
            result[_descriptor_key(canonical_type_descriptor(ref, typed=program))] = ref
        if isinstance(ref, RecordTypeRef):
            children = ref.field_types.values()
        elif isinstance(ref, (ListTypeRef, OptionalTypeRef)):
            children = (ref.item_type_ref,)
        elif isinstance(ref, MapTypeRef):
            children = (ref.key_type_ref, ref.value_type_ref)
        elif isinstance(ref, UnionTypeRef):
            children = (*ref.type_args, *(child for row in ref.variant_field_types.values()
                                         for child in row.values()))
        elif isinstance(ref, VariantCaseTypeRef):
            children = (*ref.union_type_args, *(ref.field_types or {}).values())
        elif isinstance(ref, DiscriminantTypeRef):
            children = tuple(child for child in (ref.applied_union, ref.owner_union)
                             if child is not None)
        else:
            children = ()
        for child in children:
            visit(child, program)

    def typed_nodes(body, program):
        pending, visited = [body], set()
        while pending:
            node = pending.pop()
            if id(node) in visited:
                continue
            visited.add(id(node))
            if isinstance(node, TypedExpr):
                visit(node.type_ref, program)
            if isinstance(node, TypeRef):
                continue
            if is_dataclass(node):
                pending.extend(getattr(node, row.name) for row in fields(node))
            elif isinstance(node, Mapping):
                pending.extend(node.values())
            elif isinstance(node, (tuple, list)):
                pending.extend(node)

    for program in module.builder._programs():
        for definition in (*program.workflows.values(), *program.procedures.values()):
            for _name, ref in definition.signature.params:
                visit(ref, program)
            visit(definition.signature.return_type_ref, program)
            typed_nodes(definition.typed_body, program)
    for descriptor, ref, program, _context, _hint in module.builder.emitted_descriptors:
        result[_descriptor_key(descriptor)] = ref
        visit(ref, program)
    return result


def binding_type_refs(
    module: LoadedModule, bindings: dict[str, EvaluatedValue]
) -> dict[str, TypeRef]:
    result = {}
    for name, value in bindings.items():
        if value.descriptor.get("kind") == "variant_case":
            continue
        ref = module._binding_refs.get(_descriptor_key(value.descriptor))
        if ref is not None:
            result[name] = ref
    return result


def _require_pure_lowered(value, definitions):
    pending, checked = list(_value_nodes(value)), set()
    while pending:
        node = pending.pop()
        if node.get("k") == "perform":
            raise ReplRefusal("repl_effect_refused", "REPL expressions must be pure")
        if node.get("k") == "call" and node["callee"] not in checked:
            checked.add(node["callee"])
            definition = definitions.get(node["callee"])
            if definition is None:
                raise ReplRefusal(
                    "repl_module_context_missing", f"missing callee {node['callee']!r}"
                )
            pending.extend(_ast_nodes(definition["body"]))


def typecheck_repl_expression(
    line: str, module: LoadedModule, captured: CapturedRun | None = None
) -> tuple[TypedExpr, dict[str, TypeRef], dict[str, TypeRef]]:
    """Parse, elaborate, normalize, and typecheck one expression without lowering it."""

    parsed = read_sexpr_text(line, source_path="<repl>")
    if len(parsed.items) != 1:
        raise ReplRefusal("repl_expression_arity", "enter exactly one expression")
    datum = parsed.items[0]
    node = syntax.SyntaxNode(datum, datum.span, "<repl>", ("repl",))
    stage3, context = module.stage3, module.stage3.expression_context
    visible = visible_bindings(captured) if captured is not None else {}
    captured_types = binding_type_refs(module, visible)
    values = dict(captured_types)
    externs = stage3.extern_environment.bindings_by_name
    lexical_names = frozenset(values) - frozenset(externs)
    for name, binding in externs.items():
        values[name] = PrimitiveTypeRef("Provider" if isinstance(binding, ProviderExtern) else "Prompt")
    w3 = syntax.target_dsl_supports_local_hook_inference(module.typed_program.target)
    session = CompilerSession(closed_program=True)
    try:
        expr = expressions.elaborate_expression(
            node,
            bound_names=lexical_names if w3 else frozenset(values),
            extern_names=frozenset(externs) if w3 else frozenset(),
            procedure_names=frozenset(stage3.procedure_catalog.signatures_by_name),
            function_names=frozenset(context.function_catalog.signatures_by_name) if context else frozenset(),
            function_name_resolver=context.function_name_resolver if context else None,
            procedure_name_resolver=context.procedure_name_resolver if context else None,
            workflow_name_resolver=context.workflow_name_resolver if context else None,
            target_dsl_version=module.typed_program.target,
            prompt_catalog=stage3.prompt_catalog,
            session_state=session.elaboration,
        )
    except LispFrontendCompileError as exc:
        if context is None and any(d.code in {"procedure_call_unknown", "function_call_unknown"}
                                   for d in exc.diagnostics):
            raise ReplRefusal("repl_module_context_missing", "module calls require compiler context") from exc
        raise
    if context is None:
        from .expression_traversal import walk_expr
        if any(isinstance(child, (expressions.ProcedureCallExpr,
                                 expressions.FunctionCallExpr, expressions.CallExpr))
               for child in walk_expr(expr)):
            raise ReplRefusal("repl_module_context_missing", "module calls require compiler context")
    elif syntax.target_dsl_supports_pure_call_composition(module.typed_program.target):
        expr = functions.normalize_function_calls(
            expr, typed_functions_by_name=context.typed_functions_by_name,
            target_dsl_version=module.typed_program.target,
        )
    typed = typecheck_expression(
        expr, type_env=module.type_env, value_env=values,
        workflow_catalog=stage3.workflow_catalog,
        procedure_catalog=stage3.procedure_catalog,
        function_catalog=context.function_catalog if context else None,
        extern_environment=stage3.extern_environment,
        command_boundary_environment=stage3.command_boundary_environment,
        prompt_catalog=stage3.prompt_catalog,
        procedure_effects_by_name={name: proc.transitive_effect_summary
                                   for name, proc in module.typed_program.procedures.items()},
        workflow_effects_by_name={name: workflow.effect_summary
                                  for name, workflow in module.typed_program.workflows.items()},
        compiler_session=session,
    )

    return typed, captured_types, values


def evaluate_repl_expression(
    line: str, module: LoadedModule, captured: CapturedRun
) -> tuple[EvaluatedValue, TypedExpr]:
    typed, captured_types, values = typecheck_repl_expression(line, module, captured)
    if typed.effect_summary.transitive_effects:
        raise ReplRefusal("repl_effect_refused", "REPL expressions must be pure")
    entry, builder = module.typed_program.entry, module.builder
    owner = module.build.program.tree["entry"]
    expression_owner = replace(entry, typed_body=typed, signature=WorkflowSignature(
        name=entry.definition.name, params=tuple(captured_types.items()),
        return_type_ref=typed.type_ref, span=typed.span, form_path=typed.form_path,
    ))
    d = builder.definition_context(
        canonical=owner, owner=entry.definition.name, source_program=module.typed_program,
        type_env=module.type_env, node=typed, params=entry.definition.params,
        callable_def=expression_owner,
    )
    d.names.update({name: name for name in visible_bindings(captured)})
    normalized, children = builder._prepare_command_owner(
        expression_owner, module.typed_program, d, type_env=module.type_env, value_env=values,
    )
    verify_requests = builder._install_prepared_requests(normalized, d, children)
    builder._prepare_computed_capture_requests(normalized, d, module.typed_program)
    body = builder.body(normalized, d, values)
    verify_requests()
    lowered = body["value"] if body["k"] == "halt" else {"k": "block", "body": body}
    _require_pure_lowered(lowered, builder.definitions)
    program = replace(captured.authority.program, tree={
        **captured.authority.program.tree, "definitions": builder.definitions,
        "types": builder.nominal_types,
    })
    machine = _Machine(program, None, captured.authority.header["run_id"], None, None)
    activation = (owner,)
    try:
        value = evaluate_closed_value(
            lowered, captured.environment,
            evaluate_body=lambda body, scope: machine._body(body, scope, owner, activation, ()),
            evaluate_binding=lambda bound, scope: machine._bound(bound, scope, owner, activation, ()),
        )
    except EvaluatedValueError as exc:
        if exc.code == "closed_effect_handler_missing":
            raise ReplRefusal("repl_effect_refused", "REPL expressions must be pure") from exc
        raise
    return value, typed
