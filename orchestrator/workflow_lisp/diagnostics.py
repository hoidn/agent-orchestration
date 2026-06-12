"""Typed diagnostics and rendering helpers for the workflow Lisp frontend."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .lints import (
    LINT_PROFILE_DEFAULT,
    is_required_lint_code,
    required_lint_rule,
    required_lint_severity,
)
from .spans import SourceSpan


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


class LispFrontendCompileError(Exception):
    """Raised when Workflow Lisp compilation accumulates diagnostics."""

    def __init__(self, diagnostics: tuple[LispFrontendDiagnostic, ...]):
        self.diagnostics = diagnostics
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
    return {
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
