from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CURRENT_SELECTOR_PATH = (
    "docs/plans/2026-07-13-procedure-migration-identity-compatibility-plan.md"
)
ORDERED_ROADMAP_PATHS = (
    CURRENT_SELECTOR_PATH,
    "docs/plans/2026-07-13-procedure-first-pilot-plan.md",
    "docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md",
    "docs/plans/2026-07-13-procedure-first-migration-waves-plan.md",
    "docs/plans/2026-07-07-yaml-retirement-program.md",
    "docs/design/workflow_lisp_provider_live_binding.md",
    "docs/design/workflow_lisp_language_server.md",
)
GATE_P4_REVIEWED_STATE = (
    "gates p3 and p4 are independently reviewed and satisfied"
)
TASK_4_1_REVIEWED_STATE = "task 4.1 is complete and independently reviewed"
TASK_4_2_REVIEWED_STATE = "task 4.2 is complete and independently reviewed"
TASK_4_3_COMPLETE_STATE = "task 4.3 is complete"
PHASE_4_COMPLETE_STATE = "phase 4 is complete"
GATE_S3_SATISFIED_STATE = "gate s3 is satisfied"
SEMANTIC_FREEZE_LIFTED_STATE = "semantic migration freeze is lifted"
VALID_TASK_4_3_CLOSEOUT_STATE = (
    "Gates P3 and P4 are independently reviewed and satisfied. "
    "Task 4.1 is complete and independently reviewed. "
    "Task 4.2 is complete and independently reviewed. "
    "Task 4.3 is complete. Phase 4 is complete. Gate S3 is satisfied. "
    "The semantic-migration freeze is lifted."
)
CONTRADICTORY_CLOSEOUT_STATE = re.compile(
    r"\b(?:"
    r"task 4\.3 has not started"
    r"|task 4\.3 is not complete"
    r"|task 4\.3 (?:remains|is) (?:open|pending|in progress|underway)"
    r"|phase 4 is not complete"
    r"|phase 4 (?:remains|is) (?:open|pending|in progress|underway)"
    r"|gate s3 (?:failed|has failed)"
    r"|gate s3 (?:remains|is) (?:open|pending|unsatisfied|not satisfied)"
    r"|semantic migration freeze is not lifted"
    r"|semantic migration freeze (?:remains|is) (?:in force|active)"
    r")\b"
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


def _assert_exact_ordered_routing_paths(surface: str, label: str) -> None:
    canonical = surface.replace("(plans/", "(docs/plans/").replace(
        "(design/", "(docs/design/"
    )
    positions: list[int] = []
    for path in ORDERED_ROADMAP_PATHS:
        assert canonical.count(path) == 1, (label, path, canonical.count(path))
        positions.append(canonical.index(path))
    assert positions == sorted(positions), (label, positions)
    assert "paused" in canonical.lower(), label


def _assert_task_4_3_closeout_state(surface: str, label: str) -> None:
    normalized = _normalized_routing_text(surface)
    assert GATE_P4_REVIEWED_STATE in normalized, label
    assert TASK_4_1_REVIEWED_STATE in normalized, label
    assert TASK_4_2_REVIEWED_STATE in normalized, label
    assert TASK_4_3_COMPLETE_STATE in normalized, label
    assert PHASE_4_COMPLETE_STATE in normalized, label
    assert GATE_S3_SATISFIED_STATE in normalized, label
    assert SEMANTIC_FREEZE_LIFTED_STATE in normalized, label
    assert CONTRADICTORY_CLOSEOUT_STATE.search(normalized) is None, label


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
        VALID_TASK_4_3_CLOSEOUT_STATE.replace(
            "independently reviewed and satisfied", "satisfied", 1
        ),
        VALID_TASK_4_3_CLOSEOUT_STATE.replace(
            "Task 4.1 is complete and independently reviewed. ", "", 1
        ),
        VALID_TASK_4_3_CLOSEOUT_STATE.replace(
            "Task 4.2 is complete and independently reviewed. ", "", 1
        ),
        VALID_TASK_4_3_CLOSEOUT_STATE.replace("Task 4.3 is complete. ", "", 1),
        VALID_TASK_4_3_CLOSEOUT_STATE.replace("Phase 4 is complete. ", "", 1),
        VALID_TASK_4_3_CLOSEOUT_STATE.replace("Gate S3 is satisfied. ", "", 1),
        VALID_TASK_4_3_CLOSEOUT_STATE.replace(
            "The semantic-migration freeze is lifted.", "", 1
        ),
        VALID_TASK_4_3_CLOSEOUT_STATE + " Task 4.3 has not started.",
        VALID_TASK_4_3_CLOSEOUT_STATE + " Phase 4 is not complete.",
        VALID_TASK_4_3_CLOSEOUT_STATE + " Gate S3 failed.",
        VALID_TASK_4_3_CLOSEOUT_STATE
        + " The semantic-migration freeze is not lifted.",
        VALID_TASK_4_3_CLOSEOUT_STATE + " Gate S3 remains open.",
        VALID_TASK_4_3_CLOSEOUT_STATE
        + " The semantic-migration freeze remains in force.",
    ],
    ids=[
        "weakened-gate-review",
        "missing-task-4-1-review",
        "missing-task-4-2-review",
        "missing-task-4-3-complete",
        "missing-phase-4-complete",
        "missing-gate-s3-satisfied",
        "missing-semantic-freeze-lifted",
        "contradictory-task-4-3-unstarted",
        "contradictory-phase-4-incomplete",
        "contradictory-gate-s3-failed",
        "contradictory-semantic-freeze-not-lifted",
        "contradictory-gate-s3-open",
        "contradictory-semantic-freeze-active",
    ],
)
def test_task_4_3_closeout_guard_rejects_weakened_or_contradictory_state(
    mutated_state: str,
) -> None:
    with pytest.raises(AssertionError):
        _assert_task_4_3_closeout_state(mutated_state, "mutated Task 4.3 state")


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
    capability_matrix_path = REPO_ROOT / "docs" / "capability_status_matrix.md"
    procedure_first_row = _markdown_table_row(
        capability_matrix_path, "Workflow Lisp procedure-first reuse contract"
    )
    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Current procedure-first substrate:**", 1
    )[0]
    procedure_sequence = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8").split(
        "**Current next selection (2026-07-13):**", 1
    )[1].split("The completed Phase 1 execution order was:", 1)[0]
    activation_routing = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-activation-plan.md"
    ).read_text(encoding="utf-8").split(
        "> **Routing amendment (2026-07-13):**", 1
    )[1].split("**Tech Stack:**", 1)[0]

    routing_surfaces = {
        "docs index": docs_index_routing,
        "procedure sequence": procedure_sequence,
        "activation": activation_routing,
        "capability matrix": procedure_first_row,
    }
    assert len(routing_surfaces) == 4
    for label, surface in routing_surfaces.items():
        _assert_exact_ordered_routing_paths(surface, label)

        missing = surface.replace(
            "2026-07-13-resume-projection-integrity-hardening-design-plan.md",
            "missing-hardening-plan.md",
            1,
        )
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(missing, f"{label} missing hardening")

        duplicated = surface + " " + CURRENT_SELECTOR_PATH
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(duplicated, f"{label} duplicate selector")

    assert _normalized_routing_text(docs_index_routing).count("current selector") == 1
    assert _normalized_routing_text(procedure_first_row).count("current selector") == 1
