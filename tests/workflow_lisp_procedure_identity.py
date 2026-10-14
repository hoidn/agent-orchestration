"""Stable procedure-lowering identity observations for compatibility tests."""

from __future__ import annotations

import re
from pathlib import Path



REPO_ROOT = Path(__file__).resolve().parents[1]
_DEBUG_ONLY_WCC_KEYS = frozenset({"wcc_node_id", "wcc_scope_id"})
_PYTEST_SESSION_ROOT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"\\\\[^\\/\s'\"<>!=|&+*]+[\\/][^\\/\s'\"<>!=|&+*]+"
    r"(?:[\\/][^\\/\s'\"<>!=|&+*]+)*"
    r"[\\/]pytest-of-[^\\/\s'\"<>!=|&+*]+[\\/]pytest-\d+"
    r"|"
    r"[A-Za-z]:[\\/](?:[^\\/\s'\"<>!=|&+*]+[\\/])*"
    r"pytest-of-[^\\/\s'\"<>!=|&+*]+[\\/]pytest-\d+"
    r"|"
    r"/(?:[^/\s'\"<>!=|&+*]+/)*pytest-of-[^/\s'\"<>!=|&+*]+/pytest-\d+"
    r")"
)
_PYTEST_ELAPSED_SUMMARY_PATTERN = re.compile(
    r"^(?P<prefix>\d+ "
    r"(?:failed|passed|skipped|deselected|xfailed|xpassed|error|errors|warning|warnings)"
    r"(?:, \d+ "
    r"(?:failed|passed|skipped|deselected|xfailed|xpassed|error|errors|warning|warnings)"
    r")* in )\d+(?:\.\d+)?s(?=\s*$)",
    flags=re.MULTILINE,
)
_PYTHON_REPR_ADDRESS_PATTERN = re.compile(
    r"(?P<prefix><[^\s<][^\r\n]*?\bat )0x[0-9A-Fa-f]+(?=>)"
)


def normalize_procedure_prerequisite_failure_log(
    text: str,
    *,
    repo_root: Path,
) -> str:
    """Normalize only nondeterministic prerequisite failure-log fragments."""

    normalized = text.replace(repo_root.resolve().as_posix(), "$REPO")
    normalized = _PYTEST_SESSION_ROOT_PATTERN.sub("$PYTEST_TMP", normalized)
    normalized = _PYTEST_ELAPSED_SUMMARY_PATTERN.sub(
        lambda match: f"{match.group('prefix')}$TIME",
        normalized,
    )
    return _PYTHON_REPR_ADDRESS_PATTERN.sub(
        lambda match: f"{match.group('prefix')}$ADDR",
        normalized,
    )
