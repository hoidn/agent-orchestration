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
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.workflow.pure_expr import (
    PURE_EXPR_OPERATOR_CATALOG,
    PureExprEvaluationError,
    PureOperatorSignature,
    evaluate_pure_expr,
    evaluate_pure_operator,
    validate_pure_expr_payload,
)
from orchestrator.workflow.evaluated.values import LexicalEnvironment, evaluate_closed_value
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import NameExpr, PureOpExpr
from orchestrator.workflow_lisp import result_guidance
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.definitions import PathDef
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    OptionalTypeRef,
    PathTypeRef,
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
# `print` accepts an operand of every type; only its arity refuses an application.
TOTAL_OPERATORS = {"print"}
MAX_GENERATED_ARITY = 3
_POSITION = SourcePosition(path="agreement.orc", line=1, column=1, offset=0)
_SPAN = SourceSpan(start=_POSITION, end=_POSITION)
_FORM_PATH = ("workflow-lisp", "agreement")

_BOOL = {"kind": "primitive", "name": "Bool"}
_INT_DESCRIPTOR = {"kind": "primitive", "name": "Int"}
_STRING = {"kind": "primitive", "name": "String"}
_SYMBOL = {"kind": "primitive", "name": "Symbol"}
_FLOAT_DESCRIPTOR = {"kind": "primitive", "name": "Float"}
_SELECTION = {"kind": "enum", "name": "Selection", "allowed": ["selected-item"]}
_PATH = {
    "kind": "path",
    "name": "Path.artifact-root",
    "under": "artifacts",
    "must_exist_target": False,
}
_SOURCE_TYPES = {
    "Bool": PrimitiveTypeRef(name="Bool"),
    "Int": PrimitiveTypeRef(name="Int"),
    "Float": PrimitiveTypeRef(name="Float"),
    "String": PrimitiveTypeRef(name="String"),
    "Symbol": PrimitiveTypeRef(name="Symbol"),
    "Selection": PrimitiveTypeRef(name="Selection", allowed_values=("selected-item",)),
    "Path": PathTypeRef(
        name="Path.artifact-root",
        definition=PathDef(
            name="Path.artifact-root",
            kind="relpath",
            under="artifacts",
            must_exist=False,
            span=_SPAN,
        ),
    ),
}

_FIXED_PRIMITIVE_SIGNATURES = (
    ("and", "Bool", "Bool"),
    ("or", "Bool", "Bool"),
    ("not", "Bool", "Bool"),
    ("string/empty?", "String", "Bool"),
    ("symbol/name", "Symbol", "String"),
)

_FIXED_PRIMITIVE_VALID_VECTORS = (
    ("and", (("Bool", True), ("Bool", True), ("Bool", False)), "Bool", False),
    ("or", (("Bool", False), ("Bool", False), ("Bool", True)), "Bool", True),
    ("not", (("Bool", True),), "Bool", False),
    ("not", (("Bool", False),), "Bool", True),
    ("string/empty?", (("String", ""),), "Bool", True),
    ("string/empty?", (("String", " \t"),), "Bool", False),
    ("string/empty?", (("String", "雪☂"),), "Bool", False),
    ("symbol/name", (("Symbol", "selected-item"),), "String", "selected-item"),
)


def _independent_descriptor(name: str):
    return {
        "Bool": _BOOL,
        "Int": _INT_DESCRIPTOR,
        "Float": _FLOAT_DESCRIPTOR,
        "String": _STRING,
        "Symbol": _SYMBOL,
        "Selection": _SELECTION,
        "Path": _PATH,
    }[name]


def _independent_payload(operator, operands, result_name: str):
    return {
        "pure_expr_schema_version": 1,
        "result_type": {"kind": "primitive", "name": result_name},
        "bindings": {},
        "expr": {
            "kind": "op",
            "operator": operator,
            "args": [
                {
                    "kind": "literal",
                    "type": _independent_descriptor(type_name),
                    "value": value,
                }
                for type_name, value in operands
            ],
        },
    }


def _source_result(operator: str, operands: tuple[str, ...]) -> str:
    names = [f"x{index}" for index in range(len(operands))]
    expr = PureOpExpr(
        operator=operator,
        args=tuple(NameExpr(name=name, span=_SPAN, form_path=_FORM_PATH) for name in names),
        span=_SPAN,
        form_path=_FORM_PATH,
    )
    try:
        typed = typecheck_expression(
            expr,
            type_env=FrontendTypeEnvironment({}, target_dsl_version="2.35"),
            value_env={name: _SOURCE_TYPES[type_name] for name, type_name in zip(names, operands)},
        )
    except LispFrontendCompileError as exc:
        return f"refused:{exc.diagnostics[0].code}"
    return typed.type_ref.name


@pytest.mark.parametrize(("operator", "operand", "result"), _FIXED_PRIMITIVE_SIGNATURES)
def test_catalog_primitive_operators_have_independent_signatures(
    operator: str,
    operand: str,
    result: str,
) -> None:
    assert PURE_EXPR_OPERATOR_CATALOG[operator].signatures == (
        PureOperatorSignature(operand=operand, result=result),
    )


@pytest.mark.parametrize(
    ("operator", "operands", "result_name", "expected_value"),
    _FIXED_PRIMITIVE_VALID_VECTORS,
)
def test_catalog_primitive_valid_vectors_match_source_payload_and_runtime(
    operator: str,
    operands: tuple[tuple[str, object], ...],
    result_name: str,
    expected_value: object,
) -> None:
    assert _source_result(operator, tuple(type_name for type_name, _ in operands)) == result_name

    payload = _independent_payload(operator, operands, result_name)
    validate_pure_expr_payload(payload)
    assert evaluate_pure_expr(payload) == expected_value

    observed_type, observed_value = evaluate_pure_operator(
        operator,
        [(_independent_descriptor(type_name), value) for type_name, value in operands],
    )
    assert observed_type == {"kind": "primitive", "name": result_name}
    assert observed_value == expected_value


@pytest.mark.parametrize(
    ("operator", "operands", "result_name", "observed_index", "expected_operand"),
    (
        ("and", (("Bool", True), ("Int", 7), ("Float", 2.5)), "Bool", 1, "Bool"),
        ("or", (("Bool", False), ("Int", 0)), "Bool", 1, "Bool"),
        ("not", (("Int", 1),), "Bool", 0, "Bool"),
        ("string/empty?", (("Symbol", "selected-item"),), "Bool", 0, "String"),
        ("string/empty?", (("Path", "artifacts/item.txt"),), "Bool", 0, "String"),
        ("symbol/name", (("String", "selected-item"),), "String", 0, "Symbol"),
        ("symbol/name", (("Selection", "selected-item"),), "String", 0, "Symbol"),
        ("symbol/name", (("Path", "artifacts/item.txt"),), "String", 0, "Symbol"),
    ),
)
def test_catalog_primitive_invalid_vectors_preserve_first_refusal_metadata(
    operator: str,
    operands: tuple[tuple[str, object], ...],
    result_name: str,
    observed_index: int,
    expected_operand: str,
) -> None:
    type_names = tuple(type_name for type_name, _ in operands)
    assert _source_result(operator, type_names) == "refused:pure_expr_operand_type_mismatch"

    observed_type = _independent_descriptor(type_names[observed_index])
    expected_message = f"operator `{operator}` requires {expected_operand} operands"
    payload = _independent_payload(operator, operands, result_name)
    with pytest.raises(PureExprEvaluationError) as payload_error:
        validate_pure_expr_payload(payload)
    assert payload_error.value.code == "pure_expr_operand_type_mismatch"
    assert str(payload_error.value) == expected_message
    assert payload_error.value.metadata == {"observed_type": observed_type}

    with pytest.raises(PureExprEvaluationError) as runtime_error:
        evaluate_pure_operator(
            operator,
            [(_independent_descriptor(type_name), value) for type_name, value in operands],
        )
    assert runtime_error.value.code == "pure_expr_operand_type_mismatch"
    assert str(runtime_error.value) == expected_message
    assert runtime_error.value.metadata == {"observed_type": observed_type}


@pytest.mark.parametrize(
    ("operator", "operands", "result_name"),
    (
        ("and", (("Bool", True),), "Bool"),
        ("not", (("Bool", True), ("Bool", False)), "Bool"),
        ("string/empty?", (("String", ""), ("String", "x")), "Bool"),
        ("symbol/name", (), "String"),
    ),
)
def test_catalog_primitive_arity_still_has_source_and_payload_gates(
    operator: str,
    operands: tuple[tuple[str, object], ...],
    result_name: str,
) -> None:
    assert _source_result(operator, tuple(type_name for type_name, _ in operands)) == (
        "refused:pure_expr_operand_type_mismatch"
    )
    with pytest.raises(PureExprEvaluationError) as excinfo:
        validate_pure_expr_payload(_independent_payload(operator, operands, result_name))
    assert excinfo.value.code == "pure_expr_payload_invalid"


def test_public_source_compiles_the_primitive_contract(tmp_path: Path) -> None:
    source_path = tmp_path / "primitives.orc"
    source_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule primitives)
  (export Result run)
  (defrecord Result
    (and_result Bool)
    (or_result Bool)
    (not_result Bool)
    (empty_result Bool)
    (name_result String))
  (defworkflow run ((flag Bool) (text String) (selection Symbol)) -> Result
    (record Result
      :and_result (and flag true true)
      :or_result (or false flag false)
      :not_result (not false)
      :empty_result (string/empty? "")
      :name_result (symbol/name selection))))
''',
        encoding="utf-8",
    )
    compiled = compile_stage3_entrypoint(
        source_path,
        source_roots=(tmp_path,),
        entry_workflow="run",
        workspace_root=tmp_path,
    )
    assert compiled.entry_result.typed_program is not None


def test_dependent_runtime_descriptors_keep_nested_and_nominal_matching() -> None:
    path_a = {
        "kind": "path",
        "name": "types::Path.repo",
        "under": "artifacts",
        "must_exist_target": False,
    }
    path_b = {
        "kind": "path",
        "name": "consumer::Path.repo",
        "under": "artifacts",
        "must_exist_target": False,
    }
    optional_path_a = {"kind": "optional", "item": path_a}

    observed_type, observed_value = evaluate_pure_operator(
        "or-else",
        [(optional_path_a, None), (path_b, "artifacts/next")],
    )
    assert observed_type == path_a
    assert observed_value == "artifacts/next"

    item_type = {
        "kind": "optional",
        "item": {"kind": "enum", "name": "Direction", "allowed": ["north", "south"]},
    }
    list_type = {"kind": "list", "item": item_type}
    source = [None, "north"]
    observed_type, observed_value = evaluate_pure_operator(
        "list/append",
        [(list_type, source), (item_type, "south")],
    )
    assert observed_type == list_type
    assert observed_value == [None, "north", "south"]
    assert source == [None, "north"]
    assert observed_value is not source


def test_dependent_runtime_refusals_keep_path_order_and_descriptor_metadata() -> None:
    path_type = {
        "kind": "path",
        "name": "Path.artifact-root",
        "under": "artifacts",
        "must_exist_target": False,
    }
    int_type = {"kind": "primitive", "name": "Int"}
    string_type = {"kind": "primitive", "name": "String"}

    with pytest.raises(PureExprEvaluationError) as concat_error:
        evaluate_pure_operator(
            "string/concat",
            [(int_type, 7), (path_type, "artifacts/item")],
        )
    assert concat_error.value.code == "pure_expr_operand_type_mismatch"
    assert str(concat_error.value) == "operator `string/concat` requires String operands"
    assert concat_error.value.metadata == {"observed_type": int_type}
    assert _source_result("string/concat", ("Int", "Path")) == (
        "refused:pure_expr_path_string_concat_forbidden"
    )

    list_type = {"kind": "list", "item": int_type}
    with pytest.raises(PureExprEvaluationError) as append_error:
        evaluate_pure_operator(
            "list/append",
            [(list_type, [1]), (string_type, "2")],
        )
    assert append_error.value.code == "pure_expr_operand_type_mismatch"
    assert str(append_error.value) == (
        "operator `list/append` item type must match the list element type"
    )
    assert append_error.value.metadata == {
        "item_type": string_type,
        "element_type": int_type,
    }


@pytest.mark.parametrize("item", (True, "8"), ids=("bool", "numeric-string"))
def test_list_runtime_result_coercion_keeps_operator_context(item: object) -> None:
    list_type = {
        "kind": "list",
        "item": {"kind": "primitive", "name": "Int"},
    }
    with pytest.raises(PureExprEvaluationError) as excinfo:
        evaluate_pure_operator("list/rest", [(list_type, [1, item])])
    assert excinfo.value.code == "pure_expr_operand_type_mismatch"
    assert str(excinfo.value) == "list/rest result item must be Int"
    assert excinfo.value.metadata == {}


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


def _retained_inferences(operator: str, operands: tuple[str, ...]) -> dict[str, str | None]:
    """The result type each lowering-time inference gives a well-typed application."""

    names = [f"x{index}" for index in range(len(operands))]
    expr = PureOpExpr(
        operator=operator,
        args=tuple(NameExpr(name=name, span=_SPAN, form_path=_FORM_PATH) for name in names),
        span=_SPAN,
        form_path=_FORM_PATH,
    )
    types = {name: OPERAND_TYPES[operand][0] for name, operand in zip(names, operands)}
    type_env = FrontendTypeEnvironment({}, target_dsl_version="2.35")
    inferred = {
        "result_guidance": result_guidance._infer_expr_type(expr, type_env=type_env, source_read_trace=None, lexical_types=types),
        "wcc/elaborate": wcc_elaborate._infer_expr_type(
            expr, type_env=type_env, value_env=types, workflow_return_types={}, procedure_return_types={}
        ),
    }
    return {where: None if type_ref is None else type_ref.name for where, type_ref in inferred.items()}


@pytest.mark.parametrize("operator", OPERATORS)
def test_frontend_static_typing_and_evaluator_agree_on_every_generated_application(operator: str) -> None:
    inside, _ = _arities(operator)
    disagreements = []
    for operands in (operands for arity in inside for operands in _applications(arity)):
        frontend = _frontend(operator, operands, "2.35")
        static, evaluated = _static(operator, operands), _evaluator(operator, operands)
        accepted = [not answer.startswith("refused:") for answer in (frontend, static, evaluated)]
        if any(accepted) and (not all(accepted) or len({frontend, static, evaluated}) != 1):
            disagreements.append((operands, frontend, static, evaluated))

    assert disagreements == []


@pytest.mark.parametrize("operator", OPERATORS)
def test_retained_inferences_agree_with_the_frontend_on_every_accepted_application(operator: str) -> None:
    inside, _ = _arities(operator)
    disagreements = []
    for operands in (operands for arity in inside for operands in _applications(arity)):
        frontend = _frontend(operator, operands, "2.35")
        if frontend.startswith("refused:"):
            continue
        for where, inferred in _retained_inferences(operator, operands).items():
            if inferred is not None and inferred != frontend:
                disagreements.append((operands, where, inferred, frontend))

    assert disagreements == []


@pytest.mark.parametrize("operator", OPERATORS)
def test_frontend_and_payload_validation_refuse_every_arity_outside_the_catalog(operator: str) -> None:
    _, outside = _arities(operator)
    accepted = [
        (operands, frontend, static)
        for operands in (operands for arity in outside for operands in _applications(arity))
        for frontend, static in [(_frontend(operator, operands, "2.35"), _static(operator, operands))]
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
def test_what_the_current_frontend_accepts_the_runtime_accepts_with_the_same_type(operator: str) -> None:
    inside, _ = _arities(operator)
    disagreements = [
        (operands, frontend, static, evaluated)
        for operands in (operands for arity in inside for operands in _applications(arity))
        for frontend in [_frontend(operator, operands, "2.35")]
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
    answers = {(operator, operands): _frontend(operator, operands, "2.35") for operator, operands in generated}

    assert len(answers) == len(generated)
    assert {operator for (operator, _), answer in answers.items() if not answer.startswith("refused:")} == set(OPERATORS)
    assert {operator for (operator, _), answer in answers.items() if answer.startswith("refused:")} == set(OPERATORS) - TOTAL_OPERATORS


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

    from orchestrator.contracts.closed_program.names import canonical_callee_name_from_key
    from orchestrator.contracts.closed_program.program import ClosedProgram, ClosedProgramInvalid, program_digest
    from orchestrator.contracts.closed_program.sites import assign_sites
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
