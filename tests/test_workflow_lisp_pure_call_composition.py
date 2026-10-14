"""Legacy-characterization and target-2.30 regression coverage for EC-1."""

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


PREPARATION = Path(__file__).parent / "fixtures" / "workflow_lisp" / "pure_call_composition_preparation"


def _fixture_at_current_target(fixture_name: str, *, workspace: Path) -> Path:
    source = (PREPARATION / f"{fixture_name}.orc").read_text(encoding="utf-8")
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / f"{fixture_name}_target_229.orc"
    path.write_text(source.replace('(:target-dsl "2.27")', '(:target-dsl "2.29")'), encoding="utf-8")
    return path


def _fixture_at_target_230(fixture_name: str, *, workspace: Path) -> Path:
    source = (PREPARATION / f"{fixture_name}.orc").read_text(encoding="utf-8")
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / f"{fixture_name}_target_230.orc"
    path.write_text(
        source.replace('(:target-dsl "2.27")', '(:target-dsl "2.30")'),
        encoding="utf-8",
    )
    return path


def _compile(path: Path, *, workspace: Path):
    return compile_stage3_module(
        path,
        lowering_route="wcc_m4",
        validate_shared=True,
        workspace_root=workspace,
    )




@pytest.mark.parametrize(
    ("fixture_name", "diagnostic_code"),
    (
        ("early_defun_rejection", "pure_function_has_effect"),
        ("uncalled_generic_function_specialization", "pure_function_has_effect"),
        ("aggregate_map_rejection", "effect_not_permitted"),
        ("once_only_hygienic_arguments", "effect_not_permitted"),
        ("map_short_circuit_and_proc_rejection", "list_map_body_effect_forbidden"),
        ("map_short_circuit_or_proc_rejection", "list_map_body_effect_forbidden"),
    ),
)
def test_task5_current_target_red_probes_name_the_pre_normalization_blocker(
    tmp_path: Path,
    fixture_name: str,
    diagnostic_code: str,
) -> None:
    """These rejections are Task-5 evidence, not expected Task-6 behavior."""

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            _fixture_at_current_target(fixture_name, workspace=tmp_path),
            workspace=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == diagnostic_code








def test_task5_imported_nested_call_is_currently_rejected_before_normalization(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "pure_helpers.orc"
    entry = tmp_path / "entry.orc"
    helper.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.29")',
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
                '  (:target-dsl "2.29")',
                "  (defmodule entry)",
                "  (import pure_helpers :only (increment))",
                "  (export orchestrate)",
                "  (defun twice ((value Int)) -> Int (increment (increment value)))",
                "  (defworkflow orchestrate ((value Int)) -> Int (twice value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            entry,
            source_roots=(tmp_path,),
            lowering_route="wcc_m4",
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"






















def test_target_230_retains_selected_pure_callee_provenance(tmp_path: Path) -> None:
    compiled = _compile(
        _fixture_at_target_230("early_defun_rejection", workspace=tmp_path),
        workspace=tmp_path,
    )

    frames = [
        frame
        for workflow in compiled.typed_workflows
        for node in walk_expr(workflow.typed_body.expr)
        for frame in node.expansion_stack
        if isinstance(frame, ProcedureExpansionFrame)
    ]

    assert any(frame.procedure_name == "increment" for frame in frames)




def test_target_230_materializes_uncalled_function_procedure_specializations(
    tmp_path: Path,
) -> None:
    result = _compile(
        _fixture_at_target_230(
            "uncalled_generic_function_specialization", workspace=tmp_path
        ),
        workspace=tmp_path,
    )

    assert any(
        procedure.definition.name.startswith("%parametric-call.identity.")
        for procedure in result.typed_procedures
    )


def test_target_230_expands_selected_pure_hook_in_its_specialized_environment(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_pure_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
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
        if procedure.definition.name == "apply-hook"
    )
    assert isinstance(generic_base.typed_body.expr, ProcedureCallExpr)
    assert generic_base.typed_body.expr.callee_name == "hook"

    state = StateManager(workspace=tmp_path, run_id="selected-pure-hook")







def test_target_230_expands_selected_bind_proc_hook_with_runtime_residual(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_bound_pure_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
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
        if getattr(procedure.specialization, "base_name", None) == "apply-hook"
        and "hook" in procedure.specialization.proc_ref_bindings
    )
    selected_bound_hook = next(
        procedure
        for procedure in compiled.typed_procedures
        if getattr(procedure.specialization, "base_name", None) == "add-leading"
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





def test_target_230_rechecks_uncalled_effectful_functions(tmp_path: Path) -> None:
    source = tmp_path / "uncalled_effectful.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
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
            lowering_route="wcc_m4",
            validate_shared=True,
            workspace_root=tmp_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompt.md"},
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_target_230_rechecks_uncalled_effectful_functions_in_linked_modules(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "helper.orc"
    entry = tmp_path / "entry.orc"
    helper.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
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
                '  (:target-dsl "2.30")',
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
            lowering_route="wcc_m4",
            validate_shared=True,
            workspace_root=tmp_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompt.md"},
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_target_230_rechecks_uncalled_private_functions(tmp_path: Path) -> None:
    source = tmp_path / "uncalled_private.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
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






def test_target_230_reports_unrepresentable_selected_body_without_clone_crash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unrepresentable_selected_body.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
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


def test_target_230_rejects_effectful_selected_hook_in_pure_function(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_effectful_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
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
            lowering_route="wcc_m4",
            validate_shared=True,
            workspace_root=tmp_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompt.md"},
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_target_230_rejects_private_procedure_in_pure_function(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private_pure_call.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
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
