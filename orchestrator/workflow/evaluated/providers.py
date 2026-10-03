"""Resolve the file inputs captured by one checked provider effect."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from orchestrator.deps.content_snapshot import (
    DependencyContentSnapshot,
    snapshot_content_dependencies_with_sha256,
)
from orchestrator.deps.resolver import DependencyResolver
from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow.evaluated.values import EvaluatedValue
from orchestrator.workflow_lisp.closed.frontend import WorkflowIOReader
from orchestrator.workflow_lisp.closed.sites import _effect_value_children


@dataclass(frozen=True)
class ProviderIOReads:
    """C6 text and raw-byte evidence, without the physical reader root."""

    source_kind: str | None
    source_path: str | None
    source_text: str | None
    source_sha256: str | None
    dependency_snapshot: DependencyContentSnapshot | None
    dependency_sha256s: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dependency_sha256s", MappingProxyType(dict(self.dependency_sha256s))
        )


def resolve_provider_io(
    node: Mapping[str, Any],
    operands: Sequence[EvaluatedValue],
    *,
    workspace: Path,
    reader: WorkflowIOReader | None,
) -> ProviderIOReads:
    """Read one reached provider's source and dependency snapshot exactly once."""

    if node.get("class") != "provider":
        raise TypeError("checked provider effect required")
    children = _effect_value_children(dict(node))
    if len(children) != len(operands) or not all(
        isinstance(value, EvaluatedValue) for value in operands
    ):
        raise ValueError("provider operands do not match the checked effect node")
    values = tuple(value.json_value() for value in operands)
    prompt = node.get("prompt")
    if not isinstance(prompt, Mapping):
        raise ValueError("checked provider prompt shape is invalid")

    source_kind, source_path, source_text, source_sha256 = _read_source(
        node, prompt, workspace=workspace, reader=reader
    )
    snapshot, digests = _snapshot_dependencies(node, values, Path(workspace))
    return ProviderIOReads(
        source_kind,
        source_path,
        source_text,
        source_sha256,
        snapshot,
        digests,
    )


def _read_source(node, prompt, *, workspace, reader):
    source_kind = prompt.get("source_kind")
    source_path = prompt.get("path")
    if source_kind == "asset_file":
        if reader is None:
            raise ValueError("provider file read requires its checked reader")
        text, digest = WorkflowAssetResolver(reader.workflow_path).read_text_with_sha256(
            source_path
        )
    elif source_kind == "input_file":
        text, digest, error = PromptComposer(
            workspace=Path(workspace), asset_resolver=None
        ).read_prompt_source_with_sha256(
            {"input_file": source_path},
            step_name=str(node.get("provider", "provider")),
            contract_violation_result=lambda message, context: {
                "message": message,
                "context": context,
            },
        )
        if error is not None:
            raise ValueError(error)
    elif source_kind is None and "template" in prompt:
        return None, None, None, None
    else:
        raise ValueError("checked provider has no prompt source")
    return source_kind, source_path, text, digest


def _snapshot_dependencies(node, values, workspace):
    prompt = node["prompt"]
    fills = prompt.get("fills", ())
    dependencies = node.get("dependencies") or {}
    required = dependencies.get("required", ())
    optional = dependencies.get("optional", ())
    cursor = len(node.get("inputs", ()))
    fill_values = values[cursor : cursor + len(fills)]
    cursor += len(fills)
    required_values = values[cursor : cursor + len(required)]
    cursor += len(required)
    optional_values = values[cursor : cursor + len(optional)]
    required_rows = [
        (fill["name"], path)
        for fill, path in zip(fills, fill_values, strict=True)
        if fill.get("kind") == "doc"
    ]
    required_rows.extend(
        (f"required:{index}", path) for index, path in enumerate(required_values)
    )
    optional_rows = [
        (f"optional:{index}", path) for index, path in enumerate(optional_values)
    ]
    if not required_rows and not optional_rows:
        return None, {}
    resolved = DependencyResolver(str(workspace)).resolve_exact(
        required=required_rows, optional=optional_rows
    )
    return snapshot_content_dependencies_with_sha256(
        workspace, resolved.classified_rows
    )
