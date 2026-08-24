"""Authoring provenance validation for the prompt output contract (Task 7).

A narrowly named sibling of ``orchestrator.prompt_contract``: the closed
``scaffold_output_contract.v1`` authoring forms (``default`` / ``exact`` /
``inferred``) and the usage/cost record validation, split out to keep the
pure contract module within the 500-line production cap. ``prompt_contract``
re-exports :func:`validate_authoring` and :func:`output_contract_document`
as its public facade; tests import from ``orchestrator.prompt_contract``.

The inferred form carries the output-request digest, the internal inference
provider, model, session id, and a closed finite non-negative usage record.
Unknown keys, booleans-as-integers, negatives, and NaN/Inf fail at every
level; authoring is manifest-bound but excluded from semantic identity.
"""

from __future__ import annotations

import math

from orchestrator.prompt_contract import (
    SCHEMA_VERSION,
    PromptContractError,
    SemanticContract,
    _require_sha256,
    semantic_contract_object,
)

__all__ = ["output_contract_document", "validate_authoring"]

_INFERENCE_PROVIDER = "omp_conf_inference"
_USAGE_KEYS = frozenset(
    {"input", "output", "cacheRead", "cacheWrite", "totalTokens", "cost"}
)
_USAGE_COST_KEYS = frozenset(
    {"input", "output", "cacheRead", "cacheWrite", "total"}
)


def _require_nonempty(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise PromptContractError(f"{context} must be a non-empty string")
    return value


def _require_nonnegative_int(value: object, context: str) -> int:
    if type(value) is not int:
        raise PromptContractError(f"{context} must be an integer")
    if value < 0:
        raise PromptContractError(f"{context} must be non-negative")
    return value


def _require_finite_number(value: object, context: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise PromptContractError(f"{context} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise PromptContractError(f"{context} must be finite and non-negative")
    return number


def _validate_usage(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _USAGE_KEYS:
        raise PromptContractError("usage must be exactly the closed usage keys")
    for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens"):
        _require_nonnegative_int(value[key], f"usage.{key}")
    cost = value["cost"]
    if not isinstance(cost, dict) or set(cost) != _USAGE_COST_KEYS:
        raise PromptContractError("usage.cost must be exactly the closed cost keys")
    for key in ("input", "output", "cacheRead", "cacheWrite", "total"):
        _require_finite_number(cost[key], f"usage.cost.{key}")
    return {"usage": value}


def validate_authoring(value: object) -> dict[str, object]:
    """Validate one closed authoring provenance object.

    ``{mode:"default"}`` and ``{mode:"exact"}`` are the simple forms; the
    inferred form carries output-request digest, internal inference provider,
    model, session id, and a closed finite non-negative usage record. Unknown
    keys and booleans-as-integers fail at every level.
    """
    if not isinstance(value, dict):
        raise PromptContractError("authoring must be an object")
    mode = value.get("mode")
    if mode == "default" or mode == "exact":
        if set(value) != {"mode"}:
            raise PromptContractError(
                f"authoring mode {mode!r} must be exactly {{mode}}"
            )
        return {"mode": mode}
    if mode == "inferred":
        expected = frozenset(
            {
                "mode",
                "output_request_sha256",
                "provider",
                "model",
                "session_id",
                "usage",
            }
        )
        if set(value) != expected:
            raise PromptContractError(
                "inferred authoring must be exactly the closed inferred keys"
            )
        provider = _require_nonempty(value["provider"], "authoring.provider")
        if provider != _INFERENCE_PROVIDER:
            raise PromptContractError(
                "inferred authoring provider must be omp_conf_inference"
            )
        return {
            "mode": "inferred",
            "output_request_sha256": _require_sha256(
                value["output_request_sha256"], "authoring.output_request_sha256"
            ),
            "provider": provider,
            "model": _require_nonempty(value["model"], "authoring.model"),
            "session_id": _require_nonempty(
                value["session_id"], "authoring.session_id"
            ),
            **_validate_usage(value["usage"]),
        }
    raise PromptContractError(f"unknown authoring mode {mode!r}")


def output_contract_document(
    contract: SemanticContract, authoring: object
) -> dict[str, object]:
    """The closed ``scaffold_output_contract.v1`` document for a contract.

    ``semantic`` is exactly the normalized contract; ``authoring`` is exactly
    one of the validated closed provenance forms. Unknown keys fail at every
    level; authoring is bound by the scaffold manifest but excluded from
    semantic identity.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "semantic": semantic_contract_object(contract),
        "authoring": validate_authoring(authoring),
    }
