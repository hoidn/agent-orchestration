"""Frontend/WCC carriage for the target-2.32 host-input expression leaf."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import HostInputEffect
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


def _type_env(span) -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.32",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=span,
        )
    )


def _write_module(path: Path, body: str) -> Path:
    path.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.32")',
                "  (defmodule human_input_frontend)",
                "  (export ask)",
                body,
                ")",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _compile(path: Path, *, workspace: Path, **kwargs):
    return compile_stage3_module(
        path,
        lowering_route="wcc_m4",
        workspace_root=workspace,
        **kwargs,
    )


def test_request_input_types_as_fixed_reply_and_infers_host_effect() -> None:
    expr = elaborate_expression(
        _expression('(request-input "unused-question")'),
        bound_names=frozenset(),
        target_dsl_version="2.32",
    )

    typed = typecheck_expression(expr, type_env=_type_env(expr.span), value_env={})

    assert typed.type_ref.name == "HumanReply"
    assert typed.effect_summary.direct_effects == frozenset({HostInputEffect()})


def test_request_input_rejects_an_old_target_before_typechecking() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression('(request-input "unused-question")'),
            bound_names=frozenset(),
            target_dsl_version="2.31",
        )

    assert excinfo.value.diagnostics


def test_request_input_requires_a_string_question() -> None:
    expr = elaborate_expression(
        _expression("(request-input false)"),
        bound_names=frozenset(),
        target_dsl_version="2.32",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(expr, type_env=_type_env(expr.span), value_env={})

    assert excinfo.value.diagnostics[0].code == "request_input_question_type_invalid"










def test_request_input_requires_a_matching_host_input_effect_declaration(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            _write_module(
                tmp_path / "missing_host_input_effect.orc",
                """  (defproc ask-host ((question String)) -> HumanReply
    :effects ()
    :lowering inline
    (request-input question))
  (defworkflow ask ((question String)) -> HumanReply
    (ask-host question))""",
            ),
            workspace=tmp_path,
        )

    assert any(
        diagnostic.code == "procedure_effect_mismatch"
        for diagnostic in excinfo.value.diagnostics
    )
