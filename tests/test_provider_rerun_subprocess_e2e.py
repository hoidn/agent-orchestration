"""Process-death acceptance for at-least-once provider visit recovery."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any
from unittest.mock import patch

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from tests.workflow_bundle_helpers import bundle_context_dict
from tests.workflow_fixture_loader import WorkflowLoader


pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="real SIGKILL recovery proof requires Linux fork semantics",
)


def _provider_bundle(
    workspace: Path,
    *,
    run_id: str,
    session: bool = False,
):
    workflow_path = workspace / f"{run_id}.orc"
    workflow_path.write_text(
        "; typed test fixture for a provider process-death proof\n",
        encoding="utf-8",
    )
    mapping: dict[str, Any] = {
        "version": "2.10",
        "name": f"provider-rerun-{run_id}",
        "providers": {
            "sleeping": {
                "command": [
                    sys.executable,
                    "-c",
                    "print('unused provider command')",
                ],
                "input_mode": "stdin",
            }
        },
        "steps": [
            {
                "name": "Provider",
                "id": "provider",
                "provider": "sleeping",
            }
        ],
    }
    if session:
        mapping["artifacts"] = {
            "provider_session_id": {
                "kind": "scalar",
                "type": "string",
            }
        }
        mapping["providers"]["sleeping"]["session_support"] = {
            "metadata_mode": "codex_exec_jsonl_stdout",
            "fresh_command": [
                sys.executable,
                "-c",
                "print('unused provider command')",
            ],
            "resume_command": [
                sys.executable,
                "-c",
                "print('unused ${SESSION_ID}')",
            ],
        }
        mapping["steps"][0]["provider_session"] = {
            "mode": "fresh",
            "publish_artifact": "provider_session_id",
        }
    bundle = WorkflowLoader(workspace).load_mapping(
        mapping,
        workflow_path=workflow_path,
    )
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
    )
    return bundle, manager


def _supervision_bundle(workspace: Path, *, run_id: str):
    from orchestrator.workflow_lisp.build import build_frontend_bundle
    from tests.test_workflow_lisp_provider_supervision_e2e import (
        _build_request,
        _copy_fixture,
    )

    fixture_files = _copy_fixture(workspace)
    bundle = build_frontend_bundle(
        _build_request(workspace, fixture_files)
    ).validated_bundle
    workflow_path = fixture_files["provider_supervision_continue.orc"]
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
    )
    return bundle, manager


def _peer_bundle(workspace: Path, *, run_id: str):
    from tests.test_workflow_lisp_provider_peer_group_e2e import (
        _compile_peer_group,
        _public_two_member_source,
    )

    compiled = _compile_peer_group(
        workspace,
        source=_public_two_member_source(),
        validate_shared=True,
        member_ids=("planner", "reviewer"),
    )
    bundle = compiled.validated_bundles["orchestrate"]
    workflow_path = workspace / "provider_peer_group.orc"
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
    )
    return bundle, manager


def _build_family(
    workspace: Path,
    *,
    family: str,
):
    run_id = f"{family}-provider-sigkill"
    if family == "ordinary":
        bundle, manager = _provider_bundle(
            workspace,
            run_id=run_id,
        )
    elif family == "session":
        bundle, manager = _provider_bundle(
            workspace,
            run_id=run_id,
            session=True,
        )
    elif family == "supervision":
        bundle, manager = _supervision_bundle(
            workspace,
            run_id=run_id,
        )
    elif family == "peer_group":
        bundle, manager = _peer_bundle(
            workspace,
            run_id=run_id,
        )
    elif family == "phased":
        from tests.test_workflow_lisp_phased_delivery_e2e import (
            _compile_public,
            _manager,
        )

        bundle = _compile_public(workspace)
        manager = _manager(
            workspace,
            bundle=bundle,
            run_id=run_id,
        )
        run_id = manager.run_id
    else:
        raise AssertionError(f"unknown family: {family}")
    return run_id, bundle, manager


def _interrupt_child(
    family: str,
    bundle: Any,
    workspace: str,
    run_id: str,
    marker_path: str,
) -> None:
    os.setsid()
    workspace_path = Path(workspace)
    manager = StateManager(workspace_path, run_id=run_id)
    manager.load()

    def block_mid_provider(
        executor: WorkflowExecutor,
        step: Any,
        *,
        step_name: str | None = None,
        runtime_step_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_step_name = step_name or str(step["name"])
        step_id = runtime_step_id or executor._step_id(step)
        scope = executor._provider_attempt_scope(
            step_name=resolved_step_name,
            runtime_step_id=step_id,
        )
        ordinal = executor.state_manager.allocate_provider_attempt(scope)
        provider = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(300)",
            ],
        )
        marker = Path(marker_path)
        marker.write_text(
            json.dumps(
                {
                    "provider_pid": provider.pid,
                    "scope": scope.to_dict(),
                    "scope_key": scope.key,
                    "ordinal": ordinal,
                    "family": family,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        with marker.open("rb") as handle:
            os.fsync(handle.fileno())
        while True:
            time.sleep(60)

    if family in {"ordinary", "session"}:

        def dispatch(executor, step, state):
            del state
            return block_mid_provider(executor, step)

        method_name = "_execute_provider"
    elif family in {"supervision", "peer_group"}:

        def dispatch(
            executor,
            step,
            state,
            *,
            step_name,
            runtime_step_id=None,
        ):
            del state
            return block_mid_provider(
                executor,
                step,
                step_name=step_name,
                runtime_step_id=runtime_step_id,
            )

        method_name = (
            "_execute_provider_supervision"
            if family == "supervision"
            else "_execute_provider_peer_group"
        )
    else:
        def dispatch(
            executor,
            step,
            context,
            state,
            runtime_step_id=None,
            **_kwargs,
        ):
            del context, state
            return block_mid_provider(
                executor,
                step,
                runtime_step_id=runtime_step_id,
            )

        method_name = "_execute_phased_provider_with_context"

    with patch.object(WorkflowExecutor, method_name, new=dispatch):
        WorkflowExecutor(
            bundle,
            workspace_path,
            manager,
            retry_delay_ms=0,
            step_heartbeat_interval_sec=0,
        ).execute(on_error="stop")


def _wait_for_marker(path: Path, *, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for process marker: {path}")


def _kill_process(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _completion_dispatch(
    family: str,
    fresh_attempt: dict[str, Any],
):
    def complete(
        executor: WorkflowExecutor,
        step: Any,
        state: dict[str, Any],
        *,
        step_name: str | None = None,
        runtime_step_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_step_name = step_name or str(step["name"])
        step_id = runtime_step_id or executor._step_id(step)
        scope = executor._provider_attempt_scope(
            step_name=resolved_step_name,
            runtime_step_id=step_id,
        )
        ordinal = executor.state_manager.allocate_provider_attempt(scope)
        fresh_attempt.update(
            scope=scope.to_dict(),
            scope_key=scope.key,
            ordinal=ordinal,
        )
        executor._emit_pending_interrupted_provider_rerun(
            family=family,
            step_id=step_id,
            visit_count=state["step_visits"][resolved_step_name],
        )
        result: dict[str, Any] = {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "output": "fresh visit completed",
        }
        if family == "session":
            result["debug"] = {
                "provider_session": {
                    "session_id": "fresh-session-visit-2",
                    "event_count": 1,
                }
            }
        elif family in {"supervision", "peer_group"}:
            result["artifacts"] = {
                "__result__": "fresh visit completed",
            }
        elif family == "phased":
            output_bundle = step.get("output_bundle")
            assert isinstance(output_bundle, dict)
            template = output_bundle["path"]
            assert template.startswith("${inputs.") and template.endswith("}")
            input_name = template[len("${inputs.") : -1]
            relative_path = state["bound_inputs"][input_name]
            bundle_path = executor.workspace / relative_path
            bundle_path.parent.mkdir(parents=True, exist_ok=True)
            bundle_path.write_text(
                json.dumps({"approved": True}) + "\n",
                encoding="utf-8",
            )
            result["artifacts"] = {
                "approved": True,
            }
        if family == "supervision":
            return executor._finalize_provider_supervision_settlement(
                step,
                state,
                step_name=resolved_step_name,
                result=result,
            )
        if family == "peer_group":
            return executor._finalize_provider_peer_group_settlement(
                step,
                state,
                step_name=resolved_step_name,
                result=result,
            )
        return result

    if family in {"ordinary", "session"}:

        def dispatch(executor, step, state):
            return complete(executor, step, state)

        return "_execute_provider", dispatch
    if family in {"supervision", "peer_group"}:

        def dispatch(
            executor,
            step,
            state,
            *,
            step_name,
            runtime_step_id=None,
        ):
            return complete(
                executor,
                step,
                state,
                step_name=step_name,
                runtime_step_id=runtime_step_id,
            )

        return (
            "_execute_provider_supervision"
            if family == "supervision"
            else "_execute_provider_peer_group"
        ), dispatch

    def dispatch(
        executor,
        step,
        context,
        state,
        runtime_step_id=None,
        **_kwargs,
    ):
        del context
        return complete(
            executor,
            step,
            state,
            runtime_step_id=runtime_step_id,
        )

    return "_execute_phased_provider_with_context", dispatch


@pytest.mark.parametrize(
    "family",
    ("ordinary", "session", "supervision", "peer_group", "phased"),
)
def test_provider_sigkill_resume_reruns_fresh_attempt(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    family: str,
) -> None:
    run_id, bundle, manager = _build_family(
        tmp_path,
        family=family,
    )
    marker_path = tmp_path / f"{family}-provider.json"
    context = multiprocessing.get_context("fork")
    child = context.Process(
        target=_interrupt_child,
        args=(family, bundle, str(tmp_path), run_id, str(marker_path)),
    )
    interrupted: dict[str, Any] | None = None
    child.start()
    try:
        interrupted = _wait_for_marker(marker_path)
        current_step = manager.load().current_step
        assert current_step is not None
        assert current_step["visit_count"] == 1
    finally:
        if child.pid is not None:
            _kill_process_group(child.pid)
        child.join(timeout=5)
        if interrupted is not None:
            _kill_process(int(interrupted["provider_pid"]))
        if child.is_alive():
            child.kill()
            child.join(timeout=5)

    assert interrupted is not None
    assert child.exitcode == -signal.SIGKILL

    resume_manager = StateManager(tmp_path, run_id=run_id)
    resume_manager.load()
    fresh_attempt: dict[str, Any] = {}
    method_name, completion = _completion_dispatch(
        family,
        fresh_attempt,
    )

    with caplog.at_level(logging.WARNING), patch.object(
        WorkflowExecutor,
        method_name,
        new=completion,
    ):
        resumed = WorkflowExecutor(
            bundle,
            tmp_path,
            resume_manager,
            retry_delay_ms=0,
            step_heartbeat_interval_sec=0,
        ).execute(on_error="stop", resume=True)

    assert resumed["status"] == "completed", resumed.get("error")
    step_name = interrupted["scope"]["enclosing_step"]["step_name"]
    assert resumed["steps"][step_name]["visit_count"] == 2
    allocations = resumed["provider_attempt_allocations"]
    assert len(allocations) == 2
    assert {
        row["scope"]["enclosing_step"]["visit_count"]
        for row in allocations.values()
    } == {1, 2}
    assert interrupted["scope_key"] in allocations
    assert fresh_attempt["scope_key"] in allocations
    assert fresh_attempt["scope_key"] != interrupted["scope_key"]
    assert interrupted["ordinal"] == 1
    assert fresh_attempt["ordinal"] == 1
    rerun_events = [
        record
        for record in caplog.records
        if getattr(record, "orchestrator_diagnostic", None)
        == "provider_attempt_interrupted_rerun"
    ]
    assert len(rerun_events) == 1
    assert rerun_events[0].provider_family == family
    assert rerun_events[0].discarded_visit == 1
    assert rerun_events[0].next_visit == 2
