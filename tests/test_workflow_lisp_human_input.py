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


@pytest.mark.parametrize(
    "body",
    (
        """  (defworkflow ask ((question String)) -> HumanReply
    (request-input \"unused-question\"))""",
        """  (defworkflow ask ((question String)) -> HumanReply
    (let* ((prepared (string/concat question \"\")))
      (request-input prepared)))""",
    ),
)
def test_request_input_compiles_literal_and_pure_computed_questions(
    tmp_path: Path,
    body: str,
) -> None:
    result = _compile(
        _write_module(tmp_path / "request_input.orc", body),
        workspace=tmp_path,
    )

    bundle = result.validated_bundles["ask"]
    steps = [
        step
        for step in bundle.surface.steps
        if step.kind.value == "request_input"
    ]
    assert len(steps) == 1
    assert set(steps[0].request_input) == {"question"}


def test_request_input_materializes_an_effectful_string_before_the_host_step(
    tmp_path: Path,
) -> None:
    result = _compile(
        _write_module(
            tmp_path / "effectful_question.orc",
            """  (defproc ask-host ((question String)) -> HumanReply
    :effects ((uses-provider providers.question) (host-input))
    :lowering inline
    (request-input
      (provider-result providers.question
        :prompt prompts.question
        :inputs (question)
        :returns String)))
  (defworkflow ask ((question String)) -> HumanReply
    (ask-host question))""",
        ),
        workspace=tmp_path,
        provider_externs={"providers.question": "test-provider"},
        prompt_externs={"prompts.question": "prompts/question.md"},
        validate_shared=False,
    )

    steps = result.lowered_workflows[0].authored_mapping["steps"]
    host_index, host_step = next(
        (index, step)
        for index, step in enumerate(steps)
        if "request_input" in step
    )
    provider_index = next(
        index for index, step in enumerate(steps) if "provider" in step
    )
    assert provider_index < host_index
    assert set(host_step["request_input"]["question"]) == {"ref"}


def test_request_input_compiles_selected_question(
    tmp_path: Path,
) -> None:
    result = _compile(
        _write_module(
            tmp_path / "selected_reply.orc",
            """  (defproc select-reply ((question String) (take_first Bool)) -> HumanReply
    :effects ((host-input))
    :lowering inline
    (if take_first
      (request-input (string/concat question ""))
      (request-input question)))
  (defworkflow ask ((question String) (take_first Bool)) -> HumanReply
    (select-reply question take_first))""",
        ),
        workspace=tmp_path,
    )

    assert set(result.validated_bundles["ask"].surface.outputs) == {
        "return__variant",
        "return__text",
    }


def test_request_input_matches_the_fixed_reply_variants(
    tmp_path: Path,
) -> None:
    result = _compile(
        _write_module(
            tmp_path / "matched_reply.orc",
            """  (defproc reply-text ((question String)) -> String
    :effects ((host-input))
    :lowering inline
    (match (request-input question)
      ((ANSWERED reply) reply.text)
      ((CANCELLED cancelled) "")))
  (defworkflow ask ((question String)) -> String
    (reply-text question))""",
        ),
        workspace=tmp_path,
    )

    assert set(result.validated_bundles["ask"].surface.outputs) == {"__result__"}


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


def test_private_request_input_procedure_returns_the_fixed_reply(
    tmp_path: Path,
) -> None:
    result = _compile(
        _write_module(
            tmp_path / "private_request_input.orc",
            """  (defproc ask-host ((question String)) -> HumanReply
    :effects ((host-input))
    :lowering private-workflow
    (request-input question))
  (defworkflow ask ((question String)) -> HumanReply
    (ask-host question))""",
        ),
        workspace=tmp_path,
    )

    request_steps = [
        step
        for bundle in result.validated_bundles.values()
        for step in bundle.surface.steps
        if step.kind.value == "request_input"
    ]
    assert len(request_steps) == 1
