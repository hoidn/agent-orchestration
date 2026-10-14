from __future__ import annotations

from typing import Any

import pytest

from orchestrator._common.status import is_run_terminal, is_step_settled


class _StringSubclass(str):
    pass


class _UnhashableString(str):
    __hash__ = None


@pytest.mark.parametrize(('status', 'run_terminal', 'step_settled'), (('completed', True, True), ('failed', True, True), ('skipped', False, True), ('running', False, False), ('suspended', False, False), ('pending', False, False), ('unknown', False, False), ('', False, False), (_StringSubclass('completed'), True, True), (_UnhashableString('completed'), True, True), (None, False, False), (True, False, False), (0, False, False)))
def test_status_predicates_golden_matrix(status: Any, run_terminal: bool, step_settled: bool) -> None:
    assert is_run_terminal(status) is run_terminal
    assert is_step_settled(status) is step_settled


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
