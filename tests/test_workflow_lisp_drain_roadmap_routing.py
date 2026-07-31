from __future__ import annotations

import copy
import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from tests.workflow_lisp_procedure_identity import (
    normalize_procedure_prerequisite_failure_log,
)


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
PROVIDER_LIVE_BINDING_PLAN_PATH = (
    "docs/plans/2026-07-23-provider-live-binding-implementation-plan.md"
)
PROVIDER_PEER_MESSAGING_PLAN_PATH = (
    "docs/plans/2026-07-24-provider-peer-messaging-v1.1-implementation-plan.md"
)
PURE_LIST_TRAVERSAL_DESIGN_PATH = (
    "docs/design/workflow_lisp_pure_list_traversal.md"
)
PURE_LIST_TRAVERSAL_PLAN_PATH = (
    "docs/plans/2026-07-25-workflow-lisp-pure-list-traversal-implementation-plan.md"
)
LANGUAGE_SERVER_PLAN_PATH = (
    "docs/plans/2026-07-25-workflow-lisp-language-server-implementation-plan.md"
)
LANGUAGE_QUALITY_ROADMAP_PATH = (
    "docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md"
)
SUBSTRATE_MAINTENANCE_TRACK_PATH = (
    "docs/plans/2026-07-26-substrate-maintenance-track.md"
)
PURE_RESULT_REPLAY_DESIGN_PATH = (
    "docs/design/workflow_lisp_pure_result_replay.md"
)
PURE_RESULT_REPLAY_PLAN_PATH = (
    "docs/plans/2026-07-30-pure-result-replay-feasibility-component-plan.md"
)
PURE_RESULT_REPLAY_ACTIVATION_PLAN_PATH = (
    "docs/plans/2026-07-30-pure-result-replay-activation-component-plan.md"
)
MC_COMMON_HELPER_PLAN_PATH = (
    "docs/plans/2026-07-30-mc-common-helper-consolidation-component-plan.md"
)
LEXICAL_EXECUTION_CHECKPOINTS_DESIGN_PATH = (
    "docs/design/workflow_lisp_lexical_execution_checkpoints.md"
)
WORKFLOW_LISP_STATE_LAYOUT_DESIGN_PATH = (
    "docs/design/workflow_lisp_state_layout.md"
)
DESIGN_INDEX_PATH = "docs/design/README.md"
CAPABILITY_STATUS_MATRIX_PATH = "docs/capability_status_matrix.md"
STATE_SPEC_PATH = "specs/state.md"
M0_GREEN_BASELINE_PLAN_PATH = (
    "docs/plans/2026-07-29-m0-green-baseline-component-plan.md"
)
M1_ESTATE_SHRINK_PLAN_PATH = (
    "docs/plans/2026-07-29-m1-estate-shrink-component-plan.md"
)
ML1_PROVIDER_RECOVERY_PLAN_PATH = (
    "docs/plans/2026-07-30-provider-at-least-once-recovery-component-plan.md"
)
ML2_PROVIDER_ALLOCATOR_PLAN_PATH = (
    "docs/plans/2026-07-30-provider-attempt-allocator-simplification-component-plan.md"
)
ML4_ADJUDICATION_RECOVERY_PLAN_PATH = (
    "docs/plans/2026-07-30-adjudication-rerun-recovery-component-plan.md"
)
REFUSAL_DIAGNOSABILITY_PLAN_PATH = (
    "docs/plans/2026-07-23-refusal-diagnosability-fixes-plan.md"
)
TRANSPORTABLE_VALUE_DESIGN_PATH = (
    "docs/design/workflow_lisp_transportable_value_type.md"
)
TRANSPORTABLE_VALUE_PLAN_PATH = (
    "docs/plans/2026-07-26-workflow-lisp-transportable-value-implementation-plan.md"
)
PROMPT_OUTPUT_POSITIONS_PLAN_PATH = (
    "docs/plans/2026-07-26-workflow-lisp-prompt-output-positions-implementation-plan.md"
)
PROMPT_IDENTITY_DESIGN_PATH = (
    "docs/design/workflow_lisp_prompt_identity_diagnostics.md"
)
PROMPT_IDENTITY_PLAN_PATH = (
    "docs/plans/2026-07-27-workflow-lisp-prompt-identity-diagnostics-implementation-plan.md"
)
JUDGMENT_VIEWS_DESIGN_PATH = (
    "docs/design/workflow_lisp_judgment_views.md"
)
JUDGMENT_VIEWS_PLAN_PATH = (
    "docs/plans/2026-07-29-workflow-lisp-judgment-views-implementation-plan.md"
)
PHASED_CONTRACT_DELIVERY_DESIGN_PATH = (
    "docs/design/workflow_lisp_phased_contract_delivery.md"
)
PHASED_CONTRACT_DELIVERY_PLAN_PATH = (
    "docs/plans/2026-07-27-workflow-lisp-phased-contract-delivery-implementation-plan.md"
)
LANGUAGE_SERVER_L1_PLAN_PATH = (
    "docs/plans/2026-07-26-workflow-lisp-language-server-l1-implementation-plan.md"
)
LANGUAGE_SERVER_L2_PLAN_PATH = (
    "docs/plans/2026-07-27-workflow-lisp-language-server-l2-implementation-plan.md"
)
LANGUAGE_SERVER_L3_PLAN_PATH = (
    "docs/plans/2026-07-28-workflow-lisp-language-server-l3-per-source-entry-selection-implementation-plan.md"
)
LANGUAGE_SERVER_L4_PLAN_PATH = (
    "docs/plans/2026-07-28-workflow-lisp-language-server-l4-diagnostic-lifecycle-progress-implementation-plan.md"
)
LANGUAGE_SERVER_L5_PLAN_PATH = (
    "docs/plans/2026-07-27-workflow-lisp-l5-authored-reference-navigation-implementation-plan.md"
)
EVOLUTION_FOLLOW_ON_ROADMAP_PATH = (
    "docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md"
)
E0_DIRECT_CONTROL_PLAN_PATH = (
    "docs/plans/2026-07-31-workflow-lisp-e0-direct-control-component-plan.md"
)
TRIAL_RUNS_DESIGN_PATH = "docs/design/workflow_lisp_trial_runs.md"
TYPED_PROGRAM_GATES_DESIGN_PATH = (
    "docs/design/workflow_lisp_typed_program_gates.md"
)
LEAN_PILOT_DESIGN_PATH = (
    "docs/superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md"
)
LEAN_PILOT_IMPLEMENTATION_PLAN_PATH = (
    "docs/superpowers/plans/2026-07-26-orc-effectiveness-lean-pilot.md"
)
LEAN_PILOT_READINESS_AMENDMENT_PATH = (
    "docs/plans/2026-07-27-orc-effectiveness-lean-pilot-task7-readiness-amendment.md"
)
LEAN_PILOT_INCIDENT_RECOVERY_PATH = (
    "docs/plans/2026-07-27-lean-pilot-a1-v5-review-citation-incident-recovery.md"
)
LEAN_PILOT_REPORT_PATH = (
    "docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md"
)
LEAN_PILOT_FINAL_REVIEW_PATH = (
    "artifacts/review/lean-pilot-a1-v7-final-evidence-review.md"
)
LEAN_PILOT_OWNER_DECISION_PATH = (
    "docs/reports/2026-07-31-orc-effectiveness-lean-pilot-owner-decision.md"
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
TASK8_BASELINE_REPLAY_PATH = (
    "docs/plans/evidence/procedure-first-migration-waves/"
    "task8-baseline-replay/adjudication.json"
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
FINAL_YAML_HOLDOUT_PATHS = (
    "workflows/examples/non_progress_step_back_demo.yaml",
    "tests/test_workflow_non_progress_step_back_demo.py",
    "workflows/library/scripts/write_workflow_non_progress_demo_inputs.py",
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

_TASK8_EXPECTED_PROVENANCE = [
    (
        "835f092107d583338611250a91a98bd2a254d6ce",
        "a6cce8de5b972180e6b1f6fd3f9370db2f87add1",
        4101,
    ),
    (
        "218c475303aa11507f643819e88e74090dc5ecec",
        "6f7332cbe066b5b323c8d39a346e7d0fe09e6e11",
        4115,
    ),
    (
        "b017203c398c212751e605fb34706920a022fd80",
        "9e7115f70d138d1f74fca557b4a211818a76819d",
        4137,
    ),
    (
        "a5529b6870caac3178833e75934b3211378795b1",
        "1c54f56f3f5779c2599b8d44beb76af498996a80",
        4141,
    ),
]
_TASK8_EXPECTED_CLAIMS_NOT_MADE = [
    "This adjudication does not claim that the broad test suite passes.",
    (
        "This adjudication does not claim exact normalized-log digest equality "
        "for the two logger-location-only rows."
    ),
    (
        "This adjudication does not classify any failure as caused, fixed, or "
        "made acceptable by the migration wave."
    ),
    (
        "This adjudication does not authorize editing, refreshing, or replacing "
        "the accepted baseline, correction artifact, or normalizer."
    ),
    (
        "This adjudication does not authorize any workflow, runtime, run-root, "
        "or external-state mutation."
    ),
    (
        "This adjudication does not advance the roadmap selector or authorize "
        "Stage 6; independent Task 8 reviews remain required."
    ),
    (
        "The pre-evidence dirty-scope record identifies coexistence and ownership "
        "boundaries; it does not adopt excluded user changes into this task."
    ),
]
_TASK8_EXPECTED_DIRTY_SCOPE = {
    "docs/design/workflow_lisp_parametric_type_system.md": (
        "add7d2d75b8189ef95a1e2933cd6190f27278b36433e7e6a23b62754989bf3bd",
        "task8_pre_routing_evidence",
    ),
    "docs/lisp_workflow_drafting_guide.md": (
        "3bc54613e33cb72e88553ced4c985a5777e8c99c7f16892b8e87f2da109c6bd8",
        "task8_pre_routing_evidence",
    ),
    "docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md": (
        "9db000b1889c07156ccbf69cadae8a7cc3ea3993275f13e982d74778759b2684",
        "pre_existing_user_change_excluded",
    ),
    "docs/plans/2026-07-01-workflow-audit-tier-fixes.md": (
        "0e59fdcd45625f7f6b5985cb6a86692547e4a6b8d7c2a3335a809043c983cde3",
        "pre_existing_user_change_excluded",
    ),
    "docs/plans/2026-07-13-procedure-first-migration-waves-plan.md": (
        "bedb2a8fa89226cb1004ee6e9ca74c1b2666682a2d197c287ef6699bb6a13ec9",
        "task8_pre_routing_evidence",
    ),
    "docs/plans/2026-07-13-procedure-first-reuse-inventory.md": (
        "b9a01585d8ca71d4665f273ed67fcc1074aa9faa0bef7e06bfac03b5ea805c9d",
        "task8_pre_routing_evidence",
    ),
    "docs/plans/2026-07-16-yaml-retirement-handoff-plan.md": (
        "b7247849c19a917109ca88a037dbeeb9e86e0cad877fc7d578afe721a4bd7ad2",
        "task8_pre_routing_evidence",
    ),
    (
        "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/"
        "remaining-neurips-migration-experiment/"
        "migration_experiment_recommendation_report.md"
    ): (
        "95ca608f11d58953ed39ca42881c18911f34c47b85481f391dddc75e957059a6",
        "pre_existing_user_change_excluded",
    ),
    "state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt": (
        "6ba015e073855b2c33aa7e6220fb7148bb528fd9fc0215b670c0411d8a1106e5",
        "pre_existing_user_change_excluded",
    ),
    "tests/test_workflow_lisp_drain_roadmap_routing.py": (
        "03df4df121f3a46a02735cb429b8d44ebe122a7e33c6b953f3e9ae58c630a906",
        "task8_pre_routing_evidence",
    ),
    "tests/test_workflow_non_progress_step_back_demo.py": (
        "ff8cf3f6d14136a2a93eb20da09841623d7cf8de4fb742fe65461fc06b20e46c",
        "pre_existing_user_change_excluded",
    ),
    "workflows/examples/non_progress_step_back_demo.yaml": (
        "8887b2c8d6d645cd5aed94a7b6121fdfebdae7dba25dd5105a8071bd0554fc25",
        "pre_existing_user_change_excluded",
    ),
    "workflows/library/prompts/workflow_step_back/diagnose_non_progress.md": (
        "56cc78c3f6c96fa4fe9945c14e7145ea66aab51a8e999c7e5d730b696b58fe06",
        "pre_existing_user_change_excluded",
    ),
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _assert_exact_keys(value: dict[str, object], expected: set[str]) -> None:
    assert set(value) == expected


def _git_bytes(*args: str, check: bool = True) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check:
        assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return result.stdout


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def _assert_capture_point_precedes_current_head(
    capture_commit: str,
    current_head: str,
    *,
    is_ancestor=_git_is_ancestor,
) -> None:
    assert is_ancestor(capture_commit, current_head)


def _assert_task8_baseline_replay_contract(
    replay: dict[str, object],
    *,
    raw_overrides: dict[str, bytes] | None = None,
) -> None:
    _assert_exact_keys(
        replay,
        {
            "schema",
            "captured_at",
            "repository",
            "pre_evidence_dirty_scope",
            "authorities",
            "provenance",
            "summary",
            "failures",
            "claims_not_made",
        },
    )
    assert replay["schema"] == "procedure_first_migration_wave_baseline_replay.v1"
    repository = replay["repository"]
    _assert_exact_keys(
        repository,
        {
            "head_commit",
            "head_tree",
            "task_1_wave_start_commit",
            "task_1_wave_start_tree",
            "inventory_source_commit",
            "inventory_source_tree",
        },
    )
    assert repository == {
        "head_commit": "7e6adc367a6a16745b5334b2ffc05795f061141d",
        "head_tree": "f0cf970830624c6e6a79ab5c5e8d617d75883072",
        "task_1_wave_start_commit": "4983afff66ba87f42b879f86181b4d4be0563ddf",
        "task_1_wave_start_tree": "7dafec183ebfd8c8d15ae9a535cb7637529232e8",
        "inventory_source_commit": "db9889937a895d67810dee1ea0b1b53552d30eca",
        "inventory_source_tree": "c885d5a3ef05bb629485ca12323200ece24eeeca",
    }
    assert (
        _git_bytes("rev-parse", f"{repository['head_commit']}^{{tree}}")
        .decode()
        .strip()
        == repository["head_tree"]
    )
    _assert_capture_point_precedes_current_head(repository["head_commit"], "HEAD")
    for commit_key, tree_key in (
        ("task_1_wave_start_commit", "task_1_wave_start_tree"),
        ("inventory_source_commit", "inventory_source_tree"),
    ):
        assert (
            _git_bytes("rev-parse", f"{repository[commit_key]}^{{tree}}").decode().strip()
            == repository[tree_key]
        )

    dirty_scope = replay["pre_evidence_dirty_scope"]
    _assert_exact_keys(dirty_scope, {"capture_point", "entries"})
    dirty_entries = dirty_scope["entries"]
    assert len(dirty_entries) == len(_TASK8_EXPECTED_DIRTY_SCOPE)
    for entry in dirty_entries:
        _assert_exact_keys(entry, {"status", "path", "sha256", "scope"})
    assert {
        entry["path"]: (entry["sha256"], entry["scope"])
        for entry in dirty_entries
    } == _TASK8_EXPECTED_DIRTY_SCOPE
    assert all(entry["status"] == "M" for entry in dirty_entries)
    assert all(re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) for entry in dirty_entries)
    assert {entry["scope"] for entry in dirty_entries} == {
        "task8_pre_routing_evidence",
        "pre_existing_user_change_excluded",
    }

    authorities = replay["authorities"]
    _assert_exact_keys(authorities, {"baseline", "correction", "normalizer"})
    _assert_exact_keys(
        authorities["baseline"],
        {
            "path",
            "capture_commit",
            "captured_repository_commit",
            "current_file_commit",
            "current_sha256",
        },
    )
    _assert_exact_keys(
        authorities["correction"],
        {
            "path",
            "accepted_projection_commit",
            "current_file_commit",
            "current_sha256",
        },
    )
    _assert_exact_keys(
        authorities["normalizer"],
        {
            "path",
            "implementation_commit",
            "current_file_commit",
            "implementation_symbol",
            "pinned_sha256",
            "current_sha256",
            "status",
        },
    )
    authority_paths = {
        "baseline": "docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline.json",
        "correction": "docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json",
        "normalizer": "tests/workflow_lisp_procedure_identity.py",
    }
    for name, path in authority_paths.items():
        authority = authorities[name]
        assert authority["path"] == path
        current = (REPO_ROOT / path).read_bytes()
        assert authority["current_sha256"] == _sha256_bytes(current)
        committed = _git_bytes("show", f"{authority['current_file_commit']}:{path}")
        assert current == committed
    normalizer = authorities["normalizer"]
    assert authorities["baseline"]["current_file_commit"] == "50f78791320c540181946fb3a29dce355b19fed3"
    assert authorities["correction"]["current_file_commit"] == "b7212487764bda8ff93dc995c4ca8e1a6eec54ee"
    assert normalizer["implementation_commit"] == "ffd4503de7d40dbbadb388655adce4e140a516a0"
    assert normalizer["current_file_commit"] == normalizer["implementation_commit"]
    assert normalizer["implementation_symbol"] == "normalize_procedure_prerequisite_failure_log"
    assert normalizer["pinned_sha256"] == normalizer["current_sha256"]
    assert normalizer["status"] == "unchanged"

    correction = json.loads((REPO_ROOT / authority_paths["correction"]).read_text(encoding="utf-8"))
    accepted_rows = {
        row["nodeid"]: row for row in correction["failures"][:6]
    }
    rows = replay["failures"]
    assert len(rows) == 6
    assert [row["nodeid"] for row in rows] == list(accepted_rows)
    raw_overrides = raw_overrides or {}
    seen_paths: set[str] = set()
    exact_count = 0
    drift_count = 0
    for row in rows:
        base_keys = {
            "nodeid",
            "category",
            "normalized_failure_signature",
            "command",
            "exit_code",
            "raw_log",
            "normalized_sha256",
            "accepted_baseline_normalized_sha256",
            "disposition",
        }
        expected_row_keys = (
            base_keys | {"normalized_diff"}
            if row["disposition"] == "logger_location_only_drift"
            else base_keys
        )
        _assert_exact_keys(row, expected_row_keys)
        accepted = accepted_rows[row["nodeid"]]
        assert row["category"] == accepted["category"] == "established_unrelated"
        assert row["normalized_failure_signature"] == accepted["normalized_failure_signature"]
        assert row["command"] == f"pytest -q {row['nodeid']}"
        assert row["exit_code"] == 1
        assert row["accepted_baseline_normalized_sha256"] == accepted["corrected_normalized_failure_sha256"]

        raw_contract = row["raw_log"]
        _assert_exact_keys(raw_contract, {"path", "bytes", "sha256"})
        path = raw_contract["path"]
        assert path.startswith(
            "docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/"
        )
        assert path not in seen_paths
        seen_paths.add(path)
        raw = raw_overrides.get(path, (REPO_ROOT / path).read_bytes())
        assert raw_contract["bytes"] == len(raw)
        assert raw_contract["sha256"] == _sha256_bytes(raw)
        normalized = normalize_procedure_prerequisite_failure_log(
            raw.decode("utf-8"), repo_root=REPO_ROOT
        )
        normalized_sha = _sha256_bytes(normalized.encode("utf-8"))
        assert row["normalized_sha256"] == normalized_sha

        if row["disposition"] == "exact_match":
            exact_count += 1
            assert "normalized_diff" not in row
            assert normalized_sha == row["accepted_baseline_normalized_sha256"]
            continue

        assert row["disposition"] == "logger_location_only_drift"
        drift_count += 1
        diff = row["normalized_diff"]
        _assert_exact_keys(
            diff,
            {
                "from_locator",
                "to_locator",
                "changed_line_count",
                "all_other_normalized_lines_equal",
                "line_changes",
            },
        )
        for line_change in diff["line_changes"]:
            _assert_exact_keys(line_change, {"before", "after"})
        assert diff["from_locator"] == "executor.py:4027"
        assert diff["to_locator"] == "executor.py:4141"
        assert diff["all_other_normalized_lines_equal"] is True
        changed_lines = [
            line for line in normalized.splitlines() if diff["to_locator"] in line
        ]
        assert diff["changed_line_count"] == len(changed_lines) == len(diff["line_changes"])
        assert diff["line_changes"] == [
            {
                "before": line.replace(diff["to_locator"], diff["from_locator"]),
                "after": line,
            }
            for line in changed_lines
        ]
        locator_reverted = normalized.replace(diff["to_locator"], diff["from_locator"])
        assert _sha256_bytes(locator_reverted.encode("utf-8")) == row["accepted_baseline_normalized_sha256"]

    _assert_exact_keys(
        replay["summary"],
        {
            "selected_failure_count",
            "exact_match_count",
            "logger_location_only_drift_count",
            "unexpected_failure_count",
        },
    )
    assert replay["summary"] == {
        "selected_failure_count": 6,
        "exact_match_count": exact_count,
        "logger_location_only_drift_count": drift_count,
        "unexpected_failure_count": 0,
    }
    assert (exact_count, drift_count) == (4, 2)
    provenance = replay["provenance"]
    _assert_exact_keys(
        provenance, {"finding", "pre_wave_commits", "ancestry_contract"}
    )
    assert provenance["finding"] == (
        "The logger-location movement predates the procedure-first migration wave."
    )
    for row in provenance["pre_wave_commits"]:
        _assert_exact_keys(
            row, {"commit", "tree", "executor_logger_line_after_commit"}
        )
    assert [
        (row["commit"], row["tree"], row["executor_logger_line_after_commit"])
        for row in provenance["pre_wave_commits"]
    ] == _TASK8_EXPECTED_PROVENANCE
    assert provenance["ancestry_contract"] == (
        "The final provenance commit must be an ancestor of task_1_wave_start_commit."
    )
    for row in provenance["pre_wave_commits"]:
        assert _git_bytes("rev-parse", f"{row['commit']}^{{tree}}").decode().strip() == row["tree"]
        executor_source = _git_bytes(
            "show", f"{row['commit']}:orchestrator/workflow/executor.py"
        ).decode("utf-8")
        logger_lines = [
            line_number
            for line_number, line in enumerate(executor_source.splitlines(), start=1)
            if "logger.error(f\"Step '{step_name}' failed with exit code {exit_code}. \"" in line
        ]
        assert logger_lines == [row["executor_logger_line_after_commit"]]
        ancestor = subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                row["commit"],
                repository["task_1_wave_start_commit"],
            ],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert ancestor.returncode == 0, ancestor.stderr.decode(
            "utf-8", errors="replace"
        )
    assert replay["claims_not_made"] == _TASK8_EXPECTED_CLAIMS_NOT_MADE
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


def _markdown_heading_section(document: str, heading: str) -> str:
    section = document.split(heading, 1)[1]
    return section.split("\n### ", 1)[0]


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
    migration_disposition = _markdown_table_row(
        sequence_path,
        "2026-07-13-procedure-first-migration-waves-plan.md",
    )
    yaml_disposition = _markdown_table_row(
        sequence_path,
        "2026-07-07-yaml-retirement-program.md",
    )
    provider_live_binding_disposition = _markdown_table_row(
        sequence_path,
        "2026-07-23-provider-live-binding-implementation-plan.md",
    )
    return {
        "roadmap disposition": "\n".join(
            (
                migration_disposition,
                yaml_disposition,
                provider_live_binding_disposition,
            )
        ),
        "roadmap current routing": _procedure_sequence_current_routing(),
        "roadmap Stage 5 selector": sequence.split(
            "### Stage 5: Implement Procedure-First Reuse In Waves", 1
        )[1].split("### Stage 6: Resume YAML Retirement", 1)[0],
    }


def _assert_stage_7_v1_landed_and_v1_1_routed(
    surface: str,
    label: str,
) -> None:
    normalized = _normalized_routing_text(surface)
    assert "4d4f05c7" in normalized, label
    assert re.search(
        r"\bstage 7\b.{0,180}\bv1\b.{0,120}\b(?:implement|complet|land|clos)\w*\b"
        r"|\bprovider (?:live binding|supervision) v1\b.{0,180}"
        r"\b(?:implement|complet|land|clos)\w*\b",
        normalized,
    ), label
    assert "v1.1" in normalized, label
    assert (
        "before stage 8" in normalized
        or "before the language server" in normalized
        or "before or alongside stage 8 planning" in normalized
        or "remains next" in normalized
        or "stage 8 is the next numbered stage" in normalized
        or re.search(r"\bstage 8\b.{0,40}\bactive\b", normalized)
        or re.search(r"\bstage 8\b.{0,80}\bcomplete\w*\b", normalized)
        or "next stage selection remain owned by the execution sequence roadmap"
        in normalized
    ), label
    assert "stage 7 has not started" not in normalized, label
    assert "awaits an owner scheduled design review" not in normalized, label
    assert "implementation remains gated on a reviewed" not in normalized, label


def _assert_migration_wave_complete_and_yaml_stage_closed(
    surface: str,
    label: str,
) -> None:
    normalized = _normalized_routing_text(surface)
    canonical = _canonical_routing_paths(surface)
    assert canonical.count(CURRENT_SELECTOR_PATH) == 1, label
    assert "historical complete" in normalized or re.search(
        r"\bmigration wave\b.{0,80}\bcomplete\w*\b",
        normalized,
    ), label
    assert "0 procedure candidates" in normalized, label
    assert "32 effect adapters" in normalized, label
    assert "63 legacy retire" in normalized, label
    assert re.search(r"\b(?:thirteen|13)\b.{0,40}\bpublic\b", normalized), label
    assert re.search(r"\b(?:one|1)\b.{0,40}\bhistory\b", normalized), label
    assert "7e6adc36" in normalized, label
    assert "565" in normalized and "6 skipped" in normalized, label
    assert "36" in normalized and "routing" in normalized, label
    assert "4992" in normalized and "17 skipped" in normalized, label
    assert re.search(
        r"\b(?:six|6)\b.{0,30}\bestablished unrelated\b",
        normalized,
    ), label
    assert re.search(r"\b(?:four|4)\b.{0,20}\bexact\b", normalized), label
    assert re.search(
        r"\b(?:two|2)\b.{0,30}\blogger location only\b",
        normalized,
    ), label
    assert re.search(
        r"\bstage 6\b.{0,160}\bcomplete\w*\b"
        r"|\byaml retirement\b.{0,160}\btask 7\b.{0,100}\bcomplete\w*\b",
        normalized,
    ), label
    assert "orc only" in normalized, label
    assert "focused" in normalized and "smoke" in normalized, label
    assert (
        "final scoped broad" in normalized
        or "final broad comparison" in normalized
        or "scoped broad comparison" in normalized
        or ("6386 passed" in normalized and "15 skipped" in normalized)
    ), label
    assert (
        "independent review" in normalized
        or ("pass" in normalized and "approved" in normalized)
    ), label
    _assert_stage_7_v1_landed_and_v1_1_routed(surface, label)
    for stale_task in range(1, 8):
        assert re.search(
            rf"\byaml retirement\b[^.;]{{0,120}}\btask {stale_task}\b"
            rf"[^.;]{{0,40}}\b(?:is|remains) current\b"
            rf"|\bcurrent selector\b[^.;]{{0,120}}\byaml retirement\b"
            rf"[^.;]{{0,80}}\btask {stale_task}\b",
            normalized,
        ) is None, (label, stale_task)
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


def test_procedure_first_status_surfaces_close_stage_6_and_route_stage_7_v1_1() -> None:
    capability_matrix_path = REPO_ROOT / "docs" / "capability_status_matrix.md"
    sequence = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8")
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
        assert "migration wave" in normalized and "complete" in normalized, label
        assert re.search(
            r"\bstage 6\b.{0,160}\bcomplete\w*\b"
            r"|\byaml retirement\b.{0,160}\btask 7\b.{0,100}\bcomplete\w*\b",
            normalized,
        ), label
        _assert_stage_7_v1_landed_and_v1_1_routed(surface, label)
        assert "migration waves remain blocked" not in normalized, label
        assert "runtime hardening remains pending" not in normalized, label

    yaml_row = _markdown_table_row(capability_matrix_path, "YAML DSL v2.x")
    normalized_yaml_row = _normalized_routing_text(yaml_row)
    assert "| Retired |" in yaml_row
    assert "all five content addressed queues are drained" in normalized_yaml_row
    assert "fresh run is orc only" in normalized_yaml_row
    assert "loader and project pyyaml dependency are removed" in normalized_yaml_row
    assert "task 7" in normalized_yaml_row and "complete" in normalized_yaml_row
    assert "1,020 passed" in normalized_yaml_row
    assert "5 skipped" in normalized_yaml_row
    assert "6,386 passed" in normalized_yaml_row
    assert "15 skipped" in normalized_yaml_row
    assert "four exact" in normalized_yaml_row and "zero new" in normalized_yaml_row
    assert "d9baa120" in normalized_yaml_row
    assert "pass" in normalized_yaml_row
    assert "approved" in normalized_yaml_row

    stage_6 = _normalized_routing_text(
        sequence.split("### Stage 6: Resume YAML Retirement", 1)[1].split(
            "### Stage 7:", 1
        )[0]
    )
    assert "status: complete" in stage_6
    assert "task 7" in stage_6 and "complete" in stage_6
    assert "orc only" in stage_6
    assert "1,020" in stage_6 and "5 skipped" in stage_6
    assert "scoped broad" in stage_6 and "zero new" in stage_6
    assert "d9baa120" in stage_6
    assert "pass" in stage_6 and "approved" in stage_6


def test_list_traversal_interstage_and_stage_8_closeout_routing() -> None:
    sequence = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8")
    live_binding_plan = (REPO_ROOT / PROVIDER_LIVE_BINDING_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    peer_plan = (REPO_ROOT / PROVIDER_PEER_MESSAGING_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    stage_7, after_stage_7 = sequence.split(
        "### Stage 7: Deliver Provider Live Binding", 1
    )[1].split("### Stage 8: Deliver The `.orc` Language Server", 1)
    interstage = stage_7.split("### Selected Interstage:", 1)[1]
    normalized_stage_7 = _normalized_routing_text(stage_7)
    normalized_interstage = _normalized_routing_text(interstage)

    assert "b08c04a6" in normalized_stage_7
    assert "tasks 1 11" in normalized_stage_7
    assert "task 12" in normalized_stage_7
    assert "continues with that plan s implementation" not in normalized_stage_7
    assert PURE_LIST_TRAVERSAL_DESIGN_PATH in interstage
    assert "bef65fdf" in normalized_interstage
    assert "independent design review" in normalized_interstage
    assert "one small implementation plan" in normalized_interstage
    assert "principle 29" in normalized_interstage
    assert "current status: complete" in normalized_interstage
    assert "interstage is complete" in normalized_interstage
    assert "stage 8 is complete" in normalized_interstage
    assert PURE_LIST_TRAVERSAL_PLAN_PATH in interstage
    assert after_stage_7.startswith("\n\nStage 8 is the final stage")
    normalized_stage_8 = _normalized_routing_text(after_stage_7)
    assert "current status: complete" in normalized_stage_8
    assert "gate s8" in normalized_stage_8
    assert "complete" in normalized_stage_8
    assert "condition 3 is satisfied" in normalized_stage_8
    assert "condition 3 is the remaining execution boundary" not in (
        normalized_stage_8
    )
    assert LANGUAGE_SERVER_PLAN_PATH in after_stage_7

    normalized_live_plan = _normalized_routing_text(live_binding_plan)
    assert "v1 handoff is complete" in normalized_live_plan
    assert "b08c04a6" in normalized_live_plan
    assert (
        "- [x] Immediately draft/review/execute its focused Stage-7 plan delta"
        in live_binding_plan
    )

    task_12 = peer_plan.split("## Task 12:", 1)[1].split(
        "## Completion Gate", 1
    )[0]
    normalized_task_12 = _normalized_routing_text(task_12)
    assert "- [x] **Step 1: Update normative and authoring contracts**" in task_12
    assert "- [x] **Step 2: Update routing and Stage 7 status**" in task_12
    assert "five named security modules" in normalized_task_12
    assert "before or alongside stage 8 planning" in normalized_task_12
    assert "- [x] **Step 3:" in task_12
    assert "- [x] **Step 4:" in task_12
    assert "- [x] **Step 5:" in task_12
    assert "7,479 passed" in task_12
    assert "zero new failures" in normalized_task_12
    assert "combined real v1/v1.1 smoke passed all `6` cases" in task_12
    assert "TASK12_FINAL_SPEC_APPROVED" in task_12
    assert "TASK12_FINAL_QUALITY_APPROVED" in task_12
    assert "- [x] **Step 6:" in task_12
    assert "- [x] **Step 7:" in task_12
    assert "- [x] **Step 8:" in task_12
    assert "**Status:** Complete." in peer_plan
    assert "**Gate status:** complete." in stage_7


def test_list_traversal_closeout_status_is_consistent_across_doc_routes() -> None:
    design = (REPO_ROOT / PURE_LIST_TRAVERSAL_DESIGN_PATH).read_text(
        encoding="utf-8"
    )
    plan = (REPO_ROOT / PURE_LIST_TRAVERSAL_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    language_server_plan = (REPO_ROOT / LANGUAGE_SERVER_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    design_router_path = REPO_ROOT / "docs/design/README.md"
    capability_matrix_path = REPO_ROOT / "docs/capability_status_matrix.md"
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")

    assert "status: implemented" in _normalized_routing_text(
        "\n".join(design.splitlines()[:30])
    )
    assert "status: complete" in _normalized_routing_text(
        "\n".join(plan.splitlines()[:45])
    )
    design_row = _markdown_table_row(
        design_router_path,
        "workflow_lisp_pure_list_traversal.md",
    )
    assert "| Implemented |" in design_row
    capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp target-2.18 bounded list traversal",
    )
    assert "| Implemented |" in capability_row
    list_index = index.split(
        "### [Workflow Lisp Pure List Traversal]", 1
    )[1].split("### [Workflow Lisp Language Server]", 1)[0]
    assert "implemented target 2.18" in _normalized_routing_text(list_index)
    assert "completed seven task" in _normalized_routing_text(list_index)
    normalized_language_server_plan = _normalized_routing_text(
        "\n".join(language_server_plan.splitlines()[:45])
    )
    assert (
        "status: closing verification" in normalized_language_server_plan
        or "status: complete" in normalized_language_server_plan
    )
    assert "after the selected list traversal interstage closes" not in (
        normalized_language_server_plan
    )


def test_stage_8_language_server_closeout_status_is_consistent() -> None:
    design = (
        REPO_ROOT / "docs/design/workflow_lisp_language_server.md"
    ).read_text(encoding="utf-8")
    plan = (REPO_ROOT / LANGUAGE_SERVER_PLAN_PATH).read_text(encoding="utf-8")
    sequence = (
        REPO_ROOT
        / "docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")
    setup = (
        REPO_ROOT / "docs/workflow_lisp_language_server_setup.md"
    ).read_text(encoding="utf-8")

    assert "status: implemented" in _normalized_routing_text(
        "\n".join(design.splitlines()[:30])
    )
    normalized_plan_status = _normalized_routing_text(
        "\n".join(plan.splitlines()[:45])
    )
    assert (
        "status: closing verification" in normalized_plan_status
        or "status: complete" in normalized_plan_status
    )
    assert "| Implemented |" in _markdown_table_row(
        REPO_ROOT / "docs/design/README.md",
        "workflow_lisp_language_server.md",
    )
    assert "| Implemented |" in _markdown_table_row(
        REPO_ROOT / "docs/capability_status_matrix.md",
        "Workflow Lisp language server v1",
    )

    language_server_index = index.split(
        "### [Workflow Lisp Language Server]", 1
    )[1].split("### [Workflow Lisp Language Server Implementation Plan]", 1)[0]
    normalized_index = _normalized_routing_text(language_server_index)
    assert "implemented" in normalized_index
    assert "workflow_lisp_language_server_setup.md" in language_server_index
    assert "python -m orchestrator.lsp" in setup

    stage_8 = sequence.split(
        "### Stage 8: Deliver The `.orc` Language Server", 1
    )[1].split("### Post-Stage-8 Successor Handoff", 1)[0]
    normalized_stage_8 = _normalized_routing_text(stage_8)
    assert "current status: complete" in normalized_stage_8
    assert "gate s8" in normalized_stage_8
    assert "complete" in normalized_stage_8

    successor = sequence.split(
        "### Post-Stage-8 Successor Handoff", 1
    )[1].split("## Concurrency Rules", 1)[0]
    normalized_successor = _normalized_routing_text(successor)
    assert "not additional stages" in normalized_successor
    assert "none is selected by listing" in normalized_successor
    assert "parked" in normalized_successor
    assert "not a selector" in normalized_successor


def test_lean_pilot_a1_v7_closure_routes_exact_evidence_and_narrow_owner_handoff() -> None:
    design = (REPO_ROOT / LEAN_PILOT_DESIGN_PATH).read_text(encoding="utf-8")
    implementation_plan = (
        REPO_ROOT / LEAN_PILOT_IMPLEMENTATION_PLAN_PATH
    ).read_text(encoding="utf-8")
    readiness = (REPO_ROOT / LEAN_PILOT_READINESS_AMENDMENT_PATH).read_text(
        encoding="utf-8"
    )
    recovery = (REPO_ROOT / LEAN_PILOT_INCIDENT_RECOVERY_PATH).read_text(
        encoding="utf-8"
    )
    report_path = REPO_ROOT / LEAN_PILOT_REPORT_PATH
    report = report_path.read_text(encoding="utf-8")
    final_review_path = REPO_ROOT / LEAN_PILOT_FINAL_REVIEW_PATH
    final_review = final_review_path.read_text(encoding="utf-8")
    owner_decision = (REPO_ROOT / LEAN_PILOT_OWNER_DECISION_PATH).read_text(
        encoding="utf-8"
    )
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")
    capability_row = _markdown_table_row(
        REPO_ROOT / CAPABILITY_STATUS_MATRIX_PATH,
        "| `.orc` effectiveness lean-pilot apparatus |",
    )

    lock_digest = (
        "b8d69ba2f3d2b2e7bc6d9181d776db0b7abacd2035f851cd44be613dac6d8503"
    )
    summary_digest = (
        "153263159d6516d032be83bd8f53954be0ba05b39af58be23d1abdca34085e89"
    )
    report_digest = (
        "f5a0884fc14ee399d3753644180c380387d6a78b60315e2c445daffc1baffc3c"
    )
    review_digest = (
        "c990645c3bfa54e9a1d2b0222272440296ba109685cbdc25cd9bae9db4024d01"
    )

    assert hashlib.sha256(report_path.read_bytes()).hexdigest() == report_digest
    assert (
        hashlib.sha256(final_review_path.read_bytes()).hexdigest()
        == review_digest
    )
    for surface in (
        design,
        implementation_plan,
        readiness,
        recovery,
        final_review,
        owner_decision,
        index,
        capability_row,
    ):
        assert lock_digest in surface
        assert summary_digest in surface

    assert report_digest in design
    assert report_digest in recovery
    assert report_digest in final_review
    assert report_digest in owner_decision
    assert review_digest in owner_decision

    normalized_design = _normalized_routing_text(design)
    assert "status: implemented" in normalized_design
    assert "historical complete" in normalized_design
    assert "direct won 3/3 against orc" in normalized_design
    assert "orc was viable in 1/3" in normalized_design
    assert "no pilot run was resumed or rerun" in normalized_design

    task_7 = implementation_plan.split(
        "## Task 7: Run The Apparatus Smoke And Bounded A1 Pilot",
        1,
    )[1].split("## Completion Definition", 1)[0]
    assert "- [ ]" not in task_7
    assert task_7.count("- [x]") == 8
    assert re.search(r"(?m)^- \[ \]", recovery) is None
    assert recovery.count("- [x]") == 26
    assert "historical complete" in _normalized_routing_text(readiness)
    assert "historical complete" in _normalized_routing_text(recovery)

    assert "Status: `EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED`" in report
    assert "DIRECT_VS_ORC: A=3, B=0" in report
    assert "ORC: viable=1, nonviable=2" in report
    assert "This report is exploratory controlled-task evidence only." in report
    assert "LEAN_PILOT_FINAL_EVIDENCE_APPROVED" in final_review
    assert "four treatment-specific `PROTOCOL_FAILURE`" in final_review
    assert "no pilot attempt was resumed, rerun" in _normalized_routing_text(
        final_review
    )

    normalized_decision = _normalized_routing_text(owner_decision)
    assert "PROCEED_TO_E0_ACTIVATION" in owner_decision
    assert "> dont stop, continue with E asap" in owner_decision
    assert "it is not a claim that the pilot favored .orc" in normalized_decision
    assert "does not automatically authorize e1" in normalized_decision
    assert "no e1+ implementation is selected by this record alone" in (
        normalized_decision
    )

    for path in (
        LEAN_PILOT_DESIGN_PATH,
        LEAN_PILOT_IMPLEMENTATION_PLAN_PATH,
        LEAN_PILOT_READINESS_AMENDMENT_PATH,
        LEAN_PILOT_INCIDENT_RECOVERY_PATH,
        LEAN_PILOT_REPORT_PATH,
        LEAN_PILOT_FINAL_REVIEW_PATH,
        LEAN_PILOT_OWNER_DECISION_PATH,
    ):
        assert Path(path).name in index
    normalized_capability = _normalized_routing_text(capability_row)
    assert "implemented" in normalized_capability
    assert "direct won 3/3 against orc" in normalized_capability
    assert "orc in 1/3" in normalized_capability
    assert "exploratory only" in normalized_capability
    assert "does not automatically select e1+" in normalized_capability


def test_e_series_recovered_designs_route_without_selecting_implementation() -> None:
    roadmap = (REPO_ROOT / EVOLUTION_FOLLOW_ON_ROADMAP_PATH).read_text(
        encoding="utf-8"
    )
    trial = (REPO_ROOT / TRIAL_RUNS_DESIGN_PATH).read_text(encoding="utf-8")
    gates = (REPO_ROOT / TYPED_PROGRAM_GATES_DESIGN_PATH).read_text(
        encoding="utf-8"
    )
    plan = (REPO_ROOT / E0_DIRECT_CONTROL_PLAN_PATH).read_text(encoding="utf-8")
    sequence = (
        REPO_ROOT
        / "docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8")
    design_index = (REPO_ROOT / DESIGN_INDEX_PATH).read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")
    trial_capability = _markdown_table_row(
        REPO_ROOT / CAPABILITY_STATUS_MATRIX_PATH,
        "| Workflow Lisp canonical trial runs (E0-E3 direction) |",
    )
    gates_capability = _markdown_table_row(
        REPO_ROOT / CAPABILITY_STATUS_MATRIX_PATH,
        "| Workflow Lisp typed program gates (C1 companion) |",
    )

    normalized_roadmap = _normalized_routing_text(roadmap)
    normalized_trial = _normalized_routing_text(trial)
    normalized_gates = _normalized_routing_text(gates)
    assert "e_designs_spec_approved" in normalized_roadmap
    assert "e_designs_quality_approved" in normalized_roadmap
    assert "no e implementation is selected yet" in normalized_roadmap
    assert "is proposed for ordered review" in normalized_roadmap
    assert "owner decision handoff is complete" in normalized_roadmap
    assert "creates no effect identity memo key" in normalized_roadmap
    assert "docs/superpowers/plans/2026-07-26-orc-effectiveness-lean-pilot.md" in roadmap

    for tranche, meaning in (
        ("E0", "canonical one-call direct control"),
        ("E1", "pinned-workspace child execution"),
        ("E2", "concurrent trial arms"),
        ("E3", "external gene-bounded controller"),
    ):
        assert f"| {tranche} |" in roadmap
        assert meaning in roadmap
        assert f"| {tranche} |" in trial

    for design_path, content in (
        (TRIAL_RUNS_DESIGN_PATH, trial),
        (TYPED_PROGRAM_GATES_DESIGN_PATH, gates),
    ):
        assert design_path in roadmap
        assert Path(design_path).name in design_index
        assert Path(design_path).name in index
        assert "accepted design" in _normalized_routing_text(content)
        assert "no implementation" in _normalized_routing_text(content)

    assert "not the retired provider interruption quarantine" in normalized_trial
    assert "no effect identity memo key" in normalized_trial
    assert "clone is an exact workspace/output boundary" in normalized_trial
    assert "never a sandbox" in normalized_trial
    assert "principle 30" in normalized_trial
    assert "run/resume explicitly excludes lean pilot attempts" in normalized_gates
    assert "no cross run memo" in normalized_gates
    assert "principle 30" in normalized_gates
    assert "| Designed |" in trial_capability
    assert "| Designed |" in gates_capability
    assert "No current syntax/runtime capability may be inferred" in gates_capability
    assert Path(E0_DIRECT_CONTROL_PLAN_PATH).name in roadmap
    assert Path(E0_DIRECT_CONTROL_PLAN_PATH).name in design_index
    assert Path(E0_DIRECT_CONTROL_PLAN_PATH).name in index
    assert Path(E0_DIRECT_CONTROL_PLAN_PATH).name in sequence
    assert "**Status:** proposed, implementation unselected." in plan
    assert "does not select e1" in _normalized_routing_text(plan)
    assert "no e implementation is selected" in _normalized_routing_text(
        trial_capability
    )


def test_post_stage_8_successor_selects_value_then_prompt_calculus() -> None:
    sequence_path = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    )
    sequence = sequence_path.read_text(encoding="utf-8")
    successor = (REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH).read_text(
        encoding="utf-8"
    )
    value_design = (REPO_ROOT / TRANSPORTABLE_VALUE_DESIGN_PATH).read_text(
        encoding="utf-8"
    )
    value_plan = (REPO_ROOT / TRANSPORTABLE_VALUE_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    q2_plan = (REPO_ROOT / PROMPT_OUTPUT_POSITIONS_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    q3_design = (REPO_ROOT / PROMPT_IDENTITY_DESIGN_PATH).read_text(
        encoding="utf-8"
    )
    q3_plan = (REPO_ROOT / PROMPT_IDENTITY_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    q4_design = (REPO_ROOT / JUDGMENT_VIEWS_DESIGN_PATH).read_text(
        encoding="utf-8"
    )
    q4_plan = (REPO_ROOT / JUDGMENT_VIEWS_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    l1_plan = (REPO_ROOT / LANGUAGE_SERVER_L1_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    l2_plan = (REPO_ROOT / LANGUAGE_SERVER_L2_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    evolution = (REPO_ROOT / EVOLUTION_FOLLOW_ON_ROADMAP_PATH).read_text(
        encoding="utf-8"
    )
    design_router_path = REPO_ROOT / "docs" / "design" / "README.md"
    capability_matrix_path = REPO_ROOT / "docs" / "capability_status_matrix.md"
    index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    route_registry = json.loads(
        (
            REPO_ROOT / "docs" / "workflow_lisp_route_readiness_registry.json"
        ).read_text(encoding="utf-8")
    )

    normalized_successor = _normalized_routing_text(successor)
    assert "status: complete" in normalized_successor
    assert "all q0 q5 and l0 l5 completion gates are satisfied" in (
        normalized_successor
    )
    q0_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "| Q0 |",
    )
    q0_status = _normalized_routing_text(q0_row.rsplit("|", 2)[-2])
    q0_is_closing = q0_status.startswith("closing ")
    q0_is_complete = q0_status.startswith("complete ")
    assert q0_is_closing != q0_is_complete
    assert "active" not in q0_status
    if q0_is_closing:
        assert "pending" in q0_status
    else:
        assert "pending" not in q0_status
    q1_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "| Q1 |",
    )
    q1_status = _normalized_routing_text(q1_row.rsplit("|", 2)[-2])
    assert q1_status.startswith("complete ")
    assert "implementation through af45c4f1" in q1_status
    assert "ordered final reviews accepted" in q1_status
    assert "blocked by q0" not in q1_status
    assert "design review pending" not in normalized_successor
    assert "implementation plan pending" not in normalized_successor
    assert "q1" in normalized_successor and "prompt core" in normalized_successor
    assert "e0" in normalized_successor and "unselected" in normalized_successor
    assert (
        "evolution follow on roadmap is incorporated (2026 07 30) as the "
        "tracked e series program" in normalized_successor
    )
    assert "nothing e is selectable from this roadmap" in normalized_successor
    assert "sequenced after the e program" in normalized_successor
    l0_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "Reliability and diagnostic actionability",
    )
    normalized_l0_row = _normalized_routing_text(l0_row)
    assert "| L0 |" in l0_row
    assert "complete" in normalized_l0_row
    assert "reviewed implementation" in normalized_l0_row
    assert "content keyed pure projection source cache" in normalized_l0_row
    q2_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "| Q2 |",
    )
    normalized_q2_row = _normalized_routing_text(q2_row)
    assert "complete" in normalized_q2_row
    assert "implementation through d0bb9a1d" in normalized_q2_row
    assert "a40b536c" in normalized_q2_row
    assert "4e2c4911" in normalized_q2_row
    assert "ordered final reviews accepted" in normalized_q2_row
    q3_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "| Q3 |",
    )
    normalized_q3_row = _normalized_routing_text(q3_row)
    assert "complete" in normalized_q3_row
    assert "target 2.22 carrier" in normalized_q3_row
    assert "content free five role evidence" in normalized_q3_row
    assert "prelaunch publication" in normalized_q3_row
    assert "compatibility e2e" in normalized_q3_row
    assert "reviewed implementation plan" in normalized_q3_row
    assert Path(PROMPT_IDENTITY_PLAN_PATH).name in q3_row
    assert "no q3 design is accepted" not in normalized_q3_row
    assert "blocked by q2" not in normalized_q3_row
    q4_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "| Q4 |",
    )
    normalized_q4_row = _normalized_routing_text(q4_row)
    assert "q3 complete" in normalized_q4_row
    assert "concrete generic reviewer/panel consumer is bound" in (
        normalized_q4_row
    )
    assert "original design accepted at d7fe4549" in normalized_q4_row
    assert (
        "2026 07 29 workflow lisp judgment views implementation plan.md"
        in normalized_q4_row
    )
    assert "q5 era design amendment accepted at 3c21ceb4" in normalized_q4_row
    assert "reviewed amended plan 0f21636b" in normalized_q4_row
    assert (
        "complete at commit f3335637b90feb0a87ac4c538bafac7704ac0d87"
        in normalized_q4_row
    )
    assert "tree ccec170be8757c9e4fd5ed8ece6f93b04fc03299" in normalized_q4_row
    assert (
        "85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c"
        in normalized_q4_row
    )
    assert "q4_task_9_spec_approved" in normalized_q4_row
    assert "q4_task_9_quality_approved" in normalized_q4_row
    assert "q4_final_spec_approved" in normalized_q4_row
    assert "q4_final_quality_approved" in normalized_q4_row
    assert "postcommit focused control passed 74 tests" in normalized_q4_row
    assert "implemented closure candidate" not in normalized_q4_row
    assert "external task 9 and final ordered reviews" not in normalized_q4_row
    assert "implementation not started" not in normalized_q4_row
    assert "current target 2.23 phased production" in normalized_q4_row
    assert "target 2.23 explicit composed panel sibling" in normalized_q4_row
    assert "frozen target 2.21 compatibility control" in normalized_q4_row
    assert "q5 task 14 and canonical transplant are complete" in normalized_q4_row
    normalized_q4_stage = _normalized_routing_text(
        _markdown_heading_section(
            successor,
            "## Stage Q4: Judgment Views",
        )
    )
    assert "original pre q5 plan at fbcba410" in normalized_q4_stage
    assert "q4_plan_spec_approved then q4_plan_quality_approved" in (
        normalized_q4_stage
    )
    assert "reviewed amended implementation plan at 0f21636b" in (
        normalized_q4_stage
    )
    assert "q4 is complete" in normalized_q4_stage
    assert (
        "1bdb694da1fda43fb0ed71e842cd16e54956b86bb5106aea380a5e17f681c7"
        in normalized_q4_stage
    )
    assert "task 9 focused 643 passed" in normalized_q4_stage
    assert "11,072 passed, 5 failed, 24 skipped, and 33 warnings" in (
        normalized_q4_stage
    )
    assert (
        "closed at commit f3335637b90feb0a87ac4c538bafac7704ac0d87"
        in normalized_q4_stage
    )
    assert "tree ccec170be8757c9e4fd5ed8ece6f93b04fc03299" in normalized_q4_stage
    assert (
        "85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c"
        in normalized_q4_stage
    )
    assert "postcommit focused control passed 74 tests" in normalized_q4_stage
    assert "become the current execution authority only after" not in (
        normalized_q4_stage
    )
    assert "proposed" not in normalized_q4_stage
    assert "must receive ordered plan reviews" not in normalized_q4_stage
    assert "target 2.23 phased production" in normalized_q4_stage
    assert "target 2.23 sibling" in normalized_q4_stage
    assert "explicitly composed" in normalized_q4_stage
    assert "target 2.21" in normalized_q4_stage
    assert "compatibility only control" in normalized_q4_stage
    assert "task 14 closed at 70f4a759, tree fec729cb" in normalized_successor
    assert "remain the q5 closure gate" not in normalized_successor
    assert "q5 now awaits only its task 14 external closure gate" not in (
        normalized_successor
    )
    q4_capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp judgment views Q4",
    )
    normalized_q4_capability_row = _normalized_routing_text(
        q4_capability_row
    )
    assert "| Implemented |" in q4_capability_row
    assert "| Designed |" not in q4_capability_row
    assert "| Planned |" not in q4_capability_row
    assert "original design and q5 era design amendment accepted" in (
        normalized_q4_capability_row
    )
    assert "d7fe4549" in normalized_q4_capability_row
    assert "3c21ceb4" in normalized_q4_capability_row
    assert "reviewed amended plan 0f21636b" in normalized_q4_capability_row
    assert "implementation not started" not in normalized_q4_capability_row
    assert "target 2.23 explicit composed panel sibling" in normalized_q4_capability_row
    assert "current target 2.23 phased" in normalized_q4_capability_row
    assert "frozen target 2.21 control" in normalized_q4_capability_row
    assert "never an import owner" in normalized_q4_capability_row
    normalized_q4_design = _normalized_routing_text(q4_design)
    normalized_q4_plan = _normalized_routing_text(q4_plan)
    assert "adopted consumer binding" in normalized_q4_design
    assert "status: implemented" in normalized_q4_design
    assert "target 2.23 sibling" in normalized_q4_design
    assert ":delivery :composed" in normalized_q4_design
    assert "frozen target 2.21" in normalized_q4_design
    assert "current target 2.23 phased production" in normalized_q4_plan
    assert "target 2.23 ordinary composed panel sibling" in normalized_q4_plan
    assert "frozen target 2.21 compatibility control" in normalized_q4_plan
    panel_route_rows = [
        surface
        for surface in route_registry["surfaces"]
        if surface["path"]
        == "workflows/examples/review_revise_design_docs_judgment_panel.orc"
    ]
    assert len(panel_route_rows) == 1
    [panel_route_row] = panel_route_rows
    assert set(panel_route_row) == {
        "copy_safety",
        "evidence",
        "lowering_route",
        "lowering_schema_version",
        "path",
        "readiness_label",
        "route_label",
        "surface_id",
        "surface_kind",
    }
    assert panel_route_row["surface_id"] == (
        "workflows.examples.review_revise_design_docs_judgment_panel"
    )
    assert panel_route_row["surface_kind"] == "workflow_example"
    assert panel_route_row["copy_safety"] == "preferred_current_guidance"
    assert panel_route_row["lowering_route"] == "wcc_m4"
    assert panel_route_row["lowering_schema_version"] == 2
    assert panel_route_row["readiness_label"] == "leaf_runtime_candidate"
    assert panel_route_row["route_label"] == "wcc_default"
    assert panel_route_row["evidence"] == [
        "tests/test_workflow_lisp_examples.py::"
        "test_review_revise_design_docs_judgment_panel_compiles_from_current_owner",
        "tests/test_workflow_lisp_judgment_views_e2e.py::"
        "test_panel_executes_ordered_reviews_then_one_ineligible_synthesis",
    ]
    assert "reviewed amended plan 0f21636b" in normalized_q4_plan
    assert "plan status: complete" in normalized_q4_plan
    assert "implemented closure candidate" not in normalized_q4_plan
    assert (
        "1bdb694da1fda43fb0ed71e842cd16e54956b86bb5106aea380a5e17f681c7"
        in normalized_q4_plan
    )
    assert "9e18f884" in normalized_q4_plan
    assert "4b400e7a" in normalized_q4_plan
    assert "7b96c547" in normalized_q4_plan
    assert "88af8b91" in normalized_q4_plan
    assert "a3b75d76" in normalized_q4_plan
    assert "4ca9e628" in normalized_q4_plan
    assert "19a77547" in normalized_q4_plan
    assert "6e987e23" in normalized_q4_plan
    assert "187336f7" in normalized_q4_plan
    assert "000bfcfe" in normalized_q4_plan
    assert "0187392f" in normalized_q4_plan
    assert "11,072 passed" in normalized_q4_plan
    assert "- [x] Re-run all Task 1–8 focused selectors." in q4_plan
    assert "- [x] Update docs from designed/planned to implemented" in q4_plan
    assert "- [x] Obtain `Q4_TASK_9_SPEC_APPROVED`." in q4_plan
    assert "- [x] Obtain distinct `Q4_TASK_9_QUALITY_APPROVED`." in q4_plan
    assert "- [x] Obtain ordered `Q4_FINAL_SPEC_APPROVED`." in q4_plan
    assert "- [x] Obtain distinct `Q4_FINAL_QUALITY_APPROVED`." in q4_plan
    assert "- [x] Commit the reviewed closure bytes." in q4_plan
    assert "- [x] Run a fresh postcommit focused control" in q4_plan
    assert "f3335637b90feb0a87ac4c538bafac7704ac0d87" in q4_plan
    assert "ccec170be8757c9e4fd5ed8ece6f93b04fc03299" in q4_plan
    assert (
        "85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c"
        in q4_plan
    )
    assert "the 74 pass postcommit control" in normalized_q4_plan
    assert tuple(
        text.count("`q4_task2_export_compatibility.v1`")
        for text in (q4_design, q4_plan)
    ) == (1, 1)
    normalized_q3_design_status = _normalized_routing_text(
        "\n".join(q3_design.splitlines()[:24])
    )
    assert "status: accepted" in normalized_q3_design_status
    assert "target: dsl 2.22" in normalized_q3_design_status
    assert "q3_design_spec_approved" in normalized_q3_design_status
    assert "q3_design_quality_approved" in normalized_q3_design_status
    assert "fdf16f362f93eae89c05600e6954a118270fe7b7" in q3_design
    q3_design_router_row = _markdown_table_row(
        design_router_path,
        "workflow_lisp_prompt_identity_diagnostics.md",
    )
    normalized_q3_design_router_row = _normalized_routing_text(
        q3_design_router_row
    )
    assert "| Implemented |" in q3_design_router_row
    assert "functional v2" in normalized_q3_design_router_row
    assert "prelaunch publication" in normalized_q3_design_router_row
    assert Path(PROMPT_IDENTITY_PLAN_PATH).name in q3_design_router_row
    q3_capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp prompt identity diagnostics Q3",
    )
    normalized_q3_capability_row = _normalized_routing_text(q3_capability_row)
    assert "| Implemented |" in q3_capability_row
    assert "direct fragment backed target 2.22" in (
        normalized_q3_capability_row
    )
    assert "functional v2" in normalized_q3_capability_row
    assert "fixed order comparison" in normalized_q3_capability_row
    assert Path(PROMPT_IDENTITY_PLAN_PATH).name in q3_capability_row
    normalized_index = _normalized_routing_text(index)
    prompt_identity_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Prompt Identity Diagnostics]",
        )
    )
    assert "implemented target 2.22 q3 design" in prompt_identity_index
    assert "content free" in prompt_identity_index
    assert "direct fragment only" in prompt_identity_index
    assert Path(PROMPT_IDENTITY_PLAN_PATH).name in index
    assert "# Workflow Lisp Prompt Identity And Diagnostics Implementation Plan" in (
        q3_plan
    )
    prompt_calculus = (
        REPO_ROOT / "docs" / "design" / "workflow_lisp_prompt_calculus.md"
    ).read_text(encoding="utf-8")
    normalized_prompt_calculus = _normalized_routing_text(prompt_calculus)
    assert "q3 prompt attempt identity/diagnostics are implemented" in (
        normalized_prompt_calculus
    )
    assert 'target dsl "2.22"' in normalized_prompt_calculus
    frontend = (
        REPO_ROOT
        / "docs"
        / "design"
        / "workflow_lisp_frontend_specification.md"
    ).read_text(encoding="utf-8")
    normalized_frontend = _normalized_routing_text(frontend)
    assert "implemented prompt attempt identity and diagnostics" in (
        normalized_frontend
    )
    assert "functional v2" in normalized_frontend
    q2_capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp prompt calculus Q2 output positions",
    )
    normalized_q2_capability_row = _normalized_routing_text(q2_capability_row)
    assert "| Implemented |" in q2_capability_row
    assert "target 2.21" in normalized_q2_capability_row
    assert "6ae74a82" in q2_capability_row
    assert "d0bb9a1d" in q2_capability_row
    assert "a40b536c" in q2_capability_row
    assert "4e2c4911" in q2_capability_row
    assert "q2_final_spec_approved" in normalized_q2_capability_row
    assert "q2_final_quality_approved" in normalized_q2_capability_row
    l2_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "| L2 |",
    )
    normalized_l2_row = _normalized_routing_text(l2_row)
    assert "complete" in normalized_l2_row
    assert "implementation through 10e3ccc3" in normalized_l2_row
    assert "l2_final_spec_approved" in normalized_l2_row
    assert "l2_final_quality_approved" in normalized_l2_row
    assert "active" not in normalized_l2_row
    assert "no l2 design is accepted" not in normalized_l2_row
    l3_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "| L3 |",
    )
    normalized_l3_row = _normalized_routing_text(l3_row)
    assert "complete" in normalized_l3_row
    assert (
        "implementation through fc1b01ee, 9e59929d, and "
        "xdist evidence correction 8c704f3f"
    ) in normalized_l3_row
    assert "l3_task1_spec_approved" in normalized_l3_row
    assert "l3_task1_quality_approved" in normalized_l3_row
    assert "l3_task2_spec_approved" in normalized_l3_row
    assert "l3_task2_quality_approved" in normalized_l3_row
    assert "compile path reentrancy" in normalized_l3_row
    assert "blocked by l2" not in normalized_l3_row
    l4_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "| L4 |",
    )
    normalized_l4_row = _normalized_routing_text(l4_row)
    assert "ordered l4_design_spec_approved then l4_design_quality_approved" in (
        normalized_l4_row
    )
    assert "reviewed implementation plan" in normalized_l4_row
    assert Path(LANGUAGE_SERVER_L4_PLAN_PATH).name in l4_row
    assert "l4_plan_spec_approved" in normalized_l4_row
    assert "l4_plan_quality_approved" in normalized_l4_row
    assert "implemented through 11629551 and 0d5f7009" in normalized_l4_row
    assert "l4_task1_spec_approved" in normalized_l4_row
    assert "l4_task1_quality_approved" in normalized_l4_row
    assert "l4_task2_spec_approved" in normalized_l4_row
    assert "l4_task2_quality_approved" in normalized_l4_row
    assert "task 4 focused 356 passed and broad comparison has zero new failures" in (
        normalized_l4_row
    )
    assert "separate implementation plan is the next" not in normalized_successor
    assert "no l4 behavior is implemented" not in normalized_l4_row
    assert "blocked by l3" not in normalized_l4_row
    l1_row = _markdown_table_row(
        REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH,
        "| L1 |",
    )
    normalized_l1_row = _normalized_routing_text(l1_row)
    assert "complete" in normalized_l1_row
    assert "implemented" in normalized_l1_row
    assert "active" not in normalized_l1_row
    l1_capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp language server L1 authored symbols/signatures",
    )
    assert "| Implemented |" in l1_capability_row
    assert "ten symbol kinds" in _normalized_routing_text(l1_capability_row)
    language_server_router_row = _markdown_table_row(
        design_router_path,
        "workflow_lisp_language_server.md",
    )
    normalized_language_server_router_row = _normalized_routing_text(
        language_server_router_row
    )
    assert "l1 authored symbols/signatures are implemented" in (
        normalized_language_server_router_row
    )
    assert "l2 recovery safe static completion is implemented" in (
        normalized_language_server_router_row
    )
    assert "l2_final_spec_approved" in normalized_language_server_router_row
    assert "l2_final_quality_approved" in normalized_language_server_router_row
    l3_capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp language server L3 per-source entry selection",
    )
    normalized_l3_capability_row = _normalized_routing_text(l3_capability_row)
    assert "| Implemented |" in l3_capability_row
    assert "entry_workflows" in l3_capability_row
    assert "l3_task1_spec_approved" in normalized_l3_capability_row
    assert "l3_task1_quality_approved" in normalized_l3_capability_row
    assert "l3_task2_spec_approved" in normalized_l3_capability_row
    assert "l3_task2_quality_approved" in normalized_l3_capability_row
    assert "owner reordered l5 authored reference navigation are complete" in (
        normalized_index
    )
    assert "l3 completed over mr 4 under its reviewed plan" in normalized_index
    assert "l4 diagnostic lifecycle and compile progress" in normalized_index
    assert "l4 closed at commit 251d9d53674e863fddae4535ea4f7022914287cd" in (
        normalized_index
    )
    assert "focused selector reports 356 passed" in normalized_index
    assert "broad comparison has zero new failures" in normalized_index
    assert "p1 diagnostic accumulation" in normalized_successor
    assert "p5 compile caching/incrementality" in normalized_successor
    assert "runtime debugging surface" in normalized_successor

    normalized_evolution_status = _normalized_routing_text(
        evolution.split("## Purpose", 1)[0]
    )
    assert (
        "status: incorporated as the tracked e series program"
        in normalized_evolution_status
    )
    assert "gated on ml closure" in normalized_evolution_status
    assert "p series roadmap" in normalized_evolution_status
    assert "sequenced after this e program" in normalized_evolution_status
    assert "not a selector" in normalized_evolution_status
    assert "e0 probe remains unselected" in normalized_evolution_status
    assert (
        "e4p prompt identity discipline is owned only by stage q3"
        in normalized_evolution_status
    )
    assert "no tranche in this document is selected" in normalized_evolution_status

    normalized_value = _normalized_routing_text(
        "\n".join(value_design.splitlines()[:35])
    )
    assert "status: accepted" in normalized_value
    assert "target: dsl 2.19" in normalized_value
    assert "selected consumer" in normalized_value

    normalized_plan = _normalized_routing_text(
        "\n".join(value_plan.splitlines()[:45])
    )
    if q0_is_closing:
        assert "status: closing" in normalized_plan
        assert "preliminary task 7 reviews are approved" in normalized_plan
        assert "exact byte reaffirmation" in normalized_plan
        assert "implementation/evidence commit remain" in normalized_plan
    else:
        assert "status: complete" in normalized_plan
    assert "implementation pending" not in normalized_plan
    assert "value_q0_plan_spec_approved" in normalized_plan
    assert "value_q0_plan_quality_approved" in normalized_plan
    assert TRANSPORTABLE_VALUE_PLAN_PATH in successor
    normalized_q2_plan = _normalized_routing_text(
        "\n".join(q2_plan.splitlines()[:90])
    )
    assert "execution status: complete" in normalized_q2_plan
    assert "a40b536c" in normalized_q2_plan
    assert "4e2c4911" in normalized_q2_plan
    assert "q2_final_spec_approved" in normalized_q2_plan
    assert "q2_final_quality_approved" in normalized_q2_plan
    assert "q2_plan_spec_approved" in normalized_q2_plan
    assert "q2_plan_quality_approved" in normalized_q2_plan
    normalized_l1_plan = _normalized_routing_text(
        "\n".join(l1_plan.splitlines()[:90])
    )
    assert "status: accepted for execution" in normalized_l1_plan
    assert "l1_plan_spec_approved" in normalized_l1_plan
    assert "l1_plan_quality_approved" in normalized_l1_plan
    normalized_l2_plan = _normalized_routing_text(
        "\n".join(l2_plan.splitlines()[:120])
    )
    assert "execution status: complete" in normalized_l2_plan
    assert "l2_plan_spec_approved" in normalized_l2_plan
    assert "l2_plan_quality_approved" in normalized_l2_plan
    assert "l2_final_spec_approved" in normalized_l2_plan
    assert "l2_final_quality_approved" in normalized_l2_plan
    for commit in ("70b83f32", "b399c041", "ee213a43", "10e3ccc3"):
        assert commit in normalized_l2_plan
    assert PROMPT_OUTPUT_POSITIONS_PLAN_PATH in successor
    assert LANGUAGE_SERVER_L1_PLAN_PATH in successor
    assert LANGUAGE_SERVER_L2_PLAN_PATH in successor

    normalized_sequence = _normalized_routing_text(sequence)
    assert "stage 8 is the active numbered stage" not in normalized_sequence
    assert "stage 8 is now active" not in normalized_sequence
    assert LANGUAGE_QUALITY_ROADMAP_PATH in sequence
    evolution_row = _markdown_table_row(
        sequence_path,
        "2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md",
    )
    normalized_evolution_row = _normalized_routing_text(evolution_row)
    assert "e0 probe remains unselected" in normalized_evolution_row
    assert "exclusively absorbed by successor stage q3" in normalized_evolution_row
    handoff = sequence.split(
        "### Post-Stage-8 Successor Handoff", 1
    )[1].split("## Concurrency Rules", 1)[0]
    normalized_handoff = _normalized_routing_text(handoff)
    assert "selection act completed" in normalized_handoff
    assert "q3" in normalized_handoff
    assert "must not be selected again" in normalized_handoff

    value_design_row = _markdown_table_row(
        design_router_path,
        "workflow_lisp_transportable_value_type.md",
    )
    assert "| Implemented |" in value_design_row
    assert "target 2.19" in _normalized_routing_text(value_design_row)
    capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp transportable `Value`",
    )
    assert "| Implemented |" in capability_row
    normalized_capability_row = _normalized_routing_text(capability_row)
    assert "target 2.19" in normalized_capability_row
    assert "not yet" not in normalized_capability_row
    assert "pending" not in normalized_capability_row
    provider_input_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp typed provider-input carriage",
    )
    normalized_provider_input_row = _normalized_routing_text(provider_input_row)
    assert "target 2.19" in normalized_provider_input_row
    assert "exact value" in normalized_provider_input_row
    provider_result_row = _markdown_table_row(
        capability_matrix_path,
        "| `provider-result` | Implemented |",
    )
    normalized_provider_result_row = _normalized_routing_text(provider_result_row)
    assert "target 2.19" in normalized_provider_result_row
    assert "exact opaque value" in normalized_provider_result_row
    assert "### [Workflow Lisp Transportable `Value` Type]" in index
    assert (
        "### [Workflow Lisp Language Quality And Domain Semantics Roadmap]"
        in index
    )
    normalized_successor_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Language Quality And Domain Semantics Roadmap]",
        )
    )
    assert "completed post stage 8 roadmap" in normalized_successor_index
    assert "q0 q5 and l0 l5 are complete" in normalized_successor_index
    assert (
        "q4's concrete review_revise_design_docs panel consumer is bound"
        in normalized_successor_index
    )
    assert "its original design is accepted at d7fe4549" in normalized_successor_index
    assert "q5 era design amendment is accepted at 3c21ceb4" in (
        normalized_successor_index
    )
    assert "reviewed amended plan 0f21636b" in normalized_successor_index
    assert (
        "q4 closed at commit f3335637b90feb0a87ac4c538bafac7704ac0d87"
        in normalized_successor_index
    )
    assert "tree ccec170be8757c9e4fd5ed8ece6f93b04fc03299" in normalized_successor_index
    assert (
        "85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c"
        in normalized_successor_index
    )
    assert "74 pass postcommit control" in normalized_successor_index
    assert "q5 is complete at 70f4a759, tree fec729cb" in normalized_successor_index
    assert Path(PROMPT_IDENTITY_PLAN_PATH).name in index
    assert "owner reordered l5 authored reference navigation are complete" in (
        normalized_successor_index
    )
    assert "l3 completed over mr 4 under its reviewed plan" in (
        normalized_successor_index
    )
    assert "l4 diagnostic lifecycle and compile progress" in normalized_successor_index
    assert "task 4 focused 356 passed and broad comparison has zero new failures" in (
        normalized_successor_index
    )
    assert "### [Workflow Lisp Language Server L2 Implementation Plan]" in index
    assert "do not select e0" in normalized_successor_index

    prompt_design_row = _markdown_table_row(
        design_router_path,
        "workflow_lisp_prompt_calculus.md",
    )
    normalized_prompt_design_row = _normalized_routing_text(prompt_design_row)
    assert "| Implemented |" in prompt_design_row
    assert "bounded q1 q3 surfaces" in normalized_prompt_design_row
    assert "target 2.22" in normalized_prompt_design_row
    normalized_prompt_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Prompt Calculus]",
        )
    )
    assert "implemented target 2.20 q1 prompt core, target 2.21 q2 output positions, and target 2.22 q3 prompt attempt identity/diagnostics" in (
        normalized_prompt_index
    )
    assert "authoring or reviewing the bounded q1 q3 surfaces" in (
        normalized_prompt_index
    )
    assert "partial application" in normalized_prompt_index
    assert "excludes" in normalized_prompt_index

    normalized_value_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Transportable `Value` Type]",
        )
    )
    assert "implemented target 2.19" in normalized_value_index
    assert "available for authoring" in normalized_value_index
    assert "not yet available" not in normalized_value_index


def test_historical_q2_index_routes_current_selection_to_remaining_entry_gates() -> None:
    index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    q2_section = _markdown_heading_section(
        index,
        "### [Workflow Lisp Prompt Output Positions Implementation Plan]",
    )
    normalized_q2_section = _normalized_routing_text(q2_section)

    assert "q3" in normalized_q2_section
    assert "closed" in normalized_q2_section
    assert Path(LANGUAGE_QUALITY_ROADMAP_PATH).name in q2_section
    assert "active" in normalized_q2_section
    assert "language quality roadmap" in normalized_q2_section
    assert "remaining entry gates" in normalized_q2_section
    assert (
        "current q series selection starts with q3 implementation"
        not in normalized_q2_section
    )


def test_transportable_value_normative_owners_close_the_public_contract() -> None:
    frontend = (
        REPO_ROOT / "docs/design/workflow_lisp_frontend_specification.md"
    ).read_text(encoding="utf-8")
    type_catalog = (
        REPO_ROOT / "docs/design/workflow_lisp_type_catalog.md"
    ).read_text(encoding="utf-8")
    drafting_guide = (
        REPO_ROOT / "docs/lisp_workflow_drafting_guide.md"
    ).read_text(encoding="utf-8")
    dsl = (REPO_ROOT / "specs/dsl.md").read_text(encoding="utf-8")
    io = (REPO_ROOT / "specs/io.md").read_text(encoding="utf-8")
    providers = (REPO_ROOT / "specs/providers.md").read_text(encoding="utf-8")
    versioning = (REPO_ROOT / "specs/versioning.md").read_text(encoding="utf-8")

    normalized_frontend = _normalized_routing_text(frontend)
    assert "`Value`" in frontend
    assert "target 2.19" in normalized_frontend
    assert "exact" in normalized_frontend
    assert "opaque" in normalized_frontend
    assert "Value -> Value" in frontend
    assert "T -> Value" in frontend
    assert "Value -> T" in frontend

    normalized_catalog = _normalized_routing_text(type_catalog)
    assert "`Value`" in type_catalog
    assert "direct root" in normalized_catalog
    assert "__result__" in type_catalog
    assert "type: value" in normalized_catalog
    assert "record" in normalized_catalog
    assert "union" in normalized_catalog

    normalized_guide = _normalized_routing_text(drafting_guide)
    assert "`Value`" in drafting_guide
    assert "`Json`" in drafting_guide
    assert "distinct" in normalized_guide
    assert "non transportable" in normalized_guide
    assert "record" in normalized_guide
    assert "union" in normalized_guide
    assert "opaque" in normalized_guide

    normalized_dsl = _normalized_routing_text(dsl)
    assert "type: value" in normalized_dsl
    assert "kind: value" in normalized_dsl
    assert "direct root" in normalized_dsl
    assert "__result__" in dsl
    assert "envelope" in normalized_dsl
    assert "value_guidance_example_unsupported" in dsl

    normalized_io = _normalized_routing_text(io)
    assert "`Value`" in io
    assert "strict json" in normalized_io
    assert "non finite" in normalized_io
    assert "nan" in normalized_io
    assert "infinity" in normalized_io
    assert "invalid_transportable_value" in io

    normalized_providers = _normalized_routing_text(providers)
    assert "`Value`" in providers
    assert "direct root" in normalized_providers
    assert "envelope" in normalized_providers
    assert "description" in normalized_providers
    assert "format hint" in normalized_providers
    assert "guidance" in normalized_providers

    version_rows = [
        line
        for line in versioning.splitlines()
        if line.startswith("| 2.19 |")
    ]
    assert len(version_rows) == 1
    normalized_version_row = _normalized_routing_text(version_rows[0])
    assert "value" in normalized_version_row
    assert "type: value" in normalized_version_row
    assert "kind: value" in normalized_version_row
    assert "strict json" in normalized_version_row


def test_prompt_core_normative_and_authoring_surfaces_close_q1() -> None:
    frontend = (
        REPO_ROOT / "docs/design/workflow_lisp_frontend_specification.md"
    ).read_text(encoding="utf-8")
    semantic_ir = (
        REPO_ROOT / "docs/design/workflow_lisp_semantic_workflow_ir.md"
    ).read_text(encoding="utf-8")
    executable_ir = (
        REPO_ROOT / "docs/design/workflow_lisp_executable_ir.md"
    ).read_text(encoding="utf-8")
    providers = (REPO_ROOT / "specs/providers.md").read_text(encoding="utf-8")
    state = (REPO_ROOT / "specs/state.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs/lisp_workflow_drafting_guide.md").read_text(
        encoding="utf-8"
    )
    design_router_path = REPO_ROOT / "docs/design/README.md"
    capability_matrix_path = REPO_ROOT / "docs/capability_status_matrix.md"
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")

    normalized_frontend = _normalized_routing_text(frontend)
    for required in (
        "target 2.20",
        "defprompt",
        "compiled_prompt_fragment_identity",
        "workflow_prompt_fragment_snapshot.functional.v1",
        "prompt_calculus_requires_dsl_2_20",
        "prompt_fill_renderer_unsupported",
        "prompt_return_redeclaration_forbidden",
    ):
        assert required in normalized_frontend
    assert "q2" in normalized_frontend
    assert "q3" in normalized_frontend
    assert "q4" in normalized_frontend

    for ir_contract in (semantic_ir, executable_ir):
        assert "CompilerPromptFragmentContract" in ir_contract
        assert "compiled_prompt_fragment_identity" in ir_contract
        assert "workflow_lisp_prompt_fragment" in ir_contract
        assert "runtime_plan" in ir_contract

    normalized_providers = _normalized_routing_text(providers)
    assert "workflow lisp prompt fragments" in normalized_providers
    assert "target 2.20" in normalized_providers
    assert "workflow_prompt_fragment_snapshot.functional.v1" in providers
    assert "before provider launch" in normalized_providers

    normalized_state = _normalized_routing_text(state)
    assert "workflow lisp prompt fragment attempt state and resume" in normalized_state
    assert "schema 2.1" in normalized_state
    assert "compatible completed result reuse" in normalized_state
    assert "do not read prompt snapshot evidence" in normalized_state

    normalized_guide = _normalized_routing_text(guide)
    assert "authoring prompt fragments target 2.20" in normalized_guide
    assert "fully applied" in normalized_guide
    assert "prompt owned" in normalized_guide
    assert "List[DesignDocPath]" in guide
    assert "partial application" in normalized_guide
    assert "prompt dependencies" in normalized_guide

    prompt_design_row = _markdown_table_row(
        design_router_path,
        "workflow_lisp_prompt_calculus.md",
    )
    assert "| Implemented |" in prompt_design_row
    prompt_capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp prompt calculus Q1",
    )
    assert "| Implemented |" in prompt_capability_row

    prompt_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Prompt Calculus]",
        )
    )
    assert "implemented target 2.20" in prompt_index
    assert "authoring or reviewing the bounded q1 q3 surfaces" in prompt_index
    assert "implementation plan next" not in prompt_index

    active_roadmap_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Language Quality And Domain Semantics Roadmap]",
        )
    )
    assert "q0 q5 and l0 l5 are complete" in active_roadmap_index
    assert "q4's concrete review_revise_design_docs panel consumer is bound" in (
        active_roadmap_index
    )
    assert "its original design is accepted at d7fe4549" in active_roadmap_index
    assert "q5 era design amendment is accepted at 3c21ceb4" in (
        active_roadmap_index
    )
    assert "reviewed amended plan 0f21636b" in active_roadmap_index
    assert (
        "q4 closed at commit f3335637b90feb0a87ac4c538bafac7704ac0d87"
        in active_roadmap_index
    )
    assert (
        "85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c"
        in active_roadmap_index
    )
    assert "q5 is complete at 70f4a759, tree fec729cb" in active_roadmap_index
    assert "owner reordered l5 authored reference navigation are complete" in (
        active_roadmap_index
    )
    assert "mr 4 closed l3's compile path reentrancy prerequisite" in (
        active_roadmap_index
    )
    assert "l3 immutable per source entry selection" in active_roadmap_index
    assert "l4 diagnostic lifecycle and compile progress" in active_roadmap_index
    assert "accepted editor evidence and ordered design reviews" in (
        active_roadmap_index
    )
    assert "reviewed implementation plan" in active_roadmap_index
    assert "current only diagnostic publication" in active_roadmap_index
    assert "capability gated progress" in active_roadmap_index
    assert "task 4 focused 356 passed and broad comparison has zero new failures" in (
        active_roadmap_index
    )
    assert Path(LANGUAGE_SERVER_L4_PLAN_PATH).name in index


def test_prompt_output_positions_normative_and_authoring_surfaces_ship_q2() -> None:
    master = (REPO_ROOT / "specs/index.md").read_text(encoding="utf-8")
    versioning = (REPO_ROOT / "specs/versioning.md").read_text(encoding="utf-8")
    dsl = (REPO_ROOT / "specs/dsl.md").read_text(encoding="utf-8")
    io = (REPO_ROOT / "specs/io.md").read_text(encoding="utf-8")
    providers = (REPO_ROOT / "specs/providers.md").read_text(encoding="utf-8")
    state = (REPO_ROOT / "specs/state.md").read_text(encoding="utf-8")
    semantic_ir = (
        REPO_ROOT / "docs/design/workflow_lisp_semantic_workflow_ir.md"
    ).read_text(encoding="utf-8")
    executable_ir = (
        REPO_ROOT / "docs/design/workflow_lisp_executable_ir.md"
    ).read_text(encoding="utf-8")
    prompt_design = (
        REPO_ROOT / "docs/design/workflow_lisp_prompt_calculus.md"
    ).read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs/lisp_workflow_drafting_guide.md").read_text(
        encoding="utf-8"
    )

    normalized_master = _normalized_routing_text(master)
    assert "target 2.21" in normalized_master
    assert "prompt output positions" in normalized_master
    assert "v2.18 bounded list traversal tranche" in normalized_master

    version_rows = [
        line
        for line in versioning.splitlines()
        if line.startswith("| 2.21 |")
    ]
    assert len(version_rows) == 1
    normalized_version_row = _normalized_routing_text(version_rows[0])
    assert ":path :out" in normalized_version_row
    assert "compiled_prompt_fragment_identity.v2" in version_rows[0]
    list_version_rows = [
        line
        for line in versioning.splitlines()
        if line.startswith("| 2.18 |")
    ]
    assert len(list_version_rows) == 1
    normalized_versioning = _normalized_routing_text(versioning)
    assert "v2.18 additions" in normalized_versioning
    assert "workflow lisp bounded list traversal" in normalized_versioning
    assert "v2.18: bounded workflow lisp list traversal" in normalized_versioning

    normalized_dsl = _normalized_routing_text(dsl)
    assert "workflow lisp prompt output positions" in normalized_dsl
    assert "target 2.21" in normalized_dsl
    assert "slot name :path :out [pathtype]" in normalized_dsl
    assert "compiler_prompt_fragment_contract.v2" in dsl
    assert "below target 2.21" in normalized_dsl
    assert "expected_outputs may coexist with exactly one output_bundle" in (
        normalized_dsl
    )
    assert "expected_outputs may coexist with exactly one variant_output" in (
        normalized_dsl
    )

    normalized_io = _normalized_routing_text(io)
    assert "prompt output position composition" in normalized_io
    assert "target 2.21" in normalized_io
    assert "output position first" in normalized_io
    assert "state atomic" in normalized_io

    normalized_providers = _normalized_routing_text(providers)
    assert "workflow lisp prompt output positions" in normalized_providers
    assert "target 2.21" in normalized_providers
    assert "before provider launch" in normalized_providers
    assert "output position then structured result" in normalized_providers
    assert "expected_outputs then structured contract order" in (
        normalized_providers
    )

    normalized_prompt_design = _normalized_routing_text(prompt_design)
    assert "before q2, the generic owners assumed one output contract surface" in (
        normalized_prompt_design
    )
    assert "q2 implemented the following generic correction" in (
        normalized_prompt_design
    )

    normalized_state = _normalized_routing_text(state)
    assert "target 2.21 prompt output position attempt state and resume" in (
        normalized_state
    )
    assert "compiled_prompt_fragment_identity.v2" in state
    assert "compiler_prompt_fragment_contract.v2" in state
    assert "compatible completed result reuse" in normalized_state

    for ir_contract in (semantic_ir, executable_ir):
        normalized_ir = _normalized_routing_text(ir_contract)
        assert "target 2.21 prompt output positions" in normalized_ir
        assert "compiled_prompt_fragment_identity.v2" in ir_contract
        assert "compiler_prompt_fragment_contract.v2" in ir_contract
        assert "output_positions" in ir_contract
        assert "expected_output" in ir_contract
        assert "expected_outputs" in ir_contract
        assert "pair validated" in normalized_ir

    normalized_guide = _normalized_routing_text(guide)
    assert "authoring prompt output positions target 2.21" in normalized_guide
    assert ":path :out" in normalized_guide
    assert "review design docs" in normalized_guide
    assert "one structured result" in normalized_guide
    assert "q3" in normalized_guide


def test_prompt_identity_normative_and_authoring_surfaces_ship_q3() -> None:
    master = (REPO_ROOT / "specs/index.md").read_text(encoding="utf-8")
    versioning = (REPO_ROOT / "specs/versioning.md").read_text(
        encoding="utf-8"
    )
    dsl = (REPO_ROOT / "specs/dsl.md").read_text(encoding="utf-8")
    io = (REPO_ROOT / "specs/io.md").read_text(encoding="utf-8")
    providers = (REPO_ROOT / "specs/providers.md").read_text(
        encoding="utf-8"
    )
    state = (REPO_ROOT / "specs/state.md").read_text(encoding="utf-8")
    frontend = (
        REPO_ROOT
        / "docs"
        / "design"
        / "workflow_lisp_frontend_specification.md"
    ).read_text(encoding="utf-8")
    prompt_design = (
        REPO_ROOT / "docs" / "design" / "workflow_lisp_prompt_calculus.md"
    ).read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs/lisp_workflow_drafting_guide.md").read_text(
        encoding="utf-8"
    )
    capability = (
        REPO_ROOT / "docs/capability_status_matrix.md"
    ).read_text(encoding="utf-8")

    normalized_master = _normalized_routing_text(master)
    assert "v1.1 through v2.23" in normalized_master
    assert "v2.22 adds direct fragment prompt attempt identity" in (
        normalized_master
    )

    version_rows = [
        line
        for line in versioning.splitlines()
        if line.startswith("| 2.22 |")
    ]
    assert len(version_rows) == 1
    normalized_version_row = _normalized_routing_text(version_rows[0])
    assert "functional v2 evidence" in normalized_version_row
    assert "additive prompt context reports" in normalized_version_row
    assert "target 2.20/2.21" in normalized_version_row

    normalized_dsl = _normalized_routing_text(dsl)
    assert "workflow lisp prompt attempt identity and diagnostics" in (
        normalized_dsl
    )
    assert "workflow_prompt_attempt_identity.v1" in dsl
    assert "compiler_prompt_attempt_binding_plan.v1" in dsl
    for diagnostic in (
        "prompt_attempt_identity_version_missing",
        "prompt_attempt_identity_version_invalid",
        "prompt_attempt_identity_version_mismatch",
        "prompt_attempt_binding_plan_missing",
        "prompt_attempt_binding_plan_invalid",
        "prompt_attempt_binding_plan_mismatch",
        "prompt_attempt_identity_role_invalid",
        "prompt_attempt_identity_policy_invalid",
        "prompt_attempt_identity_final_prompt_mismatch",
        "prompt_attempt_identity_composition_invalid",
        "prompt_identity_composition_mismatch",
    ):
        assert diagnostic in dsl

    normalized_io = _normalized_routing_text(io)
    assert "workflow lisp prompt attempt evidence and report io" in (
        normalized_io
    )
    assert "after successful invocation preparation and before provider launch" in (
        normalized_io
    )
    assert "prompt_context" in io

    normalized_providers = _normalized_routing_text(providers)
    assert "workflow lisp prompt attempt identity and diagnostics" in (
        normalized_providers
    )
    assert "fragment_program" in providers
    assert "resolved_bindings" in providers
    assert "injected_dependencies" in providers
    assert "runtime_contributions" in providers
    assert "provider_policy" in providers
    assert "fixed drift order" in normalized_providers

    normalized_state = _normalized_routing_text(state)
    assert "target 2.22 prompt attempt identity state and resume" in (
        normalized_state
    )
    assert "state schema 2.1" in normalized_state
    assert "non authoritative" in normalized_state
    assert "compatible completed result reuse" in normalized_state

    normalized_frontend = _normalized_routing_text(frontend)
    assert "implemented prompt attempt identity (target 2.22)" in (
        normalized_frontend
    )
    assert "implemented prompt attempt identity and diagnostics (target 2.22)" in (
        normalized_frontend
    )
    assert "allocator derived json/markdown reporting" in normalized_frontend

    normalized_prompt_design = _normalized_routing_text(prompt_design)
    assert "accepted and implemented q1, q2, and q3 designs" in (
        normalized_prompt_design
    )
    assert "functional v2 evidence" in normalized_prompt_design
    assert "provenance only" in normalized_prompt_design

    normalized_guide = _normalized_routing_text(guide)
    assert "inspecting prompt attempt identity target 2.22" in normalized_guide
    assert "there is no new call keyword" in normalized_guide
    assert "legacy_snapshot" in guide
    assert "coordinated provider and extern backed calls do not gain q3" in (
        normalized_guide
    )

    q3_capability = _markdown_table_row(
        REPO_ROOT / "docs/capability_status_matrix.md",
        "Workflow Lisp prompt identity diagnostics Q3",
    )
    assert "| Implemented |" in q3_capability
    assert "target-2.22" in q3_capability
    assert "tests/test_workflow_lisp_prompt_identity_e2e.py" in q3_capability
    assert "Q4 judgments remain excluded" in q3_capability


def test_judgment_views_normative_contracts_route_q4_only() -> None:
    state = (REPO_ROOT / "specs/state.md").read_text(encoding="utf-8")
    observability = (REPO_ROOT / "specs/observability.md").read_text(
        encoding="utf-8"
    )
    providers = (REPO_ROOT / "specs/providers.md").read_text(encoding="utf-8")
    dsl = (REPO_ROOT / "specs/dsl.md").read_text(encoding="utf-8")

    state_section = _markdown_heading_section(
        state,
        "## Workflow Prompt-Attempt Result Binding State And Resume",
    ).split("\n## ", 1)[0]
    state_items = re.findall(
        r"(?ms)^- (.*?)(?=^- |\Z)",
        state_section,
    )
    assert len(state_items) == 4
    assert "StepResult.debug.prompt_attempt_result_binding" in state_items[0]
    assert "workflow_prompt_attempt_result_binding.v1" in state_items[0]
    assert {
        match.group(1)
        for match in re.finditer(r"(?m)^  - `([a-z0-9_]+)`:", state_items[0])
    } == {
        "schema_version",
        "scope_sha256",
        "attempt_ordinal",
        "evidence_relative_path",
        "evidence_file_sha256",
        "record_kind",
    }
    assert "`prompt_snapshot`" in state_items[0]
    assert "`io.md`" in state_items[1]
    assert {"result", "artifacts", "locator"} <= set(
        re.findall(r"[a-z]+", state_items[1].lower())
    )
    assert "pre-Q4" in state_items[3]

    observability_section = _markdown_heading_section(
        observability,
        "## Workflow Lisp Judgment Views",
    ).split("\n## ", 1)[0]
    observability_items = re.findall(
        r"(?ms)^- (.*?)(?=^- |\Z)",
        observability_section,
    )
    empty_shape_match = re.search(
        r"(?ms)```json\n(.*?)\n  ```",
        observability_items[0],
    )
    assert empty_shape_match is not None
    assert json.loads(empty_shape_match.group(1)) == {
        "judgment_views": {
            "schema_version": "workflow_judgment_views.v1",
            "judgments": [],
            "matrices": [],
            "disagreements": [],
            "iteration_series": [],
        }
    }

    coordinate_item = next(
        item for item in observability_items if "workflow_checksum" in item
    )
    for field in (
        "root_workflow_identity",
        "call_frame_path",
        "runtime_step_id",
        "enclosing_step_id",
        "enclosing_visit",
        "loop",
        "kind",
        "step_id",
        "iteration",
    ):
        assert f"`{field}`" in coordinate_item
    assert {"`for_each`", "`repeat_until`"} <= set(
        re.findall(r"`[^`]+`", coordinate_item)
    )

    available_item = next(
        item
        for item in observability_items
        if "workflow_judgment_inspection.v1" in item
        and 'status: "available"' in item
    )
    for symbol in (
        "attempt_ordinal",
        "declared_shape",
        "contract_sha256",
        "value_sha256",
        "evidence_record_sha256",
        "identity_schema_version",
        "role_sha256",
        "final_prompt_sha256",
        "composition_sha256",
        "workflow_prompt_attempt_identity.v1",
    ):
        assert f"`{symbol}`" in available_item
    for enum_value in (
        "root_value",
        "record_value",
        "union_value",
        "canonical_value",
        "union_variant",
    ):
        assert f"`{enum_value}`" in available_item

    unavailable_item = next(
        item
        for item in observability_items
        if "workflow_judgment_inspection.v1" in item
        and 'status: "unavailable"' in item
    )
    assert {
        match.group(1)
        for match in re.finditer(
            r"`(judgment_(?:result|view)_[a-z_]+)`",
            unavailable_item,
        )
    } == {
        "judgment_result_binding_missing",
        "judgment_result_binding_invalid",
        "judgment_result_binding_ambiguous",
        "judgment_result_scope_mismatch",
        "judgment_result_attempt_mismatch",
        "judgment_result_evidence_invalid",
        "judgment_result_contract_mismatch",
        "judgment_result_value_mismatch",
        "judgment_result_coordinate_invalid",
        "judgment_view_group_invalid",
    }

    matrix_item = next(
        item
        for item in observability_items
        if "workflow_judgment_matrix.v1" in item
    )
    for symbol in (
        "group",
        "members",
        "result_value_sha256",
        "evidence_record_sha256",
        "comparable",
        "not_comparable",
        "unavailable",
    ):
        assert f"`{symbol}`" in matrix_item

    disagreement_item = next(
        item
        for item in observability_items
        if "workflow_judgment_disagreement.v1" in item
    )
    for symbol in (
        "available_member_count",
        "comparable_member_count",
        "not_comparable_member_count",
        "unavailable_member_count",
        "distinct_comparison_key_count",
        "insufficient_members",
        "not_comparable",
        "agree",
        "disagree",
    ):
        assert f"`{symbol}`" in disagreement_item

    series_item = next(
        item
        for item in observability_items
        if "workflow_judgment_iteration_series.v1" in item
    )
    for symbol in (
        "scope_sha256",
        "attempts",
        "attempt_ordinal",
        "record_status",
        "record_sha256",
        "committed_result_status",
        "bound",
        "not_bound",
        "unknown_pre_q4",
    ):
        assert f"`{symbol}`" in series_item

    order_item = next(
        item for item in observability_items if "ensure_ascii=False" in item
    )
    assert "`call_frame_path`" in order_item
    assert '`(",", ":")`' in order_item
    parity_item = next(
        item
        for item in observability_items
        if "load_persisted_compiled_workflow_surface" in item
    )
    assert (
        "`orchestrator.dashboard.compiled_workflow."
        "load_persisted_compiled_workflow_surface`"
    ) in parity_item
    assert (
        "`state.runtime_observability.compiled_frontend."
        "persisted_workflow_surface`"
    ) in parity_item

    providers_section = providers.split(
        "- Workflow Lisp ordinary identity-v1 judgment association",
        1,
    )[1].split(
        "\n- Workflow Lisp phased contract delivery (target 2.23)",
        1,
    )[0]
    provider_items = re.findall(
        r"(?ms)^  - (.*?)(?=^  - |\Z)",
        providers_section,
    )
    assert len(provider_items) == 3
    for symbol in (
        ":delivery :composed",
        "workflow_prompt_attempt_identity.v1",
        "workflow_prompt_fragment_snapshot.functional.v2",
        "io.md",
    ):
        assert f"`{symbol}`" in provider_items[0]
    assert "Q3" in provider_items[1]
    assert provider_items[1].count("ordinal") >= 3
    for symbol in (
        "workflow_prompt_attempt_identity.v2",
        "workflow_prompt_fragment_snapshot.functional.v3",
    ):
        assert f"`{symbol}`" in provider_items[2]
    assert "Q4-ineligible" in provider_items[2]

    dsl_section = dsl.split(
        "  - Workflow Lisp WCC child-call argument projection:",
        1,
    )[1].split(
        "\n  - reusable-call contract boundary:",
        1,
    )[0]
    assert dsl_section.count("`list/map-effect`") == 1
    assert dsl_section.count("`path/join-under`") == 1
    assert dsl_section.count("WCC") == 1


def test_stage_6_numbered_sequence_closes_task_7_after_completed_queues() -> None:
    sequence = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-09-procedure-first-roadmap-execution-sequence.md"
    ).read_text(encoding="utf-8")
    stage_6 = sequence.split("### Stage 6: Resume YAML Retirement", 1)[1].split(
        "### Stage 7:", 1
    )[0]
    steps = [
        _normalized_routing_text(body)
        for _, body in re.findall(
            r"(?ms)^(\d+)\. (.*?)(?=^\d+\. |\Z)",
            stage_6,
        )
    ]

    promotion_indexes = [
        index
        for index, step in enumerate(steps)
        if "verified_iteration_drain" in step and "generic_run_watchdog" in step
        and "port" in step and "promot" in step
    ]
    frontend_indexes = [
        index
        for index, step in enumerate(steps)
        if "task 7" in step and "frontend" in step
    ]
    queue_indexes = [
        index
        for index, step in enumerate(steps)
        if "task 6" in step
        and "archive" in step
        and "deletion" in step
        and "queue" in step
    ]
    archive_indexes = [
        index
        for index, step in enumerate(steps)
        if "design delta" in step and "archive" in step and "historical" in step
    ]

    assert len(promotion_indexes) == 1
    assert len(queue_indexes) == 1
    assert len(archive_indexes) == 1
    assert len(frontend_indexes) == 1
    promotion_index = promotion_indexes[0]
    queue_index = queue_indexes[0]
    archive_index = archive_indexes[0]
    frontend_index = frontend_indexes[0]
    normalized_stage_6 = _normalized_routing_text(stage_6)
    assert "status: complete" in normalized_stage_6
    assert "complete" in steps[promotion_index]
    assert "historical decision evidence" in steps[archive_index]
    assert "complete" in steps[queue_index]
    closeout = steps[frontend_index]
    assert "task 7" in closeout
    assert "frontend" in closeout
    assert "complete" in closeout
    assert "broad" in closeout and "zero new" in closeout
    assert "d9baa120" in closeout
    assert "pass" in closeout and "approved" in closeout
    assert archive_index < promotion_index < queue_index < frontend_index


def test_migration_wave_closeout_preserves_history_and_routes_yaml_task_7_verification() -> None:
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
        ) == ["x"] * expected_step_count
    normalized_task_7 = _normalized_routing_text(remaining_tasks[7])
    assert "complete" in normalized_task_7
    normalized_status = _normalized_routing_text(_migration_plan_status(plan))
    assert "complete" in normalized_status
    assert "historical" in normalized_status
    assert re.search(
        r"\byaml retirement\b.{0,100}\btasks? 1[ -]4\b.{0,80}\bcomplete\b",
        normalized_status,
    )
    assert re.search(
        r"\bcurrent selector\b.{0,80}\btask 5\b",
        normalized_status,
    )
    for stale_task in (1, 2, 3, 4, 6, 7):
        assert re.search(
            rf"\byaml retirement\b[^.;]{{0,120}}\btask {stale_task}\b"
            rf"[^.;]{{0,40}}\bcurrent\b"
            rf"|\bcurrent selector\b[^.;]{{0,120}}\byaml retirement\b"
            rf"[^.;]{{0,80}}\btask {stale_task}\b",
            _normalized_routing_text(plan),
        ) is None, stale_task

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
        _assert_migration_wave_complete_and_yaml_stage_closed(surface, label)

    for label in ("docs index",):
        _assert_exact_ordered_routing_paths(selector_surfaces[label], label)


def test_task8_baseline_replay_is_content_addressed_and_bounded() -> None:
    replay = json.loads((REPO_ROOT / TASK8_BASELINE_REPLAY_PATH).read_text(encoding="utf-8"))
    _assert_task8_baseline_replay_contract(replay)

    plan = (REPO_ROOT / CURRENT_SELECTOR_PATH).read_text(encoding="utf-8")
    task8 = _migration_task_section(plan, 8)
    staging_line = next(
        line for line in task8.splitlines() if line.startswith("git add ")
    )
    staged_paths = set(shlex.split(staging_line)[2:])
    evidence_root = (
        "docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/"
    )
    assert staged_paths == {
        "docs/design/workflow_lisp_parametric_type_system.md",
        "docs/lisp_workflow_drafting_guide.md",
        "docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md",
        "docs/plans/2026-07-13-procedure-first-migration-waves-plan.md",
        "docs/plans/2026-07-13-procedure-first-reuse-inventory.md",
        "docs/plans/2026-07-16-yaml-retirement-handoff-plan.md",
        f"{evidence_root}adjudication.json",
        f"{evidence_root}output-contract.txt",
        f"{evidence_root}semantic-prompt-lineage.txt",
        f"{evidence_root}executable-ir-keys.txt",
        f"{evidence_root}semantic-command-boundary.txt",
        f"{evidence_root}provider-role.txt",
        f"{evidence_root}neurips-runtime.txt",
        "docs/capability_status_matrix.md",
        "docs/index.md",
        "tests/test_workflow_lisp_drain_roadmap_routing.py",
    }


def test_task8_capture_point_accepts_a_descendant_head_and_rejects_divergence() -> None:
    capture = "capture-commit"
    descendant = "future-closeout-commit"
    accepted_edges = {(capture, capture), (capture, descendant)}

    _assert_capture_point_precedes_current_head(
        capture,
        descendant,
        is_ancestor=lambda ancestor, current: (ancestor, current) in accepted_edges,
    )
    with pytest.raises(AssertionError):
        _assert_capture_point_precedes_current_head(
            capture,
            "divergent-commit",
            is_ancestor=lambda ancestor, current: (
                ancestor,
                current,
            ) in accepted_edges,
        )


def test_task8_baseline_replay_rejects_contract_and_evidence_tampering() -> None:
    replay = json.loads((REPO_ROOT / TASK8_BASELINE_REPLAY_PATH).read_text(encoding="utf-8"))
    mutations = []

    wrong_digest = copy.deepcopy(replay)
    wrong_digest["failures"][0]["raw_log"]["sha256"] = "0" * 64
    mutations.append(wrong_digest)

    wrong_signature = copy.deepcopy(replay)
    wrong_signature["failures"][0]["normalized_failure_signature"] += " changed"
    mutations.append(wrong_signature)

    wrong_nodeid = copy.deepcopy(replay)
    wrong_nodeid["failures"][0]["nodeid"] = "tests/example.py::test_other_failure"
    mutations.append(wrong_nodeid)

    wrong_category = copy.deepcopy(replay)
    wrong_category["failures"][0]["category"] = "migration_wave_failure"
    mutations.append(wrong_category)

    wrong_diff = copy.deepcopy(replay)
    wrong_diff["failures"][0]["normalized_diff"]["changed_line_count"] = 2
    mutations.append(wrong_diff)

    wrong_provenance = copy.deepcopy(replay)
    wrong_provenance["provenance"]["pre_wave_commits"][0]["commit"] = "0" * 40
    mutations.append(wrong_provenance)

    wrong_capture_commit = copy.deepcopy(replay)
    wrong_capture_commit["repository"]["head_commit"] = "0" * 40
    mutations.append(wrong_capture_commit)

    wrong_capture_tree = copy.deepcopy(replay)
    wrong_capture_tree["repository"]["head_tree"] = "0" * 40
    mutations.append(wrong_capture_tree)

    irrelevant_claim = copy.deepcopy(replay)
    irrelevant_claim["claims_not_made"].append(
        "This unrelated statement is not part of the reviewed evidence contract."
    )
    mutations.append(irrelevant_claim)

    unexpected_authority_field = copy.deepcopy(replay)
    unexpected_authority_field["authorities"]["baseline"]["note"] = "unchecked"
    mutations.append(unexpected_authority_field)

    unexpected_top_level_field = copy.deepcopy(replay)
    unexpected_top_level_field["note"] = "unchecked"
    mutations.append(unexpected_top_level_field)

    reversed_failures = copy.deepcopy(replay)
    reversed_failures["failures"].reverse()
    mutations.append(reversed_failures)

    changed_finding = copy.deepcopy(replay)
    changed_finding["provenance"]["finding"] = "The movement may predate the wave."
    mutations.append(changed_finding)

    for mutation in mutations:
        with pytest.raises(AssertionError):
            _assert_task8_baseline_replay_contract(mutation)

    non_locator = copy.deepcopy(replay)
    row = non_locator["failures"][0]
    path = row["raw_log"]["path"]
    mutated_raw = (REPO_ROOT / path).read_bytes().replace(
        b"E       assert 2 == 0", b"E       assert 3 == 0", 1
    )
    assert mutated_raw != (REPO_ROOT / path).read_bytes()
    row["raw_log"]["bytes"] = len(mutated_raw)
    row["raw_log"]["sha256"] = _sha256_bytes(mutated_raw)
    normalized = normalize_procedure_prerequisite_failure_log(
        mutated_raw.decode("utf-8"), repo_root=REPO_ROOT
    )
    row["normalized_sha256"] = _sha256_bytes(normalized.encode("utf-8"))
    with pytest.raises(AssertionError):
        _assert_task8_baseline_replay_contract(
            non_locator, raw_overrides={path: mutated_raw}
        )


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
            queue["status"],
        )
        for queue in handoff["queues"]
    }
    assert set(manifest_rows) == set(expected)
    for queue_id, (path_count, legacy_count, machine_status) in expected.items():
        row = manifest_rows[queue_id]
        assert row[1] == path_count
        assert row[2] == legacy_count
        assert machine_status == "pending"
        assert row[3] == "complete"

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
    holdout_row = manifest_rows["hold_non_progress_step_back"]
    holdout_contract = _normalized_routing_text(holdout_row[5])
    assert "delete" in holdout_contract
    assert "no .orc port" in holdout_contract
    assert "both deletion gates passed" in holdout_contract
    assert "retired" in holdout_contract

    task_5 = program.split("### Task 5:", 1)[1].split("### Task 6:", 1)[0]
    task_5_rows = [
        line for line in task_5.splitlines() if line.startswith("| `")
    ]
    assert len(task_5_rows) == 2
    assert "verified_iteration_drain" in task_5_rows[0]
    assert "generic_run_watchdog" in task_5_rows[1]
    assert "Promotion gates closed" in task_5_rows[0]
    assert (
        "artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final/"
        "verified_iteration_drain.json"
    ) in task_5_rows[0]
    assert "The former YAML twin is retired" in task_5_rows[0]
    assert "Promotion gates closed" in task_5_rows[1]
    assert (
        "artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-final/"
        "generic_run_watchdog.json"
    ) in task_5_rows[1]
    assert "The former YAML twin is retired" in task_5_rows[1]
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
        "matching nonterminal consumer",
        "all five queues are drained",
        "task 7",
    ):
        assert contract_term in normalized

    assert "`pending_stage_6_scan`" not in program
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
    assert "## Protected working-tree guard" not in program
    released = program.split(
        "## Released holdout-specific working-tree fence", 1
    )[1].split(
        "## Stage-6 Queue Manifest", 1
    )[0]
    listed = {
        line[3:-1]
        for line in released.splitlines()
        if line.startswith("- `") and line.endswith("`")
    }
    assert listed == protected_paths
    normalized_release = _normalized_routing_text(released)
    assert "2026-07-23t16:06:20-07:00" in released.lower()
    assert "no longer fenced" in normalized_release
    assert "delete, not port" in normalized_release
    assert "git diff --cached --name-only --" not in released
    assert "never stage, restore, rewrite, format, or delete" not in normalized_release


def test_yaml_tasks_6_and_7_are_complete_with_final_stage_6_gates() -> None:
    program = (
        REPO_ROOT / "docs" / "plans" / "2026-07-07-yaml-retirement-program.md"
    ).read_text(encoding="utf-8")
    normalized_program = _normalized_routing_text(program)
    task_5 = program.split("### Task 5:", 1)[1].split("### Task 6:", 1)[0]
    task_6 = program.split("### Task 6:", 1)[1].split("### Task 7:", 1)[0]
    task_7 = program.split("### Task 7:", 1)[1].split(
        "## Program completion contract", 1
    )[0]

    assert "complete" in _normalized_routing_text(task_5[:200])
    assert "task 5 is complete" in normalized_program
    assert "reference" in _normalized_routing_text(task_6)
    assert "supported run" in _normalized_routing_text(task_6)
    assert task_6.count("- [x]") == 6
    assert "- [ ]" not in task_6
    assert task_7.count("- [x]") == 7
    assert "- [ ]" not in task_7
    normalized_task_7 = _normalized_routing_text(task_7)
    assert "complete" in normalized_task_7
    assert "1,020" in normalized_task_7
    assert "5 skipped" in normalized_task_7
    assert "6,386 passed" in normalized_task_7
    assert "15 skipped" in normalized_task_7
    assert "four failures" in normalized_task_7
    assert "zero new" in normalized_task_7
    assert "owner adopted six row baseline" in normalized_task_7
    assert "fresh" in normalized_task_7 and "smoke" in normalized_task_7
    assert "d9baa120" in normalized_task_7
    assert "pass" in normalized_task_7
    assert "approved" in normalized_task_7
    assert "stage 6" in normalized_program and "complete" in normalized_program
    assert "eligible and current" not in normalized_task_7
    assert not re.search(r"\btask 7\b.{0,80}\bis current\b", normalized_program)
    assert "2026-07-17-yaml-retirement-task-6-execution-plan.md" in program
    assert "task 5 remains the current selector" not in normalized_program


def test_yaml_task_6_completed_governing_plan_is_tracked() -> None:
    program = (
        REPO_ROOT / "docs" / "plans" / "2026-07-07-yaml-retirement-program.md"
    ).read_text(encoding="utf-8")
    task_6 = program.split("### Task 6:", 1)[1].split("### Task 7:", 1)[0]
    plan_match = re.search(
        r"docs/plans/[0-9]{4}-[0-9]{2}-[0-9]{2}-yaml-retirement-task-6-execution-plan\.md",
        task_6,
    )
    assert plan_match is not None
    governing_plan = plan_match.group(0)
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", governing_plan],
        cwd=REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert tracked.returncode == 0, tracked.stderr
    assert tracked.stdout.splitlines() == [governing_plan]


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
    assert "task 4" in _normalized_routing_text(index_routing)
    _assert_migration_wave_complete_and_yaml_stage_closed(
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
        "Stage 6 YAML retirement Task 1 remains current.",
        "Stage 6 YAML retirement Task 2 remains current.",
        "Stage 6 YAML retirement Task 3 remains current.",
        "Stage 6 YAML retirement Task 4 is current.",
        "Stage 6 YAML retirement Task 5 is current.",
        "Stage 6 YAML retirement Task 6 is current.",
        "Stage 6 YAML retirement Task 7 is current.",
        "Stage 7 has not started and awaits an owner-scheduled design review.",
    ),
)
def test_stage_6_closeout_guard_rejects_stale_or_premature_routing(
    replacement: str,
) -> None:
    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Current procedure-first substrate:**", 1
    )[0]
    mutated = docs_index_routing + "\n" + replacement

    with pytest.raises(AssertionError):
        _assert_migration_wave_complete_and_yaml_stage_closed(
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


def test_design_delta_primary_remains_routed_after_yaml_archive() -> None:
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
    assert yaml_path not in workflow_catalog

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


def test_docs_index_preserves_completed_roadmap_order() -> None:
    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Current procedure-first substrate:**", 1
    )[0]
    routing_surfaces = {"docs index": docs_index_routing}
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

def test_provider_call_policy_is_a_separate_generic_implemented_capability() -> None:
    gap_list_path = REPO_ROOT / "docs" / "workflow_yaml_orc_gap_list.md"
    row = _markdown_table_row(gap_list_path, "`common.provider-call-policy`")
    normalized_row = _normalized_routing_text(row)
    normalized_gap_list = _normalized_routing_text(
        gap_list_path.read_text(encoding="utf-8")
    )

    assert "implemented" in normalized_row
    assert "typed model" in normalized_row
    assert "effort" in normalized_row
    assert "positive literal timeout" in normalized_row
    assert "public compile run resume" in normalized_row
    assert "generic implementation closure" in normalized_gap_list
    assert "both survivor families have closed parity and promotion" in normalized_gap_list
    assert "both former yaml twins are retired" in normalized_gap_list
    assert "yaml deletion remains pending" not in normalized_gap_list


def test_provider_invocation_profile_is_separate_generic_implemented_data() -> None:
    gap_list_path = REPO_ROOT / "docs" / "workflow_yaml_orc_gap_list.md"
    row = _markdown_table_row(
        gap_list_path,
        "`common.provider-invocation-profile`",
    )
    normalized_row = _normalized_routing_text(row)

    assert "implemented" in normalized_row
    assert "shared no default unrestricted codex claude profiles" in normalized_row
    assert "codex_unrestricted_workspace" in row
    assert "claude_unrestricted_workspace" in row
    assert (
        '["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", '
        '"--skip-git-repo-check", "--model", "${model}", "--config", '
        '"reasoning_effort=${reasoning_effort}"]'
    ) in row
    assert (
        '["claude", "-p", "--model", "${model}", "--effort", "${effort}", '
        '"--permission-mode", "bypassPermissions"]'
    ) in row
    assert "`defaults={}`" in row
    assert "`input_mode=stdin`" in row
    assert "exact argv profile evidence" in normalized_row


def test_prompt_dependency_contract_is_routed_as_generic_implemented_capability() -> None:
    matrix_path = REPO_ROOT / "docs" / "capability_status_matrix.md"
    matrix_row = _markdown_table_row(
        matrix_path,
        "Workflow Lisp provider prompt dependencies",
    )
    normalized_row = _normalized_routing_text(matrix_row)
    docs_index = _normalized_routing_text(
        (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    )
    design_index = _normalized_routing_text(
        (REPO_ROOT / "docs" / "design" / "README.md").read_text(encoding="utf-8")
    )

    assert "implemented" in normalized_row
    assert "required and optional exact relpaths" in normalized_row
    assert "262144 byte" in normalized_row
    assert "one immutable snapshot per attempt" in normalized_row
    assert "fresh snapshot on retry" in normalized_row
    assert "runtime plan remains topology only" in normalized_row
    assert "evidence is non authoritative" in normalized_row
    assert "historical yaml content mode behavior" in normalized_row
    assert "no live authored frontend" in normalized_row
    assert "yaml content mode remains legacy" not in normalized_row
    assert "verified_iteration_drain" in matrix_row
    assert "closed their family parity and promotion gates" in normalized_row
    assert "generic_run_watchdog" in matrix_row
    assert "both" in normalized_row and "parity and promotion" in normalized_row
    assert "yaml twins are retired" in normalized_row
    assert "all yaml deletion remains pending" not in normalized_row
    assert "workflow lisp provider prompt dependencies" in docs_index
    assert "workflow lisp provider prompt dependencies" in design_index


def test_task_12_scope_is_functional_and_review_subject_is_frozen() -> None:
    plan = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-17-workflow-lisp-provider-prompt-dependencies-implementation-plan.md"
    ).read_text(encoding="utf-8")
    task_12 = plan.split("## Task 12:", 1)[1].split("## Task 13:", 1)[0]

    assert "functional contracts" in task_12.lower()
    for step in range(1, 7):
        assert f"- [x] **Step {step}:" in task_12
    assert "- [x] **Step 7:" in task_12


def test_final_yaml_holdout_is_retired_and_authored_workflow_estate_is_empty() -> None:
    assert all(not (REPO_ROOT / path).exists() for path in FINAL_YAML_HOLDOUT_PATHS)
    assert sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "workflows").rglob("*")
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    ) == []


def test_language_server_l2_l3_l5_are_complete_and_route_l4_final_gate() -> None:
    roadmap = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md"
    ).read_text(encoding="utf-8")
    design = (
        REPO_ROOT / "docs" / "design" / "workflow_lisp_language_server.md"
    ).read_text(encoding="utf-8")
    frontend = (
        REPO_ROOT
        / "docs"
        / "design"
        / "workflow_lisp_frontend_specification.md"
    ).read_text(encoding="utf-8")
    setup = (
        REPO_ROOT / "docs" / "workflow_lisp_language_server_setup.md"
    ).read_text(encoding="utf-8")
    drafting = (
        REPO_ROOT / "docs" / "lisp_workflow_drafting_guide.md"
    ).read_text(encoding="utf-8")

    l2_row = next(
        line
        for line in roadmap.splitlines()
        if line.startswith("| L2 |")
    )
    normalized_l2_row = _normalized_routing_text(l2_row)
    assert "complete" in normalized_l2_row
    assert "implementation through 10e3ccc3" in normalized_l2_row
    assert "l2_final_spec_approved" in normalized_l2_row
    assert "l2_final_quality_approved" in normalized_l2_row
    l3_row = next(
        line
        for line in roadmap.splitlines()
        if line.startswith("| L3 |")
    )
    normalized_l3_row = _normalized_routing_text(l3_row)
    assert "complete" in normalized_l3_row
    assert (
        "implementation through fc1b01ee, 9e59929d, and "
        "xdist evidence correction 8c704f3f"
    ) in normalized_l3_row
    assert "l3_task1_spec_approved" in normalized_l3_row
    assert "l3_task1_quality_approved" in normalized_l3_row
    assert "l3_task2_spec_approved" in normalized_l3_row
    assert "l3_task2_quality_approved" in normalized_l3_row
    assert "compile path reentrancy" in normalized_l3_row
    l4_row = next(
        line
        for line in roadmap.splitlines()
        if line.startswith("| L4 |")
    )
    normalized_l4_row = _normalized_routing_text(l4_row)
    assert "ordered l4_design_spec_approved then l4_design_quality_approved" in (
        normalized_l4_row
    )
    assert "reviewed implementation plan" in normalized_l4_row
    assert Path(LANGUAGE_SERVER_L4_PLAN_PATH).name in l4_row
    assert "l4_plan_spec_approved" in normalized_l4_row
    assert "l4_plan_quality_approved" in normalized_l4_row
    assert "implemented through 11629551 and 0d5f7009" in normalized_l4_row
    assert "l4_task1_spec_approved" in normalized_l4_row
    assert "l4_task1_quality_approved" in normalized_l4_row
    assert "l4_task2_spec_approved" in normalized_l4_row
    assert "l4_task2_quality_approved" in normalized_l4_row
    assert "real neovim acceptance passed" in normalized_l4_row
    assert "task 4 focused 356 passed and broad comparison has zero new failures" in (
        normalized_l4_row
    )
    assert "no l4 behavior is implemented" not in normalized_l4_row
    assert "blocked by l3" not in normalized_l4_row
    l2_plan = (
        REPO_ROOT
        / "docs"
        / "plans"
        / "2026-07-27-workflow-lisp-language-server-l2-implementation-plan.md"
    ).read_text(encoding="utf-8")
    normalized_l2_plan = _normalized_routing_text(l2_plan)
    assert "execution status: complete" in normalized_l2_plan
    assert "l2_plan_spec_approved" in normalized_l2_plan
    assert "l2_plan_quality_approved" in normalized_l2_plan
    assert "l2_final_spec_approved" in normalized_l2_plan
    assert "l2_final_quality_approved" in normalized_l2_plan
    for label, surface in {
        "language-server design": design,
        "frontend specification": frontend,
        "setup guide": setup,
        "drafting guide": drafting,
    }.items():
        normalized = _normalized_routing_text(surface)
        assert "process frozen form registry" in normalized, label
        assert "isincomplete=true" in normalized, label
        assert "configuration stale" in normalized, label
        assert "no stale callable" in normalized, label
        assert "implemented" in normalized, label
        assert "definition" in normalized, label
        assert "document symbol" in normalized, label

    stale_l3_routing = (
        "l3 awaits substrate mr-4",
        "l3 per-source entry selection remains gated on mr-4",
        "global pipeline state forbids concurrency",
        "compiles are strictly serialized within the server process "
        "(pipeline global state)",
    )
    for label, surface in {
        "language-server design": design,
        "active roadmap": roadmap,
        "setup guide": setup,
    }.items():
        normalized = _normalized_routing_text(surface)
        for stale in stale_l3_routing:
            assert _normalized_routing_text(stale) not in normalized, (
                label,
                stale,
            )

    stale_l2_routing = (
        "l2's design amendment/review gate is next",
        "l2 begins only with its separate design amendment and review gate",
        "must not be read back into this setup guide",
        "runtime remains l1 until the plan closes",
        "l2 is not yet implemented",
    )
    for stale in stale_l2_routing:
        assert stale not in _normalized_routing_text(frontend)
        assert stale not in _normalized_routing_text(
            (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
        )


def test_language_server_l3_routes_shipped_per_source_entry_selection() -> None:
    plan_path = REPO_ROOT / LANGUAGE_SERVER_L3_PLAN_PATH
    plan = plan_path.read_text(encoding="utf-8")
    normalized_plan = _normalized_routing_text(plan)
    roadmap_path = REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH
    l3_row = _markdown_table_row(roadmap_path, "| L3 |")
    normalized_l3_row = _normalized_routing_text(l3_row)
    design = (
        REPO_ROOT / "docs/design/workflow_lisp_language_server.md"
    ).read_text(encoding="utf-8")
    design_router_row = _markdown_table_row(
        REPO_ROOT / "docs/design/README.md",
        "workflow_lisp_language_server.md",
    )
    capability_row = _markdown_table_row(
        REPO_ROOT / "docs/capability_status_matrix.md",
        "Workflow Lisp language server L3 per-source entry selection",
    )
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")
    setup = (
        REPO_ROOT / "docs/workflow_lisp_language_server_setup.md"
    ).read_text(encoding="utf-8")
    assert "execution status: complete" in normalized_plan
    assert "l3_plan_spec_approved" in normalized_plan
    assert "l3_plan_quality_approved" in normalized_plan
    assert "l3_task1_spec_approved" in normalized_plan
    assert "l3_task1_quality_approved" in normalized_plan
    assert "l3_task2_spec_approved" in normalized_plan
    assert "l3_task2_quality_approved" in normalized_plan
    assert "l3_final_spec_approved" in normalized_plan
    assert "l3_final_quality_approved" in normalized_plan
    assert "fc1b01ee" in normalized_plan
    assert "9e59929d" in normalized_plan
    assert "8c704f3f" in normalized_plan
    for task_number in (1, 2, 3):
        assert f"## Task {task_number}:" in plan
    assert "## Task 4:" not in plan
    assert "superpowers:subagent-driven-development" in plan
    assert "superpowers:test-driven-development" in plan
    assert "do not create a worktree" in normalized_plan

    assert "complete" in normalized_l3_row
    assert "l3_final_spec_approved" in normalized_l3_row
    assert "l3_final_quality_approved" in normalized_l3_row
    assert (
        "implementation through fc1b01ee, 9e59929d, and "
        "xdist evidence correction 8c704f3f"
    ) in normalized_l3_row
    assert Path(LANGUAGE_SERVER_L3_PLAN_PATH).name in l3_row
    assert LANGUAGE_SERVER_L3_PLAN_PATH in design
    assert Path(LANGUAGE_SERVER_L3_PLAN_PATH).name in design_router_row
    assert Path(LANGUAGE_SERVER_L3_PLAN_PATH).name in capability_row
    assert "| Implemented |" in capability_row
    assert Path(LANGUAGE_SERVER_L3_PLAN_PATH).name in index
    assert (
        "### [Workflow Lisp Language Server L3 Per-Source Entry Selection "
        "Implementation Plan]" in index
    )
    normalized_setup = _normalized_routing_text(setup)
    assert "entry_workflows" in normalized_setup
    assert "exact canonical source path" in normalized_setup
    assert "unlisted source request carries no requested workflow" in normalized_setup
    assert "current shipped scalar selection" not in normalized_setup
    assert "accepted, not yet shipped" not in normalized_setup
    assert "| entry_workflow |" not in setup
    assert "l3 target initialization" not in normalized_setup


def test_language_server_l4_routes_completed_external_review() -> None:
    roadmap_path = REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH
    plan_path = REPO_ROOT / LANGUAGE_SERVER_L4_PLAN_PATH
    design_path = (
        REPO_ROOT
        / "docs"
        / "design"
        / "workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md"
    )
    baseline_path = (
        REPO_ROOT / "docs" / "design" / "workflow_lisp_language_server.md"
    )
    index_path = REPO_ROOT / "docs" / "index.md"
    setup_path = (
        REPO_ROOT / "docs" / "workflow_lisp_language_server_setup.md"
    )

    l4_row = _markdown_table_row(roadmap_path, "| L4 |")
    normalized_l4_row = _normalized_routing_text(l4_row)
    assert "implemented through 11629551 and 0d5f7009" in normalized_l4_row
    assert "l4_task1_spec_approved" in normalized_l4_row
    assert "l4_task1_quality_approved" in normalized_l4_row
    assert "l4_task2_spec_approved" in normalized_l4_row
    assert "l4_task2_quality_approved" in normalized_l4_row
    assert "bdd1e822" in normalized_l4_row
    assert "l4_task3_spec_approved" in normalized_l4_row
    assert "l4_task3_quality_approved" in normalized_l4_row
    assert "real neovim acceptance passed" in normalized_l4_row
    assert "task 4 focused 356 passed and broad comparison has zero new failures" in (
        normalized_l4_row
    )
    assert "l4_task4_spec_approved then l4_task4_quality_approved" in (
        normalized_l4_row
    )
    assert "l4_final_spec_approved then l4_final_quality_approved" in (
        normalized_l4_row
    )
    assert "complete at commit 251d9d53674e863fddae4535ea4f7022914287cd" in (
        normalized_l4_row
    )
    assert "tree e2417d395cbcabe9adaffb136759ebff3d42b677" in normalized_l4_row
    assert (
        "94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804"
        in normalized_l4_row
    )
    assert "q5_f1_f2_fix_spec_approved" in normalized_l4_row
    assert "q5_f1_f2_fix_quality_approved" in normalized_l4_row
    assert "final review metadata correction" not in normalized_l4_row
    assert "completion requires fresh ordered" not in normalized_l4_row

    capability_row = _markdown_table_row(
        REPO_ROOT / "docs" / "capability_status_matrix.md",
        "Workflow Lisp language server L4 diagnostic lifecycle/progress",
    )
    normalized_capability_row = _normalized_routing_text(capability_row)
    assert "| Implemented |" in capability_row
    assert "current only diagnostic" in normalized_capability_row
    assert "capability gated" in normalized_capability_row
    assert "logical serialized compile pump" in normalized_capability_row
    assert "neovim" in normalized_capability_row
    assert "356 passed" in normalized_capability_row
    assert "zero new failures" in normalized_capability_row
    assert "251d9d53674e863fddae4535ea4f7022914287cd" in (
        normalized_capability_row
    )
    assert "e2417d395cbcabe9adaffb136759ebff3d42b677" in normalized_capability_row
    assert (
        "94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804"
        in normalized_capability_row
    )
    assert "l4_final_spec_approved then l4_final_quality_approved" in (
        normalized_capability_row
    )
    assert "completion requires fresh ordered" not in normalized_capability_row

    design = design_path.read_text(encoding="utf-8")
    normalized_design_status = _normalized_routing_text(
        "\n".join(design.splitlines()[:35])
    )
    assert "status: implemented, incorporated, and complete" in (
        normalized_design_status
    )
    assert "11629551" in normalized_design_status
    assert "0d5f7009" in normalized_design_status
    assert "l4_task3_spec_approved" in normalized_design_status
    assert "l4_task3_quality_approved" in normalized_design_status
    assert "251d9d53674e863fddae4535ea4f7022914287cd" in normalized_design_status
    assert "e2417d395cbcabe9adaffb136759ebff3d42b677" in normalized_design_status
    assert (
        "94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804"
        in normalized_design_status
    )
    assert "implementation pending" not in normalized_design_status

    baseline = _normalized_routing_text(
        baseline_path.read_text(encoding="utf-8")
    )
    assert "current only diagnostic presentation" in baseline
    assert "capability gated" in baseline
    assert "one logical serialized compile pump busy interval" in baseline
    assert "accepted l4 target pending" not in baseline

    plan = _normalized_routing_text(plan_path.read_text(encoding="utf-8"))
    assert "task 1 commit" in plan
    assert "11629551" in plan
    assert "l4_task1_spec_approved" in plan
    assert "l4_task1_quality_approved" in plan
    assert "task 2 commit" in plan
    assert "0d5f7009" in plan
    assert "l4_task2_spec_approved" in plan
    assert "l4_task2_quality_approved" in plan
    assert "task 3 commit" in plan
    assert "bdd1e822" in plan
    assert "l4_task3_spec_approved" in plan
    assert "l4_task3_quality_approved" in plan
    assert "repository real neovim acceptance" in plan
    assert "356 tests in 70.94 seconds" in plan
    assert "1a19ac9339d54dd9416cbdbded1af1b8e1688b0d5ca8589a37f44ef520fee966" in plan
    assert "10,895 passed, 41 failed, 0 errors, 22 skipped" in plan
    assert "6f071f35bf086f027ce6445f3c83114f4812f06025ec565fe32123c37ab627a4" in plan
    assert "zero new failures" in plan
    assert "251d9d53674e863fddae4535ea4f7022914287cd" in plan
    assert "e2417d395cbcabe9adaffb136759ebff3d42b677" in plan
    assert "94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804" in plan
    assert "29e0bc01037058f0c29dac15c0d461798a5e47a836fe8b3e8336beb937410951" in plan
    assert "357 passed in 72.49 seconds" in plan
    assert "9512fd4ead25182d0460c579f5a33d80d100659077ab4f0393b2c8b126332fb0" in plan
    assert "l4_final_spec_approved then l4_final_quality_approved" in plan
    assert "completion requires fresh ordered" not in plan

    index = index_path.read_text(encoding="utf-8")
    normalized_index = _normalized_routing_text(index)
    assert "l4 diagnostic lifecycle and compile progress" in normalized_index
    assert "task 4 focused 356 passed and broad comparison has zero new failures" in (
        normalized_index
    )
    assert "q5 is complete at 70f4a759, tree fec729cb" in normalized_index
    assert "external ordered final reviews" in normalized_index
    lifecycle_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp LSP Diagnostic Lifecycle And Compile Progress]",
        )
    )
    assert "bdd1e822" in lifecycle_index
    assert "356 passed" in lifecycle_index
    assert "zero new failures" in lifecycle_index
    assert "l4_task4_spec_approved then l4_task4_quality_approved" in (
        lifecycle_index
    )
    assert "l4_final_spec_approved then l4_final_quality_approved" in lifecycle_index
    assert "251d9d53674e863fddae4535ea4f7022914287cd" in lifecycle_index
    assert "e2417d395cbcabe9adaffb136759ebff3d42b677" in lifecycle_index
    assert "complete" in lifecycle_index
    assert "completion requires fresh ordered" not in lifecycle_index
    assert "task 4 broad comparison and final closure are next" not in lifecycle_index
    plan_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp L4 Diagnostic Lifecycle And Compile Progress "
            "Implementation Plan]",
        )
    )
    assert "bdd1e822" in plan_index
    assert "356 passed" in plan_index
    assert "zero new failures" in plan_index
    assert "l4_task4_spec_approved then l4_task4_quality_approved" in plan_index
    assert "l4_final_spec_approved then l4_final_quality_approved" in plan_index
    assert "251d9d53674e863fddae4535ea4f7022914287cd" in plan_index
    assert "e2417d395cbcabe9adaffb136759ebff3d42b677" in plan_index
    assert "complete" in plan_index
    assert "completion requires fresh ordered" not in plan_index
    assert "task 4 broad comparison and final closure are next" not in plan_index
    normalized_setup = _normalized_routing_text(setup_path.read_text())
    assert "old squiggles disappear on an unsaved edit" in normalized_setup
    assert "workdoneprogress" in normalized_setup
    assert "one indeterminate progress lifecycle" in normalized_setup

    q4_row = _normalized_routing_text(
        _markdown_table_row(roadmap_path, "| Q4 |")
    )
    q5_row = _normalized_routing_text(
        _markdown_table_row(roadmap_path, "| Q5 |")
    )
    l5_row = _normalized_routing_text(
        _markdown_table_row(roadmap_path, "| L5 |")
    )
    assert "concrete generic reviewer/panel consumer is bound" in q4_row
    assert "original design accepted at d7fe4549" in q4_row
    assert "current target 2.23 phased production" in q4_row
    assert "target 2.23 explicit composed panel sibling" in q4_row
    assert "frozen target 2.21 compatibility control" in q4_row
    assert "q5 era design amendment accepted at 3c21ceb4" in q4_row
    assert "implementation plan" in q4_row
    assert "reviewed amended plan 0f21636b" in q4_row
    assert (
        "complete at commit f3335637b90feb0a87ac4c538bafac7704ac0d87"
        in q4_row
    )
    assert "tree ccec170be8757c9e4fd5ed8ece6f93b04fc03299" in q4_row
    assert (
        "85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c"
        in q4_row
    )
    assert "postcommit focused control passed 74 tests" in q4_row
    assert "implemented closure candidate" not in q4_row
    assert "external task 9 and final ordered reviews" not in q4_row
    assert "implementation not started" not in q4_row
    assert "q5 task 14 and canonical transplant are complete" in q4_row
    assert "no q4 dependency" in q5_row
    assert "complete at 70f4a759, tree fec729cb" in q5_row
    assert "external ordered q5_final_spec_approved then q5_final_quality_approved" in q5_row
    assert "complete" in l5_row
    assert "041754e6" in l5_row


def test_language_server_l4_completion_routes_exact_external_review_record() -> None:
    roadmap_path = REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH
    roadmap = roadmap_path.read_text(encoding="utf-8")
    capability_row = _markdown_table_row(
        REPO_ROOT / "docs" / "capability_status_matrix.md",
        "Workflow Lisp language server L4 diagnostic lifecycle/progress",
    )
    design_router_path = REPO_ROOT / "docs" / "design" / "README.md"
    design_router_rows = [
        _markdown_table_row(design_router_path, "workflow_lisp_language_server.md"),
        _markdown_table_row(
            design_router_path,
            "workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md",
        ),
    ]
    design_headers = [
        "\n".join(
            (
                REPO_ROOT / "docs" / "design" / "workflow_lisp_language_server.md"
            )
            .read_text(encoding="utf-8")
            .splitlines()[:45]
        ),
        "\n".join(
            (
                REPO_ROOT
                / "docs"
                / "design"
                / "workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md"
            )
            .read_text(encoding="utf-8")
            .splitlines()[:35]
        ),
    ]
    plan = (
        REPO_ROOT / LANGUAGE_SERVER_L4_PLAN_PATH
    ).read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    roadmap_l4_stage = roadmap.split(
        "## Stage L4: Diagnostic Lifecycle And Compile Progress",
        1,
    )[1].split("\n## ", 1)[0]
    index_sections = [
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Language Quality And Domain Semantics Roadmap]",
        ),
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Language Server]",
        ),
        _markdown_heading_section(
            index,
            "### [Workflow Lisp LSP Diagnostic Lifecycle And Compile Progress]",
        ),
        _markdown_heading_section(
            index,
            "### [Workflow Lisp L4 Diagnostic Lifecycle And Compile Progress "
            "Implementation Plan]",
        ),
    ]
    surfaces = [
        _markdown_table_row(roadmap_path, "| L4 |"),
        roadmap_l4_stage,
        capability_row,
        *design_router_rows,
        *design_headers,
        plan,
        *index_sections,
    ]

    for surface in surfaces:
        normalized = _normalized_routing_text(surface)
        assert "251d9d53674e863fddae4535ea4f7022914287cd" in normalized
        assert "e2417d395cbcabe9adaffb136759ebff3d42b677" in normalized
        assert (
            "94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804"
            in normalized
        )
        assert "l4_final_spec_approved then l4_final_quality_approved" in normalized
        assert "complete" in normalized
        assert "completion requires fresh ordered" not in normalized
        assert "final review metadata correction" not in normalized

    normalized_plan = _normalized_routing_text(plan)
    assert "1f64f153" in normalized_plan
    assert "7790ee0e" in normalized_plan
    assert "changes_required" in normalized_plan
    assert "superseded" in normalized_plan
    assert "29e0bc01037058f0c29dac15c0d461798a5e47a836fe8b3e8336beb937410951" in (
        normalized_plan
    )
    assert "357 passed in 72.49 seconds" in normalized_plan
    assert "9512fd4ead25182d0460c579f5a33d80d100659077ab4f0393b2c8b126332fb0" in (
        normalized_plan
    )


def test_language_server_l5_routes_shipped_admitted_shapes_and_closes_stage() -> None:
    roadmap_path = REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH
    design_path = (
        REPO_ROOT
        / "docs"
        / "design"
        / "workflow_lisp_lsp_authored_reference_navigation.md"
    )
    design_router_path = REPO_ROOT / "docs" / "design" / "README.md"
    capability_matrix_path = REPO_ROOT / "docs" / "capability_status_matrix.md"
    plan_path = REPO_ROOT / LANGUAGE_SERVER_L5_PLAN_PATH
    index = (REPO_ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    l5_row = _markdown_table_row(roadmap_path, "| L5 |")
    normalized_l5_row = _normalized_routing_text(l5_row)
    assert "accepted design at b8a41172" in normalized_l5_row
    assert "prompt heads" in normalized_l5_row
    assert "final unexpanded direct retained proc ref" in normalized_l5_row
    assert "non generated, non specialized authored owners" in normalized_l5_row
    assert "every macro head remain null" in normalized_l5_row
    assert "complete" in normalized_l5_row
    assert "041754e6" in normalized_l5_row
    assert Path(LANGUAGE_SERVER_L5_PLAN_PATH).name in l5_row

    design = design_path.read_text(encoding="utf-8")
    normalized_design_status = _normalized_routing_text(
        "\n".join(design.splitlines()[:20])
    )
    assert "status: implemented and incorporated" in normalized_design_status
    assert "95e05c01" in normalized_design_status
    assert "041754e6" in normalized_design_status
    assert "macro heads still defer shape wide" in normalized_design_status
    assert Path(LANGUAGE_SERVER_L5_PLAN_PATH).name in design

    design_router_row = _markdown_table_row(
        design_router_path,
        "workflow_lisp_lsp_authored_reference_navigation.md",
    )
    assert "| Implemented and incorporated |" in design_router_row
    assert Path(LANGUAGE_SERVER_L5_PLAN_PATH).name in design_router_row

    capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp language server L5 authored reference navigation",
    )
    normalized_capability_row = _normalized_routing_text(capability_row)
    assert "| Implemented |" in capability_row
    assert "optional read only authored to authored" in normalized_capability_row
    assert "macro heads remain null shape wide" in normalized_capability_row
    assert "compiler catalog joins ship" in normalized_capability_row
    assert Path(LANGUAGE_SERVER_L5_PLAN_PATH).name in capability_row

    plan = plan_path.read_text(encoding="utf-8")
    normalized_plan = _normalized_routing_text(plan)
    assert "# Workflow Lisp L5 Authored Reference Navigation Implementation Plan" in (
        plan
    )
    assert "pre review task 6 execution record" in normalized_plan
    assert "l5_plan_spec_approved" in normalized_plan
    assert "l5_plan_quality_approved" in normalized_plan
    assert "95e05c01" in normalized_plan
    assert "041754e6" in normalized_plan
    assert "post candidate broad comparison" in normalized_plan
    assert "pending" in normalized_plan
    assert "no compiler/frontend or non navigation production file changed" in (
        normalized_plan
    )
    assert "macro heads remain null shape wide" in normalized_plan

    assert (
        "### [Workflow Lisp L5 Authored Reference Navigation Implementation Plan]"
        in index
    )
    assert Path(LANGUAGE_SERVER_L5_PLAN_PATH).name in index
    normalized_index = _normalized_routing_text(index)
    assert "shipped execution and closure record" in normalized_index
    assert "l3 completed over mr 4 under its reviewed plan" in normalized_index

    l3_row = _markdown_table_row(roadmap_path, "| L3 |")
    normalized_l3_row = _normalized_routing_text(l3_row)
    assert "complete" in normalized_l3_row
    assert (
        "implementation through fc1b01ee, 9e59929d, and "
        "xdist evidence correction 8c704f3f"
    ) in normalized_l3_row


def test_phased_contract_delivery_routes_completed_surface() -> None:
    roadmap_path = REPO_ROOT / LANGUAGE_QUALITY_ROADMAP_PATH
    design_path = REPO_ROOT / PHASED_CONTRACT_DELIVERY_DESIGN_PATH
    plan_path = REPO_ROOT / PHASED_CONTRACT_DELIVERY_PLAN_PATH
    design_router_path = REPO_ROOT / "docs/design/README.md"
    capability_matrix_path = REPO_ROOT / "docs/capability_status_matrix.md"
    dsl_spec = (REPO_ROOT / "specs/dsl.md").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")

    normalized_design_status = _normalized_routing_text(
        "\n".join(design_path.read_text(encoding="utf-8").splitlines()[:18])
    )
    assert "status: implemented and complete at target 2.23" in normalized_design_status
    assert "bb67f680" in normalized_design_status
    assert "70f4a759" in normalized_design_status
    assert "fec729cb" in normalized_design_status
    assert "3fc3a09e" in normalized_design_status
    assert "superseded historical provenance" in normalized_design_status
    assert "external ordered final reviews" in normalized_design_status

    q5_row = _markdown_table_row(roadmap_path, "| Q5 |")
    normalized_q5_row = _normalized_routing_text(q5_row)
    assert "accepted design at 872a29af" in normalized_q5_row
    assert "reviewed implementation plan at 45468c55" in normalized_q5_row
    assert "q3 complete" in normalized_q5_row
    assert "no q4 dependency" in normalized_q5_row
    assert "complete at 70f4a759, tree fec729cb" in normalized_q5_row
    assert "post correction broad comparison" in normalized_q5_row
    assert "exact delta adjudication" in normalized_q5_row
    assert "external ordered q5_final_spec_approved then q5_final_quality_approved" in normalized_q5_row

    design_router_row = _markdown_table_row(
        design_router_path,
        "workflow_lisp_phased_contract_delivery.md",
    )
    assert "| Implemented and complete at `70f4a759` |" in design_router_row
    normalized_design_router_row = _normalized_routing_text(design_router_row)
    assert "872a29af" in normalized_design_router_row
    assert "45468c55" in normalized_design_router_row
    assert "3fc3a09e" in normalized_design_router_row
    assert "explicitly superseded history" in normalized_design_router_row
    assert "external ordered final reviews" in normalized_design_router_row
    assert "tree fec729cb" in normalized_design_router_row

    capability_row = _markdown_table_row(
        capability_matrix_path,
        "Workflow Lisp phased contract delivery Q5",
    )
    normalized_capability_row = _normalized_routing_text(capability_row)
    assert "| Implemented |" in capability_row
    assert "accepted design 872a29af" in normalized_capability_row
    assert "reviewed plan 45468c55" in normalized_capability_row
    assert "complete at 70f4a759, tree fec729cb" in normalized_capability_row
    assert "real invalid then valid attempt 10 passed" in normalized_capability_row
    assert "3fc3a09e is superseded history" in normalized_capability_row
    assert "external ordered final reviews closed task 14" in normalized_capability_row
    assert Path(PHASED_CONTRACT_DELIVERY_PLAN_PATH).name in capability_row

    normalized_design_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Phased Contract Delivery]",
        )
    )
    assert "implemented and closed target 2.23 stage q5 surface" in normalized_design_index
    assert "bb67f680" in normalized_design_index
    assert "70f4a759" in normalized_design_index
    assert "fec729cb" in normalized_design_index
    assert "3fc3a09e" in normalized_design_index
    assert "superseded historical provenance" in normalized_design_index
    assert "q5_final_spec_approved then q5_final_quality_approved" in (
        normalized_design_index
    )

    assert (
        "### [Workflow Lisp Phased Contract Delivery Implementation Plan]"
        in index
    )
    normalized_plan_index = _normalized_routing_text(
        _markdown_heading_section(
            index,
            "### [Workflow Lisp Phased Contract Delivery Implementation Plan]",
        )
    )
    assert "reviewed q5 execution plan" in normalized_plan_index
    assert "45468c55" in normalized_plan_index
    assert "tasks 1 13 are complete through bb67f680" in normalized_plan_index
    assert "task 14 closes at 70f4a759" in normalized_plan_index
    assert "3fc3a09e" in normalized_plan_index
    assert "explicitly superseded historical provenance" in normalized_plan_index
    assert "external final exact tree reviews at 70f4a759" in normalized_plan_index
    assert Path(PHASED_CONTRACT_DELIVERY_PLAN_PATH).name in index

    plan = plan_path.read_text(encoding="utf-8")
    normalized_plan = _normalized_routing_text(plan)
    assert "Q5_PLAN_SPEC_APPROVED" in plan
    assert "Q5_PLAN_QUALITY_APPROVED" in plan
    assert "872a29af13f140d53b3637b475859496a50d5724" in plan
    assert "## 2026-07-28 Task 13 Stop Record" in plan
    assert "historical provenance, superseded on 2026 07 29." in normalized_plan
    assert "withheld" in plan
    assert "Task 14 has not started" in plan
    assert "Do not infer a split-proof substitution" in plan
    assert "## 2026-07-29 Task 13 Completion Record" in plan
    assert "bb67f680" in plan
    assert "1 passed in 47.29s" in plan
    assert "passed 2,245 tests" in normalized_plan
    assert "Q5_TASK13_SPEC_APPROVED" in plan
    assert "Q5_TASK13_QUALITY_APPROVED" in plan
    assert "## 2026-07-29 Task 14 Pre-Correction Candidate Record" in plan
    assert "10,919 passed, 42 failed, 23 skipped, 0 errors, and 33 warnings" in (
        normalized_plan
    )
    assert "predates correction 5d8a3151" in normalized_plan
    assert "truthful superseded candidate evidence" in normalized_plan
    assert "fresh post correction replay" in normalized_plan
    assert "exact delta adjudication" in normalized_plan
    assert "against the post p2 baseline remain required" in normalized_plan
    assert "q5_final_spec_approved then q5_final_quality_approved" in normalized_plan
    assert "## 2026-07-29 Task 14 Final Closure Record" in plan
    assert "70f4a7597b915d511ac70084a40fe342617fe91b" in plan
    assert "fec729cb45ed9212dec14e1a72ac9e1cd1110a2a" in plan
    assert "10,925 passed, 38 failed, 23 skipped" in normalized_plan
    assert "focused q5 selector: 2,306 passed" in normalized_plan
    assert "task 14 and q5 are complete" in normalized_plan

    normalized_dsl_spec = _normalized_routing_text(dsl_spec)
    assert (
        "compilation fails with provider_phased_delivery_policy_invalid and "
        "reason fragment_application_required or contract_suffix_required"
    ) in normalized_dsl_spec
    assert (
        "delivery/identity carriers fail closed with "
        "provider_phased_delivery_carriage_mismatch"
    ) in normalized_dsl_spec
    assert (
        "identity version disagreement uses reason "
        "attempt_identity_version_mismatch"
    ) in normalized_dsl_spec
    assert (
        "provider_phased_delivery_fragment_application_required" not in dsl_spec
    )
    assert (
        "provider_phased_delivery_contract_suffix_required" not in dsl_spec
    )


def test_m1_estate_shrink_routes_the_completed_m0_boundary_and_bounded_deletion_plan() -> None:
    track = (REPO_ROOT / SUBSTRATE_MAINTENANCE_TRACK_PATH).read_text(
        encoding="utf-8"
    )
    m0_plan = (REPO_ROOT / M0_GREEN_BASELINE_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    m1_plan = (REPO_ROOT / M1_ESTATE_SHRINK_PLAN_PATH).read_text(
        encoding="utf-8"
    )
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")
    pure_replay_design = (
        REPO_ROOT / PURE_RESULT_REPLAY_DESIGN_PATH
    ).read_text(encoding="utf-8")
    pure_replay_plan = (
        REPO_ROOT / PURE_RESULT_REPLAY_PLAN_PATH
    ).read_text(encoding="utf-8")
    pure_replay_activation_plan = (
        REPO_ROOT / PURE_RESULT_REPLAY_ACTIVATION_PLAN_PATH
    ).read_text(encoding="utf-8")
    checkpoint_design = (
        REPO_ROOT / LEXICAL_EXECUTION_CHECKPOINTS_DESIGN_PATH
    ).read_text(encoding="utf-8")
    state_layout_design = (
        REPO_ROOT / WORKFLOW_LISP_STATE_LAYOUT_DESIGN_PATH
    ).read_text(encoding="utf-8")
    design_index = (REPO_ROOT / DESIGN_INDEX_PATH).read_text(encoding="utf-8")
    capability_matrix = (
        REPO_ROOT / CAPABILITY_STATUS_MATRIX_PATH
    ).read_text(encoding="utf-8")
    state_spec = (REPO_ROOT / STATE_SPEC_PATH).read_text(encoding="utf-8")

    assert Path(M0_GREEN_BASELINE_PLAN_PATH).name in track
    assert Path(M0_GREEN_BASELINE_PLAN_PATH).name in index
    assert Path(M1_ESTATE_SHRINK_PLAN_PATH).name in track
    assert Path(M1_ESTATE_SHRINK_PLAN_PATH).name in index
    assert Path(PURE_RESULT_REPLAY_PLAN_PATH).name in track
    assert Path(PURE_RESULT_REPLAY_PLAN_PATH).name in index
    assert Path(PURE_RESULT_REPLAY_ACTIVATION_PLAN_PATH).name in track
    assert Path(PURE_RESULT_REPLAY_ACTIVATION_PLAN_PATH).name in index
    assert Path(MC_COMMON_HELPER_PLAN_PATH).name in track
    assert Path(MC_COMMON_HELPER_PLAN_PATH).name in index
    assert "### [M1 Estate Shrink Implementation Plan]" in index

    m0_section = track.split("## Phase M0: Green Baseline", 1)[1].split(
        "## Phase M1: Estate Shrink",
        1,
    )[0]
    normalized_m0 = _normalized_routing_text(m0_section)
    assert "historical complete" in normalized_m0
    assert "f15b888d0c4862f7e229b990255d5f34c7392591" in m0_section
    assert "8a75f24fde68b657d2f84b28aa8b4d34df5089cf" in m0_section
    assert "passed 418 tests" in m0_section
    assert (
        "88f35cdd872ba9e5a9602d3e756ee81e2911c2384e74c6fa2388cdb907e2ba0e"
        in m0_section
    )
    assert Path(M0_GREEN_BASELINE_PLAN_PATH).name in m0_section

    track_header = track.split("## Objective", 1)[0]
    normalized_track_header = _normalized_routing_text(track_header)
    assert "m0 is historical complete" in normalized_track_header
    assert "m1 was selected" in normalized_track_header
    assert "m1 is historical complete" in normalized_track_header
    assert "57c2604e595d22dc9d9d656409607f81b332b5f8" in track_header
    assert "fc0fdbefe2cdd99cf0f9de604aa63582f79425ea" in track_header
    assert "postcommit selector passed" in normalized_track_header
    assert Path(M1_ESTATE_SHRINK_PLAN_PATH).name in track_header
    assert "later phase defaults remain recorded" in normalized_track_header
    assert "phase m2 is historical complete" in normalized_track_header
    assert "m3a tasks 1 3 landed" in normalized_track_header
    assert "m3a is historical complete" in normalized_track_header
    assert "first final quality review then found and rejected a cache hit witness bypass" in (
        normalized_track_header
    )
    assert "restarted final specification review then rejected that active form" in (
        normalized_track_header
    )
    assert (
        "passes 122 owner tests, the unchanged 259 production shape tests, a 381 "
        "test combined matrix, 569 test collection, a 968 test focused gate, and "
        "a 9,896 pass broad non security gate"
    ) in normalized_track_header
    assert "76427bdedbbac300bbd82d45db7fa6e24a770f84" in track_header
    assert "c5d8247ab6d47b209d14ee203513a0eda876acb1" in track_header
    assert "restarted ordered final reviews and a 189 pass postcommit control" in (
        normalized_track_header
    )
    assert (
        "fa8530a87a61f484e19ed1b3d5716f6e30b2061efb4ff12769bfc0b6051cf42b"
        in track_header
    )
    assert Path(PURE_RESULT_REPLAY_DESIGN_PATH).name in track_header
    normalized_track = _normalized_routing_text(track)
    assert "minimum m2/m3a correctness machinery" in normalized_track
    assert "strictly reduce both durable value count" in normalized_track
    assert "does not authorize adjacent refactoring" in normalized_track
    assert "mc implementation is complete through original task 5 commit" in (
        normalized_track_header
    )
    assert "task 6 terminal status is resolved only by the external record" in (
        normalized_track_header
    )
    assert "mr 4 is historical complete at 836721ce" in normalized_track_header
    listing_guard = next(
        clause
        for clause in normalized_track_header.split(".")
        if "not selected by listing" in clause
    )
    assert all(phase in listing_guard for phase in ("mr", "m3b", "m3c", "m4"))
    assert "mc" not in listing_guard
    assert "ml" not in listing_guard

    m1_section = track.split("## Phase M1: Estate Shrink", 1)[1].split(
        "## Phase ML:",
        1,
    )[0]
    normalized_m1 = _normalized_routing_text(m1_section)
    assert "status: historical complete" in normalized_m1
    assert "selected the exact task 0 candidate" in normalized_m1
    assert "57c2604e595d22dc9d9d656409607f81b332b5f8" in m1_section
    assert "fc0fdbefe2cdd99cf0f9de604aa63582f79425ea" in m1_section
    assert "postcommit selector passed" in normalized_m1
    assert Path(M1_ESTATE_SHRINK_PLAN_PATH).name in m1_section
    assert "route readiness" in normalized_m1
    assert "retained" in normalized_m1
    assert "frontend_kind" in m1_section
    assert "provenance" in normalized_m1
    assert "55,289" in m1_section

    ml_section = track.split(
        "## Phase ML: Provider At-Least-Once Loosening",
        1,
    )[1].split("## Phase MC:", 1)[0]
    normalized_ml = _normalized_routing_text(ml_section)
    assert "status: historical complete" in normalized_ml
    assert "selected" in normalized_ml
    assert "ml 0" in normalized_ml
    assert "normative contract" in normalized_ml
    assert "ml 1 closed at commit" in normalized_ml
    assert "task 7 verification" in normalized_ml
    assert "ordered final reviews" in normalized_ml
    assert "ml 2 closed at commit" in normalized_ml
    assert "ml 4 tasks 1 4 landed" in normalized_ml
    assert "e2e39422f8fe52ad35dd6a174bc108f65bcf2050" in ml_section
    assert "9c14dae37310755bd9cbd3de03b9256433acd9fe" in ml_section
    assert "0b149f96ace8873b0381a4cd530468b1d24a083f" in ml_section
    assert "b8783f66db4680bdec048e1b54ac14c1ae8b4d1b" in ml_section
    assert "b833b03cb91396cddf64a12cbbbc8d016cd306ad" in ml_section
    for task_commit in ("c45928f4", "b3370858", "ed19624c", "758c67e0"):
        assert task_commit in ml_section
    assert "postcommit control passed 72 tests" in normalized_ml
    for gate in (
        "5 e2e",
        "156 owning adjudication",
        "3 lock control tests with 120 deselected",
        "9,714 broad non security tests with 19 skipped and 5 warnings",
    ):
        assert gate in normalized_ml
    assert "does not auto select" in normalized_ml
    for component_plan in (
        ML1_PROVIDER_RECOVERY_PLAN_PATH,
        ML2_PROVIDER_ALLOCATOR_PLAN_PATH,
        ML4_ADJUDICATION_RECOVERY_PLAN_PATH,
    ):
        assert Path(component_plan).name in ml_section

    substrate_index_route = index.split(
        "**Current substrate status:**",
        1,
    )[1].split("\n\n", 1)[0]
    normalized_substrate_index_route = _normalized_routing_text(
        substrate_index_route
    )
    assert "m0 is historical complete" in normalized_substrate_index_route
    assert "m1 is historical complete" in normalized_substrate_index_route
    assert "phase ml is historical complete" in normalized_substrate_index_route
    assert "is historical complete at commit" in (
        normalized_substrate_index_route
    )
    assert "9c14dae37310755bd9cbd3de03b9256433acd9fe" in (
        substrate_index_route
    )
    assert "0b149f96ace8873b0381a4cd530468b1d24a083f" in (
        substrate_index_route
    )
    assert "postcommit control passed 72 tests" in (
        normalized_substrate_index_route
    )
    assert "ml 2 allocator simplification" in normalized_substrate_index_route
    assert "phase ml is historical complete" in normalized_substrate_index_route
    assert "m2 component (a) is historical complete" in normalized_substrate_index_route
    assert "m3a tasks 1 3 landed" in normalized_substrate_index_route
    assert "first final quality and restarted final specification reviews then rejected cache hit witness/cursor bypasses" in (
        normalized_substrate_index_route
    )
    assert (
        "passes 122 owner tests, 259 production shape tests, 569 test collection, "
        "968 focused tests, and 9,896 broad non security tests"
    ) in normalized_substrate_index_route
    assert "m3a is historical complete" in normalized_substrate_index_route
    assert "76427bdedbbac300bbd82d45db7fa6e24a770f84" in (
        substrate_index_route
    )
    assert "c5d8247ab6d47b209d14ee203513a0eda876acb1" in (
        substrate_index_route
    )
    assert "189 pass postcommit control" in normalized_substrate_index_route
    assert (
        "fa8530a87a61f484e19ed1b3d5716f6e30b2061efb4ff12769bfc0b6051cf42b"
        in substrate_index_route
    )
    assert "accepted m2 component (a) design" in _normalized_routing_text(index)
    assert "evidence gated and unselected" in normalized_substrate_index_route
    assert "mc implementation is complete through task 5" in (
        normalized_substrate_index_route
    )
    assert "task 6 terminal status is resolved only by the deterministic external record" in (
        normalized_substrate_index_route
    )
    assert "no successor substrate tranche is selected" in (
        normalized_substrate_index_route
    )
    assert "mr 4 is historical complete at 836721ce" in (
        normalized_substrate_index_route
    )
    for unselected_phase in ("remaining mr", "m3b", "m3c", "m4"):
        assert unselected_phase in normalized_substrate_index_route

    m2_section = track.split(
        "## Phase M2: Persistence-Parsimony Design",
        1,
    )[1].split("## Phase M3:", 1)[0]
    normalized_m2 = _normalized_routing_text(m2_section)
    assert "status: historical complete" in normalized_m2
    assert "component" in normalized_m2
    assert "only depth" in normalized_m2
    assert "159a8f5e" in m2_section
    assert "5644bd73" in m2_section
    assert "cf0490d1" in m2_section
    assert "ce02cd17" in m2_section
    assert "m3a tasks 1 3 landed" in normalized_m2
    assert "3442aef2" in m2_section
    assert "b931b7b8" in m2_section
    assert "8a01bc2b" in m2_section
    assert "separately reviewed activation plan" in normalized_m2
    assert Path(PURE_RESULT_REPLAY_DESIGN_PATH).name in m2_section
    assert Path(PURE_RESULT_REPLAY_PLAN_PATH).name in m2_section
    assert "effect identity memo keys" in normalized_m2
    assert "not selected" in normalized_m2
    assert "three distinct post ml runs" in normalized_m2
    assert "one full workflow re execution" in normalized_m2

    normalized_pure_replay = _normalized_routing_text(pure_replay_design)
    assert "status: accepted" in normalized_pure_replay
    assert "m2 feasibility complete" in normalized_pure_replay
    assert "result_persistence_profile" in pure_replay_design
    assert "derived_pure_replay.v1" in pure_replay_design
    assert "value free completion shells" in normalized_pure_replay
    assert "result_storage" in pure_replay_design
    assert "atomic state transaction" in normalized_pure_replay
    assert "noderesultaddress" in normalized_pure_replay
    assert "there is no existing typed replay dependency graph" in (
        normalized_pure_replay
    )
    assert "identity neutral typed dependency index" in normalized_pure_replay
    assert "default resume checkpoint candidate set" in normalized_pure_replay
    assert "validated_frame_entry_replay" in normalized_pure_replay
    assert "reuse its existing cursor and visit count without another increment" in (
        normalized_pure_replay
    )
    assert "profile_conflict" in pure_replay_design
    assert "progress_witness_invalid" in pure_replay_design
    assert "effect identity memo keys" in normalized_pure_replay
    assert "do not enter" in normalized_pure_replay
    assert "pure_result_replay_unavailable" in pure_replay_design
    assert "deterministic counted effect e1" in normalized_pure_replay
    assert "interrupted effect e2" in normalized_pure_replay
    assert "loop/recur" in normalized_pure_replay
    assert "not selected" in normalized_pure_replay
    assert "m2 component (a) is historical complete" in normalized_pure_replay
    assert "m3a supported activation is implemented" in normalized_pure_replay
    assert "successfully compiled typed public .orc run" in normalized_pure_replay
    assert "new .orc root created by orchestrate resume force restart" in (
        normalized_pure_replay
    )
    assert "fresh non iterative child" in normalized_pure_replay
    assert 'frontend_kind == "workflow_lisp"' in pure_replay_design
    assert "generic initialization remains explicit opt in" in (
        normalized_pure_replay
    )
    assert "122 owner tests" in normalized_pure_replay
    assert "569 test collection" in normalized_pure_replay
    assert "968 focused tests" in normalized_pure_replay
    assert "9,896 broad non security tests" in normalized_pure_replay
    assert "cursor targeting the same presentation name or step identity conflicts" in (
        normalized_pure_replay
    )
    assert "closure candidate passes its focused routing and broad gates" not in (
        normalized_pure_replay
    )
    assert "component (b)" in normalized_pure_replay
    assert "m3b" in normalized_pure_replay
    assert "m3c" in normalized_pure_replay
    assert Path(PURE_RESULT_REPLAY_DESIGN_PATH).name in index

    normalized_pure_replay_plan = _normalized_routing_text(pure_replay_plan)
    assert "status: historical complete" in (
        normalized_pure_replay_plan
    )
    assert "19a98c8b" in pure_replay_plan
    for task_commit in (
        "09c286dc",
        "159a8f5e",
        "5644bd73",
        "cf0490d1",
        "ce02cd17",
    ):
        assert task_commit in pure_replay_plan
    assert "m2 component (a) is historical complete" in normalized_pure_replay_plan
    assert "m3a is eligible but unselected" in normalized_pure_replay_plan
    assert "normal orchestrate run and orchestrate resume creation stays on the historical profile" in (
        normalized_pure_replay_plan
    )
    assert "m2_feasibility_plan_spec_approved" in normalized_pure_replay_plan
    assert "m2_feasibility_plan_quality_approved" in normalized_pure_replay_plan
    assert "m2_feasibility_final_spec_approved" in normalized_pure_replay_plan
    assert "m2_feasibility_final_quality_approved" in normalized_pure_replay_plan
    assert "9,868 passed, 19 skipped, 5 warnings" in pure_replay_plan
    assert "make only m3a eligible while leaving it unselected" in (
        normalized_pure_replay_plan
    )
    for required_closure_doc in (
        "specs/state.md",
        "workflow_lisp_lexical_execution_checkpoints.md",
        "workflow_lisp_state_layout.md",
        "docs/capability_status_matrix.md",
    ):
        assert required_closure_doc in pure_replay_plan
    assert "exact result address" in normalized_pure_replay_plan
    assert "interrupted current spines for both a and b" in (
        normalized_pure_replay_plan
    )
    assert "inactive branch" in normalized_pure_replay_plan
    assert "settlement/finalization next cases" in normalized_pure_replay_plan
    assert "prepare the complete closure candidate before review" in (
        normalized_pure_replay_plan
    )
    assert "commit the exact reviewed closure bytes unchanged" in (
        normalized_pure_replay_plan
    )
    assert "in tmux, run the full m2 feasibility matrix" in (
        normalized_pure_replay_plan
    )
    assert "pytest q n 16 dist=worksteal" in normalized_pure_replay_plan
    assert pure_replay_plan.index(
        "prepare the complete closure\n  candidate before review"
    ) < pure_replay_plan.index(
        "repository-standard broad non-security suite against\n  the complete closure candidate"
    )

    normalized_state_spec = _normalized_routing_text(state_spec)
    assert "result_persistence_profile" in state_spec
    assert "derived_pure_replay.v1" in state_spec
    assert "exact value free completion shell" in normalized_state_spec
    assert "validated_frame_entry_replay" in normalized_state_spec
    assert "unknown profile fails closed" in normalized_state_spec
    assert "typed public .orc run" in normalized_state_spec
    assert ".orc force restart" in normalized_state_spec
    assert "fresh non iterative typed workflow lisp child" in normalized_state_spec
    assert "generic initialization remains explicit opt in" in normalized_state_spec
    assert "fresh retry" in normalized_state_spec
    assert "failed predecessor" in normalized_state_spec
    assert "recurrent" in normalized_state_spec

    normalized_checkpoint_design = _normalized_routing_text(checkpoint_design)
    assert "derived_pure_replay.v1 eligible pure projection" in (
        normalized_checkpoint_design
    )
    assert "replay only" in normalized_checkpoint_design
    assert "historical and noneligible pure projections retain replay_or_reuse" in (
        normalized_checkpoint_design
    )

    normalized_state_layout = _normalized_routing_text(state_layout_design)
    assert "compiled path carriage" in normalized_state_layout
    assert "does not authorize a runtime bundle read, reuse, or write" in (
        normalized_state_layout
    )
    assert "supported automatic creation policy" in normalized_state_layout
    assert "iteration owned" in normalized_state_layout

    normalized_design_index = _normalized_routing_text(design_index)
    assert "accepted; m2 feasibility complete; m3a activation historical complete" in (
        normalized_design_index
    )
    assert "typed public" in normalized_design_index
    assert "fresh non iterative" in normalized_design_index

    normalized_capability_matrix = _normalized_routing_text(capability_matrix)
    assert "workflow lisp derived pure result replay profile" in (
        normalized_capability_matrix
    )
    assert "| Workflow Lisp derived pure-result replay profile | Implemented |" in (
        capability_matrix
    )
    assert "typed public new root" in (
        normalized_capability_matrix
    )
    assert "fresh non iterative typed workflow lisp child" in (
        normalized_capability_matrix
    )
    assert "106→98" in capability_matrix
    assert "6,539→6,199" in capability_matrix
    assert "622,815→611,912" in capability_matrix
    assert "569 test collection" in normalized_capability_matrix
    assert "968 focused tests" in normalized_capability_matrix
    assert "cache witness/cursor fix" in normalized_capability_matrix
    assert "9,896 broad non security tests with 19 skipped and 5 warnings" in (
        normalized_capability_matrix
    )
    assert "exact closure 76427bde, tree c5d8247a" in normalized_capability_matrix
    assert "passed ordered final review and a 189 pass postcommit control" in (
        normalized_capability_matrix
    )
    assert (
        "fa8530a87a61f484e19ed1b3d5716f6e30b2061efb4ff12769bfc0b6051cf42b"
        in capability_matrix
    )
    assert "component (b)" in normalized_capability_matrix
    assert "m3b" in normalized_capability_matrix
    assert "m3c" in normalized_capability_matrix

    normalized_activation_plan = _normalized_routing_text(
        pure_replay_activation_plan
    )
    assert "status: historical complete" in normalized_activation_plan
    assert "record the restarted final specification disposition" in (
        normalized_activation_plan
    )
    assert "running cursor targeted the same presentation name/step identity" in (
        normalized_activation_plan
    )
    assert "tasks 1 3 landed" in normalized_activation_plan
    assert "10 failures, 9,865 passes, 19 skips, and 5 warnings" in (
        pure_replay_activation_plan
    )
    assert (
        "6fdffec5e5c8a177372efff2a81d760fd62f1776c7932a2837a49d50ba4e4482"
        in pure_replay_activation_plan
    )
    assert "typed literal binding leaves" in normalized_activation_plan
    assert "metadata bearing consumer value documents" in (
        normalized_activation_plan
    )
    assert "sparse union results" in normalized_activation_plan
    assert "m3a_integration_fix_spec_approved" in normalized_activation_plan
    assert "m3a_integration_fix_quality_approved" in normalized_activation_plan
    assert "the corrected candidate reran these gates" in (
        normalized_activation_plan
    )
    assert (
        "- [x] In tmux, run the repository-standard broad non-security suite:"
        in pure_replay_activation_plan
    )
    assert "568 tests in 2.15 seconds" in pure_replay_activation_plan
    assert "967 tests in 8.52 seconds" in pure_replay_activation_plan
    assert "569 tests in 2.03 seconds" in pure_replay_activation_plan
    assert "968 tests in 9.72 seconds" in pure_replay_activation_plan
    assert "9,890 tests, 19 skipped, and 5 warnings" in (
        pure_replay_activation_plan
    )
    assert (
        "8787a8eb3411c707cd636287b56b68945d80ba63e83ecb82fa5648aff7d356d7"
        in pure_replay_activation_plan
    )
    assert "pre cache witness historical evidence" in normalized_activation_plan
    assert "9,890 pass result does not satisfy the refreshed closure gate" in (
        normalized_activation_plan
    )
    assert "green 9,890 pass broad gate remains the acceptance result" not in (
        normalized_activation_plan
    )
    assert "pre cursor correction broad gate passed 9,895 tests with 19 skipped and 5 warnings" in (
        normalized_activation_plan
    )
    assert (
        "07615bb605d401a068a93aeed2476544104d0721fca4d45d80785ac57eafbab3"
        in pure_replay_activation_plan
    )
    assert (
        "c36a5895c55da9cc887be5deb47095f1bf95d268cdb4c55c50452a2f4ce8f918"
        in pure_replay_activation_plan
    )
    assert (
        "3236b6844ed3ce63239f85a911b190c7d8bdbe8457fa0046e07ed891ce0c474f"
        in pure_replay_activation_plan
    )
    assert "post cursor correction broad gate passed 9,896 tests with 19 skipped and 5 warnings" in (
        normalized_activation_plan
    )
    assert (
        "d4324439f68b6881f353d5e3f436cc4d460f4728b0359d3b8297a795284efb6d"
        in pure_replay_activation_plan
    )
    assert "m3a_final_spec_approved" in normalized_activation_plan
    assert "m3a_final_quality_approved" in normalized_activation_plan
    assert normalized_activation_plan.index(
        "m3a_final_spec_approved"
    ) < normalized_activation_plan.index(
        "m3a_final_quality_approved"
    )
    assert (
        "- [x] Request `M3A_FINAL_SPEC_APPROVED`, then"
        in pure_replay_activation_plan
    )
    assert (
        "76427bdedbbac300bbd82d45db7fa6e24a770f84"
        in pure_replay_activation_plan
    )
    assert (
        "c5d8247ab6d47b209d14ee203513a0eda876acb1"
        in pure_replay_activation_plan
    )
    assert (
        "13d01cd3a37549ae937bb35f7e252ab3ae645b54bf681a2fdfeb22909c3afe9e"
        in pure_replay_activation_plan
    )
    assert (
        "fa8530a87a61f484e19ed1b3d5716f6e30b2061efb4ff12769bfc0b6051cf42b"
        in pure_replay_activation_plan
    )
    for task_commit in ("3442aef2", "b931b7b8", "8a01bc2b"):
        assert task_commit in pure_replay_activation_plan
    assert "6e06b4c0" in pure_replay_activation_plan
    assert "m3a_activation_plan_spec_approved" in normalized_activation_plan
    assert "m3a_activation_plan_quality_approved" in normalized_activation_plan
    assert "480e7e2f" in pure_replay_activation_plan
    assert "1886104a" in pure_replay_activation_plan
    assert "typed creation point selection" in normalized_activation_plan
    assert "generic initializer inference" in normalized_activation_plan
    assert "parent profile inheritance" in normalized_activation_plan
    for activation_owner in (
        "orchestrator/cli/commands/run.py",
        "orchestrator/cli/commands/resume.py",
        "orchestrator/workflow/calls.py",
    ):
        assert activation_owner in pure_replay_activation_plan
    for preserved_boundary in (
        "generic state initialization remains opt in",
        "ordinary resume never chooses or backfills a profile",
        "child_existing_frame is not none",
        "boundary.iteration_owner_node_id is not none",
        "component (b) memo keys",
        "do not modify e/p routing",
    ):
        assert preserved_boundary in normalized_activation_plan
    assert pure_replay_activation_plan.index(
        "M3A_ACTIVATION_PLAN_SPEC_APPROVED"
    ) < pure_replay_activation_plan.index(
        "M3A_ACTIVATION_PLAN_QUALITY_APPROVED"
    )
    for task_number in range(5):
        assert f"## Task {task_number}:" in pure_replay_activation_plan
    assert "m3a tasks 1 3 landed" in normalized_track
    assert "m3a is historical complete" in normalized_track
    assert "569 test collection, 968 focused tests" in normalized_track
    assert "refreshed 9,896 test broad non security gate" in normalized_track
    assert "restarted ordered final review approved exact complete diff" in (
        normalized_track
    )
    assert "189 tests" in normalized_track
    assert "m3a_activation_plan_spec_approved" in normalized_track
    assert "m3a_activation_plan_quality_approved" in normalized_track

    normalized_plan = _normalized_routing_text(m1_plan)
    normalized_plan_header = _normalized_routing_text(
        "\n".join(m1_plan.splitlines()[:35])
    )
    assert "status: historical complete" in normalized_plan_header
    assert "historical selection act" in normalized_plan_header
    assert "tasks 0 9" in normalized_plan_header
    assert "57c2604e595d22dc9d9d656409607f81b332b5f8" in m1_plan
    assert "fc0fdbefe2cdd99cf0f9de604aa63582f79425ea" in m1_plan
    assert m1_plan.index("M1_PLAN_SPEC_APPROVED") < m1_plan.index(
        "M1_PLAN_QUALITY_APPROVED"
    )
    for task_number in range(10):
        assert f"### Task {task_number}:" in m1_plan
    for preserved_boundary in (
        "docs/plans/evidence/yaml retirement/",
        "route readiness",
        "frontend_kind",
        "six current format nonterminal runs",
        "dashboard",
        "security",
    ):
        assert preserved_boundary in normalized_plan
    for archive_contract in (
        "same filesystem rename",
        "two identical censuses",
        "60 seconds",
        "restore",
        "state less orphan",
    ):
        assert archive_contract in normalized_plan
    assert "no q5 or l series gate" in normalized_plan
    assert "no new evidence schema" in normalized_plan
    assert "supersedes the amendment's 2026 07 26 blanket inclusion" in (
        normalized_plan
    )
    assert "--deselect" not in m1_plan
    for exact_path in (
        "orchestrator/cli/commands/migration_parity.py",
        "orchestrator/cli/commands/post_wcc_inventory.py",
        "orchestrator/cli/commands/route_readiness.py",
        "workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json",
        "specs/acceptance/index.md",
        "specs/dsl.md",
    ):
        assert exact_path in m1_plan
    assert "m1_final_spec_approved" in normalized_plan
    assert "m1_final_quality_approved" in normalized_plan

    # M1 closure must not rewrite or reopen the already-closed parallel Q/L
    # surfaces.
    assert (
        "l4 is complete at commit "
        "251d9d53674e863fddae4535ea4f7022914287cd"
    ) in normalized_track_header
    assert (
        "q4 is complete at commit "
        "f3335637b90feb0a87ac4c538bafac7704ac0d87"
    ) in normalized_track_header
    assert "does not reopen either gate" in normalized_track_header

    assert m0_plan.index("M0_PLAN_SPEC_APPROVED") < m0_plan.index(
        "M0_PLAN_QUALITY_APPROVED"
    )
    normalized_m0_plan = _normalized_routing_text(m0_plan)
    assert "status: implemented closure candidate" in normalized_m0_plan
    assert "12,227 passed, 28 skipped in 1229.78s" in m0_plan
    assert "5b63aca18c2c013395aecede0210e4b522f7c846549ed23d879505635f226810" in (
        m0_plan
    )


def test_mc_routes_external_resolution_and_nonsecurity_evidence() -> None:
    track = (REPO_ROOT / SUBSTRATE_MAINTENANCE_TRACK_PATH).read_text(
        encoding="utf-8"
    )
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")
    plan = (REPO_ROOT / MC_COMMON_HELPER_PLAN_PATH).read_text(encoding="utf-8")
    normalized_track = _normalized_routing_text(track)
    normalized_index = _normalized_routing_text(index)
    normalized_plan = _normalized_routing_text(plan)

    assert Path(MC_COMMON_HELPER_PLAN_PATH).name in track
    assert Path(MC_COMMON_HELPER_PLAN_PATH).name in index
    assert "terminal status: resolved only by the deterministic external record" in (
        normalized_track
    )
    assert "auditing completed mc implementation" in normalized_index
    assert "task 6's external resolution contract" in normalized_index
    assert "db01eb6a14e1c9c959b4359630667c62aeb4b507" in plan
    assert "fd6f54416f4f39090c679bb81d768b1fa7c7cff5" in plan
    for task_commit in (
        "786c1fe4",
        "2e6e58f9",
        "ff9351bb",
        "390f24d0",
        "f2453d06",
        "71f61b26",
    ):
        assert task_commit in plan
    assert "a15c38623afe3da7b29a016aa44a66b726842a1c" in plan
    assert "ac7a7bf5272928ba985ffe57bce634b08492e9e8" in plan
    assert "Preserve atomic replacement path compatibility" in plan
    assert plan.index("MC_CORRECTION_SPEC_APPROVED") < plan.index(
        "MC_CORRECTION_QUALITY_APPROVED"
    )
    assert "focused selector passed 29 tests" in normalized_plan
    assert "selector passed 671 tests" in normalized_plan
    assert "523 additions, 524 deletions, net -1" in plan
    assert "4,227 additions and 32 deletions" in plan
    assert "documentation: 830 additions and 41 deletions" in normalized_plan
    assert "2,673 passed in 63.51 seconds (64.38 seconds elapsed)" in (
        normalized_plan
    )
    assert (
        "2eebeffa1cf28ec9abac7733e9a562d0183dd590ff84dd62f0ab03dcd11bb6d6"
        in plan
    )
    assert "corrected broad rerun exited 0" in normalized_plan
    assert "7 tests in 2.63 seconds (3.04 seconds elapsed)" in normalized_plan
    assert (
        "323667f5885c57f9ba4fee3295aad2081889bfc8c979d74f87f7ec1307e6df6a"
        in plan
    )
    assert (
        "124fa184d3296e4e57402ec40adbb0d7a4d992836617af02540bedc627411789"
        in plan
    )
    assert "outside manifest proof found 0 excluded path matches" in normalized_plan
    assert (
        "09a65712abec1aba4a055a0c085b96e6aea0b5b3d319c56b665ca8f6809c7576"
        in plan
    )
    assert "115 tests in 2.16 seconds (2.53 seconds elapsed)" in normalized_plan
    assert (
        "b6c66fce37a6453ebc885b76de1a86eb16efdcf8427a1565999afee637507e01"
        in plan
    )
    assert "2 failed, 10,107 passed, 19 skipped, and 5 warnings" in normalized_plan
    assert "113.80 seconds (114.33 seconds elapsed)" in normalized_plan
    assert (
        "7b19842fef3e04366acc7ef48cedc918647e6c51bda9738c536f9e54dffabbbb"
        in plan
    )
    assert "name_max temporary basename" in normalized_plan
    assert "direct script relative import failure" in normalized_plan
    assert "10,111 passed, 19 skipped, and 5 warnings" in normalized_plan
    assert "114.71 seconds (115.40 seconds elapsed)" in normalized_plan
    assert (
        "aefafa7d3547a4f9bedcde7e4f965d4f67496b98b84c6cbec1c993329fd8afc7"
        in plan
    )
    assert plan.count("--ignore=tests/") == 21
    assert "-k 'not security and not secret and not isolation and not safety'" in plan
    assert "checked in bytes do not encode a live pending/completed flag" in (
        normalized_plan
    )
    assert "is the sole terminal status resolver" in normalized_plan
    assert "an absent, unreadable, or mismatching record means mc is not complete" in (
        normalized_plan
    )
    assert (
        "/home/ollie/.tmp/mc-common-helper-20260730/closure-verdicts.md"
        in plan
    )
    assert "- [x] Run the union of all Task 1–5 owner modules" in plan
    assert "### Externally resolved terminal operations" in plan
    assert "deliberately not live checked in checkboxes" in normalized_plan
    assert "obtain `MC_FINAL_SPEC_APPROVED` followed by" in plan
    assert "commit the reviewed bytes unchanged" in normalized_plan
    assert "run a non mutating postcommit owner plus routing selector" in (
        normalized_plan
    )
    assert "- [x] Run the architecture census" in plan
    assert "- [x] Prove the phase diff" in plan
    assert "- [x] Record `git diff --numstat`" in plan
    assert "- [x] Run `pytest --collect-only`" in plan
    assert "- [x] In tmux, run the repository-standard broad suite" in plan
    assert "- [x] Update status/routing facts" in plan
    assert "no successor roadmap tranche is selected or dispositioned" in (
        normalized_plan
    )

    assert plan.index("MC_PLAN_SPEC_APPROVED") < plan.index(
        "MC_PLAN_QUALITY_APPROVED"
    )
    assert plan.index("MC_FINAL_SPEC_APPROVED") < plan.index(
        "MC_FINAL_QUALITY_APPROVED"
    )
    for task_number in range(7):
        assert f"## Task {task_number}:" in plan
    for shared_module in (
        "orchestrator/_common/canonical.py",
        "orchestrator/_common/validation.py",
        "orchestrator/_common/status.py",
        "orchestrator/_common/io_atomic.py",
    ):
        assert shared_module in plan

    assert "admitted production loc is net negative" in normalized_plan
    assert "test and documentation totals separately" in normalized_plan
    assert "no digest migration" in normalized_plan
    assert "non finite provider timeouts fail before side effects" in (
        normalized_plan
    )
    assert "failed non durable atomic writes leave the destination unchanged" in (
        normalized_plan
    )
    for excluded_surface in (
        "report/monitor symlink policy",
        "provider isolation",
        "dashboard",
        "experiment/e series",
        "wcc middle end",
        "security surface",
    ):
        assert excluded_surface in normalized_plan

    assert "mr 4 is historical complete at 836721ce" in normalized_track
    assert "literal pre m3 windows" in normalized_track
    assert "require an explicit supersession/no go or reviewed post m3 re sequencing" in (
        normalized_track
    )
    assert "no remaining tranche is selected by this row" in normalized_track


def test_ml0_selects_at_least_once_recovery_with_reviewable_component_bounds() -> None:
    track = (REPO_ROOT / SUBSTRATE_MAINTENANCE_TRACK_PATH).read_text(
        encoding="utf-8"
    )
    index = (REPO_ROOT / "docs/index.md").read_text(encoding="utf-8")
    state_spec = (REPO_ROOT / "specs/state.md").read_text(encoding="utf-8")
    providers_spec = (REPO_ROOT / "specs/providers.md").read_text(
        encoding="utf-8"
    )
    cli_spec = (REPO_ROOT / "specs/cli.md").read_text(encoding="utf-8")
    observability_spec = (REPO_ROOT / "specs/observability.md").read_text(
        encoding="utf-8"
    )
    acceptance = (REPO_ROOT / "specs/acceptance/index.md").read_text(
        encoding="utf-8"
    )
    versioning = (REPO_ROOT / "specs/versioning.md").read_text(
        encoding="utf-8"
    )

    plans = {
        path: (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in (
            ML1_PROVIDER_RECOVERY_PLAN_PATH,
            ML2_PROVIDER_ALLOCATOR_PLAN_PATH,
            ML4_ADJUDICATION_RECOVERY_PLAN_PATH,
        )
    }
    for path, plan in plans.items():
        assert Path(path).name in track
        assert Path(path).name in index
        assert "superpowers:subagent-driven-development" in plan
        assert "RED" in plan
        assert "specification review" in plan
        assert "quality review" in plan
        assert "security" in _normalized_routing_text(plan)

    normalized_state = _normalized_routing_text(state_spec)
    assert "provider attempts are at least once" in normalized_state
    assert "provider_attempt_interrupted_rerun" in state_spec
    attempt_contract = state_spec.split(
        "Provider attempts are at-least-once across",
        1,
    )[1].split("provider execution", 1)[0]
    for family in ("ordinary", "session", "supervision", "peer-group", "phased"):
        assert family in attempt_contract
    assert "completed result reuse" in normalized_state
    integrity_contract = normalized_state.split(
        "provider attempts are at least once",
        1,
    )[1].split("state backups and cleanup", 1)[0]
    for guard in ("malformed", "ambiguous", "checksum incompatible", "fails closed"):
        assert guard in integrity_contract
    assert "provider isolation bundle transfer journal" in normalized_state
    assert "not amended" in normalized_state
    assert "plain monotonic counter" in normalized_state
    assert "run lifetime lock" in normalized_state
    assert "best effort audit evidence" in normalized_state
    assert "adjudication_resume_mismatch" not in state_spec

    normalized_providers = _normalized_routing_text(providers_spec)
    assert "at least once recovery" in normalized_providers
    assert "next unused attempt ordinal" in normalized_providers

    normalized_cli = _normalized_routing_text(cli_spec)
    assert "provider_attempt_interrupted_rerun" in cli_spec
    assert "force restart is not required" in normalized_cli

    normalized_observability = _normalized_routing_text(observability_spec)
    assert "provider_attempt_interrupted_rerun" in observability_spec
    assert "recovery diagnostic, not a run level failure" in (
        normalized_observability
    )
    assert "provider_peer_group_interrupted_visit_quarantined" not in (
        observability_spec
    )

    normalized_acceptance = _normalized_routing_text(acceptance)
    assert "at least once interrupted visit recovery" in normalized_acceptance
    assert "phased" in normalized_acceptance
    assert "adjudication mismatch" in normalized_acceptance

    normalized_versioning = _normalized_routing_text(versioning)
    assert "ml 0 contract pivot" in normalized_versioning
    assert "at least once runtime contract is implemented" in (
        normalized_versioning
    )
    assert "this closure does not select a successor phase" in (
        normalized_versioning
    )
    assert "provider isolation transfer journal remains unchanged" in (
        normalized_versioning
    )

    normalized_index = _normalized_routing_text(index)
    assert "provider at least once recovery component plan" in normalized_index
    assert "provider attempt allocator simplification component plan" in (
        normalized_index
    )
    assert "adjudication rerun recovery component plan" in normalized_index

    normalized_track = _normalized_routing_text(track)
    assert "phase ml is historical complete" in normalized_track
    assert "ml 2 closed at commit" in normalized_track
    assert "ml 4 tasks 1 4 landed" in normalized_track
    assert "phase ml is historical complete" in normalized_index
    assert "m2 component" in normalized_index
    assert "is selected" in normalized_index
    assert "evidence gated and unselected" in normalized_index

    normalized_ml2_plan = _normalized_routing_text(
        plans[ML2_PROVIDER_ALLOCATOR_PLAN_PATH]
    )
    normalized_ml4_plan = _normalized_routing_text(
        plans[ML4_ADJUDICATION_RECOVERY_PLAN_PATH]
    )
    assert "status: historical complete ml 2" in normalized_ml2_plan
    assert "ml2_task6_spec_approved" in normalized_ml2_plan
    assert "ml2_task6_quality_approved" in normalized_ml2_plan
    assert plans[ML2_PROVIDER_ALLOCATOR_PLAN_PATH].index(
        "ML2_TASK6_SPEC_APPROVED"
    ) < plans[ML2_PROVIDER_ALLOCATOR_PLAN_PATH].index(
        "ML2_TASK6_QUALITY_APPROVED"
    )
    assert "status: historical complete ml 4" in normalized_ml4_plan

    capability_row = _markdown_table_row(
        REPO_ROOT / "docs/capability_status_matrix.md",
        "Provider at-least-once interrupted-visit recovery",
    )
    assert (
        "| Implemented | Automatic runtime behavior; not an authored surface |"
        in capability_row
    )
    normalized_capability_row = _normalized_routing_text(capability_row)
    for closure_fact in (
        "b8783f66",
        "b833b03c",
        "c45928f4",
        "b3370858",
        "ed19624c",
        "758c67e0",
        "9,714 broad non security tests passed",
        "no successor phase is selected",
    ):
        assert closure_fact in normalized_capability_row
