"""Immutable source publication followed by the existing checked compiler."""
from __future__ import annotations

from dataclasses import dataclass, replace
import errno
import hashlib
import json
import os
from pathlib import Path
import secrets

from orchestrator._common.io_atomic import rename_noreplace_at
from orchestrator._common.safe_tree import open_directory, read_regular_file, remove_tree_contents
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import ClosedProgramBuildResult, build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from .emit import EMITTER_VERSION, emit


@dataclass(frozen=True)
class PythonBuildResult:
    source_path: Path
    source_map_path: Path
    request: FrontendBuildRequest
    closed_result: ClosedProgramBuildResult


def _open_child(parent, name):
    try:
        os.mkdir(name, dir_fd=parent)
        os.fsync(parent)
    except FileExistsError:
        pass
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)


def _verify(directory, expected):
    if set(os.listdir(directory)) != set(expected):
        raise ValueError('generated bundle has unexpected or missing files')
    for name, data in expected.items():
        if read_regular_file(directory, name) != data:
            raise ValueError(f'generated bundle content differs: {name}')


def _publish(workspace, module, digest, expected):
    parents = [open_directory(str(workspace))]
    temporary = None
    temporary_fd = None
    try:
        for component in ('.orchestrate', 'generated', module):
            parents.append(_open_child(parents[-1], component))
        parent = parents[-1]
        try:
            existing = os.open(digest, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            try: _verify(existing, expected)
            finally: os.close(existing)
            return
        temporary = '.tmp-' + secrets.token_hex(12)
        os.mkdir(temporary, dir_fd=parent)
        temporary_fd = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        for name, data in expected.items():
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=temporary_fd)
            try:
                remaining = memoryview(data)
                while remaining:
                    written = os.write(fd, remaining)
                    if written <= 0: raise OSError('generated bundle write made no progress')
                    remaining = remaining[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
        os.fsync(temporary_fd)
        try:
            rename_noreplace_at(parent, temporary, parent, digest)
            temporary = None
        except OSError as exc:
            if exc.errno != errno.EEXIST: raise
            existing = os.open(digest, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try: _verify(existing, expected)
            finally: os.close(existing)
        os.fsync(parent)
    finally:
        if temporary_fd is not None:
            if temporary is not None: remove_tree_contents(temporary_fd)
            os.close(temporary_fd)
        if temporary is not None: os.rmdir(temporary, dir_fd=parents[-1])
        for fd in reversed(parents): os.close(fd)


def _mapped_error(error, source_map):
    entries = json.loads(source_map)['entries']
    diagnostics = []
    for diagnostic in error.diagnostics:
        offset = diagnostic.span.start.offset
        candidates = [entry for entry in entries if entry['start'] <= offset < entry['end']]
        if candidates:
            entry = min(candidates, key=lambda entry: entry['end'] - entry['start'])
            note = f'Python {entry["file"]}:{entry["line"]} ({entry["definition"]})'
            diagnostic = replace(diagnostic, notes=(*diagnostic.notes, note))
        diagnostics.append(diagnostic)
    return LispFrontendCompileError(tuple(diagnostics))


def build(workflow, *, workspace=None, provider_externs_file=None, prompt_externs_file=None,
          command_boundaries_file=None, source_roots=()):
    workspace = Path(os.path.abspath(workspace or Path.cwd()))
    emission = emit(workflow, workspace)
    identity = json.dumps({'version': EMITTER_VERSION, 'source': emission.source.hex(),
        'source_map': emission.source_map.hex(), 'templates': [data.hex() for data in emission.templates]},
        sort_keys=True, separators=(',', ':')).encode('utf-8')
    digest = hashlib.sha256(identity).hexdigest()
    root = workspace / '.orchestrate' / 'generated' / emission.module / digest
    source = root / f'{emission.module}.orc'
    source_map = root / 'source_map.json'
    _publish(workspace, emission.module, digest, {source.name: emission.source, source_map.name: emission.source_map})
    request = FrontendBuildRequest(source_path=source, workspace_root=workspace,
        source_roots=(root, *(Path(path) for path in source_roots)), entry_workflow=workflow.__name__,
        provider_externs_path=Path(provider_externs_file) if provider_externs_file is not None else None,
        prompt_externs_path=Path(prompt_externs_file) if prompt_externs_file is not None else None,
        command_boundaries_path=Path(command_boundaries_file) if command_boundaries_file is not None else None)
    try:
        closed = build_closed_program_bundle(request)
    except LispFrontendCompileError as exc:
        raise _mapped_error(exc, emission.source_map) from exc
    return PythonBuildResult(source, source_map, request, closed)
