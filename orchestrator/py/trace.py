"""Symbolic expressions and ordered lexical traces; compilation owns semantics."""
from __future__ import annotations

from contextvars import ContextVar
from collections.abc import Mapping
from dataclasses import dataclass, field
import inspect
from types import UnionType
from typing import Union, get_args, get_origin

from .diagnostics import PythonFrontendError, PythonSite, author_site


_ACTIVE: ContextVar[Trace | None] = ContextVar("workflow_python_trace", default=None)
_INHERIT_LOOP_OWNER = object()
_INHERIT_LOOP_STATE = object()


def active_trace() -> Trace:
    trace = _ACTIVE.get()
    if trace is None:
        raise PythonFrontendError("python_effect_outside_trace", "Effects require a registered definition being generated")
    return trace


def declaration_expression(kind, args, annotation):
    trace = _ACTIVE.get()
    if trace is not None:
        return trace.expression(kind, args, annotation)
    _validate_unscoped(args, author_site())
    return Expr(kind, args, annotation, author_site())


@dataclass(eq=False, frozen=True)
class Expr:
    _kind: str
    _args: tuple
    _annotation: object = None
    _site: PythonSite = field(default_factory=author_site)
    _scope: object = field(default=None, repr=False)

    def _binary(self, op, other, *, reverse=False, annotation=None):
        return declaration_expression(
            "op", (op, other, self) if reverse else (op, self, other),
            annotation or self._annotation,
        )

    def __add__(self, other): return self._binary("+", other)
    def __radd__(self, other): return self._binary("+", other, reverse=True)
    def __sub__(self, other): return self._binary("-", other)
    def __rsub__(self, other): return self._binary("-", other, reverse=True)
    def __mul__(self, other): return self._binary("*", other)
    def __rmul__(self, other): return self._binary("*", other, reverse=True)
    def __truediv__(self, other): return self._binary("/", other, annotation=float)
    def __rtruediv__(self, other): return self._binary("/", other, reverse=True, annotation=float)
    def __floordiv__(self, other): return self._binary("int/div", other)
    def __rfloordiv__(self, other): return self._binary("int/div", other, reverse=True)
    def __mod__(self, other): return self._binary("int/mod", other)
    def __rmod__(self, other): return self._binary("int/mod", other, reverse=True)
    def __neg__(self):
        return declaration_expression(
            "op", ("-", 0.0 if self._annotation is float else 0, self), self._annotation
        )
    def __eq__(self, other): return self._binary("=", other, annotation=bool)
    def __ne__(self, other): return self._binary("!=", other, annotation=bool)
    def __lt__(self, other): return self._binary("<", other, annotation=bool)
    def __le__(self, other): return self._binary("<=", other, annotation=bool)
    def __gt__(self, other): return self._binary(">", other, annotation=bool)
    def __ge__(self, other): return self._binary(">=", other, annotation=bool)

    def _refuse(self, helper):
        raise PythonFrontendError("python_symbolic_coercion", f"Symbolic runtime values require {helper}")

    def __bool__(self): return self._refuse("when/all_of/any_of/not_ instead of Python truth testing")
    def __len__(self): return self._refuse("length instead of len")
    def __str__(self): return self._refuse("concat and typed prompt fills instead of str")
    def __format__(self, spec): return self._refuse("concat and typed prompt fills instead of formatting")
    def __iter__(self): return self._refuse("workflow list operations instead of Python iteration")
    def __contains__(self, value): return self._refuse("compiler-supported operations instead of membership")
    def __setitem__(self, key, value): return self._refuse("immutable constructors instead of mutation")
    def __getitem__(self, key):
        raise PythonFrontendError("python_symbolic_index_unsupported", "The compiler has no general list indexing operation")

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        from .declarations import fields_of
        trace = active_trace()
        trace.validate_value(self)
        annotation = self._annotation
        if trace.generator.graph is not None:
            annotation = trace.generator.graph.resolve_annotation(annotation, trace.generator)
        kind = getattr(annotation, "_orc_kind", None)
        if kind == "record" or (kind == "variant" and self._kind == "case_ref"):
            annotation = fields_of(annotation).get(name)
            if annotation is None:
                raise PythonFrontendError("python_symbolic_attribute", f"No readable symbolic field `{name}`; runtime values are immutable", site=author_site())
        else:
            raise PythonFrontendError("python_symbolic_attribute", f"No readable symbolic field `{name}`; runtime values are immutable", site=author_site())
        base = self
        if base._kind not in {"ref", "field", "case_ref"}:
            base = trace.bind(base, prefix="v")
        return trace.expression("field", (base, name), annotation)


# Frozen dataclasses otherwise raise an incidental FrozenInstanceError on author mutation.
def _immutable_expr(self, name, value):
    raise PythonFrontendError("python_symbolic_mutation", "Symbolic runtime values are immutable")


Expr.__setattr__ = _immutable_expr
Expr.__delattr__ = lambda self, name: _immutable_expr(self, name, None)


def _validate_unscoped(value, site):
    from .declarations import PromptApplication
    if isinstance(value, Expr):
        if value._scope is not None:
            raise PythonFrontendError(
                "python_scope_escape",
                "A symbolic branch or match binder cannot escape its lexical region",
                site=site or value._site,
            )
        _validate_unscoped(value._args, site)
    elif isinstance(value, Mapping):
        for child in value.values(): _validate_unscoped(child, site)
    elif isinstance(value, (tuple, list, set, frozenset)):
        for child in value: _validate_unscoped(child, site)
    elif isinstance(value, PromptApplication):
        _validate_unscoped(value.values, site)


@dataclass(eq=False)
class TraceScope:
    parent: TraceScope | None = None


@dataclass
class _NameAllocator:
    reserved: set[str] = field(default_factory=set)
    counters: dict[str, int] = field(default_factory=dict)

    def next(self, prefix):
        index = self.counters.get(prefix, 0)
        while f"_{prefix}{index}" in self.reserved:
            index += 1
        name = f"_{prefix}{index}"
        self.counters[prefix] = index + 1
        self.reserved.add(name)
        return name


@dataclass
class Trace:
    generator: object
    definition: object
    scope: TraceScope = field(default_factory=TraceScope)
    names: _NameAllocator | None = None
    bindings: list[tuple[str, Expr]] = field(default_factory=list)
    loop_owner: object | None = None
    loop_state_type: object = None
    tail_controls: list[Expr] = field(default_factory=list)

    def __post_init__(self):
        if self.names is None:
            self.names = _NameAllocator(set(inspect.signature(self.definition.function).parameters))

    def child(self, *, loop_owner=_INHERIT_LOOP_OWNER,
              loop_state_type=_INHERIT_LOOP_STATE):
        owner = self.loop_owner if loop_owner is _INHERIT_LOOP_OWNER else loop_owner
        state_type = (self.loop_state_type if loop_state_type is _INHERIT_LOOP_STATE
                      else loop_state_type)
        return Trace(
            self.generator, self.definition, TraceScope(self.scope), self.names,
            loop_owner=owner, loop_state_type=state_type,
        )

    def expression(self, kind, args, annotation=None, *, site=None):
        site = site or author_site()
        if kind in {"when", "match"}:
            self.validate_value(args[0], site=site)
        elif kind == "loop":
            self.validate_value(args[:2], site=site)
        elif kind not in {"all_of", "any_of"}:
            self.validate_value(args, site=site)
        expression = Expr(kind, args, annotation, site, self.scope)
        if kind in {"when", "match", "continue", "done"} and _contains_loop_control(expression):
            self.tail_controls.append(expression)
        return expression

    def reference(self, name, annotation, *, site=None, kind="ref"):
        return Expr(kind, (name,), annotation, site or author_site(), self.scope)

    def fresh(self, prefix):
        return self.names.next(prefix)

    def validate_value(self, value, *, site=None):
        from .declarations import PromptApplication
        if isinstance(value, Expr):
            self._validate_scope(value._scope, site or value._site)
            if value._kind == "when":
                self.validate_value(value._args[0], site=site)
            elif value._kind == "match":
                self.validate_value(value._args[0], site=site)
            elif value._kind == "loop":
                self.validate_value(value._args[:2], site=site)
            elif value._kind in {"all_of", "any_of", "ref", "case_ref", "loop_ref"}:
                return
            elif value._kind == "call":
                self.validate_value(value._args[1], site=site)
            elif value._kind == "provider":
                from .declarations import PromptApplication
                _provider, application, options = value._args
                if isinstance(application, PromptApplication):
                    self.validate_value(application.values, site=site)
                self.validate_value(options, site=site)
            else:
                self.validate_value(value._args, site=site)
        elif isinstance(value, Mapping):
            for child in value.values(): self.validate_value(child, site=site)
        elif isinstance(value, (tuple, list, set, frozenset)):
            for child in value: self.validate_value(child, site=site)
        elif isinstance(value, PromptApplication):
            self.validate_value(value.values, site=site)

    def _validate_scope(self, owner, site):
        if owner is None:
            return
        scope = self.scope
        while scope is not None:
            if owner is scope:
                return
            scope = scope.parent
        raise PythonFrontendError(
            "python_scope_escape",
            "A symbolic branch or match binder cannot escape its lexical region",
            site=site,
        )

    def region(self, function, *, binder_type=None, binder_prefix="case",
               binder_required=False, loop_owner=_INHERIT_LOOP_OWNER,
               loop_state_type=_INHERIT_LOOP_STATE):
        has_binder = binder_type is not None or binder_required
        if not callable(function):
            code = "python_match_binder_required" if has_binder else "python_when_thunk_required"
            raise PythonFrontendError(code, "Control callbacks must be callable lexical thunks", site=author_site())
        try:
            parameters = tuple(inspect.signature(function).parameters.values())
        except (TypeError, ValueError) as exc:
            code = "python_match_binder_required" if has_binder else "python_when_thunk_required"
            raise PythonFrontendError(code, "Control callbacks require an inspectable signature", site=author_site()) from exc
        expected = 1 if has_binder else 0
        valid = len(parameters) == expected and all(
            parameter.kind in {parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY}
            for parameter in parameters
        )
        if not valid:
            code = "python_match_binder_required" if has_binder else "python_when_thunk_required"
            detail = "one named binder" if expected else "zero arguments"
            raise PythonFrontendError(code, f"Control callbacks require {detail}", site=author_site())
        child = self.child(loop_owner=loop_owner, loop_state_type=loop_state_type)
        binder = None
        arguments = {}
        if has_binder:
            binder = child.fresh(binder_prefix)
            arguments[parameters[0].name] = child.reference(binder, binder_type, kind="case_ref")
        result = child.run(function, arguments)
        return child, result, binder

    def bind(self, expression: Expr, *, prefix="e") -> Expr:
        self.validate_value(expression)
        if _contains_loop_control(expression):
            raise PythonFrontendError(
                "python_loop_control_not_tail",
                "Loop transfers must remain in the tail position of a loop body",
                site=expression._site,
            )
        name = self.fresh(prefix)
        self.bindings.append((name, expression))
        return self.reference(name, expression._annotation, site=expression._site)

    def run(self, function, arguments):
        token = _ACTIVE.set(self)
        try:
            result = function(**arguments)
            self.validate_value(result)
            retained = _tail_controls(result)
            for control in retained:
                if control._kind in {"continue", "done"} and control._args[0] is not self.loop_owner:
                    raise PythonFrontendError("python_loop_control_owner_mismatch",
                        "Loop transfers must target the innermost active loop body", site=control._site)
            retained_ids = {id(control) for control in retained}
            for control in self.tail_controls:
                if id(control) not in retained_ids:
                    raise PythonFrontendError("python_loop_control_not_tail",
                        "Loop transfers must be retained in the returned tail control", site=control._site)
            return result
        finally:
            _ACTIVE.reset(token)


def _branch_annotation(generator, values):
    annotations = [
        getattr(value, "_annotation", None)
        if isinstance(value, Expr)
        else type(value) if type(value) in {bool, int, float, str} else None
        for value in values
    ]
    if not annotations or any(annotation is None for annotation in annotations):
        return None
    if all(getattr(annotation, "_orc_kind", None) == "variant" for annotation in annotations):
        from .imports import CompilerCase
        if all(isinstance(annotation, CompilerCase) for annotation in annotations):
            first = annotations[0]._union
            if all(annotation._union is first for annotation in annotations): return first
        owners = [
            {union for union in (generator.graph.type_owners if generator.graph is not None else generator.union_names)
             if annotation in get_args(union)}
            for annotation in annotations
        ]
        shared = set.intersection(*owners)
        if len(shared) == 1:
            return next(iter(shared))
    return annotations[0] if all(annotation == annotations[0] for annotation in annotations[1:]) else None


def _tail_controls(value):
    if not isinstance(value, Expr):
        return []
    if value._kind in {"continue", "done"}:
        return [value]
    if value._kind == "when":
        regions = value._args[1:]
        return [value, *(control for _trace, result in regions for control in _tail_controls(result))]
    if value._kind == "match":
        return [value, *(control for _case, _binder, _trace, result in value._args[1]
                         for control in _tail_controls(result))]
    return []


def _contains_loop_control(value):
    if isinstance(value, Expr):
        if value._kind in {"continue", "done"}:
            return True
        if value._kind == "loop":
            return False
        return _contains_loop_control(value._args)
    if isinstance(value, Trace):
        return any(_contains_loop_control(expression) for _, expression in value.bindings)
    if isinstance(value, Mapping):
        return any(_contains_loop_control(child) for child in value.values())
    if isinstance(value, (tuple, list, set, frozenset)):
        return any(_contains_loop_control(child) for child in value)
    return False


def _done_values(value, owner):
    if isinstance(value, Expr):
        if value._kind == "done":
            control_owner, payload = value._args
            return [payload] if control_owner is owner else []
        if value._kind in {"continue", "loop"}:
            return []
        return _done_values(value._args, owner)
    if isinstance(value, Trace):
        return [result for _, expression in value.bindings
                for result in _done_values(expression, owner)]
    if isinstance(value, Mapping):
        return [result for child in value.values() for result in _done_values(child, owner)]
    if isinstance(value, (tuple, list, set, frozenset)):
        return [result for child in value for result in _done_values(child, owner)]
    return []


def _closed_union(annotation):
    from .imports import CompilerType
    if isinstance(annotation, CompilerType): return annotation._orc_kind == "union"
    args = get_args(annotation)
    return (get_origin(annotation) in {UnionType, Union} and args and
            all(getattr(case, "_orc_kind", None) == "variant" for case in args))


def when(condition, *, then, else_):
    trace = active_trace()
    trace.validate_value(condition)
    then_region = trace.region(then)
    else_region = trace.region(else_)
    expression = trace.expression(
        "when", (condition, then_region[:2], else_region[:2]),
        _branch_annotation(trace.generator, (then_region[1], else_region[1])),
    )
    return expression if _contains_loop_control(expression) else trace.bind(expression)


def match(value, **cases):
    trace = active_trace()
    trace.validate_value(value)
    if not isinstance(value, Expr) or not _closed_union(value._annotation):
        raise PythonFrontendError("python_match_requires_union", "match requires a value annotated with a closed variant union", site=author_site())
    from .imports import CompilerType
    variants = (value._annotation._cases() if isinstance(value._annotation, CompilerType)
                else get_args(value._annotation))
    names = [variant.__name__ for variant in variants]
    if len(set(names)) != len(names) or set(cases) != set(names):
        raise PythonFrontendError("python_match_cases", "match requires exactly one arm for every named union case", site=author_site())
    arms = []
    for variant in variants:
        child, result, binder = trace.region(cases[variant.__name__], binder_type=variant)
        arms.append((variant, binder, child, result))
    annotation = _branch_annotation(trace.generator, [result for _, _, _, result in arms])
    expression = trace.expression("match", (value, tuple(arms)), annotation)
    return expression if _contains_loop_control(expression) else trace.bind(expression)


def _boolean_thunks(kind, thunks):
    trace = active_trace()
    regions = tuple(trace.region(thunk)[:2] for thunk in thunks)
    return trace.bind(trace.expression(kind, regions, bool))


def all_of(*thunks): return _boolean_thunks("all_of", thunks)
def any_of(*thunks): return _boolean_thunks("any_of", thunks)


def length(value): return declaration_expression("op", ("list/length", value), int)
def concat(*values): return declaration_expression("op", ("string/concat", *values), str)
def not_(value): return declaration_expression("op", ("not", value), bool)


def loop(*, state, max, body, on_exhausted):
    trace = active_trace()
    trace.validate_value(max)
    trace.validate_value(state)
    state_type = getattr(state, "_annotation", None)
    if state_type is None and type(state) in {bool, int, float, str}:
        state_type = type(state)
    owner = object()
    body_region = trace.region(
        body, binder_type=state_type, binder_required=True, binder_prefix="loop",
        loop_owner=owner, loop_state_type=state_type,
    )
    exhausted_region = trace.region(
        on_exhausted, binder_type=state_type, binder_required=True,
        binder_prefix="exhausted",
    )
    result_values = _done_values(body_region[1], owner)
    result_values.append(exhausted_region[1])
    annotation = _branch_annotation(trace.generator, result_values)
    return trace.bind(trace.expression(
        "loop", (max, state, body_region, exhausted_region, owner), annotation,
    ))


def cont(state):
    trace = active_trace()
    if trace.loop_owner is None:
        raise PythonFrontendError("python_loop_control_owner_mismatch", "cont requires an active loop body")
    trace.validate_value(state)
    return trace.expression("continue", (trace.loop_owner, state),
                            getattr(state, "_annotation", None))


def done(value):
    trace = active_trace()
    if trace.loop_owner is None:
        raise PythonFrontendError("python_loop_control_owner_mismatch", "done requires an active loop body")
    trace.validate_value(value)
    return trace.expression("done", (trace.loop_owner, value),
                            getattr(value, "_annotation", None))
