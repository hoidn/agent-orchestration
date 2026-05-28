from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _imported_type_refs,
    _validate_definition_module,
    compile_stage1_entrypoint,
    compile_stage1_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.modules import build_import_scope
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURES / "modules" / "valid" / "alias_only"
PROC_REF_FIXTURE = FIXTURES / "valid" / "proc_ref_static_surface.orc"
SPAN = SourceSpan(
    start=SourcePosition(path="inline.orc", line=1, column=1, offset=0),
    end=SourcePosition(path="inline.orc", line=1, column=1, offset=0),
)
FORM_PATH = ("workflow-lisp", "collection-types-test")


def _compile_definition_module(path: Path):
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _build_imported_type_env() -> FrontendTypeEnvironment:
    linked = compile_stage1_entrypoint(
        MODULE_FIXTURES / "neurips" / "default_alias.orc",
        source_roots=(MODULE_FIXTURES,),
    )
    types_module = linked.compiled_modules_by_name["neurips/types"]
    types_env = FrontendTypeEnvironment.from_module(types_module)
    exported_type_refs_by_module = {
        "neurips/types": {
            "WorkReport": types_env.resolve_type(
                "WorkReport",
                span=types_module.span,
                form_path=("workflow-lisp", "defpath", "WorkReport"),
            ),
            "ImplementationSummary": types_env.resolve_type(
                "ImplementationSummary",
                span=types_module.span,
                form_path=("workflow-lisp", "defrecord", "ImplementationSummary"),
            ),
        }
    }
    entry_module = linked.compiled_modules_by_name["neurips/default_alias"]
    import_scope = build_import_scope(
        entry_module,
        export_surfaces_by_name=linked.graph.export_surfaces_by_name,
    )
    return FrontendTypeEnvironment.from_module(
        entry_module,
        import_scope=import_scope,
        imported_type_refs=_imported_type_refs(import_scope, exported_type_refs_by_module),
    )


def test_parse_type_expression_supports_nested_collection_types() -> None:
    from orchestrator.workflow_lisp.type_expressions import ListTypeExpr, MapTypeExpr, NamedTypeExpr, OptionalTypeExpr, parse_type_expression

    parsed = parse_type_expression(
        "Map[String, List[Optional[WorkReport]]]",
        span=SPAN,
        form_path=FORM_PATH,
    )

    assert isinstance(parsed, MapTypeExpr)
    assert parsed.key_type == NamedTypeExpr(name="String")
    assert isinstance(parsed.value_type, ListTypeExpr)
    assert parsed.value_type.item_type == OptionalTypeExpr(
        item_type=NamedTypeExpr(name="WorkReport")
    )


def test_parse_type_expression_rejects_invalid_generic_arity() -> None:
    from orchestrator.workflow_lisp.type_expressions import parse_type_expression

    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_type_expression(
            "Optional[String, Int]",
            span=SPAN,
            form_path=FORM_PATH,
        )

    _assert_diagnostic_code(excinfo, "type_expression_invalid")


def test_frontend_type_environment_resolves_collection_type_refs() -> None:
    from orchestrator.workflow_lisp.type_env import ListTypeRef, OptionalTypeRef

    type_env = FrontendTypeEnvironment.from_module(
        _compile_definition_module(FIXTURES / "valid" / "structured_results.orc")
    )

    resolved = type_env.resolve_type(
        "List[Optional[String]]",
        span=SPAN,
        form_path=FORM_PATH,
    )

    assert isinstance(resolved, ListTypeRef)
    assert isinstance(resolved.item_type_ref, OptionalTypeRef)
    assert resolved.item_type_ref.item_type_ref.name == "String"


def test_frontend_type_environment_resolves_module_qualified_inner_type_names() -> None:
    from orchestrator.workflow_lisp.type_env import ListTypeRef, PathTypeRef

    type_env = _build_imported_type_env()

    resolved = type_env.resolve_type(
        "List[types.WorkReport]",
        span=SPAN,
        form_path=FORM_PATH,
    )

    assert isinstance(resolved, ListTypeRef)
    assert isinstance(resolved.item_type_ref, PathTypeRef)
    assert resolved.item_type_ref.definition.under == "artifacts/work"


def test_frontend_type_environment_rejects_non_string_map_keys() -> None:
    type_env = FrontendTypeEnvironment.from_module(
        _compile_definition_module(FIXTURES / "valid" / "structured_results.orc")
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        type_env.resolve_type(
            "Map[Int, WorkReport]",
            span=SPAN,
            form_path=FORM_PATH,
        )

    _assert_diagnostic_code(excinfo, "collection_key_type_invalid")


def test_frontend_type_environment_rejects_workflow_refs_nested_inside_collections() -> None:
    type_env = FrontendTypeEnvironment.from_module(
        _compile_definition_module(FIXTURES / "valid" / "workflow_refs_same_file.orc")
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        type_env.resolve_type(
            "List[WorkflowRef[WorkflowInput -> WorkflowOutput]]",
            span=SPAN,
            form_path=FORM_PATH,
        )

    _assert_diagnostic_code(excinfo, "workflow_ref_runtime_transport_forbidden")


def test_frontend_type_environment_rejects_optional_workflow_refs_nested_inside_collections() -> None:
    type_env = FrontendTypeEnvironment.from_module(
        _compile_definition_module(FIXTURES / "valid" / "workflow_refs_same_file.orc")
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        type_env.resolve_type(
            "Optional[WorkflowRef[WorkflowInput -> WorkflowOutput]]",
            span=SPAN,
            form_path=FORM_PATH,
        )

    _assert_diagnostic_code(excinfo, "workflow_ref_runtime_transport_forbidden")


def test_parse_type_expression_supports_proc_ref_signatures() -> None:
    from orchestrator.workflow_lisp.type_expressions import (
        NamedTypeExpr,
        ProcRefTypeExpr,
        parse_type_expression,
    )

    unary = parse_type_expression(
        "ProcRef[WorkflowInput -> WorkflowOutput]",
        span=SPAN,
        form_path=FORM_PATH,
    )
    multi = parse_type_expression(
        "ProcRef[(WorkflowInput WorkflowOutput) -> String]",
        span=SPAN,
        form_path=FORM_PATH,
    )
    zero = parse_type_expression(
        "ProcRef[() -> String]",
        span=SPAN,
        form_path=FORM_PATH,
    )

    assert unary == ProcRefTypeExpr(
        param_types=(NamedTypeExpr(name="WorkflowInput"),),
        return_type=NamedTypeExpr(name="WorkflowOutput"),
    )
    assert multi == ProcRefTypeExpr(
        param_types=(
            NamedTypeExpr(name="WorkflowInput"),
            NamedTypeExpr(name="WorkflowOutput"),
        ),
        return_type=NamedTypeExpr(name="String"),
    )
    assert zero == ProcRefTypeExpr(
        param_types=(),
        return_type=NamedTypeExpr(name="String"),
    )


def test_frontend_type_environment_resolves_proc_ref_type_refs() -> None:
    from orchestrator.workflow_lisp.type_env import ProcRefTypeRef

    type_env = FrontendTypeEnvironment.from_module(_compile_definition_module(PROC_REF_FIXTURE))

    resolved = type_env.resolve_type(
        "ProcRef[(WorkflowInput WorkflowOutput) -> String]",
        span=SPAN,
        form_path=FORM_PATH,
    )
    zero = type_env.resolve_type(
        "ProcRef[() -> String]",
        span=SPAN,
        form_path=FORM_PATH,
    )

    assert isinstance(resolved, ProcRefTypeRef)
    assert [type_ref.name for type_ref in resolved.param_type_refs] == [
        "WorkflowInput",
        "WorkflowOutput",
    ]
    assert resolved.return_type_ref.name == "String"
    assert isinstance(zero, ProcRefTypeRef)
    assert zero.param_type_refs == ()
    assert zero.return_type_ref.name == "String"


@pytest.mark.parametrize(
    "type_name",
    [
        "List[ProcRef[WorkflowInput -> WorkflowOutput]]",
        "Optional[ProcRef[WorkflowInput -> WorkflowOutput]]",
        "Map[String, ProcRef[WorkflowInput -> WorkflowOutput]]",
    ],
)
def test_frontend_type_environment_rejects_proc_refs_nested_inside_collections(type_name: str) -> None:
    type_env = FrontendTypeEnvironment.from_module(_compile_definition_module(PROC_REF_FIXTURE))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        type_env.resolve_type(
            type_name,
            span=SPAN,
            form_path=FORM_PATH,
        )

    _assert_diagnostic_code(excinfo, "proc_ref_runtime_transport_forbidden")


def test_compile_stage1_rejects_collection_type_invalid_arity_fixture() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "collection_type_invalid_arity.orc")

    _assert_diagnostic_code(excinfo, "type_expression_invalid")


def test_compile_stage1_rejects_collection_map_key_invalid_fixture() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "collection_map_key_invalid.orc")

    _assert_diagnostic_code(excinfo, "collection_key_type_invalid")


def test_compile_stage3_rejects_workflow_ref_transport_nested_inside_collections(tmp_path: Path) -> None:
    path = tmp_path / "workflow_ref_in_collection.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord WorkflowInput",
                "    (value String))",
                "  (defrecord WorkflowOutput",
                "    (value String))",
                "  (defrecord InvalidEnvelope",
                "    (runners List[WorkflowRef[WorkflowInput -> WorkflowOutput]]))",
                "  (defworkflow helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput :value input.value)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "workflow_ref_runtime_transport_forbidden")


def test_compile_stage3_rejects_optional_workflow_ref_transport_nested_inside_collections(tmp_path: Path) -> None:
    path = tmp_path / "workflow_ref_in_optional_collection.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord WorkflowInput",
                "    (value String))",
                "  (defrecord WorkflowOutput",
                "    (value String))",
                "  (defrecord InvalidEnvelope",
                "    (runner Optional[WorkflowRef[WorkflowInput -> WorkflowOutput]]))",
                "  (defworkflow helper",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (record WorkflowOutput :value input.value)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "workflow_ref_runtime_transport_forbidden")
