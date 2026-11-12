"""The pure public run slice for checked Workflow Lisp programs."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import replace
import os
import hashlib
import logging
from argparse import Namespace
from pathlib import Path
from typing import Any

from orchestrator.cli.progress import TerminalReporter, say
from orchestrator.state import StateManager
from orchestrator.run_lock import workspace_run_lock, reserved_run_writer_lock, ReservedRunRootError, run_root_matches_fd
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow.evaluated.authority import (
    MEMO_FILENAME, publish_run_authority, load_run_authority, load_run_header,
)
from orchestrator.workflow.evaluated.commands import workspace_relative_path
from orchestrator.workflow.evaluated.interpreters import check_command_interpreter
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import _read_bytes, read_memo
from orchestrator.workflow.evaluated.memo_reducer_lineage import current_program_digest
from orchestrator.workflow.evaluated.runtime import execute_pure_resume, execute_pure_run
from orchestrator.workflow.evaluated.spend_cap import pending_attempts
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.signatures import (
    WorkflowSignatureError,
    bind_workflow_inputs,
)
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import (
    ConfinedRunRefUnavailable, build_closed_program_bundle, prepare_closed_program_bundle,
    refuse_confined_run_ref_sites,
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
    def __init__(self, code: str, message: str, **details: Any):
        self.code = code
        self.__dict__.update(details)
        super().__init__(message)


def _require_matching_result_root(header: Mapping[str, Any], run_root: Path, workspace: Path) -> None:
    if "result_root" not in header:
        return
    current = workspace_relative_path(Path(workspace).resolve(), Path(run_root))
    if current != header["result_root"]:
        raise _ResumeRefusal(
            "resume_result_root_changed",
            f"run root {current!r} differs from the run header result_root {header['result_root']!r}",
        )


def prepare_evaluated_resume(run_root: Path, *, workspace: Path, force_restart=False,
                             run_ref_root=None, run_files=None):
    """Read-only ordinary rebuild and input preflight, shared by resume and host writes."""
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
    _require_matching_result_root(header, run_root, workspace)
    recipe = header["resume_request"]
    request = _resume_build_request(header, workspace, run_files)
    fresh = prepare_closed_program_bundle(request, source_read_trace=SourceReadTrace())
    refuse_confined_run_ref_sites(fresh.program)
    if fresh.program.digest != current_program_digest(_read_bytes(Path(run_root) / MEMO_FILENAME, run_files),
                                                      header["program_digest"]):        # only `rebased` records read
        raise _ResumeRefusal("resume_program_changed", "current program differs from the run header",
                             fresh_program=fresh.program)
    inputs = _bind_recipe(fresh.program, recipe, workspace, run_files)
    if canonical_sha256(inputs) != header["input_digest"]:
        recorded = header.get("bound_inputs", {})
        raise _ResumeRefusal("resume_inputs_changed", "current bound inputs differ from the run header",
                             changed_inputs=sorted(name for name in {*recorded, *inputs} if recorded.get(name) != inputs.get(name)))
    authority = load_run_authority(run_root, header=header, run_files=run_files)
    provider_io = fresh.provider_io.bind(authority.program)
    return authority, inputs, provider_io


def resume_evaluated_workflow(run_root: Path, *, workspace: Path, force_restart: bool = False, run_ref_root: str | None = None, run_files: WorkspaceFiles | None = None, stream_output: bool = True, quiet: bool = False, state_dir: str | None = None, terminal_lines: bool = False, max_cost_usd: float | None = None, accept_changes: bool = False) -> int:
    """Rebuild and compare before loading the stored program, pins or memo.

    `terminal_lines` (the command line sets it) prints progress, recovery lines and the result;
    `max_cost_usd` is this invocation's spend cap (never stored).
    """
    reporter = TerminalReporter(run_root.name, run_root, quiet=quiet, state_dir=state_dir, enabled=terminal_lines)
    try:
        authority, inputs, provider_io = prepare_evaluated_resume(
            run_root, workspace=workspace, force_restart=force_restart,
            run_ref_root=run_ref_root, run_files=run_files)
        authority = replace(authority, accept_changes=accept_changes)
        _warn_changed_interpreters(authority)
        reporter.announce(lazy=True)
        exit_code, _ = _execute_reported(
            reporter, execute_pure_resume, authority, inputs, stored_program=authority.program,
            spend_cap_usd=max_cost_usd, run_id=run_root.name, workspace=workspace, provider_io=provider_io, stream_output=stream_output)
        return exit_code
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2
    except (OSError, UnicodeError, ValueError, ReservedRunRootError) as exc:
        logger.error("[%s] %s", getattr(exc, "code", "resume_preflight_failed"), exc)
        reporter.error(exc, **_stored_context(exc, run_root, run_files))
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
        refuse_confined_run_ref_sites(built.program)
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2, None, None, {}
    except ConfinedRunRefUnavailable as exc:
        logger.error("[%s] %s", exc.code, exc)
        return 2, None, None, {}
    _show_compile_warnings(built, args)
    bound_inputs = _bind_initial_inputs(built.program, args, resume_request, workspace) if reserved else _bind_recipe(built.program, resume_request, workspace)
    if getattr(args, "dry_run", False):
        if getattr(args, "terminal_lines", False):
            say(f"checked {built.program.tree['entry']}  {len(built.program.sites)} effect sites")
        return 0, None, None, {}

    state_manager = StateManager(
        workspace=workspace,
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
                result_root=workspace_relative_path(state_manager.workspace, state_manager.run_root),
            ) as authority:
                reporter = TerminalReporter(state_manager.run_id, state_manager.run_root,
                                            quiet=getattr(args, "quiet", False), state_dir=getattr(args, "state_dir", None),
                                            enabled=getattr(args, "terminal_lines", False))
                reporter.announce()
                exit_code, value = _execute_reported(
                    reporter, execute_pure_run, authority, bound_inputs,
                    spend_cap_usd=getattr(args, "max_cost_usd", None), run_id=state_manager.run_id, workspace=workspace, provider_io=built.provider_io,
                    stream_output=not getattr(args, "quiet", False))
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
    for name in ("entry_workflow", "boundary_admission_profile", "lint_profile", "workspace_root"):
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


def _execute_reported(reporter: TerminalReporter, execute, authority, inputs, *, stored_program=None,
                      spend_cap_usd=None, **kwargs):
    """Run `execute` with the reporter as memo observer and error sink; Ctrl-C also prints the resume line."""
    def on_error(exc: Exception) -> None:
        reporter.error(exc, header=authority.header, stored_program=stored_program, snapshot=_memo_or_none(authority))

    try:
        cut_off = None if spend_cap_usd is None else _pending_at_start(authority)
        exit_code, value = execute(replace(authority, observer=reporter.record, spend_cap_usd=spend_cap_usd,
                                           cut_off_attempts=cut_off), inputs, on_error=on_error, **kwargs)
    except KeyboardInterrupt:
        reporter.run_failed()
        raise
    _report_outcome(reporter, authority, exit_code, value)
    return exit_code, value


def _pending_at_start(authority) -> frozenset[str] | None:
    """The attempts a capped invocation finds pending before it runs (cut off); None when the memo cannot be read."""
    if not os.path.lexists(authority.memo_path):
        return frozenset()
    snapshot = _memo_or_none(authority)
    return None if snapshot is None else pending_attempts(snapshot)


def _memo_or_none(authority):
    """A read-only memo snapshot for recovery text, after the outcome is decided; None when it cannot be read."""
    try:
        return read_memo(authority.memo_path, site_classes(authority.program), run_files=authority.run_files)
    except Exception:
        return None


def _report_outcome(reporter: TerminalReporter, authority, exit_code: int, value: Any) -> None:
    """The resume line after a failure; the result, or the waiting line of a suspended run."""
    if exit_code != 0:
        if reporter.resumable(exit_code):
            reporter.run_failed()
        return
    snapshot = _memo_or_none(authority)
    if snapshot is not None and snapshot.terminal is None:
        reporter.waiting(snapshot.suspensions)
    else:
        reporter.result(value)


def _stored_context(exc, run_root, run_files) -> dict[str, Any]:
    """The recorded header, and for a program change the stored program, for the recovery lines.

    Read only after the refusal is decided, and never as authority: an unreadable header drops the
    commands that need it, and a stored program that does not match the header digest drops the diff.
    """
    from orchestrator.contracts.closed_program.program import ClosedProgram
    from orchestrator.workflow.evaluated.authority import PROGRAM_FILENAME, _read_file

    try:
        header = load_run_header(run_root, run_files=run_files)
    except Exception:  # any failure, a RecursionError included, only drops the commands that need the header
        return {}
    if getattr(exc, "code", None) != "resume_program_changed":
        return {"header": header}
    try:
        stored = ClosedProgram.from_artifact(_read_file(run_root / PROGRAM_FILENAME, run_files).decode("utf-8"))
    except Exception:  # a hostile artifact (deep nesting included) only drops the diff
        return {"header": header}
    return {"header": header, "stored_program": stored if stored.digest == header["program_digest"] else None}


def _show_compile_warnings(built, args) -> None:
    """`py run` shows its warnings at Python locations before it gets here."""
    if not getattr(args, "compile_warnings_shown", False):
        from orchestrator.cli.commands.python import _show_run_compile_warnings
        _show_run_compile_warnings(built.compile_diagnostics or (), args)


def _warn_changed_interpreters(authority):
    for pin in authority.header["interpreters"].values():
        diagnostic = check_command_interpreter(pin)
        if diagnostic:
            logger.warning("[%s] recorded interpreter bytes changed: %s", diagnostic, pin["path"])
