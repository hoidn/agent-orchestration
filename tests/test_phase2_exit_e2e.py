"""Phase 2 headline exit test: a parallel best-of-N run survives a kill, resumes, and reports its tokens.

The installed CLI (`installed` of `tests/test_first_hour_e2e.py`: a non-editable install outside the
checkout) runs the best-of-N copy of `tests/test_workflow_evaluated_parallel_consumers.py`
(`:parallel 2 :workspace repo`, absolute repository paths) with the program's own provider bindings
switched to their metered templates: the coders on `claude_unrestricted_workspace_metered`, the judge on
`codex_unrestricted_workspace_metered`, with the program's own models (`claude-sonnet-5-5` and
`gpt-6-sol`; the source fixes them at each call, so no binding can change them). The stand-in is the
recovery helpers' `SHIM` (answers by request identity), followed by the metering stand-in's transport lines:
fixed counts, with the model the call asked for (Claude) or the call's policy model (Codex). During the
first run it holds the coders of the last two repositories after they log their request, in place of the
plan's `kill_at` gate: the same W6 window, held by the stand-in. `PATH` is closed (`closed_path`), so no
real provider can run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from orchestrator.providers.pricing import load_price_table, priced
from tests.agent_session_shims import closed_path
from tests.test_first_hour_e2e import installed  # noqa: F401  (the module-scoped fixture)
from tests.test_workflow_evaluated_parallel_consumers import (
    JUDGE, NEWEST, PARALLEL_MAP, PROGRAM, REPOS, SERIAL_MAP, _answers, coder, repos, selection,
)
from tests.test_workflow_evaluated_provider_usage import CLAUDE_USAGE, CODEX_USAGE
from tests.workflow_evaluated_consumer_sources import CANDIDATES, ROOT, git, install, jsonl
from tests.workflow_evaluated_recovery_helpers import SHIM

TIMEOUT = 120
BINDINGS = {"providers.coder": "claude_unrestricted_workspace_metered",
            "providers.judge": "codex_unrestricted_workspace_metered"}
CODER_MODEL, JUDGE_MODEL = "claude-sonnet-5-5", "gpt-6-sol"
HELD = ("gamma", "delta")       # the coders of the last two repositories, in flight when the run is killed
HOLD = '''hold("W6", bundle)
if os.environ.get("EXIT_HOLD") and Path.cwd().name in ''' + repr(HELD) + ''':
    (Path(os.environ["EXIT_HOLD"]) / f"held-{os.getpid()}").write_text(str(os.getpgrp()))
    while True:
        signal.pause()
'''
TRANSPORT = '''
_argv = sys.argv[1:]
if Path(sys.argv[0]).name == "claude":
    _model, _sid = _argv[_argv.index("--model") + 1], "00000000-0000-4000-8000-000000000001"
    _rows = [{"type": "system", "subtype": "init", "session_id": _sid},
             {"type": "assistant", "session_id": _sid, "message": {"id": "msg_0", "model": _model,
              "content": [{"type": "text", "text": "done"}], "usage": {"input_tokens": 11, "output_tokens": 1,
              "cache_read_input_tokens": 5, "cache_creation_input_tokens": 3}}},
             {"type": "result", "subtype": "success", "is_error": False, "result": "done", "session_id": _sid,
              "total_cost_usd": 0.25, "modelUsage": {_model: {"inputTokens": 11, "outputTokens": 7,
              "cacheReadInputTokens": 5, "cacheCreationInputTokens": 3, "costUSD": 0.25}}}]
else:
    _rows = [{"type": "thread.started", "thread_id": "00000000-0000-4000-8000-000000000002"},
             {"type": "turn.started"},
             {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "done"}},
             {"type": "turn.completed", "usage": {"input_tokens": 11, "cached_input_tokens": 5,
              "cache_write_input_tokens": 0, "output_tokens": 7, "reasoning_output_tokens": 0}}]
sys.stdout.write("".join(json.dumps(row) + "\\n" for row in _rows))
sys.stdout.flush()
'''
TOKENS = CLAUDE_USAGE["rows"][0]["tokens"]      # what one completed Claude stand-in call reports
JUDGE_TOKENS = CODEX_USAGE["rows"][0]["tokens"]  # and one Codex call (charged input: 11 - 5 cached)


def _standins(bin_dir: Path) -> None:
    assert SHIM.count('hold("W6", bundle)\n') == 1
    script = SHIM.replace('hold("W6", bundle)\n', HOLD) + TRANSPORT
    bin_dir.mkdir()
    for tool in ("claude", "codex"):
        (bin_dir / tool).write_text(f"#!{sys.executable}\n" + script, encoding="utf-8")
        (bin_dir / tool).chmod(0o700)


def _workspace(tmp_path: Path) -> tuple[Path, list[str]]:
    root = tmp_path / "workspace"
    inputs = {"task": "Fix add in calc.py so that it returns the sum.", "intent": "add returns a + b",
              "repos": repos(root)}
    frontend = install(root, PROGRAM, inputs)
    source = (ROOT / PROGRAM.source).read_text()
    assert source.count(SERIAL_MAP) == 1 and source.count('(:target-dsl "2.35")') == 1
    (root / PROGRAM.source).write_text(source.replace('(:target-dsl "2.35")', f'(:target-dsl "{NEWEST}")')
                                       .replace(SERIAL_MAP, PARALLEL_MAP))
    manifest = root / "manifests" / "providers.json"
    assert json.loads(manifest.read_text()) == {alias: name.removesuffix("_metered") for alias, name in BINDINGS.items()}
    assert source.count(f':model "{CODER_MODEL}"') == 1 and source.count(f':model "{JUDGE_MODEL}"') == 2
    manifest.write_text(json.dumps(BINDINGS))
    for repo in REPOS[len(CANDIDATES):]:
        git(root, "clone", "-q", CANDIDATES[0], repo)
    return root, frontend


def _env(installed: dict, tmp_path: Path, root: Path, **extra: str) -> dict:  # noqa: F811
    venv_bin = installed["PATH"].split(os.pathsep)[0]
    return {**installed, "PATH": venv_bin + os.pathsep + closed_path(tmp_path / "bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "RECOVERY_SHIM_PLAN": json.dumps({"answers": _answers(root), "repos": repos(root)}), **extra}


def _memo(root: Path) -> list[dict]:
    (memo,) = root.glob(".orchestrate/runs/*/memo.jsonl")
    return [json.loads(line) for line in memo.read_text(encoding="utf-8").splitlines() if line.endswith("}")]


def _run_until_two_commits_and_two_held(root: Path, frontend: list[str], env: dict, control: Path) -> None:
    """`orchestrator run` in its own session; SIGKILL it and the held stand-ins once two coders committed."""
    with (control / "run.log").open("wb") as log:
        process = subprocess.Popen(["orchestrator", "run", *frontend, "--input-file", "inputs.json"], cwd=root,
                                   env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    groups = {process.pid}
    try:
        deadline = time.monotonic() + TIMEOUT
        while len(held := sorted(control.glob("held-*"))) < len(HELD) and process.poll() is None:
            assert time.monotonic() < deadline, "the held coders never started"
            time.sleep(0.02)
        assert process.poll() is None, (control / "run.log").read_text()
        groups |= {int(path.read_text()) for path in held}
        assert [row["record"] for row in _memo(root)].count("committed") == 2
    finally:
        for group in groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=10)
    assert process.returncode == -signal.SIGKILL


def _dispatches(root: Path) -> dict[str, int]:
    """Stand-in launches per repository (coders log in their cwd) and of the judge (in the workspace)."""
    return {**{Path(repo).name: len(jsonl(root / repo / "requests.jsonl")) for repo in REPOS},
            "judge": len(jsonl(root / "requests.jsonl"))}


def _assert_resumed(root: Path, run_id: str, env: dict) -> None:
    """Resume completes with the expected winner; only the killed coders run again."""
    resumed = subprocess.run(["orchestrator", "resume", run_id], cwd=root, env=env, capture_output=True, text=True,
                             timeout=TIMEOUT)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert selection(root)["winner"] in resumed.stdout
    assert _dispatches(root) == {"alpha": 1, "beta": 1, "gamma": 2, "delta": 2, "judge": 1}


def _assert_step_usage(usage: dict, table: dict, coder_cost: float | None) -> None:
    """Each coder's tokens and priced cost; the killed coders' attempts count as unknown; the judge unpriced."""
    coders = [coder(index) for index in range(len(REPOS))]
    killed = {coder(REPOS.index(f"candidates/{name}")) for name in HELD}
    assert set(usage) == {*coders, JUDGE}
    for identity in coders:
        assert usage[identity] == ({"tokens": TOKENS, "cost_usd": pytest.approx(coder_cost), "attempts": 2,
                                    "unknown_attempts": 1, "partial": True} if identity in killed else
                                   {"tokens": TOKENS, "cost_usd": pytest.approx(coder_cost), "attempts": 1,
                                    "unknown_attempts": 0, "partial": False}), identity
    # The program's judge model has no rates in the price table: tokens are shown, its cost is not.
    assert JUDGE_MODEL not in table["models"]
    assert usage[JUDGE] == {"tokens": JUDGE_TOKENS, "cost_usd": None, "attempts": 1, "unknown_attempts": 0,
                            "partial": True}


def _assert_report(root: Path, run_id: str, env: dict) -> None:
    """Tokens of completed attempts per step, killed attempts unknown, the priced part of the cost."""
    report = subprocess.run(["orchestrator", "report", "--run-id", run_id, "--format", "json"], cwd=root, env=env,
                            capture_output=True, text=True, timeout=TIMEOUT)
    assert report.returncode == 0, report.stderr
    snapshot = json.loads(report.stdout)
    usage = {step["identity"]: step["usage"] for step in snapshot["steps"] if "usage" in step}
    table = load_price_table()
    coder_cost = priced([{"model": CODER_MODEL, "tokens": TOKENS}], table)
    _assert_step_usage(usage, table, coder_cost)
    total = snapshot["run"]["usage"]
    assert total == {"tokens": {key: 4 * TOKENS[key] + JUDGE_TOKENS[key] for key in TOKENS},
                     "cost_usd": pytest.approx(len(REPOS) * coder_cost), "attempts": len(usage) + len(HELD),
                     "unknown_attempts": len(HELD), "partial": True,
                     "price_table": {"source": table["source"], "date": table["date"]}}
    markdown = subprocess.run(["orchestrator", "report", "--run-id", run_id], cwd=root, env=env,
                              capture_output=True, text=True, timeout=TIMEOUT)
    assert markdown.returncode == 0, markdown.stderr
    section = markdown.stdout.split("## Usage\n", 1)[1]
    assert section.startswith("- total: `≥ "), section


def test_parallel_best_of_n_survives_a_kill_and_reports_tokens(installed, tmp_path):  # noqa: F811
    _standins(tmp_path / "bin")
    root, frontend = _workspace(tmp_path)
    control = tmp_path / "control"
    control.mkdir()

    # 1. Killed after exactly two implementation commits, with the other two in flight.
    _run_until_two_commits_and_two_held(root, frontend, _env(installed, tmp_path, root, EXIT_HOLD=str(control)),
                                        control)
    (run_id,) = [path.name for path in (root / ".orchestrate" / "runs").iterdir()]

    # 2. Resume completes with the expected winner; only the killed coders run again.
    env = _env(installed, tmp_path, root)
    _assert_resumed(root, run_id, env)

    # 3. The report: tokens of completed attempts per step, killed attempts unknown, the priced part of the cost.
    _assert_report(root, run_id, env)
