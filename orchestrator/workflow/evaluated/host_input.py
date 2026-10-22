"""Durable serial host requests; memo rows own requests and replies."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import errno
import hashlib
import math
from pathlib import Path
import time

from orchestrator.workflow.run_ref.contracts import canonical_sha256, canonical_json_bytes
from orchestrator.workflow.type_descriptor import validate_transport_value, validate_compiler_normalized_type_descriptor
from orchestrator.workflow.workspace_files import WorkspaceFiles
from .values import _thaw
from orchestrator.workflow.pure_expr import _validate_pure_path_value


class HostInputError(ValueError):
    def __init__(self, code, message=''):
        self.code = code
        self.preflight = True
        super().__init__(f'{code}: {message}')


class HostInputSuspended(Exception):
    """Deliberate nonterminal exit, never a failed effect."""


def _require(condition, detail):
    if not condition:
        raise HostInputError('memo_inconsistent', detail)


def _keys(value, keys):
    _require(isinstance(value, dict) and set(value) == set(keys), 'host payload fields differ')


def _digest(value):
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def _finite_time(value):
    try:
        return type(value) in {int, float} and math.isfinite(value)
    except OverflowError:
        return False


def _principal(value):
    if not isinstance(value, str) or not value.strip() or '\0' in value:
        raise HostInputError('host_input_invalid_principal', 'by must be nonempty NUL-free text')
    return value


def _request_id(authority, identity, attempt):
    return canonical_sha256(dict(schema_version=1, run_id=authority.header['run_id'],
        header_digest=canonical_sha256(authority.header), program_digest=authority.program.digest,
        identity=identity, attempt=attempt))


def validate_request_payload(request):
    """Structural validation is also used by the pure memo reducer."""
    _keys(request, ('schema_version', 'request_id', 'question', 'question_digest',
        'answer_contract', 'answer_contract_digest', 'reply_contract', 'reply_contract_digest',
        'show', 'created_at', 'deadline', 'timeout_sec', 'depends_on', 'payload_digest'))
    _require(type(request['schema_version']) is int and request['schema_version'] == 1, 'unsupported host payload schema')
    from .memo_reducer import _digest as check_digest
    check_digest(request['request_id'], 'request_id')
    _require(isinstance(request['question'], str), 'question must be text')
    _require(request['question_digest'] == _digest(request['question'].encode('utf-8')), 'question digest differs')
    for name in ('answer_contract', 'reply_contract'):
        validate_compiler_normalized_type_descriptor(request[name])
        _require(request[name + '_digest'] == canonical_sha256(request[name]), 'contract digest differs')
    answer = request['answer_contract']
    from orchestrator.workflow.type_descriptor import is_transportable_type_descriptor
    _require((answer == {'kind': 'primitive', 'name': 'String'} or answer['kind'] in {'enum', 'union'})
        and is_transportable_type_descriptor(answer, allow_nested_structures=True), 'answer is not transportable')
    string = {'kind': 'primitive', 'name': 'String'}
    expected = {'kind': 'union', 'name': f"std/host::HostReply[{answer['name']}]", 'variants': [
        {'name': 'ANSWERED', 'fields': [{'name': 'value', 'type': answer}, {'name': 'by', 'type': string}]},
        {'name': 'CANCELLED', 'fields': [{'name': 'by', 'type': string}]}, {'name': 'EXPIRED', 'fields': []}]}
    _require(request['reply_contract'] == expected, 'reply is not canonical HostReply')
    _require(_finite_time(request['created_at']), 'invalid host creation time')
    duration = request['timeout_sec']
    _require(duration is None or type(duration) is int and duration > 0, 'invalid timeout')
    deadline = request['deadline']
    _require(deadline is None if duration is None else _finite_time(deadline) and deadline == request['created_at'] + duration,
        'deadline differs from creation and duration')
    _require(isinstance(request['depends_on'], list) and all(isinstance(v, str) and v for v in request['depends_on'])
        and request['depends_on'] == sorted(set(request['depends_on'])), 'invalid host dependencies')
    _require(isinstance(request['show'], list), 'show must be an array')
    for row in request['show']:
        _keys(row, ('path', 'contract', 'sha256'))
        validate_compiler_normalized_type_descriptor(row['contract'])
        _require(row['contract']['kind'] == 'path', 'show contract is not a path')
        validate_transport_value(row['path'], row['contract'], path_validator=_validate_pure_path_value)
        check_digest(row['sha256'], 'shown sha256')
    _require(request['payload_digest'] == canonical_sha256({k: v for k, v in request.items() if k != 'payload_digest'}),
        'frozen payload digest differs')
    return request


def validate_reply_payload(request, row):
    """Validate inline value and provenance without reading any mutable evidence."""
    value = validate_transport_value(row['value'], request['reply_contract'], allow_nested_structures=True, path_validator=_validate_pure_path_value)
    _require(row['result_digest'] == canonical_sha256(value), 'host result digest differs')
    reply = row.get('host_reply')
    variant = value['variant']
    if variant == 'EXPIRED':
        _keys(reply, ('request_id', 'origin', 'reason', 'accept_changed_evidence', 'evidence_changes'))
        _require(reply['origin'] == 'runtime' and reply['reason'] == 'deadline'
            and reply['accept_changed_evidence'] is False and reply['evidence_changes'] == [], 'invalid expiration provenance')
        _require(request['deadline'] is not None and row['time'] >= request['deadline'], 'premature expiration')
    else:
        _keys(reply, ('request_id', 'origin', 'attestation', 'accept_changed_evidence', 'evidence_changes'))
        _require(reply['origin'] == 'host', 'invalid host origin')
        _principal(value['by'])
        _require(reply['attestation'] is None or isinstance(reply['attestation'], str), 'attestation must be opaque text')
        _require(request['deadline'] is None or row['time'] < request['deadline'], 'late host commit')
    _require(reply['request_id'] == request['request_id'], 'host reply id differs')
    _require(type(reply['accept_changed_evidence']) is bool and isinstance(reply['evidence_changes'], list), 'invalid evidence override')
    _require(reply['accept_changed_evidence'] or not reply['evidence_changes'], 'unaccepted evidence drift')
    seen = set()
    for change in reply['evidence_changes']:
        _keys(change, ('index', 'path', 'original_sha256', 'observed'))
        index = change['index']
        _require(type(index) is int and 0 <= index < len(request['show']) and index not in seen, 'invalid changed evidence index')
        seen.add(index)
        original = request['show'][index]
        _require(change['path'] == original['path'] and change['original_sha256'] == original['sha256'], 'changed evidence differs from request')
        observed = change['observed']
        _require(isinstance(observed, dict), 'invalid observed evidence')
        status = observed.get('status')
        if status == 'present':
            _keys(observed, ('status', 'sha256'))
            from .memo_reducer import _digest as check_digest
            check_digest(observed['sha256'], 'observed sha256')
            _require(observed['sha256'] != original['sha256'], 'unchanged evidence marked changed')
        else:
            _require(status in {'missing', 'unreadable'}, 'unsafe evidence cannot be waived')
            _keys(observed, ('status', 'errno'))
            _require(type(observed['errno']) is int and observed['errno'] > 0, 'invalid evidence errno')
    return value


def validate_request_start_binding(row):
    request = validate_request_payload(row['host_request'])
    parts = row['input_parts']
    expected = dict(question=request['question_digest'], answer_contract=request['answer_contract_digest'],
        reply_contract=request['reply_contract_digest'], timeout_sec=canonical_sha256(request['timeout_sec']),
        show=canonical_sha256([{k: v for k, v in item.items() if k != 'sha256'} for item in request['show']]))
    _require(set(parts) == {*expected, 'documents'} and all(parts[k] == v for k, v in expected.items()),
        'frozen request differs from semantic input parts')
    _require(row['input_digest'] == canonical_sha256(parts), 'host semantic digest differs')
    return request


def validate_checked_request(authority, node, started, commit=None, *, operands=None):
    request = validate_request_start_binding(started.data)
    _require(node['class'] == 'request_input' and request['answer_contract'] == node['answer']
        and request['reply_contract'] == node['result'], 'request contracts differ from checked node')
    _require(request['request_id'] == _request_id(authority, started.data['identity'], started.data['attempt']), 'request identity differs from checked run')
    _require(request['created_at'] == started.data['time'], 'request creation differs from start')
    if operands is not None:
        from .effect_inputs import effect_dependencies
        _require(effect_dependencies(operands) == request['depends_on'],
            'request dependencies differ from reached operands')
        values = [value.json_value() for value in operands]
        cursor = 1 if 'question' in node else len(node['prompt']['fills'])
        duration = values[cursor] if 'timeout_sec' in node else None
        if 'timeout_sec' in node:
            cursor += 1
        show = [dict(path=value, contract=_thaw(operand.descriptor)) for value, operand in zip(values[cursor:], operands[cursor:], strict=True)]
        _require(duration == request['timeout_sec'] and show == [{k: v for k, v in row.items() if k != 'sha256'} for row in request['show']],
            'request differs from reached operands')
        if 'question' in node:
            from .prompts import assemble_host_question
            _require(assemble_host_question(values[0], node['answer']) == request['question'], 'question differs from reached operand')
    if commit is not None:
        _require(commit.data['depends_on'] == request['depends_on'], 'reply dependencies differ')
        validate_reply_payload(request, commit.data)
    return request


@dataclass(frozen=True)
class RequestInput:
    question: str
    timeout_sec: int | None
    show: tuple[dict, ...]
    input_parts: dict


def resolve_request_input(node, operands, *, workspace):
    """Repeatable semantic inputs deliberately exclude time and show-file bytes."""
    values = [v.json_value() for v in operands]
    cursor = 1 if 'question' in node else len(node['prompt']['fills'])
    if 'question' in node:
        question = values[0]
        document_digests = {}
    else:
        from .providers import _snapshot_dependencies
        from .prompts import assemble_task_prompt
        dependency_snapshot, document_digests = _snapshot_dependencies(node, values, workspace)
        question = assemble_task_prompt(node, values[:cursor], dependency_snapshot=dependency_snapshot)
    duration = values[cursor] if 'timeout_sec' in node else None
    if 'timeout_sec' in node:
        cursor += 1
    if duration is not None and (type(duration) is not int or duration <= 0):
        raise HostInputError('host_input_invalid_timeout', 'timeout must be an exact positive integer')
    from .prompts import assemble_host_question
    question = assemble_host_question(question, node['answer'])
    show = tuple(dict(path=value, contract=_thaw(operand.descriptor)) for value, operand in zip(values[cursor:], operands[cursor:], strict=True))
    parts = dict(question=_digest(question.encode('utf-8')), answer_contract=canonical_sha256(node['answer']),
        reply_contract=canonical_sha256(node['result']), timeout_sec=canonical_sha256(duration),
        show=canonical_sha256(list(show)), documents=canonical_sha256(document_digests))
    return RequestInput(question, duration, show, parts)


def _observe_show(files, row, *, initial=False):
    # A missing presentation file may be waived; path safety never may.
    path = row['path']
    validate_transport_value(path, row['contract'], path_validator=_validate_pure_path_value)
    try:
        return dict(status='present', sha256=_digest(files.read(path)))
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.EINVAL}:
            raise HostInputError('host_input_unsafe_evidence', str(exc)) from exc
        if initial:
            raise
        return dict(status='missing' if exc.errno == errno.ENOENT else 'unreadable', errno=exc.errno or errno.EIO)


def _show_changes(files, request):
    differences = []
    for index, original in enumerate(request['show']):
        observed = _observe_show(files, original)
        if observed != dict(status='present', sha256=original['sha256']):
            differences.append(dict(index=index, path=original['path'], original_sha256=original['sha256'], observed=observed))
    return differences


def _publish_request_views(authority, started, commit=None):
    from .effect_inputs import open_phased_attempt
    from .views import ViewPublicationError
    from orchestrator.run_lock import ReservedRunRootError
    # Reuse the existing exact memo-derived directory walker and retained ancestors.
    try:
        with closing(open_phased_attempt(authority, started.data, create=True)) as files:
            request = started.data['host_request']
            files.write_atomic('request.prompt.txt', request['question'].encode('utf-8'))
            files.write_atomic('request.json', canonical_json_bytes(request) + b'\n')
            if commit is not None:
                files.write_atomic('reply.json', canonical_json_bytes(commit.data['value']) + b'\n')
    except (OSError, ValueError, ReservedRunRootError) as exc:
        raise ViewPublicationError(f'host request evidence publication failed: {exc}') from exc


def _reply_record(started, value, provenance, now):
    row = started.data
    committed = dict(record='committed', identity=row['identity'], attempt=row['attempt'],
        input_digest=row['input_digest'], input_parts=row['input_parts'], implementation_files=row['implementation_files'],
        result_path=row['result_path'], depends_on=row['host_request']['depends_on'], value=value,
        result_digest=canonical_sha256(value), effect_class='request_input', host_reply=provenance, time=now)
    validate_reply_payload(row['host_request'], committed)
    from .memo import _encode_record
    _encode_record(committed)
    return committed


def _commit_reply(authority, started, committed):
    from .memo import append_record
    from .authority import _require_retained_root
    _require_retained_root(authority.run_files)
    commit = append_record(authority.memo_path, committed, run_files=authority.run_files, checked_authority=authority)
    _publish_request_views(authority, started, commit)
    return commit


def execute_request(authority, node, operands, identity, *, workspace, workspace_files, site_classes, expire_host_input=False, **kwargs):
    from .memo import read_memo, append_record
    from .attempts import attempt_paths
    from .effect_inputs import effect_dependencies, _ensure_effect_can_start, _reuse_effect_commit, _EffectInputDiverged
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    resolved = resolve_request_input(node, operands, workspace=workspace)
    dependencies = effect_dependencies(operands)
    parts = resolved.input_parts
    digest = canonical_sha256(parts)
    commit = snapshot.active_commits.get(identity)
    started = snapshot.pending_starts.get(identity)
    if commit is not None:
        started = next(e for e in snapshot.entries if e.data['record'] == 'started'
            and e.data['identity'] == identity and e.data['attempt'] == commit.data['attempt'])
        validate_checked_request(authority, node, started, commit, operands=operands)
        result = _reuse_effect_commit(authority, commit, node, identity, parts, digest, dependencies)
        _publish_request_views(authority, started, commit)
        return result
    _ensure_effect_can_start(snapshot, identity)
    if started is None:
        ordinal, _, result_path = attempt_paths(snapshot, identity)
        now = time.time()
        try:
            deadline = None if resolved.timeout_sec is None else now + resolved.timeout_sec
        except OverflowError as exc:
            raise HostInputError('host_input_invalid_timeout', 'deadline is not finite') from exc
        if not _finite_time(now) or deadline is not None and not _finite_time(deadline):
            raise HostInputError('host_input_invalid_timeout', 'deadline is not finite')
        show = [{**row, 'sha256': _observe_show(workspace_files, row, initial=True)['sha256']} for row in resolved.show]
        request = dict(schema_version=1, request_id=_request_id(authority, identity, ordinal),
            question=resolved.question, question_digest=parts['question'], answer_contract=node['answer'],
            answer_contract_digest=parts['answer_contract'], reply_contract=node['result'], reply_contract_digest=parts['reply_contract'],
            show=show, created_at=now, deadline=deadline, timeout_sec=resolved.timeout_sec, depends_on=dependencies)
        request['payload_digest'] = canonical_sha256(request)
        validate_request_payload(request)
        from .authority import _require_retained_root
        _require_retained_root(authority.run_files)
        started = append_record(authority.memo_path, dict(record='started', identity=identity, attempt=ordinal,
            input_digest=digest, input_parts=parts, implementation_files={}, result_path=result_path, time=now,
            host_request=request), run_files=authority.run_files, checked_authority=authority)
    request = validate_checked_request(authority, node, started, operands=operands)
    if started.data['input_digest'] != digest or request['depends_on'] != dependencies:
        raise _EffectInputDiverged(identity, 'pending host request semantic inputs changed')
    _publish_request_views(authority, started)
    if identity not in snapshot.suspensions:
        from .authority import _require_retained_root
        _require_retained_root(authority.run_files)
        append_record(authority.memo_path, dict(record='suspended', identity=identity,
            attempt=started.data['attempt'], request_id=request['request_id']),
            run_files=authority.run_files, checked_authority=authority)
    now = time.time()
    if expire_host_input and request['deadline'] is not None and now >= request['deadline']:
        provenance = dict(request_id=request['request_id'], origin='runtime', reason='deadline',
            accept_changed_evidence=False, evidence_changes=[])
        commit = _commit_reply(authority, started, _reply_record(started, {'variant': 'EXPIRED'}, provenance, now))
        return _reuse_effect_commit(authority, commit, node, identity, parts, digest, dependencies)
    raise HostInputSuspended()


def _checked_snapshot(authority):
    from .memo import read_memo
    from .machine import site_classes
    from .replay import discover_prefix
    snapshot = read_memo(authority.memo_path, site_classes(authority.program), run_files=authority.run_files)
    prefix = discover_prefix(authority, snapshot)
    return snapshot, prefix


def pending_projection(snapshot):
    """Project the active frozen request with its memo-owned attempt locator."""
    if not snapshot.suspensions:
        return None
    identity = next(iter(snapshot.suspensions))
    row = snapshot.pending_starts[identity].data
    request = row['host_request']
    return {**request, 'identity': identity, 'attempt': row['attempt'],
        'result_path': row['result_path'],
        'deadline_elapsed': request['deadline'] is not None and time.time() >= request['deadline']}


def pending(run_root):
    """Return the checked pending request, without repair, expiration or source IO."""
    from .authority import load_run_authority
    root = Path(run_root).absolute()
    with closing(WorkspaceFiles(root)) as files:
        authority = load_run_authority(root, run_files=files)
        snapshot, _ = _checked_snapshot(authority)
        return pending_projection(snapshot)


def answer(run_root, request_id, value, *, by, attestation=None, accept_changed_evidence=False, workspace=None):
    return _settle(run_root, request_id, 'ANSWERED', value, by=by, attestation=attestation,
        accept_changed_evidence=accept_changed_evidence, workspace=workspace)


def cancel(run_root, request_id, *, by, attestation=None, accept_changed_evidence=False, workspace=None):
    return _settle(run_root, request_id, 'CANCELLED', None, by=by, attestation=attestation,
        accept_changed_evidence=accept_changed_evidence, workspace=workspace)


def _validate_answer_value(value, descriptor, *, path_validator):
    try:
        return validate_transport_value(value, descriptor, allow_nested_structures=True,
            path_validator=path_validator)
    except ValueError as exc:
        path = getattr(exc, 'value_path', None)
        detail = f'{path}: {exc}' if path else str(exc)
        raise HostInputError('host_input_answer_invalid', detail) from exc


def _settle(run_root, request_id, variant, answer_value, *, by, attestation, accept_changed_evidence, workspace):
    from .authority import load_run_authority, _require_retained_root
    from .memo import memo_writer_lock, repair_torn_tail
    from .machine import site_classes
    from .resume_prefix import checked_resume_prefix
    from orchestrator.cli.commands.evaluated import prepare_evaluated_resume
    by = _principal(by)
    if attestation is not None and not isinstance(attestation, str):
        raise HostInputError('host_input_invalid_attestation', 'attestation must be opaque text')
    if type(accept_changed_evidence) is not bool:
        raise HostInputError('host_input_invalid_evidence_override', 'override must be boolean')
    if not isinstance(request_id, str):
        raise HostInputError('host_input_stale', 'unknown request')
    value = dict(variant=variant, by=by)
    if variant == 'ANSWERED':
        value['value'] = answer_value
    root = Path(run_root).absolute()
    with memo_writer_lock(root) as fd, closing(WorkspaceFiles(root, root_fd=fd)) as files:
        _require_retained_root(files)
        authority = load_run_authority(root, run_files=files)
        snapshot, _ = _checked_snapshot(authority)
        starts = {(entry.data['identity'], entry.data['attempt']): entry for entry in snapshot.entries
            if entry.data['record'] == 'started' and 'host_request' in entry.data}
        # Active commits establish duplicate authority, even with a later pending request.
        for identity, commit in snapshot.active_commits.items():
            if commit.data['effect_class'] != 'request_input':
                continue
            started = starts[(identity, commit.data['attempt'])]
            request = started.data['host_request']
            if request['request_id'] != request_id:
                continue
            reply = commit.data['host_reply']
            proposed = _validate_answer_value(value, request['reply_contract'], path_validator=_validate_pure_path_value)
            if canonical_sha256(commit.data['value']) == canonical_sha256(proposed) and reply.get('origin') == 'host' and reply.get('attestation') == attestation \
                    and reply['accept_changed_evidence'] is accept_changed_evidence:
                return proposed
            raise HostInputError('request_already_settled', 'reply differs from active settlement')
        selected = next((entry for entry in snapshot.pending_starts.values()
            if entry.data.get('host_request', {}).get('request_id') == request_id), None)
        if selected is None:
            raise HostInputError('host_input_stale', 'unknown or invalidated request')
        identity = selected.data['identity']
        if identity not in snapshot.suspensions:
            raise HostInputError('host_input_not_suspended', 'resume must complete start recovery')
        workspace = Path.cwd() if workspace is None else Path(workspace)
        workspace = workspace.resolve(strict=True)
        authority, inputs, provider_io = prepare_evaluated_resume(root, workspace=workspace, run_files=files)
        snapshot, prefix = checked_resume_prefix(authority, inputs, run_id=authority.header["run_id"],
            workspace=workspace, provider_io=provider_io, site_classes=site_classes(authority.program))
        frontier = next((r for r in prefix.frontiers if r.identity == identity), None)
        _require(frontier is not None and frontier.node['class'] == 'request_input', 'host request is not the reached frontier')
        request = validate_checked_request(authority, frontier.node, selected)
        with closing(WorkspaceFiles(workspace)) as workspace_files:
            from orchestrator.contracts.output_contract import _require_nested_transport_path
            value = _validate_answer_value(value, frontier.node['result'],
                path_validator=lambda v, d: _require_nested_transport_path(v, d, workspace, workspace_files=workspace_files))
            changes = _show_changes(workspace_files, request)
            if changes and not accept_changed_evidence:
                raise HostInputError('shown_evidence_changed', 'shown files differ from the frozen request')
            provenance = dict(request_id=request_id, origin='host', attestation=attestation,
                accept_changed_evidence=accept_changed_evidence, evidence_changes=changes)
            # Repeat the safe snapshot immediately before publication; no caller time can backdate acceptance.
            if _show_changes(workspace_files, request) != changes:
                raise HostInputError('shown_evidence_changed', 'shown files changed during validation')
            now = time.time()
            if request['deadline'] is not None and now >= request['deadline']:
                raise HostInputError('host_input_deadline_elapsed', 'resume owns expiration')
            committed = _reply_record(selected, value, provenance, now)
            _require_retained_root(files)
            repair_torn_tail(authority.memo_path, snapshot, run_files=files)
            _commit_reply(authority, selected, committed)
            return value
