"""Stable continuation inventory and journal admission for exact lookup."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from orchestrator._common.safe_tree import SafeTreeError, read_regular_file
from orchestrator.providers.omp_observation import is_advisor_name, is_child_journal
from orchestrator.providers.omp_protocol import loads_strict
from orchestrator.providers.omp_session import (
    OmpSessionError,
    SessionManifest,
    parse_journal_bytes,
)

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
ContinuationSnapshot = tuple[list[bytes], tuple[str, ...], tuple[int, int] | None]


def _continuation_error(detail: str, cause: BaseException | None = None):
    from orchestrator.prompt_session import PromptSessionError

    error = PromptSessionError("session_continuation_invalid", detail)
    if cause is not None:
        error.__cause__ = cause
    return error


def _link_error(detail: str, cause: BaseException | None = None):
    from orchestrator.prompt_session import PromptSessionError

    error = PromptSessionError("session_link_invalid", detail)
    if cause is not None:
        error.__cause__ = cause
    return error


def read_continuations(sessions_fd: int, visit_key: str) -> ContinuationSnapshot:
    """Read a contiguous chain and bind exact bytes to its directory identity."""
    try:
        chain_fd = os.open(f"{visit_key}.continuations", _DIR_FLAGS, dir_fd=sessions_fd)
    except FileNotFoundError:
        return [], (), None
    except OSError as exc:
        raise _continuation_error(str(exc), exc)
    try:
        names = os.listdir(chain_fd)
        expected = tuple(f"{index}.json" for index in range(1, len(names) + 1))
        try:
            ordered = tuple(sorted(names, key=lambda item: int(item[:-5])))
        except (ValueError, TypeError) as exc:
            raise _continuation_error("malformed names", exc)
        if ordered != expected:
            raise _continuation_error("gapped names")
        identity = os.fstat(chain_fd)
        records = [read_regular_file(chain_fd, item) for item in expected]
        return records, expected, (identity.st_dev, identity.st_ino)
    except (OSError, SafeTreeError) as exc:
        raise _continuation_error(str(exc), exc)
    finally:
        os.close(chain_fd)


def read_manifest_bound(
    root_fd: int, manifest: SessionManifest, relative: str
) -> bytes:
    """Read one exact manifest row through the retained tree descriptor."""
    rows = [row for row in manifest.rows if row.relative_path == relative]
    if len(rows) != 1:
        raise _link_error(f"manifest lacks exact journal {relative!r}")
    row = rows[0]
    try:
        data = read_regular_file(root_fd, relative)
    except SafeTreeError as exc:
        raise _link_error(f"cannot read linked journal {relative!r}", exc)
    if len(data) != row.size_bytes or hashlib.sha256(data).hexdigest() != row.sha256:
        raise _link_error(f"journal {relative!r} disagrees with its manifest row")
    return data


def _record_documents(records: list[bytes]) -> list[dict[str, Any]]:
    documents = []
    for data in records:
        try:
            value = loads_strict(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise _continuation_error(str(exc), exc)
        if not isinstance(value, dict):
            raise _continuation_error("record is not an object")
        documents.append(value)
    return documents


def validate_continuation_journals(
    live_fd: int,
    live_manifest: SessionManifest,
    records: list[bytes],
) -> None:
    """Validate retained direct-fork topology; active bytes are checked once."""
    for record in _record_documents(records):
        if record.get("status") != "success" or record.get("mode") != "fork":
            continue
        source = record["source"]
        result = record["result"]
        result_name = result["primary_basename"]
        data = read_manifest_bound(live_fd, live_manifest, result_name)
        try:
            journal = parse_journal_bytes(data, relpath=result_name)
        except OmpSessionError as exc:
            raise _continuation_error(str(exc), exc)
        if (
            journal.header.id != result["session_id"]
            or journal.header.parent_session != source["session_id"]
            or is_advisor_name(result_name)
            or is_child_journal(journal)
        ):
            raise _continuation_error("fork result is not a direct primary")


__all__ = [
    "ContinuationSnapshot",
    "read_continuations",
    "read_manifest_bound",
    "validate_continuation_journals",
]
