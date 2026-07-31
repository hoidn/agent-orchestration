from __future__ import annotations

from typing import Any

import pytest

from orchestrator._common.status import is_run_terminal, is_step_settled
from orchestrator.workflow.resume_planner import ResumePlanner


class _StringSubclass(str):
    pass


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
