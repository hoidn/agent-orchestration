"""One catalog, one answer: rule N8 of the numeric surface and its section 8, first row.

Contract: docs/design/workflow_lisp_numeric_surface.md, rule N8 and section 8; Task 6 of
docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md.

The applications are generated from `PURE_EXPR_OPERATOR_CATALOG`: every operator, every
arity its entry admits (up to three operands) and one arity on each side of that range,
and operand types from a fixed list. The set is the same on every run. For each
application within the arity range, the frontend check, the static typing of payloads
and the evaluator either accept it with the same result type or all refuse it; the
compiler's three lowering-time inferences of an operator's result type agree with the
frontend wherever the frontend accepts. Outside the arity range, the frontend and the
payload validation both refuse.
"""

from __future__ import annotations

from itertools import product
from types import SimpleNamespace

import pytest

from orchestrator.workflow.pure_expr import (
    PURE_EXPR_OPERATOR_CATALOG,
    PureExprEvaluationError,
    evaluate_pure_operator,
    validate_pure_expr_payload,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import NameExpr, PureOpExpr
from orchestrator.workflow_lisp.lowering import core as lowering_core
from orchestrator.workflow_lisp.lowering import pure_projection as lowering_pure_projection
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    OptionalTypeRef,
    PrimitiveTypeRef,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.wcc import elaborate as wcc_elaborate


_INT = PrimitiveTypeRef(name="Int")
# name: (frontend type, payload descriptor, sample value)
OPERAND_TYPES = {
    "Int": (_INT, {"kind": "primitive", "name": "Int"}, 3),
    "Float": (PrimitiveTypeRef(name="Float"), {"kind": "primitive", "name": "Float"}, 2.5),
    "Bool": (PrimitiveTypeRef(name="Bool"), {"kind": "primitive", "name": "Bool"}, True),
    "String": (PrimitiveTypeRef(name="String"), {"kind": "primitive", "name": "String"}, "s"),
    "Symbol": (PrimitiveTypeRef(name="Symbol"), {"kind": "primitive", "name": "Symbol"}, "sym"),
    "Optional[Int]": (
        OptionalTypeRef(name="Optional[Int]", item_type_ref=_INT),
        {"kind": "optional", "item": {"kind": "primitive", "name": "Int"}},
        3,
    ),
    "List[Int]": (
        ListTypeRef(name="List[Int]", item_type_ref=_INT),
        {"kind": "list", "item": {"kind": "primitive", "name": "Int"}},
        [3],
    ),
}
# `record-update` is written as a record update, never as an operator application.
OPERATORS = sorted(name for name in PURE_EXPR_OPERATOR_CATALOG if name != "record-update")
MAX_GENERATED_ARITY = 3
_POSITION = SourcePosition(path="agreement.orc", line=1, column=1, offset=0)
_SPAN = SourceSpan(start=_POSITION, end=_POSITION)
_FORM_PATH = ("workflow-lisp", "agreement")


def _arities(operator: str) -> tuple[list[int], list[int]]:
    """The arities inside the catalog's range, and one on each side of it."""

    spec = PURE_EXPR_OPERATOR_CATALOG[operator]
    top = min(spec.max_arity or MAX_GENERATED_ARITY, MAX_GENERATED_ARITY)
    inside = list(range(spec.min_arity, top + 1))
    outside = [arity for arity in (spec.min_arity - 1, (spec.max_arity or 0) + 1) if arity > 0 and arity not in inside]
    return inside, outside


def _applications(arity: int) -> list[tuple[str, ...]]:
    """Every operand-type tuple up to two operands; at three, the uniform ones and two mixed ones."""

    if arity <= 2:
        return list(product(OPERAND_TYPES, repeat=arity))
    return [(name,) * arity for name in OPERAND_TYPES] + [("Int", "Int", "Float"), ("Float", "Float", "Int")]


def _frontend(operator: str, operands: tuple[str, ...], target: str) -> str:
    """The type the frontend check assigns, or the code it refuses with."""

    names = [f"x{index}" for index in range(len(operands))]
    expr = PureOpExpr(
        operator=operator,
        args=tuple(NameExpr(name=name, span=_SPAN, form_path=_FORM_PATH) for name in names),
        span=_SPAN,
        form_path=_FORM_PATH,
    )
    type_env = FrontendTypeEnvironment(
        {name: OPERAND_TYPES[name][0] for name in ("Int", "Float", "Bool", "String", "Symbol")},
        target_dsl_version=target,
    )
    value_env = {name: OPERAND_TYPES[operand][0] for name, operand in zip(names, operands)}
    try:
        typed = typecheck_expression(expr, type_env=type_env, value_env=value_env)
    except LispFrontendCompileError as exc:
        return f"refused:{exc.diagnostics[0].code}"
    return typed.type_ref.name


def _descriptor_name(descriptor) -> str:
    if descriptor["kind"] == "primitive":
        return descriptor["name"]
    return f"{descriptor['kind'].capitalize()}[{_descriptor_name(descriptor['item'])}]"


def _static(operator: str, operands: tuple[str, ...]) -> str:
    """The type the static typing of a payload derives, or the code it refuses with.

    The payload declares a result type that nothing produces, so a well-typed payload is
    refused only for that mismatch, and the refusal names the type it derived.
    """

    payload = {
        "pure_expr_schema_version": 2,
        "result_type": {"kind": "primitive", "name": "NoOperatorProducesThis"},
        "bindings": {f"x{index}": {"type": OPERAND_TYPES[name][1]} for index, name in enumerate(operands)},
        "expr": {
            "kind": "op",
            "operator": operator,
            "args": [{"kind": "binding", "name": f"x{index}"} for index in range(len(operands))],
        },
    }
    try:
        validate_pure_expr_payload(payload)
    except PureExprEvaluationError as exc:
        if "observed" in exc.metadata:
            return _descriptor_name(exc.metadata["observed"])
        return f"refused:{exc.code}"
    raise AssertionError("a payload with an unproducible result type was accepted")


def _evaluator(operator: str, operands: tuple[str, ...]) -> str:
    """The type the evaluator produces on sample operands, or the code it refuses with."""

    try:
        result_type, _ = evaluate_pure_operator(
            operator, [(OPERAND_TYPES[name][1], OPERAND_TYPES[name][2]) for name in operands]
        )
    except PureExprEvaluationError as exc:
        return f"refused:{exc.code}"
    return _descriptor_name(result_type)


def _lowering_inferences(operator: str, operands: tuple[str, ...]) -> dict[str, str | None]:
    """The result type each lowering-time inference gives a well-typed application."""

    names = [f"x{index}" for index in range(len(operands))]
    expr = PureOpExpr(
        operator=operator,
        args=tuple(NameExpr(name=name, span=_SPAN, form_path=_FORM_PATH) for name in names),
        span=_SPAN,
        form_path=_FORM_PATH,
    )
    types = {name: OPERAND_TYPES[operand][0] for name, operand in zip(names, operands)}
    type_env = FrontendTypeEnvironment({}, target_dsl_version="2.34")
    context = SimpleNamespace(type_env=type_env, local_type_bindings=types)
    inferred = {
        "lowering/pure_projection": lowering_pure_projection._infer_expr_type(expr, context=context, lexical_types=types),
        "wcc/elaborate": wcc_elaborate._infer_expr_type(
            expr, type_env=type_env, value_env=types, workflow_return_types={}, procedure_return_types={}
        ),
        "lowering/core": lowering_core._resolve_pure_op_type(expr, context=context),
    }
    return {where: None if type_ref is None else type_ref.name for where, type_ref in inferred.items()}


@pytest.mark.parametrize("operator", OPERATORS)
def test_frontend_static_typing_and_evaluator_agree_on_every_generated_application(operator: str) -> None:
    inside, _ = _arities(operator)
    disagreements = []
    for operands in (operands for arity in inside for operands in _applications(arity)):
        frontend = _frontend(operator, operands, "2.34")
        static, evaluated = _static(operator, operands), _evaluator(operator, operands)
        accepted = [not answer.startswith("refused:") for answer in (frontend, static, evaluated)]
        if any(accepted) and (not all(accepted) or len({frontend, static, evaluated}) != 1):
            disagreements.append((operands, frontend, static, evaluated))

    assert disagreements == []


@pytest.mark.parametrize("operator", OPERATORS)
def test_lowering_inferences_agree_with_the_frontend_on_every_accepted_application(operator: str) -> None:
    inside, _ = _arities(operator)
    disagreements = []
    for operands in (operands for arity in inside for operands in _applications(arity)):
        frontend = _frontend(operator, operands, "2.34")
        if frontend.startswith("refused:"):
            continue
        for where, inferred in _lowering_inferences(operator, operands).items():
            # lowering/core answers only for the operators whose result it needs (None otherwise).
            if inferred is not None and inferred != frontend:
                disagreements.append((operands, where, inferred, frontend))

    assert disagreements == []


@pytest.mark.parametrize("operator", OPERATORS)
def test_frontend_and_payload_validation_refuse_every_arity_outside_the_catalog(operator: str) -> None:
    _, outside = _arities(operator)
    accepted = [
        (operands, frontend, static)
        for operands in (operands for arity in outside for operands in _applications(arity))
        for frontend, static in [(_frontend(operator, operands, "2.34"), _static(operator, operands))]
        if not (frontend.startswith("refused:") and static.startswith("refused:"))
    ]

    assert accepted == []


@pytest.mark.parametrize("operator", OPERATORS)
def test_what_the_233_frontend_accepts_the_runtime_accepts_with_the_same_type(operator: str) -> None:
    inside, _ = _arities(operator)
    disagreements = [
        (operands, frontend, static, evaluated)
        for operands in (operands for arity in inside for operands in _applications(arity))
        for frontend in [_frontend(operator, operands, "2.33")]
        if not frontend.startswith("refused:")
        for static, evaluated in [(_static(operator, operands), _evaluator(operator, operands))]
        if not frontend == static == evaluated
    ]

    assert disagreements == []


def test_the_generated_set_holds_well_typed_and_ill_typed_applications_of_every_operator() -> None:
    generated = [
        (operator, operands)
        for operator in OPERATORS
        for arity in _arities(operator)[0]
        for operands in _applications(arity)
    ]
    answers = {(operator, operands): _frontend(operator, operands, "2.34") for operator, operands in generated}

    assert len(answers) == len(generated)
    assert {operator for (operator, _), answer in answers.items() if not answer.startswith("refused:")} == set(OPERATORS)
    assert {operator for (operator, _), answer in answers.items() if answer.startswith("refused:")} == set(OPERATORS)
