"""Task 11: physical fork/in-place journal postconditions for the TTY bridge.

The bridge spawns the interactive OMP child with inherited stdio, then judges
the live session tree through these exact predicates. Every failure is a
terminal failure: the bridge publishes exactly one failed continuation record
and the tail permanently blocks later orchestrator lookups (Task 9).
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass

from orchestrator._common.safe_tree import SafeTreeError
from orchestrator.providers.omp_conf import (
    OmpConfError,
    admit_conf_tree,
    revalidate_materialized_conf,
)
from orchestrator.providers.omp_launch_fs import (
    LaunchFsError,
    open_private_exec_fd,
    sha256_fd,
    source_owner_admitted,
)
from orchestrator.providers.omp_observation import is_advisor_name, is_child_journal
from orchestrator.providers.omp_session import (
    OmpSessionError,
    parse_journal_bytes,
    validate_session_graph,
)
from orchestrator.providers.omp_session_manifest import (
    SessionManifest,
    build_session_manifest,
)
from orchestrator.prompt_session_chain import read_manifest_bound
from orchestrator.prompt_resume_preflight import (
    LaunchPlan,
    PreflightError,
    capture_scaffold_inputs,
    open_relative,
    read_frame_binary,
)


class ResumePostconditionError(Exception):
    """One fork/in-place physical journal predicate failed."""


@dataclass(frozen=True, slots=True)
class ResumeResultSnapshot:
    session_id: str
    primary_basename: str
    journal_sha256: str


def _fail(detail: str) -> ResumePostconditionError:
    return ResumePostconditionError(detail)


def capture_post_live(live_fd: int) -> SessionManifest:
    """Capture one stable, immutable post-child session-tree snapshot."""
    try:
        return build_session_manifest(live_fd)
    except (OmpSessionError, OSError) as exc:
        raise _fail(f"post-child live tree cannot be admitted: {exc}") from exc


def validate_fork_result(
    *,
    live_fd: int,
    snapshot: SessionManifest,
    pre_inventory: tuple[str, ...],
    pre_manifest_sha256: str,
    source_primary: str,
    source_sha256: str,
    source_session_id: str,
) -> ResumeResultSnapshot:
    """Require source-identical plus exactly one new direct primary.

    Returns ``(basename, session_id, journal_sha256)`` of the new primary.
    """
    post_inventory = tuple(row.relative_path for row in snapshot.rows)
    pre = set(pre_inventory)
    post = set(post_inventory)
    if not pre <= post:
        raise _fail("fork removed a pre-existing live entry")
    new_names = sorted(post - pre)
    primaries = [
        name
        for name in new_names
        if "/" not in name and name.endswith(".jsonl") and not is_advisor_name(name)
    ]
    if len(primaries) != 1:
        raise _fail(
            f"fork created {len(primaries)} new direct primaries, expected exactly one"
        )
    name = primaries[0]
    artifacts = name.removesuffix(".jsonl") + "/"
    if any(path != name and not path.startswith(artifacts) for path in new_names):
        raise _fail("fork created an artifact outside the result session tree")
    if snapshot.manifest_sha256 == pre_manifest_sha256:
        raise _fail("fork left the live manifest unchanged")
    try:
        data = read_manifest_bound(live_fd, snapshot, name)
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
        source_data = read_manifest_bound(live_fd, snapshot, source_primary)
    except Exception as exc:
        raise _fail(f"source primary cannot be re-admitted: {exc}") from exc
    if hashlib.sha256(source_data).hexdigest() != source_sha256:
        raise _fail("source journal changed during the fork")
    return ResumeResultSnapshot(
        session_id=journal.header.id,
        primary_basename=name,
        journal_sha256=hashlib.sha256(data).hexdigest(),
    )


def validate_in_place_result(
    *,
    live_fd: int,
    snapshot: SessionManifest,
    pre_inventory: tuple[str, ...],
    pre_manifest_sha256: str,
    pre_bytes: bytes,
    source_primary: str,
    source_session_id: str,
) -> ResumeResultSnapshot:
    """Require same inventory, same header id, valid slot, prefix + extension.

    The pre-resume body (everything after the 256-byte pinned title slot) must
    be a byte-prefix of the post-resume body and strictly shorter: the child
    only appends complete physical records to the same primary.
    """
    post_inventory = tuple(row.relative_path for row in snapshot.rows)
    if post_inventory != pre_inventory:
        raise _fail("in-place resume changed the live inventory")
    if snapshot.manifest_sha256 == pre_manifest_sha256:
        raise _fail("in-place resume left the live manifest unchanged")
    try:
        post = read_manifest_bound(live_fd, snapshot, source_primary)
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
    return ResumeResultSnapshot(
        session_id=source_session_id,
        primary_basename=source_primary,
        journal_sha256=hashlib.sha256(post).hexdigest(),
    )

def revalidate_post_live(
    *,
    run_fd: int,
    live_fd: int,
    live_relpath: str,
    snapshot: SessionManifest,
) -> None:
    """Bind the captured whole-tree snapshot to the canonical live directory."""
    canonical_fd = -1
    try:
        canonical_fd = open_relative(run_fd, live_relpath)
        retained = os.fstat(live_fd)
        canonical = os.fstat(canonical_fd)
        if (retained.st_dev, retained.st_ino) != (
            canonical.st_dev,
            canonical.st_ino,
        ):
            raise _fail("canonical live session directory changed")
        if build_session_manifest(live_fd) != snapshot:
            raise _fail("live session tree changed after capture")
    except ResumePostconditionError:
        raise
    except Exception as exc:
        raise _fail(f"live session tree cannot be revalidated: {exc}") from exc
    finally:
        if canonical_fd >= 0:
            os.close(canonical_fd)


def verify_frozen_conf(
    *, run_fd: int, frozen_relpath: str, expected_digest: str
) -> None:
    try:
        frozen_fd = open_relative(run_fd, frozen_relpath)
    except OSError as exc:
        raise PreflightError(
            "prompt_resume_conf_invalid", f"frozen conf cannot be opened: {exc}"
        ) from exc
    try:
        try:
            manifest = admit_conf_tree(frozen_fd)
        except (OmpConfError, SafeTreeError, OSError, TypeError, ValueError) as exc:
            raise PreflightError(
                "prompt_resume_conf_invalid",
                f"frozen conf cannot be admitted: {exc}",
            ) from exc
        if manifest.manifest_sha256 != expected_digest:
            raise PreflightError(
                "prompt_resume_conf_invalid",
                "frozen conf manifest disagrees with the link",
            )
    finally:
        os.close(frozen_fd)


def verify_binary_inputs(*, source_path: str, private: str, pin) -> None:
    source_fd = private_fd = -1
    try:
        if not os.path.isabs(source_path):
            raise LaunchFsError("binary resolver returned a non-absolute path")
        source_fd = os.open(
            source_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or not source_owner_admitted(before.st_uid)
            or before.st_mode & 0o222
            or before.st_nlink != 1
        ):
            raise LaunchFsError("source binary authority changed")
        if sha256_fd(source_fd) != pin.executable_sha256:
            raise LaunchFsError("source binary digest changed")
        after = os.fstat(source_fd)
        stable = (
            "st_dev", "st_ino", "st_size", "st_mode", "st_uid", "st_nlink",
            "st_mtime_ns", "st_ctime_ns",
        )
        if any(
            getattr(after, name) != getattr(before, name)
            for name in stable
        ):
            raise LaunchFsError("source binary changed during revalidation")
        private_fd = open_private_exec_fd([private])
    except (LaunchFsError, OSError) as exc:
        raise PreflightError(
            "prompt_resume_binary_invalid", f"binary input changed: {exc}"
        ) from exc
    finally:
        if private_fd >= 0:
            os.close(private_fd)
        if source_fd >= 0:
            os.close(source_fd)

def revalidate_launch_inputs(
    *,
    run_fd: int,
    resolved,
    plan: LaunchPlan,
    pin,
    binary_resolver,
    workspace: str,
) -> None:
    """Reject child-time drift in every immutable X8 launch input."""
    plan.namespace.revalidate()
    link = resolved.link.document
    frame_binary = read_frame_binary(run_fd, resolved.visit_key)
    if frame_binary != plan.frame_binary:
        raise PreflightError(
            "prompt_resume_binary_invalid", "launch frame binary changed"
        )
    scaffold = capture_scaffold_inputs(
        run_fd=run_fd,
        workspace=workspace,
        scaffold_relpath=link["scaffold_relpath"],
        link=resolved.link,
        frame_binary=plan.frame_binary,
    )
    if scaffold != plan.scaffold:
        raise PreflightError(
            "prompt_resume_scaffold_invalid",
            "captured scaffold changed after child start",
        )
    if link["provider"]["lane"] in ("no-tools", "conf"):
        verify_frozen_conf(
            run_fd=run_fd,
            frozen_relpath=link["paths"]["conf"],
            expected_digest=link["digests"]["conf_manifest_sha256"],
        )
        if plan.profile_attempt is None or plan.conf_snapshot is None:
            raise PreflightError(
                "prompt_resume_conf_invalid",
                "profile attempt authority is absent",
            )
        try:
            revalidate_materialized_conf(
                plan.profile_attempt, plan.conf_snapshot
            )
        except Exception as exc:
            raise PreflightError(
                "prompt_resume_conf_invalid",
                f"materialized conf changed after child start: {exc}",
            ) from exc
    try:
        source_binary = binary_resolver()
    except Exception as exc:
        raise PreflightError(
            "prompt_resume_binary_invalid",
            f"binary resolver failed after the child: {exc}",
        ) from exc
    if source_binary != plan.source_binary:
        raise PreflightError(
            "prompt_resume_binary_invalid", "resolved binary path changed"
        )
    verify_binary_inputs(
        source_path=source_binary,
        private=plan.private,
        pin=pin,
    )
