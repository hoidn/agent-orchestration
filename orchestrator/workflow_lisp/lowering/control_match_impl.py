"""Compatibility shim for match-family lowering owners."""

from .control_match import (
    _binding_terminal_for_inline_match,
    _binding_terminal_for_match_subject,
    _build_match_projection_anchor_step,
    _lower_match_expr,
    _match_arm_local_values,
)
