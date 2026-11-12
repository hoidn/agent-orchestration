"""Run command implementation with safety checks."""

import json
import logging
import os
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


def run_workflow(
    args: Namespace,
    *,
    run_id: Optional[str] = None,
    expected_run_identity: Optional[tuple[int, int]] = None,
    reserved_run_fd: Optional[int] = None,
    logical_workflow_path: Optional[Path] = None,
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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s' if args.debug else '%(message)s'
    )

    try:
        # Determine workspace
        workspace = Path.cwd()
        state_root_error = _state_root_symlink_error(workspace)
        if state_root_error is not None:
            logger.error(state_root_error)
            return RunWorkflowResult(exit_code=1)
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
            entry_target_dsl_version(
                workflow_path, source_read_trace=source_read_trace
            )
        except (LispFrontendCompileError, OSError, UnicodeError):
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
