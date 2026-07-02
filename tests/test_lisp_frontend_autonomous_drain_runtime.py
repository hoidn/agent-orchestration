import json
import shutil
import subprocess
import sys
from dataclasses import is_dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
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
        "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json",
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
        "workflows/library/lisp_frontend_design_delta_done_review.v214.yaml",
        "workflows/library/lisp_frontend_plan_phase.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml",
        "workflows/library/lisp_frontend_implementation_phase.v214.yaml",
        "workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml",
        "workflows/library/scripts/build_lisp_frontend_architecture_index.py",
        "workflows/library/scripts/build_lisp_frontend_backlog_manifest.py",
        "workflows/library/scripts/build_neurips_backlog_manifest.py",
        "workflows/library/scripts/prepare_lisp_frontend_iteration_paths.py",
        "workflows/library/scripts/project_lisp_frontend_selector_manifest.py",
        "workflows/library/scripts/project_lisp_frontend_progress_signals.py",
        "workflows/library/scripts/evaluate_workflow_non_progress.py",
        "workflows/library/scripts/publish_lisp_frontend_selection_bundle.py",
        "workflows/library/scripts/project_lisp_frontend_done_review.py",
        "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py",
        "workflows/library/scripts/materialize_lisp_frontend_blocked_recovery_bundle.py",
        "workflows/library/scripts/prepare_lisp_frontend_recovered_design_gap_work_item.py",
        "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py",
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "workflows/library/scripts/materialize_lisp_frontend_recovered_design_gap_draft.py",
        "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py",
        "workflows/library/scripts/update_lisp_frontend_run_state.py",
        "workflows/library/scripts/workflow_recovery_dependencies.py",
        "workflows/library/scripts/record_lisp_frontend_design_revision_outcome.py",
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "workflows/library/scripts/record_workflow_step_back_outcome.py",
        "workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py",
        "workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py",
        "workflows/library/scripts/record_lisp_frontend_recovered_retry_unavailable.py",
        "workflows/library/scripts/write_lisp_frontend_drain_status.py",
        "workflows/library/scripts/write_lisp_frontend_recovery_status.py",
        "workflows/library/scripts/write_lisp_frontend_relpath_value.py",
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
        "post_wcc_inventory_path": (
            "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json"
        ),
        "progress_ledger_path": "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json",
    }


def _recovery_dependency_edge(
    *,
    blocked: str = "parser-syntax",
    blocker: str = "generic-context-capability",
    reason_code: str = "missing_prerequisite",
    downstream: list[str] | None = None,
) -> dict:
    return {
        "schema": "workflow_recovery_dependency_edge/v1",
        "blocked_work": {"source": "DESIGN_GAP", "id": blocked},
        "blocker_work": {"source": "DESIGN_GAP", "id": blocker},
        "relation": "requires_completion",
        "reason_code": reason_code,
        "ready_when": {"kind": "completed", "source": "DESIGN_GAP", "id": blocker},
        "retry_target": {"source": "DESIGN_GAP", "id": blocked},
        "downstream_work": [{"source": "DESIGN_GAP", "id": item} for item in downstream or []],
    }


def _write_selector_manifest_gap_architecture(
    workspace: Path, gap_id: str, *, root: str = "docs/plans/DRAIN/design-gaps"
) -> Path:
    path = workspace / root / gap_id / "implementation_architecture.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {gap_id}\n\nDesign gap id: `{gap_id}`\nStatus: draft\n",
        encoding="utf-8",
    )
    (path.parent / "execution_plan.md").write_text("# execution plan\n", encoding="utf-8")
    return path


def _run_script(workspace: Path, *argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", *argv],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=check,
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


def test_architecture_validator_rejects_run_scoped_paths_in_durable_docs(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    context_path = workspace / "state/gap/work_item_context.md"
    checks_path = workspace / "state/gap/check_commands.json"
    plan_target_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    architecture_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    architecture_path.write_text(
        "# Parser Syntax Architecture\n\n"
        "- `state/workflow_lisp/calls/20260701T000000Z-run/root/work_item_context.md`\n",
        encoding="utf-8",
    )
    plan_target_path.write_text(
        "# Parser Syntax Plan\n\n"
        "- `state/LISP-DRAIN/drain/iterations/1/recovered-gap/work_item_context.md`\n",
        encoding="utf-8",
    )
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
    assert payload["architecture_validation_status"] == "INVALID"
    assert "must not embed generated run-scoped path" in payload["reason"]
    assert "work_item_bundle_path" not in payload


def test_architecture_validator_requires_approved_review_when_provided(tmp_path):
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

    cases = [
        ("APPROVE", "VALID", True),
        ("REVISE", "INVALID", False),
        ("BLOCKED", "BLOCKED", False),
    ]
    for decision, expected_status, expect_bundle in cases:
        review_path = workspace / f"state/gap/review-{decision.lower()}.json"
        review_path.write_text(
            json.dumps({"review_decision": decision, "reason": f"{decision} reason."}) + "\n",
            encoding="utf-8",
        )
        output_path = workspace / f"state/gap/validation-{decision.lower()}.json"

        _run_script(
            workspace,
            str(ROOT / "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py"),
            "--draft-bundle-path",
            draft_path.relative_to(workspace).as_posix(),
            "--review-bundle-path",
            review_path.relative_to(workspace).as_posix(),
            "--output",
            output_path.relative_to(workspace).as_posix(),
        )

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["architecture_validation_status"] == expected_status
        assert ("work_item_bundle_path" in payload) is expect_bundle


def test_architecture_validator_rejects_malformed_review_bundle(tmp_path):
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
            }
        )
        + "\n",
        encoding="utf-8",
    )
    review_path = workspace / "state/gap/review.json"
    review_path.write_text(json.dumps({"review_decision": "MAYBE"}) + "\n", encoding="utf-8")
    output_path = workspace / "state/gap/validation.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py"),
        "--draft-bundle-path",
        draft_path.relative_to(workspace).as_posix(),
        "--review-bundle-path",
        review_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["architecture_validation_status"] == "INVALID"
    assert "Unsupported review_decision" in payload["reason"]
    assert "work_item_bundle_path" not in payload


def test_recovered_design_gap_materializer_reconstructs_missing_prior_bundle(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    recovery_path = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/blocked-recovery.json"
    output_path = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/recovered-gap/draft-architecture.json"
    architecture_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    architecture_path.write_text("# Parser Syntax Architecture\n", encoding="utf-8")
    plan_path.write_text("# Parser Syntax Execution Plan\n", encoding="utf-8")
    recovery_path.write_text(
        json.dumps(
            {
                "pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "RETRY_READY",
                "recovery_event_id": "old-run:parser-syntax:implementation-blocked",
                "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                "plan_path": plan_path.relative_to(workspace).as_posix(),
                "progress_report_path": "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/parser-syntax/progress_report.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/materialize_lisp_frontend_recovered_design_gap_draft.py"),
        "--recovery-bundle-path",
        recovery_path.relative_to(workspace).as_posix(),
        "--drain-state-root",
        "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["draft_status"] == "DRAFTED"
    assert payload["design_gap_id"] == "parser-syntax"
    assert payload["architecture_path"] == architecture_path.relative_to(workspace).as_posix()
    assert payload["plan_target_path"] == plan_path.relative_to(workspace).as_posix()
    assert payload["work_item_context_path"].endswith("/recovered-gap/recovered-work-item-context.md")
    assert payload["check_commands_path"].endswith("/recovered-gap/recovered-check-commands.json")
    assert "reconstructed from durable blocked state" in payload["summary"]
    checks = json.loads((workspace / payload["check_commands_path"]).read_text(encoding="utf-8"))
    assert f"test -f {architecture_path.relative_to(workspace).as_posix()}" in checks


def test_recovered_design_gap_materializer_embeds_prior_progress_report(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/parser-syntax/progress_report.md"
    recovery_path = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/blocked-recovery.json"
    output_path = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/recovered-gap/draft-architecture.json"
    architecture_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    architecture_path.write_text("# Parser Syntax Architecture\n", encoding="utf-8")
    plan_path.write_text("# Parser Syntax Execution Plan\n", encoding="utf-8")
    progress_path.write_text(
        "Status: BLOCKED\n\nBlocking evidence:\n- selector fails with type_unknown ExampleType\n",
        encoding="utf-8",
    )
    recovery_path.write_text(
        json.dumps(
            {
                "pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP",
                "design_gap_id": "parser-syntax",
                "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                "recovery_reason": "implementation_architecture_under_scoped",
                "recovery_status": "",
                "recovery_event_id": "old-run:parser-syntax:implementation-blocked",
                "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                "plan_path": plan_path.relative_to(workspace).as_posix(),
                "progress_report_path": progress_path.relative_to(workspace).as_posix(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/materialize_lisp_frontend_recovered_design_gap_draft.py"),
        "--recovery-bundle-path",
        recovery_path.relative_to(workspace).as_posix(),
        "--drain-state-root",
        "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    context = (workspace / payload["work_item_context_path"]).read_text(encoding="utf-8")
    assert "selector fails with type_unknown ExampleType" in context


def test_blocked_recovery_detector_honors_generic_step_back_decision(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    decision = workspace / "state/non-progress-decision.json"
    output = workspace / "state/blocked-recovery.json"
    run_state.parent.mkdir(parents=True)
    run_state.write_text(
        json.dumps(
            {
                "blocked_design_gaps": {},
                "blocked_items": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision.write_text(
        json.dumps(
            {
                "route": "STEP_BACK_REQUIRED",
                "trigger_codes": ["same_work_item_repeatedly_blocked"],
                "failure_fingerprint": "same-work",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--architecture-index-root",
        "docs/plans/design-gaps",
        "--non-progress-decision-path",
        decision.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "BLOCKED"
    assert payload["recovery_status"] == "STEP_BACK_REQUIRED"
    assert payload["blocker_class"] == "workflow_non_progress"
    assert payload["block_reason"] == "same-work"


def test_blocked_recovery_detector_prefers_recoverable_gap_over_generic_step_back(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    decision = workspace / "state/non-progress-decision.json"
    output = workspace / "state/blocked-recovery.json"
    progress = workspace / "artifacts/work/gap-a/progress_report.md"
    architecture = workspace / "docs/plans/design-gaps/gap-a/implementation_architecture.md"
    plan = workspace / "docs/plans/design-gaps/gap-a/execution_plan.md"
    run_state.parent.mkdir(parents=True)
    progress.parent.mkdir(parents=True)
    architecture.parent.mkdir(parents=True)
    progress.write_text("Status: BLOCKED\n", encoding="utf-8")
    architecture.write_text("# Gap A\n", encoding="utf-8")
    plan.write_text("# Plan A\n", encoding="utf-8")
    run_state.write_text(
        json.dumps(
            {
                "blocked_design_gaps": {
                    "gap-a": {
                        "reason": "implementation_blocked",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "recovery_event_id": "run:gap-a:blocked",
                        "progress_report_path": progress.relative_to(workspace).as_posix(),
                        "architecture_path": architecture.relative_to(workspace).as_posix(),
                        "plan_path": plan.relative_to(workspace).as_posix(),
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision.write_text(
        json.dumps(
            {
                "route": "STEP_BACK_REQUIRED",
                "trigger_codes": ["same_work_item_repeatedly_blocked"],
                "failure_fingerprint": "same-work",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--architecture-index-root",
        "docs/plans/design-gaps",
        "--non-progress-decision-path",
        decision.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["design_gap_id"] == "gap-a"
    assert payload["recovery_route"] == "GAP_DESIGN_REVISION_REQUIRED"


def _write_blocked_gap_run_state(run_state: Path, workspace: Path, *, history: list[dict]) -> tuple[Path, Path, Path]:
    progress = workspace / "artifacts/work/gap-a/progress_report.md"
    architecture = workspace / "docs/plans/design-gaps/gap-a/implementation_architecture.md"
    plan = workspace / "docs/plans/design-gaps/gap-a/execution_plan.md"
    run_state.parent.mkdir(parents=True, exist_ok=True)
    progress.parent.mkdir(parents=True, exist_ok=True)
    architecture.parent.mkdir(parents=True, exist_ok=True)
    progress.write_text("Status: BLOCKED\n", encoding="utf-8")
    architecture.write_text("# Gap A\n", encoding="utf-8")
    plan.write_text("# Plan A\n", encoding="utf-8")
    run_state.write_text(
        json.dumps(
            {
                "blocked_design_gaps": {
                    "gap-a": {
                        "reason": "implementation_blocked",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "recovery_event_id": "run:gap-a:blocked",
                        "progress_report_path": progress.relative_to(workspace).as_posix(),
                        "architecture_path": architecture.relative_to(workspace).as_posix(),
                        "plan_path": plan.relative_to(workspace).as_posix(),
                    }
                },
                "history": history,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return progress, architecture, plan


def _revision_cycle_history(cycles: int) -> list[dict]:
    history: list[dict] = [{"event": "blocked", "item_id": "gap-a", "reason": "implementation_blocked"}]
    for _ in range(cycles):
        history.append({"event": "gap_design_revision", "item_id": "gap-a"})
        history.append({"event": "blocked", "item_id": "gap-a", "reason": "implementation_blocked"})
    return history


def test_blocked_recovery_detector_reports_revision_cycles_to_classifier(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    output = workspace / "state/blocked-recovery.json"
    _write_blocked_gap_run_state(run_state, workspace, history=_revision_cycle_history(2))

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--architecture-index-root",
        "docs/plans/design-gaps",
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["revision_cycles"] == "2"


def test_blocked_recovery_detector_stops_after_exhausted_revision_cycles(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    output = workspace / "state/blocked-recovery.json"
    _write_blocked_gap_run_state(run_state, workspace, history=_revision_cycle_history(3))

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--architecture-index-root",
        "docs/plans/design-gaps",
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "BLOCKED"
    assert payload["block_reason"] == "local_recovery_exhausted"


def test_blocked_recovery_detector_ignores_unretried_revisions_in_cycle_count(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    output = workspace / "state/blocked-recovery.json"
    history = _revision_cycle_history(0)
    for _ in range(4):
        history.append({"event": "gap_design_revision", "item_id": "gap-a"})
        history.append({"event": "recovered_retry_unavailable", "item_id": "gap-a"})
    _write_blocked_gap_run_state(run_state, workspace, history=history)

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--architecture-index-root",
        "docs/plans/design-gaps",
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["revision_cycles"] == "0"


def test_blocked_recovery_detector_skips_unavailable_prerequisite_to_recover_other_gap(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    manifest = workspace / "state/selector-manifest.json"
    output = workspace / "state/blocked-recovery.json"
    progress = workspace / "artifacts/work/gap-b/progress_report.md"
    architecture = workspace / "docs/plans/design-gaps/gap-b/implementation_architecture.md"
    plan = workspace / "docs/plans/design-gaps/gap-b/execution_plan.md"
    run_state.parent.mkdir(parents=True)
    progress.parent.mkdir(parents=True)
    architecture.parent.mkdir(parents=True)
    progress.write_text("Status: BLOCKED\n", encoding="utf-8")
    architecture.write_text("# Gap B\n", encoding="utf-8")
    plan.write_text("# Plan B\n", encoding="utf-8")
    run_state.write_text(
        json.dumps(
            {
                "blocked_design_gaps": {
                    "gap-a": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "recovery_event_id": "run:gap-a:blocked",
                        "recovery_dependency_edge": _recovery_dependency_edge(
                            blocked="gap-a",
                            blocker="missing-gap",
                        ),
                    },
                    "gap-b": {
                        "reason": "implementation_blocked",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "recovery_event_id": "run:gap-b:blocked",
                        "progress_report_path": progress.relative_to(workspace).as_posix(),
                        "architecture_path": architecture.relative_to(workspace).as_posix(),
                        "plan_path": plan.relative_to(workspace).as_posix(),
                    },
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "diagnostic_mechanics_errors": [{"code": "missing_dependency_target"}],
                "blocking_mechanics_errors": [],
                "target_gap_discovery_allowed": True,
                "eligible_design_gaps": [],
                "eligible_items": [],
                "priority_recovery_work": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--architecture-index-root",
        "docs/plans/design-gaps",
        "--selector-manifest-path",
        manifest.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["design_gap_id"] == "gap-b"
    assert payload["recovery_route"] == "GAP_DESIGN_REVISION_REQUIRED"


def test_blocked_recovery_detector_suppresses_repeated_continue_with_current_plan_step_back(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    decision = workspace / "state/non-progress-decision.json"
    output = workspace / "state/blocked-recovery.json"
    run_state.parent.mkdir(parents=True)
    run_state.write_text(
        json.dumps(
            {
                "blocked_design_gaps": {},
                "blocked_items": {},
                "history": [
                    {
                        "event": "step_back",
                        "iteration": 1,
                        "action": "CONTINUE_WITH_CURRENT_PLAN",
                        "failure_fingerprint": "same-work",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision.write_text(
        json.dumps(
            {
                "route": "STEP_BACK_REQUIRED",
                "trigger_codes": ["same_work_item_repeatedly_blocked"],
                "failure_fingerprint": "same-work",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--architecture-index-root",
        "docs/plans/design-gaps",
        "--non-progress-decision-path",
        decision.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["recovery_status"] != "STEP_BACK_REQUIRED"
    assert payload["pre_selection_route"] == "SELECT_NORMAL_WORK"


def test_blocked_recovery_detector_still_step_backs_on_different_fingerprint(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    decision = workspace / "state/non-progress-decision.json"
    output = workspace / "state/blocked-recovery.json"
    run_state.parent.mkdir(parents=True)
    run_state.write_text(
        json.dumps(
            {
                "blocked_design_gaps": {},
                "blocked_items": {},
                "history": [
                    {
                        "event": "step_back",
                        "iteration": 1,
                        "action": "CONTINUE_WITH_CURRENT_PLAN",
                        "failure_fingerprint": "same-work",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision.write_text(
        json.dumps(
            {
                "route": "STEP_BACK_REQUIRED",
                "trigger_codes": ["same_work_item_repeatedly_blocked"],
                "failure_fingerprint": "different-work",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--architecture-index-root",
        "docs/plans/design-gaps",
        "--non-progress-decision-path",
        decision.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "BLOCKED"
    assert payload["recovery_status"] == "STEP_BACK_REQUIRED"
    assert payload["block_reason"] == "different-work"


def test_blocked_recovery_detector_blocks_on_manifest_mechanics_error(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    selector_manifest = workspace / "state/selector-manifest.json"
    output = workspace / "state/blocked-recovery.json"
    run_state.parent.mkdir(parents=True)
    run_state.write_text(json.dumps({"blocked_design_gaps": {}, "blocked_items": {}}) + "\n", encoding="utf-8")
    selector_manifest.write_text(
        json.dumps(
            {
                "blocking_mechanics_errors": [
                    {"code": "missing_dependency_target", "reason": "missing_dependency_target"}
                ],
                "diagnostic_mechanics_errors": [],
                "target_gap_discovery_allowed": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--selector-manifest-path",
        selector_manifest.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "BLOCKED"
    assert payload["recovery_route"] == "TERMINAL_BLOCKED"
    assert payload["recovery_reason"] == "missing_dependency_target"
    assert payload["block_reason"] == "missing_dependency_target"


def test_blocked_recovery_detector_allows_diagnostic_mechanics_for_discovery(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    selector_manifest = workspace / "state/selector-manifest.json"
    output = workspace / "state/blocked-recovery.json"
    run_state.parent.mkdir(parents=True)
    run_state.write_text(json.dumps({"blocked_design_gaps": {}, "blocked_items": {}}) + "\n", encoding="utf-8")
    selector_manifest.write_text(
        json.dumps(
            {
                "blocking_mechanics_errors": [],
                "diagnostic_mechanics_errors": [
                    {"code": "missing_dependency_target", "reason": "missing_dependency_target"}
                ],
                "target_gap_discovery_allowed": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--selector-manifest-path",
        selector_manifest.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "SELECT_NORMAL_WORK"
    assert payload["recovery_route"] == "NOT_APPLICABLE"


def test_blocked_recovery_detector_routes_empty_manifest_to_done_review(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    selector_manifest = workspace / "state/selector-manifest.json"
    output = workspace / "state/blocked-recovery.json"
    run_state.parent.mkdir(parents=True)
    run_state.write_text(json.dumps({"blocked_design_gaps": {}, "blocked_items": {}}) + "\n", encoding="utf-8")
    selector_manifest.write_text(
        json.dumps(
            {
                "items": [],
                "design_gaps": [],
                "eligible_items": [],
                "eligible_design_gaps": [],
                "priority_recovery_work": [],
                "blocking_mechanics_errors": [],
                "hidden_summary": {"blocked_by_dependencies": 0, "invalid_dependencies": 0},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--selector-manifest-path",
        selector_manifest.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "SELECT_DONE_REVIEW"
    assert payload["recovery_reason"] == "no_selectable_manifest_work"
    assert payload["recovery_status"] == "DONE_REVIEW_REQUIRED"


def test_blocked_recovery_detector_skips_hidden_prerequisite_from_diagnostic_manifest(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    selector_manifest = workspace / "state/selector-manifest.json"
    output = workspace / "state/blocked-recovery.json"
    run_state.parent.mkdir(parents=True)
    run_state.write_text(
        json.dumps(
            {
                "completed_design_gaps": [],
                "completed_items": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "a": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "recovery_event_id": "run:a",
                        "recovery_dependency_edge": _recovery_dependency_edge(blocked="a", blocker="b"),
                    },
                    "b": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "recovery_event_id": "run:b",
                        "recovery_dependency_edge": _recovery_dependency_edge(blocked="b", blocker="missing-c"),
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selector_manifest.write_text(
        json.dumps(
            {
                "eligible_design_gaps": [{"design_gap_id": "x", "status": "available"}],
                "priority_recovery_work": [],
                "hidden_work": [
                    {"source": "DESIGN_GAP", "id": "a", "reason": "waiting_on_incomplete_dependency"},
                    {"source": "DESIGN_GAP", "id": "b", "reason": "missing_dependency_target"},
                ],
                "blocking_mechanics_errors": [],
                "diagnostic_mechanics_errors": [
                    {"code": "missing_dependency_target", "reason": "missing_dependency_target"}
                ],
                "target_gap_discovery_allowed": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--selector-manifest-path",
        selector_manifest.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "SELECT_NORMAL_WORK"
    assert payload["recovery_route"] == "NOT_APPLICABLE"


def test_prerequisite_selection_requires_eligible_design_gap(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    pre_selection = workspace / "state/pre-selection.json"
    manifest = workspace / "state/selector-manifest.json"
    output = workspace / "state/selection.json"
    pre_selection.parent.mkdir(parents=True)
    pre_selection.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "recovery_pointer_status": "WAITING",
                "waiting_on_work_source": "DESIGN_GAP",
                "waiting_on_work_id": "b",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "design_gaps": [{"design_gap_id": "b", "title": "B", "status": "available"}],
                "eligible_design_gaps": [{"design_gap_id": "b", "title": "B", "status": "available"}],
                "priority_recovery_work": [{"source": "DESIGN_GAP", "id": "b", "status": "available"}],
                "hidden_work": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/write_lisp_frontend_prerequisite_selection.py"),
        "--pre-selection-path",
        pre_selection.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest.relative_to(workspace).as_posix(),
        "--target-design-path",
        "docs/design/workflow_lisp_runtime_native_drain_authoring.md",
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["selection_status"] == "DRAFT_DESIGN_GAP"
    assert payload["design_gap_id"] == "b"


def test_selection_bundle_publish_requires_eligible_design_gap_when_manifest_has_work(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_root = workspace / "state"
    state_root.mkdir()
    selection = state_root / "selection.json"
    manifest = state_root / "selector-manifest.json"
    output = state_root / "selection-bundle-path.json"
    selection.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "stale-hidden-gap",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "eligible_design_gaps": [{"design_gap_id": "current-gap", "status": "available"}],
                "eligible_items": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/publish_lisp_frontend_selection_bundle.py"),
        "--selection-path",
        selection.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
        check=False,
    )

    assert result.returncode != 0
    assert "design_gap_id is not eligible: stale-hidden-gap" in result.stderr
    assert not output.exists()


def test_selection_bundle_publish_accepts_eligible_design_gap(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_root = workspace / "state"
    state_root.mkdir()
    selection = state_root / "selection.json"
    manifest = state_root / "selector-manifest.json"
    output = state_root / "selection-bundle-path.json"
    selection.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "current-gap",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "eligible_design_gaps": [
                    {
                        "design_gap_id": "current-gap",
                        "status": "available",
                        "architecture_path": (
                            "docs/plans/DRAIN/design-gaps/current-gap/"
                            "implementation_architecture.md"
                        ),
                        "plan_path": (
                            "docs/plans/DRAIN/design-gaps/current-gap/"
                            "execution_plan.md"
                        ),
                    }
                ],
                "eligible_items": [],
                "attempt_history_summary": {
                    "completed_design_gap_ids": ["done-gap"],
                    "blocked_design_gaps": [
                        {
                            "design_gap_id": "old-gap",
                            "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                            "progress_report_path": "artifacts/work/old-gap/progress_report.md",
                        }
                    ],
                    "last_blocked_design_gap": {
                        "design_gap_id": "old-gap",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "progress_report_path": "artifacts/work/old-gap/progress_report.md",
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/publish_lisp_frontend_selection_bundle.py"),
        "--selection-path",
        selection.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["selection_bundle_path"] == "state/selection.json"
    selection_payload = json.loads(selection.read_text(encoding="utf-8"))
    assert selection_payload["selected_design_gap"] == {
        "design_gap_id": "current-gap",
        "status": "available",
        "architecture_path": "docs/plans/DRAIN/design-gaps/current-gap/implementation_architecture.md",
        "plan_path": "docs/plans/DRAIN/design-gaps/current-gap/execution_plan.md",
    }
    assert selection_payload["attempt_history_summary"]["completed_design_gap_ids"] == ["done-gap"]
    assert (
        selection_payload["attempt_history_summary"]["last_blocked_design_gap"]["progress_report_path"]
        == "artifacts/work/old-gap/progress_report.md"
    )


def test_selection_bundle_publish_allows_new_gap_discovery_when_no_eligible_work(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_root = workspace / "state"
    state_root.mkdir()
    selection = state_root / "selection.json"
    manifest = state_root / "selector-manifest.json"
    output = state_root / "selection-bundle-path.json"
    selection.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "new-target-gap",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps({"eligible_design_gaps": [], "eligible_items": []}) + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/publish_lisp_frontend_selection_bundle.py"),
        "--selection-path",
        selection.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["selection_bundle_path"] == "state/selection.json"


def test_prerequisite_selection_blocks_hidden_design_gap(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    pre_selection = workspace / "state/pre-selection.json"
    manifest = workspace / "state/selector-manifest.json"
    output = workspace / "state/selection.json"
    pre_selection.parent.mkdir(parents=True)
    pre_selection.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "recovery_pointer_status": "WAITING",
                "waiting_on_work_source": "DESIGN_GAP",
                "waiting_on_work_id": "b",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "design_gaps": [],
                "eligible_design_gaps": [],
                "priority_recovery_work": [],
                "hidden_work": [{"source": "DESIGN_GAP", "id": "b", "reason": "waiting_on_incomplete_dependency"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/write_lisp_frontend_prerequisite_selection.py"),
        "--pre-selection-path",
        pre_selection.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest.relative_to(workspace).as_posix(),
        "--target-design-path",
        "docs/design/workflow_lisp_runtime_native_drain_authoring.md",
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["selection_status"] == "BLOCKED"
    assert payload["blocking_reasons"] == ["ineligible_prerequisite_work: DESIGN_GAP b"]


def test_prerequisite_selection_blocks_missing_design_gap(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    pre_selection = workspace / "state/pre-selection.json"
    manifest = workspace / "state/selector-manifest.json"
    output = workspace / "state/selection.json"
    pre_selection.parent.mkdir(parents=True)
    pre_selection.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "recovery_pointer_status": "WAITING",
                "waiting_on_work_source": "DESIGN_GAP",
                "waiting_on_work_id": "missing-c",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "design_gaps": [],
                "eligible_design_gaps": [],
                "priority_recovery_work": [],
                "hidden_work": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/write_lisp_frontend_prerequisite_selection.py"),
        "--pre-selection-path",
        pre_selection.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest.relative_to(workspace).as_posix(),
        "--target-design-path",
        "docs/design/workflow_lisp_runtime_native_drain_authoring.md",
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["selection_status"] == "BLOCKED"
    assert payload["blocking_reasons"] == ["missing_dependency_target: DESIGN_GAP missing-c"]


def test_prerequisite_selection_drafts_missing_proposed_design_gap(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    pre_selection = workspace / "state/pre-selection.json"
    manifest = workspace / "state/selector-manifest.json"
    output = workspace / "state/selection.json"
    pre_selection.parent.mkdir(parents=True)
    pre_selection.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "recovery_pointer_status": "WAITING",
                "waiting_on_work_source": "DESIGN_GAP",
                "waiting_on_work_id": "child-union-provenance",
                "proposed_prerequisite_id": "child-union-provenance",
                "proposed_prerequisite_source": "DESIGN_GAP",
                "proposed_prerequisite_title": "Child workflow union provenance",
                "proposed_prerequisite_scope": (
                    "Specify the compiler contract for child workflow union results."
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "design_gaps": [],
                "eligible_design_gaps": [],
                "priority_recovery_work": [],
                "hidden_work": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/write_lisp_frontend_prerequisite_selection.py"),
        "--pre-selection-path",
        pre_selection.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest.relative_to(workspace).as_posix(),
        "--target-design-path",
        "docs/design/workflow_lisp_runtime_native_drain_authoring.md",
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["selection_status"] == "DRAFT_DESIGN_GAP"
    assert payload["design_gap_id"] == "child-union-provenance"
    assert payload["missing_component"] == "Child workflow union provenance"
    assert payload["proposed_scope"] == "Specify the compiler contract for child workflow union results."


def test_blocked_recovery_detector_carries_proposed_prerequisite_metadata(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_state = workspace / "state/run_state.json"
    output = workspace / "state/blocked-recovery.json"
    run_state.parent.mkdir(parents=True)
    run_state.write_text(
        json.dumps(
            {
                "completed_design_gaps": [],
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "recovery_event_id": "parser-syntax-blocked",
                        "prerequisite_gap_hint": (
                            "Child workflow union provenance - Specify the compiler contract."
                        ),
                        "recovery_dependency_edge": {
                            **_recovery_dependency_edge(
                                blocked="parser-syntax",
                                blocker="child-union-provenance",
                                reason_code="prerequisite_gap_required",
                            ),
                            "evidence": {
                                "proposed_prerequisite": {
                                    "id": "child-union-provenance",
                                    "source": "DESIGN_GAP",
                                    "title": "Child workflow union provenance",
                                    "scope": "Specify the compiler contract.",
                                    "reason": "parent match cannot consume child union result",
                                }
                            },
                        },
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        run_state.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work",
        "--architecture-index-root",
        "docs/plans/design-gaps",
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "SELECT_PREREQUISITE_WORK"
    assert payload["waiting_on_work_id"] == "child-union-provenance"
    assert payload["proposed_prerequisite_id"] == "child-union-provenance"
    assert payload["proposed_prerequisite_scope"] == "Specify the compiler contract."


def test_selector_manifest_hides_blocked_dependent_and_filters_counts(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest_path = workspace / "state/drain/manifest.json"
    run_state_path = workspace / "state/drain/run_state.json"
    output_path = workspace / "state/drain/selector-manifest.json"
    control_path = workspace / "state/drain/selector-control-manifest.json"
    gap_root = workspace / "docs/plans/DRAIN/design-gaps"
    for gap_id in ("a", "b"):
        _write_selector_manifest_gap_architecture(workspace, gap_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"items": [], "backlog_root": "docs/backlog/active"}) + "\n", encoding="utf-8")
    run_state_path.write_text(
        json.dumps(
            {
                "completed_design_gaps": [],
                "completed_items": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "a": {
                        "reason": "implementation_blocked",
                        "recovery_dependency_edge": _recovery_dependency_edge(blocked="a", blocker="b"),
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/project_lisp_frontend_selector_manifest.py"),
        "--manifest-path",
        manifest_path.relative_to(workspace).as_posix(),
        "--architecture-index-root",
        gap_root.relative_to(workspace).as_posix(),
        "--run-state-path",
        run_state_path.relative_to(workspace).as_posix(),
        "--control-output",
        control_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    control = json.loads(control_path.read_text(encoding="utf-8"))
    assert [gap["design_gap_id"] for gap in payload["eligible_design_gaps"]] == ["b"]
    assert payload["eligible_design_gaps"][0]["architecture_path"].endswith(
        "docs/plans/DRAIN/design-gaps/b/implementation_architecture.md"
    )
    assert payload["eligible_design_gaps"][0]["plan_path"].endswith(
        "docs/plans/DRAIN/design-gaps/b/execution_plan.md"
    )
    assert [gap["design_gap_id"] for gap in payload["design_gaps"]] == ["b"]
    assert payload["design_gap_count"] == 1
    assert payload["all_design_gap_count_diagnostic"] == 2
    assert payload["priority_recovery_work"] == [{"source": "DESIGN_GAP", "id": "b", "status": "available"}]
    assert payload["attempt_history_summary"]["blocked_design_gaps"][0]["design_gap_id"] == "a"
    assert payload["attempt_history_summary"]["blocked_design_gaps"][0]["architecture_path"].endswith(
        "docs/plans/DRAIN/design-gaps/a/implementation_architecture.md"
    )
    assert payload["attempt_history_summary"]["blocked_design_gaps"][0]["plan_path"].endswith(
        "docs/plans/DRAIN/design-gaps/a/execution_plan.md"
    )
    assert payload["hidden_summary"]["blocked_by_dependencies"] == 1
    assert "hidden_work" not in payload
    assert "blocking_mechanics_errors" not in payload
    assert "diagnostic_mechanics_errors" not in payload
    assert "target_gap_discovery_allowed" not in payload
    assert control["hidden_work"][0]["id"] == "a"
    assert control["hidden_work"][0]["waiting_on"] == {"source": "DESIGN_GAP", "id": "b"}
    assert control["blocking_mechanics_errors"] == []
    assert control["diagnostic_mechanics_errors"] == []


def test_selector_manifest_keeps_new_gap_discovery_available_for_missing_prerequisite(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest_path = workspace / "state/drain/manifest.json"
    run_state_path = workspace / "state/drain/run_state.json"
    output_path = workspace / "state/drain/selector-manifest.json"
    control_path = workspace / "state/drain/selector-control-manifest.json"
    gap_root = workspace / "docs/plans/DRAIN/design-gaps"
    for gap_id in ("a", "b"):
        _write_selector_manifest_gap_architecture(workspace, gap_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"items": [], "backlog_root": "docs/backlog/active"}) + "\n", encoding="utf-8")
    run_state_path.write_text(
        json.dumps(
            {
                "completed_design_gaps": [],
                "completed_items": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "a": {
                        "reason": "implementation_blocked",
                        "recovery_dependency_edge": _recovery_dependency_edge(blocked="a", blocker="b"),
                    },
                    "b": {
                        "reason": "implementation_blocked",
                        "recovery_dependency_edge": _recovery_dependency_edge(blocked="b", blocker="missing-c"),
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/project_lisp_frontend_selector_manifest.py"),
        "--manifest-path",
        manifest_path.relative_to(workspace).as_posix(),
        "--architecture-index-root",
        gap_root.relative_to(workspace).as_posix(),
        "--run-state-path",
        run_state_path.relative_to(workspace).as_posix(),
        "--control-output",
        control_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    control = json.loads(control_path.read_text(encoding="utf-8"))
    assert "target_gap_discovery_allowed" not in payload
    assert payload["eligible_design_gaps"] == []
    assert payload["design_gaps"] == []
    assert payload["design_gap_count"] == 0
    assert payload["priority_recovery_work"] == []
    assert "hidden_work" not in payload
    assert "blocking_mechanics_errors" not in payload
    assert "diagnostic_mechanics_errors" not in payload
    assert "missing-c" not in json.dumps(payload)
    assert control["target_gap_discovery_allowed"] is True
    assert {item["id"] for item in control["hidden_work"]} == {"a", "b"}
    assert control["blocking_mechanics_errors"] == []
    assert control["diagnostic_mechanics_errors"][0]["code"] == "missing_dependency_target"


def test_selector_manifest_blocks_missing_prerequisite_when_discovery_disabled(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest_path = workspace / "state/drain/manifest.json"
    run_state_path = workspace / "state/drain/run_state.json"
    output_path = workspace / "state/drain/selector-manifest.json"
    control_path = workspace / "state/drain/selector-control-manifest.json"
    gap_root = workspace / "docs/plans/DRAIN/design-gaps"
    _write_selector_manifest_gap_architecture(workspace, "a")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"items": [], "backlog_root": "docs/backlog/active"}) + "\n", encoding="utf-8")
    run_state_path.write_text(
        json.dumps(
            {
                "completed_design_gaps": [],
                "completed_items": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "a": {
                        "reason": "implementation_blocked",
                        "recovery_dependency_edge": _recovery_dependency_edge(blocked="a", blocker="missing-c"),
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/project_lisp_frontend_selector_manifest.py"),
        "--manifest-path",
        manifest_path.relative_to(workspace).as_posix(),
        "--architecture-index-root",
        gap_root.relative_to(workspace).as_posix(),
        "--run-state-path",
        run_state_path.relative_to(workspace).as_posix(),
        "--target-gap-discovery-allowed",
        "false",
        "--control-output",
        control_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    control = json.loads(control_path.read_text(encoding="utf-8"))
    assert "target_gap_discovery_allowed" not in payload
    assert payload["design_gaps"] == []
    assert "blocking_mechanics_errors" not in payload
    assert "diagnostic_mechanics_errors" not in payload
    assert "missing-c" not in json.dumps(payload)
    assert control["target_gap_discovery_allowed"] is False
    assert control["blocking_mechanics_errors"][0]["code"] == "missing_dependency_target"
    assert control["diagnostic_mechanics_errors"] == []


def test_recovered_design_gap_materializer_ignores_stale_prior_bundle_paths(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    recovery_path = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/blocked-recovery.json"
    stale_bundle_path = (
        workspace
        / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/architecture-validation.json"
    )
    stale_context_path = (
        workspace
        / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/work_item_context.md"
    )
    stale_checks_path = (
        workspace
        / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json"
    )
    output_path = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/recovered-gap/draft-architecture.json"
    architecture_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    stale_bundle_path.parent.mkdir(parents=True, exist_ok=True)
    architecture_path.write_text("# Parser Syntax Architecture\n", encoding="utf-8")
    plan_path.write_text("# Parser Syntax Execution Plan\n", encoding="utf-8")
    recovery_path.write_text(
        json.dumps(
            {
                "pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "RETRY_READY",
                "recovery_event_id": "old-run:parser-syntax:implementation-blocked",
                "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                "plan_path": plan_path.relative_to(workspace).as_posix(),
                "progress_report_path": "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/parser-syntax/progress_report.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stale_context_path.write_text("# Stale prior context\n", encoding="utf-8")
    stale_checks_path.write_text(json.dumps(["python -m pytest stale_selector"]) + "\n", encoding="utf-8")
    stale_bundle_path.write_text(
        json.dumps(
            {
                "architecture_validation_status": "VALID",
                "work_item_source": "DESIGN_GAP",
                "work_item_id": "parser-syntax",
                "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                "work_item_context_path": (
                    "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/"
                    "design-gap-architect/work_item_context.md"
                ),
                "check_commands_path": (
                    "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/"
                    "design-gap-architect/check_commands.json"
                ),
                "plan_target_path": plan_path.relative_to(workspace).as_posix(),
                "work_item_bundle_path": stale_bundle_path.relative_to(workspace).as_posix(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/materialize_lisp_frontend_recovered_design_gap_draft.py"),
        "--recovery-bundle-path",
        recovery_path.relative_to(workspace).as_posix(),
        "--drain-state-root",
        "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["work_item_context_path"].endswith("/recovered-gap/recovered-work-item-context.md")
    assert payload["check_commands_path"].endswith("/recovered-gap/recovered-check-commands.json")
    assert payload["work_item_context_path"] != stale_context_path.relative_to(workspace).as_posix()
    assert payload["check_commands_path"] != stale_checks_path.relative_to(workspace).as_posix()
    context = (workspace / payload["work_item_context_path"]).read_text(encoding="utf-8")
    assert "Do not copy their generated `state/...` paths into durable design or plan documents." in context
    assert "stale_selector" not in (workspace / payload["check_commands_path"]).read_text(encoding="utf-8")


def test_architecture_validator_rejects_stale_draft_for_current_target(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    stale_architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/old-gap/implementation_architecture.md"
    target_architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/new-gap/implementation_architecture.md"
    context_path = workspace / "state/gap/work_item_context.md"
    checks_path = workspace / "state/gap/check_commands.json"
    stale_plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/old-gap/execution_plan.md"
    target_plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/new-gap/execution_plan.md"
    stale_architecture_path.parent.mkdir(parents=True, exist_ok=True)
    target_architecture_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    stale_architecture_path.write_text("# Old Gap Architecture\n", encoding="utf-8")
    target_architecture_path.write_text("# New Gap Architecture\n", encoding="utf-8")
    context_path.write_text("# Gap Work Item\n", encoding="utf-8")
    checks_path.write_text(json.dumps(["python -c \"print('gap-check')\""]) + "\n", encoding="utf-8")
    draft_path = workspace / "state/gap/draft-bundle.json"
    draft_path.write_text(
        json.dumps(
            {
                "draft_status": "DRAFTED",
                "design_gap_id": "old-gap",
                "architecture_path": stale_architecture_path.relative_to(workspace).as_posix(),
                "work_item_context_path": context_path.relative_to(workspace).as_posix(),
                "check_commands_path": checks_path.relative_to(workspace).as_posix(),
                "plan_target_path": stale_plan_path.relative_to(workspace).as_posix(),
                "summary": "Stale gap architecture.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    targets_path = workspace / "state/gap/architecture-targets.json"
    targets_path.write_text(
        json.dumps(
            {
                "design_gap_id": "new-gap",
                "architecture_path": target_architecture_path.relative_to(workspace).as_posix(),
                "work_item_context_path": context_path.relative_to(workspace).as_posix(),
                "check_commands_path": checks_path.relative_to(workspace).as_posix(),
                "plan_target_path": target_plan_path.relative_to(workspace).as_posix(),
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
        "--architecture-targets-path",
        targets_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["architecture_validation_status"] == "INVALID"
    assert "does not match current architecture target" in payload["reason"]


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

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["terminal_route"] == "IMPLEMENTATION_BLOCKED"
    assert payload["block_reason"] == "implementation_blocked"
    assert payload["implementation_blocked"] is True
    assert payload["plan_review_exhausted"] is False
    assert payload["implementation_review_exhausted"] is False


def test_blocked_recovery_user_decision_with_repo_scope_evidence_is_recoverable(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bundle_path = workspace / "state/blocked-implementation-recovery.json"
    output_path = workspace / "state/blocked-recovery-route.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "TERMINAL_BLOCKED",
                "reason": "user_decision_required",
                "summary": (
                    "The selected gap is mostly implemented, but verification exposed "
                    "repo-local adapter and contract/import-boundary failures outside "
                    "the approved implementation slice."
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py"),
        "--terminal-route",
        "IMPLEMENTATION_BLOCKED",
        "--work-item-source",
        "DESIGN_GAP",
        "--classifier-bundle-path",
        bundle_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "blocked_recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
        "reason": "implementation_architecture_under_scoped",
    }


def test_blocked_recovery_explicit_external_user_decision_stays_terminal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bundle_path = workspace / "state/blocked-implementation-recovery.json"
    output_path = workspace / "state/blocked-recovery-route.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "TERMINAL_BLOCKED",
                "reason": "user_decision_required",
                "summary": (
                    "The blocker requires external human authority and cannot be "
                    "represented as a design change."
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py"),
        "--terminal-route",
        "IMPLEMENTATION_BLOCKED",
        "--work-item-source",
        "DESIGN_GAP",
        "--classifier-bundle-path",
        bundle_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "blocked_recovery_route": "TERMINAL_BLOCKED",
        "reason": "user_decision_required",
    }


def test_blocked_recovery_environment_user_intervention_stays_terminal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bundle_path = workspace / "state/blocked-implementation-recovery.json"
    output_path = workspace / "state/blocked-recovery-route.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "TERMINAL_BLOCKED",
                "reason": "user_decision_required",
                "summary": (
                    "User input required: the workflow cannot continue because a "
                    "credential and local setup environment issue requires user intervention."
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py"),
        "--terminal-route",
        "IMPLEMENTATION_BLOCKED",
        "--work-item-source",
        "DESIGN_GAP",
        "--classifier-bundle-path",
        bundle_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "blocked_recovery_route": "TERMINAL_BLOCKED",
        "reason": "user_decision_required",
    }


def test_blocked_recovery_target_design_ambiguity_stays_terminal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bundle_path = workspace / "state/blocked-implementation-recovery.json"
    output_path = workspace / "state/blocked-recovery-route.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "TERMINAL_BLOCKED",
                "reason": "user_decision_required",
                "summary": (
                    "Human decision required: there is a major unresolvable ambiguity "
                    "in intention that cannot be resolved by target design revision."
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py"),
        "--terminal-route",
        "IMPLEMENTATION_BLOCKED",
        "--work-item-source",
        "DESIGN_GAP",
        "--classifier-bundle-path",
        bundle_path.relative_to(workspace).as_posix(),
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "blocked_recovery_route": "TERMINAL_BLOCKED",
        "reason": "user_decision_required",
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


def test_update_run_state_design_revision_keeps_blocked_gap_until_retry_completes(tmp_path):
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
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "timestamp_utc": "2026-06-01T00:00:00Z",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
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
    assert "parser-syntax" in state["blocked_design_gaps"]


def test_update_run_state_complete_clears_blocked_gap_after_retry(tmp_path):
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
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "timestamp_utc": "2026-06-01T00:00:00Z",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
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
        "complete",
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "parser-syntax" in state["completed_design_gaps"]
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
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    assert pointer_path.read_text(encoding="utf-8").strip() == summary_path.relative_to(workspace).as_posix()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["item_status"] == "GAP_DESIGN_REVISED"


def test_update_run_state_records_blocked_recovery_metadata(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/run_state.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/update_lisp_frontend_run_state.py"),
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "blocked",
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--reason",
        "implementation_blocked",
        "--recovery-route",
        "GAP_DESIGN_REVISION_REQUIRED",
        "--recovery-reason",
        "implementation_architecture_under_scoped",
        "--progress-report-path",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md",
        "--implementation-state-path",
        "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-work-item/implementation-phase/implementation_state.json",
        "--architecture-path",
        "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md",
        "--plan-path",
        "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md",
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--recovery-status",
        "PREREQUISITE_WORK_PENDING",
        "--prerequisite-selection-bundle-path",
        "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/prerequisite-selector/selection.json",
        "--waiting-on-prerequisite-gap-id",
        "generic-context-capability",
        "--prerequisite-recovery-status",
        "SELECTED",
        "--original-blocked-gap-id",
        "parser-syntax",
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["reason"] == "implementation_blocked"
    assert blocked["recovery_route"] == "GAP_DESIGN_REVISION_REQUIRED"
    assert blocked["recovery_reason"] == "implementation_architecture_under_scoped"
    assert blocked["progress_report_path"].endswith("/progress_report.md")
    assert blocked["implementation_state_path"].endswith("/implementation_state.json")
    assert blocked["architecture_path"].endswith("/implementation_architecture.md")
    assert blocked["plan_path"].endswith("/execution_plan.md")
    assert blocked["recovery_event_id"] == "parser-syntax-implementation-blocked"
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["prerequisite_selection_bundle_path"].endswith("/prerequisite-selector/selection.json")
    assert blocked["waiting_on_prerequisite_gap_id"] == "generic-context-capability"
    assert blocked["prerequisite_recovery_status"] == "SELECTED"
    assert blocked["original_blocked_gap_id"] == "parser-syntax"
    assert state["history"][-1]["event"] == "blocked"
    assert state["history"][-1]["recovery_route"] == "GAP_DESIGN_REVISION_REQUIRED"
    assert state["history"][-1]["waiting_on_prerequisite_gap_id"] == "generic-context-capability"


def test_record_blocked_recovery_outcome_hands_off_to_detector(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_bundle.parent.mkdir(parents=True, exist_ok=True)
    recovery_bundle.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                "reason": "implementation_architecture_under_scoped",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for path, text in [
        (progress_path, "# Progress Report\n\nThe architecture is under-scoped.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["reason"] == "implementation_blocked"
    assert blocked["recovery_reason"] == "implementation_architecture_under_scoped"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )
    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["design_gap_id"] == "parser-syntax"
    assert payload["recovery_route"] == "GAP_DESIGN_REVISION_REQUIRED"
    assert payload["recovery_reason"] == "implementation_architecture_under_scoped"
    assert payload["recovery_event_id"] == "parser-syntax-implementation-blocked"


def test_prerequisite_block_recovery_stays_nonterminal_until_target_revision(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_bundle.parent.mkdir(parents=True, exist_ok=True)
    recovery_bundle.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "reason": "prerequisite_gap_required",
                "waiting_on_prerequisite_gap_id": (
                    "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters"
                ),
                "waiting_on_prerequisite_source": "DESIGN_GAP",
                "prerequisite_recovery_status": "WAITING_ON_BOOTSTRAP_REACHABILITY",
                "prerequisite_recovery_reason": "bootstrap_reachability_missing",
                "downstream_blocked_gap_id": (
                    "workflow-lisp-runtime-native-drain-work-item-summary-ownership-over-imported-finalize-selected-item"
                ),
                "blocking_failure_code": "private_exec_context_bootstrap_unsupported",
                "retry_condition": (
                    "imported stdlib-adapter selector path reaches imported finalizer branches "
                    "without private_exec_context_bootstrap_unsupported"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for path, text in [
        (progress_path, "# Progress Report\n\nThe missing prerequisite gap must be added to the target design.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["reason"] == "implementation_blocked"
    assert blocked["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert blocked["recovery_reason"] == "prerequisite_gap_required"
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )
    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "SELECT_PREREQUISITE_WORK"
    assert payload["design_gap_id"] == "parser-syntax"
    assert payload["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"


def test_blocked_recovery_recorder_does_not_persist_completed_prerequisite(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    for path, text in [
        (state_path, json.dumps({
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": ["generic-context-capability"],
            "blocked_items": {},
            "blocked_design_gaps": {},
            "history": [],
        }) + "\n"),
        (recovery_bundle, json.dumps({
            "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
            "reason": "prerequisite_gap_required",
            "recovery_dependency_edge": _recovery_dependency_edge(
                blocked="parser-syntax",
                blocker="generic-context-capability",
            ),
        }) + "\n"),
        (progress_path, "# Progress Report\n\nA stale prerequisite was selected.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert blocked["recovery_status"] == "RETRY_READY"
    assert blocked["prerequisite_recovery_status"] == "COMPLETED"
    assert blocked["recovery_dependency_edge"]["status"] == "ready_to_retry"
    assert state["history"][-1]["event"] == "prerequisite_recovery_satisfied"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RETRY_READY"
    assert summary["reason"] == "prerequisite_completed"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"


def test_blocked_recovery_recorder_does_not_reuse_completed_prerequisite_after_failed_retry(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report_retry.md"
    implementation_state_path = workspace / "state/drain/iterations/1/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    edge = _recovery_dependency_edge(
        blocked="parser-syntax",
        blocker="generic-context-capability",
    )
    for path, text in [
        (state_path, json.dumps({
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": ["generic-context-capability"],
            "blocked_items": {},
            "blocked_design_gaps": {
                "parser-syntax": {
                    "reason": "implementation_blocked",
                    "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                    "recovery_reason": "prerequisite_gap_required",
                    "recovery_status": "RETRY_READY",
                    "waiting_on_prerequisite_gap_id": "generic-context-capability",
                    "waiting_on_prerequisite_source": "DESIGN_GAP",
                    "prerequisite_recovery_status": "COMPLETED",
                    "prerequisite_recovery_reason": "prerequisite_completed",
                    "progress_report_path": "artifacts/work/old-progress.md",
                    "recovery_event_id": "parser-syntax-old-blocked",
                    "recovery_dependency_edge": {**edge, "status": "ready_to_retry"},
                }
            },
            "history": [],
        }) + "\n"),
        (recovery_bundle, json.dumps({
            "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
            "reason": "prerequisite_gap_required",
            "recovery_dependency_edge": edge,
        }) + "\n"),
        (progress_path, "# Progress Report\n\nThe retry still fails after the prerequisite.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-new-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert blocked["recovery_status"] == "PREREQUISITE_RETRY_FAILED"
    assert blocked["prerequisite_recovery_status"] == "RETRY_FAILED"
    assert blocked["prerequisite_recovery_reason"] == "completed_prerequisite_retry_failed"
    assert blocked["recovery_dependency_edge"]["status"] == "blocked"
    assert blocked["recovery_dependency_edge"]["reason"] == "retry_failed_after_completed_prerequisite"
    assert state["history"][-1]["event"] == "blocked"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["item_status"] == "BLOCKED"
    assert summary["reason"] == "implementation_blocked"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )
    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["design_gap_id"] == "parser-syntax"
    assert payload["recovery_status"] == "PREREQUISITE_RETRY_FAILED"
    assert payload["waiting_on_work_id"] == ""
    assert payload["retry_target_id"] == ""
    assert payload["recovery_pointer_status"] == ""


def test_blocked_recovery_detector_prioritizes_blocked_prerequisite_recovery(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    dependent_gap_id = "aaa-runtime-audit"
    blocker_gap_id = "zzz-parent-compile-smoke"
    completed_gap_id = "completed-reference-family"
    dependent_edge = _recovery_dependency_edge(blocked=dependent_gap_id, blocker=blocker_gap_id)
    blocker_edge = _recovery_dependency_edge(blocked=blocker_gap_id, blocker=completed_gap_id)
    blocker_progress_path = (
        workspace
        / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/"
        f"{blocker_gap_id}/"
        "progress_report.md"
    )
    blocker_architecture_path = (
        workspace
        / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/"
        f"{blocker_gap_id}/"
        "implementation_architecture.md"
    )
    blocker_plan_path = (
        workspace
        / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/"
        f"{blocker_gap_id}/"
        "execution_plan.md"
    )

    for path, text in [
        (state_path, json.dumps({
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": [completed_gap_id],
            "blocked_items": {},
            "blocked_design_gaps": {
                dependent_gap_id: {
                    "reason": "implementation_blocked",
                    "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                    "recovery_reason": "prerequisite_gap_required",
                    "recovery_status": "PREREQUISITE_WORK_PENDING",
                    "waiting_on_prerequisite_gap_id": blocker_gap_id,
                    "waiting_on_prerequisite_source": "DESIGN_GAP",
                    "prerequisite_recovery_status": "BLOCKED_RECOVERABLE",
                    "prerequisite_recovery_reason": "blocker_recoverable",
                    "recovery_event_id": "dependent-blocked",
                    "recovery_dependency_edge": {**dependent_edge, "status": "blocked"},
                },
                blocker_gap_id: {
                    "reason": "implementation_blocked",
                    "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                    "recovery_reason": "prerequisite_gap_required",
                    "recovery_status": "PREREQUISITE_RETRY_FAILED",
                    "waiting_on_prerequisite_gap_id": completed_gap_id,
                    "waiting_on_prerequisite_source": "DESIGN_GAP",
                    "prerequisite_recovery_status": "RETRY_FAILED",
                    "prerequisite_recovery_reason": "completed_prerequisite_retry_failed",
                    "progress_report_path": blocker_progress_path.relative_to(workspace).as_posix(),
                    "architecture_path": blocker_architecture_path.relative_to(workspace).as_posix(),
                    "plan_path": blocker_plan_path.relative_to(workspace).as_posix(),
                    "recovery_event_id": "blocker-retry-failed",
                    "recovery_dependency_edge": {
                        **blocker_edge,
                        "status": "blocked",
                        "reason": "retry_failed_after_completed_prerequisite",
                    },
                },
            },
            "history": [],
        }) + "\n"),
        (blocker_progress_path, "# Progress Report\n\nRetry failed after prerequisite completion.\n"),
        (blocker_architecture_path, "# Parent Compile Smoke Architecture\n"),
        (blocker_plan_path, "# Parent Compile Smoke Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--architecture-index-root",
        "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )
    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["design_gap_id"] == blocker_gap_id
    assert payload["recovery_status"] == "PREREQUISITE_RETRY_FAILED"
    assert payload["waiting_on_work_id"] == ""
    assert payload["recovery_pointer_status"] == ""


@pytest.mark.parametrize("initial_recovery_status", ["PREREQUISITE_RETRY_FAILED", "TERMINAL_BLOCKED"])
def test_blocked_recovery_recorder_blocks_prerequisite_after_failed_retry(tmp_path, initial_recovery_status):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/2/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    edge = _recovery_dependency_edge(blocked="parser-syntax", blocker="already-completed")

    for path, text in [
        (state_path, json.dumps({
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": ["already-completed"],
            "blocked_items": {},
            "blocked_design_gaps": {
                "parser-syntax": {
                    "reason": "implementation_blocked",
                    "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                    "recovery_reason": "prerequisite_gap_required",
                    "recovery_status": initial_recovery_status,
                    "waiting_on_prerequisite_gap_id": "already-completed",
                    "waiting_on_prerequisite_source": "DESIGN_GAP",
                    "prerequisite_recovery_status": "RETRY_FAILED",
                    "prerequisite_recovery_reason": "completed_prerequisite_retry_failed",
                    "progress_report_path": progress_path.relative_to(workspace).as_posix(),
                    "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                    "plan_path": plan_path.relative_to(workspace).as_posix(),
                    "recovery_event_id": "parser-syntax-retry-failed",
                    "recovery_dependency_edge": {
                        **edge,
                        "status": "blocked",
                        "reason": "retry_failed_after_completed_prerequisite",
                    },
                }
            },
            "history": [],
        }) + "\n"),
        (recovery_bundle, json.dumps({
            "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
            "reason": "prerequisite_gap_required",
            "summary": "The retry found another prerequisite-shaped blocker.",
            "waiting_on_work_id": "new-prerequisite",
            "waiting_on_work_source": "DESIGN_GAP",
        }) + "\n"),
        (progress_path, "# Progress Report\n\nRetry failed after prerequisite completion.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-second-prerequisite",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_status"] == "TERMINAL_BLOCKED"
    assert blocked["recovery_reason"] == "prerequisite_retry_failed_requires_non_prerequisite_recovery"
    assert "new-prerequisite" not in json.dumps(blocked)
    assert drain_status_path.read_text(encoding="utf-8").strip() == "BLOCKED"


def test_blocked_recovery_recorder_rejects_self_prerequisite_edge(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    for path, text in [
        (state_path, json.dumps({
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": [],
            "blocked_items": {},
            "blocked_design_gaps": {},
            "history": [],
        }) + "\n"),
        (recovery_bundle, json.dumps({
            "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
            "reason": "prerequisite_gap_required",
            "recovery_dependency_edge": _recovery_dependency_edge(
                blocked="parser-syntax",
                blocker="parser-syntax",
            ),
        }) + "\n"),
        (progress_path, "# Progress Report\n\nA self prerequisite should fail closed.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
        check=False,
    )

    assert result.returncode != 0
    assert "Invalid recovery_dependency_edge" in result.stderr
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["blocked_design_gaps"] == {}


def test_prerequisite_block_after_approved_target_revision_allows_prerequisite_selection(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    revision_report = workspace / "state/drain/blocked-design-revision-report.json"
    review_decision = workspace / "state/drain/blocked-design-revision-loop-decision.txt"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    for path, text in [
        (state_path, json.dumps({
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": [],
            "blocked_items": {},
            "blocked_design_gaps": {},
            "history": [],
        }) + "\n"),
        (recovery_bundle, json.dumps({
            "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
            "reason": "prerequisite_gap_required",
            "recovery_dependency_edge": _recovery_dependency_edge(
                blocked="parser-syntax",
                blocker="generic-context-capability",
            ),
        }) + "\n"),
        (revision_report, json.dumps({
            "design_revision_decision": "REVISED",
            "summary": "Added a prerequisite design gap to the target design scope.",
        }) + "\n"),
        (review_decision, "APPROVE\n"),
        (progress_path, "# Progress Report\n\nA prerequisite gap is missing from target design scope.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--revision-report",
        revision_report.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        review_decision.relative_to(workspace).as_posix(),
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )
    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "SELECT_PREREQUISITE_WORK"
    assert payload["design_gap_id"] == "parser-syntax"
    assert payload["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert payload["recovery_reason"] == "prerequisite_gap_required"
    assert payload["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert payload["recovery_event_id"] == "parser-syntax-implementation-blocked"


def test_prerequisite_target_design_review_revise_keeps_gap_recoverable(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    revision_report = workspace / "state/drain/blocked-design-revision-report.json"
    review_decision = workspace / "state/drain/blocked-design-revision-loop-decision.txt"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    for path, text in [
        (state_path, json.dumps({
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": [],
            "blocked_items": {},
            "blocked_design_gaps": {
                "parser-syntax": {
                    "reason": "implementation_blocked",
                    "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                    "recovery_reason": "prerequisite_gap_required",
                    "recovery_status": "TARGET_DESIGN_REVISION_REQUIRED",
                    "progress_report_path": progress_path.relative_to(workspace).as_posix(),
                    "implementation_state_path": implementation_state_path.relative_to(workspace).as_posix(),
                    "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                    "plan_path": plan_path.relative_to(workspace).as_posix(),
                    "recovery_event_id": "parser-syntax-implementation-blocked",
                }
            },
            "history": [],
        }) + "\n"),
        (recovery_bundle, json.dumps({
            "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
            "reason": "prerequisite_gap_required",
            "summary": "Target design needs clearer prerequisite sequencing.",
            "recovery_dependency_edge": _recovery_dependency_edge(
                blocked="parser-syntax",
                blocker="generic-context-capability",
            ),
        }) + "\n"),
        (revision_report, json.dumps({
            "design_revision_decision": "REVISED",
            "summary": "Updated target design, but review requested another recovery pass.",
        }) + "\n"),
        (review_decision, "REVISE\n"),
        (progress_path, "# Progress Report\n\nA prerequisite gap is missing from target design scope.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--revision-report",
        revision_report.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        review_decision.relative_to(workspace).as_posix(),
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    assert blocked["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["recovery_reason"] == "prerequisite_gap_required"
    assert state["history"][-1]["event"] == "blocked"

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )
    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "SELECT_PREREQUISITE_WORK"
    assert payload["waiting_on_work_id"] == "generic-context-capability"
    assert payload["waiting_on_work_source"] == "DESIGN_GAP"
    assert payload["recovery_pointer_status"] == "WAITING"


def test_target_design_revision_revise_feedback_uses_reviewer_report(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    revision_report = workspace / "state/drain/blocked-design-revision-report.json"
    review_report = workspace / "artifacts/review/blocked-design-revision-iteration-0-review.json"
    review_decision = workspace / "state/drain/blocked-design-revision-loop-decision.txt"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"

    for path, text in [
        (state_path, json.dumps({
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": [],
            "blocked_items": {},
            "blocked_design_gaps": {},
            "history": [],
        }) + "\n"),
        (recovery_bundle, json.dumps({
            "blocked_recovery_route": "TARGET_DESIGN_REVISION_REQUIRED",
            "reason": "target_design_contract_gap",
        }) + "\n"),
        (revision_report, json.dumps({
            "design_revision_decision": "REVISED",
            "summary": "Reviser's own account of the revision.",
        }) + "\n"),
        (review_report, "# Reviewer Feedback\n\nRevise again: address the open contract gap.\n"),
        (review_decision, "REVISE\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--revision-report",
        revision_report.relative_to(workspace).as_posix(),
        "--review-report-path",
        review_report.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        review_decision.relative_to(workspace).as_posix(),
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    feedback_path = state_path.parent / "blocked-revision-review-feedback.parser-syntax.md"
    assert feedback_path.read_text(encoding="utf-8") == review_report.read_text(encoding="utf-8")
    assert feedback_path.read_text(encoding="utf-8") != revision_report.read_text(encoding="utf-8")

    # Fallback: when no --review-report-path is supplied, feedback still carries the revision report.
    other_state_path = workspace / "state/drain-fallback/run_state.json"
    other_state_path.parent.mkdir(parents=True, exist_ok=True)
    other_state_path.write_text(state_path.read_text(encoding="utf-8"), encoding="utf-8")
    other_summary_path = workspace / "artifacts/work/blocked-summary-fallback.json"
    other_pointer_path = workspace / "state/drain-fallback/blocked-summary-path.txt"
    other_drain_status_path = workspace / "state/drain-fallback/blocked-drain-status.txt"

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--revision-report",
        revision_report.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        review_decision.relative_to(workspace).as_posix(),
        "--terminal-action",
        "continue",
        "--state-path",
        other_state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--summary-path",
        other_summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        other_pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        other_drain_status_path.relative_to(workspace).as_posix(),
    )

    fallback_feedback_path = other_state_path.parent / "blocked-revision-review-feedback.parser-syntax.md"
    assert fallback_feedback_path.read_text(encoding="utf-8") == revision_report.read_text(encoding="utf-8")


def test_prerequisite_recovery_records_compact_dependency_pointer(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    blocked_gap_id = "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters"
    blocker_gap_id = "workflow-lisp-runtime-native-drain-private-context-bootstrap-prerequisite"
    progress_path = (
        workspace
        / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/"
        f"{blocked_gap_id}/"
        "progress_report.md"
    )
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = (
        workspace
        / "docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/"
        f"{blocked_gap_id}/"
        "implementation_architecture.md"
    )
    plan_path = (
        workspace
        / "docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/"
        f"{blocked_gap_id}/"
        "execution_plan.md"
    )

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_bundle.parent.mkdir(parents=True, exist_ok=True)
    recovery_bundle.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "reason": "prerequisite_gap_required",
                "waiting_on_work_id": blocker_gap_id,
                "waiting_on_work_source": "DESIGN_GAP",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for path, text in [
        (
            progress_path,
            (
                "# Progress Report\n\n"
                "Imported stdlib-adapter execution still fails with "
                "`private_exec_context_bootstrap_unsupported` before the finalizer branches.\n"
            ),
        ),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Imported Adapter Bootstrap Architecture\n"),
        (plan_path, "# Imported Adapter Bootstrap Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        blocked_gap_id,
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "bootstrap-gap-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"][blocked_gap_id]
    assert blocked["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["waiting_on_prerequisite_gap_id"] == blocker_gap_id
    assert blocked["waiting_on_prerequisite_source"] == "DESIGN_GAP"
    assert blocked["prerequisite_recovery_status"] == "WAITING_ON_PREREQUISITE"
    assert blocked["prerequisite_recovery_reason"] == "prerequisite_required"
    assert blocked.get("downstream_blocked_gap_id", "") == ""
    assert blocked["blocking_failure_code"] == "prerequisite_gap_required"
    assert blocked["recovery_dependency_edge"]["blocker_work"] == {"source": "DESIGN_GAP", "id": blocker_gap_id}
    assert blocked["recovery_dependency_edge"]["retry_target"] == {"source": "DESIGN_GAP", "id": blocked_gap_id}
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )
    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "SELECT_PREREQUISITE_WORK"
    assert payload["design_gap_id"] == blocked_gap_id
    assert payload["waiting_on_work_id"] == blocker_gap_id
    assert payload["waiting_on_work_source"] == "DESIGN_GAP"
    assert payload["recovery_pointer_status"] == "WAITING"
    assert payload["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert payload["recovery_status"] == "PREREQUISITE_WORK_PENDING"


def test_blocked_recovery_completed_slice_records_follow_up_without_blocking_current_gap(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/selected-slice-summary.json"
    pointer_path = workspace / "state/drain/selected-slice-summary-path.txt"
    drain_status_path = workspace / "state/drain/selected-slice-drain-status.txt"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/selected-slice/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/selected-slice/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/selected-slice/execution_plan.md"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_bundle.parent.mkdir(parents=True, exist_ok=True)
    recovery_bundle.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "reason": "prerequisite_gap_required",
                "summary": "Scoped acceptance passed; broad closeout requires a follow-up gap.",
                "current_work_status": "COMPLETED",
                "recovery_dependency_edge": _recovery_dependency_edge(
                    blocked="selected-slice",
                    blocker="follow-up-gap",
                    reason_code="broad_closeout_follow_up_required",
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for path, text in [
        (progress_path, "# Progress Report\n\nScope completed; broad closeout follow-up remains.\n"),
        (implementation_state_path, '{"implementation_state":"BLOCKED"}\n'),
        (architecture_path, "# Selected Slice Architecture\n"),
        (plan_path, "# Selected Slice Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "selected-slice",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "selected-slice-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "selected-slice" in state["completed_design_gaps"]
    assert "selected-slice" not in state["blocked_design_gaps"]
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["item_status"] == "COMPLETED"
    follow_up = state["history"][-1]
    assert follow_up["event"] == "follow_up_required"
    assert follow_up["item_id"] == "selected-slice"
    assert follow_up["recovery_dependency_edge"]["blocker_work"] == {
        "source": "DESIGN_GAP",
        "id": "follow-up-gap",
    }


def test_prerequisite_recovery_rejects_missing_dependency_edge(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    progress_path = (
        workspace
        / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/"
        "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters/"
        "progress_report.md"
    )
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = (
        workspace
        / "docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/"
        "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters/"
        "implementation_architecture.md"
    )
    plan_path = (
        workspace
        / "docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/"
        "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters/"
        "execution_plan.md"
    )

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_bundle.parent.mkdir(parents=True, exist_ok=True)
    recovery_bundle.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "reason": "prerequisite_gap_required",
                "summary": "A different prerequisite gap still needs implementation before bootstrap can proceed.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for path, text in [
        (progress_path, "# Progress Report\n\nBootstrap is still blocked, but no structured boundary evidence was emitted.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Imported Adapter Bootstrap Architecture\n"),
        (plan_path, "# Imported Adapter Bootstrap Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "bootstrap-gap-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
        check=False,
    )

    assert result.returncode != 0
    assert "requires recovery_dependency_edge" in result.stderr


def test_prerequisite_recovery_accepts_proposed_prerequisite_gap(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    progress_path = workspace / "artifacts/work/design-gaps/parser-syntax/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/design-gaps/parser-syntax/execution_plan.md"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_bundle.parent.mkdir(parents=True, exist_ok=True)
    recovery_bundle.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "reason": "prerequisite_gap_required",
                "summary": "A child workflow union provenance gap must land first.",
                "proposed_prerequisite": {
                    "id": "child-union-provenance",
                    "title": "Child workflow union provenance",
                    "scope": "Specify child workflow union result provenance.",
                    "reason": "parent match cannot consume child union result",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for path, text in [
        (progress_path, "# Progress Report\n\nChild union provenance is missing.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["waiting_on_prerequisite_gap_id"] == "child-union-provenance"
    assert blocked["prerequisite_gap_hint"] == (
        "Child workflow union provenance - Specify child workflow union result provenance."
    )
    edge = blocked["recovery_dependency_edge"]
    assert edge["blocker_work"] == {"source": "DESIGN_GAP", "id": "child-union-provenance"}
    assert edge["evidence"]["proposed_prerequisite"]["scope"] == (
        "Specify child workflow union result provenance."
    )
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"


def test_prerequisite_recovery_rejects_self_completion_edge(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    progress_path = workspace / "artifacts/work/design-gaps/parser-syntax/progress_report.md"
    architecture_path = workspace / "docs/plans/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/design-gaps/parser-syntax/execution_plan.md"
    for path, text in [
        (progress_path, "# Progress Report\n"),
        (architecture_path, "# Architecture\n"),
        (plan_path, "# Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_bundle.parent.mkdir(parents=True, exist_ok=True)
    recovery_bundle.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "reason": "prerequisite_gap_required",
                "recovery_dependency_edge": {
                    "blocked_work": {"source": "DESIGN_GAP", "id": "parser-syntax"},
                    "blocker_work": {"source": "DESIGN_GAP", "id": "parser-syntax"},
                    "relation": "requires_completion",
                    "reason_code": "missing_parser",
                    "ready_when": {"kind": "completed", "source": "DESIGN_GAP", "id": "parser-syntax"},
                    "retry_target": {"source": "DESIGN_GAP", "id": "parser-syntax"},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--summary-path",
        "artifacts/work/blocked-summary.json",
        "--summary-pointer-path",
        "state/drain/blocked-summary-path.txt",
        "--drain-status-path",
        "state/drain/blocked-drain-status.txt",
        check=False,
    )

    assert result.returncode != 0
    assert "self_completion_dependency" in result.stderr


def test_prerequisite_boundary_summary_waits_for_bootstrap(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"
    original_gap_id = (
        "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters"
    )
    blocker_gap_id = "workflow-lisp-runtime-native-drain-private-context-bootstrap-prerequisite"
    downstream_gap_id = (
        "workflow-lisp-runtime-native-drain-work-item-summary-ownership-over-imported-finalize-selected-item"
    )

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    original_gap_id: {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "waiting_on_prerequisite_gap_id": blocker_gap_id,
                        "waiting_on_prerequisite_source": "DESIGN_GAP",
                        "prerequisite_recovery_status": "WAITING_ON_PREREQUISITE",
                        "prerequisite_recovery_reason": "prerequisite_required",
                        "downstream_blocked_gap_id": downstream_gap_id,
                        "blocking_failure_code": "private_exec_context_bootstrap_unsupported",
                        "retry_condition": (
                            "imported stdlib-adapter selector path reaches imported finalizer branches "
                            "without private_exec_context_bootstrap_unsupported"
                        ),
                        "recovery_dependency_edge": _recovery_dependency_edge(
                            blocked=original_gap_id,
                            blocker=blocker_gap_id,
                            reason_code="private_exec_context_bootstrap_unsupported",
                            downstream=[downstream_gap_id],
                        ),
                        "recovery_event_id": "bootstrap-gap-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": original_gap_id,
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_WORK_PENDING",
                "recovery_event_id": "bootstrap-gap-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": downstream_gap_id,
                "prerequisite_relation": (
                    f"{downstream_gap_id} remains blocked until {original_gap_id} "
                    "proves imported finalizer reachability."
                ),
                "selection_rationale": "Summary ownership should wait for bootstrap reachability.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("CONTINUE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"][original_gap_id]
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["waiting_on_prerequisite_gap_id"] == blocker_gap_id
    assert blocked["downstream_blocked_gap_id"] == downstream_gap_id
    assert blocked["prerequisite_recovery_status"] == "WAITING_ON_PREREQUISITE"
    assert blocked["prerequisite_recovery_reason"] == "selected_downstream_before_blocker_ready"
    assert state["history"][-1]["event"] == "prerequisite_recovery_continues"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RECOVERY_CONTINUES"
    assert summary["reason"] == "selected_downstream_before_blocker_ready"
    assert summary["selected_prerequisite_id"] == blocker_gap_id
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"


def test_prerequisite_boundary_retry_ready_after_bootstrap(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"
    original_gap_id = (
        "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters"
    )
    downstream_gap_id = (
        "workflow-lisp-runtime-native-drain-work-item-summary-ownership-over-imported-finalize-selected-item"
    )

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [original_gap_id],
                "blocked_items": {},
                "blocked_design_gaps": {
                    original_gap_id: {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "waiting_on_prerequisite_gap_id": original_gap_id,
                        "waiting_on_prerequisite_source": "DESIGN_GAP",
                        "prerequisite_recovery_status": "WAITING_ON_BOOTSTRAP_REACHABILITY",
                        "prerequisite_recovery_reason": "bootstrap_reachability_missing",
                        "downstream_blocked_gap_id": downstream_gap_id,
                        "blocking_failure_code": "private_exec_context_bootstrap_unsupported",
                        "retry_condition": (
                            "imported stdlib-adapter selector path reaches imported finalizer branches "
                            "without private_exec_context_bootstrap_unsupported"
                        ),
                        "recovery_event_id": "bootstrap-gap-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": original_gap_id,
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_WORK_PENDING",
                "recovery_event_id": "bootstrap-gap-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": downstream_gap_id,
                "prerequisite_relation": (
                    f"{downstream_gap_id} becomes selectable after {original_gap_id} completes."
                ),
                "selection_rationale": "Bootstrap reachability is proven, so summary ownership is now selectable.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("CONTINUE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"][original_gap_id]
    assert blocked["recovery_status"] == "RETRY_READY"
    assert blocked["waiting_on_prerequisite_gap_id"] == original_gap_id
    assert blocked["downstream_blocked_gap_id"] == downstream_gap_id
    assert blocked["prerequisite_recovery_status"] == "COMPLETED"
    assert blocked["prerequisite_recovery_reason"] == "prerequisite_completed"
    assert state["history"][-1]["event"] == "prerequisite_recovery_satisfied"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RETRY_READY"
    assert summary["selected_prerequisite_id"] == original_gap_id
    assert summary["reason"] == "prerequisite_completed"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"


def test_prerequisite_boundary_circular_relation_fails_closed(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"
    original_gap_id = (
        "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters"
    )

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    original_gap_id: {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "waiting_on_prerequisite_gap_id": original_gap_id,
                        "waiting_on_prerequisite_source": "DESIGN_GAP",
                        "prerequisite_recovery_status": "WAITING_ON_BOOTSTRAP_REACHABILITY",
                        "prerequisite_recovery_reason": "bootstrap_reachability_missing",
                        "downstream_blocked_gap_id": (
                            "workflow-lisp-runtime-native-drain-work-item-summary-ownership-over-imported-finalize-selected-item"
                        ),
                        "blocking_failure_code": "private_exec_context_bootstrap_unsupported",
                        "retry_condition": (
                            "imported stdlib-adapter selector path reaches imported finalizer branches "
                            "without private_exec_context_bootstrap_unsupported"
                        ),
                        "recovery_event_id": "bootstrap-gap-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": original_gap_id,
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_WORK_PENDING",
                "recovery_event_id": "bootstrap-gap-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": original_gap_id,
                "prerequisite_relation": (
                    f"{original_gap_id} depends on itself until bootstrap reachability is proven."
                ),
                "selection_rationale": "Accidental circular prerequisite relation.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("CONTINUE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"][original_gap_id]
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["prerequisite_recovery_status"] == "RECOVERY_CONTINUES"
    assert blocked["prerequisite_recovery_reason"] == "circular_prerequisite_relation"
    assert blocked["waiting_on_prerequisite_gap_id"] == original_gap_id
    assert state["history"][-1]["event"] == "prerequisite_recovery_continues"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RECOVERY_CONTINUES"
    assert summary["reason"] == "circular_prerequisite_relation"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"


def test_detector_treats_legacy_prerequisite_blocked_as_recoverable(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    for path, text in [
        (progress_path, "# Progress Report\n\nLegacy prerequisite state needs recovery.\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_BLOCKED",
                        "prerequisite_recovery_status": "BLOCKED_UNRECOVERABLE",
                        "prerequisite_recovery_reason": "missing_prerequisite_relation",
                        "progress_report_path": progress_path.relative_to(workspace).as_posix(),
                        "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                        "plan_path": plan_path.relative_to(workspace).as_posix(),
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "BLOCKED"
    assert payload["block_reason"] == "missing_prerequisite_dependency_edge"


def test_prerequisite_pending_with_completed_waiting_gap_retries_original_without_selection(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    for path, text in [
        (progress_path, "# Progress Report\n\nWaiting prerequisite has completed.\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": ["generic-context-capability"],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "waiting_on_prerequisite_gap_id": "generic-context-capability",
                        "waiting_on_prerequisite_source": "DESIGN_GAP",
                        "progress_report_path": progress_path.relative_to(workspace).as_posix(),
                        "implementation_state_path": "state/drain/iterations/0/work-item/implementation_state.json",
                        "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                        "plan_path": plan_path.relative_to(workspace).as_posix(),
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--architecture-index-root",
        "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["design_gap_id"] == "parser-syntax"
    assert payload["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert payload["recovery_status"] == "RETRY_READY"
    assert payload["progress_report_path"] == progress_path.relative_to(workspace).as_posix()
    assert (workspace / payload["architecture_copy_path"]).read_text(encoding="utf-8") == "# Parser Syntax Architecture\n"


def test_prerequisite_recovery_completion_marks_original_gap_retry_ready(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": ["generic-context-capability"],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "progress_report_path": "artifacts/work/design-gaps/parser-syntax/progress_report.md",
                        "implementation_state_path": "state/drain/iterations/0/work-item/implementation_state.json",
                        "architecture_path": "docs/plans/design-gaps/parser-syntax/implementation_architecture.md",
                        "plan_path": "docs/plans/design-gaps/parser-syntax/execution_plan.md",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_event_id": "parser-syntax-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "generic-context-capability",
                "prerequisite_relation": "generic-context-capability unblocks parser-syntax.",
                "selection_rationale": "Required prerequisite for parser syntax.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("CONTINUE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_status"] == "RETRY_READY"
    assert blocked["waiting_on_prerequisite_gap_id"] == "generic-context-capability"
    assert blocked["prerequisite_recovery_status"] == "COMPLETED"
    assert blocked["original_blocked_gap_id"] == "parser-syntax"
    assert blocked["prerequisite_selection_bundle_path"].endswith("/prerequisite-selector/selection.json")
    assert state["history"][-1]["event"] == "prerequisite_recovery_satisfied"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RETRY_READY"


def test_prerequisite_recovery_self_selection_with_completed_waiting_gap_retries_original(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": ["generic-context-capability"],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "waiting_on_prerequisite_gap_id": "generic-context-capability",
                        "waiting_on_prerequisite_source": "DESIGN_GAP",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_WORK_PENDING",
                "recovery_event_id": "parser-syntax-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "parser-syntax",
                "prerequisite_relation": "Resume parser-syntax because generic-context-capability is completed.",
                "selection_rationale": "The original blocked gap can now be retried.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("CONTINUE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_status"] == "RETRY_READY"
    assert blocked["waiting_on_prerequisite_gap_id"] == "generic-context-capability"
    assert blocked["prerequisite_recovery_status"] == "COMPLETED"
    assert state["history"][-1]["event"] == "prerequisite_recovery_satisfied"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RETRY_READY"
    assert summary["selected_prerequisite_id"] == "generic-context-capability"


def test_prerequisite_recovery_self_selected_gap_already_completed_does_not_require_blocked_entry(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": ["parser-syntax"],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_WORK_PENDING",
                "recovery_event_id": "parser-syntax-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "parser-syntax",
                "prerequisite_relation": "Finish parser-syntax directly now that its prerequisite work is complete.",
                "selection_rationale": "The original blocked gap was selected and completed in this iteration.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("CONTINUE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "parser-syntax" not in state["blocked_design_gaps"]
    assert state["history"][-1]["event"] == "prerequisite_recovery_satisfied"
    assert state["history"][-1]["reason"] == "original_gap_completed"
    assert state["history"][-1]["waiting_on_prerequisite_gap_id"] == "parser-syntax"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RETRY_READY"
    assert summary["reason"] == "original_gap_completed"


def test_prerequisite_recovery_recoverable_prerequisite_block_continues(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "progress_report_path": "artifacts/work/design-gaps/parser-syntax/progress_report.md",
                        "implementation_state_path": "state/drain/iterations/0/work-item/implementation_state.json",
                        "architecture_path": "docs/plans/design-gaps/parser-syntax/implementation_architecture.md",
                        "plan_path": "docs/plans/design-gaps/parser-syntax/execution_plan.md",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    },
                    "owner-seam-prerequisite": {
                        "reason": "implementation_blocked",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "progress_report_path": "artifacts/work/design-gaps/owner-seam-prerequisite/progress_report.md",
                        "implementation_state_path": "state/drain/iterations/1/work-item/implementation_state.json",
                        "architecture_path": "docs/plans/design-gaps/owner-seam-prerequisite/implementation_architecture.md",
                        "plan_path": "docs/plans/design-gaps/owner-seam-prerequisite/execution_plan.md",
                        "recovery_event_id": "owner-seam-prerequisite-implementation-blocked",
                    },
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_WORK_PENDING",
                "recovery_event_id": "parser-syntax-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "owner-seam-prerequisite",
                "prerequisite_relation": "owner-seam-prerequisite unblocks parser-syntax.",
                "selection_rationale": "Required prerequisite for parser syntax.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("CONTINUE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    original = state["blocked_design_gaps"]["parser-syntax"]
    prerequisite = state["blocked_design_gaps"]["owner-seam-prerequisite"]
    assert original["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert original["prerequisite_recovery_status"] == "BLOCKED_RECOVERABLE"
    assert original["waiting_on_prerequisite_gap_id"] == "owner-seam-prerequisite"
    assert original["prerequisite_recovery_reason"] == "selected_prerequisite_blocked_recoverable"
    assert prerequisite["recovery_route"] == "GAP_DESIGN_REVISION_REQUIRED"
    assert state["history"][-1]["event"] == "prerequisite_recovery_pending_on_blocked_prerequisite"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "WAITING_ON_RECOVERABLE_PREREQUISITE"


def test_prerequisite_recovery_terminal_prerequisite_block_keeps_original_recoverable(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    },
                    "owner-seam-prerequisite": {
                        "reason": "implementation_blocked",
                        "recovery_route": "TERMINAL_BLOCKED",
                        "recovery_reason": "user_decision_required",
                        "recovery_event_id": "owner-seam-prerequisite-implementation-blocked",
                    },
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_WORK_PENDING",
                "recovery_event_id": "parser-syntax-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "owner-seam-prerequisite",
                "prerequisite_relation": "owner-seam-prerequisite unblocks parser-syntax.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("CONTINUE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    original = state["blocked_design_gaps"]["parser-syntax"]
    assert original["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert original["prerequisite_recovery_status"] == "RECOVERY_CONTINUES"
    assert original["waiting_on_prerequisite_gap_id"] == "owner-seam-prerequisite"
    assert original["prerequisite_recovery_reason"] == "selected_prerequisite_user_input_required"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RECOVERY_CONTINUES"
    assert summary["reason"] == "selected_prerequisite_user_input_required"


def test_prerequisite_retry_ready_is_overridden_when_retry_blocks_again(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"
    detector_output = workspace / "state/drain/blocked-recovery.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    implementation_state_path = workspace / "state/drain/iterations/0/work-item/implementation_state.json"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"

    for path, text in [
        (progress_path, "# Progress Report\n\nRetry blocked again because another prerequisite is missing.\n"),
        (implementation_state_path, "{}\n"),
        (architecture_path, "# Parser Syntax Architecture\n"),
        (plan_path, "# Parser Syntax Plan\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": ["generic-context-capability"],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "RETRY_READY",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                        "progress_report_path": progress_path.relative_to(workspace).as_posix(),
                        "implementation_state_path": implementation_state_path.relative_to(workspace).as_posix(),
                        "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                        "plan_path": plan_path.relative_to(workspace).as_posix(),
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    recovery_bundle.parent.mkdir(parents=True, exist_ok=True)
    recovery_bundle.write_text(
        json.dumps(
            {
                "blocked_recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "reason": "prerequisite_gap_required",
                "recovery_dependency_edge": _recovery_dependency_edge(
                    blocked="parser-syntax",
                    blocker="owner-seam-prerequisite",
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "--recovery-bundle-path",
        recovery_bundle.relative_to(workspace).as_posix(),
        "--target-design-review-decision",
        "NOT_APPLICABLE",
        "--terminal-action",
        "continue",
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--item-id",
        "parser-syntax",
        "--source",
        "DESIGN_GAP",
        "--progress-report-path",
        progress_path.relative_to(workspace).as_posix(),
        "--implementation-state-path",
        implementation_state_path.relative_to(workspace).as_posix(),
        "--architecture-path",
        architecture_path.relative_to(workspace).as_posix(),
        "--plan-path",
        plan_path.relative_to(workspace).as_posix(),
        "--recovery-event-id",
        "parser-syntax-implementation-blocked",
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert blocked["recovery_reason"] == "prerequisite_gap_required"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["item_status"] == "BLOCKED"

    _run_script(
        workspace,
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN",
        "--output",
        detector_output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(detector_output.read_text(encoding="utf-8"))
    assert payload["pre_selection_route"] == "SELECT_PREREQUISITE_WORK"
    assert payload["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"
    assert payload["recovery_status"] == "PREREQUISITE_WORK_PENDING"


def test_prerequisite_recovery_decline_keeps_original_gap_blocked(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "progress_report_path": "artifacts/work/design-gaps/parser-syntax/progress_report.md",
                        "implementation_state_path": "state/drain/iterations/0/work-item/implementation_state.json",
                        "architecture_path": "docs/plans/design-gaps/parser-syntax/implementation_architecture.md",
                        "plan_path": "docs/plans/design-gaps/parser-syntax/execution_plan.md",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_event_id": "parser-syntax-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps({"selection_status": "DONE", "selection_rationale": "No safe prerequisite found."}) + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("DONE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["prerequisite_recovery_status"] == "RECOVERY_CONTINUES"
    assert blocked["prerequisite_recovery_reason"] == "prerequisite_selector_declined"
    assert "parser-syntax" in state["blocked_design_gaps"]
    assert state["history"][-1]["event"] == "prerequisite_recovery_continues"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RECOVERY_CONTINUES"


def test_prerequisite_recovery_decline_with_completed_waiting_gap_retries_original(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": ["generic-context-capability"],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "waiting_on_prerequisite_gap_id": "generic-context-capability",
                        "waiting_on_prerequisite_source": "DESIGN_GAP",
                        "progress_report_path": "artifacts/work/design-gaps/parser-syntax/progress_report.md",
                        "implementation_state_path": "state/drain/iterations/0/work-item/implementation_state.json",
                        "architecture_path": "docs/plans/design-gaps/parser-syntax/implementation_architecture.md",
                        "plan_path": "docs/plans/design-gaps/parser-syntax/execution_plan.md",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_status": "PREREQUISITE_WORK_PENDING",
                "recovery_event_id": "parser-syntax-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps({"selection_status": "BLOCKED", "selection_rationale": "No safe prerequisite found."}) + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("BLOCKED\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_status"] == "RETRY_READY"
    assert blocked["prerequisite_recovery_status"] == "COMPLETED"
    assert blocked["waiting_on_prerequisite_gap_id"] == "generic-context-capability"
    assert blocked["prerequisite_recovery_reason"] == "prerequisite_completed"
    assert state["history"][-1]["event"] == "prerequisite_recovery_satisfied"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RETRY_READY"
    assert summary["reason"] == "prerequisite_completed"


def test_prerequisite_recovery_missing_relation_remains_recoverable(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    pre_selection_bundle = workspace / "state/drain/blocked-recovery.json"
    selection_bundle = workspace / "state/drain/prerequisite-selector/selection.json"
    selected_status = workspace / "state/drain/selected-prerequisite-status.txt"
    summary_path = workspace / "artifacts/work/prerequisite-recovery-summary.json"
    drain_status_path = workspace / "state/drain/prerequisite-recovery-status.txt"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                        "recovery_reason": "prerequisite_gap_required",
                        "recovery_status": "PREREQUISITE_WORK_PENDING",
                        "progress_report_path": "artifacts/work/design-gaps/parser-syntax/progress_report.md",
                        "implementation_state_path": "state/drain/iterations/0/work-item/implementation_state.json",
                        "architecture_path": "docs/plans/design-gaps/parser-syntax/implementation_architecture.md",
                        "plan_path": "docs/plans/design-gaps/parser-syntax/execution_plan.md",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pre_selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    pre_selection_bundle.write_text(
        json.dumps(
            {
                "pre_selection_route": "SELECT_PREREQUISITE_WORK",
                "design_gap_id": "parser-syntax",
                "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                "recovery_reason": "prerequisite_gap_required",
                "recovery_event_id": "parser-syntax-implementation-blocked",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps({"selection_status": "DRAFT_DESIGN_GAP", "design_gap_id": "generic-context-capability"}) + "\n",
        encoding="utf-8",
    )
    selected_status.write_text("CONTINUE\n", encoding="utf-8")

    _run_script(
        workspace,
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
        "--pre-selection-bundle-path",
        pre_selection_bundle.relative_to(workspace).as_posix(),
        "--selection-bundle-path",
        selection_bundle.relative_to(workspace).as_posix(),
        "--selected-work-status-path",
        selected_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert blocked["recovery_status"] == "PREREQUISITE_WORK_PENDING"
    assert blocked["prerequisite_recovery_status"] == "RECOVERY_CONTINUES"
    assert blocked["waiting_on_prerequisite_gap_id"] == "generic-context-capability"
    assert blocked["prerequisite_recovery_reason"] == "missing_prerequisite_relation"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "CONTINUE"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "RECOVERY_CONTINUES"


def test_resolve_drain_iteration_status_maps_recovery_routes(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = str(ROOT / "workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py")

    cases = [
        ("SELECT_NORMAL_WORK", "ignored", "ignored", "ignored", "DONE", "DONE"),
        ("SELECT_DONE_REVIEW", "ignored", "ignored", "ignored", "DONE", "DONE"),
        ("SELECT_PREREQUISITE_WORK", "ignored", "ignored", "CONTINUE", "CONTINUE", "CONTINUE"),
        ("SELECT_PREREQUISITE_WORK", "ignored", "ignored", "BLOCKED", "CONTINUE", "BLOCKED"),
        ("RECOVER_BLOCKED_DESIGN_GAP", "RUN_RECOVERED_GAP", "CONTINUE", "IGNORED", "IGNORED", "CONTINUE"),
        ("RECOVER_BLOCKED_DESIGN_GAP", "RUN_RECOVERED_GAP", "BLOCKED", "IGNORED", "IGNORED", "BLOCKED"),
        ("RECOVER_BLOCKED_DESIGN_GAP", "RUN_RECOVERED_GAP", "IGNORED", "IGNORED", "IGNORED", "CONTINUE"),
        ("RECOVER_BLOCKED_DESIGN_GAP", "CONTINUE", "IGNORED", "IGNORED", "IGNORED", "CONTINUE"),
        ("RECOVER_BLOCKED_DESIGN_GAP", "BLOCKED", "IGNORED", "IGNORED", "IGNORED", "BLOCKED"),
        ("BLOCKED", "IGNORED", "IGNORED", "IGNORED", "IGNORED", "BLOCKED"),
    ]

    for index, (route, recovery, recovered, prerequisite, normal, expected) in enumerate(cases):
        root = workspace / f"case-{index}"
        root.mkdir()
        bundle = root / "pre-selection.json"
        normal_path = root / "normal.txt"
        recovery_path = root / "recovery.txt"
        recovered_path = root / "recovered.txt"
        prerequisite_path = root / "prerequisite.txt"
        output = root / "output.txt"
        bundle.write_text(json.dumps({"pre_selection_route": route}) + "\n", encoding="utf-8")
        if normal != "IGNORED":
            normal_path.write_text(normal + "\n", encoding="utf-8")
        if recovery != "IGNORED":
            recovery_path.write_text(recovery + "\n", encoding="utf-8")
        if recovered != "IGNORED":
            recovered_path.write_text(recovered + "\n", encoding="utf-8")
        if prerequisite != "IGNORED":
            prerequisite_path.write_text(prerequisite + "\n", encoding="utf-8")

        _run_script(
            workspace,
            script,
            "--pre-selection-bundle-path",
            bundle.relative_to(workspace).as_posix(),
            "--normal-status-path",
            normal_path.relative_to(workspace).as_posix(),
            "--recovery-record-status-path",
            recovery_path.relative_to(workspace).as_posix(),
            "--recovered-work-item-status-path",
            recovered_path.relative_to(workspace).as_posix(),
            "--prerequisite-recovery-status-path",
            prerequisite_path.relative_to(workspace).as_posix(),
            "--output",
            output.relative_to(workspace).as_posix(),
        )

        assert output.read_text(encoding="utf-8").strip() == expected


def test_resolve_drain_iteration_status_uses_recovered_child_output_value(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = str(ROOT / "workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py")
    root = workspace / "case"
    root.mkdir()
    bundle = root / "pre-selection.json"
    recovery_path = root / "recovery.txt"
    output = root / "output.txt"
    bundle.write_text(json.dumps({"pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP"}) + "\n", encoding="utf-8")
    recovery_path.write_text("RUN_RECOVERED_GAP\n", encoding="utf-8")

    _run_script(
        workspace,
        script,
        "--pre-selection-bundle-path",
        bundle.relative_to(workspace).as_posix(),
        "--normal-status-path",
        "state/missing-normal.txt",
        "--recovery-record-status-path",
        recovery_path.relative_to(workspace).as_posix(),
        "--recovered-work-item-status-path",
        "state/private-child-status-not-published.txt",
        "--recovered-work-item-status-value",
        "CONTINUE",
        "--prerequisite-recovery-status-path",
        "state/missing-prerequisite.txt",
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    assert output.read_text(encoding="utf-8").strip() == "CONTINUE"


def test_resolve_drain_iteration_status_rejects_unrecorded_blocked_terminal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = str(ROOT / "workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py")
    root = workspace / "case"
    root.mkdir()
    bundle = root / "pre-selection.json"
    normal_path = root / "normal.txt"
    recovery_path = root / "recovery.txt"
    recovered_path = root / "recovered.txt"
    prerequisite_path = root / "prerequisite.txt"
    run_state_path = root / "run-state.json"
    output = root / "output.txt"

    bundle.write_text(json.dumps({"pre_selection_route": "SELECT_NORMAL_WORK"}) + "\n", encoding="utf-8")
    normal_path.write_text("BLOCKED\n", encoding="utf-8")
    recovery_path.write_text("CONTINUE\n", encoding="utf-8")
    prerequisite_path.write_text("CONTINUE\n", encoding="utf-8")
    run_state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_script(
        workspace,
        script,
        "--pre-selection-bundle-path",
        bundle.relative_to(workspace).as_posix(),
        "--normal-status-path",
        normal_path.relative_to(workspace).as_posix(),
        "--recovery-record-status-path",
        recovery_path.relative_to(workspace).as_posix(),
        "--recovered-work-item-status-path",
        recovered_path.relative_to(workspace).as_posix(),
        "--prerequisite-recovery-status-path",
        prerequisite_path.relative_to(workspace).as_posix(),
        "--run-state-path",
        run_state_path.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
        check=False,
    )

    assert result.returncode != 0
    assert "BLOCKED drain status requires recorded blocked work" in result.stderr
    assert not output.exists()


def test_resolve_drain_iteration_status_allows_recorded_blocked_terminal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = str(ROOT / "workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py")
    root = workspace / "case"
    root.mkdir()
    bundle = root / "pre-selection.json"
    normal_path = root / "normal.txt"
    recovery_path = root / "recovery.txt"
    recovered_path = root / "recovered.txt"
    prerequisite_path = root / "prerequisite.txt"
    run_state_path = root / "run-state.json"
    output = root / "output.txt"

    bundle.write_text(json.dumps({"pre_selection_route": "SELECT_NORMAL_WORK"}) + "\n", encoding="utf-8")
    normal_path.write_text("BLOCKED\n", encoding="utf-8")
    recovery_path.write_text("CONTINUE\n", encoding="utf-8")
    prerequisite_path.write_text("CONTINUE\n", encoding="utf-8")
    run_state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "blocked-gap": {
                        "reason": "implementation_blocked",
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        script,
        "--pre-selection-bundle-path",
        bundle.relative_to(workspace).as_posix(),
        "--normal-status-path",
        normal_path.relative_to(workspace).as_posix(),
        "--recovery-record-status-path",
        recovery_path.relative_to(workspace).as_posix(),
        "--recovered-work-item-status-path",
        recovered_path.relative_to(workspace).as_posix(),
        "--prerequisite-recovery-status-path",
        prerequisite_path.relative_to(workspace).as_posix(),
        "--run-state-path",
        run_state_path.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    assert output.read_text(encoding="utf-8").strip() == "BLOCKED"


def test_resolve_drain_iteration_status_allows_recorded_run_level_blocker(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = str(ROOT / "workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py")
    root = workspace / "case"
    root.mkdir()
    bundle = root / "pre-selection.json"
    normal_path = root / "normal.txt"
    recovery_path = root / "recovery.txt"
    recovered_path = root / "recovered.txt"
    prerequisite_path = root / "prerequisite.txt"
    run_state_path = root / "run-state.json"
    output = root / "output.txt"

    bundle.write_text(json.dumps({"pre_selection_route": "SELECT_NORMAL_WORK"}) + "\n", encoding="utf-8")
    normal_path.write_text("BLOCKED\n", encoding="utf-8")
    recovery_path.write_text("CONTINUE\n", encoding="utf-8")
    prerequisite_path.write_text("CONTINUE\n", encoding="utf-8")
    run_state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "blocked_run": {
                    "reason": "selector_blocked",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        script,
        "--pre-selection-bundle-path",
        bundle.relative_to(workspace).as_posix(),
        "--normal-status-path",
        normal_path.relative_to(workspace).as_posix(),
        "--recovery-record-status-path",
        recovery_path.relative_to(workspace).as_posix(),
        "--recovered-work-item-status-path",
        recovered_path.relative_to(workspace).as_posix(),
        "--prerequisite-recovery-status-path",
        prerequisite_path.relative_to(workspace).as_posix(),
        "--run-state-path",
        run_state_path.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    assert output.read_text(encoding="utf-8").strip() == "BLOCKED"


def test_update_run_state_records_selector_run_level_block(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    selection_path = workspace / "state/drain/selection.json"
    drain_status_path = workspace / "state/drain/drain-status.txt"
    state_path.parent.mkdir(parents=True)
    selection_path.write_text(
        json.dumps(
            {
                "selection_status": "BLOCKED",
                "selection_rationale": "Target and baseline conflict.",
                "blocking_reasons": ["missing architectural decision"],
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
        "run_blocked",
        "--selection-path",
        selection_path.relative_to(workspace).as_posix(),
        "--reason",
        "selector_blocked",
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["blocked_run"]["reason"] == "selector_blocked"
    assert state["blocked_run"]["selection_rationale"] == "Target and baseline conflict."
    assert state["blocked_run"]["blocking_reasons"] == ["missing architectural decision"]
    assert state["history"][-1]["event"] == "run_blocked"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "BLOCKED"


def test_update_run_state_skips_run_blocked_event_for_recovery_placeholder_bundle(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    selection_path = workspace / "state/drain/blocked-recovery.json"
    drain_status_path = workspace / "state/drain/drain-status.txt"
    state_path.parent.mkdir(parents=True)
    selection_path.write_text(
        json.dumps(
            {
                "pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP",
                "design_gap_id": "parser-syntax",
                "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                "recovery_reason": "implementation_architecture_under_scoped",
                "recovery_status": "RECOVERABLE",
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
        "run_blocked",
        "--selection-path",
        selection_path.relative_to(workspace).as_posix(),
        "--reason",
        "selector_blocked",
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["blocked_run"] is None
    assert all(entry.get("event") != "run_blocked" for entry in state["history"])
    assert drain_status_path.read_text(encoding="utf-8").strip() == "BLOCKED"


def test_update_run_state_records_honest_blocked_run_for_step_back_placeholder_bundle(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    selection_path = workspace / "state/drain/blocked-step-back.json"
    drain_status_path = workspace / "state/drain/drain-status.txt"
    state_path.parent.mkdir(parents=True)
    selection_path.write_text(
        json.dumps(
            {
                "pre_selection_route": "BLOCKED",
                "recovery_route": "TERMINAL_BLOCKED",
                "recovery_reason": "workflow made no forward progress across iterations",
                "recovery_status": "STEP_BACK_RECORDED",
                "block_reason": "no_forward_progress",
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
        "run_blocked",
        "--selection-path",
        selection_path.relative_to(workspace).as_posix(),
        "--reason",
        "selector_blocked",
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert all(entry.get("event") != "run_blocked" for entry in state["history"])
    assert state["blocked_run"]["reason"] == "no_forward_progress"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "BLOCKED"


def test_update_run_state_skips_blocked_run_for_continue_step_back_placeholder_bundle(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    selection_path = workspace / "state/drain/blocked-step-back.json"
    drain_status_path = workspace / "state/drain/drain-status.txt"
    state_path.parent.mkdir(parents=True)
    selection_path.write_text(
        json.dumps(
            {
                "pre_selection_route": "BLOCKED",
                "recovery_route": "TERMINAL_BLOCKED",
                "recovery_reason": "workflow made no forward progress across iterations",
                "recovery_status": "STEP_BACK_RECORDED",
                "block_reason": "no_forward_progress",
                "step_back_action": "CONTINUE_WITH_CURRENT_PLAN",
                "step_back_drain_status": "CONTINUE",
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
        "run_blocked",
        "--selection-path",
        selection_path.relative_to(workspace).as_posix(),
        "--reason",
        "selector_blocked",
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["blocked_run"] is None
    assert all(entry.get("event") != "run_blocked" for entry in state["history"])


def test_step_back_blocked_run_state_resolves_blocked_drain_status_without_raising(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    decision_path = workspace / "state/drain/step-back-decision.json"
    diagnosis_path = workspace / "state/drain/step-back-diagnosis.json"
    summary_path = workspace / "state/drain/step-back-summary.json"
    step_back_status_path = workspace / "state/drain/step-back-status.txt"
    pre_selection_path = workspace / "state/drain/pre-selection.json"
    drain_status_path = workspace / "state/drain/drain-status.txt"
    resolved_status_path = workspace / "state/drain/resolved-status.txt"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "blocked_run": None,
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision_path.write_text(
        json.dumps(
            {
                "route": "STEP_BACK",
                "trigger_codes": ["NO_FORWARD_PROGRESS"],
                "failure_fingerprint": "no_forward_progress",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    diagnosis_path.write_text(
        json.dumps(
            {
                "action": "NEEDS_HUMAN_DECISION",
                "rationale": "The workflow made no forward progress across iterations.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/record_workflow_step_back_outcome.py"),
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "--decision-path",
        decision_path.relative_to(workspace).as_posix(),
        "--diagnosis-path",
        diagnosis_path.relative_to(workspace).as_posix(),
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        step_back_status_path.relative_to(workspace).as_posix(),
        "--pre-selection-output",
        pre_selection_path.relative_to(workspace).as_posix(),
        "--iteration",
        "1",
    )

    assert step_back_status_path.read_text(encoding="utf-8").strip() == "BLOCKED"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/update_lisp_frontend_run_state.py"),
        "--state-path",
        state_path.relative_to(workspace).as_posix(),
        "run_blocked",
        "--selection-path",
        pre_selection_path.relative_to(workspace).as_posix(),
        "--reason",
        "selector_blocked",
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py"),
        "--pre-selection-bundle-path",
        pre_selection_path.relative_to(workspace).as_posix(),
        "--normal-status-path",
        "state/drain/missing-normal.txt",
        "--recovery-record-status-path",
        "state/drain/missing-recovery.txt",
        "--recovered-work-item-status-path",
        "state/drain/missing-recovered.txt",
        "--prerequisite-recovery-status-path",
        "state/drain/missing-prerequisite.txt",
        "--step-back-status-path",
        step_back_status_path.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--output",
        resolved_status_path.relative_to(workspace).as_posix(),
    )

    assert resolved_status_path.read_text(encoding="utf-8").strip() == "BLOCKED"


def test_blocked_implementation_prompts_reserve_user_decision_for_terminal_categories():
    prompt_paths = [
        ROOT / "workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md",
        ROOT / "workflows/library/prompts/lisp_frontend_implementation_phase/implement_plan.md",
        ROOT / "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md",
    ]

    for path in prompt_paths:
        prompt = path.read_text(encoding="utf-8").lower()
        assert "user_decision_required" in prompt
        assert "repo-local" in prompt
        assert "prerequisite" in prompt
        assert "target design" in prompt
        assert "environment" in prompt or "access" in prompt or "credential" in prompt


def test_record_recovered_retry_unavailable_keeps_blocked_reason_visible(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    bundle = workspace / "state/drain/pre-selection.json"
    recovery_status = workspace / "state/drain/recovery-status.txt"
    output = workspace / "state/drain/retry-availability.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bundle.write_text(
        json.dumps({"pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP", "design_gap_id": "parser-syntax"}) + "\n",
        encoding="utf-8",
    )
    recovery_status.write_text("RUN_RECOVERED_GAP\n", encoding="utf-8")

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/record_lisp_frontend_recovered_retry_unavailable.py"),
        "--pre-selection-bundle-path",
        bundle.relative_to(workspace).as_posix(),
        "--recovery-record-status-path",
        recovery_status.relative_to(workspace).as_posix(),
        "--recovered-work-item-status-path",
        "state/drain/missing-recovered-status.txt",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert payload["record_status"] == "BLOCKED_RECORDED"
    assert blocked["reason"] == "implementation_blocked"
    assert blocked["retry_block_reason"] == "recovered_retry_status_missing"
    assert state["history"][-1]["event"] == "recovered_retry_unavailable"
    assert state["history"][-1]["reason"] == "recovered_retry_status_missing"


def test_record_recovered_retry_unavailable_preserves_invalid_recovered_architecture_reason(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    bundle = workspace / "state/drain/pre-selection.json"
    recovery_status = workspace / "state/drain/recovery-status.txt"
    recovered_status = workspace / "state/drain/recovered-gap/work-item/drain_status.txt"
    validation = workspace / "state/drain/recovered-gap/architecture-validation.json"
    output = workspace / "state/drain/retry-availability.json"
    state_path.parent.mkdir(parents=True)
    validation.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bundle.write_text(
        json.dumps({"pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP", "design_gap_id": "parser-syntax"}) + "\n",
        encoding="utf-8",
    )
    recovery_status.write_text("RUN_RECOVERED_GAP\n", encoding="utf-8")
    validation.write_text(
        json.dumps(
            {
                "architecture_validation_status": "INVALID",
                "reason": "durable design-gap document contains generated run-scoped path",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/record_lisp_frontend_recovered_retry_unavailable.py"),
        "--pre-selection-bundle-path",
        bundle.relative_to(workspace).as_posix(),
        "--recovery-record-status-path",
        recovery_status.relative_to(workspace).as_posix(),
        "--recovered-work-item-status-path",
        recovered_status.relative_to(workspace).as_posix(),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    blocked = state["blocked_design_gaps"]["parser-syntax"]
    assert payload["record_status"] == "BLOCKED_RECORDED"
    assert blocked["retry_block_reason"] == "recovered_architecture_invalid"
    assert blocked["retry_block_detail"] == "durable design-gap document contains generated run-scoped path"
    assert blocked["recovered_architecture_validation_path"] == validation.relative_to(workspace).as_posix()
    assert state["history"][-1]["reason"] == "recovered_architecture_invalid"


def test_record_recovered_retry_unavailable_uses_recovered_child_output_value(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    bundle = workspace / "state/drain/pre-selection.json"
    recovery_status = workspace / "state/drain/recovery-status.txt"
    output = workspace / "state/drain/retry-availability.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                    }
                },
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bundle.write_text(
        json.dumps({"pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP", "design_gap_id": "parser-syntax"}) + "\n",
        encoding="utf-8",
    )
    recovery_status.write_text("RUN_RECOVERED_GAP\n", encoding="utf-8")

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/record_lisp_frontend_recovered_retry_unavailable.py"),
        "--pre-selection-bundle-path",
        bundle.relative_to(workspace).as_posix(),
        "--recovery-record-status-path",
        recovery_status.relative_to(workspace).as_posix(),
        "--recovered-work-item-status-path",
        "state/drain/private-child-status-not-published.txt",
        "--recovered-work-item-status-value",
        "CONTINUE",
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["record_status"] == "RETRY_STATUS_AVAILABLE"
    assert "retry_block_reason" not in state["blocked_design_gaps"]["parser-syntax"]
    assert state["history"] == []


def test_detect_blocked_recovery_uses_recovered_architecture_validation_report_instead_of_stale_progress(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    artifact_root = workspace / "artifacts/work"
    architecture_root = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps"
    architecture = architecture_root / "parser-syntax/implementation_architecture.md"
    plan = architecture_root / "parser-syntax/execution_plan.md"
    output = workspace / "state/drain/iterations/0/blocked-recovery.json"
    validation = workspace / "state/drain/iterations/0/recovered-gap/architecture-validation.json"
    for path in (state_path, architecture, plan, validation):
        path.parent.mkdir(parents=True, exist_ok=True)
    architecture.write_text("# Parser Syntax Architecture\n", encoding="utf-8")
    plan.write_text("# Parser Syntax Plan\n", encoding="utf-8")
    validation.write_text('{"architecture_validation_status":"INVALID"}\n', encoding="utf-8")
    state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                        "architecture_path": architecture.relative_to(workspace).as_posix(),
                        "plan_path": plan.relative_to(workspace).as_posix(),
                        "implementation_state_path": "state/workflow_lisp/calls/test/implementation_state.json",
                        "retry_block_reason": "recovered_architecture_invalid",
                        "retry_block_detail": "durable design-gap document contains generated run-scoped path",
                        "recovered_architecture_validation_path": validation.relative_to(workspace).as_posix(),
                    }
                },
                "blocked_run": None,
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py"),
        "--run-state-path",
        state_path.relative_to(workspace).as_posix(),
        "--artifact-work-root",
        artifact_root.relative_to(workspace).as_posix(),
        "--architecture-index-root",
        architecture_root.relative_to(workspace).as_posix(),
        "--output",
        output.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    copied_progress = output.with_name("blocked-progress-report.md").read_text(encoding="utf-8")
    assert payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
    assert payload["blocker_class"] == "recovery_validation"
    assert payload["progress_report_path"] == output.with_name("blocked-progress-report.md").relative_to(workspace).as_posix()
    assert "durable design-gap document contains generated run-scoped path" in copied_progress
    assert "Stale implementation blocker" not in copied_progress


def _assert_gap_architect_review_loop(workflow: dict, *, draft_provider_routing: bool) -> None:
    step_names = [step["name"] for step in workflow["steps"]]
    expected_prefix = ["PrepareArchitectureTargets", "BuildExistingArchitectureIndex"]
    if draft_provider_routing:
        expected_prefix.append("ValidateDesignGapDraftProviderRouting")
    assert step_names == [
        *expected_prefix,
        "DraftDesignGapArchitecture",
        "DesignGapArchitectureReviewLoop",
        "ValidateDesignGapArchitecture",
    ]
    review_loop = next(step for step in workflow["steps"] if step["name"] == "DesignGapArchitectureReviewLoop")
    repeat = review_loop["repeat_until"]
    assert repeat["max_iterations"] == 3
    condition_values = [
        predicate["compare"]["right"]
        for predicate in repeat["condition"]["any_of"]
    ]
    assert condition_values == ["APPROVE", "BLOCKED"]
    nested_names = [step["name"] for step in repeat["steps"]]
    assert nested_names == ["ReviewDesignGapArchitecture", "RouteDesignGapArchitectureReview"]

    review_step = repeat["steps"][0]
    assert "provider" in review_step
    assert "review_implementation_architecture.md" in json.dumps(review_step)
    review_fields = {field["name"]: field for field in review_step["output_bundle"]["fields"]}
    assert review_fields["review_decision"]["allowed"] == ["APPROVE", "REVISE", "BLOCKED"]
    assert review_step["output_bundle"]["path"].endswith("/architecture-review.json")
    assert (
        "${parent.steps.PrepareArchitectureTargets.artifacts.architecture_path}"
        in review_step["depends_on"]["required"]
    )
    if draft_provider_routing:
        assert review_step["provider"] == "${parent.steps.ValidateDesignGapDraftProviderRouting.artifacts.provider}"
        assert review_step["provider_params"]["model"] == (
            "${parent.steps.ValidateDesignGapDraftProviderRouting.artifacts.model}"
        )
        assert review_step["provider_params"]["effort"] == (
            "${parent.steps.ValidateDesignGapDraftProviderRouting.artifacts.effort}"
        )

    route = repeat["steps"][1]
    cases = route["match"]["cases"]
    assert set(cases) == {"APPROVE", "REVISE", "BLOCKED"}
    assert "ReviseDesignGapArchitecture" in json.dumps(cases["REVISE"])
    revise_step = next(step for step in cases["REVISE"]["steps"] if step["name"] == "ReviseDesignGapArchitecture")
    for artifact_name in ("architecture_path", "work_item_context_path", "check_commands_path"):
        assert (
            f"${{parent.steps.PrepareArchitectureTargets.artifacts.{artifact_name}}}"
            in revise_step["depends_on"]["required"]
        )
    if draft_provider_routing:
        assert revise_step["provider"] == "${parent.steps.ValidateDesignGapDraftProviderRouting.artifacts.provider}"
        assert revise_step["provider_params"]["model"] == (
            "${parent.steps.ValidateDesignGapDraftProviderRouting.artifacts.model}"
        )
        assert revise_step["provider_params"]["effort"] == (
            "${parent.steps.ValidateDesignGapDraftProviderRouting.artifacts.effort}"
        )

    validator = next(step for step in workflow["steps"] if step["name"] == "ValidateDesignGapArchitecture")
    command = validator["command"]
    assert "--review-bundle-path" in command
    review_arg_index = command.index("--review-bundle-path") + 1
    assert command[review_arg_index] == "${inputs.state_root}/architecture-review.json"


def test_design_gap_architect_reviews_gap_design_consistency_before_validation():
    workflow = yaml.safe_load((ROOT / "workflows/library/lisp_frontend_design_gap_architect.v214.yaml").read_text())

    _assert_gap_architect_review_loop(workflow, draft_provider_routing=False)
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


def test_design_delta_gap_architect_reviews_gap_design_consistency_before_validation():
    workflow = yaml.safe_load(
        (ROOT / "workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml").read_text()
    )

    _assert_gap_architect_review_loop(workflow, draft_provider_routing=True)


def test_design_delta_gap_architect_uses_supported_claude_default():
    workflow = yaml.safe_load(
        (ROOT / "workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml").read_text()
    )
    step_names = [step["name"] for step in workflow["steps"]]

    assert step_names == [
        "PrepareArchitectureTargets",
        "BuildExistingArchitectureIndex",
        "ValidateDesignGapDraftProviderRouting",
        "DraftDesignGapArchitecture",
        "DesignGapArchitectureReviewLoop",
        "ValidateDesignGapArchitecture",
    ]
    assert workflow["inputs"]["design_gap_draft_provider"]["default"] == "codex"
    assert workflow["inputs"]["design_gap_draft_model"]["default"] == "gpt-5.5"
    assert workflow["providers"]["claude"]["defaults"]["model"] == "fable"

    validate_step = next(
        step for step in workflow["steps"] if step["name"] == "ValidateDesignGapDraftProviderRouting"
    )
    validator_source = validate_step["command"][2]

    assert 'model not in {"opus", "fable", "claude-fable-5"}' in validator_source
    assert "design-gap drafting via Claude must use a supported Claude model alias" in validator_source


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
    assert "Read the consumed steering, target design, baseline design" not in prompt
    assert "Return `DONE` only when the target design" in prompt
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


def test_blocked_implementation_recovery_prompt_keeps_roles_clear():
    path = ROOT / "workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md"
    text = path.read_text(encoding="utf-8")
    lower = text.lower()

    assert "GAP_DESIGN_REVISION_REQUIRED" in text
    assert "TARGET_DESIGN_REVISION_REQUIRED" in text
    assert "PREREQUISITE_GAP_REQUIRED" in text
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


def test_design_delta_work_item_records_blocked_implementation_for_drain_recovery():
    workflow = yaml.safe_load((ROOT / "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml").read_text())

    assert workflow["imports"] == {
        "plan_phase": "./lisp_frontend_design_delta_plan_phase.v214.yaml",
        "implementation_phase": "./lisp_frontend_design_delta_implementation_phase.v214.yaml",
    }
    classifier = next(step for step in workflow["steps"] if step["name"] == "ClassifyWorkItemTerminal")
    assert "--implementation-bundle-path" in classifier["command"]
    assert "--work-item-source" in classifier["command"]
    assert "${steps.RunImplementationPhase.artifacts.implementation_state}" in classifier["command"]
    assert "${steps.RunImplementationPhase.artifacts.implementation_review_decision}" in classifier["command"]
    assert not any(
        "${steps.ResolveWorkItemInputs.artifacts.implementation_phase_state_root}/" in part
        for part in classifier["command"]
    )

    recovery_classifier = next(step for step in workflow["steps"] if step["name"] == "ClassifyBlockedImplementationRecovery")
    assert recovery_classifier["asset_file"] == (
        "prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md"
    )
    assert recovery_classifier["output_capture"] == "json"
    assert recovery_classifier["output_file"] == (
        "${inputs.state_root}/blocked-implementation-recovery.stdout.json"
    )
    required = recovery_classifier["depends_on"]["required"]
    assert "${steps.RunPlanPhase.artifacts.plan_path}" in required
    assert "${steps.RunImplementationPhase.artifacts.implementation_state_bundle_path}" in required
    assert "${steps.ResolveWorkItemInputs.artifacts.progress_report_target_path}" in required
    assert not any(
        "${inputs.state_root}/implementation-phase/" in part
        for part in required
    )
    assert "output_bundle" not in recovery_classifier
    recovery_bundle_writer = next(
        step for step in workflow["steps"] if step["name"] == "WriteBlockedImplementationRecoveryBundle"
    )
    assert any(
        part.endswith("materialize_lisp_frontend_blocked_recovery_bundle.py")
        for part in recovery_bundle_writer["command"]
    )
    assert "${inputs.state_root}/blocked-implementation-recovery.stdout.json" in recovery_bundle_writer["command"]
    assert recovery_bundle_writer["output_bundle"]["path"] == (
        "${inputs.state_root}/blocked-implementation-recovery.json"
    )
    recovery_selector = next(step for step in workflow["steps"] if step["name"] == "SelectBlockedRecoveryRoute")
    assert any(part.endswith("select_lisp_frontend_blocked_recovery_route.py") for part in recovery_selector["command"])

    route_terminal = next(step for step in workflow["steps"] if step["name"] == "RouteWorkItemTerminal")
    terminal = route_terminal["match"]["cases"]["IMPLEMENTATION_BLOCKED"]
    recorder = next(step for step in terminal["steps"] if step["name"] == "RecordBlockedRecoveryOutcome")
    assert any(part.endswith("record_lisp_frontend_blocked_recovery_outcome.py") for part in recorder["command"])
    assert "--recovery-bundle-path" in recorder["command"]
    assert "${inputs.state_root}/blocked-implementation-recovery.json" in recorder["command"]
    assert "${steps.SelectBlockedRecoveryRoute.artifacts.blocked_recovery_route}" in recorder["command"]
    assert "${steps.ResolveWorkItemInputs.artifacts.progress_report_target_path}" in recorder["command"]
    assert "${steps.RunImplementationPhase.artifacts.implementation_state_bundle_path}" in recorder["command"]
    assert "ReviewTargetDesignRevisionLoop" not in json.dumps(terminal)
    assert "continue" in recorder["command"]


def test_design_delta_drain_checks_blocked_recovery_before_selection():
    workflow = yaml.safe_load((ROOT / "workflows/examples/lisp_frontend_design_delta_drain.yaml").read_text())
    workflow_text = (ROOT / "workflows/examples/lisp_frontend_design_delta_drain.yaml").read_text(encoding="utf-8")
    for prior_name in [
        "RoutePriorBlockedDesignGapRecovery",
        "ClassifyPriorBlockedImplementationRecovery",
        "RevisePriorBlockedDesignGap",
        "ReviewPriorBlockedDesignRevision",
        "PrepareRecoveredPriorBlockedGapWorkItem",
        "RunRecoveredPriorBlockedGapWorkItem",
    ]:
        assert prior_name not in workflow_text

    drain = next(step for step in workflow["steps"] if step["name"] == "DrainLispFrontendWork")
    repeat_steps = drain["repeat_until"]["steps"]
    repeat_names = [step["name"] for step in repeat_steps]

    assert "DetectBlockedDesignGapRecovery" in repeat_names
    assert repeat_names.index("DetectBlockedDesignGapRecovery") < repeat_names.index("SelectNextWork")
    assert repeat_names.index("DetectBlockedDesignGapRecovery") < repeat_names.index("ClassifyBlockedImplementationRecovery")
    assert repeat_names[-1] == "ResolveIterationDrainStatus"

    selector = next(step for step in repeat_steps if step["name"] == "SelectNextWork")
    selector_cases = selector["match"]["cases"]
    normal_case_names = [step["name"] for step in selector_cases["SELECT_NORMAL_WORK"]["steps"]]
    assert "ClearSelectorControlManifest" in normal_case_names
    assert any(step["name"] == "RunNormalSelector" for step in selector_cases["SELECT_NORMAL_WORK"]["steps"])
    assert normal_case_names.index("ClearSelectorControlManifest") < normal_case_names.index("RunNormalSelector")
    clear_control = next(
        step for step in selector_cases["SELECT_NORMAL_WORK"]["steps"]
        if step["name"] == "ClearSelectorControlManifest"
    )
    assert any(part.endswith("remove_lisp_frontend_private_artifact.py") for part in clear_control["command"])
    assert "${inputs.drain_state_root}/iterations/${loop.index}/selector-control-manifest.json" in clear_control["command"]
    normal_selector = next(step for step in selector_cases["SELECT_NORMAL_WORK"]["steps"] if step["name"] == "RunNormalSelector")
    assert "run_state_path" not in normal_selector["with"]
    assert "progress_ledger_path" not in normal_selector["with"]
    assert "post_wcc_inventory_path" not in normal_selector["with"]
    done_review_case = selector_cases["SELECT_DONE_REVIEW"]
    done_review_names = [step["name"] for step in done_review_case["steps"]]
    assert done_review_names == ["WriteDoneReviewSelection", "PublishDoneReviewSelectionBundle"]
    assert all(step["name"] != "RunNormalSelector" for step in done_review_case["steps"])
    assert any(
        step["name"] == "WritePrerequisiteRecoverySelection"
        for step in selector_cases["SELECT_PREREQUISITE_WORK"]["steps"]
    )

    prerequisite_selector = next(
        step for step in selector_cases["SELECT_PREREQUISITE_WORK"]["steps"]
        if step["name"] == "WritePrerequisiteRecoverySelection"
    )
    assert any(part.endswith("write_lisp_frontend_prerequisite_selection.py") for part in prerequisite_selector["command"])
    for placeholder in ["RECOVER_BLOCKED_DESIGN_GAP", "BLOCKED"]:
        assert any(
            step["name"] == "WriteSelectorBlockedPlaceholder"
            for step in selector_cases[placeholder]["steps"]
        )
    recover = {step["name"]: step for step in repeat_steps}

    classifier = recover["ClassifyBlockedImplementationRecovery"]
    assert classifier["input_file"] == (
        "workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md"
    )
    assert json.dumps(classifier["when"]).count("RETRY_READY") == 1
    reviser = recover["ReviseBlockedDesignGap"]
    assert _condition_has_pre_selection_recovery_guard(reviser["when"])
    route_values = [
        predicate["compare"]["right"]
        for clause in reviser["when"]["all_of"]
        if "any_of" in clause
        for predicate in clause["any_of"]
    ]
    assert route_values == [
        "TARGET_DESIGN_REVISION_REQUIRED",
        "GAP_DESIGN_REVISION_REQUIRED",
    ]
    assert "PREREQUISITE_GAP_REQUIRED" not in json.dumps(recover["ReviewBlockedTargetDesignRevision"]["when"])
    assert "PREREQUISITE_GAP_REQUIRED" not in json.dumps(recover["WriteBlockedDesignRevisionDecision"]["when"])
    assert "${inputs.drain_state_root}/iterations/${loop.index}/blocked-recovery-decision.json" in reviser["depends_on"]["required"]
    assert "${inputs.drain_state_root}/iterations/${loop.index}/blocked-gap-architecture.md" in reviser["depends_on"]["required"]
    assert "${inputs.drain_state_root}/iterations/${loop.index}/blocked-gap-execution-plan.md" in reviser["depends_on"]["required"]
    materializer = recover["MaterializeRecoveredBlockedGapDraft"]
    assert any(part.endswith("materialize_lisp_frontend_recovered_design_gap_draft.py") for part in materializer["command"])
    validator = recover["ValidateRecoveredBlockedGapArchitecture"]
    assert any(part.endswith("validate_lisp_frontend_design_gap_architecture.py") for part in validator["command"])
    recorder = recover["RecordBlockedRecoveryOutcome"]
    assert any(part.endswith("record_lisp_frontend_blocked_recovery_outcome.py") for part in recorder["command"])
    assert json.dumps(recorder["when"]).count("RETRY_READY") == 1
    retry_ready = recover["RecordPrerequisiteRetryReadyOutcome"]
    assert any(part.endswith("write_lisp_frontend_recovery_status.py") for part in retry_ready["command"])
    assert "RUN_RECOVERED_GAP" in retry_ready["command"]
    prerequisite_recorder = recover["RecordPrerequisiteRecoveryOutcome"]
    assert any(
        part.endswith("record_lisp_frontend_prerequisite_recovery_outcome.py")
        for part in prerequisite_recorder["command"]
    )
    assert prerequisite_recorder["when"]["compare"]["right"] == "SELECT_PREREQUISITE_WORK"
    prerequisite_output = prerequisite_recorder["output_bundle"]
    record_status_field = next(
        field for field in prerequisite_output["fields"] if field["name"] == "prerequisite_recovery_record_status"
    )
    assert record_status_field["allowed"] == [
        "RETRY_READY",
        "WAITING_ON_RECOVERABLE_PREREQUISITE",
        "RECOVERY_CONTINUES",
    ]
    drain_status_field = next(
        field for field in prerequisite_output["fields"] if field["name"] == "prerequisite_recovery_drain_status"
    )
    assert drain_status_field["allowed"] == ["CONTINUE"]
    assert repeat_names.index("WriteNormalIterationStatus") < repeat_names.index("RecordPrerequisiteRecoveryOutcome")
    assert repeat_names.index("RecordPrerequisiteRecoveryOutcome") < repeat_names.index("ResolveIterationDrainStatus")
    resolver = recover["ResolveIterationDrainStatus"]
    assert "--prerequisite-recovery-status-path" in resolver["command"]
    for step_name in [
        "ClassifyBlockedImplementationRecovery",
        "ReviseBlockedDesignGap",
        "PrepareBlockedDesignRevisionReviewReportPath",
        "ReviewBlockedTargetDesignRevision",
        "ValidateBlockedDesignRevisionReviewReportPath",
        "WriteBlockedDesignRevisionDecision",
        "RecordBlockedRecoveryOutcome",
        "RecordPrerequisiteRetryReadyOutcome",
        "MaterializeRecoveredBlockedGapDraft",
        "ValidateRecoveredBlockedGapArchitecture",
        "PrepareRecoveredBlockedGapWorkItem",
        "RunRecoveredBlockedGapWorkItem",
        "MaterializeRecoveredWorkItemStatus",
        "RecordRecoveredRetryUnavailable",
    ]:
        assert _condition_has_pre_selection_recovery_guard(recover[step_name]["when"]), step_name
    retry_unavailable = recover["RecordRecoveredRetryUnavailable"]
    assert any(part.endswith("record_lisp_frontend_recovered_retry_unavailable.py") for part in retry_unavailable["command"])
    assert "depends_on" not in retry_unavailable
    assert "--recovered-work-item-status-value" not in retry_unavailable["command"]
    assert "RunRecoveredBlockedGapWorkItem.artifacts.drain_status" not in json.dumps(retry_unavailable["command"])
    materializer_condition = json.dumps(recover["MaterializeRecoveredBlockedGapDraft"]["when"])
    assert "RETRY_READY" in materializer_condition
    assert "RecordBlockedRecoveryOutcome.artifacts.recovery_drain_status" in materializer_condition
    recovered_status_materializer = recover["MaterializeRecoveredWorkItemStatus"]
    recovered_status_materializer_condition = json.dumps(recovered_status_materializer["when"])
    assert "ValidateRecoveredBlockedGapArchitecture.artifacts.architecture_validation_status" in (
        recovered_status_materializer_condition
    )
    assert "\"VALID\"" in recovered_status_materializer_condition
    for step_name in [
        "MaterializeRecoveredBlockedGapDraft",
        "ValidateRecoveredBlockedGapArchitecture",
        "PrepareRecoveredBlockedGapWorkItem",
        "RunRecoveredBlockedGapWorkItem",
        "MaterializeRecoveredWorkItemStatus",
        "RecordRecoveredRetryUnavailable",
    ]:
        assert _condition_has_recovered_retry_request_guard(recover[step_name]["when"]), step_name
    status_materializer = recover["MaterializeRecoveredWorkItemStatus"]
    assert any(part.endswith("write_lisp_frontend_drain_status.py") for part in status_materializer["command"])
    assert "RunRecoveredBlockedGapWorkItem.artifacts.drain_status" in json.dumps(status_materializer["command"])
    assert (
        repeat_names.index("RunRecoveredBlockedGapWorkItem")
        < repeat_names.index("MaterializeRecoveredWorkItemStatus")
        < repeat_names.index("RecordRecoveredRetryUnavailable")
    )
    resolver = recover["ResolveIterationDrainStatus"]
    assert "--recovered-work-item-status-value" not in resolver["command"]
    assert "RunRecoveredBlockedGapWorkItem.artifacts.drain_status" not in json.dumps(resolver["command"])


def test_prerequisite_boundary_workflow_route():
    workflow = yaml.safe_load((ROOT / "workflows/examples/lisp_frontend_design_delta_drain.yaml").read_text(encoding="utf-8"))
    repeat_steps = list(_iter_workflow_steps(workflow["steps"]))
    recover = {step["name"]: step for step in repeat_steps}
    reviser = recover["ReviseBlockedDesignGap"]
    route_values = [
        predicate["compare"]["right"]
        for clause in reviser["when"]["all_of"]
        if "any_of" in clause
        for predicate in clause["any_of"]
    ]
    assert "PREREQUISITE_GAP_REQUIRED" not in route_values
    assert "PREREQUISITE_GAP_REQUIRED" not in json.dumps(recover["ReviewBlockedTargetDesignRevision"]["when"])
    assert "PREREQUISITE_GAP_REQUIRED" not in json.dumps(recover["WriteBlockedDesignRevisionDecision"]["when"])


def test_blocked_target_design_revision_review_report_path_is_command_owned():
    workflow = yaml.safe_load((ROOT / "workflows/examples/lisp_frontend_design_delta_drain.yaml").read_text())
    drain = next(step for step in workflow["steps"] if step["name"] == "DrainLispFrontendWork")
    repeat_steps = drain["repeat_until"]["steps"]
    names = [step["name"] for step in repeat_steps]

    assert names.index("PrepareBlockedDesignRevisionReviewReportPath") < names.index(
        "ReviewBlockedTargetDesignRevision"
    )
    assert names.index("ReviewBlockedTargetDesignRevision") < names.index(
        "ValidateBlockedDesignRevisionReviewReportPath"
    )

    prepare = next(step for step in repeat_steps if step["name"] == "PrepareBlockedDesignRevisionReviewReportPath")
    assert any(part.endswith("write_lisp_frontend_relpath_value.py") for part in prepare["command"])
    assert "${inputs.artifact_review_root}/blocked-design-revision-iteration-${loop.index}-review.json" in prepare[
        "command"
    ]
    prepared_output = prepare["expected_outputs"][0]
    assert prepared_output == {
        "name": "design_revision_review_report_path",
        "path": "${inputs.drain_state_root}/iterations/${loop.index}/blocked-design-revision-review-target-path.txt",
        "type": "relpath",
        "under": "artifacts/review",
        "must_exist_target": False,
    }

    review = next(step for step in repeat_steps if step["name"] == "ReviewBlockedTargetDesignRevision")
    assert "${inputs.drain_state_root}/iterations/${loop.index}/blocked-design-revision-review-target-path.txt" in (
        review["depends_on"]["required"]
    )
    assert [output["name"] for output in review["expected_outputs"]] == ["design_revision_review_decision"]

    validate = next(step for step in repeat_steps if step["name"] == "ValidateBlockedDesignRevisionReviewReportPath")
    assert any(part.endswith("write_lisp_frontend_relpath_value.py") for part in validate["command"])
    assert "${steps.PrepareBlockedDesignRevisionReviewReportPath.artifacts.design_revision_review_report_path}" in (
        validate["command"]
    )
    validated_output = validate["expected_outputs"][0]
    assert validated_output == {
        "name": "design_revision_review_report_path",
        "path": "${inputs.drain_state_root}/iterations/${loop.index}/blocked-design-revision-review-report-path.txt",
        "type": "relpath",
        "under": "artifacts/review",
        "must_exist_target": True,
    }


def _condition_has_pre_selection_recovery_guard(condition: dict) -> bool:
    if not isinstance(condition, dict):
        return False
    compare = condition.get("compare")
    if isinstance(compare, dict):
        left = compare.get("left")
        return (
            isinstance(left, dict)
            and left.get("ref") == "self.steps.DetectBlockedDesignGapRecovery.artifacts.pre_selection_route"
            and compare.get("op") == "eq"
            and compare.get("right") == "RECOVER_BLOCKED_DESIGN_GAP"
        )
    return any(
        _condition_has_pre_selection_recovery_guard(child)
        for key in ("all_of", "any_of")
        for child in condition.get(key, [])
    )


def _condition_has_recovered_retry_request_guard(condition: dict) -> bool:
    if not isinstance(condition, dict):
        return False
    compare = condition.get("compare")
    if isinstance(compare, dict):
        left = compare.get("left")
        if (
            isinstance(left, dict)
            and left.get("ref") == "self.steps.DetectBlockedDesignGapRecovery.artifacts.recovery_status"
            and compare.get("op") == "eq"
            and compare.get("right") == "RETRY_READY"
        ):
            return True
        if (
            isinstance(left, dict)
            and left.get("ref") == "self.steps.RecordBlockedRecoveryOutcome.artifacts.recovery_drain_status"
            and compare.get("op") == "eq"
            and compare.get("right") == "RUN_RECOVERED_GAP"
        ):
            return True
    return any(
        _condition_has_recovered_retry_request_guard(child)
        for key in ("all_of", "any_of")
        for child in condition.get(key, [])
    )
    assert "${inputs.drain_state_root}/iterations/${loop.index}/blocked-recovery-decision.json" in recorder["command"]
    assert "${inputs.drain_state_root}/iterations/${loop.index}/blocked-design-revision-report.json" in recorder["command"]
    assert "continue" in recorder["command"]

    recovered = recover["RunRecoveredBlockedGapWorkItem"]
    assert recovered["call"] == "work_item"
    assert recovered["with"]["architecture_bundle_path"]["ref"] == (
        "self.steps.PrepareRecoveredBlockedGapWorkItem.artifacts.architecture_bundle_path"
    )


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


def test_design_delta_drain_done_route_requires_terminal_review_gate():
    workflow = yaml.safe_load((ROOT / "workflows/examples/lisp_frontend_design_delta_drain.yaml").read_text())
    assert workflow["imports"]["done_review"] == "../library/lisp_frontend_design_delta_done_review.v214.yaml"
    post_wcc_input = workflow["inputs"]["post_wcc_inventory_path"]
    assert post_wcc_input["default"] == (
        "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json"
    )
    done_review_provider_input = workflow["inputs"]["done_review_provider"]
    assert done_review_provider_input["allowed"] == ["codex", "claude_opus"]
    assert done_review_provider_input["default"] == "codex"
    drain_step = next(step for step in workflow["steps"] if step["name"] == "DrainLispFrontendWork")
    prepare = next(step for step in drain_step["repeat_until"]["steps"] if step["name"] == "PrepareIterationPaths")
    prepare_fields = {field["name"]: field for field in prepare["output_bundle"]["fields"]}
    assert "done_review_state_root" in prepare_fields
    assert "done_review_design_gap_architect_state_root" in prepare_fields
    assert "done_review_design_gap_work_item_state_root" in prepare_fields

    route_selection = next(step for step in drain_step["repeat_until"]["steps"] if step["name"] == "RouteSelection")
    done_case = route_selection["match"]["cases"]["DONE"]
    assert done_case["outputs"]["drain_status"]["from"]["ref"] == "self.steps.RunDoneReview.artifacts.drain_status"
    done_step_names = [step["name"] for step in done_case["steps"]]
    assert done_step_names == ["RunDoneReview"]

    done_call = done_case["steps"][0]
    assert done_call["call"] == "done_review"
    assert done_call["with"]["selection_bundle_path"]["ref"] == "parent.steps.SelectNextWork.artifacts.selection_bundle_path"
    assert done_call["with"]["post_wcc_inventory_path"]["ref"] == "inputs.post_wcc_inventory_path"
    assert done_call["with"]["done_review_provider"]["ref"] == "inputs.done_review_provider"
    assert done_call["with"]["state_root"]["ref"] == (
        "parent.steps.PrepareIterationPaths.artifacts.done_review_state_root"
    )
    assert done_call["with"]["design_gap_architect_state_root"]["ref"] == (
        "parent.steps.PrepareIterationPaths.artifacts.done_review_design_gap_architect_state_root"
    )
    assert done_call["with"]["design_gap_work_item_state_root"]["ref"] == (
        "parent.steps.PrepareIterationPaths.artifacts.done_review_design_gap_work_item_state_root"
    )

    done_workflow = yaml.safe_load(
        (ROOT / "workflows/library/lisp_frontend_design_delta_done_review.v214.yaml").read_text()
    )
    assert done_workflow["inputs"]["post_wcc_inventory_path"]["under"] == "docs/plans"
    done_review_provider_input = done_workflow["inputs"]["done_review_provider"]
    assert done_review_provider_input["allowed"] == ["codex", "claude_opus"]
    assert done_review_provider_input["default"] == "codex"
    review = next(step for step in done_workflow["steps"] if step["name"] == "ReviewDoneDecision")
    assert review["provider"] == "${inputs.done_review_provider}"
    assert review["asset_file"] == "prompts/lisp_frontend_selector/review_done_design_delta.md"
    assert "${inputs.post_wcc_inventory_path}" in review["depends_on"]["required"]
    review_fields = {field["name"]: field for field in review["output_bundle"]["fields"]}
    assert review_fields["done_decision"]["allowed"] == ["APPROVE_DONE", "REJECT_DONE"]

    projection = next(step for step in done_workflow["steps"] if step["name"] == "ProjectDoneReview")
    assert any(part.endswith("project_lisp_frontend_done_review.py") for part in projection["command"])
    assert "--original-selection-path" in projection["command"]
    projection_fields = {field["name"]: field for field in projection["output_bundle"]["fields"]}
    assert projection_fields["selection_status"]["allowed"] == ["DONE", "DRAFT_DESIGN_GAP"]

    done_review_route = next(step for step in done_workflow["steps"] if step["name"] == "RouteDoneReview")
    nested_cases = done_review_route["match"]["cases"]
    assert set(nested_cases) == {"DONE", "DRAFT_DESIGN_GAP"}
    assert [step["name"] for step in nested_cases["DONE"]["steps"]] == ["WriteDone"]
    assert [step["name"] for step in nested_cases["DRAFT_DESIGN_GAP"]["steps"]] == [
        "DraftDoneRejectedDesignGapArchitecture",
        "RunDoneRejectedDesignGapWorkItem",
    ]
    rejected_architect = nested_cases["DRAFT_DESIGN_GAP"]["steps"][0]
    assert rejected_architect["with"]["selection_bundle_path"]["ref"] == (
        "parent.steps.ProjectDoneReview.artifacts.selection_bundle_path"
    )


def test_design_delta_selector_workflow_excludes_historical_state_from_provider_context():
    selector_workflow = yaml.safe_load(
        (ROOT / "workflows/library/lisp_frontend_design_delta_selector.v214.yaml").read_text()
    )

    for input_name in ("post_wcc_inventory_path", "progress_ledger_path", "run_state_path"):
        assert input_name not in selector_workflow["inputs"]
    for artifact_name in ("post_wcc_inventory", "progress_ledger", "run_state"):
        assert artifact_name not in selector_workflow["artifacts"]

    materialize = next(step for step in selector_workflow["steps"] if step["name"] == "MaterializeSelectorInputs")
    names = materialize["materialize_artifacts"]["input_values"][0]["names"]
    assert "post_wcc_inventory_path" not in names
    assert "progress_ledger_path" not in names
    assert "run_state_path" not in names
    publishes = {entry["artifact"]: entry["from"] for entry in materialize["publishes"]}
    assert "post_wcc_inventory" not in publishes
    assert "progress_ledger" not in publishes
    assert "run_state" not in publishes

    select = next(step for step in selector_workflow["steps"] if step["name"] == "SelectNextWork")
    consumed = [entry["artifact"] for entry in select["consumes"]]
    assert "post_wcc_inventory" not in consumed
    assert "post_wcc_inventory" not in select["prompt_consumes"]
    assert "progress_ledger" not in consumed
    assert "progress_ledger" not in select["prompt_consumes"]
    assert "run_state" not in consumed
    assert "run_state" not in select["prompt_consumes"]
    assert "baseline_design" in consumed
    assert "baseline_design" not in select["prompt_consumes"]


def test_prepare_design_delta_iteration_paths_clears_stale_iteration_outputs(tmp_path):
    manifest = tmp_path / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"items":[]}\n', encoding="utf-8")
    stale_selection = (
        tmp_path
        / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/selector/selection.json"
    )
    stale_selection.parent.mkdir(parents=True)
    stale_selection.write_text('{"selection_status":"DONE"}\n', encoding="utf-8")
    stale_work_item = (
        tmp_path
        / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-work-item/drain_status.txt"
    )
    stale_work_item.parent.mkdir(parents=True)
    stale_work_item.write_text("DONE\n", encoding="utf-8")

    output = "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/iteration-paths.json"
    result = subprocess.run(
        [
            "python",
            str(ROOT / "workflows/library/scripts/prepare_lisp_frontend_iteration_paths.py"),
            "--drain-state-root",
            "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain",
            "--iteration",
            "0",
            "--output",
            output,
        ],
        cwd=tmp_path,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert manifest.exists()
    assert not stale_selection.exists()
    assert not stale_work_item.exists()
    payload = json.loads((tmp_path / output).read_text(encoding="utf-8"))
    assert payload["selector_state_root"] == (
        "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/selector"
    )
    assert (tmp_path / payload["selector_state_root"]).is_dir()


def test_project_lisp_frontend_done_review_approves_terminal_done(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    original_selection = workspace / "state/selector/selection.json"
    original_selection.parent.mkdir(parents=True)
    original_selection.write_text(
        json.dumps({"selection_status": "DONE", "selection_rationale": "Selector saw no remaining work."}) + "\n",
        encoding="utf-8",
    )
    review_path = workspace / "state/iteration/done-review.json"
    review_path.parent.mkdir(parents=True)
    review_path.write_text(
        json.dumps({"done_decision": "APPROVE_DONE", "review_rationale": "Coverage is sufficient."}) + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/project_lisp_frontend_done_review.py"),
        "--review-path",
        "state/iteration/done-review.json",
        "--original-selection-path",
        "state/selector/selection.json",
        "--selection-output",
        "state/iteration/projected-selection.json",
        "--output",
        "state/iteration/projected-selection-path.json",
    )

    projected = json.loads((workspace / "state/iteration/projected-selection.json").read_text(encoding="utf-8"))
    assert projected == {
        "selection_status": "DONE",
        "selection_rationale": "Coverage is sufficient.",
        "terminal_review_decision": "APPROVE_DONE",
        "original_selection_bundle_path": "state/selector/selection.json",
    }
    bundle = json.loads((workspace / "state/iteration/projected-selection-path.json").read_text(encoding="utf-8"))
    assert bundle == {
        "selection_status": "DONE",
        "selection_bundle_path": "state/iteration/projected-selection.json",
    }


def test_project_lisp_frontend_done_review_rejects_done_as_design_gap(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    original_selection = workspace / "state/selector/selection.json"
    original_selection.parent.mkdir(parents=True)
    original_selection.write_text(
        json.dumps({"selection_status": "DONE", "selection_rationale": "Selector saw no remaining work."}) + "\n",
        encoding="utf-8",
    )
    review_path = workspace / "state/iteration/done-review.json"
    review_path.parent.mkdir(parents=True)
    review_path.write_text(
        json.dumps(
            {
                "done_decision": "REJECT_DONE",
                "review_rationale": "Parent-callable parity is still missing.",
                "design_gap_id": "parent-callable-parity-evidence",
                "source_design_path": "docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md",
                "source_sections": ["Tranche 8: Canonical Resume/Reuse Validation And Migration Evidence"],
                "missing_component": "Parent-callable parity evidence is incomplete.",
                "proposed_scope": "Add one bounded gap for parent-callable parity evidence.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/project_lisp_frontend_done_review.py"),
        "--review-path",
        "state/iteration/done-review.json",
        "--original-selection-path",
        "state/selector/selection.json",
        "--selection-output",
        "state/iteration/projected-selection.json",
        "--output",
        "state/iteration/projected-selection-path.json",
    )

    projected = json.loads((workspace / "state/iteration/projected-selection.json").read_text(encoding="utf-8"))
    assert projected["selection_status"] == "DRAFT_DESIGN_GAP"
    assert projected["design_gap_id"] == "parent-callable-parity-evidence"
    assert projected["selection_rationale"] == "Parent-callable parity is still missing."
    assert projected["terminal_review_decision"] == "REJECT_DONE"
    bundle = json.loads((workspace / "state/iteration/projected-selection-path.json").read_text(encoding="utf-8"))
    assert bundle == {
        "selection_status": "DRAFT_DESIGN_GAP",
        "selection_bundle_path": "state/iteration/projected-selection.json",
    }


def test_project_lisp_frontend_done_review_requires_gap_fields_when_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    original_selection = workspace / "state/selector/selection.json"
    original_selection.parent.mkdir(parents=True)
    original_selection.write_text(
        json.dumps({"selection_status": "DONE", "selection_rationale": "Selector saw no remaining work."}) + "\n",
        encoding="utf-8",
    )
    review_path = workspace / "state/iteration/done-review.json"
    review_path.parent.mkdir(parents=True)
    review_path.write_text(
        json.dumps({"done_decision": "REJECT_DONE", "review_rationale": "Still missing work."}) + "\n",
        encoding="utf-8",
    )

    result = _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/project_lisp_frontend_done_review.py"),
        "--review-path",
        "state/iteration/done-review.json",
        "--original-selection-path",
        "state/selector/selection.json",
        "--selection-output",
        "state/iteration/projected-selection.json",
        "--output",
        "state/iteration/projected-selection-path.json",
        check=False,
    )

    assert result.returncode != 0
    assert "missing required rejection field" in result.stderr


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
    call_selector_dirs = [
        pointer.parent
        for pointer in sorted(workspace.glob("state/workflow_lisp/calls/**/manifest_path.txt"))
        if not (pointer.parent / "selection.json").exists()
    ]
    if call_selector_dirs:
        return call_selector_dirs[-1]
    selector_dirs = [
        selector_dir
        for selector_dir in sorted(workspace.glob("state/**/selector"))
        if not (selector_dir / "selection.json").exists()
    ]
    if selector_dirs:
        return selector_dirs[-1]
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


def _write_done_review_approve(workspace: Path) -> None:
    roots = sorted(workspace.glob("state/**/done-review"), reverse=True)
    for root in roots:
        review_path = root / "done-review.json"
        if review_path.exists():
            continue
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            json.dumps(
                {
                    "done_decision": "APPROVE_DONE",
                    "review_rationale": "Terminal review found no remaining target design gaps.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending done-review directory found")


def _write_design_gap_architecture(workspace: Path) -> None:
    roots = [
        path.parent
        for path in sorted(workspace.glob("state/workflow_lisp/calls/**/architecture-targets.json"))
        if not (path.parent / "draft-bundle.json").exists()
    ]
    roots.extend(
        root
        for root in sorted(workspace.glob("state/**/design-gap-architect"))
        if not (root / "draft-bundle.json").exists()
    )
    for root in roots:
        bundle_path = root / "draft-bundle.json"
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


def _write_design_gap_architecture_review_approve(workspace: Path) -> None:
    roots = [
        path.parent
        for path in sorted(workspace.glob("state/workflow_lisp/calls/**/architecture-targets.json"))
        if not (path.parent / "architecture-review.json").exists()
    ]
    roots.extend(
        root
        for root in sorted(workspace.glob("state/**/design-gap-architect"))
        if not (root / "architecture-review.json").exists()
    )
    for root in roots:
        review_path = root / "architecture-review.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            json.dumps({"review_decision": "APPROVE", "reason": "Architecture is scoped."}, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending design-gap architecture review root found")


def _write_plan(workspace: Path) -> None:
    existing_target: Path | None = None
    for pointer in sorted(workspace.glob("state/**/plan_path.txt")):
        target = workspace / pointer.read_text(encoding="utf-8").strip()
        existing_target = existing_target or target
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Lisp Work Plan\n\n## Verification\n- `python -c \"print('gap-check')\"`\n", encoding="utf-8")
        return
    if existing_target is not None:
        existing_target.parent.mkdir(parents=True, exist_ok=True)
        existing_target.write_text("# Lisp Work Plan\n\n## Verification\n- `python -c \"print('gap-check')\"`\n", encoding="utf-8")
        return

    bundle_paths = sorted(workspace.glob("state/**/draft-bundle.json"))
    if not bundle_paths:
        raise AssertionError("No pending plan pointer found")
    bundle = json.loads(bundle_paths[-1].read_text(encoding="utf-8"))
    target = workspace / str(bundle.get("plan_target_path") or "")
    if not target.name:
        raise AssertionError("No pending plan pointer found")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Lisp Work Plan\n\n## Verification\n- `python -c \"print('gap-check')\"`\n", encoding="utf-8")

    plan_roots: list[Path] = []
    for paths_file in sorted(workspace.glob("state/**/iteration-paths.json")):
        paths = json.loads(paths_file.read_text(encoding="utf-8"))
        for key in ("design_gap_work_item_state_root", "backlog_work_item_state_root"):
            root = str(paths.get(key) or "").strip()
            if root:
                plan_roots.append(workspace / root / "plan-phase")
    for work_item_inputs in sorted(workspace.glob("state/**/work-item-inputs.json")):
        inputs = json.loads(work_item_inputs.read_text(encoding="utf-8"))
        root = str(inputs.get("plan_phase_state_root") or "").strip()
        if root:
            plan_roots.append(workspace / root)
    if not plan_roots:
        raise AssertionError("No pending plan pointer found")
    item_id = str(bundle.get("design_gap_id") or bundle.get("work_item_id") or "parser-syntax")
    review_target = Path("artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN") / f"{item_id}-plan-review.json"
    for root in dict.fromkeys(plan_roots):
        root.mkdir(parents=True, exist_ok=True)
        (root / "plan_path.txt").write_text(target.relative_to(workspace).as_posix() + "\n", encoding="utf-8")
        (root / "plan_review_report_path.txt").write_text(review_target.as_posix() + "\n", encoding="utf-8")


def _plan_target(workspace: Path) -> Path:
    pointers = sorted(workspace.glob("state/**/plan_path.txt"))
    if pointers:
        return workspace / pointers[-1].read_text(encoding="utf-8").strip()
    raise AssertionError("No plan pointer found")


def _pending_plan_review_root(workspace: Path) -> Path:
    roots = [
        pointer.parent
        for pointer in sorted(workspace.glob("state/**/plan_review_report_path.txt"))
        if not (pointer.parent / "plan_review_decision.txt").exists()
    ]
    if roots:
        return roots[-1]
    roots = [
        pointer.parent
        for pointer in sorted(workspace.glob("state/**/plan_review_report_path.txt"))
    ]
    if roots:
        return roots[-1]
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


def _append_or_write_plan_review_approve(workspace: Path) -> None:
    root = _pending_plan_review_root(workspace)
    decision = root / "plan_review_decision.txt"
    pointer = root / "plan_review_report_path.txt"
    target = workspace / pointer.read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"decision": "APPROVE", "findings": []}) + "\n", encoding="utf-8")
    mode = "a" if decision.exists() else "w"
    with decision.open(mode, encoding="utf-8") as handle:
        handle.write("APPROVE\n")


def _revise_plan(workspace: Path) -> None:
    target = _plan_target(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Lisp Work Plan\n\nRevised after review.\n\n## Verification\n- `python -c \"print('gap-check')\"`\n",
        encoding="utf-8",
    )



def _write_execution_state(workspace: Path) -> None:
    for target_pointer in sorted(workspace.glob("state/**/execution_report_target_path.txt")):
        root = target_pointer.parent
        bundle_path = root / "implementation_state.json"
        if bundle_path.exists():
            continue
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
    for target_pointer in sorted(workspace.glob("state/**/execution_report_target_path.txt")):
        root = target_pointer.parent
        bundle_path = root / "implementation_state.json"
        if bundle_path.exists():
            continue
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
    for target_pointer in sorted(workspace.glob("state/**/execution_report_target_path.txt")):
        root = target_pointer.parent
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
    for progress_pointer in sorted(workspace.glob("state/**/progress_report_target_path.txt")):
        root = progress_pointer.parent
        bundle_path = root / "implementation_state.json"
        if bundle_path.exists():
            continue
        target = workspace / progress_pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# Progress Report\n\n{progress_text}\n", encoding="utf-8")
        bundle_path.write_text(
            json.dumps({"implementation_state": "BLOCKED", "blocker_class": blocker_class}, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    raise AssertionError("No pending implementation phase root found")


def _write_blocked_recovery_bundle(workspace: Path, route: str, reason: str, summary: str | None = None) -> bytes:
    payload = {
        "blocked_recovery_route": route,
        "reason": reason,
        "summary": summary or f"{route} selected for test.",
    }
    targets: list[Path] = []
    for root in sorted(workspace.glob("state/**/design-gap-work-item")):
        if (root / "work-item-inputs.json").exists():
            targets.append(root / "blocked-implementation-recovery.json")
    drain_root = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain"
    if (drain_root / "prior-blocked-recovery.json").exists():
        targets.append(drain_root / "prior-blocked-recovery-decision.json")
    for path in sorted(workspace.glob("state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/*/blocked-recovery.json")):
        payload_path = path.parent / "blocked-recovery-decision.json"
        if not payload_path.exists():
            targets.append(payload_path)
    if not targets:
        raise AssertionError("No blocked recovery bundle target found")
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return (json.dumps(payload) + "\n").encode("utf-8")


def _classify_blocked_recovery_gap_design_required(workspace: Path) -> bytes:
    return _write_blocked_recovery_bundle(
        workspace,
        "GAP_DESIGN_REVISION_REQUIRED",
        "implementation_architecture_under_scoped",
    )


def _classify_blocked_recovery_gap_design_required_stdout_only(_workspace: Path) -> bytes:
    return (
        json.dumps(
            {
                "blocked_recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                "reason": "implementation_architecture_under_scoped",
                "summary": "GAP_DESIGN_REVISION_REQUIRED selected for test.",
            }
        )
        + "\n"
    ).encode("utf-8")


def _classify_blocked_recovery_target_design_required(workspace: Path) -> bytes:
    return _write_blocked_recovery_bundle(
        workspace,
        "TARGET_DESIGN_REVISION_REQUIRED",
        "target_design_contract_gap",
    )


def test_blocked_recovery_materializer_accepts_fenced_json(tmp_path):
    source_path = tmp_path / "blocked-recovery.stdout.json"
    output_path = tmp_path / "blocked-recovery.json"
    source_path.write_text(
        "```json\n"
        "{\n"
        '  "blocked_recovery_route": "GAP_DESIGN_REVISION_REQUIRED",\n'
        '  "reason": "implementation_architecture_under_scoped",\n'
        '  "summary": "The implementation slice needs a gap design revision."\n'
        "}\n"
        "```\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "workflows/library/scripts/materialize_lisp_frontend_blocked_recovery_bundle.py"),
            "--source-json-path",
            str(source_path),
        ],
        cwd=ROOT,
        env={"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(output_path)},
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["blocked_recovery_route"] == "GAP_DESIGN_REVISION_REQUIRED"
    assert payload["reason"] == "implementation_architecture_under_scoped"


def _classify_blocked_recovery_terminal(workspace: Path) -> bytes:
    return _write_blocked_recovery_bundle(
        workspace,
        "TERMINAL_BLOCKED",
        "user_decision_required",
        summary="External human authority is required and cannot be represented as a design change.",
    )


def _leave_execution_state_missing(_workspace: Path) -> None:
    return


def _implementation_execution_report_target(workspace: Path) -> Path:
    pointers = sorted(workspace.glob("state/**/execution_report_target_path.txt"))
    if pointers:
        return workspace / pointers[-1].read_text(encoding="utf-8").strip()
    raise AssertionError("No execution report target pointer found")


def _published_execution_report_path(workspace: Path) -> Path:
    for pointer in sorted(workspace.glob("state/**/execution_report_path.txt")):
        return workspace / pointer.read_text(encoding="utf-8").strip()
    raise AssertionError("No published execution report pointer found")


def _pending_implementation_review_root(workspace: Path) -> Path:
    roots = [
        pointer.parent
        for pointer in sorted(workspace.glob("state/**/implementation_review_report_path.txt"))
        if not (pointer.parent / "implementation_review_decision.txt").exists()
    ]
    if roots:
        return roots[-1]
    roots = [
        pointer.parent
        for pointer in sorted(workspace.glob("state/**/implementation_review_report_path.txt"))
    ]
    if roots:
        return roots[-1]
    raise AssertionError("No pending implementation review root found")


def _write_implementation_review(workspace: Path) -> None:
    root = _pending_implementation_review_root(workspace)
    decision = root / "implementation_review_decision.txt"
    pointer = root / "implementation_review_report_path.txt"
    target = workspace / pointer.read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Implementation Review\n\nApproved.\n", encoding="utf-8")
    decision.write_text("APPROVE\n", encoding="utf-8")
    for route_path in sorted(workspace.glob("state/**/recovered-gap/work-item-route.json")):
        route = json.loads(route_path.read_text(encoding="utf-8"))
        recovered_root_value = str(route.get("recovered_work_item_state_root") or "").strip()
        if recovered_root_value:
            status_path = workspace / recovered_root_value / "drain_status.txt"
            if not status_path.exists():
                status_path.parent.mkdir(parents=True, exist_ok=True)
                status_path.write_text("DONE\n", encoding="utf-8")
    for recovered_root in sorted(workspace.glob("state/**/recovered-gap/work-item")):
        status_path = recovered_root / "drain_status.txt"
        if not status_path.exists():
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("DONE\n", encoding="utf-8")


def _write_implementation_review_revise(workspace: Path) -> None:
    root = _pending_implementation_review_root(workspace)
    decision = root / "implementation_review_decision.txt"
    pointer = root / "implementation_review_report_path.txt"
    target = workspace / pointer.read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Implementation Review\n\nRevise required.\n", encoding="utf-8")
    decision.write_text("REVISE\n", encoding="utf-8")


def _append_or_write_implementation_review_approve(workspace: Path) -> None:
    root = _pending_implementation_review_root(workspace)
    decision = root / "implementation_review_decision.txt"
    pointer = root / "implementation_review_report_path.txt"
    target = workspace / pointer.read_text(encoding="utf-8").strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Implementation Review\n\nApproved.\n", encoding="utf-8")
    mode = "a" if decision.exists() else "w"
    with decision.open(mode, encoding="utf-8") as handle:
        handle.write("APPROVE\n")


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


def _blocked_recovery_iteration_root(workspace: Path) -> Path:
    paths = sorted(workspace.glob("state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/*/blocked-recovery-decision.json"))
    if not paths:
        raise AssertionError("No blocked recovery iteration root found")
    return paths[-1].parent


def _revise_blocked_target_design(workspace: Path) -> None:
    target = workspace / _design_delta_workflow_inputs()["target_design_path"]
    target.write_text(
        target.read_text(encoding="utf-8") + "\n\n## Blocker Revision\n\nAdded missing contract.\n",
        encoding="utf-8",
    )
    root = _blocked_recovery_iteration_root(workspace)
    (root / "blocked-design-revision-report.json").write_text(
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


def _revise_blocked_gap_design(workspace: Path) -> None:
    architecture = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    architecture.write_text(
        architecture.read_text(encoding="utf-8")
        + "\n\n## Blocked Recovery Revision\n\nAdded missing dependency sequencing.\n",
        encoding="utf-8",
    )
    root = _blocked_recovery_iteration_root(workspace)
    (root / "blocked-design-revision-report.json").write_text(
        json.dumps(
            {
                "design_revision_decision": "REVISED",
                "summary": "Updated gap implementation architecture from blocked state.",
                "changed_sections": ["Blocked Recovery Revision"],
                "blocker_class": "unknown",
                "reason": "implementation_architecture_under_scoped",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_blocked_design_revision_review_approve(workspace: Path) -> None:
    root = _blocked_recovery_iteration_root(workspace)
    target_pointer = root / "blocked-design-revision-review-target-path.txt"
    if target_pointer.exists():
        report = workspace / target_pointer.read_text(encoding="utf-8").strip()
    else:
        report = workspace / "artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/blocked-design-revision-review.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Design Revision Review\n\nApproved.\n", encoding="utf-8")
    (root / "blocked-design-revision-review-report-path.txt").write_text(
        report.relative_to(workspace).as_posix() + "\n",
        encoding="utf-8",
    )
    (root / "blocked-design-revision-review-decision.txt").write_text("APPROVE\n", encoding="utf-8")


def _seed_prior_blocked_design_gap(workspace: Path) -> None:
    run_state = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json"
    progress = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    architecture = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    previous_gap_state = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect"
    context = previous_gap_state / "work_item_context.md"
    checks = previous_gap_state / "check_commands.json"
    architecture_bundle = previous_gap_state / "architecture-validation.json"
    run_state.parent.mkdir(parents=True, exist_ok=True)
    progress.parent.mkdir(parents=True, exist_ok=True)
    architecture.parent.mkdir(parents=True, exist_ok=True)
    plan.parent.mkdir(parents=True, exist_ok=True)
    previous_gap_state.mkdir(parents=True, exist_ok=True)
    run_state.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {
                    "parser-syntax": {
                        "reason": "implementation_blocked",
                        "timestamp_utc": "2026-06-01T00:00:00Z",
                        "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                        "recovery_reason": "implementation_architecture_under_scoped",
                        "recovery_event_id": "parser-syntax-implementation-blocked",
                    }
                },
                "history": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    progress.write_text("# Progress Report\n\nBlocker class: roadmap_conflict\n", encoding="utf-8")
    architecture.write_text("# Parser Syntax Implementation Architecture\n", encoding="utf-8")
    plan.write_text("# Parser Syntax Execution Plan\n", encoding="utf-8")
    context.write_text("# Parser Syntax Work Item\n\nRetry this recovered design gap.\n", encoding="utf-8")
    checks.write_text(json.dumps(["python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q"]) + "\n", encoding="utf-8")
    architecture_bundle.write_text(
        json.dumps(
            {
                "architecture_validation_status": "VALID",
                "work_item_source": "DESIGN_GAP",
                "work_item_id": "parser-syntax",
                "architecture_path": architecture.relative_to(workspace).as_posix(),
                "work_item_context_path": context.relative_to(workspace).as_posix(),
                "check_commands_path": checks.relative_to(workspace).as_posix(),
                "plan_target_path": plan.relative_to(workspace).as_posix(),
                "work_item_bundle_path": architecture_bundle.relative_to(workspace).as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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


def _revise_prior_blocked_gap_design(workspace: Path) -> None:
    architecture = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    architecture.write_text(
        architecture.read_text(encoding="utf-8")
        + "\n\n## Blocked Recovery Revision\n\nAdded missing dependency sequencing.\n",
        encoding="utf-8",
    )
    report = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/prior-blocked-design-revision-report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "design_revision_decision": "REVISED",
                "summary": "Updated gap implementation architecture from prior blocked state.",
                "changed_sections": ["Blocked Recovery Revision"],
                "blocker_class": "unknown",
                "reason": "implementation_architecture_under_scoped",
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
        writer_result = writer(workspace)
        stdout = writer_result if isinstance(writer_result, bytes) else b"ok"
        return SimpleNamespace(
            exit_code=0,
            stdout=stdout,
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
    provider_sequence = [
        ("SelectNextWork", _write_selector_design_gap),
        ("DraftDesignGapArchitecture", _write_design_gap_architecture),
        ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
        ("DraftPlan", _write_plan),
        ("ReviewPlan", _write_plan_review),
        ("ExecuteImplementation", _write_execution_state),
        ("ReviewImplementation", _write_implementation_review),
        ("SelectNextWork", _write_selector_done),
    ]

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        provider_sequence,
    )

    assert state["__provider_calls"] == len(provider_sequence)
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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_blocked_roadmap_conflict),
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_target_design_required),
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_target_design_required),
            ("ReviseBlockedDesignGap", _revise_blocked_target_design),
            ("ReviewBlockedTargetDesignRevision", _write_blocked_design_revision_review_approve),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
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


def test_design_delta_plan_review_clears_stale_decision_before_second_review(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    workflow_path = workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review_revise),
            ("RevisePlan", _revise_plan),
            ("ReviewPlan", _append_or_write_plan_review_approve),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
            ("SelectNextWork", _write_selector_done),
            ("ReviewDoneDecision", _write_done_review_approve),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    assert state["status"] == "completed"
    decision = workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-work-item/plan-phase/plan_review_decision.txt"
    assert decision.read_text(encoding="utf-8") == "APPROVE\n"


def test_design_delta_implementation_review_clears_stale_decision_before_second_review(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    workflow_path = workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("SelectNextWork", _write_selector_design_gap),
            ("DraftDesignGapArchitecture", _write_design_gap_architecture),
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review_revise),
            ("FixImplementation", _fix_implementation),
            ("ReviewImplementation", _append_or_write_implementation_review_approve),
            ("SelectNextWork", _write_selector_done),
            ("ReviewDoneDecision", _write_done_review_approve),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    assert state["status"] == "completed"
    decision = (
        workspace
        / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-work-item/implementation-phase/implementation_review_decision.txt"
    )
    assert decision.read_text(encoding="utf-8") == "APPROVE\n"


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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_blocked_external_under_scoped_gap),
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_gap_design_required),
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_gap_design_required),
            ("ReviseBlockedDesignGap", _revise_blocked_gap_design),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
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


def test_design_delta_work_item_accepts_stdout_only_blocked_recovery_classifier_json(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    workflow_path = workspace / "workflows/library/lisp_frontend_design_delta_work_item.v214.yaml"

    manifest_path = workspace / "state/manifest.json"
    selection_path = workspace / "state/selection.json"
    architecture_path = (
        workspace
        / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    )
    context_path = workspace / "state/gap/work_item_context.md"
    checks_path = workspace / "state/gap/check_commands.json"
    plan_target_path = (
        workspace
        / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    )
    architecture_bundle_path = workspace / "state/gap/architecture-validation.json"
    run_state_path = workspace / "state/run_state.json"

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    architecture_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_path.write_text(json.dumps({"items": []}) + "\n", encoding="utf-8")
    selection_path.write_text(
        json.dumps(
            {
                "selection_status": "DRAFT_DESIGN_GAP",
                "design_gap_id": "parser-syntax",
                "selection_rationale": "Parser syntax gap remains active.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    architecture_path.write_text("# Parser Syntax Architecture\n", encoding="utf-8")
    context_path.write_text("# Parser Syntax Work Item\n", encoding="utf-8")
    checks_path.write_text(json.dumps(["python -m pytest -q"]) + "\n", encoding="utf-8")
    architecture_bundle_path.write_text(
        json.dumps(
            {
                "architecture_validation_status": "VALID",
                "work_item_source": "DESIGN_GAP",
                "work_item_id": "parser-syntax",
                "architecture_path": architecture_path.relative_to(workspace).as_posix(),
                "work_item_context_path": context_path.relative_to(workspace).as_posix(),
                "check_commands_path": checks_path.relative_to(workspace).as_posix(),
                "plan_target_path": plan_target_path.relative_to(workspace).as_posix(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    run_state_path.write_text(
        json.dumps(
            {
                "completed_design_gaps": [],
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def _write_direct_plan(_workspace: Path) -> None:
        plan_target_path.parent.mkdir(parents=True, exist_ok=True)
        plan_target_path.write_text(
            "# Lisp Work Plan\n\n## Verification\n- `python -m pytest -q`\n",
            encoding="utf-8",
        )

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("DraftPlan", _write_direct_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_blocked_external_under_scoped_gap),
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_gap_design_required_stdout_only),
        ],
        workflow_inputs={
            "state_root": "state/design-gap-work-item",
            "selection_bundle_path": "state/selection.json",
            "manifest_path": "state/manifest.json",
            "architecture_bundle_path": "state/gap/architecture-validation.json",
            "steering_path": "docs/steering.md",
            "target_design_path": "docs/design/workflow_lisp_frontend_specification.md",
            "baseline_design_path": "docs/design/workflow_lisp_frontend_mvp_specification.md",
            "progress_ledger_path": "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json",
            "run_state_path": "state/run_state.json",
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 4
    assert state["workflow_outputs"]["drain_status"] == "CONTINUE"


def test_design_delta_prior_blocked_gap_revises_design_before_selection(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    _seed_prior_blocked_design_gap(workspace)
    workflow_path = workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_target_design_required),
            ("ReviseBlockedDesignGap", _revise_blocked_target_design),
            ("ReviewBlockedTargetDesignRevision", _write_blocked_design_revision_review_approve),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    run_state = json.loads(
        (workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json").read_text(encoding="utf-8")
    )
    target_text = (workspace / _design_delta_workflow_inputs()["target_design_path"]).read_text(encoding="utf-8")

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 9
    assert any(event["event"] == "design_revision" for event in run_state["history"])
    assert any(
        event["event"] == "completed" and event["item_id"] == "parser-syntax"
        for event in run_state["history"]
    )
    assert "parser-syntax" not in run_state["blocked_design_gaps"]
    assert "Blocker Revision" in target_text


def test_design_delta_prior_blocked_gap_design_recovery_before_selection(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    _seed_prior_blocked_design_gap(workspace)
    workflow_path = workspace / "workflows/examples/lisp_frontend_design_delta_drain.yaml"

    state = _run_workflow_with_providers(
        workspace,
        workflow_path,
        [
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_gap_design_required),
            ("ReviseBlockedDesignGap", _revise_blocked_gap_design),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    run_state = json.loads(
        (workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json").read_text(encoding="utf-8")
    )
    target_text = (workspace / _design_delta_workflow_inputs()["target_design_path"]).read_text(encoding="utf-8")
    architecture_text = (
        workspace
        / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    ).read_text(encoding="utf-8")

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 6
    assert any(event["event"] == "gap_design_revision" for event in run_state["history"])
    assert any(
        event["event"] == "completed" and event["item_id"] == "parser-syntax"
        for event in run_state["history"]
    )
    assert "parser-syntax" in run_state["completed_design_gaps"]
    assert "parser-syntax" not in run_state["blocked_design_gaps"]
    assert "Prior Blocker Revision" not in target_text
    assert "Blocked Recovery Revision" in architecture_text


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
            ("ReviewDesignGapArchitecture", _write_design_gap_architecture_review_approve),
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
