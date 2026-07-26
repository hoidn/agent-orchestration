"""Closed provider-isolation backend identity and launch authority contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import errno
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path, PurePath
import posixpath
import secrets
import signal
import stat
import time
from typing import Any, Literal, Protocol, runtime_checkable
import unicodedata

from orchestrator.providers.isolation import (
    MAX_PROVIDER_ISOLATION_SCOPE_COMPONENTS,
    MAX_PROVIDER_ISOLATION_SCOPE_COMPONENT_LENGTH,
    MAX_PROVIDER_ISOLATION_RUNTIME_RELPATH_LENGTH,
    MAX_PROVIDER_ISOLATION_UINT64,
    MAX_RESULT_BUNDLE_BYTES,
    canonical_isolation_json_bytes,
)
from orchestrator.providers import isolation_environment as _environment
from orchestrator.providers.isolation_candidate import (
    ProviderCandidateAdmission,
)
from orchestrator.providers.isolation_runtime_authority import (
    ProviderIsolationRuntimeAuthority,
    RuntimeAuthorityObjectIdentity,
)


BACKEND_IDENTITY_SCHEMA_VERSION = "provider_isolation_backend_identity.v1"
BACKEND_CONTRACT_ID = "bubblewrap.v1"
BACKEND_EXECUTABLE_PATH = Path("/usr/bin/bwrap")
BACKEND_UNAVAILABLE_CODE = "provider_isolation_backend_unavailable"
INVALID_PLAN_CODE = "provider_isolation_grant_invalid"
STATE_ERROR_CODE = "provider_isolation_state_invalid"
LAUNCH_RELEASE_SCHEMA_VERSION = "provider_isolation_launch_release.v1"
_DIGEST_PREFIX = "sha256:"
_MAX_TRUSTED_FILE_BYTES = 64 * 1024 * 1024
_MAX_SYMLINKS = 40
_DEFAULT_LIBRARY_DIRECTORIES = (
    "/lib/x86_64-linux-gnu",
    "/usr/lib/x86_64-linux-gnu",
    "/lib64",
    "/usr/lib64",
    "/lib",
    "/usr/lib",
)


class ProviderIsolationBackendUnavailable(RuntimeError):
    """The fixed backend cannot establish the complete launch authority."""

    code = BACKEND_UNAVAILABLE_CODE

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


class ProviderIsolationInvalidPlan(ValueError):
    """A request can express an authority combination outside the closed union."""

    code = INVALID_PLAN_CODE

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


class ProviderIsolationStateError(RuntimeError):
    """Durable launch state is malformed, ambiguous, or replayed."""

    code = STATE_ERROR_CODE

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


def _require_digest(value: object, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != len(_DIGEST_PREFIX) + 64
        or not value.startswith(_DIGEST_PREFIX)
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise TypeError(f"{label} must be a canonical sha256 identity")
    return value


def _require_text(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or "\x00" in value
        or unicodedata.normalize("NFC", value) != value
    ):
        raise TypeError(f"{label} must be nonempty normalized text")
    return value


def _require_absolute_path(value: object, label: str) -> str:
    text = _require_text(value, label)
    if (
        not text.startswith("/")
        or text != posixpath.normpath(text)
        or text == "/"
        or "//" in text
    ):
        raise TypeError(f"{label} must be one canonical non-root absolute path")
    return text


def _require_target(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise TypeError("target must be one nonempty argv tuple")
    normalized = tuple(_require_text(item, "target item") for item in value)
    executable = _require_absolute_path(
        normalized[0],
        "target executable",
    )
    normalized = (executable, *normalized[1:])
    return normalized


@dataclass(frozen=True, slots=True)
class WorkflowProviderIsolationRequest:
    """Closed workflow-provider/typed-result request variant."""

    candidate_path: str
    target: tuple[str, ...]
    environment_digest: str
    result_channel: Literal["typed_bundle"]
    provider_template_identity: str
    aggregate_scope: tuple[str, ...]
    ordinal: int
    result_logical_path: str
    result_bundle_max_bytes: int
    subject_kind: Literal["workflow_provider"] = field(
        init=False, default="workflow_provider"
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_path",
            _require_absolute_path(self.candidate_path, "candidate_path"),
        )
        object.__setattr__(self, "target", _require_target(self.target))
        object.__setattr__(
            self,
            "environment_digest",
            _require_digest(self.environment_digest, "environment_digest"),
        )
        if self.result_channel != "typed_bundle":
            raise TypeError("workflow_provider requires result_channel typed_bundle")
        object.__setattr__(
            self,
            "provider_template_identity",
            _require_digest(
                self.provider_template_identity,
                "provider_template_identity",
            ),
        )
        if (
            type(self.aggregate_scope) is not tuple
            or not self.aggregate_scope
            or len(self.aggregate_scope)
            > MAX_PROVIDER_ISOLATION_SCOPE_COMPONENTS
        ):
            raise TypeError(
                "aggregate_scope must be a nonempty bounded tuple"
            )
        normalized_scope = tuple(
            _require_text(item, "aggregate_scope item")
            for item in self.aggregate_scope
        )
        if any(
            len(item) > MAX_PROVIDER_ISOLATION_SCOPE_COMPONENT_LENGTH
            for item in normalized_scope
        ):
            raise TypeError(
                "aggregate_scope items exceed the journal length bound"
            )
        object.__setattr__(
            self,
            "aggregate_scope",
            normalized_scope,
        )
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int):
            raise TypeError("ordinal must be a positive integer")
        if self.ordinal < 1 or self.ordinal > MAX_PROVIDER_ISOLATION_UINT64:
            raise TypeError("ordinal must be one positive uint64 integer")
        result_path = _require_absolute_path(
            self.result_logical_path,
            "result_logical_path",
        )
        candidate = Path(self.candidate_path)
        result = Path(result_path)
        runtime_root = candidate / ".orchestrate"
        try:
            runtime_relative = result.relative_to(runtime_root)
        except ValueError as exc:
            raise TypeError(
                "workflow result logical path must be below runtime authority"
            ) from exc
        runtime_relpath = runtime_relative.as_posix()
        if (
            not runtime_relative.parts
            or len(runtime_relpath)
            > MAX_PROVIDER_ISOLATION_RUNTIME_RELPATH_LENGTH
        ):
            raise TypeError(
                "workflow result runtime-relative path exceeds the journal "
                "length bound"
            )
        object.__setattr__(self, "result_logical_path", result_path)
        if (
            type(self.result_bundle_max_bytes) is not int
            or self.result_bundle_max_bytes < 1
            or self.result_bundle_max_bytes > MAX_RESULT_BUNDLE_BYTES
        ):
            raise TypeError(
                "result_bundle_max_bytes must be a positive integer "
                f"no greater than {MAX_RESULT_BUNDLE_BYTES}"
            )


@dataclass(frozen=True, slots=True)
class ControllerAttemptIsolationRequest:
    """Closed reusable controller-attempt/no-result request variant."""

    candidate_path: str
    target: tuple[str, ...]
    environment_digest: str
    result_channel: Literal["none"]
    caller_kind: str
    caller_attempt_id: str
    command_identity: str
    external_sink_identity: str
    subject_kind: Literal["controller_attempt"] = field(
        init=False, default="controller_attempt"
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_path",
            _require_absolute_path(self.candidate_path, "candidate_path"),
        )
        object.__setattr__(self, "target", _require_target(self.target))
        object.__setattr__(
            self,
            "environment_digest",
            _require_digest(self.environment_digest, "environment_digest"),
        )
        if self.result_channel != "none":
            raise TypeError("controller_attempt requires result_channel none")
        object.__setattr__(
            self, "caller_kind", _require_text(self.caller_kind, "caller_kind")
        )
        object.__setattr__(
            self,
            "caller_attempt_id",
            _require_text(self.caller_attempt_id, "caller_attempt_id"),
        )
        object.__setattr__(
            self,
            "command_identity",
            _require_digest(self.command_identity, "command_identity"),
        )
        object.__setattr__(
            self,
            "external_sink_identity",
            _require_digest(
                self.external_sink_identity,
                "external_sink_identity",
            ),
        )


ProviderIsolationRequest = (
    WorkflowProviderIsolationRequest | ControllerAttemptIsolationRequest
)


_RESULT_BROKER_AUTHORITY_TOKEN = object()
_RESULT_BROKER_QUIESCENCE_TOKEN = object()


class PinnedProviderResultBrokerAuthorities:
    """Caller-owned descriptor authority for one quiescent result broker."""

    __slots__ = (
        "_request",
        "_runtime_fd",
        "_scratch_fd",
        "_runtime_identity",
        "_scratch_identity",
        "_scratch_relpath",
        "_target_runtime_relpath",
        "_active_basename",
        "_invocation_identity",
        "_closed",
    )

    def __init__(
        self,
        *,
        request: WorkflowProviderIsolationRequest,
        runtime_fd: int,
        scratch_fd: int,
        runtime_identity: RuntimeAuthorityObjectIdentity,
        scratch_identity: RuntimeAuthorityObjectIdentity,
        scratch_relpath: str,
        target_runtime_relpath: str,
        active_basename: str,
        invocation_identity: str,
        _token: object | None = None,
    ):
        if _token is not _RESULT_BROKER_AUTHORITY_TOKEN:
            raise ProviderIsolationInvalidPlan(
                "result broker authorities require the validating factory"
            )
        self._request = request
        self._runtime_fd = runtime_fd
        self._scratch_fd = scratch_fd
        self._runtime_identity = runtime_identity
        self._scratch_identity = scratch_identity
        self._scratch_relpath = scratch_relpath
        self._target_runtime_relpath = target_runtime_relpath
        self._active_basename = active_basename
        self._invocation_identity = invocation_identity
        self._closed = False

    @property
    def request(self) -> WorkflowProviderIsolationRequest:
        return self._request

    @property
    def runtime_fd(self) -> int:
        return self._runtime_fd

    @property
    def scratch_fd(self) -> int:
        return self._scratch_fd

    @property
    def runtime_identity(self) -> RuntimeAuthorityObjectIdentity:
        return self._runtime_identity

    @property
    def scratch_identity(self) -> RuntimeAuthorityObjectIdentity:
        return self._scratch_identity

    @property
    def scratch_relpath(self) -> str:
        return self._scratch_relpath

    @property
    def target_runtime_relpath(self) -> str:
        return self._target_runtime_relpath

    @property
    def active_basename(self) -> str:
        return self._active_basename

    @property
    def invocation_identity(self) -> str:
        return self._invocation_identity

    @property
    def result_bundle_max_bytes(self) -> int:
        return self._request.result_bundle_max_bytes

    @property
    def closed(self) -> bool:
        return self._closed

    def revalidate(self) -> None:
        """Revalidate the exact duplicated post-quiescence broker authority."""

        if self._closed:
            raise ProviderIsolationInvalidPlan(
                "result broker authorities are closed"
            )
        try:
            if type(self._request) is not WorkflowProviderIsolationRequest:
                raise ProviderIsolationInvalidPlan(
                    "result broker request has an invalid exact type"
                )
            if (
                self._scratch_relpath
                != _invocation_scratch_relpath(self._request)
            ):
                raise ProviderIsolationInvalidPlan(
                    "result broker scratch binding changed"
                )
            target_relpath, active_basename = (
                _result_broker_target_runtime_relpath(self._request)
            )
            if (
                target_relpath != self._target_runtime_relpath
                or active_basename != self._active_basename
                or self._invocation_identity
                != _result_broker_invocation_identity(
                    self._request,
                    target_runtime_relpath=target_relpath,
                )
            ):
                raise ProviderIsolationInvalidPlan(
                    "result broker invocation binding changed"
                )
            for fd, identity, label in (
                (self._runtime_fd, self._runtime_identity, "runtime"),
                (self._scratch_fd, self._scratch_identity, "scratch"),
            ):
                observed = os.fstat(fd)
                if (
                    not stat.S_ISDIR(observed.st_mode)
                    or observed.st_dev != identity.device
                    or observed.st_ino != identity.inode
                    or _environment._statx_mount_id(fd)
                    != identity.mount_id
                    or observed.st_uid != os.geteuid()
                    or observed.st_gid != os.getegid()
                    or stat.S_IMODE(observed.st_mode) != 0o700
                ):
                    raise ProviderIsolationInvalidPlan(
                        f"result broker {label} descriptor changed authority"
                    )
            if (
                self._runtime_identity.mount_id
                != self._scratch_identity.mount_id
            ):
                raise ProviderIsolationInvalidPlan(
                    "result broker descriptors crossed a mount boundary"
                )
        except ProviderIsolationInvalidPlan:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ProviderIsolationInvalidPlan(
                "result broker authority revalidation failed"
            ) from exc

    def close(self) -> None:
        if self._closed:
            return
        first_failure: BaseException | None = None
        try:
            for fd_name in ("_scratch_fd", "_runtime_fd"):
                fd = getattr(self, fd_name)
                if fd < 0:
                    continue
                try:
                    os.close(fd)
                except BaseException as exc:
                    if first_failure is None:
                        first_failure = exc
                    else:
                        first_failure.add_note(
                            f"additional descriptor-close failure: {exc!r}"
                        )
                finally:
                    setattr(self, fd_name, -1)
        finally:
            self._closed = True
        if first_failure is not None:
            raise first_failure

    def __enter__(self) -> "PinnedProviderResultBrokerAuthorities":
        if self._closed:
            raise ProviderIsolationInvalidPlan(
                "result broker authorities are closed"
            )
        return self

    def __exit__(
        self,
        _exc_type: object,
        exc: BaseException | None,
        _traceback: object,
    ) -> None:
        try:
            self.close()
        except BaseException as close_exc:
            if exc is None:
                raise
            exc.add_note(
                f"result-broker authority close also failed: {close_exc!r}"
            )


_PINNED_INVOCATION_AUTHORITY_TOKEN = object()
_INVOCATION_SCRATCH_SCHEMA_VERSION = (
    "provider_isolation_invocation_scratch.v1"
)
_RESULT_BROKER_INVOCATION_SCHEMA_VERSION = (
    "provider_isolation_result_broker_invocation.v1"
)


class PinnedProviderInvocationAuthorities:
    """One request-bound live owner of every provider setup mount authority."""

    __slots__ = (
        "_snapshot",
        "_candidate",
        "_runtime",
        "_request",
        "_environment_digest",
        "_provider_prefix",
        "_candidate_path",
        "_candidate_identity",
        "_runtime_identity",
        "_scratch_relpath",
        "_scratch_fd",
        "_scratch_identity",
        "_broker_quiescence_identity",
        "_result_broker_authority_opened",
        "_closed",
    )

    def __init__(
        self,
        *,
        snapshot: _environment.ProviderEnvironmentSnapshot,
        candidate: ProviderCandidateAdmission,
        runtime: ProviderIsolationRuntimeAuthority,
        request: ProviderIsolationRequest,
        scratch_relpath: str | None = None,
        scratch_fd: int = -1,
        scratch_identity: RuntimeAuthorityObjectIdentity | None = None,
        _token: object | None = None,
    ):
        if _token is not _PINNED_INVOCATION_AUTHORITY_TOKEN:
            raise ProviderIsolationInvalidPlan(
                "pinned invocation authorities require the validating factory"
            )
        self._snapshot = snapshot
        self._candidate = candidate
        self._runtime = runtime
        self._request = request
        self._environment_digest = snapshot.digest
        self._provider_prefix = snapshot.manifest.provider_prefix
        self._candidate_path = os.fspath(candidate.path)
        self._candidate_identity = candidate.root_identity
        self._runtime_identity = runtime.identity
        self._scratch_relpath = scratch_relpath
        self._scratch_fd = scratch_fd
        self._scratch_identity = scratch_identity
        self._broker_quiescence_identity: str | None = None
        self._result_broker_authority_opened = False
        self._closed = False

    @property
    def request(self) -> ProviderIsolationRequest:
        return self._request

    @property
    def environment_digest(self) -> str:
        return self._environment_digest

    @property
    def provider_prefix(self) -> str:
        return self._provider_prefix

    @property
    def candidate_path(self) -> str:
        return self._candidate_path

    @property
    def scratch_relpath(self) -> str | None:
        return self._scratch_relpath

    @property
    def scratch_identity(self) -> RuntimeAuthorityObjectIdentity | None:
        return self._scratch_identity

    @property
    def closed(self) -> bool:
        return self._closed

    def revalidate(self) -> None:
        if self._closed:
            raise ProviderIsolationInvalidPlan(
                "pinned invocation authorities are closed"
            )
        try:
            _require_typed_invocation_components(
                snapshot=self._snapshot,
                candidate=self._candidate,
                runtime=self._runtime,
                request=self._request,
            )
            self._snapshot.revalidate_for_launch()
            self._candidate.revalidate()
            self._runtime.revalidate()
            _require_invocation_cross_binding(
                snapshot=self._snapshot,
                candidate=self._candidate,
                runtime=self._runtime,
                request=self._request,
            )
            if (
                self._snapshot.digest != self._environment_digest
                or self._snapshot.manifest.provider_prefix
                != self._provider_prefix
                or os.fspath(self._candidate.path) != self._candidate_path
                or self._candidate.root_identity != self._candidate_identity
                or self._runtime.identity != self._runtime_identity
            ):
                raise ProviderIsolationInvalidPlan(
                    "pinned invocation authority binding changed"
                )
            if isinstance(self._request, WorkflowProviderIsolationRequest):
                if (
                    self._scratch_relpath is None
                    or self._scratch_fd < 0
                    or self._scratch_identity is None
                ):
                    raise ProviderIsolationInvalidPlan(
                        "workflow invocation scratch authority is absent"
                    )
                self._runtime.revalidate_directory_binding(
                    self._scratch_relpath,
                    self._scratch_fd,
                    self._scratch_identity,
                )
            elif (
                self._scratch_relpath is not None
                or self._scratch_fd >= 0
                or self._scratch_identity is not None
            ):
                raise ProviderIsolationInvalidPlan(
                    "controller invocation has a scratch authority"
                )
        except ProviderIsolationInvalidPlan:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise ProviderIsolationInvalidPlan(
                "pinned invocation authority revalidation failed"
            ) from exc

    def revalidate_for_result_broker_after_quiescence(self) -> None:
        """Revalidate one workflow authority at the broker transition."""

        if self._closed:
            raise ProviderIsolationInvalidPlan(
                "pinned invocation authorities are closed"
            )
        try:
            _require_typed_invocation_components(
                snapshot=self._snapshot,
                candidate=self._candidate,
                runtime=self._runtime,
                request=self._request,
            )
            if type(self._request) is not WorkflowProviderIsolationRequest:
                raise ProviderIsolationInvalidPlan(
                    "result broker revalidation requires a workflow invocation"
                )
            if (
                self._scratch_relpath is None
                or self._scratch_fd < 0
                or self._scratch_identity is None
                or self._scratch_relpath
                != _invocation_scratch_relpath(self._request)
            ):
                raise ProviderIsolationInvalidPlan(
                    "workflow invocation scratch authority is absent or changed"
                )
            self._snapshot.revalidate_for_launch()
            self._candidate.revalidate()
            self._runtime.revalidate_for_broker_after_quiescence(
                self._scratch_relpath,
                self._scratch_fd,
                self._scratch_identity,
            )
            _require_invocation_cross_binding(
                snapshot=self._snapshot,
                candidate=self._candidate,
                runtime=self._runtime,
                request=self._request,
            )
            if (
                self._snapshot.digest != self._environment_digest
                or self._snapshot.manifest.provider_prefix
                != self._provider_prefix
                or os.fspath(self._candidate.path) != self._candidate_path
                or self._candidate.root_identity != self._candidate_identity
                or self._runtime.identity != self._runtime_identity
            ):
                raise ProviderIsolationInvalidPlan(
                    "pinned invocation authority binding changed"
                )
        except ProviderIsolationInvalidPlan:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise ProviderIsolationInvalidPlan(
                "pinned invocation broker revalidation failed"
            ) from exc

    def _record_result_broker_quiescence(
        self,
        containment_identity: str,
        *,
        _token: object | None = None,
    ) -> None:
        """Record the launcher's one exact empty-containment transition."""

        if _token is not _RESULT_BROKER_QUIESCENCE_TOKEN:
            raise ProviderIsolationInvalidPlan(
                "result broker quiescence requires the launcher authority"
            )
        if self._broker_quiescence_identity is not None:
            raise ProviderIsolationInvalidPlan(
                "result broker quiescence was already recorded"
            )
        identity = _require_digest(
            containment_identity,
            "containment_identity",
        )
        self.revalidate_for_result_broker_after_quiescence()
        self._broker_quiescence_identity = identity

    def open_result_broker_authority_after_quiescence(
        self,
        *,
        minimum: int = 16,
    ) -> PinnedProviderResultBrokerAuthorities:
        """Duplicate the exact runtime/scratch capability for bundle brokerage."""

        if type(self._request) is not WorkflowProviderIsolationRequest:
            raise ProviderIsolationInvalidPlan(
                "result broker authority requires a workflow invocation"
            )
        if (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or minimum < 3
        ):
            raise ProviderIsolationInvalidPlan(
                "result broker descriptor minimum must be an integer >= 3"
            )
        if self._broker_quiescence_identity is None:
            raise ProviderIsolationInvalidPlan(
                "result broker authority requires launcher-proved quiescence"
            )
        if self._result_broker_authority_opened:
            raise ProviderIsolationInvalidPlan(
                "result broker authority was already opened"
            )
        runtime_fd = -1
        scratch_fd = -1
        try:
            self.revalidate_for_result_broker_after_quiescence()
            if (
                type(self._request) is not WorkflowProviderIsolationRequest
                or self._scratch_relpath is None
                or self._scratch_fd < 0
                or self._scratch_identity is None
            ):
                raise ProviderIsolationInvalidPlan(
                    "result broker authority requires a workflow invocation"
                )
            target_runtime_relpath, active_basename = (
                _result_broker_target_runtime_relpath(self._request)
            )
            runtime_fd = (
                self._runtime
                .duplicate_runtime_fd_for_broker_after_quiescence(
                    self._scratch_relpath,
                    self._scratch_fd,
                    self._scratch_identity,
                    minimum=minimum,
                )
            )
            scratch_fd = fcntl.fcntl(
                self._scratch_fd,
                fcntl.F_DUPFD_CLOEXEC,
                max(minimum, runtime_fd + 1),
            )
            scratch = os.fstat(scratch_fd)
            if (
                not stat.S_ISDIR(scratch.st_mode)
                or scratch.st_dev != self._scratch_identity.device
                or scratch.st_ino != self._scratch_identity.inode
                or _environment._statx_mount_id(scratch_fd)
                != self._scratch_identity.mount_id
                or scratch.st_uid != os.geteuid()
                or stat.S_IMODE(scratch.st_mode) != 0o700
            ):
                raise ProviderIsolationInvalidPlan(
                    "result broker scratch descriptor changed authority"
                )
            invocation_identity = _result_broker_invocation_identity(
                self._request,
                target_runtime_relpath=target_runtime_relpath,
            )
            self.revalidate_for_result_broker_after_quiescence()
            result = PinnedProviderResultBrokerAuthorities(
                request=self._request,
                runtime_fd=runtime_fd,
                scratch_fd=scratch_fd,
                runtime_identity=self._runtime.identity.runtime,
                scratch_identity=self._scratch_identity,
                scratch_relpath=self._scratch_relpath,
                target_runtime_relpath=target_runtime_relpath,
                active_basename=active_basename,
                invocation_identity=invocation_identity,
                _token=_RESULT_BROKER_AUTHORITY_TOKEN,
            )
            runtime_fd = -1
            scratch_fd = -1
            self._result_broker_authority_opened = True
            return result
        except ProviderIsolationInvalidPlan:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ProviderIsolationInvalidPlan(
                "result broker authorities could not be duplicated"
            ) from exc
        finally:
            for fd in (scratch_fd, runtime_fd):
                if fd >= 0:
                    os.close(fd)

    def _duplicate_setup_fds(self) -> tuple[int, int, int | None]:
        """Duplicate the closed mount-source set after live revalidation."""

        rootfs_fd = -1
        candidate_fd = -1
        scratch_fd = -1
        try:
            self.revalidate()
            rootfs_fd = self._snapshot.duplicate_root_fd_for_launch(
                minimum=16,
            )
            candidate_fd = self._candidate.duplicate_root_fd(minimum=16)
            if self._scratch_fd >= 0:
                if (
                    self._scratch_relpath is None
                    or self._scratch_identity is None
                ):
                    raise ProviderIsolationInvalidPlan(
                        "workflow invocation scratch authority is absent"
                    )
                scratch_fd = self._runtime.duplicate_directory_binding(
                    self._scratch_relpath,
                    self._scratch_fd,
                    self._scratch_identity,
                    minimum=16,
                )
            self.revalidate()
            rootfs_source = os.fstat(self._snapshot.root_fd)
            rootfs_duplicate = os.fstat(rootfs_fd)
            if (
                not stat.S_ISDIR(rootfs_duplicate.st_mode)
                or rootfs_duplicate.st_dev != rootfs_source.st_dev
                or rootfs_duplicate.st_ino != rootfs_source.st_ino
                or _environment._statx_mount_id(rootfs_fd)
                != _environment._statx_mount_id(self._snapshot.root_fd)
                or stat.S_IMODE(rootfs_duplicate.st_mode)
                != stat.S_IMODE(rootfs_source.st_mode)
            ):
                raise ProviderIsolationInvalidPlan(
                    "pinned rootfs setup descriptor changed authority"
                )
            candidate_duplicate = os.fstat(candidate_fd)
            if (
                not stat.S_ISDIR(candidate_duplicate.st_mode)
                or candidate_duplicate.st_dev
                != self._candidate_identity.device
                or candidate_duplicate.st_ino
                != self._candidate_identity.inode
                or _environment._statx_mount_id(candidate_fd)
                != self._candidate_identity.mount_id
                or stat.S_IMODE(candidate_duplicate.st_mode)
                != self._candidate_identity.mode
                or candidate_duplicate.st_uid
                != self._candidate_identity.owner_uid
            ):
                raise ProviderIsolationInvalidPlan(
                    "pinned candidate setup descriptor changed authority"
                )
            if scratch_fd >= 0:
                if self._scratch_identity is None:
                    raise ProviderIsolationInvalidPlan(
                        "workflow invocation scratch authority is absent"
                    )
                scratch_duplicate = os.fstat(scratch_fd)
                if (
                    not stat.S_ISDIR(scratch_duplicate.st_mode)
                    or scratch_duplicate.st_dev
                    != self._scratch_identity.device
                    or scratch_duplicate.st_ino
                    != self._scratch_identity.inode
                    or _environment._statx_mount_id(scratch_fd)
                    != self._scratch_identity.mount_id
                    or scratch_duplicate.st_uid != os.geteuid()
                    or stat.S_IMODE(scratch_duplicate.st_mode) != 0o700
                ):
                    raise ProviderIsolationInvalidPlan(
                        "pinned scratch setup descriptor changed authority"
                    )
            identities = {
                (os.fstat(rootfs_fd).st_dev, os.fstat(rootfs_fd).st_ino),
                (
                    os.fstat(candidate_fd).st_dev,
                    os.fstat(candidate_fd).st_ino,
                ),
            }
            if scratch_fd >= 0:
                identities.add(
                    (
                        os.fstat(scratch_fd).st_dev,
                        os.fstat(scratch_fd).st_ino,
                    )
                )
            if len(identities) != (3 if scratch_fd >= 0 else 2):
                raise ProviderIsolationInvalidPlan(
                    "pinned invocation mount authorities alias"
                )
            result = (
                rootfs_fd,
                candidate_fd,
                scratch_fd if scratch_fd >= 0 else None,
            )
            rootfs_fd = -1
            candidate_fd = -1
            scratch_fd = -1
            return result
        except ProviderIsolationInvalidPlan:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ProviderIsolationInvalidPlan(
                "pinned invocation setup descriptors are unavailable"
            ) from exc
        finally:
            for fd in (rootfs_fd, candidate_fd, scratch_fd):
                if fd >= 0:
                    os.close(fd)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._scratch_fd >= 0:
            os.close(self._scratch_fd)
            self._scratch_fd = -1

    def __enter__(self) -> "PinnedProviderInvocationAuthorities":
        self.revalidate()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def pin_provider_invocation_authorities(
    *,
    snapshot: _environment.ProviderEnvironmentSnapshot,
    candidate: ProviderCandidateAdmission,
    runtime: ProviderIsolationRuntimeAuthority,
    request: ProviderIsolationRequest,
) -> PinnedProviderInvocationAuthorities:
    """Validate, cross-bind, and pin one request's complete mount-source set."""

    scratch_fd = -1
    scratch_relpath: str | None = None
    scratch_identity: RuntimeAuthorityObjectIdentity | None = None
    try:
        _require_typed_invocation_components(
            snapshot=snapshot,
            candidate=candidate,
            runtime=runtime,
            request=request,
        )
        snapshot.revalidate_for_launch()
        candidate.revalidate()
        runtime.revalidate()
        _require_invocation_cross_binding(
            snapshot=snapshot,
            candidate=candidate,
            runtime=runtime,
            request=request,
        )
        if isinstance(request, WorkflowProviderIsolationRequest):
            scratch_relpath = _invocation_scratch_relpath(request)
            scratch_fd, scratch_identity = runtime.create_fresh_directory(
                scratch_relpath,
                parents=True,
            )
        authority = PinnedProviderInvocationAuthorities(
            snapshot=snapshot,
            candidate=candidate,
            runtime=runtime,
            request=request,
            scratch_relpath=scratch_relpath,
            scratch_fd=scratch_fd,
            scratch_identity=scratch_identity,
            _token=_PINNED_INVOCATION_AUTHORITY_TOKEN,
        )
        authority.revalidate()
        scratch_fd = -1
        return authority
    except ProviderIsolationInvalidPlan:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ProviderIsolationInvalidPlan(
            "provider invocation authorities could not be pinned"
        ) from exc
    finally:
        if scratch_fd >= 0:
            try:
                if scratch_relpath is not None and scratch_identity is not None:
                    runtime.remove_empty_directory_binding(
                        scratch_relpath,
                        scratch_fd,
                        scratch_identity,
                    )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise ProviderIsolationInvalidPlan(
                    "provider invocation scratch unwind failed"
                ) from exc
            finally:
                os.close(scratch_fd)


def _require_typed_invocation_components(
    *,
    snapshot: object,
    candidate: object,
    runtime: object,
    request: object,
) -> None:
    if type(snapshot) is not _environment.ProviderEnvironmentSnapshot:
        raise ProviderIsolationInvalidPlan(
            "provider environment snapshot has an invalid exact type"
        )
    if type(candidate) is not ProviderCandidateAdmission:
        raise ProviderIsolationInvalidPlan(
            "provider candidate admission has an invalid exact type"
        )
    if type(runtime) is not ProviderIsolationRuntimeAuthority:
        raise ProviderIsolationInvalidPlan(
            "provider runtime authority has an invalid exact type"
        )
    if type(request) not in {
        WorkflowProviderIsolationRequest,
        ControllerAttemptIsolationRequest,
    }:
        raise ProviderIsolationInvalidPlan(
            "provider isolation request has an invalid exact type"
        )


def _require_invocation_cross_binding(
    *,
    snapshot: _environment.ProviderEnvironmentSnapshot,
    candidate: ProviderCandidateAdmission,
    runtime: ProviderIsolationRuntimeAuthority,
    request: ProviderIsolationRequest,
) -> None:
    request_environment_digest = _require_digest(
        request.environment_digest,
        "environment_digest",
    )
    request_candidate_path = _require_absolute_path(
        request.candidate_path,
        "candidate_path",
    )
    request_target = _require_target(request.target)
    snapshot_digest = _require_digest(
        snapshot.digest,
        "environment_digest",
    )
    provider_prefix = _require_absolute_path(
        snapshot.manifest.provider_prefix,
        "provider_prefix",
    )
    candidate_path = _require_absolute_path(
        os.fspath(candidate.path),
        "candidate_path",
    )
    runtime_identity = runtime.identity
    candidate_identity = candidate.root_identity
    if (
        request_environment_digest != snapshot_digest
        or request_candidate_path != candidate_path
        or runtime_identity.candidate_root != candidate_path
        or runtime_identity.candidate.path != candidate_path
        or candidate_identity.device != runtime_identity.candidate.device
        or candidate_identity.inode != runtime_identity.candidate.inode
        or candidate_identity.mount_id != runtime_identity.candidate.mount_id
        or not request_target[0].startswith(provider_prefix + "/")
    ):
        raise ProviderIsolationInvalidPlan(
            "provider invocation typed authorities do not cross-bind"
        )


def _invocation_scratch_relpath(
    request: WorkflowProviderIsolationRequest,
) -> str:
    document = {
        "schema_version": _INVOCATION_SCRATCH_SCHEMA_VERSION,
        "aggregate_scope": list(request.aggregate_scope),
        "ordinal": request.ordinal,
    }
    identity = sha256(canonical_isolation_json_bytes(document)).hexdigest()
    return f"provider-invocation-scratch/{identity}"


def _result_broker_target_runtime_relpath(
    request: WorkflowProviderIsolationRequest,
) -> tuple[str, str]:
    runtime_root = PurePath(request.candidate_path) / ".orchestrate"
    result = PurePath(request.result_logical_path)
    try:
        relative = result.relative_to(runtime_root)
    except ValueError as exc:
        raise ProviderIsolationInvalidPlan(
            "workflow result target must be below the runtime authority"
        ) from exc
    if not relative.parts:
        raise ProviderIsolationInvalidPlan(
            "workflow result target must name one runtime file"
        )
    relpath = relative.as_posix()
    if relpath != posixpath.normpath(relpath):
        raise ProviderIsolationInvalidPlan(
            "workflow result target runtime path is not canonical"
        )
    return relpath, relative.name


def _result_broker_invocation_identity(
    request: WorkflowProviderIsolationRequest,
    *,
    target_runtime_relpath: str,
) -> str:
    document = {
        "schema_version": _RESULT_BROKER_INVOCATION_SCHEMA_VERSION,
        "subject_kind": request.subject_kind,
        "environment_digest": request.environment_digest,
        "provider_template_identity": request.provider_template_identity,
        "aggregate_scope": list(request.aggregate_scope),
        "ordinal": request.ordinal,
        "target_runtime_relpath": target_runtime_relpath,
        "result_bundle_max_bytes": request.result_bundle_max_bytes,
    }
    return "sha256:" + sha256(
        canonical_isolation_json_bytes(document)
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderIsolationMount:
    """One role-labelled descriptor-bound mount in a closed plan."""

    role: Literal["sealed_rootfs", "candidate", "active_result_scratch"]
    source_fd: int
    destination: str
    access: Literal["ro", "rw"]
    source_path: None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if (
            isinstance(self.source_fd, bool)
            or not isinstance(self.source_fd, int)
            or self.source_fd < 3
        ):
            raise ProviderIsolationInvalidPlan(
                "mount source must be one setup-only descriptor"
            )
        if self.role == "sealed_rootfs" and self.destination == "/":
            destination = "/"
        else:
            destination = _require_absolute_path(
                self.destination,
                "mount destination",
            )
        object.__setattr__(self, "destination", destination)
        expected = {
            "sealed_rootfs": "ro",
            "candidate": "rw",
            "active_result_scratch": "rw",
        }
        if self.role not in expected or expected[self.role] != self.access:
            raise ProviderIsolationInvalidPlan("mount role/access is not admitted")


@dataclass(frozen=True, slots=True)
class ProviderInvocationIsolationPlan:
    """Immutable backend-neutral authority plan for one isolated attempt."""

    backend: Literal["bubblewrap.v1"]
    backend_identity_digest: str
    network_preflight_digest: str
    request: ProviderIsolationRequest
    result_bundle_max_bytes: int | None = field(init=False)
    mounts: tuple[ProviderIsolationMount, ...]
    provider_prefix: str
    synthetic_home: str
    readiness_fd: int
    status_fd: int
    credential_fd: int
    expected_primary_group_count: int
    expected_overflow_group_count: int
    environment: tuple[tuple[str, str], ...]
    hostname: str = "orchestrator-provider"
    declared_credential_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        from orchestrator.providers.provider_launch_shim import (
            _fixed_environment,
        )

        if self.backend != BACKEND_CONTRACT_ID:
            raise ProviderIsolationInvalidPlan("backend contract is unsupported")
        _require_digest(self.backend_identity_digest, "backend_identity_digest")
        _require_digest(
            self.network_preflight_digest,
            "network_preflight_digest",
        )
        _require_absolute_path(self.provider_prefix, "provider_prefix")
        _require_absolute_path(self.synthetic_home, "synthetic_home")
        if self.synthetic_home != "/run/provider-home":
            raise ProviderIsolationInvalidPlan(
                "synthetic home must match the fixed provider environment"
            )
        target_executable = _require_absolute_path(
            self.request.target[0],
            "target executable",
        )
        if not target_executable.startswith(self.provider_prefix + "/"):
            raise ProviderIsolationInvalidPlan(
                "target executable must be strictly inside the provider prefix"
            )
        output_bundle = (
            self.request.result_logical_path
            if isinstance(self.request, WorkflowProviderIsolationRequest)
            else None
        )
        object.__setattr__(
            self,
            "result_bundle_max_bytes",
            (
                self.request.result_bundle_max_bytes
                if isinstance(self.request, WorkflowProviderIsolationRequest)
                else None
            ),
        )
        expected_environment = tuple(
            _fixed_environment(
                {},
                provider_prefix=self.provider_prefix,
                output_bundle=output_bundle,
            ).items()
        )
        if self.environment != expected_environment:
            raise ProviderIsolationInvalidPlan(
                "plan environment is not the canonical fixed environment"
            )
        if (
            self.readiness_fd < 4
            or self.status_fd < 4
            or self.credential_fd != 3
            or len({self.readiness_fd, self.status_fd, self.credential_fd}) != 3
        ):
            raise ProviderIsolationInvalidPlan(
                "transport descriptors do not match the closed launch contract"
            )
        for count in (
            self.expected_primary_group_count,
            self.expected_overflow_group_count,
        ):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ProviderIsolationInvalidPlan(
                    "expected supplementary-group counts must be bounded integers"
                )
        if (
            self.expected_primary_group_count
            + self.expected_overflow_group_count
            > 65_536
        ):
            raise ProviderIsolationInvalidPlan(
                "expected supplementary-group counts exceed the bound"
            )
        if not self.hostname or self.hostname == os.uname().nodename:
            raise ProviderIsolationInvalidPlan("isolated hostname is invalid")
        if len(self.declared_credential_names) > 32 or len(
            set(self.declared_credential_names)
        ) != len(self.declared_credential_names):
            raise ProviderIsolationInvalidPlan(
                "declared credential-name set is invalid"
            )
        for name in self.declared_credential_names:
            if (
                not isinstance(name, str)
                or not name
                or not name.replace("_", "A").isalnum()
                or not (name[0].isalpha() or name[0] == "_")
            ):
                raise ProviderIsolationInvalidPlan(
                    "declared credential-name set is invalid"
                )
        roles = tuple(mount.role for mount in self.mounts)
        required = ("sealed_rootfs", "candidate")
        if roles[:2] != required or len(set(roles)) != len(roles):
            raise ProviderIsolationInvalidPlan("mount role set is invalid")
        if isinstance(self.request, WorkflowProviderIsolationRequest):
            if roles != required + ("active_result_scratch",):
                raise ProviderIsolationInvalidPlan(
                    "workflow provider requires exactly one result scratch"
                )
        elif roles != required:
            raise ProviderIsolationInvalidPlan(
                "controller attempt forbids result scratch"
            )


@dataclass(frozen=True, slots=True)
class TrustedPathEntry:
    """One safe regular-file identity in the host startup closure."""

    path: str
    resolved_path: str
    size: int
    mode: int
    uid: int
    gid: int
    device: int
    inode: int
    digest: str
    symlinks: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "resolved_path": self.resolved_path,
            "size": self.size,
            "mode": self.mode,
            "uid": self.uid,
            "gid": self.gid,
            "device": self.device,
            "inode": self.inode,
            "digest": self.digest,
            "symlinks": [
                {"path": path, "link_text": link_text}
                for path, link_text in self.symlinks
            ],
        }


@dataclass(frozen=True, slots=True)
class ProviderIsolationBackendIdentity:
    """Canonical content-addressed identity of one fixed backend."""

    contract_id: str
    executable: TrustedPathEntry
    version: str
    startup_closure: tuple[TrustedPathEntry, ...]
    loader_cache: TrustedPathEntry
    preload_absent: bool
    capability_probe_contract_digest: str
    containment_root_identity: str
    capability_probe_results: tuple[tuple[str, object], ...]
    canonical_json: bytes = field(repr=False)
    digest: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        if not isinstance(value, dict):  # pragma: no cover
            raise AssertionError("backend identity must be an object")
        return value


@runtime_checkable
class ProviderIsolationBackend(Protocol):
    """Closed protocol implemented by a selectable isolation backend."""

    contract_id: str
    executable_path: Path

    def preflight(self) -> "PinnedProviderIsolationBackend":
        """Pin and validate the complete backend authority."""


@dataclass(slots=True)
class PinnedProviderIsolationBackend:
    """An opened backend executable plus its immutable startup identity."""

    backend: "BubblewrapBackend"
    executable_fd: int
    identity: ProviderIsolationBackendIdentity

    def revalidate(self) -> ProviderIsolationBackendIdentity:
        if self.executable_fd < 0:
            raise ProviderIsolationBackendUnavailable(
                "pinned backend descriptor is closed"
            )
        _, digest = _hash_open_regular(
            self.executable_fd,
            maximum_bytes=_MAX_TRUSTED_FILE_BYTES,
        )
        opened = os.fstat(self.executable_fd)
        expected = self.identity.executable
        if (
            digest != expected.digest
            or opened.st_size != expected.size
            or opened.st_dev != expected.device
            or opened.st_ino != expected.inode
            or stat.S_IMODE(opened.st_mode) != expected.mode
        ):
            raise ProviderIsolationBackendUnavailable(
                "pinned backend executable identity changed"
            )
        fresh = self.backend.preflight()
        try:
            if fresh.identity.digest != self.identity.digest:
                raise ProviderIsolationBackendUnavailable(
                    "backend startup identity changed"
                )
        finally:
            fresh.close()
        return self.identity

    def close(self) -> None:
        if self.executable_fd < 0:
            return
        os.close(self.executable_fd)
        self.executable_fd = -1

    def __enter__(self) -> "PinnedProviderIsolationBackend":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class BubblewrapBackend:
    """The only v1 backend: fixed root-owned ``/usr/bin/bwrap``."""

    contract_id: str = field(init=False, default=BACKEND_CONTRACT_ID)

    @property
    def executable_path(self) -> Path:
        return BACKEND_EXECUTABLE_PATH

    def preflight(self) -> PinnedProviderIsolationBackend:
        executable_path = BACKEND_EXECUTABLE_PATH
        executable_fd = -1
        try:
            executable, executable_fd = _admit_fixed_backend_executable(
                executable_path,
                keep_open=True,
            )
            parsed = _environment._parse_elf_fd(
                executable_fd,
                os.fspath(executable_path),
            )
            cache, cache_fd = _admit_trusted_regular(
                Path("/etc/ld.so.cache"),
                keep_open=True,
            )
            try:
                cache_entries = _environment._parse_glibc_cache_fd(cache_fd)
            finally:
                os.close(cache_fd)
            preload = Path("/etc/ld.so.preload")
            if preload.exists() or preload.is_symlink():
                raise ProviderIsolationBackendUnavailable(
                    "/etc/ld.so.preload is present"
                )
            closure_paths = _resolve_host_startup_closure(
                executable_path,
                parsed=parsed,
                cache_entries=cache_entries,
            )
            closure = tuple(
                _admit_trusted_regular(Path(path), keep_open=False)[0]
                for path in closure_paths
            )
            version = _backend_version_from_descriptor(executable_fd)
            capability_results = _run_backend_capability_probe(executable_fd)
            containment_root = CgroupV2ContainmentRoot.discover()
            containment_probe = _probe_cgroup_v2_containment(
                containment_root,
                attempt_label=(
                    f"backend-preflight-{secrets.token_hex(16)}"
                ),
            )
            probe_contract = canonical_isolation_json_bytes(
                {
                    "schema_version": "provider_isolation_backend_probe.v1",
                    "required": [
                        "rootless_user_namespace",
                        "descriptor_bound_mounts",
                        "pid_namespace",
                        "shared_host_network",
                        "new_session",
                        "nested_userns_disabled",
                    ],
                }
            )
            document = {
                "schema_version": BACKEND_IDENTITY_SCHEMA_VERSION,
                "contract_id": self.contract_id,
                "executable": executable.to_dict(),
                "version": version,
                "startup_closure": [entry.to_dict() for entry in closure],
                "loader_cache": cache.to_dict(),
                "startup_configuration": {
                    "ld_so_preload": "absent",
                },
                "containment": {
                    "contract_id": "cgroup_v2_leaf.v1",
                    "root_identity": containment_root.identity_digest,
                    "probe_results": containment_probe,
                },
                "capability_probe_contract_digest": _digest(probe_contract),
                "capability_probe_results": capability_results,
            }
            canonical = canonical_isolation_json_bytes(document)
            identity = ProviderIsolationBackendIdentity(
                contract_id=self.contract_id,
                executable=executable,
                version=version,
                startup_closure=closure,
                loader_cache=cache,
                preload_absent=True,
                capability_probe_contract_digest=_digest(probe_contract),
                containment_root_identity=containment_root.identity_digest,
                capability_probe_results=tuple(
                    sorted(capability_results.items())
                ),
                canonical_json=canonical,
                digest=_digest(canonical),
            )
            return PinnedProviderIsolationBackend(
                backend=self,
                executable_fd=executable_fd,
                identity=identity,
            )
        except ProviderIsolationBackendUnavailable:
            if executable_fd >= 0:
                os.close(executable_fd)
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            if executable_fd >= 0:
                os.close(executable_fd)
            raise ProviderIsolationBackendUnavailable(
                "fixed Bubblewrap authority could not be validated"
            ) from exc


_BACKENDS: Mapping[str, ProviderIsolationBackend] = {
    BACKEND_CONTRACT_ID: BubblewrapBackend(),
}


def get_provider_isolation_backend(contract_id: str) -> ProviderIsolationBackend:
    """Select one backend from the closed registry without consulting ``PATH``."""

    try:
        return _BACKENDS[contract_id]
    except (KeyError, TypeError) as exc:
        raise ProviderIsolationBackendUnavailable(
            "requested backend contract is unsupported"
        ) from exc


def _select_host_elf_dependency(
    needed: str,
    *,
    owner: str,
    elf: _environment.ParsedElf,
    cache_entries: Sequence[Any],
) -> str:
    """Select one host dependency in the admitted loader precedence order."""

    if "/" in needed:
        if not needed.startswith("/") or posixpath.normpath(needed) != needed:
            raise ProviderIsolationBackendUnavailable(
                "host ELF dependency uses an unsafe path"
            )
        return needed
    owner_search: list[str] = []
    values = elf.runpath if elf.runpath else elf.rpath
    for value in values:
        try:
            expanded = _environment.expand_loader_search_path(
                value,
                containing_object=owner,
                allowed_root="/",
            )
        except Exception as exc:
            raise ProviderIsolationBackendUnavailable(
                "host ELF search path is unsupported"
            ) from exc
        owner_search.extend(expanded)
    for directory in owner_search:
        candidate = posixpath.normpath(posixpath.join(directory, needed))
        if candidate.startswith("/") and Path(candidate).is_file():
            return candidate
    try:
        cached = _environment._select_glibc_cache_dependency(
            cache_entries,
            needed=needed,
        )
    except Exception as exc:
        raise ProviderIsolationBackendUnavailable(
            "host loader cache dependency is ambiguous"
        ) from exc
    if cached is not None:
        return cached
    for directory in _DEFAULT_LIBRARY_DIRECTORIES:
        candidate = posixpath.normpath(posixpath.join(directory, needed))
        if candidate.startswith("/") and Path(candidate).is_file():
            return candidate
    raise ProviderIsolationBackendUnavailable(
        "host ELF dependency is unavailable"
    )


def _resolve_host_startup_closure(
    executable: Path,
    *,
    parsed: _environment.ParsedElf,
    cache_entries: Sequence[Any],
) -> tuple[str, ...]:
    pending: list[str] = []
    if parsed.interpreter is None:
        raise ProviderIsolationBackendUnavailable(
            "Bubblewrap has no admitted ELF interpreter"
        )
    pending.append(parsed.interpreter)
    parsed_by_path: dict[str, _environment.ParsedElf] = {
        os.fspath(executable): parsed
    }
    result: list[str] = []
    seen: set[str] = {os.fspath(executable)}

    for needed in parsed.needed:
        pending.append(
            _select_host_elf_dependency(
                needed,
                owner=os.fspath(executable),
                elf=parsed,
                cache_entries=cache_entries,
            )
        )

    while pending:
        path = pending.pop(0)
        admitted, fd = _admit_trusted_regular(Path(path), keep_open=True)
        try:
            canonical_path = admitted.path
            if canonical_path in seen:
                continue
            seen.add(canonical_path)
            result.append(canonical_path)
            try:
                elf = _environment._parse_elf_fd(fd, canonical_path)
            except Exception as exc:
                raise ProviderIsolationBackendUnavailable(
                    "host startup closure member is not a valid ELF"
                ) from exc
            parsed_by_path[canonical_path] = elf
            if elf.interpreter and elf.interpreter not in seen:
                pending.append(elf.interpreter)
            for needed in elf.needed:
                pending.append(
                    _select_host_elf_dependency(
                        needed,
                        owner=canonical_path,
                        elf=elf,
                        cache_entries=cache_entries,
                    )
                )
        finally:
            os.close(fd)
    return tuple(sorted(result, key=lambda value: value.encode("utf-8")))


def _admit_trusted_regular(
    path: Path,
    *,
    keep_open: bool,
) -> tuple[TrustedPathEntry, int]:
    if (
        not path.is_absolute()
        or os.fspath(path) != posixpath.normpath(os.fspath(path))
        or unicodedata.normalize("NFC", os.fspath(path)) != os.fspath(path)
    ):
        raise ProviderIsolationBackendUnavailable(
            "trusted host path is not canonical"
        )
    resolved, symlinks = _resolve_safe_host_path(path)
    _require_safe_ancestor_chain(resolved.parent)
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(resolved, flags)
    try:
        opened = os.fstat(fd)
        linked = os.lstat(resolved)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != linked.st_dev
            or opened.st_ino != linked.st_ino
            or opened.st_uid != 0
            or opened.st_gid != 0
            or opened.st_mode
            & (stat.S_ISUID | stat.S_ISGID | stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise ProviderIsolationBackendUnavailable(
                "trusted host file ownership or mode is unsafe"
            )
        _require_no_xattrs(fd)
        size, digest = _hash_open_regular(
            fd,
            maximum_bytes=_MAX_TRUSTED_FILE_BYTES,
        )
        final = os.fstat(fd)
        if (
            final.st_dev != opened.st_dev
            or final.st_ino != opened.st_ino
            or final.st_size != opened.st_size
            or final.st_mtime_ns != opened.st_mtime_ns
            or final.st_ctime_ns != opened.st_ctime_ns
        ):
            raise ProviderIsolationBackendUnavailable(
                "trusted host file changed during admission"
            )
        entry = TrustedPathEntry(
            path=os.fspath(path),
            resolved_path=os.fspath(resolved),
            size=size,
            mode=stat.S_IMODE(opened.st_mode),
            uid=opened.st_uid,
            gid=opened.st_gid,
            device=opened.st_dev,
            inode=opened.st_ino,
            digest=digest,
            symlinks=symlinks,
        )
        if keep_open:
            return entry, fd
        os.close(fd)
        return entry, -1
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _admit_fixed_backend_executable(
    path: Path,
    *,
    keep_open: bool,
) -> tuple[TrustedPathEntry, int]:
    """Open the fixed backend through a symlink-free descriptor chain."""

    if (
        not path.is_absolute()
        or os.fspath(path) != posixpath.normpath(os.fspath(path))
        or unicodedata.normalize("NFC", os.fspath(path)) != os.fspath(path)
    ):
        raise ProviderIsolationBackendUnavailable(
            "trusted host path is not canonical"
        )
    components = path.parts[1:]
    if not components:
        raise ProviderIsolationBackendUnavailable(
            "trusted host path is not canonical"
        )
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if not isinstance(no_follow, int) or no_follow <= 0:
        raise ProviderIsolationBackendUnavailable(
            "descriptor-relative no-follow opens are unavailable"
        )

    directory_fd = -1
    executable_fd = -1
    try:
        directory_fd = os.open(
            "/",
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_CLOEXEC
            | no_follow,
        )
        _require_trusted_ancestor_descriptor(directory_fd)
        for component in components[:-1]:
            linked = os.stat(
                component,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(linked.st_mode):
                raise ProviderIsolationBackendUnavailable(
                    "fixed Bubblewrap executable path must be symlink-free"
                )
            opened_fd = os.open(
                component,
                os.O_RDONLY
                | os.O_DIRECTORY
                | os.O_CLOEXEC
                | no_follow,
                dir_fd=directory_fd,
            )
            opened = os.fstat(opened_fd)
            if (
                opened.st_dev != linked.st_dev
                or opened.st_ino != linked.st_ino
            ):
                os.close(opened_fd)
                raise ProviderIsolationBackendUnavailable(
                    "trusted host ancestor changed during admission"
                )
            try:
                _require_trusted_ancestor_descriptor(opened_fd)
            except BaseException:
                os.close(opened_fd)
                raise
            os.close(directory_fd)
            directory_fd = opened_fd

        linked = os.stat(
            components[-1],
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(linked.st_mode):
            raise ProviderIsolationBackendUnavailable(
                "fixed Bubblewrap executable path must be symlink-free"
            )
        executable_fd = os.open(
            components[-1],
            os.O_RDONLY
            | os.O_CLOEXEC
            | no_follow,
            dir_fd=directory_fd,
        )
        opened = os.fstat(executable_fd)
        if (
            opened.st_dev != linked.st_dev
            or opened.st_ino != linked.st_ino
        ):
            raise ProviderIsolationBackendUnavailable(
                "trusted host file changed during admission"
            )
        entry = _trusted_regular_entry_from_descriptor(
            path=path,
            resolved=path,
            symlinks=(),
            fd=executable_fd,
        )
        if keep_open:
            result_fd = executable_fd
            executable_fd = -1
            return entry, result_fd
        os.close(executable_fd)
        executable_fd = -1
        return entry, -1
    finally:
        if executable_fd >= 0:
            os.close(executable_fd)
        if directory_fd >= 0:
            os.close(directory_fd)


def _require_trusted_ancestor_descriptor(fd: int) -> None:
    value = os.fstat(fd)
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != 0
        or value.st_gid != 0
        or value.st_mode
        & (
            stat.S_ISUID
            | stat.S_ISGID
            | stat.S_IWGRP
            | stat.S_IWOTH
        )
    ):
        raise ProviderIsolationBackendUnavailable(
            "trusted host ancestor ownership or mode is unsafe"
        )
    _require_no_xattrs(fd)


def _trusted_regular_entry_from_descriptor(
    *,
    path: Path,
    resolved: Path,
    symlinks: tuple[tuple[str, str], ...],
    fd: int,
) -> TrustedPathEntry:
    opened = os.fstat(fd)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != 0
        or opened.st_gid != 0
        or opened.st_mode
        & (stat.S_ISUID | stat.S_ISGID | stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise ProviderIsolationBackendUnavailable(
            "trusted host file ownership or mode is unsafe"
        )
    _require_no_xattrs(fd)
    size, digest = _hash_open_regular(
        fd,
        maximum_bytes=_MAX_TRUSTED_FILE_BYTES,
    )
    final = os.fstat(fd)
    if (
        final.st_dev != opened.st_dev
        or final.st_ino != opened.st_ino
        or final.st_size != opened.st_size
        or final.st_mtime_ns != opened.st_mtime_ns
        or final.st_ctime_ns != opened.st_ctime_ns
    ):
        raise ProviderIsolationBackendUnavailable(
            "trusted host file changed during admission"
        )
    return TrustedPathEntry(
        path=os.fspath(path),
        resolved_path=os.fspath(resolved),
        size=size,
        mode=stat.S_IMODE(opened.st_mode),
        uid=opened.st_uid,
        gid=opened.st_gid,
        device=opened.st_dev,
        inode=opened.st_ino,
        digest=digest,
        symlinks=symlinks,
    )


def _resolve_safe_host_path(
    path: Path,
) -> tuple[Path, tuple[tuple[str, str], ...]]:
    current_parts = list(path.parts[1:])
    resolved = Path("/")
    symlinks: list[tuple[str, str]] = []
    followed = 0
    while current_parts:
        component = current_parts.pop(0)
        if component in {"", ".", ".."}:
            raise ProviderIsolationBackendUnavailable(
                "trusted host path contains an unsafe component"
            )
        candidate = resolved / component
        value = os.lstat(candidate)
        if stat.S_ISLNK(value.st_mode):
            if value.st_uid != 0 or value.st_gid != 0:
                raise ProviderIsolationBackendUnavailable(
                    "trusted host symlink is not root-owned"
                )
            _require_no_xattrs_at(candidate)
            link_text = os.readlink(candidate)
            if (
                not link_text
                or "\x00" in link_text
                or unicodedata.normalize("NFC", link_text) != link_text
            ):
                raise ProviderIsolationBackendUnavailable(
                    "trusted host symlink text is invalid"
                )
            confirmed = os.lstat(candidate)
            if (
                confirmed.st_dev != value.st_dev
                or confirmed.st_ino != value.st_ino
                or confirmed.st_mode != value.st_mode
                or confirmed.st_uid != value.st_uid
                or confirmed.st_gid != value.st_gid
                or confirmed.st_size != value.st_size
                or confirmed.st_mtime_ns != value.st_mtime_ns
                or confirmed.st_ctime_ns != value.st_ctime_ns
            ):
                raise ProviderIsolationBackendUnavailable(
                    "trusted host symlink changed during admission"
                )
            symlinks.append((os.fspath(candidate), link_text))
            followed += 1
            if followed > _MAX_SYMLINKS:
                raise ProviderIsolationBackendUnavailable(
                    "trusted host symlink chain exceeds the bound"
                )
            target = Path(link_text)
            if target.is_absolute():
                base_parts: list[str] = []
            else:
                base_parts = list(resolved.parts[1:])
            for target_component in target.parts:
                if target_component in {"", ".", "/"}:
                    continue
                if target_component == "..":
                    if not base_parts:
                        raise ProviderIsolationBackendUnavailable(
                            "trusted host symlink escaped the root"
                        )
                    base_parts.pop()
                    continue
                base_parts.append(target_component)
            combined = Path("/", *base_parts)
            current_parts = list(combined.parts[1:]) + current_parts
            resolved = Path("/")
            continue
        resolved = candidate
    return resolved, tuple(symlinks)


def _require_safe_ancestor_chain(path: Path) -> None:
    ancestors = [Path("/")]
    current = Path("/")
    for component in path.parts[1:]:
        current /= component
        ancestors.append(current)
    for ancestor in ancestors:
        value = os.lstat(ancestor)
        if (
            not stat.S_ISDIR(value.st_mode)
            or value.st_uid != 0
            or value.st_gid != 0
            or value.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise ProviderIsolationBackendUnavailable(
                "trusted host ancestor ownership or mode is unsafe"
            )
        fd = os.open(
            ancestor,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            _require_no_xattrs(fd)
        finally:
            os.close(fd)


def _require_no_xattrs(fd: int) -> None:
    try:
        names = os.listxattr(fd)
    except OSError as exc:
        if exc.errno in {errno.ENOTSUP, errno.EOPNOTSUPP}:
            return
        raise ProviderIsolationBackendUnavailable(
            "trusted host xattrs cannot be inspected"
        ) from exc
    if names:
        raise ProviderIsolationBackendUnavailable(
            "trusted host object carries extended attributes"
        )


def _require_no_xattrs_at(path: Path) -> None:
    try:
        names = os.listxattr(path, follow_symlinks=False)
    except OSError as exc:
        if exc.errno in {errno.ENOTSUP, errno.EOPNOTSUPP}:
            return
        raise ProviderIsolationBackendUnavailable(
            "trusted host symlink xattrs cannot be inspected"
        ) from exc
    if names:
        raise ProviderIsolationBackendUnavailable(
            "trusted host symlink carries extended attributes"
        )


def _hash_open_regular(
    fd: int,
    *,
    maximum_bytes: int,
) -> tuple[int, str]:
    opened = os.fstat(fd)
    if opened.st_size < 0 or opened.st_size > maximum_bytes:
        raise ProviderIsolationBackendUnavailable(
            "trusted host file exceeds the byte bound"
        )
    digest = sha256()
    size = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, min(1024 * 1024, maximum_bytes + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > maximum_bytes:
            raise ProviderIsolationBackendUnavailable(
                "trusted host file exceeds the byte bound"
            )
        digest.update(chunk)
    if size != opened.st_size:
        raise ProviderIsolationBackendUnavailable(
            "trusted host file size changed during hashing"
        )
    return size, _DIGEST_PREFIX + digest.hexdigest()


def _backend_version_from_descriptor(fd: int) -> str:
    read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
    pid = os.fork()
    if pid == 0:
        try:
            os.dup2(write_fd, 1)
            os.dup2(write_fd, 2)
            os.close(read_fd)
            if write_fd not in {1, 2}:
                os.close(write_fd)
            os.execve(
                fd,
                ["/usr/bin/bwrap", "--version"],
                {
                    "HOME": "/",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": "/usr/bin:/bin",
                },
            )
        except BaseException:
            os._exit(127)
    os.close(write_fd)
    value = bytearray()
    try:
        while len(value) <= 4096:
            chunk = os.read(read_fd, 4097 - len(value))
            if not chunk:
                break
            value.extend(chunk)
    finally:
        os.close(read_fd)
    _, status = os.waitpid(pid, 0)
    if (
        not os.WIFEXITED(status)
        or os.WEXITSTATUS(status) != 0
        or len(value) > 4096
    ):
        raise ProviderIsolationBackendUnavailable(
            "pinned Bubblewrap version probe failed"
        )
    try:
        text = bytes(value).decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise ProviderIsolationBackendUnavailable(
            "Bubblewrap version output is not ASCII"
        ) from exc
    if (
        not text.startswith("bubblewrap ")
        or "\n" in text
        or "\r" in text
        or len(text) > 128
    ):
        raise ProviderIsolationBackendUnavailable(
            "Bubblewrap version output is malformed"
        )
    return text


def _run_backend_capability_probe(fd: int) -> dict[str, object]:
    """Exercise the required rootless namespace switches with trusted code only."""

    argv = _backend_capability_probe_argv()
    read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
    pid = os.fork()
    if pid == 0:
        try:
            os.dup2(write_fd, 1)
            os.dup2(write_fd, 2)
            os.close(read_fd)
            if write_fd not in {1, 2}:
                os.close(write_fd)
            os.execve(fd, argv, {})
        except BaseException:
            os._exit(127)
    os.close(write_fd)
    output = bytearray()
    deadline = time.monotonic() + 10
    status_value: int | None = None
    os.set_blocking(read_fd, False)
    try:
        while True:
            if status_value is None:
                observed, status = os.waitpid(pid, os.WNOHANG)
                if observed == pid:
                    status_value = status
            try:
                block = os.read(read_fd, 4097 - len(output))
            except BlockingIOError:
                block = None
            if block:
                output.extend(block)
                if len(output) > 4096:
                    raise ProviderIsolationBackendUnavailable(
                        "rootless capability probe output is oversized"
                    )
            elif block == b"" and status_value is not None:
                break
            if time.monotonic() >= deadline:
                try:
                    os.kill(pid, 9)
                except ProcessLookupError:
                    pass
                if status_value is None:
                    os.waitpid(pid, 0)
                raise ProviderIsolationBackendUnavailable(
                    "rootless capability probe timed out"
                )
            time.sleep(0.005)
    finally:
        os.close(read_fd)
    if (
        status_value is None
        or not os.WIFEXITED(status_value)
        or os.WEXITSTATUS(status_value) != 0
    ):
        raise ProviderIsolationBackendUnavailable(
            "rootless capability probe failed"
        )
    return {
        "status": "passed",
        "privileged_launcher": False,
        "controller_euid_nonzero": os.geteuid() != 0,
        "shared_host_network": True,
        "test_only_host_root_projection": True,
    }


def _backend_capability_probe_argv() -> list[str]:
    """Return the fixed capability-probe grammar for the shared-network v1."""

    return [
        "/usr/bin/bwrap",
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-cgroup",
        "--disable-userns",
        "--assert-userns-disabled",
        "--uid",
        "0",
        "--gid",
        "0",
        "--cap-drop",
        "ALL",
        "--hostname",
        "orchestrator-provider",
        "--die-with-parent",
        "--new-session",
        "--as-pid-1",
        "--ro-bind",
        "/",
        "/",
        "--clearenv",
        "--",
        "/bin/true",
    ]


def _digest(value: bytes) -> str:
    return _DIGEST_PREFIX + sha256(value).hexdigest()


def _read_cgroup_root_identity(
    delegated_root: Path,
) -> tuple[os.stat_result, int, os.stat_result, int]:
    """Read the mount and delegated root through no-follow directory pins."""

    mount_fd = -1
    root_fd = -1
    flags = os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        mount_fd = os.open(Path("/sys/fs/cgroup"), flags)
        root_fd = os.open(delegated_root, flags)
        mount_value = os.fstat(mount_fd)
        root_value = os.fstat(root_fd)
        mount_id = _environment._statx_mount_id(mount_fd)
        root_mount_id = _environment._statx_mount_id(root_fd)
    except (
        OSError,
        ValueError,
        _environment.MountIdentityUnavailable,
    ) as exc:
        raise ProviderIsolationBackendUnavailable(
            "cgroup-v2 mount or delegated root identity is unavailable"
        ) from exc
    finally:
        if root_fd >= 0:
            os.close(root_fd)
        if mount_fd >= 0:
            os.close(mount_fd)
    return mount_value, mount_id, root_value, root_mount_id


@dataclass(frozen=True, slots=True)
class CgroupV2ContainmentRoot:
    """Controller-owned delegated cgroup-v2 authority for launch leaves."""

    path: Path
    device: int
    inode: int
    uid: int
    gid: int
    mode: int
    statx_mount_id: int
    mount_device: int
    mount_inode: int
    mount_uid: int
    mount_gid: int
    mount_mode: int
    mount_statx_mount_id: int
    identity_digest: str

    @classmethod
    def discover(cls) -> "CgroupV2ContainmentRoot":
        rows = [
            line[3:]
            for line in _read_self_cgroup().splitlines()
            if line.startswith("0::")
        ]
        if len(rows) != 1 or not rows[0].startswith("/"):
            raise ProviderIsolationBackendUnavailable(
                "controller cgroup-v2 identity is unavailable"
            )
        relative = PurePath(rows[0])
        if ".." in relative.parts:
            raise ProviderIsolationBackendUnavailable(
                "controller cgroup-v2 identity is noncanonical"
            )
        mount = Path("/sys/fs/cgroup")
        if not _expected_cgroup2_mount(mount):
            raise ProviderIsolationBackendUnavailable(
                "trusted cgroup-v2 mount is unavailable"
            )
        root = mount.joinpath(*relative.parts[1:])
        (
            mount_value,
            mount_statx_mount_id,
            root_value,
            root_statx_mount_id,
        ) = _read_cgroup_root_identity(root)
        if (
            not stat.S_ISDIR(mount_value.st_mode)
            or not stat.S_ISDIR(root_value.st_mode)
            or root_statx_mount_id != mount_statx_mount_id
            or mount_value.st_uid != 0
            or mount_value.st_gid != 0
            or stat.S_IMODE(mount_value.st_mode) & 0o022
            or root_value.st_uid != os.geteuid()
            or stat.S_IMODE(root_value.st_mode) & 0o022
            or not os.access(root, os.W_OK | os.X_OK)
        ):
            raise ProviderIsolationBackendUnavailable(
                "controller cgroup-v2 scope is not delegated"
            )
        for name in ("cgroup.procs", "cgroup.events"):
            value = root / name
            if not value.is_file() or value.is_symlink():
                raise ProviderIsolationBackendUnavailable(
                    "controller cgroup-v2 scope is incomplete"
                )
        document = {
            "schema_version": "provider_isolation_containment_root.v1",
            "path": os.fspath(root),
            "device": root_value.st_dev,
            "inode": root_value.st_ino,
            "uid": root_value.st_uid,
            "gid": root_value.st_gid,
            "mode": stat.S_IMODE(root_value.st_mode),
            "statx_mount_id": root_statx_mount_id,
            "mount_device": mount_value.st_dev,
            "mount_inode": mount_value.st_ino,
            "mount_uid": mount_value.st_uid,
            "mount_gid": mount_value.st_gid,
            "mount_mode": stat.S_IMODE(mount_value.st_mode),
            "mount_statx_mount_id": mount_statx_mount_id,
        }
        identity = _digest(canonical_isolation_json_bytes(document))
        return cls(
            path=root,
            device=root_value.st_dev,
            inode=root_value.st_ino,
            uid=root_value.st_uid,
            gid=root_value.st_gid,
            mode=stat.S_IMODE(root_value.st_mode),
            statx_mount_id=root_statx_mount_id,
            mount_device=mount_value.st_dev,
            mount_inode=mount_value.st_ino,
            mount_uid=mount_value.st_uid,
            mount_gid=mount_value.st_gid,
            mount_mode=stat.S_IMODE(mount_value.st_mode),
            mount_statx_mount_id=mount_statx_mount_id,
            identity_digest=identity,
        )

    def revalidate(self) -> None:
        mount = Path("/sys/fs/cgroup")
        (
            mount_value,
            mount_statx_mount_id,
            value,
            root_statx_mount_id,
        ) = _read_cgroup_root_identity(self.path)
        if (
            not stat.S_ISDIR(mount_value.st_mode)
            or mount_value.st_dev != self.mount_device
            or mount_value.st_ino != self.mount_inode
            or mount_value.st_uid != self.mount_uid
            or mount_value.st_gid != self.mount_gid
            or stat.S_IMODE(mount_value.st_mode) != self.mount_mode
            or mount_statx_mount_id != self.mount_statx_mount_id
            or mount_value.st_uid != 0
            or mount_value.st_gid != 0
            or stat.S_IMODE(mount_value.st_mode) & 0o022
            or not _expected_cgroup2_mount(mount)
        ):
            raise ProviderIsolationBackendUnavailable(
                "cgroup-v2 mount identity changed"
            )
        if (
            not stat.S_ISDIR(value.st_mode)
            or value.st_dev != self.device
            or value.st_ino != self.inode
            or value.st_uid != self.uid
            or value.st_gid != self.gid
            or stat.S_IMODE(value.st_mode) != self.mode
            or root_statx_mount_id != self.statx_mount_id
            or root_statx_mount_id != mount_statx_mount_id
            or value.st_uid != os.geteuid()
            or stat.S_IMODE(value.st_mode) & 0o022
            or not os.access(self.path, os.W_OK | os.X_OK)
        ):
            raise ProviderIsolationBackendUnavailable(
                "delegated cgroup-v2 root identity changed"
            )

    def create_slot(self, attempt_id: str) -> "CgroupV2ContainmentSlot":
        self.revalidate()
        normalized = _require_text(attempt_id, "attempt_id")
        label = sha256(normalized.encode("utf-8")).hexdigest()[:32]
        name = f"provider-isolation-{label}"
        path = self.path / name
        try:
            os.mkdir(path, 0o700)
        except FileExistsError as exc:
            raise ProviderIsolationStateError(
                "containment slot already exists"
            ) from exc
        except OSError as exc:
            raise ProviderIsolationBackendUnavailable(
                "containment slot could not be created"
            ) from exc
        try:
            slot = self.load_slot(name)
            if slot.populated:
                raise ProviderIsolationStateError(
                    "new containment slot is not empty"
                )
            return slot
        except BaseException:
            try:
                os.rmdir(path)
                try:
                    os.lstat(path)
                except FileNotFoundError:
                    pass
                else:
                    raise OSError(
                        errno.EEXIST,
                        "containment slot remains after cleanup",
                    )
            except OSError as cleanup_error:
                raise ProviderIsolationBackendUnavailable(
                    "containment slot cleanup could not be proven"
                ) from cleanup_error
            raise

    def load_slot(
        self,
        name: str,
        *,
        expected_digest: str | None = None,
    ) -> "CgroupV2ContainmentSlot":
        self.revalidate()
        if (
            not isinstance(name, str)
            or not name.startswith("provider-isolation-")
            or len(name) != len("provider-isolation-") + 32
            or any(character not in "0123456789abcdef" for character in name[-32:])
        ):
            raise ProviderIsolationStateError("containment slot name is invalid")
        path = self.path / name
        try:
            value = os.lstat(path)
        except OSError as exc:
            raise ProviderIsolationStateError(
                "containment slot is unavailable"
            ) from exc
        if not stat.S_ISDIR(value.st_mode) or path.is_symlink():
            raise ProviderIsolationStateError(
                "containment slot authority is invalid"
            )
        for child in ("cgroup.procs", "cgroup.events", "cgroup.kill"):
            child_path = path / child
            if not child_path.is_file() or child_path.is_symlink():
                raise ProviderIsolationBackendUnavailable(
                    "containment slot kernel interface is incomplete"
                )
        document = {
            "schema_version": "provider_isolation_containment_slot.v1",
            "root_identity": self.identity_digest,
            "name": name,
            "device": value.st_dev,
            "inode": value.st_ino,
        }
        digest = _digest(canonical_isolation_json_bytes(document))
        if expected_digest is not None and digest != _require_digest(
            expected_digest,
            "expected containment identity",
        ):
            raise ProviderIsolationStateError(
                "containment slot identity changed"
            )
        return CgroupV2ContainmentSlot(
            root=self,
            name=name,
            path=path,
            device=value.st_dev,
            inode=value.st_ino,
            identity_digest=digest,
        )


@dataclass(frozen=True, slots=True)
class CgroupV2ContainmentSlot:
    """One reloadable PID-reuse-safe launch membership and teardown slot."""

    root: CgroupV2ContainmentRoot
    name: str
    path: Path
    device: int
    inode: int
    identity_digest: str

    def revalidate(self) -> None:
        self.root.revalidate()
        try:
            value = os.lstat(self.path)
        except OSError as exc:
            raise ProviderIsolationStateError(
                "containment slot disappeared"
            ) from exc
        if (
            not stat.S_ISDIR(value.st_mode)
            or value.st_dev != self.device
            or value.st_ino != self.inode
            or self.path.is_symlink()
        ):
            raise ProviderIsolationStateError(
                "containment slot identity changed"
            )

    @property
    def populated(self) -> bool:
        self.revalidate()
        values: dict[str, str] = {}
        try:
            raw = (self.path / "cgroup.events").read_text(
                encoding="ascii",
                errors="strict",
            )
        except (OSError, UnicodeError) as exc:
            raise ProviderIsolationStateError(
                "containment slot events are unreadable"
            ) from exc
        if len(raw) > 4096:
            raise ProviderIsolationStateError(
                "containment slot events exceed the bound"
            )
        for line in raw.splitlines():
            fields = line.split()
            if len(fields) != 2 or fields[0] in values:
                raise ProviderIsolationStateError(
                    "containment slot events are malformed"
                )
            values[fields[0]] = fields[1]
        if values.get("populated") not in {"0", "1"}:
            raise ProviderIsolationStateError(
                "containment populated state is unavailable"
            )
        return values["populated"] == "1"

    def members(self) -> tuple[int, ...]:
        self.revalidate()
        try:
            raw = (self.path / "cgroup.procs").read_text(
                encoding="ascii",
                errors="strict",
            )
        except (OSError, UnicodeError) as exc:
            raise ProviderIsolationStateError(
                "containment membership is unreadable"
            ) from exc
        if len(raw) > 1024 * 1024:
            raise ProviderIsolationStateError(
                "containment membership exceeds the bound"
            )
        values: list[int] = []
        for line in raw.splitlines():
            if not line.isascii() or not line.isdecimal():
                raise ProviderIsolationStateError(
                    "containment membership is malformed"
                )
            value = int(line, 10)
            if value <= 0:
                raise ProviderIsolationStateError(
                    "containment membership is malformed"
                )
            values.append(value)
        if len(values) != len(set(values)):
            raise ProviderIsolationStateError(
                "containment membership is duplicated"
            )
        return tuple(sorted(values))

    def add_pid(self, pid: int) -> None:
        self.revalidate()
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise ProviderIsolationStateError(
                "containment member PID is invalid"
            )
        try:
            with (self.path / "cgroup.procs").open(
                "w",
                encoding="ascii",
            ) as handle:
                written = handle.write(f"{pid}\n")
                handle.flush()
            if written != len(f"{pid}\n"):
                raise OSError(errno.EIO, "short cgroup membership write")
        except OSError as exc:
            raise ProviderIsolationBackendUnavailable(
                "process could not enter containment slot"
            ) from exc
        if pid not in self.members():
            raise ProviderIsolationStateError(
                "process is absent from its containment slot"
            )

    def kill(self) -> None:
        self.revalidate()
        if not self.populated:
            return
        try:
            with (self.path / "cgroup.kill").open(
                "w",
                encoding="ascii",
            ) as handle:
                if handle.write("1\n") != 2:
                    raise OSError(errno.EIO, "short cgroup kill write")
                handle.flush()
        except OSError as exc:
            raise ProviderIsolationBackendUnavailable(
                "containment slot kill is unavailable"
            ) from exc

    def wait_empty(self, *, timeout_seconds: float) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds < 0
            or timeout_seconds > 60
        ):
            raise ProviderIsolationStateError(
                "containment empty timeout is invalid"
            )
        deadline = time.monotonic() + float(timeout_seconds)
        while self.populated:
            if time.monotonic() >= deadline:
                raise ProviderIsolationStateError(
                    "containment slot did not become empty"
                )
            time.sleep(0.01)

    def remove(self) -> None:
        self.revalidate()
        if self.populated:
            raise ProviderIsolationStateError(
                "populated containment slot cannot be removed"
            )
        try:
            os.rmdir(self.path)
        except OSError as exc:
            raise ProviderIsolationStateError(
                "empty containment slot could not be removed"
            ) from exc


def _cleanup_cgroup_v2_probe(
    *,
    active_slot: CgroupV2ContainmentSlot | None,
    slot_removed: bool,
    child_pid: int,
    child_reaped: bool,
) -> None:
    """Best-effort all cleanup steps, then fail if any proof was incomplete."""

    failures: list[BaseException] = []
    if active_slot is not None and not slot_removed:
        try:
            active_slot.kill()
        except BaseException as exc:
            failures.append(exc)

    if child_pid > 0 and not child_reaped:
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except BaseException as exc:
            failures.append(exc)
        try:
            waited_pid, _wait_status = os.waitpid(child_pid, 0)
            if waited_pid != child_pid:
                raise ProviderIsolationStateError(
                    "containment probe child reap identity changed"
                )
        except BaseException as exc:
            failures.append(exc)

    empty_proven = False
    if active_slot is not None and not slot_removed:
        try:
            active_slot.wait_empty(timeout_seconds=5.0)
            empty_proven = True
        except BaseException as exc:
            failures.append(exc)

    if active_slot is not None and not slot_removed and empty_proven:
        remove_returned = False
        try:
            active_slot.remove()
            remove_returned = True
        except BaseException as exc:
            failures.append(exc)
        try:
            os.lstat(active_slot.path)
        except FileNotFoundError:
            pass
        except BaseException as exc:
            failures.append(exc)
        else:
            if remove_returned:
                try:
                    os.rmdir(active_slot.path)
                    os.lstat(active_slot.path)
                except FileNotFoundError:
                    pass
                except BaseException as exc:
                    failures.append(exc)
                else:
                    failures.append(
                        ProviderIsolationStateError(
                            "containment probe slot remains after cleanup"
                        )
                    )

    if failures:
        raise ProviderIsolationBackendUnavailable(
            "containment capability probe cleanup could not be proven"
        ) from failures[0]


def _probe_cgroup_v2_containment(
    root: CgroupV2ContainmentRoot,
    *,
    attempt_label: str,
) -> dict[str, str]:
    """Exercise one real delegated leaf with a trusted blocked child."""

    results = {
        "create": "failed",
        "member": "failed",
        "reload": "failed",
        "kill": "failed",
        "empty": "failed",
        "remove": "failed",
    }
    slot: CgroupV2ContainmentSlot | None = None
    active_slot: CgroupV2ContainmentSlot | None = None
    gate_read = -1
    gate_write = -1
    child_pid = -1
    child_reaped = False
    slot_removed = False
    try:
        slot = root.create_slot(attempt_label)
        active_slot = slot
        results["create"] = "passed"
        if slot.populated:
            raise ProviderIsolationBackendUnavailable(
                "containment probe slot is not initially empty"
            )

        gate_read, gate_write = os.pipe2(os.O_CLOEXEC)
        child_pid = os.fork()
        if child_pid == 0:
            child_exit = 0
            try:
                os.close(gate_write)
                gate_write = -1
                os.read(gate_read, 1)
            except BaseException:
                child_exit = 127
            finally:
                if gate_read >= 0:
                    os.close(gate_read)
            os._exit(child_exit)

        os.close(gate_read)
        gate_read = -1
        slot.add_pid(child_pid)
        if slot.members() != (child_pid,):
            raise ProviderIsolationBackendUnavailable(
                "containment probe membership is not exact"
            )
        results["member"] = "passed"

        active_slot = root.load_slot(
            slot.name,
            expected_digest=slot.identity_digest,
        )
        if active_slot.identity_digest != slot.identity_digest:
            raise ProviderIsolationBackendUnavailable(
                "containment probe reload identity changed"
            )
        results["reload"] = "passed"

        active_slot.kill()
        results["kill"] = "passed"
        waited_pid, wait_status = os.waitpid(child_pid, 0)
        child_reaped = True
        if (
            waited_pid != child_pid
            or not os.WIFSIGNALED(wait_status)
            or os.WTERMSIG(wait_status) != signal.SIGKILL
        ):
            raise ProviderIsolationBackendUnavailable(
                "containment probe child was not killed by its leaf"
            )

        active_slot.wait_empty(timeout_seconds=5.0)
        results["empty"] = "passed"
        active_slot.remove()
        if active_slot.path.exists():
            raise ProviderIsolationBackendUnavailable(
                "containment probe slot remains after removal"
            )
        slot_removed = True
        results["remove"] = "passed"
        return results
    except ProviderIsolationBackendUnavailable:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProviderIsolationBackendUnavailable(
            "containment capability probe failed"
        ) from exc
    finally:
        for descriptor in (gate_read, gate_write):
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if child_pid != 0:
            _cleanup_cgroup_v2_probe(
                active_slot=active_slot,
                slot_removed=slot_removed,
                child_pid=child_pid,
                child_reaped=child_reaped,
            )


def _read_self_cgroup() -> str:
    try:
        value = Path("/proc/self/cgroup").read_text(
            encoding="ascii",
            errors="strict",
        )
    except (OSError, UnicodeError) as exc:
        raise ProviderIsolationBackendUnavailable(
            "controller cgroup-v2 identity is unreadable"
        ) from exc
    if len(value) > 65_536:
        raise ProviderIsolationBackendUnavailable(
            "controller cgroup-v2 identity exceeds the bound"
        )
    return value


def _expected_cgroup2_mount(path: Path) -> bool:
    try:
        value = Path("/proc/self/mountinfo").read_text(
            encoding="utf-8",
            errors="strict",
        )
    except (OSError, UnicodeError):
        return False
    if len(value) > 16 * 1024 * 1024:
        return False
    encoded_path = os.fspath(path).replace(" ", "\\040")
    matches = []
    for line in value.splitlines():
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        fields = left.split()
        right_fields = right.split()
        if len(fields) >= 5 and len(right_fields) >= 1:
            if fields[4] == encoded_path and right_fields[0] == "cgroup2":
                matches.append(line)
    return len(matches) == 1


@dataclass(slots=True)
class DurableLaunchReleaseGate:
    """Durable intent/commit record with a non-durable one-use release permit."""

    path: Path
    launch_token: str
    containment_identity: str
    events: tuple[str, ...]
    release_consumed: bool
    _expected_document: bytes = field(repr=False)
    _parent_device: int = field(repr=False)
    _parent_inode: int = field(repr=False)
    _release_permit: str | None = field(default=None, repr=False)
    _poisoned: bool = field(default=False, repr=False)

    @property
    def release_permit(self) -> str | None:
        return self._release_permit

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @classmethod
    def create(
        cls,
        path: str | os.PathLike[str],
        *,
        launch_token: str,
        containment_identity: str,
    ) -> "DurableLaunchReleaseGate":
        target = Path(path)
        if not target.is_absolute():
            target = target.absolute()
        _require_digest(launch_token, "launch_token")
        _require_digest(containment_identity, "containment_identity")
        document = {
            "schema_version": LAUNCH_RELEASE_SCHEMA_VERSION,
            "launch_token": launch_token,
            "containment_identity": containment_identity,
            "events": [],
            "release_consumed": False,
        }
        encoded = canonical_isolation_json_bytes(document)
        parent_fd, parent_value = _open_private_release_parent(target.parent)
        try:
            fcntl.flock(parent_fd, fcntl.LOCK_EX)
            _revalidate_release_parent(
                target.parent,
                parent_fd,
                expected_device=parent_value.st_dev,
                expected_inode=parent_value.st_ino,
            )
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_CLOEXEC
                | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                fd = os.open(target.name, flags, 0o600, dir_fd=parent_fd)
            except FileExistsError as exc:
                raise ProviderIsolationStateError(
                    "launch release record already exists"
                ) from exc
            except OSError as exc:
                raise ProviderIsolationStateError(
                    "launch release record could not be created"
                ) from exc
            try:
                os.fchmod(fd, 0o600)
                _write_all(fd, encoded)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(parent_fd)
        except ProviderIsolationStateError:
            raise
        except OSError as exc:
            raise ProviderIsolationStateError(
                "launch release record could not be created"
            ) from exc
        finally:
            os.close(parent_fd)
        return cls(
            path=target,
            launch_token=launch_token,
            containment_identity=containment_identity,
            events=(),
            release_consumed=False,
            _expected_document=encoded,
            _parent_device=parent_value.st_dev,
            _parent_inode=parent_value.st_ino,
            _poisoned=False,
        )

    @classmethod
    def load(
        cls,
        path: str | os.PathLike[str],
    ) -> "DurableLaunchReleaseGate":
        target = Path(path)
        if not target.is_absolute():
            target = target.absolute()
        parent_fd, parent_value = _open_private_release_parent(target.parent)
        try:
            fcntl.flock(parent_fd, fcntl.LOCK_SH)
            _revalidate_release_parent(
                target.parent,
                parent_fd,
                expected_device=parent_value.st_dev,
                expected_inode=parent_value.st_ino,
            )
            raw = _read_release_record(parent_fd, target.name)
            document = json.loads(raw)
        except ProviderIsolationStateError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderIsolationStateError(
                "launch release record is unreadable"
            ) from exc
        finally:
            os.close(parent_fd)
        if not isinstance(document, dict) or set(document) != {
            "schema_version",
            "launch_token",
            "containment_identity",
            "events",
            "release_consumed",
        }:
            raise ProviderIsolationStateError(
                "launch release record fields are invalid"
            )
        if document["schema_version"] != LAUNCH_RELEASE_SCHEMA_VERSION:
            raise ProviderIsolationStateError(
                "launch release record version is unsupported"
            )
        try:
            launch_token = _require_digest(
                document["launch_token"], "launch_token"
            )
            containment_identity = _require_digest(
                document["containment_identity"], "containment_identity"
            )
        except TypeError as exc:
            raise ProviderIsolationStateError(
                "launch release record identity is invalid"
            ) from exc
        events_value = document["events"]
        if not isinstance(events_value, list) or any(
            not isinstance(item, str) for item in events_value
        ):
            raise ProviderIsolationStateError(
                "launch release event sequence is invalid"
            )
        events = tuple(events_value)
        if events not in {
            (),
            ("launch_intent",),
            ("launch_intent", "launch_committed"),
        }:
            raise ProviderIsolationStateError(
                "launch release event sequence is ambiguous"
            )
        consumed = document["release_consumed"]
        if not isinstance(consumed, bool) or (
            consumed and events != ("launch_intent", "launch_committed")
        ):
            raise ProviderIsolationStateError(
                "launch release consumption state is invalid"
            )
        canonical = canonical_isolation_json_bytes(document)
        if raw != canonical:
            raise ProviderIsolationStateError(
                "launch release record is not canonical"
            )
        return cls(
            path=target,
            launch_token=launch_token,
            containment_identity=containment_identity,
            events=events,
            release_consumed=consumed,
            _expected_document=canonical,
            _parent_device=parent_value.st_dev,
            _parent_inode=parent_value.st_ino,
            _release_permit=None,
            _poisoned=False,
        )

    def record_intent(self) -> None:
        self._require_usable()
        if self.events != () or self.release_consumed:
            raise ProviderIsolationStateError(
                "launch intent transition is not available"
            )
        next_events = ("launch_intent",)
        encoded = self._persist_transition(
            events=next_events,
            release_consumed=False,
        )
        self.events = next_events
        self._expected_document = encoded

    def record_commit(self) -> str:
        self._require_usable()
        if self.events != ("launch_intent",) or self.release_consumed:
            raise ProviderIsolationStateError(
                "launch commit transition is not available"
            )
        permit = secrets.token_hex(32)
        next_events = ("launch_intent", "launch_committed")
        encoded = self._persist_transition(
            events=next_events,
            release_consumed=False,
        )
        self.events = next_events
        self._expected_document = encoded
        self._release_permit = permit
        return permit

    def consume_release(self, permit: str) -> None:
        self._require_usable()
        if (
            self.events != ("launch_intent", "launch_committed")
            or self.release_consumed
            or self._release_permit is None
            or not secrets.compare_digest(permit, self._release_permit)
        ):
            raise ProviderIsolationStateError(
                "launch release permit is absent, stale, or replayed"
            )
        encoded = self._persist_transition(
            events=self.events,
            release_consumed=True,
        )
        self.release_consumed = True
        self._release_permit = None
        self._expected_document = encoded

    def _require_usable(self) -> None:
        if self._poisoned:
            raise ProviderIsolationStateError(
                "launch release gate is poisoned and unusable"
            )

    def _document(
        self,
        *,
        events: tuple[str, ...] | None = None,
        release_consumed: bool | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": LAUNCH_RELEASE_SCHEMA_VERSION,
            "launch_token": self.launch_token,
            "containment_identity": self.containment_identity,
            "events": list(self.events if events is None else events),
            "release_consumed": (
                self.release_consumed
                if release_consumed is None
                else release_consumed
            ),
        }

    def _persist_transition(
        self,
        *,
        events: tuple[str, ...],
        release_consumed: bool,
    ) -> bytes:
        encoded = canonical_isolation_json_bytes(
            self._document(
                events=events,
                release_consumed=release_consumed,
            )
        )
        parent_fd, _parent_value = _open_private_release_parent(
            self.path.parent,
            expected_device=self._parent_device,
            expected_inode=self._parent_inode,
        )
        temp_name = f".{self.path.name}.{secrets.token_hex(16)}.tmp"
        fd = -1
        replaced = False
        try:
            fcntl.flock(parent_fd, fcntl.LOCK_EX)
            _revalidate_release_parent(
                self.path.parent,
                parent_fd,
                expected_device=self._parent_device,
                expected_inode=self._parent_inode,
            )
            current = _read_release_record(parent_fd, self.path.name)
            if not secrets.compare_digest(current, self._expected_document):
                raise ProviderIsolationStateError(
                    "launch release record changed since load"
                )
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_CLOEXEC
                | getattr(os, "O_NOFOLLOW", 0)
            )
            fd = os.open(temp_name, flags, 0o600, dir_fd=parent_fd)
            os.fchmod(fd, 0o600)
            _write_all(fd, encoded)
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.replace(
                temp_name,
                self.path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            replaced = True
            os.fsync(parent_fd)
            return encoded
        except ProviderIsolationStateError:
            raise
        except OSError as exc:
            if replaced:
                self.events = events
                self.release_consumed = release_consumed
                self._expected_document = encoded
                self._release_permit = None
                self._poisoned = True
                raise ProviderIsolationStateError(
                    "launch release durability failed after visible "
                    "replacement; gate is poisoned"
                ) from exc
            raise ProviderIsolationStateError(
                "launch release transition could not be persisted"
            ) from exc
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            finally:
                os.close(parent_fd)


def _open_private_release_parent(
    path: Path,
    *,
    expected_device: int | None = None,
    expected_inode: int | None = None,
) -> tuple[int, os.stat_result]:
    try:
        fd = os.open(
            path,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise ProviderIsolationStateError(
            "launch release parent is unavailable"
        ) from exc
    try:
        value = os.fstat(fd)
        if (
            not stat.S_ISDIR(value.st_mode)
            or stat.S_IMODE(value.st_mode) & 0o077
            or value.st_uid != os.geteuid()
            or (
                expected_device is not None
                and value.st_dev != expected_device
            )
            or (
                expected_inode is not None
                and value.st_ino != expected_inode
            )
        ):
            raise ProviderIsolationStateError(
                "launch release parent is not private controller authority"
            )
        _revalidate_release_parent(
            path,
            fd,
            expected_device=value.st_dev,
            expected_inode=value.st_ino,
        )
        return fd, value
    except BaseException:
        os.close(fd)
        raise


def _revalidate_release_parent(
    path: Path,
    fd: int,
    *,
    expected_device: int,
    expected_inode: int,
) -> None:
    try:
        descriptor_value = os.fstat(fd)
        pathname_value = path.lstat()
    except OSError as exc:
        raise ProviderIsolationStateError(
            "launch release parent is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(descriptor_value.st_mode)
        or descriptor_value.st_dev != expected_device
        or descriptor_value.st_ino != expected_inode
        or pathname_value.st_dev != expected_device
        or pathname_value.st_ino != expected_inode
        or stat.S_IMODE(descriptor_value.st_mode) & 0o077
        or descriptor_value.st_uid != os.geteuid()
    ):
        raise ProviderIsolationStateError(
            "launch release parent authority changed"
        )


def _read_release_record(parent_fd: int, name: str) -> bytes:
    flags = (
        os.O_RDONLY
        | os.O_CLOEXEC
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise ProviderIsolationStateError(
            "launch release record is unreadable"
        ) from exc
    try:
        value = os.fstat(fd)
        if (
            not stat.S_ISREG(value.st_mode)
            or value.st_nlink != 1
            or stat.S_IMODE(value.st_mode) != 0o600
        ):
            raise ProviderIsolationStateError(
                "launch release record authority is invalid"
            )
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(fd, min(4096, 16_385 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > 16_384:
                raise ProviderIsolationStateError(
                    "launch release record exceeds the byte bound"
                )
        return b"".join(chunks)
    except ProviderIsolationStateError:
        raise
    except OSError as exc:
        raise ProviderIsolationStateError(
            "launch release record is unreadable"
        ) from exc
    finally:
        os.close(fd)


def _write_all(fd: int, value: bytes) -> None:
    view = memoryview(value)
    try:
        offset = 0
        while offset < len(view):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise OSError(errno.EIO, "short write")
            offset += written
    finally:
        view.release()


def _fsync_directory(path: Path) -> None:
    fd = os.open(
        path,
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_CLOEXEC
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
