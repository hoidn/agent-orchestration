from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    Stage3ValidationProfile,
    _run_stage3_validation_pipeline,
    normalize_lowering_route,
)
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import (
    CallExpr,
    LetStarExpr,
    LiteralExpr,
    NameExpr,
    ProcedureCallExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.spans import SourceSpan
from orchestrator.workflow_lisp.syntax import (
    SyntaxNode,
    clone_caller_syntax,
)
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
from orchestrator.workflow_lisp.wcc.defunctionalize import (
    _frontend_expr_from_wcc_loop_binding_value,
)
from orchestrator.workflow_lisp.wcc.model import (
    WccCall,
    WccIdentityFactory,
    WccPerform,
)


FORM_PATH = ("workflow-lisp", "authored-callee-span-test")


def _expression_syntax(source: str) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="authored_callee_span.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="authored_callee_span.orc",
        form_path=FORM_PATH,
    )


def _source_text(source: str, span: SourceSpan) -> str:
    assert span.start.path == span.end.path == "authored_callee_span.orc"
    return source[span.start.offset : span.end.offset]


@pytest.mark.parametrize(
    ("source", "procedure_names", "expected_type"),
    [
        ("(review review)", frozenset({"review"}), ProcedureCallExpr),
        ("(call review :review review)", frozenset(), CallExpr),
    ],
)
def test_direct_authored_calls_retain_only_the_exact_callee_datum_span(
    source: str,
    procedure_names: frozenset[str],
    expected_type: type[CallExpr] | type[ProcedureCallExpr],
) -> None:
    expr = elaborate_expression(
        _expression_syntax(source),
        bound_names=frozenset({"review"}),
        procedure_names=procedure_names,
    )

    assert isinstance(expr, expected_type)
    assert _source_text(source, expr.span) == source
    authored_callee_span = getattr(expr, "authored_callee_span", None)
    assert authored_callee_span is not None
    assert _source_text(source, authored_callee_span) == "review"
    assert authored_callee_span != expr.span
    assert authored_callee_span.start.offset == source.index("review")
    assert authored_callee_span.end.offset <= source.rindex("review")
    assert replace(expr, authored_callee_span=None) == expr


@pytest.mark.parametrize(
    ("source", "procedure_names"),
    [
        ("(review review)", frozenset({"review"})),
        ("(call review :review review)", frozenset()),
    ],
)
def test_authored_callee_span_survives_traversal_caller_clone_and_ordinary_copies(
    source: str,
    procedure_names: frozenset[str],
) -> None:
    syntax = _expression_syntax(source)
    expr = elaborate_expression(
        syntax,
        bound_names=frozenset({"review"}),
        procedure_names=procedure_names,
    )
    expected = getattr(expr, "authored_callee_span", None)
    assert expected is not None

    cloned_datum = clone_caller_syntax(syntax.datum)
    syntax_clone = replace(syntax, datum=cloned_datum)
    elaborated_clone = elaborate_expression(
        syntax_clone,
        bound_names=frozenset({"review"}),
        procedure_names=procedure_names,
    )
    rewritten = replace(expr, callee_name=f"{expr.callee_name}.specialized")
    container = LetStarExpr(
        bindings=(("result", rewritten),),
        body=NameExpr(
            name="result",
            span=expr.span,
            form_path=FORM_PATH,
        ),
        span=expr.span,
        form_path=FORM_PATH,
    )
    traversed = next(
        node
        for node in walk_expr(container)
        if isinstance(node, type(expr))
    )

    assert elaborated_clone.authored_callee_span == expected
    assert rewritten.authored_callee_span == expected
    assert traversed.authored_callee_span == expected
    assert copy(expr).authored_callee_span == expected
    assert deepcopy(expr).authored_callee_span == expected


def _write_module(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


def _typechecked_workflows(path: Path, *, workspace_root: Path):
    state, _ = _run_stage3_validation_pipeline(
        path,
        provider_externs=None,
        prompt_externs=None,
        imported_workflow_bundles=None,
        command_boundaries=None,
        validation_profile=Stage3ValidationProfile.FRONTEND_ONLY,
        workspace_root=workspace_root,
        lowering_route=normalize_lowering_route("legacy"),
    )
    assert state.typed_workflows
    return state.typed_workflows


def test_parametric_specialization_preserves_the_authored_procedure_head_span(
    tmp_path: Path,
) -> None:
    source = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defrecord Payload
    (value String))
  (defproc inspect
    :forall (T)
    ((value T))
    -> Payload
    :effects ()
    :lowering inline
    (record Payload
      :value "ok"))
  (defworkflow entry
    ((input Payload))
    -> Payload
    (inspect input)))
"""
    path = _write_module(tmp_path / "specialized_authored_call.orc", source)

    call = _typechecked_workflows(
        path,
        workspace_root=tmp_path,
    )[0].typed_body.expr

    assert isinstance(call, ProcedureCallExpr)
    assert call.callee_name.startswith("%parametric-call.inspect.")
    authored_callee_span = getattr(call, "authored_callee_span", None)
    assert authored_callee_span is not None
    start = authored_callee_span.start.offset
    end = authored_callee_span.end.offset
    assert source[start:end] == "inspect"


def test_macro_expanded_calls_do_not_claim_direct_authored_callee_provenance(
    tmp_path: Path,
) -> None:
    source = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defrecord Payload
    (value String))
  (defproc make-payload
    ()
    -> Payload
    :effects ()
    :lowering inline
    (record Payload
      :value "ok"))
  (defmacro generated-call (ignored)
    (make-payload))
  (defmacro pass-through (body)
    body)
  (defworkflow generated
    ((input Payload))
    -> Payload
    (generated-call input))
  (defworkflow expanded-argument
    ((input Payload))
    -> Payload
    (pass-through (make-payload))))
"""
    path = _write_module(tmp_path / "expanded_calls.orc", source)

    calls = tuple(
        workflow.typed_body.expr
        for workflow in _typechecked_workflows(path, workspace_root=tmp_path)
    )

    assert len(calls) == 2
    assert all(isinstance(call, ProcedureCallExpr) for call in calls)
    assert all(call.expansion_stack for call in calls)
    assert all(getattr(call, "authored_callee_span", None) is None for call in calls)


def test_generated_and_ambiguous_calls_default_to_no_callee_provenance() -> None:
    whole_form = _expression_syntax("(review review)").span
    same_spelled_argument = NameExpr(
        name="review",
        span=whole_form,
        form_path=FORM_PATH,
    )
    generated_procedure = ProcedureCallExpr(
        callee_name="review",
        args=(same_spelled_argument,),
        span=whole_form,
        form_path=FORM_PATH,
    )
    ambiguous_workflow = CallExpr(
        callee_name="review",
        bindings=(("review", same_spelled_argument),),
        span=whole_form,
        form_path=FORM_PATH,
    )

    assert getattr(generated_procedure, "authored_callee_span", None) is None
    assert getattr(ambiguous_workflow, "authored_callee_span", None) is None
    assert getattr(replace(generated_procedure, args=()), "authored_callee_span", None) is None
    assert getattr(copy(ambiguous_workflow), "authored_callee_span", None) is None


def test_wcc_reconstruction_never_promotes_whole_form_spans_to_callee_spans() -> None:
    whole_form = _expression_syntax("(call review :review review)").span
    metadata = WccIdentityFactory(owner_name="callee-provenance-test").value_metadata(
        role="call",
        type_ref=PrimitiveTypeRef(name="String"),
        source_span=whole_form,
        form_path=FORM_PATH,
    )
    reconstructed_workflow = _frontend_expr_from_wcc_loop_binding_value(
        WccPerform(
            metadata=metadata,
            perform_kind="workflow_call",
            target_name="review",
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name="String",
        )
    )
    reconstructed_procedure = _frontend_expr_from_wcc_loop_binding_value(
        WccCall(
            metadata=metadata,
            callee_name="review",
            specialized_callee_name="review",
            args=(),
        )
    )

    assert isinstance(reconstructed_workflow, CallExpr)
    assert isinstance(reconstructed_procedure, ProcedureCallExpr)
    assert reconstructed_workflow.span == whole_form
    assert reconstructed_procedure.span == whole_form
    assert getattr(reconstructed_workflow, "authored_callee_span", None) is None
    assert getattr(reconstructed_procedure, "authored_callee_span", None) is None
