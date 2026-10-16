"""Read-only native declaration projections; no expression execution or inference."""
from __future__ import annotations

from dataclasses import replace

from orchestrator.workflow.dynamic.capture import visible_bindings
from ..diagnostics import LispFrontendCompileError
from ..reader import read_sexpr_text
from ..repl_expr import ReplRefusal
from ..repl_inspect import _Declaration, _contract_lines, checked_source_text
from ..sexpr import BoolAtom, FloatAtom, IntAtom, StringAtom, SymbolAtom
from ..syntax import ensure_syntax_datum, syntax_node_datum, syntax_resolved_name
from ..type_env import (
    PathTypeRef, RecordTypeRef, UnionTypeRef, prelude_type_names_for_target, render_type_ref,
)
from .repl_expr import runtime_kind


_HEADS = {"record": "defrecord", "union": "defunion", "enum": "defenum", "path": "defpath",
          "function": "define", "workflow": "defworkflow", "prompt": "defprompt"}
_PATH = ("workflow-lisp", "repl-inspect")


def visible_declarations(module) -> tuple[_Declaration, ...]:
    lowerer = module.build.lowerer
    entry = lowerer.graph.entry_module_name
    source = lowerer.graph.modules_by_name[entry]
    scope, env = lowerer.scopes[entry], lowerer.type_envs[entry]
    rows = {}

    def add(kind, canonical, name, owner, declared, contract, definition=None):
        key = kind, canonical
        if key not in rows:
            rows[key] = (_Declaration(kind, canonical, (), owner, declared, contract, definition), set())
        rows[key][1].add(name)

    candidates = set(prelude_type_names_for_target("3.0"))
    for form in source.syntax_module.forms:
        if syntax_resolved_name(form.items[0]) in {"defrecord", "defunion", "defenum", "defpath"}:
            name = syntax_resolved_name(form.items[1])
            candidates.update((name, f"{entry}/{name}", f"{entry}::{name}"))
    candidates.update(scope.type_bindings)
    candidates.update(scope.unqualified_type_bindings)
    candidates.update(binding.canonical_name for binding in scope.type_bindings.values())
    for name in sorted(candidates):
        try:
            ref = env.resolve_declared_type(name, span=source.syntax_module.span, form_path=_PATH)
        except LispFrontendCompileError:
            continue
        owner, declared = env.declaring_module(ref), env.declaring_name(ref)
        binding = scope.type_bindings.get(name) or scope.unqualified_type_bindings.get(name)
        if binding is None:
            binding = next((row for row in scope.type_bindings.values() if row.canonical_name == name), None)
        if owner is None and binding is not None:
            owner_env = lowerer.type_envs[binding.module_name]
            owner_ref = owner_env.resolve_declared_type(binding.member_name, span=source.syntax_module.span, form_path=_PATH)
            owner, declared = owner_env.declaring_module(owner_ref), owner_env.declaring_name(owner_ref)
        kind = "builtin" if owner is None else (
            "record" if isinstance(ref, RecordTypeRef) else "union" if isinstance(ref, UnionTypeRef)
            else "path" if isinstance(ref, PathTypeRef) else "enum"
        )
        canonical = f"{owner}::{declared}" if owner else ref.name
        add(kind, canonical, name, owner, declared or ref.name, ref, getattr(ref, "definition", None))

    candidates = {code for code in lowerer.members if code.rpartition("::")[0] == entry}
    candidates.update(code.rpartition("::")[2] for code in tuple(candidates))
    for bindings in (scope.function_bindings, scope.workflow_bindings):
        candidates.update(bindings)
        candidates.update(binding.canonical_name for binding in bindings.values())
    for name in sorted(candidates):
        node = ensure_syntax_datum(SymbolAtom(name, source.syntax_module.span), module_path=entry, form_path=_PATH)
        canonical = lowerer.callable(node, entry)
        if canonical is None:
            continue
        params, _body, workflow, form = lowerer.members[canonical]
        owner, _, declared = canonical.rpartition("::")
        add("function" if workflow is None else "workflow", canonical, name, owner, declared,
            params if workflow is None else workflow, form)

    candidates = {syntax_resolved_name(form.items[1]) for form in source.syntax_module.forms
                  if syntax_resolved_name(form.items[0]) == "defprompt"}
    candidates.update(scope.prompt_bindings)
    candidates.update(binding.canonical_name for binding in scope.prompt_bindings.values())
    for name in sorted(candidates):
        canonical = f"{entry}::{name}"
        if canonical not in lowerer.prompts:
            canonical = scope.resolve_prompt_name(name, span=source.syntax_module.span, form_path=_PATH)
        selected = lowerer.prompts.get(canonical)
        if selected is not None:
            owner, prompt = selected
            add("prompt", canonical, name, owner, prompt.declaration.name, prompt, prompt.declaration)
    for name, extern in lowerer.externs.items():
        add("extern", name, name, entry, name, extern)
    return tuple(sorted((replace(row, names=tuple(sorted(names))) for row, names in rows.values()),
                        key=lambda row: (row.kind, row.names)))


def _matches(module, name):
    lowerer = module.build.lowerer
    scope = lowerer.scopes[lowerer.graph.entry_module_name]
    span = lowerer.graph.modules_by_name[scope.module_name].syntax_module.span
    for resolve in (scope.resolve_function_name, scope.resolve_workflow_name, scope.resolve_prompt_name):
        resolve(name, span=span, form_path=_PATH)
    rows = tuple(row for row in visible_declarations(module) if name in row.names)
    if not rows:
        raise ReplRefusal("repl_name_unknown", f"unknown visible module declaration {name!r}")
    return rows


def _form(module, row):
    if row.kind not in _HEADS:
        return None
    if row.kind in {"function", "workflow"}:
        return row.definition
    source = module.build.lowerer.graph.modules_by_name[row.module_name]
    forms = [form for form in source.syntax_module.forms
             if syntax_resolved_name(form.items[0]) == _HEADS[row.kind]
             and syntax_resolved_name(form.items[1]) == row.declared_name]
    if len(forms) != 1:
        return None
    form = forms[0]
    if row.definition is not None and (getattr(row.definition, "expansion_stack", ()) or row.definition.span != form.span):
        return None
    return form


def _heading(module, row):
    form = _form(module, row)
    location = "unavailable" if form is None else f"{form.span.start.path}:{form.span.start.line}:{form.span.start.column}"
    return f"{row.kind}: {', '.join(row.names)}\nmodule: {row.module_name or 'builtin'}\nsource: {location}"


def inspect_name(module, name):
    sections = []
    for row in _matches(module, name):
        if row.kind == "function":
            lines = ["type: Function", *(f"{param}: unavailable" for param in row.contract),
                     "returns: unavailable", "effects: unavailable"]
        elif row.kind == "workflow":
            workflow = row.contract
            env = module.build.lowerer.type_envs[row.module_name]
            def declared(name):
                return render_type_ref(env.resolve_type(name, span=workflow.span, form_path=_PATH))
            lines = ["type: Function", "basis: declared boundary schemas",
                     *(f"{param.name}: {declared(param.type_name)}" for param in workflow.params),
                     f"returns: {declared(workflow.return_type_name)}", "effects: unavailable"]
        else:
            lines = _contract_lines(row)
        sections.append(_heading(module, row) + "\n" + "\n".join(lines))
    return "\n\n".join(sections)


def browse_module(module):
    lowerer = module.build.lowerer
    scope = lowerer.scopes[lowerer.graph.entry_module_name]
    lines = [f"module: {scope.module_name}", "target: 3.0", f"entry: {module.build.entry_workflow}",
             "source: loaded snapshot", "inference: native function return types and effects unavailable"]
    lines.extend(f"snapshot: {path} {revision}" for path, revision in module.build.source_read_trace.revision_vector)
    lines.extend(f"import: {name} as {alias}" for alias, name in sorted(scope.alias_to_module.items()))
    lines.extend(f"{row.kind}: {', '.join(row.names)}" for row in visible_declarations(module))
    return "\n".join(lines)


def source_name(module, name):
    trace = module.build.source_read_trace
    sections, unavailable = [], []
    for row in _matches(module, name):
        try:
            form = _form(module, row)
            if form is None:
                raise ValueError("exact authored declaration unavailable")
            source = module.build.lowerer.graph.modules_by_name[row.module_name]
            datum = syntax_node_datum(form)
            atom = datum.items[1].items[0] if row.kind == "function" else datum.items[1]
            revision, text = checked_source_text(
                form, source.path, trace.raw_bytes_by_path.get(source.path),
                dict(trace.revision_vector).get(source.path), _HEADS[row.kind], row.declared_name,
                name_atom=atom,
            )
        except (ValueError, UnicodeError) as exc:
            unavailable.append(f"{row.kind} {row.canonical_name}: {exc}")
        else:
            sections.append(f"{_heading(module, row)}\nloaded snapshot: {revision}\n{text}")
    if unavailable:
        raise ReplRefusal("repl_source_unavailable", "; ".join(unavailable))
    return "\n\n".join(sections)


def type_query(line, module, captured=None):
    parsed = read_sexpr_text(line, source_path="<repl>")
    if len(parsed.items) != 1:
        raise ReplRefusal("repl_expression_arity", "enter exactly one expression")
    datum = parsed.items[0]
    if isinstance(datum, (BoolAtom, FloatAtom, IntAtom, StringAtom)):
        return f"type: {runtime_kind(datum.value)}\nbasis: literal kind"
    if isinstance(datum, SymbolAtom):
        visible = visible_bindings(captured) if captured is not None else {}
        if datum.value in visible:
            return f"type: {runtime_kind(visible[datum.value])}\nbasis: observed runtime kind"
        rows = tuple(row for row in visible_declarations(module) if datum.value in row.names)
        if any(row.kind in {"function", "workflow"} for row in rows):
            return "type: Function\nbasis: declared function; return and effect inference unavailable"
        raise ReplRefusal("name_unknown", f"{datum.value!r} is not a captured binding or visible function")
    raise ReplRefusal("repl_type_unavailable", "native type queries accept only literals, names and function references")
