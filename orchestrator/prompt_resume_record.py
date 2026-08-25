"""Task 10: the one mandatory continuation record and its atomic publication.

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

from orchestrator._common.io_atomic import RenameNoreplaceError, rename_noreplace_at
from orchestrator.providers.omp_launch_contract import POSITIVE_ENV_NAMES

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
        "launch": {"argv": list(interactive_argv), "env_names": list(POSITIVE_ENV_NAMES)},
        "confinement": confinement,
        "pre_live_manifest_sha256": active.live_manifest_sha256,
        "post_live_manifest_sha256": post_manifest,
    }
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def publish_continuation(
    *,
    run_fd: int,
    sessions_fd: int,
    sessions_identity: tuple[int, int],
    visit_key: str,
    records: list[bytes],
    payload: bytes,
) -> None:
    """Atomically append the next no-replace record with inode binding."""
    sequence = len(records) + 1
    name = f"{sequence}.json"
    chain_name = f"{visit_key}.continuations"
    try:
        try:
            chain_fd = os.open(chain_name, _DIR_FLAGS, dir_fd=sessions_fd)
        except FileNotFoundError:
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
        temp = f".{sequence}.json-{secrets.token_hex(8)}.tmp"
        fd = os.open(
            temp,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=chain_fd,
        )
        try:
            os.write(fd, payload)
            created = os.fstat(fd)
            if created.st_size != len(payload):
                raise ContinuationRecordError("record write was short")
        finally:
            os.close(fd)
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
    finally:
        os.close(chain_fd)
