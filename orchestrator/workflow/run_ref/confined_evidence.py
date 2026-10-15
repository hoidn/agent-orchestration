"""Bounded retained authority of a confined child, independent of its live clone."""
from contextlib import contextmanager, closing
from dataclasses import asdict
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

from orchestrator.workflow.workspace_files import WorkspaceFiles
from .contracts import canonical_json_bytes, canonical_sha256
from .image_store import capture_inventory, validate_inventory
from .runtime import RunRefRuntimeError
from .workspace import TreeEntry, manifest_from_entries

IMAGE_INVENTORY = 'image-inventory.json'
RETAINED_TREES = 'retained-trees.json'
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _invalid(detail):
    return RunRefRuntimeError('run_ref_evidence_invalid', detail)


def evidence_usage(layout, *, ledger_path=None, visit=None, extra_bytes=0, limit=None):
    """Charge retained physical files once; never clone, checkpoint, exports or baseline bytes."""
    from .confined_session import EVIDENCE_ALLOWANCE_BYTES
    from orchestrator.providers.isolation_runtime_authority import _statx_mount_id
    limit = EVIDENCE_ALLOWANCE_BYTES if limit is None else limit
    seen, total = set(), extra_bytes
    def scan_fd(fd, *, recursive, names=None):
        nonlocal total
        mount = _statx_mount_id(fd)
        for entry in os.scandir(fd):
            if names is not None and entry.name not in names:
                continue
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                if recursive:
                    child = os.open(entry.name, _DIRECTORY, dir_fd=fd)
                    try:
                        if _statx_mount_id(child) != mount:
                            raise _invalid('evidence_nested_mount')
                        scan_fd(child, recursive=True)
                    finally:
                        os.close(child)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise _invalid('evidence_file_type_invalid')
            identity = info.st_dev, info.st_ino
            if identity not in seen:
                seen.add(identity)
                total += info.st_size
                if total > limit:
                    raise _invalid('evidence_allowance_exceeded')
    def scan_files(path, *, recursive=False, names=None):
        with closing(WorkspaceFiles(path)) as files:
            scan_fd(files.root_fd, recursive=recursive, names=names)
    try:
        scan_files(layout.workspace.parent, names={'child-request.json', 'child-result.json',
            'workspace-delta.json', 'accounting.json', 'evidence-manifest.json', RETAINED_TREES})
        scan_files(layout.child_root, names={'run.json', 'closed_program.json', 'memo.jsonl',
            'child-recipe.json', IMAGE_INVENTORY, 'budget.json'})
        for name in ('effects', 'snapshots', 'holder'):
            path = layout.child_root / name
            if path.exists():
                scan_files(path, recursive=name != 'holder')
        if ledger_path is not None and Path(ledger_path).exists():
            from .ledger import load_attempt_ledger
            if visit is None:
                raise _invalid('evidence_ledger_visit_missing')
            # Carry earlier ordinals of this visit's budget, never unrelated children's work.
            rows = load_attempt_ledger(ledger_path).rows
            total += sum(len(canonical_json_bytes(row.record)) + 1 for row in rows if row.visit == visit)
        if total > limit:
            raise _invalid('evidence_allowance_exceeded')
        return total
    except OSError as exc:
        raise _invalid('evidence_unreadable') from exc


def retain_image(layout, image):
    with closing(WorkspaceFiles(layout.child_root)) as files:
        if files.exists(IMAGE_INVENTORY):
            return validate_inventory(files.read(IMAGE_INVENTORY), image.record)
        payload = capture_inventory(image)
        evidence_usage(layout, extra_bytes=len(payload))
        files.create(IMAGE_INVENTORY, payload, exclusive=True)
    return validate_inventory(payload, image.record)


@contextmanager
def replay_context(authority, recipe_bytes, image=None):
    """The ordinary input validator with authenticated membership and retained input bytes."""
    from orchestrator.workflow.evaluated.confined_dispatch import verify_attempt_snapshot
    from orchestrator.workflow.evaluated.closure_evidence import command_evidence_key, validate_implementation_evidence
    from orchestrator.workflow.evaluated.confined_dispatch import image_implementation_files
    admission = json.loads(recipe_bytes)['admission']['image']
    from .confined_session import EVIDENCE_ALLOWANCE_BYTES
    with closing(WorkspaceFiles(authority.run_root)) as files:
        inventory = validate_inventory(files.read(IMAGE_INVENTORY, max_bytes=EVIDENCE_ALLOWANCE_BYTES), admission)
    for pin in authority.header['interpreters'].values():
        if inventory.interpreter_pin(pin['path']) != pin:
            raise _invalid('retained_image_interpreter_disagrees')
    def implementation(node, pins):
        executable = pins[node['command'][0]]['path']
        rows = {command_evidence_key('absolute', executable, 0): inventory.implementation_row(executable)}
        for row in node.get('closure') or ():
            import posixpath
            path = posixpath.normpath(row['path'])
            rows[command_evidence_key('absolute', path)] = inventory.implementation_row(path)
        rows = validate_implementation_evidence(rows)
        if image is not None and rows != image_implementation_files(node, pins, image):
            raise _invalid('retained_image_implementation_disagrees')
        return rows
    with closing(WorkspaceFiles(authority.run_root / 'snapshots')) as store:
        yield SimpleNamespace(implementation_files=implementation,
                              verified_parts=lambda parts: verify_attempt_snapshot(store, parts))


def retain_trees(layout, baseline, final, delta_digest):
    record = dict(schema_version='run_ref_retained_trees.v1', baseline=asdict(baseline),
                  final=asdict(final), delta_digest=delta_digest)
    payload = canonical_json_bytes(record) + b"\n"
    path = layout.workspace.parent / RETAINED_TREES
    if path.exists() and path.read_bytes() != payload:
        raise _invalid('retained_trees_changed')
    from orchestrator._common.io_atomic import durable_atomic_write
    if not path.exists():
        evidence_usage(layout, extra_bytes=len(payload))
        durable_atomic_write(path, payload)
    return canonical_sha256(record)


def retained_trees(layout, *, expected_digest, baseline_digest, final_digest, delta_digest):
    from .runtime import _read_canonical_document
    record = _read_canonical_document(layout.workspace.parent / RETAINED_TREES, label='retained_trees')
    if (not isinstance(record, dict) or set(record) != {'schema_version', 'baseline', 'final', 'delta_digest'}
            or record['schema_version'] != 'run_ref_retained_trees.v1'
            or canonical_sha256(record) != expected_digest or record['delta_digest'] != delta_digest):
        raise _invalid('retained_trees_binding_invalid')
    results = []
    for name, digest in (('baseline', baseline_digest), ('final', final_digest)):
        value = record[name]
        if not isinstance(value, dict) or set(value) != {'schema_version', 'entries', 'digest'} or value['schema_version'] != 1:
            raise _invalid('retained_manifest_invalid')
        try:
            entries, paths, directories = [], set(), {''}
            for row in value['entries']:
                entry = TreeEntry(**row)
                parts = entry.path.split('/')
                if (any(part in ('', '.', '..') for part in parts) or entry.path in paths
                        or entry.kind not in {'file', 'directory', 'symlink'} or type(entry.mode) is not int
                        or not 0 <= entry.mode <= 0o7777 or type(entry.size) is not int or entry.size < 0):
                    raise ValueError('manifest entry malformed')
                paths.add(entry.path)
                if entry.kind == 'directory':
                    if entry.size != 0 or entry.sha256 is not None or entry.link_target is not None:
                        raise ValueError('manifest directory malformed')
                    directories.add(entry.path)
                entries.append(entry)
            if any(entry.path.rpartition('/')[0] not in directories for entry in entries):
                raise ValueError('manifest parent missing')
            rebuilt = manifest_from_entries(entries)
            if asdict(rebuilt) != {**value, 'entries': tuple(value['entries'])} or rebuilt.digest != digest:
                raise ValueError('manifest digest or order differs')
            results.append(rebuilt)
        except (ValueError, TypeError, KeyError) as exc:
            raise _invalid('retained_manifest_invalid') from exc
    return tuple(results)


def authority_inventory(layout):
    """Bind exact retained result/configuration/input bytes, including each command attempt."""
    import hashlib
    rows = {}
    with closing(WorkspaceFiles(layout.child_root)) as files:
        names = ['run.json', 'closed_program.json', 'memo.jsonl', 'child-recipe.json', IMAGE_INVENTORY]
        if files.exists('budget.json'):
            names.append('budget.json')
        for root in ('effects', 'snapshots'):
            path = layout.child_root / root
            if path.exists():
                for directory, dirs, children in os.walk(path, followlinks=False):
                    if any((Path(directory) / name).is_symlink() for name in dirs):
                        raise _invalid('retained_authority_symlink')
                    names.extend((Path(directory) / name).relative_to(layout.child_root).as_posix() for name in children)
        for name in sorted(names):
            payload = files.read(name)
            rows[name] = dict(size=len(payload), digest='sha256:' + hashlib.sha256(payload).hexdigest())
    return rows
