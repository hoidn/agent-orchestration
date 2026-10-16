import importlib
from pathlib import Path
from textwrap import dedent

import pytest

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import _definition_only_syntax_module, _validate_definition_module, compile_stage3_module
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    CommandBoundaryEnvironment,
    build_command_boundary_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_TRANSITION_FIXTURE = FIXTURES / "valid" / "resource_stdlib_transition.orc"
VALID_EFFECTS_FIXTURE = FIXTURES / "valid" / "resource_transition_effects.orc"
VALID_FINALIZE_FIXTURE = FIXTURES / "valid" / "resource_stdlib_finalize_selected_item.orc"
VALID_STDLIB_FINALIZE_FIXTURE = FIXTURES / "valid" / "resource_stdlib_finalize_selected_item_stdlib.orc"
VALID_STDLIB_DRAIN_FIXTURE = FIXTURES / "valid" / "drain_stdlib_backlog_drain_stdlib.orc"
VALID_DECLARED_TRANSITION_FIXTURE = FIXTURES / "valid" / "resource_transition_declared_runtime.orc"
INVALID_ITEM_CTX_FIXTURE = FIXTURES / "invalid" / "item_ctx_contract_invalid.orc"
INVALID_UNCERTIFIED_FIXTURE = FIXTURES / "invalid" / "resource_transition_uncertified_adapter.orc"
INVALID_CERTIFIED_ADAPTER_BYPASS_FIXTURE = FIXTURES / "invalid" / "certified_adapter_semantic_bypass.orc"
INVALID_STDLIB_DRAIN_NON_SYMBOL_CALLEE_FIXTURE = (
    FIXTURES / "invalid" / "drain_stdlib_backlog_drain_non_symbol_callee.orc"
)
INVALID_STDLIB_DRAIN_VIEW_AUTHORITY_FIXTURE = (
    FIXTURES / "invalid" / "drain_stdlib_materialized_view_authority_invalid.orc"
)
INVALID_DECLARED_TRANSITION_FIXTURES = (
    (
        FIXTURES / "invalid" / "resource_transition_unknown_transition.orc",
        "transition_unknown",
    ),
    (
        FIXTURES / "invalid" / "resource_transition_resource_kind_mismatch.orc",
        "transition_resource_kind_mismatch",
    ),
    (
        FIXTURES / "invalid" / "resource_transition_precondition_non_bool.orc",
        "transition_declaration_invalid",
    ),
    (
        FIXTURES / "invalid" / "resource_transition_undeclared_update_target.orc",
        "transition_update_target_unknown",
    ),
    (
        FIXTURES / "invalid" / "resource_transition_result_projection_type_mismatch.orc",
        "transition_result_projection_type_mismatch",
    ),
    (
        FIXTURES / "invalid" / "resource_transition_runtime_forbidden_value.orc",
        "proc_ref_runtime_transport_forbidden",
    ),
)


def _build_syntax_module(path: Path):
    return build_syntax_module(read_sexpr_file(path))


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _expression_syntax(source: str) -> SyntaxNode:
    expr_tree = read_sexpr_text(source, source_path="inline_resource_stdlib.orc")
    assert len(expr_tree.items) == 1
    datum = expr_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_resource_stdlib.orc",
        form_path=("workflow-lisp", "resource-stdlib-test"),
    )


def _command_boundary_environment(
    *,
    include_transition: bool = True,
    extra_bindings: dict[str, object] | None = None,
) -> CommandBoundaryEnvironment:
    bindings: dict[str, object] = {
        "select_next_item": CertifiedAdapterBinding(
            name="select_next_item",
            stable_command=("python", "scripts/select_next_item.py"),
            input_contract={"type": "object"},
            output_type_name="SelectionResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("select_next_item_ok",),
            negative_fixture_ids=("select_next_item_bad",),
        ),
        "execute_selected_item": CertifiedAdapterBinding(
            name="execute_selected_item",
            stable_command=("python", "scripts/execute_selected_item.py"),
            input_contract={"type": "object"},
            output_type_name="SelectedItemResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("execute_selected_item_ok",),
            negative_fixture_ids=("execute_selected_item_bad",),
        ),
        "draft_gap_item": CertifiedAdapterBinding(
            name="draft_gap_item",
            stable_command=("python", "scripts/draft_gap_item.py"),
            input_contract={"type": "object"},
            output_type_name="GapDraftResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("draft_gap_item_ok",),
            negative_fixture_ids=("draft_gap_item_bad",),
        ),
        "resolve_plan_gate": CertifiedAdapterBinding(
            name="resolve_plan_gate",
            stable_command=("python", "scripts/resolve_plan_gate.py"),
            input_contract={"type": "object"},
            output_type_name="PlanGateResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("resolve_plan_gate_ok",),
            negative_fixture_ids=("resolve_plan_gate_bad",),
        ),
        "resolve_roadmap_sync": CertifiedAdapterBinding(
            name="resolve_roadmap_sync",
            stable_command=("python", "scripts/resolve_roadmap_sync.py"),
            input_contract={"type": "object"},
            output_type_name="RoadmapSyncResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("resolve_roadmap_sync_ok",),
            negative_fixture_ids=("resolve_roadmap_sync_bad",),
        ),
        "execute_implementation": CertifiedAdapterBinding(
            name="execute_implementation",
            stable_command=("python", "scripts/execute_implementation.py"),
            input_contract={"type": "object"},
            output_type_name="ImplementationResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("execute_implementation_ok",),
            negative_fixture_ids=("execute_implementation_bad",),
        ),
    }
    if include_transition:
        bindings["apply_resource_transition"] = CertifiedAdapterBinding(
            name="apply_resource_transition",
            stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.apply_resource_transition"),
            input_contract={"type": "object"},
            output_type_name="ResourceTransitionResult",
            effects=("resource_transition", "ledger_update"),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("resource_transition_ok",),
            negative_fixture_ids=("resource_transition_bad",),
        )
    if extra_bindings:
        bindings.update(extra_bindings)
    return build_command_boundary_environment(bindings)


def _typecheck_fixture(
    path: Path,
    *,
    include_transition: bool = True,
    extra_bindings: dict[str, object] | None = None,
):
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        command_boundary_environment=_command_boundary_environment(
            include_transition=include_transition,
            extra_bindings=extra_bindings,
        ),
    )




























def test_elaborate_resource_transition_expr() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(resource-transition backlog-item "
            ":ctx item-ctx "
            ":when selected.is-active "
            ":resource selected.item-id "
            ":from Queue.active "
            ":to Queue.in_progress "
            ":ledger item-ctx.ledger "
            ":event SELECTED)"
        ),
        bound_names=frozenset({"item-ctx", "selected"}),
    )

    assert type(expr).__name__ == "ResourceTransitionExpr"


def test_elaborate_declared_resource_transition_expr() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(resource-transition "
            ":transition write-drain-status "
            ":resource drain-run-state "
            ':request (record DrainStatusRequest :status "BLOCKED"))'
        ),
        bound_names=frozenset(),
    )

    assert type(expr).__name__ == "ResourceTransitionExpr"
    assert expr.spec.transition_ref_name == "write-drain-status"
    assert expr.spec.resource_ref_name == "drain-run-state"
    assert expr.spec.request_expr is not None


def test_elaborate_finalize_selected_item_expr() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(finalize-selected-item "
            ":ctx item-ctx "
            ":selected selected "
            ":queue-transition queue-transition "
            ":roadmap roadmap "
            ":plan plan "
            ":implementation implementation)"
        ),
        bound_names=frozenset({"item-ctx", "selected", "queue-transition", "roadmap", "plan", "implementation"}),
    )

    assert type(expr).__name__ == "FinalizeSelectedItemExpr"


def test_typecheck_accepts_item_ctx_contract() -> None:
    typed = _typecheck_fixture(VALID_TRANSITION_FIXTURE)

    assert [workflow.definition.name for workflow in typed] == ["move-selected-item"]


def test_typecheck_accepts_declared_resource_transition_fixture() -> None:
    typed = _typecheck_fixture(VALID_DECLARED_TRANSITION_FIXTURE)

    assert [workflow.definition.name for workflow in typed] == ["orchestrate"]


def test_typecheck_resource_transition_infers_promoted_effects() -> None:
    effects_module = importlib.import_module("orchestrator.workflow_lisp.effects")
    typed = _typecheck_fixture(VALID_EFFECTS_FIXTURE)
    workflow = next(workflow for workflow in typed if workflow.definition.name == "move-selected-item")

    assert workflow.effect_summary.transitive_effects == frozenset(
        {
            effects_module.UsesCommandEffect(subject=("apply_resource_transition",)),
            getattr(effects_module, "MovesResourceEffect")(
                subject=("backlog-item",),
                from_queue=("Queue", "active"),
                to_queue=("Queue", "in_progress"),
            ),
            getattr(effects_module, "UpdatesLedgerEffect")(
                subject=("backlog-item",),
                event_name=("SELECTED",),
            ),
        }
    )


def test_typecheck_rejects_item_ctx_contract() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_ITEM_CTX_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "item_context_invalid"


def test_typecheck_rejects_resource_transition_adapter_authored_as_raw_command_result(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resource_transition_raw_command_result.orc"
    path.write_text(
        dedent(
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.35")
              (defpath StateFile
                :kind relpath
                :under "state"
                :must-exist false)
              (defrecord ResourceTransitionResult
                (resource_path String)
                (ledger_path StateFile))
              (defworkflow orchestrate
                ((resource_path String)
                 (ledger_path StateFile))
                -> ResourceTransitionResult
                (command-result apply_resource_transition
                  :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.apply_resource_transition" resource_path ledger_path)
                  :returns ResourceTransitionResult)))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_workflow_definitions(
            workflow_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            command_boundary_environment=_command_boundary_environment(),
        )

    assert excinfo.value.diagnostics[0].code == "resource_move_without_transition"


def test_typecheck_rejects_item_ctx_with_non_runctx_run(tmp_path: Path) -> None:
    path = tmp_path / "item_ctx_bad_run_shape.orc"
    path.write_text(
        dedent(
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.35")
              (defenum Queue
                active
                in_progress)
              (defenum LedgerEvent
                SELECTED)
              (defpath StateFile
                :kind relpath
                :under "state"
                :must-exist false)
              (defpath BacklogActivePath
                :kind relpath
                :under "docs/backlog/active"
                :must-exist true)
              (defpath BacklogInProgressPath
                :kind relpath
                :under "docs/backlog/in_progress"
                :must-exist true)
              (defrecord RunCtx
                (run-id RunId)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root))
              (defrecord BadRunCtx
                (bogus String))
              (defrecord ItemCtx
                (run BadRunCtx)
                (item-id String)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root)
                (ledger StateFile))
              (defrecord SelectedItem
                (item-id String)
                (item-path BacklogActivePath)
                (is-active Bool))
              (defrecord ResourceTransitionResult
                (resource-id String)
                (from Queue)
                (to Queue)
                (new-path BacklogInProgressPath)
                (transition-id String))
              (defrecord TransitionSummary
                (transition-id String))
              (defworkflow move-selected-item
                ((item-ctx ItemCtx)
                 (selected SelectedItem))
                -> TransitionSummary
                (let* ((transition
                         (resource-transition backlog-item
                           :ctx item-ctx
                           :resource selected.item-id
                           :from Queue.active
                           :to Queue.in_progress
                           :ledger item-ctx.ledger
                           :event SELECTED)))
                  (record TransitionSummary
                    :transition-id transition.transition-id))))
            """
        ).strip()
        + "\n"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    assert excinfo.value.diagnostics[0].code == "item_context_invalid"




def test_typecheck_rejects_resource_transition_without_certified_adapter() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_UNCERTIFIED_FIXTURE, include_transition=False)

    assert excinfo.value.diagnostics[0].code == "command_adapter_missing_contract"


def test_typecheck_rejects_resource_transition_without_promotable_adapter_effects() -> None:
    invalid_binding = CertifiedAdapterBinding(
        name="apply_resource_transition",
        stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.apply_resource_transition"),
        input_contract={"type": "object"},
        output_type_name="ResourceTransitionResult",
        effects=("structured_result",),
        path_safety={"kind": "workspace_relpath"},
        source_map_behavior="step",
        fixture_ids=("resource_transition_ok",),
        negative_fixture_ids=("resource_transition_bad",),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(
            VALID_EFFECTS_FIXTURE,
            extra_bindings={"apply_resource_transition": invalid_binding},
        )

    assert excinfo.value.diagnostics[0].code == "command_adapter_missing_contract"


def test_compile_stage3_module_auto_registers_resource_transition_adapter(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_TRANSITION_FIXTURE,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    binding = result.command_boundary_environment.bindings_by_name.get("apply_resource_transition")

    assert binding is not None
    assert isinstance(binding, CertifiedAdapterBinding)
    assert binding.stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.apply_resource_transition",
    )
    assert binding.output_type_name == "ResourceTransitionResult"


def test_command_boundaries_reject_direct_resource_transition_certified_adapter_call(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            INVALID_CERTIFIED_ADAPTER_BYPASS_FIXTURE,
            command_boundaries=_parse_command_boundaries_manifest(
                {
                    "apply_resource_transition": {
                        "kind": "certified_adapter",
                        "stable_command": [
                            "python",
                            "-m",
                            "orchestrator.workflow_lisp.adapters.apply_resource_transition",
                        ],
                        "input_contract": {"type": "object"},
                        "output_type_name": "ResourceTransitionResult",
                        "effects": ["resource_transition", "ledger_update"],
                        "path_safety": {"kind": "workspace_relpath"},
                        "source_map_behavior": "step",
                        "fixture_ids": ["resource_transition_ok"],
                        "negative_fixture_ids": ["resource_transition_bad"],
                        "behavior_class": "resource_transition",
                        "input_signature": [
                            {
                                "name": "resource_id",
                                "type_name": "String",
                                "required": True,
                                "transport_key": "resource_id",
                            },
                            {
                                "name": "from",
                                "type_name": "Queue",
                                "required": True,
                                "transport_key": "from",
                            },
                            {
                                "name": "to",
                                "type_name": "Queue",
                                "required": True,
                                "transport_key": "to",
                            },
                            {
                                "name": "new_path",
                                "type_name": "BacklogInProgressPath",
                                "required": True,
                                "transport_key": "new_path",
                            },
                            {
                                "name": "transition_id",
                                "type_name": "String",
                                "required": True,
                                "transport_key": "transition_id",
                            },
                        ],
                        "artifact_contracts": ["resource_transition_result"],
                        "state_writes": ["state/resource-ledger.json"],
                        "error_codes": ["resource_transition_invalid"],
                        "owner_module": "std/resource",
                        "replacement_path": "resource-transition",
                        "invocation_protocol": "json_object_positional_arg",
                    }
                },
                manifest_path=None,
            ),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "resource_move_without_transition"


def test_typecheck_rejects_invalid_resource_transition_queue_and_event_symbols(tmp_path: Path) -> None:
    path = tmp_path / "resource_transition_invalid_symbols.orc"
    path.write_text(
        dedent(
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.35")
              (defenum Queue
                active
                in_progress)
              (defenum LedgerEvent
                SELECTED)
              (defpath StateFile
                :kind relpath
                :under "state"
                :must-exist false)
              (defpath BacklogActivePath
                :kind relpath
                :under "docs/backlog/active"
                :must-exist true)
              (defpath BacklogInProgressPath
                :kind relpath
                :under "docs/backlog/in_progress"
                :must-exist true)
              (defrecord RunCtx
                (run-id RunId)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root))
              (defrecord ItemCtx
                (run RunCtx)
                (item-id String)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root)
                (ledger StateFile))
              (defrecord SelectedItem
                (item-id String)
                (item-path BacklogActivePath)
                (is-active Bool))
              (defrecord ResourceTransitionResult
                (resource-id String)
                (from Queue)
                (to Queue)
                (new-path BacklogInProgressPath)
                (transition-id String))
              (defrecord TransitionSummary
                (transition-id String))
              (defworkflow move-selected-item
                ((item-ctx ItemCtx)
                 (selected SelectedItem))
                -> TransitionSummary
                (let* ((transition
                         (resource-transition backlog-item
                           :ctx item-ctx
                           :resource selected.item-id
                           :from definitely_not_a_queue
                           :to still_not_a_queue
                           :ledger item-ctx.ledger
                           :event NOT_A_REAL_EVENT)))
                  (record TransitionSummary
                    :transition-id transition.transition-id))))
            """
        ).strip()
        + "\n"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    assert excinfo.value.diagnostics[0].code == "resource_transition_contract_invalid"


def test_typecheck_rejects_resource_transition_with_bool_resource_operand(tmp_path: Path) -> None:
    path = tmp_path / "resource_transition_invalid_resource_type.orc"
    path.write_text(
        dedent(
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.35")
              (defenum Queue
                active
                in_progress)
              (defenum LedgerEvent
                SELECTED)
              (defpath StateFile
                :kind relpath
                :under "state"
                :must-exist false)
              (defpath BacklogActivePath
                :kind relpath
                :under "docs/backlog/active"
                :must-exist true)
              (defpath BacklogInProgressPath
                :kind relpath
                :under "docs/backlog/in_progress"
                :must-exist true)
              (defrecord RunCtx
                (run-id RunId)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root))
              (defrecord ItemCtx
                (run RunCtx)
                (item-id String)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root)
                (ledger StateFile))
              (defrecord SelectedItem
                (item-id String)
                (item-path BacklogActivePath)
                (is-active Bool))
              (defrecord ResourceTransitionResult
                (resource-id String)
                (from Queue)
                (to Queue)
                (new-path BacklogInProgressPath)
                (transition-id String))
              (defrecord TransitionSummary
                (transition-id String))
              (defworkflow move-selected-item
                ((item-ctx ItemCtx)
                 (selected SelectedItem))
                -> TransitionSummary
                (let* ((transition
                         (resource-transition backlog-item
                           :ctx item-ctx
                           :resource selected.is-active
                           :from Queue.active
                           :to Queue.in_progress
                           :ledger item-ctx.ledger
                           :event SELECTED)))
                  (record TransitionSummary
                    :transition-id transition.transition-id))))
            """
        ).strip()
        + "\n"
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    assert excinfo.value.diagnostics[0].code == "resource_transition_contract_invalid"


@pytest.mark.parametrize(("path", "expected_code"), INVALID_DECLARED_TRANSITION_FIXTURES)
def test_typecheck_declared_resource_transition_reports_typed_diagnostics(
    path: Path,
    expected_code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    assert excinfo.value.diagnostics[0].code == expected_code


def test_typecheck_rejects_finalize_selected_item_with_malformed_phase_results(tmp_path: Path) -> None:
    path = tmp_path / "finalize_selected_item_wrong_phase_results.orc"
    path.write_text(
        dedent(
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.35")
              (defenum Queue
                active
                in_progress)
              (defenum LedgerEvent
                SELECTED)
              (defenum BlockerClass
                missing_resource
                unavailable_hardware
                roadmap_conflict
                external_dependency_outside_authority
                user_decision_required
                unrecoverable_after_fix_attempt)
              (defpath WorkReport
                :kind relpath
                :under "artifacts/work"
                :must-exist true)
              (defpath StateFile
                :kind relpath
                :under "state"
                :must-exist false)
              (defpath StateExisting
                :kind relpath
                :under "state"
                :must-exist true)
              (defpath BacklogActivePath
                :kind relpath
                :under "docs/backlog/active"
                :must-exist true)
              (defpath BacklogInProgressPath
                :kind relpath
                :under "docs/backlog/in_progress"
                :must-exist true)
              (defrecord RunCtx
                (run-id RunId)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root))
              (defrecord ItemCtx
                (run RunCtx)
                (item-id String)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root)
                (ledger StateFile))
              (defrecord SelectedItem
                (item-id String)
                (item-path BacklogActivePath)
                (is-active Bool)
                (final-plan-gate-state StateExisting))
              (defrecord ResourceTransitionResult
                (resource-id String)
                (from Queue)
                (to Queue)
                (new-path BacklogInProgressPath)
                (transition-id String))
              (defrecord RoadmapSyncResult
                (status String))
              (defunion WrongPlanResult
                (APPROVED
                  (summary-path WorkReport))
                (BLOCKED
                  (summary-path WorkReport)))
              (defunion ImplementationResult
                (COMPLETED
                  (execution-report-path WorkReport))
                (BLOCKED
                  (progress-report-path WorkReport)
                  (blocker-class BlockerClass)))
              (defunion SelectedItemResult
                (CONTINUE
                  (summary-path WorkReport)
                  (run-state StateExisting))
                (BLOCKED
                  (summary-path WorkReport)
                  (blocker-class BlockerClass)
                  (run-state StateExisting)))
              (defworkflow roadmap-sync
                ((item-ctx ItemCtx)
                 (selected SelectedItem))
                -> RoadmapSyncResult
                (record RoadmapSyncResult
                  :status selected.item-id))
                (defworkflow plan-run
                  ((item-ctx ItemCtx)
                   (selected SelectedItem)
                   (roadmap RoadmapSyncResult))
                  -> WrongPlanResult
                  (command-result resolve_wrong_plan_gate
                    :argv ("python" "scripts/resolve_wrong_plan_gate.py" selected.item-id)
                    :returns WrongPlanResult))
              (defworkflow implementation-run
                ((item-ctx ItemCtx)
                 (selected SelectedItem))
                -> ImplementationResult
                (command-result execute_implementation
                  :argv ("python" "scripts/execute_implementation.py" selected.item-id)
                  :returns ImplementationResult))
              (defworkflow run-selected-item
                ((item-ctx ItemCtx)
                 (selected SelectedItem))
                -> SelectedItemResult
                (let* ((queue-transition
                         (resource-transition backlog-item
                           :ctx item-ctx
                           :when selected.is-active
                           :resource selected.item-id
                           :from Queue.active
                           :to Queue.in_progress
                           :ledger item-ctx.ledger
                           :event SELECTED))
                       (roadmap
                         (call roadmap-sync
                           :item-ctx item-ctx
                           :selected selected))
                       (plan
                         (call plan-run
                           :item-ctx item-ctx
                           :selected selected
                           :roadmap roadmap))
                       (implementation
                         (call implementation-run
                           :item-ctx item-ctx
                           :selected selected)))
                  (finalize-selected-item
                    :ctx item-ctx
                    :selected selected
                    :queue-transition queue-transition
                    :roadmap roadmap
                    :plan plan
                    :implementation implementation))))
            """
        ).strip()
        + "\n"
    )

    extra_bindings = {
        "resolve_wrong_plan_gate": CertifiedAdapterBinding(
            name="resolve_wrong_plan_gate",
            stable_command=("python", "scripts/resolve_wrong_plan_gate.py"),
            input_contract={"type": "object"},
            output_type_name="WrongPlanResult",
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=("resolve_wrong_plan_gate_ok",),
            negative_fixture_ids=("resolve_wrong_plan_gate_bad",),
        )
    }

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path, extra_bindings=extra_bindings)

    assert excinfo.value.diagnostics[0].code == "finalize_selected_item_contract_invalid"






def test_typecheck_finalize_selected_item_accepts_union_phase_results() -> None:
    typed = _typecheck_fixture(VALID_FINALIZE_FIXTURE)

    assert [workflow.definition.name for workflow in typed] == [
        "roadmap-sync",
        "plan-run",
        "implementation-run",
        "run-selected-item",
    ]
