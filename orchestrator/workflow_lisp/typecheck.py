"""Workflow Lisp typecheck compatibility facade."""

from __future__ import annotations

from .typecheck_calls import (
    hidden_context_omission_allowed as _hidden_context_omission_allowed,
    typecheck_proc_ref_argument as _typecheck_proc_ref_argument,
    typecheck_workflow_ref_argument as _typecheck_workflow_ref_argument,
)
from .typecheck_context import (
    TypedExpr,
    ValueEnvironment,
    clear_active_reusable_state_producer_context,
    clear_active_workflow_signature,
    consume_generated_local_procedures,
    raise_error as _raise_error,
    raise_required_lint as _raise_required_lint,
    reset_generated_local_procedure_state,
    set_active_reusable_state_producer_context,
    set_active_workflow_signature,
    _require_normative_phase_ctx_type,
    _require_phase_scope_name_match,
)
from .typecheck_dispatch import typecheck_expression
from .typecheck_effects import (
    is_macro_introduced_effect as _is_macro_introduced_effect,
    validate_command_argv as _validate_command_argv,
    validate_semantic_command_adapter_usage as _validate_semantic_command_adapter_usage,
)
from .typecheck_proofs import (
    ProofFact,
    ProofScope,
    resolve_field_access as _resolve_field_access,
)

__all__ = [
    "ProofFact",
    "ProofScope",
    "TypedExpr",
    "ValueEnvironment",
    "clear_active_reusable_state_producer_context",
    "clear_active_workflow_signature",
    "consume_generated_local_procedures",
    "reset_generated_local_procedure_state",
    "set_active_reusable_state_producer_context",
    "set_active_workflow_signature",
    "typecheck_expression",
]
