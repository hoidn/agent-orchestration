"""Task 10: physical fork/in-place journal postconditions for the TTY bridge.

The bridge spawns the interactive OMP child with inherited stdio, then judges
the live session tree through these exact predicates. Every failure is a
terminal failure: the bridge publishes exactly one failed continuation record
and the tail permanently blocks later orchestrator lookups (Task 9).
"""

from __future__ import annotations

import hashlib

from orchestrator.providers.omp_launch_fs import LaunchFsError, session_inventory_fd
from orchestrator.providers.omp_observation import is_advisor_name, is_child_journal
from orchestrator.providers.omp_session import (
    OmpSessionError,
    build_session_manifest,
    parse_journal_bytes,
    validate_session_graph,
)
from orchestrator.prompt_session_chain import read_manifest_bound


class ResumePostconditionError(Exception):
    """One fork/in-place physical journal predicate failed."""


def _fail(detail: str) -> ResumePostconditionError:
    return ResumePostconditionError(detail)


def post_live_manifest(live_fd: int) -> str | None:
    """Best-effort post live manifest; None when the tree cannot be inventoried."""
    try:
        return build_session_manifest(live_fd).manifest_sha256
    except (OmpSessionError, OSError):
        return None


def validate_fork_result(
    *,
    live_fd: int,
    pre_inventory: tuple[str, ...],
    pre_manifest_sha256: str,
    source_primary: str,
    source_sha256: str,
    source_session_id: str,
) -> tuple[str, str, str]:
    """Require source-identical plus exactly one new direct primary.

    Returns ``(basename, session_id, journal_sha256)`` of the new primary.
    """
    try:
        post_inventory = session_inventory_fd(live_fd)
    except LaunchFsError as exc:
        raise _fail(f"live inventory cannot be admitted: {exc}") from exc
    pre = set(pre_inventory)
    post = set(post_inventory)
    if not pre <= post:
        raise _fail("fork removed a pre-existing live entry")
    new_names = sorted(post - pre)
    if len(new_names) != 1:
        raise _fail(
            f"fork created {len(new_names)} new entries, expected exactly one"
        )
    name = new_names[0]
    if not name.endswith(".jsonl") or is_advisor_name(name):
        raise _fail("fork result is not a primary JSONL basename")
    manifest = build_session_manifest(live_fd)
    if manifest.manifest_sha256 == pre_manifest_sha256:
        raise _fail("fork left the live manifest unchanged")
    try:
        data = read_manifest_bound(live_fd, manifest, name)
    except Exception as exc:
        raise _fail(f"fork result journal cannot be admitted: {exc}") from exc
    try:
        journal = parse_journal_bytes(data, relpath=name)
        validate_session_graph(journal.entries)
    except OmpSessionError as exc:
        raise _fail(f"fork result journal is invalid: {exc}") from exc
    if is_child_journal(journal):
        raise _fail("fork result is a child/agent journal")
    if journal.header.id == source_session_id:
        raise _fail("fork result reused the source session id")
    if journal.header.parent_session != source_session_id:
        raise _fail("fork result parentSession disagrees with the source id")
    try:
        source_data = read_manifest_bound(live_fd, manifest, source_primary)
    except Exception as exc:
        raise _fail(f"source primary cannot be re-admitted: {exc}") from exc
    if hashlib.sha256(source_data).hexdigest() != source_sha256:
        raise _fail("source journal changed during the fork")
    return name, journal.header.id, hashlib.sha256(data).hexdigest()


def validate_in_place_result(
    *,
    live_fd: int,
    pre_inventory: tuple[str, ...],
    pre_manifest_sha256: str,
    pre_bytes: bytes,
    source_primary: str,
    source_session_id: str,
) -> str:
    """Require same inventory, same header id, valid slot, prefix + extension.

    The pre-resume body (everything after the 256-byte pinned title slot) must
    be a byte-prefix of the post-resume body and strictly shorter: the child
    only appends complete physical records to the same primary.
    """
    try:
        post_inventory = session_inventory_fd(live_fd)
    except LaunchFsError as exc:
        raise _fail(f"live inventory cannot be admitted: {exc}") from exc
    if tuple(post_inventory) != tuple(pre_inventory):
        raise _fail("in-place resume changed the live inventory")
    manifest = build_session_manifest(live_fd)
    if manifest.manifest_sha256 == pre_manifest_sha256:
        raise _fail("in-place resume left the live manifest unchanged")
    try:
        post = read_manifest_bound(live_fd, manifest, source_primary)
    except Exception as exc:
        raise _fail(f"resumed primary cannot be re-admitted: {exc}") from exc
    try:
        journal = parse_journal_bytes(post, relpath=source_primary)
        validate_session_graph(journal.entries)
    except OmpSessionError as exc:
        raise _fail(f"resumed primary journal is invalid: {exc}") from exc
    if journal.header.id != source_session_id:
        raise _fail("in-place resume changed the header session id")
    body_pre = pre_bytes[256:]
    body_post = post[256:]
    if not body_post.startswith(body_pre):
        raise _fail("in-place resume replaced or reordered the pre-resume body")
    if len(body_post) <= len(body_pre):
        raise _fail("in-place resume did not add a complete physical record")
    return hashlib.sha256(post).hexdigest()
