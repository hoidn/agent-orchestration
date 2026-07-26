from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import inspect
import os
from pathlib import Path
import socket
import stat
import threading

import pytest


INVENTORY_SCHEMA_VERSION = "provider_isolation_network_inventory.v1"
PREFLIGHT_SCHEMA_VERSION = "provider_isolation_network_preflight.v1"
CAPABILITY_UNAVAILABLE = "provider_isolation_capability_unavailable"
LOCAL_SERVICE_EXPOSURE = "provider_isolation_local_service_exposure"
REQUIRED_DENIED_AUTHORITY_LABELS = (
    "candidate",
    "workflow",
    "source",
    "extern",
    "controller_state",
    "provider_environment_source",
    "provider_environment_snapshot",
    "scratch",
    "control",
    "evaluator",
    "peer",
    "parent",
)
GOLDEN_INVENTORY_BYTES = (
    b'{"listeners":[{"kind":"abstract_unix","name_hex":"ff410042",'
    b'"name_length":4,"owner":{"inode":44},"protocol":"unix",'
    b'"socket_type":"stream"},{"address":"127.0.0.1","family":"ipv4",'
    b'"kind":"inet","owner":{"inode":22,"uid":1000},"port":4321,'
    b'"protocol":"tcp"},{"address":"::1","family":"ipv6","kind":"inet",'
    b'"owner":{"inode":33,"uid":1000},"port":5353,"protocol":"udp"}],'
    b'"schema_version":"provider_isolation_network_inventory.v1"}\n'
)
GOLDEN_INVENTORY_DIGEST = (
    "sha256:1bc760f306f4a43bef38e072756f74d693e2b159721757f34"
    "cfd5a0072576631"
)


def _api():
    try:
        return importlib.import_module(
            "orchestrator.providers.isolation_network_preflight"
        )
    except ModuleNotFoundError:
        pytest.fail("provider network-preflight module is not implemented")


def _inventory_document() -> dict[str, object]:
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "listeners": [
            {
                "kind": "inet",
                "protocol": "udp",
                "family": "ipv6",
                "address": "::1",
                "port": 5353,
                "owner": {"uid": 1000, "inode": 33},
            },
            {
                "kind": "abstract_unix",
                "protocol": "unix",
                "socket_type": "stream",
                "name_hex": "ff410042",
                "name_length": 4,
                "owner": {"inode": 44},
            },
            {
                "kind": "inet",
                "protocol": "tcp",
                "family": "ipv4",
                "address": "127.0.0.1",
                "port": 4321,
                "owner": {"uid": 1000, "inode": 22},
            },
        ],
    }


def _private_output(tmp_path: Path) -> Path:
    parent = tmp_path / "network-inventory"
    parent.mkdir(mode=0o700)
    return parent / "inventory.json"


def _closed_denied_authorities(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "denied-authorities"
    root.mkdir(mode=0o700, exist_ok=True)
    authorities: dict[str, Path] = {}
    for label in REQUIRED_DENIED_AUTHORITY_LABELS:
        authority = root / label
        authority.mkdir(mode=0o700, exist_ok=True)
        authorities[label] = authority
    return authorities


def _assert_preflight_error(
    call,
    *,
    code: str = CAPABILITY_UNAVAILABLE,
) -> None:
    api = _api()
    with pytest.raises(api.ProviderIsolationNetworkPreflightError) as exc_info:
        call()
    assert exc_info.value.code == code
    assert exc_info.value.issues
    assert all(issue.code == code for issue in exc_info.value.issues)


def _listener_rows(inventory) -> tuple[dict[str, object], ...]:
    return tuple(inventory.to_dict()["listeners"])


def _probe_rows(probe) -> tuple[dict[str, str], ...]:
    return tuple(result.to_dict() for result in probe.results)


def _stub_baseline_stream_probes(api, monkeypatch: pytest.MonkeyPatch) -> None:
    real_probe = api._probe_stream_inet
    baseline_ids = frozenset(api.CLOUD_METADATA_BASELINE_ENDPOINT_IDS)

    def selective_probe(endpoint, *, timeout_seconds):
        if endpoint["id"] in baseline_ids:
            return "connection_refused"
        return real_probe(endpoint, timeout_seconds=timeout_seconds)

    monkeypatch.setattr(api, "_probe_stream_inet", selective_probe)


def test_inventory_schema_is_recursively_closed_bounded_and_versioned() -> None:
    api = _api()
    valid = _inventory_document()
    assert api.validate_provider_isolation_network_inventory(valid) == ()

    mutations = []
    top = deepcopy(valid)
    top["extra"] = True
    mutations.append(top)
    listener = deepcopy(valid)
    listener["listeners"][0]["extra"] = True
    mutations.append(listener)
    owner = deepcopy(valid)
    owner["listeners"][0]["owner"]["extra"] = True
    mutations.append(owner)
    version = deepcopy(valid)
    version["schema_version"] = "provider_isolation_network_inventory.v2"
    mutations.append(version)
    uppercase_hex = deepcopy(valid)
    uppercase_hex["listeners"][1]["name_hex"] = "FF410042"
    mutations.append(uppercase_hex)
    wrong_length = deepcopy(valid)
    wrong_length["listeners"][1]["name_length"] = 3
    mutations.append(wrong_length)
    noncanonical_ip = deepcopy(valid)
    noncanonical_ip["listeners"][0]["address"] = "0:0:0:0:0:0:0:1"
    mutations.append(noncanonical_ip)
    duplicate = deepcopy(valid)
    duplicate["listeners"].append(deepcopy(duplicate["listeners"][0]))
    mutations.append(duplicate)

    for document in mutations:
        assert api.validate_provider_isolation_network_inventory(document)
        _assert_preflight_error(
            lambda document=document: (
                api.load_provider_isolation_network_inventory(document)
            )
        )


def test_inventory_has_independent_canonical_golden_identity() -> None:
    api = _api()
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )

    assert inventory.canonical_json == GOLDEN_INVENTORY_BYTES
    assert inventory.digest == GOLDEN_INVENTORY_DIGEST
    assert inventory.listener_count == 3
    assert (
        api.load_provider_isolation_network_inventory(
            {
                "listeners": list(reversed(_inventory_document()["listeners"])),
                "schema_version": INVENTORY_SCHEMA_VERSION,
            }
        ).digest
        == GOLDEN_INVENTORY_DIGEST
    )
    _assert_preflight_error(
        lambda: api.load_provider_isolation_network_inventory(
            _inventory_document(),
            expected_digest=f"sha256:{'0' * 64}",
        )
    )


def test_owner_identity_is_bounded_uint64_before_canonicalization() -> None:
    api = _api()
    maximum = (1 << 64) - 1
    at_bound = _inventory_document()
    at_bound["listeners"][0]["owner"] = {
        "uid": maximum,
        "inode": maximum,
    }

    loaded = api.load_provider_isolation_network_inventory(at_bound)

    loaded_owner = next(
        row["owner"]
        for row in loaded.to_dict()["listeners"]
        if row.get("protocol") == "udp"
    )
    assert loaded_owner == {
        "uid": maximum,
        "inode": maximum,
    }
    for value in (maximum + 1, 10**5000):
        invalid = _inventory_document()
        invalid["listeners"][0]["owner"]["inode"] = value
        issues = api.validate_provider_isolation_network_inventory(invalid)
        assert issues
        assert all(issue.code == CAPABILITY_UNAVAILABLE for issue in issues)
        _assert_preflight_error(
            lambda invalid=invalid: (
                api.load_provider_isolation_network_inventory(invalid)
            )
        )


def test_private_inventory_huge_integer_parse_failure_is_stable_and_closes_fds(
    tmp_path: Path,
) -> None:
    api = _api()
    output = _private_output(tmp_path)
    output.write_bytes(
        b'{"schema_version":"provider_isolation_network_inventory.v1",'
        b'"listeners":[{"kind":"inet","protocol":"tcp","family":"ipv4",'
        b'"address":"127.0.0.1","port":1,"owner":{"inode":'
        + (b"9" * 5000)
        + b"}}]}\n"
    )
    output.chmod(0o600)
    denied_authorities = _closed_denied_authorities(tmp_path)

    before_fds = len(os.listdir("/proc/self/fd"))
    for _ in range(20):
        _assert_preflight_error(
            lambda: api.load_provider_isolation_network_inventory_file(
                output,
                expected_digest=f"sha256:{'0' * 64}",
                denied_authorities=denied_authorities,
            )
        )
    assert len(os.listdir("/proc/self/fd")) == before_fds


def test_iterative_json_structure_bounds_depth_nodes_and_graph_shapes() -> None:
    api = _api()
    assert api.MAX_NETWORK_JSON_DEPTH > 0
    assert api.MAX_NETWORK_JSON_NODES > api.MAX_NETWORK_JSON_DEPTH

    at_depth: object = None
    for _ in range(api.MAX_NETWORK_JSON_DEPTH):
        at_depth = [at_depth]
    assert api._iterative_network_json_structure_issues(at_depth) == ()

    at_node_bound = [None] * (api.MAX_NETWORK_JSON_NODES - 1)
    assert api._iterative_network_json_structure_issues(at_node_bound) == ()

    over_depth: object = None
    for _ in range(api.MAX_NETWORK_JSON_DEPTH + 1):
        over_depth = [over_depth]
    over_nodes = [None] * api.MAX_NETWORK_JSON_NODES
    cycle: list[object] = []
    cycle.append(cycle)
    invalid_values = (
        over_depth,
        over_nodes,
        cycle,
        ("tuple-is-not-json",),
        {1: "non-string-key"},
        float("nan"),
        float("inf"),
        1.5,
    )
    for value in invalid_values:
        issues = api._iterative_network_json_structure_issues(value)
        assert issues
        assert all(issue.code == CAPABILITY_UNAVAILABLE for issue in issues)


def test_deep_and_cyclic_documents_return_stable_issues_without_recursion() -> None:
    api = _api()
    nested: object = None
    for _ in range(1500):
        nested = [nested]
    unknown = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "listeners": [],
        "unknown": nested,
    }
    cycle: list[object] = []
    cycle.append(cycle)

    before_fds = len(os.listdir("/proc/self/fd"))
    for _ in range(20):
        for document in (nested, unknown, cycle):
            issues = api.validate_provider_isolation_network_inventory(document)
            assert issues
            assert all(
                issue.code == CAPABILITY_UNAVAILABLE for issue in issues
            )
    assert len(os.listdir("/proc/self/fd")) == before_fds


@pytest.mark.parametrize("error_type", [ValueError, RecursionError, MemoryError])
def test_private_inventory_normalizes_all_json_parser_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
) -> None:
    api = _api()
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )
    output = _private_output(tmp_path)
    denied_authorities = _closed_denied_authorities(tmp_path)
    api.publish_provider_isolation_network_inventory(
        inventory,
        output,
        denied_authorities=denied_authorities,
    )
    monkeypatch.setattr(
        api.json,
        "loads",
        lambda _content: (_ for _ in ()).throw(error_type("injected")),
    )

    before_fds = len(os.listdir("/proc/self/fd"))
    for _ in range(10):
        _assert_preflight_error(
            lambda: api.load_provider_isolation_network_inventory_file(
                output,
                expected_digest=inventory.digest,
                denied_authorities=denied_authorities,
            )
        )
    assert len(os.listdir("/proc/self/fd")) == before_fds


def test_inventory_normalizes_canonicalizer_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    monkeypatch.setattr(
        api,
        "canonical_isolation_json_bytes",
        lambda _document: (_ for _ in ()).throw(
            ValueError("injected canonicalizer failure")
        ),
    )

    _assert_preflight_error(
        lambda: api.load_provider_isolation_network_inventory(
            _inventory_document()
        )
    )


@pytest.mark.parametrize(
    ("family", "protocol", "address"),
    [
        (socket.AF_INET, socket.SOCK_STREAM, "127.0.0.1"),
        (socket.AF_INET6, socket.SOCK_STREAM, "::1"),
        (socket.AF_INET, socket.SOCK_DGRAM, "127.0.0.1"),
        (socket.AF_INET6, socket.SOCK_DGRAM, "::1"),
    ],
)
def test_kernel_inventory_captures_ipv4_ipv6_tcp_udp_listeners(
    family: socket.AddressFamily,
    protocol: socket.SocketKind,
    address: str,
) -> None:
    api = _api()
    with socket.socket(family, protocol) as listener:
        if family == socket.AF_INET6:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        try:
            listener.bind((address, 0))
        except OSError as exc:
            if family == socket.AF_INET6:
                pytest.skip(f"IPv6 loopback unavailable: {exc}")
            raise
        if protocol == socket.SOCK_STREAM:
            listener.listen()
        port = listener.getsockname()[1]

        inventory = api.capture_provider_isolation_network_inventory()

    expected = {
        "kind": "inet",
        "protocol": "tcp" if protocol == socket.SOCK_STREAM else "udp",
        "family": "ipv4" if family == socket.AF_INET else "ipv6",
        "address": address,
        "port": port,
    }
    matches = [
        row
        for row in _listener_rows(inventory)
        if all(row.get(key) == value for key, value in expected.items())
    ]
    assert len(matches) == 1
    assert matches[0]["owner"]["uid"] == os.geteuid()
    assert matches[0]["owner"]["inode"] > 0


def test_kernel_inventory_preserves_arbitrary_abstract_unix_name_bytes() -> None:
    api = _api()
    payload = (
        os.getpid().to_bytes(4, "big")
        + b"\xffA\x00B"
        + os.urandom(6)
    )
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(b"\x00" + payload)
        listener.listen()

        inventory = api.capture_provider_isolation_network_inventory()

    matches = [
        row
        for row in _listener_rows(inventory)
        if row["kind"] == "abstract_unix"
        and row["name_hex"] == payload.hex()
    ]
    assert len(matches) == 1
    assert matches[0]["name_length"] == len(payload)
    assert matches[0]["socket_type"] == "stream"
    assert matches[0]["owner"]["inode"] > 0
    assert "uid" not in matches[0]["owner"]


def test_inventory_publication_is_atomic_private_and_exactly_reloadable(
    tmp_path: Path,
) -> None:
    api = _api()
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )
    output = _private_output(tmp_path)
    denied_authorities = _closed_denied_authorities(tmp_path)

    artifact = api.publish_provider_isolation_network_inventory(
        inventory,
        output,
        denied_authorities=denied_authorities,
    )

    observed = os.stat(output, follow_symlinks=False)
    assert artifact.path == output
    assert artifact.digest == GOLDEN_INVENTORY_DIGEST
    assert output.read_bytes() == GOLDEN_INVENTORY_BYTES
    assert stat.S_ISREG(observed.st_mode)
    assert stat.S_IMODE(observed.st_mode) == 0o600
    assert observed.st_uid == os.geteuid()
    assert observed.st_nlink == 1
    assert os.listxattr(output, follow_symlinks=False) == []
    loaded = api.load_provider_isolation_network_inventory_file(
        output,
        expected_digest=GOLDEN_INVENTORY_DIGEST,
        denied_authorities=denied_authorities,
    )
    assert loaded.canonical_json == inventory.canonical_json


@pytest.mark.parametrize(
    "case",
    [
        "existing_regular",
        "existing_symlink",
        "nonprivate_parent",
        "parent_xattr",
        "untrusted_ancestor",
        "symlinked_ancestor",
        "contains_denied",
        "inside_denied",
    ],
)
def test_inventory_publication_rejects_unsafe_output_authority(
    tmp_path: Path,
    case: str,
) -> None:
    api = _api()
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )
    output = _private_output(tmp_path)
    denied_authorities = _closed_denied_authorities(tmp_path)
    sentinel: Path | None = None

    if case == "existing_regular":
        output.write_bytes(b"keep")
        output.chmod(0o600)
        sentinel = output
    elif case == "existing_symlink":
        sentinel = tmp_path / "sentinel"
        sentinel.write_bytes(b"keep")
        output.symlink_to(sentinel)
    elif case == "nonprivate_parent":
        output.parent.chmod(0o755)
    elif case == "parent_xattr":
        os.setxattr(output.parent, "user.network-preflight", b"value")
    elif case == "untrusted_ancestor":
        ancestor = tmp_path / "untrusted"
        ancestor.mkdir(mode=0o700)
        output.parent.rename(ancestor / output.parent.name)
        output = ancestor / output.parent.name / output.name
        ancestor.chmod(0o770)
    elif case == "symlinked_ancestor":
        real = output.parent
        alias = tmp_path / "inventory-alias"
        alias.symlink_to(real, target_is_directory=True)
        output = alias / output.name
    elif case == "contains_denied":
        denied = output.parent / "candidate"
        denied.mkdir(mode=0o700)
        denied_authorities["workflow"] = denied
    elif case == "inside_denied":
        denied_authorities["workflow"] = tmp_path

    _assert_preflight_error(
        lambda: api.publish_provider_isolation_network_inventory(
            inventory,
            output,
            denied_authorities=denied_authorities,
        )
    )
    if sentinel is not None:
        assert sentinel.read_bytes() == b"keep"
    else:
        assert not output.exists()


@pytest.mark.parametrize("tamper", ["content", "mode", "hardlink", "xattr"])
def test_inventory_reload_rejects_independent_file_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    api = _api()
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )
    output = _private_output(tmp_path)
    denied_authorities = _closed_denied_authorities(tmp_path)
    api.publish_provider_isolation_network_inventory(
        inventory,
        output,
        denied_authorities=denied_authorities,
    )

    if tamper == "content":
        output.write_bytes(output.read_bytes() + b" ")
    elif tamper == "mode":
        output.chmod(0o644)
    elif tamper == "hardlink":
        os.link(output, output.with_name("alias.json"))
    else:
        os.setxattr(output, "user.network-preflight", b"value")

    _assert_preflight_error(
        lambda: api.load_provider_isolation_network_inventory_file(
            output,
            expected_digest=inventory.digest,
            denied_authorities=denied_authorities,
        )
    )


def test_inventory_file_operations_require_closed_denied_authority_inventory(
    tmp_path: Path,
) -> None:
    api = _api()
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )
    output = _private_output(tmp_path)
    denied_authorities = _closed_denied_authorities(tmp_path)
    artifact = api.publish_provider_isolation_network_inventory(
        inventory,
        output,
        denied_authorities=denied_authorities,
    )

    for function in (
        api.publish_provider_isolation_network_inventory,
        api.load_provider_isolation_network_inventory_file,
        api.pin_provider_isolation_network_preflight,
    ):
        parameter = inspect.signature(function).parameters["denied_authorities"]
        assert parameter.default is inspect.Parameter.empty

    invalid_inventories = (
        {},
        {
            label: path
            for label, path in denied_authorities.items()
            if label != "candidate"
        },
        {**denied_authorities, "unknown": tmp_path},
    )
    for index, invalid in enumerate(invalid_inventories):
        _assert_preflight_error(
            lambda invalid=invalid, index=index: (
                api.publish_provider_isolation_network_inventory(
                    inventory,
                    output.with_name(f"invalid-{index}.json"),
                    denied_authorities=invalid,
                )
            )
        )
        _assert_preflight_error(
            lambda invalid=invalid: (
                api.load_provider_isolation_network_inventory_file(
                    output,
                    expected_digest=inventory.digest,
                    denied_authorities=invalid,
                )
            )
        )
        _assert_preflight_error(
            lambda invalid=invalid: (
                api.pin_provider_isolation_network_preflight(
                    reviewed_artifact=artifact,
                    denied_authorities=invalid,
                    runtime_endpoints=(),
                    timeout_seconds=0.1,
                    decision="accept_unlisted_reachability",
                )
            )
        )


def test_pinned_authority_owns_live_recapture_probe_and_exact_revalidation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )
    output = _private_output(tmp_path)
    denied_authorities = _closed_denied_authorities(tmp_path)
    artifact = api.publish_provider_isolation_network_inventory(
        inventory,
        output,
        denied_authorities=denied_authorities,
    )
    captures: list[str] = []
    probes: list[str] = []

    def capture_reviewed():
        captures.append("capture")
        return inventory

    def safe_probe(endpoint, *, timeout_seconds):
        probes.append(endpoint["id"])
        return "connection_refused"

    monkeypatch.setattr(
        api,
        "capture_provider_isolation_network_inventory",
        capture_reviewed,
    )
    monkeypatch.setattr(api, "_probe_stream_inet", safe_probe)

    authority = api.pin_provider_isolation_network_preflight(
        reviewed_artifact=artifact,
        denied_authorities=denied_authorities,
        runtime_endpoints=(),
        timeout_seconds=0.1,
        decision="accept_unlisted_reachability",
    )
    assert type(authority) is api.PinnedProviderIsolationNetworkAuthority
    assert authority.capability.digest.startswith("sha256:")
    assert authority.capability.to_dict()["inventory"]["digest"] == inventory.digest
    assert captures == ["capture"]
    assert probes == list(sorted(api.CLOUD_METADATA_BASELINE_ENDPOINT_IDS))

    repeated = authority.revalidate()
    assert repeated.canonical_json == authority.capability.canonical_json
    assert repeated.digest == authority.capability.digest
    assert captures == ["capture", "capture"]
    assert probes == [
        *sorted(api.CLOUD_METADATA_BASELINE_ENDPOINT_IDS),
        *sorted(api.CLOUD_METADATA_BASELINE_ENDPOINT_IDS),
    ]

    changed_document = _inventory_document()
    changed_document["listeners"][0]["port"] = 5354
    changed = api.load_provider_isolation_network_inventory(changed_document)
    monkeypatch.setattr(
        api,
        "capture_provider_isolation_network_inventory",
        lambda: changed,
    )
    _assert_preflight_error(
        authority.revalidate
    )


def test_pinned_authority_rejects_absent_tampered_and_forged_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )
    denied_authorities = _closed_denied_authorities(tmp_path)
    monkeypatch.setattr(
        api,
        "capture_provider_isolation_network_inventory",
        lambda: inventory,
    )
    monkeypatch.setattr(
        api,
        "_probe_stream_inet",
        lambda _endpoint, *, timeout_seconds: "connection_refused",
    )

    absent = api.ProviderIsolationNetworkInventoryArtifact(
        path=_private_output(tmp_path),
        digest=inventory.digest,
    )
    _assert_preflight_error(
        lambda: api.pin_provider_isolation_network_preflight(
            reviewed_artifact=absent,
            denied_authorities=denied_authorities,
            runtime_endpoints=(),
            timeout_seconds=0.1,
            decision="accept_unlisted_reachability",
        )
    )

    output = absent.path
    artifact = api.publish_provider_isolation_network_inventory(
        inventory,
        output,
        denied_authorities=denied_authorities,
    )
    authority = api.pin_provider_isolation_network_preflight(
        reviewed_artifact=artifact,
        denied_authorities=denied_authorities,
        runtime_endpoints=(),
        timeout_seconds=0.1,
        decision="accept_unlisted_reachability",
    )
    output.write_bytes(b"{}\n")
    _assert_preflight_error(authority.revalidate)

    changed_artifact = replace(
        artifact,
        digest=f"sha256:{'0' * 64}",
    )
    _assert_preflight_error(
        lambda: api.pin_provider_isolation_network_preflight(
            reviewed_artifact=changed_artifact,
            denied_authorities=denied_authorities,
            runtime_endpoints=(),
            timeout_seconds=0.1,
            decision="accept_unlisted_reachability",
        )
    )
    assert not hasattr(api, "build_provider_isolation_network_preflight")
    assert not hasattr(api, "ProviderIsolationNetworkRevalidatedArtifact")
    with pytest.raises(TypeError):
        api.PinnedProviderIsolationNetworkAuthority()


def test_probe_capability_canonicalization_binds_review_and_endpoint_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    inventory_path = _private_output(tmp_path)
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )
    denied_authorities = _closed_denied_authorities(tmp_path)
    reviewed = api.publish_provider_isolation_network_inventory(
        inventory,
        inventory_path,
        denied_authorities=denied_authorities,
    )
    monkeypatch.setattr(
        api,
        "capture_provider_isolation_network_inventory",
        lambda: inventory,
    )
    endpoints = [
        {
            "id": "z-tcp",
            "protocol": "tcp",
            "family": "ipv4",
            "address": "127.0.0.1",
            "port": 65000,
        },
        {
            "id": "a-unix",
            "protocol": "abstract_unix",
            "socket_type": "stream",
            "name_hex": "ff00",
            "name_length": 2,
        },
    ]
    monkeypatch.setattr(
        api,
        "_probe_stream_inet",
        lambda _endpoint, *, timeout_seconds: "connection_refused",
    )
    monkeypatch.setattr(
        api,
        "_probe_stream_abstract_unix",
        lambda _endpoint, *, timeout_seconds: "connection_refused",
    )
    first_authority = api.pin_provider_isolation_network_preflight(
        reviewed_artifact=reviewed,
        denied_authorities=denied_authorities,
        runtime_endpoints=endpoints,
        timeout_seconds=0.1,
        decision="accept_unlisted_reachability",
    )
    second_authority = api.pin_provider_isolation_network_preflight(
        reviewed_artifact=reviewed,
        denied_authorities=denied_authorities,
        runtime_endpoints=list(reversed(endpoints)),
        timeout_seconds=0.1,
        decision="accept_unlisted_reachability",
    )
    first = first_authority.capability
    second = second_authority.capability

    document = first.to_dict()
    assert first.schema_version == PREFLIGHT_SCHEMA_VERSION
    assert first.canonical_json == second.canonical_json
    assert first.digest == second.digest
    assert document["inventory"] == {
        "digest": GOLDEN_INVENTORY_DIGEST,
        "listener_counts": {
            "abstract_datagram": 0,
            "abstract_seqpacket": 0,
            "abstract_stream": 1,
            "tcp_ipv4": 1,
            "tcp_ipv6": 0,
            "total": 3,
            "udp_ipv4": 0,
            "udp_ipv6": 1,
        },
        "decision": "accept_unlisted_reachability",
        "unlisted_reachability_assumption": (
            "all_unlisted_local_and_remote_reachability_is_a_"
            "deployment_trust_assumption"
        ),
    }
    assert str(inventory_path) not in first.canonical_json.decode("utf-8")
    assert [row["endpoint_id"] for row in document["probe_results"]] == [
        "a-unix",
        *sorted(api.CLOUD_METADATA_BASELINE_ENDPOINT_IDS),
        "z-tcp",
    ]
    changed_authority = api.pin_provider_isolation_network_preflight(
        reviewed_artifact=reviewed,
        denied_authorities=denied_authorities,
        runtime_endpoints=[
            {**endpoints[0], "port": 65001},
            endpoints[1],
        ],
        timeout_seconds=0.1,
        decision="accept_unlisted_reachability",
    )
    changed = changed_authority.capability
    assert changed.endpoint_set_digest != first.endpoint_set_digest
    assert changed.digest != first.digest

    monkeypatch.setattr(api, "MAX_NETWORK_PREFLIGHT_BYTES", 1)
    _assert_preflight_error(
        lambda: api.pin_provider_isolation_network_preflight(
            reviewed_artifact=reviewed,
            denied_authorities=denied_authorities,
            runtime_endpoints=endpoints,
            timeout_seconds=0.1,
            decision="accept_unlisted_reachability",
        )
    )


def test_cloud_metadata_baseline_is_versioned_nonempty_and_always_unioned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    observed_ids: list[str] = []

    def record_stream_probe(endpoint, *, timeout_seconds):
        observed_ids.append(endpoint["id"])
        return "connection_refused"

    monkeypatch.setattr(api, "_probe_stream_inet", record_stream_probe)
    empty_runtime = api.probe_provider_isolation_network_endpoints(
        [],
        timeout_seconds=0.1,
    )

    assert api.CLOUD_METADATA_BASELINE_VERSION.endswith(".v1")
    assert api.CLOUD_METADATA_BASELINE_ENDPOINT_IDS
    assert tuple(observed_ids) == tuple(
        sorted(api.CLOUD_METADATA_BASELINE_ENDPOINT_IDS)
    )
    assert empty_runtime.cloud_metadata_baseline_version == (
        api.CLOUD_METADATA_BASELINE_VERSION
    )
    assert empty_runtime.endpoint_count == len(
        api.CLOUD_METADATA_BASELINE_ENDPOINT_IDS
    )

    observed_ids.clear()
    runtime_endpoint = {
        "id": "runtime-control",
        "protocol": "tcp",
        "family": "ipv4",
        "address": "127.0.0.1",
        "port": 9,
    }
    with_runtime = api.probe_provider_isolation_network_endpoints(
        [runtime_endpoint],
        timeout_seconds=0.1,
    )
    assert set(observed_ids) == {
        *api.CLOUD_METADATA_BASELINE_ENDPOINT_IDS,
        "runtime-control",
    }
    assert with_runtime.endpoint_count == empty_runtime.endpoint_count + 1


def test_tcp_probe_rejects_accept_and_close_as_local_service_exposure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    _stub_baseline_stream_probes(api, monkeypatch)
    accepted = threading.Event()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        def accept_and_close() -> None:
            connection, _address = listener.accept()
            accepted.set()
            connection.close()

        thread = threading.Thread(target=accept_and_close, daemon=True)
        thread.start()
        marker: list[str] = []
        _assert_preflight_error(
            lambda: (
                api.probe_provider_isolation_network_endpoints(
                    [
                        {
                            "id": "loopback-sentinel",
                            "protocol": "tcp",
                            "family": "ipv4",
                            "address": "127.0.0.1",
                            "port": port,
                        }
                    ],
                    timeout_seconds=0.2,
                ),
                marker.append("provider-started"),
            ),
            code=LOCAL_SERVICE_EXPOSURE,
        )
        thread.join(timeout=1)

    assert accepted.is_set()
    assert marker == []


def test_abstract_unix_probe_rejects_accept_and_close_without_name_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    _stub_baseline_stream_probes(api, monkeypatch)
    payload = os.getpid().to_bytes(4, "big") + b"\xff\x00sentinel"
    accepted = threading.Event()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(b"\x00" + payload)
        listener.listen()

        def accept_and_close() -> None:
            connection, _address = listener.accept()
            accepted.set()
            connection.close()

        thread = threading.Thread(target=accept_and_close, daemon=True)
        thread.start()
        with pytest.raises(
            api.ProviderIsolationNetworkPreflightError
        ) as exc_info:
            api.probe_provider_isolation_network_endpoints(
                [
                    {
                        "id": "abstract-sentinel",
                        "protocol": "abstract_unix",
                        "socket_type": "stream",
                        "name_hex": payload.hex(),
                        "name_length": len(payload),
                    }
                ],
                timeout_seconds=0.2,
            )
        thread.join(timeout=1)

    assert accepted.is_set()
    assert exc_info.value.code == LOCAL_SERVICE_EXPOSURE
    assert payload.hex() not in str(exc_info.value)


def test_udp_probe_requires_protocol_response_not_connect_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    _stub_baseline_stream_probes(api, monkeypatch)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        endpoint = {
            "id": "udp-sentinel",
            "protocol": "udp",
            "family": "ipv4",
            "address": "127.0.0.1",
            "port": port,
            "request_hex": b"ping".hex(),
            "expected_response_hex": b"pong".hex(),
        }

        probe = api.probe_provider_isolation_network_endpoints(
            [endpoint],
            timeout_seconds=0.02,
        )

        assert _probe_rows(probe)[-1:] == (
            {
                "endpoint_id": "udp-sentinel",
                "protocol": "udp",
                "status": "not_reachable",
                "match_code": "timeout",
            },
        )
        request, _address = listener.recvfrom(64)
        assert request == b"ping"

        responded = threading.Event()

        def respond() -> None:
            request, address = listener.recvfrom(64)
            assert request == b"ping"
            listener.sendto(b"pong", address)
            responded.set()

        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        _assert_preflight_error(
            lambda: api.probe_provider_isolation_network_endpoints(
                [endpoint],
                timeout_seconds=0.2,
            ),
            code=LOCAL_SERVICE_EXPOSURE,
        )
        thread.join(timeout=1)

    assert responded.is_set()


def test_udp_probe_rejects_malformed_response_as_local_service_exposure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    _stub_baseline_stream_probes(api, monkeypatch)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

        def respond_with_wrong_protocol_bytes() -> None:
            request, address = listener.recvfrom(64)
            assert request == b"ping"
            listener.sendto(b"not-pong", address)

        thread = threading.Thread(
            target=respond_with_wrong_protocol_bytes,
            daemon=True,
        )
        thread.start()
        _assert_preflight_error(
            lambda: api.probe_provider_isolation_network_endpoints(
                [
                    {
                        "id": "udp-malformed-sentinel",
                        "protocol": "udp",
                        "family": "ipv4",
                        "address": "127.0.0.1",
                        "port": port,
                        "request_hex": b"ping".hex(),
                        "expected_response_hex": b"pong".hex(),
                    }
                ],
                timeout_seconds=0.2,
            ),
            code=LOCAL_SERVICE_EXPOSURE,
        )
        thread.join(timeout=1)

    assert not thread.is_alive()


def test_probe_results_are_typed_bounded_and_reject_unknown_endpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    inventory = api.load_provider_isolation_network_inventory(
        _inventory_document()
    )
    output = _private_output(tmp_path)
    denied_authorities = _closed_denied_authorities(tmp_path)
    reviewed = api.publish_provider_isolation_network_inventory(
        inventory,
        output,
        denied_authorities=denied_authorities,
    )
    monkeypatch.setattr(
        api,
        "capture_provider_isolation_network_inventory",
        lambda: inventory,
    )
    monkeypatch.setattr(
        api,
        "_probe_stream_inet",
        lambda _endpoint, *, timeout_seconds: "connection_refused",
    )
    endpoints = [
        {
            "id": "known",
            "protocol": "tcp",
            "family": "ipv4",
            "address": "127.0.0.1",
            "port": 9,
        }
    ]
    probe = api.probe_provider_isolation_network_endpoints(
        endpoints,
        timeout_seconds=0.1,
    )
    invalid_results = tuple(
        replace(result, endpoint_id="unknown")
        if result.endpoint_id == "known"
        else result
        for result in probe.results
    )
    unknown_probe = replace(probe, results=invalid_results)
    monkeypatch.setattr(
        api,
        "probe_provider_isolation_network_endpoints",
        lambda _endpoints, *, timeout_seconds: unknown_probe,
    )
    _assert_preflight_error(
        lambda: api.pin_provider_isolation_network_preflight(
            reviewed_artifact=reviewed,
            denied_authorities=denied_authorities,
            runtime_endpoints=endpoints,
            timeout_seconds=0.1,
            decision="accept_unlisted_reachability",
        )
    )
    invalid_match_results = tuple(
        replace(result, match_code="malformed_response")
        if result.endpoint_id == "known"
        else result
        for result in probe.results
    )
    invalid_match_probe = replace(probe, results=invalid_match_results)
    monkeypatch.setattr(
        api,
        "probe_provider_isolation_network_endpoints",
        lambda _endpoints, *, timeout_seconds: invalid_match_probe,
    )
    _assert_preflight_error(
        lambda: api.pin_provider_isolation_network_preflight(
            reviewed_artifact=reviewed,
            denied_authorities=denied_authorities,
            runtime_endpoints=endpoints,
            timeout_seconds=0.1,
            decision="accept_unlisted_reachability",
        )
    )
    for field_name in ("endpoint_id", "match_code"):
        forged_results = tuple(
            replace(result, **{field_name: []})
            if result.endpoint_id == "known"
            else result
            for result in probe.results
        )
        forged_probe = replace(probe, results=forged_results)
        monkeypatch.setattr(
            api,
            "probe_provider_isolation_network_endpoints",
            lambda _endpoints, *, timeout_seconds, forged_probe=forged_probe: (
                forged_probe
            ),
        )
        _assert_preflight_error(
            lambda: api.pin_provider_isolation_network_preflight(
                reviewed_artifact=reviewed,
                denied_authorities=denied_authorities,
                runtime_endpoints=endpoints,
                timeout_seconds=0.1,
                decision="accept_unlisted_reachability",
            )
        )
    class HostileString(str):
        def __hash__(self) -> int:
            raise RuntimeError("hostile string hash must not run")

    for field_name, hostile_value in (
        ("endpoint_id", HostileString("known")),
        ("match_code", HostileString("connection_refused")),
    ):
        hostile_results = tuple(
            replace(result, **{field_name: hostile_value})
            if result.endpoint_id == "known"
            else result
            for result in probe.results
        )
        hostile_probe = replace(probe, results=hostile_results)
        monkeypatch.setattr(
            api,
            "probe_provider_isolation_network_endpoints",
            lambda _endpoints, *, timeout_seconds, hostile_probe=hostile_probe: (
                hostile_probe
            ),
        )
        _assert_preflight_error(
            lambda: api.pin_provider_isolation_network_preflight(
                reviewed_artifact=reviewed,
                denied_authorities=denied_authorities,
                runtime_endpoints=endpoints,
                timeout_seconds=0.1,
                decision="accept_unlisted_reachability",
            )
        )
    assert set(
        inspect.signature(
            api.pin_provider_isolation_network_preflight
        ).parameters
    ) == {
        "reviewed_artifact",
        "denied_authorities",
        "runtime_endpoints",
        "timeout_seconds",
        "decision",
    }
    with pytest.raises(TypeError):
        api.pin_provider_isolation_network_preflight(
            reviewed_artifact=reviewed,
            denied_authorities=denied_authorities,
            runtime_endpoints=endpoints,
            timeout_seconds=0.1,
            decision="accept_unlisted_reachability",
            inventory=object(),
        )


@pytest.mark.parametrize(
    "timeout_seconds",
    [float("nan"), float("inf"), float("-inf")],
)
def test_probe_rejects_nonfinite_timeout(timeout_seconds: float) -> None:
    api = _api()

    _assert_preflight_error(
        lambda: api.probe_provider_isolation_network_endpoints(
            [],
            timeout_seconds=timeout_seconds,
        )
    )


def test_probe_normalizes_socket_setup_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()

    def unavailable(_endpoint, *, timeout_seconds):
        raise OSError("injected socket setup failure")

    monkeypatch.setattr(api, "_probe_stream_inet", unavailable)

    _assert_preflight_error(
        lambda: api.probe_provider_isolation_network_endpoints(
            [],
            timeout_seconds=0.1,
        )
    )
