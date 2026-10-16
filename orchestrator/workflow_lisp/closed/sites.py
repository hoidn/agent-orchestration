"""Compatibility imports for the shared closed-program site owner."""

from orchestrator.contracts.closed_program.sites import (
    SEPARATOR,
    _ESCAPED_LABEL_CHARS,
    SiteAssignmentError,
    _escape_label,
    _Scope,
    assign_sites,
    _definition_order,
    _validate_call_graph,
    _call_nodes,
    _bound_calls,
    _value_calls,
    _clear_annotations,
    _ast_nodes,
    _bound_nodes,
    _value_nodes,
    _arm_root_values,
    effect_value_operands,
    _effect_value_children,
    _SiteWalker,
    _value_children,
)
