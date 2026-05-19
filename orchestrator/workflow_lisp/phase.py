"""Frontend-local phase scope helpers for the bounded Stage 4 slice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .type_env import FrontendTypeEnvironment, PathTypeRef, RecordTypeRef, TypeRef, UnionTypeRef


IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME = "ImplementationAttemptPhaseCtx"
IMPLEMENTATION_ATTEMPT_PHASE_NAME = "implementation"
IMPLEMENTATION_ATTEMPT_RESULT_NAME = "ImplementationAttempt"
IMPLEMENTATION_ATTEMPT_ARTIFACT_ROOT = "artifacts/work"
IMPLEMENTATION_STATE_BUNDLE_FIELD = "implementation_state_bundle_path"
IMPLEMENTATION_ATTEMPT_TARGET_FIELDS = {
    "execution-report": "execution_report_target",
    "progress-report": "progress_report_target",
}


@dataclass(frozen=True)
class PhaseScope:
    context_record_name: str
    phase_name: str
    bundle_path_field: str
    target_fields: Mapping[str, str]


def is_implementation_attempt_result_type(type_ref: TypeRef) -> bool:
    """Return whether the type is the bounded phase-scoped implementation-attempt union."""

    return isinstance(type_ref, UnionTypeRef) and type_ref.name == IMPLEMENTATION_ATTEMPT_RESULT_NAME


def build_implementation_attempt_phase_scope(
    type_ref: TypeRef,
    *,
    phase_name: str,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> PhaseScope:
    """Validate the bounded implementation-attempt phase context and build its scope."""

    if phase_name != IMPLEMENTATION_ATTEMPT_PHASE_NAME:
        _raise_error(
            code="phase_context_invalid",
            message="`with-phase` supports only the `implementation` phase in this bounded slice",
            span=span,
            form_path=form_path,
        )

    if not isinstance(type_ref, RecordTypeRef) or type_ref.name != IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME:
        _raise_error(
            code="phase_context_invalid",
            message=(
                "`with-phase` requires an `ImplementationAttemptPhaseCtx` value "
                "for the bounded implementation-attempt slice"
            ),
            span=span,
            form_path=form_path,
        )

    _require_path_field(
        type_ref,
        IMPLEMENTATION_STATE_BUNDLE_FIELD,
        type_env=type_env,
        span=span,
        form_path=form_path,
        expected_under=IMPLEMENTATION_ATTEMPT_ARTIFACT_ROOT,
        expected_must_exist=False,
    )
    for field_name in IMPLEMENTATION_ATTEMPT_TARGET_FIELDS.values():
        _require_path_field(
            type_ref,
            field_name,
            type_env=type_env,
            span=span,
            form_path=form_path,
            expected_under=IMPLEMENTATION_ATTEMPT_ARTIFACT_ROOT,
            expected_must_exist=False,
        )

    return PhaseScope(
        context_record_name=type_ref.name,
        phase_name=phase_name,
        bundle_path_field=IMPLEMENTATION_STATE_BUNDLE_FIELD,
        target_fields=IMPLEMENTATION_ATTEMPT_TARGET_FIELDS,
    )


def resolve_phase_target_type(
    phase_scope: PhaseScope,
    target_name: str,
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    """Resolve one approved phase target to its relpath type."""

    field_name = phase_scope.target_fields.get(target_name)
    if field_name is None:
        _raise_error(
            code="phase_target_unknown",
            message=f"`phase-target` does not support `{target_name}` in this slice",
            span=span,
            form_path=form_path,
        )
    context_type = type_env.resolve_type(
        phase_scope.context_record_name,
        span=span,
        form_path=form_path,
    )
    if not isinstance(context_type, RecordTypeRef):
        raise TypeError(f"phase scope context `{phase_scope.context_record_name}` must resolve to a record type")
    return type_env.record_field(context_type, field_name, span=span, form_path=form_path)


def _require_path_field(
    record_type: RecordTypeRef,
    field_name: str,
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expected_under: str,
    expected_must_exist: bool,
) -> None:
    field_type = type_env.record_field(record_type, field_name, span=span, form_path=form_path)
    if not isinstance(field_type, PathTypeRef):
        _raise_error(
            code="phase_context_invalid",
            message=(
                f"`{record_type.name}.{field_name}` must be a relpath contract "
                "for the bounded implementation-attempt phase scope"
            ),
            span=span,
            form_path=form_path,
        )
    if (
        field_type.definition.under != expected_under
        or field_type.definition.must_exist is not expected_must_exist
    ):
        must_exist_label = "true" if expected_must_exist else "false"
        _raise_error(
            code="phase_context_invalid",
            message=(
                f"`{record_type.name}.{field_name}` must be a relpath contract "
                f"under `{expected_under}` with `:must-exist {must_exist_label}`"
            ),
            span=span,
            form_path=form_path,
        )


def _raise_error(*, code: str, message: str, span: SourceSpan, form_path: tuple[str, ...]) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
            ),
        )
    )
