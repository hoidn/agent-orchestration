from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.report import report_workflow
from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.lexical_checkpoints import (
    resolve_checkpoint_index_path,
)
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "transportable_value_provider_resume.orc"
)
MIXED_VALUE = {
    "approved": True,
    "owner": None,
    "score": 0.91,
    "attempt_ids": [1, 2],
    "metrics": {"correctness": 0.95, "clarity": 0.87},
}
DIFFERENT_SHAPE_VALUE = [
    "approved",
    {"nested": [False, None, 3]},
]


class _PostPersistInterruption(BaseException):
    pass


def _copy_runtime_fixture(workspace: Path) -> Path:
    module_path = workspace / FIXTURE.name
    module_path.write_bytes(FIXTURE.read_bytes())
    prompt_path = workspace / "prompts" / "value.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("Return the requested JSON value.\n", encoding="utf-8")
    script_path = workspace / "scripts" / "finish.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text(
        "import os\n"
        "from pathlib import Path\n"
        'path = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        'path.write_text("true\\n", encoding="utf-8")\n',
        encoding="utf-8",
    )
    return module_path


def _compile_bundle(workspace: Path, *, lowering_route: str):
    module_path = _copy_runtime_fixture(workspace)
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        provider_externs={"providers.value": "deterministic-value-provider"},
        prompt_externs={
            "prompts.value": {"input_file": "prompts/value.md"},
        },
        command_boundaries={
            "finish-run": ExternalToolBinding(
                name="finish-run",
                stable_command=("python", "scripts/finish.py"),
            ),
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
    return module_path, bundle


def _thaw(value):
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _compiled_contract_identity(bundle) -> dict[str, object]:
    provider_node = next(
        node
        for node in bundle.ir.nodes.values()
        if node.execution_config is not None
        and node.kind.value == "provider"
    )
    output_bundle = provider_node.execution_config.common.output_bundle
    assert output_bundle is not None
    semantic_workflow = bundle.semantic_ir.workflows[bundle.surface.name]
    public_contract_id = semantic_workflow.output_contract_ids["__result__"]
    public_contract = bundle.semantic_ir.contracts[public_contract_id]
    return {
        "provider_fields": [
            {
                key: field[key]
                for key in ("name", "json_pointer", "type")
            }
            for field in output_bundle["fields"]
        ],
        "public_surface": {
            key: bundle.surface.outputs["__result__"].definition[key]
            for key in ("kind", "type")
        },
        "public_semantic_contract": {
            "contract_id": public_contract_id,
            "contract_kind": public_contract.contract_kind,
            "value_type": public_contract.value_type,
            "definition": _thaw(public_contract.definition),
        },
    }


def _persisted_checkpoint_record(
    executor: WorkflowExecutor,
    finalized: Mapping[str, object],
) -> dict[str, object]:
    step_id = finalized["step_id"]
    point = next(
        (
            candidate
            for candidate in executor.runtime_plan.lexical_checkpoint_points
            if candidate.step_id == step_id
        ),
        None,
    )
    if point is None:
        return {}
    index_path = resolve_checkpoint_index_path(
        state_manager=executor.state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = executor.workspace / index["records"][-1]["record_path"]
    return json.loads(record_path.read_text(encoding="utf-8"))


def _execute_clean(
    workspace: Path,
    *,
    module_path: Path,
    bundle,
    run_id: str,
    provider_value: object,
) -> tuple[dict[str, object], int]:
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={},
    )
    invocation_count = 0

    def prepare_invocation(_self, *args, **kwargs):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=kwargs.get("prompt_content", ""),
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def execute_provider(_self, invocation, **_kwargs):
        nonlocal invocation_count
        invocation_count += 1
        bundle_path = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(provider_value, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"provider stdout is observability only",
            stderr=b"",
            duration_ms=1,
        )

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare_invocation,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_provider,
    ):
        result = WorkflowExecutor(
            bundle,
            workspace,
            state_manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(on_error="stop")
    return result, invocation_count


def test_transportable_value_classic_and_wcc_execute_equal_direct_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_results: dict[str, dict[str, object]] = {}
    for lowering_route in ("legacy", "wcc_m4"):
        workspace = tmp_path / lowering_route
        workspace.mkdir()
        module_path, bundle = _compile_bundle(
            workspace,
            lowering_route=lowering_route,
        )
        source = module_path.read_text(encoding="utf-8")
        assert "__result__" not in source
        assert "(match " not in source
        assert "(record " not in source
        assert "(variant " not in source

        contract_identity = _compiled_contract_identity(bundle)
        assert contract_identity["provider_fields"] == [
            {
                "name": "__result__",
                "json_pointer": "",
                "type": "value",
            }
        ]
        assert contract_identity["public_surface"] == {
            "kind": "value",
            "type": "value",
        }

        monkeypatch.chdir(workspace)
        first, first_invocations = _execute_clean(
            workspace,
            module_path=module_path,
            bundle=bundle,
            run_id=f"value-clean-{lowering_route}",
            provider_value=MIXED_VALUE,
        )
        assert first["status"] == "completed"
        assert first_invocations == 1
        assert first["workflow_outputs"] == {
            "__result__": MIXED_VALUE,
        }
        provider_step = next(
            step
            for step in first["steps"].values()
            if step.get("artifacts", {}).get("__result__") == MIXED_VALUE
        )
        assert provider_step["artifacts"] == {
            "__result__": MIXED_VALUE,
        }
        assert any(
            name.endswith("finish-run") and step["status"] == "completed"
            for name, step in first["steps"].items()
        )

        second, second_invocations = _execute_clean(
            workspace,
            module_path=module_path,
            bundle=bundle,
            run_id=f"value-second-shape-{lowering_route}",
            provider_value=DIFFERENT_SHAPE_VALUE,
        )
        assert second["status"] == "completed"
        assert second_invocations == 1
        assert second["workflow_outputs"] == {
            "__result__": DIFFERENT_SHAPE_VALUE,
        }
        assert _compiled_contract_identity(bundle) == contract_identity
        route_results[lowering_route] = {
            "contract_identity": contract_identity,
            "mixed_output": first["workflow_outputs"],
            "different_shape_output": second["workflow_outputs"],
        }

    assert route_results["legacy"] == route_results["wcc_m4"]


# Classic lowering has no lexical checkpoint points; WCC is the production
# checkpoint-bearing route, while clean execution parity above covers both.
def test_transportable_value_wcc_resumes_from_committed_provider_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lowering_route = "wcc_m4"
    workspace = tmp_path / lowering_route
    workspace.mkdir()
    module_path, bundle = _compile_bundle(
        workspace,
        lowering_route=lowering_route,
    )
    run_id = f"value-resume-{lowering_route}"
    state_manager = StateManager(
        workspace=workspace,
        run_id=run_id,
    )
    state_manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs={},
    )
    invocations: list[object] = []
    interrupted_records: list[dict[str, object]] = []

    def prepare_invocation(_self, *args, **kwargs):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=kwargs.get("prompt_content", ""),
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def execute_provider(_self, invocation, **_kwargs):
        invocations.append(invocation)
        bundle_path = workspace / invocation.env[
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH"
        ]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(MIXED_VALUE, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"provider stdout is observability only",
            stderr=b"",
            duration_ms=1,
        )

    original_post_persist = (
        WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit
    )

    def interrupt_after_provider_checkpoint(
        self,
        state,
        step_name,
        step,
        finalized,
    ):
        original_post_persist(self, state, step_name, step, finalized)
        record = _persisted_checkpoint_record(self, finalized)
        completed_effect_refs = record.get("completed_effect_refs", [])
        if (
            not completed_effect_refs
            or completed_effect_refs[0].get("effect_kind") != "provider"
        ):
            return
        interrupted_records.append(record)
        raise _PostPersistInterruption

    monkeypatch.chdir(workspace)
    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare_invocation,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_provider,
    ), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_provider_checkpoint,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                workspace,
                state_manager,
                max_retries=0,
                retry_delay_ms=0,
            ).execute(on_error="stop")

    assert len(invocations) == 1
    assert len(interrupted_records) == 1
    interrupted = state_manager.load().to_dict()
    provider_step = next(
        step
        for step in interrupted["steps"].values()
        if step.get("artifacts", {}).get("__result__") == MIXED_VALUE
    )
    assert provider_step["status"] == "completed"
    assert provider_step["artifacts"] == {"__result__": MIXED_VALUE}
    command_point = next(
        point
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.details.get("effect_boundary", {}).get("effect_kind")
        == "command"
    )
    assert not any(
        step.get("step_id") == command_point.step_id
        for step in interrupted["steps"].values()
    )

    resume_manager = StateManager(
        workspace=workspace,
        run_id=run_id,
    )
    resume_manager.load()
    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        prepare_invocation,
    ), patch.object(
        ProviderExecutor,
        "execute",
        execute_provider,
    ):
        resumed = WorkflowExecutor(
            bundle,
            workspace,
            resume_manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(resume=True)

    assert len(invocations) == 1
    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": MIXED_VALUE}
    resumed_provider_step = next(
        step
        for step in resumed["steps"].values()
        if step.get("artifacts", {}).get("__result__") == MIXED_VALUE
    )
    assert resumed_provider_step["artifacts"] == {
        "__result__": MIXED_VALUE,
    }
    resumed_command_step = next(
        step
        for step in resumed["steps"].values()
        if step.get("step_id") == command_point.step_id
    )
    assert resumed_command_step["status"] == "completed"
    command_record = _persisted_checkpoint_record(
        WorkflowExecutor(
            bundle,
            workspace,
            resume_manager,
            max_retries=0,
            retry_delay_ms=0,
        ),
        {"step_id": command_point.step_id},
    )
    value_bindings = [
        binding
        for binding in command_record["restore_payload"]["bindings"]
        if binding.get("type_ref") == "Value"
    ]
    assert len(value_bindings) == 1
    assert value_bindings[0]["value"] == MIXED_VALUE
    default_resume_report = json.loads(
        resume_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )
    assert default_resume_report["selection_reason"] == (
        "validated_prior_boundary"
    )
    assert default_resume_report["restore_decision"] == "RESTORED"
    report_exit = report_workflow(
        run_id=run_id,
        runs_root=str(workspace / ".orchestrate" / "runs"),
        format="json",
    )
    assert report_exit == 0
    report_payload = json.loads(capsys.readouterr().out)
    assert report_payload["run"]["workflow_outputs"] == {
        "__result__": MIXED_VALUE,
    }
