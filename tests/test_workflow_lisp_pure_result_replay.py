from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

import pytest

import orchestrator.workflow.executor as workflow_executor_module
from orchestrator.cli.commands.run import run_workflow
from orchestrator.state import StateManager, StepResult
from orchestrator.workflow import pure_result_replay
from orchestrator.workflow.executable_ir import (
    CallBoundaryNode,
    CallStepConfig,
    NodeResultAddress,
    PureProjectionStepConfig,
    WorkflowInputAddress,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow.predicates import ArtifactBoolPredicateNode
from orchestrator.workflow.pure_expr import pure_expr_payload_digest
from orchestrator.workflow.pure_result_replay import (
    DEPENDENCY_INDEX_INVALID,
    DERIVED_PURE_REPLAY_PROFILE,
    MULTIPLE_VISIT_REGION,
    PureResultReplayIndexError,
    _propagate_pure_ineligibility,
    derive_pure_result_replay_index,
)
from orchestrator.workflow.resume_projection_integrity import ResumeScopePath
from orchestrator.workflow.runtime_plan import derive_workflow_runtime_plan
from orchestrator.workflow.runtime_step import thaw_runtime_value
from orchestrator.workflow_lisp import build_artifacts
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import (
    capture_frontend_diagnostic_identities,
)
from orchestrator.workflow_lisp.lexical_checkpoints import (
    canonical_json_dumps,
    emit_runtime_shadow_record,
)
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict
from orchestrator.workflow.surface_ast import (
    SurfaceFinallyBlock,
    SurfaceStep,
    SurfaceStepKind,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "pure_result_replay_effect_barrier.orc"
)

_EFFECT_SCRIPTS = {
    "count_e1.py": (
        "import os\n"
        "from pathlib import Path\n"
        'bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        'bundle.write_text(\'{"delta": 4, "use-effect": true}\\n\', encoding="utf-8")\n'
        'log = Path("state/effect_calls.log")\n'
        "log.parent.mkdir(parents=True, exist_ok=True)\n"
        'with log.open("a", encoding="utf-8") as handle:\n'
        '    handle.write("E1\\n")\n'
    ),
    "finish_e2.py": (
        "import os\n"
        "from pathlib import Path\n"
        'bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        'bundle.write_text("true\\n", encoding="utf-8")\n'
        'log = Path("state/effect_calls.log")\n'
        "log.parent.mkdir(parents=True, exist_ok=True)\n"
        'with log.open("a", encoding="utf-8") as handle:\n'
        '    handle.write("E2\\n")\n'
    ),
}

_TERMINAL_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule pure_result_replay_terminal_consumers)
  (export orchestrate)
  (defrecord EffectResult
    (delta Int)
    (use-effect Bool))
  (defrecord FlagValue
    (value Bool))
  (defrecord TerminalResult
    (selected Bool))
  (defworkflow orchestrate
    ()
    -> TerminalResult
    (let* ((e1
             (command-result count-e1
               :argv ("python" "scripts/count_e1.py")
               :returns EffectResult))
           (selected
             (record FlagValue
               :value e1.use-effect))
           (unrelated
             (record FlagValue
               :value (if e1.use-effect false true)))
           (observed
             (if unrelated.value
               (command-result finish-left
                 :argv ("python" "scripts/finish_e2.py")
                 :returns Bool)
               (command-result finish-right
                 :argv ("python" "scripts/finish_e2.py")
                 :returns Bool)))
           (finished
             (command-result finish-final
               :argv ("python" "scripts/finish_e2.py")
               :returns Bool)))
      (record TerminalResult
        :selected (if finished selected.value false)))))
"""

_ROUTED_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule pure_result_replay_routed_consumers)
  (export orchestrate)
  (defworkflow orchestrate
    ((choose-left Bool)
     (left-value Int)
     (right-value Int))
    -> Int
    (let* ((selected
             (if choose-left
               (let* ((left-selected
                        (+ left-value 1))
                      (left-finished
                        (command-result finish-left
                          :argv
                            ("python" "scripts/finish_e2.py")
                          :returns Bool)))
                 left-selected)
               (let* ((right-selected
                        (+ right-value 1))
                      (right-finished
                        (command-result finish-right
                          :argv
                            ("python" "scripts/finish_e2.py")
                          :returns Bool)))
                 right-selected))))
      selected)))
"""

_IMPORTED_SCALAR_CALL_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule pure_replay_imported_scalar)
  (export identity)
  (defworkflow identity
    ((value Bool))
    -> Bool
    value))
"""

_IMPORTED_SCALAR_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule pure_replay_imported_scalar_consumer)
  (import pure_replay_imported_scalar :only (identity))
  (export orchestrate)
  (defworkflow orchestrate
    ((value Bool))
    -> Bool
    (let* ((called
             (call identity :value value))
           (derived
             (if called true false)))
      derived)))
"""

_IMPORTED_RECORD_CALL_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule pure_replay_imported_record)
  (export ReplayPair identity)
  (defrecord ReplayPair
    (flag Bool)
    (count Int)
    (weights List[Float]))
  (defworkflow identity
    ((value ReplayPair))
    -> ReplayPair
    value))
"""

_IMPORTED_RECORD_CONSUMER_SOURCE = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.25")
  (defmodule pure_replay_imported_record_consumer)
  (import pure_replay_imported_record :only (ReplayPair identity))
  (export orchestrate)
  (defworkflow orchestrate
    ((value ReplayPair))
    -> Bool
    (let* ((called
             (call identity :value value))
           (derived
             (if called.flag true false)))
      derived)))
"""


class _PostPersistInterruption(BaseException):
    pass


@dataclass(frozen=True)
class _HistoricalReplayBaseline:
    canonical_diagnostics: str
    declared_artifacts: str
    settlement_result: str
    executable_ir_sha256: str
    runtime_plan_sha256: str
    state_value_count: int
    state_bytes: int
    sidecar_bytes: int


def _copy_runtime_fixture(workspace: Path) -> Path:
    module_path = workspace / FIXTURE.name
    module_path.write_bytes(FIXTURE.read_bytes())
    scripts = workspace / "scripts"
    scripts.mkdir(parents=True)
    for name, source in _EFFECT_SCRIPTS.items():
        (scripts / name).write_text(source, encoding="utf-8")
    return module_path


def _copy_and_compile_fixture_details(workspace: Path):
    module_path = _copy_runtime_fixture(workspace)
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "count-e1": ExternalToolBinding(
                name="count-e1",
                stable_command=("python", "scripts/count_e1.py"),
            ),
            "finish-e2": ExternalToolBinding(
                name="finish-e2",
                stable_command=("python", "scripts/finish_e2.py"),
            ),
        },
        validate_shared=True,
        workspace_root=workspace,
    )
    bundle = result.validated_bundles_by_name[
        "pure_result_replay_effect_barrier::orchestrate"
    ]
    return (
        module_path,
        bundle,
        capture_frontend_diagnostic_identities(result.diagnostics),
    )


def _copy_and_compile_fixture(workspace: Path):
    module_path, bundle, _ = _copy_and_compile_fixture_details(workspace)
    return module_path, bundle


def _compile_replay_consumer_fixture(
    workspace: Path,
    *,
    module_name: str,
    source: str,
    command_boundaries: Mapping[str, ExternalToolBinding] | None = None,
):
    module_path = workspace / f"{module_name}.orc"
    module_path.write_text(source, encoding="utf-8")
    if command_boundaries:
        scripts = workspace / "scripts"
        scripts.mkdir(exist_ok=True)
        for script_name in ("count_e1.py", "finish_e2.py"):
            (scripts / script_name).write_text(
                _EFFECT_SCRIPTS[script_name],
                encoding="utf-8",
            )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        provider_externs={},
        prompt_externs={},
        command_boundaries=dict(command_boundaries or {}),
        validate_shared=True,
        workspace_root=workspace,
    )
    return (
        module_path,
        result.validated_bundles_by_name[f"{module_name}::orchestrate"],
    )


def _compile_imported_scalar_replay_fixture(workspace: Path):
    imported_path = workspace / "pure_replay_imported_scalar.orc"
    imported_path.write_text(_IMPORTED_SCALAR_CALL_SOURCE, encoding="utf-8")
    consumer_path = workspace / "pure_replay_imported_scalar_consumer.orc"
    consumer_path.write_text(
        _IMPORTED_SCALAR_CONSUMER_SOURCE,
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        consumer_path,
        source_roots=(workspace,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=workspace,
    )
    return result.validated_bundles_by_name[
        "pure_replay_imported_scalar_consumer::orchestrate"
    ]


def _compile_imported_record_replay_fixture(workspace: Path):
    imported_path = workspace / "pure_replay_imported_record.orc"
    imported_path.write_text(_IMPORTED_RECORD_CALL_SOURCE, encoding="utf-8")
    consumer_path = workspace / "pure_replay_imported_record_consumer.orc"
    consumer_path.write_text(
        _IMPORTED_RECORD_CONSUMER_SOURCE,
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        consumer_path,
        source_roots=(workspace,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=workspace,
    )
    return result.validated_bundles_by_name[
        "pure_replay_imported_record_consumer::orchestrate"
    ]


def _initialize_replay_consumer_fixture(
    workspace: Path,
    *,
    run_id: str,
    module_name: str,
    source: str,
    command_boundaries: Mapping[str, ExternalToolBinding] | None = None,
):
    module_path, bundle = _compile_replay_consumer_fixture(
        workspace,
        module_name=module_name,
        source=source,
        command_boundaries=command_boundaries,
    )
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        module_path.name,
        context=bundle_context_dict(bundle),
        bound_inputs={
            name: {
                "choose-left": True,
                "left-value": 10,
                "right-value": 20,
            }[name]
            for name in bundle.ir.inputs
            if name in {"choose-left", "left-value", "right-value"}
        },
        result_persistence_profile="derived_pure_replay.v1",
    )
    return module_path, bundle, manager


def _with_typed_finalization_consumer(
    workspace: Path,
    *,
    module_path: Path,
    bundle: Any,
    source_node_id: str,
):
    source_node = bundle.ir.nodes[source_node_id]
    source_address = derive_pure_result_replay_index(bundle).nodes[
        source_node_id
    ].output_addresses[0]
    finalization = SurfaceFinallyBlock(
        token="observe-selected",
        step_id="root.finally.observe_selected",
        steps=(
            SurfaceStep(
                name="ObserveSelected",
                step_id="root.finally.observe_selected.command",
                authored_id="observe_selected",
                kind=SurfaceStepKind.COMMAND,
                command=("python", "-c", "pass"),
                when_predicate=ArtifactBoolPredicateNode(
                    ref=source_address,
                ),
            ),
        ),
    )
    return build_loaded_workflow_bundle(
        replace(
            bundle.surface,
            finalization=finalization,
        ),
        imports=bundle.imports,
        private_artifact_ids=tuple(bundle.ir.private_artifacts),
    )


def _canonical_payload_sha256(value: Any) -> str:
    return hashlib.sha256(
        canonical_json_dumps(value).encode("utf-8")
    ).hexdigest()


def _canonical_program_digests(bundle: Any) -> tuple[str, str]:
    return (
        _canonical_payload_sha256(workflow_executable_ir_to_json(bundle.ir)),
        _canonical_payload_sha256(
            build_artifacts._public_runtime_plan_payload(bundle.runtime_plan)
        ),
    )


def _canonical_program_digest(bundle: Any) -> str:
    return _canonical_payload_sha256(
        {
            "executable_ir": workflow_executable_ir_to_json(bundle.ir),
            "runtime_plan": build_artifacts._public_runtime_plan_payload(
                bundle.runtime_plan
            ),
        }
    )


def _value_leaf_count(value: Any) -> int:
    if isinstance(value, Mapping):
        return sum(_value_leaf_count(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_value_leaf_count(item) for item in value)
    return 1


def _run_owned_sidecar_bytes(
    workspace: Path,
    *,
    state_file: Path,
) -> int:
    return sum(
        path.stat().st_size
        for path in (workspace / ".orchestrate").rglob("*")
        if path.is_file() and path != state_file
    )


def _canonical_diagnostics(
    state: Mapping[str, Any],
    *,
    frontend_diagnostics: tuple[tuple[object, ...], ...],
) -> str:
    step_errors = {
        name: {
            "step_id": step.get("step_id"),
            "error": step["error"],
        }
        for name, step in sorted(state.get("steps", {}).items())
        if isinstance(step, Mapping) and "error" in step
    }
    return canonical_json_dumps(
        {
            "frontend": frontend_diagnostics,
            "runtime": {
                "run_error": state.get("error"),
                "step_errors": step_errors,
            },
        }
    )


def _canonical_declared_artifacts(
    state: Mapping[str, Any],
    *,
    bundle: Any,
) -> str:
    artifact_names = tuple(sorted(bundle.ir.artifacts))
    assert set(state.get("artifact_versions", {})).issubset(artifact_names)
    assert set(state.get("artifact_consumes", {})).issubset(artifact_names)
    return canonical_json_dumps(
        {
            "versions": {
                name: state.get("artifact_versions", {}).get(name, [])
                for name in artifact_names
            },
            "consumes": {
                name: state.get("artifact_consumes", {}).get(name, {})
                for name in artifact_names
            },
        }
    )


def _capture_historical_baseline(
    workspace: Path,
    *,
    bundle: Any,
    manager: StateManager,
    frontend_diagnostics: tuple[tuple[object, ...], ...],
) -> _HistoricalReplayBaseline:
    state_bytes = manager.state_file.read_bytes()
    state = json.loads(state_bytes)
    executable_sha256, runtime_plan_sha256 = _canonical_program_digests(
        bundle
    )
    return _HistoricalReplayBaseline(
        canonical_diagnostics=_canonical_diagnostics(
            state,
            frontend_diagnostics=frontend_diagnostics,
        ),
        declared_artifacts=_canonical_declared_artifacts(
            state,
            bundle=bundle,
        ),
        settlement_result=canonical_json_dumps(state["workflow_outputs"]),
        executable_ir_sha256=executable_sha256,
        runtime_plan_sha256=runtime_plan_sha256,
        state_value_count=_value_leaf_count(state),
        state_bytes=len(state_bytes),
        sidecar_bytes=_run_owned_sidecar_bytes(
            workspace,
            state_file=manager.state_file,
        ),
    )


def _effect_calls(workspace: Path) -> list[str]:
    return (workspace / "state" / "effect_calls.log").read_text(
        encoding="utf-8"
    ).splitlines()


def _pure_bundle_paths(
    workspace: Path,
    state: Mapping[str, Any],
) -> list[Path]:
    return [
        workspace / value
        for name, value in state["bound_inputs"].items()
        if isinstance(value, str)
        and ("__a__result_bundle" in name or "__b__result_bundle" in name)
    ]


def _checkpoint_records(
    manager: StateManager,
) -> list[dict[str, Any]]:
    records_root = (
        manager.run_root
        / "workflow_lisp"
        / "checkpoints"
        / "records"
    )
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(records_root.rglob("*.json"))
    ]


def _execute_replay_profile_fixture(
    workspace: Path,
    *,
    run_id: str,
) -> tuple[Any, StateManager, dict[str, Any], dict[str, Any]]:
    bundle, manager = _initialize_replay_profile_fixture(
        workspace,
        run_id=run_id,
    )
    active = WorkflowExecutor(
        bundle,
        workspace,
        manager,
    ).execute(on_error="stop")
    persisted = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    return bundle, manager, active, persisted


def _initialize_replay_profile_fixture(
    workspace: Path,
    *,
    run_id: str,
) -> tuple[Any, StateManager]:
    module_path, bundle = _copy_and_compile_fixture(workspace)
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        module_path.name,
        context=bundle_context_dict(bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile="derived_pure_replay.v1",
    )
    return bundle, manager


def _public_run_args(
    workflow: Path,
    *,
    command_boundaries_file: Path,
) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        context=None,
        context_file=None,
        input=["seed=3", "enabled=true"],
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        dry_run=False,
        debug=False,
        quiet=False,
        verbose=False,
        log_level="info",
        backup_state=False,
        state_dir=None,
        on_error="stop",
        max_retries=0,
        retry_delay=0,
        stream_output=False,
        step_summaries=False,
        summary_mode=None,
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_provider="claude_sonnet_summary",
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow=None,
        source_root=None,
        provider_externs_file=None,
        prompt_externs_file=None,
        imported_workflow_bundles_file=None,
        command_boundaries_file=str(command_boundaries_file),
        emit_debug_yaml=False,
    )


def _assert_replay_profile_pure_rows(
    *,
    bundle: Any,
    active: Mapping[str, Any],
    persisted: Mapping[str, Any],
) -> None:
    for node_id in (
        _node_id_ending(bundle, "__a"),
        _node_id_ending(bundle, "__b"),
    ):
        presentation_key = (
            bundle.projection.entries_by_node_id[node_id].presentation_key
        )
        active_row = active["steps"][presentation_key]
        witness = pure_result_replay.PureReplayVisitWitness(
            presentation_key=presentation_key,
            step_index=bundle.ir.body_region.index(node_id),
            step_id=node_id,
            visit_count=1,
        )
        assert active_row["status"] == "completed"
        assert active_row["artifacts"]
        assert persisted["steps"][presentation_key] == (
            pure_result_replay.build_pure_completion_shell(witness)
        )


def _with_distinct_durable_step_id(
    bundle: Any,
    *,
    node_id: str,
) -> tuple[Any, str]:
    durable_step_id = f"{node_id}::durable"
    executable = replace(
        bundle.ir,
        nodes=MappingProxyType(
            {
                **dict(bundle.ir.nodes),
                node_id: replace(
                    bundle.ir.nodes[node_id],
                    step_id=durable_step_id,
                ),
            }
        ),
    )
    projection = replace(
        bundle.projection,
        entries_by_node_id=MappingProxyType(
            {
                **dict(bundle.projection.entries_by_node_id),
                node_id: replace(
                    bundle.projection.entries_by_node_id[node_id],
                    step_id=durable_step_id,
                ),
            }
        ),
        node_id_by_step_id=MappingProxyType(
            {
                **{
                    step_id: projected_node_id
                    for step_id, projected_node_id in (
                        bundle.projection.node_id_by_step_id.items()
                    )
                    if projected_node_id != node_id
                },
                durable_step_id: node_id,
            }
        ),
    )
    runtime_plan = derive_workflow_runtime_plan(
        executable,
        projection,
    )
    runtime_plan = replace(
        runtime_plan,
        lexical_checkpoint_points=tuple(
            (
                replace(point, step_id=durable_step_id)
                if point.node_id == node_id
                else point
            )
            for point in bundle.runtime_plan.lexical_checkpoint_points
        ),
    )
    return (
        replace(
            bundle,
            ir=executable,
            projection=projection,
            runtime_plan=runtime_plan,
        ),
        durable_step_id,
    )


def _with_durable_intrinsic_dependencies(bundle: Any) -> Any:
    b_node_id = _node_id_ending(bundle, "__b")
    b_node = bundle.ir.nodes[b_node_id]
    config = b_node.execution_config
    pure_projection = thaw_runtime_value(config.pure_projection)
    payload = pure_projection["payload"]
    e1_fields = payload["bindings"]["e1"]["type"]["fields"]
    e1_fields.extend(
        [
            {
                "name": "exit-code",
                "type": {"kind": "primitive", "name": "Int"},
            },
            {
                "name": "outcome-status",
                "type": {"kind": "primitive", "name": "String"},
            },
            {
                "name": "outcome-phase",
                "type": {"kind": "primitive", "name": "String"},
            },
            {
                "name": "outcome-class",
                "type": {"kind": "primitive", "name": "String"},
            },
            {
                "name": "outcome-retryable",
                "type": {"kind": "primitive", "name": "Bool"},
            },
        ]
    )
    e1_refs = pure_projection["binding_refs"]["e1"]
    selector = e1_refs["delta"]["ref"].removesuffix(
        ".artifacts.delta"
    )
    e1_refs.update(
        {
            "exit-code": {"ref": f"{selector}.exit_code"},
            "outcome-status": {
                "ref": f"{selector}.outcome.status"
            },
            "outcome-phase": {
                "ref": f"{selector}.outcome.phase"
            },
            "outcome-class": {
                "ref": f"{selector}.outcome.class"
            },
            "outcome-retryable": {
                "ref": f"{selector}.outcome.retryable"
            },
        }
    )
    pure_projection["payload_digest"] = pure_expr_payload_digest(
        payload
    )
    executable = replace(
        bundle.ir,
        nodes=MappingProxyType(
            {
                **dict(bundle.ir.nodes),
                b_node_id: replace(
                    b_node,
                    execution_config=replace(
                        config,
                        pure_projection=MappingProxyType(
                            pure_projection
                        ),
                    ),
                ),
            }
        ),
    )
    return replace(
        bundle,
        ir=executable,
    )


def _emit_unconfigured_replay_profile_checkpoint(
    *,
    bundle: Any,
    manager: StateManager,
    node_id: str,
    call_frame_id: str | None = None,
) -> Path:
    executor = WorkflowExecutor(bundle, manager.workspace, manager)
    executor._resolve_pure_projection_bindings = (  # type: ignore[method-assign]
        lambda document, _state: (document, None)
    )
    runtime_node = bundle.runtime_plan.nodes[node_id]
    records_root = (
        manager.run_root
        / "workflow_lisp"
        / "checkpoints"
        / "records"
    )
    before = set(records_root.rglob("*.json"))

    record = emit_runtime_shadow_record(
        executor=executor,
        step_id=runtime_node.step_id,
        execution_index=runtime_node.execution_index,
        visit_count=1,
        call_frame_id=call_frame_id,
        committed_step_state={
            "name": runtime_node.presentation_key,
            "step_id": runtime_node.step_id,
            "visit_count": 1,
            "status": "completed",
            "exit_code": 0,
            "artifacts": {},
        },
    )

    assert record is not None
    created = set(records_root.rglob("*.json")) - before
    assert len(created) == 1
    return created.pop()


def _with_recurrent_pure_node(bundle: Any, *, node_id: str) -> Any:
    node = bundle.ir.nodes[node_id]
    config = node.execution_config
    assert config is not None
    return replace(
        bundle,
        ir=replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    **dict(bundle.ir.nodes),
                    node_id: replace(
                        node,
                        execution_config=replace(
                            config,
                            common=replace(
                                config.common,
                                max_visits=2,
                            ),
                        ),
                    ),
                }
            ),
        ),
    )


def _audit_replay_profile_checkpoints(
    *,
    bundle: Any,
    manager: StateManager,
) -> None:
    assert manager.state is not None
    pure_result_replay.PureReplayRuntime(
        bundle=bundle,
        scope_path=ResumeScopePath.root(manager.state.workflow_file),
    ).audit_persisted_surfaces(
        state=manager.state.to_dict(),
        state_manager=manager,
        resolve_bundle_path=lambda _node_id: None,
    )


def test_pure_result_replay_fixture_compiles_real_effect_barrier_spine(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)

    kinds = [bundle.ir.nodes[node_id].kind.value for node_id in bundle.ir.body_region]

    assert kinds.count("pure_projection") >= 2
    assert kinds.count("command") == 2
    assert _canonical_program_digest(bundle)


def test_public_run_activates_replay_profile_with_value_free_pure_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit_workspace = tmp_path / "explicit"
    explicit_workspace.mkdir()
    monkeypatch.chdir(explicit_workspace)
    _, _, explicit_active, _ = _execute_replay_profile_fixture(
        explicit_workspace,
        run_id="pure-result-replay-explicit-control",
    )

    public_workspace = tmp_path / "public"
    public_workspace.mkdir()
    module_path, bundle, _ = _copy_and_compile_fixture_details(
        public_workspace,
    )
    command_boundaries_file = public_workspace / "command-boundaries.json"
    command_boundaries_file.write_text(
        json.dumps(
            {
                "count-e1": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "scripts/count_e1.py",
                    ],
                },
                "finish-e2": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "scripts/finish_e2.py",
                    ],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(public_workspace)

    result = run_workflow(
        _public_run_args(
            module_path,
            command_boundaries_file=command_boundaries_file,
        )
    )

    runs_root = public_workspace / ".orchestrate" / "runs"
    run_root = next(path for path in runs_root.iterdir() if path.is_dir())
    persisted = json.loads(
        (run_root / "state.json").read_text(encoding="utf-8")
    )
    assert result == 0
    assert (
        persisted["result_persistence_profile"]
        == DERIVED_PURE_REPLAY_PROFILE
    )
    for node_id in (
        _node_id_ending(bundle, "__a"),
        _node_id_ending(bundle, "__b"),
    ):
        presentation_key = (
            bundle.projection.entries_by_node_id[node_id].presentation_key
        )
        witness = pure_result_replay.PureReplayVisitWitness(
            presentation_key=presentation_key,
            step_index=bundle.ir.body_region.index(node_id),
            step_id=node_id,
            visit_count=1,
        )
        assert persisted["steps"][presentation_key] == (
            pure_result_replay.build_pure_completion_shell(witness)
        )
    pure_bundle_paths = _pure_bundle_paths(public_workspace, persisted)
    assert len(pure_bundle_paths) == 2
    assert all(not path.exists() for path in pure_bundle_paths)
    assert persisted["workflow_outputs"] == explicit_active[
        "workflow_outputs"
    ]


def test_pure_result_replay_fixture_historical_profile_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_workspace = tmp_path / "clean"
    clean_workspace.mkdir()
    (
        clean_module_path,
        clean_bundle,
        clean_frontend_diagnostics,
    ) = _copy_and_compile_fixture_details(
        clean_workspace,
    )
    clean_manager = StateManager(
        clean_workspace,
        run_id="pure-result-replay-historical-clean",
    )
    clean_manager.initialize(
        clean_module_path.name,
        context=bundle_context_dict(clean_bundle),
        bound_inputs={"seed": 3, "enabled": True},
    )

    monkeypatch.chdir(clean_workspace)
    clean_result = WorkflowExecutor(
        clean_bundle,
        clean_workspace,
        clean_manager,
    ).execute(on_error="stop")
    clean_baseline = _capture_historical_baseline(
        clean_workspace,
        bundle=clean_bundle,
        manager=clean_manager,
        frontend_diagnostics=clean_frontend_diagnostics,
    )

    resume_workspace = tmp_path / "resume"
    resume_workspace.mkdir()
    module_path = _copy_runtime_fixture(resume_workspace)
    bundle = clean_bundle
    frontend_diagnostics = clean_frontend_diagnostics
    run_id = "pure-result-replay-historical-resume"
    manager = StateManager(resume_workspace, run_id=run_id)
    manager.initialize(
        module_path.name,
        context=bundle_context_dict(bundle),
        bound_inputs={"seed": 3, "enabled": True},
    )
    b_step_name = bundle.projection.entries_by_node_id[
        _node_id_ending(bundle, "__b")
    ].presentation_key
    original_publish = (
        WorkflowExecutor._execute_top_level_publish_and_persist
    )

    def interrupt_after_b_bundle(
        executor: WorkflowExecutor,
        step: Any,
        step_name: str,
        state: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        if step_name == b_step_name:
            assert result["debug"]["pure_projection"] == {
                "reused_bundle": False
            }
            raise _PostPersistInterruption
        return original_publish(executor, step, step_name, state, result)

    monkeypatch.chdir(resume_workspace)
    with patch.object(
        WorkflowExecutor,
        "_execute_top_level_publish_and_persist",
        interrupt_after_b_bundle,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                resume_workspace,
                manager,
            ).execute(on_error="stop")

    interrupted = manager.load().to_dict()
    assert interrupted["current_step"]["step_id"] == _node_id_ending(
        bundle,
        "__b",
    )
    assert interrupted["current_step"]["status"] == "running"
    assert b_step_name not in interrupted["steps"]
    assert _effect_calls(resume_workspace) == ["E1"]
    interrupted_bundle_paths = _pure_bundle_paths(
        resume_workspace,
        interrupted,
    )
    assert len(interrupted_bundle_paths) == 2
    interrupted_bundle_bytes = {
        path: path.read_bytes() for path in interrupted_bundle_paths
    }

    fresh_manager = StateManager(resume_workspace, run_id=run_id)
    fresh_manager.load()
    result = WorkflowExecutor(
        bundle,
        resume_workspace,
        fresh_manager,
    ).execute(resume=True, on_error="stop")
    persisted = json.loads(
        fresh_manager.state_file.read_text(encoding="utf-8")
    )
    historical_baseline = _capture_historical_baseline(
        resume_workspace,
        bundle=bundle,
        manager=fresh_manager,
        frontend_diagnostics=frontend_diagnostics,
    )
    pure_steps = [
        step
        for step in result["steps"].values()
        if step.get("debug", {}).get("pure_projection") is not None
    ]
    pure_bundle_paths = _pure_bundle_paths(resume_workspace, persisted)

    assert clean_result["status"] == "completed"
    assert result["status"] == "completed"
    assert result["workflow_outputs"] == {
        "return__seed-value": 3,
        "return__effect-value": 4,
        "return__finished": True,
    }
    assert _effect_calls(clean_workspace) == ["E1", "E2"]
    assert _effect_calls(resume_workspace) == ["E1", "E2"]
    assert len(pure_steps) >= 2
    assert result["steps"][b_step_name]["debug"]["pure_projection"] == {
        "reused_bundle": True
    }
    assert len(pure_bundle_paths) == 2
    assert all(path.is_file() for path in pure_bundle_paths)
    assert {
        path: path.read_bytes() for path in pure_bundle_paths
    } == interrupted_bundle_bytes
    assert "result_persistence_profile" not in persisted
    assert clean_baseline.canonical_diagnostics == (
        historical_baseline.canonical_diagnostics
    )
    assert clean_baseline.declared_artifacts == (
        historical_baseline.declared_artifacts
    )
    assert clean_baseline.settlement_result == (
        historical_baseline.settlement_result
    )
    assert clean_baseline.executable_ir_sha256 == (
        historical_baseline.executable_ir_sha256
    )
    assert clean_baseline.runtime_plan_sha256 == (
        historical_baseline.runtime_plan_sha256
    )
    assert historical_baseline.state_value_count > 0
    assert historical_baseline.state_bytes > 0
    assert historical_baseline.sidecar_bytes > 0


def test_replay_profile_clean_run_keeps_pure_results_value_free_outside_active_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    bundle, manager, active, persisted = (
        _execute_replay_profile_fixture(
            tmp_path,
            run_id="pure-result-replay-value-free-clean",
        )
    )
    pure_node_ids = (
        _node_id_ending(bundle, "__a"),
        _node_id_ending(bundle, "__b"),
    )
    pure_source_step_ids: set[str] = set()

    for node_id in pure_node_ids:
        presentation_key = (
            bundle.projection.entries_by_node_id[node_id].presentation_key
        )
        active_row = active["steps"][presentation_key]
        witness = pure_result_replay.PureReplayVisitWitness(
            presentation_key=presentation_key,
            step_index=bundle.ir.body_region.index(node_id),
            step_id=active_row["step_id"],
            visit_count=1,
        )

        assert active_row["status"] == "completed"
        assert active_row["artifacts"]
        assert persisted["steps"][presentation_key] == (
            pure_result_replay.build_pure_completion_shell(witness)
        )
        pure_source_step_ids.add(
            active_row["step_id"].removeprefix("root.")
        )

    pure_bundle_paths = _pure_bundle_paths(tmp_path, persisted)
    assert len(pure_bundle_paths) == 2
    assert all(not path.exists() for path in pure_bundle_paths)
    assert persisted["private_artifact_versions"] == {}

    checkpoint_records = _checkpoint_records(manager)
    assert checkpoint_records
    assert all(
        record["pending_effect_policy"]["effect_kind"]
        != "pure_projection"
        for record in checkpoint_records
    )
    restore_bindings = [
        binding
        for record in checkpoint_records
        for binding in record.get("restore_payload", {}).get(
            "bindings",
            (),
        )
    ]
    assert all(
        binding.get("source_step_id") not in pure_source_step_ids
        for binding in restore_bindings
    )


@pytest.mark.parametrize(
    "forbidden_surface",
    (
        pytest.param("value_row", id="value-row"),
        pytest.param("pure_bundle", id="pure-bundle"),
        pytest.param("private_lineage", id="private-lineage"),
    ),
)
def test_replay_profile_conflict_rejects_before_prologue_or_state_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    forbidden_surface: str,
) -> None:
    run_id = f"pure-result-replay-profile-conflict-{forbidden_surface}"
    monkeypatch.chdir(tmp_path)
    bundle, manager, active, persisted = (
        _execute_replay_profile_fixture(
            tmp_path,
            run_id=run_id,
        )
    )
    a_node_id = _node_id_ending(bundle, "__a")
    a_name = bundle.projection.entries_by_node_id[
        a_node_id
    ].presentation_key
    if forbidden_surface == "value_row":
        persisted["steps"][a_name] = active["steps"][a_name]
        manager.state_file.write_text(
            json.dumps(persisted, indent=2) + "\n",
            encoding="utf-8",
        )
    elif forbidden_surface == "pure_bundle":
        a_bundle_path = next(
            path
            for path in _pure_bundle_paths(tmp_path, persisted)
            if "__a__result_bundle" in path.name
        )
        a_bundle_path.parent.mkdir(parents=True, exist_ok=True)
        a_bundle_path.write_text(
            '{"forbidden_profile_mix":true}\n',
            encoding="utf-8",
        )
    else:
        persisted["private_artifact_versions"] = {
            "forbidden-derived-value": [
                {
                    "producer": bundle.ir.nodes[a_node_id].step_id,
                    "value": {"seed": 3},
                }
            ]
        }
        manager.state_file.write_text(
            json.dumps(persisted, indent=2) + "\n",
            encoding="utf-8",
        )

    fresh_manager = StateManager(tmp_path, run_id=run_id)
    fresh_manager.load()
    fresh_executor = WorkflowExecutor(
        bundle,
        tmp_path,
        fresh_manager,
    )
    before_effect_calls = _effect_calls(tmp_path)
    with patch.object(
        fresh_executor,
        "_execute_prologue",
        side_effect=AssertionError(
            "profile audit must reject before executor prologue"
        ),
    ), patch.object(
        fresh_manager,
        "_write_state",
        side_effect=AssertionError(
            "profile audit must reject before a state write"
        ),
    ), patch.object(
        fresh_executor,
        "_execute_command",
        side_effect=AssertionError(
            "profile audit must reject before effect dispatch"
        ),
    ):
        with pytest.raises(ValueError) as excinfo:
            fresh_executor.execute(resume=True, on_error="stop")

    assert getattr(excinfo.value, "code", None) == (
        "pure_result_replay_unavailable"
    )
    assert getattr(excinfo.value, "reason", None) == "profile_conflict"
    assert getattr(excinfo.value, "context", {}).get("surface") == {
        "value_row": "steps",
        "pure_bundle": "pure_bundle",
        "private_lineage": "private_artifact_versions",
    }[forbidden_surface]
    assert _effect_calls(tmp_path) == before_effect_calls


@pytest.mark.parametrize("forbidden_surface", ["checkpoint", "restore_binding"])
def test_replay_profile_checkpoint_audit_rejects_eligible_same_scope_record(
    tmp_path: Path,
    forbidden_surface: str,
) -> None:
    bundle, manager = _initialize_replay_profile_fixture(
        tmp_path,
        run_id=f"checkpoint-scope-same-{forbidden_surface}",
    )
    node_id = _node_id_ending(
        bundle,
        "__a" if forbidden_surface == "checkpoint" else "__b",
    )
    if forbidden_surface == "restore_binding":
        bundle = _with_recurrent_pure_node(
            bundle,
            node_id=node_id,
        )
    _emit_unconfigured_replay_profile_checkpoint(
        bundle=bundle,
        manager=manager,
        node_id=node_id,
    )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        _audit_replay_profile_checkpoints(
            bundle=bundle,
            manager=manager,
        )

    assert excinfo.value.reason == "profile_conflict"
    assert excinfo.value.context["surface"] == (
        "checkpoint_record"
        if forbidden_surface == "checkpoint"
        else "restore_payload"
    )


def test_replay_profile_checkpoint_audit_allows_noneligible_recurrent_pure_record(
    tmp_path: Path,
) -> None:
    bundle, manager = _initialize_replay_profile_fixture(
        tmp_path,
        run_id="checkpoint-scope-recurrent",
    )
    node_id = _node_id_ending(bundle, "__a")
    recurrent_bundle = _with_recurrent_pure_node(
        bundle,
        node_id=node_id,
    )
    _emit_unconfigured_replay_profile_checkpoint(
        bundle=recurrent_bundle,
        manager=manager,
        node_id=node_id,
    )

    _audit_replay_profile_checkpoints(
        bundle=recurrent_bundle,
        manager=manager,
    )


def test_replay_profile_recurrent_pure_node_keeps_ordinary_durable_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path, bundle = _copy_and_compile_fixture(tmp_path)
    a_node_id = _node_id_ending(bundle, "__a")
    recurrent_bundle = _with_recurrent_pure_node(
        bundle,
        node_id=a_node_id,
    )
    replay_index = derive_pure_result_replay_index(recurrent_bundle)
    assert replay_index.ineligible_pure_reasons[a_node_id] == (
        "multiple_visit_region"
    )
    manager = StateManager(
        tmp_path,
        run_id="replay-profile-recurrent-pure-durable",
    )
    manager.initialize(
        module_path.name,
        context=bundle_context_dict(recurrent_bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile="derived_pure_replay.v1",
    )

    monkeypatch.chdir(tmp_path)
    active = WorkflowExecutor(
        recurrent_bundle,
        tmp_path,
        manager,
    ).execute(on_error="stop")
    persisted = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    a_name = recurrent_bundle.projection.entries_by_node_id[
        a_node_id
    ].presentation_key
    a_row = persisted["steps"][a_name]
    a_bundle_path = next(
        path
        for path in _pure_bundle_paths(tmp_path, persisted)
        if "__a__result_bundle" in path.name
    )
    a_checkpoint_ids = {
        point.checkpoint_id
        for point in recurrent_bundle.runtime_plan.lexical_checkpoint_points
        if point.node_id == a_node_id
    }

    assert active["status"] == "completed"
    assert a_row == active["steps"][a_name]
    assert a_row["status"] == "completed"
    assert a_row["artifacts"]
    assert "result_storage" not in a_row
    assert a_bundle_path.is_file()
    assert any(
        record["checkpoint_id"] in a_checkpoint_ids
        for record in _checkpoint_records(manager)
    )


def test_replay_profile_checkpoint_audit_ignores_eligible_record_in_other_frame(
    tmp_path: Path,
) -> None:
    bundle, manager = _initialize_replay_profile_fixture(
        tmp_path,
        run_id="checkpoint-scope-other-frame",
    )
    _emit_unconfigured_replay_profile_checkpoint(
        bundle=bundle,
        manager=manager,
        node_id=_node_id_ending(bundle, "__b"),
        call_frame_id="foreign-frame",
    )

    _audit_replay_profile_checkpoints(
        bundle=bundle,
        manager=manager,
    )


def test_pure_replay_resume_after_e2_interruption_preserves_effects_and_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_workspace = tmp_path / "clean"
    clean_workspace.mkdir()
    monkeypatch.chdir(clean_workspace)
    (
        clean_bundle,
        _clean_manager,
        clean_active,
        clean_persisted,
    ) = _execute_replay_profile_fixture(
        clean_workspace,
        run_id="pure-replay-resume-clean-control",
    )

    resume_workspace = tmp_path / "resume"
    resume_workspace.mkdir()
    bundle, manager = _initialize_replay_profile_fixture(
        resume_workspace,
        run_id="pure-replay-resume-after-e2-interruption",
    )
    e2_node_id = _node_id_ending(bundle, "__e2__finish_e2")
    original_execute_command = WorkflowExecutor._execute_command

    def interrupt_e2_after_visit_started(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if executor._step_id(step) == e2_node_id:
            raise _PostPersistInterruption
        return original_execute_command(executor, step, state)

    monkeypatch.chdir(resume_workspace)
    with patch.object(
        WorkflowExecutor,
        "_execute_command",
        interrupt_e2_after_visit_started,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                resume_workspace,
                manager,
            ).execute(on_error="stop")

    interrupted = manager.load().to_dict()
    assert interrupted["current_step"]["step_id"] == e2_node_id
    assert interrupted["current_step"]["status"] == "running"
    assert _effect_calls(resume_workspace) == ["E1"]
    assert all(
        not path.exists()
        for path in _pure_bundle_paths(
            resume_workspace,
            interrupted,
        )
    )

    fresh_manager = StateManager(
        resume_workspace,
        run_id="pure-replay-resume-after-e2-interruption",
    )
    fresh_manager.load()
    resumed = WorkflowExecutor(
        bundle,
        resume_workspace,
        fresh_manager,
    ).execute(resume=True, on_error="stop")
    persisted = json.loads(
        fresh_manager.state_file.read_text(encoding="utf-8")
    )

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == clean_active["workflow_outputs"]
    assert resumed["workflow_outputs"] == {
        "return__seed-value": 3,
        "return__effect-value": 4,
        "return__finished": True,
    }
    assert _canonical_diagnostics(
        persisted,
        frontend_diagnostics=(),
    ) == _canonical_diagnostics(
        clean_persisted,
        frontend_diagnostics=(),
    )
    assert _canonical_declared_artifacts(
        persisted,
        bundle=bundle,
    ) == _canonical_declared_artifacts(
        clean_persisted,
        bundle=clean_bundle,
    )
    assert canonical_json_dumps(
        persisted["workflow_outputs"]
    ) == canonical_json_dumps(
        clean_persisted["workflow_outputs"]
    )
    assert clean_bundle.ir.outputs == bundle.ir.outputs
    assert _effect_calls(resume_workspace) == ["E1", "E2"]
    _assert_replay_profile_pure_rows(
        bundle=bundle,
        active=resumed,
        persisted=persisted,
    )
    assert all(
        not path.exists()
        for path in _pure_bundle_paths(
            resume_workspace,
            persisted,
        )
    )


def test_pure_replay_e1_boundary_reconstructs_only_required_a_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, manager = _initialize_replay_profile_fixture(
        tmp_path,
        run_id="pure-replay-e1-exact-closure",
    )
    a_node_id = _node_id_ending(bundle, "__a")
    b_node_id = _node_id_ending(bundle, "__b")
    e1_node_id = _node_id_ending(bundle, "__e1__count_e1")
    original_execute_command = WorkflowExecutor._execute_command

    def interrupt_e1_after_visit_started(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if executor._step_id(step) == e1_node_id:
            raise _PostPersistInterruption
        return original_execute_command(executor, step, state)

    monkeypatch.chdir(tmp_path)
    with patch.object(
        WorkflowExecutor,
        "_execute_command",
        interrupt_e1_after_visit_started,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
            ).execute(on_error="stop")

    interrupted = manager.load().to_dict()
    assert interrupted["current_step"]["step_id"] == e1_node_id
    assert not (tmp_path / "state" / "effect_calls.log").exists()

    fresh_manager = StateManager(
        tmp_path,
        run_id=manager.run_id,
    )
    fresh_manager.load()
    fresh_executor = WorkflowExecutor(
        bundle,
        tmp_path,
        fresh_manager,
    )
    replayed_node_ids: list[str] = []
    original_replay_evaluation = (
        fresh_executor._evaluate_pure_replay_node
    )
    resumed_execute_command = fresh_executor._execute_command

    def record_replay_evaluation(
        node_id: str,
        state: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        replayed_node_ids.append(node_id)
        return original_replay_evaluation(node_id, state)

    def assert_exact_closure_before_effect(
        step: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if fresh_executor._step_id(step) == e1_node_id:
            assert replayed_node_ids == [a_node_id]
            assert b_node_id not in replayed_node_ids
        return resumed_execute_command(step, state)

    with patch.object(
        fresh_executor,
        "_evaluate_pure_replay_node",
        side_effect=record_replay_evaluation,
    ), patch.object(
        fresh_executor,
        "_execute_command",
        side_effect=assert_exact_closure_before_effect,
    ):
        resumed = fresh_executor.execute(
            resume=True,
            on_error="stop",
        )

    assert resumed["status"] == "completed"
    assert replayed_node_ids == [a_node_id]
    assert _effect_calls(tmp_path) == ["E1", "E2"]


def test_pure_replay_settlement_seeds_only_exact_typed_output_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _module_path,
        bundle,
        manager,
    ) = _initialize_replay_consumer_fixture(
        tmp_path,
        run_id="pure-replay-settlement-exact-closure",
        module_name="pure_result_replay_terminal_consumers",
        source=_TERMINAL_CONSUMER_SOURCE,
        command_boundaries={
            "count-e1": ExternalToolBinding(
                name="count-e1",
                stable_command=("python", "scripts/count_e1.py"),
            ),
            "finish-left": ExternalToolBinding(
                name="finish-left",
                stable_command=("python", "scripts/finish_e2.py"),
            ),
            "finish-right": ExternalToolBinding(
                name="finish-right",
                stable_command=("python", "scripts/finish_e2.py"),
            ),
            "finish-final": ExternalToolBinding(
                name="finish-final",
                stable_command=("python", "scripts/finish_e2.py"),
            ),
        },
    )
    index = derive_pure_result_replay_index(bundle)
    selected_node_id = _node_id_ending(
        bundle,
        "__terminal_projection",
    )
    unrelated_node_id = _node_id_ending(
        bundle,
        "__observed__condition",
    )
    assert selected_node_id in index.nodes
    assert unrelated_node_id in index.nodes

    monkeypatch.chdir(tmp_path)
    first_executor = WorkflowExecutor(bundle, tmp_path, manager)
    with patch.object(
        first_executor,
        "_execute_epilogue",
        side_effect=_PostPersistInterruption,
    ):
        with pytest.raises(_PostPersistInterruption):
            first_executor.execute(on_error="stop")

    interrupted = manager.load().to_dict()
    assert interrupted.get("current_step") is None
    assert interrupted["status"] == "running"

    fresh_manager = StateManager(tmp_path, run_id=manager.run_id)
    fresh_manager.load()
    fresh_executor = WorkflowExecutor(
        bundle,
        tmp_path,
        fresh_manager,
    )
    replayed_node_ids: list[str] = []
    original_replay_evaluation = (
        fresh_executor._evaluate_pure_replay_node
    )
    original_resolve_outputs = (
        workflow_executor_module.resolve_workflow_outputs
    )

    def record_replay_evaluation(
        node_id: str,
        state: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        replayed_node_ids.append(node_id)
        return original_replay_evaluation(node_id, state)

    def assert_exact_closure_before_settlement(*args: Any, **kwargs: Any):
        assert replayed_node_ids == [selected_node_id]
        assert unrelated_node_id not in replayed_node_ids
        return original_resolve_outputs(*args, **kwargs)

    with patch.object(
        fresh_executor,
        "_evaluate_pure_replay_node",
        side_effect=record_replay_evaluation,
    ), patch.object(
        workflow_executor_module,
        "resolve_workflow_outputs",
        side_effect=assert_exact_closure_before_settlement,
    ):
        resumed = fresh_executor.execute(
            resume=True,
            on_error="stop",
        )

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"return__selected": True}
    assert replayed_node_ids == [selected_node_id]


def test_pure_replay_finalization_seeds_only_exact_typed_predicate_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        module_path,
        base_bundle,
        _base_manager,
    ) = _initialize_replay_consumer_fixture(
        tmp_path,
        run_id="unused-base-run",
        module_name="pure_result_replay_terminal_consumers",
        source=_TERMINAL_CONSUMER_SOURCE,
        command_boundaries={
            "count-e1": ExternalToolBinding(
                name="count-e1",
                stable_command=("python", "scripts/count_e1.py"),
            ),
            "finish-left": ExternalToolBinding(
                name="finish-left",
                stable_command=("python", "scripts/finish_e2.py"),
            ),
            "finish-right": ExternalToolBinding(
                name="finish-right",
                stable_command=("python", "scripts/finish_e2.py"),
            ),
            "finish-final": ExternalToolBinding(
                name="finish-final",
                stable_command=("python", "scripts/finish_e2.py"),
            ),
        },
    )
    selected_node_id = _node_id_ending(
        base_bundle,
        "__terminal_projection",
    )
    unrelated_node_id = _node_id_ending(
        base_bundle,
        "__observed__condition",
    )
    bundle = _with_typed_finalization_consumer(
        tmp_path,
        module_path=module_path,
        bundle=base_bundle,
        source_node_id=selected_node_id,
    )
    finalization_node_id = bundle.ir.finalization_entry_node_id
    assert isinstance(finalization_node_id, str)
    finalization_node = bundle.ir.nodes[finalization_node_id]
    assert isinstance(
        finalization_node.bound_when_predicate.ref,
        NodeResultAddress,
    )
    assert (
        finalization_node.bound_when_predicate.ref.node_id
        == selected_node_id
    )

    manager = StateManager(
        tmp_path,
        run_id="pure-replay-finalization-exact-closure",
    )
    manager.initialize(
        module_path.name,
        context=bundle_context_dict(bundle),
        bound_inputs={},
        result_persistence_profile="derived_pure_replay.v1",
    )
    first_executor = WorkflowExecutor(bundle, tmp_path, manager)
    original_execute_command = first_executor._execute_command

    def interrupt_finalization(
        step: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if first_executor._step_id(step) == finalization_node.step_id:
            raise _PostPersistInterruption
        return original_execute_command(step, state)

    monkeypatch.chdir(tmp_path)
    with patch.object(
        first_executor,
        "_execute_command",
        side_effect=interrupt_finalization,
    ):
        with pytest.raises(_PostPersistInterruption):
            first_executor.execute(on_error="stop")

    interrupted = manager.load().to_dict()
    assert (
        interrupted["current_step"]["step_id"]
        == finalization_node.step_id
    )

    fresh_manager = StateManager(tmp_path, run_id=manager.run_id)
    fresh_manager.load()
    fresh_executor = WorkflowExecutor(
        bundle,
        tmp_path,
        fresh_manager,
    )
    replayed_node_ids: list[str] = []
    original_replay_evaluation = (
        fresh_executor._evaluate_pure_replay_node
    )
    original_evaluate_condition = (
        fresh_executor._evaluate_condition_expression
    )

    def record_replay_evaluation(
        node_id: str,
        state: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        replayed_node_ids.append(node_id)
        return original_replay_evaluation(node_id, state)

    def assert_exact_closure_before_finalization(
        condition: Any,
        variables: dict[str, Any],
        state: dict[str, Any],
        *,
        scope: dict[str, dict[str, Any]] | None = None,
    ) -> bool:
        if condition is finalization_node.bound_when_predicate:
            assert replayed_node_ids == [selected_node_id]
            assert unrelated_node_id not in replayed_node_ids
        return original_evaluate_condition(
            condition,
            variables,
            state,
            scope=scope,
        )

    with patch.object(
        fresh_executor,
        "_evaluate_pure_replay_node",
        side_effect=record_replay_evaluation,
    ), patch.object(
        fresh_executor,
        "_evaluate_condition_expression",
        side_effect=assert_exact_closure_before_finalization,
    ):
        resumed = fresh_executor.execute(
            resume=True,
            on_error="stop",
        )

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"return__selected": True}
    assert replayed_node_ids == [selected_node_id]


def test_pure_replay_resume_never_evaluates_inactive_route_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _module_path,
        bundle,
        manager,
    ) = _initialize_replay_consumer_fixture(
        tmp_path,
        run_id="pure-replay-inactive-route",
        module_name="pure_result_replay_routed_consumers",
        source=_ROUTED_CONSUMER_SOURCE,
        command_boundaries={
            "finish-left": ExternalToolBinding(
                name="finish-left",
                stable_command=("python", "scripts/finish_e2.py"),
            ),
            "finish-right": ExternalToolBinding(
                name="finish-right",
                stable_command=("python", "scripts/finish_e2.py"),
            )
        },
    )
    branch_pure_node_ids = tuple(
        node_id
        for node_id, node in bundle.ir.nodes.items()
        if (
            node.kind.value == "pure_projection"
            and (
                ".then." in node.presentation_name
                or ".else." in node.presentation_name
            )
        )
    )
    assert len(branch_pure_node_ids) == 2
    selected_node_id = next(
        node_id
        for node_id in branch_pure_node_ids
        if ".then." in bundle.ir.nodes[node_id].presentation_name
    )
    inactive_node_id = next(
        node_id
        for node_id in branch_pure_node_ids
        if ".else." in bundle.ir.nodes[node_id].presentation_name
    )
    original_execute_pure = WorkflowExecutor._execute_pure_projection

    def interrupt_selected_projection(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
        *,
        scope: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if executor._step_id(step) == bundle.ir.nodes[
            selected_node_id
        ].step_id:
            raise _PostPersistInterruption
        return original_execute_pure(
            executor,
            step,
            state,
            scope=scope,
        )

    monkeypatch.chdir(tmp_path)
    with patch.object(
        WorkflowExecutor,
        "_execute_pure_projection",
        interrupt_selected_projection,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
            ).execute(on_error="stop")

    fresh_manager = StateManager(tmp_path, run_id=manager.run_id)
    fresh_manager.load()
    fresh_executor = WorkflowExecutor(
        bundle,
        tmp_path,
        fresh_manager,
    )
    evaluated_node_ids: list[str] = []
    original_execute_pure = (
        fresh_executor._execute_pure_projection
    )

    def record_pure_evaluation(
        step: Any,
        state: Mapping[str, Any],
        *,
        scope: dict[str, dict[str, Any]] | None = None,
    ) -> Mapping[str, Any]:
        node_id = fresh_executor._pure_replay_runtime.node_id_for_step_id(
            fresh_executor._step_id(step)
        )
        if isinstance(node_id, str):
            evaluated_node_ids.append(node_id)
        return original_execute_pure(
            step,
            dict(state),
            scope=scope,
        )

    with patch.object(
        fresh_executor,
        "_execute_pure_projection",
        side_effect=record_pure_evaluation,
    ):
        resumed = fresh_executor.execute(
            resume=True,
            on_error="stop",
        )

    assert resumed["status"] == "completed"
    assert evaluated_node_ids == [selected_node_id]
    assert inactive_node_id not in evaluated_node_ids
    assert _effect_calls(tmp_path) == ["E2"]


@pytest.mark.parametrize(
    "target_suffix",
    (
        pytest.param("__a", id="a-before-first-durable-boundary"),
        pytest.param("__b", id="b-after-e1"),
    ),
)
def test_interrupted_pure_current_reuses_visit_and_evaluates_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_suffix: str,
) -> None:
    bundle, manager = _initialize_replay_profile_fixture(
        tmp_path,
        run_id=f"interrupted-pure-current-{target_suffix.removeprefix('__')}",
    )
    target_node_id = _node_id_ending(bundle, target_suffix)
    target_name = bundle.projection.entries_by_node_id[
        target_node_id
    ].presentation_key
    original_execute_pure = WorkflowExecutor._execute_pure_projection

    def interrupt_after_atomic_begin(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
        *,
        scope: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if executor._step_id(step) == target_node_id:
            raise _PostPersistInterruption
        return original_execute_pure(
            executor,
            step,
            state,
            scope=scope,
        )

    monkeypatch.chdir(tmp_path)
    with patch.object(
        WorkflowExecutor,
        "_execute_pure_projection",
        interrupt_after_atomic_begin,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
            ).execute(on_error="stop")

    interrupted = manager.load().to_dict()
    assert interrupted["current_step"]["step_id"] == target_node_id
    assert interrupted["current_step"]["visit_count"] == 1
    assert interrupted["step_visits"][target_name] == 1
    assert target_name not in interrupted["steps"]
    if target_suffix == "__a":
        assert not (tmp_path / "state" / "effect_calls.log").exists()
        assert _checkpoint_records(manager) == []
    else:
        assert _effect_calls(tmp_path) == ["E1"]

    fresh_manager = StateManager(
        tmp_path,
        run_id=manager.run_id,
    )
    fresh_manager.load()
    evaluated_node_ids: list[str] = []

    def record_pure_evaluation(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
        *,
        scope: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        evaluated_node_ids.append(executor._step_id(step))
        return original_execute_pure(
            executor,
            step,
            state,
            scope=scope,
        )

    with patch.object(
        WorkflowExecutor,
        "_execute_pure_projection",
        record_pure_evaluation,
    ):
        resumed = WorkflowExecutor(
            bundle,
            tmp_path,
            fresh_manager,
        ).execute(resume=True, on_error="stop")
    persisted = json.loads(
        fresh_manager.state_file.read_text(encoding="utf-8")
    )

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {
        "return__seed-value": 3,
        "return__effect-value": 4,
        "return__finished": True,
    }
    assert evaluated_node_ids.count(target_node_id) == 1
    assert persisted["step_visits"][target_name] == 1
    assert _effect_calls(tmp_path) == ["E1", "E2"]
    _assert_replay_profile_pure_rows(
        bundle=bundle,
        active=resumed,
        persisted=persisted,
    )
    assert all(
        not path.exists()
        for path in _pure_bundle_paths(tmp_path, persisted)
    )


def test_pure_replay_overlay_requires_exact_typed_address_over_persisted_shell(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=bundle,
        scope_path=ResumeScopePath.root(str(FIXTURE)),
    )
    a_node_id = _node_id_ending(bundle, "__a")
    replay_node = runtime.index.nodes[a_node_id]
    witness = runtime.witness(a_node_id)
    full_result = {
        "name": witness.presentation_key,
        "step_id": witness.step_id,
        "visit_count": 1,
        "status": "completed",
        "exit_code": 0,
        "artifacts": {"return__value": 3},
    }
    persisted = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            )
        },
    }
    runtime.record_full_result(
        a_node_id,
        witness=witness,
        result=full_result,
    )

    assert runtime.resolve_state_address(
        replay_node.output_addresses[0],
        persisted,
    ) == (True, 3)
    for untyped_selector in (
        a_node_id,
        witness.presentation_key,
    ):
        with pytest.raises(TypeError):
            runtime.resolve_state_address(  # type: ignore[arg-type]
                untyped_selector,
                persisted,
            )
    assert not hasattr(runtime, "result_for_node_id")
    assert not hasattr(runtime, "result_for_state_node_id")
    assert runtime.overlay_active_state(persisted)["steps"][
        witness.presentation_key
    ] == full_result
    assert persisted["steps"][witness.presentation_key] == (
        pure_result_replay.build_pure_completion_shell(witness)
    )


def test_replay_profile_uses_distinct_durable_step_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path, bundle = _copy_and_compile_fixture(tmp_path)
    a_node_id = _node_id_ending(bundle, "__a")
    synthetic_bundle, durable_step_id = (
        _with_distinct_durable_step_id(
            bundle,
            node_id=a_node_id,
        )
    )
    assert a_node_id != durable_step_id
    manager = StateManager(
        tmp_path,
        run_id="pure-replay-distinct-durable-step-id",
    )
    manager.initialize(
        module_path.name,
        context=bundle_context_dict(synthetic_bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile="derived_pure_replay.v1",
    )

    monkeypatch.chdir(tmp_path)
    active = WorkflowExecutor(
        synthetic_bundle,
        tmp_path,
        manager,
    ).execute(on_error="stop")
    persisted = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=synthetic_bundle,
        scope_path=ResumeScopePath.root(str(module_path)),
    )
    witness = runtime.witness(a_node_id)

    assert active["status"] == "completed"
    assert witness.step_id == durable_step_id
    assert runtime.node_id_for_step_id(durable_step_id) == a_node_id
    assert runtime.node_id_for_step_id(a_node_id) is None
    assert persisted["steps"][witness.presentation_key] == (
        pure_result_replay.build_pure_completion_shell(witness)
    )


@pytest.mark.parametrize(
    "invalid_progress",
    (
        pytest.param("cursor", id="visit-two-cursor"),
        pytest.param("shell", id="visit-two-shell"),
    ),
)
def test_replay_profile_rejects_visit_two_progress_before_prologue(
    tmp_path: Path,
    invalid_progress: str,
) -> None:
    module_path, bundle = _copy_and_compile_fixture(tmp_path)
    manager = StateManager(
        tmp_path,
        run_id=f"pure-replay-visit-two-{invalid_progress}",
    )
    manager.initialize(
        module_path.name,
        context=bundle_context_dict(bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile="derived_pure_replay.v1",
    )
    a_node_id = _node_id_ending(bundle, "__a")
    a_name = bundle.projection.entries_by_node_id[
        a_node_id
    ].presentation_key
    payload = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    payload["step_visits"][a_name] = 2
    if invalid_progress == "cursor":
        payload["current_step"] = {
            "name": a_name,
            "index": bundle.ir.body_region.index(a_node_id),
            "type": "pure_projection",
            "status": "running",
            "started_at": "2026-07-30T12:00:00+00:00",
            "last_heartbeat_at": "2026-07-30T12:00:00+00:00",
            "step_id": bundle.ir.nodes[a_node_id].step_id,
            "visit_count": 2,
        }
    else:
        payload["steps"][a_name] = {
            "name": a_name,
            "step_id": bundle.ir.nodes[a_node_id].step_id,
            "visit_count": 2,
            "status": "completed",
            "exit_code": 0,
            "outcome": {
                "status": "completed",
                "phase": "execution",
                "class": "completed",
                "retryable": False,
            },
            "result_storage": "derived_pure_replay.v1",
        }
    manager.state_file.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    fresh_manager = StateManager(
        tmp_path,
        run_id=manager.run_id,
    )
    fresh_manager.load()
    executor = WorkflowExecutor(
        bundle,
        tmp_path,
        fresh_manager,
    )
    with patch.object(
        executor,
        "_execute_prologue",
        side_effect=AssertionError(
            "invalid replay progress must reject before prologue"
        ),
    ):
        with pytest.raises(PureResultReplayIndexError) as excinfo:
            executor.execute(resume=True, on_error="stop")

    assert excinfo.value.reason == "progress_witness_invalid"


def test_pure_replay_resume_accepts_exact_durable_intrinsic_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path, compiled_bundle = _copy_and_compile_fixture(tmp_path)
    bundle = _with_durable_intrinsic_dependencies(compiled_bundle)
    manager = StateManager(
        tmp_path,
        run_id="pure-replay-valid-durable-intrinsics",
    )
    manager.initialize(
        module_path.name,
        context=bundle_context_dict(bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile="derived_pure_replay.v1",
    )
    e2_node_id = _node_id_ending(bundle, "__e2__finish_e2")
    original_execute_command = WorkflowExecutor._execute_command

    def interrupt_e2(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if executor._step_id(step) == e2_node_id:
            raise _PostPersistInterruption
        return original_execute_command(executor, step, state)

    monkeypatch.chdir(tmp_path)
    with patch.object(
        WorkflowExecutor,
        "_execute_command",
        interrupt_e2,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
            ).execute(on_error="stop")

    fresh_manager = StateManager(tmp_path, run_id=manager.run_id)
    fresh_manager.load()
    resumed = WorkflowExecutor(
        bundle,
        tmp_path,
        fresh_manager,
    ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {
        "return__seed-value": 3,
        "return__effect-value": 4,
        "return__finished": True,
    }
    assert _effect_calls(tmp_path) == ["E1", "E2"]


@pytest.mark.parametrize(
    ("field", "member", "wrong_value"),
    (
        pytest.param("exit_code", None, "0", id="exit-code"),
        pytest.param("outcome", "status", False, id="outcome-status"),
        pytest.param("outcome", "phase", 1, id="outcome-phase"),
        pytest.param("outcome", "class", [], id="outcome-class"),
        pytest.param(
            "outcome",
            "retryable",
            "false",
            id="outcome-retryable",
        ),
    ),
)
def test_pure_replay_resume_rejects_wrong_typed_durable_intrinsic_before_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    member: str | None,
    wrong_value: Any,
) -> None:
    module_path, compiled_bundle = _copy_and_compile_fixture(tmp_path)
    bundle = _with_durable_intrinsic_dependencies(compiled_bundle)
    manager = StateManager(
        tmp_path,
        run_id=f"pure-replay-invalid-intrinsic-{field}-{member}",
    )
    manager.initialize(
        module_path.name,
        context=bundle_context_dict(bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile="derived_pure_replay.v1",
    )
    e1_node_id = _node_id_ending(bundle, "__e1__count_e1")
    e2_node_id = _node_id_ending(bundle, "__e2__finish_e2")
    e1_name = bundle.projection.entries_by_node_id[
        e1_node_id
    ].presentation_key
    original_execute_command = WorkflowExecutor._execute_command

    def interrupt_e2(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if executor._step_id(step) == e2_node_id:
            raise _PostPersistInterruption
        return original_execute_command(executor, step, state)

    monkeypatch.chdir(tmp_path)
    with patch.object(
        WorkflowExecutor,
        "_execute_command",
        interrupt_e2,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
            ).execute(on_error="stop")

    payload = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    if member is None:
        payload["steps"][e1_name][field] = wrong_value
    else:
        payload["steps"][e1_name][field][member] = wrong_value
    manager.state_file.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    fresh_manager = StateManager(tmp_path, run_id=manager.run_id)
    fresh_manager.load()

    with patch.object(
        WorkflowExecutor,
        "_execute_command",
        side_effect=AssertionError(
            "invalid intrinsic input reached the next effect"
        ),
    ):
        result = WorkflowExecutor(
            bundle,
            tmp_path,
            fresh_manager,
        ).execute(resume=True, on_error="stop")

    assert result["status"] == "failed"
    assert result["error"]["type"] == "pure_result_replay_unavailable"
    assert result["error"]["context"]["reason"] == (
        "durable_input_invalid"
    )
    assert _effect_calls(tmp_path) == ["E1"]


@pytest.mark.parametrize(
    ("durable_fault", "expected_reason"),
    (
        pytest.param(
            "missing",
            "durable_input_missing",
            id="missing-e1",
        ),
        pytest.param(
            "invalid",
            "durable_input_invalid",
            id="invalid-e1",
        ),
    ),
)
def test_pure_replay_invalid_durable_input_rejects_before_e2_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    durable_fault: str,
    expected_reason: str,
) -> None:
    bundle, manager = _initialize_replay_profile_fixture(
        tmp_path,
        run_id=f"pure-replay-{durable_fault}-durable-input",
    )
    e2_node_id = _node_id_ending(bundle, "__e2__finish_e2")
    e1_node_id = _node_id_ending(bundle, "__e1__count_e1")
    e1_name = bundle.projection.entries_by_node_id[
        e1_node_id
    ].presentation_key
    original_execute_command = WorkflowExecutor._execute_command

    def interrupt_e2(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if executor._step_id(step) == e2_node_id:
            raise _PostPersistInterruption
        return original_execute_command(executor, step, state)

    monkeypatch.chdir(tmp_path)
    with patch.object(
        WorkflowExecutor,
        "_execute_command",
        interrupt_e2,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
            ).execute(on_error="stop")

    payload = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    if durable_fault == "missing":
        payload["steps"].pop(e1_name)
    else:
        payload["steps"][e1_name]["artifacts"]["delta"] = (
            "not-an-integer"
        )
    manager.state_file.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    fresh_manager = StateManager(tmp_path, run_id=manager.run_id)
    fresh_manager.load()

    with patch.object(
        WorkflowExecutor,
        "_execute_command",
        side_effect=AssertionError(
            "invalid replay input must reject before E2 dispatch"
        ),
    ):
        result = WorkflowExecutor(
            bundle,
            tmp_path,
            fresh_manager,
        ).execute(resume=True, on_error="stop")

    assert result["status"] == "failed"
    assert result["error"]["type"] == "pure_result_replay_unavailable"
    assert result["error"]["context"]["reason"] == expected_reason
    assert _effect_calls(tmp_path) == ["E1"]


@pytest.mark.parametrize(
    ("source_fault", "expected_reason", "injected_error_type"),
    (
        pytest.param(
            "missing_bound_input",
            "durable_input_missing",
            None,
            id="missing-bound-input",
        ),
        pytest.param(
            "invalid_bound_input",
            "durable_input_invalid",
            None,
            id="invalid-bound-input",
        ),
        pytest.param(
            "unresolved_binding",
            "binding_unresolved",
            "materialize_ref_unresolved",
            id="unresolved-binding",
        ),
        pytest.param(
            "evaluation_failure",
            "evaluation_failed",
            "pure_evaluation_failed",
            id="evaluation-failure",
        ),
        pytest.param(
            "output_contract_failure",
            "output_contract_invalid",
            "pure_projection_contract_invalid",
            id="output-contract-failure",
        ),
    ),
)
def test_pure_replay_invalid_source_rejects_before_e2_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_fault: str,
    expected_reason: str,
    injected_error_type: str | None,
) -> None:
    bundle, manager = _initialize_replay_profile_fixture(
        tmp_path,
        run_id=f"pure-replay-invalid-source-{source_fault}",
    )
    e2_node_id = _node_id_ending(bundle, "__e2__finish_e2")
    original_execute_command = WorkflowExecutor._execute_command

    def interrupt_e2(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if executor._step_id(step) == e2_node_id:
            raise _PostPersistInterruption
        return original_execute_command(executor, step, state)

    monkeypatch.chdir(tmp_path)
    with patch.object(
        WorkflowExecutor,
        "_execute_command",
        interrupt_e2,
    ):
        with pytest.raises(_PostPersistInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
            ).execute(on_error="stop")

    payload = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    if source_fault == "missing_bound_input":
        payload["bound_inputs"].pop("seed")
    elif source_fault == "invalid_bound_input":
        payload["bound_inputs"]["seed"] = "not-an-integer"
    manager.state_file.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    fresh_manager = StateManager(tmp_path, run_id=manager.run_id)
    fresh_manager.load()
    fresh_executor = WorkflowExecutor(
        bundle,
        tmp_path,
        fresh_manager,
    )
    original_execute_pure = fresh_executor._execute_pure_projection

    def inject_replay_failure(
        step: Any,
        state: dict[str, Any],
        *,
        scope: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if injected_error_type is None:
            return original_execute_pure(
                step,
                state,
                scope=scope,
            )
        return {
            "status": "failed",
            "exit_code": 1,
            "error": {
                "type": injected_error_type,
                "message": f"synthetic {source_fault}",
                "context": {
                    "untrusted_detail": "must-not-enter-replay-diagnostic"
                },
            },
        }

    with patch.object(
        fresh_executor,
        "_execute_pure_projection",
        side_effect=inject_replay_failure,
    ), patch.object(
        fresh_executor,
        "_execute_command",
        side_effect=AssertionError(
            "invalid replay source must reject before E2 dispatch"
        ),
    ):
        result = fresh_executor.execute(
            resume=True,
            on_error="stop",
        )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "pure_result_replay_unavailable"
    assert result["error"]["context"]["reason"] == expected_reason
    if injected_error_type is None:
        assert "cause" not in result["error"]["context"]
    else:
        assert result["error"]["context"]["cause"] == {
            "type": injected_error_type,
        }
    assert _effect_calls(tmp_path) == ["E1"]


def _node_id_ending(bundle: Any, suffix: str) -> str:
    return next(
        node_id for node_id in bundle.ir.body_region if node_id.endswith(suffix)
    )


def _replace_binding_refs(
    bundle: Any,
    *,
    node_id: str,
    binding_refs: Mapping[str, Any],
):
    node = bundle.ir.nodes[node_id]
    config = node.execution_config
    assert config is not None
    pure_projection = {
        **dict(config.pure_projection),
        "binding_refs": binding_refs,
    }
    replacement = replace(
        node,
        execution_config=replace(
            config,
            pure_projection=MappingProxyType(pure_projection),
        ),
    )
    return replace(
        bundle.ir,
        nodes=MappingProxyType(
            {
                **dict(bundle.ir.nodes),
                node_id: replacement,
            }
        ),
    )


def _replace_payload_binding_type(
    bundle: Any,
    *,
    node_id: str,
    binding_name: str,
    descriptor: Mapping[str, Any],
):
    node = bundle.ir.nodes[node_id]
    config = node.execution_config
    assert isinstance(config, PureProjectionStepConfig)
    pure_projection = dict(config.pure_projection)
    payload = dict(pure_projection["payload"])
    bindings = dict(payload["bindings"])
    binding = dict(bindings[binding_name])
    binding["type"] = MappingProxyType(dict(descriptor))
    bindings[binding_name] = MappingProxyType(binding)
    payload["bindings"] = MappingProxyType(bindings)
    pure_projection["payload"] = MappingProxyType(payload)
    replacement = replace(
        node,
        execution_config=replace(
            config,
            pure_projection=MappingProxyType(pure_projection),
        ),
    )
    return replace(
        bundle,
        ir=replace(
            bundle.ir,
            nodes=MappingProxyType(
                {**dict(bundle.ir.nodes), node_id: replacement}
            ),
        ),
    )


def test_pure_replay_imported_scalar_call_contract_is_shared_by_index_and_runtime(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    call_id = next(
        node_id
        for node_id, node in bundle.ir.nodes.items()
        if isinstance(node, CallBoundaryNode)
    )
    derived_id = _node_id_ending(bundle, "__derived")

    runtime = pure_result_replay.PureReplayRuntime(
        bundle=bundle,
        scope_path=ResumeScopePath.root(
            str(tmp_path / "pure_replay_imported_scalar_consumer.orc")
        ),
    )
    replay_node = runtime.index.nodes[derived_id]
    witness = runtime.witness(derived_id)
    call_name = bundle.projection.presentation_key_by_node_id[call_id]
    state = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            call_name: {
                "status": "completed",
                "exit_code": 0,
                "artifacts": {"__result__": True},
            },
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            ),
        },
        "bound_inputs": {"value": True},
    }

    assert replay_node.durable_dependency_node_ids == (call_id,)
    evaluated_states: list[Mapping[str, Any]] = []

    def evaluate(
        node_id: str,
        active_state: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        assert node_id == derived_id
        called = active_state["steps"][call_name]["artifacts"]["__result__"]
        assert called is True
        evaluated_states.append(active_state)
        return {
            "name": witness.presentation_key,
            "step_id": witness.step_id,
            "visit_count": 1,
            "status": "completed",
            "exit_code": 0,
            "artifacts": {"__result__": called},
        }

    runtime.replay_node(
        derived_id,
        state=state,
        evaluate_node=evaluate,
    )

    assert len(evaluated_states) == 1
    assert runtime.value_for_state_address(
        NodeResultAddress(derived_id, "artifacts", "__result__"),
        state,
    ) is True


def test_pure_replay_import_alias_is_bound_separately_from_workflow_identity(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    call_id, call_node = next(
        (node_id, node)
        for node_id, node in bundle.ir.nodes.items()
        if isinstance(node, CallBoundaryNode)
    )
    original_alias = call_node.call_alias
    local_alias = "local-identity"
    config = call_node.execution_config
    assert isinstance(config, CallStepConfig)
    metadata = bundle.surface.imports[original_alias]
    imported = bundle.imports[original_alias]
    aliased_node = replace(
        call_node,
        call_alias=local_alias,
        execution_config=replace(config, call=local_alias),
    )
    aliased_bundle = replace(
        bundle,
        surface=replace(
            bundle.surface,
            imports=MappingProxyType(
                {local_alias: replace(metadata, alias=local_alias)}
            ),
        ),
        ir=replace(
            bundle.ir,
            nodes=MappingProxyType(
                {**dict(bundle.ir.nodes), call_id: aliased_node}
            ),
        ),
        imports=MappingProxyType({local_alias: imported}),
    )

    contract = pure_result_replay._compiled_node_result_contract(
        aliased_bundle,
        NodeResultAddress(call_id, "artifacts", "__result__"),
    )

    assert contract == imported.surface.outputs["__result__"].definition


@pytest.mark.parametrize(
    "fault",
    (
        "caller-import-alias",
        "caller-import-workflow",
        "caller-import-output-domain",
        "imported-surface-identity",
        "imported-executable-identity",
    ),
)
def test_pure_replay_imported_call_identity_catalog_tamper_fails_closed(
    tmp_path: Path,
    fault: str,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    call_node = next(
        node
        for node in bundle.ir.nodes.values()
        if isinstance(node, CallBoundaryNode)
    )
    alias = call_node.call_alias
    if fault.startswith("caller-import-"):
        metadata = bundle.surface.imports[alias]
        if fault == "caller-import-alias":
            metadata = replace(metadata, alias="wrong::identity")
        elif fault == "caller-import-workflow":
            metadata = replace(metadata, workflow_name="wrong::identity")
        else:
            metadata = replace(metadata, output_names=("not_declared",))
        bundle = replace(
            bundle,
            surface=replace(
                bundle.surface,
                imports=MappingProxyType(
                    {**dict(bundle.surface.imports), alias: metadata}
                ),
            ),
        )
    else:
        imported = bundle.imports[alias]
        if fault == "imported-surface-identity":
            imported = replace(
                imported,
                surface=replace(imported.surface, name="wrong::identity"),
            )
        else:
            imported = replace(
                imported,
                ir=replace(imported.ir, name="wrong::identity"),
            )
        bundle = replace(
            bundle,
            imports=MappingProxyType({**dict(bundle.imports), alias: imported}),
        )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(bundle)

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_imported_call_unknown_output_member_fails_closed(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    derived_id = _node_id_ending(bundle, "__derived")
    config = bundle.ir.nodes[derived_id].execution_config
    assert isinstance(config, PureProjectionStepConfig)
    binding_refs = dict(config.pure_projection["binding_refs"])
    call_ref = binding_refs["called"]["ref"]
    binding_refs["called"] = {
        "ref": call_ref.rsplit(".", 1)[0] + ".not_declared",
    }
    tampered_ir = _replace_binding_refs(
        bundle,
        node_id=derived_id,
        binding_refs=binding_refs,
    )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(replace(bundle, ir=tampered_ir))

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID
    assert excinfo.value.context["member"] == "not_declared"


@pytest.mark.parametrize(
    "fault",
    ("available-output-removed", "surface-contract-removed", "catalog-mismatch"),
)
def test_pure_replay_imported_call_contract_catalog_tamper_fails_closed(
    tmp_path: Path,
    fault: str,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    call_id, call_node = next(
        (node_id, node)
        for node_id, node in bundle.ir.nodes.items()
        if isinstance(node, CallBoundaryNode)
    )
    if fault == "available-output-removed":
        bundle = replace(
            bundle,
            ir=replace(
                bundle.ir,
                nodes=MappingProxyType(
                    {
                        **dict(bundle.ir.nodes),
                        call_id: replace(call_node, available_outputs=()),
                    }
                ),
            ),
        )
    else:
        imported = bundle.imports[call_node.call_alias]
        if fault == "surface-contract-removed":
            imported = replace(
                imported,
                surface=replace(
                    imported.surface,
                    outputs=MappingProxyType({}),
                ),
            )
        else:
            executable_contract = imported.ir.outputs["__result__"]
            imported = replace(
                imported,
                ir=replace(
                    imported.ir,
                    outputs=MappingProxyType(
                        {
                            **dict(imported.ir.outputs),
                            "__result__": replace(
                                executable_contract,
                                definition=MappingProxyType(
                                    {"type": "string", "kind": "scalar"}
                                ),
                            ),
                        }
                    ),
                ),
            )
        bundle = replace(
            bundle,
            imports=MappingProxyType(
                {**dict(bundle.imports), call_node.call_alias: imported}
            ),
        )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(bundle)

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID
    assert excinfo.value.context["member"] == "__result__"


def test_pure_replay_imported_call_contract_definitions_compare_exact_json_types(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    call_node = next(
        node
        for node in bundle.ir.nodes.values()
        if isinstance(node, CallBoundaryNode)
    )
    imported = bundle.imports[call_node.call_alias]
    surface_contract = imported.surface.outputs["__result__"]
    executable_contract = imported.ir.outputs["__result__"]
    imported = replace(
        imported,
        surface=replace(
            imported.surface,
            outputs=MappingProxyType(
                {
                    "__result__": replace(
                        surface_contract,
                        definition=MappingProxyType(
                            {
                                **dict(surface_contract.definition),
                                "integrity_probe": (
                                    MappingProxyType({"value": True}),
                                ),
                            }
                        ),
                    )
                }
            ),
        ),
        ir=replace(
            imported.ir,
            outputs=MappingProxyType(
                {
                    "__result__": replace(
                        executable_contract,
                        definition=MappingProxyType(
                            {
                                **dict(executable_contract.definition),
                                "integrity_probe": (
                                    MappingProxyType({"value": 1}),
                                ),
                            }
                        ),
                    )
                }
            ),
        ),
    )
    bundle = replace(
        bundle,
        imports=MappingProxyType(
            {**dict(bundle.imports), call_node.call_alias: imported}
        ),
    )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(bundle)

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_imported_call_contract_must_match_consumer_binding_type(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    call_node = next(
        node
        for node in bundle.ir.nodes.values()
        if isinstance(node, CallBoundaryNode)
    )
    imported = bundle.imports[call_node.call_alias]
    surface_contract = imported.surface.outputs["__result__"]
    executable_contract = imported.ir.outputs["__result__"]
    string_definition = MappingProxyType(
        {
            **dict(surface_contract.definition),
            "type": "string",
        }
    )
    imported = replace(
        imported,
        surface=replace(
            imported.surface,
            outputs=MappingProxyType(
                {
                    "__result__": replace(
                        surface_contract,
                        value_type="string",
                        definition=string_definition,
                    )
                }
            ),
        ),
        ir=replace(
            imported.ir,
            outputs=MappingProxyType(
                {
                    "__result__": replace(
                        executable_contract,
                        value_type="string",
                        definition=string_definition,
                    )
                }
            ),
        ),
    )
    bundle = replace(
        bundle,
        imports=MappingProxyType(
            {**dict(bundle.imports), call_node.call_alias: imported}
        ),
    )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(bundle)

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_concrete_call_result_is_admissible_to_json_consumer(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    derived_id = _node_id_ending(bundle, "__derived")
    bundle = _replace_payload_binding_type(
        bundle,
        node_id=derived_id,
        binding_name="called",
        descriptor={"kind": "primitive", "name": "Json"},
    )

    index = derive_pure_result_replay_index(bundle)

    assert derived_id in index.nodes


def _replace_imported_scalar_output_with_value_contract(bundle: Any):
    call_node = next(
        node
        for node in bundle.ir.nodes.values()
        if isinstance(node, CallBoundaryNode)
    )
    imported = bundle.imports[call_node.call_alias]
    surface_contract = imported.surface.outputs["__result__"]
    executable_contract = imported.ir.outputs["__result__"]
    value_definition = MappingProxyType(
        {
            **dict(surface_contract.definition),
            "kind": "value",
            "type": "value",
        }
    )
    imported = replace(
        imported,
        surface=replace(
            imported.surface,
            outputs=MappingProxyType(
                {
                    "__result__": replace(
                        surface_contract,
                        kind="value",
                        value_type="value",
                        definition=value_definition,
                    )
                }
            ),
        ),
        ir=replace(
            imported.ir,
            outputs=MappingProxyType(
                {
                    "__result__": replace(
                        executable_contract,
                        kind="value",
                        value_type="value",
                        definition=value_definition,
                    )
                }
            ),
        ),
    )
    bundle = replace(
        bundle,
        imports=MappingProxyType(
            {**dict(bundle.imports), call_node.call_alias: imported}
        ),
    )
    return bundle


def test_pure_replay_concrete_call_result_is_not_admissible_to_value_consumer(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    derived_id = _node_id_ending(bundle, "__derived")
    bundle = _replace_payload_binding_type(
        bundle,
        node_id=derived_id,
        binding_name="called",
        descriptor={"kind": "primitive", "name": "Value"},
    )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(bundle)

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_value_call_result_is_admissible_to_value_consumer(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    derived_id = _node_id_ending(bundle, "__derived")
    bundle = _replace_imported_scalar_output_with_value_contract(bundle)
    bundle = _replace_payload_binding_type(
        bundle,
        node_id=derived_id,
        binding_name="called",
        descriptor={"kind": "primitive", "name": "Value"},
    )

    index = derive_pure_result_replay_index(bundle)

    assert derived_id in index.nodes


def test_pure_replay_value_call_result_is_not_admissible_to_concrete_consumer(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    bundle = _replace_imported_scalar_output_with_value_contract(bundle)

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(bundle)

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_imported_scalar_call_rejects_wrong_durable_value_type(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_scalar_replay_fixture(tmp_path)
    call_id = next(
        node_id
        for node_id, node in bundle.ir.nodes.items()
        if isinstance(node, CallBoundaryNode)
    )
    derived_id = _node_id_ending(bundle, "__derived")
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=bundle,
        scope_path=ResumeScopePath.root(
            str(tmp_path / "pure_replay_imported_scalar_consumer.orc")
        ),
    )
    witness = runtime.witness(derived_id)
    state = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            bundle.projection.presentation_key_by_node_id[call_id]: {
                "status": "completed",
                "exit_code": 0,
                "artifacts": {"__result__": "true"},
            },
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            ),
        },
        "bound_inputs": {"value": True},
    }

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        runtime.replay_node(
            derived_id,
            state=state,
            evaluate_node=lambda _node_id, _state: pytest.fail(
                "wrong durable type must reject before pure evaluation"
            ),
        )

    assert excinfo.value.reason == pure_result_replay.DURABLE_INPUT_INVALID


def test_pure_replay_imported_record_call_uses_exact_flattened_contracts(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_record_replay_fixture(tmp_path)
    call_id, call_node = next(
        (node_id, node)
        for node_id, node in bundle.ir.nodes.items()
        if isinstance(node, CallBoundaryNode)
    )
    derived_id = _node_id_ending(bundle, "__derived")
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=bundle,
        scope_path=ResumeScopePath.root(
            str(tmp_path / "pure_replay_imported_record_consumer.orc")
        ),
    )
    witness = runtime.witness(derived_id)
    call_name = bundle.projection.presentation_key_by_node_id[call_id]
    artifacts = {
        "return__flag": True,
        "return__count": 7,
        "return__weights": [1.5, 2.5],
    }
    state = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            call_name: {
                "status": "completed",
                "exit_code": 0,
                "artifacts": artifacts,
            },
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            ),
        },
        "bound_inputs": {
            "value": {
                "flag": True,
                "count": 7,
                "weights": [1.5, 2.5],
            }
        },
    }
    evaluated: list[str] = []

    def evaluate(
        node_id: str,
        active_state: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        called = active_state["steps"][call_name]["artifacts"]
        assert called == artifacts
        evaluated.append(node_id)
        return {
            "name": witness.presentation_key,
            "step_id": witness.step_id,
            "visit_count": 1,
            "status": "completed",
            "exit_code": 0,
            "artifacts": {"__result__": called["return__flag"]},
        }

    assert call_node.available_outputs == (
        "return__flag",
        "return__count",
        "return__weights",
    )
    assert runtime.index.nodes[derived_id].durable_dependency_node_ids == (
        call_id,
    )
    runtime.replay_node(
        derived_id,
        state=state,
        evaluate_node=evaluate,
    )

    assert evaluated == [derived_id]
    assert runtime.value_for_state_address(
        NodeResultAddress(derived_id, "artifacts", "__result__"),
        state,
    ) is True


def test_pure_replay_imported_record_call_catalog_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_record_replay_fixture(tmp_path)
    call_id, call_node = next(
        (node_id, node)
        for node_id, node in bundle.ir.nodes.items()
        if isinstance(node, CallBoundaryNode)
    )
    bundle = replace(
        bundle,
        ir=replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    **dict(bundle.ir.nodes),
                    call_id: replace(
                        call_node,
                        available_outputs=("return__flag",),
                    ),
                }
            ),
        ),
    )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(bundle)

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID
    assert excinfo.value.context["member"] == "return__flag"


def test_pure_replay_imported_record_call_rejects_coercible_durable_member(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_record_replay_fixture(tmp_path)
    call_id = next(
        node_id
        for node_id, node in bundle.ir.nodes.items()
        if isinstance(node, CallBoundaryNode)
    )
    derived_id = _node_id_ending(bundle, "__derived")
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=bundle,
        scope_path=ResumeScopePath.root(
            str(tmp_path / "pure_replay_imported_record_consumer.orc")
        ),
    )
    witness = runtime.witness(derived_id)
    state = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            bundle.projection.presentation_key_by_node_id[call_id]: {
                "status": "completed",
                "exit_code": 0,
                "artifacts": {
                    "return__flag": True,
                    "return__count": "7",
                    "return__weights": [1.5],
                },
            },
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            ),
        },
        "bound_inputs": {
            "value": {"flag": True, "count": 7, "weights": [1.5]}
        },
    }

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        runtime.replay_node(
            derived_id,
            state=state,
            evaluate_node=lambda _node_id, _state: pytest.fail(
                "coercible record member must reject before pure evaluation"
            ),
        )

    assert excinfo.value.reason == pure_result_replay.DURABLE_INPUT_INVALID


def test_pure_replay_imported_record_call_rejects_nested_numeric_coercion(
    tmp_path: Path,
) -> None:
    bundle = _compile_imported_record_replay_fixture(tmp_path)
    call_id = next(
        node_id
        for node_id, node in bundle.ir.nodes.items()
        if isinstance(node, CallBoundaryNode)
    )
    derived_id = _node_id_ending(bundle, "__derived")
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=bundle,
        scope_path=ResumeScopePath.root(
            str(tmp_path / "pure_replay_imported_record_consumer.orc")
        ),
    )
    witness = runtime.witness(derived_id)
    state = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            bundle.projection.presentation_key_by_node_id[call_id]: {
                "status": "completed",
                "exit_code": 0,
                "artifacts": {
                    "return__flag": True,
                    "return__count": 7,
                    "return__weights": [1],
                },
            },
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            ),
        },
        "bound_inputs": {
            "value": {"flag": True, "count": 7, "weights": [1.0]}
        },
    }

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        runtime.replay_node(
            derived_id,
            state=state,
            evaluate_node=lambda _node_id, _state: pytest.fail(
                "nested numeric coercion must reject before pure evaluation"
            ),
        )

    assert excinfo.value.reason == pure_result_replay.DURABLE_INPUT_INVALID


def _replace_output_contracts(
    bundle: Any,
    *,
    node_id: str,
    output_contracts: Mapping[str, Any],
):
    node = bundle.ir.nodes[node_id]
    config = node.execution_config
    assert config is not None
    pure_projection = {
        **dict(config.pure_projection),
        "output_contracts": output_contracts,
    }
    replacement = replace(
        node,
        execution_config=replace(
            config,
            pure_projection=MappingProxyType(pure_projection),
        ),
    )
    return replace(
        bundle.ir,
        nodes=MappingProxyType(
            {
                **dict(bundle.ir.nodes),
                node_id: replacement,
            }
        ),
    )


def _replace_checkpoint_value_document(
    bundle: Any,
    *,
    node_id: str,
    source_step_name: str,
    value_document: Any,
):
    replaced = False
    points = []
    for point in bundle.runtime_plan.lexical_checkpoint_points:
        if point.node_id != node_id:
            points.append(point)
            continue
        details = dict(point.details)
        restore = dict(details.get("restore", {}))
        descriptors = []
        for descriptor_value in restore.get("binding_descriptors", ()):
            descriptor = dict(descriptor_value)
            if not replaced:
                descriptor["source_step_name"] = source_step_name
                descriptor["value_document"] = value_document
                replaced = True
            descriptors.append(descriptor)
        restore["binding_descriptors"] = descriptors
        details["restore"] = restore
        points.append(replace(point, details=details))
    assert replaced
    return replace(
        bundle,
        runtime_plan=replace(
            bundle.runtime_plan,
            lexical_checkpoint_points=tuple(points),
        ),
    )


def test_pure_replay_dependency_index_keeps_serialized_plan_unchanged(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    before = _canonical_program_digest(bundle)

    index = derive_pure_result_replay_index(bundle)

    after = _canonical_program_digest(bundle)
    a_id = _node_id_ending(bundle, "__a")
    e1_id = _node_id_ending(bundle, "__e1__count_e1")
    b_id = _node_id_ending(bundle, "__b")
    a_bindings = {
        binding.path: binding.address for binding in index.nodes[a_id].bindings
    }
    b_bindings = {
        binding.path: binding.address for binding in index.nodes[b_id].bindings
    }

    assert before == after
    assert a_bindings == {
        ("enabled",): WorkflowInputAddress("enabled"),
        ("seed",): WorkflowInputAddress("seed"),
    }
    assert b_bindings == {
        ("a", "value"): NodeResultAddress(
            node_id=a_id,
            field="artifacts",
            member="return__value",
        ),
        ("e1", "delta"): NodeResultAddress(
            node_id=e1_id,
            field="artifacts",
            member="delta",
        ),
        ("e1", "use-effect"): NodeResultAddress(
            node_id=e1_id,
            field="artifacts",
            member="use-effect",
        ),
    }
    assert index.nodes[b_id].pure_dependency_node_ids == (a_id,)
    assert index.nodes[b_id].durable_dependency_node_ids == (e1_id,)
    assert bundle.runtime_plan.nodes[b_id].dependency_node_ids == (e1_id,)
    assert (
        index.nodes[b_id].pure_dependency_node_ids
        != bundle.runtime_plan.nodes[b_id].dependency_node_ids
    )
    assert index.required_pure_node_ids(
        (
            NodeResultAddress(
                node_id=b_id,
                field="artifacts",
                member="return__seed-value",
            ),
        ),
        reached_node_ids=bundle.ir.body_region[:3],
    ) == (a_id, b_id)
    assert index.required_pure_node_ids(
        (
            NodeResultAddress(
                node_id=a_id,
                field="artifacts",
                member="return__value",
            ),
        ),
        reached_node_ids=(a_id,),
    ) == (a_id,)


@pytest.mark.parametrize(
    ("replacement", "reason"),
    (
        (
            {
                "a": {"value": {"ref": "inputs.missing"}},
                "e1": {
                    "delta": {
                        "ref": (
                            "root.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__e1__count-e1.artifacts.delta"
                        )
                    },
                    "use-effect": {
                        "ref": (
                            "root.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__e1__count-e1.artifacts.use-effect"
                        )
                    },
                },
            },
            "dependency_index_invalid",
        ),
        (
            {
                "a": {"value": {"note": "inputs.seed"}},
                "e1": {
                    "delta": {
                        "ref": (
                            "root.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__e1__count-e1.artifacts.delta"
                        )
                    },
                    "use-effect": {
                        "ref": (
                            "root.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__e1__count-e1.artifacts.use-effect"
                        )
                    },
                },
            },
            "dependency_index_invalid",
        ),
        (
            {
                "a": {
                    "value": {
                        "ref": (
                            "root.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__a.artifacts.return__value"
                        )
                    }
                },
                "e1": {
                    "delta": {
                        "ref": (
                            "root.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__e1__count-e1.artifacts.missing"
                        )
                    },
                    "use-effect": {
                        "ref": (
                            "root.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__e1__count-e1.artifacts.use-effect"
                        )
                    },
                },
            },
            "dependency_index_invalid",
        ),
        (
            {
                "a": {
                    "value": {
                        "ref": (
                            "self.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__a.artifacts.return__value"
                        )
                    }
                },
                "e1": {
                    "delta": {
                        "ref": (
                            "root.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__e1__count-e1.artifacts.delta"
                        )
                    },
                    "use-effect": {
                        "ref": (
                            "root.steps."
                            "pure_result_replay_effect_barrier::"
                            "orchestrate__e1__count-e1.artifacts.use-effect"
                        )
                    },
                },
            },
            "dependency_index_invalid",
        ),
    ),
)
def test_pure_replay_dependency_index_rejects_unbound_text_and_cross_frame_refs(
    tmp_path: Path,
    replacement: Mapping[str, Any],
    reason: str,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    b_id = _node_id_ending(bundle, "__b")
    tampered_ir = _replace_binding_refs(
        bundle,
        node_id=b_id,
        binding_refs=replacement,
    )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(replace(bundle, ir=tampered_ir))

    assert excinfo.value.code == "pure_result_replay_unavailable"
    assert excinfo.value.reason == reason


def test_pure_replay_dependency_index_accepts_typed_literal_bindings(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    b_id = _node_id_ending(bundle, "__b")
    a_node = bundle.ir.nodes[a_id]
    a_config = a_node.execution_config
    assert a_config is not None
    binding_refs = dict(a_config.pure_projection["binding_refs"])
    binding_refs["seed"] = 3
    literal_ir = _replace_binding_refs(
        bundle,
        node_id=a_id,
        binding_refs=binding_refs,
    )

    index = derive_pure_result_replay_index(replace(bundle, ir=literal_ir))

    assert a_id in index.nodes
    assert b_id in index.nodes
    assert {
        binding.path: binding.address
        for binding in index.nodes[a_id].bindings
    } == {
        ("enabled",): WorkflowInputAddress("enabled"),
    }
    assert index.required_pure_node_ids(
        (
            NodeResultAddress(
                node_id=a_id,
                field="artifacts",
                member="return__value",
            ),
        ),
        reached_node_ids=(a_id,),
    ) == (a_id,)


@pytest.mark.parametrize("invalid_seed", ("3", {"unexpected": 3}))
def test_pure_replay_dependency_index_rejects_wrong_typed_literal_bindings(
    tmp_path: Path,
    invalid_seed: Any,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    a_node = bundle.ir.nodes[a_id]
    a_config = a_node.execution_config
    assert a_config is not None
    binding_refs = dict(a_config.pure_projection["binding_refs"])
    binding_refs["seed"] = invalid_seed
    invalid_ir = _replace_binding_refs(
        bundle,
        node_id=a_id,
        binding_refs=binding_refs,
    )

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(replace(bundle, ir=invalid_ir))

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_typed_binding_walker_accepts_variant_case_discriminant_ref() -> None:
    refs = pure_result_replay._walk_typed_binding_ref_documents(
        {
            "revised": {
                "variant": {"ref": "root.steps.review.artifacts.return__variant"},
                "report": {"ref": "root.steps.review.artifacts.return__report"},
            }
        },
        payload_bindings={
            "revised": {
                "type": {
                    "kind": "variant_case",
                    "union_name": "ReviewDecision",
                    "variant": "REVISE",
                    "fields": [
                        {
                            "name": "report",
                            "type": {"kind": "primitive", "name": "String"},
                        }
                    ],
                }
            }
        },
    )

    assert refs == (
        (
            ("revised", "variant"),
            "root.steps.review.artifacts.return__variant",
        ),
        (
            ("revised", "report"),
            "root.steps.review.artifacts.return__report",
        ),
    )


@pytest.mark.parametrize(
    "active_value",
    (
        1,
        {"ref": "root.steps.left.artifacts.return__value"},
    ),
    ids=("literal-active-field", "ref-active-field"),
)
def test_pure_replay_typed_binding_walker_rejects_wrong_inactive_union_literal(
    active_value: Any,
) -> None:
    with pytest.raises(PureResultReplayIndexError) as excinfo:
        pure_result_replay._walk_typed_binding_ref_documents(
            {
                "decision": {
                    "variant": "LEFT",
                    "left": active_value,
                    "right": "not-an-int",
                }
            },
            payload_bindings={
                "decision": {
                    "type": {
                        "kind": "union",
                        "name": "Decision",
                        "variants": [
                            {
                                "name": "LEFT",
                                "fields": [
                                    {
                                        "name": "left",
                                        "type": {
                                            "kind": "primitive",
                                            "name": "Int",
                                        },
                                    }
                                ],
                            },
                            {
                                "name": "RIGHT",
                                "fields": [
                                    {
                                        "name": "right",
                                        "type": {
                                            "kind": "primitive",
                                            "name": "Int",
                                        },
                                    }
                                ],
                            },
                        ],
                    }
                }
            },
        )

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_typed_binding_walker_rejects_nested_wrong_inactive_union_literal() -> None:
    with pytest.raises(PureResultReplayIndexError) as excinfo:
        pure_result_replay._walk_typed_binding_ref_documents(
            {
                "envelope": {
                    "label": "decision",
                    "decision": {
                        "variant": "LEFT",
                        "left": 1,
                        "right": "not-an-int",
                    },
                }
            },
            payload_bindings={
                "envelope": {
                    "type": {
                        "kind": "record",
                        "name": "Envelope",
                        "fields": [
                            {
                                "name": "label",
                                "type": {
                                    "kind": "primitive",
                                    "name": "String",
                                },
                            },
                            {
                                "name": "decision",
                                "type": {
                                    "kind": "union",
                                    "name": "Decision",
                                    "variants": [
                                        {
                                            "name": "LEFT",
                                            "fields": [
                                                {
                                                    "name": "left",
                                                    "type": {
                                                        "kind": "primitive",
                                                        "name": "Int",
                                                    },
                                                }
                                            ],
                                        },
                                        {
                                            "name": "RIGHT",
                                            "fields": [
                                                {
                                                    "name": "right",
                                                    "type": {
                                                        "kind": "primitive",
                                                        "name": "Int",
                                                    },
                                                }
                                            ],
                                        },
                                    ],
                                },
                            },
                        ],
                    }
                }
            },
        )

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_typed_binding_walker_rejects_wrong_nested_union_in_inactive_field() -> None:
    inner_union = {
        "kind": "union",
        "name": "Inner",
        "variants": [
            {
                "name": "A",
                "fields": [
                    {
                        "name": "a",
                        "type": {"kind": "primitive", "name": "Int"},
                    }
                ],
            },
            {
                "name": "B",
                "fields": [
                    {
                        "name": "b",
                        "type": {"kind": "primitive", "name": "Int"},
                    }
                ],
            },
        ],
    }
    with pytest.raises(PureResultReplayIndexError) as excinfo:
        pure_result_replay._walk_typed_binding_ref_documents(
            {
                "outer": {
                    "variant": "LEFT",
                    "left": 1,
                    "payload": {
                        "variant": "A",
                        "a": 2,
                        "b": "not-an-int",
                    },
                }
            },
            payload_bindings={
                "outer": {
                    "type": {
                        "kind": "union",
                        "name": "Outer",
                        "variants": [
                            {
                                "name": "LEFT",
                                "fields": [
                                    {
                                        "name": "left",
                                        "type": {
                                            "kind": "primitive",
                                            "name": "Int",
                                        },
                                    }
                                ],
                            },
                            {
                                "name": "RIGHT",
                                "fields": [
                                    {
                                        "name": "payload",
                                        "type": inner_union,
                                    }
                                ],
                            },
                        ],
                    }
                }
            },
        )

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_typed_binding_walker_accepts_typed_inactive_union_literal() -> None:
    refs = pure_result_replay._walk_typed_binding_ref_documents(
        {
            "decision": {
                "variant": "LEFT",
                "left": 1,
                "right": 2,
            }
        },
        payload_bindings={
            "decision": {
                "type": {
                    "kind": "union",
                    "name": "Decision",
                    "variants": [
                        {
                            "name": "LEFT",
                            "fields": [
                                {
                                    "name": "left",
                                    "type": {
                                        "kind": "primitive",
                                        "name": "Int",
                                    },
                                }
                            ],
                        },
                        {
                            "name": "RIGHT",
                            "fields": [
                                {
                                    "name": "right",
                                    "type": {
                                        "kind": "primitive",
                                        "name": "Int",
                                    },
                                }
                            ],
                        },
                    ],
                }
            }
        },
    )

    assert refs == ()


def test_pure_replay_typed_binding_walker_validates_mixed_json_literals() -> None:
    payload_bindings = {
        "document": {
            "type": {
                "kind": "primitive",
                "name": "Json",
            }
        }
    }
    refs = pure_result_replay._walk_typed_binding_ref_documents(
        {
            "document": {
                "literal": {"enabled": True},
                "dependency": {"ref": "inputs.seed"},
            }
        },
        payload_bindings=payload_bindings,
    )

    assert refs == (
        (
            ("document", "dependency"),
            "inputs.seed",
        ),
    )
    for invalid_document in (
        {"literal": float("nan")},
        {
            "literal": float("nan"),
            "dependency": {"ref": "inputs.seed"},
        },
    ):
        with pytest.raises(PureResultReplayIndexError) as excinfo:
            pure_result_replay._walk_typed_binding_ref_documents(
                {"document": invalid_document},
                payload_bindings=payload_bindings,
            )
        assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID
    assert pure_result_replay._walk_typed_binding_ref_documents(
        {"document": {"": {"literal": 1}}},
        payload_bindings=payload_bindings,
    ) == ()


def _sparse_union_replay_bundle(bundle: Any, *, node_id: str):
    node = bundle.ir.nodes[node_id]
    config = node.execution_config
    assert config is not None
    scalar_contract = dict(
        next(iter(config.pure_projection["output_contracts"].values()))
    )
    projection_base = {
        "projection_class": "union_workflow_boundary",
        "return_kind": "union",
        "union_output_group": "return",
        "discriminant_output": "return__variant",
    }
    output_contracts = {
        "return__variant": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["LEFT", "RIGHT"],
            "projection": {
                **projection_base,
                "field_role": "discriminant",
                "active_variants": ["LEFT", "RIGHT"],
            },
        },
        "return__left": {
            **scalar_contract,
            "projection": {
                **projection_base,
                "field_role": "variant",
                "active_variants": ["LEFT"],
            },
        },
        "return__right": {
            **scalar_contract,
            "projection": {
                **projection_base,
                "field_role": "variant",
                "active_variants": ["RIGHT"],
            },
        },
    }
    return replace(
        bundle,
        ir=_replace_output_contracts(
            bundle,
            node_id=node_id,
            output_contracts=output_contracts,
        ),
    )


def test_pure_replay_sparse_union_result_uses_overlay_row_presence(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    union_bundle = _sparse_union_replay_bundle(bundle, node_id=a_id)
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=union_bundle,
        scope_path=ResumeScopePath.root(str(FIXTURE)),
    )
    witness = runtime.witness(a_id)
    state = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            )
        },
        "bound_inputs": {"seed": 3, "enabled": True},
    }
    result = {
        "name": witness.presentation_key,
        "step_id": witness.step_id,
        "visit_count": 1,
        "status": "completed",
        "exit_code": 0,
        "artifacts": {
            "return__variant": "LEFT",
            "return__left": 3,
        },
    }
    evaluations: list[str] = []

    runtime.replay_node(
        a_id,
        state=state,
        evaluate_node=lambda node_id, _state: (
            evaluations.append(node_id) or result
        ),
    )
    runtime.replay_node(
        a_id,
        state=state,
        evaluate_node=lambda _node_id, _state: (_ for _ in ()).throw(
            AssertionError("an existing sparse overlay row must not replay twice")
        ),
    )

    assert evaluations == [a_id]
    assert runtime.value_for_state_address(
        NodeResultAddress(a_id, "artifacts", "return__left"),
        state,
    ) == 3
    with pytest.raises(PureResultReplayIndexError) as inactive:
        runtime.value_for_state_address(
            NodeResultAddress(a_id, "artifacts", "return__right"),
            state,
        )
    assert inactive.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_sparse_union_cache_hit_accepts_exact_active_result(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=_sparse_union_replay_bundle(bundle, node_id=a_id),
        scope_path=ResumeScopePath.root(str(FIXTURE)),
    )
    witness = runtime.witness(a_id)
    state = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            )
        },
        "bound_inputs": {"seed": 3, "enabled": True},
    }
    result = {
        "name": witness.presentation_key,
        "step_id": witness.step_id,
        "visit_count": 1,
        "status": "completed",
        "exit_code": 0,
        "artifacts": {
            "return__variant": "LEFT",
            "return__left": 3,
        },
    }
    runtime.replay_node(
        a_id,
        state=state,
        evaluate_node=lambda _node_id, _state: result,
    )
    state["steps"][witness.presentation_key] = result
    state["current_step"] = {
        "name": "downstream",
        "index": witness.step_index + 1,
        "type": "command",
        "status": "running",
        "step_id": "downstream",
        "visit_count": 1,
        "started_at": "2026-07-30T00:00:00Z",
        "last_heartbeat_at": "2026-07-30T00:00:00Z",
    }

    runtime.replay_node(
        a_id,
        state=state,
        evaluate_node=lambda _node_id, _state: (_ for _ in ()).throw(
            AssertionError("an exact active result must use the retained cache")
        ),
    )


def test_pure_replay_sparse_union_cache_hit_rejects_relevant_running_cursor(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=_sparse_union_replay_bundle(bundle, node_id=a_id),
        scope_path=ResumeScopePath.root(str(FIXTURE)),
    )
    witness = runtime.witness(a_id)
    state = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            )
        },
        "bound_inputs": {"seed": 3, "enabled": True},
    }
    result = {
        "name": witness.presentation_key,
        "step_id": witness.step_id,
        "visit_count": 1,
        "status": "completed",
        "exit_code": 0,
        "artifacts": {
            "return__variant": "LEFT",
            "return__left": 3,
        },
    }
    runtime.replay_node(
        a_id,
        state=state,
        evaluate_node=lambda _node_id, _state: result,
    )
    state["steps"][witness.presentation_key] = result
    state["current_step"] = {
        "name": witness.presentation_key,
        "index": witness.step_index,
        "type": "pure_projection",
        "status": "running",
        "step_id": witness.step_id,
        "visit_count": witness.visit_count,
        "started_at": "2026-07-30T00:00:00Z",
        "last_heartbeat_at": "2026-07-30T00:00:00Z",
    }

    assert (
        pure_result_replay.classify_pure_replay_progress(
            state,
            witness=witness,
        )
        == "progress_witness_invalid"
    )
    with pytest.raises(PureResultReplayIndexError) as excinfo:
        runtime.replay_node(
            a_id,
            state=state,
            evaluate_node=lambda _node_id, _state: (_ for _ in ()).throw(
                AssertionError("a relevant running cursor must invalidate cache")
            ),
        )

    assert excinfo.value.reason == "progress_witness_invalid"


@pytest.mark.parametrize(
    "invalid_state_kind",
    (
        "missing-visits",
        "non-one-visit",
        "missing-shell",
        "malformed-shell",
    ),
)
def test_pure_replay_sparse_union_cache_hit_revalidates_durable_witness(
    tmp_path: Path,
    invalid_state_kind: str,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=_sparse_union_replay_bundle(bundle, node_id=a_id),
        scope_path=ResumeScopePath.root(str(FIXTURE)),
    )
    witness = runtime.witness(a_id)
    state: dict[str, Any] = {
        "step_visits": {witness.presentation_key: 1},
        "steps": {
            witness.presentation_key: (
                pure_result_replay.build_pure_completion_shell(witness)
            )
        },
        "bound_inputs": {"seed": 3, "enabled": True},
    }
    result = {
        "name": witness.presentation_key,
        "step_id": witness.step_id,
        "visit_count": 1,
        "status": "completed",
        "exit_code": 0,
        "artifacts": {
            "return__variant": "LEFT",
            "return__left": 3,
        },
    }
    runtime.replay_node(
        a_id,
        state=state,
        evaluate_node=lambda _node_id, _state: result,
    )

    if invalid_state_kind == "missing-visits":
        state["step_visits"] = {}
    elif invalid_state_kind == "non-one-visit":
        state["step_visits"] = {witness.presentation_key: 2}
    elif invalid_state_kind == "missing-shell":
        state["steps"] = {}
    else:
        state["steps"] = {
            witness.presentation_key: {
                **pure_result_replay.build_pure_completion_shell(witness),
                "status": "running",
            }
        }

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        runtime.replay_node(
            a_id,
            state=state,
            evaluate_node=lambda _node_id, _state: (_ for _ in ()).throw(
                AssertionError("an invalid durable witness must not use cache")
            ),
        )

    assert excinfo.value.reason == "progress_witness_invalid"


@pytest.mark.parametrize(
    "artifacts",
    (
        pytest.param(
            {"return__variant": "LEFT"},
            id="missing-active-variant-member",
        ),
        pytest.param(
            {
                "return__variant": "LEFT",
                "return__left": 3,
                "return__right": 4,
            },
            id="extra-inactive-variant-member",
        ),
    ),
)
def test_pure_replay_sparse_union_result_rejects_wrong_active_member_set(
    tmp_path: Path,
    artifacts: Mapping[str, Any],
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=_sparse_union_replay_bundle(bundle, node_id=a_id),
        scope_path=ResumeScopePath.root(str(FIXTURE)),
    )
    witness = runtime.witness(a_id)

    with pytest.raises(PureResultReplayIndexError) as excinfo:
        runtime.record_full_result(
            a_id,
            witness=witness,
            result={
                "name": witness.presentation_key,
                "step_id": witness.step_id,
                "visit_count": 1,
                "status": "completed",
                "exit_code": 0,
                "artifacts": dict(artifacts),
            },
        )

    assert excinfo.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_value_document_ref_walker_ignores_typed_literals() -> None:
    document = {
        "__compiler_metadata__": "state/provider/result.json",
        "payload": [
            1,
            True,
            None,
            {"source": {"ref": "inputs.seed"}},
        ],
    }

    assert pure_result_replay._walk_value_document_refs(document) == (
        (("payload", 3, "source"), "inputs.seed"),
    )
    assert pure_result_replay._walk_value_document_refs(
        ["compiler-metadata", {"ref": "inputs.seed"}]
    ) == (((1,), "inputs.seed"),)
    assert pure_result_replay._walk_value_document_refs(
        {"": {"ref": "inputs.seed"}}
    ) == ((("",), "inputs.seed"),)

    with pytest.raises(PureResultReplayIndexError) as malformed:
        pure_result_replay._walk_value_document_refs(
            [{"source": {"ref": "inputs.seed", "extra": True}}]
        )
    assert malformed.value.reason == DEPENDENCY_INDEX_INVALID

    with pytest.raises(PureResultReplayIndexError) as noncanonical:
        pure_result_replay._walk_value_document_refs(
            [{"literal": float("inf")}, {"ref": "inputs.seed"}]
        )
    assert noncanonical.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_boundary_indexes_list_root_value_documents(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    e1_id = _node_id_ending(bundle, "__e1__count_e1")
    a_name = bundle.projection.entries_by_node_id[a_id].presentation_key
    a_member = "return__value"
    a_ref = f"root.steps.{a_name}.artifacts.{a_member}"
    list_bundle = _replace_checkpoint_value_document(
        bundle,
        node_id=e1_id,
        source_step_name="compiler-metadata-only",
        value_document=["compiler-metadata", {"ref": a_ref}],
    )
    runtime = pure_result_replay.PureReplayRuntime(
        bundle=list_bundle,
        scope_path=ResumeScopePath.root(str(FIXTURE)),
    )
    witness = runtime.witness(a_id)
    state = {
        "step_visits": {a_name: 1},
        "steps": {
            a_name: pure_result_replay.build_pure_completion_shell(witness)
        },
        "bound_inputs": {"seed": 3, "enabled": True},
    }

    assert runtime.required_node_ids_for_boundary(
        e1_id,
        state=state,
    ) == (a_id,)

    malformed_bundle = _replace_checkpoint_value_document(
        bundle,
        node_id=e1_id,
        source_step_name="compiler-metadata-only",
        value_document=[
            {"ref": a_ref, "unexpected": "not-a-ref-document"}
        ],
    )
    malformed_runtime = pure_result_replay.PureReplayRuntime(
        bundle=malformed_bundle,
        scope_path=ResumeScopePath.root(str(FIXTURE)),
    )
    with pytest.raises(PureResultReplayIndexError) as malformed:
        malformed_runtime.required_node_ids_for_boundary(
            e1_id,
            state=state,
        )
    assert malformed.value.reason == DEPENDENCY_INDEX_INVALID


def test_pure_replay_dependency_index_rejects_cycle_and_multiple_visit_region(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    b_id = _node_id_ending(bundle, "__b")
    a_cycle_ir = _replace_binding_refs(
        bundle,
        node_id=a_id,
        binding_refs={
            "enabled": {"ref": "inputs.enabled"},
            "seed": {
                "ref": (
                    "root.steps."
                    "pure_result_replay_effect_barrier::"
                    "orchestrate__b.artifacts.return__seed-value"
                )
            },
        },
    )

    with pytest.raises(PureResultReplayIndexError) as cycle:
        derive_pure_result_replay_index(replace(bundle, ir=a_cycle_ir))
    assert cycle.value.reason == "dependency_index_invalid"

    a_node = bundle.ir.nodes[a_id]
    a_config = a_node.execution_config
    assert a_config is not None
    multiple_ir = replace(
        bundle.ir,
        nodes=MappingProxyType(
            {
                **dict(bundle.ir.nodes),
                a_id: replace(
                    a_node,
                    execution_config=replace(
                        a_config,
                        common=replace(a_config.common, max_visits=2),
                    ),
                ),
            }
        ),
    )
    multiple_index = derive_pure_result_replay_index(
        replace(bundle, ir=multiple_ir),
    )
    assert a_id not in multiple_index.nodes
    assert multiple_index.ineligible_pure_reasons[a_id] == (
        "multiple_visit_region"
    )
    with pytest.raises(PureResultReplayIndexError) as multiple:
        multiple_index.required_pure_node_ids(
            (
                NodeResultAddress(
                    node_id=a_id,
                    field="artifacts",
                    member="return__value",
                ),
            ),
            reached_node_ids=(a_id,),
        )
    assert multiple.value.reason == "multiple_visit_region"

    with pytest.raises(PureResultReplayIndexError) as inactive:
        derive_pure_result_replay_index(bundle).required_pure_node_ids(
            (
                NodeResultAddress(
                    node_id=b_id,
                    field="artifacts",
                    member="return__seed-value",
                ),
            ),
            reached_node_ids=(a_id,),
        )
    assert inactive.value.reason == "reachability_ambiguous"


def test_pure_replay_dependency_index_rejects_projection_identity_mismatch(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    e2_id = _node_id_ending(bundle, "__e2__finish_e2")
    duplicate_key = bundle.runtime_plan.nodes[a_id].presentation_key
    duplicate_ir = replace(
        bundle.ir,
        nodes=MappingProxyType(
            {
                **dict(bundle.ir.nodes),
                e2_id: replace(
                    bundle.ir.nodes[e2_id],
                    presentation_name=duplicate_key,
                ),
            }
        ),
    )
    duplicate_plan = replace(
        bundle.runtime_plan,
        nodes=MappingProxyType(
            {
                **dict(bundle.runtime_plan.nodes),
                e2_id: replace(
                    bundle.runtime_plan.nodes[e2_id],
                    presentation_key=duplicate_key,
                ),
            }
        ),
    )

    with pytest.raises(PureResultReplayIndexError) as mismatch:
        derive_pure_result_replay_index(
            replace(
                bundle,
                ir=duplicate_ir,
                runtime_plan=duplicate_plan,
            )
        )

    assert mismatch.value.reason == "dependency_index_invalid"


def test_pure_replay_dependency_index_rejects_duplicate_projection_authority(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)
    a_id = _node_id_ending(bundle, "__a")
    e2_id = _node_id_ending(bundle, "__e2__finish_e2")
    duplicate_key = bundle.projection.entries_by_node_id[
        a_id
    ].presentation_key
    duplicate_ir = replace(
        bundle.ir,
        nodes=MappingProxyType(
            {
                **dict(bundle.ir.nodes),
                e2_id: replace(
                    bundle.ir.nodes[e2_id],
                    presentation_name=duplicate_key,
                ),
            }
        ),
    )
    duplicate_plan = replace(
        bundle.runtime_plan,
        nodes=MappingProxyType(
            {
                **dict(bundle.runtime_plan.nodes),
                e2_id: replace(
                    bundle.runtime_plan.nodes[e2_id],
                    presentation_key=duplicate_key,
                ),
            }
        ),
    )
    duplicate_projection = replace(
        bundle.projection,
        entries_by_node_id=MappingProxyType(
            {
                **dict(bundle.projection.entries_by_node_id),
                e2_id: replace(
                    bundle.projection.entries_by_node_id[e2_id],
                    presentation_key=duplicate_key,
                ),
            }
        ),
        presentation_key_by_node_id=MappingProxyType(
            {
                **dict(bundle.projection.presentation_key_by_node_id),
                e2_id: duplicate_key,
            }
        ),
    )

    with pytest.raises(PureResultReplayIndexError) as duplicate:
        derive_pure_result_replay_index(
            replace(
                bundle,
                ir=duplicate_ir,
                runtime_plan=duplicate_plan,
                projection=duplicate_projection,
            )
        )

    assert duplicate.value.reason == "dependency_index_invalid"


def test_pure_replay_dependency_index_propagates_reasons_deterministically(
) -> None:
    eligible, reasons = _propagate_pure_ineligibility(
        eligible_node_ids={"consumer", "transitive"},
        pure_node_ids=frozenset(
            {"invalid", "multiple", "transitive", "consumer"}
        ),
        dependency_addresses={
            "transitive": (
                NodeResultAddress("invalid", "artifacts", "value"),
            ),
            "consumer": (
                NodeResultAddress("transitive", "artifacts", "value"),
                NodeResultAddress("multiple", "artifacts", "value"),
            ),
        },
        ineligible_reasons={
            "invalid": DEPENDENCY_INDEX_INVALID,
            "multiple": MULTIPLE_VISIT_REGION,
        },
        program_node_ids=(
            "invalid",
            "multiple",
            "transitive",
            "consumer",
        ),
    )

    assert eligible == set()
    assert reasons == {
        "invalid": DEPENDENCY_INDEX_INVALID,
        "multiple": MULTIPLE_VISIT_REGION,
        "transitive": DEPENDENCY_INDEX_INVALID,
        "consumer": MULTIPLE_VISIT_REGION,
    }


_PURE_PRESENTATION_KEY = "DerivedProjection"
_PURE_STEP_INDEX = 3
_PURE_STEP_ID = "root.derived_projection"
_PURE_VISIT_COUNT = 1


def _pure_replay_witness():
    return pure_result_replay.PureReplayVisitWitness(
        presentation_key=_PURE_PRESENTATION_KEY,
        step_index=_PURE_STEP_INDEX,
        step_id=_PURE_STEP_ID,
        visit_count=_PURE_VISIT_COUNT,
    )


def _exact_pure_completion_shell(
    *,
    step_id: str = _PURE_STEP_ID,
    visit_count: int = _PURE_VISIT_COUNT,
) -> dict[str, Any]:
    return {
        "name": _PURE_PRESENTATION_KEY,
        "step_id": step_id,
        "visit_count": visit_count,
        "status": "completed",
        "exit_code": 0,
        "outcome": {
            "status": "completed",
            "phase": "execution",
            "class": "completed",
            "retryable": False,
        },
        "result_storage": "derived_pure_replay.v1",
    }


def _pure_running_cursor(
    *,
    presentation_key: str = _PURE_PRESENTATION_KEY,
    step_index: int = _PURE_STEP_INDEX,
    step_type: str = "pure_projection",
    step_id: str = _PURE_STEP_ID,
    visit_count: int = _PURE_VISIT_COUNT,
    status: str = "running",
) -> dict[str, Any]:
    return {
        "name": presentation_key,
        "index": step_index,
        "type": step_type,
        "step_id": step_id,
        "visit_count": visit_count,
        "status": status,
        "started_at": "2026-07-30T12:00:00+00:00",
        "last_heartbeat_at": "2026-07-30T12:00:00+00:00",
    }


def _unrelated_running_cursor() -> dict[str, Any]:
    return _pure_running_cursor(
        presentation_key="EffectBoundary",
        step_index=_PURE_STEP_INDEX + 1,
        step_type="command",
        step_id="root.effect_boundary",
        visit_count=1,
    )


def _pure_failed_row(
    *,
    presentation_key: str = _PURE_PRESENTATION_KEY,
    step_id: str = _PURE_STEP_ID,
    visit_count: int = _PURE_VISIT_COUNT,
) -> dict[str, Any]:
    return {
        "name": presentation_key,
        "step_id": step_id,
        "visit_count": visit_count,
        "status": "failed",
        "exit_code": 2,
        "error": {
            "type": "pure_projection_failed",
            "message": "Pure projection failed",
        },
        "outcome": {
            "status": "failed",
            "phase": "execution",
            "class": "pre_execution_failed",
            "retryable": False,
        },
    }


def _pure_skipped_row(
    *,
    presentation_key: str = _PURE_PRESENTATION_KEY,
    step_id: str = _PURE_STEP_ID,
    visit_count: int = _PURE_VISIT_COUNT,
) -> dict[str, Any]:
    return {
        "name": presentation_key,
        "step_id": step_id,
        "visit_count": visit_count,
        "status": "skipped",
        "exit_code": 0,
        "skipped": True,
        "outcome": {
            "status": "skipped",
            "phase": "pre_execution",
            "class": "skipped",
            "retryable": False,
        },
    }


def _pure_progress_state(
    *,
    visit_count: int | None,
    current_step: Mapping[str, Any] | None,
    result_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "step_visits": (
            {}
            if visit_count is None
            else {_PURE_PRESENTATION_KEY: visit_count}
        ),
        "current_step": (
            None if current_step is None else dict(current_step)
        ),
        "steps": (
            {}
            if result_row is None
            else {_PURE_PRESENTATION_KEY: dict(result_row)}
        ),
    }


def test_pure_completion_shell_has_exact_shape_without_step_result_serialization(
) -> None:
    witness = _pure_replay_witness()

    with patch.object(
        StepResult,
        "to_dict",
        side_effect=AssertionError(
            "pure completion shells must not use StepResult.to_dict()"
        ),
    ):
        shell = pure_result_replay.build_pure_completion_shell(witness)

    assert shell == _exact_pure_completion_shell()
    pure_result_replay.validate_pure_completion_shell(
        shell,
        witness=witness,
    )


@pytest.mark.parametrize(
    "forbidden_extra",
    (
        pytest.param({"value": 17}, id="value"),
        pytest.param({"output": "17"}, id="output"),
        pytest.param({"text": "17"}, id="text"),
        pytest.param({"json": 17}, id="json"),
        pytest.param(
            {"artifacts": {"return__value": 17}},
            id="artifacts",
        ),
        pytest.param(
            {"debug": {"pure_projection": {"reused_bundle": False}}},
            id="debug",
        ),
        pytest.param({"duration_ms": 0}, id="duration"),
        pytest.param(
            {"output_bundle": {"path": "state/private-result.json"}},
            id="bundle-reference",
        ),
    ),
)
def test_pure_completion_shell_rejects_forbidden_extra_field(
    forbidden_extra: dict[str, Any],
) -> None:
    row = {
        **_exact_pure_completion_shell(),
        **forbidden_extra,
    }

    with pytest.raises(ValueError):
        pure_result_replay.validate_pure_completion_shell(
            row,
            witness=_pure_replay_witness(),
        )


@pytest.mark.parametrize(
    "missing_key",
    tuple(_exact_pure_completion_shell()),
)
def test_pure_completion_shell_rejects_missing_required_field(
    missing_key: str,
) -> None:
    row = _exact_pure_completion_shell()
    row.pop(missing_key)

    with pytest.raises(ValueError):
        pure_result_replay.validate_pure_completion_shell(
            row,
            witness=_pure_replay_witness(),
        )


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    (
        pytest.param("name", "OtherProjection", id="name"),
        pytest.param("step_id", "root.other_projection", id="step-id"),
        pytest.param("visit_count", 2, id="visit-count"),
        pytest.param("visit_count", True, id="visit-count-bool"),
        pytest.param("status", "failed", id="status"),
        pytest.param("exit_code", 1, id="exit-code"),
        pytest.param("exit_code", False, id="exit-code-bool"),
        pytest.param(
            "result_storage",
            "bundle_backed.v1",
            id="result-storage",
        ),
    ),
)
def test_pure_completion_shell_rejects_wrong_required_field(
    field: str,
    wrong_value: Any,
) -> None:
    row = {
        **_exact_pure_completion_shell(),
        field: wrong_value,
    }

    with pytest.raises(ValueError):
        pure_result_replay.validate_pure_completion_shell(
            row,
            witness=_pure_replay_witness(),
        )


@pytest.mark.parametrize(
    "outcome",
    (
        pytest.param(
            {
                "status": "completed",
                "phase": "execution",
                "class": "completed",
            },
            id="missing-field",
        ),
        pytest.param(
            {
                "status": "completed",
                "phase": "execution",
                "class": "completed",
                "retryable": False,
                "extra": "not-authority",
            },
            id="extra-field",
        ),
        pytest.param(
            {
                "status": "failed",
                "phase": "execution",
                "class": "completed",
                "retryable": False,
            },
            id="wrong-status",
        ),
        pytest.param(
            {
                "status": "completed",
                "phase": "pre_execution",
                "class": "completed",
                "retryable": False,
            },
            id="wrong-phase",
        ),
        pytest.param(
            {
                "status": "completed",
                "phase": "execution",
                "class": "pre_execution_failed",
                "retryable": False,
            },
            id="wrong-class",
        ),
        pytest.param(
            {
                "status": "completed",
                "phase": "execution",
                "class": "completed",
                "retryable": True,
            },
            id="wrong-retryable",
        ),
    ),
)
def test_pure_completion_shell_rejects_non_exact_outcome(
    outcome: dict[str, Any],
) -> None:
    row = {
        **_exact_pure_completion_shell(),
        "outcome": outcome,
    }

    with pytest.raises(ValueError):
        pure_result_replay.validate_pure_completion_shell(
            row,
            witness=_pure_replay_witness(),
        )


@pytest.mark.parametrize(
    ("state", "expected_classification"),
    (
        pytest.param(
            _pure_progress_state(
                visit_count=None,
                current_step=None,
                result_row=None,
            ),
            "unstarted",
            id="unstarted",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=None,
                current_step=_unrelated_running_cursor(),
                result_row=None,
            ),
            "unstarted",
            id="unstarted-while-unrelated-step-is-current",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_pure_running_cursor(),
                result_row=None,
            ),
            "interrupted",
            id="interrupted",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row=_exact_pure_completion_shell(),
            ),
            "derived_complete",
            id="derived-complete",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_unrelated_running_cursor(),
                result_row=_exact_pure_completion_shell(),
            ),
            "derived_complete",
            id="derived-complete-while-unrelated-step-is-current",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row=_pure_failed_row(),
            ),
            "durable_failure_skip",
            id="durable-failure",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row=_pure_skipped_row(),
            ),
            "durable_failure_skip",
            id="durable-skip",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row=None,
            ),
            "progress_witness_invalid",
            id="visit-without-witness",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=None,
                current_step=_pure_running_cursor(),
                result_row=None,
            ),
            "progress_witness_invalid",
            id="cursor-without-visit",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=None,
                current_step=None,
                result_row=_exact_pure_completion_shell(),
            ),
            "progress_witness_invalid",
            id="shell-without-visit",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_pure_running_cursor(),
                result_row=_exact_pure_completion_shell(),
            ),
            "progress_witness_invalid",
            id="cursor-and-row",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_pure_running_cursor(visit_count=2),
                result_row=None,
            ),
            "progress_witness_invalid",
            id="cursor-visit-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_pure_running_cursor(
                    step_id="root.other_projection"
                ),
                result_row=None,
            ),
            "progress_witness_invalid",
            id="cursor-identity-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_pure_running_cursor(
                    presentation_key="AliasedProjection"
                ),
                result_row=None,
            ),
            "progress_witness_invalid",
            id="cursor-presentation-key-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_pure_running_cursor(
                    step_index=_PURE_STEP_INDEX + 1
                ),
                result_row=None,
            ),
            "progress_witness_invalid",
            id="cursor-index-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_pure_running_cursor(step_type="command"),
                result_row=None,
            ),
            "progress_witness_invalid",
            id="cursor-kind-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_pure_running_cursor(status="completed"),
                result_row=None,
            ),
            "progress_witness_invalid",
            id="cursor-status-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row=_exact_pure_completion_shell(
                    visit_count=2
                ),
            ),
            "progress_witness_invalid",
            id="row-visit-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row=_exact_pure_completion_shell(
                    step_id="root.other_projection"
                ),
            ),
            "progress_witness_invalid",
            id="row-identity-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row={
                    **_exact_pure_completion_shell(),
                    "name": "AliasedProjection",
                },
            ),
            "progress_witness_invalid",
            id="row-presentation-key-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=None,
                current_step=None,
                result_row=_pure_failed_row(),
            ),
            "progress_witness_invalid",
            id="failure-without-visit",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row=_pure_failed_row(visit_count=2),
            ),
            "progress_witness_invalid",
            id="failure-visit-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row=_pure_skipped_row(
                    step_id="root.other_projection"
                ),
            ),
            "progress_witness_invalid",
            id="skip-identity-mismatch",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row={
                    **_exact_pure_completion_shell(),
                    "artifacts": {"return__value": 17},
                },
            ),
            "progress_witness_invalid",
            id="value-bearing-completion",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=None,
                result_row={
                    "name": _PURE_PRESENTATION_KEY,
                    "step_id": _PURE_STEP_ID,
                    "visit_count": _PURE_VISIT_COUNT,
                    "status": "running",
                },
            ),
            "progress_witness_invalid",
            id="nonterminal-row",
        ),
        pytest.param(
            _pure_progress_state(
                visit_count=_PURE_VISIT_COUNT,
                current_step=_pure_running_cursor(),
                result_row=_pure_failed_row(),
            ),
            "progress_witness_invalid",
            id="cursor-and-failure",
        ),
    ),
)
def test_pure_replay_progress_witness_classifies_closed_matrix(
    state: dict[str, Any],
    expected_classification: str,
) -> None:
    classification = pure_result_replay.classify_pure_replay_progress(
        state,
        witness=_pure_replay_witness(),
    )

    assert classification == expected_classification
