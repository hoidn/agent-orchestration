from __future__ import annotations

import copy
from contextlib import ExitStack
import ctypes
from dataclasses import FrozenInstanceError, replace
import errno
from hashlib import sha256
import importlib
import inspect
import json
import os
from pathlib import Path
import runpy
import shutil
import signal
import socket
import stat
import subprocess
import sys

import pytest

from orchestrator.providers.isolation import MAX_RESULT_BUNDLE_BYTES
from orchestrator.providers.isolation import (
    MAX_PROVIDER_ISOLATION_SCOPE_COMPONENTS,
    MAX_PROVIDER_ISOLATION_SCOPE_COMPONENT_LENGTH,
    MAX_PROVIDER_ISOLATION_RUNTIME_RELPATH_LENGTH,
    MAX_PROVIDER_ISOLATION_UINT64,
)


def _backend_api():
    from orchestrator.providers import isolation_backend

    return isolation_backend


def _bubblewrap_api():
    from orchestrator.providers import isolation_bubblewrap

    return isolation_bubblewrap


def _make_typed_invocation_components(
    tmp_path: Path,
    *,
    workflow: bool,
    ordinal: int = 1,
    result_bundle_max_bytes: int = 4096,
):
    from orchestrator.providers.isolation_candidate import (
        REQUIRED_CANDIDATE_AUTHORITY_LABELS,
        admit_provider_candidate,
    )
    from orchestrator.providers.isolation_environment import (
        assemble_provider_environment_snapshot,
        build_provider_environment_manifest,
    )
    from orchestrator.providers.isolation_runtime_authority import (
        ProviderIsolationRuntimeAuthority,
    )
    api = _backend_api()
    source = tmp_path / "environment-source"
    python = source / "opt" / "provider" / "bin" / "python"
    python.parent.mkdir(parents=True, mode=0o755)
    for directory in (
        source,
        source / "opt",
        source / "opt" / "provider",
        python.parent,
    ):
        directory.chmod(0o755)
    python.write_bytes(b"fixture interpreter\n")
    python.chmod(0o755)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = build_provider_environment_manifest(source, "/opt/provider")
    snapshot = assemble_provider_environment_snapshot(
        source,
        "/opt/provider",
        run_root,
        expected_digest=manifest.digest,
    )
    candidate = tmp_path / "candidate"
    candidate.mkdir(mode=0o700)
    authority_root = tmp_path / "denied"
    authority_root.mkdir(mode=0o700)
    denied: dict[str, Path] = {}
    for label in REQUIRED_CANDIDATE_AUTHORITY_LABELS:
        if label == "provider_environment_source":
            denied[label] = source
        elif label == "provider_environment_snapshot":
            denied[label] = snapshot.rootfs_path
        else:
            path = authority_root / label
            path.mkdir(mode=0o700)
            denied[label] = path
    admission = admit_provider_candidate(
        candidate,
        denied_authorities=denied,
        provider_prefix="/opt/provider",
    )
    runtime = ProviderIsolationRuntimeAuthority.create_fresh(candidate)
    if workflow:
        request = api.WorkflowProviderIsolationRequest(
            candidate_path=os.fspath(candidate),
            target=("/opt/provider/bin/python", "-I", "-S", "-c", "pass"),
            environment_digest=snapshot.digest,
            result_channel="typed_bundle",
            provider_template_identity="sha256:" + ("2" * 64),
            aggregate_scope=("root", "provider"),
            ordinal=ordinal,
            result_logical_path=os.fspath(
                candidate / ".orchestrate" / "results" / "value.json"
            ),
            result_bundle_max_bytes=result_bundle_max_bytes,
        )
    else:
        request = api.ControllerAttemptIsolationRequest(
            candidate_path=os.fspath(candidate),
            target=("/opt/provider/bin/python", "-I", "-S", "-c", "pass"),
            environment_digest=snapshot.digest,
            result_channel="none",
            caller_kind="capability_probe",
            caller_attempt_id=f"probe-{ordinal}",
            command_identity="sha256:" + ("3" * 64),
            external_sink_identity="sha256:" + ("4" * 64),
        )
    return snapshot, admission, runtime, request


def test_backend_registry_is_closed_and_never_searches_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _backend_api()
    fake = tmp_path / "bwrap"
    fake.write_text("#!/bin/sh\necho 'bubblewrap 0.9.0'\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", os.fspath(tmp_path))

    backend = api.get_provider_isolation_backend("bubblewrap.v1")

    assert backend.contract_id == "bubblewrap.v1"
    assert backend.executable_path == Path("/usr/bin/bwrap")
    with pytest.raises(api.ProviderIsolationBackendUnavailable):
        api.get_provider_isolation_backend("bubblewrap.v2")


def test_validated_policy_selects_only_its_closed_backend() -> None:
    from orchestrator.providers import isolation

    document = {
        "schema_version": "provider_phase_isolation.v1",
        "mode": "required",
        "backend": "bubblewrap.v1",
        "session_mode": "fresh_only",
        "workspace": {
            "access": "read_write",
            "masked_runtime_roots": [".orchestrate"],
        },
        "provider_environment": {
            "root": "/run/provider-environment",
            "provider_prefix": "/opt/provider",
            "digest": "sha256:" + ("1" * 64),
        },
        "process_environment": {"credential_env": []},
        "result_bundle": {"max_bytes": 1024},
        "shared_network_review": {
            "inventory_path": "/run/controller/network-inventory.json",
            "inventory_digest": "sha256:" + ("2" * 64),
            "decision": "accept_unlisted_reachability",
        },
        "history_retrieval": {
            "eligibility_requirement": "require_causal",
            "provider_api_transport": "allow",
            "remote_git": "deny",
            "browser": "deny",
            "source_search": "deny",
            "repository_fetch": "deny",
        },
    }
    policy = isolation.load_provider_phase_isolation_policy(document)

    selected = isolation.select_provider_isolation_backend(policy)

    assert selected.contract_id == "bubblewrap.v1"


def test_fixed_backend_preflight_is_content_addressed_and_revalidates() -> None:
    api = _backend_api()
    backend = api.get_provider_isolation_backend("bubblewrap.v1")

    pinned = backend.preflight()
    try:
        identity = pinned.identity
        document = identity.to_dict()
        assert document["schema_version"] == (
            "provider_isolation_backend_identity.v1"
        )
        assert document["contract_id"] == "bubblewrap.v1"
        assert document["executable"]["path"] == "/usr/bin/bwrap"
        assert document["executable"]["uid"] == 0
        assert document["executable"]["gid"] == 0
        assert document["executable"]["digest"].startswith("sha256:")
        assert document["version"].startswith("bubblewrap ")
        assert document["startup_closure"]
        assert document["containment"]["contract_id"] == "cgroup_v2_leaf.v1"
        assert document["containment"]["probe_results"] == {
            "create": "passed",
            "member": "passed",
            "reload": "passed",
            "kill": "passed",
            "empty": "passed",
            "remove": "passed",
        }
        assert document["capability_probe_results"]["status"] == "passed"
        assert document["capability_probe_results"]["privileged_launcher"] is False
        assert document["capability_probe_results"]["shared_host_network"] is True
        assert "--unshare-net" not in api._backend_capability_probe_argv()
        assert identity.digest.startswith("sha256:")
        assert pinned.revalidate().digest == identity.digest
    finally:
        pinned.close()


@pytest.mark.parametrize(
    (
        "owner_search_kind",
        "cache_selection",
        "expected_selection",
        "expected_cache_calls",
    ),
    (
        ("runpath", "cache", "owner", 0),
        ("rpath", "cache", "owner", 0),
        ("none", "cache", "cache", 1),
        ("none", None, "default", 1),
        ("none", "missing", "missing", 1),
    ),
)
def test_host_elf_dependency_selection_uses_owner_then_cache_then_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    owner_search_kind: str,
    cache_selection: str | None,
    expected_selection: str,
    expected_cache_calls: int,
) -> None:
    from orchestrator.providers.isolation_environment import ParsedElf

    api = _backend_api()
    needed = "libprobe.so.1"
    owner_directory = tmp_path / "owner"
    cache_directory = tmp_path / "cache"
    default_directory = tmp_path / "default"
    for directory in (owner_directory, cache_directory, default_directory):
        directory.mkdir()
    selections = {
        "owner": owner_directory / needed,
        "cache": cache_directory / needed,
        "default": default_directory / needed,
        "missing": tmp_path / "missing" / needed,
    }
    selections["owner"].write_bytes(b"owner")
    selections["cache"].write_bytes(b"cache")
    selections["default"].write_bytes(b"default")
    runpath = (
        (os.fspath(owner_directory),)
        if owner_search_kind == "runpath"
        else ()
    )
    rpath = (
        (os.fspath(owner_directory),)
        if owner_search_kind == "rpath"
        else ()
    )
    elf = ParsedElf(
        elf_class=2,
        data_encoding=1,
        ident_version=1,
        elf_type=3,
        machine=62,
        header_version=1,
        interpreter=None,
        needed=(needed,),
        rpath=rpath,
        runpath=runpath,
    )
    cache_calls: list[tuple[object, str]] = []
    cache_entries = (object(),)

    def select_cache(entries: object, *, needed: str) -> str | None:
        cache_calls.append((entries, needed))
        if cache_selection is None:
            return None
        return os.fspath(selections[cache_selection])

    monkeypatch.setattr(
        api._environment,
        "_select_glibc_cache_dependency",
        select_cache,
    )
    monkeypatch.setattr(
        api,
        "_DEFAULT_LIBRARY_DIRECTORIES",
        (os.fspath(default_directory),),
    )

    selected = api._select_host_elf_dependency(
        needed,
        owner="/usr/bin/owner",
        elf=elf,
        cache_entries=cache_entries,
    )

    assert selected == os.fspath(selections[expected_selection])
    assert len(cache_calls) == expected_cache_calls
    if cache_calls:
        assert cache_calls == [(cache_entries, needed)]
    if expected_selection == "missing":
        assert not Path(selected).exists()


def test_invalid_selected_cache_dependency_fails_without_default_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from orchestrator.providers.isolation_environment import ParsedElf

    api = _backend_api()
    executable = Path("/usr/bin/fake-bwrap")
    interpreter = "/lib64/fake-loader.so"
    needed = "libprobe.so.1"
    missing_cache_target = tmp_path / "missing-cache" / needed
    default_directory = tmp_path / "default"
    default_directory.mkdir()
    default_target = default_directory / needed
    default_target.write_bytes(b"default")
    root_elf = ParsedElf(
        elf_class=2,
        data_encoding=1,
        ident_version=1,
        elf_type=3,
        machine=62,
        header_version=1,
        interpreter=interpreter,
        needed=(needed,),
        rpath=(),
        runpath=(),
    )
    leaf_elf = replace(root_elf, interpreter=None, needed=())
    admitted_paths: list[str] = []

    def select_cache(_entries: object, *, needed: str) -> str:
        assert needed == "libprobe.so.1"
        return os.fspath(missing_cache_target)

    def admit(path: Path, *, keep_open: bool):
        admitted_paths.append(os.fspath(path))
        if path == missing_cache_target:
            raise api.ProviderIsolationBackendUnavailable(
                "selected cache target is invalid"
            )
        fd = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        return (
            api.TrustedPathEntry(
                path=os.fspath(path),
                resolved_path=os.fspath(path),
                size=0,
                mode=0o444,
                uid=0,
                gid=0,
                device=1,
                inode=len(admitted_paths),
                digest="sha256:" + ("0" * 64),
                symlinks=(),
            ),
            fd,
        )

    monkeypatch.setattr(
        api._environment,
        "_select_glibc_cache_dependency",
        select_cache,
    )
    monkeypatch.setattr(
        api,
        "_DEFAULT_LIBRARY_DIRECTORIES",
        (os.fspath(default_directory),),
    )
    monkeypatch.setattr(api, "_admit_trusted_regular", admit)
    monkeypatch.setattr(
        api._environment,
        "_parse_elf_fd",
        lambda _fd, _path: leaf_elf,
    )

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match="selected cache target is invalid",
    ):
        api._resolve_host_startup_closure(
            executable,
            parsed=root_elf,
            cache_entries=(object(),),
        )

    assert os.fspath(missing_cache_target) in admitted_paths
    assert os.fspath(default_target) not in admitted_paths


def test_recursive_host_startup_closure_parse_failure_is_stable_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.providers.isolation_environment import ParsedElf

    api = _backend_api()
    executable = Path("/usr/bin/fake-bwrap")
    interpreter = "/lib64/fake-loader.so"
    root_elf = ParsedElf(
        elf_class=2,
        data_encoding=1,
        ident_version=1,
        elf_type=3,
        machine=62,
        header_version=1,
        interpreter=interpreter,
        needed=(),
        rpath=(),
        runpath=(),
    )

    def admit(path: Path, *, keep_open: bool):
        fd = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        return (
            api.TrustedPathEntry(
                path=os.fspath(path),
                resolved_path=os.fspath(path),
                size=0,
                mode=0o444,
                uid=0,
                gid=0,
                device=1,
                inode=1,
                digest="sha256:" + ("0" * 64),
                symlinks=(),
            ),
            fd,
        )

    parse_error = ValueError("invalid recursive ELF")
    monkeypatch.setattr(api, "_admit_trusted_regular", admit)
    monkeypatch.setattr(
        api._environment,
        "_parse_elf_fd",
        lambda _fd, _path: (_ for _ in ()).throw(parse_error),
    )

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match="host startup closure member is not a valid ELF",
    ) as caught:
        api._resolve_host_startup_closure(
            executable,
            parsed=root_elf,
            cache_entries=(),
        )

    assert caught.value.__cause__ is parse_error


def test_backend_preflight_fails_when_rootless_capability_probe_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _backend_api()

    def unavailable(_fd: int):
        raise api.ProviderIsolationBackendUnavailable(
            "rootless capability probe failed"
        )

    monkeypatch.setattr(api, "_run_backend_capability_probe", unavailable)
    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match="rootless capability probe",
    ):
        api.get_provider_isolation_backend("bubblewrap.v1").preflight()


def test_backend_identity_revalidation_rejects_any_bound_byte_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _backend_api()
    backend = api.get_provider_isolation_backend("bubblewrap.v1")
    pinned = backend.preflight()
    try:
        original = api._hash_open_regular

        def changed(fd: int, *, maximum_bytes: int):
            size, digest = original(fd, maximum_bytes=maximum_bytes)
            return size, "sha256:" + ("0" * 64)

        monkeypatch.setattr(api, "_hash_open_regular", changed)
        with pytest.raises(
            api.ProviderIsolationBackendUnavailable,
            match="identity changed",
        ):
            pinned.revalidate()
    finally:
        pinned.close()


def test_subject_request_union_rejects_cross_combinations() -> None:
    api = _backend_api()

    workflow = api.WorkflowProviderIsolationRequest(
        candidate_path="/workspace/product",
        target=("/opt/provider/bin/provider", "--run"),
        environment_digest="sha256:" + ("1" * 64),
        result_channel="typed_bundle",
        provider_template_identity="sha256:" + ("2" * 64),
        aggregate_scope=("root", "step"),
        ordinal=1,
        result_logical_path="/workspace/product/.orchestrate/results/value.json",
        result_bundle_max_bytes=4096,
    )
    controller = api.ControllerAttemptIsolationRequest(
        candidate_path="/workspace/product",
        target=("/opt/provider/bin/provider", "--check"),
        environment_digest="sha256:" + ("1" * 64),
        result_channel="none",
        caller_kind="experiment_arm",
        caller_attempt_id="direct-0001",
        command_identity="sha256:" + ("3" * 64),
        external_sink_identity="sha256:" + ("4" * 64),
    )

    assert workflow.subject_kind == "workflow_provider"
    assert controller.subject_kind == "controller_attempt"
    with pytest.raises(TypeError):
        api.WorkflowProviderIsolationRequest(
            candidate_path="/workspace/product",
            target=("/opt/provider/bin/provider",),
            environment_digest="sha256:" + ("1" * 64),
            result_channel="none",
            provider_template_identity="sha256:" + ("2" * 64),
            aggregate_scope=("root",),
            ordinal=1,
            result_logical_path="/workspace/product/value.json",
            result_bundle_max_bytes=4096,
        )
    with pytest.raises(TypeError):
        api.ControllerAttemptIsolationRequest(
            candidate_path="/workspace/product",
            target=("/opt/provider/bin/provider",),
            environment_digest="sha256:" + ("1" * 64),
            result_channel="typed_bundle",
            caller_kind="experiment_arm",
            caller_attempt_id="direct-0001",
            command_identity="sha256:" + ("3" * 64),
            external_sink_identity="sha256:" + ("4" * 64),
        )


def test_workflow_request_requires_result_bundle_max_bytes() -> None:
    api = _backend_api()

    with pytest.raises(TypeError, match="result_bundle_max_bytes"):
        api.WorkflowProviderIsolationRequest(
            candidate_path="/workspace/product",
            target=("/opt/provider/bin/provider", "--run"),
            environment_digest="sha256:" + ("1" * 64),
            result_channel="typed_bundle",
            provider_template_identity="sha256:" + ("2" * 64),
            aggregate_scope=("root", "step"),
            ordinal=1,
            result_logical_path=(
                "/workspace/product/.orchestrate/results/value.json"
            ),
        )


@pytest.mark.parametrize(
    "result_bundle_max_bytes",
    (False, True, 0, MAX_RESULT_BUNDLE_BYTES + 1),
)
def test_workflow_request_rejects_invalid_result_bundle_max_bytes(
    result_bundle_max_bytes: object,
) -> None:
    api = _backend_api()

    with pytest.raises(TypeError, match="must be a positive integer"):
        api.WorkflowProviderIsolationRequest(
            candidate_path="/workspace/product",
            target=("/opt/provider/bin/provider", "--run"),
            environment_digest="sha256:" + ("1" * 64),
            result_channel="typed_bundle",
            provider_template_identity="sha256:" + ("2" * 64),
            aggregate_scope=("root", "step"),
            ordinal=1,
            result_logical_path=(
                "/workspace/product/.orchestrate/results/value.json"
            ),
            result_bundle_max_bytes=result_bundle_max_bytes,
        )


@pytest.mark.parametrize(
    "result_bundle_max_bytes",
    (1, MAX_RESULT_BUNDLE_BYTES),
)
def test_workflow_request_accepts_result_bundle_size_boundaries(
    result_bundle_max_bytes: int,
) -> None:
    api = _backend_api()

    request = api.WorkflowProviderIsolationRequest(
        candidate_path="/workspace/product",
        target=("/opt/provider/bin/provider", "--run"),
        environment_digest="sha256:" + ("1" * 64),
        result_channel="typed_bundle",
        provider_template_identity="sha256:" + ("2" * 64),
        aggregate_scope=("root", "step"),
        ordinal=1,
        result_logical_path=(
            "/workspace/product/.orchestrate/results/value.json"
        ),
        result_bundle_max_bytes=result_bundle_max_bytes,
    )

    assert request.result_bundle_max_bytes == result_bundle_max_bytes


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        (
            "aggregate_scope",
            tuple(
                f"scope-{index}"
                for index in range(
                    MAX_PROVIDER_ISOLATION_SCOPE_COMPONENTS + 1
                )
            ),
            "aggregate_scope",
        ),
        (
            "aggregate_scope",
            ("x" * (MAX_PROVIDER_ISOLATION_SCOPE_COMPONENT_LENGTH + 1),),
            "aggregate_scope",
        ),
        (
            "ordinal",
            MAX_PROVIDER_ISOLATION_UINT64 + 1,
            "ordinal",
        ),
        (
            "result_logical_path",
            (
                "/workspace/product/.orchestrate/"
                + "/".join(
                    ("x" * 240,) * 16 + ("x" * 241,)
                )
            ),
            "runtime-relative path",
        ),
    ),
)
def test_workflow_request_rejects_journal_unrepresentable_identity_before_scratch(
    field: str,
    value: object,
    message: str,
) -> None:
    api = _backend_api()
    arguments: dict[str, object] = {
        "candidate_path": "/workspace/product",
        "target": ("/opt/provider/bin/provider", "--run"),
        "environment_digest": "sha256:" + ("1" * 64),
        "result_channel": "typed_bundle",
        "provider_template_identity": "sha256:" + ("2" * 64),
        "aggregate_scope": ("root", "step"),
        "ordinal": 1,
        "result_logical_path": (
            "/workspace/product/.orchestrate/results/value.json"
        ),
        "result_bundle_max_bytes": 4096,
    }
    arguments[field] = value

    with pytest.raises(TypeError, match=message):
        api.WorkflowProviderIsolationRequest(**arguments)


def test_workflow_request_accepts_closed_journal_identity_boundaries() -> None:
    api = _backend_api()

    boundary_relpath = "/".join(("x" * 240,) * 17)
    assert len(boundary_relpath) == (
        MAX_PROVIDER_ISOLATION_RUNTIME_RELPATH_LENGTH
    )
    request = api.WorkflowProviderIsolationRequest(
        candidate_path="/workspace/product",
        target=("/opt/provider/bin/provider", "--run"),
        environment_digest="sha256:" + ("1" * 64),
        result_channel="typed_bundle",
        provider_template_identity="sha256:" + ("2" * 64),
        aggregate_scope=tuple(
            "x" * MAX_PROVIDER_ISOLATION_SCOPE_COMPONENT_LENGTH
            for _ in range(MAX_PROVIDER_ISOLATION_SCOPE_COMPONENTS)
        ),
        ordinal=MAX_PROVIDER_ISOLATION_UINT64,
        result_logical_path=(
            "/workspace/product/.orchestrate/" + boundary_relpath
        ),
        result_bundle_max_bytes=4096,
    )

    assert len(request.aggregate_scope) == MAX_PROVIDER_ISOLATION_SCOPE_COMPONENTS
    assert request.ordinal == MAX_PROVIDER_ISOLATION_UINT64
    assert request.result_logical_path.endswith(boundary_relpath)


def test_controller_request_cannot_carry_result_bundle_max_bytes() -> None:
    api = _backend_api()

    with pytest.raises(TypeError, match="result_bundle_max_bytes"):
        api.ControllerAttemptIsolationRequest(
            candidate_path="/workspace/product",
            target=("/opt/provider/bin/provider", "--check"),
            environment_digest="sha256:" + ("1" * 64),
            result_channel="none",
            caller_kind="experiment_arm",
            caller_attempt_id="direct-0001",
            command_identity="sha256:" + ("3" * 64),
            external_sink_identity="sha256:" + ("4" * 64),
            result_bundle_max_bytes=4096,
        )


def test_invocation_plan_is_immutable_and_mount_set_is_closed() -> None:
    backend_api = _backend_api()
    bwrap_api = _bubblewrap_api()
    request = backend_api.WorkflowProviderIsolationRequest(
        candidate_path="/workspace/product",
        target=("/opt/provider/bin/provider", "--run"),
        environment_digest="sha256:" + ("1" * 64),
        result_channel="typed_bundle",
        provider_template_identity="sha256:" + ("2" * 64),
        aggregate_scope=("root", "step"),
        ordinal=1,
        result_logical_path="/workspace/product/.orchestrate/results/value.json",
        result_bundle_max_bytes=8192,
    )
    plan = bwrap_api.build_bubblewrap_plan(
        request=request,
        backend_identity_digest="sha256:" + ("5" * 64),
        network_preflight_digest="sha256:" + ("6" * 64),
        rootfs_fd=40,
        candidate_fd=41,
        scratch_fd=42,
        readiness_fd=43,
        status_fd=44,
        credential_fd=3,
        provider_prefix="/opt/provider",
        synthetic_home="/run/provider-home",
        expected_primary_group_count=1,
        expected_overflow_group_count=2,
    )

    assert plan.backend == "bubblewrap.v1"
    assert plan.network_preflight_digest == "sha256:" + ("6" * 64)
    assert plan.result_bundle_max_bytes == 8192
    assert tuple(binding.role for binding in plan.mounts) == (
        "sealed_rootfs",
        "candidate",
        "active_result_scratch",
    )
    assert tuple(binding.destination for binding in plan.mounts) == (
        "/",
        "/workspace/product",
        "/workspace/product/.orchestrate/results",
    )
    assert all(binding.source_fd in {40, 41, 42} for binding in plan.mounts)
    assert not any(binding.source_path for binding in plan.mounts)
    assert dict(plan.environment) == {
        "HOME": "/run/provider-home",
        "XDG_CONFIG_HOME": "/run/provider-home/.config",
        "XDG_CACHE_HOME": "/run/provider-home/.cache",
        "XDG_DATA_HOME": "/run/provider-home/.local/share",
        "TMPDIR": "/tmp",
        "TMP": "/tmp",
        "TEMP": "/tmp",
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "PATH": "/opt/provider/bin",
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": request.result_logical_path,
    }
    assert "ORCHESTRATOR_OUTPUT_BUNDLE" not in dict(plan.environment)
    with pytest.raises(FrozenInstanceError):
        plan.hostname = "host-name"  # type: ignore[misc]

    argv = bwrap_api.render_bubblewrap_argv(plan)
    assert argv[0] == "/usr/bin/bwrap"
    assert "--ro-bind-fd" in argv
    assert "--bind-fd" in argv
    assert "--ro-bind" not in argv
    assert "--bind" not in argv
    assert not any(item == "/" and argv[index - 1] in {"--ro-bind", "--bind"}
                   for index, item in enumerate(argv) if index)
    for required in (
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-uts",
        "--disable-userns",
        "--assert-userns-disabled",
        "--cap-drop",
        "--new-session",
        "--as-pid-1",
        "--die-with-parent",
        "--clearenv",
    ):
        assert required in argv
    assert "--unshare-net" not in argv
    assert argv[-2:] == ["/opt/provider/bin/provider", "--run"]
    assert "/workspace/product" in argv
    assert "/run/provider-home" in argv
    directory_operands = {
        argv[index + 1]
        for index, value in enumerate(argv[:-1])
        if value == "--dir"
    }
    assert {
        "/run/provider-home",
        "/run/provider-home/.config",
        "/run/provider-home/.cache",
        "/run/provider-home/.local",
        "/run/provider-home/.local/share",
    } <= directory_operands
    output_index = argv.index("--output-bundle")
    assert argv[output_index + 1] == request.result_logical_path


def test_controller_plan_has_no_result_scratch_or_bundle_environment() -> None:
    backend_api = _backend_api()
    bwrap_api = _bubblewrap_api()
    request = backend_api.ControllerAttemptIsolationRequest(
        candidate_path="/tmp/product",
        target=("/opt/provider/bin/provider", "--check"),
        environment_digest="sha256:" + ("1" * 64),
        result_channel="none",
        caller_kind="certified_check",
        caller_attempt_id="check-0001",
        command_identity="sha256:" + ("3" * 64),
        external_sink_identity="sha256:" + ("4" * 64),
    )

    plan = bwrap_api.build_bubblewrap_plan(
        request=request,
        backend_identity_digest="sha256:" + ("5" * 64),
        network_preflight_digest="sha256:" + ("6" * 64),
        rootfs_fd=40,
        candidate_fd=41,
        scratch_fd=None,
        readiness_fd=43,
        status_fd=44,
        credential_fd=3,
        provider_prefix="/opt/provider",
        synthetic_home="/run/provider-home",
        expected_primary_group_count=1,
        expected_overflow_group_count=0,
    )

    assert tuple(binding.role for binding in plan.mounts) == (
        "sealed_rootfs",
        "candidate",
    )
    assert dict(plan.environment) == {
        "HOME": "/run/provider-home",
        "XDG_CONFIG_HOME": "/run/provider-home/.config",
        "XDG_CACHE_HOME": "/run/provider-home/.cache",
        "XDG_DATA_HOME": "/run/provider-home/.local/share",
        "TMPDIR": "/tmp",
        "TMP": "/tmp",
        "TEMP": "/tmp",
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "PATH": "/opt/provider/bin",
    }
    assert "--output-bundle" not in bwrap_api.render_bubblewrap_argv(plan)
    with pytest.raises(backend_api.ProviderIsolationInvalidPlan):
        bwrap_api.build_bubblewrap_plan(
            request=request,
            backend_identity_digest="sha256:" + ("5" * 64),
            network_preflight_digest="sha256:" + ("6" * 64),
            rootfs_fd=40,
            candidate_fd=41,
            scratch_fd=42,
            readiness_fd=43,
            status_fd=44,
            credential_fd=3,
            provider_prefix="/opt/provider",
            synthetic_home="/run/provider-home",
            expected_primary_group_count=1,
            expected_overflow_group_count=0,
        )


def test_plan_rejects_candidate_target_and_noncanonical_or_nonfixed_inputs() -> None:
    backend_api = _backend_api()
    bwrap_api = _bubblewrap_api()
    base_request = backend_api.ControllerAttemptIsolationRequest(
        candidate_path="/tmp/product",
        target=("/opt/provider/bin/provider", "--check"),
        environment_digest="sha256:" + ("1" * 64),
        result_channel="none",
        caller_kind="certified_check",
        caller_attempt_id="check-0001",
        command_identity="sha256:" + ("3" * 64),
        external_sink_identity="sha256:" + ("4" * 64),
    )
    plan = bwrap_api.build_bubblewrap_plan(
        request=base_request,
        backend_identity_digest="sha256:" + ("5" * 64),
        network_preflight_digest="sha256:" + ("6" * 64),
        rootfs_fd=40,
        candidate_fd=41,
        scratch_fd=None,
        readiness_fd=43,
        status_fd=44,
        credential_fd=3,
        provider_prefix="/opt/provider",
        synthetic_home="/run/provider-home",
        expected_primary_group_count=1,
        expected_overflow_group_count=0,
    )

    candidate_target = replace(
        base_request,
        target=("/tmp/product/provider",),
    )
    with pytest.raises(backend_api.ProviderIsolationInvalidPlan):
        bwrap_api.build_bubblewrap_plan(
            request=candidate_target,
            backend_identity_digest="sha256:" + ("5" * 64),
            network_preflight_digest="sha256:" + ("6" * 64),
            rootfs_fd=40,
            candidate_fd=41,
            scratch_fd=None,
            readiness_fd=43,
            status_fd=44,
            credential_fd=3,
            provider_prefix="/opt/provider",
            synthetic_home="/run/provider-home",
            expected_primary_group_count=1,
            expected_overflow_group_count=0,
        )
    for invalid_environment in (
        plan.environment + (("LD_PRELOAD", "/candidate/inject.so"),),
        plan.environment + (("HOME", "/alternate"),),
        plan.environment + (("HOME", "/run/provider-home"),),
    ):
        with pytest.raises(backend_api.ProviderIsolationInvalidPlan):
            replace(plan, environment=invalid_environment)
    with pytest.raises(TypeError):
        backend_api.ControllerAttemptIsolationRequest(
            candidate_path="//tmp/product",
            target=base_request.target,
            environment_digest=base_request.environment_digest,
            result_channel="none",
            caller_kind=base_request.caller_kind,
            caller_attempt_id=base_request.caller_attempt_id,
            command_identity=base_request.command_identity,
            external_sink_identity=base_request.external_sink_identity,
        )
    with pytest.raises(TypeError):
        replace(base_request, target=("//opt/provider/bin/provider",))


def test_typed_invocation_authority_factory_binds_workflow_and_controller(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    workflow_components = _make_typed_invocation_components(
        tmp_path / "workflow",
        workflow=True,
    )
    snapshot, admission, runtime, request = workflow_components
    authority = None
    try:
        authority = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        assert type(authority) is api.PinnedProviderInvocationAuthorities
        assert authority.request == request
        assert authority.request.result_bundle_max_bytes == 4096
        assert authority.environment_digest == snapshot.digest
        assert authority.provider_prefix == "/opt/provider"
        assert authority.candidate_path == os.fspath(admission.path)
        assert authority.scratch_identity is not None
        assert authority.scratch_relpath is not None
        scratch = (
            admission.path / ".orchestrate" / authority.scratch_relpath
        )
        assert scratch.is_dir()
        assert scratch.stat().st_ino == authority.scratch_identity.inode
        root_fd, candidate_fd, scratch_fd = authority._duplicate_setup_fds()
        try:
            assert scratch_fd is not None
            assert len(
                {
                    (os.fstat(root_fd).st_dev, os.fstat(root_fd).st_ino),
                    (
                        os.fstat(candidate_fd).st_dev,
                        os.fstat(candidate_fd).st_ino,
                    ),
                    (os.fstat(scratch_fd).st_dev, os.fstat(scratch_fd).st_ino),
                }
            ) == 3
        finally:
            os.close(root_fd)
            os.close(candidate_fd)
            assert scratch_fd is not None
            os.close(scratch_fd)
        authority.revalidate()
        with pytest.raises(api.ProviderIsolationInvalidPlan):
            api.pin_provider_invocation_authorities(
                snapshot=snapshot,
                candidate=admission,
                runtime=runtime,
                request=request,
            )
    finally:
        if authority is not None:
            authority.close()
        runtime.close()
        admission.close()
        snapshot.close()

    controller_components = _make_typed_invocation_components(
        tmp_path / "controller",
        workflow=False,
    )
    snapshot, admission, runtime, request = controller_components
    authority = None
    try:
        authority = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        assert authority.scratch_identity is None
        assert authority.scratch_relpath is None
        root_fd, candidate_fd, scratch_fd = authority._duplicate_setup_fds()
        try:
            assert scratch_fd is None
        finally:
            os.close(root_fd)
            os.close(candidate_fd)
        snapshot.close()
        with pytest.raises(api.ProviderIsolationInvalidPlan):
            authority.revalidate()
    finally:
        if authority is not None:
            authority.close()
        runtime.close()
        admission.close()
        snapshot.close()


@pytest.mark.parametrize("provider_entry_kind", ("fifo", "symlink"))
def test_workflow_invocation_broker_revalidation_opacifies_only_pinned_scratch(
    tmp_path: Path,
    provider_entry_kind: str,
) -> None:
    api = _backend_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=True,
    )
    authority = None
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unchanged")
    try:
        authority = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        assert authority.scratch_relpath is not None
        scratch = admission.path / ".orchestrate" / authority.scratch_relpath
        provider_entry = scratch / "provider-entry"
        if provider_entry_kind == "fifo":
            os.mkfifo(provider_entry)
        else:
            provider_entry.symlink_to(outside)

        authority.revalidate_for_result_broker_after_quiescence()

        with pytest.raises(api.ProviderIsolationInvalidPlan):
            authority.revalidate()
    finally:
        if authority is not None:
            authority.close()
        runtime.close()
        admission.close()
        snapshot.close()

    assert outside.read_bytes() == b"unchanged"


def test_invocation_broker_revalidation_rejects_non_scratch_tree_mutation(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=True,
    )
    authority = None
    try:
        authority = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        os.mkfifo(admission.path / ".orchestrate" / "hostile")

        with pytest.raises(api.ProviderIsolationInvalidPlan):
            authority.revalidate_for_result_broker_after_quiescence()
    finally:
        if authority is not None:
            authority.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_invocation_broker_revalidation_rejects_complete_scratch_rebinding(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=True,
    )
    authority = None
    alternate_fd = -1
    original_binding = None
    try:
        authority = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        alternate_fd, alternate_identity = runtime.create_fresh_directory(
            "provider-invocation-scratch/alternate",
        )
        original_binding = (
            authority._scratch_relpath,
            authority._scratch_fd,
            authority._scratch_identity,
        )
        authority._scratch_relpath = "provider-invocation-scratch/alternate"
        authority._scratch_fd = alternate_fd
        authority._scratch_identity = alternate_identity

        with pytest.raises(
            api.ProviderIsolationInvalidPlan,
            match="scratch authority",
        ):
            authority.revalidate_for_result_broker_after_quiescence()
    finally:
        if authority is not None and original_binding is not None:
            (
                authority._scratch_relpath,
                authority._scratch_fd,
                authority._scratch_identity,
            ) = original_binding
        if alternate_fd >= 0:
            os.close(alternate_fd)
        if authority is not None:
            authority.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_controller_invocation_cannot_enter_result_broker_revalidation_seam(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=False,
    )
    authority = None
    try:
        authority = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )

        with pytest.raises(
            api.ProviderIsolationInvalidPlan,
            match="workflow",
        ):
            authority.revalidate_for_result_broker_after_quiescence()
    finally:
        if authority is not None:
            authority.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_workflow_invocation_opens_one_descriptor_bound_result_broker_authority(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    broker_api = importlib.import_module(
        "orchestrator.providers.isolation_bundle_broker"
    )
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=True,
        result_bundle_max_bytes=37,
    )
    invocation = None
    broker_authority = None
    try:
        invocation = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        assert invocation.scratch_relpath is not None
        scratch = admission.path / ".orchestrate" / invocation.scratch_relpath
        (scratch / "value.json").write_bytes(b'{"value":true}\n')
        with pytest.raises(
            api.ProviderIsolationInvalidPlan,
            match="launcher-proved quiescence",
        ):
            invocation.open_result_broker_authority_after_quiescence(
                minimum=32,
            )
        invocation._record_result_broker_quiescence(
            "sha256:" + ("8" * 64),
            _token=api._RESULT_BROKER_QUIESCENCE_TOKEN,
        )

        broker_authority = (
            invocation.open_result_broker_authority_after_quiescence(
                minimum=32,
            )
        )

        assert (
            type(broker_authority)
            is api.PinnedProviderResultBrokerAuthorities
        )
        assert broker_authority.request is request
        assert broker_authority.runtime_fd >= 32
        assert broker_authority.scratch_fd >= 32
        assert broker_authority.runtime_fd != broker_authority.scratch_fd
        assert broker_authority.runtime_identity == runtime.identity.runtime
        assert broker_authority.scratch_identity == invocation.scratch_identity
        assert broker_authority.scratch_relpath == invocation.scratch_relpath
        assert broker_authority.target_runtime_relpath == "results/value.json"
        assert broker_authority.active_basename == "value.json"
        assert broker_authority.result_bundle_max_bytes == 37
        assert broker_authority.invocation_identity.startswith("sha256:")

        captured = broker_api.capture_active_bundle_from_authority(
            authority=broker_authority,
        )
        assert captured.classification == "captured"
        assert captured.data == b'{"value":true}\n'
    finally:
        if broker_authority is not None:
            broker_authority.close()
            assert broker_authority.closed is True
            assert broker_authority.runtime_fd == -1
            assert broker_authority.scratch_fd == -1
        if invocation is not None:
            invocation.close()
        runtime.close()
        admission.close()
        snapshot.close()


def _bare_result_broker_authority(api):
    from orchestrator.providers.isolation_runtime_authority import (
        RuntimeAuthorityObjectIdentity,
    )

    runtime_fd, runtime_write_fd = os.pipe()
    scratch_fd, scratch_write_fd = os.pipe()
    request = api.WorkflowProviderIsolationRequest(
        candidate_path="/workspace/product",
        target=("/opt/provider/bin/provider", "--run"),
        environment_digest="sha256:" + ("1" * 64),
        result_channel="typed_bundle",
        provider_template_identity="sha256:" + ("2" * 64),
        aggregate_scope=("root", "step"),
        ordinal=1,
        result_logical_path=(
            "/workspace/product/.orchestrate/results/value.json"
        ),
        result_bundle_max_bytes=4096,
    )
    runtime_identity = RuntimeAuthorityObjectIdentity(
        path="/workspace/product/.orchestrate",
        device=1,
        inode=2,
        mount_id=3,
    )
    scratch_identity = RuntimeAuthorityObjectIdentity(
        path=(
            "/workspace/product/.orchestrate/"
            f"provider-invocation-scratch/{'a' * 64}"
        ),
        device=1,
        inode=4,
        mount_id=3,
    )
    authority = api.PinnedProviderResultBrokerAuthorities(
        request=request,
        runtime_fd=runtime_fd,
        scratch_fd=scratch_fd,
        runtime_identity=runtime_identity,
        scratch_identity=scratch_identity,
        scratch_relpath=f"provider-invocation-scratch/{'a' * 64}",
        target_runtime_relpath="results/value.json",
        active_basename="value.json",
        invocation_identity="sha256:" + ("5" * 64),
        _token=api._RESULT_BROKER_AUTHORITY_TOKEN,
    )
    return authority, runtime_fd, scratch_fd, runtime_write_fd, scratch_write_fd


def test_result_broker_authority_close_attempts_every_fd_after_first_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _backend_api()
    (
        authority,
        runtime_fd,
        scratch_fd,
        runtime_write_fd,
        scratch_write_fd,
    ) = _bare_result_broker_authority(api)
    real_close = api.os.close
    close_attempts: list[int] = []

    def fail_first_close(fd: int) -> None:
        close_attempts.append(fd)
        if fd == scratch_fd:
            raise OSError("injected scratch close failure")
        real_close(fd)

    monkeypatch.setattr(api.os, "close", fail_first_close)
    try:
        with pytest.raises(OSError, match="scratch close failure"):
            authority.close()
        assert close_attempts == [scratch_fd, runtime_fd]
        assert authority.closed is True
        assert authority.scratch_fd == -1
        assert authority.runtime_fd == -1
    finally:
        real_close(scratch_fd)
        real_close(runtime_write_fd)
        real_close(scratch_write_fd)


def test_result_broker_context_close_failure_does_not_mask_primary_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _backend_api()
    (
        authority,
        runtime_fd,
        scratch_fd,
        runtime_write_fd,
        scratch_write_fd,
    ) = _bare_result_broker_authority(api)
    real_close = api.os.close
    close_attempts: list[int] = []

    def fail_first_close(fd: int) -> None:
        close_attempts.append(fd)
        if fd == scratch_fd:
            raise OSError("injected scratch close failure")
        real_close(fd)

    monkeypatch.setattr(api.os, "close", fail_first_close)
    try:
        with pytest.raises(RuntimeError, match="primary failure"):
            with authority:
                raise RuntimeError("primary failure")
        assert close_attempts == [scratch_fd, runtime_fd]
        assert authority.closed is True
    finally:
        real_close(scratch_fd)
        real_close(runtime_write_fd)
        real_close(scratch_write_fd)


@pytest.mark.parametrize(
    "execution_outcome",
    ("eligible_zero", "nonzero", "timeout", "cancelled"),
)
def test_fake_owner_applies_fixed_result_retention_through_broker_authority(
    tmp_path: Path,
    execution_outcome: str,
) -> None:
    api = _backend_api()
    broker_api = importlib.import_module(
        "orchestrator.providers.isolation_bundle_broker"
    )
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=True,
        result_bundle_max_bytes=37,
    )
    results_fd, _results_identity = runtime.create_fresh_directory("results")
    os.close(results_fd)
    invocation = None
    broker_authority = None
    payload = (
        b""
        if execution_outcome == "eligible_zero"
        else b'{"untrusted":"partial"}\n'
    )
    fake_owner_evidence: dict[str, object] = {}
    acknowledgements: list[object] = []
    try:
        invocation = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        assert invocation.scratch_relpath is not None
        scratch = (
            admission.path / ".orchestrate" / invocation.scratch_relpath
        )
        (scratch / "value.json").write_bytes(payload)
        (scratch / "sibling.tmp").write_bytes(b"discard")
        invocation._record_result_broker_quiescence(
            "sha256:" + ("8" * 64),
            _token=api._RESULT_BROKER_QUIESCENCE_TOKEN,
        )
        broker_authority = (
            invocation.open_result_broker_authority_after_quiescence()
        )

        capture = broker_api.capture_active_bundle_from_authority(
            authority=broker_authority,
        )
        transfer_request = (
            broker_api.create_bundle_transfer_request_from_authority(
                authority=broker_authority,
                capture=capture,
            )
        )
        paths = broker_api.derive_bundle_transfer_paths(transfer_request)
        fake_owner_evidence = {
            "execution_outcome": execution_outcome,
            "bundle_digest": capture.digest,
            "bundle_size": capture.size_bytes,
        }
        if execution_outcome == "eligible_zero":
            transfer_record = (
                broker_api.prepare_and_publish_bundle_transfer(
                    transfer_request
                )
            )
            assert transfer_record is not None
            cleanup_evidence = transfer_record
        else:
            # Task 4 replaces this fake decision owner. Noneligible execution
            # never grants its captured-byte request to the publication API.
            cleanup_evidence = capture

        cleanup = (
            broker_api.cleanup_invocation_scratch_after_acknowledgement(
                runtime_root_fd=broker_authority.runtime_fd,
                expected_runtime_mount_id=(
                    broker_authority.runtime_identity.mount_id
                ),
                scratch_directory_fd=broker_authority.scratch_fd,
                scratch_relative_path=broker_authority.scratch_relpath,
                expected_scratch_identity=(
                    broker_authority.scratch_identity
                ),
                evidence=cleanup_evidence,
                acknowledgement=lambda evidence: (
                    acknowledgements.append(evidence) or True
                ),
            )
        )
        target = (
            admission.path
            / ".orchestrate"
            / paths.target_relative_path
        )
        journal = (
            admission.path
            / ".orchestrate"
            / paths.journal_relative_path
        )

        assert capture.classification == "captured"
        assert fake_owner_evidence["bundle_digest"] == (
            "sha256:" + sha256(payload).hexdigest()
        )
        assert fake_owner_evidence["bundle_size"] == len(payload)
        assert cleanup.removed_entry_count == 2
        assert acknowledgements == [cleanup_evidence]
        assert not scratch.exists()
        if execution_outcome == "eligible_zero":
            assert target.read_bytes() == b""
            assert journal.is_file()
        else:
            assert not target.exists()
            assert not journal.exists()
    finally:
        if broker_authority is not None:
            broker_authority.close()
        if invocation is not None:
            invocation.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_transfer_request_factory_rejects_cross_attempt_authority_composition(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    broker_api = importlib.import_module(
        "orchestrator.providers.isolation_bundle_broker"
    )
    first = _make_typed_invocation_components(
        tmp_path / "first",
        workflow=True,
    )
    second = _make_typed_invocation_components(
        tmp_path / "second",
        workflow=True,
        result_bundle_max_bytes=1,
    )
    first_snapshot, first_admission, first_runtime, first_request = first
    second_snapshot, second_admission, second_runtime, second_request = second
    first_results_fd, _ = first_runtime.create_fresh_directory("results")
    second_results_fd, _ = second_runtime.create_fresh_directory("results")
    os.close(first_results_fd)
    os.close(second_results_fd)
    first_invocation = None
    second_invocation = None
    first_broker = None
    second_broker = None
    try:
        first_invocation = api.pin_provider_invocation_authorities(
            snapshot=first_snapshot,
            candidate=first_admission,
            runtime=first_runtime,
            request=first_request,
        )
        second_invocation = api.pin_provider_invocation_authorities(
            snapshot=second_snapshot,
            candidate=second_admission,
            runtime=second_runtime,
            request=second_request,
        )
        assert first_invocation.scratch_relpath is not None
        first_scratch = (
            first_admission.path
            / ".orchestrate"
            / first_invocation.scratch_relpath
        )
        assert second_invocation.scratch_relpath is not None
        second_scratch = (
            second_admission.path
            / ".orchestrate"
            / second_invocation.scratch_relpath
        )
        (first_scratch / "value.json").write_bytes(b'{"value":true}\n')
        (second_scratch / "value.json").write_bytes(b"x")
        first_invocation._record_result_broker_quiescence(
            "sha256:" + ("6" * 64),
            _token=api._RESULT_BROKER_QUIESCENCE_TOKEN,
        )
        second_invocation._record_result_broker_quiescence(
            "sha256:" + ("7" * 64),
            _token=api._RESULT_BROKER_QUIESCENCE_TOKEN,
        )
        first_broker = (
            first_invocation.open_result_broker_authority_after_quiescence()
        )
        second_broker = (
            second_invocation.open_result_broker_authority_after_quiescence()
        )
        capture = broker_api.capture_active_bundle_from_authority(
            authority=first_broker,
        )

        transfer = broker_api.create_bundle_transfer_request_from_authority(
            authority=first_broker,
            capture=capture,
        )

        assert transfer.runtime_root_fd == first_broker.runtime_fd
        assert transfer.invocation_identity == first_broker.invocation_identity
        with pytest.raises(
            TypeError,
            match="authority-bound capture binding",
        ):
            replace(
                capture,
                data=b'{"value":false}\n',
                digest=(
                    "sha256:"
                    + sha256(b'{"value":false}\n').hexdigest()
                ),
                size_bytes=len(b'{"value":false}\n'),
            )
        with pytest.raises(TypeError, match="capture authority binding"):
            broker_api.create_bundle_transfer_request_from_authority(
                authority=second_broker,
                capture=capture,
            )
        bounded_second = broker_api.capture_active_bundle_from_authority(
            authority=second_broker,
        )
        assert bounded_second.classification == "captured"
        second_transfer = (
            broker_api.create_bundle_transfer_request_from_authority(
                authority=second_broker,
                capture=bounded_second,
            )
        )
        first_target = (
            first_admission.path
            / ".orchestrate"
            / transfer.target_relative_path
        )
        with pytest.raises(TypeError, match="request-capture binding"):
            replace(
                transfer,
                capture=bounded_second,
                _capture_binding=bounded_second._binding,
            )
        assert not first_target.exists()
        assert not (
            first_admission.path / ".orchestrate" / broker_api._BROKER_ROOT
        ).exists()
        assert second_transfer.capture is bounded_second

        (second_scratch / "value.json").write_bytes(b"xx")
        bounded_oversize = broker_api.capture_active_bundle_from_authority(
            authority=second_broker,
        )
        assert bounded_oversize.classification == "rejected"
        assert bounded_oversize.reason == broker_api.BUNDLE_OVERSIZED_REASON
        raw_oversize_bypass = broker_api.capture_active_bundle(
            scratch_directory_fd=second_broker.scratch_fd,
            active_basename=second_broker.active_basename,
            expected_scratch_mount_id=second_broker.scratch_identity.mount_id,
            max_bytes=16,
        )
        assert raw_oversize_bypass.classification == "captured"
        with pytest.raises(TypeError, match="authority-bound capture"):
            broker_api.create_bundle_transfer_request_from_authority(
                authority=second_broker,
                capture=raw_oversize_bypass,
            )
        with pytest.raises(TypeError, match="capture"):
            replace(
                transfer,
                capture=raw_oversize_bypass,
            )
        with pytest.raises(TypeError, match="validating factory"):
            broker_api.ProviderIsolationBundleTransferRequest(
                runtime_root_fd=first_broker.runtime_fd,
                expected_runtime_mount_id=(
                    first_broker.runtime_identity.mount_id
                ),
                invocation_identity=first_broker.invocation_identity,
                scope=first_request.aggregate_scope,
                ordinal=first_request.ordinal,
                target_relative_path=first_broker.target_runtime_relpath,
                capture=capture,
            )
        with pytest.raises(TypeError, match="authority binding"):
            replace(
                transfer,
                runtime_root_fd=second_broker.runtime_fd,
                expected_runtime_mount_id=(
                    second_broker.runtime_identity.mount_id
                ),
            )
    finally:
        if second_broker is not None:
            second_broker.close()
        if first_broker is not None:
            first_broker.close()
        if second_invocation is not None:
            second_invocation.close()
        if first_invocation is not None:
            first_invocation.close()
        second_runtime.close()
        second_admission.close()
        second_snapshot.close()
        first_runtime.close()
        first_admission.close()
        first_snapshot.close()


@pytest.mark.parametrize("minimum", (True, 2, -1))
def test_result_broker_authority_rejects_invalid_descriptor_minimum(
    tmp_path: Path,
    minimum: object,
) -> None:
    api = _backend_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=True,
    )
    invocation = None
    try:
        invocation = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        with pytest.raises(api.ProviderIsolationInvalidPlan):
            invocation.open_result_broker_authority_after_quiescence(
                minimum=minimum,
            )
    finally:
        if invocation is not None:
            invocation.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_controller_invocation_cannot_open_result_broker_authority(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=False,
    )
    invocation = None
    try:
        invocation = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        with pytest.raises(
            api.ProviderIsolationInvalidPlan,
            match="workflow",
        ):
            invocation.open_result_broker_authority_after_quiescence()
    finally:
        if invocation is not None:
            invocation.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_same_parent_logical_bundle_names_receive_distinct_scratch_views(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    snapshot, admission, runtime, first_request = (
        _make_typed_invocation_components(
            tmp_path,
            workflow=True,
            ordinal=1,
        )
    )
    second_request = replace(
        first_request,
        ordinal=2,
        result_logical_path=os.fspath(
            admission.path
            / ".orchestrate"
            / "results"
            / "other-value.json"
        ),
    )
    first = None
    second = None
    try:
        first = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=first_request,
        )
        second = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=second_request,
        )

        assert (
            Path(first_request.result_logical_path).parent
            == Path(second_request.result_logical_path).parent
        )
        assert first.scratch_relpath != second.scratch_relpath
        assert first.scratch_identity is not None
        assert second.scratch_identity is not None
        assert (
            first.scratch_identity.device,
            first.scratch_identity.inode,
        ) != (
            second.scratch_identity.device,
            second.scratch_identity.inode,
        )
    finally:
        if second is not None:
            second.close()
        if first is not None:
            first.close()
        runtime.close()
        admission.close()
        snapshot.close()


@pytest.mark.parametrize(
    (
        "workflow",
        "provider_entry_kind",
        "inside_scratch",
        "expect_success",
        "post_release_failure",
        "expect_broker_authority",
    ),
    (
        (True, "fifo", True, True, None, True),
        (True, "symlink", True, True, None, True),
        (True, "fifo", False, False, None, False),
        (False, "fifo", False, False, None, False),
        (True, "fifo", True, False, "timeout", True),
        (True, "symlink", True, False, "cancel", True),
    ),
)
def test_execute_uses_broker_revalidation_only_for_quiescent_workflow_scratch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    workflow: bool,
    provider_entry_kind: str,
    inside_scratch: bool,
    expect_success: bool,
    post_release_failure: str | None,
    expect_broker_authority: bool,
) -> None:
    from orchestrator.providers.isolation_network_preflight import (
        PinnedProviderIsolationNetworkAuthority,
        ProviderIsolationNetworkPreflight,
    )

    backend_api = _backend_api()
    api = _bubblewrap_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=workflow,
    )
    invocation = backend_api.pin_provider_invocation_authorities(
        snapshot=snapshot,
        candidate=admission,
        runtime=runtime,
        request=request,
    )
    broker_authority = None
    events: list[object] = []
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unchanged")
    backend_fd = os.open(os.devnull, os.O_RDONLY | os.O_CLOEXEC)
    backend_identity = type(
        "BackendIdentity",
        (),
        {"digest": "sha256:" + ("5" * 64)},
    )()

    class PinnedBackend:
        executable_fd = backend_fd
        identity = backend_identity

        def revalidate(self):
            events.append("backend_revalidate")
            return self.identity

    capability = ProviderIsolationNetworkPreflight(
        schema_version="provider_isolation_network_preflight.v1",
        endpoint_set_digest="sha256:" + ("6" * 64),
        canonical_json=b"{}",
        digest="sha256:" + ("7" * 64),
    )
    network_authority = object.__new__(
        PinnedProviderIsolationNetworkAuthority
    )
    object.__setattr__(network_authority, "_capability", capability)
    slot_path = tmp_path / "post-quiescence-containment"
    slot_path.mkdir(mode=0o700)
    outer_pid = 4242
    provider_pid = 4343

    class Slot:
        identity_digest = "sha256:" + ("8" * 64)
        path = slot_path
        member_reads = 0

        def revalidate(self) -> None:
            events.append("slot_revalidate")

        @property
        def populated(self) -> bool:
            return False

        def add_pid(self, pid: int) -> None:
            assert pid == outer_pid
            events.append("outer_enrolled")

        def members(self) -> tuple[int, ...]:
            self.member_reads += 1
            if self.member_reads == 1:
                return (outer_pid,)
            return (outer_pid, provider_pid)

        def kill(self) -> None:
            events.append("slot_kill")

        def wait_empty(self, *, timeout_seconds: float) -> None:
            assert timeout_seconds > 0
            events.append("slot_empty")

        def remove(self) -> None:
            events.append("slot_remove")
            slot_path.rmdir()

    class ReleaseGate:
        containment_identity = Slot.identity_digest
        events = ("launch_intent",)
        release_consumed = False
        release_permit = None

        def record_commit(self) -> object:
            events.append("commit")
            return object()

        def consume_release(self, _permit: object) -> None:
            events.append("release")

    original_full_revalidate = (
        backend_api.PinnedProviderInvocationAuthorities.revalidate
    )
    original_broker_revalidate = (
        backend_api.PinnedProviderInvocationAuthorities
        .revalidate_for_result_broker_after_quiescence
    )

    def recording_full_revalidate(
        authority: backend_api.PinnedProviderInvocationAuthorities,
    ) -> None:
        events.append("full_revalidate")
        original_full_revalidate(authority)

    def recording_broker_revalidate(
        authority: backend_api.PinnedProviderInvocationAuthorities,
    ) -> None:
        events.append("broker_revalidate")
        original_broker_revalidate(authority)

    def finish_provider(
        *,
        stdout_fd: int,
        stderr_fd: int,
        status_fd: int,
        wait_state,
        **_kwargs,
    ) -> tuple[int, str, str]:
        for fd in (stdout_fd, stderr_fd, status_fd):
            os.close(fd)
        wait_state.reaped = True
        if inside_scratch:
            assert invocation.scratch_relpath is not None
            parent = (
                admission.path
                / ".orchestrate"
                / invocation.scratch_relpath
            )
        else:
            parent = admission.path / ".orchestrate"
        provider_entry = parent / "provider-entry"
        if provider_entry_kind == "fifo":
            os.mkfifo(provider_entry)
        else:
            provider_entry.symlink_to(outside)
        events.append("provider_quiesced")
        if post_release_failure == "timeout":
            raise TimeoutError("injected post-release timeout")
        if post_release_failure == "cancel":
            raise KeyboardInterrupt("injected post-release cancellation")
        return 0, "", ""

    monkeypatch.setattr(api.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(api.os, "getegid", lambda: 1000)
    monkeypatch.setattr(api.os, "getgroups", lambda: [1000])
    monkeypatch.setattr(
        api,
        "_validate_cgroup_launch_authorities",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(api.os, "fork", lambda: outer_pid)
    monkeypatch.setattr(
        api,
        "_wait_for_bwrap_child_pid",
        lambda *_args, **_kwargs: provider_pid,
    )
    monkeypatch.setattr(
        api,
        "_pin_rootless_child",
        lambda *_args, **_kwargs: (-1, -1, 12345),
    )
    monkeypatch.setattr(
        api,
        "_wait_for_boundary_ready",
        lambda *_args, **_kwargs: events.append("boundary_ready"),
    )
    monkeypatch.setattr(
        api,
        "_validate_pinned_rootless_child_boundary",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(api, "_write_all_fd", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api, "_drain_and_wait", finish_provider)
    monkeypatch.setattr(
        PinnedProviderIsolationNetworkAuthority,
        "revalidate",
        lambda _self: capability,
    )
    monkeypatch.setattr(
        backend_api.PinnedProviderInvocationAuthorities,
        "revalidate",
        recording_full_revalidate,
    )
    monkeypatch.setattr(
        backend_api.PinnedProviderInvocationAuthorities,
        "revalidate_for_result_broker_after_quiescence",
        recording_broker_revalidate,
    )

    try:
        if workflow:
            with pytest.raises(
                backend_api.ProviderIsolationInvalidPlan,
                match="launcher-proved quiescence",
            ):
                invocation.open_result_broker_authority_after_quiescence()
        if expect_success:
            result = api.execute_bubblewrap_invocation(
                invocation_authorities=invocation,
                pinned_backend=PinnedBackend(),
                credentials={},
                declared_credential_names=(),
                release_gate=ReleaseGate(),
                containment_slot=Slot(),
                network_authority=network_authority,
            )
            assert result.returncode == 0
            assert result.containment_empty is True
            if workflow:
                broker_authority = (
                    invocation.open_result_broker_authority_after_quiescence()
                )
                assert (
                    type(broker_authority)
                    is backend_api.PinnedProviderResultBrokerAuthorities
                )
                with pytest.raises(
                    backend_api.ProviderIsolationInvalidPlan,
                    match="already opened",
                ):
                    invocation.open_result_broker_authority_after_quiescence()
        else:
            expected_error = (
                api.ProviderIsolationLaunchError
                if post_release_failure is not None
                else backend_api.ProviderIsolationInvalidPlan
            )
            with pytest.raises(expected_error):
                api.execute_bubblewrap_invocation(
                    invocation_authorities=invocation,
                    pinned_backend=PinnedBackend(),
                    credentials={},
                    declared_credential_names=(),
                    release_gate=ReleaseGate(),
                    containment_slot=Slot(),
                    network_authority=network_authority,
                )
            if expect_broker_authority:
                broker_authority = (
                    invocation.open_result_broker_authority_after_quiescence()
                )
                assert (
                    type(broker_authority)
                    is backend_api.PinnedProviderResultBrokerAuthorities
                )
    finally:
        if broker_authority is not None:
            broker_authority.close()
        os.close(backend_fd)
        invocation.close()
        runtime.close()
        admission.close()
        snapshot.close()

    quiesced_index = events.index("provider_quiesced")
    empty_index = events.index("slot_empty")
    assert quiesced_index < empty_index
    if workflow:
        assert events.index("broker_revalidate") > empty_index
        assert all(
            index < quiesced_index
            for index, event in enumerate(events)
            if event == "full_revalidate"
        )
    else:
        assert "broker_revalidate" not in events
        assert any(
            index > empty_index
            for index, event in enumerate(events)
            if event == "full_revalidate"
        )
    assert outside.read_bytes() == b"unchanged"


def test_invocation_authority_factory_failure_after_scratch_creation_closes_and_removes_scratch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from orchestrator.providers.isolation_runtime_authority import (
        ProviderIsolationRuntimeAuthority,
    )

    api = _backend_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=True,
    )
    expected_relpath = api._invocation_scratch_relpath(request)
    expected_leaf = admission.path / ".orchestrate" / expected_relpath
    created_identity: tuple[int, int] | None = None
    original_create = ProviderIsolationRuntimeAuthority.create_fresh_directory
    original_revalidate = api.PinnedProviderInvocationAuthorities.revalidate

    def record_created_leaf(
        self: ProviderIsolationRuntimeAuthority,
        relpath: str,
        *,
        parents: bool = False,
    ):
        nonlocal created_identity
        directory_fd, identity = original_create(
            self,
            relpath,
            parents=parents,
        )
        created_identity = (identity.device, identity.inode)
        assert relpath == expected_relpath
        assert expected_leaf.is_dir()
        return directory_fd, identity

    def reject_final_revalidation(
        _authority: api.PinnedProviderInvocationAuthorities,
    ) -> None:
        assert created_identity is not None
        raise api.ProviderIsolationInvalidPlan(
            "injected final authority revalidation failure"
        )

    monkeypatch.setattr(
        ProviderIsolationRuntimeAuthority,
        "create_fresh_directory",
        record_created_leaf,
    )
    monkeypatch.setattr(
        api.PinnedProviderInvocationAuthorities,
        "revalidate",
        reject_final_revalidation,
    )
    retry_authority = None
    try:
        with pytest.raises(
            api.ProviderIsolationInvalidPlan,
            match="injected final authority revalidation failure",
        ):
            api.pin_provider_invocation_authorities(
                snapshot=snapshot,
                candidate=admission,
                runtime=runtime,
                request=request,
            )

        assert created_identity is not None
        assert not expected_leaf.exists()
        leaked_fds: list[int] = []
        for name in os.listdir("/proc/self/fd"):
            try:
                descriptor = int(name)
                observed = os.fstat(descriptor)
            except (OSError, ValueError):
                continue
            if (observed.st_dev, observed.st_ino) == created_identity:
                leaked_fds.append(descriptor)
        assert leaked_fds == []

        monkeypatch.setattr(
            api.PinnedProviderInvocationAuthorities,
            "revalidate",
            original_revalidate,
        )
        retry_authority = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        assert retry_authority.scratch_relpath == expected_relpath
        assert expected_leaf.is_dir()
        retry_authority.close()
        retry_authority = None
        assert expected_leaf.is_dir()
    finally:
        if retry_authority is not None:
            retry_authority.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_typed_invocation_authority_rejects_forgery_mismatch_and_scratch_swap(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    bwrap_api = _bubblewrap_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=True,
    )
    authority = None
    try:
        with pytest.raises(api.ProviderIsolationInvalidPlan):
            api.pin_provider_invocation_authorities(
                snapshot=object(),  # type: ignore[arg-type]
                candidate=admission,
                runtime=runtime,
                request=request,
            )
        with pytest.raises(api.ProviderIsolationInvalidPlan):
            api.PinnedProviderInvocationAuthorities(
                snapshot=snapshot,
                candidate=admission,
                runtime=runtime,
                request=request,
            )
        authority = api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
        mismatched = replace(
            request,
            environment_digest="sha256:" + ("9" * 64),
        )
        with pytest.raises(api.ProviderIsolationInvalidPlan):
            api.pin_provider_invocation_authorities(
                snapshot=snapshot,
                candidate=admission,
                runtime=runtime,
                request=mismatched,
            )
        parameters = inspect.signature(
            bwrap_api.execute_bubblewrap_invocation
        ).parameters
        for removed in (
            "rootfs_fd",
            "rootfs_environment_digest",
            "candidate_fd",
            "scratch_fd",
            "provider_prefix",
            "revalidate_authorities",
            "request",
        ):
            assert removed not in parameters
        assert "invocation_authorities" in parameters

        assert authority.scratch_relpath is not None
        scratch = admission.path / ".orchestrate" / authority.scratch_relpath
        displaced = scratch.with_name(scratch.name + "-displaced")
        scratch.rename(displaced)
        scratch.mkdir(mode=0o700)
        with pytest.raises(api.ProviderIsolationInvalidPlan):
            authority.revalidate()
        with pytest.raises(api.ProviderIsolationInvalidPlan):
            bwrap_api.execute_bubblewrap_invocation(
                invocation_authorities=authority,
                pinned_backend=None,  # type: ignore[arg-type]
                credentials={},
                declared_credential_names=(),
                release_gate=None,  # type: ignore[arg-type]
                containment_slot=None,  # type: ignore[arg-type]
                network_authority=None,  # type: ignore[arg-type]
            )
    finally:
        if authority is not None:
            authority.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_typed_invocation_authority_rejects_hostile_string_subclass_bindings(
    tmp_path: Path,
) -> None:
    api = _backend_api()

    class HostileDigest(str):
        def __ne__(self, _other: object) -> bool:
            return False

    class HostileTarget(str):
        def startswith(
            self,
            _prefix: object,
            *_args: object,
        ) -> bool:
            return True

    accepted: list[str] = []
    for label in ("digest", "target"):
        snapshot, admission, runtime, request = (
            _make_typed_invocation_components(
                tmp_path / label,
                workflow=False,
            )
        )
        try:
            if label == "digest":
                object.__setattr__(
                    request,
                    "environment_digest",
                    HostileDigest("sha256:" + ("9" * 64)),
                )
            else:
                object.__setattr__(
                    request,
                    "target",
                    (HostileTarget("/bin/sh"),),
                )
            try:
                authority = api.pin_provider_invocation_authorities(
                    snapshot=snapshot,
                    candidate=admission,
                    runtime=runtime,
                    request=request,
                )
            except api.ProviderIsolationInvalidPlan:
                pass
            else:
                accepted.append(label)
                authority.close()
        finally:
            runtime.close()
            admission.close()
            snapshot.close()
    assert accepted == []


@pytest.mark.parametrize("substituted_role", ("rootfs", "candidate", "scratch"))
def test_typed_invocation_setup_fds_reject_role_substitution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    substituted_role: str,
) -> None:
    import fcntl

    from orchestrator.providers.isolation_candidate import (
        ProviderCandidateAdmission,
    )
    from orchestrator.providers.isolation_environment import (
        ProviderEnvironmentSnapshot,
    )
    from orchestrator.providers.isolation_runtime_authority import (
        ProviderIsolationRuntimeAuthority,
    )

    api = _backend_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=True,
    )
    authority = api.pin_provider_invocation_authorities(
        snapshot=snapshot,
        candidate=admission,
        runtime=runtime,
        request=request,
    )
    substitute = tmp_path / "substitute"
    substitute.mkdir(mode=0o700)
    substitute_fd = os.open(
        substitute,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
    )

    def duplicate_substitute(*_args, minimum: int = 16, **_kwargs) -> int:
        return fcntl.fcntl(
            substitute_fd,
            fcntl.F_DUPFD_CLOEXEC,
            minimum,
        )

    try:
        if substituted_role == "rootfs":
            monkeypatch.setattr(
                ProviderEnvironmentSnapshot,
                "duplicate_root_fd_for_launch",
                duplicate_substitute,
                raising=False,
            )
        elif substituted_role == "candidate":
            monkeypatch.setattr(
                ProviderCandidateAdmission,
                "duplicate_root_fd",
                duplicate_substitute,
            )
        else:
            monkeypatch.setattr(
                ProviderIsolationRuntimeAuthority,
                "duplicate_directory_binding",
                duplicate_substitute,
                raising=False,
            )

        with pytest.raises(api.ProviderIsolationInvalidPlan):
            authority._duplicate_setup_fds()
    finally:
        os.close(substitute_fd)
        authority.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_execution_exposes_no_raw_mount_or_environment_authority_inputs() -> None:
    bwrap_api = _bubblewrap_api()
    parameters = inspect.signature(
        bwrap_api.execute_bubblewrap_invocation
    ).parameters
    assert "invocation_authorities" in parameters
    assert "request" not in parameters
    assert {
        "rootfs_fd",
        "rootfs_environment_digest",
        "candidate_fd",
        "scratch_fd",
        "provider_prefix",
        "revalidate_authorities",
    }.isdisjoint(parameters)


def test_execution_requires_exact_pinned_network_authority_without_callback_bypass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend_api = _backend_api()
    bwrap_api = _bubblewrap_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=False,
    )
    invocation_authorities = (
        backend_api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime,
            request=request,
        )
    )
    monkeypatch.setattr(bwrap_api.os, "geteuid", lambda: 1000)

    parameters = inspect.signature(
        bwrap_api.execute_bubblewrap_invocation
    ).parameters
    assert parameters["network_authority"].default is inspect.Parameter.empty
    assert "revalidate_network" not in parameters
    assert "network_preflight" not in parameters
    try:
        with pytest.raises(
            backend_api.ProviderIsolationInvalidPlan,
            match="network authority",
        ):
            bwrap_api.execute_bubblewrap_invocation(
                invocation_authorities=invocation_authorities,
                pinned_backend=None,  # type: ignore[arg-type]
                credentials={},
                declared_credential_names=(),
                release_gate=None,  # type: ignore[arg-type]
                containment_slot=None,  # type: ignore[arg-type]
                network_authority=object(),  # type: ignore[arg-type]
            )
    finally:
        invocation_authorities.close()
        runtime.close()
        admission.close()
        snapshot.close()


def test_parent_enrolls_exact_outer_child_before_releasing_one_byte_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _bubblewrap_api()
    events: list[object] = []

    class ExactSlot:
        def add_pid(self, pid: int) -> None:
            events.append(("add", pid))

        def members(self) -> tuple[int, ...]:
            events.append("members")
            return (4242,)

    monkeypatch.setattr(
        api,
        "_write_all_fd",
        lambda fd, value: events.append(("write", fd, value)),
    )
    monkeypatch.setattr(
        api,
        "_safe_close",
        lambda fd: events.append(("close", fd)),
    )

    api._enroll_outer_child_and_release(
        outer_pid=4242,
        containment_slot=ExactSlot(),
        gate_write_fd=91,
    )

    assert events == [
        ("add", 4242),
        "members",
        ("write", 91, b"\x01"),
        ("close", 91),
    ]


def test_execute_enrolls_and_releases_before_status_wait(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import fcntl

    from orchestrator.providers.isolation_network_preflight import (
        PinnedProviderIsolationNetworkAuthority,
        ProviderIsolationNetworkPreflight,
    )

    backend_api = _backend_api()
    api = _bubblewrap_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=False,
    )
    invocation = backend_api.pin_provider_invocation_authorities(
        snapshot=snapshot,
        candidate=admission,
        runtime=runtime,
        request=request,
    )
    events: list[object] = []
    backend_fd = os.open(os.devnull, os.O_RDONLY | os.O_CLOEXEC)
    backend_identity = type(
        "BackendIdentity",
        (),
        {"digest": "sha256:" + ("5" * 64)},
    )()

    class PinnedBackend:
        executable_fd = backend_fd
        identity = backend_identity

        def revalidate(self):
            events.append("backend_revalidate")
            return self.identity

    capability = ProviderIsolationNetworkPreflight(
        schema_version="provider_isolation_network_preflight.v1",
        endpoint_set_digest="sha256:" + ("6" * 64),
        canonical_json=b"{}",
        digest="sha256:" + ("7" * 64),
    )
    network_authority = object.__new__(
        PinnedProviderIsolationNetworkAuthority
    )
    object.__setattr__(network_authority, "_capability", capability)
    monkeypatch.setattr(
        PinnedProviderIsolationNetworkAuthority,
        "revalidate",
        lambda _self: capability,
    )
    slot_path = tmp_path / "mock-containment-slot"
    slot_path.mkdir(mode=0o700)

    class Slot:
        identity_digest = "sha256:" + ("8" * 64)
        path = slot_path

        def revalidate(self) -> None:
            events.append("slot_revalidate")

        @property
        def populated(self) -> bool:
            return False

        def add_pid(self, pid: int) -> None:
            events.append(("add", pid))

        def members(self) -> tuple[int, ...]:
            events.append("members")
            return (4242,)

        def kill(self) -> None:
            events.append("kill")

        def wait_empty(self, *, timeout_seconds: float) -> None:
            events.append("empty")

        def remove(self) -> None:
            events.append("remove")
            slot_path.rmdir()

    slot = Slot()

    class ReleaseGate:
        containment_identity = slot.identity_digest
        events = ("launch_intent",)
        release_consumed = False
        release_permit = None

    gate_pair: list[int] = []
    gate_cloexec: list[bool] = []
    real_pipe2 = api.os.pipe2
    pipe_count = 0

    def recording_pipe2(flags: int) -> tuple[int, int]:
        nonlocal pipe_count
        pair = real_pipe2(flags)
        pipe_count += 1
        if pipe_count == 6:
            gate_pair[:] = pair
            gate_cloexec.extend(
                bool(
                    fcntl.fcntl(fd, fcntl.F_GETFD)
                    & fcntl.FD_CLOEXEC
                )
                for fd in pair
            )
            events.append("gate_pipe")
        return pair

    real_safe_close = api._safe_close

    def recording_close(fd: int) -> None:
        if gate_pair and fd == gate_pair[0]:
            events.append("close_gate_read")
        elif gate_pair and fd == gate_pair[1]:
            events.append("close_gate_write")
        real_safe_close(fd)

    real_write_all = api._write_all_fd

    def recording_write_all(fd: int, value: bytes | bytearray) -> None:
        if gate_pair and fd == gate_pair[1]:
            events.append(("release", bytes(value)))
            return
        real_write_all(fd, value)

    def stop_at_status_wait(*_args, **_kwargs):
        events.append("status_wait")
        raise api.ProviderIsolationLaunchError("stop after gate ordering")

    monkeypatch.setattr(api.os, "pipe2", recording_pipe2)
    monkeypatch.setattr(
        api.os,
        "fork",
        lambda: events.append("fork") or 4242,
    )
    monkeypatch.setattr(
        api,
        "_validate_cgroup_launch_authorities",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(api, "_safe_close", recording_close)
    monkeypatch.setattr(api, "_write_all_fd", recording_write_all)
    monkeypatch.setattr(api, "_wait_for_bwrap_child_pid", stop_at_status_wait)
    monkeypatch.setattr(api.os, "kill", lambda _pid, _signal: None)
    monkeypatch.setattr(api.os, "waitpid", lambda pid, _flags: (pid, 0))

    try:
        with pytest.raises(
            api.ProviderIsolationLaunchError,
            match="stop after gate ordering",
        ):
            api.execute_bubblewrap_invocation(
                invocation_authorities=invocation,
                pinned_backend=PinnedBackend(),
                credentials={},
                declared_credential_names=(),
                release_gate=ReleaseGate(),
                containment_slot=slot,
                network_authority=network_authority,
            )
    finally:
        os.close(backend_fd)
        invocation.close()
        runtime.close()
        admission.close()
        snapshot.close()

    ordering = [
        "gate_pipe",
        "fork",
        "close_gate_read",
        ("add", 4242),
        "members",
        ("release", b"\x01"),
        "close_gate_write",
        "status_wait",
    ]
    positions = [events.index(item) for item in ordering]
    assert positions == sorted(positions)
    assert gate_cloexec == [True, True]
    assert events.count("close_gate_read") == 1
    assert events.count("close_gate_write") == 1


@pytest.mark.parametrize("with_scratch", (False, True))
def test_child_setup_waits_for_parent_gate_and_closes_only_exact_roles(
    monkeypatch: pytest.MonkeyPatch,
    with_scratch: bool,
) -> None:
    api = _bubblewrap_api()
    duplicated: list[tuple[int, int, bool]] = []
    allowed: list[set[int]] = []
    armed: list[int] = []
    reads: list[tuple[int, int]] = []
    closed: list[int] = []

    class ChildExit(BaseException):
        pass

    roles = {
        0: 100,
        1: 101,
        2: 102,
        3: 103,
        4: 104,
        5: 105,
        7: 107,
        8: 108,
    }
    if with_scratch:
        roles[6] = 106

    monkeypatch.setattr(api.os, "setsid", lambda: None)
    monkeypatch.setattr(
        api,
        "_arm_parent_death_signal",
        lambda pid: armed.append(pid),
        raising=False,
    )
    monkeypatch.setattr(
        api.os,
        "read",
        lambda fd, size: reads.append((fd, size)) or b"\x01",
    )
    monkeypatch.setattr(api.os, "close", lambda fd: closed.append(fd))
    monkeypatch.setattr(
        api.os,
        "dup2",
        lambda source, target, *, inheritable: duplicated.append(
            (source, target, inheritable)
        ),
    )
    monkeypatch.setattr(
        api,
        "_close_unlisted_fds",
        lambda values: allowed.append(set(values)),
    )
    monkeypatch.setattr(
        api.os,
        "execve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("stop")),
    )
    monkeypatch.setattr(api.os, "write", lambda _fd, value: len(value))
    monkeypatch.setattr(
        api.os,
        "_exit",
        lambda _code: (_ for _ in ()).throw(ChildExit()),
    )

    try:
        with pytest.raises(ChildExit):
            api._child_exec_pinned_backend(
                executable_fd=64,
                argv=["/usr/bin/bwrap"],
                roles=roles,
                start_gate_read_fd=90,
                start_gate_write_fd=91,
                expected_parent_pid=4242,
            )
    finally:
        monkeypatch.undo()

    assert "containment_path" not in inspect.signature(
        api._child_exec_pinned_backend
    ).parameters
    assert armed == [4242]
    assert reads == [(90, 1)]
    assert closed[:2] == [91, 90]
    assert duplicated == [
        (source, target, True)
        for target, source in sorted(roles.items())
    ]
    assert allowed == [{*roles, 64}]
    if with_scratch:
        assert (106, 6, True) in duplicated
    else:
        assert 6 not in allowed[0]


def test_child_gate_eof_never_executes_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _bubblewrap_api()
    executed: list[bool] = []
    closed: list[int] = []

    class ChildExit(BaseException):
        pass

    monkeypatch.setattr(api.os, "setsid", lambda: None)
    monkeypatch.setattr(
        api,
        "_arm_parent_death_signal",
        lambda _pid: None,
        raising=False,
    )
    monkeypatch.setattr(api.os, "read", lambda _fd, _size: b"")
    monkeypatch.setattr(api.os, "close", lambda fd: closed.append(fd))
    monkeypatch.setattr(
        api.os,
        "execve",
        lambda *_args, **_kwargs: executed.append(True),
    )
    monkeypatch.setattr(api.os, "write", lambda _fd, value: len(value))
    monkeypatch.setattr(
        api.os,
        "_exit",
        lambda _code: (_ for _ in ()).throw(ChildExit()),
    )

    try:
        with pytest.raises(ChildExit):
            api._child_exec_pinned_backend(
                executable_fd=64,
                argv=["/usr/bin/bwrap"],
                roles={},
                start_gate_read_fd=90,
                start_gate_write_fd=91,
                expected_parent_pid=4242,
            )
    finally:
        monkeypatch.undo()

    assert executed == []
    assert closed[:2] == [91, 90]


def test_controller_fixed_fd_reservations_leave_six_closed() -> None:
    script = """
import os
from orchestrator.providers.isolation_bubblewrap import _reserve_fixed_fds

for fd in range(3, 9):
    try:
        os.close(fd)
    except OSError:
        pass
reserved = _reserve_fixed_fds({0, 1, 2, 3, 4, 5, 7, 8})
observed = {}
for fd in range(9):
    try:
        os.fstat(fd)
    except OSError:
        observed[fd] = False
    else:
        observed[fd] = True
assert observed == {
    0: True,
    1: True,
    2: True,
    3: True,
    4: True,
    5: True,
    6: False,
    7: True,
    8: True,
}, observed
for fd in reserved:
    os.close(fd)
""".strip()
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_durable_release_gate_is_one_use_and_reload_cannot_release(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    path = tmp_path / "launch-release.json"
    gate = api.DurableLaunchReleaseGate.create(
        path,
        launch_token="sha256:" + ("a" * 64),
        containment_identity="sha256:" + ("b" * 64),
    )
    gate.record_intent()
    reloaded = api.DurableLaunchReleaseGate.load(path)
    assert reloaded.release_permit is None

    permit = gate.record_commit()
    assert permit is not None
    assert gate.consume_release(permit) is None
    assert api.DurableLaunchReleaseGate.load(path).release_permit is None
    with pytest.raises(api.ProviderIsolationStateError):
        gate.consume_release(permit)
    with pytest.raises(api.ProviderIsolationStateError):
        gate.record_commit()


def test_release_gate_serializes_stale_handles_without_rollback(
    tmp_path: Path,
) -> None:
    api = _backend_api()
    path = tmp_path / "launch-release.json"
    gate = api.DurableLaunchReleaseGate.create(
        path,
        launch_token="sha256:" + ("a" * 64),
        containment_identity="sha256:" + ("b" * 64),
    )
    stale_empty = api.DurableLaunchReleaseGate.load(path)

    gate.record_intent()
    with pytest.raises(api.ProviderIsolationStateError):
        stale_empty.record_intent()
    assert stale_empty.events == ()
    assert api.DurableLaunchReleaseGate.load(path).events == ("launch_intent",)

    first = api.DurableLaunchReleaseGate.load(path)
    second = api.DurableLaunchReleaseGate.load(path)
    permit = first.record_commit()
    with pytest.raises(api.ProviderIsolationStateError):
        second.record_commit()
    assert second.events == ("launch_intent",)
    persisted = api.DurableLaunchReleaseGate.load(path)
    assert persisted.events == ("launch_intent", "launch_committed")
    assert persisted.release_consumed is False

    competing_consumer = copy.copy(first)
    first.consume_release(permit)
    with pytest.raises(api.ProviderIsolationStateError):
        competing_consumer.consume_release(permit)
    assert competing_consumer.release_consumed is False
    persisted = api.DurableLaunchReleaseGate.load(path)
    assert persisted.events == ("launch_intent", "launch_committed")
    assert persisted.release_consumed is True


def test_release_gate_failed_replace_leaves_memory_and_disk_consistent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _backend_api()
    path = tmp_path / "launch-release.json"
    gate = api.DurableLaunchReleaseGate.create(
        path,
        launch_token="sha256:" + ("a" * 64),
        containment_identity="sha256:" + ("b" * 64),
    )
    before = path.read_bytes()
    real_replace = api.os.replace

    def fail_replace(*_args, **_kwargs) -> None:
        raise OSError("injected atomic-replace failure")

    monkeypatch.setattr(api.os, "replace", fail_replace)
    with pytest.raises(api.ProviderIsolationStateError):
        gate.record_intent()

    assert gate.events == ()
    assert gate.release_consumed is False
    assert gate.release_permit is None
    assert path.read_bytes() == before

    monkeypatch.setattr(api.os, "replace", real_replace)
    gate.record_intent()
    before_commit = path.read_bytes()
    monkeypatch.setattr(api.os, "replace", fail_replace)
    with pytest.raises(api.ProviderIsolationStateError):
        gate.record_commit()

    assert gate.events == ("launch_intent",)
    assert gate.release_consumed is False
    assert gate.release_permit is None
    assert path.read_bytes() == before_commit

    monkeypatch.setattr(api.os, "replace", real_replace)
    permit = gate.record_commit()
    before_consume = path.read_bytes()
    monkeypatch.setattr(api.os, "replace", fail_replace)
    with pytest.raises(api.ProviderIsolationStateError):
        gate.consume_release(permit)

    assert gate.events == ("launch_intent", "launch_committed")
    assert gate.release_consumed is False
    assert gate.release_permit == permit
    assert path.read_bytes() == before_consume


@pytest.mark.parametrize("transition", ("intent", "commit", "consume"))
def test_release_gate_post_replace_fsync_failure_poison_reconciles_visible_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    transition: str,
) -> None:
    api = _backend_api()
    path = tmp_path / "launch-release.json"
    gate = api.DurableLaunchReleaseGate.create(
        path,
        launch_token="sha256:" + ("a" * 64),
        containment_identity="sha256:" + ("b" * 64),
    )
    permit: str | None = None
    if transition in {"commit", "consume"}:
        gate.record_intent()
    if transition == "consume":
        permit = gate.record_commit()

    real_replace = api.os.replace
    real_fsync = api.os.fsync
    replaced = False

    def observe_replace(*args, **kwargs) -> None:
        nonlocal replaced
        real_replace(*args, **kwargs)
        replaced = True

    def fail_post_replace_parent_fsync(fd: int) -> None:
        if replaced and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("injected parent durability failure")
        real_fsync(fd)

    monkeypatch.setattr(api.os, "replace", observe_replace)
    monkeypatch.setattr(api.os, "fsync", fail_post_replace_parent_fsync)
    with pytest.raises(
        api.ProviderIsolationStateError,
        match="durability.*poisoned",
    ):
        if transition == "intent":
            gate.record_intent()
        elif transition == "commit":
            gate.record_commit()
        else:
            assert permit is not None
            gate.consume_release(permit)

    expected_events = {
        "intent": ("launch_intent",),
        "commit": ("launch_intent", "launch_committed"),
        "consume": ("launch_intent", "launch_committed"),
    }[transition]
    assert gate.events == expected_events
    assert gate.release_consumed is (transition == "consume")
    assert gate.release_permit is None
    assert gate.poisoned is True
    fresh = api.DurableLaunchReleaseGate.load(path)
    assert fresh.events == expected_events
    assert fresh.release_consumed is (transition == "consume")
    assert fresh.release_permit is None

    with pytest.raises(api.ProviderIsolationStateError, match="poisoned"):
        if transition == "intent":
            gate.record_intent()
        elif transition == "commit":
            gate.record_commit()
        else:
            assert permit is not None
            gate.consume_release(permit)


def test_release_gate_rejects_malformed_or_ambiguous_state(tmp_path: Path) -> None:
    api = _backend_api()
    path = tmp_path / "launch-release.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "provider_isolation_launch_release.v1",
                "launch_token": "sha256:" + ("a" * 64),
                "containment_identity": "sha256:" + ("b" * 64),
                "events": ["launch_committed"],
                "release_consumed": False,
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)

    with pytest.raises(api.ProviderIsolationStateError):
        api.DurableLaunchReleaseGate.load(path)


def test_missing_cgroup_delegation_fails_with_stable_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _backend_api()
    monkeypatch.setattr(api, "_read_self_cgroup", lambda: "1:name=systemd:/x\n")

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match="cgroup-v2",
    ):
        api.CgroupV2ContainmentRoot.discover()


@pytest.mark.parametrize(
    "unsafe_field",
    (None, "mount_uid", "mount_gid", "mount_mode", "root_uid", "root_mode"),
)
def test_cgroup_root_discovery_requires_trusted_initial_ownership_and_modes(
    monkeypatch: pytest.MonkeyPatch,
    unsafe_field: str | None,
) -> None:
    api = _backend_api()
    root_uid = 1000 if unsafe_field != "root_uid" else 1001
    root_mode = 0o700 if unsafe_field != "root_mode" else 0o722
    mount_uid = 0 if unsafe_field != "mount_uid" else 1
    mount_gid = 0 if unsafe_field != "mount_gid" else 1
    mount_mode = 0o555 if unsafe_field != "mount_mode" else 0o577
    root_value = os.stat_result(
        (
            stat.S_IFDIR | root_mode,
            101,
            30,
            1,
            root_uid,
            1000,
            0,
            0,
            0,
            0,
        )
    )
    mount_value = os.stat_result(
        (
            stat.S_IFDIR | mount_mode,
            1,
            30,
            1,
            mount_uid,
            mount_gid,
            0,
            0,
            0,
            0,
        )
    )
    monkeypatch.setattr(api, "_read_self_cgroup", lambda: "0::/delegated\n")
    monkeypatch.setattr(api, "_expected_cgroup2_mount", lambda _path: True)
    monkeypatch.setattr(
        api,
        "_read_cgroup_root_identity",
        lambda _path: (mount_value, 77, root_value, 77),
    )
    monkeypatch.setattr(api.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(api.os, "access", lambda *_args: True)
    monkeypatch.setattr(
        api.Path,
        "is_file",
        lambda self: self.name in {"cgroup.procs", "cgroup.events"},
    )
    monkeypatch.setattr(api.Path, "is_symlink", lambda _self: False)

    if unsafe_field is None:
        root = api.CgroupV2ContainmentRoot.discover()
        assert root.uid == 1000
        assert root.mount_uid == 0
    else:
        with pytest.raises(
            api.ProviderIsolationBackendUnavailable,
            match="cgroup-v2 scope is not delegated",
        ):
            api.CgroupV2ContainmentRoot.discover()


@pytest.mark.parametrize(
    ("changed_authority", "changed_field"),
    (
        (None, None),
        ("delegated_root", "device"),
        ("delegated_root", "inode"),
        ("delegated_root", "uid"),
        ("delegated_root", "gid"),
        ("delegated_root", "mode"),
        ("delegated_root", "statx_mount_id"),
        ("cgroup2_mount", "device"),
        ("cgroup2_mount", "inode"),
        ("cgroup2_mount", "uid"),
        ("cgroup2_mount", "gid"),
        ("cgroup2_mount", "mode"),
        ("cgroup2_mount", "statx_mount_id"),
    ),
)
def test_cgroup_root_revalidation_binds_complete_descriptor_identity(
    monkeypatch: pytest.MonkeyPatch,
    changed_authority: str | None,
    changed_field: str | None,
) -> None:
    api = _backend_api()
    delegated_root = Path("/delegated-cgroup")
    cgroup2_mount = Path("/sys/fs/cgroup")
    root_fd = 601
    mount_fd = 602
    root_value = os.stat_result(
        (stat.S_IFDIR | 0o700, 101, 30, 1, 1000, 1000, 0, 0, 0, 0)
    )
    mount_value = os.stat_result(
        (stat.S_IFDIR | 0o555, 1, 30, 1, 0, 0, 0, 0, 0, 0)
    )
    authority = api.CgroupV2ContainmentRoot(
        path=delegated_root,
        device=root_value.st_dev,
        inode=root_value.st_ino,
        uid=root_value.st_uid,
        gid=root_value.st_gid,
        mode=stat.S_IMODE(root_value.st_mode),
        statx_mount_id=77,
        mount_device=mount_value.st_dev,
        mount_inode=mount_value.st_ino,
        mount_uid=mount_value.st_uid,
        mount_gid=mount_value.st_gid,
        mount_mode=stat.S_IMODE(mount_value.st_mode),
        mount_statx_mount_id=77,
        identity_digest="sha256:" + ("a" * 64),
    )
    opened: list[tuple[Path, int]] = []
    closed: list[int] = []

    def changed_stat(
        value: os.stat_result,
        field: str | None,
    ) -> os.stat_result:
        if field == "statx_mount_id" or field is None:
            return value
        fields = list(value)
        index = {
            "mode": 0,
            "inode": 1,
            "device": 2,
            "uid": 4,
            "gid": 5,
        }[field]
        fields[index] += 1
        return os.stat_result(fields)

    def open_directory(path: os.PathLike[str] | str, flags: int) -> int:
        candidate = Path(path)
        opened.append((candidate, flags))
        if candidate == delegated_root:
            return root_fd
        if candidate == cgroup2_mount:
            return mount_fd
        raise AssertionError(f"unexpected directory open: {candidate}")

    def fstat_directory(fd: int) -> os.stat_result:
        if fd == root_fd:
            field = changed_field if changed_authority == "delegated_root" else None
            return changed_stat(root_value, field)
        if fd == mount_fd:
            field = changed_field if changed_authority == "cgroup2_mount" else None
            return changed_stat(mount_value, field)
        raise AssertionError(f"unexpected descriptor: {fd}")

    def mount_id(fd: int) -> int:
        if (
            changed_field == "statx_mount_id"
            and (
                (changed_authority == "delegated_root" and fd == root_fd)
                or (changed_authority == "cgroup2_mount" and fd == mount_fd)
            )
        ):
            return 78
        return 77

    monkeypatch.setattr(api.os, "open", open_directory)
    monkeypatch.setattr(api.os, "fstat", fstat_directory)
    monkeypatch.setattr(api.os, "close", closed.append)
    monkeypatch.setattr(api.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(api.os, "access", lambda *_args: True)
    monkeypatch.setattr(api, "_expected_cgroup2_mount", lambda _path: True)
    monkeypatch.setattr(api._environment, "_statx_mount_id", mount_id)

    if changed_authority is None:
        authority.revalidate()
    else:
        with pytest.raises(
            api.ProviderIsolationBackendUnavailable,
            match="cgroup-v2 .* identity changed",
        ):
            authority.revalidate()

    expected_flags = (
        os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    )
    assert opened == [
        (cgroup2_mount, expected_flags),
        (delegated_root, expected_flags),
    ]
    assert closed == [root_fd, mount_fd]


@pytest.mark.parametrize("cleanup_fails", (False, True))
def test_create_slot_propagates_unproven_failure_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cleanup_fails: bool,
) -> None:
    api = _backend_api()
    authority = api.CgroupV2ContainmentRoot(
        path=tmp_path,
        device=1,
        inode=2,
        uid=1000,
        gid=1000,
        mode=0o700,
        statx_mount_id=3,
        mount_device=1,
        mount_inode=1,
        mount_uid=0,
        mount_gid=0,
        mount_mode=0o555,
        mount_statx_mount_id=3,
        identity_digest="sha256:" + ("a" * 64),
    )
    monkeypatch.setattr(
        api.CgroupV2ContainmentRoot,
        "revalidate",
        lambda _self: None,
    )

    def reject_slot(
        _self: object,
        _name: str,
        *,
        expected_digest: str | None = None,
    ) -> object:
        assert expected_digest is None
        raise api.ProviderIsolationStateError("injected slot load failure")

    monkeypatch.setattr(
        api.CgroupV2ContainmentRoot,
        "load_slot",
        reject_slot,
    )
    real_rmdir = api.os.rmdir
    if cleanup_fails:
        monkeypatch.setattr(
            api.os,
            "rmdir",
            lambda _path: (_ for _ in ()).throw(
                OSError("injected slot cleanup failure")
            ),
        )

    slot_path = tmp_path / (
        "provider-isolation-"
        + sha256(b"pytest-create-slot-cleanup").hexdigest()[:32]
    )
    try:
        if cleanup_fails:
            with pytest.raises(
                api.ProviderIsolationBackendUnavailable,
                match="containment slot cleanup could not be proven",
            ) as failure:
                authority.create_slot("pytest-create-slot-cleanup")
            assert isinstance(failure.value.__cause__, OSError)
            assert slot_path.exists()
        else:
            with pytest.raises(
                api.ProviderIsolationStateError,
                match="injected slot load failure",
            ):
                authority.create_slot("pytest-create-slot-cleanup")
            assert not slot_path.exists()
    finally:
        if slot_path.exists():
            real_rmdir(slot_path)


def test_execute_rejects_nonempty_allocated_containment_before_fork(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from orchestrator.providers.isolation_network_preflight import (
        PinnedProviderIsolationNetworkAuthority,
    )

    backend_api = _backend_api()
    api = _bubblewrap_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=False,
    )
    invocation = backend_api.pin_provider_invocation_authorities(
        snapshot=snapshot,
        candidate=admission,
        runtime=runtime,
        request=request,
    )
    events: list[object] = []
    slot_path = tmp_path / "allocated-nonempty-containment"
    slot_path.mkdir(mode=0o700)

    class PinnedBackend:
        def revalidate(self) -> None:
            events.append("backend_revalidate")

    class Slot:
        path = slot_path

        def revalidate(self) -> None:
            events.append("slot_revalidate")

        @property
        def populated(self) -> bool:
            events.append("slot_populated")
            return True

        def kill(self) -> None:
            events.append("slot_kill")

        def wait_empty(self, *, timeout_seconds: float) -> None:
            events.append(("slot_wait_empty", timeout_seconds))

        def remove(self) -> None:
            events.append("slot_remove")
            slot_path.rmdir()

    network_authority = object.__new__(
        PinnedProviderIsolationNetworkAuthority
    )
    monkeypatch.setattr(api.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        api,
        "_validate_cgroup_launch_authorities",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        api.os,
        "fork",
        lambda: pytest.fail("nonempty containment must reject before fork"),
    )

    try:
        with pytest.raises(
            backend_api.ProviderIsolationInvalidPlan,
            match="containment slot must be empty before launch",
        ):
            api.execute_bubblewrap_invocation(
                invocation_authorities=invocation,
                pinned_backend=PinnedBackend(),
                credentials={},
                declared_credential_names=(),
                release_gate=object(),
                containment_slot=Slot(),
                network_authority=network_authority,
            )
    finally:
        invocation.close()
        runtime.close()
        admission.close()
        snapshot.close()

    assert events == [
        "backend_revalidate",
        "slot_revalidate",
        "slot_populated",
        "slot_kill",
        ("slot_wait_empty", 5.0),
        "slot_remove",
    ]
    assert not slot_path.exists()


@pytest.mark.parametrize(
    ("post_readiness_membership", "expected_error"),
    (
        ("missing_provider", "pinned provider child escaped containment"),
        ("missing_outer", "pinned outer child escaped containment"),
        ("extra_member", "provider containment membership is not exact"),
    ),
)
def test_execute_rejects_nonexact_membership_after_readiness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    post_readiness_membership: str,
    expected_error: str,
) -> None:
    from orchestrator.providers.isolation_network_preflight import (
        PinnedProviderIsolationNetworkAuthority,
        ProviderIsolationNetworkPreflight,
    )

    backend_api = _backend_api()
    api = _bubblewrap_api()
    snapshot, admission, runtime, request = _make_typed_invocation_components(
        tmp_path,
        workflow=False,
    )
    invocation = backend_api.pin_provider_invocation_authorities(
        snapshot=snapshot,
        candidate=admission,
        runtime=runtime,
        request=request,
    )
    events: list[object] = []
    backend_fd = os.open(os.devnull, os.O_RDONLY | os.O_CLOEXEC)
    backend_identity = type(
        "BackendIdentity",
        (),
        {"digest": "sha256:" + ("5" * 64)},
    )()

    class PinnedBackend:
        executable_fd = backend_fd
        identity = backend_identity

        def revalidate(self):
            events.append("backend_revalidate")
            return self.identity

    capability = ProviderIsolationNetworkPreflight(
        schema_version="provider_isolation_network_preflight.v1",
        endpoint_set_digest="sha256:" + ("6" * 64),
        canonical_json=b"{}",
        digest="sha256:" + ("7" * 64),
    )
    network_authority = object.__new__(
        PinnedProviderIsolationNetworkAuthority
    )
    object.__setattr__(network_authority, "_capability", capability)
    monkeypatch.setattr(
        PinnedProviderIsolationNetworkAuthority,
        "revalidate",
        lambda _self: capability,
    )
    slot_path = tmp_path / "escaped-provider-containment"
    slot_path.mkdir(mode=0o700)
    outer_pid = 4242
    provider_pid = 4343

    class Slot:
        identity_digest = "sha256:" + ("8" * 64)
        path = slot_path
        member_reads = 0

        def revalidate(self) -> None:
            events.append("slot_revalidate")

        @property
        def populated(self) -> bool:
            return False

        def add_pid(self, pid: int) -> None:
            events.append(("add", pid))

        def members(self) -> tuple[int, ...]:
            self.member_reads += 1
            events.append(("members", self.member_reads))
            if self.member_reads == 1:
                return (outer_pid,)
            return {
                "missing_provider": (outer_pid,),
                "missing_outer": (provider_pid,),
                "extra_member": tuple(
                    sorted((outer_pid, provider_pid, 4444))
                ),
            }[post_readiness_membership]

        def kill(self) -> None:
            events.append("slot_kill")

        def wait_empty(self, *, timeout_seconds: float) -> None:
            events.append(("slot_wait_empty", timeout_seconds))

        def remove(self) -> None:
            events.append("slot_remove")
            slot_path.rmdir()

    class ReleaseGate:
        containment_identity = Slot.identity_digest
        events = ("launch_intent",)
        release_consumed = False
        release_permit = None

    monkeypatch.setattr(api.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(api.os, "getegid", lambda: 1000)
    monkeypatch.setattr(api.os, "getgroups", lambda: [1000])
    monkeypatch.setattr(
        api,
        "_validate_cgroup_launch_authorities",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(api.os, "fork", lambda: outer_pid)
    monkeypatch.setattr(
        api,
        "_wait_for_bwrap_child_pid",
        lambda *_args, **_kwargs: provider_pid,
    )
    monkeypatch.setattr(
        api,
        "_pin_rootless_child",
        lambda *_args, **_kwargs: (-1, -1, 12345),
    )
    monkeypatch.setattr(
        api,
        "_wait_for_boundary_ready",
        lambda *_args, **_kwargs: events.append("boundary_ready"),
    )
    monkeypatch.setattr(
        api,
        "_write_all_fd",
        lambda _fd, value: events.append(("gate_release", bytes(value))),
    )
    monkeypatch.setattr(api.os, "kill", lambda _pid, _signal: None)
    monkeypatch.setattr(
        api.os,
        "waitpid",
        lambda pid, _flags: (pid, signal.SIGKILL),
    )

    try:
        with pytest.raises(
            api.ProviderIsolationLaunchError,
            match=expected_error,
        ):
            api.execute_bubblewrap_invocation(
                invocation_authorities=invocation,
                pinned_backend=PinnedBackend(),
                credentials={},
                declared_credential_names=(),
                release_gate=ReleaseGate(),
                containment_slot=Slot(),
                network_authority=network_authority,
            )
    finally:
        os.close(backend_fd)
        invocation.close()
        runtime.close()
        admission.close()
        snapshot.close()

    assert events.index(("members", 1)) < events.index("boundary_ready")
    assert events.index("boundary_ready") < events.index(("members", 2))
    assert events[-3:] == [
        "slot_kill",
        ("slot_wait_empty", 5.0),
        "slot_remove",
    ]
    assert not slot_path.exists()


def test_backend_preflight_containment_probe_exercises_full_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _backend_api()
    events: list[object] = []
    child_pid = 4242
    slot_path = tmp_path / "provider-isolation-probe"
    identity = "sha256:" + ("a" * 64)

    class RecordingSlot:
        name = "provider-isolation-" + ("b" * 32)
        identity_digest = identity
        path = slot_path

        @property
        def populated(self) -> bool:
            events.append("initial_empty")
            return False

        def add_pid(self, pid: int) -> None:
            events.append(("member", pid))

        def members(self) -> tuple[int, ...]:
            events.append("members")
            return (child_pid,)

        def kill(self) -> None:
            events.append("kill")

        def wait_empty(self, *, timeout_seconds: float) -> None:
            events.append(("empty", timeout_seconds))

        def remove(self) -> None:
            events.append("remove")
            slot_path.rmdir()

    slot = RecordingSlot()

    class RecordingRoot:
        def create_slot(self, label: str) -> RecordingSlot:
            events.append(("create", label))
            slot_path.mkdir(mode=0o700)
            return slot

        def load_slot(
            self,
            name: str,
            *,
            expected_digest: str,
        ) -> RecordingSlot:
            events.append(("reload", name, expected_digest))
            return slot

    monkeypatch.setattr(api.os, "fork", lambda: child_pid)
    monkeypatch.setattr(
        api.os,
        "waitpid",
        lambda pid, flags: (
            events.append(("reap", pid, flags))
            or (pid, signal.SIGKILL)
        ),
    )

    result = api._probe_cgroup_v2_containment(
        RecordingRoot(),
        attempt_label="pytest-preflight-lifecycle",
    )

    assert result == {
        "create": "passed",
        "member": "passed",
        "reload": "passed",
        "kill": "passed",
        "empty": "passed",
        "remove": "passed",
    }
    assert events == [
        ("create", "pytest-preflight-lifecycle"),
        "initial_empty",
        ("member", child_pid),
        "members",
        (
            "reload",
            slot.name,
            identity,
        ),
        "kill",
        ("reap", child_pid, 0),
        ("empty", 5.0),
        "remove",
    ]
    assert not slot_path.exists()


def test_backend_preflight_probe_child_exits_on_gate_read_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _backend_api()
    slot_path = tmp_path / "provider-isolation-probe-child"

    class ChildExit(BaseException):
        pass

    class Slot:
        name = "provider-isolation-" + ("c" * 32)
        identity_digest = "sha256:" + ("d" * 64)
        path = slot_path

        @property
        def populated(self) -> bool:
            return False

        def remove(self) -> None:
            if slot_path.exists():
                slot_path.rmdir()

    slot = Slot()

    class Root:
        def create_slot(self, _label: str) -> Slot:
            slot_path.mkdir(mode=0o700)
            return slot

    exit_codes: list[int] = []
    monkeypatch.setattr(api.os, "fork", lambda: 0)
    monkeypatch.setattr(
        api.os,
        "read",
        lambda _fd, _size: (_ for _ in ()).throw(OSError("gate failed")),
    )
    monkeypatch.setattr(
        api.os,
        "_exit",
        lambda code: (
            exit_codes.append(code),
            (_ for _ in ()).throw(ChildExit()),
        )[1],
    )

    with pytest.raises(ChildExit):
        api._probe_cgroup_v2_containment(
            Root(),
            attempt_label="pytest-preflight-child-failure",
        )
    assert exit_codes == [127]


def test_backend_preflight_remove_noop_fails_closed_without_residue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _backend_api()
    child_pid = 4343
    slot_path = tmp_path / "provider-isolation-remove-noop"

    class Slot:
        name = "provider-isolation-" + ("4" * 32)
        identity_digest = "sha256:" + ("5" * 64)
        path = slot_path

        @property
        def populated(self) -> bool:
            return False

        def add_pid(self, _pid: int) -> None:
            pass

        def members(self) -> tuple[int, ...]:
            return (child_pid,)

        def kill(self) -> None:
            pass

        def wait_empty(self, *, timeout_seconds: float) -> None:
            assert timeout_seconds == 5.0

        def remove(self) -> None:
            pass

    slot = Slot()

    class Root:
        def create_slot(self, _label: str) -> Slot:
            slot_path.mkdir(mode=0o700)
            return slot

        def load_slot(
            self,
            _name: str,
            *,
            expected_digest: str,
        ) -> Slot:
            assert expected_digest == slot.identity_digest
            return slot

    monkeypatch.setattr(api.os, "fork", lambda: child_pid)
    monkeypatch.setattr(
        api.os,
        "waitpid",
        lambda pid, _flags: (pid, signal.SIGKILL),
    )

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match="remains after removal",
    ):
        api._probe_cgroup_v2_containment(
            Root(),
            attempt_label="pytest-preflight-remove-noop",
        )
    assert not slot_path.exists()


@pytest.mark.parametrize(
    "cleanup_failure",
    (None, "kill", "wait_empty", "remove", "absence"),
)
def test_backend_preflight_failure_proves_complete_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cleanup_failure: str | None,
) -> None:
    api = _backend_api()
    child_pid = 4444
    slot_path = tmp_path / "provider-isolation-probe-cleanup"
    events: list[object] = []

    class Slot:
        name = "provider-isolation-" + ("6" * 32)
        identity_digest = "sha256:" + ("7" * 64)
        path = slot_path

        @property
        def populated(self) -> bool:
            return False

        def add_pid(self, _pid: int) -> None:
            raise api.ProviderIsolationBackendUnavailable(
                "injected primary probe failure"
            )

        def kill(self) -> None:
            events.append("kill")
            if cleanup_failure == "kill":
                raise RuntimeError("injected cleanup kill failure")

        def wait_empty(self, *, timeout_seconds: float) -> None:
            events.append(("wait_empty", timeout_seconds))
            if cleanup_failure == "wait_empty":
                raise RuntimeError("injected cleanup empty failure")

        def remove(self) -> None:
            events.append("remove")
            if cleanup_failure == "remove":
                raise RuntimeError("injected cleanup remove failure")
            if cleanup_failure != "absence":
                slot_path.rmdir()

    slot = Slot()

    class Root:
        def create_slot(self, _label: str) -> Slot:
            slot_path.mkdir(mode=0o700)
            return slot

    real_rmdir = api.os.rmdir
    if cleanup_failure == "absence":
        monkeypatch.setattr(
            api.os,
            "rmdir",
            lambda path: (
                (_ for _ in ()).throw(
                    OSError("injected cleanup absence failure")
                )
                if Path(path) == slot_path
                else real_rmdir(path)
            ),
        )
    monkeypatch.setattr(api.os, "fork", lambda: child_pid)
    monkeypatch.setattr(
        api.os,
        "kill",
        lambda pid, requested_signal: events.append(
            ("direct_kill", pid, requested_signal)
        ),
    )
    monkeypatch.setattr(
        api.os,
        "waitpid",
        lambda pid, flags: (
            events.append(("reap", pid, flags))
            or (pid, signal.SIGKILL)
        ),
    )

    try:
        if cleanup_failure is None:
            with pytest.raises(
                api.ProviderIsolationBackendUnavailable,
                match="injected primary probe failure",
            ):
                api._probe_cgroup_v2_containment(
                    Root(),
                    attempt_label="pytest-preflight-cleanup",
                )
            assert not slot_path.exists()
        else:
            with pytest.raises(
                api.ProviderIsolationBackendUnavailable,
                match="containment capability probe cleanup could not be proven",
            ):
                api._probe_cgroup_v2_containment(
                    Root(),
                    attempt_label="pytest-preflight-cleanup",
                )
            if cleanup_failure in {"wait_empty", "remove", "absence"}:
                assert slot_path.exists()
    finally:
        if slot_path.exists():
            real_rmdir(slot_path)

    assert events[:3] == [
        "kill",
        ("direct_kill", child_pid, signal.SIGKILL),
        ("reap", child_pid, 0),
    ]
    assert ("wait_empty", 5.0) in events
    if cleanup_failure != "wait_empty":
        assert "remove" in events


@pytest.mark.parametrize(
    ("failure_point", "expect_remove"),
    (
        ("kill", True),
        ("wait_empty", False),
        ("remove", True),
    ),
)
def test_failed_launch_propagates_containment_teardown_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_point: str,
    expect_remove: bool,
) -> None:
    api = _bubblewrap_api()
    events: list[object] = []
    slot_path = tmp_path / "provider-isolation-teardown"
    slot_path.mkdir(mode=0o700)

    class Slot:
        path = slot_path

        def kill(self) -> None:
            events.append("kill")
            if failure_point == "kill":
                raise RuntimeError("injected kill failure")

        def wait_empty(self, *, timeout_seconds: float) -> None:
            events.append(("wait_empty", timeout_seconds))
            if failure_point == "wait_empty":
                raise RuntimeError("injected empty-proof failure")

        def remove(self) -> None:
            events.append("remove")
            if failure_point == "remove":
                raise RuntimeError("injected removal failure")
            slot_path.rmdir()

    monkeypatch.setattr(
        api.os,
        "kill",
        lambda pid, requested_signal: events.append(
            ("direct_kill", pid, requested_signal)
        ),
    )
    monkeypatch.setattr(
        api.os,
        "waitpid",
        lambda pid, flags: (
            events.append(("reap", pid, flags))
            or (pid, signal.SIGKILL)
        ),
    )
    monkeypatch.setattr(
        api.os,
        "killpg",
        lambda *_args: pytest.fail("process-group kill is not teardown authority"),
    )

    with pytest.raises(
        api.ProviderIsolationLaunchError,
        match="containment teardown could not be proven",
    ):
        api._teardown_bubblewrap_containment(
            containment_slot=Slot(),
            outer_pid=4242,
            outer_reaped=False,
        )

    assert events[:3] == [
        "kill",
        ("direct_kill", 4242, signal.SIGKILL),
        ("reap", 4242, 0),
    ]
    assert ("wait_empty", 5.0) in events
    assert ("remove" in events) is expect_remove
    if failure_point == "wait_empty":
        assert slot_path.exists()


def test_teardown_kills_lingering_slot_after_outer_child_was_reaped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _bubblewrap_api()
    events: list[object] = []
    slot_path = tmp_path / "provider-isolation-reaped-descendants"
    slot_path.mkdir(mode=0o700)

    class Slot:
        path = slot_path

        def kill(self) -> None:
            events.append("kill")

        def wait_empty(self, *, timeout_seconds: float) -> None:
            events.append(("wait_empty", timeout_seconds))

        def remove(self) -> None:
            events.append("remove")
            slot_path.rmdir()

    monkeypatch.setattr(
        api.os,
        "kill",
        lambda *_args: pytest.fail("reaped direct child must not be signaled"),
    )
    monkeypatch.setattr(
        api.os,
        "waitpid",
        lambda *_args: pytest.fail("reaped direct child must not be reaped twice"),
    )

    api._teardown_bubblewrap_containment(
        containment_slot=Slot(),
        outer_pid=4242,
        outer_reaped=True,
    )

    assert events == ["kill", ("wait_empty", 5.0), "remove"]
    assert not slot_path.exists()


def test_drain_records_reap_before_later_timeout_and_teardown_avoids_pid_reuse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _bubblewrap_api()
    pid = 4242
    reads: list[int] = []
    writes: list[int] = []
    for _name in ("stdout", "stderr", "status"):
        read_fd, write_fd = os.pipe()
        reads.append(read_fd)
        writes.append(write_fd)
    wait_state = api._OuterChildWaitState()
    monkeypatch.setattr(api.os, "waitpid", lambda _pid, _flags: (pid, 0))
    monkeypatch.setattr(
        api,
        "_remaining",
        lambda _deadline: (_ for _ in ()).throw(
            TimeoutError("injected post-reap timeout")
        ),
    )

    try:
        with pytest.raises(TimeoutError, match="post-reap timeout"):
            api._drain_and_wait(
                pid=pid,
                stdout_fd=reads[0],
                stderr_fd=reads[1],
                status_fd=reads[2],
                deadline=1.0,
                wait_state=wait_state,
            )
    finally:
        for fd in writes:
            os.close(fd)

    assert wait_state.reaped is True
    slot_path = tmp_path / "provider-isolation-post-reap-timeout"
    slot_path.mkdir(mode=0o700)
    events: list[object] = []

    class Slot:
        path = slot_path

        def kill(self) -> None:
            events.append("kill")

        def wait_empty(self, *, timeout_seconds: float) -> None:
            events.append(("wait_empty", timeout_seconds))

        def remove(self) -> None:
            events.append("remove")
            slot_path.rmdir()

    monkeypatch.setattr(
        api.os,
        "kill",
        lambda *_args: pytest.fail("reaped numeric PID must not be signaled"),
    )
    monkeypatch.setattr(
        api.os,
        "waitpid",
        lambda *_args: pytest.fail("reaped child must not be waited twice"),
    )

    api._teardown_bubblewrap_containment(
        containment_slot=Slot(),
        outer_pid=pid,
        outer_reaped=wait_state.reaped,
    )

    assert events == ["kill", ("wait_empty", 5.0), "remove"]
    assert not slot_path.exists()


def test_delegated_cgroup_slot_is_reloadable_kill_and_empty_authority() -> None:
    api = _backend_api()
    try:
        root = api.CgroupV2ContainmentRoot.discover()
    except api.ProviderIsolationBackendUnavailable as exc:
        pytest.skip(str(exc))
    slot = root.create_slot("pytest-containment")
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        slot.add_pid(child.pid)
        assert child.pid in slot.members()
        reloaded = root.load_slot(slot.name, expected_digest=slot.identity_digest)
        assert reloaded.identity_digest == slot.identity_digest
        reloaded.kill()
        child.wait(timeout=10)
        reloaded.wait_empty(timeout_seconds=10)
        assert reloaded.populated is False
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        slot.wait_empty(timeout_seconds=10)
        slot.remove()


def test_launch_authorities_cross_bind_backend_gate_and_exact_slot(
    tmp_path: Path,
) -> None:
    backend_api = _backend_api()
    api = _bubblewrap_api()
    pinned = backend_api.get_provider_isolation_backend(
        "bubblewrap.v1"
    ).preflight()
    root = backend_api.CgroupV2ContainmentRoot.discover()
    slot = root.create_slot("pytest-launch-authority-binding")
    gate = backend_api.DurableLaunchReleaseGate.create(
        tmp_path / "launch-authority-binding.json",
        launch_token="sha256:" + ("e" * 64),
        containment_identity=slot.identity_digest,
    )
    gate.record_intent()
    try:
        api._validate_cgroup_launch_authorities(
            pinned_backend=pinned,
            release_gate=gate,
            containment_slot=slot,
        )
        original_identity = pinned.identity
        pinned.identity = replace(
            original_identity,
            containment_root_identity="sha256:" + ("f" * 64),
        )
        with pytest.raises(
            backend_api.ProviderIsolationInvalidPlan,
            match="containment root",
        ):
            api._validate_cgroup_launch_authorities(
                pinned_backend=pinned,
                release_gate=gate,
                containment_slot=slot,
            )
        pinned.identity = original_identity
        with pytest.raises(
            backend_api.ProviderIsolationInvalidPlan,
            match="exact types",
        ):
            api._validate_cgroup_launch_authorities(
                pinned_backend=object(),
                release_gate=gate,
                containment_slot=slot,
            )
    finally:
        pinned.close()
        if not slot.populated:
            slot.remove()


def _write_i0_probe_config(
    path: Path,
    *,
    forbidden_paths: list[Path],
    relative_forbidden: str,
    directory_authorities: list[Path],
    prior_raw_bundle: Path,
    tcp_port: int,
    abstract_name: bytes,
    expected_environment: dict[str, str],
    expected_cmdline: tuple[str, ...],
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "provider_isolation_i0_probe_config.v1",
                "forbidden_paths": [
                    os.fspath(value) for value in forbidden_paths
                ],
                "relative_forbidden": relative_forbidden,
                "directory_authorities": [
                    os.fspath(value) for value in directory_authorities
                ],
                "prior_raw_bundle": os.fspath(prior_raw_bundle),
                "tcp_port": tcp_port,
                "abstract_name_hex": abstract_name.hex(),
                "expected_environment": expected_environment,
                "expected_cmdline": list(expected_cmdline),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _assert_i0_denial_evidence(
    record: dict[str, object],
    *,
    candidate: Path,
    forbidden_paths: list[Path],
    directory_authorities: list[Path],
    prior_raw_bundle: Path,
    expected_environment: dict[str, str],
    expected_cmdline: tuple[str, ...],
) -> None:
    forbidden_text = [os.fspath(path) for path in forbidden_paths]
    assert record["capability_verdict"] == "passed"
    assert record["expected_environment"] == expected_environment
    assert record["expected_cmdline"] == list(expected_cmdline)
    assert record["environment_names"] == sorted(expected_environment)
    assert record["fds"] == [0, 1, 2]
    assert record["pids"] == [1]
    assert record["prior_raw_bundle_result"] != "READABLE"
    assert set(record["denied_reads"]) == set(forbidden_text)
    assert all(
        value != "READABLE"
        for value in record["denied_reads"].values()
    )
    assert record["escape_result"] != "READABLE"
    assert record["relative_escape_result"] != "READABLE"

    openat = record["openat_escape_attempts"]
    assert isinstance(openat, dict)
    assert set(openat) == {
        os.fspath(path) for path in directory_authorities
    }
    for authority, observation in openat.items():
        assert authority in {
            os.fspath(path) for path in directory_authorities
        }
        assert isinstance(observation, dict)
        assert observation["parent_open"] == "OPENED"
        assert set(observation["forbidden_results"]) == set(forbidden_text)
        assert all(
            value != "READABLE"
            for value in observation["forbidden_results"].values()
        )

    proc_inventory = record["proc_fd_inventory"]
    assert isinstance(proc_inventory, dict)
    assert set(proc_inventory) == {"1"}
    assert [
        row["fd"] for row in proc_inventory["1"]
    ] == [0, 1, 2]
    for row in proc_inventory["1"]:
        assert not any(
            forbidden in row["target"]
            for forbidden in forbidden_text
        )

    disclosure = record["process_disclosure"]
    assert disclosure["pidfd_getfd"]
    assert set(disclosure["pidfd_getfd"]) == {
        f"1:{fd}" for fd in (0, 1, 2)
    }
    assert disclosure["ptrace_attach"]
    assert all(
        not value.startswith("ALLOWED")
        for value in disclosure["ptrace_attach"].values()
    )
    proc_mem = disclosure["proc_mem"]
    assert isinstance(proc_mem, dict)
    assert proc_mem["target_pid"] == 1
    assert proc_mem["address_class"] == "provider_owned_marker"
    if proc_mem["status"] == "READABLE":
        assert proc_mem["marker_match"] is True
        assert proc_mem["bytes_read"] > 0
    else:
        assert proc_mem["marker_match"] is False
        assert proc_mem["bytes_read"] == 0
    assert disclosure["cwd"] == os.fspath(candidate)
    assert disclosure["root"] == "/"
    assert disclosure["environ"] == expected_environment
    assert disclosure["environ_names"] == sorted(expected_environment)
    assert disclosure["environ_forbidden_hits"] == []
    assert disclosure["cmdline_forbidden_hits"] == []
    assert disclosure["cmdline"] == list(expected_cmdline)

    terminal = record["terminal_injection"]
    assert set(terminal) == {"fd:0", "fd:1", "fd:2", "/dev/tty"}
    assert all(
        set(operation) == {"tiocsti", "tiocsctty"}
        for operation in terminal.values()
    )
    assert all(
        result != "ALLOWED"
        for operation in terminal.values()
        for result in operation.values()
    )
    assert os.fspath(prior_raw_bundle) in forbidden_text


def test_probe_fixture_reads_only_its_valid_provider_owned_memory_marker() -> None:
    fixture = runpy.run_path(
        "tests/fixtures/provider_isolation/probe_provider.py",
        run_name="provider_isolation_probe_fixture",
    )
    probe_self_memory = fixture["_probe_self_memory"]

    observation = probe_self_memory(os.getpid())

    assert observation == {
        "address_class": "provider_owned_marker",
        "bytes_read": 33,
        "marker_match": True,
        "status": "READABLE",
        "target_pid": os.getpid(),
    }


def _run_probe_ptrace_with_fake_kernel(
    monkeypatch: pytest.MonkeyPatch,
    *,
    detach_errno: int | None = None,
) -> tuple[dict[str, str], list[tuple[str, int]]]:
    fixture = runpy.run_path(
        "tests/fixtures/provider_isolation/probe_provider.py",
        run_name="provider_isolation_probe_fixture",
    )
    events: list[tuple[str, int]] = []
    pid = 47

    class FakeLibc:
        def ptrace(
            self,
            operation: object,
            target_pid: object,
            _address: object,
            _data: object,
        ) -> int:
            opcode = operation.value
            target = target_pid.value
            if opcode == fixture["_PTRACE_ATTACH"]:
                events.append(("attach", target))
                return 0
            assert opcode == fixture["_PTRACE_DETACH"]
            events.append(("detach", target))
            if detach_errno is not None:
                ctypes.set_errno(detach_errno)
                return -1
            return 0

    def waitpid(target_pid: int, options: int) -> tuple[int, int]:
        assert options == 0
        events.append(("waitpid", target_pid))
        return target_pid, (signal.SIGSTOP << 8) | 0x7F

    monkeypatch.setattr(
        fixture["ctypes"],
        "CDLL",
        lambda *_args, **_kwargs: FakeLibc(),
    )
    monkeypatch.setattr(fixture["os"], "waitpid", waitpid)
    observation = fixture["_probe_ptrace"]([pid])
    return observation, events


def test_probe_ptrace_waits_for_stop_before_verified_detach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation, events = _run_probe_ptrace_with_fake_kernel(monkeypatch)

    assert observation == {"47": "ALLOWED"}
    assert events == [
        ("attach", 47),
        ("waitpid", 47),
        ("detach", 47),
    ]


def test_probe_ptrace_records_detach_failure_as_disclosure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation, events = _run_probe_ptrace_with_fake_kernel(
        monkeypatch,
        detach_errno=errno.EIO,
    )

    assert observation == {"47": "ALLOWED_DETACH_EIO"}
    assert events == [
        ("attach", 47),
        ("waitpid", 47),
        ("detach", 47),
    ]


def _passing_i0_probe_record() -> dict[str, object]:
    expected_environment = {
        "LANG": "C",
        "PATH": "/opt/provider/bin",
    }
    expected_cmdline = [
        "/opt/provider/bin/python",
        "-I",
        "/candidate/probe.py",
    ]
    return {
        "cwd": "/candidate",
        "denied_reads": {"/forbidden": "ENOENT"},
        "escape_result": "ENOENT",
        "expected_cmdline": expected_cmdline,
        "expected_environment": expected_environment,
        "fds": [0, 1, 2],
        "openat_escape_attempts": {
            "/candidate": {
                "forbidden_results": {"/forbidden": "ENOENT"},
            }
        },
        "pids": [1],
        "prior_raw_bundle_result": "ENOENT",
        "proc_fd_inventory": {
            "1": [{"fd": descriptor} for descriptor in (0, 1, 2)]
        },
        "process_disclosure": {
            "cmdline": list(expected_cmdline),
            "cmdline_forbidden_hits": [],
            "cwd": "/candidate",
            "environ": dict(expected_environment),
            "environ_names": sorted(expected_environment),
            "environ_forbidden_hits": [],
            "pidfd_getfd": {
                f"1:{descriptor}": "ALLOWED"
                for descriptor in (0, 1, 2)
            },
            "proc_mem": {
                "address_class": "provider_owned_marker",
                "bytes_read": 33,
                "marker_match": True,
                "status": "READABLE",
                "target_pid": 1,
            },
            "ptrace_attach": {"1": "EPERM"},
            "root": "/",
        },
        "relative_escape_result": "ENOENT",
        "terminal_injection": {
            target: {"tiocsti": "ENOTTY", "tiocsctty": "EPERM"}
            for target in ("fd:0", "fd:1", "fd:2", "/dev/tty")
        },
    }


@pytest.mark.parametrize(
    "tamper",
    (
        "denied_read",
        "foreign_fd",
        "ptrace_cleanup",
        "terminal_injection",
        "self_memory_mismatch",
    ),
)
def test_probe_fixture_verdict_fails_on_any_disclosed_authority(
    tamper: str,
) -> None:
    fixture = runpy.run_path(
        "tests/fixtures/provider_isolation/probe_provider.py",
        run_name="provider_isolation_probe_fixture",
    )
    verdict = fixture["_capability_verdict"]
    record = _passing_i0_probe_record()
    assert verdict(record) == "passed"

    if tamper == "denied_read":
        record["denied_reads"]["/forbidden"] = "READABLE"
    elif tamper == "foreign_fd":
        record["fds"].append(9)
    elif tamper == "ptrace_cleanup":
        record["process_disclosure"]["ptrace_attach"]["1"] = (
            "ALLOWED_DETACH_EIO"
        )
    elif tamper == "terminal_injection":
        record["terminal_injection"]["/dev/tty"]["tiocsti"] = "ALLOWED"
    else:
        record["process_disclosure"]["proc_mem"]["marker_match"] = False

    assert verdict(record) == "failed"


@pytest.mark.parametrize(
    ("surface", "direction"),
    (
        ("environment", "observed_extra"),
        ("environment", "expected_extra"),
        ("cmdline", "observed_extra"),
        ("cmdline", "expected_extra"),
    ),
)
def test_probe_fixture_verdict_requires_exact_expected_environment_and_cmdline(
    surface: str,
    direction: str,
) -> None:
    fixture = runpy.run_path(
        "tests/fixtures/provider_isolation/probe_provider.py",
        run_name="provider_isolation_probe_fixture",
    )
    verdict = fixture["_capability_verdict"]
    record = _passing_i0_probe_record()
    disclosure = record["process_disclosure"]

    if surface == "environment":
        target = (
            disclosure["environ"]
            if direction == "observed_extra"
            else record["expected_environment"]
        )
        target["UNRELATED_AMBIENT"] = "benign"
        if direction == "observed_extra":
            disclosure["environ_names"] = sorted(target)
    else:
        target = (
            disclosure["cmdline"]
            if direction == "observed_extra"
            else record["expected_cmdline"]
        )
        target.append("--non-forbidden-ambient-argument")

    assert disclosure["environ_forbidden_hits"] == []
    assert disclosure["cmdline_forbidden_hits"] == []
    assert verdict(record) == "failed"


def _valid_i0_probe_config_document() -> dict[str, object]:
    return {
        "schema_version": "provider_isolation_i0_probe_config.v1",
        "forbidden_paths": ["/forbidden/sentinel"],
        "relative_forbidden": "../forbidden/sentinel",
        "directory_authorities": ["/candidate"],
        "prior_raw_bundle": "/forbidden/sentinel",
        "tcp_port": 12345,
        "abstract_name_hex": b"probe-name".hex(),
        "expected_environment": {
            "LANG": "C",
            "PATH": "/opt/provider/bin",
        },
        "expected_cmdline": [
            "/opt/provider/bin/python",
            "-I",
            "/candidate/probe.py",
        ],
    }


def test_probe_config_accepts_exact_expected_environment_and_cmdline(
    tmp_path: Path,
) -> None:
    fixture = runpy.run_path(
        "tests/fixtures/provider_isolation/probe_provider.py",
        run_name="provider_isolation_probe_fixture",
    )
    document = _valid_i0_probe_config_document()
    path = tmp_path / "probe-config.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    loaded = fixture["_load_probe_config"](os.fspath(path))

    assert loaded == document


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("expected_environment", []),
        ("expected_environment", {"LANG": 1}),
        ("expected_environment", {"": "C"}),
        ("expected_cmdline", {}),
        ("expected_cmdline", []),
        ("expected_cmdline", ["/opt/provider/bin/python", 1]),
        ("expected_cmdline", ["relative-python"]),
    ),
)
def test_probe_config_rejects_malformed_expected_disclosure(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    fixture = runpy.run_path(
        "tests/fixtures/provider_isolation/probe_provider.py",
        run_name="provider_isolation_probe_fixture",
    )
    document = _valid_i0_probe_config_document()
    document[field] = value
    path = tmp_path / "probe-config.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RuntimeError, match=field):
        fixture["_load_probe_config"](os.fspath(path))


def _certified_check_exit_mapping(
    *,
    caller_kind: str,
    caller_attempt_id: str,
    command_identity: str,
    exit_code: int,
) -> dict[str, object]:
    return {
        "schema_version": "certified_check_exit.v1",
        "caller_kind": caller_kind,
        "caller_attempt_id": caller_attempt_id,
        "command_identity": command_identity,
        "exit_code": exit_code,
        "outcome": "passed" if exit_code == 0 else "failed",
    }


def test_controller_exit_mapping_follows_failed_child_disclosure_verdict() -> None:
    fixture = runpy.run_path(
        "tests/fixtures/provider_isolation/probe_provider.py",
        run_name="provider_isolation_probe_fixture",
    )
    record = _passing_i0_probe_record()
    record["process_disclosure"]["environ"]["UNRELATED_AMBIENT"] = "benign"
    record["process_disclosure"]["environ_names"].append("UNRELATED_AMBIENT")
    child_verdict = fixture["_capability_verdict"](record)
    child_exit_code = 0 if child_verdict == "passed" else 98
    mapping = globals().get("_certified_check_exit_mapping")

    assert child_verdict == "failed"
    assert child_exit_code == 98
    assert callable(mapping), "certified-check exit mapper is missing"
    assert mapping(
        caller_kind="certified_check",
        caller_attempt_id="certified-check-0001",
        command_identity="sha256:" + ("7" * 64),
        exit_code=child_exit_code,
    ) == {
        "schema_version": "certified_check_exit.v1",
        "caller_kind": "certified_check",
        "caller_attempt_id": "certified-check-0001",
        "command_identity": "sha256:" + ("7" * 64),
        "exit_code": 98,
        "outcome": "failed",
    }


def _register_i0_closable(cleanup: ExitStack, resource: object) -> object:
    close = getattr(resource, "close", None)
    if not callable(close):
        raise TypeError("I0 live resource is not closable")
    cleanup.callback(close)
    return resource


def _close_i0_fd(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError as exc:
        if exc.errno != errno.EBADF:
            raise


def _register_i0_fd(cleanup: ExitStack, descriptor: int) -> int:
    if (
        isinstance(descriptor, bool)
        or not isinstance(descriptor, int)
        or descriptor < 0
    ):
        raise ValueError("I0 live descriptor is invalid")
    cleanup.callback(_close_i0_fd, descriptor)
    return descriptor


def _register_i0_fds(
    cleanup: ExitStack,
    descriptors: tuple[int, ...],
) -> tuple[int, ...]:
    if (
        not isinstance(descriptors, tuple)
        or not descriptors
        or any(
            isinstance(descriptor, bool)
            or not isinstance(descriptor, int)
            or descriptor < 0
            for descriptor in descriptors
        )
    ):
        raise ValueError("I0 live descriptor set is invalid")
    for descriptor in descriptors:
        _register_i0_fd(cleanup, descriptor)
    return descriptors


def _cleanup_i0_empty_slot(slot: object) -> None:
    path = getattr(slot, "path", None)
    if not isinstance(path, Path):
        raise TypeError("I0 containment slot path is invalid")
    if not path.exists():
        return
    if getattr(slot, "populated", True):
        raise AssertionError("I0 setup cleanup found a populated slot")
    remove = getattr(slot, "remove", None)
    if not callable(remove):
        raise TypeError("I0 containment slot is not removable")
    remove()
    if path.exists():
        raise AssertionError("I0 setup cleanup did not remove the empty slot")


def _register_i0_empty_slot(cleanup: ExitStack, slot: object) -> object:
    cleanup.callback(_cleanup_i0_empty_slot, slot)
    return slot


def test_i0_setup_failure_after_slot_creation_closes_authorities_and_slot(
    tmp_path: Path,
) -> None:
    close_events: list[str] = []

    class Closable:
        def __init__(self, label: str):
            self.label = label

        def close(self) -> None:
            close_events.append(self.label)

    class EmptySlot:
        def __init__(self, path: Path):
            self.path = path

        @property
        def populated(self) -> bool:
            return False

        def remove(self) -> None:
            self.path.rmdir()

    slot_path = tmp_path / "provider-isolation-setup-failure"
    slot_path.mkdir()
    cleanup = ExitStack()
    with pytest.raises(RuntimeError, match="injected after slot"):
        try:
            for label in ("snapshot", "admission", "runtime", "backend"):
                _register_i0_closable(cleanup, Closable(label))
            _register_i0_empty_slot(cleanup, EmptySlot(slot_path))
            raise RuntimeError("injected after slot")
        finally:
            cleanup.close()

    assert set(close_events) == {
        "snapshot",
        "admission",
        "runtime",
        "backend",
    }
    assert not slot_path.exists()


def test_i0_cleanup_tolerates_slot_already_removed_by_execution(
    tmp_path: Path,
) -> None:
    class RemovedSlot:
        path = tmp_path / "provider-isolation-already-removed"

        @property
        def populated(self) -> bool:
            raise AssertionError("removed slot must not be revalidated")

        def remove(self) -> None:
            raise AssertionError("removed slot must not be removed twice")

    cleanup = ExitStack()
    _register_i0_empty_slot(cleanup, RemovedSlot())

    cleanup.close()
    cleanup.close()


@pytest.mark.parametrize("failpoint", ("raw_fd", "pty"))
def test_i0_setup_failure_closes_socket_raw_fd_pty_and_empty_slot(
    tmp_path: Path,
    failpoint: str,
) -> None:
    class EmptySlot:
        def __init__(self, path: Path):
            self.path = path

        @property
        def populated(self) -> bool:
            return False

        def remove(self) -> None:
            self.path.rmdir()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_fd = -1
    pty_fds: tuple[int, int] = ()
    slot_path = tmp_path / f"provider-isolation-{failpoint}-failure"
    slot_path.mkdir()
    cleanup = ExitStack()
    with pytest.raises(RuntimeError, match=f"injected after {failpoint}"):
        try:
            _register_i0_closable(cleanup, listener)
            _register_i0_empty_slot(cleanup, EmptySlot(slot_path))
            raw_fd = _register_i0_fd(
                cleanup,
                os.open(os.devnull, os.O_RDONLY | os.O_CLOEXEC),
            )
            if failpoint == "raw_fd":
                raise RuntimeError("injected after raw_fd")
            pty_fds = _register_i0_fds(cleanup, os.openpty())
            raise RuntimeError("injected after pty")
        finally:
            cleanup.close()

    assert listener.fileno() == -1
    assert not slot_path.exists()
    for descriptor in (raw_fd, *pty_fds):
        with pytest.raises(OSError) as exc_info:
            os.fstat(descriptor)
        assert exc_info.value.errno == errno.EBADF


def test_real_rootless_projection_denies_external_and_publishes_only_scratch(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    run_root_value = os.environ.get("ORCHESTRATOR_I0_ENVIRONMENT_RUN_ROOT")
    digest = os.environ.get("ORCHESTRATOR_I0_ENVIRONMENT_DIGEST")
    if not run_root_value or not digest:
        pytest.skip("explicit sealed I0 environment identity is not configured")
    environment_source = os.environ.get(
        "ORCHESTRATOR_I0_ENVIRONMENT_SOURCE",
        os.fspath(Path.cwd()),
    )

    from orchestrator.providers.isolation_candidate import (
        admit_provider_candidate,
    )
    from orchestrator.providers.isolation_environment import (
        load_provider_environment_snapshot_for_launch,
    )
    from orchestrator.providers.isolation_network_preflight import (
        capture_provider_isolation_network_inventory,
        pin_provider_isolation_network_preflight,
        publish_provider_isolation_network_inventory,
    )
    from orchestrator.providers.isolation_runtime_authority import (
        ProviderIsolationRuntimeAuthority,
    )
    from orchestrator.providers.provider_launch_shim import _fixed_environment

    backend_api = _backend_api()
    bwrap_api = _bubblewrap_api()
    cleanup = ExitStack()
    request.addfinalizer(cleanup.close)
    candidate = tmp_path / "candidate"
    candidate.mkdir(mode=0o700)
    probe = candidate / "probe_provider.py"
    shutil.copyfile(
        Path("tests/fixtures/provider_isolation/probe_provider.py"),
        probe,
    )
    probe.chmod(0o600)
    hidden_roots = {
        label: tmp_path / label.replace("_", "-")
        for label in (
            "workflow",
            "source",
            "extern",
            "controller_state",
            "control",
            "evaluator",
            "peer",
            "parent",
        )
    }
    hidden_sentinels: list[Path] = []
    for label, root in hidden_roots.items():
        root.mkdir(mode=0o700)
        sentinel = root / "sentinel.txt"
        sentinel.write_text(f"forbidden:{label}\n", encoding="utf-8")
        sentinel.chmod(0o600)
        hidden_sentinels.append(sentinel)
    prior_raw_bundle = (
        hidden_roots["controller_state"] / "prior-raw-bundle.json"
    )
    prior_raw_bundle.write_text(
        '{"raw":"prior-provider-output"}\n',
        encoding="utf-8",
    )
    prior_raw_bundle.chmod(0o600)
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)

    snapshot = load_provider_environment_snapshot_for_launch(
        run_root_value,
        expected_digest=digest,
    )
    _register_i0_closable(cleanup, snapshot)
    filesystem_denied_authorities = {
        "workflow": hidden_roots["workflow"],
        "source": hidden_roots["source"],
        "extern": hidden_roots["extern"],
        "controller_state": hidden_roots["controller_state"],
        "provider_environment_source": environment_source,
        "provider_environment_snapshot": snapshot.rootfs_path,
        "scratch": scratch,
        "control": hidden_roots["control"],
        "evaluator": hidden_roots["evaluator"],
        "peer": hidden_roots["peer"],
        "parent": hidden_roots["parent"],
    }
    tcp_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _register_i0_closable(cleanup, tcp_listener)
    tcp_listener.bind(("127.0.0.1", 0))
    tcp_listener.listen()
    abstract_name = (
        b"provider-isolation-i0-"
        + os.getpid().to_bytes(8, "big")
    )
    abstract_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    _register_i0_closable(cleanup, abstract_listener)
    abstract_listener.bind(b"\x00" + abstract_name)
    abstract_listener.listen()
    probe_config = candidate / "probe-config.json"
    forbidden_paths = [
        *hidden_sentinels,
        prior_raw_bundle,
        snapshot.authority_path,
    ]
    directory_authorities = [
        candidate,
        candidate / ".orchestrate",
        candidate / ".orchestrate" / "results",
    ]
    isolation_request = backend_api.WorkflowProviderIsolationRequest(
        candidate_path=os.fspath(candidate),
        target=(
            f"{snapshot.manifest.provider_prefix}/bin/python",
            "-I",
            "-S",
            os.fspath(probe),
            "--probe-config",
            os.fspath(probe_config),
        ),
        environment_digest=digest,
        result_channel="typed_bundle",
        provider_template_identity="sha256:" + ("2" * 64),
        aggregate_scope=("root", "probe"),
        ordinal=1,
        result_logical_path=os.fspath(
            candidate / ".orchestrate" / "results" / "probe.json"
        ),
        result_bundle_max_bytes=4096,
    )
    expected_environment = _fixed_environment(
        {},
        provider_prefix=snapshot.manifest.provider_prefix,
        output_bundle=isolation_request.result_logical_path,
    )
    _write_i0_probe_config(
        probe_config,
        forbidden_paths=forbidden_paths,
        relative_forbidden=os.path.relpath(hidden_sentinels[0], candidate),
        directory_authorities=directory_authorities,
        prior_raw_bundle=prior_raw_bundle,
        tcp_port=tcp_listener.getsockname()[1],
        abstract_name=abstract_name,
        expected_environment=expected_environment,
        expected_cmdline=isolation_request.target,
    )
    admission = admit_provider_candidate(
        candidate,
        denied_authorities=filesystem_denied_authorities,
        provider_prefix=snapshot.manifest.provider_prefix,
    )
    _register_i0_closable(cleanup, admission)
    runtime_authority = ProviderIsolationRuntimeAuthority.create_fresh(candidate)
    _register_i0_closable(cleanup, runtime_authority)
    network_inventory_root = tmp_path / "network-inventory"
    network_inventory_root.mkdir(mode=0o700)
    network_denied_authorities = {
        "candidate": candidate,
        **filesystem_denied_authorities,
    }
    backend = backend_api.get_provider_isolation_backend("bubblewrap.v1")
    pinned = backend.preflight()
    _register_i0_closable(cleanup, pinned)
    network_inventory = capture_provider_isolation_network_inventory()
    network_artifact = publish_provider_isolation_network_inventory(
        network_inventory,
        network_inventory_root / "inventory.json",
        denied_authorities=network_denied_authorities,
    )
    network_authority = pin_provider_isolation_network_preflight(
        reviewed_artifact=network_artifact,
        denied_authorities=network_denied_authorities,
        runtime_endpoints=(),
        timeout_seconds=0.2,
        decision="accept_unlisted_reachability",
    )
    controller_network_namespace = os.stat("/proc/self/ns/net")
    cgroup_root = backend_api.CgroupV2ContainmentRoot.discover()
    slot = cgroup_root.create_slot("pytest-real-i0-projection")
    _register_i0_empty_slot(cleanup, slot)
    gate = backend_api.DurableLaunchReleaseGate.create(
        tmp_path / "launch-release.json",
        launch_token="sha256:" + ("a" * 64),
        containment_identity=slot.identity_digest,
    )
    gate.record_intent()
    invocation_authorities = (
        backend_api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime_authority,
            request=isolation_request,
        )
    )
    _register_i0_closable(cleanup, invocation_authorities)
    inherited_forbidden_file_fd = os.open(
        hidden_sentinels[0],
        os.O_RDONLY | os.O_CLOEXEC,
    )
    _register_i0_fd(cleanup, inherited_forbidden_file_fd)
    inherited_forbidden_directory_fd = os.open(
        hidden_roots["control"],
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
    )
    _register_i0_fd(cleanup, inherited_forbidden_directory_fd)
    controller_tty_fds = os.openpty()
    _register_i0_fds(cleanup, controller_tty_fds)
    os.set_inheritable(inherited_forbidden_file_fd, True)
    os.set_inheritable(inherited_forbidden_directory_fd, True)
    for controller_tty_fd in controller_tty_fds:
        os.set_inheritable(controller_tty_fd, True)
    try:
        result = bwrap_api.execute_bubblewrap_invocation(
            invocation_authorities=invocation_authorities,
            pinned_backend=pinned,
            credentials={},
            declared_credential_names=(),
            release_gate=gate,
            containment_slot=slot,
            network_authority=network_authority,
            timeout_seconds=20,
        )
    finally:
        cleanup.close()

    assert result.returncode == 0, result.stderr
    assert invocation_authorities.scratch_relpath is not None
    scratch_result = (
        candidate
        / ".orchestrate"
        / invocation_authorities.scratch_relpath
        / "probe.json"
    )
    record = json.loads(scratch_result.read_text(encoding="utf-8"))
    assert record["candidate_write"] == "provider-owned\n"
    assert record["cwd"] == os.fspath(candidate)
    assert all(value != "READABLE" for value in record["denied_reads"].values())
    assert set(record["denied_reads"]) == {
        os.fspath(path) for path in forbidden_paths
    }
    assert record["escape_result"] != "READABLE"
    assert record["relative_escape_result"] != "READABLE"
    _assert_i0_denial_evidence(
        record,
        candidate=candidate,
        forbidden_paths=forbidden_paths,
        directory_authorities=directory_authorities,
        prior_raw_bundle=prior_raw_bundle,
        expected_environment=dict(result.plan.environment),
        expected_cmdline=isolation_request.target,
    )
    assert record["pids"] == [1]
    assert record["hostname"] == "orchestrator-provider"
    assert record["process_identity"] == {
        "pid": 1,
        "process_group": 1,
        "session": 1,
    }
    assert record["status"]["NoNewPrivs"] == "1"
    for name in ("CapAmb", "CapBnd", "CapEff", "CapInh", "CapPrm"):
        assert int(record["status"][name], 16) == 0
    assert record["uid_map"] == [0, 0, 1]
    assert record["gid_map"] == [0, 0, 1]
    assert record["setgroups"] == "deny"
    assert set(record["groups"]) <= {0, record["overflow_gid"]}
    assert record["key_syscalls"] == {
        "add_key": "EPERM",
        "keyctl": "EPERM",
        "request_key": "EPERM",
    }
    assert record["nested_user_namespace"] in {"EPERM", "ENOSPC"}
    assert record["tty_result"] != "READABLE"
    assert record["runtime_entries"] == ["results"]
    assert record["network_observations"]["host_loopback_tcp"] == "REACHABLE"
    assert record["network_observations"]["host_abstract_unix"] == "REACHABLE"
    assert record["network_observations"]["cloud_metadata"] != "REACHABLE"
    assert record["network_namespace_identity"] == {
        "device": controller_network_namespace.st_dev,
        "inode": controller_network_namespace.st_ino,
    }
    host_runtime = candidate / ".orchestrate"
    assert host_runtime.is_dir()
    assert scratch_result.is_file()
    assert stat.S_IMODE(host_runtime.stat().st_mode) == 0o700
    scratch_relpath = Path(invocation_authorities.scratch_relpath)
    expected_runtime_entries: set[str] = set()
    parent = Path()
    for component in scratch_relpath.parts:
        parent /= component
        expected_runtime_entries.add(parent.as_posix())
    expected_runtime_entries.add(
        (scratch_relpath / "probe.json").as_posix()
    )
    assert {
        path.relative_to(host_runtime).as_posix()
        for path in host_runtime.rglob("*")
    } == expected_runtime_entries
    for label, sentinel in zip(hidden_roots, hidden_sentinels, strict=True):
        assert sentinel.read_text(encoding="utf-8") == f"forbidden:{label}\n"
    assert gate.release_consumed is True
    assert result.containment_empty is True
    assert result.network_preflight_digest == network_authority.capability.digest
    assert (
        result.plan.network_preflight_digest
        == network_authority.capability.digest
    )
    assert result.host_boundary["uid_map"] == (0, os.geteuid(), 1)
    assert result.host_boundary["gid_map"] == (0, os.getegid(), 1)
    assert result.host_boundary["setgroups"] == "deny"


def test_real_controller_attempt_certified_check_denies_g0_without_bundle(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    run_root_value = os.environ.get("ORCHESTRATOR_I0_ENVIRONMENT_RUN_ROOT")
    digest = os.environ.get("ORCHESTRATOR_I0_ENVIRONMENT_DIGEST")
    if not run_root_value or not digest:
        pytest.skip("explicit sealed I0 environment identity is not configured")
    environment_source = os.environ.get(
        "ORCHESTRATOR_I0_ENVIRONMENT_SOURCE",
        os.fspath(Path.cwd()),
    )

    from orchestrator.providers.isolation_candidate import (
        admit_provider_candidate,
    )
    from orchestrator.providers.isolation_environment import (
        load_provider_environment_snapshot_for_launch,
    )
    from orchestrator.providers.isolation_network_preflight import (
        capture_provider_isolation_network_inventory,
        pin_provider_isolation_network_preflight,
        publish_provider_isolation_network_inventory,
    )
    from orchestrator.providers.isolation_runtime_authority import (
        ProviderIsolationRuntimeAuthority,
    )
    from orchestrator.providers.provider_launch_shim import _fixed_environment

    backend_api = _backend_api()
    bwrap_api = _bubblewrap_api()
    cleanup = ExitStack()
    request.addfinalizer(cleanup.close)
    product_source = tmp_path / "certified-product-source"
    product_source.mkdir(mode=0o700)
    shutil.copyfile(
        Path("tests/fixtures/provider_isolation/probe_provider.py"),
        product_source / "certified_check.py",
    )
    (product_source / "certified_check.py").chmod(0o600)
    candidate = tmp_path / "certified-product-extract"
    shutil.copytree(product_source, candidate)
    candidate.chmod(0o700)
    probe = candidate / "certified_check.py"
    source_only_sentinel = product_source / "source-only.txt"
    source_only_sentinel.write_text(
        "forbidden:actual-product-source\n",
        encoding="utf-8",
    )
    source_only_sentinel.chmod(0o600)

    hidden_roots = {
        label: tmp_path / f"g0-{label.replace('_', '-')}"
        for label in (
            "workflow",
            "source",
            "extern",
            "controller_state",
            "scratch",
            "control",
            "evaluator",
            "peer",
            "parent",
        )
    }
    hidden_sentinels: list[Path] = []
    for label, root in hidden_roots.items():
        root.mkdir(mode=0o700)
        sentinel = root / "sentinel.txt"
        sentinel.write_text(f"forbidden:{label}\n", encoding="utf-8")
        sentinel.chmod(0o600)
        hidden_sentinels.append(sentinel)
    prior_raw_bundle = (
        hidden_roots["controller_state"] / "prior-raw-bundle.json"
    )
    prior_raw_bundle.write_text(
        '{"raw":"prior-certified-check-output"}\n',
        encoding="utf-8",
    )
    prior_raw_bundle.chmod(0o600)

    snapshot = load_provider_environment_snapshot_for_launch(
        run_root_value,
        expected_digest=digest,
    )
    _register_i0_closable(cleanup, snapshot)
    filesystem_denied_authorities = {
        "workflow": hidden_roots["workflow"],
        "source": product_source,
        "extern": hidden_roots["extern"],
        "controller_state": hidden_roots["controller_state"],
        "provider_environment_source": environment_source,
        "provider_environment_snapshot": snapshot.rootfs_path,
        "scratch": hidden_roots["scratch"],
        "control": hidden_roots["control"],
        "evaluator": hidden_roots["evaluator"],
        "peer": hidden_roots["peer"],
        "parent": hidden_roots["parent"],
    }
    tcp_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _register_i0_closable(cleanup, tcp_listener)
    tcp_listener.bind(("127.0.0.1", 0))
    tcp_listener.listen()
    abstract_name = (
        b"provider-isolation-certified-"
        + os.getpid().to_bytes(8, "big")
    )
    abstract_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    _register_i0_closable(cleanup, abstract_listener)
    abstract_listener.bind(b"\x00" + abstract_name)
    abstract_listener.listen()

    forbidden_paths = [
        *hidden_sentinels,
        source_only_sentinel,
        prior_raw_bundle,
        snapshot.authority_path,
    ]
    directory_authorities = [
        candidate,
        candidate / ".orchestrate",
    ]
    probe_config = candidate / "probe-config.json"
    isolation_request = backend_api.ControllerAttemptIsolationRequest(
        candidate_path=os.fspath(candidate),
        target=(
            f"{snapshot.manifest.provider_prefix}/bin/python",
            "-I",
            "-S",
            os.fspath(probe),
            "--probe-config",
            os.fspath(probe_config),
        ),
        environment_digest=digest,
        result_channel="none",
        caller_kind="certified_check",
        caller_attempt_id="certified-check-0001",
        command_identity="sha256:" + ("7" * 64),
        external_sink_identity="sha256:" + ("8" * 64),
    )
    expected_environment = _fixed_environment(
        {},
        provider_prefix=snapshot.manifest.provider_prefix,
    )
    _write_i0_probe_config(
        probe_config,
        forbidden_paths=forbidden_paths,
        relative_forbidden=os.path.relpath(hidden_sentinels[0], candidate),
        directory_authorities=directory_authorities,
        prior_raw_bundle=prior_raw_bundle,
        tcp_port=tcp_listener.getsockname()[1],
        abstract_name=abstract_name,
        expected_environment=expected_environment,
        expected_cmdline=isolation_request.target,
    )
    admission = admit_provider_candidate(
        candidate,
        denied_authorities=filesystem_denied_authorities,
        provider_prefix=snapshot.manifest.provider_prefix,
    )
    _register_i0_closable(cleanup, admission)
    runtime_authority = ProviderIsolationRuntimeAuthority.create_fresh(
        candidate
    )
    _register_i0_closable(cleanup, runtime_authority)

    network_inventory_root = tmp_path / "certified-network-inventory"
    network_inventory_root.mkdir(mode=0o700)
    network_denied_authorities = {
        "candidate": candidate,
        **filesystem_denied_authorities,
    }
    pinned = backend_api.get_provider_isolation_backend(
        "bubblewrap.v1"
    ).preflight()
    _register_i0_closable(cleanup, pinned)
    network_artifact = publish_provider_isolation_network_inventory(
        capture_provider_isolation_network_inventory(),
        network_inventory_root / "inventory.json",
        denied_authorities=network_denied_authorities,
    )
    network_authority = pin_provider_isolation_network_preflight(
        reviewed_artifact=network_artifact,
        denied_authorities=network_denied_authorities,
        runtime_endpoints=(),
        timeout_seconds=0.2,
        decision="accept_unlisted_reachability",
    )
    root = backend_api.CgroupV2ContainmentRoot.discover()
    slot = root.create_slot("pytest-real-certified-check")
    _register_i0_empty_slot(cleanup, slot)
    gate = backend_api.DurableLaunchReleaseGate.create(
        tmp_path / "certified-launch-release.json",
        launch_token="sha256:" + ("6" * 64),
        containment_identity=slot.identity_digest,
    )
    gate.record_intent()
    invocation_authorities = backend_api.pin_provider_invocation_authorities(
        snapshot=snapshot,
        candidate=admission,
        runtime=runtime_authority,
        request=isolation_request,
    )
    _register_i0_closable(cleanup, invocation_authorities)
    inherited_forbidden_file_fd = os.open(
        hidden_sentinels[0],
        os.O_RDONLY | os.O_CLOEXEC,
    )
    _register_i0_fd(cleanup, inherited_forbidden_file_fd)
    inherited_forbidden_directory_fd = os.open(
        hidden_roots["control"],
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
    )
    _register_i0_fd(cleanup, inherited_forbidden_directory_fd)
    controller_tty_fds = os.openpty()
    _register_i0_fds(cleanup, controller_tty_fds)
    os.set_inheritable(inherited_forbidden_file_fd, True)
    os.set_inheritable(inherited_forbidden_directory_fd, True)
    for controller_tty_fd in controller_tty_fds:
        os.set_inheritable(controller_tty_fd, True)
    try:
        result = bwrap_api.execute_bubblewrap_invocation(
            invocation_authorities=invocation_authorities,
            pinned_backend=pinned,
            credentials={},
            declared_credential_names=(),
            release_gate=gate,
            containment_slot=slot,
            network_authority=network_authority,
            timeout_seconds=20,
        )
    finally:
        cleanup.close()

    assert result.returncode == 0, result.stderr
    assert invocation_authorities.scratch_relpath is None
    assert tuple(mount.role for mount in result.plan.mounts) == (
        "sealed_rootfs",
        "candidate",
    )
    assert "ORCHESTRATOR_OUTPUT_BUNDLE" not in dict(
        result.plan.environment
    )
    record = json.loads(result.stdout)
    _assert_i0_denial_evidence(
        record,
        candidate=candidate,
        forbidden_paths=forbidden_paths,
        directory_authorities=directory_authorities,
        prior_raw_bundle=prior_raw_bundle,
        expected_environment=dict(result.plan.environment),
        expected_cmdline=isolation_request.target,
    )
    assert record["runtime_entries"] == []
    assert list((candidate / ".orchestrate").iterdir()) == []
    assert gate.release_consumed is True
    assert result.containment_empty is True
    for label, sentinel in zip(hidden_roots, hidden_sentinels, strict=True):
        assert sentinel.read_text(encoding="utf-8") == f"forbidden:{label}\n"
    assert source_only_sentinel.read_text(encoding="utf-8") == (
        "forbidden:actual-product-source\n"
    )

    caller_exit_mapping = _certified_check_exit_mapping(
        caller_kind=isolation_request.caller_kind,
        caller_attempt_id=isolation_request.caller_attempt_id,
        command_identity=isolation_request.command_identity,
        exit_code=result.returncode,
    )
    assert caller_exit_mapping == {
        "schema_version": "certified_check_exit.v1",
        "caller_kind": "certified_check",
        "caller_attempt_id": "certified-check-0001",
        "command_identity": "sha256:" + ("7" * 64),
        "exit_code": 0,
        "outcome": "passed",
    }


def test_real_timeout_kills_exact_slot_and_proves_quiescence(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    run_root_value = os.environ.get("ORCHESTRATOR_I0_ENVIRONMENT_RUN_ROOT")
    digest = os.environ.get("ORCHESTRATOR_I0_ENVIRONMENT_DIGEST")
    if not run_root_value or not digest:
        pytest.skip("explicit sealed I0 environment identity is not configured")
    environment_source = os.environ.get(
        "ORCHESTRATOR_I0_ENVIRONMENT_SOURCE",
        os.fspath(Path.cwd()),
    )
    from orchestrator.providers.isolation_candidate import (
        admit_provider_candidate,
    )
    from orchestrator.providers.isolation_environment import (
        load_provider_environment_snapshot_for_launch,
    )
    from orchestrator.providers.isolation_network_preflight import (
        capture_provider_isolation_network_inventory,
        pin_provider_isolation_network_preflight,
        publish_provider_isolation_network_inventory,
    )
    from orchestrator.providers.isolation_runtime_authority import (
        ProviderIsolationRuntimeAuthority,
    )

    backend_api = _backend_api()
    bwrap_api = _bubblewrap_api()
    cleanup = ExitStack()
    request.addfinalizer(cleanup.close)
    candidate = tmp_path / "candidate"
    candidate.mkdir(mode=0o700)
    control = tmp_path / "control"
    control.mkdir(mode=0o700)
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    controller_state = tmp_path / "controller-state"
    controller_state.mkdir(mode=0o700)
    snapshot = load_provider_environment_snapshot_for_launch(
        run_root_value,
        expected_digest=digest,
    )
    _register_i0_closable(cleanup, snapshot)
    filesystem_denied_authorities = {
        "workflow": Path.cwd(),
        "source": Path.cwd(),
        "extern": control,
        "controller_state": controller_state,
        "provider_environment_source": environment_source,
        "provider_environment_snapshot": snapshot.rootfs_path,
        "scratch": scratch,
        "control": control,
        "evaluator": control,
        "peer": control,
        "parent": Path.cwd(),
    }
    admission = admit_provider_candidate(
        candidate,
        denied_authorities=filesystem_denied_authorities,
        provider_prefix=snapshot.manifest.provider_prefix,
    )
    _register_i0_closable(cleanup, admission)
    runtime_authority = ProviderIsolationRuntimeAuthority.create_fresh(candidate)
    _register_i0_closable(cleanup, runtime_authority)
    network_inventory_root = tmp_path / "network-inventory"
    network_inventory_root.mkdir(mode=0o700)
    network_denied_authorities = {
        "candidate": candidate,
        **filesystem_denied_authorities,
    }
    pinned = backend_api.get_provider_isolation_backend(
        "bubblewrap.v1"
    ).preflight()
    _register_i0_closable(cleanup, pinned)
    network_artifact = publish_provider_isolation_network_inventory(
        capture_provider_isolation_network_inventory(),
        network_inventory_root / "inventory.json",
        denied_authorities=network_denied_authorities,
    )
    network_authority = pin_provider_isolation_network_preflight(
        reviewed_artifact=network_artifact,
        denied_authorities=network_denied_authorities,
        runtime_endpoints=(),
        timeout_seconds=0.1,
        decision="accept_unlisted_reachability",
    )
    root = backend_api.CgroupV2ContainmentRoot.discover()
    slot = root.create_slot("pytest-real-i0-timeout")
    _register_i0_empty_slot(cleanup, slot)
    gate = backend_api.DurableLaunchReleaseGate.create(
        tmp_path / "launch-release.json",
        launch_token="sha256:" + ("c" * 64),
        containment_identity=slot.identity_digest,
    )
    gate.record_intent()
    isolation_request = backend_api.ControllerAttemptIsolationRequest(
        candidate_path=os.fspath(candidate),
        target=(
            f"{snapshot.manifest.provider_prefix}/bin/python",
            "-I",
                "-S",
                "-c",
                (
                    "import os,time\n"
                    "fds = []\n"
                    "for name in os.listdir('/proc/self/fd'):\n"
                    "    if not name.isdecimal():\n"
                    "        continue\n"
                    "    descriptor = int(name)\n"
                    "    try:\n"
                    "        os.fstat(descriptor)\n"
                    "    except OSError:\n"
                    "        continue\n"
                    "    fds.append(descriptor)\n"
                    "assert sorted(fds) == [0, 1, 2]\n"
                    "time.sleep(60)\n"
                ),
        ),
        environment_digest=digest,
        result_channel="none",
        caller_kind="capability_probe",
        caller_attempt_id="timeout-0001",
        command_identity="sha256:" + ("d" * 64),
        external_sink_identity="sha256:" + ("e" * 64),
    )
    invocation_authorities = (
        backend_api.pin_provider_invocation_authorities(
            snapshot=snapshot,
            candidate=admission,
            runtime=runtime_authority,
            request=isolation_request,
        )
    )
    _register_i0_closable(cleanup, invocation_authorities)
    inherited_forbidden_fd = os.open(
        control,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
    )
    _register_i0_fd(cleanup, inherited_forbidden_fd)
    os.set_inheritable(inherited_forbidden_fd, True)
    try:
        with pytest.raises(
            bwrap_api.ProviderIsolationLaunchError,
            match="invocation failed",
        ):
            bwrap_api.execute_bubblewrap_invocation(
                invocation_authorities=invocation_authorities,
                pinned_backend=pinned,
                credentials={},
                declared_credential_names=(),
                release_gate=gate,
                containment_slot=slot,
                network_authority=network_authority,
                # The total deadline includes strict revalidation of the
                # real sealed snapshot before the provider is released.
                timeout_seconds=15,
            )
    finally:
        cleanup.close()

    assert gate.release_consumed is True
    assert not slot.path.exists()
    assert list((candidate / ".orchestrate").iterdir()) == []
