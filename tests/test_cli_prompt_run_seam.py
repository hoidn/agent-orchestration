"""Task 8: minimal structured run seam — ``StateManager.new_run_id``,
immutable ``RunWorkflowResult``, and the keyword-only internal ``run_id``.

Step 8.3: the public ``run`` parser exposes no run-id flag, CLI dispatch
returns only ``result.exit_code``, and the structured result detaches and
recursively freezes ``workflow_outputs``/``usage`` so callers can never
mutate finalized outputs or provenance (top-level, nested, or via the
executor's live source mappings).
"""

from __future__ import annotations

import json
import os
import re
from argparse import Namespace
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.cli.commands.run import RunWorkflowResult, run_workflow
from orchestrator.cli.main import main
from orchestrator.state import StateManager

from tests.test_cli_prompt import (  # noqa: F401  (shared harness)
    MODEL,
    TASK_TEXT,
    _exit,
    _usage_row,
    fake_runtime,
)

def test_state_manager_new_run_id_public_and_formatted(tmp_path):
    manager = StateManager(workspace=tmp_path)
    run_id = manager.new_run_id()
    assert re.fullmatch(r"\d{8}T\d{6}Z-[a-z0-9]{6}", run_id)
    assert manager.new_run_id() != run_id


def _stub_workflow_run(
    monkeypatch,
    tmp_path: Path,
    *,
    execute_result: object,
    run_id: str | None = None,
) -> Namespace:
    from tests.workflow_fixture_loader import WorkflowLoader

    workflow = tmp_path / "workflow.orc"
    workflow.write_text("(workflow-lisp)\n")
    bundle = WorkflowLoader(tmp_path).load_mapping(
        {
            "version": "2.1",
            "name": "test",
            "steps": [{"name": "test", "command": ["bash", "-lc", "true"]}],
        }
    )
    monkeypatch.setattr(
        "orchestrator.cli.commands.run.build_frontend_bundle",
        lambda request: SimpleNamespace(
            validated_bundle=bundle,
            manifest=SimpleNamespace(lowering_schema_version=1),
        ),
    )
    monkeypatch.setattr(
        "orchestrator.cli.commands.run.WorkflowExecutor",
        lambda **kwargs: SimpleNamespace(execute=lambda **kw: execute_result),
    )
    args = Namespace(
        workflow=str(workflow), context=None, context_file=None,
        input=None, input_file=None, clean_processed=False,
        archive_processed=None, dry_run=False, debug=False, quiet=False,
        verbose=False, log_level="info", backup_state=False, state_dir=None,
        on_error="stop", max_retries=0, retry_delay=1000,
        stream_output=False, step_summaries=False, summary_mode=None,
        summary_provider="claude_sonnet_summary", summary_timeout_sec=120,
        summary_max_input_chars=12000, summary_profile=None,
        live_agent_notes=False, live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0, live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000, entry_workflow=None,
        source_root=None, provider_externs_file=None,
        prompt_externs_file=None, imported_workflow_bundles_file=None,
        command_boundaries_file=None, emit_debug_yaml=False,
        run_ref_root=None,
    )
    if run_id is not None:
        monkeypatch.setattr(
            "orchestrator.cli.commands.run.StateManager",
            lambda **kwargs: StateManager(
                workspace=tmp_path,
                **{k: v for k, v in kwargs.items() if k != "workspace"},
            ),
        )
    monkeypatch.chdir(tmp_path)
    return args


def test_run_workflow_result_immutable_and_structured(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "orchestrator.cli.commands.run.StateManager",
        lambda **kwargs: StateManager(
            workspace=tmp_path,
            **{k: v for k, v in kwargs.items() if k != "workspace"},
        ),
    )
    args = _stub_workflow_run(monkeypatch, tmp_path, execute_result={
        "status": "completed", "workflow_outputs": {"result": "ok"},
        "steps": {"step-a": {"debug": {"provider_session": {
            "session_id": "session-step-a", "final_provider": "omp",
            "final_model": MODEL, "total_tokens": 15, "total_cost": 0.0,
            "messages": [{"provider": "omp", "model": MODEL,
                          "usage": _usage_row(), "stop_reason": "stop"}],
        }}}},
    })
    result = run_workflow(args)
    assert isinstance(result, RunWorkflowResult)
    assert result.exit_code == 0
    assert isinstance(result.run_id, str)
    assert result.run_root == tmp_path / ".orchestrate" / "runs" / result.run_id
    assert result.workflow_outputs == {"result": "ok"}
    assert result.session_status == "completed"
    usage = result.usage["step-a"]
    assert usage["session_id"] == "session-step-a"
    assert usage["usage"]["totalTokens"] == 15
    with pytest.raises(FrozenInstanceError):
        result.exit_code = 1
    with pytest.raises(FrozenInstanceError):
        result.usage = {}


def test_run_workflow_accepts_keyword_run_id(tmp_path, monkeypatch):
    reserved = "20260821T000000Z-abc123"
    args = _stub_workflow_run(
        monkeypatch,
        tmp_path,
        execute_result={"status": "completed"},
        run_id=reserved,
    )
    result = run_workflow(args, run_id=reserved)
    assert result.exit_code == 0
    assert result.run_id == reserved
    assert result.run_root == tmp_path / ".orchestrate" / "runs" / reserved
    assert (result.run_root / "state.json").is_file()

def test_descriptor_workflow_persists_logical_resume_path(
    tmp_path, monkeypatch
):
    from orchestrator.providers.omp_launch_fs import directory_identity
    from orchestrator.run_lock import reserved_run_writer_lock

    run_id = "20260821T000000Z-logical1"
    args = _stub_workflow_run(
        monkeypatch, tmp_path, execute_result={"status": "completed"}
    )
    run_root = tmp_path / ".orchestrate" / "runs" / run_id
    prompt_inputs = run_root / "prompt-inputs"
    prompt_inputs.mkdir(parents=True)
    logical_workflow = prompt_inputs / "workflow.orc"
    logical_workflow.write_bytes(Path(args.workflow).read_bytes())
    prompt_fd = os.open(
        prompt_inputs,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    identity = directory_identity(str(run_root))
    try:
        with reserved_run_writer_lock(run_root, identity) as run_fd:
            args.workflow = f"/proc/self/fd/{prompt_fd}/workflow.orc"
            args.source_root = [f"/proc/self/fd/{prompt_fd}"]
            result = run_workflow(
                args,
                run_id=run_id,
                expected_run_identity=identity,
                reserved_run_fd=run_fd,
                logical_workflow_path=logical_workflow,
            )
    finally:
        os.close(prompt_fd)

    state = json.loads((run_root / "state.json").read_text())
    assert result.exit_code == 0
    assert state["workflow_file"] == (
        f".orchestrate/runs/{run_id}/prompt-inputs/workflow.orc"
    )
    assert "/proc/self/fd/" not in state["workflow_file"]


def test_run_parser_exposes_no_run_id_flag(tmp_path, monkeypatch):
    workflow = tmp_path / "workflow.orc"
    workflow.write_text("(workflow-lisp)\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["run", str(workflow), "--run-id", "x"])
    assert exc.value.code == 2


def test_main_run_dispatch_returns_exit_code_only(tmp_path, monkeypatch):
    args = _stub_workflow_run(
        monkeypatch,
        tmp_path,
        execute_result={"status": "completed"},
    )
    code = main(["run", str(Path(args.workflow))])
    assert code == 0
    assert not isinstance(code, RunWorkflowResult)


def test_reserved_root_swapped_after_writer_lock_fails_before_initialize(
    tmp_path, monkeypatch, fake_runtime
):
    # R7: the run root path is revalidated against the retained directory
    # authority immediately before StateManager.initialize; a root replaced
    # while the writer lock is held must fail closed with no state work and
    # no file created in the replacement target.
    import orchestrator.cli.commands.prompt_run_service as prompt_run_service
    from contextlib import contextmanager

    reserved = "20260821T000000Z-lock001"
    monkeypatch.setattr(StateManager, "new_run_id", lambda: reserved)
    original_lock = prompt_run_service.reserved_run_writer_lock
    initialize_calls = []

    @contextmanager
    def lock_then_swap(run_root, identity):
        with original_lock(run_root, identity) as dir_fd:
            # Barrier: replace the reserved root after the writer lock is held.
            parent = run_root.parent
            os.replace(run_root, parent / (run_root.name + "-swapped"))
            run_root.mkdir()
            yield dir_fd

    monkeypatch.setattr(
        prompt_run_service, "reserved_run_writer_lock", lock_then_swap
    )
    original_initialize = StateManager.initialize

    def spy_initialize(self, *args, **kwargs):
        initialize_calls.append(True)
        return original_initialize(self, *args, **kwargs)

    monkeypatch.setattr(StateManager, "initialize", spy_initialize)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert initialize_calls == []
    assert fake_runtime.executed == []
    runs_root = tmp_path / ".orchestrate" / "runs"
    replacement = runs_root / reserved
    assert list(replacement.iterdir()) == []



def test_reserved_root_swap_during_initialize_never_writes_replacement(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.cli.commands.run as run_command

    reserved = "20260821T000000Z-lock002"
    monkeypatch.setattr(StateManager, "new_run_id", lambda: reserved)
    original_initialize = StateManager.initialize
    original_root = tmp_path / ".orchestrate" / "runs" / f"{reserved}-original"

    def swap_then_initialize(self, *args, **kwargs):
        os.replace(self.run_root, original_root)
        self.run_root.mkdir()
        return original_initialize(self, *args, **kwargs)

    monkeypatch.setattr(StateManager, "initialize", swap_then_initialize)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )

    replacement = tmp_path / ".orchestrate" / "runs" / reserved
    assert code == 1
    assert fake_runtime.executed == []
    assert list(replacement.iterdir()) == []
    assert not (replacement / "run.lock").exists()
    assert not (replacement / "state.json").exists()
    assert (original_root / "run.lock").is_file()
    assert (original_root / "state.json").is_file()

def test_run_workflow_reserved_root_pre_lock_swap_fails_before_any_write(
    tmp_path, monkeypatch
):
    # R7 shared boundary: a reserved run root replaced by a different
    # directory before run_workflow opens it fails with no lock/temp/state
    # file created in the replacement target. Every prompt-run caller routes
    # through this boundary.
    import orchestrator.cli.commands.run as run_module
    from orchestrator.providers.omp_launch_fs import directory_identity

    run_id = "20260821T000000Z-swap001"
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_root = runs_root / run_id
    run_root.mkdir(parents=True)
    identity = directory_identity(str(run_root))
    os.replace(run_root, runs_root / (run_id + "-original"))
    replacement = runs_root / run_id
    replacement.mkdir()

    args = _stub_workflow_run(
        monkeypatch, tmp_path, execute_result={}, run_id=run_id
    )
    result = run_workflow(args, run_id=run_id, expected_run_identity=identity)
    assert result.exit_code == 1
    assert result.run_id == run_id
    assert result.run_root == run_root
    assert (result.session_id, result.session_status) == (None, None)
    assert list(replacement.iterdir()) == []
    assert not (replacement / "run.lock").exists()
    assert not (replacement / "state.json").exists()


def test_run_workflow_reserved_root_pre_lock_symlink_swap_fails_before_any_write(
    tmp_path, monkeypatch
):
    # R7 shared boundary, symlink variant: the reserved path pointing at an
    # attacker directory must fail before writing through the symlink.
    import orchestrator.cli.commands.run as run_module
    from orchestrator.providers.omp_launch_fs import directory_identity

    run_id = "20260821T000000Z-swap002"
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_root = runs_root / run_id
    run_root.mkdir(parents=True)
    identity = directory_identity(str(run_root))
    os.replace(run_root, runs_root / (run_id + "-original"))
    attacker = runs_root / (run_id + "-attacker")
    attacker.mkdir()
    run_root.symlink_to(attacker, target_is_directory=True)

    args = _stub_workflow_run(
        monkeypatch, tmp_path, execute_result={}, run_id=run_id
    )
    result = run_workflow(args, run_id=run_id, expected_run_identity=identity)
    assert result.exit_code == 1
    assert result.run_id == run_id
    assert list(attacker.iterdir()) == []
    assert not (attacker / "run.lock").exists()
    assert not (attacker / "state.json").exists()


def test_prompt_run_seam_pre_lock_swap_fails_without_files_in_replacement(
    tmp_path, monkeypatch, fake_runtime
):
    # R7 at the prompt-run seam: a reserved root swapped before the shared
    # run boundary acquires the lock fails with exit 1 and no file in the
    # replacement target (run.lock / state.json / logs all absent).
    import orchestrator.cli.commands.prompt_run_service as prompt_run_service

    reserved = "20260821T000000Z-seam003"
    monkeypatch.setattr(StateManager, "new_run_id", lambda: reserved)
    original_lock = prompt_run_service.reserved_run_writer_lock

    def swap_before_lock(run_root, identity):
        # Simulate an attacker swap that already happened before the shared
        # boundary opened the reserved root.
        parent = run_root.parent
        os.replace(run_root, parent / (run_root.name + "-swapped"))
        run_root.mkdir()
        return original_lock(run_root, identity)

    monkeypatch.setattr(
        prompt_run_service, "reserved_run_writer_lock", swap_before_lock
    )
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    runs_root = tmp_path / ".orchestrate" / "runs"
    replacement = runs_root / reserved
    assert list(replacement.iterdir()) == []
    assert not (replacement / "run.lock").exists()
    assert not (replacement / "state.json").exists()


def test_prompt_run_seam_pre_lock_symlink_swap_fails_without_files_in_target(
    tmp_path, monkeypatch, fake_runtime
):
    # R7 at the prompt-run seam, symlink variant: the lock must never be
    # created inside the attacker directory behind the symlinked root.
    import orchestrator.cli.commands.prompt_run_service as prompt_run_service

    reserved = "20260821T000000Z-seam004"
    monkeypatch.setattr(StateManager, "new_run_id", lambda: reserved)
    original_lock = prompt_run_service.reserved_run_writer_lock

    def symlink_before_lock(run_root, identity):
        parent = run_root.parent
        os.replace(run_root, parent / (run_root.name + "-swapped"))
        attacker = parent / (run_root.name + "-attacker")
        attacker.mkdir()
        run_root.symlink_to(attacker, target_is_directory=True)
        return original_lock(run_root, identity)

    monkeypatch.setattr(
        prompt_run_service, "reserved_run_writer_lock", symlink_before_lock
    )
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    runs_root = tmp_path / ".orchestrate" / "runs"
    attacker = runs_root / (reserved + "-attacker")
    assert list(attacker.iterdir()) == []
    assert not (attacker / "run.lock").exists()


def test_run_workflow_result_outputs_and_usage_are_deeply_immutable(
    tmp_path, monkeypatch
):
    execute_result = {
        "status": "completed",
        "workflow_outputs": {"result": "ok", "nested": {"list": [1, 2]}},
        "steps": {
            "step-a": {
                "debug": {
                    "provider_session": {
                        "session_id": "session-step-a",
                        "final_provider": "omp",
                        "final_model": MODEL,
                        "total_tokens": 15,
                        "total_cost": 0.0,
                        "messages": [
                            {"provider": "omp", "model": MODEL,
                             "usage": _usage_row(), "stop_reason": "stop"}
                        ],
                    }
                }
            }
        },
    }
    args = _stub_workflow_run(
        monkeypatch, tmp_path, execute_result=execute_result
    )
    result = run_workflow(args)
    assert result.workflow_outputs == {"result": "ok", "nested": {"list": (1, 2)}}
    with pytest.raises(TypeError):
        result.workflow_outputs["result"] = "changed"
    with pytest.raises((TypeError, AttributeError)):
        result.workflow_outputs["nested"]["list"].append(3)
    with pytest.raises(TypeError):
        result.usage["step-a"]["session_id"] = "changed"
    with pytest.raises(TypeError):
        result.usage["step-a"]["usage"]["totalTokens"] = 999
    # Alias independence: mutating the executor's live mappings after the
    # result was built cannot change the frozen result.
    execute_result["workflow_outputs"]["result"] = "mutated-live"
    execute_result["steps"]["step-a"]["debug"]["provider_session"][
        "session_id"
    ] = "mutated-session"
    assert result.workflow_outputs["result"] == "ok"
    assert result.usage["step-a"]["session_id"] == "session-step-a"


def test_commands_package_exports_run_workflow_and_result():
    from orchestrator.cli.commands import (
        RunWorkflowResult as ExportedResult,
    )
    from orchestrator.cli.commands import __all__ as exported
    from orchestrator.cli.commands import run_workflow as exported_run

    assert "run_workflow" in exported
    assert "prompt_workflow" in exported
    assert "RunWorkflowResult" in exported
    assert exported_run is run_workflow
    assert ExportedResult is RunWorkflowResult


def test_run_workflow_result_defaults_and_direct_construction_are_frozen():
    bare = RunWorkflowResult(exit_code=1)
    with pytest.raises(TypeError):
        bare.workflow_outputs["x"] = 1
    with pytest.raises(TypeError):
        bare.usage["u"] = {}
    source = {"nested": {"list": [1, 2]}}
    usage_source = {"step-a": {"session_id": "s", "usage": {"totalTokens": 3}}}
    result = RunWorkflowResult(
        exit_code=0, workflow_outputs=source, usage=usage_source
    )
    assert result.workflow_outputs == {"nested": {"list": (1, 2)}}
    with pytest.raises((TypeError, AttributeError)):
        result.workflow_outputs["nested"]["list"].append(3)
    with pytest.raises(TypeError):
        result.usage["step-a"]["usage"]["totalTokens"] = 9
    source["nested"]["list"].append(99)
    usage_source["step-a"]["session_id"] = "mutated"
    assert result.workflow_outputs["nested"]["list"] == (1, 2)
    assert result.usage["step-a"]["session_id"] == "s"


def test_run_workflow_identity_mismatch_returns_known_run_id_and_root(
    tmp_path, monkeypatch
):
    import orchestrator.cli.commands.run as run_module
    from orchestrator.providers.omp_launch_fs import directory_identity

    run_id = "20260821T000000Z-caller1"
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_root = runs_root / run_id
    run_root.mkdir(parents=True)
    wrong_identity = (directory_identity(str(run_root))[0] + 1, 0)
    args = _stub_workflow_run(
        monkeypatch, tmp_path, execute_result={}, run_id=run_id
    )
    result = run_workflow(args, run_id=run_id, expected_run_identity=wrong_identity)
    assert result.exit_code == 1
    assert result.run_id == run_id
    assert result.run_root == tmp_path / ".orchestrate" / "runs" / run_id
    assert (result.session_id, result.session_status) == (None, None)


def test_run_workflow_post_session_exception_returns_session_id_and_failed(
    tmp_path, monkeypatch
):
    import orchestrator.cli.commands.run as run_module

    args = _stub_workflow_run(monkeypatch, tmp_path, execute_result={})
    monkeypatch.setattr(
        run_module, "WorkflowExecutor",
        lambda **kw: SimpleNamespace(
            execute=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))),
    )
    monkeypatch.setattr(
        run_module, "open_executor_session", lambda *a, **kw: "sess-123"
    )
    result = run_workflow(args)
    assert (result.exit_code, result.session_id, result.session_status) == (
        1, "sess-123", "failed")


def test_run_workflow_caller_run_id_kept_with_empty_archive_destination(
    tmp_path, monkeypatch
):
    (tmp_path / "processed").mkdir()
    run_id = "20260821T000000Z-caller2"
    args = _stub_workflow_run(
        monkeypatch, tmp_path,
        execute_result={"status": "completed"}, run_id=run_id,
    )
    args.archive_processed = " "
    result = run_workflow(args, run_id=run_id)
    assert result.exit_code == 0
    assert result.run_id == run_id


def test_typed_inputs_cannot_bridge_to_provider_params_outside_omp_conf(
    tmp_path, monkeypatch
):
    import orchestrator.workflow.executor as workflow_module
    from orchestrator.state import StateManager
    from tests.workflow_fixture_loader import WorkflowLoader

    workflow = {
        "version": "2.10",
        "name": "bridge",
        "providers": {"sim": {"command": ["echo", "${workspace}"]}},
        "steps": [
            {
                "name": "Ask",
                "provider": "sim",
                "provider_params": {"model": "authored"},
                "typed_prompt_inputs": [
                    {
                        "schema_version": "workflow_lisp_typed_prompt_input.v1",
                        "binding_name": "workspace",
                        "renderer": {"renderer_id": "canonical-json",
                                     "renderer_version": 1,
                                     "accepted_shape": "any_pure_value"},
                        "value_source": {"kind": "typed_binding_ref",
                                         "binding": {"ref": "inputs.workspace"}},
                        "value_type_name": "String",
                        "source_map_origin_key": "typed-prompt-input-bridge",
                        "injection_order": 0,
                    }
                ],
            }
        ],
    }
    (tmp_path / "workflow.yaml").write_text(
        json.dumps(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(tmp_path / "workflow.yaml")
    state_manager = StateManager(workspace=tmp_path, run_id="bridge-run")
    state_manager.initialize(
        "workflow.yaml", bound_inputs={"workspace": "/evil/path"}
    )
    captured = {}

    def capturing_execute(self, invocation, **kwargs):
        captured["command"] = list(invocation.command)
        captured["env"] = dict(invocation.env)
        return {"status": "completed", "exit_code": 0}

    monkeypatch.setattr(
        workflow_module.WorkflowExecutor,
        "_execute_provider_invocation",
        capturing_execute,
    )
    executor = workflow_module.WorkflowExecutor(loaded, tmp_path, state_manager)
    result = executor.execute()
    # The hostile typed input must never bridge into provider params (the
    # template ${workspace} placeholder stays unresolved; pre-fix the value
    # was injected and substituted into the command).
    assert "/evil/path" not in " ".join(captured.get("command") or [])
    assert "/evil/path" not in " ".join(
        str(v) for v in (captured.get("env") or {}).values())
    assert result["steps"]["Ask"]["status"] in ("completed", "failed")

def test_inference_snapshot_rejects_control_character_model(tmp_path):
    from orchestrator.cli.commands import prompt_io

    prompt_inputs = tmp_path / "prompt-inputs"
    prompt_inputs.mkdir()
    asset = tmp_path / "infer-output-contract.orc"
    asset.write_bytes(b"      :inputs (task_prompt output_request)\n")
    with pytest.raises(prompt_io.PromptRunError, match="model"):
        prompt_io._write_inference_snapshot(
            prompt_inputs, "bad\x01model", "infer this", str(asset))
    assert not (prompt_inputs / "infer-output-contract.orc").exists()


def test_inference_snapshot_requires_exactly_one_marker(tmp_path):
    from orchestrator.cli.commands import prompt_io

    prompt_inputs = tmp_path / "prompt-inputs"
    prompt_inputs.mkdir()
    asset = tmp_path / "infer-output-contract.orc"
    asset.write_bytes(
        b"      :inputs (task_prompt output_request)\n"
        b"      :inputs (task_prompt output_request)\n"
    )
    with pytest.raises(prompt_io.PromptRunError, match="exactly one"):
        prompt_io._write_inference_snapshot(
            prompt_inputs, "gpt-5.6-sol", "infer this", str(asset))
    assert not (prompt_inputs / "infer-output-contract.orc").exists()

def test_run_workflow_close_failure_after_success_returns_failed_session(
    tmp_path, monkeypatch
):
    import orchestrator.cli.commands.run as run_module

    args = _stub_workflow_run(
        monkeypatch, tmp_path, execute_result={"status": "completed"}
    )
    monkeypatch.setattr(
        run_module, "open_executor_session", lambda *a, **kw: "sess-123"
    )
    monkeypatch.setattr(
        run_module, "close_executor_session",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("close boom")),
    )
    result = run_workflow(args)
    assert (result.exit_code, result.session_id, result.session_status) == (
        1, "sess-123", "failed")
    run = sorted((tmp_path / ".orchestrate" / "runs").iterdir())[0]
    persisted = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"


@pytest.mark.parametrize(
    "mode_args",
    [[], ["--returns", '{"mode":"scalar","type":"String"}']],
)
def test_control_character_model_rejected_before_destination(
    tmp_path, monkeypatch, fake_runtime, capsys, mode_args
):
    argv = ["prompt", "run", "--prompt", TASK_TEXT, "--provider",
            "omp_no_tools", "--model", "bad\x01model"] + mode_args
    code = _exit(argv, tmp_path, monkeypatch)
    assert code == 1
    assert fake_runtime.executed == []
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "prompt run:" in err
    assert not (tmp_path / ".orchestrate").exists()
    assert not (tmp_path / "workflows" / "generated").exists()

def test_run_workflow_body_and_close_exception_persists_failed_run(
    tmp_path, monkeypatch
):
    import orchestrator.cli.commands.run as run_module

    args = _stub_workflow_run(monkeypatch, tmp_path, execute_result={})
    monkeypatch.setattr(
        run_module, "WorkflowExecutor",
        lambda **kw: SimpleNamespace(
            execute=lambda **kw: (_ for _ in ()).throw(RuntimeError("body boom"))),
    )
    monkeypatch.setattr(
        run_module, "open_executor_session", lambda *a, **kw: "sess-123"
    )
    monkeypatch.setattr(
        run_module, "close_executor_session",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("close boom")),
    )
    result = run_workflow(args)
    assert (result.exit_code, result.session_id, result.session_status) == (
        1, "sess-123", "failed")
    run = sorted((tmp_path / ".orchestrate" / "runs").iterdir())[0]
    persisted = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
