"""Public readers reconstruct evaluated authority without changing evidence."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.cli.commands.report import report_workflow
from orchestrator.state import RunState, StateManager
from tests.test_workflow_evaluated_cli import _build, _run_cli
from tests.test_workflow_evaluated_invalidate import _tree_bytes


def _pure_run(root: Path) -> Path:
    source, _program = _build(root)
    result = _run_cli(root, str(source), "--input", "score=0.75")
    assert result.returncode == 0, result.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return run_root


def test_report_reads_evaluated_root_without_state(tmp_path, capsys):
    run_root = _pure_run(tmp_path)
    (run_root / "state.json").unlink(missing_ok=True)
    before = _tree_bytes(tmp_path)

    result = report_workflow(run_root.name, runs_root=str(run_root.parent), format="json")

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["status"] == "completed"
    assert payload["run"]["workflow_outputs"] == {"accepted": True, "score": 0.75}
    assert payload["run"]["memo_offset"] == len((run_root / "memo.jsonl").read_bytes())
    assert _tree_bytes(tmp_path) == before


def test_state_manager_reconstructs_before_reading_contradictory_view(tmp_path):
    run_root = _pure_run(tmp_path)
    (run_root / "state.json").write_text('{"status":"failed","result_persistence_profile":"unknown"}')
    before = _tree_bytes(tmp_path)

    state = StateManager(tmp_path, run_root.name).load()

    assert state.status == "completed"
    assert state.workflow_outputs == {"accepted": True, "score": 0.75}
    payload = state.to_dict()
    assert RunState.from_dict(payload).to_dict() == payload
    assert payload["memo_offset"] == len((run_root / "memo.jsonl").read_bytes())
    assert _tree_bytes(tmp_path) == before


def _scalar_run(root, returns, expression):
    source = root / "scalar.orc"
    parameters, arguments = "", []
    if expression == "null":
        parameters, expression = f"(payload {returns})", "payload"
        inputs = root / "inputs.json"
        inputs.write_text('{"payload":null}')
        arguments = ["--input-file", str(inputs)]
    source.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule scalar) (export run) (defworkflow run ({parameters}) -> {returns} {expression}))''')
    result = _run_cli(root, str(source), *arguments)
    assert result.returncode == 0, result.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return run_root


@pytest.mark.parametrize("returns,expression,value", [
    ("Int", "7", 7), ("Bool", "false", False), ("List[Int]", "(list 1 2)", [1, 2]),
    ("Optional[Int]", "null", None), ("List[Int]", "(list)", []),
])
def test_report_markdown_preserves_direct_json_outputs(tmp_path, capsys, returns, expression, value):
    run_root = _scalar_run(tmp_path, returns, expression)
    before = _tree_bytes(tmp_path)

    assert report_workflow(run_root.name, runs_root=str(run_root.parent), format="md") == 0
    rendered = capsys.readouterr().out

    assert "## Outputs" in rendered
    encoded = rendered.split("```json\n", 1)[1].split("\n```", 1)[0]
    assert json.loads(encoded) == value
    assert "## Prompt context" not in rendered
    assert "## Judgment views" not in rendered
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("view", [None, "invalid json", '{"status":"failed"}'])
def test_report_reconstructs_missing_stale_and_invalid_views(tmp_path, capsys, view):
    run_root = _pure_run(tmp_path)
    if view is not None:
        (run_root / "state.json").write_text(view)
    (tmp_path / "evaluated" / "inputs.orc").unlink()
    before = _tree_bytes(tmp_path)
    assert report_workflow(runs_root=str(run_root.parent), format="json") == 0
    assert json.loads(capsys.readouterr().out)["run"]["status"] == "completed"
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("fields", [(), ("resume_request",), ("run_ref_root",), ("resume_request", "run_ref_root")])
def test_historical_optional_authority_still_loads_without_sources(tmp_path, fields):
    run_root = _pure_run(tmp_path)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_bytes())
    for name in fields:
        header.pop(name, None)
    header_path.write_text(json.dumps(header))
    (tmp_path / "evaluated" / "inputs.orc").unlink()
    before = _tree_bytes(tmp_path)
    assert StateManager(tmp_path, run_root.name).load().status == "completed"
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("change", ["profile", "schema", "missing_header", "artifact", "digest", "inputs", "recipe", "root"])
def test_authority_corruption_refuses_before_state_fallback(tmp_path, capsys, change):
    run_root = _pure_run(tmp_path)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_bytes())
    mutations = {"profile": ("result_persistence_profile", "unknown"), "schema": ("schema_version", "2.1"),
                 "digest": ("program_digest", "sha256:" + "0" * 64), "inputs": ("bound_inputs", {"score": True}),
                 "recipe": ("resume_request", {}), "root": ("run_ref_root", "relative")}
    if change == "missing_header":
        header_path.unlink()
    elif change == "artifact":
        (run_root / "closed_program.json").write_text("{}")
    else:
        name, value = mutations[change]
        header[name] = value
        header_path.write_text(json.dumps(header))
    (run_root / "state.json").write_text('{"status":"completed","workflow_outputs":{"stale":true}}')
    before = _tree_bytes(tmp_path)
    assert report_workflow(run_root.name, runs_root=str(run_root.parent), format="json") == 1
    captured = capsys.readouterr()
    assert "memo_inconsistent" in captured.err
    assert not captured.out
    with pytest.raises(ValueError):
        StateManager(tmp_path, run_root.name).load()
    assert _tree_bytes(tmp_path) == before


def test_public_report_subprocess_reconstructs_without_source_or_state(tmp_path):
    run_root = _pure_run(tmp_path)
    (tmp_path / "evaluated" / "inputs.orc").unlink()
    before = _tree_bytes(tmp_path)
    result = subprocess.run([sys.executable, "-m", "orchestrator", "report", "--run-id", run_root.name,
                             "--runs-root", str(run_root.parent), "--format", "json"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run"]["workflow_outputs"]["score"] == 0.75
    assert _tree_bytes(tmp_path) == before


def test_pure_failed_terminal_reports_its_error_without_outputs(tmp_path, capsys):
    source = tmp_path / "failure.orc"
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule failure) (export run) (defworkflow run ((divisor Float)) -> Float (/ 1.0 divisor)))''')
    result = _run_cli(tmp_path, str(source), "--input", "divisor=0")
    assert result.returncode == 1, result.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    source.unlink()
    before = _tree_bytes(tmp_path)
    assert report_workflow(run_root.name, runs_root=str(run_root.parent), format="json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["status"] == "failed"
    assert payload["run"]["error"]["code"] == "pure_expr_division_by_zero"
    assert payload["run"]["workflow_outputs"] is None
    assert _tree_bytes(tmp_path) == before
