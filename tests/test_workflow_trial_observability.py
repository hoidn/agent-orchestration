from __future__ import annotations

import builtins
import io
import json
import os
from pathlib import Path

import pytest

from orchestrator.cli.commands.report import _state_only_snapshot
from orchestrator.cli.main import main
from tests.test_executor_retirement_cutoff import tree


def test_state_only_trial_report_identifies_kind_without_projecting_or_scanning(
    tmp_path: Path,
) -> None:
    run_dir = (tmp_path / "run").resolve()
    decoy = run_dir / "trials" / "should-not-be-read"
    decoy.mkdir(parents=True)
    (decoy / "authored-arm-id-direct").write_text("secret", encoding="utf-8")
    active = {
        "run_id": "run",
        "status": "running",
        "steps": {},
        "current_step": {
            "name": "Compare",
            "step_id": "root.compare",
            "type": "trial",
            "status": "running",
            "visit_count": 1,
            "duration_ms": 999,
            "output": "active-preview-secret",
            "debug": {"trace": "active-debug-secret"},
        },
    }
    terminal = {
        "run_id": "run",
        "status": "completed",
        "steps": {
            "Compare": {
                "status": "completed",
                "step_id": "root.compare",
                "trial": {"outcomes": [{"arm_id": "direct"}]},
                "duration_ms": 999,
                "output": "terminal-preview-secret",
                "artifacts": {
                    "outcomes": [
                        {
                            "value": "candidate-output-secret",
                            "evidence": {
                                "workspace_delta": {},
                                "child_run_id": "child-secret",
                                "evaluation_label": "evaluation-secret",
                                "scorer_identity": "scorer-secret",
                            },
                        }
                    ]
                },
                "error": {"message": "terminal-error-secret"},
                "outcome": {"reason": "terminal-outcome-secret"},
                "debug": {"trace": "terminal-debug-secret"},
            }
        },
        "current_step": None,
    }

    active_snapshot = _state_only_snapshot(active, run_dir)
    terminal_snapshot = _state_only_snapshot(terminal, run_dir)

    assert active_snapshot["steps"][0]["kind"] == "trial"
    assert terminal_snapshot["steps"][0]["kind"] == "trial"
    assert active_snapshot["steps"][0]["output"] == {}
    assert terminal_snapshot["steps"][0]["output"] == {}
    rendered = json.dumps(terminal_snapshot["steps"][0])
    for forbidden in (
        "direct",
        "duration_ms",
        "candidate-output-secret",
        "workspace_delta",
        "child_run_id",
        "evaluation_label",
        "scorer_identity",
        "terminal-preview-secret",
        "terminal-error-secret",
        "terminal-outcome-secret",
        "terminal-debug-secret",
    ):
        assert forbidden not in rendered

def test_ordinary_report_does_zero_trial_projection_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ordinary_root = (tmp_path / "ordinary" / "run").resolve()
    ordinary_root.mkdir(parents=True)
    imported: list[str] = []
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "orchestrator.workflow.trial.observability":
            imported.append(name)
            raise AssertionError("ordinary report imported trial observability")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    snapshot = _state_only_snapshot(
        {
            "run_id": "ordinary",
            "status": "running",
            "steps": {},
            "current_step": None,
        },
        ordinary_root,
    )

    assert snapshot["progress"]["total"] == 0
    assert imported == []
    assert not (ordinary_root / "trials").exists()


@pytest.mark.parametrize("variant", ("active", "prepared", "committed"))
@pytest.mark.parametrize("report_format", ("json", "md"))
def test_public_report_keeps_historical_trial_state_opaque_and_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    variant: str, report_format: str,
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "historical_trial_observability.json"
    captured = json.loads(fixture.read_bytes())["variants"][variant]
    state = json.loads(json.dumps(captured["state"]).replace("@WORKSPACE@", str(tmp_path)))
    run_root = Path(state["run_root"])
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(json.dumps(state), encoding="utf-8")
    for relative, content in captured["files"].items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    before = tree(tmp_path)
    trial_root = run_root / "trials"
    original_open, original_io_open, original_scandir = builtins.open, io.open, os.scandir
    original_import = builtins.__import__

    def refuse_trial_path(path):
        if isinstance(path, (str, bytes, os.PathLike)):
            assert not Path(os.fsdecode(path)).is_relative_to(trial_root), "report scanned trial evidence"

    def guarded_open(path, *args, **kwargs):
        refuse_trial_path(path)
        return original_open(path, *args, **kwargs)

    def guarded_io_open(path, *args, **kwargs):
        refuse_trial_path(path)
        return original_io_open(path, *args, **kwargs)

    def guarded_scandir(path):
        refuse_trial_path(path)
        return original_scandir(path)

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        assert not name.startswith("orchestrator.workflow.trial"), "report loaded trial execution metadata"
        return original_import(name, globals, locals, fromlist, level)

    with monkeypatch.context() as guard:
        guard.setattr(builtins, "open", guarded_open)
        guard.setattr(io, "open", guarded_io_open)
        guard.setattr(os, "scandir", guarded_scandir)
        guard.setattr(builtins, "__import__", guarded_import)
        assert main(["report", "--run-id", state["run_id"], "--runs-root", str(run_root.parent),
                     "--format", report_format]) == 0
    rendered = capsys.readouterr().out
    if report_format == "json":
        report = json.loads(rendered)
        [step] = report["steps"]
        assert step["kind"] == "trial"
        assert step["output"] == {}
    for private_detail in (
        "trial_observability", "workspace_delta", "child_run_id", "evaluation_label",
        "scorer_identity", "opaque-", "candidate-output", "legacy-preview-secret",
        "legacy-text-secret", "legacy-error-secret", "legacy-outcome-secret", "legacy-debug-secret",
    ):
        assert private_detail not in rendered
    assert tree(tmp_path) == before
