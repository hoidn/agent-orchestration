from dataclasses import FrozenInstanceError

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    RunRefBundleProgram,
    RunRefExpr,
    RunRefSource,
    elaborate_expression,
)
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
        elaborate_expression(
            _expression(_mode_one_source()),
            bound_names=frozenset(),
            target_dsl_version="2.23",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_target_dsl_unsupported"


def test_run_ref_target_224_elaborates_frozen_mode_one_carriers() -> None:
    expr = elaborate_expression(
        _expression(_mode_one_source()),
        bound_names=frozenset(),
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
