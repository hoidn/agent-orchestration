"""Publish a known-variant union terminal plainly inside a normalized match case.

From target 2.29 a union literal that ends a match arm lowers to a pure
projection whose outputs carry union-boundary metadata: a variant field may be
read only under a proof that the projection's own discriminant selected that
variant. The case's `result_bundle` re-materializes the union from the
discriminant, shared and active-variant fields, and nothing proves the
projection's discriminant, so shared validation rejects the read
(`workflow_boundary_type_invalid`). The variant is known at compile time, so
from target 2.33 the projection publishes only the fields the bundle reads, as
plain artifacts that are always present. Targets 2.29-2.32 keep their
lowering.
"""

from __future__ import annotations

from typing import Any

from ..syntax import target_dsl_supports_generic_unions


def publish_known_variant_terminal_plainly(
    case_steps: list[dict[str, Any]],
    *,
    terminal_step_name: str,
    variant_name: str,
    target_dsl_version: str | None,
) -> None:
    """Narrow the arm's terminal projection to the fields of `variant_name`, in place."""

    if not target_dsl_supports_generic_unions(target_dsl_version or ""):
        return
    step = next(
        (
            candidate
            for candidate in case_steps
            if candidate.get("name") == terminal_step_name and "pure_projection" in candidate
        ),
        None,
    )
    if step is None:
        return
    contracts = step["pure_projection"]["output_contracts"]
    if not any(_field_role(contract) == "variant" for contract in contracts.values()):
        return
    published = {name for name, contract in contracts.items() if _is_published(contract, variant_name)}
    step["pure_projection"]["output_contracts"] = {
        name: _without_projection(contract) for name, contract in contracts.items() if name in published
    }
    step["output_bundle"]["fields"] = [
        _without_projection(field) for field in step["output_bundle"]["fields"] if field["name"] in published
    ]


def _field_role(contract: dict[str, Any]) -> str | None:
    projection = contract.get("projection")
    return projection.get("field_role") if isinstance(projection, dict) else None


def _is_published(contract: dict[str, Any], variant_name: str) -> bool:
    role = _field_role(contract)
    if role is None or role in {"discriminant", "shared"}:
        return True
    return variant_name in contract["projection"].get("active_variants", ())


def _without_projection(definition: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in definition.items() if key != "projection"}
