from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.compiler import compile_stage3_module


REPO_ROOT = Path(__file__).resolve().parent.parent
GENERIC_FAMILY_PROFILE_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "family_profiles"
    / "generic_phase_family_profile.json"
)
VALID_WORKFLOW_LISP_FIXTURES = (
    REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
)
TYPED_PROMPT_INPUT_PHASE_FIXTURE = (
    VALID_WORKFLOW_LISP_FIXTURES / "typed_prompt_input_phase.orc"
)
DESIGN_DELTA_FAMILY_PROFILE_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.family_profile.json"
)
FORBIDDEN_SOURCE_SHAPE_TOKENS = (
    "lisp_frontend_design_delta",
    "PHASE_FAMILY_MODULE_PREFIX",
    "DESIGN_DELTA_PARENT_DRAIN_TARGET_WORKFLOW_NAMES",
    "_C1_TYPED_PROMPT_INPUT_ROWS",
)
SOURCE_SHAPE_GUARD_PATHS = (
    REPO_ROOT / "orchestrator" / "workflow_lisp" / "phase_family_boundary.py",
    REPO_ROOT / "orchestrator" / "workflow_lisp" / "workflows.py",
    REPO_ROOT / "orchestrator" / "workflow_lisp" / "lowering" / "phase_scope.py",
)


def _family_profiles_module():
    return importlib.import_module("orchestrator.workflow_lisp.family_profiles")


def _phase_family_boundary_module():
    return importlib.import_module(
        "orchestrator.workflow_lisp.phase_family_boundary"
    )


def _generic_profile_payload() -> dict[str, object]:
    return json.loads(GENERIC_FAMILY_PROFILE_FIXTURE.read_text(encoding="utf-8"))


def _write_profile(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def test_design_delta_reference_family_profile_manifest_is_checked_in() -> None:
    assert DESIGN_DELTA_FAMILY_PROFILE_PATH.is_file()


def test_phase_family_helpers_require_explicit_profile_catalog() -> None:
    module = _phase_family_boundary_module()

    assert (
        module.is_selected_phase_family_workflow(
            "lisp_frontend_design_delta/drain::drain"
        )
        is False
    )
    assert (
        module.is_design_delta_parent_drain_target_workflow(
            "lisp_frontend_design_delta/work_item::run-work-item"
        )
        is False
    )
    assert (
        module.phase_family_entry_phase_identity(
            "lisp_frontend_design_delta/work_item::run-work-item"
        )
        is None
    )
    assert (
        module.checked_design_delta_public_input_names(
            "lisp_frontend_design_delta/work_item::run-work-item"
        )
        == frozenset()
    )


def test_generic_family_profile_loader_accepts_fixture_workflows() -> None:
    module = _family_profiles_module()
    catalog = module.load_workflow_family_profile_catalog(
        (GENERIC_FAMILY_PROFILE_FIXTURE,)
    )

    assert catalog.entry_phase_identity(
        "design_delta_parent_calls_work_item::run-parent-work-item"
    ) == "work-item"
    assert catalog.entry_phase_identity(
        "design_delta_parent_calls_implementation_phase::run-implementation-phase"
    ) == "implementation"
    assert catalog.checked_public_inputs(
        "design_delta_parent_calls_work_item::run-parent-work-item"
    ) == frozenset(
        {
            "work_item_bootstrap",
            "steering_path",
            "target_design_path",
            "baseline_design_path",
            "fixture_run_state_path",
        }
    )
    prompt_context_row = catalog.typed_prompt_input_row(
        "typed_prompt_input_phase::run-typed-prompt-phase-demo",
        "providers.execute",
    )
    assert prompt_context_row["c0_row_id"] == "c0.fixture.prompt_context"
    assert prompt_context_row["u0_row_id"] == "u0.fixture.prompt_context"
    request_row = catalog.typed_prompt_input_row(
        "typed_prompt_input_local_request_record::run-local-request-record-demo",
        "providers.execute",
    )
    assert request_row["preserve_request_record"] is True
    assert request_row["request_fields"]["has_subject"] is True
    assert request_row["request_fields"]["has_targets"] is True


def test_family_profile_loader_rejects_malformed_schema(tmp_path: Path) -> None:
    module = _family_profiles_module()
    payload = _generic_profile_payload()
    payload["schema_version"] = "workflow_lisp_family_profile.broken"
    path = _write_profile(tmp_path / "schema-invalid.json", payload)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        module.load_workflow_family_profile_catalog((path,))

    assert excinfo.value.diagnostics[0].code == "workflow_family_profile_schema_invalid"


def test_family_profile_loader_rejects_duplicate_prompt_row_ids(
    tmp_path: Path,
) -> None:
    module = _family_profiles_module()
    payload = _generic_profile_payload()
    duplicate_row = dict(payload["typed_prompt_input_rows"][0])
    duplicate_row["workflow_name"] = (
        "typed_prompt_input_local_request_record::run-local-request-record-demo"
    )
    duplicate_row["u0_row_id"] = "u0.fixture.request"
    duplicate_row["c0_row_id"] = "c0.fixture.request"
    payload["typed_prompt_input_rows"].append(duplicate_row)
    path = _write_profile(tmp_path / "duplicate-prompt-row.json", payload)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        module.load_workflow_family_profile_catalog((path,))

    assert excinfo.value.diagnostics[0].code == "workflow_family_profile_prompt_row_duplicate"


def test_family_profile_loader_rejects_duplicate_prompt_binding_for_workflow(
    tmp_path: Path,
) -> None:
    module = _family_profiles_module()
    payload = _generic_profile_payload()
    duplicate_row = dict(payload["typed_prompt_input_rows"][0])
    duplicate_row["binding_name"] = "duplicate_prompt_context"
    duplicate_row["u0_row_id"] = "u0.fixture.duplicate_prompt_context"
    duplicate_row["c0_row_id"] = "c0.fixture.duplicate_prompt_context"
    payload["typed_prompt_input_rows"].append(duplicate_row)
    path = _write_profile(tmp_path / "duplicate-prompt-binding.json", payload)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        module.load_workflow_family_profile_catalog((path,))

    assert excinfo.value.diagnostics[0].code == "workflow_family_profile_prompt_row_duplicate"


def test_family_profile_loader_rejects_prompt_row_for_unknown_target(
    tmp_path: Path,
) -> None:
    module = _family_profiles_module()
    payload = _generic_profile_payload()
    payload["typed_prompt_input_rows"][0]["workflow_name"] = "unknown/workflow::run"
    path = _write_profile(tmp_path / "unknown-target.json", payload)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        module.load_workflow_family_profile_catalog((path,))

    assert excinfo.value.diagnostics[0].code == "workflow_family_profile_target_unknown"


def test_compile_rejects_profile_prompt_row_for_missing_provider_call(
    tmp_path: Path,
) -> None:
    module = _family_profiles_module()
    payload = _generic_profile_payload()
    payload["typed_prompt_input_rows"].append(
        {
            "workflow_name": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
            "provider_binding": "providers.missing",
            "binding_name": "missing_prompt_context",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "value_source": {
                "kind": "typed_binding_ref",
                "ref": "inputs.prompt_context",
            },
            "value_type_name": "PromptContext",
            "source_map_origin_key": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
            "u0_row_id": "u0.fixture.missing_prompt_context",
            "c0_row_id": "c0.fixture.missing_prompt_context",
            "injection_order": 1,
        }
    )
    path = _write_profile(tmp_path / "missing-provider-binding.json", payload)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            TYPED_PROMPT_INPUT_PHASE_FIXTURE,
            provider_externs={"providers.execute": "fake-execute"},
            prompt_externs={
                "prompts.implementation.execute": "prompts/implementation/execute.md",
            },
            validate_shared=True,
            workspace_root=tmp_path,
            family_profile_catalog=module.load_workflow_family_profile_catalog((path,)),
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_family_profile_prompt_row_unknown_workflow"
    assert "typed_prompt_input_phase::run-typed-prompt-phase-demo" in diagnostic.message
    assert "providers.missing" in diagnostic.message


def test_family_profile_catalog_rejects_ambiguous_workflow_matches(
    tmp_path: Path,
) -> None:
    module = _family_profiles_module()
    payload = _generic_profile_payload()
    overlapping_payload = _generic_profile_payload()
    overlapping_payload["family_id"] = "generic_phase_family_fixture_overlap"
    overlapping_payload["typed_prompt_input_rows"] = []
    overlapping_payload["checked_public_inputs"] = {}
    overlapping_payload["hidden_context_rules"] = []
    first_path = _write_profile(tmp_path / "first.json", payload)
    second_path = _write_profile(tmp_path / "second.json", overlapping_payload)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        module.load_workflow_family_profile_catalog((first_path, second_path))

    assert excinfo.value.diagnostics[0].code == "workflow_family_profile_ambiguous"


def test_family_profile_loader_preserves_hidden_context_rule_parameter_name(
    tmp_path: Path,
) -> None:
    module = _family_profiles_module()
    payload = _generic_profile_payload()
    payload["hidden_context_rules"][0]["parameter_name"] = "fixture_run_state_path"
    payload["hidden_context_rules"][1]["parameter_name"] = "implementation_ctx"
    path = _write_profile(tmp_path / "hidden-context-invalid.json", payload)

    catalog = module.load_workflow_family_profile_catalog((path,))

    assert (
        catalog.hidden_context_rule(
            "design_delta_parent_calls_work_item::run-parent-work-item"
        ).parameter_name
        == "fixture_run_state_path"
    )
    assert (
        catalog.hidden_context_rule(
            "design_delta_parent_calls_implementation_phase::run-implementation-phase"
        ).parameter_name
        == "implementation_ctx"
    )


def test_family_profile_loader_accepts_hidden_context_parameter_alias(
    tmp_path: Path,
) -> None:
    module = _family_profiles_module()
    payload = _generic_profile_payload()
    payload["hidden_context_rules"][0]["parameter_name"] = "phase_ctx"
    path = _write_profile(tmp_path / "hidden-context-alias.json", payload)

    catalog = module.load_workflow_family_profile_catalog((path,))

    assert (
        catalog.hidden_context_rule(
            "design_delta_parent_calls_work_item::run-parent-work-item"
        ).parameter_name
        == "phase_ctx"
    )


def test_core_modules_do_not_retain_family_specific_hook_tables() -> None:
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{token}"
        for path in SOURCE_SHAPE_GUARD_PATHS
        for token in FORBIDDEN_SOURCE_SHAPE_TOKENS
        if token in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
