"""Workflow Lisp compile command."""

from __future__ import annotations

import json
import logging
from argparse import Namespace
from pathlib import Path

from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    _cli_request_diagnostic,
    build_frontend_bundle,
    emit_requested_frontend_artifact_exports,
    normalize_frontend_artifact_exports,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic
from orchestrator.workflow_lisp.wcc.route import lowering_route_for_schema


logger = logging.getLogger(__name__)


def compile_workflow(args: Namespace) -> int:
    """Compile one `.orc` entrypoint into deterministic frontend artifacts."""

    workflow_path = Path(args.workflow).resolve()
    if workflow_path.suffix != ".orc":
        logger.error(
            render_diagnostic(
                _cli_request_diagnostic(
                    code="workflow_lisp_cli_input_unsupported",
                    message="compile only supports .orc entrypoints",
                    path=workflow_path,
                )
            )
        )
        return 2
    try:
        export_requests = normalize_frontend_artifact_exports(
            {
                "executable_ir": list(getattr(args, "emit_executable_ir", ()) or ()),
                "core_workflow_ast": list(getattr(args, "emit_core_ast", ()) or ()),
                "runtime_plan": list(getattr(args, "emit_runtime_plan", ()) or ()),
                "semantic_ir": list(getattr(args, "emit_semantic_ir", ()) or ()),
                "source_map": list(getattr(args, "emit_source_map", ()) or ()),
                "expanded_debug_yaml": list(getattr(args, "emit_debug_yaml", ()) or ()),
            },
            cwd=Path.cwd(),
            source_path=workflow_path,
        )
        result = build_frontend_bundle(
            FrontendBuildRequest(
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
                emit_debug_yaml="expanded_debug_yaml" in export_requests,
                workspace_root=Path.cwd(),
            )
        )
        exported_artifacts = emit_requested_frontend_artifact_exports(
            result=result,
            export_requests=export_requests,
        )
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2
    except OSError as exc:
        logger.error(str(exc))
        return 2

    summary = {
        "fingerprint": result.manifest.fingerprint,
        "entry_workflow": result.selected_workflow_name,
        "build_root": str(result.build_root),
        "lowering_route": lowering_route_for_schema(result.manifest.lowering_schema_version).value,
        "lowering_schema_version": result.manifest.lowering_schema_version,
        "imported_bundle_keys": [
            binding.canonical_key
            for binding in result.imported_workflow_bundles
        ],
        "artifact_paths": {
            name: str(path)
            for name, path in sorted(result.artifact_paths.items())
        },
        "exported_artifacts": {
            name: str(path)
            for name, path in sorted(exported_artifacts.items())
        },
        "diagnostic_count": len(result.diagnostics),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0
