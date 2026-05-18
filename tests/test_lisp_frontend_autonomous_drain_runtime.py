import json
import shutil
import subprocess
from dataclasses import is_dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


def _copy_repo_file_to_workspace(workspace: Path, repo_relpath: str) -> None:
    src = ROOT / repo_relpath
    dest = workspace / repo_relpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _copy_runtime_files(workspace: Path) -> Path:
    shutil.copytree(FIXTURE_ROOT, workspace, dirs_exist_ok=True)
    files = [
        "workflows/examples/lisp_frontend_autonomous_drain.yaml",
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


def test_lisp_frontend_workflows_load(tmp_path):
    workspace = tmp_path / "workspace"
    workflow_path = _copy_runtime_files(workspace)
    loader = WorkflowLoader(workspace)

    top = loader.load(workflow_path)
    assert workflow_input_contracts(top).get("roadmap_gate_path") is None
    for relpath in [
        "workflows/library/lisp_frontend_selector.v214.yaml",
        "workflows/library/lisp_frontend_design_gap_architect.v214.yaml",
        "workflows/library/lisp_frontend_work_item.v214.yaml",
        "workflows/library/lisp_frontend_plan_phase.v214.yaml",
        "workflows/library/lisp_frontend_implementation_phase.v214.yaml",
    ]:
        loader.load(workspace / relpath)


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


def _write_plan_review(workspace: Path) -> None:
    for root in sorted(workspace.glob("state/**/plan-phase")):
        decision = root / "plan_review_decision.txt"
        if decision.exists():
            continue
        pointer = root / "plan_review_report_path.txt"
        if not pointer.exists():
            continue
        target = workspace / pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"decision": "APPROVE", "findings": []}) + "\n", encoding="utf-8")
        decision.write_text("APPROVE\n", encoding="utf-8")
        return
    raise AssertionError("No pending plan review root found")


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


def _write_implementation_review(workspace: Path) -> None:
    for root in sorted(workspace.glob("state/**/implementation-phase")):
        decision = root / "implementation_review_decision.txt"
        if decision.exists():
            continue
        pointer = root / "implementation_review_report_path.txt"
        if not pointer.exists():
            continue
        target = workspace / pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Implementation Review\n\nApproved.\n", encoding="utf-8")
        decision.write_text("APPROVE\n", encoding="utf-8")
        return
    raise AssertionError("No pending implementation review root found")


def _run_workflow_with_providers(workspace: Path, workflow_path: Path, provider_sequence):
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

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **kwargs):
        expected_step, writer = provider_sequence[call_index["value"]]
        actual_step = kwargs.get("step_name")
        if actual_step is not None:
            assert actual_step == expected_step
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
    state["__provider_calls"] = call_index["value"]
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
