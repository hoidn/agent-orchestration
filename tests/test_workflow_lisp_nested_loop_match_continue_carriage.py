from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "modules"
VALID_ROOT = (
    FIXTURES / "valid" / "nested_loop_match_continue_carriage" / "nested_loop_match_continue_carriage"
)
VALID_ENTRY_FIXTURE = VALID_ROOT / "entry.orc"
WORKFLOW_NAME = "entry::run-carriage"

INVALID_FIXTURES: dict[str, tuple[Path, Path, str]] = {
    "branch_local_ref_leak": (
        FIXTURES
        / "invalid"
        / "nested_loop_match_continue_branch_local_ref_leak"
        / "nested_loop_match_continue_branch_local_ref_leak",
        FIXTURES
        / "invalid"
        / "nested_loop_match_continue_branch_local_ref_leak"
        / "nested_loop_match_continue_branch_local_ref_leak"
        / "entry.orc",
        "name_unknown",
    ),
    "proof_reset": (
        FIXTURES
        / "invalid"
        / "nested_loop_match_continue_proof_reset"
        / "nested_loop_match_continue_proof_reset",
        FIXTURES
        / "invalid"
        / "nested_loop_match_continue_proof_reset"
        / "nested_loop_match_continue_proof_reset"
        / "entry.orc",
        "variant_ref_unproved",
    ),
}


def _compile_entry_fixture(path: Path, *, source_root: Path, tmp_path: Path):
    return compile_stage3_entrypoint(
        path,
        source_roots=(source_root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )








def test_positive_nested_loop_match_continue_carriage_compiles_on_wcc_schema2_and_executes(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)

    assert result.entry_result.lowering_schema_version == 2








def test_branch_local_ref_leak_fails_without_loop_frame_materialization(
    tmp_path: Path,
) -> None:
    source_root, path, expected_code = INVALID_FIXTURES["branch_local_ref_leak"]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(path, source_root=source_root, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == expected_code


def test_proof_reset_requires_rematch_for_carried_union_value(
    tmp_path: Path,
) -> None:
    source_root, path, expected_code = INVALID_FIXTURES["proof_reset"]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(path, source_root=source_root, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == expected_code
