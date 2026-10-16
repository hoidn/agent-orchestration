from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import orchestrator.workflow_lisp.compiler as compiler_module
from orchestrator.workflow_lisp.procedure_specialization import _resolve_procedure_lowering
import orchestrator.workflow_lisp.wcc.elaborate as wcc_elaborate_module
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
)
from orchestrator.workflow_lisp.definitions import (
    elaborate_definition_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.procedures import (
    build_procedure_catalog,
    elaborate_procedure_definitions,
)
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import (
    ExternalToolBinding,
    build_command_boundary_environment,
    build_extern_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
)
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.analysis import analyze_wcc_body
from orchestrator.workflow_lisp.wcc import analysis as wcc_analysis
from orchestrator.workflow_lisp.wcc import model as wcc_model

from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
from orchestrator.workflow_lisp.wcc.model import (
    WCC_M4_ROUTE_SCHEMA_VERSION,
    WccCall,
    WccHalt,
    WccIdentityFactory,
    WccJoinParam,
    WccLiteralAtom,
    WccLet,
    WccLoopContinue,
    WccLoopDone,
    WccLoopRole,
    WccNameAtom,
    WccPerform,
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


def _assert_diagnostic_code(
    excinfo: pytest.ExceptionInfo[LispFrontendCompileError],
    code: str,
) -> None:
    assert excinfo.value.diagnostics
    assert excinfo.value.diagnostics[0].code == code






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
                '  (:target-dsl "2.35")',
                "  (defmodule pkg/helpers)",
                "  (import std/resource :only (WorkReport))",
                "  (export Outcome route)",
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
                "    :effects ((calls-workflow pkg/helpers::finalize))",
                "    :lowering inline",
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
                '  (:target-dsl "2.35")',
                "  (defmodule pkg/entry)",
                "  (import std/resource :only (WorkReport))",
                "  (import pkg/helpers :only (Outcome route))",
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
                '  (:target-dsl "2.35")',
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


_SUPERVISION_FORM_PATH = ("workflow-lisp", "defworkflow", "supervise")
_SUPERVISION_STRING = PrimitiveTypeRef(name="String")


def _supervision_metadata(factory: WccIdentityFactory, role: str, *, kind: str = "body"):
    return getattr(factory, f"{kind}_metadata")(
        role=role,
        type_ref=_SUPERVISION_STRING,
        source_span=_span(),
        form_path=_SUPERVISION_FORM_PATH,
    )


def _supervision_name(factory: WccIdentityFactory, name: str) -> WccNameAtom:
    return WccNameAtom(
        metadata=_supervision_metadata(factory, f"name:{name}", kind="atom"),
        name=name,
    )


def _supervision_perform(
    factory: WccIdentityFactory,
    role: str,
    *,
    perform_kind: str = "provider_result",
) -> WccPerform:
    return WccPerform(
        metadata=_supervision_metadata(factory, role, kind="value"),
        perform_kind=perform_kind,
        target_name=f"providers.{role}",
        prompt_name=f"prompts.{role}" if perform_kind == "provider_result" else None,
        positional_args=(),
        keyword_args=(),
        returns_type_name="String",
    )


def _supervision_member(
    factory: WccIdentityFactory,
    name: str,
    values: tuple[object, ...],
    *,
    result_name: str | None = None,
):
    result_names = tuple(f"{name}_{index}" for index in range(len(values)))
    body = WccHalt(
        metadata=_supervision_metadata(factory, f"{name}:halt"),
        result=_supervision_name(
            factory,
            result_name or result_names[-1],
        ),
    )
    for result_name, value in reversed(tuple(zip(result_names, values, strict=True))):
        body = WccLet(
            metadata=_supervision_metadata(factory, f"{name}:let:{result_name}"),
            bound_name=result_name,
            bound_type_ref=_SUPERVISION_STRING,
            bound_value=value,
            body=body,
        )
    return getattr(wcc_model, "WccProviderSupervisionMember")(
        metadata=_supervision_metadata(factory, f"member:{name}", kind="value"),
        binding_metadata=_supervision_metadata(
            factory,
            f"member-binding:{name}",
            kind="value",
        ),
        binding_name=name,
        normalized_body=body,
    )


def _synthetic_provider_supervision_body(*, defect: str | None = None):
    factory = WccIdentityFactory(
        owner_name="supervise",
        lexical_owner_chain=("workflow", "provider-supervision"),
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    worker_values: tuple[object, ...] = (_supervision_perform(factory, "worker"),)
    if defect == "residual_call":
        worker_values = (
            WccCall(
                metadata=_supervision_metadata(factory, "call:worker", kind="value"),
                callee_name="worker",
                specialized_callee_name="worker",
                args=(),
            ),
        )
    elif defect == "residual_call_with_forward_arg":
        worker_values = (
            WccCall(
                metadata=_supervision_metadata(
                    factory,
                    "call:worker",
                    kind="value",
                ),
                callee_name="worker",
                specialized_callee_name="worker",
                args=(
                    _supervision_name(factory, "worker_1"),
                ),
            ),
            WccLiteralAtom(
                metadata=_supervision_metadata(
                    factory,
                    "worker:later-pure",
                    kind="atom",
                ),
                value="later",
                literal_kind="string",
            ),
        )
    elif defect == "second_perform":
        worker_values += (_supervision_perform(factory, "worker-again"),)
    elif defect == "non_provider_perform":
        worker_values = (
            _supervision_perform(factory, "worker-command", perform_kind="command_result"),
        )
    elif defect == "pure_refs_later_provider":
        worker_values = (
            _supervision_name(factory, "worker_1"),
            replace(
                _supervision_perform(factory, "worker"),
                positional_args=(
                    _supervision_name(factory, "worker_0"),
                ),
            ),
        )
    elif defect == "provider_refs_later_pure":
        worker_values = (
            replace(
                _supervision_perform(factory, "worker"),
                positional_args=(
                    _supervision_name(factory, "worker_1"),
                ),
            ),
            WccLiteralAtom(
                metadata=_supervision_metadata(
                    factory,
                    "worker:later-pure",
                    kind="atom",
                ),
                value="later",
                literal_kind="string",
            ),
        )

    settlement = WccHalt(
        metadata=_supervision_metadata(factory, "settlement:halt"),
        result=_supervision_name(factory, "worker"),
    )
    if defect == "effectful_settlement":
        settlement = WccLet(
            metadata=_supervision_metadata(factory, "settlement:let"),
            bound_name="settlement_effect",
            bound_type_ref=_SUPERVISION_STRING,
            bound_value=_supervision_perform(factory, "settlement"),
            body=settlement,
        )
    group = getattr(wcc_model, "WccProviderSupervision")(
        metadata=_supervision_metadata(factory, "provider-supervision", kind="value"),
        observation_metadata=_supervision_metadata(
            factory,
            "provider-supervision:observation",
            kind="value",
        ),
        members=(
            _supervision_member(
                factory,
                "worker",
                worker_values,
                result_name=(
                    "worker_0"
                    if defect == "provider_refs_later_pure"
                    else None
                ),
            ),
            _supervision_member(
                factory,
                "supervisor",
                (_supervision_perform(factory, "supervisor"),),
            ),
        ),
        supervisor_name="supervisor",
        worker_name="worker",
        settlement_body=settlement,
    )
    return WccLet(
        metadata=_supervision_metadata(factory, "let:supervised"),
        bound_name="supervised",
        bound_type_ref=_SUPERVISION_STRING,
        bound_value=group,
        body=WccHalt(
            metadata=_supervision_metadata(factory, "halt:supervised"),
            result=_supervision_name(factory, "supervised"),
        ),
    )


def test_wcc_m4_analysis_accepts_canonical_provider_supervision_members() -> None:
    analysis = analyze_wcc_body(_synthetic_provider_supervision_body())

    assert analysis.arm_scopes == ()
    assert analysis.loop_sites == ()


@pytest.mark.parametrize(
    ("defect", "expected_code"),
    (
        ("residual_call", "provider_supervision_member_ineligible"),
        ("second_perform", "provider_supervision_member_ineligible"),
        ("non_provider_perform", "provider_supervision_member_ineligible"),
        ("pure_refs_later_provider", "provider_supervision_member_ineligible"),
        ("provider_refs_later_pure", "provider_supervision_member_ineligible"),
        ("effectful_settlement", "provider_supervision_settlement_effectful"),
    ),
)
def test_wcc_m4_analysis_rejects_noncanonical_provider_supervision(
    defect: str,
    expected_code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        analyze_wcc_body(_synthetic_provider_supervision_body(defect=defect))

    _assert_diagnostic_code(excinfo, expected_code)


def test_wcc_m4_supervision_residual_call_diagnostic_precedes_forward_arg(
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        analyze_wcc_body(
            _synthetic_provider_supervision_body(
                defect="residual_call_with_forward_arg",
            )
        )

    _assert_diagnostic_code(
        excinfo,
        "provider_supervision_member_ineligible",
    )
    assert "residual procedure call" in (
        excinfo.value.diagnostics[0].message
    )


_PEER_GROUP_FORM_PATH = (
    "workflow-lisp",
    "defworkflow",
    "with-live-provider-peers",
)


def _peer_group_metadata(
    factory: WccIdentityFactory,
    role: str,
    *,
    kind: str = "body",
):
    return getattr(factory, f"{kind}_metadata")(
        role=role,
        type_ref=_SUPERVISION_STRING,
        source_span=_span(),
        form_path=_PEER_GROUP_FORM_PATH,
    )


def _peer_group_name(
    factory: WccIdentityFactory,
    name: str,
) -> WccNameAtom:
    return WccNameAtom(
        metadata=_peer_group_metadata(
            factory,
            f"name:{name}",
            kind="atom",
        ),
        name=name,
    )


def _peer_group_perform(
    factory: WccIdentityFactory,
    role: str,
    *,
    perform_kind: str = "provider_result",
    positional_args: tuple[object, ...] = (),
) -> WccPerform:
    return WccPerform(
        metadata=_peer_group_metadata(factory, role, kind="value"),
        perform_kind=perform_kind,
        target_name=f"providers.{role}",
        prompt_name=(
            f"prompts.{role}"
            if perform_kind == "provider_result"
            else None
        ),
        positional_args=positional_args,
        keyword_args=(),
        returns_type_name="String",
    )


def _peer_group_member(
    factory: WccIdentityFactory,
    name: str,
    values: tuple[object, ...],
    *,
    terminal_result: object | None = None,
):
    result_names = tuple(
        f"{name}_{index}"
        for index in range(len(values))
    )
    body = WccHalt(
        metadata=_peer_group_metadata(factory, f"{name}:halt"),
        result=(
            terminal_result
            if terminal_result is not None
            else _peer_group_name(factory, result_names[-1])
        ),
    )
    for result_name, value in reversed(
        tuple(zip(result_names, values, strict=True))
    ):
        body = WccLet(
            metadata=_peer_group_metadata(
                factory,
                f"{name}:let:{result_name}",
            ),
            bound_name=result_name,
            bound_type_ref=_SUPERVISION_STRING,
            bound_value=value,
            body=body,
        )
    return getattr(wcc_model, "WccProviderPeerGroupMember")(
        metadata=_peer_group_metadata(
            factory,
            f"member:{name}",
            kind="value",
        ),
        binding_metadata=_peer_group_metadata(
            factory,
            f"member-binding:{name}",
            kind="value",
        ),
        binding_name=name,
        normalized_body=body,
    )


def _synthetic_provider_peer_group_body(
    *,
    defect: str | None = None,
    member_count: int = 3,
):
    factory = WccIdentityFactory(
        owner_name="peer-group",
        lexical_owner_chain=("workflow", "provider-peer-group"),
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    names = tuple(
        (
            "planner",
            "reviewer",
            "builder",
            "tester",
            "publisher",
            "observer",
            "auditor",
            "reporter",
            "extra",
        )[:member_count]
    )
    first_values: tuple[object, ...] = (
        _peer_group_perform(factory, names[0]),
    )
    first_terminal: object | None = WccPureOp(
        metadata=_peer_group_metadata(
            factory,
            f"{names[0]}:projection",
            kind="value",
        ),
        operator="identity",
        args=(_peer_group_name(factory, f"{names[0]}_0"),),
    )
    if defect == "residual_call":
        first_values = (
            WccCall(
                metadata=_peer_group_metadata(
                    factory,
                    "call:planner",
                    kind="value",
                ),
                callee_name="planner",
                specialized_callee_name="planner",
                args=(),
            ),
        )
        first_terminal = None
    elif defect == "zero_provider_perform":
        first_values = (
            WccLiteralAtom(
                metadata=_peer_group_metadata(
                    factory,
                    f"{names[0]}:pure",
                    kind="atom",
                ),
                value="pure",
                literal_kind="string",
            ),
        )
        first_terminal = None
    elif defect == "provider_result_ignored":
        first_values = (
            _peer_group_perform(factory, names[0]),
            WccLiteralAtom(
                metadata=_peer_group_metadata(
                    factory,
                    f"{names[0]}:ignored-result",
                    kind="atom",
                ),
                value="constant",
                literal_kind="string",
            ),
        )
        first_terminal = None
    elif defect == "second_perform":
        first_values += (
            _peer_group_perform(factory, f"{names[0]}-again"),
        )
        first_terminal = None
    elif defect == "non_provider_perform":
        first_values = (
            _peer_group_perform(
                factory,
                f"{names[0]}-command",
                perform_kind="command_result",
            ),
        )
        first_terminal = None
    elif defect == "later_sibling_reference":
        first_values = (
            _peer_group_perform(
                factory,
                names[0],
                positional_args=(
                    _peer_group_name(factory, names[1]),
                ),
            ),
        )
        first_terminal = None

    members = [
        _peer_group_member(
            factory,
            names[0],
            first_values,
            terminal_result=first_terminal,
        )
    ]
    members.extend(
        _peer_group_member(
            factory,
            name,
            (_peer_group_perform(factory, name),),
        )
        for name in names[1:]
    )
    if defect == "earlier_sibling_reference":
        members[1] = _peer_group_member(
            factory,
            names[1],
            (
                _peer_group_perform(
                    factory,
                    names[1],
                    positional_args=(
                        _peer_group_name(factory, names[0]),
                    ),
                ),
            ),
        )
    elif defect == "duplicate_member":
        members[-1] = replace(
            members[-1],
            binding_name=names[0],
        )
    elif defect == "branch":
        members[0] = replace(
            members[0],
            normalized_body=wcc_model.WccIf(
                metadata=_peer_group_metadata(factory, "planner:if"),
                condition=WccLiteralAtom(
                    metadata=_peer_group_metadata(
                        factory,
                        "planner:condition",
                        kind="atom",
                    ),
                    value=True,
                    literal_kind="bool",
                ),
                condition_shape=object(),
                then_body=members[0].normalized_body,
                else_body=members[0].normalized_body,
            ),
        )
    elif defect == "loop":
        members[0] = replace(
            members[0],
            normalized_body=WccRecJoin(
                metadata=_peer_group_metadata(factory, "planner:loop"),
                loop_name="planner-loop",
                params=(),
                budget=WccLiteralAtom(
                    metadata=_peer_group_metadata(
                        factory,
                        "planner:budget",
                        kind="atom",
                    ),
                    value=1,
                    literal_kind="int",
                ),
                body=WccLoopDone(
                    metadata=_peer_group_metadata(
                        factory,
                        "planner:done",
                    ),
                    result=_peer_group_name(factory, "planner_0"),
                ),
                exhaustion=None,
            ),
        )

    settlement = WccHalt(
        metadata=_peer_group_metadata(factory, "settlement:halt"),
        result=_peer_group_name(factory, names[0]),
    )
    if defect == "effectful_settlement":
        settlement = WccLet(
            metadata=_peer_group_metadata(factory, "settlement:let"),
            bound_name="settlement_effect",
            bound_type_ref=_SUPERVISION_STRING,
            bound_value=_peer_group_perform(factory, "settlement"),
            body=settlement,
        )
    elif defect == "settlement_outer_capture":
        settlement = replace(
            settlement,
            result=_peer_group_name(factory, "outer_request"),
        )
    group = getattr(wcc_model, "WccProviderPeerGroup")(
        metadata=_peer_group_metadata(
            factory,
            "provider-peer-group",
            kind="value",
        ),
        members=tuple(members),
        settlement_body=settlement,
    )
    return WccLet(
        metadata=_peer_group_metadata(factory, "let:peer-group"),
        bound_name="peer_group",
        bound_type_ref=_SUPERVISION_STRING,
        bound_value=group,
        body=WccHalt(
            metadata=_peer_group_metadata(factory, "halt:peer-group"),
            result=_peer_group_name(factory, "peer_group"),
        ),
    )


def test_wcc_m4_analysis_accepts_authored_order_provider_peer_group() -> None:
    body = _synthetic_provider_peer_group_body()
    assert isinstance(body, WccLet)
    group = body.bound_value

    validated = getattr(
        wcc_analysis,
        "validate_wcc_provider_peer_group",
    )(group)
    analyze_wcc_body(body)

    assert isinstance(
        validated,
        getattr(wcc_model, "WccProviderPeerGroup"),
    )
    assert not isinstance(validated, wcc_model.WccProviderSupervision)
    assert tuple(
        member.binding_name
        for member in validated.members
    ) == ("planner", "reviewer", "builder")
    assert all(
        member.provider_binding_name is not None
        for member in validated.members
    )


@pytest.mark.parametrize("member_count", (1, 9))
def test_wcc_m4_analysis_rejects_provider_peer_group_outside_static_bounds(
    member_count: int,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        analyze_wcc_body(
            _synthetic_provider_peer_group_body(
                member_count=member_count,
            )
        )

    _assert_diagnostic_code(
        excinfo,
        "provider_peer_group_member_ineligible",
    )


@pytest.mark.parametrize(
    ("defect", "expected_code"),
    (
        ("residual_call", "provider_peer_group_member_ineligible"),
        (
            "zero_provider_perform",
            "provider_peer_group_member_ineligible",
        ),
        (
            "provider_result_ignored",
            "provider_peer_group_member_ineligible",
        ),
        ("branch", "provider_peer_group_member_ineligible"),
        ("loop", "provider_peer_group_member_ineligible"),
        ("second_perform", "provider_peer_group_member_ineligible"),
        ("non_provider_perform", "provider_peer_group_member_ineligible"),
        (
            "earlier_sibling_reference",
            "provider_peer_group_member_ineligible",
        ),
        (
            "later_sibling_reference",
            "provider_peer_group_member_ineligible",
        ),
        (
            "duplicate_member",
            "provider_peer_group_member_ineligible",
        ),
        (
            "effectful_settlement",
            "provider_peer_group_settlement_effectful",
        ),
        (
            "settlement_outer_capture",
            "provider_peer_group_settlement_environment_invalid",
        ),
    ),
)
def test_wcc_m4_analysis_rejects_noncanonical_provider_peer_group(
    defect: str,
    expected_code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        analyze_wcc_body(
            _synthetic_provider_peer_group_body(defect=defect)
        )

    _assert_diagnostic_code(excinfo, expected_code)


def test_wcc_m4_peer_group_join_param_binds_continuation() -> None:
    factory = WccIdentityFactory(
        owner_name="peer-join-scope",
        lexical_owner_chain=("workflow", "peer-settlement"),
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    literal = WccLiteralAtom(
        metadata=_peer_group_metadata(
            factory,
            "producer:literal",
            kind="atom",
        ),
        value="producer",
        literal_kind="string",
    )
    join = wcc_model.WccJoin(
        metadata=_peer_group_metadata(factory, "join"),
        join_name="settle",
        params=(
            WccJoinParam(
                name="joined",
                type_ref=_SUPERVISION_STRING,
            ),
        ),
        body=WccHalt(
            metadata=_peer_group_metadata(
                factory,
                "producer:halt",
            ),
            result=literal,
        ),
        continuation=WccHalt(
            metadata=_peer_group_metadata(
                factory,
                "continuation:halt",
            ),
            result=_peer_group_name(factory, "joined"),
        ),
    )

    assert wcc_analysis._free_wcc_names_in_body(join) == set()


def test_wcc_m4_peer_group_join_param_does_not_bind_producer_body() -> None:
    factory = WccIdentityFactory(
        owner_name="peer-join-scope",
        lexical_owner_chain=("workflow", "peer-settlement"),
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    literal = WccLiteralAtom(
        metadata=_peer_group_metadata(
            factory,
            "continuation:literal",
            kind="atom",
        ),
        value="continuation",
        literal_kind="string",
    )
    join = wcc_model.WccJoin(
        metadata=_peer_group_metadata(factory, "join"),
        join_name="settle",
        params=(
            WccJoinParam(
                name="joined",
                type_ref=_SUPERVISION_STRING,
            ),
        ),
        body=WccHalt(
            metadata=_peer_group_metadata(
                factory,
                "producer:halt",
            ),
            result=_peer_group_name(factory, "joined"),
        ),
        continuation=WccHalt(
            metadata=_peer_group_metadata(
                factory,
                "continuation:halt",
            ),
            result=literal,
        ),
    )

    assert wcc_analysis._free_wcc_names_in_body(join) == {
        "joined"
    }


def _provider_peer_group_module_source(*forms: str) -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.35")',
            *(f"  {form}" for form in forms),
            ")",
        )
    )


def _typed_provider_peer_group_wcc_context(
    tmp_path: Path,
    *forms: str,
):
    source = _provider_peer_group_module_source(*forms)
    path = tmp_path / "provider_peer_group_wcc_probe.orc"
    path.write_text(source, encoding="utf-8")
    syntax_module = build_syntax_module(
        read_sexpr_text(source, source_path=str(path))
    )
    module = elaborate_definition_module(
        _definition_only_syntax_module(syntax_module)
    )
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(
        module,
        workflow_defs,
        type_env,
    )
    procedure_catalog = build_procedure_catalog(
        procedure_defs,
        type_env=type_env,
    )
    extern_environment = build_extern_environment(
        provider_externs={
            "providers.planner": "planner-provider",
            "providers.reviewer": "reviewer-provider",
            "providers.builder": "builder-provider",
            "providers.worker": "worker-provider",
            "providers.supervisor": "supervisor-provider",
        },
        prompt_externs={
            "prompts.planner": "prompts/planner.md",
            "prompts.reviewer": "prompts/reviewer.md",
            "prompts.builder": "prompts/builder.md",
            "prompts.worker": "prompts/worker.md",
            "prompts.supervisor": "prompts/supervisor.md",
        },
    )
    command_boundary_environment = (
        build_command_boundary_environment(
            {
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("echo",),
                ),
            }
        )
    )
    typed_procedures, typed_workflows, _ = (
        compiler_module._infer_stage3_effect_summaries(
            procedure_defs,
            module=module,
            workflow_defs=workflow_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=(
                command_boundary_environment
            ),
        )
    )
    procedure_type_envs = {
        procedure.definition.name: type_env
        for procedure in typed_procedures
    }
    resolved_procedures_by_name = (
        _resolve_procedure_lowering(
            typed_procedures,
            typed_workflows=typed_workflows,
            workflow_path=path,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
        )
    )
    return {
        "path": path,
        "source": source,
        "type_env": type_env,
        "typed_workflow": next(
            workflow
            for workflow in typed_workflows
            if workflow.definition.name == "orchestrate"
        ),
        "resolved_procedures_by_name": (
            resolved_procedures_by_name
        ),
        "procedure_type_envs": procedure_type_envs,
        "workflow_return_types": {
            workflow.definition.name: (
                workflow.signature.return_type_ref
            )
            for workflow in typed_workflows
        },
        "procedure_return_types": {
            name: procedure.signature.return_type_ref
            for name, procedure
            in resolved_procedures_by_name.items()
        },
    }


def _elaborate_closed_provider_group(context):
    return elaborate_typed_workflow_body(
        context["typed_workflow"].typed_body,
        owner_name=context["typed_workflow"].definition.name,
        value_env=dict(context["typed_workflow"].signature.params),
        type_env=context["type_env"],
        workflow_return_types=context["workflow_return_types"],
        procedure_return_types=context["procedure_return_types"],
        resolved_procedures_by_name=context[
            "resolved_procedures_by_name"
        ],
        procedure_type_envs=context["procedure_type_envs"],
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )


def _first_provider_group(body):
    current = body
    while isinstance(current, WccLet):
        if isinstance(
            current.bound_value,
            (
                wcc_model.WccProviderPeerGroup,
                wcc_model.WccProviderSupervision,
            ),
        ):
            return current.bound_value
        current = current.body
    raise AssertionError("expected a provider group WCC binding")


def test_wcc_m4_provider_peer_group_closes_nested_inline_procedures(
    tmp_path: Path,
) -> None:
    context = _typed_provider_peer_group_wcc_context(
        tmp_path,
        (
            "(defproc pure-project ((value String)) -> String "
            ":effects () :lowering inline "
            "(let* ((projected value)) projected))"
        ),
        (
            "(defproc provider-leaf ((request String)) -> String "
            ":effects ((uses-provider providers.planner)) "
            ":lowering inline "
            "(let* ((raw "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs (request) "
            ":returns String)) "
            "(projected (pure-project raw))) "
            "projected))"
        ),
        (
            "(defproc member-entry ((request String)) -> String "
            ":effects ((uses-provider providers.planner)) "
            ":lowering inline "
            "(provider-leaf request))"
        ),
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-provider-peers "
            '((planner (member-entry "request")) '
            "(reviewer "
            "(provider-result providers.reviewer "
            ":prompt prompts.reviewer :inputs () "
            ":returns String)) "
            "(builder "
            "(provider-result providers.builder "
            ":prompt prompts.builder :inputs () "
            ":returns String))) "
            "planner))"
        ),
    )

    group = _first_provider_group(
        _elaborate_closed_provider_group(context)
    )

    assert isinstance(group, wcc_model.WccProviderPeerGroup)
    assert not isinstance(group, wcc_model.WccProviderSupervision)
    assert tuple(
        member.binding_name
        for member in group.members
    ) == ("planner", "reviewer", "builder")
    for member in group.members:
        provider_performs = 0
        current = member.normalized_body
        while isinstance(current, WccLet):
            assert not isinstance(current.bound_value, WccCall)
            provider_performs += isinstance(
                current.bound_value,
                WccPerform,
            )
            current = current.body
        assert isinstance(current, WccHalt)
        assert provider_performs == 1




def test_wcc_m4_peer_settlement_type_inference_excludes_outer_names() -> None:
    from orchestrator.workflow_lisp.expressions import (
        LiveProviderPeerBinding,
        LiteralExpr,
        NameExpr,
        WithLiveProviderPeersExpr,
    )

    span = _span()
    form_path = _PEER_GROUP_FORM_PATH
    peer_expr = WithLiveProviderPeersExpr(
        bindings=tuple(
            LiveProviderPeerBinding(
                name=name,
                value_expr=LiteralExpr(
                    value=name,
                    literal_kind="string",
                    span=span,
                    form_path=form_path,
                ),
                name_span=span,
                span=span,
                form_path=form_path,
            )
            for name in ("planner", "reviewer")
        ),
        body=NameExpr(
            name="outer_only",
            span=span,
            form_path=form_path,
        ),
        span=span,
        form_path=form_path,
    )

    with pytest.raises(KeyError, match="outer_only"):
        wcc_elaborate_module._infer_expr_type(
            peer_expr,
            type_env=FrontendTypeEnvironment(
                {},
                target_dsl_version="2.35",
            ),
            value_env={
                "outer_only": PrimitiveTypeRef(name="String"),
            },
            workflow_return_types={},
            procedure_return_types={},
        )


def _ineligible_peer_member_forms(defect: str) -> tuple[str, ...]:
    if defect == "residual_non_inline_call":
        member_form = (
            "(defproc bad-member () -> String "
            ":effects ((uses-provider providers.planner)) "
            ":lowering auto "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs () :returns String))"
        )
    elif defect == "zero_provider_perform":
        member_form = (
            "(defproc bad-member () -> String "
            ":effects () :lowering inline "
            '"no provider")'
        )
    elif defect == "provider_result_ignored":
        member_form = (
            "(defproc bad-member () -> String "
            ":effects ((uses-provider providers.planner)) "
            ":lowering inline "
            "(let* ((ignored "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs () :returns String))) "
            '"constant"))'
        )
    elif defect == "branch":
        member_form = (
            "(defproc bad-member () -> String "
            ":effects ((uses-provider providers.planner)) "
            ":lowering inline "
            "(if true "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs () :returns String) "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs () :returns String)))"
        )
    elif defect == "loop":
        member_form = (
            "(defproc bad-member () -> String "
            ":effects ((uses-provider providers.planner)) "
            ":lowering inline "
            "(let* ((result "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs () :returns String))) "
            "(loop/recur :max 1 :state result "
            "(fn (state) (done state)))))"
        )
    elif defect == "second_perform":
        member_form = (
            "(defproc bad-member () -> String "
            ":effects ((uses-provider providers.planner)) "
            ":lowering inline "
            "(let* ((first "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs () :returns String)) "
            "(second "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs (first) "
            ":returns String))) "
            "second))"
        )
    elif defect == "non_provider_perform":
        member_form = (
            "(defproc bad-member () -> String "
            ":effects ((uses-command run_checks)) "
            ":lowering inline "
            "(command-result run_checks "
            ':argv ("echo" "ok") :returns String))'
        )
    else:
        raise AssertionError(f"unknown peer member defect: {defect}")
    workflow_form = (
        "(defworkflow orchestrate () -> String "
        "(with-live-provider-peers "
        "((planner (bad-member)) "
        "(reviewer "
        "(provider-result providers.reviewer "
        ":prompt prompts.reviewer :inputs () :returns String))) "
        "planner))"
    )
    return member_form, workflow_form


@pytest.mark.parametrize(
    "defect",
    (
        "residual_non_inline_call",
        "zero_provider_perform",
        "provider_result_ignored",
        "branch",
        "loop",
        "second_perform",
        "non_provider_perform",
    ),
)
def test_wcc_m4_provider_peer_group_rejects_source_member_defects(
    tmp_path: Path,
    defect: str,
) -> None:
    context = _typed_provider_peer_group_wcc_context(
        tmp_path,
        *_ineligible_peer_member_forms(defect),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _elaborate_closed_provider_group(context)

    _assert_diagnostic_code(
        excinfo,
        "provider_peer_group_member_ineligible",
    )


@pytest.mark.parametrize(
    "bindings",
    (
        (
            "(planner reviewer) "
            "(reviewer "
            "(provider-result providers.reviewer "
            ":prompt prompts.reviewer :inputs () :returns String))"
        ),
        (
            "(planner "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs () :returns String)) "
            "(reviewer planner)"
        ),
    ),
)
def test_wcc_m4_provider_peer_group_source_rejects_sibling_capture(
    tmp_path: Path,
    bindings: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typed_provider_peer_group_wcc_context(
            tmp_path,
            (
                "(defworkflow orchestrate () -> String "
                "(with-live-provider-peers "
                f"({bindings}) "
                "planner))"
            ),
        )

    _assert_diagnostic_code(excinfo, "name_unknown")


def test_wcc_m4_provider_peer_group_preserves_outer_capture_shadowed_by_peer(
    tmp_path: Path,
) -> None:
    context = _typed_provider_peer_group_wcc_context(
        tmp_path,
        (
            "(defworkflow orchestrate ((reviewer String)) "
            "-> String "
            "(with-live-provider-peers "
            "((planner "
            "(provider-result providers.planner "
            ":prompt prompts.planner :inputs (reviewer) "
            ":returns String)) "
            "(reviewer "
            "(provider-result providers.reviewer "
            ":prompt prompts.reviewer :inputs () "
            ":returns String))) "
            "planner))"
        ),
    )

    group = _first_provider_group(
        _elaborate_closed_provider_group(context)
    )

    assert isinstance(group, wcc_model.WccProviderPeerGroup)
    assert group.members[0].lexical_capture_names == ("reviewer",)


def test_wcc_m4_provider_peer_group_source_rejects_outer_settlement_capture(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typed_provider_peer_group_wcc_context(
            tmp_path,
            (
                "(defworkflow orchestrate ((request String)) "
                "-> String "
                "(with-live-provider-peers "
                "((planner "
                "(provider-result providers.planner "
                ":prompt prompts.planner :inputs () "
                ":returns String)) "
                "(reviewer "
                "(provider-result providers.reviewer "
                ":prompt prompts.reviewer :inputs () "
                ":returns String))) "
                "request))"
            ),
        )

    _assert_diagnostic_code(excinfo, "name_unknown")


def test_wcc_m4_target_217_keeps_v1_provider_supervision_term(
    tmp_path: Path,
) -> None:
    context = _typed_provider_peer_group_wcc_context(
        tmp_path,
        (
            "(defworkflow orchestrate () -> String "
            "(with-live-providers "
            "((worker "
            "(provider-result providers.worker "
            ":prompt prompts.worker :inputs () :returns String)) "
            "(supervisor "
            "(provider-result providers.supervisor "
            ":prompt prompts.supervisor :inputs () "
            ":returns ProviderSteeringDirective) "
            ":observes worker)) "
            "worker))"
        ),
    )

    group = _first_provider_group(
        _elaborate_closed_provider_group(context)
    )

    assert isinstance(group, wcc_model.WccProviderSupervision)
    assert not isinstance(group, wcc_model.WccProviderPeerGroup)
