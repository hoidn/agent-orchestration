"""Loader and runtime coverage for reusable workflow imports and call boundaries."""

from copy import deepcopy
import json
import os
from dataclasses import replace
from pathlib import Path
import stat
from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping
from unittest.mock import patch

import pytest

from orchestrator.exceptions import WorkflowValidationError
from tests.workflow_fixture_loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.calls import CallExecutor
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_import_bundle, workflow_provenance
from orchestrator.workflow.pure_result_replay import (
    DERIVED_PURE_REPLAY_PROFILE,
    PureReplayVisitWitness,
    build_pure_completion_shell,
)
from orchestrator.workflow.resume_planner import ResumePlanner, ResumeStateIntegrityError
from tests.workflow_bundle_helpers import (
    bundle_context_dict,
    materialize_projection_body_steps,
)


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=False), encoding="utf-8")
    return path


def _projection_run_tree_snapshot(run_root: Path) -> tuple[tuple[str, str, bytes], ...]:
    """Return a deterministic whole-tree snapshot for mutation characterization."""
    entries: list[tuple[str, str, bytes]] = []

    def visit(directory: Path, relative_directory: Path) -> None:
        with os.scandir(directory) as children:
            sorted_children = sorted(children, key=lambda child: child.name)
        for child in sorted_children:
            relative_path = relative_directory / child.name
            relative_text = relative_path.as_posix()
            mode = child.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                entries.append((relative_text, "dir", b""))
                visit(Path(child.path), relative_path)
            elif stat.S_ISREG(mode):
                entries.append((relative_text, "file", Path(child.path).read_bytes()))
            elif stat.S_ISLNK(mode):
                entries.append(
                    (
                        relative_text,
                        "link",
                        os.readlink(child.path).encode("utf-8"),
                    )
                )
            else:
                entries.append((relative_text, "other", b""))

    visit(run_root, Path())
    return tuple(sorted(entries, key=lambda entry: entry[0]))


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_projection_resume_integrity_run_tree_snapshot_tracks_symlink_targets(
    tmp_path: Path,
) -> None:
    """Whole-tree mutation evidence must preserve link identity, not target bytes."""
    run_root = tmp_path / "run-tree"
    run_root.mkdir()
    (run_root / "target-a.txt").write_bytes(b"equal\n")
    (run_root / "target-b.txt").write_bytes(b"equal\n")
    link = run_root / "current.txt"
    link.symlink_to("target-a.txt")
    first = _projection_run_tree_snapshot(run_root)

    link.unlink()
    link.symlink_to("target-b.txt")
    second = _projection_run_tree_snapshot(run_root)

    assert second != first
    assert ("current.txt", "link", b"target-b.txt") in second

    empty = run_root / "empty-a"
    empty.mkdir()
    first_empty_directory = _projection_run_tree_snapshot(run_root)
    empty.rename(run_root / "empty-b")
    second_empty_directory = _projection_run_tree_snapshot(run_root)

    assert first_empty_directory != second_empty_directory
    assert ("empty-b", "dir", b"") in second_empty_directory


def _library_workflow(*, version: str = "2.5") -> dict:
    return {
        "version": version,
        "name": "review-fix-loop",
        "inputs": {
            "max_cycles": {
                "kind": "scalar",
                "type": "integer",
            },
            "write_root": {
                "kind": "relpath",
                "type": "relpath",
            },
        },
        "outputs": {
            "approved": {
                "kind": "scalar",
                "type": "bool",
                "from": {"ref": "root.steps.SetApproved.artifacts.approved"},
            }
        },
        "artifacts": {
            "approved": {
                "kind": "scalar",
                "type": "bool",
            }
        },
        "steps": [
            {
                "name": "SetApproved",
                "id": "set_approved",
                "set_scalar": {
                    "artifact": "approved",
                    "value": True,
                },
            }
        ],
    }


def _caller_workflow(*, call_step: dict, imports: dict | None = None, version: str = "2.5") -> dict:
    return {
        "version": version,
        "name": "call-demo",
        "imports": imports or {"review_loop": "workflows/library/review_loop_fixture.yaml"},
        "steps": [call_step],
    }


def _managed_write_root_library(*, version: str = "2.5") -> dict:
    return {
        "version": version,
        "name": "write-root-library",
        "inputs": {
            "max_cycles": {
                "kind": "scalar",
                "type": "integer",
            },
            "write_root": {
                "kind": "relpath",
                "type": "relpath",
            },
        },
        "steps": [
            {
                "name": "WriteOutput",
                "id": "write_output",
                "command": ["bash", "-lc", "printf 'ok\\n'"],
                "output_file": "${inputs.write_root}/result.txt",
            }
        ],
    }


def _run_workflow(
    tmp_path: Path,
    workflow: dict,
    run_id: str,
    *,
    on_error: str = "stop",
) -> tuple[dict, dict]:
    workflow_path = _write_yaml(tmp_path / "workflow.yaml", workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(tmp_path, run_id=run_id)
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(loaded))
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    final_state = executor.execute(on_error=on_error)
    persisted = state_manager.load().to_dict()
    return final_state, persisted


def _write_projection_integrity_call_graph(
    workspace: Path,
    *,
    leaf_input: bool = False,
) -> Path:
    """Write a generic root -> middle -> leaf imported-call graph."""
    leaf_workflow = {
        "version": "2.5",
        "name": "projection-leaf",
        "artifacts": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
            }
        },
        "outputs": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
                "from": {"ref": "root.steps.SetReady.artifacts.ready"},
            }
        },
        "steps": [
            {
                "name": "SetReady",
                "id": "set_ready",
                "set_scalar": {
                    "artifact": "ready",
                    "value": True,
                },
            }
        ],
    }
    if leaf_input:
        leaf_workflow["inputs"] = {
            "token": {
                "kind": "scalar",
                "type": "integer",
            }
        }
    _write_yaml(
        workspace / "imports" / "leaf.yaml",
        leaf_workflow,
    )
    leaf_call = {
        "name": "InvokeLeaf",
        "id": "invoke_leaf",
        "call": "leaf",
    }
    if leaf_input:
        leaf_call["with"] = {"token": 7}
    _write_yaml(
        workspace / "imports" / "middle.yaml",
        {
            "version": "2.5",
            "name": "projection-middle",
            "imports": {"leaf": "leaf.yaml"},
            "outputs": {
                "ready": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.InvokeLeaf.artifacts.ready"},
                }
            },
            "steps": [
                leaf_call
            ],
        },
    )
    return _write_yaml(
        workspace / "workflow.yaml",
        {
            "version": "2.5",
            "name": "projection-root",
            "imports": {
                "middle": "imports/middle.yaml",
                "middle_duplicate_alias": "imports/middle.yaml",
            },
            "steps": [
                {
                    "name": "InvokeMiddle",
                    "id": "invoke_middle",
                    "call": "middle",
                }
            ],
        },
    )


def _typed_workflow_lisp_import(parent_bundle, alias: str):
    imported_bundle = workflow_import_bundle(parent_bundle, alias)
    assert imported_bundle is not None
    typed_bundle = replace(
        imported_bundle,
        provenance=replace(
            imported_bundle.provenance,
            frontend_kind="workflow_lisp",
        ),
    )
    return replace(
        parent_bundle,
        imports=MappingProxyType(
            {
                **parent_bundle.imports,
                alias: typed_bundle,
            }
        ),
    )


def _projection_call_frame(
    manager: StateManager,
    imported_bundle,
    *,
    frame_id: str,
    status: str,
    call_step_id: str,
    import_alias: str,
    bound_inputs: dict | None = None,
    current_step_id: str | None = None,
    checksum: str | None = None,
) -> dict:
    provenance = workflow_provenance(imported_bundle)
    assert provenance is not None
    child_state = {
        "workflow_checksum": (
            checksum
            if checksum is not None
            else manager.calculate_checksum(provenance.workflow_path)
        ),
        "steps": {},
        "call_frames": {},
    }
    if current_step_id is not None:
        child_state["current_step"] = {
            "status": "running",
            "name": "SetReady",
            "step_id": current_step_id,
        }
    return {
        "call_frame_id": frame_id,
        "call_step_name": "InvokeLeaf",
        "call_step_id": call_step_id,
        "import_alias": import_alias,
        "status": status,
        "bound_inputs": dict(bound_inputs or {}),
        "state": child_state,
    }


def _compile_imported_pure_replay_call_fixture(
    workspace: Path,
):
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    from orchestrator.workflow_lisp.workflows import ExternalToolBinding
    from tests.test_workflow_lisp_pure_result_replay import (
        _copy_runtime_fixture,
    )

    child_path = _copy_runtime_fixture(workspace)
    child_path.write_text(
        child_path.read_text(encoding="utf-8").replace(
            "(export orchestrate)",
            "(export ReplayResult orchestrate)",
        ),
        encoding="utf-8",
    )
    parent_path = workspace / "pure_replay_parent.orc"
    parent_path.write_text(
        """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule pure_replay_parent)
  (import pure_result_replay_effect_barrier :only
    (ReplayResult orchestrate))
  (export entry)
  (defworkflow entry
    ((seed Int)
     (enabled Bool))
    -> ReplayResult
    (let* ((forwarded-seed (+ seed 0)))
      (call orchestrate
        :seed forwarded-seed
        :enabled enabled))))
""",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        parent_path,
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
    parent_bundle = result.validated_bundles_by_name[
        "pure_replay_parent::entry"
    ]
    import_alias = "pure_result_replay_effect_barrier::orchestrate"
    child_bundle = workflow_import_bundle(parent_bundle, import_alias)
    assert child_bundle is not None
    return parent_path, parent_bundle, child_path, child_bundle


class _NestedPureReplayInterruption(BaseException):
    pass


def _pure_node_ids(bundle: Any) -> tuple[str, ...]:
    return tuple(
        node_id
        for node_id in bundle.ir.body_region
        if bundle.ir.nodes[node_id].kind.value == "pure_projection"
    )


def _assert_exact_replay_shell(
    *,
    bundle: Any,
    state: Mapping[str, Any],
    node_id: str,
) -> None:
    presentation_key = (
        bundle.projection.entries_by_node_id[node_id].presentation_key
    )
    assert state["steps"][presentation_key] == build_pure_completion_shell(
        PureReplayVisitWitness(
            presentation_key=presentation_key,
            step_index=bundle.ir.body_region.index(node_id),
            step_id=bundle.ir.nodes[node_id].step_id,
            visit_count=1,
        )
    )


def _pure_bundle_paths_for_state(
    workspace: Path,
    state: Mapping[str, Any],
) -> tuple[Path, ...]:
    bound_inputs = state.get("bound_inputs", {})
    assert isinstance(bound_inputs, Mapping)
    return tuple(
        workspace / value
        for name, value in bound_inputs.items()
        if (
            isinstance(name, str)
            and isinstance(value, str)
            and "__result_bundle" in name
            and (
                "__bind_seed__" in name
                or "__a__" in name
                or "__b__" in name
            )
        )
    )


def _assert_parent_replay_prefix_is_value_free(
    *,
    workspace: Path,
    bundle: Any,
    state: Mapping[str, Any],
) -> None:
    pure_node_ids = _pure_node_ids(bundle)
    assert len(pure_node_ids) == 1
    _assert_exact_replay_shell(
        bundle=bundle,
        state=state,
        node_id=pure_node_ids[0],
    )
    bundle_paths = _pure_bundle_paths_for_state(workspace, state)
    assert len(bundle_paths) == 1
    assert all(not path.exists() for path in bundle_paths)


def _assert_child_replay_state_is_value_free(
    *,
    workspace: Path,
    bundle: Any,
    state: Mapping[str, Any],
) -> None:
    assert (
        state["result_persistence_profile"]
        == DERIVED_PURE_REPLAY_PROFILE
    )
    pure_node_ids = _pure_node_ids(bundle)
    assert len(pure_node_ids) == 2
    for node_id in pure_node_ids:
        _assert_exact_replay_shell(
            bundle=bundle,
            state=state,
            node_id=node_id,
        )
    bundle_paths = _pure_bundle_paths_for_state(workspace, state)
    assert len(bundle_paths) == 2
    assert all(not path.exists() for path in bundle_paths)
    assert state.get("private_artifact_versions", {}) == {}


def _nested_diagnostic_surface(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    steps = state.get("steps", {})
    call_frames = state.get("call_frames", {})
    assert isinstance(steps, Mapping)
    assert isinstance(call_frames, Mapping)
    return {
        "error": state.get("error"),
        "step_errors": {
            str(name): row.get("error")
            for name, row in sorted(steps.items())
            if isinstance(row, Mapping) and "error" in row
        },
        "call_frames": {
            str(frame_id): _nested_diagnostic_surface(frame["state"])
            for frame_id, frame in sorted(call_frames.items())
            if (
                isinstance(frame, Mapping)
                and isinstance(frame.get("state"), Mapping)
            )
        },
    }


def _nested_artifact_surface(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    steps = state.get("steps", {})
    call_frames = state.get("call_frames", {})
    assert isinstance(steps, Mapping)
    assert isinstance(call_frames, Mapping)
    return {
        "workflow_outputs": state.get("workflow_outputs", {}),
        "artifact_versions": state.get("artifact_versions", {}),
        "artifact_consumes": state.get("artifact_consumes", {}),
        "step_artifacts": {
            str(name): row["artifacts"]
            for name, row in sorted(steps.items())
            if isinstance(row, Mapping) and "artifacts" in row
        },
        "call_frames": {
            str(frame_id): _nested_artifact_surface(frame["state"])
            for frame_id, frame in sorted(call_frames.items())
            if (
                isinstance(frame, Mapping)
                and isinstance(frame.get("state"), Mapping)
            )
        },
    }


def _nested_settlement_surface(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    call_frames = state.get("call_frames", {})
    assert isinstance(call_frames, Mapping)
    return {
        "status": state.get("status"),
        "finalization": state.get("finalization", {}),
        "call_frames": {
            str(frame_id): {
                "status": frame.get("status"),
                "body_status": frame.get("body_status"),
                "finalization_status": frame.get(
                    "finalization_status"
                ),
                "export_status": frame.get("export_status"),
                "state": _nested_settlement_surface(frame["state"]),
            }
            for frame_id, frame in sorted(call_frames.items())
            if (
                isinstance(frame, Mapping)
                and isinstance(frame.get("state"), Mapping)
            )
        },
    }


def test_fresh_noniterative_replay_profile_uses_typed_callee_not_parent(
    tmp_path: Path,
) -> None:
    parent_path, parent_bundle, _, child_bundle = (
        _compile_imported_pure_replay_call_fixture(tmp_path)
    )
    child_provenance = workflow_provenance(child_bundle)
    assert child_provenance is not None
    assert child_provenance.frontend_kind == "workflow_lisp"
    manager = StateManager(
        tmp_path,
        run_id="fresh-noniterative-replay-constructor",
    )
    manager.initialize(
        parent_path.name,
        context=bundle_context_dict(parent_bundle),
        bound_inputs={"seed": 3, "enabled": True},
    )
    assert manager.load().result_persistence_profile is None
    executor = WorkflowExecutor(parent_bundle, tmp_path, manager)
    state = manager.load().to_dict()
    call_step = next(
        step
        for step in materialize_projection_body_steps(parent_bundle)
        if step.get("call") is not None
    )
    constructor_kwargs: dict[str, Any] = {}

    def construct_manager(*_args: Any, **kwargs: Any) -> Any:
        constructor_kwargs.update(kwargs)
        return SimpleNamespace(
            update_bound_input_resume_validation=lambda **_kwargs: None,
            _snapshot=lambda: {},
        )

    with patch.object(
        executor.call_executor,
        "resolve_bound_inputs",
        return_value=({"seed": 3, "enabled": True}, None),
    ), patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
        side_effect=construct_manager,
    ), patch(
        "orchestrator.workflow.executor.WorkflowExecutor",
    ) as child_executor:
        child_executor.return_value.execute.return_value = {
            "status": "completed",
            "workflow_outputs": {
                "return__seed-value": 3,
                "return__effect-value": 4,
                "return__finished": True,
            },
        }
        result = executor.call_executor.execute_call(
            call_step,
            state,
            runtime_step_id=call_step["step_id"],
            step_name_override=call_step["name"],
        )

    assert result["status"] == "completed"
    assert constructor_kwargs["existing_frame"] is None
    assert (
        constructor_kwargs["result_persistence_profile"]
        == DERIVED_PURE_REPLAY_PROFILE
    )


def test_fresh_noniterative_replay_profile_clean_child_elides_pure_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_workflow_lisp_pure_result_replay import (
        _effect_calls,
        _execute_replay_profile_fixture,
    )

    explicit_workspace = tmp_path / "explicit-child"
    explicit_workspace.mkdir()
    monkeypatch.chdir(explicit_workspace)
    _, _, explicit_active, _ = _execute_replay_profile_fixture(
        explicit_workspace,
        run_id="nested-replay-explicit-child-control",
    )

    nested_workspace = tmp_path / "nested-parent"
    nested_workspace.mkdir()
    parent_path, parent_bundle, _, child_bundle = (
        _compile_imported_pure_replay_call_fixture(nested_workspace)
    )
    manager = StateManager(
        nested_workspace,
        run_id="fresh-noniterative-replay-clean",
    )
    manager.initialize(
        parent_path.name,
        context=bundle_context_dict(parent_bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
    )
    monkeypatch.chdir(nested_workspace)
    active = WorkflowExecutor(
        parent_bundle,
        nested_workspace,
        manager,
    ).execute(on_error="stop")
    persisted = manager.load().to_dict()
    frame = next(iter(persisted["call_frames"].values()))
    child_state = frame["state"]

    assert active["status"] == "completed"
    assert (
        active["workflow_outputs"]
        == explicit_active["workflow_outputs"]
    )
    _assert_parent_replay_prefix_is_value_free(
        workspace=nested_workspace,
        bundle=parent_bundle,
        state=persisted,
    )
    _assert_child_replay_state_is_value_free(
        workspace=nested_workspace,
        bundle=child_bundle,
        state=child_state,
    )
    assert _effect_calls(explicit_workspace) == ["E1", "E2"]
    assert _effect_calls(nested_workspace) == ["E1", "E2"]


def test_nested_pure_replay_resume_preserves_exact_effects_and_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_workflow_lisp_pure_result_replay import (
        _checkpoint_records,
        _effect_calls,
    )

    clean_workspace = tmp_path / "clean"
    clean_workspace.mkdir()
    clean_parent_path, clean_parent_bundle, _, clean_child_bundle = (
        _compile_imported_pure_replay_call_fixture(clean_workspace)
    )
    clean_manager = StateManager(
        clean_workspace,
        run_id="nested-pure-replay-clean-control",
    )
    clean_manager.initialize(
        clean_parent_path.name,
        context=bundle_context_dict(clean_parent_bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
    )
    monkeypatch.chdir(clean_workspace)
    clean_active = WorkflowExecutor(
        clean_parent_bundle,
        clean_workspace,
        clean_manager,
    ).execute(on_error="stop")
    clean_persisted = clean_manager.load().to_dict()
    clean_child_state = next(
        iter(clean_persisted["call_frames"].values())
    )["state"]

    resume_workspace = tmp_path / "resume"
    resume_workspace.mkdir()
    parent_path, parent_bundle, _, child_bundle = (
        _compile_imported_pure_replay_call_fixture(resume_workspace)
    )
    manager = StateManager(
        resume_workspace,
        run_id="nested-pure-replay-interrupted",
    )
    manager.initialize(
        parent_path.name,
        context=bundle_context_dict(parent_bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
    )
    e2_node_id = next(
        node_id
        for node_id in child_bundle.ir.body_region
        if node_id.endswith("__e2__finish_e2")
    )
    original_execute_command = WorkflowExecutor._execute_command

    def interrupt_child_e2(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if executor._step_id(step) == e2_node_id:
            raise _NestedPureReplayInterruption
        return original_execute_command(executor, step, state)

    monkeypatch.chdir(resume_workspace)
    with patch.object(
        WorkflowExecutor,
        "_execute_command",
        interrupt_child_e2,
    ):
        with pytest.raises(_NestedPureReplayInterruption):
            WorkflowExecutor(
                parent_bundle,
                resume_workspace,
                manager,
            ).execute(on_error="stop")

    interrupted = manager.load().to_dict()
    _assert_parent_replay_prefix_is_value_free(
        workspace=resume_workspace,
        bundle=parent_bundle,
        state=interrupted,
    )
    interrupted_frame = next(
        iter(interrupted["call_frames"].values())
    )
    interrupted_child = interrupted_frame["state"]
    assert interrupted_child["current_step"]["step_id"] == e2_node_id
    assert interrupted_child["current_step"]["status"] == "running"
    assert interrupted_child["bound_inputs"]["seed"] == 3
    _assert_child_replay_state_is_value_free(
        workspace=resume_workspace,
        bundle=child_bundle,
        state=interrupted_child,
    )
    assert _effect_calls(resume_workspace) == ["E1"]

    fresh_manager = StateManager(
        resume_workspace,
        run_id=manager.run_id,
    )
    fresh_manager.load()
    resumed = WorkflowExecutor(
        parent_bundle,
        resume_workspace,
        fresh_manager,
    ).execute(resume=True, on_error="stop")
    persisted = fresh_manager.load().to_dict()
    frame = next(iter(persisted["call_frames"].values()))
    child_state = frame["state"]

    assert resumed["status"] == "completed"
    assert frame["status"] == "completed"
    assert child_state["status"] == "completed"
    assert resumed["workflow_outputs"] == clean_active[
        "workflow_outputs"
    ]
    assert (
        _nested_artifact_surface(persisted)
        == _nested_artifact_surface(clean_persisted)
    )
    assert (
        _nested_diagnostic_surface(persisted)
        == _nested_diagnostic_surface(clean_persisted)
    )
    assert (
        _nested_settlement_surface(persisted)
        == _nested_settlement_surface(clean_persisted)
    )
    assert _effect_calls(clean_workspace) == ["E1", "E2"]
    assert _effect_calls(resume_workspace) == ["E1", "E2"]
    _assert_parent_replay_prefix_is_value_free(
        workspace=resume_workspace,
        bundle=parent_bundle,
        state=persisted,
    )
    _assert_child_replay_state_is_value_free(
        workspace=resume_workspace,
        bundle=child_bundle,
        state=child_state,
    )
    _assert_child_replay_state_is_value_free(
        workspace=clean_workspace,
        bundle=clean_child_bundle,
        state=clean_child_state,
    )
    pure_source_step_ids = {
        child_bundle.ir.nodes[node_id].step_id.removeprefix("root.")
        for node_id in _pure_node_ids(child_bundle)
    }
    checkpoint_records = _checkpoint_records(fresh_manager)
    assert checkpoint_records
    assert all(
        record["pending_effect_policy"]["effect_kind"]
        != "pure_projection"
        for record in checkpoint_records
    )
    assert all(
        binding.get("source_step_id") not in pure_source_step_ids
        for record in checkpoint_records
        for binding in record.get("restore_payload", {}).get(
            "bindings",
            (),
        )
    )


def test_pure_replay_runtime_keeps_true_imported_callee_refs_workflow_local(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.pure_result_replay import (
        PureReplayRuntime,
        PureResultReplayIndexError,
        derive_pure_result_replay_index,
    )
    from orchestrator.workflow.resume_projection_integrity import (
        ResumeScopePath,
    )
    from tests.test_workflow_lisp_pure_result_replay import _node_id_ending

    parent_path, parent_bundle, _, child_bundle = (
        _compile_imported_pure_replay_call_fixture(tmp_path)
    )
    import_alias = "pure_result_replay_effect_barrier::orchestrate"

    assert parent_bundle.imports[import_alias] is child_bundle
    runtime = PureReplayRuntime(
        bundle=child_bundle,
        scope_path=ResumeScopePath.root(str(parent_path)).child(
            "root.call-child::visit::1"
        ),
    )

    assert runtime.index.scope_kind == "root"
    assert set(runtime.index.nodes) == {
        _node_id_ending(child_bundle, "__a"),
        _node_id_ending(child_bundle, "__b"),
    }
    with pytest.raises(PureResultReplayIndexError) as excinfo:
        derive_pure_result_replay_index(
            child_bundle,
            scope_kind="self",
        )
    assert excinfo.value.reason == "dependency_index_invalid"
    assert excinfo.value.context["expected_scope"] == "self"
    assert excinfo.value.context["actual_scope"] == "root"


@pytest.mark.parametrize(
    ("forbidden_surface", "expected_surface"),
    (
        pytest.param("value_row", "steps", id="value-row"),
        pytest.param("pure_bundle", "pure_bundle", id="pure-bundle"),
        pytest.param(
            "private_lineage",
            "private_artifact_versions",
            id="private-lineage",
        ),
        pytest.param(
            "checkpoint",
            "checkpoint_record",
            id="same-frame-pure-checkpoint",
        ),
        pytest.param(
            "restore_binding",
            "restore_payload",
            id="restore-binding",
        ),
    ),
)
def test_existing_replay_profile_call_frame_audit_rejects_mixed_surfaces(
    tmp_path: Path,
    forbidden_surface: str,
    expected_surface: str,
) -> None:
    from orchestrator.workflow.call_frame_state import (
        load_existing_call_frame_read_only,
    )
    from orchestrator.workflow.pure_result_replay import (
        PureResultReplayIndexError,
    )
    from orchestrator.workflow.resume_projection_integrity import (
        ResumeScopePath,
    )
    from tests.test_workflow_lisp_pure_result_replay import (
        _emit_unconfigured_replay_profile_checkpoint,
        _node_id_ending,
        _pure_bundle_paths,
        _with_recurrent_pure_node,
    )

    parent_path, parent_bundle, child_path, child_bundle = (
        _compile_imported_pure_replay_call_fixture(tmp_path)
    )
    source_manager = StateManager(
        tmp_path,
        run_id=f"nested-profile-source-{forbidden_surface}",
    )
    source_manager.initialize(
        child_path.name,
        context=bundle_context_dict(child_bundle),
        bound_inputs={"seed": 3, "enabled": True},
        result_persistence_profile="derived_pure_replay.v1",
    )
    active = WorkflowExecutor(
        child_bundle,
        tmp_path,
        source_manager,
    ).execute(on_error="stop")
    child_state = json.loads(
        source_manager.state_file.read_text(encoding="utf-8")
    )
    parent_manager = StateManager(
        tmp_path,
        run_id=f"nested-profile-parent-{forbidden_surface}",
    )
    parent_manager.initialize(
        parent_path.name,
        context=bundle_context_dict(parent_bundle),
        bound_inputs={"seed": 3, "enabled": True},
    )
    parent_executor = WorkflowExecutor(
        parent_bundle,
        tmp_path,
        parent_manager,
    )
    frame_id = "root.imported-pure-replay::visit::1"
    a_node_id = _node_id_ending(child_bundle, "__a")
    b_node_id = _node_id_ending(child_bundle, "__b")

    if forbidden_surface == "value_row":
        presentation_key = child_bundle.projection.entries_by_node_id[
            a_node_id
        ].presentation_key
        child_state["steps"][presentation_key] = active["steps"][
            presentation_key
        ]
    elif forbidden_surface == "pure_bundle":
        bundle_path = next(
            path
            for path in _pure_bundle_paths(tmp_path, child_state)
            if "__a__result_bundle" in path.name
        )
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            '{"forbidden_profile_mix":true}\n',
            encoding="utf-8",
        )
    elif forbidden_surface == "private_lineage":
        child_state["private_artifact_versions"] = {
            "forbidden-derived-value": [
                {
                    "producer": child_bundle.ir.nodes[a_node_id].step_id,
                    "value": {"seed": 3},
                }
            ]
        }
    elif forbidden_surface == "checkpoint":
        _emit_unconfigured_replay_profile_checkpoint(
            bundle=child_bundle,
            manager=parent_manager,
            node_id=a_node_id,
            call_frame_id=frame_id,
        )
    else:
        child_bundle = _with_recurrent_pure_node(
            child_bundle,
            node_id=b_node_id,
        )
        _emit_unconfigured_replay_profile_checkpoint(
            bundle=child_bundle,
            manager=parent_manager,
            node_id=b_node_id,
            call_frame_id=frame_id,
        )

    before_parent_bytes = parent_manager.state_file.read_bytes()
    before_parent_tree = _projection_run_tree_snapshot(
        parent_manager.run_root
    )
    detached_state = load_existing_call_frame_read_only(
        {"state": child_state}
    )

    # The execute_call ordering test below proves this hook runs before the
    # child manager constructor and its bound-input-validation persistence.
    with pytest.raises(PureResultReplayIndexError) as excinfo:
        parent_executor._audit_existing_pure_replay_call_frame(
            child_bundle,
            detached_state,
            ResumeScopePath.root(str(parent_path)).child(frame_id),
        )

    assert excinfo.value.code == "pure_result_replay_unavailable"
    assert excinfo.value.reason == "profile_conflict"
    assert excinfo.value.context["surface"] == expected_surface
    assert parent_manager.state_file.read_bytes() == before_parent_bytes
    assert (
        _projection_run_tree_snapshot(parent_manager.run_root)
        == before_parent_tree
    )


def test_existing_call_frame_read_only_loader_returns_detached_state_without_io(
    tmp_path: Path,
) -> None:
    from orchestrator.state import RunState
    from orchestrator.workflow import call_frame_state

    existing_frame = {
        "state": {
            "schema_version": StateManager.SCHEMA_VERSION,
            "run_id": "detached-call-frame",
            "workflow_file": "imports/child.orc",
            "workflow_checksum": "sha256:" + ("1" * 64),
            "started_at": "2026-07-30T00:00:00+00:00",
            "updated_at": "2026-07-30T00:00:01+00:00",
            "status": "running",
            "context": {"nested": {"values": [1]}},
            "bound_inputs": {"payload": {"items": ["a"]}},
            "steps": {},
        }
    }
    before = deepcopy(existing_frame)

    with patch.object(
        Path,
        "mkdir",
        side_effect=AssertionError("read-only loader attempted directory creation"),
    ), patch.object(
        StateManager,
        "_write_state",
        side_effect=AssertionError("read-only loader attempted persistence"),
    ):
        loaded = call_frame_state.load_existing_call_frame_read_only(
            existing_frame
        )

    assert isinstance(loaded, RunState)
    loaded.context["nested"]["values"].append(2)
    loaded.bound_inputs["payload"]["items"].append("b")
    assert existing_frame == before
    assert not (tmp_path / ".orchestrate").exists()


def test_existing_reached_call_frame_audit_hook_is_read_only_and_precedes_constructor(
    tmp_path: Path,
) -> None:
    from orchestrator.state import RunState

    class AuditStopped(RuntimeError):
        pass

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    leaf_bundle = workflow_import_bundle(middle_bundle, "leaf")
    assert leaf_bundle is not None
    manager = StateManager(tmp_path, run_id="reached-call-read-only-audit")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(middle_bundle, tmp_path, manager)
    executor.resume_mode = True
    frame_id = "root.invoke_leaf::visit::1"
    state = manager.load().to_dict()
    child_state = manager.load().to_dict()
    leaf_provenance = workflow_provenance(leaf_bundle)
    assert leaf_provenance is not None
    child_state.update(
        {
            "workflow_file": "imports/leaf.yaml",
            "workflow_checksum": manager.calculate_checksum(
                leaf_provenance.workflow_path
            ),
            "status": "running",
            "context": bundle_context_dict(leaf_bundle),
            "bound_inputs": {},
            "steps": {},
            "call_frames": {},
            "step_visits": {},
            "result_persistence_profile": "derived_pure_replay.v1",
        }
    )
    frame = _projection_call_frame(
        manager,
        leaf_bundle,
        frame_id=frame_id,
        status="running",
        call_step_id="root.invoke_leaf",
        import_alias="leaf",
    )
    frame["state"] = child_state
    state["step_visits"] = {"InvokeLeaf": 1}
    state["call_frames"] = {frame_id: frame}
    before_state = deepcopy(state)
    before_bytes = manager.state_file.read_bytes()
    before_tree = _projection_run_tree_snapshot(manager.run_root)
    events: list[str] = []

    def audit_existing_frame(
        imported_workflow,
        detached_state,
        scope_path,
    ) -> None:
        events.append("audit")
        assert imported_workflow is leaf_bundle
        assert isinstance(detached_state, RunState)
        assert scope_path.call_frame_ids == (frame_id,)
        detached_state.context["audit_probe"] = {"detached": True}
        assert state == before_state
        raise AuditStopped

    executor._audit_existing_pure_replay_call_frame = audit_existing_frame

    def unexpected_constructor(*_args, **_kwargs):
        events.append("constructor")
        raise AssertionError("call-frame constructor ran before detached audit")

    with patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
        side_effect=unexpected_constructor,
    ), patch.object(
        manager,
        "update_call_frame",
        side_effect=AssertionError("detached audit attempted a frame write"),
    ):
        with pytest.raises(AuditStopped):
            executor.call_executor.execute_call(
                materialize_projection_body_steps(middle_bundle)[0],
                state,
            )

    assert events == ["audit"]
    assert state == before_state
    assert manager.state_file.read_bytes() == before_bytes
    assert _projection_run_tree_snapshot(manager.run_root) == before_tree


def test_fresh_non_workflow_lisp_call_frame_ignores_parent_profile_and_orc_suffix(
    tmp_path: Path,
) -> None:
    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    middle_provenance = workflow_provenance(middle_bundle)
    assert middle_provenance is not None
    suffix_only_bundle = replace(
        middle_bundle,
        provenance=replace(
            middle_provenance,
            workflow_path=tmp_path / "imports" / "misleading.orc",
            frontend_kind=None,
        ),
    )
    root_bundle = replace(
        root_bundle,
        imports=MappingProxyType(
            {
                **root_bundle.imports,
                "middle": suffix_only_bundle,
            }
        ),
    )
    suffix_only_provenance = workflow_provenance(suffix_only_bundle)
    assert suffix_only_provenance is not None
    assert suffix_only_provenance.workflow_path.suffix == ".orc"
    assert suffix_only_provenance.frontend_kind is None
    manager = StateManager(tmp_path, run_id="fresh-call-no-profile-inheritance")
    manager.initialize(
        "workflow.yaml",
        context=bundle_context_dict(root_bundle),
        result_persistence_profile="derived_pure_replay.v1",
    )
    executor = WorkflowExecutor(root_bundle, tmp_path, manager)
    state = manager.load().to_dict()
    constructor_kwargs: dict = {}
    audit_calls: list[str] = []

    def audit_existing_frame(*_args, **_kwargs) -> None:
        audit_calls.append("audit")

    executor._audit_existing_pure_replay_call_frame = audit_existing_frame

    def construct_manager(*_args, **kwargs):
        constructor_kwargs.update(kwargs)
        return SimpleNamespace(
            update_bound_input_resume_validation=lambda **_kwargs: None,
            _snapshot=lambda: {},
        )

    with patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
        side_effect=construct_manager,
    ), patch(
        "orchestrator.workflow.executor.WorkflowExecutor",
    ) as child_executor:
        child_executor.return_value.execute.return_value = {
            "status": "completed",
            "workflow_outputs": {},
        }
        result = executor.call_executor.execute_call(
            materialize_projection_body_steps(root_bundle)[0],
            state,
        )

    assert result["status"] == "completed"
    assert audit_calls == []
    assert constructor_kwargs.get("result_persistence_profile") is None
    assert constructor_kwargs["existing_frame"] is None


def test_existing_absent_replay_profile_workflow_lisp_frame_is_unchanged_before_execution(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.call_frame_state import (
        _CallFrameStateManager,
    )

    class ChildExecutionReached(BaseException):
        pass

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    middle_bundle = _typed_workflow_lisp_import(middle_bundle, "leaf")
    leaf_bundle = workflow_import_bundle(middle_bundle, "leaf")
    assert leaf_bundle is not None
    leaf_provenance = workflow_provenance(leaf_bundle)
    assert leaf_provenance is not None
    assert leaf_provenance.frontend_kind == "workflow_lisp"

    manager = StateManager(
        tmp_path,
        run_id="existing-absent-profile-call-frame",
    )
    manager.initialize(
        "workflow.yaml",
        context=bundle_context_dict(root_bundle),
    )
    executor = WorkflowExecutor(middle_bundle, tmp_path, manager)
    executor.resume_mode = True
    call_step = materialize_projection_body_steps(middle_bundle)[0]
    frame_id = f"{call_step['step_id']}::visit::1"
    seeded = _CallFrameStateManager(
        parent_manager=manager,
        workflow=leaf_bundle,
        frame_id=frame_id,
        call_step_name=call_step["name"],
        call_step_id=call_step["step_id"],
        import_alias="leaf",
        bound_inputs={},
        result_persistence_profile=None,
    )
    seeded.update_bound_input_resume_validation(
        status="reused",
        diagnostics=[],
    )
    persisted = manager.load()
    persisted.step_visits = {call_step["name"]: 1}
    manager._write_state()
    state = manager.load().to_dict()
    selected_frame = state["call_frames"][frame_id]
    selected_state = selected_frame["state"]
    assert "result_persistence_profile" not in selected_state
    selected_frame_bytes = _canonical_json_bytes(selected_frame)
    constructor_profiles: list[str | None] = []

    def construct_manager(*args: Any, **kwargs: Any) -> Any:
        constructor_profiles.append(
            kwargs.get("result_persistence_profile")
        )
        assert kwargs["existing_frame"] is selected_frame
        assert _canonical_json_bytes(kwargs["existing_frame"]) == (
            selected_frame_bytes
        )
        constructed = _CallFrameStateManager(*args, **kwargs)
        assert _canonical_json_bytes(
            manager.load().to_dict()["call_frames"][frame_id]
        ) == selected_frame_bytes
        return constructed

    def reach_child_execution(*_args: Any, **_kwargs: Any) -> Any:
        assert _canonical_json_bytes(
            manager.load().to_dict()["call_frames"][frame_id]
        ) == selected_frame_bytes
        raise ChildExecutionReached

    with patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
        side_effect=construct_manager,
    ), patch(
        "orchestrator.workflow.executor.WorkflowExecutor",
        side_effect=reach_child_execution,
    ):
        with pytest.raises(ChildExecutionReached):
            executor.call_executor.execute_call(call_step, state)

    assert constructor_profiles == [None]
    assert (
        _canonical_json_bytes(state["call_frames"][frame_id])
        == selected_frame_bytes
    )
    assert _canonical_json_bytes(
        manager.load().to_dict()["call_frames"][frame_id]
    ) == selected_frame_bytes


def test_imported_workflows_must_validate_independently(tmp_path: Path):
    library_path = _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.5",
            "name": "invalid-library",
            "providers": {
                "broken": {
                    "input_mode": "stdin",
                }
            },
            "steps": [
                {
                    "name": "Review",
                    "provider": "broken",
                }
            ],
        },
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
            imports={"review_loop": str(library_path.relative_to(tmp_path))},
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    messages = [str(error.message) for error in exc_info.value.errors]
    assert any("Import 'review_loop'" in message for message in messages)
    assert any("missing required 'command' field" in message for message in messages)


def test_call_requires_authored_stable_id(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(),
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "call requires an authored stable 'id'" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_rejects_mixed_caller_callee_versions(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(version="2.4"),
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "must declare the same DSL version" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_with_literal_binding_must_match_callee_input_type(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(),
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": "not-an-int",
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "call.with.max_cycles is invalid" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_rejects_unknown_import_alias(tmp_path: Path):
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "missing_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "unknown import alias 'missing_loop'" in str(error.message)
        for error in exc_info.value.errors
    )


def test_imported_v2_workflow_allows_depends_on_inject(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.7",
            "name": "imported-depends-on-inject",
            "providers": {
                "reviewer": {
                    "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                    "input_mode": "stdin",
                }
            },
            "steps": [
                {
                    "name": "Review",
                    "id": "review",
                    "provider": "reviewer",
                    "depends_on": {
                        "required": ["state/runtime-manifest.txt"],
                        "inject": True,
                    },
                }
            ],
        },
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "call-demo",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "steps": [
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                }
            ],
        },
    )

    workflow = WorkflowLoader(tmp_path).load(caller_path)

    assert [step["name"] for step in materialize_projection_body_steps(workflow)] == ["RunReviewLoop"]


def test_call_executes_from_loaded_bundle_without_legacy_import_magic(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    state_manager = StateManager(tmp_path, run_id="bundle-call")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    final_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    assert final_state["status"] == "completed"
    assert final_state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}


def test_call_uses_typed_import_contracts_when_legacy_specs_are_missing(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    state_manager = StateManager(tmp_path, run_id="bundle-call-typed-contracts")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    final_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    persisted = state_manager.load().to_dict()

    assert final_state["status"] == "completed"
    assert final_state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}

    frame = next(iter(persisted["call_frames"].values()))
    assert frame["bound_inputs"] == {
        "max_cycles": 3,
        "write_root": "state/review-loop",
    }
    assert frame["export_status"] == "completed"
    assert frame["state"]["workflow_outputs"] == {"approved": True}


def test_call_runtime_preserves_depends_on_inject_and_asset_depends_on_prompt_order(
    tmp_path: Path,
):
    workflow_dir = tmp_path / "workflows" / "library"
    (workflow_dir / "prompts").mkdir(parents=True)
    (workflow_dir / "rubrics").mkdir(parents=True)
    (workflow_dir / "prompts" / "depends_on_inject_imported_review.md").write_text(
        "Base prompt.\n",
        encoding="utf-8",
    )
    (workflow_dir / "rubrics" / "depends_on_inject_imported_review.md").write_text(
        "Rubric body.\n",
        encoding="utf-8",
    )
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.7",
            "name": "depends-on-inject-imported-review",
            "inputs": {
                "state_root": {
                    "kind": "relpath",
                    "type": "relpath",
                },
                "manifest_path": {
                    "kind": "relpath",
                    "type": "relpath",
                    "must_exist_target": True,
                },
            },
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {
                        "ref": "root.steps.ReviewImportedInjection.artifacts.review_decision",
                    },
                }
            },
            "providers": {
                "reviewer": {
                    "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                    "input_mode": "stdin",
                }
            },
            "steps": [
                {
                    "name": "ReviewImportedInjection",
                    "id": "review_imported_injection",
                    "provider": "reviewer",
                    "asset_file": "prompts/depends_on_inject_imported_review.md",
                    "asset_depends_on": ["rubrics/depends_on_inject_imported_review.md"],
                    "depends_on": {
                        "required": ["${inputs.manifest_path}"],
                        "inject": True,
                    },
                    "expected_outputs": [
                        {
                            "name": "review_decision",
                            "path": "${inputs.state_root}/decision.txt",
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                        }
                    ],
                }
            ],
        },
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "call-mixed-injection-order",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "steps": [
                {
                    "name": "WriteRuntimeManifest",
                    "id": "write_runtime_manifest",
                    "command": [
                        "bash",
                        "-lc",
                        (
                            "mkdir -p state && "
                            "printf 'runtime manifest\\n' > state/runtime-manifest.txt && "
                            "printf 'state/runtime-manifest.txt\\n' > state/manifest_path.txt"
                        ),
                    ],
                    "expected_outputs": [
                        {
                            "name": "manifest_path",
                            "path": "state/manifest_path.txt",
                            "type": "relpath",
                            "must_exist_target": True,
                        }
                    ],
                },
                {
                    "name": "RunImportedReview",
                    "id": "run_imported_review",
                    "call": "review_loop",
                    "with": {
                        "state_root": "state/imported-review",
                        "manifest_path": {
                            "ref": "root.steps.WriteRuntimeManifest.artifacts.manifest_path",
                        },
                    },
                },
            ],
        },
    )

    workflow = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    state_manager = StateManager(tmp_path, run_id="call-mixed-injection-order")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(_self, *args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_self, _invocation, **_kwargs):
        decision_path = tmp_path / "state" / "imported-review" / "decision.txt"
        decision_path.parent.mkdir(parents=True, exist_ok=True)
        decision_path.write_text("APPROVE\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["RunImportedReview"]["artifacts"] == {"review_decision": "APPROVE"}
    assert len(state.get("call_frames", {})) == 1
    assert captured["prompt"].index("The following required files are available:") < captured["prompt"].index(
        "=== File: rubrics/depends_on_inject_imported_review.md ==="
    )
    assert captured["prompt"].index(
        "=== File: rubrics/depends_on_inject_imported_review.md ==="
    ) < captured["prompt"].index("Base prompt.")
    assert captured["prompt"].index("Base prompt.") < captured["prompt"].index("## Output Contract")


def test_import_path_rejects_source_tree_escape(tmp_path: Path):
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
            imports={"review_loop": "../outside.yaml"},
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "workflow source tree" in str(error.message)
        for error in exc_info.value.errors
    )


def test_reusable_workflow_rejects_hard_coded_dsl_managed_write_root(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "steps": [
                {
                    "name": "WriteOutput",
                    "id": "write_output",
                    "command": ["bash", "-lc", "printf 'ok\\n'"],
                    "output_file": "state/fixed-output.txt",
                }
            ],
        },
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "DSL-managed write roots" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_rejects_colliding_write_root_bindings(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "inputs": {
                "write_root": {
                    "kind": "relpath",
                    "type": "relpath",
                }
            },
            "steps": [
                {
                    "name": "WriteOutput",
                    "id": "write_output",
                    "command": ["bash", "-lc", "printf 'ok\\n'"],
                    "output_file": "${inputs.write_root}/result.txt",
                }
            ],
        },
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.5",
            "name": "call-demo",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "steps": [
                {
                    "name": "RunReviewLoopA",
                    "id": "run_review_loop_a",
                    "call": "review_loop",
                    "with": {
                        "write_root": "state/shared",
                    },
                },
                {
                    "name": "RunReviewLoopB",
                    "id": "run_review_loop_b",
                    "call": "review_loop",
                    "with": {
                        "write_root": "state/shared",
                    },
                },
            ],
        },
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "colliding write-root bindings" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_rejects_colliding_write_root_bindings_without_imported_legacy_magic(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _managed_write_root_library(version="2.7"),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "for-each-call-collision-typed-imports",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "steps": [
                {
                    "name": "ReviewItems",
                    "id": "review_items",
                    "for_each": {
                        "items": ["a", "b"],
                        "as": "item",
                        "steps": [
                            {
                                "name": "ResolveWriteRoot",
                                "id": "resolve_write_root",
                                "command": ["bash", "-lc", "printf 'state/shared\\n'"],
                                "output_file": "state/shared-write-root.txt",
                                "expected_outputs": [
                                    {
                                        "name": "write_root",
                                        "path": "state/shared-write-root.txt",
                                        "type": "relpath",
                                    }
                                ],
                            },
                            {
                                "name": "RunReviewLoop",
                                "id": "run_review_loop",
                                "call": "review_loop",
                                "with": {
                                    "max_cycles": 1,
                                    "write_root": {
                                        "ref": "self.steps.ResolveWriteRoot.artifacts.write_root",
                                    },
                                },
                            },
                        ],
                    },
                },
            ],
        },
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    state_manager = StateManager(tmp_path, run_id="for-each-call-collision-typed-imports")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(on_error="continue")
    persisted = state_manager.load().to_dict()

    assert state["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["type"] == "contract_violation"
    assert state["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["context"]["reason"] == (
        "colliding_write_root_binding"
    )
    assert persisted["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["type"] == "contract_violation"
    assert persisted["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["context"]["reason"] == (
        "colliding_write_root_binding"
    )


def test_repeat_until_call_rejects_invariant_write_root_binding(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _managed_write_root_library(version="2.7"),
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "looped-call-demo",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "artifacts": {
                "done": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "steps": [
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "iteration_body",
                        "outputs": {
                            "done": {
                                "kind": "scalar",
                                "type": "bool",
                                "from": {
                                    "ref": "self.steps.MarkDone.artifacts.done",
                                },
                            }
                        },
                        "condition": {
                            "artifact_bool": {
                                "ref": "self.outputs.done",
                            }
                        },
                        "max_iterations": 2,
                        "steps": [
                            {
                                "name": "RunReviewLoop",
                                "id": "run_review_loop",
                                "call": "review_loop",
                                "with": {
                                    "max_cycles": 1,
                                    "write_root": "state/review-loop",
                                },
                            },
                            {
                                "name": "MarkDone",
                                "id": "mark_done",
                                "set_scalar": {
                                    "artifact": "done",
                                    "value": True,
                                },
                            },
                        ],
                    },
                }
            ],
        },
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "must vary per invocation" in str(error.message)
        for error in exc_info.value.errors
    )


def test_for_each_call_runtime_rejects_reused_write_root_from_loop_local_ref(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _managed_write_root_library(version="2.5"),
    )
    workflow = {
        "version": "2.5",
        "name": "for-each-call-collision",
        "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
        "steps": [
            {
                "name": "ReviewItems",
                "id": "review_items",
                "for_each": {
                    "items": ["a", "b"],
                    "as": "item",
                    "steps": [
                        {
                            "name": "ResolveWriteRoot",
                            "id": "resolve_write_root",
                            "command": ["bash", "-lc", "printf 'state/shared\\n'"],
                            "output_file": "state/shared-write-root.txt",
                            "expected_outputs": [
                                {
                                    "name": "write_root",
                                    "path": "state/shared-write-root.txt",
                                    "type": "relpath",
                                }
                            ],
                        },
                        {
                            "name": "RunReviewLoop",
                            "id": "run_review_loop",
                            "call": "review_loop",
                            "with": {
                                "max_cycles": 1,
                                "write_root": {
                                    "ref": "self.steps.ResolveWriteRoot.artifacts.write_root",
                                },
                            },
                        },
                    ],
                },
            }
        ],
    }

    final_state, persisted = _run_workflow(
        tmp_path,
        workflow,
        run_id="for-each-call-collision-run",
        on_error="continue",
    )

    assert final_state["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["type"] == "contract_violation"
    assert persisted["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["type"] == "contract_violation"
    assert persisted["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["context"]["reason"] == (
        "colliding_write_root_binding"
    )
    assert len(persisted.get("call_frames", {})) == 1


def test_reusable_call_runtime_write_root_bindings_still_validate(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _managed_write_root_library(version="2.7"),
    )
    final_state, persisted = _run_workflow(
        tmp_path,
        {
            "version": "2.7",
            "name": "call-with-distinct-write-root",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "steps": [
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                    "with": {
                        "max_cycles": 1,
                        "write_root": "state/review-loop-a",
                    },
                }
            ],
        },
        run_id="call-with-distinct-write-root",
    )

    assert final_state["status"] == "completed"
    assert len(persisted.get("call_frames", {})) == 1
    call_frame = next(iter(persisted["call_frames"].values()))
    assert call_frame["bound_inputs"]["write_root"] == "state/review-loop-a"


def test_call_executes_imported_workflow_and_persists_call_frame_state(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "artifacts": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "outputs": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.SetApproved.artifacts.approved"},
                }
            },
            "steps": [
                {
                    "name": "SetApproved",
                    "id": "set_approved",
                    "set_scalar": {
                        "artifact": "approved",
                        "value": True,
                    },
                }
            ],
        },
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
        ),
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(tmp_path, run_id="call-run")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}
    assert "SetApproved" not in state["steps"]

    call_frames = state.get("call_frames", {})
    assert len(call_frames) == 1
    frame = next(iter(call_frames.values()))
    assert frame["import_alias"] == "review_loop"
    assert frame["status"] == "completed"
    assert frame["export_status"] == "completed"
    assert frame["state"]["workflow_checksum"].startswith("sha256:")
    assert frame["state"]["workflow_outputs"] == {"approved": True}
    assert frame["state"]["steps"]["SetApproved"]["artifacts"] == {"approved": True}


def test_resumed_parent_starts_never_entered_child_call_fresh(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.5",
            "name": "resume-reaches-new-child",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "steps": [
                {
                    "name": "PersistProgress",
                    "id": "persist_progress",
                    "command": ["bash", "-lc", "mkdir -p state && printf 'done\\n' > state/progress.txt"],
                },
                {
                    "name": "ResumeGate",
                    "id": "resume_gate",
                    "command": ["bash", "-lc", "test -f state/resume-ready.txt"],
                },
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                    "with": {
                        "max_cycles": 3,
                        "write_root": "state/review-loop",
                    },
                },
            ],
        },
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    state_manager = StateManager(tmp_path, run_id="resume-reaches-new-child")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))

    first_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    assert first_state["status"] == "failed"
    assert first_state["steps"]["PersistProgress"]["status"] == "completed"
    assert first_state.get("call_frames", {}) == {}
    (tmp_path / "state" / "resume-ready.txt").write_text("ready\n", encoding="utf-8")

    child_default_resume_calls: list[dict] = []

    def _default_resume_decision(executor, state, *, restart_node_id):
        if isinstance(executor.state_manager, StateManager):
            return {
                "mode": "LEXICAL_CHECKPOINT_DEFAULT",
                "restore_decision": "RESTORED",
                "restore_candidate": {
                    "kind": "RESTORED",
                    "checkpoint_id": "checkpoint:prior",
                    "record_id": "record:prior",
                    "source_map_origin_key": "source:prior",
                    "restore_payload": {},
                    "diagnostics": [],
                },
                "checkpoint_id": "checkpoint:prior",
                "record_id": "record:prior",
                "selection_reason": "validated_prior_boundary",
                "diagnostics": [],
            }
        child_default_resume_calls.append(state)
        return {
            "mode": "FAIL_CLOSED",
            "restore_decision": None,
            "diagnostics": ["lexical_default_resume_prior_boundary_missing"],
        }

    with patch.object(
        WorkflowExecutor,
        "_determine_resume_default_resume_decision",
        _default_resume_decision,
    ):
        resumed_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed_state["status"] == "completed"
    assert resumed_state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}
    assert child_default_resume_calls == []
    assert len(resumed_state["call_frames"]) == 1
    frame = next(iter(resumed_state["call_frames"].values()))
    assert frame["bound_input_resume_validation"] == {
        "status": "fresh",
        "diagnostics": [],
    }


@pytest.mark.parametrize(
    ("corrupt_call_frames", "expected_detail"),
    (
        ("malformed-container", "call_frames_not_mapping"),
        (
            {"root.run_review_loop::visit::1": "malformed-frame"},
            "call_frame_not_mapping",
        ),
    ),
)
def test_resumed_parent_rejects_malformed_child_call_frame_state_without_overwrite(
    tmp_path: Path,
    corrupt_call_frames,
    expected_detail: str,
):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.5",
            "name": "resume-rejects-corrupt-child-state",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "steps": [
                {
                    "name": "ResumeGate",
                    "id": "resume_gate",
                    "command": ["bash", "-lc", "test -f state/resume-ready.txt"],
                },
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                    "with": {
                        "max_cycles": 3,
                        "write_root": "state/review-loop",
                    },
                },
            ],
        },
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    state_manager = StateManager(
        tmp_path,
        run_id=f"resume-corrupt-child-state-{expected_detail}",
    )
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    first_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    assert first_state["status"] == "failed"
    assert first_state.get("call_frames", {}) == {}

    persisted = state_manager.load()
    persisted.call_frames = corrupt_call_frames
    state_manager._write_state()
    before_resume = state_manager.load().to_dict()
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / "resume-ready.txt").write_text("ready\n", encoding="utf-8")
    parent_default_resume_calls: list[dict] = []

    def _default_resume_decision(executor, state, *, restart_node_id):
        parent_default_resume_calls.append(state)
        return {
            "mode": "LEXICAL_CHECKPOINT_DEFAULT",
            "restore_decision": "RESTORED",
            "restore_candidate": {
                "kind": "RESTORED",
                "restore_payload": {},
                "diagnostics": [],
            },
            "selection_reason": "validated_prior_boundary",
            "diagnostics": [],
        }

    resume_executor = WorkflowExecutor(bundle, tmp_path, state_manager)
    with patch.object(
        WorkflowExecutor,
        "_determine_resume_default_resume_decision",
        _default_resume_decision,
    ), patch("orchestrator.workflow.executor.WorkflowExecutor") as child_constructor:
        child_constructor.return_value.execute.return_value = {
            "status": "completed",
            "workflow_outputs": {},
        }
        resumed_state = resume_executor.execute(resume=True)

    assert parent_default_resume_calls == []
    assert resumed_state["status"] == "failed"
    error = resumed_state["error"]
    assert error["type"] == "resume_projection_integrity_error"
    assert error["context"]["reason"] == "unsupported_shape"
    assert error["context"]["field"] == (
        "call_frames"
        if expected_detail == "call_frames_not_mapping"
        else "call_frames.root.run_review_loop::visit::1"
    )
    child_constructor.assert_not_called()
    assert resumed_state["call_frames"] == corrupt_call_frames
    assert resumed_state["steps"] == before_resume["steps"]
    assert resumed_state["step_visits"] == before_resume["step_visits"]
    assert resumed_state.get("current_step") == before_resume.get("current_step")
    assert state_manager.load().call_frames == corrupt_call_frames


def test_resumed_parent_still_fails_closed_for_persisted_child_without_prior_boundary(
    tmp_path: Path,
):
    library = _library_workflow()
    library["steps"].insert(
        0,
        {
            "name": "ResumeGate",
            "id": "resume_gate",
            "command": ["bash", "-lc", "test -f state/child-resume-ready.txt"],
        },
    )
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        library,
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    state_manager = StateManager(tmp_path, run_id="resume-existing-child-invalid-boundary")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))

    first_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    assert first_state["status"] == "failed"
    assert len(first_state["call_frames"]) == 1
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / "child-resume-ready.txt").write_text("ready\n", encoding="utf-8")
    child_default_resume_calls: list[dict] = []

    def _default_resume_decision(executor, state, *, restart_node_id):
        if isinstance(executor.state_manager, StateManager):
            return {
                "mode": "LEXICAL_CHECKPOINT_DEFAULT",
                "restore_decision": "RESTORED",
                "restore_candidate": {
                    "kind": "RESTORED",
                    "restore_payload": {},
                    "diagnostics": [],
                },
                "selection_reason": "validated_prior_boundary",
                "diagnostics": [],
            }
        child_default_resume_calls.append(state)
        return {
            "mode": "FAIL_CLOSED",
            "restore_decision": None,
            "diagnostics": ["lexical_default_resume_prior_boundary_missing"],
        }

    with patch.object(
        WorkflowExecutor,
        "_determine_resume_default_resume_decision",
        _default_resume_decision,
    ):
        resumed_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed_state["status"] == "failed"
    assert len(child_default_resume_calls) == 1
    child_error = resumed_state["steps"]["RunReviewLoop"]["error"]["context"]["error"]
    assert child_error["type"] == "lexical_default_resume_invalid"
    assert child_error["context"]["diagnostics"] == [
        "lexical_default_resume_prior_boundary_missing"
    ]
    assert len(resumed_state["call_frames"]) == 1
    frame = next(iter(resumed_state["call_frames"].values()))
    assert frame["bound_input_resume_validation"] == {
        "status": "reused",
        "diagnostics": [],
    }


def test_failed_workflow_lisp_child_retry_still_allocates_fresh_frame(tmp_path: Path):
    from orchestrator.workflow.call_frame_state import (
        _CallFrameStateManager,
    )

    library = _library_workflow()
    library["steps"].insert(
        0,
        {
            "name": "ResumeGate",
            "id": "resume_gate",
            "command": ["bash", "-lc", "test -f state/child-retry-ready.txt"],
        },
    )
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        library,
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    imported_bundle = workflow_import_bundle(bundle, "review_loop")
    assert imported_bundle is not None
    imported_bundle = replace(
        imported_bundle,
        provenance=replace(
            imported_bundle.provenance,
            frontend_kind="workflow_lisp",
        ),
    )
    bundle = replace(
        bundle,
        imports=MappingProxyType(
            {
                **bundle.imports,
                "review_loop": imported_bundle,
            }
        ),
    )
    state_manager = StateManager(tmp_path, run_id="resume-failed-child-fresh-retry")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))

    first_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    assert first_state["status"] == "failed"
    assert len(first_state["call_frames"]) == 1
    failed_frame_id = next(iter(first_state["call_frames"]))
    assert failed_frame_id == "root.run_review_loop::visit::1"
    failed_frame_bytes = _canonical_json_bytes(
        first_state["call_frames"][failed_frame_id]
    )
    expected_retry_id = f"{failed_frame_id}::retry::1"
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / "child-retry-ready.txt").write_text("ready\n", encoding="utf-8")
    child_default_resume_calls: list[dict] = []
    constructor_calls: list[tuple[str, Any, str | None]] = []

    def _default_resume_decision(executor, state, *, restart_node_id):
        if isinstance(executor.state_manager, StateManager):
            return {
                "mode": "LEXICAL_CHECKPOINT_DEFAULT",
                "restore_decision": "RESTORED",
                "restore_candidate": {
                    "kind": "RESTORED",
                    "restore_payload": {},
                    "diagnostics": [],
                },
                "selection_reason": "validated_prior_boundary",
                "diagnostics": [],
            }
        child_default_resume_calls.append(state)
        return {
            "mode": "FAIL_CLOSED",
            "restore_decision": None,
            "diagnostics": ["lexical_default_resume_prior_boundary_missing"],
        }

    def construct_manager(*args: Any, **kwargs: Any) -> Any:
        constructor_calls.append(
            (
                kwargs["frame_id"],
                kwargs["existing_frame"],
                kwargs.get("result_persistence_profile"),
            )
        )
        return _CallFrameStateManager(*args, **kwargs)

    with patch.object(
        WorkflowExecutor,
        "_determine_resume_default_resume_decision",
        _default_resume_decision,
    ), patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
        side_effect=construct_manager,
    ):
        resumed_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed_state["status"] == "completed"
    assert child_default_resume_calls == []
    assert set(resumed_state["call_frames"]) == {
        failed_frame_id,
        expected_retry_id,
    }
    assert constructor_calls == [
        (
            expected_retry_id,
            None,
            DERIVED_PURE_REPLAY_PROFILE,
        )
    ]
    assert _canonical_json_bytes(
        resumed_state["call_frames"][failed_frame_id]
    ) == failed_frame_bytes
    assert _canonical_json_bytes(
        state_manager.load().to_dict()["call_frames"][failed_frame_id]
    ) == failed_frame_bytes
    retry_frame = resumed_state["call_frames"][expected_retry_id]
    assert retry_frame["status"] == "completed"
    assert retry_frame["bound_input_resume_validation"] == {
        "status": "fresh",
        "diagnostics": [],
    }
    assert (
        retry_frame["state"]["result_persistence_profile"]
        == DERIVED_PURE_REPLAY_PROFILE
    )


def test_call_outputs_publish_into_caller_lineage_with_outer_producer(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.5",
            "name": "call-demo",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "artifacts": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "steps": [
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                    "with": {
                        "max_cycles": 3,
                        "write_root": "state/review-loop",
                    },
                    "publishes": [{"artifact": "approved", "from": "approved"}],
                },
                {
                    "name": "ReadApproved",
                    "id": "read_approved",
                    "consumes": [
                        {
                            "artifact": "approved",
                            "producers": ["RunReviewLoop"],
                            "policy": "latest_successful",
                            "freshness": "any",
                        }
                    ],
                    "consume_bundle": {"path": "state/approved_bundle.json"},
                    "command": ["bash", "-lc", "cat state/approved_bundle.json"],
                },
            ],
        },
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(tmp_path, run_id="call-lineage")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    state = executor.execute()
    persisted = state_manager.load().to_dict()

    assert state["status"] == "completed"
    assert json.loads(state["steps"]["ReadApproved"]["output"]) == {"approved": True}

    versions = persisted.get("artifact_versions", {}).get("approved", [])
    assert len(versions) == 1
    assert versions[0]["producer"] == "root.run_review_loop"
    assert versions[0]["producer_name"] == "RunReviewLoop"
    assert versions[0]["value"] is True
    assert versions[0]["source_provenance"] == {
        "source_ref": "root.steps.SetApproved.artifacts.approved",
        "source_step_id": "root.set_approved",
        "source_step_name": "SetApproved",
    }

    consumes = persisted.get("artifact_consumes", {}).get("root.read_approved", {})
    assert consumes.get("approved") == 1


def test_call_keeps_callee_context_defaults_isolated_from_caller(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "context": {
                "decision": "child",
            },
            "steps": [
                {
                    "name": "DoWork",
                    "id": "do_work",
                    "command": ["echo", "ok"],
                }
            ],
        },
    )

    state, persisted = _run_workflow(
        tmp_path,
        {
            "version": "2.5",
            "name": "call-context-isolation",
            "context": {
                "decision": "parent",
            },
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "steps": [
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                },
                {
                    "name": "ReadParentContext",
                    "id": "read_parent_context",
                    "command": ["bash", "-lc", "printf '%s' '${context.decision}'"],
                },
            ],
        },
        run_id="call-context-isolation",
    )

    assert state["status"] == "completed"
    assert state["steps"]["ReadParentContext"]["output"] == "parent"
    assert persisted["context"] == {"decision": "parent"}

    frame = next(iter(persisted["call_frames"].values()))
    assert frame["state"]["context"] == {"decision": "child"}
    assert frame["bound_inputs"] == {}


def test_call_repeat_until_provider_defaults_use_callee_context(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop.yaml",
        {
            "version": "2.7",
            "name": "review-loop",
            "context": {
                "workflow_model": "gpt-5.4",
                "workflow_effort": "high",
            },
            "inputs": {
                "state_root": {
                    "kind": "relpath",
                    "type": "relpath",
                }
            },
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {
                        "ref": "root.steps.ReviewLoop.artifacts.review_decision",
                    },
                }
            },
            "providers": {
                "reviewer": {
                    "command": [
                        "fake-reviewer",
                        "--model",
                        "${model}",
                        "--effort",
                        "${effort}",
                    ],
                    "input_mode": "stdin",
                    "defaults": {
                        "model": "${context.workflow_model}",
                        "effort": "${context.workflow_effort}",
                    },
                }
            },
            "steps": [
                {
                    "name": "Initialize",
                    "id": "initialize",
                    "command": [
                        "bash",
                        "-lc",
                        "mkdir -p \"${inputs.state_root}\"",
                    ],
                },
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "review_iteration",
                        "max_iterations": 2,
                        "outputs": {
                            "review_decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.Review.artifacts.review_decision",
                                },
                            }
                        },
                        "condition": {
                            "compare": {
                                "left": {
                                    "ref": "self.outputs.review_decision",
                                },
                                "op": "eq",
                                "right": "APPROVE",
                            }
                        },
                        "steps": [
                            {
                                "name": "Review",
                                "id": "review",
                                "provider": "reviewer",
                                "expected_outputs": [
                                    {
                                        "name": "review_decision",
                                        "path": "${inputs.state_root}/decision.txt",
                                        "type": "enum",
                                        "allowed": ["APPROVE", "REVISE"],
                                    }
                                ],
                            }
                        ],
                    },
                },
            ],
        },
    )

    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "call-repeat-until-provider-context",
            "imports": {"review_loop": "workflows/library/review_loop.yaml"},
            "steps": [
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                    "with": {
                        "state_root": "state/review-loop",
                    },
                }
            ],
        },
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(tmp_path, run_id="call-repeat-until-provider-context")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    captured_commands: list[list[str]] = []

    def _execute(_self, invocation, **_kwargs):
        captured_commands.append(list(invocation.command))
        decision_path = tmp_path / "state" / "review-loop" / "decision.txt"
        decision_path.parent.mkdir(parents=True, exist_ok=True)
        decision_path.write_text("APPROVE\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    with patch.object(ProviderExecutor, "execute", _execute):
        state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert captured_commands == [["fake-reviewer", "--model", "gpt-5.4", "--effort", "high"]]


def test_call_uses_bound_inputs_when_legacy_ref_is_corrupted(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(version="2.7"),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "bound-call-inputs",
            "imports": {"review_loop": "workflows/library/review_loop_fixture.yaml"},
            "artifacts": {
                "max_cycles": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "steps": [
                {
                    "name": "WriteMaxCycles",
                    "id": "write_max_cycles",
                    "set_scalar": {
                        "artifact": "max_cycles",
                        "value": 3,
                    },
                },
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                    "with": {
                        "max_cycles": {"ref": "root.steps.WriteMaxCycles.artifacts.max_cycles"},
                        "write_root": "state/review-loop",
                    },
                },
            ],
        },
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    state_manager = StateManager(tmp_path, run_id="bound-call-inputs")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager)
    step = dict(executor._runtime_step_for_node_id("root.run_review_loop"))
    step["with"] = {
        "max_cycles": {"ref": "root.steps.Missing.artifacts.max_cycles"},
        "write_root": "state/review-loop",
    }

    assert executor._call_input_bindings(step)["max_cycles"] != step["with"]["max_cycles"]
    state = executor.execute(on_error="continue")

    assert state["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}


def test_call_debug_exports_use_bound_output_addresses_when_surface_ref_is_corrupted(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    imported_bundle = bundle.imports["review_loop"]
    assert not hasattr(imported_bundle.surface.outputs["approved"], "raw")

    state_manager = StateManager(tmp_path, run_id="bound-call-output-provenance")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    executor = WorkflowExecutor(bundle, tmp_path, state_manager)
    state = executor.execute()
    persisted = state_manager.load().to_dict()
    frame_id, frame = next(iter(persisted["call_frames"].items()))

    debug_payload = executor.call_executor.build_debug_payload(
        frame_id=frame_id,
        step=materialize_projection_body_steps(bundle)[0],
        imported_workflow=imported_bundle,
        child_state=frame["state"],
    )

    assert state["status"] == "completed"
    assert debug_payload["exports"]["approved"] == {
        "source_ref": "root.steps.SetApproved.artifacts.approved",
        "source_step_id": "root.set_approved",
        "source_step_name": "SetApproved",
    }


def test_projection_resume_call_frame_selects_one_current_callee_and_recurses(
    tmp_path: Path,
) -> None:
    """Execute root and middle call boundaries while recording current selection.

    The real `CallExecutor.execute_call` path delegates
    `workflow_import_bundle(parent_bundle, alias)` first for root -> middle and
    recursively for middle -> leaf.  Each selected bundle's projection owns
    the next call scope or leaf-local step scope.
    """
    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    manager = StateManager(tmp_path, run_id="projection-current-callee-selection")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    root_executor = WorkflowExecutor(root_bundle, tmp_path, manager)
    state = manager.load().to_dict()
    selections: list[dict] = []
    execution_scopes: list[str] = []
    original_execute_call = CallExecutor.execute_call

    def record_import_selection(parent_bundle, alias):
        selected = workflow_import_bundle(parent_bundle, alias)
        assert selected is not None
        selections.append(
            {
                "parent": parent_bundle.surface.name,
                "alias": alias,
                "parent_call_boundaries": tuple(
                    parent_bundle.projection.call_boundaries
                ),
                "selected": selected.surface.name,
                "selected_call_boundaries": tuple(
                    selected.projection.call_boundaries
                ),
                "selected_step_ids": tuple(selected.projection.node_id_by_step_id),
            }
        )
        return selected

    def record_execute_call(call_executor, step, state, **kwargs):
        execution_scopes.append(call_executor.executor.workflow_name)
        return original_execute_call(call_executor, step, state, **kwargs)

    with patch(
        "orchestrator.workflow.calls.workflow_import_bundle",
        new=record_import_selection,
    ), patch.object(
        CallExecutor,
        "execute_call",
        record_execute_call,
    ):
        result = root_executor.call_executor.execute_call(
            materialize_projection_body_steps(root_bundle)[0],
            state,
        )

    assert result["status"] == "completed"
    assert result["artifacts"] == {"ready": True}
    assert execution_scopes == ["projection-root", "projection-middle"]
    assert selections == [
        {
            "parent": "projection-root",
            "alias": "middle",
            "parent_call_boundaries": ("root.invoke_middle",),
            "selected": "projection-middle",
            "selected_call_boundaries": ("root.invoke_leaf",),
            "selected_step_ids": ("root.invoke_leaf",),
        },
        {
            "parent": "projection-middle",
            "alias": "leaf",
            "parent_call_boundaries": ("root.invoke_leaf",),
            "selected": "projection-leaf",
            "selected_call_boundaries": (),
            "selected_step_ids": ("root.set_ready",),
        },
    ]


def test_projection_integrity_loop_contained_call_uses_exact_boundary_candidate(
    tmp_path: Path,
) -> None:
    _write_yaml(
        tmp_path / "imports" / "child.yaml",
        {
            "version": "2.5",
            "name": "loop-child",
            "artifacts": {
                "ready": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "outputs": {
                "ready": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.SetReady.artifacts.ready"},
                }
            },
            "steps": [
                {
                    "name": "SetReady",
                    "id": "set_ready",
                    "set_scalar": {
                        "artifact": "ready",
                        "value": True,
                    },
                }
            ],
        },
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.5",
            "name": "loop-contained-call-resume",
            "imports": {"child": "imports/child.yaml"},
            "steps": [
                {
                    "name": "ResumeGate",
                    "id": "resume_gate",
                    "command": ["bash", "-lc", "test -f state/resume-ready.txt"],
                },
                {
                    "name": "ReviewItems",
                    "id": "review_items",
                    "for_each": {
                        "items": ["only-item"],
                        "as": "item",
                        "steps": [
                            {
                                "name": "InvokeChild",
                                "id": "invoke_child",
                                "call": "child",
                            }
                        ],
                    },
                },
            ],
        },
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    manager = StateManager(tmp_path, run_id="loop-contained-call-exact-candidate")
    manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    first = WorkflowExecutor(bundle, tmp_path, manager).execute()
    assert first["status"] == "failed"
    assert first.get("call_frames", {}) == {}

    boundary = next(
        boundary
        for boundary in bundle.projection.call_boundaries.values()
        if boundary.iteration_owner_node_id is not None
    )
    expected_call_step_id = bundle.projection.call_boundary_runtime_step_id(
        boundary.node_id,
        iteration_index=0,
    )
    observed_resolutions: list[tuple[str, int, str | None]] = []
    projection_type = type(bundle.projection)
    original_resolve_call_boundary = projection_type.resolve_call_boundary

    def record_exact_resolution(projection, slot_index, call_step_id):
        resolution = original_resolve_call_boundary(
            projection,
            slot_index,
            call_step_id,
        )
        if call_step_id == expected_call_step_id:
            observed_resolutions.append(
                (
                    call_step_id,
                    resolution.candidate_count,
                    resolution.boundary.node_id
                    if resolution.boundary is not None
                    else None,
                )
            )
        return resolution

    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / "resume-ready.txt").write_text(
        "ready\n",
        encoding="utf-8",
    )
    with patch.object(
        projection_type,
        "resolve_call_boundary",
        record_exact_resolution,
    ):
        resumed = WorkflowExecutor(bundle, tmp_path, manager).execute(resume=True)

    assert resumed["status"] == "completed"
    assert observed_resolutions == [
        (expected_call_step_id, 1, boundary.node_id),
    ]
    assert tuple(resumed["call_frames"]) == (
        f"{expected_call_step_id}::visit::1",
    )
    assert resumed["steps"]["ReviewItems[0].InvokeChild"]["step_id"] == (
        expected_call_step_id
    )


def test_projection_resume_call_frame_unknown_alias_fails_before_frame_or_effect(
    tmp_path: Path,
) -> None:
    """Exercise `CallExecutor.execute_call` rather than import-map inspection.

    An unknown current call alias returns one deterministic contract failure
    before `frame_id_with_overrides`, `_CallFrameStateManager`, child
    `WorkflowExecutor`, or any persisted run-tree mutation.
    """
    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    manager = StateManager(tmp_path, run_id="projection-unknown-alias")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(root_bundle, tmp_path, manager)
    executor.resume_mode = True
    step = dict(materialize_projection_body_steps(root_bundle)[0])
    step["call"] = "missing"
    state = manager.load().to_dict()
    before_state = json.loads(json.dumps(state))
    before_tree = _projection_run_tree_snapshot(manager.run_root)

    def unexpected_boundary(*_args, **_kwargs):
        raise AssertionError("unknown alias reached frame or child construction")

    with patch.object(
        executor.call_executor,
        "frame_id_with_overrides",
        side_effect=unexpected_boundary,
    ) as frame_selection, patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
        side_effect=unexpected_boundary,
    ) as frame_construction, patch(
        "orchestrator.workflow.executor.WorkflowExecutor",
        side_effect=unexpected_boundary,
    ) as child_construction:
        result = executor.call_executor.execute_call(step, state)

    assert result["error"]["type"] == "contract_violation"
    assert result["error"]["context"] == {
        "step": "InvokeMiddle",
        "reason": "unknown_import_alias",
        "call": "missing",
    }
    frame_selection.assert_not_called()
    frame_construction.assert_not_called()
    child_construction.assert_not_called()
    assert state == before_state
    assert _projection_run_tree_snapshot(manager.run_root) == before_tree


def test_projection_resume_call_frame_ambiguity_fails_without_mapping_order_selection(
    tmp_path: Path,
) -> None:
    """Non-Workflow-Lisp duplicate candidates fail instead of selecting by order."""
    from orchestrator.workflow.resume_projection_integrity import (
        CallFrameRetryLineageError,
    )

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    manager = StateManager(tmp_path, run_id="projection-call-ambiguity")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(root_bundle, tmp_path, manager)
    executor.resume_mode = True
    step = materialize_projection_body_steps(root_bundle)[0]
    state = {
        "call_frames": {
            "frame-first": {
                "status": "running",
                "call_step_id": "root.invoke_middle",
                "import_alias": "middle",
            },
            "frame-second": {
                "status": "failed",
                "call_step_id": "root.invoke_middle",
                "import_alias": "middle",
            },
        },
        "step_visits": {"InvokeMiddle": 1},
    }

    with pytest.raises(CallFrameRetryLineageError) as exc_info:
        executor.call_executor.frame_id_with_overrides(
            step,
            state,
            step_name="InvokeMiddle",
            step_id="root.invoke_middle",
        )

    assert exc_info.value.reason == "ambiguous_resumable_call_frame"


@pytest.mark.parametrize(
    "persisted_call_step_id",
    [
        pytest.param("root.run_review_loop", id="matching-caller"),
        pytest.param("root.stale_call", id="stale-caller"),
        pytest.param(None, id="missing-caller"),
    ],
)
def test_occupied_completed_call_frame_collision_rejects_before_lineage_grouping(
    tmp_path: Path,
    persisted_call_step_id: str | None,
) -> None:
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    state_manager = StateManager(tmp_path, run_id="completed-frame-id-collision")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    completed_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    frame_id = "root.run_review_loop::visit::1"

    assert completed_state["step_visits"]["RunReviewLoop"] == 1
    assert completed_state["call_frames"][frame_id]["status"] == "completed"
    if persisted_call_step_id is None:
        completed_state["call_frames"][frame_id].pop("call_step_id")
    else:
        completed_state["call_frames"][frame_id][
            "call_step_id"
        ] = persisted_call_step_id

    resume_executor = WorkflowExecutor(bundle, tmp_path, state_manager)
    resume_executor.resume_mode = True
    step = materialize_projection_body_steps(bundle)[0]
    before_frames = dict(completed_state["call_frames"])

    with patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager"
    ) as child_manager, patch(
        "orchestrator.workflow.executor.WorkflowExecutor"
    ) as child_executor:
        child_executor.return_value.execute.return_value = {
            "status": "completed",
            "workflow_outputs": {},
        }
        result = resume_executor.call_executor.execute_call(step, completed_state)

    assert result["status"] == "failed"
    assert result["error"]["context"] == {
        "step": "RunReviewLoop",
        "call": "review_loop",
        "call_frame_id": frame_id,
        "reason": "call_resume_state_invalid",
        "detail": "completed_call_frame_id_collision",
    }
    child_manager.assert_not_called()
    child_executor.assert_not_called()
    assert completed_state["call_frames"] == before_frames


def _retry_lineage_frame(
    *,
    status: str,
    call_step_id: str = "root.invoke_child",
    import_alias: str = "child",
) -> dict:
    return {
        "status": status,
        "call_step_id": call_step_id,
        "import_alias": import_alias,
    }


def test_call_frame_retry_lineage_indexes_failed_history_and_next_id() -> None:
    from orchestrator.workflow.resume_projection_integrity import (
        index_retry_lineage,
        next_unused_retry_frame_id,
    )

    base_frame_id = "root.invoke_child::visit::7"
    completed_history = [
        (
            f"root.invoke_child::visit::{visit}",
            _retry_lineage_frame(status="completed"),
        )
        for visit in range(101, 201)
    ]
    completed_history.append(
        (
            f"{base_frame_id}::retry::3",
            _retry_lineage_frame(status="completed"),
        )
    )
    lineage = index_retry_lineage(
        "root.invoke_child",
        [
            *completed_history,
            (
                f"{base_frame_id}::retry::2",
                _retry_lineage_frame(status="failed"),
            ),
            (base_frame_id, _retry_lineage_frame(status="failed")),
            (
                f"{base_frame_id}::retry::1",
                _retry_lineage_frame(status="failed"),
            ),
        ],
        frontend_kind="workflow_lisp",
    )

    assert lineage.base_frame_id == base_frame_id
    assert len(lineage.completed_members) == 101
    assert [
        (member.frame_id, member.ordinal)
        for member in lineage.failed_predecessors
    ] == [
        (base_frame_id, 0),
        (f"{base_frame_id}::retry::1", 1),
        (f"{base_frame_id}::retry::2", 2),
    ]
    assert lineage.running_member is None
    assert next_unused_retry_frame_id(lineage) == f"{base_frame_id}::retry::4"
    assert next_unused_retry_frame_id(lineage) == f"{base_frame_id}::retry::4"


def test_call_frame_retry_lineage_allows_one_running_member_with_failed_history() -> None:
    from orchestrator.workflow.resume_projection_integrity import (
        RetryFrameMember,
        index_retry_lineage,
    )

    base_frame_id = "root.invoke_child::visit::3"
    lineage = index_retry_lineage(
        "root.invoke_child",
        [
            (
                f"{base_frame_id}::retry::1",
                _retry_lineage_frame(status="failed"),
            ),
            (
                f"{base_frame_id}::retry::2",
                _retry_lineage_frame(status="running"),
            ),
            (base_frame_id, _retry_lineage_frame(status="failed")),
        ],
        frontend_kind="workflow_lisp",
    )

    assert [member.ordinal for member in lineage.failed_predecessors] == [0, 1]
    assert isinstance(lineage.running_member, RetryFrameMember)
    assert lineage.running_member.frame_id == f"{base_frame_id}::retry::2"
    assert lineage.running_member.ordinal == 2


@pytest.mark.parametrize(
    ("frontend_kind", "invalid_lineage", "expected_reason"),
    [
        pytest.param(
            "workflow_lisp",
            [
                ("base", _retry_lineage_frame(status="running")),
                ("base::retry::1", _retry_lineage_frame(status="running")),
            ],
            "ambiguous_resumable_call_frame",
            id="multiple-running",
        ),
        pytest.param(
            "workflow_lisp",
            [
                ("base-a", _retry_lineage_frame(status="failed")),
                ("base-b::retry::1", _retry_lineage_frame(status="failed")),
            ],
            "ambiguous_resumable_call_frame",
            id="mixed-bases",
        ),
        pytest.param(
            "workflow_lisp",
            [
                ("base", _retry_lineage_frame(status="failed")),
                ("base", _retry_lineage_frame(status="failed")),
            ],
            "ambiguous_resumable_call_frame",
            id="duplicate-ordinal",
        ),
        pytest.param(
            "workflow_lisp",
            [
                ("base", _retry_lineage_frame(status="failed")),
                ("base::retry::2", _retry_lineage_frame(status="failed")),
            ],
            "unsupported_shape",
            id="missing-ordinal",
        ),
        pytest.param(
            "workflow_lisp",
            [
                ("base", _retry_lineage_frame(status="failed")),
                ("base::retry::zero", _retry_lineage_frame(status="failed")),
            ],
            "unsupported_shape",
            id="malformed-ordinal",
        ),
        pytest.param(
            "workflow_lisp",
            [
                ("base", _retry_lineage_frame(status="failed")),
                (
                    "base::retry::1::retry::2",
                    _retry_lineage_frame(status="failed"),
                ),
            ],
            "unsupported_shape",
            id="nested-retry-marker",
        ),
        pytest.param(
            "workflow_lisp",
            [
                (
                    "base",
                    _retry_lineage_frame(
                        status="failed",
                        call_step_id="root.other_child",
                    ),
                ),
            ],
            "missing_call_boundary",
            id="caller-mismatch",
        ),
        pytest.param(
            "workflow_lisp",
            [
                ("base", _retry_lineage_frame(status="failed")),
                (
                    "base::retry::1",
                    _retry_lineage_frame(
                        status="failed",
                        import_alias="other_child",
                    ),
                ),
            ],
            "persisted_import_alias_mismatch",
            id="alias-mismatch",
        ),
        pytest.param(
            "workflow_lisp",
            [("base", _retry_lineage_frame(status="paused"))],
            "unsupported_shape",
            id="unknown-status",
        ),
        pytest.param(
            None,
            [
                ("first", _retry_lineage_frame(status="running")),
                ("second", _retry_lineage_frame(status="failed")),
            ],
            "ambiguous_resumable_call_frame",
            id="non-workflow-lisp-multiple-noncompleted",
        ),
    ],
)
def test_call_frame_retry_lineage_rejects_ambiguity_and_malformed_ordinals(
    frontend_kind: str | None,
    invalid_lineage: list[tuple[str, dict]],
    expected_reason: str,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import (
        CallFrameRetryLineageError,
        index_retry_lineage,
    )

    with pytest.raises(CallFrameRetryLineageError) as exc_info:
        index_retry_lineage(
            "root.invoke_child",
            invalid_lineage,
            frontend_kind=frontend_kind,
        )

    assert exc_info.value.reason == expected_reason


def test_workflow_lisp_retry_classification_uses_typed_frontend_kind_not_suffix(
    tmp_path: Path,
) -> None:
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.5",
            "name": "typed-frontend-classification",
            "steps": [
                {
                    "name": "Done",
                    "id": "done",
                    "command": ["bash", "-lc", "true"],
                }
            ],
        },
    )
    yaml_bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    typed_lisp_bundle = replace(
        yaml_bundle,
        provenance=replace(
            yaml_bundle.provenance,
            frontend_kind="workflow_lisp",
        ),
    )
    suffix_only_bundle = replace(
        yaml_bundle,
        provenance=replace(
            yaml_bundle.provenance,
            workflow_path=tmp_path / "misleading.orc",
            frontend_kind=None,
        ),
    )

    assert CallExecutor._is_workflow_lisp_target(typed_lisp_bundle) is True
    assert CallExecutor._is_workflow_lisp_target(suffix_only_bundle) is False


def test_reached_call_revalidates_boundary_alias_and_lineage_before_child_manager(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import audit_scope as real_audit_scope

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    manager = StateManager(tmp_path, run_id="reached-call-boundary-lineage")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(root_bundle, tmp_path, manager)
    executor.resume_mode = True
    frame_id = "root.invoke_middle::visit::1"
    state = manager.load().to_dict()
    state["step_visits"] = {"InvokeMiddle": 1}
    state["call_frames"] = {
        frame_id: _projection_call_frame(
            manager,
            middle_bundle,
            frame_id=frame_id,
            status="running",
            call_step_id="root.invoke_middle",
            import_alias="middle_duplicate_alias",
        )
    }
    events: list[str] = []
    original_import = workflow_import_bundle
    original_resolve = executor.call_executor.resolve_bound_inputs

    def record_import(parent_bundle, alias):
        events.append("bundle")
        return original_import(parent_bundle, alias)

    def record_authored_inputs(*args, **kwargs):
        events.append("authored_inputs")
        return original_resolve(*args, **kwargs)

    def record_lineage(bundle, audited_state, scope_path):
        events.append("lineage")
        return real_audit_scope(bundle, audited_state, scope_path)

    with patch(
        "orchestrator.workflow.calls.workflow_import_bundle",
        side_effect=record_import,
    ), patch.object(
        executor.call_executor,
        "resolve_bound_inputs",
        side_effect=record_authored_inputs,
    ), patch(
        "orchestrator.workflow.calls.audit_scope",
        side_effect=record_lineage,
        create=True,
    ), patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
    ) as child_manager, patch(
        "orchestrator.workflow.executor.WorkflowExecutor",
    ) as child_executor:
        child_manager.return_value._snapshot.return_value = state["call_frames"][frame_id]
        child_executor.return_value.execute.return_value = {
            "status": "completed",
            "workflow_outputs": {},
        }
        result = executor.call_executor.execute_call(
            materialize_projection_body_steps(root_bundle)[0],
            state,
        )

    assert events == ["bundle", "authored_inputs", "lineage"]
    assert result["error"]["type"] == "resume_projection_integrity_error"
    assert result["error"]["context"]["reason"] == "persisted_import_alias_mismatch"
    child_manager.assert_not_called()
    child_executor.assert_not_called()


def test_reached_call_checksum_precedes_local_projection_failure(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import audit_scope as real_audit_scope

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    leaf_bundle = workflow_import_bundle(middle_bundle, "leaf")
    assert leaf_bundle is not None
    manager = StateManager(tmp_path, run_id="reached-call-checksum-precedence")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(middle_bundle, tmp_path, manager)
    executor.resume_mode = True
    frame_id = "root.invoke_leaf::visit::1"
    state = manager.load().to_dict()
    state["step_visits"] = {"InvokeLeaf": 1}
    frame = _projection_call_frame(
        manager,
        leaf_bundle,
        frame_id=frame_id,
        status="running",
        call_step_id="root.invoke_leaf",
        import_alias="leaf",
        current_step_id="root.removed_leaf_step",
        checksum="sha256:" + ("0" * 64),
    )
    state["call_frames"] = {frame_id: frame}
    child_audits: list[str] = []

    def record_audit(bundle, audited_state, scope_path):
        if scope_path.call_frame_ids:
            child_audits.append(scope_path.call_frame_ids[-1])
        return real_audit_scope(bundle, audited_state, scope_path)

    with patch(
        "orchestrator.workflow.calls.audit_scope",
        side_effect=record_audit,
        create=True,
    ), patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
    ) as child_manager:
        checksum_result = executor.call_executor.execute_call(
            materialize_projection_body_steps(middle_bundle)[0],
            state,
        )

    assert checksum_result["error"]["type"] == "call_resume_checksum_mismatch"
    assert child_audits == []
    child_manager.assert_not_called()

    provenance = workflow_provenance(leaf_bundle)
    assert provenance is not None
    frame["state"]["workflow_checksum"] = manager.calculate_checksum(
        provenance.workflow_path
    )
    with patch(
        "orchestrator.workflow.calls.audit_scope",
        side_effect=record_audit,
        create=True,
    ), patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
    ) as repaired_child_manager:
        projection_result = executor.call_executor.execute_call(
            materialize_projection_body_steps(middle_bundle)[0],
            state,
        )

    assert projection_result["error"]["type"] == "resume_projection_integrity_error"
    assert projection_result["error"]["context"]["reason"] == "out_of_scope_step_id"
    assert child_audits == [frame_id]
    repaired_child_manager.assert_not_called()


def test_reached_call_running_workflow_lisp_guards_precede_failed_history_audit(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import audit_scope as real_audit_scope

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    middle_bundle = _typed_workflow_lisp_import(middle_bundle, "leaf")
    leaf_bundle = workflow_import_bundle(middle_bundle, "leaf")
    assert leaf_bundle is not None
    manager = StateManager(tmp_path, run_id="reached-call-running-wfl-order")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(middle_bundle, tmp_path, manager)
    executor.resume_mode = True
    base_frame_id = "root.invoke_leaf::visit::1"
    running_frame_id = f"{base_frame_id}::retry::1"
    state = manager.load().to_dict()
    state["step_visits"] = {"InvokeLeaf": 1}
    state["call_frames"] = {
        base_frame_id: _projection_call_frame(
            manager,
            leaf_bundle,
            frame_id=base_frame_id,
            status="failed",
            call_step_id="root.invoke_leaf",
            import_alias="leaf",
            current_step_id="root.stale_failed_history",
        ),
        running_frame_id: _projection_call_frame(
            manager,
            leaf_bundle,
            frame_id=running_frame_id,
            status="running",
            call_step_id="root.invoke_leaf",
            import_alias="leaf",
            checksum="sha256:" + ("0" * 64),
        ),
    }
    child_audits: list[str] = []

    def record_audit(bundle, audited_state, scope_path):
        if scope_path.call_frame_ids:
            child_audits.append(scope_path.call_frame_ids[-1])
        return real_audit_scope(bundle, audited_state, scope_path)

    with patch(
        "orchestrator.workflow.calls.audit_scope",
        side_effect=record_audit,
        create=True,
    ), patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
    ) as child_manager:
        result = executor.call_executor.execute_call(
            materialize_projection_body_steps(middle_bundle)[0],
            state,
        )

    assert result["error"]["type"] == "call_resume_checksum_mismatch"
    assert result["error"]["context"]["call_frame_id"] == running_frame_id
    assert child_audits == []
    child_manager.assert_not_called()


@pytest.mark.parametrize("status", ["running", "failed"])
@pytest.mark.parametrize(
    "winning_guard",
    ["call_resume_checksum_mismatch", "call_resume_bound_input_mismatch"],
)
def test_reached_call_non_workflow_lisp_resumable_guards_precede_local_audit(
    tmp_path: Path,
    status: str,
    winning_guard: str,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import audit_scope as real_audit_scope

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path, leaf_input=True)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    leaf_bundle = workflow_import_bundle(middle_bundle, "leaf")
    assert leaf_bundle is not None
    manager = StateManager(
        tmp_path,
        run_id=f"reached-call-non-wfl-{status}-{winning_guard}",
    )
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(middle_bundle, tmp_path, manager)
    executor.resume_mode = True
    frame_id = "root.invoke_leaf::visit::1"
    state = manager.load().to_dict()
    state["step_visits"] = {"InvokeLeaf": 1}
    frame = _projection_call_frame(
        manager,
        leaf_bundle,
        frame_id=frame_id,
        status=status,
        call_step_id="root.invoke_leaf",
        import_alias="leaf",
        bound_inputs={
            "token": (
                8
                if winning_guard == "call_resume_bound_input_mismatch"
                else 7
            )
        },
        current_step_id="root.removed_leaf_step",
        checksum=(
            "sha256:" + ("0" * 64)
            if winning_guard == "call_resume_checksum_mismatch"
            else None
        ),
    )
    state["call_frames"] = {frame_id: frame}
    child_audits: list[str] = []
    guard_events: list[str] = []
    original_checksum = executor.call_executor.validate_resume_checksum
    original_bound_inputs = executor.call_executor.validate_resume_bound_inputs

    def record_audit(bundle, audited_state, scope_path):
        if scope_path.call_frame_ids:
            child_audits.append(scope_path.call_frame_ids[-1])
        return real_audit_scope(bundle, audited_state, scope_path)

    def record_checksum(*args, **kwargs):
        guard_events.append("checksum")
        return original_checksum(*args, **kwargs)

    def record_bound_inputs(*args, **kwargs):
        guard_events.append("bound_inputs")
        return original_bound_inputs(*args, **kwargs)

    with patch(
        "orchestrator.workflow.calls.audit_scope",
        side_effect=record_audit,
        create=True,
    ), patch.object(
        executor.call_executor,
        "validate_resume_checksum",
        side_effect=record_checksum,
    ), patch.object(
        executor.call_executor,
        "validate_resume_bound_inputs",
        side_effect=record_bound_inputs,
    ), patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
    ) as child_manager:
        result = executor.call_executor.execute_call(
            materialize_projection_body_steps(middle_bundle)[0],
            state,
        )

    assert result["error"]["type"] == winning_guard
    assert guard_events == (
        ["checksum"]
        if winning_guard == "call_resume_checksum_mismatch"
        else ["checksum", "bound_inputs"]
    )
    assert child_audits == []
    child_manager.assert_not_called()


def test_reached_call_fresh_retry_audits_all_failed_history_before_allocation(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import audit_scope as real_audit_scope

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    middle_bundle = _typed_workflow_lisp_import(middle_bundle, "leaf")
    leaf_bundle = workflow_import_bundle(middle_bundle, "leaf")
    assert leaf_bundle is not None
    manager = StateManager(tmp_path, run_id="reached-call-fresh-retry-order")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(middle_bundle, tmp_path, manager)
    executor.resume_mode = True
    base_frame_id = "root.invoke_leaf::visit::1"
    predecessor_ids = [base_frame_id, f"{base_frame_id}::retry::1"]
    state = manager.load().to_dict()
    state["step_visits"] = {"InvokeLeaf": 1}
    state["call_frames"] = {
        frame_id: _projection_call_frame(
            manager,
            leaf_bundle,
            frame_id=frame_id,
            status="failed",
            call_step_id="root.invoke_leaf",
            import_alias="leaf",
        )
        for frame_id in reversed(predecessor_ids)
    }
    events: list[str] = []
    original_import = workflow_import_bundle
    original_resolve = executor.call_executor.resolve_bound_inputs
    original_finalize = executor.call_executor.finalize_bound_inputs
    original_write_root = executor.call_executor.validate_write_root_bindings
    original_checksum = executor.call_executor.validate_resume_checksum

    def record_import(parent_bundle, alias):
        events.append("bundle")
        return original_import(parent_bundle, alias)

    def record_authored_inputs(*args, **kwargs):
        events.append("authored_inputs")
        return original_resolve(*args, **kwargs)

    def record_finalize(*args, **kwargs):
        events.append("finalized_inputs")
        return original_finalize(*args, **kwargs)

    def record_write_root(*args, **kwargs):
        events.append("write_root")
        return original_write_root(*args, **kwargs)

    def record_checksum(*args, **kwargs):
        events.append(f"checksum:{kwargs['frame_id']}")
        return original_checksum(*args, **kwargs)

    def record_audit(bundle, audited_state, scope_path):
        if scope_path.call_frame_ids:
            events.append(f"audit:{scope_path.call_frame_ids[-1]}")
        else:
            events.append("lineage")
        return real_audit_scope(bundle, audited_state, scope_path)

    def allocate(lineage, provisional_frame_id, **_kwargs):
        events.append("allocation")
        return provisional_frame_id

    def construct_manager(*args, **kwargs):
        events.append("child_manager")
        manager_mock = SimpleNamespace(
            update_bound_input_resume_validation=lambda **_kwargs: None,
            _snapshot=lambda: {},
        )
        return manager_mock

    def construct_executor(*args, **kwargs):
        events.append("child_executor")
        return SimpleNamespace(
            execute=lambda **_kwargs: {
                "status": "completed",
                "workflow_outputs": {},
            }
        )

    with patch(
        "orchestrator.workflow.calls.workflow_import_bundle",
        side_effect=record_import,
    ), patch.object(
        executor.call_executor,
        "resolve_bound_inputs",
        side_effect=record_authored_inputs,
    ), patch.object(
        executor.call_executor,
        "finalize_bound_inputs",
        side_effect=record_finalize,
    ), patch.object(
        executor.call_executor,
        "validate_write_root_bindings",
        side_effect=record_write_root,
    ), patch.object(
        executor.call_executor,
        "validate_resume_checksum",
        side_effect=record_checksum,
    ), patch(
        "orchestrator.workflow.calls.audit_scope",
        side_effect=record_audit,
        create=True,
    ), patch.object(
        executor.call_executor,
        "_allocate_retry_frame_id",
        side_effect=allocate,
        create=True,
    ), patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
        side_effect=construct_manager,
    ), patch(
        "orchestrator.workflow.executor.WorkflowExecutor",
        side_effect=construct_executor,
    ):
        result = executor.call_executor.execute_call(
            materialize_projection_body_steps(middle_bundle)[0],
            state,
        )

    expected_retry_id = f"{base_frame_id}::retry::2"
    assert result["status"] == "completed"
    assert events == [
        "bundle",
        "authored_inputs",
        "lineage",
        "finalized_inputs",
        "write_root",
        f"checksum:{predecessor_ids[0]}",
        f"audit:{predecessor_ids[0]}",
        f"checksum:{predecessor_ids[1]}",
        f"audit:{predecessor_ids[1]}",
        "allocation",
        "child_manager",
        "child_executor",
    ]
    assert expected_retry_id in state["call_frames"]


def test_reached_call_projection_failure_does_not_mutate_selected_callee(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import audit_scope as real_audit_scope

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    leaf_bundle = workflow_import_bundle(middle_bundle, "leaf")
    assert leaf_bundle is not None
    manager = StateManager(tmp_path, run_id="reached-call-no-selected-mutation")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(middle_bundle, tmp_path, manager)
    executor.resume_mode = True
    frame_id = "root.invoke_leaf::visit::1"
    state = manager.load().to_dict()
    state["step_visits"] = {"InvokeLeaf": 1}
    state["call_frames"] = {
        frame_id: _projection_call_frame(
            manager,
            leaf_bundle,
            frame_id=frame_id,
            status="running",
            call_step_id="root.invoke_leaf",
            import_alias="leaf",
            current_step_id="root.removed_leaf_step",
        )
    }
    before_state = deepcopy(state)
    before_bytes = manager.state_file.read_bytes()
    before_tree = _projection_run_tree_snapshot(manager.run_root)

    with patch(
        "orchestrator.workflow.calls.audit_scope",
        side_effect=real_audit_scope,
        create=True,
    ), patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
    ) as child_manager, patch(
        "orchestrator.workflow.executor.WorkflowExecutor",
    ) as child_executor:
        child_manager.return_value._snapshot.return_value = {}
        child_executor.return_value.execute.return_value = {
            "status": "completed",
            "workflow_outputs": {},
        }
        result = executor.call_executor.execute_call(
            materialize_projection_body_steps(middle_bundle)[0],
            state,
        )

    assert result["error"]["type"] == "resume_projection_integrity_error"
    child_manager.assert_not_called()
    child_executor.assert_not_called()
    assert state == before_state
    assert manager.state_file.read_bytes() == before_bytes
    assert _projection_run_tree_snapshot(manager.run_root) == before_tree


def test_projection_resume_call_frame_stale_caller_id_is_not_scoped_to_boundary(
    tmp_path: Path,
) -> None:
    """A stale persisted caller id is ignored and a fresh frame id is derived.

    This freezes the current gap before `CallExecutor.execute_call`: the parent
    projection is not consulted to reject the stale frame's `call_step_id`.
    """
    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    manager = StateManager(tmp_path, run_id="projection-stale-caller")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    executor = WorkflowExecutor(root_bundle, tmp_path, manager)
    executor.resume_mode = True
    state = {
        "call_frames": {
            "stale-frame": {
                "status": "running",
                "call_step_id": "root.removed_call",
            }
        },
        "step_visits": {"InvokeMiddle": 1},
    }

    selected_frame_id = executor.call_executor.frame_id_with_overrides(
        materialize_projection_body_steps(root_bundle)[0],
        state,
        step_name="InvokeMiddle",
        step_id="root.invoke_middle",
    )

    assert selected_frame_id == "root.invoke_middle::visit::1"


def test_projection_resume_call_frame_stale_callee_local_current_id_fails_closed(
    tmp_path: Path,
) -> None:
    """The selected callee projection rejects a stale local `current_step.step_id`."""
    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None

    with pytest.raises(ResumeStateIntegrityError) as exc_info:
        ResumePlanner().determine_restart_node_id(
            {
                "steps": {},
                "current_step": {
                    "status": "running",
                    "name": "InvokeLeaf",
                    "step_id": "root.removed_local_call",
                },
            },
            projection=middle_bundle.projection,
        )

    assert exc_info.value.context == {
        "step_id": "root.removed_local_call",
        "field": "step_id",
        "expected": "known projection step_id",
        "actual": "root.removed_local_call",
    }


def test_projection_resume_call_frame_nested_checksum_mismatch_precedes_child_construction(
    tmp_path: Path,
) -> None:
    """Exercise nested checksum rejection through real `CallExecutor.execute_call`.

    A persisted current leaf frame with a mismatched checksum returns the
    deterministic existing checksum failure before child-frame construction,
    child executor construction, state writes, provider/command execution, or
    any run-tree mutation.
    """
    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    leaf_bundle = workflow_import_bundle(middle_bundle, "leaf")
    assert leaf_bundle is not None
    manager = StateManager(tmp_path, run_id="projection-nested-checksum")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    middle_executor = WorkflowExecutor(middle_bundle, tmp_path, manager)
    middle_executor.resume_mode = True
    frame_id = "root.invoke_leaf::visit::1"
    persisted_checksum = "sha256:" + ("0" * 64)
    persisted = manager.load()
    persisted.call_frames = {
        frame_id: {
            "call_frame_id": frame_id,
            "call_step_name": "InvokeLeaf",
            "call_step_id": "root.invoke_leaf",
            "import_alias": "leaf",
            "status": "running",
            "bound_inputs": {},
            "state": {
                "workflow_checksum": persisted_checksum,
            },
        }
    }
    persisted.step_visits = {"InvokeLeaf": 1}
    manager._write_state()
    step = materialize_projection_body_steps(middle_bundle)[0]
    state = manager.load().to_dict()
    before_state = json.loads(json.dumps(state))
    before_state_bytes = manager.state_file.read_bytes()
    before_tree = _projection_run_tree_snapshot(manager.run_root)
    leaf_provenance = workflow_provenance(leaf_bundle)
    assert leaf_provenance is not None
    current_checksum = manager.calculate_checksum(leaf_provenance.workflow_path)

    def unexpected_boundary(*_args, **_kwargs):
        raise AssertionError("checksum mismatch reached a child or effect boundary")

    with patch(
        "orchestrator.workflow.call_frame_state._CallFrameStateManager",
        side_effect=unexpected_boundary,
    ) as frame_construction, patch(
        "orchestrator.workflow.executor.WorkflowExecutor",
        side_effect=unexpected_boundary,
    ) as child_construction, patch.object(
        manager,
        "update_call_frame",
        side_effect=unexpected_boundary,
    ) as frame_write, patch.object(
        WorkflowExecutor,
        "_execute_provider_with_context",
        side_effect=unexpected_boundary,
    ) as provider_effect, patch.object(
        WorkflowExecutor,
        "_execute_command_with_context",
        side_effect=unexpected_boundary,
    ) as command_effect:
        result = middle_executor.call_executor.execute_call(step, state)

    assert result == {
        "status": "failed",
        "exit_code": 2,
        "duration_ms": 0,
        "error": {
            "type": "call_resume_checksum_mismatch",
            "message": "Called workflow has been modified since the run started",
            "context": {
                "step": "InvokeLeaf",
                "call": "leaf",
                "call_frame_id": frame_id,
                "workflow_file": "imports/leaf.yaml",
                "persisted_checksum": persisted_checksum,
                "current_checksum": current_checksum,
                "reason": "workflow_modified",
            },
        },
    }
    frame_construction.assert_not_called()
    child_construction.assert_not_called()
    frame_write.assert_not_called()
    provider_effect.assert_not_called()
    command_effect.assert_not_called()
    assert state == before_state
    assert manager.state_file.read_bytes() == before_state_bytes
    assert _projection_run_tree_snapshot(manager.run_root) == before_tree


def test_projection_resume_call_frame_mutation_order_stale_caller_id_fails_at_root_audit(
    tmp_path: Path,
) -> None:
    """A stale caller is rejected by the root guard before call execution."""
    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    manager = StateManager(tmp_path, run_id="projection-stale-caller-mutation")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    first = WorkflowExecutor(root_bundle, tmp_path, manager).execute()
    assert first["status"] == "completed"

    persisted = manager.load()
    original_frame_id, original_frame = next(iter(persisted.call_frames.items()))
    original_frame["call_step_id"] = "root.removed_call"
    assert root_bundle.projection.call_boundaries.get(
        original_frame["call_step_id"]
    ) is None
    assert root_bundle.projection.entry_for_step_id(
        original_frame["call_step_id"]
    ) is None
    original_frame["status"] = "running"
    persisted.status = "failed"
    persisted.steps["InvokeMiddle"]["status"] = "failed"
    manager._write_state()
    before_state = manager.load().to_dict()
    before = _projection_run_tree_snapshot(manager.run_root)

    resumed = WorkflowExecutor(root_bundle, tmp_path, manager).execute(resume=True)
    after = _projection_run_tree_snapshot(manager.run_root)

    assert resumed["status"] == "failed"
    assert before != after
    assert resumed["error"]["type"] == "resume_projection_integrity_error"
    assert resumed["error"]["context"]["reason"] == "out_of_scope_step_id"
    assert resumed["error"]["context"]["field"] == (
        f"call_frames.{original_frame_id}.call_step_id"
    )
    assert resumed["call_frames"] == before_state["call_frames"]
    assert resumed["steps"] == before_state["steps"]
    assert resumed["step_visits"] == before_state["step_visits"]
    assert resumed.get("current_step") == before_state.get("current_step")
    assert not (manager.run_root / "provider_sessions").exists()


def test_projection_resume_call_frame_mutation_order_callee_local_corruption_preserves_selected_child(
    tmp_path: Path,
) -> None:
    """Parent failure records persist while the selected child stays untouched."""
    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    manager = StateManager(tmp_path, run_id="projection-callee-local-mutation")
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    first = WorkflowExecutor(root_bundle, tmp_path, manager).execute()
    assert first["status"] == "completed"

    persisted = manager.load()
    frame_id, frame = next(iter(persisted.call_frames.items()))
    child_state = frame["state"]
    child_state["status"] = "failed"
    child_state["steps"]["InvokeLeaf"]["status"] = "failed"
    child_state["current_step"] = {
        "status": "running",
        "name": "RemovedLocal",
        "index": 0,
        "step_id": "root.removed_local_call",
        "visit_count": 1,
    }
    frame["status"] = "running"
    frame["current_step"] = dict(child_state["current_step"])
    persisted.status = "failed"
    persisted.steps["InvokeMiddle"]["status"] = "failed"
    before_selected_frame = deepcopy(frame)
    before_parent_steps = json.loads(json.dumps(persisted.steps))
    before_parent_visits = dict(persisted.step_visits)
    manager._write_state()
    before = _projection_run_tree_snapshot(manager.run_root)

    resumed = WorkflowExecutor(root_bundle, tmp_path, manager).execute(resume=True)
    after = _projection_run_tree_snapshot(manager.run_root)
    persisted_after = manager.load().to_dict()

    assert resumed["status"] == "failed"
    assert before != after
    assert persisted_after["step_visits"]["InvokeMiddle"] == (
        before_parent_visits["InvokeMiddle"] + 1
    )
    assert persisted_after["steps"]["InvokeMiddle"] != before_parent_steps["InvokeMiddle"]
    parent_error = persisted_after["steps"]["InvokeMiddle"]["error"]
    assert parent_error["type"] == "resume_projection_integrity_error"
    assert parent_error["context"]["reason"] == "out_of_scope_step_id"
    assert parent_error["context"]["offending_value"] == "root.removed_local_call"
    assert persisted_after["call_frames"][frame_id] == before_selected_frame
    assert not (manager.run_root / "provider_sessions").exists()


def test_call_frame_persists_internal_since_last_consume_bookkeeping(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "inputs": {
                "write_root": {
                    "kind": "relpath",
                    "type": "relpath",
                }
            },
            "artifacts": {
                "failed_count": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "steps": [
                {
                    "name": "Initialize",
                    "id": "initialize",
                    "set_scalar": {
                        "artifact": "failed_count",
                        "value": 1,
                    },
                    "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
                },
                {
                    "name": "ReadInitial",
                    "id": "read_initial",
                    "consumes": [
                        {
                            "artifact": "failed_count",
                            "producers": ["Initialize"],
                            "policy": "latest_successful",
                            "freshness": "since_last_consume",
                        }
                    ],
                    "consume_bundle": {"path": "${inputs.write_root}/read_initial.json"},
                    "command": ["bash", "-lc", "cat ${inputs.write_root}/read_initial.json"],
                },
                {
                    "name": "Increment",
                    "id": "increment",
                    "increment_scalar": {
                        "artifact": "failed_count",
                        "by": 1,
                    },
                    "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
                },
                {
                    "name": "ReadFresh",
                    "id": "read_fresh",
                    "consumes": [
                        {
                            "artifact": "failed_count",
                            "producers": ["Initialize", "Increment"],
                            "policy": "latest_successful",
                            "freshness": "since_last_consume",
                        }
                    ],
                    "consume_bundle": {"path": "${inputs.write_root}/read_fresh.json"},
                    "command": ["bash", "-lc", "cat ${inputs.write_root}/read_fresh.json"],
                },
            ],
        },
    )

    state, persisted = _run_workflow(
        tmp_path,
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "write_root": "state/review-loop",
                },
            },
        ),
        run_id="call-freshness",
    )

    assert state["status"] == "completed"
    frame = next(iter(persisted["call_frames"].values()))
    child_state = frame["state"]

    versions = child_state["artifact_versions"]["failed_count"]
    assert [entry["value"] for entry in versions] == [1, 2]
    assert child_state["artifact_consumes"]["root.read_initial"]["failed_count"] == 1
    assert child_state["artifact_consumes"]["root.read_fresh"]["failed_count"] == 2
    assert "root.read_initial" not in persisted.get("artifact_consumes", {})
    assert "root.read_fresh" not in persisted.get("artifact_consumes", {})


def test_call_exports_outputs_after_callee_finalization_completes(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "artifacts": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "outputs": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.SetApproved.artifacts.approved"},
                }
            },
            "steps": [
                {
                    "name": "SetApproved",
                    "id": "set_approved",
                    "set_scalar": {
                        "artifact": "approved",
                        "value": True,
                    },
                }
            ],
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "Cleanup",
                        "id": "cleanup_step",
                        "command": [
                            "bash",
                            "-lc",
                            "mkdir -p state && printf 'cleanup\\n' >> state/call-finalization.log",
                        ],
                    }
                ],
            },
        },
    )

    state, persisted = _run_workflow(
        tmp_path,
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
        ),
        run_id="call-finalization-success",
    )

    assert state["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}

    frame = next(iter(persisted["call_frames"].values()))
    assert frame["status"] == "completed"
    assert frame["finalization_status"] == "completed"
    assert frame["export_status"] == "completed"
    assert frame["state"]["workflow_outputs"] == {"approved": True}


def test_call_suppresses_outputs_when_callee_finalization_fails(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop_fixture.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "artifacts": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "outputs": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.SetApproved.artifacts.approved"},
                }
            },
            "steps": [
                {
                    "name": "SetApproved",
                    "id": "set_approved",
                    "set_scalar": {
                        "artifact": "approved",
                        "value": True,
                    },
                }
            ],
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "FailCleanup",
                        "id": "fail_cleanup",
                        "command": [
                            "bash",
                            "-lc",
                            "mkdir -p state && printf 'cleanup-failed\\n' >> state/call-finalization.log && exit 1",
                        ],
                    }
                ],
            },
        },
    )

    state, persisted = _run_workflow(
        tmp_path,
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
        ),
        run_id="call-finalization-failure",
    )

    assert state["status"] == "failed"
    assert state["steps"]["RunReviewLoop"]["status"] == "failed"
    assert state["steps"]["RunReviewLoop"]["error"]["type"] == "call_failed"
    assert "artifacts" not in state["steps"]["RunReviewLoop"]

    frame = next(iter(persisted["call_frames"].values()))
    assert frame["status"] == "failed"
    assert frame["finalization_status"] == "failed"
    assert frame["export_status"] == "suppressed"
    assert frame["state"]["workflow_outputs"] == {}


def _root_result_library(*, fail: bool = False) -> dict:
    produce = (
        "mkdir -p state && printf 'true\n' > state/root_result_probe.txt && exit 1"
        if fail
        else "true"
    )
    return {
        "version": "2.5",
        "name": "root-result-library",
        "outputs": {
            "__result__": {
                "kind": "scalar",
                "type": "bool",
                "from": {"ref": "root.steps.SetResult.artifacts.__result__"},
            }
        },
        "artifacts": {
            "__result__": {
                "kind": "scalar",
                "type": "bool",
            }
        },
        "steps": [
            {
                "name": "Probe",
                "id": "probe",
                "command": ["bash", "-lc", produce],
            },
            {
                "name": "SetResult",
                "id": "set_result",
                "set_scalar": {
                    "artifact": "__result__",
                    "value": True,
                },
            },
        ],
    }


def test_call_step_exposes_root_result_output_artifact(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "root_result_library.yaml",
        _root_result_library(),
    )
    caller = _caller_workflow(
        call_step={
            "name": "CallRootResult",
            "id": "call_root_result",
            "call": "root_result",
        },
        imports={"root_result": "workflows/library/root_result_library.yaml"},
    )

    final_state, persisted = _run_workflow(tmp_path, caller, "call-root-result")

    assert final_state["status"] == "completed"
    call_step = persisted["steps"]["CallRootResult"]
    assert call_step["status"] == "completed"
    assert call_step["artifacts"] == {"__result__": True}


def test_call_root_result_child_workflow_failure_suppresses_child_finalization(tmp_path: Path):
    library = _root_result_library(fail=True)
    library["finally"] = {
        "id": "cleanup",
        "steps": [
            {
                "name": "Cleanup",
                "id": "cleanup_step",
                "command": ["bash", "-lc", "true"],
            }
        ],
    }
    _write_yaml(
        tmp_path / "workflows" / "library" / "root_result_library.yaml",
        library,
    )
    caller = _caller_workflow(
        call_step={
            "name": "CallRootResult",
            "id": "call_root_result",
            "call": "root_result",
        },
        imports={"root_result": "workflows/library/root_result_library.yaml"},
    )

    final_state, persisted = _run_workflow(
        tmp_path,
        caller,
        "call-root-result-failure",
        on_error="stop",
    )

    assert final_state["status"] == "failed"
    call_step = persisted["steps"]["CallRootResult"]
    assert call_step["status"] == "failed"
    call_debug = call_step["debug"]["call"]
    assert call_debug["workflow_outputs"] == {}
    assert call_debug["finalization"]["workflow_outputs_status"] == "suppressed"


def test_resume_projection_auditor_rejects_stale_caller_and_alias_without_mutation(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import (
        ResumeProjectionIntegrityError,
        ResumeScopePath,
        audit_scope,
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    workflow_file = str(bundle.provenance.workflow_path)
    scope_path = ResumeScopePath.root(workflow_file).child("parent-frame")
    base_state = {
        "workflow_checksum": "sha256:no-mutation",
        "steps": {},
        "call_frames": {
            "frame": {
                "status": "running",
                "call_step_id": "root.invoke_middle",
                "import_alias": "middle",
                "bound_inputs": {"private_token": "secret-input"},
                "artifacts": {"private_output": "secret-artifact"},
                "state": {"context": {"private": "secret-context"}},
            }
        },
    }

    for field, value, expected_reason in (
        ("call_step_id", "root.stale_call", "out_of_scope_step_id"),
        ("import_alias", "retired_alias", "persisted_import_alias_mismatch"),
    ):
        state = deepcopy(base_state)
        state["call_frames"]["frame"][field] = value
        before = deepcopy(state)

        with pytest.raises(ResumeProjectionIntegrityError) as exc_info:
            audit_scope(bundle, state, scope_path)

        assert exc_info.value.error["context"]["reason"] == expected_reason
        assert exc_info.value.error["context"]["scope_path"] == [
            {"kind": "root", "workflow_file": workflow_file},
            {"kind": "call_frame", "frame_id": "parent-frame"},
        ]
        diagnostic_text = json.dumps(exc_info.value.error, sort_keys=True)
        assert "secret-input" not in diagnostic_text
        assert "secret-artifact" not in diagnostic_text
        assert "secret-context" not in diagnostic_text
        assert state == before


def test_resume_projection_auditor_does_not_load_or_checksum_child_bundles(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import (
        ResumeScopePath,
        audit_scope,
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    state = {
        "workflow_checksum": "sha256:no-child-io",
        "steps": {},
        "call_frames": {
            "frame": {
                "status": "running",
                "call_step_id": "root.invoke_middle",
                "import_alias": "middle",
            }
        },
    }
    before = deepcopy(state)

    with patch.object(
        WorkflowLoader,
        "load",
        side_effect=AssertionError("auditor must not load child workflows"),
    ) as load_workflow, patch.object(
        WorkflowLoader,
        "load_bundle",
        side_effect=AssertionError("auditor must not load child bundles"),
    ) as load_bundle, patch.object(
        StateManager,
        "calculate_checksum",
        side_effect=AssertionError("auditor must not checksum child bundles"),
    ) as checksum, patch.object(
        Path,
        "read_text",
        side_effect=AssertionError("auditor must not read evidence"),
    ) as read_text, patch.object(
        Path,
        "read_bytes",
        side_effect=AssertionError("auditor must not read evidence"),
    ) as read_bytes:
        audit_scope(
            bundle,
            state,
            ResumeScopePath.root(str(bundle.provenance.workflow_path)),
        )

    load_workflow.assert_not_called()
    load_bundle.assert_not_called()
    checksum.assert_not_called()
    read_text.assert_not_called()
    read_bytes.assert_not_called()
    assert state == before


def _assert_nested_projection_error_is_not_wrapped_in_call_failed(
    tmp_path: Path,
    nesting_depth: int,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import (
        ResumeProjectionIntegrityError,
        ResumeScopePath,
        audit_scope,
    )

    root_bundle = WorkflowLoader(tmp_path).load_bundle(
        _write_projection_integrity_call_graph(tmp_path)
    )
    middle_bundle = workflow_import_bundle(root_bundle, "middle")
    assert middle_bundle is not None
    leaf_bundle = workflow_import_bundle(middle_bundle, "leaf")
    assert leaf_bundle is not None

    manager = StateManager(
        tmp_path,
        run_id=f"sticky-projection-nested-{nesting_depth}",
    )
    manager.initialize("workflow.yaml", context=bundle_context_dict(root_bundle))
    first = WorkflowExecutor(root_bundle, tmp_path, manager).execute()
    assert first["status"] == "completed"

    persisted = manager.load()
    outer_frame_id, outer_frame = next(iter(persisted.call_frames.items()))
    outer_state = outer_frame["state"]
    scope_path = ResumeScopePath.root(persisted.workflow_file).child(outer_frame_id)
    selected_frame_before = None

    if nesting_depth == 1:
        audited_bundle = middle_bundle
        audited_state = outer_state
        audited_state["current_step"] = {
            "status": "running",
            "name": "RemovedMiddleStep",
            "step_id": "root.removed_middle_step",
            "visit_count": 1,
        }
        outer_frame["current_step"] = dict(audited_state["current_step"])
    else:
        inner_frame_id, inner_frame = next(
            iter(outer_state["call_frames"].items())
        )
        audited_bundle = leaf_bundle
        audited_state = inner_frame["state"]
        scope_path = scope_path.child(inner_frame_id)
        audited_state["current_step"] = {
            "status": "running",
            "name": "RemovedLeafStep",
            "step_id": "root.removed_leaf_step",
            "visit_count": 1,
        }
        inner_frame["current_step"] = dict(audited_state["current_step"])
        inner_frame["status"] = "running"
        selected_frame_before = deepcopy(inner_frame)
        outer_state["status"] = "failed"
        outer_state["steps"]["InvokeLeaf"]["status"] = "failed"

    outer_frame["status"] = "running"
    if nesting_depth == 1:
        selected_frame_before = deepcopy(outer_frame)
    persisted.status = "failed"
    persisted.steps["InvokeMiddle"]["status"] = "failed"
    visits_before = dict(persisted.step_visits)

    with pytest.raises(ResumeProjectionIntegrityError) as exc_info:
        audit_scope(audited_bundle, audited_state, scope_path)
    expected_error = deepcopy(exc_info.value.error)
    manager._write_state()

    resumed = WorkflowExecutor(root_bundle, tmp_path, manager).execute(resume=True)
    after = manager.load().to_dict()

    assert resumed["status"] == "failed"
    assert resumed["error"] == expected_error
    assert after["error"] == expected_error
    assert after["steps"]["InvokeMiddle"]["error"] == expected_error
    assert after["steps"]["InvokeMiddle"]["error"]["type"] != "call_failed"
    assert after["step_visits"]["InvokeMiddle"] == visits_before["InvokeMiddle"] + 1

    if nesting_depth == 1:
        assert selected_frame_before is not None
        assert after["call_frames"][outer_frame_id] == selected_frame_before
    else:
        assert after["call_frames"][outer_frame_id]["status"] == "failed"
        outer_after = after["call_frames"][outer_frame_id]["state"]
        assert outer_after["error"] == expected_error
        assert outer_after["steps"]["InvokeLeaf"]["error"] == expected_error
        assert selected_frame_before is not None
        inner_frame_id = next(iter(outer_after["call_frames"]))
        assert outer_after["call_frames"][inner_frame_id] == selected_frame_before


def test_nested_projection_error_is_not_wrapped_in_call_failed(
    tmp_path: Path,
) -> None:
    _assert_nested_projection_error_is_not_wrapped_in_call_failed(tmp_path, 1)


def test_projection_integrity_two_level_failure_preserves_exact_root_diagnostic(
    tmp_path: Path,
) -> None:
    _assert_nested_projection_error_is_not_wrapped_in_call_failed(tmp_path, 2)
