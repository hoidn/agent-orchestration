from __future__ import annotations

import importlib
import json
import re
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from orchestrator._common.io_atomic import (
    atomic_write_text as common_atomic_write_text,
)
import orchestrator.workflow_lisp.compiler as workflow_lisp_compiler
from orchestrator.workflow_lisp.adapters import reusable_phase_state_common
from orchestrator.workflow_lisp.compiler import _definition_only_syntax_module, _imported_type_refs, _validate_definition_module, compile_stage1_entrypoint, compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.contracts import is_review_findings_type
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import UsesCommandEffect, UsesProviderEffect
from orchestrator.workflow_lisp.expressions import (
    GeneratedRelpathSeedExpr,
    LoopRecurExpr,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.modules import build_import_scope
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding, CommandBoundaryEnvironment, ExternalToolBinding, build_workflow_catalog, elaborate_workflow_definitions, typecheck_workflow_definitions


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
REPO_ROOT = Path(__file__).resolve().parent.parent
STDLIB_MODULE_ROOT = REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules"


def test_reusable_result_bundle_delegates_exact_unframed_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH",
        "state/results/reusable.json",
    )
    writes: list[tuple[Path, str, dict[str, object]]] = []

    def tracking_write(path: Path, text: str, **kwargs) -> None:
        assert path.parent.is_dir()
        writes.append((path, text, kwargs))
        common_atomic_write_text(path, text, **kwargs)

    monkeypatch.setattr(
        reusable_phase_state_common,
        "atomic_write_text",
        tracking_write,
    )
    payload = {"status": "RÉSUMÉ", "count": 2}

    assert reusable_phase_state_common.emit_structured_result(payload) == 0

    assert writes == [
        (
            Path("state/results/reusable.json"),
            json.dumps(payload, sort_keys=True),
            {},
        )
    ]
    assert json.loads(capsys.readouterr().out) == payload
VALID_REVIEW_LOOP_FIXTURE = FIXTURES / "valid" / "phase_stdlib_review_loop.orc"
VALID_PHASE_SCOPE_STDLIB_FIXTURE = FIXTURES / "valid" / "phase_scope_stdlib_targets.orc"
VALID_NESTED_IMPLEMENTATION_PHASE_FIXTURE = FIXTURES / "valid" / "design_delta_nested_implementation_phase.orc"
VALID_NESTED_SAME_FILE_CALL_FIXTURE = (
    FIXTURES / "valid" / "design_delta_nested_same_file_call_local_record.orc"
)
VALID_NESTED_IMPORTED_BRANCH_EFFECTS_FIXTURE = (
    FIXTURES / "valid" / "design_delta_nested_imported_branch_effects.orc"
)
VALID_NESTED_BRANCH_SCOPE_COLLISION_FIXTURE = (
    FIXTURES / "valid" / "design_delta_nested_branch_scope_collision.orc"
)
INVALID_PHASE_CTX_FIXTURE = FIXTURES / "invalid" / "phase_ctx_contract_invalid.orc"
INVALID_PHASE_TARGET_FIXTURE = FIXTURES / "invalid" / "phase_target_unknown_generic.orc"
INVALID_REVIEW_LOOP_FIXTURE = FIXTURES / "invalid" / "review_loop_findings_contract_invalid.orc"
INVALID_REVIEW_LOOP_LEGACY_OPERANDS_FIXTURE = (
    FIXTURES / "invalid" / "review_loop_legacy_bridge_operands_invalid.orc"
)
INVALID_NESTED_INVALID_PROOF_USE_FIXTURE = (
    FIXTURES / "invalid" / "design_delta_nested_invalid_proof_use.orc"
)
INVALID_NESTED_BRANCH_REF_LEAK_FIXTURE = (
    FIXTURES / "invalid" / "design_delta_nested_branch_ref_leak.orc"
)
INVALID_NESTED_MISSING_PROJECTION_FIXTURE = (
    FIXTURES / "invalid" / "design_delta_nested_missing_projection.orc"
)
INVALID_NESTED_UNSUPPORTED_SHAPE_FIXTURE = (
    FIXTURES / "invalid" / "design_delta_nested_unsupported_shape.orc"
)


def _build_syntax_module(path: Path):
    return build_syntax_module(read_sexpr_file(path))


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _linked_module_type_environment_or_fail(linked, module_name: str):
    helper = getattr(importlib.import_module("orchestrator.workflow_lisp.compiler"), "_linked_module_type_environment", None)
    assert callable(helper), "_linked_module_type_environment is missing"
    return helper(linked, module_name)


def _write_module(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _rewrite_fixture(path: Path, *, replacements: tuple[tuple[str, str], ...], tmp_path: Path, filename: str) -> Path:
    source = path.read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in source, f"fixture text not found: {old}"
        source = source.replace(old, new, 1)
    return _write_module(tmp_path / filename, source)


def _typecheck_fixture(path: Path):
    return _compile(
        path,
        tmp_path=path.parent,
        validate_shared=False,
    ).typed_workflows


def _compile(
    path: Path,
    *,
    tmp_path: Path,
    validate_shared: bool = False,
):
    return compile_stage3_module(
        path,
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
        },
        validate_shared=validate_shared,
        workspace_root=tmp_path,

    )


def _compile_entrypoint(
    path: Path,
    *,
    tmp_path: Path,
    validate_shared: bool = False,
):
    return compile_stage3_entrypoint(
        path,
        source_roots=(path.parent,),
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
        },
        validate_shared=validate_shared,
        workspace_root=tmp_path,

    )


def _walk_nodes(node):
    if is_dataclass(node):
        yield node
        for field in fields(node):
            yield from _walk_nodes(getattr(node, field.name))
        return
    if isinstance(node, tuple):
        for item in node:
            yield from _walk_nodes(item)
        return
    if isinstance(node, list):
        for item in node:
            yield from _walk_nodes(item)
        return
    if isinstance(node, dict):
        for item in node.values():
            yield from _walk_nodes(item)


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def test_typecheck_accepts_generic_phase_ctx_for_phase_target(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_phase_target_ok.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defpath WorkReportTarget",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist false)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ReportTargetOnly",
                "    (report_path WorkReportTarget))",
                "  (defworkflow generic-phase-target",
                "    ((phase-ctx PhaseCtx))",
                "    -> ReportTargetOnly",
                "    (with-phase phase-ctx implementation",
                "      (record ReportTargetOnly",
                "        :report_path (phase-target execution-report)))))",
            ]
        ),
    )

    typed = _typecheck_fixture(path)

    assert [workflow.definition.name.rsplit("::", 1)[-1] for workflow in typed] == ["generic-phase-target"]


def test_typecheck_rejects_resume_state_adapter_authored_outside_resume_or_start(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "resume_state_adapter_outside_resume_or_start.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defpath StateFile",
                "    :kind relpath",
                '    :under "state"',
                "    :must-exist false)",
                "  (defrecord ChecksResult",
                "    (status String))",
                "  (defworkflow orchestrate",
                "    ((resume_state StateFile))",
                "    -> ChecksResult",
                "    (command-result load_resume_state",
                '      :argv ("python" "scripts/load_resume_state.py" resume_state)',
                "      :returns ChecksResult)))",
            ]
        ),
    )
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    command_boundary_environment = CommandBoundaryEnvironment(
        bindings_by_name={
            "load_resume_state": CertifiedAdapterBinding(
                name="load_resume_state",
                stable_command=("python", "scripts/load_resume_state.py"),
                input_contract={"type": "object"},
                output_type_name="ChecksResult",
                effects=("resume_state_reuse", "structured_result"),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("resume_state_reuse_ok",),
                negative_fixture_ids=("resume_state_reuse_bad",),
            ),
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_workflow_definitions(
            workflow_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            command_boundary_environment=command_boundary_environment,
        )

    _assert_diagnostic_code(excinfo, "recovery_gate_without_resume_or_start")


def test_typecheck_rejects_invalid_generic_phase_ctx_contract() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_PHASE_CTX_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_context_invalid")


def test_typecheck_rejects_unknown_generic_phase_target() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_PHASE_TARGET_FIXTURE)

    _assert_diagnostic_code(excinfo, "phase_target_contract_unresolved")


def test_current_target_composes_review_loop_through_phase_private_workflow(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "reusable_composed_with_phase_review_loop.orc",
        "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.35")',
                    "  (defmodule reusable_composed_with_phase_review_loop)",
                    "  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult ReviewReportPath review-revise-loop with-phase))",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord CompletedSurface",
                "    (plan_path WorkReport))",
                "  (defrecord ReviewInputs",
                "    (report_path WorkReport)",
                "    (fix_prompt WorkReport))",
                "  (defrecord ReviewSurfaceResult",
                "    (report_path ReviewReportPath))",
                "  (defproc review-once",
                "    ((completed CompletedSurface)",
                "     (inputs ReviewInputs))",
                "    -> ReviewDecision",
                "    :effects ((uses-provider providers.review))",
                "    :lowering inline",
                "    (provider-result providers.review",
                "      :prompt prompts.implementation.review",
                "      :inputs (completed.plan_path inputs.report_path)",
                "      :returns ReviewDecision))",
                "  (defproc apply-fix",
                "    ((completed CompletedSurface)",
                "     (inputs ReviewInputs)",
                "     (findings ReviewFindings))",
                "    -> CompletedSurface",
                "    :effects ((uses-provider providers.fix))",
                "    :lowering inline",
                "    (provider-result providers.fix",
                "      :prompt prompts.implementation.fix",
                "      :inputs (completed.plan_path inputs.fix_prompt findings.items_path)",
                "      :returns CompletedSurface))",
                "  (defproc review-phase-helper",
                "    ((phase-ctx PhaseCtx)",
                "     (completed CompletedSurface)",
                "     (inputs ReviewInputs))",
                "    -> ReviewLoopResult",
                    "    :effects ((uses-provider providers.review) (uses-provider providers.fix) (uses-command validate_review_findings_v1))",
                "    :lowering private-workflow",
                "    (with-phase phase-ctx implementation-review",
                "      (review-revise-loop implementation-review",
                "        :ctx phase-ctx",
                "        :completed completed",
                "        :inputs inputs",
                "        :review (proc-ref review-once)",
                "        :fix (proc-ref apply-fix)",
                "        :max 3)))",
                "  (defworkflow run-review",
                "    ((phase-ctx PhaseCtx)",
                "     (completed CompletedSurface)",
                "     (inputs ReviewInputs))",
                "    -> ReviewSurfaceResult",
                "    (let* ((review (review-phase-helper phase-ctx completed inputs)))",
                "      (match review",
                "        ((APPROVED approved)",
                "         (record ReviewSurfaceResult",
                "           :report_path approved.review_report))",
                    "        ((BLOCKED blocked)",
                    "         (record ReviewSurfaceResult",
                    "           :report_path blocked.review_report))",
                "        ((EXHAUSTED exhausted)",
                "         (record ReviewSurfaceResult",
                "           :report_path exhausted.last_review_report))))))",
            ]
        ),
    )

    result = compile_stage3_module(
        path,
        provider_externs={
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    helper = next(
        procedure
        for procedure in result.typed_procedures
        if procedure.definition.name.endswith("::review-phase-helper")
    )
    assert helper.resolved_lowering_mode.value == "private-workflow"
    assert helper.transitive_effect_summary.transitive_effects == frozenset(
        {
            UsesProviderEffect(subject=("providers", "review")),
            UsesProviderEffect(subject=("providers", "fix")),
            UsesCommandEffect(subject=("validate_review_findings_v1",)),
        }
    )


def test_typecheck_rejects_invalid_review_loop_findings_contract() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(INVALID_REVIEW_LOOP_FIXTURE)

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_typecheck_accepts_review_loop_result_contract_with_equivalent_findings_alias(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "phase_stdlib_review_loop_alias.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule phase_stdlib_review_loop_alias)",
                "  (import std/phase :as phase :only (ReviewFindings))",
                "  (defrecord WrappedFindings",
                "    (findings phase.ReviewFindings)))",
            ]
        ),
    )

    linked = compile_stage1_entrypoint(path, source_roots=(tmp_path,))
    entry_module = linked.compiled_modules_by_name["phase_stdlib_review_loop_alias"]
    phase_module, _, phase_env = _linked_module_type_environment_or_fail(linked, "std/phase")
    import_scope = build_import_scope(
        entry_module,
        export_surfaces_by_name=linked.graph.export_surfaces_by_name,
    )
    type_env = FrontendTypeEnvironment.from_module(
        entry_module,
        import_scope=import_scope,
        imported_type_refs=_imported_type_refs(
            import_scope,
            {
                "std/phase": {
                    "ReviewFindings": phase_env.resolve_type(
                        "ReviewFindings",
                        span=phase_module.span,
                        form_path=("workflow-lisp", "defrecord", "ReviewFindings"),
                    )
                }
            },
        ),
    )
    resolved = type_env.resolve_type(
        "phase.ReviewFindings",
        span=entry_module.span,
        form_path=("workflow-lisp", "defrecord", "WrappedFindings"),
    )

    assert is_review_findings_type(resolved)


def test_linked_builtin_std_phase_owner_lane_resolves_exported_review_loop_types(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "phase_stdlib_owner_lane.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule phase_stdlib_owner_lane)",
                "  (import std/phase :as phase :only (",
                "    ReviewDecision",
                "    ReviewFindings",
                "    ReviewFindingsJsonPath",
                "    ReviewLoopResult",
                "    PhaseScopeTargets",
                "  ))",
                "  (export LocalDecision LocalFindings LocalLoopResult LocalFindingsPath LocalTargets)",
                "  (defrecord LocalDecision",
                "    (decision phase.ReviewDecision))",
                "  (defrecord LocalFindings",
                "    (findings phase.ReviewFindings))",
                "  (defrecord LocalLoopResult",
                "    (result phase.ReviewLoopResult))",
                "  (defrecord LocalFindingsPath",
                "    (report phase.ReviewFindingsJsonPath))",
                "  (defrecord LocalTargets",
                "    (targets phase.PhaseScopeTargets)))",
            ]
        ),
    )

    linked = compile_stage1_entrypoint(path, source_roots=(tmp_path,))
    phase_module, phase_import_scope, phase_env = _linked_module_type_environment_or_fail(linked, "std/phase")

    assert "PhaseCtx" in phase_import_scope.unqualified_type_bindings
    for type_name in (
        "ReviewDecision",
        "ReviewFindings",
        "ReviewLoopResult",
        "ReviewFindingsJsonPath",
        "PhaseScopeTargets",
    ):
        resolved = phase_env.resolve_type(
            type_name,
            span=phase_module.span,
            form_path=("workflow-lisp", type_name),
        )
        assert resolved.name == type_name

    entry_module = linked.compiled_modules_by_name["phase_stdlib_owner_lane"]
    entry_import_scope = build_import_scope(
        entry_module,
        export_surfaces_by_name=linked.graph.export_surfaces_by_name,
    )
    entry_type_env = FrontendTypeEnvironment.from_module(
        entry_module,
        import_scope=entry_import_scope,
        imported_type_refs=_imported_type_refs(
            entry_import_scope,
            {
                "std/phase": {
                    type_name: phase_env.resolve_type(
                        type_name,
                        span=phase_module.span,
                        form_path=("workflow-lisp", type_name),
                    )
                    for type_name in (
                        "ReviewDecision",
                        "ReviewFindings",
                        "ReviewFindingsJsonPath",
                        "ReviewLoopResult",
                        "PhaseScopeTargets",
                    )
                }
            },
        ),
    )

    for qualified_name in (
        "phase.ReviewDecision",
        "phase.ReviewFindings",
        "phase.ReviewFindingsJsonPath",
        "phase.ReviewLoopResult",
        "phase.PhaseScopeTargets",
    ):
        resolved = entry_type_env.resolve_type(
            qualified_name,
            span=entry_module.span,
            form_path=("workflow-lisp", "defrecord"),
        )
        assert resolved.name == f"std/phase::{qualified_name.split('.', 1)[1]}"


def test_linked_builtin_std_phase_owner_lane_fails_closed_on_review_loop_result_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken_phase_source = (STDLIB_MODULE_ROOT / "std" / "phase.orc").read_text(encoding="utf-8").replace(
        "(defunion ReviewLoopResult",
        "(defunion BrokenReviewLoopResult",
        1,
    )
    _write_module(
        tmp_path / "std" / "context.orc",
        (STDLIB_MODULE_ROOT / "std" / "context.orc").read_text(encoding="utf-8"),
    )
    _write_module(tmp_path / "std" / "phase.orc", broken_phase_source)
    entry_path = _write_module(
        tmp_path / "phase_owner.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule phase_owner)",
                "  (import std/phase :only (ReviewLoopResult))",
                "  (defrecord ResultHolder (result ReviewLoopResult))",
                "  (defworkflow run () -> Int 1))",
            ]
        ),
    )
    monkeypatch.setattr(workflow_lisp_compiler, "_builtin_stdlib_source_root", lambda: tmp_path)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            entry_path,
            source_roots=(tmp_path,),
            validate_shared=True,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code in {"type_unknown", "module_export_missing"}
    assert diagnostic.span.start.path.endswith("std/phase.orc")


def test_typecheck_rejects_non_alias_path_type_substitution(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "path_type_substitution_invalid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule path_type_substitution_invalid)",
                "  (defpath ReportA",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath ReportB",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Input",
                "    (report ReportA))",
                "  (defrecord Output",
                "    (report ReportB))",
                "  (defworkflow demo",
                "    ((input Input))",
                "    -> Output",
                "    (record Output",
                "      :report input.report)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_typecheck_rejects_review_findings_json_path_substitution(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "review_findings_path_substitution_invalid.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule review_findings_path_substitution_invalid)",
                "  (import std/phase :as phase :only (ReviewFindingsJsonPath))",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Input",
                "    (report WorkReport))",
                "  (defrecord Output",
                "    (report phase.ReviewFindingsJsonPath))",
                "  (defworkflow demo",
                "    ((input Input))",
                "    -> Output",
                "    (record Output",
                "      :report input.report)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_typecheck_accepts_review_revise_loop_name_as_stdlib_macro_argument(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_REVIEW_LOOP_FIXTURE,
        replacements=(("review-revise-loop implementation-review", "review-revise-loop wrong-loop"),),
        tmp_path=tmp_path,
        filename="phase_stdlib_review_loop.orc",
    )

    _typecheck_fixture(path)


def test_typecheck_rejects_review_revise_loop_without_imported_std_phase_surface(tmp_path: Path) -> None:
    path = _rewrite_fixture(
        VALID_REVIEW_LOOP_FIXTURE,
        replacements=(
            (
                "  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult review-revise-loop with-phase))\n",
                "  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult))\n",
            ),
        ),
        tmp_path=tmp_path,
        filename="phase_stdlib_review_loop.orc",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _typecheck_fixture(path)

    _assert_diagnostic_code(excinfo, "stdlib_extension_missing_import_route")


def test_typecheck_rejects_review_revise_loop_legacy_bridge_operands(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            INVALID_REVIEW_LOOP_LEGACY_OPERANDS_FIXTURE,
            provider_externs={
                "providers.review": "fake-review",
                "providers.fix": "fake-fix",
            },
            prompt_externs={
                "prompts.implementation.review": "prompts/implementation/review.md",
                "prompts.implementation.fix": "prompts/implementation/fix.md",
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_review_loop_specializes_to_ordinary_typed_forms(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    surviving = [
        node
        for workflow in result.typed_workflows
        for node in _walk_nodes(workflow.typed_body.expr)
        if type(node).__name__ == "StdlibSpecializationExpr"
    ]
    surviving.extend(
        node
        for procedure in result.typed_procedures
        for node in _walk_nodes(procedure.typed_body.expr)
        if type(node).__name__ == "StdlibSpecializationExpr"
    )

    assert not surviving


def test_review_loop_entrypoint_smoke(tmp_path: Path) -> None:
    result = _compile_entrypoint(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    assert any(
        workflow.definition.name.endswith("::review-revise-loop-demo")
        for workflow in result.entry_result.typed_workflows
    )


def test_review_loop_compiles_without_bridge_controls(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    assert any(
        workflow.definition.name.endswith("::review-revise-loop-demo")
        for workflow in result.typed_workflows
    )


def test_typecheck_accepts_generic_phase_scoped_provider_result_record(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_phase_provider_result.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule generic_phase_provider_result)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord ReviewSurfaceResult",
                "    (report_path WorkReport))",
                "  (defworkflow run-review",
                "    ((phase-ctx PhaseCtx))",
                "    -> ReviewSurfaceResult",
                "    (with-phase phase-ctx implementation-review",
                "      (provider-result providers.execute",
                "        :prompt prompts.implementation.execute",
                "        :inputs ()",
                "        :returns ReviewSurfaceResult))))",
            ]
        ),
    )

    result = _compile(path, tmp_path=tmp_path)

    assert any(workflow.definition.name.endswith("run-review") for workflow in result.typed_workflows)


def test_stdlib_form_phase_scope_fixture_compiles_through_builtin_stdlib_import(tmp_path: Path) -> None:
    source = VALID_PHASE_SCOPE_STDLIB_FIXTURE.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None
    module_path = (tmp_path / Path(*module_match.group(1).split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries={},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert "phase_scope_stdlib_targets::phase-scope-demo" in result.entry_result.workflow_catalog.signatures_by_name


def test_review_loop_seed_state_uses_distinct_generated_seed_roles(tmp_path: Path) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    roles = {
        node.seed_role
        for workflow in result.typed_workflows
        for node in _walk_nodes(workflow.typed_body.expr)
        if isinstance(node, GeneratedRelpathSeedExpr)
    }
    roles.update(
        node.seed_role
        for procedure in result.typed_procedures
        for node in _walk_nodes(procedure.typed_body.expr)
        if isinstance(node, GeneratedRelpathSeedExpr)
    )

    assert roles >= {
        "review_loop_last_review_report_seed",
        "review_loop_findings_items_path_seed",
    }


def test_review_loop_direct_route_populates_loop_recur_on_exhausted_result_expr(
    tmp_path: Path,
) -> None:
    result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)

    loop_exprs = [
        node
        for owner in (*result.typed_workflows, *result.typed_procedures)
        for node in _walk_nodes(owner.typed_body.expr)
        if isinstance(node, LoopRecurExpr)
    ]

    assert loop_exprs
    assert loop_exprs[0].on_exhausted_result_expr is not None
    assert loop_exprs[0].on_exhausted_result_expr.span.start.path.endswith(
        "orchestrator/workflow_lisp/stdlib_modules/std/phase.orc"
    )


def test_review_loop_validator_binding_registers_only_when_review_loop_present(tmp_path: Path) -> None:
    review_loop_result = _compile(VALID_REVIEW_LOOP_FIXTURE, tmp_path=tmp_path)
    phase_scope_result = _compile(VALID_PHASE_SCOPE_STDLIB_FIXTURE, tmp_path=tmp_path)

    assert "validate_review_findings_v1" in review_loop_result.command_boundary_environment.bindings_by_name
    assert "validate_review_findings_v1" not in phase_scope_result.command_boundary_environment.bindings_by_name


def test_nested_implementation_phase_rejects_branch_local_ref_leak(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            INVALID_NESTED_BRANCH_REF_LEAK_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    assert excinfo.value.diagnostics


def test_nested_implementation_phase_rejects_missing_projection(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            INVALID_NESTED_MISSING_PROJECTION_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    assert excinfo.value.diagnostics


def test_nested_control_rejects_unsupported_shape_before_invalid_lowering(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            INVALID_NESTED_UNSUPPORTED_SHAPE_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    assert excinfo.value.diagnostics


def test_nested_control_rejects_invalid_proof_use(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            INVALID_NESTED_INVALID_PROOF_USE_FIXTURE,
            tmp_path=tmp_path,
            validate_shared=True,
        )

    assert excinfo.value.diagnostics[0].code == "variant_ref_unproved"
