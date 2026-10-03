"""The pure public run slice for checked Workflow Lisp programs."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import logging
from pathlib import Path
from typing import Any

from orchestrator.state import StateManager
from orchestrator.run_lock import workspace_run_lock
from orchestrator.workflow.evaluated.authority import publish_run_authority
from orchestrator.workflow.evaluated.runtime import execute_pure_run
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.signatures import (
    WorkflowSignatureError,
    bind_workflow_inputs,
)
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic
from orchestrator.workflow_lisp.reader import SourceReadTrace


logger = logging.getLogger(__name__)


def bind_program_inputs(
    program: Any,
    provided: Mapping[str, Any],
    *,
    workspace: Path,
) -> dict[str, Any]:
    """Validate CLI values, defaults and existence-bearing paths at the boundary."""
    params = dict(program.tree["params"])
    defaults = program.tree.get("defaults", {})
    schemas = {
        name: {
            **transport_schema_for_descriptor(
                descriptor, allow_nested_structures=True
            ),
            **({"default": defaults[name]} if name in defaults else {}),
        }
        for name, descriptor in params.items()
    }
    validated = bind_workflow_inputs(
        schemas, provided, workspace, finite_floats=True
    )
    bound: dict[str, Any] = {}
    for name, descriptor in params.items():
        try:
            bound[name] = coerce_evaluated_value(
                validated[name], descriptor, context=f"input {name}"
            ).json_value()
        except (TypeError, ValueError) as exc:
            raise WorkflowSignatureError(
                f"Workflow input binding failed: {exc}",
                context={"scope": "workflow_inputs", "input": name, "reason": "invalid_value"},
            ) from exc
    return bound


def _request(args: Any, workflow_path: Path, workspace: Path) -> FrontendBuildRequest:
    from orchestrator._common.safe_tree import resolve_path_preserving_fd

    def optional_path(name: str) -> Path | None:
        value = getattr(args, name, None)
        return resolve_path_preserving_fd(value) if value else None

    return FrontendBuildRequest(
        source_path=workflow_path,
        source_roots=tuple(
            resolve_path_preserving_fd(path)
            for path in (getattr(args, "source_root", None) or ())
        ),
        entry_workflow=getattr(args, "entry_workflow", None),
        provider_externs_path=optional_path("provider_externs_file"),
        prompt_externs_path=optional_path("prompt_externs_file"),
        imported_workflow_bundles_path=optional_path("imported_workflow_bundles_file"),
        command_boundaries_path=optional_path("command_boundaries_file"),
        emit_debug_yaml=bool(getattr(args, "emit_debug_yaml", False)),
        workspace_root=workspace,
    )


def run_evaluated_workflow(
    args: Any,
    *,
    workspace: Path,
    workflow_path: Path,
    logical_workflow_path: Path | None,
    run_id: str | None,
    source_read_trace: SourceReadTrace,
) -> tuple[int, str | None, Path | None, Mapping[str, Any]]:
    """Build and run an evaluated target without entering legacy run state."""
    from orchestrator.cli.commands.run import parse_inputs, _workflow_path_for_state

    try:
        built = build_closed_program_bundle(
            _request(args, workflow_path, workspace),
            source_read_trace=source_read_trace,
        )
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2, None, None, {}
    bound_inputs = bind_program_inputs(
        built.program, parse_inputs(args), workspace=workspace
    )
    if getattr(args, "dry_run", False):
        return 0, None, None, {}

    state_manager = StateManager(
        workspace=workspace,
        backup_enabled=getattr(args, "backup_state", False),
        debug=getattr(args, "debug", False),
        state_dir=Path(args.state_dir).expanduser().resolve()
        if getattr(args, "state_dir", None) else None,
        run_id=run_id,
    )
    source_bytes = source_read_trace.raw_bytes_by_path[workflow_path]
    workflow_file = _workflow_path_for_state(
        workspace, logical_workflow_path or workflow_path
    )
    try:
        with workspace_run_lock(workspace, state_manager.run_id):
            with publish_run_authority(
                state_manager.run_root,
                built.program,
                run_id=state_manager.run_id,
                workflow_file=workflow_file,
                workflow_checksum="sha256:" + hashlib.sha256(source_bytes).hexdigest(),
                bound_inputs=bound_inputs,
            ) as authority:
                exit_code, value = execute_pure_run(
                    authority,
                    bound_inputs,
                    run_id=state_manager.run_id,
                    workspace=workspace,
                    provider_io=built.provider_io,
                )
                if exit_code != 0:
                    outputs: Mapping[str, Any] = {}
                elif isinstance(value, Mapping):
                    outputs = dict(value)
                else:
                    outputs = {"__result__": value}
                return exit_code, state_manager.run_id, state_manager.run_root, outputs
    finally:
        state_manager.close()
