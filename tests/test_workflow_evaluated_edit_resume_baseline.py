"""Phase 3b T1 controls: what the base resumes and refuses today, which resume under an edited program must keep.

Every test drives the public command line with local stand-ins on a closed PATH; no model is called. The
recorded run roots under `tests/fixtures/declaration_pre_change/` were written by the base before the
`declaration` digest changes (README there) and are never regenerated.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.agent_session_shims import FAKE_CLAUDE, FAKE_CODEX, closed_path

ROOT = Path(__file__).resolve().parents[1]
RECORDED = Path(__file__).parent / "fixtures" / "declaration_pre_change"
# Where the cases were recorded. An agent allocation's pinned configuration binds the launch cwd, so a run root
# with an agent turn still to dispatch or recover resumes only in its recorded workspace (README).
RECORDED_AT = Path("/tmp/orc-declaration-pre-change")


@contextmanager
def _recorded_workspace(case: str):
    """The case's recorded workspace path, held exclusively by this process (other sessions may run this test)."""
    RECORDED_AT.mkdir(exist_ok=True)
    with (RECORDED_AT.parent / f"{RECORDED_AT.name}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        root = RECORDED_AT / case
        shutil.rmtree(root, ignore_errors=True)
        try:
            yield root
        finally:
            shutil.rmtree(root, ignore_errors=True)


def _shim(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
    path.chmod(0o700)


def _cli(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "orchestrator", *args], cwd=root, capture_output=True, text=True,
                          timeout=120, check=False,
                          env={**os.environ, **env, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})


def _rows(run_root: Path) -> list[dict]:
    return [json.loads(line) for line in (run_root / "memo.jsonl").read_text(encoding="utf-8").splitlines()]


def _recorded(case: str, root: Path) -> tuple[Path, dict[str, str]]:
    """The recorded workspace and run root in `root`, with the case's stand-ins on a closed PATH."""
    source = RECORDED / case
    shutil.copytree(source, root, ignore=shutil.ignore_patterns("runs", "README.md"), dirs_exist_ok=True)
    shutil.copytree(source / "runs", root / ".orchestrate" / "runs")
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    for path in run_root.rglob("*"):        # git keeps no 0600 mode; the run wrote its files 0600 (README)
        if path.is_file():
            path.chmod(0o600)
    env = {"PATH": closed_path(root / "bin")}
    if case == "provider_committed":
        _shim(root / "bin" / "codex", (source / "codex_shim.py").read_text(encoding="utf-8"))
    elif case.startswith("agent"):
        _shim(root / "bin" / "codex", FAKE_CODEX)
        _shim(root / "bin" / "claude", FAKE_CLAUDE)
        env.update(CODEX_HOME=str(root / "codex"), CLAUDE_CONFIG_DIR=str(root / "claude"))
    else:
        _shim(root / "bin" / "codex", (ROOT / "tests/fixtures/providers/fake_phased_interactive.py").read_text())
        env["ORC_FAKE_PHASED_MODE"] = "success"
    return run_root, env


def _new_rows(run_root: Path, recorded: list[dict], record: str) -> list[dict]:
    rows = _rows(run_root)
    assert rows[:len(recorded)] == recorded
    return [row for row in rows[len(recorded):] if row["record"] == record]


def test_recorded_committed_provider_resumes_on_the_base_without_dispatch(tmp_path) -> None:
    run_root, env = _recorded("provider_committed", tmp_path)
    recorded = _rows(run_root)

    resumed = _cli(tmp_path, env, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert _rows(run_root) == recorded
    assert not (tmp_path / "requests.jsonl").exists()


def test_recorded_committed_agent_turns_resume_on_the_base_without_dispatch(tmp_path) -> None:
    run_root, env = _recorded("agent_turns_committed", tmp_path)
    recorded = _rows(run_root)

    resumed = _cli(tmp_path, {**env, "AGENT_SHIM_PLAN": "{}"}, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert _rows(run_root) == recorded
    assert not list((tmp_path / "bin").glob(".*.calls"))


def test_recorded_pending_agent_turn_is_recovered_on_the_base_at_its_ordinal() -> None:
    with _recorded_workspace("agent_turn_pending") as root:
        _pending_agent_turn_is_recovered(root)


def test_recorded_pending_agent_turn_refuses_on_the_base_in_another_workspace(tmp_path) -> None:
    """What the README says: the allocation pinned its cwd, so this run root does not relocate."""
    run_root, env = _recorded("agent_turn_pending", tmp_path)
    recorded = _rows(run_root)

    resumed = _cli(tmp_path, {**env, "AGENT_SHIM_PLAN": "{}"}, "resume", run_root.name)

    assert resumed.returncode == 2 and "[agent_policy_mismatch]" in resumed.stderr
    assert _rows(run_root) == recorded


def _pending_agent_turn_is_recovered(tmp_path: Path) -> None:
    run_root, env = _recorded("agent_turn_pending", tmp_path)
    recorded = _rows(run_root)
    (pending,) = [row for row in recorded if row["record"] == "started" and row["identity"].endswith("/ b1")]
    plan = {"claude": [{"mode": "success", "result": {"text": "d2"}}], "codex": [{"mode": "success", "result": {"notes": ["done"]}}]}

    resumed = _cli(tmp_path, {**env, "AGENT_SHIM_PLAN": json.dumps(plan)}, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    started = _new_rows(run_root, recorded, "started")
    assert [row["identity"].rsplit("/ ", 1)[1] for row in started] == ["a2", "b2"]
    (b1,) = [row for row in _new_rows(run_root, recorded, "committed") if row["identity"] == pending["identity"]]
    assert b1["attempt"] == 1 and b1["input_digest"] == pending["input_digest"]
    requests = [json.loads(line) for line in (tmp_path / "requests.jsonl").read_text().splitlines()]
    assert [request["tool"] for request in requests] == ["claude", "codex"]


def test_recorded_committed_phased_provider_reconciles_on_the_base_without_dispatch(tmp_path) -> None:
    run_root, env = _recorded("phased_committed", tmp_path)
    recorded = _rows(run_root)
    (phased,) = [row for row in recorded if row["record"] == "committed"]

    resumed = _cli(tmp_path, env, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert [row["identity"] for row in _new_rows(run_root, recorded, "settled")] == [phased["identity"]]
    assert phased["identity"] not in {row["identity"] for row in _new_rows(run_root, recorded, "started")}
    assert _rows(run_root)[-1] == {"record": "terminal", "outcome": "completed", "value": 9}
    assert not (tmp_path / "phased-events.jsonl").exists()


def test_recorded_pending_phased_attempt_refuses_on_the_base_without_its_transport_namespace(tmp_path) -> None:
    """The prepared attempt's receipt names a transport reservation under /tmp (by device and inode), which no
    other host and no later boot has. The base refuses before any write or dispatch: this run root does not
    relocate (README), and a pending phased attempt is stranded once /tmp is cleared."""
    run_root, env = _recorded("phased_pending", tmp_path)
    (start,) = [row for row in _rows(run_root) if row["record"] == "started"]
    receipt = json.loads((run_root / start["result_path"]).with_name("phased-attempt.json").read_text())
    if (Path("/tmp") / receipt["transport"]["namespace"]).exists():
        pytest.skip("the recording host still holds this reservation")
    before = {path: path.read_bytes() for path in run_root.rglob("*") if path.is_file() and path.name != "run.lock"}

    resumed = _cli(tmp_path, env, "resume", run_root.name)

    assert resumed.returncode == 2 and "[provider_phased_cleanup_failed]" in resumed.stderr
    assert {path: path.read_bytes() for path in run_root.rglob("*") if path.is_file() and path.name != "run.lock"} == before
    assert not (tmp_path / "phased-events.jsonl").exists()


# Claim 4: the bare `--accept-changes` keeps its meaning. It accepts only unproven command attempts' changed files;
# never an edited program, never a committed step whose input changed, with or without an unproven attempt.

def _four_steps(root: Path, *, unproven: bool) -> None:
    """A completed four-step run, or one whose `s4` failed after writing its own script (an unproven attempt)."""
    from tests.test_workflow_evaluated_script_fix_retry import SELF_WRITE, fix, run_four, write_four_steps
    write_four_steps(root, {"s4": SELF_WRITE} if unproven else None)
    assert run_four(root).returncode == (1 if unproven else 0)
    if unproven:
        fix(root, "s4")


@pytest.mark.parametrize("unproven", [False, True], ids=["completed", "with_unproven_attempt"])
def test_bare_flag_never_accepts_an_edited_program(tmp_path: Path, unproven: bool) -> None:
    from tests.test_workflow_evaluated_script_fix_retry import refuses_without_writes
    _four_steps(tmp_path, unproven=unproven)
    source = tmp_path / "main.orc"
    source.write_text(source.read_text().replace('("python" "s2.py" a)', '("python" "s2.py" (+ a 1))'))

    refuses_without_writes(tmp_path, "resume_program_changed")
    refuses_without_writes(tmp_path, "resume_program_changed", "--accept-changes")


@pytest.mark.parametrize("unproven", [False, True], ids=["completed", "with_unproven_attempt"])
def test_bare_flag_never_accepts_a_committed_divergence(tmp_path: Path, unproven: bool) -> None:
    from tests.test_workflow_evaluated_script_fix_retry import IDENTITIES, refuses_without_writes
    _four_steps(tmp_path, unproven=unproven)
    (tmp_path / "s2.py").write_text((tmp_path / "s2.py").read_text() + "# a committed step's script changed\n")

    plain = refuses_without_writes(tmp_path, "effect_input_diverged")
    flagged = refuses_without_writes(tmp_path, "effect_input_diverged", "--accept-changes")

    assert IDENTITIES["s2"] in plain.stderr.splitlines()[0] and IDENTITIES["s2"] in flagged.stderr.splitlines()[0]


# Claim 9: cancelling commits refunds nothing. `report` sums every attempt of every row and the spend cap sums
# every attempt directory, also of attempts a C8 range cancelled.

def test_invalidated_provider_attempts_stay_counted_by_report_and_the_cap(tmp_path: Path) -> None:
    from tests.test_workflow_evaluated_report_usage import ONE_CALL, _report
    from tests.test_workflow_evaluated_spend_cap import BELOW_ONE_CALL, _calls, _capped, _run, _run_id
    from tests.test_workflow_evaluated_provider_usage import _orchestrator
    root = _capped(tmp_path)
    assert _run(root).returncode == 0 and _calls(root) == 2
    first = "workflow:main::run / first"
    assert _orchestrator(root, "invalidate", _run_id(root), first).returncode == 0

    cancelled = _report(root)
    assert {step["identity"]: step["status"] for step in cancelled["steps"]}[first] == "invalidated"
    assert (cancelled["run"]["usage"]["attempts"], cancelled["run"]["usage"]["cost_usd"]) == (2, pytest.approx(2 * ONE_CALL))
    capped = _orchestrator(root, "resume", _run_id(root), "--max-cost-usd", BELOW_ONE_CALL)
    assert capped.returncode == 1 and "[spend_cap_reached]" in capped.stderr and _calls(root) == 2

    resumed = _orchestrator(root, "resume", _run_id(root), "--max-cost-usd", "100")
    assert resumed.returncode == 0, resumed.stderr
    total = _report(root)["run"]["usage"]
    assert _calls(root) == 4 and (total["attempts"], total["cost_usd"]) == (4, pytest.approx(4 * ONE_CALL))
