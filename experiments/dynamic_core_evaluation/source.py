"""Bounded experimental source lowering; boundary types use the existing compiler."""
from __future__ import annotations

import json

from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow_lisp.normalized_type_descriptor import compiler_normalized_type_descriptor
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import (
    BoolAtom, FloatAtom, IntAtom, KeywordAtom, ListExpr, StringAtom, SymbolAtom,
)

from .program import DynamicProgram, EFFECT_SCHEMA, _OPERATORS, _pointer


_FORMS = {'dynamic-core', 'define', 'run', 'fn', 'let*', 'if', 'record',
          'field', 'list', 'at', 'effect'}
_RESERVED = _FORMS | _OPERATORS


def _invalid(node, message):
    pos = node.span.start
    return EvaluatedValueError('dynamic_source_invalid', message,
                               location=f'{pos.path}:{pos.line}:{pos.column}')


def _items(node, size=None):
    if not isinstance(node, ListExpr) or (size is not None and len(node.items) != size):
        raise _invalid(node, 'malformed source form')
    return node.items


def _symbol(node, *, binder=False):
    if not isinstance(node, SymbolAtom) or not node.value or (binder and node.value in _RESERVED):
        raise _invalid(node, 'expected an ordinary name')
    return node.value


def _binders(nodes):
    names = [_symbol(node, binder=True) for node in nodes]
    if len(set(names)) != len(names):
        raise _invalid(nodes[-1], 'duplicate binding name')
    return names


def compile_source(text, *, source_path, type_env):
    """Read one dynamic-core form and admit its inferred-closure artifact."""
    try:
        return _compile_source(text, source_path=source_path, type_env=type_env)
    except RecursionError as exc:
        # ponytail: retain frontend depth ceilings; iterate only if deep source is needed.
        raise EvaluatedValueError(
            'dynamic_source_invalid', 'source nesting exceeds the bounded frontend',
            location=f'{source_path}:1:1',
        ) from exc


def _compile_source(text, *, source_path, type_env):
    document = read_sexpr_text(text, source_path=str(source_path))
    if len(document.items) != 1:
        raise _invalid(document, 'expected one dynamic-core form')
    outer = document.items[0]
    items = _items(outer)
    if len(items) < 6 or _symbol(items[0]) != 'dynamic-core':
        raise _invalid(outer, 'expected dynamic-core headers and run')
    headers = []
    for node, expected in zip(items[1:5], ('budget', 'inputs', 'result', 'effects')):
        row = _items(node)
        if not row or not isinstance(row[0], KeywordAtom) or row[0].value != ':' + expected:
            raise _invalid(node, f'expected :{expected} header')
        headers.append(row[1:])
    budget, inputs, result, effects = headers
    if len(budget) != 1 or not isinstance(budget[0], IntAtom) or budget[0].value <= 0:
        raise _invalid(items[1], 'budget must be a positive integer')
    if len(result) != 1:
        raise _invalid(items[3], 'result requires one type name')
    input_rows = [_items(node, 2) for node in inputs]
    input_names = _binders([row[0] for row in input_rows])
    effect_names = [_symbol(node) for node in effects]
    if len(set(effect_names)) != len(effect_names):
        raise _invalid(items[4], 'duplicate effect name')
    schemas = {}

    def schema(node):
        name = _symbol(node)
        ref = type_env.resolve_type(name, span=node.span, form_path=('dynamic-core', 'schema'))
        schemas[name] = compiler_normalized_type_descriptor(ref, type_env=type_env)
        return name

    typed_inputs = [[name, schema(row[1])] for name, row in zip(input_names, input_rows)]
    result_name = schema(result[0])
    helpers = {}
    for node in items[5:-1]:
        row = _items(node, 3)
        if _symbol(row[0]) != 'define':
            raise _invalid(node, 'only helper definitions may precede run')
        signature = _items(row[1])
        if not signature:
            raise _invalid(row[1], 'helper requires a name')
        name = _symbol(signature[0], binder=True)
        if name in helpers:
            raise _invalid(signature[0], 'duplicate helper name')
        helpers[name] = (_binders(signature[1:]), row[2])
    run = _items(items[-1], 2)
    if _symbol(run[0]) != 'run':
        raise _invalid(items[-1], 'expected final run')
    definitions = {}

    def helper_code(name):
        return _pointer('helper', name)

    def lower(node, scope, path):
        if isinstance(node, (BoolAtom, IntAtom, FloatAtom, StringAtom)):
            return {'k': 'lit', 'v': node.value}, set()
        if isinstance(node, SymbolAtom):
            if node.value in scope:
                return {'k': 'name', 'n': node.value}, {node.value}
            if node.value in helpers:
                return {'k': 'fn', 'code': helper_code(node.value), 'captures': []}, set()
            raise _invalid(node, f'unbound name {node.value!r}')
        row = _items(node)
        if not row:
            raise _invalid(node, 'empty application')
        head = row[0].value if isinstance(row[0], SymbolAtom) else None

        def children(indexed):
            nodes, free = [], set()
            for index, child in indexed:
                lowered, used = lower(child, scope, _pointer(path, index))
                nodes.append(lowered)
                free.update(used)
            return nodes, free

        if head == 'fn':
            _items(node, 3)
            params = _binders(_items(row[1]))
            body, free = lower(row[2], scope | set(params), _pointer(path, 2))
            captures = sorted(free - set(params))
            definitions[path] = {'params': params, 'captures': captures, 'body': body}
            return {'k': 'fn', 'code': path,
                    'captures': [{'k': 'name', 'n': name} for name in captures]}, set(captures)
        if head == 'let*':
            _items(node, 3)
            bindings = [_items(binding, 2) for binding in _items(row[1])]
            names = _binders([binding[0] for binding in bindings])
            local, bound, free, lowered = set(scope), set(), set(), []
            for index, (name, binding) in enumerate(zip(names, bindings)):
                value, used = lower(binding[1], local, _pointer(_pointer(path, 1), index))
                free.update(used - bound)
                lowered.append([name, value])
                local.add(name)
                bound.add(name)
            body, used = lower(row[2], local, _pointer(path, 2))
            return {'k': 'let', 'bindings': lowered, 'body': body}, free | (used - bound)
        if head == 'record':
            fields, free, seen = [], set(), set()
            for index, field in enumerate(row[1:], 1):
                key, value = _items(field, 2)
                if not isinstance(key, (SymbolAtom, StringAtom)) or not key.value or key.value in seen:
                    raise _invalid(key, 'record field names must be nonempty and unique')
                seen.add(key.value)
                child, used = lower(value, scope, _pointer(path, index))
                fields.append([key.value, child])
                free.update(used)
            return {'k': 'record', 'fields': fields}, free
        if head == 'field':
            _items(node, 3)
            if not isinstance(row[2], StringAtom) or not row[2].value:
                raise _invalid(row[2], 'field access requires a literal nonempty string')
            base, free = lower(row[1], scope, _pointer(path, 1))
            return {'k': 'field', 'base': base, 'name': row[2].value}, free
        if head == 'effect':
            _items(node, 3)
            name = _symbol(row[1])
            if name not in effect_names:
                raise _invalid(row[1], 'undeclared effect')
            value, free = lower(row[2], scope, _pointer(path, 2))
            return {'k': 'effect', 'name': name, 'inputs': value}, free
        if head in {'if', 'at'}:
            _items(node, 4 if head == 'if' else 3)
            nodes, free = children(enumerate(row[1:], 1))
            keys = ('cond', 'then', 'else') if head == 'if' else ('base', 'index')
            return {'k': head, **dict(zip(keys, nodes))}, free
        if head == 'list' or head in _OPERATORS:
            nodes, free = children(enumerate(row[1:], 1))
            if head == 'list':
                return {'k': 'list', 'items': nodes}, free
            return {'k': 'op', 'name': head, 'args': nodes}, free
        nodes, free = children(enumerate(row))
        return {'k': 'call', 'callee': nodes[0], 'args': nodes[1:]}, free

    for name, (params, body) in helpers.items():
        code = helper_code(name)
        lowered, _ = lower(body, set(params), _pointer(code, 'body'))
        definitions[code] = {'params': params, 'captures': [], 'body': lowered}
    body, _ = lower(run[1], set(input_names), 'entry/body')
    definitions['entry'] = {'params': input_names, 'captures': [], 'body': body}
    return DynamicProgram.from_artifact(json.dumps({
        'schema': EFFECT_SCHEMA, 'entry': 'entry', 'budget': budget[0].value,
        'schemas': schemas, 'inputs': typed_inputs, 'result': result_name,
        'effects': effect_names, 'definitions': definitions,
    }, ensure_ascii=False, allow_nan=False))
