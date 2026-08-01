"""Specialized compiler contract for generated ``run-ref`` result carriers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
import json
from typing import Any

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)

from .contracts import is_transportable_result_type
from .normalized_type_descriptor import (
    compiler_normalized_type_descriptor,
    validate_compiler_normalized_type_descriptor,
)
from .type_env import FrontendTypeEnvironment, RecordTypeRef
from .typecheck_run_ref import compiler_run_ref_fixed_types


RUN_REF_RESULT_CONTRACT_SCHEMA = "run_ref_result_contract.v1"
_GENERATED_RESULT_NAME = re.compile(r"RunRefResult\$[0-9a-f]{16}\Z")
_RESULT_FIELD_NAMES = ("value", "workspace_delta", "accounting")


@dataclass(frozen=True)
class GeneratedRunRefResultContract:
    """Content-addressed normalized contract for one generated result carrier."""

    _descriptor_json: bytes = field(repr=False)
    digest: str
    type_ref: RecordTypeRef

    def __post_init__(self) -> None:
        if type(self._descriptor_json) is not bytes:
            raise ValueError("run-ref result descriptor authority must be bytes")
        try:
            decoded = json.loads(self._descriptor_json)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            raise ValueError(
                "run-ref result descriptor authority must be valid JSON"
            ) from exc
        if (
            not isinstance(decoded, dict)
            or set(decoded) != {"schema", "envelope"}
            or decoded.get("schema") != RUN_REF_RESULT_CONTRACT_SCHEMA
            or not isinstance(decoded.get("envelope"), dict)
        ):
            raise ValueError("run-ref result descriptor authority has invalid shape")
        if canonical_json_bytes(decoded) != self._descriptor_json:
            raise ValueError(
                "run-ref result descriptor authority must use canonical JSON"
            )
        if canonical_sha256(decoded) != self.digest:
            raise ValueError("run-ref result descriptor digest mismatch")

    @property
    def descriptor(self) -> dict[str, Any]:
        """Return a defensive copy of the canonical descriptor."""

        return json.loads(self._descriptor_json)


def _require_generated_result_shape(result_type_ref: RecordTypeRef) -> None:
    if _GENERATED_RESULT_NAME.fullmatch(result_type_ref.name) is None:
        raise ValueError(
            "run-ref result contract requires a generated RunRefResult$ type"
        )
    if result_type_ref.definition.name != result_type_ref.name:
        raise ValueError("run-ref result type and definition names must match")
    field_names = tuple(
        field.name for field in result_type_ref.definition.fields
    )
    if field_names != _RESULT_FIELD_NAMES:
        raise ValueError(
            "run-ref result fields must be exactly value, workspace_delta, accounting"
        )
    if tuple(result_type_ref.field_types) != _RESULT_FIELD_NAMES:
        raise ValueError(
            "run-ref result field types must match the exact ordered definition"
        )


def derive_run_ref_result_contract(
    result_type_ref: RecordTypeRef,
    *,
    type_env: FrontendTypeEnvironment,
) -> GeneratedRunRefResultContract:
    """Derive and validate one exact compiler-owned ``run-ref`` result contract."""

    if not isinstance(result_type_ref, RecordTypeRef):
        raise ValueError("run-ref result contract requires a record type")
    _require_generated_result_shape(result_type_ref)

    value_type = result_type_ref.field_types["value"]
    workspace_delta_type = result_type_ref.field_types["workspace_delta"]
    accounting_type = result_type_ref.field_types["accounting"]
    if not is_transportable_result_type(value_type):
        raise ValueError("run-ref result value type must be transportable")
    if not isinstance(workspace_delta_type, RecordTypeRef) or (
        workspace_delta_type.name != "WorkspaceDelta"
    ):
        raise ValueError(
            "run-ref result workspace_delta must use WorkspaceDelta"
        )
    if not isinstance(accounting_type, RecordTypeRef) or (
        accounting_type.name != "RunRefAccounting"
    ):
        raise ValueError(
            "run-ref result accounting must use RunRefAccounting"
        )

    envelope = compiler_normalized_type_descriptor(
        result_type_ref,
        type_env=type_env,
    )
    validate_compiler_normalized_type_descriptor(
        envelope,
        context="run_ref_result_contract.envelope",
    )

    expected_fixed = dict(compiler_run_ref_fixed_types(type_env))
    expected_workspace_delta = compiler_normalized_type_descriptor(
        expected_fixed["WorkspaceDelta"],
        type_env=type_env,
    )
    expected_accounting = compiler_normalized_type_descriptor(
        expected_fixed["RunRefAccounting"],
        type_env=type_env,
    )
    if envelope["fields"][1]["type"] != expected_workspace_delta:
        raise ValueError(
            "run-ref result workspace_delta does not match the fixed compiler schema"
        )
    if envelope["fields"][2]["type"] != expected_accounting:
        raise ValueError(
            "run-ref result accounting does not match the fixed compiler schema"
        )

    descriptor = {
        "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
        "envelope": envelope,
    }
    return GeneratedRunRefResultContract(
        _descriptor_json=canonical_json_bytes(descriptor),
        digest=canonical_sha256(descriptor),
        type_ref=result_type_ref,
    )
