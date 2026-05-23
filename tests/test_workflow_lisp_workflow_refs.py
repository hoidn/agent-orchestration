from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    serialize_diagnostic,
)
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_DRAIN_FIXTURE = FIXTURES / "valid" / "drain_stdlib_backlog_drain.orc"
INVALID_SIGNATURE_FIXTURE = FIXTURES / "invalid" / "backlog_drain_workflow_ref_signature_invalid.orc"


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


def test_workflow_ref_type_surface_remains_out_of_scope_for_required_lints_slice(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workflow_ref_type_surface.orc"
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
                "  (defworkflow invoke-runner",
                "    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])",
                "     (input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput",
                "      :report input.report)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    _assert_diagnostic_code(excinfo, "frontend_parse_error")


def test_workflow_ref_literal_surface_remains_out_of_scope_for_required_lints_slice(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workflow_ref_literal_surface.orc"
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
                "    (record WorkflowOutput",
                "      :report input.report))",
                "  (defworkflow orchestrate",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (let* ((runner",
                "             (workflow-ref echo-helper)))",
                "      (record WorkflowOutput",
                "        :report input.report))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    _assert_diagnostic_code(excinfo, "procedure_call_unknown")


def test_signature_erased_required_lint_replaces_live_workflow_ref_signature_failures(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            INVALID_SIGNATURE_FIXTURE,
            command_boundaries=_command_boundaries(),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]

    assert diagnostic.code == "workflow_call_signature_erased"
    payload = serialize_diagnostic(diagnostic)
    assert payload["diagnostic_kind"] == "required_lint"
    assert payload["validation_pass"] == "reference"
    assert payload["authority_layer"] == "frontend"


def test_signature_erased_required_lint_replaces_unknown_workflow_ref_failures(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workflow_ref_unknown.orc"
    path.write_text(
        VALID_DRAIN_FIXTURE.read_text(encoding="utf-8").replace(
            ":selector selector-run",
            ":selector missing-selector",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            command_boundaries=_command_boundaries(),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]

    assert diagnostic.code == "workflow_call_signature_erased"
    assert "missing-selector" in diagnostic.message
