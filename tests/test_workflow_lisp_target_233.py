"""Current typed target registration and unsupported-header refusal."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow.run_ref import config as run_ref_config
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


def _compile_minimal_module(tmp_path: Path, target_dsl_version: str):
    path = tmp_path / f"target_{target_dsl_version.replace('.', '_')}.orc"
    path.write_text(
        f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target_dsl_version}")
  (defrecord Out
    (label String))
  (defworkflow tiny
    ()
    -> Out
    (record Out :label "ok")))
""",
        encoding="utf-8",
    )
    return compile_stage3_module(
        path,
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,

    )




@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(syntax.SUPPORTED_TARGET_DSL_VERSIONS, id="frontend"),
        pytest.param(run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, id="run-ref-config"),
    ],
)
def test_current_target_235_is_registered(registry) -> None:
    assert "2.35" in registry




def test_module_targeting_235_compiles_with_no_new_forms(tmp_path: Path) -> None:
    result = _compile_minimal_module(tmp_path, "2.35")

    assert result.typed_program.target == "2.35"


def test_module_targeting_future_241_is_rejected_as_unsupported(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_minimal_module(tmp_path, "2.41")

    assert excinfo.value.diagnostics[0].code == "target_dsl_unsupported"
