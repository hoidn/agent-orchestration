"""Descriptor-safe historical scaffold verification."""

import os
from pathlib import Path
from orchestrator.prompt_scaffold_render import ScaffoldVerificationError, _NOFOLLOW_DIR
from orchestrator.prompt_scaffold_verify import verify_occupant

def open_generated_root(path: Path) -> int:
    """Open a directory with every component no-follow; symlink/special
    components and final non-directories fail closed."""
    absolute = Path(os.path.abspath(path))
    current = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in absolute.parts[1:]:
            if not part or part == os.sep:
                continue
            try:
                next_fd = os.open(part, _NOFOLLOW_DIR, dir_fd=current)
            except OSError as exc:
                raise ScaffoldVerificationError(
                    f"refusing non-directory or symlink component {part!r}: {exc}"
                ) from exc
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise
