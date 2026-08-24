"""Deterministic scaffold rendering, admission, and contract derivation.

Narrowly named sibling of ``orchestrator.prompt_scaffold``: the shared error
vocabulary, the code-owned provider policy and identity objects, closed-input
admission (prompt/conf/provider-template validation), deterministic byte
rendering of ``run.orc`` / manifests / scaffold.json, and the compiled-contract
derivation shared by publication compile-checks and private-snapshot
compilation. This module imports nothing from ``prompt_scaffold`` so the
documented public surface can stay at ``orchestrator.prompt_scaffold``.
"""

from __future__ import annotations

import os
import re
from typing import Mapping

from orchestrator.prompt_contract import (
    RENDERER_VERSION,
    ContractField,
    ListType,
    MapType,
    OptionalType,
    PrimitiveType,
    SemanticContract,
    canonical_json_bytes,
    output_contract_document,
    parse_strict_json_object,
    semantic_contract_sha256,
)
from orchestrator.providers.omp_launch import LANE_POLICY, neutral_conf_root
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint

PUBLIC_PROVIDER_NAMES = (
    "omp",
    "omp_no_tools",
    "omp_conf",
    "omp_unrestricted_workspace",
)
OMP_PROVIDER_POLICY_VERSION = "omp_provider_policy.v1"
SCAFFOLD_SCHEMA_VERSION = "prompt_scaffold.v1"
_MODULE_NAME = "run"
_FILE_MODE = "0644"
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_NOFOLLOW_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class PromptScaffoldError(Exception):
    """Base class for scaffold generation, verification, and snapshots."""


class ScaffoldIdentityError(PromptScaffoldError):
    """The scaffold's identity disagrees with the declared inputs."""


class ScaffoldVerificationError(PromptScaffoldError):
    """The published scaffold tree violates the closed file contract."""


class ScaffoldPublicationError(PromptScaffoldError):
    """Atomic publication failed."""


class ScaffoldLockError(PromptScaffoldError):
    """The per-identity publication lock is unusable."""


class ScaffoldSnapshotError(PromptScaffoldError):
    """The run-owned private snapshot could not be created."""


class ScaffoldCompileError(PromptScaffoldError):
    """The generated source did not compile to the declared contract."""


# Code-owned provider policy; identity and the rendered source bind it.
OMP_PROVIDER_POLICY: Mapping[str, Mapping[str, object]] = {
    name: {
        "policy_version": OMP_PROVIDER_POLICY_VERSION,
        "lane": LANE_POLICY[name],
        "approval_mode": "yolo" if name == "omp_unrestricted_workspace" else "write",
        "publishes_fresh_session": True,
    }
    for name in PUBLIC_PROVIDER_NAMES
}


def _neutral_conf_snapshot() -> object:
    """Admit the code-owned packaged neutral conf tree (cached, immutable)."""
    from orchestrator.providers.omp_conf import admit_conf_tree

    snapshot = getattr(_neutral_conf_snapshot, "_cached", None)
    if snapshot is None:
        fd = os.open(
            neutral_conf_root(),
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        try:
            snapshot = admit_conf_tree(fd)
        finally:
            os.close(fd)
        _neutral_conf_snapshot._cached = snapshot
    return snapshot


def _conf_manifest_object(manifest: object) -> object:
    """The exact closed ``omp_conf_manifest.v1`` object, or ``None``.

    Identity binds the parsed canonical manifest object (X7), never the
    digest key; the canonical roundtrip proves the exact closed form.
    """
    if manifest is None:
        return None
    manifest_bytes = getattr(manifest, "manifest_bytes", None)
    if not isinstance(manifest_bytes, bytes) or not manifest_bytes:
        raise ValueError("conf manifest bytes are missing")
    parsed = parse_strict_json_object(manifest_bytes)
    if set(parsed) != {"schema_version", "files"}:
        raise ValueError("conf manifest is not the exact closed object shape")
    if parsed.get("schema_version") != "omp_conf_manifest.v1":
        raise ValueError("conf manifest schema_version mismatch")
    if canonical_json_bytes(parsed) != manifest_bytes:
        raise ValueError("conf manifest is not the canonical closed object")
    return parsed


def _validate_conf_snapshot(manifest: object) -> None:
    """Reject a forged or internally inconsistent ``ConfSnapshot``.

    Every record digest is recomputed from its content, the manifest digest
    from its bytes, and the exact ordered canonical manifest rows must equal
    the records — a manually built snapshot whose hashes or rows disagree is
    refused before any identity use. Content bytes may be empty (the size is
    nonnegative); only the bytes type is required.
    """
    from orchestrator._common.safe_tree import validate_relative_path
    from orchestrator.providers.omp_conf import ConfFileRecord, ConfSnapshot

    if not isinstance(manifest, ConfSnapshot):
        raise ValueError("conf_manifest must be a ConfSnapshot")
    # _conf_manifest_object type-checks manifest_bytes (bytes) first, so a
    # forged snapshot with non-bytes bytes raises ValueError, not TypeError.
    parsed = _conf_manifest_object(manifest)
    if not isinstance(manifest.manifest_sha256, str) or _HEX_SHA256_RE.fullmatch(
        manifest.manifest_sha256
    ) is None:
        raise ValueError("conf manifest_sha256 must be a 64-char lowercase hex")
    if _sha256(manifest.manifest_bytes) != manifest.manifest_sha256:
        raise ValueError("conf manifest_sha256 does not match its bytes")
    files = manifest.files
    if not isinstance(files, Mapping):
        raise ValueError("conf snapshot files must be a mapping")
    ordered: list[ConfFileRecord] = []
    for relative, record in files.items():
        if not isinstance(relative, str):
            raise ValueError("conf snapshot file key must be a string")
        validate_relative_path(relative)
        if not isinstance(record, ConfFileRecord):
            raise ValueError(
                f"conf snapshot file {relative!r} is not a ConfFileRecord"
            )
        if record.relative_path != relative:
            raise ValueError(
                f"conf snapshot file key {relative!r} disagrees with its record"
            )
        if not isinstance(record.content, bytes):
            raise ValueError(f"conf snapshot file {relative!r} content must be bytes")
        if not isinstance(record.sha256, str) or _HEX_SHA256_RE.fullmatch(
            record.sha256
        ) is None:
            raise ValueError(f"conf snapshot file {relative!r} has an invalid sha256")
        if _sha256(record.content) != record.sha256:
            raise ValueError(
                f"conf snapshot file {relative!r} sha256 does not match its content"
            )
        if type(record.size_bytes) is not int or record.size_bytes < 0:
            raise ValueError(f"conf snapshot file {relative!r} has an invalid size")
        if record.size_bytes != len(record.content):
            raise ValueError(
                f"conf snapshot file {relative!r} size disagrees with its bytes"
            )
        ordered.append(record)
    expected_rows = [
        {
            "mode": "0644",
            "path": record.relative_path,
            "sha256": record.sha256,
            "size": record.size_bytes,
        }
        for record in sorted(
            ordered, key=lambda record: record.relative_path.encode("utf-8")
        )
    ]
    if parsed["files"] != expected_rows:
        raise ValueError(
            "conf manifest rows disagree with the snapshot records"
        )


def _validate_provider_template(provider: str) -> None:
    """The selected installed template must match the code-owned entry.

    X7: generation and verified rerun compare the captured template to the
    code-owned ``omp_templates`` table before hashing; the current policy is
    itself code-owned. No pin equality is checked here (identity stays pure
    for injected-pin sensitivity; the current-pin gate is applied at
    ``generate_scaffold``/``verify_scaffold``).
    """
    from orchestrator.providers.omp_templates import omp_templates
    from orchestrator.providers.registry import ProviderRegistry

    installed = ProviderRegistry().get(provider)
    if installed is None or installed != omp_templates()[provider]:
        raise ValueError(
            f"installed provider template for {provider!r} does not match "
            "the code-owned omp_templates entry"
        )


def _sha256(data: bytes) -> str:
    from hashlib import sha256

    return sha256(data).hexdigest()


def _provider_object(inputs: object) -> dict[str, object]:
    policy = OMP_PROVIDER_POLICY[inputs.provider]
    return {
        "extern": "providers.task",
        "registry_name": inputs.provider,
        "concrete_model": inputs.model,
        "policy_version": policy["policy_version"],
        "lane": policy["lane"],
        "approval_mode": policy["approval_mode"],
        "publishes_fresh_session": policy["publishes_fresh_session"],
    }


def _binary_object(inputs: object) -> dict[str, object]:
    return {
        "platform": inputs.pin.platform,
        "arch": inputs.pin.arch,
        "version": inputs.pin.version,
        "sha256": inputs.pin.executable_sha256,
    }


# --- rendering ----------------------------------------------------------------


def _render_type(node) -> str:
    if isinstance(node, PrimitiveType):
        return node.name
    if isinstance(node, OptionalType):
        return f"Optional[{_render_type(node.item)}]"
    if isinstance(node, ListType):
        return f"List[{_render_type(node.item)}]"
    if isinstance(node, MapType):
        return f"Map[String,{_render_type(node.value)}]"
    raise PromptScaffoldError(f"cannot render type node {node!r}")


def wfl_string_literal(text: str) -> str:
    """One Workflow Lisp-safe double-quoted string body.

    Control characters are rejected outright and ``\\`` / ``"`` are escaped
    so a model selector containing syntax punctuation can never break out of
    the literal into surrounding Lisp forms.
    """
    for character in text:
        code = ord(character)
        if code < 0x20 or code == 0x7F:
            raise ValueError("model selector contains a control character")
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _render_run_orc(inputs: object) -> bytes:
    contract = inputs.contract
    lines = [
        "(workflow-lisp",
        '  (:language "0.1")',
        '  (:target-dsl "2.27")',
        f"  (defmodule {_MODULE_NAME})",
        f"  (export {_MODULE_NAME})",
    ]
    if contract.mode == "record":
        lines.append(f"  (defrecord {contract.record_name}")
        for field in contract.fields:
            lines.append(f"    ({field.name} {_render_type(field.type)})")
        lines.append(")")
    with_conf = inputs.provider == "omp_conf"
    params = "((omp_conf_root String))" if with_conf else "()"
    result = (
        _render_type(contract.type)
        if contract.mode == "scalar"
        else contract.record_name
    )
    lines.append(f"  (defworkflow {_MODULE_NAME} {params} -> {result}")
    lines.append("    (provider-result providers.task")
    lines.append("      :prompt prompts.task")
    lines.append(f"      :inputs {'(omp_conf_root)' if with_conf else '()'}")
    lines.append(f'      :model "{wfl_string_literal(inputs.model)}"')
    lines.append("      :session-artifact omp_session")
    lines.append(f"      :returns {result})")
    lines.append(")")
    lines.append(")")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _prompts_manifest() -> bytes:
    return b'{"prompts.task":"prompt.md"}\n'


def _providers_manifest(provider: str) -> bytes:
    return canonical_json_bytes({"providers.task": provider}) + b"\n"


def _output_contract_bytes(inputs: object, authoring: object) -> bytes:
    return canonical_json_bytes(
        output_contract_document(inputs.contract, authoring)
    ) + b"\n"


def _manifest_bytes(inputs: object, identity: str, rows: list[dict[str, object]]) -> bytes:
    manifest = {
        "schema_version": SCAFFOLD_SCHEMA_VERSION,
        "identity": identity,
        "renderer_version": RENDERER_VERSION,
        "prompt_sha256": inputs.prompt_sha256,
        "semantic_contract_sha256": semantic_contract_sha256(inputs.contract),
        "provider": _provider_object(inputs),
        "binary": _binary_object(inputs),
        "conf_manifest_sha256": inputs.conf_manifest_sha256,
        "files": rows,
    }
    return canonical_json_bytes(manifest) + b"\n"


def _scaffold_files(
    inputs: object, prompt_bytes: bytes, authoring: object
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """All scaffold files keyed by scaffold-root-relative path, plus the conf
    subtree keyed relative to ``conf/`` (empty unless ``omp_conf``)."""
    files: dict[str, bytes] = {
        "run.orc": _render_run_orc(inputs),
        "prompt.md": prompt_bytes,
        "prompts.json": _prompts_manifest(),
        "providers.json": _providers_manifest(inputs.provider),
        "output-contract.json": _output_contract_bytes(inputs, authoring),
    }
    conf_files: dict[str, bytes] = {}
    if inputs.provider == "omp_conf":
        conf_files = {
            record.relative_path: record.content
            for record in inputs.conf_manifest.files.values()
        }
        for relative, data in conf_files.items():
            files[f"conf/{relative}"] = data
    return files, conf_files


# --- compiled-contract derivation ----------------------------------------------


def _bundle_field_type(field: Mapping[str, object]):
    kind = field["type"]
    if kind == "string":
        return PrimitiveType("String")
    if kind == "integer":
        return PrimitiveType("Int")
    if kind == "float":
        return PrimitiveType("Float")
    if kind == "boolean":
        return PrimitiveType("Bool")
    if kind == "optional":
        return OptionalType(_bundle_field_type(field["item"]))
    if kind == "list":
        return ListType(_bundle_field_type(field["items"]))
    if kind == "map":
        return MapType(_bundle_field_type(field["values"]))
    raise ScaffoldCompileError(f"unknown compiled field type {kind!r}")


def derive_compiled_contract(compiled: object) -> SemanticContract:
    """Re-derive the semantic contract from the compiled workflow mapping."""
    mapping = compiled.entry_result.lowered_workflows[0].authored_mapping
    step = next(step for step in mapping["steps"] if "provider" in step)
    fields = step["output_bundle"]["fields"]
    if len(fields) == 1 and fields[0].get("name") == "__result__":
        return SemanticContract(mode="scalar", type=_bundle_field_type(fields[0]))
    return SemanticContract(
        mode="record",
        record_name=None,
        fields=tuple(
            ContractField(field["name"], _bundle_field_type(field))
            for field in fields
        ),
    )


def _fd_root(fd: int):
    """A stable path to a retained directory descriptor (Linux)."""
    from pathlib import Path

    return Path(f"/proc/self/fd/{fd}")


def compile_check(root_fd: int, provider: str) -> SemanticContract:
    """Compile a directory-descriptor tree through its retained fd path."""
    root = _fd_root(root_fd)
    try:
        compiled = compile_stage3_entrypoint(
            root / "run.orc",
            source_roots=(root,),
            provider_externs={"providers.task": provider},
            prompt_externs={"prompts.task": {"asset_file": "prompt.md"}},
            validate_shared=True,
            workspace_root=root,
        )
    except Exception as exc:
        raise ScaffoldCompileError(
            f"generated source failed Stage 3 compilation: {exc}"
        ) from exc
    return derive_compiled_contract(compiled)
