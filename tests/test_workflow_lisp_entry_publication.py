from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
ENTRY_PUBLICATION_RUNTIME_FIXTURE = VALID_FIXTURES / "entry_publication_runtime.orc"
MATERIALIZE_VIEW_RUNTIME_FIXTURE = VALID_FIXTURES / "materialize_view_runtime.orc"


def _entry_publication_module():
    return importlib.import_module("orchestrator.workflow_lisp.entry_publication")


def _entry_publication_census() -> dict[str, object]:
    return {
        "rows": [
            {
                "row_id": "c0.drain_materialized_drain_summary",
                "consumer_lane": "entry_publication",
            },
            {
                "row_id": "c0.selector_output_return_selection_bundle_path",
                "track_c_decision": "RETIRE_TO_ENTRY_PUBLICATION",
            },
            {
                "row_id": "c0.selector_output_return_selection_bundle_path_compiled_boundary",
                "track_c_decision": "RETIRE_TO_ENTRY_PUBLICATION",
            },
            {
                "row_id": "c0.drain_output_return_run_state",
                "consumer_lane": "semantic_runtime",
            },
        ]
    }


def _compile_fixture(path: Path, tmp_path: Path):
    return compile_stage3_module(
        path,
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )


def test_entry_publication_helpers_select_only_c3_rows_from_local_census() -> None:
    module = _entry_publication_module()
    selector = getattr(module, "select_entry_publication_rows")

    selected_rows = selector(_entry_publication_census())
    selected_row_ids = {row["row_id"] for row in selected_rows}

    assert selected_row_ids == {
        "c0.drain_materialized_drain_summary",
        "c0.selector_output_return_selection_bundle_path",
        "c0.selector_output_return_selection_bundle_path_compiled_boundary",
    }
    assert "c0.drain_output_return_run_state" not in selected_row_ids
    assert "c0.drain_output_return_run_state_compiled_boundary" not in selected_row_ids
    assert "c0.plan_phase_output_approved_plan_path" not in selected_row_ids
    assert "c0.plan_phase_output_approved_plan_path_compiled_boundary" not in selected_row_ids
    assert "c0.plan_phase_output_return_blocked_plan_path" not in selected_row_ids
    assert "c0.plan_phase_output_return_blocked_plan_path_compiled_boundary" not in selected_row_ids
    assert "c0.plan_phase_output_return_exhausted_plan_path" not in selected_row_ids
    assert "c0.plan_phase_output_return_exhausted_plan_path_compiled_boundary" not in selected_row_ids
    assert "c0.plan_phase_output_return_findings_items_path" not in selected_row_ids
    assert (
        "c0.plan_phase_output_return_findings_items_path_compiled_boundary"
        not in selected_row_ids
    )



def test_entry_publication_helpers_classify_legal_and_compatibility_only_rows() -> None:
    module = _entry_publication_module()
    classifier = getattr(module, "classify_entry_publication_rows")

    classified = classifier(
        workflow_name="entry_publication_runtime::entry-publication-runtime",
        return_union_name="EntryPublicationResult",
        return_variants=("DONE", "BLOCKED", "SKIPPED"),
        selected_rows=(
            {
                "row_id": "c0.synthetic_publishable_done",
                "workflow_name": "entry_publication_runtime::entry-publication-runtime",
                "typed_value_surface": "terminal_result_variant",
                "value_kind": "union_variant",
                "value_type": "EntryPublicationResult",
                "variant": "DONE",
            },
            {
                "row_id": "c0.synthetic_field_projection_only",
                "workflow_name": "entry_publication_runtime::entry-publication-runtime",
                "typed_value_surface": None,
                "value_kind": "returned_path_field",
                "value_type": "EntryPublicationResult",
                "variant": None,
            },
        ),
        policy_rows=(
            {"variant": "DONE", "role": "drain-summary"},
            {"variant": "BLOCKED", "role": "drain-summary"},
        ),
    )

    assert [row["row_id"] for row in classified["legal_rows"]] == [
        "c0.synthetic_publishable_done"
    ]
    assert classified["compatibility_reasons"] == [
        {
            "row_id": "c0.synthetic_field_projection_only",
            "reason": "field_level_publication_not_supported_in_c3",
        }
    ]
    assert classified["omitted_variants"] == ["SKIPPED"]


def test_entry_publication_helpers_resolve_role_registry_and_serialize_report() -> None:
    module = _entry_publication_module()
    resolve_roles = getattr(module, "resolve_publication_role_registry")
    serialize_report = getattr(module, "serialize_entry_publication_report")

    roles = resolve_roles()
    drain_summary = roles["drain-summary"]
    payload = serialize_report(
        target_family="design_delta_parent_drain",
        workflow_name="entry_publication_runtime::entry-publication-runtime",
        source_census={"path": "local-entry-publication-census"},
        consumer_rendering_census={"path": "local-entry-publication-census"},
        publication_policy={"rows": [{"variant": "DONE", "role": "drain-summary"}]},
        selected_c0_rows=[{"row_id": "c0.synthetic_publishable_done"}],
        lowered_publications=[{"variant": "DONE", "role": "drain-summary"}],
        compatibility_reasons=[],
        omitted_variants=["SKIPPED"],
        contract_isolation={
            "workflow_signature_unchanged": True,
            "call_contract_unchanged": True,
            "boundary_projection_public_inputs_unchanged": True,
            "semantic_call_edges_hide_publish_policy": True,
        },
        diagnostics=[],
    )

    assert drain_summary["renderer_id"] == "canonical-json"
    assert payload["schema_version"] == "workflow_lisp_entry_publication_report.v1"
    assert payload["target_family"] == "design_delta_parent_drain"
    assert payload["workflow_name"] == "entry_publication_runtime::entry-publication-runtime"
    assert payload["omitted_variants"] == ["SKIPPED"]


def test_legacy_workflow_without_publish_metadata_still_compiles(tmp_path: Path) -> None:
    result = _compile_fixture(
        MATERIALIZE_VIEW_RUNTIME_FIXTURE,
        tmp_path,
    )

    assert "orchestrate" in result.validated_bundles


def test_compile_stage3_rejects_malformed_publish_metadata(tmp_path: Path) -> None:
    malformed_fixture = tmp_path / "entry_publication_policy_invalid.orc"
    malformed_fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule entry_publication_policy_invalid)",
                "  (export entry-publication-policy-invalid)",
                "  (defunion EntryPublicationResult",
                "    (DONE (message String))",
                "    (BLOCKED (reason String)))",
                "  (defworkflow entry-publication-policy-invalid",
                "    ()",
                "    -> EntryPublicationResult",
                "    (:publish (DONE :as drain-summary))",
                "    (variant EntryPublicationResult DONE",
                '      :message "done")))',
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_fixture(
            malformed_fixture,
            tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "entry_publication_policy_invalid"


def test_compile_stage3_entry_publication_fixture_keeps_policy_out_of_signature(tmp_path: Path) -> None:
    result = _compile_fixture(
        ENTRY_PUBLICATION_RUNTIME_FIXTURE,
        tmp_path,
    )

    workflow_catalog = result.workflow_catalog
    signature = workflow_catalog.signatures_by_name["entry-publication-runtime"]
    workflow_def = workflow_catalog.definitions_by_name["entry-publication-runtime"]

    assert hasattr(workflow_def, "publication_policy")
    assert getattr(workflow_def, "publication_policy") is not None
    assert not hasattr(signature, "publication_policy")


def test_compile_stage3_rejects_publish_on_exported_non_selected_helper(tmp_path: Path) -> None:
    fixture_path = tmp_path / "entry_publication_selected_entry_only.orc"
    fixture_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule entry_publication_selected_entry_only)",
                "  (export entry helper)",
                "  (defunion EntryPublicationResult",
                "    (DONE (message String))",
                "    (BLOCKED (reason String)))",
                "  (defworkflow entry",
                "    ()",
                "    -> EntryPublicationResult",
                "    (call helper))",
                "  (defworkflow helper",
                "    ()",
                "    -> EntryPublicationResult",
                "    (:publish",
                "      ((DONE :as drain-summary)))",
                "    (variant EntryPublicationResult DONE",
                '      :message "helper-only")))',
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            fixture_path,
            source_roots=(tmp_path,),
            provider_externs={},
            prompt_externs={},
            command_boundaries={},
            validate_shared=True,
            workspace_root=tmp_path,
            entry_workflow="entry",
        )

    assert excinfo.value.diagnostics[0].code == "entry_publication_not_entrypoint"


def test_entry_publication_role_metadata_can_drive_exact_target_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_publication = _entry_publication_module()
    defunctionalize = importlib.import_module(
        "orchestrator.workflow_lisp.wcc.defunctionalize"
    )

    role_registry = {
        "custom-summary": {
            "role": "custom-summary",
            "renderer_id": "canonical-json",
            "renderer_version": 1,
            "output_contract": {
                "kind": "relpath",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            "authority_class": "public_artifact",
            "path_template": "artifacts/work/custom_summary.json",
        }
    }
    monkeypatch.setattr(
        entry_publication,
        "resolve_publication_role_registry",
        lambda: role_registry,
    )
    monkeypatch.setattr(
        defunctionalize,
        "resolve_publication_role_registry",
        lambda: role_registry,
    )

    source_path = tmp_path / "custom_entry_publication.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule custom_entry_publication)",
                "  (export publish-result)",
                "  (defrecord CustomSummary",
                "    (message String))",
                "  (defunion PublishResult",
                "    (DONE",
                "      (custom-summary CustomSummary)))",
                "  (defworkflow publish-result",
                "    ()",
                "    -> PublishResult",
                "    (:publish",
                "      ((DONE :as custom-summary)))",
                "    (variant PublishResult DONE",
                "      :custom-summary (record CustomSummary",
                '        :message "done"))))',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        source_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    lowered = next(
        workflow
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
        if workflow.typed_workflow.definition.name
        == "custom_entry_publication::publish-result"
    )
    publish_boundary = next(
        step
        for step in lowered.authored_mapping["steps"]
        if step["id"].endswith("__publish_boundary")
    )
    done_steps = publish_boundary["match"]["cases"]["DONE"]["steps"]
    materialize_step = next(step for step in done_steps if "materialize_view" in step)

    assert materialize_step["materialize_view"]["target_path"] == (
        "artifacts/work/custom_summary.json"
    )
    generated_allocations = [
        {
            "allocation_id": allocation.allocation_id,
            "concrete_path_template": allocation.concrete_path_template,
        }
        for allocation in lowered.generated_path_allocations
    ]
    publish_allocation = next(
        allocation
        for allocation in generated_allocations
        if allocation["allocation_id"]
        == materialize_step["materialize_view"]["target_allocation_id"]
    )
    assert publish_allocation["concrete_path_template"] == "artifacts/work/custom_summary.json"
