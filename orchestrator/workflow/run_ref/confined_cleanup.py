"""One settled attempt's disposable clone obligation in the existing parent ledger."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import stat

from orchestrator._common.io_atomic import rename_noreplace_at
from orchestrator.providers.isolation_runtime_authority import _statx_mount_id
from orchestrator.workflow.workspace_files import WorkspaceFiles
from .confinement import _owned_root_identity, _read_recipe
from .contracts import canonical_sha256
from .ledger import append_confined_event, load_attempt_ledger, settled_result_binding_from_record, _exact_pending_row
from .runtime import RunRefRuntimeError, _read_canonical_document

_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _pending(detail):
    return RunRefRuntimeError('run_ref_cleanup_pending', detail)


def checkpoint_binding(layout, name='checkpoint.json', *, expected=None):
    with closing(WorkspaceFiles(layout.child_root)) as files:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=files.root_fd)
        try:
            value = os.fstat(fd)
            if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
                raise _pending('checkpoint_type_invalid')
            identity = dict(device=value.st_dev, inode=value.st_ino, mount_id=_statx_mount_id(fd))
            if expected is not None and (identity != expected['identity'] or value.st_size != expected['size']):
                raise _pending(f'cleanup_checkpoint_replacement_preserved:{layout.child_root / name}')
            payload = os.read(fd, value.st_size + 1)
            after = os.fstat(fd)
            linked = files.stat(name)
            if (len(payload) != value.st_size or (value.st_dev, value.st_ino, value.st_mtime_ns, value.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns)
                    or (linked.st_dev, linked.st_ino) != (value.st_dev, value.st_ino)):
                raise _pending('cleanup_checkpoint_changed_while_reading')
            return dict(identity=identity, size=value.st_size, digest='sha256:' + hashlib.sha256(payload).hexdigest())
        finally:
            os.close(fd)


def _events(rows, settled):
    return [row for row in rows if row.visit == settled.visit and row.attempt_ordinal == settled.attempt_ordinal
            and row.event_kind in {'cleanup_intent', 'cleanup_error', 'cleanup_complete'}]


def settlement_entry(snapshot, identity, attempt):
    if (identity, attempt) not in snapshot.settlements:
        return None
    return next(entry for entry in reversed(snapshot.entries) if entry.data.get('record') == 'settled'
                and entry.data.get('identity') == identity and entry.data.get('attempt') == attempt)


def cleanup_projection(authority, snapshot):
    """Project only validated ledger obligations; no source reads, repair or deletion."""
    path = authority.run_root / 'run-ref-attempts.jsonl'
    if not path.exists():
        return []
    ledger = load_attempt_ledger(path, run_files=authority.run_files)
    pending = []
    for identity, commit in snapshot.active_commits.items():
        if commit.data['effect_class'] != 'run_ref':
            continue
        settled = settled_result_binding_from_record(commit.data['proof']['settled_result'])
        rows = [row for row in ledger.rows if row.visit == settled.visit
                and row.attempt_ordinal == settled.attempt_ordinal]
        committed = [row for row in rows if row.stage == 'committed' and row.event_kind == 'progress']
        if not rows or rows[0].schema_version != 'run_ref_attempt_ledger.v2':
            continue
        settlement = settlement_entry(snapshot, identity, commit.data['attempt'])
        if settlement is None:
            continue
        pending_row = _exact_pending_row(ledger, settled)
        if (settled.visit.parent_run_id != authority.run_root.name or len(committed) != 1
                or committed[0].bindings != pending_row.bindings
                or committed[0].previous_row_digest != pending_row.row_digest):
            raise RunRefRuntimeError('run_ref_evidence_invalid', 'cleanup_coordinator_binding_invalid')
        events = _events(rows, settled)
        if events:
            intent = events[0].event
            if (intent['identity'] != identity or intent['attempt'] != commit.data['attempt']
                    or intent['settled_digest'] != canonical_sha256(settlement.data)):
                raise _pending('cleanup_parent_settlement_binding_invalid')
            if events[-1].event_kind == 'cleanup_complete':
                continue
        error = events[-1].event['error'] if events and events[-1].event_kind == 'cleanup_error' else None
        pending.append(dict(identity=identity, attempt=commit.data['attempt'], status='pending', error=error))
    return sorted(pending, key=lambda row: (row['identity'], row['attempt']))


def _check_mounts(fd):
    mount = _statx_mount_id(fd)
    for entry in os.scandir(fd):
        if _statx_mount_id(fd, entry.name) != mount:
            raise _pending('cleanup_nested_mount')
        if entry.is_dir(follow_symlinks=False):
            child = os.open(entry.name, _DIRECTORY, dir_fd=fd)
            try:
                if _statx_mount_id(child) != mount:
                    raise _pending('cleanup_nested_mount')
                _check_mounts(child)
            finally:
                os.close(child)


def _delete_contents(fd):
    """Delete through retained descriptors, checking mount boundaries again at each descent."""
    mount = _statx_mount_id(fd)
    os.fchmod(fd, stat.S_IMODE(os.fstat(fd).st_mode) | 0o700)
    for entry in os.scandir(fd):
        if _statx_mount_id(fd, entry.name) != mount:
            raise _pending('cleanup_nested_mount')
        if entry.is_dir(follow_symlinks=False):
            child = os.open(entry.name, _DIRECTORY, dir_fd=fd)
            try:
                if _statx_mount_id(child) != mount:
                    raise _pending('cleanup_nested_mount')
                before = os.fstat(child)
                _delete_contents(child)
                after = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise _pending('cleanup_descendant_replaced')
            finally:
                os.close(child)
            os.rmdir(entry.name, dir_fd=fd)
        else:
            os.unlink(entry.name, dir_fd=fd)
    os.fsync(fd)


def cleanup_settled(request, *, identity, attempt, settlement):
    """Called with the parent writer held and only after its durable `settled` memo append."""
    from .confined_lifecycle import _layout
    from .holder_scope import validate_holder_scopes_quiescent
    from .confined_evidence import evidence_usage
    from .runtime import validate_run_ref_memo_authority
    # Verify the actual parent memo authority, not merely a caller's settlement spelling.
    from orchestrator.workflow.evaluated.memo import read_memo
    from orchestrator.workflow.evaluated.machine import site_classes
    snapshot = read_memo(request.parent_run_root / 'memo.jsonl', site_classes(request.parent_program), run_files=request.run_files)
    commit = snapshot.active_commits.get(identity)
    actual = settlement_entry(snapshot, identity, attempt)
    if (actual is None or actual != settlement or commit is None or commit.data['attempt'] != attempt):
        raise _pending('cleanup_requires_durable_parent_settlement')
    settled = settled_result_binding_from_record(commit.data['proof']['settled_result'])
    rows = load_attempt_ledger(request.ledger_path, run_files=request.run_files).rows
    events = _events(rows, settled)
    if events and events[-1].event_kind == 'cleanup_complete':
        return True
    validate_run_ref_memo_authority(request, settled_result=commit.data['proof']['settled_result'],
        artifacts=commit.data['proof']['artifacts'], allow_pending=False)
    layout = _layout(request, settled.attempt_ordinal)
    recipe = _read_recipe(layout)
    evidence = _read_canonical_document(layout.workspace.parent / 'evidence-manifest.json', label='evidence_manifest')
    bindings = recipe['owned_roots']
    checkpoint = evidence['cleanup_checkpoint']
    intent = dict(identity=identity, attempt=attempt, settled_digest=canonical_sha256(actual.data),
        private_name='.run-ref-cleanup-' + canonical_sha256(dict(visit=settled.visit.record,
            ordinal=settled.attempt_ordinal)).removeprefix('sha256:'),
        root=bindings['clone'], parent=bindings['clone_parent'], control=bindings['control'],
        control_parent=bindings['control_parent'], checkpoint_digest=checkpoint['digest'])
    def append(kind, event):
        return append_confined_event(request.ledger_path, visit=settled.visit,
            attempt_ordinal=settled.attempt_ordinal, event_kind=kind, event=event, run_files=request.run_files,
            before_append=lambda size: evidence_usage(layout, ledger_path=request.ledger_path, visit=request.visit, extra_bytes=size))
    if events:
        if events[0].event != intent:
            raise _pending('cleanup_original_binding_disagrees')
        intent_row = events[0]
    else:
        intent_row = append('cleanup_intent', intent)
    private = layout.workspace.parent / intent['private_name']
    try:
        validate_holder_scopes_quiescent(layout.child_root / 'holder')
        evidence_usage(layout, ledger_path=request.ledger_path, visit=request.visit)
        for path, expected in ((layout.workspace.parent, intent['parent']), (layout.child_root, intent['control']),
                               (layout.child_root.parent, intent['control_parent'])):
            if _owned_root_identity(path) != expected:
                raise _pending('cleanup_parent_identity_changed')
        with closing(WorkspaceFiles(layout.workspace.parent)) as files:
            fd = files.root_fd
            value = os.fstat(fd)
            if dict(device=value.st_dev, inode=value.st_ino, mount_id=_statx_mount_id(fd)) != intent['parent']:
                raise _pending('cleanup_parent_descriptor_changed')
            # Any replacement at either name blocks every retry, even after partial deletion.
            for path in (layout.workspace, private):
                if os.path.lexists(path) and _owned_root_identity(path) != intent['root']:
                    raise _pending(f'cleanup_replacement_preserved:{path}')
            if os.path.lexists(layout.workspace) and os.path.lexists(private):
                raise _pending(f'cleanup_both_names_present:{private}')
            if os.path.lexists(layout.workspace):
                rename_noreplace_at(fd, layout.workspace.name, fd, private.name)
                os.fsync(fd)
            if os.path.lexists(private):
                moved = os.open(private.name, _DIRECTORY, dir_fd=fd)
                try:
                    value = os.fstat(moved)
                    moved_identity = dict(device=value.st_dev, inode=value.st_ino, mount_id=_statx_mount_id(moved))
                    if moved_identity != intent['root']:
                        raise _pending(f'cleanup_replacement_preserved:{private}')
                    _check_mounts(moved)
                    _delete_contents(moved)
                    if _owned_root_identity(private) != intent['root']:
                        raise _pending(f'cleanup_replacement_preserved:{private}')
                finally:
                    os.close(moved)
                os.rmdir(private.name, dir_fd=fd)
            if os.path.lexists(private) or os.path.lexists(layout.workspace):
                raise _pending(f'cleanup_clone_still_present:{private}')
            os.fsync(fd)
        with closing(WorkspaceFiles(layout.child_root)) as files:
            value = os.fstat(files.root_fd)
            if dict(device=value.st_dev, inode=value.st_ino, mount_id=_statx_mount_id(files.root_fd)) != intent['control']:
                raise _pending('cleanup_control_descriptor_changed')
            private_header = '.run-ref-checkpoint-cleanup-' + intent_row.row_digest.removeprefix('sha256:')
            for name in ('checkpoint.json', private_header):
                if files.exists(name) and checkpoint_binding(layout, name, expected=checkpoint) != checkpoint:
                    raise _pending(f'cleanup_checkpoint_replacement_preserved:{layout.child_root / name}')
            if files.exists('checkpoint.json'):
                if files.exists(private_header):
                    raise _pending(f'cleanup_checkpoint_both_names_present:{layout.child_root / private_header}')
                rename_noreplace_at(files.root_fd, 'checkpoint.json', files.root_fd, private_header)
                os.fsync(files.root_fd)
            if files.exists(private_header):
                if checkpoint_binding(layout, private_header, expected=checkpoint) != checkpoint:
                    raise _pending(f'cleanup_checkpoint_replacement_preserved:{layout.child_root / private_header}')
                os.unlink(private_header, dir_fd=files.root_fd)
            os.fsync(files.root_fd)
            for name in ('checkpoint.json', private_header):
                if files.exists(name):
                    raise _pending(f'cleanup_checkpoint_replacement_preserved:{layout.child_root / name}')
        append('cleanup_complete', dict(intent_digest=intent_row.row_digest))
        return True
    except (OSError, ValueError, RunRefRuntimeError) as exc:
        message = str(exc)
        # A rename race must keep the exact private location across crash/retry.
        if os.path.lexists(private):
            message += f'; preserved_private={private}'
        message = message.encode('utf-8')[:4096].decode('utf-8', errors='ignore')
        append('cleanup_error', dict(intent_digest=intent_row.row_digest,
            error=dict(code='run_ref_cleanup_pending', message=message)))
        return False
