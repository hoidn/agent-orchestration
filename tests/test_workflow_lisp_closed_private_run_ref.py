from __future__ import annotations

import base64

import pytest

from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from orchestrator.workflow.evaluated.machine import site_nodes
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.procedures import ProcedureLoweringMode
from tests.test_workflow_evaluated_run_ref import _public_fixture


def _private_source(root, *, imported=False, generic=False, mode="private-workflow", target="2.35", twice=False):
    params = '(extra T) (flag Bool)' if generic else '(flag Bool)'
    name = 'invoke :forall (T)' if generic else 'invoke'
    call_args = '"capture" true' if generic else 'true'
    def definitions(call):
        return f'''(defproc {name} ({params}) -> Bool
          :effects ((runs-ref run)) :lowering {mode}
          (let* ((child {call})) child.value))'''
    invoke = f'(invoke {call_args})'
    body = f'(let* ((first {invoke})) {invoke})' if twice else invoke
    parent, source, _refs = _public_fixture(root, definitions=definitions,
        parent_target=target, inputs="(flag-name Bool)", call_inputs=":flag-name flag",
        child_body="flag-name", body=lambda _call: body,
        imports='(import helper :only (invoke))' if imported else '')
    if imported:
        text = source.read_text()
        start = text.index('(defproc ')
        end = text.index('(defworkflow run ', start)
        helper = parent / 'helper.orc'
        helper.write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule helper) (export invoke) {text[start:end]})''')
        source.write_text(text[:start] + text[end:])
    return parent, source


@pytest.mark.parametrize("imported", [False, True])
@pytest.mark.parametrize("generic", [False, True])
def test_closed_explicit_private_run_ref_retains_mode_and_owner(tmp_path, imported, generic):
    parent, source = _private_source(tmp_path, imported=imported, generic=generic)
    typed = compile_typed_program(source, entry_workflow="run", source_roots=(parent,), workspace_root=parent, command_boundaries={})
    _assert_private_mode_and_owner(typed, imported, generic)
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=source, source_roots=(parent,), workspace_root=parent))
    restored = ClosedProgram.from_artifact(built.artifact_path.read_text())
    assert (restored.digest, restored.tree, restored.sites) == (
        built.program.digest, built.program.tree, built.program.sites)
    [(identity, node)] = site_nodes(restored).items()
    [call] = [node for node in _ast_nodes(restored.tree["body"]) if node.get("k") == "call"]
    assert call["frame"] in identity
    module = "helper" if imported else "controller"
    assert restored.tree["definitions"][call["callee"]]["key"][:2] == [module, "procedure"]
    config = decode_run_ref_static_config(base64.b64decode(node["config"]))
    assert config.inputs[0].binding.record == {"kind": "reference", "reference": "inputs.flag-name"}
    assert config.program.return_refinement == {"kind": "primitive", "name": "Bool"}


def _assert_private_mode_and_owner(typed, imported, generic):
    selected = [procedure for procedure in typed.procedures.values()
                if not procedure.signature.type_params]
    assert selected
    assert all(procedure.resolved_lowering_mode is ProcedureLoweringMode.PRIVATE_WORKFLOW
               for procedure in selected)
    if generic:
        assert any(procedure.specialization is not None for procedure in selected)
    expected_target = "2.34" if imported else "2.35"
    assert all(typed.procedure_type_env(procedure).target_dsl_version == expected_target
               for procedure in selected)


def test_closed_auto_run_ref_keeps_existing_inline_selection(tmp_path):
    parent, source = _private_source(tmp_path, mode="auto", twice=True)
    typed = compile_typed_program(source, entry_workflow="run", source_roots=(parent,), workspace_root=parent, command_boundaries={})
    assert all(procedure.resolved_lowering_mode is ProcedureLoweringMode.INLINE
               for procedure in typed.procedures.values())


def test_legacy_explicit_private_run_ref_keeps_boundary_diagnostic(tmp_path):
    parent, source = _private_source(tmp_path, target="2.34")
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    with pytest.raises(LispFrontendCompileError) as caught:
        compile_stage3_entrypoint(source, source_roots=(parent,), workspace_root=parent)
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "proc_private_workflow_boundary_invalid"
    assert diagnostic.span.start.path == str(source)
