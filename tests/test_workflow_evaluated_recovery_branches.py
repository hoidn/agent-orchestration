"""The window product over every further branch scenario the consumer harness keeps.

std/improve blocked and exhausted, the reviewed change after a wrong approach, escalated to a
person and unresolved after three rounds, and the generic run watchdog on its no-action, codex
repair and claude repair branches. Each scenario's census fixes the identities it reaches; each
cell kills one effect's first attempt at one window and resumes it as the core cells do.
"""

from __future__ import annotations

import pytest

from tests.test_workflow_evaluated_recovery import assert_census, assert_window_resumes
from tests.workflow_evaluated_recovery_cases import BRANCH_CELLS, BRANCHES


@pytest.mark.parametrize("scenario", BRANCHES)
def test_public_branch_census_matches_reached_effects(tmp_path_factory, tmp_path, monkeypatch, scenario):
    assert_census(tmp_path_factory, tmp_path, monkeypatch, scenario)


@pytest.mark.parametrize("cell", BRANCH_CELLS, ids=lambda cell: cell.id)
def test_public_branch_effect_window_resumes(tmp_path_factory, tmp_path, monkeypatch, cell):
    assert_window_resumes(tmp_path_factory, tmp_path, monkeypatch, cell)
