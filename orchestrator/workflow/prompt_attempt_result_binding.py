"""Pure construction of one provider-attempt/result debug locator."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from .prompt_dependency_evidence import (
    FRAGMENT_SUCCESS_SCHEMA_V2,
    PublicationResult,
    canonical_record_bytes,
    evidence_relative_path,
)
from .prompt_identity import PROMPT_ATTEMPT_IDENTITY_VERSION
from .provider_attempts import (
    ProviderAttemptScope,
    validate_provider_attempt_allocations,
)


PROMPT_ATTEMPT_RESULT_BINDING_SCHEMA = (
    "workflow_prompt_attempt_result_binding.v1"
)
PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY = (
    "prompt_attempt_result_binding"
)

_BINDING_KEYS = {
    "schema_version",
    "scope_sha256",
    "attempt_ordinal",
    "evidence_relative_path",
    "evidence_file_sha256",
    "record_kind",
}


class PromptAttemptResultBindingError(ValueError):
    """Raised when retained authorities cannot prove one exact binding."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise PromptAttemptResultBindingError(code, message)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _canonical_relative_path(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\x00" in value
    ):
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and path != PurePosixPath(".")
        and ".." not in path.parts
        and str(path) == value
    )


def validate_prompt_attempt_result_binding(
    value: Any,
) -> dict[str, Any]:
    """Validate and normalize the closed persisted locator."""

    if not isinstance(value, Mapping) or set(value) != _BINDING_KEYS:
        _fail(
            "judgment_result_binding_invalid",
            "binding must be a closed six-field object",
        )
    if (
        value["schema_version"]
        != PROMPT_ATTEMPT_RESULT_BINDING_SCHEMA
        or not _is_sha256(value["scope_sha256"])
        or isinstance(value["attempt_ordinal"], bool)
        or not isinstance(value["attempt_ordinal"], int)
        or value["attempt_ordinal"] < 1
        or not _canonical_relative_path(
            value["evidence_relative_path"]
        )
        or not _is_sha256(value["evidence_file_sha256"])
        or value["record_kind"] != "prompt_snapshot"
    ):
        _fail(
            "judgment_result_binding_invalid",
            "binding field value is invalid",
        )
    return dict(value)


def is_prompt_attempt_result_binding_eligible(
    *,
    direct_fragment_call: bool,
    compiled_fragment_contract_present: bool,
    delivery: str | None,
    prompt_attempt_identity_schema_version: str | None,
    validated_result_ready_for_commit: bool,
) -> bool:
    """Apply the source-free eligibility prefix before retained validation."""

    return (
        direct_fragment_call is True
        and compiled_fragment_contract_present is True
        and delivery in {None, "composed"}
        and prompt_attempt_identity_schema_version
        == PROMPT_ATTEMPT_IDENTITY_VERSION
        and validated_result_ready_for_commit is True
    )


def _debug_copy(debug: Mapping[str, Any] | None) -> dict[str, Any]:
    if debug is None:
        return {}
    if not isinstance(debug, Mapping):
        _fail(
            "judgment_result_binding_invalid",
            "result debug must be an object",
        )
    return dict(debug)


def _publication_schema(
    publication: PublicationResult | None,
) -> str:
    if publication is None:
        _fail(
            "judgment_result_binding_missing",
            "eligible result has no retained publication",
        )
    if not isinstance(publication, PublicationResult):
        _fail(
            "judgment_result_binding_invalid",
            "retained publication has the wrong type",
        )
    if not isinstance(publication.payload, bytes):
        _fail(
            "judgment_result_evidence_invalid",
            "retained publication payload is not bytes",
        )
    try:
        record = json.loads(publication.payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromptAttemptResultBindingError(
            "judgment_result_evidence_invalid",
            "retained publication payload is not JSON",
        ) from exc
    if not isinstance(record, Mapping):
        _fail(
            "judgment_result_evidence_invalid",
            "retained publication payload is not an object",
        )
    schema = record.get("schema")
    if not isinstance(schema, str):
        _fail(
            "judgment_result_evidence_invalid",
            "retained publication evidence schema is missing",
        )
    return schema


def _validated_exact_allocation(
    *,
    root_provider_attempt_allocations: Mapping[str, Any] | None,
    scope: ProviderAttemptScope,
    attempt_ordinal: int,
) -> dict[str, Any]:
    if root_provider_attempt_allocations is None:
        _fail(
            "judgment_result_binding_missing",
            "root provider-attempt allocator is missing",
        )
    if not isinstance(root_provider_attempt_allocations, Mapping):
        _fail(
            "judgment_result_binding_invalid",
            "root provider-attempt allocator is not an object",
        )
    raw_entry = root_provider_attempt_allocations.get(scope.key)
    if raw_entry is None:
        _fail(
            "judgment_result_scope_mismatch",
            "root allocator has no entry for the retained scope",
        )
    if not isinstance(raw_entry, Mapping):
        _fail(
            "judgment_result_binding_invalid",
            "root allocator scope entry is invalid",
        )
    try:
        allocations = validate_provider_attempt_allocations(
            root_provider_attempt_allocations
        )
    except (TypeError, ValueError) as exc:
        raise PromptAttemptResultBindingError(
            "judgment_result_binding_invalid",
            "root provider-attempt allocator is invalid",
        ) from exc
    entry = allocations.get(scope.key)
    if entry is None or entry["scope"] != scope.to_dict():
        _fail(
            "judgment_result_scope_mismatch",
            "allocator scope disagrees with the retained scope",
        )
    if attempt_ordinal > entry["last_allocated_ordinal"]:
        _fail(
            "judgment_result_attempt_mismatch",
            "successful attempt ordinal was not allocated",
        )
    return entry


def _validate_evidence(
    *,
    publication: PublicationResult,
    scope: ProviderAttemptScope,
    attempt_ordinal: int,
    compiler_fragment_identity_schema_version: str | None,
) -> None:
    if not isinstance(
        compiler_fragment_identity_schema_version,
        str,
    ):
        _fail(
            "judgment_result_evidence_invalid",
            "compiler fragment identity authority is missing",
        )
    expected_path = str(
        evidence_relative_path(scope, attempt_ordinal)
    )
    publication_path = str(publication.relative_path)
    if (
        publication.record_kind != "prompt_snapshot"
        or publication_path != expected_path
        or not _is_sha256(publication.file_sha256)
        or _sha256(publication.payload) != publication.file_sha256
    ):
        _fail(
            "judgment_result_evidence_invalid",
            "publication path, digest, or kind is contradictory",
        )
    try:
        canonical = canonical_record_bytes(
            json.loads(publication.payload),
            compiler_fragment_identity_schema_version=(
                compiler_fragment_identity_schema_version
            ),
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise PromptAttemptResultBindingError(
            "judgment_result_evidence_invalid",
            "functional-v2 evidence is invalid",
        ) from exc
    if canonical != publication.payload:
        _fail(
            "judgment_result_evidence_invalid",
            "functional-v2 evidence bytes are noncanonical",
        )
    record = json.loads(canonical)
    identity = record.get("prompt_attempt_identity")
    if (
        record.get("schema") != FRAGMENT_SUCCESS_SCHEMA_V2
        or record.get("record_kind") != "prompt_snapshot"
        or not isinstance(identity, Mapping)
        or identity.get("schema_version")
        != PROMPT_ATTEMPT_IDENTITY_VERSION
    ):
        _fail(
            "judgment_result_evidence_invalid",
            "evidence is not exact functional-v2 with identity-v1",
        )
    attempt = record.get("attempt")
    if not isinstance(attempt, Mapping):
        _fail(
            "judgment_result_evidence_invalid",
            "evidence attempt authority is missing",
        )
    if (
        attempt.get("scope_sha256") != scope.key
        or attempt.get("scope") != scope.to_dict()
    ):
        _fail(
            "judgment_result_scope_mismatch",
            "evidence attempt scope disagrees with retained scope",
        )
    if attempt.get("ordinal") != attempt_ordinal:
        _fail(
            "judgment_result_attempt_mismatch",
            "evidence attempt ordinal disagrees with successful attempt",
        )


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def attach_prompt_attempt_result_binding(
    debug: Mapping[str, Any] | None,
    *,
    direct_fragment_call: bool,
    compiled_fragment_contract_present: bool,
    delivery: str | None,
    prompt_attempt_identity_schema_version: str | None,
    compiler_fragment_identity_schema_version: str | None,
    validated_result_ready_for_commit: bool,
    scope: ProviderAttemptScope | None = None,
    attempt_ordinal: int | None = None,
    root_provider_attempt_allocations: Mapping[str, Any] | None = None,
    publication: PublicationResult | None = None,
) -> dict[str, Any]:
    """Attach one proven locator while preserving other debug owners."""

    projected_debug = _debug_copy(debug)
    if not is_prompt_attempt_result_binding_eligible(
        direct_fragment_call=direct_fragment_call,
        compiled_fragment_contract_present=(
            compiled_fragment_contract_present
        ),
        delivery=delivery,
        prompt_attempt_identity_schema_version=(
            prompt_attempt_identity_schema_version
        ),
        validated_result_ready_for_commit=(
            validated_result_ready_for_commit
        ),
    ):
        return projected_debug

    if PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY in projected_debug:
        _fail(
            "judgment_result_binding_ambiguous",
            "result debug already contains a binding",
        )
    evidence_schema = _publication_schema(publication)
    if evidence_schema != FRAGMENT_SUCCESS_SCHEMA_V2:
        return projected_debug
    if scope is None or attempt_ordinal is None:
        _fail(
            "judgment_result_binding_missing",
            "eligible result is missing retained scope or ordinal",
        )
    if not isinstance(scope, ProviderAttemptScope):
        _fail(
            "judgment_result_binding_invalid",
            "retained scope has the wrong type",
        )
    if (
        isinstance(attempt_ordinal, bool)
        or not isinstance(attempt_ordinal, int)
        or attempt_ordinal < 1
    ):
        _fail(
            "judgment_result_binding_invalid",
            "retained attempt ordinal is invalid",
        )
    assert isinstance(publication, PublicationResult)
    entry = _validated_exact_allocation(
        root_provider_attempt_allocations=(
            root_provider_attempt_allocations
        ),
        scope=scope,
        attempt_ordinal=attempt_ordinal,
    )
    if (
        entry.get("prompt_fragment_identity_schema_version")
        != compiler_fragment_identity_schema_version
    ):
        _fail(
            "judgment_result_evidence_invalid",
            "allocator fragment identity authority disagrees",
        )
    _validate_evidence(
        publication=publication,
        scope=scope,
        attempt_ordinal=attempt_ordinal,
        compiler_fragment_identity_schema_version=(
            compiler_fragment_identity_schema_version
        ),
    )
    binding = validate_prompt_attempt_result_binding(
        {
            "schema_version": PROMPT_ATTEMPT_RESULT_BINDING_SCHEMA,
            "scope_sha256": scope.key,
            "attempt_ordinal": attempt_ordinal,
            "evidence_relative_path": str(publication.relative_path),
            "evidence_file_sha256": publication.file_sha256,
            "record_kind": publication.record_kind,
        }
    )
    projected_debug[PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY] = binding
    return projected_debug


__all__ = [
    "PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY",
    "PROMPT_ATTEMPT_RESULT_BINDING_SCHEMA",
    "PromptAttemptResultBindingError",
    "attach_prompt_attempt_result_binding",
    "is_prompt_attempt_result_binding_eligible",
    "validate_prompt_attempt_result_binding",
]
