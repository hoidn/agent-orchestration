from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT_PLAN_PATH = (
    "docs/plans/2026-07-13-procedure-first-pilot-plan.md"
)
HARDENING_PLAN_PATH = (
    "docs/plans/2026-07-13-resume-projection-integrity-hardening-implementation-plan.md"
)
CURRENT_SELECTOR_PATH = (
    "docs/plans/2026-07-13-procedure-first-migration-waves-plan.md"
)
TRACKED_DESIGN_RETIREMENT_PLAN_PATH = (
    "docs/plans/2026-07-16-tracked-design-phase-identity-retirement-plan.md"
)
STACK_IMPLEMENTATION_RETIREMENT_PLAN_PATH = (
    "docs/plans/2026-07-16-design-plan-impl-implementation-phase-identity-retirement-plan.md"
)
SAME_FILE_BUILD_CHECKS_RETIREMENT_PLAN_PATH = (
    "docs/plans/2026-07-16-same-file-build-checks-identity-retirement-plan.md"
)
DESIGN_DELTA_EXPORTED_RETENTION_PLAN_PATH = (
    "docs/plans/2026-07-16-design-delta-exported-workflow-retention-plan.md"
)
DESIGN_DELTA_FINALIZER_RETENTION_PLAN_PATH = (
    "docs/plans/2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md"
)
DESIGN_DELTA_BLOCKED_RECOVERY_RETENTION_PLAN_PATH = (
    "docs/plans/2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md"
)
DESIGN_DELTA_PHASE_ORCHESTRATION_RETENTION_PLAN_PATH = (
    "docs/plans/2026-07-16-design-delta-phase-orchestration-retention-plan.md"
)
DESIGN_DELTA_COMPLETED_FINALIZATION_RETENTION_PLAN_PATH = (
    "docs/plans/2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md"
)
DESIGN_DELTA_DRAIN_BUILDER_RETENTION_PLAN_PATH = (
    "docs/plans/2026-07-16-design-delta-drain-builder-checkpoint-retention-plan.md"
)
MIGRATION_TASK_1_IMPLEMENTATION_COMMITS = ("4983afff", "fa16bcf0")
CORRECTION_SUBPLAN_PATH = (
    "docs/plans/2026-07-14-procedure-identity-store-match-scoped-counts-plan.md"
)
ORDERED_ROADMAP_PATHS = (
    CURRENT_SELECTOR_PATH,
    "docs/plans/2026-07-07-yaml-retirement-program.md",
    "docs/design/workflow_lisp_provider_live_binding.md",
    "docs/design/workflow_lisp_language_server.md",
)
PROJECTION_ACCEPTANCE_OWNERS = {
    "201-205": (
        "tests/test_workflow_state_projection.py",
        "tests/test_resume_command.py",
    ),
    "206-207": (
        "tests/test_resume_command.py",
        "tests/test_subworkflow_calls.py",
    ),
    "208-213": (
        "tests/test_workflow_state_projection.py",
        "tests/test_resume_command.py",
        "tests/test_subworkflow_calls.py",
    ),
    "214-224": (
        "tests/test_subworkflow_calls.py",
        "tests/test_loader_validation.py",
    ),
    "197, 225-227": ("tests/test_resume_command.py",),
    "228-231": (
        "tests/test_subworkflow_calls.py",
        "tests/test_resume_command.py",
        "tests/test_runtime_step_lifecycle.py",
    ),
    "232-233": (
        "tests/test_state_manager.py",
        "tests/test_observability_report.py",
        "tests/test_resume_command.py",
        "tests/test_subworkflow_calls.py",
    ),
    "234": (
        "tests/test_workflow_state_projection.py",
        "tests/test_resume_command.py",
        "tests/test_subworkflow_calls.py",
    ),
}
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


def _canonical_routing_paths(surface: str) -> str:
    canonical = surface.replace("../plans/", "docs/plans/")
    canonical = canonical.replace("(plans/", "(docs/plans/").replace(
        "(design/", "(docs/design/"
    )
    for path in ORDERED_ROADMAP_PATHS:
        canonical = canonical.replace(f"`{Path(path).name}`", f"`{path}`")
    return canonical


def _procedure_sequence_current_routing() -> str:
    sequence = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8")
    return sequence.split("The tracked-plan pilot subsequently", 1)[1].split(
        "The completed Phase 1 execution order was:", 1
    )[0]


def _migration_task_section(plan: str, task_number: int) -> str:
    section = plan.split(f"### Task {task_number}:", 1)[1]
    next_heading = f"### Task {task_number + 1}:"
    return section.split(next_heading, 1)[0] if next_heading in section else section


def _migration_plan_status(plan: str) -> str:
    return plan.split("**Status:**", 1)[1].split("- Accepted contract:", 1)[0]


def _procedure_sequence_selector_surfaces() -> dict[str, str]:
    sequence_path = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    )
    sequence = sequence_path.read_text(encoding="utf-8")
    return {
        "roadmap disposition": _markdown_table_row(
            sequence_path,
            "2026-07-13-procedure-first-migration-waves-plan.md",
        ),
        "roadmap current routing": _procedure_sequence_current_routing(),
        "roadmap Stage 5 selector": sequence.split(
            "### Stage 5: Implement Procedure-First Reuse In Waves", 1
        )[1].split("### Stage 6: Resume YAML Retirement", 1)[0],
    }


def _assert_task_6_complete_and_task_7_step_1_current(
    surface: str,
    label: str,
) -> None:
    normalized = _normalized_routing_text(surface)
    canonical = _canonical_routing_paths(surface)
    assert canonical.count(DESIGN_DELTA_FINALIZER_RETENTION_PLAN_PATH) == 1, label
    assert canonical.count(DESIGN_DELTA_BLOCKED_RECOVERY_RETENTION_PLAN_PATH) == 1, label
    assert canonical.count(DESIGN_DELTA_PHASE_ORCHESTRATION_RETENTION_PLAN_PATH) == 1, label
    assert canonical.count(DESIGN_DELTA_COMPLETED_FINALIZATION_RETENTION_PLAN_PATH) == 1, label
    assert canonical.count(DESIGN_DELTA_DRAIN_BUILDER_RETENTION_PLAN_PATH) == 1, label
    assert re.search(
        r"\btask 1\b.{0,160}(?:"
        r"rebaseline.{0,80}\bcomplete\w*\b"
        r"|\bcomplete\w*\b.{0,80}rebaseline)",
        normalized,
    ), label
    assert "task 2" in normalized and "complete" in normalized, label
    assert "daff694c" in normalized, label
    assert "task 3" in normalized and "retained" in normalized, label
    assert "task 4" in normalized and "complete" in normalized, label
    for commit in ("c9687539", "26d9ecd0", "848ceb52"):
        assert commit in normalized, (label, commit)
    assert "0 procedure candidates" in normalized, label
    assert "32 effect adapters" in normalized, label
    assert "63 legacy retire" in normalized, label
    assert re.search(r"\b(?:thirteen|13)\b.{0,40}\bpublic\b", normalized), label
    assert re.search(r"\b(?:one|1)\b.{0,40}\bhistory\b", normalized), label
    assert "finalizer" in normalized and "retained" in normalized, label
    assert "strict compatibility" in normalized, label
    assert "phase orchestration" in normalized and "retained" in normalized, label
    assert "completed finalization" in normalized, label
    assert "4 + 6 + 9 + 2 = 21" in normalized, label
    assert "task 5" in normalized and "retained" in normalized, label
    assert re.search(
        r"\btask 6\b.{0,80}\bcomplete\w*\b",
        normalized,
    ), label
    assert re.search(
        r"\btask 7\b.{0,40}\bstep 1\b.{0,80}\bcurrent\b"
        r"|\bcurrent\b.{0,80}\btask 7\b.{0,40}\bstep 1\b",
        normalized,
    ), label
    for commit in MIGRATION_TASK_1_IMPLEMENTATION_COMMITS:
        assert normalized.count(commit) == 1, (label, commit)

    assert re.search(
        r"\bphase orchestration\b.{0,80}\bcurrent sub selector\b"
        r"|\bblocked recovery/finalization\b.{0,80}\bcurrent sub selector\b"
        r"|\bcompleted finalization\b.{0,100}\bcurrent sub selector\b",
        normalized,
    ) is None, label


def _assert_exact_ordered_routing_paths(surface: str, label: str) -> None:
    canonical = _canonical_routing_paths(surface)
    positions: list[int] = []
    for path in ORDERED_ROADMAP_PATHS:
        assert canonical.count(path) == 1, (label, path, canonical.count(path))
        positions.append(canonical.index(path))
    assert positions == sorted(positions), (label, positions)
    assert canonical.count(CORRECTION_SUBPLAN_PATH) == 0, label
    assert _normalized_routing_text(surface).count("current selector") == 1, label


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


def test_procedure_first_status_surfaces_share_current_migration_wave_boundary() -> None:
    capability_matrix_path = REPO_ROOT / "docs" / "capability_status_matrix.md"
    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Current procedure-first substrate:**", 1
    )[0]
    routing_surfaces = {
        "docs index": docs_index_routing,
        "procedure sequence": _procedure_sequence_current_routing(),
        "capability matrix": _markdown_table_row(
            capability_matrix_path,
            "Workflow Lisp procedure-first reuse contract",
        ),
    }

    for label, surface in routing_surfaces.items():
        canonical = _canonical_routing_paths(surface)
        assert canonical.count(CURRENT_SELECTOR_PATH) == 1, label
        normalized = _normalized_routing_text(surface)
        assert "migration wave" in normalized, label
        assert "current selector" in normalized, label
        assert "migration waves remain blocked" not in normalized, label
        assert "runtime hardening remains pending" not in normalized, label


def test_migration_wave_task_7_handoff_advances_local_selector_to_task_8() -> None:
    plan = (REPO_ROOT / CURRENT_SELECTOR_PATH).read_text(encoding="utf-8")
    current_queue = plan.split(
        "## Current queue after Task 6 closeout",
        1,
    )[1].split("## Per-family migration protocol", 1)[0]
    public_boundary_row = next(
        line
        for line in current_queue.splitlines()
        if line.startswith("| `public-boundary` |")
    )
    assert re.search(r"\|\s*13 separate entries\s*\|", public_boundary_row)
    task_1 = _migration_task_section(plan, 1)
    task_2 = _migration_task_section(plan, 2)
    task_3 = _migration_task_section(plan, 3)
    task_4 = _migration_task_section(plan, 4)
    task_5 = _migration_task_section(plan, 5)
    remaining_tasks = {
        task_number: _migration_task_section(plan, task_number)
        for task_number in range(6, 9)
    }
    task_1_steps = re.findall(r"(?m)^- \[([ xX])\] \*\*Step", task_1)

    assert task_1_steps == ["x", "x", "x", "x"]
    assert re.findall(r"(?m)^- \[([ xX])\] \*\*Step", task_2) == [
        "x", "x", "x", "x", "x", "x"
    ]
    assert re.findall(r"(?m)^- \[([ xX])\] \*\*Step", task_3) == [
        "x", "x", "x", "x", "x"
    ]
    assert re.findall(r"(?m)^- \[([ xX])\] \*\*Step", task_4) == [
        "x", "x", "x", "x"
    ]
    assert re.findall(r"(?m)^- \[([ xX])\] \*\*Step", task_5) == [
        "x", "x", "x", "x", "x"
    ]
    for task_number, expected_step_count in {6: 5}.items():
        assert re.findall(
            r"(?m)^- \[([ xX])\] \*\*Step",
            remaining_tasks[task_number],
        ) == ["x"] * expected_step_count
    for task_number, expected_step_count in {7: 4}.items():
        assert re.findall(
            r"(?m)^- \[([ xX])\] \*\*Step",
            remaining_tasks[task_number],
        ) == ["x"] * expected_step_count
    for task_number, expected_step_count in {8: 5}.items():
        assert re.findall(
            r"(?m)^- \[([ xX])\] \*\*Step",
            remaining_tasks[task_number],
        ) == [" "] * expected_step_count
    normalized_task_7 = _normalized_routing_text(remaining_tasks[7])
    assert "complete" in normalized_task_7
    normalized_status = _normalized_routing_text(_migration_plan_status(plan))
    assert re.search(
        r"\btask 8\b.{0,40}\bstep 1\b.{0,80}\bcurrent\b"
        r"|\bcurrent\b.{0,80}\btask 8\b.{0,40}\bstep 1\b",
        normalized_status,
    )

    for commit in MIGRATION_TASK_1_IMPLEMENTATION_COMMITS:
        assert commit in task_1

    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Current procedure-first substrate:**", 1
    )[0]
    capability_row = _markdown_table_row(
        REPO_ROOT / "docs" / "capability_status_matrix.md",
        "Workflow Lisp procedure-first reuse contract",
    )
    selector_surfaces = {
        "docs index": docs_index_routing,
        "capability matrix": capability_row,
        **_procedure_sequence_selector_surfaces(),
    }
    for label, surface in selector_surfaces.items():
        _assert_task_6_complete_and_task_7_step_1_current(surface, label)

    for label in ("docs index", "roadmap current routing"):
        _assert_exact_ordered_routing_paths(selector_surfaces[label], label)


def test_yaml_retirement_program_uses_exact_handoff_queues_and_two_ports() -> None:
    program = (
        REPO_ROOT / "docs" / "plans" / "2026-07-07-yaml-retirement-program.md"
    ).read_text(encoding="utf-8")
    inventory = json.loads(
        (
            REPO_ROOT
            / "docs"
            / "plans"
            / "2026-07-13-procedure-first-reuse-inventory.json"
        ).read_text(encoding="utf-8")
    )
    handoff = inventory["yaml_retirement_handoff"]
    manifest = program.split("## Stage-6 Queue Manifest", 1)[1].split(
        "### Task 1:", 1
    )[0]
    manifest_rows = {
        cells[0]: cells
        for line in manifest.splitlines()
        if line.startswith("| `")
        for cells in ([cell.strip(" `") for cell in line.strip("|").split("|")],)
    }
    expected = {
        queue["queue_id"]: (
            str(len(queue["paths"])),
            str(len(queue["legacy_retire_record_ids"])),
        )
        for queue in handoff["queues"]
    }
    assert set(manifest_rows) == set(expected)
    for queue_id, (path_count, legacy_count) in expected.items():
        row = manifest_rows[queue_id]
        assert row[1] == path_count
        assert row[2] == legacy_count
        assert row[3] == "pending"

    assert manifest_rows["delete_non_survivor_estate"][4] == "none"
    assert manifest_rows["archive_design_delta_yaml_twin"][4] == (
        "delete_non_survivor_estate"
    )
    for queue_id in (
        "port_verified_iteration",
        "port_generic_run_watchdog",
        "hold_non_progress_step_back",
    ):
        assert manifest_rows[queue_id][4] == "none"

    task_5 = program.split("### Task 5:", 1)[1].split("### Task 6:", 1)[0]
    task_5_rows = [
        line for line in task_5.splitlines() if line.startswith("| `")
    ]
    assert len(task_5_rows) == 2
    assert "verified_iteration_drain" in task_5_rows[0]
    assert "generic_run_watchdog" in task_5_rows[1]
    for retired_family in (
        "lisp_frontend_autonomous_drain",
        "neurips_steered_backlog_drain",
        "major_project_tranche_drain",
        "lisp_frontend_proc_refs_partial_application_drain",
    ):
        assert retired_family not in task_5

    normalized = _normalized_routing_text(program)
    for contract_term in (
        "yaml and yml",
        "git history",
        "zero unclassified active references",
        "zero supported matching nonterminal",
        "pending adjudication",
        "early independent",
    ):
        assert contract_term in normalized
    assert "`pending_stage_6_scan`" in program
    assert re.search(r"design delta \.?orc primary satisfies", normalized)
    assert "class delete example archive ungated" not in normalized
    assert "port vs absorb decision" not in normalized

    protected_paths = {
        "docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md",
        "docs/plans/2026-07-01-workflow-audit-tier-fixes.md",
        (
            "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/"
            "remaining-neurips-migration-experiment/"
            "migration_experiment_recommendation_report.md"
        ),
        "state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt",
        "tests/test_workflow_non_progress_step_back_demo.py",
        "workflows/examples/non_progress_step_back_demo.yaml",
        "workflows/library/prompts/workflow_step_back/diagnose_non_progress.md",
    }
    protected = program.split("## Protected working-tree guard", 1)[1].split(
        "## Stage-6 Queue Manifest", 1
    )[0]
    listed = {
        line[3:-1]
        for line in protected.splitlines()
        if line.startswith("- `") and line.endswith("`")
    }
    assert listed == protected_paths
    assert "git diff --cached --name-only --" in protected
    for path in protected_paths:
        assert f"'{path}'" in protected


def test_yaml_retirement_handoff_plan_stages_exact_eight_owned_paths() -> None:
    handoff_plan = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-16-yaml-retirement-handoff-plan.md"
    ).read_text(encoding="utf-8")
    stage_block = handoff_plan.split("Stage only these eight paths:", 1)[1].split(
        "```", 2
    )[1]
    staged_paths = {
        line.strip().removesuffix(" \\")
        for line in stage_block.splitlines()
        if line.strip().startswith(("docs/", "tests/"))
    }
    assert staged_paths == {
        "docs/plans/2026-07-07-yaml-retirement-program.md",
        "docs/workflow_yaml_estate_triage.md",
        "docs/plans/2026-07-13-procedure-first-reuse-inventory.json",
        "docs/plans/2026-07-13-procedure-first-reuse-inventory.md",
        "docs/plans/2026-07-13-procedure-first-migration-waves-plan.md",
        "docs/plans/2026-07-16-yaml-retirement-handoff-plan.md",
        "tests/test_workflow_lisp_procedure_first_migrations.py",
        "tests/test_workflow_lisp_drain_roadmap_routing.py",
    }


def test_task_2_step_1_closes_on_bounded_identity_retirement_ineligibility() -> None:
    migration_plan = (REPO_ROOT / CURRENT_SELECTOR_PATH).read_text(encoding="utf-8")
    prerequisite = REPO_ROOT / TRACKED_DESIGN_RETIREMENT_PLAN_PATH
    sequence = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    assert prerequisite.is_file()
    assert TRACKED_DESIGN_RETIREMENT_PLAN_PATH not in ORDERED_ROADMAP_PATHS
    prerequisite_text = prerequisite.read_text(encoding="utf-8")
    assert "reviewed_internal_identity_retirement" in prerequisite_text
    prerequisite_status = prerequisite_text.split("**Status:**", 1)[1].split(
        "**Goal:**", 1
    )[0]
    assert "Complete by fail-closed eligibility stop" in prerequisite_status
    assert "26 supported old-identity consumers" in prerequisite_status
    assert "introduced no new" in prerequisite_status
    assert CURRENT_SELECTOR_PATH in prerequisite_text
    assert "Parent selector" in prerequisite_text
    assert "procedure first migration waves task 2 step 2 is the next" in (
        _normalized_routing_text(prerequisite_text)
    )

    task_2_step_1 = _migration_task_section(migration_plan, 2).split(
        "- [x] **Step 2:", 1
    )[0]
    for label, surface in {
        "migration Task 2 Step 1": task_2_step_1,
        "roadmap Stage 5": sequence.split(
            "### Stage 5: Implement Procedure-First Reuse In Waves", 1
        )[1].split("### Stage 6: Resume YAML Retirement", 1)[0],
        "docs index component routing": docs_index.split(
            "**Component-plan routing:**", 1
        )[1].split("**Current procedure-first substrate:**", 1)[0],
    }.items():
        canonical = _canonical_routing_paths(surface)
        assert canonical.count(TRACKED_DESIGN_RETIREMENT_PLAN_PATH) == 1, label
        normalized = _normalized_routing_text(surface)
        assert "task 2" in normalized, label
        assert "consumer" in normalized, label

    index_routing = docs_index.split("**Component-plan routing:**", 1)[1].split(
        "**Current procedure-first substrate:**", 1
    )[0]
    canonical_index = _canonical_routing_paths(index_routing)
    assert canonical_index.count(CURRENT_SELECTOR_PATH) == 1
    assert _normalized_routing_text(index_routing).count("current selector") == 1
    assert "task 3" in _normalized_routing_text(index_routing)
    _assert_task_6_complete_and_task_7_step_1_current(
        index_routing,
        "docs index component routing",
    )


def test_task_2_step_2_closes_on_bounded_identity_retirement_ineligibility() -> None:
    migration_plan = (REPO_ROOT / CURRENT_SELECTOR_PATH).read_text(encoding="utf-8")
    decision = REPO_ROOT / STACK_IMPLEMENTATION_RETIREMENT_PLAN_PATH
    sequence = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    assert decision.is_file()
    assert STACK_IMPLEMENTATION_RETIREMENT_PLAN_PATH not in ORDERED_ROADMAP_PATHS
    decision_text = decision.read_text(encoding="utf-8")
    assert "reviewed_internal_identity_retirement" in decision_text
    decision_status = decision_text.split("**Status:**", 1)[1].split(
        "**Goal:**", 1
    )[0]
    assert "Complete by fail-closed eligibility stop" in decision_status
    assert "24 supported old-identity" in decision_status
    assert CURRENT_SELECTOR_PATH in decision_text
    assert "Parent selector" in decision_text
    assert "procedure first migration waves task 2 step 3 is the next" in (
        _normalized_routing_text(decision_text)
    )

    task_2 = _migration_task_section(migration_plan, 2)
    task_2_step_2 = task_2.split("- [x] **Step 2:", 1)[1].split(
        "- [x] **Step 3:", 1
    )[0]
    for label, surface in {
        "migration Task 2 Step 2": task_2_step_2,
        "roadmap Stage 5": sequence.split(
            "### Stage 5: Implement Procedure-First Reuse In Waves", 1
        )[1].split("### Stage 6: Resume YAML Retirement", 1)[0],
        "docs index component routing": docs_index.split(
            "**Component-plan routing:**", 1
        )[1].split("**Current procedure-first substrate:**", 1)[0],
    }.items():
        canonical = _canonical_routing_paths(surface)
        assert canonical.count(STACK_IMPLEMENTATION_RETIREMENT_PLAN_PATH) == 1, label
        normalized = _normalized_routing_text(surface)
        assert "task 2" in normalized, label
        assert "24" in normalized and "consumer" in normalized, label


def test_task_2_step_3_closes_on_live_route_strict_compatibility() -> None:
    migration_plan = (REPO_ROOT / CURRENT_SELECTOR_PATH).read_text(encoding="utf-8")
    decision = REPO_ROOT / SAME_FILE_BUILD_CHECKS_RETIREMENT_PLAN_PATH
    sequence = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    assert decision.is_file()
    assert SAME_FILE_BUILD_CHECKS_RETIREMENT_PLAN_PATH not in ORDERED_ROADMAP_PATHS
    decision_text = decision.read_text(encoding="utf-8")
    decision_status = decision_text.split("**Status:**", 1)[1].split(
        "**Goal:**", 1
    )[0]
    normalized_decision = _normalized_routing_text(decision_text)
    normalized_status = _normalized_routing_text(decision_status)
    assert "complete by fail closed eligibility stop" in normalized_status
    assert "evaluated against source baseline commit 174b7351" in normalized_status
    assert "strict_compatibility is mandatory for promoted/live routes" in (
        normalized_decision
    )
    assert "current/live" in normalized_decision
    assert "must not encode a counterfactual route_live: false" in normalized_decision
    assert "zero store consumers alone are insufficient" in normalized_decision
    for route_label in (
        "wcc_default",
        "leaf_runtime_candidate",
        "preferred_current_guidance",
    ):
        assert route_label in decision_text
    assert "task 2 step 3 closes without a migration" in normalized_decision
    assert "task 2 step 4 is the next sub selector" in normalized_decision

    task_2 = _migration_task_section(migration_plan, 2)
    task_2_step_3 = task_2.split("- [x] **Step 3:", 1)[1].split(
        "- [x] **Step 4:", 1
    )[0]
    for label, surface in {
        "migration Task 2 Step 3": task_2_step_3,
        "roadmap Stage 5": sequence.split(
            "### Stage 5: Implement Procedure-First Reuse In Waves", 1
        )[1].split("### Stage 6: Resume YAML Retirement", 1)[0],
        "docs index component routing": docs_index.split(
            "**Component-plan routing:**", 1
        )[1].split("**Current procedure-first substrate:**", 1)[0],
    }.items():
        canonical = _canonical_routing_paths(surface)
        assert canonical.count(SAME_FILE_BUILD_CHECKS_RETIREMENT_PLAN_PATH) == 1, label
        normalized = _normalized_routing_text(surface)
        assert (
            "step 3" in normalized
            or "same_file_record_call_binding.orc" in normalized
        ), label
        assert (
            "strict compatibility" in normalized
            or "strict_compatibility" in normalized
        ), label
        assert "live" in normalized or "active" in normalized, label


@pytest.mark.parametrize(
    "replacement",
    (
        "Task 5 completed finalization remains current.",
        "Task 5 remains open; Task 6 has not started.",
        "Task 6 remains open; Task 7 has not started.",
    ),
)
def test_task_7_current_selector_guard_rejects_stale_or_skipped_routing(
    replacement: str,
) -> None:
    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Current procedure-first substrate:**", 1
    )[0]
    mutated = re.sub(
        r"Task 6[^.]{0,500}Task 7 Step 1[^.]{0,100}(?:current|selected)\.",
        replacement,
        docs_index_routing,
        count=1,
    )
    assert mutated != docs_index_routing

    with pytest.raises(AssertionError):
        _assert_task_6_complete_and_task_7_step_1_current(
            mutated,
            "mutated docs-index routing",
        )


def test_resume_projection_hardening_is_closed_without_claiming_migration() -> None:
    implementation_plan = (REPO_ROOT / HARDENING_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    capability_matrix_path = REPO_ROOT / "docs" / "capability_status_matrix.md"
    hardening_row = _markdown_table_row(
        capability_matrix_path,
        "Resume projection-integrity hardening",
    )

    assert re.search(r"(?m)^- \[ \] \*\*Step", implementation_plan) is None
    assert "complete" in _normalized_routing_text(implementation_plan[:1600])
    assert "| Implemented |" in hardening_row
    normalized_row = _normalized_routing_text(hardening_row)
    assert "migration waves remain blocked" not in normalized_row
    assert "migration waves are implemented" not in normalized_row


def test_projection_integrity_acceptance_proof_ownership_is_complete() -> None:
    acceptance = (REPO_ROOT / "specs" / "acceptance" / "index.md").read_text(
        encoding="utf-8"
    )
    normative, proof_routing = acceptance.split(
        "Resume Projection-Integrity Executable-Proof Routing",
        1,
    )
    proof_routing = proof_routing.split("## DSL Evolution Rollout Crosswalk", 1)[0]
    normalized = _normalized_routing_text(proof_routing)

    for clause in (197, *range(201, 235)):
        assert re.search(rf"(?m)^{clause}\. ", normative), clause
    assert "clauses 197 and 201 234" in normalized
    assert "runtime implementation is pending" not in normalized
    assert "pending executable proof ownership" not in normalized
    assert "runtime implementation" in normalized
    assert "complete" in normalized
    assert HARDENING_PLAN_PATH in proof_routing
    assert "fdf1e06b" in proof_routing
    assert "baseline equivalence" in normalized
    assert "all pass" in normalized and "not" in normalized

    for clauses, owners in PROJECTION_ACCEPTANCE_OWNERS.items():
        row = next(
            line
            for line in proof_routing.splitlines()
            if line.startswith(f"| {clauses} |")
        )
        for owner in owners:
            assert owner in row, (clauses, owner)


def test_historical_and_durable_authorities_do_not_claim_live_selector_ownership() -> None:
    activation = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-activation-plan.md"
    ).read_text(encoding="utf-8")
    compatibility_design = (
        REPO_ROOT
        / "docs"
        / "design"
        / "workflow_lisp_procedure_migration_identity_compatibility.md"
    ).read_text(encoding="utf-8")

    assert "current selector" not in _normalized_routing_text(activation)
    assert "historical" in _normalized_routing_text(activation)
    assert HARDENING_PLAN_PATH in activation
    assert "current selector" not in _normalized_routing_text(compatibility_design)
    assert "durable compatibility design" in _normalized_routing_text(
        compatibility_design
    )
    assert HARDENING_PLAN_PATH in compatibility_design
    assert CURRENT_SELECTOR_PATH in compatibility_design


def test_current_task_3_routes_only_the_authorized_same_id_recovery_selector() -> None:
    pilot = (REPO_ROOT / PILOT_PLAN_PATH).read_text(encoding="utf-8")

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
    triage_cells = [cell.strip() for cell in triage_row.strip().strip("|").split("|")]
    assert triage_cells == [
        yaml_path,
        "archive_design_delta_yaml_twin",
        "archive",
        orc_path,
        "6",
        "git_history",
        "pending",
        "reference + supported-run-consumer",
    ]

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
    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Current procedure-first substrate:**", 1
    )[0]
    routing_surfaces = {
        "docs index": docs_index_routing,
        "procedure sequence": _procedure_sequence_current_routing(),
    }
    assert len(routing_surfaces) == 2
    for label, surface in routing_surfaces.items():
        _assert_exact_ordered_routing_paths(surface, label)

        missing = surface.replace(
            "2026-07-13-procedure-first-migration-waves-plan.md",
            "missing-migration-plan.md",
            1,
        )
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(missing, f"{label} missing migration")

        duplicated = surface + " " + CURRENT_SELECTOR_PATH
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(duplicated, f"{label} duplicate selector")

        correction_promoted = surface + " " + CORRECTION_SUBPLAN_PATH
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(
                correction_promoted,
                f"{label} correction promoted",
            )

        migration_name = Path(ORDERED_ROADMAP_PATHS[0]).name
        yaml_name = Path(ORDERED_ROADMAP_PATHS[1]).name
        reordered = (
            surface.replace(migration_name, "__MIGRATION_PLAN__", 1)
            .replace(yaml_name, migration_name, 1)
            .replace("__MIGRATION_PLAN__", yaml_name, 1)
        )
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(reordered, f"{label} reordered")

        missing_selector_declaration = re.sub(
            "current selector",
            "active plan",
            surface,
            count=1,
            flags=re.IGNORECASE,
        )
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(
                missing_selector_declaration,
                f"{label} missing selector declaration",
            )

        removed_selector_declaration = re.sub(
            "current selector",
            "",
            surface,
            count=1,
            flags=re.IGNORECASE,
        )
        with pytest.raises(AssertionError):
            _assert_exact_ordered_routing_paths(
                removed_selector_declaration,
                f"{label} removed selector declaration",
            )
