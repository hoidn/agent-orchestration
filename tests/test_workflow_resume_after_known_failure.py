"""Resume behavior for Workflow Lisp effects without a committed result.

Every run goes through the public entry (`run_workflow`, `resume_workflow`).
Effects are command probes that log their argv, and a stand-in provider. A probe
exits 3 while `<name>.broken` exists next to it; deleting that file is the
corrected cause.
"""

from __future__ import annotations

import json
import logging
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.exec.step_executor import StepExecutor
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.workflow_lisp.build_manifest_io import (
    _json_data,
    _parse_command_boundaries_manifest,
)
from orchestrator.workflow_lisp.command_boundaries import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    build_command_boundary_environment,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_lisp_generic_union_provider_results import _Provider
from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)


PROBE = """import json, os, sys
from pathlib import Path
name = sys.argv[1]
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(name + "\\n")
if Path(__file__).with_name(name + ".broken").exists():
    sys.exit(3)
payload = {"variant": "FAST", "note": {"note": name}} if name == "route" else {"note": name + "+"}
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(payload), encoding="utf-8")
"""

PRELUDE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Note (note String))
  (defproc step ((name String)) -> Note
    :effects ((uses-command probe))
    (command-result probe :argv ("python" "PROBE" name) :returns Note))
"""

SEQUENCE = PRELUDE + """  (defworkflow run () -> Note
    (let* ((a (step "prepare"))
           (b (step "check")))
      (step "finish"))))
"""

LOOP = PRELUDE + """  (defworkflow run () -> Note
    (loop/recur :max 5
      :state (record Note :note "seed")
      :on-exhausted state
      (fn (state)
        (let* ((next (step state.note)))
          (if (= next.note "seed+++") (done next) (continue next)))))))
"""

MATCH = PRELUDE + """  (defunion Route (FAST (note Note)) (SLOW (note Note)))
  (defproc route () -> Route
    :effects ((uses-command probe))
    (command-result probe :argv ("python" "PROBE" "route") :returns Route))
  (defworkflow run () -> Note
    (match (route)
      ((FAST f) (step "fast"))
      ((SLOW s) (step "slow")))))
"""

CALL = PRELUDE + """  (defproc pair () -> Note
    :effects ((uses-command probe))
    :lowering private-workflow
    (let* ((x (step "one")))
      (step "two")))
  (defworkflow run () -> Note
    (let* ((a (step "prepare"))
           (b (pair)))
      (step "finish"))))
"""

PROVIDER = PRELUDE + """  (defproc ask () -> Note
    :effects ((uses-provider providers.seed))
    (provider-result providers.seed :prompt prompts.seed :inputs () :returns Note))
  (defworkflow run () -> Note
    (let* ((a (ask)))
      (step "finish"))))
"""


class _Interruption(BaseException):
    """The process stops during an effect: it started, its completion is unknown."""


class _FailingProvider(_Provider):
    def execute(self, invocation, **_kwargs):
        self.calls += 1
        return SimpleNamespace(
            exit_code=1, stdout=b"", stderr=b"", duration_ms=1, error=None, missing_placeholders=None,
            invalid_prompt_placeholder=False, raw_stdout=None, normalized_stdout=None, provider_session=None,
        )


class _InterruptedProvider(_Provider):
    def execute(self, invocation, **_kwargs):
        self.calls += 1
        raise _Interruption


def _install(root: Path, source: str, *, target: str = "2.33", broken: tuple[str, ...] = ()) -> dict[str, Path]:
    probe = _write_probe(root, "probe", PROBE)
    _write_sources(root, {"grt/entry.orc": source.replace("TARGET", target).replace("PROBE", probe.as_posix())})
    for name in broken:
        probe.with_name(f"{name}.broken").write_text("", encoding="utf-8")
    files = _public_run_files(root, {"probe": probe})
    files["providers"].write_text(json.dumps({"providers.seed": "codex"}), encoding="utf-8")
    files["prompts"].write_text(json.dumps({"prompts.seed": "seed.md"}), encoding="utf-8")
    (root / "grt" / "seed.md").write_text("Answer.\n", encoding="utf-8")
    return {**files, "probe": probe}


def _repair(files: dict[str, Path], name: str) -> None:
    files["probe"].with_name(f"{name}.broken").unlink()


def _mark_probe_must_not_repeat(files: dict[str, Path]) -> None:
    commands = json.loads(files["commands"].read_text(encoding="utf-8"))
    commands["probe"]["must_not_repeat"] = True
    files["commands"].write_text(json.dumps(commands), encoding="utf-8")


def _resume_diagnostics(state: dict) -> list[dict]:
    return state.get("resume_diagnostics", [])


def _all_resume_diagnostics(state: dict) -> list[dict]:
    diagnostics = list(_resume_diagnostics(state))
    for frame in state.get("call_frames", {}).values():
        child = frame.get("state") if isinstance(frame, dict) else None
        if isinstance(child, dict):
            diagnostics.extend(_all_resume_diagnostics(child))
    return diagnostics


@pytest.mark.parametrize("kind", ["external_tool", "certified_adapter"])
@pytest.mark.parametrize("value", [1, "false", None])
def test_command_boundary_must_not_repeat_requires_an_exact_boolean(
    tmp_path: Path, kind: str, value: object
) -> None:
    with pytest.raises(LispFrontendCompileError):
        _parse_command_boundaries_manifest(
            {
                "probe": {
                    "kind": kind,
                    "stable_command": ["python", "probe.py"],
                    "must_not_repeat": value,
                }
            },
            manifest_path=tmp_path / "commands.json",
        )


def test_default_command_boundary_serialization_omits_repeat_policy() -> None:
    binding = ExternalToolBinding(name="probe", stable_command=("python", "probe.py"))
    assert "must_not_repeat" not in _json_data(binding)


@pytest.mark.parametrize("kind", ["external_tool", "certified_adapter"])
def test_programmatic_command_boundary_must_not_repeat_requires_boolean(kind: str) -> None:
    if kind == "external_tool":
        binding = ExternalToolBinding(
            name="probe",
            stable_command=("python", "probe.py"),
            must_not_repeat=1,
        )
    else:
        binding = CertifiedAdapterBinding(
            name="probe",
            stable_command=("python", "probe.py"),
            input_contract={},
            output_type_name="",
            effects=(),
            path_safety={},
            source_map_behavior="",
            fixture_ids=(),
            negative_fixture_ids=(),
            must_not_repeat=1,
        )
    with pytest.raises(LispFrontendCompileError):
        build_command_boundary_environment({"probe": binding})


def _with_provider(provider: _Provider | None) -> ExitStack:
    stack = ExitStack()
    if provider is not None:
        stack.enter_context(patch.object(ProviderExecutor, "prepare_invocation", provider.prepare_invocation))
        stack.enter_context(patch.object(ProviderExecutor, "execute", provider.execute))
    return stack


def _run(files: dict[str, Path], provider: _Provider | None = None) -> int:
    with _with_provider(provider):
        return _public_run(files).exit_code


def _resume(root: Path, provider: _Provider | None = None) -> tuple[int, dict]:
    run_id = next((root / ".orchestrate" / "runs").iterdir()).name
    with _with_provider(provider):
        exit_code = resume_workflow(run_id=run_id, retry_delay_ms=0)
    state = json.loads((root / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8"))
    return exit_code, state


def _interrupt_command(name: str):
    """Stop the process once the command for `name` has run, before its result is recorded."""

    original = StepExecutor.execute_command

    def interrupted(self, step_name, command, *args, **kwargs):
        result = original(self, step_name, command, *args, **kwargs)
        if name in command:
            raise _Interruption
        return result

    return patch.object(StepExecutor, "execute_command", interrupted)


def _outcome(exit_code: int, state: dict, files: dict[str, Path]) -> tuple:
    return exit_code, state["status"], dict(state.get("workflow_outputs") or {}), _log(files["probe"])


@pytest.mark.parametrize("target", ["2.14", "2.33"])
@pytest.mark.parametrize(
    ("failed", "before", "after"),
    [
        ("check", ["prepare", "check"], ["prepare", "check", "check", "finish"]),
        ("prepare", ["prepare"], ["prepare", "prepare", "check", "finish"]),
    ],
    ids=["nonfirst", "first"],
)
def test_resume_runs_again_the_command_that_exited_with_a_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    failed: str,
    before: list[str],
    after: list[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, SEQUENCE, target=target, broken=(failed,))
    assert (_run(files), _log(files["probe"])) == (1, before)
    _repair(files, failed)

    exit_code, state = _resume(tmp_path)

    assert _outcome(exit_code, state, files) == (
        0, "completed", {"return__note": "finish+"}, after,
    )
    assert [row["diagnostic"] for row in _resume_diagnostics(state)] == ["workflow_effect_rerun"]


def test_resume_runs_again_the_failed_command_of_the_current_loop_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, LOOP, broken=("seed+",))
    assert (_run(files), _log(files["probe"])) == (1, ["seed", "seed+"])
    _repair(files, "seed+")

    exit_code, state = _resume(tmp_path)

    assert _outcome(exit_code, state, files) == (
        0, "completed", {"return__note": "seed+++"}, ["seed", "seed+", "seed+", "seed++"],
    )
    assert [row["diagnostic"] for row in _all_resume_diagnostics(state)] == ["workflow_effect_rerun"]


def test_resume_runs_again_the_failed_command_of_the_selected_match_arm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, MATCH, broken=("fast",))
    assert (_run(files), _log(files["probe"])) == (1, ["route", "fast"])
    _repair(files, "fast")

    exit_code, state = _resume(tmp_path)

    assert _outcome(exit_code, state, files) == (
        0, "completed", {"return__note": "fast+"}, ["route", "fast", "fast"],
    )
    assert [row["diagnostic"] for row in _resume_diagnostics(state)] == ["workflow_effect_rerun"]


def test_resume_runs_again_an_interrupted_command_after_a_committed_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, SEQUENCE)
    with _interrupt_command("check"), pytest.raises(_Interruption):
        _run(files)
    assert _log(files["probe"]) == ["prepare", "check"]

    exit_code, state = _resume(tmp_path)

    assert _outcome(exit_code, state, files) == (
        0, "completed", {"return__note": "finish+"}, ["prepare", "check", "check", "finish"],
    )
    assert [row["diagnostic"] for row in _resume_diagnostics(state)] == ["workflow_effect_rerun"]


def test_resume_runs_again_an_interrupted_first_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, SEQUENCE)
    with _interrupt_command("prepare"), pytest.raises(_Interruption):
        _run(files)
    assert _log(files["probe"]) == ["prepare"]

    exit_code, state = _resume(tmp_path)

    assert _outcome(exit_code, state, files) == (
        0, "completed", {"return__note": "finish+"}, ["prepare", "prepare", "check", "finish"],
    )
    assert [row["diagnostic"] for row in _resume_diagnostics(state)] == ["workflow_effect_rerun"]


@pytest.mark.parametrize("interrupted", [False, True], ids=["failed", "interrupted"])
def test_nonrepeatable_command_fails_closed_with_source_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, SEQUENCE, broken=() if interrupted else ("check",))
    _mark_probe_must_not_repeat(files)
    if interrupted:
        with _interrupt_command("check"), pytest.raises(_Interruption):
            _run(files)
    else:
        assert _run(files) == 1
        _repair(files, "check")
    assert _log(files["probe"]) == ["prepare", "check"]

    exit_code, state = _resume(tmp_path)

    assert exit_code == 1
    assert state["status"] == "failed"
    error_context = state["error"]["context"]
    assert "lexical_restore_pending_effect_unsafe" in error_context["diagnostics"]
    location = error_context["source_location"]
    assert location["path"] == "entry.orc"
    assert location["line"] == SEQUENCE.splitlines().index(
        '    (command-result probe :argv ("python" "PROBE" name) :returns Note))'
    ) + 1
    assert location["column"] > 0
    if interrupted:
        assert state["current_step"]["step_id"] == location["step_id"]
        assert state["current_step"]["status"] == "failed"
    else:
        failed_rows = [
            row
            for row in state["steps"].values()
            if isinstance(row, dict)
            and row.get("step_id") == location["step_id"]
            and row.get("status") == "failed"
        ]
        assert len(failed_rows) == 1
    assert _log(files["probe"]) == ["prepare", "check"]
    assert _resume_diagnostics(state) == []


def _interrupted_reruns(caplog: pytest.LogCaptureFixture) -> int:
    return sum(record.getMessage() == "provider_attempt_interrupted_rerun" for record in caplog.records)


def test_resume_runs_again_a_provider_call_that_exited_with_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed provider visit is not an interrupted one: no interrupted-rerun diagnostic."""

    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, PROVIDER)
    failing = _FailingProvider({"note": "unused"})
    assert (_run(files, failing), failing.calls, _log(files["probe"])) == (1, 1, [])
    answering = _Provider({"note": "asked"})

    with caplog.at_level(logging.INFO):
        exit_code, state = _resume(tmp_path, answering)

    assert (*_outcome(exit_code, state, files), answering.calls, _interrupted_reruns(caplog)) == (
        0, "completed", {"return__note": "finish+"}, ["finish"], 1, 0,
    )
    assert [row["diagnostic"] for row in _resume_diagnostics(state)] == ["workflow_effect_rerun"]


def test_each_interrupted_command_rerun_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interruption during a rerun is at-least-once on the next resume."""

    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, SEQUENCE, broken=("check",))
    assert _run(files) == 1
    _repair(files, "check")
    with _interrupt_command("check"), pytest.raises(_Interruption):
        _resume(tmp_path)
    assert _log(files["probe"]) == ["prepare", "check", "check"]

    exit_code, state = _resume(tmp_path)

    assert _outcome(exit_code, state, files) == (
        0, "completed", {"return__note": "finish+"}, ["prepare", "check", "check", "check", "finish"],
    )
    assert [row["diagnostic"] for row in _resume_diagnostics(state)] == [
        "workflow_effect_rerun",
        "workflow_effect_rerun",
    ]


def test_resume_descends_into_a_failed_workflow_call_and_reuses_committed_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The call frame reuses `one`'s result and reruns only failed `two`."""

    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, CALL, broken=("two",))
    assert (_run(files), _log(files["probe"])) == (1, ["prepare", "one", "two"])
    _repair(files, "two")

    exit_code, state = _resume(tmp_path)

    assert _outcome(exit_code, state, files) == (
        0, "completed", {"return__note": "finish+"}, ["prepare", "one", "two", "two", "finish"],
    )
    child_states = [
        frame["state"]
        for frame in state["call_frames"].values()
        if isinstance(frame, dict) and isinstance(frame.get("state"), dict)
    ]
    child_state = next(
        child
        for child in child_states
        if _resume_diagnostics(child)
    )
    assert [row["diagnostic"] for row in _resume_diagnostics(child_state)] == ["workflow_effect_rerun"]


def test_interrupted_provider_call_runs_again_once_with_the_named_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """specs/providers.md: an interrupted provider visit reruns with one `provider_attempt_interrupted_rerun`."""

    monkeypatch.chdir(tmp_path)
    files = _install(tmp_path, PROVIDER)
    interrupted = _InterruptedProvider({"note": "unused"})
    with pytest.raises(_Interruption):
        _run(files, interrupted)
    answering = _Provider({"note": "asked"})

    with caplog.at_level(logging.INFO):
        exit_code, state = _resume(tmp_path, answering)

    assert (*_outcome(exit_code, state, files), interrupted.calls, answering.calls, _interrupted_reruns(caplog)) == (
        0, "completed", {"return__note": "finish+"}, ["finish"], 1, 1, 1,
    )
    assert [row["diagnostic"] for row in _resume_diagnostics(state)] == ["provider_attempt_interrupted_rerun"]
