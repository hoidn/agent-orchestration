"""Exact dynamic public routing and dry-run boundary checks."""
from argparse import Namespace
import sys
from unittest.mock import patch

from tests.test_workflow_dynamic_source import write_source
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args


def test_candidate_registration_cannot_fall_through_public_owners(tmp_path, monkeypatch, caplog):
    from orchestrator.cli.commands import compile as compile_command, run as run_command, evaluated
    path = write_source(tmp_path, "demo/main", "(export main) (defworkflow main () -> Int 1)")
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("dynamic target entered a retained frontend/runtime")
    monkeypatch.setattr(compile_command, "build_frontend_bundle", forbidden)
    monkeypatch.setattr(compile_command, "build_closed_program_bundle", forbidden)
    monkeypatch.setattr(run_command, "StateManager", forbidden)
    monkeypatch.setattr(run_command, "build_frontend_bundle", forbidden)
    monkeypatch.setattr(evaluated, "run_evaluated_workflow", forbidden)
    args = Namespace(workflow=str(path), diagnostics_json=False)
    assert compile_command.compile_workflow(args) == 2
    run_args = _run_args({"source": path, "source_root": tmp_path, "providers": path, "prompts": path})
    with patch.object(sys, "argv", ["orchestrator", "run", str(path)]):
        result = run_command.run_workflow(run_args)
    assert result.exit_code == 2
    assert "dynamic_source_route_required" in caplog.text
    assert not (tmp_path / ".orchestrate").exists()
