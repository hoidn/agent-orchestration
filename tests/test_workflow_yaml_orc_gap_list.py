from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
GAP_LIST = REPO_ROOT / "docs" / "workflow_yaml_orc_gap_list.md"
HANDOFF = REPO_ROOT / "docs" / "plans" / "2026-07-13-procedure-first-reuse-inventory.json"
YAML_RETIREMENT_PROGRAM = REPO_ROOT / "docs" / "plans" / "2026-07-07-yaml-retirement-program.md"
ROADMAP = REPO_ROOT / "docs" / "plans" / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
CAPABILITY_MATRIX = REPO_ROOT / "docs" / "capability_status_matrix.md"
DOCS_INDEX = REPO_ROOT / "docs" / "index.md"

SCOPED_QUEUES = {
    "port_verified_iteration": {
        "disposition": "port",
        "path": "workflows/examples/verified_iteration_drain.yaml",
    },
    "port_generic_run_watchdog": {
        "disposition": "port",
        "path": "workflows/examples/generic_run_watchdog.yaml",
    },
    "hold_non_progress_step_back": {
        "disposition": "hold",
        "path": "workflows/examples/non_progress_step_back_demo.yaml",
    },
}

ALLOWED_CLASSIFICATIONS = {"implemented", "blocking_gate", "owner_waiver", "drop"}

EXPECTED_GAPS = {
    "common.public-boundary-defaults": "implemented",
    "common.runtime-provider-selection": "implemented",
    "common.provider-call-policy": "blocking_gate",
    "common.structured-results": "implemented",
    "common.prompt-dependency-parity": "blocking_gate",
    "common.command-boundary": "implemented",
    "verified.bounded-loop": "implemented",
    "verified.iteration-artifact-lineage": "blocking_gate",
    "verified.summary-pointer-helper": "drop",
    "verified.task-15-input-drift": "implemented",
    "watchdog.probe-and-publication": "implemented",
    "watchdog.conditional-repair": "implemented",
    "watchdog.port-plan-and-parity": "blocking_gate",
    "step-back.typed-routing": "implemented",
    "step-back.owner-disposition": "blocking_gate",
}

REQUIRED_MECHANIC_TOKENS = {
    "default",
    "provider",
    "provider_params",
    "timeout_sec",
    "expected_outputs",
    "output_bundle",
    "depends_on",
    "inject",
    "repeat_until",
    "on_exhausted",
    "loop.index",
    "PublishSummaryPath",
    "when",
    "match",
    "set_scalar",
}


def _table_after_heading(text: str, heading: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    start = lines.index(heading)
    table_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            table_lines.append(line)
    assert len(table_lines) >= 3, f"missing Markdown table after {heading}"
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip().replace("`", "") for cell in line.strip("|").split("|")]
        assert len(cells) == len(headers), line
        rows.append(dict(zip(headers, cells, strict=True)))
    return rows


def _handoff_queues() -> dict[str, dict[str, object]]:
    payload = json.loads(HANDOFF.read_text(encoding="utf-8"))
    queues = payload["yaml_retirement_handoff"]["queues"]
    return {row["queue_id"]: row for row in queues}


def test_gap_list_queue_scope_is_exact_projection_of_handoff() -> None:
    rows = _table_after_heading(GAP_LIST.read_text(encoding="utf-8"), "## Queue reconciliation")
    assert {row["Queue ID"] for row in rows} == set(SCOPED_QUEUES)

    authority = _handoff_queues()
    for row in rows:
        expected = SCOPED_QUEUES[row["Queue ID"]]
        handoff = authority[row["Queue ID"]]
        assert row["Disposition"] == expected["disposition"] == handoff["disposition"]
        assert row["YAML path"] == expected["path"]
        assert handoff["paths"] == [expected["path"]]
        assert row["Decision gate"]


def test_every_scoped_gap_has_a_closed_classification_and_binding() -> None:
    text = GAP_LIST.read_text(encoding="utf-8")
    rows = _table_after_heading(text, "## Gap decisions")
    decisions = {row["Gap ID"]: row for row in rows}

    assert {gap_id: row["Classification"] for gap_id, row in decisions.items()} == EXPECTED_GAPS
    assert all(row["Classification"] in ALLOWED_CLASSIFICATIONS for row in rows)
    assert all(row["Gate or authority"] for row in rows)
    assert "TBD" not in text.upper()


def test_gap_list_covers_the_observed_yaml_mechanics_without_expanding_scope() -> None:
    text = GAP_LIST.read_text(encoding="utf-8")
    rows = _table_after_heading(text, "## Gap decisions")
    observed = " ".join(row["Observed YAML mechanics"] for row in rows)

    assert all(token in observed for token in REQUIRED_MECHANIC_TOKENS)
    assert "delete_non_survivor_estate" not in {row["Applies to"] for row in rows}
    assert "archive_design_delta_yaml_twin" not in {row["Applies to"] for row in rows}


def test_task_15_reconciliation_binds_three_prompts_and_drops_only_pointer_helper() -> None:
    text = GAP_LIST.read_text(encoding="utf-8")
    assert "work.md" in text
    assert "review_iteration.md" in text
    assert "review_done.md" in text
    assert "write_lisp_frontend_relpath_value.py" in text

    rows = _table_after_heading(text, "## Gap decisions")
    task_15 = next(row for row in rows if row["Gap ID"] == "verified.task-15-input-drift")
    pointer = next(row for row in rows if row["Gap ID"] == "verified.summary-pointer-helper")
    assert task_15["Classification"] == "implemented"
    assert pointer["Classification"] == "drop"


def test_protected_holdout_stays_owner_gated_without_an_inferred_port() -> None:
    rows = _table_after_heading(GAP_LIST.read_text(encoding="utf-8"), "## Gap decisions")
    owner_gate = next(row for row in rows if row["Gap ID"] == "step-back.owner-disposition")
    assert owner_gate["Classification"] == "blocking_gate"
    assert "hold_non_progress_step_back" in owner_gate["Applies to"]
    assert "owner" in owner_gate["Gate or authority"].lower()


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    remainder = text[start + len(heading) :]
    next_heading = remainder.find("\n### ")
    return remainder if next_heading == -1 else remainder[:next_heading]


def test_yaml_retirement_tasks_1_and_2_are_closed_and_task_3_is_current() -> None:
    program = YAML_RETIREMENT_PROGRAM.read_text(encoding="utf-8")
    task_1 = _section(program, "### Task 1: Close the `.orc` language-gap list — ENABLING")
    task_2 = _section(program, "### Task 2: Move dashboard structure reads to the typed surface — ENABLING")
    task_3 = _section(program, "### Task 3: Split YAML parsing from shared validation — ENABLING")

    assert task_1.count("- [x]") == 3
    assert "- [ ]" not in task_1
    assert task_2.count("- [x]") == 3
    assert "- [ ]" not in task_2
    assert task_3.count("- [ ]") == 3
    assert "**Current selector:** Task 3" in program
    assert "PASS" in task_1
    assert "APPROVED" in task_1
    assert "PASS" in task_2
    assert "APPROVED" in task_2


def test_canonical_routing_surfaces_select_yaml_retirement_task_3() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    capability = CAPABILITY_MATRIX.read_text(encoding="utf-8")
    index = DOCS_INDEX.read_text(encoding="utf-8")

    for text in (roadmap, capability, index):
        assert "YAML retirement Task 3" in text
        assert "YAML retirement Task 1 is current" not in text
        assert "YAML retirement Task 2 is current" not in text

    stage_6 = _section(roadmap, "### Stage 6: Resume YAML Retirement")
    assert "**Current selector:** Task 3" in stage_6
    assert "tasks 1-2 are complete" in " ".join(stage_6.lower().split())
    assert "docs/workflow_yaml_orc_gap_list.md" in stage_6
