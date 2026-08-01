"""Workflow Lisp compile command."""

from __future__ import annotations

import json
import logging
from argparse import Namespace
from collections.abc import Mapping
from pathlib import Path

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
    compute_compiler_runtime_identity,
)
from orchestrator.workflow_lisp.build import (
    FrontendBuildResult,
    FrontendBuildRequest,
    _cli_request_diagnostic,
    _json_data,
    build_frontend_bundle,
    emit_requested_frontend_artifact_exports,
    normalize_frontend_artifact_exports,
)
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    build_compile_diagnostics_document,
    build_normalized_program_identity,
    render_diagnostic,
)
from orchestrator.workflow_lisp.wcc.route import lowering_route_for_schema


logger = logging.getLogger(__name__)


def _print_machine_document(document: Mapping[str, object]) -> None:
    print(canonical_json_bytes(document).decode("utf-8"))


def _reject_machine_compile(
    diagnostics: tuple[LispFrontendDiagnostic, ...],
) -> int:
    _print_machine_document(
        build_compile_diagnostics_document(
            status="rejected",
            diagnostics=diagnostics,
        )
    )
    return 2


def _selected_entry_document(result: FrontendBuildResult) -> dict[str, object]:
    canonical_name = result.entry_selection.canonical_name
    signatures = result.compile_result.entry_result.workflow_catalog.signatures_by_name
    signature = signatures.get(canonical_name)
    if signature is None:
        signature = signatures.get(result.entry_selection.selected_name)
    if signature is None:
        raise ValueError("selected workflow signature is missing")
    return {
        "selected_name": (
            result.entry_selection.requested_name
            or result.entry_selection.selected_name
        ),
        "canonical_name": canonical_name,
        "signature": {
            "parameters": [
                {
                    "name": name,
                    "type": type_ref.name,
                    "required": name not in signature.param_defaults,
                }
                for name, type_ref in signature.params
            ],
            "return_type": signature.return_type_ref.name,
            "input_contracts": {
                name: _json_data(contract.definition)
                for name, contract in sorted(
                    result.validated_bundle.surface.inputs.items()
                )
            },
            "output_contracts": {
                name: _json_data(contract.definition)
                for name, contract in sorted(
                    result.validated_bundle.surface.outputs.items()
                )
            },
        },
    }


def _module_source_revisions(
    result: FrontendBuildResult,
) -> list[dict[str, str]]:
    revisions_by_path = dict(result.source_read_trace.revision_vector)
    rows: list[dict[str, str]] = []
    for module_name, module_source in sorted(
        result.compile_result.graph.modules_by_name.items()
    ):
        revision = revisions_by_path.get(module_source.path)
        if revision is None:
            raise ValueError(
                f"source trace is missing compiled module `{module_name}`"
            )
        rows.append(
            {
                "module_name": module_name,
                "source_sha256": revision,
            }
        )
    return rows


def _configuration_identity(
    result: FrontendBuildResult,
) -> tuple[dict[str, str], list[dict[str, object]]]:
    revisions_by_path = dict(result.configuration_trace.revision_vector)
    request = result.resolved_request
    paths = {
        "provider_externs": request.provider_externs_path,
        "prompt_externs": request.prompt_externs_path,
        "command_boundaries": request.command_boundaries_path,
    }
    revisions: list[dict[str, object]] = []
    payload_digests: dict[str, str] = {}
    for role, path in paths.items():
        revision = None if path is None else revisions_by_path.get(path)
        if path is not None and revision is None:
            raise ValueError(f"configuration trace is missing `{role}`")
        revisions.append({"role": role, "source_sha256": revision})
        payload_digests[role] = (
            revision if revision is not None else canonical_sha256({})
        )
    return payload_digests, revisions


def _accepted_machine_document(
    result: FrontendBuildResult,
) -> dict[str, object]:
    selected_entry = _selected_entry_document(result)
    configuration_payload_digests, configuration_revisions = (
        _configuration_identity(result)
    )
    route = result.compile_request_capture.lowering_route.value
    program_identity = build_normalized_program_identity(
        compiler_runtime_identity=compute_compiler_runtime_identity().digest,
        module_source_revisions=_module_source_revisions(result),
        selected_entry=selected_entry,
        lowering_route=route,
        lowering_schema_version=result.manifest.lowering_schema_version,
        configuration_payload_digests=configuration_payload_digests,
        configuration_revisions=configuration_revisions,
    )
    return build_compile_diagnostics_document(
        status="accepted",
        diagnostics=result.diagnostics,
        selected_entry=selected_entry,
        normalized_program_identity=program_identity,
    )


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
        if machine_mode:
            return _reject_machine_compile(exc.diagnostics)
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2
    except OSError as exc:
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
        try:
            document = _accepted_machine_document(result)
        except (OSError, ValueError) as exc:
            return _reject_machine_compile(
                (
                    _cli_request_diagnostic(
                        code="workflow_lisp_compile_identity_invalid",
                        message=str(exc),
                        path=workflow_path,
                    ),
                )
            )
        _print_machine_document(document)
        return 0

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
