"""Specialized compiler contract for generated ``run-ref`` result carriers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.workflow.run_ref.contracts import canonical_sha256

from .contracts import is_transportable_result_type
from .lowering.pure_projection import (
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

    descriptor: Mapping[str, Any]
    digest: str
    type_ref: RecordTypeRef


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
        descriptor=descriptor,
        digest=canonical_sha256(descriptor),
        type_ref=result_type_ref,
    )
