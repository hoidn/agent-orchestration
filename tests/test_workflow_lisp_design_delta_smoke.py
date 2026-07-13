from __future__ import annotations

import json
from pathlib import Path

from tests.test_workflow_lisp_design_delta_drain_migration_feasibility import (
    REPO_ROOT,
    _compile_design_delta_parent_drain_entrypoint,
)


HISTORICAL_PARITY_REPORT_PATH = (
    REPO_ROOT
    / "artifacts"
    / "work"
    / "review-parity-check"
    / "design_delta_parent_drain.json"
)
FOCUSED_SMOKE_MODULE = "tests/test_workflow_lisp_design_delta_smoke.py"
FEASIBILITY_MODULE = (
    "tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py"
)
PARENT_DRAIN_EVIDENCE_ROLES = (
    "smoke_or_integration",
    "terminal_state_parity",
)


def test_design_delta_parent_drain_smoke_compiles_production_entry(
    tmp_path: Path,
) -> None:
    # Task 3.3 handoff: inline the minimal loader setup here before deleting
    # the feasibility module that temporarily owns this shared helper.
    result, lowered_by_name = _compile_design_delta_parent_drain_entrypoint(tmp_path)

    assert not result.diagnostics
    assert result.entry_result.lowering_schema_version == 2
    assert "lisp_frontend_design_delta/drain::drain" in (
        result.entry_result.validated_bundles
    )
    assert "lisp_frontend_design_delta/drain::drain" in lowered_by_name


def test_design_delta_parent_drain_historical_parity_records_focused_smoke() -> None:
    report = json.loads(HISTORICAL_PARITY_REPORT_PATH.read_text(encoding="utf-8"))
    expected_command = [
        "python",
        "-m",
        "pytest",
        FOCUSED_SMOKE_MODULE,
        "-q",
    ]

    for role in PARENT_DRAIN_EVIDENCE_ROLES:
        evidence = report["evidence"][role]
        command = evidence["argv"]
        assert command == expected_command
        assert evidence["exit_code"] == 0
        assert evidence["status"] == "pass"
        assert FEASIBILITY_MODULE not in command
