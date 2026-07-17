"""Public compile/run/resume acceptance for Workflow Lisp provider call policy."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.providers import InputMode
from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle
from orchestrator.workflow_lisp.lexical_checkpoint_restore import select_restore_candidate
from orchestrator.workflow_lisp.lexical_checkpoints import resolve_checkpoint_index_path


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "workflow_lisp" / "provider_call_policy"
)
POLICY_FIXTURE_FILES = (
    "policy.orc",
    "prompt.md",
    "prompts.json",
    "providers.json",
    "finish.py",
    "commands.json",
)
MODEL = "policy-model"
EFFORT = "policy-effort"
TIMEOUT_SEC = 7200

EXPECTED_COMMANDS = {
    "codex_unrestricted_workspace": [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        MODEL,
        "--config",
        f"reasoning_effort={EFFORT}",
    ],
    "claude_unrestricted_workspace": [
        "claude",
        "-p",
        "--model",
        MODEL,
        "--effort",
        EFFORT,
        "--permission-mode",
        "bypassPermissions",
    ],
}
PROVIDER_EXTERNS = {
    "codex_unrestricted_workspace": "providers.public_codex",
    "claude_unrestricted_workspace": "providers.public_claude",
}


class _PostPersistInterruption(BaseException):
    pass


def _copy_fixture(workspace: Path, provider_profile: str) -> dict[str, Path]:
    copied: dict[str, Path] = {}
    for name in POLICY_FIXTURE_FILES:
        destination = workspace / name
        destination.write_bytes((FIXTURE_ROOT / name).read_bytes())
        copied[name] = destination
    nested_prompt = workspace / "tests/fixtures/workflow_lisp/provider_call_policy/prompt.md"
    nested_prompt.parent.mkdir(parents=True, exist_ok=True)
    nested_prompt.write_bytes((FIXTURE_ROOT / "prompt.md").read_bytes())
    copied["policy.orc"].write_text(
        copied["policy.orc"]
        .read_text(encoding="utf-8")
        .replace(
            '  (:target-dsl "2.15")\n',
            '  (:target-dsl "2.15")\n  (defmodule policy)\n  (export policy)\n',
            1,
        )
        .replace("providers.execute", PROVIDER_EXTERNS[provider_profile])
        .replace("prompts.execute", "prompts.public_execute"),
        encoding="utf-8",
    )
    return copied


def _build_request(workspace: Path, files: dict[str, Path]) -> FrontendBuildRequest:
    return FrontendBuildRequest(
        source_path=files["policy.orc"],
        source_roots=(workspace,),
        entry_workflow="policy",
        provider_externs_path=files["providers.json"],
        prompt_externs_path=files["prompts.json"],
        imported_workflow_bundles_path=None,
        command_boundaries_path=files["commands.json"],
        emit_debug_yaml=True,
        workspace_root=workspace,
    )


def _run_args(files: dict[str, Path]) -> Namespace:
    return Namespace(
        workflow=str(files["policy.orc"]),
        context=None,
        context_file=None,
        input=[f"model={MODEL}", f"effort={EFFORT}"],
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=False,
        backup_state=False,
        state_dir=None,
        on_error="stop",
        max_retries=0,
        retry_delay=0,
        quiet=True,
        verbose=False,
        log_level="error",
        step_summaries=False,
        summary_mode=None,
        summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow="policy",
        source_root=[str(files["policy.orc"].parent)],
        provider_externs_file=str(files["providers.json"]),
        prompt_externs_file=str(files["prompts.json"]),
        imported_workflow_bundles_file=None,
        command_boundaries_file=str(files["commands.json"]),
        emit_debug_yaml=True,
    )


def _run_argv(files: dict[str, Path]) -> list[str]:
    return [
        "orchestrator",
        "run",
        str(files["policy.orc"]),
        "--source-root",
        str(files["policy.orc"].parent),
        "--entry-workflow",
        "policy",
        "--provider-externs-file",
        str(files["providers.json"]),
        "--prompt-externs-file",
        str(files["prompts.json"]),
        "--command-boundaries-file",
        str(files["commands.json"]),
        "--emit-debug-yaml",
    ]


def _state(workspace: Path, run_id: str) -> dict[str, object]:
    return json.loads(
        (workspace / ".orchestrate" / "runs" / run_id / "state.json").read_text(
            encoding="utf-8"
        )
    )


def _only_run_id(workspace: Path) -> str:
    run_roots = list((workspace / ".orchestrate" / "runs").iterdir())
    assert len(run_roots) == 1
    return run_roots[0].name


def _persisted_checkpoint_record(executor: WorkflowExecutor, finalized: dict) -> dict:
    step_id = finalized["step_id"]
    point = next(
        (
            candidate
            for candidate in executor.runtime_plan.lexical_checkpoint_points
            if candidate.step_id == step_id
        ),
        None,
    )
    if point is None:
        return {}
    index_path = resolve_checkpoint_index_path(
        state_manager=executor.state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = executor.workspace / index["records"][-1]["record_path"]
    return json.loads(record_path.read_text(encoding="utf-8"))


def _interrupt_public_run(
    workspace: Path,
    files: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, list[object], object]:
    invocations: list[object] = []

    def execute_provider(_self, invocation, **_kwargs):
        invocations.append(invocation)
        bundle_path = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps({"approved": True, "summary": "provider boundary"}) + "\n",
            encoding="utf-8",
        )
        return ProviderExecutionResult(exit_code=0, stdout=b"", stderr=b"", duration_ms=1)

    original_post_persist = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit

    def interrupt_after_provider_checkpoint(self, state, step_name, step, finalized):
        original_post_persist(self, state, step_name, step, finalized)
        record = _persisted_checkpoint_record(self, finalized)
        refs = record.get("completed_effect_refs", [])
        if refs and refs[0].get("effect_kind") == "provider":
            raise _PostPersistInterruption

    monkeypatch.chdir(workspace)
    with patch.object(ProviderExecutor, "execute", execute_provider), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_provider_checkpoint,
    ), patch.object(sys, "argv", _run_argv(files)):
        with pytest.raises(_PostPersistInterruption):
            run_workflow(_run_args(files))
    return _only_run_id(workspace), invocations, execute_provider


@pytest.mark.parametrize(
    "provider_profile",
    ["codex_unrestricted_workspace", "claude_unrestricted_workspace"],
)
def test_public_compile_run_resume_uses_call_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_profile: str,
) -> None:
    files = _copy_fixture(tmp_path, provider_profile)
    built = build_frontend_bundle(_build_request(tmp_path, files))
    assert built.validated_bundle.surface.name.endswith("policy")

    invocations = []
    interrupted_records = []

    def execute_provider(_self, invocation, **_kwargs):
        invocations.append(invocation)
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps({"approved": True, "summary": "provider boundary"}) + "\n",
            encoding="utf-8",
        )
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"provider stdout is observability only",
            stderr=b"",
            duration_ms=1,
        )

    original_post_persist = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit

    def interrupt_after_provider_checkpoint(self, state, step_name, step, finalized):
        original_post_persist(self, state, step_name, step, finalized)
        record = _persisted_checkpoint_record(self, finalized)
        refs = record.get("completed_effect_refs", [])
        if not refs or refs[0].get("effect_kind") != "provider":
            return
        barrier = record.get("restore_payload", {}).get("completed_effect_barrier")
        assert barrier == {
            "effect_kind": "provider",
            "step_id": refs[0]["step_id"],
            "source_map_origin_key": refs[0]["source_map_origin_key"],
            "completed_effect_refs_digest": record["validity_envelope"][
                "completed_effect_refs_digest"
            ],
        }
        interrupted_records.append(record)
        raise _PostPersistInterruption

    monkeypatch.chdir(tmp_path)
    with patch.object(ProviderExecutor, "execute", execute_provider), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_provider_checkpoint,
    ), patch.object(sys, "argv", _run_argv(files)):
        with pytest.raises(_PostPersistInterruption):
            run_workflow(_run_args(files))

    assert len(invocations) == 1
    assert len(interrupted_records) == 1
    invocation = invocations[0]
    assert invocation.input_mode == InputMode.STDIN
    assert invocation.command == EXPECTED_COMMANDS[provider_profile]
    assert invocation.timeout_sec == TIMEOUT_SEC

    run_id = _only_run_id(tmp_path)
    interrupted = _state(tmp_path, run_id)
    provider_step = next(
        step
        for step in interrupted["steps"].values()
        if step.get("artifacts", {}).get("summary") == "provider boundary"
    )
    assert provider_step["status"] == "completed"
    assert provider_step["artifacts"] == {
        "approved": True,
        "summary": "provider boundary",
    }
    assert not any(step.get("status") == "failed" for step in interrupted["steps"].values())
    command_point = next(
        point
        for point in built.validated_bundle.runtime_plan.lexical_checkpoint_points
        if point.details.get("effect_boundary", {}).get("effect_kind") == "command"
    )
    assert not any(
        step.get("step_id") == command_point.step_id
        for step in interrupted["steps"].values()
    )
    interrupted_state_manager = StateManager(tmp_path, run_id=run_id)
    command_index_path = resolve_checkpoint_index_path(
        state_manager=interrupted_state_manager,
        workflow_name=command_point.workflow_name,
        checkpoint_id=command_point.checkpoint_id,
    )
    assert not command_index_path.exists()
    command_decision = select_restore_candidate(
        state_manager=interrupted_state_manager,
        runtime_plan=built.validated_bundle.runtime_plan,
        state=interrupted_state_manager.load().to_dict(),
        checkpoint_id=command_point.checkpoint_id,
        executable_workflow=built.validated_bundle.ir,
        loaded_workflow=built.validated_bundle,
    )
    assert command_decision.kind == "NOT_RESTORABLE"
    assert command_decision.selection_observation == "record_absent"

    (tmp_path / "finish.marker").write_text("resume\n", encoding="utf-8")
    import orchestrator.cli.commands.resume as resume_command

    original_build = resume_command.build_frontend_bundle
    original_command = WorkflowExecutor._execute_command
    command_executions = []

    def execute_command(self, step, state):
        command_executions.append(step["name"])
        return original_command(self, step, state)

    with patch.object(ProviderExecutor, "execute", execute_provider), patch.object(
        resume_command,
        "build_frontend_bundle",
        wraps=original_build,
    ) as resume_build, patch.object(WorkflowExecutor, "_execute_command", execute_command):
        resume_exit = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
            retry_delay_ms=0,
        )

    assert resume_exit == 0
    assert resume_build.call_count == 1
    resume_request = resume_build.call_args.args[0]
    assert (tmp_path / resume_request.source_path).resolve() == files["policy.orc"].resolve()
    assert resume_request.source_roots == (tmp_path.resolve(),)
    assert len(invocations) == 1
    assert len(command_executions) == 1

    completed = _state(tmp_path, run_id)
    assert completed["run_id"] == run_id
    assert {
        "model": completed["bound_inputs"]["model"],
        "effort": completed["bound_inputs"]["effort"],
    } == {"model": MODEL, "effort": EFFORT}
    assert completed["status"] == "completed"
    assert completed["workflow_outputs"] == {
        "return__approved": True,
        "return__summary": "resumed command",
    }
    default_resume = json.loads(
        (
            tmp_path
            / ".orchestrate"
            / "runs"
            / run_id
            / "workflow_lisp"
            / "checkpoints"
            / "default_resume_report.json"
        ).read_text(encoding="utf-8")
    )
    assert default_resume["selection_reason"] == "validated_prior_boundary"


@pytest.mark.parametrize(
    "drift_kind",
    ["literal", "binding", "added_keyword", "removed_keyword"],
)
def test_public_resume_rejects_provider_call_policy_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_kind: str,
) -> None:
    files = _copy_fixture(tmp_path, "codex_unrestricted_workspace")
    if drift_kind == "added_keyword":
        files["policy.orc"].write_text(
            files["policy.orc"].read_text(encoding="utf-8").replace(
                "               :timeout-sec 7200\n",
                "",
            ),
            encoding="utf-8",
        )
    run_id, invocations, execute_provider = _interrupt_public_run(
        tmp_path,
        files,
        monkeypatch,
    )
    source = files["policy.orc"].read_text(encoding="utf-8")
    if drift_kind == "literal":
        source = source.replace(":timeout-sec 7200", ":timeout-sec 7201")
    elif drift_kind == "binding":
        source = source.replace(":model model", ":model effort")
    elif drift_kind == "added_keyword":
        source = source.replace(
            "               :effort effort\n",
            "               :effort effort\n               :timeout-sec 7200\n",
        )
    else:
        source = source.replace("               :effort effort\n", "")
    files["policy.orc"].write_text(source, encoding="utf-8")

    command_launches: list[str] = []

    def observe_command(self, step, state):
        command_launches.append(step["name"])
        raise AssertionError("command must not launch after provider policy drift")

    with patch.object(ProviderExecutor, "execute", execute_provider), patch.object(
        WorkflowExecutor,
        "_execute_command",
        observe_command,
    ):
        resume_exit = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
            retry_delay_ms=0,
        )

    assert resume_exit != 0
    assert len(invocations) == 1
    assert command_launches == []


def test_resume_rebuilds_non_authoritative_views_and_rejects_authoritative_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view_workspace = tmp_path / "view-only"
    view_workspace.mkdir()
    view_files = _copy_fixture(view_workspace, "codex_unrestricted_workspace")
    view_run_id, view_invocations, view_provider = _interrupt_public_run(
        view_workspace,
        view_files,
        monkeypatch,
    )
    build_root = next((view_workspace / ".orchestrate" / "build").iterdir())
    for name in ("expanded.debug.yaml", "runtime_plan.json", "source_map.json"):
        (build_root / name).write_text("tampered non-authority view\n", encoding="utf-8")
    (view_workspace / "finish.marker").write_text("resume\n", encoding="utf-8")
    with patch.object(ProviderExecutor, "execute", view_provider):
        assert resume_workflow(
            run_id=view_run_id,
            repair=False,
            force_restart=False,
            retry_delay_ms=0,
        ) == 0
    assert len(view_invocations) == 1

    source_workspace = tmp_path / "source-authority"
    source_workspace.mkdir()
    source_files = _copy_fixture(source_workspace, "codex_unrestricted_workspace")
    source_run_id, source_invocations, source_provider = _interrupt_public_run(
        source_workspace,
        source_files,
        monkeypatch,
    )
    source = source_files["policy.orc"].read_text(encoding="utf-8")
    source_files["policy.orc"].write_text(
        source.replace(":model model", ":model effort"),
        encoding="utf-8",
    )
    command_launches: list[str] = []

    def observe_command(self, step, state):
        command_launches.append(step["name"])
        raise AssertionError("view files must not authorize source drift")

    with patch.object(ProviderExecutor, "execute", source_provider), patch.object(
        WorkflowExecutor,
        "_execute_command",
        observe_command,
    ):
        source_resume_exit = resume_workflow(
            run_id=source_run_id,
            repair=False,
            force_restart=False,
            retry_delay_ms=0,
        )
    assert source_resume_exit != 0
    assert len(source_invocations) == 1
    assert command_launches == []
