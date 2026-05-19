"""Frontend-only hygienic user macro expansion for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .syntax import (
    ExpansionFrame,
    ExpansionStack,
    SyntaxBool,
    SyntaxDatum,
    SyntaxIdentifier,
    SyntaxInt,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    WorkflowLispSyntaxModule,
    clone_caller_syntax,
    clone_template_syntax,
    ensure_syntax_datum,
    introduced_identifier,
    syntax_display_name,
    syntax_expansion_stack,
    syntax_head_name,
    syntax_node_datum,
    top_level_form_path,
)

_RESERVED_MACRO_NAMES = frozenset(
    {
        "workflow-lisp",
        "defenum",
        "defpath",
        "defrecord",
        "defunion",
        "defworkflow",
        "defmacro",
        "record",
        "let*",
        "match",
        "call",
        "provider-result",
        "command-result",
        "with-phase",
        "phase-target",
    }
)

_ALLOWED_TOP_LEVEL_HEADS = frozenset(
    {
        "defenum",
        "defpath",
        "defrecord",
        "defunion",
        "defworkflow",
    }
)


@dataclass(frozen=True)
class MacroDef:
    """One same-file user macro definition."""

    name: str
    params: tuple[str, ...]
    rest_param: str | None
    body_param: str | None
    template: SyntaxDatum
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class MacroCatalog:
    """One same-file macro catalog."""

    definitions_by_name: Mapping[str, MacroDef]


@dataclass
class _ExpansionAllocator:
    next_id: int = 1

    def allocate(self) -> str:
        expansion_id = f"m{self.next_id:04d}"
        self.next_id += 1
        return expansion_id


def collect_macro_catalog(module_syntax: WorkflowLispSyntaxModule) -> MacroCatalog:
    """Collect all same-file top-level `defmacro` definitions before elaboration."""

    definitions_by_name: dict[str, MacroDef] = {}
    diagnostics: list[LispFrontendDiagnostic] = []
    for form in module_syntax.forms:
        datum = syntax_node_datum(form)
        if syntax_head_name(datum) != "defmacro":
            continue
        try:
            macro_def = _elaborate_macro_definition(form, datum)
        except LispFrontendCompileError as error:
            diagnostics.extend(error.diagnostics)
            continue
        if macro_def.name in _RESERVED_MACRO_NAMES:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="macro_reserved_name",
                    message=f"`defmacro` may not bind reserved head `{macro_def.name}`",
                    span=macro_def.span,
                    form_path=macro_def.form_path,
                    expansion_stack=syntax_expansion_stack(datum),
                )
            )
            continue
        if macro_def.name in definitions_by_name:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="macro_reserved_name",
                    message=f"duplicate macro definition `{macro_def.name}`",
                    span=macro_def.span,
                    form_path=macro_def.form_path,
                    expansion_stack=syntax_expansion_stack(datum),
                )
            )
            continue
        definitions_by_name[macro_def.name] = macro_def
    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return MacroCatalog(definitions_by_name=definitions_by_name)


def expand_module_forms(
    module_syntax: WorkflowLispSyntaxModule,
    *,
    catalog: MacroCatalog,
) -> WorkflowLispSyntaxModule:
    """Expand all non-`defmacro` forms recursively through the macro catalog."""

    allocator = _ExpansionAllocator()
    expanded_forms: list[SyntaxNode] = []
    for form in module_syntax.forms:
        datum = syntax_node_datum(form)
        if syntax_head_name(datum) == "defmacro":
            continue
        expanded = _expand_datum(datum, catalog=catalog, allocator=allocator, active_stack=())
        _validate_top_level_form(expanded)
        expanded_forms.append(
            SyntaxNode(
                datum=expanded,
                span=expanded.span,
                module_path=module_syntax.module_path,
                form_path=top_level_form_path(expanded),
            )
        )
    return WorkflowLispSyntaxModule(
        language_version=module_syntax.language_version,
        target_dsl_version=module_syntax.target_dsl_version,
        forms=tuple(expanded_forms),
        span=module_syntax.span,
        module_path=module_syntax.module_path,
    )


def _elaborate_macro_definition(form: SyntaxNode, datum: SyntaxDatum) -> MacroDef:
    if not isinstance(datum, SyntaxList) or len(datum.items) != 4:
        _raise_macro_error(
            code="frontend_parse_error",
            message="`defmacro` requires a name, param list, and one template form",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=syntax_expansion_stack(datum),
        )
    name_node = datum.items[1]
    if not isinstance(name_node, SyntaxIdentifier):
        _raise_macro_error(
            code="frontend_parse_error",
            message="macro name must be a symbol",
            span=name_node.span,
            form_path=form.form_path,
            expansion_stack=syntax_expansion_stack(datum),
        )
    raw_params = datum.items[2]
    if not isinstance(raw_params, SyntaxList):
        _raise_macro_error(
            code="frontend_parse_error",
            message="macro params must be a list",
            span=raw_params.span,
            form_path=form.form_path,
            expansion_stack=syntax_expansion_stack(datum),
        )
    params, rest_param, body_param = _parse_macro_params(raw_params, form.form_path)
    return MacroDef(
        name=name_node.resolved_name,
        params=params,
        rest_param=rest_param,
        body_param=body_param,
        template=datum.items[3],
        span=form.span,
        form_path=form.form_path,
    )


def _parse_macro_params(
    raw_params: SyntaxList,
    form_path: tuple[str, ...],
) -> tuple[tuple[str, ...], str | None, str | None]:
    params: list[str] = []
    rest_param: str | None = None
    body_param: str | None = None
    items = list(raw_params.items)
    index = 0
    while index < len(items):
        item = items[index]
        if not isinstance(item, SyntaxIdentifier):
            _raise_macro_error(
                code="frontend_parse_error",
                message="macro params must be symbols",
                span=item.span,
                form_path=form_path,
                expansion_stack=syntax_expansion_stack(raw_params),
            )
        if item.resolved_name in {"&rest", "&body"}:
            if index != len(items) - 2:
                _raise_macro_error(
                    code="frontend_parse_error",
                    message="`&rest` and `&body` must be the final param marker",
                    span=item.span,
                    form_path=form_path,
                    expansion_stack=syntax_expansion_stack(raw_params),
                )
            capture = items[index + 1]
            if not isinstance(capture, SyntaxIdentifier):
                _raise_macro_error(
                    code="frontend_parse_error",
                    message="rest/body capture names must be symbols",
                    span=capture.span,
                    form_path=form_path,
                    expansion_stack=syntax_expansion_stack(raw_params),
                )
            if item.resolved_name == "&rest":
                rest_param = capture.resolved_name
            else:
                body_param = capture.resolved_name
            break
        params.append(item.resolved_name)
        index += 1
    return tuple(params), rest_param, body_param


def _expand_datum(
    datum: SyntaxDatum,
    *,
    catalog: MacroCatalog,
    allocator: _ExpansionAllocator,
    active_stack: ExpansionStack,
) -> SyntaxDatum:
    if not isinstance(datum, SyntaxList):
        return datum
    head_name = syntax_head_name(datum)
    if head_name and head_name in catalog.definitions_by_name:
        return _expand_macro_call(
            datum,
            macro_def=catalog.definitions_by_name[head_name],
            catalog=catalog,
            allocator=allocator,
            active_stack=active_stack,
        )
    return replace(
        datum,
        items=tuple(
            _expand_datum(item, catalog=catalog, allocator=allocator, active_stack=active_stack)
            for item in datum.items
        ),
    )


def _expand_macro_call(
    call: SyntaxList,
    *,
    macro_def: MacroDef,
    catalog: MacroCatalog,
    allocator: _ExpansionAllocator,
    active_stack: ExpansionStack,
) -> SyntaxDatum:
    for frame in active_stack:
        if frame.macro_name == macro_def.name and frame.call_span == call.span:
            chain = " -> ".join(active.macro_name for active in active_stack + (frame,))
            _raise_macro_error(
                code="macro_expansion_cycle",
                message=f"macro expansion cycle detected while expanding `{macro_def.name}` ({chain})",
                span=call.span,
                form_path=call.form_path,
                expansion_stack=active_stack,
            )
    expansion_id = allocator.allocate()
    frame = ExpansionFrame(
        macro_name=macro_def.name,
        expansion_id=expansion_id,
        call_span=call.span,
        definition_span=macro_def.span,
        template_path=macro_def.form_path,
    )
    bindings = _bind_macro_arguments(call, macro_def=macro_def, active_stack=active_stack)
    instantiated = _instantiate_template(
        macro_def.template,
        bindings=bindings,
        frame=frame,
        macro_def=macro_def,
    )
    hygienic = _apply_hygiene(
        instantiated,
        macro_name=macro_def.name,
        expansion_id=expansion_id,
    )
    expanded = _expand_datum(
        hygienic,
        catalog=catalog,
        allocator=allocator,
        active_stack=active_stack + (frame,),
    )
    return expanded


def _bind_macro_arguments(
    call: SyntaxList,
    *,
    macro_def: MacroDef,
    active_stack: ExpansionStack,
) -> Mapping[str, SyntaxDatum | tuple[SyntaxDatum, ...]]:
    args = call.items[1:]
    minimum = len(macro_def.params)
    if macro_def.rest_param is None and macro_def.body_param is None and len(args) != minimum:
        _raise_macro_error(
            code="macro_arity_error",
            message=f"macro `{macro_def.name}` expected {minimum} args but got {len(args)}",
            span=call.span,
            form_path=call.form_path,
            expansion_stack=active_stack,
        )
    if (macro_def.rest_param or macro_def.body_param) is not None and len(args) < minimum:
        _raise_macro_error(
            code="macro_arity_error",
            message=f"macro `{macro_def.name}` expected at least {minimum} args but got {len(args)}",
            span=call.span,
            form_path=call.form_path,
            expansion_stack=active_stack,
        )
    bindings: dict[str, SyntaxDatum | tuple[SyntaxDatum, ...]] = {}
    for name, value in zip(macro_def.params, args, strict=False):
        bindings[name] = value
    remaining = tuple(args[minimum:])
    if macro_def.rest_param is not None:
        bindings[macro_def.rest_param] = remaining
    if macro_def.body_param is not None:
        bindings[macro_def.body_param] = remaining
    return bindings


def _instantiate_template(
    template: SyntaxDatum,
    *,
    bindings: Mapping[str, SyntaxDatum | tuple[SyntaxDatum, ...]],
    frame: ExpansionFrame,
    macro_def: MacroDef,
    allow_splice: bool = False,
) -> SyntaxDatum:
    if isinstance(template, SyntaxIdentifier):
        bound = bindings.get(template.resolved_name)
        if bound is None:
            return clone_template_syntax(
                template,
                frame=frame,
                introduced_by_expansion_id=frame.expansion_id,
            )
        if isinstance(bound, tuple):
            _raise_macro_error(
                code="macro_emits_invalid_ast",
                message=f"macro `{macro_def.name}` may splice `{template.display_name}` only inside a list",
                span=template.span,
                form_path=template.form_path,
                expansion_stack=(frame,),
            )
        return clone_template_syntax(bound, frame=frame)
    if isinstance(template, (SyntaxKeyword, SyntaxString, SyntaxInt, SyntaxBool)):
        return clone_template_syntax(template, frame=frame)
    if not isinstance(template, SyntaxList):
        raise TypeError(f"unsupported macro template node: {type(template)!r}")
    if _is_splice_form(template):
        if not allow_splice:
            _raise_macro_error(
                code="macro_emits_invalid_ast",
                message=f"macro `{macro_def.name}` may use `(splice ...)` only inside a list template",
                span=template.span,
                form_path=template.form_path,
                expansion_stack=(frame,),
            )
        raise AssertionError("splice handling must be intercepted by parent list")
    items: list[SyntaxDatum] = []
    for item in template.items:
        if _is_splice_form(item):
            splice_name = _splice_target_name(item)
            bound = bindings.get(splice_name)
            if not isinstance(bound, tuple):
                _raise_macro_error(
                    code="macro_emits_invalid_ast",
                    message=f"macro `{macro_def.name}` may splice only list captures, got `{splice_name}`",
                    span=item.span,
                    form_path=item.form_path,
                    expansion_stack=(frame,),
                )
            items.extend(clone_template_syntax(argument, frame=frame) for argument in bound)
            continue
        items.append(
            _instantiate_template(
                item,
                bindings=bindings,
                frame=frame,
                macro_def=macro_def,
                allow_splice=True,
            )
        )
    return replace(
        template,
        items=tuple(items),
        expansion_stack=template.expansion_stack + (frame,),
    )


def _apply_hygiene(
    datum: SyntaxDatum,
    *,
    macro_name: str,
    expansion_id: str,
    env: Mapping[str, str] | None = None,
) -> SyntaxDatum:
    active_env = dict(env or {})
    if isinstance(datum, SyntaxIdentifier):
        renamed = active_env.get(datum.resolved_name)
        if datum.introduced_by_expansion_id == expansion_id and renamed is not None:
            return replace(datum, resolved_name=renamed)
        return datum
    if not isinstance(datum, SyntaxList):
        return datum
    head_name = syntax_head_name(datum)
    if head_name == "let*":
        return _hygienic_letstar(datum, macro_name=macro_name, expansion_id=expansion_id, env=active_env)
    if head_name == "match":
        return _hygienic_match(datum, macro_name=macro_name, expansion_id=expansion_id, env=active_env)
    if head_name == "defworkflow":
        return _hygienic_defworkflow(datum, macro_name=macro_name, expansion_id=expansion_id, env=active_env)
    if head_name == "record":
        return _replace_list_item_range(
            datum,
            {
                index: _apply_hygiene(item, macro_name=macro_name, expansion_id=expansion_id, env=active_env)
                for index, item in enumerate(datum.items)
                if index == 0 or index >= 3 and index % 2 == 1
            },
        )
    if head_name == "call":
        return _replace_list_item_range(
            datum,
            {
                index: _apply_hygiene(item, macro_name=macro_name, expansion_id=expansion_id, env=active_env)
                for index, item in enumerate(datum.items)
                if index == 0 or index >= 3 and index % 2 == 1
            },
        )
    if head_name == "provider-result":
        updated = list(datum.items)
        for index in (1, 3):
            if index < len(updated):
                updated[index] = _apply_hygiene(
                    updated[index],
                    macro_name=macro_name,
                    expansion_id=expansion_id,
                    env=active_env,
                )
        if len(updated) > 5 and isinstance(updated[5], SyntaxList):
            updated[5] = replace(
                updated[5],
                items=tuple(
                    _apply_hygiene(item, macro_name=macro_name, expansion_id=expansion_id, env=active_env)
                    for item in updated[5].items
                ),
            )
        return replace(datum, items=tuple(updated))
    if head_name == "command-result":
        updated = list(datum.items)
        if len(updated) > 3 and isinstance(updated[3], SyntaxList):
            updated[3] = replace(
                updated[3],
                items=tuple(
                    _apply_hygiene(item, macro_name=macro_name, expansion_id=expansion_id, env=active_env)
                    for item in updated[3].items
                ),
            )
        return replace(datum, items=tuple(updated))
    if head_name == "with-phase":
        updated = list(datum.items)
        if len(updated) > 1:
            updated[1] = _apply_hygiene(updated[1], macro_name=macro_name, expansion_id=expansion_id, env=active_env)
        if len(updated) > 3:
            updated[3] = _apply_hygiene(updated[3], macro_name=macro_name, expansion_id=expansion_id, env=active_env)
        return replace(datum, items=tuple(updated))
    if head_name == "phase-target":
        return datum
    return replace(
        datum,
        items=tuple(
            item if index == 0 else _apply_hygiene(item, macro_name=macro_name, expansion_id=expansion_id, env=active_env)
            for index, item in enumerate(datum.items)
        ),
    )


def _hygienic_letstar(
    datum: SyntaxList,
    *,
    macro_name: str,
    expansion_id: str,
    env: Mapping[str, str],
) -> SyntaxDatum:
    if len(datum.items) != 3:
        return datum
    updated = list(datum.items)
    bindings_node = datum.items[1]
    if not isinstance(bindings_node, SyntaxList):
        return datum
    local_env = dict(env)
    new_bindings: list[SyntaxDatum] = []
    for raw_binding in bindings_node.items:
        if not isinstance(raw_binding, SyntaxList) or len(raw_binding.items) != 2:
            new_bindings.append(_apply_hygiene(raw_binding, macro_name=macro_name, expansion_id=expansion_id, env=local_env))
            continue
        name_node = raw_binding.items[0]
        value_node = _apply_hygiene(
            raw_binding.items[1],
            macro_name=macro_name,
            expansion_id=expansion_id,
            env=local_env,
        )
        if isinstance(name_node, SyntaxIdentifier) and name_node.introduced_by_expansion_id == expansion_id:
            renamed = introduced_identifier(name_node, macro_name=macro_name, expansion_id=expansion_id)
            local_env[name_node.resolved_name] = renamed.resolved_name
            name_node = renamed
        new_bindings.append(replace(raw_binding, items=(name_node, value_node)))
    updated[1] = replace(bindings_node, items=tuple(new_bindings))
    updated[2] = _apply_hygiene(
        datum.items[2],
        macro_name=macro_name,
        expansion_id=expansion_id,
        env=local_env,
    )
    return replace(datum, items=tuple(updated))


def _hygienic_match(
    datum: SyntaxList,
    *,
    macro_name: str,
    expansion_id: str,
    env: Mapping[str, str],
) -> SyntaxDatum:
    updated = list(datum.items)
    updated[1] = _apply_hygiene(
        datum.items[1],
        macro_name=macro_name,
        expansion_id=expansion_id,
        env=env,
    )
    new_arms: list[SyntaxDatum] = []
    for raw_arm in datum.items[2:]:
        if not isinstance(raw_arm, SyntaxList) or len(raw_arm.items) != 2:
            new_arms.append(_apply_hygiene(raw_arm, macro_name=macro_name, expansion_id=expansion_id, env=env))
            continue
        pattern = raw_arm.items[0]
        if not isinstance(pattern, SyntaxList) or len(pattern.items) != 2:
            new_arms.append(_apply_hygiene(raw_arm, macro_name=macro_name, expansion_id=expansion_id, env=env))
            continue
        binding_env = dict(env)
        binder = pattern.items[1]
        if isinstance(binder, SyntaxIdentifier) and binder.introduced_by_expansion_id == expansion_id:
            renamed = introduced_identifier(binder, macro_name=macro_name, expansion_id=expansion_id)
            binding_env[binder.resolved_name] = renamed.resolved_name
            pattern = replace(pattern, items=(pattern.items[0], renamed))
        body = _apply_hygiene(
            raw_arm.items[1],
            macro_name=macro_name,
            expansion_id=expansion_id,
            env=binding_env,
        )
        new_arms.append(replace(raw_arm, items=(pattern, body)))
    updated[2:] = new_arms
    return replace(datum, items=tuple(updated))


def _hygienic_defworkflow(
    datum: SyntaxList,
    *,
    macro_name: str,
    expansion_id: str,
    env: Mapping[str, str],
) -> SyntaxDatum:
    updated = list(datum.items)
    params = datum.items[2]
    if not isinstance(params, SyntaxList):
        return datum
    binding_env = dict(env)
    new_params: list[SyntaxDatum] = []
    for raw_param in params.items:
        if not isinstance(raw_param, SyntaxList) or len(raw_param.items) != 2:
            new_params.append(_apply_hygiene(raw_param, macro_name=macro_name, expansion_id=expansion_id, env=binding_env))
            continue
        name_node = raw_param.items[0]
        if isinstance(name_node, SyntaxIdentifier) and name_node.introduced_by_expansion_id == expansion_id:
            renamed = introduced_identifier(name_node, macro_name=macro_name, expansion_id=expansion_id)
            binding_env[name_node.resolved_name] = renamed.resolved_name
            name_node = renamed
        new_params.append(replace(raw_param, items=(name_node, raw_param.items[1])))
    updated[2] = replace(params, items=tuple(new_params))
    updated[5] = _apply_hygiene(
        datum.items[5],
        macro_name=macro_name,
        expansion_id=expansion_id,
        env=binding_env,
    )
    return replace(datum, items=tuple(updated))


def _replace_list_item_range(datum: SyntaxList, replacements: Mapping[int, SyntaxDatum]) -> SyntaxList:
    items = list(datum.items)
    for index, value in replacements.items():
        items[index] = value
    return replace(datum, items=tuple(items))


def _validate_top_level_form(datum: SyntaxDatum) -> None:
    if not isinstance(datum, SyntaxList) or not datum.items:
        _raise_macro_error(
            code="macro_emits_invalid_ast",
            message="macro expansion must produce a non-empty top-level form",
            span=datum.span,
            form_path=top_level_form_path(datum),
            expansion_stack=syntax_expansion_stack(datum),
        )
    head = datum.items[0]
    if not isinstance(head, SyntaxIdentifier):
        _raise_macro_error(
            code="macro_emits_invalid_ast",
            message="macro expansion must produce a top-level form headed by a symbol",
            span=datum.span,
            form_path=top_level_form_path(datum),
            expansion_stack=syntax_expansion_stack(datum),
        )
    if head.resolved_name == "defmacro":
        _raise_macro_error(
            code="macro_emits_invalid_ast",
            message="macro expansion may not emit a top-level `defmacro` form",
            span=datum.span,
            form_path=top_level_form_path(datum),
            expansion_stack=syntax_expansion_stack(datum),
        )
    if head.resolved_name not in _ALLOWED_TOP_LEVEL_HEADS:
        _raise_macro_error(
            code="macro_emits_invalid_ast",
            message=(
                "macro expansion must produce a top-level frontend definition form, "
                f"got `{head.display_name}`"
            ),
            span=head.span,
            form_path=top_level_form_path(datum),
            expansion_stack=syntax_expansion_stack(datum),
        )


def _is_splice_form(datum: SyntaxDatum) -> bool:
    return isinstance(datum, SyntaxList) and syntax_head_name(datum) == "splice" and len(datum.items) == 2


def _splice_target_name(datum: SyntaxDatum) -> str:
    assert isinstance(datum, SyntaxList)
    target = datum.items[1]
    if not isinstance(target, SyntaxIdentifier):
        _raise_macro_error(
            code="macro_emits_invalid_ast",
            message="`splice` requires one capture name",
            span=datum.span,
            form_path=datum.form_path,
            expansion_stack=syntax_expansion_stack(datum),
        )
    return target.resolved_name


def _raise_macro_error(
    *,
    code: str,
    message: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack,
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
