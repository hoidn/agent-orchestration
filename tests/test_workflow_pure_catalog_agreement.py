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
payload validation both refuse. The closed-value evaluator is compared with the runtime
catalog over the same generated operator applications.
"""

from __future__ import annotations

from importlib import import_module
from itertools import product
from types import SimpleNamespace

import pytest

from orchestrator.workflow.pure_expr import (
    PURE_EXPR_OPERATOR_CATALOG,
    PureExprEvaluationError,
    evaluate_pure_expr,
    evaluate_pure_operator,
    validate_pure_expr_payload,
)
from orchestrator.workflow.evaluated.values import LexicalEnvironment, evaluate_closed_value
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


def _closed_value_catalog_application(operator, operands):
    typed_operands = [
        (OPERAND_TYPES[name][1], OPERAND_TYPES[name][2]) for name in operands
    ]
    try:
        expected_type, expected_value = evaluate_pure_operator(operator, typed_operands)
    except PureExprEvaluationError as exc:
        expected = f"refused:{exc.code}"
        result_type = {"kind": "primitive", "name": "String"}
    else:
        expected = (_descriptor_name(expected_type), expected_value)
        result_type = expected_type

    payload = {
        "pure_expr_schema_version": 2,
        "result_type": result_type,
        "bindings": {
            f"a{index}": {"type": descriptor}
            for index, (descriptor, _) in enumerate(typed_operands)
        },
        "expr": {
            "kind": "op",
            "operator": operator,
            "args": [
                {"kind": "binding", "name": f"a{index}"}
                for index in range(len(typed_operands))
            ],
        },
    }
    closed = {
        "k": "op",
        "payload": payload,
        "args": [
            {"k": "lit", "v": value, "type": descriptor}
            for descriptor, value in typed_operands
        ],
    }
    try:
        evaluated = evaluate_closed_value(closed, LexicalEnvironment())
    except PureExprEvaluationError as exc:
        observed = f"refused:{exc.code}"
    else:
        observed = (_descriptor_name(evaluated.descriptor), evaluated.json_value())
    return expected, observed


@pytest.mark.parametrize("operator", OPERATORS)
def test_closed_value_evaluator_matches_catalog_for_generated_applications(operator: str) -> None:
    inside, _ = _arities(operator)
    disagreements = []
    for operands in (case for arity in inside for case in _applications(arity)):
        expected, observed = _closed_value_catalog_application(operator, operands)
        if observed != expected:
            disagreements.append((operands, expected, observed))

    assert disagreements == []


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


def test_catalog_rejects_wrong_boolean_integer_bindings_and_non_finite_results() -> None:
    for descriptor, observed in (
        ({"kind": "primitive", "name": "Bool"}, 1),
        ({"kind": "primitive", "name": "Int"}, True),
    ):
        payload = {
            "pure_expr_schema_version": 2,
            "result_type": descriptor,
            "bindings": {"x": {"type": descriptor}},
            "expr": {"kind": "binding", "name": "x"},
        }
        with pytest.raises(PureExprEvaluationError):
            evaluate_pure_expr(payload, resolved_bindings={"x": observed})

    with pytest.raises(PureExprEvaluationError) as excinfo:
        evaluate_pure_operator(
            "*",
            [
                ({"kind": "primitive", "name": "Float"}, 1e308),
                ({"kind": "primitive", "name": "Float"}, 1e308),
            ],
        )
    assert excinfo.value.code == "pure_expr_float_not_finite"


def test_evaluated_value_coercion_uses_catalog_and_rejects_non_finite_float() -> None:
    coerce = getattr(import_module("orchestrator.workflow.pure_expr"), "coerce_pure_value")

    with pytest.raises(PureExprEvaluationError) as excinfo:
        coerce(float("inf"), {"kind": "primitive", "name": "Float"})

    assert excinfo.value.code == "pure_expr_float_not_finite"


@pytest.mark.parametrize(
    ("descriptor", "value"),
    [
        (
            {"kind": "path", "name": "sample::Artifact", "under": "artifacts", "must_exist_target": True},
            "artifacts/run/report.md",
        ),
        (
            {"kind": "record", "name": "sample::Row", "fields": [
                {"name": "count", "type": {"kind": "primitive", "name": "Int"}},
                {"name": "path", "type": {"kind": "path", "name": "sample::Artifact", "under": "artifacts", "must_exist_target": True}},
            ]},
            {"count": 4, "path": "artifacts/run/report.md"},
        ),
        (
            {"kind": "list", "item": {"kind": "primitive", "name": "Int"}},
            [1, 2],
        ),
        (
            {
                "kind": "map",
                "key": {"kind": "primitive", "name": "String"},
                "value": {"kind": "primitive", "name": "Int"},
            },
            {"count": 2},
        ),
        (
            {"kind": "union", "name": "sample::Choice", "variants": [
                {"name": "Ready", "fields": [{"name": "path", "type": {"kind": "path", "name": "sample::Artifact", "under": "artifacts", "must_exist_target": True}}]},
                {"name": "Skipped", "fields": []},
            ]},
            {"variant": "Ready", "path": "artifacts/run/report.md"},
        ),
        (
            {"kind": "optional", "item": {"kind": "primitive", "name": "String"}},
            None,
        ),
    ],
)
def test_catalog_coerces_closed_transport_shapes(
    descriptor: dict, value: object
) -> None:
    payload = {
        "pure_expr_schema_version": 2,
        "result_type": descriptor,
        "bindings": {"x": {"type": descriptor}},
        "expr": {"kind": "binding", "name": "x"},
    }

    assert evaluate_pure_expr(payload, resolved_bindings={"x": value}) == value


@pytest.mark.parametrize("kind", ["list", "record", "union", "op", "record_update"])
@pytest.mark.parametrize("malformed", ["missing", {}, ""])
def test_readback_refuses_key_operator_payload_invalid_containers(kind, malformed) -> None:
    from copy import deepcopy

    from orchestrator.workflow_lisp.closed.names import canonical_callee_name_from_key
    from orchestrator.workflow_lisp.closed.program import (
        ClosedProgram, ClosedProgramInvalid, program_digest,
    )
    from orchestrator.workflow_lisp.closed.sites import assign_sites
    from tests.test_workflow_lisp_closed_program_check import _halt, _lit, _tree

    INT = {"kind": "primitive", "name": "Int"}
    record = {"kind": "record", "name": "sample::Empty", "fields": []}
    union = {"kind": "union", "name": "sample::Choice", "variants": [
        {"name": "Ready", "fields": []},
    ]}
    updated = {"kind": "record", "name": "sample::Count", "fields": [
        {"name": "count", "type": INT},
    ]}
    literal = {"kind": "literal", "type": INT, "value": 1}
    fields = [{"name": "count", "value": literal}]
    descriptor = {
        "list": INT, "record": record, "union": union, "op": INT,
        "record_update": updated,
    }[kind]
    sequence_node = {
        "list": {"kind": "list", "element_type": INT, "items": []},
        "record": {"kind": "record", "type": record, "fields": []},
        "union": {"kind": "union", "type": union, "variant": "Ready", "fields": []},
        "op": {"kind": "op", "operator": "+", "args": [literal, literal]},
        "record_update": {
            "kind": "record_update", "record_type": updated, "fields": fields,
            "base": {"kind": "record", "type": updated, "fields": fields},
        },
    }[kind]
    expression = (
        {"kind": "op", "operator": "list/length", "args": [sequence_node]}
        if kind == "list" else sequence_node
    )
    payload = {
        "pure_expr_schema_version": 2, "result_type": descriptor,
        "bindings": {}, "expr": expression,
    }
    closed = {"k": "op", "payload": payload, "args": []}
    key = [
        "sample", "procedure", "f", [], [], [], [["value", descriptor, closed]], [],
        {"params": [], "result": deepcopy(INT)},
    ]

    def artifact():
        name = canonical_callee_name_from_key(key)
        tree = _tree(_halt(_lit(0)))
        tree["types"] = {row["name"]: row for row in (record, union, updated)}
        tree["definitions"] = {
            name: {"key": key, "params": [], "result": deepcopy(INT), "body": _halt(_lit(0))}
        }
        tree["sites"] = [list(row) for row in assign_sites(tree)]
        return ClosedProgram(
            tree=tree, sites=tuple(tuple(row) for row in tree["sites"]),
            digest=program_digest(tree),
        ).artifact()

    assert ClosedProgram.from_artifact(artifact()).tree["definitions"]
    field = {"list": "items", "op": "args"}.get(kind, "fields")
    if malformed == "missing":
        del sequence_node[field]
    else:
        sequence_node[field] = malformed

    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(artifact())
    assert excinfo.value.rule == "definition_key"
