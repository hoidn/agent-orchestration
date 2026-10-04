from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from tests.test_workflow_evaluated_providers import _fixture, _requests


_COMMIT_GATE = '''\
import os
import signal
import sys
from pathlib import Path

from orchestrator.workflow.evaluated import runtime

append_record = runtime.append_record
marker = Path(os.environ["ORCHESTRATOR_TEST_COMMIT_MARKER"])

def gate(*args, **kwargs):
    entry = append_record(*args, **kwargs)
    record = args[1] if len(args) > 1 else kwargs["record"]
    if record.get("record") == "committed" and not marker.exists():
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(record["identity"], encoding="utf-8")
        signal.pause()
    return entry

runtime.append_record = gate
from orchestrator.cli import main
raise SystemExit(main())
'''

_COMMAND_SOURCE = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defworkflow run () -> Int
    (let* ((first (command-result first :argv ("python" "probe.py" "first") :returns Int))
           (second (command-result second :argv ("python" "probe.py" "second" first) :returns Int)))
      second)))
'''

_PROVIDER_SOURCE = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Review (ok Bool))
  (defworkflow run ((message String)) -> Int
    (let* ((review (provider-result providers.review :prompt prompts.base
                    :inputs (message) :model "chosen-model" :effort "low" :returns Review))
           (after (command-result after :argv ("python" "after.py" review.ok) :returns Int)))
      after)))
'''


def _env(root: Path, *, provider: bool = False) -> dict[str, str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if provider:
        env["PATH"] = str(root / "bin") + os.pathsep + env["PATH"]
        env["PROVIDER_SHIM_MODE"] = "success"
        env["PROVIDER_SHIM_RESULT"] = '{"ok":true}'
    return env


def _cli(root: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", *args], cwd=root, env=env,
        capture_output=True, text=True, check=False,
    )


def _kill_after_first_commit(root: Path, args: list[str], env: dict[str, str]) -> str:
    control = root / ".test-control"
    marker = control / "committed-identity"
    launcher = control / "cli_with_commit_gate.py"
    control.mkdir(parents=True)
    launcher.write_text(_COMMIT_GATE, encoding="utf-8")
    child_env = {**env, "ORCHESTRATOR_TEST_COMMIT_MARKER": str(marker)}
    process = subprocess.Popen(
        [sys.executable, str(launcher), *args], cwd=root, env=child_env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 15
        while process.poll() is None and not marker.is_file() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not marker.is_file():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"CLI did not reach a committed effect: {stdout}\n{stderr}")
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == -signal.SIGKILL, (stdout, stderr)
        return marker.read_text(encoding="utf-8")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def _run_root(root: Path) -> Path:
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return run_root


def _snapshot(run_root: Path):
    authority = load_run_authority(run_root)
    return read_memo(authority.memo_path, site_classes(authority.program))


def _rows(snapshot, name: str) -> list[dict]:
    return [entry.data for entry in snapshot.entries if entry.data["record"] == name]


def _hashes(root: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in names
    }


def _attempt_files(run_root: Path, commit: dict) -> dict[str, bytes]:
    result = run_root / commit["result_path"]
    attempt = result.parent
    return {
        path.relative_to(attempt).as_posix(): path.read_bytes()
        for path in attempt.rglob("*") if path.is_file()
    }


def _assert_attempt_streams(evidence: dict[str, bytes], first_class: str) -> None:
    if first_class == "provider":
        assert "prompt.txt" in evidence
        stdout, stderr = b"complete stdout\n", b"complete stderr\n"
    else:
        stdout, stderr = b"command stdout first\n", b"command stderr first\n"
    assert evidence["stdout.txt"] == stdout
    assert evidence["stderr.txt"] == stderr


def _assert_attempt_evidence(run_root: Path, commit: dict, first_class: str) -> dict[str, bytes]:
    evidence = _attempt_files(run_root, commit)
    assert {"result.json", "stdout.txt", "stderr.txt"} <= evidence.keys()
    assert evidence["result.json"]
    result_digest = "sha256:" + hashlib.sha256(evidence["result.json"]).hexdigest()
    assert result_digest == commit["result_digest"]
    _assert_attempt_streams(evidence, first_class)
    return evidence


def _assert_interrupted_prefix(run_root: Path, first_class: str, marker_identity: str):
    before = _snapshot(run_root)
    (first_before,) = _rows(before, "committed")
    assert first_before["identity"] == marker_identity
    assert first_before["effect_class"] == first_class
    assert before.terminal is None
    evidence = _assert_attempt_evidence(run_root, first_before, first_class)
    return first_before, evidence


def _assert_resumed_records(after, first_before: dict, first_class: str):
    starts, commits = _rows(after, "started"), _rows(after, "committed")
    assert len(starts) == len(commits) == 2
    assert [row["attempt"] for row in starts] == [1, 1]
    assert [row["identity"] for row in starts] == [row["identity"] for row in commits]
    assert starts[0]["identity"] != starts[1]["identity"]
    assert [row["effect_class"] for row in commits] == [first_class, "command"]
    assert commits[0] == first_before
    assert commits[1]["depends_on"] == [first_before["identity"]]


def _assert_resumed_terminal(after, run_root: Path, first_before: dict, evidence: dict,
                             expected_value) -> None:
    assert after.terminal is not None
    assert after.terminal.data["outcome"] == "completed"
    assert after.terminal.data["value"] == expected_value
    assert _attempt_files(run_root, first_before) == evidence


def _assert_resumed_state(run_root: Path, first_before: dict, evidence: dict, expected_value,
                          first_class: str) -> None:
    after = _snapshot(run_root)
    _assert_resumed_records(after, first_before, first_class)
    _assert_resumed_terminal(after, run_root, first_before, evidence, expected_value)


def _assert_resumed_once(root: Path, expected_value, first_class: str, marker_identity: str,
                         env: dict[str, str], source_hashes: dict[str, str]) -> None:
    run_root = _run_root(root)
    first_before, evidence = _assert_interrupted_prefix(run_root, first_class, marker_identity)
    resumed = _cli(root, ["resume", run_root.name], env)
    assert resumed.returncode == 0, resumed.stderr
    _assert_resumed_state(run_root, first_before, evidence, expected_value, first_class)
    assert _hashes(root, tuple(source_hashes)) == source_hashes


def _write_command_case(root: Path) -> tuple[list[str], dict[str, str]]:
    root.mkdir(parents=True)
    source = root / "main.orc"
    source.write_text(_COMMAND_SOURCE, encoding="utf-8")
    probe = root / "probe.py"
    probe.write_text(
        'import json, os, sys\nfrom pathlib import Path\n'
        'kind = sys.argv[1]\n'
        'Path("dispatches.jsonl").open("a", encoding="utf-8").write('
        'json.dumps({"kind": kind}) + "\\n")\n'
        'print("command stdout " + kind)\n'
        'print("command stderr " + kind, file=sys.stderr)\n'
        'value = 5 if kind == "first" else int(sys.argv[2]) + 1\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(value), encoding="utf-8")\n',
        encoding="utf-8",
    )
    manifest = root / "commands.json"
    manifest.write_text(json.dumps({
        name: {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]}
        for name in ("first", "second")
    }), encoding="utf-8")
    names = ("main.orc", "probe.py", "commands.json")
    return ["run", str(source), "--command-boundaries-file", str(manifest)], _hashes(root, names)


def test_public_command_commit_survives_group_kill_and_resume_runs_continuation_once(tmp_path):
    baseline, interrupted = tmp_path / "baseline", tmp_path / "interrupted"
    baseline_args, baseline_hashes = _write_command_case(baseline)
    interrupted_args, interrupted_hashes = _write_command_case(interrupted)
    assert baseline_hashes == interrupted_hashes
    env = _env(baseline)
    first = _cli(baseline, baseline_args, env)
    assert first.returncode == 0, first.stderr
    baseline_run = _run_root(baseline)
    baseline_snapshot = _snapshot(baseline_run)
    assert baseline_snapshot.terminal is not None
    expected = baseline_snapshot.terminal.data["value"]

    marker_identity = _kill_after_first_commit(interrupted, interrupted_args, _env(interrupted))
    _assert_resumed_once(
        interrupted, expected, "command", marker_identity, _env(interrupted), interrupted_hashes
    )
    dispatches = [json.loads(line)["kind"] for line in
                  (interrupted / "dispatches.jsonl").read_text(encoding="utf-8").splitlines()]
    assert dispatches == ["first", "second"]


def _write_provider_case(root: Path) -> tuple[list[str], dict[str, str]]:
    root.mkdir(parents=True)
    source, providers, prompts, _request = _fixture(root, _PROVIDER_SOURCE)
    after = root / "after.py"
    after.write_text(
        'import os, sys\nfrom pathlib import Path\n'
        'Path("continuations.jsonl").open("a", encoding="utf-8").write(sys.argv[1] + "\\n")\n'
        'value = 9 if sys.argv[1].lower() == "true" else 8\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(value), encoding="utf-8")\n',
        encoding="utf-8",
    )
    commands = root / "commands.json"
    commands.write_text(json.dumps({
        "after": {"stable_command": ["python", "after.py"], "closure": ["after.py"]}
    }), encoding="utf-8")
    args = ["run", str(source), "--source-root", str(root),
        "--provider-externs-file", str(providers), "--prompt-externs-file", str(prompts),
        "--command-boundaries-file", str(commands), "--input", "message=typed input"]
    names = ("main.orc", "providers.json", "prompts.json", "prompt.md",
        "commands.json", "after.py", "bin/codex")
    return args, _hashes(root, names)


def test_public_provider_commit_survives_group_kill_and_resume_runs_continuation_once(tmp_path):
    baseline, interrupted = tmp_path / "baseline", tmp_path / "interrupted"
    baseline_args, baseline_hashes = _write_provider_case(baseline)
    interrupted_args, interrupted_hashes = _write_provider_case(interrupted)
    assert baseline_hashes == interrupted_hashes
    baseline_env, interrupted_env = _env(baseline, provider=True), _env(interrupted, provider=True)
    first = _cli(baseline, baseline_args, baseline_env)
    assert first.returncode == 0, first.stderr
    baseline_snapshot = _snapshot(_run_root(baseline))
    assert baseline_snapshot.terminal is not None
    expected = baseline_snapshot.terminal.data["value"]

    marker_identity = _kill_after_first_commit(interrupted, interrupted_args, interrupted_env)
    _assert_resumed_once(
        interrupted, expected, "provider", marker_identity, interrupted_env, interrupted_hashes
    )
    assert len(_requests(interrupted)) == 1
    assert (interrupted / "continuations.jsonl").read_text(encoding="utf-8").splitlines() == ["true"]
