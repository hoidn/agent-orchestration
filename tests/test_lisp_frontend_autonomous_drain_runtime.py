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
        "workflows/library/scripts/prepare_lisp_frontend_recovered_design_gap_work_item.py",
        "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py",
        "workflows/library/scripts/classify_lisp_frontend_implementation_blocker.py",
        "workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py",
        "workflows/library/scripts/detect_lisp_frontend_prior_blocked_design_gap.py",
        "workflows/library/scripts/materialize_lisp_frontend_recovered_design_gap_draft.py",
        "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py",
        "workflows/library/scripts/update_lisp_frontend_run_state.py",
        "workflows/library/scripts/record_lisp_frontend_design_revision_outcome.py",
        "workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py",
        "workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py",
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
    assert blocked["recovery_status"] == "TARGET_DESIGN_REVISION_REQUIRED"
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
    assert payload["recovery_route"] == "PREREQUISITE_GAP_REQUIRED"


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


def test_prerequisite_retry_ready_bypasses_reclassification_for_original_gap_retry(tmp_path):
    workspace = tmp_path / "workspace"
    _copy_runtime_files(workspace)
    state_path = workspace / "state/drain/run_state.json"
    recovery_bundle = workspace / "state/drain/recovery-decision.json"
    summary_path = workspace / "artifacts/work/blocked-summary.json"
    pointer_path = workspace / "state/drain/blocked-summary-path.txt"
    drain_status_path = workspace / "state/drain/blocked-drain-status.txt"

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
        "--summary-path",
        summary_path.relative_to(workspace).as_posix(),
        "--summary-pointer-path",
        pointer_path.relative_to(workspace).as_posix(),
        "--drain-status-path",
        drain_status_path.relative_to(workspace).as_posix(),
    )

    assert drain_status_path.read_text(encoding="utf-8").strip() == "RUN_RECOVERED_GAP"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["item_status"] == "PREREQUISITE_RETRY_READY"


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
    assert blocked["recovery_status"] == "PREREQUISITE_BLOCKED"
    assert blocked["prerequisite_recovery_status"] == "DECLINED"
    assert "parser-syntax" in state["blocked_design_gaps"]
    assert state["history"][-1]["event"] == "prerequisite_recovery_blocked"
    assert drain_status_path.read_text(encoding="utf-8").strip() == "BLOCKED"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_status"] == "BLOCKED"


def test_resolve_drain_iteration_status_maps_recovery_routes(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = str(ROOT / "workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py")

    cases = [
        ("SELECT_NORMAL_WORK", "ignored", "ignored", "ignored", "DONE", "DONE"),
        ("SELECT_PREREQUISITE_WORK", "ignored", "ignored", "CONTINUE", "CONTINUE", "CONTINUE"),
        ("SELECT_PREREQUISITE_WORK", "ignored", "ignored", "BLOCKED", "CONTINUE", "BLOCKED"),
        ("RECOVER_BLOCKED_DESIGN_GAP", "RUN_RECOVERED_GAP", "CONTINUE", "IGNORED", "IGNORED", "CONTINUE"),
        ("RECOVER_BLOCKED_DESIGN_GAP", "RUN_RECOVERED_GAP", "BLOCKED", "IGNORED", "IGNORED", "BLOCKED"),
        ("RECOVER_BLOCKED_DESIGN_GAP", "RUN_RECOVERED_GAP", "IGNORED", "IGNORED", "IGNORED", "BLOCKED"),
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


def test_detect_prior_blocked_design_gap_recovers_roadmap_conflict(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    output_path = workspace / "state/drain/prior-blocked-recovery.json"
    state_path.parent.mkdir(parents=True)
    progress_path.parent.mkdir(parents=True)
    architecture_path.parent.mkdir(parents=True)
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
    progress_path.write_text("# Progress Report\n\nBlocker class: roadmap_conflict\n", encoding="utf-8")
    architecture_path.write_text("# Parser Syntax Architecture\n", encoding="utf-8")
    plan_path.write_text("# Parser Syntax Plan\n", encoding="utf-8")

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
        "architecture_path": "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md",
        "plan_path": "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md",
        "architecture_copy_path": output_path.with_name("prior-blocked-gap-architecture.md").relative_to(workspace).as_posix(),
        "plan_copy_path": output_path.with_name("prior-blocked-gap-execution-plan.md").relative_to(workspace).as_posix(),
        "blocker_class": "roadmap_conflict",
        "block_reason": "implementation_blocked",
    }


def test_detect_prior_blocked_design_gap_recovers_under_scoped_architecture(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state_path = workspace / "state/drain/run_state.json"
    progress_path = workspace / "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/progress_report.md"
    architecture_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/implementation_architecture.md"
    plan_path = workspace / "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax/execution_plan.md"
    output_path = workspace / "state/drain/prior-blocked-recovery.json"
    state_path.parent.mkdir(parents=True)
    progress_path.parent.mkdir(parents=True)
    architecture_path.parent.mkdir(parents=True)
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
    progress_path.write_text(
        "# Progress Report\n\nThe approved implementation architecture is under-scoped for this gap.\n",
        encoding="utf-8",
    )
    architecture_path.write_text("# Parser Syntax Architecture\n", encoding="utf-8")
    plan_path.write_text("# Parser Syntax Plan\n", encoding="utf-8")

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
    assert payload["architecture_path"].endswith("/parser-syntax/implementation_architecture.md")
    assert payload["plan_path"].endswith("/parser-syntax/execution_plan.md")
    assert payload["architecture_copy_path"].endswith("/prior-blocked-gap-architecture.md")
    assert payload["plan_copy_path"].endswith("/prior-blocked-gap-execution-plan.md")


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

    recovery_classifier = next(step for step in workflow["steps"] if step["name"] == "ClassifyBlockedImplementationRecovery")
    assert recovery_classifier["asset_file"] == (
        "prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md"
    )
    recovery_selector = next(step for step in workflow["steps"] if step["name"] == "SelectBlockedRecoveryRoute")
    assert any(part.endswith("select_lisp_frontend_blocked_recovery_route.py") for part in recovery_selector["command"])

    route_terminal = next(step for step in workflow["steps"] if step["name"] == "RouteWorkItemTerminal")
    terminal = route_terminal["match"]["cases"]["IMPLEMENTATION_BLOCKED"]
    recorder = next(step for step in terminal["steps"] if step["name"] == "RecordBlockedRecoveryOutcome")
    assert any(part.endswith("record_lisp_frontend_blocked_recovery_outcome.py") for part in recorder["command"])
    assert "${steps.SelectBlockedRecoveryRoute.artifacts.blocked_recovery_route}" in recorder["command"]
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
    assert any(step["name"] == "RunNormalSelector" for step in selector_cases["SELECT_NORMAL_WORK"]["steps"])
    normal_selector = next(step for step in selector_cases["SELECT_NORMAL_WORK"]["steps"] if step["name"] == "RunNormalSelector")
    assert normal_selector["with"]["run_state_path"]["ref"] == "inputs.run_state_target_path"
    assert any(
        step["name"] == "RunPrerequisiteRecoverySelector"
        for step in selector_cases["SELECT_PREREQUISITE_WORK"]["steps"]
    )
    prerequisite_selector = next(
        step for step in selector_cases["SELECT_PREREQUISITE_WORK"]["steps"]
        if step["name"] == "RunPrerequisiteRecoverySelector"
    )
    assert prerequisite_selector["call"] == "selector"
    assert prerequisite_selector["with"]["state_root"]["ref"] == (
        "parent.steps.PrepareIterationPaths.artifacts.prerequisite_selector_state_root"
    )
    assert prerequisite_selector["with"]["run_state_path"]["ref"] == "inputs.run_state_target_path"
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
        "PREREQUISITE_GAP_REQUIRED",
    ]
    assert "PREREQUISITE_GAP_REQUIRED" in json.dumps(recover["ReviewBlockedTargetDesignRevision"]["when"])
    assert "PREREQUISITE_GAP_REQUIRED" in json.dumps(recover["WriteBlockedDesignRevisionDecision"]["when"])
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
        "RecordRecoveredRetryUnavailable",
    ]:
        assert _condition_has_pre_selection_recovery_guard(recover[step_name]["when"]), step_name
    retry_unavailable = recover["RecordRecoveredRetryUnavailable"]
    assert any(part.endswith("record_lisp_frontend_recovered_retry_unavailable.py") for part in retry_unavailable["command"])
    materializer_condition = json.dumps(recover["MaterializeRecoveredBlockedGapDraft"]["when"])
    assert "RETRY_READY" in materializer_condition
    assert "RecordBlockedRecoveryOutcome.artifacts.recovery_drain_status" in materializer_condition


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
    existing_target: Path | None = None
    for pointer in sorted(workspace.glob("state/**/plan-phase/plan_path.txt")):
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
    raise AssertionError("No pending plan pointer found")


def _plan_target(workspace: Path) -> Path:
    pointers = sorted(workspace.glob("state/**/plan-phase/plan_path.txt"))
    if pointers:
        return workspace / pointers[-1].read_text(encoding="utf-8").strip()
    raise AssertionError("No plan pointer found")


def _pending_plan_review_root(workspace: Path) -> Path:
    roots = [
        root
        for root in sorted(workspace.glob("state/**/plan-phase"))
        if (root / "plan_review_report_path.txt").exists() and not (root / "plan_review_decision.txt").exists()
    ]
    if roots:
        return roots[-1]
    roots = [
        root
        for root in sorted(workspace.glob("state/**/plan-phase"))
        if (root / "plan_review_report_path.txt").exists()
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
    for path in sorted(workspace.glob("state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/*/blocked-recovery.json")):
        payload_path = path.parent / "blocked-recovery-decision.json"
        if not payload_path.exists():
            targets.append(payload_path)
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
    pointers = sorted(workspace.glob("state/**/implementation-phase/execution_report_target_path.txt"))
    if pointers:
        return workspace / pointers[-1].read_text(encoding="utf-8").strip()
    raise AssertionError("No execution report target pointer found")


def _published_execution_report_path(workspace: Path) -> Path:
    for pointer in sorted(workspace.glob("state/**/implementation-phase/execution_report_path.txt")):
        return workspace / pointer.read_text(encoding="utf-8").strip()
    raise AssertionError("No published execution report pointer found")


def _pending_implementation_review_root(workspace: Path) -> Path:
    roots = [
        root
        for root in sorted(workspace.glob("state/**/implementation-phase"))
        if (root / "implementation_review_report_path.txt").exists()
        and not (root / "implementation_review_decision.txt").exists()
    ]
    if roots:
        return roots[-1]
    roots = [
        root
        for root in sorted(workspace.glob("state/**/implementation-phase"))
        if (root / "implementation_review_report_path.txt").exists()
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
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_target_design_required),
            ("ReviseBlockedDesignGap", _revise_blocked_target_design),
            ("ReviewBlockedTargetDesignRevision", _write_blocked_design_revision_review_approve),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
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
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_gap_design_required),
            ("ReviseBlockedDesignGap", _revise_blocked_gap_design),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
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
            ("ClassifyBlockedImplementationRecovery", _classify_blocked_recovery_target_design_required),
            ("ReviseBlockedDesignGap", _revise_blocked_target_design),
            ("ReviewBlockedTargetDesignRevision", _write_blocked_design_revision_review_approve),
            ("DraftPlan", _write_plan),
            ("ReviewPlan", _write_plan_review),
            ("ExecuteImplementation", _write_execution_state),
            ("ReviewImplementation", _write_implementation_review),
            ("SelectNextWork", _write_selector_done),
        ],
        workflow_inputs=_design_delta_workflow_inputs(),
    )

    run_state = json.loads(
        (workspace / "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json").read_text(encoding="utf-8")
    )
    target_text = (workspace / _design_delta_workflow_inputs()["target_design_path"]).read_text(encoding="utf-8")

    assert state["status"] == "completed"
    assert state["__provider_calls"] == 8
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
            ("SelectNextWork", _write_selector_done),
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
    assert state["__provider_calls"] == 7
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
