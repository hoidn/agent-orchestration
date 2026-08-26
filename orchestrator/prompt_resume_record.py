"""Task 11: the one mandatory continuation record and its atomic publication.

After any started child the bridge commits exactly one next closed
``session_continuation.v1`` record (success or failed). Publication is a
no-replace rename of a temp file created inside the retained chain directory,
bound to the retained sessions/chain identities and the created inode — the
same directory/created-inode contract as the Task 9 link sink. Any failure
raises ``ContinuationRecordError`` so the orchestrator surfaces it as its own
stable bridge error instead of masking the recorded outcome.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat

from orchestrator._common.safe_tree import RegularFileRow, SafeTreeError, read_regular_file
from orchestrator._common.io_atomic import RenameNoreplaceError, rename_noreplace_at
from orchestrator.prompt_session_chain import read_continuations

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class ContinuationRecordError(Exception):
    """The exactly-one next continuation record could not be published."""


def build_record(
    *,
    link_raw: bytes,
    records: list[bytes],
    active,
    mode: str,
    child_exit_code: int,
    failure: str | None,
    result: dict[str, str | None],
    started_at: str,
    ended_at: str,
    pin,
    interactive_argv,
    confinement: dict[str, object] | None,
    conf_manifest: str | None,
    post_manifest: str | None,
    env_names: list[str],
) -> bytes:
    """Build the exact closed continuation record for the one outcome."""
    previous = link_raw if not records else records[-1]
    record = {
        "schema_version": "session_continuation.v1",
        "sequence": len(records) + 1,
        "previous_sha256": hashlib.sha256(previous).hexdigest(),
        "status": "success" if failure is None else "failed",
        "mode": mode,
        "source": {
            "session_id": active.session_id,
            "primary_basename": active.primary_basename,
            "journal_sha256": active.journal_sha256,
        },
        "result": result,
        "started_at": started_at,
        "ended_at": ended_at,
        "child_exit_code": child_exit_code,
        "failure": failure,
        "binary": {
            "platform": pin.platform,
            "arch": pin.arch,
            "version": pin.version,
            "sha256": pin.executable_sha256,
        },
        "conf_manifest_sha256": conf_manifest,
        "launch": {"argv": list(interactive_argv), "env_names": list(env_names)},
        "confinement": confinement,
        "pre_live_manifest_sha256": active.live_manifest_sha256,
        "post_live_manifest_sha256": post_manifest,
    }
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise ContinuationRecordError("record write made no progress")
        remaining = remaining[written:]


def publish_continuation(
    *,
    run_fd: int,
    sessions_fd: int,
    sessions_identity: tuple[int, int],
    visit_key: str,
    records: list[bytes],
    expected_chain_identity: tuple[int, int] | None,
    expected_names: tuple[str, ...],
    payload: bytes,
) -> None:
    """Atomically append the next no-replace record with inode binding."""
    sequence = len(records) + 1
    name = f"{sequence}.json"
    chain_name = f"{visit_key}.continuations"
    try:
        try:
            chain_fd = os.open(chain_name, _DIR_FLAGS, dir_fd=sessions_fd)
            if expected_chain_identity is None:
                os.close(chain_fd)
                raise ContinuationRecordError(
                    "continuation directory appeared during publication"
                )
        except FileNotFoundError:
            if expected_chain_identity is not None:
                raise ContinuationRecordError(
                    "continuation directory disappeared during publication"
                )
            try:
                os.mkdir(chain_name, mode=0o700, dir_fd=sessions_fd)
            except FileExistsError as exc:
                raise ContinuationRecordError(
                    "continuation directory appeared during publication"
                ) from exc
            chain_fd = os.open(chain_name, _DIR_FLAGS, dir_fd=sessions_fd)
    except OSError as exc:
        raise ContinuationRecordError(str(exc)) from exc
    try:
        chain_identity = os.fstat(chain_fd)
        if (
            expected_chain_identity is not None
            and (chain_identity.st_dev, chain_identity.st_ino)
            != expected_chain_identity
        ):
            raise ContinuationRecordError(
                "continuation directory changed before publication"
            )
        try:
            current_records, current_names, current_identity = read_continuations(
                sessions_fd, visit_key
            )
        except Exception as exc:
            raise ContinuationRecordError(
                f"continuation chain cannot be revalidated: {exc}"
            ) from exc
        if (
            current_records != records
            or current_names != expected_names
            or current_identity
            != (chain_identity.st_dev, chain_identity.st_ino)
        ):
            raise ContinuationRecordError(
                "continuation chain changed before publication"
            )
        temp = f".{sequence}.json-{secrets.token_hex(8)}.tmp"
        try:
            fd = os.open(
                temp,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=chain_fd,
            )
            try:
                _write_all(fd, payload)
                created = os.fstat(fd)
                if created.st_size != len(payload):
                    raise ContinuationRecordError("record write was short")
            finally:
                os.close(fd)
        except (OSError, ContinuationRecordError) as exc:
            try:
                os.unlink(temp, dir_fd=chain_fd)
            except OSError:
                pass
            if isinstance(exc, ContinuationRecordError):
                raise
            raise ContinuationRecordError(str(exc)) from exc
        try:
            rename_noreplace_at(chain_fd, temp, chain_fd, name)
        except RenameNoreplaceError as exc:
            try:
                os.unlink(temp, dir_fd=chain_fd)
            except OSError:
                pass
            raise ContinuationRecordError("continuation record already exists") from exc
        canonical_fd = os.open("provider_sessions", _DIR_FLAGS, dir_fd=run_fd)
        try:
            canonical_identity = os.fstat(canonical_fd)
            retained = os.stat(chain_name, dir_fd=sessions_fd, follow_symlinks=False)
            canonical = os.stat(chain_name, dir_fd=canonical_fd, follow_symlinks=False)
            target = os.stat(name, dir_fd=chain_fd, follow_symlinks=False)
        finally:
            os.close(canonical_fd)
        bound = (
            (canonical_identity.st_dev, canonical_identity.st_ino) == sessions_identity
            and (retained.st_dev, retained.st_ino)
            == (chain_identity.st_dev, chain_identity.st_ino)
            and (canonical.st_dev, canonical.st_ino)
            == (chain_identity.st_dev, chain_identity.st_ino)
            and (target.st_dev, target.st_ino) == (created.st_dev, created.st_ino)
        )
        if not bound:
            raise ContinuationRecordError(
                "continuation directory changed during publication"
            )
        if (
            target.st_nlink != 1
            or target.st_uid != os.getuid()
            or stat.S_IMODE(target.st_mode) != 0o600
            or target.st_size != len(payload)
        ):
            raise ContinuationRecordError("published continuation record is not private")
        expected = RegularFileRow(
            relative_path=name,
            size_bytes=target.st_size,
            device=target.st_dev,
            inode=target.st_ino,
            mode=target.st_mode,
            uid=target.st_uid,
            link_count=target.st_nlink,
            mtime_ns=target.st_mtime_ns,
            ctime_ns=target.st_ctime_ns,
        )
        try:
            published = read_regular_file(
                chain_fd, name, expected=expected, max_bytes=len(payload)
            )
        except SafeTreeError as exc:
            raise ContinuationRecordError(
                "published continuation record changed"
            ) from exc
        if published != payload:
            raise ContinuationRecordError(
                "published continuation record bytes changed"
            )
        try:
            final_records, final_names, final_identity = read_continuations(
                sessions_fd, visit_key
            )
        except Exception as exc:
            raise ContinuationRecordError(
                f"published continuation chain cannot be revalidated: {exc}"
            ) from exc
        if (
            final_records != [*records, payload]
            or final_names != (*expected_names, name)
            or final_identity
            != (chain_identity.st_dev, chain_identity.st_ino)
        ):
            raise ContinuationRecordError(
                "published continuation chain changed"
            )
    finally:
        os.close(chain_fd)
