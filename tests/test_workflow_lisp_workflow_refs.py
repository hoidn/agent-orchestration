from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


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


def test_workflow_ref_same_file_higher_order_calls_compile_and_validate(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "workflow_refs_same_file.orc",
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
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
    )

    assert "echo-helper" in result.validated_bundles
    assert "entry" in result.validated_bundles


def test_workflow_ref_forwarding_through_defproc_compiles_and_validates(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "workflow_refs_forwarding.orc",
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "echo-helper" in result.validated_bundles
    assert "entry" in result.validated_bundles


def test_workflow_ref_specialization_through_owner_seam_compiles_and_validates(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "workflow_refs_forwarding.orc",
        command_boundaries=_workflow_ref_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
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
        )

    _assert_diagnostic_code(excinfo, expected_code)
