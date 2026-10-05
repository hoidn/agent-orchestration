"""Real public-process interruption comparison for imported ``std/improve``."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from orchestrator.workflow.dynamic.state import load_dynamic_view
from tests.test_workflow_dynamic_improve import _stage_dynamic
from tests.test_workflow_dynamic_interruptions import (
    _kill_known_processes,
    _tree_snapshot,
    _wait_file,
)
from tests.test_workflow_lisp_generic_unions_runtime import (
    _public_run_files,
)
from tests.test_workflow_lisp_improve_stdlib import _write_project
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_argv
from tests.workflow_lisp_improve_stdlib_sources import string_inputs_entry_source


_CLI_GATE = '''\
import json
import os
from pathlib import Path
import time

control = Path(os.environ["IMPROVE_INTERRUPT_CONTROL"])
mode = os.environ["IMPROVE_INTERRUPT_MODE"]
paused = False

def pause(barrier):
    global paused
    if paused:
        return
    paused = True
    marker = control / "gate.json"
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.write_text(json.dumps({
        "barrier": barrier, "pid": os.getpid(), "pgid": os.getpgrp(),
    }), encoding="utf-8")
    temporary.replace(marker)
    while not (control / "release").exists():
        time.sleep(0.01)

if mode == "dynamic":
    from orchestrator.workflow.dynamic.state import DynamicRun

    original_finish_effect = DynamicRun.finish_effect
    def gated_finish_effect(self, *, steps, error=None):
        current = self.state.get("current_effect")
        rows = self.state.get("effects", [])
        should_pause = (
            current == 2 and error is None and rows
            and rows[-1].get("ordinal") == 2
            and rows[-1].get("status") == "running"
        )
        result = original_finish_effect(self, steps=steps, error=error)
        if should_pause:
            pause("dynamic_effect_2_settled")
        return result

    DynamicRun.finish_effect = gated_finish_effect
else:
    from orchestrator.workflow.executor import WorkflowExecutor

    original_checkpoint = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_repeat_until_commit
    def gated_checkpoint(self, step, progress):
        result = original_checkpoint(self, step, progress)
        if progress.get("last_condition_result") is False:
            pause("typed_first_pair_checkpoint_published")
        return result

    WorkflowExecutor._emit_lexical_checkpoint_shadow_after_repeat_until_commit = gated_checkpoint

from orchestrator.cli import main
raise SystemExit(main())
'''

_PROBE_MARKER = '    log.write(" ".join(sys.argv[1:]) + "\\n")\n'
_PROBE_EVENT = '''
event = {
    "hook": os.environ["IMPROVE_INTERRUPT_HOOK"],
    "argv": sys.argv[1:],
    "pid": os.getpid(),
    "pgid": os.getpgrp(),
}
with open(Path(os.environ["IMPROVE_INTERRUPT_CONTROL"]) / "calls.jsonl", "a", encoding="utf-8") as calls:
    calls.write(json.dumps(event, sort_keys=True) + "\\n")
    calls.flush()
    os.fsync(calls.fileno())
'''

_EXPECTED_CALLS = [
    {"hook": "review", "argv": ["draft", "steady", "clear"]},
    {"hook": "revise", "argv": ["draft", "steady", "fb0"]},
    {"hook": "review", "argv": ["draft+r", "steady", "clear"]},
    {"hook": "revise", "argv": ["draft+r", "steady", "fb1"]},
    {"hook": "review", "argv": ["draft+r+r", "steady", "clear"]},
    {"hook": "revise", "argv": ["draft+r+r", "steady", "fb2"]},
]

_DYNAMIC_OUTPUT = {
    "variant": "EXHAUSTED",
    "value": {"title": "draft+r+r+r", "score": 3},
}
_TYPED_OUTPUT = {
    "return__variant": "EXHAUSTED",
    "return__value__title": "draft+r+r+r",
    "return__value__score": 3,
}


def _instrument_probe(path: Path, hook: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(_PROBE_MARKER) == 1
    event = _PROBE_EVENT.replace('"hook": os.environ["IMPROVE_INTERRUPT_HOOK"]', f'"hook": {hook!r}')
    path.write_text(text.replace(_PROBE_MARKER, _PROBE_MARKER + event, 1), encoding="utf-8")


def _prepare_dynamic(root: Path) -> dict[str, object]:
    source, manifest = _stage_dynamic(root)
    for hook in ("review", "revise"):
        _instrument_probe(root / f"probe_{hook}.py", hook)
    inputs = root / "inputs.json"
    inputs.write_text(json.dumps({"seed": "draft", "goal": "steady", "rubric": "clear", "limit": 3}))
    return {
        "kind": "dynamic",
        "root": root,
        "source": source,
        "args": [
            "run", str(source), "--command-boundaries-file", str(manifest),
            "--input-file", str(inputs),
        ],
    }


def _prepare_typed(root: Path, *, string_goal: bool) -> dict[str, object]:
    probes = _write_project(root, seed="draft", limit=3)
    entry = root / "grt" / "entry.orc"
    source = entry.read_text(encoding="utf-8")
    marker = "candidate.title brief.goal)"
    assert source.count(marker) == 1
    source = source.replace(marker, 'candidate.title brief.goal "clear")', 1)
    if string_goal:
        source = string_inputs_entry_source(source)
    else:
        source = source.replace("(defworkflow run ()", "(defworkflow run ((goal String))", 1)
        source = source.replace('(record Brief :goal "tidy")', "(record Brief :goal goal)", 1)
    entry.write_text(source, encoding="utf-8")
    for hook, path in (("review", probes["probe_review"]), ("revise", probes["probe_revise"])):
        _instrument_probe(path, hook)
    files = _public_run_files(root, probes)
    inputs = root / "inputs.json"
    inputs.write_text(json.dumps({"goal": "steady"}))
    cli_args = [
        *(arg for arg in _run_argv(files)[1:] if arg != "--emit-debug-yaml"),
        "--command-boundaries-file", str(files["commands"]),
        "--input-file", str(inputs),
    ]
    return {
        "kind": "typed",
        "root": root,
        "source": entry,
        "args": cli_args,
        "inputs": inputs,
    }


def _environment(case: dict[str, object], control: Path, *, mode: str) -> dict[str, str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "IMPROVE_INTERRUPT_CONTROL": str(control),
        "IMPROVE_INTERRUPT_MODE": mode,
    }
    if case["kind"] == "dynamic":
        env["DYNAMIC_IMPROVE_EVENT_LOG"] = str(Path(case["root"]) / "hook-events.jsonl")
    return env


def _start_public(case: dict[str, object], control: Path, *, mode: str):
    control.mkdir(parents=True, exist_ok=True)
    launcher = control / "public_cli_gate.py"
    launcher.write_text(_CLI_GATE, encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-B", str(launcher), *case["args"]],
        cwd=case["root"], env=_environment(case, control, mode=mode),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )


@contextmanager
def _live_public(case: dict[str, object], control: Path, *, mode: str):
    process = _start_public(case, control, mode=mode)
    try:
        yield process
    finally:
        _kill_known_processes(process, control)


def _calls(control: Path) -> list[dict[str, object]]:
    path = control / "calls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _request_shape(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{"hook": event["hook"], "argv": event["argv"]} for event in events]


def _public_cli(case: dict[str, object], control: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-B", "-m", "orchestrator", *args]
    process = subprocess.Popen(
        command, cwd=case["root"], env=_environment(case, control, mode=""),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )

    def kill_owned_group() -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    try:
        stdout, stderr = process.communicate(timeout=60)
    except BaseException:
        kill_owned_group()
        process.communicate(timeout=8)
        raise
    finally:
        if process.poll() is None:
            kill_owned_group()
            process.communicate(timeout=8)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _only_run_root(case: dict[str, object]) -> Path:
    roots = list((case["root"] / ".orchestrate" / "runs").iterdir())
    assert len(roots) == 1
    return roots[0]


def _assert_gate_killed(process, control: Path, expected_barrier: str) -> dict[str, object]:
    marker = _wait_file(process, control / "gate.json")
    assert marker["barrier"] == expected_barrier
    assert marker["pid"] == marker["pgid"] == process.pid
    _kill_known_processes(process, control)
    assert process.returncode == -signal.SIGKILL
    assert not (control / "release").exists()
    return marker


@pytest.mark.parametrize("string_goal", [False, True], ids=["record-context", "string-goal-capture"])
def test_dynamic_public_improve_kill_restarts_pair_with_fresh_run_and_budget(tmp_path, string_goal):
    dynamic_control = tmp_path / ".dynamic-old-control"
    dynamic = _prepare_dynamic(tmp_path / "dynamic")

    with _live_public(dynamic, dynamic_control, mode="dynamic") as process:
        _assert_gate_killed(process, dynamic_control, "dynamic_effect_2_settled")
        old_root = _only_run_root(dynamic)
        old_view = load_dynamic_view(old_root)
        old_header = json.loads((old_root / "run.json").read_text(encoding="utf-8"))
        assert old_header["bound_inputs"]["goal"] == "steady"
        assert old_view["status"] == "interrupted" and old_view["resumable"] is False
        assert 0 < old_view["steps_used"] < old_view["budget"] == 1000
        assert old_view["workflow_outputs"] is None
        assert [(row["ordinal"], row["status"]) for row in old_view["effects"]] == [
            (1, "completed"), (2, "completed")]
        dynamic_prefix = _calls(dynamic_control)
        assert _request_shape(dynamic_prefix) == _EXPECTED_CALLS[:2]
        assert all(event["pgid"] == process.pid and event["pid"] != process.pid
                   for event in dynamic_prefix)
        before = _tree_snapshot(old_root)

        fresh_control = tmp_path / ".dynamic-fresh-control"
        fresh_control.mkdir()
        fresh = _public_cli(dynamic, fresh_control, dynamic["args"])
        assert fresh.returncode == 0, fresh.stderr
        roots = list((dynamic["root"] / ".orchestrate" / "runs").iterdir())
        assert len(roots) == 2
        fresh_root = next(root for root in roots if root != old_root)
        assert fresh_root.name != old_root.name
        fresh_view = load_dynamic_view(fresh_root)
        fresh_header = json.loads((fresh_root / "run.json").read_text(encoding="utf-8"))
        assert fresh_view["status"] == "completed"
        assert fresh_view["workflow_outputs"] == _DYNAMIC_OUTPUT
        assert 0 < fresh_view["steps_used"] <= fresh_view["budget"] == 1000
        assert fresh_view["steps_used"] > old_view["steps_used"]
        assert fresh_header["bound_inputs"]["goal"] == "steady"
        assert _request_shape(_calls(fresh_control)) == _EXPECTED_CALLS
        dynamic_total_calls = len(_calls(dynamic_control)) + len(_calls(fresh_control))
        assert dynamic_total_calls == 8
        assert _tree_snapshot(old_root) == before

    typed_control = tmp_path / ".typed-control"
    typed = _prepare_typed(tmp_path / "typed", string_goal=string_goal)
    with _live_public(typed, typed_control, mode="typed") as process:
        _assert_gate_killed(process, typed_control, "typed_first_pair_checkpoint_published")
        typed_root = _only_run_root(typed)
        old_state = json.loads((typed_root / "state.json").read_text(encoding="utf-8"))
        assert old_state["bound_inputs"]["goal"] == "steady"
        assert old_state["status"] == "running"
        repeat_state, = old_state["repeat_until"].values()
        assert repeat_state["current_iteration"] == 0
        assert repeat_state["last_condition_result"] is False
        typed_prefix = _calls(typed_control)
        assert _request_shape(typed_prefix) == _EXPECTED_CALLS[:2]
        assert all(event["pgid"] == process.pid and event["pid"] != process.pid
                   for event in typed_prefix)
        typed_run_id = typed_root.name
        first_pair_results = sorted(
            (Path(typed["root"]) / ".orchestrate" / "workflow_lisp" / "calls").rglob("*__result_bundle.json")
        )
        assert len(first_pair_results) == 2
        assert {
            path.name.split("__probe_", 1)[1].split("__", 1)[0]
            for path in first_pair_results
        } == {"review", "revise"}
        expected_results = {
            path.relative_to(typed["root"]).as_posix(): path.read_bytes()
            for path in first_pair_results
        }
        assert {
            "review" if "review_candidate" in path.name else "revise": json.loads(path.read_bytes())
            for path in first_pair_results
        } == {
            "review": {"variant": "REVISE", "feedback": {"note": "fb0"}},
            "revise": {"title": "draft+r", "score": 1},
        }

        resumed = _public_cli(typed, typed_control, ["resume", typed_run_id])
        assert resumed.returncode == 0, resumed.stderr
        assert _only_run_root(typed) == typed_root
        final_state = json.loads((typed_root / "state.json").read_text(encoding="utf-8"))
        assert final_state["status"] == "completed"
        assert final_state["workflow_outputs"] == _TYPED_OUTPUT
        assert _request_shape(_calls(typed_control)) == _EXPECTED_CALLS
        typed_total_calls = len(_calls(typed_control))
        assert typed_total_calls == 6
        assert typed_root.name == typed_run_id
        assert all((Path(typed["root"]) / relative).read_bytes() == data
                   for relative, data in expected_results.items())

    assert dynamic_total_calls - typed_total_calls == 2
