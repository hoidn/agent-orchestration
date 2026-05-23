"""Workflow Lisp explain command."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from argparse import Namespace
from pathlib import Path

from orchestrator.workflow.core_ast import workflow_core_ast_to_json
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    _cli_request_diagnostic,
    _json_data,
    _origin_payload,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic
from orchestrator.workflow_lisp.lowering import LoweringOrigin


logger = logging.getLogger(__name__)


def explain_workflow(args: Namespace) -> int:
    """Explain typed/lowered/source-trace surfaces for one `.orc` form."""

    workflow_path = Path(args.workflow).resolve()
    if workflow_path.suffix != ".orc":
        logger.error(
            render_diagnostic(
                _cli_request_diagnostic(
                    code="workflow_lisp_cli_input_unsupported",
                    message="explain only supports .orc entrypoints",
                    path=workflow_path,
                )
            )
        )
        return 2
    try:
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
                workspace_root=Path.cwd(),
            )
        )
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2

    form_name = args.form or result.selected_workflow_name
    try:
        selection = _select_explain_subject(
            result,
            requested_form=form_name,
            source_path=workflow_path,
        )
    except LispFrontendCompileError as exc:
        for diagnostic in exc.diagnostics:
            logger.error(render_diagnostic(diagnostic))
        return 2
    manifest = result.manifest

    print(f"Form: {form_name}")
    print(f"Entry workflow: {result.selected_workflow_name}")
    print(f"Build root: {result.build_root}")
    imported_payload = selection.get("imported_target")
    if imported_payload is not None:
        print("Imported target:")
        print(json.dumps(_json_data(imported_payload), indent=2, sort_keys=True))
        print("")
    print("Expansion frames:")
    print(json.dumps(selection["expansion_frames"], indent=2, sort_keys=True))
    print("")
    print("Typed callable:")
    print(json.dumps(_json_data(selection["typed_payload"]), indent=2, sort_keys=True))
    print("")
    print("Lowered workflows:")
    print(json.dumps(selection["lowered_payload"], indent=2, sort_keys=True))
    print("")
    print("Executable nodes:")
    print(json.dumps(selection["executable_payload"], indent=2, sort_keys=True))
    print("")
    print("Core Workflow AST:")
    print(json.dumps(selection["core_ast_payload"], indent=2, sort_keys=True))
    print("")
    print("Semantic IR:")
    print(json.dumps(selection["semantic_ir_payload"], indent=2, sort_keys=True))
    print("")
    print("Source trace:")
    print(json.dumps(selection["source_trace_payload"], indent=2, sort_keys=True))
    print("")
    print(f"Manifest fingerprint: {manifest.fingerprint}")
    return 0


def _select_explain_subject(
    result: object,
    *,
    requested_form: str,
    source_path: Path,
) -> dict[str, object]:
    local_selection = _select_local_explain_workflow(result, requested_form=requested_form)
    if local_selection is not None:
        return local_selection

    procedure_selection = _select_local_explain_procedure(result, requested_form=requested_form)
    if procedure_selection is not None:
        return procedure_selection

    imported_selection = _select_imported_explain_target(result, requested_form=requested_form)
    if imported_selection is not None:
        return imported_selection

    raise LispFrontendCompileError(
        (
            _explain_request_diagnostic(
                code="explain_form_unknown",
                message=f"requested form `{requested_form}` does not match any compiled workflow",
                path=source_path,
            ),
        )
    )


def _select_local_explain_workflow(
    result: object,
    *,
    requested_form: str,
) -> dict[str, object] | None:
    exact_matches: list[tuple[str, object]] = []
    display_matches: list[tuple[str, object]] = []
    for module_name, compiled_result in sorted(result.compile_result.compiled_results_by_name.items()):
        for lowered in compiled_result.lowered_workflows:
            workflow_name = lowered.typed_workflow.definition.name
            display_name = workflow_name.split("::", 1)[-1]
            if workflow_name == requested_form:
                exact_matches.append((module_name, lowered))
            elif display_name == requested_form:
                display_matches.append((module_name, lowered))

    matches = exact_matches or display_matches
    if not matches:
        return None
    if len(matches) > 1:
        raise LispFrontendCompileError(
            (
                _explain_request_diagnostic(
                    code="explain_form_ambiguous",
                    message=f"requested form `{requested_form}` matches multiple compiled workflows; use the full workflow name",
                    path=Path(result.manifest.source_path),
                ),
            )
        )

    module_name, lowered = matches[0]
    workflow_name = lowered.typed_workflow.definition.name
    display_name = workflow_name.split("::", 1)[-1]
    bundle = result.compile_result.validated_bundles_by_name.get(workflow_name)
    origins = tuple(
        origin
        for origin in (
            lowered.origin_map.workflow_origin,
            *lowered.origin_map.step_spans.values(),
        )
        if isinstance(origin, LoweringOrigin)
    )
    return {
        "typed_payload": {
            "display_name": display_name,
            "workflow_name": workflow_name,
            "typed_workflow": _json_data(lowered.typed_workflow),
        },
        "expansion_frames": _collect_expansion_frames(origins),
        "lowered_payload": {
            "modules": {
                module_name: {
                    "workflows": [
                        {
                            "authored_mapping": _json_data(lowered.authored_mapping),
                            "display_name": display_name,
                            "step_ids": sorted(lowered.origin_map.step_spans),
                            "workflow_name": workflow_name,
                        }
                    ]
                }
            }
        },
        "executable_payload": {
            "workflows": {
                display_name: {
                    "workflow_name": workflow_name,
                    "node_ids": _workflow_executable_node_ids(bundle),
                }
            }
        },
        "core_ast_payload": _core_ast_payload(bundle, workflow_name),
        "semantic_ir_payload": _semantic_ir_payload(bundle, workflow_name),
        "source_trace_payload": {
            "workflows": {
                display_name: {
                    "generated_inputs": {
                        name: _origin_payload(origin)
                        for name, origin in sorted(lowered.origin_map.generated_input_spans.items())
                    },
                    "generated_outputs": {
                        name: _origin_payload(origin)
                        for name, origin in sorted(lowered.origin_map.generated_output_spans.items())
                    },
                    "generated_paths": {
                        name: _origin_payload(origin)
                        for name, origin in sorted(lowered.origin_map.generated_path_spans.items())
                    },
                    "expansion_frames": _collect_expansion_frames(origins),
                    "selected_entry_workflow": workflow_name == result.entry_selection.canonical_name,
                    "step_ids": {
                        step_id: _origin_payload(origin)
                        for step_id, origin in sorted(lowered.origin_map.step_spans.items())
                    },
                    "workflow_origin": _origin_payload(lowered.origin_map.workflow_origin),
                }
            }
        },
    }


def _select_local_explain_procedure(
    result: object,
    *,
    requested_form: str,
) -> dict[str, object] | None:
    exact_matches: list[tuple[str, object]] = []
    display_matches: list[tuple[str, object]] = []
    for module_name, compiled_result in sorted(result.compile_result.compiled_results_by_name.items()):
        for procedure in compiled_result.typed_procedures:
            procedure_name = procedure.definition.name
            display_name = procedure_name.split("::", 1)[-1]
            if procedure_name == requested_form:
                exact_matches.append((module_name, procedure))
            elif display_name == requested_form:
                display_matches.append((module_name, procedure))

    matches = exact_matches or display_matches
    if not matches:
        return None
    if len(matches) > 1:
        raise LispFrontendCompileError(
            (
                _explain_request_diagnostic(
                    code="explain_form_ambiguous",
                    message=(
                        f"requested form `{requested_form}` matches multiple compiled procedures; "
                        "use the full procedure name"
                    ),
                    path=Path(result.manifest.source_path),
                ),
            )
        )

    module_name, procedure = matches[0]
    procedure_name = procedure.definition.name
    display_name = procedure_name.split("::", 1)[-1]
    related_workflows = _collect_procedure_related_workflows(result, procedure=procedure)
    origins = tuple(
        origin
        for workflow in related_workflows.values()
        for origin in workflow["origins"]
    )

    return {
        "typed_payload": {
            "display_name": display_name,
            "generated_workflow_name": procedure.generated_workflow_name,
            "module_name": module_name,
            "procedure_name": procedure_name,
            "resolved_lowering_mode": getattr(procedure.resolved_lowering_mode, "value", None),
            "typed_procedure": _json_data(procedure),
        },
        "expansion_frames": _collect_expansion_frames(origins),
        "lowered_payload": {
            "workflows": {
                workflow_name: {
                    "display_name": workflow["display_name"],
                    "step_ids": sorted(workflow["step_ids"]),
                    "workflow_name": workflow_name,
                }
                for workflow_name, workflow in sorted(related_workflows.items())
            }
        },
        "executable_payload": {
            "workflows": {
                workflow_name: {
                    "display_name": workflow["display_name"],
                    "node_ids": workflow["node_ids"],
                    "workflow_name": workflow_name,
                }
                for workflow_name, workflow in sorted(related_workflows.items())
            }
        },
        "core_ast_payload": {
            "schema_version": "core_workflow_ast.v1",
            "workflows": {
                workflow_name: _core_ast_payload(
                    workflow["bundle"],
                    workflow_name,
                )["workflow"]
                for workflow_name, workflow in sorted(related_workflows.items())
            },
        },
        "semantic_ir_payload": {
            "schema_version": "workflow_semantic_ir.v1",
            "workflows": {
                workflow_name: _semantic_ir_payload(
                    workflow["bundle"],
                    workflow_name,
                )["workflow"]
                for workflow_name, workflow in sorted(related_workflows.items())
            },
        },
        "source_trace_payload": {
            "workflows": {
                workflow_name: {
                    "display_name": workflow["display_name"],
                    "expansion_frames": _collect_expansion_frames(workflow["origins"]),
                    "generated_inputs": workflow["generated_inputs"],
                    "generated_outputs": workflow["generated_outputs"],
                    "generated_paths": workflow["generated_paths"],
                    "selected_entry_workflow": workflow["selected_entry_workflow"],
                    "step_ids": workflow["step_ids"],
                    "workflow_origin": workflow["workflow_origin"],
                }
                for workflow_name, workflow in sorted(related_workflows.items())
            }
        },
    }


def _collect_procedure_related_workflows(
    result: object,
    *,
    procedure: object,
) -> dict[str, dict[str, object]]:
    related_workflows: dict[str, dict[str, object]] = {}
    for compiled_result in result.compile_result.compiled_results_by_name.values():
        for lowered in compiled_result.lowered_workflows:
            related_step_origins = {
                step_id: origin
                for step_id, origin in sorted(lowered.origin_map.step_spans.items())
                if _origin_matches_procedure(origin, procedure=procedure)
            }
            related_input_origins = {
                name: origin
                for name, origin in sorted(lowered.origin_map.generated_input_spans.items())
                if _origin_matches_procedure(origin, procedure=procedure)
            }
            related_output_origins = {
                name: origin
                for name, origin in sorted(lowered.origin_map.generated_output_spans.items())
                if _origin_matches_procedure(origin, procedure=procedure)
            }
            related_path_origins = {
                name: origin
                for name, origin in sorted(lowered.origin_map.generated_path_spans.items())
                if _origin_matches_procedure(origin, procedure=procedure)
            }
            workflow_origin = lowered.origin_map.workflow_origin
            workflow_origin_matches = _origin_matches_procedure(
                workflow_origin,
                procedure=procedure,
            )
            if not (
                related_step_origins
                or related_input_origins
                or related_output_origins
                or related_path_origins
                or workflow_origin_matches
            ):
                continue

            workflow_name = lowered.typed_workflow.definition.name
            display_name = workflow_name.split("::", 1)[-1]
            bundle = result.compile_result.validated_bundles_by_name.get(workflow_name)
            node_ids: list[str] = []
            seen_node_ids: set[str] = set()
            for step_id in related_step_origins:
                node_id = _resolve_executable_node_id(
                    bundle,
                    step_name=step_id,
                    lowered_step_id=step_id,
                    canonical_key=procedure.definition.name,
                )
                if isinstance(node_id, str) and node_id not in seen_node_ids:
                    seen_node_ids.add(node_id)
                    node_ids.append(node_id)
            if not node_ids and workflow_origin_matches:
                for node_id in _workflow_executable_node_ids(bundle):
                    if node_id not in seen_node_ids:
                        seen_node_ids.add(node_id)
                        node_ids.append(node_id)

            origins = [
                *related_step_origins.values(),
                *related_input_origins.values(),
                *related_output_origins.values(),
                *related_path_origins.values(),
            ]
            if workflow_origin_matches:
                origins.append(workflow_origin)

            related_workflows[workflow_name] = {
                "bundle": bundle,
                "display_name": display_name,
                "generated_inputs": {
                    name: _origin_payload(origin)
                    for name, origin in related_input_origins.items()
                },
                "generated_outputs": {
                    name: _origin_payload(origin)
                    for name, origin in related_output_origins.items()
                },
                "generated_paths": {
                    name: _origin_payload(origin)
                    for name, origin in related_path_origins.items()
                },
                "node_ids": node_ids,
                "origins": tuple(origins),
                "selected_entry_workflow": workflow_name == result.entry_selection.canonical_name,
                "step_ids": {
                    step_id: _origin_payload(origin)
                    for step_id, origin in related_step_origins.items()
                },
                "workflow_origin": _origin_payload(workflow_origin) if workflow_origin_matches else None,
            }
    return related_workflows


def _origin_matches_procedure(
    origin: object,
    *,
    procedure: object,
) -> bool:
    if not isinstance(origin, LoweringOrigin):
        return False
    procedure_start = procedure.definition.span.start
    if (
        origin.span.start.path == procedure_start.path
        and tuple(getattr(origin, "form_path", ()) or ()) == procedure.definition.form_path
    ):
        return True
    procedure_note = (
        f"procedure definition at {procedure_start.path}:"
        f"{procedure_start.line}:{procedure_start.column}"
    )
    return procedure_note in tuple(getattr(origin, "notes", ()) or ())


def _select_imported_explain_target(
    result: object,
    *,
    requested_form: str,
) -> dict[str, object] | None:
    exact_matches = [
        binding
        for binding in result.imported_workflow_bundles
        if binding.canonical_key == requested_form or binding.workflow_name == requested_form
    ]
    display_matches = [
        binding
        for binding in result.imported_workflow_bundles
        if isinstance(binding.workflow_name, str)
        and binding.workflow_name.split("::", 1)[-1] == requested_form
    ]
    matches = exact_matches or display_matches
    if not matches:
        return None
    if len(matches) > 1:
        raise LispFrontendCompileError(
            (
                _explain_request_diagnostic(
                    code="explain_form_ambiguous",
                    message=f"requested form `{requested_form}` matches multiple imported workflow targets; use the canonical imported key",
                    path=Path(result.manifest.source_path),
                ),
            )
        )

    binding = matches[0]
    call_sites = _collect_imported_call_sites(result, canonical_key=binding.canonical_key)
    call_site_origins = tuple(
        call_site["origin"]
        for call_site in call_sites
        if isinstance(call_site.get("origin"), LoweringOrigin)
    )
    imported_payload = {
        "bundle_fingerprint": binding.bundle_fingerprint,
        "bundle_kind": binding.bundle_kind,
        "canonical_key": binding.canonical_key,
        "frontend_kind": binding.bundle.provenance.frontend_kind,
        "load_status": binding.load_status,
        "source_root": str(binding.bundle.provenance.source_root),
        "workflow_name": binding.workflow_name,
        "workflow_path": str(binding.bundle.provenance.workflow_path),
    }
    return {
        "imported_target": imported_payload,
        "typed_payload": imported_payload,
        "expansion_frames": _collect_expansion_frames(call_site_origins),
        "lowered_payload": {
            "call_sites": [
                {
                    "canonical_key": binding.canonical_key,
                    "executable_node_id": call_site["executable_node_id"],
                    "lowered_step_id": call_site["lowered_step_id"],
                    "step_name": call_site["step_name"],
                    "workflow_name": call_site["workflow_name"],
                }
                for call_site in call_sites
            ]
        },
        "executable_payload": {
            "call_sites": [
                {
                    "canonical_key": binding.canonical_key,
                    "executable_node_id": call_site["executable_node_id"],
                    "step_name": call_site["step_name"],
                    "workflow_name": call_site["workflow_name"],
                }
                for call_site in call_sites
            ]
        },
        "core_ast_payload": _core_ast_payload(
            binding.bundle,
            binding.workflow_name or binding.bundle.surface.name or "",
        ),
        "semantic_ir_payload": _semantic_ir_payload(
            binding.bundle,
            binding.workflow_name or binding.bundle.surface.name or "",
        ),
        "source_trace_payload": {
            "call_sites": [
                {
                    "canonical_key": binding.canonical_key,
                    "origin": _origin_payload(call_site["origin"]),
                    "step_name": call_site["step_name"],
                    "workflow_name": call_site["workflow_name"],
                }
                for call_site in call_sites
                if isinstance(call_site.get("origin"), LoweringOrigin)
            ]
        },
    }


def _collect_imported_call_sites(
    result: object,
    *,
    canonical_key: str,
) -> list[dict[str, object]]:
    call_sites: list[dict[str, object]] = []
    for compiled_result in result.compile_result.compiled_results_by_name.values():
        for lowered in compiled_result.lowered_workflows:
            authored_steps = lowered.authored_mapping.get("steps")
            if not isinstance(authored_steps, list):
                continue
            validated_bundle = result.compile_result.validated_bundles_by_name.get(
                lowered.typed_workflow.definition.name
            )
            for step in authored_steps:
                if not isinstance(step, Mapping):
                    continue
                if step.get("call") != canonical_key:
                    continue
                step_name = step.get("name")
                lowered_step_id = step.get("id")
                origin = None
                if isinstance(step_name, str):
                    origin = lowered.origin_map.step_spans.get(step_name)
                if origin is None and isinstance(lowered_step_id, str):
                    origin = lowered.origin_map.step_spans.get(lowered_step_id)
                call_sites.append(
                    {
                        "executable_node_id": _resolve_executable_node_id(
                            validated_bundle,
                            step_name=step_name if isinstance(step_name, str) else None,
                            lowered_step_id=lowered_step_id if isinstance(lowered_step_id, str) else None,
                            canonical_key=canonical_key,
                        ),
                        "lowered_step_id": lowered_step_id,
                        "origin": origin,
                        "step_name": step_name,
                        "workflow_name": lowered.typed_workflow.definition.name,
                    }
                )
    return call_sites


def _resolve_executable_node_id(
    bundle: object,
    *,
    step_name: str | None,
    lowered_step_id: str | None,
    canonical_key: str,
) -> str | None:
    if bundle is None:
        return None
    for node_id in (*bundle.ir.body_region, *bundle.ir.finalization_region):
        node = bundle.ir.nodes.get(node_id)
        if getattr(node, "call_alias", None) == canonical_key:
            return node_id
        if isinstance(step_name, str) and getattr(node, "presentation_name", None) == step_name:
            return node_id
        if isinstance(lowered_step_id, str):
            candidate_step_id = getattr(node, "step_id", None)
            if candidate_step_id == lowered_step_id or candidate_step_id == f"root.{lowered_step_id}":
                return node_id
    return None


def _workflow_executable_node_ids(bundle: object) -> list[str]:
    if bundle is None:
        return []
    return list((*bundle.ir.body_region, *bundle.ir.finalization_region))


def _semantic_ir_payload(bundle: object | None, workflow_name: str) -> dict[str, object]:
    if bundle is None:
        return {
            "schema_version": None,
            "workflow_name": workflow_name,
            "workflow": None,
        }
    semantic_ir = getattr(bundle, "semantic_ir", None)
    if semantic_ir is None:
        return {
            "schema_version": None,
            "workflow_name": workflow_name,
            "workflow": None,
        }
    workflow = semantic_ir.workflows.get(workflow_name)
    return {
        "schema_version": semantic_ir.schema_version,
        "workflow_name": workflow_name,
        "workflow": _json_data(workflow),
    }


def _core_ast_payload(bundle: object | None, workflow_name: str) -> dict[str, object]:
    if bundle is None:
        return {
            "schema_version": None,
            "workflow_name": workflow_name,
            "workflow": None,
        }
    core_workflow_ast = getattr(bundle, "core_workflow_ast", None)
    if core_workflow_ast is None:
        return {
            "schema_version": None,
            "workflow_name": workflow_name,
            "workflow": None,
        }
    return {
        "schema_version": core_workflow_ast.schema_version,
        "workflow_name": workflow_name,
        "workflow": workflow_core_ast_to_json(core_workflow_ast),
    }


def _collect_expansion_frames(origins: Iterable[LoweringOrigin]) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    seen: set[str] = set()
    for origin in origins:
        for frame in getattr(origin, "expansion_stack", ()) or ():
            payload = _expansion_frame_payload(frame)
            marker = json.dumps(payload, sort_keys=True)
            if marker in seen:
                continue
            seen.add(marker)
            frames.append(payload)
    return frames


def _expansion_frame_payload(frame: object) -> dict[str, object]:
    span = getattr(frame, "span", None)
    if span is None:
        return {"frame": repr(frame)}
    form_path = getattr(frame, "form_path", ()) or ()
    return {
        "column": span.start.column,
        "form_path": list(form_path),
        "line": span.start.line,
        "path": span.start.path,
    }


def _explain_request_diagnostic(*, code: str, message: str, path: Path):
    return _cli_request_diagnostic(code=code, message=message, path=path)
