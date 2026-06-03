import importlib
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _infer_stage3_effect_summaries,
    _typecheck_procedure_definitions,
    _validate_definition_module,
    _validate_procedure_effects_and_cycles,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.drain_stdlib import BacklogDrainSpec
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic
from orchestrator.workflow_lisp.effects import CallsWorkflowEffect, UsesCommandEffect, UsesProviderEffect
from orchestrator.workflow_lisp.expressions import (
    BacklogDrainExpr,
    BindProcBinding,
    BindProcExpr,
    FinalizeSelectedItemExpr,
    LetStarExpr,
    LiteralExpr,
    NameExpr,
    ProcedureCallExpr,
    ProcRefLiteralExpr,
    ProduceOneOfExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
)
from orchestrator.workflow_lisp.lowering import _resolve_procedure_lowering, lower_workflow_definitions
from orchestrator.workflow_lisp.phase_stdlib import ProduceOneOfProducerSpec
from orchestrator.workflow_lisp.procedures import (
    ProcedureLoweringMode,
    build_procedure_catalog,
    elaborate_procedure_definitions,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.resource_stdlib import FinalizeSelectedItemSpec, ResourceTransitionSpec
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.typecheck import TypedExpr, consume_generated_local_procedures
from orchestrator.workflow_lisp.workflows import (
    ExternalToolBinding,
    TypedWorkflowDef,
    WorkflowDef,
    WorkflowSignature,
    build_command_boundary_environment,
    build_extern_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURES / "modules"
INLINE_FIXTURE = FIXTURES / "valid" / "defproc_inline.orc"
PRIVATE_WORKFLOW_FIXTURE = FIXTURES / "valid" / "defproc_private_workflow.orc"
EFFECT_MISMATCH_FIXTURE = FIXTURES / "invalid" / "procedure_effect_mismatch.orc"
CYCLE_FIXTURE = FIXTURES / "invalid" / "procedure_cycle.orc"
PRIVATE_BOUNDARY_FIXTURE = FIXTURES / "invalid" / "procedure_private_boundary_invalid.orc"
ARITY_FIXTURE = FIXTURES / "invalid" / "procedure_arity_mismatch.orc"
WORKFLOW_REF_FORWARDING_FIXTURE = FIXTURES / "valid" / "workflow_refs_forwarding.orc"
PROC_REF_FIXTURE = FIXTURES / "valid" / "proc_ref_static_surface.orc"
PROC_REF_BIND_PROC_FIXTURE = FIXTURES / "valid" / "proc_ref_bind_proc_forwarding.orc"
LET_PROC_FIXTURE = FIXTURES / "valid" / "let_proc_proc_ref_forwarding.orc"
PROC_REF_LITERAL_REQUIRED_FIXTURE = FIXTURES / "invalid" / "proc_ref_literal_required.orc"
PROC_REF_SIGNATURE_INVALID_FIXTURE = FIXTURES / "invalid" / "proc_ref_signature_invalid.orc"
PROC_REF_SPECIALIZATION_CYCLE_FIXTURE = FIXTURES / "invalid" / "proc_ref_specialization_cycle.orc"


def _compile(path: Path, *, tmp_path: Path):
    return compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )


def _compile_validated(path: Path, *, tmp_path: Path):
    return compile_stage3_module(
        path,
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
    )


def _write_module(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _assert_proc_ref_cycle_diagnostics_at_authored_call_sites(
    excinfo: pytest.ExceptionInfo[LispFrontendCompileError],
) -> None:
    diagnostics = excinfo.value.diagnostics

    assert [diagnostic.code for diagnostic in diagnostics] == [
        "proc_ref_specialization_cycle",
        "proc_ref_specialization_cycle",
    ]
    assert [diagnostic.span.start.line for diagnostic in diagnostics] == [24, 18]
    assert [diagnostic.form_path for diagnostic in diagnostics] == [
        ("workflow-lisp", "defproc", "loop-helper"),
        ("workflow-lisp", "defproc", "use-runner"),
    ]
    assert diagnostics[0].message == "recursive procedure specialization cycle detected for `loop-helper`"
    assert diagnostics[1].message == "recursive procedure specialization cycle detected for `use-runner`"
    assert all("%proc-ref" not in diagnostic.message for diagnostic in diagnostics)


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def _infer_stage3_proc_ref_effects(path: Path):
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    procedure_catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    extern_environment = build_extern_environment(
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
    )
    command_boundary_environment = build_command_boundary_environment(
        {
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        }
    )
    return _infer_stage3_effect_summaries(
        procedure_defs,
        workflow_defs=workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
    )


def _proc_ref_discovery_context(tmp_path: Path):
    path = _write_module(
        tmp_path / "proc_ref_discovery_context.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc helper",
            "    ((fixed String)",
            "     (input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ((uses-command run_checks))",
            "    :lowering inline",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" input.report fixed)',
            "      :returns WorkflowOutput))",
            "  (defproc invoke-runner",
            "    ((runner ProcRef[WorkflowInput -> WorkflowOutput])",
            "     (input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (runner input)))",
        ],
    )
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    procedure_catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    extern_environment = build_extern_environment(provider_externs={}, prompt_externs={})
    command_boundary_environment = build_command_boundary_environment(
        {
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        }
    )
    typed_procedures, _typed_workflows, _diagnostics = _infer_stage3_effect_summaries(
        procedure_defs,
        workflow_defs=workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
    )
    return module, procedure_defs, typed_procedures, procedure_catalog, type_env


def _nested_proc_ref_specialization_expr(*, span, form_path: tuple[str, ...]) -> LetStarExpr:
    runner_ref = BindProcExpr(
        base_expr=ProcRefLiteralExpr(
            target_name="helper",
            authored_name="helper",
            span=span,
            form_path=form_path,
        ),
        bindings=(
            BindProcBinding(
                name="fixed",
                value_expr=LiteralExpr(
                    value="same",
                    literal_kind="string",
                    span=span,
                    form_path=form_path,
                ),
                keyword_span=span,
                keyword_form_path=form_path,
            ),
        ),
        span=span,
        form_path=form_path,
    )
    return LetStarExpr(
        bindings=(("runner", runner_ref),),
        body=ProcedureCallExpr(
            callee_name="invoke-runner",
            args=(
                NameExpr(name="runner", span=span, form_path=form_path),
                NameExpr(name="input", span=span, form_path=form_path),
            ),
            span=span,
            form_path=form_path,
        ),
        span=span,
        form_path=form_path,
    )


def _wrap_proc_ref_discovery_expr(case_name: str, nested_expr: LetStarExpr, *, span, form_path: tuple[str, ...]):
    placeholder = NameExpr(name="placeholder", span=span, form_path=form_path)
    if case_name == "run_provider_phase":
        return RunProviderPhaseExpr(
            phase_name="implementation",
            ctx_expr=placeholder,
            inputs_expr=nested_expr,
            provider=placeholder,
            prompt=placeholder,
            returns_type_name="WorkflowOutput",
            span=span,
            form_path=form_path,
        )
    if case_name == "produce_one_of":
        return ProduceOneOfExpr(
            returns_type_name="WorkflowOutput",
            ctx_expr=placeholder,
            producer=ProduceOneOfProducerSpec(
                kind="provider",
                provider_expr=placeholder,
                prompt_expr=placeholder,
                inputs=(nested_expr,),
            ),
            candidates=(),
            span=span,
            form_path=form_path,
        )
    if case_name == "resume_or_start":
        return ResumeOrStartExpr(
            resume_name="checks",
            ctx_expr=placeholder,
            resume_from_expr=placeholder,
            valid_when=(),
            start_expr=nested_expr,
            returns_type_name="WorkflowOutput",
            span=span,
            form_path=form_path,
        )
    if case_name == "resource_transition":
        return ResourceTransitionExpr(
            spec=ResourceTransitionSpec(
                transition_name="backlog-item",
                ctx_expr=placeholder,
                when_expr=None,
                resource_expr=nested_expr,
                from_queue_name="Queue.active",
                to_queue_name="Queue.in_progress",
                ledger_expr=placeholder,
                event_name="SELECTED",
            ),
            span=span,
            form_path=form_path,
        )
    if case_name == "finalize_selected_item":
        return FinalizeSelectedItemExpr(
            spec=FinalizeSelectedItemSpec(
                ctx_expr=placeholder,
                selected_expr=placeholder,
                queue_transition_expr=placeholder,
                roadmap_expr=placeholder,
                plan_expr=nested_expr,
                implementation_expr=placeholder,
            ),
            span=span,
            form_path=form_path,
        )
    if case_name == "backlog_drain":
        return BacklogDrainExpr(
            spec=BacklogDrainSpec(
                drain_name="neurips",
                ctx_expr=placeholder,
                selector_name="selector-run",
                run_item_name="run-selected-item",
                gap_drafter_name="gap-draft",
                providers_expr=nested_expr,
                max_iterations_expr=LiteralExpr(value=4, literal_kind="int", span=span, form_path=form_path),
            ),
            span=span,
            form_path=form_path,
        )
    raise AssertionError(f"unknown outer ProcRef discovery case: {case_name}")


def test_compile_stage3_collects_defproc_catalog_before_body_checking(tmp_path: Path) -> None:
    result = _compile(INLINE_FIXTURE, tmp_path=tmp_path)

    assert tuple(result.procedure_catalog.signatures_by_name) == ("build-checks", "copy-checks")
    assert [procedure.definition.name for procedure in result.typed_procedures] == [
        "build-checks",
        "copy-checks",
    ]
    assert type(result.typed_workflows[0].typed_body.expr).__name__ == "ProcedureCallExpr"
    assert type(result.typed_procedures[0].typed_body.expr).__name__ == "ProcedureCallExpr"


def test_elaboration_rejects_unknown_same_file_procedure_call_heads(tmp_path: Path) -> None:
    path = tmp_path / "unknown_procedure_call.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (report WorkReport))",
                "  (defworkflow orchestrate",
                "    ((report_path WorkReport))",
                "    -> ChecksResult",
                "    (missing-proc report_path)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "procedure_call_unknown")


def test_typecheck_rejects_procedure_effect_mismatch(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(EFFECT_MISMATCH_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "procedure_effect_mismatch")


def test_compile_rejects_recursive_procedure_cycle(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(CYCLE_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "proc_lowering_cycle")


def test_typecheck_rejects_procedure_arity_mismatch(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(ARITY_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "procedure_arity_mismatch")


def test_lowering_generates_private_workflow_for_reused_boundary_lowerable_procedure(tmp_path: Path) -> None:
    result = _compile(PRIVATE_WORKFLOW_FIXTURE, tmp_path=tmp_path)

    lowered_names = [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows]

    assert "%defproc_private_workflow.build-checks.v1" in lowered_names
    assert lowered_names.count("%defproc_private_workflow.build-checks.v1") == 1
    assert result.lowered_workflows[-1].typed_workflow.definition.name == "%defproc_private_workflow.build-checks.v1"
    assert "%defproc_private_workflow.build-checks.v1" in _compile_validated(
        PRIVATE_WORKFLOW_FIXTURE,
        tmp_path=tmp_path,
    ).validated_bundles


def test_lowering_preloads_nested_private_workflow_procedure_dependencies(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "nested_private_workflow_order_sensitive.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ChecksResult",
            "    (report WorkReport))",
            "  (defproc outer",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    :effects ((uses-command run_checks))",
            "    :lowering private-workflow",
            "    (inner report_path))",
            "  (defproc inner",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    :effects ((uses-command run_checks))",
            "    :lowering private-workflow",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" report_path)',
            "      :returns ChecksResult))",
            "  (defworkflow first",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (outer report_path))",
            "  (defworkflow second",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (outer report_path)))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    lowered_names = [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows]
    outer_private = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "%nested_private_workflow_order_sensitive.outer.v1"
    )
    validated = _compile_validated(path, tmp_path=tmp_path)

    assert "%nested_private_workflow_order_sensitive.inner.v1" in lowered_names
    assert "%nested_private_workflow_order_sensitive.outer.v1" in lowered_names
    assert outer_private.authored_mapping["steps"][0]["call"] == "%nested_private_workflow_order_sensitive.inner.v1"
    assert "%nested_private_workflow_order_sensitive.inner.v1" in validated.validated_bundles
    assert "%nested_private_workflow_order_sensitive.outer.v1" in validated.validated_bundles


def test_lowering_rejects_private_workflow_for_non_boundary_type(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(PRIVATE_BOUNDARY_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "procedure_effect_mismatch")

def test_auto_lowering_stays_inline_when_call_sites_cannot_bind_through_stage3_seam(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "auto_inline_required.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord Flagged",
            "    (flag Bool))",
            "  (defproc make-flag",
            "    ((flag Bool))",
            "    -> Flagged",
            "    :effects ()",
            "    :lowering auto",
            "    (record Flagged :flag flag))",
            "  (defproc forward-flag",
            "    ((flag Bool))",
            "    -> Flagged",
            "    :effects ()",
            "    :lowering inline",
            "    (make-flag flag))",
            "  (defworkflow first",
            "    ()",
            "    -> Flagged",
            "    (forward-flag true))",
            "  (defworkflow second",
            "    ()",
            "    -> Flagged",
            "    (forward-flag false)))",
        ],
    )

    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    procedure_catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    typed_procedures = _typecheck_procedure_definitions(
        procedure_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=None,
        command_boundary_environment=None,
    )
    typed_procedures, procedure_catalog = _validate_procedure_effects_and_cycles(
        typed_procedures,
        procedure_catalog=procedure_catalog,
    )
    typed_workflows = typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=None,
        command_boundary_environment=None,
        procedure_effects_by_name={
            procedure.definition.name: procedure.transitive_effect_summary
            for procedure in typed_procedures
        },
    )
    procedure = _resolve_procedure_lowering(
        typed_procedures,
        typed_workflows=typed_workflows,
        workflow_path=path,
        type_env=type_env,
    )["make-flag"]

    assert procedure.definition.name == "make-flag"
    assert procedure.resolved_lowering_mode.value == "inline"
    assert procedure.generated_workflow_name is None


def test_auto_lowering_counts_distinct_same_file_call_sites_not_reachable_paths(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "nested_distinct_site.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord Flagged",
            "    (flag Bool))",
            "  (defproc make-flag",
            "    ((flag Bool))",
            "    -> Flagged",
            "    :effects ()",
            "    :lowering auto",
            "    (record Flagged :flag flag))",
            "  (defproc wrap-flag",
            "    ((flag Bool))",
            "    -> Flagged",
            "    :effects ()",
            "    :lowering inline",
            "    (make-flag flag))",
            "  (defworkflow first",
            "    ((flag Bool))",
            "    -> Flagged",
            "    (wrap-flag flag))",
            "  (defworkflow second",
            "    ((flag Bool))",
            "    -> Flagged",
            "    (wrap-flag flag)))",
        ],
    )

    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    procedure_catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    typed_procedures = _typecheck_procedure_definitions(
        procedure_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=None,
        command_boundary_environment=None,
    )
    typed_procedures, procedure_catalog = _validate_procedure_effects_and_cycles(
        typed_procedures,
        procedure_catalog=procedure_catalog,
    )
    typed_workflows = typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=None,
        command_boundary_environment=None,
        procedure_effects_by_name={
            procedure.definition.name: procedure.transitive_effect_summary
            for procedure in typed_procedures
        },
    )
    procedure = _resolve_procedure_lowering(
        typed_procedures,
        typed_workflows=typed_workflows,
        workflow_path=path,
        type_env=type_env,
    )["make-flag"]

    assert procedure.definition.name == "make-flag"
    assert procedure.resolved_lowering_mode.value == "inline"
    assert procedure.generated_workflow_name is None


def test_auto_lowering_stays_inline_when_private_workflow_would_only_project_inputs(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "auto_inline_required_for_input_projection.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ChecksResult",
            "    (report WorkReport))",
            "  (defproc build-checks",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    :effects ()",
            "    :lowering auto",
            "    (record ChecksResult",
            "      :report report_path))",
            "  (defworkflow first",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (build-checks report_path))",
            "  (defworkflow second",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (build-checks report_path)))",
        ],
    )

    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    procedure_catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    typed_procedures = _typecheck_procedure_definitions(
        procedure_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=None,
        command_boundary_environment=None,
    )
    typed_procedures, procedure_catalog = _validate_procedure_effects_and_cycles(
        typed_procedures,
        procedure_catalog=procedure_catalog,
    )
    typed_workflows = typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=None,
        command_boundary_environment=None,
        procedure_effects_by_name={
            procedure.definition.name: procedure.transitive_effect_summary
            for procedure in typed_procedures
        },
    )
    procedure = _resolve_procedure_lowering(
        typed_procedures,
        typed_workflows=typed_workflows,
        workflow_path=path,
        type_env=type_env,
    )["build-checks"]

    assert procedure.definition.name == "build-checks"
    assert procedure.resolved_lowering_mode.value == "inline"
    assert procedure.generated_workflow_name is None
    result = compile_stage3_module(
        path,
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered_names = [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows]

    assert lowered_names == ["first", "second"]
    assert all(".build-checks.v1" not in name for name in lowered_names)


def test_explicit_private_workflow_rejects_input_projection_body(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "explicit_private_input_projection.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ChecksResult",
            "    (report WorkReport))",
            "  (defproc build-checks",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    :effects ()",
            "    :lowering private-workflow",
            "    (record ChecksResult",
            "      :report report_path))",
            "  (defworkflow first",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (build-checks report_path))",
            "  (defworkflow second",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (build-checks report_path)))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "procedure_effect_mismatch")


def test_direct_command_result_procedure_effects_do_not_require_hidden_bundle_writes(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "procedure_direct_command_result.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ChecksResult",
            "    (report WorkReport))",
            "  (defproc build-checks",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    :effects",
            "      ((uses-command run_checks))",
            "    :lowering inline",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" report_path)',
            "      :returns ChecksResult))",
            "  (defworkflow orchestrate",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (build-checks report_path)))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    procedure = next(procedure for procedure in result.typed_procedures if procedure.definition.name == "build-checks")

    assert procedure.transitive_effect_summary.transitive_effects == frozenset(
        {
            UsesCommandEffect(subject=("run_checks",)),
        }
    )


def test_inline_procedure_lowering_accepts_literal_command_arguments(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "procedure_inline_literal_argument.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ChecksResult",
            "    (report WorkReport))",
            "  (defproc build-checks",
            "    ((label String)",
            "     (report_path WorkReport))",
            "    -> ChecksResult",
            "    :effects",
            "      ((uses-command run_checks))",
            "    :lowering inline",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" label report_path)',
            "      :returns ChecksResult))",
            "  (defworkflow orchestrate",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            '    (build-checks "strict" report_path)))',
        ],
    )

    result = _compile(path, tmp_path=tmp_path)

    assert result.lowered_workflows[0].authored_mapping["steps"][0]["command"] == [
        "python",
        "scripts/run_checks.py",
        "strict",
        "${inputs.report_path}",
    ]


def test_private_workflow_call_lowers_local_record_argument_into_flattened_with_bindings(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "procedure_private_workflow_local_record_argument.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc build-checks",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects",
            "      ((uses-command run_checks))",
            "    :lowering private-workflow",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" input.report)',
            "      :returns WorkflowOutput))",
            "  (defworkflow entry",
            "    ((report_path WorkReport))",
            "    -> WorkflowOutput",
            "    (let* ((input (record WorkflowInput :report report_path)))",
            "      (build-checks input))))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    lowered = next(
        workflow.authored_mapping for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "entry"
    )

    assert lowered["steps"][0]["with"]["input__report"] == {"ref": "inputs.report_path"}


def test_direct_provider_result_procedure_effects_do_not_require_hidden_bundle_writes(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "procedure_direct_provider_result.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ChecksResult",
            "    (report WorkReport))",
            "  (defproc generate-checks",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    :effects",
            "      ((uses-provider providers.execute))",
            "    :lowering inline",
            "    (provider-result providers.execute",
            "      :prompt prompts.implementation.execute",
            "      :inputs (report_path)",
            "      :returns ChecksResult))",
            "  (defworkflow orchestrate",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (generate-checks report_path)))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    procedure = next(procedure for procedure in result.typed_procedures if procedure.definition.name == "generate-checks")

    assert procedure.transitive_effect_summary.transitive_effects == frozenset(
        {
            UsesProviderEffect(subject=("providers", "execute")),
        }
    )


def test_private_workflow_review_phase_procedure_rejects_review_loop_result_projection_boundary(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "procedure_review_phase_private_workflow.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule procedure_review_phase_private_workflow)",
            "  (import std/phase :only (ReviewFindings review-revise-loop))",
            "  (defenum BlockerClass",
            "    user_decision_required)",
            "  (defenum ReviewDecision",
            "    APPROVE",
            "    REVISE",
            "    BLOCKED)",
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
            "    (report_path WorkReport))",
            "  (defrecord ReviewSurfaceResult",
            "    (report_path WorkReport))",
            "  (defunion ReviewLoopResult",
            "    (APPROVED",
            "      (checks_report WorkReport)",
            "      (review_report WorkReport)",
            "      (review_decision ReviewDecision)",
            "      (findings ReviewFindings))",
            "    (BLOCKED",
            "      (progress_report WorkReport)",
            "      (blocker_class BlockerClass)",
            "      (findings ReviewFindings))",
            "    (EXHAUSTED",
            "      (last_review_report WorkReport)",
            "      (findings ReviewFindings)",
            "      (reason String)))",
            "  (defproc review-phase-helper",
            "    ((phase-ctx PhaseCtx)",
            "     (completed CompletedSurface)",
            "     (inputs ReviewInputs))",
            "    -> ReviewSurfaceResult",
            "    :effects ((uses-provider providers.review) (uses-provider providers.fix))",
            "    :lowering private-workflow",
            "    (with-phase phase-ctx implementation-review",
            "      (let* ((review",
            "               (review-revise-loop implementation-review",
            "                 :ctx phase-ctx",
            "                 :completed completed",
            "                 :inputs inputs",
            "                 :review-provider providers.review",
            "                 :fix-provider providers.fix",
            "                 :review-prompt prompts.review",
            "                 :fix-prompt prompts.fix",
            "                 :max 3",
            "                 :returns ReviewLoopResult)))",
            "        (match review",
            "          ((APPROVED approved)",
            "           (record ReviewSurfaceResult",
            "             :report_path approved.review_report))",
            "          ((BLOCKED blocked)",
            "           (record ReviewSurfaceResult",
            "             :report_path blocked.progress_report))",
            "          ((EXHAUSTED exhausted)",
            "           (record ReviewSurfaceResult",
            "             :report_path exhausted.last_review_report))))))",
            "  (defworkflow run-review",
            "    ((phase-ctx PhaseCtx)",
            "     (completed CompletedSurface)",
            "     (inputs ReviewInputs))",
            "    -> ReviewSurfaceResult",
            "    (review-phase-helper phase-ctx completed inputs)))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            provider_externs={
                "providers.review": "test-review-provider",
                "providers.fix": "test-fix-provider",
            },
            prompt_externs={
                "prompts.review": "prompts/review.md",
                "prompts.fix": "prompts/fix.md",
            },
            validate_shared=True,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "procedure_effect_mismatch")


def test_private_workflow_call_rejects_review_loop_boundary_before_allocator_reuse(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "procedure_review_phase_private_workflow_allocator.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule procedure_review_phase_private_workflow_allocator)",
            "  (import std/phase :only (ReviewFindings review-revise-loop))",
            "  (defenum BlockerClass",
            "    user_decision_required)",
            "  (defenum ReviewDecision",
            "    APPROVE",
            "    REVISE",
            "    BLOCKED)",
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
            "    (report_path WorkReport))",
            "  (defrecord ReviewSurfaceResult",
            "    (report_path WorkReport))",
            "  (defunion ReviewLoopResult",
            "    (APPROVED",
            "      (checks_report WorkReport)",
            "      (review_report WorkReport)",
            "      (review_decision ReviewDecision)",
            "      (findings ReviewFindings))",
            "    (BLOCKED",
            "      (progress_report WorkReport)",
            "      (blocker_class BlockerClass)",
            "      (findings ReviewFindings))",
            "    (EXHAUSTED",
            "      (last_review_report WorkReport)",
            "      (findings ReviewFindings)",
            "      (reason String)))",
            "  (defproc review-phase-helper",
            "    ((phase-ctx PhaseCtx)",
            "     (completed CompletedSurface)",
            "     (inputs ReviewInputs))",
            "    -> ReviewSurfaceResult",
            "    :effects ((uses-provider providers.review) (uses-provider providers.fix))",
            "    :lowering private-workflow",
            "    (with-phase phase-ctx implementation-review",
            "      (let* ((review",
            "               (review-revise-loop implementation-review",
            "                 :ctx phase-ctx",
            "                 :completed completed",
            "                 :inputs inputs",
            "                 :review-provider providers.review",
            "                 :fix-provider providers.fix",
            "                 :review-prompt prompts.review",
            "                 :fix-prompt prompts.fix",
            "                 :max 3",
            "                 :returns ReviewLoopResult)))",
            "        (match review",
            "          ((APPROVED approved)",
            "           (record ReviewSurfaceResult",
            "             :report_path approved.review_report))",
            "          ((BLOCKED blocked)",
            "           (record ReviewSurfaceResult",
            "             :report_path blocked.progress_report))",
            "          ((EXHAUSTED exhausted)",
            "           (record ReviewSurfaceResult",
            "             :report_path exhausted.last_review_report))))))",
            "  (defworkflow run-review",
            "    ((phase-ctx PhaseCtx)",
            "     (completed CompletedSurface)",
            "     (inputs ReviewInputs))",
            "    -> ReviewSurfaceResult",
            "    (review-phase-helper phase-ctx completed inputs)))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            provider_externs={
                "providers.review": "test-review-provider",
                "providers.fix": "test-fix-provider",
            },
            prompt_externs={
                "prompts.review": "prompts/review.md",
                "prompts.fix": "prompts/fix.md",
            },
            validate_shared=True,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "procedure_effect_mismatch")


def test_private_workflow_with_phase_binding_exports_step_backed_outputs(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "procedure_with_phase_binding_private_workflow.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defenum BlockerClass",
            "    missing_resource",
            "    unavailable_hardware",
            "    roadmap_conflict",
            "    external_dependency_outside_authority",
            "    user_decision_required",
            "    unrecoverable_after_fix_attempt)",
            "  (defenum ImplementationStateTag",
            "    COMPLETED",
            "    BLOCKED)",
            "  (defpath DesignDocPath",
            "    :kind relpath",
            '    :under "docs/design"',
            "    :must-exist true)",
            "  (defpath PlanDocPath",
            "    :kind relpath",
            '    :under "docs/plans"',
            "    :must-exist true)",
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defpath WorkReportTarget",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist false)",
            "  (defpath ImplementationStateBundlePath",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist false)",
            "  (defrecord ImplementationAttemptInputs",
            "    (design DesignDocPath)",
            "    (plan PlanDocPath))",
            "  (defrecord ImplementationAttemptPhaseCtx",
            "    (implementation_state_bundle_path ImplementationStateBundlePath)",
            "    (execution_report_target WorkReportTarget)",
            "    (progress_report_target WorkReportTarget))",
            "  (defunion ImplementationAttempt",
            "    (COMPLETED",
            "      (implementation_state ImplementationStateTag)",
            "      (execution_report_path WorkReport))",
            "    (BLOCKED",
            "      (implementation_state ImplementationStateTag)",
            "      (progress_report_path WorkReport)",
            "      (blocker_class BlockerClass)))",
            "  (defrecord ImplementationAttemptReport",
            "    (report_path WorkReport))",
            "  (defproc private-run",
            "    ((phase-ctx ImplementationAttemptPhaseCtx)",
            "     (inputs ImplementationAttemptInputs))",
            "    -> ImplementationAttemptReport",
            "    :effects ((uses-provider providers.execute))",
            "    :lowering private-workflow",
            "    (let* ((phase-result",
            "             (with-phase phase-ctx implementation",
                "               (provider-result providers.execute",
            "                 :prompt prompts.implementation.execute",
            "                 :inputs (inputs.design",
            "                          inputs.plan",
            "                          (phase-target execution-report)",
            "                          (phase-target progress-report))",
            "                 :returns ImplementationAttempt))))",
            "      (match phase-result",
            "        ((COMPLETED completed)",
            "         (record ImplementationAttemptReport",
            "           :report_path completed.execution_report_path))",
            "        ((BLOCKED blocked)",
            "         (record ImplementationAttemptReport",
            "           :report_path blocked.progress_report_path)))))",
            "  (defworkflow run-private",
            "    ((phase-ctx ImplementationAttemptPhaseCtx)",
            "     (inputs ImplementationAttemptInputs))",
            "    -> ImplementationAttemptReport",
            "    (private-run phase-ctx inputs)))",
        ],
    )

    result = compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered_names = [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows]
    private_names = [name for name in lowered_names if name.endswith(".private-run.v1")]

    assert private_names == ["%procedure_with_phase_binding_private_workflow.private-run.v1"]
    outer_workflow = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-private"
    )
    assert any(step.get("call") == private_names[0] for step in outer_workflow["steps"])


def test_private_workflow_effectful_match_arms_export_step_backed_outputs(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "procedure_effectful_match_private_workflow.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defenum BlockerClass",
            "    missing_resource",
            "    unavailable_hardware)",
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord AttemptReport",
            "    (report WorkReport))",
            "  (defunion ImplementationState",
            "    (COMPLETED",
            "      (execution_report WorkReport))",
            "    (BLOCKED",
            "      (progress_report WorkReport)",
            "      (blocker_class BlockerClass)))",
            "  (defproc private-run",
            "    ((report_path WorkReport))",
            "    -> AttemptReport",
            "    :effects ((uses-provider providers.execute))",
            "    :lowering private-workflow",
            "    (let* ((attempt",
            "             (provider-result providers.execute",
            "               :prompt prompts.implementation.execute",
            "               :inputs (report_path)",
            "               :returns ImplementationState)))",
            "      (match attempt",
            "        ((COMPLETED completed)",
            "         (provider-result providers.execute",
            "           :prompt prompts.implementation.execute",
            "           :inputs (completed.execution_report)",
            "           :returns AttemptReport))",
            "        ((BLOCKED blocked)",
            "         (provider-result providers.execute",
            "           :prompt prompts.implementation.execute",
            "           :inputs (blocked.progress_report)",
            "           :returns AttemptReport)))))",
            "  (defworkflow run-private",
            "    ((report_path WorkReport))",
            "    -> AttemptReport",
            "    (private-run report_path)))",
        ],
    )

    result = compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    lowered_names = [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows]
    private_names = [name for name in lowered_names if name.endswith(".private-run.v1")]

    assert private_names == ["%procedure_effectful_match_private_workflow.private-run.v1"]
    outer_workflow = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-private"
    )
    assert any(step.get("call") == private_names[0] for step in outer_workflow["steps"])


def test_private_workflow_match_binding_exports_step_backed_outputs(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "procedure_match_binding_private_workflow.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defenum BlockerClass",
            "    missing_resource",
            "    unavailable_hardware)",
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord AttemptReport",
            "    (report WorkReport))",
            "  (defrecord FinalReport",
            "    (report WorkReport))",
            "  (defunion ImplementationState",
            "    (COMPLETED",
            "      (execution_report WorkReport))",
            "    (BLOCKED",
            "      (progress_report WorkReport)",
            "      (blocker_class BlockerClass)))",
            "  (defproc private-run",
            "    ((report_path WorkReport))",
            "    -> FinalReport",
            "    :effects ((uses-provider providers.execute))",
            "    :lowering private-workflow",
            "    (let* ((attempt",
            "             (provider-result providers.execute",
            "               :prompt prompts.implementation.execute",
            "               :inputs (report_path)",
            "               :returns ImplementationState))",
            "            (alias attempt)",
            "            (attempt-report",
            "             (match alias",
            "               ((COMPLETED completed)",
            "                (provider-result providers.execute",
            "                  :prompt prompts.implementation.execute",
            "                  :inputs (completed.execution_report)",
            "                  :returns AttemptReport))",
            "               ((BLOCKED blocked)",
            "                (provider-result providers.execute",
            "                  :prompt prompts.implementation.execute",
            "                  :inputs (blocked.progress_report)",
            "                  :returns AttemptReport))))",
            "            (final-report",
            "             (provider-result providers.execute",
            "               :prompt prompts.implementation.execute",
            "               :inputs (attempt-report.report)",
            "               :returns FinalReport)))",
            "      final-report))",
            "  (defworkflow run-private",
            "    ((report_path WorkReport))",
            "    -> FinalReport",
            "    (private-run report_path)))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)

    lowered_names = [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows]
    private_names = [name for name in lowered_names if name.endswith(".private-run.v1")]

    assert private_names == ["%procedure_match_binding_private_workflow.private-run.v1"]
    outer_workflow = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-private"
    )
    assert any(step.get("call") == private_names[0] for step in outer_workflow["steps"])


def test_private_workflow_union_match_uses_private_workflow_metadata_not_name_heuristic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_module(
        tmp_path / "procedure_union_match_private_workflow.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defenum BlockerClass",
            "    missing_resource",
            "    unavailable_hardware)",
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defunion AttemptResult",
            "    (APPROVED",
            "      (execution_report_path WorkReport))",
            "    (BLOCKED",
            "      (progress_report_path WorkReport)",
            "      (blocker_class BlockerClass)))",
            "  (defproc private-wrap",
            "    ((report_path WorkReport))",
            "    -> AttemptResult",
            "    :effects ((uses-provider providers.execute))",
            "    :lowering private-workflow",
            "    (let* ((attempt",
            "             (provider-result providers.execute",
            "               :prompt prompts.implementation.execute",
            "               :inputs (report_path)",
            "               :returns AttemptResult)))",
            "      (match attempt",
            "        ((APPROVED approved)",
            "         (variant AttemptResult APPROVED",
            "           :execution_report_path approved.execution_report_path))",
            "        ((BLOCKED blocked)",
            "         (variant AttemptResult BLOCKED",
            "           :progress_report_path blocked.progress_report_path",
            "           :blocker_class blocked.blocker_class)))))",
            "  (defworkflow run-private",
            "    ((report_path WorkReport))",
            "    -> AttemptResult",
            "    (private-wrap report_path)))",
        ],
    )

    compiled = compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )
    private_proc = next(
        procedure for procedure in compiled.typed_procedures if procedure.definition.name == "private-wrap"
    )
    custom_private_proc = replace(
        private_proc,
        resolved_lowering_mode=ProcedureLoweringMode.PRIVATE_WORKFLOW,
        generated_workflow_name="%custom.private-wrap",
    )
    lowering_module = importlib.import_module("orchestrator.workflow_lisp.lowering")
    monkeypatch.setattr(
        lowering_module,
        "_resolve_procedure_lowering",
        lambda *args, **kwargs: {"private-wrap": custom_private_proc},
    )

    lowered = lower_workflow_definitions(
        compiled.typed_workflows,
        typed_procedures=compiled.typed_procedures,
        procedure_catalog=compiled.procedure_catalog,
        workflow_path=path,
        workflow_catalog=compiled.workflow_catalog,
        imported_workflow_bundles=compiled.workflow_catalog.imported_bundles_by_name,
        extern_environment=compiled.extern_environment,
        command_boundary_environment=compiled.command_boundary_environment,
        type_env=FrontendTypeEnvironment.from_module(compiled.module),
    )
    private_workflow = next(
        workflow for workflow in lowered if workflow.typed_workflow.definition.name == "%custom.private-wrap"
    )

    assert not any(
        name.endswith("__match_attempt__result_bundle") for name in private_workflow.authored_mapping["inputs"]
    )


def test_procedure_effect_validation_includes_nested_workflow_effects(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "procedure_nested_workflow_effects.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ChecksResult",
            "    (report WorkReport))",
            "  (defworkflow run-checks",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" report_path)',
            "      :returns ChecksResult))",
            "  (defproc wrap-checks",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    :effects",
            "      ((calls-workflow run-checks)",
            "       (uses-command run_checks))",
            "    :lowering inline",
            "    (call run-checks :report_path report_path))",
            "  (defworkflow orchestrate",
            "    ((report_path WorkReport))",
            "    -> ChecksResult",
            "    (wrap-checks report_path)))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    procedure = next(procedure for procedure in result.typed_procedures if procedure.definition.name == "wrap-checks")

    assert procedure.transitive_effect_summary.transitive_effects == frozenset(
        {
            CallsWorkflowEffect(subject=("run-checks",)),
            UsesCommandEffect(subject=("run_checks",)),
        }
    )


def test_shared_validation_remap_renders_procedure_call_and_definition_notes(tmp_path: Path) -> None:
    path = tmp_path / "procedure_shared_validation_remap.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath EscapedReport",
                "    :kind relpath",
                '    :under "../escape"',
                "    :must-exist true)",
                "  (defrecord EscapedSummary",
                "    (report EscapedReport))",
                "  (defproc escaped-summary",
                "    ((report_path EscapedReport))",
                "    -> EscapedSummary",
                "    :effects ()",
                "    :lowering inline",
                "    (record EscapedSummary",
                "      :report report_path))",
                "  (defworkflow orchestrate",
                "    ((report_path EscapedReport))",
                "    -> EscapedSummary",
                "    (escaped-summary report_path)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=True,
            workspace_root=tmp_path,
        )

    rendered = render_diagnostic(excinfo.value.diagnostics[0])

    assert "procedure call site at" in rendered
    assert "procedure definition at" in rendered


def test_compile_stage3_entrypoint_registers_imported_procedure_signatures(tmp_path: Path) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    source_root = MODULE_FIXTURES / "valid" / "callables"
    result = compile_fn(
        source_root / "neurips" / "entry.orc",
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert "neurips/procedures::build-checks" in result.entry_result.procedure_catalog.signatures_by_name


def test_procedures_can_call_pure_helpers_without_introducing_extra_effects(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "procedure_helper_call.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ChecksResult",
            "    (report WorkReport))",
            "  (defrecord ImplementationSummary",
            "    (report WorkReport))",
            "  (defun summarize",
            "    ((input ChecksResult))",
            "    -> ImplementationSummary",
            "    (record ImplementationSummary :report input.report))",
            "  (defproc wrap-summary",
            "    ((input ChecksResult))",
            "    -> ImplementationSummary",
            "    :effects ()",
            "    (summarize input))",
            "  (defworkflow orchestrate",
            "    ((input ChecksResult))",
            "    -> ImplementationSummary",
            "    (wrap-summary input)))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    procedure = next(procedure for procedure in result.typed_procedures if procedure.definition.name == "wrap-summary")

    assert procedure.transitive_effect_summary.transitive_effects == frozenset()


def test_compile_stage3_elaborates_authored_union_variant_constructor_to_union_variant_expr(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "union_variant_expr.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defunion WorkflowResult",
            "    (APPROVED",
            "      (report WorkReport)",
            "      (message String))",
            "    (BLOCKED",
            "      (report WorkReport)",
            "      (reason String)))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (variant WorkflowResult APPROVED",
            "      :report input.report",
            '      :message "ok"))',
            ")",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    entry = next(workflow for workflow in result.typed_workflows if workflow.definition.name == "entry")

    assert isinstance(entry.typed_body.expr, UnionVariantExpr)
    assert entry.typed_body.expr.type_name == "WorkflowResult"
    assert entry.typed_body.expr.variant_name == "APPROVED"
    assert [field_name for field_name, _ in entry.typed_body.expr.fields] == ["report", "message"]


def test_typecheck_authored_union_variant_constructor_rejects_non_union_target(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "union_variant_non_union_target.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowResult",
            "    (report WorkReport))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (variant WorkflowResult APPROVED",
            "      :report input.report))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_typecheck_authored_union_variant_constructor_rejects_unknown_variant(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "union_variant_unknown_variant.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defunion WorkflowResult",
            "    (APPROVED",
            "      (report WorkReport)))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (variant WorkflowResult BLOCKED",
            "      :report input.report))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "union_variant_unknown")


def test_typecheck_authored_union_variant_constructor_rejects_missing_required_field(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "union_variant_missing_field.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defunion WorkflowResult",
            "    (APPROVED",
            "      (report WorkReport)",
            "      (message String)))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (variant WorkflowResult APPROVED",
            "      :report input.report))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "record_field_missing")


def test_typecheck_authored_union_variant_constructor_rejects_unknown_field(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "union_variant_unknown_field.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defunion WorkflowResult",
            "    (APPROVED",
            "      (report WorkReport)))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (variant WorkflowResult APPROVED",
            "      :report input.report",
            '      :message "unexpected"))',
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "record_field_unknown")


def test_typecheck_authored_union_variant_constructor_rejects_duplicate_field(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "union_variant_duplicate_field.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defunion WorkflowResult",
            "    (APPROVED",
            "      (report WorkReport)))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (variant WorkflowResult APPROVED",
            "      :report input.report",
            "      :report input.report))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "record_field_duplicate")


def test_typecheck_authored_union_variant_constructor_rejects_field_type_mismatch(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "union_variant_field_type_invalid.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defunion WorkflowResult",
            "    (APPROVED",
            "      (report WorkReport)",
            "      (message String)))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (variant WorkflowResult APPROVED",
            "      :report input.report",
            "      :message input))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "type_mismatch")


def test_compile_stage3_supports_pure_helper_authored_union_variant_constructor(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "union_variant_pure_helper.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defunion WorkflowResult",
            "    (APPROVED",
            "      (report WorkReport)",
            "      (message String))",
            "    (BLOCKED",
            "      (report WorkReport)",
            "      (reason String)))",
            "  (defun wrap",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (variant WorkflowResult APPROVED",
            "      :report input.report",
            '      :message "ok"))',
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (wrap input))",
            ")",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)

    assert "entry" in {workflow.definition.name for workflow in result.typed_workflows}

def test_lowering_authored_union_variant_constructor_reuses_existing_union_output_path(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "union_variant_lowering.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defunion WorkflowResult",
            "    (APPROVED",
            "      (report WorkReport)",
            "      (message String))",
            "    (BLOCKED",
            "      (report WorkReport)",
            "      (reason String)))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowResult",
            "    (variant WorkflowResult APPROVED",
            "      :report input.report",
            '      :message "ok"))',
            ")",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    lowered = next(workflow for workflow in result.lowered_workflows if workflow.typed_workflow.definition.name == "entry")
    step = lowered.authored_mapping["steps"][0]
    values = {value["name"]: value["source"] for value in step["materialize_artifacts"]["values"]}

    assert step["name"] == "entry"
    assert values["variant"] == {"literal": "APPROVED"}
    assert values["report"] == {"ref": "inputs.input__report"}
    assert values["message"] == {"literal": "ok"}
    assert step["variant_output"]["path"] == "${inputs.__write_root__entry__result_bundle}"
    assert lowered.origin_map.step_spans["entry"].form_path == ("workflow-lisp", "defworkflow", "entry")
    assert lowered.origin_map.generated_output_spans["return__variant"].form_path == (
        "workflow-lisp",
        "defworkflow",
        "entry",
    )


def test_compile_stage3_supports_forwarded_workflow_ref_procedure_calls(tmp_path: Path) -> None:
    result = _compile_validated(WORKFLOW_REF_FORWARDING_FIXTURE, tmp_path=tmp_path)

    assert "entry" in result.validated_bundles
    assert result.typed_procedures[0].definition.name == "invoke-runner"


def test_compile_stage3_supports_proc_ref_signature_parameters_and_same_file_literals(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.expressions import ProcRefLiteralExpr, ProcedureCallExpr
    from orchestrator.workflow_lisp.type_env import ProcRefTypeRef

    result = _compile_validated(PROC_REF_FIXTURE, tmp_path=tmp_path)
    procedure = next(
        procedure for procedure in result.typed_procedures if procedure.definition.name == "forward-helper"
    )
    entry = next(workflow for workflow in result.typed_workflows if workflow.definition.name == "entry")
    call_expr = entry.typed_body.expr

    assert isinstance(procedure.signature.params[0][1], ProcRefTypeRef)
    assert isinstance(call_expr, ProcedureCallExpr)
    assert isinstance(call_expr.args[0], ProcRefLiteralExpr)
    assert call_expr.args[0].target_name == "helper"


def test_compile_stage3_supports_bind_proc_forwarding_and_lexical_proc_ref_calls(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.expressions import BindProcExpr, LetStarExpr, ProcedureCallExpr

    result = _compile_validated(PROC_REF_BIND_PROC_FIXTURE, tmp_path=tmp_path)
    invoke_runner = next(
        procedure for procedure in result.typed_procedures if procedure.definition.name == "invoke-runner"
    )
    entry = next(workflow for workflow in result.typed_workflows if workflow.definition.name == "entry")
    entry_body = entry.typed_body.expr

    assert isinstance(invoke_runner.typed_body.expr, ProcedureCallExpr)
    assert invoke_runner.typed_body.expr.callee_name == "runner"
    assert isinstance(entry_body, LetStarExpr)
    assert isinstance(entry_body.bindings[0][1], BindProcExpr)
    assert "entry" in result.validated_bundles


def test_let_proc_resolves_to_hidden_generated_proc_ref(tmp_path: Path) -> None:
    result = _compile(LET_PROC_FIXTURE, tmp_path=tmp_path)
    generated = [p for p in result.typed_procedures if p.definition.name.startswith("%let-proc.")]

    assert len(generated) == 1
    assert generated[0].definition.name == generated[0].signature.name
    assert generated[0].specialization is None


def test_compile_rejects_let_proc_generated_name_authored_reference(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(FIXTURES / "invalid" / "let_proc_generated_name_private.orc", tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "let_proc_generated_name_private")


def test_let_proc_generated_names_change_when_local_body_changes(tmp_path: Path) -> None:
    def write_case(path: Path, helper_name: str) -> Path:
        return _write_module(
            path,
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord WorkflowInput",
                "    (report WorkReport))",
                "  (defrecord WorkflowOutput",
                "    (report WorkReport))",
                "  (defproc invoke-runner",
                "    ((runner ProcRef[WorkflowInput -> WorkflowOutput])",
                "     (input WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ()",
                "    :lowering inline",
                "    (runner input))",
                f"  (defproc {helper_name}",
                "    ((item WorkflowInput))",
                "    -> WorkflowOutput",
                "    :effects ()",
                "    :lowering inline",
                "    (record WorkflowOutput :report item.report))",
                "  (defworkflow entry",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput",
                "                :captures ()",
                f"                ({helper_name} item))",
                "      (invoke-runner (proc-ref run-local) input)))",
                ")",
            ],
        )

    first = _compile(write_case(tmp_path / "let_proc_name_case.orc", "helper-a"), tmp_path=tmp_path)
    first_name = next(
        procedure.definition.name
        for procedure in first.typed_procedures
        if procedure.definition.name.startswith("%let-proc.")
    )
    second = _compile(write_case(tmp_path / "let_proc_name_case.orc", "helper-b"), tmp_path=tmp_path)
    second_name = next(
        procedure.definition.name
        for procedure in second.typed_procedures
        if procedure.definition.name.startswith("%let-proc.")
    )

    assert first_name != second_name


def test_let_proc_generated_names_are_stable_across_workspace_roots(tmp_path: Path) -> None:
    lines = [
        "(workflow-lisp",
        '  (:language "0.1")',
        '  (:target-dsl "2.14")',
        "  (defpath WorkReport",
        "    :kind relpath",
        '    :under "artifacts/work"',
        "    :must-exist true)",
        "  (defrecord WorkflowInput",
        "    (report WorkReport))",
        "  (defrecord WorkflowOutput",
        "    (report WorkReport))",
        "  (defproc invoke-runner",
        "    ((runner ProcRef[WorkflowInput -> WorkflowOutput])",
        "     (input WorkflowInput))",
        "    -> WorkflowOutput",
        "    :effects ()",
        "    :lowering inline",
        "    (runner input))",
        "  (defworkflow entry",
        "    ((input WorkflowInput))",
        "    -> WorkflowOutput",
        "    (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput",
        "                :captures ()",
        "                (record WorkflowOutput :report item.report))",
        "      (invoke-runner (proc-ref run-local) input)))",
        ")",
    ]
    first_path = _write_module(tmp_path / "root-a" / "stable.orc", lines)
    second_path = _write_module(tmp_path / "root-b" / "stable.orc", lines)

    first = _compile(first_path, tmp_path=tmp_path / "workspace-a")
    second = _compile(second_path, tmp_path=tmp_path / "workspace-b")

    first_name = next(
        procedure.definition.name
        for procedure in first.typed_procedures
        if procedure.definition.name.startswith("%let-proc.")
    )
    second_name = next(
        procedure.definition.name
        for procedure in second.typed_procedures
        if procedure.definition.name.startswith("%let-proc.")
    )

    assert first_name == second_name


def test_compile_clears_generated_local_procedure_state_after_failure(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "let_proc_state_cleanup.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc build-runner",
            "    ()",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput",
            "                :captures ()",
            "                (record WorkflowOutput :report item.report))",
            "      true))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "procedure_return_type_invalid")
    assert consume_generated_local_procedures() == ()


def test_stage3_materializes_proc_ref_specializations_before_lowering_and_preserves_effects() -> None:
    typed_procedures, typed_workflows, _ = _infer_stage3_proc_ref_effects(PROC_REF_BIND_PROC_FIXTURE)

    typed_names = {procedure.definition.name for procedure in typed_procedures}
    entry = next(workflow for workflow in typed_workflows if workflow.definition.name == "entry")
    specialized_invoke_runner = next(
        procedure
        for procedure in typed_procedures
        if procedure.definition.name.startswith("%proc-ref-call.invoke_runner.")
    )

    assert any(name.startswith("%proc-ref.helper.") for name in typed_names)
    assert specialized_invoke_runner.direct_effect_summary.procedure_edges
    assert entry.effect_summary.transitive_effects == frozenset(
        {
            UsesCommandEffect(subject=("run_checks",)),
        }
    )


@pytest.mark.parametrize(
    "case_name",
    [
        "run_provider_phase",
        "produce_one_of",
        "resume_or_start",
        "resource_transition",
        "finalize_selected_item",
        "backlog_drain",
    ],
)
def test_stage3_discovery_walks_nested_proc_ref_specializations_in_owner_forms(
    tmp_path: Path,
    case_name: str,
) -> None:
    module, procedure_defs, typed_procedures, procedure_catalog, type_env = _proc_ref_discovery_context(tmp_path)
    span = procedure_defs[0].span
    form_path = ("workflow-lisp", "defworkflow", f"walk-{case_name}")
    workflow_return_type = type_env.resolve_type(
        "WorkflowOutput",
        span=module.span,
        form_path=("workflow-lisp",),
    )
    nested_expr = _nested_proc_ref_specialization_expr(span=span, form_path=form_path)
    wrapped_expr = _wrap_proc_ref_discovery_expr(case_name, nested_expr, span=span, form_path=form_path)
    typed_workflow = TypedWorkflowDef(
        definition=WorkflowDef(
            name=f"walk-{case_name}",
            params=(),
            return_type_name="WorkflowOutput",
            body=procedure_defs[0].body,
            span=span,
            form_path=form_path,
        ),
        signature=WorkflowSignature(
            name=f"walk-{case_name}",
            params=(),
            return_type_ref=workflow_return_type,
            span=span,
            form_path=form_path,
        ),
        typed_body=TypedExpr(
            expr=wrapped_expr,
            type_ref=workflow_return_type,
            span=span,
            form_path=form_path,
        ),
    )

    compiler_module = _compiler_module()
    discovered = compiler_module._discover_proc_ref_specializations(
        typed_procedures=typed_procedures,
        typed_workflows=(typed_workflow,),
        procedure_catalog=procedure_catalog,
        type_env=type_env,
    )

    assert [
        procedure.definition.name
        for procedure in discovered
        if procedure.definition.name.startswith("%proc-ref-call.invoke_runner.")
    ]


def test_stage3_preserves_nested_proc_ref_effects_inside_run_provider_phase(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "proc_ref_nested_run_provider_phase.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
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
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defunion ImplementationAttempt",
            "    (COMPLETED",
            "      (report WorkReport)))",
            "  (defproc build-inputs-helper",
            "    ((fixed String)",
            "     (input WorkflowInput))",
            "    -> WorkflowInput",
            "    :effects ((uses-command run_checks))",
            "    :lowering inline",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" input.report fixed)',
            "      :returns WorkflowInput))",
            "  (defproc invoke-runner",
            "    ((runner ProcRef[WorkflowInput -> WorkflowInput])",
            "     (input WorkflowInput))",
            "    -> WorkflowInput",
            "    :effects ()",
            "    :lowering inline",
            "    (runner input))",
            "  (defworkflow entry",
            "    ((phase-ctx PhaseCtx)",
            "     (input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (with-phase phase-ctx implementation",
            "      (let* ((attempt",
            "               (run-provider-phase implementation",
            "                 :ctx phase-ctx",
            "                 :inputs",
            "                   (let* ((runner (bind-proc (proc-ref build-inputs-helper)",
            '                                    :fixed "nested")))',
            "                     (invoke-runner runner input))",
            "                 :provider providers.execute",
            "                 :prompt prompts.implementation.execute",
            "                 :returns ImplementationAttempt)))",
            "        (match attempt",
            "          ((COMPLETED completed)",
            "           (record WorkflowOutput",
            "             :report completed.report)))))",
            "))",
        ],
    )

    typed_procedures, typed_workflows, _ = _infer_stage3_proc_ref_effects(path)
    entry = next(workflow for workflow in typed_workflows if workflow.definition.name == "entry")

    assert any(
        procedure.definition.name.startswith("%proc-ref-call.invoke_runner.")
        for procedure in typed_procedures
    )
    assert UsesCommandEffect(subject=("run_checks",)) in entry.effect_summary.transitive_effects


def test_compile_stage3_supports_let_proc_proc_ref_forwarding_and_shared_validation(
    tmp_path: Path,
) -> None:
    result = _compile_validated(LET_PROC_FIXTURE, tmp_path=tmp_path)
    generated = next(
        procedure for procedure in result.typed_procedures if procedure.definition.name.startswith("%let-proc.")
    )

    assert generated.definition.name in result.procedure_catalog.signatures_by_name
    assert generated.transitive_effect_summary.transitive_effects == frozenset(
        {
            UsesCommandEffect(subject=("run_checks",)),
        }
    )


def test_compile_rejects_let_proc_name_collision_in_same_scope(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "let_proc_name_collision.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (let* ((run-local input))",
            "      (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput",
            "                  :captures ()",
            "                  (record WorkflowOutput :report item.report))",
            "        (record WorkflowOutput :report input.report))))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "let_proc_name_collision")


def test_compile_rejects_let_proc_return_type_mismatch_with_v1_code(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "let_proc_return_type_invalid.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (let-proc (run-local ((item WorkflowInput)) -> WorkflowInput",
            "                :captures ()",
            "                (record WorkflowOutput :report item.report))",
            "      (record WorkflowOutput :report input.report)))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "let_proc_return_type_invalid")


@pytest.mark.parametrize(
    ("fixture_name", "code"),
    [
        ("let_proc_unknown_capture.orc", "let_proc_capture_unknown"),
        ("let_proc_duplicate_capture.orc", "let_proc_capture_duplicate"),
        ("let_proc_recursive.orc", "let_proc_recursive_unsupported"),
        ("let_proc_scope_escape.orc", "let_proc_scope_escape"),
    ],
)
def test_compile_rejects_invalid_let_proc_scopes(
    tmp_path: Path,
    fixture_name: str,
    code: str,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(FIXTURES / "invalid" / fixture_name, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, code)


def test_compile_rejects_let_proc_scope_escape_wrapped_in_if(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "let_proc_scope_escape_if.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc build-runner",
            "    ()",
            "    -> ProcRef[WorkflowInput -> WorkflowOutput]",
            "    :effects ()",
            "    :lowering inline",
            "    (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput",
            "                :captures ()",
            "                (record WorkflowOutput :report item.report))",
            "      (if true",
            "        (proc-ref run-local)",
            "        (proc-ref run-local)))))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "let_proc_scope_escape")


def test_compile_rejects_let_proc_scope_escape_nested_in_bind_proc_binding(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "let_proc_scope_escape_bind_proc.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc invoke-runner",
            "    ((runner ProcRef[WorkflowInput -> WorkflowOutput])",
            "     (input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (runner input))",
            "  (defproc build-runner",
            "    ()",
            "    -> ProcRef[WorkflowInput -> WorkflowOutput]",
            "    :effects ()",
            "    :lowering inline",
            "    (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput",
            "                :captures ()",
            "                (record WorkflowOutput :report item.report))",
            "      (bind-proc (proc-ref invoke-runner)",
            "        :runner (proc-ref run-local)))))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "let_proc_scope_escape")


def test_compile_rejects_let_proc_scope_escape_forwarded_through_proc_return(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "let_proc_scope_escape_proc_forwarding.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc id-runner",
            "    ((runner ProcRef[WorkflowInput -> WorkflowOutput]))",
            "    -> ProcRef[WorkflowInput -> WorkflowOutput]",
            "    :effects ()",
            "    :lowering inline",
            "    runner)",
            "  (defproc build-runner",
            "    ()",
            "    -> ProcRef[WorkflowInput -> WorkflowOutput]",
            "    :effects ()",
            "    :lowering inline",
            "    (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput",
            "                :captures ()",
            "                (record WorkflowOutput :report item.report))",
            "      (id-runner (proc-ref run-local))))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "let_proc_scope_escape")


def test_compile_rejects_let_proc_scope_escape_forwarded_through_helper_return(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "let_proc_scope_escape_helper_forwarding.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defun id-runner",
            "    ((runner ProcRef[WorkflowInput -> WorkflowOutput]))",
            "    -> ProcRef[WorkflowInput -> WorkflowOutput]",
            "    runner)",
            "  (defproc build-runner",
            "    ()",
            "    -> ProcRef[WorkflowInput -> WorkflowOutput]",
            "    :effects ()",
            "    :lowering inline",
            "    (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput",
            "                :captures ()",
            "                (record WorkflowOutput :report item.report))",
            "      (id-runner (proc-ref run-local))))",
            ")",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "let_proc_scope_escape")


def test_compile_stage3_rejects_non_literal_proc_ref_arguments(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(PROC_REF_LITERAL_REQUIRED_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "proc_ref_literal_required")


def test_compile_stage3_rejects_proc_ref_signature_mismatches(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(PROC_REF_SIGNATURE_INVALID_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "proc_ref_signature_invalid")


def test_compile_stage3_rejects_bind_proc_unknown_keywords(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "proc_ref_bind_proc_unknown_keyword.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc helper",
            "    ((fixed String)",
            "     (input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (record WorkflowOutput",
            "      :report input.report))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (let* ((runner (bind-proc (proc-ref helper)",
            "                      :missing input.report)))",
            "      (runner input))))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "proc_ref_binding_unknown")


def test_compile_stage3_rejects_bind_proc_duplicate_keywords(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "proc_ref_bind_proc_duplicate_keyword.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc helper",
            "    ((fixed String)",
            "     (input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (record WorkflowOutput",
            "      :report input.report))",
                "  (defworkflow entry",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (let* ((runner (bind-proc (proc-ref helper)",
                '                      :fixed "same"',
                '                      :fixed "same")))',
                "      (runner input))))",
            ],
        )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "proc_ref_binding_duplicate")


def test_compile_stage3_rejects_nested_bind_proc_duplicate_keywords(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "proc_ref_bind_proc_nested_duplicate_keyword.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc helper",
            "    ((fixed String)",
            "     (input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (record WorkflowOutput",
            "      :report input.report))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (let* ((runner (bind-proc",
            "                     (bind-proc (proc-ref helper)",
            '                       :fixed "one")',
            '                     :fixed "two")))',
            "      (runner input))))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "proc_ref_binding_duplicate")


def test_compile_stage3_rejects_bind_proc_mistyped_bound_values(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "proc_ref_bind_proc_type_invalid.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defproc helper",
            "    ((fixed String)",
            "     (input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (record WorkflowOutput",
            "      :report input.report))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (let* ((runner (bind-proc (proc-ref helper)",
            "                      :fixed input)))",
            "      (runner input))))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "proc_ref_binding_type_invalid")


def test_compile_stage3_rejects_proc_ref_specialization_cycles(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(PROC_REF_SPECIALIZATION_CYCLE_FIXTURE, tmp_path=tmp_path)

    _assert_proc_ref_cycle_diagnostics_at_authored_call_sites(excinfo)


def test_stage3_effect_inference_rejects_proc_ref_specialization_cycles_before_lowering() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _infer_stage3_proc_ref_effects(PROC_REF_SPECIALIZATION_CYCLE_FIXTURE)

    _assert_proc_ref_cycle_diagnostics_at_authored_call_sites(excinfo)


def test_higher_order_procedure_specializations_reuse_private_workflow_lowering(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "higher_order_private_reuse.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowInput",
            "    (report WorkReport))",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defworkflow echo-helper",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" input.report)',
            "      :returns WorkflowOutput))",
            "  (defproc invoke-runner",
            "    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])",
            "     (input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ((calls-workflow runner))",
            "    :lowering auto",
            "    (call runner",
            "      :input input))",
            "  (defworkflow first",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (invoke-runner echo-helper input))",
            "  (defworkflow second",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (invoke-runner echo-helper input)))",
        ],
    )

    result = _compile_validated(path, tmp_path=tmp_path)
    lowered_names = [workflow.typed_workflow.definition.name for workflow in result.lowered_workflows]
    private_names = [name for name in lowered_names if name.startswith("%higher_order_private_reuse.")]

    assert len(private_names) == 1
    assert "invoke-runner__spec__runner__echo_helper" in private_names[0]
    assert private_names[0] in result.validated_bundles
