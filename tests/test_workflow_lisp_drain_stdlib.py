from pathlib import Path
import re

import pytest

from orchestrator.workflow_lisp.compiler import _definition_only_syntax_module, _validate_definition_module, compile_stage3_entrypoint
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
REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_STDLIB_PARENT_TERMINAL_REPROJECTION_FIXTURE = (
    FIXTURES / "valid" / "drain_stdlib_backlog_drain_parent_terminal_reprojection.orc"
)
VALID_STDLIB_BRANCH_LOCAL_TERMINAL_CONTRACT_ALIGNMENT_FIXTURE = (
    FIXTURES / "valid" / "drain_stdlib_backlog_drain_branch_local_terminal_contract_alignment.orc"
)
VALID_STDLIB_RICH_GAP_FIXTURE = (
    FIXTURES / "valid" / "drain_stdlib_backlog_drain_rich_gap_payload.orc"
)
INVALID_UNION_BOUNDARY_FIXTURE = FIXTURES / "invalid" / "backlog_drain_union_call_boundary_invalid.orc"
INVALID_GAP_DRAFTER_NON_RECORD_PAYLOAD_FIXTURE = (
    FIXTURES / "invalid" / "backlog_drain_gap_drafter_non_record_payload_invalid.orc"
)
INVALID_STDLIB_DRAIN_NON_SYMBOL_CALLEE_FIXTURE = (
    FIXTURES / "invalid" / "drain_stdlib_backlog_drain_non_symbol_callee.orc"
)
INVALID_STDLIB_DRAIN_VIEW_AUTHORITY_FIXTURE = (
    FIXTURES / "invalid" / "drain_stdlib_materialized_view_authority_invalid.orc"
)
INVALID_HIDDEN_COMPATIBILITY_BRIDGE_PUBLIC_RUN_ITEM_FIXTURE = (
    FIXTURES
    / "invalid"
    / "backlog_drain_hidden_compatibility_bridge_public_run_item_invalid.orc"
)


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




def _compile_linked_stdlib_fixture(
    path: Path,
    *,
    tmp_path: Path,
    validation_profile: str | None = None,
    validate_shared: bool = False,
):
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    compile_kwargs: dict[str, object] = {
        "source_roots": (tmp_path,),
        "command_boundaries": _command_boundaries(gap_output_type_name="GapResult").bindings_by_name,
        "workspace_root": tmp_path,
    }
    if validation_profile is not None:
        compile_kwargs["validation_profile"] = validation_profile
    else:
        compile_kwargs["validate_shared"] = validate_shared
    return module_path, compile_stage3_entrypoint(module_path, **compile_kwargs)




































def test_workflow_ref_union_call_boundary_projection_rejects_unproved_variant_access() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_UNION_BOUNDARY_FIXTURE)

    assert excinfo.value.diagnostics[0].code == "variant_ref_unproved"


def test_workflow_ref_resolution_rejects_gap_drafter_non_record_payload(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(
            INVALID_GAP_DRAFTER_NON_RECORD_PAYLOAD_FIXTURE,
            tmp_path=tmp_path,

            validate_shared=False,
        )

    assert excinfo.value.diagnostics[0].code == "parametric_constraint_unsatisfied"


















def test_backlog_drain_target_contract_exposes_selector_blocked_variant() -> None:
    source = (
        REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules" / "std" / "drain.orc"
    ).read_text(encoding="utf-8")
    selection_union = source.split("(defunion SelectionResult", 1)[1].split(
        "(defunion GapResult", 1
    )[0]
    gap_union = source.split("(defunion GapResult", 1)[1].split("(defunion DrainResult", 1)[0]

    assert "(EMPTY)" in selection_union
    assert "(GAP" in selection_union
    assert "(SELECTED" in selection_union
    assert """(BLOCKED
      (reason String))""" in selection_union
    assert "(run-state StateExisting)" not in selection_union
    assert "(CONTINUE)" in gap_union
    assert """(BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass))""" in gap_union
    assert "(run-state StateExisting)" not in gap_union


def test_backlog_drain_target_contract_separates_terminal_value_from_effect_consumers() -> None:
    source = (
        REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules" / "std" / "drain.orc"
    ).read_text(encoding="utf-8")
    finalize_section = source.split("(defproc finalize-drain-terminal", 1)[1].split(
        "(defproc consume-drain-terminal-effects", 1
    )[0]

    assert "(defproc consume-drain-terminal-effects" in source
    assert "resource-transition" not in finalize_section
    assert "materialize-view" not in finalize_section


def test_backlog_drain_target_contract_removes_run_state_from_public_stdlib_shapes() -> None:
    source = (
        REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules" / "std" / "drain.orc"
    ).read_text(encoding="utf-8")
    drain_result_union = source.split("(defunion DrainResult", 1)[1].split(
        "(defenum DrainTerminalKind", 1
    )[0]
    drain_loop_terminal_union = source.split("(defunion DrainLoopTerminal", 1)[1].split(
        "(defrecord DrainLoopState", 1
    )[0]
    drain_loop_state_record = source.split("(defrecord DrainLoopState", 1)[1].split(
        "(defrecord DrainOutcomeState", 1
    )[0]
    helper_section = source.split("(defproc empty-drain-result-proc", 1)[1].split(
        "(defproc consume-drain-terminal-effects", 1
    )[0]

    assert "(run-state StateExisting)" not in drain_result_union
    assert "(run_state StateExisting)" not in drain_loop_terminal_union
    assert "(run-state StateExisting)" not in drain_loop_state_record
    assert "(run-state StateExisting)" not in helper_section
    assert "(run_state StateExisting)" not in helper_section


def test_stdlib_backlog_drain_rejects_non_symbol_callee_on_imported_route(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(INVALID_STDLIB_DRAIN_NON_SYMBOL_CALLEE_FIXTURE, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == "frontend_parse_error"


def test_stdlib_backlog_drain_view_authority_misuse_still_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(INVALID_STDLIB_DRAIN_VIEW_AUTHORITY_FIXTURE, tmp_path=tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "type_mismatch"
    assert "reason" in diagnostic.message


def test_compile_stage3_module_rejects_hidden_compatibility_bridge_public_run_item_fixture(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_linked_stdlib_fixture(
            INVALID_HIDDEN_COMPATIBILITY_BRIDGE_PUBLIC_RUN_ITEM_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    diagnostic = excinfo.value.diagnostics[0]
    # Generic route: the smuggled extra run_state_path parameter on the run-item
    # hook is rejected by the parametric proc-ref signature check at the macro
    # boundary (arity mismatch) instead of the intrinsic workflow-signature
    # comparison. The scenario stays impossible to author; the checker reports
    # the arity mismatch without naming the offending parameter.
    assert diagnostic.code == "proc_ref_signature_invalid"
    assert diagnostic.form_path == ("workflow-lisp", "defworkflow", "drain")
    assert "does not match parametric signature" in diagnostic.message
