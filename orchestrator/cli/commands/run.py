"""Run command implementation with safety checks."""

import copy
import json
import logging
import os
import shutil
import traceback
import zipfile
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Dict, Any, Mapping, Optional
from argparse import Namespace

from orchestrator._common.safe_tree import resolve_path_preserving_fd
from orchestrator.state import StateManager
from orchestrator.run_lock import (
    ReservedRunRootError,
    RunAlreadyActiveError,
    reserved_run_writer_lock,
    run_root_matches_fd,
    run_writer_lock,
)
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    LoadedWorkflowBundle,
    workflow_bundle as loaded_workflow_bundle,
    workflow_context,
    workflow_public_input_contracts,
)
from orchestrator.workflow.linting import lint_workflow
from orchestrator.workflow.calls import replay_profile_bundles
from orchestrator.workflow.frontend_origins import workflow_node_origin
from orchestrator.workflow.pure_result_replay import (
    DERIVED_PURE_REPLAY_PROFILE,
    PureReplayRuntime,
    PureResultReplayIndexError,
)
from orchestrator.workflow.resume_projection_integrity import ResumeScopePath
from orchestrator.monitor.process import process_start_time_token, write_process_metadata
from orchestrator.observability.summary import DEFAULT_SUMMARY_TIMEOUT_SEC
from orchestrator.runtime_observability import close_executor_session, open_executor_session
from orchestrator.runtime_observability import record_compiled_frontend_provenance
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    render_diagnostic,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.wcc.route import workflow_lisp_context_with_lowering_schema
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


_ZERO_USAGE = {
    "input": 0,
    "output": 0,
    "cacheRead": 0,
    "cacheWrite": 0,
    "totalTokens": 0,
    "cost": {
        "input": 0.0,
        "output": 0.0,
        "cacheRead": 0.0,
        "cacheWrite": 0.0,
        "total": 0.0,
    },
}


def _provider_usage_record(provider_session: object) -> dict[str, object]:
    """One normalized per-provider usage record from the step debug projection."""
    if not isinstance(provider_session, dict):
        return {}
    record: dict[str, object] = {}
    for key in ("session_id", "final_provider", "final_model",
                "total_tokens", "total_cost"):
        if key in provider_session:
            record[key] = provider_session[key]
    messages = provider_session.get("messages")
    usage = None
    if isinstance(messages, list):
        for row in reversed(messages):
            if isinstance(row, dict) and isinstance(row.get("usage"), dict):
                usage = row["usage"]
                break
    if not isinstance(usage, dict):
        record["usage"] = copy.deepcopy(_ZERO_USAGE)
        return record
    cost = usage.get("cost")
    if not isinstance(cost, dict):
        cost = {}
    record["usage"] = {
        "input": usage.get("input", 0),
        "output": usage.get("output", 0),
        "cacheRead": usage.get("cacheRead", 0),
        "cacheWrite": usage.get("cacheWrite", 0),
        "totalTokens": usage.get("totalTokens", 0),
        "cost": {
            "input": cost.get("input", 0.0),
            "output": cost.get("output", 0.0),
            "cacheRead": cost.get("cacheRead", 0.0),
            "cacheWrite": cost.get("cacheWrite", 0.0),
            "total": cost.get("total", 0.0),
        },
    }
    return record


def _normalize_usage(result: object) -> dict[str, dict[str, object]]:
    """Best-effort usage normalization over finalized provider steps."""
    if not isinstance(result, dict):
        return {}
    steps = result.get("steps")
    if not isinstance(steps, dict):
        return {}
    usage: dict[str, dict[str, object]] = {}
    for step_name, step in steps.items():
        if not isinstance(step, dict):
            continue
        debug = step.get("debug")
        if not isinstance(debug, dict):
            continue
        record = _provider_usage_record(debug.get("provider_session"))
        if record.get("session_id"):
            usage[step_name] = record
    return usage


def _run_result(
    exit_code: int,
    *,
    state_manager: StateManager | None = None,
    session_id: str | None = None,
    session_status: str | None = None,
    result: object = None,
) -> RunWorkflowResult:
    """Build one structured result; workflow outputs/usage are best-effort."""
    run_id: str | None = None
    run_root: Path | None = None
    if state_manager is not None:
        run_id = state_manager.run_id
        run_root = state_manager.run_root
    workflow_outputs: Mapping[str, object] = {}
    if isinstance(result, dict):
        outputs = result.get("workflow_outputs")
        if isinstance(outputs, dict):
            workflow_outputs = outputs
    return RunWorkflowResult(
        exit_code=exit_code,
        run_id=run_id,
        run_root=run_root,
        workflow_outputs=workflow_outputs,
        session_id=session_id,
        session_status=session_status,
        usage=_normalize_usage(result),
    )


def _workflow_path_for_state(workspace: Path, workflow_path: Path) -> str:
    """Persist a workflow path relative to the workspace when possible."""

    try:
        return str(workflow_path.relative_to(workspace))
    except ValueError:
        return str(workflow_path)


def _cli_exception_error(exc: BaseException) -> dict[str, object]:
    return {
        "type": "cli_unhandled_exception",
        "message": str(exc),
        "exception_type": type(exc).__name__,
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
    }


def render_replay_index_rejection(
    exc: PureResultReplayIndexError, bundle: LoadedWorkflowBundle
) -> str:
    """Render a replay-index rejection as a frontend diagnostic at its authored form.

    The rejection names its workflow and node (and, from ``--dry-run``, the call
    sites that reach that workflow); ``bundle`` is the run's root, whose source
    map covers every workflow of the build. The location only improves the
    rejection: when it cannot be found, the diagnostic sits at the workflow file
    without a line, and a note says why.
    """
    context = dict(exc.context)
    path = context.pop("workflow_path", None) or bundle.provenance.workflow_path
    call_sites = context.pop("call_sites", ())
    source_map = bundle.provenance.frontend_source_trace_path
    try:
        if "workflow" not in context or "node_id" not in context:
            raise LookupError("the rejection names no workflow node")
        origin = workflow_node_origin(source_map, context["workflow"], context["node_id"])
        path, line, column = origin["path"], origin["line"], origin["column"]
        notes = list(origin.get("notes", ()))
    except Exception as lookup_error:  # The lookup must never replace the rejection.
        origin, line, column = {}, 1, 1
        notes = [f"source location could not be determined: {_lookup_failure(lookup_error, source_map)}"]
    for caller, node_id in call_sites:
        try:
            site = workflow_node_origin(source_map, caller, node_id)
            notes.append(f"workflow call site at {site['path']}:{site['line']}:{site['column']}")
        except Exception as lookup_error:  # As above: a note, never a replacement.
            notes.append(f"workflow call site in {caller} could not be located: {_lookup_failure(lookup_error, source_map)}")
    position = SourcePosition(path=str(path), line=line, column=column, offset=0)
    text = render_diagnostic(
        LispFrontendDiagnostic(
            code=exc.code,
            message=str(exc),
            span=SourceSpan(start=position, end=position),
            form_path=tuple(origin.get("form_path", ())),
            notes=(
                *notes,
                f"reason: {exc.reason}",
                *(f"{key}: {value}" for key, value in context.items()),
            ),
        )
    )
    # Without an origin the file is known and the line is not: drop the placeholder.
    return text if origin else text.replace(f"{path}:1:1: ", f"{path}: ", 1)


def _lookup_failure(error: Exception, source_map: Path | None) -> str:
    if type(error) is LookupError:  # Raised with its own explanation.
        return str(error)
    return f"reading {source_map} raised {type(error).__name__}: {error}"


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

    state_manager: StateManager | None = None
    writer_lock_stack = ExitStack()
    session_id: str | None = None
    session_status: str | None = None
    reserved_fd: int | None = None

    try:
        # Determine workspace
        workspace = Path.cwd()
        state_dir_override = Path(args.state_dir).expanduser().resolve() if args.state_dir else None
        run_ref_root = resolve_run_ref_root(getattr(args, "run_ref_root", None))

        workflow_path = resolve_path_preserving_fd(args.workflow)
        if workflow_path.suffix.lower() != ".orc":
            logger.error(
                ".orc required: authored workflows must use the Workflow Lisp frontend"
            )
            return _run_result(1)
        if not workflow_path.exists():
            logger.error(f"Workflow file not found: {workflow_path}")
            return _run_result(1)

        frontend_build = None
        try:
            frontend_build = build_frontend_bundle(
                FrontendBuildRequest(
                    source_path=workflow_path,
                    source_roots=tuple(
                        resolve_path_preserving_fd(path)
                        for path in (getattr(args, "source_root", None) or ())
                    ),
                    entry_workflow=getattr(args, "entry_workflow", None),
                    provider_externs_path=resolve_path_preserving_fd(
                        args.provider_externs_file)
                    if getattr(args, "provider_externs_file", None) else None,
                    prompt_externs_path=resolve_path_preserving_fd(
                        args.prompt_externs_file)
                    if getattr(args, "prompt_externs_file", None) else None,
                    imported_workflow_bundles_path=resolve_path_preserving_fd(
                        args.imported_workflow_bundles_file)
                    if getattr(args, "imported_workflow_bundles_file", None) else None,
                    command_boundaries_path=resolve_path_preserving_fd(
                        args.command_boundaries_file)
                    if getattr(args, "command_boundaries_file", None) else None,
                    emit_debug_yaml=bool(getattr(args, "emit_debug_yaml", False)),
                    workspace_root=workspace,
                )
            )
        except LispFrontendCompileError as e:
            for diagnostic in e.diagnostics:
                logger.error(render_diagnostic(diagnostic))
            return _run_result(2)
        workflow = frontend_build.validated_bundle
        bundle = loaded_workflow_bundle(workflow)
        # Determine processed directory
        if bundle is not None:
            processed_root = bundle.surface.processed_dir or 'processed'
        elif isinstance(workflow, dict):
            processed_root = workflow.get('processed_dir', 'processed')
        else:
            processed_root = 'processed'
        processed_dir = workspace / str(processed_root)

        # Handle --clean-processed flag
        if args.clean_processed:
            validate_clean_processed(workflow_path, processed_dir)
            if not args.dry_run:
                clean_processed_directory(processed_dir)
            else:
                logger.info(f"[DRY RUN] Would clean processed directory: {processed_dir}")

        # Validate archive destination if specified
        archive_dest = None
        if args.archive_processed:
            if args.archive_processed.strip():
                archive_dest = Path(args.archive_processed).resolve()
            else:
                # Default to RUN_ROOT/processed.zip; never rebind the service
                # run id when a caller-selected id is in flight.
                archive_run_id = run_id or datetime.now().strftime("%Y%m%dT%H%M%SZ")
                runs_root = state_dir_override or (workspace / '.orchestrate' / 'runs')
                run_root = runs_root / archive_run_id
                archive_dest = run_root / 'processed.zip'

            validate_archive_destination(processed_dir, archive_dest)

            if args.dry_run:
                logger.info(f"[DRY RUN] Would archive processed directory to: {archive_dest}")

        raw_inputs = parse_inputs(args)
        lint_warnings = lint_workflow(workflow)

        bound_inputs = bind_workflow_inputs(
            workflow_public_input_contracts(workflow),
            raw_inputs,
            workspace=workspace,
        )

        if args.dry_run:
            for warning in lint_warnings:
                logger.warning(
                    "[LINT] %s (%s at %s)",
                    warning.get("message"),
                    warning.get("code"),
                    warning.get("path"),
                )
            # A run builds this runtime at its start and in each call frame it
            # opens, before any effect there
            # (WorkflowExecutor._configure_pure_replay_runtime). Building each
            # here reports the same rejections; it reads only the bundles.
            scope_path = ResumeScopePath.root(
                _workflow_path_for_state(
                    workspace, logical_workflow_path or workflow_path
                )
            )
            for frame_bundle, call_path in replay_profile_bundles(bundle):
                try:
                    # The scope path is only type-checked here; derivation
                    # reads the bundle alone.
                    PureReplayRuntime(bundle=frame_bundle, scope_path=scope_path)
                except PureResultReplayIndexError as exc:
                    raise PureResultReplayIndexError(
                        exc.reason,
                        str(exc),
                        context={
                            **exc.context,
                            "call_sites": [
                                (caller.surface.name, boundary.node_id)
                                for caller, boundary in reversed(call_path)
                            ],
                        },
                    ) from exc
            return _run_result(0)

        # Parse context
        context = parse_context(args, workflow_context=dict(workflow_context(workflow)))
        if frontend_build is not None:
            context = workflow_lisp_context_with_lowering_schema(
                context,
                frontend_build.manifest.lowering_schema_version,
            )

        observability = build_observability_config(args)

        # Initialize state manager
        # AT-69: --debug implies backup_enabled
        state_manager = StateManager(
            workspace=workspace,
            backup_enabled=args.backup_state,
            debug=args.debug if hasattr(args, 'debug') else False,
            state_dir=state_dir_override,
            run_id=run_id,
        )
        if run_id is not None and expected_run_identity is not None:
            # R7: prompt callers acquire this lock before their first write
            # and pass the retained authority through the whole lifecycle.
            if reserved_run_fd is None:
                reserved_fd = writer_lock_stack.enter_context(
                    reserved_run_writer_lock(
                        state_manager.run_root, expected_run_identity
                    )
                )
            else:
                reserved_fd = reserved_run_fd
            if not run_root_matches_fd(
                state_manager.run_root, reserved_fd
            ):
                logger.error(
                    f"Reserved run root {state_manager.run_root} was swapped "
                    "after the writer lock"
                )
                return _run_result(
                    1,
                    state_manager=state_manager,
                    session_id=session_id,
                    session_status=session_status,
                )
        else:
            state_manager.run_root.mkdir(parents=True, exist_ok=True)
            writer_lock_stack.enter_context(
                run_writer_lock(state_manager.run_root)
            )

        run_state = state_manager.initialize(
            _workflow_path_for_state(
                workspace, logical_workflow_path or workflow_path
            ),
            context,
            bound_inputs=bound_inputs,
            observability=observability,
            result_persistence_profile=DERIVED_PURE_REPLAY_PROFILE,
            run_root_fd=reserved_fd,
        )
        if reserved_fd is not None and not run_root_matches_fd(
            state_manager.run_root, reserved_fd
        ):
            logger.error(
                f"Reserved run root {state_manager.run_root} was swapped "
                "during initialization"
            )
            return _run_result(1, state_manager=state_manager)
        if getattr(args, "run_ref_root", None) is not None:
            state_manager.bind_run_ref_root(run_ref_root)
        if frontend_build is not None:
            with state_manager.state_transaction() as transaction_state:
                record_compiled_frontend_provenance(
                    transaction_state,
                    frontend_build.validated_bundle.provenance,
                )
            run_state = state_manager.state
            assert run_state is not None
        logger.info(f"Created new run: {run_state.run_id}")

        try:
            with state_manager.state_transaction() as transaction_state:
                session_id = open_executor_session(
                    transaction_state,
                    entrypoint="run",
                    process_start_time=process_start_time_token(os.getpid()),
                )
            session_status = "failed"
            try:
                write_process_metadata(
                    state_manager.io_run_root,
                    executor_session_id=session_id,
                )
            except OSError as exc:
                logger.debug("Failed to write monitor process metadata: %s", exc)

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=workspace,
                state_manager=state_manager,
                logs_dir=state_manager.logs_dir,
                debug=args.debug if hasattr(args, 'debug') else False,
                stream_output=args.stream_output if hasattr(args, 'stream_output') else False,
                max_retries=args.max_retries,
                retry_delay_ms=args.retry_delay,
                observability=observability,
                no_tools_conf_root=no_tools_conf_root,
                no_tools_conf_identity=no_tools_conf_identity,
                no_tools_conf_manifest_sha256=no_tools_conf_manifest_sha256,
                profile_conf_fd=profile_conf_fd,
            )

            result = executor.execute(
                run_id=run_state.run_id,
                on_error=args.on_error,
                max_retries=args.max_retries,
                retry_delay_ms=args.retry_delay
            )

            run_completed = False
            if isinstance(result, dict):
                run_completed = result.get("status") == "completed"
                run_succeeded = run_completed or result.get("status") == "suspended"
            else:
                run_completed = bool(result)
                run_succeeded = run_completed
            session_status = "completed" if run_succeeded else "failed"

            # Archive processed directory on successful completion only; an
            # archive failure marks the session failed, never stale completed.
            if run_completed and archive_dest:
                try:
                    archive_processed_directory(processed_dir, archive_dest)
                except Exception:
                    session_status = "failed"
                    raise

            return _run_result(
                0 if run_succeeded else 1,
                state_manager=state_manager,
                session_id=session_id,
                session_status=session_status,
                result=result,
            )
        finally:
            if session_id is not None and state_manager.state is not None:
                try:
                    with state_manager.state_transaction() as transaction_state:
                        close_executor_session(
                            transaction_state,
                            session_id=session_id,
                            status=session_status or "failed",
                        )
                except Exception as exc:
                    # Never return from the finally block: a close failure
                    # must reach the outer handler so fail_run persists a
                    # failed run state and the exact failed result returns
                    # (a return here would suppress an active body exception
                    # and leave the persisted run completed).
                    logger.error(f"Failed to close executor session: {exc}")
                    session_status = "failed"
                    raise

    except RunAlreadyActiveError as e:
        logger.error(str(e))
        return _run_result(
            1, state_manager=state_manager, session_id=session_id,
            session_status="failed" if session_id is not None else None)
    except ReservedRunRootError as e:
        logger.error(str(e))
        return _run_result(
            1, state_manager=state_manager, session_id=session_id,
            session_status="failed" if session_id is not None else None)
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return _run_result(
            1, state_manager=state_manager, session_id=session_id,
            session_status="failed" if session_id is not None else None)
    except PureResultReplayIndexError as e:
        # Raised by the replay-index build in --dry-run and at run start alike.
        logger.error(render_replay_index_rejection(e, bundle))
        return _run_result(
            2, state_manager=state_manager, session_id=session_id,
            session_status="failed" if session_id is not None else None)
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return _run_result(
            2, state_manager=state_manager, session_id=session_id,
            session_status="failed" if session_id is not None else None)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        if state_manager is not None and state_manager.state is not None:
            state_manager.fail_run(_cli_exception_error(e))
        return _run_result(
            1, state_manager=state_manager, session_id=session_id,
            session_status="failed" if session_id is not None else None)
    finally:
        if state_manager is not None:
            state_manager.close()
        writer_lock_stack.close()
