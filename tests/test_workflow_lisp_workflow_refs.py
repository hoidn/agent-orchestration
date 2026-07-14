import ast
import importlib
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

import orchestrator.workflow_lisp.compiler as workflow_lisp_compiler
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import NameExpr, ProduceOneOfExpr, ProviderResultExpr
from orchestrator.workflow_lisp.phase_stdlib import (
    ProduceOneOfCandidateFieldSpec,
    ProduceOneOfCandidateSpec,
    ProduceOneOfProducerSpec,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.workflow_lisp.wcc.route import LoweringRoute
from orchestrator.workflow_lisp.wcc.defunctionalize import lower_wcc_m4_workflow_definitions
from orchestrator.workflow_lisp.wcc import defunctionalize as wcc_defunctionalize
from orchestrator.workflow_lisp.workflow_refs import (
    ResolvedWorkflowRef,
    WorkflowExternRebindingPlan,
    WorkflowRefAuthoritySource,
)


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
    assert any(
        procedure.definition.name == "invoke-runner__spec__runner__echo_helper"
        for procedure in result.typed_procedures
    )
    assert specialized_names <= set(result.validated_bundles)


def test_workflow_ref_procedure_specialization_is_materialized_before_lowering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_mappings: list[tuple[tuple[object, ...], object]] = []
    consumer_name = "lower_workflow_definitions"
    original_consumer = getattr(workflow_lisp_compiler, consumer_name)

    def capture_consumer(typed_workflows, **kwargs):
        received_mappings.append(
            (kwargs["typed_procedures"], kwargs["resolved_procedures_by_name"])
        )
        return original_consumer(typed_workflows, **kwargs)

    monkeypatch.setattr(workflow_lisp_compiler, consumer_name, capture_consumer)

    result = compile_stage3_module(
        VALID_FIXTURES / "workflow_refs_forwarding.orc",
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    specialized = next(
        procedure
        for procedure in result.typed_procedures
        if procedure.definition.name == "invoke-runner__spec__runner__echo_helper"
    )
    assert tuple(name for name, _ in specialized.signature.params) == ("input",)
    assert tuple(specialized.specialization.workflow_ref_bindings) == ("runner",)
    assert specialized.resolved_lowering_mode.value == "private-workflow"
    assert specialized.generated_workflow_name == (
        "%workflow_refs_forwarding.invoke-runner__spec__runner__echo_helper.v1"
    )
    assert len(received_mappings) == 1
    typed_rows, resolved_rows = received_mappings[0]
    assert resolved_rows[specialized.definition.name] is specialized
    assert any(row is specialized for row in typed_rows)


def test_classic_procedure_lowering_has_no_specialization_fallback() -> None:
    source_path = Path(
        importlib.import_module("orchestrator.workflow_lisp.lowering.procedures").__file__
    )
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    lowering_function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_lower_procedure_call"
    )

    assert not any(
        isinstance(node, ast.Name) and node.id == "specialize_typed_procedure"
        for node in ast.walk(lowering_function)
    )


def test_classic_procedure_lowering_rejects_a_missing_stage3_workflow_ref_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow_lisp_compiler,
        "_discover_workflow_ref_specializations",
        lambda **kwargs: (),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            VALID_FIXTURES / "workflow_refs_forwarding.orc",
            command_boundaries=_workflow_ref_command_boundaries(),
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.LEGACY,
        )

    assert excinfo.value.diagnostics[0].code == "procedure_lowering_unresolved"


def test_stage3_materializes_combined_workflow_and_proc_ref_specialization(
    tmp_path: Path,
) -> None:
    path = tmp_path / "combined_refs.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport :kind relpath :under \"artifacts/work\" :must-exist true)",
                "  (defrecord WorkflowInput (report WorkReport))",
                "  (defrecord WorkflowOutput (report WorkReport))",
                "  (defworkflow echo-helper",
                "    ((input WorkflowInput)) -> WorkflowOutput",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" input.report)',
                "      :returns WorkflowOutput))",
                "  (defproc identity-helper",
                "    ((input WorkflowInput)) -> WorkflowOutput",
                "    :effects () :lowering inline",
                "    (record WorkflowOutput :report input.report))",
                "  (defproc invoke-runner",
                "    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])",
                "     (hook ProcRef[WorkflowInput -> WorkflowOutput])",
                "     (input WorkflowInput)) -> WorkflowOutput",
                "    :effects ((calls-workflow runner)) :lowering inline",
                "    (call runner :input input))",
                "  (defworkflow entry",
                "    ((input WorkflowInput)) -> WorkflowOutput",
                "    (invoke-runner (workflow-ref echo-helper) (proc-ref identity-helper) input)))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        path,
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    combined = next(
        procedure
        for procedure in result.typed_procedures
        if procedure.specialization is not None
        and procedure.specialization.workflow_ref_bindings
        and procedure.specialization.proc_ref_bindings
    )
    assert tuple(name for name, _ in combined.signature.params) == ("input",)
    assert tuple(combined.specialization.workflow_ref_bindings) == ("runner",)
    assert tuple(combined.specialization.proc_ref_bindings) == ("hook",)


def test_linked_stage3_materializes_imported_workflow_ref_procedure_specialization(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "linked_refs"
    package = source_root / "demo"
    package.mkdir(parents=True)
    (package / "types.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/types)",
                "  (export WorkReport WorkflowInput WorkflowOutput)",
                "  (defpath WorkReport :kind relpath :under \"artifacts/work\" :must-exist true)",
                "  (defrecord WorkflowInput (report WorkReport))",
                "  (defrecord WorkflowOutput (report WorkReport)))",
            ]
        ),
        encoding="utf-8",
    )
    (package / "procedures.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/procedures)",
                "  (import demo/types :only (WorkflowInput WorkflowOutput))",
                "  (export invoke-runner)",
                "  (defproc invoke-runner",
                "    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])",
                "     (input WorkflowInput)) -> WorkflowOutput",
                "    :effects ((calls-workflow runner)) :lowering inline",
                "    (call runner :input input)))",
            ]
        ),
        encoding="utf-8",
    )
    entry_path = package / "entry.orc"
    entry_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/types :only (WorkflowInput WorkflowOutput))",
                "  (import demo/procedures :only (invoke-runner))",
                "  (export entry)",
                "  (defworkflow echo-helper",
                "    ((input WorkflowInput)) -> WorkflowOutput",
                "    (record WorkflowOutput :report input.report))",
                "  (defworkflow entry",
                "    ((input WorkflowInput)) -> WorkflowOutput",
                "    (invoke-runner (workflow-ref echo-helper) input)))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(source_root,),
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )

    specialized = next(
        procedure
        for procedure in result.entry_result.typed_procedures
        if procedure.specialization is not None
        and procedure.specialization.workflow_ref_bindings
    )
    assert specialized.specialization.base_name == "demo/procedures::invoke-runner"
    assert tuple(name for name, _ in specialized.signature.params) == ("input",)
    assert specialized.resolved_lowering_mode.value == "inline"


def test_wcc_procedure_lowering_has_no_specialization_fallback() -> None:
    source_path = Path(
        importlib.import_module("orchestrator.workflow_lisp.wcc.defunctionalize").__file__
    )
    module = ast.parse(source_path.read_text(encoding="utf-8"))

    assert not any(
        isinstance(node, ast.Name) and node.id == "specialize_typed_procedure"
        for node in ast.walk(module)
    )


@pytest.mark.parametrize("lowering_route", (LoweringRoute.LEGACY, LoweringRoute.WCC_M4))
def test_workflow_ref_specialization_preserves_return_guidance(
    tmp_path: Path,
    lowering_route: LoweringRoute,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / f"guided_workflow_ref_{lowering_route.value}.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
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
                '    -> (result WorkflowOutput :description "Forwarded workflow output.")',
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
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=LoweringRoute.LEGACY,
    )
    lowered_workflows = result.lowered_workflows
    captured_specializations = []
    if lowering_route is LoweringRoute.WCC_M4:
        type_env = FrontendTypeEnvironment.from_module(result.module)
        echo_helper = next(
            workflow for workflow in result.typed_workflows if workflow.definition.name == "echo-helper"
        )
        resolved_runner = ResolvedWorkflowRef(
            workflow_name="echo-helper",
            signature_params=echo_helper.signature.params,
            return_type_ref=echo_helper.signature.return_type_ref,
            authority_source=WorkflowRefAuthoritySource(kind="local", workflow_name="echo-helper"),
            extern_rebinding_plan=WorkflowExternRebindingPlan(provider_bindings={}, prompt_bindings={}),
        )

        def capture_wcc_specialization(typed_workflow, **kwargs):
            if typed_workflow.definition.name == "entry":
                captured_specializations.append(
                    kwargs["specialize_workflow"]("call-runner", {"runner": resolved_runner})
                )
            return SimpleNamespace(typed_workflow=typed_workflow)

        monkeypatch.setattr(
            wcc_defunctionalize,
            "_lower_one_wcc_workflow",
            capture_wcc_specialization,
        )
        lowered_workflows = lower_wcc_m4_workflow_definitions(
            result.typed_workflows,
            typed_procedures=result.typed_procedures,
            resolved_procedures_by_name=MappingProxyType(
                {
                    procedure.definition.name: procedure
                    for procedure in result.typed_procedures
                }
            ),
            procedure_type_envs={
                procedure.definition.name: type_env
                for procedure in result.typed_procedures
            },
            procedure_catalog=result.procedure_catalog,
            workflow_path=path,
            workflow_catalog=result.workflow_catalog,
            imported_workflow_bundles={},
            extern_environment=result.extern_environment,
            command_boundary_environment=result.command_boundary_environment,
            type_env=type_env,
            target_dsl_version=result.module.target_dsl_version,
        )
    specialized = (
        captured_specializations[0]
        if lowering_route is LoweringRoute.WCC_M4
        else next(
            lowered.typed_workflow
            for lowered in lowered_workflows
            if lowered.typed_workflow.definition.name.startswith("call-runner__spec__")
        )
    )

    assert specialized.definition.return_spec.guidance.description == "Forwarded workflow output."


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
