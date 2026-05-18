from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_module
from orchestrator.workflow_lisp.contracts import (
    derive_structured_result_contract,
    derive_workflow_signature_contracts,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import WorkflowLispSyntaxModule, build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, PrimitiveTypeRef, RecordTypeRef, UnionTypeRef
from orchestrator.workflow_lisp.workflows import (
    WorkflowSignature,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"


def _build_syntax_module(path: Path) -> WorkflowLispSyntaxModule:
    return build_syntax_module(read_sexpr_file(path))


def _build_type_env() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(compile_stage1_module(TYPE_FIXTURE))


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _typecheck_fixture(path: Path):
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=_build_type_env(),
        workflow_catalog=build_workflow_catalog(
            compile_stage1_module(TYPE_FIXTURE),
            workflow_defs,
            _build_type_env(),
        ),
    )


def test_typecheck_workflow_definitions_validates_same_file_call_signatures() -> None:
    typed_workflows = _typecheck_fixture(FIXTURES / "valid" / "structured_results.orc")

    assert [typed_workflow.definition.name for typed_workflow in typed_workflows] == [
        "provider_attempt",
        "command_checks",
        "orchestrate",
    ]
    assert isinstance(typed_workflows[0].signature.return_type_ref, UnionTypeRef)
    assert isinstance(typed_workflows[1].signature.return_type_ref, RecordTypeRef)
    assert typed_workflows[2].typed_body.type_ref == typed_workflows[0].signature.return_type_ref


def test_typecheck_workflow_definitions_rejects_unknown_callees() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(FIXTURES / "invalid" / "unknown_callee.orc")

    _assert_diagnostic_code(excinfo, "workflow_call_unknown")


def test_typecheck_workflow_definitions_rejects_return_type_mismatches(tmp_path: Path) -> None:
    mismatch_path = tmp_path / "return_type_mismatch.orc"
    mismatch_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow mismatch",
                "    ((report_path WorkReport))",
                "    -> ImplementationState",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(mismatch_path)

    _assert_diagnostic_code(excinfo, "return_type_mismatch")


def test_typecheck_provider_result_requires_record_or_union_return_types(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as bad_return:
        _typecheck_fixture(FIXTURES / "invalid" / "provider_result_bad_return.orc")
    _assert_diagnostic_code(bad_return, "provider_result_return_type_invalid")

    invalid_provider_path = tmp_path / "provider_operand_type_invalid.orc"
    invalid_provider_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defworkflow provider-attempt",
                "    ((provider Prompt)",
                "     (prompt Provider)",
                "     (input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationState",
                "    (provider-result provider",
                "      :prompt prompt",
                "      :inputs (input report_path)",
                "      :returns ImplementationState)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as invalid_operands:
        _typecheck_fixture(invalid_provider_path)

    _assert_diagnostic_code(invalid_operands, "type_mismatch")


def test_typecheck_command_result_rejects_inline_shell_and_python_glue() -> None:
    with pytest.raises(LispFrontendCompileError) as bad_return:
        _typecheck_fixture(FIXTURES / "invalid" / "command_result_bad_return.orc")
    _assert_diagnostic_code(bad_return, "command_result_return_type_invalid")

    with pytest.raises(LispFrontendCompileError) as inline_python:
        _typecheck_fixture(FIXTURES / "invalid" / "inline_python_command_result.orc")
    _assert_diagnostic_code(inline_python, "inline_python_command_in_workflow")

    with pytest.raises(LispFrontendCompileError) as inline_shell:
        _typecheck_fixture(FIXTURES / "invalid" / "inline_shell_command_result.orc")
    _assert_diagnostic_code(inline_shell, "inline_shell_command_in_workflow")


def test_derive_structured_result_contract_builds_output_bundle_for_record_results() -> None:
    type_env = _build_type_env()
    checks_result = type_env.resolve_type(
        "ChecksResult",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(checks_result, RecordTypeRef)
    contract = derive_structured_result_contract(
        checks_result,
        workflow_name="command_checks",
        step_id="command_checks__run_checks",
    )

    assert contract.contract_kind == "output_bundle"
    assert contract.path == ".orchestrate/workflow_lisp/command_checks/command_checks__run_checks/result.json"
    assert contract.payload["fields"] == [
        {
            "name": "status",
            "json_pointer": "/status",
            "type": "string",
        },
        {
            "name": "report",
            "json_pointer": "/report",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        },
    ]


def test_derive_structured_result_contract_builds_variant_output_for_union_results() -> None:
    type_env = _build_type_env()
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_state, UnionTypeRef)
    contract = derive_structured_result_contract(
        implementation_state,
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )

    assert contract.contract_kind == "variant_output"
    assert contract.payload["discriminant"] == {
        "name": "variant",
        "json_pointer": "/variant",
        "type": "enum",
        "allowed": ["COMPLETED", "BLOCKED"],
    }
    assert contract.payload["shared_fields"] == []
    assert contract.payload["variants"]["COMPLETED"]["fields"] == [
        {
            "name": "execution_report",
            "json_pointer": "/execution_report",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        }
    ]
    assert contract.payload["variants"]["BLOCKED"]["fields"][1] == {
        "name": "blocker_class",
        "json_pointer": "/blocker_class",
        "type": "enum",
        "allowed": ["missing_resource", "roadmap_conflict"],
    }


def test_generated_bundle_paths_are_deterministic() -> None:
    type_env = _build_type_env()
    implementation_state = type_env.resolve_type(
        "ImplementationState",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(implementation_state, UnionTypeRef)
    first = derive_structured_result_contract(
        implementation_state,
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )
    second = derive_structured_result_contract(
        implementation_state,
        workflow_name="provider_attempt",
        step_id="provider_attempt__result",
    )

    assert first.path == second.path
    assert first.payload == second.payload


def test_workflow_signature_contract_flattening_records_origin_metadata() -> None:
    type_env = _build_type_env()
    checks_result = type_env.resolve_type(
        "ChecksResult",
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "contract-test"),
    )

    assert isinstance(checks_result, RecordTypeRef)
    signature = WorkflowSignature(
        name="summarize_checks",
        params=(("input", checks_result),),
        return_type_ref=checks_result,
        span=_build_syntax_module(TYPE_FIXTURE).span,
        form_path=("workflow-lisp", "defworkflow", "summarize_checks"),
    )

    inputs, outputs, flattened = derive_workflow_signature_contracts(signature)

    assert tuple(inputs) == ("input__status", "input__report")
    assert tuple(outputs) == ("return__status", "return__report")
    assert [field.generated_name for field in flattened] == [
        "input__status",
        "input__report",
        "return__status",
        "return__report",
    ]
    assert flattened[0].source_path == ("input", "status")
    assert flattened[-1].source_path == ("return", "report")
    assert inputs["input__report"].definition == {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": True,
    }
