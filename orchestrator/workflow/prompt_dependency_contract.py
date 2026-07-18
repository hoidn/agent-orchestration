"""Typed compiler contract for Workflow Lisp provider prompt dependencies."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


COMPILER_PROMPT_DEPENDENCY_CONTRACT_SCHEMA = "compiler_prompt_dependency_contract.v1"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class PromptDependencyOriginKind(Enum):
    """Closed compiler origin for the typed dependency contract."""

    WORKFLOW_LISP_PROVIDER_RESULT_PROMPT_DEPENDENCIES = (
        "workflow_lisp_provider_result_prompt_dependencies"
    )


class PromptDependencyPathInterpretation(Enum):
    """Closed path interpretation selected by the compiler."""

    EXACT = "exact"


class PromptDependencyPosition(Enum):
    """Closed prompt-injection position."""

    PREPEND = "prepend"
    APPEND = "append"


@dataclass(frozen=True)
class CompilerPromptDependencyContract:
    """Compiler-owned normalized provider prompt dependency contract."""

    schema: str
    origin_kind: PromptDependencyOriginKind
    path_interpretation: PromptDependencyPathInterpretation
    evidence_required: bool
    source_origin_key: str
    source_workflow_sha256: str
    required_binding_refs: tuple[str, ...]
    optional_binding_refs: tuple[str, ...]
    position: PromptDependencyPosition
    instruction_utf8_sha256_or_null: str | None
    normalized_contract_sha256: str

    def __post_init__(self) -> None:
        _validate_contract_fields(self)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def _sha256_digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _normalized_payload(
    *,
    required_binding_refs: tuple[str, ...],
    optional_binding_refs: tuple[str, ...],
    position: PromptDependencyPosition,
    instruction_utf8_sha256_or_null: str | None,
) -> dict[str, Any]:
    return {
        "schema": COMPILER_PROMPT_DEPENDENCY_CONTRACT_SCHEMA,
        "required_binding_refs": list(required_binding_refs),
        "optional_binding_refs": list(optional_binding_refs),
        "position": position.value,
        "instruction_utf8_sha256_or_null": instruction_utf8_sha256_or_null,
    }


def _normalized_contract_sha256(
    *,
    required_binding_refs: tuple[str, ...],
    optional_binding_refs: tuple[str, ...],
    position: PromptDependencyPosition,
    instruction_utf8_sha256_or_null: str | None,
) -> str:
    return _sha256_digest(
        _canonical_json_bytes(
            _normalized_payload(
                required_binding_refs=required_binding_refs,
                optional_binding_refs=optional_binding_refs,
                position=position,
                instruction_utf8_sha256_or_null=instruction_utf8_sha256_or_null,
            )
        )
    )


def _build_compiler_prompt_dependency_contract(
    *,
    required_binding_refs: tuple[str, ...],
    optional_binding_refs: tuple[str, ...],
    position: PromptDependencyPosition,
    instruction: str | None,
    source_origin_key: str,
    source_workflow_bytes: bytes,
) -> CompilerPromptDependencyContract:
    """Build one validated contract from the lowering owner's typed inputs."""

    if not isinstance(source_workflow_bytes, bytes):
        raise TypeError("source_workflow_bytes must be bytes")
    if instruction is not None and not isinstance(instruction, str):
        raise TypeError("instruction must be a string or None")
    instruction_digest = (
        _sha256_digest(instruction.encode("utf-8")) if instruction is not None else None
    )
    normalized_digest = _normalized_contract_sha256(
        required_binding_refs=required_binding_refs,
        optional_binding_refs=optional_binding_refs,
        position=position,
        instruction_utf8_sha256_or_null=instruction_digest,
    )
    return CompilerPromptDependencyContract(
        schema=COMPILER_PROMPT_DEPENDENCY_CONTRACT_SCHEMA,
        origin_kind=(
            PromptDependencyOriginKind.WORKFLOW_LISP_PROVIDER_RESULT_PROMPT_DEPENDENCIES
        ),
        path_interpretation=PromptDependencyPathInterpretation.EXACT,
        evidence_required=True,
        source_origin_key=source_origin_key,
        source_workflow_sha256=_sha256_digest(source_workflow_bytes),
        required_binding_refs=required_binding_refs,
        optional_binding_refs=optional_binding_refs,
        position=position,
        instruction_utf8_sha256_or_null=instruction_digest,
        normalized_contract_sha256=normalized_digest,
    )


def _validate_refs(name: str, refs: object) -> tuple[str, ...]:
    if not isinstance(refs, tuple):
        raise TypeError(f"{name} must be a tuple")
    if any(not isinstance(ref, str) or not ref for ref in refs):
        raise ValueError(f"{name} must contain only non-empty binding refs")
    return refs


def _validate_contract_fields(contract: CompilerPromptDependencyContract) -> None:
    if contract.schema != COMPILER_PROMPT_DEPENDENCY_CONTRACT_SCHEMA:
        raise ValueError("unsupported compiler prompt dependency contract schema")
    if not isinstance(contract.origin_kind, PromptDependencyOriginKind):
        raise TypeError("origin_kind must be PromptDependencyOriginKind")
    if not isinstance(contract.path_interpretation, PromptDependencyPathInterpretation):
        raise TypeError("path_interpretation must be PromptDependencyPathInterpretation")
    if contract.evidence_required is not True:
        raise ValueError("evidence_required must be true")
    if not isinstance(contract.source_origin_key, str) or not contract.source_origin_key:
        raise ValueError("source_origin_key must be non-empty")
    if not isinstance(contract.source_workflow_sha256, str) or not _SHA256_RE.fullmatch(
        contract.source_workflow_sha256
    ):
        raise ValueError("source_workflow_sha256 must be sha256:<lowercase-hex>")
    required = _validate_refs("required_binding_refs", contract.required_binding_refs)
    optional = _validate_refs("optional_binding_refs", contract.optional_binding_refs)
    if not required and not optional:
        raise ValueError("at least one prompt dependency binding ref is required")
    if not isinstance(contract.position, PromptDependencyPosition):
        raise TypeError("position must be PromptDependencyPosition")
    instruction_digest = contract.instruction_utf8_sha256_or_null
    if instruction_digest is not None and (
        not isinstance(instruction_digest, str) or not _SHA256_RE.fullmatch(instruction_digest)
    ):
        raise ValueError(
            "instruction_utf8_sha256_or_null must be sha256:<lowercase-hex> or null"
        )
    expected = _normalized_contract_sha256(
        required_binding_refs=required,
        optional_binding_refs=optional,
        position=contract.position,
        instruction_utf8_sha256_or_null=instruction_digest,
    )
    if contract.normalized_contract_sha256 != expected:
        raise ValueError("normalized_contract_sha256 does not match contract fields")


def validate_compiler_prompt_dependency_contract(
    contract: CompilerPromptDependencyContract,
) -> CompilerPromptDependencyContract:
    """Validate a typed contract without coercing mappings or enum strings."""

    if type(contract) is not CompilerPromptDependencyContract:
        raise TypeError("expected CompilerPromptDependencyContract")
    _validate_contract_fields(contract)
    return contract


def serialize_compiler_prompt_dependency_contract(
    contract: CompilerPromptDependencyContract,
) -> dict[str, Any]:
    """Serialize one validated contract to its closed wire representation."""

    contract = validate_compiler_prompt_dependency_contract(contract)
    return {
        "schema": contract.schema,
        "origin_kind": contract.origin_kind.value,
        "path_interpretation": contract.path_interpretation.value,
        "evidence_required": contract.evidence_required,
        "source_origin_key": contract.source_origin_key,
        "source_workflow_sha256": contract.source_workflow_sha256,
        "required_binding_refs": list(contract.required_binding_refs),
        "optional_binding_refs": list(contract.optional_binding_refs),
        "position": contract.position.value,
        "instruction_utf8_sha256_or_null": contract.instruction_utf8_sha256_or_null,
        "normalized_contract_sha256": contract.normalized_contract_sha256,
    }


def canonical_compiler_prompt_dependency_contract_json(
    contract: CompilerPromptDependencyContract,
) -> str:
    """Return compact canonical ASCII JSON with no trailing newline."""

    return _canonical_json_bytes(
        serialize_compiler_prompt_dependency_contract(contract)
    ).decode("ascii")
