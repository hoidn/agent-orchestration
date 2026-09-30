"""Resume behavior of Workflow Lisp effects without a committed result.

Each test asserts the intended behavior. A case that fails today carries a
strict xfail that names its defect. Runs go through the public entry
(`run_workflow`, `resume_workflow`)
with the command probe and helpers of
`tests/test_workflow_resume_after_known_failure.py`.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.test_workflow_lisp_generic_unions_runtime import _log
from tests.test_workflow_lisp_provider_supervision_e2e import _install_fake_provider_runtime
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor
from tests.test_workflow_resume_after_known_failure import (
    CALL,
    LOOP,
    PRELUDE,
    _all_resume_diagnostics,
    _install,
    _interrupt_command,
    _Interruption,
    _mark_probe_must_not_repeat,
    _outcome,
    _repair,
    _resume,
    _run,
)
from tests.e2e.test_e2e_workflow_lisp_run_ref import _commit_candidate
from orchestrator.workflow.run_ref.runtime import (
    RunRefRuntimeDependencies,
    RunRefRuntimeError,
)


REFUSAL = "lexical_restore_pending_effect_unsafe"
COMMAND_LINE = PRELUDE.splitlines().index(
    '    (command-result probe :argv ("python" "PROBE" name) :returns Note))'
) + 1
COMMAND_COLUMN = PRELUDE.splitlines()[COMMAND_LINE - 1].index("(command-result") + 1

LOOP_TWO_CALLS = PRELUDE + """  (defproc pair ((name String)) -> Note
    :effects ((uses-command probe))
    :lowering private-workflow
    (step name))
  (defworkflow run () -> Note
    (loop/recur :max 4
      :state (record Note :note "seed")
      :on-exhausted state
      (fn (state)
        (let* ((first (pair state.note))
               (second (pair first.note)))
          (if (= second.note "seed++++++++")
            (done second)
            (continue second)))))))
"""

NESTED_CALL = PRELUDE + """  (defproc leaf () -> Note
    :effects ((uses-command probe))
    :lowering private-workflow
    (step "two"))
  (defproc middle () -> Note
    :effects ((uses-command probe))
    :lowering private-workflow
    (leaf))
  (defworkflow run () -> Note
    (let* ((answer (middle)))
      answer)))
"""

SUPERVISED = PRELUDE + """  (defworkflow run () -> Note
    (let* ((answer
             (with-live-providers
               ((worker
                 (provider-result providers.worker
                   :prompt prompts.worker :inputs () :timeout-sec 30 :returns String))
                (supervisor
                 (provider-result providers.supervisor
                   :prompt prompts.supervisor :inputs () :timeout-sec 30
                   :returns ProviderSteeringDirective)
                 :observes worker))
               worker)))
      (step answer))))
"""

PEER_GROUP = PRELUDE + """  (defworkflow run () -> Note
    (let* ((answer
             (with-live-provider-peers
               ((worker
                 (provider-result providers.worker
                   :prompt prompts.worker :inputs () :timeout-sec 30 :returns String))
                (reviewer
                 (provider-result providers.reviewer
                   :prompt prompts.reviewer :inputs () :timeout-sec 30 :returns Bool)))
               worker)))
      (step answer))))
"""

def _refusals(value: object):
    """Every mapping in the state, at any depth, whose diagnostics name the refusal."""

    if isinstance(value, dict):
        diagnostics = value.get("diagnostics")
        if isinstance(diagnostics, list) and REFUSAL in diagnostics:
            yield value
        for item in value.values():
            yield from _refusals(item)
    elif isinstance(value, list):
        for item in value:
            yield from _refusals(item)


def _assert_located_refusal(exit_code: int, state: dict, files: dict[str, Path], log: list[str]) -> None:
    refusals = list(_refusals(state))
    assert (exit_code, state["status"], _log(files["probe"]), bool(refusals)) == (1, "failed", log, True)
    locations = [refusal.get("source_location") or {} for refusal in refusals]
    assert [
        (location.get("path"), location.get("line"), location.get("column"))
        for location in locations
    ] == [
        ("entry.orc", COMMAND_LINE, COMMAND_COLUMN)
    ] * len(locations)


def _rerun_recorded(state: dict) -> bool:
    return "workflow_effect_rerun" in {row["diagnostic"] for row in _all_resume_diagnostics(state)}


def _command_reruns(state: dict) -> list[dict]:
    return [
        row
        for row in _all_resume_diagnostics(state)
        if row.get("diagnostic") == "workflow_effect_rerun"
        and row.get("effect_kind") == "command"
    ]


def _interrupt_after_call_commit(call_number: int):
    """Interrupt after a selected top-level called-workflow result is durable."""

    original = WorkflowExecutor._execute_nested_loop_step
    completed_calls = 0

    def interrupt_after_commit(
        self,
        step,
        context,
        state,
        iteration_state,
        parent_scope_steps,
        *args,
        **kwargs,
    ):
        nonlocal completed_calls
        finalized = original(
            self,
            step,
            context,
            state,
            iteration_state,
            parent_scope_steps,
            *args,
            **kwargs,
        )
        if (
            getattr(self.state_manager, "frame_id", None) is None
            and self._execution_kind_for_step(step)
            is ExecutableNodeKind.CALL_BOUNDARY
            and finalized.get("status") == "completed"
        ):
            completed_calls += 1
            if completed_calls == call_number:
                raise _Interruption
        return finalized

    return patch.object(
        WorkflowExecutor,
        "_execute_nested_loop_step",
        interrupt_after_commit,
    )


def _install_supervised(root: Path, monkeypatch: pytest.MonkeyPatch):
    files = _install(root, SUPERVISED)
    files["providers"].write_text(
        json.dumps({"providers.worker": "codex", "providers.supervisor": "supervisor-provider"}),
        encoding="utf-8",
    )
    files["prompts"].write_text(
        json.dumps({"prompts.worker": "worker.md", "prompts.supervisor": "supervisor.md"}),
        encoding="utf-8",
    )
    for name in ("worker", "supervisor"):
        (root / "grt" / f"{name}.md").write_text("Answer.\n", encoding="utf-8")
    return files, _install_fake_provider_runtime(monkeypatch)


def _run_without_debug_yaml(files: dict[str, Path]) -> int:
    """Use the public run entry without invoking its unrelated run-ref YAML serializer."""

    import sys

    from orchestrator.cli.commands.run import run_workflow
    from tests.test_workflow_lisp_rich_loop_values_e2e import (
        _run_args,
        _run_argv,
    )

    args = _run_args(files)
    args.emit_debug_yaml = False
    args.command_boundaries_file = str(files["commands"])
    workspace = files["source"].resolve().parent.parent
    args.run_ref_root = str(
        workspace.parent / f"{workspace.name}-run-ref-root"
    )
    argv = [arg for arg in _run_argv(files) if arg != "--emit-debug-yaml"]
    argv.extend(("--command-boundaries-file", str(files["commands"])))
    argv.extend(("--run-ref-root", args.run_ref_root))
    with patch.object(sys, "argv", argv):
        return run_workflow(args).exit_code


@pytest.mark.parametrize("must_not_repeat", [False, True], ids=["rerun", "must_not_repeat"])
def test_interrupted_command_in_a_later_loop_iteration_runs_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, must_not_repeat: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, LOOP)
    if must_not_repeat:
        _mark_probe_must_not_repeat(files)
    with _interrupt_command("seed+"), pytest.raises(_Interruption):
        _run(files)
    assert _log(files["probe"]) == ["seed", "seed+"]

    exit_code, state = _resume(tmp_path)

    if must_not_repeat:
        _assert_located_refusal(exit_code, state, files, ["seed", "seed+"])
        return
    assert (*_outcome(exit_code, state, files), _rerun_recorded(state)) == (
        0, "completed", {"return__note": "seed+++"}, ["seed", "seed+", "seed+", "seed++"], True,
    )


@pytest.mark.parametrize("command_index", range(8), ids=[f"command-{index + 1}" for index in range(8)])
def test_interrupted_command_across_called_workflow_iterations_and_callsites_runs_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command_index: int
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, LOOP_TWO_CALLS)
    command_args = ["seed" + "+" * index for index in range(8)]
    interrupted = command_args[command_index]
    with _interrupt_command(interrupted), pytest.raises(_Interruption):
        _run(files)
    assert _log(files["probe"]) == command_args[: command_index + 1]

    exit_code, state = _resume(tmp_path)

    expected_log = command_args[: command_index + 1] + [interrupted] + command_args[command_index + 1 :]
    assert (*_outcome(exit_code, state, files), _rerun_recorded(state)) == (
        0, "completed", {"return__note": "seed++++++++"}, expected_log, True,
    )
    reruns = _command_reruns(state)
    assert len(reruns) == 1
    location = reruns[0]["source_location"]
    assert (location["path"], location["line"], location["column"]) == (
        "entry.orc", COMMAND_LINE, COMMAND_COLUMN
    )
    assert isinstance(location["step_id"], str) and location["step_id"]


@pytest.mark.parametrize(
    ("iteration", "call_number"),
    ((1, 1), (2, 3), (4, 7)),
    ids=["first-iteration", "second-iteration", "last-iteration"],
)
def test_interrupt_between_callees_keeps_completed_first_callee_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    iteration: int,
    call_number: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, LOOP_TWO_CALLS)
    command_args = ["seed" + "+" * index for index in range(8)]
    committed_prefix = command_args[:call_number]
    with _interrupt_after_call_commit(call_number), pytest.raises(_Interruption):
        _run(files)
    assert _log(files["probe"]) == committed_prefix

    exit_code, state = _resume(tmp_path)

    assert (*_outcome(exit_code, state, files), _rerun_recorded(state)) == (
        0, "completed", {"return__note": "seed++++++++"}, command_args, False,
    )


@pytest.mark.parametrize(
    "must_not_repeat",
    [pytest.param(False, id="rerun"), pytest.param(True, id="must_not_repeat")],
)
def test_interrupted_command_after_a_provider_group_runs_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, must_not_repeat: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    files, providers = _install_supervised(tmp_path, monkeypatch)
    if must_not_repeat:
        _mark_probe_must_not_repeat(files)
    with _interrupt_command("fresh-value"), pytest.raises(_Interruption):
        _run(files)
    assert (len(providers.executed), _log(files["probe"])) == (2, ["fresh-value"])

    exit_code, state = _resume(tmp_path)

    assert len(providers.executed) == 2
    if must_not_repeat:
        _assert_located_refusal(exit_code, state, files, ["fresh-value"])
        return
    assert (*_outcome(exit_code, state, files), _rerun_recorded(state)) == (
        0, "completed", {"return__note": "fresh-value+"}, ["fresh-value", "fresh-value"], True,
    )


def test_pre_repair_provider_group_state_refuses_at_the_interrupted_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    files, providers = _install_supervised(tmp_path, monkeypatch)
    emit_shadow = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit

    def omit_group_shadow(self, state, step_name, step, finalized):
        if self._resolve_step_type(step) in {"provider_supervision", "provider_peer_group"}:
            return
        emit_shadow(self, state, step_name, step, finalized)

    monkeypatch.setattr(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        omit_group_shadow,
    )
    with _interrupt_command("fresh-value"), pytest.raises(_Interruption):
        _run(files)
    assert (len(providers.executed), _log(files["probe"])) == (2, ["fresh-value"])

    exit_code, state = _resume(tmp_path)

    context = state["error"]["context"]
    location = context["source_location"]
    assert (exit_code, state["status"], _log(files["probe"])) == (
        1, "failed", ["fresh-value"]
    )
    assert len(providers.executed) == 2
    assert "lexical_default_resume_prior_boundary_not_restorable" in context["diagnostics"]
    assert (location["path"], location["line"], location["column"]) == (
        "entry.orc", COMMAND_LINE, COMMAND_COLUMN
    )


def test_interrupted_command_after_a_peer_group_runs_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_workflow_lisp_provider_peer_group_e2e import (
        _install_controlled_public_adapters,
    )

    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, PEER_GROUP)
    files["providers"].write_text(
        json.dumps({"providers.worker": "codex", "providers.reviewer": "codex"}),
        encoding="utf-8",
    )
    files["prompts"].write_text(
        json.dumps({"prompts.worker": "worker.md", "prompts.reviewer": "reviewer.md"}),
        encoding="utf-8",
    )
    (tmp_path / "grt" / "worker.md").write_text("Answer.\n", encoding="utf-8")
    (tmp_path / "grt" / "reviewer.md").write_text("Answer.\n", encoding="utf-8")
    harness = _install_controlled_public_adapters(
        monkeypatch,
        member_ids=("worker", "reviewer"),
        values={"worker": "fresh-value", "reviewer": True},
    )
    with _interrupt_command("fresh-value"), pytest.raises(_Interruption):
        _run(files)
    assert _log(files["probe"]) == ["fresh-value"]
    assert {name: len(calls) for name, calls in harness.resolved_commands.items()} == {
        "worker": 1, "reviewer": 1
    }

    exit_code, state = _resume(tmp_path)

    assert (*_outcome(exit_code, state, files), _rerun_recorded(state)) == (
        0, "completed", {"return__note": "fresh-value+"}, ["fresh-value", "fresh-value"], True,
    )
    assert {name: len(calls) for name, calls in harness.resolved_commands.items()} == {
        "worker": 1, "reviewer": 1
    }


@pytest.mark.parametrize("interrupted", [False, True], ids=["failed", "interrupted"])
def test_nonrepeatable_command_inside_a_called_workflow_is_refused_with_a_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, CALL, broken=() if interrupted else ("two",))
    _mark_probe_must_not_repeat(files)
    if interrupted:
        with _interrupt_command("two"), pytest.raises(_Interruption):
            _run(files)
    else:
        assert _run(files) == 1
        _repair(files, "two")
    assert _log(files["probe"]) == ["prepare", "one", "two"]

    exit_code, state = _resume(tmp_path)

    _assert_located_refusal(exit_code, state, files, ["prepare", "one", "two"])


def test_nonrepeatable_command_inside_a_nested_callee_is_refused_with_a_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, NESTED_CALL)
    _mark_probe_must_not_repeat(files)
    with _interrupt_command("two"), pytest.raises(_Interruption):
        _run(files)
    assert _log(files["probe"]) == ["two"]

    exit_code, state = _resume(tmp_path)

    _assert_located_refusal(exit_code, state, files, ["two"])


@pytest.mark.parametrize(
    ("crash_boundary", "launches_at_hook", "expected_launches", "interrupted"),
    (
        ("launch", 1, 2, False),
        ("child_completion", 2, 3, False),
        ("launch", 1, 2, True),
    ),
    ids=("failed-launch", "failed-child-completion", "interrupted-launch"),
)
def test_run_ref_rerun_diagnostic_preserves_committed_prior_site_and_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_boundary: str,
    launches_at_hook: int,
    expected_launches: int,
    interrupted: bool,
) -> None:
    candidate = tmp_path / "candidate"
    commit = _commit_candidate(
        candidate,
        """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export run)
  (defworkflow run () -> Bool
    true))
""",
    )
    source = PRELUDE + f"""  (defworkflow run () -> Bool
    (let* ((before (step "before"))
           (first
             (run-ref
               :source (:repo "{candidate.resolve().as_uri()}" :commit "{commit}")
               :program (:path "candidate.orc" :entry run)
               :inputs () :returns Bool
               :policy (:environment :deterministic-effect-free :setup ())))
           (second
             (run-ref
               :source (:repo "{candidate.resolve().as_uri()}" :commit "{commit}")
               :program (:path "candidate.orc" :entry run)
               :inputs () :returns Bool
               :policy (:environment :deterministic-effect-free :setup ()))))
      second.value)))
"""
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, source, target="2.24")
    launches = []
    crash_fired = False
    base_dependencies = RunRefRuntimeDependencies()

    def counted_launch(launch):
        launches.append(launch)
        return base_dependencies.launch_child(launch)

    def crash(boundary: str) -> None:
        nonlocal crash_fired
        if (
            not crash_fired
            and boundary == crash_boundary
            and len(launches) == launches_at_hook
        ):
            crash_fired = True
            if interrupted:
                raise _Interruption
            raise RunRefRuntimeError("run_ref_child_launch_failed", "injected-resume-case")

    monkeypatch.setattr(
        WorkflowExecutor,
        "_run_ref_runtime_dependencies",
        replace(base_dependencies, launch_child=counted_launch, crash_hook=crash),
        raising=False,
    )
    if interrupted:
        with pytest.raises(_Interruption):
            _run_without_debug_yaml(files)
    else:
        assert _run_without_debug_yaml(files) != 0
    assert _log(files["probe"]) == ["before"]
    run_id = next((tmp_path / ".orchestrate" / "runs").iterdir()).name
    before_state = json.loads(
        (tmp_path / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8")
    )
    assert before_state["current_step"]["type"] == "run_ref"
    assert before_state["current_step"]["status"] == ("running" if interrupted else "failed")
    assert before_state["current_step"]["name"] not in before_state["steps"]
    assert len(launches) == launches_at_hook
    first_child_id = launches[0].child_run_id

    exit_code, state = _resume(tmp_path)

    assert (exit_code, state["status"], _log(files["probe"])) == (0, "completed", ["before"])
    assert len(launches) == expected_launches
    assert sum(launch.child_run_id == first_child_id for launch in launches) == 1
    reruns = [
        row
        for row in _all_resume_diagnostics(state)
        if row.get("diagnostic") == "workflow_effect_rerun"
    ]
    assert len(reruns) == 1
    assert reruns[0]["effect_kind"] == "run_ref"
