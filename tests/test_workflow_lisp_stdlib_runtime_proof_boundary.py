from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.workflow.executable_ir import validate_executable_workflow
from orchestrator.workflow_lisp.compiler import Stage3ValidationProfile, compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lints import LINT_PROFILE_STRICT
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


_ENTRY_PARAMS = """  (defworkflow drain
    ((ctx DrainCtx)
     (max-iterations Int))"""
_LOW_LEVEL_ENTRY_PARAMS = """  (defworkflow drain
    ((ctx DrainCtx)
     (state-root Path.state-root)
     (max-iterations Int))"""


def _compile_low_level_boundary_variant(*, tmp_path: Path, **compile_kwargs: object):
    source = DRAIN_STDLIB_FIXTURE.read_text(encoding="utf-8")
    assert source.count(_ENTRY_PARAMS) == 1
    variant_source = source.replace(_ENTRY_PARAMS, _LOW_LEVEL_ENTRY_PARAMS, 1)
    variant_path = tmp_path / "low_level_boundary_variant.orc"
    variant_path.write_text(variant_source, encoding="utf-8")
    return _compile_linked_fixture(
        variant_path,
        tmp_path=tmp_path,
        **compile_kwargs,
    )


def _selected_lowered_workflow(result):
    return next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == ENTRY_WORKFLOW_NAME
    )


def _walk_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_nodes(child)


_DRAIN_REPEAT_OUTPUTS = {
    "status",
    "state__items-processed",
    "state__progress-report-path",
    "result__variant",
    "result__items_processed",
    "result__progress_report_path",
    "result__blocker_class",
}


def _inline_repeat_candidates(authored_mapping):
    candidates = []
    for node in _walk_nodes(authored_mapping):
        repeat = node.get("repeat_until")
        if not isinstance(repeat, dict) or not isinstance(repeat.get("steps"), list):
            continue
        outputs = repeat.get("outputs")
        exhausted = repeat.get("on_exhausted", {}).get("outputs", {})
        if (
            isinstance(outputs, dict)
            and _DRAIN_REPEAT_OUTPUTS <= set(outputs)
            and exhausted.get("status") == "DONE"
            and exhausted.get("result__variant") == "EXHAUSTED"
        ):
            candidates.append((node, repeat))
    return candidates


def _selected_inline_repeat(authored_mapping):
    candidates = _inline_repeat_candidates(authored_mapping)
    assert len(candidates) == 1, (
        f"expected one parent-owned inline drain repeat, found {len(candidates)}"
    )
    return candidates[0]


def _source_mapped_owner_records(lowered):
    records = {}
    for node in _walk_nodes(lowered.authored_mapping):
        name = node.get("name")
        step_id = node.get("id")
        if not isinstance(name, str) or not isinstance(step_id, str):
            continue
        origin = lowered.origin_map.step_spans.get(step_id)
        if origin is not None:
            records[name] = (node, origin)
    return records


def _assert_generated_stdlib_owner(node, origin) -> None:
    assert Path(origin.span.start.path).as_posix().endswith(
        "orchestrator/workflow_lisp/stdlib_modules/std/drain.orc"
    )
    assert (
        origin.form_path[-2:] == ("defproc", "backlog-drain-proc")
        or (
            "assert" in node
            and origin.form_path[-2:] == ("defworkflow", "drain")
        )
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


def _replace_entry_workflow(result, replacement):
    return tuple(
        replacement
        if item.typed_workflow.definition.name == ENTRY_WORKFLOW_NAME
        else item
        for item in result.entry_result.lowered_workflows
    )


def _assert_low_level_boundary_diagnostic(diagnostic) -> None:
    assert diagnostic.code == "low_level_state_path_in_high_level_module"
    assert diagnostic.validation_pass == "contract"
    assert diagnostic.authority_layer == "frontend"
    assert diagnostic.form_path
    assert diagnostic.span is not None


def _runtime_proof_nested_structured_mutation(result, *, include_allowance: bool):
    lowered = _selected_lowered_workflow(result)
    authored = deepcopy(lowered.authored_mapping)
    _, repeat = _selected_inline_repeat(authored)
    generated_sources = [
        step for step in repeat["steps"] if "if" in step and "when" not in step
    ]
    assert len(generated_sources) == 1
    generated_source = generated_sources[0]
    guarded_parents = [
        step
        for step in repeat["steps"]
        if "if" in step
        and "when" in step
        and len(step["then"].get("steps", ())) == 1
        and len(step["else"].get("steps", ())) == 1
    ]
    assert len(guarded_parents) == 1

    nested_name = f"{generated_source['name']}__runtime_proof_scope_guard"
    def marker_branch(branch_name: str, value: bool):
        return {
            "steps": [
                {
                    "name": f"{nested_name}__{branch_name}",
                    "id": f"runtime_proof_scope_guard_{branch_name}",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "marker",
                                "source": {"literal": value},
                                "contract": {"kind": "scalar", "type": "bool"},
                            }
                        ]
                    },
                }
            ]
        }

    nested = deepcopy(generated_source)
    nested.update(
        {
            "name": nested_name,
            "id": "runtime_proof_scope_guard",
            "if": {"compare": {"left": 1, "op": "eq", "right": 1}},
            "then": marker_branch("then", True),
            "else": marker_branch("else", False),
        }
    )
    guarded_parents[0]["then"]["steps"].append(nested)
    generated_origin = lowered.origin_map.step_spans[generated_source["name"]]
    origin_map = replace(
        lowered.origin_map,
        step_spans={
            **lowered.origin_map.step_spans,
            nested_name: generated_origin,
            nested["id"]: generated_origin,
        },
    )
    allowances = lowered.runtime_proof_nested_structured_step_names
    if include_allowance:
        allowances = (*allowances, nested_name)
    return replace(
        lowered,
        authored_mapping=authored,
        origin_map=origin_map,
        runtime_proof_nested_structured_step_names=allowances,
    )


def _validate_runtime_proof_mutation(result, mutated, *, tmp_path: Path) -> None:
    validate_lowered_workflows(
        _replace_entry_workflow(result, mutated),
        workspace_root=tmp_path,
        imported_workflow_bundles=result.entry_result.workflow_catalog.imported_bundles_by_name,
        validation_profile=Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF,
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
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=True,
    )

    lowered = _selected_lowered_workflow(result)

    _, inline_repeat = _selected_inline_repeat(lowered.authored_mapping)
    assert inline_repeat["steps"]
    assert not any(
        step.get("call") == "std/drain::backlog-drain"
        for step in lowered.authored_mapping["steps"]
    )


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
    repeat_owner, inline_repeat = _selected_inline_repeat(lowered.authored_mapping)

    assert result.entry_result.retained_non_promotable_diagnostics == ()
    assert inline_repeat["steps"]
    assert repeat_owner["id"] in lowered.origin_map.step_spans
    repeat_index = lowered.authored_mapping["steps"].index(repeat_owner)
    terminal_owners = lowered.authored_mapping["steps"][repeat_index + 1 :]
    assert terminal_owners
    assert all(step["id"] in lowered.origin_map.step_spans for step in terminal_owners)
    assert any(
        "__write_root__" in path
        for path in lowered.origin_map.generated_path_spans
    )
    assert any(
        "finalize_drain_terminal" in path
        for path in lowered.origin_map.generated_path_spans
    )
    assert not any(
        step.get("call") == "std/drain::backlog-drain"
        for step in lowered.authored_mapping["steps"]
    )


def test_parent_owned_inline_route_selector_fails_closed_on_ambiguous_shape(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    lowered = _selected_lowered_workflow(result)
    authored = deepcopy(lowered.authored_mapping)
    repeat_owner, _ = _selected_inline_repeat(authored)
    authored["steps"].append(deepcopy(repeat_owner))

    with pytest.raises(AssertionError, match="found 2"):
        _selected_inline_repeat(authored)
    with pytest.raises(AssertionError, match="found 0"):
        _selected_inline_repeat({})


def test_dedicated_runtime_proof_default_lint_retains_low_level_boundary_variant(
    tmp_path: Path,
) -> None:
    result = _compile_low_level_boundary_variant(
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    validate_executable_workflow(result.entry_result.validated_bundles[ENTRY_WORKFLOW_NAME].ir)
    findings = [
        item
        for item in result.entry_result.retained_non_promotable_diagnostics
        if item.code == "low_level_state_path_in_high_level_module"
    ]
    assert len(findings) == 1
    _assert_low_level_boundary_diagnostic(findings[0])


def test_shared_callable_default_lint_retains_low_level_boundary_variant(
    tmp_path: Path,
) -> None:
    result = _compile_low_level_boundary_variant(
        tmp_path=tmp_path,
        validate_shared=True,
    )
    findings = [
        item
        for item in result.entry_result.retained_non_promotable_diagnostics
        if item.code == "low_level_state_path_in_high_level_module"
    ]
    assert len(findings) == 1
    _assert_low_level_boundary_diagnostic(findings[0])


def test_shared_callable_strict_lint_rejects_low_level_boundary_variant(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_low_level_boundary_variant(
            tmp_path=tmp_path,
            validate_shared=True,
            lint_profile=LINT_PROFILE_STRICT,
        )
    findings = [
        item
        for item in excinfo.value.diagnostics
        if item.code == "low_level_state_path_in_high_level_module"
    ]
    assert len(findings) == 1
    _assert_low_level_boundary_diagnostic(findings[0])


def test_dedicated_runtime_proof_strict_lint_rejects_low_level_boundary_variant(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_low_level_boundary_variant(
            tmp_path=tmp_path,
            validation_profile="DEDICATED_RUNTIME_PROOF",
            lint_profile=LINT_PROFILE_STRICT,
        )
    findings = [
        item
        for item in excinfo.value.diagnostics
        if item.code == "low_level_state_path_in_high_level_module"
    ]
    assert len(findings) == 1
    _assert_low_level_boundary_diagnostic(findings[0])


def test_runtime_proof_metadata_resolves_to_source_mapped_generated_owners(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="DEDICATED_RUNTIME_PROOF",
    )
    lowered = _selected_lowered_workflow(result)
    records = _source_mapped_owner_records(lowered)

    assert lowered.runtime_proof_nested_structured_step_names
    assert lowered.runtime_proof_shared_validation_parent_ref_allowances
    assert lowered.runtime_proof_executable_parent_ref_allowances
    for owner in lowered.runtime_proof_nested_structured_step_names:
        _assert_generated_stdlib_owner(*records[owner])
    for allowances in (
        lowered.runtime_proof_shared_validation_parent_ref_allowances,
        lowered.runtime_proof_executable_parent_ref_allowances,
    ):
        for owner, _ in allowances:
            _assert_generated_stdlib_owner(*records[owner])


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


def test_runtime_proof_profile_accepts_generated_nested_structured_steps_on_parent_owned_inline_route(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=False,
    )
    mutated = _runtime_proof_nested_structured_mutation(result, include_allowance=True)

    _validate_runtime_proof_mutation(result, mutated, tmp_path=tmp_path)


def test_runtime_proof_profile_rejects_generated_nested_structured_step_without_metadata_allowance(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validate_shared=False,
    )
    mutated = _runtime_proof_nested_structured_mutation(result, include_allowance=False)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _validate_runtime_proof_mutation(result, mutated, tmp_path=tmp_path)

    matching = [
        item
        for item in excinfo.value.diagnostics
        if item.code == "workflow_boundary_type_invalid"
        and item.validation_pass == "shared_validation"
        and item.authority_layer == "shared_validation"
        and item.form_path[-2:] == ("defproc", "backlog-drain-proc")
        and Path(item.span.start.path).as_posix().endswith(
            "orchestrator/workflow_lisp/stdlib_modules/std/drain.orc"
        )
    ]
    assert len(matching) == 1


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
    repeat_owner, repeat = _selected_inline_repeat(authored)
    authored_ref = (
        f"parent.steps.{repeat_owner['name']}__current_loop_state."
        "artifacts.acc__items-processed"
    )
    authored_owner = f"{ENTRY_WORKFLOW_NAME}__runtime_proof_parent_scope_guard"
    repeat["steps"].append(
        {
            "name": authored_owner,
            "id": "runtime_proof_parent_scope_guard",
            "materialize_artifacts": {
                "values": [
                    {
                        "name": "copied_items_processed",
                        "source": {"ref": authored_ref},
                        "contract": {
                            "kind": "scalar",
                            "type": "integer",
                        },
                    }
                ]
            },
        }
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
            _replace_entry_workflow(result, mutated),
            workspace_root=tmp_path,
            imported_workflow_bundles=result.entry_result.workflow_catalog.imported_bundles_by_name,
            validation_profile=Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF,
        )

    matching = [
        item
        for item in excinfo.value.diagnostics
        if item.code == "workflow_boundary_type_invalid"
        and item.validation_pass == "shared_validation"
        and item.authority_layer == "shared_validation"
        and item.form_path[-2:] == ("defproc", "backlog-drain-proc")
        and Path(item.span.start.path).as_posix().endswith(
            "orchestrator/workflow_lisp/stdlib_modules/std/drain.orc"
        )
    ]
    assert len(matching) == 1


def test_validation_profile_accepts_serialized_enum_value(
    tmp_path: Path,
) -> None:
    result = _compile_linked_fixture(
        DRAIN_STDLIB_FIXTURE,
        tmp_path=tmp_path,
        validation_profile="dedicated_runtime_proof",
    )

    assert result.entry_result.validation_profile is Stage3ValidationProfile.DEDICATED_RUNTIME_PROOF
