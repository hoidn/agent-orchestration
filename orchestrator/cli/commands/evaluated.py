"""The pure public run slice for checked Workflow Lisp programs."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack
import os
import hashlib
import logging
from argparse import Namespace
from pathlib import Path
from typing import Any

from orchestrator.state import StateManager
from orchestrator.run_lock import workspace_run_lock, reserved_run_writer_lock, ReservedRunRootError, run_root_matches_fd
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow.evaluated.authority import (
    publish_run_authority, load_run_authority, load_run_header,
)
from orchestrator.workflow.evaluated.interpreters import check_command_interpreter
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.evaluated.runtime import execute_pure_resume, execute_pure_run
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.signatures import (
    WorkflowSignatureError,
    bind_workflow_inputs,
)
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import (
    build_closed_program_bundle, prepare_closed_program_bundle,
)
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


def _locator(path: Path, workspace: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def capture_resume_request(args: Any, request: FrontendBuildRequest, workspace: Path, *, logical: bool = False) -> dict[str, Any]:
    """Capture the effective request and explicit inputs before applying defaults."""
    from orchestrator.cli.commands.run import parse_inputs
    locator = _durable_locator if logical else _locator
    recipe = {
        field: locator(getattr(request, field), workspace) if getattr(request, field) is not None else None
        for field in ("provider_externs_path", "prompt_externs_path", "imported_workflow_bundles_path", "command_boundaries_path")
    }
    input_file = getattr(args, "logical_input_file", None) if logical else getattr(args, "input_file", None)
    recipe.update(
        source_roots=[locator(path, workspace) for path in request.source_roots],
        entry_workflow=request.entry_workflow,
        input_file=locator(Path(input_file), workspace) if input_file else None,
        input_overrides=parse_inputs(Namespace(input=getattr(args, "input", None))),
    )
    return recipe


def _recipe_path(locator: str | None, workspace: Path) -> Path | None:
    return workspace / locator if locator is not None else None


def _bind_recipe(program: Any, recipe: Mapping[str, Any], workspace: Path, run_files=None) -> dict[str, Any]:
    from orchestrator.cli.commands.run import parse_inputs
    input_path = _resume_physical_path(_recipe_path(recipe["input_file"], workspace), run_files)
    provided = parse_inputs(Namespace(input_file=str(input_path) if input_path is not None else None))
    provided.update(recipe["input_overrides"])
    return bind_program_inputs(program, provided, workspace=workspace)


def _resume_build_request(header: Mapping[str, Any], workspace: Path, run_files=None) -> FrontendBuildRequest:
    recipe = header["resume_request"]
    return FrontendBuildRequest(
        source_path=_resume_physical_path(_recipe_path(header["workflow_file"], workspace), run_files),
        source_roots=tuple(_resume_physical_path(_recipe_path(root, workspace), run_files) for root in recipe["source_roots"]),
        entry_workflow=recipe["entry_workflow"],
        workspace_root=workspace,
        **{field: _resume_physical_path(_recipe_path(recipe[field], workspace), run_files) for field in (
            "provider_externs_path", "prompt_externs_path", "imported_workflow_bundles_path", "command_boundaries_path")},
    )


class _ResumeRefusal(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def resume_evaluated_workflow(run_root: Path, *, workspace: Path, force_restart: bool = False, run_ref_root: str | None = None, run_files: WorkspaceFiles | None = None) -> int:
    """Rebuild and compare before loading the stored program, pins or memo."""
    try:
        if run_files is not None:
            from orchestrator.workflow.evaluated.authority import _require_retained_root
            _require_retained_root(run_files)
        header = load_run_header(run_root, run_files=run_files)
        if "resume_request" not in header:
            raise _ResumeRefusal("resume_request_missing", "run header has no durable rebuild request")
        if force_restart:
            raise _ResumeRefusal("evaluated_execution_unavailable", "force restart is unavailable for evaluated execution")
        if run_ref_root is not None:
            from orchestrator.cli.run_ref_root import resolve_run_ref_root
            selected_root = resolve_run_ref_root(run_ref_root).as_posix()
            if selected_root != header.get("run_ref_root", selected_root):
                raise _ResumeRefusal(
                    "resume_run_ref_root_changed",
                    "explicit run-reference root differs from the run header",
                )
        recipe = header["resume_request"]
        request = _resume_build_request(header, workspace, run_files)
        fresh = prepare_closed_program_bundle(request, source_read_trace=SourceReadTrace())
        if fresh.program.digest != header["program_digest"]:
            raise _ResumeRefusal("resume_program_changed", "current program differs from the run header")
        inputs = _bind_recipe(fresh.program, recipe, workspace, run_files)
        if canonical_sha256(inputs) != header["input_digest"]:
            raise _ResumeRefusal("resume_inputs_changed", "current bound inputs differ from the run header")
        authority = load_run_authority(run_root, header=header, run_files=run_files)
        provider_io = fresh.provider_io.bind(authority.program)
        _warn_changed_interpreters(authority)
        exit_code, _ = execute_pure_resume(authority, inputs, run_id=run_root.name, workspace=workspace, provider_io=provider_io)
        return exit_code
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2
    except (OSError, UnicodeError, ValueError, ReservedRunRootError) as exc:
        logger.error("[%s] %s", getattr(exc, "code", "resume_preflight_failed"), exc)
        return 2


def run_evaluated_workflow(
    args: Any,
    *,
    workspace: Path,
    workflow_path: Path,
    logical_workflow_path: Path | None,
    run_id: str | None,
    source_read_trace: SourceReadTrace,
    expected_run_identity: tuple[int, int] | None = None,
    reserved_run_fd: int | None = None,
) -> tuple[int, str | None, Path | None, Mapping[str, Any]]:
    """Build and run an evaluated target without entering legacy run state."""
    reserved = expected_run_identity is not None or reserved_run_fd is not None
    request, logical, resume_request = _capture_run_request(args, workflow_path, workspace, reserved)
    try:
        builder = prepare_closed_program_bundle if reserved else build_closed_program_bundle
        built = builder(
            request,
            source_read_trace=source_read_trace,
        )
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2, None, None, {}
    bound_inputs = _bind_initial_inputs(built.program, args, resume_request, workspace) if reserved else _bind_recipe(built.program, resume_request, workspace)
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
    workflow_file = _run_source_locator(logical, workspace, reserved, logical_workflow_path)
    try:
        with ExitStack() as locks:
            locks.enter_context(workspace_run_lock(workspace, state_manager.run_id))
            run_files = _reserved_files(locks, state_manager.run_root, expected_run_identity, reserved_run_fd) if reserved else None
            with publish_run_authority(
                state_manager.run_root,
                built.program,
                run_id=state_manager.run_id,
                workflow_file=workflow_file,
                workflow_checksum="sha256:" + hashlib.sha256(source_bytes).hexdigest(),
                bound_inputs=bound_inputs,
                resume_request=resume_request,
                run_ref_root=getattr(args, "run_ref_root", None),
                run_files=run_files,
            ) as authority:
                exit_code, value = execute_pure_run(
                    authority,
                    bound_inputs,
                    run_id=state_manager.run_id,
                    workspace=workspace,
                    provider_io=built.provider_io,
                )
                return exit_code, state_manager.run_id, state_manager.run_root, _run_outputs(exit_code, value)
    finally:
        state_manager.close()


def _durable_locator(path: Path, workspace: Path) -> str:
    resolved = Path(os.path.abspath(path))
    try:
        return resolved.relative_to(workspace).as_posix()
    except ValueError:
        return resolved.as_posix()


def _bind_initial_inputs(program, args, recipe, workspace):
    from orchestrator.cli.commands.run import parse_inputs
    provided = parse_inputs(Namespace(input_file=getattr(args, "input_file", None)))
    provided.update(recipe["input_overrides"])
    return bind_program_inputs(program, provided, workspace=workspace)


def _reserved_files(stack, root, identity, fd):
    if identity is None:
        raise ReservedRunRootError(root, "has no reserved identity")
    if fd is None:
        fd = stack.enter_context(reserved_run_writer_lock(root, identity))
    info = os.fstat(fd)
    if (info.st_dev, info.st_ino) != identity or not run_root_matches_fd(root, fd):
        raise ReservedRunRootError(root, "changed before publication")
    owner = WorkspaceFiles(root, root_fd=fd)
    stack.callback(owner.close)
    return owner


def _validate_reserved_pair(args, physical, logical, source, workspace):
    if not isinstance(physical, FrontendBuildRequest) or not isinstance(logical, FrontendBuildRequest):
        raise ValueError("reserved entry requires a complete physical/logical build request pair")
    if physical != _request(args, source, workspace):
        raise ValueError("physical request differs from the effective invocation")
    if not hasattr(args, "logical_input_file"):
        raise ValueError("reserved input-file requires an explicit logical counterpart")
    for name in ("entry_workflow", "boundary_admission_profile", "emit_debug_yaml", "lint_profile", "lowering_route", "workspace_root"):
        if getattr(physical, name) != getattr(logical, name):
            raise ValueError(f"reserved request option differs: {name}")
    if len(physical.source_roots) != len(logical.source_roots):
        raise ValueError("reserved source root multiplicity differs")
    pairs = [(physical.source_path, logical.source_path), *zip(physical.source_roots, logical.source_roots)]
    pairs.extend((getattr(physical, name), getattr(logical, name)) for name in ("provider_externs_path", "prompt_externs_path", "imported_workflow_bundles_path", "command_boundaries_path"))
    pairs.append((getattr(args, "input_file", None), args.logical_input_file))
    anchors = {}
    for physical_path, logical_path in pairs:
        _validate_locator_pair(physical_path, logical_path, workspace, anchors)


def _validate_locator_pair(physical, logical, workspace, anchors):
    from orchestrator.workflow.evaluated.authority import _validate_locator
    if physical is None or logical is None:
        if physical is not None or logical is not None:
            raise ValueError("reserved locator has no counterpart")
        return
    logical = Path(os.path.abspath(logical))
    _validate_locator(_durable_locator(logical, workspace))
    physical = Path(physical)
    parts = physical.parts
    if parts[:4] == ("/", "proc", "self", "fd") and len(parts) >= 5:
        _bind_fd_locator(parts, logical, anchors)
    elif Path(os.path.abspath(physical)) != logical:
        raise ValueError("reserved physical/logical locator differs")


def _resume_physical_path(path: Path | None, run_files: WorkspaceFiles | None) -> Path | None:
    if path is None or run_files is None:
        return path
    try:
        relative = path.relative_to(run_files.workspace)
    except ValueError:
        return path
    return Path(f"/proc/self/fd/{run_files.root_fd}") / relative


def _bind_fd_locator(parts, logical, anchors):
    tail = parts[5:]
    if tail and logical.parts[-len(tail):] != tail:
        raise ValueError("reserved locator leaves differ")
    base = logical.parents[len(tail)-1] if tail else logical
    anchor = parts[:5]
    if anchor in anchors and anchors[anchor] != base:
        raise ValueError("reserved locator order or root differs")
    anchors[anchor] = base


def _capture_run_request(args, source, workspace, reserved):
    request = _request(args, source, workspace)
    logical = request
    if reserved:
        request = getattr(args, "physical_build_request", None)
        logical = getattr(args, "logical_build_request", None)
        _validate_reserved_pair(args, request, logical, source, workspace)
    return request, logical, capture_resume_request(args, logical, workspace, logical=reserved)


def _run_source_locator(request, workspace, reserved, logical_workflow_path):
    from orchestrator.cli.commands.run import _workflow_path_for_state
    if reserved:
        return _durable_locator(request.source_path, workspace)
    return _workflow_path_for_state(workspace, logical_workflow_path or request.source_path)


def _run_outputs(exit_code, value):
    if exit_code != 0:
        return {}
    return dict(value) if isinstance(value, Mapping) else {"__result__": value}


def _warn_changed_interpreters(authority):
    for pin in authority.header["interpreters"].values():
        diagnostic = check_command_interpreter(pin)
        if diagnostic:
            logger.warning("[%s] recorded interpreter bytes changed: %s", diagnostic, pin["path"])
