from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import (
    NodeResultAddress,
    WorkflowInputAddress,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.pure_result_replay import (
    DEPENDENCY_INDEX_INVALID,
    MULTIPLE_VISIT_REGION,
    PureResultReplayIndexError,
    _propagate_pure_ineligibility,
    derive_pure_result_replay_index,
)
from orchestrator.workflow_lisp import build_artifacts
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import (
    capture_frontend_diagnostic_identities,
)
from orchestrator.workflow_lisp.lexical_checkpoints import canonical_json_dumps
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


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


def test_pure_result_replay_fixture_compiles_real_effect_barrier_spine(
    tmp_path: Path,
) -> None:
    _, bundle = _copy_and_compile_fixture(tmp_path)

    kinds = [bundle.ir.nodes[node_id].kind.value for node_id in bundle.ir.body_region]

    assert kinds.count("pure_projection") >= 2
    assert kinds.count("command") == 2
    assert _canonical_program_digest(bundle)


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
