import ast
import importlib
import inspect
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment, PathTypeRef
from orchestrator.workflow_lisp.typecheck import typecheck_expression


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"
FORM_PATH = ("workflow-lisp", "variant-proof-test")


def _build_type_env() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(compile_stage1_module(TYPE_FIXTURE))


def _expression_syntax(source: str, *, form_path: tuple[str, ...] = FORM_PATH) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="inline_variant_expression.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_variant_expression.orc",
        form_path=form_path,
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _typecheck_top_level_names() -> set[str]:
    source_path = Path(importlib.import_module("orchestrator.workflow_lisp.typecheck").__file__)
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in module.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    }


def test_variant_proof_owner_split_moves_proof_types_out_of_typecheck_facade() -> None:
    package_dir = Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent
    proof_path = package_dir / "typecheck_proofs.py"
    dispatch_path = package_dir / "typecheck_dispatch.py"
    dispatch_source = dispatch_path.read_text(encoding="utf-8")
    typecheck_module = importlib.import_module("orchestrator.workflow_lisp.typecheck")

    assert proof_path.is_file()
    assert inspect.getsourcefile(typecheck_module.ProofFact) == str(proof_path)
    assert inspect.getsourcefile(typecheck_module.ProofScope) == str(proof_path)
    assert "ProofFact" not in _typecheck_top_level_names()
    assert "ProofScope" not in _typecheck_top_level_names()
    assert "def _resolve_field_access(" not in dispatch_source
    assert "if isinstance(expr, MatchExpr):" not in dispatch_source
    assert "typecheck_match_expr(" in dispatch_source
    assert "typecheck_field_access_expr(" in dispatch_source


def test_typecheck_match_requires_union_subject_and_exhaustive_variants() -> None:
    type_env = _build_type_env()
    literal_probe = _expression_syntax('"seed"')
    report_type = type_env.resolve_type(
        "WorkReport",
        span=literal_probe.span,
        form_path=literal_probe.form_path,
    )
    attempt_type = type_env.resolve_type(
        "ImplementationState",
        span=literal_probe.span,
        form_path=literal_probe.form_path,
    )

    with pytest.raises(LispFrontendCompileError) as not_union:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax(
                    "(match report-path "
                    "((COMPLETED completed) completed.execution_report) "
                    "((BLOCKED blocked) blocked.progress_report))"
                ),
                bound_names=frozenset({"report-path"}),
            ),
            type_env=type_env,
            value_env={"report-path": report_type},
        )
    _assert_diagnostic_code(not_union, "match_subject_not_union")

    with pytest.raises(LispFrontendCompileError) as non_exhaustive:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax(
                    "(match attempt ((COMPLETED completed) completed.execution_report))"
                ),
                bound_names=frozenset({"attempt"}),
            ),
            type_env=type_env,
            value_env={"attempt": attempt_type},
        )
    _assert_diagnostic_code(non_exhaustive, "union_match_non_exhaustive")

    with pytest.raises(LispFrontendCompileError) as unknown_variant:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax(
                    "(match attempt "
                    "((COMPLETED completed) completed.execution_report) "
                    "((MISSING blocked) blocked.progress_report))"
                ),
                bound_names=frozenset({"attempt"}),
            ),
            type_env=type_env,
            value_env={"attempt": attempt_type},
        )
    _assert_diagnostic_code(unknown_variant, "union_variant_unknown")


def test_typecheck_match_narrows_binding_and_subject_inside_each_arm() -> None:
    type_env = _build_type_env()
    probe = _expression_syntax('"seed"')
    attempt_type = type_env.resolve_type(
        "ImplementationState",
        span=probe.span,
        form_path=probe.form_path,
    )

    typed = typecheck_expression(
        elaborate_expression(
            _expression_syntax(
                "(match attempt "
                "((COMPLETED completed) completed.execution_report) "
                "((BLOCKED blocked) attempt.progress_report))"
            ),
            bound_names=frozenset({"attempt"}),
        ),
        type_env=type_env,
        value_env={"attempt": attempt_type},
    )

    assert isinstance(typed.type_ref, PathTypeRef)
    assert typed.type_ref.name == "WorkReport"


def test_typecheck_variant_field_access_requires_proof_context() -> None:
    type_env = _build_type_env()
    probe = _expression_syntax('"seed"')
    attempt_type = type_env.resolve_type(
        "ImplementationState",
        span=probe.span,
        form_path=probe.form_path,
    )

    with pytest.raises(LispFrontendCompileError) as unproved:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax("attempt.execution_report"),
                bound_names=frozenset({"attempt"}),
            ),
            type_env=type_env,
            value_env={"attempt": attempt_type},
        )
    _assert_diagnostic_code(unproved, "variant_ref_unproved")

    with pytest.raises(LispFrontendCompileError) as wrong_variant:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax(
                    "(match attempt "
                    "((COMPLETED completed) completed.progress_report) "
                    "((BLOCKED blocked) blocked.progress_report))"
                ),
                bound_names=frozenset({"attempt"}),
            ),
            type_env=type_env,
            value_env={"attempt": attempt_type},
        )
    _assert_diagnostic_code(wrong_variant, "variant_ref_wrong_variant")


def test_typecheck_match_requires_consistent_arm_result_types() -> None:
    type_env = _build_type_env()
    probe = _expression_syntax('"seed"')
    attempt_type = type_env.resolve_type(
        "ImplementationState",
        span=probe.span,
        form_path=probe.form_path,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax(
                    "(match attempt "
                    "((COMPLETED completed) completed.execution_report) "
                    "((BLOCKED blocked) blocked.blocker_class))"
                ),
                bound_names=frozenset({"attempt"}),
            ),
            type_env=type_env,
            value_env={"attempt": attempt_type},
        )

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_typecheck_if_inherits_existing_proof_scope() -> None:
    type_env = _build_type_env()
    probe = _expression_syntax('"seed"')
    attempt_type = type_env.resolve_type(
        "ImplementationState",
        span=probe.span,
        form_path=probe.form_path,
    )
    report_type = type_env.resolve_type(
        "WorkReport",
        span=probe.span,
        form_path=probe.form_path,
    )

    typed = typecheck_expression(
        elaborate_expression(
            _expression_syntax(
                "(match attempt "
                "((COMPLETED completed) "
                "(if ready completed.execution_report fallback-report)) "
                "((BLOCKED blocked) "
                "(if ready blocked.progress_report fallback-report)))"
            ),
            bound_names=frozenset({"attempt", "ready", "fallback-report"}),
        ),
        type_env=type_env,
        value_env={
            "attempt": attempt_type,
            "ready": type_env.resolve_type("Bool", span=probe.span, form_path=probe.form_path),
            "fallback-report": report_type,
        },
    )

    assert isinstance(typed.type_ref, PathTypeRef)
    assert typed.type_ref.name == "WorkReport"


def test_typecheck_if_does_not_create_variant_proof() -> None:
    type_env = _build_type_env()
    probe = _expression_syntax('"seed"')
    attempt_type = type_env.resolve_type(
        "ImplementationState",
        span=probe.span,
        form_path=probe.form_path,
    )
    report_type = type_env.resolve_type(
        "WorkReport",
        span=probe.span,
        form_path=probe.form_path,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            elaborate_expression(
                _expression_syntax(
                    "(if ready attempt.execution_report fallback-report)"
                ),
                bound_names=frozenset({"attempt", "ready", "fallback-report"}),
            ),
            type_env=type_env,
            value_env={
                "attempt": attempt_type,
                "ready": type_env.resolve_type("Bool", span=probe.span, form_path=probe.form_path),
                "fallback-report": report_type,
            },
        )

    _assert_diagnostic_code(excinfo, "variant_ref_unproved")
