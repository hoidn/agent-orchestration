"""Spike of evaluated execution: the effect memo and resume.

Throwaway (Task 9 of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md).
Contract: docs/design/workflow_lisp_evaluated_execution.md sections 7 and 8, the table
of evaluation and resume and the table of crash windows.

A run is stopped by raising from the evaluator's hook at a named moment of an
attempt. Resume is the same evaluation again, on the same run root. The probe's
log counts every command invocation.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from experiments.evaluated_execution_spike.evaluator import EffectSuspended, EvaluationFailed
from experiments.evaluated_execution_spike.memo import Memo, MemoBusy, answer, read_records
from experiments.evaluated_execution_spike.performers import result_path
from tests.experiments.test_evaluated_execution_spike import (
    KNOWN_DEFECTS,
    PROGRAMS,
    RULES,
    SKIPPED,
    _cell,
    _refused_by_typecheck,
    build,
    calls,
    cells,
    fixture,
    install,
    records,
    run_root,
    spike,
    stand_in_provider,
)
from tests.experiments.test_evaluated_execution_spike_programs import (
    REAL,
    _spike_real,
    launches,
    run_controller,
    scripted_providers,
)
from tests.workflow_lisp_totality_matrix_sources import PROBE


class Interrupt(BaseException):
    """The process stops here."""


def stop_at(event: str, occurrence: int = 1):
    seen: list[str] = []

    def hook(name: str, identity: str) -> None:
        if name == event:
            seen.append(identity)
            if len(seen) == occurrence:
                raise Interrupt(identity)

    return hook


def interrupted(root: Path, sources, closed, *, inputs=None, hook=None) -> None:
    install(root, sources)
    with pytest.raises(Interrupt):
        spike(root, sources, inputs=inputs, closed=closed, hook=hook)


def attempts(root: Path, identity: str, kind: str = "started") -> list[int]:
    return [r["attempt"] for r in records(root, kind) if r["identity"] == identity]


def _resumable() -> list:
    matrix_cells = [
        pytest.param(*_cell(*cell)[:2], id="/".join(cell))
        for cell in cells()
        if cell not in SKIPPED and cell not in RULES and not _refused_by_typecheck(cell) and _cell(*cell)[3]
    ]
    return [*matrix_cells, *(pytest.param(case[0], case[1], id=name) for name, case in PROGRAMS.items() if case[3])]


@pytest.mark.parametrize(("sources", "inputs"), _resumable())
def test_stopping_after_each_committed_effect_and_resuming_gives_the_uninterrupted_run(
    tmp_path: Path, sources, inputs
) -> None:
    closed, once = spike(tmp_path / "once", sources, inputs=inputs)
    committed = [r["identity"] for r in records(tmp_path / "once")]
    invocations = Counter(calls(tmp_path / "once"))

    for k in range(1, len(committed) + 1):
        root = tmp_path / f"stop-{k}"
        interrupted(root, sources, closed, inputs=inputs, hook=stop_at("committed", k))
        assert len(calls(root)) == k
        _, resumed = spike(root, sources, inputs=inputs, closed=closed)

        assert (resumed.value, Counter(calls(root)), [r["identity"] for r in records(root)]) == (
            once.value, invocations, committed
        ), f"stopped after effect {k}"


def test_evaluating_a_completed_run_again_launches_nothing_and_reaches_the_same_effects_in_order(tmp_path: Path) -> None:
    sources, inputs, *_ = PROGRAMS["if-in-hook"]
    closed, first = spike(tmp_path, sources, inputs=inputs)
    launched = calls(tmp_path)

    _, again = spike(tmp_path, sources, inputs=inputs, closed=closed)

    assert (again.value, again.trace, calls(tmp_path)) == (first.value, first.trace, launched)
    assert len(first.trace) == 7


# The table of crash windows: where the process stops, then, for the stopped command,
# whether it was launched before the stop, how many more times it runs on resume, and
# the attempts its identity has after resume.
WINDOWS = {
    "before started is written": ("resolved", 0, 0, [1]),
    "while the effect runs": ("started", 0, 0, [1, 2]),
    "after the result file, before committed": ("finished", 1, 1, [1, 2]),
    "after committed": ("committed", 1, 0, [1]),
}


@pytest.mark.parametrize("window", list(WINDOWS))
@pytest.mark.parametrize("name", ["loop-in-branch", "if-in-hook"])
def test_each_crash_window_at_each_effect_resumes_as_the_design_states(tmp_path: Path, window: str, name: str) -> None:
    sources, inputs, *_ = PROGRAMS[name]
    event, launched, extra, expected_attempts = WINDOWS[window]
    closed, once = spike(tmp_path / "once", sources, inputs=inputs)
    committed = [r["identity"] for r in records(tmp_path / "once")]
    total = len(calls(tmp_path / "once"))

    for k, identity in enumerate(committed, start=1):
        root = tmp_path / f"stop-{k}"
        interrupted(root, sources, closed, inputs=inputs, hook=stop_at(event, k))
        before = len(calls(root))
        _, resumed = spike(root, sources, inputs=inputs, closed=closed)
        reruns = [d["identity"] for d in resumed.diagnostics if d["code"] == "effect_rerun"]

        assert (before, len(calls(root))) == (k - 1 + launched, total + extra), f"effect {k}"
        assert (resumed.value, attempts(root, identity), attempts(root, identity, "committed")) == (
            once.value, expected_attempts, expected_attempts[-1:]
        ), f"effect {k}"
        assert reruns == ([identity] if len(expected_attempts) > 1 else []), f"effect {k}"


def test_a_complete_valid_result_file_of_an_uncommitted_attempt_is_never_the_result(tmp_path: Path) -> None:
    sources, inputs, *_ = PROGRAMS["loop-in-branch"]
    closed, once = spike(tmp_path / "once", sources, inputs=inputs)
    root = tmp_path / "stopped"
    interrupted(root, sources, closed, inputs=inputs, hook=stop_at("finished", 2))
    identity = [r["identity"] for r in records(root, "started")][-1]
    left = result_path(run_root(root), identity, 1)
    assert json.loads(left.read_text(encoding="utf-8")) == {"n": 2}
    left.write_text(json.dumps({"n": 99}), encoding="utf-8")  # complete, valid, and not what the command returns

    _, resumed = spike(root, sources, inputs=inputs, closed=closed)

    committed = next(r for r in records(root) if r["identity"] == identity)
    assert (resumed.value, committed["attempt"], committed["value"]) == (once.value, 2, {"n": 2})
    assert json.loads(left.read_text(encoding="utf-8")) == {"n": 99}  # the evidence of attempt 1 stays
    assert result_path(run_root(root), identity, 2).exists()


def test_a_partial_result_file_left_while_the_effect_ran_is_never_the_result(tmp_path: Path) -> None:
    sources, inputs, *_ = PROGRAMS["loop-in-branch"]
    closed, once = spike(tmp_path / "once", sources, inputs=inputs)
    root = tmp_path / "stopped"
    interrupted(root, sources, closed, inputs=inputs, hook=stop_at("started", 1))
    identity = records(root, "started")[0]["identity"]
    partial = result_path(run_root(root), identity, 1)
    partial.parent.mkdir(parents=True)
    partial.write_text('{"n": ', encoding="utf-8")

    _, resumed = spike(root, sources, inputs=inputs, closed=closed)

    assert (resumed.value, attempts(root, identity, "committed")) == (once.value, [2])


def test_a_record_torn_by_the_crash_is_dropped_and_the_run_resumes(tmp_path: Path) -> None:
    sources, inputs, *_ = PROGRAMS["loop-in-branch"]
    closed, once = spike(tmp_path / "once", sources, inputs=inputs)
    root = tmp_path / "stopped"
    interrupted(root, sources, closed, inputs=inputs, hook=stop_at("finished", 1))
    with open(run_root(root) / "memo.jsonl", "ab") as memo:
        memo.write(b'{"record":"committed","identity":"spk/lo')

    _, resumed = spike(root, sources, inputs=inputs, closed=closed)

    assert resumed.value == once.value
    assert all(line for line in (run_root(root) / "memo.jsonl").read_text(encoding="utf-8").splitlines())
    assert len(read_records(run_root(root))) == len((run_root(root) / "memo.jsonl").read_text().splitlines())


def test_an_effect_that_must_not_repeat_stops_resume_when_it_started_without_a_commit(tmp_path: Path) -> None:
    sources, inputs, *_ = PROGRAMS["loop-in-branch"]
    closed = build(tmp_path, sources, no_repeat=frozenset({"fetch"}))
    interrupted(tmp_path, sources, closed, inputs=inputs, hook=stop_at("started", 2))

    with pytest.raises(EvaluationFailed) as refused:
        spike(tmp_path, sources, inputs=inputs, closed=closed)

    assert (refused.value.code, refused.value.detail, calls(tmp_path)) == (
        "lexical_restore_pending_effect_unsafe", {"attempts": [1]}, ["fetch 1"]
    )


def test_a_failed_attempt_runs_again_on_resume(tmp_path: Path) -> None:
    sources, inputs, *_ = PROGRAMS["loop-in-branch"]
    closed = build(tmp_path, sources)
    (tmp_path / "probe.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    with pytest.raises(EvaluationFailed) as failed:
        spike(tmp_path, sources, inputs=inputs, closed=closed)
    (tmp_path / "probe.py").write_text(PROBE, encoding="utf-8")

    _, resumed = spike(tmp_path, sources, inputs=inputs, closed=closed)

    first = records(tmp_path, "failed")[0]["identity"]
    assert (failed.value.code, resumed.value, attempts(tmp_path, first)) == ("command_failed", {"n": 3}, [1, 2])


def test_a_committed_effect_whose_resolved_input_changed_stops_resume_and_names_the_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prompt file is part of a provider effect's resolved input; the program and the inputs are unchanged."""

    stand_in_provider(monkeypatch, {"variant": "REVISE", "feedback": {"notes": "again"}})
    sources = fixture("provider_review")
    closed = build(tmp_path, sources)
    interrupted(tmp_path, sources, closed, inputs={"draft": "d1"}, hook=stop_at("committed", 1))
    (tmp_path / "spk" / "review.md").write_text("Review the draft again.\n", encoding="utf-8")

    with pytest.raises(EvaluationFailed) as diverged:
        spike(tmp_path, sources, inputs={"draft": "d1"}, closed=closed)

    assert (diverged.value.code, diverged.value.detail["differs"], diverged.value.detail["files"]) == (
        "effect_input_diverged", ["declared"], ["spk/review.md"]
    )
    assert diverged.value.detail["recorded"] != diverged.value.detail["resolved"]


def test_resume_with_other_inputs_or_another_program_is_refused_before_any_effect(tmp_path: Path) -> None:
    sources, inputs, *_ = PROGRAMS["loop-in-branch"]
    closed = build(tmp_path, sources)
    interrupted(tmp_path, sources, closed, inputs=inputs, hook=stop_at("committed", 1))
    edited = {path: text.replace("(< b.n 3)", "(< b.n 4)") for path, text in sources.items()}
    spaced = {path: text.replace("\n  (def", "\n\n  (def") for path, text in sources.items()}

    with pytest.raises(EvaluationFailed) as other_inputs:
        spike(tmp_path, sources, inputs={"go": False}, closed=closed)
    with pytest.raises(EvaluationFailed) as other_program:
        spike(tmp_path, edited, inputs=inputs)
    _, resumed = spike(tmp_path, spaced, inputs=inputs)

    assert (other_inputs.value.code, other_program.value.code) == ("resume_inputs_changed", "resume_program_changed")
    assert (resumed.value, calls(tmp_path)) == ({"n": 3}, ["fetch 1", "fetch 2", "fetch 3"])


def test_a_request_for_input_suspends_until_answered_and_nothing_runs_twice(tmp_path: Path) -> None:
    sources = fixture("ask")
    closed = build(tmp_path, sources)

    with pytest.raises(EffectSuspended) as first:
        spike(tmp_path, sources, closed=closed)
    with pytest.raises(EffectSuspended) as again:
        spike(tmp_path, sources, closed=closed)
    answer(run_root(tmp_path), first.value.identity, "yes")
    _, resumed = spike(tmp_path, sources, closed=closed)

    assert (first.value.identity, first.value.request, again.value.identity) == ("spk/ask::run / reply", "Go on?", first.value.identity)
    assert (resumed.value, calls(tmp_path)) == ({"n": 2}, ["fetch 1", "fetch 2"])


def test_the_memo_has_one_writer(tmp_path: Path) -> None:
    with Memo(tmp_path):
        with pytest.raises(MemoBusy):
            with Memo(tmp_path):
                pass


def test_the_compact_search_controller_resumed_after_each_effect_runs_no_committed_effect_twice(tmp_path: Path) -> None:
    closed, once = run_controller(tmp_path / "once", 12)
    committed = [r["identity"] for r in records(tmp_path / "once")]
    assert len(committed) == 18

    for k in range(1, len(committed) + 1):
        root = tmp_path / f"stop-{k}"
        with pytest.raises(Interrupt):
            run_controller(root, 12, closed=closed, hook=stop_at("committed", k))
        _, resumed = run_controller(root, 12, closed=closed)
        launches = Counter(r["identity"] for r in records(root, "started"))

        assert (resumed.value, [r["identity"] for r in records(root)]) == (once.value, committed), f"effect {k}"
        assert set(launches.values()) == {1}, f"effect {k}"


@pytest.mark.parametrize("name", list(REAL))
def test_a_real_program_resumed_after_each_effect_calls_no_provider_or_command_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    scripted = scripted_providers(monkeypatch, name)
    once = (_spike_real(tmp_path / "once", name, monkeypatch), scripted.calls, launches(tmp_path / "once"))
    committed = [r["identity"] for r in records(tmp_path / "once")]

    for k in range(1, len(committed) + 1):
        root = tmp_path / f"stop-{k}"
        scripted = scripted_providers(monkeypatch, name)
        with pytest.raises(Interrupt):
            _spike_real(root, name, monkeypatch, hook=stop_at("committed", k))
        resumed = _spike_real(root, name, monkeypatch)

        assert (resumed, scripted.calls, launches(root)) == once, f"effect {k}"
        assert [r["identity"] for r in records(root)] == committed, f"effect {k}"
