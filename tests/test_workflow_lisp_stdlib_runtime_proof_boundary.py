from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.workflow.executable_ir import validate_executable_workflow
from orchestrator.workflow_lisp.compiler import Stage3ValidationProfile, compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lowering.core import validate_lowered_workflows
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding
from tests.test_workflow_lisp_stdlib_form_migration import (
    DRAIN_STDLIB_FIXTURE,
    _command_boundary_environment,
    _control_dispatch_module,
)


ENTRY_WORKFLOW_NAME = "drain_stdlib_backlog_drain_stdlib::drain"
EXPECTED_PLACEHOLDER_BOUNDARIES = frozenset(
    {"select_next_item", "draft_gap_item", "execute_selected_item", "apply_resource_transition"}
)


def _compile_linked_fixture(
    path: Path,
    *,
    tmp_path: Path,
    **compile_kwargs: object,
):
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries=_command_boundary_environment().bindings_by_name,
        workspace_root=tmp_path,
        **compile_kwargs,
    )


def _selected_lowered_workflow(result):
    return next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == ENTRY_WORKFLOW_NAME
    )


def _observed_command_boundary_names(result) -> set[str]:
    names: set[str] = set()
    for bundle in result.validated_bundles_by_name.values():
        names.update(
            boundary.boundary_name
            for boundary in bundle.semantic_ir.command_boundaries.values()
            if isinstance(boundary.boundary_name, str)
        )
    return names


def _replace_entry_lowered_workflow(result, replacement):
    return tuple(
        replacement if workflow.typed_workflow.definition.name == ENTRY_WORKFLOW_NAME else workflow
        for workflow in result.entry_result.lowered_workflows
    )


def test_dedicated_runtime_proof_profile_builds_validated_entry_bundle_for_imported_stdlib_drain(
    tmp_path: Path,
) -> None:
    dispatch = _control_dispatch_module()
    dispatch.reset_intrinsic_form_lowering_counts()

    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )

    assert result.entry_result.validation_profile.name == "DEDICATED_RUNTIME_PROOF"
    bundle = result.entry_result.validated_bundles[ENTRY_WORKFLOW_NAME]
    validate_executable_workflow(bundle.ir)
    assert result.validated_bundles_by_name[ENTRY_WORKFLOW_NAME] is bundle
    assert dispatch.intrinsic_form_lowering_counts().get("backlog-drain", 0) == 0


def test_shared_callable_profile_keeps_generated_structured_branch_guard_active(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_fixture(
            DRAIN_STDLIB_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    diagnostics = [diag for diag in excinfo.value.diagnostics if diag.code == "workflow_boundary_type_invalid"]

    assert len(diagnostics) == 2
    assert all("structured if/else is only supported on top-level steps in v2.2" in diag.message for diag in diagnostics)
    assert any("__terminal__body__gap" in diag.message for diag in diagnostics)
    assert any("__terminal__body__selected" in diag.message for diag in diagnostics)


def test_frontend_only_profile_keeps_entry_validated_bundles_empty_for_linked_fixture(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=False,
    )

    assert result.entry_result.validated_bundles == {}


def test_runtime_proof_profile_records_non_promotable_boundary_evidence_and_source_map_lineage(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )

    lowered = _selected_lowered_workflow(result)
    retained = result.entry_result.retained_non_promotable_diagnostics

    assert any(diag.code == "low_level_state_path_in_high_level_module" for diag in retained)
    structured = [diag for diag in retained if diag.code == "workflow_boundary_type_invalid"]
    assert len(structured) == 2
    assert any("__terminal__body__gap" in diag.message for diag in structured)
    assert any("__terminal__body__selected" in diag.message for diag in structured)
    assert any("__terminal__body__gap" in step_id for step_id in lowered.origin_map.step_spans)
    assert any("__terminal__body__selected" in step_id for step_id in lowered.origin_map.step_spans)
    assert any("materialize-view__drain-summary" in step_id for step_id in lowered.origin_map.step_spans)
    assert any("artifacts/work/drain-progress-report.md" in path for path in lowered.origin_map.generated_path_spans)
    assert any("state/drain-run-state.json" in path for path in lowered.origin_map.generated_path_spans)


def test_runtime_proof_profile_keeps_placeholder_command_boundaries_certified(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )

    bindings = result.entry_result.command_boundary_environment.bindings_by_name
    observed = _observed_command_boundary_names(result)
    raw_suffixes = {
        name.rsplit("__", 1)[-1]
        for name in observed
        if not name.endswith("__managed_write_roots")
    }

    assert raw_suffixes >= {"select_next_item", "draft_gap_item", "execute_selected_item"}
    assert raw_suffixes <= EXPECTED_PLACEHOLDER_BOUNDARIES
    assert all(name.endswith("__managed_write_roots") or name.rsplit("__", 1)[-1] in EXPECTED_PLACEHOLDER_BOUNDARIES for name in observed)
    for name in raw_suffixes:
        binding = bindings[name]
        assert isinstance(binding, CertifiedAdapterBinding)
        assert binding.stable_command
        assert binding.fixture_ids


def test_runtime_proof_profile_rejects_authored_nested_structured_steps_even_when_metadata_lists_them(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=False,
    )
    lowered = _selected_lowered_workflow(result)
    authored = deepcopy(lowered.authored_mapping)
    gap_steps = authored["steps"][1]["repeat_until"]["steps"][-1]["match"]["cases"]["GAP"]["steps"]
    gap_steps.append(
        {
            "name": "drain_stdlib_backlog_drain_stdlib::drain__runtime_proof_scope_guard",
            "id": "drain_stdlib_backlog_drain_stdlib_drain__runtime_proof_scope_guard",
            "if": {
                "compare": {
                    "left": {
                        "ref": "root.steps.drain_stdlib_backlog_drain_stdlib::drain__%macro__backlog-drain__m0001__terminal__seed.artifacts.state__items-processed"
                    },
                    "op": "eq",
                    "right": 0,
                }
            },
            "then": {
                "id": "drain_stdlib_backlog_drain_stdlib_drain__runtime_proof_scope_guard__then",
                "steps": [
                    {
                        "name": "drain_stdlib_backlog_drain_stdlib::drain__runtime_proof_scope_guard__then__done",
                        "id": "drain_stdlib_backlog_drain_stdlib_drain__runtime_proof_scope_guard__then__done",
                        "materialize_artifacts": {
                            "values": [
                                {
                                    "name": "status",
                                    "source": {"literal": "DONE"},
                                    "contract": {
                                        "kind": "scalar",
                                        "type": "enum",
                                        "allowed": ["CONTINUE", "DONE"],
                                    },
                                }
                            ]
                        },
                    }
                ],
                "outputs": {
                    "status": {
                        "kind": "scalar",
                        "type": "enum",
                        "allowed": ["CONTINUE", "DONE"],
                        "from": {
                            "ref": "self.steps.drain_stdlib_backlog_drain_stdlib::drain__runtime_proof_scope_guard__then__done.artifacts.status"
                        },
                    }
                },
            },
            "else": {
                "id": "drain_stdlib_backlog_drain_stdlib_drain__runtime_proof_scope_guard__else",
                "steps": [
                    {
                        "name": "drain_stdlib_backlog_drain_stdlib::drain__runtime_proof_scope_guard__else__continue",
                        "id": "drain_stdlib_backlog_drain_stdlib_drain__runtime_proof_scope_guard__else__continue",
                        "materialize_artifacts": {
                            "values": [
                                {
                                    "name": "status",
                                    "source": {"literal": "CONTINUE"},
                                    "contract": {
                                        "kind": "scalar",
                                        "type": "enum",
                                        "allowed": ["CONTINUE", "DONE"],
                                    },
                                }
                            ]
                        },
                    }
                ],
                "outputs": {
                    "status": {
                        "kind": "scalar",
                        "type": "enum",
                        "allowed": ["CONTINUE", "DONE"],
                        "from": {
                            "ref": "self.steps.drain_stdlib_backlog_drain_stdlib::drain__runtime_proof_scope_guard__else__continue.artifacts.status"
                        },
                    }
                },
            },
        }
    )
    mutated = replace(
        lowered,
        authored_mapping=authored,
        runtime_proof_nested_structured_step_names=(
            *lowered.runtime_proof_nested_structured_step_names,
            "drain_stdlib_backlog_drain_stdlib::drain__runtime_proof_scope_guard",
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate_lowered_workflows(
            _replace_entry_lowered_workflow(result, mutated),
            workspace_root=tmp_path,
            imported_workflow_bundles=result.entry_result.workflow_catalog.imported_bundles_by_name,
            validation_profile=Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF,
        )

    assert any(
        "runtime_proof_scope_guard" in diag.message
        and "structured if/else is only supported on top-level steps" in diag.message
        for diag in excinfo.value.diagnostics
    )


def test_runtime_proof_profile_rejects_authored_parent_scope_fallback_refs_even_when_metadata_lists_them(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=False,
    )
    lowered = _selected_lowered_workflow(result)
    authored = deepcopy(lowered.authored_mapping)
    blocked_steps = authored["steps"][1]["repeat_until"]["steps"][-1]["match"]["cases"]["GAP"]["steps"][-1]["else"]["steps"]
    blocked_steps.append(
        {
            "name": "drain_stdlib_backlog_drain_stdlib::drain__runtime_proof_parent_scope_guard",
            "id": "drain_stdlib_backlog_drain_stdlib_drain__runtime_proof_parent_scope_guard",
            "materialize_artifacts": {
                "values": [
                    {
                        "name": "copied_items_processed",
                        "source": {
                            "ref": "parent.steps.drain_stdlib_backlog_drain_stdlib::drain__%macro__backlog-drain__m0001__terminal__body__state.artifacts.state__items-processed"
                        },
                        "contract": {
                            "kind": "scalar",
                            "type": "integer",
                        },
                    }
                ]
            },
        }
    )
    authored_ref = (
        "parent.steps.drain_stdlib_backlog_drain_stdlib::drain__%macro__backlog-drain__m0001__terminal__body__state"
        ".artifacts.state__items-processed"
    )
    authored_owner = (
        "drain_stdlib_backlog_drain_stdlib::drain__runtime_proof_parent_scope_guard"
    )
    mutated = replace(
        lowered,
        authored_mapping=authored,
        runtime_proof_shared_validation_parent_ref_allowances=(
            *lowered.runtime_proof_shared_validation_parent_ref_allowances,
            (authored_owner, authored_ref),
        ),
        runtime_proof_executable_parent_ref_allowances=(
            *lowered.runtime_proof_executable_parent_ref_allowances,
            (authored_owner, authored_ref),
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        validate_lowered_workflows(
            _replace_entry_lowered_workflow(result, mutated),
            workspace_root=tmp_path,
            imported_workflow_bundles=result.entry_result.workflow_catalog.imported_bundles_by_name,
            validation_profile=Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF,
        )

    assert any(
        diag.code == "workflow_boundary_type_invalid"
        and "runtime_proof_parent_scope_guard" in diag.message
        for diag in excinfo.value.diagnostics
    )


def test_validation_profile_accepts_serialized_enum_value(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="dedicated_runtime_proof",
    )

    assert result.entry_result.validation_profile is Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF
