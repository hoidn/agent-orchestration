"""Read-only confined terminal proofs and idempotent repair under the child writer."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from orchestrator.run_lock import run_writer_lock
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import append_record, read_memo, reduce_memo
from orchestrator.workflow.evaluated.replay import discover_prefix
from orchestrator.workflow.workspace_files import WorkspaceFiles

from .contracts import canonical_sha256, canonical_json_bytes
from .runtime import RunRefRuntimeError


def _invalid(detail):
    return RunRefRuntimeError('run_ref_evidence_invalid', detail)


def _bytes_digest(raw):
    return 'sha256:' + sha256(raw).hexdigest()


def diagnostic_digest(exc):
    return canonical_sha256(dict(code=exc.code, source=exc.source, metadata=exc.metadata))


def _require_child_authority(request, layout, authority, recipe_bytes):
    from .confinement import checked_child_program
    from .confined_lifecycle import resolve_run_ref_parent_input_values
    from .evaluated_child import confined_child_header, require_confined_child_header
    expected = confined_child_header(program=checked_child_program(request.parent_program, request.step_config.run_ref),
        child_run_id=layout.child_run_id, child_root=layout.child_root, clone_root=layout.workspace,
        run_ref_root=request.run_ref_root, inputs=resolve_run_ref_parent_input_values(request))
    try:
        require_confined_child_header(authority.header, expected, json.loads(recipe_bytes)['admission']['image']['tree_digest'])
    except (ValueError, KeyError, TypeError) as exc:
        raise _invalid('failed_child_authority_disagrees') from exc


def _prefix(authority, raw, clone_root, recipe_bytes, image=None):
    from .evaluated_child import _verify_confined_effect_inputs
    snapshot = reduce_memo(raw, site_classes(authority.program))
    if snapshot.tail or snapshot.unsettled_coordinators:
        raise _invalid('failed_prefix_incomplete')
    prefix = discover_prefix(authority, snapshot)
    _verify_confined_effect_inputs(authority, snapshot, prefix, clone_root, recipe_bytes, image)
    return snapshot, prefix


def _boundary(authority, raw, clone_root, recipe_bytes, *, code, released, state, image=None):
    snapshot, prefix = _prefix(authority, raw, clone_root, recipe_bytes, image)
    if snapshot.terminal is not None:
        raise _invalid('failure_prefix_already_terminal')
    if code == 'run_ref_budget_exhausted' and not released:
        raise RunRefRuntimeError(code, 'budget_failure_without_released_attempt')
    if snapshot.pending_starts:
        if len(snapshot.pending_starts) != 1 or len(prefix.frontiers) != 1:
            raise _invalid('failed_boundary_ambiguous')
        identity, started = next(iter(snapshot.pending_starts.items()))
        reached = prefix.frontiers[0]
        if reached.identity != identity:
            raise _invalid('failed_started_boundary_unreachable')
        _verify_started_input(authority, snapshot, reached, started, clone_root, recipe_bytes, image)
        return dict(kind='started_attempt', identity=identity, attempt=started.data['attempt'])
    if prefix.frontiers:
        if len(prefix.frontiers) != 1:
            raise _invalid('failed_boundary_ambiguous')
        reached = prefix.frontiers[0]
        return dict(kind='before_start', identity=reached.identity, site=reached.node['site'])
    if prefix.fault is not None:
        if prefix.fault.code != code:
            raise _invalid("pure_failure_code_disagrees")
        return dict(kind='pure_fault', diagnostic_digest=diagnostic_digest(prefix.fault))
    if prefix.halted and code == 'run_ref_budget_exhausted' and released:
        if state['charged_ns'] < state['limit_ns']:
            raise _invalid('finalization_budget_not_exhausted')
        return dict(kind='finalization', halt_digest=canonical_sha256(prefix.value))
    raise _invalid('failure_not_at_proven_boundary')


def _verify_started_input(authority, snapshot, reached, started, clone_root, recipe_bytes, image=None):
    """Recompute a past start through its snapshot, with no retry authorization or live clone reads."""
    from orchestrator.workflow.evaluated import effect_inputs
    from orchestrator.workflow.evaluated.confined_dispatch import verify_attempt_snapshot
    from .image_store import open_sealed_image
    own_image = image is None
    if own_image:
        record = json.loads(recipe_bytes)['admission']['image']
        image = open_sealed_image(Path(authority.header['run_ref_root']) / 'images', record['image'])
    try:
        with closing(WorkspaceFiles(authority.run_root / 'snapshots')) as store:
            context = SimpleNamespace(image=image, verified_parts=lambda parts: verify_attempt_snapshot(store, parts))
            cwd = effect_inputs.resolve_launch_cwd(clone_root, reached.launch_workspace,
                identity=reached.identity, previous=started, recorded=True)
            _resolved, parts, files = effect_inputs._resolve_effect_input(authority, reached.node, reached.operands,
                reached.identity, clone_root, reached.reader, started, None, None, started.data['result_path'],
                check_command_destinations=False, owner=reached.owner, launch_cwd=cwd, confined=context)
            if (parts != started.data['input_parts'] or canonical_sha256(parts) != started.data['input_digest']
                    or files != started.data['implementation_files']):
                raise _invalid('failed_started_input_disagrees')
    finally:
        if own_image:
            image.close()


def record_failure(request, provisioned, authority, exc, budget, side):
    """Called with the child's writer held, after stop and budget-close acknowledgement."""
    code, detail = getattr(exc, 'code', 'evaluated_execution_failed'), str(exc)
    if (getattr(exc, 'preflight', False) or getattr(exc, 'publication_failure', False)
            or code in {'run_ref_evidence_invalid', 'run_ref_ledger_invalid', 'run_ref_environment_changed',
                        'run_ref_environment_unavailable', 'reserved_run_root_changed'}):
        raise exc
    _require_child_authority(request, provisioned.layout, authority, provisioned.recipe_bytes)
    raw = authority.run_files.read(authority.memo_path)
    released = request is not None and _released(provisioned.layout)
    boundary = _boundary(authority, raw, provisioned.layout.workspace, provisioned.recipe_bytes,
        code=code, released=released, state=budget.state, image=None)
    if boundary['kind'] == 'pure_fault':
        from orchestrator.workflow.pure_expr import PureExprEvaluationError
        if not isinstance(exc, PureExprEvaluationError) or diagnostic_digest(exc) != boundary['diagnostic_digest']:
            raise _invalid('pure_failure_diagnostic_disagrees')
    failure = None
    if boundary['kind'] == 'started_attempt':
        failure = dict(record='failed', identity=boundary['identity'], attempt=boundary['attempt'], code=code,
                       exit_info=getattr(exc, 'exit_info', None) or {})
        if getattr(exc, 'violations', None) is not None:
            failure['violations'] = exc.violations
    accounting = _accounting(provisioned.layout, budget.state)
    event = dict(code=code, detail=detail or code, closure_digest=budget.state['closure_digest'],
        prefix_bytes=len(raw), prefix_digest=_bytes_digest(raw), boundary=boundary,
        accounting=accounting, effect_failure=failure)
    side('failed_terminal', event)
    return event


def _released(layout):
    from orchestrator.providers.isolation_backend import DurableLaunchReleaseGate
    return any(DurableLaunchReleaseGate.load(path).release_consumed
               for path in (layout.child_root / 'holder').glob('holder-release-*.json'))


def _accounting(layout, state):
    from .confinement import confined_child_accounting
    return confined_child_accounting(layout, attempt_ordinal=int(layout.workspace.parent.name), terminal_status='failed',
                                     elapsed_ms=state['charged_ns'] // 1_000_000)


def retained_terminal(request, layout, rows, state):
    """Return validated durable terminal evidence without admission or a new execution interval."""
    if not (layout.child_root / 'run.json').exists():
        return None
    proof_row = next((row for row in reversed(rows) if row.visit == request.visit
        and row.bindings.child_run_id == layout.child_run_id and row.event_kind == 'failed_terminal'), None)
    if proof_row is not None:
        repair_failed_terminal(request, layout, proof_row, state)
    authority = load_run_authority(layout.child_root)
    memo = read_memo(authority.memo_path, site_classes(authority.program))
    if memo.terminal is None:
        return None
    terminal = memo.terminal.data
    if terminal['outcome'] == 'failed' and proof_row is None:
        raise _invalid('failed_terminal_without_parent_row')
    from .confined_lifecycle import _checked_child, resolve_run_ref_parent_input_values
    return _checked_child(request, layout, (layout.child_root / 'child-recipe.json').read_bytes(),
        resolve_run_ref_parent_input_values(request), terminal['outcome'], terminal.get('value'))


def _failed_suffix(request, layout, row, state, authority, raw):
    proof = row.event
    _require_child_authority(request, layout, authority, (layout.child_root / 'child-recipe.json').read_bytes())
    if proof['closure_digest'] != state['closure_digest'] or proof['accounting'] != _accounting(layout, state):
        raise _invalid('failed_budget_binding_disagrees')
    length = proof['prefix_bytes']
    captured = raw[:length]
    if len(captured) != length or _bytes_digest(captured) != proof['prefix_digest']:
        raise _invalid('failed_prefix_digest_disagrees')
    boundary = _boundary(authority, captured, layout.workspace,
        (layout.child_root / 'child-recipe.json').read_bytes(), code=proof['code'],
        released=_released(layout), state=state)
    if boundary != proof['boundary']:
        raise _invalid('failed_boundary_disagrees')
    failure = proof['effect_failure']
    if boundary['kind'] == 'started_attempt':
        if (not isinstance(failure, dict) or failure.get('record') != 'failed'
                or failure.get('identity') != boundary['identity'] or failure.get('attempt') != boundary['attempt']
                or failure.get('code') != proof['code']):
            raise _invalid('failed_effect_binding_disagrees')
    elif failure is not None:
        raise _invalid('failed_proof_invented_effect')
    expected = [] if failure is None else [failure]
    expected.append(dict(record='terminal', outcome='failed', code=proof['code'], message=proof['detail']))
    snapshot = reduce_memo(raw, site_classes(authority.program))
    suffix = [json.loads(line) for line in raw[length:snapshot.complete_bytes].splitlines()]
    if suffix != expected[:len(suffix)] or len(suffix) > len(expected):
        raise _invalid('failed_terminal_suffix_disagrees')
    return snapshot, expected[len(suffix):]


def validate_failed_terminal_evidence(request, layout):
    from .ledger import load_attempt_ledger, confined_budget
    rows = load_attempt_ledger(request.ledger_path, run_files=request.run_files).rows
    candidates = [row for row in rows if row.visit == request.visit
        and row.bindings.child_run_id == layout.child_run_id and row.event_kind == 'failed_terminal']
    if len(candidates) != 1:
        raise _invalid('failed_terminal_without_parent_row')
    with closing(WorkspaceFiles(layout.child_root)) as files:
        authority = load_run_authority(layout.child_root, run_files=files)
        snapshot, missing = _failed_suffix(request, layout, candidates[0], confined_budget(rows, request.visit),
                                          authority, files.read(authority.memo_path))
        if snapshot.tail or missing:
            raise _invalid('failed_terminal_incomplete')


def repair_failed_terminal(request, layout, row, state):
    """Validate captured evidence first, then append only its exact missing suffix."""
    from orchestrator.workflow.evaluated.memo import repair_torn_tail
    with run_writer_lock(layout.child_root):
        with closing(WorkspaceFiles(layout.child_root)) as files:
            authority = load_run_authority(layout.child_root, run_files=files)
            snapshot, missing = _failed_suffix(request, layout, row, state, authority, files.read(authority.memo_path))
            if snapshot.tail:
                repair_torn_tail(authority.memo_path, snapshot, run_files=files)
            for record in missing:
                append_record(authority.memo_path, record, run_files=files, checked_authority=authority)


def fail_exhausted_retained(request, layout, rows, budget, side):
    if budget.state['active'] is not None or budget.state['charged_ns'] < budget.state['limit_ns']:
        raise _invalid('retained_budget_not_proven_exhausted')
    if not _released(layout):
        raise RunRefRuntimeError('run_ref_budget_exhausted', 'child wall budget exhausted before release')
    from .confinement import _read_recipe
    provisioned = SimpleNamespace(layout=layout, recipe_bytes=canonical_json_bytes(_read_recipe(layout)))
    with run_writer_lock(layout.child_root):
        with closing(WorkspaceFiles(layout.child_root)) as files:
            authority = load_run_authority(layout.child_root, run_files=files)
            exc = RunRefRuntimeError('run_ref_budget_exhausted', 'child wall budget exhausted during interruption')
            record_failure(request, provisioned, authority, exc, budget, side)
    from .ledger import load_attempt_ledger
    rows = load_attempt_ledger(request.ledger_path, run_files=request.run_files).rows
    return retained_terminal(request, layout, rows, budget.state)
