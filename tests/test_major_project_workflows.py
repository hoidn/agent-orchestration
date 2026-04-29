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
from workflows.library.scripts.major_project_scope_boundary import check_completion, write_scope_boundary


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


def _step_names(workflow: dict) -> set[str]:
    return {step["name"] for _, step in _walk_steps(workflow["steps"])}


def _bundle_field(step: dict, name: str) -> dict:
    fields = {field["name"]: field for field in step["output_bundle"]["fields"]}
    return fields[name]


def _all_allowed_values(node):
    if isinstance(node, dict):
        if isinstance(node.get("allowed"), list):
            yield node["allowed"]
        for value in node.values():
            yield from _all_allowed_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _all_allowed_values(value)


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
        "workflows/library/major_project_tranche_drain_iteration.yaml",
        "workflows/library/major_project_tranche_plan_phase.yaml",
        "workflows/library/major_project_tranche_implementation_phase.yaml",
        "workflows/library/major_project_roadmap_revision_phase.yaml",
        "workflows/library/tracked_plan_phase.yaml",
        "workflows/library/design_plan_impl_implementation_phase.yaml",
        "workflows/library/scripts/major_project_escalation_state.py",
        "workflows/library/scripts/major_project_phase_visits.py",
        "workflows/library/scripts/major_project_tranche_phase_routes.py",
        "workflows/library/scripts/major_project_scope_boundary.py",
        "workflows/library/scripts/publish_major_project_continue_outcome.py",
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
        "workflows/library/major_project_tranche_drain_iteration.yaml",
    ]:
        assert (ROOT / relpath).is_file(), relpath


def test_tranche_stack_uses_major_project_local_plan_and_implementation_phases():
    workflow = _load_yaml("workflows/library/major_project_tranche_design_plan_impl_stack.yaml")

    assert workflow["imports"] == {
        "big_design_phase": "tracked_big_design_phase.yaml",
        "plan_phase": "major_project_tranche_plan_phase.yaml",
        "implementation_phase": "major_project_tranche_implementation_phase.yaml",
    }


def test_approved_design_tranche_stack_uses_major_project_local_phases():
    workflow = _load_yaml("workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml")

    assert workflow["imports"] == {
        "phase_complete_tranche_stack": "major_project_tranche_design_plan_impl_stack.yaml",
    }


def test_major_project_implementation_phase_uses_adjacent_only_escalation():
    workflow = _load_yaml("workflows/library/major_project_tranche_implementation_phase.yaml")

    assert workflow["outputs"]["implementation_review_decision"]["allowed"] == [
        "APPROVE",
        "REVISE",
        "ESCALATE_REPLAN",
        "ESCALATE_ROADMAP_REVISION",
        "BLOCK",
    ]
    route_step = _step_by_name(workflow, "RouteImplementationDecision")
    assert set(route_step["match"]["cases"]) == {
        "APPROVE",
        "REVISE",
        "ESCALATE_REPLAN",
        "ESCALATE_ROADMAP_REVISION",
        "BLOCK",
    }
    assert "ESCALATE_REDESIGN" not in (ROOT / "workflows/library/major_project_tranche_implementation_phase.yaml").read_text(
        encoding="utf-8"
    )


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
        "drain_iteration": "../library/major_project_tranche_drain_iteration.yaml",
    }
    assert [step["name"] for step in workflow["steps"]] == [
        "RunRoadmapPhase",
        "DrainManifest",
        "PublishDrainSummary",
    ]

    drain = _step_by_name(workflow, "DrainManifest")
    body_names = [step["name"] for step in drain["repeat_until"]["steps"]]
    assert body_names == ["PrepareDrainIterationPaths", "RunDrainIteration"]
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
        "drain_iteration": "../library/major_project_tranche_drain_iteration.yaml",
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
        "RouteSelectedTrancheOutcome",
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
        "upstream_escalation_context",
    ]
    assert {consume["artifact"] for consume in draft_step["consumes"]} == {
        "tranche_brief",
        "project_brief",
        "project_roadmap",
        "tranche_manifest",
        "upstream_escalation_context",
    }


def test_major_project_plan_and_implementation_interfaces_include_escalation_context():
    workflow = _load_yaml("workflows/library/major_project_tranche_design_plan_impl_stack.yaml")

    plan_call = _step_by_name(workflow, "RunPlanPhase")
    implementation_call = _step_by_name(workflow, "RunImplementationPhase")

    assert plan_call["call"] == "plan_phase"
    assert set(plan_call["with"]) == {
        "state_root",
        "design_path",
        "scope_boundary_path",
        "project_roadmap_path",
        "tranche_manifest_path",
        "plan_target_path",
        "plan_review_report_target_path",
        "upstream_escalation_context_path",
    }
    assert plan_call["with"]["project_roadmap_path"] == {"ref": "inputs.project_roadmap_path"}
    assert plan_call["with"]["tranche_manifest_path"] == {"ref": "inputs.tranche_manifest_path"}
    assert implementation_call["call"] == "implementation_phase"
    assert set(implementation_call["with"]) == {
        "state_root",
        "design_path",
        "plan_path",
        "scope_boundary_path",
        "project_roadmap_path",
        "tranche_manifest_path",
        "execution_report_target_path",
        "implementation_review_report_target_path",
    }


def test_plan_and_implementation_phases_consume_scope_boundary():
    plan_workflow = _load_yaml("workflows/library/major_project_tranche_plan_phase.yaml")
    implementation_workflow = _load_yaml("workflows/library/major_project_tranche_implementation_phase.yaml")

    assert "scope_boundary_path" in plan_workflow["inputs"]
    assert "scope_boundary" in plan_workflow["artifacts"]
    assert "project_roadmap_path" in plan_workflow["inputs"]
    assert "tranche_manifest_path" in plan_workflow["inputs"]
    assert "project_roadmap" in plan_workflow["artifacts"]
    assert "tranche_manifest" in plan_workflow["artifacts"]
    assert "scope_boundary_path" in implementation_workflow["inputs"]
    assert "scope_boundary" in implementation_workflow["artifacts"]
    assert "project_roadmap_path" in implementation_workflow["inputs"]
    assert "tranche_manifest_path" in implementation_workflow["inputs"]
    assert "project_roadmap" in implementation_workflow["artifacts"]
    assert "tranche_manifest" in implementation_workflow["artifacts"]

    for step_name in ["DraftPlan", "ReviewPlanTracked", "RevisePlanTracked"]:
        step = _step_by_name(plan_workflow, step_name)
        assert "scope_boundary" in step["prompt_consumes"]
        assert "scope_boundary" in {consume["artifact"] for consume in step["consumes"]}
        assert "project_roadmap" in step["prompt_consumes"]
        assert "tranche_manifest" in step["prompt_consumes"]
        assert "project_roadmap" in {consume["artifact"] for consume in step["consumes"]}
        assert "tranche_manifest" in {consume["artifact"] for consume in step["consumes"]}

    for step_name in ["ExecuteImplementation", "ReviewImplementation", "FixImplementation"]:
        step = _step_by_name(implementation_workflow, step_name)
        assert "scope_boundary" in step["prompt_consumes"]
        assert "scope_boundary" in {consume["artifact"] for consume in step["consumes"]}

    review_step = _step_by_name(implementation_workflow, "ReviewImplementation")
    assert "project_roadmap" in review_step["prompt_consumes"]
    assert "tranche_manifest" in review_step["prompt_consumes"]
    assert "project_roadmap" in {consume["artifact"] for consume in review_step["consumes"]}
    assert "tranche_manifest" in {consume["artifact"] for consume in review_step["consumes"]}

    execute_step = _step_by_name(implementation_workflow, "ExecuteImplementation")
    assert "project_roadmap" not in execute_step["prompt_consumes"]
    assert "tranche_manifest" not in execute_step["prompt_consumes"]


def test_plan_phase_revision_keeps_underscoped_plan_from_approval(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/library/major_project_tranche_plan_phase.yaml",
    )

    phase_root = "state/direct/plan-phase"
    design = tmp_path / "docs/plans/direct/design.md"
    roadmap = tmp_path / "docs/plans/direct/project-roadmap.md"
    manifest = tmp_path / "state/direct/tranche_manifest.json"
    scope_boundary = tmp_path / "state/direct/scope_boundary.json"
    upstream = tmp_path / "state/direct/upstream.json"
    for path, content in [
        (design, "# Design\nFull public behavior is required.\n"),
        (roadmap, "# Roadmap\nT1 requires public behavior A, B, and C.\n"),
        (scope_boundary, json.dumps({"required_deliverables": ["A", "B", "C"]}) + "\n"),
        (upstream, json.dumps({"active": False}) + "\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "project_id": "direct",
                "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
                "tranches": [{"tranche_id": "T1", "status": "pending"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    review_count = {"value": 0}

    def review_plan(workspace: Path) -> None:
        review_count["value"] += 1
        assert (workspace / f"{phase_root}/project_roadmap_path.txt").is_file()
        assert (workspace / f"{phase_root}/tranche_manifest_path.txt").is_file()
        report = _target_from_pointer(workspace, f"{phase_root}/plan_review_report_path.txt")
        if review_count["value"] == 1:
            payload = {
                "decision": "REVISE",
                "summary": "Plan narrows roadmap scope to a first pass.",
                "unresolved_high_count": 1,
                "unresolved_medium_count": 0,
                "findings": [
                    {
                        "id": "PLAN-H1",
                        "status": "NEW",
                        "severity": "high",
                        "title": "Unauthorized first-pass scope narrowing",
                    }
                ],
            }
        else:
            payload = {
                "decision": "APPROVE",
                "summary": "Plan now covers the selected tranche boundary.",
                "unresolved_high_count": 0,
                "unresolved_medium_count": 0,
                "findings": [
                    {
                        "id": "PLAN-H1",
                        "status": "RESOLVED",
                        "severity": "high",
                        "title": "Unauthorized first-pass scope narrowing",
                    }
                ],
            }
        report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        (workspace / f"{phase_root}/plan_review_decision.txt").write_text(
            f"{payload['decision']}\n", encoding="utf-8"
        )
        (workspace / f"{phase_root}/unresolved_high_count.txt").write_text(
            f"{payload['unresolved_high_count']}\n", encoding="utf-8"
        )
        (workspace / f"{phase_root}/unresolved_medium_count.txt").write_text(
            f"{payload['unresolved_medium_count']}\n", encoding="utf-8"
        )

    provider_sequence = [
        "DraftPlan",
        "ReviewPlanTracked",
        "RoutePlanDecision.REVISE.RevisePlanTracked",
        "ReviewPlanTracked",
    ]
    provider_writers = {
        "DraftPlan": lambda ws: _target_from_pointer(ws, f"{phase_root}/plan_path.txt").write_text(
            "# Plan\n\nFirst pass: inventory only.\n",
            encoding="utf-8",
        ),
        "ReviewPlanTracked": review_plan,
        "RoutePlanDecision.REVISE.RevisePlanTracked": lambda ws: _target_from_pointer(
            ws,
            f"{phase_root}/plan_path.txt",
        ).write_text("# Plan\n\nImplement A, B, and C.\n", encoding="utf-8"),
    }

    state = _run_with_mocked_providers(
        tmp_path,
        workflow_path,
        provider_sequence,
        provider_writers,
        bound_inputs={
            "state_root": phase_root,
            "design_path": design.relative_to(tmp_path).as_posix(),
            "scope_boundary_path": scope_boundary.relative_to(tmp_path).as_posix(),
            "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
            "tranche_manifest_path": manifest.relative_to(tmp_path).as_posix(),
            "plan_target_path": "docs/plans/direct/plan.md",
            "plan_review_report_target_path": "artifacts/review/direct/plan-review.json",
            "upstream_escalation_context_path": upstream.relative_to(tmp_path).as_posix(),
        },
    )

    assert state["status"] == "completed"
    assert state["__provider_calls"] == len(provider_sequence)
    assert review_count["value"] == 2
    assert state["workflow_outputs"]["plan_review_decision"] == "APPROVE"


def test_plan_phase_routes_design_insufficient_boundary_to_redesign(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/library/major_project_tranche_plan_phase.yaml",
    )

    phase_root = "state/direct/plan-phase"
    design = tmp_path / "docs/plans/direct/design.md"
    roadmap = tmp_path / "docs/plans/direct/project-roadmap.md"
    manifest = tmp_path / "state/direct/tranche_manifest.json"
    scope_boundary = tmp_path / "state/direct/scope_boundary.json"
    upstream = tmp_path / "state/direct/upstream.json"
    for path, content in [
        (design, "# Design\nMissing architecture needed for full selected tranche.\n"),
        (roadmap, "# Roadmap\nFull tranche remains required.\n"),
        (scope_boundary, json.dumps({"required_deliverables": ["full tranche"]}) + "\n"),
        (upstream, json.dumps({"active": False}) + "\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "project_id": "direct",
                "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
                "tranches": [{"tranche_id": "T1", "status": "pending"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def review_plan(workspace: Path) -> None:
        report = _target_from_pointer(workspace, f"{phase_root}/plan_review_report_path.txt")
        report.write_text(
            json.dumps(
                {
                    "decision": "ESCALATE_REDESIGN",
                    "summary": "Design cannot support an executable full-boundary plan.",
                    "unresolved_high_count": 1,
                    "unresolved_medium_count": 0,
                    "findings": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (workspace / f"{phase_root}/plan_review_decision.txt").write_text(
            "ESCALATE_REDESIGN\n", encoding="utf-8"
        )
        (workspace / f"{phase_root}/unresolved_high_count.txt").write_text("1\n", encoding="utf-8")
        (workspace / f"{phase_root}/unresolved_medium_count.txt").write_text("0\n", encoding="utf-8")
        context = _target_from_pointer(workspace, f"{phase_root}/plan_escalation_context_path.txt")
        context.write_text(
            json.dumps(
                {
                    "active": True,
                    "source_phase": "plan",
                    "decision": "ESCALATE_REDESIGN",
                    "recommended_next_phase": "design_revision",
                    "reason_summary": "The approved design cannot plan the selected tranche boundary.",
                    "must_change": ["Revise design architecture."],
                    "evidence_paths": {"review_report": report.relative_to(workspace).as_posix()},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    provider_sequence = ["DraftPlan", "ReviewPlanTracked"]
    provider_writers = {
        "DraftPlan": lambda ws: _target_from_pointer(ws, f"{phase_root}/plan_path.txt").write_text(
            "# Plan\n\nCannot plan full boundary from current design.\n",
            encoding="utf-8",
        ),
        "ReviewPlanTracked": review_plan,
    }

    state = _run_with_mocked_providers(
        tmp_path,
        workflow_path,
        provider_sequence,
        provider_writers,
        bound_inputs={
            "state_root": phase_root,
            "design_path": design.relative_to(tmp_path).as_posix(),
            "scope_boundary_path": scope_boundary.relative_to(tmp_path).as_posix(),
            "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
            "tranche_manifest_path": manifest.relative_to(tmp_path).as_posix(),
            "plan_target_path": "docs/plans/direct/plan.md",
            "plan_review_report_target_path": "artifacts/review/direct/plan-review.json",
            "upstream_escalation_context_path": upstream.relative_to(tmp_path).as_posix(),
        },
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["plan_review_decision"] == "ESCALATE_REDESIGN"
    assert json.loads((tmp_path / f"{phase_root}/plan_escalation_context.json").read_text(encoding="utf-8"))[
        "active"
    ]


def test_tranche_stack_uses_current_phase_visit_roots_for_reentry():
    workflow = _load_yaml("workflows/library/major_project_tranche_design_plan_impl_stack.yaml")
    text = (ROOT / "workflows/library/major_project_tranche_design_plan_impl_stack.yaml").read_text(encoding="utf-8")

    assert _step_by_name(workflow, "RunBigDesignPhase")["with"]["state_root"] == {
        "ref": "self.steps.PrepareBigDesignVisit.artifacts.phase_state_root"
    }
    assert _step_by_name(workflow, "RunPlanPhase")["with"]["state_root"] == {
        "ref": "self.steps.PreparePlanVisit.artifacts.phase_state_root"
    }
    assert _step_by_name(workflow, "RunImplementationPhase")["with"]["state_root"] == {
        "ref": "self.steps.PrepareImplementationVisit.artifacts.phase_state_root"
    }

    route_step = _step_by_name(workflow, "RouteCurrentPhase")
    assert set(route_step["match"]["cases"]) == {"big_design", "plan", "implementation"}
    assert _step_by_name(workflow, "TranchePhaseLoop")["repeat_until"]["condition"]["compare"] == {
        "left": {"ref": "self.outputs.tranche_status"},
        "op": "ne",
        "right": "CONTINUE",
    }

    for stale_read in [
        "${inputs.big_design_phase_state_root}/final_design_review_decision.txt",
        "${inputs.plan_phase_state_root}/final_plan_review_decision.txt",
        "${inputs.implementation_phase_state_root}/final_implementation_review_decision.txt",
        "${inputs.plan_phase_state_root}/final_plan_escalation_context_path.txt",
        "${inputs.implementation_phase_state_root}/final_implementation_escalation_context_path.txt",
    ]:
        assert stale_read not in text
    helper_text = (ROOT / "workflows/library/scripts/major_project_phase_visits.py").read_text(encoding="utf-8")
    assert "current_{phase}_phase_state_root.txt" in helper_text


def test_full_tranche_stack_supports_configurable_initial_phase():
    workflow = _load_yaml("workflows/library/major_project_tranche_design_plan_impl_stack.yaml")

    assert workflow["inputs"]["initial_phase"] == {
        "kind": "scalar",
        "type": "enum",
        "allowed": ["big_design", "plan", "implementation"],
        "default": "big_design",
    }

    init_step = _step_by_name(workflow, "InitializeItemState")
    command_text = "\n".join(str(part) for part in init_step["command"])
    assert "${inputs.initial_phase}" in command_text
    assert "current_phase.txt" in command_text
    assert "if [ ! -f" in command_text or "if [ ! -s" in command_text


def test_approved_design_stack_delegates_to_phase_complete_stack():
    workflow = _load_yaml("workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml")

    assert workflow["imports"]["phase_complete_tranche_stack"] == "major_project_tranche_design_plan_impl_stack.yaml"
    assert "scope_boundary_path" in workflow["inputs"]
    assert "big_design_phase_state_root" in workflow["inputs"]
    assert "design_review_report_target_path" in workflow["inputs"]

    run_step = _step_by_name(workflow, "RunPhaseCompleteStackFromApprovedDesign")
    assert run_step["call"] == "phase_complete_tranche_stack"
    assert run_step["with"]["initial_phase"] == "plan"
    assert run_step["with"]["scope_boundary_path"] == {"ref": "inputs.scope_boundary_path"}
    assert run_step["with"]["design_target_path"] == {"ref": "inputs.design_path"}
    assert run_step["with"]["big_design_phase_state_root"] == {"ref": "inputs.big_design_phase_state_root"}
    assert run_step["with"]["design_review_report_target_path"] == {
        "ref": "inputs.design_review_report_target_path"
    }


def test_continue_from_approved_design_routes_redesign_roadmap_escalation_before_manifest_update():
    workflow = _load_yaml("workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml")

    run_step = _step_by_name(workflow, "RunSelectedTrancheFromApprovedDesign")
    assert run_step["with"]["scope_boundary_path"] == {
        "ref": "root.steps.SelectNextTranche.artifacts.scope_boundary_path"
    }
    assert run_step["with"]["big_design_phase_state_root"] == {
        "ref": "root.steps.SelectNextTranche.artifacts.big_design_phase_state_root"
    }
    assert run_step["with"]["design_review_report_target_path"] == {
        "ref": "root.steps.SelectNextTranche.artifacts.design_review_report_target_path"
    }

    route_step = _step_by_name(workflow, "RouteSelectedTrancheOutcome")
    assert set(route_step["match"]["cases"]) == {
        "APPROVED",
        "SKIPPED_AFTER_DESIGN",
        "SKIPPED_AFTER_PLAN",
        "SKIPPED_AFTER_IMPLEMENTATION",
        "ESCALATE_ROADMAP_REVISION",
    }


def test_tranche_stack_does_not_convert_phase_call_failures_to_skipped_outcomes():
    workflow = _load_yaml("workflows/library/major_project_tranche_design_plan_impl_stack.yaml")

    run_big_design = _step_by_name(workflow, "RunBigDesignPhase")
    run_plan = _step_by_name(workflow, "RunPlanPhase")
    run_implementation = _step_by_name(workflow, "RunImplementationPhase")

    assert "on" not in run_big_design
    assert "on" not in run_plan
    assert "on" not in run_implementation


def test_big_design_block_is_a_phase_decision_not_provider_failure():
    workflow = _load_yaml("workflows/library/tracked_big_design_phase.yaml")

    review_loop = _step_by_name(workflow, "BigDesignReviewLoop")
    route_step = next(
        step
        for step in review_loop["repeat_until"]["steps"]
        if step["name"] == "RouteBigDesignDecision"
    )
    block_case = route_step["match"]["cases"]["BLOCK"]

    assert review_loop["repeat_until"]["condition"]["any_of"][0]["compare"]["right"] == "APPROVE"
    assert review_loop["repeat_until"]["condition"]["any_of"][1]["compare"]["right"] == "ESCALATE_ROADMAP_REVISION"
    assert review_loop["repeat_until"]["condition"]["any_of"][2]["compare"]["right"] == "BLOCK"
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
            "upstream_escalation_context_path": "state/major-project-demo/upstream_escalation_context.json",
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


def test_big_design_runtime_ignores_provider_pointer_corruption(tmp_path: Path):
    workspace = tmp_path
    workflow_relpath = "workflows/library/tracked_big_design_phase.yaml"
    workflow_path = _copy_major_project_runtime_files(workspace, workflow_relpath)

    tranche_brief = workspace / "docs/backlog/generated/major-project-demo/repo-docs-baseline.md"
    project_brief = workspace / "workflows/examples/inputs/major_project_brief.md"
    project_roadmap = workspace / "docs/plans/major-project-demo/project-roadmap.md"
    tranche_manifest = workspace / "state/major-project-demo/tranche_manifest.json"
    canonical_review_relpath = "artifacts/review/major-project-demo/repo-docs-baseline-design-review.json"
    phase_root = "state/major-project-demo/big-design-phase"

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
                        "design_review_report_target_path": canonical_review_relpath,
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
            "state_root": phase_root,
            "brief_path": tranche_brief.relative_to(workspace).as_posix(),
            "project_brief_path": project_brief.relative_to(workspace).as_posix(),
            "project_roadmap_path": project_roadmap.relative_to(workspace).as_posix(),
            "tranche_manifest_path": tranche_manifest.relative_to(workspace).as_posix(),
            "design_target_path": "docs/plans/major-project-demo/repo-docs-baseline-design.md",
            "design_review_report_target_path": canonical_review_relpath,
            "upstream_escalation_context_path": "state/major-project-demo/upstream_escalation_context.json",
        },
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    call_index = {"value": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **_kwargs):
        step_name = ["DraftBigDesign", "ReviewBigDesign"][call_index["value"]]
        call_index["value"] += 1
        if step_name == "DraftBigDesign":
            _target_from_pointer(workspace, f"{phase_root}/design_path.txt").write_text(
                "# Big design draft\n",
                encoding="utf-8",
            )
        elif step_name == "ReviewBigDesign":
            review_path = workspace / canonical_review_relpath
            review_path.parent.mkdir(parents=True, exist_ok=True)
            review_path.write_text(
                json.dumps(
                    {
                        "decision": "APPROVE",
                        "summary": "Design approved.",
                        "findings": [],
                        "unresolved_high_count": 0,
                        "unresolved_medium_count": 0,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (workspace / f"{phase_root}/design_review_report_path.txt").write_text(
                "major-project-demo/repo-docs-baseline-design-review.json\n",
                encoding="utf-8",
            )
            (workspace / f"{phase_root}/design_review_decision.txt").write_text("APPROVE\n", encoding="utf-8")
            (workspace / f"{phase_root}/unresolved_high_count.txt").write_text("0\n", encoding="utf-8")
            (workspace / f"{phase_root}/unresolved_medium_count.txt").write_text("0\n", encoding="utf-8")
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
    assert state["workflow_outputs"]["design_review_report_path"] == canonical_review_relpath
    assert (workspace / f"{phase_root}/design_review_report_path.txt").read_text(encoding="utf-8").strip() == (
        canonical_review_relpath
    )


def test_roadmap_phase_runtime_ignores_provider_pointer_corruption(tmp_path: Path):
    workspace = tmp_path
    workflow_relpath = "workflows/library/major_project_roadmap_phase.yaml"
    workflow_path = _copy_major_project_runtime_files(workspace, workflow_relpath)

    project_brief = workspace / "workflows/examples/inputs/major_project_brief.md"
    phase_root = "state/major-project-demo/roadmap-phase"
    canonical_review_relpath = "artifacts/review/major-project-demo/project-roadmap-review.json"

    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_relpath,
        bundle_context_dict(workflow),
        bound_inputs={
            "state_root": phase_root,
            "project_brief_path": project_brief.relative_to(workspace).as_posix(),
            "project_roadmap_target_path": "docs/plans/major-project-demo/project-roadmap.md",
            "tranche_manifest_target_path": "state/major-project-demo/tranche_manifest.json",
            "roadmap_review_report_target_path": canonical_review_relpath,
        },
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)

    call_index = {"value": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **_kwargs):
        step_name = ["DraftProjectRoadmap", "ReviewProjectRoadmap"][call_index["value"]]
        call_index["value"] += 1
        if step_name == "DraftProjectRoadmap":
            roadmap = _target_from_pointer(workspace, f"{phase_root}/project_roadmap_path.txt")
            manifest = _target_from_pointer(workspace, f"{phase_root}/tranche_manifest_path.txt")
            brief = workspace / "docs/backlog/generated/major-project-demo/repo-docs-baseline.md"
            brief.parent.mkdir(parents=True, exist_ok=True)
            brief.write_text("# Repo docs baseline\n", encoding="utf-8")
            roadmap.write_text("# Major project roadmap\n", encoding="utf-8")
            manifest.write_text(
                json.dumps(
                    {
                        "project_id": "major-project-demo",
                        "project_brief_path": project_brief.relative_to(workspace).as_posix(),
                        "project_roadmap_path": "docs/plans/major-project-demo/project-roadmap.md",
                        "tranches": [
                            {
                                "tranche_id": "repo-docs-baseline",
                                "title": "Repository documentation baseline",
                                "brief_path": brief.relative_to(workspace).as_posix(),
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
        elif step_name == "ReviewProjectRoadmap":
            review_path = workspace / canonical_review_relpath
            review_path.parent.mkdir(parents=True, exist_ok=True)
            review_path.write_text(
                json.dumps(
                    {
                        "decision": "APPROVE",
                        "summary": "Roadmap approved.",
                        "findings": [],
                        "unresolved_high_count": 0,
                        "unresolved_medium_count": 0,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (workspace / f"{phase_root}/roadmap_review_report_path.txt").write_text(
                "major-project-demo/project-roadmap-review.json\n",
                encoding="utf-8",
            )
            (workspace / f"{phase_root}/roadmap_review_decision.txt").write_text("APPROVE\n", encoding="utf-8")
            (workspace / f"{phase_root}/unresolved_high_count.txt").write_text("0\n", encoding="utf-8")
            (workspace / f"{phase_root}/unresolved_medium_count.txt").write_text("0\n", encoding="utf-8")
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
    assert state["workflow_outputs"]["roadmap_review_report_path"] == canonical_review_relpath
    assert (workspace / f"{phase_root}/roadmap_review_report_path.txt").read_text(encoding="utf-8").strip() == (
        canonical_review_relpath
    )


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
        "scope_boundary_path",
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
    workflow = _load_yaml("workflows/library/major_project_tranche_drain_iteration.yaml")
    selector = _step_by_name(workflow, "SelectNextTranche")
    router = _step_by_name(workflow, "RouteSelection")

    fields = {field["name"]: field for field in selector["output_bundle"]["fields"]}

    assert fields["selection_status"]["type"] == "enum"
    assert fields["selection_status"]["allowed"] == ["SELECTED", "DONE", "BLOCKED"]
    assert fields["scope_boundary_path"]["type"] == "relpath"
    assert "selected_tranche_id" not in fields
    assert set(router["match"]["cases"]) == {"SELECTED", "DONE", "BLOCKED"}


def test_drain_iteration_dispatches_roadmap_revision_at_top_level():
    workflow = _load_yaml("workflows/library/major_project_tranche_drain_iteration.yaml")

    assert workflow["imports"] == {
        "tranche_stack": "major_project_tranche_design_plan_impl_stack.yaml",
        "roadmap_revision_phase": "major_project_roadmap_revision_phase.yaml",
    }
    assert [step["name"] for step in workflow["steps"]] == [
        "SelectNextTranche",
        "RouteSelection",
        "RouteIterationOutcome",
    ]
    outcome_router = _step_by_name(workflow, "RouteIterationOutcome")
    assert set(outcome_router["match"]["cases"]) == {
        "APPROVED",
        "SKIPPED_AFTER_DESIGN",
        "SKIPPED_AFTER_PLAN",
        "SKIPPED_AFTER_IMPLEMENTATION",
        "ESCALATE_ROADMAP_REVISION",
        "DONE",
        "BLOCKED",
    }
    roadmap_case = outcome_router["match"]["cases"]["ESCALATE_ROADMAP_REVISION"]
    assert [step["name"] for step in roadmap_case["steps"]] == [
        "RunRoadmapRevision",
        "PromoteRoadmapRevision",
    ]


def test_roadmap_revision_phase_uses_single_advisory_review():
    workflow = _load_yaml("workflows/library/major_project_roadmap_revision_phase.yaml")

    assert [step["name"] for step in workflow["steps"]] == [
        "InitializeRoadmapRevisionPaths",
        "DraftRoadmapRevision",
        "ReviewRoadmapRevision",
        "FinalizeRoadmapRevisionOutputs",
    ]
    assert "repeat_until" not in _step_by_name(workflow, "ReviewRoadmapRevision")
    assert "RoadmapRevisionReviewLoop" not in [step["name"] for step in workflow["steps"]]


def test_neurips_implementation_phase_uses_terminal_implementation_states():
    workflow = _load_yaml("workflows/library/neurips_backlog_implementation_phase.yaml")
    execute = _step_by_name(workflow, "ExecuteImplementation")
    write_state = _step_by_name(workflow, "WriteImplementationState")
    finalize = _step_by_name(workflow, "FinalizeImplementationPhaseOutputs")
    fix = _step_by_name(workflow, "FixImplementation")

    assert workflow["outputs"]["implementation_state"]["allowed"] == ["COMPLETED", "BLOCKED"]
    assert _bundle_field(execute, "implementation_state")["allowed"] == ["COMPLETED", "BLOCKED"]
    assert write_state["expected_outputs"][0]["allowed"] == ["COMPLETED", "BLOCKED"]
    assert finalize["expected_outputs"][0]["allowed"] == ["COMPLETED", "BLOCKED"]
    assert execute["timeout_sec"] == 86400
    assert fix["timeout_sec"] == 86400
    assert "PublishProgressReport" not in _step_names(workflow)


def test_neurips_selected_item_does_not_emit_waiting_status():
    workflow = _load_yaml("workflows/library/neurips_selected_backlog_item.yaml")

    assert workflow["outputs"]["drain_status"]["allowed"] == ["CONTINUE", "BLOCKED"]
    assert "RecordImplementationWaiting" not in _step_names(workflow)
    for allowed in _all_allowed_values(workflow):
        assert "WAITING" not in allowed


def test_neurips_top_level_drain_does_not_emit_waiting_status():
    workflow = _load_yaml("workflows/examples/neurips_steered_backlog_drain.yaml")

    assert workflow["outputs"]["drain_status"]["allowed"] == ["CONTINUE", "DONE", "BLOCKED"]
    assert workflow["artifacts"]["drain_status"]["allowed"] == ["CONTINUE", "DONE", "BLOCKED"]
    for allowed in _all_allowed_values(workflow):
        assert "WAITING" not in allowed


def test_drain_iteration_promotes_roadmap_revision_for_any_advisory_decision():
    workflow = _load_yaml("workflows/library/major_project_tranche_drain_iteration.yaml")
    outcome_router = _step_by_name(workflow, "RouteIterationOutcome")
    roadmap_case = outcome_router["match"]["cases"]["ESCALATE_ROADMAP_REVISION"]
    promote = next(step for step in roadmap_case["steps"] if step["name"] == "PromoteRoadmapRevision")
    script = "\n".join(promote["command"])

    assert 'case "$decision" in' in script
    assert "APPROVE|REVISE|BLOCK" in script
    assert 'if [ "$decision" = "APPROVE" ]' not in script
    assert 'printf \'%s\\n\' CONTINUE' in script
    assert 'cp "$roadmap_candidate" "${inputs.project_roadmap_path}"' in script
    assert 'cp "$manifest_candidate" "${inputs.tranche_manifest_path}"' in script

    output_names = {output["name"] for output in promote["expected_outputs"]}
    assert {"drain_status", "roadmap_revision_decision", "roadmap_revision_report_path"} <= output_names


def test_scope_boundary_helper_derives_selected_tranche_boundary(tmp_path: Path):
    manifest_path = tmp_path / "state/demo/tranche_manifest.json"
    brief_path = tmp_path / "docs/backlog/generated/demo/t1.md"
    boundary_path = tmp_path / "state/demo/items/t1/scope_boundary.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# T1 brief\nImplement the public behavior.\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "project_id": "demo",
                "project_brief_path": "docs/backlog/demo.md",
                "project_roadmap_path": "docs/plans/demo.md",
                "tranches": [
                    {
                        "tranche_id": "T1-public-behavior",
                        "title": "Public behavior",
                        "brief_path": brief_path.relative_to(tmp_path).as_posix(),
                        "completion_gate": "implementation_approved",
                        "status": "pending",
                        "prerequisites": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = write_scope_boundary(
        root=tmp_path,
        tranche_manifest_path=manifest_path.relative_to(tmp_path).as_posix(),
        tranche_brief_path=brief_path.relative_to(tmp_path).as_posix(),
        scope_boundary_path=boundary_path.relative_to(tmp_path).as_posix(),
    )

    assert payload["tranche_id"] == "T1-public-behavior"
    assert payload["completion_gate"] == "implementation_approved"
    assert payload["required_deliverables"]
    assert boundary_path.is_file()


def test_completion_guard_rejects_approved_slice_with_unapproved_deferred_work(tmp_path: Path):
    boundary = tmp_path / "state/demo/items/t1/scope_boundary.json"
    execution_report = tmp_path / "artifacts/work/demo/execution.md"
    review_report = tmp_path / "artifacts/review/demo/review.md"
    for path in (boundary, execution_report, review_report):
        path.parent.mkdir(parents=True, exist_ok=True)
    boundary.write_text(
        json.dumps(
            {
                "tranche_id": "T1",
                "required_deliverables": ["public solver"],
                "required_evidence": [],
                "authorized_deferred_work": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    execution_report.write_text("Task 3 is done. Exact public solver work remains deferred and blocked.\n", encoding="utf-8")
    review_report.write_text("Decision: APPROVE\nBroader exact-runtime blockers remain deferred.\n", encoding="utf-8")

    result = check_completion(
        root=tmp_path,
        scope_boundary_path=boundary.relative_to(tmp_path).as_posix(),
        implementation_decision="APPROVE",
        execution_report_path=execution_report.relative_to(tmp_path).as_posix(),
        implementation_review_report_path=review_report.relative_to(tmp_path).as_posix(),
    )

    assert result["completion_status"] == "SCOPE_MISMATCH"
    assert result["recommended_route"] == "escalate_roadmap_revision"


def test_completion_guard_allows_roadmap_authorized_deferral(tmp_path: Path):
    boundary = tmp_path / "state/demo/items/t1/scope_boundary.json"
    execution_report = tmp_path / "artifacts/work/demo/execution.md"
    review_report = tmp_path / "artifacts/review/demo/review.md"
    for path in (boundary, execution_report, review_report):
        path.parent.mkdir(parents=True, exist_ok=True)
    boundary.write_text(
        json.dumps(
            {
                "tranche_id": "T1",
                "required_deliverables": ["public solver"],
                "required_evidence": [],
                "authorized_deferred_work": [
                    {"work": "CUDA promotion", "authority": "roadmap", "handoff": "T1A"}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    execution_report.write_text("CPU work complete. CUDA promotion remains deferred to T1A.\n", encoding="utf-8")
    review_report.write_text("Decision: APPROVE\n", encoding="utf-8")

    result = check_completion(
        root=tmp_path,
        scope_boundary_path=boundary.relative_to(tmp_path).as_posix(),
        implementation_decision="APPROVE",
        execution_report_path=execution_report.relative_to(tmp_path).as_posix(),
        implementation_review_report_path=review_report.relative_to(tmp_path).as_posix(),
    )

    assert result["completion_status"] == "COMPLETE"
    assert result["recommended_route"] == "complete"


def test_example_and_reusable_workflows_validate_with_loader():
    loader = WorkflowLoader(ROOT)

    for relpath in [
        "workflows/library/major_project_roadmap_phase.yaml",
        "workflows/library/tracked_big_design_phase.yaml",
        "workflows/library/major_project_tranche_design_plan_impl_stack.yaml",
        "workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml",
        "workflows/library/major_project_tranche_drain_iteration.yaml",
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
    big_design_root = f"{tranche_root}/big-design-phase/visits/0000"
    plan_root = f"{tranche_root}/plan-phase/visits/0000"
    implementation_root = f"{tranche_root}/implementation-phase/visits/0000"

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
    plan_root = f"{item_root}/plan-phase/visits/0000"
    implementation_root = f"{item_root}/implementation-phase/visits/0000"
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


def test_continue_from_approved_design_runtime_routes_plan_escalation_to_redesign(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml",
    )

    project_id = "major-project-demo"
    tranche_id = "repo-docs-baseline"
    drain_root = "state/major-project-demo/tranche-drain"
    item_root = f"{drain_root}/items/{project_id}/{tranche_id}"
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

    def current_root(workspace: Path, phase: str) -> str:
        return (workspace / item_root / f"current_{phase}_phase_state_root.txt").read_text(encoding="utf-8").strip()

    def write_pointer_target(workspace: Path, phase: str, pointer_name: str, content: str) -> None:
        root = current_root(workspace, phase)
        _target_from_pointer(workspace, f"{root}/{pointer_name}").write_text(content, encoding="utf-8")

    plan_review_count = {"value": 0}

    def review_plan(workspace: Path) -> None:
        root = current_root(workspace, "plan")
        plan_review_count["value"] += 1
        if plan_review_count["value"] == 1:
            report = _target_from_pointer(workspace, f"{root}/plan_review_report_path.txt")
            report.write_text(
                json.dumps(
                    {
                        "decision": "ESCALATE_REDESIGN",
                        "summary": "The approved design cannot support an executable plan.",
                        "findings": [
                            {
                                "severity": "high",
                                "summary": "Design gap",
                                "detail": "Runtime regression forces redesign.",
                            }
                        ],
                        "unresolved_high_count": 1,
                        "unresolved_medium_count": 0,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (workspace / root / "plan_review_decision.txt").write_text("ESCALATE_REDESIGN\n", encoding="utf-8")
            (workspace / root / "unresolved_high_count.txt").write_text("1\n", encoding="utf-8")
            (workspace / root / "unresolved_medium_count.txt").write_text("0\n", encoding="utf-8")
            context = _target_from_pointer(workspace, f"{root}/plan_escalation_context_path.txt")
            context.write_text(
                json.dumps(
                    {
                        "active": True,
                        "source_phase": "plan",
                        "decision": "ESCALATE_REDESIGN",
                        "recommended_next_phase": "design_revision",
                        "reason_summary": "Approved-design continuation needs a redesign pass.",
                        "must_change": ["Revise the design before planning again."],
                        "evidence_paths": {"review_report": report.relative_to(workspace).as_posix()},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return
        _write_review_outputs(
            workspace,
            pointer_relpath=f"{root}/plan_review_report_path.txt",
            decision_relpath=f"{root}/plan_review_decision.txt",
            high_count_relpath=f"{root}/unresolved_high_count.txt",
            medium_count_relpath=f"{root}/unresolved_medium_count.txt",
        )

    provider_sequence = [
        "DraftPlan",
        "ReviewPlanTracked",
        "DraftBigDesign",
        "ReviewBigDesign",
        "DraftPlan",
        "ReviewPlanTracked",
        "ExecuteImplementation",
        "ReviewImplementation",
    ]
    provider_writers = {
        "DraftPlan": lambda ws: write_pointer_target(ws, "plan", "plan_path.txt", "# Plan\n"),
        "ReviewPlanTracked": review_plan,
        "DraftBigDesign": lambda ws: write_pointer_target(ws, "big_design", "design_path.txt", "# Redesigned\n"),
        "ReviewBigDesign": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{current_root(ws, 'big_design')}/design_review_report_path.txt",
            decision_relpath=f"{current_root(ws, 'big_design')}/design_review_decision.txt",
            high_count_relpath=f"{current_root(ws, 'big_design')}/unresolved_high_count.txt",
            medium_count_relpath=f"{current_root(ws, 'big_design')}/unresolved_medium_count.txt",
        ),
        "ExecuteImplementation": lambda ws: write_pointer_target(
            ws,
            "implementation",
            "execution_report_path.txt",
            "# Execution report\n",
        ),
        "ReviewImplementation": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{current_root(ws, 'implementation')}/implementation_review_report_path.txt",
            decision_relpath=f"{current_root(ws, 'implementation')}/implementation_review_decision.txt",
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

    ledger = json.loads((tmp_path / item_root / "phase_visit_ledger.json").read_text(encoding="utf-8"))
    plan_roots = [visit["state_root"] for visit in ledger["visits"] if visit["phase"] == "plan"]
    big_design_roots = [visit["state_root"] for visit in ledger["visits"] if visit["phase"] == "big_design"]
    implementation_roots = [visit["state_root"] for visit in ledger["visits"] if visit["phase"] == "implementation"]

    assert state["status"] == "completed"
    assert state["__provider_calls"] == len(provider_sequence)
    assert state["workflow_outputs"]["drain_status"] == "CONTINUE"
    assert state["steps"]["RunSelectedTrancheFromApprovedDesign"]["artifacts"]["item_outcome"] == "APPROVED"
    assert (tmp_path / item_root / "current_phase.txt").read_text(encoding="utf-8").strip() == "implementation"
    assert design_path.read_text(encoding="utf-8").startswith("# Redesigned")
    assert plan_roots == [f"{item_root}/plan-phase/visits/0000", f"{item_root}/plan-phase/visits/0001"]
    assert big_design_roots == [f"{item_root}/big-design-phase/visits/0000"]
    assert implementation_roots == [f"{item_root}/implementation-phase/visits/0000"]


def test_continue_from_approved_design_runtime_blocks_on_redesign_roadmap_escalation(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml",
    )

    project_id = "major-project-demo"
    tranche_id = "repo-docs-baseline"
    drain_root = "state/major-project-demo/tranche-drain"
    item_root = f"{drain_root}/items/{project_id}/{tranche_id}"
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

    def current_root(workspace: Path, phase: str) -> str:
        return (workspace / item_root / f"current_{phase}_phase_state_root.txt").read_text(encoding="utf-8").strip()

    def write_pointer_target(workspace: Path, phase: str, pointer_name: str, content: str) -> None:
        root = current_root(workspace, phase)
        _target_from_pointer(workspace, f"{root}/{pointer_name}").write_text(content, encoding="utf-8")

    def review_plan_escalates(workspace: Path) -> None:
        root = current_root(workspace, "plan")
        report = _target_from_pointer(workspace, f"{root}/plan_review_report_path.txt")
        report.write_text(
            json.dumps(
                {
                    "decision": "ESCALATE_REDESIGN",
                    "summary": "Plan requires redesign.",
                    "findings": [],
                    "unresolved_high_count": 1,
                    "unresolved_medium_count": 0,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (workspace / root / "plan_review_decision.txt").write_text("ESCALATE_REDESIGN\n", encoding="utf-8")
        (workspace / root / "unresolved_high_count.txt").write_text("1\n", encoding="utf-8")
        (workspace / root / "unresolved_medium_count.txt").write_text("0\n", encoding="utf-8")
        context = _target_from_pointer(workspace, f"{root}/plan_escalation_context_path.txt")
        context.write_text(
            json.dumps(
                {
                    "active": True,
                    "source_phase": "plan",
                    "decision": "ESCALATE_REDESIGN",
                    "recommended_next_phase": "design_revision",
                    "reason_summary": "Plan review escalated to redesign.",
                    "must_change": ["Revisit roadmap-level tranche shape."],
                    "evidence_paths": {"review_report": report.relative_to(workspace).as_posix()},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def review_big_design_escalates_to_roadmap(workspace: Path) -> None:
        root = current_root(workspace, "big_design")
        report = _target_from_pointer(workspace, f"{root}/design_review_report_path.txt")
        report.write_text(
            json.dumps(
                {
                    "decision": "ESCALATE_ROADMAP_REVISION",
                    "summary": "The tranche needs roadmap revision.",
                    "findings": [],
                    "unresolved_high_count": 1,
                    "unresolved_medium_count": 0,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (workspace / root / "design_review_decision.txt").write_text("ESCALATE_ROADMAP_REVISION\n", encoding="utf-8")
        (workspace / root / "unresolved_high_count.txt").write_text("1\n", encoding="utf-8")
        (workspace / root / "unresolved_medium_count.txt").write_text("0\n", encoding="utf-8")
        request = _target_from_pointer(workspace, f"{root}/roadmap_change_request_path.txt")
        request.write_text(
            json.dumps(
                {
                    "active": True,
                    "source_phase": "design",
                    "decision": "ESCALATE_ROADMAP_REVISION",
                    "reason_summary": "Roadmap shape must change.",
                    "requested_program_change": "Split the tranche.",
                    "requested_changes": ["Split the tranche."],
                    "superseded_tranche_ids": [tranche_id],
                    "proposed_new_tranche_ids": [f"{tranche_id}-a", f"{tranche_id}-b"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    provider_sequence = [
        "DraftPlan",
        "ReviewPlanTracked",
        "DraftBigDesign",
        "ReviewBigDesign",
    ]
    provider_writers = {
        "DraftPlan": lambda ws: write_pointer_target(ws, "plan", "plan_path.txt", "# Plan\n"),
        "ReviewPlanTracked": review_plan_escalates,
        "DraftBigDesign": lambda ws: write_pointer_target(ws, "big_design", "design_path.txt", "# Redesigned\n"),
        "ReviewBigDesign": review_big_design_escalates_to_roadmap,
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
    assert state["workflow_outputs"]["drain_status"] == "BLOCKED"
    assert state["steps"]["RunSelectedTrancheFromApprovedDesign"]["artifacts"]["item_outcome"] == (
        "ESCALATE_ROADMAP_REVISION"
    )
    assert state["steps"]["RouteSelectedTrancheOutcome"]["artifacts"]["item_outcome"] == "ESCALATE_ROADMAP_REVISION"
    assert manifest["tranches"][0]["status"] == "pending"
    assert (tmp_path / item_root / "final_roadmap_change_request_path.txt").is_file()


def test_tranche_stack_replan_runtime_uses_second_active_plan_visit(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/library/major_project_tranche_design_plan_impl_stack.yaml",
    )

    item_root = "state/direct/item"
    project_brief = tmp_path / "workflows/examples/inputs/major_project_brief.md"
    roadmap = tmp_path / "docs/plans/direct/project-roadmap.md"
    manifest = tmp_path / "state/direct/tranche_manifest.json"
    brief = tmp_path / "docs/backlog/generated/direct/tranche.md"
    for path, content in [
        (project_brief, "# Project brief\n"),
        (roadmap, "# Roadmap\n"),
        (brief, "# Tranche brief\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "project_id": "direct",
                "project_brief_path": project_brief.relative_to(tmp_path).as_posix(),
                "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
                "tranches": [
                    {
                        "tranche_id": "direct-tranche",
                        "title": "Direct tranche",
                        "brief_path": brief.relative_to(tmp_path).as_posix(),
                        "status": "pending",
                        "completion_gate": "implementation_approved",
                        "prerequisites": [],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def current_root(workspace: Path, phase: str) -> str:
        return (workspace / item_root / f"current_{phase}_phase_state_root.txt").read_text(encoding="utf-8").strip()

    def write_pointer_target(workspace: Path, phase: str, pointer_name: str, content: str) -> None:
        root = current_root(workspace, phase)
        _target_from_pointer(workspace, f"{root}/{pointer_name}").write_text(content, encoding="utf-8")

    implementation_review_count = {"value": 0}

    def review_implementation(workspace: Path) -> None:
        root = current_root(workspace, "implementation")
        implementation_review_count["value"] += 1
        if implementation_review_count["value"] == 1:
            report = _target_from_pointer(workspace, f"{root}/implementation_review_report_path.txt")
            report.write_text("# Implementation review\n", encoding="utf-8")
            (workspace / root / "implementation_review_decision.txt").write_text("ESCALATE_REPLAN\n", encoding="utf-8")
            context_path = _target_from_pointer(workspace, f"{root}/implementation_escalation_context_path.txt")
            context_path.write_text(
                json.dumps(
                    {
                        "active": True,
                        "source_phase": "implementation",
                        "decision": "ESCALATE_REPLAN",
                        "recommended_next_phase": "plan_revision",
                        "reason_summary": "runtime regression replan",
                        "must_change": ["plan"],
                        "evidence_paths": {"review_report": report.relative_to(workspace).as_posix()},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return
        _write_review_outputs(
            workspace,
            pointer_relpath=f"{root}/implementation_review_report_path.txt",
            decision_relpath=f"{root}/implementation_review_decision.txt",
            markdown=True,
        )

    provider_sequence = [
        "DraftBigDesign",
        "ReviewBigDesign",
        "DraftPlan",
        "ReviewPlanTracked",
        "ExecuteImplementation",
        "ReviewImplementation",
        "DraftPlan",
        "ReviewPlanTracked",
        "ExecuteImplementation",
        "ReviewImplementation",
    ]
    provider_writers = {
        "DraftBigDesign": lambda ws: write_pointer_target(ws, "big_design", "design_path.txt", "# Big design\n"),
        "ReviewBigDesign": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{current_root(ws, 'big_design')}/design_review_report_path.txt",
            decision_relpath=f"{current_root(ws, 'big_design')}/design_review_decision.txt",
            high_count_relpath=f"{current_root(ws, 'big_design')}/unresolved_high_count.txt",
            medium_count_relpath=f"{current_root(ws, 'big_design')}/unresolved_medium_count.txt",
        ),
        "DraftPlan": lambda ws: write_pointer_target(ws, "plan", "plan_path.txt", "# Plan\n"),
        "ReviewPlanTracked": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{current_root(ws, 'plan')}/plan_review_report_path.txt",
            decision_relpath=f"{current_root(ws, 'plan')}/plan_review_decision.txt",
            high_count_relpath=f"{current_root(ws, 'plan')}/unresolved_high_count.txt",
            medium_count_relpath=f"{current_root(ws, 'plan')}/unresolved_medium_count.txt",
        ),
        "ExecuteImplementation": lambda ws: write_pointer_target(
            ws,
            "implementation",
            "execution_report_path.txt",
            "# Execution report\n",
        ),
        "ReviewImplementation": review_implementation,
    }

    state = _run_with_mocked_providers(
        tmp_path,
        workflow_path,
        provider_sequence,
        provider_writers,
        bound_inputs={
            "item_state_root": item_root,
            "scope_boundary_path": f"{item_root}/scope_boundary.json",
            "upstream_escalation_context_path": f"{item_root}/upstream_escalation_context.json",
            "big_design_phase_state_root": f"{item_root}/big-design-phase",
            "plan_phase_state_root": f"{item_root}/plan-phase",
            "implementation_phase_state_root": f"{item_root}/implementation-phase",
            "project_brief_path": project_brief.relative_to(tmp_path).as_posix(),
            "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
            "tranche_manifest_path": manifest.relative_to(tmp_path).as_posix(),
            "tranche_brief_path": brief.relative_to(tmp_path).as_posix(),
            "design_target_path": "docs/plans/direct/design.md",
            "design_review_report_target_path": "artifacts/review/direct/design-review.json",
            "plan_target_path": "docs/plans/direct/plan.md",
            "plan_review_report_target_path": "artifacts/review/direct/plan-review.json",
            "execution_report_target_path": "artifacts/work/direct/execution.md",
            "implementation_review_report_target_path": "artifacts/review/direct/implementation-review.md",
            "item_summary_target_path": "artifacts/work/direct/summary.json",
        },
    )

    ledger = json.loads((tmp_path / item_root / "phase_visit_ledger.json").read_text(encoding="utf-8"))
    plan_roots = [visit["state_root"] for visit in ledger["visits"] if visit["phase"] == "plan"]
    implementation_roots = [visit["state_root"] for visit in ledger["visits"] if visit["phase"] == "implementation"]

    assert state["status"] == "completed"
    assert (tmp_path / item_root / "item_outcome.txt").read_text(encoding="utf-8").strip() == "APPROVED"
    assert plan_roots == [f"{item_root}/plan-phase/visits/0000", f"{item_root}/plan-phase/visits/0001"]
    assert implementation_roots == [
        f"{item_root}/implementation-phase/visits/0000",
        f"{item_root}/implementation-phase/visits/0001",
    ]
    assert (tmp_path / item_root / "current_plan_phase_state_root.txt").read_text(encoding="utf-8").strip() == (
        f"{item_root}/plan-phase/visits/0001"
    )


def test_tranche_stack_routes_implementation_roadmap_escalation(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/library/major_project_tranche_design_plan_impl_stack.yaml",
    )

    item_root = "state/direct/item"
    project_brief = tmp_path / "workflows/examples/inputs/major_project_brief.md"
    roadmap = tmp_path / "docs/plans/direct/project-roadmap.md"
    manifest = tmp_path / "state/direct/tranche_manifest.json"
    brief = tmp_path / "docs/backlog/generated/direct/tranche.md"
    for path, content in [
        (project_brief, "# Project brief\n"),
        (roadmap, "# Roadmap\n"),
        (brief, "# Tranche brief\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "project_id": "direct",
                "project_brief_path": project_brief.relative_to(tmp_path).as_posix(),
                "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
                "tranches": [
                    {
                        "tranche_id": "direct-tranche",
                        "title": "Direct tranche",
                        "brief_path": brief.relative_to(tmp_path).as_posix(),
                        "status": "pending",
                        "completion_gate": "implementation_approved",
                        "prerequisites": [],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def current_root(workspace: Path, phase: str) -> str:
        return (workspace / item_root / f"current_{phase}_phase_state_root.txt").read_text(encoding="utf-8").strip()

    def write_pointer_target(workspace: Path, phase: str, pointer_name: str, content: str) -> None:
        root = current_root(workspace, phase)
        _target_from_pointer(workspace, f"{root}/{pointer_name}").write_text(content, encoding="utf-8")

    def review_implementation_escalates(workspace: Path) -> None:
        root = current_root(workspace, "implementation")
        report = _target_from_pointer(workspace, f"{root}/implementation_review_report_path.txt")
        report.write_text("# Implementation review\nScope must be split at roadmap level.\n", encoding="utf-8")
        (workspace / root / "implementation_review_decision.txt").write_text(
            "ESCALATE_ROADMAP_REVISION\n",
            encoding="utf-8",
        )
        context_path = _target_from_pointer(workspace, f"{root}/implementation_escalation_context_path.txt")
        context_path.write_text(
            json.dumps(
                {
                    "active": True,
                    "source_phase": "implementation",
                    "decision": "ESCALATE_ROADMAP_REVISION",
                    "reason_summary": "scope split required",
                    "must_change": ["split selected tranche"],
                    "evidence_paths": {"review_report": report.relative_to(workspace).as_posix()},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    provider_sequence = [
        "DraftBigDesign",
        "ReviewBigDesign",
        "DraftPlan",
        "ReviewPlanTracked",
        "ExecuteImplementation",
        "ReviewImplementation",
    ]
    provider_writers = {
        "DraftBigDesign": lambda ws: write_pointer_target(ws, "big_design", "design_path.txt", "# Big design\n"),
        "ReviewBigDesign": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{current_root(ws, 'big_design')}/design_review_report_path.txt",
            decision_relpath=f"{current_root(ws, 'big_design')}/design_review_decision.txt",
            high_count_relpath=f"{current_root(ws, 'big_design')}/unresolved_high_count.txt",
            medium_count_relpath=f"{current_root(ws, 'big_design')}/unresolved_medium_count.txt",
        ),
        "DraftPlan": lambda ws: write_pointer_target(ws, "plan", "plan_path.txt", "# Plan\n"),
        "ReviewPlanTracked": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{current_root(ws, 'plan')}/plan_review_report_path.txt",
            decision_relpath=f"{current_root(ws, 'plan')}/plan_review_decision.txt",
            high_count_relpath=f"{current_root(ws, 'plan')}/unresolved_high_count.txt",
            medium_count_relpath=f"{current_root(ws, 'plan')}/unresolved_medium_count.txt",
        ),
        "ExecuteImplementation": lambda ws: write_pointer_target(
            ws,
            "implementation",
            "execution_report_path.txt",
            "# Execution report\n",
        ),
        "ReviewImplementation": review_implementation_escalates,
    }

    state = _run_with_mocked_providers(
        tmp_path,
        workflow_path,
        provider_sequence,
        provider_writers,
        bound_inputs={
            "item_state_root": item_root,
            "scope_boundary_path": f"{item_root}/scope_boundary.json",
            "upstream_escalation_context_path": f"{item_root}/upstream_escalation_context.json",
            "big_design_phase_state_root": f"{item_root}/big-design-phase",
            "plan_phase_state_root": f"{item_root}/plan-phase",
            "implementation_phase_state_root": f"{item_root}/implementation-phase",
            "project_brief_path": project_brief.relative_to(tmp_path).as_posix(),
            "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
            "tranche_manifest_path": manifest.relative_to(tmp_path).as_posix(),
            "tranche_brief_path": brief.relative_to(tmp_path).as_posix(),
            "design_target_path": "docs/plans/direct/design.md",
            "design_review_report_target_path": "artifacts/review/direct/design-review.json",
            "plan_target_path": "docs/plans/direct/plan.md",
            "plan_review_report_target_path": "artifacts/review/direct/plan-review.json",
            "execution_report_target_path": "artifacts/work/direct/execution.md",
            "implementation_review_report_target_path": "artifacts/review/direct/implementation-review.md",
            "item_summary_target_path": "artifacts/work/direct/summary.json",
        },
    )

    assert state["status"] == "completed"
    assert (tmp_path / item_root / "item_outcome.txt").read_text(encoding="utf-8").strip() == (
        "ESCALATE_ROADMAP_REVISION"
    )
    assert (tmp_path / item_root / "final_roadmap_change_request_path.txt").is_file()


def test_tranche_stack_completion_guard_escalates_approved_slice_with_deferred_scope(tmp_path: Path):
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/library/major_project_tranche_design_plan_impl_stack.yaml",
    )

    item_root = "state/direct/item"
    project_brief = tmp_path / "workflows/examples/inputs/major_project_brief.md"
    roadmap = tmp_path / "docs/plans/direct/project-roadmap.md"
    manifest = tmp_path / "state/direct/tranche_manifest.json"
    brief = tmp_path / "docs/backlog/generated/direct/tranche.md"
    for path, content in [
        (project_brief, "# Project brief\n"),
        (roadmap, "# Roadmap\n"),
        (brief, "# Tranche brief\n"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "project_id": "direct",
                "project_brief_path": project_brief.relative_to(tmp_path).as_posix(),
                "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
                "tranches": [
                    {
                        "tranche_id": "direct-tranche",
                        "title": "Direct tranche",
                        "brief_path": brief.relative_to(tmp_path).as_posix(),
                        "status": "pending",
                        "completion_gate": "implementation_approved",
                        "prerequisites": [],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def current_root(workspace: Path, phase: str) -> str:
        return (workspace / item_root / f"current_{phase}_phase_state_root.txt").read_text(encoding="utf-8").strip()

    def write_pointer_target(workspace: Path, phase: str, pointer_name: str, content: str) -> None:
        root = current_root(workspace, phase)
        _target_from_pointer(workspace, f"{root}/{pointer_name}").write_text(content, encoding="utf-8")

    def review_implementation_approves_deferred_scope(workspace: Path) -> None:
        root = current_root(workspace, "implementation")
        report = _target_from_pointer(workspace, f"{root}/implementation_review_report_path.txt")
        report.write_text(
            "Decision: APPROVE\nTasks 4 and 5 remain real work and are still deferred.\n",
            encoding="utf-8",
        )
        (workspace / root / "implementation_review_decision.txt").write_text("APPROVE\n", encoding="utf-8")

    provider_sequence = [
        "DraftBigDesign",
        "ReviewBigDesign",
        "DraftPlan",
        "ReviewPlanTracked",
        "ExecuteImplementation",
        "ReviewImplementation",
    ]
    provider_writers = {
        "DraftBigDesign": lambda ws: write_pointer_target(ws, "big_design", "design_path.txt", "# Big design\n"),
        "ReviewBigDesign": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{current_root(ws, 'big_design')}/design_review_report_path.txt",
            decision_relpath=f"{current_root(ws, 'big_design')}/design_review_decision.txt",
            high_count_relpath=f"{current_root(ws, 'big_design')}/unresolved_high_count.txt",
            medium_count_relpath=f"{current_root(ws, 'big_design')}/unresolved_medium_count.txt",
        ),
        "DraftPlan": lambda ws: write_pointer_target(ws, "plan", "plan_path.txt", "# Plan\n"),
        "ReviewPlanTracked": lambda ws: _write_review_outputs(
            ws,
            pointer_relpath=f"{current_root(ws, 'plan')}/plan_review_report_path.txt",
            decision_relpath=f"{current_root(ws, 'plan')}/plan_review_decision.txt",
            high_count_relpath=f"{current_root(ws, 'plan')}/unresolved_high_count.txt",
            medium_count_relpath=f"{current_root(ws, 'plan')}/unresolved_medium_count.txt",
        ),
        "ExecuteImplementation": lambda ws: write_pointer_target(
            ws,
            "implementation",
            "execution_report_path.txt",
            "# Execution report\nTask 3 is complete. Public solver closure remains deferred and blocked.\n",
        ),
        "ReviewImplementation": review_implementation_approves_deferred_scope,
    }

    state = _run_with_mocked_providers(
        tmp_path,
        workflow_path,
        provider_sequence,
        provider_writers,
        bound_inputs={
            "item_state_root": item_root,
            "scope_boundary_path": f"{item_root}/scope_boundary.json",
            "upstream_escalation_context_path": f"{item_root}/upstream_escalation_context.json",
            "big_design_phase_state_root": f"{item_root}/big-design-phase",
            "plan_phase_state_root": f"{item_root}/plan-phase",
            "implementation_phase_state_root": f"{item_root}/implementation-phase",
            "project_brief_path": project_brief.relative_to(tmp_path).as_posix(),
            "project_roadmap_path": roadmap.relative_to(tmp_path).as_posix(),
            "tranche_manifest_path": manifest.relative_to(tmp_path).as_posix(),
            "tranche_brief_path": brief.relative_to(tmp_path).as_posix(),
            "design_target_path": "docs/plans/direct/design.md",
            "design_review_report_target_path": "artifacts/review/direct/design-review.json",
            "plan_target_path": "docs/plans/direct/plan.md",
            "plan_review_report_target_path": "artifacts/review/direct/plan-review.json",
            "execution_report_target_path": "artifacts/work/direct/execution.md",
            "implementation_review_report_target_path": "artifacts/review/direct/implementation-review.md",
            "item_summary_target_path": "artifacts/work/direct/summary.json",
        },
    )

    guard = json.loads((tmp_path / item_root / "completion_guard.json").read_text(encoding="utf-8"))

    assert state["status"] == "completed"
    assert guard["completion_status"] == "SCOPE_MISMATCH"
    assert (tmp_path / item_root / "item_outcome.txt").read_text(encoding="utf-8").strip() == (
        "ESCALATE_ROADMAP_REVISION"
    )
    assert (tmp_path / item_root / "final_roadmap_change_request_path.txt").is_file()


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


def _write_stub_escalating_tranche_stack(workspace: Path) -> None:
    stub = workspace / "workflows/library/major_project_tranche_design_plan_impl_stack.yaml"
    stub.write_text(
        """
version: "2.12"
name: "stub-escalating-tranche-stack"

inputs:
  item_state_root: {type: relpath, under: state}
  scope_boundary_path: {type: relpath, under: state}
  upstream_escalation_context_path: {type: relpath, under: state}
  big_design_phase_state_root: {type: relpath, under: state}
  plan_phase_state_root: {type: relpath, under: state}
  implementation_phase_state_root: {type: relpath, under: state}
  project_brief_path: {type: relpath, must_exist_target: true}
  project_roadmap_path: {type: relpath, must_exist_target: true}
  tranche_manifest_path: {type: relpath, must_exist_target: true}
  tranche_brief_path: {type: relpath, must_exist_target: true}
  design_target_path: {type: relpath, under: docs/plans}
  design_review_report_target_path: {type: relpath, under: artifacts/review}
  plan_target_path: {type: relpath, under: docs/plans}
  plan_review_report_target_path: {type: relpath, under: artifacts/review}
  execution_report_target_path: {type: relpath, under: artifacts/work}
  implementation_review_report_target_path: {type: relpath, under: artifacts/review}
  item_summary_target_path: {type: relpath, under: artifacts/work}

outputs:
  item_outcome:
    kind: scalar
    type: enum
    allowed: ["APPROVED", "SKIPPED_AFTER_DESIGN", "SKIPPED_AFTER_PLAN", "SKIPPED_AFTER_IMPLEMENTATION", "ESCALATE_ROADMAP_REVISION"]
    from:
      ref: root.steps.PublishEscalation.artifacts.item_outcome
  execution_report_path:
    type: relpath
    under: artifacts/work
    must_exist_target: true
    from:
      ref: root.steps.PublishEscalation.artifacts.execution_report_path
  item_summary_path:
    type: relpath
    under: artifacts/work
    must_exist_target: true
    from:
      ref: root.steps.PublishEscalation.artifacts.item_summary_path
  roadmap_change_request_path:
    type: relpath
    under: state
    must_exist_target: true
    from:
      ref: root.steps.PublishEscalation.artifacts.roadmap_change_request_path

steps:
  - name: PublishEscalation
    id: publish_escalation
    command:
      - bash
      - -lc
      - |
        mkdir -p "${inputs.item_state_root}" "$(dirname "${inputs.execution_report_target_path}")" "$(dirname "${inputs.item_summary_target_path}")"
        printf '%s\\n' ESCALATE_ROADMAP_REVISION > "${inputs.item_state_root}/item_outcome.txt"
        printf 'execution\\n' > "${inputs.execution_report_target_path}"
        printf 'summary\\n' > "${inputs.item_summary_target_path}"
        printf '%s\\n' "${inputs.execution_report_target_path}" > "${inputs.item_state_root}/execution_report_path.txt"
        printf '%s\\n' "${inputs.item_summary_target_path}" > "${inputs.item_state_root}/item_summary_path.txt"
        printf '%s\\n' "${inputs.item_state_root}/roadmap_change_request.json" > "${inputs.item_state_root}/final_roadmap_change_request_path.txt"
        cat > "${inputs.item_state_root}/roadmap_change_request.json" <<'JSON'
        {
          "active": true,
          "source_phase": "design",
          "decision": "ESCALATE_ROADMAP_REVISION",
          "reason_summary": "stub escalation",
          "requested_changes": ["revise roadmap"]
        }
        JSON
    expected_outputs:
      - name: item_outcome
        path: ${inputs.item_state_root}/item_outcome.txt
        type: enum
        allowed: ["APPROVED", "SKIPPED_AFTER_DESIGN", "SKIPPED_AFTER_PLAN", "SKIPPED_AFTER_IMPLEMENTATION", "ESCALATE_ROADMAP_REVISION"]
      - name: execution_report_path
        path: ${inputs.item_state_root}/execution_report_path.txt
        type: relpath
        under: artifacts/work
        must_exist_target: true
      - name: item_summary_path
        path: ${inputs.item_state_root}/item_summary_path.txt
        type: relpath
        under: artifacts/work
        must_exist_target: true
      - name: roadmap_change_request_path
        path: ${inputs.item_state_root}/final_roadmap_change_request_path.txt
        type: relpath
        under: state
        must_exist_target: true
""".lstrip(),
        encoding="utf-8",
    )


def _run_roadmap_revision_advisory_promotion(tmp_path: Path, decision: str) -> dict:
    workflow_path = _copy_major_project_runtime_files(
        tmp_path,
        "workflows/library/major_project_tranche_drain_iteration.yaml",
    )
    _write_stub_escalating_tranche_stack(tmp_path)

    project_id = "major-project-demo"
    tranche_id = "repo-docs-baseline"
    drain_root = "state/major-project-demo/tranche-drain"
    iteration_root = f"{drain_root}/iterations/0"
    manifest_path = tmp_path / "state/major-project-demo/tranche_manifest.json"
    roadmap_path = tmp_path / "docs/plans/major-project-demo/project-roadmap.md"
    brief_path = tmp_path / "docs/backlog/generated/major-project-demo/repo-docs-baseline.md"

    roadmap_path.parent.mkdir(parents=True, exist_ok=True)
    roadmap_path.write_text("# Original roadmap\n", encoding="utf-8")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# Repo docs baseline\n", encoding="utf-8")
    manifest = {
        "project_id": project_id,
        "project_brief_path": "workflows/examples/inputs/major_project_brief.md",
        "project_roadmap_path": "docs/plans/major-project-demo/project-roadmap.md",
        "tranches": [
            {
                "tranche_id": tranche_id,
                "title": "Repository documentation baseline",
                "brief_path": brief_path.relative_to(tmp_path).as_posix(),
                "design_target_path": f"docs/plans/major-project-demo/{tranche_id}-design.md",
                "design_review_report_target_path": f"artifacts/review/major-project-demo/{tranche_id}-design-review.json",
                "plan_target_path": f"docs/plans/major-project-demo/{tranche_id}-plan.md",
                "plan_review_report_target_path": f"artifacts/review/major-project-demo/{tranche_id}-plan-review.json",
                "execution_report_target_path": f"artifacts/work/major-project-demo/{tranche_id}-execution-report.md",
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
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def draft_roadmap_revision(workspace: Path) -> None:
        candidate_roadmap = _target_from_pointer(
            workspace,
            f"{iteration_root}/roadmap-revision-phase/updated_project_roadmap_path.txt",
        )
        candidate_manifest = _target_from_pointer(
            workspace,
            f"{iteration_root}/roadmap-revision-phase/updated_tranche_manifest_path.txt",
        )
        candidate_roadmap.write_text(f"# Revised roadmap for {decision}\n", encoding="utf-8")
        revised_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        revised_manifest["advisory_decision_seen"] = decision
        candidate_manifest.write_text(json.dumps(revised_manifest, indent=2) + "\n", encoding="utf-8")

    def review_roadmap_revision(workspace: Path) -> None:
        report = _target_from_pointer(
            workspace,
            f"{iteration_root}/roadmap-revision-phase/roadmap_revision_report_path.txt",
        )
        report.write_text(
            json.dumps(
                {
                    "decision": decision,
                    "summary": f"Advisory {decision.lower()} for test.",
                    "findings": [{"severity": "medium", "title": "carried forward"}],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (workspace / f"{iteration_root}/roadmap-revision-phase/roadmap_revision_decision.txt").write_text(
            f"{decision}\n",
            encoding="utf-8",
        )

    state = _run_with_mocked_providers(
        tmp_path,
        workflow_path,
        ["DraftRoadmapRevision", "ReviewRoadmapRevision"],
        {
            "DraftRoadmapRevision": draft_roadmap_revision,
            "ReviewRoadmapRevision": review_roadmap_revision,
        },
        bound_inputs={
            "project_brief_path": "workflows/examples/inputs/major_project_brief.md",
            "project_roadmap_path": "docs/plans/major-project-demo/project-roadmap.md",
            "tranche_manifest_path": "state/major-project-demo/tranche_manifest.json",
            "drain_state_root": drain_root,
            "iteration_state_root": iteration_root,
            "roadmap_change_request_path": f"{iteration_root}/roadmap_change_request.json",
            "roadmap_revision_state_root": f"{iteration_root}/roadmap-revision-phase",
            "updated_project_roadmap_candidate_path": (
                "docs/plans/major-project-roadmap-revision-candidates/test-project-roadmap.md"
            ),
            "updated_tranche_manifest_candidate_path": f"{iteration_root}/roadmap-revision/tranche-manifest.candidate.json",
            "roadmap_revision_report_target_path": "artifacts/review/major-project-roadmap-revision/test.json",
        },
    )
    return state


def test_roadmap_revision_revise_promotes_candidate(tmp_path: Path):
    state = _run_roadmap_revision_advisory_promotion(tmp_path, "REVISE")

    manifest = json.loads((tmp_path / "state/major-project-demo/tranche_manifest.json").read_text(encoding="utf-8"))

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["drain_status"] == "CONTINUE"
    assert (tmp_path / "docs/plans/major-project-demo/project-roadmap.md").read_text(encoding="utf-8") == (
        "# Revised roadmap for REVISE\n"
    )
    assert manifest["advisory_decision_seen"] == "REVISE"
    assert (
        tmp_path / "state/major-project-demo/tranche-drain/iterations/0/roadmap_revision_decision.txt"
    ).read_text(encoding="utf-8").strip() == "REVISE"


def test_roadmap_revision_block_promotes_candidate(tmp_path: Path):
    state = _run_roadmap_revision_advisory_promotion(tmp_path, "BLOCK")

    manifest = json.loads((tmp_path / "state/major-project-demo/tranche_manifest.json").read_text(encoding="utf-8"))

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["drain_status"] == "CONTINUE"
    assert (tmp_path / "docs/plans/major-project-demo/project-roadmap.md").read_text(encoding="utf-8") == (
        "# Revised roadmap for BLOCK\n"
    )
    assert manifest["advisory_decision_seen"] == "BLOCK"
    assert (
        tmp_path / "state/major-project-demo/tranche-drain/iterations/0/roadmap_revision_decision.txt"
    ).read_text(encoding="utf-8").strip() == "BLOCK"


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
    assert (
        tmp_path / f"{phase_root(tranche_ids[0], 'implementation-phase')}/visits/0000/implementation_review_decision.txt"
    ).read_text(encoding="utf-8").strip() == "APPROVE"
