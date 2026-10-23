"""Deferred, bounded declarative tracing into ordinary Lisp expressions."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
import inspect
from pathlib import Path
import typing

from .types import Type, Types, HostType, Fill, Effect

_ACTIVE = ContextVar('workflow_python_trace', default=None)
_OMITTED = object()


class AuthoringError(ValueError):
    """A located refusal of unsupported Python authoring."""


@dataclass(frozen=True)
class Location:
    path: str
    line: int
    definition: str


def location():
    frame = inspect.currentframe().f_back
    while frame and Path(frame.f_code.co_filename).parent == Path(__file__).parent:
        frame = frame.f_back
    return Location(frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name) if frame else Location('<unknown>', 1, '<unknown>')


def fail(message, loc=None):
    loc = loc or location()
    raise AuthoringError(f'{loc.path}:{loc.line} ({loc.definition}): {message}')


def current():
    active = _ACTIVE.get()
    if active is None: fail('workflow expressions require explicit build tracing')
    return active


@dataclass(frozen=True)
class Expr:
    kind: str
    type: Type
    data: object
    loc: Location


@dataclass(frozen=True)
class Block:
    bindings: tuple
    result: Expr


class Symbol:
    def __init__(self, expr): self.expr = expr
    def __getattr__(self, name):
        for field, type in self.expr.type.fields:
            if field == name:
                return Symbol(Expr('field', type, (self.expr, name), location()))
        fail(f'unknown field {name!r} on {self.expr.type.name}')
    def _refuse(self, *args, **kwargs): fail('symbolic values cannot use Python truth, iteration, string, comparison or arithmetic operations')
    __bool__ = __iter__ = __len__ = __str__ = __repr__ = __format__ = _refuse
    __eq__ = __ne__ = __lt__ = __le__ = __gt__ = __ge__ = _refuse
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _refuse
    __truediv__ = __rtruediv__ = __floordiv__ = __rfloordiv__ = _refuse
    __mod__ = __rmod__ = __pow__ = __rpow__ = __neg__ = __pos__ = __abs__ = _refuse
    __and__ = __rand__ = __or__ = __ror__ = __xor__ = __rxor__ = _refuse
    __getitem__ = __contains__ = __index__ = __int__ = __float__ = __bytes__ = _refuse
    __hash__ = None


class Declaration:
    def __init__(self, fn, returns, effects, kind):
        self.fn, self.returns, self.effects, self.kind = fn, returns, effects, kind
        self.__name__, self.__module__ = fn.__name__, fn.__module__
        self.__doc__ = fn.__doc__
    def __call__(self, *args, **kwargs): return current().call(self, args, kwargs)


def _decorator(kind, returns, effects):
    def decorate(fn):
        if inspect.iscoroutinefunction(fn) or inspect.isgeneratorfunction(fn):
            fail('async and generator workflows are unsupported')
        return Declaration(fn, returns, effects, kind)
    return decorate


def workflow(*, returns=_OMITTED): return _decorator('workflow', returns, _OMITTED)


def proc(*, returns=_OMITTED, effects=_OMITTED): return _decorator('proc', returns, effects)


class Prompt:
    def __init__(self, *, text=None, file=None, fills=None, returns):
        if (text is None) == (file is None): raise TypeError('Prompt requires exactly one of text and file')
        if text is not None and not isinstance(text, str): raise TypeError('Prompt text must be a string')
        self.text, self.file, self.fills, self.returns = text, file, dict(fills or {}), returns
        self.loc = location()
        if not all(isinstance(name, str) and isinstance(fill, Fill) for name, fill in self.fills.items()):
            raise TypeError('Prompt fills require named typed fill descriptors')
    def __call__(self, **fills):
        trace = current()
        name = trace.prompt(self)
        if set(fills) != set(self.fills): fail('prompt requires exactly its declared fills')
        operands = []
        for key, fill in self.fills.items():
            operand = trace.value(fills[key], trace.types.resolve(fill.type))
            if operand.kind not in ('literal', 'name', 'field'):
                operand = trace.bind(operand).expr
            operands.append((key, operand))
        return AppliedPrompt(self, name, operands)


@dataclass(frozen=True)
class AppliedPrompt:
    prompt: Prompt
    name: str
    fills: tuple


class Provider:
    def __init__(self, name): self.name = name
    def __call__(self, prompt, *, model=None, effort=None, timeout_sec=None):
        trace = current()
        if not isinstance(prompt, AppliedPrompt): fail('Provider requires a fully applied typed prompt')
        result = trace.types.resolve(prompt.prompt.returns)
        options = tuple((key, trace.value(value)) for key, value in [('model', model), ('effort', effort), ('timeout-sec', timeout_sec)] if value is not None)
        return trace.bind(Expr('provider', result, (self.name, prompt, options), location()))


class Command:
    def __init__(self, name, *, returns): self.name, self.returns = name, returns
    def __call__(self, *argv):
        trace = current()
        return trace.bind(Expr('command', trace.types.resolve(self.returns), (self.name, tuple(trace.value(v) for v in argv)), location()))


def ask(question, *, returns, timeout_sec=None, show=()):
    trace = current()
    answer = trace.types.resolve(returns)
    if isinstance(question, AppliedPrompt):
        if trace.types.resolve(question.prompt.returns) != answer: fail('question prompt return type disagrees with ask')
    else: question = trace.value(question, Type('primitive', 'String'))
    if not isinstance(show, (tuple, list)): fail('show requires a list or tuple of typed paths')
    shown = tuple(trace.value(value) for value in show)
    if any(value.type.kind != 'path' for value in shown): fail('show requires typed paths')
    timeout = trace.value(timeout_sec) if timeout_sec is not None else None
    result = trace.types.resolve(HostType(returns))
    return trace.bind(Expr('ask', result, (question, answer, timeout, shown), location()))


def _callback(callback, count):
    if not callable(callback): fail('branches require lazy callbacks, not eager expressions')
    if len(inspect.signature(callback).parameters) != count: fail(f'branch callback requires exactly {count} parameters')


def match(value, **branches):
    trace = current()
    subject = trace.value(value)
    type = subject.type
    names = [name for name, _ in (type.members if type.kind == 'enum' else type.tags)]
    if type.kind not in ('enum', 'union', 'host') or set(branches) != set(names):
        fail('match requires exhaustive enum/union callbacks with no unknown tags')
    arms = []
    result_type = None
    for name in names:
        callback = branches[name]
        _callback(callback, 1)
        binder = trace.name('arm')
        payload = type if type.kind == 'enum' else Type('payload', f'{type.name}.{name}', fields=dict(type.tags)[name])
        symbol = Symbol(Expr('name', payload, binder, location()))
        block = trace.branch(lambda: callback(symbol), origin=Location(callback.__code__.co_filename, callback.__code__.co_firstlineno, callback.__code__.co_name))
        if result_type is not None and block.result.type != result_type: fail('match branches must return one common type')
        result_type = block.result.type
        arms.append((name, binder, block))
    return trace.bind(Expr('match', result_type, (subject, tuple(arms)), location()))


def when(condition, *, then, otherwise):
    trace = current()
    _callback(then, 0)
    _callback(otherwise, 0)
    condition = trace.value(condition, Type('primitive', 'Bool'))
    yes, no = trace.branch(then), trace.branch(otherwise)
    if yes.result.type != no.result.type: fail('when branches must return one common type')
    return trace.bind(Expr('if', yes.result.type, (condition, yes, no), location()))


@dataclass
class Procedure:
    declaration: Declaration
    name: str
    params: tuple
    result: Type
    block: Block | None = None
    calls: list = field(default_factory=list)


class Trace:
    def __init__(self, entry, workspace):
        self.workspace = workspace
        self.entry = entry
        self.types = Types([entry.fn.__globals__])
        self.procedures = {}
        self.prompts = {}
        self.reserved = set(self.types.namespace)
        for value in self.types.namespace.values():
            if isinstance(value, Declaration):
                self.reserved.add(value.__name__)
                self.reserved.update(inspect.signature(value.fn).parameters)
        self.counter = 0
        self.bindings = []
        self.active = None

    def name(self, prefix):
        self.counter += 1
        while f'{prefix}{self.counter}' in self.reserved:
            self.counter += 1
        return f'{prefix}{self.counter}'

    def signature(self, declaration):
        signature = inspect.signature(declaration.fn)
        hints = typing.get_type_hints(declaration.fn, globalns=declaration.fn.__globals__)
        annotation = hints.get('return', _OMITTED)
        selected = annotation if declaration.returns is _OMITTED else declaration.returns
        if selected is _OMITTED: fail('declaration requires returns= or a return annotation')
        result = self.types.resolve(selected)
        if annotation is not _OMITTED and self.types.resolve(annotation) != result: fail('conflicting return contracts')
        params = []
        for name, parameter in signature.parameters.items():
            if parameter.kind not in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY) or parameter.default is not parameter.empty:
                fail('only annotated required parameters are supported')
            if name not in hints: fail(f'parameter {name} requires an annotation')
            params.append((name, self.types.resolve(hints[name])))
        return tuple(params), result

    def declaration(self, declaration):
        if declaration not in self.procedures:
            self.types.namespace.update(declaration.fn.__globals__)
            self.reserved.update(inspect.signature(declaration.fn).parameters)
            self.reserved.add(declaration.__name__)
            params, result = self.signature(declaration)
            name = declaration.__name__
            if any(p.name == name for p in self.procedures.values()): fail(f'duplicate declaration name {name}')
            self.procedures[declaration] = Procedure(declaration, name, params, result)
        return self.procedures[declaration]

    def call(self, declaration, args, kwargs):
        proc = self.declaration(declaration)
        bound = inspect.signature(declaration.fn).bind(*args, **kwargs)
        values = tuple(self.value(bound.arguments[name], type) for name, type in proc.params)
        self.active.calls.append(declaration)
        return self.bind(Expr('call', proc.result, (proc.name, values), location()))

    def value(self, value, expected=None, loc=None):
        loc = loc or location()
        if isinstance(value, Symbol): expr = value.expr
        elif isinstance(value, Enum):
            enum_type = self.types.resolve(value.__class__)
            expr = Expr('enum', enum_type, value.value, loc)
        elif type(value) in (str, int, float, bool):
            expr = Expr('literal', self.types.resolve(type(value)), value, loc)
        elif isinstance(value, list):
            item = expected.item if expected and expected.kind == 'list' else None
            values = tuple(self.value(v, item) for v in value)
            if not values and item is None: fail('empty list requires an expected list type')
            item = item or values[0].type
            if any(v.type != item for v in values): fail('list elements require one type')
            expr = Expr('list', Type('list', f'List[{item.name}]', item=item), values, loc)
        else: fail(f'unsupported workflow value {type(value).__name__}')
        if expected is not None and expr.type != expected: fail(f'expected {expected.name}, got {expr.type.name}')
        return expr

    def construct(self, cls, args, kwargs):
        type = self.types.resolve(cls)
        tag = cls.__name__ if cls.__orc_kind__ == 'variant' else None
        fields = dict(type.tags)[tag] if tag else type.fields
        if len(args) > len(fields): fail('too many constructor arguments')
        values = dict(zip((name for name, _ in fields), args))
        if set(values) & set(kwargs): fail('duplicate constructor fields')
        values.update(kwargs)
        if set(values) != {name for name, _ in fields}: fail('constructor requires exactly its declared fields')
        operands = tuple((name, self.value(values[name], field)) for name, field in fields)
        return self.bind(Expr('variant' if tag else 'record', type, (tag, operands) if tag else operands, location()))

    def path(self, cls, child):
        return self.bind(Expr('path', self.types.resolve(cls), self.value(child, Type('primitive', 'String')), location()))

    def bind(self, expr):
        name = self.name('v')
        self.bindings.append((name, expr))
        return Symbol(Expr('name', expr.type, name, expr.loc))

    def branch(self, callback, expected=None, origin=None):
        previous, self.bindings = self.bindings, []
        if origin is None:
            code = callback.__code__
            origin = Location(code.co_filename, code.co_firstlineno, code.co_name)
            if Path(origin.path).parent == Path(__file__).parent:
                code = self.active.declaration.fn.__code__
                origin = Location(code.co_filename, code.co_firstlineno, code.co_name)
        try:
            result = self.value(callback(), expected, origin)
            return Block(tuple(self.bindings), result)
        finally:
            self.bindings = previous

    def prompt(self, prompt):
        if prompt not in self.prompts:
            name = self.name('prompt')
            template = prompt.text if prompt.file is None else (self.workspace / prompt.file).read_bytes().decode('utf-8')
            self.prompts[prompt] = (name, template)
            self.types.resolve(prompt.returns)
            for fill in prompt.fills.values(): self.types.resolve(fill.type)
        return self.prompts[prompt][0]

    def run(self):
        self.declaration(self.entry)
        token = _ACTIVE.set(self)
        try:
            while any(proc.block is None for proc in self.procedures.values()):
                proc = next(proc for proc in self.procedures.values() if proc.block is None)
                self.active = proc
                args = {name: Symbol(Expr('name', type, name, Location(proc.declaration.fn.__code__.co_filename,
                    proc.declaration.fn.__code__.co_firstlineno, proc.name))) for name, type in proc.params}
                proc.block = self.branch(lambda: proc.declaration.fn(**args), proc.result)
            visiting, visited = set(), set()
            def visit(declaration):
                if declaration in visiting: fail('recursive procedure graphs are unsupported')
                if declaration in visited: return
                visiting.add(declaration)
                for called in self.procedures[declaration].calls: visit(called)
                visiting.remove(declaration)
                visited.add(declaration)
            visit(self.entry)
            return self
        except AuthoringError:
            raise
        finally:
            _ACTIVE.reset(token)
