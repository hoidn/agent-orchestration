"""Run command implementation with safety checks."""

import json
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from argparse import Namespace

from orchestrator.loader import WorkflowLoader
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


logger = logging.getLogger(__name__)


def parse_context(args: Namespace) -> Dict[str, str]:
    """Parse context variables from command line arguments."""
    context = {}

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
            f"Safety check failed: cannot clean WORKSPACE root directory"
        )

    if workspace.is_relative_to(processed_abs):
        raise ValueError(
            f"Safety check failed: cannot clean parent directory of WORKSPACE"
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

    logger.info(f"Successfully cleaned processed directory")


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

        # Load workflow
        workflow_path = Path(args.workflow).resolve()
        if not workflow_path.exists():
            logger.error(f"Workflow file not found: {workflow_path}")
            return 1

        logger.info(f"Loading workflow: {workflow_path}")
        loader = WorkflowLoader(workspace)
        try:
            workflow = loader.load(workflow_path)
        except WorkflowValidationError as e:
            # Print validation errors to stderr
            for error in e.errors:
                logger.error(f"Validation error: {error.message}")
            return e.exit_code

        # Determine processed directory
        processed_dir = workspace / (workflow.get('processed_dir', 'processed'))

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
                state_dir = workspace / '.orchestrate' / 'runs'
                run_root = state_dir / run_id
                archive_dest = run_root / 'processed.zip'

            validate_archive_destination(processed_dir, archive_dest)

            if args.dry_run:
                logger.info(f"[DRY RUN] Would archive processed directory to: {archive_dest}")

        # Dry run mode - just validate
        if args.dry_run:
            logger.info("[DRY RUN] Workflow validation successful")
            return 0

        # Parse context
        context = parse_context(args)

        # Initialize state manager
        # AT-69: --debug implies backup_enabled
        state_manager = StateManager(
            workspace=workspace,
            backup_enabled=args.backup_state,
            debug=args.debug if hasattr(args, 'debug') else False
        )

        # Create new run
        run_state = state_manager.initialize(str(workflow_path.relative_to(workspace)), context)
        logger.info(f"Created new run: {run_state.run_id}")

        # Execute workflow
        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=workspace,
            state_manager=state_manager,
            logs_dir=state_manager.logs_dir,
            debug=args.debug if hasattr(args, 'debug') else False,
            max_retries=args.max_retries,
            retry_delay_ms=args.retry_delay
        )

        result = executor.execute(
            run_id=run_state.run_id,
            on_error=args.on_error,
            max_retries=args.max_retries,
            retry_delay_ms=args.retry_delay
        )

        # Archive processed directory on success
        if result and archive_dest:
            archive_processed_directory(processed_dir, archive_dest)

        return 0 if result else 1

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 2
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1