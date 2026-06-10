"""Resume command implementation."""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
import sys

from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_boundary_projection,
    workflow_context,
    workflow_is_managed_write_root_input_name,
    workflow_managed_write_root_inputs,
    workflow_public_input_contracts,
    workflow_runtime_context_inputs,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.monitor.process import (
    process_start_time_token,
    read_process_metadata,
    write_process_metadata,
)
from orchestrator.observability.summary import DEFAULT_SUMMARY_TIMEOUT_SEC
from orchestrator.runtime_observability import close_executor_session, open_executor_session
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic


logger = logging.getLogger(__name__)
PROVIDER_SESSION_QUARANTINE_ERROR = "provider_session_interrupted_visit_quarantined"


def _public_rebind_inputs_for_force_restart(
    workflow_bundle: Any,
    persisted_bound_inputs: Any,
) -> Dict[str, Any]:
    raw_inputs = persisted_bound_inputs if isinstance(persisted_bound_inputs, dict) else {}
    boundary = workflow_boundary_projection(workflow_bundle)
    managed_inputs = {
        name
        for name in boundary.private_managed_write_root_inputs
        if isinstance(name, str)
    }
    runtime_context_inputs = {
        name
        for binding in boundary.private_runtime_context_bindings
        for name in binding.generated_input_names
        if isinstance(name, str)
    }
    compatibility_bridge_inputs = {
        name
        for name in boundary.private_compatibility_bridge_inputs
        if isinstance(name, str)
    }
    return {
        str(name): value
        for name, value in raw_inputs.items()
        if isinstance(name, str)
        and name not in managed_inputs
        and name not in runtime_context_inputs
        and name not in compatibility_bridge_inputs
        and not workflow_is_managed_write_root_input_name(name)
    }


def _merge_observability_overrides(base: Optional[Dict[str, Any]], **overrides: Any) -> Optional[Dict[str, Any]]:
    """Merge resume-time summary overrides onto persisted runtime config."""
    config: Dict[str, Any] = dict(base or {})
    step_cfg: Dict[str, Any] = dict(config.get("step_summaries", {}))

    if not step_cfg and not any(value is not None for value in overrides.values()):
        return None

    if not step_cfg:
        step_cfg = {
            "enabled": True,
            "mode": "async",
            "provider": "claude_sonnet_summary",
            "timeout_sec": DEFAULT_SUMMARY_TIMEOUT_SEC,
            "max_input_chars": 12000,
            "best_effort": True,
        }

    if overrides.get("summary_mode") is not None:
        step_cfg["mode"] = overrides["summary_mode"]
    if overrides.get("summary_provider") is not None:
        step_cfg["provider"] = overrides["summary_provider"]
    if overrides.get("summary_profile") is not None:
        step_cfg["profile"] = overrides["summary_profile"]
    if overrides.get("summary_timeout_sec") is not None:
        timeout_sec = int(overrides["summary_timeout_sec"])
        if timeout_sec <= 0:
            raise ValueError("--summary-timeout-sec must be > 0")
        step_cfg["timeout_sec"] = timeout_sec
    if overrides.get("summary_max_input_chars") is not None:
        max_chars = int(overrides["summary_max_input_chars"])
        if max_chars <= 0:
            raise ValueError("--summary-max-input-chars must be > 0")
        step_cfg["max_input_chars"] = max_chars

    live_override_keys = {
        "live_agent_notes",
        "live_agent_note_provider",
        "live_agent_note_interval_sec",
        "live_agent_note_timeout_sec",
        "live_agent_note_max_tail_chars",
    }
    if any(overrides.get(key) is not None for key in live_override_keys):
        live_cfg: Dict[str, Any] = dict(step_cfg.get("live_agent_notes", {}))
        if overrides.get("live_agent_notes") is not None:
            live_cfg["enabled"] = bool(overrides["live_agent_notes"])
        if overrides.get("live_agent_note_provider") is not None:
            live_cfg["provider"] = overrides["live_agent_note_provider"]
        if overrides.get("live_agent_note_interval_sec") is not None:
            interval_sec = float(overrides["live_agent_note_interval_sec"])
            if interval_sec <= 0:
                raise ValueError("--live-agent-note-interval-sec must be > 0")
            live_cfg["interval_sec"] = interval_sec
        if overrides.get("live_agent_note_timeout_sec") is not None:
            live_timeout_sec = int(overrides["live_agent_note_timeout_sec"])
            if live_timeout_sec <= 0:
                raise ValueError("--live-agent-note-timeout-sec must be > 0")
            live_cfg["timeout_sec"] = live_timeout_sec
        if overrides.get("live_agent_note_max_tail_chars") is not None:
            max_tail_chars = int(overrides["live_agent_note_max_tail_chars"])
            if max_tail_chars <= 0:
                raise ValueError("--live-agent-note-max-tail-chars must be > 0")
            live_cfg["max_tail_chars"] = max_tail_chars
        live_cfg.setdefault("enabled", True)
        live_cfg.setdefault("provider", "claude_haiku_summary")
        live_cfg.setdefault("interval_sec", 15.0)
        live_cfg.setdefault("timeout_sec", 30)
        live_cfg.setdefault("max_tail_chars", 6000)
        live_cfg.setdefault("source", "tmux")
        step_cfg["live_agent_notes"] = live_cfg

    step_cfg["enabled"] = True
    config["step_summaries"] = step_cfg
    return config


def _resolve_cli_path(workspace_dir: Path, raw_path: Optional[str]) -> Optional[Path]:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = workspace_dir / path
    return path.resolve()


def _argv_option_values(argv: tuple[str, ...], flag: str) -> tuple[str, ...]:
    values: list[str] = []
    index = 0
    while index < len(argv):
        if argv[index] == flag and index + 1 < len(argv):
            values.append(argv[index + 1])
            index += 2
            continue
        index += 1
    return tuple(values)


def _argv_has_flag(argv: tuple[str, ...], flag: str) -> bool:
    return any(token == flag for token in argv)


def _load_resume_workflow_bundle(
    *,
    workflow_path: Path,
    workspace_dir: Path,
    run_root: Path,
):
    if workflow_path.suffix != ".orc":
        loader = WorkflowLoader(workspace_dir)
        return loader.load_bundle(workflow_path)

    metadata = read_process_metadata(run_root)
    argv = metadata.argv if metadata is not None else ()

    def first_path(flag: str) -> Optional[Path]:
        values = _argv_option_values(argv, flag)
        return _resolve_cli_path(workspace_dir, values[-1]) if values else None

    source_roots = tuple(
        resolved
        for resolved in (
            _resolve_cli_path(workspace_dir, raw)
            for raw in _argv_option_values(argv, "--source-root")
        )
        if resolved is not None
    )
    entry_values = _argv_option_values(argv, "--entry-workflow")
    frontend_build = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=workflow_path,
            source_roots=source_roots,
            entry_workflow=entry_values[-1] if entry_values else None,
            provider_externs_path=first_path("--provider-externs-file"),
            prompt_externs_path=first_path("--prompt-externs-file"),
            imported_workflow_bundles_path=first_path("--imported-workflow-bundles-file"),
            command_boundaries_path=first_path("--command-boundaries-file"),
            emit_debug_yaml=_argv_has_flag(argv, "--emit-debug-yaml"),
            workspace_root=workspace_dir,
        )
    )
    return frontend_build.validated_bundle


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
    **kwargs
) -> int:
    """Resume an interrupted workflow run.

    Args:
        run_id: The run ID to resume
        repair: Attempt to recover from backup if state is corrupted
        force_restart: Ignore existing state and start new run
        state_dir: Optional override for the runs root directory
        on_error: Error handling mode ('stop' or 'continue')
        max_retries: Maximum retry attempts
        retry_delay_ms: Delay between retries in milliseconds
        backup_state: Enable state backups
        debug: Enable debug logging
        stream_output: Stream provider stdout/stderr live without enabling debug side effects
        summary_mode: Optional summary mode override
        summary_provider: Optional summary provider override
        summary_timeout_sec: Optional summary timeout override
        summary_max_input_chars: Optional summary max input chars override
        summary_profile: Optional summary prompt/snapshot profile override
        live_agent_notes: Optional live note enable override
        live_agent_note_provider: Optional live note provider override
        live_agent_note_interval_sec: Optional live note interval override
        live_agent_note_timeout_sec: Optional live note timeout override
        live_agent_note_max_tail_chars: Optional live note tail size override
        **kwargs: Additional options (ignored)

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    if debug:
        logging.getLogger('orchestrator').setLevel(logging.DEBUG)

    # Match `run` defaults so provider retry policy always receives concrete values.
    max_retries = 1 if max_retries is None else max_retries
    retry_delay_ms = 1000 if retry_delay_ms is None else retry_delay_ms

    # Determine workspace and state directory
    workspace_dir = Path.cwd()
    state_dir_override = Path(state_dir).expanduser().resolve() if state_dir else None
    runs_root = state_dir_override or (workspace_dir / '.orchestrate' / 'runs')
    run_root = runs_root / run_id
    if not run_root.exists():
        logger.error(f"Run directory not found: {run_root}")
        print(f"Error: No run found with ID '{run_id}'", file=sys.stderr)
        return 1

    # Initialize state manager with existing run_id
    # AT-69: debug implies backup_enabled
    state_manager = StateManager(
        workspace=workspace_dir,
        run_id=run_id,
        backup_enabled=backup_state,
        debug=debug,
        state_dir=state_dir_override,
    )

    try:
        # Load existing state
        loaded_state = state_manager.load()
        if loaded_state is None:
            raise FileNotFoundError("State could not be loaded")

    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load state: {e}")
        if repair:
            logger.info("Attempting to repair state from backups")
            if state_manager.attempt_repair():
                print("Successfully repaired state from backup")
                try:
                    loaded_state = state_manager.load()
                    if loaded_state is None:
                        print("Error: Failed to load repaired state", file=sys.stderr)
                        return 1
                except Exception as repair_e:
                    print(f"Error: Failed to load repaired state: {repair_e}", file=sys.stderr)
                    return 1
            else:
                print("Error: Failed to repair state from backups", file=sys.stderr)
                return 1
        else:
            print(f"Error: Failed to load state: {e}", file=sys.stderr)
            print("Use --repair to attempt recovery from backups.", file=sys.stderr)
            return 1

    # Get state information from loaded state
    state = state_manager.state
    if state is None:
        print("Error: No state was loaded", file=sys.stderr)
        return 1
    if state.schema_version != StateManager.SCHEMA_VERSION and not force_restart:
        print(
            "Error: State schema version "
            f"'{state.schema_version}' is not resumable with orchestrator schema "
            f"'{StateManager.SCHEMA_VERSION}'.",
            file=sys.stderr,
        )
        print("Use --force-restart to start a new run on the current schema.", file=sys.stderr)
        return 1
    if (
        not force_restart
        and isinstance(state.error, dict)
        and state.error.get("type") == PROVIDER_SESSION_QUARANTINE_ERROR
    ):
        print(f"Error: {state.error.get('message')}", file=sys.stderr)
        context = state.error.get("context", {})
        if isinstance(context, dict):
            metadata_path = context.get("metadata_path")
            transport_spool_path = context.get("transport_spool_path")
            if metadata_path:
                print(f"Metadata: {metadata_path}", file=sys.stderr)
            if transport_spool_path:
                print(f"Transport spool: {transport_spool_path}", file=sys.stderr)
        print("Use --force-restart to start a new run.", file=sys.stderr)
        return 1

    workflow_file = state.workflow_file
    if not workflow_file:
        print("Error: No workflow file recorded in state", file=sys.stderr)
        return 1

    observability = _merge_observability_overrides(
        state.observability,
        summary_mode=summary_mode,
        summary_provider=summary_provider,
        summary_timeout_sec=summary_timeout_sec,
        summary_max_input_chars=summary_max_input_chars,
        summary_profile=summary_profile,
        live_agent_notes=live_agent_notes,
        live_agent_note_provider=live_agent_note_provider,
        live_agent_note_interval_sec=live_agent_note_interval_sec,
        live_agent_note_timeout_sec=live_agent_note_timeout_sec,
        live_agent_note_max_tail_chars=live_agent_note_max_tail_chars,
    )
    if observability is not None:
        # Persist runtime override so future resumes are deterministic.
        state.observability = observability
        state_manager._write_state()

    workflow_path = Path(workflow_file)
    if not workflow_path.exists():
        # Try relative to current directory
        workflow_path = Path.cwd() / workflow_file
        if not workflow_path.exists():
            print(f"Error: Workflow file not found: {workflow_file}", file=sys.stderr)
            return 1

    # Load workflow
    workspace_dir = Path.cwd()
    try:
        workflow_bundle = _load_resume_workflow_bundle(
            workflow_path=workflow_path,
            workspace_dir=workspace_dir,
            run_root=run_root,
        )
    except LispFrontendCompileError as e:
        for diagnostic in e.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2
    except WorkflowValidationError as e:
        print(f"Error loading workflow: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error loading workflow: {e}", file=sys.stderr)
        return 1

    # Validate checksum unless force restart
    if not force_restart:
        if not state_manager.validate_checksum(str(workflow_path)):
            print("Error: Workflow has been modified since the run started.", file=sys.stderr)
            print("The workflow checksum does not match the recorded checksum.", file=sys.stderr)
            print("Use --force-restart to ignore this and start a new run.", file=sys.stderr)
            return 1

    if force_restart:
        try:
            bound_inputs = bind_workflow_inputs(
                workflow_public_input_contracts(workflow_bundle),
                _public_rebind_inputs_for_force_restart(workflow_bundle, getattr(state, 'bound_inputs', {})),
                workspace=workspace_dir,
            )
        except ValueError as exc:
            logger.error(f"Validation error: {exc}")
            print(f"Error: {exc}", file=sys.stderr)
            return 2

        # AT-68: Start a NEW run with a NEW run_id (ignore existing state)
        import uuid
        new_run_id = uuid.uuid4().hex
        print(f"Force restarting workflow with new run ID: {new_run_id}")
        print(f"(Ignoring existing state from run {run_id})")

        # Create a new StateManager with the new run_id
        state_manager = StateManager(
            workspace=workspace_dir,
            run_id=new_run_id,
            backup_enabled=backup_state,
            debug=debug,
            state_dir=state_dir_override,
        )
        state_manager.initialize(
            workflow_file=str(workflow_path),
            context=dict(workflow_context(workflow_bundle)),
            bound_inputs=bound_inputs,
            observability=observability,
        )
    else:
        # Find the next step to execute
        steps_state = state.steps
        current_status = state.status

        if current_status == 'completed':
            print(f"Run {run_id} has already completed successfully")
            return 0
        elif current_status == 'failed':
            print(f"Run {run_id} previously failed. Attempting to resume from last incomplete step.")

        # Log resume information
        completed_steps = []
        pending_steps = []
        for step_name, step_result in steps_state.items():
            if isinstance(step_result, dict):
                status = step_result.get('status', 'pending')
                if status in ['completed', 'skipped']:
                    completed_steps.append(step_name)
                else:
                    pending_steps.append(step_name)

        if completed_steps:
            print(f"Resuming run {run_id}")
            print(f"  Completed steps: {', '.join(completed_steps)}")
        if pending_steps:
            print(f"  Pending steps: {', '.join(pending_steps)}")

    session_id: str | None = None
    session_status = "failed"
    try:
        session_id = open_executor_session(
            state_manager.state,
            entrypoint="run" if force_restart else "resume",
            process_start_time=process_start_time_token(os.getpid()),
        )
        state_manager._write_state()
        try:
            write_process_metadata(
                state_manager.run_root,
                executor_session_id=session_id,
            )
        except OSError as exc:
            logger.debug("Failed to write monitor process metadata: %s", exc)

        # Initialize executor with existing state
        workspace_dir = Path.cwd()
        executor = WorkflowExecutor(
            workflow=workflow_bundle,
            workspace=workspace_dir,
            state_manager=state_manager,
            max_retries=max_retries,
            retry_delay_ms=retry_delay_ms,
            debug=debug,
            stream_output=stream_output,
            observability=observability,
        )

        # Execute workflow
        # AT-68: For force_restart, we start fresh without resume flag
        result = executor.execute(
            run_id=run_id,
            on_error=on_error,
            max_retries=max_retries,
            retry_delay_ms=retry_delay_ms,
            resume=not force_restart  # Don't resume if force_restart
        )

        final_status = result.get('status', 'unknown')
        run_error = result.get('error') if isinstance(result, dict) else None
        if isinstance(run_error, dict) and run_error.get("type") == PROVIDER_SESSION_QUARANTINE_ERROR:
            print(f"Error: {run_error.get('message')}", file=sys.stderr)
            context = run_error.get("context", {})
            if isinstance(context, dict):
                metadata_path = context.get("metadata_path")
                transport_spool_path = context.get("transport_spool_path")
                if metadata_path:
                    print(f"Metadata: {metadata_path}", file=sys.stderr)
                if transport_spool_path:
                    print(f"Transport spool: {transport_spool_path}", file=sys.stderr)
        elif final_status == 'failed' and isinstance(run_error, dict):
            message = run_error.get("message")
            if isinstance(message, str) and message:
                print(f"Error: {message}", file=sys.stderr)
        if final_status == 'completed':
            session_status = "completed"
            print("Workflow resumed and completed successfully")
            return 0
        else:
            session_status = "failed" if final_status == "failed" else "completed"
            print(f"Workflow execution ended with status: {final_status}")
            return 1 if final_status == 'failed' else 0

    except KeyboardInterrupt:
        print("\nWorkflow execution interrupted by user")
        session_status = "interrupted"
        state_manager.update_status('suspended')
        return 130  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}", exc_info=True)
        print(f"Error during workflow execution: {e}", file=sys.stderr)
        state_manager.update_status('failed')
        return 1
    finally:
        if session_id is not None and state_manager.state is not None:
            close_executor_session(
                state_manager.state,
                session_id=session_id,
                status=session_status,
            )
            state_manager._write_state()
