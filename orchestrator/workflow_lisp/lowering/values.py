"""Value, projection, and inline materialization helpers for lowering."""

from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from ..contracts import derive_structured_result_contract, derive_workflow_boundary_fields
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import (
    BindProcExpr,
    EnumMemberExpr,
    FieldAccessExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    NameExpr,
    PhaseTargetExpr,
    ProviderBundlePathExpr,
    ProcRefLiteralExpr,
    RecordExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
)
from ..procedures import TypedProcedureDef
from ..syntax import target_dsl_supports_generic_unions, target_dsl_supports_rich_loop_values
from ..type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from ..typecheck import TypedExpr
from .context import _compile_error, _LoweringContext, _TerminalResult
from .generated_paths import allocate_generated_result_bundle
from .origins import (
    LoweringOrigin,
    _origin_from_context_source,
    _record_step_origin,
    _register_generated_contract_field_bindings,
)


_PROVIDER_BUNDLE_PATH_REF_KEY = "__provider_bundle_path_ref__"
_PROVIDER_BUNDLE_PROJECTION_KEY = "__provider_bundle_projection__"


@dataclass(frozen=True)
class ProjectedPathRef:
    """Inline lowered ref plus projection metadata for public output provenance."""

    ref: str
    projection: Mapping[str, Any]


def attach_provider_bundle_identity(
    local_value: Mapping[str, Any],
    *,
    provider_bundle_identity: Mapping[str, Any],
) -> dict[str, Any]:
    annotated = dict(local_value)
    path_ref = provider_bundle_identity.get("bundle_path_ref")
    if isinstance(path_ref, str):
        annotated[_PROVIDER_BUNDLE_PATH_REF_KEY] = path_ref
    annotated[_PROVIDER_BUNDLE_PROJECTION_KEY] = dict(provider_bundle_identity)
    return annotated


def _projected_provider_bundle_ref(value: Any) -> ProjectedPathRef | None:
    if not isinstance(value, Mapping):
        return None
    path_ref = value.get(_PROVIDER_BUNDLE_PATH_REF_KEY)
    projection = value.get(_PROVIDER_BUNDLE_PROJECTION_KEY)
    if not isinstance(path_ref, str) or not isinstance(projection, Mapping):
        return None
    return ProjectedPathRef(ref=path_ref, projection=dict(projection))


def _value_compile_error(*, code: str, message: str, span, form_path: tuple[str, ...]) -> LispFrontendCompileError:
    return LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                phase="lowering",
            ),
        )
    )


def _boundary_placeholder_literals(
    type_ref: TypeRef,
    *,
    span,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    placeholders: dict[str, Any] = {}
    for field in derive_workflow_boundary_fields(
        type_ref,
        generated_name="return",
        source_path=("return",),
        span=span,
        form_path=form_path,
    ):
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
            under = definition.get("under", "artifacts")
            placeholders[field.generated_name] = f"{under}/placeholder.txt"
        else:
            placeholders[field.generated_name] = ""
    return placeholders


def _union_variant_materialize_source(
    union_expr: UnionVariantExpr,
    *,
    field_path: tuple[str, ...],
    local_values: Mapping[str, Any],
    bound_record_fields: bool,
) -> dict[str, Any]:
    leaf_expr = _union_variant_expr_value_at_path(union_expr, field_path, bound_record_fields=bound_record_fields)
    leaf_value = _resolve_inline_expr_value(leaf_expr, local_values=local_values)
    if isinstance(leaf_value, LiteralExpr):
        return {"literal": leaf_value.value}
    if isinstance(leaf_value, str):
        return {"ref": leaf_value}
    raise _compile_error(
        code="workflow_return_not_exportable",
        message=(
            f"union return field `{'__'.join(field_path)}` must lower from an existing step artifact "
            "or literal in this Stage 3 slice"
        ),
        span=leaf_expr.span,
        form_path=leaf_expr.form_path,
    )


def _build_record_local_value(type_ref: RecordTypeRef, *, generated_name: str) -> dict[str, Any]:
    """Represent a record parameter as nested refs to flattened inputs."""

    local_value: dict[str, Any] = {}
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        leaf_name = f"{generated_name}__{field.name}"
        if isinstance(field_type, RecordTypeRef):
            local_value[field.name] = _build_record_local_value(
                field_type,
                generated_name=leaf_name,
            )
        elif isinstance(field_type, UnionTypeRef):
            local_value[field.name] = _build_union_local_value(
                field_type,
                generated_name=leaf_name,
            )
        else:
            local_value[field.name] = f"inputs.{leaf_name}"
    return local_value


def _build_union_local_value(type_ref: UnionTypeRef, *, generated_name: str) -> dict[str, Any]:
    """Represent a union parameter as nested refs to flattened inputs."""

    local_value: dict[str, Any] = {}
    for leaf_name, field_path in _flatten_boundary_leaf_paths(type_ref, generated_name=generated_name):
        _assign_nested_local_value(local_value, field_path, f"inputs.{leaf_name}")
    return local_value


def union_prompt_source_from_type(
    type_ref: UnionTypeRef,
    *,
    generated_name: str,
) -> dict[str, Any]:
    def field_source(field_type: TypeRef, field_name: str) -> dict[str, Any]:
        if isinstance(field_type, RecordTypeRef):
            return {
                "kind": "record",
                "fields": {
                    name: field_source(nested_type, f"{field_name}__{name}")
                    for name, nested_type in field_type.field_types.items()
                },
            }
        return {"kind": "reference", "reference": f"inputs.{field_name}"}

    return {
        "kind": "union",
        "discriminant": {
            "kind": "reference",
            "reference": f"inputs.{generated_name}__variant",
        },
        "variants": {
            variant_name: {
                field_name: field_source(
                    field_type,
                    f"{generated_name}__{field_name}",
                )
                for field_name, field_type in fields.items()
            }
            for variant_name, fields in type_ref.variant_field_types.items()
        },
    }


def union_prompt_source_from_output_refs(
    type_ref: UnionTypeRef,
    *,
    output_refs: Mapping[str, str],
) -> dict[str, Any] | None:
    """Preserve branch-specific terminal refs before local-value nesting."""

    def field_source(field_type: TypeRef, prefix: str) -> dict[str, Any] | None:
        if isinstance(field_type, RecordTypeRef):
            fields: dict[str, Any] = {}
            for name, nested_type in field_type.field_types.items():
                child = field_source(nested_type, f"{prefix}__{name}")
                if child is None:
                    return None
                fields[name] = child
            return {"kind": "record", "fields": fields}
        ref = output_refs.get(prefix) or output_refs.get(prefix.removeprefix("return__"))
        return (
            {"kind": "reference", "reference": ref}
            if isinstance(ref, str)
            else None
        )

    discriminant = output_refs.get("return__variant") or output_refs.get("variant")
    if not isinstance(discriminant, str):
        return None
    variants: dict[str, Any] = {}
    for variant_name, fields in type_ref.variant_field_types.items():
        variant_sources: dict[str, Any] = {}
        for field_name, field_type in fields.items():
            source = field_source(field_type, f"return__{field_name}")
            if source is None:
                return None
            variant_sources[field_name] = source
        variants[variant_name] = variant_sources
    return {
        "kind": "union",
        "discriminant": {"kind": "reference", "reference": discriminant},
        "variants": variants,
    }


def union_output_refs_from_source(
    type_ref: UnionTypeRef,
    source: Mapping[str, Any],
) -> dict[str, str] | None:
    """Recover original terminal refs from compiler-owned union source data."""

    output_refs: dict[str, str] = {}

    def add_ref(node: Any, output_name: str) -> bool:
        if not isinstance(node, Mapping) or node.get("kind") != "reference":
            return False
        reference = node.get("reference")
        if not isinstance(reference, str):
            return False
        return output_refs.setdefault(output_name, reference) == reference

    def field_refs(field_type: TypeRef, node: Any, prefix: str) -> bool:
        if isinstance(field_type, RecordTypeRef):
            if not isinstance(node, Mapping) or node.get("kind") != "record":
                return False
            fields = node.get("fields")
            return isinstance(fields, Mapping) and all(
                field_refs(nested_type, fields.get(name), f"{prefix}__{name}")
                for name, nested_type in field_type.field_types.items()
            )
        return add_ref(node, prefix)

    if not isinstance(source, Mapping) or source.get("kind") != "union":
        return None
    if not add_ref(source.get("discriminant"), "return__variant"):
        return None
    variants = source.get("variants")
    if not isinstance(variants, Mapping):
        return None
    for name, fields in type_ref.variant_field_types.items():
        sources = variants.get(name)
        if not isinstance(sources, Mapping) or not all(
            field_refs(field_type, sources.get(field_name), f"return__{field_name}")
            for field_name, field_type in fields.items()
        ):
            return None
    return output_refs


def rewrite_typed_union_projection_references(
    value: Any,
    rewrite_reference: Callable[[str], str],
) -> Any | None:
    """Rewrite explicit source refs while keeping literal payload data opaque."""

    if not isinstance(value, Mapping) or set(value) != {
        "kind",
        "descriptor",
        "source",
    } or value.get("kind") != "typed_union_projection":
        return None

    return {
        **value,
        "source": rewrite_typed_union_prompt_source_references(
            value["source"],
            rewrite_reference,
        ),
    }


def rewrite_typed_union_prompt_source_references(
    source: Any,
    rewrite_reference: Callable[[str], str],
) -> Any:
    """Rewrite a compiler-owned source tree; literal values are terminal data."""

    def rewrite_source(source: Any) -> Any:
        if not isinstance(source, Mapping):
            return source
        kind = source.get("kind")
        if kind == "reference" and isinstance(source.get("reference"), str):
            return {**source, "reference": rewrite_reference(source["reference"])}
        if kind == "literal":
            return dict(source)
        if kind == "record":
            return {
                **source,
                "fields": {
                    name: rewrite_source(child)
                    for name, child in source["fields"].items()
                },
            }
        if kind == "union":
            return {
                **source,
                "discriminant": rewrite_source(source["discriminant"]),
                "variants": {
                    tag: {
                        name: rewrite_source(child)
                        for name, child in fields.items()
                    }
                    for tag, fields in source["variants"].items()
                },
            }
        return dict(source)

    return rewrite_source(source)


def iter_typed_union_prompt_source_references(source: Any) -> tuple[str, ...]:
    """Return explicit source references without interpreting literal payloads."""

    refs: list[str] = []

    def visit(node: Any) -> None:
        if not isinstance(node, Mapping):
            return
        kind = node.get("kind")
        if kind == "reference":
            reference = node.get("reference")
            if isinstance(reference, str):
                refs.append(reference)
            return
        if kind == "record":
            for child in (node.get("fields") or {}).values():
                visit(child)
            return
        if kind == "union":
            visit(node.get("discriminant"))
            for fields in (node.get("variants") or {}).values():
                for child in fields.values():
                    visit(child)

    visit(source)
    return tuple(refs)


def iter_typed_union_projection_references(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, Mapping) or set(value) != {
        "kind",
        "descriptor",
        "source",
    } or value.get("kind") != "typed_union_projection":
        return None
    return iter_typed_union_prompt_source_references(value["source"])


def iter_parent_ref_strings(payload: object) -> tuple[str, ...]:
    """Find compiler references while treating typed-union literals as data."""

    refs: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            source_refs = iter_typed_union_projection_references(value)
            if source_refs is not None:
                refs.extend(ref for ref in source_refs if ref.startswith("parent.steps."))
                return
            ref = value.get("ref")
            if isinstance(ref, str) and ref.startswith("parent.steps."):
                refs.append(ref)
            for key, nested in value.items():
                if key == "__typed_union_prompt_source__":
                    refs.extend(
                        ref
                        for ref in iter_typed_union_prompt_source_references(nested)
                        if ref.startswith("parent.steps.")
                    )
                    continue
                visit(nested)
            return
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for nested in value:
                visit(nested)

    visit(payload)
    return tuple(refs)


def _build_nested_record_step_local_value(
    type_ref: RecordTypeRef,
    *,
    step_name: str,
    artifact_prefix: tuple[str, ...],
) -> dict[str, Any]:
    """Represent a nested record result from step artifact refs."""

    local_value: dict[str, Any] = {}
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        next_prefix = artifact_prefix + (field.name,)
        if isinstance(field_type, RecordTypeRef):
            local_value[field.name] = _build_nested_record_step_local_value(
                field_type,
                step_name=step_name,
                artifact_prefix=next_prefix,
            )
            continue
        local_value[field.name] = f"root.steps.{step_name}.artifacts.{'__'.join(next_prefix)}"
    return local_value


def _build_record_step_local_value(type_ref: RecordTypeRef, *, step_name: str) -> dict[str, Any]:
    """Represent a record result as nested refs to one step's artifacts."""

    local_value: dict[str, Any] = {}
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        artifact_name = field.name
        if isinstance(field_type, RecordTypeRef):
            local_value[field.name] = _build_nested_record_step_local_value(
                field_type,
                step_name=step_name,
                artifact_prefix=(artifact_name,),
            )
            continue
        local_value[field.name] = f"root.steps.{step_name}.artifacts.{artifact_name}"
    return local_value


def _procedure_signature_local_values(procedure: TypedProcedureDef) -> dict[str, Any]:
    """Seed local value refs from a private workflow procedure signature."""

    local_values: dict[str, Any] = {}
    for param_name, param_type in procedure.signature.params:
        if isinstance(param_type, RecordTypeRef):
            local_values[param_name] = _build_record_local_value(
                param_type,
                generated_name=param_name,
            )
            continue
        if isinstance(param_type, UnionTypeRef):
            local_values[param_name] = _build_union_local_value(
                param_type,
                generated_name=param_name,
            )
            continue
        local_values[param_name] = f"inputs.{param_name}"
    if procedure.specialization is not None:
        local_values.update(dict(getattr(procedure.specialization, "workflow_ref_bindings", {})))
        local_values.update(dict(getattr(procedure.specialization, "proc_ref_bindings", {})))
        local_values.update(dict(getattr(procedure.specialization, "value_bindings", {})))
    return local_values


def _signature_local_values(typed_workflow: Any) -> dict[str, Any]:
    """Seed local value refs from a workflow signature."""

    signature = typed_workflow.signature
    local_values: dict[str, Any] = {}
    for param_name, param_type in signature.params:
        if isinstance(param_type, RecordTypeRef):
            local_values[param_name] = _build_record_local_value(param_type, generated_name=param_name)
        elif isinstance(param_type, UnionTypeRef):
            local_values[param_name] = _build_union_local_value(param_type, generated_name=param_name)
        else:
            local_values[param_name] = f"inputs.{param_name}"
    specialization = getattr(typed_workflow, "specialization", None)
    if specialization is not None:
        local_values.update(dict(getattr(specialization, "workflow_ref_bindings", {})))
        local_values.update(dict(getattr(specialization, "proc_ref_bindings", {})))
        local_values.update(dict(getattr(specialization, "value_bindings", {})))
    return local_values


def _procedure_signature_local_type_bindings(procedure: TypedProcedureDef) -> dict[str, TypeRef]:
    """Seed local type bindings from a private workflow procedure signature."""

    local_type_bindings = {
        param_name: param_type
        for param_name, param_type in procedure.signature.params
    }
    specialization = getattr(procedure, "specialization", None)
    if specialization is not None:
        local_type_bindings.update(dict(getattr(specialization, "bound_param_types", {})))
    return local_type_bindings


def _resolve_nested_local_value(value: Any, field_path: tuple[str, ...]) -> Any:
    """Follow a flattened field path through a nested local-value mapping."""

    current = value
    for field_name in field_path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(field_name)
    return current


def _resolve_expr_local_value(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    """Resolve simple name, field, and phase-target expressions from locals."""

    if isinstance(expr, NameExpr):
        return local_values.get(expr.name)
    if isinstance(expr, FieldAccessExpr):
        base_value = _resolve_expr_local_value(expr.base, local_values=local_values)
        return _resolve_nested_local_value(base_value, tuple(expr.fields))
    if isinstance(expr, PhaseTargetExpr):
        return None
    return None


def _record_field_value(record_expr: RecordExpr, field_name: str) -> Any:
    for current_name, current_value in record_expr.fields:
        if current_name == field_name:
            return current_value
    return None


def _resolve_inline_field_value(
    value: Any,
    *,
    field_path: tuple[str, ...],
    local_values: Mapping[str, Any],
) -> Any:
    """Resolve a nested field path through inline mappings or record expressions."""

    current = value
    for field_name in field_path:
        if current is not None and not isinstance(current, (Mapping, RecordExpr, UnionVariantExpr)):
            next_current = _resolve_inline_expr_value(current, local_values=local_values)
            if next_current is current:
                return None
            current = next_current
        if isinstance(current, Mapping):
            current = current.get(field_name)
            continue
        if isinstance(current, RecordExpr):
            current = _record_field_value(current, field_name)
            current = _resolve_inline_expr_value(current, local_values=local_values)
            continue
        if isinstance(current, UnionVariantExpr):
            current = _union_variant_expr_value_at_path(current, (field_name,))
            current = _resolve_inline_expr_value(current, local_values=local_values)
            continue
        return None
    return current


def projected_union_field_activity(
    value: Any,
    *,
    discriminant_path: tuple[str, ...],
    active_variants: Sequence[str],
    local_values: Mapping[str, Any],
) -> bool | None:
    """Return known union-field activity without reading its variant payload."""

    discriminant = _resolve_inline_field_value(
        value,
        field_path=discriminant_path,
        local_values=local_values,
    )
    if isinstance(discriminant, LiteralExpr) and isinstance(discriminant.value, str):
        return discriminant.value in active_variants
    return None


def _resolve_inline_expr_value(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    """Resolve literals, names, fields, and record expressions for inline use."""

    if isinstance(expr, LiteralExpr | GeneratedRelpathSeedExpr | WorkflowRefLiteralExpr):
        return expr
    if isinstance(expr, EnumMemberExpr):
        return LiteralExpr(
            value=expr.member_name,
            literal_kind="string",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, ProcRefLiteralExpr | BindProcExpr):
        return expr
    if isinstance(expr, RecordExpr):
        inline_value: dict[str, Any] = {}
        for field_name, field_expr in expr.fields:
            resolved_value = _resolve_inline_expr_value(field_expr, local_values=local_values)
            if resolved_value is None:
                return expr
            inline_value[field_name] = resolved_value
        return inline_value
    if isinstance(expr, LoopStateSeedExpr):
        return _loop_state_seed_inline_value(expr, local_values=local_values)
    if isinstance(expr, LoopStateUpdateExpr):
        return _loop_state_update_inline_value(expr, local_values=local_values)
    if isinstance(expr, LetStarExpr):
        child_locals = dict(local_values)
        for binding_name, binding_expr in expr.bindings:
            resolved_binding = _resolve_inline_expr_value(binding_expr, local_values=child_locals)
            if resolved_binding is None:
                return expr
            child_locals[binding_name] = resolved_binding
        return _resolve_inline_expr_value(expr.body, local_values=child_locals)
    if isinstance(expr, IfExpr):
        condition_value = _resolve_inline_expr_value(expr.condition_expr, local_values=local_values)
        if isinstance(condition_value, LiteralExpr) and condition_value.literal_kind == "bool":
            branch = expr.then_expr if condition_value.value else expr.else_expr
            return _resolve_inline_expr_value(branch, local_values=local_values)
        return expr
    if isinstance(expr, ProviderBundlePathExpr):
        source_value = _resolve_inline_expr_value(expr.source_expr, local_values=local_values)
        projected = _projected_provider_bundle_ref(source_value)
        if projected is None:
            return expr
        return projected
    resolved = _resolve_expr_local_value(expr, local_values=local_values)
    if isinstance(resolved, (str, Mapping, LiteralExpr, RecordExpr, ProjectedPathRef)):
        return resolved
    if resolved is not None:
        if resolved is expr:
            return expr
        return _resolve_inline_expr_value(resolved, local_values=local_values)
    if isinstance(expr, NameExpr):
        bound = local_values.get(expr.name)
        if bound is None:
            return None
        if isinstance(bound, (str, Mapping)):
            return bound
        if bound is expr:
            return expr
        return _resolve_inline_expr_value(bound, local_values=local_values)
    if isinstance(expr, FieldAccessExpr):
        return _resolve_inline_field_value(
            local_values.get(expr.base.name),
            field_path=tuple(expr.fields),
            local_values=local_values,
        )
    return expr


def _loop_state_seed_inline_value(
    expr: LoopStateSeedExpr,
    *,
    local_values: Mapping[str, Any],
) -> Any:
    inline_value: dict[str, Any] = {}
    for field in expr.fields:
        resolved_value = _resolve_inline_expr_value(field.value_expr, local_values=local_values)
        if resolved_value is None:
            return expr
        inline_value[field.name] = resolved_value
    return inline_value


def _loop_state_update_inline_value(
    expr: LoopStateUpdateExpr,
    *,
    local_values: Mapping[str, Any],
) -> Any:
    base_value = _resolve_inline_expr_value(expr.base_expr, local_values=local_values)
    if not isinstance(base_value, Mapping):
        return expr
    updated_value = {name: _clone_inline_value(value) for name, value in base_value.items()}
    for field_name, field_expr in expr.overrides:
        resolved_value = _resolve_inline_expr_value(field_expr, local_values=local_values)
        if resolved_value is None:
            return expr
        updated_value[field_name] = resolved_value
    return updated_value


def _clone_inline_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _clone_inline_value(item)
            for key, item in value.items()
        }
    return value


def _build_output_step_local_value(
    output_refs: Mapping[str, str],
    *,
    type_ref: RecordTypeRef | UnionTypeRef | None = None,
    type_env: Any | None = None,
) -> dict[str, Any]:
    """Convert flattened terminal output refs into nested local-value shape."""

    field_paths = (
        dict(
            _flatten_boundary_leaf_paths(
                type_ref,
                generated_name="return",
                type_env=type_env,
            )
        )
        if type_ref is not None
        else {}
    )
    local_value: dict[str, Any] = {}
    for output_name, ref in output_refs.items():
        field_path = field_paths.get(
            output_name,
            tuple(output_name.removeprefix("return__").split("__")),
        )
        current = local_value
        for field_name in field_path[:-1]:
            next_current = current.get(field_name)
            if not isinstance(next_current, dict):
                next_current = {}
                current[field_name] = next_current
            current = next_current
        current[field_path[-1]] = ref
    return local_value


def _flatten_inline_output_refs(local_value: Any) -> dict[str, str]:
    """Flatten nested local-value mappings back into generated output refs."""

    if not isinstance(local_value, Mapping):
        return {}
    output_refs: dict[str, str] = {}

    def visit(value: Any, *, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {
                    "__lowering_returned_union_type",
                    "__typed_union_prompt_source__",
                }:
                    continue
                if isinstance(key, str):
                    visit(item, path=path + (key,))
            return
        if isinstance(value, str):
            output_refs[f"return__{'__'.join(path)}"] = value

    visit(local_value, path=())
    return output_refs


def _flatten_boundary_leaf_paths(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    generated_name: str,
    field_path: tuple[str, ...] = (),
    type_env: Any | None = None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return generated boundary names paired with frontend field paths."""

    if isinstance(type_ref, UnionTypeRef):
        return tuple(
            (field.generated_name, field_path + field.source_path[1:])
            for field in derive_workflow_boundary_fields(
                type_ref,
                generated_name=generated_name,
                source_path=(generated_name,),
                span=type_ref.definition.span,
                form_path=("workflow-lisp", "defunion", type_ref.name),
                type_env=type_env,
            )
        )
    flattened: list[tuple[str, tuple[str, ...]]] = []
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        next_generated_name = f"{generated_name}__{field.name}"
        next_field_path = field_path + (field.name,)
        if isinstance(field_type, (RecordTypeRef, UnionTypeRef)):
            flattened.extend(
                _flatten_boundary_leaf_paths(
                    field_type,
                    generated_name=next_generated_name,
                    field_path=next_field_path,
                    type_env=type_env,
                )
            )
            continue
        flattened.append((next_generated_name, next_field_path))
    return tuple(flattened)


def _record_expr_value_at_path(record_expr: RecordExpr, field_path: tuple[str, ...]) -> Any:
    """Read a nested field from an authored `record` expression."""

    current: Any = record_expr
    for field_name in field_path:
        if isinstance(current, RecordExpr):
            current = _record_field_value(current, field_name)
            continue
        if isinstance(current, UnionVariantExpr):
            current = _union_variant_expr_value_at_path(current, (field_name,))
            continue
        if not isinstance(current, RecordExpr):
            raise _value_compile_error(
                code="workflow_return_not_exportable",
                message=(
                    f"record return field `{'__'.join(field_path)}` must lower from nested record or variant expressions "
                    "when the workflow return type contains nested records"
                ),
                span=record_expr.span,
                form_path=record_expr.form_path,
            )
    return current


def _normalize_union_field_path(field_path: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for segment in field_path:
        normalized.extend(part for part in segment.split("__") if part)
    return tuple(normalized)


def _union_variant_expr_value_at_path(
    union_expr: UnionVariantExpr,
    field_path: tuple[str, ...],
    *,
    bound_record_fields: bool = False,
) -> Any:
    """Read a field from one compiler-generated union variant literal.

    `bound_record_fields` (target 2.33+) lets a nested record field populated
    from a bound name lower as a field access; older targets reject it.
    """

    field_path = _normalize_union_field_path(field_path)
    if not field_path:
        return union_expr
    field_name = field_path[0]
    if field_name == "variant":
        return LiteralExpr(
            value=union_expr.variant_name,
            literal_kind="string",
            span=union_expr.span,
            form_path=union_expr.form_path,
            expansion_stack=union_expr.expansion_stack,
        )
    for current_name, current_value in union_expr.fields:
        if current_name != field_name:
            continue
        if len(field_path) == 1:
            return current_value
        if isinstance(current_value, (RecordExpr, UnionVariantExpr)):
            return _record_expr_value_at_path(current_value, field_path[1:])
        if bound_record_fields and isinstance(current_value, NameExpr):
            # A nested record populated from a bound value: read the leaf
            # through the same field access an author would write.
            return FieldAccessExpr(
                base=current_value,
                fields=field_path[1:],
                span=current_value.span,
                form_path=current_value.form_path,
                expansion_stack=current_value.expansion_stack,
            )
        if bound_record_fields and isinstance(current_value, FieldAccessExpr):
            return replace(current_value, fields=current_value.fields + field_path[1:])
        raise _value_compile_error(
            code="workflow_return_not_exportable",
            message=(
                f"union return field `{'__'.join(field_path)}` must lower from nested record expressions "
                "when the workflow return type contains nested records"
            ),
            span=union_expr.span,
            form_path=union_expr.form_path,
        )
    return None


def _render_existing_output_ref(
    expr: Any,
    *,
    local_values: Mapping[str, Any],
    context: Any | None = None,
) -> str | None:
    """Return a shared runtime ref when an expression already names one."""

    if isinstance(expr, PhaseTargetExpr):
        if context is None or context.phase_scope is None:
            return None
        return context.phase_scope.target_refs.get(expr.target_name)
    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, ProjectedPathRef):
        return value.ref
    if not isinstance(value, str):
        return None
    if value.startswith(("root.steps.", "self.steps.", "parent.steps.", "inputs.")):
        return value
    return None


def lower_rich_structural_return(
    expr: Any,
    *,
    type_ref: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    span,
    form_path: tuple[str, ...],
) -> tuple[list[dict[str, Any]], _TerminalResult] | None:
    """Lower a new-target record/union terminal through the shared pure owner."""

    if (
        not target_dsl_supports_rich_loop_values(context.type_env.target_dsl_version)
        or not isinstance(type_ref, (RecordTypeRef, UnionTypeRef))
    ):
        return None
    from . import core as lowering_core
    from .pure_projection import is_pure_projection_expr, lower_pure_projection_step, output_contracts_for_boundary_type

    fields = tuple(
        derive_workflow_boundary_fields(
            type_ref,
            generated_name="return",
            source_path=("return",),
            span=span,
            form_path=form_path,
            type_env=context.type_env,
        )
    )
    direct_refs = lowering_core._inline_output_refs_for_expr(
        expr,
        type_ref=type_ref,
        local_values=local_values,
        context=context,
    )
    if direct_refs is not None and all(
        isinstance(direct_refs.get(field.generated_name), str) for field in fields
    ):
        return [], _TerminalResult(
            step_name=context.step_name_prefix,
            step_id=context.normalize_generated_step_id(context.step_name_prefix),
            output_refs=direct_refs,
            output_kind="projection",
            hidden_inputs={},
        )
    if not is_pure_projection_expr(expr):
        return None
    step_name = f"{context.step_name_prefix}__terminal_projection"
    step_id = context.normalize_generated_step_id(step_name)
    lowered = lower_pure_projection_step(
        expr,
        result_type=type_ref,
        context=context,
        local_values=local_values,
        step_name=step_name,
        step_id=step_id,
        stable_target="terminal_projection",
        output_contracts=output_contracts_for_boundary_type(
            type_ref,
            generated_name="return",
            span=span,
            form_path=form_path,
            type_env=context.type_env,
        ),
        output_fields=fields,
    )
    return [lowered.step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=lowered.output_refs,
        output_kind="projection",
        hidden_inputs={},
    )


def _assign_nested_local_value(target: dict[str, Any], field_path: tuple[str, ...], ref: str) -> None:
    """Assign a flattened ref into a nested local-value mapping."""

    current = target
    for field_name in field_path[:-1]:
        nested = current.get(field_name)
        if not isinstance(nested, dict):
            nested = {}
            current[field_name] = nested
        current = nested
    current[field_path[-1]] = ref


def _flatten_record_output_refs(step_name: str, type_ref: RecordTypeRef) -> dict[str, str]:
    """Build flattened workflow return refs for a record-producing step."""

    return {
        f"return__{'__'.join(field_path)}": f"root.steps.{step_name}.artifacts.{'__'.join(field_path)}"
        for _, field_path in _flatten_boundary_leaf_paths(type_ref, generated_name="return")
    }

def _render_provider_artifact_ref(provider_step_name: str, field_access: FieldAccessExpr) -> str | None:
    """Render a provider result field access as a step artifact ref."""

    if not field_access.fields:
        return None
    return f"root.steps.{provider_step_name}.artifacts.{'__'.join(field_access.fields)}"


def _record_output_refs(step_name: str, type_ref: Any, *, use_site: Any | None = None) -> dict[str, str]:
    """Return flattened output refs for a record, union, or direct-root result type.

    Structural and type-driven, matching `GeneratedBundleContract.result_shape`
    (`orchestrator/workflow_lisp/contracts.py`): every non-record/non-union
    transportable type lowers to one generated `__result__` artifact (see
    `docs/design/workflow_lisp_native_transportable_returns.md`).
    """

    if isinstance(type_ref, RecordTypeRef):
        return _flatten_record_output_refs(step_name, type_ref)
    if isinstance(type_ref, UnionTypeRef):
        from ..generic_unions import diagnostics_at_use_site

        with diagnostics_at_use_site(type_ref, use_site):
            leaf_paths = _flatten_boundary_leaf_paths(type_ref, generated_name="return")
        return {
            output_name: f"root.steps.{step_name}.artifacts.{'__'.join(field_path)}"
            for output_name, field_path in leaf_paths
        }
    return {"return": f"root.steps.{step_name}.artifacts.__result__"}


def _flatten_return_output_names(context: _LoweringContext) -> tuple[str, ...]:
    """Return flattened output names for the active workflow return contract."""

    return tuple(f"return__{field_name}" for field_name in context.return_output_contracts)


def _return_field_path(field_name: str) -> tuple[str, ...]:
    """Convert a flattened return field name into a nested field path."""

    return tuple(field_name.split("__"))

def _inline_expr_field_value(
    expr: Any,
    *,
    field_path: tuple[str, ...],
    local_values: Mapping[str, Any],
    context: _LoweringContext | None = None,
) -> Any:
    """Resolve one projected leaf from an inline branch expression."""

    if isinstance(expr, RecordExpr):
        value = _record_expr_value_at_path(expr, field_path)
        if isinstance(value, PhaseTargetExpr) and context is not None:
            return _phase_target_inline_ref(value, context=context)
        return _resolve_inline_expr_value(value, local_values=local_values)
    if isinstance(expr, UnionVariantExpr):
        value = _union_variant_expr_value_at_path(
            expr,
            field_path,
            bound_record_fields=context is not None
            and target_dsl_supports_generic_unions(context.type_env.target_dsl_version),
        )
        if isinstance(value, PhaseTargetExpr) and context is not None:
            return _phase_target_inline_ref(value, context=context)
        return _resolve_inline_expr_value(value, local_values=local_values)
    if isinstance(expr, PhaseTargetExpr) and context is not None:
        return _phase_target_inline_ref(expr, context=context)
    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if field_path:
        return _resolve_nested_local_value(value, field_path)
    return value


def _phase_target_inline_ref(expr: PhaseTargetExpr, *, context: _LoweringContext) -> str:
    """Resolve a direct phase-target projection to the active phase reference."""

    phase_scope = context.phase_scope
    if phase_scope is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="phase-target lowering requires an active phase scope",
            span=expr.span,
            form_path=expr.form_path,
        )
    target_ref = phase_scope.target_refs.get(expr.target_name)
    if target_ref is None:
        raise _compile_error(
            code="phase_target_unknown",
            message=f"`phase-target` does not support `{expr.target_name}` in this slice",
            span=expr.span,
            form_path=expr.form_path,
        )
    return target_ref

def _lower_record_expr(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Project a record return expression from existing step-backed refs."""

    from .control_loops import _materialize_values_step

    record_expr = typed_expr.expr
    assert isinstance(record_expr, RecordExpr)
    step_name = context.step_name_prefix
    step_id = context.normalize_generated_step_id(step_name)
    direct_output_refs: dict[str, str] = {}
    values: list[dict[str, Any]] = []
    for field_name in context.return_output_contracts:
        output_name = f"return__{field_name}"
        value = _record_expr_value_at_path(record_expr, _return_field_path(field_name))
        resolved_value = _resolve_inline_expr_value(value, local_values=local_values)
        if isinstance(resolved_value, ProjectedPathRef):
            context.output_projection_metadata[output_name] = {
                **dict(resolved_value.projection),
                "projection_id": f"{context.workflow_name}:{output_name}",
                "projected_output_name": output_name,
            }
        source_ref = _render_existing_output_ref(value, local_values=local_values, context=context)
        if source_ref is not None:
            direct_output_refs[output_name] = source_ref
            values.append(
                {
                    "name": field_name,
                    "source": {"ref": source_ref},
                    "contract": dict(context.return_output_contracts[field_name]),
                }
            )
            continue
        if isinstance(resolved_value, LiteralExpr):
            values.append(
                {
                    "name": field_name,
                    "source": {"literal": resolved_value.value},
                    "contract": dict(context.return_output_contracts[field_name]),
                }
            )
            continue
        raise _compile_error(
            code="workflow_return_not_exportable",
            message=(
                f"record return field `{field_name}` must lower from an existing step artifact "
                "or structured statement output in this Stage 3 slice"
            ),
            span=record_expr.span,
            form_path=record_expr.form_path,
        )
    if all(
        source_ref.startswith("root.steps.")
        or (
            isinstance(context.output_projection_metadata.get(output_name), Mapping)
            and context.output_projection_metadata[output_name].get("projection_class")
            == "provider_bundle_path_projection"
            and context.output_projection_metadata[output_name].get("bundle_path_ref") == source_ref
        )
        for output_name, source_ref in direct_output_refs.items()
    ):
        return [], _TerminalResult(
            step_name=step_name,
            step_id=step_id,
            output_refs=direct_output_refs,
            output_kind="projection",
            hidden_inputs={},
        )
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=record_expr)
    step = _materialize_values_step(step_name=step_name, step_id=step_id, values=values)
    return [step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=_record_output_refs(step_name, typed_expr.type_ref),
        output_kind="step",
        hidden_inputs={},
    )


def _lower_union_variant_expr(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Materialize one compiler-generated union variant through workflow outputs."""

    from .control_loops import _materialize_values_step
    from .phase_scope import _surface_contract_from_structured_field

    union_expr = typed_expr.expr
    assert isinstance(union_expr, UnionVariantExpr)
    assert isinstance(typed_expr.type_ref, UnionTypeRef)
    step_name = context.step_name_prefix
    step_id = context.normalize_generated_step_id(step_name)
    if step_name != context.workflow_name:
        values: list[dict[str, Any]] = []
        placeholders = _boundary_placeholder_literals(
            typed_expr.type_ref,
            span=union_expr.span,
            form_path=union_expr.form_path,
        )
        active_field_names = {name for name, _ in union_expr.fields}
        for field in derive_workflow_boundary_fields(
            typed_expr.type_ref,
            generated_name="return",
            source_path=("return",),
            span=union_expr.span,
            form_path=union_expr.form_path,
        ):
            field_path = _normalize_union_field_path(field.source_path[1:])
            field_name = field_path[0] if field_path else ""
            contract = dict(field.contract_definition)
            if field_name == "variant":
                source = {"literal": union_expr.variant_name}
            elif field_name in active_field_names:
                leaf_expr = _union_variant_expr_value_at_path(
                    union_expr,
                    field_path,
                    bound_record_fields=target_dsl_supports_generic_unions(context.type_env.target_dsl_version),
                )
                leaf_value = _resolve_inline_expr_value(leaf_expr, local_values=local_values)
                if isinstance(leaf_value, LiteralExpr):
                    source = {"literal": leaf_value.value}
                elif isinstance(leaf_value, str):
                    source = {"ref": leaf_value}
                else:
                    raise _compile_error(
                        code="workflow_return_not_exportable",
                        message=(
                            f"union return field `{field.generated_name}` must lower from an existing step artifact "
                            "or literal in this Stage 3 slice"
                        ),
                        span=leaf_expr.span,
                        form_path=leaf_expr.form_path,
                    )
            else:
                source = {"literal": placeholders[field.generated_name]}
                if contract.get("type") == "relpath":
                    contract["must_exist_target"] = False
            values.append(
                {
                    "name": field.generated_name,
                    "source": source,
                    "contract": contract,
                }
            )
        _record_step_origin(context, step_name=step_name, step_id=step_id, source=union_expr)
        step = _materialize_values_step(step_name=step_name, step_id=step_id, values=values)
        return [step], _TerminalResult(
            step_name=step_name,
            step_id=step_id,
            output_refs={
                field.generated_name: f"root.steps.{step_name}.artifacts.{field.generated_name}"
                for field in derive_workflow_boundary_fields(
                    typed_expr.type_ref,
                    generated_name="return",
                    source_path=("return",),
                    span=union_expr.span,
                    form_path=union_expr.form_path,
                )
            },
            output_kind="step",
            hidden_inputs={},
            returned_union_type_name=typed_expr.type_ref.name,
            returned_union_variant_name=union_expr.variant_name,
        )
    bundle_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=union_expr.span,
        form_path=union_expr.form_path,
    )
    _register_generated_contract_field_bindings(context, bundle_contract.field_origins)
    allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=union_expr,
        step_name=step_name,
        step_id=step_id,
        semantic_role=GeneratedPathSemanticRole.VARIANT_PROJECTION_BUNDLE,
    )
    authored_contract = dict(bundle_contract.payload)
    authored_contract["path"] = allocation.concrete_path_template
    bound_record_fields = target_dsl_supports_generic_unions(context.type_env.target_dsl_version)
    values: list[dict[str, Any]] = []
    values.append(
        {
            "name": "variant",
            "source": {"literal": union_expr.variant_name},
            "contract": _surface_contract_from_structured_field(authored_contract["discriminant"]),
        }
    )
    for field in authored_contract.get("shared_fields", ()):
        values.append(
            {
                "name": field["name"],
                "source": _union_variant_materialize_source(
                    union_expr,
                    field_path=(field["name"],),
                    local_values=local_values,
                    bound_record_fields=bound_record_fields,
                ),
                "contract": _surface_contract_from_structured_field(field),
            }
        )
    for field in authored_contract["variants"][union_expr.variant_name]["fields"]:
        values.append(
            {
                "name": field["name"],
                "source": _union_variant_materialize_source(
                    union_expr,
                    field_path=(field["name"],),
                    local_values=local_values,
                    bound_record_fields=bound_record_fields,
                ),
                "contract": _surface_contract_from_structured_field(field),
            }
        )
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=union_expr)
    step = {
        **_materialize_values_step(step_name=step_name, step_id=step_id, values=values),
        bundle_contract.contract_kind: authored_contract,
    }
    output_refs = {}
    for field in derive_workflow_boundary_fields(
        typed_expr.type_ref,
        generated_name="return",
        source_path=("return",),
        span=union_expr.span,
        form_path=union_expr.form_path,
    ):
        field_path = _normalize_union_field_path(field.source_path[1:])
        output_refs[field.generated_name] = f"root.steps.{step_name}.artifacts.{'__'.join(field_path)}"
    return [step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=output_refs,
        output_kind="step",
        hidden_inputs={allocation.generated_input_name: _origin_from_context_source(context, union_expr)},
        returned_union_type_name=typed_expr.type_ref.name,
        returned_union_variant_name=union_expr.variant_name,
    )
