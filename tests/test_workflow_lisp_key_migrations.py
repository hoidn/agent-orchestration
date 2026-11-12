from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lints import LINT_PROFILE_STRICT
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


REPO_ROOT = Path(__file__).resolve().parents[1]
LISP_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
LISP_INVALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "invalid"
EXPERIMENT_CTX_FIXTURE = LISP_FIXTURES / "context_generalization_experiment_ctx.orc"
RUNCTX_ONLY_DRAIN_ENTRY_FIXTURE = LISP_FIXTURES / "context_generalization_runctx_only_drain_entry.orc"
STD_CONTEXT_IMPORT_FIXTURE = LISP_FIXTURES / "context_generalization_std_context_import.orc"
ANCHORLESS_STATE_PATH_FIXTURE = REPO_ROOT / "tests/fixtures/workflow_lisp/current235/invalid/context_generalization_anchorless_state_path.orc"
ROLELESS_BINDING_FIXTURE = LISP_INVALID_FIXTURES / "context_generalization_roleless_binding.orc"


def test_context_generalization_anchorless_state_path_fixture_rejects_low_level_state_boundary(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            ANCHORLESS_STATE_PATH_FIXTURE,
            source_roots=(ANCHORLESS_STATE_PATH_FIXTURE.parent,),
            command_boundaries={
                "emit_state_root": ExternalToolBinding(
                    name="emit_state_root",
                    stable_command=("python", "scripts/emit_state_root.py"),
                ),
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lint_profile=LINT_PROFILE_STRICT,
        )

    assert excinfo.value.diagnostics[0].code == "low_level_state_path_in_high_level_module"


