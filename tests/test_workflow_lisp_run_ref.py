from dataclasses import FrozenInstanceError
from typing import get_args

import pytest

from orchestrator.workflow.run_ref.contracts import SetupCommand, SetupPolicy
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.compiler_session import ElaborationSessionState
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
