"""Readers show agent identity and continuation without locators; a pending unresolved turn is `running`."""
from __future__ import annotations

import json
import os

import pytest

from orchestrator.workflow.evaluated.views import load_evaluated_view
from tests.agent_session_shims import install_agent_shims
from tests.test_workflow_evaluated_agent_turns import PLAN, fixture, memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli


def _short(view):
    return {k.rsplit("/ ", 1)[1]: v for k, v in view["steps"].items()}


def test_view_rows_carry_agent_identity_and_continuation(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    run_root, _authority, classes, memo = memo_of(tmp_path)
    view = load_evaluated_view(run_root)
    rows = _short(view)
    t = turns(memo, classes)
    assert [rows[k]["continuation"] for k in ("a1", "b1", "a2", "b2")] == ["initial", "initial", "continued", "continued"]
    assert (rows["a1"]["predecessor"], rows["a2"]["predecessor"]) == (None, t["a1"]["identity"])
    assert rows["a2"]["agent"] == t["a2"]["proof"]["agent"] and rows["a2"]["agent"].endswith("/ designer")
    assert all(rows[k]["locator_present"] is True for k in ("a1", "b1", "a2", "b2"))
    assert rows["designer"]["effect_class"] == "agent" and rows["designer"]["agent"] == rows["a1"]["agent"]
    assert all(v["status"] == "completed" for v in rows.values())
    assert json.loads((run_root / "state.json").read_text())["steps"] == view["steps"]


def test_no_locator_or_position_reaches_state_or_report(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    run_root, _authority, classes, memo = memo_of(tmp_path)
    proofs = [row["proof"] for row in turns(memo, classes).values()]
    secrets = {p["locator"] for p in proofs} | {p["position"]["turn_id"] for p in proofs}
    outputs = [(run_root / "state.json").read_text()]
    for fmt in ("json", "md"):
        report = _cli(tmp_path, "report", "--run-id", run_root.name, "--format", fmt)
        assert report.returncode == 0, report.stderr
        outputs.append(report.stdout)
    assert "- continuation: `continued`" in outputs[-1] and "- agent: `" in outputs[-1]   # md keeps the logical fields
    for text in outputs:
        assert not [s for s in secrets if str(s) in text]
        assert not [k for k in ('"locator"', '"position"', "end_line", "turn_id", "tmux", "%pane") if k in text]


def test_pending_unresolved_turn_is_running_and_report_succeeds(tmp_path, monkeypatch) -> None:
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": "interrupted", "result": {}}], "codex": PLAN["codex"]}
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 1
    run_root, *_ = memo_of(tmp_path)
    view = load_evaluated_view(run_root)
    row = _short(view)["a2"]
    assert row["status"] == "running" and view["status"] == "interrupted" and view["current_step"]["identity"].endswith("/ a2")
    report = _cli(tmp_path, "report", "--run-id", run_root.name, "--format", "json")
    assert report.returncode == 0, report.stderr
    assert json.loads(report.stdout)["progress"]["running"] == 1


@pytest.mark.parametrize("change", ["missing", "advanced"])
def test_d1_refusal_reaches_state_and_report_without_native_facts(tmp_path, monkeypatch, change) -> None:
    """Task 14 review: the run is killed after a1 settles; before resume the designer's native session is deleted
    (`agent_session_unavailable`) or advanced by hand (`agent_session_diverged`). a2's D1 refusal becomes the failed
    terminal's message, which the view and both report formats publish; none of them may carry the locator, the
    recorded position or the native store path."""
    import shutil
    import subprocess
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECORD, _stopped
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": "success", "result": {"text": "by hand"}}], "codex": PLAN["codex"]}
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "settled", "STOP_TURN": "/ a1"}, "run", *fixture(tmp_path))
    run_root, _authority, classes, memo = memo_of(tmp_path)
    proof = turns(memo, classes)["a1"]["proof"]
    if change == "missing":
        shutil.rmtree(tmp_path / "claude")
    else:
        subprocess.run([str(tmp_path / "bin" / "claude"), "-p", "--resume", proof["locator"]], input=b"by hand", cwd=tmp_path,
                       check=True, env={**os.environ, "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(tmp_path / "by-hand.json")})
    code = {"missing": "agent_session_unavailable", "advanced": "agent_session_diverged"}[change]
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 1 and code in resumed.stderr, resumed.stderr
    secrets = [proof["locator"], proof["position"]["turn_id"], str(tmp_path / "claude")]
    outputs = [(run_root / "state.json").read_text(), resumed.stderr]
    assert code in outputs[0]
    for fmt in ("json", "md"):
        report = _cli(tmp_path, "report", "--run-id", run_root.name, "--format", fmt)
        assert report.returncode == 0, report.stderr
        outputs.append(report.stdout)
    assert not [(i, s) for i, text in enumerate(outputs) for s in secrets if s in text]
