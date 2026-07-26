from pathlib import Path

import pytest

import orchestrator.workflow_lisp.syntax as syntax
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    compile_stage1_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.result_guidance import (
    ResultGuidance,
    parse_return_spec,
    validate_result_guidance_example,
)
from orchestrator.workflow_lisp.syntax import (
    SyntaxNode,
    build_syntax_module,
    ensure_syntax_datum,
)
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    PrimitiveTypeRef,
    prelude_type_names_for_target,
    type_refs_compatible,
)
from orchestrator.workflow_lisp.typecheck import typecheck_expression


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
TYPE_FIXTURE = FIXTURES / "valid" / "type_definitions.orc"
FORM_PATH = ("workflow-lisp", "transportable-value-test")
VALUE_TYPE = PrimitiveTypeRef(name="Value")


def _module_source(target_dsl: str, *forms: str) -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target_dsl}")',
            *(f"  {form}" for form in forms),
            ")",
        )
    )


def _write_module(path: Path, target_dsl: str, *forms: str) -> Path:
    path.write_text(_module_source(target_dsl, *forms), encoding="utf-8")
    return path


def _expression(source: str) -> SyntaxNode:
    parsed = read_sexpr_text(
        source,
        source_path="inline_transportable_value.orc",
    )
    assert len(parsed.items) == 1
    datum = parsed.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_transportable_value.orc",
        form_path=FORM_PATH,
    )


def _type_environment() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(
        compile_stage1_module(TYPE_FIXTURE)
    )


def _diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError]) -> str:
    return excinfo.value.diagnostics[0].code


def test_value_type_is_installed_only_from_target_219() -> None:
    assert syntax.VALUE_MIN_TARGET_DSL_VERSION == "2.19"
    assert not syntax.target_dsl_supports_value("2.18")
    assert syntax.target_dsl_supports_value("2.19")
    assert "Value" not in prelude_type_names_for_target("2.18")
    assert "Value" in prelude_type_names_for_target("2.19")

    module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.19", "(defrecord Box (payload Value))"),
            source_path="target_219_value.orc",
        )
    )
    definition_module = elaborate_definition_module(
        _definition_only_syntax_module(module)
    )
    type_env = FrontendTypeEnvironment.from_module(definition_module)
    probe = _expression("true")

    assert type_env.resolve_type(
        "Value",
        span=probe.span,
        form_path=probe.form_path,
    ) == VALUE_TYPE


@pytest.mark.parametrize("type_name", ("Value", "Optional[Value]"))
def test_target_218_value_occurrence_reports_version_gate_at_authored_type(
    tmp_path: Path,
    type_name: str,
) -> None:
    path = _write_module(
        tmp_path / "target_218_value.orc",
        "2.18",
        f"(defworkflow probe ((payload {type_name})) -> Bool true)",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert _diagnostic_code(excinfo) == "value_type_requires_dsl_2_19"
    assert excinfo.value.diagnostics[0].span.start.line == 4


@pytest.mark.parametrize("target_dsl", ("2.18", "2.19"))
@pytest.mark.parametrize(
    "definition",
    (
        "(defrecord Value (payload Bool))",
        "(defunion Value (LEGACY))",
        "(defschema Value (payload Bool))",
    ),
)
def test_value_name_is_reserved_against_local_definitions_at_every_target(
    tmp_path: Path,
    target_dsl: str,
    definition: str,
) -> None:
    path = _write_module(
        tmp_path / f"local_value_shadow_{target_dsl}.orc",
        target_dsl,
        definition,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert _diagnostic_code(excinfo) == "prelude_type_name_reserved"


@pytest.mark.parametrize("target_dsl", ("2.18", "2.19"))
def test_value_name_is_reserved_against_imported_definitions_at_every_target(
    target_dsl: str,
) -> None:
    syntax_module = build_syntax_module(
        read_sexpr_text(
            _module_source(target_dsl),
            source_path=f"imported_value_shadow_{target_dsl}.orc",
        )
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        FrontendTypeEnvironment.from_module(
            module,
            imported_type_refs={
                "Value": PrimitiveTypeRef(name="legacy/Value"),
            },
        )

    assert _diagnostic_code(excinfo) == "prelude_type_name_reserved"


def test_value_type_compatibility_is_exact_in_both_directions() -> None:
    type_env = _type_environment()
    probe = _expression("true")
    narrower_types = tuple(
        type_env.resolve_type(
            type_name,
            span=probe.span,
            form_path=probe.form_path,
        )
        for type_name in (
            "Bool",
            "WorkReport",
            "ChecksResult",
            "ImplementationState",
            "Optional[Bool]",
            "List[Int]",
            "Map[String, Float]",
        )
    )

    assert type_refs_compatible(VALUE_TYPE, VALUE_TYPE)
    for narrower_type in narrower_types:
        assert not type_refs_compatible(VALUE_TYPE, narrower_type)
        assert not type_refs_compatible(narrower_type, VALUE_TYPE)


@pytest.mark.parametrize(
    "narrower_type_name",
    (
        "Bool",
        "WorkReport",
        "ChecksResult",
        "ImplementationState",
        "Optional[Bool]",
        "List[Int]",
        "Map[String, Float]",
    ),
)
@pytest.mark.parametrize(
    ("then_name", "else_name"),
    (("value", "narrower"), ("narrower", "value")),
)
def test_ordinary_typechecking_rejects_value_narrower_flows_in_both_directions(
    narrower_type_name: str,
    then_name: str,
    else_name: str,
) -> None:
    type_env = _type_environment()
    probe = _expression("true")
    narrower_type = type_env.resolve_type(
        narrower_type_name,
        span=probe.span,
        form_path=probe.form_path,
    )
    expression = elaborate_expression(
        _expression(f"(if true {then_name} {else_name})"),
        bound_names=frozenset({"value", "narrower"}),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expression,
            type_env=type_env,
            value_env={
                "value": VALUE_TYPE,
                "narrower": narrower_type,
            },
        )

    assert _diagnostic_code(excinfo) == "type_mismatch"


@pytest.mark.parametrize(
    ("source", "expected_code"),
    (
        ("(if value true false)", "if_condition_not_bool"),
        ("(match value ((ONLY item) item))", "match_subject_not_union"),
        ("value.field", "record_field_unknown"),
        (
            "(provider-bundle-path value :as Path.state-root)",
            "provider_bundle_path_source_invalid",
        ),
        ("(+ value 1)", "pure_expr_operand_type_mismatch"),
        ("(list/length value)", "pure_expr_operand_type_mismatch"),
    ),
)
def test_value_operations_keep_the_existing_operation_owned_diagnostic(
    source: str,
    expected_code: str,
) -> None:
    type_env = _type_environment()
    expression = elaborate_expression(
        _expression(source),
        bound_names=frozenset({"value"}),
        target_dsl_version="2.18",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expression,
            type_env=type_env,
            value_env={"value": VALUE_TYPE},
        )

    assert _diagnostic_code(excinfo) == expected_code


def test_value_guidance_allows_text_but_rejects_example_before_evaluation() -> None:
    raw_return = ensure_syntax_datum(
        _expression(
            '(result Value :description "Return one JSON value." '
            ':format-hint "Write it at the document root.")'
        ).datum,
        module_path="inline_transportable_value.orc",
        form_path=FORM_PATH,
    )
    return_spec = parse_return_spec(
        raw_return,
        form_path=FORM_PATH,
        label="return type",
    )

    assert return_spec.type_name == "Value"
    assert return_spec.guidance is not None
    assert return_spec.guidance.description == "Return one JSON value."
    assert (
        return_spec.guidance.format_hint
        == "Write it at the document root."
    )

    deliberately_nonconstant_example = _expression("missing-runtime-name")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate_result_guidance_example(
            ResultGuidance(example_expr=deliberately_nonconstant_example),
            expected_type=VALUE_TYPE,
            type_env=_type_environment(),
        )

    assert _diagnostic_code(excinfo) == "value_guidance_example_unsupported"
