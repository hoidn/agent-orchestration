"""Tests for the JSON-only shared-validation fixture adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.exceptions import WorkflowValidationError
from tests.workflow_fixture_loader import WorkflowLoader


def _workflow(name: str, *, imports: dict[str, str] | None = None) -> dict:
    payload = {
        "version": "2.5",
        "name": name,
        "steps": [{"name": "done", "command": ["true"]}],
    }
    if imports is not None:
        payload["imports"] = imports
    return payload


def test_json_fixture_loader_builds_a_typed_bundle(tmp_path: Path) -> None:
    path = tmp_path / "workflow.fixture.json"
    path.write_text(json.dumps(_workflow("root")), encoding="utf-8")

    bundle = WorkflowLoader(tmp_path).load_bundle(path)

    assert bundle.surface.name == "root"


def test_json_fixture_loader_resolves_relative_imports(tmp_path: Path) -> None:
    child = tmp_path / "child.fixture.json"
    child.write_text(json.dumps(_workflow("child")), encoding="utf-8")
    root = tmp_path / "root.fixture.json"
    root.write_text(
        json.dumps(_workflow("root", imports={"child": child.name})),
        encoding="utf-8",
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(root)

    imported = bundle.surface.imports["child"]
    assert imported.workflow_name == "child"
    assert imported.workflow_path == child.resolve()


def test_json_fixture_loader_rejects_non_json_fixture_text(tmp_path: Path) -> None:
    path = tmp_path / "workflow.fixture.json"
    path.write_text("name: legacy-yaml\n", encoding="utf-8")

    with pytest.raises(WorkflowValidationError, match="JSON workflow fixture"):
        WorkflowLoader(tmp_path).load_bundle(path)
