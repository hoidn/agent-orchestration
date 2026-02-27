"""Prompt rendering for deterministic output contract instructions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def render_output_contract_block(expected_outputs: List[Dict[str, Any]]) -> str:
    """Render a stable prompt suffix describing required output artifacts."""
    lines: List[str] = [
        "## Output Contract",
        "Write the following artifacts exactly as specified.",
        "Each artifact file must contain only the value for that artifact.",
    ]

    for spec in expected_outputs:
        lines.append(f"- name: {spec['name']}")
        lines.append(f"  path: {spec['path']}")
        lines.append(f"  type: {spec['type']}")

        if "allowed" in spec:
            allowed_values = ", ".join(str(value) for value in spec["allowed"])
            lines.append(f"  allowed: {allowed_values}")
        if "under" in spec:
            lines.append(f"  under: {spec['under']}")
        if spec.get("must_exist_target"):
            lines.append("  must_exist_target: true")
        if spec.get("required") is False:
            lines.append("  required: false")
        if "description" in spec:
            lines.append(f"  description: {spec['description']}")
        if "format_hint" in spec:
            lines.append(f"  format_hint: {spec['format_hint']}")
        if "example" in spec:
            lines.append(f"  example: {spec['example']}")

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
