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
