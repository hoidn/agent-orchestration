"""Non-authoritative debug YAML projection for validated Workflow Lisp bundles."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Mapping

import yaml

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle


WARNING_HEADER = (
    "# WARNING: generated debug projection only\n"
    "# This YAML is non-authoritative and must not be used as execution input.\n"
)


def render_debug_yaml(
    bundle: LoadedWorkflowBundle,
    *,
    source_trace_path: Path | None = None,
) -> str:
    """Render one validated bundle into a stable debug YAML string."""

    payload = {
        "warning": "non_authoritative_debug_projection",
        "workflow": _thaw(bundle.surface),
    }
    if source_trace_path is not None:
        payload["source_trace_path"] = str(source_trace_path)
    return WARNING_HEADER + yaml.safe_dump(payload, sort_keys=False)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {
            field: _thaw(getattr(value, field))
            for field in value.__dataclass_fields__
        }
    return value
