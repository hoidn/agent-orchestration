import ast
import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import NameExpr, ProduceOneOfExpr, ProviderResultExpr
from orchestrator.workflow_lisp.phase_stdlib import (
    ProduceOneOfCandidateFieldSpec,
    ProduceOneOfCandidateSpec,
    ProduceOneOfProducerSpec,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.workflow_lisp.wcc.route import LoweringRoute


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
INVALID_FIXTURES = FIXTURES / "invalid"
MODULE_FIXTURES = FIXTURES / "modules" / "valid" / "workflow_refs"


def _command_boundaries() -> dict[str, CertifiedAdapterBinding]:
    return {
        "select_next_item": CertifiedAdapterBinding(
            name="select_next_item",
            stable_command=("python", "scripts/select_next_item.py"),
            input_contract={"type": "object"},
            output_type_name="SelectionResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("select_next_item_ok",),
            negative_fixture_ids=("select_next_item_bad",),
        ),
        "execute_selected_item": CertifiedAdapterBinding(
            name="execute_selected_item",
            stable_command=("python", "scripts/execute_selected_item.py"),
            input_contract={"type": "object"},
            output_type_name="SelectedItemResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("execute_selected_item_ok",),
            negative_fixture_ids=("execute_selected_item_bad",),
        ),
        "draft_gap_item": CertifiedAdapterBinding(
            name="draft_gap_item",
            stable_command=("python", "scripts/draft_gap_item.py"),
            input_contract={"type": "object"},
            output_type_name="GapDraftResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("draft_gap_item_ok",),
            negative_fixture_ids=("draft_gap_item_bad",),
        ),
    }


def _workflow_ref_command_boundaries() -> dict[str, ExternalToolBinding]:
    return {
        "run_checks": ExternalToolBinding(
            name="run_checks",
            stable_command=("python", "scripts/run_checks.py"),
        )
    }


def _typecheck_top_level_names() -> set[str]:
    source_path = Path(importlib.import_module("orchestrator.workflow_lisp.typecheck").__file__)
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in module.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    }


def _test_span(path: str) -> SourceSpan:
    start = SourcePosition(path=path, line=1, column=1, offset=0)
    end = SourcePosition(path=path, line=1, column=2, offset=1)
    return SourceSpan(start=start, end=end)


def _function_body_mentions_symbol(path: Path, function_name: str, symbol: str) -> bool:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == symbol:
                return True
            if isinstance(child, ast.Attribute) and child.attr == symbol:
                return True
            if isinstance(child, ast.ImportFrom):
                if any(alias.name == symbol or alias.asname == symbol for alias in child.names):
                    return True
    return False


def _name(name: str) -> NameExpr:
    return NameExpr(name=name, span=_test_span(name), form_path=("workflow-lisp", "workflow-ref-test"))


def test_workflow_ref_owner_split_moves_non_procedure_call_typing_out_of_typecheck_facade() -> None:
    package_dir = Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent
    dispatch_source = (package_dir / "typecheck_dispatch.py").read_text(encoding="utf-8")

    assert (package_dir / "typecheck_calls.py").is_file()
    top_level_names = _typecheck_top_level_names()
    assert "_typecheck_workflow_ref_argument" not in top_level_names
    assert "_validate_selector_workflow_ref" not in top_level_names
    assert "_validate_run_item_workflow_ref" not in top_level_names
    assert "_validate_gap_drafter_workflow_ref" not in top_level_names
    assert "if isinstance(expr, CallExpr):" not in dispatch_source
    assert "if isinstance(expr, FunctionCallExpr):" not in dispatch_source
    assert "typecheck_call_expr(" in dispatch_source
    assert "typecheck_function_call_expr(" in dispatch_source


def test_workflow_ref_extern_owner_uses_shared_iter_child_exprs() -> None:
    source_path = Path(importlib.import_module("orchestrator.workflow_lisp.workflow_refs").__file__)

    assert _function_body_mentions_symbol(source_path, "collect_workflow_extern_names", "iter_child_exprs")


def test_workflow_ref_extern_collection_descends_into_produce_one_of_candidate_targets() -> None:
    from orchestrator.workflow_lisp.workflow_refs import collect_workflow_extern_names

    expr = ProduceOneOfExpr(
        returns_type_name="SelectionResult",
        ctx_expr=_name("ctx"),
        producer=ProduceOneOfProducerSpec(
            kind="provider",
            provider_expr=None,
            prompt_expr=None,
            inputs=(),
        ),
        candidates=(
            ProduceOneOfCandidateSpec(
                variant_name="APPROVED",
                fields=(
                    ProduceOneOfCandidateFieldSpec(
                        field_name="result",
                        target_expr=ProviderResultExpr(
                            provider=_name("providers.execute"),
                            prompt=_name("prompts.implementation.execute"),
                            inputs=(),
                            returns_type_name="ChecksResult",
                            span=_test_span("provider-result"),
                            form_path=("workflow-lisp", "workflow-ref-test"),
                        ),
                    ),
                ),
            ),
        ),
        span=_test_span("produce-one-of"),
        form_path=("workflow-lisp", "workflow-ref-test"),
    )

    providers, prompts = collect_workflow_extern_names(expr)

    assert providers == {"providers.execute"}
    assert prompts == {"prompts.implementation.execute"}


def test_workflow_ref_same_file_higher_order_calls_compile_and_validate(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "workflow_refs_same_file.orc",
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    lowered_input_sets = {workflow.typed_workflow.definition.name: set(workflow.authored_mapping["inputs"]) for workflow in result.lowered_workflows}

    assert "echo-helper" in result.validated_bundles
    assert "entry" in result.validated_bundles
    assert any(name != "call-runner" and name.startswith("call-runner") for name in lowered_input_sets)
    assert all("runner" not in inputs for inputs in lowered_input_sets.values())


def test_workflow_ref_explicit_literal_calls_still_compile_and_validate(tmp_path: Path) -> None:
    path = tmp_path / "workflow_ref_literal.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord WorkflowInput",
                "    (report WorkReport))",
                "  (defrecord WorkflowOutput",
                "    (report WorkReport))",
                "  (defworkflow echo-helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" input.report)',
                "      :returns WorkflowOutput))",
                "  (defworkflow call-runner",
                "    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])",
                "     (input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (call runner",
                "      :input input))",
                "  (defworkflow entry",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (call call-runner",
                "      :runner (workflow-ref echo-helper)",
                "      :input input)))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    assert "echo-helper" in result.validated_bundles
    assert "entry" in result.validated_bundles


def test_workflow_ref_forwarding_through_defproc_compiles_and_validates(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "workflow_refs_forwarding.orc",
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    assert "echo-helper" in result.validated_bundles
    assert "entry" in result.validated_bundles


def test_workflow_ref_specialization_through_owner_seam_compiles_and_validates(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "workflow_refs_forwarding.orc",
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    specialized_names = {
        workflow.typed_workflow.definition.name
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.startswith("%workflow_refs_forwarding.")
    }

    assert specialized_names == {"%workflow_refs_forwarding.invoke-runner__spec__runner__echo_helper.v1"}
    assert specialized_names <= set(result.validated_bundles)


def test_workflow_ref_imported_module_resolution_compiles_and_validates(tmp_path: Path) -> None:
    result = compile_stage3_entrypoint(
        MODULE_FIXTURES / "workflow_refs" / "imported_entry.orc",
        source_roots=(MODULE_FIXTURES,),
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    assert "workflow_refs/imported_entry::entry" in result.validated_bundles_by_name
    assert "workflow_refs/imported_helper::echo-helper" in result.entry_result.workflow_catalog.signatures_by_name


def test_workflow_ref_top_level_param_is_allowed_but_nested_return_transport_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workflow_ref_nested_return_invalid.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord WorkflowInput",
                "    (report String))",
                "  (defrecord WorkflowOutput",
                "    (report String))",
                "  (defrecord WorkflowEnvelope",
                "    (runner WorkflowRef[WorkflowInput -> WorkflowOutput]))",
                "  (defworkflow echo-helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput",
                "      :report input.report))",
                "  (defworkflow entry",
                "    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])",
                "     (input WorkflowInput))",
                "    -> WorkflowEnvelope",
                "    (record WorkflowEnvelope",
                "      :runner runner)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )

    _assert_diagnostic_code(excinfo, "workflow_ref_runtime_transport_forbidden")


@pytest.mark.parametrize(
    ("fixture_name", "expected_code"),
    [
        ("workflow_ref_literal_required.orc", "workflow_ref_literal_required"),
        ("workflow_ref_runtime_transport_invalid.orc", "workflow_ref_runtime_transport_forbidden"),
        ("workflow_ref_signature_invalid.orc", "workflow_ref_signature_invalid"),
        ("workflow_ref_specialization_cycle.orc", "workflow_ref_specialization_cycle"),
        ("workflow_ref_extern_unsatisfied.orc", "workflow_ref_extern_rebinding_unsatisfied"),
        ("workflow_ref_extern_unsatisfied_if.orc", "workflow_ref_extern_rebinding_unsatisfied"),
    ],
)
def test_workflow_ref_invalid_contracts_raise_targeted_diagnostics(
    fixture_name: str,
    expected_code: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            INVALID_FIXTURES / fixture_name,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            command_boundaries=_command_boundaries(),
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )

    _assert_diagnostic_code(excinfo, expected_code)


_ROOT_RESULT_CALLEE_LINES = [
    "  (defworkflow root-flag",
    "    ((count Int))",
    "    -> Bool",
    "    (provider-result providers.execute",
    "      :prompt prompts.implementation.execute",
    "      :inputs (count)",
    "      :returns Bool))",
]


def _root_result_provider_externs() -> dict[str, str]:
    return {"providers.execute": "test-provider"}


def _root_result_prompt_externs() -> dict[str, str]:
    return {"prompts.implementation.execute": "prompts/implementation/execute.md"}


@pytest.mark.parametrize("lowering_route", [LoweringRoute.LEGACY, LoweringRoute.WCC_M4])
def test_same_file_call_of_root_result_workflow_binds_declared_type(
    tmp_path: Path,
    lowering_route: LoweringRoute,
) -> None:
    path = tmp_path / "root_result_same_file_call.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defrecord Wrap",
                "    (ok Bool))",
                *_ROOT_RESULT_CALLEE_LINES,
                "  (defworkflow outer",
                "    ((count Int))",
                "    -> Wrap",
                "    (let* ((ok (call root-flag :count count)))",
                "      (record Wrap :ok ok))))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        provider_externs=_root_result_provider_externs(),
        prompt_externs=_root_result_prompt_externs(),
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
    )

    assert "root-flag" in result.validated_bundles
    assert "outer" in result.validated_bundles
    callee = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "root-flag"
    )
    assert set(callee.authored_mapping["outputs"]) == {"__result__"}
    outer = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "outer"
    )
    call_step = next(
        step for step in outer.authored_mapping["steps"] if step.get("call") == "root-flag"
    )
    output_ref = outer.authored_mapping["outputs"]["return__ok"]["from"]["ref"]
    assert output_ref == f"root.steps.{call_step['name']}.artifacts.__result__"


def test_imported_bundle_call_of_root_result_workflow_binds_declared_type(
    tmp_path: Path,
) -> None:
    callee_path = tmp_path / "root_result_imported_callee.orc"
    callee_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                *_ROOT_RESULT_CALLEE_LINES,
                ")",
            ]
        ),
        encoding="utf-8",
    )
    compiled_callee = compile_stage3_module(
        callee_path,
        provider_externs=_root_result_provider_externs(),
        prompt_externs=_root_result_prompt_externs(),
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )
    callee_bundle = next(
        bundle
        for name, bundle in compiled_callee.validated_bundles.items()
        if name == "root-flag" or name.endswith("::root-flag")
    )

    caller_path = tmp_path / "root_result_imported_caller.orc"
    caller_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Wrap",
                "    (ok Bool))",
                "  (defworkflow outer",
                "    ((count Int))",
                "    -> Wrap",
                "    (let* ((ok (call root-flag :count count)))",
                "      (record Wrap :ok ok))))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        caller_path,
        provider_externs=_root_result_provider_externs(),
        prompt_externs=_root_result_prompt_externs(),
        imported_workflow_bundles={"root-flag": callee_bundle},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    outer = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "outer"
    )
    call_step = next(
        step for step in outer.authored_mapping["steps"] if step.get("call") == "root-flag"
    )
    output_ref = outer.authored_mapping["outputs"]["return__ok"]["from"]["ref"]
    assert output_ref == f"root.steps.{call_step['name']}.artifacts.__result__"
