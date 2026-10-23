"""Finite Python authoring descriptors; ordinary Lisp owns type validation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import inspect
import types
import typing


@dataclass(frozen=True)
class Type:
    kind: str
    name: str
    fields: tuple = ()
    tags: tuple = ()
    members: tuple = ()
    item: Type | None = None
    under: str | None = None
    must_exist: bool = False


@dataclass(frozen=True)
class HostType:
    answer: object


class HostReply:
    """Descriptor for the ordinary imported std/host::HostReply, never a value."""
    def __class_getitem__(cls, answer):
        return HostType(answer)


def _decorate(cls, kind):
    if cls.__bases__ != (object,) or getattr(cls, '__parameters__', ()):
        raise TypeError('record/variant inheritance and generics are unsupported')
    cls.__orc_kind__ = kind
    cls.__orc_namespace__ = dict(inspect.currentframe().f_back.f_back.f_globals)
    def construct(cls, *args, **kwargs):
        from .trace import current
        return current().construct(cls, args, kwargs)
    cls.__new__ = construct
    return cls


def record(cls):
    return _decorate(cls, 'record')


def variant(cls):
    return _decorate(cls, 'variant')


class RelPath:
    def __init_subclass__(cls, *, under, must_exist=False, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__bases__ != (RelPath,) or not isinstance(under, str) or type(must_exist) is not bool:
            raise TypeError('RelPath requires a string root, boolean must_exist and direct inheritance')
        cls.__orc_under__ = under
        cls.__orc_must_exist__ = must_exist

    def __new__(cls, child):
        from .trace import current
        return current().path(cls, child)


@dataclass(frozen=True)
class Fill:
    kind: str
    type: object = str


Text = Fill('text')


class Doc:
    def __class_getitem__(cls, type): return Fill('doc', type)


class Value:
    def __class_getitem__(cls, type): return Fill('value', type)


class PathOf:
    def __class_getitem__(cls, type): return Fill('path', type)


class Out:
    def __class_getitem__(cls, type): return Fill('out', type)


@dataclass(frozen=True)
class Effect:
    kind: str
    subject: str | None = None


host_input = Effect('host-input')


def uses_provider(name): return Effect('uses-provider', name)


def uses_command(name): return Effect('uses-command', name)


class Types:
    def __init__(self, namespaces):
        self.namespace = {}
        for namespace in namespaces:
            self.namespace.update(namespace)
        self.declarations = {}
        self.owners = {}
        self.resolving = set()
        self.unions = {}
        for name, value in self.namespace.items():
            if typing.get_origin(value) in (typing.Union, types.UnionType):
                args = typing.get_args(value)
                if args and all(isinstance(v, type) and v.__dict__.get('__orc_kind__') == 'variant' for v in args):
                    for cls in args:
                        if cls in self.unions and self.unions[cls][0] != name:
                            raise TypeError(f'ambiguous union membership for {cls.__name__}')
                        self.unions[cls] = (name, value)

    def resolve(self, value):
        if isinstance(value, str):
            value = eval(value, self.namespace)
        primitives = {str: 'String', int: 'Int', float: 'Float', bool: 'Bool'}
        if value in primitives:
            return Type('primitive', primitives[value])
        if isinstance(value, HostType):
            answer = self.resolve(value.answer)
            string = Type('primitive', 'String')
            return Type('host', f'HostReply[{answer.name}]', tags=(('ANSWERED', (('value', answer), ('by', string))),
                ('CANCELLED', (('by', string),)), ('EXPIRED', ())), item=answer)
        origin = typing.get_origin(value)
        if origin is list:
            args = typing.get_args(value)
            if len(args) != 1: raise TypeError('list requires one element type')
            item = self.resolve(args[0])
            return Type('list', f'List[{item.name}]', item=item)
        if origin in (typing.Union, types.UnionType):
            aliases = [name for name, item in self.namespace.items() if item is value]
            if not aliases: raise TypeError('variant unions require a named alias')
            name = aliases[0]
            args = typing.get_args(value)
            if not args or not all(v in self.unions for v in args):
                raise TypeError('only closed decorated variants form unions')
            return self._declare(name, value, lambda: Type('union', name, tags=tuple(
                (cls.__name__, self._fields(cls)) for cls in args)))
        if not isinstance(value, type) or getattr(value, '__parameters__', ()):
            raise TypeError(f'unsupported authoring type {value!r}')
        if issubclass(value, Enum):
            members = tuple((name, member.value) for name, member in value.__members__.items())
            wires = [wire for _, wire in members]
            for wire in wires:
                if not isinstance(wire, str) or not wire or any(c.isspace() for c in wire) or any(c in wire for c in '()[]";:'):
                    raise TypeError('Enum values must be nonempty enum tokens')
            if len(set(wires)) != len(wires): raise TypeError('Enum aliases and duplicate wire values are unsupported')
            return self._declare(value.__name__, value, lambda: Type('enum', value.__name__, members=members))
        if issubclass(value, RelPath) and value is not RelPath:
            return self._declare(value.__name__, value, lambda: Type('path', value.__name__, under=value.__orc_under__, must_exist=value.__orc_must_exist__))
        kind = value.__dict__.get('__orc_kind__')
        if kind == 'record':
            return self._declare(value.__name__, value, lambda: Type('record', value.__name__, fields=self._fields(value)))
        if kind == 'variant' and value in self.unions:
            return self.resolve(self.unions[value][1])
        raise TypeError(f'unsupported authoring type {value!r}')

    def _declare(self, name, owner, make):
        from orchestrator.workflow_lisp.type_env import PRELUDE_TYPE_NAMES
        if name in PRELUDE_TYPE_NAMES | {'Value', 'Agent', 'List', 'HostReply'}:
            raise TypeError(f'reserved authoring type name {name}')
        if name in self.declarations:
            if self.owners[name] is not owner:
                raise TypeError(f'conflicting authoring type name {name}')
            return self.declarations[name]
        if name in self.resolving: raise TypeError(f'recursive type {name} is unsupported')
        self.resolving.add(name)
        try:
            result = make()
            self.declarations[name] = result
            self.owners[name] = owner
            return result
        finally:
            self.resolving.remove(name)

    def _fields(self, cls):
        namespace = {**getattr(cls, '__orc_namespace__', {}), **self.namespace}
        annotations = typing.get_type_hints(cls, globalns=namespace, localns=namespace)
        return tuple((name, self.resolve(type)) for name, type in annotations.items())
