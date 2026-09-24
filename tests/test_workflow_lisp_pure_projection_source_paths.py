"""Computed call bindings retain field paths independently of output labels."""

from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.lowering.pure_projection import _runtime_binding_value


@pytest.mark.parametrize("target", ["2.28", "2.29"])
@pytest.mark.parametrize("bind_first", [False, True])
def test_computed_record_call_binding_uses_exact_source_paths(
    tmp_path: Path, target: str, bind_first: bool
) -> None:
    update = "(record-update (record Box :value 0) :value (+ n 1))"
    body = (
        f"(let* ((updated {update})) (call echo :box updated))"
        if bind_first
        else f"(call echo :box {update})"
    )
    source = tmp_path / "computed_record_binding.orc"
    source.write_text(
        f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defrecord Box (value Int))
  (defworkflow echo ((box Box)) -> Box box)
  (defworkflow run ((n Int)) -> Box
    {body}))
""",
        encoding="utf-8",
    )
    compiled = compile_stage3_module(
        source, lowering_route="wcc_m4", validate_shared=True, workspace_root=tmp_path
    )
    bundle = compiled.validated_bundles["run"]
    state = StateManager(workspace=tmp_path, run_id="computed-binding")
    state.initialize(str(source), bound_inputs={"n": 8})

    result = WorkflowExecutor(bundle, tmp_path, state, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert result["status"] == "completed", result.get("error")
    assert result["workflow_outputs"] == {"return__value": 9}


def test_runtime_binding_preserves_user_double_underscore_fields() -> None:
    assert _runtime_binding_value(
        {
            "__kept": 8,
            "nested": {"__also_kept__": 9},
            "__lowering_returned_union_type": "Outcome",
            "__typed_union_prompt_source__": {"compiler": "only"},
            "__provider_bundle_path_ref__": "root.steps.provider.artifacts.bundle",
            "__provider_bundle_projection__": {"compiler": "only"},
        }
    ) == {"__kept": 8, "nested": {"__also_kept__": 9}}


def test_record_binding_with_user_double_underscore_field_executes(tmp_path: Path) -> None:
    source = tmp_path / "record_field.orc"
    source.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.30")
  (defrecord Box (__kept Int) (value Int))
  (defworkflow run ((n Int)) -> Int
    (let* ((box (record Box :__kept n :value 0)))
      (+ box.__kept 1))))
''',
        encoding="utf-8",
    )
    compiled = compile_stage3_module(
        source, lowering_route="wcc_m4", validate_shared=True, workspace_root=tmp_path
    )
    state = StateManager(workspace=tmp_path, run_id="record-field")
    state.initialize(str(source), bound_inputs={"n": 8})
    result = WorkflowExecutor(
        compiled.validated_bundles["run"], tmp_path, state, retry_delay_ms=0
    ).execute(on_error="stop")

    assert result["status"] == "completed", result.get("error")
    assert result["workflow_outputs"] == {"__result__": 9}
