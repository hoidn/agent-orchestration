"""Closed ordinary-provider context configuration validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .provider_phased_delivery.models import partition_provider_call_policy
from .type_descriptor import (
    transport_descriptor_for_schema,
    transport_schema_for_descriptor,
    validate_compiler_normalized_type_descriptor,
)


_PROVIDER_CONTEXT_KEYS = frozenset({"input", "capture", "result_descriptor"})


def _target_at_least(value: str, minimum: tuple[int, int]) -> bool:
    try:
        parts = tuple(int(part) for part in value.split("."))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("provider context target DSL version is invalid") from exc
    return parts >= minimum


def validate_provider_context_config(
    value: Any,
    *,
    step_kind: str,
    target_dsl_version: str,
    provider_call_policy: Mapping[str, object] | None = None,
    executable: bool = False,
) -> Mapping[str, Any]:
    """Validate the closed persisted provider-context map without runtime authority."""

    if step_kind != "provider":
        raise ValueError("provider context requires an ordinary provider step")
    if not _target_at_least(target_dsl_version, (2, 31)):
        raise ValueError("provider context requires target DSL 2.31")
    if not isinstance(value, Mapping):
        raise ValueError("provider context must be a mapping")
    if not value or set(value) - _PROVIDER_CONTEXT_KEYS:
        raise ValueError("provider context has unknown keys or is empty")

    has_input = "input" in value
    has_capture = "capture" in value
    has_descriptor = "result_descriptor" in value
    if has_input:
        input_value = value["input"]
        if (
            not isinstance(input_value, Mapping)
            or set(input_value) != {"ref"}
        ):
            raise ValueError("provider context input must be {ref: String}")
        ref = input_value["ref"]
        if executable:
            from .executable_ir import BoundAddress

            if not isinstance(ref, BoundAddress):
                raise ValueError("provider context input requires a bound address")
        elif not isinstance(ref, str) or not ref:
            raise ValueError("provider context input must be {ref: String}")
    if has_capture and value["capture"] != "portable":
        raise ValueError("provider context capture must be portable")
    if has_descriptor != has_capture:
        raise ValueError(
            "provider context result_descriptor is required exactly with capture"
        )
    if has_descriptor:
        validate_compiler_normalized_type_descriptor(
            value["result_descriptor"],
            context="provider context result_descriptor",
        )
    try:
        _provider_policy, runtime_policy = partition_provider_call_policy(
            {} if provider_call_policy is None else provider_call_policy
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("provider context call policy is invalid") from exc
    if runtime_policy is not None and runtime_policy.delivery == "phased":
        raise ValueError("provider context is incompatible with phased delivery")
    return value


def validate_capture_output_contract(
    config: Mapping[str, Any] | None,
    output_bundle: Any,
    variant_output: Any = None,
) -> None:
    """Require capture to consume one already-validated, complete model value."""

    if config is None or "capture" not in config:
        return
    fields = output_bundle.get("fields") if isinstance(output_bundle, Mapping) else None
    if (
        variant_output is not None
        or not isinstance(fields, Sequence)
        or isinstance(fields, (str, bytes))
        or len(fields) != 1
        or not isinstance(fields[0], Mapping)
    ):
        raise ValueError("capture output contract requires one root __result__ field")
    field = fields[0]
    if (
        field.get("name") != "__result__"
        or field.get("json_pointer") != ""
        or field.get("required", True) is not True
        or "projection" in field
    ):
        raise ValueError("capture output contract requires a mandatory, unprojected root")
    try:
        actual = transport_schema_for_descriptor(
            transport_descriptor_for_schema(field), allow_nested_structures=True,
        )
        expected = transport_schema_for_descriptor(
            config.get("result_descriptor"), allow_nested_structures=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("capture output contract has an invalid transport schema") from exc
    if actual != expected:
        raise ValueError("capture output contract disagrees with result_descriptor")


def capture_artifact_contracts(config: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Derive the two runtime-owned outputs; the model bundle still describes T."""

    if config is None or "capture" not in config:
        return None
    from orchestrator.providers.portable_context import PORTABLE_CONTEXT_V1_DESCRIPTOR

    return {
        name: transport_schema_for_descriptor(descriptor, allow_nested_structures=True)
        for name, descriptor in (
            ("result", config["result_descriptor"]),
            ("context", PORTABLE_CONTEXT_V1_DESCRIPTOR),
        )
    }


__all__ = [
    "capture_artifact_contracts", "validate_capture_output_contract",
    "validate_provider_context_config",
]
