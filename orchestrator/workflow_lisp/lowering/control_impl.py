"""Compatibility shim for the split control lowering owners."""

from .control_dispatch import _is_inline_let_binding_expr, _lower_expression, _lower_if_expr, _lower_let_star
from .control_loops import _conditional_case_ref, _inline_procedure_step_prefix, _lower_loop_recur, _materialize_values_step
from .control_match import (
    _binding_terminal_for_inline_match,
    _binding_terminal_for_match_subject,
    _build_match_projection_anchor_step,
    _lower_match_expr,
    _match_arm_local_values,
)
