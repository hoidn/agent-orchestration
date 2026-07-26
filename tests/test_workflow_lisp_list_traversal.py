from __future__ import annotations

from dataclasses import replace
import importlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import (
    ProviderExecutionResult,
    ProviderExecutor,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow.validation import (
    _WorkflowMappingValidator,
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    validate_workflow_mapping,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import (
    DoneExpr,
    FunctionCallExpr,
    LiteralExpr,
    ProcedureCallExpr,
    elaborate_expression,
)
from orchestrator.workflow_lisp.family_profiles import (
    load_workflow_family_profile_catalog,
)
from orchestrator.workflow_lisp.loops import ensure_loop_projectable_type
from orchestrator.workflow_lisp.lowering import core as lowering_core
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import (
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PrimitiveTypeRef,
    TypeParamRef,
)
from orchestrator.workflow_lisp.wcc.defunctionalize import (
    _frontend_expr_from_wcc_loop_body,
)
from orchestrator.workflow_lisp.wcc.model import (
    WCC_M4_ROUTE_SCHEMA_VERSION,
    WccIdentityFactory,
    WccLiteralAtom,
    WccLoopDone,
)
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


_LIST_TRAVERSAL_AUTHORED_HEADS = (
    "list",
    "list/map",
    "list/map-effect",
    "path/join-under",
    "list/empty?",
    "list/head",
    "list/rest",
    "list/append",
    "list/length",
)
_RUNTIME_CARDINALITY_PROVIDER_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "list_map_effect_runtime_cardinality_provider.orc"
)
_RUNTIME_CARDINALITY_WORKFLOW = (
    "list_map_effect_runtime_cardinality_provider::orchestrate"
)


def _module_source(target_dsl: str) -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target_dsl}")',
            "  (defmodule old_only_projection)",
            "  (export orchestrate)",
            "  (defworkflow orchestrate",
            "    ((value Int))",
            "    -> Int",
            "    (+ value 1)))",
        )
    )


def _int_literal_payload(schema_version: object) -> dict[str, object]:
    descriptor = {"kind": "primitive", "name": "Int"}
    return {
        "pure_expr_schema_version": schema_version,
        "result_type": descriptor,
        "bindings": {},
        "expr": {
            "kind": "literal",
            "type": descriptor,
            "value": 1,
        },
    }


def _future_list_payload(schema_version: int) -> dict[str, object]:
    item_descriptor = {"kind": "primitive", "name": "Int"}
    return {
        "pure_expr_schema_version": schema_version,
        "result_type": {"kind": "list", "item": item_descriptor},
        "bindings": {},
        "expr": {
            "kind": "list",
            "element_type": item_descriptor,
            "items": [],
        },
    }


def _build_old_only_projection(tmp_path: Path, *, target_dsl: str):
    source_path = tmp_path / "old_only_projection.orc"
    source_path.write_text(_module_source(target_dsl) + "\n", encoding="utf-8")
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    return build.build_frontend_bundle(
        build.FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="orchestrate",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _projection_payload(result) -> dict[str, object]:
    projection_steps = [
        step
        for step in result.validated_bundle.surface.steps
        if step.pure_projection is not None
    ]
    assert len(projection_steps) == 1
    return projection_steps[0].pure_projection


def _compile_runtime_cardinality_provider_fixture(workspace: Path):
    module_path = workspace / _RUNTIME_CARDINALITY_PROVIDER_FIXTURE.name
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_bytes(
        _RUNTIME_CARDINALITY_PROVIDER_FIXTURE.read_bytes()
    )
    (workspace / "provider.md").write_text(
        "Return the declared typed result.\n",
        encoding="utf-8",
    )
    profile_path = workspace / "runtime-cardinality-family-profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_family_profile.v1",
                "family_id": "runtime_cardinality_fixture",
                "workflow_name_prefixes": [],
                "target_workflows": [_RUNTIME_CARDINALITY_WORKFLOW],
                "boundary_authority_registry": None,
                "checked_public_inputs": {},
                "entry_phase_identities": {},
                "hidden_context_rules": [],
                "typed_prompt_input_rows": [
                    {
                        "workflow_name": _RUNTIME_CARDINALITY_WORKFLOW,
                        "provider_binding": provider_binding,
                        "binding_name": binding_name,
                        "renderer": {
                            "renderer_id": "canonical-json",
                            "renderer_version": 1,
                            "accepted_shape": "any_pure_value",
                        },
                        "value_source": {
                            "kind": "typed_binding_ref",
                            "ref": f"locals.{binding_name}",
                        },
                        "value_type_name": value_type_name,
                        "source_map_origin_key": _RUNTIME_CARDINALITY_WORKFLOW,
                        "u0_row_id": f"u0.fixture.{binding_name}",
                        "c0_row_id": f"c0.fixture.{binding_name}",
                        "injection_order": 0,
                    }
                    for provider_binding, binding_name, value_type_name in (
                        ("providers.review", "lens_id", "Int"),
                        (
                            "providers.synthesize",
                            "reports",
                            "List[ReviewReport]",
                        ),
                    )
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        entry_workflow="orchestrate",
        provider_externs={
            "providers.review": "deterministic-review",
            "providers.synthesize": "deterministic-synthesis",
        },
        prompt_externs={
            "prompts.review": "provider.md",
            "prompts.synthesize": "provider.md",
        },
        validate_shared=True,
        workspace_root=workspace,
        lowering_route="wcc_m4",
        family_profile_catalog=load_workflow_family_profile_catalog(
            (profile_path,)
        ),
    )
    bundle = result.validated_bundles_by_name[
        _RUNTIME_CARDINALITY_WORKFLOW
    ]
    return module_path, bundle


def test_runtime_cardinality_provider_fixture_binds_a_runtime_list(
    tmp_path: Path,
) -> None:
    module_path, bundle = _compile_runtime_cardinality_provider_fixture(
        tmp_path
    )

    public_contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound = bind_workflow_inputs(
        public_contracts,
        {"lens_ids": [3, 1, 2]},
        tmp_path,
    )

    assert module_path.read_bytes() == (
        _RUNTIME_CARDINALITY_PROVIDER_FIXTURE.read_bytes()
    )
    assert bound == {"lens_ids": [3, 1, 2]}
    nested_provider = next(
        point
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.point_kind == "effect_boundary"
        and point.node_id not in bundle.runtime_plan.ordered_node_ids
    )
    qualified = [
        checkpoint
        for checkpoint in bundle.runtime_plan.resume_checkpoints
        if checkpoint.node_id == nested_provider.node_id
        and checkpoint.runtime_step_id_mode == "qualified_iteration"
    ]
    assert len(qualified) == 1
    assert qualified[0].checkpoint_kind == "call_boundary"
    assert qualified[0].iteration_owner_node_id is not None
    assert qualified[0].iteration_step_id_suffix


def _runtime_cardinality_inputs(
    bundle,
    workspace: Path,
    lens_ids: list[int],
) -> dict[str, object]:
    public_contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    return bind_workflow_inputs(
        public_contracts,
        {"lens_ids": lens_ids},
        workspace,
    )


def _typed_prompt_input_value(prompt: str, binding_name: str) -> object:
    marker = f"## Typed Prompt Input: {binding_name}\n"
    assert prompt.count(marker) == 1
    rendered = prompt.split(marker, 1)[1].splitlines()[0]
    return json.loads(rendered)


def _deterministic_runtime_cardinality_provider_hooks(
    workspace: Path,
    *,
    events: list[dict[str, object]],
):
    control: dict[str, object] = {"runtime_step_id": None}
    original_provider = WorkflowExecutor._execute_provider_with_context

    def prepare_provider(
        _self,
        provider_name=None,
        prompt_content=None,
        env=None,
        **_kwargs,
    ):
        return (
            SimpleNamespace(
                provider_name=provider_name,
                prompt=prompt_content or "",
                env=env or {},
            ),
            None,
        )

    def execute_provider(_self, invocation, **_kwargs):
        provider_name = invocation.provider_name
        review_count = sum(
            event["provider"] == "deterministic-review"
            for event in events
        )
        if provider_name == "deterministic-review":
            lens_id = _typed_prompt_input_value(
                invocation.prompt,
                "lens_id",
            )
            assert isinstance(lens_id, int) and not isinstance(lens_id, bool)
            input_value: object = lens_id
            result_path = f"artifacts/reviews/lens-{lens_id}.md"
            report = workspace / result_path
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                f"deterministic review for lens {lens_id}\n",
                encoding="utf-8",
            )
        else:
            assert provider_name == "deterministic-synthesis"
            reports = _typed_prompt_input_value(
                invocation.prompt,
                "reports",
            )
            assert isinstance(reports, list)
            assert all(isinstance(path, str) for path in reports)
            assert review_count == len(reports)
            assert all((workspace / path).is_file() for path in reports)
            input_value = reports
            result_path = "artifacts/synthesis/panel.md"
            synthesis = workspace / result_path
            synthesis.parent.mkdir(parents=True, exist_ok=True)
            synthesis.write_text(
                "\n".join(reports) + "\n",
                encoding="utf-8",
            )
        output_path = workspace / invocation.env[
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH"
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result_path) + "\n",
            encoding="utf-8",
        )
        events.append(
            {
                "provider": provider_name,
                "runtime_step_id": control["runtime_step_id"],
                "result_path": result_path,
                "input_value": input_value,
            }
        )
        return ProviderExecutionResult(0, b"", b"", 1)

    def record_provider_identity(
        current_executor,
        step,
        context,
        state,
        runtime_step_id=None,
        **kwargs,
    ):
        assert control["runtime_step_id"] is None
        control["runtime_step_id"] = (
            runtime_step_id or current_executor._step_id(step)
        )
        try:
            return original_provider(
                current_executor,
                step,
                context,
                state,
                runtime_step_id=runtime_step_id,
                **kwargs,
            )
        finally:
            control["runtime_step_id"] = None

    return prepare_provider, execute_provider, record_provider_identity


def _run_clean_runtime_cardinality_provider(
    workspace: Path,
    *,
    run_id: str,
    lens_ids: list[int],
):
    module_path, bundle = _compile_runtime_cardinality_provider_fixture(
        workspace
    )
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        str(module_path),
        context=bundle_context_dict(bundle),
        bound_inputs=_runtime_cardinality_inputs(
            bundle,
            workspace,
            lens_ids,
        ),
    )
    events: list[dict[str, object]] = []
    prepare_provider, execute_provider, record_provider = (
        _deterministic_runtime_cardinality_provider_hooks(
            workspace,
            events=events,
        )
    )
    with (
        patch.object(
            ProviderExecutor,
            "prepare_invocation",
            prepare_provider,
        ),
        patch.object(ProviderExecutor, "execute", execute_provider),
        patch.object(
            WorkflowExecutor,
            "_execute_provider_with_context",
            record_provider,
        ),
    ):
        state = WorkflowExecutor(
            bundle,
            workspace,
            state_manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(on_error="stop")
    return module_path, bundle, state_manager, state, events


def test_runtime_cardinality_provider_executes_ordered_reviews_then_synthesis(
    tmp_path: Path,
) -> None:
    lens_ids = [3, 1, 2]
    _, _, _, state, events = _run_clean_runtime_cardinality_provider(
        tmp_path,
        run_id="runtime-cardinality-clean",
        lens_ids=lens_ids,
    )
    expected_reports = [
        f"artifacts/reviews/lens-{lens_id}.md"
        for lens_id in lens_ids
    ]

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__reports": expected_reports,
        "return__synthesis": "artifacts/synthesis/panel.md",
    }
    assert [event["provider"] for event in events] == [
        "deterministic-review",
        "deterministic-review",
        "deterministic-review",
        "deterministic-synthesis",
    ]
    assert [event["result_path"] for event in events] == [
        *expected_reports,
        "artifacts/synthesis/panel.md",
    ]
    assert [event["input_value"] for event in events] == [
        *lens_ids,
        expected_reports,
    ]
    assert (tmp_path / "artifacts/synthesis/panel.md").read_text(
        encoding="utf-8"
    ) == "\n".join(expected_reports) + "\n"


def test_runtime_cardinality_provider_resume_reuses_committed_review_without_replay(
    tmp_path: Path,
) -> None:
    lens_ids = [3, 1, 2]
    clean_workspace = tmp_path / "clean"
    interrupted_workspace = tmp_path / "interrupted"
    _, _, _, clean_state, clean_events = (
        _run_clean_runtime_cardinality_provider(
            clean_workspace,
            run_id="runtime-cardinality-clean",
            lens_ids=lens_ids,
        )
    )
    module_path, bundle = _compile_runtime_cardinality_provider_fixture(
        interrupted_workspace
    )
    run_id = "runtime-cardinality-interrupted"
    state_manager = StateManager(
        workspace=interrupted_workspace,
        run_id=run_id,
    )
    state_manager.initialize(
        str(module_path),
        context=bundle_context_dict(bundle),
        bound_inputs=_runtime_cardinality_inputs(
            bundle,
            interrupted_workspace,
            lens_ids,
        ),
    )
    events: list[dict[str, object]] = []
    prepare_provider, execute_provider, record_provider = (
        _deterministic_runtime_cardinality_provider_hooks(
            interrupted_workspace,
            events=events,
        )
    )
    original_nested = WorkflowExecutor._execute_nested_loop_step
    interrupted = {"done": False}

    class _InjectedPostProviderInterruption(BaseException):
        pass

    def interrupt_after_committed_review(
        current_executor,
        step,
        context,
        state,
        iteration_state,
        parent_scope_steps,
        **kwargs,
    ):
        result = original_nested(
            current_executor,
            step,
            context,
            state,
            iteration_state,
            parent_scope_steps,
            **kwargs,
        )
        if (
            not interrupted["done"]
            and isinstance(step.get("provider"), str)
            and result.get("status") == "completed"
            and kwargs.get("iteration_index") == 0
        ):
            interrupted["done"] = True
            raise _InjectedPostProviderInterruption
        return result

    with (
        patch.object(
            ProviderExecutor,
            "prepare_invocation",
            prepare_provider,
        ),
        patch.object(ProviderExecutor, "execute", execute_provider),
        patch.object(
            WorkflowExecutor,
            "_execute_provider_with_context",
            record_provider,
        ),
        patch.object(
            WorkflowExecutor,
            "_execute_nested_loop_step",
            interrupt_after_committed_review,
        ),
    ):
        with pytest.raises(_InjectedPostProviderInterruption):
            WorkflowExecutor(
                bundle,
                interrupted_workspace,
                state_manager,
                max_retries=0,
                retry_delay_ms=0,
            ).execute(on_error="stop")

    assert state_manager.load().status == "running"
    assert len(events) == 1
    first_committed_identity = events[0]["runtime_step_id"]
    provider_point = next(
        point
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.point_kind == "effect_boundary"
        and point.node_id not in bundle.runtime_plan.ordered_node_ids
    )
    qualified_checkpoint = next(
        checkpoint
        for checkpoint in bundle.runtime_plan.resume_checkpoints
        if checkpoint.node_id == provider_point.node_id
        and checkpoint.runtime_step_id_mode == "qualified_iteration"
    )
    from orchestrator.workflow_lisp.lexical_checkpoint_default_resume import (
        determine_runtime_default_resume_decision,
    )

    missing_authority_plan = replace(
        bundle.runtime_plan,
        resume_checkpoints=tuple(
            checkpoint
            for checkpoint in bundle.runtime_plan.resume_checkpoints
            if checkpoint is not qualified_checkpoint
        ),
    )

    def reject_unexpected_restore_selection(**_kwargs):
        raise AssertionError("invalid checkpoint authority reached selector")

    missing_authority = determine_runtime_default_resume_decision(
        state=state_manager.load().to_dict(),
        runtime_plan=missing_authority_plan,
        restart_node_id=qualified_checkpoint.iteration_owner_node_id,
        state_manager=state_manager,
        loaded_workflow=bundle,
        executable_workflow=bundle.ir,
        is_workflow_lisp=True,
        restore_selector=reject_unexpected_restore_selection,
    )
    assert missing_authority["mode"] == "FAIL_CLOSED"
    assert missing_authority["diagnostics"] == [
        "lexical_default_resume_prior_boundary_unordered"
    ]
    ambiguous_authority = determine_runtime_default_resume_decision(
        state=state_manager.load().to_dict(),
        runtime_plan=replace(
            bundle.runtime_plan,
            resume_checkpoints=(
                *bundle.runtime_plan.resume_checkpoints,
                qualified_checkpoint,
            ),
        ),
        restart_node_id=qualified_checkpoint.iteration_owner_node_id,
        state_manager=state_manager,
        loaded_workflow=bundle,
        executable_workflow=bundle.ir,
        is_workflow_lisp=True,
        restore_selector=reject_unexpected_restore_selection,
    )
    assert ambiguous_authority["mode"] == "FAIL_CLOSED"
    assert ambiguous_authority["diagnostics"] == [
        "lexical_default_resume_prior_boundary_ambiguous"
    ]

    resume_manager = StateManager(
        workspace=interrupted_workspace,
        run_id=run_id,
    )
    resume_manager.load()
    with (
        patch.object(
            ProviderExecutor,
            "prepare_invocation",
            prepare_provider,
        ),
        patch.object(ProviderExecutor, "execute", execute_provider),
        patch.object(
            WorkflowExecutor,
            "_execute_provider_with_context",
            record_provider,
        ),
    ):
        resumed = WorkflowExecutor(
            bundle,
            interrupted_workspace,
            resume_manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed", resumed
    assert resumed["workflow_outputs"] == clean_state["workflow_outputs"]
    assert events == clean_events
    assert (
        sum(
            event["runtime_step_id"] == first_committed_identity
            for event in events
        )
        == 1
    )
    assert (
        interrupted_workspace / "artifacts/synthesis/panel.md"
    ).read_bytes() == (
        clean_workspace / "artifacts/synthesis/panel.md"
    ).read_bytes()
    default_resume = json.loads(
        resume_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )
    assert default_resume["selection_reason"] == "validated_prior_boundary"


def _build_source(
    tmp_path: Path,
    source: str,
    *,
    entry_workflow: str = "orchestrate",
    filename: str | None = None,
    source_roots: tuple[Path, ...] | None = None,
    lowering_route: str | None = None,
):
    if filename is None:
        module_match = re.search(r"\(defmodule\s+([^()\s]+)\)", source)
        assert module_match is not None
        filename = f"{module_match.group(1)}.orc"
    source_path = tmp_path / filename
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source.strip() + "\n", encoding="utf-8")
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    return build.build_frontend_bundle(
        build.FrontendBuildRequest(
            source_path=source_path,
            source_roots=source_roots or (tmp_path,),
            entry_workflow=entry_workflow,
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
            lowering_route=lowering_route,
        )
    )


def _diagnostic_code_for_source(
    tmp_path: Path,
    source: str,
    *,
    filename: str | None = None,
) -> str:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_source(tmp_path, source, filename=filename)
    return excinfo.value.diagnostics[0].code


def _expression_syntax(source: str) -> SyntaxNode:
    parse_tree = read_sexpr_text(
        source,
        source_path="inline_list_traversal_compatibility.orc",
    )
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_list_traversal_compatibility.orc",
        form_path=("workflow-lisp", "list-traversal-compatibility"),
    )


def _write_legacy_list_traversal_macro(
    tmp_path: Path,
    *,
    head: str,
) -> None:
    module_path = tmp_path / "legacy" / "list-macros.orc"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.17")
          (defmodule legacy/list-macros)
          (export {head})
          (defmacro {head} (value) value))
        """.strip()
        + "\n",
        encoding="utf-8",
    )


def _write_list_map_template_macro(tmp_path: Path) -> None:
    module_path = tmp_path / "helpers" / "list-map-macros.orc"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule helpers/list-map-macros)
          (export map-plus-one)
          (defmacro map-plus-one (values)
            (list/map ((item values))
              (+ item 1))))
        """.strip()
        + "\n",
        encoding="utf-8",
    )


def test_target_218_is_accepted_and_owns_one_list_traversal_gate() -> None:
    syntax = importlib.import_module("orchestrator.workflow_lisp.syntax")

    module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.18"),
            source_path="target_218_list_traversal.orc",
        )
    )

    assert module.target_dsl_version == "2.18"
    assert syntax.LIST_TRAVERSAL_MIN_TARGET_DSL_VERSION == "2.18"


def test_shared_mapping_validation_accepts_target_218(tmp_path: Path) -> None:
    result = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping={
                "version": "2.18",
                "name": "target-218",
                "steps": [{"name": "Done", "command": ["echo", "done"]}],
            },
            workflow_path=tmp_path / "target-218.orc",
            frontend_kind="workflow_lisp",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )

    assert result.errors == ()
    assert result.bundle is not None
    assert result.bundle.surface.version == "2.18"


def test_unknown_target_versions_still_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(
            read_sexpr_text(
                _module_source("2.19"),
                source_path="target_219_list_traversal.orc",
            )
        )
    assert excinfo.value.diagnostics[0].code == "target_dsl_unsupported"

    result = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping={
                "version": "2.19",
                "name": "target-219",
                "steps": [{"name": "Done", "command": ["echo", "done"]}],
            },
            workflow_path=tmp_path / "target-219.orc",
            frontend_kind="workflow_lisp",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )
    assert result.bundle is None
    assert any("Unsupported version '2.19'" in error.message for error in result.errors)


def test_pure_runtime_accepts_existing_nodes_in_schema_2() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    payload = _int_literal_payload(2)

    assert pure_expr.validate_pure_expr_payload(payload) is payload
    assert pure_expr.evaluate_pure_expr(payload) == 1


@pytest.mark.parametrize("schema_version", (0, 3, True, 2.0, "2"))
def test_unknown_or_non_integer_pure_schema_versions_fail_closed(
    schema_version: object,
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(
            _int_literal_payload(schema_version)
        )

    assert excinfo.value.code == "pure_expr_schema_mismatch"


def test_schema_1_rejects_schema_2_list_node() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(
            _future_list_payload(1)
        )

    assert excinfo.value.code == "pure_expr_schema_mismatch"


def test_old_only_target_218_projection_stays_on_schema_1(
    tmp_path: Path,
) -> None:
    target_217_projection = _projection_payload(
        _build_old_only_projection(tmp_path, target_dsl="2.17")
    )
    target_218_projection = _projection_payload(
        _build_old_only_projection(tmp_path, target_dsl="2.18")
    )

    assert target_218_projection["payload"]["pure_expr_schema_version"] == 1
    assert target_218_projection["payload"] == target_217_projection["payload"]
    assert (
        target_218_projection["payload_digest"]
        == target_217_projection["payload_digest"]
    )


def test_target_217_schema_1_projection_digest_is_frozen(
    tmp_path: Path,
) -> None:
    projection = _projection_payload(
        _build_old_only_projection(tmp_path, target_dsl="2.17")
    )

    assert projection["payload"]["pure_expr_schema_version"] == 1
    assert projection["payload_digest"] == (
        "sha256:a40fe0237ee12f03aff127afcc613dfa89daad5a0e586c0a49072289a50f0323"
    )


_BOOL = {"kind": "primitive", "name": "Bool"}
_INT = {"kind": "primitive", "name": "Int"}
_STRING = {"kind": "primitive", "name": "String"}
_LIST_INT = {"kind": "list", "item": _INT}


def _literal(descriptor: dict[str, object], value: object) -> dict[str, object]:
    return {"kind": "literal", "type": descriptor, "value": value}


def _list_node(*items: dict[str, object]) -> dict[str, object]:
    return {
        "kind": "list",
        "element_type": _INT,
        "items": list(items),
    }


def _pure_payload(
    expr: dict[str, object],
    *,
    result_type: dict[str, object],
    schema_version: int = 2,
    bindings: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "pure_expr_schema_version": schema_version,
        "result_type": result_type,
        "bindings": bindings or {},
        "expr": expr,
    }


def _list_map_node(
    *,
    source: dict[str, object],
    binder_name: str = "item",
    binder_type: dict[str, object] = _INT,
    body: dict[str, object] | None = None,
    result_element_type: dict[str, object] = _INT,
) -> dict[str, object]:
    return {
        "kind": "list_map",
        "source": source,
        "binder": {"name": binder_name, "type": binder_type},
        "body": (
            body
            if body is not None
            else {"kind": "binding", "name": binder_name}
        ),
        "result_element_type": result_element_type,
    }


def _path_descriptor(
    *,
    name: str = "Path.state-root",
    under: object = "state",
    must_exist_target: object = False,
) -> dict[str, object]:
    return {
        "kind": "path",
        "name": name,
        "under": under,
        "must_exist_target": must_exist_target,
    }


def _path_join_node(
    child: object,
    *,
    path_type: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "kind": "path_join_under",
        "path_type": (
            path_type
            if path_type is not None
            else _path_descriptor()
        ),
        "child": _literal(_STRING, child),
    }


def _nonempty_head_node(source: dict[str, object]) -> dict[str, object]:
    return {
        "kind": "list_nonempty_head",
        "source": source,
        "element_type": _INT,
        "compiler_owned": True,
        "invariant_diagnostic": "list_nonempty_invariant_broken",
    }


@pytest.mark.parametrize(
    ("expr", "result_type"),
    (
        (_list_node(), _LIST_INT),
        (
            _list_map_node(source=_list_node(_literal(_INT, 1))),
            _LIST_INT,
        ),
        (_path_join_node("run.json"), _path_descriptor()),
        (
            _nonempty_head_node(_list_node(_literal(_INT, 1))),
            _INT,
        ),
    ),
    ids=("list", "list-map", "path-join-under", "list-nonempty-head"),
)
def test_schema_1_rejects_every_schema_2_node(
    expr: dict[str, object],
    result_type: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(
            _pure_payload(
                expr,
                result_type=result_type,
                schema_version=1,
            )
        )

    assert excinfo.value.code == "pure_expr_schema_mismatch"


@pytest.mark.parametrize(
    ("operator", "args", "result_type"),
    (
        ("list/empty?", [_list_node()], _BOOL),
        ("list/head", [_list_node()], {"kind": "optional", "item": _INT}),
        ("list/rest", [_list_node()], _LIST_INT),
        ("list/append", [_list_node(), _literal(_INT, 1)], _LIST_INT),
        ("list/length", [_list_node()], _INT),
    ),
)
def test_schema_1_rejects_every_schema_2_list_operator(
    operator: str,
    args: list[dict[str, object]],
    result_type: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        {"kind": "op", "operator": operator, "args": args},
        result_type=result_type,
        schema_version=1,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_schema_mismatch"


def test_schema_2_node_count_includes_every_list_item_and_map_body_node() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    expr = _list_map_node(
        source=_list_node(
            _literal(_INT, 1),
            _literal(_INT, 2),
        ),
        body={
            "kind": "op",
            "operator": "+",
            "args": [
                {"kind": "binding", "name": "item"},
                _literal(_INT, 1),
            ],
        },
    )
    payload = _pure_payload(expr, result_type=_LIST_INT)

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload, max_nodes=6)

    assert excinfo.value.code == "pure_expr_payload_too_large"
    assert pure_expr.validate_pure_expr_payload(payload, max_nodes=7) is payload


def test_list_constructor_rejects_element_descriptor_mismatch() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_node(_literal(_STRING, "wrong")),
        result_type=_LIST_INT,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


@pytest.mark.parametrize(
    "expr",
    (
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            binder_type=_STRING,
            result_element_type=_STRING,
        ),
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            result_element_type=_STRING,
        ),
    ),
    ids=("source-binder", "body-result"),
)
def test_list_map_rejects_descriptor_mismatch(
    expr: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        expr,
        result_type={"kind": "list", "item": _STRING},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


@pytest.mark.parametrize(
    ("binder_name", "bindings"),
    (
        (
            "item",
            {"item": {"type": _INT, "value": 99}},
        ),
        ("__compiler_item", {}),
    ),
    ids=("top-level-collision", "reserved-name"),
)
def test_list_map_rejects_binder_collisions_and_reserved_names(
    binder_name: str,
    bindings: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            binder_name=binder_name,
        ),
        result_type=_LIST_INT,
        bindings=bindings,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "list_map_binder_invalid"


def test_nested_list_map_rejects_duplicate_lexical_binder() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    nested = _list_map_node(
        source=_list_node(_literal(_INT, 2)),
        binder_name="item",
    )
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            binder_name="item",
            body=nested,
            result_element_type=_LIST_INT,
        ),
        result_type={"kind": "list", "item": _LIST_INT},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "list_map_binder_invalid"


def test_list_map_rejects_out_of_scope_binding_reference() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            body={"kind": "binding", "name": "not_in_scope"},
        ),
        result_type=_LIST_INT,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_payload_invalid"


def test_list_map_binder_is_evaluator_local_and_source_is_evaluated_once() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    class CountingList(list[int]):
        def __init__(self, values: list[int]) -> None:
            super().__init__(values)
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            return super().__iter__()

    source = CountingList([3, 1, 2])
    payload = _pure_payload(
        _list_map_node(
            source={"kind": "binding", "name": "source"},
            body={
                "kind": "op",
                "operator": "+",
                "args": [
                    {"kind": "binding", "name": "item"},
                    {"kind": "binding", "name": "offset"},
                ],
            },
        ),
        result_type=_LIST_INT,
        bindings={
            "source": {"type": _LIST_INT},
            "offset": {"type": _INT},
        },
    )

    result = pure_expr.evaluate_pure_expr(
        payload,
        resolved_bindings={"source": source, "offset": 10},
    )

    assert result == [13, 11, 12]
    assert source.iterations == 1
    assert result is not source

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(
            payload,
            resolved_bindings={"source": source, "offset": 10, "item": 99},
        )
    assert excinfo.value.code == "pure_expr_binding_unexpected"


def test_list_append_returns_fresh_array_without_mutating_input() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    source = [1, 2]
    payload = _pure_payload(
        {
            "kind": "op",
            "operator": "list/append",
            "args": [
                {"kind": "binding", "name": "source"},
                _literal(_INT, 3),
            ],
        },
        result_type=_LIST_INT,
        bindings={"source": {"type": _LIST_INT}},
    )

    result = pure_expr.evaluate_pure_expr(
        payload,
        resolved_bindings={"source": source},
    )

    assert source == [1, 2]
    assert result == [1, 2, 3]
    assert result is not source


@pytest.mark.parametrize(
    "under",
    ("", ".", "/state", "state/", "state//runs", "state/./runs", "state/../runs"),
)
def test_path_join_under_rejects_malformed_selected_root(under: str) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    descriptor = _path_descriptor(under=under)
    payload = _pure_payload(
        _path_join_node("run.json", path_type=descriptor),
        result_type=descriptor,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "path_join_under_root_invalid"


@pytest.mark.parametrize("child", ("", ".", "reports/", "reports//one.md", "reports/./one.md"))
def test_path_join_under_rejects_empty_or_malformed_child(child: str) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _path_join_node(child),
        result_type=_path_descriptor(),
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "path_join_under_child_invalid"


@pytest.mark.parametrize("child", ("/absolute.md", "../escape.md", "safe/../../escape.md"))
def test_path_join_under_rejects_absolute_or_escaping_child(child: str) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _path_join_node(child),
        result_type=_path_descriptor(),
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "path_join_under_escape"


def test_path_join_under_requires_exact_path_descriptor_and_string_child() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    invalid_type_payload = _pure_payload(
        _path_join_node(
            "run.json",
            path_type={"kind": "primitive", "name": "String"},
        ),
        result_type=_STRING,
    )
    invalid_child_payload = _pure_payload(
        {
            "kind": "path_join_under",
            "path_type": _path_descriptor(),
            "child": _literal(_INT, 1),
        },
        result_type=_path_descriptor(),
    )
    unresolved_type_payload = _pure_payload(
        {
            "kind": "path_join_under",
            "path_type": {},
            "child": _literal(_STRING, "run.json"),
        },
        result_type=_STRING,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as type_excinfo:
        pure_expr.evaluate_pure_expr(invalid_type_payload)
    assert type_excinfo.value.code == "path_join_under_type_invalid"

    with pytest.raises(pure_expr.PureExprEvaluationError) as child_excinfo:
        pure_expr.evaluate_pure_expr(invalid_child_payload)
    assert child_excinfo.value.code == "pure_expr_operand_type_mismatch"

    with pytest.raises(pure_expr.PureExprEvaluationError) as unresolved_excinfo:
        pure_expr.evaluate_pure_expr(unresolved_type_payload)
    assert unresolved_excinfo.value.code == "path_join_under_type_invalid"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("compiler_owned", None),
        ("compiler_owned", False),
        ("invariant_diagnostic", None),
        ("invariant_diagnostic", "some_other_code"),
    ),
)
def test_list_nonempty_head_rejects_missing_compiler_contract(
    field: str,
    value: object,
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    expr = _nonempty_head_node(_list_node(_literal(_INT, 1)))
    if value is None:
        del expr[field]
    else:
        expr[field] = value
    payload = _pure_payload(expr, result_type=_INT)

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_payload_invalid"


def test_list_nonempty_head_enforces_compiler_nonempty_invariant() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    empty_payload = _pure_payload(
        _nonempty_head_node(_list_node()),
        result_type=_INT,
    )
    present_payload = _pure_payload(
        _nonempty_head_node(_list_node(_literal(_INT, 7))),
        result_type=_INT,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(empty_payload)
    assert excinfo.value.code == "list_nonempty_invariant_broken"

    assert pure_expr.evaluate_pure_expr(present_payload) == 7


def test_validate_rejects_list_item_vs_element_descriptor_mismatch() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_node(_literal(_STRING, "wrong")),
        result_type=_LIST_INT,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_validate_rejects_list_map_source_vs_binder_descriptor_mismatch() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            binder_type=_STRING,
            result_element_type=_STRING,
        ),
        result_type={"kind": "list", "item": _STRING},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_validate_rejects_list_map_body_descriptor_mismatch_for_empty_source() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(),
            result_element_type=_STRING,
        ),
        result_type={"kind": "list", "item": _STRING},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_validate_rejects_nonempty_head_source_vs_element_descriptor() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    expr = _nonempty_head_node(_list_node(_literal(_INT, 1)))
    expr["element_type"] = _STRING
    payload = _pure_payload(expr, result_type=_STRING)

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_validate_rejects_root_expr_vs_payload_result_descriptor() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _literal(_INT, 1),
        result_type=_STRING,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_payload_invalid"


@pytest.mark.parametrize(
    ("declared_name", "canonical_name"),
    (
        ("ConsumerPath", "example/types::ConsumerPath"),
        ("one/types::ConsumerPath", "two/types::ConsumerPath"),
    ),
)
def test_validate_accepts_canonical_path_name_for_same_declared_path(
    declared_name: str,
    canonical_name: str,
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    declared_path = _path_descriptor(name=declared_name)
    canonical_path = _path_descriptor(name=canonical_name)
    record_type = {
        "kind": "record",
        "name": "PathEnvelope",
        "fields": [{"name": "path", "type": declared_path}],
    }
    payload = _pure_payload(
        {
            "kind": "record",
            "type": record_type,
            "fields": [
                {
                    "name": "path",
                    "value": {"kind": "binding", "name": "path"},
                }
            ],
        },
        result_type=record_type,
        bindings={"path": {"type": canonical_path, "value": "state/run.json"}},
    )

    assert pure_expr.validate_pure_expr_payload(payload) is payload


@pytest.mark.parametrize(
    ("declared_path", "observed_path"),
    (
        (
            _path_descriptor(name="one/types::ConsumerPath"),
            _path_descriptor(name="two/types::OtherPath"),
        ),
        (
            _path_descriptor(name="ConsumerPath"),
            _path_descriptor(
                name="example/types::ConsumerPath",
                under="artifacts",
            ),
        ),
        (
            _path_descriptor(name="ConsumerPath"),
            _path_descriptor(
                name="example/types::ConsumerPath",
                must_exist_target=True,
            ),
        ),
    ),
)
def test_validate_rejects_different_path_identity_or_contract(
    declared_path: dict[str, object],
    observed_path: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    record_type = {
        "kind": "record",
        "name": "PathEnvelope",
        "fields": [{"name": "path", "type": declared_path}],
    }
    payload = _pure_payload(
        {
            "kind": "record",
            "type": record_type,
            "fields": [
                {
                    "name": "path",
                    "value": {"kind": "binding", "name": "path"},
                }
            ],
        },
        result_type=record_type,
        bindings={"path": {"type": observed_path, "value": "state/run.json"}},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_validate_accepts_nested_container_path_alias() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    declared_type = {
        "kind": "list",
        "item": {
            "kind": "optional",
            "item": _path_descriptor(name="ConsumerPath"),
        },
    }
    canonical_type = {
        "kind": "list",
        "item": {
            "kind": "optional",
            "item": _path_descriptor(name="example/types::ConsumerPath"),
        },
    }
    payload = _pure_payload(
        {"kind": "binding", "name": "paths"},
        result_type=declared_type,
        bindings={
            "paths": {
                "type": canonical_type,
                "value": [None, "state/run.json"],
            }
        },
    )

    assert pure_expr.validate_pure_expr_payload(payload) is payload


def test_validate_rejects_nested_container_path_contract_mismatch() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    declared_type = {
        "kind": "list",
        "item": {
            "kind": "optional",
            "item": _path_descriptor(name="ConsumerPath"),
        },
    }
    mismatched_type = {
        "kind": "list",
        "item": {
            "kind": "optional",
            "item": _path_descriptor(
                name="example/types::ConsumerPath",
                under="artifacts",
            ),
        },
    }
    payload = _pure_payload(
        {"kind": "binding", "name": "paths"},
        result_type=declared_type,
        bindings={
            "paths": {
                "type": mismatched_type,
                "value": ["artifacts/run.json"],
            }
        },
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_payload_invalid"


def test_validate_rejects_non_string_path_child_descriptor() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        {
            "kind": "path_join_under",
            "path_type": _path_descriptor(),
            "child": _literal(_INT, 1),
        },
        result_type=_path_descriptor(),
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


@pytest.mark.parametrize(
    ("operator", "args", "result_type", "expected_code"),
    (
        (
            "list/empty?",
            [_literal(_STRING, "not-a-list")],
            _BOOL,
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/head",
            [_literal(_STRING, "not-a-list")],
            {"kind": "optional", "item": _INT},
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/rest",
            [_literal(_STRING, "not-a-list")],
            _LIST_INT,
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/append",
            [_list_node(), _literal(_STRING, "wrong")],
            _LIST_INT,
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/length",
            [_literal(_STRING, "not-a-list")],
            _INT,
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/empty?",
            [_list_node()],
            _INT,
            "pure_expr_payload_invalid",
        ),
        (
            "list/head",
            [_list_node()],
            {"kind": "optional", "item": _STRING},
            "pure_expr_payload_invalid",
        ),
        (
            "list/rest",
            [_list_node()],
            {"kind": "list", "item": _STRING},
            "pure_expr_payload_invalid",
        ),
        (
            "list/append",
            [_list_node(), _literal(_INT, 1)],
            {"kind": "list", "item": _STRING},
            "pure_expr_payload_invalid",
        ),
        (
            "list/length",
            [_list_node()],
            _BOOL,
            "pure_expr_payload_invalid",
        ),
    ),
)
def test_validate_enforces_schema_2_list_operator_operand_and_result_types(
    operator: str,
    args: list[dict[str, object]],
    result_type: dict[str, object],
    expected_code: str,
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        {"kind": "op", "operator": operator, "args": args},
        result_type=result_type,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == expected_code


def test_frontend_list_constructor_and_total_operators_synthesize_exact_types(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule list_surface)
          (export orchestrate)
          (defun is-empty ((items List[Int])) -> Bool
            (list/empty? items))
          (defun first-item ((items List[Int])) -> Optional[Int]
            (list/head items))
          (defun remaining-items ((items List[Int])) -> List[Int]
            (list/rest items))
          (defun append-item ((items List[Int]) (item Int)) -> List[Int]
            (list/append items item))
          (defun item-count ((items List[Int])) -> Int
            (list/length items))
          (defworkflow orchestrate
            ((items List[Int]))
            -> List[Int]
            (append-item (list 1 2) 3)))
        """,
    )

    projection = _projection_payload(result)
    payload = projection["payload"]
    assert payload["pure_expr_schema_version"] == 2
    # Each helper body is checked against its distinct declared result above;
    # reaching a bundle proves all five operator result types synthesized.
    assert payload["expr"]["kind"] == "op"
    assert payload["expr"]["operator"] == "list/append"
    assert payload["expr"]["args"][0] == {
        "kind": "list",
        "element_type": _INT,
        "items": (
            _literal(_INT, 1),
            _literal(_INT, 2),
        ),
    }


def test_frontend_list_constructor_rejects_mixed_element_types(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule list_mismatch)
              (export orchestrate)
              (defworkflow orchestrate () -> List[Int]
                (list 1 "wrong")))
            """,
        )
        == "pure_expr_operand_type_mismatch"
    )


@pytest.mark.parametrize(
    "body",
    (
        "(list)",
        "(record Box :items (list))",
        "(variant Choice READY :items (list))",
        "(identity-list (list))",
        "(if true (list) (list 1))",
    ),
    ids=(
        "declared-return",
        "record-field",
        "union-field",
        "direct-callable-argument",
        "if-branch",
    ),
)
def test_empty_list_uses_only_enumerated_exact_expected_type_contexts(
    tmp_path: Path,
    body: str,
) -> None:
    definitions = """
      (defrecord Box (items List[Int]))
      (defunion Choice
        (EMPTY)
        (READY (items List[Int])))
      (defun identity-list ((items List[Int])) -> List[Int] items)
    """
    params = "()"
    return_type = (
        "Box"
        if body.startswith("(record")
        else "Choice"
        if body.startswith("(variant")
        else "List[Int]"
    )
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule empty_context)
          (export orchestrate)
          {definitions}
          (defworkflow orchestrate {params} -> {return_type}
            {body}))
        """,
    )

    if return_type == "List[Int]":
        payload = _projection_payload(result)["payload"]
        assert payload["pure_expr_schema_version"] == 2


def test_empty_list_uses_declared_return_context_through_match_arms(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "match_empty_context.orc"
    source_path.write_text(
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule match_empty_context)
          (defunion Choice
            (EMPTY)
            (READY (items List[Int])))
          (defun choice-items ((choice Choice)) -> List[Int]
            (match choice
              ((EMPTY value) (list))
              ((READY value) (list 1)))))
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    definitions = importlib.import_module("orchestrator.workflow_lisp.definitions")
    functions = importlib.import_module("orchestrator.workflow_lisp.functions")
    reader = importlib.import_module("orchestrator.workflow_lisp.reader")
    syntax = importlib.import_module("orchestrator.workflow_lisp.syntax")
    type_env_module = importlib.import_module("orchestrator.workflow_lisp.type_env")
    traversal = importlib.import_module("orchestrator.workflow_lisp.expression_traversal")
    expressions = importlib.import_module("orchestrator.workflow_lisp.expressions")

    syntax_module = syntax.build_syntax_module(reader.read_sexpr_file(source_path))
    module = definitions.elaborate_definition_module(
        compiler._definition_only_syntax_module(syntax_module)
    )
    compiler._validate_definition_module(module)
    type_env = type_env_module.FrontendTypeEnvironment.from_module(module)
    function_defs = functions.elaborate_function_definitions(syntax_module)
    catalog = functions.build_function_catalog(function_defs, type_env=type_env)
    typed = functions.typecheck_function_definitions(
        function_defs,
        type_env=type_env,
        function_catalog=catalog,
    )

    list_nodes = [
        node
        for node in traversal.walk_expr(typed[0].typed_body.expr)
        if isinstance(node, expressions.ListExpr)
    ]
    assert [node.element_type_ref.name for node in list_nodes] == ["Int", "Int"]


def test_empty_list_in_loop_state_lowers_as_one_collection_field(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule empty_loop_state_context)
          (export orchestrate)
          (defworkflow orchestrate () -> Int
            (loop/recur
              :max 1
              :state (loop-state
                (items List[Int] (list)))
              (fn (state)
                (done 0)))))
        """,
    )

    repeat_step = next(
        step
        for step in result.validated_bundle.surface.steps
        if step.repeat_until is not None
    )
    state_fields = {
        name: dict(contract.definition)
        for name, contract in repeat_step.repeat_until.outputs.items()
        if name.startswith("state")
    }
    assert set(state_fields) == {"state__items"}
    assert {
        key: value
        for key, value in state_fields["state__items"].items()
        if key != "from"
    } == {
        "kind": "collection",
        "type": "list",
        "items": {"type": "integer"},
    }
    assert state_fields["state__items"]["from"]["ref"].endswith(
        ".artifacts.state__items"
    )


@pytest.mark.parametrize(
    "list_type",
    (
        "List[String]",
        "List[Path.artifact-root]",
    ),
)
def test_loop_recur_accepts_whole_list_transportable_state_and_result(
    tmp_path: Path,
    list_type: str,
) -> None:
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule list_loop_contract)
          (export orchestrate)
          (defworkflow orchestrate ((items {list_type})) -> {list_type}
            (loop/recur
              :max 1
              :state items
              (fn (state)
                (done state)))))
        """,
    )

    repeat_step = next(
        step
        for step in result.validated_bundle.surface.steps
        if step.repeat_until is not None
    )
    assert repeat_step.repeat_until.outputs["state"].kind == "collection"
    assert repeat_step.repeat_until.outputs["state"].value_type == "list"
    assert repeat_step.repeat_until.outputs["result"].kind == "collection"
    assert repeat_step.repeat_until.outputs["result"].value_type == "list"


@pytest.mark.parametrize("state_kind", ("optional", "map"))
def test_loop_recur_keeps_top_level_optional_and_map_state_unsupported(
    state_kind: str,
) -> None:
    string_type = PrimitiveTypeRef(name="String")
    state_type = (
        OptionalTypeRef(name="Optional[String]", item_type_ref=string_type)
        if state_kind == "optional"
        else MapTypeRef(
            name="Map[String,String]",
            key_type_ref=string_type,
            value_type_ref=string_type,
        )
    )
    span = _expression_syntax("1").span

    with pytest.raises(LispFrontendCompileError) as excinfo:
        ensure_loop_projectable_type(
            state_type,
            code="loop_recur_state_type_invalid",
            span=span,
            form_path=("workflow-lisp", "defworkflow", "orchestrate"),
        )

    assert excinfo.value.diagnostics[0].code == "loop_recur_state_type_invalid"


@pytest.mark.parametrize("state_kind", ("optional", "map"))
def test_loop_recur_keeps_generic_top_level_optional_and_map_state_unsupported(
    state_kind: str,
) -> None:
    type_param = TypeParamRef(name="T")
    string_type = PrimitiveTypeRef(name="String")
    state_type = (
        OptionalTypeRef(name="Optional[T]", item_type_ref=type_param)
        if state_kind == "optional"
        else MapTypeRef(
            name="Map[String,T]",
            key_type_ref=string_type,
            value_type_ref=type_param,
        )
    )
    span = _expression_syntax("1").span

    with pytest.raises(LispFrontendCompileError) as excinfo:
        ensure_loop_projectable_type(
            state_type,
            code="loop_recur_state_type_invalid",
            span=span,
            form_path=("workflow-lisp", "defworkflow", "orchestrate"),
        )

    assert excinfo.value.diagnostics[0].code == "loop_recur_state_type_invalid"


def test_loop_recur_defers_unresolved_generic_list_projection_validation() -> None:
    span = _expression_syntax("1").span

    ensure_loop_projectable_type(
        ListTypeRef(
            name="List[T]",
            item_type_ref=TypeParamRef(name="T"),
        ),
        code="loop_recur_state_type_invalid",
        span=span,
        form_path=("workflow-lisp", "defworkflow", "orchestrate"),
    )


def test_generic_list_loop_revalidates_supported_concrete_specialization(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule generic_supported_list_loop)
          (export orchestrate)
          (defproc carry-list
            :forall (T)
            ((items List[T]))
            -> List[T]
            :effects ()
            :lowering inline
            (loop/recur :max 1 :state items
              (fn (state)
                (done state))))
          (defworkflow orchestrate ((items List[String])) -> List[String]
            (carry-list items)))
        """,
    )

    assert result.validated_bundle.surface.outputs["__result__"].kind == "collection"


def test_generic_list_loop_rejects_unsupported_concrete_specialization(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule generic_unsupported_list_loop)
              (export orchestrate)
              (defrecord Item
                (value Int))
              (defproc carry-list
                :forall (T)
                ((items List[T]))
                -> List[T]
                :effects ()
                :lowering inline
                (loop/recur :max 1 :state items
                  (fn (state)
                    (done state))))
              (defproc instantiate-unsupported
                ((items List[Item]))
                -> Int
                :effects ()
                :lowering inline
                (let* ((ignored (carry-list items)))
                  0))
              (defworkflow orchestrate () -> Int
                0))
            """,
        )
        == "list_collection_contract_unsupported"
    )


@pytest.mark.parametrize(
    "state_type",
    (
        "Optional[T]",
        "Map[String,T]",
    ),
)
def test_generic_optional_and_map_loops_fail_before_specialization(
    tmp_path: Path,
    state_type: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule generic_unsupported_container_loop)
              (export orchestrate)
              (defproc carry-container
                :forall (T)
                ((value {state_type}))
                -> {state_type}
                :effects ()
                :lowering inline
                (loop/recur :max 1 :state value
                  (fn (state)
                    (done state))))
              (defworkflow orchestrate () -> Int
                0))
            """,
        )
        == "loop_recur_state_type_invalid"
    )


@pytest.mark.parametrize(
    ("element_definition", "seed_expr"),
    (
        ("(defrecord Item (value Int))", "(list (record Item :value 1))"),
        (
            "(defunion Item (READY (value Int)))",
            "(list (variant Item READY :value 1))",
        ),
    ),
)
def test_loop_recur_rejects_record_and_union_collection_elements(
    tmp_path: Path,
    element_definition: str,
    seed_expr: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule unsupported_loop_list)
              (export orchestrate)
              {element_definition}
              (defworkflow orchestrate () -> Int
                (loop/recur
                  :max 1
                  :state {seed_expr}
                  (fn (state)
                    (done 0)))))
            """,
        )
        == "list_collection_contract_unsupported"
    )


@pytest.mark.parametrize(
    "body",
    (
        "(list)",
        "(let* ((items (list))) items)",
    ),
    ids=("standalone-wrong-expected-type", "unannotated-let"),
)
def test_empty_list_without_exact_list_context_fails_closed(
    tmp_path: Path,
    body: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule empty_context_required)
              (export orchestrate)
              (defworkflow orchestrate () -> Int
                {body}))
            """,
        )
        == "list_empty_type_context_required"
    )


def test_frontend_pure_map_captures_lexically_and_lowers_one_schema2_value(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule pure_map)
          (export orchestrate)
          (defworkflow orchestrate
            ((items List[Int]) (offset Int))
            -> List[Int]
            (list/map ((item items))
              (+ item offset))))
        """,
    )

    projection = _projection_payload(result)
    payload = projection["payload"]
    assert payload["pure_expr_schema_version"] == 2
    assert payload["expr"]["kind"] == "list_map"
    assert payload["expr"]["source"] == {"kind": "binding", "name": "items"}
    assert payload["expr"]["binder"] == {"name": "item", "type": _INT}
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    assert pure_expr.evaluate_pure_expr(
        payload,
        resolved_bindings={"items": [3, 1, 2], "offset": 10},
    ) == [13, 11, 12]


@pytest.mark.parametrize(
    "binder",
    (
        "()",
        "((item))",
        "((item xs) (other xs))",
        "((__compiler_item xs))",
    ),
)
def test_frontend_pure_map_rejects_invalid_binder_shapes(
    tmp_path: Path,
    binder: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule invalid_map_binder)
              (export orchestrate)
              (defworkflow orchestrate ((xs List[Int])) -> List[Int]
                (list/map {binder} 1)))
            """,
        )
        == "list_map_binder_invalid"
    )


def test_frontend_pure_map_rejects_effectful_body(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule impure_map)
              (export orchestrate)
              (defworkflow child ((value Int)) -> Int value)
              (defworkflow orchestrate ((xs List[Int])) -> List[Int]
                (list/map ((item xs))
                  (call child :value item))))
            """,
        )
        == "list_map_body_effect_forbidden"
    )


@pytest.mark.parametrize(
    "element_type",
    (
        "Optional[String]",
        "Map[String,Int]",
    ),
)
def test_frontend_pure_map_accepts_whole_list_transportable_nested_shapes(
    tmp_path: Path,
    element_type: str,
) -> None:
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule nested_map)
          (export orchestrate)
          (defun map-items
            ((items List[{element_type}]))
            -> List[{element_type}]
            (list/map ((item items)) item))
          (defworkflow orchestrate () -> Int 1))
        """,
    )

    assert result.validated_bundle.surface.name == "nested_map::orchestrate"


@pytest.mark.parametrize(
    "element_definition",
    (
        "(defrecord Item (value Int))",
        "(defunion Item (READY (value Int)))",
    ),
)
def test_frontend_pure_map_rejects_record_and_union_collection_elements(
    tmp_path: Path,
    element_definition: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule unsupported_map_contract)
              (export orchestrate)
              {element_definition}
              (defun map-items ((items List[Item])) -> List[Item]
                (list/map ((item items)) item))
              (defworkflow orchestrate () -> Int 1))
            """,
        )
        == "list_collection_contract_unsupported"
    )


@pytest.mark.parametrize(
    "binder",
    (
        "()",
        "((item))",
        "((item xs) (other xs))",
        "((__compiler_item xs))",
    ),
)
def test_frontend_effect_map_rejects_invalid_binder_shapes(
    tmp_path: Path,
    binder: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule invalid_effect_map_binder)
              (export orchestrate)
              (defworkflow child ((value Int)) -> Int value)
              (defworkflow orchestrate ((xs List[Int])) -> List[Int]
                (list/map-effect {binder} :max 2
                  (call child :value item))))
            """,
        )
        == "list_map_binder_invalid"
    )


@pytest.mark.parametrize(
    "max_clause",
    (
        "",
        ":max (+ 1 1)",
        ":max 0",
        ":max -1",
    ),
    ids=("absent", "computed", "zero", "negative"),
)
def test_frontend_effect_map_requires_positive_literal_max(
    tmp_path: Path,
    max_clause: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule invalid_effect_map_max)
              (export orchestrate)
              (defworkflow child ((value Int)) -> Int value)
              (defworkflow orchestrate ((xs List[Int])) -> List[Int]
                (list/map-effect ((item xs)) {max_clause}
                  (call child :value item))))
            """,
        )
        == "list_map_effect_max_invalid"
    )


def test_frontend_effect_map_rejects_effectful_source(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule impure_effect_map_source)
              (export orchestrate)
              (defworkflow source () -> List[Int] (list 1))
              (defworkflow child ((value Int)) -> Int value)
              (defworkflow orchestrate () -> List[Int]
                (list/map-effect ((item (call source))) :max 2
                  (call child :value item))))
            """,
        )
        == "list_map_effect_body_unsupported"
    )


def test_frontend_effect_map_rejects_effectful_body_composition(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule composed_effect_map_body)
              (export orchestrate)
              (defworkflow child ((value Int)) -> Int value)
              (defworkflow orchestrate ((xs List[Int])) -> List[Int]
                (list/map-effect ((item xs)) :max 2
                  (if true
                    (call child :value item)
                    (call child :value item)))))
            """,
        )
        == "list_map_effect_body_unsupported"
    )


def test_frontend_effect_map_rejects_effectful_call_argument(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule nested_effect_map_argument)
              (export orchestrate)
              (defworkflow source () -> Int 1)
              (defworkflow child ((value Int)) -> Int value)
              (defworkflow orchestrate ((xs List[Int])) -> List[Int]
                (list/map-effect ((item xs)) :max 2
                  (call child :value (call source)))))
            """,
        )
        == "list_map_effect_body_unsupported"
    )


def test_frontend_effect_map_accepts_computed_pure_call_argument(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule pure_effect_map_argument)
          (export orchestrate)
          (defworkflow child ((value Int)) -> Int value)
          (defworkflow orchestrate () -> List[Int]
            (list/map-effect ((item (list 1 2))) :max 2
              (call child :value (+ item 10)))))
        """,
        lowering_route="wcc_m4",
    )
    state_manager = StateManager(
        workspace=tmp_path,
        run_id="pure-effect-map-argument",
    )
    state_manager.initialize(str(tmp_path / "pure_effect_map_argument.orc"))

    state = WorkflowExecutor(
        result.validated_bundle,
        tmp_path,
        state_manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"__result__": [11, 12]}
    effect_point = next(
        point
        for point in result.validated_bundle.runtime_plan.lexical_checkpoint_points
        if point.point_kind == "effect_boundary"
    )
    qualified = [
        checkpoint
        for checkpoint in result.validated_bundle.runtime_plan.resume_checkpoints
        if checkpoint.node_id == effect_point.node_id
        and checkpoint.runtime_step_id_mode == "qualified_iteration"
    ]
    assert len(qualified) == 1
    assert qualified[0].checkpoint_kind == "call_boundary"


@pytest.mark.parametrize(
    ("module_name", "body", "expected_effect_kind"),
    (
        (
            "effect_map_provider_boundary",
            (
                "(provider-result providers.worker "
                ":prompt prompts.worker :inputs (item) :returns Int)"
            ),
            "provider",
        ),
        (
            "effect_map_command_boundary",
            (
                "(command-result run_item "
                ':argv ("echo" item) :returns Int)'
            ),
            "command",
        ),
    ),
)
def test_frontend_effect_map_accepts_existing_provider_and_command_boundaries(
    tmp_path: Path,
    module_name: str,
    body: str,
    expected_effect_kind: str,
) -> None:
    module_path = tmp_path / f"{module_name}.orc"
    module_path.write_text(
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule {module_name})
          (export orchestrate)
          (defworkflow orchestrate ((items List[Int])) -> List[Int]
            (list/map-effect ((item items)) :max 2
              {body})))
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "worker.md").write_text(
        "provider prompt\n",
        encoding="utf-8",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.worker": "fake-worker"},
        prompt_externs={"prompts.worker": "worker.md"},
        command_boundaries={
            "run_item": ExternalToolBinding(
                name="run_item",
                stable_command=("echo",),
            )
        },
        lowering_route="wcc_m4",
        validate_shared=True,
        workspace_root=tmp_path,
    )
    lowered = result.lowered_workflows[0]
    effect_points = tuple(
        point
        for point in lowered.lexical_checkpoint_points
        if point.get("point_kind") == "effect_boundary"
    )

    assert len(effect_points) == 1
    assert (
        effect_points[0]["effect_boundary"]["effect_kind"]
        == expected_effect_kind
    )
    bundle = next(iter(result.validated_bundles.values()))
    runtime_effect_point = next(
        point
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.point_kind == "effect_boundary"
    )
    qualified = [
        checkpoint
        for checkpoint in bundle.runtime_plan.resume_checkpoints
        if checkpoint.node_id == runtime_effect_point.node_id
        and checkpoint.runtime_step_id_mode == "qualified_iteration"
    ]
    assert len(qualified) == 1
    assert qualified[0].checkpoint_kind == "call_boundary"
    assert any(
        "repeat_until" in step
        for step in lowered.authored_mapping["steps"]
    )


def test_frontend_effect_map_accepts_one_specialized_private_workflow_call(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule specialized_single_effect_map)
          (export orchestrate)
          (defworkflow child ((value Int)) -> Int value)
          (defproc invoke-child
            ((value Int))
            -> Int
            :effects ((calls-workflow specialized_single_effect_map::child))
            :lowering inline
            (call child :value (+ value 10)))
          (defworkflow orchestrate () -> List[Int]
            (list/map-effect ((item (list 1 2))) :max 2
              (invoke-child item))))
        """,
        lowering_route="wcc_m4",
    )
    state_manager = StateManager(
        workspace=tmp_path,
        run_id="specialized-single-effect-map",
    )
    state_manager.initialize(
        str(tmp_path / "specialized_single_effect_map.orc")
    )

    state = WorkflowExecutor(
        result.validated_bundle,
        tmp_path,
        state_manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"__result__": [11, 12]}


def test_frontend_effect_map_rejects_two_effects_after_specialization(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule specialized_multiple_effect_map)
              (export orchestrate)
              (defworkflow child ((value Int)) -> Int value)
              (defproc invoke-child-twice
                ((value Int))
                -> Int
                :effects ((calls-workflow specialized_multiple_effect_map::child))
                :lowering inline
                (let* ((first (call child :value value)))
                  (call child :value (+ first 1))))
              (defworkflow orchestrate () -> List[Int]
                (list/map-effect ((item (list 1 2))) :max 2
                  (invoke-child-twice item))))
            """,
        )
        == "list_map_effect_body_unsupported"
    )


def test_terminal_loop_state_survives_wcc_round_trip_and_generic_traversal() -> None:
    span = _expression_syntax("1").span
    int_type = PrimitiveTypeRef(name="Int")
    factory = WccIdentityFactory(
        owner_name="terminal-state-round-trip",
        lexical_owner_chain=("workflow", "loop"),
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
    )
    result_value = WccLiteralAtom(
        metadata=factory.atom_metadata(
            role="loop-result",
            type_ref=int_type,
            source_span=span,
            form_path=("workflow-lisp", "loop-result"),
        ),
        value=11,
        literal_kind="int",
    )
    terminal_state = WccLiteralAtom(
        metadata=factory.atom_metadata(
            role="loop-terminal-state",
            type_ref=int_type,
            source_span=span,
            form_path=("workflow-lisp", "loop-terminal-state"),
        ),
        value=22,
        literal_kind="int",
    )

    restored = _frontend_expr_from_wcc_loop_body(
        WccLoopDone(
            metadata=factory.body_metadata(
                role="loop-done",
                type_ref=int_type,
                source_span=span,
                form_path=("workflow-lisp", "loop-done"),
            ),
            result=result_value,
            state=terminal_state,
        )
    )

    assert isinstance(restored, DoneExpr)
    assert isinstance(restored.result_expr, LiteralExpr)
    assert isinstance(restored.terminal_state_expr, LiteralExpr)
    assert [
        node.value
        for node in walk_expr(restored)
        if isinstance(node, LiteralExpr)
    ] == [11, 22]


@pytest.mark.parametrize(
    "workflow_source",
    (
        """
        (defrecord Item (value Int))
        (defworkflow child ((value Item)) -> Int value.value)
        (defworkflow orchestrate ((xs List[Item])) -> List[Int]
          (list/map-effect ((item xs)) :max 2
            (call child :value item)))
        """,
        """
        (defrecord Item (value Int))
        (defworkflow child ((value Int)) -> Item
          (record Item :value value))
        (defworkflow orchestrate ((xs List[Int])) -> Int
          (let* ((mapped
                    (list/map-effect ((item xs)) :max 2
                      (call child :value item))))
            1))
        """,
    ),
    ids=("source-contract", "result-contract"),
)
def test_frontend_effect_map_rejects_unsupported_complete_list_contract(
    tmp_path: Path,
    workflow_source: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule unsupported_effect_map_contract)
              (export orchestrate)
              {workflow_source})
            """,
        )
        == "list_collection_contract_unsupported"
    )


def test_frontend_effect_map_erases_to_existing_repeat_loop(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule effect_map_erasure)
          (export orchestrate)
          (defworkflow child ((value Int)) -> Int (+ value 1))
          (defworkflow orchestrate () -> List[Int]
            (list/map-effect ((item (list 3 1 2))) :max 3
              (call child :value item))))
        """,
        lowering_route="wcc_m4",
    )

    repeat_steps = [
        step
        for lowered in result.compile_result.entry_result.lowered_workflows
        if lowered.typed_workflow.definition.name.endswith("::orchestrate")
        for step in lowered.authored_mapping["steps"]
        if "repeat_until" in step
    ]
    assert len(repeat_steps) == 1
    assert repeat_steps[0]["repeat_until"]["max_iterations"] == 3
    assert (
        repeat_steps[0]["repeat_until"]["exhaustion_diagnostic_code"]
        == "list_map_effect_cap_exceeded"
    )
    assert {
        node.kind.value
        for node in result.validated_bundle.ir.nodes.values()
    }.isdisjoint({"list_map_effect", "list-map-effect"})

    state_manager = StateManager(
        workspace=tmp_path,
        run_id="effect-map-erasure",
    )
    state_manager.initialize(str(tmp_path / "effect_map_erasure.orc"))
    state = WorkflowExecutor(
        result.validated_bundle,
        tmp_path,
        state_manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    loop_state = state["steps"][repeat_steps[0]["name"]]
    assert state["status"] == "completed", loop_state
    assert state["workflow_outputs"] == {"__result__": [4, 2, 3]}


def _compiler_nested_if_declaration_probe(
    tmp_path: Path,
    *,
    branch_id: str = "generated_branch",
    branch_name: str = "GeneratedBranch",
    declared_ids: tuple[str, ...] = ("generated_branch",),
    frontend_kind: str | None = "workflow_lisp",
) -> _WorkflowMappingValidator:
    mapping = {
        "steps": [
            {
                "name": "GeneratedLoop",
                "id": "generated_loop",
                "repeat_until": {
                    "exhaustion_diagnostic_code": (
                        "bounded_traversal_cap_exceeded"
                    ),
                    "steps": [
                        {
                            "name": branch_name,
                            "id": branch_id,
                            "if": {"compare": {}},
                            "then": {"steps": []},
                            "else": {"steps": []},
                        }
                    ],
                },
            }
        ]
    }
    validator = _WorkflowMappingValidator(
        WorkflowMappingBuildRequest(
            authored_mapping=mapping,
            workflow_path=tmp_path / "compiler-nested-if-probe.orc",
            frontend_kind=frontend_kind,
            compiler_owned_repeat_until_metadata={
                "generated_loop": {
                    "exhaustion_diagnostic_code": (
                        "bounded_traversal_cap_exceeded"
                    ),
                }
            },
            compiler_owned_nested_if_step_ids=declared_ids,
        ),
        WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )
    validator._validate_compiler_owned_nested_if_steps(mapping)
    return validator


def test_compiler_owned_nested_if_declaration_matches_exact_step_id(
    tmp_path: Path,
) -> None:
    validator = _compiler_nested_if_declaration_probe(tmp_path)

    assert validator.errors == []


@pytest.mark.parametrize(
    ("declared_ids", "expected_message"),
    (
        ((), "is undeclared"),
        (
            ("generated_branch", "extra_branch"),
            "has no eligible emitted step",
        ),
        (
            ("generated_branch", "generated_branch"),
            "must be unique",
        ),
    ),
    ids=("missing", "extra", "duplicate"),
)
def test_compiler_owned_nested_if_declaration_fails_closed_for_inexact_ids(
    tmp_path: Path,
    declared_ids: tuple[str, ...],
    expected_message: str,
) -> None:
    validator = _compiler_nested_if_declaration_probe(
        tmp_path,
        declared_ids=declared_ids,
    )

    assert any(
        expected_message in error.message for error in validator.errors
    )


def test_compiler_owned_nested_if_declaration_rejects_non_lisp_frontend(
    tmp_path: Path,
) -> None:
    validator = _compiler_nested_if_declaration_probe(
        tmp_path,
        frontend_kind=None,
    )

    assert any(
        "require the Workflow Lisp frontend" in error.message
        for error in validator.errors
    )


def test_compiler_owned_nested_if_declaration_binds_id_not_display_name(
    tmp_path: Path,
) -> None:
    renamed = _compiler_nested_if_declaration_probe(
        tmp_path,
        branch_name="RenamedGeneratedBranch",
    )
    tampered_id = _compiler_nested_if_declaration_probe(
        tmp_path,
        branch_id="tampered_branch",
    )

    assert renamed.errors == []
    assert {
        error.message for error in tampered_id.errors
    } == {
        (
            "compiler-owned nested if step id 'tampered_branch' "
            "is undeclared"
        ),
        (
            "compiler-owned nested if step-id declaration "
            "'generated_branch' has no eligible emitted step"
        ),
    }


def test_effect_map_lowering_captures_every_compiler_owned_nested_if_id(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule effect_map_nested_if_ids)
          (export orchestrate)
          (defworkflow child ((value Int)) -> Int value)
          (defworkflow orchestrate () -> List[Int]
            (list/map-effect ((item (list 1))) :max 1
              (call child :value item))))
        """,
        lowering_route="wcc_m4",
    )
    lowered = next(
        workflow
        for workflow in result.compile_result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name.endswith("::orchestrate")
    )
    captured = lowering_core._capture_compiler_owned_nested_if_step_ids(
        lowered.authored_mapping
    )

    assert captured
    assert captured == lowered.compiler_owned_nested_if_step_ids

    missing = replace(
        lowered,
        compiler_owned_nested_if_step_ids=captured[:-1],
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        lowering_core._validate_one_lowered_workflow(
            missing,
            workspace_root=tmp_path,
            imported_bundles={},
            workflow_is_imported=False,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        )
    assert "is undeclared" in excinfo.value.diagnostics[0].message


def _run_effect_map_source(
    tmp_path: Path,
    *,
    module_name: str,
    child_param_type: str,
    child_return_type: str,
    child_body: str,
    source_expr: str,
    max_iterations: int,
    entry_params: str = "()",
    bound_inputs: dict[str, object] | None = None,
):
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule {module_name})
          (export orchestrate)
          (defworkflow child
            ((value {child_param_type}))
            -> {child_return_type}
            {child_body})
          (defworkflow orchestrate {entry_params} -> List[{child_return_type}]
            (list/map-effect ((item {source_expr})) :max {max_iterations}
              (call child :value item))))
        """,
        lowering_route="wcc_m4",
    )
    repeat_step = next(
        step
        for lowered in result.compile_result.entry_result.lowered_workflows
        if lowered.typed_workflow.definition.name.endswith("::orchestrate")
        for step in lowered.authored_mapping["steps"]
        if "repeat_until" in step
    )
    state_manager = StateManager(
        workspace=tmp_path,
        run_id=f"{module_name}-run",
    )
    state_manager.initialize(
        str(tmp_path / f"{module_name}.orc"),
        bound_inputs=bound_inputs,
    )
    state = WorkflowExecutor(
        result.validated_bundle,
        tmp_path,
        state_manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")
    return result, repeat_step, state


def _effect_map_call_frames(
    state: dict[str, object],
) -> list[dict[str, object]]:
    call_frames = state.get("call_frames")
    assert isinstance(call_frames, dict)
    frames = [
        frame
        for frame in call_frames.values()
        if isinstance(frame, dict)
        and str(frame.get("import_alias", "")).endswith("::child")
    ]

    def iteration(frame: dict[str, object]) -> int:
        match = re.search(r"__loop#(\d+)", str(frame["call_frame_id"]))
        assert match is not None
        return int(match.group(1))

    return sorted(frames, key=iteration)


@pytest.mark.parametrize(
    (
        "case_name",
        "max_iterations",
        "expected_inputs",
        "expected_outputs",
    ),
    (
        ("empty", 1, [], []),
        ("one", 1, [7], [8]),
        ("below_cap", 3, [3, 1], [4, 2]),
        ("at_cap", 3, [3, 1, 2], [4, 2, 3]),
    ),
)
def test_frontend_effect_map_runtime_commits_exact_calls_in_source_order(
    tmp_path: Path,
    case_name: str,
    max_iterations: int,
    expected_inputs: list[int],
    expected_outputs: list[int],
) -> None:
    _, repeat_step, state = _run_effect_map_source(
        tmp_path,
        module_name=f"effect_map_runtime_{case_name}",
        child_param_type="Int",
        child_return_type="Int",
        child_body="(+ value 1)",
        source_expr="items",
        max_iterations=max_iterations,
        entry_params="((items List[Int]))",
        bound_inputs={"items": expected_inputs},
    )

    frames = _effect_map_call_frames(state)
    loop_state = state["steps"][repeat_step["name"]]
    assert state["status"] == "completed", loop_state
    assert state["workflow_outputs"] == {"__result__": expected_outputs}
    assert [frame["status"] for frame in frames] == [
        "completed"
    ] * len(expected_inputs)
    assert [
        frame["bound_inputs"]["value"] for frame in frames
    ] == expected_inputs
    assert [
        frame["state"]["workflow_outputs"]["__result__"]
        for frame in frames
    ] == expected_outputs
    if case_name == "at_cap":
        assert loop_state["artifacts"]["state__remaining"] == []
        assert (
            loop_state["artifacts"]["state__results"]
            == expected_outputs
        )


def test_frontend_effect_map_runtime_fails_with_exact_cap_diagnostic_before_max_plus_one(
    tmp_path: Path,
) -> None:
    _, repeat_step, state = _run_effect_map_source(
        tmp_path,
        module_name="effect_map_runtime_cap",
        child_param_type="Int",
        child_return_type="Int",
        child_body="(+ value 1)",
        source_expr="(list 3 1 2)",
        max_iterations=2,
    )

    frames = _effect_map_call_frames(state)
    loop_state = state["steps"][repeat_step["name"]]
    assert state["status"] == "failed"
    assert loop_state["status"] == "failed"
    assert loop_state["error"]["type"] == "repeat_until_iterations_exhausted"
    assert loop_state["error"]["code"] == "list_map_effect_cap_exceeded"
    assert [frame["bound_inputs"]["value"] for frame in frames] == [3, 1]
    assert [frame["status"] for frame in frames] == [
        "completed",
        "completed",
    ]
    assert [
        frame["state"]["workflow_outputs"]["__result__"]
        for frame in frames
    ] == [4, 2]


def test_frontend_effect_map_runtime_body_failure_does_not_append_or_call_later_items(
    tmp_path: Path,
) -> None:
    _, repeat_step, state = _run_effect_map_source(
        tmp_path,
        module_name="effect_map_runtime_body_failure",
        child_param_type="Int",
        child_return_type="Int",
        child_body="(+ value 1)",
        source_expr="items",
        max_iterations=3,
        entry_params="((items List[Int]))",
        bound_inputs={"items": [1, 9223372036854775807, 3]},
    )

    frames = _effect_map_call_frames(state)
    loop_state = state["steps"][repeat_step["name"]]
    assert state["status"] == "failed"
    assert loop_state["status"] == "failed"
    assert [frame["bound_inputs"]["value"] for frame in frames] == [
        1,
        9223372036854775807,
    ]
    assert [frame["status"] for frame in frames] == [
        "completed",
        "failed",
    ]
    assert loop_state["artifacts"]["state__results"] == [2]
    assert loop_state["artifacts"]["state__remaining"] == [
        9223372036854775807,
        3,
    ]


def test_frontend_effect_map_generated_roles_and_source_spans_are_stable(
    tmp_path: Path,
) -> None:
    source = """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule effect_map_stable_roles)
          (export orchestrate)
          (defworkflow child ((value Int)) -> Int (+ value 1))
          (defworkflow orchestrate () -> List[Int]
            (list/map-effect ((item (list 3 1))) :max 2
              (call child :value item))))
    """

    def generated_roles(root: Path) -> dict[str, tuple[object, ...]]:
        result = _build_source(
            root,
            source,
            lowering_route="wcc_m4",
        )
        source_map = json.loads(
            result.artifact_paths["source_map"].read_text(encoding="utf-8")
        )
        step_ids = source_map["workflows"][
            "effect_map_stable_roles::orchestrate"
        ]["step_ids"]
        return {
            step_id: (
                origin["line"],
                origin["column"],
                origin["end_line"],
                origin["end_column"],
                origin["generated_name_origin"],
                tuple(origin["form_path"]),
            )
            for step_id, origin in step_ids.items()
            if step_id.startswith("effect_map_stable_roles::orchestrate__")
        }

    first = generated_roles(tmp_path / "first")
    second = generated_roles(tmp_path / "second")

    assert first == second
    assert {
        "effect_map_stable_roles::orchestrate__seed",
        "effect_map_stable_roles::orchestrate__loop",
        "effect_map_stable_roles::orchestrate__body",
        "effect_map_stable_roles::orchestrate__body__condition",
        "effect_map_stable_roles::orchestrate__body__else__item",
    }.issubset(first)
    assert any(
        "__list_map_effect_result__call_effect_map_stable_roles::child"
        in step_id
        for step_id in first
    )
    assert all(
        role[-1]
        == ("workflow-lisp", "defworkflow", "orchestrate")
        for role in first.values()
    )


@pytest.mark.parametrize(
    ("path_type", "expected_under"),
    (
        ("Path.state-root", "state"),
        ("Path.artifact-root", "artifacts"),
        ("LocalReport", "artifacts/reports"),
    ),
)
def test_frontend_path_join_under_resolves_exact_prelude_and_local_family(
    tmp_path: Path,
    path_type: str,
    expected_under: str,
) -> None:
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule path_join)
          (export orchestrate)
          (defpath LocalReport
            :kind relpath
            :under "artifacts/reports"
            :must-exist true)
          (defworkflow orchestrate ((child String)) -> {path_type}
            (path/join-under {path_type} child)))
        """,
    )

    payload = _projection_payload(result)["payload"]
    assert payload["pure_expr_schema_version"] == 2
    assert payload["expr"]["kind"] == "path_join_under"
    assert payload["expr"]["path_type"]["under"] == expected_under
    assert payload["expr"]["path_type"]["name"].endswith(path_type)
    if path_type == "LocalReport":
        assert payload["expr"]["path_type"]["must_exist_target"] is True


def test_frontend_path_join_under_resolves_imported_family(
    tmp_path: Path,
) -> None:
    package = tmp_path / "paths"
    package.mkdir()
    (package / "types.orc").write_text(
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule paths/types)
          (export ImportedReport)
          (defpath ImportedReport
            :kind relpath
            :under "artifacts/imported"
            :must-exist false))
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule paths/entry)
          (import paths/types :only (ImportedReport))
          (export orchestrate)
          (defworkflow orchestrate ((child String)) -> ImportedReport
            (path/join-under ImportedReport child)))
        """,
        filename="paths/entry.orc",
    )

    descriptor = _projection_payload(result)["payload"]["expr"]["path_type"]
    assert descriptor["name"] == "paths/types::ImportedReport"
    assert descriptor["under"] == "artifacts/imported"


@pytest.mark.parametrize(
    ("path_type", "child", "expected_code"),
    (
        ("String", '"child.md"', "path_join_under_type_invalid"),
        ("Path.state-root", "1", "pure_expr_operand_type_mismatch"),
        ("MalformedRoot", '"child.md"', "path_join_under_root_invalid"),
        ("Path.state-root", '""', "path_join_under_child_invalid"),
        ("Path.state-root", '"/absolute.md"', "path_join_under_escape"),
        ("Path.state-root", '"../escape.md"', "path_join_under_escape"),
    ),
)
def test_frontend_path_join_under_preserves_exact_refusal_families(
    tmp_path: Path,
    path_type: str,
    child: str,
    expected_code: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule invalid_path_join)
              (export orchestrate)
              (defpath MalformedRoot
                :kind relpath
                :under "."
                :must-exist false)
              (defworkflow orchestrate () -> {path_type}
                (path/join-under {path_type} {child})))
            """,
        )
        == expected_code
    )


def test_list_traversal_authored_head_inventory_is_exact() -> None:
    registry = importlib.import_module(
        "orchestrator.workflow_lisp.form_registry"
    )

    assert registry.list_traversal_authored_heads() == frozenset(
        _LIST_TRAVERSAL_AUTHORED_HEADS
    )


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
@pytest.mark.parametrize("callable_lane", ("function", "procedure", "bound"))
def test_target_217_list_traversal_heads_defer_to_same_named_callable(
    head: str,
    callable_lane: str,
) -> None:
    expression = elaborate_expression(
        _expression_syntax(f"({head} 1)"),
        target_dsl_version="2.17",
        function_names=(
            frozenset({head})
            if callable_lane == "function"
            else frozenset()
        ),
        procedure_names=(
            frozenset({head})
            if callable_lane == "procedure"
            else frozenset()
        ),
        bound_names=(
            frozenset({head})
            if callable_lane == "bound"
            else frozenset()
        ),
    )

    expected_type = (
        FunctionCallExpr
        if callable_lane == "function"
        else ProcedureCallExpr
    )
    assert isinstance(expression, expected_type)
    assert expression.callee_name == head


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
def test_target_217_list_traversal_heads_are_macro_bindable(
    tmp_path: Path,
    head: str,
) -> None:
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.17")
          (defmodule legacy_list_traversal_macro)
          (export orchestrate)
          (defmacro {head} (value) value)
          (defworkflow orchestrate () -> Int
            ({head} 1)))
        """,
    )

    assert (
        result.validated_bundle.surface.name
        == "legacy_list_traversal_macro::orchestrate"
    )


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
def test_target_217_receiver_imports_and_expands_legacy_list_macro(
    tmp_path: Path,
    head: str,
) -> None:
    _write_legacy_list_traversal_macro(tmp_path, head=head)

    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.17")
          (defmodule legacy_macro_receiver)
          (import legacy/list-macros :only ({head}))
          (export orchestrate)
          (defworkflow orchestrate () -> Int
            ({head} 1)))
        """,
    )

    assert (
        result.validated_bundle.surface.name
        == "legacy_macro_receiver::orchestrate"
    )


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
def test_target_218_receiver_rejects_imported_legacy_list_macro(
    tmp_path: Path,
    head: str,
) -> None:
    _write_legacy_list_traversal_macro(tmp_path, head=head)

    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule current_macro_receiver)
              (import legacy/list-macros :only ({head}))
              (export orchestrate)
              (defworkflow orchestrate () -> Int
                ({head} 1)))
            """,
        )
        == "macro_reserved_name"
    )


def test_target_218_local_macro_hygienically_introduces_list_map_binder(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule local_list_map_hygiene)
          (export orchestrate)
          (defmacro map-plus-one (values)
            (list/map ((item values))
              (+ item 1)))
          (defworkflow orchestrate
            ((values List[Int]) (item Int))
            -> List[Int]
            (map-plus-one values)))
        """,
    )

    expression = _projection_payload(result)["payload"]["expr"]
    binder_name = expression["binder"]["name"]
    assert binder_name == "%macro__map-plus-one__m0001__item"
    assert binder_name != "item"
    assert expression["body"]["args"][0] == {
        "kind": "binding",
        "name": binder_name,
    }


def test_target_218_imported_macro_hygienically_introduces_list_map_binder(
    tmp_path: Path,
) -> None:
    _write_list_map_template_macro(tmp_path)

    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule imported_list_map_hygiene)
          (import helpers/list-map-macros :only (map-plus-one))
          (export orchestrate)
          (defworkflow orchestrate
            ((values List[Int]) (item Int))
            -> List[Int]
            (map-plus-one values)))
        """,
    )

    expression = _projection_payload(result)["payload"]["expr"]
    binder_name = expression["binder"]["name"]
    assert binder_name == "%macro__map-plus-one__m0001__item"
    assert binder_name != "item"
    assert expression["body"]["args"][0] == {
        "kind": "binding",
        "name": binder_name,
    }


def test_target_217_user_macro_list_map_head_keeps_generic_hygiene(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.17")
          (defmodule legacy_list_map_hygiene)
          (export orchestrate)
          (defmacro list/map (bindings body) body)
          (defmacro use-legacy-map (values)
            (list/map ((item values))
              (+ item 1)))
          (defworkflow orchestrate
            ((values List[Int]) (item Int))
            -> Int
            (use-legacy-map values)))
        """,
    )

    expression = _projection_payload(result)["payload"]["expr"]
    assert expression["kind"] == "op"
    assert expression["operator"] == "+"
    assert expression["args"][0] == {
        "kind": "binding",
        "name": "item",
    }


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
def test_target_218_list_traversal_heads_remain_macro_reserved(
    tmp_path: Path,
    head: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule owned_list_traversal_macro)
              (export orchestrate)
              (defmacro {head} (value) value)
              (defworkflow orchestrate () -> Int
                ({head} 1)))
            """,
        )
        == "macro_reserved_name"
    )


@pytest.mark.parametrize(
    ("body", "params", "return_type"),
    (
        ("(list 1)", "()", "List[Int]"),
        (
            "(list/map ((item xs)) item)",
            "((xs List[Int]))",
            "List[Int]",
        ),
        (
            '(path/join-under Path.state-root "child")',
            "()",
            "Path.state-root",
        ),
        ("(list/empty? xs)", "((xs List[Int]))", "Bool"),
        ("(list/head xs)", "((xs List[Int]))", "Optional[Int]"),
        ("(list/rest xs)", "((xs List[Int]))", "List[Int]"),
        ("(list/append xs 1)", "((xs List[Int]))", "List[Int]"),
        ("(list/length xs)", "((xs List[Int]))", "Int"),
    ),
)
def test_every_new_list_surface_is_rejected_below_target_218(
    tmp_path: Path,
    body: str,
    params: str,
    return_type: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.17")
              (defmodule target_gate)
              (export orchestrate)
              (defworkflow orchestrate {params} -> {return_type}
                {body}))
            """,
        )
        == "list_traversal_target_dsl_unsupported"
    )


@pytest.mark.parametrize(
    ("target_dsl", "uses_declared_callee"),
    (("2.17", False), ("2.18", True)),
)
def test_workflow_call_resume_policy_preserves_pre_218_identity_boundary(
    tmp_path: Path,
    target_dsl: str,
    uses_declared_callee: bool,
) -> None:
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "{target_dsl}")
          (defmodule call_policy_target_boundary)
          (export orchestrate)
          (defworkflow internal-phase ((value Int)) -> Int value)
          (defworkflow orchestrate ((value Int)) -> Int
            (call internal-phase :value value)))
        """,
        lowering_route="wcc_m4",
    )
    points = json.loads(
        result.artifact_paths["lexical_checkpoint_points"].read_text(
            encoding="utf-8"
        )
    )["points"]
    policy = next(
        point["effect_boundary"]["policy"]
        for point in points
        if point["effect_boundary"]["effect_kind"] == "call"
    )
    call_evidence = policy["evidence_requirements"]["workflow_call"]

    assert call_evidence["target_dsl_version"] == target_dsl
    assert call_evidence["callee_checksum"].startswith("sha256:")
    if uses_declared_callee:
        assert call_evidence["callee_workflow"].endswith("internal-phase")
        assert call_evidence["callee_workflow"] != policy["step_id"]
    else:
        assert call_evidence["callee_workflow"] == policy["step_id"]


def test_schema2_list_frontend_stays_inside_existing_ir_node_families(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule list_ir_shape)
          (export orchestrate)
          (defworkflow orchestrate ((xs List[Int])) -> List[Int]
            (list/map ((item xs)) (+ item 1))))
        """,
    )

    executable_ir = json.loads(
        result.artifact_paths["executable_ir"].read_text(encoding="utf-8")
    )
    core_ast = json.loads(
        result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8")
    )
    assert executable_ir["schema_version"] == "workflow_executable_ir.v1"
    assert core_ast["schema_version"] == "core_workflow_ast.v1"
    projection = _projection_payload(result)
    assert projection["payload"]["pure_expr_schema_version"] == 2
    assert all(
        step.pure_projection is not None
        for step in result.validated_bundle.surface.steps
    )


def test_list_values_route_through_wcc_as_values_without_new_nodes(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule list_wcc_routes)
          (export orchestrate)
          (defworkflow orchestrate () -> List[Int]
            (list/map ((item (list 1 2))) item)))
        """,
        lowering_route="wcc_m4",
    )

    payload = _projection_payload(result)["payload"]
    assert payload["pure_expr_schema_version"] == 2
    assert payload["expr"]["kind"] == "list_map"
