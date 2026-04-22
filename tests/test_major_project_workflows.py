import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from tests.workflow_bundle_helpers import bundle_context_dict


ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(relpath: str) -> dict:
    return yaml.safe_load((ROOT / relpath).read_text(encoding="utf-8"))


def _walk_steps(steps: list[dict], prefix: str = ""):
    for step in steps:
        name = step["name"]
        path = f"{prefix} > {name}" if prefix else name
        yield path, step
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            yield from _walk_steps(repeat_until.get("steps", []), path)
        match = step.get("match")
        if isinstance(match, dict):
            for case_name, case in match.get("cases", {}).items():
                case_steps = case.get("steps", case) if isinstance(case, dict) else case
                yield from _walk_steps(case_steps, f"{path} > case {case_name}")
        for branch_name in ("then", "else"):
            branch = step.get(branch_name)
            if isinstance(branch, dict):
                yield from _walk_steps(branch.get("steps", []), f"{path} > {branch_name}")
            elif isinstance(branch, list):
                yield from _walk_steps(branch, f"{path} > {branch_name}")
        for_each = step.get("for_each")
        if isinstance(for_each, dict):
            yield from _walk_steps(for_each.get("steps", []), path)


def _step_by_name(workflow: dict, name: str) -> dict:
    for _, step in _walk_steps(workflow["steps"]):
        if step["name"] == name:
            return step
    raise AssertionError(f"Missing step {name}")


def _on_config(step: dict) -> dict:
    return step.get("on", step.get(True, {}))


def _copy_repo_file_to_workspace(workspace: Path, repo_relpath: str) -> None:
    src = ROOT / repo_relpath
    dest = workspace / repo_relpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _copy_major_project_runtime_files(
    workspace: Path,
    workflow_relpath: str = "workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml",
) -> Path:
    files = [
        workflow_relpath,
        "workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml",
        "workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml",
        "workflows/examples/inputs/major_project_brief.md",
        "workflows/library/major_project_roadmap_phase.yaml",
        "workflows/library/tracked_big_design_phase.yaml",
        "workflows/library/major_project_tranche_design_plan_impl_stack.yaml",
        "workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml",
        "workflows/library/tracked_plan_phase.yaml",
        "workflows/library/design_plan_impl_implementation_phase.yaml",
        "workflows/library/scripts/validate_major_project_tranche_manifest.py",
        "workflows/library/scripts/select_major_project_tranche.py",
        "workflows/library/scripts/update_major_project_tranche_manifest.py",
    ]
    files.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / "workflows/library/prompts").rglob("*.md"))
    for relpath in sorted(set(files)):
        _copy_repo_file_to_workspace(workspace, relpath)
    return workspace / workflow_relpath


def _target_from_pointer(workspace: Path, pointer_relpath: str) -> Path:
    target_relpath = (workspace / pointer_relpath).read_text(encoding="utf-8").strip()
    target = workspace / target_relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _write_review_outputs(
    workspace: Path,
    *,
    pointer_relpath: str,
    decision_relpath: str,
    high_count_relpath: str | None = None,
    medium_count_relpath: str | None = None,
    markdown: bool = False,
) -> None:
    report = _target_from_pointer(workspace, pointer_relpath)
    if markdown:
        report.write_text("APPROVE\n", encoding="utf-8")
    else:
        report.write_text(
            json.dumps(
                {
                    "decision": "APPROVE",
                    "summary": "Runtime smoke approval.",
                    "findings": [],
                    "unresolved_high_count": 0,
                    "unresolved_medium_count": 0,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    (workspace / decision_relpath).write_text("APPROVE\n", encoding="utf-8")
    if high_count_relpath:
        (workspace / high_count_relpath).write_text("0\n", encoding="utf-8")
    if medium_count_relpath:
        (workspace / medium_count_relpath).write_text("0\n", encoding="utf-8")


def _run_with_mocked_providers(
    workspace: Path,
    workflow_path: Path,
    provider_sequence: list[str],
    provider_writers: dict[str, object],
    bound_inputs: dict[str, str] | None = None,
) -> dict:
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    workflow_relpath = workflow_path.relative_to(workspace).as_posix()
    bound_inputs = bind_workflow_inputs(workflow_input_contracts(workflow), bound_inputs or {}, workspace)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(workflow_relpath, bundle_context_dict(workflow), bound_inputs=bound_inputs)
    executor = WorkflowExecutor(workflow, workspace, state_manager)
    call_index = {"value": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **kwargs):
        step_name = provider_sequence[call_index["value"]]
        call_index["value"] += 1
        writer_result = provider_writers[step_name](workspace)
        if hasattr(writer_result, "exit_code"):
            return writer_result
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


def test_major_project_workflow_files_exist():
    for relpath in [
        "workflows/library/major_project_roadmap_phase.yaml",
        "workflows/library/tracked_big_design_phase.yaml",
        "workflows/library/major_project_tranche_design_plan_impl_stack.yaml",
        "workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml",
        "workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml",
        "workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml",
        "workflows/examples/major_project_tranche_drain_stack_v2_call.yaml",
        "workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml",
    ]:
        assert (ROOT / relpath).is_file(), relpath


def test_tranche_stack_reuses_existing_plan_and_implementation_phases():
    workflow = _load_yaml("workflows/library/major_project_tranche_design_plan_impl_stack.yaml")

    assert workflow["imports"] == {
        "big_design_phase": "tracked_big_design_phase.yaml",
        "plan_phase": "tracked_plan_phase.yaml",
        "implementation_phase": "design_plan_impl_implementation_phase.yaml",
    }


def test_approved_design_tranche_stack_reuses_existing_plan_and_implementation_phases():
    workflow = _load_yaml("workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml")

    assert workflow["imports"] == {
        "plan_phase": "tracked_plan_phase.yaml",
        "implementation_phase": "design_plan_impl_implementation_phase.yaml",
    }


def test_runnable_example_runs_roadmap_phase_before_tranche_stack():
    workflow = _load_yaml("workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml")

    assert workflow["imports"] == {
        "roadmap_phase": "../library/major_project_roadmap_phase.yaml",
        "tranche_stack": "../library/major_project_tranche_design_plan_impl_stack.yaml",
    }
    assert [step["name"] for step in workflow["steps"]] == [
        "RunRoadmapPhase",
        "SelectNextTranche",
        "RunSelectedTranche",
    ]
    assert _step_by_name(workflow, "RunSelectedTranche")["with"]["tranche_manifest_path"] == {
        "ref": "root.steps.SelectNextTranche.artifacts.tranche_manifest_path"
    }


def test_drain_workflow_runs_roadmap_once_before_manifest_loop():
    workflow = _load_yaml("workflows/examples/major_project_tranche_drain_stack_v2_call.yaml")

    assert workflow["imports"] == {
        "roadmap_phase": "../library/major_project_roadmap_phase.yaml",
        "tranche_stack": "../library/major_project_tranche_design_plan_impl_stack.yaml",
    }
    assert [step["name"] for step in workflow["steps"]] == [
        "RunRoadmapPhase",
        "DrainManifest",
        "PublishDrainSummary",
    ]

    drain = _step_by_name(workflow, "DrainManifest")
    body_names = [step["name"] for step in drain["repeat_until"]["steps"]]
    assert body_names == ["SelectNextTranche", "RouteTrancheSelection"]
    assert "RunRoadmapPhase" not in body_names
    assert drain["repeat_until"]["condition"] == {
        "any_of": [
            {
                "compare": {
                    "left": {"ref": "self.outputs.drain_status"},
                    "op": "eq",
                    "right": "DONE",
                }
            },
            {
                "compare": {
                    "left": {"ref": "self.outputs.drain_status"},
                    "op": "eq",
                    "right": "BLOCKED",
                }
            },
        ]
    }


def test_drain_from_manifest_workflow_starts_at_manifest_loop():
    workflow = _load_yaml("workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml")

    assert workflow["imports"] == {
        "tranche_stack": "../library/major_project_tranche_design_plan_impl_stack.yaml",
    }
    assert [step["name"] for step in workflow["steps"]] == [
        "DrainManifest",
        "PublishDrainSummary",
    ]


def test_continue_from_approved_design_workflow_starts_at_manifest_selection():
    workflow = _load_yaml("workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml")

    assert workflow["imports"] == {
        "approved_design_tranche_stack": "../library/major_project_tranche_plan_impl_from_approved_design_stack.yaml",
    }
    assert [step["name"] for step in workflow["steps"]] == [
        "SelectNextTranche",
        "AssertApprovedDesignMatchesSelectedTranche",
        "RunSelectedTrancheFromApprovedDesign",
        "UpdateTrancheManifest",
    ]
    assert "project_roadmap_path" in workflow["inputs"]
    assert "project_roadmap_target_path" not in workflow["inputs"]


def test_roadmap_phase_validates_manifest_before_review_and_after_revision():
    workflow = _load_yaml("workflows/library/major_project_roadmap_phase.yaml")

    top_level_names = [step["name"] for step in workflow["steps"]]
    assert top_level_names.index("ValidateDraftTrancheManifest") < top_level_names.index("RoadmapReviewLoop")

    validate_draft = _step_by_name(workflow, "ValidateDraftTrancheManifest")
    validate_revised = _step_by_name(workflow, "ValidateRevisedTrancheManifest")
    for step in (validate_draft, validate_revised):
        assert "workflows/library/scripts/validate_major_project_tranche_manifest.py" in step["command"]
        output_names = {field["name"] for field in step["expected_outputs"]}
        assert {
            "project_roadmap_path",
            "tranche_manifest_path",
            "validated_tranche_count",
            "ready_tranche_count",
        } <= output_names
        assert {publish["artifact"] for publish in step["publishes"]} == {
            "project_roadmap",
            "tranche_manifest",
        }


def test_major_project_prompt_references_are_bundled_assets():
    roadmap = _load_yaml("workflows/library/major_project_roadmap_phase.yaml")
    big_design = _load_yaml("workflows/library/tracked_big_design_phase.yaml")

    prompt_assets = {
        step["asset_file"]
        for workflow in (roadmap, big_design)
        for _, step in _walk_steps(workflow["steps"])
        if "asset_file" in step
    }

    assert prompt_assets == {
        "prompts/major_project_stack/draft_project_roadmap.md",
        "prompts/major_project_stack/review_project_roadmap.md",
        "prompts/major_project_stack/revise_project_roadmap.md",
        "prompts/major_project_stack/draft_big_design.md",
        "prompts/major_project_stack/review_big_design.md",
        "prompts/major_project_stack/revise_big_design.md",
    }


def test_big_design_draft_consumes_selected_tranche_and_project_context():
    workflow = _load_yaml("workflows/library/tracked_big_design_phase.yaml")

    draft_step = _step_by_name(workflow, "DraftBigDesign")

    assert draft_step["prompt_consumes"] == [
        "tranche_brief",
        "project_brief",
        "project_roadmap",
        "tranche_manifest",
    ]
    assert {consume["artifact"] for consume in draft_step["consumes"]} == {
        "tranche_brief",
        "project_brief",
        "project_roadmap",
        "tranche_manifest",
    }


def test_generic_plan_and_implementation_interfaces_stay_narrow():
    workflow = _load_yaml("workflows/library/major_project_tranche_design_plan_impl_stack.yaml")

    plan_call = _step_by_name(workflow, "RunPlanPhase")
    implementation_call = _step_by_name(workflow, "RunImplementationPhase")

    assert plan_call["call"] == "plan_phase"
    assert set(plan_call["with"]) == {
        "state_root",
        "design_path",
        "plan_target_path",
        "plan_review_report_target_path",
    }
    assert implementation_call["call"] == "implementation_phase"
    assert set(implementation_call["with"]) == {
        "state_root",
        "design_path",
        "plan_path",
        "execution_report_target_path",
        "implementation_review_report_target_path",
    }


def test_tranche_stack_does_not_convert_phase_call_failures_to_skipped_outcomes():
    workflow = _load_yaml("workflows/library/major_project_tranche_design_plan_impl_stack.yaml")

    run_big_design = _step_by_name(workflow, "RunBigDesignPhase")
    approve_gate = _step_by_name(workflow, "AssertBigDesignApproved")
    run_plan = _step_by_name(workflow, "RunPlanPhase")
    run_implementation = _step_by_name(workflow, "RunImplementationPhase")

    assert "on" not in run_big_design
    assert approve_gate["assert"] == {
        "compare": {
            "left": {"ref": "root.steps.RunBigDesignPhase.artifacts.design_review_decision"},
            "op": "eq",
            "right": "APPROVE",
        }
    }
    assert _on_config(approve_gate)["failure"]["goto"] == "FinalizeSkippedAfterDesign"
    assert "on" not in run_plan
    assert _on_config(run_implementation) == {"success": {"goto": "FinalizeApprovedItem"}}


def test_big_design_block_is_a_phase_decision_not_provider_failure():
    workflow = _load_yaml("workflows/library/tracked_big_design_phase.yaml")

    review_loop = _step_by_name(workflow, "BigDesignReviewLoop")
    block_case = review_loop["repeat_until"]["steps"][1]["match"]["cases"]["BLOCK"]

    assert review_loop["repeat_until"]["condition"] == {
        "any_of": [
            {
                "compare": {
                    "left": {"ref": "self.outputs.review_decision"},
                    "op": "eq",
                    "right": "APPROVE",
                }
            },
            {
                "compare": {
                    "left": {"ref": "self.outputs.review_decision"},
                    "op": "eq",
                    "right": "BLOCK",
                }
            },
        ]
    }
    assert [step["name"] for step in block_case["steps"]] == ["WriteBlockedBigDesignDecision"]


def test_big_design_runtime_carries_lowercase_open_findings(tmp_path: Path):
    workspace = tmp_path
    workflow_relpath = "workflows/library/tracked_big_design_phase.yaml"
    workflow_path = _copy_major_project_runtime_files(workspace, workflow_relpath)

    tranche_brief = workspace / "docs/backlog/generated/major-project-demo/repo-docs-baseline.md"
    project_brief = workspace / "workflows/examples/inputs/major_project_brief.md"
    project_roadmap = workspace / "docs/plans/major-project-demo/project-roadmap.md"
    tranche_manifest = workspace / "state/major-project-demo/tranche_manifest.json"

    tranche_brief.parent.mkdir(parents=True, exist_ok=True)
    tranche_brief.write_text("# Repo docs baseline\n", encoding="utf-8")
    project_roadmap.parent.mkdir(parents=True, exist_ok=True)
    project_roadmap.write_text("# Major project roadmap\n", encoding="utf-8")
    tranche_manifest.parent.mkdir(parents=True, exist_ok=True)
    tranche_manifest.write_text(
        json.dumps(
            {
                "project_id": "major-project-demo",
                "project_brief_path": project_brief.relative_to(workspace).as_posix(),
                "project_roadmap_path": project_roadmap.relative_to(workspace).as_posix(),
                "tranches": [
                    {
                        "tranche_id": "repo-docs-baseline",
                        "title": "Repository documentation baseline",
                        "brief_path": tranche_brief.relative_to(workspace).as_posix(),
                        "design_target_path": "docs/plans/major-project-demo/repo-docs-baseline-design.md",
                        "design_review_report_target_path": "artifacts/review/major-project-demo/repo-docs-baseline-design-review.json",
                        "plan_target_path": "docs/plans/major-project-demo/repo-docs-baseline-plan.md",
                        "plan_review_report_target_path": "artifacts/review/major-project-demo/repo-docs-baseline-plan-review.json",
                        "execution_report_target_path": "artifacts/work/major-project-demo/repo-docs-baseline-execution-report.md",
                        "implementation_review_report_target_path": "artifacts/review/major-project-demo/repo-docs-baseline-implementation-review.md",
                        "item_summary_target_path": "artifacts/work/major-project-demo/repo-docs-baseline-summary.json",
                        "prerequisites": [],
                        "status": "pending",
                        "design_depth": "big",
                        "completion_gate": "implementation_approved",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_relpath,
        bundle_context_dict(workflow),
        bound_inputs={
            "state_root": "state/major-project-demo/big-design-phase",
            "brief_path": tranche_brief.relative_to(workspace).as_posix(),
            "project_brief_path": project_brief.relative_to(workspace).as_posix(),
            "project_roadmap_path": project_roadmap.relative_to(workspace).as_posix(),
            "tranche_manifest_path": tranche_manifest.relative_to(workspace).as_posix(),
            "design_target_path": "docs/plans/major-project-demo/repo-docs-baseline-design.md",
            "design_review_report_target_path": "artifacts/review/major-project-demo/repo-docs-baseline-design-review.json",
        },
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    review_calls = {"count": 0}
    call_index = {"value": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **_kwargs):
        step_name = [
            "DraftBigDesign",
            "ReviewBigDesign",
            "RouteBigDesignDecision.REVISE.ReviseBigDesign",
            "ReviewBigDesign",
        ][call_index["value"]]
        call_index["value"] += 1
        if step_name == "DraftBigDesign":
            _target_from_pointer(workspace, "state/major-project-demo/big-design-phase/design_path.txt").write_text(
                "# Big design draft\n",
                encoding="utf-8",
            )
        elif step_name == "ReviewBigDesign":
            review_calls["count"] += 1
            if review_calls["count"] == 2:
                open_findings = json.loads(
                    (
                        workspace
                        / "state/major-project-demo/big-design-phase/open_findings.json"
                    ).read_text(encoding="utf-8")
                )
                assert open_findings["findings"] == [
                    {
                        "id": "DESIGN-H1",
                        "status": "open",
                        "severity": "high",
                        "title": "Lowercase unresolved finding should carry forward",
                    }
                ]

            report_relpath = (
                workspace / "state/major-project-demo/big-design-phase/design_review_report_path.txt"
            ).read_text(encoding="utf-8").strip()
            report_path = workspace / report_relpath
            report_path.parent.mkdir(parents=True, exist_ok=True)
            if review_calls["count"] == 1:
                payload = {
                    "decision": "REVISE",
                    "summary": "One unresolved finding remains.",
                    "unresolved_high_count": 1,
                    "unresolved_medium_count": 0,
                    "findings": [
                        {
                            "id": "DESIGN-H1",
                            "status": "open",
                            "severity": "high",
                            "title": "Lowercase unresolved finding should carry forward",
                        },
                        {
                            "id": "DESIGN-M1",
                            "status": "RESOLVED",
                            "severity": "medium",
                            "title": "Resolved finding should not carry forward",
                        },
                    ],
                }
            else:
                payload = {
                    "decision": "APPROVE",
                    "summary": "Design approved after revision.",
                    "unresolved_high_count": 0,
                    "unresolved_medium_count": 0,
                    "findings": [
                        {
                            "id": "DESIGN-H1",
                            "status": "RESOLVED",
                            "severity": "high",
                            "title": "Lowercase unresolved finding should carry forward",
                        }
                    ],
                }
            report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            (workspace / "state/major-project-demo/big-design-phase/design_review_decision.txt").write_text(
                f"{payload['decision']}\n", encoding="utf-8"
            )
            (workspace / "state/major-project-demo/big-design-phase/unresolved_high_count.txt").write_text(
                f"{payload['unresolved_high_count']}\n", encoding="utf-8"
            )
            (workspace / "state/major-project-demo/big-design-phase/unresolved_medium_count.txt").write_text(
                f"{payload['unresolved_medium_count']}\n", encoding="utf-8"
            )
        elif step_name == "RouteBigDesignDecision.REVISE.ReviseBigDesign":
            _target_from_pointer(workspace, "state/major-project-demo/big-design-phase/design_path.txt").write_text(
                "# Revised big design draft\n",
                encoding="utf-8",
            )
        else:
            raise AssertionError(f"Unexpected provider step {step_name!r}")

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

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["design_review_decision"] == "APPROVE"


def test_select_next_tranche_publishes_typed_handoff_fields():
    workflow = _load_yaml("workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml")
    selector = _step_by_name(workflow, "SelectNextTranche")

    fields = {field["name"]: field for field in selector["output_bundle"]["fields"]}

    assert fields["selection_status"]["type"] == "enum"
    assert fields["selection_status"]["allowed"] == ["SELECTED"]
    for name in [
        "project_brief_path",
        "project_roadmap_path",
        "tranche_manifest_path",
        "item_state_root",
        "big_design_phase_state_root",
        "plan_phase_state_root",
        "implementation_phase_state_root",
        "tranche_brief_path",
        "design_target_path",
        "design_review_report_target_path",
        "plan_target_path",
        "plan_review_report_target_path",
        "execution_report_target_path",
        "implementation_review_report_target_path",
        "item_summary_target_path",
    ]:
        assert name in fields


def test_drain_selector_publishes_selected_done_and_blocked_statuses():
    workflow = _load_yaml("workflows/examples/major_project_tranche_drain_stack_v2_call.yaml")
    selector = _step_by_name(workflow, "SelectNextTranche")
    router = _step_by_name(workflow, "RouteTrancheSelection")

    fields = {field["name"]: field for field in selector["output_bundle"]["fields"]}

    assert fields["selection_status"]["type"] == "enum"
    assert fields["selection_status"]["allowed"] == ["SELECTED", "DONE", "BLOCKED"]
    assert "selected_tranche_id" not in fields
    assert set(router["match"]["cases"]) == {"SELECTED", "DONE", "BLOCKED"}


def test_example_and_reusable_workflows_validate_with_loader():
    loader = WorkflowLoader(ROOT)

    for relpath in [
        "workflows/library/major_project_roadmap_phase.yaml",
        "workflows/library/tracked_big_design_phase.yaml",
        "workflows/library/major_project_tranche_design_plan_impl_stack.yaml",
        "workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml",
        "workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml",
        "workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml",
        "workflows/examples/major_project_tranche_drain_stack_v2_call.yaml",
        "workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml",
    ]:
        workflow = loader.load(ROOT / relpath)
        assert workflow.surface.steps, relpath


def test_major_project_example_runtime_with_mocked_providers(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(tmp_path)

    roadmap_root = "state/major-project-demo/roadmap-phase"
    tranche_id = "repo-docs-baseline"
    tranche_root = f"state/major-project-tranche-stack/major-project-demo/{tranche_id}"
    big_design_root = f"{tranche_root}/big-design-phase"
    plan_root = f"{tranche_root}/plan-phase"
    implementation_root = f"{tranche_root}/implementation-phase"

    def draft_project_roadmap(workspace: Path) -> None:
        roadmap = _target_from_pointer(workspace, f"{roadmap_root}/project_roadmap_path.txt")
        manifest = _target_from_pointer(workspace, f"{roadmap_root}/tranche_manifest_path.txt")
        tranche_brief = workspace / "docs/backlog/generated/major-project-demo/repo-docs-baseline.md"
        tranche_brief.parent.mkdir(parents=True, exist_ok=True)
        tranche_brief.write_text("# Repo docs baseline\n", encoding="utf-8")
        roadmap.write_text("# Major project roadmap\n", encoding="utf-8")
        manifest.write_text(
            json.dumps(
                {
                    "project_id": "major-project-demo",
                    "project_brief_path": "workflows/examples/inputs/major_project_brief.md",
                    "project_roadmap_path": "docs/plans/major-project-demo/project-roadmap.md",
                    "tranches": [
                        {
                            "tranche_id": tranche_id,
                            "title": "Repository documentation baseline",
                            "brief_path": "docs/backlog/generated/major-project-demo/repo-docs-baseline.md",
                            "design_target_path": f"docs/plans/major-project-demo/{tranche_id}-design.md",
                            "design_review_report_target_path": f"artifacts/review/major-project-demo/{tranche_id}-design-review.json",
                            "plan_target_path": f"docs/plans/major-project-demo/{tranche_id}-plan.md",
                            "plan_review_report_target_path": f"artifacts/review/major-project-demo/{tranche_id}-plan-review.json",
                            "execution_report_target_path": f"artifacts/work/major-project-demo/{tranche_id}-execution-report.md",
                            "implementation_review_report_target_path": f"artifacts/review/major-project-demo/{tranche_id}-implementation-review.md",
                            "item_summary_target_path": f"artifacts/work/major-project-demo/{tranche_id}-summary.json",
                            "prerequisites": [],
                            "status": "pending",
                            "design_depth": "big",
                            "completion_gate": "implementation_approved",
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    provider_sequence = [
        "DraftProjectRoadmap",
        "ReviewProjectRoadmap",
        "DraftBigDesign",
        "ReviewBigDesign",
        "DraftPlan",
        "ReviewPlanTracked",
        "ExecuteImplementation",
        "ReviewImplementation",
    ]
    provider_writers = {
        "DraftProjectRoadmap": draft_project_roadmap,
        "ReviewProjectRoadmap": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{roadmap_root}/roadmap_review_report_path.txt",
            decision_relpath=f"{roadmap_root}/roadmap_review_decision.txt",
            high_count_relpath=f"{roadmap_root}/unresolved_high_count.txt",
            medium_count_relpath=f"{roadmap_root}/unresolved_medium_count.txt",
        ),
        "DraftBigDesign": lambda ws: _target_from_pointer(ws, f"{big_design_root}/design_path.txt").write_text(
            "# Big design\n\nSelected tranche context included.\n",
            encoding="utf-8",
        ),
        "ReviewBigDesign": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{big_design_root}/design_review_report_path.txt",
            decision_relpath=f"{big_design_root}/design_review_decision.txt",
            high_count_relpath=f"{big_design_root}/unresolved_high_count.txt",
            medium_count_relpath=f"{big_design_root}/unresolved_medium_count.txt",
        ),
        "DraftPlan": lambda ws: _target_from_pointer(ws, f"{plan_root}/plan_path.txt").write_text(
            "# Plan\n",
            encoding="utf-8",
        ),
        "ReviewPlanTracked": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{plan_root}/plan_review_report_path.txt",
            decision_relpath=f"{plan_root}/plan_review_decision.txt",
            high_count_relpath=f"{plan_root}/unresolved_high_count.txt",
            medium_count_relpath=f"{plan_root}/unresolved_medium_count.txt",
        ),
        "ExecuteImplementation": lambda ws: _target_from_pointer(
            ws,
            f"{implementation_root}/execution_report_path.txt",
        ).write_text("# Execution report\n", encoding="utf-8"),
        "ReviewImplementation": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{implementation_root}/implementation_review_report_path.txt",
            decision_relpath=f"{implementation_root}/implementation_review_decision.txt",
            markdown=True,
        ),
    }

    state = _run_with_mocked_providers(tmp_path, workflow_path, provider_sequence, provider_writers)

    assert state["status"] == "completed"
    assert state["__provider_calls"] == len(provider_sequence)
    assert state["workflow_outputs"]["item_outcome"] == "APPROVED"
    assert state["workflow_outputs"]["execution_report_path"] == (
        f"artifacts/work/major-project-demo/{tranche_id}-execution-report.md"
    )
    assert state["steps"]["SelectNextTranche"]["artifacts"]["selection_status"] == "SELECTED"
    assert state["steps"]["RunSelectedTranche"]["artifacts"]["item_outcome"] == "APPROVED"


def test_continue_from_approved_design_runtime_with_mocked_providers(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml",
    )

    project_id = "major-project-demo"
    tranche_id = "repo-docs-baseline"
    drain_root = "state/major-project-demo/tranche-drain"
    item_root = f"{drain_root}/items/{project_id}/{tranche_id}"
    plan_root = f"{item_root}/plan-phase"
    implementation_root = f"{item_root}/implementation-phase"
    manifest_path = tmp_path / "state/major-project-demo/tranche_manifest.json"
    roadmap_path = tmp_path / "docs/plans/major-project-demo/project-roadmap.md"
    brief_path = tmp_path / "docs/backlog/generated/major-project-demo/repo-docs-baseline.md"
    design_path = tmp_path / "docs/plans/major-project-demo/repo-docs-baseline-design.md"

    roadmap_path.parent.mkdir(parents=True, exist_ok=True)
    roadmap_path.write_text("# Major project roadmap\n", encoding="utf-8")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# Repo docs baseline\n", encoding="utf-8")
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text("# Approved big design\n", encoding="utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "project_id": project_id,
                "project_brief_path": "workflows/examples/inputs/major_project_brief.md",
                "project_roadmap_path": "docs/plans/major-project-demo/project-roadmap.md",
                "tranches": [
                    {
                        "tranche_id": tranche_id,
                        "title": "Repository documentation baseline",
                        "brief_path": brief_path.relative_to(tmp_path).as_posix(),
                        "design_target_path": design_path.relative_to(tmp_path).as_posix(),
                        "design_review_report_target_path": (
                            f"artifacts/review/major-project-demo/{tranche_id}-design-review.json"
                        ),
                        "plan_target_path": f"docs/plans/major-project-demo/{tranche_id}-plan.md",
                        "plan_review_report_target_path": (
                            f"artifacts/review/major-project-demo/{tranche_id}-plan-review.json"
                        ),
                        "execution_report_target_path": (
                            f"artifacts/work/major-project-demo/{tranche_id}-execution-report.md"
                        ),
                        "implementation_review_report_target_path": (
                            f"artifacts/review/major-project-demo/{tranche_id}-implementation-review.md"
                        ),
                        "item_summary_target_path": f"artifacts/work/major-project-demo/{tranche_id}-summary.json",
                        "prerequisites": [],
                        "status": "pending",
                        "design_depth": "big",
                        "completion_gate": "implementation_approved",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    provider_sequence = [
        "DraftPlan",
        "ReviewPlanTracked",
        "ExecuteImplementation",
        "ReviewImplementation",
    ]
    provider_writers = {
        "DraftPlan": lambda ws: _target_from_pointer(ws, f"{plan_root}/plan_path.txt").write_text(
            "# Plan\n",
            encoding="utf-8",
        ),
        "ReviewPlanTracked": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{plan_root}/plan_review_report_path.txt",
            decision_relpath=f"{plan_root}/plan_review_decision.txt",
            high_count_relpath=f"{plan_root}/unresolved_high_count.txt",
            medium_count_relpath=f"{plan_root}/unresolved_medium_count.txt",
        ),
        "ExecuteImplementation": lambda ws: _target_from_pointer(
            ws,
            f"{implementation_root}/execution_report_path.txt",
        ).write_text("# Execution report\n", encoding="utf-8"),
        "ReviewImplementation": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{implementation_root}/implementation_review_report_path.txt",
            decision_relpath=f"{implementation_root}/implementation_review_decision.txt",
            markdown=True,
        ),
    }

    state = _run_with_mocked_providers(
        tmp_path,
        workflow_path,
        provider_sequence,
        provider_writers,
        bound_inputs={
            "project_brief_path": "workflows/examples/inputs/major_project_brief.md",
            "project_roadmap_path": "docs/plans/major-project-demo/project-roadmap.md",
            "tranche_manifest_target_path": "state/major-project-demo/tranche_manifest.json",
            "approved_design_path": "docs/plans/major-project-demo/repo-docs-baseline-design.md",
        },
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert state["status"] == "completed"
    assert state["__provider_calls"] == len(provider_sequence)
    assert state["workflow_outputs"]["drain_status"] == "CONTINUE"
    assert state["workflow_outputs"]["execution_report_path"] == (
        f"artifacts/work/major-project-demo/{tranche_id}-execution-report.md"
    )
    assert state["steps"]["RunSelectedTrancheFromApprovedDesign"]["artifacts"]["item_outcome"] == "APPROVED"
    assert manifest["tranches"][0]["status"] == "completed"


def test_drain_provider_failure_does_not_mark_tranche_blocked(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml",
    )

    project_id = "major-project-demo"
    tranche_id = "repo-docs-baseline"
    drain_root = "state/major-project-demo/tranche-drain"
    manifest_path = tmp_path / "state/major-project-demo/tranche_manifest.json"
    roadmap_path = tmp_path / "docs/plans/major-project-demo/project-roadmap.md"
    brief_path = tmp_path / "docs/backlog/generated/major-project-demo/repo-docs-baseline.md"

    roadmap_path.parent.mkdir(parents=True, exist_ok=True)
    roadmap_path.write_text("# Major project roadmap\n", encoding="utf-8")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# Repo docs baseline\n", encoding="utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "project_id": project_id,
                "project_brief_path": "workflows/examples/inputs/major_project_brief.md",
                "project_roadmap_path": "docs/plans/major-project-demo/project-roadmap.md",
                "tranches": [
                    {
                        "tranche_id": tranche_id,
                        "title": "Repository documentation baseline",
                        "brief_path": brief_path.relative_to(tmp_path).as_posix(),
                        "design_target_path": f"docs/plans/major-project-demo/{tranche_id}-design.md",
                        "design_review_report_target_path": (
                            f"artifacts/review/major-project-demo/{tranche_id}-design-review.json"
                        ),
                        "plan_target_path": f"docs/plans/major-project-demo/{tranche_id}-plan.md",
                        "plan_review_report_target_path": (
                            f"artifacts/review/major-project-demo/{tranche_id}-plan-review.json"
                        ),
                        "execution_report_target_path": (
                            f"artifacts/work/major-project-demo/{tranche_id}-execution-report.md"
                        ),
                        "implementation_review_report_target_path": (
                            f"artifacts/review/major-project-demo/{tranche_id}-implementation-review.md"
                        ),
                        "item_summary_target_path": f"artifacts/work/major-project-demo/{tranche_id}-summary.json",
                        "prerequisites": [],
                        "status": "pending",
                        "design_depth": "big",
                        "completion_gate": "implementation_approved",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    def draft_big_design(workspace: Path) -> None:
        pointer = next((workspace / drain_root / "items").glob("**/design_path.txt"))
        target = workspace / pointer.read_text(encoding="utf-8").strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Big design\n", encoding="utf-8")

    def review_big_design_then_provider_fails(workspace: Path) -> SimpleNamespace:
        pointer = next((workspace / drain_root / "items").glob("**/design_review_report_path.txt"))
        phase = pointer.parent
        _write_review_outputs(
            workspace,
            pointer_relpath=pointer.relative_to(workspace).as_posix(),
            decision_relpath=(phase / "design_review_decision.txt").relative_to(workspace).as_posix(),
            high_count_relpath=(phase / "unresolved_high_count.txt").relative_to(workspace).as_posix(),
            medium_count_relpath=(phase / "unresolved_medium_count.txt").relative_to(workspace).as_posix(),
        )
        return SimpleNamespace(
            exit_code=2,
            stdout=b"review wrote a report but provider crashed",
            stderr=b"mock provider failure",
            duration_ms=1,
            error={"type": "execution_error", "message": "mock provider failure"},
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    state = _run_with_mocked_providers(
        tmp_path,
        workflow_path,
        ["DraftBigDesign", "ReviewBigDesign"],
        {
            "DraftBigDesign": draft_big_design,
            "ReviewBigDesign": review_big_design_then_provider_fails,
        },
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item_root = tmp_path / drain_root / "items" / project_id / tranche_id

    assert state["status"] == "failed"
    assert manifest["tranches"][0]["status"] == "pending"
    assert "last_item_outcome" not in manifest["tranches"][0]
    assert not (item_root / "item_outcome.txt").exists()
    assert "UpdateTrancheManifest" not in state["steps"]


def test_major_project_drain_runtime_runs_roadmap_once_and_two_tranches(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/examples/major_project_tranche_drain_stack_v2_call.yaml",
    )

    roadmap_root = "state/major-project-demo/roadmap-phase"
    drain_root = "state/major-project-demo/tranche-drain"
    project_id = "major-project-demo"
    tranche_ids = ["repo-docs-baseline", "api-inventory"]

    def item_root(tranche_id: str) -> str:
        return f"{drain_root}/items/{project_id}/{tranche_id}"

    def phase_root(tranche_id: str, phase: str) -> str:
        return f"{item_root(tranche_id)}/{phase}"

    def draft_project_roadmap(workspace: Path) -> None:
        roadmap = _target_from_pointer(workspace, f"{roadmap_root}/project_roadmap_path.txt")
        manifest = _target_from_pointer(workspace, f"{roadmap_root}/tranche_manifest_path.txt")
        roadmap.write_text("# Major project roadmap\n", encoding="utf-8")
        tranches = []
        for index, tranche_id in enumerate(tranche_ids):
            brief = workspace / f"docs/backlog/generated/major-project-demo/{tranche_id}.md"
            brief.parent.mkdir(parents=True, exist_ok=True)
            brief.write_text(f"# {tranche_id}\n", encoding="utf-8")
            tranches.append(
                {
                    "tranche_id": tranche_id,
                    "title": tranche_id.replace("-", " ").title(),
                    "brief_path": brief.relative_to(workspace).as_posix(),
                    "design_target_path": f"docs/plans/major-project-demo/{tranche_id}-design.md",
                    "design_review_report_target_path": f"artifacts/review/major-project-demo/{tranche_id}-design-review.json",
                    "plan_target_path": f"docs/plans/major-project-demo/{tranche_id}-plan.md",
                    "plan_review_report_target_path": f"artifacts/review/major-project-demo/{tranche_id}-plan-review.json",
                    "execution_report_target_path": f"artifacts/work/major-project-demo/{tranche_id}-execution-report.md",
                    "implementation_review_report_target_path": (
                        f"artifacts/review/major-project-demo/{tranche_id}-implementation-review.md"
                    ),
                    "item_summary_target_path": f"artifacts/work/major-project-demo/{tranche_id}-summary.json",
                    "prerequisites": [] if index == 0 else [tranche_ids[index - 1]],
                    "status": "pending",
                    "design_depth": "big",
                    "completion_gate": "implementation_approved",
                }
            )
        manifest.write_text(
            json.dumps(
                {
                    "project_id": project_id,
                    "project_brief_path": "workflows/examples/inputs/major_project_brief.md",
                    "project_roadmap_path": "docs/plans/major-project-demo/project-roadmap.md",
                    "tranches": tranches,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def write_next_pointer_target(workspace: Path, pointer_name: str, content: str) -> None:
        for pointer in sorted((workspace / drain_root / "items").glob(f"**/{pointer_name}")):
            target = workspace / pointer.read_text(encoding="utf-8").strip()
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return
        raise AssertionError(f"No unwritten target for {pointer_name}")

    def write_next_review(
        workspace: Path,
        *,
        pointer_name: str,
        decision_name: str,
        markdown: bool = False,
    ) -> None:
        for pointer in sorted((workspace / drain_root / "items").glob(f"**/{pointer_name}")):
            phase = pointer.parent
            if not (phase / decision_name).exists():
                _write_review_outputs(
                    workspace,
                    pointer_relpath=pointer.relative_to(workspace).as_posix(),
                    decision_relpath=(phase / decision_name).relative_to(workspace).as_posix(),
                    high_count_relpath=(phase / "unresolved_high_count.txt").relative_to(workspace).as_posix()
                    if not markdown
                    else None,
                    medium_count_relpath=(phase / "unresolved_medium_count.txt").relative_to(workspace).as_posix()
                    if not markdown
                    else None,
                    markdown=markdown,
                )
                return
        raise AssertionError(f"No unwritten review for {pointer_name}")

    provider_sequence = [
        "DraftProjectRoadmap",
        "ReviewProjectRoadmap",
        "DraftBigDesign",
        "ReviewBigDesign",
        "DraftPlan",
        "ReviewPlanTracked",
        "ExecuteImplementation",
        "ReviewImplementation",
        "DraftBigDesign",
        "ReviewBigDesign",
        "DraftPlan",
        "ReviewPlanTracked",
        "ExecuteImplementation",
        "ReviewImplementation",
    ]
    provider_writers = {
        "DraftProjectRoadmap": draft_project_roadmap,
        "ReviewProjectRoadmap": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{roadmap_root}/roadmap_review_report_path.txt",
            decision_relpath=f"{roadmap_root}/roadmap_review_decision.txt",
            high_count_relpath=f"{roadmap_root}/unresolved_high_count.txt",
            medium_count_relpath=f"{roadmap_root}/unresolved_medium_count.txt",
        ),
        "DraftBigDesign": lambda ws: write_next_pointer_target(ws, "design_path.txt", "# Big design\n"),
        "ReviewBigDesign": lambda ws: write_next_review(
            ws,
            pointer_name="design_review_report_path.txt",
            decision_name="design_review_decision.txt",
        ),
        "DraftPlan": lambda ws: write_next_pointer_target(ws, "plan_path.txt", "# Plan\n"),
        "ReviewPlanTracked": lambda ws: write_next_review(
            ws,
            pointer_name="plan_review_report_path.txt",
            decision_name="plan_review_decision.txt",
        ),
        "ExecuteImplementation": lambda ws: write_next_pointer_target(
            ws,
            "execution_report_path.txt",
            "# Execution report\n",
        ),
        "ReviewImplementation": lambda ws: write_next_review(
            ws,
            pointer_name="implementation_review_report_path.txt",
            decision_name="implementation_review_decision.txt",
            markdown=True,
        ),
    }

    state = _run_with_mocked_providers(tmp_path, workflow_path, provider_sequence, provider_writers)

    assert state["status"] == "completed"
    assert state["__provider_calls"] == len(provider_sequence)
    assert state["workflow_outputs"]["drain_status"] == "DONE"
    assert (tmp_path / state["workflow_outputs"]["drain_summary_path"]).is_file()

    manifest = json.loads((tmp_path / "state/major-project-demo/tranche_manifest.json").read_text(encoding="utf-8"))
    assert [tranche["status"] for tranche in manifest["tranches"]] == ["completed", "completed"]
    assert [tranche["last_item_outcome"] for tranche in manifest["tranches"]] == ["APPROVED", "APPROVED"]
    assert (tmp_path / f"{phase_root(tranche_ids[0], 'implementation-phase')}/implementation_review_decision.txt").read_text(
        encoding="utf-8"
    ).strip() == "APPROVE"
