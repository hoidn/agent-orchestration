"""Resume command implementation."""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import sys

from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.exceptions import WorkflowValidationError


logger = logging.getLogger(__name__)


def resume_workflow(
    run_id: str,
    repair: bool = False,
    force_restart: bool = False,
    on_error: str = 'stop',
    max_retries: Optional[int] = None,
    retry_delay_ms: Optional[int] = None,
    backup_state: bool = False,
    debug: bool = False,
    **kwargs
) -> int:
    """Resume an interrupted workflow run.

    Args:
        run_id: The run ID to resume
        repair: Attempt to recover from backup if state is corrupted
        force_restart: Ignore existing state and start new run
        on_error: Error handling mode ('stop' or 'continue')
        max_retries: Maximum retry attempts
        retry_delay_ms: Delay between retries in milliseconds
        backup_state: Enable state backups
        debug: Enable debug logging
        **kwargs: Additional options (ignored)

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    if debug:
        logging.getLogger('orchestrator').setLevel(logging.DEBUG)

    # Determine workspace and state directory
    workspace_dir = Path.cwd()
    state_dir = workspace_dir / '.orchestrate' / 'runs' / run_id
    if not state_dir.exists():
        logger.error(f"Run directory not found: {state_dir}")
        print(f"Error: No run found with ID '{run_id}'", file=sys.stderr)
        return 1

    # Initialize state manager with existing run_id
    # AT-69: debug implies backup_enabled
    state_manager = StateManager(workspace=workspace_dir, run_id=run_id, backup_enabled=backup_state, debug=debug)

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

    workflow_file = state.workflow_file
    workflow_checksum = state.workflow_checksum

    if not workflow_file:
        print("Error: No workflow file recorded in state", file=sys.stderr)
        return 1

    workflow_path = Path(workflow_file)
    if not workflow_path.exists():
        # Try relative to current directory
        workflow_path = Path.cwd() / workflow_file
        if not workflow_path.exists():
            print(f"Error: Workflow file not found: {workflow_file}", file=sys.stderr)
            return 1

    # Load workflow
    workspace_dir = Path.cwd()
    loader = WorkflowLoader(workspace_dir)
    try:
        workflow = loader.load(workflow_path)
        # Calculate checksum separately using StateManager's method
        checksum = state_manager._calculate_checksum(workflow_path)
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
            debug=debug
        )
        state_manager.initialize(
            workflow_file=str(workflow_path),
            context=workflow.get('context', {})
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

    # Initialize executor with existing state
    workspace_dir = Path.cwd()
    executor = WorkflowExecutor(
        workflow=workflow,
        workspace_dir=workspace_dir,
        state_manager=state_manager,
        max_retries=max_retries,
        retry_delay_ms=retry_delay_ms,
        debug=debug
    )

    # Execute workflow
    try:
        # AT-68: For force_restart, we start fresh without resume flag
        result = executor.execute(
            run_id=run_id,
            on_error=on_error,
            max_retries=max_retries,
            retry_delay_ms=retry_delay_ms,
            resume=not force_restart  # Don't resume if force_restart
        )

        final_status = result.get('status', 'unknown')
        if final_status == 'completed':
            print(f"Workflow resumed and completed successfully")
            return 0
        else:
            print(f"Workflow execution ended with status: {final_status}")
            return 1 if final_status == 'failed' else 0

    except KeyboardInterrupt:
        print("\nWorkflow execution interrupted by user")
        state_manager.update_status('suspended')
        return 130  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}", exc_info=True)
        print(f"Error during workflow execution: {e}", file=sys.stderr)
        state_manager.update_status('failed')
        return 1