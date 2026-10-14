"""Workflow Lisp compile command."""

from __future__ import annotations

import json
import logging
from argparse import Namespace
from collections.abc import Mapping
from pathlib import Path

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    _cli_request_diagnostic,
)
from orchestrator.workflow_lisp.closed.artifact import (
    build_closed_program_bundle,
)
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.compile_diagnostics import (
    build_rejected_compile_diagnostics_document,
)
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    render_diagnostic,
)


logger = logging.getLogger(__name__)


def _print_machine_document(document: Mapping[str, object]) -> None:
    print(canonical_json_bytes(document).decode("utf-8"))


def _reject_machine_compile(
    diagnostics: tuple[LispFrontendDiagnostic, ...],
) -> int:
    _print_machine_document(
        build_rejected_compile_diagnostics_document(diagnostics)
    )
    return 2


def compile_workflow(args: Namespace) -> int:
    """Compile one `.orc` entrypoint into deterministic frontend artifacts."""

    machine_mode = bool(getattr(args, "diagnostics_json", False))
    workflow_path = Path(args.workflow).resolve()
    if workflow_path.suffix != ".orc":
        diagnostic = _cli_request_diagnostic(
            code="workflow_lisp_cli_input_unsupported",
            message="compile only supports .orc entrypoints",
            path=workflow_path,
        )
        if machine_mode:
            return _reject_machine_compile((diagnostic,))
        logger.error(render_diagnostic(diagnostic))
        return 2
    source_read_trace = SourceReadTrace()
    try:
        request = FrontendBuildRequest(
            source_path=workflow_path,
            source_roots=tuple(Path(path) for path in (args.source_root or ())),
            entry_workflow=args.entry_workflow,
            provider_externs_path=Path(args.provider_externs_file).resolve()
            if args.provider_externs_file else None,
            prompt_externs_path=Path(args.prompt_externs_file).resolve()
            if args.prompt_externs_file else None,
            imported_workflow_bundles_path=Path(args.imported_workflow_bundles_file).resolve()
            if args.imported_workflow_bundles_file else None,
            command_boundaries_path=Path(args.command_boundaries_file).resolve()
            if args.command_boundaries_file else None,
            workspace_root=Path.cwd(),
        )
        emit_flags = (
            ("emit_executable_ir", "--emit-executable-ir"),
            ("emit_core_ast", "--emit-core-ast"),
            ("emit_runtime_plan", "--emit-runtime-plan"),
            ("emit_semantic_ir", "--emit-semantic-ir"),
            ("emit_source_map", "--emit-source-map"),
            ("emit_debug_yaml", "--emit-debug-yaml"),
        )
        requested_flags = [
            flag for attribute, flag in emit_flags
            if getattr(args, attribute, None)
        ]
        if requested_flags:
            raise LispFrontendCompileError(
                (
                    _cli_request_diagnostic(
                        code="workflow_lisp_cli_input_unsupported",
                        message=f"{requested_flags[0]} is unavailable for evaluated-execution builds",
                        path=workflow_path,
                    ),
                )
            )
        closed_result = build_closed_program_bundle(
            request, source_read_trace=source_read_trace
        )
    except LispFrontendCompileError as exc:
        if machine_mode:
            return _reject_machine_compile(exc.diagnostics)
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2
    except (OSError, UnicodeError) as exc:
        if machine_mode:
            return _reject_machine_compile(
                (
                    _cli_request_diagnostic(
                        code="workflow_lisp_cli_io_error",
                        message=str(exc),
                        path=workflow_path,
                    ),
                )
            )
        logger.error(str(exc))
        return 2

    if machine_mode:
        _print_machine_document(
            {
                "status": "accepted",
                "program_digest": closed_result.program.digest,
                "build_key": closed_result.build_key,
            }
        )
    else:
        print(json.dumps(
            {
                "build_key": closed_result.build_key,
                "build_root": str(closed_result.build_root),
                "entry_workflow": closed_result.entry_workflow,
                "program_digest": closed_result.program.digest,
                "sites": len(closed_result.program.sites),
                "artifact_paths": {
                    "closed_program": str(closed_result.artifact_path),
                },
            },
            indent=2,
            sort_keys=True,
        ))
    return 0
