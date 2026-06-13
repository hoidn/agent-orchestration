from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "modules"
VALID_ROOT = FIXTURES / "valid" / "imported_stdlib_macro_payload_helper_composition"
VALID_ENTRY_FIXTURE = (
    VALID_ROOT / "imported_stdlib_macro_payload_helper_composition" / "entry.orc"
)

INVALID_FIXTURES: dict[str, tuple[Path, Path, str]] = {
    "bad_field": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_bad_field",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_bad_field"
        / "imported_stdlib_macro_payload_helper_bad_field"
        / "entry.orc",
        "record_field_unknown",
    ),
    "signature_mismatch": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_signature_mismatch",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_signature_mismatch"
        / "imported_stdlib_macro_payload_helper_signature_mismatch"
        / "entry.orc",
        "type_mismatch",
    ),
    "effect_position_invalid": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_effect_position_invalid",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_effect_position_invalid"
        / "imported_stdlib_macro_payload_helper_effect_position_invalid"
        / "entry.orc",
        "effect_not_permitted",
    ),
    "variant_unproved": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_variant_unproved",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_variant_unproved"
        / "imported_stdlib_macro_payload_helper_variant_unproved"
        / "entry.orc",
        "variant_ref_unproved",
    ),
    "hidden_command_effect": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_hidden_command_effect",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_hidden_command_effect"
        / "imported_stdlib_macro_payload_helper_hidden_command_effect"
        / "entry.orc",
        "macro_hidden_effect",
    ),
    "non_symbol_callee": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_non_symbol_callee",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_non_symbol_callee"
        / "imported_stdlib_macro_payload_helper_non_symbol_callee"
        / "entry.orc",
        "frontend_parse_error",
    ),
}


def _compile_entry_fixture(
    path: Path,
    *,
    source_root: Path,
    tmp_path: Path,
    command_boundaries: dict[str, ExternalToolBinding] | None = None,
):
    return compile_stage3_entrypoint(
        path,
        source_roots=(source_root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries=command_boundaries or {},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )


def _bound_runtime_inputs(bundle, workspace: Path) -> dict[str, object]:
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    public_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    return bind_workflow_inputs(public_inputs, {}, workspace)


def _execute_bundle(bundle, *, workflow_path: Path, workspace: Path, run_id: str) -> dict[str, object]:
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bound_runtime_inputs(bundle, workspace),
    )
    return WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(on_error="stop")


def test_positive_imported_stdlib_macro_payload_helper_route_compiles_on_wcc_schema2_and_executes(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)

    assert result.entry_result.lowering_schema_version == 2
    bundle = result.validated_bundles_by_name[
        "imported_stdlib_macro_payload_helper_composition/entry::run-drain-like"
    ]
    effect_kinds = {effect.effect_kind for effect in bundle.semantic_ir.effects.values()}

    assert "materialize_view" in effect_kinds

    state = _execute_bundle(
        bundle,
        workflow_path=VALID_ENTRY_FIXTURE,
        workspace=tmp_path,
        run_id="g5c-imported-stdlib-helper-positive",
    )
    summary_path = tmp_path / state["workflow_outputs"]["return__summary-path"]
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["return__variant"] == "SUCCESS"
    assert state["workflow_outputs"]["return__selected-id"] == "selected-1"
    assert state["workflow_outputs"]["return__call-selected-id"] == "selected-1"
    assert state["workflow_outputs"]["return__call-summary-status"] == "SELECTED"
    assert summary_payload == {"selected-id": "selected-1"}


def test_positive_imported_stdlib_macro_payload_helper_route_feeds_call_record_and_variant_positions(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)
    bundle = result.validated_bundles_by_name[
        "imported_stdlib_macro_payload_helper_composition/entry::run-drain-like"
    ]

    state = _execute_bundle(
        bundle,
        workflow_path=VALID_ENTRY_FIXTURE,
        workspace=tmp_path,
        run_id="g5c-imported-stdlib-helper-flow-shapes",
    )

    assert state["workflow_outputs"]["return__selected-id"] == "selected-1"
    assert state["workflow_outputs"]["return__gap-id"] == ""
    assert state["workflow_outputs"]["return__call-selected-id"] == "selected-1"
    assert state["workflow_outputs"]["return__call-summary-status"] == "SELECTED"


def test_positive_imported_stdlib_macro_payload_helper_route_is_name_neutral_not_std_drain_special_cased(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)
    workflow_name = "imported_stdlib_macro_payload_helper_composition/entry::run-drain-like"
    source_map_payload = json.dumps(
        build_source_map_document(
            result,
            selected_name=workflow_name,
            display_name_resolver=lambda name: name,
        ).__dict__,
        default=lambda value: value.__dict__,
        sort_keys=True,
    )

    assert workflow_name in result.validated_bundles_by_name
    assert "std/drain" not in source_map_payload
    assert "backlog-drain" not in source_map_payload


@pytest.mark.parametrize(
    ("fixture_key", "command_boundaries"),
    [
        ("bad_field", None),
        ("signature_mismatch", None),
        ("effect_position_invalid", None),
        ("variant_unproved", None),
        (
            "hidden_command_effect",
            {
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
        ),
        ("non_symbol_callee", None),
    ],
)
def test_invalid_imported_stdlib_macro_payload_helper_routes_fail_with_owner_layer_diagnostics(
    tmp_path: Path,
    *,
    fixture_key: str,
    command_boundaries: dict[str, ExternalToolBinding] | None,
) -> None:
    source_root, path, expected_code = INVALID_FIXTURES[fixture_key]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(
            path,
            source_root=source_root,
            tmp_path=tmp_path,
            command_boundaries=command_boundaries,
        )

    assert excinfo.value.diagnostics[0].code == expected_code
