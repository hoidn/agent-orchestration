"""A local 2.35 proposal edit with a stable 2.33 route as its baseline."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.test_workflow_evaluated_consumers import (
    BLOCKED_LAUNCH,
    BUGGY,
    CHANGE,
    REDO,
    REVIEWED,
    _files as _consumer_files,
    _improve_plan,
    _owners as _consumer_owners,
    _predecessors as _consumer_predecessors,
    _review,
)
from tests.test_workflow_lisp_improve_example_e2e import (
    APPROVED_LAUNCH,
    EXHAUSTED_LAUNCH,
    QUESTION,
)
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_verified_drain import STOP_AFTER_COMMIT
from tests.workflow_evaluated_consumer_sources import (
    BUNDLE,
    PROGRAMS,
    SITE,
    Route,
    assert_request_lineage,
    checked_run,
    flat_outputs,
    install,
    install_shims,
    jsonl,
    lineage,
    missing_edges,
    r3,
    requests,
    request_view,
    ROOT,
)
from tests.workflow_evaluated_totality_helpers import assert_commit_bytes


VARIANT = ROOT / "experiments/orc_repetition_census/variants/phase6a_proposal.orc.txt"
REVIEWED_VARIANT = ROOT / "experiments/orc_repetition_census/variants/phase6a_reviewed_change.orc.txt"
REVIEW = "decision=procedure:improve_experiment_proposal::review-proposal"
REVIEWED_STOP = "review-for-improve"
FOCI = ("scope-marker:focus-a7c4", "scope-marker:focus-b2d9")
SCENARIOS = [
    pytest.param(("REVISE", "APPROVE"), APPROVED_LAUNCH, id="approved"),
    pytest.param(("REVISE", "BLOCKED"), BLOCKED_LAUNCH, id="blocked"),
    pytest.param(("REVISE",) * 3, EXHAUSTED_LAUNCH, id="exhausted"),
]


def _capture(root: Path, argv: list[str], extra_env: dict[str, str] | None = None):
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        **(extra_env or {}),
    }
    result = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, check=False)
    trace = root.parent / f"{root.name}-public-cli.jsonl"
    with trace.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "cwd": str(root),
            "argv": argv,
            "env": {key: env[key] for key in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "STOP_AFTER_COMMIT")
                    if key in env},
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }) + "\n")
    return result


def _effective_request(request: dict) -> tuple:
    env = {key: value for key, value in request["env"].items() if key not in (BUNDLE, SITE)}
    return request["tool"], request["argv"], env, r3(request)


def _run_baseline(root: Path, monkeypatch, plan: dict) -> Route:
    install_shims(root.parent / "bin", monkeypatch, plan)
    frontend = install(root, PROGRAMS["improve"], {"question": QUESTION}, current=False)
    result = _capture(root, [sys.executable, "-m", "orchestrator", "run", *frontend,
                            "--input-file", "inputs.json"])
    assert result.returncode == 0, result.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    state = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
    return Route(root, state["workflow_outputs"], requests(root))


def _run_variant(root: Path, frontend: list[str], focus: str, marker: str) -> Route:
    compiled = _capture(root, [sys.executable, "-m", "orchestrator", "compile", *frontend,
                               "--diagnostics-json"])
    assert compiled.returncode == 0, compiled.stderr
    dry_run = _capture(root, [sys.executable, "-m", "orchestrator", "run", *frontend,
                              "--input-file", "inputs.json", "--dry-run"])
    assert dry_run.returncode == 0, dry_run.stderr
    stopped = _capture(root, [sys.executable, "-c", STOP_AFTER_COMMIT,
                              "run", *frontend, "--input-file", "inputs.json"],
                       {"STOP_AFTER_COMMIT": marker})
    assert stopped.returncode == 75, stopped.stderr

    authority, paused = checked_run(root)
    last = paused.entries[-1].data
    assert (paused.terminal, last["record"], marker in last["identity"]) == (None, "committed", True)
    assert len(paused.active_commits) == len(requests(root)) == 1
    prefix = authority.memo_path.read_bytes()
    paused_requests = requests(root)
    assert focus in paused_requests[0]["prompt"]
    return _resume_and_replay(root, authority, prefix, paused_requests)


def _resume_and_replay(root: Path, authority, prefix: bytes, paused_requests: list[dict]) -> Route:
    resumed = _capture(root, [sys.executable, "-m", "orchestrator", "resume", authority.run_root.name])
    assert resumed.returncode == 0, resumed.stderr
    authority, snapshot = checked_run(root)
    assert authority.memo_path.read_bytes().startswith(prefix)
    assert snapshot.terminal.data["outcome"] == "completed"
    for entry in snapshot.active_commits.values():
        assert_commit_bytes(authority, entry)
    completed_before = _tree_bytes(root)
    replay = _capture(root, [sys.executable, "-m", "orchestrator", "resume", authority.run_root.name])
    assert replay.returncode == 0, replay.stderr
    assert _tree_bytes(root) == completed_before
    return Route(root, snapshot.terminal.data["value"], requests(root), authority, snapshot, paused_requests)


def _assert_outcome_and_launcher(old: Route, new: Route, launch: dict) -> None:
    assert old.value == flat_outputs(new.value)
    assert new.value == {"status": "launched" if launch["outcome"] == "approved" else "held"}
    assert jsonl(old.root / "scripts/launch_experiment.log") == [launch]
    assert jsonl(new.root / "scripts/launch_experiment.log") == [launch]
    assert set(new.started().values()) == {1}


def _assert_hook_inputs(old: Route, new: Route, focus: str, verdicts: tuple[str, ...]) -> None:
    review_requests, revise_requests = new.requests[::2], new.requests[1::2]
    assert len(review_requests) == len(old.requests[::2])
    assert all(focus in request["prompt"] for request in review_requests)
    assert all(focus not in request["prompt"] for request in revise_requests)
    assert [_effective_request(request) for request in old.requests[1::2]] == [
        _effective_request(request) for request in revise_requests
    ]
    assert len(new.paused) == 1
    assert len(new.requests) == 2 * len(verdicts) - (verdicts[-1] != "REVISE")


@pytest.mark.parametrize("verdicts,launch", SCENARIOS)
@pytest.mark.parametrize("focus", FOCI)
def test_proposal_review_focus_is_review_only_and_survives_public_resume(
    tmp_path, monkeypatch, verdicts, launch, focus,
):
    plan = _improve_plan(*verdicts)
    old = _run_baseline(tmp_path / "old", monkeypatch, plan)
    new_root = tmp_path / "new"
    inputs = {"question": QUESTION, "review_focus": focus}
    frontend = install(new_root, PROGRAMS["improve"], inputs, current=True)
    (new_root / PROGRAMS["improve"].source).write_text(VARIANT.read_text(encoding="utf-8"), encoding="utf-8")
    new = _run_variant(new_root, frontend, focus, REVIEW)
    _assert_outcome_and_launcher(old, new, launch)
    _assert_hook_inputs(old, new, focus, verdicts)


REVIEWED_CASES = [
    pytest.param(case.values[0], REVIEWED_STOP, 2, case.values[3], id=case.id)
    for case in REVIEWED
]
REVIEWED_CASES.extend([
    pytest.param(
        {"claude": [CHANGE], "codex": [_review("APPROVE", 1, notes=["fine"])]},
        REVIEWED_STOP,
        2,
        {"variant": "READY", "report": "artifacts/review/round-1.md", "rounds": 1},
        id="approved-first-review",
    ),
    pytest.param(
        {
            "claude": [CHANGE, REDO, REDO],
            "codex": [
                _review("WRONG_APPROACH", 1, reason="change the caller"),
                _review("WRONG_APPROACH", 2, reason="replace the core"),
                _review("WRONG_APPROACH", 3, reason="last design rejection"),
            ],
        },
        REVIEWED_STOP,
        2,
        {"variant": "UNRESOLVED", "reason": "last design rejection", "rounds": 3},
        id="wrong-approach-at-final-round",
    ),
])


def _run_reviewed_baseline(root: Path, plan: dict, inputs: dict) -> Route:
    program = PROGRAMS["reviewed_change"]
    frontend = install(root, program, inputs, current=False)
    result = _capture(root, [sys.executable, "-m", "orchestrator", "run", *frontend,
                            "--input-file", "inputs.json"])
    assert result.returncode == 0, result.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    state = json.loads((run_root / "state.json").read_text(encoding="utf-8"))
    return Route(root, state["workflow_outputs"], requests(root))


def _run_reviewed_variant(root: Path, frontend: list[str], marker: str) -> Route:
    compiled = _capture(root, [sys.executable, "-m", "orchestrator", "compile", *frontend,
                               "--diagnostics-json"])
    assert compiled.returncode == 0, compiled.stderr
    dry_run = _capture(root, [sys.executable, "-m", "orchestrator", "run", *frontend,
                              "--input-file", "inputs.json", "--dry-run"])
    assert dry_run.returncode == 0, dry_run.stderr
    stopped = _capture(root, [sys.executable, "-c", STOP_AFTER_COMMIT,
                              "run", *frontend, "--input-file", "inputs.json"],
                       {"STOP_AFTER_COMMIT": marker})
    assert stopped.returncode == 75, stopped.stderr

    authority, paused = checked_run(root)
    last = paused.entries[-1].data
    assert (paused.terminal, last["record"], marker in last["identity"]) == (None, "committed", True)
    assert len(paused.active_commits) == len(requests(root)) == 2
    prefix = authority.memo_path.read_bytes()
    paused_requests = requests(root)
    return _resume_and_replay(root, authority, prefix, paused_requests)


@pytest.mark.parametrize("plan,marker,paused_count,value", REVIEWED_CASES)
def test_reviewed_change_reuses_improve_without_changing_its_contract(
    tmp_path, monkeypatch, plan, marker, paused_count, value,
):
    install_shims(tmp_path / "bin", monkeypatch, plan)
    inputs = {"task": "Fix add in repo/calc.py so that it returns the sum.",
              "intent": "add returns a + b", "repo": "repo"}
    old = _run_reviewed_baseline(tmp_path / "old", plan, inputs)
    new_root = tmp_path / "new"
    program = PROGRAMS["reviewed_change"]
    frontend = install(new_root, program, inputs, current=True)
    (new_root / program.source).write_text(REVIEWED_VARIANT.read_text(encoding="utf-8"), encoding="utf-8")
    new = _run_reviewed_variant(new_root, frontend, marker)
    _assert_reviewed_contract(old, new, plan, value, paused_count)


def _assert_reviewed_contract(old: Route, new: Route, plan: dict, value: dict, paused_count: int) -> None:
    _assert_reviewed_values_and_requests(old, new, value, plan)
    _assert_reviewed_lifecycle(new, plan, paused_count)
    _assert_reviewed_artifacts(old, new, plan)
    assert_request_lineage(new)


def _assert_reviewed_values_and_requests(old: Route, new: Route, value: dict, plan: dict) -> None:
    calls = len(plan["claude"]) + len(plan["codex"])
    expected_tools = [tool for _ in range(len(plan["codex"])) for tool in ("claude", "codex")]
    assert new.value == value
    assert old.value == flat_outputs(new.value)
    assert request_view(new) == request_view(old)
    assert [request["tool"] for request in new.requests] == expected_tools
    assert len(new.requests) == calls


def _assert_reviewed_lifecycle(new: Route, plan: dict, paused_count: int) -> None:
    calls = len(plan["claude"]) + len(plan["codex"])
    assert len(new.paused) == paused_count
    assert len(new.started()) == calls
    assert set(new.started().values()) == {1}
    assert all(effect_class == "provider" for effect_class, _ in _consumer_owners(new))
    assert lineage(new)[0] == []
    assert missing_edges(new, _consumer_predecessors(calls)) == [[]] * calls


def _assert_reviewed_artifacts(old: Route, new: Route, plan: dict) -> None:
    reports = {name: text.encode() for answer in plan["codex"] for name, text in answer.get("files", {}).items()}
    repo_files = {"calc.py": BUGGY.encode(), **{
        name.removeprefix("repo/"): text.encode()
        for answer in plan["claude"] for name, text in answer.get("files", {}).items()
    }}
    assert _consumer_files(old.root, "artifacts") == reports
    assert _consumer_files(new.root, "artifacts") == reports
    assert _consumer_files(old.root / "repo", ".") == repo_files
    assert _consumer_files(new.root / "repo", ".") == repo_files
