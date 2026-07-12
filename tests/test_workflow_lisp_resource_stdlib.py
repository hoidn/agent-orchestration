import importlib
from pathlib import Path
import json
import re
import shutil
from textwrap import dedent

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
    compile_stage3_entrypoint,
    compile_stage3_module,
    validate_lowered_workflows,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import elaborate_expression
from orchestrator.workflow_lisp.lowering import _observed_statement_families
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.stdlib_contracts import STDLIB_LOWERING_CONTRACTS_BY_FORM
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
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_TRANSITION_FIXTURE = FIXTURES / "valid" / "resource_stdlib_transition.orc"
VALID_EFFECTS_FIXTURE = FIXTURES / "valid" / "resource_transition_effects.orc"
VALID_FINALIZE_FIXTURE = FIXTURES / "valid" / "resource_stdlib_finalize_selected_item.orc"
VALID_STDLIB_FINALIZE_FIXTURE = FIXTURES / "valid" / "resource_stdlib_finalize_selected_item_stdlib.orc"
VALID_STDLIB_DRAIN_FIXTURE = FIXTURES / "valid" / "drain_stdlib_backlog_drain_stdlib.orc"
VALID_DECLARED_TRANSITION_FIXTURE = FIXTURES / "valid" / "resource_transition_declared_runtime.orc"
INVALID_ITEM_CTX_FIXTURE = FIXTURES / "invalid" / "item_ctx_contract_invalid.orc"
INVALID_DRAIN_CTX_FIXTURE = FIXTURES / "invalid" / "drain_ctx_contract_invalid.orc"
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


def _typecheck_module_fixture(
    path: Path,
    *,
    tmp_path: Path,
    include_transition: bool = True,
):
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries=_command_boundary_environment(include_transition=include_transition).bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
    )
    return result.entry_result.typed_workflows


def _compile(path: Path, *, tmp_path: Path, include_transition: bool = True):
    return compile_stage3_module(
        path,
        command_boundaries=_command_boundary_environment(include_transition=include_transition).bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
    )


def _runtime_command_boundary_environment() -> CommandBoundaryEnvironment:
    bindings = dict(_command_boundary_environment().bindings_by_name)
    transition = bindings["apply_resource_transition"]
    bindings["apply_resource_transition"] = CertifiedAdapterBinding(
        name=transition.name,
        stable_command=(
            "python",
            str(REPO_ROOT / "orchestrator" / "workflow_lisp" / "adapters" / "apply_resource_transition.py"),
        ),
        input_contract=transition.input_contract,
        output_type_name=transition.output_type_name,
        effects=transition.effects,
        path_safety=transition.path_safety,
        source_map_behavior=transition.source_map_behavior,
        fixture_ids=transition.fixture_ids,
        negative_fixture_ids=transition.negative_fixture_ids,
    )
    return build_command_boundary_environment(bindings)


def _compile_linked_module_fixture(path: Path, *, tmp_path: Path):
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    runtime_command_boundaries = _runtime_command_boundary_environment()
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries=runtime_command_boundaries.bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
    )
    validated = validate_lowered_workflows(
        result.entry_result.lowered_workflows,
        workspace_root=tmp_path,
        imported_workflow_bundles=result.entry_result.workflow_catalog.imported_bundles_by_name,
    )
    return module_path, result, validated


def _default_state_value(type_payload: dict[str, object]) -> object:
    kind = type_payload.get("kind")
    if kind == "primitive":
        primitive_name = type_payload.get("name")
        if primitive_name == "String":
            return ""
        if primitive_name == "Bool":
            return False
        if primitive_name == "Int":
            return 0
        if primitive_name == "Float":
            return 0.0
        if primitive_name == "Json":
            return {}
    if kind == "record":
        return {
            str(field["name"]): _default_state_value(dict(field["type"]))
            for field in type_payload.get("fields", ())
        }
    if kind == "path":
        name = str(type_payload.get("name", ""))
        if "Report" in name or "report" in name:
            return "artifacts/work/seed-report.md"
        return "state/seed-state.json"
    if kind == "enum":
        allowed = tuple(type_payload.get("allowed", ()))
        assert allowed
        return allowed[0]
    if kind == "list":
        return []
    if kind == "map":
        return {}
    if kind == "optional":
        return None
    raise AssertionError(f"unsupported test seed type: {type_payload!r}")


def _iter_surface_steps(steps):
    for step in steps or ():
        yield step
        for branch_step in step.then_branch or ():
            yield from _iter_surface_steps((branch_step,))
        for branch_step in step.else_branch or ():
            yield from _iter_surface_steps((branch_step,))
        for branch_step in step.for_each_steps or ():
            yield from _iter_surface_steps((branch_step,))
        for case in step.match_cases.values():
            yield from _iter_surface_steps(case.steps)


def _seed_native_resource_states(bundle, workspace: Path) -> None:
    for step in _iter_surface_steps(bundle.surface.steps):
        declaration = step.resource_transition.get("declaration")
        resource = step.resource_transition.get("resource")
        if declaration is None or resource is None:
            continue
        if declaration.resource.backing.kind != "native":
            continue
        state_path = workspace / str(resource["state_path"])
        if state_path.exists():
            continue
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "transition_schema_version": 1,
                    "resource_id": resource["resource_id"],
                    "resource_kind": resource["resource_kind"],
                    "state_version": "native:0:seed",
                    "state": _default_state_value(dict(declaration.resource.state_type)),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def _write_resource_runtime_scripts(workspace: Path) -> None:
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script_payloads = {
        "resolve_roadmap_sync.py": {
            "body": {
                "status": "aligned",
            },
            "artifact_relpaths": (),
        },
        "resolve_plan_gate.py": {
            "body": {
                "variant": "APPROVED",
                "execution-report-path": "artifacts/work/plan-gate-approved.md",
            },
            "artifact_relpaths": ("artifacts/work/plan-gate-approved.md",),
        },
        "execute_implementation.py": {
            "body": {
                "variant": "COMPLETED",
                "execution-report-path": "artifacts/work/implementation-execution.md",
            },
            "artifact_relpaths": ("artifacts/work/implementation-execution.md",),
        },
    }
    for script_name, payload in script_payloads.items():
        lines = [
            "import json",
            "import os",
            "from pathlib import Path",
            "",
        ]
        for relpath in payload["artifact_relpaths"]:
            lines.extend(
                [
                    f"artifact_path = Path({relpath!r})",
                    "artifact_path.parent.mkdir(parents=True, exist_ok=True)",
                    "artifact_path.write_text('generated\\n', encoding='utf-8')",
                    "",
                ]
            )
        lines.extend(
            [
                'bundle_path = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])',
                "bundle_path.parent.mkdir(parents=True, exist_ok=True)",
                f"bundle_path.write_text(json.dumps({payload['body']!r}) + '\\n', encoding='utf-8')",
            ]
        )
        (scripts_dir / script_name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _bound_runtime_inputs(bundle, workspace: Path, inputs: dict[str, object]) -> dict[str, object]:
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    public_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    return bind_workflow_inputs(public_inputs, inputs, workspace)


def _execute_bundle(bundle, *, workflow_path: Path, workspace: Path, inputs: dict[str, object], run_id: str):
    _seed_native_resource_states(bundle, workspace)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bound_runtime_inputs(bundle, workspace, inputs),
    )
    for relpath in ("scripts", "docs", "state"):
        source = workspace / relpath
        if source.exists():
            shutil.copytree(source, state_manager.run_root / relpath, dirs_exist_ok=True)
    return WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(on_error="stop")


def _iter_nested_steps(steps):
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        yield step
        match = step.get("match")
        if isinstance(match, dict):
            for case in (match.get("cases") or {}).values():
                if isinstance(case, dict):
                    yield from _iter_nested_steps(case.get("steps"))
        repeat = step.get("repeat_until")
        if isinstance(repeat, dict):
            yield from _iter_nested_steps(repeat.get("steps"))


def _assert_contract_matches_observed_families(contract, *, steps) -> set[str]:
    observed = set(_observed_statement_families(steps))
    assert set(contract.required_statement_families).issubset(observed)
    for alternatives in contract.alternative_statement_family_sets:
        matches = observed.intersection(alternatives)
        assert len(matches) == 1
    return observed


def _assert_contract_source_map_expectations(
    contract,
    lowered,
    *,
    hidden_inputs: tuple[str, ...] = (),
    generated_paths: tuple[str, ...] = (),
) -> None:
    nested_steps = list(_iter_nested_steps(lowered.authored_mapping["steps"]))
    assert nested_steps
    for step in nested_steps:
        step_id = step.get("id")
        if isinstance(step_id, str):
            assert step_id in lowered.origin_map.step_spans
            assert lowered.origin_map.step_spans[step_id].origin_key
    if "high_level_form_origin" in contract.source_map_expectations:
        assert any(origin.form_path for origin in lowered.origin_map.step_spans.values())
    if "generated_hidden_input_span" in contract.source_map_expectations:
        for hidden_input in hidden_inputs:
            assert hidden_input in lowered.origin_map.internal_input_spans
    if "generated_hidden_path_span" in contract.source_map_expectations:
        for generated_path in generated_paths:
            assert generated_path in lowered.origin_map.generated_path_spans


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


def test_typecheck_rejects_drain_ctx_contract() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_DRAIN_CTX_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "drain_context_invalid"


def test_typecheck_rejects_resource_transition_adapter_authored_as_raw_command_result(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resource_transition_raw_command_result.orc"
    path.write_text(
        dedent(
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.14")
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
              (:target-dsl "2.14")
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


def test_typecheck_rejects_drain_ctx_with_non_runctx_run(tmp_path: Path) -> None:
    path = tmp_path / "drain_ctx_bad_run_shape.orc"
    source = (FIXTURES / "valid" / "drain_stdlib_backlog_drain.orc").read_text()
    source = source.replace(
        "(defrecord RunCtx\n    (run-id RunId)\n    (state-root Path.state-root)\n    (artifact-root Path.artifact-root))",
        "(defrecord RunCtx\n    (run-id RunId)\n    (state-root Path.state-root)\n    (artifact-root Path.artifact-root))\n  (defrecord BadRunCtx\n    (bogus String))",
        1,
    )
    source = source.replace("(run RunCtx)", "(run BadRunCtx)", 1)
    path.write_text(source)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    assert excinfo.value.diagnostics[0].code == "drain_context_invalid"


def test_promoted_entry_ItemCtx_hidden_binding_reports_unsupported_private_exec_bootstrap(
    tmp_path: Path,
) -> None:
    path = tmp_path / "private_exec_context" / "item_ctx.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        dedent(
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.14")
              (defmodule private_exec_context/item_ctx)
              (export entry run-selected-item)
              (defrecord RunCtx
                (run-id RunId)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root))
              (defpath StateFile
                :kind relpath
                :under "state"
                :must-exist false)
              (defrecord ItemCtx
                (run RunCtx)
                (item-id String)
                (state-root Path.state-root)
                (artifact-root Path.artifact-root)
                (ledger StateFile))
              (defrecord SelectionPayload
                (item-id String))
              (defrecord Result
                (item-id String))
              (defworkflow entry
                ((selection SelectionPayload))
                -> Result
                (call run-selected-item
                  :selection selection))
              (defworkflow run-selected-item
                ((item-ctx ItemCtx)
                 (selection SelectionPayload))
                -> Result
                (record Result :item-id selection.item-id)))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            path,
            source_roots=(tmp_path,),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "private_exec_context_bootstrap_unsupported"
    assert "ItemCtx" in diagnostic.message


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
              (:target-dsl "2.14")
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
              (:target-dsl "2.14")
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
              (:target-dsl "2.14")
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


def test_lowering_resource_transition_uses_certified_adapter(tmp_path: Path) -> None:
    result = _compile(VALID_TRANSITION_FIXTURE, tmp_path=tmp_path)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "move-selected-item"
    )
    command_steps = [
        step
        for step in _iter_nested_steps(authored["steps"])
        if step.get("command", [])[:3] == ["python", "-m", "orchestrator.workflow_lisp.adapters.apply_resource_transition"]
    ]

    assert len(command_steps) == 1
    assert "output_bundle" in command_steps[0]
    assert len(command_steps[0]["command"]) == 4
    assert command_steps[0]["when"] == {"artifact_bool": {"ref": "inputs.selected__is-active"}}
    payload = json.loads(command_steps[0]["command"][3])
    assert payload["transition_name"] == "backlog-item"
    assert payload["resource_id"] == "${inputs.selected__item-id}"
    assert payload["resource_path"] == "${inputs.selected__item-path}"
    assert payload["from"] == "active"
    assert payload["to"] == "in_progress"
    assert payload["ledger_path"] == "${inputs.item-ctx__ledger}"
    assert payload["event"] == "SELECTED"


def test_lowering_resource_transition_uses_authored_resource_path_operand(tmp_path: Path) -> None:
    path = tmp_path / "resource_transition_path_operand.orc"
    path.write_text(
        dedent(
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.14")
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
                (item BacklogActivePath)
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
                           :when selected.is-active
                           :resource selected.item
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

    result = _compile(path, tmp_path=tmp_path)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "move-selected-item"
    )
    command_step = next(
        step
        for step in _iter_nested_steps(authored["steps"])
        if step.get("command", [])[:3] == ["python", "-m", "orchestrator.workflow_lisp.adapters.apply_resource_transition"]
    )

    payload = json.loads(command_step["command"][3])

    assert payload["resource_id"] == "${inputs.selected__item-id}"
    assert payload["resource_path"] == "${inputs.selected__item}"


def test_typecheck_finalize_selected_item_accepts_union_phase_results() -> None:
    typed = _typecheck_fixture(VALID_FINALIZE_FIXTURE)

    assert [workflow.definition.name for workflow in typed] == [
        "roadmap-sync",
        "plan-run",
        "implementation-run",
        "run-selected-item",
    ]


def test_lowering_finalize_selected_item_materializes_outcome_and_publishes_summary(tmp_path: Path) -> None:
    result = _compile(VALID_FINALIZE_FIXTURE, tmp_path=tmp_path)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-selected-item"
    )
    nested_steps = list(_iter_nested_steps(authored["steps"]))
    finalize_step = next(step for step in authored["steps"] if step.get("name") == "run-selected-item")
    materialize_steps = [step for step in nested_steps if "materialize_artifacts" in step]
    published_steps = [step for step in nested_steps if step.get("publishes")]

    assert "match" in finalize_step
    assert any(
        {
            value["name"]
            for value in step["materialize_artifacts"]["values"]
        }
        >= {"return__variant", "return__summary-path"}
        for step in materialize_steps
    )
    assert any(
        publish.get("artifact") == "selected_item_summary"
        for step in published_steps
        for publish in step["publishes"]
    )


def test_lowering_finalize_selected_item_carries_queue_transition_id(tmp_path: Path) -> None:
    result = _compile(VALID_FINALIZE_FIXTURE, tmp_path=tmp_path)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-selected-item"
    )
    materialize_steps = [
        step for step in _iter_nested_steps(authored["steps"]) if "materialize_artifacts" in step
    ]

    queue_transition_values = [
        value
        for step in materialize_steps
        for value in step["materialize_artifacts"]["values"]
        if value["name"] == "queue_transition_id"
    ]

    assert queue_transition_values
    assert all(
        value["source"] == {"ref": "root.steps.run-selected-item__queue-transition.artifacts.transition-id"}
        for value in queue_transition_values
    )


def test_resource_stdlib_contract_inventory_matches_lowering_families(tmp_path: Path) -> None:
    transition_result = _compile(VALID_TRANSITION_FIXTURE, tmp_path=tmp_path)
    finalize_result = _compile(VALID_FINALIZE_FIXTURE, tmp_path=tmp_path)

    transition_lowered = next(
        workflow
        for workflow in transition_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "move-selected-item"
    )
    finalize_lowered = next(
        workflow
        for workflow in finalize_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-selected-item"
    )

    transition_contract = STDLIB_LOWERING_CONTRACTS_BY_FORM["resource-transition"]
    assert transition_contract.family == "resource_finalize_drain"
    assert transition_contract.backend_kinds == ("certified_adapter", "runtime_native")
    assert transition_contract.required_statement_families == ("output_bundle",)
    assert transition_contract.alternative_statement_family_sets == (("command_step", "resource_transition"),)
    assert transition_contract.delegated_statement_family_policy == "none"
    assert transition_contract.state_root_policies == ("generated_hidden_bundle_input",)
    assert transition_contract.authority_model == "validated_structured_result_bundle"
    assert transition_contract.proof_model == "contract_validated_bundle"
    assert transition_contract.source_map_expectations == (
        "high_level_form_origin",
        "generated_step_span",
        "generated_hidden_input_span",
        "generated_hidden_path_span",
        "adapter_command_step_origin",
    )
    assert transition_contract.adapter_binding_names == ("apply_resource_transition",)
    transition_authored = transition_lowered.authored_mapping
    transition_command_step = next(
        step
        for step in _iter_nested_steps(transition_authored["steps"])
        if step.get("command", [])[:3]
        == ["python", "-m", "orchestrator.workflow_lisp.adapters.apply_resource_transition"]
    )
    transition_path = transition_command_step["output_bundle"]["path"]
    transition_hidden_input = transition_path.removeprefix("${inputs.").removesuffix("}")
    _assert_contract_matches_observed_families(
        transition_contract,
        steps=transition_authored["steps"],
    )
    _assert_contract_source_map_expectations(
        transition_contract,
        transition_lowered,
        hidden_inputs=(transition_hidden_input,),
        generated_paths=(transition_path,),
    )

    finalize_contract = STDLIB_LOWERING_CONTRACTS_BY_FORM["finalize-selected-item"]
    assert finalize_contract.family == "resource_finalize_drain"
    assert finalize_contract.backend_kinds == ("runtime_native",)
    assert finalize_contract.required_statement_families == (
        "match",
        "materialize_view",
        "output_bundle",
    )
    assert finalize_contract.alternative_statement_family_sets == ()
    assert finalize_contract.delegated_statement_family_policy == "none"
    assert finalize_contract.state_root_policies == (
        "generated_hidden_bundle_input",
        "runtime_native_resource_state",
    )
    assert finalize_contract.authority_model == "transition_audit_backed_materialized_summary"
    assert finalize_contract.proof_model == "typed_transition_then_branch_normalization"
    assert finalize_contract.source_map_expectations == (
        "high_level_form_origin",
        "generated_step_span",
        "generated_hidden_input_span",
        "generated_hidden_path_span",
    )


def test_lowering_declared_resource_transition_emits_generated_runtime_step(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_DECLARED_TRANSITION_FIXTURE,
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )
    bundle = result.validated_bundles["orchestrate"]
    step = bundle.surface.steps[0]

    assert step.kind.value == "resource_transition"
    assert step.resource_transition["declaration"].transition.name == "write-drain-status"
    assert step.resource_transition["resource"]["resource_id"] == "drain-run-state"
    assert lowered.typed_workflow.definition.name == "orchestrate"


def test_declared_transition_result_extraction_relaxes_must_exist_only(
    tmp_path: Path,
) -> None:
    path = tmp_path / "declared_transition_result_extraction.orc"
    path.write_text(
        dedent(
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.14")
              (defpath StateFile
                :kind relpath
                :under "state"
                :must-exist false)
              (defpath WorkReport
                :kind relpath
                :under "artifacts/work"
                :must-exist true)
              (defrecord ReportState
                (report WorkReport))
              (defrecord ReportRequest
                (report WorkReport))
              (defrecord ReportResult
                (report WorkReport))
              (defrecord ReportAudit
                (report WorkReport))
              (defresource report-state
                :state-type ReportState
                :backing (bridge state_path))
              (deftransition record-report
                :resource report-state
                :request-type ReportRequest
                :result-type ReportResult
                :preconditions ()
                :updates ((set-field report request.report))
                :write-set (report)
                :idempotency-fields (report)
                :result (record ReportResult :report request.report)
                :audit (record ReportAudit :report request.report)
                :conflict-policy fail_closed
                :backend runtime_native)
              (defworkflow transition-report
                ((state_path StateFile) (report WorkReport))
                -> ReportResult
                (resource-transition
                  :transition record-report
                  :resource report-state
                  :request (record ReportRequest :report report)))
              (defworkflow project-report
                ((report WorkReport))
                -> ReportResult
                (record ReportResult :report report)))
            """
        ).strip()
        + "\n"
    )

    result = compile_stage3_module(
        path,
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    transition_step = result.validated_bundles["transition-report"].surface.steps[0]
    projection_output = result.validated_bundles["project-report"].surface.outputs[
        "return__report"
    ]
    request_report_type = transition_step.resource_transition["declaration"].transition.request_type[
        "fields"
    ][0]["type"]
    transition_report_field = transition_step.common.output_bundle["fields"][0]

    assert request_report_type == {"kind": "path", "name": "WorkReport"}
    assert projection_output.definition["must_exist_target"] is True
    assert "must_exist_target" not in transition_report_field


def test_shared_validation_accepts_resource_transition_and_imported_finalize_selected_item(
    tmp_path: Path,
) -> None:
    command_boundaries = _command_boundary_environment().bindings_by_name
    transition_result = compile_stage3_module(
        VALID_TRANSITION_FIXTURE,
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    _workflow_path, _result, _validated = _compile_linked_module_fixture(
        VALID_STDLIB_FINALIZE_FIXTURE,
        tmp_path=tmp_path,
    )
    shared_finalize = compile_stage3_entrypoint(
        _workflow_path,
        source_roots=(tmp_path,),
        command_boundaries=_runtime_command_boundary_environment().bindings_by_name,
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert {
        workflow.typed_workflow.definition.name for workflow in transition_result.lowered_workflows
    } >= {"move-selected-item"}
    assert any(
        workflow.typed_workflow.definition.name.endswith("::run-selected-item")
        for workflow in shared_finalize.entry_result.lowered_workflows
    )


def test_stdlib_finalize_selected_item_executes_promoted_route_with_runtime_native_transition_and_view(
    tmp_path: Path,
) -> None:
    workflow_path, _result, validated = _compile_linked_module_fixture(
        VALID_STDLIB_FINALIZE_FIXTURE,
        tmp_path=tmp_path,
    )
    bundle = validated["resource_stdlib_finalize_selected_item_stdlib::run-selected-item"]
    _write_resource_runtime_scripts(tmp_path)

    backlog_item = tmp_path / "docs" / "backlog" / "active" / "item-1.md"
    backlog_item.parent.mkdir(parents=True, exist_ok=True)
    backlog_item.write_text("selected item\n", encoding="utf-8")
    (tmp_path / "docs" / "backlog" / "in_progress").mkdir(parents=True, exist_ok=True)
    ledger_path = tmp_path / "state" / "runtime" / "ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("[]\n", encoding="utf-8")
    (tmp_path / "state" / "items" / "item-1").mkdir(parents=True, exist_ok=True)

    state = _execute_bundle(
        bundle,
        workflow_path=workflow_path,
        workspace=tmp_path,
        run_id="resource-stdlib-runtime",
        inputs={
            "item-ctx__run__run-id": "resource-stdlib-runtime",
            "item-ctx__run__state-root": "state/runtime",
            "item-ctx__run__artifact-root": "artifacts/work",
            "item-ctx__item-id": "item-1",
            "item-ctx__state-root": "state/items/item-1",
            "item-ctx__artifact-root": "artifacts/work",
            "item-ctx__ledger": "state/runtime/ledger.json",
            "selected__item-id": "item-1",
            "selected__item-path": "docs/backlog/active/item-1.md",
            "selected__is-active": True,
        },
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["return__variant"] == "CONTINUE"
    assert state["workflow_outputs"]["return__summary-path"] == "artifacts/work/implementation-execution.md"
    assert "return__run-state" not in state["workflow_outputs"]
    assert (tmp_path / "artifacts" / "work" / "implementation-execution.md").is_file()
    resource_state_paths = sorted(tmp_path.rglob("*selected-item-outcome-state.json"))
    transition_audit_paths = sorted(tmp_path.rglob("*record-selected-item-outcome-audit.jsonl"))
    assert resource_state_paths
    assert transition_audit_paths
