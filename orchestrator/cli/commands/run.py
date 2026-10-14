"""Run command implementation with safety checks."""

import json
import logging
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Dict, Any, Mapping, Optional
from argparse import Namespace

from orchestrator._common.safe_tree import resolve_path_preserving_fd
from orchestrator.run_lock import (
    ReservedRunRootError,
    RunAlreadyActiveError,
    WorkspaceAlreadyActiveError,
)
from orchestrator.observability.summary import DEFAULT_SUMMARY_TIMEOUT_SEC
from orchestrator.workflow_lisp.closed.target import (
    entry_target_dsl_version,
    refuse_retired_entry_target,
)
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    render_diagnostic,
)
from orchestrator.cli.run_ref_root import resolve_run_ref_root


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RunWorkflowResult:
    """Structured run outcome: exit code plus exact run/root/output/session data."""

    exit_code: int
    run_id: str | None = None
    run_root: Path | None = None
    workflow_outputs: Mapping[str, object] = field(default_factory=dict)
    session_id: str | None = None
    session_status: str | None = None
    usage: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Detach and deep-freeze both mapping fields on EVERY construction
        path (defaults included), so a public ``RunWorkflowResult`` can never
        alias a caller's or the executor's mutable state."""
        object.__setattr__(
            self, "workflow_outputs", _deep_freeze(self.workflow_outputs)
        )
        object.__setattr__(self, "usage", _deep_freeze(self.usage))


def _deep_freeze(value: object) -> object:
    """Recursively detach and freeze one result payload into immutable views.

    Mappings become read-only mapping proxies, lists become tuples, so a
    finalized ``RunWorkflowResult`` can never alias executor-owned mutable
    state: top-level and nested mutation both fail, and mutating the source
    after construction cannot change the result. Any ``Mapping`` is
    accepted, not only ``dict``.
    """
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _workflow_path_for_state(workspace: Path, workflow_path: Path) -> str:
    """Persist a workflow path relative to the workspace when possible."""

    try:
        return str(workflow_path.relative_to(workspace))
    except ValueError:
        return str(workflow_path)


def _state_root_symlink_error(workspace: Path) -> str | None:
    """The run-start refusal of a workspace whose `.orchestrate` is a symbolic link.

    Build artifacts, run state and result files are created beneath it, and a
    result path may not pass through a symbolic link (specs/io.md,
    "Result-file freshness"), wherever the link points.
    """
    state_root = workspace / ".orchestrate"
    if not state_root.is_symlink():
        return None
    return (
        f"state_root_symlink: {state_root} is a symbolic link to "
        f"{os.readlink(state_root)}; run state and result files may not pass "
        "through a symbolic link. Replace the link with a real directory, for "
        "example by moving the directory it points to into its place."
    )



def build_observability_config(args: Namespace) -> Optional[Dict[str, Any]]:
    """Build runtime observability config from CLI flags.

    Observability is runtime-only (not DSL). Summaries default to async when enabled.
    """
    step_summaries_enabled = bool(getattr(args, 'step_summaries', False))
    summary_mode = getattr(args, 'summary_mode', None)
    summary_profile = getattr(args, 'summary_profile', None)
    live_agent_notes_enabled = bool(getattr(args, 'live_agent_notes', False))

    if (summary_mode or summary_profile or live_agent_notes_enabled) and not step_summaries_enabled:
        # Explicit mode should implicitly enable summaries.
        step_summaries_enabled = True

    if not step_summaries_enabled:
        return None

    summary_timeout_sec = int(getattr(args, 'summary_timeout_sec', DEFAULT_SUMMARY_TIMEOUT_SEC))
    summary_max_input_chars = int(getattr(args, 'summary_max_input_chars', 12000))
    if summary_timeout_sec <= 0:
        raise ValueError("--summary-timeout-sec must be > 0")
    if summary_max_input_chars <= 0:
        raise ValueError("--summary-max-input-chars must be > 0")

    step_summaries = {
        "enabled": True,
        "mode": summary_mode or "async",
        "provider": getattr(args, 'summary_provider', 'claude_sonnet_summary'),
        "timeout_sec": summary_timeout_sec,
        "max_input_chars": summary_max_input_chars,
        "best_effort": True,
        "profile": summary_profile or "basic",
    }

    if live_agent_notes_enabled:
        interval_sec = float(getattr(args, 'live_agent_note_interval_sec', 15.0))
        live_timeout_sec = int(getattr(args, 'live_agent_note_timeout_sec', 30))
        max_tail_chars = int(getattr(args, 'live_agent_note_max_tail_chars', 6000))
        if interval_sec <= 0:
            raise ValueError("--live-agent-note-interval-sec must be > 0")
        if live_timeout_sec <= 0:
            raise ValueError("--live-agent-note-timeout-sec must be > 0")
        if max_tail_chars <= 0:
            raise ValueError("--live-agent-note-max-tail-chars must be > 0")
        step_summaries["live_agent_notes"] = {
            "enabled": True,
            "provider": getattr(args, 'live_agent_note_provider', None)
            or "claude_haiku_summary",
            "interval_sec": interval_sec,
            "timeout_sec": live_timeout_sec,
            "max_tail_chars": max_tail_chars,
            "source": "tmux",
        }

    return {
        "step_summaries": {
            **step_summaries,
        }
    }


def parse_context(args: Namespace, workflow_context: Dict[str, Any] | None = None) -> Dict[str, str]:
    """Parse context variables from workflow defaults and command line arguments.

    Precedence:
    1. workflow_context defaults
    2. --context key=value arguments
    3. --context-file JSON values
    """
    context: Dict[str, str] = {}

    # Start with workflow-level defaults so ${context.*} works without CLI overrides.
    if workflow_context:
        for key, value in workflow_context.items():
            context[str(key)] = str(value)

    # Parse context from key=value pairs
    if args.context:
        for item in args.context:
            if '=' not in item:
                raise ValueError(f"Invalid context format: {item}. Expected KEY=VALUE")
            key, value = item.split('=', 1)
            context[key] = value

    # Parse context from JSON file
    if args.context_file:
        context_file = Path(args.context_file)
        if not context_file.exists():
            raise FileNotFoundError(f"Context file not found: {context_file}")

        with open(context_file, 'r') as f:
            file_context = json.load(f)
            if not isinstance(file_context, dict):
                raise ValueError(f"Context file must contain a JSON object, got {type(file_context).__name__}")

            # Convert all values to strings
            for key, value in file_context.items():
                context[str(key)] = str(value)

    return context


def parse_inputs(args: Namespace) -> Dict[str, Any]:
    """Parse workflow-boundary inputs from CLI flags."""
    inputs: Dict[str, Any] = {}

    input_file = getattr(args, 'input_file', None)
    if isinstance(input_file, str) and input_file:
        input_file_path = Path(input_file)
        if not input_file_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_file_path}")

        with open(input_file_path, 'r') as f:
            file_inputs = json.load(f)
            if not isinstance(file_inputs, dict):
                raise ValueError(
                    f"Input file must contain a JSON object, got {type(file_inputs).__name__}"
                )
            for key, value in file_inputs.items():
                inputs[str(key)] = value

    raw_inputs = getattr(args, 'input', None)
    if isinstance(raw_inputs, list):
        for item in raw_inputs:
            if '=' not in item:
                raise ValueError(f"Invalid input format: {item}. Expected NAME=VALUE")
            key, value = item.split('=', 1)
            inputs[key] = value

    return inputs


def validate_clean_processed(workflow_path: Path, processed_dir: Path) -> None:
    """
    Validate that processed_dir is safe to clean.

    AT-16: CLI Safety - fails if processed dir is outside WORKSPACE
    """
    # Determine WORKSPACE (current working directory)
    workspace = Path.cwd().resolve()

    # Resolve processed_dir to absolute path
    processed_abs = processed_dir.resolve()

    # Check if processed_dir is within WORKSPACE
    try:
        processed_abs.relative_to(workspace)
    except ValueError:
        raise ValueError(
            f"Safety check failed: processed directory '{processed_abs}' is outside WORKSPACE '{workspace}'. "
            f"The --clean-processed flag can only operate on directories within the workspace."
        )

    # Additional safety: prevent cleaning root or parent directories
    if processed_abs == workspace:
        raise ValueError(
            "Safety check failed: cannot clean WORKSPACE root directory"
        )

    if workspace.is_relative_to(processed_abs):
        raise ValueError(
            "Safety check failed: cannot clean parent directory of WORKSPACE"
        )


def clean_processed_directory(processed_dir: Path) -> None:
    """
    Clean the processed directory.

    AT-11: Clean processed - empties directory
    """
    if not processed_dir.exists():
        logger.info(f"Processed directory does not exist, nothing to clean: {processed_dir}")
        return

    if not processed_dir.is_dir():
        raise ValueError(f"Processed path is not a directory: {processed_dir}")

    # Remove all contents but keep the directory itself
    logger.info(f"Cleaning processed directory: {processed_dir}")
    for item in processed_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    logger.info("Successfully cleaned processed directory")


def validate_archive_destination(processed_dir: Path, archive_dest: Path) -> None:
    """
    Validate that archive destination is safe.

    Per spec: destination must not be inside the configured processed_dir
    """
    processed_abs = processed_dir.resolve()
    archive_abs = archive_dest.resolve()

    # Check if archive destination is inside processed directory
    try:
        archive_abs.relative_to(processed_abs)
        raise ValueError(
            f"Safety check failed: archive destination '{archive_abs}' cannot be inside "
            f"processed directory '{processed_abs}'"
        )
    except ValueError as e:
        if "does not start with" not in str(e) and "is not in the subpath" not in str(e):
            raise


def archive_processed_directory(processed_dir: Path, archive_dest: Path) -> None:
    """
    Archive the processed directory to a zip file.

    AT-12: Archive processed - creates zip on success
    """
    if not processed_dir.exists():
        logger.warning(f"Processed directory does not exist, creating empty archive: {processed_dir}")
        processed_dir.mkdir(parents=True, exist_ok=True)

    if not processed_dir.is_dir():
        raise ValueError(f"Processed path is not a directory: {processed_dir}")

    # Ensure parent directory exists
    archive_dest.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Archiving processed directory to: {archive_dest}")

    # Create zip archive
    with zipfile.ZipFile(archive_dest, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(processed_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(processed_dir.parent)
                zf.write(file_path, arcname)

    logger.info(f"Successfully archived processed directory to {archive_dest}")


def run_workflow(
    args: Namespace,
    *,
    run_id: Optional[str] = None,
    expected_run_identity: Optional[tuple[int, int]] = None,
    reserved_run_fd: Optional[int] = None,
    logical_workflow_path: Optional[Path] = None,
    no_tools_conf_root: Optional[str] = None,
    no_tools_conf_identity: Optional[tuple[int, int]] = None,
    no_tools_conf_manifest_sha256: Optional[str] = None,
    profile_conf_fd: Optional[int] = None,
) -> RunWorkflowResult:
    """
    Run a workflow with safety checks.

    Implements AT-11, AT-12, AT-16. Prompt callers may supply their already
    locked ``reserved_run_fd`` so one descriptor authority covers prompt
    materialization, execution, and publication.
    """
    # Set up logging
    log_level = getattr(logging, args.log_level.upper())
    if args.debug:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.ERROR
    elif args.verbose:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        # Determine workspace
        workspace = Path.cwd()
        state_root_error = _state_root_symlink_error(workspace)
        if state_root_error is not None:
            logger.error(state_root_error)
            return RunWorkflowResult(exit_code=1)
        state_dir_override = Path(args.state_dir).expanduser().resolve() if args.state_dir else None
        run_ref_root = resolve_run_ref_root(getattr(args, "run_ref_root", None))

        workflow_path = resolve_path_preserving_fd(args.workflow)
        if workflow_path.suffix.lower() != ".orc":
            logger.error(
                ".orc required: authored workflows must use the Workflow Lisp frontend"
            )
            return RunWorkflowResult(exit_code=1)
        if not workflow_path.exists():
            logger.error(f"Workflow file not found: {workflow_path}")
            return RunWorkflowResult(exit_code=1)

        try:
            refuse_retired_entry_target(workflow_path)
        except LispFrontendCompileError as exc:
            for diagnostic in exc.diagnostics:
                logger.error(render_diagnostic(diagnostic))
            return RunWorkflowResult(exit_code=2)

        source_read_trace = SourceReadTrace()
        try:
            selected_target = entry_target_dsl_version(
                workflow_path, source_read_trace=source_read_trace
            )
        except (LispFrontendCompileError, OSError, UnicodeError):
            selected_target = None
            source_read_trace = None
        from orchestrator.cli.commands.evaluated import run_evaluated_workflow

        exit_code, evaluated_run_id, evaluated_run_root, outputs = run_evaluated_workflow(
            args,
            workspace=workspace,
            workflow_path=workflow_path,
            logical_workflow_path=logical_workflow_path,
            run_id=run_id,
            source_read_trace=source_read_trace,
            expected_run_identity=expected_run_identity,
            reserved_run_fd=reserved_run_fd,
        )
        return RunWorkflowResult(
            exit_code=exit_code,
            run_id=evaluated_run_id,
            run_root=evaluated_run_root,
            workflow_outputs=outputs,
        )

    except WorkspaceAlreadyActiveError as e:
        logger.error(str(e))
        return RunWorkflowResult(exit_code=2, run_id=run_id)
    except RunAlreadyActiveError as e:
        logger.error(str(e))
        return RunWorkflowResult(exit_code=2)
    except ReservedRunRootError as e:
        logger.error(str(e))
        return RunWorkflowResult(exit_code=1, run_id=run_id, run_root=e.run_root)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return RunWorkflowResult(exit_code=1)
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return RunWorkflowResult(exit_code=2)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return RunWorkflowResult(exit_code=1)
