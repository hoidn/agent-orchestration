"""Inert shared lowering leaf for one typed ``run-ref`` effect."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn

from orchestrator.workflow.run_ref.config import (
    ArrayBinding,
    InputBinding,
    LiteralBinding,
    ObjectBinding,
    ReferenceBinding,
    RunRefInput,
    build_run_ref_static_config,
)
from orchestrator.workflow.run_ref.contracts import (
    VerifiedCompilerRuntimeIdentity,
    compute_compiler_runtime_identity,
)
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from ..expressions import (
    ListExpr,
    LiteralExpr,
    NameExpr,
    RecordExpr,
    UnionVariantExpr,
)
from ..normalized_type_descriptor import compiler_normalized_type_descriptor
from ..run_ref_result_contract import (
    derive_run_ref_output_bundle_fields,
    derive_run_ref_result_contract,
)
from ..type_env import (
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
)
from .context import _compile_error, _LoweringContext, _TerminalResult
from .generated_paths import allocate_generated_result_bundle
from .origins import (
    GeneratedSemanticEffectBinding,
    LoweringOrigin,
    _origin_from_context_source,
    _record_step_origin,
    _with_origin_key,
)
from .pure_projection import (
    build_pure_projection_payload,
    is_pure_projection_expr,
    lower_pure_projection_step,
)
from .values import ProjectedPathRef, _record_output_refs, _resolve_inline_expr_value

if TYPE_CHECKING:
    from ..wcc.model import WccRunRefPayload
    from .core import LoweredWorkflow


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_WHOLE_INPUT_OUTPUT_CONTRACTS = {
    "__result__": {"kind": "value", "type": "value"},
}


def _shared_validation_source_map_payload(
    lowered_workflow: LoweredWorkflow,
) -> Mapping[str, object] | None:
    """Project generated E1/trial lineage for shared bundle validators."""

    workflow_name = lowered_workflow.typed_workflow.definition.name
    generated_semantic_effects = tuple(
        lowered_workflow.origin_map.generated_semantic_effects
    )
    identity_effects = tuple(
        effect
        for effect in generated_semantic_effects
        if effect.effect_kind in {"run_ref", "trial"}
    )
    if not identity_effects:
        return None

    def origin_rows(
        origins: Mapping[str, LoweringOrigin],
        *,
        entity_kind: str,
    ) -> dict[str, dict[str, str]]:
        return {
            subject_name: {
                "origin_key": _with_origin_key(
                    origin,
                    workflow_name=workflow_name,
                    entity_kind=entity_kind,
                    subject_name=subject_name,
                ).origin_key
            }
            for subject_name, origin in origins.items()
        }

    generated_effects: list[dict[str, object]] = []
    for effect in generated_semantic_effects:
        if effect.effect_kind == "pointer_materialization":
            entity_kind = "generated_path"
            subject_name = str(
                effect.details.get("pointer_path", effect.step_id)
            )
        elif effect.effect_kind == "provider_bundle_path_projection":
            entity_kind = "generated_output"
            subject_name = str(
                effect.details.get("projected_output_name", effect.step_id)
            )
        else:
            entity_kind = "step_id"
            subject_name = effect.step_id
        generated_effects.append(
            {
                "effect_key": effect.effect_key,
                "step_id": effect.step_id,
                "effect_kind": effect.effect_kind,
                "origin_key": _with_origin_key(
                    effect.origin,
                    workflow_name=workflow_name,
                    entity_kind=entity_kind,
                    subject_name=subject_name,
                ).origin_key,
                "details": dict(effect.details),
            }
        )

    return {
        "workflows": {
            workflow_name: {
                "workflow_origin": {
                    "origin_key": _with_origin_key(
                        lowered_workflow.origin_map.workflow_origin,
                        workflow_name=workflow_name,
                        entity_kind="workflow",
                        subject_name=workflow_name,
                    ).origin_key
                },
                "step_ids": origin_rows(
                    lowered_workflow.origin_map.step_spans,
                    entity_kind="step_id",
                ),
                "generated_inputs": origin_rows(
                    lowered_workflow.origin_map.authored_input_spans,
                    entity_kind="generated_input",
                ),
                "generated_outputs": origin_rows(
                    lowered_workflow.origin_map.generated_output_spans,
                    entity_kind="generated_output",
                ),
                "generated_paths": origin_rows(
                    lowered_workflow.origin_map.generated_path_spans,
                    entity_kind="generated_path",
                ),
                "generated_internal_inputs": origin_rows(
                    lowered_workflow.origin_map.internal_input_spans,
                    entity_kind="generated_internal_input",
                ),
                "contract_fields": {},
                "validation_subjects": [],
                "generated_semantic_effects": generated_effects,
            }
        }
    }


class _DirectBindingUnavailable(Exception):
    """Internal signal that one otherwise-pure input needs projection."""


@dataclass(frozen=True)
class _RunRefInputBindingPlan:
    row: LowerableRunRefInput
    direct_binding: InputBinding | None
    requires_projection: bool


@dataclass(frozen=True)
class LowerableRunRefInput:
    """One ordered typed input paired with its frontend value expression."""

    name: str
    value_expr: object
    type_ref: TypeRef
    type_descriptor: Mapping[str, object]


@dataclass(frozen=True)
class LowerableRunRef:
    """Closed arguments consumed by the shared leaf after WCC elaboration."""

    payload: WccRunRefPayload
    inputs: tuple[LowerableRunRefInput, ...]
    span: object
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        from ..wcc.model import WccRunRefPayload

        if not isinstance(self.payload, WccRunRefPayload):
            raise TypeError("lowerable run-ref requires a closed WCC payload")
        if not isinstance(self.inputs, tuple) or any(
            not isinstance(row, LowerableRunRefInput) for row in self.inputs
        ):
            raise TypeError("lowerable run-ref inputs must be an ordered tuple")


@dataclass(frozen=True)
class _RunRefContractView:
    descriptor: Mapping[str, object]
    digest: str
    allow_nested_structures: bool


def _input_binding_error(
    row: LowerableRunRefInput,
    *,
    code: str,
    message: str,
) -> NoReturn:
    raise _compile_error(
        code=code,
        message=message,
        span=getattr(row.value_expr, "span"),
        form_path=getattr(row.value_expr, "form_path", ()),
    )


def _resolved_binding_value(value: object, *, local_values: Mapping[str, object]) -> object:
    if isinstance(value, NameExpr) and value.name in local_values:
        return local_values[value.name]
    return _resolve_inline_expr_value(value, local_values=local_values)


def _literal_binding_for_value(
    value: object,
    *,
    row: LowerableRunRefInput,
) -> LiteralBinding:
    if value is not None and not isinstance(value, (str, int, float, bool)):
        _input_binding_error(
            row,
            code="run_ref_input_binding_invalid",
            message=f"run-ref input `{row.name}` contains a non-scalar literal",
        )
    try:
        return LiteralBinding(value)
    except ValueError as exc:
        _input_binding_error(
            row,
            code="run_ref_input_binding_invalid",
            message=f"run-ref input `{row.name}` contains an invalid scalar: {exc}",
        )


def _reference_binding_for_value(
    reference: str,
    *,
    row: LowerableRunRefInput,
) -> ReferenceBinding:
    try:
        return ReferenceBinding(reference)
    except ValueError as exc:
        _input_binding_error(
            row,
            code="run_ref_input_binding_invalid",
            message=f"run-ref input `{row.name}` contains an invalid reference: {exc}",
        )


def _utf8_sorted_object_entries(
    value: Mapping[object, object],
    *,
    row: LowerableRunRefInput,
) -> tuple[tuple[str, object], ...]:
    if any(not isinstance(key, str) for key in value):
        _input_binding_error(
            row,
            code="run_ref_input_binding_invalid",
            message=f"run-ref input `{row.name}` object keys must be strings",
        )
    try:
        return tuple(
            sorted(
                ((key, item) for key, item in value.items() if isinstance(key, str)),
                key=lambda item: item[0].encode("utf-8"),
            )
        )
    except UnicodeEncodeError:
        _input_binding_error(
            row,
            code="run_ref_input_binding_invalid",
            message=f"run-ref input `{row.name}` object key is not valid UTF-8",
        )


def _value_binding(
    value: object,
    *,
    row: LowerableRunRefInput,
    local_values: Mapping[str, object],
) -> InputBinding:
    resolved = _resolved_binding_value(value, local_values=local_values)
    if isinstance(resolved, LiteralExpr):
        return _literal_binding_for_value(resolved.value, row=row)
    if isinstance(resolved, ProjectedPathRef):
        return _reference_binding_for_value(resolved.ref, row=row)
    if (
        isinstance(resolved, Mapping)
        and set(resolved) == {"ref"}
        and isinstance(resolved.get("ref"), str)
    ):
        return _reference_binding_for_value(resolved["ref"], row=row)
    if isinstance(resolved, str):
        return _reference_binding_for_value(resolved, row=row)
    if isinstance(resolved, (type(None), bool, int, float)):
        return _literal_binding_for_value(resolved, row=row)
    if isinstance(resolved, (list, tuple)):
        return ArrayBinding(
            tuple(
                _value_binding(item, row=row, local_values=local_values)
                for item in resolved
            )
        )
    if isinstance(resolved, Mapping):
        return ObjectBinding(
            tuple(
                (
                    key,
                    _value_binding(item, row=row, local_values=local_values),
                )
                for key, item in _utf8_sorted_object_entries(resolved, row=row)
            )
        )
    if is_pure_projection_expr(resolved):
        raise _DirectBindingUnavailable
    _input_binding_error(
        row,
        code="run_ref_input_binding_invalid",
        message=f"run-ref input `{row.name}` contains an unsupported Value member",
    )


def _direct_binding_value(
    value: object,
    type_ref: TypeRef,
    *,
    row: LowerableRunRefInput,
    local_values: Mapping[str, object],
) -> InputBinding:
    resolved = _resolved_binding_value(value, local_values=local_values)
    if isinstance(resolved, ProjectedPathRef):
        return _reference_binding_for_value(resolved.ref, row=row)
    if (
        isinstance(resolved, Mapping)
        and set(resolved) == {"ref"}
        and isinstance(resolved.get("ref"), str)
    ):
        return _reference_binding_for_value(resolved["ref"], row=row)
    if isinstance(resolved, str) and not isinstance(value, LiteralExpr):
        return _reference_binding_for_value(resolved, row=row)

    if isinstance(type_ref, OptionalTypeRef):
        if resolved is None:
            return LiteralBinding(None)
        return _direct_binding_value(
            value,
            type_ref.item_type_ref,
            row=row,
            local_values=local_values,
        )
    if isinstance(type_ref, ListTypeRef):
        items: object
        if isinstance(value, ListExpr):
            items = value.items
        else:
            items = resolved
        if not isinstance(items, (list, tuple)):
            if is_pure_projection_expr(resolved):
                raise _DirectBindingUnavailable
            _input_binding_error(
                row,
                code="run_ref_input_binding_invalid",
                message=f"run-ref input `{row.name}` must be a list",
            )
        return ArrayBinding(
            tuple(
                _direct_binding_value(
                    item,
                    type_ref.item_type_ref,
                    row=row,
                    local_values=local_values,
                )
                for item in items
            )
        )
    if isinstance(type_ref, RecordTypeRef):
        if isinstance(value, RecordExpr):
            if value.type_name != type_ref.name:
                _input_binding_error(
                    row,
                    code="run_ref_input_binding_invalid",
                    message=f"run-ref input `{row.name}` record type changed before lowering",
                )
            names = tuple(name for name, _ in value.fields)
            if len(set(names)) != len(names):
                _input_binding_error(
                    row,
                    code="run_ref_input_binding_invalid",
                    message=f"run-ref input `{row.name}` record fields must be unique",
                )
            field_values: Mapping[object, object] = dict(value.fields)
        elif isinstance(resolved, Mapping):
            field_values = resolved
        else:
            if is_pure_projection_expr(resolved):
                raise _DirectBindingUnavailable
            _input_binding_error(
                row,
                code="run_ref_input_binding_invalid",
                message=f"run-ref input `{row.name}` must be a record",
            )
        declared_names = tuple(field.name for field in type_ref.definition.fields)
        if set(field_values) != set(declared_names) or any(
            not isinstance(name, str) for name in field_values
        ):
            _input_binding_error(
                row,
                code="run_ref_input_binding_invalid",
                message=f"run-ref input `{row.name}` record fields are incomplete or unknown",
            )
        return ObjectBinding(
            tuple(
                (
                    name,
                    _direct_binding_value(
                        field_values[name],
                        type_ref.field_types[name],
                        row=row,
                        local_values=local_values,
                    ),
                )
                for name in declared_names
            )
        )
    if isinstance(type_ref, UnionTypeRef):
        if isinstance(value, UnionVariantExpr):
            if value.type_name != type_ref.name:
                _input_binding_error(
                    row,
                    code="run_ref_input_binding_invalid",
                    message=f"run-ref input `{row.name}` union type changed before lowering",
                )
            variant_name = value.variant_name
            names = tuple(name for name, _ in value.fields)
            if len(set(names)) != len(names):
                _input_binding_error(
                    row,
                    code="run_ref_input_binding_invalid",
                    message=f"run-ref input `{row.name}` union fields must be unique",
                )
            field_values = dict(value.fields)
        elif isinstance(resolved, Mapping):
            raw_variant = resolved.get("variant")
            if isinstance(raw_variant, LiteralExpr):
                variant_name = raw_variant.value
            elif isinstance(raw_variant, (str, ProjectedPathRef)) or (
                isinstance(raw_variant, Mapping)
                and set(raw_variant) == {"ref"}
                and isinstance(raw_variant.get("ref"), str)
            ):
                raise _DirectBindingUnavailable
            else:
                variant_name = raw_variant
            field_values = {
                key: item for key, item in resolved.items() if key != "variant"
            }
        else:
            if is_pure_projection_expr(resolved):
                raise _DirectBindingUnavailable
            _input_binding_error(
                row,
                code="run_ref_input_binding_invalid",
                message=f"run-ref input `{row.name}` must be a union value",
            )
        if not isinstance(variant_name, str):
            _input_binding_error(
                row,
                code="run_ref_input_binding_invalid",
                message=f"run-ref input `{row.name}` union variant is missing",
            )
        variant = next(
            (
                candidate
                for candidate in type_ref.definition.variants
                if candidate.name == variant_name
            ),
            None,
        )
        if variant is None:
            _input_binding_error(
                row,
                code="run_ref_input_binding_invalid",
                message=f"run-ref input `{row.name}` union variant is unknown",
            )
        declared_names = tuple(field.name for field in variant.fields)
        if set(field_values) != set(declared_names) or any(
            not isinstance(name, str) for name in field_values
        ):
            _input_binding_error(
                row,
                code="run_ref_input_binding_invalid",
                message=f"run-ref input `{row.name}` union fields are incomplete or unknown",
            )
        variant_types = type_ref.variant_field_types[variant_name]
        return ObjectBinding(
            (("variant", LiteralBinding(variant_name)),)
            + tuple(
                (
                    name,
                    _direct_binding_value(
                        field_values[name],
                        variant_types[name],
                        row=row,
                        local_values=local_values,
                    ),
                )
                for name in declared_names
            )
        )
    if isinstance(type_ref, MapTypeRef):
        if not isinstance(resolved, Mapping):
            if is_pure_projection_expr(resolved):
                raise _DirectBindingUnavailable
            _input_binding_error(
                row,
                code="run_ref_input_binding_invalid",
                message=f"run-ref input `{row.name}` must be a string-keyed map",
            )
        return ObjectBinding(
            tuple(
                (
                    key,
                    _direct_binding_value(
                        item,
                        type_ref.value_type_ref,
                        row=row,
                        local_values=local_values,
                    ),
                )
                for key, item in _utf8_sorted_object_entries(resolved, row=row)
            )
        )
    if isinstance(type_ref, PrimitiveTypeRef) and type_ref.name == "Value":
        return _value_binding(value, row=row, local_values=local_values)

    if isinstance(resolved, LiteralExpr):
        scalar = resolved.value
    else:
        scalar = resolved
    if is_pure_projection_expr(scalar):
        raise _DirectBindingUnavailable
    if hasattr(scalar, "span") and hasattr(scalar, "form_path"):
        _input_binding_error(
            row,
            code="run_ref_input_binding_unsupported",
            message=(
                f"run-ref input `{row.name}` is effectful or cannot be "
                "represented as transportable data"
            ),
        )
    if isinstance(type_ref, PathTypeRef):
        valid = isinstance(scalar, str)
    elif isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.allowed_values:
            valid = isinstance(scalar, str) and scalar in type_ref.allowed_values
        elif type_ref.name in {"String", "Symbol", "RunId"}:
            valid = isinstance(scalar, str)
        elif type_ref.name == "Bool":
            valid = isinstance(scalar, bool)
        elif type_ref.name == "Int":
            valid = isinstance(scalar, int) and not isinstance(scalar, bool)
        elif type_ref.name == "Float":
            valid = isinstance(scalar, (int, float)) and not isinstance(scalar, bool)
        else:
            valid = isinstance(scalar, (str, int, float, bool, type(None)))
    else:
        valid = False
    if not valid:
        _input_binding_error(
            row,
            code="run_ref_input_binding_invalid",
            message=f"run-ref input `{row.name}` scalar does not match its declared type",
        )
    return _literal_binding_for_value(scalar, row=row)


def _direct_run_ref_input_binding(
    row: LowerableRunRefInput,
    *,
    local_values: Mapping[str, object],
) -> InputBinding:
    return _direct_binding_value(
        row.value_expr,
        row.type_ref,
        row=row,
        local_values=local_values,
    )


def _plan_run_ref_input_binding(
    row: LowerableRunRefInput,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, object],
) -> _RunRefInputBindingPlan:
    try:
        binding = _direct_run_ref_input_binding(row, local_values=local_values)
    except _DirectBindingUnavailable:
        if not is_pure_projection_expr(row.value_expr):
            _input_binding_error(
                row,
                code="run_ref_input_binding_unsupported",
                message=(
                    f"run-ref input `{row.name}` is effectful or cannot be "
                    "represented as transportable data"
                ),
            )
        build_pure_projection_payload(
            row.value_expr,
            result_type=row.type_ref,
            context=context,
            local_values=local_values,
        )
        return _RunRefInputBindingPlan(
            row=row,
            direct_binding=None,
            requires_projection=True,
        )
    return _RunRefInputBindingPlan(
        row=row,
        direct_binding=binding,
        requires_projection=False,
    )


def _compiler_runtime_identity_digest(
    session,
    *,
    identity_provider: Callable[
        [], VerifiedCompilerRuntimeIdentity
    ] = compute_compiler_runtime_identity,
) -> str:
    """Return one validated compiler/runtime digest, computing it once/session."""

    cached = getattr(session, "run_ref_compiler_runtime_identity_digest", None)
    if cached is not None:
        if not isinstance(cached, str) or _SHA256_RE.fullmatch(cached) is None:
            raise ValueError("cached run-ref compiler/runtime identity is invalid")
        return cached
    identity = identity_provider()
    if not isinstance(identity, VerifiedCompilerRuntimeIdentity):
        raise TypeError("run-ref compiler identity provider returned an invalid value")
    if _SHA256_RE.fullmatch(identity.digest) is None:
        raise ValueError("run-ref compiler/runtime identity digest is invalid")
    session.run_ref_compiler_runtime_identity_digest = identity.digest
    return identity.digest


def _lower_run_ref_operation(
    run_ref: LowerableRunRef,
    *,
    result_type: RecordTypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, object],
    identity_provider: Callable[
        [], VerifiedCompilerRuntimeIdentity
    ] = compute_compiler_runtime_identity,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Build an inert run-ref step without selecting a public lowering route."""

    prefix_steps, config, contract = _lower_run_ref_static_config(
        run_ref,
        result_type=result_type,
        context=context,
        local_values=local_values,
        identity_provider=identity_provider,
    )
    output_fields = derive_run_ref_output_bundle_fields(contract)

    step_name = context.step_name_prefix
    step_id = context.normalize_generated_step_id(step_name)
    allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=run_ref,
        step_name=step_name,
        step_id=step_id,
        semantic_role=GeneratedPathSemanticRole.RUN_REF_RESULT_BUNDLE,
        stable_target="run_ref_result",
    )
    _record_step_origin(
        context,
        step_name=step_name,
        step_id=step_id,
        source=run_ref,
    )
    context.generated_semantic_effects.append(
        GeneratedSemanticEffectBinding(
            effect_key=f"run_ref:{step_id}",
            step_id=step_id,
            effect_kind="run_ref",
            origin=context.step_spans[step_id],
            details={
                "run_ref_static_config_schema_version": config.record[
                    "schema_version"
                ],
                "run_ref_static_config_digest": config.digest,
                "compiler_runtime_identity_digest": (
                    config.compiler_runtime_identity_digest
                ),
                "site_digest": config.site_digest,
                "generated_result_type": config.generated_result_type,
                "result_digest": config.result_digest,
                "program_mode": config.program.record["mode"],
                "result_allocation_id": allocation.allocation_id,
                "output_bundle_path": allocation.concrete_path_template,
            },
        )
    )
    step = {
        "name": step_name,
        "id": step_id,
        "output_bundle": {
            "path": allocation.concrete_path_template,
            "fields": output_fields,
        },
        "run_ref": config,
    }
    return [*prefix_steps, step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=_record_output_refs(step_name, result_type),
        output_kind="step",
        hidden_inputs={
            allocation.generated_input_name: _origin_from_context_source(
                context,
                run_ref,
            )
        },
        checkpoint_identity_component_digest=config.digest,
    )


def _lower_run_ref_static_config(
    run_ref: LowerableRunRef,
    *,
    result_type: RecordTypeRef | None,
    context: _LoweringContext,
    local_values: Mapping[str, object],
    identity_provider: Callable[
        [], VerifiedCompilerRuntimeIdentity
    ] = compute_compiler_runtime_identity,
    projection_step_role: str = "input",
):
    """Lower one nested E1 form without emitting its own effect node."""

    if not isinstance(run_ref, LowerableRunRef):
        raise TypeError("run-ref lowering requires LowerableRunRef")
    if result_type is not None and not isinstance(result_type, RecordTypeRef):
        raise TypeError("run-ref lowering requires its generated record result")
    contract = (
        derive_run_ref_result_contract(
            result_type,
            type_env=context.type_env,
        )
        if isinstance(result_type, RecordTypeRef)
        else _RunRefContractView(
            descriptor=run_ref.payload.result_descriptor,
            digest=run_ref.payload.result_digest,
            allow_nested_structures=run_ref.payload.allow_nested_structures,
        )
    )
    if (
        (
            isinstance(result_type, RecordTypeRef)
            and result_type.name != run_ref.payload.generated_result_type
        )
        or contract.descriptor != run_ref.payload.result_descriptor
        or contract.digest != run_ref.payload.result_digest
        or contract.allow_nested_structures
        is not run_ref.payload.allow_nested_structures
    ):
        raise ValueError("run-ref result metadata changed before lowering")
    if isinstance(result_type, RecordTypeRef):
        # Keep the public leaf's established fail-before-mutation contract:
        # output flattening can reject collisions, so validate it before
        # projection allocation or compiler-identity caching.
        derive_run_ref_output_bundle_fields(contract)
    payload_descriptors = run_ref.payload.input_type_descriptors
    if len(run_ref.inputs) != len(payload_descriptors):
        raise ValueError("run-ref input metadata changed before lowering")
    input_plans: list[_RunRefInputBindingPlan] = []
    for row, (payload_name, payload_descriptor) in zip(
        run_ref.inputs,
        payload_descriptors,
        strict=True,
    ):
        normalized_descriptor = compiler_normalized_type_descriptor(
            row.type_ref,
            type_env=context.type_env,
            source_read_trace=getattr(context, "source_read_trace", None),
        )
        if (
            row.name != payload_name
            or dict(row.type_descriptor) != payload_descriptor
            or normalized_descriptor != payload_descriptor
        ):
            raise ValueError("run-ref input metadata changed before lowering")
        input_plans.append(
            _plan_run_ref_input_binding(
                row,
                context=context,
                local_values=local_values,
            )
        )

    prefix_steps: list[dict[str, Any]] = []
    lowered_inputs: list[RunRefInput] = []
    for plan, (_, payload_descriptor) in zip(
        input_plans,
        payload_descriptors,
        strict=True,
    ):
        binding = plan.direct_binding
        if plan.requires_projection:
            projection_step_name = context.normalize_generated_step_id(
                f"{context.step_name_prefix}__{projection_step_role}__{plan.row.name}"
            )
            lowered_projection = lower_pure_projection_step(
                plan.row.value_expr,
                result_type=plan.row.type_ref,
                context=context,
                local_values=local_values,
                step_name=projection_step_name,
                step_id=projection_step_name,
                stable_target=(
                    f"run_ref_{projection_step_role}_{plan.row.name}"
                ),
                output_contracts=_WHOLE_INPUT_OUTPUT_CONTRACTS,
            )
            binding_ref = lowered_projection.output_refs.get("return")
            if (
                set(lowered_projection.output_refs) != {"return"}
                or not isinstance(binding_ref, str)
            ):
                raise ValueError(
                    "run-ref whole-input projection did not expose one root ref"
                )
            prefix_steps.append(lowered_projection.step)
            binding = ReferenceBinding(binding_ref)
        if binding is None:
            raise AssertionError("run-ref input plan did not produce a binding")
        lowered_inputs.append(
            RunRefInput(
                name=plan.row.name,
                type_descriptor=payload_descriptor,
                binding=binding,
                allow_nested_structures=contract.allow_nested_structures,
            )
        )

    compiler_identity = _compiler_runtime_identity_digest(
        context.lowering_session,
        identity_provider=identity_provider,
    )
    config = build_run_ref_static_config(
        compiler_runtime_identity_digest=compiler_identity,
        site_digest=run_ref.payload.site_digest,
        source=run_ref.payload.source,
        program=run_ref.payload.program,
        inputs=tuple(lowered_inputs),
        result_descriptor=contract.descriptor,
        result_digest=contract.digest,
        target_dsl_version=context.type_env.target_dsl_version,
    )
    return prefix_steps, config, contract
