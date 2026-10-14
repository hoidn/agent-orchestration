from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
PURE_EXPR_LOOP_COUNTER = VALID_FIXTURES / "pure_expr_loop_counter.orc"
PURE_EXPR_SELECTOR_PROJECTION = VALID_FIXTURES / "pure_expr_selector_action_projection.orc"
INVALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "invalid"


















def _compile_invalid_pure_projection_fixture(
    fixture_path: Path,
    tmp_path: Path,
    *,
    lint_profile: str = "default",
):
    return compile_stage3_entrypoint(
        fixture_path,
        source_roots=(fixture_path.parent,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lint_profile=lint_profile,
    )



























def test_compile_strict_effectful_boundary_fixture_preserves_required_lints(
    tmp_path: Path,
) -> None:
    fixture_path = INVALID_FIXTURES / "pure_projection_effectful_boundary_lints.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_invalid_pure_projection_fixture(
            fixture_path,
            tmp_path,
            lint_profile="strict",
        )

    assert {diagnostic.code for diagnostic in excinfo.value.diagnostics} == {
        "low_level_state_path_in_high_level_module",
        "variant_output_without_variant_specific_fields",
    }


def test_compile_strict_pure_projection_boundary_fixture_skips_boundary_lints(
    tmp_path: Path,
) -> None:
    source_root = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "workflow_lisp"
        / "modules"
        / "valid"
        / "pure_projection_boundary_decision_consumer"
    )
    entry_path = source_root / "pure_projection_boundary_decision_consumer" / "entry.orc"

    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(source_root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
        lint_profile="strict",
    )

    assert (
        "pure_projection_boundary_decision_consumer/entry::run"
        in result.entry_result.typed_program.workflows
    )




def test_compile_rejects_pure_projection_binding_type_mismatch_at_typecheck(
    tmp_path: Path,
) -> None:
    fixture_path = INVALID_FIXTURES / "pure_projection_binding_type_mismatch.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_invalid_pure_projection_fixture(fixture_path, tmp_path)

    assert excinfo.value.diagnostics[0].code == "type_mismatch"
