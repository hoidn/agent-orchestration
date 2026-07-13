"""Artifact fingerprinting, writing, and serialization for the Workflow Lisp build.

Extracted from build.py. Produces the on-disk build tree (frontend_ast.json,
runtime_plan.json, source_map.json, manifest.json, and the temporary G8 proof)
from already-computed payloads. Content-addressed fingerprints
and artifact bytes are byte-identical to the pre-split build.py.

May import build_manifest_io; must not import build.
Names that stay in build.py (e.g. `BUILD_SCHEMA_VERSION`, `_collect_materialize_view_effects`,
`_iter_surface_steps`) are pulled in via a deferred, function-body `from .build
import ...` to avoid an import-time cycle; type-only references to build.py
dataclasses use a `TYPE_CHECKING` guard instead.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from orchestrator.workflow.core_ast import workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_boundary_projection
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from .build_manifest_io import _json_data, _sha256_path
from .compiler import LinkedStage3CompileResult
from .debug_yaml import render_debug_yaml
from .diagnostics import LispFrontendDiagnostic, serialize_diagnostics
from .lexical_checkpoints import (
    CHECKPOINT_POINTS_SCHEMA_VERSION,
    CHECKPOINT_RECORD_SCHEMA_VERSION,
    CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION,
    canonical_json_dumps,
)
from .phase_family_boundary import is_structural_pure_projection_effect_summary
from .source_map import SOURCE_MAP_COVERAGE, SOURCE_MAP_SCHEMA_VERSION, build_source_map_document
from .workflows import prompt_extern_source_bindings_payload

if TYPE_CHECKING:
    from .build import (
        FrontendBuildManifest,
        FrontendBuildRequest,
        FrontendEntrySelection,
        ImportedWorkflowBundleBinding,
    )


def _fingerprint_build(
    *,
    request: FrontendBuildRequest,
    compile_result: LinkedStage3CompileResult,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    entry_selection: FrontendEntrySelection,
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundary_manifest: Mapping[str, object],
) -> str:
    from .build import BUILD_SCHEMA_VERSION

    source_payload = {
        "schema_version": BUILD_SCHEMA_VERSION,
        "source_files": {
            module_name: _sha256_path(module_source.path)
            for module_name, module_source in sorted(compile_result.graph.modules_by_name.items())
        },
        "source_roots": [str(path) for path in request.source_roots],
        "entry_workflow": entry_selection.canonical_name,
        "lowering_schema_version": compile_result.entry_result.lowering_schema_version,
        "provider_externs": dict(sorted(provider_externs.items())),
        "prompt_externs": prompt_extern_source_bindings_payload(prompt_externs),
        "command_boundaries": _json_data(dict(sorted(command_boundary_manifest.items()))),
        "imported_workflow_bundles": [
            {
                "canonical_key": binding.canonical_key,
                "manifest_entry_path": binding.manifest_entry_path,
                "resolved_bundle_path": str(binding.resolved_bundle_path),
                "bundle_kind": binding.bundle_kind,
                "bundle_fingerprint": binding.bundle_fingerprint,
            }
            for binding in imported_bindings
        ],
    }
    encoded = json.dumps(source_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _write_build_artifacts(
    *,
    build_root: Path,
    compile_result: LinkedStage3CompileResult,
    validated_bundle: LoadedWorkflowBundle,
    entry_selection: FrontendEntrySelection,
    diagnostics: tuple[LispFrontendDiagnostic, ...],
    emit_debug_yaml: bool,
    executable_ir_payload: Mapping[str, object] | None = None,
    semantic_ir_payload: Mapping[str, object] | None = None,
    source_map_payload: Mapping[str, object],
    workflow_boundary_projection_payload: Mapping[str, object],
    g8_deletion_evidence: Mapping[str, object] | None = None,
) -> Mapping[str, Path]:
    debug_yaml_path = build_root / "expanded.debug.yaml"
    artifact_paths = {
        "frontend_ast": build_root / "frontend_ast.json",
        "expanded_frontend_ast": build_root / "expanded_frontend_ast.json",
        "typed_frontend_ast": build_root / "typed_frontend_ast.json",
        "lowered_workflows": build_root / "lowered_workflows.json",
        "executable_ir": build_root / "executable_ir.json",
        "core_workflow_ast": build_root / "core_workflow_ast.json",
        "semantic_ir": build_root / "semantic_ir.json",
        "runtime_plan": build_root / "runtime_plan.json",
        "source_map": build_root / "source_map.json",
        "lexical_checkpoint_points": build_root / "lexical_checkpoint_points.json",
        "lexical_checkpoint_shadow_report": build_root / "lexical_checkpoint_shadow_report.json",
        "workflow_boundary_projection": build_root / "workflow_boundary_projection.json",
        "diagnostics": build_root / "diagnostics.json",
    }
    runtime_plan_payload = _public_runtime_plan_payload(validated_bundle.runtime_plan)
    if executable_ir_payload is None:
        executable_ir_payload = workflow_executable_ir_to_json(validated_bundle.ir)
    if semantic_ir_payload is None:
        semantic_ir_payload = workflow_semantic_ir_to_json(validated_bundle.semantic_ir)
    source_map_json = _json_data(source_map_payload)
    payloads = {
        "frontend_ast": _serialize_frontend_ast(compile_result),
        "expanded_frontend_ast": _serialize_expanded_frontend_ast(compile_result),
        "typed_frontend_ast": _serialize_typed_frontend_ast(compile_result),
        "lowered_workflows": _serialize_lowered_workflows(
            compile_result,
        ),
        "executable_ir": executable_ir_payload,
        "core_workflow_ast": workflow_core_ast_to_json(validated_bundle.core_workflow_ast),
        "semantic_ir": semantic_ir_payload,
        "runtime_plan": runtime_plan_payload,
        "source_map": source_map_json,
        "lexical_checkpoint_points": _serialize_lexical_checkpoint_points(
            validated_bundle,
            runtime_plan_payload=runtime_plan_payload,
            semantic_ir_payload=semantic_ir_payload,
        ),
        "lexical_checkpoint_shadow_report": _serialize_lexical_checkpoint_shadow_report(
            validated_bundle,
            semantic_ir_payload=semantic_ir_payload,
            runtime_plan_payload=runtime_plan_payload,
            source_map_payload=source_map_json,
        ),
        "workflow_boundary_projection": _json_data(workflow_boundary_projection_payload),
        "diagnostics": serialize_diagnostics(diagnostics),
    }
    if g8_deletion_evidence is not None:
        artifact_paths["g8_deletion_evidence"] = build_root / "g8_deletion_evidence.json"
        payloads["g8_deletion_evidence"] = _json_data(g8_deletion_evidence)
    for name, path in artifact_paths.items():
        path.write_text(json.dumps(payloads[name], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if emit_debug_yaml:
        debug_yaml_path.write_text(
            render_debug_yaml(
                validated_bundle,
                source_trace_path=artifact_paths["source_map"],
            ),
            encoding="utf-8",
        )
        artifact_paths["expanded_debug_yaml"] = debug_yaml_path
    elif debug_yaml_path.exists():
        debug_yaml_path.unlink()
    return artifact_paths


def _public_runtime_plan_payload(
    runtime_plan: Any,
) -> Mapping[str, Any]:
    """Serialize runtime-plan build output without private checkpoint identity."""

    payload = _json_data(runtime_plan)
    lexical_points = payload.get("lexical_checkpoint_points")
    if isinstance(lexical_points, list):
        sanitized_points: list[Any] = []
        for point in lexical_points:
            if not isinstance(point, Mapping):
                sanitized_points.append(point)
                continue
            details = point.get("details")
            if not isinstance(details, Mapping):
                sanitized_points.append(point)
                continue
            sanitized_points.append(
                {
                    **point,
                    "details": {
                        str(key): value
                        for key, value in details.items()
                        if key != "runtime_program_identity"
                    },
                }
            )
        payload = {
            **payload,
            "lexical_checkpoint_points": sanitized_points,
        }

    return payload


def _build_manifest(
    *,
    request: FrontendBuildRequest,
    compile_result: LinkedStage3CompileResult,
    entry_selection: FrontendEntrySelection,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    artifact_paths: Mapping[str, Path],
    fingerprint: str,
    diagnostics: tuple[LispFrontendDiagnostic, ...],
    build_root: Path,
    emit_debug_yaml: bool,
) -> FrontendBuildManifest:
    from .build import BUILD_SCHEMA_VERSION, FrontendBuildManifest

    return FrontendBuildManifest(
        schema_version=BUILD_SCHEMA_VERSION,
        fingerprint=fingerprint,
        source_path=str(request.source_path),
        source_sha256=_sha256_path(request.source_path),
        source_roots=tuple(str(path) for path in request.source_roots),
        entry_module=compile_result.graph.entry_module_name,
        entry_workflow=entry_selection.canonical_name,
        imported_workflow_bundle_manifest_path=(
            str(request.imported_workflow_bundles_path)
            if request.imported_workflow_bundles_path is not None
            else None
        ),
        imported_workflow_bundles=tuple(
            {
                "canonical_key": binding.canonical_key,
                "manifest_entry_path": binding.manifest_entry_path,
                "resolved_bundle_path": str(binding.resolved_bundle_path),
                "resolved_workflow_name": binding.workflow_name,
                "bundle_kind": binding.bundle_kind,
                "bundle_fingerprint": binding.bundle_fingerprint,
                "load_status": binding.load_status,
            }
            for binding in imported_bindings
        ),
        compiled_module_names=tuple(sorted(compile_result.compiled_results_by_name)),
        validated_bundle_names=tuple(sorted(compile_result.validated_bundles_by_name)),
        artifact_paths={
            name: str(path.relative_to(build_root.parent.parent))
            for name, path in artifact_paths.items()
        },
        artifact_status={
            **{name: "emitted" for name in artifact_paths},
            "executable_ir": "emitted",
            "core_workflow_ast": "emitted",
            "runtime_plan": "emitted",
            "semantic_ir": "emitted",
        },
        diagnostic_count=len(diagnostics),
        shared_validation_status="validated",
        debug_yaml_status="emitted" if emit_debug_yaml else "not_requested",
        source_map_schema_version=SOURCE_MAP_SCHEMA_VERSION,
        source_map_coverage=dict(SOURCE_MAP_COVERAGE),
        lowering_schema_version=compile_result.entry_result.lowering_schema_version,
    )


def _collect_origin_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "origin_key" and isinstance(item, str):
                keys.add(item)
            keys.update(_collect_origin_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_origin_keys(item))
    return keys


def _checkpoint_program_identity(
    validated_bundle: LoadedWorkflowBundle,
    *,
    runtime_plan_payload: Mapping[str, Any],
    semantic_ir_payload: Mapping[str, Any],
) -> dict[str, str]:
    workflow_path = validated_bundle.provenance.workflow_path
    source_module_digest = f"sha256:{hashlib.sha256(workflow_path.read_bytes()).hexdigest()}"
    return {
        "source_module_digest": source_module_digest,
        "executable_ir_digest": f"sha256:{hashlib.sha256(canonical_json_dumps(runtime_plan_payload).encode('utf-8')).hexdigest()}",
        "semantic_ir_digest": f"sha256:{hashlib.sha256(canonical_json_dumps(semantic_ir_payload).encode('utf-8')).hexdigest()}",
    }


def _serialize_lexical_checkpoint_points(
    validated_bundle: LoadedWorkflowBundle,
    *,
    runtime_plan_payload: Mapping[str, Any],
    semantic_ir_payload: Mapping[str, Any],
) -> dict[str, object]:
    from orchestrator.workflow_lisp.lexical_checkpoint_restore import public_restore_metadata

    points = [
        {
            "checkpoint_id": point.checkpoint_id,
            "program_point_id": point.program_point_id,
            "point_kind": point.point_kind,
            "workflow_name": point.workflow_name,
            "wcc_identity": point.details.get("wcc_identity"),
            "executable_identity": {
                "node_id": point.node_id,
                "step_id": point.step_id,
                "presentation_key": point.presentation_key,
            },
            "source_lineage": {
                "origin_key": point.origin_key,
            },
            "binding_schema": point.details.get("binding_schema"),
            "storage": point.details.get("storage"),
            "effect_boundary": point.details.get("effect_boundary"),
            "loop_back_edge": point.details.get("loop_back_edge"),
            "restore": public_restore_metadata(point.details.get("restore", {})),
        }
        for point in validated_bundle.runtime_plan.lexical_checkpoint_points
    ]
    return {
        "schema_version": CHECKPOINT_POINTS_SCHEMA_VERSION,
        "workflow_name": validated_bundle.surface.name,
        "checkpoint_schema_version": CHECKPOINT_RECORD_SCHEMA_VERSION,
        "program_identity": _checkpoint_program_identity(
            validated_bundle,
            runtime_plan_payload=runtime_plan_payload,
            semantic_ir_payload=semantic_ir_payload,
        ),
        "points": points,
    }


def _validate_lexical_checkpoint_artifacts(
    points_payload: Mapping[str, Any],
    *,
    validated_bundle: LoadedWorkflowBundle | None = None,
    semantic_ir_payload: Mapping[str, Any],
    runtime_plan_payload: Mapping[str, Any],
    source_map_payload: Mapping[str, Any],
) -> None:
    from orchestrator.workflow_lisp.lexical_checkpoint_effect_policies import validate_effect_boundary_payload

    if points_payload.get("schema_version") != CHECKPOINT_POINTS_SCHEMA_VERSION:
        raise ValueError("lexical checkpoint points schema mismatch")
    if points_payload.get("checkpoint_schema_version") != CHECKPOINT_RECORD_SCHEMA_VERSION:
        raise ValueError("lexical checkpoint points checkpoint schema mismatch")
    runtime_node_ids = set(runtime_plan_payload.get("nodes", {}))
    origin_keys = _collect_origin_keys(source_map_payload) | _collect_origin_keys(semantic_ir_payload)
    program_identity = dict(points_payload.get("program_identity", {}))
    expected_runtime_program_identity = {
        "executable_ir_digest": f"sha256:{hashlib.sha256(canonical_json_dumps(runtime_plan_payload).encode('utf-8')).hexdigest()}",
        "semantic_ir_digest": f"sha256:{hashlib.sha256(canonical_json_dumps(semantic_ir_payload).encode('utf-8')).hexdigest()}",
    }
    for key, expected_value in expected_runtime_program_identity.items():
        if program_identity.get(key) != expected_value:
            raise ValueError("lexical checkpoint program identity drift")
    if validated_bundle is not None:
        expected_program_identity = _checkpoint_program_identity(
            validated_bundle,
            runtime_plan_payload=runtime_plan_payload,
            semantic_ir_payload=semantic_ir_payload,
        )
        if program_identity.get("source_module_digest") != expected_program_identity["source_module_digest"]:
            raise ValueError("lexical checkpoint program identity drift")
    for point in points_payload.get("points", []):
        if not isinstance(point.get("wcc_identity", {}), Mapping):
            raise ValueError("lexical checkpoint point missing WCC identity")
        if not point.get("binding_schema", {}).get("schema_digest"):
            raise ValueError("lexical checkpoint point missing binding schema digest")
        if not point.get("storage", {}).get("allocation_id"):
            raise ValueError("lexical checkpoint point missing storage allocation")
        if point.get("executable_identity", {}).get("node_id") not in runtime_node_ids:
            raise ValueError("lexical checkpoint point missing executable node linkage")
        if point.get("source_lineage", {}).get("origin_key") not in origin_keys:
            raise ValueError("lexical checkpoint point missing source-map origin coverage")
        if point.get("point_kind") == "effect_boundary":
            validate_effect_boundary_payload(
                dict(point.get("effect_boundary", {})),
                expected_origin_key=str(point.get("source_lineage", {}).get("origin_key") or ""),
            )


def _serialize_lexical_checkpoint_shadow_report(
    validated_bundle: LoadedWorkflowBundle,
    *,
    semantic_ir_payload: Mapping[str, Any],
    runtime_plan_payload: Mapping[str, Any],
    source_map_payload: Mapping[str, Any],
) -> dict[str, object]:
    points_payload = _serialize_lexical_checkpoint_points(
        validated_bundle,
        runtime_plan_payload=runtime_plan_payload,
        semantic_ir_payload=semantic_ir_payload,
    )
    _validate_lexical_checkpoint_artifacts(
        points_payload,
        validated_bundle=validated_bundle,
        semantic_ir_payload=semantic_ir_payload,
        runtime_plan_payload=runtime_plan_payload,
        source_map_payload=source_map_payload,
    )
    return {
        "schema_version": CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION,
        "workflow_name": validated_bundle.surface.name,
        "status": "pass",
        "checked_points": len(points_payload["points"]),
        "checked_records": 0,
        "missing_points": [],
        "invalid_records": [],
        "stale_records": [],
        "diagnostics": [],
    }


def _serialize_frontend_ast(compile_result: LinkedStage3CompileResult) -> dict[str, object]:
    return {
        "entry_module": compile_result.graph.entry_module_name,
        "modules": {
            module_name: _json_data(module_source.syntax_module)
            for module_name, module_source in sorted(compile_result.graph.modules_by_name.items())
        },
    }


def _serialize_expanded_frontend_ast(compile_result: LinkedStage3CompileResult) -> dict[str, object]:
    return {
        "modules": {
            module_name: {
                "definitions": _json_data(compiled_result.module),
                "typed_workflow_names": [
                    workflow.definition.name
                    for workflow in compiled_result.typed_workflows
                ],
                "typed_procedure_names": [
                    procedure.definition.name
                    for procedure in compiled_result.typed_procedures
                ],
            }
            for module_name, compiled_result in sorted(compile_result.compiled_results_by_name.items())
        }
    }


def _serialize_typed_frontend_ast(compile_result: LinkedStage3CompileResult) -> dict[str, object]:
    return {
        "modules": {
            module_name: {
                "typed_workflows": _json_data(compiled_result.typed_workflows),
                "typed_procedures": _json_data(compiled_result.typed_procedures),
                "workflow_catalog": {
                    "signatures": sorted(compiled_result.workflow_catalog.signatures_by_name),
                },
            }
            for module_name, compiled_result in sorted(compile_result.compiled_results_by_name.items())
        }
    }


def _serialize_lowered_workflows(
    compile_result: LinkedStage3CompileResult,
) -> dict[str, object]:
    return {
        "modules": {
            module_name: {
                "workflows": [
                    {
                        "workflow_name": lowered.typed_workflow.definition.name,
                        "display_name": _display_workflow_name(lowered.typed_workflow.definition.name),
                        "authored_mapping": _json_data(lowered.authored_mapping),
                        "step_ids": sorted(lowered.origin_map.step_spans),
                    }
                    for lowered in compiled_result.lowered_workflows
                ],
            }
            for module_name, compiled_result in sorted(compile_result.compiled_results_by_name.items())
        }
    }


def _serialize_source_map(
    compile_result: LinkedStage3CompileResult,
    *,
    selected_name: str,
) -> dict[str, object]:
    return _json_data(
        build_source_map_document(
            compile_result,
            selected_name=selected_name,
            display_name_resolver=_display_workflow_name,
        )
    )


def _serialize_workflow_boundary_projection(
    compile_result: LinkedStage3CompileResult,
    *,
    selected_name: str,
) -> dict[str, object]:
    workflows: list[dict[str, object]] = []
    for compiled_result in compile_result.compiled_results_by_name.values():
        for lowered in compiled_result.lowered_workflows:
            projection = lowered.boundary_projection
            allocation_by_input_name: dict[str, object] = {}
            for allocation in lowered.generated_path_allocations:
                if not isinstance(allocation.generated_input_name, str):
                    continue
                current = allocation_by_input_name.get(allocation.generated_input_name)
                if current is None:
                    allocation_by_input_name[allocation.generated_input_name] = allocation
                    continue
                if (
                    getattr(current, "semantic_role", None)
                    == GeneratedPathSemanticRole.ENTRYPOINT_MANAGED_WRITE_ROOT
                    and allocation.semantic_role
                    != GeneratedPathSemanticRole.ENTRYPOINT_MANAGED_WRITE_ROOT
                ):
                    allocation_by_input_name[allocation.generated_input_name] = allocation
            bundle = compile_result.validated_bundles_by_name.get(
                lowered.typed_workflow.definition.name
            )
            if bundle is not None:
                boundary = workflow_boundary_projection(bundle)
                private_compatibility_bridge_inputs = sorted(
                    name
                    for name in lowered.compatibility_bridge_inputs
                    if isinstance(name, str)
                )
                private_runtime_context_input_names = {
                    generated_name
                    for binding in boundary.private_runtime_context_bindings
                    for generated_name in binding.generated_input_names
                    if isinstance(generated_name, str)
                }
                public_input_names = sorted(
                    name
                    for name in bundle.surface.inputs
                    if isinstance(name, str)
                    and name not in bundle.provenance.runtime_context_inputs
                    and name not in bundle.provenance.managed_write_root_inputs
                    and name not in private_runtime_context_input_names
                    and name not in private_compatibility_bridge_inputs
                )
                boundary_payload = {
                    "public_input_names": public_input_names,
                    "private_runtime_context_bindings": [
                        {
                            "binding_id": binding.binding_id,
                            "source_param_name": binding.source_param_name,
                            "context_family": binding.context_family,
                            "bridge_class": binding.bridge_class,
                            "derived_phase_identity": binding.derived_phase_identity,
                            "generated_input_names": sorted(binding.generated_input_names),
                            "projection_hints": _json_data(binding.projection_hints),
                            "source_provenance": _json_data(binding.source_provenance),
                        }
                        for binding in boundary.private_runtime_context_bindings
                    ],
                    "private_managed_write_root_inputs": sorted(
                        name
                        for name in boundary.private_managed_write_root_inputs
                        if isinstance(name, str)
                    ),
                    "private_compatibility_bridge_inputs": private_compatibility_bridge_inputs,
                    "pure_projection_classification": {
                        "structural": is_structural_pure_projection_effect_summary(
                            lowered.typed_workflow.effect_summary
                        )
                    },
                }
            else:
                boundary_payload = {
                    "public_input_names": sorted(
                        field.generated_name
                        for field in projection.flattened_inputs
                        if field.generated_name
                        not in {
                            internal.generated_name
                            for internal in projection.generated_internal_inputs
                        }
                    ),
                    "private_runtime_context_bindings": [
                        {
                            "binding_id": binding.binding_id,
                            "source_param_name": binding.source_param_name,
                            "context_family": binding.context_family,
                            "bridge_class": binding.bridge_class,
                            "derived_phase_identity": binding.derived_phase_identity,
                            "generated_input_names": sorted(binding.generated_input_names),
                            "projection_hints": _json_data(binding.projection_hints),
                            "source_provenance": _json_data(binding.source_provenance),
                        }
                        for binding in lowered.private_exec_context_bindings
                    ],
                    "private_managed_write_root_inputs": sorted(
                        field.generated_name
                        for field in projection.generated_internal_inputs
                        if field.reason == "managed_write_root"
                    ),
                    "private_compatibility_bridge_inputs": sorted(
                        name
                        for name in lowered.compatibility_bridge_inputs
                        if isinstance(name, str)
                    ),
                    "pure_projection_classification": {
                        "structural": is_structural_pure_projection_effect_summary(
                            lowered.typed_workflow.effect_summary
                        )
                    },
                }
            workflows.append(
                {
                    "workflow_name": projection.workflow_name,
                    "display_name": projection.display_name,
                    "boundary": boundary_payload,
                    "params": [
                        {"name": param.name, "type_kind": param.type_kind}
                        for param in projection.params
                    ],
                    "return_kind": projection.return_kind,
                    "flattened_inputs": [
                        {
                            "generated_name": field.generated_name,
                            "source_path": list(field.source_path),
                            "contract_definition": _json_data(field.contract_definition),
                        }
                        for field in sorted(projection.flattened_inputs, key=lambda field: field.generated_name)
                    ],
                    "flattened_outputs": [
                        {
                            "generated_name": field.generated_name,
                            "source_path": list(field.source_path),
                            "contract_definition": _json_data(field.contract_definition),
                            **(
                                {
                                    "projection": _json_data(output_definition.get("projection"))
                                }
                                if isinstance(
                                    (lowered.authored_mapping.get("outputs", {}) or {}).get(field.generated_name),
                                    Mapping,
                                )
                                and isinstance(
                                    (
                                        (lowered.authored_mapping.get("outputs", {}) or {}).get(field.generated_name)
                                    ).get("projection"),
                                    Mapping,
                                )
                                else {}
                            ),
                        }
                        for field in sorted(projection.flattened_outputs, key=lambda field: field.generated_name)
                        for output_definition in [
                            (lowered.authored_mapping.get("outputs", {}) or {}).get(field.generated_name, {})
                        ]
                    ],
                    "generated_internal_inputs": [
                        {
                            "generated_name": field.generated_name,
                            "reason": field.reason,
                            "allocation_id": (
                                allocation_by_input_name[field.generated_name].allocation_id
                                if field.generated_name in allocation_by_input_name
                                else None
                            ),
                            "semantic_role": (
                                allocation_by_input_name[field.generated_name].semantic_role.value
                                if field.generated_name in allocation_by_input_name
                                else None
                            ),
                        }
                        for field in sorted(
                            projection.generated_internal_inputs,
                            key=lambda field: field.generated_name,
                        )
                    ],
                    "generated_path_allocations": [
                        {
                            "allocation_id": allocation.allocation_id,
                            "semantic_role": allocation.semantic_role.value,
                            "privacy": allocation.privacy.value,
                            "resume_scope": allocation.resume_scope.value,
                            "stable_identity": allocation.stable_identity,
                            "concrete_path_template": allocation.concrete_path_template,
                            "generated_input_name": allocation.generated_input_name,
                            "path_safety_policy": allocation.path_safety_policy,
                        }
                        for allocation in lowered.generated_path_allocations
                    ],
                }
            )
    workflows.sort(key=lambda workflow: str(workflow["workflow_name"]))
    return {
        "schema_version": "workflow_lisp_boundary_projection.v1",
        "entry_workflow": selected_name,
        "workflows": workflows,
    }


def _origin_payload(origin: object) -> dict[str, object]:
    span = getattr(origin, "span")
    return {
        "origin_key": getattr(origin, "origin_key", ""),
        "path": span.start.path,
        "line": span.start.line,
        "column": span.start.column,
        "form_path": list(getattr(origin, "form_path", ()) or ()),
        "notes": list(getattr(origin, "notes", ()) or ()),
    }


def _display_workflow_name(name: str) -> str:
    return name.split("::", 1)[-1]


def _command_boundary_metadata_for_workflow(
    source_map_payload: Mapping[str, object],
    *,
    workflow_name: str,
) -> Mapping[str, tuple[str, str]]:
    workflows = source_map_payload.get("workflows")
    if not isinstance(workflows, Mapping):
        return {}
    workflow_payload = workflows.get(workflow_name)
    if not isinstance(workflow_payload, Mapping):
        return {}
    command_boundaries = workflow_payload.get("command_boundaries")
    if not isinstance(command_boundaries, list):
        return {}
    metadata: dict[str, tuple[str, str]] = {}
    for boundary in command_boundaries:
        if not isinstance(boundary, Mapping):
            continue
        step_id = boundary.get("step_id")
        boundary_kind = boundary.get("boundary_kind")
        boundary_name = boundary.get("adapter_name") or boundary.get("command_name")
        if (
            isinstance(step_id, str)
            and step_id
            and isinstance(boundary_kind, str)
            and boundary_kind
            and isinstance(boundary_name, str)
            and boundary_name
        ):
            metadata[step_id] = (boundary_kind, boundary_name)
            if not step_id.startswith("root."):
                metadata[f"root.{step_id}"] = (boundary_kind, boundary_name)
    return metadata
