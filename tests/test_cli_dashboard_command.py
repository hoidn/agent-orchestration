"""Tests for dashboard CLI command wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.cli.commands.dashboard import dashboard_workflow
from orchestrator.cli.main import create_parser


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
