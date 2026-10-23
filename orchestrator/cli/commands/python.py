"""Public CLI for the Python authoring frontend."""
from __future__ import annotations

import json
import logging
from argparse import Namespace
from pathlib import Path

from orchestrator.py import PythonBuildResult, build, check
from orchestrator.py.diagnostics import PythonFrontendError
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    render_diagnostic,
)


logger = logging.getLogger(__name__)


def _frontend_result(args: Namespace, *, checking: bool) -> PythonBuildResult:
    operation = check if checking else build
    return operation(
        args.workflow,
        entry_workflow=args.entry_workflow,
        source_roots=tuple(args.source_root or ()),
        workspace_root=Path.cwd(),
        provider_externs_file=args.provider_externs_file,
        prompt_externs_file=args.prompt_externs_file,
        command_boundaries_file=args.command_boundaries_file,
        imported_workflow_bundles_file=args.imported_workflow_bundles_file,
        frozen=args.frozen,
    )


def _result_document(result: PythonBuildResult) -> dict[str, object]:
    return {
        "build_key": result.build_key,
        "entry_workflow": result.entry_workflow,
        "program_digest": result.program_digest,
        "source_path": str(result.source_path),
        "source_root": str(result.source_root),
        "source_map_path": str(result.source_map_path),
        "snapshot_path": str(result.snapshot_path),
        "artifact_paths": {"closed_program": str(result.artifact_path)},
    }


def _runtime_args(args: Namespace, result: PythonBuildResult) -> Namespace:
    request = result.request
    runtime_args = Namespace(**vars(args))
    runtime_args.workflow = str(request.source_path)
    runtime_args.entry_workflow = request.entry_workflow
    runtime_args.source_root = [str(path) for path in request.source_roots]
    runtime_args.provider_externs_file = (
        str(request.provider_externs_path) if request.provider_externs_path else None
    )
    runtime_args.prompt_externs_file = (
        str(request.prompt_externs_path) if request.prompt_externs_path else None
    )
    runtime_args.imported_workflow_bundles_file = (
        str(request.imported_workflow_bundles_path)
        if request.imported_workflow_bundles_path else None
    )
    runtime_args.command_boundaries_file = (
        str(request.command_boundaries_path) if request.command_boundaries_path else None
    )
    return runtime_args


def _show_run_compile_warnings(diagnostics, args: Namespace) -> None:
    if getattr(args, "debug", False):
        visible = True
    elif getattr(args, "quiet", False):
        visible = False
    elif getattr(args, "verbose", False):
        visible = True
    else:
        level_name = str(getattr(args, "log_level", "info")).upper()
        visible = getattr(logging, level_name, logging.INFO) <= logging.WARNING
    if visible:
        for diagnostic in diagnostics:
            logger.warning(render_diagnostic(diagnostic))


def python_workflow(args: Namespace) -> int:
    """Run one Python frontend command through ordinary build/run owners."""
    if getattr(args, "debug", False):
        logging.basicConfig(level=logging.DEBUG)
    try:
        result = _frontend_result(args, checking=args.py_command == "check")
        if args.py_command in {"build", "check"}:
            for diagnostic in result.compile_diagnostics:
                logger.warning(render_diagnostic(diagnostic))
            print(json.dumps(_result_document(result), indent=2, sort_keys=True))
            return 0

        _show_run_compile_warnings(result.compile_diagnostics, args)
        from orchestrator.cli.commands.run import run_workflow
        return run_workflow(_runtime_args(args, result)).exit_code
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        if getattr(args, "debug", False) and getattr(exc, "traceback", None):
            logger.debug("%s", exc.traceback)
        return 2
    except PythonFrontendError as exc:
        logger.error(str(exc))
        if getattr(args, "debug", False) and getattr(exc, "traceback", None):
            logger.debug("%s", exc.traceback)
        return 2
