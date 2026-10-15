"""PQ-1a deterministic gate: the real two-agent consumer through the public CLI with the fake CLIs, every failure-table
row and kill point the design names (Verification, Risks And Handoff).

Every orchestrator process here runs with the file-only observation fake (the `_stopped` prelude), including the plain
`_cli` calls: agent-bearing programs open observation, and no real tmux server may start on the host.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_agent_turn_recovery import _FAKE_OBSERVATION, STOP_AFTER_RECEIPT, STOP_AFTER_RECORD, _stopped
from tests.test_workflow_evaluated_agent_turns import memo_of, turns
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.workflow_evaluated_consumer_sources import PROGRAMS, ROOT, Program, design_docs, install

DOC = "artifacts/design/slug.md"
FINAL = "docs/design/slug.md"
RESULTS = {
    "claude": [{"mode": "success", "result": {"doc": DOC}, "files": {DOC: "# draft\n"}},
               {"mode": "success", "result": {"doc": FINAL}, "files": {FINAL: "# final\n"}}],
    "codex": [{"mode": "success", "result": {"blocking": ["b1"], "notes": []}},
              {"mode": "success", "result": {"summary": "done", "commits": ["abc"], "checks_run": ["pytest"], "left_undone": []}}],
}
RUN = ("--input-file", "inputs.json")
DRIVER = _FAKE_OBSERVATION + "import sys\nfrom orchestrator.cli import main\nsys.argv = ['orchestrator', *sys.argv[1:]]\nsys.exit(main())\n"


def _cli(root: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """`orchestrator <argv>` with the fake observation backend."""
    return subprocess.run([sys.executable, "-c", DRIVER, *argv], cwd=root, capture_output=True, text=True, check=False,
                          env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})


def _setup(tmp_path, monkeypatch, plan=RESULTS, program=PROGRAMS["design_review_execute_agents"]) -> list[str]:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)
    return install(tmp_path, program, {"task": "t"}, current=False)


def _plan(tool: str, index: int, mode: str, *, retry: bool) -> dict:
    plan = {k: [dict(s) for s in v] for k, v in RESULTS.items()}
    plan[tool][index] = {**plan[tool][index], "mode": mode}
    if retry:
        plan[tool].insert(index + 1, dict(RESULTS[tool][index]))      # the next attempt answers correctly
    return plan


def _claude_store(root: Path, locator: str) -> Path:
    return next((root / "claude" / "projects").rglob(f"{locator}.jsonl"))


def _foreign_append(root: Path, locator: str) -> None:
    """An operator continues the designer's native session by hand after its draft turn committed."""
    path = _claude_store(root, locator)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    common = {"sessionId": locator, "promptId": "ext", "isSidechain": False}
    rows += [{"type": "user", "uuid": "ext-u", "parentUuid": rows[-1]["uuid"], **common, "message": {"role": "user", "content": "operator"}},
             {"type": "assistant", "uuid": "ext-a", "parentUuid": "ext-u", **common,
              "message": {"id": "msg_ext", "role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}}]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _stop_after_feedback(tmp_path, frontend):
    """Run until the reviewer's first turn settles; the designer's draft is committed and its revise turn not started."""
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "settled", "STOP_TURN": "/ feedback"}, "run", *frontend, *RUN)
    run_root, _a, classes, memo = memo_of(tmp_path)
    assert set(turns(memo, classes)) == {"draft", "feedback"} and len(shim_requests(tmp_path)) == 2
    return run_root, turns(memo, classes)["draft"]["proof"]["locator"]


def test_clean_consumer_run_four_turns_two_sessions_lineage_and_readonly_resume(tmp_path, monkeypatch) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    compiled = _cli(tmp_path, "compile", *frontend)
    assert compiled.returncode == 0 and json.loads(compiled.stdout)["sites"] == 6, compiled.stderr
    run = _cli(tmp_path, "run", *frontend, *RUN)
    assert run.returncode == 0, run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    t = turns(memo, classes)
    assert len(t) == 4 and {"draft", "feedback", "revised"} <= set(t)   # the final execute turn is the anonymous binding
    draft, feedback, revised = t["draft"], t["feedback"], t["revised"]
    assert draft["value"] == {"doc": DOC} and revised["value"] == {"doc": FINAL}
    assert revised["proof"]["predecessor"] == draft["identity"] and draft["identity"] in revised["depends_on"]
    assert feedback["identity"] in revised["depends_on"]
    (execute,) = [v for k, v in t.items() if k not in {"draft", "feedback", "revised"}]
    assert execute["proof"]["predecessor"] == feedback["identity"] and revised["identity"] in execute["depends_on"]
    assert memo.terminal.data["value"] == RESULTS["codex"][1]["result"]
    assert (tmp_path / DOC).read_text() == "# draft\n" and (tmp_path / FINAL).read_text() == "# final\n"
    requests = shim_requests(tmp_path)
    assert [r["tool"] for r in requests] == ["claude", "codex", "claude", "codex"] and len({r["session"] for r in requests}) == 2
    before = _tree_bytes(run_root)
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0 and _tree_bytes(run_root) == before
    assert len(shim_requests(tmp_path)) == 4


def test_completed_consumer_replays_readonly_after_native_sessions_and_receipts_disappear(tmp_path, monkeypatch) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    assert _cli(tmp_path, "run", *frontend, *RUN).returncode == 0
    run_root, *_ = memo_of(tmp_path)
    shutil.rmtree(tmp_path / "codex"); shutil.rmtree(tmp_path / "claude")
    for receipt in (run_root / "effects").rglob("receipt.json"):
        receipt.unlink()
    before = _tree_bytes(run_root)
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert _tree_bytes(run_root) == before and len(shim_requests(tmp_path)) == 4


@pytest.mark.parametrize("tool, index, mode", [
    ("codex", 0, "interrupted"),        # reviewer first turn, unknown outcome after the committed draft
    ("codex", 0, "invalid-result"),     # reviewer first turn, invalid typed result after native success
    ("codex", 0, "missing-result"),     # reviewer first turn, no typed result after native success
])
def test_reviewer_first_turn_failure_bootstraps_only_a_fresh_reviewer_on_explicit_resume(tmp_path, monkeypatch, tool, index, mode) -> None:
    frontend = _setup(tmp_path, monkeypatch, _plan(tool, index, mode, retry=True))
    assert _cli(tmp_path, "run", *frontend, *RUN).returncode == 1
    run_root, _a, classes, memo = memo_of(tmp_path)
    assert set(turns(memo, classes)) == {"draft"}
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert "agent_bootstrap_restarted" in resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    t = turns(after, classes)
    assert after.terminal.data["outcome"] == "completed" and len(t) == 4
    assert t["draft"]["attempt"] == 1 and t["feedback"]["attempt"] == 2          # the designer's committed draft is kept
    codex = [r for r in shim_requests(tmp_path) if r["tool"] == "codex"]
    assert len(codex) == 3 and codex[0]["session"] != codex[1]["session"] == codex[2]["session"]
    assert "resume" not in codex[1]["argv"]                                      # a fresh candidate, never the abandoned one


@pytest.mark.parametrize("tool, index, mode, code", [
    ("claude", 1, "interrupted", "agent_turn_unresolved"),         # designer's second turn: unknown outcome
    ("claude", 1, "invalid-result", "agent_turn_result_invalid"),  # designer's second turn: invalid output after native success
    ("claude", 1, "missing-result", "agent_turn_result_invalid"),  # designer's second turn: no result file after native success
    ("codex", 1, "nonzero", "agent_turn_unresolved"),              # open head after a nonzero exit: uncertainty
])
def test_later_turn_failure_refuses_on_resume_without_any_write(tmp_path, monkeypatch, tool, index, mode, code) -> None:
    frontend = _setup(tmp_path, monkeypatch, _plan(tool, index, mode, retry=False))
    run = _cli(tmp_path, "run", *frontend, *RUN)
    assert run.returncode == 1 and code in run.stderr, run.stderr
    run_root, *_ = memo_of(tmp_path)
    memo_bytes = (run_root / "memo.jsonl").read_bytes()
    dispatched = len(shim_requests(tmp_path))
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 2 and code in resumed.stderr, resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == memo_bytes and len(shim_requests(tmp_path)) == dispatched


def test_proven_undispatched_later_turn_failure_resumes_with_the_next_attempt(tmp_path, monkeypatch) -> None:
    """Exit before any native append on the reviewer's execute turn: the adapter proves the head unchanged, the attempt
    closes `failed` and resume runs an ordinary next attempt on the same session."""
    frontend = _setup(tmp_path, monkeypatch, _plan("codex", 1, "nonzero-before-append", retry=True))
    assert _cli(tmp_path, "run", *frontend, *RUN).returncode == 1
    run_root, _a, _c, memo = memo_of(tmp_path)
    assert memo.terminal.data["outcome"] == "failed" and not memo.pending_starts
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    t = turns(after, classes)
    assert after.terminal.data["value"]["summary"] == "done" and len(t) == 4
    assert [v["attempt"] for k, v in t.items() if k not in {"draft", "feedback", "revised"}] == [2]
    codex = [r for r in shim_requests(tmp_path) if r["tool"] == "codex"]
    assert len({r["session"] for r in codex}) == 1          # the exited call logged nothing; the retry resumed the session


def test_external_advancement_of_the_designer_refuses_before_dispatch(tmp_path, monkeypatch) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    run_root, locator = _stop_after_feedback(tmp_path, frontend)
    _foreign_append(tmp_path, locator)
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 1 and "agent_session_diverged" in resumed.stderr, resumed.stderr
    _r, _a, _c, memo = memo_of(tmp_path)
    assert not any(e.data["record"] == "started" and e.data["identity"].endswith("/ revised") for e in memo.entries)
    assert len(shim_requests(tmp_path)) == 2


def test_lost_designer_session_refuses_before_dispatch(tmp_path, monkeypatch) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    run_root, locator = _stop_after_feedback(tmp_path, frontend)
    _claude_store(tmp_path, locator).unlink()
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 1 and "agent_session_unavailable" in resumed.stderr, resumed.stderr
    assert locator not in resumed.stderr                    # diagnostics never carry the native locator
    assert len(shim_requests(tmp_path)) == 2


def test_claude_filename_session_mismatch_refuses_before_dispatch_without_native_details(tmp_path, monkeypatch) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    run_root, locator = _stop_after_feedback(tmp_path, frontend)
    native_path = _claude_store(tmp_path, locator)
    rows = [json.loads(line) for line in native_path.read_text().splitlines()]
    foreign_id = "a35c7d52-28a9-4c42-a589-f206f2e112c9"
    for row in rows:
        row["sessionId"] = foreign_id
    native_path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    resumed = _cli(tmp_path, "resume", run_root.name)

    assert resumed.returncode == 1 and "agent_session_unavailable" in resumed.stderr, resumed.stderr
    _root, _authority, _classes, memo = memo_of(tmp_path)
    assert not any(row.data["record"] == "started" and row.data["identity"].endswith("/ revised") for row in memo.entries)
    assert len(shim_requests(tmp_path)) == 2
    outputs = [resumed.stderr, (run_root / "state.json").read_text()]
    for fmt in ("json", "md"):
        report = _cli(tmp_path, "report", "--run-id", run_root.name, "--format", fmt)
        assert report.returncode == 0, report.stderr
        outputs.append(report.stdout)
    secrets = (locator, foreign_id, str(native_path), str(tmp_path / "claude"))
    assert all(secret not in output for secret in secrets for output in outputs)


@pytest.mark.parametrize("hook, env, retried", [
    (STOP_AFTER_RECORD, {"STOP_RECORD": "started", "STOP_TURN": "/ draft"}, "draft"),          # before intent
    (STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "intent", "STOP_TURN": "/ feedback"}, "feedback"),  # after intent
    (STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "completed", "STOP_TURN": "/ revised"}, None),  # after native completion
    (STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "proof", "STOP_TURN": "/ feedback"}, None),     # after proof persistence
    (STOP_AFTER_RECORD, {"STOP_RECORD": "committed", "STOP_TURN": "/ revised"}, None),         # after memo commit
    (STOP_AFTER_RECORD, {"STOP_RECORD": "settled", "STOP_TURN": "/ draft"}, None),             # after settlement
], ids=["started", "intent", "completed", "proof", "committed", "settled"])
def test_every_kill_point_resumes_to_the_same_value_without_a_turn_running_twice(tmp_path, monkeypatch, hook, env, retried) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    _stopped(tmp_path, hook, env, "run", *frontend, *RUN)
    run_root, *_ = memo_of(tmp_path)
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, memo = memo_of(tmp_path)
    assert memo.terminal.data["value"] == RESULTS["codex"][1]["result"]
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude", "codex", "claude", "codex"]   # each turn dispatched once
    t = turns(memo, classes)
    assert len(t) == 4 and {k for k, v in t.items() if v["attempt"] != 1} == ({retried} if retried else set())


def test_invalidating_feedback_is_refused_after_revised_committed_but_the_baseline_consumer_allows_it(tmp_path, monkeypatch) -> None:
    frontend = _setup(tmp_path / "agents", monkeypatch)
    assert _cli(tmp_path / "agents", "run", *frontend, *RUN).returncode == 0
    run_root, _a, _c, memo = memo_of(tmp_path / "agents")
    before = _tree_bytes(run_root)
    refused = _cli(tmp_path / "agents", "invalidate", run_root.name, next(i for i in memo.active_commits if i.endswith("/ feedback")))
    assert refused.returncode == 2 and "invalidate_coordinator_committed" in refused.stderr, refused.stderr
    assert _tree_bytes(run_root) == before
    baseline = Program("workflows/examples/design_review_execute.orc", "2.35", "design_review_execute::run", "workflows/examples",
                       {"providers": "workflows/examples/inputs/design_review_execute/providers.json"}, prepare=design_docs)
    frontend = _setup(tmp_path / "baseline", monkeypatch, program=baseline)
    assert _cli(tmp_path / "baseline", "run", *frontend, *RUN).returncode == 0
    run_root, _a, _c, memo = memo_of(tmp_path / "baseline")
    done = _cli(tmp_path / "baseline", "invalidate", run_root.name, next(i for i in memo.active_commits if i.endswith("/ feedback")))
    assert done.returncode == 0, done.stderr


def test_corrupt_receipt_of_a_pending_turn_refuses_on_resume_without_any_write(tmp_path, monkeypatch) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "completed", "STOP_TURN": "/ revised"}, "run", *frontend, *RUN)
    run_root, _a, _c, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts.values()
    (run_root / Path(pending.data["result_path"]).parent / "receipt.json").write_text("{not json")
    memo_bytes = (run_root / "memo.jsonl").read_bytes()
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 2 and "memo_inconsistent" in resumed.stderr, resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == memo_bytes and len(shim_requests(tmp_path)) == 3
