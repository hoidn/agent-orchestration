import json
import shutil
import subprocess
from dataclasses import is_dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.calls import CallExecutor
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_context, workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/lisp_frontend_autonomous_drain"


def _thaw(value):
    if isinstance(value, dict):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): _thaw(item) for key, item in value.items()}
    if is_dataclass(value):
        return {str(key): _thaw(item) for key, item in vars(value).items()}
    return value


def _bundle_context_dict(bundle) -> dict:
    return _thaw(workflow_context(bundle))


def _iter_workflow_steps(steps):
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        yield step
        repeat = step.get("repeat_until")
        if isinstance(repeat, dict):
            yield from _iter_workflow_steps(repeat.get("steps"))
        match = step.get("match")
        if isinstance(match, dict):
            for case in (match.get("cases") or {}).values():
                if isinstance(case, dict):
                    yield from _iter_workflow_steps(case.get("steps"))


def _copy_repo_file_to_workspace(workspace: Path, repo_relpath: str) -> None:
    src = ROOT / repo_relpath
    dest = workspace / repo_relpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _copy_runtime_files(workspace: Path) -> Path:
    shutil.copytree(FIXTURE_ROOT, workspace, dirs_exist_ok=True)
    files = [
        "docs/design/workflow_command_adapter_contract.md",
        "docs/design/workflow_lisp_proc_refs_partial_application.md",
        "docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md",
        "state/LISP-PROC-REFS-PARTIAL-APPLICATION/progress_ledger.json",
        "workflows/examples/lisp_frontend_autonomous_drain.yaml",
        "workflows/examples/lisp_frontend_design_delta_drain.yaml",
        "workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml",
        "workflows/library/lisp_frontend_selector.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_selector.v214.yaml",
        "workflows/library/lisp_frontend_design_gap_architect.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml",
        "workflows/library/lisp_frontend_work_item.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml",
        "workflows/library/lisp_frontend_plan_phase.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml",
        "workflows/library/lisp_frontend_implementation_phase.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml",
        "workflows/library/scripts/build_lisp_frontend_architecture_index.py",
        "workflows/library/scripts/build_lisp_frontend_backlog_manifest.py",
        "workflows/library/scripts/build_neurips_backlog_manifest.py",
        "workflows/library/scripts/prepare_lisp_frontend_iteration_paths.py",
        "workflows/library/scripts/publish_lisp_frontend_selection_bundle.py",
        "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py",
        "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py",
        "workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py",
        "workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py",
        "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py",
        "workflows/library/scripts/update_lisp_frontend_run_state.py",
        "workflows/library/scripts/record_lisp_frontend_design_revision_outcome.py",
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py",
        "workflows/library/scripts/write_lisp_frontend_design_revision_iteration_decision.py",
        "workflows/library/scripts/finalize_lisp_frontend_drain_summary.py",
        "workflows/library/scripts/run_neurips_backlog_checks.py",
    ]
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_selector").rglob("*.md")
    )
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_design_gap_architect").rglob("*.md")
    )
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect").rglob("*.md")
    )
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_plan_phase").rglob("*.md")
    )
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_design_delta_plan_phase").rglob("*.md")
    )
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_implementation_phase").rglob("*.md")
    )
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase").rglob("*.md")
    )
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_design_delta_work_item").rglob("*.md")
    )
    for relpath in sorted(set(files)):
        _copy_repo_file_to_workspace(workspace, relpath)
    return workspace / "workflows/examples/lisp_frontend_autonomous_drain.yaml"


def _workflow_inputs() -> dict:
    return {
        "steering_path": "docs/steering.md",
        "full_design_path": "docs/design/workflow_lisp_frontend_specification.md",
        "mvp_design_path": "docs/design/workflow_lisp_frontend_mvp_specification.md",
        "progress_ledger_path": "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json",
    }


def _design_delta_workflow_inputs() -> dict:
    return {
        "steering_path": "docs/steering.md",
        "target_design_path": "docs/design/workflow_lisp_frontend_specification.md",
        "baseline_design_path": "docs/design/workflow_lisp_frontend_mvp_specification.md",
        "progress_ledger_path": "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json",
    }


def _run_script(workspace: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", *argv],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    )


def _write_runtime_default_module(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord Summary",
                "    (report WorkReport))",
                "  (defworkflow defaults",
                '    ((report_path WorkReport :default "default.md"))',
                "    -> Summary",
                "    (record Summary :report report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_runtime_imported_default_modules(tmp_path: Path) -> Path:
    source_root = tmp_path / "defaults_pkg"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "types.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule defaults_pkg/types)",
                "  (export WorkReport WorkflowOutput)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord WorkflowOutput",
                "    (report WorkReport)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (source_root / "helper.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule defaults_pkg/helper)",
                "  (import defaults_pkg/types :only (WorkReport WorkflowOutput))",
                "  (export helper)",
                "  (defworkflow helper",
                '    ((required_path WorkReport)',
                '     (optional_report WorkReport :default "default.md"))',
                "    -> WorkflowOutput",
                "    (record WorkflowOutput :report optional_report)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    entry_path = source_root / "entry.orc"
    entry_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule defaults_pkg/entry)",
                "  (import defaults_pkg/types :only (WorkReport WorkflowOutput))",
                "  (import defaults_pkg/helper :as helper :only (helper))",
                "  (export entry)",
                "  (defworkflow entry",
                "    ((required_path WorkReport))",
                "    -> WorkflowOutput",
                "    (call helper.helper",
                "      :required_path required_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return entry_path


def test_materializer_normalizes_backlog_selection(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    manifest_path = workspace / "state/manifest.json"
    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/build_neurips_backlog_manifest.py"),
        "--backlog-root",
        "docs/backlog/active",
        "--output",
        manifest_path.relative_to(workspace).as_posix(),
    )
    selection_path = workspace / "state/selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_status": "SELECT_BACKLOG_ITEM",
                "selected_item_id": "2026-05-18-existing-parser-item",
                "selected_item_path": "docs/backlog/active/2026-05-18-existing-parser-item.md",
                "selection_rationale": "Existing item covers parser MVP.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = workspace / "state/work-item/inputs.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py"),
        "--selection-path",
        selection_path.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest_path.relative_to(workspace).as_posix(),
        "--state-root",
        "state/work-item",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["work_item_source"] == "BACKLOG_ITEM"
    assert payload["work_item_id"] == "2026-05-18-existing-parser-item"
    assert payload["plan_target_path"].endswith("2026-05-18-existing-parser-item/execution_plan.md")
    assert (workspace / payload["work_item_context_path"]).is_file()
    assert json.loads((workspace / payload["check_commands_path"]).read_text(encoding="utf-8")) == [
        "python -c \"print('lisp-parser-check')\""
    ]


def test_materialize_lisp_work_item_inputs_accepts_custom_artifact_roots_for_backlog(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    manifest_path = workspace / "state/manifest.json"
    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/build_neurips_backlog_manifest.py"),
        "--backlog-root",
        "docs/backlog/active",
        "--output",
        manifest_path.relative_to(workspace).as_posix(),
    )
    selection_path = workspace / "state/selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_status": "SELECT_BACKLOG_ITEM",
                "selected_item_id": "2026-05-18-existing-parser-item",
                "selected_item_path": "docs/backlog/active/2026-05-18-existing-parser-item.md",
                "selection_rationale": "Existing item covers parser MVP.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = workspace / "state/work-item/inputs.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py"),
        "--selection-path",
        selection_path.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest_path.relative_to(workspace).as_posix(),
        "--state-root",
        "state/work-item",
        "--artifact-work-root",
        "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION",
        "--artifact-checks-root",
        "artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION",
        "--artifact-review-root",
        "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["execution_report_target_path"].startswith(
        "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    assert payload["progress_report_target_path"].startswith(
        "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    assert payload["checks_report_target_path"].startswith(
        "artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    assert payload["implementation_review_report_target_path"].startswith(
        "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    assert payload["plan_review_report_target_path"].startswith(
        "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    artifact_targets = [
        payload["execution_report_target_path"],
        payload["progress_report_target_path"],
        payload["checks_report_target_path"],
        payload["implementation_review_report_target_path"],
        payload["plan_review_report_target_path"],
        payload["item_summary_target_path"],
    ]
    assert all("LISP-FRONTEND-AUTONOMOUS-DRAIN" not in target for target in artifact_targets)


def test_materialize_lisp_work_item_inputs_accepts_custom_artifact_roots_for_design_gap(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    selection_path = workspace / "state/selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "procref-static-surface-and-resolution",
                "selection_rationale": "ProcRef surface is missing.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    architecture_path = workspace / "docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref/implementation_architecture.md"
    context_path = workspace / "state/gap/work_item_context.md"
    checks_path = workspace / "state/gap/check_commands.json"
    plan_target_path = workspace / "docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref/execution_plan.md"
    architecture_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    architecture_path.write_text("# ProcRef Architecture\n", encoding="utf-8")
    context_path.write_text("# ProcRef Work Item\n", encoding="utf-8")
    checks_path.write_text(json.dumps(["python -c \"print('procref-check')\""]) + "\n", encoding="utf-8")
    bundle_path = workspace / "state/gap/architecture-validation.json"
    bundle_path.write_text(
        json.dumps(
            {
                "architecture_validation_status": "VALID",
                "work_item_source": "DESIGN_GAP",
                "work_item_id": "procref-static-surface-and-resolution",
                "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                "work_item_context_path": context_path.relative_to(workspace).as_posix(),
                "check_commands_path": checks_path.relative_to(workspace).as_posix(),
                "plan_target_path": plan_target_path.relative_to(workspace).as_posix(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = workspace / "state/manifest.json"
    manifest_path.write_text(json.dumps({"items": []}) + "\n", encoding="utf-8")
    output_path = workspace / "state/work-item/inputs.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py"),
        "--selection-path",
        selection_path.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest_path.relative_to(workspace).as_posix(),
        "--state-root",
        "state/work-item",
        "--architecture-bundle-path",
        bundle_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION",
        "--artifact-checks-root",
        "artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION",
        "--artifact-review-root",
        "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload)
    assert payload["execution_report_target_path"].startswith(
        "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/"
    )
    assert payload["checks_report_target_path"].startswith(
        "artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/"
    )
    assert payload["implementation_review_report_target_path"].startswith(
        "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/"
    )
    assert payload["item_summary_target_path"].startswith(
        "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/"
    )
    assert "LISP-FRONTEND-AUTONOMOUS-DRAIN" not in serialized


def test_architecture_validator_accepts_valid_design_gap(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    context_path = workspace / "state/gap/work_item_context.md"
    checks_path = workspace / "state/gap/check_commands.json"
    plan_target_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    architecture_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    architecture_path.write_text("# Parser Syntax Architecture\n", encoding="utf-8")
    context_path.write_text("# Parser Syntax Work Item\n", encoding="utf-8")
    checks_path.write_text(json.dumps(["python -c \"print('gap-check')\""]) + "\n", encoding="utf-8")
    draft_path = workspace / "state/gap/draft-bundle.json"
    draft_path.write_text(
        json.dumps(
            {
                "draft_status": "DRAFTED",
                "design_gap_id": "parser-syntax",
                "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                "work_item_context_path": context_path.relative_to(workspace).as_posix(),
                "check_commands_path": checks_path.relative_to(workspace).as_posix(),
                "plan_target_path": plan_target_path.relative_to(workspace).as_posix(),
                "summary": "Parser syntax gap.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = workspace / "state/gap/validation.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py"),
        "--draft-bundle-path",
        draft_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["architecture_validation_status"] == "VALID"
    assert payload["work_item_source"] == "DESIGN_GAP"
    assert payload["work_item_id"] == "parser-syntax"
    assert payload["work_item_bundle_path"] == output_path.relative_to(workspace).as_posix()


def test_architecture_index_lists_prior_docs_and_excludes_current_target(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    prior_path = workspace / "docs/plans/custom-design-gaps/prior-slice/implementation_architecture.md"
    current_path = workspace / "docs/plans/custom-design-gaps/current-slice/implementation_architecture.md"
    output_path = workspace / "state/index.md"
    bundle_path = workspace / "state/index.json"
    prior_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.parent.mkdir(parents=True, exist_ok=True)
    prior_path.write_text("# Prior Slice Architecture\n", encoding="utf-8")
    current_path.write_text("# Current Slice Architecture\n", encoding="utf-8")

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/build_lisp_frontend_architecture_index.py"),
        "--root",
        "docs/plans/custom-design-gaps",
        "--exclude",
        current_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
        "--bundle",
        bundle_path.relative_to(workspace).as_posix(),
    )

    index_text = output_path.read_text(encoding="utf-8")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert "prior-slice/implementation_architecture.md" in index_text
    assert "current-slice/implementation_architecture.md" not in index_text
    assert bundle["existing_architecture_count"] == 1
    assert bundle["architecture_index_path"] == output_path.relative_to(workspace).as_posix()


def test_classify_implementation_blocker_allows_roadmap_conflict(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/implementation_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps({"implementation_state": "BLOCKED", "blocker_class": "roadmap_conflict"}) + "\n",
        encoding="utf-8",
    )
    output_path = workspace / "state/blocker-route.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py"),
        "--implementation-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--work-item-source",
        "DESIGN_GAP",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == {
        "blocker_route": "DESIGN_REVISION_ALLOWED",
        "blocker_class": "roadmap_conflict",
        "block_reason": "implementation_design_revision_required",
    }


def test_classify_implementation_blocker_keeps_user_decision_terminal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/implementation_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps({"implementation_state": "BLOCKED", "blocker_class": "user_decision_required"}) + "\n",
        encoding="utf-8",
    )
    output_path = workspace / "state/blocker-route.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py"),
        "--implementation-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--work-item-source",
        "DESIGN_GAP",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == {
        "blocker_route": "TERMINAL_BLOCK",
        "blocker_class": "user_decision_required",
        "block_reason": "implementation_blocked",
    }


def test_work_item_terminal_keeps_external_dependency_blocked_for_recovery_classification(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/final_implementation_state.txt"
    review_path = workspace / "state/final_implementation_review_decision.txt"
    bundle_path = workspace / "state/implementation_state.json"
    output_path = workspace / "state/terminal-route.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("BLOCKED\n", encoding="utf-8")
    review_path.write_text("NOT_APPLICABLE\n", encoding="utf-8")
    bundle_path.write_text(
        json.dumps({"implementation_state": "BLOCKED", "blocker_class": "external_dependency_outside_authority"})
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py"),
        "--plan-review-decision",
        "APPROVE",
        "--implementation-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--implementation-review-decision-path",
        review_path.relative_to(workspace).as_posix(),
        "--implementation-bundle-path",
        bundle_path.relative_to(workspace).as_posix(),
        "--work-item-source",
        "DESIGN_GAP",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "terminal_route": "IMPLEMENTATION_BLOCKED",
        "block_reason": "implementation_blocked",
    }


def test_update_run_state_records_design_revision_without_terminal_item_state(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/run_state.json"
    summary_path = workspace / "artifacts/work/parser-syntax-summary.json"
    pointer_path = workspace / "state/item_summary_path.txt"
    drain_status_path = workspace / "state/drain_status.txt"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/update_lisp_frontend_run_state.py"),
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "design_revision",
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--reason",
        "implementation_design_revision_required",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["history"][-1]["event"] == "design_revision"
    assert "parser-syntax" not in state["completed_design_gaps"]
    assert "parser-syntax" not in state["blocked_design_gaps"]
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    assert pointer_path.read_text(encoding="utf-8").strip() == summary_path.relative_to(workspace).as_posix()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["item_status"] == "DESIGN_REVISED"


def test_update_run_state_design_revision_clears_prior_blocked_design_gap(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/run_state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {"reason": "implementation_blocked", "timestamp_utc": "2026-06-01T00:00:00Z"}
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/update_lisp_frontend_run_state.py"),
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "design_revision",
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--reason",
        "implementation_design_revision_required",
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "parser-syntax" not in state["blocked_design_gaps"]


def test_update_run_state_records_gap_design_revision_without_terminal_item_state(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/run_state.json"
    summary_path = workspace / "artifacts/work/parser-syntax-summary.json"
    pointer_path = workspace / "state/item_summary_path.txt"
    drain_status_path = workspace / "state/drain_status.txt"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/update_lisp_frontend_run_state.py"),
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "gap_design_revision",
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--reason",
        "implementation_architecture_under_scoped",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["history"][-1]["event"] == "gap_design_revision"
    assert "parser-syntax" not in state["completed_design_gaps"]
    assert "parser-syntax" not in state["blocked_design_gaps"]
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    assert pointer_path.read_text(encoding="utf-8").strip() == summary_path.relative_to(workspace).as_posix()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["item_status"] == "GAP_DESIGN_REVISED"


def test_detect_prior_blocked_design_gap_recovers_roadmap_conflict(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    output_path = workspace / "state/drain/prior-blocked-recovery.json"
    state_path.parent.mkdir(parents=True)
    progress_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {"reason": "implementation_blocked", "timestamp_utc": "2026-06-01T00:00:00Z"}
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    progress_path.write_text("# Progress Report\n\nBlocker class: roadmap_conflict\n", encoding="utf-8")

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py"),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == {
        "recovery_status": "RECOVER_BLOCKED_DESIGN_GAP",
        "design_gap_id": "parser-syntax",
        "progress_report_path": progress_path.relative_to(workspace).as_posix(),
        "blocker_class": "roadmap_conflict",
        "block_reason": "implementation_blocked",
    }


def test_detect_prior_blocked_design_gap_recovers_under_scoped_architecture(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    output_path = workspace / "state/drain/prior-blocked-recovery.json"
    state_path.parent.mkdir(parents=True)
    progress_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {"reason": "implementation_blocked", "timestamp_utc": "2026-06-01T00:00:00Z"}
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    progress_path.write_text(
        "# Progress Report\n\nThe approved implementation architecture is under-scoped for this gap.\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py"),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["recovery_status"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["design_gap_id"] == "parser-syntax"
    assert payload["progress_report_path"] == progress_path.relative_to(workspace).as_posix()


def test_design_gap_architect_stays_single_pass_for_stage7_scope():
    workflow = yaml.safe_load((ROOT / "workflows/library/lisp_frontend_design_gap_architect.v214.yaml").read_text())
    step_names = [step["name"] for step in workflow["steps"]]

    assert step_names == [
        "PrepareArchitectureTargets",
        "BuildExistingArchitectureIndex",
        "DraftDesignGapArchitecture",
        "ValidateDesignGapArchitecture",
    ]
    assert workflow["outputs"]["architecture_validation_status"]["from"]["ref"] == (
        "root.steps.ValidateDesignGapArchitecture.artifacts.architecture_validation_status"
    )
    assert workflow["outputs"]["work_item_bundle_path"]["from"]["ref"] == (
        "root.steps.ValidateDesignGapArchitecture.artifacts.work_item_bundle_path"
    )

    draft_step = next(step for step in workflow["steps"] if step["name"] == "DraftDesignGapArchitecture")
    fields = {field["name"]: field for field in draft_step["output_bundle"]["fields"]}

    assert set(fields) == {"draft_status"}
    assert draft_step["depends_on"]["inject"]["mode"] == "content"


def test_lisp_frontend_workflows_load(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)
    loader = WorkflowLoader(workspace)

    top = loader.load(workflow_path)
    assert workflow_input_contracts(top).get("roadmap_gate_path") is None
    proc_ref_top = loader.load(workspace / "workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml")
    proc_ref_inputs = workflow_input_contracts(proc_ref_top)
    assert proc_ref_inputs["artifact_work_root"]["default"] == "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION"
    assert proc_ref_inputs["artifact_checks_root"]["default"] == "artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION"
    assert proc_ref_inputs["artifact_review_root"]["default"] == "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION"
    design_delta_top = loader.load(workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml")
    design_delta_inputs = workflow_input_contracts(design_delta_top)
    assert "target_design_path" in design_delta_inputs
    assert "baseline_design_path" in design_delta_inputs
    for relpath in [
        "workflows/library/lisp_frontend_selector.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_selector.v214.yaml",
        "workflows/library/lisp_frontend_design_gap_architect.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml",
        "workflows/library/lisp_frontend_work_item.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml",
        "workflows/library/lisp_frontend_plan_phase.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml",
        "workflows/library/lisp_frontend_implementation_phase.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml",
    ]:
        loader.load(workspace / relpath)


def test_bind_workflow_inputs_prefers_provided_values_over_authored_defaults(tmp_path):
    result = compile_stage3_module(
        _write_runtime_default_module(tmp_path / "workflow_param_default_runtime.orc"),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    workflow = result.validated_bundles["defaults"]

    omitted = bind_workflow_inputs(workflow_input_contracts(workflow), {}, tmp_path)
    provided = bind_workflow_inputs(
        workflow_input_contracts(workflow),
        {"report_path": "provided.md"},
        tmp_path,
    )

    assert omitted["report_path"] == "artifacts/work/default.md"
    assert provided["report_path"] == "artifacts/work/provided.md"


def test_imported_workflow_call_binding_uses_callee_default_when_binding_is_omitted(tmp_path):
    entry_path = _write_runtime_imported_default_modules(tmp_path)
    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    helper_bundle = result.validated_bundles_by_name["defaults_pkg/helper::helper"]

    class _FakeExecutor:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace
            self.current_step = 0

        def _call_input_bindings(self, step):
            return step.get("with")

        def _resolve_runtime_value(self, raw_value, state, scope=None):
            del scope
            if isinstance(raw_value, dict) and raw_value.get("ref", "").startswith("inputs."):
                return state["inputs"][raw_value["ref"].split(".", 1)[1]]
            return raw_value

        def _contract_violation_result(self, message, details):
            return {"message": message, "details": details}

        def _json_safe_runtime_value(self, value):
            return value

    call_executor = CallExecutor(_FakeExecutor(tmp_path))
    state = {"inputs": {"required_path": "required.md", "override_report": "override.md"}}

    omitted_inputs, omitted_error = call_executor.resolve_bound_inputs(
        {
            "name": "CallHelper",
            "with": {
                "required_path": {"ref": "inputs.required_path"},
            },
        },
        helper_bundle,
        state,
    )
    provided_inputs, provided_error = call_executor.resolve_bound_inputs(
        {
            "name": "CallHelper",
            "with": {
                "required_path": {"ref": "inputs.required_path"},
                "optional_report": {"ref": "inputs.override_report"},
            },
        },
        helper_bundle,
        state,
    )

    assert omitted_error is None
    assert omitted_inputs == {
        "required_path": "artifacts/work/required.md",
        "optional_report": "default.md",
    }
    assert provided_error is None
    assert provided_inputs == {
        "required_path": "artifacts/work/required.md",
        "optional_report": "artifacts/work/override.md",
    }


def test_design_delta_selector_prompt_defines_target_and_baseline():
    prompt = (ROOT / "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md").read_text(
        encoding="utf-8"
    )

    assert "target design" in prompt.lower()
    assert "baseline design" in prompt.lower()
    assert "Return `DONE` only when the target delta" in prompt
    assert "MVP" not in prompt


def test_proc_ref_path_prompts_use_target_and_baseline_roles():
    prompt_paths = [
        ROOT / "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md",
        ROOT / "workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/draft_implementation_architecture.md",
        ROOT / "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md",
        ROOT / "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md",
    ]

    for path in prompt_paths:
        text = path.read_text(encoding="utf-8").lower()
        assert "target" in text, path
        assert "baseline" in text, path


def test_design_delta_blocker_revision_prompts_keep_roles_clear():
    prompt_paths = [
        ROOT / "workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_target_design_for_blocker.md",
        ROOT / "workflows/library/prompts/lisp_frontend_design_delta_work_item/review_target_design_revision.md",
    ]

    for path in prompt_paths:
        text = path.read_text(encoding="utf-8").lower()
        assert "target design" in text, path
        assert "baseline design" in text, path
        assert "workflow owns" not in text, path
        assert "drain loop" not in text, path


def test_blocked_implementation_recovery_prompt_keeps_roles_clear():
    path = ROOT / "workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md"
    text = path.read_text(encoding="utf-8")
    lower = text.lower()

    assert "GAP_DESIGN_REVISION_REQUIRED" in text
    assert "TARGET_DESIGN_REVISION_REQUIRED" in text
    assert "TERMINAL_BLOCKED" in text
    assert "target design" in lower
    assert "progress report" in lower
    assert "mark the drain" not in lower
    assert "workflow routing" not in lower


def test_shared_autonomous_prompt_roots_keep_full_mvp_semantics():
    shared_prompt_paths = [
        ROOT / "workflows/library/prompts/lisp_frontend_selector/select_next_work.md",
        ROOT / "workflows/library/prompts/lisp_frontend_design_gap_architect/draft_implementation_architecture.md",
        ROOT / "workflows/library/prompts/lisp_frontend_plan_phase/draft_plan.md",
        ROOT / "workflows/library/prompts/lisp_frontend_implementation_phase/implement_plan.md",
    ]

    for path in shared_prompt_paths:
        text = path.read_text(encoding="utf-8").lower()
        assert "full design" in text, path
        assert "mvp design" in text, path


def test_shared_prompt_roots_do_not_include_procref_specific_ids():
    shared_prompt_roots = [
        ROOT / "workflows/library/prompts/lisp_frontend_selector",
        ROOT / "workflows/library/prompts/lisp_frontend_design_gap_architect",
        ROOT / "workflows/library/prompts/lisp_frontend_plan_phase",
        ROOT / "workflows/library/prompts/lisp_frontend_implementation_phase",
    ]

    for root in shared_prompt_roots:
        for path in root.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            assert "LISP-PROC-REFS-PARTIAL-APPLICATION" not in text, path


def test_proc_ref_delta_drain_uses_proc_ref_backlog_root():
    text = (ROOT / "workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml").read_text(
        encoding="utf-8"
    )

    assert "docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION" in text


def test_design_delta_drain_uses_design_delta_library_variants():
    workflow = yaml.safe_load((ROOT / "workflows/examples/lisp_frontend_design_delta_drain.yaml").read_text())
    imports = workflow["imports"]

    assert imports["selector"] == "../library/lisp_frontend_design_delta_selector.v214.yaml"
    assert imports["design_gap_architect"] == "../library/lisp_frontend_design_delta_design_gap_architect.v214.yaml"
    assert imports["work_item"] == "../library/lisp_frontend_design_delta_work_item.v214.yaml"


def test_design_delta_work_item_routes_blocked_implementation_through_recovery_classifier():
    workflow = yaml.safe_load((ROOT / "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml").read_text())

    assert workflow["imports"] == {
        "plan_phase": "./lisp_frontend_design_delta_plan_phase.v214.yaml",
        "implementation_phase": "./lisp_frontend_design_delta_implementation_phase.v214.yaml",
    }
    classifier = next(step for step in workflow["steps"] if step["name"] == "ClassifyWorkItemTerminal")
    assert "--implementation-bundle-path" in classifier["command"]
    assert "--work-item-source" in classifier["command"]

    recovery_classifier = next(step for step in workflow["steps"] if step["name"] == "ClassifyBlockedImplementationRecovery")
    assert recovery_classifier["asset_file"] == (
        "prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md"
    )
    recovery_selector = next(step for step in workflow["steps"] if step["name"] == "SelectBlockedRecoveryRoute")
    assert any(part.endswith("select_lisp_frontend_blocked_recovery_route.py") for part in recovery_selector["command"])

    revision_loop = next(step for step in workflow["steps"] if step["name"] == "ReviewTargetDesignRevisionLoop")
    route_revision = next(step for step in revision_loop["repeat_until"]["steps"] if step["name"] == "RouteDesignRevisionWork")
    design_case = route_revision["match"]["cases"]["TARGET_DESIGN_REVISION_REQUIRED"]
    assert any(step["name"] == "ReviseTargetDesignForBlocker" for step in design_case["steps"])
    assert "GAP_DESIGN_REVISION_REQUIRED" in route_revision["match"]["cases"]
    assert "TERMINAL_BLOCKED" in route_revision["match"]["cases"]
    route_terminal = next(step for step in workflow["steps"] if step["name"] == "RouteWorkItemTerminal")
    terminal = route_terminal["match"]["cases"]["IMPLEMENTATION_BLOCKED"]
    recorder = next(step for step in terminal["steps"] if step["name"] == "RecordBlockedRecoveryOutcome")
    assert any(part.endswith("record_lisp_frontend_blocked_recovery_outcome.py") for part in recorder["command"])
    assert "${steps.SelectBlockedRecoveryRoute.artifacts.blocked_recovery_route}" in recorder["command"]
    assert "${steps.ReviewTargetDesignRevisionLoop.artifacts.design_revision_review_decision}" in recorder["command"]


def test_design_delta_drain_classifies_prior_blocked_recovery_before_revision():
    workflow = yaml.safe_load((ROOT / "workflows/examples/lisp_frontend_design_delta_drain.yaml").read_text())
    route = next(step for step in workflow["steps"] if step["name"] == "RoutePriorBlockedDesignGapRecovery")
    recover = route["match"]["cases"]["RECOVER_BLOCKED_DESIGN_GAP"]

    classifier = next(step for step in recover["steps"] if step["name"] == "ClassifyPriorBlockedImplementationRecovery")
    assert classifier["input_file"] == (
        "workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md"
    )
    reviser = next(step for step in recover["steps"] if step["name"] == "RevisePriorBlockedDesignGap")
    assert reviser["when"]["compare"]["right"] == "TARGET_DESIGN_REVISION_REQUIRED"
    recorder = next(step for step in recover["steps"] if step["name"] == "RecordPriorBlockedRecoveryOutcome")
    assert any(part.endswith("record_lisp_frontend_blocked_recovery_outcome.py") for part in recorder["command"])
    assert "${inputs.drain_state_root}/prior-blocked-recovery-decision.json" in recorder["command"]
    assert "continue" in recorder["command"]


def test_autonomous_drain_design_gap_path_stays_plan_scoped():
    workflow = yaml.safe_load((ROOT / "workflows/examples/lisp_frontend_autonomous_drain.yaml").read_text())
    drain_step = next(step for step in workflow["steps"] if step["name"] == "DrainLispFrontendWork")
    route_selection = next(step for step in drain_step["repeat_until"]["steps"] if step["name"] == "RouteSelection")
    design_gap_case = route_selection["match"]["cases"]["DRAFT_DESIGN_GAP"]

    assert design_gap_case["outputs"]["drain_status"]["from"]["ref"] == (
        "self.steps.RunDesignGapWorkItem.artifacts.drain_status"
    )
    assert [step["name"] for step in design_gap_case["steps"]] == [
        "DraftDesignGapArchitecture",
        "RunDesignGapWorkItem",
    ]


def test_implementation_review_checks_report_consumes_are_loop_safe():
    workflow_paths = [
        "workflows/library/lisp_frontend_implementation_phase.v214.yaml",
        "workflows/library/neurips_backlog_implementation_phase.yaml",
        "workflows/library/neurips_backlog_implementation_phase.v214.yaml",
    ]

    offenders = []
    for relpath in workflow_paths:
        workflow = yaml.safe_load((ROOT / relpath).read_text(encoding="utf-8"))
        for step in _iter_workflow_steps(workflow.get("steps")):
            if step.get("name") != "ReviewImplementation":
                continue
            for consume in step.get("consumes") or []:
                if consume.get("artifact") == "checks_report" and consume.get("freshness", "any") != "any":
                    offenders.append(f"{relpath}:{step.get('name')}:checks_report")

    assert offenders == []


def _next_selector_dir(workspace: Path) -> Path:
    for selector_dir in sorted(workspace.glob("state/**/selector")):
        if not (selector_dir / "selection.json").exists():
            return selector_dir
    raise AssertionError("No pending selector directory found")


def _write_selector_design_gap(workspace: Path) -> None:
    selector_dir = _next_selector_dir(workspace)
    (selector_dir / "selection.json").write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "parser-syntax",
                "source_design_path": "docs/design/workflow_lisp_frontend_mvp_specification.md",
                "source_sections": ["Stage 1: Frontend Core Without Workflow Execution"],
                "missing_component": "Parser and syntax objects",
                "proposed_scope": "Draft a parser and syntax-object implementation architecture.",
                "selection_rationale": "Parser is the first MVP dependency.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_selector_done(workspace: Path) -> None:
    selector_dir = _next_selector_dir(workspace)
    (selector_dir / "selection.json").write_text(
        json.dumps(
            {
                "selection_status": "DONE",
                "selection_rationale": "No active backlog items or design gaps remain.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_design_gap_architecture(workspace: Path) -> None:
    roots = sorted(workspace.glob("state/**/design-gap-architect"))
    for root in roots:
        bundle_path = root / "draft-bundle.json"
        if bundle_path.exists():
            continue
        architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
        context_path = root / "work_item_context.md"
        checks_path = root / "check_commands.json"
        plan_target_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
        architecture_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.parent.mkdir(parents=True, exist_ok=True)
        architecture_path.write_text("# Parser Syntax Architecture\n", encoding="utf-8")
        context_path.write_text("# Parser Syntax Work Item\n", encoding="utf-8")
        checks_path.write_text(json.dumps(["python -c \"print('gap-check')\""]) + "\n", encoding="utf-8")
        bundle_path.write_text(
            json.dumps(
                {
                    "draft_status": "DRAFTED",
                    "design_gap_id": "parser-syntax",
                    "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                    "work_item_context_path": context_path.relative_to(workspace).as_posix(),
                    "check_commands_path": checks_path.relative_to(workspace).as_posix(),
                    "plan_target_path": plan_target_path.relative_to(workspace).as_posix(),
                    "summary": "Parser syntax gap architecture.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending design-gap architect root found")


def _write_plan(workspace: Path) -> None:
    for pointer in sorted(workspace.glob("state/**/plan-phase/plan_path.txt")):
        target = workspace / pointer.read_text(encoding="utf-8").strip()
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Lisp Work Plan\n\n## Verification\n- `python -c \"print('gap-check')\"`\n", encoding="utf-8")
        return
    raise AssertionError("No pending plan pointer found")


def _plan_target(workspace: Path) -> Path:
    for pointer in sorted(workspace.glob("state/**/plan-phase/plan_path.txt")):
        return workspace / pointer.read_text(encoding="utf-8").strip()
    raise AssertionError("No plan pointer found")


def _pending_plan_review_root(workspace: Path) -> Path:
    for root in sorted(workspace.glob("state/**/plan-phase")):
        if (root / "plan_review_report_path.txt").exists():
            return root
    raise AssertionError("No pending plan review root found")


def _write_plan_review(workspace: Path) -> None:
    root = _pending_plan_review_root(workspace)
    decision = root / "plan_review_decision.txt"
    pointer = root / "plan_review_report_path.txt"
    target = workspace / pointer.read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"decision": "APPROVE", "findings": []}) + "\n", encoding="utf-8")
    decision.write_text("APPROVE\n", encoding="utf-8")


def _write_plan_review_revise(workspace: Path) -> None:
    root = _pending_plan_review_root(workspace)
    decision = root / "plan_review_decision.txt"
    pointer = root / "plan_review_report_path.txt"
    target = workspace / pointer.read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"decision": "REVISE", "findings": [{"id": "P1"}]}) + "\n", encoding="utf-8")
    decision.write_text("REVISE\n", encoding="utf-8")


def _revise_plan(workspace: Path) -> None:
    target = _plan_target(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Lisp Work Plan\n\nRevised after review.\n\n## Verification\n- `python -c \"print('gap-check')\"`\n",
        encoding="utf-8",
    )



def _write_execution_state(workspace: Path) -> None:
    for root in sorted(workspace.glob("state/**/implementation-phase")):
        bundle_path = root / "implementation_state.json"
        if bundle_path.exists():
            continue
        target_pointer = root / "execution_report_target_path.txt"
        target = workspace / target_pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Execution Report\n\nCompleted.\n", encoding="utf-8")
        bundle_path.write_text(
            json.dumps(
                {
                    "implementation_state": "COMPLETED",
                    "execution_report_path": target.relative_to(workspace).as_posix(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending implementation phase root found")


def _write_execution_state_without_completed_path(workspace: Path) -> None:
    for root in sorted(workspace.glob("state/**/implementation-phase")):
        bundle_path = root / "implementation_state.json"
        if bundle_path.exists():
            continue
        target_pointer = root / "execution_report_target_path.txt"
        target = workspace / target_pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Execution Report\n\nCompleted from canonical target only.\n", encoding="utf-8")
        bundle_path.write_text(
            json.dumps(
                {
                    "implementation_state": "COMPLETED",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending implementation phase root found")


def _write_execution_state_noncanonical(workspace: Path) -> None:
    for root in sorted(workspace.glob("state/**/implementation-phase")):
        bundle_path = root / "implementation_state.json"
        if bundle_path.exists():
            continue
        target = workspace / "artifacts/work/noncanonical-execution-report.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Execution Report\n\nCompleted at noncanonical path.\n", encoding="utf-8")
        bundle_path.write_text(
            json.dumps(
                {
                    "implementation_state": "COMPLETED",
                    "execution_report_path": target.relative_to(workspace).as_posix(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending implementation phase root found")


def _write_blocked_roadmap_conflict(workspace: Path) -> None:
    _write_blocked_implementation_state(workspace, "roadmap_conflict", "Blocked by design conflict.")


def _write_blocked_user_decision_required(workspace: Path) -> None:
    _write_blocked_implementation_state(workspace, "user_decision_required", "Blocked pending user decision.")


def _write_blocked_external_under_scoped_gap(workspace: Path) -> None:
    _write_blocked_implementation_state(
        workspace,
        "external_dependency_outside_authority",
        "The approved implementation architecture is under-scoped for this design gap.",
    )


def _write_blocked_implementation_state(workspace: Path, blocker_class: str, progress_text: str) -> None:
    for root in sorted(workspace.glob("state/**/implementation-phase")):
        bundle_path = root / "implementation_state.json"
        if bundle_path.exists():
            continue
        progress_pointer = root / "progress_report_target_path.txt"
        target = workspace / progress_pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# Progress Report\n\n{progress_text}\n", encoding="utf-8")
        bundle_path.write_text(
            json.dumps({"implementation_state": "BLOCKED", "blocker_class": blocker_class}, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending implementation phase root found")


def _write_blocked_recovery_bundle(workspace: Path, route: str, reason: str) -> None:
    payload = {
        "blocked_recovery_route": route,
        "reason": reason,
        "summary": f"{route} selected for test.",
    }
    targets: list[Path] = []
    for root in sorted(workspace.glob("state/**/design-gap-work-item")):
        if (root / "work-item-inputs.json").exists():
            targets.append(root / "blocked-implementation-recovery.json")
    drain_root = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain"
    if (drain_root / "prior-blocked-recovery.json").exists():
        targets.append(drain_root / "prior-blocked-recovery-decision.json")
    if not targets:
        raise AssertionError("No blocked recovery bundle target found")
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _classify_blocked_recovery_gap_design_required(workspace: Path) -> None:
    _write_blocked_recovery_bundle(
        workspace,
        "GAP_DESIGN_REVISION_REQUIRED",
        "implementation_architecture_under_scoped",
    )


def _classify_blocked_recovery_target_design_required(workspace: Path) -> None:
    _write_blocked_recovery_bundle(
        workspace,
        "TARGET_DESIGN_REVISION_REQUIRED",
        "target_design_contract_gap",
    )


def _classify_blocked_recovery_terminal(workspace: Path) -> None:
    _write_blocked_recovery_bundle(
        workspace,
        "TERMINAL_BLOCKED",
        "user_decision_required",
    )


def _leave_execution_state_missing(_workspace: Path) -> None:
    return


def _implementation_execution_report_target(workspace: Path) -> Path:
    for pointer in sorted(workspace.glob("state/**/implementation-phase/execution_report_target_path.txt")):
        return workspace / pointer.read_text(encoding="utf-8").strip()
    raise AssertionError("No execution report target pointer found")


def _published_execution_report_path(workspace: Path) -> Path:
    for pointer in sorted(workspace.glob("state/**/implementation-phase/execution_report_path.txt")):
        return workspace / pointer.read_text(encoding="utf-8").strip()
    raise AssertionError("No published execution report pointer found")


def _pending_implementation_review_root(workspace: Path) -> Path:
    for root in sorted(workspace.glob("state/**/implementation-phase")):
        if (root / "implementation_review_report_path.txt").exists():
            return root
    raise AssertionError("No pending implementation review root found")


def _write_implementation_review(workspace: Path) -> None:
    root = _pending_implementation_review_root(workspace)
    decision = root / "implementation_review_decision.txt"
    pointer = root / "implementation_review_report_path.txt"
    target = workspace / pointer.read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Implementation Review\n\nApproved.\n", encoding="utf-8")
    decision.write_text("APPROVE\n", encoding="utf-8")


def _write_implementation_review_revise(workspace: Path) -> None:
    root = _pending_implementation_review_root(workspace)
    decision = root / "implementation_review_decision.txt"
    pointer = root / "implementation_review_report_path.txt"
    target = workspace / pointer.read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Implementation Review\n\nRevise required.\n", encoding="utf-8")
    decision.write_text("REVISE\n", encoding="utf-8")


def _fix_implementation(workspace: Path) -> None:
    target = _implementation_execution_report_target(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Execution Report\n\nFixed after review.\n", encoding="utf-8")


def _fix_implementation_noncanonical(workspace: Path) -> None:
    target = _published_execution_report_path(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Execution Report\n\nFixed after review at noncanonical path.\n", encoding="utf-8")


def _design_revision_work_item_root(workspace: Path) -> Path:
    for root in sorted(workspace.glob("state/**/design-gap-work-item")):
        if (root / "work-item-inputs.json").exists():
            return root
    raise AssertionError("No design-gap work-item root found")


def _revise_target_design_for_blocker(workspace: Path) -> None:
    target = workspace / _design_delta_workflow_inputs()["target_design_path"]
    target.write_text(
        target.read_text(encoding="utf-8") + "\n\n## Blocker Revision\n\nAdded missing contract.\n",
        encoding="utf-8",
    )
    root = _design_revision_work_item_root(workspace)
    report = root / "design-revision-report.json"
    report.write_text(
        json.dumps(
            {
                "design_revision_decision": "REVISED",
                "summary": "Updated the target design.",
                "changed_sections": ["Blocker Revision"],
                "blocker_class": "roadmap_conflict",
                "reason": "implementation_design_revision_required",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_design_revision_review_approve(workspace: Path) -> None:
    root = _design_revision_work_item_root(workspace)
    report = workspace / "artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/design-revision-review.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Design Revision Review\n\nApproved.\n", encoding="utf-8")
    (root / "design-revision-review-report-path.txt").write_text(
        report.relative_to(workspace).as_posix() + "\n",
        encoding="utf-8",
    )
    (root / "design-revision-review-decision.txt").write_text("APPROVE\n", encoding="utf-8")


def _seed_prior_blocked_design_gap(workspace: Path) -> None:
    run_state = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json"
    progress = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    run_state.parent.mkdir(parents=True, exist_ok=True)
    progress.parent.mkdir(parents=True, exist_ok=True)
    run_state.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {"reason": "implementation_blocked", "timestamp_utc": "2026-06-01T00:00:00Z"}
                },
                "history": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    progress.write_text("# Progress Report\n\nBlocker class: roadmap_conflict\n", encoding="utf-8")


def _revise_prior_blocked_design_gap(workspace: Path) -> None:
    target = workspace / _design_delta_workflow_inputs()["target_design_path"]
    target.write_text(
        target.read_text(encoding="utf-8") + "\n\n## Prior Blocker Revision\n\nAdded startup recovery contract.\n",
        encoding="utf-8",
    )
    report = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/prior-blocked-design-revision-report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "design_revision_decision": "REVISED",
                "summary": "Updated target design from prior blocked state.",
                "changed_sections": ["Prior Blocker Revision"],
                "blocker_class": "roadmap_conflict",
                "reason": "implementation_design_revision_required",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_prior_design_revision_review_approve(workspace: Path) -> None:
    report = workspace / "artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/prior-blocked-design-revision-review.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Prior Design Revision Review\n\nApproved.\n", encoding="utf-8")
    root = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain"
    (root / "prior-blocked-design-revision-review-report-path.txt").write_text(
        report.relative_to(workspace).as_posix() + "\n",
        encoding="utf-8",
    )
    (root / "prior-blocked-design-revision-review-decision.txt").write_text("APPROVE\n", encoding="utf-8")


def _provider_step_matches(actual: str | None, expected: str) -> bool:
    if actual is None:
        return True
    return actual == expected or actual.endswith(f".{expected}")


def _provider_step_called(state: dict, expected: str) -> bool:
    return any(_provider_step_matches(actual, expected) for actual in state.get("__provider_step_names", []))


def _run_workflow_with_providers(
    workspace: Path,
    workflow_path: Path,
    provider_sequence,
    require_all_providers: bool = True,
    workflow_inputs: dict | None = None,
):
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    bound_inputs = bind_workflow_inputs(workflow_input_contracts(workflow), workflow_inputs or _workflow_inputs(), workspace)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_path.relative_to(workspace).as_posix(),
        _bundle_context_dict(workflow),
        bound_inputs=bound_inputs,
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)
    call_index = {"value": 0}
    provider_step_names: list[str | None] = []

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **kwargs):
        assert call_index["value"] < len(provider_sequence)
        expected_step, writer = provider_sequence[call_index["value"]]
        actual_step = kwargs.get("step_name")
        assert _provider_step_matches(actual_step, expected_step)
        provider_step_names.append(actual_step)
        call_index["value"] += 1
        writer(workspace)
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()
    if require_all_providers:
        assert call_index["value"] == len(provider_sequence)
    state["__provider_calls"] = call_index["value"]
    state["__provider_step_names"] = provider_step_names
    return state


def test_lisp_frontend_drain_design_gap_runtime_smoke(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
            ("SelectNextWork", _write_selector_done),
        ],
    )

    assert state["__provider_calls"] == 7
    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["drain_status"] == "DONE"
    assert summary["completed_design_gaps"] == ["parser-syntax"]
    assert (
        workspace
        / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    ).is_file()


def test_selected_item_fresh_plan(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
            ("SelectNextWork", _write_selector_done),
        ],
    )

    assert _provider_step_called(state, "DraftPlan")
    assert _plan_target(workspace).is_file()


def test_selected_item_reuses_approved_plan(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    first_run_state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _leave_execution_state_missing),
        ],
    )

    assert first_run_state["status"] == "failed"
    assert any(workspace.glob("state/**/final_plan_review_decision.txt"))
    assert _provider_step_called(first_run_state, "DraftPlan")
    assert _provider_step_called(first_run_state, "ReviewPlan")

    resume_sequence = [
        ("ExecuteImplementation", _write_execution_state),
        ("ReviewImplementation", _write_implementation_review),
        ("SelectNextWork", _write_selector_done),
    ]
    call_index = {"value": 0}
    provider_step_names: list[str | None] = []

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **kwargs):
        assert call_index["value"] < len(resume_sequence)
        expected_step, writer = resume_sequence[call_index["value"]]
        actual_step = kwargs.get("step_name")
        assert _provider_step_matches(actual_step, expected_step)
        provider_step_names.append(actual_step)
        call_index["value"] += 1
        writer(workspace)
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ), patch("os.getcwd", return_value=str(workspace)):
        result = resume_workflow(run_id="test-run", repair=False, force_restart=False)

    resumed_state = StateManager(workspace=workspace, run_id="test-run").load()
    named_provider_steps = [step for step in provider_step_names if step is not None]

    assert result == 0
    assert call_index["value"] == len(resume_sequence)
    assert resumed_state.status == "completed"
    assert all(not _provider_step_matches(step, "DraftPlan") for step in named_provider_steps)
    assert all(not _provider_step_matches(step, "ReviewPlan") for step in named_provider_steps)


def test_lisp_frontend_plan_review_revise_then_approve(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review_revise),
            ("RevisePlan", _revise_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
            ("SelectNextWork", _write_selector_done),
        ],
    )

    assert _provider_step_called(state, "RevisePlan")
    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["drain_status"] == "DONE"
    assert summary["completed_design_gaps"] == ["parser-syntax"]
    assert "Revised after review" in _plan_target(workspace).read_text(encoding="utf-8")


def test_lisp_frontend_implementation_review_revise_then_approve(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review_revise),
            ("FixImplementation", _fix_implementation),
            ("ReviewImplementation", _write_implementation_review),
            ("SelectNextWork", _write_selector_done),
        ],
    )

    assert _provider_step_called(state, "FixImplementation")
    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["drain_status"] == "DONE"
    assert summary["completed_design_gaps"] == ["parser-syntax"]
    assert "Fixed after review" in _implementation_execution_report_target(workspace).read_text(encoding="utf-8")


def test_lisp_frontend_completed_execution_uses_canonical_target_without_completed_path(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state_without_completed_path),
            ("ReviewImplementation", _write_implementation_review),
            ("SelectNextWork", _write_selector_done),
        ],
    )

    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["status"] == "completed"
    assert summary["drain_status"] == "DONE"
    assert summary["completed_design_gaps"] == ["parser-syntax"]
    assert _published_execution_report_path(workspace) == _implementation_execution_report_target(workspace)
    assert "Completed from canonical target only" in _published_execution_report_path(workspace).read_text(
        encoding="utf-8"
    )


def test_lisp_frontend_completed_execution_requires_canonical_target_path(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state_noncanonical),
        ],
        require_all_providers=False,
    )

    assert state["status"] == "failed"
    assert state["__provider_calls"] == 5
    assert not _implementation_execution_report_target(workspace).is_file()


def test_lisp_frontend_plan_review_exhaustion_records_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            *[item for _ in range(12) for item in [
                ("ReviewPlan", _write_plan_review_revise),
                ("RevisePlan", _revise_plan),
            ]],
        ],
    )

    assert _provider_step_called(state, "RevisePlan")
    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["drain_status"] == "BLOCKED"
    assert summary["completed_design_gaps"] == []
    assert summary["blocked_design_gaps"]["parser-syntax"]["reason"] == "plan_review_exhausted"


def test_lisp_frontend_implementation_review_exhaustion_records_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            *[item for _ in range(40) for item in [
                ("ReviewImplementation", _write_implementation_review_revise),
                ("FixImplementation", _fix_implementation),
            ]],
        ],
    )

    assert _provider_step_called(state, "FixImplementation")
    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["drain_status"] == "BLOCKED"
    assert summary["completed_design_gaps"] == []
    assert summary["blocked_design_gaps"]["parser-syntax"]["reason"] == "implementation_review_exhausted"


def test_design_delta_target_design_recovery_revises_design_and_continues(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    workflow_path = workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_blocked_roadmap_conflict),
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_target_design_required),
            ("ReviseTargetDesignForBlocker", _revise_target_design_for_blocker),
            ("ReviewTargetDesignRevision", _write_design_revision_review_approve),
            ("SelectNextWork", _write_selector_done),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )
    run_state = json.loads(
        (workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json").read_text(encoding="utf-8")
    )
    target_text = (workspace / _design_delta_workflow_inputs()["target_design_path"]).read_text(encoding="utf-8")

    assert state["status"] == "completed"
    assert summary["drain_status"] == "DONE"
    assert any(event["event"] == "design_revision" for event in run_state["history"])
    assert "parser-syntax" not in run_state["blocked_design_gaps"]
    assert "Blocker Revision" in target_text


def test_design_delta_gap_design_recovery_continues_without_target_edit(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    workflow_path = workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_blocked_external_under_scoped_gap),
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_gap_design_required),
            ("SelectNextWork", _write_selector_done),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )
    run_state = json.loads(
        (workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json").read_text(encoding="utf-8")
    )
    target_text = (workspace / _design_delta_workflow_inputs()["target_design_path"]).read_text(encoding="utf-8")

    assert state["status"] == "completed"
    assert summary["drain_status"] == "DONE"
    assert any(event["event"] == "gap_design_revision" for event in run_state["history"])
    assert "parser-syntax" not in run_state["blocked_design_gaps"]
    assert "Blocker Revision" not in target_text


def test_design_delta_prior_blocked_gap_revises_design_before_selection(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    _seed_prior_blocked_design_gap(workspace)
    workflow_path = workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("ClassifyPriorBlockedImplementationRecovery", _classify_blocked_recovery_target_design_required),
            ("RevisePriorBlockedDesignGap", _revise_prior_blocked_design_gap),
            ("ReviewPriorBlockedDesignRevision", _write_prior_design_revision_review_approve),
            ("SelectNextWork", _write_selector_done),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    run_state = json.loads(
        (workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json").read_text(encoding="utf-8")
    )
    target_text = (workspace / _design_delta_workflow_inputs()["target_design_path"]).read_text(encoding="utf-8")

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 4
    assert any(event["event"] == "design_revision" for event in run_state["history"])
    assert "parser-syntax" not in run_state["blocked_design_gaps"]
    assert "Prior Blocker Revision" in target_text


def test_design_delta_prior_blocked_gap_design_recovery_before_selection(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    _seed_prior_blocked_design_gap(workspace)
    workflow_path = workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("ClassifyPriorBlockedImplementationRecovery", _classify_blocked_recovery_gap_design_required),
            ("SelectNextWork", _write_selector_done),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    run_state = json.loads(
        (workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json").read_text(encoding="utf-8")
    )
    target_text = (workspace / _design_delta_workflow_inputs()["target_design_path"]).read_text(encoding="utf-8")

    assert state["status"] == "completed"
    assert any(event["event"] == "gap_design_revision" for event in run_state["history"])
    assert "parser-syntax" not in run_state["blocked_design_gaps"]
    assert "Prior Blocker Revision" not in target_text


def test_design_delta_terminal_blocker_does_not_revise_design(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    workflow_path = workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_blocked_user_decision_required),
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_terminal),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert state["status"] == "completed"
    assert summary["drain_status"] == "BLOCKED"
    assert summary["blocked_design_gaps"]["parser-syntax"]["reason"] == "implementation_blocked"
    assert state["__provider_calls"] == 6
    assert "Blocker Revision" not in (
        workspace / _design_delta_workflow_inputs()["target_design_path"]
    ).read_text(encoding="utf-8")


def test_lisp_frontend_drain_done_runtime_smoke(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [("SelectNextWork", _write_selector_done)],
    )

    assert state["__provider_calls"] == 1
    summary = json.loads(
        (workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["drain_status"] == "DONE"
