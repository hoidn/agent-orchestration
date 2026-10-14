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
import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.exec.step_executor import StepExecutor
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_lisp_generic_union_provider_results import _Provider
from tests.workflow_evaluated_totality_helpers import _log, _public_run_files, _write_sources
from tests.test_workflow_evaluated_cli import _run_args, _run_argv


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


def test_a_stale_file_on_an_ordinary_nested_bundle_path_is_removed(tmp_path: Path) -> None:
    stale = tmp_path / "a" / "b" / "result.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")
    files = WorkspaceFiles(tmp_path)
    try:
        error = files.clear("a/b/result.json")
    finally:
        files.close()

    assert (error, stale.exists()) == (None, False)


def test_a_bundle_path_whose_last_component_is_a_link_removes_the_link_and_not_its_target(tmp_path: Path) -> None:
    target = tmp_path / "kept.json"
    target.write_text("kept", encoding="utf-8")
    link = tmp_path / "a" / "result.json"
    link.parent.mkdir()
    link.symlink_to(target)
    files = WorkspaceFiles(tmp_path)
    try:
        error = files.clear("a/result.json")
    finally:
        files.close()

    assert (error, link.is_symlink(), target.read_text(encoding="utf-8")) == (None, False, "kept")
