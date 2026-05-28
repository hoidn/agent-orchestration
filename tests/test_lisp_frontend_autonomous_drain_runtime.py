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
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_context, workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs


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
        "workflows/examples/lisp_frontend_autonomous_drain.yaml",
        "workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml",
        "workflows/library/lisp_frontend_selector.v214.yaml",
        "workflows/library/lisp_frontend_design_gap_architect.v214.yaml",
        "workflows/library/lisp_frontend_work_item.v214.yaml",
        "workflows/library/lisp_frontend_plan_phase.v214.yaml",
        "workflows/library/lisp_frontend_implementation_phase.v214.yaml",
        "workflows/library/scripts/build_lisp_frontend_architecture_index.py",
        "workflows/library/scripts/build_lisp_frontend_backlog_manifest.py",
        "workflows/library/scripts/build_neurips_backlog_manifest.py",
        "workflows/library/scripts/prepare_lisp_frontend_iteration_paths.py",
        "workflows/library/scripts/publish_lisp_frontend_selection_bundle.py",
        "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py",
        "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py",
        "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py",
        "workflows/library/scripts/update_lisp_frontend_run_state.py",
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
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_plan_phase").rglob("*.md")
    )
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "workflows/library/prompts/lisp_frontend_implementation_phase").rglob("*.md")
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


def _run_script(workspace: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", *argv],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    )


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
    assert proc_ref_inputs["artifact_work_root"].default == "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION"
    assert proc_ref_inputs["artifact_checks_root"].default == "artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION"
    assert proc_ref_inputs["artifact_review_root"].default == "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION"
    for relpath in [
        "workflows/library/lisp_frontend_selector.v214.yaml",
        "workflows/library/lisp_frontend_design_gap_architect.v214.yaml",
        "workflows/library/lisp_frontend_work_item.v214.yaml",
        "workflows/library/lisp_frontend_plan_phase.v214.yaml",
        "workflows/library/lisp_frontend_implementation_phase.v214.yaml",
    ]:
        loader.load(workspace / relpath)


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


def _provider_step_matches(actual: str | None, expected: str) -> bool:
    if actual is None:
        return True
    return actual == expected or actual.endswith(f".{expected}")


def _provider_step_called(state: dict, expected: str) -> bool:
    return any(_provider_step_matches(actual, expected) for actual in state.get("__provider_step_names", []))


def _run_workflow_with_providers(
    workspace: Path, workflow_path: Path, provider_sequence, require_all_providers: bool = True
):
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    bound_inputs = bind_workflow_inputs(workflow_input_contracts(workflow), _workflow_inputs(), workspace)
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
