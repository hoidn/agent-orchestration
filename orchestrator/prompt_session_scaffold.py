"""Exact descriptor verification for public and run-private prompt scaffolds."""
from __future__ import annotations
import hashlib
import json
import os
from dataclasses import replace
from types import MappingProxyType
from typing import Mapping
from orchestrator._common.safe_tree import SafeTreeError, read_regular_file
from orchestrator.prompt_contract import canonical_json_bytes, parse_semantic_contract, semantic_contract_sha256
from orchestrator.prompt_scaffold import (
    ScaffoldInputs, ScaffoldVerification, ScaffoldVerificationError,
    _scaffold_files, identity_for,
)
from orchestrator.prompt_scaffold_verify import verify_occupant
from orchestrator.providers.omp_conf import ConfFileRecord, ConfSnapshot, OmpConfError, admit_conf_tree
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.providers.omp_protocol import loads_strict

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _invalid(detail: str, cause: BaseException | None = None) -> PromptSessionError:
    from orchestrator.prompt_session import PromptSessionError
    error = PromptSessionError("session_link_invalid", detail)
    if cause is not None:
        error.__cause__ = cause
    return error


def _snapshot_from_bytes(files: Mapping[str, bytes]) -> ConfSnapshot:
    ordered = sorted(files, key=lambda path: path.encode("utf-8"))
    records = {
        path: ConfFileRecord(path, len(files[path]), hashlib.sha256(files[path]).hexdigest(), files[path], 0, 0)
        for path in ordered
    }
    rows = [
        {"mode": "0644", "path": path, "sha256": records[path].sha256, "size": records[path].size_bytes}
        for path in ordered
    ]
    manifest_bytes = json.dumps(
        {"schema_version": "omp_conf_manifest.v1", "files": rows},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return ConfSnapshot(
        files=MappingProxyType(records), manifest_bytes=manifest_bytes,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def _private_no_tools_inputs(*, prompt_sha256: str, contract, model: str, conf: ConfSnapshot) -> ScaffoldInputs:
    return ScaffoldInputs.from_admitted_no_tools_conf(
        prompt_sha256=prompt_sha256,
        contract=contract,
        model=model,
        admitted_conf=conf,
        slug="prompt",
        pin=OMP_BINARY_PIN,
    )


def _inputs(*, provider: str, model: str, prompt_sha256: str, contract, conf: ConfSnapshot | None) -> ScaffoldInputs:
    if provider == "omp_no_tools":
        if conf is None:
            raise _invalid("no-tools private conf is missing")
        return _private_no_tools_inputs(
            prompt_sha256=prompt_sha256, contract=contract, model=model, conf=conf,
        )
    return ScaffoldInputs(
        prompt_sha256=prompt_sha256, contract=contract, provider=provider,
        model=model, conf_manifest=conf, slug="prompt", pin=OMP_BINARY_PIN,
    )


def _expected(inputs: ScaffoldInputs) -> tuple[set[str], dict[str, bytes]]:
    files, _conf = _scaffold_files(inputs, b"", {"mode": "exact"})
    deterministic = {
        path: data for path, data in files.items()
        if path not in ("prompt.md", "output-contract.json")
    }
    return set(files), deterministic


def _semantic(scaffold_fd: int):
    try:
        document = loads_strict(read_regular_file(scaffold_fd, "output-contract.json").decode("utf-8"))
    except (SafeTreeError, UnicodeDecodeError, ValueError) as exc:
        raise _invalid("private output contract cannot be admitted", exc)
    if not isinstance(document, dict) or set(document) != {"schema_version", "semantic", "authoring"}:
        raise _invalid("private output contract is not the closed object")
    try:
        return parse_semantic_contract(canonical_json_bytes(document["semantic"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid("private semantic contract is invalid", exc)


def _admit_conf(scaffold_fd: int, relative: str) -> ConfSnapshot:
    try:
        conf_fd = os.open(relative, _DIR_FLAGS, dir_fd=scaffold_fd)
    except OSError as exc:
        raise _invalid(f"private conf {relative!r} cannot be opened", exc)
    try:
        return admit_conf_tree(conf_fd)
    except (OSError, OmpConfError, SafeTreeError, TypeError, ValueError) as exc:
        raise _invalid(f"private conf {relative!r} cannot be admitted", exc)
    finally:
        os.close(conf_fd)


def _provider_binding(manifest_bytes: bytes) -> tuple[dict, str, str]:
    try:
        manifest = loads_strict(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _invalid("scaffold manifest is not strict JSON", exc)
    provider = manifest.get("provider") if isinstance(manifest, dict) else None
    if not isinstance(provider, dict):
        raise _invalid("scaffold provider binding is missing")
    name, model = provider.get("registry_name"), provider.get("concrete_model")
    if not isinstance(name, str) or not isinstance(model, str):
        raise _invalid("scaffold provider/model binding is invalid")
    return manifest, name, model


def verify_private_scaffold(scaffold_fd: int, link) -> ScaffoldVerification:
    """Verify the held source-private occupant and every linked identity."""
    try:
        manifest_bytes = read_regular_file(scaffold_fd, "scaffold.json")
        prompt = read_regular_file(scaffold_fd, "prompt.md")
    except SafeTreeError as exc:
        raise _invalid("source private scaffold cannot be read", exc)
    _manifest, provider, model = _provider_binding(manifest_bytes)
    contract = _semantic(scaffold_fd)
    conf = None
    controlled: dict[str, bytes] = {}
    if provider == "omp_conf":
        conf = _admit_conf(scaffold_fd, "conf")
    elif provider == "omp_no_tools":
        conf = _admit_conf(scaffold_fd, ".omp-conf")
        controlled = {f".omp-conf/{path}": row.content for path, row in conf.files.items()}
    try:
        inputs = _inputs(
            provider=provider, model=model,
            prompt_sha256=hashlib.sha256(prompt).hexdigest(),
            contract=contract, conf=conf,
        )
        expected_paths, expected_files = _expected(inputs)
        verified = verify_occupant(
            scaffold_fd, inputs, identity_for(inputs), expected_paths,
            expected_files, controlled, 0o400,
        )
    except (
        OSError,
        SafeTreeError,
        ScaffoldVerificationError,
        TypeError,
        ValueError,
    ) as exc:
        raise _invalid("source private scaffold verification failed", exc)
    document = link.document
    comparisons = {
        "provider": provider == document["provider"]["name"],
        "model": model == document["provider"]["model"],
        "identity": verified.identity == document["scaffold_identity"],
        "manifest": (
            verified.manifest_bytes == manifest_bytes
            and hashlib.sha256(verified.manifest_bytes).hexdigest()
            == document["digests"]["scaffold_manifest_sha256"]
        ),
        "prompt": (
            verified.files["prompt.md"] == prompt
            and hashlib.sha256(verified.files["prompt.md"]).hexdigest()
            == document["digests"]["authored_prompt_sha256"]
        ),
        "source": hashlib.sha256(verified.files["run.orc"]).hexdigest()
        == document["digests"]["source_sha256"],
        "semantic": (
            verified.semantic_contract == contract
            and semantic_contract_sha256(verified.semantic_contract)
            == document["digests"]["semantic_contract_sha256"]
        ),
        "conf": (None if conf is None else conf.manifest_sha256)
        == document["digests"]["conf_manifest_sha256"],
    }
    mismatches = sorted(name for name, matches in comparisons.items() if not matches)
    if mismatches:
        raise _invalid(
            f"source private scaffold disagrees with link: {', '.join(mismatches)}"
        )
    files = dict(verified.files)
    files["scaffold.json"] = verified.manifest_bytes
    files.update(controlled)
    conf_files = (
        MappingProxyType({
            path: row.content for path, row in conf.files.items()
        })
        if provider == "omp_no_tools" and conf is not None
        else verified.conf_files
    )
    return replace(
        verified,
        files=MappingProxyType(files),
        conf_files=conf_files,
    )


def _captured_inputs(verification: ScaffoldVerification) -> ScaffoldInputs:
    conf = _snapshot_from_bytes(verification.conf_files) if verification.conf_files else None
    return _inputs(
        provider=verification.provider, model=verification.model,
        prompt_sha256=hashlib.sha256(verification.files["prompt.md"]).hexdigest(),
        contract=verification.semantic_contract, conf=conf,
    )


def verify_captured_occupant(scaffold_fd: int, verification: ScaffoldVerification, *, private: bool) -> None:
    """Prove one occupant exactly equals the pre-execution captured scaffold."""
    inputs = _captured_inputs(verification)
    expected_paths, expected_files = _expected(inputs)
    controlled = ({
        path: data for path, data in verification.files.items()
        if path.startswith(".omp-conf/")
    } if private else {})
    try:
        verified = verify_occupant(
            scaffold_fd, inputs, verification.identity, expected_paths,
            expected_files, controlled, 0o400 if private else 0o644,
        )
    except (
        OSError,
        SafeTreeError,
        ScaffoldVerificationError,
        TypeError,
        ValueError,
    ) as exc:
        raise _invalid("captured scaffold occupant drifted", exc)
    captured_files = {
        path: data for path, data in verification.files.items()
        if path != "scaffold.json" and not path.startswith(".omp-conf/")
    }
    if (
        verified.manifest_bytes != verification.manifest_bytes
        or dict(verified.files) != captured_files
    ):
        raise _invalid("captured scaffold bytes drifted")


def with_private_execution_authority(verification):
    """Retain manifest and captured neutral-conf bytes before execution."""
    files = dict(verification.files)
    files["scaffold.json"] = verification.manifest_bytes
    conf_files = dict(verification.conf_files)
    if verification.provider == "omp_no_tools":
        if not conf_files:
            from orchestrator.providers.omp_launch import neutral_conf_root
            try:
                descriptor = os.open(neutral_conf_root(), _DIR_FLAGS)
            except OSError as exc:
                raise _invalid("neutral conf cannot be captured", exc)
            try:
                snapshot = admit_conf_tree(descriptor)
            finally:
                os.close(descriptor)
            conf_files = {
                path: record.content for path, record in snapshot.files.items()
            }
        expected = {
            f".omp-conf/{path}": data for path, data in conf_files.items()
        }
        present = {
            path: data for path, data in files.items()
            if path.startswith(".omp-conf/")
        }
        if present and present != expected:
            raise _invalid("retained no-tools conf disagrees")
        files.update(expected)
    return replace(
        verification,
        files=MappingProxyType(files),
        conf_files=MappingProxyType(conf_files),
    )


def capture_no_tools_conf_authority(
    snapshot_fd: int,
) -> tuple[tuple[int, int], str]:
    """Capture the retained private conf identity and manifest before execution."""
    try:
        conf_fd = os.open(".omp-conf", _DIR_FLAGS, dir_fd=snapshot_fd)
    except OSError as exc:
        raise _invalid("private no-tools conf cannot be opened", exc)
    try:
        observed = os.fstat(conf_fd)
        try:
            digest = admit_conf_tree(conf_fd).manifest_sha256
        except (OSError, OmpConfError, SafeTreeError, TypeError, ValueError) as exc:
            raise _invalid("private no-tools conf cannot be admitted", exc)
        return (observed.st_dev, observed.st_ino), digest
    finally:
        os.close(conf_fd)


__all__ = [
    "capture_no_tools_conf_authority",
    "with_private_execution_authority",
    "verify_captured_occupant",
    "verify_private_scaffold",
]
