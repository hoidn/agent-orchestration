"""Frontend-local phase scope helpers for generic and legacy phase scopes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .definitions import PathDef
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .type_env import (
    FrontendTypeEnvironment,
    PRELUDE_PATH_TYPES,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
)


RUN_CONTEXT_NAME = "RunCtx"
PHASE_CONTEXT_NAME = "PhaseCtx"
IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME = "ImplementationAttemptPhaseCtx"
IMPLEMENTATION_ATTEMPT_PHASE_NAME = "implementation"
IMPLEMENTATION_ATTEMPT_RESULT_NAME = "ImplementationAttempt"
IMPLEMENTATION_ATTEMPT_ARTIFACT_ROOT = "artifacts/work"
IMPLEMENTATION_STATE_BUNDLE_FIELD = "implementation_state_bundle_path"
IMPLEMENTATION_ATTEMPT_TARGET_FIELDS = {
    "execution-report": "execution_report_target",
    "progress-report": "progress_report_target",
}
PHASE_TARGET_SPECS = {
    "execution-report": ("WorkReportTarget", "artifacts/work", "execution-report.md"),
    "progress-report": ("WorkReportTarget", "artifacts/work", "progress-report.md"),
    "checks-report": ("ChecksReport", "artifacts/work", "checks-report.md"),
    "review-report": ("ReviewReport", "artifacts/work", "review-report.md"),
    "last-review-report": ("ReviewReport", "artifacts/work", "last-review-report.md"),
}


@dataclass(frozen=True)
class PhaseLayout:
    """Derived paths and target refs for one scoped workflow phase."""

    phase_name: str
    state_root_ref: str
    artifact_root_ref: str
    state_bundle_path: str
    temp_bundle_path: str
    snapshot_root: str
    candidate_root: str
    target_refs: Mapping[str, str]


@dataclass(frozen=True)
class PhaseScope:
    """Validated phase context plus target names available inside `with-phase`."""

    context_record_name: str
    phase_name: str
    bundle_path_field: str | None = None
    target_fields: Mapping[str, str] = field(default_factory=dict)
    target_types: Mapping[str, PathTypeRef] = field(default_factory=dict)
    uses_legacy_bridge: bool = False


def is_implementation_attempt_result_type(type_ref: TypeRef) -> bool:
    """Return whether the type is the supported implementation-attempt union."""

    return isinstance(type_ref, UnionTypeRef) and type_ref.name == IMPLEMENTATION_ATTEMPT_RESULT_NAME


def build_phase_scope(
    type_ref: TypeRef,
    *,
    phase_name: str,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> PhaseScope:
    """Validate one authored phase context and build its scope."""

    if isinstance(type_ref, RecordTypeRef) and type_ref.name == IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME:
        return build_implementation_attempt_phase_scope(
            type_ref,
            phase_name=phase_name,
            type_env=type_env,
            span=span,
            form_path=form_path,
        )

    if not isinstance(type_ref, RecordTypeRef) or type_ref.name != PHASE_CONTEXT_NAME:
        _raise_error(
            code="phase_context_invalid",
            message="`with-phase` requires a `PhaseCtx` value or the bounded legacy implementation bridge",
            span=span,
            form_path=form_path,
        )

    _require_record_field_type(
        type_ref,
        "run",
        expected_record_name=RUN_CONTEXT_NAME,
        type_env=type_env,
        span=span,
        form_path=form_path,
    )
    run_type = type_env.record_field(type_ref, "run", span=span, form_path=form_path)
    assert isinstance(run_type, RecordTypeRef)
    _require_primitive_field_type(
        run_type,
        "run-id",
        expected_name="RunId",
        type_env=type_env,
        span=span,
        form_path=form_path,
    )
    _require_path_field(
        run_type,
        "state-root",
        type_env=type_env,
        span=span,
        form_path=form_path,
        expected_under="state",
        expected_must_exist=False,
    )
    _require_path_field(
        run_type,
        "artifact-root",
        type_env=type_env,
        span=span,
        form_path=form_path,
        expected_under="artifacts",
        expected_must_exist=False,
    )
    _require_primitive_field_type(
        type_ref,
        "phase-name",
        expected_name="Symbol",
        type_env=type_env,
        span=span,
        form_path=form_path,
    )
    _require_path_field(
        type_ref,
        "state-root",
        type_env=type_env,
        span=span,
        form_path=form_path,
        expected_under="state",
        expected_must_exist=False,
    )
    _require_path_field(
        type_ref,
        "artifact-root",
        type_env=type_env,
        span=span,
        form_path=form_path,
        expected_under="artifacts",
        expected_must_exist=False,
    )

    return PhaseScope(
        context_record_name=type_ref.name,
        phase_name=phase_name,
        target_types={
            target_name: _build_phase_target_type(phase_name=phase_name, target_name=target_name)
            for target_name in PHASE_TARGET_SPECS
        },
    )


def build_implementation_attempt_phase_scope(
    type_ref: RecordTypeRef,
    *,
    phase_name: str,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> PhaseScope:
    """Validate the legacy implementation-attempt phase context and build its scope."""

    if phase_name != IMPLEMENTATION_ATTEMPT_PHASE_NAME:
        _raise_error(
            code="phase_context_invalid",
            message="`with-phase` supports only the `implementation` phase in this bounded slice",
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
        uses_legacy_bridge=True,
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

    target_type = phase_scope.target_types.get(target_name)
    if target_type is not None:
        resolved_named_type = type_env.resolve_type(
            target_type.name,
            span=span,
            form_path=form_path,
        )
        if (
            isinstance(resolved_named_type, PathTypeRef)
            and resolved_named_type.definition.under == target_type.definition.under
            and resolved_named_type.definition.must_exist is target_type.definition.must_exist
        ):
            return resolved_named_type
        return target_type

    field_name = phase_scope.target_fields.get(target_name)
    if field_name is None:
        _raise_error(
            code="phase_target_unknown" if phase_scope.uses_legacy_bridge else "phase_target_contract_unresolved",
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


def _require_record_field_type(
    record_type: RecordTypeRef,
    field_name: str,
    *,
    expected_record_name: str,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    field_type = type_env.record_field(record_type, field_name, span=span, form_path=form_path)
    if not isinstance(field_type, RecordTypeRef) or field_type.name != expected_record_name:
        _raise_error(
            code="phase_context_invalid",
            message=f"`{record_type.name}.{field_name}` must be `{expected_record_name}`",
            span=span,
            form_path=form_path,
        )


def _require_primitive_field_type(
    record_type: RecordTypeRef,
    field_name: str,
    *,
    expected_name: str,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    field_type = type_env.record_field(record_type, field_name, span=span, form_path=form_path)
    if field_type != PrimitiveTypeRef(name=expected_name):
        _raise_error(
            code="phase_context_invalid",
            message=f"`{record_type.name}.{field_name}` must be `{expected_name}`",
            span=span,
            form_path=form_path,
        )


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
                "for the active phase scope"
            ),
            span=span,
            form_path=form_path,
        )
    if field_type.definition.under != expected_under or field_type.definition.must_exist is not expected_must_exist:
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


def _build_phase_target_type(*, phase_name: str, target_name: str) -> PathTypeRef:
    type_name, under_root, preferred_suffix = PHASE_TARGET_SPECS[target_name]
    return PathTypeRef(
        name=type_name,
        definition=PathDef(
            name=type_name,
            kind="relpath",
            under=under_root,
            must_exist=False,
            span=PRELUDE_PATH_TYPES["Path.artifact-root"].span,
        ),
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
