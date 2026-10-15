"""Descriptor-guided, bounded copies from a quiescent clone to retained parent exports."""
from contextlib import closing
import hashlib
import os
from pathlib import Path, PurePosixPath
import secrets
import stat

from orchestrator._common.io_atomic import rename_noreplace_at
from orchestrator.contracts.output_contract import _require_nested_transport_path
from orchestrator.providers.isolation_runtime_authority import _statx_mount_id
from orchestrator.run_lock import run_root_matches_fd
from orchestrator.workflow.type_descriptor import validate_transport_value
from orchestrator.workflow.workspace_files import WorkspaceFiles
from .checkpoint import MAX_CHECKPOINT_ENTRIES, MAX_TREE_DEPTH
from .contracts import canonical_json_bytes, canonical_sha256
from .runtime import RunRefRuntimeError, declared_artifacts_from_value

_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_RESERVED = {'.git', '.orchestrate', '.run-ref-exports', 'workspace.guard', 'workspace.lock'}


def _invalid(detail):
    return RunRefRuntimeError('run_ref_export_invalid', detail)


def _relative(text):
    if (not isinstance(text, str) or not text or '\0' in text or '\\' in text
            or any(part in ('', '.', '..') for part in text.split('/'))):
        raise _invalid('noncanonical_export_path')
    text.encode('utf-8')
    return PurePosixPath(text)


def _identity(fd):
    info = os.fstat(fd)
    return dict(device=info.st_dev, inode=info.st_ino, mount_id=_statx_mount_id(fd))


def _parent(root, relative, *, create=False):
    """Retain every component and reject mounts, including same-device bind mounts."""
    parts = _relative(relative).parts
    fd = os.dup(root)
    mount = _statx_mount_id(fd)
    try:
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(part, _DIRECTORY, dir_fd=fd)
            if _statx_mount_id(child) != mount:
                os.close(child)
                raise _invalid('export_nested_mount')
            os.close(fd)
            fd = child
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def _inspect(root, path, *, max_bytes=None):
    parent, name = _parent(root, path)
    try:
        fd = os.open(name, _READ, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if _statx_mount_id(fd) != _statx_mount_id(parent):
                raise _invalid('export_nested_mount')
            if stat.S_ISDIR(info.st_mode):
                return dict(kind='directory', mode=stat.S_IMODE(info.st_mode), size=0, digest=None,
                            identity=_identity(fd))
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise _invalid('export_not_single_link_regular_file')
            if max_bytes is not None and info.st_size > max_bytes:
                raise _invalid('export_byte_bound_exceeded')
            digest, size = hashlib.sha256(), 0
            bound = info.st_size if max_bytes is None else min(info.st_size, max_bytes)
            while chunk := os.read(fd, min(1024 * 1024, bound - size + 1)):
                size += len(chunk)
                if size > bound:
                    raise _invalid('export_byte_bound_exceeded_during_read')
                digest.update(chunk)
            after = os.fstat(fd)
            if ((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                    or size != info.st_size):
                raise _invalid('export_source_changed')
            return dict(kind='file', mode=stat.S_IMODE(info.st_mode), size=size,
                        digest='sha256:' + digest.hexdigest(), identity=_identity(fd))
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def _inventory(root, paths, *, max_entries, max_depth, max_bytes):
    entries, scanned = {}, set()
    total = 0
    def add(path, under, descend):
        nonlocal total
        if path not in entries:
            if len(entries) >= max_entries:
                raise _invalid('export_entry_bound_exceeded')
            row = _inspect(root, path, max_bytes=max_bytes - total)
            depth = len(PurePosixPath(path).relative_to(under).parts)
            directory_depth = depth if row['kind'] == 'directory' else depth - 1
            if directory_depth > max_depth:
                raise _invalid('export_depth_bound_exceeded')
            total += row['size']
            if total > max_bytes:
                raise _invalid('export_byte_bound_exceeded')
            entries[path] = row
        row = entries[path]
        if descend and row['kind'] == 'directory' and path not in scanned:
            scanned.add(path)
            parent, name = _parent(root, path)
            fd = os.open(name, _DIRECTORY, dir_fd=parent)
            os.close(parent)
            try:
                names = []
                with os.scandir(fd) as scan:
                    for entry in scan:
                        names.append(entry.name)
                        if len(names) > max_entries:
                            raise _invalid('export_entry_bound_exceeded')
                for name in sorted(names):
                    add(path + '/' + name, under, True)
            finally:
                os.close(fd)
    for path, under in paths:
        suffix = PurePosixPath(path).relative_to(under)
        for parent in reversed(suffix.parents):
            if parent != PurePosixPath('.'):
                add((under / parent).as_posix(), under, False)
        add(path, under, True)
    return entries, total


def _content(entries):
    return {path: {key: value for key, value in row.items() if key != 'identity'}
            for path, row in sorted(entries.items())}


def _copy_tree(source, target_parent, stage, source_path, entries):
    root = entries[source_path]
    if root['kind'] == 'directory':
        os.mkdir(stage, mode=0o700, dir_fd=target_parent)
        target = os.open(stage, _DIRECTORY, dir_fd=target_parent)
        try:
            descendants = [(path[len(source_path) + 1:], row) for path, row in entries.items()
                           if path.startswith(source_path + '/')]
            for relative, row in sorted(descendants, key=lambda item: (item[0].count('/'), item[0])):
                parent, name = _parent(target, relative, create=True)
                try:
                    if row['kind'] == 'directory':
                        os.mkdir(name, mode=0o700, dir_fd=parent)
                    else:
                        _copy_file(source, source_path + '/' + relative, parent, name, row)
                finally:
                    os.close(parent)
            for relative, row in sorted(descendants, reverse=True):
                if row['kind'] == 'directory':
                    parent, name = _parent(target, relative)
                    try:
                        child = os.open(name, _DIRECTORY, dir_fd=parent)
                        try:
                            os.fchmod(child, row['mode']); os.fsync(child)
                        finally:
                            os.close(child)
                    finally:
                        os.close(parent)
            os.fchmod(target, root['mode']); os.fsync(target)
        finally:
            os.close(target)
    else:
        _copy_file(source, source_path, target_parent, stage, root)
    os.fsync(target_parent)


def _copy_file(source, path, parent, name, expected):
    directory, basename = _parent(source, path)
    fd = os.open(basename, _READ, dir_fd=directory)
    os.close(directory)
    target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent)
    try:
        if _identity(fd) != expected['identity'] or os.fstat(fd).st_nlink != 1:
            raise _invalid('export_source_identity_changed')
        digest, size = hashlib.sha256(), 0
        while chunk := os.read(fd, min(1024 * 1024, expected['size'] - size + 1)):
            size += len(chunk)
            if size > expected['size']:
                raise _invalid('export_byte_bound_exceeded_during_copy')
            digest.update(chunk)
            remaining = memoryview(chunk)
            while remaining:
                written = os.write(target, remaining)
                if written <= 0:
                    raise _invalid('export_copy_made_no_progress')
                remaining = remaining[written:]
        if size != expected['size'] or 'sha256:' + digest.hexdigest() != expected['digest']:
            raise _invalid('export_source_changed')
        os.fchmod(target, expected['mode']); os.fsync(target)
    finally:
        os.close(fd); os.close(target)


def _validate_publication(parent_files, event, *, source_entries):
    if _identity(parent_files.root_fd) != event['parent_root']:
        raise _invalid('export_parent_root_changed')
    fd, name = _parent(parent_files.root_fd, event['destination'])
    try:
        if _identity(fd) != event['parent']:
            raise _invalid('export_destination_parent_changed')
        target = os.open(name, _READ, dir_fd=fd)
        try:
            if _identity(target) != event['staged_identity']:
                raise _invalid('export_foreign_destination')
        finally:
            os.close(target)
    finally:
        os.close(fd)
    rows, _ = _inventory(parent_files.root_fd, [(event['destination'], PurePosixPath(event['destination']))],
        max_entries=MAX_CHECKPOINT_ENTRIES, max_depth=MAX_TREE_DEPTH, max_bytes=event['bytes'])
    rebased = {event['source'] + path[len(event['destination']):]: row for path, row in rows.items()}
    expected = {path: row for path, row in source_entries.items()
                if path == event['source'] or path.startswith(event['source'] + '/')}
    if _content(rebased) != _content(expected) or canonical_sha256(_content(expected)) != event['inventory_digest']:
        raise _invalid('export_inventory_changed')


def _publication_roots(paths, descriptors):
    """Select source roots and validate overlaps through actual path ancestors."""
    roots = []
    for path in paths:
        nested = False
        for ancestor in PurePosixPath(path).parents:
            shape = descriptors.get(ancestor.as_posix())
            if shape is not None:
                nested = True
                if shape['under'] != descriptors[path]['under']:
                    raise _invalid('export_overlap_mapping_conflict')
        if not nested:
            roots.append(path)
    return roots


def export_value(value, descriptor, *, clone, parent, parent_run, activation, attempt, max_bytes,
                 prepared_events, persist, crash_hook=lambda boundary: None,
                 max_entries=MAX_CHECKPOINT_ENTRIES, max_depth=MAX_TREE_DEPTH):
    """Validate every path, copy each compatible source once, bind identity then publish."""
    try:
        with closing(WorkspaceFiles(clone)) as source, closing(WorkspaceFiles(parent)) as target:
            descriptors = {}
            def source_path(path, shape):
                under, relative = _relative(shape['under']), _relative(path)
                if (not shape['must_exist_target'] or under.parts[0] in _RESERVED
                        or any(part in _RESERVED for part in relative.parts)
                        or not relative.is_relative_to(under)):
                    raise _invalid('export_descriptor_root_invalid')
                _require_nested_transport_path(path, shape, Path(clone), workspace_files=source)
                previous = descriptors.setdefault(path, shape)
                if canonical_json_bytes(previous) != canonical_json_bytes(shape):
                    raise _invalid('export_alias_descriptor_conflict')
                return path
            original = validate_transport_value(value, descriptor, allow_nested_structures=True, path_validator=source_path)
            paths = sorted(descriptors)
            roots = _publication_roots(paths, descriptors)
            entries, total = _inventory(source.root_fd,
                [(path, PurePosixPath(descriptors[path]['under'])) for path in paths],
                max_entries=max_entries, max_depth=max_depth, max_bytes=max_bytes)
            destinations = {path: (PurePosixPath(shape['under']) / '.run-ref-exports' / parent_run / activation /
                                   str(attempt) / PurePosixPath(path).relative_to(shape['under'])).as_posix()
                            for path, shape in descriptors.items()}
            publications = []
            for path in roots:
                destination = destinations[path]
                matching = [event for event in prepared_events if event.get('source') == path]
                if len(matching) > 1:
                    raise _invalid('export_publication_ambiguous')
                parent_fd, name = _parent(target.root_fd, destination, create=True)
                try:
                    selected = {key: row for key, row in entries.items() if key == path or key.startswith(path + '/')}
                    if matching:
                        event = matching[0]
                        if (event['destination'] != destination or event['parent_root'] != _identity(target.root_fd)
                                or event['parent'] != _identity(parent_fd)
                                or event['inventory_digest'] != canonical_sha256(_content(selected))):
                            raise _invalid('export_prepared_binding_changed')
                        stage = event['staged_name']
                    else:
                        stage = '.run-ref-stage-' + secrets.token_hex(16)
                        _copy_tree(source.root_fd, parent_fd, stage, path, entries)
                        staged = os.open(stage, _READ, dir_fd=parent_fd)
                        try:
                            event = dict(source=path, destination=destination, staged_name=stage,
                                parent_root=_identity(target.root_fd), parent=_identity(parent_fd),
                                staged_identity=_identity(staged), inventory_digest=canonical_sha256(_content(selected)),
                                bytes=sum(row['size'] for row in selected.values()))
                        finally:
                            os.close(staged)
                        persist(event)
                        crash_hook('export_prepared')
                    if os.path.lexists(Path(f'/proc/self/fd/{parent_fd}') / stage):
                        staged = os.open(stage, _READ, dir_fd=parent_fd)
                        try:
                            if _identity(staged) != event['staged_identity']:
                                raise _invalid('export_stage_identity_changed')
                        finally:
                            os.close(staged)
                        rename_noreplace_at(parent_fd, stage, parent_fd, name)
                        os.fsync(parent_fd)
                        crash_hook('export_renamed')
                    _validate_publication(target, event, source_entries=entries)
                    publications.append(event)
                finally:
                    os.close(parent_fd)
            after, _ = _inventory(source.root_fd,
                [(path, PurePosixPath(descriptors[path]['under'])) for path in paths],
                max_entries=max_entries, max_depth=max_depth, max_bytes=max_bytes)
            if entries != after or not run_root_matches_fd(clone, source.root_fd) or not run_root_matches_fd(parent, target.root_fd):
                raise _invalid('export_root_or_source_changed')
            def rebase(path, shape):
                result = destinations[path]
                return _require_nested_transport_path(result, shape, Path(parent), workspace_files=target)
            rebased = validate_transport_value(original, descriptor, allow_nested_structures=True, path_validator=rebase)
            proof = dict(schema_version='run_ref_exports.v1', bytes=total, entries=_content(entries),
                limits=dict(max_entries=max_entries, max_depth=max_depth, max_bytes=max_bytes),
                paths=[dict(location=row.name, source=row.path, destination=destinations[row.path],
                            descriptor=descriptors[row.path]) for row in declared_artifacts_from_value(original, descriptor, pointer_locations=True)],
                publications=publications)
            return rebased, proof
    except RunRefRuntimeError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise _invalid(f'export_refused:{exc}') from exc


def validate_exports(value, descriptor, proof, *, parent):
    """Validate committed exported objects without consulting or recreating the clone."""
    try:
        if proof.get('schema_version') != 'run_ref_exports.v1':
            raise _invalid('export_proof_schema_invalid')
        with closing(WorkspaceFiles(parent)) as files:
            for event in proof['publications']:
                _validate_publication(files, event, source_entries=proof['entries'])
            destinations = {row['source']: row['destination'] for row in proof['paths']}
            shapes = {row['source']: row['descriptor'] for row in proof['paths']}
            def rebase(path, shape):
                if shapes.get(path) != shape:
                    raise _invalid('export_descriptor_binding_invalid')
                return _require_nested_transport_path(destinations[path], shape, Path(parent), workspace_files=files)
            return validate_transport_value(value, descriptor, allow_nested_structures=True, path_validator=rebase)
    except RunRefRuntimeError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise _invalid(f'export_validation_refused:{exc}') from exc
