"""Fresh dynamic authority: immutable pins, atomic progress, and read-only views."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import os
from pathlib import Path, PurePosixPath
from typing import Any

from orchestrator.contracts.output_contract import strict_json_loads
from orchestrator.run_lock import run_root_matches_fd, run_writer_active
from orchestrator.workflow.evaluated.interpreters import pin_command_interpreter, validate_command_interpreter_pin_shape, _valid_digest
from orchestrator.workflow.evaluated.values import _freeze, _thaw
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256, compute_compiler_runtime_identity
from orchestrator.workflow.type_descriptor import validate_transport_value
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow_lisp.dynamic.program import DynamicProgram, _node_children, _pointer

PROFILE = 'dynamic_execution.v1'
SCHEMA_VERSION = '3.1'
HEADER_FIELDS = frozenset({'schema_version', 'result_persistence_profile', 'run_id', 'workflow_file',
    'workflow_checksum', 'started_at', 'program_digest', 'input_digest', 'bound_inputs', 'representation',
    'interpreters', 'workspace', 'runtime_pin', 'provenance_digest'})
STATE_FIELDS = frozenset({'schema_version', 'result_persistence_profile', 'run_id', 'program_digest',
    'updated_at', 'status', 'steps_used', 'current_effect', 'effects', 'workflow_outputs', 'error'})
EFFECT_FIELDS = frozenset({'ordinal', 'definition', 'location', 'effect_class', 'status', 'result_path',
    'stdout_path', 'stderr_path', 'prompt_path', 'started_at', 'finished_at', 'error'})


class DynamicStateError(ValueError):
    code = 'dynamic_state_invalid'


def _now():
    return datetime.now(timezone.utc).isoformat()


def _exact(value, fields, name):
    if not isinstance(value, Mapping) or set(value) != fields:
        raise DynamicStateError(f'{name} has missing or unknown fields')


def _timestamp(value):
    if type(value) is not str:
        raise DynamicStateError('timestamp must be a string')
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('timestamp has no timezone')
    except ValueError as exc:
        raise DynamicStateError('invalid timestamp') from exc
    return parsed


def _locator(value, *, absolute=False):
    if type(value) is not str or not value or '\x00' in value or '\\' in value:
        raise DynamicStateError('invalid locator')
    path = PurePosixPath(value)
    if '..' in path.parts or path.as_posix() != value or value.startswith('//') or (absolute and not path.is_absolute()):
        raise DynamicStateError('noncanonical locator')
    if value.startswith('/dev/fd/') or (value.startswith('/proc/') and 'fd' in path.parts):
        raise DynamicStateError('descriptor locator is not durable')
    return path


def _stored_path(value, descriptor):
    # Stored schemas check durable path shape without reobserving original assets.
    path = _locator(value)
    under = PurePosixPath(descriptor['under'])
    if path.is_absolute() or not path.is_relative_to(under):
        raise DynamicStateError('stored schema path escapes its declared root')
    return value


def _schema_value(value, descriptor):
    normalized = validate_transport_value(_thaw(value), descriptor, allow_nested_structures=True,
        require_int64=True, redact_runtime_keys=True, path_validator=_stored_path)
    if canonical_json_bytes(normalized) != canonical_json_bytes(_thaw(value)):
        raise DynamicStateError('stored value is not canonical')


def _effect_nodes(program):
    nodes = {}
    for code, definition in program.definitions.items():
        stack = [(_pointer(_pointer('/definitions', code), 'body'), definition['body'])]
        while stack:
            pointer, node = stack.pop()
            if node['k'] == 'perform':
                nodes[pointer] = (code, node)
            stack.extend(_node_children(node, pointer))
    return nodes


def _interpreter_tokens(program):
    return {node['command'][0] for _, node in _effect_nodes(program).values()
            if node['class'] == 'command' and '/' not in node['command'][0]}


def _safe_error(value):
    _exact(value, {'code', 'message', 'location', 'metadata'}, 'error')
    if type(value['code']) is not str or not value['code'] or type(value['message']) is not str:
        raise DynamicStateError('invalid error code/message')
    if value['location'] is not None and type(value['location']) is not str:
        raise DynamicStateError('invalid error location')
    if not isinstance(value['metadata'], Mapping):
        raise DynamicStateError('invalid error metadata')
    canonical_json_bytes(_thaw(value))


def error_payload(exc):
    return {'code': getattr(exc, 'code', 'dynamic_execution_failed'), 'message': str(exc),
            'location': getattr(exc, 'location', None), 'metadata': _thaw(getattr(exc, 'metadata', {}))}


def validate_header(header, program, run_root):
    _exact(header, HEADER_FIELDS, 'run header')
    if (header['schema_version'], header['result_persistence_profile']) != (SCHEMA_VERSION, PROFILE):
        raise DynamicStateError('unsupported dynamic authority profile/schema')
    if type(header['run_id']) is not str or header['run_id'] != Path(run_root).name:
        raise DynamicStateError('run identity differs from root')
    if header['representation'] != 'dynamic/1' or header['program_digest'] != program.semantic_digest or header['provenance_digest'] != program.provenance_digest:
        raise DynamicStateError('program pins differ from checked artifact')
    for field in ('workflow_checksum', 'program_digest', 'input_digest', 'runtime_pin', 'provenance_digest'):
        if not _valid_digest(header[field]):
            raise DynamicStateError(f'invalid {field}')
    if header['workflow_checksum'] not in {source['source_sha256'] for source in program.sources.values()}:
        raise DynamicStateError('workflow checksum differs from captured sources')
    _locator(header['workflow_file'])
    _locator(header['workspace'], absolute=True)
    _timestamp(header['started_at'])
    entry = program.definitions[program.entry]['boundary']
    inputs = header['bound_inputs']
    if not isinstance(inputs, Mapping) or set(inputs) != {name for name, _ in entry['params']}:
        raise DynamicStateError('bound inputs differ from checked entry')
    for name, schema in entry['params']:
        _schema_value(inputs[name], program.schemas[schema])
    if canonical_sha256(_thaw(inputs)) != header['input_digest']:
        raise DynamicStateError('input digest differs from bound inputs')
    pins = header['interpreters']
    if not isinstance(pins, Mapping) or set(pins) != _interpreter_tokens(program):
        raise DynamicStateError('interpreter pins differ from checked commands')
    for pin in pins.values():
        validate_command_interpreter_pin_shape(pin)


def effect_paths(ordinal, effect_class):
    root = f'effects/{ordinal}/attempt-1'
    return {'result_path': f'{root}/result.json', 'stdout_path': f'{root}/stdout.txt',
            'stderr_path': f'{root}/stderr.txt', 'prompt_path': f'{root}/prompt.txt' if effect_class == 'provider' else None}


def validate_state(state, header, program, files):
    _exact(state, STATE_FIELDS, 'state')
    for field in ('schema_version', 'result_persistence_profile', 'run_id', 'program_digest'):
        if state[field] != header[field]:
            raise DynamicStateError(f'state {field} differs from header')
    updated = _timestamp(state['updated_at'])
    if updated < _timestamp(header['started_at']):
        raise DynamicStateError('state predates run')
    if type(state['steps_used']) is not int or not 0 <= state['steps_used'] <= program.budget:
        raise DynamicStateError('steps_used outside evaluation budget')
    if state['status'] not in {'running', 'completed', 'failed'}:
        raise DynamicStateError('invalid stored status')
    rows = state['effects']
    if not isinstance(rows, (list, tuple)):
        raise DynamicStateError('effects is not an ordered array')
    nodes = _effect_nodes(program)
    running = None
    failed = False
    for ordinal, row in enumerate(rows, 1):
        _exact(row, EFFECT_FIELDS, 'effect row')
        if type(row['ordinal']) is not int or row['ordinal'] != ordinal:
            raise DynamicStateError('effect ordinals must be contiguous positive integers')
        source = nodes.get(row['location'])
        if source is None or source[0] != row['definition'] or source[1]['class'] != row['effect_class']:
            raise DynamicStateError('effect source does not identify checked code')
        if row['status'] not in {'running', 'completed', 'failed'}:
            raise DynamicStateError('invalid effect status')
        for field, expected in effect_paths(ordinal, row['effect_class']).items():
            if row[field] != expected:
                raise DynamicStateError('effect paths differ from prescribed attempt')
            if expected is not None:
                files.relative(expected)
                # Existing parent components must remain within the descriptor owner.
                files.exists(expected)
        started = _timestamp(row['started_at'])
        if started < _timestamp(header['started_at']) or started > updated:
            raise DynamicStateError('effect start timestamp outside run')
        if failed:
            raise DynamicStateError('effect follows a failed invocation')
        if row['status'] == 'running':
            if ordinal != len(rows) or row['finished_at'] is not None or row['error'] is not None:
                raise DynamicStateError('only the final effect may be running')
            running = ordinal
        else:
            finished = _timestamp(row['finished_at'])
            if finished < started or finished > updated:
                raise DynamicStateError('effect finish timestamp outside invocation')
            if row['status'] == 'failed':
                _safe_error(row['error']); failed = True
            elif row['error'] is not None:
                raise DynamicStateError('completed effect has an error')
    if state['current_effect'] is not None and type(state['current_effect']) is not int:
        raise DynamicStateError('invalid current effect')
    if state['current_effect'] != running:
        raise DynamicStateError('current effect differs from final running row')
    if state['status'] == 'completed':
        if running is not None or failed or state['error'] is not None:
            raise DynamicStateError('completed state has unfinished/failed effect or error')
        boundary = program.definitions[program.entry]['boundary']
        _schema_value(state['workflow_outputs'], program.schemas[boundary['result']])
    elif state['status'] == 'failed':
        if running is not None or state['workflow_outputs'] is not None:
            raise DynamicStateError('failed state has an active effect or result')
        _safe_error(state['error'])
    elif state['workflow_outputs'] is not None or state['error'] is not None:
        raise DynamicStateError('running state has a terminal result/error')


class DynamicRun:
    """One descriptor-pinned writer; a failed write/allocation permanently stops it."""
    def __init__(self, files, program, header, state):
        self.files = files
        self.program = program
        self.header = _freeze(header)
        self.state = _freeze(state)
        self._stopped = False

    def _write(self, candidate):
        if self._stopped or self.state['status'] != 'running':
            raise DynamicStateError('dynamic writer is stopped or terminal')
        try:
            if not run_root_matches_fd(self.files.workspace, self.files.root_fd):
                raise DynamicStateError('run root no longer matches pinned descriptor')
            candidate['updated_at'] = _now()
            if candidate['steps_used'] < self.state['steps_used']:
                raise DynamicStateError('steps_used cannot decrease')
            validate_state(candidate, self.header, self.program, self.files)
            self.files.write_atomic('state.json', canonical_json_bytes(candidate) + b'\n')
            self.state = _freeze(candidate)
        except BaseException:
            self._stopped = True
            raise

    def start_effect(self, definition, location, effect_class, *, steps):
        if self.state['current_effect'] is not None or any(row['status'] == 'failed' for row in self.state['effects']):
            raise DynamicStateError('cannot start another effect before settlement')
        ordinal = len(self.state['effects']) + 1
        row = {'ordinal': ordinal, 'definition': definition, 'location': location,
               'effect_class': effect_class, 'status': 'running', **effect_paths(ordinal, effect_class),
               'started_at': _now(), 'finished_at': None, 'error': None}
        candidate = _thaw(self.state)
        candidate['effects'].append(row)
        candidate.update(current_effect=ordinal, steps_used=steps)
        self._write(candidate)
        try:
            directory = self.files.mkdir_exclusive(f'effects/{ordinal}')
            try:
                attempt = directory.mkdir_exclusive('attempt-1')
                attempt.close()
            finally:
                directory.close()
        except BaseException:
            self._stopped = True
            raise
        return self.state['effects'][-1]

    def finish_effect(self, *, steps, error=None):
        if self.state['current_effect'] is None:
            raise DynamicStateError('no effect is running')
        candidate = _thaw(self.state)
        candidate['effects'][-1].update(status='failed' if error is not None else 'completed',
                                      finished_at=_now(), error=error)
        candidate.update(current_effect=None, steps_used=steps)
        self._write(candidate)

    def complete(self, value, *, steps):
        candidate = _thaw(self.state)
        candidate.update(status='completed', workflow_outputs=_thaw(value), steps_used=steps)
        self._write(candidate)

    def fail(self, error, *, steps):
        candidate = _thaw(self.state)
        candidate.update(status='failed', error=_thaw(error), steps_used=steps)
        self._write(candidate)


def publish_dynamic_run(files, program, *, run_id, workflow_file, workflow_checksum, bound_inputs, workspace):
    """Publish all three exact authority files before evaluating any dynamic body."""
    if not run_root_matches_fd(files.workspace, files.root_fd):
        raise DynamicStateError('run root no longer matches pinned descriptor')
    for name in ('closed_program.json', 'run.json', 'state.json', 'memo.jsonl'):
        if files.exists(name):
            raise FileExistsError(f'dynamic authority already exists: {name}')
    checked = DynamicProgram.from_artifact(program.artifact())
    header = {'schema_version': SCHEMA_VERSION, 'result_persistence_profile': PROFILE, 'run_id': run_id,
        'workflow_file': workflow_file, 'workflow_checksum': workflow_checksum, 'started_at': _now(),
        'program_digest': checked.semantic_digest, 'input_digest': canonical_sha256(_thaw(bound_inputs)),
        'bound_inputs': _thaw(bound_inputs), 'representation': 'dynamic/1',
        'interpreters': {token: pin_command_interpreter((token,)) for token in sorted(_interpreter_tokens(checked))},
        'workspace': str(Path(os.path.abspath(workspace))), 'runtime_pin': compute_compiler_runtime_identity().digest,
        'provenance_digest': checked.provenance_digest}
    state = {'schema_version': SCHEMA_VERSION, 'result_persistence_profile': PROFILE, 'run_id': run_id,
        'program_digest': checked.semantic_digest, 'updated_at': _now(), 'status': 'running', 'steps_used': 0,
        'current_effect': None, 'effects': [], 'workflow_outputs': None, 'error': None}
    validate_header(header, checked, files.workspace)
    validate_state(state, header, checked, files)
    files.create('closed_program.json', checked.artifact().encode(), exclusive=True)
    persisted = DynamicProgram.from_artifact(files.read('closed_program.json'))
    validate_header(header, persisted, files.workspace)
    files.create('run.json', canonical_json_bytes(header) + b'\n', exclusive=True)
    files.write_atomic('state.json', canonical_json_bytes(state) + b'\n')
    return DynamicRun(files, persisted, header, state)


def load_dynamic_run(run_root, *, run_files=None):
    """Read exact authority once without source/executable reads, repair, or replay."""
    own = run_files is None
    files = run_files
    try:
        if files is None:
            files = WorkspaceFiles(run_root)
        if not run_root_matches_fd(run_root, files.root_fd):
            raise DynamicStateError('run root no longer matches pinned descriptor')
        header = strict_json_loads(files.read('run.json'))
        program = DynamicProgram.from_artifact(files.read('closed_program.json'))
        state = strict_json_loads(files.read('state.json'))
        if files.exists('memo.jsonl'):
            raise DynamicStateError('dynamic authority cannot contain a memo')
        validate_header(header, program, run_root)
        validate_state(state, header, program, files)
        return _freeze(header), program, _freeze(state)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        if isinstance(exc, DynamicStateError):
            raise
        raise DynamicStateError(f'invalid dynamic authority: {exc}') from exc
    finally:
        if own and files is not None:
            files.close()


def load_dynamic_view(run_root, *, run_files=None):
    """Validated native scalar/progress view; interruption is a liveness result."""
    files = run_files
    own = files is None
    try:
        if files is None:
            files = WorkspaceFiles(run_root)
        header, program, state = load_dynamic_run(run_root, run_files=files)
        view = _thaw(state)
        if view['status'] == 'running' and not run_writer_active(Path(run_root), root_fd=files.root_fd):
            view['status'] = 'interrupted'
        view.update(resumable=False, workflow_file=header['workflow_file'], workspace=header['workspace'],
                    started_at=header['started_at'], budget=program.budget)
        return view
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, DynamicStateError): raise
        raise DynamicStateError(f'invalid dynamic view: {exc}') from exc
    finally:
        if own and files is not None: files.close()
