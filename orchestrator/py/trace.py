"""Symbolic expressions and ordered lexical traces; compilation owns semantics."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import inspect

from .diagnostics import PythonFrontendError, PythonSite, author_site


_ACTIVE: ContextVar[Trace | None] = ContextVar("workflow_python_trace", default=None)


def active_trace() -> Trace:
    trace = _ACTIVE.get()
    if trace is None:
        raise PythonFrontendError("python_effect_outside_trace", "Effects require a registered definition being generated")
    return trace


@dataclass(eq=False, frozen=True)
class Expr:
    _kind: str
    _args: tuple
    _annotation: object = None
    _site: PythonSite = field(default_factory=author_site)

    def _binary(self, op, other, *, reverse=False, annotation=None):
        return Expr("op", (op, other, self) if reverse else (op, self, other),
                    annotation or self._annotation)

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
    def __neg__(self): return Expr("op", ("-", 0.0 if self._annotation is float else 0, self), self._annotation)
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
        if getattr(self._annotation, "_orc_kind", None) == "record":
            annotations = fields_of(self._annotation)
            if name in annotations:
                base = self
                if base._kind not in {"ref", "field"}:
                    base = active_trace().bind(base, prefix="v")
                return Expr("field", (base, name), annotations[name])
        raise PythonFrontendError("python_symbolic_attribute", f"No readable symbolic field `{name}`; runtime values are immutable")


# Frozen dataclasses otherwise raise an incidental FrozenInstanceError on author mutation.
def _immutable_expr(self, name, value):
    raise PythonFrontendError("python_symbolic_mutation", "Symbolic runtime values are immutable")


Expr.__setattr__ = _immutable_expr
Expr.__delattr__ = lambda self, name: _immutable_expr(self, name, None)


@dataclass
class Trace:
    generator: object
    definition: object
    bindings: list[tuple[str, Expr]] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)

    def bind(self, expression: Expr, *, prefix="e") -> Expr:
        index = self.counters.get(prefix, 0)
        occupied = set(inspect.signature(self.definition.function).parameters) | {name for name, _ in self.bindings}
        while f"_{prefix}{index}" in occupied:
            index += 1
        self.counters[prefix] = index + 1
        name = f"_{prefix}{index}"
        self.bindings.append((name, expression))
        return Expr("ref", (name,), expression._annotation, expression._site)

    def run(self, function, arguments):
        token = _ACTIVE.set(self)
        try:
            return function(**arguments)
        finally:
            _ACTIVE.reset(token)


def length(value): return Expr("op", ("list/length", value), int)
def concat(*values): return Expr("op", ("string/concat", *values), str)
def not_(value): return Expr("op", ("not", value), bool)
