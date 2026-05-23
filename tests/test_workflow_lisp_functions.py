import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
INVALID_FIXTURES = FIXTURES / "invalid"
MODULE_FIXTURES = FIXTURES / "modules" / "valid" / "imported_defun"

def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def _functions_module():
    try:
        return importlib.import_module("orchestrator.workflow_lisp.functions")
    except ModuleNotFoundError as exc:
        pytest.fail(f"workflow Lisp helper layer is missing: {exc}")


def _compile(path: Path, *, tmp_path: Path):
    return compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )


def _compile_stage3_entrypoint(path: Path, *, source_root: Path, tmp_path: Path):
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"
    return compile_fn(
        path,
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )


def _compile_definition_module(path: Path):
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module, syntax_module


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def test_build_function_catalog_registers_local_helpers_before_body_checking() -> None:
    functions = _functions_module()
    module, syntax_module = _compile_definition_module(VALID_FIXTURES / "defun_forward_ref.orc")
    type_env = FrontendTypeEnvironment.from_module(module)

    elaborate = getattr(functions, "elaborate_function_definitions", None)
    build_catalog = getattr(functions, "build_function_catalog", None)

    assert callable(elaborate), "elaborate_function_definitions is missing"
    assert callable(build_catalog), "build_function_catalog is missing"

    function_defs = elaborate(syntax_module)
    catalog = build_catalog(function_defs, type_env=type_env)

    assert tuple(catalog.definitions_by_name) == ("render-summary", "extract-report")
    assert tuple(catalog.signatures_by_name) == ("render-summary", "extract-report")


def test_compile_stage3_supports_helper_forward_references(tmp_path: Path) -> None:
    result = _compile(VALID_FIXTURES / "defun_forward_ref.orc", tmp_path=tmp_path)

    assert result.typed_workflows[0].definition.name == "orchestrate"


def test_compile_stage3_rejects_helper_return_type_mismatches(tmp_path: Path) -> None:
    path = tmp_path / "defun_return_type_invalid.orc"
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
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defun summarize",
                "    ((input ChecksResult))",
                "    -> WorkReport",
                "    (record ImplementationSummary",
                "      :report input.report))",
                "  (defworkflow orchestrate",
                "    ((input ChecksResult))",
                "    -> ImplementationSummary",
                "    (summarize input)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    diagnostic_codes = [diagnostic.code for diagnostic in excinfo.value.diagnostics]
    assert "function_return_type_invalid" in diagnostic_codes


def test_compile_stage3_rejects_effectful_helper_bodies(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_FIXTURES / "defun_effectful.orc", tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "pure_function_has_effect")


def test_compile_stage3_rejects_helper_cycles(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_FIXTURES / "defun_cycle.orc", tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "function_cycle")


def test_compile_stage3_rejects_same_file_helper_procedure_name_collisions(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_FIXTURES / "defun_proc_name_collision.orc", tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "callable_name_collision")


def test_compile_stage3_normalizes_helper_calls_before_lowering(tmp_path: Path) -> None:
    result = _compile(VALID_FIXTURES / "defun_forward_ref.orc", tmp_path=tmp_path)

    assert "FunctionCallExpr" not in repr(result.typed_workflows[0].typed_body.expr)
    assert "FunctionCallExpr" not in repr(result.typed_workflows[0].typed_body)


def test_compile_stage3_entrypoint_supports_imported_helpers(tmp_path: Path) -> None:
    path = MODULE_FIXTURES / "entry.orc"

    result = _compile_stage3_entrypoint(path, source_root=MODULE_FIXTURES, tmp_path=tmp_path)

    assert result.entry_result.typed_workflows[0].definition.name == "entry::orchestrate"


def test_compile_stage3_normalizes_helper_calls_inside_if(tmp_path: Path) -> None:
    path = tmp_path / "if_helper_normalization.orc"
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
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defun choose-summary-helper",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (record ImplementationSummary",
                "      :report report_path))",
                "  (defworkflow choose-summary",
                "    ((ready Bool)",
                "     (report_path WorkReport)",
                "     (fallback_path WorkReport))",
                "    -> ImplementationSummary",
                "    (if ready",
                "      (choose-summary-helper report_path)",
                "      (record ImplementationSummary",
                "        :report fallback_path))))",
            ]
        ),
        encoding="utf-8",
    )

    result = _compile(path, tmp_path=tmp_path)

    assert "FunctionCallExpr" not in repr(result.typed_workflows[0].typed_body.expr)
    assert "FunctionCallExpr" not in repr(result.typed_workflows[0].typed_body)


def test_function_dependency_walker_descends_through_if_expr(tmp_path: Path) -> None:
    functions = _functions_module()
    elaborate = getattr(functions, "elaborate_function_definitions", None)
    build_catalog = getattr(functions, "build_function_catalog", None)
    typecheck_defs = getattr(functions, "typecheck_function_definitions", None)
    dependency_walker = getattr(functions, "_function_dependencies", None)

    assert callable(elaborate), "elaborate_function_definitions is missing"
    assert callable(build_catalog), "build_function_catalog is missing"
    assert callable(typecheck_defs), "typecheck_function_definitions is missing"
    assert callable(dependency_walker), "_function_dependencies is missing"

    path = tmp_path / "if_helper_dependencies.orc"
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
                "  (defun leaf",
                "    ((report_path WorkReport))",
                "    -> WorkReport",
                "    report_path)",
                "  (defun branch",
                "    ((ready Bool) (report_path WorkReport) (fallback_path WorkReport))",
                "    -> WorkReport",
                "    (if ready",
                "      (leaf report_path)",
                "      fallback_path))",
                "  (defworkflow choose-summary",
                "    ((ready Bool)",
                "     (report_path WorkReport)",
                "     (fallback_path WorkReport))",
                "    -> WorkReport",
                "    (branch ready report_path fallback_path)))",
            ]
        ),
        encoding="utf-8",
    )
    module, syntax_module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    function_defs = elaborate(syntax_module)
    catalog = build_catalog(function_defs, type_env=type_env)
    typed_functions = typecheck_defs(
        function_defs,
        type_env=type_env,
        function_catalog=catalog,
    )
    render_summary = next(
        function
        for function in typed_functions
        if function.definition.name == "branch"
    )

    assert dependency_walker(render_summary.typed_body.expr) == {"leaf"}
