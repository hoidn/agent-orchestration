"""Descriptor-bound capture of one phase-private provider result bundle."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from hashlib import sha256
import errno
import json
import os
import stat
from typing import Any, Literal, Mapping, Protocol
import unicodedata

from jsonschema import Draft202012Validator

from orchestrator.providers.isolation import (
    MAX_PROVIDER_ISOLATION_RUNTIME_RELPATH_LENGTH,
    canonical_isolation_json_bytes,
    load_provider_isolation_schema,
)
from orchestrator.providers.isolation_runtime_authority import (
    MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH,
    MAX_RUNTIME_AUTHORITY_ENTRY_COUNT,
    MountIdentityUnavailable,
    RuntimeAuthorityObjectIdentity,
    _statx_mount_id,
)


BUNDLE_BROKER_ERROR_CODE = "provider_isolation_bundle_broker_failed"
BUNDLE_OVERSIZED_REASON = "provider_isolation_bundle_oversized"
BUNDLE_REJECTED_REASON = "provider_isolation_bundle_rejected"
_TRANSFER_SCHEMA_RESOURCE = "provider-isolation-bundle-transfer-v1.schema.json"
_TRANSFER_SCHEMA_VERSION = "provider_isolation_bundle_transfer.v1"
_MAX_BUNDLE_BYTES = 16_777_216
_MAX_UINT64 = (1 << 64) - 1
_BROKER_ROOT = ".provider-isolation-broker"
_TRANSFER_ROOT = "transfers"
_JOURNAL_NAME = "transfer.json"
_STAGED_NAME = "bundle.staged"
_ARCHIVE_NAME = "bundle.invalid"
_RENAME_NOREPLACE = 1
_BOUND_CAPTURE_TOKEN = object()
_TRANSFER_REQUEST_TOKEN = object()


class ProviderIsolationBundleBrokerError(RuntimeError):
    """A descriptor-bound bundle operation could not be proved safe."""

    code = BUNDLE_BROKER_ERROR_CODE

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True, slots=True)
class ProviderIsolationBundleCapture:
    """Bounded result of classifying and reading one active bundle."""

    classification: Literal["captured", "missing", "rejected"]
    data: bytes | None
    digest: str | None
    size_bytes: int | None
    reason: str | None
    _source_authority_binding: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _binding: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _token: object | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_capture_shape(self)
        if self._source_authority_binding is None:
            if self._binding is not None or self._token is not None:
                raise TypeError("raw bundle capture has invalid private fields")
            return
        if self._token is not _BOUND_CAPTURE_TOKEN:
            raise TypeError(
                "authority-bound capture requires the validating factory"
            )
        _require_digest(
            self._source_authority_binding,
            "capture source authority binding",
        )
        if self._binding != _derive_bound_capture_binding(
            self,
            source_authority_binding=self._source_authority_binding,
        ):
            raise TypeError("authority-bound capture binding changed")


def capture_active_bundle(
    *,
    scratch_directory_fd: int,
    active_basename: str,
    expected_scratch_mount_id: int,
    max_bytes: int,
) -> ProviderIsolationBundleCapture:
    """Capture one regular active bundle without readable-opening its basename."""

    _require_arguments(
        scratch_directory_fd=scratch_directory_fd,
        active_basename=active_basename,
        expected_scratch_mount_id=expected_scratch_mount_id,
        max_bytes=max_bytes,
    )
    pin_fd = -1
    read_fd = -1
    try:
        scratch = os.fstat(scratch_directory_fd)
        try:
            scratch_mount_id = _statx_mount_id(scratch_directory_fd)
        except MountIdentityUnavailable as exc:
            raise ProviderIsolationBundleBrokerError(
                "scratch mount identity is unavailable"
            ) from exc
        if not stat.S_ISDIR(scratch.st_mode) or (
            scratch_mount_id != expected_scratch_mount_id
        ):
            return _rejected(BUNDLE_REJECTED_REASON)
        try:
            pin_fd = os.open(
                active_basename,
                os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=scratch_directory_fd,
            )
        except FileNotFoundError:
            return _missing()
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return _missing()
            raise ProviderIsolationBundleBrokerError(
                "descriptor-first bundle pin is unavailable"
            ) from exc

        pinned = os.fstat(pin_fd)
        if not stat.S_ISREG(pinned.st_mode) or pinned.st_nlink != 1:
            return _rejected(BUNDLE_REJECTED_REASON)
        if pinned.st_size > max_bytes:
            return _rejected(BUNDLE_OVERSIZED_REASON)
        try:
            if _statx_mount_id(pin_fd) != expected_scratch_mount_id:
                return _rejected(BUNDLE_REJECTED_REASON)
            linked_before = os.stat(
                active_basename,
                dir_fd=scratch_directory_fd,
                follow_symlinks=False,
            )
            if (
                not _same_object(linked_before, pinned)
                or _statx_mount_id(
                    scratch_directory_fd,
                    active_basename,
                )
                != expected_scratch_mount_id
            ):
                return _rejected(BUNDLE_REJECTED_REASON)
        except MountIdentityUnavailable as exc:
            raise ProviderIsolationBundleBrokerError(
                "bundle mount identity is unavailable"
            ) from exc
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return _rejected(BUNDLE_REJECTED_REASON)
            raise ProviderIsolationBundleBrokerError(
                "linked bundle classification is unavailable"
            ) from exc
        except ValueError as exc:
            raise ProviderIsolationBundleBrokerError(
                "linked bundle classification failed"
            ) from exc

        try:
            read_fd = os.open(
                f"/proc/self/fd/{pin_fd}",
                os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC,
            )
        except OSError as exc:
            raise ProviderIsolationBundleBrokerError(
                "trusted descriptor read view is unavailable"
            ) from exc
        readable_before = os.fstat(read_fd)
        try:
            readable_mount_id = _statx_mount_id(read_fd)
        except MountIdentityUnavailable as exc:
            raise ProviderIsolationBundleBrokerError(
                "read descriptor mount identity is unavailable"
            ) from exc
        if not _same_stable_file(readable_before, pinned) or (
            readable_mount_id != expected_scratch_mount_id
        ):
            return _rejected(BUNDLE_REJECTED_REASON)
        try:
            data = _read_bounded(read_fd, max_bytes)
        except OSError as exc:
            raise ProviderIsolationBundleBrokerError(
                "bounded descriptor read failed"
            ) from exc

        readable_after = os.fstat(read_fd)
        pin_after = os.fstat(pin_fd)
        try:
            linked_after = os.stat(
                active_basename,
                dir_fd=scratch_directory_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return _rejected(BUNDLE_REJECTED_REASON)
            raise ProviderIsolationBundleBrokerError(
                "post-read linked bundle classification is unavailable"
            ) from exc
        try:
            read_mount_after = _statx_mount_id(read_fd)
            pin_mount_after = _statx_mount_id(pin_fd)
            linked_mount_after = _statx_mount_id(
                scratch_directory_fd,
                active_basename,
            )
            scratch_mount_after = _statx_mount_id(scratch_directory_fd)
        except MountIdentityUnavailable as exc:
            raise ProviderIsolationBundleBrokerError(
                "post-read mount identity is unavailable"
            ) from exc
        if (
            not _same_stable_file(readable_after, pinned)
            or not _same_stable_file(pin_after, pinned)
            or not _same_stable_file(linked_after, pinned)
            or read_mount_after != expected_scratch_mount_id
            or pin_mount_after != expected_scratch_mount_id
            or linked_mount_after != expected_scratch_mount_id
            or scratch_mount_after != expected_scratch_mount_id
        ):
            return _rejected(BUNDLE_REJECTED_REASON)
        if len(data) > max_bytes:
            return _rejected(BUNDLE_OVERSIZED_REASON)
        if len(data) != pinned.st_size:
            return _rejected(BUNDLE_REJECTED_REASON)
        return ProviderIsolationBundleCapture(
            classification="captured",
            data=data,
            digest=f"sha256:{sha256(data).hexdigest()}",
            size_bytes=len(data),
            reason=None,
        )
    except ProviderIsolationBundleBrokerError:
        raise
    except (OSError, ValueError) as exc:
        raise ProviderIsolationBundleBrokerError(
            "descriptor-bound bundle classification failed"
        ) from exc
    finally:
        if read_fd >= 0:
            os.close(read_fd)
        if pin_fd >= 0:
            os.close(pin_fd)


def _read_bounded(fd: int, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    while remaining:
        chunk = os.read(fd, min(remaining, 64 * 1024))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _same_object(
    observed: os.stat_result,
    expected: os.stat_result,
) -> bool:
    return (
        stat.S_IFMT(observed.st_mode) == stat.S_IFMT(expected.st_mode)
        and observed.st_dev == expected.st_dev
        and observed.st_ino == expected.st_ino
        and observed.st_nlink == expected.st_nlink
    )


def _same_stable_file(
    observed: os.stat_result,
    expected: os.stat_result,
) -> bool:
    return (
        _same_object(observed, expected)
        and observed.st_nlink == 1
        and observed.st_size == expected.st_size
        and observed.st_mtime_ns == expected.st_mtime_ns
        and observed.st_ctime_ns == expected.st_ctime_ns
    )


def _require_arguments(
    *,
    scratch_directory_fd: int,
    active_basename: str,
    expected_scratch_mount_id: int,
    max_bytes: int,
) -> None:
    if type(scratch_directory_fd) is not int or scratch_directory_fd < 0:
        raise TypeError("scratch_directory_fd must be an open descriptor")
    if (
        type(active_basename) is not str
        or not active_basename
        or active_basename in {".", ".."}
        or "/" in active_basename
        or "\x00" in active_basename
        or unicodedata.normalize("NFC", active_basename) != active_basename
    ):
        raise TypeError("active_basename must be one normalized basename")
    if (
        type(expected_scratch_mount_id) is not int
        or expected_scratch_mount_id <= 0
    ):
        raise TypeError("expected_scratch_mount_id must be a positive integer")
    if (
        type(max_bytes) is not int
        or max_bytes <= 0
        or max_bytes > _MAX_BUNDLE_BYTES
    ):
        raise TypeError(
            "max_bytes must be in the inclusive range 1..16777216"
        )


def _missing() -> ProviderIsolationBundleCapture:
    return ProviderIsolationBundleCapture(
        classification="missing",
        data=None,
        digest=None,
        size_bytes=None,
        reason=None,
    )


def _rejected(reason: str) -> ProviderIsolationBundleCapture:
    return ProviderIsolationBundleCapture(
        classification="rejected",
        data=None,
        digest=None,
        size_bytes=None,
        reason=reason,
    )


@dataclass(frozen=True, slots=True)
class ProviderIsolationBundleTransferIdentity:
    """Reconstructable authority and identity for journal reconciliation."""

    runtime_root_fd: int
    expected_runtime_mount_id: int
    invocation_identity: str
    scope: tuple[str, ...]
    ordinal: int
    target_relative_path: str

    def __post_init__(self) -> None:
        _validate_transfer_identity(self)


@dataclass(frozen=True, slots=True)
class ProviderIsolationBundleTransferRequest:
    """Publication authority plus the ephemeral captured provider bytes."""

    runtime_root_fd: int
    expected_runtime_mount_id: int
    invocation_identity: str
    scope: tuple[str, ...]
    ordinal: int
    target_relative_path: str
    capture: ProviderIsolationBundleCapture
    _authority_binding: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _capture_binding: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _request_capture_binding: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _token: object | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self._token is not _TRANSFER_REQUEST_TOKEN:
            raise TypeError(
                "bundle transfer request requires the validating factory"
            )
        _validate_transfer_request(self)


@dataclass(frozen=True, slots=True)
class ProviderIsolationBundleTransferPaths:
    """Deterministic runtime-relative paths for one exact transfer."""

    journal_relative_path: str
    staged_relative_path: str
    target_relative_path: str
    archive_relative_path: str


@dataclass(frozen=True, slots=True)
class ProviderIsolationBundleTransferRecord:
    """One schema-validated canonical transfer journal."""

    state: Literal[
        "prepared",
        "published",
        "validated",
        "rotation_pending",
        "rotated",
    ]
    journal_relative_path: str
    staged_relative_path: str
    target_relative_path: str
    archive_relative_path: str
    canonical_json: bytes

    def to_dict(self) -> dict[str, Any]:
        document = json.loads(self.canonical_json)
        if not isinstance(document, dict):  # pragma: no cover - invariant
            raise AssertionError("bundle transfer journal must be an object")
        return document


class ProviderIsolationBundleRotationAcknowledgement(Protocol):
    """Temporary Task-3 caller seam authorizing invalid-result rotation."""

    def __call__(
        self,
        record: ProviderIsolationBundleTransferRecord,
    ) -> bool: ...


ProviderIsolationBundleCleanupEvidence = (
    ProviderIsolationBundleCapture | ProviderIsolationBundleTransferRecord
)


class ProviderIsolationBundleScratchCleanupAcknowledgement(Protocol):
    """Caller proof that bounded bundle evidence is durably accounted for."""

    def __call__(
        self,
        evidence: ProviderIsolationBundleCleanupEvidence,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class ProviderIsolationBundleScratchCleanup:
    """Completed deletion of one exact, fully proved scratch subtree."""

    cleaned: Literal[True]
    removed_entry_count: int


@dataclass(frozen=True, slots=True)
class _ScratchCleanupEntry:
    """One descriptor-relative scratch entry captured for a two-pass proof."""

    relative_parts: tuple[str, ...]
    device: int
    inode: int
    mount_id: int
    mode_type: int
    link_count: int


def capture_active_bundle_from_authority(
    *,
    authority: object,
) -> ProviderIsolationBundleCapture:
    """Capture with the exact authority path and declared byte bound."""

    _require_result_broker_authority(authority)
    source_binding = _derive_capture_source_authority_binding(authority)
    capture = capture_active_bundle(
        scratch_directory_fd=authority.scratch_fd,
        active_basename=authority.active_basename,
        expected_scratch_mount_id=authority.scratch_identity.mount_id,
        max_bytes=authority.result_bundle_max_bytes,
    )
    _require_result_broker_authority(authority)
    if _derive_capture_source_authority_binding(authority) != source_binding:
        raise TypeError("capture authority binding changed during capture")
    binding = _derive_bound_capture_binding(
        capture,
        source_authority_binding=source_binding,
    )
    return ProviderIsolationBundleCapture(
        classification=capture.classification,
        data=capture.data,
        digest=capture.digest,
        size_bytes=capture.size_bytes,
        reason=capture.reason,
        _source_authority_binding=source_binding,
        _binding=binding,
        _token=_BOUND_CAPTURE_TOKEN,
    )


def create_bundle_transfer_request_from_authority(
    *,
    authority: object,
    capture: ProviderIsolationBundleCapture,
) -> ProviderIsolationBundleTransferRequest:
    """Bind publication fields to one exact post-quiescence authority."""

    _require_result_broker_authority(authority)
    if not isinstance(capture, ProviderIsolationBundleCapture):
        raise TypeError("capture must be ProviderIsolationBundleCapture")
    _validate_capture_shape(capture)
    source_binding = _derive_capture_source_authority_binding(authority)
    if (
        capture._token is not _BOUND_CAPTURE_TOKEN
        or capture._source_authority_binding is None
        or capture._binding is None
    ):
        raise TypeError(
            "publication requires an authority-bound capture"
        )
    if capture._source_authority_binding != source_binding:
        raise TypeError("capture authority binding changed")
    if (
        capture.classification == "captured"
        and capture.size_bytes is not None
        and capture.size_bytes > authority.result_bundle_max_bytes
    ):
        raise TypeError("capture exceeds the authority byte bound")
    capture_binding = _derive_bound_capture_binding(
        capture,
        source_authority_binding=source_binding,
    )
    if capture._binding != capture_binding:
        raise TypeError("capture binding changed")
    binding = _derive_transfer_request_authority_binding(
        runtime_root_fd=authority.runtime_fd,
        expected_runtime_mount_id=authority.runtime_identity.mount_id,
        invocation_identity=authority.invocation_identity,
        scope=authority.request.aggregate_scope,
        ordinal=authority.request.ordinal,
        target_relative_path=authority.target_runtime_relpath,
    )
    request_capture_binding = _derive_request_capture_binding(
        request_authority_binding=binding,
        capture_source_authority_binding=source_binding,
        capture_binding=capture_binding,
    )
    return ProviderIsolationBundleTransferRequest(
        runtime_root_fd=authority.runtime_fd,
        expected_runtime_mount_id=authority.runtime_identity.mount_id,
        invocation_identity=authority.invocation_identity,
        scope=authority.request.aggregate_scope,
        ordinal=authority.request.ordinal,
        target_relative_path=authority.target_runtime_relpath,
        capture=capture,
        _authority_binding=binding,
        _capture_binding=capture_binding,
        _request_capture_binding=request_capture_binding,
        _token=_TRANSFER_REQUEST_TOKEN,
    )


def _require_result_broker_authority(authority: object) -> None:
    from orchestrator.providers.isolation_backend import (
        PinnedProviderResultBrokerAuthorities,
    )

    if type(authority) is not PinnedProviderResultBrokerAuthorities:
        raise TypeError(
            "authority must be PinnedProviderResultBrokerAuthorities"
        )
    authority.revalidate()
    _require_scratch_root_binding(
        runtime_root_fd=authority.runtime_fd,
        expected_runtime_mount_id=authority.runtime_identity.mount_id,
        scratch_directory_fd=authority.scratch_fd,
        scratch_relative_path=authority.scratch_relpath,
        expected_scratch_identity=authority.scratch_identity,
    )


def _derive_capture_source_authority_binding(authority: object) -> str:
    request_binding = _derive_transfer_request_authority_binding(
        runtime_root_fd=authority.runtime_fd,
        expected_runtime_mount_id=authority.runtime_identity.mount_id,
        invocation_identity=authority.invocation_identity,
        scope=authority.request.aggregate_scope,
        ordinal=authority.request.ordinal,
        target_relative_path=authority.target_runtime_relpath,
    )
    document = {
        "schema_version": (
            "provider_isolation_bundle_capture_source_authority.v1"
        ),
        "request_authority_binding": request_binding,
        "scratch_relative_path": authority.scratch_relpath,
        "scratch_device": authority.scratch_identity.device,
        "scratch_inode": authority.scratch_identity.inode,
        "scratch_mount_id": authority.scratch_identity.mount_id,
        "active_basename": authority.active_basename,
        "result_bundle_max_bytes": authority.result_bundle_max_bytes,
    }
    return f"sha256:{sha256(canonical_isolation_json_bytes(document)).hexdigest()}"


def _derive_bound_capture_binding(
    capture: ProviderIsolationBundleCapture,
    *,
    source_authority_binding: str,
) -> str:
    document = {
        "schema_version": "provider_isolation_bound_bundle_capture.v1",
        "source_authority_binding": source_authority_binding,
        "classification": capture.classification,
        "digest": capture.digest,
        "size_bytes": capture.size_bytes,
        "reason": capture.reason,
    }
    return f"sha256:{sha256(canonical_isolation_json_bytes(document)).hexdigest()}"


def _derive_request_capture_binding(
    *,
    request_authority_binding: str,
    capture_source_authority_binding: str,
    capture_binding: str,
) -> str:
    document = {
        "schema_version": "provider_isolation_request_capture_binding.v1",
        "request_authority_binding": request_authority_binding,
        "capture_source_authority_binding": (
            capture_source_authority_binding
        ),
        "capture_binding": capture_binding,
    }
    return f"sha256:{sha256(canonical_isolation_json_bytes(document)).hexdigest()}"


def cleanup_invocation_scratch_after_acknowledgement(
    *,
    runtime_root_fd: int,
    expected_runtime_mount_id: int,
    scratch_directory_fd: int,
    scratch_relative_path: str,
    expected_scratch_identity: RuntimeAuthorityObjectIdentity,
    evidence: ProviderIsolationBundleCleanupEvidence,
    acknowledgement: ProviderIsolationBundleScratchCleanupAcknowledgement,
) -> ProviderIsolationBundleScratchCleanup:
    """Delete one exact quiescent scratch tree after evidence acknowledgement.

    The acknowledgement is an external lifecycle decision.  After it returns
    exactly ``True``, the broker proves the entire tree twice without mutation,
    then revalidates every descriptor-relative entry immediately before
    deleting it.
    """

    _validate_scratch_cleanup_arguments(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_runtime_mount_id,
        scratch_directory_fd=scratch_directory_fd,
        scratch_relative_path=scratch_relative_path,
        expected_scratch_identity=expected_scratch_identity,
        evidence=evidence,
        acknowledgement=acknowledgement,
    )
    _require_scratch_cleanup_acknowledgement(acknowledgement, evidence)

    first_proof = _prove_scratch_cleanup_tree(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_runtime_mount_id,
        scratch_directory_fd=scratch_directory_fd,
        scratch_relative_path=scratch_relative_path,
        expected_scratch_identity=expected_scratch_identity,
    )
    second_proof = _prove_scratch_cleanup_tree(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_runtime_mount_id,
        scratch_directory_fd=scratch_directory_fd,
        scratch_relative_path=scratch_relative_path,
        expected_scratch_identity=expected_scratch_identity,
    )
    if second_proof != first_proof:
        raise _broker_error("scratch tree changed between cleanup proofs")

    _require_scratch_root_binding(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_runtime_mount_id,
        scratch_directory_fd=scratch_directory_fd,
        scratch_relative_path=scratch_relative_path,
        expected_scratch_identity=expected_scratch_identity,
    )
    for entry in second_proof:
        _delete_proved_scratch_entry(
            scratch_directory_fd=scratch_directory_fd,
            expected_mount_id=expected_scratch_identity.mount_id,
            entry=entry,
        )

    parent_fd, linked_fd, basename = _open_linked_scratch_root(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_runtime_mount_id,
        scratch_directory_fd=scratch_directory_fd,
        scratch_relative_path=scratch_relative_path,
        expected_scratch_identity=expected_scratch_identity,
    )
    try:
        try:
            remaining = os.listdir(linked_fd)
        except OSError as exc:
            raise _broker_error(
                "proved scratch root cannot be enumerated before removal"
            ) from exc
        if remaining:
            raise _broker_error(
                "scratch root contains an entry absent from the cleanup proof"
            )
        try:
            os.rmdir(basename, dir_fd=parent_fd)
        except OSError as exc:
            raise _broker_error("exact scratch root removal failed") from exc
        _fsync_directory(parent_fd)
    finally:
        os.close(linked_fd)
        os.close(parent_fd)

    return ProviderIsolationBundleScratchCleanup(
        cleaned=True,
        removed_entry_count=len(second_proof),
    )


def derive_bundle_transfer_paths(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
) -> ProviderIsolationBundleTransferPaths:
    """Derive ASCII broker paths from canonical attempt identity."""

    _validate_transfer_identity(request)
    identity = canonical_isolation_json_bytes(
        {
            "schema_version": "provider_isolation_bundle_transfer_path.v1",
            "invocation_identity": request.invocation_identity,
            "scope": list(request.scope),
            "ordinal": request.ordinal,
            "target_path": request.target_relative_path,
        }
    )
    key = sha256(identity).hexdigest()
    base = f"{_BROKER_ROOT}/{_TRANSFER_ROOT}/{key[:2]}/{key}"
    return ProviderIsolationBundleTransferPaths(
        journal_relative_path=f"{base}/{_JOURNAL_NAME}",
        staged_relative_path=f"{base}/{_STAGED_NAME}",
        target_relative_path=request.target_relative_path,
        archive_relative_path=f"{base}/{_ARCHIVE_NAME}",
    )


def prepare_and_publish_bundle_transfer(
    request: ProviderIsolationBundleTransferRequest,
) -> ProviderIsolationBundleTransferRecord | None:
    """Durably stage and no-replace publish one captured bundle."""

    _validate_transfer_request(request)
    paths = derive_bundle_transfer_paths(request)
    _validate_runtime_root(request)
    if request.capture.classification != "captured":
        _require_noncaptured_shape(request.capture)
        existing = reconcile_bundle_transfer(request)
        if existing is not None:
            raise _broker_error(
                "a noncaptured outcome conflicts with an existing transfer"
            )
        return None

    _require_captured_shape(request.capture)
    transfer_dir_fd = _open_transfer_directory_if_present(request, paths)
    target_parent_fd = -1
    try:
        if transfer_dir_fd is not None:
            existing_journal = _read_journal_if_present(
                request,
                paths,
                transfer_dir_fd,
            )
            if existing_journal is not None:
                existing_document = existing_journal.to_dict()
                if (
                    existing_document["bundle_digest"]
                    != request.capture.digest
                    or existing_document["bundle_size"]
                    != request.capture.size_bytes
                ):
                    raise _broker_error(
                        "captured bundle conflicts with durable transfer"
                    )
                return reconcile_bundle_transfer(request)

        # Prove product-visible ancestry and target absence before creating
        # any private transfer namespace.
        target_parent_fd = _open_parent_directory(
            request,
            paths.target_relative_path,
        )
        target_name = _target_basename(paths.target_relative_path)
        _require_absent_at(target_parent_fd, target_name, "canonical target")
        if transfer_dir_fd is None:
            transfer_dir_fd = _open_transfer_directory(
                request,
                paths,
                create=True,
            )
        _require_known_transfer_directory_entries(transfer_dir_fd, set())
        _require_absent_at(
            transfer_dir_fd,
            _STAGED_NAME,
            "staged bundle",
        )
        _require_absent_at(
            transfer_dir_fd,
            _ARCHIVE_NAME,
            "bundle archive",
        )
        staged_identity = _write_staged_bundle(
            request,
            paths,
            transfer_dir_fd,
        )
        target_identity = dict(staged_identity)
        target_identity["path"] = paths.target_relative_path
        prepared_document: dict[str, Any] = {
            "schema_version": _TRANSFER_SCHEMA_VERSION,
            "state": "prepared",
            "invocation_identity": request.invocation_identity,
            "scope": list(request.scope),
            "ordinal": request.ordinal,
            "staged_identity": staged_identity,
            "target_identity": target_identity,
            "bundle_digest": request.capture.digest,
            "bundle_size": request.capture.size_bytes,
        }
        prepared_bytes = _canonical_validated_journal(prepared_document)
        _advance_journal(
            transfer_dir_fd,
            journal_name=_JOURNAL_NAME,
            document=prepared_document,
            expected_previous_bytes=None,
            expected_mount_id=request.expected_runtime_mount_id,
        )
        _rename_noreplace(
            transfer_dir_fd,
            _STAGED_NAME,
            target_parent_fd,
            target_name,
        )
        _fsync_directory(transfer_dir_fd)
        _fsync_directory(target_parent_fd)
        if not _validate_location_if_present(
            target_parent_fd,
            target_name,
            target_identity,
            prepared_document,
            request.expected_runtime_mount_id,
        ):
            raise _broker_error(
                "canonical target disappeared after publication"
            )
        published_document = dict(prepared_document)
        published_document["state"] = "published"
        _advance_journal(
            transfer_dir_fd,
            journal_name=_JOURNAL_NAME,
            document=published_document,
            expected_previous_bytes=prepared_bytes,
            expected_mount_id=request.expected_runtime_mount_id,
        )
        expected_published = _record_from_document(
            paths,
            published_document,
        )
        reconciled = reconcile_bundle_transfer(request)
        if (
            reconciled is None
            or reconciled.state != "published"
            or reconciled.canonical_json != expected_published.canonical_json
        ):
            raise _broker_error(
                "published transfer could not be reconciled"
            )
        return reconciled
    except ProviderIsolationBundleBrokerError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise _broker_error("bundle publication failed") from exc
    finally:
        if target_parent_fd >= 0:
            os.close(target_parent_fd)
        if transfer_dir_fd is not None:
            os.close(transfer_dir_fd)


def record_bundle_transfer_validation(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
    *,
    contract_digest: str,
    disposition: Literal["valid", "invalid"],
    normalized_value_digest: str | None,
) -> ProviderIsolationBundleTransferRecord:
    """Persist exactly one idempotent typed-validation outcome."""

    _require_digest(contract_digest, "contract_digest")
    if disposition not in {"valid", "invalid"}:
        raise TypeError("disposition must be 'valid' or 'invalid'")
    if disposition == "valid":
        if normalized_value_digest is None:
            raise TypeError(
                "valid disposition requires normalized_value_digest"
            )
        _require_digest(normalized_value_digest, "normalized_value_digest")
    elif normalized_value_digest is not None:
        raise TypeError(
            "invalid disposition forbids normalized_value_digest"
        )

    current = reconcile_bundle_transfer(request)
    if current is None:
        raise _broker_error("validation requires a published transfer")
    current_document = current.to_dict()
    expected_fields: dict[str, Any] = {
        "contract_digest": contract_digest,
        "validation_disposition": disposition,
    }
    if normalized_value_digest is not None:
        expected_fields["normalized_value_digest"] = normalized_value_digest
    if current.state == "validated":
        if all(
            current_document.get(name) == value
            for name, value in expected_fields.items()
        ) and set(current_document).isdisjoint(
            {"normalized_value_digest"} - set(expected_fields)
        ):
            return current
        raise _broker_error("validation outcome conflicts with durable journal")
    if current.state != "published":
        raise _broker_error(
            f"validation is illegal from transfer state {current.state!r}"
        )

    next_document = dict(current_document)
    next_document["state"] = "validated"
    next_document.update(expected_fields)
    transfer_dir_fd = _open_transfer_directory(
        request,
        derive_bundle_transfer_paths(request),
        create=False,
    )
    try:
        _advance_journal(
            transfer_dir_fd,
            journal_name=_JOURNAL_NAME,
            document=next_document,
            expected_previous_bytes=current.canonical_json,
            expected_mount_id=request.expected_runtime_mount_id,
        )
    finally:
        os.close(transfer_dir_fd)
    return _record_from_document(
        derive_bundle_transfer_paths(request),
        next_document,
    )


def rotate_invalid_bundle_transfer(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
    *,
    acknowledgement: ProviderIsolationBundleRotationAcknowledgement,
) -> ProviderIsolationBundleTransferRecord:
    """Rotate one invalid target after an explicit caller acknowledgement."""

    if not callable(acknowledgement):
        raise TypeError("acknowledgement must be callable")
    current = reconcile_bundle_transfer(request)
    if current is None:
        raise _broker_error("rotation requires a validated transfer")
    document = current.to_dict()
    if current.state == "rotated":
        return current
    if (
        current.state != "validated"
        or document.get("validation_disposition") != "invalid"
    ):
        raise _broker_error("only a validated invalid transfer may rotate")
    _require_positive_acknowledgement(acknowledgement, current)

    # The callback is outside broker authority. Re-prove the exact target before
    # making the durable rotation decision.
    reproved = reconcile_bundle_transfer(request)
    if reproved is None or reproved.canonical_json != current.canonical_json:
        raise _broker_error("transfer changed during rotation acknowledgement")
    paths = derive_bundle_transfer_paths(request)
    archive_identity = dict(document["target_identity"])
    archive_identity["path"] = paths.archive_relative_path
    pending_document = dict(document)
    pending_document["state"] = "rotation_pending"
    pending_document["archive_identity"] = archive_identity
    transfer_dir_fd = _open_transfer_directory(
        request,
        paths,
        create=False,
    )
    target_parent_fd = _open_parent_directory(
        request,
        paths.target_relative_path,
    )
    try:
        _advance_journal(
            transfer_dir_fd,
            journal_name=_JOURNAL_NAME,
            document=pending_document,
            expected_previous_bytes=current.canonical_json,
            expected_mount_id=request.expected_runtime_mount_id,
        )
        _rename_noreplace(
            target_parent_fd,
            _target_basename(paths.target_relative_path),
            transfer_dir_fd,
            _ARCHIVE_NAME,
        )
        _fsync_directory(target_parent_fd)
        _fsync_directory(transfer_dir_fd)
        rotated_document = dict(pending_document)
        rotated_document["state"] = "rotated"
        _advance_journal(
            transfer_dir_fd,
            journal_name=_JOURNAL_NAME,
            document=rotated_document,
            expected_previous_bytes=_canonical_validated_journal(
                pending_document
            ),
            expected_mount_id=request.expected_runtime_mount_id,
        )
        return _record_from_document(paths, rotated_document)
    except ProviderIsolationBundleBrokerError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise _broker_error("invalid bundle rotation failed") from exc
    finally:
        os.close(target_parent_fd)
        os.close(transfer_dir_fd)


def reconcile_bundle_transfer(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
) -> ProviderIsolationBundleTransferRecord | None:
    """Validate and monotonically complete one exact durable transfer."""

    paths = derive_bundle_transfer_paths(request)
    _validate_runtime_root(request)
    target_parent_fd = _open_parent_directory(
        request,
        paths.target_relative_path,
    )
    transfer_dir_fd = _open_transfer_directory_if_present(request, paths)
    try:
        target_name = _target_basename(paths.target_relative_path)
        if transfer_dir_fd is None:
            _require_absent_at(
                target_parent_fd,
                target_name,
                "unexplained canonical target",
            )
            return None
        journal = _read_journal_if_present(
            request,
            paths,
            transfer_dir_fd,
        )
        if journal is None:
            _require_known_transfer_directory_entries(transfer_dir_fd, set())
            _require_absent_at(
                transfer_dir_fd,
                _STAGED_NAME,
                "unexplained staged bundle",
            )
            _require_absent_at(
                transfer_dir_fd,
                _ARCHIVE_NAME,
                "unexplained bundle archive",
            )
            _require_absent_at(
                target_parent_fd,
                target_name,
                "unexplained canonical target",
            )
            return None

        document = journal.to_dict()
        allowed_entries = {_JOURNAL_NAME}
        if _entry_exists(transfer_dir_fd, _STAGED_NAME):
            allowed_entries.add(_STAGED_NAME)
        if _entry_exists(transfer_dir_fd, _ARCHIVE_NAME):
            allowed_entries.add(_ARCHIVE_NAME)
        _require_known_transfer_directory_entries(
            transfer_dir_fd,
            allowed_entries,
        )
        stage_present = _validate_location_if_present(
            transfer_dir_fd,
            _STAGED_NAME,
            document["staged_identity"],
            document,
            request.expected_runtime_mount_id,
        )
        target_present = _validate_location_if_present(
            target_parent_fd,
            target_name,
            document["target_identity"],
            document,
            request.expected_runtime_mount_id,
        )
        archive_identity = document.get("archive_identity")
        archive_present = _validate_location_if_present(
            transfer_dir_fd,
            _ARCHIVE_NAME,
            archive_identity,
            document,
            request.expected_runtime_mount_id,
        )
        state = journal.state
        if state == "prepared":
            if archive_present or stage_present == target_present:
                raise _broker_error(
                    "prepared requires exactly one staged or target location"
                )
            if stage_present:
                _rename_noreplace(
                    transfer_dir_fd,
                    _STAGED_NAME,
                    target_parent_fd,
                    target_name,
                )
                _fsync_directory(transfer_dir_fd)
                _fsync_directory(target_parent_fd)
            next_document = dict(document)
            next_document["state"] = "published"
            _advance_journal(
                transfer_dir_fd,
                journal_name=_JOURNAL_NAME,
                document=next_document,
                expected_previous_bytes=journal.canonical_json,
                expected_mount_id=request.expected_runtime_mount_id,
            )
            return _record_from_document(paths, next_document)
        if state in {"published", "validated"}:
            if stage_present or archive_present or not target_present:
                raise _broker_error(
                    f"{state} requires only the exact canonical target"
                )
            return journal
        if state == "rotation_pending":
            if stage_present or target_present == archive_present:
                raise _broker_error(
                    "rotation_pending requires exactly one target or archive"
                )
            if target_present:
                _rename_noreplace(
                    target_parent_fd,
                    target_name,
                    transfer_dir_fd,
                    _ARCHIVE_NAME,
                )
                _fsync_directory(target_parent_fd)
                _fsync_directory(transfer_dir_fd)
            next_document = dict(document)
            next_document["state"] = "rotated"
            _advance_journal(
                transfer_dir_fd,
                journal_name=_JOURNAL_NAME,
                document=next_document,
                expected_previous_bytes=journal.canonical_json,
                expected_mount_id=request.expected_runtime_mount_id,
            )
            return _record_from_document(paths, next_document)
        if state == "rotated":
            if stage_present or target_present or not archive_present:
                raise _broker_error("rotated requires only the exact archive")
            return journal
        raise _broker_error(f"unknown transfer state {state!r}")
    except ProviderIsolationBundleBrokerError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise _broker_error("bundle reconciliation failed") from exc
    finally:
        os.close(target_parent_fd)
        if transfer_dir_fd is not None:
            os.close(transfer_dir_fd)


def _validate_scratch_cleanup_arguments(
    *,
    runtime_root_fd: int,
    expected_runtime_mount_id: int,
    scratch_directory_fd: int,
    scratch_relative_path: str,
    expected_scratch_identity: RuntimeAuthorityObjectIdentity,
    evidence: ProviderIsolationBundleCleanupEvidence,
    acknowledgement: ProviderIsolationBundleScratchCleanupAcknowledgement,
) -> None:
    if type(runtime_root_fd) is not int or runtime_root_fd < 0:
        raise TypeError("runtime_root_fd must be an open descriptor")
    if (
        type(expected_runtime_mount_id) is not int
        or expected_runtime_mount_id <= 0
    ):
        raise TypeError("expected_runtime_mount_id must be positive")
    if type(scratch_directory_fd) is not int or scratch_directory_fd < 0:
        raise TypeError("scratch_directory_fd must be an open descriptor")
    scratch_parts = _parse_runtime_relpath(scratch_relative_path)
    if (
        len(scratch_parts) != 2
        or scratch_parts[0] != "provider-invocation-scratch"
        or len(scratch_parts[1]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in scratch_parts[1]
        )
    ):
        raise _broker_error(
            "scratch cleanup authority is not one invocation scratch root"
        )
    if not isinstance(
        expected_scratch_identity,
        RuntimeAuthorityObjectIdentity,
    ):
        raise TypeError(
            "expected_scratch_identity must be RuntimeAuthorityObjectIdentity"
        )
    if (
        not isinstance(expected_scratch_identity.path, str)
        or not expected_scratch_identity.path
        or type(expected_scratch_identity.device) is not int
        or expected_scratch_identity.device < 0
        or type(expected_scratch_identity.inode) is not int
        or expected_scratch_identity.inode <= 0
        or type(expected_scratch_identity.mount_id) is not int
        or expected_scratch_identity.mount_id <= 0
    ):
        raise TypeError("expected_scratch_identity fields are invalid")
    if expected_scratch_identity.mount_id != expected_runtime_mount_id:
        raise _broker_error(
            "scratch cleanup authority crossed the runtime mount boundary"
        )
    _validate_scratch_cleanup_evidence(evidence)
    if not callable(acknowledgement):
        raise TypeError("acknowledgement must be callable")


def _validate_scratch_cleanup_evidence(
    evidence: ProviderIsolationBundleCleanupEvidence,
) -> None:
    if isinstance(evidence, ProviderIsolationBundleCapture):
        _validate_capture_shape(evidence)
        return
    if not isinstance(evidence, ProviderIsolationBundleTransferRecord):
        raise TypeError(
            "evidence must be a bundle capture or transfer record"
        )
    if (
        not isinstance(evidence.canonical_json, bytes)
        or len(evidence.canonical_json) > 128 * 1024
    ):
        raise TypeError("transfer evidence is not bounded canonical JSON")
    try:
        document = json.loads(evidence.canonical_json)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TypeError("transfer evidence is not strict JSON") from exc
    if not isinstance(document, dict):
        raise TypeError("transfer evidence root must be an object")
    if _canonical_validated_journal(document) != evidence.canonical_json:
        raise TypeError("transfer evidence is not canonical")
    if evidence.state != document["state"]:
        raise TypeError("transfer evidence state binding changed")
    if (
        evidence.staged_relative_path
        != document["staged_identity"]["path"]
        or evidence.target_relative_path
        != document["target_identity"]["path"]
    ):
        raise TypeError("transfer evidence path binding changed")
    archive = document.get("archive_identity")
    if archive is not None:
        if evidence.archive_relative_path != archive["path"]:
            raise TypeError("transfer evidence archive binding changed")
    _parse_runtime_relpath(evidence.journal_relative_path)
    _parse_runtime_relpath(evidence.staged_relative_path)
    _parse_runtime_relpath(evidence.target_relative_path)
    _parse_runtime_relpath(evidence.archive_relative_path)


def _require_scratch_cleanup_acknowledgement(
    acknowledgement: ProviderIsolationBundleScratchCleanupAcknowledgement,
    evidence: ProviderIsolationBundleCleanupEvidence,
) -> None:
    try:
        accepted = acknowledgement(evidence)
    except BaseException as exc:
        raise _broker_error("scratch cleanup acknowledgement failed") from exc
    if accepted is not True:
        raise _broker_error("caller did not acknowledge scratch cleanup")


def _prove_scratch_cleanup_tree(
    *,
    runtime_root_fd: int,
    expected_runtime_mount_id: int,
    scratch_directory_fd: int,
    scratch_relative_path: str,
    expected_scratch_identity: RuntimeAuthorityObjectIdentity,
) -> tuple[_ScratchCleanupEntry, ...]:
    _require_scratch_root_binding(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_runtime_mount_id,
        scratch_directory_fd=scratch_directory_fd,
        scratch_relative_path=scratch_relative_path,
        expected_scratch_identity=expected_scratch_identity,
    )
    entries: list[_ScratchCleanupEntry] = []
    budget = [0]

    def visit(directory_fd: int, prefix: tuple[str, ...], depth: int) -> None:
        if depth > MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH:
            raise _broker_error("scratch cleanup tree exceeds depth bound")
        try:
            names = tuple(sorted(os.listdir(directory_fd)))
        except OSError as exc:
            raise _broker_error(
                "scratch cleanup directory cannot be enumerated"
            ) from exc
        for name in names:
            budget[0] += 1
            if budget[0] > MAX_RUNTIME_AUTHORITY_ENTRY_COUNT:
                raise _broker_error("scratch cleanup tree exceeds entry bound")
            pin_fd = -1
            child_fd = -1
            try:
                try:
                    pin_fd = os.open(
                        name,
                        os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=directory_fd,
                    )
                except OSError as exc:
                    raise _broker_error(
                        "scratch cleanup entry could not be pinned"
                    ) from exc
                observed = os.fstat(pin_fd)
                mount_id = _statx_mount_id(pin_fd)
                if (
                    observed.st_dev != expected_scratch_identity.device
                    or mount_id != expected_scratch_identity.mount_id
                ):
                    raise _broker_error(
                        "scratch cleanup entry crossed an authority boundary"
                    )
                mode_type = stat.S_IFMT(observed.st_mode)
                relative_parts = (*prefix, name)
                if stat.S_ISDIR(observed.st_mode):
                    try:
                        child_fd = os.open(
                            name,
                            os.O_RDONLY
                            | os.O_DIRECTORY
                            | os.O_NOFOLLOW
                            | os.O_CLOEXEC,
                            dir_fd=directory_fd,
                        )
                    except OSError as exc:
                        raise _broker_error(
                            "scratch cleanup directory could not be opened"
                        ) from exc
                    _require_cleanup_entry_binding(
                        parent_fd=directory_fd,
                        basename=name,
                        pin_fd=child_fd,
                        device=observed.st_dev,
                        inode=observed.st_ino,
                        mount_id=mount_id,
                        mode_type=mode_type,
                        link_count=observed.st_nlink,
                        deleting=False,
                    )
                    visit(child_fd, relative_parts, depth + 1)
                _require_cleanup_entry_binding(
                    parent_fd=directory_fd,
                    basename=name,
                    pin_fd=pin_fd,
                    device=observed.st_dev,
                    inode=observed.st_ino,
                    mount_id=mount_id,
                    mode_type=mode_type,
                    link_count=observed.st_nlink,
                    deleting=False,
                )
                entries.append(
                    _ScratchCleanupEntry(
                        relative_parts=relative_parts,
                        device=observed.st_dev,
                        inode=observed.st_ino,
                        mount_id=mount_id,
                        mode_type=mode_type,
                        link_count=observed.st_nlink,
                    )
                )
            except MountIdentityUnavailable as exc:
                raise _broker_error(
                    "scratch cleanup mount identity is unavailable"
                ) from exc
            finally:
                if child_fd >= 0:
                    os.close(child_fd)
                if pin_fd >= 0:
                    os.close(pin_fd)

    try:
        root_view_fd = os.open(
            ".",
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | os.O_CLOEXEC,
            dir_fd=scratch_directory_fd,
        )
    except OSError as exc:
        raise _broker_error(
            "held scratch root cannot be opened for cleanup proof"
        ) from exc
    try:
        root_view = os.fstat(root_view_fd)
        if (
            root_view.st_dev != expected_scratch_identity.device
            or root_view.st_ino != expected_scratch_identity.inode
            or _statx_mount_id(root_view_fd)
            != expected_scratch_identity.mount_id
        ):
            raise _broker_error("scratch cleanup proof root identity changed")
        visit(root_view_fd, (), 0)
    except MountIdentityUnavailable as exc:
        raise _broker_error(
            "scratch cleanup proof root mount identity is unavailable"
        ) from exc
    finally:
        os.close(root_view_fd)
    _require_scratch_root_binding(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_runtime_mount_id,
        scratch_directory_fd=scratch_directory_fd,
        scratch_relative_path=scratch_relative_path,
        expected_scratch_identity=expected_scratch_identity,
    )
    return tuple(entries)


def _require_scratch_root_binding(
    *,
    runtime_root_fd: int,
    expected_runtime_mount_id: int,
    scratch_directory_fd: int,
    scratch_relative_path: str,
    expected_scratch_identity: RuntimeAuthorityObjectIdentity,
) -> None:
    parent_fd, linked_fd, _basename = _open_linked_scratch_root(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_runtime_mount_id,
        scratch_directory_fd=scratch_directory_fd,
        scratch_relative_path=scratch_relative_path,
        expected_scratch_identity=expected_scratch_identity,
    )
    os.close(linked_fd)
    os.close(parent_fd)


def _open_linked_scratch_root(
    *,
    runtime_root_fd: int,
    expected_runtime_mount_id: int,
    scratch_directory_fd: int,
    scratch_relative_path: str,
    expected_scratch_identity: RuntimeAuthorityObjectIdentity,
) -> tuple[int, int, str]:
    _require_directory_fd(runtime_root_fd, expected_runtime_mount_id)
    _require_directory_fd(
        scratch_directory_fd,
        expected_scratch_identity.mount_id,
    )
    _require_private_directory_fd(scratch_directory_fd)
    try:
        held = os.fstat(scratch_directory_fd)
    except OSError as exc:
        raise _broker_error("held scratch identity is unavailable") from exc
    if (
        held.st_dev != expected_scratch_identity.device
        or held.st_ino != expected_scratch_identity.inode
    ):
        raise _broker_error("held scratch identity changed")

    parts = _parse_runtime_relpath(scratch_relative_path)
    parent_fd = _open_directory_chain(
        runtime_root_fd,
        parts[:-1],
        expected_mount_id=expected_runtime_mount_id,
        create=False,
        private=False,
    )
    linked_fd = -1
    try:
        try:
            linked_fd = os.open(
                parts[-1],
                os.O_RDONLY
                | os.O_DIRECTORY
                | os.O_NOFOLLOW
                | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise _broker_error(
                "linked scratch root could not be opened"
            ) from exc
        linked = os.fstat(linked_fd)
        linked_mount_id = _statx_mount_id(linked_fd)
        if (
            not stat.S_ISDIR(linked.st_mode)
            or linked.st_dev != expected_scratch_identity.device
            or linked.st_ino != expected_scratch_identity.inode
            or linked_mount_id != expected_scratch_identity.mount_id
            or not _same_object(linked, held)
        ):
            raise _broker_error(
                "linked scratch root differs from held authority"
            )
        _require_private_directory_fd(linked_fd)
        return parent_fd, linked_fd, parts[-1]
    except MountIdentityUnavailable as exc:
        raise _broker_error(
            "linked scratch mount identity is unavailable"
        ) from exc
    except BaseException:
        if linked_fd >= 0:
            os.close(linked_fd)
        os.close(parent_fd)
        raise


def _require_cleanup_entry_binding(
    *,
    parent_fd: int,
    basename: str,
    pin_fd: int,
    device: int,
    inode: int,
    mount_id: int,
    mode_type: int,
    link_count: int,
    deleting: bool,
) -> None:
    try:
        pinned = os.fstat(pin_fd)
        linked = os.stat(
            basename,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        pinned_mount_id = _statx_mount_id(pin_fd)
    except (OSError, MountIdentityUnavailable) as exc:
        raise _broker_error(
            "scratch cleanup entry identity is unavailable"
        ) from exc
    expected = (device, inode, mount_id, mode_type)
    if (
        (
            pinned.st_dev,
            pinned.st_ino,
            pinned_mount_id,
            stat.S_IFMT(pinned.st_mode),
        )
        != expected
        or (
            linked.st_dev,
            linked.st_ino,
            pinned_mount_id,
            stat.S_IFMT(linked.st_mode),
        )
        != expected
    ):
        raise _broker_error("scratch cleanup entry identity changed")
    if not deleting and (
        pinned.st_nlink != link_count or linked.st_nlink != link_count
    ):
        raise _broker_error("scratch cleanup entry link count changed")


def _delete_proved_scratch_entry(
    *,
    scratch_directory_fd: int,
    expected_mount_id: int,
    entry: _ScratchCleanupEntry,
) -> None:
    parent_fd = _open_directory_chain(
        scratch_directory_fd,
        entry.relative_parts[:-1],
        expected_mount_id=expected_mount_id,
        create=False,
        private=False,
    )
    pin_fd = -1
    try:
        basename = entry.relative_parts[-1]
        try:
            pin_fd = os.open(
                basename,
                os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise _broker_error(
                "proved scratch cleanup entry is unavailable"
            ) from exc
        _require_cleanup_entry_binding(
            parent_fd=parent_fd,
            basename=basename,
            pin_fd=pin_fd,
            device=entry.device,
            inode=entry.inode,
            mount_id=entry.mount_id,
            mode_type=entry.mode_type,
            link_count=entry.link_count,
            deleting=True,
        )
        quarantine_name = _scratch_cleanup_quarantine_name(entry)
        try:
            _require_absent_at(
                parent_fd,
                quarantine_name,
                "scratch cleanup quarantine",
            )
            _rename_noreplace(
                parent_fd,
                basename,
                parent_fd,
                quarantine_name,
            )
            _fsync_directory(parent_fd)
            _require_cleanup_entry_binding(
                parent_fd=parent_fd,
                basename=quarantine_name,
                pin_fd=pin_fd,
                device=entry.device,
                inode=entry.inode,
                mount_id=entry.mount_id,
                mode_type=entry.mode_type,
                link_count=entry.link_count,
                deleting=True,
            )
            if entry.mode_type == stat.S_IFDIR:
                directory_fd = os.open(
                    quarantine_name,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | os.O_NOFOLLOW
                    | os.O_CLOEXEC,
                    dir_fd=parent_fd,
                )
                try:
                    if os.listdir(directory_fd):
                        raise _broker_error(
                            "proved scratch directory is not empty"
                        )
                finally:
                    os.close(directory_fd)
                os.rmdir(quarantine_name, dir_fd=parent_fd)
            else:
                os.unlink(quarantine_name, dir_fd=parent_fd)
        except ProviderIsolationBundleBrokerError:
            raise
        except OSError as exc:
            raise _broker_error(
                "proved scratch cleanup entry removal failed"
            ) from exc
        _fsync_directory(parent_fd)
    finally:
        if pin_fd >= 0:
            os.close(pin_fd)
        os.close(parent_fd)


def _scratch_cleanup_quarantine_name(entry: _ScratchCleanupEntry) -> str:
    digest = sha256()
    digest.update(b"provider-isolation-scratch-cleanup-quarantine-v1\0")
    for part in entry.relative_parts:
        encoded = os.fsencode(part)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    for value in (
        entry.device,
        entry.inode,
        entry.mount_id,
        entry.mode_type,
        entry.link_count,
    ):
        digest.update(value.to_bytes(16, "big", signed=False))
    return f".provider-cleanup-{digest.hexdigest()}"


def _validate_transfer_request(
    request: ProviderIsolationBundleTransferRequest,
) -> None:
    _validate_transfer_identity(request)
    if not isinstance(request.capture, ProviderIsolationBundleCapture):
        raise TypeError("capture must be ProviderIsolationBundleCapture")
    _validate_capture_shape(request.capture)
    if (
        request.capture._token is not _BOUND_CAPTURE_TOKEN
        or request.capture._source_authority_binding is None
        or request.capture._binding is None
    ):
        raise TypeError("bundle transfer request requires an authority-bound capture")
    observed_capture_binding = _derive_bound_capture_binding(
        request.capture,
        source_authority_binding=(
            request.capture._source_authority_binding
        ),
    )
    if (
        request.capture._binding != observed_capture_binding
        or request._capture_binding != observed_capture_binding
    ):
        raise TypeError("bundle transfer request capture binding changed")
    try:
        observed_binding = _derive_transfer_request_authority_binding(
            runtime_root_fd=request.runtime_root_fd,
            expected_runtime_mount_id=request.expected_runtime_mount_id,
            invocation_identity=request.invocation_identity,
            scope=request.scope,
            ordinal=request.ordinal,
            target_relative_path=request.target_relative_path,
        )
    except ProviderIsolationBundleBrokerError as exc:
        raise TypeError("bundle transfer request authority binding is invalid") from exc
    if request._authority_binding != observed_binding:
        raise TypeError("bundle transfer request authority binding changed")
    observed_request_capture_binding = _derive_request_capture_binding(
        request_authority_binding=observed_binding,
        capture_source_authority_binding=(
            request.capture._source_authority_binding
        ),
        capture_binding=observed_capture_binding,
    )
    if request._request_capture_binding != observed_request_capture_binding:
        raise TypeError("bundle transfer request-capture binding changed")


def _derive_transfer_request_authority_binding(
    *,
    runtime_root_fd: int,
    expected_runtime_mount_id: int,
    invocation_identity: str,
    scope: tuple[str, ...],
    ordinal: int,
    target_relative_path: str,
) -> str:
    """Bind composable request fields to one exact runtime-root object."""

    try:
        observed = os.fstat(runtime_root_fd)
        mount_id = _statx_mount_id(runtime_root_fd)
    except (OSError, MountIdentityUnavailable) as exc:
        raise _broker_error(
            "bundle transfer request authority is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(observed.st_mode)
        or mount_id != expected_runtime_mount_id
    ):
        raise _broker_error("bundle transfer request authority changed")
    document = {
        "schema_version": "provider_isolation_bundle_transfer_authority.v1",
        "runtime_device": observed.st_dev,
        "runtime_inode": observed.st_ino,
        "runtime_mount_id": mount_id,
        "invocation_identity": invocation_identity,
        "scope": list(scope),
        "ordinal": ordinal,
        "target_relative_path": target_relative_path,
    }
    return f"sha256:{sha256(canonical_isolation_json_bytes(document)).hexdigest()}"


def _validate_transfer_identity(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
) -> None:
    if type(request.runtime_root_fd) is not int or request.runtime_root_fd < 0:
        raise TypeError("runtime_root_fd must be an open descriptor")
    if (
        type(request.expected_runtime_mount_id) is not int
        or request.expected_runtime_mount_id <= 0
    ):
        raise TypeError("expected_runtime_mount_id must be positive")
    _require_digest(request.invocation_identity, "invocation_identity")
    if (
        not isinstance(request.scope, tuple)
        or not request.scope
        or len(request.scope) > 128
    ):
        raise TypeError("scope must be a nonempty tuple with at most 128 items")
    for item in request.scope:
        if (
            not isinstance(item, str)
            or not item
            or len(item) > 255
            or "\x00" in item
            or unicodedata.normalize("NFC", item) != item
        ):
            raise TypeError("scope items must be nonempty NFC strings")
        try:
            item.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise TypeError("scope items must be strict UTF-8") from exc
    if (
        type(request.ordinal) is not int
        or request.ordinal <= 0
        or request.ordinal > _MAX_UINT64
    ):
        raise TypeError("ordinal must be a positive unsigned 64-bit integer")
    _parse_runtime_relpath(request.target_relative_path)


def _validate_capture_shape(capture: ProviderIsolationBundleCapture) -> None:
    if capture.classification == "captured":
        _require_captured_shape(capture)
    elif capture.classification in {"missing", "rejected"}:
        _require_noncaptured_shape(capture)
    else:
        raise TypeError("capture classification is not closed")


def _require_captured_shape(capture: ProviderIsolationBundleCapture) -> None:
    if (
        not isinstance(capture.data, bytes)
        or type(capture.size_bytes) is not int
        or capture.size_bytes < 0
        or capture.size_bytes > _MAX_BUNDLE_BYTES
        or capture.size_bytes != len(capture.data)
        or capture.digest != f"sha256:{sha256(capture.data).hexdigest()}"
        or capture.reason is not None
    ):
        raise TypeError("captured bundle fields are inconsistent")


def _require_noncaptured_shape(capture: ProviderIsolationBundleCapture) -> None:
    if (
        capture.data is not None
        or capture.digest is not None
        or capture.size_bytes is not None
        or (
            capture.classification == "missing"
            and capture.reason is not None
        )
        or (
            capture.classification == "rejected"
            and capture.reason
            not in {BUNDLE_REJECTED_REASON, BUNDLE_OVERSIZED_REASON}
        )
    ):
        raise TypeError("noncaptured bundle fields are inconsistent")


def _require_digest(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise TypeError(f"{label} must be one canonical sha256 identity")


def _parse_runtime_relpath(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_PROVIDER_ISOLATION_RUNTIME_RELPATH_LENGTH
        or value.startswith("/")
        or value.endswith("/")
        or "//" in value
        or "\x00" in value
        or unicodedata.normalize("NFC", value) != value
    ):
        raise TypeError("target_relative_path must be canonical and relative")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise TypeError("target_relative_path must be strict UTF-8") from exc
    parts = tuple(value.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise TypeError("target_relative_path may not contain dot components")
    return parts


def _validate_runtime_root(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
) -> None:
    try:
        observed = os.fstat(request.runtime_root_fd)
        mount_id = _statx_mount_id(request.runtime_root_fd)
    except (OSError, MountIdentityUnavailable) as exc:
        raise _broker_error("runtime root authority is unavailable") from exc
    if not stat.S_ISDIR(observed.st_mode):
        raise _broker_error("runtime root descriptor is not a directory")
    if mount_id != request.expected_runtime_mount_id:
        raise _broker_error("runtime root mount identity changed")


def _target_basename(relative_path: str) -> str:
    return _parse_runtime_relpath(relative_path)[-1]


def _open_parent_directory(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
    relative_path: str,
) -> int:
    parts = _parse_runtime_relpath(relative_path)
    return _open_directory_chain(
        request.runtime_root_fd,
        parts[:-1],
        expected_mount_id=request.expected_runtime_mount_id,
        create=False,
        private=False,
    )


def _open_transfer_directory(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
    paths: ProviderIsolationBundleTransferPaths,
    *,
    create: bool,
) -> int:
    parts = _parse_runtime_relpath(paths.journal_relative_path)[:-1]
    return _open_directory_chain(
        request.runtime_root_fd,
        parts,
        expected_mount_id=request.expected_runtime_mount_id,
        create=create,
        private=True,
    )


def _open_transfer_directory_if_present(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
    paths: ProviderIsolationBundleTransferPaths,
) -> int | None:
    try:
        return _open_transfer_directory(request, paths, create=False)
    except ProviderIsolationBundleBrokerError as exc:
        if "directory is absent" in str(exc):
            return None
        raise


def _open_directory_chain(
    root_fd: int,
    parts: tuple[str, ...],
    *,
    expected_mount_id: int,
    create: bool,
    private: bool,
) -> int:
    try:
        current = os.open(
            ".",
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | os.O_CLOEXEC,
            dir_fd=root_fd,
        )
    except OSError as exc:
        raise _broker_error("held runtime root cannot be opened") from exc
    try:
        _require_directory_fd(current, expected_mount_id)
        for part in parts:
            try:
                next_fd = os.open(
                    part,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | os.O_NOFOLLOW
                    | os.O_CLOEXEC,
                    dir_fd=current,
                )
            except FileNotFoundError:
                if not create:
                    raise _broker_error("required broker directory is absent")
                try:
                    os.mkdir(part, 0o700, dir_fd=current)
                    _fsync_directory(current)
                    next_fd = os.open(
                        part,
                        os.O_RDONLY
                        | os.O_DIRECTORY
                        | os.O_NOFOLLOW
                        | os.O_CLOEXEC,
                        dir_fd=current,
                    )
                except OSError as exc:
                    raise _broker_error(
                        "private broker directory creation failed"
                    ) from exc
            except OSError as exc:
                raise _broker_error(
                    "directory traversal rejected a non-directory edge"
                ) from exc
            try:
                _require_directory_fd(next_fd, expected_mount_id)
                if private:
                    _require_private_directory_fd(next_fd)
            except BaseException:
                os.close(next_fd)
                raise
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


def _require_directory_fd(directory_fd: int, expected_mount_id: int) -> None:
    try:
        observed = os.fstat(directory_fd)
        mount_id = _statx_mount_id(directory_fd)
    except (OSError, MountIdentityUnavailable) as exc:
        raise _broker_error("directory identity is unavailable") from exc
    if not stat.S_ISDIR(observed.st_mode):
        raise _broker_error("held traversal edge is not a directory")
    if mount_id != expected_mount_id:
        raise _broker_error("directory traversal crossed a mount boundary")


def _require_private_directory_fd(directory_fd: int) -> None:
    try:
        observed = os.fstat(directory_fd)
    except OSError as exc:
        raise _broker_error("private broker directory identity is unavailable") from exc
    if (
        observed.st_uid != os.geteuid()
        or observed.st_gid != os.getegid()
        or stat.S_IMODE(observed.st_mode) != 0o700
    ):
        raise _broker_error(
            "broker directory is not private to the controller identity"
        )


def _write_staged_bundle(
    request: ProviderIsolationBundleTransferRequest,
    paths: ProviderIsolationBundleTransferPaths,
    transfer_dir_fd: int,
) -> dict[str, Any]:
    data = request.capture.data
    assert data is not None  # validated request invariant
    try:
        fd = os.open(
            _STAGED_NAME,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_CLOEXEC,
            0o600,
            dir_fd=transfer_dir_fd,
        )
    except OSError as exc:
        raise _broker_error("deterministic staged bundle already exists") from exc
    try:
        os.fchmod(fd, 0o600)
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise _broker_error("staged bundle write made no progress")
            offset += written
        os.fsync(fd)
        identity = _file_identity(
            fd,
            paths.staged_relative_path,
            request.expected_runtime_mount_id,
        )
    except BaseException:
        # Never unlink: a partial deterministic stage is ambiguous evidence.
        raise
    finally:
        os.close(fd)
    _fsync_directory(transfer_dir_fd)
    return identity


def _file_identity(
    fd: int,
    path: str,
    expected_mount_id: int,
) -> dict[str, Any]:
    try:
        observed = os.fstat(fd)
        mount_id = _statx_mount_id(fd)
    except (OSError, MountIdentityUnavailable) as exc:
        raise _broker_error("file identity is unavailable") from exc
    if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
        raise _broker_error("bundle authority is not one unaliased regular file")
    if mount_id != expected_mount_id:
        raise _broker_error("bundle authority crossed a mount boundary")
    return {
        "path": path,
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "mount_id": mount_id,
    }


def _canonical_validated_journal(document: Mapping[str, Any]) -> bytes:
    schema = load_provider_isolation_schema(_TRANSFER_SCHEMA_RESOURCE)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if errors:
        raise _broker_error(
            f"transfer journal violates schema: {errors[0].message}"
        )
    try:
        return canonical_isolation_json_bytes(document)
    except (TypeError, ValueError) as exc:
        raise _broker_error("transfer journal is not canonicalizable") from exc


def _advance_journal(
    transfer_dir_fd: int,
    *,
    journal_name: str,
    document: Mapping[str, Any],
    expected_previous_bytes: bytes | None,
    expected_mount_id: int,
) -> bytes:
    encoded = _canonical_validated_journal(document)
    _require_directory_fd(transfer_dir_fd, expected_mount_id)
    current = _read_regular_bytes_if_present(
        transfer_dir_fd,
        journal_name,
        expected_mount_id=expected_mount_id,
        max_bytes=128 * 1024,
    )
    if current != expected_previous_bytes:
        raise _broker_error("durable journal does not match expected predecessor")
    temp_name = f".{journal_name}.next"
    _require_absent_at(transfer_dir_fd, temp_name, "journal staging file")
    try:
        temp_fd = os.open(
            temp_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_CLOEXEC,
            0o600,
            dir_fd=transfer_dir_fd,
        )
    except OSError as exc:
        raise _broker_error("journal staging creation failed") from exc
    try:
        os.fchmod(temp_fd, 0o600)
        offset = 0
        while offset < len(encoded):
            written = os.write(temp_fd, encoded[offset:])
            if written <= 0:
                raise _broker_error("journal write made no progress")
            offset += written
        os.fsync(temp_fd)
        _file_identity(
            temp_fd,
            f".{journal_name}.next",
            expected_mount_id,
        )
    finally:
        os.close(temp_fd)

    # Recheck immediately before the atomic namespace transition.
    repeated = _read_regular_bytes_if_present(
        transfer_dir_fd,
        journal_name,
        expected_mount_id=expected_mount_id,
        max_bytes=128 * 1024,
    )
    if repeated != expected_previous_bytes:
        raise _broker_error("durable journal changed before atomic advance")
    try:
        if expected_previous_bytes is None:
            _rename_noreplace(
                transfer_dir_fd,
                temp_name,
                transfer_dir_fd,
                journal_name,
            )
        else:
            os.replace(
                temp_name,
                journal_name,
                src_dir_fd=transfer_dir_fd,
                dst_dir_fd=transfer_dir_fd,
            )
    except ProviderIsolationBundleBrokerError:
        raise
    except OSError as exc:
        raise _broker_error("atomic journal advance failed") from exc
    _fsync_directory(transfer_dir_fd)
    return encoded


def _read_journal_if_present(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
    paths: ProviderIsolationBundleTransferPaths,
    transfer_dir_fd: int,
) -> ProviderIsolationBundleTransferRecord | None:
    raw = _read_regular_bytes_if_present(
        transfer_dir_fd,
        _JOURNAL_NAME,
        expected_mount_id=request.expected_runtime_mount_id,
        max_bytes=128 * 1024,
    )
    if raw is None:
        return None
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _broker_error("transfer journal is not strict JSON") from exc
    if not isinstance(document, dict):
        raise _broker_error("transfer journal root is not an object")
    canonical = _canonical_validated_journal(document)
    if raw != canonical:
        raise _broker_error("transfer journal bytes are noncanonical")
    _require_journal_binding(request, paths, document)
    return _record_from_document(paths, document)


def _require_journal_binding(
    request: (
        ProviderIsolationBundleTransferIdentity
        | ProviderIsolationBundleTransferRequest
    ),
    paths: ProviderIsolationBundleTransferPaths,
    document: Mapping[str, Any],
) -> None:
    expected = {
        "schema_version": _TRANSFER_SCHEMA_VERSION,
        "invocation_identity": request.invocation_identity,
        "scope": list(request.scope),
        "ordinal": request.ordinal,
    }
    for field, value in expected.items():
        if document.get(field) != value:
            raise _broker_error(f"transfer journal {field} binding changed")
    if document["staged_identity"]["path"] != paths.staged_relative_path:
        raise _broker_error("transfer journal staged path binding changed")
    if document["target_identity"]["path"] != paths.target_relative_path:
        raise _broker_error("transfer journal target path binding changed")
    archive = document.get("archive_identity")
    if archive is not None and archive["path"] != paths.archive_relative_path:
        raise _broker_error("transfer journal archive path binding changed")
    staged_tuple = tuple(
        document["staged_identity"][field]
        for field in ("device", "inode", "mount_id")
    )
    target_tuple = tuple(
        document["target_identity"][field]
        for field in ("device", "inode", "mount_id")
    )
    if staged_tuple != target_tuple:
        raise _broker_error("stage and target identities do not bind one inode")
    if archive is not None:
        archive_tuple = tuple(
            archive[field] for field in ("device", "inode", "mount_id")
        )
        if archive_tuple != target_tuple:
            raise _broker_error(
                "target and archive identities do not bind one inode"
            )


def _record_from_document(
    paths: ProviderIsolationBundleTransferPaths,
    document: Mapping[str, Any],
) -> ProviderIsolationBundleTransferRecord:
    canonical = _canonical_validated_journal(document)
    state = document["state"]
    if state not in {
        "prepared",
        "published",
        "validated",
        "rotation_pending",
        "rotated",
    }:  # pragma: no cover - schema invariant
        raise _broker_error("transfer state is not closed")
    return ProviderIsolationBundleTransferRecord(
        state=state,
        journal_relative_path=paths.journal_relative_path,
        staged_relative_path=paths.staged_relative_path,
        target_relative_path=paths.target_relative_path,
        archive_relative_path=paths.archive_relative_path,
        canonical_json=canonical,
    )


def _read_regular_bytes_if_present(
    parent_fd: int,
    name: str,
    *,
    expected_mount_id: int,
    max_bytes: int,
) -> bytes | None:
    pin_fd = -1
    read_fd = -1
    try:
        try:
            pin_fd = os.open(
                name,
                os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return None
        before = os.fstat(pin_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > max_bytes
        ):
            raise _broker_error("broker-owned file has invalid type or size")
        if _statx_mount_id(pin_fd) != expected_mount_id:
            raise _broker_error("broker-owned file crossed a mount boundary")
        try:
            read_fd = os.open(
                f"/proc/self/fd/{pin_fd}",
                os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC,
            )
        except OSError as exc:
            raise _broker_error("trusted descriptor read view is unavailable") from exc
        data = _read_bounded(read_fd, max_bytes)
        after = os.fstat(read_fd)
        pin_after = os.fstat(pin_fd)
        if (
            len(data) > max_bytes
            or not _same_stable_file(after, before)
            or not _same_stable_file(pin_after, before)
            or _statx_mount_id(read_fd) != expected_mount_id
            or _statx_mount_id(pin_fd) != expected_mount_id
        ):
            raise _broker_error("broker-owned file changed during read")
        return data
    except ProviderIsolationBundleBrokerError:
        raise
    except (OSError, MountIdentityUnavailable, ValueError) as exc:
        raise _broker_error("broker-owned file could not be read safely") from exc
    finally:
        if read_fd >= 0:
            os.close(read_fd)
        if pin_fd >= 0:
            os.close(pin_fd)


def _validate_location_if_present(
    parent_fd: int,
    basename: str,
    expected_identity: Mapping[str, Any] | None,
    document: Mapping[str, Any],
    expected_mount_id: int,
) -> bool:
    data = _read_regular_bytes_if_present(
        parent_fd,
        basename,
        expected_mount_id=expected_mount_id,
        max_bytes=int(document["bundle_size"]),
    )
    if data is None:
        return False
    if expected_identity is None:
        raise _broker_error("unexpected bundle location exists")
    try:
        pin_fd = os.open(
            basename,
            os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except OSError as exc:  # pragma: no cover - just read it
        raise _broker_error("bundle identity disappeared after read") from exc
    try:
        observed = _file_identity(
            pin_fd,
            str(expected_identity["path"]),
            expected_mount_id,
        )
    finally:
        os.close(pin_fd)
    if any(
        observed[field] != expected_identity[field]
        for field in ("device", "inode", "mount_id")
    ):
        raise _broker_error("bundle file identity differs from journal")
    if len(data) != document["bundle_size"] or (
        f"sha256:{sha256(data).hexdigest()}" != document["bundle_digest"]
    ):
        raise _broker_error("bundle bytes differ from journal")
    return True


def _entry_exists(parent_fd: int, name: str) -> bool:
    try:
        fd = os.open(
            name,
            os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise _broker_error("bundle location could not be classified") from exc
    else:
        os.close(fd)
        return True


def _require_absent_at(parent_fd: int, name: str, label: str) -> None:
    if _entry_exists(parent_fd, name):
        raise _broker_error(f"{label} already exists")


def _require_known_transfer_directory_entries(
    transfer_dir_fd: int,
    expected: set[str],
) -> None:
    try:
        names = set(os.listdir(transfer_dir_fd))
    except OSError as exc:
        raise _broker_error("private transfer directory cannot be enumerated") from exc
    if names != expected:
        raise _broker_error(
            "private transfer directory contains unexplained entries"
        )


def _rename_noreplace(
    source_parent_fd: int,
    source_name: str,
    target_parent_fd: int,
    target_name: str,
) -> None:
    """Linux renameat2(RENAME_NOREPLACE), with no overwrite fallback."""

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise _broker_error("Linux renameat2 is unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    try:
        source_bytes = os.fsencode(source_name)
        target_bytes = os.fsencode(target_name)
    except (TypeError, UnicodeEncodeError) as exc:
        raise _broker_error("rename path is not a filesystem name") from exc
    result = renameat2(
        source_parent_fd,
        source_bytes,
        target_parent_fd,
        target_bytes,
        _RENAME_NOREPLACE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise _broker_error(
            f"atomic no-replace rename failed with errno {error_number}"
        ) from OSError(error_number, os.strerror(error_number))


def _fsync_directory(directory_fd: int) -> None:
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        raise _broker_error("directory fsync is unavailable") from exc


def _require_positive_acknowledgement(
    acknowledgement: ProviderIsolationBundleRotationAcknowledgement,
    record: ProviderIsolationBundleTransferRecord,
) -> None:
    try:
        accepted = acknowledgement(record)
    except BaseException as exc:
        raise _broker_error("caller acknowledgement failed") from exc
    if accepted is not True:
        raise _broker_error("caller did not acknowledge invalid rotation")


def _broker_error(message: str) -> ProviderIsolationBundleBrokerError:
    return ProviderIsolationBundleBrokerError(message)


__all__ = [
    "BUNDLE_BROKER_ERROR_CODE",
    "BUNDLE_OVERSIZED_REASON",
    "BUNDLE_REJECTED_REASON",
    "ProviderIsolationBundleBrokerError",
    "ProviderIsolationBundleCapture",
    "ProviderIsolationBundleCleanupEvidence",
    "ProviderIsolationBundleRotationAcknowledgement",
    "ProviderIsolationBundleScratchCleanup",
    "ProviderIsolationBundleScratchCleanupAcknowledgement",
    "ProviderIsolationBundleTransferIdentity",
    "ProviderIsolationBundleTransferPaths",
    "ProviderIsolationBundleTransferRecord",
    "ProviderIsolationBundleTransferRequest",
    "capture_active_bundle",
    "capture_active_bundle_from_authority",
    "cleanup_invocation_scratch_after_acknowledgement",
    "create_bundle_transfer_request_from_authority",
    "derive_bundle_transfer_paths",
    "prepare_and_publish_bundle_transfer",
    "record_bundle_transfer_validation",
    "reconcile_bundle_transfer",
    "rotate_invalid_bundle_transfer",
]
