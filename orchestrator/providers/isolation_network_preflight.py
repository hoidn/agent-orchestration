"""Closed shared-network inventory and denied-endpoint preflight.

The private listener inventory and the probe capability result are separate
content-addressed authorities.  This module intentionally does not integrate
either one with ``ProviderExecutor``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import ctypes
from dataclasses import dataclass, field
import errno
from hashlib import sha256
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import struct
from typing import Any
import unicodedata

from jsonschema import Draft202012Validator

from .isolation import (
    ProviderIsolationIssue,
    canonical_isolation_json_bytes,
    isolation_schema_validation_issues,
    load_provider_isolation_schema,
)
from .isolation_candidate import REQUIRED_CANDIDATE_AUTHORITY_LABELS


NETWORK_INVENTORY_SCHEMA_RESOURCE = (
    "provider-isolation-network-inventory-v1.schema.json"
)
NETWORK_INVENTORY_SCHEMA_VERSION = (
    "provider_isolation_network_inventory.v1"
)
NETWORK_PREFLIGHT_SCHEMA_VERSION = "provider_isolation_network_preflight.v1"
NETWORK_PROBE_SCHEMA_VERSION = "provider_isolation_network_probe.v1"
DENIED_ENDPOINT_SET_SCHEMA_VERSION = (
    "provider_isolation_denied_endpoint_set.v1"
)
CLOUD_METADATA_BASELINE_VERSION = (
    "provider_isolation_cloud_metadata_baseline.v1"
)
CAPABILITY_UNAVAILABLE_CODE = "provider_isolation_capability_unavailable"
LOCAL_SERVICE_EXPOSURE_CODE = "provider_isolation_local_service_exposure"

MAX_NETWORK_LISTENERS = 4096
MAX_NETWORK_INVENTORY_BYTES = 1_048_576
MAX_NETWORK_PREFLIGHT_BYTES = 32_768
MAX_NETWORK_JSON_DEPTH = 64
MAX_NETWORK_JSON_NODES = 65_536
MAX_NETWORK_OWNER_IDENTITY = (1 << 64) - 1
MAX_DENIED_ENDPOINTS = 64
MAX_PROBE_PAYLOAD_BYTES = 4096
MAX_ABSTRACT_NAME_BYTES = 107
MAX_KERNEL_INVENTORY_BYTES = 4 * 1024 * 1024

_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENDPOINT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_LOWER_HEX_PATTERN = re.compile(r"^(?:[0-9a-f]{2})*$")
_AT_EMPTY_PATH = 0x1000

_NETLINK_SOCK_DIAG = 4
_SOCK_DIAG_BY_FAMILY = 20
_NLM_F_REQUEST = 0x1
_NLM_F_DUMP = 0x300
_NLMSG_ERROR = 2
_NLMSG_DONE = 3
_UNIX_DIAG_NAME_REQUEST = 0x1
_UNIX_DIAG_NAME_ATTRIBUTE = 0
_TCP_LISTEN_STATE = 0x0A

REQUIRED_NETWORK_DENIED_AUTHORITY_LABELS = (
    "candidate",
    *REQUIRED_CANDIDATE_AUTHORITY_LABELS,
)
UNLISTED_REACHABILITY_ASSUMPTION = (
    "all_unlisted_local_and_remote_reachability_is_a_"
    "deployment_trust_assumption"
)
_CLOUD_METADATA_BASELINE = (
    {
        "id": "cloud-metadata-alibaba-ipv4",
        "protocol": "tcp",
        "family": "ipv4",
        "address": "100.100.100.200",
        "port": 80,
    },
    {
        "id": "cloud-metadata-container-credentials-ipv4",
        "protocol": "tcp",
        "family": "ipv4",
        "address": "169.254.170.2",
        "port": 80,
    },
    {
        "id": "cloud-metadata-link-local-ipv4",
        "protocol": "tcp",
        "family": "ipv4",
        "address": "169.254.169.254",
        "port": 80,
    },
    {
        "id": "cloud-metadata-link-local-ipv6",
        "protocol": "tcp",
        "family": "ipv6",
        "address": "fd00:ec2::254",
        "port": 80,
    },
    {
        "id": "cloud-metadata-pod-identity-ipv4",
        "protocol": "tcp",
        "family": "ipv4",
        "address": "169.254.170.23",
        "port": 80,
    },
)
CLOUD_METADATA_BASELINE_ENDPOINT_IDS = tuple(
    sorted(
        (row["id"] for row in _CLOUD_METADATA_BASELINE),
        key=lambda value: value.encode("utf-8"),
    )
)


@dataclass(frozen=True, slots=True)
class ProviderIsolationNetworkInventory:
    """One canonical private listener inventory."""

    schema_version: str
    canonical_json: bytes = field(repr=False)
    digest: str

    @property
    def listener_count(self) -> int:
        return len(self.to_dict()["listeners"])

    def to_dict(self) -> dict[str, Any]:
        try:
            value = json.loads(self.canonical_json)
        except (ValueError, RecursionError, MemoryError) as exc:
            raise _error(
                "$.inventory",
                "network inventory canonical bytes are invalid",
            ) from exc
        if not isinstance(value, dict):
            raise _error("$.inventory", "network inventory is not an object")
        return value


@dataclass(frozen=True, slots=True)
class ProviderIsolationNetworkInventoryArtifact:
    """Exact private path and digest of one published inventory."""

    path: Path
    digest: str


@dataclass(frozen=True, slots=True)
class _ProviderIsolationNetworkRevalidatedArtifact:
    """Reviewed artifact paired with its mandatory live recapture."""

    reviewed: ProviderIsolationNetworkInventoryArtifact = field(repr=False)
    inventory: ProviderIsolationNetworkInventory = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProviderIsolationNetworkProbeResult:
    """One safe result from the closed effective denied-endpoint set."""

    endpoint_id: str
    protocol: str
    status: str
    match_code: str

    def to_dict(self) -> dict[str, str]:
        return {
            "endpoint_id": self.endpoint_id,
            "protocol": self.protocol,
            "status": self.status,
            "match_code": self.match_code,
        }


@dataclass(frozen=True, slots=True)
class ProviderIsolationNetworkProbe:
    """Typed binding between the mandatory endpoint set and safe results."""

    schema_version: str
    endpoint_set_schema_version: str
    cloud_metadata_baseline_version: str
    endpoint_set_canonical_json: bytes = field(repr=False)
    endpoint_set_digest: str
    endpoint_count: int
    results: tuple[ProviderIsolationNetworkProbeResult, ...]


@dataclass(frozen=True, slots=True)
class ProviderIsolationNetworkPreflight:
    """Canonical capability result bound to a reviewed inventory."""

    schema_version: str
    endpoint_set_digest: str
    canonical_json: bytes = field(repr=False)
    digest: str

    def to_dict(self) -> dict[str, Any]:
        try:
            value = json.loads(self.canonical_json)
        except (ValueError, RecursionError, MemoryError) as exc:
            raise _error(
                "$.network_preflight",
                "network preflight canonical bytes are invalid",
            ) from exc
        if not isinstance(value, dict):
            raise _error(
                "$.network_preflight",
                "network preflight is not an object",
            )
        return value


_NETWORK_AUTHORITY_CONSTRUCTION_TOKEN = object()


class PinnedProviderIsolationNetworkAuthority:
    """Pinned reviewed network capability with mandatory live revalidation."""

    __slots__ = (
        "_capability",
        "_decision",
        "_denied_authorities",
        "_reviewed_artifact",
        "_runtime_endpoints_json",
        "_timeout_seconds",
    )

    def __init__(
        self,
        *,
        capability: ProviderIsolationNetworkPreflight | None = None,
        reviewed_artifact: ProviderIsolationNetworkInventoryArtifact | None = None,
        denied_authorities: tuple[tuple[str, Path], ...] = (),
        runtime_endpoints_json: bytes = b"",
        timeout_seconds: float = 0,
        decision: str = "",
        _construction_token: object | None = None,
    ) -> None:
        if _construction_token is not _NETWORK_AUTHORITY_CONSTRUCTION_TOKEN:
            raise TypeError(
                "network authority must be created by "
                "pin_provider_isolation_network_preflight"
            )
        if (
            type(capability) is not ProviderIsolationNetworkPreflight
            or type(reviewed_artifact)
            is not ProviderIsolationNetworkInventoryArtifact
        ):
            raise TypeError("network authority construction state is invalid")
        object.__setattr__(self, "_capability", capability)
        object.__setattr__(self, "_reviewed_artifact", reviewed_artifact)
        object.__setattr__(self, "_denied_authorities", denied_authorities)
        object.__setattr__(
            self,
            "_runtime_endpoints_json",
            runtime_endpoints_json,
        )
        object.__setattr__(self, "_timeout_seconds", timeout_seconds)
        object.__setattr__(self, "_decision", decision)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("pinned network authority is immutable")

    @property
    def capability(self) -> ProviderIsolationNetworkPreflight:
        """Return the safe path-free capability pinned by this authority."""

        return self._capability

    def revalidate(self) -> ProviderIsolationNetworkPreflight:
        """Repeat reload, live recapture, and probes and require exact bytes."""

        try:
            runtime_endpoints = json.loads(self._runtime_endpoints_json)
        except (ValueError, RecursionError, MemoryError) as exc:
            raise _error(
                "$.network_authority",
                "pinned runtime endpoint authority is invalid",
            ) from exc
        if not isinstance(runtime_endpoints, list):
            raise _error(
                "$.network_authority",
                "pinned runtime endpoint authority is invalid",
            )
        capability = _perform_provider_isolation_network_preflight(
            reviewed_artifact=self._reviewed_artifact,
            denied_authorities=dict(self._denied_authorities),
            runtime_endpoints=runtime_endpoints,
            timeout_seconds=self._timeout_seconds,
            decision=self._decision,
        )
        pinned = self._capability
        if (
            type(pinned) is not ProviderIsolationNetworkPreflight
            or capability.digest != pinned.digest
            or capability.canonical_json != pinned.canonical_json
        ):
            raise _error(
                "$.network_preflight_digest",
                "live network preflight differs from pinned capability bytes",
            )
        return capability


class ProviderIsolationNetworkPreflightError(ValueError):
    """Fail-closed inventory, authority, or denied-endpoint rejection."""

    def __init__(
        self,
        issues: Sequence[ProviderIsolationIssue],
        *,
        code: str | None = None,
    ):
        self.issues = tuple(issues)
        self.code = code or (
            self.issues[0].code
            if self.issues
            else CAPABILITY_UNAVAILABLE_CODE
        )
        detail = "; ".join(
            f"{issue.path}: {issue.message}" for issue in self.issues
        )
        super().__init__(f"{self.code}: {detail}")


@dataclass(frozen=True, slots=True)
class _AuthorityEdge:
    parent_fd: int
    child_fd: int
    name: str
    opened_stat: os.stat_result


@dataclass(slots=True)
class _PinnedPrivateDirectory:
    requested_path: Path
    directory_fd: int
    directory_stat: os.stat_result
    root_fd: int
    root_stat: os.stat_result
    owned_fds: list[int]
    edges: tuple[_AuthorityEdge, ...]

    def revalidate(self) -> None:
        root_opened = os.fstat(self.root_fd)
        _require_same_identity(
            self.root_stat,
            root_opened,
            root_opened,
            path="$.inventory_path",
        )
        _require_trusted_ancestor(root_opened)
        for edge in self.edges:
            opened = os.fstat(edge.child_fd)
            linked = os.stat(
                edge.name,
                dir_fd=edge.parent_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(linked.st_mode):
                raise _error(
                    "$.inventory_path",
                    "private inventory authority edge is not a directory",
                )
            _require_same_identity(
                edge.opened_stat,
                opened,
                linked,
                path="$.inventory_path",
            )
            if edge.child_fd != self.directory_fd:
                _require_trusted_ancestor(opened)
        _require_private_directory_binding(
            self.requested_path,
            self.directory_fd,
            self.directory_stat,
        )

    def close(self) -> None:
        for descriptor in reversed(self.owned_fds):
            try:
                os.close(descriptor)
            except OSError:
                pass
        self.owned_fds.clear()
        self.directory_fd = -1
        self.root_fd = -1


def validate_provider_isolation_network_inventory(
    document: object,
    *,
    expected_digest: str | None = None,
) -> tuple[ProviderIsolationIssue, ...]:
    """Return every deterministic closed inventory issue."""

    structure_issues = _iterative_network_json_structure_issues(document)
    if structure_issues:
        return structure_issues
    semantic_issues = (
        _inventory_semantic_issues(document)
        if isinstance(document, Mapping)
        else []
    )
    if semantic_issues:
        return _deduplicate_issues(semantic_issues)
    schema = load_provider_isolation_schema(
        NETWORK_INVENTORY_SCHEMA_RESOURCE
    )
    validator = Draft202012Validator(schema)
    issues = list(
        isolation_schema_validation_issues(
            validator.iter_errors(document),
            error_code=CAPABILITY_UNAVAILABLE_CODE,
        )
    )
    issues = list(_deduplicate_issues(issues))
    if expected_digest is not None:
        if (
            not isinstance(expected_digest, str)
            or _DIGEST_PATTERN.fullmatch(expected_digest) is None
        ):
            issues.append(
                _issue(
                    "$.inventory_digest",
                    "expected inventory identity must be canonical sha256",
                )
            )
        elif not issues:
            try:
                normalized = _normalized_inventory_document(document)
                actual = _digest(canonical_isolation_json_bytes(normalized))
            except (TypeError, ValueError, RecursionError, MemoryError):
                issues.append(
                    _issue(
                        "$.inventory",
                        "network inventory cannot be canonicalized safely",
                    )
                )
            else:
                if actual != expected_digest:
                    issues.append(
                        _issue(
                            "$.inventory_digest",
                            "network inventory identity does not match expected digest",
                        )
                    )
    return _deduplicate_issues(issues)


def load_provider_isolation_network_inventory(
    document: Mapping[str, Any],
    *,
    expected_digest: str | None = None,
) -> ProviderIsolationNetworkInventory:
    """Validate and load one canonical private inventory."""

    issues = validate_provider_isolation_network_inventory(
        document,
        expected_digest=expected_digest,
    )
    if issues:
        raise ProviderIsolationNetworkPreflightError(issues)
    try:
        normalized = _normalized_inventory_document(document)
        canonical_json = canonical_isolation_json_bytes(normalized)
    except (TypeError, ValueError, RecursionError, MemoryError) as exc:
        raise _error(
            "$.inventory",
            "network inventory cannot be canonicalized safely",
        ) from exc
    if len(canonical_json) > MAX_NETWORK_INVENTORY_BYTES:
        raise _error(
            "$.listeners",
            "canonical network inventory exceeds its byte bound",
        )
    return ProviderIsolationNetworkInventory(
        schema_version=NETWORK_INVENTORY_SCHEMA_VERSION,
        canonical_json=canonical_json,
        digest=_digest(canonical_json),
    )


def capture_provider_isolation_network_inventory(
    *,
    proc_net_root: str | os.PathLike[str] = "/proc/net",
) -> ProviderIsolationNetworkInventory:
    """Capture current INET and byte-safe abstract AF_UNIX listeners."""

    try:
        root = _canonical_absolute_path(
            proc_net_root,
            path="$.kernel_inventory",
        )
        listeners: list[dict[str, Any]] = []
        for filename, protocol, family in (
            ("tcp", "tcp", "ipv4"),
            ("tcp6", "tcp", "ipv6"),
            ("udp", "udp", "ipv4"),
            ("udp6", "udp", "ipv6"),
        ):
            listeners.extend(
                _capture_proc_inet_listeners(
                    root / filename,
                    protocol=protocol,
                    family=family,
                )
            )
        listeners.extend(_capture_abstract_unix_listeners())
        if len(listeners) > MAX_NETWORK_LISTENERS:
            raise _error(
                "$.listeners",
                "kernel listener inventory exceeds its entry bound",
            )
        return load_provider_isolation_network_inventory(
            {
                "schema_version": NETWORK_INVENTORY_SCHEMA_VERSION,
                "listeners": listeners,
            }
        )
    except ProviderIsolationNetworkPreflightError:
        raise
    except (OSError, ValueError, struct.error) as exc:
        raise _error(
            "$.kernel_inventory",
            "trusted kernel listener inventory is unavailable",
        ) from exc


def publish_provider_isolation_network_inventory(
    inventory: ProviderIsolationNetworkInventory | Mapping[str, Any],
    output_path: str | os.PathLike[str],
    *,
    denied_authorities: Mapping[str, str | os.PathLike[str]],
) -> ProviderIsolationNetworkInventoryArtifact:
    """Atomically publish a new private single-link inventory file."""

    _require_closed_denied_authority_inventory(denied_authorities)
    loaded = (
        inventory
        if isinstance(inventory, ProviderIsolationNetworkInventory)
        else load_provider_isolation_network_inventory(inventory)
    )
    output = _canonical_absolute_path(
        output_path,
        path="$.inventory_path",
    )
    if output.name in {"", ".", ".."}:
        raise _error("$.inventory_path", "inventory output basename is invalid")
    authority: _PinnedPrivateDirectory | None = None
    try:
        authority = _open_private_directory(output.parent)
        _require_disjoint_authorities(
            authority.requested_path,
            denied_authorities,
        )
        _require_absent(authority.directory_fd, output.name)

        def revalidate() -> None:
            assert authority is not None
            authority.revalidate()
            _require_disjoint_authorities(
                authority.requested_path,
                denied_authorities,
            )

        _publish_private_bytes(
            authority.directory_fd,
            output.name,
            loaded.canonical_json,
            authority_check=revalidate,
        )
        return ProviderIsolationNetworkInventoryArtifact(
            path=output,
            digest=loaded.digest,
        )
    except ProviderIsolationNetworkPreflightError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise _error(
            "$.inventory_path",
            "private inventory publication failed closed",
        ) from exc
    finally:
        if authority is not None:
            authority.close()


def load_provider_isolation_network_inventory_file(
    inventory_path: str | os.PathLike[str],
    *,
    expected_digest: str,
    denied_authorities: Mapping[str, str | os.PathLike[str]],
) -> ProviderIsolationNetworkInventory:
    """Load and revalidate one exact private inventory path and digest."""

    _require_closed_denied_authority_inventory(denied_authorities)
    output = _canonical_absolute_path(
        inventory_path,
        path="$.inventory_path",
    )
    authority: _PinnedPrivateDirectory | None = None
    inventory_fd: int | None = None
    try:
        authority = _open_private_directory(output.parent)
        _require_disjoint_authorities(
            authority.requested_path,
            denied_authorities,
        )
        before = os.stat(
            output.name,
            dir_fd=authority.directory_fd,
            follow_symlinks=False,
        )
        _require_private_inventory_stat(before)
        inventory_fd = os.open(
            output.name,
            os.O_RDONLY
            | os.O_NONBLOCK
            | os.O_CLOEXEC
            | os.O_NOFOLLOW,
            dir_fd=authority.directory_fd,
        )
        opened = os.fstat(inventory_fd)
        _require_same_identity(
            before,
            opened,
            opened,
            path="$.inventory_path",
        )
        _require_private_inventory_fd(inventory_fd)
        content = _read_bounded(
            inventory_fd,
            limit=MAX_NETWORK_INVENTORY_BYTES,
        )
        after_fd = os.fstat(inventory_fd)
        after_path = os.stat(
            output.name,
            dir_fd=authority.directory_fd,
            follow_symlinks=False,
        )
        _require_same_identity(
            before,
            after_fd,
            after_path,
            path="$.inventory_path",
        )
        _require_private_inventory_fd(inventory_fd)
        authority.revalidate()
        _require_disjoint_authorities(
            authority.requested_path,
            denied_authorities,
        )
        try:
            document = json.loads(content)
        except (ValueError, RecursionError, MemoryError) as exc:
            raise _error(
                "$.inventory",
                "private inventory is not bounded canonical UTF-8 JSON",
            ) from exc
        if not isinstance(document, Mapping):
            raise _error("$.inventory", "private inventory must be an object")
        inventory = load_provider_isolation_network_inventory(
            document,
            expected_digest=expected_digest,
        )
        if content != inventory.canonical_json:
            raise _error(
                "$.inventory",
                "private inventory bytes are not canonical",
            )
        return inventory
    except ProviderIsolationNetworkPreflightError:
        raise
    except (FileNotFoundError, NotADirectoryError, OSError, TypeError) as exc:
        raise _error(
            "$.inventory_path",
            "private inventory authority is unavailable",
        ) from exc
    finally:
        if inventory_fd is not None:
            os.close(inventory_fd)
        if authority is not None:
            authority.close()


def _revalidate_provider_isolation_network_inventory(
    reviewed_artifact: ProviderIsolationNetworkInventoryArtifact,
    *,
    denied_authorities: Mapping[str, str | os.PathLike[str]],
) -> _ProviderIsolationNetworkRevalidatedArtifact:
    """Require reviewed bytes and a fresh inventory to remain identical."""

    _require_closed_denied_authority_inventory(denied_authorities)
    if type(reviewed_artifact) is not ProviderIsolationNetworkInventoryArtifact:
        raise _error(
            "$.inventory",
            "live revalidation requires a typed reviewed inventory artifact",
        )
    reviewed = load_provider_isolation_network_inventory_file(
        reviewed_artifact.path,
        expected_digest=reviewed_artifact.digest,
        denied_authorities=denied_authorities,
    )
    current = capture_provider_isolation_network_inventory()
    if not isinstance(current, ProviderIsolationNetworkInventory):
        raise _error(
            "$.kernel_inventory",
            "live kernel inventory must be canonical and validated",
        )
    if current.canonical_json != reviewed.canonical_json:
        raise _error(
            "$.kernel_inventory",
            "live listener inventory differs from reviewed bytes",
        )
    repeated = load_provider_isolation_network_inventory_file(
        reviewed_artifact.path,
        expected_digest=reviewed_artifact.digest,
        denied_authorities=denied_authorities,
    )
    if repeated.canonical_json != reviewed.canonical_json:
        raise _error(
            "$.inventory",
            "reviewed inventory changed during revalidation",
        )
    return _ProviderIsolationNetworkRevalidatedArtifact(
        reviewed=reviewed_artifact,
        inventory=repeated,
    )


def probe_provider_isolation_network_endpoints(
    runtime_endpoints: Sequence[Mapping[str, Any]],
    *,
    timeout_seconds: float,
) -> ProviderIsolationNetworkProbe:
    """Probe the mandatory metadata baseline plus runtime-known endpoints."""

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
        or timeout_seconds > 5
        or not math.isfinite(float(timeout_seconds))
    ):
        raise _error(
            "$.timeout_seconds",
            "probe timeout must be within the bounded (0, 5] interval",
        )
    normalized = _effective_denied_endpoints(runtime_endpoints)
    endpoint_document = _endpoint_set_document(normalized)
    endpoint_canonical_json = canonical_isolation_json_bytes(endpoint_document)
    results: list[dict[str, str]] = []
    for endpoint in normalized:
        protocol = endpoint["protocol"]
        try:
            if protocol == "tcp":
                match_code = _probe_stream_inet(
                    endpoint,
                    timeout_seconds=float(timeout_seconds),
                )
            elif protocol == "abstract_unix":
                match_code = _probe_stream_abstract_unix(
                    endpoint,
                    timeout_seconds=float(timeout_seconds),
                )
            elif protocol == "udp":
                match_code = _probe_udp(
                    endpoint,
                    timeout_seconds=float(timeout_seconds),
                )
            else:  # pragma: no cover - normalization invariant
                raise AssertionError(f"unknown endpoint protocol {protocol!r}")
        except ProviderIsolationNetworkPreflightError:
            raise
        except (OSError, OverflowError, ValueError) as exc:
            raise _error(
                f"$.endpoints[{endpoint['id']}]",
                "denied endpoint socket probe is unavailable",
            ) from exc
        results.append(
            {
                "endpoint_id": endpoint["id"],
                "protocol": protocol,
                "status": "not_reachable",
                "match_code": match_code,
            }
        )
    normalized_results = _normalize_probe_results(
        results,
        endpoints=normalized,
    )
    return ProviderIsolationNetworkProbe(
        schema_version=NETWORK_PROBE_SCHEMA_VERSION,
        endpoint_set_schema_version=DENIED_ENDPOINT_SET_SCHEMA_VERSION,
        cloud_metadata_baseline_version=CLOUD_METADATA_BASELINE_VERSION,
        endpoint_set_canonical_json=endpoint_canonical_json,
        endpoint_set_digest=_digest(endpoint_canonical_json),
        endpoint_count=len(normalized),
        results=tuple(
            ProviderIsolationNetworkProbeResult(**result)
            for result in normalized_results
        ),
    )


def pin_provider_isolation_network_preflight(
    *,
    reviewed_artifact: ProviderIsolationNetworkInventoryArtifact,
    denied_authorities: Mapping[str, str | os.PathLike[str]],
    runtime_endpoints: Sequence[Mapping[str, Any]],
    timeout_seconds: float,
    decision: str,
) -> PinnedProviderIsolationNetworkAuthority:
    """Pin one reviewed capability and all inputs needed to reproduce it."""

    if type(reviewed_artifact) is not ProviderIsolationNetworkInventoryArtifact:
        raise _error(
            "$.inventory",
            "network authority requires a typed reviewed inventory artifact",
        )
    _require_closed_denied_authority_inventory(denied_authorities)
    normalized_denied_authorities = tuple(
        (
            label,
            _canonical_absolute_path(
                denied_authorities[label],
                path=f"$.denied_authorities[{label}]",
            ),
        )
        for label in REQUIRED_NETWORK_DENIED_AUTHORITY_LABELS
    )
    normalized_runtime_endpoints = _normalize_endpoints(runtime_endpoints)
    normalized_artifact = ProviderIsolationNetworkInventoryArtifact(
        path=_canonical_absolute_path(
            reviewed_artifact.path,
            path="$.inventory_path",
        ),
        digest=reviewed_artifact.digest,
    )
    capability = _perform_provider_isolation_network_preflight(
        reviewed_artifact=normalized_artifact,
        denied_authorities=dict(normalized_denied_authorities),
        runtime_endpoints=normalized_runtime_endpoints,
        timeout_seconds=timeout_seconds,
        decision=decision,
    )
    return PinnedProviderIsolationNetworkAuthority(
        capability=capability,
        reviewed_artifact=normalized_artifact,
        denied_authorities=normalized_denied_authorities,
        runtime_endpoints_json=canonical_isolation_json_bytes(
            normalized_runtime_endpoints
        ),
        timeout_seconds=float(timeout_seconds),
        decision=decision,
        _construction_token=_NETWORK_AUTHORITY_CONSTRUCTION_TOKEN,
    )


def _perform_provider_isolation_network_preflight(
    *,
    reviewed_artifact: ProviderIsolationNetworkInventoryArtifact,
    denied_authorities: Mapping[str, str | os.PathLike[str]],
    runtime_endpoints: Sequence[Mapping[str, Any]],
    timeout_seconds: float,
    decision: str,
) -> ProviderIsolationNetworkPreflight:
    inventory = _revalidate_provider_isolation_network_inventory(
        reviewed_artifact,
        denied_authorities=denied_authorities,
    )
    probe = probe_provider_isolation_network_endpoints(
        runtime_endpoints,
        timeout_seconds=timeout_seconds,
    )
    return _build_provider_isolation_network_preflight(
        inventory=inventory,
        decision=decision,
        probe=probe,
    )


def _build_provider_isolation_network_preflight(
    *,
    inventory: _ProviderIsolationNetworkRevalidatedArtifact,
    decision: str,
    probe: ProviderIsolationNetworkProbe,
) -> ProviderIsolationNetworkPreflight:
    """Build one deterministic capability record bound to reviewed inventory."""

    if type(inventory) is not _ProviderIsolationNetworkRevalidatedArtifact:
        raise _error(
            "$.inventory",
            "capability construction requires a typed live-revalidated inventory",
        )
    if (
        not isinstance(inventory.reviewed, ProviderIsolationNetworkInventoryArtifact)
        or not isinstance(inventory.inventory, ProviderIsolationNetworkInventory)
        or inventory.reviewed.digest != inventory.inventory.digest
        or inventory.inventory.schema_version != NETWORK_INVENTORY_SCHEMA_VERSION
        or _DIGEST_PATTERN.fullmatch(inventory.inventory.digest) is None
    ):
        raise _error("$.inventory", "revalidated inventory binding is inconsistent")
    if decision != "accept_unlisted_reachability":
        raise _error(
            "$.inventory.decision",
            "network review decision is not the closed v1 value",
        )
    normalized_results = _validate_probe_binding(probe)
    document = {
        "schema_version": NETWORK_PREFLIGHT_SCHEMA_VERSION,
        "inventory": {
            "digest": inventory.inventory.digest,
            "listener_counts": _listener_counts(inventory.inventory),
            "decision": decision,
            "unlisted_reachability_assumption": (
                UNLISTED_REACHABILITY_ASSUMPTION
            ),
        },
        "endpoint_set_digest": probe.endpoint_set_digest,
        "probe_results": normalized_results,
    }
    canonical_json = canonical_isolation_json_bytes(document)
    if len(canonical_json) > MAX_NETWORK_PREFLIGHT_BYTES:
        raise _error(
            "$",
            "canonical network preflight exceeds its public byte bound",
        )
    return ProviderIsolationNetworkPreflight(
        schema_version=NETWORK_PREFLIGHT_SCHEMA_VERSION,
        endpoint_set_digest=probe.endpoint_set_digest,
        canonical_json=canonical_json,
        digest=_digest(canonical_json),
    )


def _inventory_semantic_issues(
    document: Mapping[str, Any],
) -> list[ProviderIsolationIssue]:
    issues: list[ProviderIsolationIssue] = []
    listeners = document.get("listeners")
    if not isinstance(listeners, list):
        return issues
    seen: set[bytes] = set()
    for index, row in enumerate(listeners):
        path = f"$.listeners[{index}]"
        if not isinstance(row, Mapping):
            continue
        owner = row.get("owner")
        if isinstance(owner, Mapping):
            for field_name in ("uid", "inode"):
                if field_name not in owner:
                    continue
                identity = owner[field_name]
                if (
                    type(identity) is int
                    and not 0 <= identity <= MAX_NETWORK_OWNER_IDENTITY
                ):
                    issues.append(
                        _issue(
                            f"{path}.owner.{field_name}",
                            "owner identity must be an unsigned 64-bit integer",
                        )
                    )
        kind = row.get("kind")
        if kind == "inet":
            family = row.get("family")
            address = row.get("address")
            if isinstance(address, str) and family in {"ipv4", "ipv6"}:
                try:
                    parsed = ipaddress.ip_address(address)
                except ValueError:
                    issues.append(_issue(f"{path}.address", "IP address is invalid"))
                else:
                    expected_version = 4 if family == "ipv4" else 6
                    if parsed.version != expected_version or str(parsed) != address:
                        issues.append(
                            _issue(
                                f"{path}.address",
                                "IP address is not canonical for its family",
                            )
                        )
        elif kind == "abstract_unix":
            name_hex = row.get("name_hex")
            name_length = row.get("name_length")
            if isinstance(name_hex, str) and isinstance(name_length, int):
                if (
                    _LOWER_HEX_PATTERN.fullmatch(name_hex) is None
                    or len(name_hex) // 2 != name_length
                ):
                    issues.append(
                        _issue(
                            f"{path}.name_length",
                            "abstract name hex and exact byte length disagree",
                        )
                    )
        try:
            identity = canonical_isolation_json_bytes(dict(row))
        except (TypeError, ValueError):
            continue
        if identity in seen:
            issues.append(_issue(path, "listener row must be unique"))
        seen.add(identity)
    return issues


def _normalized_inventory_document(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = deepcopy(dict(document))
    listeners = normalized["listeners"]
    listeners.sort(key=_listener_sort_key)
    return normalized


def _listener_sort_key(row: Mapping[str, Any]) -> tuple[object, ...]:
    owner = row["owner"]
    if row["kind"] == "abstract_unix":
        return (
            0,
            row["socket_type"],
            bytes.fromhex(row["name_hex"]),
            owner["inode"],
            owner.get("uid", -1),
        )
    return (
        1,
        0 if row["protocol"] == "tcp" else 1,
        0 if row["family"] == "ipv4" else 1,
        ipaddress.ip_address(row["address"]).packed,
        row["port"],
        owner["inode"],
        owner.get("uid", -1),
    )


def _capture_proc_inet_listeners(
    path: Path,
    *,
    protocol: str,
    family: str,
) -> list[dict[str, Any]]:
    content = _read_bounded_path(path, limit=MAX_KERNEL_INVENTORY_BYTES)
    try:
        lines = content.decode("ascii", "strict").splitlines()
    except UnicodeDecodeError as exc:
        raise _error(
            "$.kernel_inventory",
            "INET kernel inventory is not canonical ASCII",
        ) from exc
    listeners: list[dict[str, Any]] = []
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 10:
            raise _error(
                "$.kernel_inventory",
                "INET kernel inventory row is malformed",
            )
        local = fields[1]
        state = fields[3]
        if protocol == "tcp" and state != "0A":
            continue
        if protocol == "udp" and state != "07":
            continue
        try:
            encoded_address, encoded_port = local.split(":", 1)
            port = int(encoded_port, 16)
            uid = int(fields[7], 10)
            inode = int(fields[9], 10)
            address = _decode_proc_inet_address(
                encoded_address,
                family=family,
            )
        except (ValueError, IndexError) as exc:
            raise _error(
                "$.kernel_inventory",
                "INET kernel inventory row is malformed",
            ) from exc
        if port == 0:
            continue
        listeners.append(
            {
                "kind": "inet",
                "protocol": protocol,
                "family": family,
                "address": address,
                "port": port,
                "owner": {"uid": uid, "inode": inode},
            }
        )
    return listeners


def _decode_proc_inet_address(encoded: str, *, family: str) -> str:
    raw = bytes.fromhex(encoded)
    if family == "ipv4":
        if len(raw) != 4:
            raise ValueError("invalid proc IPv4 address")
        raw = raw[::-1]
    else:
        if len(raw) != 16:
            raise ValueError("invalid proc IPv6 address")
        raw = b"".join(
            raw[offset : offset + 4][::-1]
            for offset in range(0, 16, 4)
        )
    return str(ipaddress.ip_address(raw))


def _capture_abstract_unix_listeners() -> list[dict[str, Any]]:
    request_sequence = 1
    request = struct.pack(
        "=IHHII",
        16 + 24,
        _SOCK_DIAG_BY_FAMILY,
        _NLM_F_REQUEST | _NLM_F_DUMP,
        request_sequence,
        0,
    ) + struct.pack(
        "=BBHIIIII",
        socket.AF_UNIX,
        0,
        0,
        0xFFFFFFFF,
        0,
        _UNIX_DIAG_NAME_REQUEST,
        0xFFFFFFFF,
        0xFFFFFFFF,
    )
    listeners: list[dict[str, Any]] = []
    total_bytes = 0
    with socket.socket(
        socket.AF_NETLINK,
        socket.SOCK_RAW,
        _NETLINK_SOCK_DIAG,
    ) as diagnostic:
        diagnostic.set_inheritable(False)
        diagnostic.settimeout(1.0)
        diagnostic.bind((0, 0))
        diagnostic.send(request)
        done = False
        while not done:
            block = diagnostic.recv(1 << 20)
            total_bytes += len(block)
            if total_bytes > MAX_KERNEL_INVENTORY_BYTES:
                raise _error(
                    "$.kernel_inventory",
                    "AF_UNIX kernel inventory exceeds its byte bound",
                )
            offset = 0
            while offset + 16 <= len(block):
                length, message_type, _flags, sequence, _pid = struct.unpack_from(
                    "=IHHII",
                    block,
                    offset,
                )
                if length < 16 or offset + length > len(block):
                    raise _error(
                        "$.kernel_inventory",
                        "AF_UNIX diagnostic response is malformed",
                    )
                payload = block[offset + 16 : offset + length]
                if sequence != request_sequence:
                    raise _error(
                        "$.kernel_inventory",
                        "AF_UNIX diagnostic sequence changed",
                    )
                if message_type == _NLMSG_DONE:
                    done = True
                    break
                if message_type == _NLMSG_ERROR:
                    error = (
                        struct.unpack_from("=i", payload, 0)[0]
                        if len(payload) >= 4
                        else -errno.EPROTO
                    )
                    if error != 0:
                        raise OSError(-error, os.strerror(-error))
                elif message_type == _SOCK_DIAG_BY_FAMILY:
                    row = _parse_unix_diag_message(payload)
                    if row is not None:
                        listeners.append(row)
                offset += _aligned(length)
            if offset > len(block):
                raise _error(
                    "$.kernel_inventory",
                    "AF_UNIX diagnostic framing is malformed",
                )
    return listeners


def _parse_unix_diag_message(
    payload: bytes,
) -> dict[str, Any] | None:
    if len(payload) < 16:
        raise _error(
            "$.kernel_inventory",
            "AF_UNIX diagnostic row is truncated",
        )
    family, socket_type, state, _pad, inode, _cookie0, _cookie1 = (
        struct.unpack_from("=BBBBIII", payload, 0)
    )
    if family != socket.AF_UNIX:
        raise _error(
            "$.kernel_inventory",
            "AF_UNIX diagnostic family changed",
        )
    type_name = {
        socket.SOCK_STREAM: "stream",
        socket.SOCK_DGRAM: "datagram",
        socket.SOCK_SEQPACKET: "seqpacket",
    }.get(socket_type)
    if type_name is None:
        return None
    if type_name in {"stream", "seqpacket"} and state != _TCP_LISTEN_STATE:
        return None
    name: bytes | None = None
    offset = 16
    while offset + 4 <= len(payload):
        attribute_length, attribute_type = struct.unpack_from(
            "=HH",
            payload,
            offset,
        )
        if (
            attribute_length < 4
            or offset + attribute_length > len(payload)
        ):
            raise _error(
                "$.kernel_inventory",
                "AF_UNIX diagnostic attribute is malformed",
            )
        if attribute_type == _UNIX_DIAG_NAME_ATTRIBUTE:
            name = payload[offset + 4 : offset + attribute_length]
        offset += _aligned(attribute_length)
    if name is None or not name.startswith(b"\x00"):
        return None
    abstract_payload = name[1:]
    if len(abstract_payload) > MAX_ABSTRACT_NAME_BYTES:
        raise _error(
            "$.kernel_inventory",
            "abstract AF_UNIX name exceeds its byte bound",
        )
    return {
        "kind": "abstract_unix",
        "protocol": "unix",
        "socket_type": type_name,
        "name_hex": abstract_payload.hex(),
        "name_length": len(abstract_payload),
        "owner": {"inode": inode},
    }


def _open_private_directory(path: Path) -> _PinnedPrivateDirectory:
    owned_fds: list[int] = []
    edges: list[_AuthorityEdge] = []
    try:
        root_fd = os.open(
            "/",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        owned_fds.append(root_fd)
        root_stat = os.fstat(root_fd)
        _require_trusted_ancestor(root_stat)
        current_fd = root_fd
        for component in path.parts[1:]:
            before = os.stat(
                component,
                dir_fd=current_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(before.st_mode):
                raise _error(
                    "$.inventory_path",
                    "private inventory authority has a non-directory ancestor",
                )
            child_fd = os.open(
                component,
                os.O_RDONLY
                | os.O_DIRECTORY
                | os.O_NOFOLLOW
                | os.O_CLOEXEC,
                dir_fd=current_fd,
            )
            owned_fds.append(child_fd)
            opened = os.fstat(child_fd)
            _require_same_identity(
                before,
                opened,
                before,
                path="$.inventory_path",
            )
            edges.append(
                _AuthorityEdge(
                    parent_fd=current_fd,
                    child_fd=child_fd,
                    name=component,
                    opened_stat=opened,
                )
            )
            current_fd = child_fd
        directory_stat = os.fstat(current_fd)
        authority = _PinnedPrivateDirectory(
            requested_path=path,
            directory_fd=current_fd,
            directory_stat=directory_stat,
            root_fd=root_fd,
            root_stat=root_stat,
            owned_fds=owned_fds,
            edges=tuple(edges),
        )
        for edge in authority.edges:
            if edge.child_fd != authority.directory_fd:
                _require_trusted_ancestor(edge.opened_stat)
        authority.revalidate()
        return authority
    except BaseException:
        for descriptor in reversed(owned_fds):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _require_trusted_ancestor(value: os.stat_result) -> None:
    if not stat.S_ISDIR(value.st_mode):
        raise _error(
            "$.inventory_path",
            "private inventory ancestor is not a directory",
        )
    if value.st_uid not in {0, os.geteuid()}:
        raise _error(
            "$.inventory_path",
            "private inventory ancestor is not controller-owned",
        )
    other_writable = stat.S_IMODE(value.st_mode) & 0o022
    root_sticky = value.st_uid == 0 and value.st_mode & stat.S_ISVTX
    if other_writable and not root_sticky:
        raise _error(
            "$.inventory_path",
            "private inventory ancestor is writable by an untrusted peer",
        )


def _require_private_directory_binding(
    requested_path: Path,
    directory_fd: int,
    expected: os.stat_result,
) -> None:
    opened = os.fstat(directory_fd)
    linked = os.lstat(requested_path)
    _require_same_identity(
        expected,
        opened,
        linked,
        path="$.inventory_path",
    )
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
    ):
        raise _error(
            "$.inventory_path",
            "inventory parent must be a controller-owned 0700 real directory",
        )
    if os.listxattr(directory_fd):
        raise _error(
            "$.inventory_path",
            "inventory parent xattrs are forbidden",
        )
    resolved = Path(f"/proc/self/fd/{directory_fd}").resolve(strict=True)
    if resolved != requested_path:
        raise _error(
            "$.inventory_path",
            "inventory parent is not its exact canonical path",
        )


def _require_disjoint_authorities(
    private_directory: Path,
    denied_authorities: Mapping[str, str | os.PathLike[str]],
) -> None:
    _require_closed_denied_authority_inventory(denied_authorities)
    for label in REQUIRED_NETWORK_DENIED_AUTHORITY_LABELS:
        authority = denied_authorities[label]
        denied = _canonical_absolute_path(
            authority,
            path=f"$.denied_authorities[{label}]",
        )
        try:
            denied_resolved = denied.resolve(strict=True)
        except OSError as exc:
            raise _error(
                f"$.denied_authorities[{label}]",
                "denied authority is unavailable",
            ) from exc
        if denied_resolved != denied:
            raise _error(
                f"$.denied_authorities[{label}]",
                "denied authority must be a real canonical path",
            )
        if _paths_overlap(private_directory, denied):
            raise _error(
                f"$.denied_authorities[{label}]",
                "private inventory authority overlaps a denied authority",
            )


def _require_closed_denied_authority_inventory(
    denied_authorities: Mapping[str, str | os.PathLike[str]],
) -> None:
    if not isinstance(denied_authorities, Mapping):
        raise _error(
            "$.denied_authorities",
            "denied authority inventory must be a role-labeled mapping",
        )
    observed = set(denied_authorities)
    for label in REQUIRED_NETWORK_DENIED_AUTHORITY_LABELS:
        if label not in observed:
            raise _error(
                f"$.denied_authorities[{label}]",
                "denied authority inventory is missing a required root",
            )
    required = frozenset(REQUIRED_NETWORK_DENIED_AUTHORITY_LABELS)
    unknown = [
        label
        for label in observed
        if not isinstance(label, str) or label not in required
    ]
    if unknown:
        label = min(unknown, key=lambda value: str(value).encode("utf-8"))
        diagnostic_label = label if isinstance(label, str) else "<non-string>"
        raise _error(
            f"$.denied_authorities[{diagnostic_label}]",
            "denied authority inventory contains an unknown role",
        )


def _publish_private_bytes(
    parent_fd: int,
    name: str,
    payload: bytes,
    *,
    authority_check,
) -> None:
    temporary_fd: int | None = None
    try:
        authority_check()
        if not hasattr(os, "O_TMPFILE"):
            raise _error(
                "$.inventory_path",
                "atomic unnamed-file publication is unavailable",
            )
        temporary_fd = os.open(
            ".",
            os.O_RDWR | os.O_TMPFILE | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        os.fchmod(temporary_fd, 0o600)
        _require_private_inventory_fd(
            temporary_fd,
            expected_nlink=0,
            expected_size=0,
        )
        _write_all(temporary_fd, payload)
        os.fsync(temporary_fd)
        _require_private_inventory_fd(
            temporary_fd,
            expected_nlink=0,
            expected_size=len(payload),
            expected_content=payload,
        )
        authority_check()
        _link_unnamed_noreplace(temporary_fd, parent_fd, name)
        _require_name_binding(parent_fd, name, temporary_fd)
        _require_private_inventory_fd(
            temporary_fd,
            expected_nlink=1,
            expected_size=len(payload),
            expected_content=payload,
        )
        os.fsync(parent_fd)
        authority_check()
        _require_name_binding(parent_fd, name, temporary_fd)
        _require_private_inventory_fd(
            temporary_fd,
            expected_nlink=1,
            expected_size=len(payload),
            expected_content=payload,
        )
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)


def _require_private_inventory_stat(
    value: os.stat_result,
    *,
    expected_nlink: int = 1,
) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o600
        or value.st_nlink != expected_nlink
        or value.st_size > MAX_NETWORK_INVENTORY_BYTES
    ):
        raise _error(
            "$.inventory_path",
            "inventory file metadata is not private and canonical",
        )


def _require_private_inventory_fd(
    descriptor: int,
    *,
    expected_nlink: int | None = None,
    expected_size: int | None = None,
    expected_content: bytes | None = None,
) -> None:
    observed = os.fstat(descriptor)
    _require_private_inventory_stat(
        observed,
        expected_nlink=1 if expected_nlink is None else expected_nlink,
    )
    if expected_size is not None and observed.st_size != expected_size:
        raise _error("$.inventory_path", "inventory file size changed")
    if os.listxattr(descriptor):
        raise _error("$.inventory_path", "inventory file xattrs are forbidden")
    if expected_content is not None:
        content = _read_bounded(
            descriptor,
            limit=MAX_NETWORK_INVENTORY_BYTES,
        )
        if content != expected_content:
            raise _error("$.inventory_path", "inventory file bytes changed")


def _require_absent(parent_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise _error(
        "$.inventory_path",
        "inventory output already exists and cannot be replaced",
    )


def _link_unnamed_noreplace(
    source_fd: int,
    parent_fd: int,
    name: str,
) -> None:
    try:
        linkat = ctypes.CDLL(None, use_errno=True).linkat
    except AttributeError as exc:
        raise _error(
            "$.inventory_path",
            "atomic no-replace publication is unavailable",
        ) from exc
    linkat.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    linkat.restype = ctypes.c_int
    if (
        linkat(
            source_fd,
            b"",
            parent_fd,
            os.fsencode(name),
            _AT_EMPTY_PATH,
        )
        == 0
    ):
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise _error(
            "$.inventory_path",
            "inventory output appeared during publication",
        )
    raise OSError(error_number, os.strerror(error_number))


def _require_name_binding(
    parent_fd: int,
    name: str,
    held_fd: int,
) -> None:
    held = os.fstat(held_fd)
    linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(linked.st_mode) or not os.path.samestat(held, linked):
        raise _error(
            "$.inventory_path",
            "inventory output binding changed",
        )


def _effective_denied_endpoints(
    runtime_endpoints: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized_runtime = _normalize_endpoints(runtime_endpoints)
    return _normalize_endpoints(
        [
            *(deepcopy(endpoint) for endpoint in _CLOUD_METADATA_BASELINE),
            *normalized_runtime,
        ]
    )


def _endpoint_set_document(
    endpoints: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": DENIED_ENDPOINT_SET_SCHEMA_VERSION,
        "cloud_metadata_baseline_version": CLOUD_METADATA_BASELINE_VERSION,
        "endpoints": list(endpoints),
    }


def _validate_probe_binding(
    probe: ProviderIsolationNetworkProbe,
) -> list[dict[str, str]]:
    if not isinstance(probe, ProviderIsolationNetworkProbe):
        raise _error("$.probe", "capability construction requires a typed probe")
    if (
        probe.schema_version != NETWORK_PROBE_SCHEMA_VERSION
        or probe.endpoint_set_schema_version
        != DENIED_ENDPOINT_SET_SCHEMA_VERSION
        or probe.cloud_metadata_baseline_version
        != CLOUD_METADATA_BASELINE_VERSION
        or not isinstance(probe.endpoint_count, int)
        or isinstance(probe.endpoint_count, bool)
        or not isinstance(probe.endpoint_set_canonical_json, bytes)
        or not isinstance(probe.endpoint_set_digest, str)
        or _DIGEST_PATTERN.fullmatch(probe.endpoint_set_digest) is None
    ):
        raise _error("$.probe", "typed probe binding metadata is invalid")
    try:
        endpoint_document = json.loads(probe.endpoint_set_canonical_json)
    except (ValueError, RecursionError, MemoryError) as exc:
        raise _error("$.probe", "typed probe endpoint binding is not JSON") from exc
    if (
        not isinstance(endpoint_document, Mapping)
        or set(endpoint_document)
        != {
            "schema_version",
            "cloud_metadata_baseline_version",
            "endpoints",
        }
        or endpoint_document.get("schema_version")
        != DENIED_ENDPOINT_SET_SCHEMA_VERSION
        or endpoint_document.get("cloud_metadata_baseline_version")
        != CLOUD_METADATA_BASELINE_VERSION
    ):
        raise _error("$.probe", "typed probe endpoint binding is not closed")
    normalized_endpoints = _normalize_endpoints(
        endpoint_document.get("endpoints")
    )
    expected_document = _endpoint_set_document(normalized_endpoints)
    expected_bytes = canonical_isolation_json_bytes(expected_document)
    if (
        expected_bytes != probe.endpoint_set_canonical_json
        or _digest(expected_bytes) != probe.endpoint_set_digest
        or len(normalized_endpoints) != probe.endpoint_count
    ):
        raise _error("$.probe", "typed probe endpoint binding identity changed")
    endpoints_by_id = {endpoint["id"]: endpoint for endpoint in normalized_endpoints}
    for baseline in _CLOUD_METADATA_BASELINE:
        if endpoints_by_id.get(baseline["id"]) != baseline:
            raise _error(
                "$.probe",
                "typed probe omits or changes the mandatory metadata baseline",
            )
    if not isinstance(probe.results, tuple) or any(
        not isinstance(result, ProviderIsolationNetworkProbeResult)
        for result in probe.results
    ):
        raise _error("$.probe_results", "typed probe results are invalid")
    return _normalize_probe_results(
        [result.to_dict() for result in probe.results],
        endpoints=normalized_endpoints,
    )


def _listener_counts(
    inventory: ProviderIsolationNetworkInventory,
) -> dict[str, int]:
    counts = {
        "total": 0,
        "tcp_ipv4": 0,
        "tcp_ipv6": 0,
        "udp_ipv4": 0,
        "udp_ipv6": 0,
        "abstract_stream": 0,
        "abstract_datagram": 0,
        "abstract_seqpacket": 0,
    }
    for listener in inventory.to_dict()["listeners"]:
        counts["total"] += 1
        if listener["kind"] == "inet":
            counts[f"{listener['protocol']}_{listener['family']}"] += 1
        else:
            counts[f"abstract_{listener['socket_type']}"] += 1
    return counts


def _normalize_endpoints(
    endpoints: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(endpoints, (str, bytes)) or not isinstance(endpoints, Sequence):
        raise _error("$.endpoints", "denied endpoints must be an array")
    if len(endpoints) > MAX_DENIED_ENDPOINTS:
        raise _error("$.endpoints", "denied endpoint set exceeds its bound")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, endpoint in enumerate(endpoints):
        path = f"$.endpoints[{index}]"
        if not isinstance(endpoint, Mapping):
            raise _error(path, "denied endpoint must be an object")
        identifier = endpoint.get("id")
        protocol = endpoint.get("protocol")
        if (
            not isinstance(identifier, str)
            or _ENDPOINT_ID_PATTERN.fullmatch(identifier) is None
            or unicodedata.normalize("NFC", identifier) != identifier
            or identifier in seen
        ):
            raise _error(f"{path}.id", "endpoint id is invalid or duplicated")
        seen.add(identifier)
        if protocol in {"tcp", "udp"}:
            required = {"id", "protocol", "family", "address", "port"}
            if protocol == "udp":
                required |= {"request_hex", "expected_response_hex"}
            if set(endpoint) != required:
                raise _error(path, "INET endpoint fields are not recursively closed")
            family = endpoint.get("family")
            address = endpoint.get("address")
            port = endpoint.get("port")
            if family not in {"ipv4", "ipv6"} or not isinstance(address, str):
                raise _error(path, "INET endpoint family/address is invalid")
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError as exc:
                raise _error(f"{path}.address", "endpoint address is invalid") from exc
            expected_version = 4 if family == "ipv4" else 6
            if parsed.version != expected_version or str(parsed) != address:
                raise _error(
                    f"{path}.address",
                    "endpoint address is not canonical for its family",
                )
            if (
                isinstance(port, bool)
                or not isinstance(port, int)
                or not (1 <= port <= 65535)
            ):
                raise _error(f"{path}.port", "endpoint port is invalid")
            row = {
                "id": identifier,
                "protocol": protocol,
                "family": family,
                "address": address,
                "port": port,
            }
            if protocol == "udp":
                for field_name in ("request_hex", "expected_response_hex"):
                    value = endpoint.get(field_name)
                    _require_probe_hex(value, f"{path}.{field_name}")
                    assert isinstance(value, str)
                    if len(value) == 0:
                        raise _error(
                            f"{path}.{field_name}",
                            "UDP probe payload must not be empty",
                        )
                    row[field_name] = value
            normalized.append(row)
            continue
        if protocol == "abstract_unix":
            required = {
                "id",
                "protocol",
                "socket_type",
                "name_hex",
                "name_length",
            }
            if set(endpoint) != required:
                raise _error(
                    path,
                    "abstract AF_UNIX endpoint fields are not recursively closed",
                )
            if endpoint.get("socket_type") != "stream":
                raise _error(
                    f"{path}.socket_type",
                    "v1 abstract probes require a stream endpoint",
                )
            name_hex = endpoint.get("name_hex")
            name_length = endpoint.get("name_length")
            _require_probe_hex(name_hex, f"{path}.name_hex")
            if (
                isinstance(name_length, bool)
                or not isinstance(name_length, int)
                or not isinstance(name_hex, str)
                or name_length != len(name_hex) // 2
                or name_length > MAX_ABSTRACT_NAME_BYTES
            ):
                raise _error(
                    f"{path}.name_length",
                    "abstract endpoint hex and byte length disagree",
                )
            normalized.append(
                {
                    "id": identifier,
                    "protocol": protocol,
                    "socket_type": "stream",
                    "name_hex": name_hex,
                    "name_length": name_length,
                }
            )
            continue
        raise _error(f"{path}.protocol", "endpoint protocol is unsupported")
    normalized.sort(key=lambda row: row["id"].encode("utf-8"))
    return normalized


def _normalize_probe_results(
    results: Sequence[Mapping[str, Any]],
    *,
    endpoints: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    if isinstance(results, (str, bytes)) or not isinstance(results, Sequence):
        raise _error("$.probe_results", "probe results must be an array")
    endpoints_by_id = {row["id"]: row for row in endpoints}
    if len(results) != len(endpoints_by_id):
        raise _error(
            "$.probe_results",
            "probe results must cover every endpoint exactly once",
        )
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    allowed_match_codes = {
        "connection_refused",
        "timeout",
        "kernel_error",
    }
    for index, result in enumerate(results):
        path = f"$.probe_results[{index}]"
        if not isinstance(result, Mapping) or set(result) != {
            "endpoint_id",
            "protocol",
            "status",
            "match_code",
        }:
            raise _error(path, "probe result fields are not recursively closed")
        endpoint_id = result.get("endpoint_id")
        match_code = result.get("match_code")
        if type(endpoint_id) is not str:
            raise _error(
                f"{path}.endpoint_id",
                "probe endpoint id must be text",
            )
        endpoint = endpoints_by_id.get(endpoint_id)
        if (
            endpoint is None
            or endpoint_id in seen
        ):
            raise _error(
                f"{path}.endpoint_id",
                "probe endpoint is unknown or duplicated",
            )
        seen.add(endpoint_id)
        if (
            type(match_code) is not str
            or result.get("protocol") != endpoint["protocol"]
            or result.get("status") != "not_reachable"
            or match_code not in allowed_match_codes
        ):
            raise _error(path, "probe result is not a closed safe status")
        normalized.append(dict(result))
    normalized.sort(key=lambda row: row["endpoint_id"].encode("utf-8"))
    return normalized


def _probe_stream_inet(
    endpoint: Mapping[str, Any],
    *,
    timeout_seconds: float,
) -> str:
    family = (
        socket.AF_INET
        if endpoint["family"] == "ipv4"
        else socket.AF_INET6
    )
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout_seconds)
        try:
            probe.connect((endpoint["address"], endpoint["port"]))
        except socket.timeout:
            return "timeout"
        except ConnectionRefusedError:
            return "connection_refused"
        except OSError:
            return "kernel_error"
    raise _local_service_exposure(
        endpoint["id"],
        match_code="tcp_connect",
    )


def _probe_stream_abstract_unix(
    endpoint: Mapping[str, Any],
    *,
    timeout_seconds: float,
) -> str:
    address = b"\x00" + bytes.fromhex(endpoint["name_hex"])
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout_seconds)
        try:
            probe.connect(address)
        except socket.timeout:
            return "timeout"
        except ConnectionRefusedError:
            return "connection_refused"
        except OSError:
            return "kernel_error"
    raise _local_service_exposure(
        endpoint["id"],
        match_code="abstract_unix_connect",
    )


def _probe_udp(
    endpoint: Mapping[str, Any],
    *,
    timeout_seconds: float,
) -> str:
    family = (
        socket.AF_INET
        if endpoint["family"] == "ipv4"
        else socket.AF_INET6
    )
    request = bytes.fromhex(endpoint["request_hex"])
    expected_response = bytes.fromhex(endpoint["expected_response_hex"])
    with socket.socket(family, socket.SOCK_DGRAM) as probe:
        probe.settimeout(timeout_seconds)
        try:
            probe.connect((endpoint["address"], endpoint["port"]))
            probe.send(request)
            response = probe.recv(MAX_PROBE_PAYLOAD_BYTES + 1)
        except socket.timeout:
            return "timeout"
        except ConnectionRefusedError:
            return "connection_refused"
        except OSError:
            return "kernel_error"
    raise _local_service_exposure(
        endpoint["id"],
        match_code=(
            "udp_response"
            if response == expected_response
            else "udp_malformed_response"
        ),
    )


def _local_service_exposure(
    endpoint_id: str,
    *,
    match_code: str,
) -> ProviderIsolationNetworkPreflightError:
    return ProviderIsolationNetworkPreflightError(
        (
            _issue(
                f"$.probe_results[{endpoint_id}]",
                f"registered denied endpoint is reachable ({match_code})",
                code=LOCAL_SERVICE_EXPOSURE_CODE,
            ),
        ),
        code=LOCAL_SERVICE_EXPOSURE_CODE,
    )


def _require_probe_hex(value: object, path: str) -> None:
    if (
        not isinstance(value, str)
        or _LOWER_HEX_PATTERN.fullmatch(value) is None
        or len(value) // 2 > MAX_PROBE_PAYLOAD_BYTES
    ):
        raise _error(path, "probe bytes must be bounded lowercase hex")


def _canonical_absolute_path(
    value: str | os.PathLike[str],
    *,
    path: str,
) -> Path:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise _error(path, "authority path must be textual and absolute") from exc
    if (
        not isinstance(raw, str)
        or not raw.startswith("/")
        or "\x00" in raw
        or unicodedata.normalize("NFC", raw) != raw
        or (
            raw != "/"
            and any(component in {"", ".", ".."} for component in raw.split("/")[1:])
        )
    ):
        raise _error(path, "authority path must use canonical absolute spelling")
    result = Path(raw)
    if not result.is_absolute() or os.fspath(result) != raw:
        raise _error(path, "authority path must use canonical absolute spelling")
    return result


def _require_same_identity(
    before: os.stat_result,
    opened: os.stat_result,
    after: os.stat_result,
    *,
    path: str,
) -> None:
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")
    expected = tuple(getattr(before, field) for field in fields)
    opened_identity = tuple(getattr(opened, field) for field in fields)
    after_identity = tuple(getattr(after, field) for field in fields)
    if expected != opened_identity or expected != after_identity:
        raise _error(path, "private authority identity changed")


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second
        or first in second.parents
        or second in first.parents
    )


def _read_bounded_path(path: Path, *, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        return _read_bounded(descriptor, limit=limit)
    finally:
        os.close(descriptor)


def _read_bounded(descriptor: int, *, limit: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    size = 0
    while True:
        block = os.read(descriptor, min(64 * 1024, limit + 1 - size))
        if not block:
            return b"".join(chunks)
        chunks.append(block)
        size += len(block)
        if size > limit:
            raise _error("$.inventory", "bounded input exceeds its byte limit")


def _write_all(descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:  # pragma: no cover - defensive kernel invariant
            raise OSError(errno.EIO, "short write")
        remaining = remaining[written:]


def _iterative_network_json_structure_issues(
    value: object,
) -> tuple[ProviderIsolationIssue, ...]:
    """Bound a JSON tree before recursive schema or canonical operations."""

    stack: list[tuple[object, str, int]] = [(value, "$", 0)]
    seen_containers: set[int] = set()
    node_count = 0
    issues: list[ProviderIsolationIssue] = []
    while stack:
        current, path, depth = stack.pop()
        node_count += 1
        if node_count > MAX_NETWORK_JSON_NODES:
            return (
                _issue(
                    "$",
                    "network inventory JSON exceeds its node bound",
                ),
            )
        if depth > MAX_NETWORK_JSON_DEPTH:
            return (
                _issue(
                    path,
                    "network inventory JSON exceeds its depth bound",
                ),
            )
        current_type = type(current)
        if current_type in {dict, list}:
            identity = id(current)
            if identity in seen_containers:
                return (
                    _issue(
                        path,
                        "network inventory JSON containers must form one tree",
                    ),
                )
            seen_containers.add(identity)
            remaining_nodes = (
                MAX_NETWORK_JSON_NODES - node_count - len(stack)
            )
            if len(current) > remaining_nodes:
                return (
                    _issue(
                        "$",
                        "network inventory JSON exceeds its node bound",
                    ),
                )
            if current_type is dict:
                assert isinstance(current, dict)
                children: list[tuple[object, str, int]] = []
                for key, item in current.items():
                    if type(key) is not str:
                        return (
                            _issue(
                                path,
                                "network inventory JSON object keys must be strings",
                            ),
                        )
                    child_path = (
                        f"{path}.{key}"
                        if len(key) <= 128
                        and key
                        and all(
                            character.isascii()
                            and (character.isalnum() or character == "_")
                            for character in key
                        )
                        else f"{path}.<key>"
                    )
                    children.append((item, child_path, depth + 1))
            else:
                assert isinstance(current, list)
                children = [
                    (item, f"{path}[{index}]", depth + 1)
                    for index, item in enumerate(current)
                ]
            if (
                node_count + len(stack) + len(children)
                > MAX_NETWORK_JSON_NODES
            ):
                return (
                    _issue(
                        "$",
                        "network inventory JSON exceeds its node bound",
                    ),
                )
            stack.extend(reversed(children))
            continue
        if current_type is int:
            if not 0 <= current <= MAX_NETWORK_OWNER_IDENTITY:
                issues.append(
                    _issue(
                        path,
                        "network inventory JSON integer exceeds uint64 bounds",
                    )
                )
            continue
        if current is None or current_type in {str, bool}:
            continue
        if current_type is float:
            message = (
                "network inventory JSON forbids non-finite floating-point values"
                if not math.isfinite(current)
                else "network inventory JSON forbids floating-point values"
            )
            issues.append(_issue(path, message))
            continue
        return (
            _issue(
                path,
                "network inventory contains a non-JSON value",
            ),
        )
    return _deduplicate_issues(issues)


def _deduplicate_issues(
    issues: Sequence[ProviderIsolationIssue],
) -> tuple[ProviderIsolationIssue, ...]:
    return tuple(sorted(set(issues)))


def _aligned(value: int) -> int:
    return (value + 3) & ~3


def _digest(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _issue(
    path: str,
    message: str,
    *,
    code: str = CAPABILITY_UNAVAILABLE_CODE,
) -> ProviderIsolationIssue:
    return ProviderIsolationIssue(code=code, path=path, message=message)


def _error(
    path: str,
    message: str,
    *,
    code: str = CAPABILITY_UNAVAILABLE_CODE,
) -> ProviderIsolationNetworkPreflightError:
    return ProviderIsolationNetworkPreflightError(
        (_issue(path, message, code=code),),
        code=code,
    )


__all__ = [
    "CAPABILITY_UNAVAILABLE_CODE",
    "CLOUD_METADATA_BASELINE_ENDPOINT_IDS",
    "CLOUD_METADATA_BASELINE_VERSION",
    "DENIED_ENDPOINT_SET_SCHEMA_VERSION",
    "LOCAL_SERVICE_EXPOSURE_CODE",
    "MAX_ABSTRACT_NAME_BYTES",
    "MAX_DENIED_ENDPOINTS",
    "MAX_NETWORK_INVENTORY_BYTES",
    "MAX_NETWORK_JSON_DEPTH",
    "MAX_NETWORK_JSON_NODES",
    "MAX_NETWORK_LISTENERS",
    "MAX_NETWORK_OWNER_IDENTITY",
    "MAX_NETWORK_PREFLIGHT_BYTES",
    "NETWORK_INVENTORY_SCHEMA_RESOURCE",
    "NETWORK_INVENTORY_SCHEMA_VERSION",
    "NETWORK_PREFLIGHT_SCHEMA_VERSION",
    "NETWORK_PROBE_SCHEMA_VERSION",
    "ProviderIsolationNetworkInventory",
    "ProviderIsolationNetworkInventoryArtifact",
    "PinnedProviderIsolationNetworkAuthority",
    "ProviderIsolationNetworkPreflight",
    "ProviderIsolationNetworkPreflightError",
    "ProviderIsolationNetworkProbe",
    "ProviderIsolationNetworkProbeResult",
    "REQUIRED_NETWORK_DENIED_AUTHORITY_LABELS",
    "UNLISTED_REACHABILITY_ASSUMPTION",
    "capture_provider_isolation_network_inventory",
    "load_provider_isolation_network_inventory",
    "load_provider_isolation_network_inventory_file",
    "pin_provider_isolation_network_preflight",
    "probe_provider_isolation_network_endpoints",
    "publish_provider_isolation_network_inventory",
    "validate_provider_isolation_network_inventory",
]
