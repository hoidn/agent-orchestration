"""Emit regular Workflow Lisp and supplementary Python attribution."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re

from .trace import AppliedPrompt, AuthoringError, Declaration, Location, Trace, fail

EMITTER_VERSION = 'workflow-python/1'


def token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_./-]*', value):
        fail(f'invalid source identifier {value!r}')
    return value


def literal(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class Emission:
    module: str
    source: bytes
    source_map: bytes
    templates: tuple[bytes, ...]


class Emitter:
    def __init__(self, trace, workspace):
        self.trace, self.workspace = trace, workspace
        self.parts, self.entries = [], []
        self.offset = 0

    def write(self, text):
        self.parts.append(text)
        self.offset += len(text)

    def mapped(self, loc, callback):
        start = self.offset
        callback()
        try:
            path = Path(os.path.abspath(loc.path)).relative_to(self.workspace).as_posix()
        except ValueError:
            fail('authoring source must be inside the workspace', loc)
        self.entries.append({'start': start, 'end': self.offset, 'file': path,
            'line': loc.line, 'definition': loc.definition})

    def prompt(self, applied):
        self.write(f'({applied.name}')
        for name, expr in applied.fills:
            self.write(f' :{token(name)} ')
            self.expr(expr)
        self.write(')')

    def expr(self, expr):
        self.mapped(expr.loc, lambda: self._expr(expr))

    def _expr(self, expr):
        kind, data, type = expr.kind, expr.data, expr.type
        if kind == 'literal': self.write(literal(data))
        elif kind == 'name': self.write(token(data))
        elif kind == 'enum': self.write(f'{token(type.name)}.{token(data)}')
        elif kind == 'field':
            base, name = data
            if base.kind == 'name' or base.kind == 'field':
                self.expr(base)
                self.write('.' + token(name))
            else:
                fail('project fields from a bound symbolic value', expr.loc)
        elif kind in ('record', 'variant'):
            self.write(f'({kind} {token(type.name)}')
            fields = data
            if kind == 'variant':
                tag, fields = data
                self.write(' ' + token(tag))
            for name, value in fields:
                self.write(f' :{token(name)} ')
                self.expr(value)
            self.write(')')
        elif kind == 'list':
            self.write('(list')
            for value in data:
                self.write(' ')
                self.expr(value)
            self.write(')')
        elif kind == 'path':
            self.write(f'(path/join-under {token(type.name)} ')
            self.expr(data)
            self.write(')')
        elif kind == 'call':
            name, args = data
            self.write('(' + token(name))
            for value in args:
                self.write(' ')
                self.expr(value)
            self.write(')')
        elif kind == 'command':
            name, args = data
            self.write(f'(command-result {token(name)} :argv (')
            for index, value in enumerate(args):
                if index: self.write(' ')
                self.expr(value)
            self.write(f') :returns {type.name})')
        elif kind == 'provider':
            name, prompt, options = data
            self.write(f'(provider-result {token(name)} :prompt ')
            self.prompt(prompt)
            for key, value in options:
                self.write(' :' + key + ' ')
                self.expr(value)
            self.write(')')
        elif kind == 'ask':
            question, answer, timeout, show = data
            self.write('(request-input ')
            self.prompt(question) if isinstance(question, AppliedPrompt) else self.expr(question)
            self.write(f' :returns {answer.name}')
            if timeout is not None:
                self.write(' :timeout-sec ')
                self.expr(timeout)
            if show:
                self.write(' :show (')
                for index, value in enumerate(show):
                    if index: self.write(' ')
                    self.expr(value)
                self.write(')')
            self.write(')')
        elif kind == 'if':
            condition, yes, no = data
            self.write('(if ')
            self.expr(condition)
            self.write('\n')
            self.block(yes)
            self.write('\n')
            self.block(no)
            self.write(')')
        elif kind == 'match':
            subject, arms = data
            if subject.type.kind == 'enum':
                for index, (name, binder, block) in enumerate(arms):
                    if index < len(arms) - 1:
                        wire = dict(subject.type.members)[name]
                        self.write('(if (= ')
                        self.expr(subject)
                        self.write(f' {token(subject.type.name)}.{token(wire)})\n')
                    self.write(f'(let* (({binder} ')
                    self.expr(subject)
                    self.write(')) ')
                    self.block(block)
                    self.write(')\n')
                self.write(')' * (len(arms) - 1))
            else:
                self.write('(match ')
                self.expr(subject)
                for tag, binder, block in arms:
                    self.write(f'\n(({token(tag)} {binder}) ')
                    self.block(block)
                    self.write(')')
                self.write(')')
        else: fail(f'unsupported traced expression {kind}', expr.loc)

    def block(self, block):
        if block.bindings:
            self.write('(let* (')
            for index, (name, value) in enumerate(block.bindings):
                if index: self.write('\n')
                self.write(f'({name} ')
                self.expr(value)
                self.write(')')
            self.write(')\n')
        self.expr(block.result)
        if block.bindings: self.write(')')

    def emit(self):
        module = token(self.trace.entry.__name__)
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', module):
            fail('generated module requires a simple Python identifier')
        self.write(f'(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n(defmodule {module})\n(import std/host :only (HostReply))\n(export {module})\n')
        for type in self.trace.types.declarations.values():
            name = token(type.name)
            if type.kind == 'enum': self.write(f'(defenum {name} ' + ' '.join(token(v) for _, v in type.members) + ')\n')
            elif type.kind == 'record': self.write(f'(defrecord {name}' + ''.join(f' ({token(n)} {t.name})' for n, t in type.fields) + ')\n')
            elif type.kind == 'union': self.write(f'(defunion {name}' + ''.join(f' ({token(n)}' + ''.join(f' ({token(f)} {t.name})' for f, t in fields) + ')' for n, fields in type.tags) + ')\n')
            elif type.kind == 'path': self.write(f'(defpath {name} :kind relpath :under {literal(type.under)} :must-exist {literal(type.must_exist)})\n')
        for prompt, (name, template) in self.trace.prompts.items():
            def emit_prompt():
                self.write(f'(defprompt {name} (:fills')
                for fill_name, fill in prompt.fills.items():
                    suffix = '' if fill.kind == 'text' else ' ' + self.trace.types.resolve(fill.type).name
                    kind = 'path :out' if fill.kind == 'out' else fill.kind
                    self.write(f' ({token(fill_name)} :{kind}{suffix})')
                self.write(f') -> {self.trace.types.resolve(prompt.returns).name} {literal(template)})\n')
            self.mapped(prompt.loc, emit_prompt)
        for proc in self.trace.procedures.values():
            fn = proc.declaration.fn
            from .trace import Location, _OMITTED
            def emit_proc():
                self.write(f'(def{proc.declaration.kind} {token(proc.name)} (' + ' '.join(f'({token(n)} {t.name})' for n, t in proc.params) + f') -> {proc.result.name}\n')
                if proc.declaration.effects is not _OMITTED:
                    self.write(':effects (')
                    for effect in proc.declaration.effects:
                        if not isinstance(effect, Effect): fail('effects require effect descriptors')
                        self.write('(' + token(effect.kind) + (' ' + token(effect.subject) if effect.subject is not None else '') + ')')
                    self.write(')\n')
                self.block(proc.block)
                self.write(')\n')
            from .types import Effect
            self.mapped(Location(fn.__code__.co_filename, fn.__code__.co_firstlineno, proc.name), emit_proc)
        self.write(')\n')
        source = ''.join(self.parts)
        files = sorted({entry['file'] for entry in self.entries})
        source_map = {'schema': EMITTER_VERSION, 'sources': {name: hashlib.sha256((self.workspace / name).read_bytes()).hexdigest() for name in files}, 'entries': self.entries}
        return Emission(module, source.encode('utf-8'), json.dumps(source_map, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8'),
            tuple(template.encode('utf-8') for _, template in self.trace.prompts.values()))


def emit(entry, workspace):
    if not isinstance(entry, Declaration) or entry.kind != 'workflow': fail('build requires a decorated workflow')
    try:
        trace = Trace(entry, workspace).run()
        return Emitter(trace, workspace).emit()
    except AuthoringError:
        raise
    except (TypeError, ValueError, NameError, AttributeError) as exc:
        code = entry.fn.__code__
        origin = Location(code.co_filename, code.co_firstlineno, code.co_name)
        frame = exc.__traceback__
        while frame is not None:
            filename = Path(frame.tb_frame.f_code.co_filename)
            if filename.is_relative_to(workspace) and filename.parent != Path(__file__).parent:
                origin = Location(str(filename), frame.tb_lineno, frame.tb_frame.f_code.co_name)
            frame = frame.tb_next
        fail(str(exc), origin)
