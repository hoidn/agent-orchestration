"""Compatibility shim for split phase/resource/drain lowering helpers."""

from .phase_scope import (
    _build_phase_prompt_input_prelude,
    _build_phase_stdlib_prompt_input_prelude,
    _flatten_phase_stdlib_prompt_inputs,
    _join_ref_path,
    _lower_composed_with_phase,
    _lower_workflow_outputs,
    _phase_prompt_inputs_are_direct,
    _phase_prompt_artifact_definition,
    _phase_prompt_input_pointer_path,
    _require_phase_scope_name_match,
    _resolve_active_phase_scope,
    _resolved_proc_ref_value,
    _resolved_workflow_ref_value,
    _surface_contract_from_structured_field,
    _template_for_ref,
    _union_output_contracts,
    _uses_legacy_phase_prompt_input_prelude,
    _workflow_extern_requirements,
)
