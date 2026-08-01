"""Typed diagnostics and rendering helpers for the workflow Lisp frontend."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)

from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    DiagnosticSource,
    DiagnosticSpan,
    PhasedDeliveryDiagnostic,
    build_phased_delivery_diagnostic,
)
from orchestrator.workflow.provider_phased_delivery.protocol import (
    diagnostic_to_dict as phased_delivery_diagnostic_to_dict,
)

from .lints import (
    LINT_PROFILE_DEFAULT,
    is_required_lint_code,
    required_lint_rule,
    required_lint_severity,
)
from .spans import SourcePosition, SourceSpan


_VALIDATION_PASS_TO_PHASE = {
    "parse": "read",
    "module": "syntax",
    "macro": "macro",
    "type": "typecheck",
    "effect": "typecheck",
    "reference": "typecheck",
    "contract": "typecheck",
    "proof": "typecheck",
    "authority": "lowering",
    "lowering_surface": "lowering",
    "source_map": "source_map",
    "shared_validation": "shared_validation",
    "semantic_ir": "semantic_ir",
    "executable": "executable",
}
_VALIDATION_PASS_ORDER = (
    "parse",
    "module",
    "macro",
    "type",
    "effect",
    "reference",
    "contract",
    "proof",
    "authority",
    "lowering_surface",
    "source_map",
    "shared_validation",
    "semantic_ir",
    "executable",
)
_VALIDATION_PASS_ORDER_INDEX = {
    pass_id: index for index, pass_id in enumerate(_VALIDATION_PASS_ORDER)
}
_PHASE_TO_VALIDATION_PASS = {
    "read": "parse",
    "syntax": "module",
    "macro": "macro",
    "typecheck": "type",
    "lowering": "lowering_surface",
    "source_map": "source_map",
    "shared_validation": "shared_validation",
    "semantic_ir": "semantic_ir",
    "executable": "executable",
}
_SHARED_VALIDATION_CODES = frozenset(
    {
        "workflow_call_version_mismatch",
        "contract_refinement_weakened",
        "contract_refinement_type_conflict",
        "pointer_authority_conflict",
        "snapshot_ref_unknown_step",
        "snapshot_ref_unknown_name",
        "snapshot_candidate_unchanged",
        "snapshot_candidate_ambiguous",
        "invalid_variant_bundle",
        "variant_required_field_missing",
        "variant_forbidden_field_present",
        "variant_ref_unproved",
        "variant_ref_wrong_variant",
        "variant_unavailable",
        "atomic_commit_failed",
        "bundle_commit_aborted_invalid_candidate",
        "semantic_ir_invalid",
    }
)
_AUTHORITY_CODES = frozenset(
    {
        "command_adapter_missing_contract",
        "inline_python_command_in_workflow",
        "inline_shell_command_in_workflow",
        "semantic_field_extracted_from_report",
        "markdown_report_used_as_state",
        "pointer_used_as_semantic_authority",
        "materialized_view_used_as_semantic_authority",
        "noncanonical_pointer_sidecar",
        "published_pointer_path_instead_of_value",
        "legacy_adapter_missing_fixture",
        "legacy_adapter_not_deprecated",
    }
)
_SOURCE_MAP_CODES = frozenset(
    {
        "source_map_missing",
        "closure_source_map_missing",
    }
)
_EXECUTABLE_CODES = frozenset(
    {
        "executable_ir_invalid",
        "closure_resume_bundle_mismatch",
        "closure_resume_code_mismatch",
    }
)
_RUNTIME_CLOSURE_TYPE_CODES = frozenset(
    {
        "runtime_closure_not_enabled",
        "closure_family_unknown",
        "closure_code_id_invalid",
        "closure_signature_invalid",
        "closure_dynamic_code_forbidden",
        "closure_provider_capture_forbidden",
        "closure_capture_mode_forbidden",
        "closure_capture_schema_invalid",
        "closure_runtime_transport_forbidden",
        "closure_effect_bound_invalid",
        "closure_capability_bound_invalid",
        "closure_write_root_ambiguous",
    }
)
_TYPE_CODES = frozenset(
    {
        "name_unknown",
        "record_field_unknown",
        "record_field_missing",
        "union_variant_unknown",
        "union_match_non_exhaustive",
        "schema_used_as_type",
        "type_expression_invalid",
        "collection_key_type_invalid",
        "function_call_unknown",
        "function_arity_mismatch",
        "function_return_type_invalid",
        "parametric_constraint_malformed",
        "parametric_constraint_unknown",
        "parametric_constraint_unsatisfied",
        "parametric_capability_undeclared",
        "procedure_return_type_invalid",
        "workflow_call_unknown",
        "transition_unknown",
        "transition_declaration_invalid",
        "transition_resource_unknown",
        "transition_resource_kind_mismatch",
        "transition_request_type_mismatch",
        "transition_update_target_unknown",
        "transition_write_set_undeclared",
        "transition_result_projection_type_mismatch",
        "transition_backend_unknown",
        "loop_state_requires_typed_fields",
        "loop_state_duplicate_field",
        "loop_state_like_not_loop_state",
        "loop_state_unknown_field",
        "loop_state_field_type_mismatch",
        "loop_state_runtime_transport_forbidden",
        "loop_state_unresolved_type_parameter",
        "loop_state_not_projectable",
        "pure_expr_operator_unsupported",
        "pure_expr_operand_type_mismatch",
        "enum_member_unknown",
        "pure_expr_union_equality_forbidden",
        "pure_expr_float_equality_forbidden",
        "pure_expr_path_string_concat_forbidden",
        "pure_expr_optional_access_unproved",
        "pure_expr_overflow",
        "materialize_view_renderer_unknown",
        "materialize_view_value_type_invalid",
        "materialize_view_target_contract_invalid",
        "value_type_requires_dsl_2_19",
        "value_guidance_example_unsupported",
    }
)
_LOWERING_SURFACE_CODES = frozenset(
    {
        "lowering_no_backend_for_form",
        "resource_transition_requires_runtime_backend",
        "proc_lowering_cycle",
        "wcc_lowering_route_unsupported",
        "path_definition_invalid",
        "workflow_boundary_type_invalid",
        "workflow_boundary_collection_unsupported",
        "collection_element_type_unsupported",
        "review_loop_special_lowerer_used",
        "union_return_variant_ambiguous",
        "union_return_variant_incompatible",
        "pure_expr_payload_too_large",
        "materialize_view_render_failed",
        "materialize_view_nondeterministic_render",
        "materialize_view_resume_schema_mismatch",
    }
)
_MODULE_CODES = frozenset(
    {
        "definition_duplicate",
        "schema_definition_invalid",
        "schema_unknown",
        "schema_cycle",
        "schema_field_duplicate",
        "function_definition_duplicate",
        "record_field_duplicate",
        "union_variant_duplicate",
        "module_not_found",
        "module_cycle",
        "module_export_missing",
        "module_import_ambiguous",
        "callable_name_collision",
        "definition_form_unknown",
        "target_dsl_unsupported",
        "language_version_unsupported",
        "procedure_definition_duplicate",
        "procedure_type_param_duplicate",
        "procedure_type_param_clause_invalid",
        "procedure_type_param_unknown",
        "procedure_type_param_unbindable",
        "procedure_where_clause_invalid",
        "procedure_where_field_requirement_invalid",
    }
)
_EFFECT_CODES = frozenset(
    {
        "pure_function_has_effect",
        "function_cycle",
        "macro_has_effect",
        "effect_not_declared",
        "effect_not_permitted",
        "resource_transition_capability_missing",
        "provider_effect_hidden",
        "command_effect_hidden",
        "state_update_hidden",
    }
)


@dataclass(frozen=True)
class LispFrontendDiagnostic:
    """One deterministic frontend diagnostic."""

    code: str
    message: str
    span: SourceSpan
    diagnostic_kind: str | None = None
    severity: str | None = None
    form_path: tuple[str, ...] = ()
    expansion_stack: tuple[object, ...] = ()
    notes: tuple[str, ...] = ()
    phase: str | None = None
    validation_pass: str | None = None
    authority_layer: str | None = None
    phased_delivery_diagnostic: PhasedDeliveryDiagnostic | None = None


class LispFrontendCompileError(Exception):
    """Raised when Workflow Lisp compilation accumulates diagnostics."""

    def __init__(
        self,
        diagnostics: tuple[LispFrontendDiagnostic, ...],
        *,
        configuration_revision_vector: tuple[tuple[Path, str], ...] | None = None,
        configuration_revision_conflict_paths: tuple[Path, ...] | None = None,
    ):
        self.diagnostics = diagnostics
        self.configuration_revision_vector = configuration_revision_vector
        self.configuration_revision_conflict_paths = (
            configuration_revision_conflict_paths
        )
        super().__init__(render_diagnostics(diagnostics))


def render_diagnostic(diagnostic: LispFrontendDiagnostic) -> str:
    """Render one diagnostic into stable human-readable text."""

    classified = with_diagnostic_metadata(diagnostic)
    location = (
        f"{diagnostic.span.start.path}:"
        f"{diagnostic.span.start.line}:"
        f"{diagnostic.span.start.column}"
    )
    parts = [f"{location}: [{diagnostic.code}] {diagnostic.message}"]
    if classified.diagnostic_kind is not None:
        parts.append(f"kind: {classified.diagnostic_kind}")
    if classified.form_path:
        parts.append(f"form: {' > '.join(classified.form_path)}")
    for note in _render_expansion_notes(classified.expansion_stack):
        parts.append(f"note: {note}")
    for note in classified.notes:
        parts.append(f"note: {note}")
    return "\n".join(parts)


def render_diagnostics(diagnostics: Iterable[LispFrontendDiagnostic]) -> str:
    """Render multiple diagnostics in deterministic order."""

    return "\n\n".join(render_diagnostic(diagnostic) for diagnostic in diagnostics)


def serialize_diagnostic(
    diagnostic: LispFrontendDiagnostic,
    *,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> dict[str, object]:
    """Serialize one diagnostic into a machine-readable envelope."""

    classified = with_diagnostic_metadata(diagnostic, lint_profile=lint_profile)
    payload: dict[str, object] = {
        "code": classified.code,
        "diagnostic_kind": classified.diagnostic_kind,
        "severity": classified.severity or "error",
        "message": classified.message,
        "path": classified.span.start.path,
        "line": classified.span.start.line,
        "column": classified.span.start.column,
        "form_path": list(classified.form_path),
        "expansion_stack": [
            _serialize_expansion_frame(frame)
            for frame in classified.expansion_stack
        ],
        "notes": list(classified.notes),
        "phase": classified.phase,
        "validation_pass": classified.validation_pass,
        "authority_layer": classified.authority_layer,
    }
    if classified.phased_delivery_diagnostic is not None:
        payload["phased_delivery_diagnostic"] = (
            phased_delivery_diagnostic_to_dict(
                classified.phased_delivery_diagnostic
            )
        )
    return payload


def build_authored_phased_delivery_diagnostic(
    reason: str,
    *,
    canonical_value: bool | int | str | None,
    source_spans_by_owner: Mapping[str, SourceSpan],
) -> PhasedDeliveryDiagnostic:
    """Build a closed phased diagnostic from exact authored syntax spans."""

    sources = {
        owner: DiagnosticSource(
            kind="authored_span",
            owner=owner,
            path=_relative_diagnostic_source_path(span.start.path),
            span=DiagnosticSpan(
                start_line=span.start.line,
                start_column=span.start.column,
                end_line=span.end.line,
                end_column=span.end.column,
            ),
        )
        for owner, span in source_spans_by_owner.items()
    }
    return build_phased_delivery_diagnostic(
        reason,
        canonical_value=canonical_value,
        sources_by_owner=sources,
    )


def _relative_diagnostic_source_path(value: str) -> str:
    """Normalize a retained compiler path without inventing a source location."""

    path = Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(Path.cwd())
        except ValueError:
            # Standalone source compilation defaults its source root to the
            # source file's parent, making the file name root-relative.
            path = Path(path.name)
    normalized = path.as_posix()
    if not normalized or normalized.startswith("../") or normalized == "..":
        raise ValueError(
            "phased-delivery diagnostic source must be root-relative"
        )
    return normalized


def serialize_diagnostics(
    diagnostics: Iterable[LispFrontendDiagnostic],
    *,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> list[dict[str, object]]:
    """Serialize multiple diagnostics in deterministic order."""

    return [
        serialize_diagnostic(diagnostic, lint_profile=lint_profile)
        for diagnostic in diagnostics
    ]


def _canonical_json_value(value: object) -> object:
    """Copy one closed JSON value through the canonical encoder."""

    return json.loads(canonical_json_bytes(value))


def _is_sha256_identity(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(
        character in "0123456789abcdef" for character in digest
    )


def _canonical_selected_entry(
    selected_entry: Mapping[str, object],
) -> dict[str, object]:
    value = _canonical_json_value(dict(selected_entry))
    if not isinstance(value, Mapping) or set(value) != {
        "selected_name",
        "canonical_name",
        "signature",
    }:
        raise ValueError("selected entry has an invalid shape")
    if any(
        not isinstance(value.get(field), str) or not value.get(field)
        for field in ("selected_name", "canonical_name")
    ):
        raise ValueError("selected entry names must be non-empty strings")
    signature = value.get("signature")
    if not isinstance(signature, Mapping) or set(signature) != {
        "parameters",
        "return_type",
        "input_contracts",
        "output_contracts",
    }:
        raise ValueError("selected entry signature has an invalid shape")
    parameters = signature.get("parameters")
    if not isinstance(parameters, list) or any(
        not isinstance(parameter, Mapping)
        or set(parameter) != {"name", "type", "required"}
        or not isinstance(parameter.get("name"), str)
        or not parameter.get("name")
        or not isinstance(parameter.get("type"), str)
        or not parameter.get("type")
        or not isinstance(parameter.get("required"), bool)
        for parameter in parameters
    ):
        raise ValueError("selected entry signature parameters have an invalid shape")
    parameter_names = [str(parameter["name"]) for parameter in parameters]
    if len(parameter_names) != len(set(parameter_names)):
        raise ValueError("selected entry signature parameters contain a duplicate")
    if (
        not isinstance(signature.get("return_type"), str)
        or not signature.get("return_type")
    ):
        raise ValueError("selected entry return type must be a non-empty string")
    for field in ("input_contracts", "output_contracts"):
        contracts = signature.get(field)
        if not isinstance(contracts, Mapping) or any(
            not isinstance(name, str) or not name for name in contracts
        ):
            raise ValueError(f"selected entry {field} have an invalid shape")
    return dict(value)


def _canonical_module_source_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    value = _canonical_json_value(list(rows))
    if not isinstance(value, list) or not value:
        raise ValueError("program identity requires module source revisions")
    if any(
        not isinstance(row, Mapping)
        or set(row) != {"module_name", "source_sha256"}
        or not isinstance(row.get("module_name"), str)
        or not row.get("module_name")
        or not _is_sha256_identity(row.get("source_sha256"))
        for row in value
    ):
        raise ValueError("module source revisions have an invalid shape")
    names = [str(row["module_name"]) for row in value]
    if len(names) != len(set(names)):
        raise ValueError("module source revisions contain a duplicate module")
    return sorted(
        (dict(row) for row in value),
        key=lambda row: str(row["module_name"]).encode("utf-8"),
    )


def _canonical_compiler_source_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    value = _canonical_json_value(list(rows))
    if not isinstance(value, list) or not value:
        raise ValueError("program identity requires compiler source revisions")
    if any(
        not isinstance(row, Mapping)
        or set(row) != {"root_role", "relative_path", "source_sha256"}
        or not isinstance(row.get("root_role"), str)
        or not row.get("root_role")
        or not isinstance(row.get("relative_path"), str)
        or not row.get("relative_path")
        or not _is_sha256_identity(row.get("source_sha256"))
        for row in value
    ):
        raise ValueError("compiler source revisions have an invalid shape")
    identities = [
        (str(row["root_role"]), str(row["relative_path"]))
        for row in value
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("compiler source revisions contain a duplicate path")
    return sorted(
        (dict(row) for row in value),
        key=lambda row: (
            str(row["root_role"]).encode("utf-8"),
            str(row["relative_path"]).encode("utf-8"),
        ),
    )


def _canonical_imported_bundle_rows(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    value = _canonical_json_value(list(rows))
    if not isinstance(value, list):
        raise ValueError("imported bundle bindings have an invalid shape")
    expected_fields = {
        "canonical_key",
        "bundle_kind",
        "workflow_name",
        "resolved_workflow_name",
    }
    if any(
        not isinstance(row, Mapping)
        or set(row) != expected_fields
        or not isinstance(row.get("canonical_key"), str)
        or not row.get("canonical_key")
        or not isinstance(row.get("bundle_kind"), str)
        or not row.get("bundle_kind")
        or not (
            row.get("workflow_name") is None
            or (
                isinstance(row.get("workflow_name"), str)
                and bool(row.get("workflow_name"))
            )
        )
        or not isinstance(row.get("resolved_workflow_name"), str)
        or not row.get("resolved_workflow_name")
        for row in value
    ):
        raise ValueError("imported bundle bindings have an invalid shape")
    keys = [str(row["canonical_key"]) for row in value]
    if len(keys) != len(set(keys)):
        raise ValueError("imported bundle bindings contain a duplicate key")
    return sorted(
        (dict(row) for row in value),
        key=lambda row: str(row["canonical_key"]).encode("utf-8"),
    )


def build_normalized_program_identity(
    *,
    compiler_runtime_identity: str,
    module_source_revisions: Iterable[Mapping[str, object]],
    compiler_source_revisions: Iterable[Mapping[str, object]],
    imported_bundle_bindings: Iterable[Mapping[str, object]],
    selected_entry: Mapping[str, object],
    lowering_route: str,
    lowering_schema_version: int,
    configuration_payload_digests: Mapping[str, str],
    configuration_revisions: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Build the path-independent identity exposed by machine compilation."""

    if not _is_sha256_identity(compiler_runtime_identity):
        raise ValueError("compiler/runtime identity must be a SHA-256 identity")
    if not isinstance(lowering_route, str) or not lowering_route:
        raise ValueError("lowering route must be non-empty")
    if (
        not isinstance(lowering_schema_version, int)
        or isinstance(lowering_schema_version, bool)
        or lowering_schema_version < 1
    ):
        raise ValueError("lowering schema version must be positive")
    module_rows = _canonical_module_source_rows(module_source_revisions)
    compiler_source_rows = _canonical_compiler_source_rows(
        compiler_source_revisions
    )
    imported_bundle_rows = _canonical_imported_bundle_rows(
        imported_bundle_bindings
    )
    payload_digests = _canonical_json_value(dict(configuration_payload_digests))
    expected_configuration_roles = {
        "provider_externs",
        "prompt_externs",
        "command_boundaries",
    }
    if (
        not isinstance(payload_digests, Mapping)
        or set(payload_digests) != expected_configuration_roles
        or any(not _is_sha256_identity(value) for value in payload_digests.values())
    ):
        raise ValueError("configuration payload digests have an invalid shape")
    revision_rows_value = _canonical_json_value(list(configuration_revisions))
    if not isinstance(revision_rows_value, list) or {
        row.get("role")
        for row in revision_rows_value
        if isinstance(row, Mapping)
    } != expected_configuration_roles:
        raise ValueError("configuration revisions have an invalid role set")
    if any(
        not isinstance(row, Mapping)
        or set(row) != {"role", "source_sha256"}
        or not (
            row.get("source_sha256") is None
            or _is_sha256_identity(row.get("source_sha256"))
        )
        for row in revision_rows_value
    ):
        raise ValueError("configuration revisions have an invalid shape")
    if len(revision_rows_value) != len(expected_configuration_roles):
        raise ValueError("configuration revisions contain a duplicate role")
    revision_rows = sorted(
        (dict(row) for row in revision_rows_value),
        key=lambda row: str(row["role"]).encode("utf-8"),
    )
    selected_entry_value = _canonical_selected_entry(selected_entry)
    components = {
        "schema_version": "workflow_lisp_program_identity.v1",
        "compiler_runtime_identity": compiler_runtime_identity,
        "module_source_revisions": module_rows,
        "compiler_source_revisions": compiler_source_rows,
        "imported_bundle_bindings": imported_bundle_rows,
        "selected_entry_sha256": canonical_sha256(selected_entry_value),
        "lowering_route": lowering_route,
        "lowering_schema_version": lowering_schema_version,
        "configuration_payload_digests": payload_digests,
        "configuration_revisions": revision_rows,
    }
    return {
        **components,
        "digest": canonical_sha256(components),
    }


def build_compile_diagnostics_document(
    *,
    status: str,
    diagnostics: Iterable[LispFrontendDiagnostic],
    selected_entry: Mapping[str, object] | None = None,
    normalized_program_identity: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Serialize one closed external full-compiler result document."""

    if status not in {"accepted", "rejected"}:
        raise ValueError("compile diagnostics status must be accepted or rejected")
    accepted_payload_present = (
        selected_entry is not None and normalized_program_identity is not None
    )
    if status == "accepted" and not accepted_payload_present:
        raise ValueError("accepted compile diagnostics require entry and identity")
    if status == "rejected" and (
        selected_entry is not None or normalized_program_identity is not None
    ):
        raise ValueError("rejected compile diagnostics cannot carry accepted fields")
    if status == "accepted":
        selected_entry_value = _canonical_selected_entry(selected_entry or {})
        if set(normalized_program_identity or ()) != {
            "schema_version",
            "digest",
            "compiler_runtime_identity",
            "module_source_revisions",
            "compiler_source_revisions",
            "imported_bundle_bindings",
            "selected_entry_sha256",
            "lowering_route",
            "lowering_schema_version",
            "configuration_payload_digests",
            "configuration_revisions",
        }:
            raise ValueError("normalized program identity has an invalid shape")
        if (
            (normalized_program_identity or {}).get("schema_version")
            != "workflow_lisp_program_identity.v1"
        ):
            raise ValueError("normalized program identity version is invalid")
        identity = dict(normalized_program_identity or {})
        identity_digest = identity.pop("digest", None)
        if identity_digest != canonical_sha256(identity):
            raise ValueError("normalized program identity digest is invalid")
        try:
            rebuilt_identity = build_normalized_program_identity(
                compiler_runtime_identity=identity.get(
                    "compiler_runtime_identity"
                ),
                module_source_revisions=identity.get(
                    "module_source_revisions", ()
                ),
                compiler_source_revisions=identity.get(
                    "compiler_source_revisions", ()
                ),
                imported_bundle_bindings=identity.get(
                    "imported_bundle_bindings", ()
                ),
                selected_entry=selected_entry_value,
                lowering_route=identity.get("lowering_route"),
                lowering_schema_version=identity.get(
                    "lowering_schema_version"
                ),
                configuration_payload_digests=identity.get(
                    "configuration_payload_digests", {}
                ),
                configuration_revisions=identity.get(
                    "configuration_revisions", ()
                ),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(
                "normalized program identity has an invalid nested shape"
            ) from exc
        if rebuilt_identity != normalized_program_identity:
            raise ValueError("normalized program identity payload is not canonical")

    payload: dict[str, object] = {
        "schema_version": "workflow_lisp_compile_diagnostics.v1",
        "status": status,
    }
    if status == "accepted":
        payload["selected_entry"] = selected_entry_value
        payload["normalized_program_identity"] = _canonical_json_value(
            normalized_program_identity
        )
    payload["diagnostics"] = serialize_diagnostics(diagnostics)
    return payload


def capture_frontend_diagnostic_identities(
    diagnostics: Iterable[LispFrontendDiagnostic],
) -> tuple[tuple[object, ...], ...]:
    """Capture the ordered post-metadata compiler identity of diagnostics."""

    return tuple(
        _capture_frontend_diagnostic_identity(diagnostic)
        for diagnostic in diagnostics
    )


def _capture_frontend_diagnostic_identity(
    diagnostic: LispFrontendDiagnostic,
) -> tuple[object, ...]:
    classified = with_diagnostic_metadata(diagnostic)
    return (
        classified.code,
        (
            diagnostic.diagnostic_kind
            if diagnostic.diagnostic_kind is not None
            else classified.diagnostic_kind
        ),
        (
            diagnostic.severity
            if diagnostic.severity is not None
            else classified.severity or "error"
        ),
        (
            diagnostic.phase
            if diagnostic.phase is not None
            else classified.phase
        ),
        (
            diagnostic.validation_pass
            if diagnostic.validation_pass is not None
            else classified.validation_pass
        ),
        (
            diagnostic.authority_layer
            if diagnostic.authority_layer is not None
            else classified.authority_layer
        ),
        _capture_source_span_identity(diagnostic.span, nullable=False),
        diagnostic.form_path,
        tuple(
            _capture_expansion_frame_identity(frame)
            for frame in diagnostic.expansion_stack
        ),
    )


def _capture_source_span_identity(
    span: SourceSpan | None,
    *,
    nullable: bool,
) -> tuple[object, ...] | None:
    if span is None:
        if nullable:
            return None
        raise TypeError(
            "frontend diagnostic identity requires a non-null SourceSpan"
        )
    if not isinstance(span, SourceSpan):
        raise TypeError(
            "frontend diagnostic identity requires a SourceSpan or None"
        )
    return (
        str(Path(span.start.path).resolve(strict=False)),
        _capture_source_position_identity(span.start),
        _capture_source_position_identity(span.end),
    )


def _capture_source_position_identity(
    position: SourcePosition,
) -> tuple[int, int, int]:
    if not isinstance(position, SourcePosition):
        raise TypeError(
            "frontend diagnostic identity requires SourcePosition values"
        )
    return (position.line, position.column, position.offset)


def _capture_expansion_frame_identity(frame: object) -> tuple[object, ...]:
    missing = object()
    macro_name = getattr(frame, "macro_name", missing)
    function_name = getattr(frame, "function_name", missing)
    has_macro_name = isinstance(macro_name, str) and bool(macro_name)
    has_function_name = isinstance(function_name, str) and bool(function_name)
    if has_macro_name == has_function_name:
        raise TypeError(
            "frontend diagnostic identity requires exactly one valid "
            "macro_name or function_name"
        )
    call_span = getattr(frame, "call_span", missing)
    definition_span = getattr(frame, "definition_span", missing)
    if call_span is missing or definition_span is missing:
        raise TypeError(
            "frontend diagnostic identity requires call_span and "
            "definition_span frame fields"
        )
    if has_macro_name:
        expansion_id = getattr(frame, "expansion_id", missing)
        if expansion_id is missing or not (
            expansion_id is None or isinstance(expansion_id, str)
        ):
            raise TypeError(
                "frontend diagnostic macro frame requires a nullable "
                "string expansion_id"
            )
        return (
            "macro",
            macro_name,
            expansion_id,
            _capture_source_span_identity(call_span, nullable=True),
            _capture_source_span_identity(definition_span, nullable=True),
        )
    helper_expansion_id = getattr(frame, "expansion_id", None)
    if helper_expansion_id is not None:
        raise TypeError(
            "frontend diagnostic helper frame cannot carry an expansion_id"
        )
    return (
        "helper",
        function_name,
        None,
        _capture_source_span_identity(call_span, nullable=True),
        _capture_source_span_identity(definition_span, nullable=True),
    )


def _render_expansion_notes(expansion_stack: tuple[object, ...]) -> tuple[str, ...]:
    notes: list[str] = []
    for frame in expansion_stack:
        macro_name = getattr(frame, "macro_name", None)
        function_name = getattr(frame, "function_name", None)
        expansion_id = getattr(frame, "expansion_id", None)
        call_span = getattr(frame, "call_span", None)
        definition_span = getattr(frame, "definition_span", None)
        if call_span is None or definition_span is None:
            continue
        call_location = (
            f"{call_span.start.path}:{call_span.start.line}:{call_span.start.column}"
        )
        definition_location = (
            f"{definition_span.start.path}:{definition_span.start.line}:{definition_span.start.column}"
        )
        if macro_name is not None:
            if expansion_id:
                notes.append(
                    f"expanded from macro `{macro_name}` call at {call_location} ({expansion_id})"
                )
            else:
                notes.append(f"expanded from macro `{macro_name}` call at {call_location}")
            notes.append(f"macro definition at {definition_location}")
            continue
        if function_name is not None:
            notes.append(f"helper call site at {call_location} (`{function_name}`)")
            notes.append(f"helper definition at {definition_location}")
    return tuple(notes)


def _serialize_expansion_frame(frame: object) -> dict[str, object]:
    call_span = getattr(frame, "call_span", None)
    definition_span = getattr(frame, "definition_span", None)
    payload: dict[str, object] = {
        "macro_name": getattr(frame, "macro_name", None),
        "function_name": getattr(frame, "function_name", None),
        "expansion_id": getattr(frame, "expansion_id", None),
    }
    if call_span is not None:
        payload["call"] = {
            "path": call_span.start.path,
            "line": call_span.start.line,
            "column": call_span.start.column,
        }
    if definition_span is not None:
        payload["definition"] = {
            "path": definition_span.start.path,
            "line": definition_span.start.line,
            "column": definition_span.start.column,
        }
    return payload


def _infer_phase(code: str) -> str:
    validation_pass = _infer_validation_pass(code, None)
    return _VALIDATION_PASS_TO_PHASE.get(validation_pass, "read")


def validation_pass_order_key(pass_id: str) -> int:
    """Return the stable ordering index for one validation pass id."""

    return _VALIDATION_PASS_ORDER_INDEX.get(pass_id, len(_VALIDATION_PASS_ORDER_INDEX))


def with_diagnostic_metadata(
    diagnostic: LispFrontendDiagnostic,
    *,
    validation_pass: str | None = None,
    authority_layer: str | None = None,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> LispFrontendDiagnostic:
    """Return a diagnostic with canonical validation metadata attached."""

    diagnostic = _normalize_legacy_diagnostic_code(diagnostic)
    resolved_pass = validation_pass or diagnostic.validation_pass or _infer_validation_pass(
        diagnostic.code,
        diagnostic.phase,
    )
    resolved_phase = diagnostic.phase
    if resolved_phase != "cli_request":
        resolved_phase = _VALIDATION_PASS_TO_PHASE.get(resolved_pass, resolved_phase or _infer_phase(diagnostic.code))
    resolved_authority_layer = authority_layer or diagnostic.authority_layer
    if resolved_authority_layer is None:
        rule = required_lint_rule(diagnostic.code)
        if rule is not None:
            resolved_authority_layer = rule.authority_layer
        elif resolved_pass == "shared_validation":
            resolved_authority_layer = "shared_validation"
        elif resolved_pass == "semantic_ir":
            resolved_authority_layer = "shared"
        else:
            resolved_authority_layer = "frontend"
    resolved_kind = diagnostic.diagnostic_kind
    if resolved_kind is None:
        resolved_kind = "required_lint" if is_required_lint_code(diagnostic.code) else "validation"
    resolved_severity = diagnostic.severity
    if resolved_severity is None:
        resolved_severity = required_lint_severity(
            diagnostic.code,
            lint_profile=lint_profile,
        )
    return replace(
        diagnostic,
        diagnostic_kind=resolved_kind,
        severity=resolved_severity,
        phase=resolved_phase,
        validation_pass=resolved_pass,
        authority_layer=resolved_authority_layer,
    )


def _normalize_legacy_diagnostic_code(
    diagnostic: LispFrontendDiagnostic,
) -> LispFrontendDiagnostic:
    if diagnostic.code == "macro_has_effect":
        return replace(diagnostic, code="macro_hidden_effect")
    if diagnostic.code in {
        "provider_effect_hidden",
        "command_effect_hidden",
        "state_update_hidden",
    } and diagnostic.expansion_stack:
        return replace(diagnostic, code="macro_hidden_effect")
    return diagnostic


def diagnostic_effective_severity(
    diagnostic: LispFrontendDiagnostic,
    *,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> str:
    """Return the effective severity for one diagnostic under a lint profile."""

    return with_diagnostic_metadata(
        diagnostic,
        lint_profile=lint_profile,
    ).severity or "error"


def _infer_validation_pass(code: str, phase: str | None) -> str:
    if phase == "cli_request":
        return "module"
    rule = required_lint_rule(code)
    if rule is not None:
        return rule.owning_pass
    if code in _SHARED_VALIDATION_CODES:
        if code == "semantic_ir_invalid":
            return "semantic_ir"
        return "shared_validation"
    if code in _EXECUTABLE_CODES:
        return "executable"
    if code.startswith("source_map_") or code in _SOURCE_MAP_CODES:
        return "source_map"
    if code.startswith("macro_"):
        return "macro"
    if code.startswith("frontend_parse"):
        return "parse"
    if code == "command_result_adapter_invalid":
        return "parse"
    if code in _MODULE_CODES or code.startswith("module_"):
        return "module"
    if code in _AUTHORITY_CODES:
        return "authority"
    if code == "stdlib_special_form_disallowed":
        return "contract"
    if code.startswith("workflow_ref_"):
        return "reference"
    if code in _EFFECT_CODES:
        return "effect"
    if (
        code in _TYPE_CODES
        or code in _RUNTIME_CLOSURE_TYPE_CODES
        or code.startswith("type_")
        or code.startswith("provider_result_")
        or code.startswith("command_result_")
    ):
        return "type"
    if code.startswith("variant_"):
        return "proof"
    if code in _LOWERING_SURFACE_CODES:
        return "lowering_surface"
    if phase in _PHASE_TO_VALIDATION_PASS:
        return _PHASE_TO_VALIDATION_PASS[phase]
    return "parse"
