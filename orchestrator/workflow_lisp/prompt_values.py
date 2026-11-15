"""Prompt values and provider values (staged-workflow authoring design §4.1 and §4.4).

A `defprompt` declared `-> T` applied to every slot, `(name :slot value …)`, is a value of type `Prompt[T]`
wherever it is written. Outside the `:prompt` of `provider-result` and a `request-input` question nothing
consumes such a value yet, so every position refuses with `prompt_value_escape`, the argument of a call
included. `Prompt[...]`, where no declared or imported type is named `Prompt`, is the type of a `defproc`
parameter and of nothing else. A provider extern is a value only as the provider operand of a call or of
`agent`, or as a `bind-proc` argument: in the other positions whose lowering reads it, in code the entry
reaches, it refuses with the same code (`refuse_provider_values`); a definition the entry does not reach
keeps compiling.

Dependencies: the prompt catalog and syntax of the elaborator (`is_prompt_application`), the fill typecheck of
`prompts.py` (`refuse_prompt_application`), and the provider externs of the typed program
(`refuse_provider_values`, called by the closed build for each owner it lowers). Every function here either
returns a fact or raises one `LispFrontendCompileError`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING, NoReturn

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .syntax import SyntaxKeyword
from .type_env import PrimitiveTypeRef, PromptTypeRef, render_type_ref

if TYPE_CHECKING:
    from .expressions import ExprNode, NameExpr
    from .modules import ModuleImportScope
    from .prompts import PromptApplicationExpr, PromptCatalog
    from .spans import SourceSpan
    from .syntax import SyntaxIdentifier, SyntaxList
    from .type_env import FrontendTypeEnvironment, TypeRef
    from .type_expressions import AppliedTypeExpr

PROMPT_VALUE_ESCAPE = "prompt_value_escape"
_ONLY_IN_PROMPT = "a prompt application is written only as the `:prompt` of `provider-result` or a `request-input` question"


def _refuse(message: str, *, span: SourceSpan, form_path: tuple[str, ...],
            expansion_stack: tuple[object, ...] = ()) -> NoReturn:
    raise LispFrontendCompileError((LispFrontendDiagnostic(
        code=PROMPT_VALUE_ESCAPE, message=message, span=span, form_path=form_path,
        expansion_stack=expansion_stack),))


def is_prompt_application(datum: SyntaxList, head: SyntaxIdentifier, *, catalog: PromptCatalog | None,
                          taken: frozenset[str]) -> bool:
    """The head rule outside `:prompt`, after language forms and operators have been taken.

    `(name :slot value …)` with `name` a visible prompt is its application, whatever else has the name; a call
    with a keyword first compiles today only when it is one. `(name)` is the application unless `name` is in
    `taken` (a binding, procedure, function or local), so that call keeps its meaning.
    """

    if catalog is None or catalog.resolve(head.resolved_name) is None:
        return False
    if len(datum.items) > 1:
        return isinstance(datum.items[1], SyntaxKeyword)
    return head.resolved_name not in taken


def prompt_type(item_type_ref: TypeRef) -> PromptTypeRef:
    """The type `Prompt[T]` of a prompt declared `-> T`."""
    return PromptTypeRef(name=f"Prompt[{render_type_ref(item_type_ref)}]", item_type_ref=item_type_ref)


def names_builtin_prompt(head: str, *, type_refs: Mapping[str, TypeRef],
                         import_scope: ModuleImportScope | None) -> bool:
    """`head` names the built-in `Prompt`: no type of the module, and no unqualified import, has that name."""

    local = type_refs.get(head)
    imported = import_scope is not None and head in import_scope.unqualified_type_bindings
    return head == "Prompt" and local == PrimitiveTypeRef(name="Prompt") and not imported


def resolve_prompt_type(parsed: AppliedTypeExpr, *, admitted: bool, resolve_arg: Callable[[object], TypeRef],
                        span: SourceSpan, form_path: tuple[str, ...],
                        expansion_stack: tuple[object, ...]) -> PromptTypeRef:
    """`Prompt[T]` written as a type: admitted for the whole type of a `defproc` parameter only."""

    if len(parsed.args) != 1:
        raise LispFrontendCompileError((LispFrontendDiagnostic(
            code="type_expression_invalid", message="`Prompt` takes one type argument, the prompt's result type",
            span=span, form_path=form_path, expansion_stack=expansion_stack),))
    type_ref = prompt_type(resolve_arg(parsed.args[0]))
    if not admitted:
        _refuse(f"`{type_ref.name}` is the type of a `defproc` parameter only", span=span, form_path=form_path,
                expansion_stack=expansion_stack)
    return type_ref


def refuse_prompt_application(application: PromptApplicationExpr, *, recurse: Callable[[ExprNode], object],
                              type_env: FrontendTypeEnvironment) -> NoReturn:
    """Type the fills of a prompt application in value position, then refuse it with its type."""

    from .prompts import typecheck_prompt_application

    typecheck_prompt_application(application, recurse=recurse, type_env=type_env)
    value_type = prompt_type(application.prompt.return_type_ref)
    _refuse(f"a prompt value of type `{value_type.name}` is not admitted here: {_ONLY_IN_PROMPT}",
            span=application.span, form_path=application.form_path, expansion_stack=application.expansion_stack)


def refuse_prompt_name(expr: NameExpr, type_ref: TypeRef) -> None:
    """A name whose type is `Prompt[T]` (a `defproc` parameter) used as a value."""

    if isinstance(type_ref, PromptTypeRef):
        _refuse(f"`{expr.name}` is a prompt value of type `{type_ref.name}` and is not admitted here: "
                f"{_ONLY_IN_PROMPT}", span=expr.span, form_path=expr.form_path,
                expansion_stack=expr.expansion_stack)


def refuse_provider_values(body: ExprNode, *, provider_names: Iterable[str], bound: Iterable[str]) -> None:
    """A provider extern named in a value position of a body the entry reaches (defect D7).

    The positions are those whose lowering reads the name as a value and that typecheck admits: a `let*`
    binding, a record or variant field, an `if`, `cond` or `match` value, a procedure or `defun` argument,
    and the body's own result. A list element and a workflow `call` input are refused by typecheck first. A
    `bind-proc` argument is not refused (design §4.4); an uncalled one is never read. Only a free name is the
    extern: a parameter of the owner (`bound`) or a local binder of the same name is not.
    """

    from .expression_traversal import iter_child_exprs, map_expr, walk_expr
    from .expressions import (CondExpr, FunctionCallExpr, IfExpr, LetStarExpr, MatchExpr, ProcedureCallExpr,
                              RecordExpr, UnionVariantExpr)

    names = frozenset(provider_names)
    externs: list = []
    map_expr(body, lambda name: externs.append(name) or name, bound=frozenset(bound))
    extern_ids = {id(name) for name in externs if name.name in names}
    value_parents = (LetStarExpr, RecordExpr, UnionVariantExpr, IfExpr, CondExpr, MatchExpr, ProcedureCallExpr,
                     FunctionCallExpr)
    candidates = [body] + [child for node in walk_expr(body) if isinstance(node, value_parents)
                           for child in iter_child_exprs(node)]
    for expr in candidates:
        if id(expr) in extern_ids:
            _refuse(f"provider `{expr.name}` (type `Provider`) is a value only as the provider of `provider-result` "
                    "or `agent`, or as a `bind-proc` argument",
                    span=expr.span, form_path=expr.form_path, expansion_stack=expr.expansion_stack)
