"""Prompt rendering for deterministic output contract instructions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


_RELPATH_GUIDANCE = (
    "# Relpath values are workspace-relative. Include the declared `under` "
    "prefix in the value: for `under: artifacts/work`, write "
    "`artifacts/work/...`; for `under: artifacts/review`, write "
    "`artifacts/review/...`."
)


def _append_field_constraints(lines: List[str], spec: Dict[str, Any], *, indent: int = 2) -> None:
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
    if "description" in spec:
        lines.append(f"{prefix}description: {spec['description']}")
    if "format_hint" in spec:
        lines.append(f"{prefix}format_hint: {spec['format_hint']}")
    if "example" in spec:
        lines.append(f"{prefix}example: {spec['example']}")


def _append_nested_schema(lines: List[str], spec: Dict[str, Any], *, indent: int, key: str) -> None:
    nested = spec.get(key)
    if not isinstance(nested, dict):
        return
    prefix = " " * indent
    lines.append(f"{prefix}{key}:")
    _append_schema_spec(lines, nested, indent=indent + 2)


def _append_schema_spec(lines: List[str], spec: Dict[str, Any], *, indent: int) -> None:
    prefix = " " * indent
    lines.append(f"{prefix}type: {spec['type']}")
    _append_field_constraints(lines, spec, indent=indent)
    _append_nested_schema(lines, spec, indent=indent, key="item")
    _append_nested_schema(lines, spec, indent=indent, key="items")
    _append_nested_schema(lines, spec, indent=indent, key="keys")
    _append_nested_schema(lines, spec, indent=indent, key="values")


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
        "  fields:",
    ]

    for spec in output_bundle.get("fields", []):
        lines.append(f"    - name: {spec['name']}")
        lines.append(f"      json_pointer: {spec['json_pointer']}")
        _append_schema_spec(lines, spec, indent=6)

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
        "  discriminant:",
        f"    name: {discriminant['name']}",
        f"    json_pointer: {discriminant['json_pointer']}",
        f"    type: {discriminant.get('type', 'enum')}",
    ]
    if "allowed" in discriminant:
        allowed_values = ", ".join(str(value) for value in discriminant["allowed"])
        lines.append(f"    allowed: {allowed_values}")
    shared_fields = variant_output.get("shared_fields", [])
    if shared_fields:
        lines.append("  shared_fields:")
        for spec in shared_fields:
            lines.append(f"    - name: {spec['name']}")
            lines.append(f"      json_pointer: {spec['json_pointer']}")
            _append_schema_spec(lines, spec, indent=6)
    lines.append("  variants:")
    for variant_name, variant_spec in variant_output.get("variants", {}).items():
        lines.append(f"    {variant_name}:")
        lines.append("      fields:")
        for spec in variant_spec.get("fields", []):
            lines.append(f"        - name: {spec['name']}")
            lines.append(f"          json_pointer: {spec['json_pointer']}")
            _append_schema_spec(lines, spec, indent=10)
    return "\n".join(lines) + "\n"


def render_consumed_artifacts_block(
    consumed: Dict[str, Any],
    guidance_by_name: Optional[Dict[str, Dict[str, str]]] = None,
) -> str:
    """Render a stable prompt block describing resolved consumed artifacts."""
    lines: List[str] = ["## Consumed Artifacts"]
    guidance = guidance_by_name or {}
    for name in sorted(consumed.keys()):
        lines.append(f"- {name}: {consumed[name]}")
        field_guidance = guidance.get(name, {})
        if "description" in field_guidance:
            lines.append(f"  description: {field_guidance['description']}")
        if "format_hint" in field_guidance:
            lines.append(f"  format_hint: {field_guidance['format_hint']}")
        if "example" in field_guidance:
            lines.append(f"  example: {field_guidance['example']}")
    lines.append("Read these files before acting.")
    return "\n".join(lines) + "\n"
