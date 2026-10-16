from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "current235" / "modules"
VALID_ROOT = FIXTURES / "valid" / "imported_stdlib_loop_exhaustion_post_loop_terminal"
VALID_ENTRY_FIXTURE = VALID_ROOT / "entry.orc"

INVALID_FIXTURES: dict[str, tuple[Path, Path, str]] = {
    "direct_resource_transition": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_resource_transition",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_resource_transition" / "entry.orc",
        "loop_recur_contract_invalid",
    ),
    "direct_materialize_view": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_materialize_view",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_materialize_view" / "entry.orc",
        "loop_recur_contract_invalid",
    ),
    "direct_command_result": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_command_result",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_command_result" / "entry.orc",
        "loop_recur_contract_invalid",
    ),
    "effectful_on_exhausted_helper": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_effectful_on_exhausted_helper",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_effectful_on_exhausted_helper" / "entry.orc",
        "loop_recur_contract_invalid",
    ),
    "unproved_variant_payload": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_unproved_variant_payload",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_unproved_variant_payload" / "entry.orc",
        "variant_ref_unproved",
    ),
}

SUMMARY_PATH = "artifacts/work/imported-stdlib-loop-exhaustion-summary.json"
RUN_STATE_PATH = "state/imported-stdlib-loop-exhaustion-run-state.json"


def _command_boundaries() -> dict[str, ExternalToolBinding]:
    return {
        "run_checks": ExternalToolBinding(
            name="run_checks",
            stable_command=("python", "scripts/run_checks.py"),
        )
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

    )














def test_positive_imported_stdlib_loop_exhaustion_post_loop_terminal_keeps_native_type(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)

    assert result.entry_result.lowering_schema_version == 2
    workflow_name = "entry::run-drain-like"




    entry = result.entry_result.typed_program.workflows[workflow_name]
    assert entry.typed_body.type_ref == entry.signature.return_type_ref


@pytest.mark.parametrize("fixture_key", tuple(INVALID_FIXTURES))
def test_invalid_imported_stdlib_loop_exhaustion_routes_fail_with_owner_layer_diagnostics(
    tmp_path: Path,
    *,
    fixture_key: str,
) -> None:
    source_root, path, expected_code = INVALID_FIXTURES[fixture_key]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(
            path,
            source_root=source_root,
            tmp_path=tmp_path,
            command_boundaries=_command_boundaries()
            if fixture_key in {"direct_command_result", "view_authority_finalizer"}
            else None,
        )

    assert excinfo.value.diagnostics[0].code == expected_code
