"""Tests for dashboard CLI command wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.cli.commands.dashboard import dashboard_workflow
from orchestrator.cli.main import create_parser
from orchestrator.dashboard.projection import RunProjector
from tests.test_dashboard_compiled_workflow import (
    _write_real_imported_bundle_mix_run,
)


def test_parser_supports_dashboard_subcommand(tmp_path: Path):
    parser = create_parser()
    args = parser.parse_args(
        [
            "dashboard",
            "--workspace",
            str(tmp_path),
            "--workspace",
            str(tmp_path / "other"),
            "--port",
            "8765",
        ]
    )

    assert args.command == "dashboard"
    assert args.workspace == [str(tmp_path), str(tmp_path / "other")]
    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_parser_rejects_missing_dashboard_workspace():
    parser = create_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["dashboard"])


def test_dashboard_handler_validates_workspaces_before_starting_server(tmp_path: Path):
    started = {}

    def fake_serve(*, scanner, host, port):
        started["workspaces"] = [workspace.root for workspace in scanner.workspaces]
        started["host"] = host
        started["port"] = port
        return 0

    result = dashboard_workflow(
        workspace=[str(tmp_path)],
        host="127.0.0.1",
        port=8765,
        serve=fake_serve,
    )

    assert result == 0
    assert started == {
        "workspaces": [tmp_path.resolve()],
        "host": "127.0.0.1",
        "port": 8765,
    }


@pytest.mark.parametrize("mode", ["bound", "legacy", "corrupt"])
def test_dashboard_handler_projects_persisted_surface_run_contracts(
    tmp_path: Path,
    mode: str,
):
    _result, _source_path, state = _write_real_imported_bundle_mix_run(tmp_path)
    if mode != "bound":
        compiled = state["runtime_observability"]["compiled_frontend"]
        if mode == "legacy":
            compiled.pop("persisted_workflow_surface")
        else:
            compiled["persisted_workflow_surface"]["sha256"] = "sha256:" + "A" * 64
        state_path = tmp_path / ".orchestrate" / "runs" / "run1" / "state.json"
        state_path.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    observed = {}

    def fake_serve(*, scanner, host, port):
        detail = RunProjector().project_detail(scanner.scan().runs[0])
        observed["structure"] = detail.workflow_structure
        observed["warnings"] = detail.warnings
        return 0

    result = dashboard_workflow(
        workspace=[str(tmp_path)],
        host="127.0.0.1",
        port=8765,
        serve=fake_serve,
    )

    assert result == 0
    if mode == "bound":
        assert observed["structure"].entry_workflow == "neurips/entry::orchestrate"
        assert observed["warnings"] == []
    else:
        assert observed["structure"] is None
        assert any("failed to load workflow metadata" in item for item in observed["warnings"])
