"""One fresh dynamic run; effects remain unsupported until direct performers land."""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import logging
import os
from pathlib import Path

from orchestrator.prompt_scaffold_fs import open_root_creating
from orchestrator.run_lock import reserved_run_writer_lock, workspace_run_lock
from orchestrator.state import StateManager
from orchestrator.workflow.workspace_files import WorkspaceFiles
from .evaluator import evaluate
from .state import error_payload, publish_dynamic_run

logger = logging.getLogger(__name__)


def execute_dynamic_run(built, inputs, *, workspace, workflow_path, state_dir=None):
    """Publish captured checked authority before source-free pure evaluation."""
    run_id = StateManager.new_run_id()
    runs_root = Path(state_dir).expanduser().absolute() if state_dir else workspace / '.orchestrate/runs'
    run_root = runs_root / run_id
    source_bytes = built.source_read_trace.raw_bytes_by_path[workflow_path]
    try:
        with ExitStack() as owners:
            owners.enter_context(workspace_run_lock(workspace, run_id))
            parent = WorkspaceFiles(runs_root, root_fd=open_root_creating(runs_root), owns_root=True)
            owners.callback(parent.close)
            files = parent.mkdir_exclusive(run_id)
            owners.callback(files.close)
            info = os.fstat(files.root_fd)
            owners.enter_context(reserved_run_writer_lock(run_root, (info.st_dev, info.st_ino)))
            run = publish_dynamic_run(files, built.program, run_id=run_id, workflow_file=str(workflow_path),
                workflow_checksum='sha256:' + hashlib.sha256(source_bytes).hexdigest(),
                bound_inputs=inputs, workspace=workspace)
            workspace_files = WorkspaceFiles(workspace)
            owners.callback(workspace_files.close)
            try:
                result = evaluate(run.program, inputs, workspace_files=workspace_files)
            except ValueError as exc:
                steps = getattr(exc, 'metadata', {}).get('steps', run.state['steps_used'])
                run.fail(error_payload(exc), steps=steps)
                logger.error('[%s] %s', getattr(exc, 'code', 'dynamic_execution_failed'), exc)
                return 1, run_id, run_root, None
            run.complete(result.value, steps=result.steps)
            return 0, run_id, run_root, result.value
    except (OSError, ValueError, RuntimeError) as exc:
        logger.error('[%s] %s', getattr(exc, 'code', 'dynamic_execution_failed'), exc)
        return 1, run_id, run_root, None
