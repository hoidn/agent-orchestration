"""Retire the closed private script shape after process quiescence.

Recovery uses the protected scope inventory's namespace, not a reconstructed
old inode. D-e assumes the runtime is its sole authorized host-side mutator.
No script contents are read, executed, imported or retained by this owner.
"""
from __future__ import annotations

import os
import re
import stat

from orchestrator.providers.isolation_runtime_authority import _statx_mount_id as _mount

from .holder_broker import MAX_RESULT_ENTRIES
from .runtime import RunRefRuntimeError

_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_LEAF = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')


def _refused():
    return RunRefRuntimeError('run_ref_environment_escape_rejected', 'holder_script_retirement_refused')


def _identity(info):
    return info.st_dev, info.st_ino


def _directory(fd, *, parent=None, expected=None):
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or expected is not None and _identity(info) != expected
            or parent is not None and (info.st_dev != os.fstat(parent).st_dev or _mount(fd) != _mount(parent))):
        raise _refused()
    return _identity(info)


def _entries(fd):
    names = []
    with os.scandir(fd) as entries:
        for entry in entries:
            if len(names) >= MAX_RESULT_ENTRIES:
                raise _refused()
            names.append(entry.name)
    return sorted(names)


def _inventory(parent, name, expected=None):
    if '/' in name or name in {'', '.', '..'}:
        raise _refused()
    root = os.open(name, _DIR, dir_fd=parent)
    try:
        identity = _directory(root, parent=parent, expected=expected)
        leaves = []
        for leaf in _entries(root):
            if not _LEAF.fullmatch(leaf):
                raise _refused()
            directory = os.open(leaf, _DIR, dir_fd=root)
            try:
                leaf_identity = _directory(directory, parent=root)
                names = _entries(directory)
                if names not in ([], ['leaf.sh']):
                    raise _refused()
                script_identity = None
                if names:
                    script = os.open('leaf.sh', os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
                    try:
                        info = os.fstat(script)
                        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                                or stat.S_IMODE(info.st_mode) not in {0o600, 0o644}  # new writes use 0600
                                or info.st_nlink != 1 or info.st_dev != os.fstat(root).st_dev
                                or _mount(script) != _mount(root)):
                            raise _refused()
                        script_identity = _identity(info)
                    finally:
                        os.close(script)
                leaves.append((leaf, leaf_identity, script_identity))
            finally:
                os.close(directory)
        return name, identity, leaves
    finally:
        os.close(root)


def _remove(parent, inventory, *, remove_root):
    name, identity, leaves = inventory
    # Revalidate the complete shape before the first destructive operation.
    if _inventory(parent, name, expected=identity) != inventory:
        raise _refused()
    root = os.open(name, _DIR, dir_fd=parent)
    try:
        for leaf, leaf_identity, script_identity in leaves:
            directory = os.open(leaf, _DIR, dir_fd=root)
            try:
                _directory(directory, parent=root, expected=leaf_identity)
                if script_identity is not None:
                    current = os.stat('leaf.sh',dir_fd=directory,follow_symlinks=False)
                    if _identity(current) != script_identity:
                        raise _refused()
                    os.unlink('leaf.sh',dir_fd=directory)
                if os.listdir(directory):
                    raise _refused()
            finally:
                os.close(directory)
            os.rmdir(leaf,dir_fd=root)
        if os.listdir(root):
            raise _refused()
    finally:
        os.close(root)
    if remove_root:
        os.rmdir(name,dir_fd=parent)
        if os.path.lexists(f'/proc/self/fd/{parent}/{name}'):
            raise _refused()


def retire_leaf(root, leaf, *, parent_identity, root_identity, leaf_identity):
    """Live identity-pinned retirement; absence is checked before import."""
    parent = os.open(root.parent, _DIR)
    try:
        _directory(parent, expected=parent_identity)
        inventory = _inventory(parent, root.name, expected=root_identity)
        if not inventory[2]:
            return
        if len(inventory[2]) != 1 or inventory[2][0][:2] != (leaf, leaf_identity):
            raise _refused()
        _remove(parent, inventory, remove_root=False)
    except OSError:
        raise _refused() from None
    finally:
        os.close(parent)


def identities(root):
    parent = os.open(root.parent, _DIR)
    try:
        parent_identity = _directory(parent)
        directory = os.open(root.name, _DIR, dir_fd=parent)
        try:
            return parent_identity, _directory(directory, parent=parent)
        finally:
            os.close(directory)
    finally:
        os.close(parent)


def write_script(root, leaf, text, *, parent_identity, root_identity, leaf_identity):
    if identities(root) != (parent_identity, root_identity):
        raise _refused()
    root_fd = os.open(root, _DIR)
    try:
        _directory(root_fd,expected=root_identity)
        directory = os.open(leaf,_DIR,dir_fd=root_fd)
        try:
            _directory(directory,parent=root_fd,expected=leaf_identity)
            descriptor = os.open('leaf.sh',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,
                                 0o600,dir_fd=directory)
            with os.fdopen(descriptor,'w') as target:
                target.write(text)
        finally:
            os.close(directory)
    finally:
        os.close(root_fd)


def retire_root(root, *, parent_identity, root_identity):
    parent = os.open(root.parent, _DIR)
    try:
        _directory(parent, expected=parent_identity)
        _remove(parent,_inventory(parent,root.name,expected=root_identity),remove_root=True)
    except OSError:
        raise _refused() from None
    finally:
        os.close(parent)


def recover_scripts(control_dir, names, *, readonly=False):
    """After all scope validation/stop, validate every tree before retiring any."""
    parent = os.open(control_dir, _DIR)
    try:
        _directory(parent)
        if any(name.startswith('runref-') and name not in names for name in _entries(parent)):
            raise _refused()
        inventories = []
        for name in names:
            try:
                os.stat(name,dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:
                continue
            inventories.append(_inventory(parent, name))
        if not readonly:
            for inventory in inventories:
                _remove(parent, inventory, remove_root=True)
    except OSError:
        raise _refused() from None
    finally:
        os.close(parent)
