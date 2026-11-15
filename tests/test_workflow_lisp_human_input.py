"""Frontend/WCC carriage for the target-2.32 host-input expression leaf."""

from __future__ import annotations

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.definitions import WorkflowLispModule


def _expression(source: str) -> SyntaxNode:
    module = read_sexpr_text(source, source_path="human_input_expression.orc")
    assert len(module.items) == 1
    datum = module.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="human_input_expression.orc",
        form_path=("workflow-lisp", "human-input-expression"),
    )


def _type_env(span, target: str = "2.40") -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version=target,
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=span,
        )
    )


def test_request_input_requires_a_string_question() -> None:
    expr = elaborate_expression(
        _expression("(request-input false :returns String)"),
        bound_names=frozenset(),
        target_dsl_version="2.40",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(expr, type_env=_type_env(expr.span), value_env={})

    assert excinfo.value.diagnostics[0].code == "request_input_question_type_invalid"
