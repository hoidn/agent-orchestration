"""Prompt values and provider values (staged-workflow authoring design §4.1 and §4.4).

A `defprompt` declared `-> T` applied to every slot, `(name :slot value …)`, is a value of type `Prompt[T]`
wherever it is written. Outside the `:prompt` of `provider-result` and a `request-input` question nothing
consumes such a value yet, so every position refuses with `prompt_value_escape`, the argument of a call
included. `Prompt[...]`, where no declared or imported type is named `Prompt`, is the type of a `defproc`
parameter and of nothing else. A provider extern is not a value: where the closed build's lowering looks one up
as a value, which on the base was a `compiler_defect`, it refuses with the same code at the name
(`refuse_provider_value`); a program that builds, and a definition the entry does not reach, are never
refused.

Dependencies: the prompt catalog and syntax of the elaborator (`is_prompt_application`), the fill typecheck of
`prompts.py` (`refuse_prompt_application`), and the typed program the closed build is lowering, held in a
context variable for the duration of the build (`refusing_provider_values`, `refuse_provider_value`). Every
function here either returns a fact or raises one `LispFrontendCompileError`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, Any, NoReturn

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


def names_builtin_prompt(head: str, *, type_refs: Mapping[str, TypeRef], import_scope: ModuleImportScope | None,
                         local_type_params: frozenset[str]) -> bool:
    """`head` names the built-in `Prompt`: no type of the module, no unqualified import and no type parameter in
    scope has that name."""

    local = type_refs.get(head)
    imported = import_scope is not None and head in import_scope.unqualified_type_bindings
    shadowed = imported or head in local_type_params
    return head == "Prompt" and local == PrimitiveTypeRef(name="Prompt") and not shadowed


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


# The program the closed build is lowering, for `refuse_provider_value` at the lowering's name lookup: that
# lookup is reached from many call sites whose arguments do not carry the externs, so the build sets it here.
_LOWERED_PROGRAM: ContextVar[Any] = ContextVar("workflow_lisp_lowered_program", default=None)
# Fields and `(name, value)` collections in which an expression, a definition or a signature declares a name.
_BINDER_FIELDS = frozenset({"binder_name", "binding_name", "local_name"})
_BINDER_PAIRS = frozenset({"bindings", "params"})


@contextmanager
def refusing_provider_values(typed: Any) -> Iterator[None]:
    """While the closed build lowers the typed program `typed`, `refuse_provider_value` decides against it."""

    token = _LOWERED_PROGRAM.set(typed)
    try:
        yield
    finally:
        _LOWERED_PROGRAM.reset(token)


def refuse_provider_value(expr: NameExpr) -> None:
    """Called by the lowering where `expr` is missing from its scope; return to let the lookup fail as before.

    That scope holds the program's bindings and never an extern, so a provider extern used as a value is missing
    there (defect D7 of the design, a `compiler_defect` on the base). Refuse when the name is a provider extern
    of the program being lowered and no binder or parameter of the program has that name: a binder spelled like
    an extern and looked up out of its scope is a compiler defect, not a provider. The diagnostic is at the name
    as written, its `authored_span` inside an inlined procedure, whose call the expansion stack keeps. Outside a
    closed build nothing is refused; a program that builds never reaches this, nor an unreached definition.
    """

    typed = _LOWERED_PROGRAM.get()
    if typed is None:
        return
    programs = _programs(typed)
    if expr.name not in _provider_names(programs) or expr.name in _binder_names(programs):
        return
    _refuse(f"provider `{expr.name}` (type `Provider`) is not a value: it is written only as the provider of "
            "`provider-result` or `agent`", span=expr.authored_span or expr.span, form_path=expr.form_path,
            expansion_stack=expr.expansion_stack)


def _programs(typed: Any) -> list[Any]:
    """`typed` and every program it imports, directly or not."""

    programs, stack = [], [typed]
    while stack:
        program = stack.pop()
        if all(program is not seen for seen in programs):
            programs.append(program)
            stack.extend(program.imported_programs.values())
    return programs


def _provider_names(programs: list[Any]) -> frozenset[str]:
    from .workflows import ProviderExtern

    bindings = [each for program in programs for each in (program.externs, *program.module_externs.values())]
    return frozenset(name for each in bindings for name, extern in each.items() if isinstance(extern, ProviderExtern))


def _binder_names(programs: list[Any]) -> frozenset[str]:
    """Every name a binder or parameter of the programs' workflows and procedures declares, a superset."""

    stack: list[Any] = [definition for program in programs
                        for definition in (program.entry, *program.workflows.values(), *program.procedures.values())]
    names: set[str] = set()
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if isinstance(node, (tuple, list)):
            stack.extend(node)
        elif is_dataclass(node) and not isinstance(node, type) and id(node) not in seen:
            seen.add(id(node))
            names.update(_declared_names(node))
            stack.extend(getattr(node, item.name) for item in fields(node))
    return frozenset(names)


def _declared_names(node: Any) -> Iterator[str]:
    for item in fields(node):
        value = getattr(node, item.name)
        if item.name in _BINDER_FIELDS and isinstance(value, str):
            yield value
        elif item.name in _BINDER_PAIRS and isinstance(value, tuple):
            yield from _pair_names(value)
    if type(node).__name__.endswith(("Binding", "Param")) and isinstance(getattr(node, "name", None), str):
        yield node.name


def _pair_names(pairs: tuple) -> Iterator[str]:
    """The names of `(name, value)` pairs, as a `let*` binds and a signature lists its parameters."""

    return (pair[0] for pair in pairs if isinstance(pair, tuple) and pair and isinstance(pair[0], str))
