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
    return {
        "roadmap disposition": migration_disposition + "\n" + yaml_disposition,
        "roadmap current routing": _procedure_sequence_current_routing(),
        "roadmap Stage 5 selector": sequence.split(
            "### Stage 5: Implement Procedure-First Reuse In Waves", 1
        )[1].split("### Stage 6: Resume YAML Retirement", 1)[0],
    }


def _assert_migration_wave_complete_and_yaml_task_5_current(
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
        r"\byaml retirement\b.{0,120}\btask 5\b.{0,80}\bcurrent\b"
        r"|\byaml retirement\b.{0,120}\bcurrent\b.{0,80}\btask 5\b"
        r"|\bcurrent\b.{0,100}\byaml retirement\b.{0,100}\btask 5\b",
        normalized,
    ), label
    assert re.search(
        r"\byaml retirement\b.{0,120}\btasks? 1[ -]4\b.{0,80}\bcomplete\w*\b"
        r"|\btasks? 1[ -]4\b.{0,80}\bcomplete\w*\b.{0,120}\byaml retirement\b",
        normalized,
    ), label
    for stale_task in (1, 2, 3, 4, 6, 7):
        assert re.search(
            rf"\byaml retirement\b[^.;]{{0,120}}\btask {stale_task}\b"
            rf"[^.;]{{0,40}}\bcurrent\b"
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


def test_procedure_first_status_surfaces_route_completed_wave_to_yaml_task_5() -> None:
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
        assert "migration wave" in normalized and "complete" in normalized, label
        assert "current selector" in normalized, label
        assert "migration waves remain blocked" not in normalized, label
        assert "runtime hardening remains pending" not in normalized, label


def test_migration_wave_closeout_routes_through_completed_yaml_tasks_1_4_to_task_5() -> None:
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
        _assert_migration_wave_complete_and_yaml_task_5_current(surface, label)

    for label in ("docs index", "roadmap current routing"):
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
    assert "Promotion gates closed" in task_5_rows[0]
    assert (
        "artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final/"
        "verified_iteration_drain.json"
    ) in task_5_rows[0]
    assert "YAML remains present and executable until Task 6" in task_5_rows[0]
    assert "**Pending.**" in task_5_rows[1]
    assert "No watchdog promotion or deletion gate is closed" in task_5_rows[1]
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
    assert "task 4" in _normalized_routing_text(index_routing)
    _assert_migration_wave_complete_and_yaml_task_5_current(
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
        "Stage 6 YAML retirement Task 6 is current.",
        "Stage 6 YAML retirement Task 7 is current.",
        "Task 5 remains open; Task 6 has not started.",
    ),
)
def test_yaml_task_5_current_selector_guard_rejects_stale_or_skipped_routing(
    replacement: str,
) -> None:
    docs_index_routing = (REPO_ROOT / "docs" / "index.md").read_text(
        encoding="utf-8"
    ).split("**Component-plan routing:**", 1)[1].split(
        "**Current procedure-first substrate:**", 1
    )[0]
    mutated = re.sub(
        r"(?:Stage 6 )?YAML retirement[^.]{0,200}Task 5[^.]{0,100}(?:current|selected)[^.]*\.",
        replacement,
        docs_index_routing,
        count=0,
    )
    assert mutated != docs_index_routing

    with pytest.raises(AssertionError):
        _assert_migration_wave_complete_and_yaml_task_5_current(
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
    assert "verified iteration family parity and promotion are closed" in normalized_gap_list
    assert "watchdog family parity and promotion" in normalized_gap_list
    assert "yaml deletion remains pending" in normalized_gap_list


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
    assert "yaml content mode remains legacy" in normalized_row
    assert "verified_iteration_drain" in matrix_row
    assert "closed its family parity and promotion gate" in normalized_row
    assert "generic_run_watchdog" in matrix_row
    assert "parity and promotion" in normalized_row and "pending" in normalized_row
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
