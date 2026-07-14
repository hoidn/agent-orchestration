"""Declarative end-to-end acceptance for native transportable returns.

Compiles real public-v2.15 `.orc` provider and command results that each
write direct JSON `true`/`false`, branches on the resulting `Bool`, persists
state, resumes, and asserts no wrapper object, no stdout extraction, no
authored `__result__` access, and no name-specific lowering.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.contracts import derive_reusable_state_contract_metadata
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, UnionTypeRef
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid"
PROVIDER_FIXTURE = FIXTURES / "native_bool_provider_branch.orc"
COMMAND_FIXTURE = FIXTURES / "native_bool_command_branch.orc"


def _copy_fixture(workspace: Path, fixture: Path) -> Path:
    local = workspace / fixture.name
    local.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    return local


def _bool_bundle_command(workspace: Path, name: str, value: str) -> ExternalToolBinding:
    scripts = workspace / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / f"{name}.py").write_text(
        "import os, pathlib\n"
        'bundle = pathlib.Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        f'bundle.write_text("{value}\\n", encoding="utf-8")\n'
        'print("stdout must stay a sidecar")\n',
        encoding="utf-8",
    )
    return ExternalToolBinding(name=name, stable_command=("python", f"scripts/{name}.py"))


def _provider_executor_patches(workspace: Path, document: str):
    def _prepare_invocation(_self, *args, **kwargs):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=kwargs.get("prompt_content", ""),
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def _execute(_self, invocation, **_kwargs):
        bundle_path = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(document + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"stdout must stay a sidecar",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    return (
        patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation),
        patch.object(ProviderExecutor, "execute", _execute),
    )


def _bind_and_execute(bundle, workspace: Path, run_id: str, module_path: Path, inputs: dict):
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(binding_inputs, inputs, workspace)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return state_manager


def _guided_runtime_source(*, guided: bool) -> str:
    score_field = (
        '(score Float :description "Confidence score." :format-hint "0 to 1." :example 0.9)'
        if guided
        else "(score Float)"
    )
    approve_field = (
        '(approved Bool :description "Approval branch flag." :example true)'
        if guided
        else "(approved Bool)"
    )
    revise_field = (
        '(approved Bool :description "Revision branch flag." :example false)'
        if guided
        else "(approved Bool)"
    )
    meta_field = (
        '(meta ReviewMeta :description "Approval metrics context.")'
        if guided
        else "(meta ReviewMeta)"
    )
    reason_field = (
        '(reason String :description "Required revision." :example "fix tests")'
        if guided
        else "(reason String)"
    )
    workflow_return = (
        '(result FinalResult :description "Completed routed review result.")'
        if guided
        else "FinalResult"
    )
    provider_return = (
        '(result Decision :description "Choose the review route." '
        ':format-hint "Tagged decision object.")'
        if guided
        else "Decision"
    )
    return (
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule guidance_runtime_neutrality)",
                "  (export orchestrate)",
                "  (defpath SummaryPath",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ReviewMeta",
                f"    {score_field})",
                "  (defunion Decision",
                "    (APPROVE",
                f"      {approve_field}",
                f"      {meta_field})",
                "    (REVISE",
                f"      {revise_field}",
                f"      {reason_field}))",
                "  (defrecord SummaryValue (approved Bool))",
                "  (defrecord FinalResult",
                "    (approved Bool)",
                "    (summary_path SummaryPath))",
                "  (defworkflow orchestrate",
                "    ((summary_target SummaryPath))",
                f"    -> {workflow_return}",
                "    (let* ((decision",
                "             (provider-result providers.review",
                "               :prompt prompts.review",
                "               :inputs ()",
                f"               :returns {provider_return}))",
                "           (approved",
                "             (match decision",
                "               ((APPROVE approved-decision)",
                "                 (command-result record_approved",
                '                   :argv ("python" "scripts/record_approved.py")',
                "                   :returns Bool))",
                "               ((REVISE revise-decision)",
                "                 (command-result record_revise",
                '                   :argv ("python" "scripts/record_revise.py")',
                "                   :returns Bool))))",
                "           (summary_path",
                "             (materialize-view runtime-summary",
                "               :value (record SummaryValue :approved approved)",
                "               :renderer canonical-json",
                "               :renderer-version 1",
                "               :target summary_target",
                "               :returns SummaryPath)))",
                "      (record FinalResult",
                "        :approved approved",
                "        :summary_path summary_path))))",
            ]
        )
        + "\n"
    )


def _compile_guidance_runtime_bundle(workspace: Path, *, guided: bool, lowering_route: str):
    module_path = workspace / "guidance_runtime_neutrality.orc"
    module_path.write_text(_guided_runtime_source(guided=guided), encoding="utf-8")
    (workspace / "prompts").mkdir(exist_ok=True)
    (workspace / "prompts" / "review.md").write_text("Review.\n", encoding="utf-8")
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        provider_externs={"providers.review": "fake-review-provider"},
        prompt_externs={"prompts.review": {"input_file": "prompts/review.md"}},
        command_boundaries={
            "record_approved": _bool_bundle_command(workspace, "record_approved", "true"),
            "record_revise": _bool_bundle_command(workspace, "record_revise", "false"),
        },
        validate_shared=True,
        workspace_root=workspace,
        lowering_route=lowering_route,
    )
    bundle = next(
        candidate
        for name, candidate in result.validated_bundles_by_name.items()
        if name.endswith("::orchestrate") or name == "orchestrate"
    )
    compiled_module = result.entry_result.module
    type_env = FrontendTypeEnvironment.from_module(compiled_module)
    decision_type = type_env.resolve_type(
        "Decision",
        span=compiled_module.span,
        form_path=("workflow-lisp", "defunion", "Decision"),
    )
    assert isinstance(decision_type, UnionTypeRef)
    _, reusable_fingerprint, _, _ = derive_reusable_state_contract_metadata(
        decision_type,
        target_dsl_version="2.15",
        workflow_name="guidance_runtime_neutrality::orchestrate",
        step_id="decision",
        span=compiled_module.span,
        form_path=("workflow-lisp", "defworkflow", "orchestrate"),
    )
    return module_path, bundle, reusable_fingerprint


def _runtime_checkpoint_contract_fingerprints(bundle) -> tuple[str, ...]:
    fingerprints: list[str] = []
    for point in bundle.runtime_plan.lexical_checkpoint_points:
        effect_boundary = point.details.get("effect_boundary")
        if not isinstance(effect_boundary, Mapping):
            continue
        policy = effect_boundary.get("policy")
        if not isinstance(policy, Mapping):
            continue
        policy_digest = policy.get("policy_digest")
        if isinstance(policy_digest, str):
            fingerprints.append(policy_digest)
        requirements = policy.get("evidence_requirements")
        if not isinstance(requirements, Mapping):
            continue
        for requirement in requirements.values():
            if not isinstance(requirement, Mapping):
                continue
            fingerprint = requirement.get("contract_digest")
            if isinstance(fingerprint, str):
                fingerprints.append(fingerprint)
    return tuple(fingerprints)


def _execute_guidance_runtime_case(workspace: Path, bundle, module_path: Path, *, run_id: str):
    target = workspace / "artifacts" / "work" / "summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}\n", encoding="utf-8")
    state_manager = _bind_and_execute(
        bundle,
        workspace,
        run_id,
        module_path,
        {"summary_target": "artifacts/work/summary.json"},
    )
    provider_patches = _provider_executor_patches(
        workspace,
        '{"variant":"APPROVE","approved":true,"meta":{"score":0.9}}',
    )
    with provider_patches[0], provider_patches[1]:
        first = WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    resume_manager = StateManager(workspace=workspace, run_id=run_id)
    resume_manager.load()
    provider_patches = _provider_executor_patches(
        workspace,
        '{"variant":"APPROVE","approved":true,"meta":{"score":0.9}}',
    )
    with provider_patches[0], provider_patches[1]:
        resumed = WorkflowExecutor(bundle, workspace, resume_manager, retry_delay_ms=0).execute(
            resume=True
        )
    return first, resumed


def test_compiled_occurrence_guidance_is_runtime_checkpoint_and_resume_neutral(
    tmp_path: Path,
) -> None:
    lowering_route = "wcc_m4"
    plain_workspace = tmp_path / "plain"
    guided_workspace = tmp_path / "guided"
    plain_workspace.mkdir()
    guided_workspace.mkdir()
    plain_path, plain_bundle, plain_reusable_fingerprint = _compile_guidance_runtime_bundle(
        plain_workspace,
        guided=False,
        lowering_route=lowering_route,
    )
    guided_path, guided_bundle, guided_reusable_fingerprint = _compile_guidance_runtime_bundle(
        guided_workspace,
        guided=True,
        lowering_route=lowering_route,
    )

    guided_provider = next(
        node.execution_config.common.variant_output
        for node in guided_bundle.ir.nodes.values()
        if node.execution_config is not None
        and node.execution_config.common.variant_output
    )
    assert guided_provider["guidance"] == {
        "description": "Choose the review route.",
        "format_hint": "Tagged decision object.",
    }
    shared_approved = next(
        field for field in guided_provider["shared_fields"] if field["name"] == "approved"
    )
    assert set(shared_approved["guidance_by_variant"]) == {"APPROVE", "REVISE"}
    score_field = next(
        field
        for field in guided_provider["variants"]["APPROVE"]["fields"]
        if field["name"].endswith("score")
    )
    assert score_field["description"] == "Confidence score."
    assert [dict(row) for row in score_field["guidance_context"]] == [
        {
            "json_pointer": "/meta",
            "description": "Approval metrics context.",
        }
    ]

    assert plain_bundle.projection == guided_bundle.projection
    assert plain_bundle.runtime_plan.resume_checkpoints == guided_bundle.runtime_plan.resume_checkpoints
    assert [point.checkpoint_id for point in plain_bundle.runtime_plan.lexical_checkpoint_points] == [
        point.checkpoint_id for point in guided_bundle.runtime_plan.lexical_checkpoint_points
    ]
    assert _runtime_checkpoint_contract_fingerprints(plain_bundle) == _runtime_checkpoint_contract_fingerprints(
        guided_bundle
    )
    assert _runtime_checkpoint_contract_fingerprints(plain_bundle)
    assert plain_reusable_fingerprint == guided_reusable_fingerprint

    plain_first, plain_resumed = _execute_guidance_runtime_case(
        plain_workspace,
        plain_bundle,
        plain_path,
        run_id="plain-guidance-neutrality",
    )
    guided_first, guided_resumed = _execute_guidance_runtime_case(
        guided_workspace,
        guided_bundle,
        guided_path,
        run_id="guided-guidance-neutrality",
    )

    assert plain_first["status"] == guided_first["status"] == "completed"
    assert plain_resumed["status"] == guided_resumed["status"] == "completed"
    expected_outputs = {
        "return__approved": True,
        "return__summary_path": "artifacts/work/summary.json",
    }
    assert plain_first["workflow_outputs"] == guided_first["workflow_outputs"] == expected_outputs
    assert plain_resumed["workflow_outputs"] == guided_resumed["workflow_outputs"] == expected_outputs

    def runtime_semantic_state(state):
        return {
            "status": state["status"],
            "workflow_outputs": state["workflow_outputs"],
            "steps": {
                name: {
                    key: step.get(key)
                    for key in ("status", "exit_code", "artifacts", "skipped", "outcome", "visit_count")
                }
                for name, step in state["steps"].items()
            },
        }

    assert runtime_semantic_state(plain_first) == runtime_semantic_state(guided_first)
    assert runtime_semantic_state(plain_resumed) == runtime_semantic_state(guided_resumed)
    for state in (plain_resumed, guided_resumed):
        completed_steps = {
            name for name, step in state["steps"].items() if step["status"] == "completed"
        }
        assert any(name.endswith("record_approved") for name in completed_steps)
        assert not any(name.endswith("record_revise") for name in completed_steps)
        provider_step = next(
            step for name, step in state["steps"].items() if name.endswith("__decision")
        )
        assert provider_step["exit_code"] == 0
        assert provider_step["artifacts"] == {
            "variant": "APPROVE",
            "approved": True,
            "meta__score": 0.9,
        }


def test_provider_root_bool_result_drives_branching_persists_and_resumes(
    tmp_path: Path,
) -> None:
    module_path = _copy_fixture(tmp_path, PROVIDER_FIXTURE)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review the change.\n", encoding="utf-8")
    work = tmp_path / "artifacts" / "work"
    work.mkdir(parents=True)
    (work / "summary.json").write_text("{}\n", encoding="utf-8")

    source_text = module_path.read_text(encoding="utf-8")
    assert "__result__" not in source_text

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={"providers.review": "fake-review-provider"},
        prompt_externs={"prompts.review": {"input_file": "prompts/review.md"}},
        command_boundaries={
            "record_approved": _bool_bundle_command(tmp_path, "record_approved", "true"),
            "record_revise": _bool_bundle_command(tmp_path, "record_revise", "true"),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        validated
        for name, validated in result.validated_bundles_by_name.items()
        if name.endswith("::decide") or name == "decide"
    )
    run_id = "native-provider-branch"
    state_manager = _bind_and_execute(
        bundle, tmp_path, run_id, module_path, {"summary_target": "artifacts/work/summary.json"}
    )

    # Fail once at the materialize-view boundary to force an interrupted run,
    # then resume it -- proving state persists and the run is resumable, not
    # just a single-shot execution.
    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic materialize-view failure")
        return real_render_view(*args, **kwargs)

    p1, p2 = _provider_executor_patches(tmp_path, "true")
    with p1, p2, patch(
        "orchestrator.workflow.executor.render_view", side_effect=_fail_render_once
    ):
        first_run = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first_run["status"] == "failed"
    provider_step = first_run["steps"]["native_bool_provider_branch::decide__approved"]
    assert provider_step["artifacts"] == {"__result__": True}
    assert provider_step["output"] != json.dumps(True)

    resume_manager = StateManager(workspace=tmp_path, run_id=run_id)
    resume_manager.load()
    p1, p2 = _provider_executor_patches(tmp_path, "true")
    with p1, p2:
        resumed = WorkflowExecutor(bundle, tmp_path, resume_manager, retry_delay_ms=0).execute(
            resume=True
        )

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": True}
    branch_step = next(
        step
        for name, step in resumed["steps"].items()
        if name.endswith("record_approved")
    )
    assert branch_step["artifacts"] == {"__result__": True}
    # No stdout parsing: the captured raw output text is the sidecar marker,
    # never the parsed boolean value or a wrapper object.
    for step in resumed["steps"].values():
        assert "json" not in step
        assert "lines" not in step
        if "output" in step:
            assert step["output"] != "true\n"


def test_command_root_bool_result_drives_branching_and_resumes_when_completed(
    tmp_path: Path,
) -> None:
    module_path = _copy_fixture(tmp_path, COMMAND_FIXTURE)

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "probe_ready": _bool_bundle_command(tmp_path, "probe_ready", "true"),
            "record_ready": _bool_bundle_command(tmp_path, "record_ready", "true"),
            "record_blocked": _bool_bundle_command(tmp_path, "record_blocked", "true"),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        validated
        for name, validated in result.validated_bundles_by_name.items()
        if name.endswith("::gate") or name == "gate"
    )
    run_id = "native-command-branch"
    state_manager = _bind_and_execute(bundle, tmp_path, run_id, module_path, {})

    first_run = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert first_run["status"] == "completed"
    assert first_run["workflow_outputs"] == {"__result__": True}
    probe_step = first_run["steps"]["native_bool_command_branch::gate__ready__probe_ready"]
    assert probe_step["artifacts"] == {"__result__": True}
    assert probe_step["output"] == "stdout must stay a sidecar\n"
    branch_step = next(
        step for name, step in first_run["steps"].items() if name.endswith("record_ready")
    )
    assert branch_step["artifacts"] == {"__result__": True}
    for step in first_run["steps"].values():
        assert "json" not in step
        assert "lines" not in step

    # Persisting state and resuming: an idempotent resume of an already
    # completed run reconfirms the persisted terminal state without
    # re-executing any step or altering the recorded result.
    resume_manager = StateManager(workspace=tmp_path, run_id=run_id)
    resume_manager.load()
    resumed = WorkflowExecutor(bundle, tmp_path, resume_manager, retry_delay_ms=0).execute(
        resume=True
    )

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": True}


def test_command_root_bool_result_false_branch_records_blocked(tmp_path: Path) -> None:
    module_path = _copy_fixture(tmp_path, COMMAND_FIXTURE)

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "probe_ready": _bool_bundle_command(tmp_path, "probe_ready", "false"),
            "record_ready": _bool_bundle_command(tmp_path, "record_ready", "true"),
            "record_blocked": _bool_bundle_command(tmp_path, "record_blocked", "true"),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        validated
        for name, validated in result.validated_bundles_by_name.items()
        if name.endswith("::gate") or name == "gate"
    )
    state_manager = _bind_and_execute(
        bundle, tmp_path, "native-command-branch-false", module_path, {}
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"__result__": True}
    probe_step = state["steps"]["native_bool_command_branch::gate__ready__probe_ready"]
    assert probe_step["artifacts"] == {"__result__": False}
    branch_step = next(
        step for name, step in state["steps"].items() if name.endswith("record_blocked")
    )
    assert branch_step["artifacts"] == {"__result__": True}


def test_native_root_relpath_workflow_return_executes_without_wrapper(tmp_path: Path) -> None:
    """N3: a root-relpath return (the whole bundle document is a path string)."""
    module_path = tmp_path / "native_relpath_return.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule native_relpath_return)",
                "  (export locate)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defworkflow locate",
                "    ((report_path WorkReport))",
                "    -> WorkReport",
                "    (command-result locate_report",
                '      :argv ("python" "scripts/locate_report.py")',
                "      :returns WorkReport)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    work = tmp_path / "artifacts" / "work"
    work.mkdir(parents=True)
    (work / "report.md").write_text("report\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "locate_report.py").write_text(
        "import os, pathlib\n"
        'bundle = pathlib.Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        'bundle.write_text("\\"artifacts/work/report.md\\"\\n", encoding="utf-8")\n'
        'print("stdout must stay a sidecar")\n',
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "locate_report": ExternalToolBinding(
                name="locate_report",
                stable_command=("python", "scripts/locate_report.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        validated
        for name, validated in result.validated_bundles_by_name.items()
        if name.endswith("::locate") or name == "locate"
    )
    state_manager = _bind_and_execute(
        bundle, tmp_path, "native-relpath-return", module_path, {"report_path": "artifacts/work/report.md"}
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"__result__": "artifacts/work/report.md"}
    step = state["steps"]["native_relpath_return::locate__locate_report"]
    assert step["artifacts"] == {"__result__": "artifacts/work/report.md"}
    assert step["output"] == "stdout must stay a sidecar\n"
