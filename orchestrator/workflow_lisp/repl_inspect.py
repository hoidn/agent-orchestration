"""Read-only REPL projections of retained compiler declarations and source."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .diagnostics import LispFrontendCompileError
from .effects import render_effect_set
from .repl_expr import LoadedModule, ReplRefusal
from .syntax import SyntaxList, syntax_resolved_name, syntax_node_datum
from .type_env import (
    PathTypeRef, RecordTypeRef, UnionTypeRef,
    prelude_type_names_for_target, render_type_ref,
)
from .workflows import ProviderExtern


COVERAGE = "named types, functions, procedures, workflows, prompts and externs"
EXCLUSIONS = "macros, schemas, resources, transitions, operator documentation, applied generic type syntax as NAME, generated local definitions and specializations"
_TYPE_HEADS = {"record": "defrecord", "union": "defunion", "enum": "defenum", "path": "defpath"}
_HEADS = {**_TYPE_HEADS, "function": "defun", "procedure": "defproc", "workflow": "defworkflow", "prompt": "defprompt"}


@dataclass(frozen=True)
class _Declaration:
    kind: str
    canonical_name: str
    names: tuple[str, ...]
    module_name: str | None
    declared_name: str
    contract: object
    definition: object | None = None


def _context(module):
    context = module.stage3.expression_context
    if context is None or context.linked_module_graph is None or context.module_import_scope is None:
        raise ReplRefusal("repl_module_context_missing", "module inspection requires retained graph and import scope")
    return context


def visible_declarations(module: LoadedModule) -> tuple[_Declaration, ...]:
    """Project accepted spellings through existing namespace resolvers."""
    context = _context(module)
    scope, stage3, env = context.module_import_scope, module.stage3, module.type_env
    span, form_path = stage3.module.span, ("workflow-lisp", "repl-inspect")
    rows = {}

    def add(kind, canonical, name, owner, declared, contract, definition=None):
        key = kind, canonical
        if key not in rows:
            rows[key] = (_Declaration(kind, canonical, (), owner, declared, contract, definition), set())
        rows[key][1].add(name)

    candidates = set(prelude_type_names_for_target(module.typed_program.target))
    for definition in stage3.module.definitions:
        candidates.update((definition.name, f"{scope.module_name}/{definition.name}", f"{scope.module_name}::{definition.name}"))
    candidates.update(scope.type_bindings)
    candidates.update(scope.unqualified_type_bindings)
    candidates.update(binding.canonical_name for binding in scope.type_bindings.values())
    for name in sorted(candidates):
        try:
            ref = env.resolve_declared_type(name, span=span, form_path=form_path)
        except LispFrontendCompileError:
            continue
        owner, declared = env.declaring_module(ref), env.declaring_name(ref)
        binding = scope.type_bindings.get(name) or scope.unqualified_type_bindings.get(name)
        if binding is None:
            binding = next((row for row in scope.type_bindings.values() if row.canonical_name == name), None)
        if owner is None and binding is not None:
            owner_env = module.typed_program.module_type_envs.get(binding.module_name)
            if owner_env is None:
                raise ReplRefusal("repl_module_context_missing", f"type owner unavailable: {name}")
            owner_ref = owner_env.resolve_declared_type(binding.member_name, span=span, form_path=form_path)
            owner, declared = owner_env.declaring_module(owner_ref), owner_env.declaring_name(owner_ref)
        kind = "builtin" if owner is None else (
            "record" if isinstance(ref, RecordTypeRef) else "union" if isinstance(ref, UnionTypeRef)
            else "path" if isinstance(ref, PathTypeRef) else "enum"
        )
        canonical = f"{owner}::{declared}" if owner else ref.name
        add(kind, canonical, name, owner, declared or ref.name, ref, getattr(ref, "definition", None))

    catalogs = (
        ("function", context.function_catalog, context.function_name_resolver, context.typed_functions_by_name),
        ("procedure", stage3.procedure_catalog, context.procedure_name_resolver, module.typed_program.procedures),
        ("workflow", stage3.workflow_catalog, context.workflow_name_resolver, module.typed_program.workflows),
    )
    for kind, catalog, resolve, typed_defs in catalogs:
        candidates = set(catalog.signatures_by_name)
        for definition in catalog.definitions_by_name.values():
            if len(definition.form_path) >= 2 and definition.form_path[-2] == _HEADS[kind]:
                candidates.add(definition.form_path[-1])
        for name in sorted(candidates):
            canonical = resolve(name, span, form_path)
            signature = catalog.signatures_by_name.get(canonical)
            typed = typed_defs.get(canonical)
            definition = catalog.definitions_by_name.get(canonical) or getattr(typed, "definition", None)
            if signature is None:
                continue
            if getattr(typed, "specialization", None) is not None or getattr(definition, "generated_local_procedure", None) is not None:
                continue
            if definition is not None and (len(definition.form_path) < 2 or definition.form_path[-2] != _HEADS[kind]):
                continue
            bindings = getattr(scope, f"{kind}_bindings")
            binding = bindings.get(name) or next((row for row in bindings.values() if row.canonical_name == canonical), None)
            owner = binding.module_name if binding else scope.module_name
            declared = binding.member_name if binding else (definition.form_path[-1] if definition else signature.name)
            add(kind, canonical, name, owner, declared, (signature, typed), definition)

    if stage3.prompt_catalog is None:
        raise ReplRefusal("repl_module_context_missing", "prompt catalog unavailable")
    for name in sorted(stage3.prompt_catalog.definitions_by_name):
        prompt = stage3.prompt_catalog.resolve(name)
        binding = scope.prompt_bindings.get(name)
        owner = binding.module_name if binding else next((row.module_name for row in scope.prompt_bindings.values() if row.canonical_name == prompt.qualified_name), scope.module_name)
        add("prompt", prompt.qualified_name, name, owner, prompt.declaration.name, prompt, prompt.declaration)
    for name, binding in stage3.extern_environment.bindings_by_name.items():
        add("extern", name, name, scope.module_name, name, binding)
    return tuple(sorted((
        _Declaration(row.kind, row.canonical_name, tuple(sorted(names)), row.module_name,
                     row.declared_name, row.contract, row.definition)
        for row, names in rows.values()
    ), key=lambda row: (row.kind, row.names)))


def _matches(module, name):
    # Resolve the query as well so same-namespace compiler refusals stay intact.
    context = _context(module)
    span, path = module.stage3.module.span, ("workflow-lisp", "repl-inspect")
    for resolve in (context.function_name_resolver, context.procedure_name_resolver, context.workflow_name_resolver):
        resolve(name, span, path)
    rows = tuple(row for row in visible_declarations(module) if name in row.names)
    if not rows:
        raise ReplRefusal("repl_name_unknown", f"unknown module name {name!r}; coverage: {COVERAGE}; use :type or :bindings for values")
    return rows


def _authored_form(module, row):
    source = _context(module).linked_module_graph.modules_by_name.get(row.module_name)
    if source is None or row.kind not in _HEADS:
        return None
    matches = []
    for form in source.syntax_module.forms:
        datum = syntax_node_datum(form)
        if not isinstance(datum, SyntaxList) or len(datum.items) < 2:
            continue
        if syntax_resolved_name(datum.items[0]) == _HEADS[row.kind] and syntax_resolved_name(datum.items[1]) == row.declared_name:
            matches.append(form)
    if len(matches) != 1:
        return None
    form = matches[0]
    if row.definition is not None and (getattr(row.definition, "expansion_stack", ()) or row.definition.span != form.span):
        return None
    return form


def _heading(module, row):
    form = _authored_form(module, row)
    location = "unavailable" if form is None else f"{form.span.start.path}:{form.span.start.line}:{form.span.start.column}"
    return f"{row.kind}: {', '.join(row.names)}\nmodule: {row.module_name or 'builtin'}\nsource: {location}"


def _contract_lines(row):
    value = row.contract
    if row.kind in {"record", "builtin"} and isinstance(value, RecordTypeRef):
        return [f"{name}: {render_type_ref(ref)}" for name, ref in value.field_types.items()]
    if row.kind in {"union", "builtin"} and isinstance(value, UnionTypeRef):
        lines = [f"type parameters: {', '.join(value.definition.type_params)}"] if value.definition.type_params else []
        for variant, fields in value.variant_field_types.items():
            lines.append(f"{variant}: ({', '.join(f'{name}: {render_type_ref(ref)}' for name, ref in fields.items())})")
        return lines
    if isinstance(value, PathTypeRef):
        definition = value.definition
        return [f"kind: {definition.kind}", f"under: {definition.under}", f"must-exist: {str(definition.must_exist).lower()}"]
    if row.kind == "enum":
        return [f"members: {', '.join(value.allowed_values)}"]
    if row.kind == "builtin":
        return [f"type: {render_type_ref(value)}"]
    if row.kind in {"function", "procedure", "workflow"}:
        signature, typed = value
        lines = [f"{name}: {render_type_ref(ref)}" for name, ref in signature.params]
        lines.append(f"returns: {render_type_ref(signature.return_type_ref)}")
        effect = getattr(typed, "transitive_effect_summary", None) or getattr(typed, "effect_summary", None)
        if effect is None and row.kind == "function" and typed is not None:
            effect = typed.typed_body.effect_summary
        lines.append(f"effects: {render_effect_set(effect.transitive_effects) if effect is not None else 'unavailable'}")
        return lines
    if row.kind == "prompt":
        lines = []
        for slot in value.slots:
            declaration = slot.declaration
            refinement = render_type_ref(slot.refinement_type_ref) if slot.refinement_type_ref is not None else "none"
            lines.append(f"{declaration.name}: {declaration.kind.value}; refinement: {refinement}; output-role: {declaration.output_role.value}")
        return [*lines, f"returns: {render_type_ref(value.return_type_ref)}"]
    return [f"type: {'Provider' if isinstance(value, ProviderExtern) else 'Prompt'}", "contract: unavailable"]


def inspect_name(module: LoadedModule, name: str) -> str:
    return "\n\n".join(_heading(module, row) + "\n" + "\n".join(_contract_lines(row)) for row in _matches(module, name))


def browse_module(module: LoadedModule) -> str:
    context = _context(module)
    lines = [f"module: {context.module_import_scope.module_name}", f"target: {module.typed_program.target}",
             f"entry: {module.build.entry_workflow}", f"source: {_snapshot_label(module)}",
             f"coverage: {COVERAGE}", f"excluded: {EXCLUSIONS}"]
    lines.extend(f"snapshot: {path} {revision}" for path, revision in module.source_revisions)
    lines.extend(f"import: {name} as {alias}" for alias, name in sorted(context.module_import_scope.alias_to_module.items()))
    lines.extend(f"{row.kind}: {', '.join(row.names)}" for row in visible_declarations(module))
    return "\n".join(lines)


def _snapshot_label(module):
    return "reconstructed module source" if module.source_origin == "reconstructed" else "loaded snapshot"


def _source_text(module, row):
    form = _authored_form(module, row)
    if form is None:
        raise ValueError("exact authored declaration unavailable")
    source = _context(module).linked_module_graph.modules_by_name[row.module_name]
    span = form.span
    if span.start.path != str(source.path) or span.end.path != str(source.path):
        raise ValueError("source path identity mismatch")
    payload = module.source_snapshots.get(source.path)
    revision = dict(module.source_revisions).get(source.path)
    if payload is None or revision is None:
        raise ValueError("snapshot unavailable")
    if f"sha256:{hashlib.sha256(payload).hexdigest()}" != revision:
        raise ValueError("snapshot revision mismatch")
    text = payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if not 0 <= span.start.offset < span.end.offset <= len(text):
        raise ValueError("invalid source span")
    if span != syntax_node_datum(form).span:
        raise ValueError("declaration span identity mismatch")
    for atom, expected in zip(syntax_node_datum(form).items[:2], (_HEADS[row.kind], row.declared_name)):
        if atom.span.start.path != str(source.path) or atom.span.end.path != str(source.path):
            raise ValueError("declaration identity path mismatch")
        if not span.start.offset <= atom.span.start.offset < atom.span.end.offset <= span.end.offset:
            raise ValueError("declaration identity outside source span")
        if text[atom.span.start.offset:atom.span.end.offset] != expected:
            raise ValueError("snapshot declaration identity mismatch")
    if text[span.start.offset] != "(" or text[span.end.offset - 1] != ")":
        raise ValueError("source does not contain a complete declaration")
    return revision, text[span.start.offset:span.end.offset]


def source_name(module: LoadedModule, name: str) -> str:
    sections, unavailable = [], []
    for row in _matches(module, name):
        try:
            revision, text = _source_text(module, row)
        except (ValueError, UnicodeError) as exc:
            unavailable.append(f"{row.kind} {row.canonical_name}: {exc}")
        else:
            sections.append(f"{_heading(module, row)}\n{_snapshot_label(module)}: {revision}\n{text}")
    if unavailable:
        raise ReplRefusal("repl_source_unavailable", "; ".join(unavailable))
    return "\n\n".join(sections)
