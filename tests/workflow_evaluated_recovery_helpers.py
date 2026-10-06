"""Window gates, identity-keyed stand-ins and external kills for the public recovery campaign.

`GATE` is the public CLI with one window gate: it wraps the real append, allocation,
directory creation or journal write named by `RECOVERY_WINDOW`, lets the real call reach
the window's boundary, publishes a marker and blocks there; the test kills its process
group. W1 alone cuts the real `started` write short (an induced short write, then the
kill). W6 and W7 are held by the stand-ins themselves: a launched provider or command logs
its dispatch and blocks (W6) or writes half of its result and blocks (W7); a copied
library script gets the same gate through `COMMAND_GATE` and `_WRITE_HOOK`. Each provider
stand-in answers from the identity of its request (its site key), never from a count of
earlier requests, so a retried attempt receives the same answer as the uninterrupted run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import pytest

from tests.workflow_evaluated_consumer_sources import EXEC_LOG, FUTURE, PROGRAMS, install, jsonl, sha256
from tests.workflow_evaluated_run_ref_helpers import _output
from tests.workflow_lisp_improve_example_sources import LAUNCH_PROBE


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = tuple(f"W{index}" for index in range(10))
LAUNCHER_PATH = "scripts/launch_experiment.py"
BUNDLE = re.compile(r"effects/([0-9a-f]{64})/attempt-([1-9][0-9]*)/result\.json\Z")
DEADLINE = 120  # seconds until a marker; reaching it is a failure, never an ordering device

GATE = r'''import json, os, signal, sys
from pathlib import Path

config = json.loads(os.environ["RECOVERY_WINDOW"])
window, identity, attempt, digest = config["window"], config["identity"], config["attempt"], config["digest"]
fired = False

def hold(run, **facts):
    global fired
    fired = True
    marker = Path(config["marker"])
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.write_text(json.dumps({"window": window, "run": run, "identity": identity, "attempt": attempt,
                                     "pid": os.getpid(), "pgid": os.getpgrp(), "runner_pid": os.getpid(),
                                     **facts}), encoding="utf-8")
    os.replace(temporary, marker)
    while True:
        signal.pause()

def reached(record, kind):
    return (not fired and record.get("record") == kind and record.get("identity") == identity
            and record.get("attempt") == attempt)

def descriptor_path(fd):
    try:
        return os.readlink(f"/proc/self/fd/{fd}")
    except OSError:
        return ""

real_write, real_mkdir = os.write, os.mkdir

def write(fd, data):
    raw, journal = bytes(data), descriptor_path(fd)
    if (window in ("W1", "W2") and not fired and b'"record":"started"' in raw
            and journal.endswith("/memo.jsonl") and reached(json.loads(raw), "started")):
        if window == "W1":
            real_write(fd, raw[: len(raw) // 2])
            hold(Path(journal).parent.name, written=len(raw) // 2, length=len(raw))
        real_write(fd, raw)
        hold(Path(journal).parent.name, written=len(raw), length=len(raw))
    return real_write(fd, data)

def mkdir(path, mode=0o777, *, dir_fd=None):
    result = real_mkdir(path, mode, dir_fd=dir_fd)
    if (window == "W4" and not fired and dir_fd is not None and path == f"attempt-{attempt}"
            and descriptor_path(dir_fd).endswith(f"/effects/{digest}")):
        hold(Path(descriptor_path(dir_fd)).parents[1].name)
    return result

os.write, os.mkdir = write, mkdir

from orchestrator.workflow.evaluated import attempts, runtime
from orchestrator.workflow.workspace_files import WorkspaceFiles

real_started = attempts.append_record

def append_started(path, record, **kwargs):
    if window == "W0" and reached(record, "started"):
        hold(Path(path).parent.name)
    return real_started(path, record, **kwargs)

real_exclusive = WorkspaceFiles.mkdir_exclusive

def exclusive(self, path):
    if window == "W3" and not fired and str(path) == f"effects/{digest}/attempt-{attempt}":
        hold(self.workspace.name)
    return real_exclusive(self, path)

real_allocate = runtime.allocate_attempt

def allocate(run_files, memo_path, started, **kwargs):
    files = real_allocate(run_files, memo_path, started, **kwargs)
    if window == "W5" and reached(started, "started"):
        hold(Path(memo_path).parent.name)
    return files

real_append = runtime.append_record

def append(path, record, **kwargs):
    if window == "W8" and reached(record, "committed"):
        hold(Path(path).parent.name)
    entry = real_append(path, record, **kwargs)
    if window == "W9" and reached(record, "committed"):
        hold(Path(path).parent.name)
    return entry

attempts.append_record, runtime.allocate_attempt, runtime.append_record = append_started, allocate, append
WorkspaceFiles.mkdir_exclusive = exclusive

from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
raise SystemExit(main())
'''

STANDIN_GATE = r'''
def _window(bundle):
    raw = os.environ.get("RECOVERY_WINDOW")
    config = json.loads(raw) if raw else None
    expected = f"effects/{config['digest']}/attempt-{config['attempt']}/result.json" if config else None
    return config if config and bundle.replace(os.sep, "/").endswith(expected) else None

def hold(window, bundle, **facts):
    config = _window(bundle)
    if config is None or config["window"] != window:
        return
    marker = Path(config["marker"])
    temporary = marker.with_name(marker.name + ".tmp")
    parts = Path(bundle).parts
    temporary.write_text(json.dumps({"window": window, "run": parts[parts.index("effects") - 1],
                                     "digest": config["digest"], "attempt": config["attempt"],
                                     "pid": os.getpid(), "pgid": os.getpgrp(), "runner_pid": os.getppid(),
                                     **facts}), encoding="utf-8")
    os.replace(temporary, marker)
    while True:
        signal.pause()

def write_result(bundle, text):
    config = _window(bundle)
    if config is not None and config["window"] == "W7":
        Path(bundle).write_text(text[: len(text) // 2], encoding="utf-8")
        hold("W7", bundle, written=len(text[: len(text) // 2].encode()), length=len(text.encode()))
    Path(bundle).write_text(text, encoding="utf-8")
'''

SHIM = r'''import json, os, signal, sys
from pathlib import Path
''' + STANDIN_GATE + r'''
prompt = sys.stdin.buffer.read().decode("utf-8")
plan = json.loads(os.environ["RECOVERY_SHIM_PLAN"])
site, bundle = os.environ["ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY"], os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
repos = sorted((repo for repo in plan["repos"] if repo in prompt), key=prompt.index)
with open("requests.jsonl", "a", encoding="utf-8") as log:
    log.write(json.dumps({"tool": Path(sys.argv[0]).name, "site": site, "bundle": bundle, "cwd": os.getcwd(),
                          "repos": repos}) + "\n")
hold("W6", bundle)
answer = plan["answers"][site]
for name, text in answer.get("files", {}).items():
    if "{repo}" in name:
        (repo,) = repos
        name = name.replace("{repo}", repo)
    Path(name).parent.mkdir(parents=True, exist_ok=True)
    Path(name).write_text(text, encoding="utf-8")
write_result(bundle, json.dumps(answer["result"]))
'''

COMMAND_GATE = ("import json, os, signal\nfrom pathlib import Path\n" + STANDIN_GATE
                + 'with open("commands.jsonl", "a", encoding="utf-8") as _log:\n'
                + '    _log.write(json.dumps({"bundle": os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]}) + "\\n")\n'
                + 'hold("W6", os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n')
_PROBE_WRITE = 'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(payload), encoding="utf-8")'
assert LAUNCH_PROBE.count(_PROBE_WRITE) == 1
LAUNCHER = COMMAND_GATE + LAUNCH_PROBE.replace(
    _PROBE_WRITE, 'write_result(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], json.dumps(payload))')
_MAIN = 'if __name__ == "__main__":'
_WRITE_HOOK = '''_unhooked_write_json = _write_json


def _write_json(path, payload):
    if _window(str(path)) is None:
        return _unhooked_write_json(path, payload)
    write_result(str(path), json.dumps(payload, indent=2) + "\\n")


'''


def _gate_script(path: Path) -> None:
    """Give a copied library script the command gate: dispatch log and W6 at start, W7 in its writer."""
    text = path.read_text(encoding="utf-8")
    assert (text.count(FUTURE + EXEC_LOG), text.count(_MAIN), text.count("def _write_json(")) == (1, 1, 1)
    text = text.replace(FUTURE + EXEC_LOG, FUTURE + EXEC_LOG + COMMAND_GATE).replace(_MAIN, _WRITE_HOOK + _MAIN)
    path.write_text(text, encoding="utf-8")


def install_standins(bin_dir: Path, monkeypatch, answers: dict[str, dict], repos: list[str]) -> None:
    """`SHIM` as `codex` and `claude` on PATH, answering by request identity (`sha256:` site key)."""
    bin_dir.mkdir(parents=True)
    for tool in ("codex", "claude"):
        (bin_dir / tool).write_text(f"#!{sys.executable}\n" + SHIM, encoding="utf-8")
        (bin_dir / tool).chmod(0o700)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("RECOVERY_SHIM_PLAN", json.dumps({"answers": answers, "repos": repos}))


def current_source(name: str) -> bytes:
    """The program's 2.35 copy: its repository source with only the target header changed."""
    program = PROGRAMS[name]
    header = f'(:target-dsl "{program.target}")'
    text = (ROOT / program.source).read_text(encoding="utf-8")
    assert text.count(header) == 1
    return text.replace(header, '(:target-dsl "2.35")').encode("utf-8")


def prepare(root: Path, name: str, inputs: dict, *, must_not_repeat: bool = False) -> list[str]:
    """Install the 2.35 program in `root` with gated commands; return its frontend arguments."""
    program = PROGRAMS[name]
    frontend = install(root, program, inputs, current=True)
    assert (root / program.source).read_bytes() == current_source(name)
    if (root / LAUNCHER_PATH).exists():
        (root / LAUNCHER_PATH).write_text(LAUNCHER, encoding="utf-8")
    for asset in program.assets:
        if asset.endswith(".py"):
            _gate_script(root / asset)
    if must_not_repeat:
        manifest = root / "manifests/commands.json"
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        rows = {name: {**row, "must_not_repeat": True} for name, row in rows.items()}
        manifest.write_text(json.dumps(rows), encoding="utf-8")
    return frontend


def dispatches(root: Path) -> list[tuple[str, int]]:
    """(`digest` of the identity, attempt) of every launch the stand-ins logged, providers then commands."""
    bundles = [row["bundle"] for row in jsonl(root / "requests.jsonl")]
    bundles += [row["bundle"] for row in jsonl(root / "commands.jsonl")]
    matches = [BUNDLE.search(bundle.replace(os.sep, "/")) for bundle in bundles]
    assert all(matches), bundles
    return [(match.group(1), int(match.group(2))) for match in matches]


def digest(identity: str) -> str:
    """The hex digest naming an identity's `effects/` directory (its site key without `sha256:`)."""
    return sha256(identity).removeprefix("sha256:")


def _gone(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return True
    return state == "Z"


def _kill_tree(process: subprocess.Popen, marker: dict | None) -> None:
    """SIGKILL the CLI's own group and, if a stand-in left it, the stand-in's group; reap both."""
    groups = {process.pid} | ({marker["pgid"]} if marker else set())
    for group in groups:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)
    deadline = time.monotonic() + 10
    while marker and not _gone(marker["pid"]):
        assert time.monotonic() < deadline, f"stand-in {marker['pid']} survived its group kill"
        time.sleep(0.02)


def _wait_for_marker(process: subprocess.Popen, path: Path) -> dict | None:
    """The published marker, or None if the run exited or `DEADLINE` passed without one."""
    deadline = time.monotonic() + DEADLINE
    while process.poll() is None and not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    return json.loads(path.read_bytes()) if path.is_file() else None


def resume(root: Path, run_id: str) -> subprocess.CompletedProcess[str]:
    """`orchestrator resume` like `_resume_cli`, but a resume that blocks fails at `DEADLINE`."""
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-m", "orchestrator", "resume", run_id], cwd=root, env=env,
                          capture_output=True, text=True, check=False, timeout=DEADLINE)


def kill_at(root: Path, control: Path, argv: list[str], window: dict | None, check, *, env: dict | None = None):
    """Run `argv` in its own session until the marker, `check(marker)` the held state, then SIGKILL it.

    `window` (the `RECOVERY_WINDOW` gate configuration) selects `GATE`; without it the
    public CLI runs unwrapped and a stand-in publishes the marker named by `env`.
    """
    control.mkdir(parents=True, exist_ok=True)
    marker_path = control / "marker.json"
    assert not marker_path.exists(), f"stale marker {marker_path}"
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
    if window is not None:
        (control / "gate.py").write_text(GATE, encoding="utf-8")
        env["RECOVERY_WINDOW"] = json.dumps({**window, "marker": str(marker_path)})
        argv = [sys.executable, str(control / "gate.py"), *argv]
    else:
        argv = [sys.executable, "-m", "orchestrator", *argv]
    streams = (control / "stdout.log", control / "stderr.log")
    with streams[0].open("wb") as stdout, streams[1].open("wb") as stderr:
        process = subprocess.Popen(argv, cwd=root, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
    marker = None
    try:
        marker = _wait_for_marker(process, marker_path)
        if marker is None:
            pytest.fail(f"run missed its window marker (exit {process.poll()}):\n{_output(*streams)}")
        assert process.poll() is None, _output(*streams)
        assert marker["runner_pid"] == process.pid
        check(marker)
    finally:
        _kill_tree(process, marker)  # bound before any assert, so a stand-in's own group is killed too
    assert process.returncode == -signal.SIGKILL, _output(*streams)
    return marker
