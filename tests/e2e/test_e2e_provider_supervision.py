"""Real-provider smoke for bounded Workflow Lisp live supervision."""

from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import re
import subprocess

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e


_OBSERVATION_MARKER_PREFIX = "LIVE_WORKER_DRAFT_V1:"
_OBSERVATION_MARKER_PATTERN = re.compile(
    rf"{re.escape(_OBSERVATION_MARKER_PREFIX)}[0-9a-f]{{32}}"
)
_CORRECTED_VALUE = "corrected-value"


def _write_fixture(workspace: Path) -> dict[str, Path]:
    files = {
        "source": workspace / "live_supervision.orc",
        "providers": workspace / "providers.json",
        "prompts": workspace / "prompts.json",
        "worker": workspace / "worker.md",
        "supervisor": workspace / "supervisor.md",
    }
    files["source"].write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.16")',
                "  (defmodule live_supervision)",
                "  (export orchestrate)",
                "  (defworkflow orchestrate () -> String",
                "    (with-live-providers",
                "      ((worker",
                "        (provider-result providers.worker",
                "          :prompt prompts.worker",
                "          :inputs ()",
                "          :timeout-sec 300",
                "          :returns String))",
                "       (supervisor",
                "        (provider-result providers.supervisor",
                "          :prompt prompts.supervisor",
                "          :inputs ()",
                "          :timeout-sec 180",
                "          :returns ProviderSteeringDirective)",
                "        :observes worker))",
                "      worker)))",
                "",
            )
        ),
        encoding="utf-8",
    )
    files["providers"].write_text(
        json.dumps(
            {
                "providers.worker": "codex",
                "providers.supervisor": "codex",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files["prompts"].write_text(
        json.dumps(
            {
                "prompts.worker": "worker.md",
                "prompts.supervisor": "supervisor.md",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files["worker"].write_text(
        (
            "Work only inside this temporary repository. Use the shell to "
            "generate a fresh 32-character lowercase hexadecimal token. "
            "Write the JSON "
            'string "uncorrected-value" to the required output-bundle path. '
            "Then finish with one concise assistant message containing the "
            f"exact prefix {_OBSERVATION_MARKER_PREFIX} immediately followed "
            "by that token. "
            "Do not create or edit any other file.\n"
        ),
        encoding="utf-8",
    )
    files["supervisor"].write_text(
        (
            "Act as the live supervisor. The runtime appends a JSON observation "
            "target containing socket_path and target. Use the shell command "
            "`tmux -S <socket_path> capture-pane -p -J -t <target>` repeatedly "
            f"until the pane contains {_OBSERVATION_MARKER_PREFIX} followed "
            "immediately by exactly 32 lowercase hexadecimal characters. Do "
            "not decide before observing that complete worker-generated "
            "marker, and do not invent or transform its token. Once observed, "
            "write a STEER directive to the required output-bundle path. Its "
            "guidance must copy the complete observed marker exactly and must "
            "direct the resumed worker "
            "to skip all waiting, write the JSON string "
            f'"{_CORRECTED_VALUE}" to its required output-bundle path, and '
            "finish. Never return CONTINUE. Do not create or edit any other "
            "file.\n"
        ),
        encoding="utf-8",
    )
    return files


def _build_request(
    workspace: Path,
    files: dict[str, Path],
) -> FrontendBuildRequest:
    return FrontendBuildRequest(
        source_path=files["source"],
        source_roots=(workspace,),
        entry_workflow="orchestrate",
        provider_externs_path=files["providers"],
        prompt_externs_path=files["prompts"],
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=workspace,
    )


def _run_args(files: dict[str, Path]) -> Namespace:
    return Namespace(
        workflow=str(files["source"]),
        context=None,
        context_file=None,
        input=None,
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
        entry_workflow="orchestrate",
        source_root=[str(files["source"].parent)],
        provider_externs_file=str(files["providers"]),
        prompt_externs_file=str(files["prompts"]),
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=False,
    )


def _realize(run_root: Path, template: str) -> Path:
    return run_root / template.replace("{visit}", "1")


@pytest.mark.e2e
def test_real_supervisor_steers_session_worker_to_distinct_typed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Observe one live target and select its exact resumed result."""

    skip_if_no_e2e()
    for executable in ("codex", "git", "tmux"):
        skip_if_no_cli(executable)

    workspace = tmp_path / "provider-supervision"
    workspace.mkdir()
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )
    files = _write_fixture(workspace)
    built = build_frontend_bundle(_build_request(workspace, files))
    [node] = built.validated_bundle.ir.nodes.values()
    assert node.kind is ExecutableNodeKind.PROVIDER_SUPERVISION
    config = node.execution_config

    monkeypatch.chdir(workspace)
    assert run_workflow(_run_args(files)) == 0

    [run_root] = (workspace / ".orchestrate" / "runs").iterdir()
    state = json.loads(
        (run_root / "state.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "__result__": _CORRECTED_VALUE
    }
    [step] = state["steps"].values()
    assert step["artifacts"] == {"__result__": _CORRECTED_VALUE}
    assert len(state["provider_attempt_allocations"]) == 3

    fresh_bundle = _realize(
        run_root,
        config.paths.worker_fresh.provisional_bundle_relpath,
    )
    resume_bundle = _realize(
        run_root,
        config.paths.worker_resume.provisional_bundle_relpath,
    )
    directive_bundle = _realize(
        run_root,
        config.paths.supervisor_directive.provisional_bundle_relpath,
    )
    assert json.loads(fresh_bundle.read_text(encoding="utf-8")) == (
        "uncorrected-value"
    )
    assert json.loads(resume_bundle.read_text(encoding="utf-8")) == (
        _CORRECTED_VALUE
    )
    directive = json.loads(directive_bundle.read_text(encoding="utf-8"))
    assert directive["variant"] == "STEER"

    transcripts = tuple(sorted(
        (run_root / "provider-observation" / "transcripts").glob(
            "*.transcript"
        )
    ))
    assert len(transcripts) == 3
    worker_markers = set(
        _OBSERVATION_MARKER_PATTERN.findall(
            transcripts[0].read_text(
                encoding="utf-8",
                errors="strict",
            )
        )
    )
    assert len(worker_markers) == 1
    [worker_marker] = worker_markers
    assert worker_marker in directive["guidance"]
