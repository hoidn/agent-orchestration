from __future__ import annotations

from pathlib import Path

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_shadow_points.orc")


def _executor_for_fixture(tmp_path: Path) -> WorkflowExecutor:
    tmp_path.mkdir(parents=True, exist_ok=True)
    local_fixture = tmp_path / FIXTURE.name
    local_fixture.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )
    state_manager = StateManager(tmp_path, run_id="checkpoint-identity-comparison")
    return WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)


def checkpoint_identity_map(executor: WorkflowExecutor) -> dict[tuple[str, str], str]:
    """Map (workflow_name, origin_key) to checkpoint_id for every lexical point."""
    return {
        (point.workflow_name, point.origin_key): point.checkpoint_id
        for point in executor.runtime_plan.lexical_checkpoint_points
    }


def test_checkpoint_identity_stable_across_recompiles(tmp_path: Path) -> None:
    first = _executor_for_fixture(tmp_path / "a")
    second = _executor_for_fixture(tmp_path / "b")

    assert checkpoint_identity_map(first) == checkpoint_identity_map(second)
