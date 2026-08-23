"""Frozen OMP executable pin validation contracts (Task 1, F4)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from orchestrator.providers.omp_pin import (
    OMP_BINARY_PIN,
    OmpBinaryPin,
    OmpPinError,
    canonical_pin_json,
    validate_build_observations,
    validate_cpu_target,
    validate_platform,
    validate_version_digest,
)


def _pin(**overrides: object) -> OmpBinaryPin:
    values: dict[str, object] = {
        "platform": "linux",
        "arch": "x86_64",
        "avx2": True,
        "native_target": "//:natives-linux-x64-modern",
        "version": "17.3.4",
        "source_commit": "f" * 40,
        "bun_version": "1.3.14",
        "bun_path": "/opt/tools/bin/bun",
        "bun_sha256": "9fd3" + "0" * 60,
        "bazelisk_version": "1.29.0",
        "bazelisk_path": "/opt/tools/bin/bazelisk",
        "bazelisk_sha256": "5a40" + "0" * 60,
        "bazel_version": "9.2.0",
        "bazel_path": "/opt/cache/bin/bazel",
        "bazel_sha256": "7668" + "0" * 60,
        "git_version": "2.43.0",
        "git_path": "/usr/bin/git",
        "git_sha256": "2a8c" + "0" * 60,
        "bun_lock_sha256": "da59" + "0" * 60,
        "cargo_lock_sha256": "ad47" + "0" * 60,
        "cargo_toml_sha256": "8ff1" + "0" * 60,
        "module_bazel_sha256": "7eba" + "0" * 60,
        "module_bazel_lock_sha256": "0060" + "0" * 60,
        "module_bazel_lock_effective_sha256": "0376" + "0" * 60,
        "bazelversion_sha256": "1b94" + "0" * 60,
        "rust_toolchain_label": (
            "@rust_linux_x86_64__x86_64-unknown-linux-gnu__nightly_tools//:rust_toolchain"
        ),
        "cc_toolchain_label": "@zig_sdk//libc_aware/toolchain:linux_amd64_gnu.2.17",
        "rustc_executable_sha256": "aa" + "0" * 62,
        "cc_compile_executable_sha256": "bb" + "0" * 62,
        "link_executable_sha256": "cc" + "0" * 62,
        "native_archive_patch_sha256": "ee" + "0" * 62,
        "canonical_build_root": "/opt/omp-canonical",
        "bazel_jobs": "1",
        "bazel_spawn_strategy": "local",
        "native_addon_mtime_ns": 0,
        "environment_variables": (
            "HOME",
            "LANG",
            "LC_ALL",
            "OMP_I1_POSITIVE_ENV",
            "PATH",
            "SSL_CERT_DIR",
            "SSL_CERT_FILE",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
        ),
        "executable_sha256": "dd" + "0" * 62,
    }
    values.update(overrides)
    return OmpBinaryPin(**values)  # type: ignore[arg-type]


def _observations(pin: OmpBinaryPin, **overrides: object) -> dict[str, object]:
    env = {
        name: f"{pin.canonical_build_root}/{name.lower()}" for name in pin.environment_variables
    }
    values: dict[str, object] = {
        "canonical_build_root": pin.canonical_build_root,
        "bazel_jobs": pin.bazel_jobs,
        "bazel_spawn_strategy": pin.bazel_spawn_strategy,
        "native_addon_mtime_ns": pin.native_addon_mtime_ns,
        "native_archive_patch_sha256": pin.native_archive_patch_sha256,
        "bun": {
            "path": pin.bun_path,
            "version": pin.bun_version,
            "sha256": pin.bun_sha256,
        },
        "bazelisk": {
            "path": pin.bazelisk_path,
            "version": pin.bazelisk_version,
            "sha256": pin.bazelisk_sha256,
        },
        "bazel": {
            "path": pin.bazel_path,
            "version": pin.bazel_version,
            "sha256": pin.bazel_sha256,
        },
        "git": {
            "path": pin.git_path,
            "version": pin.git_version,
            "sha256": pin.git_sha256,
        },
        "native_target": pin.native_target,
        "bun_lock_sha256": pin.bun_lock_sha256,
        "cargo_lock_sha256": pin.cargo_lock_sha256,
        "cargo_toml_sha256": pin.cargo_toml_sha256,
        "module_bazel_sha256": pin.module_bazel_sha256,
        "module_bazel_lock_sha256": pin.module_bazel_lock_sha256,
        "module_bazel_lock_effective_sha256": pin.module_bazel_lock_effective_sha256,
        "bazelversion_sha256": pin.bazelversion_sha256,
        "rust_toolchain_label": pin.rust_toolchain_label,
        "cc_toolchain_label": pin.cc_toolchain_label,
        "rustc_executable_sha256": pin.rustc_executable_sha256,
        "cc_compile_executable_sha256": pin.cc_compile_executable_sha256,
        "link_executable_sha256": pin.link_executable_sha256,
        "environment": env,
    }
    values.update(overrides)
    return values


# --- Platform / CPU target ----------------------------------------------------

def test_supported_platform_and_cpu_target_validate() -> None:
    pin = _pin()
    validate_platform(pin, platform="linux", arch="x86_64", avx2=True)
    validate_cpu_target(pin, native_target="//:natives-linux-x64-modern")
    assert pin.platform == "linux"
    assert pin.arch == "x86_64"
    assert pin.avx2 is True


def test_wrong_platform_rejected() -> None:
    pin = _pin()
    for platform in ("darwin", "win32", "freebsd", ""):
        with pytest.raises(OmpPinError):
            validate_platform(pin, platform=platform, arch="x86_64", avx2=True)


def test_wrong_architecture_rejected() -> None:
    pin = _pin()
    for arch in ("arm64", "aarch64", "x86", "riscv64", ""):
        with pytest.raises(OmpPinError):
            validate_platform(pin, platform="linux", arch=arch, avx2=True)


def test_missing_avx2_rejected() -> None:
    pin = _pin()
    with pytest.raises(OmpPinError):
        validate_platform(pin, platform="linux", arch="x86_64", avx2=False)


def test_wrong_bazel_native_target_rejected() -> None:
    pin = _pin()
    for target in (
        "//:natives-linux-x64-baseline",
        "//:natives-linux-arm64",
        "//:natives-darwin-arm64",
        "",
    ):
        with pytest.raises(OmpPinError):
            validate_cpu_target(pin, native_target=target)


# --- Version / digest observations --------------------------------------------

def test_supplied_version_and_digest_match_validate() -> None:
    pin = _pin()
    validate_version_digest(pin, version=pin.version, sha256=pin.executable_sha256)


def test_wrong_version_rejected() -> None:
    pin = _pin()
    for version in ("17.3.5", "18.0.0", "v17.3.4", "17.3", ""):
        with pytest.raises(OmpPinError):
            validate_version_digest(pin, version=version, sha256=pin.executable_sha256)


def test_wrong_executable_digest_rejected() -> None:
    pin = _pin()
    wrong = "ee" + "0" * 62
    assert wrong != pin.executable_sha256
    with pytest.raises(OmpPinError):
        validate_version_digest(pin, version=pin.version, sha256=wrong)


def test_malformed_digest_syntax_rejected() -> None:
    pin = _pin()
    for digest in ("", "sha256:dd", "DD" + "0" * 62, "xyz", "dd" + "0" * 61):
        with pytest.raises(OmpPinError):
            validate_version_digest(pin, version=pin.version, sha256=digest)


# --- Build observations ---------------------------------------------------------

def test_matching_build_observations_validate() -> None:
    pin = _pin()
    validate_build_observations(pin, observations=_observations(pin))


def test_wrong_launcher_path_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["bazelisk"] = dict(obs["bazelisk"], path="/usr/local/bin/bazelisk")  # type: ignore[arg-type]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_wrong_launcher_digest_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["bazelisk"] = dict(obs["bazelisk"], sha256="ff" + "0" * 62)  # type: ignore[arg-type]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_wrong_launcher_version_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["bazelisk"] = dict(obs["bazelisk"], version="1.28.0")  # type: ignore[arg-type]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_wrong_resolved_bazel_path_and_digest_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["bazel"] = dict(obs["bazel"], path="/opt/cache/bin/bazel-other")  # type: ignore[arg-type]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)
    obs = _observations(pin)
    obs["bazel"] = dict(obs["bazel"], sha256="77" + "0" * 62)  # type: ignore[arg-type]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_wrong_bun_path_digest_or_version_rejected() -> None:
    pin = _pin()
    for field, value in (
        ("path", "/opt/tools/bin/bun-other"),
        ("sha256", "99" + "0" * 62),
        ("version", "1.3.13"),
    ):
        obs = _observations(pin)
        obs["bun"] = dict(obs["bun"], **{field: value})  # type: ignore[arg-type]
        with pytest.raises(OmpPinError):
            validate_build_observations(pin, observations=obs)


def test_wrong_git_path_or_digest_rejected() -> None:
    pin = _pin()
    for field, value in (("path", "/usr/local/bin/git"), ("sha256", "2b" + "0" * 62)):
        obs = _observations(pin)
        obs["git"] = dict(obs["git"], **{field: value})  # type: ignore[arg-type]
        with pytest.raises(OmpPinError):
            validate_build_observations(pin, observations=obs)


def test_rust_toolchain_label_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["rust_toolchain_label"] = "@rust_linux_x86_64__x86_64-unknown-linux-gnu__nightly_tools//:other_toolchain"  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_cc_toolchain_label_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["cc_toolchain_label"] = "@zig_sdk//libc_aware/toolchain:linux_amd64_gnu.2.28"  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_rustc_executable_digest_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["rustc_executable_sha256"] = "ab" + "0" * 62  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_cc_compile_executable_digest_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["cc_compile_executable_sha256"] = "ac" + "0" * 62  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_link_executable_digest_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["link_executable_sha256"] = "ad" + "0" * 62  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_missing_observation_members_rejected() -> None:
    pin = _pin()
    for key in ("bun", "bazelisk", "bazel", "git", "native_target", "environment"):
        obs = _observations(pin)
        del obs[key]  # type: ignore[misc]
        with pytest.raises(OmpPinError):
            validate_build_observations(pin, observations=obs)


def test_wrong_native_target_in_observations_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["native_target"] = "//:natives-linux-x64-baseline"  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


# --- Positive environment schema ----------------------------------------------

_PLANTED_OVERRIDES = (
    "OMP_NATIVE_BUILD_BACKEND",
    "OMP_BAZEL_RC",
    "USE_BAZEL_VERSION",
    "USE_BAZELISK_VERSION",
    "BAZELISK_HOME",
    "BAZEL_HOME",
    "BUN_COMPILE_EXECUTABLE_PATH",
    "BUN_OPTIONS",
    "BUN_PRELOAD",
    "NODE_OPTIONS",
    "NODE_PRELOAD",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "CFLAGS",
    "CXXFLAGS",
    "LDFLAGS",
    "CPPFLAGS",
    "CC",
    "CXX",
    "RUSTFLAGS",
    "RUSTDOCFLAGS",
    "RUSTC",
    "RUSTC_WRAPPER",
    "CARGO_HOME",
    "RUSTUP_HOME",
    "CARGO_TARGET_DIR",
    "CROSS_TARGET",
    "TARGET_PLATFORM",
    "TARGET_ARCH",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "__PI_NATIVE_VARIANT_CACHE",
    "PI_CONFIG_DIR",
    "PI_CODING_AGENT_DIR",
)


def test_planted_parent_build_overrides_rejected() -> None:
    pin = _pin()
    for name in _PLANTED_OVERRIDES:
        obs = _observations(pin)
        env: dict[str, str] = dict(obs["environment"])  # type: ignore[arg-type]
        env[name] = "planted"
        obs["environment"] = env
        with pytest.raises(OmpPinError):
            validate_build_observations(pin, observations=obs)


def test_environment_missing_admitted_variable_rejected() -> None:
    pin = _pin()
    for name in pin.environment_variables:
        obs = _observations(pin)
        env: dict[str, str] = dict(obs["environment"])  # type: ignore[arg-type]
        del env[name]
        obs["environment"] = env
        with pytest.raises(OmpPinError):
            validate_build_observations(pin, observations=obs)


def test_environment_extra_variable_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    env: dict[str, str] = dict(obs["environment"])  # type: ignore[arg-type]
    env["IRRELEVANT_JUNK"] = "x"
    obs["environment"] = env
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_environment_empty_value_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    env: dict[str, str] = dict(obs["environment"])  # type: ignore[arg-type]
    env["PATH"] = ""
    obs["environment"] = env
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_module_bazel_lock_declared_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["module_bazel_lock_sha256"] = "0061" + "0" * 60  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_module_bazel_lock_effective_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["module_bazel_lock_effective_sha256"] = "0377" + "0" * 60  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_cargo_toml_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["cargo_toml_sha256"] = "8ff2" + "0" * 60  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_other_build_input_hash_drift_rejected() -> None:
    pin = _pin()
    for key in (
        "bun_lock_sha256",
        "cargo_lock_sha256",
        "module_bazel_sha256",
        "bazelversion_sha256",
        "native_archive_patch_sha256",
    ):
        obs = _observations(pin)
        obs[key] = "ab" + "0" * 62  # type: ignore[assignment]
        with pytest.raises(OmpPinError):
            validate_build_observations(pin, observations=obs)


def test_declared_and_effective_lock_states_both_validate() -> None:
    pin = _pin()
    assert pin.module_bazel_lock_sha256 != pin.module_bazel_lock_effective_sha256
    validate_build_observations(pin, observations=_observations(pin))


def test_canonical_build_root_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["canonical_build_root"] = "/opt/somewhere-else"  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_environment_values_outside_canonical_root_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    env: dict[str, str] = dict(obs["environment"])  # type: ignore[arg-type]
    env["HOME"] = "/elsewhere/home"
    obs["environment"] = env
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)
    obs = _observations(pin)
    env: dict[str, str] = dict(obs["environment"])  # type: ignore[arg-type]
    env["XDG_CACHE_HOME"] = f"{pin.canonical_build_root}2/cache"
    obs["environment"] = env
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


def test_environment_values_inside_canonical_root_validate() -> None:
    pin = _pin()
    validate_build_observations(pin, observations=_observations(pin))


def test_bazel_jobs_drift_rejected() -> None:
    pin = _pin()
    obs = _observations(pin)
    obs["bazel_jobs"] = "32"  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)
    obs = _observations(pin)
    obs["bazel_jobs"] = 1  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)

def test_reproducibility_control_drift_rejected() -> None:
    pin = _pin()
    for key, value in (
        ("bazel_spawn_strategy", "sandboxed"),
        ("bazel_spawn_strategy", 1),
        ("native_addon_mtime_ns", 1),
        ("native_addon_mtime_ns", "0"),
        ("native_addon_mtime_ns", True),
    ):
        obs = _observations(pin)
        obs[key] = value
        with pytest.raises(OmpPinError):
            validate_build_observations(pin, observations=obs)


def test_canonical_pin_serializes_reproducibility_controls() -> None:
    payload = json.loads(canonical_pin_json(_pin()))
    assert payload.get("bazel_spawn_strategy") == "local"
    assert payload.get("native_addon_mtime_ns") == 0


# --- Non-string values ----------------------------------------------------------

def test_non_string_values_rejected() -> None:
    pin = _pin()
    with pytest.raises(OmpPinError):
        validate_version_digest(pin, version=17, sha256=pin.executable_sha256)
    with pytest.raises(OmpPinError):
        validate_version_digest(pin, version=pin.version, sha256=123)
    with pytest.raises(OmpPinError):
        validate_version_digest(pin, version=None, sha256=None)
    with pytest.raises(OmpPinError):
        validate_platform(pin, platform=b"linux", arch="x86_64", avx2=True)
    with pytest.raises(OmpPinError):
        validate_cpu_target(pin, native_target=42)
    obs = _observations(pin)
    obs["native_target"] = 42  # type: ignore[assignment]
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)
    obs = _observations(pin)
    env = dict(obs["environment"])  # type: ignore[arg-type]
    env["PATH"] = 7  # type: ignore[assignment]
    obs["environment"] = env
    with pytest.raises(OmpPinError):
        validate_build_observations(pin, observations=obs)


# --- Exact canonical serialization ----------------------------------------------

def test_exact_canonical_serialization() -> None:
    pin = _pin()
    expected = json.dumps(
        dataclasses.asdict(pin),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    assert canonical_pin_json(pin) == expected
    assert "\n" not in canonical_pin_json(pin)
    assert canonical_pin_json(pin) == canonical_pin_json(pin)


def test_canonical_serialization_differs_on_field_change() -> None:
    base = _pin()
    for overrides in (
        {"version": "17.3.5"},
        {"executable_sha256": "ee" + "0" * 62},
        {"avx2": False},
        {"native_target": "//:natives-linux-x64-baseline"},
        {"bazel_spawn_strategy": "sandboxed"},
        {"native_addon_mtime_ns": 1},
    ):
        assert canonical_pin_json(_pin(**overrides)) != canonical_pin_json(base)


def test_canonical_serialization_roundtrips_to_fields() -> None:
    pin = _pin()
    expected = dataclasses.asdict(pin)
    expected["environment_variables"] = list(pin.environment_variables)
    assert json.loads(canonical_pin_json(pin)) == expected


# --- Frozen singleton ------------------------------------------------------------

def test_pin_is_frozen_and_immutable() -> None:
    pin = _pin()
    with pytest.raises(dataclasses.FrozenInstanceError):
        pin.version = "18.0.0"  # type: ignore[misc]


def test_frozen_pin_structure_is_complete_and_valid() -> None:
    pin = OMP_BINARY_PIN
    assert isinstance(pin, OmpBinaryPin)
    assert pin.platform == "linux"
    assert pin.arch == "x86_64"
    assert pin.avx2 is True
    assert pin.native_target == "//:natives-linux-x64-modern"
    assert pin.version == "17.3.4"
    assert len(pin.source_commit) == 40
    for digest_field in (
        "bun_sha256",
        "bazelisk_sha256",
        "bazel_sha256",
        "git_sha256",
        "bun_lock_sha256",
        "cargo_lock_sha256",
        "cargo_toml_sha256",
        "module_bazel_sha256",
        "module_bazel_lock_sha256",
        "module_bazel_lock_effective_sha256",
        "bazelversion_sha256",
        "rustc_executable_sha256",
        "cc_compile_executable_sha256",
        "link_executable_sha256",
        "native_archive_patch_sha256",
        "executable_sha256",
    ):
        digest = getattr(pin, digest_field)
        assert isinstance(digest, str) and len(digest) == 64
        assert all(ch in "0123456789abcdef" for ch in digest)
    for path_field in ("bun_path", "bazelisk_path", "bazel_path", "git_path"):
        assert isinstance(getattr(pin, path_field), str)
        assert getattr(pin, path_field).startswith("/")
    assert pin.environment_variables == (
        "HOME",
        "LANG",
        "LC_ALL",
        "OMP_I1_POSITIVE_ENV",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
    )
    validate_platform(pin, platform="linux", arch="x86_64", avx2=True)
    validate_cpu_target(pin, native_target=pin.native_target)
    validate_version_digest(pin, version=pin.version, sha256=pin.executable_sha256)
    validate_build_observations(
        pin,
        observations=_observations_from_pin(pin),
    )


def test_native_archive_overlay_bytes_match_frozen_pin() -> None:
    overlay = Path(__file__).parents[1] / "orchestrator/providers/omp_native_archive.patch"
    assert (
        hashlib.sha256(overlay.read_bytes()).hexdigest()
        == OMP_BINARY_PIN.native_archive_patch_sha256
    )


def _observations_from_pin(pin: OmpBinaryPin) -> Mapping[str, object]:
    """Build observations that exactly match the frozen pin record."""
    env = {
        name: f"{pin.canonical_build_root}/{name.lower()}" for name in pin.environment_variables
    }
    return {
        "canonical_build_root": pin.canonical_build_root,
        "bazel_jobs": pin.bazel_jobs,
        "bazel_spawn_strategy": pin.bazel_spawn_strategy,
        "native_addon_mtime_ns": pin.native_addon_mtime_ns,
        "bun": {"path": pin.bun_path, "version": pin.bun_version, "sha256": pin.bun_sha256},
        "bazelisk": {"path": pin.bazelisk_path, "version": pin.bazelisk_version, "sha256": pin.bazelisk_sha256},
        "bazel": {"path": pin.bazel_path, "version": pin.bazel_version, "sha256": pin.bazel_sha256},
        "git": {"path": pin.git_path, "version": pin.git_version, "sha256": pin.git_sha256},
        "native_target": pin.native_target,
        "bun_lock_sha256": pin.bun_lock_sha256,
        "cargo_lock_sha256": pin.cargo_lock_sha256,
        "cargo_toml_sha256": pin.cargo_toml_sha256,
        "module_bazel_sha256": pin.module_bazel_sha256,
        "module_bazel_lock_sha256": pin.module_bazel_lock_sha256,
        "module_bazel_lock_effective_sha256": pin.module_bazel_lock_effective_sha256,
        "bazelversion_sha256": pin.bazelversion_sha256,
        "native_archive_patch_sha256": pin.native_archive_patch_sha256,
        "rust_toolchain_label": pin.rust_toolchain_label,
        "cc_toolchain_label": pin.cc_toolchain_label,
        "rustc_executable_sha256": pin.rustc_executable_sha256,
        "cc_compile_executable_sha256": pin.cc_compile_executable_sha256,
        "link_executable_sha256": pin.link_executable_sha256,
        "environment": env,
    }


def test_validation_is_pure_and_unaffected_by_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin = _pin()
    monkeypatch.setenv("OMP_BINARY_PIN_EXECUTABLE_SHA256", "0" * 64)
    monkeypatch.setenv("OMP_NATIVE_BUILD_BACKEND", "cargo")
    assert canonical_pin_json(pin) == json.dumps(
        dataclasses.asdict(pin),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    validate_platform(pin, platform="linux", arch="x86_64", avx2=True)
    validate_version_digest(pin, version=pin.version, sha256=pin.executable_sha256)
    validate_build_observations(pin, observations=_observations(pin))
