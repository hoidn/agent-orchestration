"""Public target-2.25 trial SDK and CLI contract tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import inspect
import json
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType
from typing import Any

import pytest

from orchestrator.cli.main import create_parser, main
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.trial.sdk import (
    TRIAL_RUN_RESULT_SCHEMA_VERSION,
    TrialEntryRequestError,
    TrialRunOptions,
    TrialRunResult,
    run_trial_entry,
)
from tests.test_workflow_lisp_trial_lowering import (
    COMMIT_A,
    COMMIT_B,
    _build_trial,
    _write_trial_module,
)


def _options(workspace: Path) -> TrialRunOptions:
    return TrialRunOptions(
        source_roots=(workspace,),
        provider_externs_file=workspace / "providers.json",
        prompt_externs_file=workspace / "prompts.json",
        max_retries=0,
        retry_delay_ms=0,
    )


def _terminal_state(run_id: str) -> dict[str, object]:
    verdict = {
        "selected_arm": "direct",
        "budget_accounting": {"elapsed_ms": 17},
    }
    return {
        "run_id": run_id,
        "status": "completed",
        "steps": {
            "compare": {
                "status": "completed",
                "trial": {
                    "outcomes": [],
                    "verdict": verdict,
                    "verdict_artifact": "artifacts/trials/verdict.json",
                },
            }
        },
    }


def test_trial_run_result_is_frozen_closed_and_canonical() -> None:
    result = TrialRunResult.completed(
        run_id="run-1",
        verdict_digest="sha256:" + "a" * 64,
        verdict_path="artifacts/trials/verdict.json",
    )

    assert result.record == MappingProxyType(
        {
            "schema_version": TRIAL_RUN_RESULT_SCHEMA_VERSION,
            "run_id": "run-1",
            "terminal_status": "completed",
            "verdict_digest": "sha256:" + "a" * 64,
            "verdict_path": "artifacts/trials/verdict.json",
            "failure_diagnostic": None,
        }
    )
    assert json.loads(result.canonical_bytes) == dict(result.record)
    with pytest.raises(FrozenInstanceError):
        result.run_id = "changed"  # type: ignore[misc]


def test_trial_sdk_has_no_raw_config_or_runtime_injection_parameters() -> None:
    parameters = set(inspect.signature(run_trial_entry).parameters)

    assert parameters == {
        "workflow_file",
        "entry_workflow",
        "inputs",
        "workspace",
        "state_dir",
        "run_ref_root",
        "options",
    }
    assert {
        "workflow",
        "bundle",
        "executable_ir",
        "executor",
        "state_manager",
        "resume",
        "force_restart",
        "bypass",
    }.isdisjoint(parameters)


def test_trial_sdk_compiles_exact_pin_wrapper_through_ordinary_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.trial import sdk as sdk_module

    workspace = tmp_path.resolve()
    workflow_file = _write_trial_module(workspace).resolve()
    state_dir = (workspace / "state").resolve()
    run_ref_root = (workspace / "children").resolve()
    run_ref_root.mkdir()
    observed: dict[str, Any] = {}

    class FakeExecutor:
        def __init__(self, workflow, execution_workspace, state_manager, **kwargs):
            observed["workflow"] = workflow
            observed["workspace"] = execution_workspace
            observed["state_manager"] = state_manager
            observed["executor_options"] = kwargs

        def execute(self, **kwargs):
            observed["execute_options"] = kwargs
            state_manager = observed["state_manager"]
            return _terminal_state(state_manager.run_id)

    monkeypatch.setattr(sdk_module, "WorkflowExecutor", FakeExecutor)

    result = run_trial_entry(
        workflow_file=workflow_file,
        entry_workflow="compare",
        inputs={},
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
        options=_options(workspace),
    )

    assert result.terminal_status == "completed"
    assert result.verdict_digest == canonical_sha256(
        {
            "selected_arm": "direct",
            "budget_accounting": {"elapsed_ms": 17},
        }
    )
    assert result.verdict_path == "artifacts/trials/verdict.json"
    manager = observed["state_manager"]
    assert manager.state.result_persistence_profile == "derived_pure_replay.v1"
    assert manager.state.run_ref_root == run_ref_root.as_posix()
    compiled_frontend = manager.state.runtime_observability["compiled_frontend"]
    assert compiled_frontend["frontend_kind"] == "workflow_lisp"
    assert compiled_frontend["frontend_entry_workflow"] == "trial_lowering::compare"
    workflow = observed["workflow"]
    trial_configs = [
        node.execution_config.trial
        for node in workflow.ir.nodes.values()
        if node.kind.value == "trial"
    ]
    assert len(trial_configs) == 1
    assert [
        arm.run_ref.source.commit for arm in trial_configs[0].arms
    ] == [COMMIT_A, COMMIT_B]
    assert observed["execute_options"] == {
        "run_id": result.run_id,
        "on_error": "stop",
        "max_retries": 0,
        "retry_delay_ms": 0,
    }


def test_generated_exact_pin_wrapper_uses_same_sdk_and_cli_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.workflow.trial import sdk as sdk_module

    workspace = tmp_path.resolve()
    workflow_file = _write_trial_module(workspace).resolve()
    sdk_state_dir = (workspace / "sdk-state").resolve()
    cli_state_dir = (workspace / "cli-state").resolve()
    sdk_run_ref_root = (workspace / "sdk-children").resolve()
    cli_run_ref_root = (workspace / "cli-children").resolve()
    sdk_run_ref_root.mkdir()
    cli_run_ref_root.mkdir()
    observed: list[dict[str, object]] = []

    def execute_without_effects(self, **kwargs):
        trial_configs = [
            node.execution_config.trial
            for node in self.executable_ir.nodes.values()
            if node.kind.value == "trial"
        ]
        assert len(trial_configs) == 1
        observed.append(
            {
                "pins": tuple(
                    arm.run_ref.source.commit
                    for arm in trial_configs[0].arms
                ),
                "run_ref_root": self.state_manager.state.run_ref_root,
                "entry_workflow": self.state_manager.state.runtime_observability[
                    "compiled_frontend"
                ]["frontend_entry_workflow"],
                "execute_options": kwargs,
            }
        )
        return _terminal_state(self.state_manager.run_id)

    monkeypatch.setattr(
        sdk_module.WorkflowExecutor,
        "execute",
        execute_without_effects,
    )
    shared_options = TrialRunOptions(
        source_roots=(workspace,),
        provider_externs_file=workspace / "providers.json",
        prompt_externs_file=workspace / "prompts.json",
    )

    sdk_result = run_trial_entry(
        workflow_file=workflow_file,
        entry_workflow="compare",
        inputs={},
        workspace=workspace,
        state_dir=sdk_state_dir,
        run_ref_root=sdk_run_ref_root,
        options=shared_options,
    )

    monkeypatch.chdir(workspace)
    cli_exit = main(
        [
            "trial",
            workflow_file.as_posix(),
            "--entry-workflow",
            "compare",
            "--source-root",
            workspace.as_posix(),
            "--provider-externs-file",
            (workspace / "providers.json").as_posix(),
            "--prompt-externs-file",
            (workspace / "prompts.json").as_posix(),
            "--state-dir",
            cli_state_dir.as_posix(),
            "--run-ref-root",
            cli_run_ref_root.as_posix(),
        ]
    )

    cli_record = json.loads(capsys.readouterr().out)
    sdk_record = dict(sdk_result.record)
    assert cli_exit == 0
    assert sdk_record.pop("run_id") != cli_record.pop("run_id")
    assert cli_record == sdk_record
    assert [entry["pins"] for entry in observed] == [
        (COMMIT_A, COMMIT_B),
        (COMMIT_A, COMMIT_B),
    ]
    assert [entry["run_ref_root"] for entry in observed] == [
        sdk_run_ref_root.as_posix(),
        cli_run_ref_root.as_posix(),
    ]
    assert [entry["entry_workflow"] for entry in observed] == [
        "trial_lowering::compare",
        "trial_lowering::compare",
    ]
    assert len(tuple(sdk_state_dir.iterdir())) == 1
    assert len(tuple(cli_state_dir.iterdir())) == 1


def test_ordinary_cli_import_parse_and_dispatch_stay_trial_module_free(
    tmp_path: Path,
) -> None:
    code = r'''
import json
import importlib
import sys

cli_main = importlib.import_module("orchestrator.cli.main")

names = (
    "orchestrator.cli.commands.trial",
    "orchestrator.workflow.trial.sdk",
)
after_import = [name for name in names if name in sys.modules]
cli_main.create_parser().parse_args(["run", "ordinary.yaml"])
after_parse = [name for name in names if name in sys.modules]
cli_main.run_workflow = lambda _args: 0
exit_code = cli_main.main(["run", "ordinary.yaml"])
after_dispatch = [name for name in names if name in sys.modules]
print(json.dumps({
    "after_import": after_import,
    "after_parse": after_parse,
    "after_dispatch": after_dispatch,
    "exit_code": exit_code,
}))
'''

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "after_import": [],
        "after_parse": [],
        "after_dispatch": [],
        "exit_code": 0,
    }


def _write_plain_entry(workspace: Path, *, target: str) -> Path:
    source = workspace / "plain.orc"
    source.write_text(
        f'''\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule plain)
  (export run)
  (defworkflow run () -> String "not-a-trial"))
''',
        encoding="utf-8",
    )
    return source.resolve()


@pytest.mark.parametrize(
    ("target", "code"),
    (
        ("2.24", "trial_entry_target_unsupported"),
        ("2.25", "trial_entry_result_required"),
    ),
)
def test_trial_sdk_rejects_wrong_target_and_non_trial_terminal_result(
    tmp_path: Path,
    target: str,
    code: str,
) -> None:
    workspace = tmp_path.resolve()
    run_ref_root = (workspace / "children").resolve()
    run_ref_root.mkdir()

    with pytest.raises(TrialEntryRequestError) as raised:
        run_trial_entry(
            workflow_file=_write_plain_entry(workspace, target=target),
            entry_workflow="run",
            inputs={},
            workspace=workspace,
            state_dir=(workspace / "state").resolve(),
            run_ref_root=run_ref_root,
        )

    assert raised.value.code == code
    assert not (workspace / "state").exists()


def test_trial_sdk_rejects_non_orc_and_non_path_requests(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    wrong = workspace / "trial.json"
    wrong.write_text("{}", encoding="utf-8")

    with pytest.raises(TrialEntryRequestError) as raised:
        run_trial_entry(
            workflow_file=wrong,
            entry_workflow="compare",
            inputs={},
            workspace=workspace,
            state_dir=(workspace / "state").resolve(),
            run_ref_root=(workspace / "children").resolve(),
        )
    assert raised.value.code == "trial_entry_source_unsupported"

    with pytest.raises(TypeError, match="workflow_file must be a Path"):
        run_trial_entry(
            workflow_file=str(wrong),  # type: ignore[arg-type]
            entry_workflow="compare",
            inputs={},
            workspace=workspace,
            state_dir=(workspace / "state").resolve(),
            run_ref_root=(workspace / "children").resolve(),
        )


def test_trial_sdk_rejects_portable_runtime_pin_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.trial import sdk as sdk_module

    workspace = tmp_path.resolve()
    workflow_file = _write_trial_module(workspace).resolve()
    text = workflow_file.read_text(encoding="utf-8")
    text = text.replace(
        "(defworkflow compare () -> Value",
        "(defworkflow compare ((pin String)) -> Value",
    ).replace(f':commit "{COMMIT_A}"', ":commit pin", 1)
    workflow_file.write_text(text, encoding="utf-8")
    run_ref_root = (workspace / "children").resolve()
    run_ref_root.mkdir()
    monkeypatch.setattr(
        sdk_module,
        "WorkflowExecutor",
        lambda *_args, **_kwargs: pytest.fail("portable pin reached execution"),
    )

    with pytest.raises(TrialEntryRequestError) as raised:
        run_trial_entry(
            workflow_file=workflow_file,
            entry_workflow="compare",
            inputs={"pin": COMMIT_A},
            workspace=workspace,
            state_dir=(workspace / "state").resolve(),
            run_ref_root=run_ref_root,
            options=_options(workspace),
        )

    assert raised.value.code == "trial_entry_compile_failed"
    assert not (workspace / "state").exists()


def test_trial_sdk_rejects_compiler_result_digest_disagreement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.trial import sdk as sdk_module

    workspace = tmp_path.resolve()
    workflow_file, built = _build_trial(workspace)
    canonical_name = built.entry_selection.canonical_name
    typed_workflows = tuple(
        replace(
            workflow,
            signature=replace(
                workflow.signature,
                compiler_direct_result_contract_digest="sha256:" + "f" * 64,
            ),
        )
        if workflow.definition.name == canonical_name
        else workflow
        for workflow in built.compile_result.entry_result.typed_workflows
    )
    tampered = replace(
        built,
        compile_result=replace(
            built.compile_result,
            entry_result=replace(
                built.compile_result.entry_result,
                typed_workflows=typed_workflows,
            ),
        ),
    )
    monkeypatch.setattr(
        sdk_module,
        "build_frontend_bundle",
        lambda _request: tampered,
    )

    with pytest.raises(TrialEntryRequestError) as raised:
        sdk_module._compile_trial_entry(
            workflow_file=workflow_file.resolve(),
            entry_workflow="compare",
            workspace=workspace,
            options=_options(workspace),
        )

    assert raised.value.code == "trial_entry_result_required"


def test_trial_cli_routes_only_ordinary_flags_and_prints_sdk_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.cli.commands import trial as trial_command

    workflow_file = (tmp_path / "entry.orc").resolve()
    workspace = tmp_path.resolve()
    state_dir = (workspace / "state").resolve()
    run_ref_root = (workspace / "children").resolve()
    providers = (workspace / "providers.json").resolve()
    prompts = (workspace / "prompts.json").resolve()
    observed: dict[str, object] = {}
    expected = TrialRunResult.completed(
        run_id="run-cli",
        verdict_digest="sha256:" + "b" * 64,
        verdict_path="artifacts/trials/verdict.json",
    )

    def fake_run_trial_entry(**kwargs):
        observed.update(kwargs)
        return expected

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(trial_command, "run_trial_entry", fake_run_trial_entry)

    exit_code = main(
        [
            "trial",
            workflow_file.as_posix(),
            "--entry-workflow",
            "compare",
            "--input",
            "task=measure",
            "--source-root",
            workspace.as_posix(),
            "--provider-externs-file",
            providers.as_posix(),
            "--prompt-externs-file",
            prompts.as_posix(),
            "--state-dir",
            state_dir.as_posix(),
            "--run-ref-root",
            run_ref_root.as_posix(),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.encode("utf-8") == expected.canonical_bytes + b"\n"
    assert observed["workflow_file"] == workflow_file
    assert observed["workspace"] == workspace
    assert observed["inputs"] == {"task": "measure"}
    assert observed["state_dir"] == state_dir
    assert observed["run_ref_root"] == run_ref_root
    options = observed["options"]
    assert options == TrialRunOptions(
        source_roots=(workspace,),
        provider_externs_file=providers,
        prompt_externs_file=prompts,
    )


def test_trial_cli_failure_summary_has_matching_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.cli.commands import trial as trial_command

    failed = TrialRunResult.failed(
        run_id="run-failed",
        code="trial_run_failed",
        message="provider stopped",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(trial_command, "run_trial_entry", lambda **_kwargs: failed)

    exit_code = main(
        [
            "trial",
            "entry.orc",
            "--entry-workflow",
            "compare",
            "--state-dir",
            "state",
            "--run-ref-root",
            (tmp_path / "children").resolve().as_posix(),
        ]
    )

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out) == dict(failed.record)


@pytest.mark.parametrize("flag", ("--dry-run", "--force-restart", "--executor"))
def test_trial_cli_rejects_bypass_flags(flag: str) -> None:
    parser = create_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "trial",
                "entry.orc",
                "--entry-workflow",
                "compare",
                "--state-dir",
                "state",
                "--run-ref-root",
                "children",
                flag,
            ]
        )


def test_trial_cli_requires_explicit_entry_workflow() -> None:
    with pytest.raises(SystemExit):
        create_parser().parse_args(["trial", "entry.orc"])
