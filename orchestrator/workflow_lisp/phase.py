"""Frontend-local phase scope helpers for generic and legacy phase scopes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from .workflows import WorkflowSignature


RUN_CONTEXT_NAME = "RunCtx"
PHASE_CONTEXT_NAME = "PhaseCtx"
ITEM_CONTEXT_NAME = "ItemCtx"
DRAIN_CONTEXT_NAME = "DrainCtx"
SELECTION_CONTEXT_NAME = "SelectionCtx"
RECOVERY_CONTEXT_NAME = "RecoveryCtx"
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
    "review-report": ("ReviewReportTarget", "artifacts/review", "review-report.md"),
    "last-review-report": ("ReviewReportTarget", "artifacts/review", "last-review-report.md"),
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


@dataclass(frozen=True)
class PromotedEntryHiddenContextRequirement:
    """Compiler-owned hidden context binding metadata for promoted-entry callers."""

    param_name: str
    context_kind: str
    phase_name: str | None = None


def private_exec_context_capabilities(context_kind: str) -> tuple[str, ...]:
    """Return the capability tags required for one private executable context family."""

    return {
        RUN_CONTEXT_NAME: ("run",),
        PHASE_CONTEXT_NAME: ("run", "phase"),
        ITEM_CONTEXT_NAME: ("run", "item"),
        DRAIN_CONTEXT_NAME: ("run", "drain"),
        SELECTION_CONTEXT_NAME: ("selection",),
        RECOVERY_CONTEXT_NAME: ("recovery",),
    }.get(context_kind, ())


def private_exec_context_bootstrap_supported(context_kind: str) -> bool:
    """Return whether the current runtime can bootstrap one context family."""

    return context_kind in {RUN_CONTEXT_NAME, PHASE_CONTEXT_NAME}


def private_exec_context_kind(type_ref: TypeRef) -> str | None:
    """Classify one record boundary by private executable context family."""

    if _is_run_context_shape(type_ref):
        return RUN_CONTEXT_NAME
    if _is_phase_context_shape(type_ref):
        return PHASE_CONTEXT_NAME
    if _is_item_context_shape(type_ref):
        return ITEM_CONTEXT_NAME
    if _is_drain_context_shape(type_ref):
        return DRAIN_CONTEXT_NAME
    if _is_selection_context_shape(type_ref):
        return SELECTION_CONTEXT_NAME
    if _is_recovery_context_shape(type_ref):
        return RECOVERY_CONTEXT_NAME
    return None


def is_implementation_attempt_result_type(type_ref: TypeRef) -> bool:
    """Return whether the type is the supported implementation-attempt union."""

    return isinstance(type_ref, UnionTypeRef) and type_ref.name == IMPLEMENTATION_ATTEMPT_RESULT_NAME


def _record_definition_name(type_ref: RecordTypeRef) -> str:
    """Return the authored record name before import canonicalization."""

    return type_ref.definition.name


def is_record_definition_named(type_ref: TypeRef, expected_name: str) -> bool:
    """Return whether a record ref's authored definition has the expected name."""

    return isinstance(type_ref, RecordTypeRef) and _record_definition_name(type_ref) == expected_name


def build_phase_scope(
    type_ref: TypeRef,
    *,
    phase_name: str,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> PhaseScope:
    """Validate one authored phase context and build its scope."""

    if is_record_definition_named(type_ref, IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME):
        assert isinstance(type_ref, RecordTypeRef)
        return build_implementation_attempt_phase_scope(
            type_ref,
            phase_name=phase_name,
            type_env=type_env,
            span=span,
            form_path=form_path,
        )

    if not is_record_definition_named(type_ref, PHASE_CONTEXT_NAME):
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
        try:
            resolved_named_type = type_env.resolve_type(
                target_type.name,
                span=span,
                form_path=form_path,
            )
        except LispFrontendCompileError as exc:
            if any(diagnostic.code != "type_unknown" for diagnostic in exc.diagnostics):
                raise
            return target_type
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


def derive_promoted_entry_hidden_context_metadata(
    signature: "WorkflowSignature",
    body_expr: Any,
) -> tuple[
    Mapping[str, PromotedEntryHiddenContextRequirement],
    Mapping[str, tuple[str, ...]],
]:
    """Derive hidden-context eligibility metadata from one typed workflow body."""

    requirements: dict[str, PromotedEntryHiddenContextRequirement] = {}
    ambiguities: dict[str, tuple[str, ...]] = {}
    for param_name, type_ref in signature.params:
        context_kind = private_exec_context_kind(type_ref)
        if context_kind == RUN_CONTEXT_NAME:
            requirements[param_name] = PromotedEntryHiddenContextRequirement(
                param_name=param_name,
                context_kind=RUN_CONTEXT_NAME,
            )
            continue
        if context_kind != PHASE_CONTEXT_NAME:
            if context_kind is not None:
                requirements[param_name] = PromotedEntryHiddenContextRequirement(
                    param_name=param_name,
                    context_kind=context_kind,
                )
            continue
        phase_names = tuple(sorted(_collect_with_phase_names(body_expr, ctx_name=param_name)))
        if len(phase_names) == 1:
            requirements[param_name] = PromotedEntryHiddenContextRequirement(
                param_name=param_name,
                context_kind=PHASE_CONTEXT_NAME,
                phase_name=phase_names[0],
            )
        elif len(phase_names) > 1:
            ambiguities[param_name] = phase_names
    return requirements, ambiguities


def _collect_with_phase_names(expr: Any, *, ctx_name: str) -> set[str]:
    phase_names: set[str] = set()

    def _visit(node: Any) -> None:
        if node is None:
            return
        if isinstance(node, WithPhaseExpr):
            if isinstance(node.ctx_expr, NameExpr) and node.ctx_expr.name == ctx_name:
                phase_names.add(node.phase_name)
            _visit(node.ctx_expr)
            _visit(node.body)
            return
        if is_dataclass(node):
            for field_info in fields(node):
                _visit(getattr(node, field_info.name))
            return
        if isinstance(node, Mapping):
            for item in node.values():
                _visit(item)
            return
        if isinstance(node, (tuple, list)):
            for item in node:
                _visit(item)

    from .expressions import NameExpr, WithPhaseExpr

    _visit(expr)
    return phase_names


def _is_run_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    return (
        _record_field_is_primitive(type_ref, "run-id", "RunId")
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
    )


def _is_phase_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _is_run_context_shape(run_field)
        and _record_field_is_primitive(type_ref, "phase-name", "Symbol")
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
    )


def _is_item_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _is_run_context_shape(run_field)
        and _record_field_is_primitive(type_ref, "item-id", "String")
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
        and _record_field_is_path_under(type_ref, "ledger", "state")
    )


def _is_drain_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _is_run_context_shape(run_field)
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "manifest", "state")
        and _record_field_is_path_under(type_ref, "ledger", "state")
    )


def _is_selection_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _record_definition_name(type_ref) == SELECTION_CONTEXT_NAME
        and _is_run_context_shape(run_field)
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
    )


def _is_recovery_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _record_definition_name(type_ref) == RECOVERY_CONTEXT_NAME
        and _is_run_context_shape(run_field)
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
    )


def _record_field_is_primitive(record_type: RecordTypeRef, field_name: str, expected_name: str) -> bool:
    field_type = record_type.field_types.get(field_name)
    return isinstance(field_type, PrimitiveTypeRef) and field_type.name == expected_name


def _record_field_is_path_under(record_type: RecordTypeRef, field_name: str, expected_under: str) -> bool:
    field_type = record_type.field_types.get(field_name)
    return isinstance(field_type, PathTypeRef) and field_type.definition.under == expected_under


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
    if not is_record_definition_named(field_type, expected_record_name):
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
