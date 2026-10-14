"""Resume evaluated workflows without mutating retired run profiles."""

import logging
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Optional
from orchestrator.state import DERIVED_PURE_REPLAY_PROFILE
from orchestrator.run_lock import RunAlreadyActiveError, WorkspaceAlreadyActiveError, run_writer_lock, workspace_run_lock
from orchestrator.cli.commands.run import _state_root_symlink_error

logger = logging.getLogger(__name__)

def _evaluated_resume_route(run_root: Path, workspace: Path, *, force_restart: bool, run_ref_root: str | None, run_files=None, stream_output: bool = True) -> int | None:
    """Select immutable authority under the writer locks, before legacy state."""
    from orchestrator.workflow.evaluated.authority import PROFILE, SCHEMA_VERSION, RunAuthorityError, _read_header_json
    from orchestrator.cli.commands.evaluated import resume_evaluated_workflow
    header_path = run_root / "run.json"
    try:
        if not _has_authority_header(run_root, run_files):
            return None
        header = _read_header_json(header_path, run_files)
        if not isinstance(header, dict):
            raise RunAuthorityError("run header is not an object")
        profile = header.get("result_persistence_profile")
        schema = header.get("schema_version")
        if profile == PROFILE and schema == SCHEMA_VERSION:
            return resume_evaluated_workflow(run_root, workspace=workspace, force_restart=force_restart, run_ref_root=run_ref_root, run_files=run_files, stream_output=stream_output)
        if schema == "2.1" and profile in (None, DERIVED_PURE_REPLAY_PROFILE):
            return None
        raise RunAuthorityError("unsupported run authority profile or schema")
    except (OSError, UnicodeError, ValueError) as exc:
        logger.error("[%s] %s", getattr(exc, "code", "memo_inconsistent"), exc)
        return 2

def _has_authority_header(run_root, run_files):
    from orchestrator.workflow.evaluated.authority import PROFILE, SCHEMA_VERSION, RunAuthorityError, _read_header_json
    from orchestrator.workflow.evaluated.memo import MemoError
    exists = run_files.exists if run_files is not None else lambda path: Path(path).exists() or Path(path).is_symlink()
    if exists(run_root / "run.json"):
        header = _read_header_json(run_root / "run.json", run_files)
        if not isinstance(header, dict):
            raise RunAuthorityError("run header is not an object")
        if header.get("schema_version") == "2.1" and header.get("result_persistence_profile") in (None, DERIVED_PURE_REPLAY_PROFILE):
            raise MemoError("workflow_execution_profile_retired", "historical workflow execution is retired; use a separately retained complete release/environment qualified for this run")
        if header.get("schema_version") != SCHEMA_VERSION or header.get("result_persistence_profile") != PROFILE:
            raise RunAuthorityError("unsupported run authority profile or schema")
        return True
    if exists(run_root / "memo.jsonl") or exists(run_root / "closed_program.json"):
        raise RunAuthorityError("evaluated run authority header is missing")
    return False

def resume_workflow(
    run_id: str,
    repair: bool = False,
    force_restart: bool = False,
    state_dir: Optional[str] = None,
    on_error: str = 'stop',
    max_retries: Optional[int] = None,
    retry_delay_ms: Optional[int] = None,
    backup_state: bool = False,
    debug: bool = False,
    stream_output: bool = False,
    summary_mode: Optional[str] = None,
    summary_provider: Optional[str] = None,
    summary_timeout_sec: Optional[int] = None,
    summary_max_input_chars: Optional[int] = None,
    summary_profile: Optional[str] = None,
    live_agent_notes: Optional[bool] = None,
    live_agent_note_provider: Optional[str] = None,
    live_agent_note_interval_sec: Optional[float] = None,
    live_agent_note_timeout_sec: Optional[int] = None,
    live_agent_note_max_tail_chars: Optional[int] = None,
    run_ref_root: Optional[str] = None,
    **kwargs
) -> int:
    """Hold the selected run's writer lock for the complete resume command."""

    workspace_dir = Path.cwd()
    if state_dir is None:
        state_root_error = _state_root_symlink_error(workspace_dir)
        if state_root_error is not None:
            logger.error(state_root_error)
            return 1
    state_dir_override = (
        Path(state_dir).expanduser().resolve()
        if state_dir
        else None
    )
    runs_root = state_dir_override or (
        workspace_dir / '.orchestrate' / 'runs'
    )
    run_root = runs_root / run_id
    if not run_root.exists():
        logger.error(f"Run directory not found: {run_root}")
        print(f"Error: No run found with ID '{run_id}'", file=sys.stderr)
        return 1

    try:
        if not _has_authority_header(run_root, None):
            from orchestrator.workflow.evaluated.memo import MemoError
            raise MemoError("workflow_execution_profile_retired", "historical workflow execution is retired; use a separately retained complete release/environment qualified for this run")
        with ExitStack() as writer_locks:
            import uuid
            restart_run_id = uuid.uuid4().hex if force_restart else None
            writer_locks.enter_context(
                workspace_run_lock(workspace_dir, restart_run_id or run_id)
            )
            from orchestrator.workflow.workspace_files import WorkspaceFiles
            run_fd = writer_locks.enter_context(run_writer_lock(run_root))
            run_files = WorkspaceFiles(run_root, root_fd=run_fd)
            writer_locks.callback(run_files.close)
            evaluated_exit = _evaluated_resume_route(run_root, workspace_dir, force_restart=force_restart, run_ref_root=run_ref_root, run_files=run_files, stream_output=not kwargs.get("quiet", False))
            if evaluated_exit is not None:
                return evaluated_exit
            from orchestrator.workflow.evaluated.authority import RunAuthorityError
            raise RunAuthorityError("evaluated run authority header disappeared before resume")
    except (OSError, UnicodeError, ValueError) as exc:
        code = getattr(exc, "code", "memo_inconsistent")
        logger.error("[%s] %s", code, exc)
        print(f"Error: [{code}] {exc}", file=sys.stderr)
        return 2
    except (RunAlreadyActiveError, WorkspaceAlreadyActiveError) as exc:
        logger.error(str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 2
