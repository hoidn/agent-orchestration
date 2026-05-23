import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _typecheck_procedure_definitions,
    _validate_definition_module,
    _validate_procedure_effects_and_cycles,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, render_diagnostic
from orchestrator.workflow_lisp.effects import CallsWorkflowEffect, UsesCommandEffect, UsesProviderEffect
from orchestrator.workflow_lisp.lowering import _resolve_procedure_lowering
from orchestrator.workflow_lisp.procedures import build_procedure_catalog, elaborate_procedure_definitions
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import (
    ExternalToolBinding,
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
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


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

    _assert_diagnostic_code(excinfo, "proc_private_workflow_boundary_invalid")

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
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            validate_shared=True,
            workspace_root=tmp_path,
        )

    rendered_diagnostics = [render_diagnostic(diagnostic) for diagnostic in excinfo.value.diagnostics]

    assert all("%auto_inline_required_for_input_projection.build-checks.v1" not in rendered for rendered in rendered_diagnostics)
    assert any("procedure call site at" in rendered for rendered in rendered_diagnostics)


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

    _assert_diagnostic_code(excinfo, "proc_private_workflow_boundary_invalid")


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


def test_compile_stage3_supports_forwarded_workflow_ref_procedure_calls(tmp_path: Path) -> None:
    result = _compile_validated(WORKFLOW_REF_FORWARDING_FIXTURE, tmp_path=tmp_path)

    assert "entry" in result.validated_bundles
    assert result.typed_procedures[0].definition.name == "invoke-runner"


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
