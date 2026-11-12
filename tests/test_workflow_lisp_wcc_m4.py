from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.analysis import analyze_wcc_body

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
PURE_EXPR_SELECTOR_PROJECTION = FIXTURES / "current_wcc" / "pure_expr_selector_action_projection.orc"
LEXICAL_CHECKPOINT_FIXTURE = VALID_FIXTURES / "lexical_checkpoint_shadow_points.orc"
LEXICAL_POLICY_FIXTURE = VALID_FIXTURES / "lexical_checkpoint_effect_policies.orc"
LEXICAL_RESTORE_FIXTURE = VALID_FIXTURES / "lexical_checkpoint_restore_regions.orc"
CERTIFIED_ADAPTER_FIXTURE = VALID_FIXTURES / "certified_adapter_call.orc"


def _span() -> SourceSpan:
    position = SourcePosition(path="tests/fixtures/workflow_lisp/valid/loop_recur_minimal.orc", line=1, column=1, offset=0)
    return SourceSpan(start=position, end=position)


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












def test_wcc_m4_accepts_imported_procedure_calling_owner_module_workflow(tmp_path: Path) -> None:
    package_dir = tmp_path / "pkg"
    package_dir.mkdir(parents=True)
    (package_dir / "helpers.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defmodule pkg/helpers)",
                "  (export WorkReport Outcome route)",
                '  (defpath WorkReport :kind relpath :under "artifacts/work" :must-exist true)',
                "  (defunion Outcome",
                "    (DONE",
                "      (summary-path WorkReport)))",
                "  (defworkflow finalize",
                "    ((summary-path WorkReport))",
                "    -> Outcome",
                "    (variant Outcome DONE",
                "      :summary-path summary-path))",
                "  (defproc route",
                "    ((summary-path WorkReport))",
                "    -> Outcome",
                "    (call finalize",
                "      :summary-path summary-path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    entry_path = package_dir / "entry.orc"
    entry_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defmodule pkg/entry)",
                "  (import pkg/helpers :only (WorkReport Outcome route))",
                "  (export drain)",
                "  (defworkflow drain",
                "    ((summary-path WorkReport))",
                "    -> Outcome",
                "    (route summary-path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(tmp_path,),
        validate_shared=False,
        workspace_root=tmp_path,

        entry_workflow="drain",
    )

    workflows = result.entry_result.typed_program.workflows
    assert "pkg/helpers::finalize" in workflows
    assert "pkg/entry::drain" in workflows




def test_wcc_m4_accepts_generic_imported_workflow_call_module_graph(
    tmp_path: Path,
) -> None:
    result = compile_stage3_module(
        MODULE_FIXTURES / "imported_loop_recur_on_exhausted" / "entry.orc",
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,

    )

    assert result.typed_workflows


def test_wcc_m4_pure_op_elaboration_preserves_operation_metadata(tmp_path: Path) -> None:
    type_env, workflows, workflow_return_types, procedure_return_types = _compile_fixture(
        PURE_EXPR_SELECTOR_PROJECTION,
        tmp_path=tmp_path,
    )
    typed_workflow = workflows["pure_expr_selector_action_projection::orchestrate"]

    body = elaborate_typed_workflow_body(
        typed_workflow.typed_body,
        owner_name=typed_workflow.definition.name,
        value_env=dict(typed_workflow.signature.params),
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






def test_wcc_m4_rejects_runtime_proc_ref_in_loop_state(tmp_path: Path) -> None:
    module_path = tmp_path / "proc_ref_loop_state.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.40")',
                "  (defrecord Output",
                "    (value String))",
                "  (defproc echo",
                "    ((value String))",
                "    -> String",
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

        )

    assert excinfo.value.diagnostics[0].code == "proc_ref_runtime_transport_forbidden"


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
        FIXTURES / "current_wcc" / "loop_recur_minimal.orc",
        tmp_path=tmp_path,
    )

    body = elaborate_typed_workflow_body(
        workflows["entry::loop-recur-minimal"].typed_body,
        owner_name=workflows["entry::loop-recur-minimal"].definition.name,
        value_env=dict(workflows["entry::loop-recur-minimal"].signature.params),
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
        FIXTURES / "current_wcc" / "loop_recur_on_exhausted_union.orc",
        tmp_path=tmp_path,
    )

    workflow = next(iter(workflows.values()))
    body = elaborate_typed_workflow_body(
        workflow.typed_body,
        owner_name=workflow.definition.name,
        value_env=dict(workflow.signature.params),
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
        FIXTURES / "current_wcc" / "loop_recur_on_exhausted_union.orc",
        tmp_path=tmp_path,
    )
    workflow = next(iter(workflows.values()))
    body = elaborate_typed_workflow_body(
        workflow.typed_body,
        owner_name=workflow.definition.name,
        value_env=dict(workflow.signature.params),
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
        FIXTURES / "current_wcc" / "loop_recur_minimal.orc",
        tmp_path=tmp_path,
    )
    body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            workflows["entry::loop-recur-minimal"].typed_body,
            owner_name=workflows["entry::loop-recur-minimal"].definition.name,
            value_env=dict(workflows["entry::loop-recur-minimal"].signature.params),
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
