"""Compile-time lowering contracts for supported Workflow Lisp stdlib forms."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .expressions import (
    BacklogDrainExpr,
    CommandResultExpr,
    FinalizeSelectedItemExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    StdlibSpecializationExpr,
)


@dataclass(frozen=True)
class StdlibLoweringContract:
    form_name: str
    expr_type: type[Any]
    family: str
    backend_kinds: tuple[str, ...]
    required_statement_families: tuple[str, ...]
    alternative_statement_family_sets: tuple[tuple[str, ...], ...]
    delegated_statement_family_policy: str
    state_root_policies: tuple[str, ...]
    authority_model: str
    proof_model: str
    source_map_expectations: tuple[str, ...]
    primary_diagnostics: tuple[str, ...]
    helper_owner_modules: tuple[str, ...]
    adapter_binding_names: tuple[str, ...]
    test_surfaces: tuple[str, ...]


STDLIB_LOWERING_CONTRACTS: tuple[StdlibLoweringContract, ...] = (
    StdlibLoweringContract(
        form_name="provider-result",
        expr_type=ProviderResultExpr,
        family="structured_result_producer",
        backend_kinds=("provider",),
        required_statement_families=("provider_step",),
        alternative_statement_family_sets=(("output_bundle", "variant_output"),),
        delegated_statement_family_policy="none",
        state_root_policies=("generated_hidden_bundle_input", "active_phase_bundle"),
        authority_model="validated_structured_result_bundle",
        proof_model="contract_validated_bundle",
        source_map_expectations=(
            "high_level_form_origin",
            "generated_step_span",
            "generated_hidden_input_span",
            "generated_hidden_path_span",
        ),
        primary_diagnostics=("provider_result_provider_invalid",),
        helper_owner_modules=("typecheck", "lowering"),
        adapter_binding_names=(),
        test_surfaces=("tests.test_workflow_lisp_lowering",),
    ),
    StdlibLoweringContract(
        form_name="command-result",
        expr_type=CommandResultExpr,
        family="structured_result_producer",
        backend_kinds=("external_tool", "certified_adapter"),
        required_statement_families=("command_step",),
        alternative_statement_family_sets=(("output_bundle", "variant_output"),),
        delegated_statement_family_policy="none",
        state_root_policies=("generated_hidden_bundle_input",),
        authority_model="validated_structured_result_bundle",
        proof_model="contract_validated_bundle",
        source_map_expectations=(
            "high_level_form_origin",
            "generated_step_span",
            "generated_hidden_input_span",
            "generated_hidden_path_span",
            "adapter_command_step_origin",
        ),
        primary_diagnostics=("command_boundary_missing",),
        helper_owner_modules=("typecheck", "lowering"),
        adapter_binding_names=(),
        test_surfaces=(
            "tests.test_workflow_lisp_lowering",
            "tests.test_workflow_lisp_drain_stdlib",
        ),
    ),
    StdlibLoweringContract(
        form_name="run-provider-phase",
        expr_type=RunProviderPhaseExpr,
        family="structured_result_producer",
        backend_kinds=("provider",),
        required_statement_families=("materialize_artifacts", "provider_step"),
        alternative_statement_family_sets=(("output_bundle", "variant_output"),),
        delegated_statement_family_policy="none",
        state_root_policies=("active_phase_bundle",),
        authority_model="validated_structured_result_bundle",
        proof_model="contract_validated_bundle",
        source_map_expectations=(
            "high_level_form_origin",
            "generated_step_span",
            "generated_hidden_path_span",
        ),
        primary_diagnostics=("phase_translation_body_invalid", "phase_scope_name_mismatch"),
        helper_owner_modules=("phase_stdlib", "typecheck", "lowering"),
        adapter_binding_names=(),
        test_surfaces=("tests.test_workflow_lisp_phase_stdlib",),
    ),
    StdlibLoweringContract(
        form_name="produce-one-of",
        expr_type=ProduceOneOfExpr,
        family="structured_result_producer",
        backend_kinds=("provider",),
        required_statement_families=(
            "materialize_artifacts",
            "pre_snapshot",
            "provider_step",
            "select_variant_output",
            "match",
        ),
        alternative_statement_family_sets=(),
        delegated_statement_family_policy="none",
        state_root_policies=("active_phase_bundle_plus_snapshot",),
        authority_model="validated_selected_variant_bundle",
        proof_model="snapshot_diff_variant_selection",
        source_map_expectations=(
            "high_level_form_origin",
            "generated_step_span",
            "generated_hidden_path_span",
        ),
        primary_diagnostics=("phase_translation_body_invalid", "provider_result_provider_invalid"),
        helper_owner_modules=("phase_stdlib", "typecheck", "lowering"),
        adapter_binding_names=(),
        test_surfaces=("tests.test_workflow_lisp_phase_stdlib",),
    ),
    StdlibLoweringContract(
        form_name="review-revise-loop",
        expr_type=StdlibSpecializationExpr,
        family="review_reuse_control",
        backend_kinds=("provider", "certified_adapter"),
        required_statement_families=(
            "repeat_until",
            "workflow_call",
            "command_step",
            "output_bundle",
            "match",
            "materialize_artifacts",
        ),
        alternative_statement_family_sets=(),
        delegated_statement_family_policy="none",
        state_root_policies=("repeat_until_generated_bundle",),
        authority_model="validated_repeat_until_route_bundle",
        proof_model="typed_review_decision_routing",
        source_map_expectations=(
            "high_level_form_origin",
            "generated_step_span",
            "generated_hidden_input_span",
            "generated_hidden_path_span",
            "adapter_command_step_origin",
        ),
        primary_diagnostics=("review_loop_result_contract_invalid", "phase_scope_name_mismatch"),
        helper_owner_modules=("phase_stdlib", "typecheck", "lowering"),
        adapter_binding_names=("validate_review_findings_v1",),
        test_surfaces=("tests.test_workflow_lisp_phase_stdlib",),
    ),
    StdlibLoweringContract(
        form_name="resume-or-start",
        expr_type=ResumeOrStartExpr,
        family="review_reuse_control",
        backend_kinds=("certified_adapter",),
        required_statement_families=("command_step", "variant_output", "match"),
        alternative_statement_family_sets=(),
        delegated_statement_family_policy="resume_start_branch_delegates_to_wrapped_expression",
        state_root_policies=("managed_reusable_boundary_inputs",),
        authority_model="validated_reusable_state_boundary",
        proof_model="reusable_state_validation_then_branch_normalization",
        source_map_expectations=(
            "high_level_form_origin",
            "generated_step_span",
            "generated_hidden_input_span",
            "generated_hidden_path_span",
            "adapter_command_step_origin",
        ),
        primary_diagnostics=("resume_or_start_uncertified_backend", "resume_or_start_contract_invalid"),
        helper_owner_modules=("phase_stdlib", "typecheck", "lowering", "compiler"),
        adapter_binding_names=(
            "validate_reusable_phase_state",
            "write_reusable_phase_state_v1",
            "load_canonical_phase_result__<ReturnType>",
        ),
        test_surfaces=("tests.test_workflow_lisp_phase_stdlib",),
    ),
    StdlibLoweringContract(
        form_name="resource-transition",
        expr_type=ResourceTransitionExpr,
        family="resource_finalize_drain",
        backend_kinds=("certified_adapter",),
        required_statement_families=("command_step", "output_bundle"),
        alternative_statement_family_sets=(),
        delegated_statement_family_policy="none",
        state_root_policies=("generated_hidden_bundle_input",),
        authority_model="validated_structured_result_bundle",
        proof_model="contract_validated_bundle",
        source_map_expectations=(
            "high_level_form_origin",
            "generated_step_span",
            "generated_hidden_input_span",
            "generated_hidden_path_span",
            "adapter_command_step_origin",
        ),
        primary_diagnostics=("resource_transition_contract_invalid", "command_adapter_missing_contract"),
        helper_owner_modules=("resource_stdlib", "resource", "typecheck", "lowering", "compiler"),
        adapter_binding_names=("apply_resource_transition",),
        test_surfaces=("tests.test_workflow_lisp_resource_stdlib",),
    ),
    StdlibLoweringContract(
        form_name="finalize-selected-item",
        expr_type=FinalizeSelectedItemExpr,
        family="resource_finalize_drain",
        backend_kinds=("materialize_only",),
        required_statement_families=("match", "materialize_artifacts", "publishes"),
        alternative_statement_family_sets=(),
        delegated_statement_family_policy="none",
        state_root_policies=("item_or_drain_layout_projection",),
        authority_model="match_routed_published_summary",
        proof_model="typed_branch_normalization",
        source_map_expectations=(
            "high_level_form_origin",
            "generated_step_span",
            "generated_hidden_path_span",
        ),
        primary_diagnostics=("finalize_selected_item_contract_invalid",),
        helper_owner_modules=("resource_stdlib", "resource", "typecheck", "lowering"),
        adapter_binding_names=(),
        test_surfaces=("tests.test_workflow_lisp_resource_stdlib",),
    ),
    StdlibLoweringContract(
        form_name="backlog-drain",
        expr_type=BacklogDrainExpr,
        family="resource_finalize_drain",
        backend_kinds=("workflow_call",),
        required_statement_families=(
            "repeat_until",
            "workflow_call",
            "materialize_artifacts",
            "match",
            "publishes",
        ),
        alternative_statement_family_sets=(),
        delegated_statement_family_policy="none",
        state_root_policies=("managed_reusable_boundary_inputs", "item_or_drain_layout_projection"),
        authority_model="loop_accumulator_normalized_result",
        proof_model="typed_loop_accumulator_normalization",
        source_map_expectations=("high_level_form_origin", "generated_step_span"),
        primary_diagnostics=("backlog_drain_contract_invalid", "workflow_call_signature_erased"),
        helper_owner_modules=("drain_stdlib", "typecheck", "lowering"),
        adapter_binding_names=(),
        test_surfaces=("tests.test_workflow_lisp_drain_stdlib",),
    ),
)

STDLIB_LOWERING_CONTRACTS_BY_FORM: Mapping[str, StdlibLoweringContract] = MappingProxyType(
    {contract.form_name: contract for contract in STDLIB_LOWERING_CONTRACTS}
)
_STDLIB_LOWERING_CONTRACTS_BY_EXPR: Mapping[type[Any], StdlibLoweringContract] = MappingProxyType(
    {contract.expr_type: contract for contract in STDLIB_LOWERING_CONTRACTS}
)


def stdlib_contract_for_expr(expr_or_type: object) -> StdlibLoweringContract:
    expr_type = expr_or_type if isinstance(expr_or_type, type) else type(expr_or_type)
    contract = _STDLIB_LOWERING_CONTRACTS_BY_EXPR.get(expr_type)
    if contract is None:
        raise KeyError(f"missing stdlib lowering contract for `{expr_type.__name__}`")
    return contract
