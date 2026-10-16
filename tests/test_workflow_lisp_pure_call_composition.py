"""Current pure procedure composition and selected-hook regressions."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import ProcedureCallExpr
from orchestrator.workflow_lisp.syntax import ProcedureExpansionFrame


CURRENT = Path(__file__).parent / "fixtures" / "workflow_lisp" / "pure_call_composition_current"


def _compile(path: Path, *, workspace: Path):
    return compile_stage3_module(
        path,

        validate_shared=True,
        workspace_root=workspace,
    )




@pytest.mark.parametrize(
    "fixture_name",
    (
        "early_defun_rejection",
        "uncalled_generic_function_specialization",
        "aggregate_map_rejection",
        "once_only_hygienic_arguments",
        "map_short_circuit_and_proc_rejection",
        "map_short_circuit_or_proc_rejection",
    ),
)
def test_current_pure_composition_normalizes_calls(tmp_path: Path, fixture_name: str) -> None:
    compiled = _compile(CURRENT / f"{fixture_name}.orc", workspace=tmp_path)
    assert compiled.typed_workflows
    assert not any(
        isinstance(node, ProcedureCallExpr)
        for workflow in compiled.typed_workflows
        for node in walk_expr(workflow.typed_body.expr)
    )








def test_current_imported_nested_call_normalizes(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "pure_helpers.orc"
    entry = tmp_path / "entry.orc"
    helper.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule pure_helpers)",
                "  (export increment)",
                "  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 1)))",
            )
        ),
        encoding="utf-8",
    )
    entry.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule entry)",
                "  (import pure_helpers :only (increment))",
                "  (export orchestrate)",
                "  (defun twice ((value Int)) -> Int (increment (increment value)))",
                "  (defworkflow orchestrate ((value Int)) -> Int (twice value)))",
            )
        ),
        encoding="utf-8",
    )

    compiled = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),

        validate_shared=True,
        workspace_root=tmp_path,
    )
    assert not any(
        isinstance(node, ProcedureCallExpr)
        for workflow in compiled.entry_result.typed_workflows
        for node in walk_expr(workflow.typed_body.expr)
    )






















def test_current_target_retains_selected_pure_callee_provenance(tmp_path: Path) -> None:
    compiled = _compile(
        CURRENT / "early_defun_rejection.orc",
        workspace=tmp_path,
    )

    frames = [
        frame
        for workflow in compiled.typed_workflows
        for node in walk_expr(workflow.typed_body.expr)
        for frame in node.expansion_stack
        if isinstance(frame, ProcedureExpansionFrame)
    ]

    assert any(frame.procedure_name == 'early_defun_rejection::increment' for frame in frames)




def test_current_target_materializes_uncalled_function_procedure_specializations(
    tmp_path: Path,
) -> None:
    result = _compile(
        CURRENT / "uncalled_generic_function_specialization.orc",
        workspace=tmp_path,
    )

    assert any(
        procedure.definition.name.startswith('%parametric-call.uncalled_generic_function_specialization.identity.')
        for procedure in result.typed_procedures
    )


def test_current_target_expands_selected_pure_hook_in_its_specialized_environment(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_pure_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 1))",
                "  (defproc apply-hook",
                "    :forall (T)",
                "    ((hook ProcRef[T -> T]) (value T)) -> T",
                "    :effects () :lowering inline",
                "    (hook value))",
                "  (defun wrapped ((value Int)) -> Int",
                "    (apply-hook (proc-ref increment) value))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    compiled = _compile(source, workspace=tmp_path)
    generic_base = next(
        procedure
        for procedure in compiled.typed_procedures
        if procedure.definition.name == 'entry::apply-hook'
    )
    assert isinstance(generic_base.typed_body.expr, ProcedureCallExpr)
    assert generic_base.typed_body.expr.callee_name == "hook"

    state = StateManager(workspace=tmp_path, run_id="selected-pure-hook")







def test_current_target_expands_selected_bind_proc_hook_with_runtime_residual(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_bound_pure_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defproc add-leading ((leading Int) (value Int)) -> Int",
                "    :effects () :lowering inline (+ leading value))",
                "  (defproc apply-hook",
                "    ((hook ProcRef[Int -> Int]) (value Int)) -> Int",
                "    :effects () :lowering inline (hook value))",
                "  (defun wrapped ((value Int)) -> Int",
                "    (let* ((hook (bind-proc (proc-ref add-leading) :leading 2)))",
                "      (apply-hook hook value)))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    compiled = _compile(source, workspace=tmp_path)
    selected_apply_hook = next(
        procedure
        for procedure in compiled.typed_procedures
        if getattr(procedure.specialization, "base_name", None) == 'entry::apply-hook'
        and "hook" in procedure.specialization.proc_ref_bindings
    )
    selected_bound_hook = next(
        procedure
        for procedure in compiled.typed_procedures
        if getattr(procedure.specialization, "base_name", None) == 'entry::add-leading'
        and "leading" in procedure.specialization.value_bindings
    )
    assert (
        selected_apply_hook.specialization.proc_ref_bindings["hook"].call_target_name
        == selected_bound_hook.definition.name
    )
    assert selected_bound_hook.specialization.value_bindings["leading"].value == 2
    # Formal aliases are direct references to the materialized actual, not
    # additional projection bundles.  The selected hook still remains visible
    # on the projection origins that do materialize its bound leading value.

    state = StateManager(workspace=tmp_path, run_id="selected-bound-pure-hook")





def test_current_target_rechecks_uncalled_effectful_functions(tmp_path: Path) -> None:
    source = tmp_path / "uncalled_effectful.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defproc provider-backed ((value Int)) -> Int",
                "    :effects ((uses-provider providers.execute))",
                "    :lowering inline",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute :inputs (value) :returns Int))",
                "  (defun uncalled ((value Int)) -> Int (provider-backed value))",
                "  (defworkflow orchestrate ((value Int)) -> Int value))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            source,

            validate_shared=True,
            workspace_root=tmp_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompt.md"},
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_current_target_rechecks_uncalled_effectful_functions_in_linked_modules(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "helper.orc"
    entry = tmp_path / "entry.orc"
    helper.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule helper)",
                "  (export identity)",
                "  (defproc provider-backed ((value Int)) -> Int",
                "    :effects ((uses-provider providers.execute)) :lowering inline",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute :inputs (value) :returns Int))",
                "  (defun uncalled ((value Int)) -> Int (provider-backed value))",
                "  (defun identity ((value Int)) -> Int value))",
            )
        ),
        encoding="utf-8",
    )
    entry.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule entry)",
                "  (import helper :only (identity))",
                "  (export orchestrate)",
                "  (defworkflow orchestrate ((value Int)) -> Int (identity value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            entry,
            source_roots=(tmp_path,),

            validate_shared=True,
            workspace_root=tmp_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompt.md"},
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_current_target_rechecks_uncalled_private_functions(tmp_path: Path) -> None:
    source = tmp_path / "uncalled_private.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord Box (value Int))",
                "  (defproc private ((value Int)) -> Box",
                "    :effects () :lowering private-workflow (record Box :value value))",
                "  (defun uncalled ((value Int)) -> Box (private value))",
                "  (defworkflow orchestrate ((value Int)) -> Int value))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(source, workspace=tmp_path)

    assert excinfo.value.diagnostics[0].code == "pure_call_representation_unsupported"






def test_current_target_reports_unrepresentable_selected_body_without_clone_crash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unrepresentable_selected_body.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord Box (value Int))",
                "  (defworkflow child ((value Int)) -> Box (record Box :value value))",
                "  (defproc helper ((value Int)) -> Int",
                "    :effects () :lowering inline",
                "    (let* ((child-ref (workflow-ref child))) value))",
                "  (defun wrapped ((value Int)) -> Int (helper value))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(source, workspace=tmp_path)

    assert excinfo.value.diagnostics[0].code == "pure_call_representation_unsupported"


def test_current_target_rejects_effectful_selected_hook_in_pure_function(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_effectful_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defproc effectful ((value Int)) -> Int",
                "    :effects ((uses-provider providers.execute)) :lowering inline",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute :inputs (value) :returns Int))",
                "  (defproc apply-hook",
                "    ((hook ProcRef[Int -> Int]) (value Int)) -> Int",
                "    :effects () :lowering inline (hook value))",
                "  (defun wrapped ((value Int)) -> Int",
                "    (apply-hook (proc-ref effectful) value))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            source,

            validate_shared=True,
            workspace_root=tmp_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompt.md"},
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_current_target_rejects_private_procedure_in_pure_function(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private_pure_call.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defrecord Box (value Int))",
                "  (defproc private ((value Int)) -> Box",
                "    :effects () :lowering private-workflow (record Box :value value))",
                "  (defun wrapped ((value Int)) -> Box (private value))",
                "  (defworkflow orchestrate ((value Int)) -> Box (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(source, workspace=tmp_path)

    assert excinfo.value.diagnostics[0].code == "pure_call_representation_unsupported"
