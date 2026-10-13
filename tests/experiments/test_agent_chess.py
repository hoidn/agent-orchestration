from __future__ import annotations

import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo


REPO = Path(__file__).parents[2]
PACKAGE = REPO / "experiments" / "agent_chess"
BOARD_PATH = "artifacts/agent_chess/partida.md"
POSITIONS = [
    "initial board",
    "white 1 position",
    "black 1 position",
    "white 2 position",
    "black 2 position",
]


PROVIDER_SHIM = r'''#!__PYTHON__
import json, os, sys, time
from pathlib import Path

provider = Path(sys.argv[0]).name
log = Path("provider_calls.jsonl")
calls = log.read_text().splitlines() if log.exists() else []
number = len(calls)
prompt = sys.stdin.buffer.read().decode("utf-8")
board_path = Path(os.environ["CHESS_BOARD_PATH"])
visible_board = board_path.read_text() if board_path.exists() else None
with log.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"provider": provider, "prompt": prompt, "visible_board": visible_board}) + "\n")

if os.environ.get("CHESS_GATE") and number == 0:
    Path(os.environ["CHESS_STARTED"]).write_text(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
    print("EARLY_WHITE_OUTPUT", flush=True)
    while not Path(os.environ["CHESS_GATE"]).exists():
        time.sleep(0.02)

if number == int(os.environ.get("CHESS_BAD_CALL", "-1")):
    output = os.environ["CHESS_BAD_OUTPUT"].encode()
else:
    if provider == "codex":
        white_turn = sum(json.loads(row)["provider"] == "codex" for row in calls)
        position = __POSITIONS__[1 + 2 * white_turn]
    else:
        position = {
            __POSITIONS__[1]: __POSITIONS__[2],
            __POSITIONS__[3]: __POSITIONS__[4],
        }[visible_board]
    output = json.dumps({"variant": "Moved", "position": position}).encode()
target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
target.write_bytes(output)
'''.replace("__PYTHON__", sys.executable).replace("__POSITIONS__", repr(POSITIONS))


def _workspace(tmp_path: Path, *, bad_call: int | None = None, bad_output: str = ""):
    root = tmp_path
    shutil.copytree(PACKAGE, root / "experiments" / "agent_chess")
    binary_dir = root / "bin"
    binary_dir.mkdir()
    for name in ("codex", "claude"):
        binary = binary_dir / name
        binary.write_text(PROVIDER_SHIM, encoding="utf-8")
        binary.chmod(0o700)
    env = {
        **os.environ,
        "PATH": str(binary_dir) + os.pathsep + os.environ["PATH"],
        "PYTHONPATH": str(REPO),
        "PYTHONDONTWRITEBYTECODE": "1",
        "CHESS_BOARD_PATH": str(root / BOARD_PATH),
        "CHESS_BAD_CALL": str(-1 if bad_call is None else bad_call),
        "CHESS_BAD_OUTPUT": bad_output,
    }
    return root, env


def _arguments(root: Path):
    package = root / "experiments" / "agent_chess"
    return (
        str(package / "chess.orc"),
        "--source-root", str(root / "experiments"),
        "--entry-workflow", "agent_chess/chess::run",
        "--provider-externs-file", str(package / "providers.json"),
        "--prompt-externs-file", str(package / "prompts.json"),
        "--command-boundaries-file", str(package / "commands.json"),
    )


def _cli(root: Path, env, *args: str):
    return subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", *args], cwd=root,
        env=env, capture_output=True, text=True, check=False,
    )


def _input_args(*, rounds: int = 2):
    return (
        "--input", "board=" + POSITIONS[0],
        "--input", "path=" + BOARD_PATH,
        "--input", f"rounds={rounds}",
    )


def _calls(root: Path):
    return [json.loads(line) for line in (root / "provider_calls.jsonl").read_text().splitlines()]


def _run_snapshot(root: Path):
    run_root, = (root / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    return run_root, read_memo(authority.memo_path, site_classes(authority.program))


def test_public_run_alternates_two_rounds_and_completed_resume_does_not_redispatch(tmp_path):
    root, env = _workspace(tmp_path)
    args = _arguments(root)
    compiled = _cli(root, env, "compile", *args)
    assert compiled.returncode == 0, compiled.stderr

    result = _cli(root, env, "run", *args, *_input_args())
    assert result.returncode == 0, result.stderr
    calls = _calls(root)
    assert [call["provider"] for call in calls] == ["codex", "claude", "codex", "claude"]
    assert [call["visible_board"] for call in calls] == POSITIONS[:4]
    assert all(position in call["prompt"] for position, call in zip(POSITIONS, calls))
    assert (root / BOARD_PATH).read_text() == POSITIONS[-1]

    run_root, snapshot = _run_snapshot(root)
    assert snapshot.terminal.data == {
        "record": "terminal", "outcome": "completed",
        "value": {"variant": "Finished", "position": POSITIONS[-1]},
    }
    requests_before = (root / "provider_calls.jsonl").read_bytes()
    memo_before = (run_root / "memo.jsonl").read_bytes()
    resumed = _cli(root, env, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert (root / "provider_calls.jsonl").read_bytes() == requests_before
    assert (run_root / "memo.jsonl").read_bytes() == memo_before


def test_provider_stdout_is_visible_while_its_result_file_is_pending(tmp_path):
    root, env = _workspace(tmp_path)
    gate = root / "allow-provider-finish"
    started = root / "provider-started"
    env.update(CHESS_GATE=str(gate), CHESS_STARTED=str(started))
    process = subprocess.Popen(
        [sys.executable, "-B", "-m", "orchestrator", "run", *_arguments(root), *_input_args(rounds=1)],
        cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
    )
    try:
        ready, _, _ = select.select([process.stdout], [], [], 30)
        assert ready, "provider did not stream output before the deadline"
        assert "EARLY_WHITE_OUTPUT" in process.stdout.readline()
        assert started.is_file()
        assert not (root / started.read_text()).exists()
    finally:
        gate.touch()
        try:
            stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
    assert process.returncode == 0, stderr
    assert "EARLY_WHITE_OUTPUT" not in stdout


def test_invalid_black_result_preserves_last_accepted_white_board(tmp_path):
    root, env = _workspace(tmp_path, bad_call=1, bad_output="not-json")
    result = _cli(root, env, "run", *_arguments(root), *_input_args(rounds=1))
    assert result.returncode == 1
    assert [call["provider"] for call in _calls(root)] == ["codex", "claude"]
    assert (root / BOARD_PATH).read_text() == POSITIONS[1]
    run_root, before = _run_snapshot(root)
    assert before.terminal.data["outcome"] == "failed"
    white_commit, = [commit for commit in before.active_commits.values() if commit.data["effect_class"] == "provider"]
    white_attempt = run_root / Path(white_commit.data["result_path"]).parent
    white_evidence = {path.name: path.read_bytes() for path in white_attempt.iterdir()}
    black_failure, = [entry.data for entry in before.entries if entry.data["record"] == "failed"]
    black_start, = [
        entry.data for entry in before.entries
        if entry.data["record"] == "started" and entry.data["identity"] == black_failure["identity"]
    ]
    failed_black_attempt = run_root / Path(black_start["result_path"]).parent
    failed_black_evidence = {path.name: path.read_bytes() for path in failed_black_attempt.iterdir()}

    env["CHESS_BAD_CALL"] = "-1"
    resumed = _cli(root, env, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    calls = _calls(root)
    assert [call["provider"] for call in calls] == ["codex", "claude", "claude"]
    assert [call["visible_board"] for call in calls] == [POSITIONS[0], POSITIONS[1], POSITIONS[1]]
    assert (root / BOARD_PATH).read_text() == POSITIONS[2]

    _, after = _run_snapshot(root)
    assert after.terminal.data["outcome"] == "completed"
    assert after.terminal.data["value"] == {"variant": "Finished", "position": POSITIONS[2]}
    assert after.active_commits[white_commit.data["identity"]] == white_commit
    assert {path.name: path.read_bytes() for path in white_attempt.iterdir()} == white_evidence
    assert {path.name: path.read_bytes() for path in failed_black_attempt.iterdir()} == failed_black_evidence


def test_non_outcome_black_result_preserves_last_accepted_white_board(tmp_path):
    root, env = _workspace(tmp_path, bad_call=1, bad_output="17")
    result = _cli(root, env, "run", *_arguments(root), *_input_args(rounds=1))
    assert result.returncode == 1
    assert (root / BOARD_PATH).read_text() == POSITIONS[1]
    _, snapshot = _run_snapshot(root)
    assert snapshot.terminal.data["outcome"] == "failed"


def test_blocked_white_result_commits_and_ends_game_without_retry(tmp_path):
    blocked = {"variant": "Blocked", "reason": "no legal move"}
    root, env = _workspace(tmp_path, bad_call=0, bad_output=json.dumps(blocked))
    result = _cli(root, env, "run", *_arguments(root), *_input_args(rounds=2))
    assert result.returncode == 0, result.stderr
    assert [call["provider"] for call in _calls(root)] == ["codex"]
    assert (root / BOARD_PATH).read_text() == POSITIONS[0]

    _, snapshot = _run_snapshot(root)
    assert snapshot.terminal.data["outcome"] == "completed"
    assert snapshot.terminal.data["value"] == {"variant": "Blocked", "side": "White", "reason": "no legal move"}
    white_commit, = [commit for commit in snapshot.active_commits.values() if commit.data["effect_class"] == "provider"]
    assert white_commit.data["value"] == blocked
    started = [entry.data["identity"] for entry in snapshot.entries if entry.data["record"] == "started"]
    assert started.count(white_commit.data["identity"]) == 1
    assert not [entry for entry in snapshot.entries if entry.data["record"] == "failed"]


def test_board_writer_refuses_paths_outside_its_artifact_directory(tmp_path):
    root, env = _workspace(tmp_path)
    request = root / "inputs.json"
    request.write_text(json.dumps({"board": "must not publish", "path": "artifacts/other/board.md"}))
    result_path = root / "command-result.json"
    result = subprocess.run(
        [sys.executable, str(root / "experiments/agent_chess/write_board.py"), str(request)],
        cwd=root, env={**env, "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(result_path)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert not (root / "artifacts/other/board.md").exists()
    assert not result_path.exists()
