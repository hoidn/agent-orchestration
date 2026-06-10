import ast
import importlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _infer_stage3_effect_summaries,
    _typecheck_procedure_definitions,
    _validate_definition_module,
    _validate_procedure_effects_and_cycles,
    compile_stage3_module as _compile_stage3_module,
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
    LetProcBinding,
    LetProcExpr,
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
    WithPhaseExpr,
)
from orchestrator.workflow_lisp.lowering import _resolve_procedure_lowering, lower_workflow_definitions
from orchestrator.workflow_lisp.phase_stdlib import ProduceOneOfProducerSpec
from orchestrator.workflow_lisp.procedures import (
    ProcedureLoweringMode,
    build_procedure_catalog,
    elaborate_procedure_definitions,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
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


def compile_stage3_module(*args, **kwargs):
    kwargs.setdefault("lowering_route", "legacy")
    return _compile_stage3_module(*args, **kwargs)


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
        lowering_route="legacy",
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
        lowering_route="legacy",
        validate_shared=True,
        workspace_root=tmp_path,
    )


def _write_module(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _test_span(path: str) -> SourceSpan:
    start = SourcePosition(path=path, line=1, column=1, offset=0)
    end = SourcePosition(path=path, line=1, column=2, offset=1)
    return SourceSpan(start=start, end=end)


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


def _procedure_specialization_source_path() -> Path:
    path = Path(importlib.import_module("orchestrator.workflow_lisp.procedure_specialization").__file__)
    assert path.is_file()
    return path


def _definition_context(path: Path):
    syntax_module = build_syntax_module(read_sexpr_file(path))
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    return syntax_module, module, type_env


def _typecheck_top_level_names() -> set[str]:
    source_path = Path(importlib.import_module("orchestrator.workflow_lisp.typecheck").__file__)
    return _module_top_level_names(source_path)


def _module_top_level_names(source_path: Path) -> set[str]:
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in module.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    }


def _function_body_mentions_symbol(path: Path, function_name: str, symbol: str) -> bool:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == symbol:
                return True
            if isinstance(child, ast.Attribute) and child.attr == symbol:
                return True
            if isinstance(child, ast.ImportFrom):
                if any(alias.name == symbol or alias.asname == symbol for alias in child.names):
                    return True
    return False


def _imported_symbols_from(source_path: Path, module_name: str) -> set[str]:
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.ImportFrom) or node.module != module_name:
            continue
        for alias in node.names:
            imported.add(alias.asname or alias.name)
    return imported


def test_typecheck_facade_keeps_generated_local_procedure_helpers_after_let_proc_split() -> None:
    package_dir = Path(importlib.import_module("orchestrator.workflow_lisp").__file__).resolve().parent
    typecheck_module = importlib.import_module("orchestrator.workflow_lisp.typecheck")
    dispatch_source = (package_dir / "typecheck_dispatch.py").read_text(encoding="utf-8")
    procedure_source = (package_dir / "procedure_typecheck.py").read_text(encoding="utf-8")
    dispatch_top_level_names = _module_top_level_names(package_dir / "typecheck_dispatch.py")
    procedure_top_level_names = _module_top_level_names(package_dir / "procedure_typecheck.py")

    assert hasattr(typecheck_module, "consume_generated_local_procedures")
    assert hasattr(typecheck_module, "reset_generated_local_procedure_state")
    assert hasattr(typecheck_module, "set_active_workflow_signature")
    assert hasattr(typecheck_module, "clear_active_workflow_signature")
    assert hasattr(typecheck_module, "set_active_reusable_state_producer_context")
    assert hasattr(typecheck_module, "clear_active_reusable_state_producer_context")
    assert (package_dir / "procedure_typecheck.py").is_file()
    assert "_typecheck_let_proc" not in _typecheck_top_level_names()
    assert "typecheck_let_proc_expr(" in procedure_source
    assert "from .typecheck_dispatch import _typecheck_let_proc" not in procedure_source
    assert "return _typecheck_let_proc(" not in procedure_source
    assert {
        "LocalProcRewriteBinding",
        "_rewrite_local_proc_references",
        "_expr_returns_local_proc_value",
        "_replace_eliminated_let_procs",
    } <= procedure_top_level_names
    assert dispatch_top_level_names.isdisjoint(
        {
            "_typecheck_let_proc",
            "LocalProcRewriteBinding",
            "_rewrite_local_proc_references",
            "_expr_returns_local_proc_value",
            "_replace_eliminated_let_procs",
        }
    )
    assert "if isinstance(expr, LetProcExpr):" not in dispatch_source


def test_compiler_procedure_dependency_owner_uses_shared_walk_expr() -> None:
    source_path = Path(importlib.import_module("orchestrator.workflow_lisp.compiler").__file__)

    assert _function_body_mentions_symbol(source_path, "_procedure_dependencies", "walk_expr")


def test_proc_ref_specialization_owner_uses_shared_iter_child_exprs() -> None:
    source_path = _procedure_specialization_source_path()

    assert _function_body_mentions_symbol(
        source_path,
        "discover_proc_ref_specializations",
        "iter_child_exprs",
    )


def test_procedure_dependency_walker_descends_through_let_proc_expr() -> None:
    dependency_walker = getattr(_compiler_module(), "_procedure_dependencies", None)
    assert callable(dependency_walker), "_procedure_dependencies is missing"

    span = _test_span("nested_procedure_dependency.orc")
    expr = LetProcExpr(
        binding=LetProcBinding(
            local_name="local-helper",
            params=(),
            return_type_name="WorkflowOutput",
            capture_names=(),
            local_body=LiteralExpr(
                value="noop",
                literal_kind="string",
                span=span,
                form_path=("workflow-lisp", "defworkflow", "entry"),
            ),
            span=span,
            form_path=("workflow-lisp", "defworkflow", "entry"),
        ),
        body=ProcedureCallExpr(
            callee_name="run-helper",
            args=(),
            span=span,
            form_path=("workflow-lisp", "defworkflow", "entry"),
        ),
        span=span,
        form_path=("workflow-lisp", "defworkflow", "entry"),
    )

    assert dependency_walker(expr) == {"run-helper"}


def test_elaborate_defproc_parses_structured_where_metadata(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "parametric_proc_metadata.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defproc carry",
            "    :forall (T U)",
            "    ((current T)",
            "     (next U))",
            "    :where ((T is-record)",
            "            (U has-field report WorkReport))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    current))",
        ],
    )

    syntax_module = build_syntax_module(read_sexpr_file(path))
    procedures = elaborate_procedure_definitions(syntax_module)

    assert len(procedures) == 1
    assert [param.name for param in procedures[0].type_params] == ["T", "U"]
    assert [clause.subject_name for clause in procedures[0].where_clauses] == ["T", "U"]
    assert [clause.constraint_name for clause in procedures[0].where_clauses] == ["is-record", "has-field"]
    assert procedures[0].where_clauses[0].variant_name is None
    assert procedures[0].where_clauses[0].field_name is None
    assert procedures[0].where_clauses[0].field_requirements == ()
    assert procedures[0].where_clauses[1].field_name == "report"
    assert procedures[0].where_clauses[1].field_type_name == "WorkReport"
    assert procedures[0].where_clauses[1].variant_name is None
    assert procedures[0].where_clauses[1].field_requirements == ()


def test_elaborate_defproc_rejects_duplicate_type_params(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "parametric_proc_duplicate_type_params.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defproc carry",
            "    :forall (T T)",
            "    ((value T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    value))",
        ],
    )

    syntax_module = build_syntax_module(read_sexpr_file(path))
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_procedure_definitions(syntax_module)

    _assert_diagnostic_code(excinfo, "procedure_type_param_duplicate")


def test_elaborate_defproc_rejects_invalid_parametric_clause_order(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "parametric_proc_clause_order.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defproc carry",
            "    ((value T))",
            "    :forall (T)",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    value))",
        ],
    )

    syntax_module = build_syntax_module(read_sexpr_file(path))
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_procedure_definitions(syntax_module)

    _assert_diagnostic_code(excinfo, "procedure_type_param_clause_invalid")


def test_elaborate_defproc_parses_has_union_variant_field_requirements(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "parametric_proc_variant_where.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defproc carry",
            "    :forall (ResultT)",
            "    ((value ResultT))",
            "    :where ((ResultT has-union-variant APPROVED (report WorkReport) (status String)))",
            "    -> ResultT",
            "    :effects ()",
            "    :lowering inline",
            "    value))",
        ],
    )

    syntax_module = build_syntax_module(read_sexpr_file(path))
    procedures = elaborate_procedure_definitions(syntax_module)

    assert len(procedures) == 1
    assert len(procedures[0].where_clauses) == 1
    clause = procedures[0].where_clauses[0]
    assert clause.subject_name == "ResultT"
    assert clause.constraint_name == "has-union-variant"
    assert clause.variant_name == "APPROVED"
    assert clause.field_name is None
    assert clause.field_type_name is None
    assert [field.field_name for field in clause.field_requirements] == ["report", "status"]
    assert [field.field_type_name for field in clause.field_requirements] == ["WorkReport", "String"]


def test_elaborate_defproc_rejects_unknown_where_subject_type_param(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "parametric_proc_unknown_where_subject.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defproc carry",
            "    :forall (T)",
            "    ((value T))",
            "    :where ((U is-record))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    value))",
        ],
    )

    syntax_module = build_syntax_module(read_sexpr_file(path))
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_procedure_definitions(syntax_module)

    _assert_diagnostic_code(excinfo, "procedure_type_param_unknown")


def test_elaborate_defproc_rejects_malformed_where_variant_field_requirements(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "parametric_proc_malformed_where_variant_field.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defproc carry",
            "    :forall (T)",
            "    ((value T))",
            "    :where ((T has-union-variant APPROVED (report WorkReport extra)))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    value))",
        ],
    )

    syntax_module = build_syntax_module(read_sexpr_file(path))
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_procedure_definitions(syntax_module)

    _assert_diagnostic_code(excinfo, "procedure_where_field_requirement_invalid")


def test_build_procedure_catalog_resolves_type_params_inside_nested_proc_ref_and_workflow_ref_types(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.type_env import ProcRefTypeRef, TypeParamRef, WorkflowRefTypeRef

    path = _write_module(
        tmp_path / "parametric_proc_nested_type_params.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defrecord WorkflowOutput",
            "    (report String))",
            "  (defproc invoke-runner",
            "    :forall (T)",
            "    ((runner ProcRef[(WorkflowRef[T -> WorkflowOutput]) -> WorkflowOutput])",
            "     (target WorkflowRef[T -> WorkflowOutput]))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (runner target)))",
        ],
    )

    syntax_module, module, type_env = _definition_context(path)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    signature = catalog.signatures_by_name["invoke-runner"]

    assert [param.name for param in procedure_defs[0].type_params] == ["T"]
    assert [param.name for param in signature.type_params] == ["T"]
    assert isinstance(signature.params[0][1], ProcRefTypeRef)
    assert isinstance(signature.params[0][1].param_type_refs[0], WorkflowRefTypeRef)
    assert isinstance(signature.params[0][1].param_type_refs[0].param_type_refs[0], TypeParamRef)
    assert isinstance(signature.params[1][1], WorkflowRefTypeRef)
    assert isinstance(signature.params[1][1].param_type_refs[0], TypeParamRef)


def test_build_procedure_catalog_resolves_type_param_refs(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.type_env import TypeParamRef

    path = _write_module(
        tmp_path / "parametric_proc_type_param_refs.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defproc identity",
            "    :forall (T)",
            "    ((value T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    value))",
        ],
    )

    syntax_module, module, type_env = _definition_context(path)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    signature = catalog.signatures_by_name["identity"]

    assert isinstance(signature.params[0][1], TypeParamRef)
    assert isinstance(signature.return_type_ref, TypeParamRef)
    assert signature.params[0][1].name == "T"
    assert signature.return_type_ref.name == "T"


def test_type_param_substitution_rewrites_nested_proc_ref_and_workflow_ref_types(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.type_env import (
        ProcRefTypeRef,
        RecordTypeRef,
        WorkflowRefTypeRef,
        ensure_no_type_params,
        substitute_type_params,
    )

    path = _write_module(
        tmp_path / "parametric_proc_substitution.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defrecord WorkflowOutput",
            "    (report String))",
            "  (defproc invoke-runner",
            "    :forall (T)",
            "    ((runner ProcRef[(WorkflowRef[T -> WorkflowOutput]) -> T]))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    (runner entry))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (record WorkflowOutput :report input.report)))",
        ],
    )

    syntax_module, module, type_env = _definition_context(path)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    signature = catalog.signatures_by_name["invoke-runner"]
    concrete_input = type_env.resolve_type(
        "WorkflowInput",
        span=procedure_defs[0].span,
        form_path=procedure_defs[0].form_path,
    )

    substituted = substitute_type_params(signature.params[0][1], {"T": concrete_input})
    ensure_no_type_params(
        substituted,
        span=procedure_defs[0].span,
        form_path=procedure_defs[0].form_path,
    )

    assert isinstance(substituted, ProcRefTypeRef)
    assert isinstance(substituted.param_type_refs[0], WorkflowRefTypeRef)
    assert isinstance(substituted.param_type_refs[0].param_type_refs[0], RecordTypeRef)
    assert substituted.param_type_refs[0].param_type_refs[0].name == "WorkflowInput"
    assert isinstance(substituted.return_type_ref, RecordTypeRef)
    assert substituted.return_type_ref.name == "WorkflowInput"


def test_nonempty_where_metadata_is_preserved_when_header_validation_succeeds(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "parametric_proc_where_metadata.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defproc carry",
            "    :forall (T)",
            "    ((value T))",
            "    :where ((T has-field report WorkReport))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    value))",
        ],
    )

    syntax_module, module, type_env = _definition_context(path)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    signature = catalog.signatures_by_name["carry"]

    assert len(signature.where_clauses) == 1
    assert signature.where_clauses[0].subject_name == "T"
    assert signature.where_clauses[0].constraint_name == "has-field"
    assert signature.where_clauses[0].field_name == "report"
    assert signature.where_clauses[0].field_type_name == "WorkReport"


def test_compile_stage3_specializes_generic_defproc_before_lowering(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_specialization.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defproc apply-runner",
            "    :forall (T)",
            "    ((runner ProcRef[T -> T])",
            "     (value T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    (runner value))",
            "  (defproc echo-input",
            "    ((value WorkflowInput))",
            "    -> WorkflowInput",
            "    :effects ()",
            "    :lowering inline",
            "    (record WorkflowInput",
            "      :report value.report))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowInput",
            "    (apply-runner (proc-ref echo-input) input)))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    specialized = [
        procedure
        for procedure in result.typed_procedures
        if getattr(procedure.specialization, "type_bindings", {})
    ]

    assert len(specialized) == 1
    assert specialized[0].definition.name.startswith("%proc-ref-call.%parametric_call.apply_runner.")
    assert set(specialized[0].specialization.proc_ref_bindings) == {"runner"}
    assert specialized[0].signature.type_params == ()
    assert specialized[0].signature.return_type_ref.name == "WorkflowInput"


def test_compile_stage3_reuses_equivalent_parametric_specializations(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_specialization_reuse.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defproc apply-runner",
            "    :forall (T)",
            "    ((runner ProcRef[T -> T])",
            "     (value T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    (runner value))",
            "  (defproc echo-input",
            "    ((value WorkflowInput))",
            "    -> WorkflowInput",
            "    :effects ()",
            "    :lowering inline",
            "    (record WorkflowInput",
            "      :report value.report))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowInput",
            "    (let* ((first (apply-runner (proc-ref echo-input) input))",
            "           (second (apply-runner (proc-ref echo-input) first)))",
            "      second)))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    specialized = [
        procedure
        for procedure in result.typed_procedures
        if getattr(procedure.specialization, "type_bindings", {})
        and procedure.specialization.base_name == "apply-runner"
    ]

    assert len(specialized) == 1


def test_compile_stage3_rejects_ambiguous_type_argument_bindings(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_binding_ambiguous.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord LeftValue",
            "    (report String))",
            "  (defrecord RightValue",
            "    (report String))",
            "  (defproc choose-left",
            "    :forall (T)",
            "    ((left T)",
            "     (right T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    left)",
            "  (defworkflow entry",
            "    ((left LeftValue)",
            "     (right RightValue))",
            "    -> LeftValue",
            "    (choose-left left right)))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_type_binding_ambiguous")


def test_compile_stage3_rejects_unresolved_type_parameters(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_binding_unresolved.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defproc identity",
            "    :forall (T U)",
            "    ((value T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    value)",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowInput",
            "    (identity input)))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_type_binding_unresolved")


def test_compile_stage3_accepts_is_record_and_has_field_constraints(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_where_record_field.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defproc apply-runner",
            "    :forall (T)",
            "    ((runner ProcRef[T -> T])",
            "     (value T))",
            "    :where ((T is-record)",
            "            (T has-field report String))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    (runner value))",
            "  (defproc echo-input",
            "    ((value WorkflowInput))",
            "    -> WorkflowInput",
            "    :effects ()",
            "    :lowering inline",
            "    (record WorkflowInput",
            "      :report value.report))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowInput",
            "    (apply-runner (proc-ref echo-input) input)))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    specialized = next(
        procedure
        for procedure in result.typed_procedures
        if getattr(procedure.specialization, "type_bindings", {})
        and procedure.specialization.base_name == "apply-runner"
    )

    assert specialized.signature.type_params == ()
    assert specialized.signature.return_type_ref.name == "WorkflowInput"


def test_compile_stage3_accepts_has_union_variant_with_field_requirements(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_where_union_variant.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defunion ReviewResult",
            "    (APPROVED",
            "      (report String)",
            "      (status String))",
            "    (BLOCKED",
            "      (report String)))",
            "  (defrecord WorkflowOutput",
            "    (status String))",
            "  (defproc check-approved",
            "    :forall (T)",
            "    ((runner ProcRef[String -> WorkflowOutput])",
            "     (value T)",
            "     (label String))",
            "    :where ((T has-union-variant APPROVED (report String) (status String)))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (runner label))",
            "  (defproc emit-output",
            "    ((label String))",
            "    -> WorkflowOutput",
            "    :effects ((uses-command run_checks))",
            "    :lowering inline",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" label)',
            "      :returns WorkflowOutput))",
            "  (defworkflow entry",
            "    ((input String))",
            "    -> WorkflowOutput",
            "    (check-approved",
            '      (proc-ref emit-output)',
            "      (variant ReviewResult APPROVED",
            '        :report input',
            '        :status "done")',
            '      "approved")))',
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    specialized = next(
        procedure
        for procedure in result.typed_procedures
        if getattr(procedure.specialization, "type_bindings", {})
        and procedure.specialization.base_name == "check-approved"
    )

    assert specialized.signature.type_params == ()
    assert specialized.signature.return_type_ref.name == "WorkflowOutput"


def test_compile_stage3_rejects_unknown_structural_constraint(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_where_unknown_constraint.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defproc identity",
            "    :forall (T)",
            "    ((value T))",
            "    :where ((T unknown-constraint report String))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    value)",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowInput",
            "    (identity input)))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_constraint_unknown")


def test_compile_stage3_rejects_unsatisfied_has_field_constraint(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_where_missing_field.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (status String))",
            "  (defproc identity",
            "    :forall (T)",
            "    ((value T))",
            "    :where ((T has-field report String))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    value)",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowInput",
            "    (identity input)))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_constraint_unsatisfied")
    assert "has-field" in excinfo.value.diagnostics[0].message


def test_compile_stage3_rejects_unsatisfied_has_union_variant_constraint(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_where_missing_variant.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defunion ReviewResult",
            "    (BLOCKED",
            "      (report String)))",
            "  (defrecord ResultRecord",
            "    (status String))",
            "  (defproc check-approved",
            "    :forall (T)",
            "    ((value T))",
            "    :where ((T has-union-variant APPROVED))",
            "    -> String",
            "    :effects ()",
            "    :lowering inline",
            '    "ok")',
            "  (defworkflow entry",
            "    ((input String))",
            "    -> ResultRecord",
            "    (record ResultRecord",
            "      :status (check-approved",
            "        (variant ReviewResult BLOCKED",
            "          :report input)))))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_constraint_unsatisfied")
    assert "has-union-variant" in excinfo.value.diagnostics[0].message


def test_compile_stage3_rejects_unsatisfied_shared_union_field_constraint(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_where_missing_shared_union_field.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defunion ReviewResult",
            "    (APPROVED",
            "      (report String))",
            "    (BLOCKED",
            "      (progress String)))",
            "  (defrecord ResultRecord",
            "    (status String))",
            "  (defproc check-shared-report",
            "    :forall (T)",
            "    ((value T))",
            "    :where ((T has-shared-union-field report String))",
            "    -> String",
            "    :effects ()",
            "    :lowering inline",
            '    "ok")',
            "  (defworkflow entry",
            "    ((input String))",
            "    -> ResultRecord",
            "    (record ResultRecord",
            "      :status (check-shared-report",
            "        (variant ReviewResult APPROVED",
            "          :report input)))))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_constraint_unsatisfied")
    assert "has-shared-union-field" in excinfo.value.diagnostics[0].message


def test_compile_stage3_accepts_generic_shared_union_field_projection(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_shared_union_projection.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord WorkflowOutput",
            "    (report WorkReport))",
            "  (defunion ReviewState",
            "    (APPROVED",
            "      (shared_report WorkReport))",
            "    (BLOCKED",
            "      (shared_report WorkReport)",
            "      (blocker_class String)))",
            "  (defproc extract-report",
            "    :forall (T)",
            "    ((value T))",
            "    :where ((T has-shared-union-field shared_report WorkReport))",
            "    -> WorkflowOutput",
            "    :effects ((uses-command run_checks))",
            "    :lowering inline",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" value.shared_report)',
            "      :returns WorkflowOutput))",
            "  (defworkflow entry",
            "    ((input WorkReport))",
            "    -> WorkflowOutput",
            "    (extract-report",
            "      (variant ReviewState APPROVED",
            "        :shared_report input))))",
        ],
    )

    result = _compile(path, tmp_path=tmp_path)
    specialized = next(
        procedure
        for procedure in result.typed_procedures
        if getattr(procedure.specialization, "type_bindings", {})
        and procedure.specialization.base_name == "extract-report"
    )

    assert specialized.signature.type_params == ()
    assert specialized.signature.return_type_ref.name == "WorkflowOutput"


def test_compile_stage3_validates_generic_where_workflow_bundle(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_validated_bundle.orc",
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
            "  (defproc run-checks",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ((uses-command run_checks))",
            "    :lowering inline",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" input.report)',
            "      :returns WorkflowOutput))",
            "  (defproc apply-checker",
            "    :forall (T)",
            "    ((runner ProcRef[T -> WorkflowOutput])",
            "     (value T))",
            "    :where ((T is-record)",
            "            (T has-field report WorkReport))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (runner value))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (apply-checker (proc-ref run-checks) input)))",
        ],
    )

    result = _compile_validated(path, tmp_path=tmp_path)
    specialized = next(
        procedure
        for procedure in result.typed_procedures
        if getattr(procedure.specialization, "type_bindings", {})
        and procedure.specialization.base_name == "apply-checker"
    )

    assert "entry" in result.validated_bundles
    assert specialized.signature.type_params == ()
    assert all(type(param_type).__name__ != "TypeParamRef" for _, param_type in specialized.signature.params)
    assert type(specialized.signature.return_type_ref).__name__ != "TypeParamRef"


def test_compile_stage3_preserves_effect_visibility_for_constrained_generic_procref_fixture(
    tmp_path: Path,
) -> None:
    path = _write_module(
        tmp_path / "generic_proc_effect_visibility.orc",
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
            "  (defproc run-checks",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    :effects ((uses-command run_checks))",
            "    :lowering inline",
            "    (command-result run_checks",
            '      :argv ("python" "scripts/run_checks.py" input.report)',
            "      :returns WorkflowOutput))",
            "  (defproc apply-checker",
            "    :forall (T)",
            "    ((runner ProcRef[T -> WorkflowOutput])",
            "     (value T))",
            "    :where ((T is-record)",
            "            (T has-field report WorkReport))",
            "    -> WorkflowOutput",
            "    :effects ()",
            "    :lowering inline",
            "    (runner value))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowOutput",
            "    (apply-checker (proc-ref run-checks) input)))",
        ],
    )

    result = _compile_validated(path, tmp_path=tmp_path)
    proc_ref_specialized = next(
        procedure
        for procedure in result.typed_procedures
        if getattr(procedure.specialization, "proc_ref_bindings", {})
        and getattr(procedure.specialization, "base_name", "") == "apply-checker"
    )

    expected_effect = UsesCommandEffect(subject=("run_checks",))

    assert expected_effect in proc_ref_specialized.transitive_effect_summary.transitive_effects


def test_compile_stage3_rejects_parametric_specialization_cycles(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_specialization_cycle.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defproc loop",
            "    :forall (T)",
            "    ((value T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    (loop value))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowInput",
            "    (loop input)))",
        ],
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_specialization_cycle")


def test_compile_stage3_supports_type_params_nested_inside_proc_ref_signatures(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_nested_proc_ref.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defproc apply-runner",
            "    :forall (T)",
            "    ((runner ProcRef[T -> T])",
            "     (value T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    (runner value))",
            "  (defproc echo-input",
            "    ((value WorkflowInput))",
            "    -> WorkflowInput",
            "    :effects ()",
            "    :lowering inline",
            "    (record WorkflowInput",
            "      :report value.report))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowInput",
            "    (apply-runner (proc-ref echo-input) input)))",
        ],
    )

    result = _compile_validated(path, tmp_path=tmp_path)
    specialized = next(
        procedure
        for procedure in result.typed_procedures
        if getattr(procedure.specialization, "type_bindings", {})
        and procedure.specialization.base_name == "apply-runner"
    )

    assert specialized.signature.return_type_ref.name == "WorkflowInput"
    assert "entry" in result.validated_bundles


def test_compile_stage3_specializes_nested_generic_defproc_calls_transitively(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "generic_proc_nested_specialization.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defrecord WorkflowInput",
            "    (report String))",
            "  (defproc invoke-runner",
            "    :forall (T)",
            "    ((runner ProcRef[T -> T])",
            "     (value T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    (runner value))",
            "  (defproc wrap",
            "    :forall (T)",
            "    ((runner ProcRef[T -> T])",
            "     (value T))",
            "    -> T",
            "    :effects ()",
            "    :lowering inline",
            "    (invoke-runner runner value))",
            "  (defproc echo-input",
            "    ((value WorkflowInput))",
            "    -> WorkflowInput",
            "    :effects ()",
            "    :lowering inline",
            "    (record WorkflowInput",
            "      :report value.report))",
            "  (defworkflow entry",
            "    ((input WorkflowInput))",
            "    -> WorkflowInput",
            "    (wrap (proc-ref echo-input) input)))",
        ],
    )

    result = _compile_validated(path, tmp_path=tmp_path)
    specialized = {
        procedure.specialization.base_name: procedure
        for procedure in result.typed_procedures
        if getattr(procedure.specialization, "type_bindings", {})
    }

    assert set(specialized) == {"invoke-runner", "wrap"}
    assert specialized["wrap"].typed_body.expr.callee_name == specialized["invoke-runner"].definition.name
    assert specialized["invoke-runner"].signature.return_type_ref.name == "WorkflowInput"
    assert specialized["wrap"].signature.return_type_ref.name == "WorkflowInput"


def test_compiler_owner_split_stops_importing_procedure_specialization_from_lowering() -> None:
    compiler_path = Path(_compiler_module().__file__)

    assert "from .lowering import _specialize_typed_procedure" not in compiler_path.read_text(
        encoding="utf-8"
    )


def test_specialization_owner_split_stops_importing_private_workflow_eligibility_from_core() -> None:
    path = _procedure_specialization_source_path()
    imported_from_core = _imported_symbols_from(path, "lowering.core")

    assert "_procedure_private_boundary_valid" not in imported_from_core
    assert "_procedure_private_body_valid" not in imported_from_core


def test_specialization_owner_split_stops_importing_value_helpers_from_core() -> None:
    source_path = _procedure_specialization_source_path()
    imported_from_core = _imported_symbols_from(source_path, "lowering.core")

    assert imported_from_core.isdisjoint(
        {
            "_build_output_step_local_value",
            "_flatten_boundary_leaf_paths",
            "_flatten_inline_output_refs",
            "_record_expr_value_at_path",
            "_render_existing_output_ref",
            "_normalize_union_field_path",
            "_union_variant_expr_value_at_path",
        }
    )

    imported_from_values = _imported_symbols_from(source_path, "lowering.values")
    assert {
        "_build_output_step_local_value",
        "_flatten_boundary_leaf_paths",
        "_flatten_inline_output_refs",
        "_record_expr_value_at_path",
        "_render_existing_output_ref",
        "_normalize_union_field_path",
        "_union_variant_expr_value_at_path",
    } <= imported_from_values

    control_owner_path = source_path.parent / "lowering" / "control.py"
    if control_owner_path.is_file():
        assert imported_from_core.isdisjoint(
            {
                "_binding_terminal_for_match_subject",
                "_is_inline_let_binding_expr",
                "_binding_terminal_for_inline_match",
                "_match_arm_local_values",
            }
        )
        imported_from_control = _imported_symbols_from(source_path, "lowering.control")
        assert {
            "_binding_terminal_for_match_subject",
            "_is_inline_let_binding_expr",
            "_binding_terminal_for_inline_match",
            "_match_arm_local_values",
        } <= imported_from_control


def test_specialization_workflow_call_imports_managed_write_root_helper() -> None:
    source_path = _procedure_specialization_source_path()
    imported_from_core = _imported_symbols_from(source_path, "lowering.core")

    assert "_managed_write_root_binding_step" not in imported_from_core

    imported_from_workflow_calls = _imported_symbols_from(source_path, "lowering.workflow_calls")
    assert "_managed_write_root_binding_step" in imported_from_workflow_calls


def test_compiler_keeps_typecheck_procedure_definitions_compat_entrypoint() -> None:
    compiler_module = _compiler_module()

    assert callable(_typecheck_procedure_definitions)
    assert compiler_module._typecheck_procedure_definitions is _typecheck_procedure_definitions


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
            "  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult ReviewReportPath review-revise-loop))",
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
            "      :prompt prompts.review",
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
            "      :prompt prompts.fix",
            "      :inputs (completed.plan_path inputs.fix_prompt findings.items_path)",
            "      :returns CompletedSurface))",
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
            "                 :review (proc-ref review-once)",
            "                 :fix (proc-ref apply-fix)",
            "                 :max 3)))",
            "        (match review",
            "          ((APPROVED approved)",
            "           (record ReviewSurfaceResult",
            "             :report_path approved.review_report))",
                "          ((BLOCKED blocked)",
                "           (record ReviewSurfaceResult",
                "             :report_path blocked.review_report))",
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
            "  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult ReviewReportPath review-revise-loop))",
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
            "      :prompt prompts.review",
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
            "      :prompt prompts.fix",
            "      :inputs (completed.plan_path inputs.fix_prompt findings.items_path)",
            "      :returns CompletedSurface))",
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
            "                 :review (proc-ref review-once)",
            "                 :fix (proc-ref apply-fix)",
            "                 :max 3)))",
            "        (match review",
            "          ((APPROVED approved)",
            "           (record ReviewSurfaceResult",
            "             :report_path approved.review_report))",
                "          ((BLOCKED blocked)",
                "           (record ReviewSurfaceResult",
                "             :report_path blocked.review_report))",
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
    lowering_module = importlib.import_module("orchestrator.workflow_lisp.lowering.procedures")
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


def test_compile_stage3_imported_generic_loop_state_seed_specializes_completed_field(
    tmp_path: Path,
) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    source_root = tmp_path / "loop_state_seed"
    _write_module(
        source_root / "stdlib" / "types.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule stdlib/types)",
            "  (export ReviewReportPath ReviewFindings)",
            "  (defpath ReviewReportPath",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ReviewFindings",
            "    (items_path ReviewReportPath))",
            ")",
        ],
    )
    _write_module(
        source_root / "stdlib" / "loop_state.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule stdlib/loop_state)",
            "  (import stdlib/types :only (ReviewFindings ReviewReportPath))",
            "  (export seed-completed)",
            "  (defproc seed-completed",
            "    :forall (CompletedT)",
            "    ((completed CompletedT)",
            "     (findings ReviewFindings)",
            "     (report_path ReviewReportPath))",
            "    :where ((CompletedT is-record))",
            "    -> CompletedT",
            "    :effects ()",
            "    :lowering inline",
            "    (let* ((state",
            "             (loop-state",
            "               (completed CompletedT completed)",
            "               (findings ReviewFindings findings)",
            "               (report_path ReviewReportPath report_path))))",
            "      state.completed)))",
        ],
    )
    entry_path = _write_module(
        source_root / "entry.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule entry)",
            "  (import stdlib/types :only (ReviewFindings ReviewReportPath))",
            "  (import stdlib/loop_state :as loop-state :only (seed-completed))",
            "  (export orchestrate)",
            "  (defrecord CompletedSurface",
            "    (report ReviewReportPath))",
            "  (defworkflow orchestrate",
            "    ((completed CompletedSurface)",
            "     (findings ReviewFindings)",
            "     (report_path ReviewReportPath))",
            "    -> CompletedSurface",
            "    (loop-state.seed-completed completed findings report_path)))",
        ],
    )

    result = compile_fn(
        entry_path,
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        lowering_route="legacy",
        validate_shared=True,
        workspace_root=tmp_path,
    )

    specialized = next(
        procedure
        for procedure in result.entry_result.typed_procedures
        if getattr(procedure.specialization, "base_name", "") == "stdlib/loop_state::seed-completed"
    )

    assert all(type(param_type).__name__ != "TypeParamRef" for _, param_type in specialized.signature.params)
    assert type(specialized.signature.return_type_ref).__name__ != "TypeParamRef"
    bundle = next(iter(result.validated_bundles_by_name.values()))
    serialized_payloads = (
        json.dumps(workflow_executable_ir_to_json(bundle.ir), sort_keys=True),
        json.dumps(workflow_semantic_ir_to_json(bundle.semantic_ir), sort_keys=True),
    )
    for payload in serialized_payloads:
        assert "TypeParamRef" not in payload
        assert "%loop-state." not in payload


def test_compile_stage3_imported_generic_loop_state_update_reuses_specialized_carrier(
    tmp_path: Path,
) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    source_root = tmp_path / "loop_state_update"
    _write_module(
        source_root / "stdlib" / "types.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule stdlib/types)",
            "  (export ReviewReportPath ReviewFindings)",
            "  (defpath ReviewReportPath",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ReviewFindings",
            "    (items_path ReviewReportPath))",
            ")",
        ],
    )
    _write_module(
        source_root / "stdlib" / "loop_state.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule stdlib/loop_state)",
            "  (import stdlib/types :only (ReviewFindings ReviewReportPath))",
            "  (export update-completed)",
            "  (defproc update-completed",
            "    :forall (CompletedT)",
            "    ((completed CompletedT)",
            "     (replacement CompletedT)",
            "     (findings ReviewFindings)",
            "     (report_path ReviewReportPath))",
            "    :where ((CompletedT is-record))",
            "    -> CompletedT",
            "    :effects ()",
            "    :lowering inline",
            "    (let* ((state",
            "             (loop-state",
            "               (completed CompletedT completed)",
            "               (findings ReviewFindings findings)",
            "               (report_path ReviewReportPath report_path)))",
            "           (updated",
            "             (loop-state :like state :completed replacement)))",
            "      updated.completed)))",
        ],
    )
    entry_path = _write_module(
        source_root / "entry.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule entry)",
            "  (import stdlib/types :only (ReviewFindings ReviewReportPath))",
            "  (import stdlib/loop_state :as loop-state :only (update-completed))",
            "  (export orchestrate)",
            "  (defrecord CompletedSurface",
            "    (report ReviewReportPath))",
            "  (defworkflow orchestrate",
            "    ((completed CompletedSurface)",
            "     (replacement CompletedSurface)",
            "     (findings ReviewFindings)",
            "     (report_path ReviewReportPath))",
            "    -> CompletedSurface",
            "    (loop-state.update-completed completed replacement findings report_path)))",
        ],
    )

    result = compile_fn(
        entry_path,
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        lowering_route="legacy",
        validate_shared=True,
        workspace_root=tmp_path,
    )

    specialized = next(
        procedure
        for procedure in result.entry_result.typed_procedures
        if getattr(procedure.specialization, "base_name", "") == "stdlib/loop_state::update-completed"
    )

    assert all(type(param_type).__name__ != "TypeParamRef" for _, param_type in specialized.signature.params)
    assert type(specialized.signature.return_type_ref).__name__ != "TypeParamRef"
    bundle = next(iter(result.validated_bundles_by_name.values()))
    serialized_payloads = (
        json.dumps(workflow_executable_ir_to_json(bundle.ir), sort_keys=True),
        json.dumps(workflow_semantic_ir_to_json(bundle.semantic_ir), sort_keys=True),
    )
    for payload in serialized_payloads:
        assert "TypeParamRef" not in payload
        assert "%loop-state." not in payload


def test_compile_stage3_imported_generic_loop_state_consumer_specializes_without_runtime_leaks(
    tmp_path: Path,
) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    source_root = tmp_path / "imported_consumer"
    _write_module(
        source_root / "stdlib" / "types.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule stdlib/types)",
            "  (export WorkReport ReviewReportPath ReviewFindingsJsonPath ReviewFindings BlockerClass ReviewDecision ReviewReportResult ReviewLoopResult)",
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defpath ReviewReportPath",
            "    :kind relpath",
            '    :under "artifacts/review"',
            "    :must-exist true)",
            "  (defpath ReviewFindingsJsonPath",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord ReviewFindings",
            "    (schema_version String)",
            "    (items_path ReviewFindingsJsonPath))",
            "  (defenum BlockerClass",
            "    missing_resource",
            "    user_decision_required)",
            "  (defrecord ReviewReportResult",
            "    (report_path ReviewReportPath))",
            "  (defunion ReviewDecision",
            "    (APPROVE",
                "      (review_report ReviewReportPath)",
                "      (findings ReviewFindings))",
            "    (REVISE",
            "      (review_report ReviewReportPath)",
            "      (findings ReviewFindings))",
            "    (BLOCKED",
            "      (review_report ReviewReportPath)",
            "      (blocker_class BlockerClass)",
            "      (findings ReviewFindings)))",
            "  (defunion ReviewLoopResult",
            "    (APPROVED",
                "      (review_report ReviewReportPath)",
                "      (findings ReviewFindings))",
            "    (BLOCKED",
            "      (review_report ReviewReportPath)",
            "      (blocker_class BlockerClass)",
            "      (findings ReviewFindings))",
            "    (EXHAUSTED",
            "      (last_review_report ReviewReportPath)",
            "      (findings ReviewFindings)",
            "      (reason String))))",
        ],
    )
    _write_module(
        source_root / "stdlib" / "review_loop_consumer.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule stdlib/review_loop_consumer)",
            "  (import stdlib/types :only (BlockerClass ReviewDecision ReviewReportPath ReviewFindings ReviewLoopResult))",
            "  (export consume-review-loop)",
            "  (defproc consume-review-loop",
            "    :forall (CompletedT InputsT)",
            "    ((completed CompletedT)",
            "     (inputs InputsT)",
            "     (initial_review_report ReviewReportPath)",
            "     (initial_findings ReviewFindings)",
            "     (review ProcRef[(CompletedT InputsT) -> ReviewDecision])",
            "     (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])",
            "     (max_iterations Int))",
                "    :where ((CompletedT is-record)",
                "            (InputsT is-record))",
                "    -> ReviewLoopResult",
                "    :effects ()",
                "    :lowering inline",
                "    (loop/recur",
                "      :max max_iterations",
            "      :state (loop-state",
            "               (completed CompletedT completed)",
            "               (inputs InputsT inputs)",
            "               (last_review_report ReviewReportPath initial_review_report)",
            "               (latest_findings ReviewFindings initial_findings))",
            "      :on-exhausted (variant ReviewLoopResult EXHAUSTED",
            '                      :reason "max_iterations_reached"',
            "                      :last_review_report state.last_review_report",
            "                      :findings (record ReviewFindings",
            "                                  :schema_version state.latest_findings.schema_version",
            "                                  :items_path state.latest_findings.items_path))",
            "      (fn (state)",
                "        (let* ((review-decision",
                "                 (review state.completed state.inputs)))",
                "          (match review-decision",
                "            ((APPROVE approved)",
                "             (done",
                "               (variant ReviewLoopResult APPROVED",
                "                 :review_report approved.review_report",
                    "                 :findings (record ReviewFindings",
                    "                             :schema_version approved.findings.schema_version",
                    "                             :items_path approved.findings.items_path))))",
                    "            ((REVISE revised)",
                    "             (let* ((fixed-completed",
                    "                      (fix state.completed state.inputs revised.findings)))",
                    "               (continue",
                    "                 (loop-state :like state",
                    "                   :completed fixed-completed",
                    "                   :last_review_report revised.review_report",
                    "                   :latest_findings revised.findings))))",
                    "            ((BLOCKED blocked)",
                "             (done",
                "               (variant ReviewLoopResult BLOCKED",
                "                 :review_report blocked.review_report",
                "                 :blocker_class blocked.blocker_class",
                "                 :findings (record ReviewFindings",
                "                             :schema_version blocked.findings.schema_version",
                "                             :items_path blocked.findings.items_path))))",
                    "            ))))))",
            ],
        )
    entry_path = _write_module(
        source_root / "entry.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule entry)",
                "  (import stdlib/types :only (BlockerClass WorkReport ReviewReportPath ReviewFindingsJsonPath ReviewFindings ReviewDecision ReviewReportResult ReviewLoopResult))",
            "  (import stdlib/review_loop_consumer :as review-loop :only (consume-review-loop))",
            "  (export orchestrate)",
            "  (defrecord CompletedSurface",
            "    (execution_report_path WorkReport))",
            "  (defrecord InputsSurface",
            "    (findings_path ReviewFindingsJsonPath))",
                "  (defproc review-once",
                "    ((completed CompletedSurface)",
                "     (inputs InputsSurface))",
                "    -> ReviewDecision",
                "    :effects ((uses-provider providers.execute))",
                "    :lowering inline",
                "    (let* ((review-report",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (completed.execution_report_path inputs.findings_path)",
                "               :returns ReviewReportResult)))",
                "      (variant ReviewDecision REVISE",
                "        :review_report review-report.report_path",
                "        :findings (record ReviewFindings",
                '                    :schema_version "ReviewFindings.v1"',
                "                    :items_path inputs.findings_path))))",
                "  (defproc fix-completed",
                    "    ((completed CompletedSurface)",
                    "     (inputs InputsSurface)",
                    "     (findings ReviewFindings))",
                    "    -> CompletedSurface",
                    "    :effects ()",
                    "    :lowering inline",
                    "    (let* ((state",
                    "             (loop-state",
                    "               (completed CompletedSurface completed)",
                    "               (inputs InputsSurface inputs)",
                    "               (findings ReviewFindings findings)))",
                    "           (updated",
                    "             (loop-state :like state :completed completed)))",
                    "      updated.completed))",
            "  (defworkflow orchestrate",
            "    ((completed CompletedSurface)",
                "     (inputs InputsSurface)",
                "     (initial_review_report ReviewReportPath))",
                "    -> ReviewLoopResult",
                "    (let* ((max_iterations 4)",
                "           (initial_findings",
                "             (record ReviewFindings",
                '               :schema_version "ReviewFindings.v1"',
                "               :items_path inputs.findings_path)))",
            "      (review-loop.consume-review-loop",
            "        completed",
            "        inputs",
            "        initial_review_report",
            "        initial_findings",
            "        (proc-ref review-once)",
            "        (proc-ref fix-completed)",
            "        max_iterations))))",
        ],
    )

    result = compile_fn(
        entry_path,
        source_roots=(source_root,),
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

    specialized = next(
        procedure
        for procedure in result.entry_result.typed_procedures
        if getattr(procedure.specialization, "base_name", "") == "stdlib/review_loop_consumer::consume-review-loop"
    )

    assert all(type(param_type).__name__ != "TypeParamRef" for _, param_type in specialized.signature.params)
    assert type(specialized.signature.return_type_ref).__name__ != "TypeParamRef"
    assert UsesProviderEffect(subject=("providers", "execute")) in specialized.transitive_effect_summary.transitive_effects
    assert (
        [variant.name for variant in specialized.signature.return_type_ref.definition.variants]
        == ["APPROVED", "BLOCKED", "EXHAUSTED"]
    )

    bundle = next(iter(result.validated_bundles_by_name.values()))
    serialized_payloads = (
        json.dumps(workflow_executable_ir_to_json(bundle.ir), sort_keys=True),
        json.dumps(workflow_semantic_ir_to_json(bundle.semantic_ir), sort_keys=True),
    )
    for payload in serialized_payloads:
        assert "TypeParamRef" not in payload
        assert "ProcRef[" not in payload
        assert "providers.execute" not in payload
        assert "prompts.implementation.execute" not in payload
        assert "%loop-state." not in payload
        assert "procedure_call_unknown" not in payload
        assert "type_unknown" not in payload
        assert "loop_recur_state_type_invalid" not in payload

    lowered = next(
        workflow
        for workflow in result.compiled_results_by_name["entry"].lowered_workflows
        if workflow.typed_workflow.definition.name == "entry::orchestrate"
    )
    authored_payload = json.dumps(lowered.authored_mapping, sort_keys=True)
    assert "providers.execute" not in authored_payload
    assert "prompts.implementation.execute" not in authored_payload
    assert "`review`" not in authored_payload
    assert "`fix`" not in authored_payload

    repeat_step = next(step for step in lowered.authored_mapping["steps"] if "repeat_until" in step)
    outputs = repeat_step["repeat_until"]["outputs"]
    on_exhausted = repeat_step["repeat_until"]["on_exhausted"]["outputs"]
    assert repeat_step["repeat_until"]["max_iterations"] == 4
    assert "state__latest_findings__schema_version" in outputs
    assert "state__latest_findings__items_path" in outputs
    assert outputs["state__latest_findings__items_path"]["under"] == "artifacts/work"
    assert outputs["state__latest_findings__items_path"]["must_exist_target"] is True
    assert on_exhausted["result__variant"] == "EXHAUSTED"
    assert on_exhausted["result__reason"] == "max_iterations_reached"
    assert "result__findings__schema_version" not in on_exhausted
    assert "result__findings__items_path" not in on_exhausted
    assert "result__review_report" not in on_exhausted
    assert "result__last_review_report" not in on_exhausted

    seed_step = next(step for step in lowered.authored_mapping["steps"] if step["name"].endswith("__seed"))
    seed_values = {value["name"]: value for value in seed_step["materialize_artifacts"]["values"]}
    assert seed_values["state__latest_findings__schema_version"]["source"] == {"literal": "ReviewFindings.v1"}
    assert seed_values["state__latest_findings__items_path"]["source"] == {"ref": "inputs.inputs__findings_path"}

    current_state_step = next(
        step
        for step in repeat_step["repeat_until"]["steps"]
        if step["name"].endswith("__body__state")
    )
    carried_copy = next(
        nested_step
        for nested_step in current_state_step["then"]["steps"]
        if nested_step["name"].endswith("__use_carried_state")
    )
    carried_contracts = {
        value["name"]: value["contract"]
        for value in carried_copy["materialize_artifacts"]["values"]
        if value["name"] in {"state__latest_findings__schema_version", "state__latest_findings__items_path"}
    }
    assert set(carried_contracts) == {
        "state__latest_findings__schema_version",
        "state__latest_findings__items_path",
    }
    assert carried_contracts["state__latest_findings__items_path"]["under"] == "artifacts/work"
    assert carried_contracts["state__latest_findings__items_path"]["must_exist_target"] is True
    review_decision_step = next(
        step
        for step in repeat_step["repeat_until"]["steps"]
        if step["name"].endswith("__body__review-decision__review_1")
    )
    review_decision_values = {
        value["name"]: value["source"]
        for value in review_decision_step["materialize_artifacts"]["values"]
    }
    assert review_decision_values["return__review_report"] == {
        "ref": (
            "self.steps."
            f"{review_decision_step['name']}__review-report.artifacts.report_path"
        )
    }
    assert '"APPROVED"' in authored_payload
    assert '"BLOCKED"' in authored_payload
    assert '"EXHAUSTED"' in authored_payload

    origin_paths = {
        origin.span.start.path
        for mapping in (
            lowered.origin_map.step_spans,
            lowered.origin_map.generated_output_spans,
            lowered.origin_map.generated_path_spans,
        )
        for origin in mapping.values()
        if getattr(origin, "span", None) is not None
    }
    assert any(path.endswith("entry.orc") for path in origin_paths)
    assert any(path.endswith("stdlib/review_loop_consumer.orc") for path in origin_paths)


def test_compile_stage3_imported_generic_loop_state_consumer_preserves_custom_schema_version_on_exhausted_state_projection(
    tmp_path: Path,
) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    source_root = tmp_path / "imported_consumer_custom"
    _write_module(
        source_root / "stdlib" / "types.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule stdlib/types)",
            "  (export WorkReport ReviewReportPath ReviewFindingsJsonPath CustomFindings ReviewDecision ReviewReportResult ReviewLoopResult)",
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defpath ReviewReportPath",
            "    :kind relpath",
            '    :under "artifacts/review"',
            "    :must-exist true)",
            "  (defpath ReviewFindingsJsonPath",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defrecord CustomFindings",
            "    (schema_version String)",
            "    (items_path ReviewFindingsJsonPath))",
            "  (defrecord ReviewReportResult",
            "    (report_path ReviewReportPath))",
            "  (defunion ReviewDecision",
            "    (APPROVE",
            "      (review_report ReviewReportPath)",
            "      (findings CustomFindings))",
            "    (REVISE",
            "      (review_report ReviewReportPath)",
            "      (findings CustomFindings)))",
            "  (defunion ReviewLoopResult",
            "    (APPROVED",
            "      (review_report ReviewReportPath)",
            "      (findings CustomFindings))",
            "    (EXHAUSTED",
            "      (last_review_report ReviewReportPath)",
            "      (findings CustomFindings)",
            "      (reason String))))",
        ],
    )
    _write_module(
        source_root / "stdlib" / "review_loop_consumer.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule stdlib/review_loop_consumer)",
            "  (import stdlib/types :only (ReviewDecision ReviewReportPath CustomFindings ReviewLoopResult))",
            "  (export consume-review-loop)",
            "  (defproc consume-review-loop",
            "    :forall (CompletedT InputsT)",
            "    ((completed CompletedT)",
            "     (inputs InputsT)",
            "     (initial_review_report ReviewReportPath)",
            "     (initial_findings CustomFindings)",
            "     (review ProcRef[(CompletedT InputsT) -> ReviewDecision])",
            "     (fix ProcRef[(CompletedT InputsT CustomFindings) -> CompletedT])",
            "     (max_iterations Int))",
            "    :where ((CompletedT is-record)",
            "            (InputsT is-record))",
            "    -> ReviewLoopResult",
            "    :effects ()",
            "    :lowering inline",
            "    (loop/recur",
            "      :max max_iterations",
            "      :state (loop-state",
            "               (completed CompletedT completed)",
            "               (inputs InputsT inputs)",
            "               (last_review_report ReviewReportPath initial_review_report)",
            "               (latest_findings CustomFindings initial_findings))",
            "      :on-exhausted (variant ReviewLoopResult EXHAUSTED",
            '                      :reason "max_iterations_reached"',
            "                      :last_review_report state.last_review_report",
            "                      :findings (record CustomFindings",
            "                                  :schema_version state.latest_findings.schema_version",
            "                                  :items_path state.latest_findings.items_path))",
            "      (fn (state)",
            "        (let* ((review-decision",
            "                 (review state.completed state.inputs)))",
            "          (match review-decision",
            "            ((APPROVE approved)",
            "             (done",
            "               (variant ReviewLoopResult APPROVED",
            "                 :review_report approved.review_report",
            "                 :findings (record CustomFindings",
            "                             :schema_version approved.findings.schema_version",
            "                             :items_path approved.findings.items_path))))",
            "            ((REVISE revised)",
            "             (let* ((fixed-completed",
            "                      (fix state.completed state.inputs revised.findings)))",
            "               (continue",
            "                 (loop-state :like state",
            "                   :completed fixed-completed",
            "                   :last_review_report revised.review_report",
            "                   :latest_findings revised.findings))))",
            "            ))))))",
        ],
    )
    entry_path = _write_module(
        source_root / "entry.orc",
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule entry)",
            "  (import stdlib/types :only (WorkReport ReviewReportPath ReviewFindingsJsonPath CustomFindings ReviewDecision ReviewReportResult ReviewLoopResult))",
            "  (import stdlib/review_loop_consumer :as review-loop :only (consume-review-loop))",
            "  (export orchestrate)",
            "  (defrecord CompletedSurface",
            "    (execution_report_path WorkReport))",
            "  (defrecord InputsSurface",
            "    (findings_path ReviewFindingsJsonPath))",
            "  (defproc review-once",
            "    ((completed CompletedSurface)",
            "     (inputs InputsSurface))",
            "    -> ReviewDecision",
            "    :effects ((uses-provider providers.execute))",
            "    :lowering inline",
            "    (let* ((review-report",
            "             (provider-result providers.execute",
            "               :prompt prompts.implementation.execute",
            "               :inputs (completed.execution_report_path inputs.findings_path)",
            "               :returns ReviewReportResult)))",
            "      (variant ReviewDecision REVISE",
            "        :review_report review-report.report_path",
            "        :findings (record CustomFindings",
            '                    :schema_version "Custom.v2"',
            "                    :items_path inputs.findings_path))))",
            "  (defproc fix-completed",
            "    ((completed CompletedSurface)",
            "     (inputs InputsSurface)",
            "     (findings CustomFindings))",
            "    -> CompletedSurface",
            "    :effects ()",
            "    :lowering inline",
            "    (let* ((state",
            "             (loop-state",
            "               (completed CompletedSurface completed)",
            "               (inputs InputsSurface inputs)",
            "               (findings CustomFindings findings)))",
            "           (updated",
            "             (loop-state :like state :completed completed)))",
            "      updated.completed))",
            "  (defworkflow orchestrate",
            "    ((completed CompletedSurface)",
            "     (inputs InputsSurface)",
            "     (initial_review_report ReviewReportPath))",
            "    -> ReviewLoopResult",
            "    (let* ((max_iterations 4)",
            "           (initial_findings",
            "             (record CustomFindings",
            '               :schema_version "Custom.v2"',
            "               :items_path inputs.findings_path)))",
            "      (review-loop.consume-review-loop",
            "        completed",
            "        inputs",
            "        initial_review_report",
            "        initial_findings",
            "        (proc-ref review-once)",
            "        (proc-ref fix-completed)",
            "        max_iterations))))",
        ],
    )

    result = compile_fn(
        entry_path,
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        lowering_route="legacy",
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = next(
        workflow
        for workflow in result.compiled_results_by_name["entry"].lowered_workflows
        if workflow.typed_workflow.definition.name == "entry::orchestrate"
    )
    repeat_step = next(step for step in lowered.authored_mapping["steps"] if "repeat_until" in step)
    on_exhausted = repeat_step["repeat_until"]["on_exhausted"]["outputs"]
    result_step = next(
        step for step in lowered.authored_mapping["steps"] if step["name"].endswith("__result")
    )
    exhausted_case = result_step["match"]["cases"]["EXHAUSTED"]

    assert repeat_step["repeat_until"]["max_iterations"] == 4
    assert on_exhausted["result__variant"] == "EXHAUSTED"
    assert on_exhausted["result__reason"] == "max_iterations_reached"
    assert "result__findings__schema_version" not in on_exhausted
    assert "result__findings__items_path" not in on_exhausted
    assert exhausted_case["outputs"]["return__findings__schema_version"]["from"] == {
        "ref": f"root.steps.{repeat_step['name']}.artifacts.state__latest_findings__schema_version"
    }
    assert exhausted_case["outputs"]["return__findings__items_path"]["from"] == {
        "ref": f"root.steps.{repeat_step['name']}.artifacts.state__latest_findings__items_path"
    }


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
