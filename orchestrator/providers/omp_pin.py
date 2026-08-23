"""Candidate pin for the self-built OMP v17.3.4 executable (F4).

The record remains incomplete until two clean whole outputs compare
byte-for-byte. It binds the positive build environment, launcher/toolchain
identities, source/module-lock hashes, producing-build controls, and admitted
executable digest. Validators are pure: they compare caller-supplied
observations and never read process or filesystem state.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from dataclasses import dataclass

from orchestrator._common.canonical import compact_ascii_json_dumps

_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class OmpPinError(ValueError):
    """A supplied observation disagrees with the frozen OMP binary pin."""


@dataclass(frozen=True, slots=True)
class OmpBinaryPin:
    """Immutable admission record for the OMP v17.3.4 executable.

    Every field is a code-owned constant. There is deliberately no
    environment-variable override for any member: admission compares supplied
    observations against this record and fails closed on any drift.
    """

    platform: str
    arch: str
    avx2: bool
    native_target: str
    version: str
    source_commit: str

    # Build launchers: canonical path, version, and whole-file SHA-256.
    bun_version: str
    bun_path: str
    bun_sha256: str
    bazelisk_version: str
    bazelisk_path: str
    bazelisk_sha256: str
    bazel_version: str
    bazel_path: str
    bazel_sha256: str
    git_version: str
    git_path: str
    git_sha256: str

    # Source/module-lock hashes measured before and after each clean build.
    # Cargo.toml and Cargo.lock are both crate_universe extension inputs.
    bun_lock_sha256: str
    cargo_lock_sha256: str
    cargo_toml_sha256: str
    module_bazel_sha256: str
    # MODULE.bazel.lock has two admitted identities: the declared/committed
    # source lock each no-local clone MUST start from, and the deterministic
    # effective post-resolution lock (see the design's documented v17.3.4
    # release-omission exception). Any other state is rejected.
    module_bazel_lock_sha256: str
    module_bazel_lock_effective_sha256: str
    bazelversion_sha256: str
    # Audited overlay applied to the pinned upstream source before compilation.
    native_archive_patch_sha256: str

    # Bazel action-toolchain closure selected for //:natives-linux-x64-modern.
    rust_toolchain_label: str
    cc_toolchain_label: str
    rustc_executable_sha256: str
    cc_compile_executable_sha256: str
    link_executable_sha256: str

    # Positive launch environment: the exhaustive admitted variable names,
    # all rooted at the recorded canonical build root.
    canonical_build_root: str
    # Producing-build controls that remove the two observed nondeterministic
    # addon inputs before whole-file comparison.
    bazel_jobs: str
    bazel_spawn_strategy: str
    native_addon_mtime_ns: int
    environment_variables: tuple[str, ...]

    # Whole single-file executable.
    executable_sha256: str


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise OmpPinError(f"{label} must be a non-empty string")
    return value


def _require_sha256(value: object, label: str) -> str:
    text = _require_str(value, label)
    if _HEX_SHA256_RE.fullmatch(text) is None:
        raise OmpPinError(f"{label} must be a 64-char lowercase hex SHA-256")
    return text


def validate_platform(
    pin: OmpBinaryPin,
    *,
    platform: object,
    arch: object,
    avx2: object,
) -> None:
    """Require the observed host to match the pinned Linux x86_64 AVX2 pin."""
    observed_platform = _require_str(platform, "platform")
    observed_arch = _require_str(arch, "architecture")
    if not isinstance(avx2, bool):
        raise OmpPinError("avx2 must be a boolean")
    if observed_platform != pin.platform:
        raise OmpPinError(
            f"platform {observed_platform!r} does not match pinned {pin.platform!r}"
        )
    if observed_arch != pin.arch:
        raise OmpPinError(
            f"architecture {observed_arch!r} does not match pinned {pin.arch!r}"
        )
    if not avx2:
        raise OmpPinError("AVX2 support is required by this pin")


def validate_cpu_target(pin: OmpBinaryPin, *, native_target: object) -> None:
    """Require the Bazel native target to be the pinned AVX2 linux-x64 target."""
    observed = _require_str(native_target, "native target")
    if observed != pin.native_target:
        raise OmpPinError(
            f"native target {observed!r} does not match pinned {pin.native_target!r}"
        )


def validate_version_digest(
    pin: OmpBinaryPin,
    *,
    version: object,
    sha256: object,
) -> None:
    """Require a supplied version/digest observation to match the executable."""
    observed_version = _require_str(version, "version")
    observed_digest = _require_sha256(sha256, "executable SHA-256")
    if observed_version != pin.version:
        raise OmpPinError(
            f"version {observed_version!r} does not match pinned {pin.version!r}"
        )
    if observed_digest != pin.executable_sha256:
        raise OmpPinError("executable SHA-256 does not match the pinned digest")


def _validate_tool(
    observations: Mapping[str, object],
    key: str,
    *,
    expected_path: str,
    expected_version: str,
    expected_digest: str,
) -> None:
    observed = observations.get(key)
    if not isinstance(observed, Mapping):
        raise OmpPinError(f"build observation {key!r} must be a mapping")
    observed_path = _require_str(observed.get("path"), f"{key} path")
    observed_version = _require_str(observed.get("version"), f"{key} version")
    observed_digest = _require_sha256(observed.get("sha256"), f"{key} SHA-256")
    if observed_path != expected_path:
        raise OmpPinError(
            f"{key} path {observed_path!r} does not match pinned {expected_path!r}"
        )
    if observed_version != expected_version:
        raise OmpPinError(
            f"{key} version {observed_version!r} does not match pinned "
            f"{expected_version!r}"
        )
    if observed_digest != expected_digest:
        raise OmpPinError(f"{key} SHA-256 does not match the pinned digest")


def _validate_environment(
    pin: OmpBinaryPin,
    environment: object,
) -> None:
    if not isinstance(environment, Mapping):
        raise OmpPinError("build observation 'environment' must be a mapping")
    admitted = set(pin.environment_variables)
    observed_names = set(environment)
    if observed_names != admitted:
        missing = sorted(admitted - observed_names)
        extra = sorted(observed_names - admitted)
        raise OmpPinError(
            "launch environment must contain exactly the positive schema "
            f"variables; missing={missing} extra={extra}"
        )
    root = pin.canonical_build_root
    for name in pin.environment_variables:
        value = environment.get(name)
        if not isinstance(value, str) or not value:
            raise OmpPinError(
                f"environment variable {name!r} must be a non-empty string"
            )
    for name in pin.environment_variables:
        if name in ("HOME", "TMPDIR") or name.startswith("XDG_"):
            value = environment[name]
            if not (value + "/").startswith(root + "/"):
                raise OmpPinError(
                    f"environment variable {name!r} value {value!r} is not "
                    f"under the canonical build root {root!r}"
                )


def validate_build_observations(
    pin: OmpBinaryPin,
    *,
    observations: object,
) -> None:
    """Require recorded build observations to match every pinned identity.

    Rejects a wrong launcher path/version/digest, wrong resolved Bazel, wrong
    Git, wrong native target, drifted Rust/C/C++ toolchain labels or
    executable digests, and any planted parent build override in the launch
    environment (the environment must equal the positive schema exactly).
    """
    if not isinstance(observations, Mapping):
        raise OmpPinError("build observations must be a mapping")
    _validate_tool(
        observations,
        "bun",
        expected_path=pin.bun_path,
        expected_version=pin.bun_version,
        expected_digest=pin.bun_sha256,
    )
    _validate_tool(
        observations,
        "bazelisk",
        expected_path=pin.bazelisk_path,
        expected_version=pin.bazelisk_version,
        expected_digest=pin.bazelisk_sha256,
    )
    _validate_tool(
        observations,
        "bazel",
        expected_path=pin.bazel_path,
        expected_version=pin.bazel_version,
        expected_digest=pin.bazel_sha256,
    )
    _validate_tool(
        observations,
        "git",
        expected_path=pin.git_path,
        expected_version=pin.git_version,
        expected_digest=pin.git_sha256,
    )
    observed_target = _require_str(
        observations.get("native_target"), "native target"
    )
    if observed_target != pin.native_target:
        raise OmpPinError(
            f"native target {observed_target!r} does not match pinned "
            f"{pin.native_target!r}"
        )
    observed_root = _require_str(
        observations.get("canonical_build_root"), "canonical build root"
    )
    if observed_root != pin.canonical_build_root:
        raise OmpPinError(
            f"canonical build root {observed_root!r} does not match pinned "
            f"{pin.canonical_build_root!r}"
        )
    observed_jobs = _require_str(
        observations.get("bazel_jobs"), "bazel jobs"
    )
    if observed_jobs != pin.bazel_jobs:
        raise OmpPinError(
            f"bazel jobs {observed_jobs!r} does not match pinned {pin.bazel_jobs!r}"
        )
    observed_strategy = _require_str(
        observations.get("bazel_spawn_strategy"), "Bazel spawn strategy"
    )
    if observed_strategy != pin.bazel_spawn_strategy:
        raise OmpPinError(
            f"Bazel spawn strategy {observed_strategy!r} does not match pinned "
            f"{pin.bazel_spawn_strategy!r}"
        )
    observed_mtime_ns = observations.get("native_addon_mtime_ns")
    if (
        type(observed_mtime_ns) is not int
        or observed_mtime_ns != pin.native_addon_mtime_ns
    ):
        raise OmpPinError(
            "native addon mtime ns does not match pinned "
            f"{pin.native_addon_mtime_ns!r}"
        )
    for key, expected in (
        ("bun_lock_sha256", pin.bun_lock_sha256),
        ("cargo_lock_sha256", pin.cargo_lock_sha256),
        ("cargo_toml_sha256", pin.cargo_toml_sha256),
        ("module_bazel_sha256", pin.module_bazel_sha256),
        ("module_bazel_lock_sha256", pin.module_bazel_lock_sha256),
        ("module_bazel_lock_effective_sha256", pin.module_bazel_lock_effective_sha256),
        ("bazelversion_sha256", pin.bazelversion_sha256),
        ("native_archive_patch_sha256", pin.native_archive_patch_sha256),
    ):
        observed_digest = _require_sha256(observations.get(key), f"{key}")
        if observed_digest != expected:
            raise OmpPinError(f"{key} does not match the pinned digest")
    observed_rust = _require_str(
        observations.get("rust_toolchain_label"), "Rust toolchain label"
    )
    if observed_rust != pin.rust_toolchain_label:
        raise OmpPinError(
            f"Rust toolchain label {observed_rust!r} does not match pinned "
            f"{pin.rust_toolchain_label!r}"
        )
    observed_cc = _require_str(
        observations.get("cc_toolchain_label"), "C/C++ toolchain label"
    )
    if observed_cc != pin.cc_toolchain_label:
        raise OmpPinError(
            f"C/C++ toolchain label {observed_cc!r} does not match pinned "
            f"{pin.cc_toolchain_label!r}"
        )
    for key, expected in (
        ("rustc_executable_sha256", pin.rustc_executable_sha256),
        ("cc_compile_executable_sha256", pin.cc_compile_executable_sha256),
        ("link_executable_sha256", pin.link_executable_sha256),
    ):
        observed_digest = _require_sha256(
            observations.get(key), f"{key} executable SHA-256"
        )
        if observed_digest != expected:
            raise OmpPinError(f"{key} does not match the pinned executable digest")
    _validate_environment(pin, observations.get("environment"))


def canonical_pin_json(pin: OmpBinaryPin) -> str:
    """Return the exact canonical serialization of the pin record."""
    return compact_ascii_json_dumps(dataclasses.asdict(pin))


def _sha256(value: str) -> str:
    if _HEX_SHA256_RE.fullmatch(value) is None:
        raise AssertionError(f"invalid pinned SHA-256 literal: {value!r}")
    return value


def _commit(value: str) -> str:
    if _HEX_COMMIT_RE.fullmatch(value) is None:
        raise AssertionError(f"invalid pinned commit literal: {value!r}")
    return value


OMP_BINARY_PIN = OmpBinaryPin(
    platform="linux",
    arch="x86_64",
    avx2=True,
    native_target="//:natives-linux-x64-modern",
    version="17.3.4",
    source_commit=_commit("ffd53ff92a6f575d499730475a73460dd7cc2eea"),
    bun_version="1.3.14",
    bun_path="/home/ollie/.bun/bin/bun",
    bun_sha256=_sha256("9fd36f87e4b90b07632b987a2e4ec81ca15a62c81bf983190cea6d715be2ad74"),
    bazelisk_version="1.29.0",
    bazelisk_path="/home/ollie/.local/opt/omp-i1-tools/bazelisk",
    bazelisk_sha256=_sha256("5a408715e932c0250d28bd84555f12edbf70117de42f9181691c736eacc4a992"),
    bazel_version="9.2.0",
    bazel_path=(
        "/home/ollie/.cache/bazelisk/downloads/sha256/"
        "7668a95db1250f12c40407251e4e203b4ec8bf39bc495d2f485b2d8c99048694/bin/bazel"
    ),
    bazel_sha256=_sha256("7668a95db1250f12c40407251e4e203b4ec8bf39bc495d2f485b2d8c99048694"),
    git_version="2.43.0",
    git_path="/usr/bin/git",
    git_sha256=_sha256("2a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668"),
    bun_lock_sha256=_sha256("da59664f5956518e0b8fe66472c5de79a14f88a9a016c075308b815bd5c74f76"),
    cargo_lock_sha256=_sha256("ad471d6b6cc10d96d87fb259fd7ba5287eb2262a581b69ec30b5a01879f75f8b"),
    cargo_toml_sha256=_sha256("8ff17fda5daa014fefa536c347f3060d9fa159719665e31ac96d560566899bdb"),
    module_bazel_sha256=_sha256("7eba8ce12e97c47f3851381c35cc781fafa0b18e9ae2ba075a31d50bf6632ef9"),
    module_bazel_lock_sha256=_sha256("0060efc6e59203c4395a92b971859e6e51c2cef8a94fc8bf7443f9a003e9e2c9"),
    module_bazel_lock_effective_sha256=_sha256(
        "037601949bfb583a6e301589698894df301acfe82e858b6e9619575a864ca1ed"
    ),
    bazelversion_sha256=_sha256("1b9487d55bea47fea50d226cc9c53bc548877ad2a318bac8fbc8b320f429e5c5"),
    native_archive_patch_sha256=_sha256(
        "a5bb53ab92814423139518fc535493bcdb27ee8a9350b8d93801dabafb23c375"
    ),
    rust_toolchain_label=(
        "@@rules_rust++rust+rust_linux_x86_64__x86_64-unknown-linux-gnu__"
        "nightly_tools//:rust_toolchain"
    ),
    cc_toolchain_label=(
        "@@hermetic_cc_toolchain++toolchains+zig_config//:"
        "x86_64-linux-gnu.2.17_cc"
    ),
    rustc_executable_sha256=_sha256(
        "7e2e2af3e78489bbc2acedc6c8a2523e5d7636ef2b8694318e09eea8ea427ace"
    ),
    cc_compile_executable_sha256=_sha256(
        "75cf21290be09f56d26e1680be616234e7dc309ecf3f789598dba985ae3a84b8"
    ),
    link_executable_sha256=_sha256(
        "75cf21290be09f56d26e1680be616234e7dc309ecf3f789598dba985ae3a84b8"
    ),
    canonical_build_root="/home/ollie/.cache/omp-i1/canonical",
    bazel_jobs="1",
    bazel_spawn_strategy="local",
    native_addon_mtime_ns=0,
    environment_variables=(
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
    executable_sha256=_sha256(
        "f1ffead4d40e6d3740cd2400522d967b270dad5d43a80de7e70c509d97f88211"
    ),
)


__all__ = [
    "OMP_BINARY_PIN",
    "OmpBinaryPin",
    "OmpPinError",
    "canonical_pin_json",
    "validate_build_observations",
    "validate_cpu_target",
    "validate_platform",
    "validate_version_digest",
]
