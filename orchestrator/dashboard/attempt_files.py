"""Which files of an evaluated effect's attempt directory the run and effect pages link.

Policy: the effect's result path, then the attempt directory's top-level regular files (not symlinks,
FIFOs, devices or subdirectories), sorted by name and keyed by name as it is, at most `LINK_LIMIT`.
Each goes through the run-scope `FileReferenceResolver`. Not linked, by owner ruling (2026-11-11):
`receipt.json` (native session locator, process group) and an agent turn's `stdout.txt` (the raw
provider stream, which repeats the session id and carries tool arguments the normalized views omit).
The file route still serves both to someone who types the path. Names that are not UTF-8 are skipped.
Every skip is reported as a warning. Reads one directory listing; never opens a file.
"""

from __future__ import annotations

import os
from pathlib import Path

from orchestrator.dashboard.files import UnsafePathError

LINK_LIMIT = 50
_UNLINKED = frozenset({"receipt.json"})
_UNLINKED_BY_CLASS = {"agent_turn": frozenset({"stdout.txt"})}
_NAMED_SKIPS = 5


def attempt_file_refs(payload, resolver, warnings: list[str]) -> dict:
    """File references for one evaluated view row (`result_path`, `effect_class`), keyed by file name."""
    result = Path(payload["result_path"])
    hidden = _UNLINKED | _UNLINKED_BY_CLASS.get(payload["effect_class"], frozenset())
    names = list(dict.fromkeys([result.name, *_listed_names(result.parent, hidden, resolver, warnings)]))
    if len(names) > LINK_LIMIT:
        warnings.append(f"{len(names) - LINK_LIMIT} more files in {result.parent} are not linked (limit {LINK_LIMIT})")
    references = {}
    for name in names[:LINK_LIMIT]:
        try:
            references[name] = resolver.run_ref(result.parent / name, label=name)
        except UnsafePathError as exc:
            warnings.append(f"unsafe {name} file: {exc}")
        except OSError as exc:
            warnings.append(f"unreadable {name} file: {exc.strerror}")
    return references


def _listed_names(attempt: Path, hidden, resolver, warnings: list[str]) -> list[str]:
    try:
        directory = resolver.run_ref(attempt, label="attempt directory")
    except UnsafePathError as exc:
        warnings.append(f"unsafe attempt directory: {exc}")
        return []
    if directory.status != "not_file":
        return []
    try:
        regular, irregular = _scan(directory.absolute_path, hidden)
    except OSError as exc:
        warnings.append(f"unreadable attempt directory {attempt}: {exc.strerror}")
        return []
    names = [name for name in regular if utf8_name(name)]
    _warn_skipped(attempt, len(regular) - len(names), irregular, warnings)
    return names


def _scan(directory: Path, hidden) -> tuple[list[str], list[str]]:
    """Top-level regular file names and other non-directory entry names, both sorted; nothing followed."""
    regular, irregular = [], []
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.name in hidden or entry.is_dir(follow_symlinks=False):
                continue
            (regular if entry.is_file(follow_symlinks=False) else irregular).append(entry.name)
    return sorted(regular), sorted(irregular)


def _warn_skipped(attempt: Path, undecodable: int, irregular: list[str], warnings: list[str]) -> None:
    if undecodable:
        warnings.append(f"{undecodable} file names in {attempt} are not UTF-8 and are not linked")
    shown = [name for name in irregular if utf8_name(name)][:_NAMED_SKIPS]
    warnings.extend(f"unsafe {name}: not a regular file, not linked" for name in shown)
    if len(irregular) > len(shown):
        warnings.append(f"{len(irregular) - len(shown)} more entries in {attempt} are not regular files and are not linked")


def utf8_name(name: str) -> bool:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True
