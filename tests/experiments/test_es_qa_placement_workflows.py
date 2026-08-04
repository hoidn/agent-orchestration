"""Compiler/runtime contract for the E-series four-cell QA-placement study."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, is_dataclass
import importlib.util
from pathlib import Path
from threading import Lock
from types import ModuleType
from typing import Any, Mapping, cast
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderParams
from orchestrator.state import StateManager
from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow.executable_ir import TrialStepConfig
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_context,
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.run_ref.bundle_transport import (
    write_bundle_capsule_directory,
)
from orchestrator.workflow.run_ref.contracts import (
    PostSetupBaselineIdentity,
    RepositoryRevisionId,
    VerifiedGitTreeIdentity,
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.run_ref.runtime import (
    RunRefChildLaunch,
    RunRefChildProcessResult,
    RunRefRuntimeDependencies,
)
from orchestrator.workflow.run_ref.source import (
    MaterializedSource,
    SourceRequest,
    canonical_source_request,
)
from orchestrator.workflow.run_ref.workspace import freeze_tree
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow.surface_ast import TrialSurfaceStep
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow.trial import evaluation as trial_evaluation
from orchestrator.workflow.trial.config import build_trial_runtime_request
from orchestrator.workflow.trial.contracts import (
    TrialCellKey,
    build_sealed_opaque_label_map,
    derive_trial_cell_effect_scopes,
)
from orchestrator.workflow.trial.runtime import (
    TrialRuntimeDependencies,
    execute_trial_cells,
)
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle
from orchestrator.workflow_lisp.compiler import LoweringRoute


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = (
    REPOSITORY_ROOT / "workflows" / "experiments" / "qa_placement_effectiveness"
)
LIBRARY_ROOT = REPOSITORY_ROOT / "workflows" / "library"
ARMS_SOURCE = WORKFLOW_ROOT / "qa_placement_arms.orc"
TRIAL_SOURCE = WORKFLOW_ROOT / "qa_placement_trial.orc"
PROVIDERS = WORKFLOW_ROOT / "providers.json"
PROMPTS = WORKFLOW_ROOT / "prompts.json"

ARM_ENTRYPOINTS = {
    "DIRECT": "direct",
    "DESIGN_QA": "design-qa",
    "PRODUCT_QA": "product-qa",
    "RICH": "rich",
}

DESIGN_PATH = "artifacts/work/qa-placement/design.md"
DESIGN_REVIEW_PATH = "artifacts/review/qa-placement/design-review.md"
PRODUCT_REVIEW_PATH = "artifacts/review/qa-placement/product-review.md"

ROLE_BY_STEP_FRAGMENT = {
    "direct-task": "I",
    "produce-design": "D",
    "review-design": "DR",
    "revise-design": "DREV",
    "implement-with-design": "I",
    "review-product": "PR",
    "fix-product": "FIX",
}


def _load_decision_lock() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/experiments/es/decision_lock.py"
    spec = importlib.util.spec_from_file_location("es_task4_decision_lock", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision_lock = _load_decision_lock()


def _build_arm(entry_workflow: str):
    return build_frontend_bundle(
        FrontendBuildRequest(
            source_path=ARMS_SOURCE,
            source_roots=(WORKFLOW_ROOT.parent, LIBRARY_ROOT),
            entry_workflow=entry_workflow,
            provider_externs_path=PROVIDERS,
            prompt_externs_path=PROMPTS,
            workspace_root=REPOSITORY_ROOT,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )


def _build_trial():
    return build_frontend_bundle(
        FrontendBuildRequest(
            source_path=TRIAL_SOURCE,
            source_roots=(WORKFLOW_ROOT.parent, LIBRARY_ROOT),
            entry_workflow="compare",
            provider_externs_path=PROVIDERS,
            prompt_externs_path=PROMPTS,
            workspace_root=REPOSITORY_ROOT,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )


@pytest.mark.parametrize("arm_id,entry_workflow", ARM_ENTRYPOINTS.items())
def test_exact_four_arm_entries_compile_to_common_bool_result(
    arm_id: str,
    entry_workflow: str,
) -> None:
    assert ARMS_SOURCE.is_file(), f"missing Task-4 arm module for {arm_id}"
    assert PROVIDERS.is_file()
    assert PROMPTS.is_file()

    built = _build_arm(entry_workflow)

    surface_name = built.validated_bundle.surface.name
    assert isinstance(surface_name, str)
    assert surface_name.endswith(f"::{entry_workflow}")
    result_contract = built.validated_bundle.surface.outputs["__result__"]
    assert result_contract.kind == "scalar"
    assert dict(result_contract.definition)["type"] == "bool"


def test_four_cell_trial_compiles_through_the_public_target_225_entry() -> None:
    assert TRIAL_SOURCE.is_file()

    built = _build_trial()

    surface_name = built.validated_bundle.surface.name
    assert isinstance(surface_name, str)
    assert surface_name.endswith("::compare")
    trial_steps = [
        step
        for step in built.validated_bundle.surface.steps
        if isinstance(step, TrialSurfaceStep)
    ]
    assert len(trial_steps) == 1
    trial = trial_steps[0]
    trial_config = trial.trial
    assert trial_config is not None
    assert tuple(arm.arm_id for arm in trial_config.arms) == tuple(ARM_ENTRYPOINTS)
    assert all(
        arm.run_ref.source.commit == "93e0eb08e092fed177316517328b7effc2893399"
        for arm in trial_config.arms
    )


def test_public_trial_scorer_prepares_the_locked_unrestricted_profile(
    tmp_path: Path,
) -> None:
    built = _build_trial()
    [trial_node] = [
        node
        for node in built.validated_bundle.ir.nodes.values()
        if isinstance(node.execution_config, TrialStepConfig)
    ]
    step_config = trial_node.execution_config
    assert isinstance(step_config, TrialStepConfig)
    common_inputs: dict[str, object] = {
        "task": "Implement the frozen F1 extension-boundary task.",
        "check_contract": "Run the frozen visible F1 check manifest.",
        "model": "gpt-5.5",
        "effort": "high",
    }
    request = build_trial_runtime_request(
        step_config=step_config,
        visit=RunRefVisitKey(
            parent_run_id="task4-scorer-parent",
            execution_frame_id="root",
            call_frame_id=None,
            step_id=trial_node.step_id,
            visit_count=1,
        ),
        resolved_inputs_by_arm={
            arm.arm_id: common_inputs for arm in step_config.trial.arms
        },
    )
    scorer_config = trial_evaluation.build_trial_scorer_config(request)
    registry = ProviderRegistry()
    scorer, instruction, rubric = trial_evaluation._resolve_scorer(
        scorer_config=scorer_config,
        provider_registry=registry,
        prompt_composer=PromptComposer(
            workspace=tmp_path,
            asset_resolver=WorkflowAssetResolver(TRIAL_SOURCE),
        ),
    )

    assert scorer["evaluator_provider"] == "codex_gpt55_unrestricted_workspace"
    invocation, error = ProviderExecutor(
        tmp_path,
        registry,
        provider_observation_enabled=False,
    ).prepare_invocation(
        str(scorer["evaluator_provider"]),
        ProviderParams(
            params=dict(cast(Mapping[str, Any], scorer["evaluator_params"]))
        ),
        {},
        prompt_content=f"{instruction}\n\nRubric:\n{rubric}",
    )

    assert error is None
    assert invocation is not None
    policy = invocation.prepared_provider_policy
    assert policy is not None
    assert policy.model == "gpt-5.5"
    assert policy.effort == "high"
    assert "--dangerously-bypass-approvals-and-sandbox" in invocation.command
    assert "--skip-git-repo-check" in invocation.command


@dataclass(frozen=True)
class ScriptedReply:
    role: str
    output: object
    artifact_path: str | None = None
    malformed: bool = False
    provider_failure: bool = False


@dataclass(frozen=True)
class ProviderCall:
    role: str
    provider_name: str
    step_name: str


@dataclass(frozen=True)
class ScriptedRun:
    state: dict[str, object]
    calls: tuple[ProviderCall, ...]


@dataclass(frozen=True)
class RouteScenario:
    arm: str
    entry_workflow: str
    route_id: str
    roles: tuple[str, ...]
    completed: bool
    terminal_cause: str
    replies: tuple[ScriptedReply, ...]
    pre_execute_failure: bool = False


def _reply(
    role: str,
    *,
    decision: str | None = None,
    malformed: bool = False,
) -> ScriptedReply:
    artifact_path = {
        "D": DESIGN_PATH,
        "DR": DESIGN_REVIEW_PATH,
        "DREV": DESIGN_PATH,
        "PR": PRODUCT_REVIEW_PATH,
    }.get(role)
    output: object = (
        {"decision": decision or "APPROVE"}
        if role in {"DR", "PR"}
        else True
    )
    return ScriptedReply(
        role=role,
        output=output,
        artifact_path=artifact_path,
        malformed=malformed,
    )


def _replies_for_completed_route(roles: tuple[str, ...]) -> tuple[ScriptedReply, ...]:
    return tuple(
        _reply(
            role,
            decision=(
                "REVISE"
                if role == "DR" and "DREV" in roles
                else "REVISE"
                if role == "PR" and "FIX" in roles
                else "APPROVE"
            ),
        )
        for role in roles
    )


def _route_scenarios() -> tuple[RouteScenario, ...]:
    scenarios: list[RouteScenario] = []
    for row in decision_lock.derive_terminal_routes():
        arm = cast(str, row["arm"])
        route_id = cast(str, row["route_id"])
        roles = tuple(cast(list[str], row["role_sequence"]))
        completed = cast(bool, row["completed"])
        if not roles:
            scenarios.append(
                RouteScenario(
                    arm=arm,
                    entry_workflow=ARM_ENTRYPOINTS[arm],
                    route_id=route_id,
                    roles=roles,
                    completed=False,
                    terminal_cause="PRE_EXECUTION_FAILURE",
                    replies=(),
                    pre_execute_failure=True,
                )
            )
            continue
        if completed:
            scenarios.append(
                RouteScenario(
                    arm=arm,
                    entry_workflow=ARM_ENTRYPOINTS[arm],
                    route_id=route_id,
                    roles=roles,
                    completed=True,
                    terminal_cause="COMPLETED_TRUE",
                    replies=_replies_for_completed_route(roles),
                )
            )
            continue
        if route_id.endswith(".FAILED_AT_FINAL_CALL"):
            replies = list(_replies_for_completed_route(roles))
            last_reply = replies[-1]
            replies[-1] = ScriptedReply(
                role=last_reply.role,
                output=last_reply.output,
                artifact_path=last_reply.artifact_path,
                provider_failure=True,
            )
            scenarios.append(
                RouteScenario(
                    arm=arm,
                    entry_workflow=ARM_ENTRYPOINTS[arm],
                    route_id=route_id,
                    roles=roles,
                    completed=False,
                    terminal_cause="FAILED_AT_FINAL_CALL",
                    replies=tuple(replies),
                )
            )
            continue
        if roles == ("D", "DR"):
            scenarios.append(
                RouteScenario(
                    arm=arm,
                    entry_workflow=ARM_ENTRYPOINTS[arm],
                    route_id=route_id,
                    roles=roles,
                    completed=False,
                    terminal_cause="COMPLETED_FALSE_BLOCKED",
                    replies=(
                        _reply("D"),
                        _reply("DR", decision="BLOCKED"),
                    ),
                )
            )
            continue
        replies = list(_replies_for_completed_route(roles))
        last_reply = replies[-1]
        replies[-1] = ScriptedReply(
            role=last_reply.role,
            output=False,
            artifact_path=last_reply.artifact_path,
        )
        scenarios.append(
            RouteScenario(
                arm=arm,
                entry_workflow=ARM_ENTRYPOINTS[arm],
                route_id=route_id,
                roles=roles,
                completed=False,
                terminal_cause="COMPLETED_FALSE_ACTION",
                replies=tuple(replies),
            )
        )
    return tuple(scenarios)


ROUTE_SCENARIOS = _route_scenarios()


def _runtime_role(step_name: str) -> str:
    matches = {
        role
        for fragment, role in ROLE_BY_STEP_FRAGMENT.items()
        if fragment in step_name
    }
    assert len(matches) == 1, f"provider step has ambiguous role: {step_name}"
    return matches.pop()


def _thaw(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    if is_dataclass(value):
        return {str(key): _thaw(item) for key, item in vars(value).items()}
    return value


def _scripted_runtime(
    workspace: Path,
    *,
    entry_workflow: str,
    replies: tuple[ScriptedReply, ...],
    pre_execute_failure: bool = False,
    run_id: str | None = None,
) -> ScriptedRun:
    built = _build_arm(entry_workflow)
    bundle = built.validated_bundle
    contracts: dict[str, dict[str, Any]] = {
        name: dict(contract)
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        contracts,
        {
            "task": "Implement the frozen F1 extension-boundary task.",
            "check_contract": "Run the frozen visible F1 check manifest.",
            "model": "gpt-5.5",
            "effort": "high",
        },
        workspace,
    )
    manager = StateManager(
        workspace=workspace,
        run_id=run_id or f"task4-{entry_workflow}",
    )
    manager.initialize(
        ARMS_SOURCE.as_posix(),
        context=_thaw(workflow_context(bundle)),
        bound_inputs=bound_inputs,
    )
    pending = list(replies)
    calls: list[ProviderCall] = []
    active_step_names: list[str] = []
    prepared_invocations: dict[int, tuple[str, str]] = {}

    original_execute_provider = WorkflowExecutor._execute_provider
    original_prepare_invocation = ProviderExecutor.prepare_invocation

    def _execute_provider_with_trace(_self, step, state):
        step_name = str(step.get("name", ""))
        active_step_names.append(step_name)
        try:
            return original_execute_provider(_self, step, state)
        finally:
            assert active_step_names.pop() == step_name

    def _prepare_invocation(_self, *args, **kwargs):
        if pre_execute_failure:
            return None, {
                "type": "scripted_pre_execution_failure",
                "message": "scripted failure before provider execution",
                "context": {},
            }
        assert len(active_step_names) == 1
        invocation, error = original_prepare_invocation(
            _self,
            *args,
            **kwargs,
        )
        if invocation is not None:
            prepared_invocations[id(invocation)] = (
                str(kwargs.get("provider_name", "")),
                active_step_names[-1],
            )
        return invocation, error

    def _execute(_self, invocation, **_kwargs):
        if not pending:
            pytest.fail("treatment exceeded its scripted provider-call bound")
        reply = pending.pop(0)
        provider_name, step_name = prepared_invocations.pop(id(invocation))
        call = ProviderCall(
            role=_runtime_role(step_name),
            provider_name=provider_name,
            step_name=step_name,
        )
        calls.append(call)
        assert call.role == reply.role
        if reply.provider_failure:
            return ProviderExecutionResult(
                exit_code=1,
                stdout=b"",
                stderr=b"scripted final provider-call failure",
                duration_ms=1,
            )
        artifact_path = reply.artifact_path
        if artifact_path is not None:
            artifact = workspace / artifact_path
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(f"provider-call-{len(calls)}\n", encoding="utf-8")
        output_path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not output_path.is_absolute():
            output_path = workspace / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"malformed": True} if reply.malformed else reply.output
        output_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"scripted provider output is not a data channel",
            stderr=b"",
            duration_ms=1,
        )

    with patch.object(
        WorkflowExecutor,
        "_execute_provider",
        _execute_provider_with_trace,
    ), patch.object(
        ProviderExecutor,
        "prepare_invocation",
        _prepare_invocation,
    ), patch.object(ProviderExecutor, "execute", _execute):
        state = WorkflowExecutor(
            bundle,
            workspace,
            manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert not pending, "treatment skipped a required scripted provider call"
    return ScriptedRun(state=state, calls=tuple(calls))


@pytest.mark.parametrize(
    "scenario",
    ROUTE_SCENARIOS,
    ids=lambda scenario: scenario.route_id,
)
def test_all_locked_terminal_routes_have_concrete_runtime_outcomes(
    tmp_path: Path,
    scenario: RouteScenario,
) -> None:
    result = _scripted_runtime(
        tmp_path,
        entry_workflow=scenario.entry_workflow,
        replies=scenario.replies,
        pre_execute_failure=scenario.pre_execute_failure,
    )

    assert tuple(call.role for call in result.calls) == scenario.roles
    assert all(
        call.provider_name == "codex_gpt55_unrestricted_workspace"
        for call in result.calls
    )
    if scenario.terminal_cause == "COMPLETED_TRUE":
        assert result.state["status"] == "completed"
        assert result.state["workflow_outputs"] == {"__result__": True}
    elif scenario.terminal_cause in {
        "COMPLETED_FALSE_ACTION",
        "COMPLETED_FALSE_BLOCKED",
    }:
        assert result.state["status"] == "completed"
        assert result.state["workflow_outputs"] == {"__result__": False}
    else:
        assert scenario.terminal_cause in {
            "FAILED_AT_FINAL_CALL",
            "PRE_EXECUTION_FAILURE",
        }
        assert result.state["status"] == "failed"
        outputs = result.state.get("workflow_outputs")
        assert not isinstance(outputs, Mapping) or "__result__" not in outputs


@pytest.mark.parametrize(
    ("scenario_id", "entry_workflow", "replies", "expected_roles"),
    (
        (
            "PRODUCT_QA.I_PR.BLOCKED",
            "product-qa",
            (_reply("I"), _reply("PR", decision="BLOCKED")),
            ("I", "PR"),
        ),
        (
            "RICH.D_DR_I_PR.BLOCKED",
            "rich",
            (
                _reply("D"),
                _reply("DR", decision="APPROVE"),
                _reply("I"),
                _reply("PR", decision="BLOCKED"),
            ),
            ("D", "DR", "I", "PR"),
        ),
        (
            "RICH.D_DR_DREV_I_PR.BLOCKED",
            "rich",
            (
                _reply("D"),
                _reply("DR", decision="REVISE"),
                _reply("DREV"),
                _reply("I"),
                _reply("PR", decision="BLOCKED"),
            ),
            ("D", "DR", "DREV", "I", "PR"),
        ),
    ),
)
def test_blocked_outcomes_are_not_inferred_from_colliding_completed_sequences(
    tmp_path: Path,
    scenario_id: str,
    entry_workflow: str,
    replies: tuple[ScriptedReply, ...],
    expected_roles: tuple[str, ...],
) -> None:
    result = _scripted_runtime(
        tmp_path,
        entry_workflow=entry_workflow,
        replies=replies,
    )

    assert scenario_id
    assert tuple(call.role for call in result.calls) == expected_roles
    assert result.state["status"] == "completed"
    assert result.state["workflow_outputs"] == {"__result__": False}


def test_malformed_typed_review_fails_after_the_review_invocation(
    tmp_path: Path,
) -> None:
    result = _scripted_runtime(
        tmp_path,
        entry_workflow="design-qa",
        replies=(
            _reply("D"),
            _reply("DR", malformed=True),
        ),
    )

    assert tuple(call.role for call in result.calls) == ("D", "DR")
    assert result.state["status"] == "failed"
    outputs = result.state.get("workflow_outputs")
    assert not isinstance(outputs, Mapping) or "__result__" not in outputs


def _materialize_trial_source(
    request: SourceRequest,
    *,
    run_ref_root: Path,
    workspace: Path,
    progress_hook=None,
) -> MaterializedSource:
    workspace.mkdir(parents=True)
    (workspace / ".git").mkdir()
    (workspace / "seed.txt").write_text("frozen task seed\n", encoding="utf-8")
    source_manifest = freeze_tree(workspace, excluded_roots=(".git",))
    if progress_hook is not None:
        progress_hook("materialized")
    source_record = canonical_source_request(request)

    def _required_string(record: Mapping[str, object], name: str) -> str:
        value = record[name]
        assert isinstance(value, str)
        return value

    revision = RepositoryRevisionId.build(
        normalized_locator=_required_string(source_record, "normalized_locator"),
        resolved_commit_sha=_required_string(source_record, "resolved_commit_sha"),
        materializer_version=_required_string(source_record, "materializer_version"),
        submodule_policy=_required_string(source_record, "submodule_policy"),
        lfs_policy=_required_string(source_record, "lfs_policy"),
        authored_setup_identity=_required_string(
            source_record, "authored_setup_identity"
        ),
    )
    setup = {
        "schema_version": "run_ref_setup_evidence.v1",
        "repository_revision_digest": revision.digest,
        "authored_setup_identity": revision.authored_setup_identity,
        "status": "passed",
        "commands": [],
    }
    setup_path = workspace.parent / f"{workspace.name}-setup.json"
    setup_path.write_bytes(canonical_json_bytes(setup) + b"\n")
    post_setup = freeze_tree(workspace, excluded_roots=(".git", ".orchestrate"))
    if progress_hook is not None:
        progress_hook("setup_completed")
    return MaterializedSource(
        repository_revision_id=revision,
        normalized_locator=revision.normalized_locator,
        resolved_commit_sha=revision.resolved_commit_sha,
        verified_git_tree=VerifiedGitTreeIdentity("git-tree:" + "b" * 40),
        mirror_path=run_ref_root / "mirrors" / workspace.name,
        mirror_seal_path=run_ref_root / "mirrors" / workspace.name / "seal.json",
        workspace_path=workspace,
        source_tree_manifest=source_manifest,
        setup_evidence_path=setup_path,
        setup_evidence_digest=canonical_sha256(setup),
        post_setup_tree_manifest=post_setup,
        post_setup_baseline_identity=PostSetupBaselineIdentity(post_setup.digest),
    )


def _scripted_trial_child_process(
    launch: RunRefChildLaunch,
    *,
    scripted_run: ScriptedRun,
) -> RunRefChildProcessResult:
    child_state_path = (
        launch.workspace
        / ".orchestrate"
        / "runs"
        / launch.child_run_id
        / "state.json"
    )
    assert child_state_path.is_file()
    if scripted_run.state["status"] != "completed":
        diagnostic = {
            "schema_version": "run_ref_child_diagnostic.v1",
            "status": "rejected",
            "code": "run_ref_child_launch_failed",
            "reason": "workflow_execution_failed",
        }
        return RunRefChildProcessResult(
            returncode=1,
            stdout=b"",
            stderr=canonical_json_bytes(diagnostic) + b"\n",
            duration_ms=1,
        )

    workflow_outputs = cast(
        dict[str, object],
        scripted_run.state["workflow_outputs"],
    )
    result = {
        "schema_version": "run_ref_child_result.v1",
        "status": "completed",
        "capsule_digest": launch.request_document["expected_capsule_digest"],
        "target_workflow_name": launch.request_document["target_workflow_name"],
        "child_run_id": launch.child_run_id,
        "workflow_outputs": workflow_outputs,
    }
    return RunRefChildProcessResult(
        returncode=0,
        stdout=canonical_json_bytes(result) + b"\n",
        stderr=b"",
        duration_ms=1,
    )


def test_public_four_cell_trial_preserves_siblings_when_one_arm_fails(
    tmp_path: Path,
) -> None:
    built = _build_trial()
    bundle = built.validated_bundle
    [trial_node] = [
        node
        for node in bundle.ir.nodes.values()
        if isinstance(node.execution_config, TrialStepConfig)
    ]
    step_config = trial_node.execution_config
    assert isinstance(step_config, TrialStepConfig)
    common_inputs: dict[str, object] = {
        "task": "Implement the frozen F1 extension-boundary task.",
        "check_contract": "Run the frozen visible F1 check manifest.",
        "model": "gpt-5.5",
        "effort": "high",
    }
    request = build_trial_runtime_request(
        step_config=step_config,
        visit=RunRefVisitKey(
            parent_run_id="task4-parent",
            execution_frame_id="root",
            call_frame_id=None,
            step_id=trial_node.step_id,
            visit_count=1,
        ),
        resolved_inputs_by_arm={
            arm.arm_id: common_inputs for arm in step_config.trial.arms
        },
    )
    parent_workspace = (tmp_path / "parent-workspace").resolve()
    parent_workspace.mkdir()
    parent_run_root = (tmp_path / "parent-run-root").resolve()
    parent_run_root.mkdir()
    run_ref_root = (tmp_path / "run-ref-root").resolve()
    capsule_dir = (tmp_path / "capsule").resolve()
    assert built.run_ref_bundle_capsule is not None
    write_bundle_capsule_directory(capsule_dir, built.run_ref_bundle_capsule)
    scopes = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
    )
    assert all(isinstance(cell, TrialCellKey) for cell in request.cell_domain)
    cell_domain = cast(tuple[TrialCellKey, ...], request.cell_domain)
    sealed_labels = build_sealed_opaque_label_map(
        cell_domain,
        salt=b"qa-placement-task4-sibling-proof" * 2,
    )
    launches: list[TrialCellKey] = []
    child_runs: dict[str, ScriptedRun] = {}
    child_execution_lock = Lock()
    replies_by_arm = {
        "DIRECT": (_reply("I"),),
        "DESIGN_QA": (
            _reply("D"),
            _reply("DR", malformed=True),
        ),
        "PRODUCT_QA": (
            _reply("I"),
            _reply("PR", decision="APPROVE"),
        ),
        "RICH": (
            _reply("D"),
            _reply("DR", decision="APPROVE"),
            _reply("I"),
            _reply("PR", decision="APPROVE"),
        ),
    }

    def _dependencies_for(
        cell: TrialCellKey,
        _request: object,
    ) -> RunRefRuntimeDependencies:
        def _launch(launch: RunRefChildLaunch) -> RunRefChildProcessResult:
            launches.append(cell)
            with child_execution_lock:
                scripted_run = _scripted_runtime(
                    launch.workspace,
                    entry_workflow=ARM_ENTRYPOINTS[cell.arm_id],
                    replies=replies_by_arm[cell.arm_id],
                    run_id=launch.child_run_id,
                )
                child_runs[cell.arm_id] = scripted_run
            return _scripted_trial_child_process(
                launch,
                scripted_run=scripted_run,
            )

        return RunRefRuntimeDependencies(
            materialize_source=_materialize_trial_source,
            launch_child=_launch,
        )

    result = execute_trial_cells(
        request,
        parent_state={"bound_inputs": common_inputs, "steps": {}},
        parent_workspace=parent_workspace,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
        capsule_dir=capsule_dir,
        sealed_opaque_labels=sealed_labels,
        dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=_dependencies_for,
        ),
    )

    assert Counter(launches) == Counter(cell_domain)
    assert tuple(outcome.cell.arm_id for outcome in result.outcomes) == tuple(
        ARM_ENTRYPOINTS
    )
    assert [outcome.status for outcome in result.outcomes] == [
        "completed",
        "failed",
        "completed",
        "completed",
    ]
    failure = result.outcomes[1].failure
    assert failure is not None
    assert failure.code == "run_ref_child_launch_failed"
    assert set(child_runs) == set(ARM_ENTRYPOINTS)
    assert child_runs["DESIGN_QA"].state["status"] == "failed"
    assert tuple(
        call.role for call in child_runs["DESIGN_QA"].calls
    ) == ("D", "DR")
    assert all(
        child_runs[arm].state["workflow_outputs"] == {"__result__": True}
        for arm in ("DIRECT", "PRODUCT_QA", "RICH")
    )
    sibling_envelopes = [result.outcomes[index].envelope for index in (0, 2, 3)]
    assert all(envelope is not None for envelope in sibling_envelopes)
    assert [
        cast(Mapping[str, object], envelope)["value"]
        for envelope in sibling_envelopes
    ] == [
        True,
        True,
        True,
    ]
    assert len(scopes) == 4
