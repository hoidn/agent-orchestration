from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.pure_expr import pure_expr_payload_digest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lowering import pure_projection as pure_projection_lowering
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import MapTypeRef, PrimitiveTypeRef
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import historical_workflow_lisp_bundle_context


REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
PURE_EXPR_LOOP_COUNTER = VALID_FIXTURES / "pure_expr_loop_counter.orc"
PURE_EXPR_SELECTOR_PROJECTION = VALID_FIXTURES / "pure_expr_selector_action_projection.orc"
INVALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "invalid"


def _write_yaml(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_authored_pure_projection_workflow(workspace: Path) -> Path:
    payload = {
        "pure_expr_schema_version": 1,
        "result_type": {
            "kind": "record",
            "name": "ProjectionOutput",
            "fields": [
                {"name": "status", "type": {"kind": "primitive", "name": "String"}},
            ],
        },
        "bindings": {
            "maybe_reason": {
                "type": {
                    "kind": "optional",
                    "item": {"kind": "primitive", "name": "String"},
                }
            }
        },
        "expr": {
            "kind": "record",
            "type": {
                "kind": "record",
                "name": "ProjectionOutput",
                "fields": [
                    {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                ],
            },
            "fields": [
                {
                    "name": "status",
                    "value": {
                        "kind": "op",
                        "operator": "or-else",
                        "args": [
                            {"kind": "binding", "name": "maybe_reason"},
                            {
                                "kind": "literal",
                                "type": {"kind": "primitive", "name": "String"},
                                "value": "fallback",
                            },
                        ],
                    },
                }
            ],
        },
    }
    return _write_yaml(
        workspace / "workflow.yaml",
        {
            "version": "2.14",
            "name": "pure-projection-runtime",
            "outputs": {
                "status": {
                    "kind": "scalar",
                    "type": "string",
                    "from": {"ref": "root.steps.Project.artifacts.return__status"},
                }
            },
            "steps": [
                {
                    "name": "Project",
                    "id": "project",
                    "output_bundle": {
                        "path": "state/pure_projection/project.json",
                        "fields": [
                            {
                                "name": "return__status",
                                "json_pointer": "/result/status",
                                "type": "string",
                            }
                        ],
                    },
                    "pure_projection": {
                        "payload": payload,
                        "binding_refs": {"maybe_reason": {"ref": "inputs.maybe_reason"}},
                        "payload_digest": pure_expr_payload_digest(payload),
                        "output_contracts": {
                            "return__status": {"kind": "scalar", "type": "string"},
                        },
                    },
                }
            ],
        },
    )


def _compile_pure_projection_bundle(tmp_path: Path):
    result = compile_stage3_entrypoint(
        PURE_EXPR_SELECTOR_PROJECTION,
        source_roots=(VALID_FIXTURES,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["pure_expr_selector_action_projection::orchestrate"]


def _compile_runtime_overflow_bundle(tmp_path: Path):
    module_path = tmp_path / "pure_expr_runtime_overflow.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pure_expr_runtime_overflow)",
                "  (export project)",
                "  (defrecord OverflowResult",
                "    (count Int))",
                "  (defworkflow project",
                "    ((count Int))",
                "    -> OverflowResult",
                "    (record OverflowResult",
                "      :count (+ count 1))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["pure_expr_runtime_overflow::project"]


def _compile_runtime_enum_member_bundle(tmp_path: Path):
    module_path = tmp_path / "pure_expr_runtime_enum_member.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pure_expr_runtime_enum_member)",
                "  (export project)",
                "  (defenum SelectionStatus",
                "    WAITING",
                "    DONE)",
                "  (defrecord ProjectionResult",
                "    (ready Bool)",
                "    (status SelectionStatus))",
                "  (defworkflow project",
                "    ((status SelectionStatus))",
                "    -> ProjectionResult",
                "    (record ProjectionResult",
                "      :ready (= status SelectionStatus.DONE)",
                "      :status SelectionStatus.DONE))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["pure_expr_runtime_enum_member::project"]


def _compile_runtime_native_root_bundle(tmp_path: Path):
    module_path = tmp_path / "pure_expr_runtime_native_root.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pure_expr_runtime_native_root)",
                "  (export root-flag)",
                "  (defrecord FlagResult",
                "    (flag Bool))",
                "  (defworkflow root-flag",
                "    ((count Int))",
                "    -> FlagResult",
                "    (let* ((flag (if (> count 0) true false)))",
                "      (record FlagResult :flag flag))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["pure_expr_runtime_native_root::root-flag"]


def _compile_runtime_union_variant_bundle(tmp_path: Path):
    module_path = tmp_path / "pure_expr_runtime_union_variant.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pure_expr_runtime_union_variant)",
                "  (export project)",
                "  (defpath SelectionBundlePath",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist true)",
                "  (defenum SelectionStatus",
                "    SELECT_BACKLOG_ITEM",
                "    BLOCKED)",
                "  (defunion ProjectionDecision",
                "    (SELECTED_ITEM",
                "      (selected_item_selection_bundle SelectionBundlePath))",
                "    (BLOCKED",
                "      (blocked_reason String)))",
                "  (defworkflow project",
                "    ((selection_status SelectionStatus)",
                "     (selection_bundle_path SelectionBundlePath)",
                "     (blocked_reason String))",
                "    -> ProjectionDecision",
                "    (let* ((is-selected",
                "             (= selection_status SelectionStatus.SELECT_BACKLOG_ITEM)))",
                "      (if is-selected",
                "        (variant ProjectionDecision SELECTED_ITEM",
                "          :selected_item_selection_bundle selection_bundle_path)",
                "        (variant ProjectionDecision BLOCKED",
                "          :blocked_reason blocked_reason))))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["pure_expr_runtime_union_variant::project"]


def _compile_provider_bundle_path_projection_bundle(tmp_path: Path):
    prompt_path = tmp_path / "prompts" / "selector.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("Select work.\n", encoding="utf-8")
    module_path = tmp_path / "provider_bundle_path_runtime.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule provider_bundle_path_runtime)",
                "  (export select)",
                "  (defpath SelectionBundlePath",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist true)",
                "  (defrecord SelectorDecision",
                "    (selection_bundle_path SelectionBundlePath)",
                "    (status String))",
                "  (defrecord SelectorPublicResult",
                "    (selection_bundle_path SelectionBundlePath)",
                "    (status String))",
                "  (defworkflow select",
                "    ((request String))",
                "    -> SelectorPublicResult",
                "    (let* ((decision",
                "             (provider-result providers.selector",
                "               :prompt prompts.selector",
                "               :inputs (request)",
                "               :returns SelectorDecision))",
                "           (selection-bundle-path",
                "             (provider-bundle-path decision :as SelectionBundlePath)))",
                "      (record SelectorPublicResult",
                "        :selection_bundle_path selection-bundle-path",
                "        :status decision.status)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={"providers.selector": "fake-selector"},
        prompt_externs={"prompts.selector": prompt_path.relative_to(tmp_path).as_posix()},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["provider_bundle_path_runtime::select"]


def _compile_invalid_pure_projection_fixture(
    fixture_path: Path,
    tmp_path: Path,
    *,
    lint_profile: str = "default",
):
    return compile_stage3_entrypoint(
        fixture_path,
        source_roots=(fixture_path.parent,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lint_profile=lint_profile,
    )


def _resume_failed_single_step(state_manager: StateManager, *, step_name: str) -> None:
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {step_name: {"status": "failed", "exit_code": 1}}
    state_manager._write_state()


def _compiled_bundle_path(workspace: Path, state_manager: StateManager) -> Path:
    assert state_manager.state is not None
    relative_path = next(
        value
        for name, value in state_manager.state.bound_inputs.items()
        if name.startswith("__write_root__") and isinstance(value, str)
    )
    return workspace / relative_path


def test_loader_rejects_authored_pure_projection_step(tmp_path: Path) -> None:
    workflow_file = _write_authored_pure_projection_workflow(tmp_path)

    with pytest.raises(WorkflowValidationError) as excinfo:
        WorkflowLoader(tmp_path).load_bundle(workflow_file)

    assert "pure_projection is compiler-generated only" in str(excinfo.value)


def test_compile_stage3_entrypoint_emits_visible_pure_projection_step(tmp_path: Path) -> None:
    bundle = _compile_pure_projection_bundle(tmp_path)

    assert [step.kind.value for step in bundle.surface.steps] == ["pure_projection"]
    assert bundle.surface.steps[0].pure_projection["payload"]["pure_expr_schema_version"] == 1


def test_pure_projection_collection_root_contract_emits_boundary_diagnostic() -> None:
    span = SourceSpan(
        start=SourcePosition(path="collection_root.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="collection_root.orc", line=1, column=2, offset=1),
    )
    map_ref = MapTypeRef(
        name="(Map String Int)",
        key_type_ref=PrimitiveTypeRef(name="String"),
        value_type_ref=PrimitiveTypeRef(name="Int"),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        pure_projection_lowering._output_contracts_for_type(
            map_ref,
            context=None,
            span=span,
            form_path=("workflow", "return"),
        )

    assert [diagnostic.code for diagnostic in excinfo.value.diagnostics] == [
        "workflow_boundary_collection_unsupported"
    ]


def test_pure_projection_runtime_reuses_committed_bundle_on_resume(tmp_path: Path) -> None:
    loaded = _compile_pure_projection_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name
    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-runtime")
    state_manager.initialize(
        str(PURE_EXPR_SELECTOR_PROJECTION),
        context=historical_workflow_lisp_bundle_context(loaded),
        bound_inputs={"approved": False, "status": "WAIT"},
    )

    first = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    _resume_failed_single_step(state_manager, step_name=step_name)
    resumed = WorkflowExecutor(loaded, tmp_path, state_manager).execute(resume=True)
    default_resume_report = json.loads(
        state_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )

    assert first["steps"][step_name]["debug"]["pure_projection"]["reused_bundle"] is False
    assert resumed["steps"][step_name]["artifacts"] == {"return__status": "WAIT", "return__ready": False}
    assert resumed["steps"][step_name]["debug"]["pure_projection"]["reused_bundle"] is True
    assert (
        default_resume_report["default_modes"][0]["mode"]
        == "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"
    )


def test_pure_projection_runtime_bounds_overlong_private_bundle_paths(tmp_path: Path) -> None:
    loaded = _compile_pure_projection_bundle(tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-long-path")
    state_manager.initialize(str(PURE_EXPR_SELECTOR_PROJECTION), bound_inputs={"approved": False, "status": "WAIT"})
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    long_path = tmp_path / ".orchestrate" / "workflow_lisp" / "calls" / "nested" / f"{'x' * 320}.json"

    bounded = executor._bounded_private_runtime_bundle_path(long_path, namespace="pure_projection")

    assert bounded != long_path
    assert bounded.is_relative_to(tmp_path / ".orchestrate" / "runtime_sidecars" / "pure_projection")
    assert all(len(part.encode("utf-8")) <= 240 for part in bounded.relative_to(tmp_path).parts)


def test_pure_projection_runtime_fails_closed_when_resume_bundle_schema_changes(tmp_path: Path) -> None:
    loaded = _compile_pure_projection_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name
    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-schema")
    state_manager.initialize(
        str(PURE_EXPR_SELECTOR_PROJECTION),
        context=historical_workflow_lisp_bundle_context(loaded),
        bound_inputs={"approved": True, "status": "WAIT"},
    )

    WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    bundle_path = _compiled_bundle_path(tmp_path, state_manager)
    bundle_record = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_record["pure_expr_schema_version"] = 999
    bundle_path.write_text(json.dumps(bundle_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _resume_failed_single_step(state_manager, step_name=step_name)
    resumed = WorkflowExecutor(loaded, tmp_path, state_manager).execute(resume=True)
    default_resume_report = json.loads(
        state_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )

    assert resumed["steps"][step_name]["status"] == "failed"
    assert resumed["steps"][step_name]["error"]["type"] == "pure_projection_resume_schema_mismatch"
    assert (
        default_resume_report["default_modes"][0]["mode"]
        == "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"
    )


def test_pure_projection_runtime_surfaces_typed_evaluator_failure_codes(tmp_path: Path) -> None:
    loaded = _compile_runtime_overflow_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name
    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-overflow")
    state_manager.initialize(str(tmp_path / "pure_expr_runtime_overflow.orc"), bound_inputs={"count": 9223372036854775807})

    result = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    project = result["steps"][step_name]

    assert project["status"] == "failed"
    assert project["error"]["type"] == "pure_expr_overflow"


def test_pure_projection_runtime_executes_enum_member_equality(tmp_path: Path) -> None:
    loaded = _compile_runtime_enum_member_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name
    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-enum-member")
    state_manager.initialize(str(tmp_path / "pure_expr_runtime_enum_member.orc"), bound_inputs={"status": "DONE"})

    result = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    project = result["steps"][step_name]

    assert project["status"] == "completed"
    assert project["artifacts"] == {"return__ready": True, "return__status": "DONE"}


def test_pure_projection_runtime_executes_native_root_result_projection(tmp_path: Path) -> None:
    loaded = _compile_runtime_native_root_bundle(tmp_path)
    projection_step = next(
        step for step in loaded.surface.steps if getattr(step, "pure_projection", None)
    )
    bundle_fields = [dict(field) for field in projection_step.common.output_bundle["fields"]]
    assert bundle_fields == [
        {"name": "__result__", "json_pointer": "", "kind": "scalar", "type": "bool"}
    ]

    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-native-root")
    state_manager.initialize(
        str(tmp_path / "pure_expr_runtime_native_root.orc"),
        bound_inputs={"count": 2},
    )

    result = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    project = result["steps"][projection_step.name]

    assert project["status"] == "completed"
    assert project["artifacts"] == {"__result__": True}


def test_pure_projection_runtime_skips_inactive_union_variant_outputs(tmp_path: Path) -> None:
    bundle = _compile_runtime_union_variant_bundle(tmp_path)
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "selector_selected.json").write_text("{}\n", encoding="utf-8")
    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-union-variant")
    state_manager.initialize(
        str(tmp_path / "pure_expr_runtime_union_variant.orc"),
        bound_inputs={
            "selection_status": "SELECT_BACKLOG_ITEM",
            "selection_bundle_path": "state/selector_selected.json",
            "blocked_reason": "",
        },
    )

    result = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    workflow_step = result["steps"].get(bundle.surface.name)
    if workflow_step is None:
        workflow_step = result["steps"][f"{bundle.surface.name}__terminal_projection"]

    assert result["status"] == "completed"
    assert workflow_step["status"] == "completed"
    assert workflow_step["artifacts"] == {
        "return__variant": "SELECTED_ITEM",
        "return__selected_item_selection_bundle": "state/selector_selected.json",
    }


def test_provider_bundle_path_projection_exports_generated_bundle_path(tmp_path: Path) -> None:
    bundle = _compile_provider_bundle_path_projection_bundle(tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="provider-bundle-path-runtime")
    state_manager.initialize(
        str(tmp_path / "provider_bundle_path_runtime.orc"),
        bound_inputs={
            "request": "select something",
        },
    )

    def _prepare_invocation(_self, *args, **kwargs):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=kwargs.get("prompt_content", ""),
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def _execute(_self, invocation, **_kwargs):
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        selection_path = tmp_path / "state" / "provider-selection.json"
        selection_path.parent.mkdir(parents=True, exist_ok=True)
        selection_path.write_text("{}\n", encoding="utf-8")
        bundle_path.write_text(
            json.dumps(
                {
                    "selection_bundle_path": "state/provider-selection.json",
                    "status": "SELECTED",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        result = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    assert result["status"] == "completed"
    bound_inputs = result["bound_inputs"]
    write_root = next(
        value
        for name, value in bound_inputs.items()
        if name.startswith("__write_root__")
    )
    assert result["workflow_outputs"]["return__selection_bundle_path"] == write_root


def test_compile_strict_effectful_boundary_fixture_preserves_required_lints(
    tmp_path: Path,
) -> None:
    fixture_path = INVALID_FIXTURES / "pure_projection_effectful_boundary_lints.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_invalid_pure_projection_fixture(
            fixture_path,
            tmp_path,
            lint_profile="strict",
        )

    assert {diagnostic.code for diagnostic in excinfo.value.diagnostics} == {
        "low_level_state_path_in_high_level_module",
        "variant_output_without_variant_specific_fields",
    }


def test_compile_strict_pure_projection_boundary_fixture_skips_boundary_lints(
    tmp_path: Path,
) -> None:
    source_root = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "workflow_lisp"
        / "modules"
        / "valid"
        / "pure_projection_boundary_decision_consumer"
    )
    entry_path = source_root / "pure_projection_boundary_decision_consumer" / "entry.orc"

    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(source_root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
        lint_profile="strict",
    )

    assert (
        "pure_projection_boundary_decision_consumer/entry::run"
        in result.validated_bundles_by_name
    )


def test_imported_call_binding_pure_projection_steps_are_visible_in_bundle(
    tmp_path: Path,
) -> None:
    source_root = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "workflow_lisp"
        / "modules"
        / "valid"
        / "pure_projection_boundary_decision_consumer"
    )
    entry_path = source_root / "pure_projection_boundary_decision_consumer" / "entry.orc"

    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(source_root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name[
        "pure_projection_boundary_decision_consumer/entry::run"
    ]
    pure_projection_step_names = {
        step.name
        for step in bundle.surface.steps
        if step.kind.value == "pure_projection"
    }

    assert any(name.endswith("__bind_route") for name in pure_projection_step_names)
    assert any(name.endswith("__bind_reason") for name in pure_projection_step_names)


def test_compile_rejects_pure_projection_binding_type_mismatch_at_typecheck(
    tmp_path: Path,
) -> None:
    fixture_path = INVALID_FIXTURES / "pure_projection_binding_type_mismatch.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_invalid_pure_projection_fixture(fixture_path, tmp_path)

    assert excinfo.value.diagnostics[0].code == "type_mismatch"


def test_compile_rejects_pure_projection_binding_effectful_expr_with_existing_lowering_diagnostic(
    tmp_path: Path,
) -> None:
    fixture_path = INVALID_FIXTURES / "pure_projection_binding_effectful_expr.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_invalid_pure_projection_fixture(fixture_path, tmp_path)

    assert excinfo.value.diagnostics[0].code == "workflow_signature_mismatch"
    assert "resolve to workflow inputs" in excinfo.value.diagnostics[0].message


def test_compile_rejects_oversized_pure_projection_region(tmp_path: Path) -> None:
    field_count = 260
    record_fields = "\n".join(f"    (f{index} Int)" for index in range(field_count))
    base_fields = "\n".join(f"        :f{index} seed" for index in range(field_count))
    updated_fields = "\n".join(f"      :f{index} (+ seed 1)" for index in range(field_count))
    module_path = tmp_path / "oversized.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule oversized)",
                "  (export run)",
                "  (defrecord Box",
                record_fields,
                "  )",
                "  (defworkflow run",
                "    ((seed Int))",
                "    -> Box",
                "    (record-update",
                "      (record Box",
                base_fields,
                "      )",
                updated_fields,
                "    ))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            module_path,
            source_roots=(tmp_path,),
            provider_externs={},
            prompt_externs={},
            command_boundaries={},
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "pure_expr_payload_too_large"


def test_cli_dry_run_executes_loop_counter_fixture(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "run",
            str(PURE_EXPR_LOOP_COUNTER),
            "--entry-workflow",
            "run-counter",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
