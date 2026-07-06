"""Frontend-local resource/drain contracts and helper metadata."""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef


@dataclass(frozen=True)
class ItemLayout:
    """Derived paths for the intrinsic finalize-selected-item compatibility lane."""

    item_state_bundle_path: str
    item_temp_bundle_path: str
    outcome_bundle_path: str
    summary_target_path: str
    phase_root_prefix: str


@dataclass(frozen=True)
class DrainLayout:
    """Derived paths for the intrinsic backlog-drain compatibility lane."""

    run_state_bundle_path: str
    run_state_temp_bundle_path: str
    iteration_root_prefix: str
    summary_target_path: str
    gap_request_path: str


@dataclass(frozen=True)
class DrainAccumulator:
    """Runtime accumulator fields projected through the generated drain loop."""

    items_processed: int
    last_run_state_path: str | None = None
    blocked_stage: str | None = None
    blocked_reason: str | None = None


def ensure_item_context_type(
    type_ref: TypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Validate the record shape required for item-scoped stdlib forms."""

    if not isinstance(type_ref, RecordTypeRef):
        _raise_context_error(
            code="item_context_invalid",
            message="`resource-transition` and `finalize-selected-item` require an `ItemCtx` record",
            span=span,
            form_path=form_path,
        )
    run_type = _record_field_type(
        type_ref,
        "run",
        code="item_context_invalid",
        span=span,
        form_path=form_path,
    )
    _require_run_context_shape(run_type, field_name=f"{type_ref.name}.run", code="item_context_invalid", span=span, form_path=form_path)
    _require_record_field(type_ref, "item-id", expected_primitive="String", code="item_context_invalid", span=span, form_path=form_path)
    _require_record_field(type_ref, "state-root", expected_under="state", code="item_context_invalid", span=span, form_path=form_path)
    _require_record_field(type_ref, "artifact-root", expected_under="artifacts", code="item_context_invalid", span=span, form_path=form_path)
    _require_record_field(type_ref, "ledger", expected_under="state", code="item_context_invalid", span=span, form_path=form_path)


def ensure_drain_context_type(
    type_ref: TypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Validate the record shape required for `backlog-drain` contexts."""

    if not isinstance(type_ref, RecordTypeRef):
        _raise_context_error(
            code="drain_context_invalid",
            message="`backlog-drain` requires a `DrainCtx` record",
            span=span,
            form_path=form_path,
        )
    run_type = _record_field_type(
        type_ref,
        "run",
        code="drain_context_invalid",
        span=span,
        form_path=form_path,
    )
    _require_run_context_shape(
        run_type,
        field_name=f"{type_ref.name}.run",
        code="drain_context_invalid",
        span=span,
        form_path=form_path,
    )
    _require_record_field(type_ref, "state-root", expected_under="state", code="drain_context_invalid", span=span, form_path=form_path)
    _require_record_field(type_ref, "manifest", expected_under="state", code="drain_context_invalid", span=span, form_path=form_path)
    _require_record_field(type_ref, "ledger", expected_under="state", code="drain_context_invalid", span=span, form_path=form_path)


def ensure_resource_transition_members(
    resource_result_type: TypeRef,
    *,
    type_env: "FrontendTypeEnvironment",
    from_queue_name: str,
    to_queue_name: str,
    event_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Validate queue enum members used by a resource transition result."""

    if not isinstance(resource_result_type, RecordTypeRef):
        _raise_context_error(
            code="resource_transition_contract_invalid",
            message="`resource-transition` requires a record `ResourceTransitionResult` type",
            span=span,
            form_path=form_path,
        )
    from_type = _record_field_type(
        resource_result_type,
        "from",
        code="resource_transition_contract_invalid",
        span=span,
        form_path=form_path,
    )
    to_type = _record_field_type(
        resource_result_type,
        "to",
        code="resource_transition_contract_invalid",
        span=span,
        form_path=form_path,
    )
    ledger_event_type = type_env.resolve_type(
        "LedgerEvent",
        span=span,
        form_path=form_path,
    )
    _require_enum_member(
        from_type,
        authored_name=from_queue_name,
        label=":from",
        code="resource_transition_contract_invalid",
        span=span,
        form_path=form_path,
    )
    _require_enum_member(
        to_type,
        authored_name=to_queue_name,
        label=":to",
        code="resource_transition_contract_invalid",
        span=span,
        form_path=form_path,
    )
    _require_enum_member(
        ledger_event_type,
        authored_name=event_name,
        label=":event",
        code="resource_transition_contract_invalid",
        span=span,
        form_path=form_path,
    )


def ensure_resource_transition_resource_type(
    resource_type: TypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Validate the resource operand type accepted by `resource-transition`."""

    if isinstance(resource_type, PathTypeRef):
        return
    if isinstance(resource_type, PrimitiveTypeRef) and resource_type.name == "String":
        return
    _raise_context_error(
        code="resource_transition_contract_invalid",
        message="`resource-transition :resource` must resolve to `String` or an authored relpath contract",
        span=span,
        form_path=form_path,
    )


def ensure_finalize_selected_item_inputs(
    *,
    type_env: "FrontendTypeEnvironment",
    selected_type: TypeRef,
    roadmap_type: TypeRef,
    plan_type: TypeRef,
    implementation_type: TypeRef,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Validate typed inputs expected by `finalize-selected-item` lowering."""

    if not isinstance(selected_type, RecordTypeRef):
        _raise_context_error(
            code="finalize_selected_item_contract_invalid",
            message="`finalize-selected-item :selected` must resolve to a record",
            span=span,
            form_path=form_path,
        )
    if not isinstance(roadmap_type, RecordTypeRef):
        _raise_context_error(
            code="finalize_selected_item_contract_invalid",
            message="`finalize-selected-item :roadmap` must resolve to a record",
            span=span,
            form_path=form_path,
        )
    roadmap_status = _record_field_type(
        roadmap_type,
        "status",
        code="finalize_selected_item_contract_invalid",
        span=span,
        form_path=form_path,
    )
    if roadmap_status != PrimitiveTypeRef(name="String"):
        _raise_context_error(
            code="finalize_selected_item_contract_invalid",
            message="`finalize-selected-item :roadmap.status` must resolve to `String`",
            span=span,
            form_path=form_path,
        )
    blocker_class = type_env.resolve_type(
        "BlockerClass",
        span=span,
        form_path=form_path,
    )
    _require_finalize_union_contract(
        plan_type,
        completed_variant="APPROVED",
        completed_field="execution-report-path",
        blocked_variant="BLOCKED",
        blocked_summary_field="progress-report-path",
        blocker_class=blocker_class,
        span=span,
        form_path=form_path,
    )
    _require_finalize_union_contract(
        implementation_type,
        completed_variant="COMPLETED",
        completed_field="execution-report-path",
        blocked_variant="BLOCKED",
        blocked_summary_field="progress-report-path",
        blocker_class=blocker_class,
        span=span,
        form_path=form_path,
    )


def item_layout_for_ref(ctx_ref: str) -> ItemLayout:
    """Derive item-scoped generated field names from a context reference."""

    return ItemLayout(
        item_state_bundle_path=f"{ctx_ref}__item_state_bundle_path",
        item_temp_bundle_path=f"{ctx_ref}__item_temp_bundle_path",
        outcome_bundle_path=f"{ctx_ref}__outcome_bundle_path",
        summary_target_path=f"{ctx_ref}__summary_target_path",
        phase_root_prefix=f"{ctx_ref}__phase_root_prefix",
    )


def drain_layout_for_ref(ctx_ref: str) -> DrainLayout:
    """Derive drain-scoped generated field names from a context reference."""

    return DrainLayout(
        run_state_bundle_path=f"{ctx_ref}__run_state_bundle_path",
        run_state_temp_bundle_path=f"{ctx_ref}__run_state_temp_bundle_path",
        iteration_root_prefix=f"{ctx_ref}__iteration_root_prefix",
        summary_target_path=f"{ctx_ref}__summary_target_path",
        gap_request_path=f"{ctx_ref}__gap_request_path",
    )


def _require_record_field(
    type_ref: RecordTypeRef,
    field_name: str,
    *,
    expected_kind: str | None = None,
    expected_primitive: str | None = None,
    expected_under: str | None = None,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    field_type = type_ref.field_types.get(field_name)
    if field_type is None:
        _raise_context_error(
            code=code,
            message=f"context `{type_ref.name}` is missing required field `{field_name}`",
            span=span,
            form_path=form_path,
        )
    if expected_kind == "record" and not isinstance(field_type, RecordTypeRef):
        _raise_context_error(
            code=code,
            message=f"context field `{type_ref.name}.{field_name}` must be a record",
            span=span,
            form_path=form_path,
        )
    if expected_primitive is not None:
        if not isinstance(field_type, PrimitiveTypeRef) or field_type.name != expected_primitive:
            _raise_context_error(
                code=code,
                message=f"context field `{type_ref.name}.{field_name}` must resolve to `{expected_primitive}`",
                span=span,
                form_path=form_path,
            )
    if expected_under is not None:
        if not isinstance(field_type, PathTypeRef) or field_type.definition.under != expected_under:
            _raise_context_error(
                code=code,
                message=f"context field `{type_ref.name}.{field_name}` must be a relpath under `{expected_under}`",
                span=span,
                form_path=form_path,
            )


def _require_run_context_shape(
    type_ref: TypeRef,
    *,
    field_name: str,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if not isinstance(type_ref, RecordTypeRef):
        _raise_context_error(
            code=code,
            message=f"context field `{field_name}` must be a RunCtx-shaped record",
            span=span,
            form_path=form_path,
        )
    _require_record_field(
        type_ref,
        "run-id",
        expected_primitive="RunId",
        code=code,
        span=span,
        form_path=form_path,
    )
    _require_record_field(
        type_ref,
        "state-root",
        expected_under="state",
        code=code,
        span=span,
        form_path=form_path,
    )
    _require_record_field(
        type_ref,
        "artifact-root",
        expected_under="artifacts",
        code=code,
        span=span,
        form_path=form_path,
    )


def _record_field_type(
    type_ref: RecordTypeRef,
    field_name: str,
    *,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    field_type = type_ref.field_types.get(field_name)
    if field_type is None:
        _raise_context_error(
            code=code,
            message=f"context `{type_ref.name}` is missing required field `{field_name}`",
            span=span,
            form_path=form_path,
        )
    return field_type


def _require_enum_member(
    enum_type: TypeRef,
    *,
    authored_name: str,
    label: str,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if not isinstance(enum_type, PrimitiveTypeRef) or not enum_type.allowed_values:
        _raise_context_error(
            code=code,
            message=f"`resource-transition {label}` must resolve through an enum contract",
            span=span,
            form_path=form_path,
        )
    qualifier, _, value_name = authored_name.partition(".")
    if value_name:
        if qualifier != enum_type.name or value_name not in enum_type.allowed_values:
            _raise_context_error(
                code=code,
                message=f"`resource-transition {label}` must resolve to `{enum_type.name}`",
                span=span,
                form_path=form_path,
            )
        return
    if qualifier not in enum_type.allowed_values:
        _raise_context_error(
            code=code,
            message=f"`resource-transition {label}` must resolve to a declared `{enum_type.name}` value",
            span=span,
            form_path=form_path,
        )


def _require_finalize_union_contract(
    type_ref: TypeRef,
    *,
    completed_variant: str,
    completed_field: str,
    blocked_variant: str,
    blocked_summary_field: str,
    blocker_class: TypeRef,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if not isinstance(type_ref, UnionTypeRef):
        _raise_context_error(
            code="finalize_selected_item_contract_invalid",
            message="`finalize-selected-item` requires union plan and implementation results",
            span=span,
            form_path=form_path,
        )
    completed_field_type = _union_variant_field_type(
        type_ref,
        completed_variant,
        completed_field,
        span=span,
        form_path=form_path,
    )
    if not isinstance(completed_field_type, PathTypeRef) or completed_field_type.definition.under != "artifacts/work":
        _raise_context_error(
            code="finalize_selected_item_contract_invalid",
            message=(
                f"`finalize-selected-item` requires `{type_ref.name}.{completed_variant}.{completed_field}` "
                "to be a relpath under `artifacts/work`"
            ),
            span=span,
            form_path=form_path,
        )
    blocked_summary_type = _union_variant_field_type(
        type_ref,
        blocked_variant,
        blocked_summary_field,
        span=span,
        form_path=form_path,
    )
    if not isinstance(blocked_summary_type, PathTypeRef) or blocked_summary_type.definition.under != "artifacts/work":
        _raise_context_error(
            code="finalize_selected_item_contract_invalid",
            message=(
                f"`finalize-selected-item` requires `{type_ref.name}.{blocked_variant}.{blocked_summary_field}` "
                "to be a relpath under `artifacts/work`"
            ),
            span=span,
            form_path=form_path,
        )
    blocked_class_type = _union_variant_field_type(
        type_ref,
        blocked_variant,
        "blocker-class",
        span=span,
        form_path=form_path,
    )
    if blocked_class_type != blocker_class:
        _raise_context_error(
            code="finalize_selected_item_contract_invalid",
            message=(
                f"`finalize-selected-item` requires `{type_ref.name}.{blocked_variant}.blocker-class` "
                "to resolve to `BlockerClass`"
            ),
            span=span,
            form_path=form_path,
        )


def _union_variant_field_type(
    type_ref: UnionTypeRef,
    variant_name: str,
    field_name: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    variant_fields = type_ref.variant_field_types.get(variant_name)
    if variant_fields is None:
        _raise_context_error(
            code="finalize_selected_item_contract_invalid",
            message=f"`finalize-selected-item` requires variant `{variant_name}` on `{type_ref.name}`",
            span=span,
            form_path=form_path,
        )
    field_type = variant_fields.get(field_name)
    if field_type is None:
        _raise_context_error(
            code="finalize_selected_item_contract_invalid",
            message=f"`finalize-selected-item` requires field `{type_ref.name}.{variant_name}.{field_name}`",
            span=span,
            form_path=form_path,
        )
    return field_type


def _raise_context_error(
    *,
    code: str,
    message: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
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
