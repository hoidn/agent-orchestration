from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.analysis import analyze_wcc_body
from orchestrator.workflow_lisp.wcc.route import (
    DEFAULT_LOWERING_ROUTE,
    LoweringRoute,
    normalize_lowering_route,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
from orchestrator.workflow_lisp.wcc.model import (
    WCC_M4_ROUTE_SCHEMA_VERSION,
    WccHalt,
    WccIdentityFactory,
    WccJoinParam,
    WccLiteralAtom,
    WccLet,
    WccLoopContinue,
    WccLoopDone,
    WccLoopRole,
    WccNameAtom,
    WccPureOp,
    WccRecJoin,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
MODULE_FIXTURES = FIXTURES / "modules" / "valid"
CHARACTERIZATION_SOURCES = FIXTURES / "characterization" / "sources"
PURE_EXPR_LOOP_COUNTER = VALID_FIXTURES / "pure_expr_loop_counter.orc"
PURE_EXPR_SELECTOR_PROJECTION = VALID_FIXTURES / "pure_expr_selector_action_projection.orc"


def _span() -> SourceSpan:
    position = SourcePosition(path="tests/fixtures/workflow_lisp/valid/loop_recur_minimal.orc", line=1, column=1, offset=0)
    return SourceSpan(start=position, end=position)


def _assert_diagnostic_code(
    excinfo: pytest.ExceptionInfo[LispFrontendCompileError],
    code: str,
) -> None:
    assert excinfo.value.diagnostics
    assert excinfo.value.diagnostics[0].code == code


def _compile_review_loop_wcc_m4(path: Path, *, tmp_path: Path):
    return compile_stage3_module(
        path,
        provider_externs={
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
            "providers.execute": "fake-execute",
            "providers.checks": "fake-checks",
        },
        prompt_externs={
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.checks": "prompts/implementation/checks.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1"),
            ),
        },
        lowering_route="wcc_m4",
        validate_shared=True,
        workspace_root=tmp_path,
    )


def _compile_fixture(path: Path, *, tmp_path: Path):
    result = compile_stage3_module(
        path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )
    type_env = FrontendTypeEnvironment.from_module(result.module)
    workflows = {workflow.definition.name: workflow for workflow in result.typed_workflows}
    workflow_return_types = {
        workflow.definition.name: workflow.signature.return_type_ref
        for workflow in result.typed_workflows
    }
    procedure_return_types = {
        procedure.definition.name: procedure.signature.return_type_ref
        for procedure in result.typed_procedures
    }
    return type_env, workflows, workflow_return_types, procedure_return_types


def _skip_lets(body):
    current = body
    while isinstance(current, WccLet):
        current = current.body
    return current


def _walk_steps(steps):
    for step in steps:
        yield step
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            nested = repeat_until.get("steps", [])
            if isinstance(nested, list):
                yield from _walk_steps(nested)
        branch = step.get("if")
        if isinstance(branch, dict):
            for key in ("then", "else"):
                case = branch.get(key)
                if isinstance(case, dict):
                    nested = case.get("steps", [])
                    if isinstance(nested, list):
                        yield from _walk_steps(nested)
        match_block = step.get("match")
        if isinstance(match_block, dict):
            cases = match_block.get("cases", {})
            if isinstance(cases, dict):
                for case in cases.values():
                    if isinstance(case, dict):
                        nested = case.get("steps", [])
                        if isinstance(nested, list):
                            yield from _walk_steps(nested)


def test_normalize_lowering_route_accepts_wcc_m4() -> None:
    assert normalize_lowering_route("wcc_m4") is LoweringRoute.WCC_M4
    assert normalize_lowering_route(LoweringRoute.WCC_M4) is LoweringRoute.WCC_M4


def test_default_lowering_route_is_wcc_m4_after_m5_flip() -> None:
    assert DEFAULT_LOWERING_ROUTE is LoweringRoute.WCC_M4


def test_wcc_m4_route_validator_accepts_loop_recur_fixture(tmp_path: Path) -> None:
    try:
        compile_stage3_module(
            VALID_FIXTURES / "loop_recur_minimal.orc",
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m4",
        )
    except LispFrontendCompileError as exc:
        assert exc.diagnostics[0].code != "wcc_lowering_route_unsupported"
    except TypeError as exc:
        assert "LoopRecurExpr" in str(exc)
    except AttributeError as exc:
        assert "WccRecJoin" in str(exc)


def test_wcc_m3_still_rejects_loop_recur_fixture(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            VALID_FIXTURES / "loop_recur_minimal.orc",
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m3",
        )

    _assert_diagnostic_code(excinfo, "wcc_lowering_route_unsupported")


def test_wcc_m4_accepts_generic_imported_workflow_call_module_graph(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        MODULE_FIXTURES / "imported_loop_recur_on_exhausted" / "entry.orc",
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    assert result.lowered_workflows


def test_wcc_m4_pure_op_elaboration_preserves_operation_metadata(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        PURE_EXPR_SELECTOR_PROJECTION,
        tmp_path=tmp_path,
    )
    typed_workflow = workflows["orchestrate"]

    body = elaborate_typed_workflow(
        typed_workflow,
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )

    assert isinstance(body, WccHalt)
    assert isinstance(body.result, WccPureOp)
    assert body.result.operator == "record-update"
    assert body.result.metadata.node_id.startswith("wcc-node:wcc_m4:")
    assert body.result.metadata.scope_id.startswith("wcc-scope:wcc_m4:")


def test_wcc_m4_pure_projection_runtime_regions_emit_visible_projection_steps(tmp_path: Path) -> None:
    result = compile_stage3_module(
        PURE_EXPR_LOOP_COUNTER,
        provider_externs={},
        prompt_externs={},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    all_steps = list(_walk_steps(result.lowered_workflows[0].authored_mapping["steps"]))
    pure_projection_steps = [step for step in all_steps if "pure_projection" in step]

    assert pure_projection_steps
    assert any(step["name"].endswith("__condition") for step in pure_projection_steps)
    assert all(step["output_bundle"]["fields"] for step in pure_projection_steps)


def test_wcc_m4_constant_folds_literal_only_pure_expression_without_projection_step(tmp_path: Path) -> None:
    module_path = tmp_path / "literal_fold.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule literal_fold)",
                "  (export fold)",
                "  (defworkflow fold () -> Int",
                "    (+ 1 (+ 2 3)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={},
        prompt_externs={},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    steps = list(_walk_steps(result.lowered_workflows[0].authored_mapping["steps"]))

    assert not any("pure_projection" in step for step in steps)
    materialize = next(step for step in steps if "materialize_artifacts" in step)
    assert materialize["materialize_artifacts"]["values"][0]["source"]["literal"] == 6


def test_wcc_m4_rejects_runtime_proc_ref_in_loop_state(tmp_path: Path) -> None:
    module_path = tmp_path / "proc_ref_loop_state.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Output",
                "    (value String))",
                "  (defproc echo",
                "    ((value String))",
                "    -> String",
                "    :effects ()",
                "    :lowering inline",
                "    value)",
                "  (defworkflow carry-proc-ref () -> Output",
                "    (loop/recur",
                "      :max 1",
                "      :state (proc-ref echo)",
                "      (fn (state)",
                '        (done (record Output :value "unreachable"))))))',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            module_path,
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m4",
        )

    assert excinfo.value.diagnostics[0].code in {
        "wcc_lowering_route_unsupported",
        "proc_ref_runtime_transport_forbidden",
    }


def test_wcc_m4_model_instantiates_rec_join_loop_nodes() -> None:
    string_type = PrimitiveTypeRef(name="String")
    int_type = PrimitiveTypeRef(name="Int")
    bool_type = PrimitiveTypeRef(name="Bool")
    span = _span()
    factory = WccIdentityFactory(
        owner_name="loop-recur-minimal",
        lexical_owner_chain=("workflow", "loop"),
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    literal = WccLiteralAtom(
        metadata=factory.atom_metadata(
            role="literal:seed",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow"),
        ),
        value="seed",
        literal_kind="string",
    )
    done = WccLoopDone(
        metadata=factory.body_metadata(
            role="loop:done",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow"),
        ),
        result=literal,
    )
    continue_node = WccLoopContinue(
        metadata=factory.body_metadata(
            role="loop:continue",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow"),
        ),
        target_name="review_loop",
        state_args=(literal,),
    )
    exhaustion = WccHalt(
        metadata=factory.body_metadata(
            role="loop:exhaustion",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow"),
        ),
        result=literal,
    )
    rec_join = WccRecJoin(
        metadata=factory.body_metadata(
            role="rec-join:review_loop",
            type_ref=string_type,
            source_span=span,
            form_path=("workflow-lisp", "defworkflow"),
        ),
        loop_name="review_loop",
        params=(WccJoinParam(name="state", type_ref=string_type),),
        budget=WccLiteralAtom(
            metadata=factory.atom_metadata(
                role="literal:budget",
                type_ref=int_type,
                source_span=span,
                form_path=("workflow-lisp", "defworkflow"),
            ),
            value=3,
            literal_kind="int",
        ),
        body=done,
        exhaustion=exhaustion,
    )

    assert WCC_M4_ROUTE_SCHEMA_VERSION == "wcc_m4"
    assert rec_join.metadata.node_id.startswith("wcc-node:wcc_m4:")
    assert rec_join.loop_name == "review_loop"
    assert rec_join.params == (WccJoinParam(name="state", type_ref=string_type),)
    assert rec_join.budget.literal_kind == "int"
    assert rec_join.body is done
    assert rec_join.exhaustion is exhaustion
    assert rec_join.roles == WccLoopRole()
    assert rec_join.roles.frame_role == "loop_frame"
    assert rec_join.roles.iteration_role == "loop_iteration"
    assert continue_node.target_name == "review_loop"
    assert continue_node.state_args == (literal,)
    assert continue_node.metadata.type_ref == string_type
    assert bool_type.name == "Bool"


def test_wcc_m4_elaborates_top_level_loop_recur_to_rec_join(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        VALID_FIXTURES / "loop_recur_minimal.orc",
        tmp_path=tmp_path,
    )

    body = elaborate_typed_workflow(
        workflows["loop-recur-minimal"],
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )

    rec_join = _skip_lets(body)
    assert isinstance(rec_join, WccRecJoin)
    assert rec_join.loop_name.startswith("__wcc_loop_state_")
    assert rec_join.params == (WccJoinParam(name="state", type_ref=rec_join.params[0].type_ref),)
    assert isinstance(rec_join.budget, WccLiteralAtom)
    assert rec_join.budget.value == 3
    assert _contains_loop_done(rec_join.body)
    assert _contains_loop_continue(rec_join.body)
    assert isinstance(rec_join.exhaustion, type(None))


def test_wcc_m4_elaborates_continue_done_and_exhaustion(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        VALID_FIXTURES / "loop_recur_on_exhausted_union.orc",
        tmp_path=tmp_path,
    )

    body = elaborate_typed_workflow(
        next(iter(workflows.values())),
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )

    rec_join = _skip_lets(body)
    assert isinstance(rec_join, WccRecJoin)
    assert rec_join.exhaustion is not None
    assert _contains_loop_done(rec_join.body)
    assert _contains_loop_continue(rec_join.body)


def _contains_loop_continue(body) -> bool:
    if isinstance(body, WccLoopContinue):
        assert body.target_name
        assert all(isinstance(arg, WccNameAtom | WccLiteralAtom) or hasattr(arg, "metadata") for arg in body.state_args)
        return True
    if isinstance(body, WccLet):
        return _contains_loop_continue(body.body)
    if hasattr(body, "arms"):
        return any(_contains_loop_continue(arm.body) for arm in body.arms)
    return False


def _contains_loop_done(body) -> bool:
    if isinstance(body, WccLoopDone):
        return True
    if isinstance(body, WccLet):
        return _contains_loop_done(body.body)
    if hasattr(body, "arms"):
        return any(_contains_loop_done(arm.body) for arm in body.arms)
    return False


def _first_rec_join(body) -> WccRecJoin:
    current = body
    while isinstance(current, WccLet):
        current = current.body
    assert isinstance(current, WccRecJoin)
    return current


def _loop_continue_nodes(body) -> list[WccLoopContinue]:
    found: list[WccLoopContinue] = []
    if isinstance(body, WccLoopContinue):
        return [body]
    if isinstance(body, WccLet):
        return _loop_continue_nodes(body.body)
    if hasattr(body, "arms"):
        for arm in body.arms:
            found.extend(_loop_continue_nodes(arm.body))
    return found


def _loop_done_nodes(body) -> list[WccLoopDone]:
    found: list[WccLoopDone] = []
    if isinstance(body, WccLoopDone):
        return [body]
    if isinstance(body, WccLet):
        return _loop_done_nodes(body.body)
    if hasattr(body, "arms"):
        for arm in body.arms:
            found.extend(_loop_done_nodes(arm.body))
    return found


def test_wcc_m4_anf_atomizes_loop_budget_continue_done_and_exhaustion(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        VALID_FIXTURES / "loop_recur_on_exhausted_union.orc",
        tmp_path=tmp_path,
    )
    body = elaborate_typed_workflow(
        next(iter(workflows.values())),
        type_env=type_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )

    normalized = normalize_wcc_body_to_anf(body)
    rec_join = _first_rec_join(normalized)

    assert isinstance(rec_join.budget, WccLiteralAtom | WccNameAtom)
    assert all(
        isinstance(arg, WccLiteralAtom | WccNameAtom)
        for continue_node in _loop_continue_nodes(rec_join.body)
        for arg in continue_node.state_args
    )
    assert all(isinstance(done.result, WccLiteralAtom | WccNameAtom) for done in _loop_done_nodes(rec_join.body))
    assert rec_join.exhaustion is not None
    assert isinstance(_skip_lets(rec_join.exhaustion), WccHalt)
    assert isinstance(_skip_lets(rec_join.exhaustion).result, WccLiteralAtom | WccNameAtom)


def test_wcc_m4_analysis_records_loop_site_and_nested_case_scopes(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        VALID_FIXTURES / "loop_recur_minimal.orc",
        tmp_path=tmp_path,
    )
    body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow(
            workflows["loop-recur-minimal"],
            type_env=type_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
        )
    )

    analysis = analyze_wcc_body(body)

    assert len(analysis.loop_sites) == 1
    loop_site = analysis.loop_sites[0]
    assert loop_site.loop_name.startswith("__wcc_loop_state_")
    assert tuple(param.name for param in loop_site.state_params) == ("state",)
    assert loop_site.roles.frame_role == "loop_frame"
    assert loop_site.roles.iteration_role == "loop_iteration"
    assert loop_site.terminal_type is not None
    assert {"COMPLETED", "BLOCKED"}.issubset({scope.variant_name for scope in analysis.arm_scopes})


def test_wcc_m4_defunctionalizes_loop_recur_to_repeat_until(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "loop_recur_minimal.orc",
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    lowered = result.lowered_workflows[0].authored_mapping
    assert any("repeat_until" in step for step in lowered["steps"])


def test_wcc_m4_hoists_effectful_match_arm_steps_by_structure_not_workflow_name(tmp_path: Path) -> None:
    module_path = tmp_path / "generic_effectful_match_arm_route.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule generic_effectful_match_arm_route)",
                "  (export run)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion Attempt",
                "    (COMPLETED",
                "      (report WorkReport))",
                "    (BLOCKED",
                "      (reason String)",
                "      (report WorkReport)))",
                "  (defrecord Followup",
                "    (ok Bool)",
                "    (report WorkReport))",
                "  (defunion RouteResult",
                "    (COMPLETED",
                "      (report WorkReport))",
                "    (BLOCKED",
                "      (reason String)",
                "      (report WorkReport)))",
                "  (defworkflow run",
                "    ((seed_report WorkReport))",
                "    -> RouteResult",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (seed_report)",
                "               :returns Attempt)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                "         (let* ((followup",
                "                  (provider-result providers.execute",
                "                    :prompt prompts.implementation.execute",
                "                    :inputs (completed.report)",
                "                    :returns Followup)))",
                "           (if followup.ok",
                "             (variant RouteResult COMPLETED",
                "               :report followup.report)",
                "             (variant RouteResult COMPLETED",
                "               :report completed.report))))",
                "        ((BLOCKED blocked)",
                "         (let* ((followup",
                "                  (provider-result providers.execute",
                "                    :prompt prompts.implementation.execute",
                "                    :inputs (blocked.report)",
                "                    :returns Followup)))",
                "           (if followup.ok",
                "             (variant RouteResult BLOCKED",
                "               :reason blocked.reason",
                "               :report followup.report)",
                "             (variant RouteResult BLOCKED",
                '               :reason "fallback"',
                "               :report blocked.report))))))",
                ")",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    steps = result.lowered_workflows[0].authored_mapping["steps"]
    match_index = next(index for index, step in enumerate(steps) if "match" in step)
    hoisted_provider_steps = [
        step
        for step in steps[:match_index]
        if step.get("provider") == "fake" and step["name"].endswith("__followup")
    ]

    assert len(hoisted_provider_steps) == 2
    assert {step["when"]["compare"]["right"] for step in hoisted_provider_steps} == {
        "COMPLETED",
        "BLOCKED",
    }
    assert all("requires_variant" not in step for step in hoisted_provider_steps)


def test_wcc_m4_loop_emitter_does_not_call_legacy_loop_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from orchestrator.workflow_lisp.lowering import control_loops

    def fail_legacy_adapter(*args, **kwargs):
        raise AssertionError("WCC M4 must not call legacy loop adapter")

    monkeypatch.setattr(control_loops, "_control_lower_loop_recur_impl", fail_legacy_adapter)

    result = compile_stage3_module(
        VALID_FIXTURES / "loop_recur_minimal.orc",
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    assert any("repeat_until" in step for step in result.lowered_workflows[0].authored_mapping["steps"])


def test_wcc_m4_loop_emitter_does_not_rebuild_frontend_loop_recur(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp.lowering import control_loops
    from orchestrator.workflow_lisp.wcc import defunctionalize

    def fail_frontend_loop_recur_adapter(*args, **kwargs):
        raise AssertionError("WCC M4 must not rebuild LoopRecurExpr for repeat_until emission")

    monkeypatch.setattr(
        control_loops,
        "_emit_repeat_until_from_loop_recur_expr",
        fail_frontend_loop_recur_adapter,
    )
    monkeypatch.setattr(
        defunctionalize,
        "_emit_repeat_until_from_loop_recur_expr",
        fail_frontend_loop_recur_adapter,
        raising=False,
    )

    result = compile_stage3_module(
        VALID_FIXTURES / "loop_recur_minimal.orc",
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    assert any("repeat_until" in step for step in result.lowered_workflows[0].authored_mapping["steps"])


def test_wcc_m4_defunctionalizes_typed_exhaustion_to_repeat_until_outputs(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_FIXTURES / "loop_recur_on_exhausted_union.orc",
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    repeat_step = next(
        step for step in result.lowered_workflows[0].authored_mapping["steps"] if "repeat_until" in step
    )
    on_exhausted = repeat_step["repeat_until"]["on_exhausted"]["outputs"]
    assert on_exhausted["result__variant"] == "EXHAUSTED"
    assert on_exhausted["result__reason"] == "max_iterations_reached"


def test_wcc_m4_exports_specialized_stdlib_review_loop_terminal_value(tmp_path: Path) -> None:
    result = _compile_review_loop_wcc_m4(
        VALID_FIXTURES / "phase_stdlib_review_loop.orc",
        tmp_path=tmp_path,
    )

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::review-revise-loop-demo")
    ).authored_mapping

    assert any("repeat_until" in step for step in lowered["steps"])
    assert set(lowered["outputs"]) >= {"return__variant", "return__review_report", "return__last_review_report"}


def test_wcc_m4_full_fixture_exports_terminal_review_decision(tmp_path: Path) -> None:
    result = _compile_review_loop_wcc_m4(
        CHARACTERIZATION_SOURCES / "wcc_m4_implementation_phase_full_fixture.orc",
        tmp_path=tmp_path,
    )

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::run")
    ).authored_mapping

    def walk_steps(steps):
        for step in steps:
            yield step
            if "repeat_until" in step:
                yield from walk_steps(step["repeat_until"].get("steps", []))
            if "match" in step:
                for case in step["match"].get("cases", {}).values():
                    yield from walk_steps(case.get("steps", []))

    all_steps = list(walk_steps(lowered["steps"]))
    assert any("match" in step for step in lowered["steps"])
    assert any(step.get("command", [])[:2] == ["python", "scripts/run_checks.py"] for step in all_steps)
    assert any("repeat_until" in step for step in all_steps)
    assert set(lowered["outputs"]) >= {"return__variant", "return__review_report", "return__findings__items_path"}
