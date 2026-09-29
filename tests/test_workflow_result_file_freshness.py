"""A result file is absent before every command and provider call (plan Task 8).

Contract: `specs/io.md`, command and provider structured-bundle environment.
A call delivers its result as a JSON file at `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
A file left at that path by an earlier iteration, an earlier run or an
interrupted call is never read as the result of a new call: a call that writes
nothing fails with the existing `missing_bundle_file` contract violation.
Clearing the path never acts outside the workspace, and a path that cannot be
cleared fails the call before launch with `stale_bundle_removal_failed`.

Commands are a probe that logs its argument; providers are a stand-in provider
executor (no real provider call). Programs run through the public run and
resume entries. Two shapes reach two path families: a call written directly in
the loop body gets an entry path that names the run but not the iteration; a
procedure call in the loop body is promoted to a call whose path names the
iteration but not the run.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.exec.step_executor import StepExecutor
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.workflow.executor import WorkflowExecutor
from tests.test_workflow_lisp_generic_union_provider_results import _Provider
from tests.test_workflow_lisp_generic_unions_runtime import _log, _public_run_files, _write_sources
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv


SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Count (n Int) (stop Bool))
  (defproc tick ((state Count)) -> Count
    :effects ((EFFECT))
    :lowering inline
    CALL)
  (defworkflow run () -> Count
    (loop/recur :max 3
      :state (record Count :n 0 :stop false)
      :on-exhausted state
      (fn (state)
        (let* ((next BODY))
          (if next.stop (done next) (continue next)))))))
"""

EXHAUSTED_AFTER_THREE_WRITES = {"return__n": 3, "return__stop": False}

PROBE_PRELUDE = """import json, os, sys
from pathlib import Path
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(sys.argv[1] + "\\n")
n = int(sys.argv[1])
bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
"""

# What the probe writes for its argument `n`; the stand-in provider does the
# same for its call number (1, 2, 3), so both finish a full loop at n = 3.
PROBE_WRITES = {
    "every_call": 'bundle.write_text(json.dumps({"n": n + 1, "stop": False}), encoding="utf-8")\n',
    "first_call_only": 'if n == 0:\n    bundle.write_text(json.dumps({"n": 1, "stop": False}), encoding="utf-8")\n',
    "partial": 'bundle.write_text(\'{"n": 1\', encoding="utf-8")\n',
    "nothing": "",
}


class _Interrupted(BaseException):
    """The orchestrator process stops after the call returned, before validation."""


class _Commands:
    effect = "uses-command probe_tick"
    call = '(command-result probe_tick :argv ("python" "PROBE" state.n) :returns Count)'

    def __init__(self, root: Path) -> None:
        self.probe = root / "probe_tick.py"
        self.files = _public_run_files(root, {"probe_tick": self.probe})
        self.interrupt_first_call = False

    def source(self, text: str) -> str:
        return text.replace("PROBE", self.probe.as_posix())

    def writes(self, policy: str) -> None:
        self.probe.write_text(PROBE_PRELUDE + PROBE_WRITES[policy], encoding="utf-8")

    @property
    def calls(self) -> int:
        return len(_log(self.probe))

    @contextmanager
    def active(self):
        original = StepExecutor.execute_command

        def execute_command(executor, step_name, command, *args, **kwargs):
            result = original(executor, step_name, command, *args, **kwargs)
            if self.interrupt_first_call and self.calls == 1:
                raise _Interrupted
            return result

        with patch.object(StepExecutor, "execute_command", execute_command):
            yield


class _Providers(_Provider):
    effect = "uses-provider providers.tick"
    call = "(provider-result providers.tick :prompt prompts.tick :inputs (state) :returns Count)"

    def __init__(self, root: Path) -> None:
        super().__init__(payload={})
        self.files = _public_run_files(root, {})
        self.files["providers"].write_text(json.dumps({"providers.tick": "codex"}), encoding="utf-8")
        self.files["prompts"].write_text(json.dumps({"prompts.tick": "tick.md"}), encoding="utf-8")
        _write_sources(root, {"grt/tick.md": "Advance the count.\n"})
        self.policy = "nothing"
        self.interrupt_first_call = False
        self.fail_first_call = False

    def source(self, text: str) -> str:
        return text

    def writes(self, policy: str) -> None:
        self.policy = policy

    def execute(self, invocation, **_kwargs):
        self.calls += 1
        bundle = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if self.policy == "every_call" or (self.policy == "first_call_only" and self.calls == 1):
            bundle.write_text(json.dumps({"n": self.calls, "stop": False}), encoding="utf-8")
        elif self.policy == "partial":
            bundle.write_text('{"n": 1', encoding="utf-8")
        if self.interrupt_first_call and self.calls == 1:
            raise _Interrupted
        return SimpleNamespace(
            exit_code=1 if self.fail_first_call and self.calls == 1 else 0, stdout=b"", stderr=b"", duration_ms=1, error=None, missing_placeholders=None,
            invalid_prompt_placeholder=False, raw_stdout=None, normalized_stdout=None, provider_session=None,
        )

    @contextmanager
    def active(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(ProviderExecutor, "prepare_invocation", self.prepare_invocation))
            stack.enter_context(patch.object(ProviderExecutor, "execute", self.execute))
            yield


@pytest.fixture(params=[_Commands, _Providers], ids=["command", "provider"])
def effect_kind(request):
    return request.param


def _install(root: Path, effect_kind, *, body: str, target: str = "2.33"):
    """Write the program; `body` is "call" (entry path) or "procedure" (promoted call path)."""

    effect = effect_kind(root)
    text = SOURCE.replace("EFFECT", effect.effect).replace("CALL", effect.call)
    text = text.replace("BODY", effect.call if body == "call" else "(tick state)").replace("TARGET", target)
    _write_sources(root, {"grt/entry.orc": effect.source(text)})
    return effect


def _runs(root: Path) -> set[Path]:
    runs = root / ".orchestrate" / "runs"
    return set(runs.iterdir()) if runs.exists() else set()


def _run(effect, *, max_retries: int = 0) -> tuple[str, dict[str, object]]:
    """Run once through the public entry; return the new run id and its final state."""

    args = _run_args(effect.files)
    args.command_boundaries_file = str(effect.files["commands"])
    args.max_retries = max_retries
    argv = [*_run_argv(effect.files), "--command-boundaries-file", str(effect.files["commands"])]
    before = _runs(Path.cwd())
    with effect.active(), patch.object(sys, "argv", argv):
        run_workflow(args)
    (run_dir,) = _runs(Path.cwd()) - before
    return run_dir.name, json.loads((run_dir / "state.json").read_text(encoding="utf-8"))


def _resume(effect, run_id: str) -> dict[str, object]:
    with effect.active():
        resume_workflow(run_id=run_id, retry_delay_ms=0)
    return json.loads((Path.cwd() / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8"))


def _failed_violations(state: dict[str, object]) -> list[dict[str, object]]:
    """Contract violations of every failed step, including steps in call frames."""

    frames = [state, *(frame["state"] for frame in (state.get("call_frames") or {}).values())]
    return [
        violation
        for frame in frames
        for step in frame["steps"].values()
        if isinstance(step, dict) and step.get("status") == "failed"
        for violation in ((step.get("error") or {}).get("context") or {}).get("violations", ())
    ]


def _violations(state: dict[str, object]) -> list[str]:
    return [violation["type"] for violation in _failed_violations(state)]


@pytest.mark.parametrize("target", ["2.26", "2.33"])
def test_a_call_that_writes_its_result_only_in_the_first_iteration_fails_in_the_second(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effect_kind, target: str
) -> None:
    effect = _install(tmp_path, effect_kind, body="call", target=target)
    effect.writes("first_call_only")
    monkeypatch.chdir(tmp_path)

    _run_id, state = _run(effect)

    assert (state["status"], _violations(state), effect.calls) == ("failed", ["missing_bundle_file"], 2)


def test_a_second_run_does_not_read_the_result_file_left_by_the_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effect_kind
) -> None:
    """The promoted call path names the iteration but not the run, so both runs use the same files."""

    effect = _install(tmp_path, effect_kind, body="procedure")
    monkeypatch.chdir(tmp_path)
    effect.writes("every_call")
    _first_id, first = _run(effect)
    effect.writes("nothing")

    _second_id, second = _run(effect)

    assert (first["status"], second["status"], _violations(second)) == (
        "completed",
        "failed",
        ["missing_bundle_file"],
    )


@pytest.mark.parametrize("written", ["every_call", "partial"], ids=["complete-file", "partial-file"])
def test_a_call_interrupted_after_it_wrote_its_result_file_is_not_satisfied_by_that_file_on_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effect_kind, written: str
) -> None:
    effect = _install(tmp_path, effect_kind, body="call")
    effect.writes(written)
    effect.interrupt_first_call = True
    monkeypatch.chdir(tmp_path)
    with pytest.raises(_Interrupted):
        _run(effect)
    (run_dir,) = _runs(tmp_path)
    effect.interrupt_first_call = False
    effect.writes("nothing")

    state = _resume(effect, run_dir.name)

    assert (state["status"], _violations(state), effect.calls) == ("failed", ["missing_bundle_file"], 2)


@pytest.mark.parametrize("body", ["call", "procedure"])
def test_a_loop_of_three_iterations_that_writes_a_result_each_time_still_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effect_kind, body: str
) -> None:
    effect = _install(tmp_path, effect_kind, body=body)
    effect.writes("every_call")
    monkeypatch.chdir(tmp_path)

    _run_id, state = _run(effect)

    assert (state["status"], state["workflow_outputs"], effect.calls) == (
        "completed",
        EXHAUSTED_AFTER_THREE_WRITES,
        3,
    )


def test_a_retried_provider_call_is_not_satisfied_by_the_file_of_the_failed_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first attempt writes a complete result and exits 1 (retryable); the retry writes nothing."""

    effect = _install(tmp_path, _Providers, body="call")
    effect.writes("first_call_only")
    effect.fail_first_call = True
    monkeypatch.chdir(tmp_path)

    _run_id, state = _run(effect, max_retries=1)

    assert (state["status"], _violations(state), effect.calls) == ("failed", ["missing_bundle_file"], 2)


def test_a_bundle_parent_replaced_by_a_link_after_validation_does_not_lead_the_removal_outside_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent passes validation, then becomes a link to a directory outside that holds a file of the same name."""

    workspace, outside = tmp_path / "workspace", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    effect = _install(workspace, _Commands, body="call")
    effect.writes("every_call")
    monkeypatch.chdir(workspace)
    validate = WorkflowExecutor._prepare_runtime_output_bundle_parent
    victims: list[Path] = []

    def validate_then_switch_parent(executor, bundle):
        error = validate(executor, bundle)
        if not victims:
            parent = (workspace / bundle["path"]).parent
            victims.append(outside / Path(bundle["path"]).name)
            victims[0].write_text("outside", encoding="utf-8")
            parent.rename(parent.with_name(parent.name + ".validated"))
            parent.symlink_to(outside, target_is_directory=True)
        return error

    with patch.object(WorkflowExecutor, "_prepare_runtime_output_bundle_parent", validate_then_switch_parent):
        _run_id, state = _run(effect)

    assert (victims[0].read_text(encoding="utf-8"), state["status"], effect.calls) == ("outside", "failed", 0)


def _bare_executor(workspace: Path) -> WorkflowExecutor:
    """Path preparation that succeeds, or is rejected as an escape, reads nothing but the workspace."""

    executor = object.__new__(WorkflowExecutor)
    executor.workspace = workspace
    return executor


@pytest.mark.parametrize("path", ["link/result.json", "../outside/result.json"], ids=["linked-parent", "dot-dot"])
def test_a_bundle_path_through_a_link_or_dot_dot_is_rejected_and_nothing_outside_is_removed(
    tmp_path: Path, path: str
) -> None:
    workspace, outside = tmp_path / "workspace", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    victim = outside / "result.json"
    victim.write_text("outside", encoding="utf-8")

    error = _bare_executor(workspace)._prepare_absent_runtime_output_bundle({}, {"path": path})

    assert (error["error"]["type"], victim.read_text(encoding="utf-8")) == ("contract_violation", "outside")


def test_a_stale_file_on_an_ordinary_nested_bundle_path_is_removed(tmp_path: Path) -> None:
    stale = tmp_path / "a" / "b" / "result.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    error = _bare_executor(tmp_path)._prepare_absent_runtime_output_bundle({}, {"path": "a/b/result.json"})

    assert (error, stale.exists()) == (None, False)


def test_a_bundle_path_whose_last_component_is_a_link_removes_the_link_and_not_its_target(tmp_path: Path) -> None:
    target = tmp_path / "kept.json"
    target.write_text("kept", encoding="utf-8")
    link = tmp_path / "a" / "result.json"
    link.parent.mkdir()
    link.symlink_to(target)

    error = _bare_executor(tmp_path)._prepare_absent_runtime_output_bundle({}, {"path": "a/result.json"})

    assert (error, link.is_symlink(), target.read_text(encoding="utf-8")) == (None, False, "kept")


def test_a_result_path_that_cannot_be_cleared_fails_before_launch_with_its_own_code_at_the_step_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effect_kind
) -> None:
    """An interrupted call left its result file; a directory replaces it before resume runs the call again."""

    effect = _install(tmp_path, effect_kind, body="call")
    effect.writes("every_call")
    effect.interrupt_first_call = True
    monkeypatch.chdir(tmp_path)
    with pytest.raises(_Interrupted):
        _run(effect)
    (run_dir,) = _runs(tmp_path)
    (result_file,) = (tmp_path / ".orchestrate" / "workflow_lisp" / "entry").rglob("*result_bundle.json")
    result_file.unlink()
    result_file.mkdir()
    effect.interrupt_first_call = False

    state = _resume(effect, run_dir.name)

    assert [
        (violation["type"], [(origin["path"], origin["line"] > 0) for origin in violation["source_origins"]])
        for violation in _failed_violations(state)
    ] + [effect.calls] == [("stale_bundle_removal_failed", [(str(effect.files["source"]), True)]), 1]


CONCURRENT_PROBE = """import json, os, time
from pathlib import Path
root = Path(__file__).parent
try:
    marker = os.open(root / "first", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    (root / "second").write_text("started", encoding="utf-8")
else:
    os.close(marker)
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"n": 1, "stop": True}), encoding="utf-8")
    (root / "written").write_text("written", encoding="utf-8")
    deadline = time.monotonic() + 120
    while not (root / "release").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
"""


def test_two_concurrent_runs_do_not_share_the_result_file_of_a_promoted_call(tmp_path: Path) -> None:
    """A second run is refused before it can delete the active call's result."""

    effect = _install(tmp_path, _Commands, body="procedure")
    effect.probe.write_text(CONCURRENT_PROBE, encoding="utf-8")
    run_argv = [arg for arg in _run_argv(effect.files) if arg != "--emit-debug-yaml"]  # recorded argv only, not a CLI flag
    command = [sys.executable, "-m", *run_argv, "--command-boundaries-file", str(effect.files["commands"])]
    first = subprocess.Popen(command, cwd=tmp_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 20
        while not (tmp_path / "written").exists() and first.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (tmp_path / "written").exists(), "first run never reached the held command"
        (active_run,) = _runs(tmp_path)
        second = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=20)
        assert second.returncode == 1
        assert "workspace_run_already_active" in second.stderr
        assert active_run.name in second.stderr
        assert not (tmp_path / "second").exists(), "second run dispatched a command"
    finally:
        (tmp_path / "release").touch()
        try:
            first.wait(timeout=10)
        except subprocess.TimeoutExpired:
            first.kill()
            first.wait(timeout=5)
    states = [json.loads((run_dir / "state.json").read_text(encoding="utf-8")) for run_dir in _runs(tmp_path)]

    assert first.returncode == 0
    assert sorted((state["status"], _violations(state)) for state in states) == [
        ("completed", []),
    ]
