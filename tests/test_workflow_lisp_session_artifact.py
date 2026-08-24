"""Target-2.27 `:session-artifact` syntax, placement, and lowering acceptance.

Covers the full Task 6 RED/GREEN matrix: version gates, bare-symbol
declaration syntax, immutable spec shape, pairing rejections, entry-root /
sequential-`let*`-spine placement with fail-closed boundary clearing, scalar
String artifact emission, collision rejection, and WCC payload carriage.
"""

from __future__ import annotations

import dataclasses
import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    compile_stage1_module,
    compile_stage3_entrypoint,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    NameExpr,
    ProviderResultExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.workflows import build_extern_environment

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/workflow_lisp/session_artifact"
FORM_PATH = ("workflow-lisp", "session-artifact-test")
_PROVIDER_EXTERNS = {"providers.session": "omp"}
_PROMPT_EXTERNS = {"prompts.session": {"input_file": "prompts/session.md"}}


def _syntax_module():
    return importlib.import_module("orchestrator.workflow_lisp.syntax")


def _expressions_module():
    return importlib.import_module("orchestrator.workflow_lisp.expressions")


def _session_spec_type():
    return getattr(_expressions_module(), "SessionArtifactSpec", None)


def _expression_syntax(source: str) -> SyntaxNode:
    parse_tree = read_sexpr_text(source, source_path="session_artifact_test.orc")
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="session_artifact_test.orc",
        form_path=FORM_PATH,
    )


def _session_source(clause: str = ":session-artifact omp_session", *, extra: str = "") -> str:
    return (
        "(provider-result providers.session "
        ":prompt prompts.session "
        ":inputs () "
        + extra
        + clause
        + " :returns String)"
    )


def _elaborate_session(source: str, *, target: str = "2.27"):
    return elaborate_expression(
        _expression_syntax(source),
        bound_names=frozenset({"providers.session", "prompts.session"}),
        target_dsl_version=target,
    )


def _elaborate_diagnostic_code(source: str, *, target: str = "2.27") -> str:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_session(source, target=target)
    return excinfo.value.diagnostics[0].code


def _type_env() -> FrontendTypeEnvironment:
    return FrontendTypeEnvironment.from_module(
        compile_stage1_module(
            REPO_ROOT / "tests/fixtures/workflow_lisp/valid/type_definitions.orc"
        )
    )


def _extern_environment():
    return build_extern_environment(
        provider_externs=_PROVIDER_EXTERNS,
        prompt_externs={"prompts.session": "prompts/session.md"},
    )


def _typecheck_session(
    source: str,
    *,
    session_artifact_allowed: bool = False,
    target: str = "2.27",
):
    expr = _elaborate_session(source, target=target)
    return typecheck_expression(
        expr,
        type_env=_type_env(),
        value_env={},
        extern_environment=_extern_environment(),
        session_artifact_allowed=session_artifact_allowed,
    )


def _provider_steps(value):
    found = []
    if isinstance(value, dict):
        if "provider" in value:
            found.append(value)
        for item in value.values():
            found.extend(_provider_steps(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_provider_steps(item))
    return found


def _write_prompt(workspace: Path) -> None:
    prompt_dir = workspace / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "session.md").write_text(
        "Return a session summary.\n",
        encoding="utf-8",
    )


def _compile_fixture(
    name: str,
    *,
    validate_shared: bool = False,
    provider_externs=None,
    lowering_route: str | None = None,
):
    return compile_stage3_entrypoint(
        FIXTURE_ROOT / name,
        source_roots=(FIXTURE_ROOT,),
        provider_externs=provider_externs or _PROVIDER_EXTERNS,
        prompt_externs=_PROMPT_EXTERNS,
        validate_shared=validate_shared,
        workspace_root=FIXTURE_ROOT,
        lowering_route=lowering_route,
    )


def _compile_source(
    tmp_path: Path,
    source: str,
    *,
    name: str,
    validate_shared: bool = False,
    provider_externs=None,
    prompt_externs=None,
):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    _write_prompt(tmp_path)
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "supervisor.md").write_text(
        "Return a steering directive.\n",
        encoding="utf-8",
    )
    return compile_stage3_entrypoint(
        path,
        source_roots=(tmp_path,),
        provider_externs=provider_externs or _PROVIDER_EXTERNS,
        prompt_externs=prompt_externs or _PROMPT_EXTERNS,
        validate_shared=validate_shared,
        workspace_root=tmp_path,
    )


def _workflow_mapping(result):
    return result.entry_result.lowered_workflows[0].authored_mapping


# --- Step 6.1: syntax and typecheck REDs -------------------------------------


def test_syntax_supported_versions_include_2_27() -> None:
    assert "2.27" in _syntax_module().SUPPORTED_TARGET_DSL_VERSIONS


def test_syntax_session_artifact_gate_admits_2_27_and_rejects_2_26() -> None:
    syntax = _syntax_module()
    assert syntax.SESSION_ARTIFACT_MIN_TARGET_DSL_VERSION == "2.27"
    helper = getattr(syntax, "target_dsl_supports_session_artifact", None)
    assert helper is not None
    assert helper("2.26") is False
    assert helper("2.27") is True
    assert helper("2.28") is True


def test_elaborate_rejects_session_artifact_at_2_26() -> None:
    assert (
        _elaborate_diagnostic_code(_session_source(), target="2.26")
        == "session_artifact_target_dsl_unsupported"
    )


def test_elaborate_admits_session_artifact_at_2_27_as_bare_symbol_declaration() -> None:
    expr = _elaborate_session(_session_source())
    assert isinstance(expr, ProviderResultExpr)
    spec_type = _session_spec_type()
    assert spec_type is not None
    spec = expr.session_artifact
    assert isinstance(spec, spec_type)
    assert spec.symbol == "omp_session"
    assert not isinstance(spec, NameExpr)
    assert isinstance(expr.session_artifact.span.start.path, str)


def test_session_artifact_spec_is_frozen_declaration() -> None:
    spec_type = _session_spec_type()
    assert spec_type is not None
    assert dataclasses.is_dataclass(spec_type)
    expr = _elaborate_session(_session_source())
    with pytest.raises(dataclasses.FrozenInstanceError):
        expr.session_artifact.symbol = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize(
    "clause",
    (
        ':session-artifact "abc"',
        ":session-artifact :keyword",
        ":session-artifact (nested)",
    ),
)
def test_elaborate_rejects_non_symbol_values(clause: str) -> None:
    assert (
        _elaborate_diagnostic_code(_session_source(clause=clause))
        == "session_artifact_value_invalid"
    )


def test_elaborate_rejects_dotted_symbol_value() -> None:
    assert (
        _elaborate_diagnostic_code(_session_source(clause=":session-artifact a.b"))
        == "session_artifact_value_invalid"
    )


def test_elaborate_rejects_missing_session_artifact_value() -> None:
    assert (
        _elaborate_diagnostic_code(
            "(provider-result providers.session :prompt prompts.session "
            ":inputs () :returns String :session-artifact)"
        )
        == "frontend_parse_error"
    )


def test_elaborate_rejects_duplicate_session_artifact_keyword() -> None:
    assert (
        _elaborate_diagnostic_code(
            _session_source(clause=":session-artifact a :session-artifact b")
        )
        == "frontend_parse_error"
    )


def test_elaborate_rejects_phased_delivery_pairing() -> None:
    assert (
        _elaborate_diagnostic_code(
            _session_source(extra=":delivery :phased ")
        )
        == "session_artifact_phased_delivery_invalid"
    )


def test_elaborate_rejects_materialization_attempts_pairing() -> None:
    assert (
        _elaborate_diagnostic_code(
            _session_source(extra=":materialization-attempts 2 ")
        )
        == "session_artifact_materialization_attempts_invalid"
    )


def test_typecheck_admits_session_artifact_with_entry_permission() -> None:
    typed = _typecheck_session(_session_source(), session_artifact_allowed=True)
    assert isinstance(typed.expr, ProviderResultExpr)
    assert typed.expr.session_artifact is not None
    assert typed.expr.session_artifact.symbol == "omp_session"


def test_typecheck_rejects_session_artifact_without_entry_permission() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_session(_session_source())
    assert excinfo.value.diagnostics[0].code == "session_artifact_placement_invalid"


def test_typecheck_clears_permission_at_branch_boundary() -> None:
    source = (
        "(if true "
        + _session_source()
        + " "
        + _session_source(clause=":session-artifact omp_session_2")
        + ")"
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_session(source, session_artifact_allowed=True)
    assert excinfo.value.diagnostics[0].code == "session_artifact_placement_invalid"


def test_traversal_does_not_visit_session_artifact_spec() -> None:
    expr = _elaborate_session(_session_source())
    assert isinstance(expr, ProviderResultExpr)
    spec_type = _session_spec_type()
    assert spec_type is not None
    children = list(iter_child_exprs(expr))
    assert not any(isinstance(child, spec_type) for child in children)


# --- Step 6.2: lowering and workflow-level REDs ------------------------------


def test_stage3_omitted_clause_remains_transient(tmp_path: Path) -> None:
    source = (
        "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.27\") "
        "(defmodule transient) (export run) "
        "(defworkflow run () -> String "
        "(provider-result providers.session :prompt prompts.session "
        ":inputs () :returns String)))"
    )
    result = _compile_source(tmp_path, source, name="transient.orc")
    mapping = _workflow_mapping(result)
    provider_step = _provider_steps(mapping)[0]
    assert "provider_session" not in provider_step
    assert "artifacts" not in mapping


def test_stage3_root_placement_emits_scalar_artifact_and_session_block() -> None:
    result = _compile_fixture("root.orc")
    mapping = _workflow_mapping(result)
    assert mapping["artifacts"] == {
        "omp_session": {"kind": "scalar", "type": "string"}
    }
    provider_step = _provider_steps(mapping)[0]
    assert provider_step["provider_session"] == {
        "mode": "fresh",
        "publish_artifact": "omp_session",
    }


def test_stage3_two_root_sequential_declarations_remain_distinct() -> None:
    result = _compile_fixture("root_two.orc")
    mapping = _workflow_mapping(result)
    assert mapping["artifacts"] == {
        "omp_session": {"kind": "scalar", "type": "string"},
        "omp_session_2": {"kind": "scalar", "type": "string"},
    }
    publishes = sorted(
        step["provider_session"]["publish_artifact"]
        for step in _provider_steps(mapping)
    )
    assert publishes == ["omp_session", "omp_session_2"]


def test_stage3_collision_rejected_before_registry_mutation() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_fixture("root_collision.orc")
    diagnostics = excinfo.value.diagnostics
    assert diagnostics[0].code == "session_artifact_collision"
    assert diagnostics[0].phase == "lowering"
    # The first declaration committed; the collision points at the SECOND
    # declaration (line 15) and no partial registry change is emitted.
    assert diagnostics[0].span.start.line == 15


def test_stage3_target_2_26_rejected() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_fixture("root_2_26.orc")
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_target_dsl_unsupported"
    )


def test_stage3_procedure_placement_rejected(tmp_path: Path) -> None:
    source = (
        "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.27\") "
        "(defmodule procedure) "
        "(defproc worker () -> String "
        ":effects ((uses-provider providers.session)) "
        "(provider-result providers.session :prompt prompts.session "
        ":inputs () :session-artifact omp_session :returns String)) "
        "(defworkflow run () -> String \"ok\"))"
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_source(tmp_path, source, name="procedure.orc")
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_placement_invalid"
    )


def test_stage3_phase_placement_rejected(tmp_path: Path) -> None:
    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.27")',
            "  (defmodule phase)",
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord RunCtx",
            "    (run-id RunId)",
            "    (state-root Path.state-root)",
            "    (artifact-root Path.artifact-root))",
            "  (defrecord PhaseCtx",
            "    (run RunCtx)",
            "    (phase-name Symbol)",
            "    (state-root Path.state-root)",
            "    (artifact-root Path.artifact-root))",
            "  (defrecord ReviewSurfaceResult",
            "    (report_path WorkReport))",
            "  (defworkflow run-review",
            "    ((phase-ctx PhaseCtx))",
            "    -> ReviewSurfaceResult",
            "    (with-phase phase-ctx implementation-review",
            "      (provider-result providers.session",
            "        :prompt prompts.session",
            "        :inputs ()",
            "        :session-artifact omp_session",
            "        :returns ReviewSurfaceResult))))",
        ]
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_source(tmp_path, source, name="phase.orc")
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_placement_invalid"
    )


def test_stage3_loop_placement_rejected(tmp_path: Path) -> None:
    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.27")',
            "  (defmodule loop)",
            "  (export gate)",
            "  (defworkflow gate () -> Bool",
            "    (if (loop/recur",
            "          :max 1",
            "          :state (loop-state (count Int 0))",
            "          :on-exhausted false",
            "          (fn (state)",
            "            (if (= state.count 0)",
            "                (done (provider-result providers.session",
            "                        :prompt prompts.session",
            "                        :inputs ()",
            "                        :session-artifact omp_session",
            "                        :returns Bool))",
            "                (continue (loop-state :like state :count 1)))))",
            "        (provider-result providers.session :prompt prompts.session :inputs () :returns Bool)",
            "        (provider-result providers.session :prompt prompts.session :inputs () :returns Bool))))",
        ]
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_source(tmp_path, source, name="loop.orc")
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_placement_invalid"
    )


def test_stage3_imported_workflow_placement_rejected(tmp_path: Path) -> None:
    (tmp_path / "lib.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.27")',
                "  (defmodule lib)",
                "  (export helper)",
                "  (defworkflow helper () -> String",
                "    (provider-result providers.session",
                "      :prompt prompts.session",
                "      :inputs ()",
                "      :session-artifact omp_session",
                "      :returns String)))",
            ]
        ),
        encoding="utf-8",
    )
    main_path = tmp_path / "main.orc"
    main_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.27")',
                "  (defmodule main)",
                "  (import lib :only (helper))",
                "  (export run)",
                "  (defworkflow run () -> String (helper)))",
            ]
        ),
        encoding="utf-8",
    )
    _write_prompt(tmp_path)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            main_path,
            source_roots=(tmp_path,),
            provider_externs=_PROVIDER_EXTERNS,
            prompt_externs=_PROMPT_EXTERNS,
            validate_shared=False,
            workspace_root=tmp_path,
        )
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_placement_invalid"
    )


def test_stage3_unsupported_provider_fails_existing_session_validator() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_fixture(
            "root.orc",
            validate_shared=True,
            provider_externs={"providers.session": "no-such-provider"},
        )
    message = excinfo.value.diagnostics[0].message
    assert "known provider template" in message


def test_stage3_wcc_route_lowers_session_artifact() -> None:
    result = _compile_fixture("root.orc", lowering_route="wcc_m4")
    mapping = _workflow_mapping(result)
    assert mapping["artifacts"] == {
        "omp_session": {"kind": "scalar", "type": "string"}
    }
    provider_step = _provider_steps(mapping)[0]
    assert provider_step["provider_session"] == {
        "mode": "fresh",
        "publish_artifact": "omp_session",
    }


def test_stage3_function_placement_rejected_by_purity_enforcement(
    tmp_path: Path,
) -> None:
    source = (
        "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.27\") "
        "(defmodule fn_placement) "
        "(defun helper () -> String "
        "(provider-result providers.session :prompt prompts.session "
        ":inputs () :session-artifact omp_session :returns String)) "
        "(defworkflow run () -> String \"ok\"))"
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_source(tmp_path, source, name="fn_placement.orc")
    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_stage3_if_branch_placement_rejected(tmp_path: Path) -> None:
    source = (
        "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.27\") "
        "(defmodule if_placement) "
        "(defworkflow run () -> String "
        "(if true "
        "(provider-result providers.session :prompt prompts.session "
        ":inputs () :session-artifact omp_session :returns String) "
        "(provider-result providers.session :prompt prompts.session "
        ":inputs () :returns String))))"
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_source(tmp_path, source, name="if_placement.orc")
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_placement_invalid"
    )


def test_stage3_resume_boundary_placement_rejected(tmp_path: Path) -> None:
    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.27")',
            "  (defmodule resume_placement)",
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defpath ResumePoint",
            "    :kind relpath",
            '    :under "state"',
            "    :must-exist true)",
            "  (defrecord RunCtx",
            "    (run-id RunId)",
            "    (state-root Path.state-root)",
            "    (artifact-root Path.artifact-root))",
            "  (defrecord PhaseCtx",
            "    (run RunCtx)",
            "    (phase-name Symbol)",
            "    (state-root Path.state-root)",
            "    (artifact-root Path.artifact-root))",
            "  (defrecord ReviewSurfaceResult",
            "    (report WorkReport))",
            "  (defworkflow run",
            "    ((phase-ctx PhaseCtx) (resume_from ResumePoint))",
            "    -> ReviewSurfaceResult",
            "    (with-phase phase-ctx checks",
            "      (resume-or-start checks",
            "        :ctx phase-ctx",
            "        :resume-from resume_from",
            "        :returns ReviewSurfaceResult",
            "        :start (provider-result providers.session",
            "          :prompt prompts.session",
            "          :inputs ()",
            "          :session-artifact omp_session",
            "          :returns ReviewSurfaceResult)))))",
        ]
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_source(tmp_path, source, name="resume_placement.orc")
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_placement_invalid"
    )


def test_stage3_live_provider_boundary_placement_rejected(
    tmp_path: Path,
) -> None:
    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.27")',
            "  (defmodule live_placement)",
            "  (defworkflow orchestrate () -> String",
            "    (with-live-providers",
            "      ((worker",
            "        (provider-result providers.session",
            "          :prompt prompts.session",
            "          :inputs ()",
            "          :session-artifact omp_session",
            "          :returns String))",
            "       (supervisor",
            "        (provider-result providers.supervisor",
            "          :prompt prompts.supervisor",
            "          :inputs ()",
            "          :returns ProviderSteeringDirective)",
            "        :observes worker))",
            "      worker)))",
        ]
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_source(
            tmp_path,
            source,
            name="live_placement.orc",
            provider_externs={
                "providers.session": "omp",
                "providers.supervisor": "omp",
            },
            prompt_externs={
                "prompts.session": {"input_file": "prompts/session.md"},
                "prompts.supervisor": {"input_file": "prompts/supervisor.md"},
            },
        )
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_placement_invalid"
    )


def test_stage3_sole_exported_entry_is_eligible_with_prior_private_helper(
    tmp_path: Path,
) -> None:
    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.27")',
            "  (defmodule entry_selection)",
            "  (export run)",
            "  (defworkflow helper () -> String",
            "    (provider-result providers.session",
            "      :prompt prompts.session",
            "      :inputs ()",
            "      :returns String))",
            "  (defworkflow run () -> String",
            "    (provider-result providers.session",
            "      :prompt prompts.session",
            "      :inputs ()",
            "      :session-artifact omp_session",
            "      :returns String)))",
        ]
    )
    result = _compile_source(tmp_path, source, name="entry_selection.orc")
    run_mapping = next(
        lowered.authored_mapping
        for lowered in result.entry_result.lowered_workflows
        if lowered.typed_workflow.definition.name.endswith("::run")
    )
    assert run_mapping["artifacts"] == {
        "omp_session": {"kind": "scalar", "type": "string"}
    }
    provider_step = next(
        step for step in run_mapping["steps"] if "provider" in step
    )
    assert provider_step["provider_session"] == {
        "mode": "fresh",
        "publish_artifact": "omp_session",
    }


def test_stage3_zero_exported_workflows_uses_legacy_fallback(
    tmp_path: Path,
) -> None:
    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.27")',
            "  (defmodule export_record_only)",
            "  (export SessionOutcome)",
            "  (defrecord SessionOutcome (summary String))",
            "  (defworkflow run () -> String",
            "    (provider-result providers.session",
            "      :prompt prompts.session",
            "      :inputs ()",
            "      :session-artifact omp_session",
            "      :returns String)))",
        ]
    )
    result = _compile_source(tmp_path, source, name="export_record_only.orc")
    mapping = _workflow_mapping(result)
    assert mapping["artifacts"] == {
        "omp_session": {"kind": "scalar", "type": "string"}
    }


def test_stage3_two_exports_never_get_implicit_selection(
    tmp_path: Path,
) -> None:
    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.27")',
            "  (defmodule two_exports)",
            "  (export bridge session_run)",
            "  (defrecord WorkflowInput (value String))",
            "  (defrecord WorkflowOutput (value String))",
            "  (defworkflow bridge",
            "    ((child WorkflowRef[WorkflowInput -> WorkflowOutput]))",
            '    -> String "ok")',
            "  (defworkflow session_run () -> String",
            "    (provider-result providers.session",
            "      :prompt prompts.session",
            "      :inputs ()",
            "      :session-artifact omp_session",
            "      :returns String)))",
        ]
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_source(tmp_path, source, name="two_exports.orc")
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_placement_invalid"
    )
    source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.27")',
            "  (defmodule entry_selection_reject)",
            "  (export run)",
            "  (defworkflow helper () -> String",
            "    (provider-result providers.session",
            "      :prompt prompts.session",
            "      :inputs ()",
            "      :session-artifact omp_session",
            "      :returns String))",
            "  (defworkflow run () -> String \"ok\"))",
        ]
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_source(
            tmp_path,
            source,
            name="entry_selection_reject.orc",
        )
    assert (
        excinfo.value.diagnostics[0].code
        == "session_artifact_placement_invalid"
    )
