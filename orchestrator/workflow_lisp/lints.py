"""Required-lint registry and severity policy for the Workflow Lisp frontend."""

from __future__ import annotations

from dataclasses import dataclass


LINT_PROFILE_DEFAULT = "default"
LINT_PROFILE_STRICT = "strict"
_KNOWN_LINT_PROFILES = frozenset({LINT_PROFILE_DEFAULT, LINT_PROFILE_STRICT})


@dataclass(frozen=True)
class RequiredLintRule:
    """One required-lint rule and its stable policy metadata."""

    code: str
    summary: str
    owning_pass: str
    authority_layer: str
    default_severity: str
    strict_severity: str
    surface_status: str
    primary_surface: str
    replacement_hint: str | None = None


REQUIRED_LINT_REGISTRY: dict[str, RequiredLintRule] = {
    "low_level_state_path_in_high_level_module": RequiredLintRule(
        code="low_level_state_path_in_high_level_module",
        summary="manual low-level state paths should use derived context/layout helpers",
        owning_pass="contract",
        authority_layer="frontend",
        default_severity="warn",
        strict_severity="error",
        surface_status="active",
        primary_surface="typed_ast",
        replacement_hint="derive state paths from phase or item context helpers",
    ),
    "semantic_field_extracted_from_report": RequiredLintRule(
        code="semantic_field_extracted_from_report",
        summary="semantic fields must not be extracted from markdown reports",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="command_boundary",
        replacement_hint="emit structured state instead of parsing reports",
    ),
    "markdown_report_used_as_state": RequiredLintRule(
        code="markdown_report_used_as_state",
        summary="markdown reports are views and cannot be semantic state",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="lowered_surface",
        replacement_hint="move semantic data into structured bundles or typed artifacts",
    ),
    "variant_output_without_variant_specific_fields": RequiredLintRule(
        code="variant_output_without_variant_specific_fields",
        summary="union outputs without variant-specific fields should become a record plus enum",
        owning_pass="contract",
        authority_layer="frontend",
        default_severity="warn",
        strict_severity="error",
        surface_status="active",
        primary_surface="typed_ast",
        replacement_hint="replace the union with a record that carries the discriminant",
    ),
    "pointer_used_as_semantic_authority": RequiredLintRule(
        code="pointer_used_as_semantic_authority",
        summary="pointer files are representations and cannot be semantic authority",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="lowered_surface",
        replacement_hint="use artifact values or structured bundles as authority",
    ),
    "materialized_view_used_as_semantic_authority": RequiredLintRule(
        code="materialized_view_used_as_semantic_authority",
        summary="materialized views are representations and cannot be semantic authority",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="typed_ast",
        replacement_hint="use canonical state bundles or structured values as authority",
    ),
    "resource_move_without_transition": RequiredLintRule(
        code="resource_move_without_transition",
        summary="resource movement must use resource-transition or a certified adapter",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="command_boundary",
        replacement_hint="use resource-transition or declare a certified resource_transition adapter",
    ),
    "recovery_gate_without_resume_or_start": RequiredLintRule(
        code="recovery_gate_without_resume_or_start",
        summary="reusable-state gating must use resume-or-start or a certified adapter",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="command_boundary",
        replacement_hint="use resume-or-start or declare a certified resume_state_reuse adapter",
    ),
    "workflow_call_signature_erased": RequiredLintRule(
        code="workflow_call_signature_erased",
        summary="compile-time workflow references must preserve their typed workflow signatures",
        owning_pass="reference",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="workflow_ref",
        replacement_hint="preserve typed compile-time workflow references instead of erasing them to opaque runtime handles",
    ),
    "macro_hidden_effect": RequiredLintRule(
        code="macro_hidden_effect",
        summary="macros cannot hide workflow effects",
        owning_pass="effect",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="macro",
        replacement_hint="surface the effect through typed workflow or procedure forms",
    ),
    "interior_publication": RequiredLintRule(
        code="interior_publication",
        summary="non-entry promoted workflows must not keep authored body-level materialize-view publication",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="typed_ast",
        replacement_hint="move durable publication to entry-boundary `:publish` or keep it as an explicitly timed publication outside C3",
    ),
    "command_adapter_missing_contract": RequiredLintRule(
        code="command_adapter_missing_contract",
        summary="workflow-semantic commands require certified adapter metadata",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="command_boundary",
        replacement_hint="declare a certified adapter contract with fixtures and typed outputs",
    ),
    "inline_python_command_in_workflow": RequiredLintRule(
        code="inline_python_command_in_workflow",
        summary="inline Python command glue is not allowed in high-level workflows",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="command_boundary",
        replacement_hint="use a certified adapter or external tool binding",
    ),
    "inline_shell_command_in_workflow": RequiredLintRule(
        code="inline_shell_command_in_workflow",
        summary="inline shell command glue is not allowed in high-level workflows",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="command_boundary",
        replacement_hint="use a certified adapter or external tool binding",
    ),
    "legacy_adapter_missing_fixture": RequiredLintRule(
        code="legacy_adapter_missing_fixture",
        summary="legacy adapters require positive and negative fixtures",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="active",
        primary_surface="command_boundary",
        replacement_hint="declare positive and negative adapter fixtures",
    ),
    "manual_snapshot_name_in_high_level_module": RequiredLintRule(
        code="manual_snapshot_name_in_high_level_module",
        summary="manual snapshot names are reserved policy metadata until the authored surface exists",
        owning_pass="contract",
        authority_layer="frontend",
        default_severity="warn",
        strict_severity="error",
        surface_status="reserved",
        primary_surface="typed_ast",
        replacement_hint="let lowering own snapshot naming",
    ),
    "manual_candidate_path_in_high_level_module": RequiredLintRule(
        code="manual_candidate_path_in_high_level_module",
        summary="manual candidate paths are reserved policy metadata until the authored surface exists",
        owning_pass="contract",
        authority_layer="frontend",
        default_severity="warn",
        strict_severity="error",
        surface_status="reserved",
        primary_surface="typed_ast",
        replacement_hint="let lowering own candidate-path materialization",
    ),
    "line_prefix_extractor_in_workflow": RequiredLintRule(
        code="line_prefix_extractor_in_workflow",
        summary="line-prefix report extraction is reserved until an explicit authored surface exists",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="reserved",
        primary_surface="command_boundary",
        replacement_hint="move semantic state into structured outputs",
    ),
    "manual_when_requires_variant_pair": RequiredLintRule(
        code="manual_when_requires_variant_pair",
        summary="manual variant gating is reserved until authored conditional surfaces exist",
        owning_pass="proof",
        authority_layer="frontend",
        default_severity="warn",
        strict_severity="error",
        surface_status="reserved",
        primary_surface="typed_ast",
        replacement_hint="use match or another proof-carrying surface",
    ),
    "string_status_gate_without_union_match": RequiredLintRule(
        code="string_status_gate_without_union_match",
        summary="string status gates are reserved until authored string-gate surfaces exist",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="reserved",
        primary_surface="typed_ast",
        replacement_hint="use a tagged union and match over the discriminant",
    ),
    "inline_json_state_rewrite": RequiredLintRule(
        code="inline_json_state_rewrite",
        summary="inline JSON state rewrites are reserved until a structural detection surface exists",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="reserved",
        primary_surface="command_boundary",
        replacement_hint="use structured bundle contracts instead of ad hoc rewrites",
    ),
    "inline_pointer_write": RequiredLintRule(
        code="inline_pointer_write",
        summary="inline pointer writes are reserved until a structural detection surface exists",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="reserved",
        primary_surface="command_boundary",
        replacement_hint="use materialized artifacts owned by lowering or runtime helpers",
    ),
    "inline_subprocess_nested_command": RequiredLintRule(
        code="inline_subprocess_nested_command",
        summary="nested subprocess launching is reserved until explicit command metadata exposes it",
        owning_pass="authority",
        authority_layer="frontend",
        default_severity="error",
        strict_severity="error",
        surface_status="reserved",
        primary_surface="command_boundary",
        replacement_hint="declare the real command boundary directly",
    ),
}


def validate_lint_profile(lint_profile: str) -> str:
    """Return one supported lint profile or raise for invalid values."""

    if lint_profile not in _KNOWN_LINT_PROFILES:
        raise ValueError(
            f"unsupported lint profile `{lint_profile}`; expected one of {sorted(_KNOWN_LINT_PROFILES)!r}"
        )
    return lint_profile


def required_lint_rule(code: str) -> RequiredLintRule | None:
    """Return policy metadata for one required-lint code, if registered."""

    return REQUIRED_LINT_REGISTRY.get(code)


def is_required_lint_code(code: str) -> bool:
    """Return whether one diagnostic code is a frontend required lint."""

    return code in REQUIRED_LINT_REGISTRY


def required_lint_severity(code: str, *, lint_profile: str = LINT_PROFILE_DEFAULT) -> str | None:
    """Return the effective severity for one required lint under a profile."""

    rule = required_lint_rule(code)
    if rule is None:
        return None
    validate_lint_profile(lint_profile)
    if lint_profile == LINT_PROFILE_STRICT:
        return rule.strict_severity
    return rule.default_severity


def serialize_required_lint_registry() -> list[dict[str, str]]:
    """Serialize the required-lint registry as stable policy metadata."""

    return [
        {
            "code": rule.code,
            "owning_pass": rule.owning_pass,
            "authority_layer": rule.authority_layer,
            "default_severity": rule.default_severity,
            "strict_severity": rule.strict_severity,
            "surface_status": rule.surface_status,
        }
        for rule in REQUIRED_LINT_REGISTRY.values()
    ]


def required_lint_diagnostic(
    code: str,
    *,
    message: str,
    span: object,
    form_path: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    expansion_stack: tuple[object, ...] = (),
) -> object:
    """Construct one required-lint diagnostic with stable metadata attached."""

    rule = required_lint_rule(code)
    if rule is None:
        raise KeyError(f"unknown required-lint code `{code}`")
    from .diagnostics import LispFrontendDiagnostic

    return LispFrontendDiagnostic(
        code=code,
        message=message,
        span=span,
        diagnostic_kind="required_lint",
        form_path=form_path,
        notes=notes,
        expansion_stack=expansion_stack,
        validation_pass=rule.owning_pass,
        authority_layer=rule.authority_layer,
    )
