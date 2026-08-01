from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import subprocess
import sys
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
    IfExpr,
    LiteralExpr,
    NameExpr,
    ProcedureCallExpr,
    parse_run_ref_expression,
)
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs
from orchestrator.workflow_lisp.form_registry import get_form_spec
from orchestrator.workflow_lisp.lowering import pure_projection as pure_projection_lowering
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.run_ref_result_contract import (
    GeneratedRunRefResultContract,
    RUN_REF_RESULT_CONTRACT_SCHEMA,
    derive_run_ref_result_contract,
)
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
    compiler_run_ref_fixed_types,
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
    return FrontendTypeEnvironment(
        refs,
        target_dsl_version="2.24",
        nominal_descriptor_names_by_definition_id={
            id(type_ref.definition): type_ref.name
            for type_ref in extra_types
            if isinstance(type_ref, (RecordTypeRef, UnionTypeRef))
        },
    )


def test_compiler_normalized_type_descriptor_is_public_behavior_identical() -> None:
    from orchestrator.workflow_lisp import normalized_type_descriptor

    type_env = _type_env()
    type_ref = PrimitiveTypeRef("String")

    assert hasattr(
        pure_projection_lowering,
        "compiler_normalized_type_descriptor",
    )
    assert pure_projection_lowering.compiler_normalized_type_descriptor(
        type_ref,
        type_env=type_env,
    ) == pure_projection_lowering._type_descriptor(
        type_ref,
        type_env=type_env,
    )
    assert (
        pure_projection_lowering.compiler_normalized_type_descriptor
        is normalized_type_descriptor.compiler_normalized_type_descriptor
    )
    assert (
        pure_projection_lowering.validate_compiler_normalized_type_descriptor
        is normalized_type_descriptor.validate_compiler_normalized_type_descriptor
    )


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


def _run_ref_result_contract(
    expr: RunRefExpr,
    value_type,
    *,
    hydrate: bool = False,
):
    type_env = _type_env(value_type)
    session = CompilerSession()
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr, return_type=value_type),
        compiler_session=session,
    )
    if hydrate:
        register_all_known_run_ref_types(
            type_env,
            session_state=session.typecheck,
        )
    return (
        derive_run_ref_result_contract(
            typed.type_ref,
            type_env=type_env,
        ),
        typed.type_ref,
        type_env,
    )


@pytest.mark.parametrize(
    ("return_index", "expected_kind"),
    tuple(
        enumerate(
            (
                "primitive",
                "record",
                "union",
                "list",
                "map",
                "optional",
                "path",
                "primitive",
            )
        )
    ),
)
def test_run_ref_result_contract_preserves_all_transportable_child_roots(
    return_index: int,
    expected_kind: str,
) -> None:
    expr = _mode_one_expr()
    value_type = _transportable_types(expr.span)[return_index]

    contract, result_type, type_env = _run_ref_result_contract(expr, value_type)

    envelope = contract.descriptor["envelope"]
    assert contract.descriptor["schema"] == RUN_REF_RESULT_CONTRACT_SCHEMA
    assert envelope["kind"] == "record"
    assert envelope["name"] == result_type.name
    assert [field["name"] for field in envelope["fields"]] == [
        "value",
        "workspace_delta",
        "accounting",
    ]
    child_descriptor = pure_projection_lowering.compiler_normalized_type_descriptor(
        value_type,
        type_env=type_env,
    )
    assert envelope["fields"][0]["type"] == child_descriptor
    assert envelope["fields"][0]["type"]["kind"] == expected_kind
    assert contract.type_ref == result_type
    from orchestrator.workflow.run_ref.contracts import canonical_sha256

    assert contract.digest == canonical_sha256(contract.descriptor)


def test_run_ref_result_contract_carries_exact_recursive_fixed_schema() -> None:
    expr = _mode_one_expr()
    contract, _, _ = _run_ref_result_contract(expr, PrimitiveTypeRef("String"))

    workspace = contract.descriptor["envelope"]["fields"][1]["type"]
    accounting = contract.descriptor["envelope"]["fields"][2]["type"]
    with pytest.raises(FrozenInstanceError):
        contract.digest = "sha256:changed"
    assert workspace == {
        "kind": "record",
        "name": "WorkspaceDelta",
        "fields": [
            {
                "name": "base",
                "type": {
                    "kind": "record",
                    "name": "RepositoryRevisionId",
                    "fields": [
                        {"name": name, "type": {"kind": "primitive", "name": "String"}}
                        for name in (
                            "digest",
                            "normalized_locator",
                            "resolved_commit_sha",
                            "materializer_version",
                            "submodule_policy",
                            "lfs_policy",
                            "authored_setup_identity",
                        )
                    ],
                },
            },
            *[
                {
                    "name": name,
                    "type": {
                        "kind": "list",
                        "item": {
                            "kind": "record",
                            "name": "WorkspaceEntryDelta",
                            "fields": [
                                {"name": "path", "type": {"kind": "primitive", "name": "String"}},
                                {"name": "kind", "type": {"kind": "primitive", "name": "String"}},
                                {"name": "mode", "type": {"kind": "primitive", "name": "Int"}},
                                {"name": "size", "type": {"kind": "primitive", "name": "Int"}},
                                *[
                                    {
                                        "name": optional_name,
                                        "type": {
                                            "kind": "optional",
                                            "item": {"kind": "primitive", "name": "String"},
                                        },
                                    }
                                    for optional_name in (
                                        "old_sha256",
                                        "new_sha256",
                                        "link_target",
                                    )
                                ],
                            ],
                        },
                    },
                }
                for name in ("changed_files", "deleted_files", "untracked_files")
            ],
            {
                "name": "normalized_diff",
                "type": {
                    "kind": "record",
                    "name": "NormalizedWorkspaceDiff",
                    "fields": [
                        {
                            "name": "entries",
                            "type": {
                                "kind": "list",
                                "item": {
                                    "kind": "record",
                                    "name": "NormalizedTextDiffEntry",
                                    "fields": [
                                        {"name": "path", "type": {"kind": "primitive", "name": "String"}},
                                        {"name": "text", "type": {"kind": "primitive", "name": "String"}},
                                        {"name": "truncated", "type": {"kind": "primitive", "name": "Bool"}},
                                        {"name": "omitted_bytes", "type": {"kind": "primitive", "name": "Int"}},
                                    ],
                                },
                            },
                        },
                        {"name": "catalog_digest", "type": {"kind": "primitive", "name": "String"}},
                        {"name": "truncated", "type": {"kind": "primitive", "name": "Bool"}},
                        {"name": "omitted_bytes", "type": {"kind": "primitive", "name": "Int"}},
                        {"name": "omitted_entries", "type": {"kind": "primitive", "name": "Int"}},
                    ],
                },
            },
            {
                "name": "declared_artifacts",
                "type": {
                    "kind": "list",
                    "item": {
                        "kind": "record",
                        "name": "DeclaredWorkspaceArtifact",
                        "fields": [
                            {"name": "name", "type": {"kind": "primitive", "name": "String"}},
                            {"name": "path", "type": {"kind": "primitive", "name": "String"}},
                            {"name": "kind", "type": {"kind": "primitive", "name": "String"}},
                            {"name": "mode", "type": {"kind": "primitive", "name": "Int"}},
                            {"name": "size", "type": {"kind": "primitive", "name": "Int"}},
                            {
                                "name": "sha256",
                                "type": {
                                    "kind": "optional",
                                    "item": {"kind": "primitive", "name": "String"},
                                },
                            },
                            {
                                "name": "link_target",
                                "type": {
                                    "kind": "optional",
                                    "item": {"kind": "primitive", "name": "String"},
                                },
                            },
                        ],
                    },
                },
            },
        ],
    }
    assert accounting == {
        "kind": "record",
        "name": "RunRefAccounting",
        "fields": [
            {"name": "child_run_id", "type": {"kind": "primitive", "name": "RunId"}},
            {"name": "attempt_ordinal", "type": {"kind": "primitive", "name": "Int"}},
            {"name": "terminal_status", "type": {"kind": "primitive", "name": "String"}},
            {"name": "elapsed_ms", "type": {"kind": "primitive", "name": "Int"}},
            {"name": "setup_ms", "type": {"kind": "primitive", "name": "Int"}},
            {"name": "compile_ms", "type": {"kind": "primitive", "name": "Int"}},
            {"name": "provider_attempts", "type": {"kind": "primitive", "name": "Value"}},
            {"name": "token_usage", "type": {"kind": "primitive", "name": "Value"}},
            {"name": "cost", "type": {"kind": "primitive", "name": "Value"}},
        ],
    }


def test_run_ref_result_contract_descriptor_views_are_defensive_copies() -> None:
    expr = _mode_one_expr()
    contract, _, _ = _run_ref_result_contract(expr, PrimitiveTypeRef("String"))
    descriptor = contract.descriptor
    descriptor["envelope"]["fields"][1]["type"]["fields"][0]["name"] = (
        "mutated"
    )

    fresh_descriptor = contract.descriptor
    assert fresh_descriptor["envelope"]["fields"][1]["type"]["fields"][0][
        "name"
    ] == "base"
    from orchestrator.workflow.run_ref.contracts import canonical_sha256

    assert canonical_sha256(fresh_descriptor) == contract.digest


def test_run_ref_result_contract_is_not_publicly_constructible() -> None:
    from orchestrator.workflow.run_ref.contracts import (
        canonical_json_bytes,
        canonical_sha256,
    )

    expr = _mode_one_expr()
    contract, result_type, _ = _run_ref_result_contract(
        expr,
        PrimitiveTypeRef("String"),
    )
    malformed = {
        "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
        "envelope": {},
    }
    invalid = (
        (
            canonical_json_bytes(malformed),
            canonical_sha256(malformed),
            result_type,
        ),
        (
            canonical_json_bytes(contract.descriptor),
            contract.digest,
            PrimitiveTypeRef("String"),
        ),
    )

    for descriptor_json, digest, unrelated_type_ref in invalid:
        with pytest.raises(TypeError):
            GeneratedRunRefResultContract(
                _descriptor_json=descriptor_json,
                digest=digest,
                type_ref=unrelated_type_ref,
            )


def test_run_ref_result_contract_import_does_not_load_lowering_modules() -> None:
    check = subprocess.run(
        (
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib, importlib.abc, sys",
                    "import orchestrator.workflow_lisp",
                    "contract = 'orchestrator.workflow_lisp.run_ref_result_contract'",
                    "neutral = 'orchestrator.workflow_lisp.normalized_type_descriptor'",
                    "blocked = 'orchestrator.workflow_lisp.lowering'",
                    "sys.modules.pop(contract, None)",
                    "sys.modules.pop(neutral, None)",
                    "for name in tuple(sys.modules):",
                    "    if name.startswith(blocked):",
                    "        sys.modules.pop(name)",
                    "class Blocker(importlib.abc.MetaPathFinder):",
                    "    def find_spec(self, fullname, path, target=None):",
                    "        if fullname.startswith(blocked):",
                    "            raise RuntimeError('blocked lowering dependency')",
                    "        return None",
                    "sys.meta_path.insert(0, Blocker())",
                    "importlib.import_module(contract)",
                    "assert not any(name.startswith(blocked) for name in sys.modules)",
                )
            ),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr


def test_run_ref_result_contract_is_hydration_and_source_path_independent() -> None:
    left = _mode_one_expr(source_path="/clone-a/controller.orc")
    right = _mode_one_expr(source_path="/clone-b/controller.orc")

    left_contract, left_type, _ = _run_ref_result_contract(
        left,
        PrimitiveTypeRef("String"),
        hydrate=True,
    )
    right_contract, right_type, _ = _run_ref_result_contract(
        right,
        PrimitiveTypeRef("String"),
        hydrate=True,
    )

    assert left_type.name == right_type.name
    assert left_contract.descriptor == right_contract.descriptor
    assert left_contract.digest == right_contract.digest


def test_run_ref_result_contract_digest_binds_child_and_site_without_flattening() -> None:
    base = _mode_one_expr()
    moved = replace(
        base,
        span=replace(
            base.span,
            start=replace(base.span.start, column=base.span.start.column + 1),
        ),
    )
    string_contract, _, _ = _run_ref_result_contract(
        base,
        PrimitiveTypeRef("String"),
    )
    bool_contract, _, _ = _run_ref_result_contract(
        base,
        PrimitiveTypeRef("Bool"),
    )
    moved_contract, _, _ = _run_ref_result_contract(
        moved,
        PrimitiveTypeRef("String"),
    )

    assert len(
        {string_contract.digest, bool_contract.digest, moved_contract.digest}
    ) == 3
    tampered = deepcopy(string_contract.descriptor)
    tampered["envelope"]["fields"][1]["type"]["fields"][0]["name"] = "changed"
    from orchestrator.workflow.run_ref.contracts import canonical_sha256

    assert canonical_sha256(tampered) != string_contract.digest


def _record_with_fields(
    record: RecordTypeRef,
    fields,
    *,
    name: str | None = None,
) -> RecordTypeRef:
    resolved_name = name or record.name
    return RecordTypeRef(
        name=resolved_name,
        definition=RecordDef(
            name=resolved_name,
            fields=tuple(
                RecordField(
                    name=field_name,
                    type_name=field_type.name,
                    span=record.definition.span,
                )
                for field_name, field_type in fields
            ),
            span=record.definition.span,
        ),
        field_types=dict(fields),
    )


def test_run_ref_result_contract_rejects_forged_envelopes_and_fixed_schemas() -> None:
    expr = _mode_one_expr()
    _, valid, type_env = _run_ref_result_contract(
        expr,
        PrimitiveTypeRef("String"),
    )
    value = valid.field_types["value"]
    workspace = valid.field_types["workspace_delta"]
    accounting = valid.field_types["accounting"]
    valid_fields = (
        ("value", value),
        ("workspace_delta", workspace),
        ("accounting", accounting),
    )
    wrong_workspace_name = _record_with_fields(
        workspace,
        tuple(workspace.field_types.items()),
        name="OtherWorkspaceDelta",
    )
    wrong_accounting_name = _record_with_fields(
        accounting,
        tuple(accounting.field_types.items()),
        name="OtherRunRefAccounting",
    )
    changed_accounting = _record_with_fields(
        accounting,
        (*tuple(accounting.field_types.items()), ("extra", PrimitiveTypeRef("Int"))),
    )
    base = workspace.field_types["base"]
    changed_base = _record_with_fields(
        base,
        (
            ("digest", PrimitiveTypeRef("Bool")),
            *tuple(list(base.field_types.items())[1:]),
        ),
    )
    changed_workspace = _record_with_fields(
        workspace,
        (
            ("base", changed_base),
            *tuple(list(workspace.field_types.items())[1:]),
        ),
    )
    invalid = (
        _record_with_fields(valid, valid_fields, name="OtherResult"),
        _record_with_fields(valid, (valid_fields[1], valid_fields[0], valid_fields[2])),
        _record_with_fields(valid, valid_fields[:-1]),
        _record_with_fields(valid, (*valid_fields, ("extra", value))),
        _record_with_fields(
            valid,
            (("value", value), ("workspace_delta", wrong_workspace_name), ("accounting", accounting)),
        ),
        _record_with_fields(
            valid,
            (("value", value), ("workspace_delta", workspace), ("accounting", wrong_accounting_name)),
        ),
        _record_with_fields(
            valid,
            (("value", PrimitiveTypeRef("Json")), ("workspace_delta", workspace), ("accounting", accounting)),
        ),
        _record_with_fields(
            valid,
            (("value", value), ("workspace_delta", changed_workspace), ("accounting", accounting)),
        ),
        _record_with_fields(
            valid,
            (("value", value), ("workspace_delta", workspace), ("accounting", changed_accounting)),
        ),
    )

    for forged in invalid:
        with pytest.raises(ValueError):
            derive_run_ref_result_contract(
                forged,
                type_env=type_env,
            )


def test_run_ref_result_contract_is_additive_to_ordinary_result_contracts() -> None:
    from orchestrator.workflow_lisp.contracts import derive_structured_result_contract

    expr = _mode_one_expr()
    bool_type, record_type, union_type, *_ = _transportable_types(expr.span)
    ordinary = tuple(
        derive_structured_result_contract(
            type_ref,
            workflow_name="ordinary",
            step_id=f"step-{index}",
        )
        for index, type_ref in enumerate((bool_type, record_type, union_type))
    )
    _run_ref_result_contract(expr, PrimitiveTypeRef("String"))
    repeated = tuple(
        derive_structured_result_contract(
            type_ref,
            workflow_name="ordinary",
            step_id=f"step-{index}",
        )
        for index, type_ref in enumerate((bool_type, record_type, union_type))
    )

    assert repeated == ordinary
    assert [contract.contract_kind for contract in ordinary] == [
        "output_bundle",
        "output_bundle",
        "variant_output",
    ]
    assert [contract.result_shape for contract in ordinary] == [
        "root_value",
        "record_value",
        "union_value",
    ]


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
    independent_session = CompilerSession()
    typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        workflow_catalog=_catalog(expr),
        compiler_session=independent_session,
    )
    equivalent = snapshot_session_state(independent_session.typecheck)
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


def test_run_ref_metadata_merge_rejects_changed_hydration_vector() -> None:
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
    changed = snapshot_session_state(session.typecheck)
    metadata = changed.run_ref_metadata_by_name[typed.type_ref.name]
    replacement = replace(
        metadata,
        compiler_owned_types=metadata.compiler_owned_types[:-1],
    )
    changed.run_ref_metadata_by_name[typed.type_ref.name] = replacement
    changed.run_ref_metadata_by_expr_key[metadata.expression_key][
        metadata.type_signature
    ] = replacement

    with pytest.raises(TypecheckSessionStateCollisionError):
        merge_successful_session_outputs(outer, changed)


def test_run_ref_compiler_type_rejects_shape_equal_unowned_binding() -> None:
    from orchestrator.workflow_lisp.typecheck_context import (
        TypecheckSessionStateCollisionError,
    )

    expr = _mode_one_expr()
    owned_env = _type_env()
    owned_session = CompilerSession()
    typecheck_expression(
        expr,
        type_env=owned_env,
        value_env={},
        workflow_catalog=_catalog(expr),
        compiler_session=owned_session,
    )
    register_all_known_run_ref_types(
        owned_env,
        session_state=owned_session.typecheck,
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


@pytest.mark.parametrize(
    "primitive_name",
    ("String", "Int", "Bool", "Value", "RunId"),
)
def test_run_ref_fixed_catalog_and_result_contract_reject_enum_like_primitives(
    primitive_name: str,
) -> None:
    from orchestrator.workflow_lisp.typecheck_context import (
        TypecheckSessionStateCollisionError,
    )

    malformed = PrimitiveTypeRef(
        name=primitive_name,
        allowed_values=("MALFORMED",),
    )
    type_env = _type_env()
    type_env._type_refs[primitive_name] = malformed
    with pytest.raises(TypecheckSessionStateCollisionError):
        compiler_run_ref_fixed_types(type_env)

    expr = _mode_one_expr()
    _, result_type, contract_env = _run_ref_result_contract(
        expr,
        PrimitiveTypeRef("String"),
    )
    contract_env._type_refs[primitive_name] = malformed
    with pytest.raises(TypecheckSessionStateCollisionError):
        derive_run_ref_result_contract(
            result_type,
            type_env=contract_env,
        )


def test_run_ref_fixed_catalog_and_result_contract_reject_key_name_mismatch() -> None:
    from orchestrator.workflow_lisp.typecheck_context import (
        TypecheckSessionStateCollisionError,
    )

    mismatched = PrimitiveTypeRef("NotString")
    type_env = _type_env()
    type_env._type_refs["String"] = mismatched
    with pytest.raises(TypecheckSessionStateCollisionError):
        compiler_run_ref_fixed_types(type_env)

    expr = _mode_one_expr()
    _, result_type, contract_env = _run_ref_result_contract(
        expr,
        PrimitiveTypeRef("String"),
    )
    contract_env._type_refs["String"] = mismatched
    with pytest.raises(TypecheckSessionStateCollisionError):
        derive_run_ref_result_contract(
            result_type,
            type_env=contract_env,
        )


def test_run_ref_nested_late_failure_rolls_back_session_and_type_environment() -> None:
    run_ref = _mode_one_expr()
    outer = IfExpr(
        condition_expr=LiteralExpr(True, "bool", run_ref.span, FORM_PATH),
        then_expr=run_ref,
        else_expr=LiteralExpr("mismatch", "string", run_ref.span, FORM_PATH),
        span=run_ref.span,
        form_path=FORM_PATH,
    )
    type_env = _type_env()
    session = CompilerSession()
    original_types = dict(type_env._type_refs)
    original_owned_names = set(type_env._compiler_owned_type_names)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            outer,
            type_env=type_env,
            value_env={},
            workflow_catalog=_catalog(run_ref),
            compiler_session=session,
        )
    assert excinfo.value.diagnostics[0].code == "type_mismatch"
    assert session.typecheck.run_ref_metadata_by_name == {}
    assert session.typecheck.run_ref_metadata_by_expr_key == {}
    assert type_env._type_refs == original_types
    assert type_env._compiler_owned_type_names == original_owned_names


def test_run_ref_success_resolves_without_mutation_then_hydrates_explicitly() -> None:
    expr = _mode_one_expr()
    type_env = _type_env()
    session = CompilerSession()
    original_types = dict(type_env._type_refs)
    original_owned_names = set(type_env._compiler_owned_type_names)

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={},
        workflow_catalog=_catalog(expr),
        compiler_session=session,
    )
    assert type_env._type_refs == original_types
    assert type_env._compiler_owned_type_names == original_owned_names
    assert type_env.resolve_type(
        typed.type_ref.name,
        span=expr.span,
        form_path=FORM_PATH,
        session_state=session.typecheck,
    ) == typed.type_ref
    assert type_env._type_refs == original_types
    assert type_env._compiler_owned_type_names == original_owned_names

    register_all_known_run_ref_types(
        type_env,
        session_state=session.typecheck,
    )
    assert typed.type_ref.name in type_env._compiler_owned_type_names
    assert type_env._type_refs[typed.type_ref.name] == typed.type_ref
