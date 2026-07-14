"""Prompt rendering for deterministic output contract instructions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence


_RELPATH_GUIDANCE = (
    "# Relpath values are workspace-relative. Include the declared `under` "
    "prefix in the value: for `under: artifacts/work`, write "
    "`artifacts/work/...`; for `under: artifacts/review`, write "
    "`artifacts/review/...`."
)

_CONTENT_ONLY_FOOTER = "Use these consumed artifacts as context for your work."
_REFERENCE_ONLY_FOOTER = "These references preserve artifact lineage; open them only when needed."
_MIXED_FOOTER = "Use embedded content as context and open referenced artifacts only when needed."


@dataclass(frozen=True)
class ConsumePromptPolicy:
    artifact_name: str
    mode: str = "content"
    label: str | None = None
    description: str | None = None
    format_hint: str | None = None
    example: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class RenderedConsumedArtifact:
    artifact_name: str
    mode: str
    rendered_value: str
    label: str | None = None
    description: str | None = None
    format_hint: str | None = None
    example: str | None = None
    role: str | None = None


def _nested_prompt_mapping(consume: Mapping[str, Any]) -> Mapping[str, Any]:
    prompt = consume.get("prompt")
    if isinstance(prompt, Mapping):
        return prompt
    return {}


def normalize_consume_prompt_policy(consume: Mapping[str, Any]) -> ConsumePromptPolicy:
    """Merge legacy row guidance with nested prompt metadata."""
    nested = _nested_prompt_mapping(consume)
    artifact_name = str(consume.get("artifact", ""))
    mode = nested.get("mode") if isinstance(nested.get("mode"), str) else "content"
    if mode not in {"content", "reference", "none"}:
        mode = "content"

    def _guidance_value(field_name: str) -> str | None:
        nested_value = nested.get(field_name)
        if isinstance(nested_value, str):
            return nested_value
        legacy_value = consume.get(field_name)
        if isinstance(legacy_value, str):
            return legacy_value
        return None

    label = nested.get("label")
    role = nested.get("role")
    return ConsumePromptPolicy(
        artifact_name=artifact_name,
        mode=mode,
        label=label if isinstance(label, str) else None,
        description=_guidance_value("description"),
        format_hint=_guidance_value("format_hint"),
        example=_guidance_value("example"),
        role=role if isinstance(role, str) else None,
    )


def selected_consumed_artifacts_for_prompt(
    step: Mapping[str, Any],
    step_consumed_values: Mapping[str, Any],
) -> list[tuple[ConsumePromptPolicy, Any]]:
    """Return consumes selected by prompt filters and reserved-session exclusion."""
    consumes = step.get("consumes")
    if not isinstance(consumes, Sequence) or isinstance(consumes, (str, bytes)):
        return []
    if not isinstance(step_consumed_values, Mapping):
        return []

    prompt_consumes = step.get("prompt_consumes")
    allowed_names: set[str] | None = None
    if prompt_consumes is not None:
        if not isinstance(prompt_consumes, list):
            return []
        allowed_names = {
            name for name in prompt_consumes
            if isinstance(name, str) and name.strip()
        }
        if not allowed_names:
            return []

    reserved_session_artifact: str | None = None
    provider_session = step.get("provider_session")
    if isinstance(provider_session, Mapping) and provider_session.get("mode") == "resume":
        session_id_from = provider_session.get("session_id_from")
        if isinstance(session_id_from, str) and session_id_from:
            reserved_session_artifact = session_id_from

    selected: list[tuple[ConsumePromptPolicy, Any]] = []
    for consume in consumes:
        if not isinstance(consume, Mapping):
            continue
        policy = normalize_consume_prompt_policy(consume)
        artifact_name = policy.artifact_name
        if not artifact_name:
            continue
        if reserved_session_artifact is not None and artifact_name == reserved_session_artifact:
            continue
        if allowed_names is not None and artifact_name not in allowed_names:
            continue
        if artifact_name not in step_consumed_values:
            continue
        selected.append((policy, step_consumed_values[artifact_name]))
    return selected


def stringify_consumed_value(value: Any) -> str | None:
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return None


def _append_field_constraints(
    lines: List[str],
    spec: Dict[str, Any],
    *,
    indent: int = 2,
    include_legacy_guidance: bool = True,
) -> None:
    """Append optional field-level contract constraints."""
    prefix = " " * indent
    if "allowed" in spec:
        allowed_values = ", ".join(str(value) for value in spec["allowed"])
        lines.append(f"{prefix}allowed: {allowed_values}")
    if "under" in spec:
        lines.append(f"{prefix}under: {spec['under']}")
    if spec.get("must_exist_target"):
        lines.append(f"{prefix}must_exist_target: true")
    if spec.get("required") is False:
        lines.append(f"{prefix}required: false")
    if include_legacy_guidance:
        if "description" in spec:
            lines.append(f"{prefix}description: {spec['description']}")
        if "format_hint" in spec:
            lines.append(f"{prefix}format_hint: {spec['format_hint']}")
        if "example" in spec:
            lines.append(f"{prefix}example: {spec['example']}")


def _append_guidance_payload(
    lines: List[str],
    payload: Mapping[str, Any],
    *,
    indent: int,
    variant_order: Sequence[str] = (),
) -> None:
    """Render one validated v2.15 guidance payload without reinterpretation."""
    prefix = " " * indent
    if "description" in payload:
        lines.append(f"{prefix}description: {payload['description']}")
    if "format_hint" in payload:
        lines.append(f"{prefix}format_hint: {payload['format_hint']}")
    if "example" in payload:
        rendered_example = json.dumps(
            payload["example"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        lines.append(f"{prefix}example: {rendered_example}")

    guidance_context = payload.get("guidance_context")
    if isinstance(guidance_context, list) and guidance_context:
        lines.append(f"{prefix}guidance_context:")
        for context in guidance_context:
            lines.append(f"{prefix}  - json_pointer: {context['json_pointer']}")
            _append_guidance_payload(lines, context, indent=indent + 4)

    guidance_by_variant = payload.get("guidance_by_variant")
    if isinstance(guidance_by_variant, Mapping) and guidance_by_variant:
        lines.append(f"{prefix}guidance_by_variant:")
        ordered_variants = [
            variant for variant in variant_order if variant in guidance_by_variant
        ]
        ordered_variants.extend(
            variant
            for variant in guidance_by_variant
            if variant not in ordered_variants
        )
        for variant in ordered_variants:
            lines.append(f"{prefix}  {variant}:")
            _append_guidance_payload(
                lines,
                guidance_by_variant[variant],
                indent=indent + 4,
            )


def _append_nested_schema(lines: List[str], spec: Dict[str, Any], *, indent: int, key: str) -> None:
    nested = spec.get(key)
    if not isinstance(nested, dict):
        return
    prefix = " " * indent
    lines.append(f"{prefix}{key}:")
    _append_schema_spec(lines, nested, indent=indent + 2)


def _append_schema_spec(
    lines: List[str],
    spec: Dict[str, Any],
    *,
    indent: int,
    variant_order: Sequence[str] = (),
) -> None:
    prefix = " " * indent
    lines.append(f"{prefix}type: {spec['type']}")
    _append_field_constraints(
        lines,
        spec,
        indent=indent,
        include_legacy_guidance=False,
    )
    _append_nested_schema(lines, spec, indent=indent, key="item")
    _append_nested_schema(lines, spec, indent=indent, key="items")
    _append_nested_schema(lines, spec, indent=indent, key="keys")
    _append_nested_schema(lines, spec, indent=indent, key="values")
    _append_guidance_payload(
        lines,
        spec,
        indent=indent,
        variant_order=variant_order,
    )


def render_output_contract_block(expected_outputs: List[Dict[str, Any]]) -> str:
    """Render a stable prompt suffix describing required one-file-per-value artifacts."""
    lines: List[str] = [
        "## Output Contract",
        "Write the following artifacts exactly as specified.",
        "Each artifact file must contain only the value for that artifact.",
        _RELPATH_GUIDANCE,
    ]

    for spec in expected_outputs:
        lines.append(f"- name: {spec['name']}")
        lines.append(f"  path: {spec['path']}")
        lines.append(f"  type: {spec['type']}")
        _append_field_constraints(lines, spec)

    return "\n".join(lines) + "\n"


def render_output_bundle_contract_block(output_bundle: Dict[str, Any]) -> str:
    """Render a stable prompt suffix describing a required JSON output bundle."""
    fields = output_bundle.get("fields", [])
    if len(fields) == 1 and fields[0].get("json_pointer") == "":
        return _render_root_output_bundle_contract_block(output_bundle, fields[0])

    lines: List[str] = [
        "## Output Contract",
        (
            "Write the following JSON bundle exactly as specified. If "
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH is present, it is the "
            "runtime-owned authoritative write target."
        ),
        _RELPATH_GUIDANCE,
        f"- path: {output_bundle['path']}",
        "  format: JSON object",
    ]

    guidance = output_bundle.get("guidance")
    if isinstance(guidance, Mapping):
        lines.append("  guidance:")
        _append_guidance_payload(lines, guidance, indent=4)
    lines.append("  fields:")

    for spec in fields:
        lines.append(f"    - name: {spec['name']}")
        lines.append(f"      json_pointer: {spec['json_pointer']}")
        _append_schema_spec(lines, spec, indent=6)

    return "\n".join(lines) + "\n"


def _render_root_output_bundle_contract_block(
    output_bundle: Dict[str, Any], field: Dict[str, Any]
) -> str:
    """Render a stable prompt suffix for a single direct-JSON-root output bundle.

    A non-record/non-union result lowers to one `__result__` field at JSON
    pointer `""` (`orchestrator/workflow_lisp/contracts.py`,
    `docs/design/workflow_lisp_native_transportable_returns.md`). The bundle
    is one JSON value, not an object with named fields, so the prompt must not
    claim `format: JSON object` or name the compiler-owned `__result__` field.
    """
    lines: List[str] = [
        "## Output Contract",
        (
            "Write one JSON value exactly as specified. If "
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH is present, it is the "
            "runtime-owned authoritative write target."
        ),
        _RELPATH_GUIDANCE,
        f"- path: {output_bundle['path']}",
        "  format: JSON value",
    ]
    guidance = output_bundle.get("guidance")
    if isinstance(guidance, Mapping):
        lines.append("  guidance:")
        _append_guidance_payload(lines, guidance, indent=4)
    _append_schema_spec(lines, field, indent=2)
    return "\n".join(lines) + "\n"


def render_variant_output_contract_block(variant_output: Dict[str, Any]) -> str:
    """Render a stable prompt suffix describing a tagged-union JSON output bundle."""
    discriminant = variant_output["discriminant"]
    lines: List[str] = [
        "## Variant Output Contract",
        (
            "Write the following JSON bundle exactly as specified. If "
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH is present, it is the "
            "runtime-owned authoritative write target."
        ),
        _RELPATH_GUIDANCE,
        f"- path: {variant_output['path']}",
        "  format: JSON object",
    ]
    guidance = variant_output.get("guidance")
    if isinstance(guidance, Mapping):
        lines.append("  guidance:")
        _append_guidance_payload(lines, guidance, indent=4)
    lines.extend(
        [
            "  discriminant:",
            f"    name: {discriminant['name']}",
            f"    json_pointer: {discriminant['json_pointer']}",
            f"    type: {discriminant.get('type', 'enum')}",
        ]
    )
    if "allowed" in discriminant:
        allowed_values = ", ".join(str(value) for value in discriminant["allowed"])
        lines.append(f"    allowed: {allowed_values}")
    shared_fields = variant_output.get("shared_fields", [])
    if shared_fields:
        lines.append("  shared_fields:")
        for spec in shared_fields:
            lines.append(f"    - name: {spec['name']}")
            lines.append(f"      json_pointer: {spec['json_pointer']}")
            _append_schema_spec(
                lines,
                spec,
                indent=6,
                variant_order=discriminant.get("allowed", ()),
            )
    lines.append("  variants:")
    variants = variant_output.get("variants", {})
    variant_names = [
        variant_name
        for variant_name in discriminant.get("allowed", ())
        if variant_name in variants
    ]
    variant_names.extend(
        variant_name for variant_name in variants if variant_name not in variant_names
    )
    for variant_name in variant_names:
        variant_spec = variants[variant_name]
        lines.append(f"    {variant_name}:")
        lines.append("      fields:")
        for spec in variant_spec.get("fields", []):
            lines.append(f"        - name: {spec['name']}")
            lines.append(f"          json_pointer: {spec['json_pointer']}")
            _append_schema_spec(lines, spec, indent=10)
    return "\n".join(lines) + "\n"


def render_consumed_artifacts_block(
    consumed: Sequence[RenderedConsumedArtifact],
) -> str:
    """Render a stable prompt block describing resolved consumed artifacts."""
    lines: List[str] = ["## Consumed Artifacts"]
    sorted_consumed = sorted(consumed, key=lambda entry: entry.artifact_name)
    rendered_modes: set[str] = set()
    for entry in sorted_consumed:
        rendered_modes.add(entry.mode)
        if entry.mode == "reference":
            lines.append(f"- {entry.artifact_name}:")
            lines.append("  mode: reference")
            if entry.label:
                lines.append(f"  label: {entry.label}")
            lines.append(f"  resolved_value: {entry.rendered_value}")
            if entry.role:
                lines.append(f"  role: {entry.role}")
        else:
            lines.append(f"- {entry.artifact_name}: {entry.rendered_value}")
            if entry.label:
                lines.append(f"  label: {entry.label}")
            if entry.role:
                lines.append(f"  role: {entry.role}")
        if entry.description:
            lines.append(f"  description: {entry.description}")
        if entry.format_hint:
            lines.append(f"  format_hint: {entry.format_hint}")
        if entry.example:
            lines.append(f"  example: {entry.example}")

    if rendered_modes == {"content"}:
        lines.append(_CONTENT_ONLY_FOOTER)
    elif rendered_modes == {"reference"}:
        lines.append(_REFERENCE_ONLY_FOOTER)
    else:
        lines.append(_MIXED_FOOTER)
    return "\n".join(lines) + "\n"
