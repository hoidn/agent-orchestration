from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CURRENT_SELECTOR_PATH = (
    "docs/plans/2026-07-13-procedure-first-pilot-plan.md"
)
CORRECTION_SUBPLAN_PATH = (
    "docs/plans/2026-07-14-procedure-identity-store-match-scoped-counts-plan.md"
)
ORDERED_ROADMAP_PATHS = (
    CURRENT_SELECTOR_PATH,
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
CURRENT_RECOVERY_FIX_COMMIT = "1cba48c8"
RECOVERY_STATUS_SURFACES = (
    "docs/index.md",
    "docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md",
    "docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md",
    CURRENT_SELECTOR_PATH,
)
CONTRADICTORY_RECOVERY_STATUS = re.compile(
    r"\bgeneric prerequisite fix (?:remains|is) (?:open|pending|in progress|underway)\b"
    r"|\bsecond mutation requires .*\bfix\b.*\breviews?\b"
    r"|\b(?:second )?recovery harness reviews passed\b"
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
    assert canonical.count(CORRECTION_SUBPLAN_PATH) == 0, label
    assert _normalized_routing_text(surface).count("current selector") == 1, label


def _assert_early_yaml_sweep_exception(surface: str, label: str) -> None:
    normalized = _normalized_routing_text(surface)
    assert "deletion" in normalized, label
    assert "sweep" in normalized, label
    assert "quiescence" in normalized, label
    assert "independent" in normalized, label
    assert "not selected" in normalized, label
    assert "has not started" in normalized, label
    assert "not full stage 6" in normalized, label
    assert "does not reorder" in normalized, label


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


def _assert_current_task_3_recovery_status(
    surface: str,
    label: str,
    *,
    require_explicit_mutation_hold: bool = False,
) -> None:
    normalized = _normalized_routing_text(surface)
    assert CURRENT_RECOVERY_FIX_COMMIT in normalized, label
    assert "second recovery form" in normalized, label
    assert "ordered harness reviews" in normalized, label
    assert "harness commit" in normalized, label
    assert "owner confirmation" in normalized, label
    assert "no second attempt" in normalized, label
    if require_explicit_mutation_hold:
        assert "no second mutation" in normalized and "authorized" in normalized, label
    assert CONTRADICTORY_RECOVERY_STATUS.search(normalized) is None, label


def test_procedure_first_status_surfaces_share_current_task_3_recovery_boundary() -> None:
    for relative_path in RECOVERY_STATUS_SURFACES:
        surface = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        _assert_current_task_3_recovery_status(
            surface,
            relative_path,
            require_explicit_mutation_hold=relative_path.endswith(
                "procedure-first-roadmap-activation-plan.md"
            ),
        )


def test_current_task_3_routes_only_the_authorized_same_id_recovery_selector() -> None:
    pilot = (REPO_ROOT / CURRENT_SELECTOR_PATH).read_text(encoding="utf-8")

    assert "test_tracked_plan_phase_exact_two_run_evidence" not in pilot
    assert (
        "test_tracked_plan_phase_authorized_interrupted_run_recovery" in pilot
    )
    assert (
        "docs/plans/evidence/procedure-first-pilot/tracked-plan-phase/"
        "attestations/task-3/fresh-child-resume-recovery-authorization.json"
    ) in pilot
    normalized = _normalized_routing_text(pilot)
    assert "authorization remains uncommitted" in normalized
    assert "bound harness commit" in normalized
    assert "committed atomically with" in normalized


@pytest.mark.parametrize(
    "contradiction",
    (
        "The generic prerequisite fix is in progress.",
        "Any second mutation requires the fix and its ordered reviews to pass.",
    ),
)
def test_task_3_recovery_status_guard_rejects_stale_prerequisite_state(
    contradiction: str,
) -> None:
    current = (
        f"The generic fix landed at {CURRENT_RECOVERY_FIX_COMMIT}. "
        "The exact second-recovery form awaits ordered harness reviews, the harness "
        "commit, mechanical binding population, and owner confirmation. "
        "No second attempt has occurred, and no second mutation is authorized."
    )

    with pytest.raises(AssertionError):
        _assert_current_task_3_recovery_status(
            f"{current} {contradiction}",
            "mutated Task 3 recovery status",
            require_explicit_mutation_hold=True,
        )


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

        correction_promoted = surface + " " + CORRECTION_SUBPLAN_PATH
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(
                correction_promoted,
                f"{label} correction promoted",
            )

        missing_selector_declaration = surface.replace("current selector", "active plan", 1)
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(
                missing_selector_declaration,
                f"{label} missing selector declaration",
            )

        removed_selector_declaration = surface.replace("current selector", "", 1)
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(
                removed_selector_declaration,
                f"{label} removed selector declaration",
            )

        _assert_early_yaml_sweep_exception(surface, label)

        for mutation, mutation_label in (
            (
                surface.replace("has not started", "has started", 1),
                "started sweep",
            ),
            (
                surface.replace("has not started", "", 1),
                "missing not-started clause",
            ),
            (
                surface.replace("does not reorder", "does reorder", 1),
                "reordered stages",
            ),
            (
                surface.replace("does not reorder", "", 1),
                "missing no-reorder clause",
            ),
        ):
            with pytest.raises(AssertionError):
                _assert_early_yaml_sweep_exception(
                    mutation,
                    f"{label} {mutation_label}",
                )
