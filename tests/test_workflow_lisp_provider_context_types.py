import pytest

from orchestrator.workflow_lisp.definitions import RecordDef, RecordField, WorkflowLispModule
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import FieldAccessExpr, NameExpr
from orchestrator.workflow_lisp.normalized_type_descriptor import (
    compiler_normalized_type_descriptor,
)
from orchestrator.workflow_lisp.procedure_typecheck import (
    _infer_parametric_type_bindings,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    RecordTypeRef,
    render_type_ref,
    substitute_type_params,
)
from orchestrator.workflow_lisp.type_expressions import parse_type_expression
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.providers.portable_context import PORTABLE_CONTEXT_V1_DESCRIPTOR


SPAN = SourceSpan(
    start=SourcePosition(path="context-types.orc", line=1, column=1, offset=0),
    end=SourcePosition(path="context-types.orc", line=1, column=1, offset=0),
)
FORM_PATH = ("workflow-lisp", "context-types-test")


def _type_env(
    target: str,
    *,
    definitions: tuple[RecordDef, ...] = (),
    imported_type_refs: dict[str, object] | None = None,
) -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version=target,
            module_name=None,
            imports=(),
            exports=(),
            definitions=definitions,
            span=SPAN,
        ),
        imported_type_refs=imported_type_refs,
    )


def _record_type(name: str) -> RecordTypeRef:
    definition = RecordDef(
        name=name,
        fields=(RecordField(name="value", type_name="String", span=SPAN),),
        span=SPAN,
    )
    return RecordTypeRef(
        name=name,
        definition=definition,
        field_types={"value": _resolve(_type_env("2.30"), "String")},
    )


def _resolve(
    type_env: FrontendTypeEnvironment,
    name: str,
    *,
    params: frozenset[str] = frozenset(),
):
    return type_env.resolve_type(
        name,
        span=SPAN,
        form_path=FORM_PATH,
        local_type_params=params,
    )


def test_contextual_type_round_trips_as_an_ordinary_recursive_descriptor() -> None:
    type_env = _type_env("2.31")

    contextual = _resolve(type_env, "Contextual[Int]")

    assert isinstance(contextual, RecordTypeRef)
    assert contextual.name == "Contextual[Int]"
    assert render_type_ref(contextual) == "Contextual[Int]"
    assert _resolve(type_env, render_type_ref(contextual)) == contextual
    assert contextual.field_types["result"].name == "Int"
    assert contextual.field_types["context"].name == "Context"
    descriptor = compiler_normalized_type_descriptor(contextual, type_env=type_env)
    assert descriptor["kind"] == "record"
    assert descriptor["name"] == "Contextual[Int]"
    assert descriptor["fields"][1]["type"]["fields"][1]["type"]["kind"] == "list"
    assert descriptor["fields"][1]["type"]["fields"][1]["type"]["item"]["kind"] == "union"
    assert descriptor["fields"][1]["type"] == PORTABLE_CONTEXT_V1_DESCRIPTOR


def test_context_file_change_fixed_type_matches_the_portable_descriptor() -> None:
    type_env = _type_env("2.31")

    change = _resolve(type_env, "ContextFileChange")
    origin = _resolve(type_env, "ContextOrigin")
    event = _resolve(type_env, "ContextEvent")
    descriptor = compiler_normalized_type_descriptor(event, type_env=type_env)
    file_change = next(
        variant for variant in descriptor["variants"] if variant["name"] == "FILE_CHANGE"
    )

    assert tuple(change.field_types) == ("path", "kind")
    assert file_change["fields"] == [
        {
            "name": "origin",
            "type": compiler_normalized_type_descriptor(origin, type_env=type_env),
        },
        {"name": "sequence", "type": {"kind": "primitive", "name": "Int"}},
        {"name": "item_id", "type": {"kind": "primitive", "name": "String"}},
        {"name": "status", "type": {"kind": "primitive", "name": "String"}},
        {
            "name": "changes",
            "type": {
                "kind": "list",
                "item": {
                    **compiler_normalized_type_descriptor(change, type_env=type_env),
                },
            },
        },
    ]


def test_context_is_a_whole_ordinary_value_for_pure_field_access() -> None:
    type_env = _type_env("2.31")
    context = _resolve(type_env, "Context")
    access = FieldAccessExpr(
        base=NameExpr(name="context", span=SPAN, form_path=FORM_PATH),
        fields=("schema",),
        span=SPAN,
        form_path=FORM_PATH,
    )

    typed = typecheck_expression(
        access,
        type_env=type_env,
        value_env={"context": context},
    )

    assert typed.type_ref.name == "String"


def test_contextual_substitution_rebuilds_its_concrete_definition() -> None:
    type_env = _type_env("2.31")
    generic = _resolve(type_env, "Contextual[T]", params=frozenset({"T"}))

    substituted = substitute_type_params(generic, {"T": _resolve(type_env, "Int")})

    assert substituted == _resolve(type_env, "Contextual[Int]")
    assert substituted.name == "Contextual[Int]"
    assert substituted.definition.name == "Contextual[Int]"


def test_wrapper_only_argument_infers_a_generic_parameter_from_contextual_result() -> None:
    type_env = _type_env("2.31")
    bindings = {}

    _infer_parametric_type_bindings(
        _resolve(type_env, "Contextual[T]", params=frozenset({"T"})),
        _resolve(type_env, "Contextual[Int]"),
        bindings=bindings,
        raise_error=lambda *args, **kwargs: pytest.fail(str(args)),
        span=SPAN,
        form_path=FORM_PATH,
    )

    assert bindings == {"T": _resolve(type_env, "Int")}


def test_context_type_names_remain_unavailable_before_the_unadmitted_target() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _resolve(_type_env("2.30"), "Context")

    assert excinfo.value.diagnostics[0].code == "type_unknown"


@pytest.mark.parametrize("type_name", ("Contextual[Int]", "List[Contextual[Int]]"))
def test_contextual_is_rejected_before_231_even_when_old_source_defines_context(
    type_name: str,
) -> None:
    type_env = _type_env(
        "2.30",
        definitions=(
            RecordDef(
                name="Context",
                fields=(RecordField(name="value", type_name="String", span=SPAN),),
                span=SPAN,
            ),
        ),
    )
    assert _resolve(type_env, "Context").definition.span.start.path == "context-types.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _resolve(type_env, type_name)

    assert excinfo.value.diagnostics[0].code == "contextual_type_requires_dsl_2_31"


def test_contextual_inference_preserves_wrapper_result_constraints() -> None:
    type_env = _type_env("2.31")
    bindings = {}
    expected = _resolve(type_env, "Contextual[T]", params=frozenset({"T"}))

    _infer_parametric_type_bindings(
        expected,
        _resolve(type_env, "Contextual[Int]"),
        bindings=bindings,
        raise_error=lambda *args, **kwargs: pytest.fail(str(args)),
        span=SPAN,
        form_path=FORM_PATH,
    )
    with pytest.raises(pytest.fail.Exception):
        _infer_parametric_type_bindings(
            expected,
            _resolve(type_env, "Contextual[String]"),
            bindings=bindings,
            raise_error=lambda *args, **kwargs: pytest.fail(str(args)),
            span=SPAN,
            form_path=FORM_PATH,
        )


def test_contextual_rejects_the_wrong_concrete_result_type() -> None:
    type_env = _type_env("2.31")

    with pytest.raises(pytest.fail.Exception):
        _infer_parametric_type_bindings(
            _resolve(type_env, "Contextual[Int]"),
            _resolve(type_env, "Contextual[String]"),
            bindings={},
            raise_error=lambda *args, **kwargs: pytest.fail(str(args)),
            span=SPAN,
            form_path=FORM_PATH,
        )


def test_non_contextual_records_keep_nominal_inference_compatibility() -> None:
    expected = _record_type("Left")
    actual = _record_type("Right")

    with pytest.raises(pytest.fail.Exception):
        _infer_parametric_type_bindings(
            expected,
            actual,
            bindings={},
            raise_error=lambda *args, **kwargs: pytest.fail(str(args)),
            span=SPAN,
            form_path=FORM_PATH,
        )


def test_imported_contextual_rebuilds_its_canonical_name_and_definition() -> None:
    from orchestrator.workflow_lisp.compiler import _canonicalize_nested_imported_type_ref

    item = RecordDef(
        name="Item",
        fields=(RecordField(name="value", type_name="Int", span=SPAN),),
        span=SPAN,
    )
    library_env = _type_env("2.31", definitions=(item,))
    wrapped = _resolve(library_env, "Contextual[Item]")
    canonical_item = _canonicalize_nested_imported_type_ref(
        _resolve(library_env, "Item"),
        module_name="library",
        exported_names=frozenset({"Item"}),
    )
    imported = _canonicalize_nested_imported_type_ref(
        wrapped,
        module_name="library",
        exported_names=frozenset({"Item"}),
    )
    consumer_env = _type_env(
        "2.31",
        imported_type_refs={"library::Item": canonical_item},
    )

    assert imported.name == "Contextual[library::Item]"
    assert imported.definition.name == "Contextual[library::Item]"
    assert render_type_ref(imported) == "Contextual[library::Item]"
    assert _resolve(consumer_env, render_type_ref(imported)) == imported


@pytest.mark.parametrize("type_name", ("Contextual[,Int]", "Contextual[Int,]", "Contextual[Int,,]"))
def test_contextual_rejects_empty_generic_argument_positions(type_name: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_type_expression(type_name, span=SPAN, form_path=FORM_PATH)

    assert excinfo.value.diagnostics[0].code == "type_expression_invalid"
