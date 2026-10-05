"""Real public-process interruption boundaries for dynamic command/provider effects."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from orchestrator.workflow.dynamic.state import load_dynamic_view
from tests.test_workflow_dynamic_source import write_source


_CLI_GATE = '''\
import json
import os
from pathlib import Path
import time

from orchestrator.workflow.dynamic import runtime
from orchestrator.workflow.dynamic.state import DynamicRun

control = Path(os.environ["DYNAMIC_TEST_CONTROL"])
target_kind = os.environ["DYNAMIC_TEST_KIND"]
barrier = os.environ.get("DYNAMIC_TEST_BARRIER", "")
dispatch_count = 0
gate_written = False

def publish_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)

def pause(name, effect_kind):
    global gate_written
    if gate_written:
        return
    gate_written = True
    publish_json(control / "gate.json", {
        "barrier": name, "kind": effect_kind, "pid": os.getpid(),
        "pgid": os.getpgrp(),
    })
    while not (control / "release").exists():
        time.sleep(0.01)

def wrap_performer(name, original):
    def wrapped(*args, **kwargs):
        global dispatch_count
        if name == target_kind:
            dispatch_count += 1
            if barrier == "pre_dispatch":
                pause("pre_dispatch", name)
            elif barrier == "second_dispatch" and dispatch_count == 2:
                pause("second_dispatch", name)
        return original(*args, **kwargs)
    return wrapped

runtime.perform_command = wrap_performer("command", runtime.perform_command)
runtime.perform_provider = wrap_performer("provider", runtime.perform_provider)

finish_effect = DynamicRun.finish_effect
def gated_finish(self, *, steps, error=None):
    if (barrier == "before_row" and error is None and self.state["current_effect"] is not None
            and self.state["effects"][-1]["effect_class"] == target_kind):
        pause("before_row", target_kind)
    return finish_effect(self, steps=steps, error=error)
DynamicRun.finish_effect = gated_finish

complete = DynamicRun.complete
def gated_complete(self, value, *, steps):
    if barrier == "before_terminal":
        pause("before_terminal", target_kind)
    return complete(self, value, steps=steps)
DynamicRun.complete = gated_complete

from orchestrator.cli import main
raise SystemExit(main())
'''


_EFFECT_PROBE = '''\
#!/usr/bin/env python3
import json
import os
from pathlib import Path
import re
import sys
import time

def publish_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)

mode = os.environ["DYNAMIC_TEST_MODE"]
control = Path(os.environ["DYNAMIC_TEST_CONTROL"])
if mode == "command":
    token = sys.argv[-1]
else:
    prompt = sys.stdin.read()
    match = re.search(r"TOKEN_(ONLY|ONE|TWO)", prompt)
    if match is None:
        raise SystemExit("provider request omitted the fixture token")
    token = "TOKEN_" + match.group(1)

label = token.removeprefix("TOKEN_").lower()
event = {"kind": mode, "label": label, "pid": os.getpid(), "pgid": os.getpgrp(),
         "result_path": os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")}
if mode == "provider":
    event["prompt"] = prompt
with (control / "calls.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(event, sort_keys=True) + "\\n")
    stream.flush()
    os.fsync(stream.fileno())

if label == os.environ.get("DYNAMIC_TEST_BLOCK_LABEL"):
    publish_json(control / "effect-ready.json", event)
    while not (control / "release").exists():
        time.sleep(0.01)

if mode == "command":
    value = {"only": 17, "one": 11, "two": 22}[label]
else:
    value = "reply-" + label
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
    json.dumps(value), encoding="utf-8"
)
print("fixture stdout " + label, flush=True)
print("fixture stderr " + label, file=sys.stderr, flush=True)
'''


def _write_case(root: Path, kind: str, *, two_effects: bool = False, budget: int = 80):
    root.mkdir(parents=True, exist_ok=True)
    probe = root / "interrupt_probe.py"
    probe.write_text(_EFFECT_PROBE, encoding="utf-8")
    source = root / "demo/main.orc"
    source.parent.mkdir(parents=True)

    if kind == "command":
        commands = root / "commands.json"
        commands.write_text(json.dumps({"probe": {
            "kind": "external_tool",
            "stable_command": ["python", "interrupt_probe.py"],
            "closure": [],
        }}), encoding="utf-8")
        labels = ("TOKEN_ONE", "TOKEN_TWO") if two_effects else ("TOKEN_ONLY",)
        calls = [
            f'(command-result probe :argv ("python" "interrupt_probe.py" "{label}") :returns Int)'
            for label in labels
        ]
        if two_effects:
            body = f'(list {calls[0]} {calls[1]})'
            result = "List[Int]"
        else:
            body = calls[0]
            result = "Int"
        write_source(root, "demo/main", f'(export main) (defworkflow main () -> {result} {body})', budget=budget)
        args = ["run", str(source), "--command-boundaries-file", str(commands)]
    elif kind == "provider":
        binary = root / "bin/codex"
        binary.parent.mkdir()
        binary.write_text(_EFFECT_PROBE, encoding="utf-8")
        binary.chmod(0o700)
        providers = root / "providers.json"
        providers.write_text(json.dumps({"providers.ask": "codex"}), encoding="utf-8")
        labels = ("TOKEN_ONE", "TOKEN_TWO") if two_effects else ("TOKEN_ONLY",)
        params = ("one", "two") if two_effects else ("only",)
        calls = [
            f'(provider-result providers.ask :prompt (request :label {param}) '
            ':model "fixture-model" :effort "low" :returns String)'
            for param in params
        ]
        body = f'(defprompt request (:fills (label :text)) -> String "effect {{label}}") '
        if two_effects:
            body += f'(defworkflow main ((one String) (two String)) -> List[String] (list {calls[0]} {calls[1]}))'
        else:
            body += f'(defworkflow main ((only String)) -> String {calls[0]})'
        write_source(root, "demo/main", f'(export main) {body}', budget=budget)
        args = ["run", str(source), "--source-root", str(root), "--provider-externs-file", str(providers)]
        args.extend(part for param, label in zip(params, labels, strict=True)
                    for part in ("--input", f"{param}={label}"))
    else:
        raise AssertionError(kind)

    return {"root": root, "source": source, "args": args, "kind": kind}


def _env(case, control: Path, *, barrier: str = "", block_label: str = ""):
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DYNAMIC_TEST_CONTROL": str(control),
        "DYNAMIC_TEST_KIND": case["kind"],
        "DYNAMIC_TEST_MODE": case["kind"],
        "DYNAMIC_TEST_BARRIER": barrier,
        "DYNAMIC_TEST_BLOCK_LABEL": block_label,
    }
    if case["kind"] == "provider":
        env["PATH"] = str(case["root"] / "bin") + os.pathsep + env["PATH"]
    return env


def _start_cli(case, control: Path, *, barrier: str = "", block_label: str = ""):
    control.mkdir()
    launcher = control / "cli_with_dynamic_gate.py"
    launcher.write_text(_CLI_GATE, encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(launcher), *case["args"]], cwd=case["root"],
        env=_env(case, control, barrier=barrier, block_label=block_label),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    return process


@contextmanager
def _live_cli(case, control: Path, *, barrier: str = "", block_label: str = ""):
    process = _start_cli(case, control, barrier=barrier, block_label=block_label)
    try:
        yield process
    finally:
        _cleanup_cli(process, control)


def _wait_file(process, path: Path, *, timeout: float = 20):
    deadline = time.monotonic() + timeout
    while not path.is_file():
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"CLI exited before {path.name}: {stdout}\n{stderr}")
        if time.monotonic() >= deadline:
            pytest.fail(f"CLI did not reach {path.name} within {timeout}s")
        time.sleep(0.01)
    return json.loads(path.read_text(encoding="utf-8"))


def _events(control: Path, *, tolerate_partial: bool = False):
    path = control / "calls.jsonl"
    if not path.exists():
        return []
    rows = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if tolerate_partial and index == len(lines) - 1:
                continue
            raise
    return rows


def _assert_calls(control: Path, kind: str, labels: list[str]):
    calls = _events(control)
    assert [event["label"] for event in calls] == labels
    assert all(event["kind"] == kind for event in calls)
    if kind == "provider":
        for event, label in zip(calls, labels, strict=True):
            assert f"TOKEN_{label.upper()}" in event["prompt"]


def _proc_state(pid: int):
    try:
        record = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return record[record.rfind(")") + 2:].split()[0]


def _kill_known_processes(process, control: Path):
    if getattr(process, "_dynamic_test_tree_cleaned", False):
        return "", ""
    groups = {process.pid} if process.poll() is None else set()
    pids = set()
    deadline = time.monotonic() + 3
    settled = 0
    while time.monotonic() < deadline:
        for event in _events(control, tolerate_partial=True):
            if type(event.get("pid")) is int:
                pids.add(event["pid"])
            if type(event.get("pgid")) is int and event["pgid"] > 1:
                groups.add(event["pgid"])
        gate = control / "gate.json"
        if gate.exists():
            try:
                event = json.loads(gate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                event = None
            if event is not None and process.poll() is None:
                pids.add(event["pid"])
                groups.add(event["pgid"])
        for pgid in groups:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is not None and all(_proc_state(pid) in (None, "Z") for pid in pids):
            settled += 1
            if settled >= 4:
                break
        else:
            settled = 0
        time.sleep(0.025)
    stdout, stderr = process.communicate(timeout=8)
    assert process.returncode is not None, (stdout, stderr)
    for pid in pids:
        deadline = time.monotonic() + 2
        while _proc_state(pid) not in (None, "Z") and time.monotonic() < deadline:
            time.sleep(0.01)
        assert _proc_state(pid) in (None, "Z"), f"fixture process {pid} survived interruption"
    process._dynamic_test_tree_cleaned = True
    return stdout, stderr


def _cleanup_cli(process, control: Path):
    _kill_known_processes(process, control)


def _run_cli(case, control: Path, args=None):
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", *(case["args"] if args is None else args)],
        cwd=case["root"], env=_env(case, control), capture_output=True, text=True,
        timeout=30, check=False,
    )


def _run_root(case):
    (root,) = (case["root"] / ".orchestrate/runs").iterdir()
    return root


def _tree_snapshot(root: Path):
    snapshot = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[name] = ("symlink", os.readlink(path))
        elif path.is_dir():
            snapshot[name] = ("directory",)
        else:
            snapshot[name] = ("file", path.read_bytes())
    return snapshot


def _assert_interrupted_source_free(case, control, run_root, before):
    source_bytes = case["source"].read_bytes()
    case["source"].unlink()
    try:
        calls_before = _events(control)
        view = load_dynamic_view(run_root)
        assert view["status"] == "interrupted" and view["resumable"] is False
        assert _events(control) == calls_before
        snapshot = _tree_snapshot(run_root)
        assert snapshot == before

        run_id = run_root.name
        resume = _run_cli(case, control, ["resume", run_id])
        assert resume.returncode == 2 and "dynamic_resume_unsupported" in resume.stderr
        assert _events(control) == calls_before
        invalidate = _run_cli(case, control, ["invalidate", run_id, "unused-effect"])
        assert invalidate.returncode == 2 and "dynamic_invalidation_unsupported" in invalidate.stderr
        assert _events(control) == calls_before
        assert _tree_snapshot(run_root) == before
    finally:
        case["source"].write_bytes(source_bytes)


def _assert_fresh_run_does_not_adopt_orphan(case, control, old_root, old_snapshot, kind):
    old_state = _state(old_root)
    assert old_state["status"] == "running" and old_state["workflow_outputs"] is None
    old_row, = old_state["effects"]
    assert old_row["status"] == "running"
    old_event, = _events(control)
    old_result = Path(old_event["result_path"])
    if not old_result.is_absolute():
        old_result = case["root"] / old_result
    assert old_result.resolve() == (old_root / old_row["result_path"]).resolve()
    old_result_bytes = old_result.read_bytes()

    fresh_control = control.parent / ".fresh-orphan-control"
    fresh_control.mkdir()
    fresh = _run_cli(case, fresh_control)
    assert fresh.returncode == 0, fresh.stderr
    new_roots = [root for root in (case["root"] / ".orchestrate/runs").iterdir() if root != old_root]
    new_root, = new_roots
    assert new_root.name != old_root.name
    new_view = load_dynamic_view(new_root)
    assert new_view["status"] == "completed"
    new_row, = new_view["effects"]
    assert new_row["status"] == "completed"
    assert 0 < new_view["steps_used"] <= new_view["budget"] == 80
    new_event, = _events(fresh_control)
    assert new_event["kind"] == kind and new_event["label"] == "only"
    new_result = Path(new_event["result_path"])
    if not new_result.is_absolute():
        new_result = case["root"] / new_result
    assert new_result.resolve() == (new_root / new_row["result_path"]).resolve()
    assert new_result.is_file() and new_result != old_result
    assert old_result.read_bytes() == old_result_bytes
    assert _tree_snapshot(old_root) == old_snapshot


def _state(run_root):
    return json.loads((run_root / "state.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind", ["command", "provider"])
@pytest.mark.parametrize("barrier", ["pre_dispatch", "in_flight", "before_row", "before_terminal"])
def test_public_effect_kill_leaves_source_free_interrupted_authority(tmp_path, kind, barrier):
    case = _write_case(tmp_path, kind)
    control = tmp_path / ".interrupt-control"
    block_label = "only" if barrier == "in_flight" else ""
    with _live_cli(case, control,
                   barrier="pre_dispatch" if barrier == "pre_dispatch" else barrier,
                   block_label=block_label) as process:
        readiness = control / ("effect-ready.json" if barrier == "in_flight" else "gate.json")
        marker = _wait_file(process, readiness)
        run_root = _run_root(case)
        state = _state(run_root)
        assert state["status"] == "running" and state["workflow_outputs"] is None
        assert state["effects"]
        if barrier == "before_terminal":
            assert state["current_effect"] is None
            assert [row["status"] for row in state["effects"]] == ["completed"]
        else:
            assert state["current_effect"] == 1
            row = state["effects"][0]
            assert row["effect_class"] == kind and row["status"] == "running"
        assert (run_root / "effects/1/attempt-1").is_dir()

        if barrier == "pre_dispatch":
            assert marker["barrier"] == "pre_dispatch"
            _assert_calls(control, kind, [])
        elif barrier == "in_flight":
            assert marker["kind"] == kind and marker["label"] == "only"
            _assert_calls(control, kind, ["only"])
            attempt = run_root / "effects/1/attempt-1"
            assert not (attempt / "result.json").exists()
            if kind == "provider":
                assert (attempt / "prompt.txt").is_file()
        elif barrier == "before_row":
            assert marker["barrier"] == "before_row"
            _assert_calls(control, kind, ["only"])
            attempt = run_root / "effects/1/attempt-1"
            assert (attempt / "result.json").is_file()
            assert (attempt / "stdout.txt").is_file() and (attempt / "stderr.txt").is_file()
        else:
            assert marker["barrier"] == "before_terminal"
            _assert_calls(control, kind, ["only"])
            assert [effect["status"] for effect in state["effects"]] == ["completed"]
            assert state["current_effect"] is None
            assert state["workflow_outputs"] is None

        _kill_known_processes(process, control)
        assert process.returncode == -signal.SIGKILL

        view = load_dynamic_view(run_root)
        assert view["status"] == "interrupted" and view["resumable"] is False
        assert view["workflow_outputs"] is None
        assert _state(run_root)["status"] == "running"
        before = _tree_snapshot(run_root)
        _assert_interrupted_source_free(case, control, run_root, before)
        if barrier == "before_row":
            _assert_fresh_run_does_not_adopt_orphan(case, control, run_root, before, kind)


@pytest.mark.parametrize("kind", ["command", "provider"])
def test_killed_two_effect_prefix_repeats_on_a_fresh_public_run(tmp_path, kind):
    case = _write_case(tmp_path, kind, two_effects=True, budget=80)
    control = tmp_path / ".interrupt-control"
    with _live_cli(case, control, barrier="second_dispatch") as process:
        marker = _wait_file(process, control / "gate.json")
        assert marker["barrier"] == "second_dispatch" and marker["kind"] == kind
        old_root = _run_root(case)
        interrupted = _state(old_root)
        assert interrupted["status"] == "running" and interrupted["workflow_outputs"] is None
        assert interrupted["current_effect"] == 2 and interrupted["steps_used"] > 0
        assert [(row["ordinal"], row["status"]) for row in interrupted["effects"]] == [
            (1, "completed"), (2, "running")]
        assert (old_root / "effects/1/attempt-1/result.json").is_file()
        assert not (old_root / "effects/2/attempt-1/result.json").exists()
        _assert_calls(control, kind, ["one"])
        _kill_known_processes(process, control)
        assert process.returncode == -signal.SIGKILL

        before = _tree_snapshot(old_root)
        _assert_interrupted_source_free(case, control, old_root, before)
        assert load_dynamic_view(old_root)["budget"] == 80

        fresh_control = tmp_path / ".fresh-control"
        fresh_control.mkdir()
        fresh = _run_cli(case, fresh_control)
        assert fresh.returncode == 0, fresh.stderr
        roots = sorted((case["root"] / ".orchestrate/runs").iterdir())
        assert len(roots) == 2
        new_root = next(root for root in roots if root != old_root)
        assert new_root.name != old_root.name
        completed = load_dynamic_view(new_root)
        assert completed["status"] == "completed"
        assert [row["status"] for row in completed["effects"]] == ["completed", "completed"]
        assert 0 < completed["steps_used"] <= completed["budget"] == 80
        _assert_calls(fresh_control, kind, ["one", "two"])
        assert _tree_snapshot(old_root) == before


@pytest.mark.parametrize("kill_cli_first", [False, True])
def test_harness_finally_kills_known_provider_process_after_test_failure(tmp_path, kill_cli_first):
    case = _write_case(tmp_path, "provider")
    control = tmp_path / ".interrupt-control"
    holder = {}
    with pytest.raises(AssertionError, match="intentional cleanup witness"):
        with _live_cli(case, control, block_label="only") as process:
            holder["process"] = process
            _wait_file(process, control / "effect-ready.json")
            if kill_cli_first:
                os.kill(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
                assert process.returncode == -signal.SIGKILL
                (provider_event,) = _events(control)
                assert _proc_state(provider_event["pid"]) not in (None, "Z")
            raise AssertionError("intentional cleanup witness")

    process = holder["process"]
    (event,) = _events(control)
    assert process.returncode == -signal.SIGKILL
    assert _proc_state(event["pid"]) in (None, "Z")
    assert not (control / "release").exists()
    view = load_dynamic_view(_run_root(case))
    assert view["status"] == "interrupted" and view["effects"][0]["status"] == "running"
