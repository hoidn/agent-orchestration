"""Deterministic OMP prompt scaffolds: identity, rendering, and publication API.

Implements X5/X7: closed identity (provider policy, pinned binary, conf
manifest, prompt digest, semantic contract, renderer version) drives
deterministic file generation; publication is exclusive via
``renameat2(RENAME_NOREPLACE)`` under a per-identity ``flock``; every
materialized/published path is descriptor-safe no-follow; the run-owned
private snapshot is materialized from bytes captured during verification, so
verification-to-execution swaps can never be consumed.

Rendered ``run.orc`` targets DSL 2.27, pins the concrete model, returns the
exact semantic contract, declares exactly one ``:session-artifact
omp_session``, and passes ``omp_conf_root`` as an input only for ``omp_conf``.
The packaged neutral conf manifest is bound into ``omp_no_tools`` identity
without any conf copy or authored override. Nothing here starts providers,
links sessions, or resumes TTYs (Tasks 8-10).

Deterministic byte rendering, input admission, the shared error vocabulary,
and the compiled-contract derivation live in the narrowly named sibling
``prompt_scaffold_render``; descriptor-safe filesystem mechanics live in
``prompt_scaffold_fs``; occupant verification in ``prompt_scaffold_verify``.
The documented import surface stays at ``orchestrator.prompt_scaffold``.
"""

from __future__ import annotations

import os
import re
from dataclasses import InitVar, dataclass
from pathlib import Path
from typing import Mapping

from orchestrator.prompt_contract import (
    RENDERER_VERSION,
    SemanticContract,
    canonical_json_bytes,
    semantic_contract_object,
    validate_authoring,
    validate_contract,
)
from orchestrator.prompt_scaffold_conf import owned_conf_snapshot
from orchestrator.prompt_scaffold_render import (
    OMP_PROVIDER_POLICY,
    OMP_PROVIDER_POLICY_VERSION,
    PUBLIC_PROVIDER_NAMES,
    SCAFFOLD_SCHEMA_VERSION,
    PromptScaffoldError,
    ScaffoldCompileError,
    ScaffoldIdentityError,
    ScaffoldLockError,
    ScaffoldPublicationError,
    ScaffoldSnapshotError,
    ScaffoldVerificationError,
    _FILE_MODE,
    _NOFOLLOW_DIR,
    _binary_object,
    _conf_manifest_object,
    _manifest_bytes,
    _neutral_conf_snapshot,
    _provider_object,
    _scaffold_files,
    _sha256,
    _validate_provider_template,
)
from orchestrator.providers.omp_pin import OMP_BINARY_PIN, OmpBinaryPin
from orchestrator.providers.omp_templates import DEFAULT_OMP_MODEL

IDENTITY_SCHEMA_VERSION = "scaffold_identity.v1"

__all__ = [
    "OMP_PROVIDER_POLICY",
    "OMP_PROVIDER_POLICY_VERSION",
    "PUBLIC_PROVIDER_NAMES",
    "SCAFFOLD_SCHEMA_VERSION",
    "PromptScaffoldError",
    "ScaffoldCompileError",
    "ScaffoldIdentityError",
    "ScaffoldLockError",
    "ScaffoldPublicationError",
    "ScaffoldSnapshotError",
    "ScaffoldVerificationError",
    "ScaffoldInputs",
    "ScaffoldResult",
    "ScaffoldVerification",
    "RunSnapshot",
    "identity_for",
    "resolve_concrete_model",
    "scaffold_dir_name",
    "slugify",
    "generate_scaffold",
    "verify_scaffold",
    # Lazy fs facade services (resolved through the PEP 562 __getattr__).
    "compile_snapshot",
    "create_run_root",
    "derive_compiled_contract",
    "materialize_run_snapshot",
]




_SOURCE_CONF_AUTHORITY = object()


@dataclass(frozen=True, slots=True)
class ScaffoldInputs:
    """Closed identity inputs: prompt digest, contract, provider, model,
    authored conf manifest, slug, and the pinned binary record."""

    prompt_sha256: str
    contract: SemanticContract
    provider: str
    model: str
    conf_manifest: object | None
    slug: str
    pin: OmpBinaryPin
    _source_conf_authority: InitVar[object | None] = None

    def __post_init__(self, _source_conf_authority: object | None) -> None:
        admitted_no_tools_conf = _source_conf_authority is _SOURCE_CONF_AUTHORITY
        if _source_conf_authority is not None and not admitted_no_tools_conf:
            raise ValueError("invalid internal source-conf authority")
        if not isinstance(self.prompt_sha256, str) or re.fullmatch(
            r"^[0-9a-f]{64}$", self.prompt_sha256
        ) is None:
            raise ValueError(
                "prompt_sha256 must be a 64-char lowercase hex SHA-256"
            )
        if not isinstance(self.pin, OmpBinaryPin):
            raise ValueError("pin must be an OmpBinaryPin")
        if self.provider not in PUBLIC_PROVIDER_NAMES:
            raise ValueError(f"unknown provider {self.provider!r}")
        validate_contract(self.contract)
        object.__setattr__(
            self, "model", resolve_concrete_model(self.provider, self.model)
        )
        if self.provider in ("omp", "omp_unrestricted_workspace"):
            if self.conf_manifest is not None:
                raise ValueError(
                    f"{self.provider} is ambient and binds no conf manifest "
                    "(X7: conf_manifest is null)"
                )
        if self.provider == "omp_conf":
            if self.conf_manifest is None:
                raise ValueError("omp_conf requires an authored conf manifest")
            object.__setattr__(
                self, "conf_manifest", owned_conf_snapshot(self.conf_manifest)
            )
        if self.provider == "omp_no_tools":
            if admitted_no_tools_conf:
                if self.conf_manifest is None:
                    raise ValueError("admitted no-tools conf is missing")
                object.__setattr__(
                    self, "conf_manifest", owned_conf_snapshot(self.conf_manifest)
                )
            else:
                if self.conf_manifest is not None:
                    raise ValueError(
                        "omp_no_tools binds the packaged neutral conf manifest; "
                        "an authored conf override is refused"
                    )
                object.__setattr__(
                    self, "conf_manifest",
                    owned_conf_snapshot(_neutral_conf_snapshot()),
                )
        elif admitted_no_tools_conf:
            raise ValueError("admitted no-tools conf requires omp_no_tools")
        if not isinstance(self.slug, str) or not self.slug:
            raise ValueError("slug must be a non-empty string")
        for label in ("platform", "arch", "version"):
            if not isinstance(getattr(self.pin, label), str) or not getattr(
                self.pin, label
            ):
                raise ValueError(f"pin.{label} must be a non-empty string")
        digest = self.pin.executable_sha256
        if not isinstance(digest, str) or re.fullmatch(
            r"^[0-9a-f]{64}$", digest
        ) is None:
            raise ValueError(
                "pin.executable_sha256 must be a 64-char lowercase hex"
            )
        _validate_provider_template(self.provider)

    @classmethod
    def from_admitted_no_tools_conf(
        cls,
        *,
        prompt_sha256: str,
        contract: SemanticContract,
        model: str,
        admitted_conf: object,
        slug: str,
        pin: OmpBinaryPin,
    ) -> "ScaffoldInputs":
        """Construct validated no-tools identity directly from admitted private conf."""
        return cls(
            prompt_sha256=prompt_sha256,
            contract=contract,
            provider="omp_no_tools",
            model=model,
            conf_manifest=admitted_conf,
            slug=slug,
            pin=pin,
            _source_conf_authority=_SOURCE_CONF_AUTHORITY,
        )

    @property
    def conf_manifest_sha256(self) -> str | None:
        manifest = self.conf_manifest
        return None if manifest is None else manifest.manifest_sha256


@dataclass(frozen=True, slots=True)
class ScaffoldVerification:
    """Bytes and identity captured from one verified scaffold publication.

    ``files``/``conf_files``/``manifest`` are immutable views of captured
    bytes; ``manifest_bytes`` retains the exact verified ``scaffold.json``
    bytes so downstream consumers (Task 9 link binding) can hash/bind the
    manifest without reopening the mutable published scaffold. The captured
    file mapping never includes ``scaffold.json`` itself.
    """

    identity: str
    provider: str
    model: str
    semantic_contract: SemanticContract
    files: Mapping[str, bytes]
    conf_files: Mapping[str, bytes]
    manifest: object
    manifest_bytes: bytes


@dataclass(frozen=True, slots=True)
class ScaffoldResult:
    """One scaffold publication: identity, directory, reuse flag, and the
    captured verification for run snapshot materialization."""

    path: Path
    identity: str
    reused: bool
    verification: ScaffoldVerification


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    """The run-owned private snapshot consumed by the runner (Task 8+).

    ``provider`` is the verified provider bound at materialization;
    ``compile_snapshot`` refuses any other provider. ``root_fd`` retains the
    no-follow directory descriptor so compilation happens through a retained
    descriptor path, never the mutable published/generated path. The caller
    (Task 8) holds the snapshot as a context manager through compilation/run;
    ``__exit__`` closes the descriptor, ``close()`` is idempotent, and the
    finalizer backstop closes a snapshot that was never exited.
    """

    root: Path
    run_orc: Path
    prompt_md: Path
    prompts_json: Path
    providers_json: Path
    output_contract_json: Path
    conf_root: Path | None
    provider: str
    root_fd: int

    def close(self) -> None:
        """Close the retained root descriptor; idempotent and safe to repeat."""
        fd = self.root_fd
        if fd >= 0:
            object.__setattr__(self, "root_fd", -1)
            os.close(fd)

    def __enter__(self) -> "RunSnapshot":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def resolve_concrete_model(provider: str, model: object) -> str:
    """Resolve the pinned concrete model; ``None`` selects the template default."""
    if provider not in PUBLIC_PROVIDER_NAMES:
        raise ValueError(f"unknown provider {provider!r}")
    if model is None:
        return DEFAULT_OMP_MODEL
    if not isinstance(model, str) or not model:
        raise ValueError("model must be a non-empty string")
    return model


def slugify(stem: str) -> str:
    """Normalize a slug: lowercase, non-alnum to ``-``, stripped, capped 32."""
    text = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return text[:32] or "prompt"


def identity_for(inputs: ScaffoldInputs) -> str:
    """The closed identity: SHA-256 of the canonical identity basis JSON.

    ``conf_manifest`` is null for ambient lanes and otherwise the parsed
    exact closed ``omp_conf_manifest.v1`` object (X7), never the digest key.
    """
    basis = {
        "schema": IDENTITY_SCHEMA_VERSION,
        "renderer_version": RENDERER_VERSION,
        "prompt_sha256": inputs.prompt_sha256,
        "semantic_contract": semantic_contract_object(inputs.contract),
        "provider": _provider_object(inputs),
        "binary": _binary_object(inputs),
        "prompt_externs": {"prompts.task": "prompt.md"},
        "provider_externs": {"providers.task": inputs.provider},
        "conf_manifest": _conf_manifest_object(inputs.conf_manifest),
    }
    return _sha256(canonical_json_bytes(basis))


def scaffold_dir_name(inputs: ScaffoldInputs) -> str:
    return f"{slugify(inputs.slug)}-{identity_for(inputs)[:12]}"


# --- publication API -----------------------------------------------------------


def generate_scaffold(
    *,
    generated_root: Path,
    inputs: ScaffoldInputs,
    prompt_bytes: bytes,
    authoring: object,
) -> ScaffoldResult:
    """Generate, compile-check, and exclusively publish one scaffold.

    A same-identity concurrent publication serializes on the per-identity
    lock; the loser re-verifies the winner's occupant and reuses it. A
    mismatched occupant is refused (never deleted, replaced, or forced).

    Closed gates run before any identity, lock, or filesystem work: prompt
    bytes must be non-empty UTF-8 matching ``inputs.prompt_sha256``, authoring
    must validate, and the binary pin must be the current ``OMP_BINARY_PIN``.
    """
    from orchestrator.prompt_scaffold_fs import (
        acquire_scaffold_lock,
        open_generated_root,
        publish_scaffold,
    )

    if not isinstance(prompt_bytes, bytes) or not prompt_bytes:
        raise ValueError("prompt_bytes must be non-empty bytes")
    try:
        prompt_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("prompt_bytes must be valid UTF-8") from exc
    if _sha256(prompt_bytes) != inputs.prompt_sha256:
        raise ValueError("prompt_bytes do not match inputs.prompt_sha256")
    validate_authoring(authoring)
    if inputs.pin != OMP_BINARY_PIN:
        raise ValueError(
            "inputs.pin does not match the current OMP_BINARY_PIN"
        )
    identity = identity_for(inputs)
    files, _conf = _scaffold_files(inputs, prompt_bytes, authoring)
    rows = [
        {
            "path": relative,
            "size": len(data),
            "sha256": _sha256(data),
            "mode": _FILE_MODE,
        }
        for relative, data in sorted(
            files.items(), key=lambda item: item[0].encode("utf-8")
        )
    ]
    files["scaffold.json"] = _manifest_bytes(inputs, identity, rows)
    expected_files = {
        path: data
        for path, data in files.items()
        if path not in ("prompt.md", "output-contract.json", "scaffold.json")
    }

    destination = Path(generated_root) / scaffold_dir_name(inputs)
    root_fd = open_generated_root(Path(generated_root))
    lock_fd = None
    try:
        lock_fd = acquire_scaffold_lock(root_fd, identity)
        verification, reused = publish_scaffold(
            root_fd,
            generated_root=Path(generated_root),
            destination_name=destination.name,
            files=files,
            identity=identity,
            inputs=inputs,
            expected_files=expected_files,
        )
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        os.close(root_fd)
    return ScaffoldResult(
        path=destination, identity=identity, reused=reused,
        verification=verification,
    )


def _require_single_component(name: object) -> None:
    """One safe scaffold path component; traversal/slashes/NUL fail closed."""
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or "/" in name
        or "\x00" in name
    ):
        raise ValueError("scaffold name must be one safe path component")


def verify_scaffold(
    *,
    generated_root: Path,
    inputs: ScaffoldInputs,
    name: str | None = None,
) -> ScaffoldVerification:
    """Re-verify one published scaffold against the declared identity inputs;
    any drift (source, conf, provider, model, or binary pin) rejects the run."""
    from orchestrator.prompt_scaffold_fs import (
        open_generated_root,
        verify_occupant,
    )

    if inputs.pin != OMP_BINARY_PIN:
        raise ValueError(
            "inputs.pin does not match the current OMP_BINARY_PIN"
        )
    if name is not None:
        _require_single_component(name)
    identity = identity_for(inputs)
    name = name or scaffold_dir_name(inputs)
    root_fd = open_generated_root(Path(generated_root))
    try:
        try:
            scaffold_fd = os.open(name, _NOFOLLOW_DIR, dir_fd=root_fd)
        except FileNotFoundError as exc:
            raise ScaffoldIdentityError(
                f"scaffold {name!r} not published for this identity"
            ) from exc
        try:
            files, _conf = _scaffold_files(inputs, b"", {"mode": "exact"})
            expected_files = {
                path: data
                for path, data in files.items()
                if path not in ("prompt.md", "output-contract.json")
            }
            return verify_occupant(
                scaffold_fd, inputs, identity, set(files), expected_files
            )
        finally:
            os.close(scaffold_fd)
    finally:
        os.close(root_fd)


# Public facade for the fs sibling's compile/snapshot services. The facade is
# lazy (PEP 562) so a fresh interpreter importing the fs sibling first cannot
# deadlock the module cycle.
_FS_FACADE = (
    "compile_snapshot",
    "create_run_root",
    "derive_compiled_contract",
    "materialize_run_snapshot",
)


def __getattr__(name: str):
    if name in _FS_FACADE:
        from orchestrator import prompt_scaffold_fs

        value = getattr(prompt_scaffold_fs, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
