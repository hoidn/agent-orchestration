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
    _improve_plan,
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
    checked_run,
    flat_outputs,
    install,
    install_shims,
    jsonl,
    r3,
    requests,
    ROOT,
)
from tests.workflow_evaluated_totality_helpers import assert_commit_bytes


VARIANT = ROOT / "experiments/orc_repetition_census/variants/phase6a_proposal.orc.txt"
REVIEW = "decision=procedure:improve_experiment_proposal::review-proposal"
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
