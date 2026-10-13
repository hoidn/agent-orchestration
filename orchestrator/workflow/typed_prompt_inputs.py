"""Source-free typed prompt input validation and deterministic rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow.prompt_fragment_contract import (
    CompilerPromptAttemptBindingPlan,
    validate_typed_prompt_value_source,
)
from orchestrator.workflow.prompting import (
    PromptFragmentRenderResult,
    validate_prompt_fragment_render_trace,
)
from orchestrator.workflow.view_renderer import (
    VIEW_RENDERER_SCHEMA_VERSION,
    ViewRendererError,
    render_view,
    resolve_view_renderer,
    view_bytes_digest,
    view_evidence_key,
)


TYPED_PROMPT_INPUT_SCHEMA_VERSION = "workflow_lisp_typed_prompt_input.v1"


TYPED_PROMPT_INPUT_EVIDENCE_SCHEMA_VERSION = "workflow_lisp_typed_prompt_input_evidence.v1"


def normalize_typed_prompt_input_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one lowered typed prompt-input entry."""

    normalized = dict(entry)
    if normalized.get("schema_version") != TYPED_PROMPT_INPUT_SCHEMA_VERSION:
        raise ValueError("typed_prompt_input_schema_invalid: schema_version is required")
    for field_name in (
        "binding_name",
        "value_type_name",
        "source_map_origin_key",
    ):
        _require_non_empty_string(normalized.get(field_name), field_name)
    has_u0_row = "u0_row_id" in normalized
    has_c0_row = "c0_row_id" in normalized
    if has_u0_row != has_c0_row:
        raise ValueError(
            "typed_prompt_input_schema_invalid: "
            "u0_row_id and c0_row_id must be supplied together"
        )
    if has_u0_row:
        normalized["u0_row_id"] = _require_non_empty_string(
            normalized.get("u0_row_id"),
            "u0_row_id",
        )
        normalized["c0_row_id"] = _require_non_empty_string(
            normalized.get("c0_row_id"),
            "c0_row_id",
        )
    if not isinstance(normalized.get("value_source"), Mapping):
        raise ValueError("typed_prompt_input_schema_invalid: value_source is required")
    renderer = normalized.get("renderer")
    if not isinstance(renderer, Mapping):
        raise ValueError("typed_prompt_input_schema_invalid: renderer is required")
    renderer_id = _require_non_empty_string(renderer.get("renderer_id"), "renderer.renderer_id")
    renderer_version = renderer.get("renderer_version")
    if not isinstance(renderer_version, int):
        raise ValueError("typed_prompt_input_schema_invalid: renderer.renderer_version is required")
    accepted_shape = _require_non_empty_string(
        renderer.get("accepted_shape"),
        "renderer.accepted_shape",
    )
    try:
        descriptor = resolve_view_renderer(renderer_id, renderer_version)
    except ViewRendererError as exc:
        raise ValueError(
            f"typed_prompt_input_renderer_unknown: {exc}"
        ) from exc
    if accepted_shape != descriptor.accepted_shape:
        raise ValueError(
            "typed_prompt_input_renderer_shape_mismatch: "
            f"renderer `{renderer_id}` expects `{descriptor.accepted_shape}`"
        )
    injection_order = normalized.get("injection_order")
    if not isinstance(injection_order, int) or injection_order < 0:
        raise ValueError("typed_prompt_input_schema_invalid: injection_order must be a non-negative integer")
    value_source = dict(cast_mapping(normalized["value_source"]))
    if value_source.get("kind") == "typed_union_projection":
        try:
            validate_typed_prompt_value_source(value_source)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"typed_prompt_input_schema_invalid: {exc}"
            ) from exc
        binding_source = value_source
    else:
        binding_source = _normalize_typed_prompt_input_binding_source(value_source)
    normalized["renderer"] = {
        "renderer_id": renderer_id,
        "renderer_version": renderer_version,
        "accepted_shape": accepted_shape,
    }
    normalized["binding_name"] = str(normalized["binding_name"])
    normalized["value_type_name"] = str(normalized["value_type_name"])
    normalized["source_map_origin_key"] = str(normalized["source_map_origin_key"])
    normalized["injection_order"] = injection_order
    normalized["value_source"] = binding_source
    return normalized


def typed_prompt_input_value_digest(value: Any) -> str:
    """Return one deterministic digest for one resolved typed prompt value."""

    if isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        try:
            payload = canonical_json_for_pure_value(value).encode("utf-8")
        except Exception as exc:
            raise ValueError(
                "typed_prompt_input_value_unavailable: resolved typed prompt input is not JSON-like"
            ) from exc
    return f"sha256:{sha256(payload).hexdigest()}"


def render_typed_prompt_input_blocks(
    rows: Sequence[tuple[str, str, int, Any]],
) -> tuple[str, tuple[bytes, ...]]:
    """Render labeled input blocks and return their original renderer bytes."""

    blocks: list[str] = []
    rendered_rows: list[bytes] = []
    for binding_name, renderer_id, renderer_version, value in rows:
        try:
            rendered_bytes = render_view(renderer_id, renderer_version, value)
        except ViewRendererError as exc:
            code = (
                "typed_prompt_input_renderer_shape_mismatch"
                if exc.code == "view_value_shape_invalid"
                else "typed_prompt_input_renderer_unknown"
            )
            raise ValueError(f"{code}: {exc}") from exc
        rendered_text = rendered_bytes.decode("utf-8").rstrip("\n")
        blocks.append(
            "\n".join((f"## Typed Prompt Input: {binding_name}", rendered_text))
        )
        rendered_rows.append(rendered_bytes)
    return "\n\n".join(blocks), tuple(rendered_rows)


def render_typed_prompt_inputs(
    entries: Sequence[Mapping[str, Any]],
    *,
    resolved_typed_values: Mapping[str, Any],
    workflow_name: str,
    step_id: str,
    fragment_render_result: PromptFragmentRenderResult | None = None,
    compiler_prompt_attempt_binding_plan: (
        CompilerPromptAttemptBindingPlan | None
    ) = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Render typed prompt-input blocks and structured runtime evidence."""

    fragment_owned = _fragment_trace_pair_present(
        fragment_render_result,
        compiler_prompt_attempt_binding_plan,
    )
    if fragment_owned:
        assert fragment_render_result is not None
        assert compiler_prompt_attempt_binding_plan is not None
        evidence_payloads = _expected_fragment_typed_evidence(
            entries,
            resolved_typed_values=resolved_typed_values,
            workflow_name=workflow_name,
            step_id=step_id,
            fragment_render_result=fragment_render_result,
            compiler_prompt_attempt_binding_plan=(
                compiler_prompt_attempt_binding_plan
            ),
        )
        validated_evidence = validate_typed_prompt_input_composition(
            entries,
            resolved_typed_values=resolved_typed_values,
            evidence=evidence_payloads,
            workflow_name=workflow_name,
            step_id=step_id,
            fragment_render_result=fragment_render_result,
            compiler_prompt_attempt_binding_plan=(
                compiler_prompt_attempt_binding_plan
            ),
        )
        return "", validated_evidence

    normalized_entries = _validated_composition_entries(
        entries,
        resolved_typed_values=resolved_typed_values,
    )
    render_rows: list[tuple[str, str, int, Any]] = []
    for entry in normalized_entries:
        binding_name = entry["binding_name"]
        if binding_name not in resolved_typed_values:
            raise ValueError(
                f"typed_prompt_input_value_unavailable: missing resolved typed value for `{binding_name}`"
            )
        renderer = entry["renderer"]
        render_rows.append(
            (
                binding_name,
                str(renderer["renderer_id"]),
                int(renderer["renderer_version"]),
                resolved_typed_values[binding_name],
            )
        )
    rendered_block, rendered_rows = render_typed_prompt_input_blocks(render_rows)
    evidence_payloads: list[dict[str, Any]] = []
    for entry, rendered_bytes in zip(normalized_entries, rendered_rows, strict=True):
        binding_name = entry["binding_name"]
        resolved_value = resolved_typed_values[binding_name]
        value_digest = typed_prompt_input_value_digest(resolved_value)
        renderer = entry["renderer"]
        evidence_payload = {
            "schema_version": TYPED_PROMPT_INPUT_EVIDENCE_SCHEMA_VERSION,
            "workflow_name": workflow_name,
            "step_id": step_id,
            "binding_name": binding_name,
            "renderer": dict(renderer),
            "value_type_name": entry["value_type_name"],
            "value_digest": value_digest,
            "rendered_bytes_digest": view_bytes_digest(rendered_bytes),
            "evidence_key": view_evidence_key(
                str(renderer["renderer_id"]),
                int(renderer["renderer_version"]),
                VIEW_RENDERER_SCHEMA_VERSION,
                value_digest,
            ),
            "source_map_origin_key": entry["source_map_origin_key"],
            "injection_order": entry["injection_order"],
            "request_field_evidence": _request_field_evidence_rows(
                entry=entry,
                resolved_value=resolved_value,
            ),
        }
        for row_field in ("u0_row_id", "c0_row_id"):
            if row_field in entry:
                evidence_payload[row_field] = entry[row_field]
        evidence_payloads.append(evidence_payload)
    validated_evidence = validate_typed_prompt_input_composition(
        normalized_entries,
        resolved_typed_values=resolved_typed_values,
        evidence=evidence_payloads,
        workflow_name=workflow_name,
        step_id=step_id,
    )
    return rendered_block, validated_evidence


def validate_typed_prompt_input_composition(
    entries: Sequence[Mapping[str, Any]],
    *,
    resolved_typed_values: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    workflow_name: str,
    step_id: str,
    fragment_render_result: PromptFragmentRenderResult | None = None,
    compiler_prompt_attempt_binding_plan: (
        CompilerPromptAttemptBindingPlan | None
    ) = None,
) -> list[dict[str, Any]]:
    """Validate the closed lowered/value/rendered-evidence correspondence."""

    fragment_owned = _fragment_trace_pair_present(
        fragment_render_result,
        compiler_prompt_attempt_binding_plan,
    )
    if fragment_owned:
        assert fragment_render_result is not None
        assert compiler_prompt_attempt_binding_plan is not None
        expected_rows = _expected_fragment_typed_evidence(
            entries,
            resolved_typed_values=resolved_typed_values,
            workflow_name=workflow_name,
            step_id=step_id,
            fragment_render_result=fragment_render_result,
            compiler_prompt_attempt_binding_plan=(
                compiler_prompt_attempt_binding_plan
            ),
        )
        return _validate_fragment_typed_evidence_rows(
            evidence,
            expected_rows=expected_rows,
        )

    normalized_entries = _validated_composition_entries(
        entries,
        resolved_typed_values=resolved_typed_values,
    )
    if len(evidence) != len(normalized_entries):
        raise ValueError(
            "typed_prompt_input_evidence_set_mismatch: "
            "evidence cardinality does not match lowered bindings"
        )

    validated: list[dict[str, Any]] = []
    for entry, raw_row in zip(normalized_entries, evidence, strict=True):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                "typed_prompt_input_evidence_set_mismatch: evidence rows must be mappings"
            )
        row = dict(raw_row)
        binding_name = entry["binding_name"]
        if row.get("binding_name") != binding_name:
            raise ValueError(
                "typed_prompt_input_evidence_set_mismatch: "
                "evidence order or binding identity does not match lowering"
            )
        resolved_value = resolved_typed_values[binding_name]
        renderer = entry["renderer"]
        try:
            rendered_bytes = render_view(
                str(renderer["renderer_id"]),
                int(renderer["renderer_version"]),
                resolved_value,
            )
        except ViewRendererError as exc:
            code = (
                "typed_prompt_input_renderer_shape_mismatch"
                if exc.code == "view_value_shape_invalid"
                else "typed_prompt_input_renderer_unknown"
            )
            raise ValueError(f"{code}: {exc}") from exc
        value_digest = typed_prompt_input_value_digest(resolved_value)
        expected = {
            "schema_version": TYPED_PROMPT_INPUT_EVIDENCE_SCHEMA_VERSION,
            "workflow_name": workflow_name,
            "step_id": step_id,
            "binding_name": binding_name,
            "renderer": dict(renderer),
            "value_type_name": entry["value_type_name"],
            "value_digest": value_digest,
            "rendered_bytes_digest": view_bytes_digest(rendered_bytes),
            "evidence_key": view_evidence_key(
                str(renderer["renderer_id"]),
                int(renderer["renderer_version"]),
                VIEW_RENDERER_SCHEMA_VERSION,
                value_digest,
            ),
            "source_map_origin_key": entry["source_map_origin_key"],
            "injection_order": entry["injection_order"],
            "request_field_evidence": _request_field_evidence_rows(
                entry=entry,
                resolved_value=resolved_value,
            ),
        }
        for row_field in ("u0_row_id", "c0_row_id"):
            if row_field in entry:
                expected[row_field] = entry[row_field]
            elif row_field in row:
                raise ValueError(
                    "typed_prompt_input_evidence_set_mismatch: "
                    f"unexpected profile lineage field `{row_field}`"
                )
        if set(row) != set(expected):
            raise ValueError(
                "typed_prompt_input_evidence_set_mismatch: "
                "evidence row fields do not match the closed evidence contract"
            )
        mismatches = [
            field_name
            for field_name, expected_value in expected.items()
            if row.get(field_name) != expected_value
        ]
        if mismatches:
            raise ValueError(
                "typed_prompt_input_evidence_set_mismatch: "
                "evidence row does not match rendered binding "
                f"`{binding_name}` ({', '.join(sorted(mismatches))})"
            )
        validated.append(row)
    return validated


def _fragment_trace_pair_present(
    fragment_render_result: PromptFragmentRenderResult | None,
    compiler_prompt_attempt_binding_plan: (
        CompilerPromptAttemptBindingPlan | None
    ),
) -> bool:
    if (
        fragment_render_result is None
        and compiler_prompt_attempt_binding_plan is None
    ):
        return False
    if (
        fragment_render_result is None
        or compiler_prompt_attempt_binding_plan is None
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "fragment render trace and binding plan must be paired"
        )
    return True


def _expected_fragment_typed_evidence(
    entries: Sequence[Mapping[str, Any]],
    *,
    resolved_typed_values: Mapping[str, Any],
    workflow_name: str,
    step_id: str,
    fragment_render_result: PromptFragmentRenderResult,
    compiler_prompt_attempt_binding_plan: CompilerPromptAttemptBindingPlan,
) -> list[dict[str, Any]]:
    """Build legacy evidence rows solely from one validated Q3 trace."""

    try:
        trace = validate_prompt_fragment_render_trace(
            fragment_render_result,
            compiler_prompt_attempt_binding_plan=(
                compiler_prompt_attempt_binding_plan
            ),
        )
        normalized_entries = _validated_composition_entries(
            entries,
            resolved_typed_values=resolved_typed_values,
        )
        typed_plan_rows = tuple(
            row
            for row in compiler_prompt_attempt_binding_plan.rows
            if row.slot_kind in {"value", "path"}
        )
        if tuple(
            entry["binding_name"] for entry in normalized_entries
        ) != tuple(row.slot_name for row in typed_plan_rows):
            raise ValueError(
                "typed carriers do not match fragment binding plan"
            )

        expected: list[dict[str, Any]] = []
        for entry, plan_row in zip(
            normalized_entries,
            typed_plan_rows,
            strict=True,
        ):
            renderer = entry["renderer"]
            if (
                plan_row.renderer is None
                or renderer["renderer_id"]
                != plan_row.renderer["renderer_id"]
                or renderer["renderer_version"]
                != plan_row.renderer["renderer_version"]
            ):
                raise ValueError(
                    "typed renderer does not match fragment binding plan"
                )
            rendered_slot_ordinal = plan_row.runtime_source["ordinal"]
            if (
                type(rendered_slot_ordinal) is not int
                or rendered_slot_ordinal < 0
                or rendered_slot_ordinal >= len(trace)
            ):
                raise ValueError(
                    "typed trace locator is outside the fragment trace"
                )
            trace_row = trace[rendered_slot_ordinal]
            binding_name = entry["binding_name"]
            resolved_value = resolved_typed_values[binding_name]
            value_digest = typed_prompt_input_value_digest(
                resolved_value
            )
            if (
                trace_row.slot_name != binding_name
                or trace_row.renderer
                != {
                    "renderer_id": renderer["renderer_id"],
                    "renderer_version": renderer["renderer_version"],
                }
                or trace_row.value_sha256 != value_digest
            ):
                raise ValueError(
                    "typed value does not match fragment render trace"
                )
            evidence_payload = {
                "schema_version": (
                    TYPED_PROMPT_INPUT_EVIDENCE_SCHEMA_VERSION
                ),
                "workflow_name": workflow_name,
                "step_id": step_id,
                "binding_name": binding_name,
                "renderer": dict(renderer),
                "value_type_name": entry["value_type_name"],
                "value_digest": trace_row.value_sha256,
                "rendered_bytes_digest": (
                    trace_row.raw_renderer_bytes_sha256
                ),
                "evidence_key": view_evidence_key(
                    str(renderer["renderer_id"]),
                    int(renderer["renderer_version"]),
                    VIEW_RENDERER_SCHEMA_VERSION,
                    trace_row.value_sha256,
                ),
                "source_map_origin_key": (
                    entry["source_map_origin_key"]
                ),
                "injection_order": entry["injection_order"],
                "request_field_evidence": (
                    _request_field_evidence_rows(
                        entry=entry,
                        resolved_value=resolved_value,
                    )
                ),
            }
            for row_field in ("u0_row_id", "c0_row_id"):
                if row_field in entry:
                    evidence_payload[row_field] = entry[row_field]
            expected.append(evidence_payload)
        return expected
    except (TypeError, ValueError) as exc:
        if str(exc).startswith("prompt_attempt_binding_plan_invalid:"):
            raise
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "fragment trace and typed evidence disagree"
        ) from exc


def _validate_fragment_typed_evidence_rows(
    evidence: Sequence[Mapping[str, Any]],
    *,
    expected_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if len(evidence) != len(expected_rows):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "fragment trace and typed evidence cardinality disagree"
        )
    validated: list[dict[str, Any]] = []
    for raw_row, expected_row in zip(
        evidence,
        expected_rows,
        strict=True,
    ):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "typed evidence row is not a mapping"
            )
        row = dict(raw_row)
        expected = dict(expected_row)
        if set(row) != set(expected) or any(
            row.get(field_name) != expected_value
            for field_name, expected_value in expected.items()
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "fragment trace and typed evidence row disagree"
            )
        validated.append(row)
    return validated


def _validated_composition_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    resolved_typed_values: Mapping[str, Any],
) -> list[dict[str, Any]]:
    normalized_entries = sorted(
        (normalize_typed_prompt_input_entry(entry) for entry in entries),
        key=lambda item: (item["injection_order"], item["binding_name"]),
    )
    binding_names = [entry["binding_name"] for entry in normalized_entries]
    if (
        len(binding_names) != len(set(binding_names))
        or set(binding_names) != set(resolved_typed_values)
    ):
        raise ValueError(
            "typed_prompt_input_binding_set_mismatch: "
            "lowered bindings and resolved typed values must match exactly"
        )
    injection_orders = [entry["injection_order"] for entry in normalized_entries]
    if (
        len(injection_orders) != len(set(injection_orders))
        or injection_orders != list(range(len(injection_orders)))
    ):
        raise ValueError(
            "typed_prompt_input_injection_order_invalid: "
            "injection orders must be unique and contiguous"
        )
    return normalized_entries


def cast_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return value


def _request_field_evidence_rows(
    *,
    entry: Mapping[str, Any],
    resolved_value: Any,
) -> list[dict[str, Any]]:
    request_fields = entry.get("request_fields")
    if not isinstance(request_fields, Mapping):
        return []
    field_authority = request_fields.get("field_authority")
    if not isinstance(field_authority, Mapping):
        return []
    evidence_rows: list[dict[str, Any]] = []
    for field_path in sorted(
        str(path) for path in field_authority if isinstance(path, str) and path
    ):
        metadata = field_authority.get(field_path)
        if not isinstance(metadata, Mapping):
            continue
        leaf_value = _resolve_request_field_value(resolved_value, field_path)
        evidence_row = {
            "field_path": field_path,
            "authority_class": str(metadata.get("authority_class", "")),
            "source_binding": str(metadata.get("source_binding", "")),
            "bridge_field_name": str(metadata.get("bridge_field_name", "")),
            "rendered_leaf_shape": _rendered_leaf_shape(
                leaf_value,
                field_path=field_path,
            ),
            "rendered_leaf_digest": typed_prompt_input_value_digest(leaf_value),
        }
        checked_row_id = metadata.get("checked_row_id")
        if isinstance(checked_row_id, str) and checked_row_id:
            evidence_row["checked_row_id"] = checked_row_id
        evidence_rows.append(evidence_row)
    return evidence_rows


def _resolve_request_field_value(value: Any, field_path: str) -> Any:
    current = value
    for segment in field_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise ValueError(
                "typed_prompt_input_hidden_bridge_field_missing: "
                f"missing rendered request field `{field_path}`"
            )
        current = current[segment]
    return current


def _rendered_leaf_shape(value: Any, *, field_path: str) -> str:
    if isinstance(value, str):
        return "scalar_path"
    if isinstance(value, Mapping) and isinstance(value.get("ref"), str):
        return "ref_object"
    raise ValueError(
        "typed_prompt_input_hidden_bridge_leaf_shape_invalid: "
        f"rendered request field `{field_path}` is not path-like"
    )


def _normalize_typed_prompt_input_binding_source(value_source: Mapping[str, Any]) -> dict[str, Any]:
    kind = value_source.get("kind")
    binding: Any
    if "binding" in value_source:
        binding = value_source["binding"]
    elif isinstance(value_source.get("binding_ref"), str):
        binding = {"ref": value_source["binding_ref"]}
    elif isinstance(value_source.get("ref"), str):
        binding = {"ref": value_source["ref"]}
    else:
        raise ValueError("typed_prompt_input_schema_invalid: value_source binding is required")
    return {
        "kind": str(kind) if isinstance(kind, str) and kind else "typed_binding_ref",
        "binding": binding,
    }


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"typed_prompt_input_schema_invalid: {field_name} is required")
    return value
