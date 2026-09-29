from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.providers import (
    ProviderExecutor,
    ProviderParams,
    ProviderRegistry,
    ProviderSessionMode,
    ProviderSessionRequest,
)
from orchestrator.workflow_lisp.build import build_frontend_bundle_in_memory
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_adjudicated_provider_loader import (
    _base_workflow as _base_adjudicated_workflow,
    _load as _load_adjudicated_workflow,
)
from tests.test_workflow_lisp_provider_call_policy_e2e import (
    _build_request,
    _copy_fixture,
    _run_args,
    _run_argv,
)
from tests.test_workflow_lisp_provider_peer_group import (
    _module_source as _peer_module_source,
)
from tests.test_workflow_lisp_provider_supervision import (
    _module_source as _supervision_module_source,
)
from tests.test_workflow_lisp_provider_supervision import _write_module


def _provider_call_without_policy(
    source: str,
    *,
    model: bool = True,
    effort: bool = True,
) -> str:
    if model:
        source = source.replace(":model model", "")
    if effort:
        source = source.replace(":effort effort", "")
    return source


def test_codex_default_model_and_cli_reasoning_key(tmp_path: Path) -> None:
    registry = ProviderRegistry()
    executor = ProviderExecutor(tmp_path, registry)

    default, error = executor.prepare_invocation(
        "codex", ProviderParams(), {}, "prompt"
    )
    overridden, override_error = executor.prepare_invocation(
        "codex",
        ProviderParams(),
        {},
        "prompt",
        provider_call_policy={"model": "explicit-model", "effort": "medium"},
    )

    assert error is override_error is None
    assert default is not None
    assert overridden is not None
    assert default.command[default.command.index("--model") + 1] == "gpt-5.5"
    assert default.command[default.command.index("--config") + 1] == (
        "model_reasoning_effort=high"
    )
    assert overridden.command[overridden.command.index("--model") + 1] == (
        "explicit-model"
    )
    assert overridden.command[overridden.command.index("--config") + 1] == (
        "model_reasoning_effort=medium"
    )


@pytest.mark.parametrize(
    "provider_name",
    (
        "codex",
        "codex_gpt55",
        "codex_unrestricted_workspace",
        "codex_gpt55_unrestricted_workspace",
    ),
)
def test_codex_command_profiles_use_cli_config_key(
    tmp_path: Path,
    provider_name: str,
) -> None:
    executor = ProviderExecutor(tmp_path, ProviderRegistry())
    invocation, error = executor.prepare_invocation(
        provider_name,
        ProviderParams(),
        {},
        "prompt",
        provider_call_policy={"model": "chosen-model", "effort": "medium"},
    )

    assert error is None
    assert invocation is not None
    assert "model_reasoning_effort=medium" in invocation.command


@pytest.mark.parametrize(
    ("provider_name", "session_mode"),
    (
        ("codex", ProviderSessionMode.FRESH),
        ("codex", ProviderSessionMode.RESUME),
        ("codex_gpt55", ProviderSessionMode.FRESH),
        ("codex_gpt55", ProviderSessionMode.RESUME),
    ),
)
def test_codex_session_commands_use_cli_config_key(
    tmp_path: Path,
    provider_name: str,
    session_mode: ProviderSessionMode,
) -> None:
    executor = ProviderExecutor(tmp_path, ProviderRegistry())
    invocation, error = executor.prepare_invocation(
        provider_name,
        ProviderParams(),
        {},
        "prompt",
        session_request=ProviderSessionRequest(
            mode=session_mode,
            session_id="session-id" if session_mode == ProviderSessionMode.RESUME else None,
        ),
        provider_call_policy={"model": "chosen-model", "effort": "medium"},
    )

    assert error is None
    assert invocation is not None
    assert "model_reasoning_effort=medium" in invocation.command


def test_codex_interactive_command_uses_cli_config_key(tmp_path: Path) -> None:
    executor = ProviderExecutor(tmp_path, ProviderRegistry())
    invocation, error = executor.prepare_interactive_invocation(
        provider_name="codex",
        params={},
        context={},
        prompt_content="turn",
        invocation_id="invocation",
        member_id="worker",
        attempt_scope_key="sha256:" + "a" * 64,
        attempt_ordinal=1,
        cwd=tmp_path,
        provider_call_policy={"model": "chosen-model", "effort": "medium"},
    )

    assert error is None
    assert invocation is not None
    assert "model_reasoning_effort=medium" in invocation.pre_prompt_command


@pytest.mark.parametrize(
    ("provider_profile", "remove_model", "remove_effort", "missing_params"),
    (
        ("codex_unrestricted_workspace", True, True, ("model", "reasoning_effort")),
        ("claude_unrestricted_workspace", True, True, ("model", "effort")),
        ("codex_unrestricted_workspace", False, True, ("reasoning_effort",)),
        ("claude_unrestricted_workspace", True, False, ("model",)),
    ),
)
def test_unrestricted_missing_params_have_located_build_diagnostic(
    tmp_path: Path,
    provider_profile: str,
    remove_model: bool,
    remove_effort: bool,
    missing_params: tuple[str, ...],
) -> None:
    files = _copy_fixture(tmp_path, provider_profile)
    source = files["policy_e2e.orc"].read_text(encoding="utf-8")
    provider_alias = (
        "providers.public_codex"
        if provider_profile == "codex_unrestricted_workspace"
        else "providers.public_claude"
    )
    provider_call = f"""(provider-result {provider_alias}
               :prompt prompts.public_execute
               :inputs ()
               :model model
               :effort effort
               :timeout-sec 7200
               :returns WorkResult)"""
    provider_call_line = source[: source.index(provider_call)].count("\n") + 1
    missing_call = _provider_call_without_policy(
        provider_call,
        model=remove_model,
        effort=remove_effort,
    )
    source = source.replace(
        provider_call,
        f"(if true\n                 {missing_call}\n                 {provider_call})",
        1,
    )
    call_line = provider_call_line + 1
    files["policy_e2e.orc"].write_text(source, encoding="utf-8")
    call_column = (
        source.splitlines()[call_line - 1].index("(provider-result") + 1
    )

    with pytest.raises(LispFrontendCompileError) as error:
        build_frontend_bundle_in_memory(_build_request(tmp_path, files))

    diagnostic = next(
        item
        for item in error.value.diagnostics
        if item.code == "provider_parameters_missing"
    )
    assert Path(diagnostic.span.start.path) == files["policy_e2e.orc"]
    assert diagnostic.span.start.line == call_line
    assert diagnostic.span.start.column == call_column
    assert all(param in diagnostic.message for param in missing_params)
    assert provider_profile in diagnostic.message
    assert "policy-model" not in diagnostic.message
    assert "policy-effort" not in diagnostic.message
    assert not diagnostic.notes


def test_defaulted_and_dynamic_provider_parameters_pass_early_check(
    tmp_path: Path,
) -> None:
    defaulted_workspace = tmp_path / "defaulted"
    defaulted_workspace.mkdir()
    files = _copy_fixture(defaulted_workspace, "codex_unrestricted_workspace")
    providers = json.loads(files["providers.json"].read_text(encoding="utf-8"))
    providers["providers.public_codex"] = "codex_gpt55_unrestricted_workspace"
    files["providers.json"].write_text(json.dumps(providers), encoding="utf-8")
    files["policy_e2e.orc"].write_text(
        _provider_call_without_policy(
            files["policy_e2e.orc"].read_text(encoding="utf-8")
        ),
        encoding="utf-8",
    )
    assert build_frontend_bundle_in_memory(
        _build_request(defaulted_workspace, files)
    ).validated_bundle

    dynamic_workspace = tmp_path / "dynamic"
    dynamic_workspace.mkdir()
    dynamic_files = _copy_fixture(
        dynamic_workspace, "codex_unrestricted_workspace"
    )
    assert build_frontend_bundle_in_memory(
        _build_request(dynamic_workspace, dynamic_files)
    ).validated_bundle


@pytest.mark.parametrize(
    "provider_profile",
    ("codex_unrestricted_workspace", "claude_unrestricted_workspace"),
)
def test_public_dry_run_reports_missing_provider_params_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    provider_profile: str,
) -> None:
    files = _copy_fixture(tmp_path, provider_profile)
    files["policy_e2e.orc"].write_text(
        _provider_call_without_policy(
            files["policy_e2e.orc"].read_text(encoding="utf-8")
        ),
        encoding="utf-8",
    )
    args = _run_args(files)
    args.dry_run = True
    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.ERROR)

    with patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError("missing params must fail before provider execution"),
    ), patch.object(sys, "argv", _run_argv(files)):
        result = run_workflow(args)

    assert result.exit_code == 2
    assert "[provider_parameters_missing]" in caplog.text
    assert str(files["policy_e2e.orc"]) in caplog.text
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_supervision_member_missing_params_have_located_build_diagnostic(
    tmp_path: Path,
) -> None:
    source = _supervision_module_source(
        "2.16",
        "(defworkflow orchestrate () -> String "
        "(with-live-providers "
        "((worker (provider-result providers.worker "
        ":prompt prompts.worker :inputs () :timeout-sec 30 :returns String)) "
        "(supervisor (provider-result providers.supervisor "
        ":prompt prompts.supervisor :inputs () :timeout-sec 20 "
        ":returns ProviderSteeringDirective) :observes worker)) worker))",
    )
    path = _write_module(tmp_path / "supervision_missing_params.orc", source)
    for prompt_name in ("worker", "supervisor"):
        prompt = tmp_path / "prompts" / f"{prompt_name}.md"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text("prompt\n", encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as error:
        compile_stage3_module(
            path,
            entry_workflow="orchestrate",
            provider_externs={
                "providers.worker": "codex",
                "providers.supervisor": "codex_unrestricted_workspace",
            },
            prompt_externs={
                "prompts.worker": "prompts/worker.md",
                "prompts.supervisor": "prompts/supervisor.md",
            },
            validate_shared=True,
            workspace_root=tmp_path,
        )

    diagnostic = next(
        item
        for item in error.value.diagnostics
        if item.code == "provider_parameters_missing"
    )
    assert Path(diagnostic.span.start.path) == path
    assert diagnostic.span.start.line > 1
    assert diagnostic.span.start.column > 1
    assert not diagnostic.notes
    assert "supervisor" in diagnostic.message
    assert "codex_unrestricted_workspace" in diagnostic.message
    assert "model" in diagnostic.message
    assert "reasoning_effort" in diagnostic.message


def test_peer_members_missing_params_have_located_build_diagnostic(
    tmp_path: Path,
) -> None:
    source = _peer_module_source(
        "2.17",
        "(defworkflow orchestrate () -> String "
        "(with-live-provider-peers "
        "((planner (provider-result providers.planner "
        ":prompt prompts.planner :inputs () :timeout-sec 30 :returns String)) "
        "(reviewer (provider-result providers.reviewer "
        ":prompt prompts.reviewer :inputs () :timeout-sec 20 :returns String)) "
        ") planner))",
    )
    path = tmp_path / "peer_missing_params.orc"
    path.write_text(source, encoding="utf-8")
    for prompt_name in ("planner", "reviewer"):
        prompt = tmp_path / "prompts" / f"{prompt_name}.md"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text("prompt\n", encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as error:
        compile_stage3_module(
            path,
            entry_workflow="orchestrate",
            provider_externs={
                "providers.planner": "codex_unrestricted_workspace",
                "providers.reviewer": "claude_unrestricted_workspace",
            },
            prompt_externs={
                "prompts.planner": "prompts/planner.md",
                "prompts.reviewer": "prompts/reviewer.md",
            },
            validate_shared=True,
            workspace_root=tmp_path,
        )

    diagnostics = [
        item
        for item in error.value.diagnostics
        if item.code == "provider_parameters_missing"
    ]
    assert len(diagnostics) == 2
    assert {Path(item.span.start.path) for item in diagnostics} == {path}
    assert all(item.span.start.line > 1 for item in diagnostics)
    assert all(item.span.start.column > 1 for item in diagnostics)
    assert all(not item.notes for item in diagnostics)
    assert any("member 'planner'" in item.message for item in diagnostics)
    assert any("member 'reviewer'" in item.message for item in diagnostics)


def test_adjudication_candidate_and_evaluator_missing_params_fail_early(
    tmp_path: Path,
) -> None:
    (tmp_path / "prompt.md").write_text("prompt\n", encoding="utf-8")
    (tmp_path / "evaluator.md").write_text("evaluator\n", encoding="utf-8")
    workflow = _base_adjudicated_workflow()
    adjudication = workflow["steps"][0]["adjudicated_provider"]
    adjudication["candidates"][0]["provider"] = (
        "codex_unrestricted_workspace"
    )
    adjudication["candidates"][0]["provider_call_policy"] = {
        "model": "ignored-candidate-model",
        "effort": "ignored-candidate-effort",
    }
    adjudication["evaluator"]["provider"] = (
        "claude_unrestricted_workspace"
    )
    adjudication["evaluator"]["provider_call_policy"] = {
        "model": "ignored-evaluator-model",
        "effort": "ignored-evaluator-effort",
    }

    with pytest.raises(WorkflowValidationError) as error:
        _load_adjudicated_workflow(tmp_path, workflow)

    missing = [
        item
        for item in error.value.errors
        if item.message.startswith("provider_parameters_missing:")
    ]
    assert len(missing) == 2
    assert {item.subject_refs[0].subject_name for item in missing} == {"draft"}
    candidate_error = next(
        item for item in missing if "candidate 'fake_a'" in item.message
    )
    evaluator_error = next(
        item for item in missing if "evaluator" in item.message
    )
    assert "model, reasoning_effort" in candidate_error.message
    assert "effort, model" in evaluator_error.message

    adjudication["candidates"][0]["provider_params"] = {
        "model": "candidate-model",
        "reasoning_effort": "high",
    }
    adjudication["evaluator"]["provider_params"] = {
        "model": "evaluator-model",
        "effort": "high",
    }
    assert _load_adjudicated_workflow(tmp_path, workflow)
