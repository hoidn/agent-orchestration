from __future__ import annotations

from pathlib import Path

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_lisp_command_boundaries import validate_review_findings_v1_binding


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"


def _compile_module_fixture(path: Path, *, tmp_path: Path):
    return compile_stage3_module(
        path,
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "apply_resource_transition": ExternalToolBinding(
                name="apply_resource_transition",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.apply_resource_transition",
                ),
            ),
            "produce_review_decision": ExternalToolBinding(
                name="produce_review_decision",
                stable_command=("python", "scripts/produce_review_decision.py"),
            ),
            "validate_review_findings_v1": validate_review_findings_v1_binding(),
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=None,
    )


def test_minimal_caller_satisfies_review_revise_loop_declared_constraints(tmp_path: Path) -> None:
    assert (
        _compile_module_fixture(
            FIXTURES / "valid" / "minimal_caller_review_revise_loop.orc",
            tmp_path=tmp_path,
        )
        is not None
    )


def test_minimal_caller_satisfies_finalize_selected_item_declared_constraints(tmp_path: Path) -> None:
    assert (
        _compile_module_fixture(
            FIXTURES / "valid" / "minimal_caller_finalize_selected_item.orc",
            tmp_path=tmp_path,
        )
        is not None
    )
