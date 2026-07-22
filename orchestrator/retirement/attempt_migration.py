"""Replay-safe migration of one explicitly reviewed repository attempt.

The mechanism is intentionally policy-neutral.  A caller supplies the exact
attempt path manifest, review authority, lineage coordinates, and protected
paths.  This module only proves and applies that content-addressed disposition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .safe_io import (
    AtomicPublishError,
    bind_logical_parent,
    capture_regular_file_at,
    conditional_quarantine_file_at,
    conditional_publish_file_at,
)


SCHEMA_VERSION = "attempt_migration_disposition.v1"
POST_REPORT_SCHEMA_VERSION = "attempt_migration_post_report.v1"
INCIDENT_SCHEMA_VERSION = "attempt_migration_incident.v1"
DISPOSITION = "archive_failed_pre_adoption_attempt_and_restore_tracked_files"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
GIT_STATUS_RE = re.compile(r"^[ MADRCUT?!]{2}$")
TOP_LEVEL_KEYS = {
    "schema_version",
    "disposition",
    "governing_plan_binding",
    "migration_plan_binding",
    "authority_review_bindings",
    "attempt_binding",
    "pre_move_repository_state",
    "protected_path_bindings",
    "ledger_lineage",
    "attempt_rows",
    "attempt_path_count",
    "attempt_path_set_sha256",
    "archive_path_set_sha256",
    "normalized_row_set_sha256",
    "normalized_disposition_sha256",
    "claims_not_made",
}
ROW_KEYS = {
    "original_path",
    "archive_path",
    "tracked_state",
    "file_type",
    "lstat_mode",
    "size",
    "sha256",
}
CLAIMS_NOT_MADE = [
    "The captured attempt stopped before personal owner adoption.",
    "None of the captured baseline, reviews, or pending form may be consumed by a later attestation, index, or completion claim.",
    "Archival relocation preserves bytes but grants no mutation or completion authority.",
    "A later attempt may begin only after the tracked live file equals its reviewed restoration binding.",
]
POST_CLAIMS_NOT_MADE = [
    "This report proves only the exact reviewed archival move and tracked-file restoration.",
    "This report grants no owner adoption, workflow execution, remediation, or completion authority.",
]
AUTHORITY_SUBJECT_CLAIMS_NOT_MADE = [
    "This subject authorizes only review of the bound generic migration mechanism and synthetic verification evidence.",
    "This subject does not itself authorize relocation, owner adoption, workflow execution, or completion.",
]
AUTHORITY_SUBJECT_KEYS = {
    "schema_version",
    "governing_plan_binding",
    "migration_plan_binding",
    "expected_paths_manifest_binding",
    "protected_path_bindings",
    "mechanism_binding",
    "test_binding",
    "evidence_bindings",
    "normalized_subject_sha256",
    "claims_not_made",
}
AUTHORITY_EVIDENCE_ROLES = frozenset(
    {
        "candidate_manifest",
        "exact_diff",
        "focused_test_evidence",
        "broad_test_evidence",
    }
)
ARTIFACT_ROLES = (
    "baseline",
    "baseline_specification_review",
    "baseline_quality_review",
    "pending_request",
    "pending_snapshot",
    "pending_record",
)
V2_SCHEMA_VERSION = "attempt_migration_disposition.v2"
V2_DISPOSITION = (
    "archive_invalidated_owner_adopted_uncommitted_attempt_and_restore_tracked_files"
)
V2_TOP_LEVEL_KEYS = TOP_LEVEL_KEYS | {"attempt_lifecycle"}
V2_ARTIFACT_ROLES = (
    "baseline",
    "baseline_specification_review",
    "baseline_quality_review",
    "workspace_baseline",
    "attestation_request",
    "attestation_snapshot",
    "attestation_record",
)
V2_ATTEMPT_LIFECYCLE_KEYS = {
    "adoption_state",
    "repository_commit_state",
    "invalidation_reason",
    "incident_binding",
    "workspace_baseline_role",
    "owner_attestation_role",
    "adoption_transfer",
}
V2_CLAIMS_NOT_MADE = [
    "The captured attempt was personally owner-adopted but remained uncommitted when its repository predecessor was invalidated.",
    "Historical owner adoption remains bound only to the archived attempt and may not be transferred to or consumed by any later attestation, index, or completion claim.",
    "Archival relocation preserves bytes but grants no mutation or completion authority.",
    "A later attempt may begin only after the tracked live file equals its reviewed restoration binding.",
]
CONTENT_METADATA_FIELDS = ("file_type", "lstat_mode", "size", "sha256")
INCIDENT_TOP_LEVEL_KEYS = {
    "schema_version",
    "governing_plan_binding",
    "migration_plan_binding",
    "workspace_baseline_binding",
    "owner_attestation_binding",
    "pending_attestation_snapshot_binding",
    "known_failure_baseline_binding",
    "expected_paths_manifest_binding",
    "source_root",
    "intended_predecessor",
    "predecessor_projection",
    "pre_move_repository_state",
    "attempt_rows",
    "attempt_path_count",
    "attempt_path_set_sha256",
    "normalized_attempt_row_set_sha256",
    "adoption_facts",
    "normalized_incident_sha256",
    "claims_not_made",
}
INCIDENT_ROW_KEYS = {
    "path",
    "tracked_state",
    "file_type",
    "lstat_mode",
    "size",
    "sha256",
}
INCIDENT_ADOPTION_FACT_KEYS = {
    "adoption_state",
    "repository_commit_state",
    "evidence_status",
    "owner_identity",
    "owner_role",
    "confirmed_at",
    "adopted_at",
}
INCIDENT_CLAIMS_NOT_MADE = [
    "This incident makes no claim that the bound uncommitted attempt was sealed "
    "because its recorded workspace-baseline HEAD does not equal the intended "
    "commit predecessor."
]


class AttemptMigrationError(RuntimeError):
    """A closed migration precondition or replay check failed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _canonical_digest(value: Any, *, exclude: str | None = None) -> str:
    if exclude is not None:
        if not isinstance(value, Mapping):
            raise AttemptMigrationError("digest_projection_invalid")
        value = {key: item for key, item in value.items() if key != exclude}
    return _bytes_digest(_canonical_json(value))


def _bytes_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _is_commit_identity(value: Any) -> bool:
    return isinstance(value, str) and COMMIT_RE.fullmatch(value) is not None


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AttemptMigrationError("duplicate_json_key", key)
        value[key] = item
    return value


def _json_bytes(data: bytes, logical_path: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_object)
    except AttemptMigrationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttemptMigrationError("json_invalid", logical_path) from exc
    if not isinstance(value, dict):
        raise AttemptMigrationError("json_root_invalid", logical_path)
    return value


def _relative_path(value: Path | str, *, field: str = "path") -> str:
    text = value.as_posix() if isinstance(value, Path) else value
    if not isinstance(text, str):
        raise AttemptMigrationError("path_invalid", field)
    try:
        text.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise AttemptMigrationError("path_not_utf8", field) from exc
    parsed = PurePosixPath(text)
    if (
        not text
        or parsed.is_absolute()
        or parsed.as_posix() != text
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise AttemptMigrationError("path_invalid", f"{field}:{text!r}")
    return text


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def _reject_output_overlap(
    path: str, source_root: str, archive_root: str, originals: Sequence[str] = ()
) -> None:
    if _under(path, source_root) or _under(path, archive_root) or path in originals:
        raise AttemptMigrationError("output_path_overlaps_migration", path)


def _git(
    repository_root: Path, *arguments: str, input_bytes: bytes | None = None
) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository_root,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise AttemptMigrationError(
            "git_command_failed", f"{arguments[0] if arguments else 'git'}:{detail}"
        )
    return completed.stdout


def _git_is_ancestor(repository_root: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    raise AttemptMigrationError(
        "git_command_failed",
        "merge-base:" + completed.stderr.decode("utf-8", "replace").strip(),
    )


def _repository_root(value: Path | str) -> Path:
    supplied = Path(value).resolve(strict=True)
    try:
        actual = Path(
            _git(supplied, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        ).resolve(strict=True)
    except (OSError, UnicodeDecodeError) as exc:
        raise AttemptMigrationError("repository_root_invalid") from exc
    if supplied != actual:
        raise AttemptMigrationError("repository_root_mismatch")
    return supplied


def _open_parent(
    repository_root: Path, relative_path: Path | str, *, create: bool = False
) -> tuple[int, str, str]:
    relative = _relative_path(relative_path)
    parts = PurePosixPath(relative).parts
    flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(repository_root, flags)
        for component in parts[:-1]:
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, 0o755, dir_fd=descriptor)
                child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1], relative
    except FileNotFoundError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise AttemptMigrationError("path_parent_missing", relative) from exc
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise AttemptMigrationError("path_parent_invalid", relative) from exc


def _read_regular(
    repository_root: Path, relative_path: Path | str, *, missing_ok: bool = False
) -> dict[str, Any] | None:
    try:
        parent, name, relative = _open_parent(repository_root, relative_path)
    except AttemptMigrationError as exc:
        if missing_ok and exc.code == "path_parent_missing":
            return None
        raise
    descriptor = -1
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        try:
            descriptor = os.open(name, flags, dir_fd=parent)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise AttemptMigrationError("file_missing", relative)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise AttemptMigrationError("file_not_regular", relative)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after:
            raise AttemptMigrationError("file_changed_during_read", relative)
        data = b"".join(chunks)
        return {
            "path": relative,
            "file_type": "regular",
            "lstat_mode": stat.S_IMODE(after.st_mode),
            "size": len(data),
            "sha256": _bytes_digest(data),
            "data": data,
        }
    except AttemptMigrationError:
        raise
    except OSError as exc:
        raise AttemptMigrationError("file_unreadable", relative) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _public_binding(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": snapshot["path"],
        "file_type": "regular",
        "lstat_mode": snapshot["lstat_mode"],
        "size": snapshot["size"],
        "sha256": snapshot["sha256"],
    }


def _content_binding(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": snapshot["path"],
        "size": snapshot["size"],
        "sha256": snapshot["sha256"],
    }


def _git_regular_mode_matches_live(tree_entry: str, live_mode: int) -> bool:
    git_mode = tree_entry.split()[0]
    return git_mode in {"100644", "100755"} and (
        git_mode == "100755"
    ) == bool(live_mode & 0o111)


def _committed_bytes(
    repository_root: Path, path: str, *, revision: str = "HEAD"
) -> bytes:
    relative = _relative_path(path)
    return _git(repository_root, "show", f"{revision}:{relative}")


def _require_committed_live(
    repository_root: Path, path: str
) -> dict[str, Any]:
    live = _read_regular(repository_root, path)
    assert live is not None
    try:
        committed = _committed_bytes(repository_root, path)
    except AttemptMigrationError as exc:
        if exc.code == "git_command_failed":
            raise AttemptMigrationError("authority_not_committed_at_head", path) from exc
        raise
    if live["data"] != committed:
        raise AttemptMigrationError("authority_not_committed_at_head", path)
    tree_entry = _git(repository_root, "ls-tree", "HEAD", "--", path).decode(
        "ascii", "strict"
    ).strip()
    if not tree_entry:
        raise AttemptMigrationError("authority_not_committed_at_head", path)
    if not _git_regular_mode_matches_live(tree_entry, live["lstat_mode"]):
        raise AttemptMigrationError("committed_mode_mismatch", path)
    return live


def _parse_review(data: bytes, logical_path: str) -> dict[str, Any]:
    review = _json_bytes(data, logical_path)
    if set(review) != {
        "schema_version",
        "review_kind",
        "reviewer",
        "reviewed_at",
        "subject",
        "issues",
        "result",
        "claims_not_made",
    }:
        raise AttemptMigrationError("review_keys_mismatch", logical_path)
    if review["schema_version"] != "review.v1":
        raise AttemptMigrationError("review_schema_invalid", logical_path)
    if not isinstance(review["review_kind"], str) or review[
        "review_kind"
    ] not in {"specification", "code_quality"}:
        raise AttemptMigrationError("review_kind_invalid", logical_path)
    reviewer = review["reviewer"]
    if (
        not isinstance(reviewer, dict)
        or set(reviewer) != {"identity"}
        or not isinstance(reviewer["identity"], str)
        or not reviewer["identity"]
    ):
        raise AttemptMigrationError("reviewer_invalid", logical_path)
    try:
        timestamp = datetime.fromisoformat(review["reviewed_at"])
        if timestamp.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise AttemptMigrationError("reviewed_at_invalid", logical_path) from exc
    subject = review["subject"]
    if (
        not isinstance(subject, dict)
        or set(subject) != {"kind", "path", "sha256"}
        or not isinstance(subject["kind"], str)
        or not subject["kind"]
        or not isinstance(subject["sha256"], str)
        or SHA256_RE.fullmatch(subject["sha256"]) is None
    ):
        raise AttemptMigrationError("review_subject_invalid", logical_path)
    _relative_path(subject["path"], field="review.subject.path")
    if review["result"] != "approved" or review["issues"] != []:
        raise AttemptMigrationError("review_not_approved", logical_path)
    if (
        not isinstance(review["claims_not_made"], list)
        or not review["claims_not_made"]
        or any(not isinstance(item, str) or not item for item in review["claims_not_made"])
    ):
        raise AttemptMigrationError("review_claims_invalid", logical_path)
    return review


def _validate_review_pair(
    repository_root: Path,
    specification_path: str,
    quality_path: str,
    *,
    require_committed: bool,
    expected_subject_kind: str | None = None,
    expected_subject_path: str | None = None,
    expected_subject_sha256: str | None = None,
    expected_subject_snapshot: Mapping[str, Any] | None = None,
    specification_snapshot: Mapping[str, Any] | None = None,
    quality_snapshot: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    readers = _require_committed_live if require_committed else _read_regular
    if (specification_snapshot is None) != (quality_snapshot is None):
        raise AttemptMigrationError("review_snapshot_pair_invalid")
    if specification_snapshot is None:
        specification_file = readers(repository_root, specification_path)
        quality_file = readers(repository_root, quality_path)
    else:
        specification_file = dict(specification_snapshot)
        specification_file["path"] = specification_path
        quality_file = dict(quality_snapshot)
        quality_file["path"] = quality_path
    assert specification_file is not None and quality_file is not None
    specification = _parse_review(specification_file["data"], specification_path)
    quality = _parse_review(quality_file["data"], quality_path)
    if specification["review_kind"] != "specification":
        raise AttemptMigrationError("review_pair_order_invalid", specification_path)
    if quality["review_kind"] != "code_quality":
        raise AttemptMigrationError("review_pair_order_invalid", quality_path)
    if specification["subject"] != quality["subject"]:
        raise AttemptMigrationError("review_pair_subject_mismatch")
    if specification["reviewer"] == quality["reviewer"]:
        raise AttemptMigrationError("review_pair_reviewer_not_distinct")
    if datetime.fromisoformat(specification["reviewed_at"]) > datetime.fromisoformat(
        quality["reviewed_at"]
    ):
        raise AttemptMigrationError("review_pair_timestamp_order_invalid")
    subject = specification["subject"]
    if expected_subject_kind is not None and subject["kind"] != expected_subject_kind:
        raise AttemptMigrationError("review_subject_kind_mismatch")
    if expected_subject_path is not None and subject["path"] != expected_subject_path:
        raise AttemptMigrationError("review_subject_path_mismatch")
    if expected_subject_sha256 is not None and subject["sha256"] != expected_subject_sha256:
        raise AttemptMigrationError("review_subject_digest_mismatch")
    if expected_subject_snapshot is None:
        subject_file = readers(repository_root, subject["path"])
        assert subject_file is not None
    else:
        subject_file = dict(expected_subject_snapshot)
        if subject_file.get("path") != subject["path"]:
            raise AttemptMigrationError("review_subject_path_mismatch")
    if subject_file["sha256"] != subject["sha256"]:
        raise AttemptMigrationError("review_subject_digest_mismatch")
    return specification_file, quality_file, specification, quality


def _parse_status(data: bytes) -> list[dict[str, Any]]:
    fields = data.split(b"\0")
    if fields[-1:] == [b""]:
        fields.pop()
    rows: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(fields):
        field = fields[cursor]
        cursor += 1
        if len(field) < 4 or field[2:3] != b" ":
            raise AttemptMigrationError("git_status_invalid")
        try:
            status_code = field[:2].decode("ascii")
            path = _relative_path(field[3:].decode("utf-8", "strict"))
        except (UnicodeDecodeError, AttemptMigrationError) as exc:
            raise AttemptMigrationError("git_status_invalid") from exc
        source_path: str | None = None
        if status_code[0] in "RC" or status_code[1] in "RC":
            if cursor >= len(fields):
                raise AttemptMigrationError("git_status_invalid")
            try:
                source_path = _relative_path(fields[cursor].decode("utf-8", "strict"))
            except (UnicodeDecodeError, AttemptMigrationError) as exc:
                raise AttemptMigrationError("git_status_invalid") from exc
            cursor += 1
        rows.append(
            {"path": path, "source_path": source_path, "status": status_code}
        )
    return sorted(rows, key=lambda row: (row["path"], row["source_path"] or "", row["status"]))


def _repository_state(repository_root: Path) -> dict[str, Any]:
    status_rows = _parse_status(
        _git(
            repository_root,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
    )
    head = _git(repository_root, "rev-parse", "HEAD").decode("ascii").strip()
    tree = _git(repository_root, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    if COMMIT_RE.fullmatch(head) is None or COMMIT_RE.fullmatch(tree) is None:
        raise AttemptMigrationError("repository_identity_invalid")
    index_path_text = _git(
        repository_root, "rev-parse", "--path-format=absolute", "--git-path", "index"
    ).decode("utf-8").strip()
    index_path = Path(index_path_text).resolve(strict=True)
    try:
        index_relative = index_path.relative_to(repository_root).as_posix()
    except ValueError as exc:
        raise AttemptMigrationError("index_outside_repository") from exc
    index = _read_regular(repository_root, index_relative)
    assert index is not None
    return {
        "head": head,
        "tree": tree,
        "index_sha256": index["sha256"],
        "status_projection": {
            "rows": status_rows,
            "row_count": len(status_rows),
            "normalized_rows_sha256": _canonical_digest(status_rows),
        },
    }


def _validate_repository_state_structure(
    value: Any, *, source_root: str
) -> dict[str, Any]:
    """Validate the closed repository-state projection without reading live state."""

    state = dict(
        _require_keys(
            value,
            {"head", "tree", "index_sha256", "status_projection"},
            "repository_state_keys_mismatch",
        )
    )
    if (
        not _is_commit_identity(state["head"])
        or not _is_commit_identity(state["tree"])
        or not _is_sha256(state["index_sha256"])
    ):
        raise AttemptMigrationError("repository_state_identity_invalid")
    projection = _require_keys(
        state["status_projection"],
        {"rows", "row_count", "normalized_rows_sha256"},
        "status_projection_keys_mismatch",
    )
    if (
        not isinstance(projection["rows"], list)
        or type(projection["row_count"]) is not int
        or projection["row_count"] != len(projection["rows"])
        or projection["normalized_rows_sha256"]
        != _canonical_digest(projection["rows"])
    ):
        raise AttemptMigrationError("status_projection_invalid")
    status_rows = projection["rows"]
    for row in status_rows:
        if not isinstance(row, Mapping) or set(row) != {
            "path",
            "source_path",
            "status",
        }:
            raise AttemptMigrationError("status_projection_row_invalid")
        try:
            _relative_path(row["path"], field="status.path")
            if row["source_path"] is not None:
                _relative_path(row["source_path"], field="status.source_path")
        except (AttemptMigrationError, TypeError) as exc:
            raise AttemptMigrationError("status_projection_row_invalid") from exc
        if (
            not isinstance(row["status"], str)
            or GIT_STATUS_RE.fullmatch(row["status"]) is None
            or row["status"] == "  "
        ):
            raise AttemptMigrationError("status_projection_row_invalid")
        is_rename = row["status"][0] in "RC" or row["status"][1] in "RC"
        if is_rename != (row["source_path"] is not None):
            raise AttemptMigrationError("status_projection_row_invalid")
    _validate_status_projection_boundaries(status_rows, source_root)
    if status_rows != sorted(
        status_rows,
        key=lambda row: (row["path"], row["source_path"] or "", row["status"]),
    ):
        raise AttemptMigrationError("status_projection_row_order_invalid")
    status_identities = [
        (row["path"], row["source_path"], row["status"]) for row in status_rows
    ]
    if len(status_identities) != len(set(status_identities)):
        raise AttemptMigrationError("status_projection_row_duplicate")
    return state


def _validate_status_projection_boundaries(
    rows: Sequence[Mapping[str, Any]], source_root: str
) -> None:
    for row in rows:
        source_path = row.get("source_path")
        if source_path is not None and _under(row["path"], source_root) != _under(
            source_path, source_root
        ):
            raise AttemptMigrationError("status_projection_boundary_crossing")


def _status_paths(rows: Sequence[Mapping[str, Any]], source_root: str) -> list[str]:
    paths: set[str] = set()
    for row in rows:
        for field in ("path", "source_path"):
            value = row.get(field)
            if isinstance(value, str) and _under(value, source_root):
                paths.add(value)
    return sorted(paths)


def _outside_status_paths(
    rows: Sequence[Mapping[str, Any]], source_root: str
) -> list[str]:
    paths: set[str] = set()
    for row in rows:
        for field in ("path", "source_path"):
            value = row.get(field)
            if isinstance(value, str) and not _under(value, source_root):
                paths.add(value)
    return sorted(paths)


def _is_tracked(repository_root: Path, path: str) -> bool:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        cwd=repository_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def _manifest_paths(data: bytes, logical_path: str) -> list[str]:
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise AttemptMigrationError("expected_manifest_not_utf8", logical_path) from exc
    if not text.endswith("\n") or "\r" in text:
        raise AttemptMigrationError("expected_manifest_format_invalid", logical_path)
    raw_paths = text[:-1].split("\n") if text[:-1] else []
    paths = [_relative_path(path, field="expected_manifest.path") for path in raw_paths]
    if not paths or paths != sorted(paths) or len(paths) != len(set(paths)):
        raise AttemptMigrationError("expected_manifest_order_invalid", logical_path)
    return paths


def _incident_manifest_binding(
    snapshot: Mapping[str, Any], paths: Sequence[str]
) -> dict[str, Any]:
    binding = _content_binding(snapshot)
    binding.update(
        {
            "row_count": len(paths),
            "normalized_path_set_sha256": _canonical_digest(list(paths)),
        }
    )
    return binding


def _incident_attempt_rows(
    repository_root: Path, paths: Sequence[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        snapshot = _read_regular(repository_root, path)
        assert snapshot is not None
        rows.append(
            {
                "path": path,
                "tracked_state": (
                    "modified" if _is_tracked(repository_root, path) else "untracked"
                ),
                "file_type": "regular",
                "lstat_mode": snapshot["lstat_mode"],
                "size": snapshot["size"],
                "sha256": snapshot["sha256"],
            }
        )
    return rows


def _incident_status_paths(
    rows: Sequence[Mapping[str, Any]], source_root: str
) -> list[str]:
    paths: list[str] = []
    for row in rows:
        for field in ("path", "source_path"):
            value = row.get(field)
            if isinstance(value, str) and _under(value, source_root):
                paths.append(value)
    if len(paths) != len(set(paths)):
        raise AttemptMigrationError("incident_source_status_duplicate")
    return sorted(paths)


def _broad_issue_detail(issues: Sequence[Any]) -> str:
    return ",".join(
        sorted(
            {
                str(getattr(issue, "code", issue))
                for issue in issues
            }
        )
    )


def _validate_incident_broad_record(
    repository_root: Path,
    record: Mapping[str, Any],
    *,
    role: str,
    validate_bound: bool,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> None:
    from .broad_evidence import (
        validate_bound_record,
        validate_record,
        validate_review_binding_pair,
    )

    shape_issues = validate_record(record)
    if shape_issues:
        raise AttemptMigrationError(
            f"incident_{role}_invalid", _broad_issue_detail(shape_issues)
        )
    if validate_bound:
        bound_issues = validate_bound_record(
            record,
            repository_root,
            bound_file_bytes=bound_file_bytes,
            require_committed_fallback=require_committed_fallback,
        )
        historical_subject_issues = [
            issue
            for issue in bound_issues
            if getattr(issue, "code", None) == "review_pair_subject_invalid"
        ]
        other_bound_issues = [
            issue
            for issue in bound_issues
            if getattr(issue, "code", None) != "review_pair_subject_invalid"
        ]
        if historical_subject_issues:
            baseline = record.get("baseline_binding")
            review_issues = validate_review_binding_pair(
                specification_binding=record.get("specification_review_binding"),
                quality_binding=record.get("quality_review_binding"),
                repository_root=repository_root,
                expected_subject_kind="implementation_failure_baseline",
                expected_subject_binding={
                    "path": baseline.get("path"),
                    "sha256": baseline.get("sha256"),
                }
                if isinstance(baseline, Mapping)
                else None,
                bound_file_bytes=bound_file_bytes,
                require_committed_fallback=require_committed_fallback,
            )
            other_bound_issues.extend(review_issues)
        if other_bound_issues:
            raise AttemptMigrationError(
                f"incident_{role}_binding_invalid",
                _broad_issue_detail(other_bound_issues),
            )


def _issue_coordinates(issues: Sequence[Any]) -> set[tuple[str, str]]:
    return {
        (str(getattr(issue, "code", issue)), str(getattr(issue, "path", "")))
        for issue in issues
    }


def _validate_incident_historical_baseline(
    repository_root: Path,
    baseline: Mapping[str, Any],
    *,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> None:
    """Validate a bound baseline while recognizing only its expected HEAD drift.

    The broad validator is intentionally live-candidate strict.  An incident is
    captured after a corrective descendant commit, so its content-addressed
    baseline graph is historical by construction.  Every ordinary bound check
    still runs; only the two wrapper issues caused by that already-proved HEAD
    drift are accepted, and the nested outcome must fail for that reason alone.
    """

    from .broad_evidence import validate_bound_record, validate_record

    baseline_issues = validate_bound_record(
        baseline,
        repository_root,
        check_ledger_future_absence=False,
        bound_file_bytes=bound_file_bytes,
        require_committed_fallback=require_committed_fallback,
    )
    if not baseline_issues:
        return
    baseline_coordinates = _issue_coordinates(baseline_issues)
    required_baseline_coordinates = {
        ("bound_record_invalid", "$.broad_outcome_binding"),
        ("candidate_git_identity_mismatch", "$.candidate_binding"),
    }
    permitted_candidate_drift = {
        (
            "candidate_path_set_live_mismatch",
            "$.candidate_binding.candidate_paths",
        )
    }
    if (
        not required_baseline_coordinates <= baseline_coordinates
        or baseline_coordinates
        - required_baseline_coordinates
        - permitted_candidate_drift
    ):
        raise AttemptMigrationError(
            "incident_known_failure_baseline_binding_invalid",
            _broad_issue_detail(baseline_issues),
        )

    broad_binding = baseline.get("broad_outcome_binding")
    if not isinstance(broad_binding, Mapping):
        raise AttemptMigrationError(
            "incident_known_failure_baseline_binding_invalid"
        )
    broad_path = broad_binding.get("path")
    broad_data = (
        bound_file_bytes.get(broad_path)
        if bound_file_bytes is not None and isinstance(broad_path, str)
        else None
    )
    broad_snapshot = None
    if broad_data is None:
        broad_snapshot = (
            _require_committed_live(repository_root, broad_path)
            if require_committed_fallback
            else _read_regular(repository_root, broad_path)
        )
    if broad_data is None:
        assert broad_snapshot is not None
        broad_data = broad_snapshot["data"]
    if (
        _bytes_digest(broad_data) != broad_binding.get("sha256")
        or (
            "size" in broad_binding
            and len(broad_data) != broad_binding.get("size")
        )
    ):
        raise AttemptMigrationError(
            "incident_known_failure_baseline_binding_invalid"
        )
    broad = _json_bytes(broad_data, str(broad_path))
    broad_shape_issues = validate_record(broad)
    broad_bound_issues = validate_bound_record(
        broad,
        repository_root,
        check_ledger_future_absence=False,
        bound_file_bytes=bound_file_bytes,
        require_committed_fallback=require_committed_fallback,
    )
    broad_coordinates = _issue_coordinates(broad_bound_issues)
    required_broad_coordinates = {
        ("candidate_git_identity_mismatch", "$.candidate_binding")
    }
    if (
        broad_shape_issues
        or not required_broad_coordinates <= broad_coordinates
        or broad_coordinates - required_broad_coordinates - permitted_candidate_drift
    ):
        raise AttemptMigrationError(
            "incident_known_failure_baseline_binding_invalid",
            _broad_issue_detail([*broad_shape_issues, *broad_bound_issues]),
        )


def _incident_adoption_facts(
    owner_attestation: Mapping[str, Any],
) -> dict[str, Any]:
    owner = owner_attestation.get("owner")
    confirmations = owner_attestation.get("owner_confirmations")
    adoption = owner_attestation.get("owner_adoption")
    if not all(isinstance(value, Mapping) for value in (owner, confirmations, adoption)):
        raise AttemptMigrationError("incident_owner_lifecycle_invalid")
    assert isinstance(owner, Mapping)
    assert isinstance(confirmations, Mapping)
    assert isinstance(adoption, Mapping)
    if (
        owner_attestation.get("evidence_status") != "owner_confirmed"
        or owner.get("identity") != adoption.get("identity")
    ):
        raise AttemptMigrationError("incident_owner_lifecycle_invalid")
    return {
        "adoption_state": "owner_adopted",
        "repository_commit_state": "uncommitted",
        "evidence_status": "owner_confirmed",
        "owner_identity": owner.get("identity"),
        "owner_role": owner.get("role"),
        "confirmed_at": confirmations.get("confirmed_at"),
        "adopted_at": adoption.get("adopted_at"),
    }


def _validate_incident_evidence_records(
    repository_root: Path,
    *,
    workspace_snapshot: Mapping[str, Any],
    owner_snapshot: Mapping[str, Any],
    pending_snapshot: Mapping[str, Any],
    baseline_snapshot: Mapping[str, Any],
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    from .source_bindings import validate_workspace_record_shape

    workspace = _json_bytes(workspace_snapshot["data"], workspace_snapshot["path"])
    workspace_issues = validate_workspace_record_shape(workspace)
    if workspace_issues:
        raise AttemptMigrationError(
            "incident_workspace_baseline_invalid",
            _broad_issue_detail(workspace_issues),
        )

    owner_attestation = _json_bytes(owner_snapshot["data"], owner_snapshot["path"])
    pending_attestation = _json_bytes(
        pending_snapshot["data"], pending_snapshot["path"]
    )
    baseline = _json_bytes(baseline_snapshot["data"], baseline_snapshot["path"])
    _validate_incident_broad_record(
        repository_root,
        owner_attestation,
        role="owner_attestation",
        validate_bound=True,
        bound_file_bytes=bound_file_bytes,
        require_committed_fallback=require_committed_fallback,
    )
    _validate_incident_broad_record(
        repository_root,
        pending_attestation,
        role="pending_attestation",
        validate_bound=True,
        bound_file_bytes=bound_file_bytes,
        require_committed_fallback=require_committed_fallback,
    )
    _validate_incident_broad_record(
        repository_root,
        baseline,
        role="known_failure_baseline",
        validate_bound=False,
    )
    _validate_incident_historical_baseline(
        repository_root,
        baseline,
        bound_file_bytes=bound_file_bytes,
        require_committed_fallback=require_committed_fallback,
    )

    if pending_attestation.get("evidence_status") != "pending_owner_confirmation":
        raise AttemptMigrationError("incident_pending_lifecycle_invalid")
    facts = _incident_adoption_facts(owner_attestation)

    reverted = dict(owner_attestation)
    reverted.update(
        {
            "evidence_status": "pending_owner_confirmation",
            "owner": None,
            "owner_confirmations": {
                "classification_partition_confirmed": False,
                "comparison_only_confirmed": False,
                "confirmed_at": None,
                "exact_failure_table_confirmed": False,
                "no_out_of_scope_repair_confirmed": False,
                "normalization_contract_confirmed": False,
                "reviews_confirmed": False,
            },
            "owner_adoption": None,
        }
    )
    if reverted != pending_attestation:
        raise AttemptMigrationError("incident_attestation_snapshot_mismatch")

    owner_baseline_binding = owner_attestation.get("baseline_binding")
    pending_baseline_binding = pending_attestation.get("baseline_binding")
    if (
        not isinstance(owner_baseline_binding, Mapping)
        or owner_baseline_binding != pending_baseline_binding
        or owner_baseline_binding.get("path") != baseline_snapshot["path"]
        or owner_baseline_binding.get("sha256") != baseline_snapshot["sha256"]
    ):
        raise AttemptMigrationError("incident_baseline_binding_mismatch")
    return (
        workspace,
        owner_attestation,
        pending_attestation,
        baseline,
        facts,
    )


def _validate_incident_structure(record: Any) -> dict[str, Any]:
    incident = dict(
        _require_keys(record, INCIDENT_TOP_LEVEL_KEYS, "incident_keys_mismatch")
    )
    if incident["schema_version"] != INCIDENT_SCHEMA_VERSION:
        raise AttemptMigrationError("incident_schema_invalid")
    if incident["claims_not_made"] != INCIDENT_CLAIMS_NOT_MADE:
        raise AttemptMigrationError("incident_claims_invalid")
    if incident["normalized_incident_sha256"] != _canonical_digest(
        incident, exclude="normalized_incident_sha256"
    ):
        raise AttemptMigrationError("normalized_incident_digest_mismatch")

    for field in (
        "governing_plan_binding",
        "migration_plan_binding",
        "workspace_baseline_binding",
        "owner_attestation_binding",
        "pending_attestation_snapshot_binding",
        "known_failure_baseline_binding",
    ):
        _validate_file_binding(incident[field], full=False)
    manifest = _require_keys(
        incident["expected_paths_manifest_binding"],
        {"path", "size", "sha256", "row_count", "normalized_path_set_sha256"},
        "incident_manifest_binding_invalid",
    )
    _validate_file_binding(
        {key: manifest[key] for key in ("path", "size", "sha256")}, full=False
    )
    if type(manifest["row_count"]) is not int or manifest["row_count"] <= 0:
        raise AttemptMigrationError("incident_manifest_binding_invalid")
    if not _is_sha256(manifest["normalized_path_set_sha256"]):
        raise AttemptMigrationError("incident_manifest_binding_invalid")

    source_root = _relative_path(incident["source_root"], field="source_root")
    pre_move_state = _validate_repository_state_structure(
        incident["pre_move_repository_state"], source_root=source_root
    )
    intended = _require_keys(
        incident["intended_predecessor"],
        {"head", "tree"},
        "incident_predecessor_invalid",
    )
    if not _is_commit_identity(intended["head"]) or not _is_commit_identity(
        intended["tree"]
    ):
        raise AttemptMigrationError("incident_predecessor_invalid")
    if not isinstance(incident["predecessor_projection"], Mapping):
        raise AttemptMigrationError("incident_predecessor_projection_invalid")

    rows = incident["attempt_rows"]
    if not isinstance(rows, list) or not rows:
        raise AttemptMigrationError("incident_attempt_rows_invalid")
    row_paths: list[str] = []
    for value in rows:
        row = _require_keys(value, INCIDENT_ROW_KEYS, "incident_attempt_row_invalid")
        path = _relative_path(row["path"], field="incident_attempt_row.path")
        if not _under(path, source_root):
            raise AttemptMigrationError("incident_attempt_path_outside_source", path)
        if row["tracked_state"] not in {"modified", "untracked"}:
            raise AttemptMigrationError("incident_attempt_row_invalid", path)
        if (
            row["file_type"] != "regular"
            or type(row["lstat_mode"]) is not int
            or not 0 <= row["lstat_mode"] <= 0o7777
            or type(row["size"]) is not int
            or row["size"] < 0
            or not _is_sha256(row["sha256"])
        ):
            raise AttemptMigrationError("incident_attempt_row_invalid", path)
        row_paths.append(path)
    if row_paths != sorted(set(row_paths)):
        raise AttemptMigrationError("incident_attempt_row_order_invalid")
    if (
        type(incident["attempt_path_count"]) is not int
        or incident["attempt_path_count"] != len(rows)
        or incident["attempt_path_set_sha256"] != _canonical_digest(row_paths)
        or incident["normalized_attempt_row_set_sha256"]
        != _canonical_digest(rows)
    ):
        raise AttemptMigrationError("incident_attempt_projection_invalid")
    if manifest["row_count"] != len(rows):
        raise AttemptMigrationError("incident_manifest_binding_invalid")
    if (
        _status_paths(pre_move_state["status_projection"]["rows"], source_root)
        != row_paths
    ):
        raise AttemptMigrationError("incident_source_status_coverage_mismatch")

    facts = _require_keys(
        incident["adoption_facts"],
        INCIDENT_ADOPTION_FACT_KEYS,
        "incident_adoption_facts_invalid",
    )
    if (
        facts["adoption_state"] != "owner_adopted"
        or facts["repository_commit_state"] != "uncommitted"
        or facts["evidence_status"] != "owner_confirmed"
        or any(
            not isinstance(facts[field], str) or not facts[field]
            for field in ("owner_identity", "owner_role")
        )
    ):
        raise AttemptMigrationError("incident_adoption_facts_invalid")
    timestamps: list[datetime] = []
    for field in ("confirmed_at", "adopted_at"):
        try:
            timestamp = datetime.fromisoformat(facts[field])
            if timestamp.tzinfo is None:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise AttemptMigrationError("incident_adoption_facts_invalid") from exc
        timestamps.append(timestamp)
    if timestamps[0] > timestamps[1]:
        raise AttemptMigrationError("incident_adoption_facts_invalid")
    return incident


def _reopen_incident_binding(
    repository_root: Path, binding: Mapping[str, Any], *, role: str
) -> dict[str, Any]:
    snapshot = _read_regular(repository_root, binding["path"])
    assert snapshot is not None
    if _content_binding(snapshot) != dict(binding):
        raise AttemptMigrationError("incident_binding_mismatch", role)
    return snapshot


def validate_attempt_migration_incident(
    repository_root: Path | str, record: Any
) -> dict[str, Any]:
    """Reopen and rederive one closed invalidated-attempt incident."""

    from .source_bindings import (
        SourceBindingError,
        derive_committed_predecessor_lineage,
    )

    root = _repository_root(repository_root)
    incident = _validate_incident_structure(record)
    frozen_state = incident["pre_move_repository_state"]
    frozen_tree = _git(
        root, "rev-parse", f"{frozen_state['head']}^{{tree}}"
    ).decode("ascii").strip()
    if frozen_tree != frozen_state["tree"]:
        raise AttemptMigrationError("incident_repository_state_tree_mismatch")
    snapshots: dict[str, dict[str, Any]] = {}
    for field in ("governing_plan_binding", "migration_plan_binding"):
        snapshot = _require_committed_live(root, incident[field]["path"])
        if _content_binding(snapshot) != incident[field]:
            raise AttemptMigrationError("incident_binding_mismatch", field)
        snapshots[field] = snapshot
    for field in (
        "workspace_baseline_binding",
        "owner_attestation_binding",
        "pending_attestation_snapshot_binding",
        "known_failure_baseline_binding",
    ):
        snapshots[field] = _reopen_incident_binding(
            root, incident[field], role=field
        )
    manifest_binding = incident["expected_paths_manifest_binding"]
    manifest_snapshot = _require_committed_live(root, manifest_binding["path"])
    paths = _manifest_paths(manifest_snapshot["data"], manifest_snapshot["path"])
    if _incident_manifest_binding(manifest_snapshot, paths) != manifest_binding:
        raise AttemptMigrationError("incident_manifest_binding_mismatch")
    source_root = incident["source_root"]
    if any(not _under(path, source_root) for path in paths):
        raise AttemptMigrationError("incident_attempt_path_outside_source")

    workspace, _owner, _pending, baseline, adoption_facts = (
        _validate_incident_evidence_records(
            root,
            workspace_snapshot=snapshots["workspace_baseline_binding"],
            owner_snapshot=snapshots["owner_attestation_binding"],
            pending_snapshot=snapshots["pending_attestation_snapshot_binding"],
            baseline_snapshot=snapshots["known_failure_baseline_binding"],
        )
    )
    if adoption_facts != incident["adoption_facts"]:
        raise AttemptMigrationError("incident_adoption_facts_mismatch")

    intended = incident["intended_predecessor"]
    candidate = baseline.get("candidate_binding")
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("head") != intended["head"]
        or candidate.get("head_tree") != intended["tree"]
    ):
        raise AttemptMigrationError("incident_candidate_predecessor_mismatch")
    try:
        projection = derive_committed_predecessor_lineage(
            root,
            baseline_head=workspace["head"],
            intended_predecessor_head=intended["head"],
            require_uncovered_paths=True,
        )
    except (KeyError, SourceBindingError) as exc:
        raise AttemptMigrationError(
            "incident_predecessor_projection_invalid", str(exc)
        ) from exc
    if (
        projection != incident["predecessor_projection"]
        or projection["intended_predecessor_tree"] != intended["tree"]
    ):
        raise AttemptMigrationError("incident_predecessor_projection_mismatch")

    state = _repository_state(root)
    if not _git_is_ancestor(root, intended["head"], state["head"]):
        raise AttemptMigrationError("incident_predecessor_not_current_ancestor")
    _validate_status_projection_boundaries(
        state["status_projection"]["rows"], source_root
    )
    observed_paths = _incident_status_paths(
        state["status_projection"]["rows"], source_root
    )
    if observed_paths != paths:
        raise AttemptMigrationError("incident_source_set_mismatch")
    required_attempt_bindings = {
        incident[field]["path"]
        for field in (
            "workspace_baseline_binding",
            "owner_attestation_binding",
            "pending_attestation_snapshot_binding",
            "known_failure_baseline_binding",
        )
    }
    if not required_attempt_bindings <= set(paths):
        raise AttemptMigrationError("incident_evidence_outside_attempt")
    if _incident_attempt_rows(root, paths) != incident["attempt_rows"]:
        raise AttemptMigrationError("incident_attempt_rows_mismatch")
    return incident


def _build_attempt_migration_incident(
    repository_root: Path | str,
    *,
    governing_plan_path: Path | str,
    migration_plan_path: Path | str,
    workspace_baseline_path: Path | str,
    owner_attestation_path: Path | str,
    pending_attestation_snapshot_path: Path | str,
    known_failure_baseline_path: Path | str,
    expected_paths_manifest_path: Path | str,
    source_root: Path | str,
    intended_predecessor_head: str,
    pre_move_repository_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Purely derive an incident from one already captured repository state."""

    from .source_bindings import (
        SourceBindingError,
        derive_committed_predecessor_lineage,
    )

    root = _repository_root(repository_root)
    source_prefix = _relative_path(source_root, field="source_root")
    path_fields = {
        "governing_plan_binding": governing_plan_path,
        "migration_plan_binding": migration_plan_path,
        "workspace_baseline_binding": workspace_baseline_path,
        "owner_attestation_binding": owner_attestation_path,
        "pending_attestation_snapshot_binding": pending_attestation_snapshot_path,
        "known_failure_baseline_binding": known_failure_baseline_path,
    }
    snapshots: dict[str, dict[str, Any]] = {}
    for field, raw_path in path_fields.items():
        path = _relative_path(raw_path, field=field)
        snapshot = (
            _require_committed_live(root, path)
            if field in {"governing_plan_binding", "migration_plan_binding"}
            else _read_regular(root, path)
        )
        assert snapshot is not None
        snapshots[field] = snapshot

    manifest_path = _relative_path(
        expected_paths_manifest_path, field="expected_paths_manifest_path"
    )
    manifest_snapshot = _require_committed_live(root, manifest_path)
    paths = _manifest_paths(manifest_snapshot["data"], manifest_path)
    if any(not _under(path, source_prefix) for path in paths):
        raise AttemptMigrationError("incident_attempt_path_outside_source")

    workspace, _owner, _pending, baseline, adoption_facts = (
        _validate_incident_evidence_records(
            root,
            workspace_snapshot=snapshots["workspace_baseline_binding"],
            owner_snapshot=snapshots["owner_attestation_binding"],
            pending_snapshot=snapshots["pending_attestation_snapshot_binding"],
            baseline_snapshot=snapshots["known_failure_baseline_binding"],
        )
    )
    if not _is_commit_identity(intended_predecessor_head):
        raise AttemptMigrationError("incident_predecessor_invalid")
    try:
        projection = derive_committed_predecessor_lineage(
            root,
            baseline_head=workspace["head"],
            intended_predecessor_head=intended_predecessor_head,
            require_uncovered_paths=True,
        )
    except (KeyError, SourceBindingError) as exc:
        raise AttemptMigrationError(
            "incident_predecessor_projection_invalid", str(exc)
        ) from exc
    intended = {
        "head": intended_predecessor_head,
        "tree": projection["intended_predecessor_tree"],
    }
    candidate = baseline.get("candidate_binding")
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("head") != intended["head"]
        or candidate.get("head_tree") != intended["tree"]
    ):
        raise AttemptMigrationError("incident_candidate_predecessor_mismatch")

    state = dict(pre_move_repository_state)
    _validate_repository_state_structure(state, source_root=source_prefix)
    if not _git_is_ancestor(root, intended_predecessor_head, state["head"]):
        raise AttemptMigrationError("incident_predecessor_not_current_ancestor")
    _validate_status_projection_boundaries(
        state["status_projection"]["rows"], source_prefix
    )
    if (
        _incident_status_paths(state["status_projection"]["rows"], source_prefix)
        != paths
    ):
        raise AttemptMigrationError("incident_source_set_mismatch")

    required_attempt_paths = {
        snapshots[field]["path"]
        for field in (
            "workspace_baseline_binding",
            "owner_attestation_binding",
            "pending_attestation_snapshot_binding",
            "known_failure_baseline_binding",
        )
    }
    if not required_attempt_paths <= set(paths):
        raise AttemptMigrationError("incident_evidence_outside_attempt")
    rows = _incident_attempt_rows(root, paths)
    record: dict[str, Any] = {
        "schema_version": INCIDENT_SCHEMA_VERSION,
        "governing_plan_binding": _content_binding(
            snapshots["governing_plan_binding"]
        ),
        "migration_plan_binding": _content_binding(
            snapshots["migration_plan_binding"]
        ),
        "workspace_baseline_binding": _content_binding(
            snapshots["workspace_baseline_binding"]
        ),
        "owner_attestation_binding": _content_binding(
            snapshots["owner_attestation_binding"]
        ),
        "pending_attestation_snapshot_binding": _content_binding(
            snapshots["pending_attestation_snapshot_binding"]
        ),
        "known_failure_baseline_binding": _content_binding(
            snapshots["known_failure_baseline_binding"]
        ),
        "expected_paths_manifest_binding": _incident_manifest_binding(
            manifest_snapshot, paths
        ),
        "source_root": source_prefix,
        "intended_predecessor": intended,
        "predecessor_projection": projection,
        "pre_move_repository_state": state,
        "attempt_rows": rows,
        "attempt_path_count": len(rows),
        "attempt_path_set_sha256": _canonical_digest(paths),
        "normalized_attempt_row_set_sha256": _canonical_digest(rows),
        "adoption_facts": adoption_facts,
        "normalized_incident_sha256": "",
        "claims_not_made": INCIDENT_CLAIMS_NOT_MADE,
    }
    record["normalized_incident_sha256"] = _canonical_digest(
        record, exclude="normalized_incident_sha256"
    )
    _validate_incident_structure(record)
    return validate_attempt_migration_incident(root, record)


def build_attempt_migration_incident(
    repository_root: Path | str,
    *,
    governing_plan_path: Path | str,
    migration_plan_path: Path | str,
    workspace_baseline_path: Path | str,
    owner_attestation_path: Path | str,
    pending_attestation_snapshot_path: Path | str,
    known_failure_baseline_path: Path | str,
    expected_paths_manifest_path: Path | str,
    source_root: Path | str,
    intended_predecessor_head: str,
) -> dict[str, Any]:
    """Build and fully validate one deterministic invalidation incident."""

    root = _repository_root(repository_root)
    return _build_attempt_migration_incident(
        root,
        governing_plan_path=governing_plan_path,
        migration_plan_path=migration_plan_path,
        workspace_baseline_path=workspace_baseline_path,
        owner_attestation_path=owner_attestation_path,
        pending_attestation_snapshot_path=pending_attestation_snapshot_path,
        known_failure_baseline_path=known_failure_baseline_path,
        expected_paths_manifest_path=expected_paths_manifest_path,
        source_root=source_root,
        intended_predecessor_head=intended_predecessor_head,
        pre_move_repository_state=_repository_state(root),
    )


def _binding_from_row(row: Mapping[str, Any], *, path_field: str) -> dict[str, Any]:
    return {
        "path": row[path_field],
        "file_type": row["file_type"],
        "lstat_mode": row["lstat_mode"],
        "size": row["size"],
        "sha256": row["sha256"],
    }


def _content_metadata(binding: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(binding[field] for field in CONTENT_METADATA_FIELDS)


def _byte_identity(binding: Mapping[str, Any]) -> tuple[Any, Any]:
    return binding["size"], binding["sha256"]


def _validate_semantic_coordinates(
    *,
    rows: Sequence[Mapping[str, Any]],
    artifact_bindings: Mapping[str, Mapping[str, Any]],
    generation5: Mapping[str, Any],
    generation11: Mapping[str, Any],
    restoration: Mapping[str, Any],
    artifact_roles: Sequence[str] = ARTIFACT_ROLES,
    snapshot_record_roles: tuple[str, str] | None = (
        "pending_snapshot",
        "pending_record",
    ),
) -> None:
    coordinate_bindings: dict[str, Mapping[str, Any]] = {
        "generation5_request": generation5["request_binding"],
        "generation5_snapshot": generation5["snapshot_binding"],
        "generation11_request": generation11["request_binding"],
        "generation11_snapshot": generation11["snapshot_binding"],
        "generation11_live": generation11["live_binding"],
    }
    coordinate_bindings.update(
        {role: artifact_bindings[role] for role in artifact_roles}
    )
    paths = [binding["path"] for binding in coordinate_bindings.values()]
    if len(paths) != len(set(paths)):
        raise AttemptMigrationError("semantic_coordinate_alias")

    row_by_path = {row["original_path"]: row for row in rows}
    row_backed = {
        role: binding
        for role, binding in coordinate_bindings.items()
        if role not in {"generation5_request", "generation5_snapshot"}
    }
    for role, binding in row_backed.items():
        row = row_by_path.get(binding["path"])
        if row is None or binding != _binding_from_row(
            row, path_field="original_path"
        ):
            raise AttemptMigrationError(
                "semantic_coordinate_row_binding_mismatch", role
            )
    live_row = row_by_path[generation11["live_binding"]["path"]]
    if live_row["tracked_state"] != "modified":
        raise AttemptMigrationError(
            "semantic_coordinate_row_binding_mismatch", "generation11_live"
        )

    if (
        restoration["source_path"] != generation5["snapshot_binding"]["path"]
        or restoration["target_path"] != generation11["live_binding"]["path"]
    ):
        raise AttemptMigrationError("semantic_restoration_coordinate_mismatch")
    if _content_metadata(restoration) != _content_metadata(
        generation5["snapshot_binding"]
    ):
        raise AttemptMigrationError("semantic_restoration_metadata_mismatch")
    if _byte_identity(generation11["snapshot_binding"]) != _byte_identity(
        generation11["live_binding"]
    ):
        raise AttemptMigrationError("generation11_snapshot_live_mismatch")
    if snapshot_record_roles is not None:
        snapshot_role, record_role = snapshot_record_roles
        if _byte_identity(artifact_bindings[snapshot_role]) != _byte_identity(
            artifact_bindings[record_role]
        ):
            raise AttemptMigrationError("pending_snapshot_record_mismatch")


def _publish_exclusive(
    repository_root: Path, relative_path: str, data: bytes, mode: int
) -> None:
    parent, name, relative = _open_parent(repository_root, relative_path, create=True)
    temporary = f".{name}.{os.getpid()}.{secrets.token_hex(12)}.tmp"
    descriptor = -1
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(temporary, flags, mode, dir_fd=parent)
        os.fchmod(descriptor, mode)
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(
                temporary,
                name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise AttemptMigrationError("destination_already_exists", relative) from exc
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
    except AttemptMigrationError:
        raise
    except OSError as exc:
        raise AttemptMigrationError("exclusive_publication_failed", relative) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def _committed_binding(
    repository_root: Path, path: str
) -> dict[str, Any]:
    return _content_binding(_require_committed_live(repository_root, path))


def _validate_authority_subject(
    repository_root: Path,
    subject_path: str,
    *,
    governing_plan_binding: Mapping[str, Any],
    migration_plan_binding: Mapping[str, Any],
    expected_manifest_binding: Mapping[str, Any],
    protected_path_bindings: Sequence[Mapping[str, Any]],
    protected_order_insensitive: bool = False,
) -> dict[str, Any]:
    subject_file = _require_committed_live(repository_root, subject_path)
    subject = _json_bytes(subject_file["data"], subject_path)
    if subject_file["data"] != _canonical_json(subject) + b"\n":
        raise AttemptMigrationError("authority_subject_not_canonical")
    _require_keys(subject, AUTHORITY_SUBJECT_KEYS, "authority_subject_keys_mismatch")
    if subject["schema_version"] != "attempt_migration_authority_subject.v1":
        raise AttemptMigrationError("authority_subject_schema_invalid")
    if subject["claims_not_made"] != AUTHORITY_SUBJECT_CLAIMS_NOT_MADE:
        raise AttemptMigrationError("authority_subject_claims_invalid")
    if subject["normalized_subject_sha256"] != _canonical_digest(
        subject, exclude="normalized_subject_sha256"
    ):
        raise AttemptMigrationError("authority_subject_digest_mismatch")
    if subject["governing_plan_binding"] != governing_plan_binding:
        raise AttemptMigrationError("authority_subject_governing_plan_mismatch")
    if subject["migration_plan_binding"] != migration_plan_binding:
        raise AttemptMigrationError("authority_subject_migration_plan_mismatch")
    if subject["expected_paths_manifest_binding"] != expected_manifest_binding:
        raise AttemptMigrationError("authority_subject_manifest_mismatch")
    subject_protected = subject["protected_path_bindings"]
    expected_protected = list(protected_path_bindings)
    if protected_order_insensitive:
        if (
            not isinstance(subject_protected, list)
            or any(not isinstance(row, Mapping) for row in subject_protected)
            or any(not isinstance(row, Mapping) for row in expected_protected)
        ):
            raise AttemptMigrationError("authority_subject_protected_set_mismatch")
        subject_protected = sorted(subject_protected, key=lambda row: row.get("path", ""))
        expected_protected = sorted(
            expected_protected, key=lambda row: row.get("path", "")
        )
    if subject_protected != expected_protected:
        raise AttemptMigrationError("authority_subject_protected_set_mismatch")

    mechanism = _validate_file_binding(subject["mechanism_binding"])
    test = _validate_file_binding(subject["test_binding"])
    evidence = subject["evidence_bindings"]
    if not isinstance(evidence, Mapping) or set(evidence) != AUTHORITY_EVIDENCE_ROLES:
        raise AttemptMigrationError("authority_subject_evidence_roles_invalid")
    reopened_bindings = [mechanism, test]
    for role in sorted(AUTHORITY_EVIDENCE_ROLES):
        reopened_bindings.append(_validate_file_binding(evidence[role]))
    role_bindings = [
        subject["governing_plan_binding"],
        subject["migration_plan_binding"],
        subject["expected_paths_manifest_binding"],
        *subject["protected_path_bindings"],
        *reopened_bindings,
    ]
    paths = [binding["path"] for binding in role_bindings]
    if len(paths) != len(set(paths)):
        raise AttemptMigrationError("authority_subject_binding_path_duplicate")
    for binding in reopened_bindings:
        live = _require_committed_live(repository_root, binding["path"])
        if _public_binding(live) != binding:
            raise AttemptMigrationError(
                "authority_subject_bound_file_mismatch", binding["path"]
            )
    return subject_file


def capture(
    repository_root: Path | str,
    *,
    disposition_path: Path | str,
    source_root: Path | str,
    archive_root: Path | str,
    governing_plan_path: Path | str,
    migration_plan_path: Path | str,
    authority_subject_path: Path | str,
    authority_specification_review_path: Path | str,
    authority_quality_review_path: Path | str,
    source_commit: str,
    source_tree: str,
    expected_paths_manifest_path: Path | str,
    protected_paths: Sequence[Path | str],
    generation5_request_path: Path | str,
    generation5_snapshot_path: Path | str,
    generation11_request_path: Path | str,
    generation11_snapshot_path: Path | str,
    live_ledger_path: Path | str,
    baseline_path: Path | str,
    baseline_specification_review_path: Path | str,
    baseline_quality_review_path: Path | str,
    pending_request_path: Path | str,
    pending_snapshot_path: Path | str,
    pending_record_path: Path | str,
) -> dict[str, Any]:
    """Capture and exclusively publish one closed pre-move disposition."""

    root = _repository_root(repository_root)
    output_path = _relative_path(disposition_path, field="disposition_path")
    source_prefix = _relative_path(source_root, field="source_root")
    archive_prefix = _relative_path(archive_root, field="archive_root")
    if _under(source_prefix, archive_prefix) or _under(archive_prefix, source_prefix):
        raise AttemptMigrationError("source_archive_roots_overlap")
    _reject_output_overlap(output_path, source_prefix, archive_prefix)
    if _read_regular(root, output_path, missing_ok=True) is not None:
        raise AttemptMigrationError("disposition_already_exists", output_path)
    if _scan_regular_files(root, archive_prefix):
        raise AttemptMigrationError("archive_not_empty", archive_prefix)

    governing_path = _relative_path(governing_plan_path)
    correction_path = _relative_path(migration_plan_path)
    authority_spec_path = _relative_path(authority_specification_review_path)
    authority_quality_path = _relative_path(authority_quality_review_path)
    authority_subject_relative = _relative_path(authority_subject_path)
    manifest_path = _relative_path(expected_paths_manifest_path)
    governing_binding = _committed_binding(root, governing_path)
    migration_binding = _committed_binding(root, correction_path)
    manifest_file = _require_committed_live(root, manifest_path)
    expected_paths = _manifest_paths(manifest_file["data"], manifest_path)
    if any(not _under(path, source_prefix) for path in expected_paths):
        raise AttemptMigrationError("expected_path_outside_source_root")

    state = _repository_state(root)
    _validate_status_projection_boundaries(
        state["status_projection"]["rows"], source_prefix
    )
    observed_paths = _status_paths(state["status_projection"]["rows"], source_prefix)
    if observed_paths != expected_paths:
        raise AttemptMigrationError(
            "source_set_mismatch",
            _canonical_json({"expected": expected_paths, "observed": observed_paths}).decode(),
        )

    if not _is_commit_identity(source_commit) or not _is_commit_identity(source_tree):
        raise AttemptMigrationError("source_identity_invalid")
    observed_tree = _git(root, "rev-parse", f"{source_commit}^{{tree}}").decode("ascii").strip()
    if observed_tree != source_tree:
        raise AttemptMigrationError("source_tree_mismatch")
    if not _git_is_ancestor(root, source_commit, state["head"]):
        raise AttemptMigrationError("source_commit_not_ancestor")

    protected: list[dict[str, Any]] = []
    for raw_path in protected_paths:
        path = _relative_path(raw_path, field="protected_path")
        if path in expected_paths or _under(path, archive_prefix):
            raise AttemptMigrationError("protected_path_overlaps_attempt", path)
        snapshot = _read_regular(root, path)
        assert snapshot is not None
        protected.append(_public_binding(snapshot))
    protected.sort(key=lambda row: row["path"])
    if len({row["path"] for row in protected}) != len(protected):
        raise AttemptMigrationError("protected_path_duplicate")
    if [row["path"] for row in protected] != _outside_status_paths(
        state["status_projection"]["rows"], source_prefix
    ):
        raise AttemptMigrationError("protected_status_coverage_mismatch")

    manifest_binding = _content_binding(manifest_file)
    manifest_binding.update(
        {
            "row_count": len(expected_paths),
            "normalized_path_set_sha256": _canonical_digest(expected_paths),
        }
    )
    authority_subject_file = _validate_authority_subject(
        root,
        authority_subject_relative,
        governing_plan_binding=governing_binding,
        migration_plan_binding=migration_binding,
        expected_manifest_binding=manifest_binding,
        protected_path_bindings=protected,
    )
    authority_spec_file, authority_quality_file, _, _ = _validate_review_pair(
        root,
        authority_spec_path,
        authority_quality_path,
        require_committed=True,
        expected_subject_kind="attempt_migration_authority",
        expected_subject_path=authority_subject_relative,
        expected_subject_sha256=authority_subject_file["sha256"],
    )

    rows: list[dict[str, Any]] = []
    for original_path in expected_paths:
        snapshot = _read_regular(root, original_path)
        assert snapshot is not None
        tracked = _is_tracked(root, original_path)
        row = {
            "original_path": original_path,
            "archive_path": f"{archive_prefix}/{original_path}",
            "tracked_state": "modified" if tracked else "untracked",
            "file_type": "regular",
            "lstat_mode": snapshot["lstat_mode"],
            "size": snapshot["size"],
            "sha256": snapshot["sha256"],
        }
        rows.append(row)

    live_path = _relative_path(live_ledger_path)
    modified_rows = [row for row in rows if row["tracked_state"] == "modified"]
    if len(modified_rows) != 1 or modified_rows[0]["original_path"] != live_path:
        raise AttemptMigrationError("tracked_source_set_invalid")

    role_paths = {
        "baseline": _relative_path(baseline_path),
        "baseline_specification_review": _relative_path(
            baseline_specification_review_path
        ),
        "baseline_quality_review": _relative_path(baseline_quality_review_path),
        "pending_request": _relative_path(pending_request_path),
        "pending_snapshot": _relative_path(pending_snapshot_path),
        "pending_record": _relative_path(pending_record_path),
    }
    row_by_path = {row["original_path"]: row for row in rows}
    if any(path not in row_by_path for path in role_paths.values()):
        raise AttemptMigrationError("attempt_artifact_coordinates_invalid")
    artifact_bindings = {
        role: _binding_from_row(row_by_path[path], path_field="original_path")
        for role, path in sorted(role_paths.items())
    }
    baseline_file = _read_regular(root, role_paths["baseline"])
    assert baseline_file is not None
    _validate_review_pair(
        root,
        role_paths["baseline_specification_review"],
        role_paths["baseline_quality_review"],
        require_committed=False,
        expected_subject_kind="implementation_failure_baseline",
        expected_subject_path=role_paths["baseline"],
        expected_subject_sha256=baseline_file["sha256"],
    )

    g5_request_path = _relative_path(generation5_request_path)
    g5_snapshot_path = _relative_path(generation5_snapshot_path)
    g11_request_path = _relative_path(generation11_request_path)
    g11_snapshot_path = _relative_path(generation11_snapshot_path)
    g5_request_file = _require_committed_live(root, g5_request_path)
    g5_snapshot_file = _require_committed_live(root, g5_snapshot_path)
    if g11_request_path not in row_by_path or g11_snapshot_path not in row_by_path:
        raise AttemptMigrationError("generation11_coordinates_invalid")
    g11_request_file = _read_regular(root, g11_request_path)
    g11_snapshot_file = _read_regular(root, g11_snapshot_path)
    live_file = _read_regular(root, live_path)
    assert g11_request_file and g11_snapshot_file and live_file
    committed_live = _committed_bytes(root, live_path, revision=source_commit)
    if g5_snapshot_file["data"] != committed_live:
        raise AttemptMigrationError("restoration_bytes_mismatch")
    source_mode_text = _git(
        root, "ls-tree", source_commit, "--", live_path
    ).decode("ascii", "strict").strip()
    if not source_mode_text:
        raise AttemptMigrationError("restoration_source_missing")
    if not _git_regular_mode_matches_live(
        source_mode_text, g5_snapshot_file["lstat_mode"]
    ):
        raise AttemptMigrationError("restoration_mode_mismatch")

    attempt_binding = {
        "source_commit": source_commit,
        "source_tree": source_tree,
        "source_root": source_prefix,
        "archive_root": archive_prefix,
        "expected_paths_manifest_binding": manifest_binding,
        "artifact_bindings": artifact_bindings,
    }
    ledger_lineage = {
        "generation_5": {
            "generation": 5,
            "request_binding": _public_binding(g5_request_file),
            "snapshot_binding": _public_binding(g5_snapshot_file),
        },
        "generation_11": {
            "generation": 11,
            "request_binding": _binding_from_row(
                row_by_path[g11_request_path], path_field="original_path"
            ),
            "snapshot_binding": _binding_from_row(
                row_by_path[g11_snapshot_path], path_field="original_path"
            ),
            "live_binding": _binding_from_row(
                row_by_path[live_path], path_field="original_path"
            ),
        },
        "restoration_binding": {
            "source_path": g5_snapshot_path,
            "target_path": live_path,
            "source_commit": source_commit,
            "source_tree": source_tree,
            "file_type": "regular",
            "lstat_mode": g5_snapshot_file["lstat_mode"],
            "size": g5_snapshot_file["size"],
            "sha256": g5_snapshot_file["sha256"],
        },
    }
    _validate_semantic_coordinates(
        rows=rows,
        artifact_bindings=artifact_bindings,
        generation5=ledger_lineage["generation_5"],
        generation11=ledger_lineage["generation_11"],
        restoration=ledger_lineage["restoration_binding"],
    )

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "disposition": DISPOSITION,
        "governing_plan_binding": governing_binding,
        "migration_plan_binding": migration_binding,
        "authority_review_bindings": {
            "specification": _content_binding(authority_spec_file),
            "code_quality": _content_binding(authority_quality_file),
        },
        "attempt_binding": attempt_binding,
        "pre_move_repository_state": state,
        "protected_path_bindings": protected,
        "ledger_lineage": ledger_lineage,
        "attempt_rows": rows,
        "attempt_path_count": len(rows),
        "attempt_path_set_sha256": _canonical_digest(expected_paths),
        "archive_path_set_sha256": _canonical_digest(
            [row["archive_path"] for row in rows]
        ),
        "normalized_row_set_sha256": _canonical_digest(rows),
        "normalized_disposition_sha256": "",
        "claims_not_made": CLAIMS_NOT_MADE,
    }
    record["normalized_disposition_sha256"] = _canonical_digest(
        record, exclude="normalized_disposition_sha256"
    )
    _publish_exclusive(root, output_path, _canonical_json(record) + b"\n", 0o644)
    return validate(root, output_path)


def _classify_invalidated_adopted_outputs(
    root: Path,
    *,
    source_root: str,
    incident_path: str,
    disposition_path: str,
) -> tuple[
    str,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """Recognize only A/A, exact I/A, or exact I/D publication prefixes."""

    current_state = _repository_state(root)
    _validate_repository_state_structure(current_state, source_root=source_root)
    status_rows = current_state["status_projection"]["rows"]
    _validate_status_projection_boundaries(status_rows, source_root)
    snapshots = {
        incident_path: _read_regular(root, incident_path, missing_ok=True),
        disposition_path: _read_regular(root, disposition_path, missing_ok=True),
    }
    output_rows: dict[str, dict[str, Any]] = {}
    for path, snapshot in snapshots.items():
        touching = [
            row
            for row in status_rows
            if path in {row["path"], row.get("source_path")}
        ]
        if snapshot is None:
            if touching:
                raise AttemptMigrationError("capture_output_state_invalid", path)
            continue
        if (
            snapshot["lstat_mode"] != 0o644
            or touching
            != [{"path": path, "source_path": None, "status": "??"}]
        ):
            raise AttemptMigrationError("capture_output_state_invalid", path)
        output_rows[path] = touching[0]

    incident_snapshot = snapshots[incident_path]
    disposition_snapshot = snapshots[disposition_path]
    if incident_snapshot is None:
        if disposition_snapshot is not None:
            raise AttemptMigrationError("capture_output_prefix_invalid")
        return "A/A", current_state, current_state, None, None, None

    incident = _json_bytes(incident_snapshot["data"], incident_path)
    if incident_snapshot["data"] != _canonical_json(incident) + b"\n":
        raise AttemptMigrationError("capture_incident_not_canonical")
    incident = _validate_incident_structure(incident)
    removed = set(output_rows)
    stripped_rows = [row for row in status_rows if row["path"] not in removed]
    stripped_state = dict(current_state)
    stripped_state["status_projection"] = {
        "rows": stripped_rows,
        "row_count": len(stripped_rows),
        "normalized_rows_sha256": _canonical_digest(stripped_rows),
    }
    if stripped_state != incident["pre_move_repository_state"]:
        raise AttemptMigrationError("capture_frozen_repository_state_mismatch")
    return (
        "I/D" if disposition_snapshot is not None else "I/A",
        current_state,
        incident["pre_move_repository_state"],
        incident_snapshot,
        disposition_snapshot,
        incident,
    )


def _validate_owner_review_role_cross_links(
    owner_attestation: Mapping[str, Any],
    artifact_bindings: Mapping[str, Mapping[str, Any]],
) -> None:
    role_fields = {
        "baseline_specification_review": "specification_review_binding",
        "baseline_quality_review": "quality_review_binding",
    }
    for role, field in role_fields.items():
        owner_binding = owner_attestation.get(field)
        artifact = artifact_bindings[role]
        if (
            not isinstance(owner_binding, Mapping)
            or owner_binding.get("logical_path") != artifact["path"]
            or owner_binding.get("sha256") != artifact["sha256"]
        ):
            raise AttemptMigrationError("v2_owner_review_binding_mismatch", role)


def _build_invalidated_adopted_disposition(
    root: Path,
    *,
    incident_path: str,
    disposition_path: str,
    incident: Mapping[str, Any],
    archive_root: Path | str,
    authority_subject_path: Path | str,
    authority_specification_review_path: Path | str,
    authority_quality_review_path: Path | str,
    restoration_commit: str,
    restoration_tree: str,
    protected_paths: Sequence[Path | str],
    generation5_request_path: Path | str,
    generation5_snapshot_path: Path | str,
    generation11_request_path: Path | str,
    generation11_snapshot_path: Path | str,
    live_ledger_path: Path | str,
    baseline_path: Path | str,
    baseline_specification_review_path: Path | str,
    baseline_quality_review_path: Path | str,
    workspace_baseline_path: Path | str,
    attestation_request_path: Path | str,
    attestation_snapshot_path: Path | str,
    attestation_record_path: Path | str,
) -> dict[str, Any]:
    source_prefix = incident["source_root"]
    archive_prefix = _relative_path(archive_root, field="archive_root")
    state = incident["pre_move_repository_state"]
    expected_paths = [row["path"] for row in incident["attempt_rows"]]
    governing_binding = _committed_binding(
        root, incident["governing_plan_binding"]["path"]
    )
    migration_binding = _committed_binding(
        root, incident["migration_plan_binding"]["path"]
    )
    if (
        governing_binding != incident["governing_plan_binding"]
        or migration_binding != incident["migration_plan_binding"]
    ):
        raise AttemptMigrationError("v2_incident_plan_binding_mismatch")
    manifest_binding = incident["expected_paths_manifest_binding"]
    manifest_file = _require_committed_live(root, manifest_binding["path"])
    if _incident_manifest_binding(
        manifest_file,
        _manifest_paths(manifest_file["data"], manifest_binding["path"]),
    ) != manifest_binding:
        raise AttemptMigrationError("expected_manifest_binding_mismatch")

    protected: list[dict[str, Any]] = []
    for raw_path in protected_paths:
        path = _relative_path(raw_path, field="protected_path")
        if (
            path in expected_paths
            or _under(path, archive_prefix)
            or path in {incident_path, disposition_path}
        ):
            raise AttemptMigrationError("protected_path_overlaps_attempt", path)
        snapshot = _read_regular(root, path)
        assert snapshot is not None
        protected.append(_public_binding(snapshot))
    authority_protected = list(protected)
    protected.sort(key=lambda row: row["path"])
    if len({row["path"] for row in protected}) != len(protected):
        raise AttemptMigrationError("protected_path_duplicate")
    if [row["path"] for row in protected] != _outside_status_paths(
        state["status_projection"]["rows"], source_prefix
    ):
        raise AttemptMigrationError("protected_status_coverage_mismatch")

    authority_subject_relative = _relative_path(authority_subject_path)
    authority_subject_file = _validate_authority_subject(
        root,
        authority_subject_relative,
        governing_plan_binding=governing_binding,
        migration_plan_binding=migration_binding,
        expected_manifest_binding=manifest_binding,
        protected_path_bindings=authority_protected,
    )
    authority_spec_file, authority_quality_file, _, _ = _validate_review_pair(
        root,
        _relative_path(authority_specification_review_path),
        _relative_path(authority_quality_review_path),
        require_committed=True,
        expected_subject_kind="attempt_migration_authority",
        expected_subject_path=authority_subject_relative,
        expected_subject_sha256=authority_subject_file["sha256"],
    )

    rows = [
        {
            "original_path": row["path"],
            "archive_path": f"{archive_prefix}/{row['path']}",
            "tracked_state": row["tracked_state"],
            "file_type": row["file_type"],
            "lstat_mode": row["lstat_mode"],
            "size": row["size"],
            "sha256": row["sha256"],
        }
        for row in incident["attempt_rows"]
    ]
    row_by_path = {row["original_path"]: row for row in rows}
    live_path = _relative_path(live_ledger_path)
    modified_rows = [row for row in rows if row["tracked_state"] == "modified"]
    if len(modified_rows) != 1 or modified_rows[0]["original_path"] != live_path:
        raise AttemptMigrationError("tracked_source_set_invalid")

    role_paths = {
        "baseline": _relative_path(baseline_path),
        "baseline_specification_review": _relative_path(
            baseline_specification_review_path
        ),
        "baseline_quality_review": _relative_path(
            baseline_quality_review_path
        ),
        "workspace_baseline": _relative_path(workspace_baseline_path),
        "attestation_request": _relative_path(attestation_request_path),
        "attestation_snapshot": _relative_path(attestation_snapshot_path),
        "attestation_record": _relative_path(attestation_record_path),
    }
    if any(path not in row_by_path for path in role_paths.values()):
        raise AttemptMigrationError("attempt_artifact_coordinates_invalid")
    artifact_bindings = {
        role: _binding_from_row(row_by_path[path], path_field="original_path")
        for role, path in sorted(role_paths.items())
    }
    baseline_file = _read_regular(root, role_paths["baseline"])
    assert baseline_file is not None
    _validate_review_pair(
        root,
        role_paths["baseline_specification_review"],
        role_paths["baseline_quality_review"],
        require_committed=False,
        expected_subject_kind="implementation_failure_baseline",
        expected_subject_path=role_paths["baseline"],
        expected_subject_sha256=baseline_file["sha256"],
    )
    owner_snapshot = _read_regular(root, role_paths["attestation_record"])
    assert owner_snapshot is not None
    owner_attestation = _json_bytes(
        owner_snapshot["data"], role_paths["attestation_record"]
    )
    _validate_owner_review_role_cross_links(owner_attestation, artifact_bindings)

    g5_request_path = _relative_path(generation5_request_path)
    g5_snapshot_path = _relative_path(generation5_snapshot_path)
    g11_request_path = _relative_path(generation11_request_path)
    g11_snapshot_path = _relative_path(generation11_snapshot_path)
    g5_request_file = _require_committed_live(root, g5_request_path)
    g5_snapshot_file = _require_committed_live(root, g5_snapshot_path)
    if g11_request_path not in row_by_path or g11_snapshot_path not in row_by_path:
        raise AttemptMigrationError("generation11_coordinates_invalid")
    g11_request_file = _read_regular(root, g11_request_path)
    g11_snapshot_file = _read_regular(root, g11_snapshot_path)
    live_file = _read_regular(root, live_path)
    assert g11_request_file and g11_snapshot_file and live_file
    if not _is_commit_identity(restoration_commit) or not _is_commit_identity(
        restoration_tree
    ):
        raise AttemptMigrationError("source_identity_invalid")
    observed_tree = _git(
        root, "rev-parse", f"{restoration_commit}^{{tree}}"
    ).decode("ascii").strip()
    if observed_tree != restoration_tree:
        raise AttemptMigrationError("source_tree_mismatch")
    if not _git_is_ancestor(root, restoration_commit, state["head"]):
        raise AttemptMigrationError("source_commit_not_ancestor")
    committed_live = _committed_bytes(
        root, live_path, revision=restoration_commit
    )
    if g5_snapshot_file["data"] != committed_live:
        raise AttemptMigrationError("restoration_bytes_mismatch")
    source_mode_text = _git(
        root, "ls-tree", restoration_commit, "--", live_path
    ).decode("ascii", "strict").strip()
    if not source_mode_text or not _git_regular_mode_matches_live(
        source_mode_text, g5_snapshot_file["lstat_mode"]
    ):
        raise AttemptMigrationError("restoration_mode_mismatch")

    attempt_binding = {
        "source_commit": restoration_commit,
        "source_tree": restoration_tree,
        "source_root": source_prefix,
        "archive_root": archive_prefix,
        "expected_paths_manifest_binding": manifest_binding,
        "artifact_bindings": artifact_bindings,
    }
    ledger_lineage = {
        "generation_5": {
            "generation": 5,
            "request_binding": _public_binding(g5_request_file),
            "snapshot_binding": _public_binding(g5_snapshot_file),
        },
        "generation_11": {
            "generation": 11,
            "request_binding": _binding_from_row(
                row_by_path[g11_request_path], path_field="original_path"
            ),
            "snapshot_binding": _binding_from_row(
                row_by_path[g11_snapshot_path], path_field="original_path"
            ),
            "live_binding": _binding_from_row(
                row_by_path[live_path], path_field="original_path"
            ),
        },
        "restoration_binding": {
            "source_path": g5_snapshot_path,
            "target_path": live_path,
            "source_commit": restoration_commit,
            "source_tree": restoration_tree,
            "file_type": "regular",
            "lstat_mode": g5_snapshot_file["lstat_mode"],
            "size": g5_snapshot_file["size"],
            "sha256": g5_snapshot_file["sha256"],
        },
    }
    _validate_semantic_coordinates(
        rows=rows,
        artifact_bindings=artifact_bindings,
        generation5=ledger_lineage["generation_5"],
        generation11=ledger_lineage["generation_11"],
        restoration=ledger_lineage["restoration_binding"],
        artifact_roles=V2_ARTIFACT_ROLES,
        snapshot_record_roles=None,
    )
    incident_data = _canonical_json(incident) + b"\n"
    incident_binding = {
        "path": incident_path,
        "size": len(incident_data),
        "sha256": _bytes_digest(incident_data),
    }
    record: dict[str, Any] = {
        "schema_version": V2_SCHEMA_VERSION,
        "disposition": V2_DISPOSITION,
        "governing_plan_binding": governing_binding,
        "migration_plan_binding": migration_binding,
        "authority_review_bindings": {
            "specification": _content_binding(authority_spec_file),
            "code_quality": _content_binding(authority_quality_file),
        },
        "attempt_binding": attempt_binding,
        "attempt_lifecycle": {
            "adoption_state": "owner_adopted",
            "repository_commit_state": "uncommitted",
            "invalidation_reason": "workspace_baseline_predecessor_mismatch",
            "incident_binding": incident_binding,
            "workspace_baseline_role": "workspace_baseline",
            "owner_attestation_role": "attestation_record",
            "adoption_transfer": "forbidden",
        },
        "pre_move_repository_state": state,
        "protected_path_bindings": protected,
        "ledger_lineage": ledger_lineage,
        "attempt_rows": rows,
        "attempt_path_count": len(rows),
        "attempt_path_set_sha256": _canonical_digest(expected_paths),
        "archive_path_set_sha256": _canonical_digest(
            [row["archive_path"] for row in rows]
        ),
        "normalized_row_set_sha256": _canonical_digest(rows),
        "normalized_disposition_sha256": "",
        "claims_not_made": V2_CLAIMS_NOT_MADE,
    }
    record["normalized_disposition_sha256"] = _canonical_digest(
        record, exclude="normalized_disposition_sha256"
    )
    validated = _validate_disposition_v2_structure(record)
    _validate_v2_attestation_transition(root, validated)
    return validated


def capture_invalidated_adopted(
    repository_root: Path | str,
    *,
    incident_path: Path | str,
    disposition_path: Path | str,
    source_root: Path | str,
    archive_root: Path | str,
    governing_plan_path: Path | str,
    migration_plan_path: Path | str,
    authority_subject_path: Path | str,
    authority_specification_review_path: Path | str,
    authority_quality_review_path: Path | str,
    intended_predecessor_head: str,
    restoration_commit: str,
    restoration_tree: str,
    expected_paths_manifest_path: Path | str,
    protected_paths: Sequence[Path | str],
    generation5_request_path: Path | str,
    generation5_snapshot_path: Path | str,
    generation11_request_path: Path | str,
    generation11_snapshot_path: Path | str,
    live_ledger_path: Path | str,
    baseline_path: Path | str,
    baseline_specification_review_path: Path | str,
    baseline_quality_review_path: Path | str,
    workspace_baseline_path: Path | str,
    attestation_request_path: Path | str,
    attestation_snapshot_path: Path | str,
    attestation_record_path: Path | str,
) -> dict[str, dict[str, Any]]:
    """Publish one incident/disposition pair through its exact prefix automaton."""

    root = _repository_root(repository_root)
    incident_relative = _relative_path(incident_path, field="incident_path")
    disposition_relative = _relative_path(
        disposition_path, field="disposition_path"
    )
    source_prefix = _relative_path(source_root, field="source_root")
    archive_prefix = _relative_path(archive_root, field="archive_root")
    if incident_relative == disposition_relative:
        raise AttemptMigrationError("capture_output_paths_alias")
    if _under(incident_relative, disposition_relative) or _under(
        disposition_relative, incident_relative
    ):
        raise AttemptMigrationError("capture_output_paths_overlap")
    if _under(source_prefix, archive_prefix) or _under(
        archive_prefix, source_prefix
    ):
        raise AttemptMigrationError("source_archive_roots_overlap")
    _reject_output_overlap(incident_relative, source_prefix, archive_prefix)
    _reject_output_overlap(disposition_relative, source_prefix, archive_prefix)

    operand_paths = {
        _relative_path(path)
        for path in (
            governing_plan_path,
            migration_plan_path,
            authority_subject_path,
            authority_specification_review_path,
            authority_quality_review_path,
            expected_paths_manifest_path,
            generation5_request_path,
            generation5_snapshot_path,
            generation11_request_path,
            generation11_snapshot_path,
            live_ledger_path,
            baseline_path,
            baseline_specification_review_path,
            baseline_quality_review_path,
            workspace_baseline_path,
            attestation_request_path,
            attestation_snapshot_path,
            attestation_record_path,
        )
    }
    protected_relatives = [
        _relative_path(path, field="protected_path") for path in protected_paths
    ]
    for output in (incident_relative, disposition_relative):
        if output in operand_paths or output in protected_relatives:
            raise AttemptMigrationError("capture_output_overlaps_operand", output)
    if _scan_regular_files(root, archive_prefix):
        raise AttemptMigrationError("archive_not_empty", archive_prefix)

    prefix, _current_state, frozen_state, incident_snapshot, disposition_snapshot, _ = (
        _classify_invalidated_adopted_outputs(
            root,
            source_root=source_prefix,
            incident_path=incident_relative,
            disposition_path=disposition_relative,
        )
    )
    incident = _build_attempt_migration_incident(
        root,
        governing_plan_path=governing_plan_path,
        migration_plan_path=migration_plan_path,
        workspace_baseline_path=workspace_baseline_path,
        owner_attestation_path=attestation_record_path,
        pending_attestation_snapshot_path=attestation_snapshot_path,
        known_failure_baseline_path=baseline_path,
        expected_paths_manifest_path=expected_paths_manifest_path,
        source_root=source_prefix,
        intended_predecessor_head=intended_predecessor_head,
        pre_move_repository_state=frozen_state,
    )
    incident_data = _canonical_json(incident) + b"\n"
    if incident_snapshot is not None and (
        incident_snapshot["data"] != incident_data
        or incident_snapshot["lstat_mode"] != 0o644
    ):
        raise AttemptMigrationError("capture_incident_conflict", incident_relative)

    disposition = _build_invalidated_adopted_disposition(
        root,
        incident_path=incident_relative,
        disposition_path=disposition_relative,
        incident=incident,
        archive_root=archive_prefix,
        authority_subject_path=authority_subject_path,
        authority_specification_review_path=authority_specification_review_path,
        authority_quality_review_path=authority_quality_review_path,
        restoration_commit=restoration_commit,
        restoration_tree=restoration_tree,
        protected_paths=protected_relatives,
        generation5_request_path=generation5_request_path,
        generation5_snapshot_path=generation5_snapshot_path,
        generation11_request_path=generation11_request_path,
        generation11_snapshot_path=generation11_snapshot_path,
        live_ledger_path=live_ledger_path,
        baseline_path=baseline_path,
        baseline_specification_review_path=baseline_specification_review_path,
        baseline_quality_review_path=baseline_quality_review_path,
        workspace_baseline_path=workspace_baseline_path,
        attestation_request_path=attestation_request_path,
        attestation_snapshot_path=attestation_snapshot_path,
        attestation_record_path=attestation_record_path,
    )
    disposition_data = _canonical_json(disposition) + b"\n"
    if disposition_snapshot is not None and (
        disposition_snapshot["data"] != disposition_data
        or disposition_snapshot["lstat_mode"] != 0o644
    ):
        raise AttemptMigrationError(
            "capture_disposition_conflict", disposition_relative
        )

    if prefix == "A/A":
        _publish_exclusive(root, incident_relative, incident_data, 0o644)
        _publish_exclusive(root, disposition_relative, disposition_data, 0o644)
    elif prefix == "I/A":
        _publish_exclusive(root, disposition_relative, disposition_data, 0o644)
    elif prefix != "I/D":
        raise AttemptMigrationError("capture_output_prefix_invalid")

    validated = validate(root, disposition_relative)
    if validated != disposition:
        raise AttemptMigrationError("capture_disposition_replay_mismatch")
    return {"incident": incident, "disposition": disposition}


def _require_keys(value: Any, expected: set[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise AttemptMigrationError(code)
    return value


def _validate_file_binding(value: Any, *, full: bool = True) -> Mapping[str, Any]:
    keys = {"path", "file_type", "lstat_mode", "size", "sha256"} if full else {"path", "size", "sha256"}
    binding = _require_keys(value, keys, "file_binding_keys_mismatch")
    _relative_path(binding["path"])
    if full and (
        binding["file_type"] != "regular"
        or type(binding["lstat_mode"]) is not int
        or not 0 <= binding["lstat_mode"] <= 0o7777
    ):
        raise AttemptMigrationError("file_binding_metadata_invalid")
    if type(binding["size"]) is not int or binding["size"] < 0:
        raise AttemptMigrationError("file_binding_size_invalid")
    if not _is_sha256(binding["sha256"]):
        raise AttemptMigrationError("file_binding_digest_invalid")
    return binding


def _same_content(snapshot: Mapping[str, Any] | None, binding: Mapping[str, Any]) -> bool:
    return snapshot is not None and all(
        snapshot.get(key) == binding.get(key)
        for key in ("file_type", "lstat_mode", "size", "sha256")
    )


def _resolve_attempt_row_snapshot(
    root: Path, row: Mapping[str, Any]
) -> dict[str, Any]:
    source = _read_regular(root, row["original_path"], missing_ok=True)
    if _same_content(source, _binding_from_row(row, path_field="original_path")):
        assert source is not None
        return source
    archive = _read_regular(root, row["archive_path"], missing_ok=True)
    if _same_content(archive, _binding_from_row(row, path_field="archive_path")):
        assert archive is not None
        resolved = dict(archive)
        resolved["path"] = row["original_path"]
        return resolved
    raise AttemptMigrationError("attempt_review_binding_unavailable", row["original_path"])


def _scan_regular_files(repository_root: Path, prefix: str) -> list[str]:
    parts = PurePosixPath(_relative_path(prefix)).parts
    flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(repository_root, flags)
        for component in parts:
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                return []
            os.close(descriptor)
            descriptor = child

        result: list[str] = []

        def walk(directory_fd: int, relative: str) -> None:
            try:
                names = sorted(os.listdir(directory_fd))
            except OSError as exc:
                raise AttemptMigrationError("archive_tree_unreadable", relative) from exc
            for name in names:
                logical = f"{relative}/{name}"
                metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISDIR(metadata.st_mode):
                    child_fd = os.open(name, flags, dir_fd=directory_fd)
                    try:
                        walk(child_fd, logical)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(metadata.st_mode):
                    result.append(logical)
                else:
                    raise AttemptMigrationError("archive_entry_not_regular", logical)

        walk(descriptor, prefix)
        return result
    except AttemptMigrationError:
        raise
    except OSError as exc:
        raise AttemptMigrationError("archive_tree_invalid", prefix) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _validate_disposition_v1_structure(
    record: Any,
    *,
    artifact_roles: Sequence[str] = ARTIFACT_ROLES,
    snapshot_record_roles: tuple[str, str] | None = (
        "pending_snapshot",
        "pending_record",
    ),
) -> dict[str, Any]:
    disposition = dict(_require_keys(record, TOP_LEVEL_KEYS, "disposition_keys_mismatch"))
    if disposition["schema_version"] != SCHEMA_VERSION:
        raise AttemptMigrationError("disposition_schema_invalid")
    if disposition["disposition"] != DISPOSITION:
        raise AttemptMigrationError("disposition_value_invalid")
    if disposition["claims_not_made"] != CLAIMS_NOT_MADE:
        raise AttemptMigrationError("disposition_claims_invalid")
    if disposition["normalized_disposition_sha256"] != _canonical_digest(
        disposition, exclude="normalized_disposition_sha256"
    ):
        raise AttemptMigrationError("normalized_disposition_digest_mismatch")
    _validate_file_binding(disposition["governing_plan_binding"], full=False)
    _validate_file_binding(disposition["migration_plan_binding"], full=False)
    reviews = _require_keys(
        disposition["authority_review_bindings"],
        {"specification", "code_quality"},
        "authority_review_bindings_invalid",
    )
    _validate_file_binding(reviews["specification"], full=False)
    _validate_file_binding(reviews["code_quality"], full=False)

    attempt = _require_keys(
        disposition["attempt_binding"],
        {
            "source_commit",
            "source_tree",
            "source_root",
            "archive_root",
            "expected_paths_manifest_binding",
            "artifact_bindings",
        },
        "attempt_binding_keys_mismatch",
    )
    if not _is_commit_identity(attempt["source_commit"]) or not _is_commit_identity(
        attempt["source_tree"]
    ):
        raise AttemptMigrationError("attempt_source_identity_invalid")
    source_root = _relative_path(attempt["source_root"])
    archive_root = _relative_path(attempt["archive_root"])
    if _under(source_root, archive_root) or _under(archive_root, source_root):
        raise AttemptMigrationError("source_archive_roots_overlap")
    manifest = _require_keys(
        attempt["expected_paths_manifest_binding"],
        {"path", "size", "sha256", "row_count", "normalized_path_set_sha256"},
        "expected_manifest_binding_invalid",
    )
    _validate_file_binding(
        {key: manifest[key] for key in ("path", "size", "sha256")}, full=False
    )
    if type(manifest["row_count"]) is not int or manifest["row_count"] < 1:
        raise AttemptMigrationError("expected_manifest_count_invalid")
    if not _is_sha256(manifest["normalized_path_set_sha256"]):
        raise AttemptMigrationError("expected_manifest_digest_invalid")
    artifacts = _require_keys(
        attempt["artifact_bindings"],
        set(artifact_roles),
        "attempt_artifact_bindings_invalid",
    )
    for binding in artifacts.values():
        _validate_file_binding(binding)

    rows = disposition["attempt_rows"]
    if not isinstance(rows, list) or not rows:
        raise AttemptMigrationError("attempt_rows_invalid")
    for row in rows:
        _require_keys(row, ROW_KEYS, "attempt_row_keys_mismatch")
        _validate_file_binding(_binding_from_row(row, path_field="original_path"))
        _relative_path(row["archive_path"])
        if not isinstance(row["tracked_state"], str) or row[
            "tracked_state"
        ] not in {"modified", "untracked"}:
            raise AttemptMigrationError("attempt_row_tracked_state_invalid")
    originals = [row["original_path"] for row in rows]
    archives = [row["archive_path"] for row in rows]
    if originals != sorted(originals) or len(originals) != len(set(originals)):
        raise AttemptMigrationError("attempt_row_order_invalid")
    if len(archives) != len(set(archives)) or any(
        archive != f"{archive_root}/{original}"
        for original, archive in zip(originals, archives, strict=True)
    ):
        raise AttemptMigrationError("attempt_archive_projection_invalid")
    if any(not _under(path, source_root) for path in originals):
        raise AttemptMigrationError("attempt_source_projection_invalid")
    if (
        type(disposition["attempt_path_count"]) is not int
        or disposition["attempt_path_count"] != len(rows)
        or manifest["row_count"] != len(rows)
    ):
        raise AttemptMigrationError("attempt_path_count_mismatch")
    expected_path_digest = _canonical_digest(originals)
    if (
        disposition["attempt_path_set_sha256"] != expected_path_digest
        or manifest["normalized_path_set_sha256"] != expected_path_digest
    ):
        raise AttemptMigrationError("attempt_path_set_digest_mismatch")
    if disposition["archive_path_set_sha256"] != _canonical_digest(archives):
        raise AttemptMigrationError("archive_path_set_digest_mismatch")
    if disposition["normalized_row_set_sha256"] != _canonical_digest(rows):
        raise AttemptMigrationError("attempt_row_set_digest_mismatch")
    if len([row for row in rows if row["tracked_state"] == "modified"]) != 1:
        raise AttemptMigrationError("tracked_source_set_invalid")

    protected = disposition["protected_path_bindings"]
    if not isinstance(protected, list):
        raise AttemptMigrationError("protected_bindings_invalid")
    for binding in protected:
        _validate_file_binding(binding)
    if [row["path"] for row in protected] != sorted(row["path"] for row in protected):
        raise AttemptMigrationError("protected_binding_order_invalid")

    state = _require_keys(
        disposition["pre_move_repository_state"],
        {"head", "tree", "index_sha256", "status_projection"},
        "repository_state_keys_mismatch",
    )
    if (
        not _is_commit_identity(state["head"])
        or not _is_commit_identity(state["tree"])
        or not _is_sha256(state["index_sha256"])
    ):
        raise AttemptMigrationError("repository_state_identity_invalid")
    projection = _require_keys(
        state["status_projection"],
        {"rows", "row_count", "normalized_rows_sha256"},
        "status_projection_keys_mismatch",
    )
    if (
        not isinstance(projection["rows"], list)
        or type(projection["row_count"]) is not int
        or projection["row_count"] != len(projection["rows"])
        or projection["normalized_rows_sha256"]
        != _canonical_digest(projection["rows"])
    ):
        raise AttemptMigrationError("status_projection_invalid")
    status_rows = projection["rows"]
    for row in status_rows:
        if not isinstance(row, Mapping) or set(row) != {
            "path",
            "source_path",
            "status",
        }:
            raise AttemptMigrationError("status_projection_row_invalid")
        try:
            _relative_path(row["path"], field="status.path")
            if row["source_path"] is not None:
                _relative_path(row["source_path"], field="status.source_path")
        except (AttemptMigrationError, TypeError) as exc:
            raise AttemptMigrationError("status_projection_row_invalid") from exc
        if (
            not isinstance(row["status"], str)
            or GIT_STATUS_RE.fullmatch(row["status"]) is None
            or row["status"] == "  "
        ):
            raise AttemptMigrationError("status_projection_row_invalid")
        is_rename = row["status"][0] in "RC" or row["status"][1] in "RC"
        if is_rename != (row["source_path"] is not None):
            raise AttemptMigrationError("status_projection_row_invalid")
    _validate_status_projection_boundaries(status_rows, source_root)
    if status_rows != sorted(
        status_rows,
        key=lambda row: (row["path"], row["source_path"] or "", row["status"]),
    ):
        raise AttemptMigrationError("status_projection_row_order_invalid")
    status_identities = [
        (row["path"], row["source_path"], row["status"]) for row in status_rows
    ]
    if len(status_identities) != len(set(status_identities)):
        raise AttemptMigrationError("status_projection_row_duplicate")
    if _status_paths(status_rows, source_root) != originals:
        raise AttemptMigrationError("source_status_coverage_mismatch")
    if [row["path"] for row in protected] != _outside_status_paths(
        projection["rows"], source_root
    ):
        raise AttemptMigrationError("protected_status_coverage_mismatch")

    lineage = _require_keys(
        disposition["ledger_lineage"],
        {"generation_5", "generation_11", "restoration_binding"},
        "ledger_lineage_keys_mismatch",
    )
    g5 = _require_keys(
        lineage["generation_5"],
        {"generation", "request_binding", "snapshot_binding"},
        "generation5_binding_invalid",
    )
    if type(g5["generation"]) is not int or g5["generation"] != 5:
        raise AttemptMigrationError("generation5_value_invalid")
    _validate_file_binding(g5["request_binding"])
    _validate_file_binding(g5["snapshot_binding"])
    g11 = _require_keys(
        lineage["generation_11"],
        {"generation", "request_binding", "snapshot_binding", "live_binding"},
        "generation11_binding_invalid",
    )
    if type(g11["generation"]) is not int or g11["generation"] != 11:
        raise AttemptMigrationError("generation11_value_invalid")
    for binding in (g11["request_binding"], g11["snapshot_binding"], g11["live_binding"]):
        _validate_file_binding(binding)
    restoration = _require_keys(
        lineage["restoration_binding"],
        {
            "source_path",
            "target_path",
            "source_commit",
            "source_tree",
            "file_type",
            "lstat_mode",
            "size",
            "sha256",
        },
        "restoration_binding_invalid",
    )
    _validate_file_binding(
        {
            "path": restoration["target_path"],
            "file_type": restoration["file_type"],
            "lstat_mode": restoration["lstat_mode"],
            "size": restoration["size"],
            "sha256": restoration["sha256"],
        }
    )
    _relative_path(restoration["source_path"])
    _validate_semantic_coordinates(
        rows=rows,
        artifact_bindings=artifacts,
        generation5=g5,
        generation11=g11,
        restoration=restoration,
        artifact_roles=artifact_roles,
        snapshot_record_roles=snapshot_record_roles,
    )
    if (
        restoration["source_commit"] != attempt["source_commit"]
        or restoration["source_tree"] != attempt["source_tree"]
    ):
        raise AttemptMigrationError("restoration_coordinates_mismatch")
    return disposition


def _validate_disposition_v2_structure(record: Any) -> dict[str, Any]:
    disposition = dict(
        _require_keys(record, V2_TOP_LEVEL_KEYS, "disposition_keys_mismatch")
    )
    if disposition["schema_version"] != V2_SCHEMA_VERSION:
        raise AttemptMigrationError("disposition_schema_invalid")
    if disposition["disposition"] != V2_DISPOSITION:
        raise AttemptMigrationError("disposition_value_invalid")
    if disposition["claims_not_made"] != V2_CLAIMS_NOT_MADE:
        raise AttemptMigrationError("disposition_claims_invalid")
    if disposition["normalized_disposition_sha256"] != _canonical_digest(
        disposition, exclude="normalized_disposition_sha256"
    ):
        raise AttemptMigrationError("normalized_disposition_digest_mismatch")

    lifecycle = _require_keys(
        disposition["attempt_lifecycle"],
        V2_ATTEMPT_LIFECYCLE_KEYS,
        "attempt_lifecycle_invalid",
    )
    if (
        lifecycle["adoption_state"] != "owner_adopted"
        or lifecycle["repository_commit_state"] != "uncommitted"
        or lifecycle["invalidation_reason"]
        != "workspace_baseline_predecessor_mismatch"
        or lifecycle["workspace_baseline_role"] != "workspace_baseline"
        or lifecycle["owner_attestation_role"] != "attestation_record"
        or lifecycle["adoption_transfer"] != "forbidden"
    ):
        raise AttemptMigrationError("attempt_lifecycle_invalid")
    _validate_file_binding(lifecycle["incident_binding"], full=False)

    common = {
        key: value
        for key, value in disposition.items()
        if key != "attempt_lifecycle"
    }
    common.update(
        {
            "schema_version": SCHEMA_VERSION,
            "disposition": DISPOSITION,
            "claims_not_made": CLAIMS_NOT_MADE,
            "normalized_disposition_sha256": "",
        }
    )
    common["normalized_disposition_sha256"] = _canonical_digest(
        common, exclude="normalized_disposition_sha256"
    )
    _validate_disposition_v1_structure(
        common,
        artifact_roles=V2_ARTIFACT_ROLES,
        snapshot_record_roles=None,
    )
    return disposition


def _validate_disposition_structure(record: Any) -> dict[str, Any]:
    """Dispatch a closed disposition to exactly one versioned validator."""

    if isinstance(record, Mapping) and record.get("schema_version") == V2_SCHEMA_VERSION:
        return _validate_disposition_v2_structure(record)
    if isinstance(record, Mapping) and "schema_version" in record and record.get(
        "schema_version"
    ) != SCHEMA_VERSION:
        raise AttemptMigrationError("disposition_schema_invalid")
    return _validate_disposition_v1_structure(record)


def _validate_attempt_replay_states(
    root: Path, record: Mapping[str, Any]
) -> None:
    restoration = record["ledger_lineage"]["restoration_binding"]
    restoration_binding = {
        "path": restoration["target_path"],
        "file_type": restoration["file_type"],
        "lstat_mode": restoration["lstat_mode"],
        "size": restoration["size"],
        "sha256": restoration["sha256"],
    }
    for row in record["attempt_rows"]:
        pre_binding = _binding_from_row(row, path_field="original_path")
        archive_binding = _binding_from_row(row, path_field="archive_path")
        source = _read_regular(root, row["original_path"], missing_ok=True)
        archive = _read_regular(root, row["archive_path"], missing_ok=True)
        source_pre = _same_content(source, pre_binding)
        archive_exact = _same_content(archive, archive_binding)
        if archive is not None and not archive_exact:
            raise AttemptMigrationError("archive_binding_mismatch", row["archive_path"])
        if row["tracked_state"] == "untracked":
            if not (
                (source_pre and archive is None)
                or (source_pre and archive_exact)
                or (source is None and archive_exact)
            ):
                raise AttemptMigrationError(
                    "attempt_row_state_invalid", row["original_path"]
                )
        else:
            source_post = _same_content(source, restoration_binding)
            if not (
                (source_pre and archive is None)
                or (source_pre and archive_exact)
                or (source_post and archive_exact)
            ):
                raise AttemptMigrationError(
                    "attempt_row_state_invalid", row["original_path"]
                )


def _validate_common_live_bindings(root: Path, record: Mapping[str, Any]) -> None:
    capture_state = record["pre_move_repository_state"]
    capture_tree = _git(
        root, "rev-parse", f"{capture_state['head']}^{{tree}}"
    ).decode("ascii").strip()
    if capture_tree != capture_state["tree"]:
        raise AttemptMigrationError("capture_head_tree_mismatch")
    current_head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if not _git_is_ancestor(root, capture_state["head"], current_head):
        raise AttemptMigrationError("capture_head_not_ancestor")
    current_status = _repository_state(root)["status_projection"]["rows"]
    _validate_status_projection_boundaries(
        current_status, record["attempt_binding"]["source_root"]
    )

    for field in ("governing_plan_binding", "migration_plan_binding"):
        binding = record[field]
        live = _require_committed_live(root, binding["path"])
        if _content_binding(live) != binding:
            raise AttemptMigrationError("committed_binding_mismatch", binding["path"])

    review_bindings = record["authority_review_bindings"]
    spec_path = review_bindings["specification"]["path"]
    quality_path = review_bindings["code_quality"]["path"]
    spec_file, quality_file, specification_review, _ = _validate_review_pair(
        root,
        spec_path,
        quality_path,
        require_committed=True,
        expected_subject_kind="attempt_migration_authority",
    )
    if (
        _content_binding(spec_file) != review_bindings["specification"]
        or _content_binding(quality_file) != review_bindings["code_quality"]
    ):
        raise AttemptMigrationError("authority_review_binding_mismatch")

    attempt = record["attempt_binding"]
    observed_tree = _git(root, "rev-parse", f"{attempt['source_commit']}^{{tree}}").decode("ascii").strip()
    if observed_tree != attempt["source_tree"]:
        raise AttemptMigrationError("source_tree_mismatch")
    if not _git_is_ancestor(root, attempt["source_commit"], capture_state["head"]):
        raise AttemptMigrationError("source_commit_not_ancestor")
    manifest_binding = attempt["expected_paths_manifest_binding"]
    manifest_file = _require_committed_live(root, manifest_binding["path"])
    if _content_binding(manifest_file) != {
        key: manifest_binding[key] for key in ("path", "size", "sha256")
    }:
        raise AttemptMigrationError("expected_manifest_binding_mismatch")
    manifest_paths = _manifest_paths(manifest_file["data"], manifest_binding["path"])
    if manifest_paths != [row["original_path"] for row in record["attempt_rows"]]:
        raise AttemptMigrationError("expected_manifest_rows_mismatch")

    _validate_authority_subject(
        root,
        specification_review["subject"]["path"],
        governing_plan_binding=record["governing_plan_binding"],
        migration_plan_binding=record["migration_plan_binding"],
        expected_manifest_binding=manifest_binding,
        protected_path_bindings=record["protected_path_bindings"],
        protected_order_insensitive=(record["schema_version"] == V2_SCHEMA_VERSION),
    )

    _validate_attempt_replay_states(root, record)

    artifact_bindings = attempt["artifact_bindings"]
    row_by_path = {row["original_path"]: row for row in record["attempt_rows"]}
    baseline_binding = artifact_bindings["baseline"]
    baseline_specification = artifact_bindings["baseline_specification_review"]
    baseline_quality = artifact_bindings["baseline_quality_review"]
    baseline_snapshot = _resolve_attempt_row_snapshot(
        root, row_by_path[baseline_binding["path"]]
    )
    baseline_specification_snapshot = _resolve_attempt_row_snapshot(
        root, row_by_path[baseline_specification["path"]]
    )
    baseline_quality_snapshot = _resolve_attempt_row_snapshot(
        root, row_by_path[baseline_quality["path"]]
    )
    _validate_review_pair(
        root,
        baseline_specification["path"],
        baseline_quality["path"],
        require_committed=False,
        expected_subject_kind="implementation_failure_baseline",
        expected_subject_path=baseline_binding["path"],
        expected_subject_sha256=baseline_binding["sha256"],
        expected_subject_snapshot=baseline_snapshot,
        specification_snapshot=baseline_specification_snapshot,
        quality_snapshot=baseline_quality_snapshot,
    )

    for protected in record["protected_path_bindings"]:
        if not _same_content(_read_regular(root, protected["path"], missing_ok=True), protected):
            raise AttemptMigrationError("protected_path_changed", protected["path"])

    lineage = record["ledger_lineage"]
    for binding in (
        lineage["generation_5"]["request_binding"],
        lineage["generation_5"]["snapshot_binding"],
    ):
        live = _require_committed_live(root, binding["path"])
        if not _same_content(live, binding):
            raise AttemptMigrationError("generation5_binding_mismatch", binding["path"])
    restoration = lineage["restoration_binding"]
    restoration_source = _require_committed_live(root, restoration["source_path"])
    if not _same_content(
        restoration_source,
        {
            "file_type": restoration["file_type"],
            "lstat_mode": restoration["lstat_mode"],
            "size": restoration["size"],
            "sha256": restoration["sha256"],
        },
    ):
        raise AttemptMigrationError("restoration_binding_mismatch")
    committed_live = _committed_bytes(
        root, restoration["target_path"], revision=restoration["source_commit"]
    )
    if _bytes_digest(committed_live) != restoration["sha256"] or len(committed_live) != restoration["size"]:
        raise AttemptMigrationError("restoration_commit_bytes_mismatch")
    source_mode_text = _git(
        root,
        "ls-tree",
        restoration["source_commit"],
        "--",
        restoration["target_path"],
    ).decode("ascii", "strict").strip()
    if not source_mode_text or not _git_regular_mode_matches_live(
        source_mode_text, restoration["lstat_mode"]
    ):
        raise AttemptMigrationError("restoration_mode_mismatch")

    expected_archives = [row["archive_path"] for row in record["attempt_rows"]]
    observed_archives = _scan_regular_files(root, attempt["archive_root"])
    if any(path not in expected_archives for path in observed_archives):
        raise AttemptMigrationError("archive_contains_unreviewed_path")
    expected_source_status = set(row["original_path"] for row in record["attempt_rows"])
    extras = set(_status_paths(current_status, attempt["source_root"])) - expected_source_status
    if extras:
        raise AttemptMigrationError("source_contains_unreviewed_change")


def _validate_v2_attestation_transition(
    root: Path, record: Mapping[str, Any]
) -> dict[str, Any]:
    artifacts = record["attempt_binding"]["artifact_bindings"]
    row_by_path = {row["original_path"]: row for row in record["attempt_rows"]}
    snapshot_binding = artifacts["attestation_snapshot"]
    owner_binding = artifacts["attestation_record"]
    pending_snapshot = _resolve_attempt_row_snapshot(
        root, row_by_path[snapshot_binding["path"]]
    )
    owner_snapshot = _resolve_attempt_row_snapshot(
        root, row_by_path[owner_binding["path"]]
    )
    pending = _json_bytes(pending_snapshot["data"], snapshot_binding["path"])
    owner = _json_bytes(owner_snapshot["data"], owner_binding["path"])
    if pending.get("evidence_status") != "pending_owner_confirmation":
        raise AttemptMigrationError("v2_attestation_snapshot_lifecycle_invalid")
    if owner.get("evidence_status") != "owner_confirmed":
        raise AttemptMigrationError("v2_attestation_record_lifecycle_invalid")
    reversal_fields = (
        "evidence_status",
        "owner",
        "owner_confirmations",
        "owner_adoption",
    )
    if any(field not in pending or field not in owner for field in reversal_fields):
        raise AttemptMigrationError("v2_attestation_transition_invalid")
    reversed_owner = dict(owner)
    for field in reversal_fields:
        reversed_owner[field] = pending[field]
    if reversed_owner != pending:
        raise AttemptMigrationError("v2_attestation_transition_invalid")
    return owner


def _incident_original_rows_are_available(
    root: Path, incident: Mapping[str, Any]
) -> bool:
    for row in incident["attempt_rows"]:
        snapshot = _read_regular(root, row["path"], missing_ok=True)
        binding = {
            "path": row["path"],
            "file_type": row["file_type"],
            "lstat_mode": row["lstat_mode"],
            "size": row["size"],
            "sha256": row["sha256"],
        }
        if not _same_content(snapshot, binding):
            return False
    return True


def _validate_v2_incident_from_attempt_replay(
    root: Path,
    disposition: Mapping[str, Any],
    incident_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an incident through already-proved source/archive replay rows."""

    from .source_bindings import (
        SourceBindingError,
        derive_committed_predecessor_lineage,
    )

    incident = _validate_incident_structure(incident_record)
    frozen_state = incident["pre_move_repository_state"]
    frozen_tree = _git(
        root, "rev-parse", f"{frozen_state['head']}^{{tree}}"
    ).decode("ascii").strip()
    if frozen_tree != frozen_state["tree"]:
        raise AttemptMigrationError("incident_repository_state_tree_mismatch")

    for field in ("governing_plan_binding", "migration_plan_binding"):
        snapshot = _require_committed_live(root, incident[field]["path"])
        if _content_binding(snapshot) != incident[field]:
            raise AttemptMigrationError("incident_binding_mismatch", field)

    manifest_binding = incident["expected_paths_manifest_binding"]
    manifest_snapshot = _require_committed_live(root, manifest_binding["path"])
    paths = _manifest_paths(manifest_snapshot["data"], manifest_snapshot["path"])
    if _incident_manifest_binding(manifest_snapshot, paths) != manifest_binding:
        raise AttemptMigrationError("incident_manifest_binding_mismatch")
    if any(not _under(path, incident["source_root"]) for path in paths):
        raise AttemptMigrationError("incident_attempt_path_outside_source")

    disposition_rows = {
        row["original_path"]: row for row in disposition["attempt_rows"]
    }
    if set(disposition_rows) != {row["path"] for row in incident["attempt_rows"]}:
        raise AttemptMigrationError("v2_incident_row_set_mismatch")
    resolved: dict[str, dict[str, Any]] = {}
    for incident_row in incident["attempt_rows"]:
        disposition_row = disposition_rows[incident_row["path"]]
        if {
            "path": disposition_row["original_path"],
            "tracked_state": disposition_row["tracked_state"],
            "file_type": disposition_row["file_type"],
            "lstat_mode": disposition_row["lstat_mode"],
            "size": disposition_row["size"],
            "sha256": disposition_row["sha256"],
        } != incident_row:
            raise AttemptMigrationError("v2_incident_row_binding_mismatch")
        snapshot = _resolve_attempt_row_snapshot(root, disposition_row)
        expected_binding = {
            "path": incident_row["path"],
            "file_type": incident_row["file_type"],
            "lstat_mode": incident_row["lstat_mode"],
            "size": incident_row["size"],
            "sha256": incident_row["sha256"],
        }
        if not _same_content(snapshot, expected_binding):
            raise AttemptMigrationError(
                "v2_incident_resolved_row_mismatch", incident_row["path"]
            )
        resolved[incident_row["path"]] = snapshot
    if paths != sorted(resolved):
        raise AttemptMigrationError("incident_source_set_mismatch")
    bound_file_bytes = {
        path: snapshot["data"] for path, snapshot in resolved.items()
    }

    evidence_fields = (
        "workspace_baseline_binding",
        "owner_attestation_binding",
        "pending_attestation_snapshot_binding",
        "known_failure_baseline_binding",
    )
    evidence_snapshots: dict[str, dict[str, Any]] = {}
    for field in evidence_fields:
        binding = incident[field]
        snapshot = resolved.get(binding["path"])
        if snapshot is None or _content_binding(snapshot) != binding:
            raise AttemptMigrationError("incident_binding_mismatch", field)
        evidence_snapshots[field] = snapshot

    workspace, _owner, _pending, baseline, adoption_facts = (
        _validate_incident_evidence_records(
            root,
            workspace_snapshot=evidence_snapshots["workspace_baseline_binding"],
            owner_snapshot=evidence_snapshots["owner_attestation_binding"],
            pending_snapshot=evidence_snapshots[
                "pending_attestation_snapshot_binding"
            ],
            baseline_snapshot=evidence_snapshots[
                "known_failure_baseline_binding"
            ],
            bound_file_bytes=bound_file_bytes,
            require_committed_fallback=True,
        )
    )
    if adoption_facts != incident["adoption_facts"]:
        raise AttemptMigrationError("incident_adoption_facts_mismatch")

    intended = incident["intended_predecessor"]
    candidate = baseline.get("candidate_binding")
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("head") != intended["head"]
        or candidate.get("head_tree") != intended["tree"]
    ):
        raise AttemptMigrationError("incident_candidate_predecessor_mismatch")
    try:
        predecessor_projection = derive_committed_predecessor_lineage(
            root,
            baseline_head=workspace["head"],
            intended_predecessor_head=intended["head"],
            require_uncovered_paths=True,
        )
    except (KeyError, SourceBindingError) as exc:
        raise AttemptMigrationError(
            "incident_predecessor_projection_invalid", str(exc)
        ) from exc
    if (
        predecessor_projection != incident["predecessor_projection"]
        or predecessor_projection["intended_predecessor_tree"] != intended["tree"]
    ):
        raise AttemptMigrationError("incident_predecessor_projection_mismatch")
    current_head = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if not _git_is_ancestor(root, intended["head"], current_head):
        raise AttemptMigrationError("incident_predecessor_not_current_ancestor")
    required_attempt_bindings = {
        incident[field]["path"] for field in evidence_fields
    }
    if not required_attempt_bindings <= set(paths):
        raise AttemptMigrationError("incident_evidence_outside_attempt")
    return incident


def _validate_disposition_v2_live_bindings(
    root: Path, record: Mapping[str, Any]
) -> None:
    lifecycle = record["attempt_lifecycle"]
    incident_binding = lifecycle["incident_binding"]
    incident_snapshot = _read_regular(root, incident_binding["path"])
    assert incident_snapshot is not None
    if (
        incident_snapshot["lstat_mode"] != 0o644
        or _content_binding(incident_snapshot) != incident_binding
    ):
        raise AttemptMigrationError("v2_incident_binding_mismatch")
    incident = _json_bytes(incident_snapshot["data"], incident_binding["path"])
    if incident_snapshot["data"] != _canonical_json(incident) + b"\n":
        raise AttemptMigrationError("v2_incident_not_canonical")
    incident = _validate_incident_structure(incident)
    if _incident_original_rows_are_available(root, incident):
        incident = validate_attempt_migration_incident(root, incident)
    else:
        incident = _validate_v2_incident_from_attempt_replay(root, record, incident)

    if (
        record["governing_plan_binding"] != incident["governing_plan_binding"]
        or record["migration_plan_binding"] != incident["migration_plan_binding"]
        or record["pre_move_repository_state"]
        != incident["pre_move_repository_state"]
    ):
        raise AttemptMigrationError("v2_incident_coordinate_mismatch")
    attempt = record["attempt_binding"]
    if (
        attempt["source_root"] != incident["source_root"]
        or attempt["expected_paths_manifest_binding"]
        != incident["expected_paths_manifest_binding"]
    ):
        raise AttemptMigrationError("v2_incident_coordinate_mismatch")

    incident_rows = {row["path"]: row for row in incident["attempt_rows"]}
    if set(incident_rows) != {
        row["original_path"] for row in record["attempt_rows"]
    }:
        raise AttemptMigrationError("v2_incident_row_set_mismatch")
    for row in record["attempt_rows"]:
        incident_row = incident_rows[row["original_path"]]
        if {
            "path": row["original_path"],
            "tracked_state": row["tracked_state"],
            "file_type": row["file_type"],
            "lstat_mode": row["lstat_mode"],
            "size": row["size"],
            "sha256": row["sha256"],
        } != incident_row:
            raise AttemptMigrationError("v2_incident_row_binding_mismatch")

    artifacts = attempt["artifact_bindings"]
    incident_role_fields = {
        "baseline": "known_failure_baseline_binding",
        "workspace_baseline": "workspace_baseline_binding",
        "attestation_snapshot": "pending_attestation_snapshot_binding",
        "attestation_record": "owner_attestation_binding",
    }
    for role, field in incident_role_fields.items():
        binding = artifacts[role]
        incident_content = incident[field]
        if {
            key: binding[key] for key in ("path", "size", "sha256")
        } != incident_content:
            raise AttemptMigrationError("v2_incident_artifact_binding_mismatch", role)
    owner_attestation = _validate_v2_attestation_transition(root, record)
    _validate_owner_review_role_cross_links(owner_attestation, artifacts)


def _validate_live_bindings(root: Path, record: Mapping[str, Any]) -> None:
    _validate_common_live_bindings(root, record)
    if record["schema_version"] == V2_SCHEMA_VERSION:
        _validate_disposition_v2_live_bindings(root, record)

def _load_disposition(
    repository_root: Path, disposition_path: Path | str
) -> tuple[dict[str, Any], dict[str, Any]]:
    logical_path = _relative_path(disposition_path, field="disposition_path")
    snapshot = _read_regular(repository_root, logical_path)
    assert snapshot is not None
    if snapshot["lstat_mode"] != 0o644:
        raise AttemptMigrationError("disposition_mode_invalid", logical_path)
    record = _json_bytes(snapshot["data"], logical_path)
    if snapshot["data"] != _canonical_json(record) + b"\n":
        raise AttemptMigrationError("disposition_not_canonical")
    try:
        validated = _validate_disposition_structure(record)
    except AttemptMigrationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise AttemptMigrationError("disposition_structure_invalid") from exc
    _reject_output_overlap(
        logical_path,
        validated["attempt_binding"]["source_root"],
        validated["attempt_binding"]["archive_root"],
        [row["original_path"] for row in validated["attempt_rows"]],
    )
    return validated, snapshot


def validate(
    repository_root: Path | str, disposition_path: Path | str
) -> dict[str, Any]:
    """Reopen every bound byte and validate an allowed replay state."""

    root = _repository_root(repository_root)
    disposition_relative = _relative_path(disposition_path)
    record, _ = _load_disposition(root, disposition_relative)
    _validate_live_bindings(root, record)
    if record["schema_version"] == V2_SCHEMA_VERSION:
        _require_outside_status_projection_unchanged(
            root,
            record,
            additional_ignored_paths=(
                disposition_relative,
                record["attempt_lifecycle"]["incident_binding"]["path"],
            ),
        )
    return record


def _require_committed_disposition_review_pair(
    root: Path,
    disposition_path: str,
    disposition_snapshot: Mapping[str, Any],
    specification_review_path: Path | str,
    quality_review_path: Path | str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        committed_bytes = _committed_bytes(root, disposition_path)
    except AttemptMigrationError as exc:
        raise AttemptMigrationError("disposition_not_committed_at_head") from exc
    tree_entry = _git(root, "ls-tree", "HEAD", "--", disposition_path).decode(
        "ascii", "strict"
    ).strip()
    if not tree_entry:
        raise AttemptMigrationError("disposition_not_committed_at_head")
    committed_mode = int(tree_entry.split()[0], 8) & 0o7777
    if (
        committed_bytes != disposition_snapshot["data"]
        or committed_mode != disposition_snapshot["lstat_mode"]
    ):
        raise AttemptMigrationError("disposition_not_committed_at_head")
    spec_path = _relative_path(specification_review_path)
    quality_path = _relative_path(quality_review_path)
    spec_file, quality_file, _, _ = _validate_review_pair(
        root,
        spec_path,
        quality_path,
        require_committed=True,
        expected_subject_kind="attempt_migration_disposition",
        expected_subject_path=disposition_path,
        expected_subject_sha256=disposition_snapshot["sha256"],
        expected_subject_snapshot=disposition_snapshot,
    )
    return _content_binding(spec_file), _content_binding(quality_file)


def _publish_archive_from_source(root: Path, row: Mapping[str, Any]) -> None:
    source_parent, source_name, _ = _open_parent(root, row["original_path"])
    archive_parent, archive_name, archive_relative = _open_parent(
        root, row["archive_path"], create=True
    )
    try:
        try:
            os.link(
                source_name,
                archive_name,
                src_dir_fd=source_parent,
                dst_dir_fd=archive_parent,
                follow_symlinks=False,
            )
        except FileExistsError:
            existing = _read_regular(root, archive_relative)
            if not _same_content(existing, _binding_from_row(row, path_field="archive_path")):
                raise AttemptMigrationError("archive_destination_conflict", archive_relative)
        except OSError as exc:
            raise AttemptMigrationError("archive_publication_failed", archive_relative) from exc
        os.fsync(archive_parent)
    finally:
        os.close(source_parent)
        os.close(archive_parent)
    archive = _read_regular(root, archive_relative)
    if not _same_content(archive, _binding_from_row(row, path_field="archive_path")):
        raise AttemptMigrationError("archive_publication_mismatch", archive_relative)


def _remove_exact_source(root: Path, row: Mapping[str, Any]) -> None:
    parent, name, relative = _open_parent(root, row["original_path"])
    try:
        logical_parent = bind_logical_parent(root, Path(relative).parent, parent)
        captured = capture_regular_file_at(parent, name, relative, missing_ok=False)
        assert captured is not None
        if (
            stat.S_IMODE(captured.mode) != row["lstat_mode"]
            or len(captured.data) != row["size"]
            or _bytes_digest(captured.data) != row["sha256"]
        ):
            raise AttemptMigrationError("source_changed_before_removal", relative)
        quarantine = conditional_quarantine_file_at(
            parent,
            name,
            captured,
            relative,
            logical_parent=logical_parent,
        )
        quarantined = capture_regular_file_at(
            parent, quarantine, relative, missing_ok=False
        )
        assert quarantined is not None
        if (
            stat.S_IMODE(quarantined.mode) != row["lstat_mode"]
            or len(quarantined.data) != row["size"]
            or _bytes_digest(quarantined.data) != row["sha256"]
        ):
            raise AttemptMigrationError("quarantined_source_mismatch", relative)
        os.unlink(quarantine, dir_fd=parent)
        os.fsync(parent)
    except AttemptMigrationError:
        raise
    except (AtomicPublishError, OSError) as exc:
        raise AttemptMigrationError("source_removal_failed", relative) from exc
    finally:
        os.close(parent)


def _restore_tracked_source(
    root: Path, row: Mapping[str, Any], restoration: Mapping[str, Any]
) -> None:
    restoration_source = _read_regular(root, restoration["source_path"])
    assert restoration_source is not None
    parent, name, relative = _open_parent(root, row["original_path"])
    temporary = f".{name}.{os.getpid()}.{secrets.token_hex(12)}.restore"
    descriptor = -1
    cleanup = True
    try:
        existing = capture_regular_file_at(parent, name, relative, missing_ok=False)
        assert existing is not None
        if (
            stat.S_IMODE(existing.mode) != row["lstat_mode"]
            or len(existing.data) != row["size"]
            or _bytes_digest(existing.data) != row["sha256"]
        ):
            raise AttemptMigrationError("tracked_source_changed_before_restore", relative)
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(temporary, flags, restoration["lstat_mode"], dir_fd=parent)
        os.fchmod(descriptor, restoration["lstat_mode"])
        data = restoration_source["data"]
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        logical_parent = bind_logical_parent(root, Path(relative).parent, parent)
        conditional_publish_file_at(
            parent,
            temporary,
            name,
            existing,
            relative,
            logical_parent=logical_parent,
        )
        displaced = capture_regular_file_at(parent, temporary, relative, missing_ok=False)
        assert displaced is not None
        if _bytes_digest(displaced.data) != row["sha256"]:
            cleanup = False
            raise AttemptMigrationError("tracked_source_exchange_invalid", relative)
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
    except AttemptMigrationError:
        raise
    except (AtomicPublishError, OSError) as exc:
        raise AttemptMigrationError("tracked_source_restore_failed", relative) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if cleanup:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def apply(
    repository_root: Path | str,
    disposition_path: Path | str,
    specification_review_path: Path | str,
    quality_review_path: Path | str,
) -> dict[str, Any]:
    """Apply only the exact disposition authorized by committed review bytes."""

    root = _repository_root(repository_root)
    disposition_relative = _relative_path(disposition_path)
    record, snapshot = _load_disposition(root, disposition_relative)
    _require_committed_disposition_review_pair(
        root,
        disposition_relative,
        snapshot,
        specification_review_path,
        quality_review_path,
    )
    _validate_live_bindings(root, record)
    _require_outside_status_projection_unchanged(root, record)
    _require_migration_index_classification(root, record)
    restoration = record["ledger_lineage"]["restoration_binding"]
    restoration_binding = {
        "path": restoration["target_path"],
        "file_type": restoration["file_type"],
        "lstat_mode": restoration["lstat_mode"],
        "size": restoration["size"],
        "sha256": restoration["sha256"],
    }
    for row in record["attempt_rows"]:
        source = _read_regular(root, row["original_path"], missing_ok=True)
        archive = _read_regular(root, row["archive_path"], missing_ok=True)
        pre_binding = _binding_from_row(row, path_field="original_path")
        archive_binding = _binding_from_row(row, path_field="archive_path")
        source_pre = _same_content(source, pre_binding)
        archive_exact = _same_content(archive, archive_binding)
        if row["tracked_state"] == "untracked":
            if source is None and archive_exact:
                continue
            if not source_pre or (archive is not None and not archive_exact):
                raise AttemptMigrationError("attempt_row_state_invalid", row["original_path"])
            if archive is None:
                _publish_archive_from_source(root, row)
            _remove_exact_source(root, row)
        else:
            source_post = _same_content(source, restoration_binding)
            if source_post and archive_exact:
                continue
            if not source_pre or (archive is not None and not archive_exact):
                raise AttemptMigrationError("attempt_row_state_invalid", row["original_path"])
            if archive is None:
                _publish_archive_from_source(root, row)
            _restore_tracked_source(root, row, restoration)
    return record


def _outside_status_rows(
    rows: Sequence[Mapping[str, Any]], ignored_paths: set[str]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        operands = {row["path"]}
        if row.get("source_path") is not None:
            operands.add(row["source_path"])
        if operands.issubset(ignored_paths):
            continue
        if not operands.isdisjoint(ignored_paths):
            raise AttemptMigrationError("status_projection_boundary_crossing")
        result.append(dict(row))
    return result


def _require_outside_status_projection_unchanged(
    root: Path,
    record: Mapping[str, Any],
    *,
    additional_ignored_paths: Sequence[str] = (),
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ignored = {
        *[row["original_path"] for row in record["attempt_rows"]],
        *[row["archive_path"] for row in record["attempt_rows"]],
        *additional_ignored_paths,
    }
    before = _outside_status_rows(
        record["pre_move_repository_state"]["status_projection"]["rows"], ignored
    )
    current_state = _repository_state(root)
    after = _outside_status_rows(current_state["status_projection"]["rows"], ignored)
    if before != after:
        raise AttemptMigrationError("outside_status_projection_changed")
    return current_state, after


def _git_path_entries(
    root: Path,
    paths: Sequence[str],
    *,
    index: bool,
    revision: str = "HEAD",
) -> dict[str, tuple[str, str]]:
    output = (
        _git(root, "ls-files", "--stage", "-z", "--", *paths)
        if index
        else _git(root, "ls-tree", "-z", revision, "--", *paths)
    )
    entries: dict[str, tuple[str, str]] = {}
    try:
        for raw_entry in output.split(b"\0"):
            if not raw_entry:
                continue
            raw_metadata, separator, raw_path = raw_entry.partition(b"\t")
            if not separator:
                raise ValueError("entry separator missing")
            metadata = raw_metadata.decode("ascii", "strict").split()
            path = raw_path.decode("utf-8", "strict")
            if index:
                if len(metadata) != 3 or metadata[2] != "0":
                    raise ValueError("non-stage-zero index entry")
                mode, object_id = metadata[:2]
            else:
                if len(metadata) != 3 or metadata[1] != "blob":
                    raise ValueError("non-blob tree entry")
                mode, object_id = metadata[0], metadata[2]
            if path in entries:
                raise ValueError("duplicate path entry")
            entries[path] = (mode, object_id)
    except (UnicodeDecodeError, ValueError) as exc:
        raise AttemptMigrationError("migration_index_classification_changed") from exc
    return entries


def _is_full_migration_post_state(
    root: Path, record: Mapping[str, Any]
) -> bool:
    restoration = record["ledger_lineage"]["restoration_binding"]
    restoration_binding = {
        "file_type": restoration["file_type"],
        "lstat_mode": restoration["lstat_mode"],
        "size": restoration["size"],
        "sha256": restoration["sha256"],
    }
    for row in record["attempt_rows"]:
        archive = _read_regular(root, row["archive_path"], missing_ok=True)
        if not _same_content(
            archive, _binding_from_row(row, path_field="archive_path")
        ):
            return False
        source = _read_regular(root, row["original_path"], missing_ok=True)
        if row["tracked_state"] == "untracked":
            if source is not None:
                return False
        elif not _same_content(source, restoration_binding):
            return False
    return True


def _require_migration_index_classification(
    root: Path, record: Mapping[str, Any]
) -> None:
    rows = record["attempt_rows"]
    originals = [row["original_path"] for row in rows]
    archives = [row["archive_path"] for row in rows]
    paths = [*originals, *archives]
    head_entries = _git_path_entries(root, paths, index=False)
    index_entries = _git_path_entries(root, paths, index=True)
    restoration = record["ledger_lineage"]["restoration_binding"]
    restoration_path = restoration["target_path"]
    restoration_entry = _git_path_entries(
        root,
        [restoration_path],
        index=False,
        revision=restoration["source_commit"],
    ).get(restoration_path)
    if (
        restoration_entry is None
        or restoration_entry[0] not in {"100644", "100755"}
        or not _git_regular_mode_matches_live(
            restoration_entry[0], restoration["lstat_mode"]
        )
    ):
        raise AttemptMigrationError("migration_index_classification_changed")
    committed_archives = {path for path in archives if path in head_entries}
    if committed_archives and (
        len(committed_archives) != len(archives)
        or not _is_full_migration_post_state(root, record)
    ):
        raise AttemptMigrationError("migration_index_classification_changed")

    for row in rows:
        original = row["original_path"]
        archive = row["archive_path"]
        if row["tracked_state"] == "untracked":
            if original in head_entries or original in index_entries:
                raise AttemptMigrationError("migration_index_classification_changed")
        else:
            head_entry = head_entries.get(original)
            if (
                head_entry != restoration_entry
                or index_entries.get(original) != restoration_entry
            ):
                raise AttemptMigrationError("migration_index_classification_changed")

        archive_head = head_entries.get(archive)
        archive_index = index_entries.get(archive)
        if archive_head is None:
            if archive_index is not None:
                raise AttemptMigrationError("migration_index_classification_changed")
            continue
        if archive_index != archive_head or not _git_regular_mode_matches_live(
            archive_head[0], row["lstat_mode"]
        ):
            raise AttemptMigrationError("migration_index_classification_changed")
        committed = _committed_bytes(root, archive)
        if len(committed) != row["size"] or _bytes_digest(committed) != row["sha256"]:
            raise AttemptMigrationError("migration_index_classification_changed")


def _state_without_paths(
    state: Mapping[str, Any], ignored_paths: set[str]
) -> dict[str, Any]:
    projected = dict(state)
    status_rows = _outside_status_rows(state["status_projection"]["rows"], ignored_paths)
    projected["status_projection"] = {
        "rows": status_rows,
        "row_count": len(status_rows),
        "normalized_rows_sha256": _canonical_digest(status_rows),
    }
    return projected


def postvalidate(
    repository_root: Path | str,
    disposition_path: Path | str,
    specification_review_path: Path | str,
    quality_review_path: Path | str,
    report_path: Path | str,
) -> dict[str, Any]:
    """Require the exact post-state and emit a closed canonical report."""

    root = _repository_root(repository_root)
    disposition_relative = _relative_path(disposition_path)
    report_relative = _relative_path(report_path)
    record, snapshot = _load_disposition(root, disposition_relative)
    _reject_output_overlap(
        report_relative,
        record["attempt_binding"]["source_root"],
        record["attempt_binding"]["archive_root"],
        [row["original_path"] for row in record["attempt_rows"]],
    )
    specification_binding, quality_binding = _require_committed_disposition_review_pair(
        root,
        disposition_relative,
        snapshot,
        specification_review_path,
        quality_review_path,
    )
    _validate_live_bindings(root, record)
    current_state, after_outside = _require_outside_status_projection_unchanged(
        root, record, additional_ignored_paths=(report_relative,)
    )
    expected_archives = [row["archive_path"] for row in record["attempt_rows"]]
    if _scan_regular_files(root, record["attempt_binding"]["archive_root"]) != expected_archives:
        raise AttemptMigrationError("archive_coverage_mismatch")
    restoration = record["ledger_lineage"]["restoration_binding"]
    restoration_binding = {
        "path": restoration["target_path"],
        "file_type": restoration["file_type"],
        "lstat_mode": restoration["lstat_mode"],
        "size": restoration["size"],
        "sha256": restoration["sha256"],
    }
    archive_rows: list[dict[str, Any]] = []
    for row in record["attempt_rows"]:
        archive_binding = _binding_from_row(row, path_field="archive_path")
        archive = _read_regular(root, row["archive_path"])
        assert archive is not None
        if not _same_content(archive, archive_binding):
            raise AttemptMigrationError("archive_binding_mismatch", row["archive_path"])
        source = _read_regular(root, row["original_path"], missing_ok=True)
        if row["tracked_state"] == "untracked":
            if source is not None:
                raise AttemptMigrationError("untracked_source_still_present", row["original_path"])
        elif not _same_content(source, restoration_binding):
            raise AttemptMigrationError("tracked_source_not_restored", row["original_path"])
        archive_rows.append(archive_binding)

    for protected in record["protected_path_bindings"]:
        if not _same_content(_read_regular(root, protected["path"], missing_ok=True), protected):
            raise AttemptMigrationError("protected_path_changed", protected["path"])

    report: dict[str, Any] = {
        "schema_version": POST_REPORT_SCHEMA_VERSION,
        "result": "passed",
        "disposition_binding": _content_binding(snapshot),
        "disposition_review_bindings": {
            "specification": specification_binding,
            "code_quality": quality_binding,
        },
        "repository_state": _state_without_paths(current_state, {report_relative}),
        "archive_rows": archive_rows,
        "archive_path_count": len(archive_rows),
        "archive_path_set_sha256": _canonical_digest(expected_archives),
        "protected_path_bindings": record["protected_path_bindings"],
        "outside_status_projection_sha256": _canonical_digest(after_outside),
        "normalized_report_sha256": "",
        "claims_not_made": POST_CLAIMS_NOT_MADE,
    }
    report["normalized_report_sha256"] = _canonical_digest(
        report, exclude="normalized_report_sha256"
    )
    data = _canonical_json(report) + b"\n"
    existing = _read_regular(root, report_relative, missing_ok=True)
    if existing is None:
        _publish_exclusive(root, report_relative, data, 0o644)
    elif existing["data"] != data or existing["lstat_mode"] != 0o644:
        raise AttemptMigrationError("post_report_conflict", report_relative)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m orchestrator.retirement.attempt_migration")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--repository-root", required=True)
    capture_parser.add_argument("--disposition-path", required=True)
    capture_parser.add_argument("--source-root", required=True)
    capture_parser.add_argument("--archive-root", required=True)
    capture_parser.add_argument("--governing-plan-path", required=True)
    capture_parser.add_argument("--migration-plan-path", required=True)
    capture_parser.add_argument("--authority-subject-path", required=True)
    capture_parser.add_argument("--authority-specification-review-path", required=True)
    capture_parser.add_argument("--authority-quality-review-path", required=True)
    capture_parser.add_argument("--source-commit", required=True)
    capture_parser.add_argument("--source-tree", required=True)
    capture_parser.add_argument("--expected-paths-manifest-path", required=True)
    capture_parser.add_argument("--protected-path", action="append", default=[])
    capture_parser.add_argument("--generation5-request-path", required=True)
    capture_parser.add_argument("--generation5-snapshot-path", required=True)
    capture_parser.add_argument("--generation11-request-path", required=True)
    capture_parser.add_argument("--generation11-snapshot-path", required=True)
    capture_parser.add_argument("--live-ledger-path", required=True)
    capture_parser.add_argument("--baseline-path", required=True)
    capture_parser.add_argument("--baseline-specification-review-path", required=True)
    capture_parser.add_argument("--baseline-quality-review-path", required=True)
    capture_parser.add_argument("--pending-request-path", required=True)
    capture_parser.add_argument("--pending-snapshot-path", required=True)
    capture_parser.add_argument("--pending-record-path", required=True)

    adopted_parser = subparsers.add_parser("capture-invalidated-adopted")
    adopted_parser.add_argument("--repository-root", required=True)
    adopted_parser.add_argument("--incident-path", required=True)
    adopted_parser.add_argument("--disposition-path", required=True)
    adopted_parser.add_argument("--source-root", required=True)
    adopted_parser.add_argument("--archive-root", required=True)
    adopted_parser.add_argument("--governing-plan-path", required=True)
    adopted_parser.add_argument("--migration-plan-path", required=True)
    adopted_parser.add_argument("--authority-subject-path", required=True)
    adopted_parser.add_argument(
        "--authority-specification-review-path", required=True
    )
    adopted_parser.add_argument("--authority-quality-review-path", required=True)
    adopted_parser.add_argument("--intended-predecessor-head", required=True)
    adopted_parser.add_argument("--restoration-commit", required=True)
    adopted_parser.add_argument("--restoration-tree", required=True)
    adopted_parser.add_argument("--expected-paths-manifest-path", required=True)
    adopted_parser.add_argument("--protected-path", action="append", default=[])
    adopted_parser.add_argument("--generation5-request-path", required=True)
    adopted_parser.add_argument("--generation5-snapshot-path", required=True)
    adopted_parser.add_argument("--generation11-request-path", required=True)
    adopted_parser.add_argument("--generation11-snapshot-path", required=True)
    adopted_parser.add_argument("--live-ledger-path", required=True)
    adopted_parser.add_argument("--baseline-path", required=True)
    adopted_parser.add_argument(
        "--baseline-specification-review-path", required=True
    )
    adopted_parser.add_argument("--baseline-quality-review-path", required=True)
    adopted_parser.add_argument("--workspace-baseline-path", required=True)
    adopted_parser.add_argument("--attestation-request-path", required=True)
    adopted_parser.add_argument("--attestation-snapshot-path", required=True)
    adopted_parser.add_argument("--attestation-record-path", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--repository-root", required=True)
    validate_parser.add_argument("--disposition-path", required=True)

    for mode in ("apply", "postvalidate"):
        command = subparsers.add_parser(mode)
        command.add_argument("--repository-root", required=True)
        command.add_argument("--disposition-path", required=True)
        command.add_argument("--specification-review-path", required=True)
        command.add_argument("--quality-review-path", required=True)
        if mode == "postvalidate":
            command.add_argument("--report-path", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = vars(_parser().parse_args(argv))
    mode = arguments.pop("mode")
    try:
        if mode == "capture":
            arguments["protected_paths"] = arguments.pop("protected_path")
            result = capture(**arguments)
        elif mode == "capture-invalidated-adopted":
            arguments["protected_paths"] = arguments.pop("protected_path")
            result = capture_invalidated_adopted(**arguments)
        elif mode == "validate":
            result = validate(**arguments)
        elif mode == "apply":
            result = apply(**arguments)
        elif mode == "postvalidate":
            result = postvalidate(**arguments)
        else:  # pragma: no cover - argparse constrains the mode set
            raise AttemptMigrationError("operation_mode_invalid", mode)
    except AttemptMigrationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(_canonical_json(result).decode("utf-8"))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI test
    raise SystemExit(main())
