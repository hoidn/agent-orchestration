"""Inert shared lowering leaf for one typed ``run-ref`` effect."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from orchestrator.workflow.run_ref.config import (
    LiteralBinding,
    ReferenceBinding,
    RunRefInput,
    build_run_ref_static_config,
)
from orchestrator.workflow.run_ref.contracts import (
    VerifiedCompilerRuntimeIdentity,
    compute_compiler_runtime_identity,
)
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from ..expressions import LiteralExpr
from ..normalized_type_descriptor import compiler_normalized_type_descriptor
from ..run_ref_result_contract import (
    derive_run_ref_output_bundle_fields,
    derive_run_ref_result_contract,
)
from ..type_env import RecordTypeRef, TypeRef
from .context import _compile_error, _LoweringContext, _TerminalResult
from .generated_paths import allocate_generated_result_bundle
from .origins import _origin_from_context_source, _record_step_origin
from .values import ProjectedPathRef, _record_output_refs, _resolve_inline_expr_value

if TYPE_CHECKING:
    from ..wcc.model import WccRunRefPayload


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


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

    if not isinstance(run_ref, LowerableRunRef):
        raise TypeError("run-ref lowering requires LowerableRunRef")
    if not isinstance(result_type, RecordTypeRef):
        raise TypeError("run-ref lowering requires its generated record result")
    contract = derive_run_ref_result_contract(
        result_type,
        type_env=context.type_env,
    )
    if (
        result_type.name != run_ref.payload.generated_result_type
        or contract.descriptor != run_ref.payload.result_descriptor
        or contract.digest != run_ref.payload.result_digest
    ):
        raise ValueError("run-ref result metadata changed before lowering")
    output_fields = derive_run_ref_output_bundle_fields(contract)

    payload_descriptors = run_ref.payload.input_type_descriptors
    if len(run_ref.inputs) != len(payload_descriptors):
        raise ValueError("run-ref input metadata changed before lowering")
    lowered_inputs: list[RunRefInput] = []
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
        lowered_inputs.append(
            RunRefInput(
                name=row.name,
                type_descriptor=payload_descriptor,
                binding=_scalar_or_reference_binding(
                    row,
                    local_values=local_values,
                ),
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
    )
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
    step = {
        "name": step_name,
        "id": step_id,
        "output_bundle": {
            "path": allocation.concrete_path_template,
            "fields": output_fields,
        },
        "run_ref": config,
    }
    return [step], _TerminalResult(
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
        checkpoint_identity_component_digest=None,
    )


def _scalar_or_reference_binding(
    row: LowerableRunRefInput,
    *,
    local_values: Mapping[str, object],
):
    resolved = _resolve_inline_expr_value(
        row.value_expr,
        local_values=local_values,
    )
    if isinstance(resolved, LiteralExpr):
        return LiteralBinding(resolved.value)
    if isinstance(resolved, ProjectedPathRef):
        return ReferenceBinding(resolved.ref)
    if isinstance(resolved, str):
        return ReferenceBinding(resolved)
    if (
        isinstance(resolved, Mapping)
        and set(resolved) == {"ref"}
        and isinstance(resolved.get("ref"), str)
    ):
        return ReferenceBinding(resolved["ref"])
    raise _compile_error(
        code="run_ref_input_binding_unsupported",
        message=(
            "run-ref input requires a scalar literal or canonical runtime "
            "reference in this lowering slice"
        ),
        span=getattr(row.value_expr, "span"),
        form_path=getattr(row.value_expr, "form_path", ()),
    )
