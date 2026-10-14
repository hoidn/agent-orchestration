from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_lisp_command_boundaries import validate_review_findings_v1_binding


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURES / "modules"
VALID_MODULE_ROOT = MODULE_FIXTURES / "valid" / "generic_stdlib_composition"
VALID_ENTRY_FIXTURE = VALID_MODULE_ROOT / "generic_stdlib_composition" / "entry.orc"
INVALID_MODULE_ROOT = MODULE_FIXTURES / "invalid" / "generic_stdlib_composition_unqualified_transition"
INVALID_ENTRY_FIXTURE = (
    INVALID_MODULE_ROOT / "generic_stdlib_composition_unqualified_transition" / "entry.orc"
)
CAPABILITY_UNDECLARED_FIXTURE = FIXTURES / "invalid" / "generic_stdlib_composition_capability_undeclared.orc"
CONSTRAINT_ORDERING_FIXTURE = FIXTURES / "invalid" / "generic_stdlib_composition_constraint_ordering.orc"
NON_EXHAUSTIVE_FIXTURE = FIXTURES / "invalid" / "generic_stdlib_composition_non_exhaustive.orc"


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _compile_entry_fixture(path: Path, *, source_root: Path, tmp_path: Path, validate_shared: bool = True):
    return compile_stage3_entrypoint(
        path,
        source_roots=(source_root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=validate_shared,
        workspace_root=tmp_path,
        lowering_route=None,
    )


def _compile_module_fixture(
    path: Path,
    *,
    tmp_path: Path,
    command_boundaries: dict[str, ExternalToolBinding] | None = None,
):
    return compile_stage3_module(
        path,
        provider_externs={},
        prompt_externs={},
        command_boundaries=command_boundaries or {},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )


def _compile_module_fixture_frontend_only(path: Path, *, tmp_path: Path):
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


















def test_compile_stage3_entrypoint_rejects_unqualified_macro_emitted_transition_reference(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(INVALID_ENTRY_FIXTURE, source_root=INVALID_MODULE_ROOT, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "transition_unknown")


def test_compile_stage3_rejects_parametric_capability_undeclared(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(CAPABILITY_UNDECLARED_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_capability_undeclared")


def test_compile_stage3_preserves_constraint_failure_before_instantiated_body_typecheck(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(CONSTRAINT_ORDERING_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_constraint_unsatisfied")
    assert "APPROVED" in excinfo.value.diagnostics[0].message


def test_compile_stage3_rechecks_instantiated_generic_match_exhaustiveness(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(NON_EXHAUSTIVE_FIXTURE, tmp_path=tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    call_line = next(
        line_number
        for line_number, line in enumerate(NON_EXHAUSTIVE_FIXTURE.read_text(encoding="utf-8").splitlines(), 1)
        if "(status-from-outcome" in line
    )
    _assert_diagnostic_code(excinfo, "union_match_non_exhaustive")
    assert diagnostic.span.start.path == str(NON_EXHAUSTIVE_FIXTURE)
    assert any(
        "instantiated from" in note and f"{NON_EXHAUSTIVE_FIXTURE}:{call_line}:" in note
        for note in diagnostic.notes
    )


def test_minimal_caller_satisfies_review_revise_loop_declared_constraints(tmp_path: Path) -> None:
    # The shared validation pass re-validates lowered workflows through
    # elaborate_surface_workflow, which requires a non-empty `steps` field;
    # this fixture's trivially-bodied inline defproc hook trips
    # `source_map_missing` under validate_shared=True. Tracked as feasibility
    # gap G5 in docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md.
    assert (
        _compile_module_fixture_frontend_only(
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


def test_minimal_caller_satisfies_backlog_drain_proc_declared_constraints(tmp_path: Path) -> None:
    # Minimal-caller fixture for the Tranche 2 flagship (design Acceptance
    # Checks: every stdlib generic gets one whose types provide exactly the
    # declared constraints and nothing more). The fixture let*-binds the
    # backlog-drain-proc terminal and passes it to settle-drain-terminal —
    # the user-sanctioned composition idiom (2026-07-10 adjudication:
    # procedure calls in argument position are unsupported; bind with let*).
    # The backlog-drain macro is NOT exercised (it re-targets in Task 5 of
    # docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md and must
    # emit this same let*-bound shape).
    #
    # Contract anchors preserved by the generic procedure:
    # - G2 selection-payload projection: the item context is built from
    #   selection `item-id` and `item-state-root` plus ctx `run`/`ledger`
    #   and run `artifact-root`.
    # - G4 selector-BLOCKED mapping: the selector's BLOCKED `reason` is
    #   dropped and the terminal blocker class is the constant
    #   `user_decision_required`.
    # - Exhaustion class: `on_exhausted` forces loop-status EXHAUSTED with
    #   blocker class `unrecoverable_after_fix_attempt`; items/progress stay
    #   at accumulator state.
    # - Progress-report seeding: the intrinsic seeds the accumulator
    #   progress path with the literal
    #   `artifacts/work/drain-progress-report.md`; the generic proc takes
    #   it as the `initial-progress-report` parameter, which this fixture
    #   (and Task 5's macro) supplies via the `__generated-relpath-seed__`
    #   pattern with that same literal.
    # - EMPTY vs COMPLETED: an EMPTY selection terminates as EMPTY only when
    #   zero items were processed, otherwise COMPLETED.
    assert (
        _compile_module_fixture(
            FIXTURES / "valid" / "minimal_caller_backlog_drain.orc",
            tmp_path=tmp_path,
            command_boundaries={
                "drain_select": ExternalToolBinding(
                    name="drain_select",
                    stable_command=("python", "scripts/select_next_item.py"),
                ),
                "drain_run_item": ExternalToolBinding(
                    name="drain_run_item",
                    stable_command=("python", "scripts/execute_selected_item.py"),
                ),
                "drain_draft_gap": ExternalToolBinding(
                    name="drain_draft_gap",
                    stable_command=("python", "scripts/draft_gap_item.py"),
                ),
            },
        )
        is not None
    )


def test_cross_module_generic_loop_projects_caller_union_fields(tmp_path: Path) -> None:
    # Gap C regression (docs/plans/2026-07-07-drain-migration-g8-retirement.md,
    # Phase 1 Ledger): a specialized generic `loop/recur` body that matches a
    # caller-module union and projects variant fields into its `done` payload
    # must lower from the resolved type refs carried through specialization.
    # Re-resolving the union by bare name in the generic's defining-module
    # type environment fails with `type_unknown` for exactly the flagship's
    # cross-module shape (imported stdlib generic + caller-owned unions).
    entry_fixture = (
        MODULE_FIXTURES
        / "valid"
        / "generic_loop_union_cross_module"
        / "generic_loop_union_cross_module"
        / "entry.orc"
    )
    result = compile_stage3_entrypoint(
        entry_fixture,
        source_roots=(MODULE_FIXTURES / "valid" / "generic_loop_union_cross_module",),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "probe_select": ExternalToolBinding(
                name="probe_select",
                stable_command=("python", "scripts/select_next_item.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )
    assert result is not None


def test_same_module_generic_loop_projects_caller_union_fields(tmp_path: Path) -> None:
    # Same-module control for the cross-module gap-C regression above: the
    # identical generic loop shape compiles when the caller union lives in
    # the generic's own module, pinning that the fix only has to change the
    # cross-module resolution path.
    assert (
        _compile_module_fixture(
            FIXTURES / "valid" / "generic_loop_union_same_module.orc",
            tmp_path=tmp_path,
            command_boundaries={
                "probe_select": ExternalToolBinding(
                    name="probe_select",
                    stable_command=("python", "scripts/select_next_item.py"),
                )
            },
        )
        is not None
    )


def test_drain_generic_hook_probe_effectful_proc_hook_compiles_shared_validated(tmp_path: Path) -> None:
    # Drain-migration feasibility probe (gaps G1/G3/G5): an effectful defproc
    # hook that returns a caller-owned union and contains a command-result
    # effect must bind through ProcRef inference into a generic definition and
    # compile through the shared-validated stage-3 entry. Probe record:
    # docs/plans/2026-07-07-drain-migration-g8-retirement.md, Phase 1 Ledger.
    assert (
        _compile_module_fixture(
            FIXTURES / "valid" / "drain_generic_hook_probe.orc",
            tmp_path=tmp_path,
            command_boundaries={
                "probe_select": ExternalToolBinding(
                    name="probe_select",
                    stable_command=("python", "scripts/select_next_item.py"),
                )
            },
        )
        is not None
    )
