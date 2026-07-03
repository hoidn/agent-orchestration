"""Pending parametric specialization materialization for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from .procedures import TypedProcedureDef, procedure_type_env_for
from .type_env import FrontendTypeEnvironment

if TYPE_CHECKING:
    from .procedure_typecheck import PendingParametricProcedureSpecialization


def materialize_pending_parametric_specialization(
    request: "PendingParametricProcedureSpecialization",
    *,
    procedure_targets: Mapping[str, object],
    visible_typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    typed_procedures: tuple[TypedProcedureDef, ...],
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
) -> TypedProcedureDef | None:
    """Build one typed specialization target for the next stage-3 iteration."""

    from .procedure_specialization import specialize_typed_procedure

    if request.specialized_name in procedure_targets:
        return None

    typed_by_name = {
        **visible_typed_procedures_by_name,
        **{procedure.definition.name: procedure for procedure in typed_procedures},
    }
    base_procedure = typed_by_name.get(request.base_name)
    if base_procedure is None:
        return None

    return specialize_typed_procedure(
        base_procedure,
        type_bindings=request.type_bindings,
        proc_ref_bindings=request.proc_ref_bindings,
        shared_union_field_capabilities=request.shared_union_field_capabilities,
        remaining_params=request.remaining_params,
        workflow_path=Path(base_procedure.definition.span.start.path),
        type_env=procedure_type_env_for(
            base_procedure,
            procedure_type_envs=procedure_type_envs,
            default=type_env,
        ),
        typed_procedures_by_name=typed_by_name,
        procedure_type_envs=procedure_type_envs,
        specialized_name=request.specialized_name,
        origin_span=request.origin_span,
        origin_form_path=request.origin_form_path,
        defer_lowering_resolution=True,
    )
