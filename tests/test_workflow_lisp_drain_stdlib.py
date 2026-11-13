from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _validate_definition_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment

from orchestrator.workflow_lisp.workflows import ExternEnvironment
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    build_command_boundary_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
INVALID_UNION_BOUNDARY_FIXTURE = FIXTURES / "invalid" / "backlog_drain_union_call_boundary_invalid.orc"


def _build_syntax_module(path: Path):
    return build_syntax_module(read_sexpr_file(path))


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _command_boundaries(
    *,
    gap_output_type_name: str = "GapDraftResult",
):
    return build_command_boundary_environment(
        {
            "select_next_item": CertifiedAdapterBinding(
                name="select_next_item",
                stable_command=("python", "scripts/select_next_item.py"),
                input_contract={"type": "object"},
                output_type_name="SelectionResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("select_next_item_ok",),
                negative_fixture_ids=("select_next_item_bad",),
            ),
            "execute_selected_item": CertifiedAdapterBinding(
                name="execute_selected_item",
                stable_command=("python", "scripts/execute_selected_item.py"),
                input_contract={"type": "object"},
                output_type_name="SelectedItemResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("execute_selected_item_ok",),
                negative_fixture_ids=("execute_selected_item_bad",),
            ),
            "draft_gap_item": CertifiedAdapterBinding(
                name="draft_gap_item",
                stable_command=("python", "scripts/draft_gap_item.py"),
                input_contract={"type": "object"},
                output_type_name=gap_output_type_name,
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("draft_gap_item_ok",),
                negative_fixture_ids=("draft_gap_item_bad",),
            ),
        }
    )


def _typecheck_fixture(path: Path):
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        extern_environment=ExternEnvironment(bindings_by_name={}),
        command_boundary_environment=_command_boundaries(),
    )


def test_workflow_ref_union_call_boundary_projection_rejects_unproved_variant_access() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_UNION_BOUNDARY_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "variant_ref_unproved"
