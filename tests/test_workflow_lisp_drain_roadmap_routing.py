from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CURRENT_SELECTOR = (
    "phase 4 task 4.2: strip the g8 serializer"
)
GATE_P4_REVIEWED_STATE = (
    "gates p3 and p4 are independently reviewed and satisfied"
)
TASK_4_1_REVIEWED_STATE = "task 4.1 is complete and independently reviewed"
TASK_4_2_UNSTARTED_STATE = "task 4.2 has not started"
CONTRADICTORY_TASK_4_2_START = re.compile(
    r"(?<!no )\b(?:"
    r"task 4\.2(?: (?:implementation|work|source deletion|deletion))?"
    r"|g8(?: serializer)?(?: (?:implementation|work|source deletion|deletion|removal))?"
    r") has (?:started|begun)\b"
)


def _markdown_table_row(path: Path, key: str) -> str:
    return next(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("|") and key in line
    )


def _normalized_routing_text(text: str) -> str:
    return " ".join(
        text.lower()
        .replace("-", " ")
        .replace("–", " ")
        .replace(">", " ")
        .replace("*", "")
        .replace("`", "")
        .split()
    )


def _assert_current_selector(surface: str, label: str) -> None:
    normalized = _normalized_routing_text(surface)
    clauses = re.findall(
        r"(?:current selector|active step|next active selection)\s*(?:is|:)\s*((?:\d+\.\d+|[^.,;|])+)",
        normalized,
    )
    assert clauses, label
    assert any(CURRENT_SELECTOR in clause for clause in clauses), (label, clauses)
    forbidden = re.compile(
        r"phase 3|task 4\.1|task 4\.(?:[3-9]|[1-9][0-9]+)|stage 5|typed result guidance|yaml archive"
    )
    for clause in clauses:
        assert forbidden.search(clause) is None, (label, clause)


def _assert_task_4_1_closure_state(surface: str, label: str) -> None:
    normalized = _normalized_routing_text(surface)
    assert GATE_P4_REVIEWED_STATE in normalized, label
    assert TASK_4_1_REVIEWED_STATE in normalized, label
    assert TASK_4_2_UNSTARTED_STATE in normalized, label
    assert CONTRADICTORY_TASK_4_2_START.search(normalized) is None, label


def _assert_task_4_2_temporary_pipeline_contract(surface: str, label: str) -> None:
    normalized = _normalized_routing_text(surface)
    assert "temporary g8 artifact pipeline" in normalized, label
    assert "serialize_design_delta_g8_deletion_evidence" in surface, label
    assert "_serialize_design_delta_g8_deletion_evidence" not in surface, label
    assert "_write_build_artifacts" in surface, label
    assert "_add_design_delta_artifacts" not in surface, label
    assert "git rm orchestrator/workflow_lisp/build_design_delta.py" in surface, label
    assert "tests/test_workflow_lisp_stdlib_form_migration.py" in surface, label
    assert "fresh temporary build root" in normalized, label
    assert "artifact_paths" in surface, label
    assert "repo global code search" in normalized, label
    assert "orchestrator/" in surface, label
    assert "tests/" in surface, label
    assert "intentional tests and guards" in normalized, label
    assert "consumer outside" in normalized, label
    assert "artifact gate or parity dependency" in normalized, label
    assert "stop" in normalized, label


@pytest.mark.parametrize(
    "mutated_state",
    [
        (
            "Gates P3 and P4 are satisfied. "
            "Task 4.1 is complete and independently reviewed. "
            "Task 4.2 has not started."
        ),
        (
            "Gates P3 and P4 are independently reviewed and satisfied. "
            "Task 4.2 has not started."
        ),
        (
            "Gates P3 and P4 are independently reviewed and satisfied. "
            "Task 4.1 is complete and independently reviewed. "
            "Task 4.2 has not started. Task 4.2 implementation has begun."
        ),
        (
            "Gates P3 and P4 are independently reviewed and satisfied. "
            "Task 4.1 is complete and independently reviewed. "
            "Task 4.2 has not started. G8 serializer deletion has started."
        ),
        (
            "Gates P3 and P4 are independently reviewed and satisfied. "
            "Task 4.1 is complete and independently reviewed. "
            "Task 4.2 has not started. G8 deletion has started."
        ),
        (
            "Gates P3 and P4 are independently reviewed and satisfied. "
            "Task 4.1 is complete and independently reviewed. "
            "Task 4.2 has not started. G8 removal has begun."
        ),
    ],
    ids=[
        "weakened-gate-review",
        "missing-task-4-1-review",
        "contradictory-task-start",
        "contradictory-serializer-start",
        "contradictory-g8-deletion-start",
        "contradictory-g8-removal-start",
    ],
)
def test_task_4_1_closure_guard_rejects_weakened_or_contradictory_state(
    mutated_state: str,
) -> None:
    with pytest.raises(AssertionError):
        _assert_task_4_1_closure_state(mutated_state, "mutated Task 4.1 state")


def test_design_delta_primary_and_archive_deferral_remain_routed() -> None:
    orc_path = "workflows/library/lisp_frontend_design_delta/drain.orc"
    yaml_path = "workflows/examples/lisp_frontend_design_delta_drain.yaml"
    workflow_catalog_path = REPO_ROOT / "workflows" / "README.md"
    workflow_catalog = workflow_catalog_path.read_text(encoding="utf-8")
    preferred = workflow_catalog.split("Fresh preferred starting points:", 1)[1].split(
        "Reference corpus:", 1
    )[0]
    assert orc_path in preferred
    assert yaml_path not in preferred
    assert "Primary" in _markdown_table_row(workflow_catalog_path, orc_path)
    assert "Compatibility" in _markdown_table_row(workflow_catalog_path, yaml_path)

    triage_path = REPO_ROOT / "docs" / "workflow_yaml_estate_triage.md"
    triage_row = _markdown_table_row(triage_path, yaml_path)
    assert "| yes |" in triage_row
    assert ".orc primary" in triage_row
    assert "Stage 6" in triage_row

    migration_record = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION"
        / "migration_record.md"
    ).read_text(encoding="utf-8")
    current_surface = migration_record.split("## Historical YAML Baseline", 1)[0]
    assert orc_path in current_surface
    assert "primary" in current_surface.lower()
    assert "Gate P3" in current_surface


@pytest.mark.parametrize(
    "mutated_contract",
    [
        "A surviving serializer caller means Task 3.3 was incomplete — STOP.",
        (
            "The temporary G8 artifact pipeline remains live. "
            "Delete it without checking for external consumers."
        ),
    ],
    ids=["reject-all-callers", "missing-external-consumer-stop"],
)
def test_task_4_2_inventory_guard_rejects_incomplete_pipeline_contract(
    mutated_contract: str,
) -> None:
    with pytest.raises(AssertionError):
        _assert_task_4_2_temporary_pipeline_contract(
            mutated_contract, "mutated Task 4.2 contract"
        )


def test_drain_authorities_share_one_current_selector_and_preserve_later_order() -> None:
    drain_plan = (
        REPO_ROOT / "docs" / "plans" / "2026-07-07-drain-migration-g8-retirement.md"
    ).read_text(encoding="utf-8")
    gate_p4_status = drain_plan.split("**Gate P4 (entry to Phase 4):**", 1)[1].split(
        "---", 1
    )[0]
    task_4_2_plan = drain_plan.split(
        "### Task 4.2: Strip the G8 serializer", 1
    )[1].split("### Task 4.3:", 1)[0]
    capability_matrix_path = REPO_ROOT / "docs" / "capability_status_matrix.md"
    backlog_drain_row = _markdown_table_row(
        capability_matrix_path, "`backlog-drain` generic stdlib route"
    )
    design_delta_row = _markdown_table_row(
        capability_matrix_path, "Design Delta parent-family boundary"
    )
    typed_guidance_row = _markdown_table_row(
        capability_matrix_path, "Workflow Lisp typed result guidance"
    )
    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Later procedure-first substrate:**", 1
    )[0]
    procedure_sequence = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8").split(
        "**Current next selection (2026-07-13):**", 1
    )[1].split("The completed Phase 1 execution order was:", 1)[0]
    activation = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-activation-plan.md"
    ).read_text(encoding="utf-8").split(
        "> **Current execution amendment (updated 2026-07-13):**", 1
    )[1].split("**Tech Stack:**", 1)[0]
    migration_record = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "LISP-FRONTEND-DESIGN-DELTA-DRAIN-ORC-MIGRATION"
        / "migration_record.md"
    ).read_text(encoding="utf-8").split(
        "The promotion handoff now has strict promotable parity", 1
    )[1].split("The remaining sections preserve the June migration inventory", 1)[0]
    family_one_row = _markdown_table_row(
        REPO_ROOT / "docs" / "plans" / "2026-07-07-yaml-retirement-program.md",
        "lisp_frontend_design_delta_drain.yaml",
    )
    workflow_catalog_row = _markdown_table_row(
        REPO_ROOT / "workflows" / "README.md", "lisp_frontend_design_delta/drain.orc"
    )
    parametric_status = (
        REPO_ROOT / "docs" / "design" / "workflow_lisp_parametric_type_system.md"
    ).read_text(encoding="utf-8").split("Current status (2026-07-13):", 1)[1].split(
        "## Acceptance Checks", 1
    )[0]
    inventory = json.loads(
        (
            REPO_ROOT
            / "docs"
            / "plans"
            / "LISP-FRONTEND-AUTONOMOUS-DRAIN"
            / "post_wcc_current_state_inventory.json"
        ).read_text(encoding="utf-8")
    )
    inventory_guidance = next(
        row["selector_guidance"]
        for row in inventory["surfaces"]
        if row["surface_id"] == "workflow-lisp-yaml-primary-promotion-gate"
    )
    reconciliation_row = _markdown_table_row(
        REPO_ROOT
        / "docs"
        / "plans"
        / "LISP-FRONTEND-AUTONOMOUS-DRAIN"
        / "design-gaps"
        / "post_wcc_reconciliation_index.md",
        "YAML-primary promotion gate",
    )
    routing_surfaces = {
        "drain plan": gate_p4_status,
        "backlog drain": backlog_drain_row,
        "design delta": design_delta_row,
        "typed guidance": typed_guidance_row,
        "docs index": docs_index_routing,
        "procedure sequence": procedure_sequence,
        "activation": activation,
        "migration record": migration_record,
        "YAML family 1": family_one_row,
        "workflow catalog": workflow_catalog_row,
        "parametric design": parametric_status,
        "post-WCC inventory": inventory_guidance,
        "reconciliation": reconciliation_row,
    }
    assert len(routing_surfaces) == 13
    for label, surface in routing_surfaces.items():
        _assert_current_selector(surface, label)
        _assert_task_4_1_closure_state(surface, label)
    _assert_task_4_2_temporary_pipeline_contract(task_4_2_plan, "Task 4.2 plan")

    mutated = docs_index_routing.replace(
        "strip the G8 serializer",
        "unrelated cleanup",
        1,
    )
    with pytest.raises(AssertionError):
        _assert_current_selector(mutated, "mutated selector title")

    workflow_lisp_readme = (
        REPO_ROOT / "orchestrator" / "workflow_lisp" / "README.md"
    ).read_text(encoding="utf-8")
    assert "`drain_stdlib.py`" not in workflow_lisp_readme
    assert workflow_lisp_readme.count("`stdlib_modules/std/drain.orc`") == 1
    drain_owner = workflow_lisp_readme.split("`stdlib_modules/std/drain.orc`", 1)[1].split(
        "\n- ", 1
    )[0]
    assert "imported generic" in drain_owner
    assert "ordinary specialization and WCC lowering" in drain_owner

    order = _normalized_routing_text(typed_guidance_row).split("current order", 1)[1]
    assert order.index("phase 4 task 4.2") < order.index("stage 5")
    assert "+ 6 `v214` library imports" in family_one_row
    assert "Stage 6" in family_one_row
