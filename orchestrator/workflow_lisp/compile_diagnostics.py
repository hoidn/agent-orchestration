"""Machine compile-diagnostics assembly for full frontend builds."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from orchestrator.workflow.run_ref.contracts import (
    canonical_sha256,
    compute_compiler_runtime_identity,
)

from .build import FrontendBuildResult
from .build_manifest_io import _json_data
from .compiler import WorkflowBoundaryAdmissionProfile
from .diagnostics import (
    LispFrontendDiagnostic,
    build_compile_diagnostics_document,
    build_normalized_program_identity,
)


def build_rejected_compile_diagnostics_document(
    diagnostics: Iterable[LispFrontendDiagnostic],
) -> dict[str, object]:
    """Build the closed machine document for a rejected full compile."""

    return build_compile_diagnostics_document(
        status="rejected",
        diagnostics=diagnostics,
    )


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


def _compiler_source_revisions(
    result: FrontendBuildResult,
) -> list[dict[str, object]]:
    request = result.resolved_request
    roots: list[tuple[str, Path]] = [
        (f"source_root:{index}", root)
        for index, root in enumerate(request.source_roots)
    ]
    roots.append(("entry_source_root", request.source_path.parent))
    roots.extend(
        (
            f"imported_bundle:{binding.canonical_key}",
            binding.resolved_bundle_path.parent,
        )
        for binding in sorted(
            result.imported_workflow_bundles,
            key=lambda item: item.canonical_key.encode("utf-8"),
        )
    )
    roots.append(("workspace_root", request.workspace_root))

    rows: list[dict[str, object]] = []
    for source_path, revision in result.source_read_trace.revision_vector:
        normalized: tuple[str, str] | None = None
        for root_role, root in roots:
            try:
                relative_path = source_path.relative_to(root)
            except ValueError:
                continue
            normalized = (root_role, relative_path.as_posix())
            break
        if normalized is None:
            raise ValueError(
                "compiler-read source is outside declared identity roots"
            )
        rows.append(
            {
                "root_role": normalized[0],
                "relative_path": normalized[1],
                "source_sha256": revision,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row["root_role"]),
            str(row["relative_path"]).encode("utf-8"),
        ),
    )


def _imported_bundle_bindings(
    result: FrontendBuildResult,
) -> list[dict[str, object]]:
    return [
        {
            "canonical_key": binding.canonical_key,
            "bundle_kind": binding.bundle_kind,
            "workflow_name": binding.workflow_name,
            "resolved_workflow_name": binding.bundle.surface.name,
        }
        for binding in result.imported_workflow_bundles
    ]


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


def build_accepted_compile_diagnostics_document(
    result: FrontendBuildResult,
) -> dict[str, object]:
    """Build the closed machine document for an accepted full compile."""

    selected_entry = _selected_entry_document(result)
    configuration_payload_digests, configuration_revisions = (
        _configuration_identity(result)
    )
    route = result.compile_request_capture.lowering_route.value
    program_identity = build_normalized_program_identity(
        compiler_runtime_identity=compute_compiler_runtime_identity().digest,
        module_source_revisions=_module_source_revisions(result),
        compiler_source_revisions=_compiler_source_revisions(result),
        imported_bundle_bindings=_imported_bundle_bindings(result),
        selected_entry=selected_entry,
        lowering_route=route,
        lowering_schema_version=result.manifest.lowering_schema_version,
        configuration_payload_digests=configuration_payload_digests,
        configuration_revisions=configuration_revisions,
        boundary_admission_profile=(
            result.compile_request_capture.boundary_admission_profile.value
            if result.compile_request_capture.boundary_admission_profile
            is WorkflowBoundaryAdmissionProfile.TRANSPORTABLE_CHILD
            else None
        ),
    )
    return build_compile_diagnostics_document(
        status="accepted",
        diagnostics=result.diagnostics,
        selected_entry=selected_entry,
        normalized_program_identity=program_identity,
    )
