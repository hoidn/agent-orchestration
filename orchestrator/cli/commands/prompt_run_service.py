"""Shared private-snapshot materialization and ordinary prompt run service."""

from __future__ import annotations

import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

from orchestrator import prompt_scaffold
from orchestrator.cli.commands.prompt_io import (
    PromptRunError,
    _create_prompt_inputs_root,
)
from orchestrator.cli.commands.run import run_workflow
from orchestrator.observability.summary import DEFAULT_SUMMARY_TIMEOUT_SEC
from orchestrator.prompt_contract import SemanticContract, contracts_structurally_equal
from orchestrator.prompt_scaffold import (
    ScaffoldCompileError,
    ScaffoldSnapshotError,
    ScaffoldVerification,
    ScaffoldVerificationError,
)
from orchestrator.prompt_session import (
    PromptSessionError,
    publish_prompt_run_link,
    with_private_execution_authority,
)
from orchestrator.state import StateManager
from orchestrator.run_lock import reserved_run_writer_lock

_RUN_NS = {
    "context": None, "context_file": None, "input": None, "input_file": None,
    "clean_processed": False, "archive_processed": None, "dry_run": False,
    "debug": False, "quiet": True, "verbose": False, "log_level": "error",
    "backup_state": False, "on_error": "stop", "max_retries": 0,
    "retry_delay": 1000, "stream_output": False, "step_summaries": False,
    "summary_mode": None, "summary_provider": "claude_sonnet_summary",
    "summary_timeout_sec": DEFAULT_SUMMARY_TIMEOUT_SEC, "summary_max_input_chars": 12000,
    "summary_profile": None, "live_agent_notes": False,
    "live_agent_note_provider": None, "live_agent_note_interval_sec": 15.0,
    "live_agent_note_timeout_sec": 30, "live_agent_note_max_tail_chars": 6000,
    "entry_workflow": None, "source_root": None,
    "provider_externs_file": None, "prompt_externs_file": None,
    "imported_workflow_bundles_file": None, "command_boundaries_file": None,
    "emit_debug_yaml": False, "run_ref_root": None,
}


def run_namespace(**overrides: object) -> Namespace:
    """Build the quiet internal namespace consumed by ordinary run_workflow."""
    base = dict(_RUN_NS)
    base.update(overrides)
    return Namespace(**base)


def materialize_and_run(
    *,
    workspace: Path,
    runs_root: Path,
    run_id: str,
    run_root: Path,
    identity: tuple[int, int],
    captured: Any,
    contract: SemanticContract,
    verification: ScaffoldVerification,
    print_scaffold: bool,
    scaffold_path: Path | None = None,
    scaffold_workspace: Path | None = None,
) -> int:
    """Materialize, compile, execute, and publish through one stable boundary."""
    snapshot = None
    profile_conf_fd = None
    try:
        verification = with_private_execution_authority(verification)
        with reserved_run_writer_lock(run_root, identity) as run_root_fd:
            prompt_inputs, prompt_inputs_fd = _create_prompt_inputs_root(
                run_root, identity, run_root_fd=run_root_fd
            )
            try:
                snapshot = prompt_scaffold.materialize_run_snapshot(
                    verification,
                    run_root=prompt_inputs,
                    run_root_fd=prompt_inputs_fd,
                )
            finally:
                os.close(prompt_inputs_fd)
            _compiled, compiled_contract = prompt_scaffold.compile_snapshot(
                snapshot, provider=captured.provider
            )
            if not contracts_structurally_equal(compiled_contract, contract):
                raise PromptRunError(
                    "compiled contract disagrees with the admitted contract")
            authority = Path(f"/proc/self/fd/{snapshot.root_fd}")
            if captured.provider in {"omp_no_tools", "omp_conf"}:
                conf_name = (
                    ".omp-conf" if captured.provider == "omp_no_tools" else "conf"
                )
                try:
                    profile_conf_fd = os.open(
                        conf_name,
                        os.O_RDONLY | os.O_DIRECTORY
                        | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=snapshot.root_fd,
                    )
                except OSError as exc:
                    raise PromptRunError(
                        f"cannot retain private conf authority: {exc}") from exc
            input_values = (
                [f"omp_conf_root={snapshot.conf_root}"]
                if captured.provider == "omp_conf" else []
            )
            ns = run_namespace(
                workflow=str(authority / "run.orc"), input=input_values,
                state_dir=str(runs_root), source_root=[str(authority)],
                provider_externs_file=str(authority / "providers.json"),
                prompt_externs_file=str(authority / "prompts.json"),
            )
            no_tools_root = None
            no_tools_identity = None
            no_tools_digest = None
            if captured.provider == "omp_no_tools":
                from orchestrator.prompt_session_scaffold import capture_no_tools_conf_authority
                no_tools_identity, no_tools_digest = capture_no_tools_conf_authority(
                    snapshot.root_fd
                )
                no_tools_root = str(snapshot.root / ".omp-conf")
            result = run_workflow(
                ns,
                run_id=run_id,
                expected_run_identity=identity,
                reserved_run_fd=run_root_fd,
                logical_workflow_path=snapshot.run_orc,
                no_tools_conf_root=no_tools_root,
                no_tools_conf_identity=no_tools_identity,
                no_tools_conf_manifest_sha256=no_tools_digest,
                profile_conf_fd=profile_conf_fd,
            )
            if result.run_id != run_id or result.run_root != run_root:
                raise PromptRunError("task run identity mismatch")
            if result.exit_code == 0:
                if scaffold_path is None:
                    raise PromptRunError("successful prompt run has no scaffold path")
                publish_prompt_run_link(
                    StateManager(workspace, run_id=run_id, state_dir=runs_root),
                    workflow_workspace=scaffold_workspace or workspace,
                    scaffold_path=scaffold_path,
                    private_snapshot_fd=snapshot.root_fd,
                    verification=verification,
                    expected_run_identity=identity,
                )
            if print_scaffold and scaffold_path is not None:
                print(f"scaffold: {scaffold_path}", file=sys.stderr)
            return result.exit_code
    except (ScaffoldCompileError, ScaffoldSnapshotError, ScaffoldVerificationError) as exc:
        raise PromptRunError(str(exc)) from exc
    except PromptSessionError:
        raise
    finally:
        if profile_conf_fd is not None:
            os.close(profile_conf_fd)
        if snapshot is not None:
            snapshot.close()


__all__ = ["materialize_and_run", "run_namespace"]
