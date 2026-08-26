"""Iterative descriptor-relative tree cleanup."""
from __future__ import annotations

import os
import stat

_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def remove_tree_contents(directory_fd: int) -> None:
    """Best-effort cleanup without symlink following or Python recursion."""
    root_fd = os.dup(directory_fd)
    stack = []
    try:
        root_kind = os.fstat(root_fd)
        if not stat.S_ISDIR(root_kind.st_mode) or root_kind.st_uid != os.geteuid():
            os.close(root_fd)
            return
        os.fchmod(root_fd, 0o700)
        try:
            root_entries = os.scandir(root_fd)
        except OSError:
            os.close(root_fd)
            return
        stack.append((root_fd, None, None, root_entries))
        while stack:
            current_fd, parent_fd, current_name, entries = stack[-1]
            try:
                name = next(entries).name
            except StopIteration:
                entries.close()
                stack.pop()
                os.close(current_fd)
                if parent_fd is not None:
                    try:
                        os.rmdir(current_name, dir_fd=parent_fd)
                    except OSError:
                        pass
                continue
            except OSError:
                entries.close()
                stack.pop()
                os.close(current_fd)
                continue
            try:
                kind = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
                if stat.S_ISDIR(kind.st_mode):
                    if kind.st_uid != os.geteuid():
                        continue
                    os.chmod(
                        name, 0o700, dir_fd=current_fd, follow_symlinks=False
                    )
                    child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=current_fd)
                    opened = os.fstat(child_fd)
                    if (opened.st_dev, opened.st_ino) != (kind.st_dev, kind.st_ino):
                        os.close(child_fd)
                        continue
                    os.fchmod(child_fd, 0o700)
                    try:
                        child_entries = os.scandir(child_fd)
                    except BaseException:
                        os.close(child_fd)
                        raise
                    stack.append((child_fd, current_fd, name, child_entries))
                else:
                    os.unlink(name, dir_fd=current_fd)
            except OSError:
                pass
    finally:
        for descriptor, _parent, _name, entries in reversed(stack):
            entries.close()
            os.close(descriptor)
