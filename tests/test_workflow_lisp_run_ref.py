from dataclasses import FrozenInstanceError
from typing import get_args

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    RunRefBundleProgram,
    RunRefExpr,
    RunRefSource,
    ExprNode,
    parse_run_ref_expression,
)
from orchestrator.workflow_lisp.form_registry import get_form_spec
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode


FORM_PATH = ("workflow-lisp", "run-ref-test")


def _expression(source: str) -> SyntaxNode:
    parsed = read_sexpr_text(source, source_path="run_ref_expression.orc")
    assert len(parsed.items) == 1
    datum = parsed.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="run_ref_expression.orc",
        form_path=FORM_PATH,
    )


def _mode_one_source() -> str:
    return " ".join(
        (
            "(run-ref",
            ':source (:repo "file:///workspace"',
            ':commit "0123456789abcdef0123456789abcdef01234567")',
            ":program (:bundle child)",
            ":inputs ()",
            ":policy (:setup ()))",
        )
    )


def test_run_ref_rejects_target_223() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(_mode_one_source()),
            target_dsl_version="2.23",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_target_dsl_unsupported"


def test_run_ref_target_224_elaborates_frozen_mode_one_carriers() -> None:
    expr = parse_run_ref_expression(
        _expression(_mode_one_source()),
        target_dsl_version="2.24",
    )

    assert expr == RunRefExpr(
        source=RunRefSource(
            repo="file:///workspace",
            commit="0123456789abcdef0123456789abcdef01234567",
        ),
        program=RunRefBundleProgram(workflow_name="child"),
        inputs=(),
        setup=(),
        span=expr.span,
        form_path=FORM_PATH,
    )
    with pytest.raises(FrozenInstanceError):
        expr.inputs = ()


@pytest.mark.parametrize(
    "source",
    (
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs ())",
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs () :inputs () :policy (:setup ()))",
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs () :policy (:setup ()) :extra true)",
        '(run-ref :source (:repo "file:///workspace") '
        ":program (:bundle child) :inputs () :policy (:setup ()))",
    ),
)
def test_run_ref_structural_errors_use_closed_shape_diagnostic(source: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_shape_invalid"


@pytest.mark.parametrize(
    "source",
    (
        "(run-ref :source workspace :program (:bundle child) "
        ":inputs () :policy (:setup ()))",
        "(run-ref :source (:repo workspace "
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs () :policy (:setup ()))",
        '(run-ref :source (:repo "file:///workspace" :commit 12) '
        ":program (:bundle child) :inputs () :policy (:setup ()))",
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ':program (:bundle "child") :inputs () :policy (:setup ()))',
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ':program (:bundle child) :inputs () :policy (:setup "none"))',
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs () :policy setup)",
    ),
)
def test_run_ref_nonliteral_static_fields_use_closed_literal_diagnostic(
    source: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_literal_required"


@pytest.mark.parametrize(
    "program",
    (
        '(:path "candidate.orc" :entry child)',
        "(:workflow child)",
    ),
)
def test_run_ref_program_discriminator_uses_closed_mode_diagnostic(
    program: str,
) -> None:
    source = _mode_one_source().replace("(:bundle child)", program)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_program_mode_invalid"


def test_run_ref_parser_is_not_registered_for_ordinary_elaboration() -> None:
    assert get_form_spec("run-ref", target_dsl_version="2.24") is None
    assert RunRefExpr in get_args(ExprNode)
