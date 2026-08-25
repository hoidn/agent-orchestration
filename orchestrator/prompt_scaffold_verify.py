"""Closed occupant verification for published OMP prompt scaffolds (Task 7).

A narrowly named sibling of ``orchestrator.prompt_scaffold_fs``: verifies one
published scaffold tree against (a) the current declared inputs' deterministic
bytes, (b) the exact closed ``prompt_scaffold.v1`` manifest, and (c) the exact
directory set implied by the admitted file paths. Every regular file is opened
once through no-follow descriptors and hashed from the captured bytes (no
hash-then-reopen window); the actual mode 0644 is enforced; the captured
mapping returned to the runner is immutable and the exact ``scaffold.json``
bytes are retained for downstream manifest binding. ``prompt_scaffold_fs``
re-exports the service.
"""

from __future__ import annotations

import os
import stat
from types import MappingProxyType
from typing import Mapping

from orchestrator._common.safe_tree import walk_regular_files
from orchestrator.prompt_contract import (
    SCHEMA_VERSION,
    canonical_json_bytes,
    parse_strict_json_object,
    semantic_contract_object,
    semantic_contract_sha256,
    validate_authoring,
)
from orchestrator.prompt_scaffold import (
    RENDERER_VERSION,
    SCAFFOLD_SCHEMA_VERSION,
    ScaffoldIdentityError,
    ScaffoldInputs,
    ScaffoldVerification,
    ScaffoldVerificationError,
    _binary_object,
    _FILE_MODE,
    _provider_object,
    _sha256,
)

_NOFOLLOW_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_NOFOLLOW_REGULAR = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "identity",
        "renderer_version",
        "prompt_sha256",
        "semantic_contract_sha256",
        "provider",
        "binary",
        "conf_manifest_sha256",
        "files",
    }
)
_ROW_KEYS = frozenset({"path", "size", "sha256", "mode"})


def _deep_freeze(value: object) -> object:
    """Recursively freeze nested dict/list values into immutable views."""
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _expected_directories(paths: set[str]) -> frozenset[str]:
    """The exact directory set implied by scaffold-root-relative paths."""
    directories = {""}
    for relative in paths:
        parts = relative.split("/")
        for index in range(1, len(parts)):
            directories.add("/".join(parts[:index]))
    return frozenset(directories)


def _read_captured(scaffold_fd: int, relative: str) -> tuple[bytes, int]:
    """Open one regular file once (no-follow) and return bytes + actual mode.

    The descriptor used for the read is also the descriptor whose mode is
    checked, so a same-inode swap between hashing and capture cannot occur.
    """
    parent = scaffold_fd
    owned: list[int] = []
    try:
        for component in relative.split("/")[:-1]:
            try:
                child = os.open(component, _NOFOLLOW_DIR, dir_fd=parent)
            except OSError as exc:
                raise ScaffoldVerificationError(
                    f"occupant path {relative!r} cannot be traversed: {exc}"
                ) from exc
            owned.append(child)
            parent = child
        try:
            descriptor = os.open(
                relative.split("/")[-1], _NOFOLLOW_REGULAR, dir_fd=parent
            )
        except OSError as exc:
            raise ScaffoldVerificationError(
                f"occupant file {relative!r} cannot be opened: {exc}"
            ) from exc
    finally:
        for fd in reversed(owned):
            os.close(fd)
    try:
        kind = os.fstat(descriptor)
        if not stat.S_ISREG(kind.st_mode):
            raise ScaffoldVerificationError(
                f"occupant file {relative!r} is not a regular file"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                return b"".join(chunks), stat.S_IMODE(kind.st_mode)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def _validate_output_contract(data: bytes, inputs: ScaffoldInputs) -> None:
    """Admit one authoring-flexible output-contract document.

    The authoring provenance may differ by design across runs (default/exact/
    inferred), but the file must strict-parse and canonicalize, carry exactly
    the declared semantic contract, and pass the closed authoring validation.
    """
    try:
        document = parse_strict_json_object(data)
    except Exception as exc:
        raise ScaffoldVerificationError(
            f"occupant output-contract.json is not strict JSON: {exc}"
        ) from exc
    if canonical_json_bytes(document) + b"\n" != data:
        raise ScaffoldVerificationError(
            "occupant output-contract.json is not canonical JSON"
        )
    if set(document) != {"schema_version", "semantic", "authoring"}:
        raise ScaffoldVerificationError(
            "occupant output-contract.json has unknown keys"
        )
    if document["schema_version"] != SCHEMA_VERSION:
        raise ScaffoldVerificationError(
            "occupant output-contract schema_version mismatch"
        )
    if document["semantic"] != semantic_contract_object(inputs.contract):
        raise ScaffoldVerificationError(
            "occupant output-contract semantic disagrees with the declared "
            "contract"
        )
    try:
        validate_authoring(document["authoring"])
    except Exception as exc:
        raise ScaffoldVerificationError(
            f"occupant output-contract authoring is invalid: {exc}"
        ) from exc


def verify_occupant(
    scaffold_fd: int,
    inputs: ScaffoldInputs,
    identity: str,
    expected_paths: set[str],
    expected_files: Mapping[str, bytes],
    controlled_files: Mapping[str, bytes] | None = None,
    occupant_mode: int = 0o644,
) -> ScaffoldVerification:
    """Verify one published scaffold against current inputs and the exact
    closed manifest; every file's bytes are captured for the private snapshot.

    ``expected_files`` carries the deterministic bytes for every
    scaffold-root-relative path except ``prompt.md`` (admitted by its
    identity-bound SHA-256) and ``output-contract.json`` (authoring-flexible
    but closed-validated). Self-consistent tampering — source/conf edits with
    matching manifest-row hash/size updates — cannot pass because the captured
    bytes must equal the deterministic bytes for the current inputs.
    """
    controlled = dict(controlled_files or {})
    directories: list[str] = []
    rows = {
        row.relative_path: row
        for row in walk_regular_files(scaffold_fd, directories=directories)
    }
    if "scaffold.json" not in rows:
        raise ScaffoldVerificationError("occupant lacks scaffold.json")
    manifest_raw, scaffold_mode = _read_captured(scaffold_fd, "scaffold.json")
    if scaffold_mode != occupant_mode:
        raise ScaffoldVerificationError(
            f"occupant scaffold.json actual mode is not {occupant_mode:04o}"
        )
    try:
        manifest = parse_strict_json_object(manifest_raw)
    except Exception as exc:
        raise ScaffoldVerificationError(
            f"occupant scaffold.json is not strict JSON: {exc}"
        ) from exc
    if manifest.get("schema_version") != SCAFFOLD_SCHEMA_VERSION:
        raise ScaffoldVerificationError(
            "occupant scaffold schema_version mismatch"
        )
    if manifest.get("identity") != identity:
        raise ScaffoldIdentityError(
            "occupant identity disagrees with the declared inputs (drift)"
        )
    if set(manifest) != _MANIFEST_KEYS:
        raise ScaffoldVerificationError(
            "occupant scaffold.json has unknown or missing keys"
        )
    if manifest_raw != canonical_json_bytes(manifest) + b"\n":
        raise ScaffoldVerificationError(
            "occupant scaffold.json is not canonical JSON"
        )
    if manifest["renderer_version"] != RENDERER_VERSION:
        raise ScaffoldVerificationError(
            "occupant scaffold renderer_version mismatch"
        )
    if manifest["prompt_sha256"] != inputs.prompt_sha256:
        raise ScaffoldVerificationError(
            "occupant scaffold prompt_sha256 disagrees with the inputs"
        )
    if manifest["semantic_contract_sha256"] != semantic_contract_sha256(
        inputs.contract
    ):
        raise ScaffoldVerificationError(
            "occupant scaffold semantic_contract_sha256 disagrees with the "
            "inputs"
        )
    if manifest["provider"] != _provider_object(inputs):
        raise ScaffoldVerificationError(
            "occupant scaffold provider binding disagrees with the inputs"
        )
    if manifest["binary"] != _binary_object(inputs):
        raise ScaffoldVerificationError(
            "occupant scaffold binary binding disagrees with the inputs"
        )
    if manifest["conf_manifest_sha256"] != inputs.conf_manifest_sha256:
        raise ScaffoldVerificationError(
            "occupant scaffold conf_manifest_sha256 disagrees with the inputs"
        )
    walked_paths = set(rows) - {"scaffold.json"}
    complete_paths = expected_paths | set(controlled)
    if walked_paths != complete_paths:
        raise ScaffoldVerificationError(
            "occupant file set mismatch: "
            f"missing={sorted(complete_paths - walked_paths)} "
            f"extra={sorted(walked_paths - complete_paths)}"
        )
    if set(directories) != _expected_directories(complete_paths):
        raise ScaffoldVerificationError(
            f"missing={sorted(_expected_directories(complete_paths) - set(directories))} "
            f"extra={sorted(set(directories) - _expected_directories(complete_paths))}"
        )
    manifest_rows = manifest["files"]
    if not isinstance(manifest_rows, list) or len(manifest_rows) != len(
        expected_paths
    ):
        raise ScaffoldVerificationError("occupant files rows are incomplete")

    captured: dict[str, bytes] = {}
    for relative in sorted(expected_paths, key=lambda p: p.encode("utf-8")):
        data, actual_mode = _read_captured(scaffold_fd, relative)
        if actual_mode != occupant_mode:
            raise ScaffoldVerificationError(
                f"occupant file {relative!r} actual mode is not {occupant_mode:04o}"
            )
        digest = _sha256(data)
        if relative == "prompt.md":
            if digest != inputs.prompt_sha256:
                raise ScaffoldVerificationError(
                    "occupant prompt.md hash disagrees with the identity-bound "
                    "digest"
                )
        elif relative == "output-contract.json":
            _validate_output_contract(data, inputs)
        elif data != expected_files[relative]:
            raise ScaffoldVerificationError(
                f"occupant {relative!r} drifted from the deterministic bytes "
                "for the current inputs"
            )
        captured[relative] = data
    for relative in sorted(controlled, key=lambda p: p.encode("utf-8")):
        data, actual_mode = _read_captured(scaffold_fd, relative)
        if actual_mode != occupant_mode or data != controlled[relative]:
            raise ScaffoldVerificationError(
                f"occupant controlled file {relative!r} disagrees"
            )

    expected_rows: list[dict[str, object]] = []
    for relative in sorted(expected_paths, key=lambda p: p.encode("utf-8")):
        data = captured[relative]
        expected_rows.append(
            {
                "path": relative,
                "size": len(data),
                "sha256": (
                    inputs.prompt_sha256
                    if relative == "prompt.md"
                    else _sha256(data)
                ),
                "mode": _FILE_MODE,
            }
        )
    for index, row in enumerate(manifest_rows):
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise ScaffoldVerificationError(
                "occupant file row is not the exact closed row shape"
            )
        if row != expected_rows[index]:
            raise ScaffoldVerificationError(
                "occupant files rows are not the exact deterministic rows "
                "(self-consistent tampering cannot update source bytes)"
            )

    conf_files = {
        relative[len("conf/") :]: data
        for relative, data in captured.items()
        if relative.startswith("conf/")
    }
    return ScaffoldVerification(
        identity=identity,
        provider=inputs.provider,
        model=inputs.model,
        semantic_contract=inputs.contract,
        files=MappingProxyType(captured),
        conf_files=MappingProxyType(conf_files),
        manifest=_deep_freeze(manifest),
        manifest_bytes=manifest_raw,
    )


__all__ = ["verify_occupant"]
