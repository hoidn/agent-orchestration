from dataclasses import FrozenInstanceError
import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_module
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    render_diagnostic,
    render_diagnostics,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import build_syntax_module


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURES / "modules"


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def test_render_diagnostic_includes_location_and_form_path() -> None:
    start = SourcePosition(
        path="tests/fixtures/workflow_lisp/invalid/example.orc",
        line=3,
        column=5,
        offset=18,
    )
    end = SourcePosition(
        path="tests/fixtures/workflow_lisp/invalid/example.orc",
        line=3,
        column=14,
        offset=27,
    )
    span = SourceSpan(start=start, end=end)
    diagnostic = LispFrontendDiagnostic(
        code="frontend_parse_error",
        message="unexpected closing parenthesis",
        span=span,
        form_path=("workflow-lisp", "defrecord", "ChecksResult"),
        notes=("while reading field list",),
    )

    rendered = render_diagnostic(diagnostic)

    assert "tests/fixtures/workflow_lisp/invalid/example.orc:3:5" in rendered
    assert "[frontend_parse_error]" in rendered
    assert "unexpected closing parenthesis" in rendered
    assert "workflow-lisp > defrecord > ChecksResult" in rendered
    assert "while reading field list" in rendered
    assert render_diagnostics((diagnostic,)) == rendered

    with pytest.raises(FrozenInstanceError):
        diagnostic.message = "mutated"


def test_frontend_compile_error_exposes_diagnostics_tuple() -> None:
    span = SourceSpan(
        start=SourcePosition(path="module.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="module.orc", line=1, column=6, offset=5),
    )
    diagnostics = (
        LispFrontendDiagnostic(
            code="definition_duplicate",
            message="duplicate definition `Thing`",
            span=span,
        ),
        LispFrontendDiagnostic(
            code="type_unknown",
            message="unknown type `Missing`",
            span=span,
        ),
    )

    error = LispFrontendCompileError(diagnostics)

    assert error.diagnostics == diagnostics
    assert isinstance(error.diagnostics, tuple)
    assert "[definition_duplicate]" in str(error)
    assert "[type_unknown]" in str(error)


def test_compile_stage1_renders_unknown_type_diagnostic_with_field_location() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "unknown_type.orc")

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "unknown_type.orc:5:5" in rendered
    assert "[type_unknown]" in rendered
    assert "unknown type `MissingType`" in rendered
    assert "workflow-lisp > defrecord > ChecksResult" in rendered


def test_compile_stage1_renders_unsupported_target_dsl_diagnostic() -> None:
    parse_tree = read_sexpr_file(FIXTURES / "invalid" / "unsupported_target_dsl.orc")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(parse_tree)

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "unsupported_target_dsl.orc:3:16" in rendered
    assert "[target_dsl_unsupported]" in rendered
    assert "unsupported target DSL `2.15`" in rendered


def test_compile_stage1_preserves_diagnostic_order(tmp_path: Path) -> None:
    path = tmp_path / "multiple_errors.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord ProblemRecord",
                "    (status MissingA)",
                "    (status MissingB))",
                "  (defrecord ProblemRecord",
                "    (report MissingC)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(path)

    diagnostics = excinfo.value.diagnostics

    assert [diagnostic.code for diagnostic in diagnostics] == [
        "definition_duplicate",
        "record_field_duplicate",
        "type_unknown",
        "type_unknown",
        "type_unknown",
    ]


def test_compile_stage1_renders_macro_expansion_notes_in_stable_order() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "macro_emits_invalid_form.orc")

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "[macro_emits_invalid_ast]" in rendered
    assert "expanded from macro `broken-workflow` call at" in rendered
    assert "macro definition at" in rendered


def test_compile_stage3_renders_macro_expansion_notes_for_downstream_command_errors(tmp_path: Path) -> None:
    path = tmp_path / "macro_command_result_missing_boundary.orc"
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
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (emit-command-workflow command_checks)",
                "  (defmacro emit-command-workflow (name)",
                "    (defworkflow name",
                "      ((report_path WorkReport))",
                "      -> ChecksResult",
                "      (command-result run_checks",
                '        :argv ("python" "scripts/run_checks.py" report_path)',
                "        :returns ChecksResult))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "command_adapter_missing_contract"
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-command-workflow"
    assert "expanded from macro `emit-command-workflow` call at" in rendered
    assert "macro definition at" in rendered


def test_compile_stage3_reports_macro_emitted_malformed_letstar_as_frontend_diagnostic(tmp_path: Path) -> None:
    path = tmp_path / "macro_emits_malformed_letstar.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Out",
                "    (value String))",
                "  (emit-broken-workflow broken)",
                "  (defmacro emit-broken-workflow (name)",
                "    (defworkflow name",
                "      ()",
                "      -> Out",
                "      (let*))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.message == "`let*` requires a binding list and one body"
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-broken-workflow"
    assert "expanded from macro `emit-broken-workflow` call at" in rendered


def test_compile_stage3_renders_macro_expansion_notes_for_downstream_name_unknown_errors(tmp_path: Path) -> None:
    path = tmp_path / "macro_record_missing_name.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Out",
                "    (value String))",
                "  (emit-record-workflow broken)",
                "  (defmacro emit-record-workflow (name)",
                "    (defworkflow name",
                "      ()",
                "      -> Out",
                "      (record Out :value missing_name))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "name_unknown"
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-record-workflow"
    assert "expanded from macro `emit-record-workflow` call at" in rendered
    assert "macro definition at" in rendered


def test_compile_stage3_renders_procedure_provenance_notes_for_shared_validation_errors(tmp_path: Path) -> None:
    path = tmp_path / "procedure_validation_notes.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath EscapedReport",
                "    :kind relpath",
                '    :under "../escape"',
                "    :must-exist true)",
                "  (defrecord EscapedSummary",
                "    (report EscapedReport))",
                "  (defproc escaped-summary",
                "    ((report_path EscapedReport))",
                "    -> EscapedSummary",
                "    :effects ()",
                "    :lowering inline",
                "    (record EscapedSummary",
                "      :report report_path))",
                "  (defworkflow orchestrate",
                "    ((report_path EscapedReport))",
                "    -> EscapedSummary",
                "    (escaped-summary report_path)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=True, workspace_root=tmp_path)

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "procedure call site at" in rendered
    assert "procedure definition at" in rendered


def test_compile_stage3_renders_macro_expansion_notes_for_downstream_provider_parse_errors(tmp_path: Path) -> None:
    path = tmp_path / "macro_provider_result_invalid_inputs.orc"
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
                "  (defrecord ImplementationState",
                "    (status String)",
                "    (report WorkReport))",
                "  (emit-provider-workflow provider_attempt)",
                "  (defmacro emit-provider-workflow (name)",
                "    (defworkflow name",
                "      ((input WorkReport)",
                "       (report_path WorkReport))",
                "      -> ImplementationState",
                "      (provider-result providers.execute",
                "        :prompt prompts.implementation.execute",
                "        :inputs report_path",
                "        :returns ImplementationState))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(path, validate_shared=False)

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == "frontend_parse_error"
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-provider-workflow"
    assert "expanded from macro `emit-provider-workflow` call at" in rendered
    assert "macro definition at" in rendered


@pytest.mark.parametrize(
    ("provider_externs", "prompt_externs", "expected_code", "expected_message"),
    [
        (
            {},
            {"prompts.implementation.execute": "prompts/implementation/execute.md"},
            "provider_result_provider_invalid",
            "provider `providers.execute` is not a declared provider extern",
        ),
        (
            {"providers.execute": "test-provider"},
            {},
            "provider_result_prompt_invalid",
            "prompt `prompts.implementation.execute` is not a declared prompt extern",
        ),
    ],
)
def test_compile_stage3_renders_macro_expansion_notes_for_provider_extern_validation_errors(
    tmp_path: Path,
    provider_externs: dict[str, str],
    prompt_externs: dict[str, str],
    expected_code: str,
    expected_message: str,
) -> None:
    path = tmp_path / "macro_provider_result_missing_extern.orc"
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
                "  (defrecord ImplementationState",
                "    (status String)",
                "    (report WorkReport))",
                "  (emit-provider-workflow provider_attempt)",
                "  (defmacro emit-provider-workflow (name)",
                "    (defworkflow name",
                "      ((input WorkReport)",
                "       (report_path WorkReport))",
                "      -> ImplementationState",
                "      (provider-result providers.execute",
                "        :prompt prompts.implementation.execute",
                "        :inputs (input report_path)",
                "        :returns ImplementationState))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    rendered = render_diagnostic(diagnostic)

    assert diagnostic.code == expected_code
    assert expected_message in diagnostic.message
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-provider-workflow"
    assert "expanded from macro `emit-provider-workflow` call at" in rendered
    assert "macro definition at" in rendered


def test_compile_stage1_entrypoint_renders_module_path_mismatch_diagnostic() -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage1_entrypoint", None)
    assert callable(compile_fn), "compile_stage1_entrypoint is missing"

    source_root = MODULE_FIXTURES / "invalid" / "path_mismatch"
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_fn(
            source_root / "neurips" / "bad.orc",
            source_roots=(source_root,),
        )

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "[module_path_mismatch]" in rendered
    assert "other/place" in rendered
