"""Artifact fingerprinting, writing, and serialization for the Workflow Lisp build.

Extracted from build.py. Produces the on-disk build tree (frontend_ast.json,
runtime_plan.json, source_map.json, manifest.json, and the optional design-delta
report artifacts) from already-computed payloads. Content-addressed fingerprints
and artifact bytes are byte-identical to the pre-split build.py.

May import build_manifest_io and build_design_delta; must not import build.
Names that stay in build.py (e.g. `BUILD_SCHEMA_VERSION`, `_collect_materialize_view_effects`,
`_iter_surface_steps`) are pulled in via a deferred, function-body `from .build
import ...` to avoid an import-time cycle; type-only references to build.py
dataclasses use a `TYPE_CHECKING` guard instead.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from orchestrator.workflow.core_ast import workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_boundary_projection
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from .build_manifest_io import _cli_request_diagnostic, _json_data, _sha256_path
from .build_design_delta import (
    DesignDeltaReportPayloads,
    _boundary_authority_registry_provenance,
    _consumer_rendering_census_provenance,
    _family_profile_metadata_for_entry,
    _observability_old_writer_pair_provenance,
    _value_flow_census_provenance,
)
from .compiler import LinkedStage3CompileResult
from .debug_yaml import render_debug_yaml
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic, serialize_diagnostics
from .entry_publication import (
    compatibility_reason_for_selected_row,
    select_entry_publication_rows,
    serialize_entry_publication_policy,
    serialize_entry_publication_report,
)
from .family_profiles import WorkflowFamilyProfileCatalog
from .lexical_checkpoints import (
    CHECKPOINT_POINTS_SCHEMA_VERSION,
    CHECKPOINT_RECORD_SCHEMA_VERSION,
    CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION,
    canonical_json_dumps,
)
from .phase_family_boundary import (
    checked_design_delta_public_input_names,
    is_structural_pure_projection_effect_summary,
    is_design_delta_parent_drain_target_workflow,
)
from .source_map import SOURCE_MAP_COVERAGE, SOURCE_MAP_SCHEMA_VERSION, build_source_map_document
from .type_env import UnionTypeRef
from .workflows import prompt_extern_source_bindings_payload

if TYPE_CHECKING:
    from .build import (
        FrontendBuildManifest,
        FrontendBuildRequest,
        FrontendEntrySelection,
        ImportedWorkflowBundleBinding,
    )


def _build_entry_publication_report(
    *,
    compile_result: LinkedStage3CompileResult,
    entry_workflow_name: str,
    workflow_boundary_projection_payload: Mapping[str, object],
    source_map_payload: Mapping[str, object],
    consumer_rendering_census: Mapping[str, object],
) -> Mapping[str, object]:
    # `_collect_entry_publication_lowerings` is defined below in this module,
    # but is imported back from `.build` (its re-export) rather than called
    # as a bare name so that tests monkeypatching `build.<name>` (as they did
    # when both functions lived in build.py) still observe the patch.
    from .build import _collect_entry_publication_lowerings, _collect_materialize_view_effects

    target_family = str(consumer_rendering_census.get("target_family", ""))
    typed_workflows_by_name = {
        workflow.definition.name: workflow
        for compiled_result in compile_result.compiled_results_by_name.values()
        for workflow in compiled_result.typed_workflows
    }
    entry_workflow = typed_workflows_by_name.get(entry_workflow_name)
    selected_rows = select_entry_publication_rows(consumer_rendering_census)
    compatibility_reasons: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    lowered_publications = _collect_entry_publication_lowerings(
        compile_result,
        source_map_payload=source_map_payload,
    )
    materialize_view_effects = _collect_materialize_view_effects(
        compile_result.validated_bundles_by_name
    )
    materialize_view_workflows = {
        str(effect.get("workflow_surface", ""))
        for effect in materialize_view_effects
        if isinstance(effect.get("workflow_surface"), str)
        and str(effect.get("authority_class", "materialized_view"))
        == "materialized_view"
    }
    published_variants: set[str] = set()
    policy_rows = ()
    if entry_workflow is not None and entry_workflow.definition.publication_policy is not None:
        policy_rows = entry_workflow.definition.publication_policy.rows
        published_variants = {row.variant for row in policy_rows}
    for row in selected_rows:
        workflow_surface = row.get("workflow_surface")
        workflow_name = workflow_surface if isinstance(workflow_surface, str) else None
        typed_workflow = (
            typed_workflows_by_name.get(workflow_name) if workflow_name is not None else None
        )
        return_kind = None
        if typed_workflow is not None and isinstance(
            typed_workflow.signature.return_type_ref, UnionTypeRef
        ):
            return_kind = "union"
        elif typed_workflow is not None:
            return_kind = "non_union"
        row_variant = row.get("variant")
        row_is_legal_entry_candidate = (
            workflow_name == entry_workflow_name
            and return_kind == "union"
            and row.get("typed_value_surface") == "terminal_result_variant"
            and row.get("value_kind") == "union_variant"
            and isinstance(row_variant, str)
        )
        if row_is_legal_entry_candidate and row_variant not in published_variants:
            diagnostics.append(
                {
                    "code": "entry_publication_c0_row_missing",
                    "row_id": str(row.get("row_id", "")),
                    "u0_row_id": str(row.get("u0_row_id", "")),
                    "workflow_name": workflow_name,
                    "variant": row_variant,
                    "message": (
                        "selected C0 entry-publication row is legal for C3 but has no "
                        "matching `:publish` policy row"
                    ),
                }
            )
            continue
        if row_is_legal_entry_candidate:
            continue
        if (
            workflow_name is not None
            and workflow_name != entry_workflow_name
            and workflow_name in materialize_view_workflows
        ):
            diagnostics.append(
                {
                    "code": "interior_publication",
                    "row_id": str(row.get("row_id", "")),
                    "u0_row_id": str(row.get("u0_row_id", "")),
                    "workflow_name": workflow_name,
                    "message": (
                        "selected non-entry C3 candidate still lowers authored "
                        "body-level materialize_view effects"
                    ),
                }
            )
        compatibility_reasons.append(
            compatibility_reason_for_selected_row(
                row,
                workflow_surface=workflow_name,
                is_entry_workflow=workflow_name == entry_workflow_name,
                return_kind=return_kind,
            )
        )
    omitted_variants: list[str] = []
    if (
        entry_workflow is not None
        and entry_workflow.definition.publication_policy is not None
        and isinstance(entry_workflow.signature.return_type_ref, UnionTypeRef)
    ):
        omitted_variants = [
            variant.name
            for variant in entry_workflow.signature.return_type_ref.definition.variants
            if variant.name not in published_variants
        ]
        lowered_publications_for_entry = [
            row
            for row in lowered_publications
            if row.get("workflow_name") == entry_workflow_name
        ]
        lowered_publication_row_ids = {
            str(row.get("row_id", ""))
            for row in lowered_publications_for_entry
            if isinstance(row.get("row_id"), str)
        }
        source_map_generated_effect_step_ids = _entry_publication_source_map_step_ids(
            source_map_payload,
            workflow_name=entry_workflow_name,
        )
        for policy_row in policy_rows:
            if policy_row.row_id not in lowered_publication_row_ids:
                diagnostics.append(
                    {
                        "code": "entry_publication_lowering_missing",
                        "row_id": policy_row.row_id,
                        "workflow_name": entry_workflow_name,
                        "variant": policy_row.variant,
                        "role": policy_row.role,
                        "message": "publication policy row did not lower to a generated materialize_view step",
                    }
                )
                continue
            matching_step_ids = {
                str(row.get("step_id", ""))
                for row in lowered_publications_for_entry
                if row.get("row_id") == policy_row.row_id and isinstance(row.get("step_id"), str)
            }
            if not matching_step_ids or not matching_step_ids.issubset(source_map_generated_effect_step_ids):
                diagnostics.append(
                    {
                        "code": "entry_publication_source_map_missing",
                        "row_id": policy_row.row_id,
                        "workflow_name": entry_workflow_name,
                        "variant": policy_row.variant,
                        "role": policy_row.role,
                        "message": "publication policy row is missing generated source-map effect lineage",
                    }
                )
        for lowered in lowered_publications_for_entry:
            lowered_variant = lowered.get("variant")
            if not isinstance(lowered_variant, str) or lowered_variant not in omitted_variants:
                continue
            diagnostics.append(
                {
                    "code": "entry_publication_omitted_variant_published",
                    "row_id": str(lowered.get("row_id", "")),
                    "workflow_name": entry_workflow_name,
                    "variant": lowered_variant,
                    "role": str(lowered.get("role", "")),
                    "message": "omitted entry-publication variant lowered a publication view",
                }
            )
    contract_isolation = {
        "workflow_signature_unchanged": entry_workflow is None
        or not hasattr(entry_workflow.signature, "publication_policy"),
        "call_contract_unchanged": entry_workflow is None
        or not hasattr(entry_workflow.signature, "publication_policy"),
        "boundary_projection_public_inputs_unchanged": all(
            "publication" not in input_name
            for workflow in workflow_boundary_projection_payload.get("workflows", [])
            if isinstance(workflow, Mapping)
            for input_name in workflow.get("boundary", {}).get("public_input_names", [])
            if isinstance(workflow.get("boundary", {}), Mapping) and isinstance(input_name, str)
        ),
        "semantic_call_edges_hide_publish_policy": all(
            "publication" not in json.dumps(_json_data(bundle.semantic_ir.call_edges), sort_keys=True)
            for bundle in compile_result.validated_bundles_by_name.values()
        ),
    }
    for check_name, passed in contract_isolation.items():
        if passed:
            continue
        diagnostics.append(
            {
                "code": "entry_publication_contract_leak",
                "row_id": check_name,
                "workflow_name": entry_workflow_name,
                "message": f"publication policy leaked into `{check_name}`",
            }
        )
    return {
        **serialize_entry_publication_report(
            target_family=target_family,
            workflow_name=entry_workflow_name,
            source_census=_json_data(consumer_rendering_census.get("source_census", {}))
            if isinstance(consumer_rendering_census.get("source_census"), Mapping)
            else {},
            consumer_rendering_census={
                "path": str(consumer_rendering_census.get("__manifest_path__", "")),
                "sha256": (
                    f"sha256:{consumer_rendering_census.get('__manifest_sha256__', '')}"
                    if consumer_rendering_census.get("__manifest_sha256__")
                    else ""
                ),
                "schema_version": str(consumer_rendering_census.get("schema_version", "")),
            },
            publication_policy=serialize_entry_publication_policy(
                entry_workflow.definition.publication_policy if entry_workflow is not None else None
            ),
            selected_c0_rows=selected_rows,
            lowered_publications=lowered_publications,
            compatibility_reasons=compatibility_reasons,
            omitted_variants=omitted_variants,
            contract_isolation=contract_isolation,
            diagnostics=diagnostics,
        ),
    }


def _collect_entry_publication_lowerings(
    compile_result: LinkedStage3CompileResult,
    *,
    source_map_payload: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    from .build import _iter_surface_steps

    collected: list[dict[str, object]] = []
    for workflow_name, bundle in sorted(compile_result.validated_bundles_by_name.items()):
        for step in _iter_surface_steps(bundle.surface.steps):
            materialize_view = getattr(step, "materialize_view", None)
            if not isinstance(materialize_view, Mapping):
                continue
            publication = materialize_view.get("publication")
            if not isinstance(publication, Mapping):
                continue
            step_id = step.step_id
            if step_id.startswith("root."):
                step_id = step_id.rsplit(".", 1)[-1]
            collected.append(
                {
                    "workflow_name": workflow_name,
                    "step_id": step_id,
                    "step_name": step.name,
                    "row_id": str(publication.get("row_id", "")),
                    "role": str(publication.get("role", "")),
                    "variant": str(publication.get("variant", "")),
                    "renderer_id": str(materialize_view.get("renderer_id", "")),
                    "renderer_version": materialize_view.get("renderer_version"),
                    "target_path": materialize_view.get("target_path"),
                }
            )
    workflows = source_map_payload.get("workflows") if isinstance(source_map_payload, Mapping) else None
    if isinstance(workflows, Mapping):
        for workflow_name, workflow_payload in sorted(workflows.items()):
            if not isinstance(workflow_name, str) or not isinstance(workflow_payload, Mapping):
                continue
            generated_effects = workflow_payload.get("generated_semantic_effects")
            if not isinstance(generated_effects, list):
                continue
            for effect in generated_effects:
                if not isinstance(effect, Mapping) or effect.get("effect_kind") != "materialize_view":
                    continue
                details = effect.get("details")
                if not isinstance(details, Mapping):
                    continue
                role = details.get("publication_role")
                value_type = details.get("value_type")
                variant = value_type.get("variant") if isinstance(value_type, Mapping) else None
                step_id = effect.get("step_id")
                if not isinstance(role, str) or not role or not isinstance(variant, str) or not variant:
                    continue
                collected.append(
                    {
                        "workflow_name": workflow_name,
                        "step_id": str(step_id or ""),
                        "step_name": str(step_id or ""),
                        "row_id": _entry_publication_policy_row_id(
                            workflow_name=workflow_name,
                            variant=variant,
                            role=role,
                        ),
                        "role": role,
                        "variant": variant,
                        "renderer_id": str(details.get("renderer_id", "")),
                        "renderer_version": details.get("renderer_version"),
                        "target_path": details.get("target_path"),
                    }
                )
    deduped: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in collected:
        key = (
            str(row.get("workflow_name", "")),
            str(row.get("row_id", "")),
            str(row.get("step_id", "")),
        )
        deduped[key] = row
    return [deduped[key] for key in sorted(deduped)]


def _entry_publication_policy_row_id(
    *,
    workflow_name: str,
    variant: str,
    role: str,
) -> str:
    workflow_slug_source = workflow_name.rsplit("::", 1)[-1]
    return (
        f"publish.{_entry_publication_slug(workflow_slug_source)}."
        f"{variant.lower()}.{_entry_publication_slug(role)}"
    )


def _entry_publication_slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-")


def _entry_publication_source_map_step_ids(
    source_map_payload: Mapping[str, object],
    *,
    workflow_name: str,
) -> set[str]:
    workflows = source_map_payload.get("workflows")
    if not isinstance(workflows, Mapping):
        return set()
    workflow_payload = workflows.get(workflow_name)
    if not isinstance(workflow_payload, Mapping):
        return set()
    generated_effects = workflow_payload.get("generated_semantic_effects")
    if not isinstance(generated_effects, list):
        return set()
    step_ids: set[str] = set()
    for effect in generated_effects:
        if not isinstance(effect, Mapping):
            continue
        step_id = effect.get("step_id")
        if isinstance(step_id, str) and step_id:
            step_ids.add(step_id)
    return step_ids


def _fingerprint_build(
    *,
    request: FrontendBuildRequest,
    compile_result: LinkedStage3CompileResult,
    imported_bindings: tuple[ImportedWorkflowBundleBinding, ...],
    entry_selection: FrontendEntrySelection,
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    command_boundary_manifest: Mapping[str, object],
    family_profile_catalog: WorkflowFamilyProfileCatalog | None,
    boundary_authority_registry: Mapping[str, object] | None,
    value_flow_census: Mapping[str, object] | None,
    consumer_rendering_census: Mapping[str, object] | None,
    observability_old_writer_pair_manifest: Mapping[str, object] | None,
    resume_plumbing_retirement_manifest: Mapping[str, object] | None,
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
        "family_profile": _family_profile_metadata_for_entry(
            family_profile_catalog,
            entry_selection.canonical_name,
        ),
        "boundary_authority_registry": _json_data(boundary_authority_registry)
        if boundary_authority_registry is not None
        else None,
        "value_flow_census": _json_data(value_flow_census)
        if value_flow_census is not None
        else None,
        "consumer_rendering_census": _json_data(consumer_rendering_census)
        if consumer_rendering_census is not None
        else None,
        "observability_old_writer_pair_manifest": _json_data(
            observability_old_writer_pair_manifest
        )
        if observability_old_writer_pair_manifest is not None
        else None,
        "resume_plumbing_retirement_manifest": _json_data(
            resume_plumbing_retirement_manifest
        )
        if resume_plumbing_retirement_manifest is not None
        else None,
    }
    encoded = json.dumps(source_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _add_design_delta_artifacts(
    artifact_paths: dict[str, Path],
    payloads: dict[str, object],
    build_root: Path,
    reports: DesignDeltaReportPayloads,
) -> None:
    """Register the populated design-delta report artifacts (path + payload).

    Isolated so a future retirement of the certification lane deletes it (and the
    single call site) cleanly. Each entry mirrors a pre-split
    ``if <payload> is not None:`` block; the emit order matches the pre-split source.
    ``compatibility_bridge_generated_steps`` (folded into ``lowered_workflows``) and
    the ``checkpoint_*_for_retirement`` fields are deliberately not emitted here.
    """

    design_delta_artifacts: tuple[tuple[str, str, Mapping[str, object] | None], ...] = (
        ("adapter_census", "adapter_census.json", reports.adapter_census),
        (
            "boundary_authority_report",
            "boundary_authority_report.json",
            reports.boundary_authority_report,
        ),
        (
            "value_flow_census_report",
            "value_flow_census_report.json",
            reports.value_flow_census_report,
        ),
        (
            "consumer_rendering_census_report",
            "consumer_rendering_census_report.json",
            reports.consumer_rendering_census_report,
        ),
        (
            "typed_prompt_input_report",
            "typed_prompt_input_report.json",
            reports.typed_prompt_input_report,
        ),
        (
            "observability_summary_report",
            "observability_summary_report.json",
            reports.observability_summary_report,
        ),
        (
            "entry_publication_report",
            "entry_publication_report.json",
            reports.entry_publication_report,
        ),
        (
            "compatibility_bridge_report",
            "compatibility_bridge_report.json",
            reports.compatibility_bridge_report,
        ),
        (
            "rendering_cleanup_report",
            "rendering_cleanup_report.json",
            reports.rendering_cleanup_report,
        ),
        (
            "rendering_ergonomics_report",
            "rendering_ergonomics_report.json",
            reports.rendering_ergonomics_report,
        ),
        (
            "transition_authoring_report",
            "transition_authoring_report.json",
            reports.transition_authoring_report,
        ),
        (
            "resume_plumbing_retirement_report",
            "resume_plumbing_retirement_report.json",
            reports.resume_plumbing_retirement_report,
        ),
        (
            "parent_drain_census_alignment_report",
            "parent_drain_census_alignment_report.json",
            reports.parent_drain_census_alignment_report,
        ),
        (
            "reference_family_conformance_profile",
            "reference_family_conformance_profile.json",
            reports.reference_family_conformance_profile,
        ),
        (
            "lexical_checkpoint_default_resume_report",
            "lexical_checkpoint_default_resume_report.json",
            reports.default_resume_report,
        ),
        ("g8_deletion_evidence", "g8_deletion_evidence.json", reports.g8_deletion_evidence),
    )
    for artifact_key, filename, payload in design_delta_artifacts:
        if payload is not None:
            artifact_paths[artifact_key] = build_root / filename
            payloads[artifact_key] = _json_data(payload)


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
    design_delta_reports: DesignDeltaReportPayloads | None = None,
) -> Mapping[str, Path]:
    reports = design_delta_reports or DesignDeltaReportPayloads()
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
            extra_compatibility_bridge_steps=reports.compatibility_bridge_generated_steps,
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
    _add_design_delta_artifacts(artifact_paths, payloads, build_root, reports)
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
    *,
    extra_compatibility_bridge_steps: Sequence[Mapping[str, object]] = (),
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

    workflow_name = payload.get("workflow_name")
    if not isinstance(workflow_name, str) or not workflow_name:
        return payload
    nodes = payload.get("nodes")
    if not isinstance(nodes, dict):
        return payload
    observability = payload.get("observability")
    observability_nodes = (
        observability.get("nodes")
        if isinstance(observability, dict)
        and isinstance(observability.get("nodes"), dict)
        else None
    )
    ordered_node_ids = payload.get("ordered_node_ids")
    if not isinstance(ordered_node_ids, list):
        ordered_node_ids = []
        payload["ordered_node_ids"] = ordered_node_ids
    existing_step_ids = {
        str(node.get("step_id", ""))
        for node in nodes.values()
        if isinstance(node, Mapping) and isinstance(node.get("step_id"), str)
    }
    execution_indexes = [
        int(node.get("execution_index"))
        for node in nodes.values()
        if isinstance(node, Mapping) and isinstance(node.get("execution_index"), int)
    ]
    next_execution_index = max(execution_indexes) + 1 if execution_indexes else 0
    for row in extra_compatibility_bridge_steps:
        if not isinstance(row, Mapping) or row.get("workflow_name") != workflow_name:
            continue
        step_id = row.get("step_id")
        node_id = row.get("node_id")
        if not isinstance(step_id, str) or not isinstance(node_id, str):
            continue
        if step_id in existing_step_ids:
            continue
        display_name = step_id.replace("__", " ")
        node_payload = {
            "node_id": node_id,
            "step_id": step_id,
            "presentation_key": step_id,
            "display_name": display_name,
            "kind": "materialize_view",
            "region": "top_level",
            "execution_index": next_execution_index,
            "lexical_scope": [],
            "fallthrough_node_id": None,
            "routed_transfer_targets": {},
            "dependency_node_ids": [],
            "nested_body_node_ids": [],
            "call_alias": None,
            "command_boundary_kind": None,
            "command_boundary_name": None,
        }
        nodes[node_id] = node_payload
        ordered_node_ids.append(node_id)
        if observability_nodes is not None:
            observability_nodes[node_id] = {
                "node_id": node_id,
                "step_id": step_id,
                "presentation_key": step_id,
                "display_name": display_name,
                "kind": "materialize_view",
                "region": "top_level",
            }
            top_level = observability.get("top_level_ordered_node_ids")
            if isinstance(top_level, list):
                top_level.append(node_id)
        existing_step_ids.add(step_id)
        next_execution_index += 1
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
    family_profile: Mapping[str, object] | None,
    boundary_authority_registry: Mapping[str, object] | None,
    value_flow_census: Mapping[str, object] | None,
    consumer_rendering_census: Mapping[str, object] | None,
    observability_old_writer_pair_manifest: Mapping[str, object] | None,
    resume_plumbing_retirement_manifest: Mapping[str, object] | None,
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
        family_profile=family_profile,
        boundary_authority_registry=_boundary_authority_registry_provenance(
            boundary_authority_registry
        ),
        value_flow_census=_value_flow_census_provenance(value_flow_census),
        consumer_rendering_census=_consumer_rendering_census_provenance(
            consumer_rendering_census
        ),
        observability_old_writer_pair_evidence=_observability_old_writer_pair_provenance(
            observability_old_writer_pair_manifest
        ),
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
    *,
    extra_compatibility_bridge_steps: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    step_ids_by_workflow: dict[str, set[str]] = {}
    for row in extra_compatibility_bridge_steps:
        if not isinstance(row, Mapping):
            continue
        workflow_name = row.get("workflow_name")
        step_id = row.get("step_id")
        if not isinstance(workflow_name, str) or not isinstance(step_id, str):
            continue
        step_ids_by_workflow.setdefault(workflow_name, set()).add(step_id)
    return {
        "modules": {
            module_name: {
                "workflows": [
                    {
                        "workflow_name": lowered.typed_workflow.definition.name,
                        "display_name": _display_workflow_name(lowered.typed_workflow.definition.name),
                        "authored_mapping": _json_data(lowered.authored_mapping),
                        "step_ids": sorted(
                            set(lowered.origin_map.step_spans)
                            | step_ids_by_workflow.get(
                                lowered.typed_workflow.definition.name, set()
                            )
                        ),
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
    boundary_authority_registry: Mapping[str, object] | None = None,
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
                checked_public_bridge_inputs = checked_design_delta_public_input_names(
                    lowered.typed_workflow.definition.name,
                    boundary_authority_registry=boundary_authority_registry,
                    family_profile_catalog=compiled_result.workflow_catalog.family_profile_catalog,
                )
                private_compatibility_bridge_inputs = sorted(
                    name
                    for name in lowered.compatibility_bridge_inputs
                    if isinstance(name, str)
                    and name not in checked_public_bridge_inputs
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


def _validate_selected_workflow_hidden_compatibility_bridge_public_boundary(
    boundary_projection_payload: Mapping[str, object],
    *,
    selected_name: str,
    boundary_authority_registry: Mapping[str, object] | None,
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None,
) -> None:
    if boundary_authority_registry is None:
        # A missing registry only exempts workflows outside the
        # design-delta-parent-drain family, which has no checked
        # boundary-authority-registry concept to begin with. A design-delta
        # target missing its registry must still fail closed.
        if not is_design_delta_parent_drain_target_workflow(
            selected_name, family_profile_catalog=family_profile_catalog
        ):
            return
    elif (
        boundary_authority_registry.get("workflow_family") != "design_delta_parent_drain"
        and (
            family_profile_catalog is None
            or not family_profile_catalog.workflow_in_profile(selected_name)
        )
    ):
        return
    workflows = {
        str(workflow["workflow_name"]): workflow
        for workflow in boundary_projection_payload.get("workflows", [])
        if isinstance(workflow, Mapping)
        and isinstance(workflow.get("workflow_name"), str)
    }
    selected_workflow = workflows.get(selected_name)
    if not isinstance(selected_workflow, Mapping):
        return

    params = {
        str(param.get("name"))
        for param in selected_workflow.get("params", [])
        if isinstance(param, Mapping) and isinstance(param.get("name"), str)
    }
    private_bridge_inputs = {
        str(name)
        for name in selected_workflow.get("boundary", {}).get(
            "private_compatibility_bridge_inputs", []
        )
        if isinstance(name, str)
    }
    if not private_bridge_inputs:
        return

    registry_path = None
    if isinstance(boundary_authority_registry, Mapping):
        raw_registry_path = boundary_authority_registry.get("__registry_path__")
        if isinstance(raw_registry_path, (str, Path)) and str(raw_registry_path):
            registry_path = Path(str(raw_registry_path))

    allowed_public_bridge_inputs = {
        str(row.get("field_name"))
        for row in (boundary_authority_registry or {}).get("rows", [])
        if isinstance(row, Mapping)
        and row.get("workflow_name") == selected_name
        and row.get("surface_kind") == "compatibility_bridge_input"
        and row.get("authority_class") == "compatibility_bridge"
        and isinstance(row.get("field_name"), str)
    }
    publicly_authored_hidden_bridges = sorted(
        (params & private_bridge_inputs) - allowed_public_bridge_inputs
    )
    if not publicly_authored_hidden_bridges:
        return
    raise LispFrontendCompileError(
        (
            _cli_request_diagnostic(
                code="workflow_boundary_authority_unclassified",
                message=(
                    "selected workflow publicly declares hidden compatibility bridge "
                    "inputs without checked boundary-authority metadata: "
                    f"{selected_name}: {', '.join(publicly_authored_hidden_bridges)}"
                ),
                path=registry_path,
            ),
        )
    )


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
