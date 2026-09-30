"""Spike of evaluated execution, iteration 2, items A and C: hidden inputs of an effect, and input defaults.

Throwaway. Review finding 1 (Critical): a run stopped after its first commit, the
command's script changed, and the resume returned 206, a value no uninterrupted run
gives (306 with the new script, 6 with the old). Review finding 4: declared defaults
were not bound.

The resolved input of a command now carries the digest of every file its boundary
names in its stable command; that of a provider, its prompt asset and its prompt
dependencies. A committed effect whose resolved input changed stops the resume with
`effect_input_diverged` before any other effect is launched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.evaluated_execution_spike.evaluator import EvaluationFailed
from experiments.mlevolve_pair.search import run_search
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.workflow.outcomes import OutcomeRecorder
from tests.experiments.test_evaluated_execution_spike import (
    build,
    calls,
    fixture,
    install,
    records,
    spike,
    stand_in_provider,
)
from tests.experiments.test_evaluated_execution_spike_programs import CONTROLLER, compact_controller, run_controller
from tests.experiments.test_evaluated_execution_spike_resume import Interrupt, interrupted, stop_at
from tests.test_workflow_lisp_generic_unions_runtime import _public_run, _public_run_files
from tests.workflow_lisp_totality_matrix_sources import COMMANDS, PROBE

NEW_PROBE = PROBE.replace('"fetch": {"n": n}', '"fetch": {"n": n+100}')


def _flat_run_changed_between_run_and_resume(root: Path, monkeypatch: pytest.MonkeyPatch, *, change: bool):
    """The reviewer's experiment on the flat route, through the public run and resume entries."""

    entry = install(root, fixture("three_call_sites"))
    files = {**_public_run_files(root, {name: Path("probe.py") for name in COMMANDS}), "source": entry}
    monkeypatch.chdir(root)
    original = OutcomeRecorder.persist_step_result

    def stop_after_the_first_command(self, state, step_name, *args, **kwargs):
        result = original(self, state, step_name, *args, **kwargs)
        raise Interrupt(step_name)

    with monkeypatch.context() as stopping:
        stopping.setattr(OutcomeRecorder, "persist_step_result", stop_after_the_first_command)
        with pytest.raises(Interrupt):
            _public_run(files)
    if change:
        (root / "probe.py").write_text(NEW_PROBE, encoding="utf-8")
    run_id = next((root / ".orchestrate" / "runs").iterdir()).name
    assert resume_workflow(run_id=run_id, retry_delay_ms=0) == 0
    state = json.loads((root / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8"))
    return dict(state["workflow_outputs"]), calls(root)


def test_the_flat_route_also_resumes_a_run_whose_command_changed_to_a_value_no_run_gives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Measured, not repaired: the present route returns 206 too; 6 unchanged, 306 with the new script."""

    changed = _flat_run_changed_between_run_and_resume(tmp_path / "changed", monkeypatch, change=True)
    unchanged = _flat_run_changed_between_run_and_resume(tmp_path / "unchanged", monkeypatch, change=False)

    assert changed == ({"return__n": 206}, ["fetch 1", "fetch 2", "fetch 3"])
    assert unchanged == ({"return__n": 6}, ["fetch 1", "fetch 2", "fetch 3"])


def test_a_committed_command_whose_program_file_changed_stops_the_resume_before_any_launch(tmp_path: Path) -> None:
    sources = fixture("three_call_sites")
    closed = build(tmp_path, sources)
    interrupted(tmp_path, sources, closed, hook=stop_at("committed", 1))
    (tmp_path / "probe.py").write_text(NEW_PROBE, encoding="utf-8")

    with pytest.raises(EvaluationFailed) as diverged:
        spike(tmp_path, sources, closed=closed)

    first = records(tmp_path)[0]
    assert (diverged.value.code, diverged.value.detail["differs"], diverged.value.detail["files"]) == (
        "effect_input_diverged", ["declared"], ["probe.py"]
    )
    assert diverged.value.at["span"].endswith("three_call_sites.orc:10:5")  # the `command-result` of `fetch`
    assert (calls(tmp_path), len(records(tmp_path, "started")), first["identity"]) == (
        ["fetch 1"], 1, "spk/three_call_sites::run / a=spk/three_call_sites::fetch / #1"
    )


def test_an_effect_without_a_commit_runs_the_program_that_is_there_when_it_starts(tmp_path: Path) -> None:
    """The rule the refusal leaves: only a committed result binds its program file."""

    sources = fixture("three_call_sites")
    closed = build(tmp_path, sources)
    interrupted(tmp_path, sources, closed, hook=stop_at("started", 1))
    (tmp_path / "probe.py").write_text(NEW_PROBE, encoding="utf-8")

    _, resumed = spike(tmp_path, sources, closed=closed)

    assert (resumed.value, calls(tmp_path)) == ({"n": 306}, ["fetch 1", "fetch 2", "fetch 3"])


def test_the_program_file_of_a_certified_adapter_is_bound_too(tmp_path: Path) -> None:
    closed, _ = run_controller(tmp_path / "once", 2)
    root = tmp_path / "stopped"
    with pytest.raises(Interrupt):
        run_controller(root, 2, closed=closed, hook=stop_at("committed", 1))
    leaves = root / "experiments" / "mlevolve_pair" / "leaves.py"
    leaves.write_text(leaves.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")

    with pytest.raises(EvaluationFailed) as diverged:  # not `run_controller`, which copies the leaves again
        spike(root, {}, inputs={"max_evaluations": 2, "target_score": 0.0}, closed=closed)

    assert (diverged.value.code, diverged.value.detail["files"], len(records(root, "started"))) == (
        "effect_input_diverged", ["experiments/mlevolve_pair/leaves.py"], 1
    )


def test_a_prompt_dependency_is_bound_into_the_provider_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stand_in_provider(monkeypatch, {"n": 5})
    notes = tmp_path / "artifacts" / "work" / "notes.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("first notes\n", encoding="utf-8")
    sources, inputs = fixture("prompt_dependency"), {"notes": "artifacts/work/notes.md"}
    closed = build(tmp_path, sources)
    interrupted(tmp_path, sources, closed, inputs=inputs, hook=stop_at("committed", 1))
    notes.write_text("other notes\n", encoding="utf-8")

    with pytest.raises(EvaluationFailed) as diverged:
        spike(tmp_path, sources, inputs=inputs, closed=closed)

    assert (diverged.value.code, diverged.value.detail["files"], calls(tmp_path)) == (
        "effect_input_diverged", ["artifacts/work/notes.md"], []
    )


# C: defaults --------------------------------------------------------------------


def _controller(root: Path, inputs: dict, **options):
    sources, boundaries = compact_controller(root)
    return spike(root, sources, inputs=inputs, boundaries=boundaries, workflow=f"{CONTROLLER}::run-search", **options)


def test_the_compact_controller_runs_with_its_declared_defaults(tmp_path: Path) -> None:
    _, result = _controller(tmp_path, {})

    assert result.value == run_search(max_evaluations=12)


def test_a_resume_with_the_defaults_written_out_is_the_same_run(tmp_path: Path) -> None:
    """The run's input digest is taken after the defaults are bound."""

    with pytest.raises(Interrupt):
        _controller(tmp_path, {}, hook=stop_at("committed", 3))

    _, resumed = _controller(tmp_path, {"max_evaluations": 12, "target_score": 0.0})

    assert (resumed.value, len(records(tmp_path, "started"))) == (run_search(max_evaluations=12), 18)


@pytest.mark.parametrize(
    ("inputs", "code"),
    [({"go": 1}, "workflow_input_invalid"), ({"go": True, "other": 1}, "workflow_input_unknown"), ({}, "workflow_input_missing")],
    ids=["wrong-type", "undeclared", "missing"],
)
def test_inputs_are_checked_against_their_declared_types_before_the_run_starts(tmp_path: Path, inputs, code) -> None:
    with pytest.raises(EvaluationFailed) as refused:
        spike(tmp_path, fixture("loop_in_branch"), inputs=inputs)

    assert (refused.value.code, (tmp_path / ".orchestrate" / "spike" / "run" / "run.json").exists()) == (code, False)
