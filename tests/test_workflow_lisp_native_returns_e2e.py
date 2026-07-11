"""Declarative end-to-end acceptance for native transportable returns.

Compiles real preview-v2.15 `.orc` provider and command results that each
write direct JSON `true`/`false`, branches on the resulting `Bool`, persists
state, resumes, and asserts no wrapper object, no stdout extraction, no
authored `__result__` access, and no name-specific lowering.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid"
PROVIDER_FIXTURE = FIXTURES / "native_bool_provider_branch.orc"
COMMAND_FIXTURE = FIXTURES / "native_bool_command_branch.orc"


def _copy_fixture(workspace: Path, fixture: Path) -> Path:
    local = workspace / fixture.name
    local.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    return local


def _bool_bundle_command(workspace: Path, name: str, value: str) -> ExternalToolBinding:
    scripts = workspace / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / f"{name}.py").write_text(
        "import os, pathlib\n"
        'bundle = pathlib.Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        f'bundle.write_text("{value}\\n", encoding="utf-8")\n'
        'print("stdout must stay a sidecar")\n',
        encoding="utf-8",
    )
    return ExternalToolBinding(name=name, stable_command=("python", f"scripts/{name}.py"))


def _provider_executor_patches(workspace: Path, document: str):
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
        bundle_path = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(document + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"stdout must stay a sidecar",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    return (
        patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation),
        patch.object(ProviderExecutor, "execute", _execute),
    )


def _bind_and_execute(bundle, workspace: Path, run_id: str, module_path: Path, inputs: dict):
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(binding_inputs, inputs, workspace)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return state_manager


def test_provider_root_bool_result_drives_branching_persists_and_resumes(
    tmp_path: Path,
) -> None:
    module_path = _copy_fixture(tmp_path, PROVIDER_FIXTURE)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review the change.\n", encoding="utf-8")
    work = tmp_path / "artifacts" / "work"
    work.mkdir(parents=True)
    (work / "summary.json").write_text("{}\n", encoding="utf-8")

    source_text = module_path.read_text(encoding="utf-8")
    assert "__result__" not in source_text

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={"providers.review": "fake-review-provider"},
        prompt_externs={"prompts.review": {"input_file": "prompts/review.md"}},
        command_boundaries={
            "record_approved": _bool_bundle_command(tmp_path, "record_approved", "true"),
            "record_revise": _bool_bundle_command(tmp_path, "record_revise", "true"),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        validated
        for name, validated in result.validated_bundles_by_name.items()
        if name.endswith("::decide") or name == "decide"
    )
    run_id = "native-provider-branch"
    state_manager = _bind_and_execute(
        bundle, tmp_path, run_id, module_path, {"summary_target": "artifacts/work/summary.json"}
    )

    # Fail once at the materialize-view boundary to force an interrupted run,
    # then resume it -- proving state persists and the run is resumable, not
    # just a single-shot execution.
    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic materialize-view failure")
        return real_render_view(*args, **kwargs)

    p1, p2 = _provider_executor_patches(tmp_path, "true")
    with p1, p2, patch(
        "orchestrator.workflow.executor.render_view", side_effect=_fail_render_once
    ):
        first_run = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first_run["status"] == "failed"
    provider_step = first_run["steps"]["native_bool_provider_branch::decide__approved"]
    assert provider_step["artifacts"] == {"__result__": True}
    assert provider_step["output"] != json.dumps(True)

    resume_manager = StateManager(workspace=tmp_path, run_id=run_id)
    resume_manager.load()
    p1, p2 = _provider_executor_patches(tmp_path, "true")
    with p1, p2:
        resumed = WorkflowExecutor(bundle, tmp_path, resume_manager, retry_delay_ms=0).execute(
            resume=True
        )

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": True}
    branch_step = next(
        step
        for name, step in resumed["steps"].items()
        if name.endswith("record_approved")
    )
    assert branch_step["artifacts"] == {"__result__": True}
    # No stdout parsing: the captured raw output text is the sidecar marker,
    # never the parsed boolean value or a wrapper object.
    for step in resumed["steps"].values():
        assert "json" not in step
        assert "lines" not in step
        if "output" in step:
            assert step["output"] != "true\n"


def test_command_root_bool_result_drives_branching_and_resumes_when_completed(
    tmp_path: Path,
) -> None:
    module_path = _copy_fixture(tmp_path, COMMAND_FIXTURE)

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "probe_ready": _bool_bundle_command(tmp_path, "probe_ready", "true"),
            "record_ready": _bool_bundle_command(tmp_path, "record_ready", "true"),
            "record_blocked": _bool_bundle_command(tmp_path, "record_blocked", "true"),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        validated
        for name, validated in result.validated_bundles_by_name.items()
        if name.endswith("::gate") or name == "gate"
    )
    run_id = "native-command-branch"
    state_manager = _bind_and_execute(bundle, tmp_path, run_id, module_path, {})

    first_run = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert first_run["status"] == "completed"
    assert first_run["workflow_outputs"] == {"__result__": True}
    probe_step = first_run["steps"]["native_bool_command_branch::gate__ready__probe_ready"]
    assert probe_step["artifacts"] == {"__result__": True}
    assert probe_step["output"] == "stdout must stay a sidecar\n"
    branch_step = next(
        step for name, step in first_run["steps"].items() if name.endswith("record_ready")
    )
    assert branch_step["artifacts"] == {"__result__": True}
    for step in first_run["steps"].values():
        assert "json" not in step
        assert "lines" not in step

    # Persisting state and resuming: an idempotent resume of an already
    # completed run reconfirms the persisted terminal state without
    # re-executing any step or altering the recorded result.
    resume_manager = StateManager(workspace=tmp_path, run_id=run_id)
    resume_manager.load()
    resumed = WorkflowExecutor(bundle, tmp_path, resume_manager, retry_delay_ms=0).execute(
        resume=True
    )

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": True}


def test_command_root_bool_result_false_branch_records_blocked(tmp_path: Path) -> None:
    module_path = _copy_fixture(tmp_path, COMMAND_FIXTURE)

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "probe_ready": _bool_bundle_command(tmp_path, "probe_ready", "false"),
            "record_ready": _bool_bundle_command(tmp_path, "record_ready", "true"),
            "record_blocked": _bool_bundle_command(tmp_path, "record_blocked", "true"),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        validated
        for name, validated in result.validated_bundles_by_name.items()
        if name.endswith("::gate") or name == "gate"
    )
    state_manager = _bind_and_execute(
        bundle, tmp_path, "native-command-branch-false", module_path, {}
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"__result__": True}
    probe_step = state["steps"]["native_bool_command_branch::gate__ready__probe_ready"]
    assert probe_step["artifacts"] == {"__result__": False}
    branch_step = next(
        step for name, step in state["steps"].items() if name.endswith("record_blocked")
    )
    assert branch_step["artifacts"] == {"__result__": True}


def test_native_root_relpath_workflow_return_executes_without_wrapper(tmp_path: Path) -> None:
    """N3: a root-relpath return (the whole bundle document is a path string)."""
    module_path = tmp_path / "native_relpath_return.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule native_relpath_return)",
                "  (export locate)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defworkflow locate",
                "    ((report_path WorkReport))",
                "    -> WorkReport",
                "    (command-result locate_report",
                '      :argv ("python" "scripts/locate_report.py")',
                "      :returns WorkReport)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    work = tmp_path / "artifacts" / "work"
    work.mkdir(parents=True)
    (work / "report.md").write_text("report\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "locate_report.py").write_text(
        "import os, pathlib\n"
        'bundle = pathlib.Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        'bundle.write_text("\\"artifacts/work/report.md\\"\\n", encoding="utf-8")\n'
        'print("stdout must stay a sidecar")\n',
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "locate_report": ExternalToolBinding(
                name="locate_report",
                stable_command=("python", "scripts/locate_report.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        validated
        for name, validated in result.validated_bundles_by_name.items()
        if name.endswith("::locate") or name == "locate"
    )
    state_manager = _bind_and_execute(
        bundle, tmp_path, "native-relpath-return", module_path, {"report_path": "artifacts/work/report.md"}
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"__result__": "artifacts/work/report.md"}
    step = state["steps"]["native_relpath_return::locate__locate_report"]
    assert step["artifacts"] == {"__result__": "artifacts/work/report.md"}
    assert step["output"] == "stdout must stay a sidecar\n"
