"""Frontend-local helpers for bounded `loop/recur` typing and lowering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .type_env import PrimitiveTypeRef, TypeRef, UnionTypeRef, WorkflowRefTypeRef

if TYPE_CHECKING:
    from .contracts import FlattenedContractField, UnionWorkflowBoundaryProjection
    from .expressions import ExprNode


LOOP_STATUS_ALLOWED = ("CONTINUE", "DONE")
LOOP_STATUS_OUTPUT_NAME = "status"


@dataclass(frozen=True)
class LoopRecurSpec:
    """Parsed author-facing bounded loop inputs."""

    max_iterations_expr: "ExprNode"
    initial_state_expr: "ExprNode"


@dataclass(frozen=True)
class LoopBodyBinding:
    """One loop-body state binding."""

    binding_name: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class LoopControlTypeRef:
    """Frontend-local `continue`/`done` control type."""

    state_type_ref: TypeRef
    result_type_ref: TypeRef | None


@dataclass(frozen=True)
class LoopValueProjection:
    """Flattened projection metadata for one carried loop value."""

    kind: str
    prefix: str
    flattened_fields: tuple[FlattenedContractField, ...]
    union_projection: UnionWorkflowBoundaryProjection | None = None
    placeholder_literals: Mapping[str, Any] = ()
    optional_relpath_fields: frozenset[str] = frozenset()


@dataclass(frozen=True)
class LoopLoweringPlan:
    """Deterministic generated names and projections for one lowered loop."""

    state_projection: LoopValueProjection
    result_projection: LoopValueProjection
    status_output_name: str
    seed_step_name: str
    repeat_step_name: str
    body_projection_step_name: str
    result_normalization_step_name: str


def ensure_loop_projectable_type(
    type_ref: TypeRef,
    *,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Reject carried loop types that cannot lower across the loop-output surface."""

    if isinstance(type_ref, WorkflowRefTypeRef):
        _raise_loop_error(
            code=code,
            message="workflow refs cannot be carried across `loop/recur` outputs",
            span=span,
            form_path=form_path,
        )
    if isinstance(type_ref, PrimitiveTypeRef) and type_ref.name in {"Json", "Provider", "Prompt"}:
        _raise_loop_error(
            code=code,
            message=f"`{type_ref.name}` cannot be carried across `loop/recur` outputs",
            span=span,
            form_path=form_path,
        )
    try:
        project_loop_value(
            type_ref,
            kind="probe",
            prefix="probe",
            span=span,
            form_path=form_path,
        )
    except TypeError as exc:
        _raise_loop_error(
            code=code,
            message=str(exc),
            span=span,
            form_path=form_path,
        )
    except LispFrontendCompileError as exc:
        diagnostic = exc.diagnostics[0]
        _raise_loop_error(
            code=code,
            message=diagnostic.message,
            span=span,
            form_path=form_path,
            expansion_stack=diagnostic.expansion_stack,
        )


def project_loop_value(
    type_ref: TypeRef,
    *,
    kind: str,
    prefix: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> LoopValueProjection:
    """Project one carried loop value onto deterministic flattened names."""

    from .contracts import (
        UnionWorkflowBoundaryProjection,
        derive_union_workflow_boundary_projection,
        derive_workflow_boundary_fields,
    )

    if isinstance(type_ref, UnionTypeRef):
        projection = derive_union_workflow_boundary_projection(
            type_ref,
            span=span,
            form_path=form_path,
        )
        renamed_fields = (
            _rename_flattened_field(projection.discriminant_field, prefix=prefix),
            *(_rename_flattened_field(field, prefix=prefix) for field in projection.shared_fields),
            *(
                _rename_flattened_field(field, prefix=prefix)
                for variant_fields in projection.variant_fields.values()
                for field in variant_fields
            ),
        )
        renamed_union_projection = UnionWorkflowBoundaryProjection(
            discriminant_field=_rename_flattened_field(projection.discriminant_field, prefix=prefix),
            shared_fields=tuple(
                _rename_flattened_field(field, prefix=prefix) for field in projection.shared_fields
            ),
            variant_fields={
                variant: tuple(_rename_flattened_field(field, prefix=prefix) for field in fields)
                for variant, fields in projection.variant_fields.items()
            },
        )
        return LoopValueProjection(
            kind=kind,
            prefix=prefix,
            flattened_fields=tuple(renamed_fields),
            union_projection=renamed_union_projection,
            placeholder_literals=_placeholder_literals(tuple(renamed_fields)),
            optional_relpath_fields=_optional_relpath_fields(
                tuple(renamed_fields),
                union_projection=renamed_union_projection,
            ),
        )

    fields = derive_workflow_boundary_fields(
        type_ref,
        generated_name=prefix,
        source_path=(prefix,),
        span=span,
        form_path=form_path,
    )
    return LoopValueProjection(
        kind=kind,
        prefix=prefix,
        flattened_fields=fields,
        union_projection=None,
        placeholder_literals=_placeholder_literals(fields),
        optional_relpath_fields=frozenset(),
    )


def build_loop_lowering_plan(
    *,
    step_name_prefix: str,
    state_type_ref: TypeRef,
    result_type_ref: TypeRef,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> LoopLoweringPlan:
    """Return deterministic generated names and flattened projections for one loop."""

    return LoopLoweringPlan(
        state_projection=project_loop_value(
            state_type_ref,
            kind="state",
            prefix="state",
            span=span,
            form_path=form_path,
        ),
        result_projection=project_loop_value(
            result_type_ref,
            kind="result",
            prefix="result",
            span=span,
            form_path=form_path,
        ),
        status_output_name=LOOP_STATUS_OUTPUT_NAME,
        seed_step_name=f"{step_name_prefix}__seed",
        repeat_step_name=f"{step_name_prefix}__loop",
        body_projection_step_name=f"{step_name_prefix}__body",
        result_normalization_step_name=f"{step_name_prefix}__result",
    )


def projection_by_name(projection: LoopValueProjection) -> dict[str, FlattenedContractField]:
    """Index one loop projection by generated field name."""

    return {field.generated_name: field for field in projection.flattened_fields}


def relpath_placeholder_name(*projections: LoopValueProjection) -> str | None:
    """Return one relpath field name suitable as a branch fallback."""

    for projection in projections:
        for field in projection.flattened_fields:
            definition = field.contract_definition
            if definition.get("kind") == "relpath" or definition.get("type") == "relpath":
                return field.generated_name
    return None


def projection_relpath_fields(projection: LoopValueProjection) -> frozenset[str]:
    """Return generated field names whose contracts are relpaths."""

    return frozenset(
        field.generated_name
        for field in projection.flattened_fields
        if field.contract_definition.get("type") == "relpath"
    )


def internal_loop_contract(
    field: FlattenedContractField,
    *,
    allow_missing_target_fields: frozenset[str],
) -> dict[str, Any]:
    """Return the internal loop contract for one flattened field.

    Internal loop plumbing may carry placeholder relpaths for inactive union
    arms or deferred loop results. Those relpaths stay typed as relpaths, but
    their generated internal contracts must not require the placeholder target
    to exist until the active branch is normalized back to the authored return.
    """

    contract = dict(field.contract_definition)
    if (
        field.generated_name in allow_missing_target_fields
        and contract.get("type") == "relpath"
    ):
        contract["must_exist_target"] = False
    return contract


def _rename_flattened_field(field: FlattenedContractField, *, prefix: str) -> FlattenedContractField:
    from .contracts import FlattenedContractField

    suffix = "__".join(field.source_path[1:])
    generated_name = prefix if not suffix else f"{prefix}__{suffix}"
    return FlattenedContractField(
        generated_name=generated_name,
        source_path=(prefix, *field.source_path[1:]),
        contract_definition=dict(field.contract_definition),
    )


def _placeholder_literals(fields: tuple[FlattenedContractField, ...]) -> dict[str, Any]:
    placeholders: dict[str, Any] = {}
    for field in fields:
        definition = field.contract_definition
        field_type = definition.get("type")
        if field_type == "bool":
            placeholders[field.generated_name] = False
        elif field_type == "integer":
            placeholders[field.generated_name] = 0
        elif field_type == "enum":
            allowed = definition.get("allowed", [])
            placeholders[field.generated_name] = allowed[0] if isinstance(allowed, list) and allowed else ""
        elif field_type == "relpath":
            under = str(definition.get("under", "state")).rstrip("/")
            placeholders[field.generated_name] = f"{under}/loop-placeholder.txt"
        else:
            placeholders[field.generated_name] = ""
    return placeholders


def _optional_relpath_fields(
    fields: tuple[FlattenedContractField, ...],
    *,
    union_projection: UnionWorkflowBoundaryProjection | None,
) -> frozenset[str]:
    if union_projection is None:
        return frozenset()

    variant_only_names = {
        field.generated_name
        for variant_fields in union_projection.variant_fields.values()
        for field in variant_fields
    }
    return frozenset(
        field.generated_name
        for field in fields
        if field.generated_name in variant_only_names
        and field.contract_definition.get("type") == "relpath"
    )


def _raise_loop_error(
    *,
    code: str,
    message: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
                phase="validation",
            ),
        )
    )
