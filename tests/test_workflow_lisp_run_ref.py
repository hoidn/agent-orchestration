from dataclasses import FrozenInstanceError, replace
from typing import get_args

import pytest

from orchestrator.workflow.run_ref.contracts import SetupCommand, SetupPolicy
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.compiler_session import (
    CompilerSession,
    ElaborationSessionState,
)
from orchestrator.workflow_lisp.definitions import (
    PathDef,
    RecordDef,
    RecordField,
    UnionDef,
    UnionVariant,
)
from orchestrator.workflow_lisp.expressions import (
    RunRefBundleProgram,
    RunRefExpr,
    RunRefPathProgram,
    RunRefSource,
    ExprNode,
    FunctionCallExpr,
    LiteralExpr,
    NameExpr,
    ProcedureCallExpr,
    parse_run_ref_expression,
)
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs
from orchestrator.workflow_lisp.form_registry import get_form_spec
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxList, SyntaxNode, syntax_node_datum
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    UnionTypeRef,
)
from orchestrator.workflow_lisp.typecheck_dispatch import typecheck_expression
from orchestrator.workflow_lisp.typecheck_run_ref import (
    RUN_REF_FIXED_TYPE_NAMES,
    metadata_for_run_ref_expr,
    register_all_known_run_ref_types,
)
from orchestrator.workflow_lisp.workflows import WorkflowCatalog, WorkflowSignature


FORM_PATH = ("workflow-lisp", "run-ref-test")


def _expression(source: str) -> SyntaxNode:
    parsed = read_sexpr_text(source, source_path="run_ref_expression.orc")
    assert len(parsed.items) == 1
    datum = parsed.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="run_ref_expression.orc",
        form_path=FORM_PATH,
    )


def _type_env(*extra_types) -> FrontendTypeEnvironment:
    refs = {
        name: PrimitiveTypeRef(name=name)
        for name in (
            "String", "Int", "Float", "Bool", "Value", "Json", "RunId"
        )
    }
    refs.update({type_ref.name: type_ref for type_ref in extra_types})
    return FrontendTypeEnvironment(refs, target_dsl_version="2.24")


def _catalog(expr: RunRefExpr, *, params=(), return_type=None, defaults=()):
    signature = WorkflowSignature(
        name="child",
        params=tuple(params),
        return_type_ref=return_type or PrimitiveTypeRef("String"),
        span=expr.span,
        form_path=("workflow-lisp", "defworkflow", "child"),
        param_defaults={name: object() for name in defaults},
    )
    return WorkflowCatalog(
        signatures_by_name={"child": signature},
        definitions_by_name={},
        imported_bundles_by_name={},
    )


def _mode_one_expr(*, inputs=(), source_path="run_ref_expression.orc") -> RunRefExpr:
    parsed = read_sexpr_text(_mode_one_source(), source_path=source_path)
    datum = parsed.items[0]
    expr = parse_run_ref_expression(
        SyntaxNode(
            datum=datum,
            span=datum.span,
            module_path=source_path,
            form_path=FORM_PATH,
        ),
        target_dsl_version="2.24",
    )
    return replace(expr, inputs=tuple(inputs))


def _mode_one_source() -> str:
    return " ".join(
        (
            "(run-ref",
            ':source (:repo "file:///workspace"',
            ':commit "0123456789abcdef0123456789abcdef01234567")',
            ":program (:bundle child)",
            ":inputs ()",
            ":policy (:setup ()))",
        )
    )


def test_run_ref_rejects_target_223() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(_mode_one_source()),
            target_dsl_version="2.23",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_target_dsl_unsupported"


def test_run_ref_target_224_elaborates_frozen_mode_one_carriers() -> None:
    expr = parse_run_ref_expression(
        _expression(_mode_one_source()),
        target_dsl_version="2.24",
    )

    assert expr == RunRefExpr(
        source=RunRefSource(
            repo="file:///workspace",
            commit="0123456789abcdef0123456789abcdef01234567",
        ),
        program=RunRefBundleProgram(workflow_name="child"),
        inputs=(),
        setup=SetupPolicy(),
        span=expr.span,
        form_path=FORM_PATH,
    )
    with pytest.raises(FrozenInstanceError):
        expr.inputs = ()


def test_run_ref_target_224_elaborates_mode_two_with_return(
    tmp_path,
) -> None:
    source = "\n".join(
        (
            "(run-ref",
            f'  :source (:repo "{tmp_path}"',
            '            :commit "0123456789abcdef0123456789abcdef01234567")',
            '  :program (:path "experiments/candidate.orc" :entry candidate)',
            "  :inputs ()",
            "  :returns Value",
            "  :policy (:environment :deterministic-effect-free :setup ()))",
        )
    )

    expr = parse_run_ref_expression(
        _expression(source),
        target_dsl_version="2.24",
    )

    assert expr.source == RunRefSource(
        repo=tmp_path.resolve().as_uri(),
        commit="0123456789abcdef0123456789abcdef01234567",
    )
    assert expr.program == RunRefPathProgram(
        path="experiments/candidate.orc",
        entry_name="candidate",
    )
    assert expr.returns_type_name == "Value"
    assert expr.environment == "deterministic-effect-free"
    assert expr.setup == SetupPolicy()


def test_run_ref_mode_one_elaborates_inputs_setup_and_traversal() -> None:
    source = " ".join(
        (
            "(run-ref",
            ':source (:repo "https://EXAMPLE.com/repo/"',
            ':commit "0123456789abcdef0123456789abcdef01234567")',
            ":program (:bundle child)",
            ":inputs (:task task :attempt 3)",
            ':policy (:setup ((:argv ("/usr/bin/python3" "-V")',
            ':env (:MODE "test"))',
            '(:argv ("./tools/setup")))))',
        )
    )

    expr = parse_run_ref_expression(
        _expression(source),
        target_dsl_version="2.24",
        bound_names=frozenset({"task"}),
    )

    assert expr.source.repo == "https://example.com/repo"
    assert tuple(name for name, _ in expr.inputs) == ("task", "attempt")
    task_expr = expr.inputs[0][1]
    attempt_expr = expr.inputs[1][1]
    assert task_expr == NameExpr(
        name="task",
        span=task_expr.span,
        form_path=FORM_PATH + ("inputs", "task"),
    )
    assert attempt_expr == LiteralExpr(
        value=3,
        literal_kind="int",
        span=attempt_expr.span,
        form_path=FORM_PATH + ("inputs", "attempt"),
    )
    assert expr.setup == SetupPolicy(
        commands=(
            SetupCommand(
                argv=("/usr/bin/python3", "-V"),
                env=(("MODE", "test"),),
            ),
            SetupCommand(argv=("./tools/setup",)),
        )
    )
    assert iter_child_exprs(expr) == (task_expr, attempt_expr)


@pytest.mark.parametrize(
    ("call_source", "visibility", "expected_type"),
    (
        ("(normalize task)", "function", FunctionCallExpr),
        ("(prepare task)", "procedure", ProcedureCallExpr),
    ),
)
def test_run_ref_inputs_preserve_visible_callable_context_without_state_leak(
    call_source: str,
    visibility: str,
    expected_type: type,
) -> None:
    source = _mode_one_source().replace(
        ":inputs ()",
        f":inputs (:value {call_source})",
    )
    session_state = ElaborationSessionState(
        function_names=frozenset({"original"}),
        target_dsl_version="2.19",
        guidance_example=True,
    )

    expr = parse_run_ref_expression(
        _expression(source),
        target_dsl_version="2.24",
        bound_names=frozenset({"task"}),
        function_names=(
            frozenset({"normalize"})
            if visibility == "function"
            else frozenset()
        ),
        procedure_names=(
            frozenset({"prepare"})
            if visibility == "procedure"
            else frozenset()
        ),
        guidance_example=False,
        session_state=session_state,
    )

    value_expr = expr.inputs[0][1]
    assert isinstance(value_expr, expected_type)
    assert value_expr.args == (
        NameExpr(
            name="task",
            span=value_expr.args[0].span,
            form_path=FORM_PATH + ("inputs", "value"),
        ),
    )
    assert session_state.function_names == frozenset({"original"})
    assert session_state.target_dsl_version == "2.19"
    assert session_state.guidance_example is True


def test_run_ref_bundle_uses_workflow_resolver_without_session_leak() -> None:
    source = _mode_one_source().replace("child", "local-alias")
    observed: list[tuple[str, object, tuple[str, ...]]] = []

    def resolve_workflow(name, span, form_path):
        observed.append((name, span, form_path))
        return "imported/canonical-child"

    session_state = ElaborationSessionState(
        workflow_name_resolver=resolve_workflow,
        target_dsl_version="2.19",
    )

    expr = parse_run_ref_expression(
        _expression(source),
        target_dsl_version="2.24",
        session_state=session_state,
    )

    assert expr.program == RunRefBundleProgram(
        workflow_name="imported/canonical-child"
    )
    assert len(observed) == 1
    authored_name, authored_span, resolver_form_path = observed[0]
    assert authored_name == "local-alias"
    assert authored_span.start.column == source.index("local-alias") + 1
    assert resolver_form_path == FORM_PATH
    assert session_state.workflow_name_resolver is resolve_workflow
    assert session_state.target_dsl_version == "2.19"


def test_run_ref_mode_two_without_returns_defers_default() -> None:
    source = " ".join(
        (
            "(run-ref",
            ':source (:repo "ssh://example.com/repo"',
            ':commit "0123456789abcdef0123456789abcdef01234567")',
            ':program (:path "candidate.orc" :entry candidate)',
            ":inputs ()",
            ":policy (:environment :deterministic-effect-free :setup ()))",
        )
    )

    expr = parse_run_ref_expression(
        _expression(source),
        target_dsl_version="2.24",
    )

    assert isinstance(expr.program, RunRefPathProgram)
    assert expr.returns_type_name is None


def test_run_ref_repository_locator_normalization_is_clone_root_independent(
    tmp_path,
) -> None:
    canonical_root = tmp_path / "repo"
    spellings = (
        str(tmp_path / "clone" / ".." / "repo"),
        canonical_root.as_uri(),
    )

    expressions = tuple(
        parse_run_ref_expression(
            _expression(_mode_one_source().replace("file:///workspace", locator)),
            target_dsl_version="2.24",
        )
        for locator in spellings
    )

    assert expressions[0].source == expressions[1].source


def test_run_ref_invalid_repository_locator_is_literal_diagnostic() -> None:
    source = _mode_one_source().replace("file:///workspace", "relative/repo")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "run_ref_literal_required"
    assert "repository locator is invalid" in diagnostic.message
    assert diagnostic.span.start.column == source.index('"relative/repo"') + 1


@pytest.mark.parametrize(
    ("source", "expected_code"),
    (
        (
            _mode_one_source().replace(
                ':commit "0123456789abcdef0123456789abcdef01234567"',
                ':repo "file:///duplicate" '
                ':commit "0123456789abcdef0123456789abcdef01234567"',
            ),
            "run_ref_shape_invalid",
        ),
        (
            _mode_one_source().replace(
                ':commit "0123456789abcdef0123456789abcdef01234567"',
                ':branch "main" '
                ':commit "0123456789abcdef0123456789abcdef01234567"',
            ),
            "run_ref_shape_invalid",
        ),
        (
            _mode_one_source().replace(
                "(:bundle child)",
                '(:path "candidate.orc")',
            ),
            "run_ref_program_mode_invalid",
        ),
        (
            _mode_one_source().replace(
                "(:bundle child)",
                '(:bundle child :path "candidate.orc" :entry candidate)',
            ),
            "run_ref_program_mode_invalid",
        ),
        (
            _mode_one_source().replace(
                ":inputs ()",
                ":inputs () :returns Value",
            ),
            "run_ref_program_mode_invalid",
        ),
        (
            _mode_one_source().replace(
                ":policy (:setup ())",
                ":policy (:environment :deterministic-effect-free :setup ())",
            ),
            "run_ref_program_mode_invalid",
        ),
        (
            _mode_one_source()
            .replace("(:bundle child)", '(:path "candidate.orc" :entry candidate)')
            .replace(
                ":policy (:setup ())",
                ":policy (:setup ())",
            ),
            "run_ref_program_mode_invalid",
        ),
    ),
)
def test_run_ref_nested_shape_and_mode_restrictions(
    source: str,
    expected_code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    assert excinfo.value.diagnostics[0].code == expected_code


@pytest.mark.parametrize(
    "setup",
    (
        '((:argv ("python")))',
        '((:argv ("/bin/tool" value)))',
        '((:argv ("/bin/tool") :env (:MODE value)))',
        '((:argv ("/bin/tool") :env (:PWD "owned")))',
    ),
)
def test_run_ref_setup_static_policy_failures_are_literal_diagnostics(
    setup: str,
) -> None:
    source = _mode_one_source().replace(
        ":setup ()",
        f":setup {setup}",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_literal_required"


def test_runs_ref_declared_effect_parses_and_renders_stably() -> None:
    from orchestrator.workflow_lisp.effects import (
        RunsRefEffect,
        parse_effect_clause,
        render_effect_atom,
    )

    syntax = syntax_node_datum(_expression("((runs-ref child-name))"))
    assert isinstance(syntax, SyntaxList)

    effects = parse_effect_clause(
        syntax,
        span=syntax.span,
        form_path=FORM_PATH,
    )

    assert effects == frozenset({RunsRefEffect(subject=("child-name",))})
    assert render_effect_atom(next(iter(effects))) == "runs-ref(child-name)"


def test_runs_ref_declared_effect_requires_one_static_subject() -> None:
    from orchestrator.workflow_lisp.effects import parse_effect_clause

    syntax = syntax_node_datum(_expression("((runs-ref first second))"))
    assert isinstance(syntax, SyntaxList)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_effect_clause(
            syntax,
            span=syntax.span,
            form_path=FORM_PATH,
        )

    assert excinfo.value.diagnostics[0].code == "procedure_effect_invalid"


@pytest.mark.parametrize(
    ("source", "line"),
    (
        (
            '(run-ref :source (:repo "file:///workspace" '
            ':commit "0123456789abcdef0123456789abcdef0123456A") '
            ":program (:bundle child) :inputs () :policy (:setup ()))",
            1,
        ),
        (
            '(run-ref :source (:repo "file:///workspace" '
            ':commit "0123456789abcdef0123456789abcdef01234567") '
            ':program (:path "../candidate.orc" :entry candidate) '
            ":inputs () :policy (:environment :deterministic-effect-free "
            ":setup ()))",
            1,
        ),
    ),
)
def test_run_ref_invalid_sha_or_program_path_is_literal_diagnostic(
    source: str,
    line: int,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "run_ref_literal_required"
    assert diagnostic.span.start.line == line


@pytest.mark.parametrize(
    "source",
    (
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs ())",
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs () :inputs () :policy (:setup ()))",
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs () :policy (:setup ()) :extra true)",
        '(run-ref :source (:repo "file:///workspace") '
        ":program (:bundle child) :inputs () :policy (:setup ()))",
        _mode_one_source().replace("(:bundle child)", "(:workflow child)"),
    ),
)
def test_run_ref_structural_errors_use_closed_shape_diagnostic(source: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_shape_invalid"


@pytest.mark.parametrize(
    "source",
    (
        "(run-ref :source workspace :program (:bundle child) "
        ":inputs () :policy (:setup ()))",
        "(run-ref :source (:repo workspace "
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs () :policy (:setup ()))",
        '(run-ref :source (:repo "file:///workspace" :commit 12) '
        ":program (:bundle child) :inputs () :policy (:setup ()))",
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ':program (:bundle "child") :inputs () :policy (:setup ()))',
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ':program (:bundle child) :inputs () :policy (:setup "none"))',
        '(run-ref :source (:repo "file:///workspace" '
        ':commit "0123456789abcdef0123456789abcdef01234567") '
        ":program (:bundle child) :inputs () :policy setup)",
    ),
)
def test_run_ref_nonliteral_static_fields_use_closed_literal_diagnostic(
    source: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_literal_required"


@pytest.mark.parametrize(
    "program",
    ('(:path "candidate.orc" :entry child)',),
)
def test_run_ref_program_discriminator_uses_closed_mode_diagnostic(
    program: str,
) -> None:
    source = _mode_one_source().replace("(:bundle child)", program)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        parse_run_ref_expression(
            _expression(source),
            target_dsl_version="2.24",
        )

    assert excinfo.value.diagnostics[0].code == "run_ref_program_mode_invalid"


def test_run_ref_parser_is_not_registered_for_ordinary_elaboration() -> None:
    assert get_form_spec("run-ref", target_dsl_version="2.24") is None
    assert RunRefExpr in get_args(ExprNode)


def _transportable_types(span):
    string_type = PrimitiveTypeRef("String")
    int_type = PrimitiveTypeRef("Int")
    record_def = RecordDef(
        name="ChildRecord",
        fields=(RecordField(name="value", type_name="String", span=span),),
        span=span,
    )
    record_type = RecordTypeRef(
        name="ChildRecord",
        definition=record_def,
        field_types={"value": string_type},
    )
    union_def = UnionDef(
        name="ChildUnion",
        variants=(UnionVariant(name="OK", fields=(), span=span),),
        span=span,
    )
    union_type = UnionTypeRef(
        name="ChildUnion",
        definition=union_def,
        variant_field_types={"OK": {}},
    )
    path_def = PathDef(
        name="ChildPath",
        kind="relpath",
        under="artifacts/work",
        must_exist=False,
        span=span,
    )
    return (
        PrimitiveTypeRef("Bool"),
        record_type,
        union_type,
        ListTypeRef("List[String]", string_type),
        MapTypeRef("Map[String,Int]", string_type, int_type),
        OptionalTypeRef("Optional[String]", string_type),
        PathTypeRef("ChildPath", path_def),
        PrimitiveTypeRef("Value"),
    )


@pytest.mark.parametrize("return_index", range(8))
def test_run_ref_mode_one_accepts_every_transportable_return_root(
    return_index: int,
) -> None:
    expr = _mode_one_expr()
    return_type = _transportable_types(expr.span)[return_index]

    typed = typecheck_expression(
        expr,
        type_env=_type_env(*_transportable_types(expr.span)[1:]),
        value_env={},
        workflow_catalog=_catalog(expr, return_type=return_type),
    )

    assert isinstance(typed.type_ref, RecordTypeRef)
    assert typed.type_ref.name.startswith("RunRefResult$")
    assert typed.type_ref.field_types["value"] == return_type


def test_run_ref_mode_one_checks_public_inputs_defaults_and_effect() -> None:
    expr = _mode_one_expr(
        inputs=(
            ("task", LiteralExpr("work", "string", _mode_one_expr().span, FORM_PATH)),
        )
    )
    string_type = PrimitiveTypeRef("String")
    int_type = PrimitiveTypeRef("Int")

    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(
            expr,
            params=(("task", string_type), ("attempt", int_type)),
            defaults=("attempt",),
        ),
    )

    from orchestrator.workflow_lisp.effects import RunsRefEffect

    assert typed.effect_summary.direct_effects == frozenset(
        {RunsRefEffect(subject=("child",))}
    )


@pytest.mark.parametrize(
    ("inputs", "params", "expected_code"),
    (
        ((), (("task", PrimitiveTypeRef("String")),), "workflow_signature_mismatch"),
        (
            (("extra", LiteralExpr("x", "string", _expression('"x"').span, FORM_PATH)),),
            (),
            "workflow_signature_mismatch",
        ),
        (
            (
                ("task", LiteralExpr("x", "string", _expression('"x"').span, FORM_PATH)),
                ("task", LiteralExpr("y", "string", _expression('"y"').span, FORM_PATH)),
            ),
            (("task", PrimitiveTypeRef("String")),),
            "workflow_signature_mismatch",
        ),
        (
            (("task", LiteralExpr(1, "int", _expression("1").span, FORM_PATH)),),
            (("task", PrimitiveTypeRef("String")),),
            "type_mismatch",
        ),
    ),
)
def test_run_ref_mode_one_rejects_signature_mismatches(
    inputs,
    params,
    expected_code: str,
) -> None:
    expr = _mode_one_expr(inputs=inputs)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(expr, params=params),
        )
    assert excinfo.value.diagnostics[0].code == expected_code


@pytest.mark.parametrize("supply_private", (False, True))
def test_run_ref_mode_one_rejects_selected_private_boundary_state(
    supply_private: bool,
) -> None:
    inputs = (
        (("private", LiteralExpr("x", "string", _expression('"x"').span, FORM_PATH)),)
        if supply_private
        else ()
    )
    expr = _mode_one_expr(inputs=inputs)
    string_type = PrimitiveTypeRef("String")
    signature = WorkflowSignature(
        name="child",
        params=(),
        return_type_ref=string_type,
        span=expr.span,
        form_path=FORM_PATH,
        private_compatibility_bridge_types={"private": string_type},
        allow_private_compatibility_bridge_omission=True,
    )
    catalog = WorkflowCatalog(
        signatures_by_name={"child": signature},
        definitions_by_name={},
        imported_bundles_by_name={},
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=catalog,
        )
    assert excinfo.value.diagnostics[0].code == "workflow_signature_mismatch"


@pytest.mark.parametrize(
    ("signature_kwargs", "supplied_name"),
    (
        ({"hidden_context_requirements": {"ctx": object()}}, "ctx"),
        ({"hidden_context_ambiguities": {"ctx": ("one", "two")}}, "ctx"),
    ),
)
@pytest.mark.parametrize("supply_hidden", (False, True))
def test_run_ref_mode_one_rejects_selected_hidden_boundary_state(
    signature_kwargs,
    supplied_name: str,
    supply_hidden: bool,
) -> None:
    inputs = (
        ((supplied_name, LiteralExpr("x", "string", _expression('"x"').span, FORM_PATH)),)
        if supply_hidden
        else ()
    )
    expr = _mode_one_expr(inputs=inputs)
    signature = WorkflowSignature(
        name="child",
        params=(),
        return_type_ref=PrimitiveTypeRef("String"),
        span=expr.span,
        form_path=FORM_PATH,
        **signature_kwargs,
    )
    catalog = WorkflowCatalog(
        signatures_by_name={"child": signature},
        definitions_by_name={},
        imported_bundles_by_name={},
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=catalog,
        )
    assert excinfo.value.diagnostics[0].code == "workflow_signature_mismatch"


def test_run_ref_mode_one_private_name_is_unknown_on_public_only_signature() -> None:
    value_expr = LiteralExpr("x", "string", _expression('"x"').span, FORM_PATH)
    expr = _mode_one_expr(inputs=(("private", value_expr),))

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(expr),
        )
    assert excinfo.value.diagnostics[0].code == "workflow_signature_mismatch"


def test_run_ref_effect_preserves_canonical_identity_as_one_subject() -> None:
    expr = replace(
        _mode_one_expr(),
        program=RunRefBundleProgram("imported.module/child-name"),
    )
    catalog = _catalog(expr)
    canonical_signature = replace(
        catalog.signatures_by_name["child"],
        name="imported.module/child-name",
    )
    catalog = replace(
        catalog,
        signatures_by_name={"imported.module/child-name": canonical_signature},
    )

    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=catalog,
    )

    from orchestrator.workflow_lisp.effects import CallsWorkflowEffect, RunsRefEffect

    assert typed.effect_summary.direct_effects == frozenset(
        {RunsRefEffect(subject=("imported.module/child-name",))}
    )
    assert not any(
        isinstance(effect, CallsWorkflowEffect)
        for effect in typed.effect_summary.transitive_effects
    )


def _mode_two_expr(*, returns_type_name=None, inputs=()) -> RunRefExpr:
    source = " ".join(
        (
            "(run-ref",
            ':source (:repo "file:///workspace"',
            ':commit "0123456789abcdef0123456789abcdef01234567")',
            ':program (:path "candidate.orc" :entry candidate)',
            ":inputs ()",
            ":policy (:environment :deterministic-effect-free :setup ()))",
        )
    )
    expr = parse_run_ref_expression(
        _expression(source), target_dsl_version="2.24"
    )
    return replace(expr, returns_type_name=returns_type_name, inputs=tuple(inputs))


@pytest.mark.parametrize("return_index", range(8))
def test_run_ref_mode_two_resolves_every_transportable_return_refinement(
    return_index: int,
) -> None:
    probe = _mode_two_expr()
    types = _transportable_types(probe.span)
    return_type = types[return_index]
    expr = replace(probe, returns_type_name=return_type.name)

    typed = typecheck_expression(
        expr,
        type_env=_type_env(*types[1:]),
        value_env={},
    )

    assert isinstance(typed.type_ref, RecordTypeRef)
    assert typed.type_ref.name.startswith("RunRefResult$")
    assert typed.type_ref.field_types["value"] == return_type


def test_run_ref_mode_two_defaults_value_and_merges_input_effects() -> None:
    inner = _mode_one_expr()
    expr = _mode_two_expr(inputs=(("seed", inner),))

    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(inner),
    )

    from orchestrator.workflow_lisp.effects import RunsRefEffect

    assert isinstance(typed.type_ref, RecordTypeRef)
    assert typed.type_ref.field_types["value"] == PrimitiveTypeRef("Value")
    assert typed.effect_summary.direct_effects == frozenset(
        {
            RunsRefEffect(subject=("child",)),
            RunsRefEffect(subject=("candidate",)),
        }
    )


@pytest.mark.parametrize(
    "expr",
    (
        _mode_two_expr(returns_type_name="Json"),
        _mode_two_expr(
            inputs=(("payload", NameExpr("payload", _expression("payload").span, FORM_PATH)),)
        ),
    ),
)
def test_run_ref_mode_two_rejects_nontransportable_returns_and_inputs(
    expr: RunRefExpr,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={"payload": PrimitiveTypeRef("Json")},
        )
    assert excinfo.value.diagnostics[0].code == "workflow_boundary_type_invalid"


def _record_field_signature(type_ref: RecordTypeRef):
    return tuple(
        (field.name, type_ref.field_types[field.name].name)
        for field in type_ref.definition.fields
    )


def test_run_ref_registers_exact_fixed_structural_catalog_and_wrapper() -> None:
    expr = _mode_one_expr()
    type_env = _type_env()
    session = CompilerSession()

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr),
        compiler_session=session,
    )

    assert isinstance(typed.type_ref, RecordTypeRef)
    fixed = {
        name: type_env.resolve_type(
            name,
            span=expr.span,
            form_path=FORM_PATH,
            session_state=session.typecheck,
        )
        for name in RUN_REF_FIXED_TYPE_NAMES
    }
    assert all(isinstance(value, RecordTypeRef) for value in fixed.values())
    assert _record_field_signature(fixed["RepositoryRevisionId"]) == (
        ("digest", "String"),
        ("normalized_locator", "String"),
        ("resolved_commit_sha", "String"),
        ("materializer_version", "String"),
        ("submodule_policy", "String"),
        ("lfs_policy", "String"),
        ("authored_setup_identity", "String"),
    )
    assert _record_field_signature(fixed["WorkspaceEntryDelta"]) == (
        ("path", "String"),
        ("kind", "String"),
        ("mode", "Int"),
        ("size", "Int"),
        ("old_sha256", "Optional[String]"),
        ("new_sha256", "Optional[String]"),
        ("link_target", "Optional[String]"),
    )
    assert _record_field_signature(fixed["NormalizedTextDiffEntry"]) == (
        ("path", "String"),
        ("text", "String"),
        ("truncated", "Bool"),
        ("omitted_bytes", "Int"),
    )
    assert _record_field_signature(fixed["NormalizedWorkspaceDiff"]) == (
        ("entries", "List[NormalizedTextDiffEntry]"),
        ("catalog_digest", "String"),
        ("truncated", "Bool"),
        ("omitted_bytes", "Int"),
        ("omitted_entries", "Int"),
    )
    assert _record_field_signature(fixed["DeclaredWorkspaceArtifact"]) == (
        ("name", "String"),
        ("path", "String"),
        ("kind", "String"),
        ("mode", "Int"),
        ("size", "Int"),
        ("sha256", "Optional[String]"),
        ("link_target", "Optional[String]"),
    )
    assert _record_field_signature(fixed["WorkspaceDelta"]) == (
        ("base", "RepositoryRevisionId"),
        ("changed_files", "List[WorkspaceEntryDelta]"),
        ("deleted_files", "List[WorkspaceEntryDelta]"),
        ("untracked_files", "List[WorkspaceEntryDelta]"),
        ("normalized_diff", "NormalizedWorkspaceDiff"),
        ("declared_artifacts", "List[DeclaredWorkspaceArtifact]"),
    )
    assert _record_field_signature(fixed["RunRefAccounting"]) == (
        ("child_run_id", "RunId"),
        ("attempt_ordinal", "Int"),
        ("terminal_status", "String"),
        ("elapsed_ms", "Int"),
        ("setup_ms", "Int"),
        ("compile_ms", "Int"),
        ("provider_attempts", "Value"),
        ("token_usage", "Value"),
        ("cost", "Value"),
    )
    assert _record_field_signature(typed.type_ref) == (
        ("value", "String"),
        ("workspace_delta", "WorkspaceDelta"),
        ("accounting", "RunRefAccounting"),
    )


def test_run_ref_generated_name_ignores_authored_source_path() -> None:
    left = _mode_one_expr(source_path="/clone-a/controller.orc")
    right = _mode_one_expr(source_path="/clone-b/controller.orc")
    left_session = CompilerSession()
    right_session = CompilerSession()

    left_typed = typecheck_expression(
        left,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(left),
        compiler_session=left_session,
    )
    right_typed = typecheck_expression(
        right,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(right),
        compiler_session=right_session,
    )

    assert left_typed.type_ref.name == right_typed.type_ref.name


def test_run_ref_generated_name_binds_site_program_and_value_type() -> None:
    base = _mode_one_expr()
    moved = replace(
        base,
        span=replace(
            base.span,
            start=replace(base.span.start, column=base.span.start.column + 1),
        ),
    )
    alternate = replace(base, program=RunRefBundleProgram("other-child"))
    names = []
    for expr, program_name, value_type in (
        (base, "child", PrimitiveTypeRef("String")),
        (moved, "child", PrimitiveTypeRef("String")),
        (alternate, "other-child", PrimitiveTypeRef("String")),
        (base, "child", PrimitiveTypeRef("Bool")),
    ):
        catalog = WorkflowCatalog(
            signatures_by_name={
                program_name: WorkflowSignature(
                    name=program_name,
                    params=(),
                    return_type_ref=value_type,
                    span=expr.span,
                    form_path=FORM_PATH,
                )
            },
            definitions_by_name={},
            imported_bundles_by_name={},
        )
        typed = typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=catalog,
        )
        names.append(typed.type_ref.name)
    assert len(set(names)) == 4


def test_run_ref_generated_name_binds_active_canonical_caller_identity() -> None:
    expr = _mode_one_expr()
    names = []
    for caller_name in ("module/first", "module/second"):
        session = CompilerSession()
        session.typecheck.workflow_signature = WorkflowSignature(
            name=caller_name,
            params=(),
            return_type_ref=PrimitiveTypeRef("String"),
            span=expr.span,
            form_path=FORM_PATH,
        )
        typed = typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(expr),
            compiler_session=session,
        )
        names.append(typed.type_ref.name)
    assert names[0] != names[1]


def test_run_ref_metadata_rolls_back_and_reuses_equal_site() -> None:
    session = CompilerSession()
    missing = _mode_one_expr()
    with pytest.raises(LispFrontendCompileError):
        typecheck_expression(
            missing,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(
                missing,
                params=(("required", PrimitiveTypeRef("String")),),
            ),
            compiler_session=session,
        )
    assert session.typecheck.run_ref_metadata_by_name == {}
    assert session.typecheck.run_ref_metadata_by_expr_key == {}

    expr = _mode_one_expr()
    first = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr),
        compiler_session=session,
    )
    second = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr),
        compiler_session=session,
    )
    assert first.type_ref.name == second.type_ref.name
    assert len(session.typecheck.run_ref_metadata_by_name) == 1


def test_run_ref_metadata_hydrates_another_type_environment() -> None:
    expr = _mode_one_expr()
    session = CompilerSession()
    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr),
        compiler_session=session,
    )
    metadata = metadata_for_run_ref_expr(
        typed.expr,
        result_type=typed.type_ref,
        session_state=session.typecheck,
    )
    assert metadata is not None

    hydrated = _type_env()
    register_all_known_run_ref_types(
        hydrated,
        session_state=session.typecheck,
    )
    assert hydrated.resolve_type(
        typed.type_ref.name,
        span=expr.span,
        form_path=FORM_PATH,
        session_state=session.typecheck,
    ) == typed.type_ref


def test_run_ref_metadata_collision_fails_closed_and_restores_session() -> None:
    from orchestrator.workflow_lisp.typecheck_context import (
        TypecheckSessionStateCollisionError,
    )

    expr = _mode_one_expr()
    session = CompilerSession()
    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr),
        compiler_session=session,
    )
    metadata = session.typecheck.run_ref_metadata_by_name[typed.type_ref.name]
    conflicting = replace(metadata, site_digest="0" * 64)
    session.typecheck.run_ref_metadata_by_name[typed.type_ref.name] = conflicting
    session.typecheck.run_ref_metadata_by_expr_key[metadata.expression_key][
        metadata.type_signature
    ] = conflicting

    with pytest.raises(TypecheckSessionStateCollisionError):
        typecheck_expression(
            expr,
            type_env=_type_env(),
            value_env={},
            workflow_catalog=_catalog(expr),
            compiler_session=session,
        )
    assert session.typecheck.run_ref_metadata_by_name[typed.type_ref.name] is conflicting


def test_run_ref_metadata_merge_accepts_equivalent_and_rejects_conflict() -> None:
    from orchestrator.workflow_lisp.typecheck_context import (
        TypecheckSessionStateCollisionError,
        merge_successful_session_outputs,
        snapshot_session_state,
    )

    expr = _mode_one_expr()
    session = CompilerSession()
    typed = typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr),
        compiler_session=session,
    )
    outer = snapshot_session_state(session.typecheck)
    equivalent = snapshot_session_state(session.typecheck)
    merged = merge_successful_session_outputs(outer, equivalent)
    assert merged.run_ref_metadata_by_name == outer.run_ref_metadata_by_name

    conflicting = snapshot_session_state(session.typecheck)
    metadata = conflicting.run_ref_metadata_by_name[typed.type_ref.name]
    replacement = replace(metadata, site_digest="f" * 64)
    conflicting.run_ref_metadata_by_name[typed.type_ref.name] = replacement
    conflicting.run_ref_metadata_by_expr_key[metadata.expression_key][
        metadata.type_signature
    ] = replacement
    with pytest.raises(TypecheckSessionStateCollisionError):
        merge_successful_session_outputs(outer, conflicting)


def test_run_ref_compiler_type_rejects_shape_equal_unowned_binding() -> None:
    from orchestrator.workflow_lisp.typecheck_context import (
        TypecheckSessionStateCollisionError,
    )

    expr = _mode_one_expr()
    owned_env = _type_env()
    typecheck_expression(
        expr,
        type_env=owned_env,
        value_env={},
        workflow_catalog=_catalog(expr),
    )
    shape_equal_unowned = owned_env._type_refs["WorkspaceDelta"]
    unowned_env = _type_env(shape_equal_unowned)

    with pytest.raises(TypecheckSessionStateCollisionError):
        typecheck_expression(
            expr,
            type_env=unowned_env,
            value_env={},
            workflow_catalog=_catalog(expr),
        )


@pytest.mark.parametrize("missing_name", ("Value", "RunId"))
def test_run_ref_fixed_catalog_rejects_missing_target_primitive(
    missing_name: str,
) -> None:
    from orchestrator.workflow_lisp.typecheck_context import (
        TypecheckSessionStateCollisionError,
    )

    expr = _mode_one_expr()
    type_env = _type_env()
    del type_env._type_refs[missing_name]
    with pytest.raises(TypecheckSessionStateCollisionError):
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={},
            workflow_catalog=_catalog(expr),
        )
