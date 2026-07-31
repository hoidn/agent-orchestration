from __future__ import annotations

from typing import Any

import pytest

from orchestrator._common.status import is_run_terminal, is_step_settled
from orchestrator.workflow.loops import LoopExecutor
from orchestrator.workflow.resume_planner import ResumePlanner
from orchestrator.workflow.state_projection import IterationStepKeyProjection


class _StringSubclass(str):
    pass


class _UnhashableString(str):
    __hash__ = None


@pytest.mark.parametrize(
    (
        "status",
        "run_terminal",
        "step_settled",
        "resume_entry_terminal",
    ),
    (
        ("completed", True, True, True),
        ("failed", True, True, False),
        ("skipped", False, True, True),
        ("running", False, False, False),
        ("suspended", False, False, False),
        ("pending", False, False, False),
        ("unknown", False, False, False),
        ("", False, False, False),
        (_StringSubclass("completed"), True, True, True),
        (_UnhashableString("completed"), True, True, True),
        (None, False, False, False),
        (True, False, False, False),
        (0, False, False, False),
    ),
)
def test_status_predicates_and_resume_owner_golden_matrix(
    status: Any,
    run_terminal: bool,
    step_settled: bool,
    resume_entry_terminal: bool,
) -> None:
    assert is_run_terminal(status) is run_terminal
    assert is_step_settled(status) is step_settled
    assert (
        ResumePlanner().entry_is_terminal({"status": status})
        is resume_entry_terminal
    )


def test_resume_recursive_ownership_remains_distinct_from_step_settlement() -> None:
    planner = ResumePlanner()
    nested = [
        {"status": "completed"},
        {"inner": {"status": "skipped"}},
    ]

    assert planner.entry_is_terminal(nested) is True
    assert planner.entry_is_terminal(
        [*nested, {"status": "failed"}]
    ) is False
    assert is_step_settled("failed") is True
    assert is_step_settled("suspended") is False


@pytest.mark.parametrize("status", ([], {}))
def test_common_status_predicates_return_false_for_unhashable_values(
    status: object,
) -> None:
    assert is_run_terminal(status) is False
    assert is_step_settled(status) is False


@pytest.mark.parametrize("status", ([], {}))
def test_common_status_predicates_can_preserve_set_membership_errors(
    status: object,
) -> None:
    with pytest.raises(TypeError, match="unhashable type"):
        is_run_terminal(status, raise_on_unhashable=True)
    with pytest.raises(TypeError, match="unhashable type"):
        is_step_settled(status, raise_on_unhashable=True)


def test_common_status_strict_mode_rejects_an_unhashable_string_subclass() -> None:
    status = _UnhashableString("completed")

    with pytest.raises(TypeError, match="unhashable type"):
        is_run_terminal(status, raise_on_unhashable=True)
    with pytest.raises(TypeError, match="unhashable type"):
        is_step_settled(status, raise_on_unhashable=True)


@pytest.mark.parametrize("typed", (False, True))
@pytest.mark.parametrize("status", ([], {}))
def test_loop_resume_treats_unhashable_nested_status_as_unsettled(
    status: object,
    typed: bool,
) -> None:
    loop_executor = LoopExecutor.__new__(LoopExecutor)
    state = {
        "steps": {
            "Loop": [{}],
            "Loop[0].Nested": {"status": status},
        }
    }

    if typed:
        loop_results, completed_indices, start_index = (
            loop_executor.typed_resume_for_each_state(
                state,
                "Loop",
                ("node",),
                IterationStepKeyProjection(
                    node_id="loop",
                    frame_key="Loop",
                    nested_presentation_keys={"node": "Nested"},
                ),
                ["item"],
            )
        )
    else:
        loop_results, completed_indices, start_index = (
            loop_executor.resume_for_each_state(
                state,
                "Loop",
                [{"name": "Nested"}],
                ["item"],
            )
        )

    assert loop_results == [{}]
    assert completed_indices == []
    assert start_index == 0


@pytest.mark.parametrize("typed", (False, True))
def test_loop_resume_accepts_an_unhashable_completed_string_subclass(
    typed: bool,
) -> None:
    loop_executor = LoopExecutor.__new__(LoopExecutor)
    state = {
        "steps": {
            "Loop": [{}],
            "Loop[0].Nested": {"status": _UnhashableString("completed")},
        }
    }

    if typed:
        _, completed_indices, start_index = loop_executor.typed_resume_for_each_state(
            state,
            "Loop",
            ("node",),
            IterationStepKeyProjection(
                node_id="loop",
                frame_key="Loop",
                nested_presentation_keys={"node": "Nested"},
            ),
            ["item"],
        )
    else:
        _, completed_indices, start_index = loop_executor.resume_for_each_state(
            state,
            "Loop",
            [{"name": "Nested"}],
            ["item"],
        )

    assert completed_indices == [0]
    assert start_index == 1
