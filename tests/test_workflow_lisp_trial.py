import pytest

from orchestrator.workflow_lisp.type_env import (
    PrimitiveTypeRef,
)


@pytest.mark.parametrize("target_dsl_version", ("2.35", "2.36"))
def test_full_compiler_keeps_non_trial_value_return_signature(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    target_dsl_version: str,
) -> None:
    from orchestrator.workflow_lisp import compiler as workflow_lisp_compiler

    source_path = tmp_path / "value_frontend.orc"
    source_path.write_text(
        f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target_dsl_version}")
  (defmodule value_frontend)
  (export passthrough)
  (defworkflow passthrough ((payload Value)) -> Value
    payload))
""",
        encoding="utf-8",
    )

    result = workflow_lisp_compiler.compile_stage3_module(
        source_path, entry_workflow="passthrough", workspace_root=tmp_path,
    )
    typed_entry = result.typed_program.workflows["value_frontend::passthrough"]
    assert typed_entry.signature.return_type_ref == PrimitiveTypeRef("Value")
    assert result.workflow_catalog.signatures_by_name["passthrough"].return_type_ref == PrimitiveTypeRef("Value")
