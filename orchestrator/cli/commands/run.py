"""Run command implementation with safety checks."""

import json
import logging
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from argparse import Namespace

from orchestrator.loader import WorkflowLoader
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_bundle as loaded_workflow_bundle,
    workflow_context,
    workflow_input_contracts,
)
from orchestrator.workflow.linting import lint_workflow
from orchestrator.workflow.signatures import bind_workflow_inputs


logger = logging.getLogger(__name__)


def build_observability_config(args: Namespace) -> Optional[Dict[str, Any]]:
    """Build runtime observability config from CLI flags.

    Observability is runtime-only (not DSL). Summaries default to async when enabled.
    """
    step_summaries_enabled = bool(getattr(args, 'step_summaries', False))
    summary_mode = getattr(args, 'summary_mode', None)

    if summary_mode and not step_summaries_enabled:
        # Explicit mode should implicitly enable summaries.
        step_summaries_enabled = True

    if not step_summaries_enabled:
        return None

    summary_timeout_sec = int(getattr(args, 'summary_timeout_sec', 120))
    summary_max_input_chars = int(getattr(args, 'summary_max_input_chars', 12000))
    if summary_timeout_sec <= 0:
        raise ValueError("--summary-timeout-sec must be > 0")
    if summary_max_input_chars <= 0:
        raise ValueError("--summary-max-input-chars must be > 0")

    return {
        "step_summaries": {
            "enabled": True,
            "mode": summary_mode or "async",
            "provider": getattr(args, 'summary_provider', 'claude_sonnet_summary'),
            "timeout_sec": summary_timeout_sec,
            "max_input_chars": summary_max_input_chars,
            "best_effort": True,
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


def run_workflow(args: Namespace) -> int:
    """
    Run a workflow with safety checks.

    Implements AT-11, AT-12, AT-16
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
        state_dir_override = Path(args.state_dir).expanduser().resolve() if args.state_dir else None

        # Load workflow
        workflow_path = Path(args.workflow).resolve()
        if not workflow_path.exists():
            logger.error(f"Workflow file not found: {workflow_path}")
            return 1

        logger.info(f"Loading workflow: {workflow_path}")
        loader = WorkflowLoader(workspace)
        try:
            workflow = loader.load_bundle(workflow_path)
        except WorkflowValidationError as e:
            # Print validation errors to stderr
            for error in e.errors:
                logger.error(f"Validation error: {error.message}")
            return e.exit_code
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
                # Default to RUN_ROOT/processed.zip
                run_id = datetime.now().strftime("%Y%m%dT%H%M%SZ")
                runs_root = state_dir_override or (workspace / '.orchestrate' / 'runs')
                run_root = runs_root / run_id
                archive_dest = run_root / 'processed.zip'

            validate_archive_destination(processed_dir, archive_dest)

            if args.dry_run:
                logger.info(f"[DRY RUN] Would archive processed directory to: {archive_dest}")

        # Dry run mode - just validate
        raw_inputs = parse_inputs(args)
        bound_inputs = bind_workflow_inputs(
            workflow_input_contracts(workflow),
            raw_inputs,
            workspace=workspace,
        )
        lint_warnings = lint_workflow(workflow)

        if args.dry_run:
            for warning in lint_warnings:
                logger.warning(
                    "[LINT] %s (%s at %s)",
                    warning.get("message"),
                    warning.get("code"),
                    warning.get("path"),
                )
            logger.info("[DRY RUN] Workflow validation successful")
            return 0

        # Parse context
        context = parse_context(args, workflow_context=dict(workflow_context(workflow)))

        observability = build_observability_config(args)

        # Initialize state manager
        # AT-69: --debug implies backup_enabled
        state_manager = StateManager(
            workspace=workspace,
            backup_enabled=args.backup_state,
            debug=args.debug if hasattr(args, 'debug') else False,
            state_dir=state_dir_override,
        )

        # Create new run
        run_state = state_manager.initialize(
            str(workflow_path.relative_to(workspace)),
            context,
            bound_inputs=bound_inputs,
            observability=observability,
        )
        logger.info(f"Created new run: {run_state.run_id}")

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
        )

        result = executor.execute(
            run_id=run_state.run_id,
            on_error=args.on_error,
            max_retries=args.max_retries,
            retry_delay_ms=args.retry_delay
        )

        if isinstance(result, dict):
            run_succeeded = result.get("status") == "completed"
        else:
            run_succeeded = bool(result)

        # Archive processed directory on successful completion only.
        if run_succeeded and archive_dest:
            archive_processed_directory(processed_dir, archive_dest)

        return 0 if run_succeeded else 1

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 2
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
