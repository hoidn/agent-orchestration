import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage1_module, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import CallExpr
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "modules"
VALID_FIXTURES = FIXTURES / "valid"
INVALID_FIXTURES = FIXTURES / "invalid"
WORKFLOW_REF_FIXTURES = VALID_FIXTURES / "workflow_refs"
PROC_REF_FIXTURES = VALID_FIXTURES / "proc_refs"
INVALID_PROC_REF_FIXTURES = INVALID_FIXTURES / "proc_refs"


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")

def _compile_stage1_entrypoint(path: Path, *, source_root: Path):
    compile_fn = getattr(_compiler_module(), "compile_stage1_entrypoint", None)
    assert callable(compile_fn), "compile_stage1_entrypoint is missing"
    return compile_fn(path, source_roots=(source_root,))


def _compile_stage3_entrypoint(
    path: Path,
    *,
    source_root: Path,
    imported_workflow_bundles=None,
    tmp_path: Path,
):
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"
    return compile_fn(
        path,
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        imported_workflow_bundles=imported_workflow_bundles,
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _write_module(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_compile_stage1_entrypoint_resolves_source_roots_and_matches_module_paths() -> None:
    source_root = VALID_FIXTURES / "alias_only"
    path = source_root / "neurips" / "default_alias.orc"

    result = _compile_stage1_entrypoint(path, source_root=source_root)

    assert result.entry_module.module_name == "neurips/default_alias"
    assert tuple(result.graph.modules_by_name) == (
        "neurips/default_alias",
        "neurips/types",
    )
    assert result.graph.modules_by_name["neurips/default_alias"].path == path
    assert result.compiled_modules_by_name["neurips/types"].module_name == "neurips/types"


def test_compile_stage1_entrypoint_supports_default_aliases_and_only_bindings() -> None:
    source_root = VALID_FIXTURES / "alias_only"

    alias_result = _compile_stage1_entrypoint(
        source_root / "neurips" / "default_alias.orc",
        source_root=source_root,
    )
    only_result = _compile_stage1_entrypoint(
        source_root / "neurips" / "only_binding.orc",
        source_root=source_root,
    )

    assert alias_result.entry_module.imports[0].alias == "types"
    assert alias_result.entry_module.imports[0].only == ()
    assert only_result.entry_module.imports[0].alias == "types"
    assert only_result.entry_module.imports[0].only == ("WorkReport", "ImplementationSummary")


def test_compile_stage1_entrypoint_imports_exported_schemas_for_includes() -> None:
    source_root = VALID_FIXTURES / "schema_import"
    path = source_root / "neurips" / "entry.orc"

    result = _compile_stage1_entrypoint(path, source_root=source_root)

    workflow_inputs = next(
        definition for definition in result.entry_module.definitions if definition.name == "WorkflowInputs"
    )

    assert workflow_inputs.name == "WorkflowInputs"
    assert [field.name for field in workflow_inputs.fields] == [
        "status",
        "execution_report",
        "review_report",
    ]


def test_compile_stage1_entrypoint_imports_transitively_reexported_schemas_for_includes() -> None:
    source_root = VALID_FIXTURES / "schema_reexport_import"
    path = source_root / "neurips" / "entry.orc"

    result = _compile_stage1_entrypoint(path, source_root=source_root)

    workflow_inputs = next(
        definition for definition in result.entry_module.definitions if definition.name == "WorkflowInputs"
    )

    assert workflow_inputs.name == "WorkflowInputs"
    assert [field.name for field in workflow_inputs.fields] == [
        "status",
        "execution_report",
        "review_report",
    ]


def test_compile_stage1_entrypoint_validates_export_surfaces() -> None:
    source_root = INVALID_FIXTURES / "missing_export"
    path = source_root / "neurips" / "entry.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage1_entrypoint(path, source_root=source_root)

    _assert_diagnostic_code(excinfo, "module_export_missing")


def test_compile_stage1_entrypoint_accepts_exported_local_macros(tmp_path: Path) -> None:
    source_root = tmp_path / "exported_local_macro"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/helper :only (m))",
                "  (export EntryOut)",
                "  (defrecord EntryOut",
                "    (report String)))",
            ]
        ),
    )
    _write_module(
        source_root / "demo" / "helper.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/helper)",
                "  (export m)",
                "  (defmacro m ()",
                "    (defrecord ImportedOut",
                "      (report String))))",
            ]
        ),
    )

    result = _compile_stage1_entrypoint(entry_path, source_root=source_root)

    assert "m" in result.graph.export_surfaces_by_name["demo/helper"].macros_by_name


def test_compile_stage1_entrypoint_rejects_duplicate_alias_bindings() -> None:
    source_root = INVALID_FIXTURES / "duplicate_alias"
    path = source_root / "duplicate" / "alias.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage1_entrypoint(path, source_root=source_root)

    _assert_diagnostic_code(excinfo, "module_alias_duplicate")


def test_compile_stage1_entrypoint_rejects_module_cycles() -> None:
    source_root = INVALID_FIXTURES / "cycle"
    path = source_root / "cycle" / "entry.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage1_entrypoint(path, source_root=source_root)

    _assert_diagnostic_code(excinfo, "module_cycle")


def test_compile_stage1_entrypoint_rejects_ambiguous_only_imports() -> None:
    source_root = INVALID_FIXTURES / "ambiguous"
    path = source_root / "ambiguous" / "entry.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage1_entrypoint(path, source_root=source_root)

    _assert_diagnostic_code(excinfo, "module_import_ambiguous")


def test_compile_stage1_entrypoint_rejects_ambiguous_unqualified_schema_imports() -> None:
    source_root = INVALID_FIXTURES / "schema_only_ambiguous"
    path = source_root / "neurips" / "entry.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage1_entrypoint(path, source_root=source_root)

    _assert_diagnostic_code(excinfo, "module_import_ambiguous")


def test_compile_stage1_entrypoint_rejects_declaring_file_path_mismatches() -> None:
    source_root = INVALID_FIXTURES / "path_mismatch"
    path = source_root / "neurips" / "bad.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage1_entrypoint(path, source_root=source_root)

    _assert_diagnostic_code(excinfo, "module_path_mismatch")


def test_compile_stage1_entrypoint_resolves_builtin_stdlib_imports_without_manual_source_root(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "builtin_stdlib_import"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import std/phase :only (ReviewDecision))",
                "  (export LocalDecision)",
                "  (defrecord LocalDecision",
                "    (decision ReviewDecision)))",
            ]
        ),
    )

    result = _compile_stage1_entrypoint(entry_path, source_root=source_root)

    assert "std/phase" in result.graph.modules_by_name
    assert result.graph.modules_by_name["std/phase"].source_root != source_root

def test_compile_stage1_entrypoint_exposes_review_loop_macro_from_builtin_stdlib(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "builtin_stdlib_review_loop_macro"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import std/phase :only (review-revise-loop))",
                "  (export EntryOut)",
                "  (defrecord EntryOut",
                "    (report String)))",
            ]
        ),
    )

    result = _compile_stage1_entrypoint(entry_path, source_root=source_root)

    assert "review-revise-loop" in result.graph.export_surfaces_by_name["std/phase"].macros_by_name
    assert "review-revise-loop-proc" in result.graph.export_surfaces_by_name["std/phase"].procedures_by_name


def test_compile_stage1_entrypoint_rejects_project_local_stdlib_shadowing(tmp_path: Path) -> None:
    source_root = tmp_path / "shadowed_stdlib"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import std/phase :only (ReviewDecision))",
                "  (export LocalDecision)",
                "  (defrecord LocalDecision",
                "    (decision ReviewDecision)))",
            ]
        ),
    )
    _write_module(
        source_root / "std" / "phase.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule std/phase)",
                "  (export ReviewDecision)",
                "  (defenum ReviewDecision",
                "    APPROVE",
                "    REVISE",
                "    BLOCKED))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage1_entrypoint(entry_path, source_root=source_root)

    _assert_diagnostic_code(excinfo, "module_import_ambiguous")


def test_compile_stage3_entrypoint_registers_canonical_callable_keys(tmp_path: Path) -> None:
    source_root = VALID_FIXTURES / "callables"
    path = source_root / "neurips" / "entry.orc"

    result = _compile_stage3_entrypoint(path, source_root=source_root, tmp_path=tmp_path)

    assert "neurips/procedures::build-checks" in result.entry_result.procedure_catalog.signatures_by_name
    assert "neurips/helper::provider-attempt" in result.entry_result.workflow_catalog.signatures_by_name
    assert "neurips/helper::secondary" in result.validated_bundles_by_name


def test_compile_stage3_entrypoint_resolves_imported_workflow_refs_to_canonical_keys(tmp_path: Path) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    path = WORKFLOW_REF_FIXTURES / "workflow_refs" / "imported_entry.orc"
    result = compile_fn(
        path,
        source_roots=(WORKFLOW_REF_FIXTURES,),
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "workflow_refs/imported_helper::echo-helper" in result.entry_result.workflow_catalog.signatures_by_name
    assert "workflow_refs/imported_entry::entry" in result.validated_bundles_by_name


def test_compile_stage3_entrypoint_resolves_imported_proc_refs_to_canonical_keys(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.expressions import ProcRefLiteralExpr, ProcedureCallExpr

    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    path = PROC_REF_FIXTURES / "proc_refs" / "imported_entry.orc"
    result = compile_fn(
        path,
        source_roots=(PROC_REF_FIXTURES,),
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )
    entry = next(
        workflow
        for workflow in result.entry_result.typed_workflows
        if workflow.definition.name == "proc_refs/imported_entry::entry"
    )
    body = entry.typed_body.expr

    assert "proc_refs/imported_helper::echo-helper" in result.entry_result.procedure_catalog.signatures_by_name
    assert isinstance(body, ProcedureCallExpr)
    assert isinstance(body.args[0], ProcRefLiteralExpr)
    assert body.args[0].target_name == "proc_refs/imported_helper::echo-helper"


def test_compile_stage3_entrypoint_resolves_imported_bind_proc_bases_to_canonical_keys(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.expressions import BindProcExpr, ProcRefLiteralExpr, ProcedureCallExpr

    source_root = tmp_path / "proc_ref_bind_proc_imports"
    _write_module(
        source_root / "proc_refs" / "helper.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule proc_refs/helper)",
                "  (export helper)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defproc helper",
                "    ((fixed String)",
                "     (input String))",
                "    -> String",
                "    :effects ()",
                "    :lowering inline",
                "    fixed))",
            ]
        ),
    )
    entry_path = _write_module(
        source_root / "proc_refs" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule proc_refs/entry)",
                '  (import proc_refs/helper :as helper)',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord WorkflowInput",
                "    (report WorkReport)",
                "    (label String))",
                "  (defrecord WorkflowOutput",
                "    (label String))",
                "  (defproc forward",
                "    ((runner ProcRef[String -> String])",
                "     (input String))",
                "    -> WorkflowOutput",
                "    :effects ((uses-command run_checks))",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" input)',
                "      :returns WorkflowOutput))",
                "  (defworkflow entry",
                "    ((input WorkflowInput))",
                "    -> WorkflowOutput",
                "    (forward",
                "      (bind-proc (proc-ref helper.helper)",
                "        :fixed input.label)",
                "      input.label)))",
            ]
        ),
    )

    result = _compile_stage3_entrypoint(entry_path, source_root=source_root, tmp_path=tmp_path)
    entry = next(
        workflow
        for workflow in result.entry_result.typed_workflows
        if workflow.definition.name == "proc_refs/entry::entry"
    )
    body = entry.typed_body.expr

    assert isinstance(body, ProcedureCallExpr)
    assert isinstance(body.args[0], BindProcExpr)
    assert isinstance(body.args[0].base_expr, ProcRefLiteralExpr)
    assert body.args[0].base_expr.target_name == "proc_refs/helper::helper"


def test_compile_stage3_entrypoint_specializes_imported_parametric_proc_defs(tmp_path: Path) -> None:
    source_root = tmp_path / "parametric_proc_imports"
    _write_module(
        source_root / "parametric" / "helper.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule parametric/helper)",
                "  (export WorkflowInput apply-runner echo-input)",
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
                "      :report value.report)))",
            ]
        ),
    )
    entry_path = _write_module(
        source_root / "parametric" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule parametric/entry)",
                "  (import parametric/helper :only (WorkflowInput apply-runner echo-input))",
                "  (export entry)",
                "  (defworkflow entry",
                "    ((input WorkflowInput))",
                "    -> WorkflowInput",
                "    (apply-runner (proc-ref echo-input) input)))",
            ]
        ),
    )

    result = _compile_stage3_entrypoint(entry_path, source_root=source_root, tmp_path=tmp_path)
    specialized = [
        procedure
        for procedure in result.entry_result.typed_procedures
        if getattr(procedure.specialization, "type_bindings", {})
        and procedure.specialization.base_name == "parametric/helper::apply-runner"
    ]

    assert "parametric/helper::apply-runner" in result.entry_result.procedure_catalog.signatures_by_name
    assert len(specialized) == 1
    assert specialized[0].definition.name.startswith("%parametric-call.parametric.helper.apply_runner.")
    assert specialized[0].signature.type_params == ()


def test_compile_stage3_entrypoint_rejects_private_imported_proc_refs(tmp_path: Path) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    path = INVALID_PROC_REF_FIXTURES / "proc_refs" / "private_entry.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_fn(
            path,
            source_roots=(INVALID_PROC_REF_FIXTURES,),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "proc_ref_private_import_invalid")


def test_compile_stage3_entrypoint_preserves_wrapper_behavior_for_single_file_fixtures(tmp_path: Path) -> None:
    stage1_fixture = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid" / "type_definitions.orc"
    stage3_fixture = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid" / "structured_results.orc"

    stage1_module = compile_stage1_module(stage1_fixture)
    stage3_result = compile_stage3_module(
        stage3_fixture,
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

    assert stage1_module.definitions
    assert "provider_attempt" in stage3_result.workflow_catalog.signatures_by_name


def test_compile_stage3_module_supports_builtin_stdlib_imports(tmp_path: Path) -> None:
    path = _write_module(
        tmp_path / "builtin_stdlib_stage3" / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import std/phase :only (ReviewDecision))",
                "  (export WorkflowOutput run)",
                "  (defrecord WorkflowOutput",
                "    (report String))",
                "  (defworkflow run",
                "    ()",
                "    -> WorkflowOutput",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs ()",
                "      :returns WorkflowOutput)))",
            ]
        ),
    )

    result = compile_stage3_module(
        path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert "demo/entry::run" in result.workflow_catalog.signatures_by_name

def test_compile_stage3_entrypoint_skips_shared_validation_when_disabled(tmp_path: Path) -> None:
    source_root = tmp_path / "validate_shared_disabled"
    path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (export run)",
                "  (defpath EscapedReport",
                "    :kind relpath",
                '    :under "../escape"',
                "    :must-exist true)",
                "  (defrecord Out",
                "    (report EscapedReport))",
                "  (defworkflow run",
                "    ((report_path EscapedReport))",
                "    -> Out",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (report_path)",
                "      :returns Out)))",
            ]
        ),
    )

    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    with pytest.raises(LispFrontendCompileError):
        compile_fn(
            path,
            source_roots=(source_root,),
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=True,
            workspace_root=tmp_path,
        )

    result = compile_fn(
        path,
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.entry_result.validated_bundles == {}
    assert result.validated_bundles_by_name == {}


def test_compile_stage3_entrypoint_prefers_local_names_over_only_imports(tmp_path: Path) -> None:
    source_root = tmp_path / "local_precedence"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/helper :only (Out run))",
                "  (export run entry Out)",
                "  (defrecord Out",
                "    (local_report String))",
                "  (defworkflow run",
                "    ()",
                "    -> Out",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs ()",
                "      :returns Out))",
                "  (defworkflow entry",
                "    ()",
                "    -> Out",
                "    (call run)))",
            ]
        ),
    )
    _write_module(
        source_root / "demo" / "helper.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/helper)",
                "  (export Out run)",
                "  (defrecord Out",
                "    (remote_report String))",
                "  (defworkflow run",
                "    ()",
                "    -> Out",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs ()",
                "      :returns Out)))",
            ]
        ),
    )

    result = _compile_stage3_entrypoint(entry_path, source_root=source_root, tmp_path=tmp_path)

    local_run_signature = result.entry_result.workflow_catalog.signatures_by_name["demo/entry::run"]
    assert tuple(field.name for field in local_run_signature.return_type_ref.definition.fields) == ("local_report",)

    entry_workflow = next(
        workflow for workflow in result.entry_result.typed_workflows if workflow.definition.name == "demo/entry::entry"
    )
    assert isinstance(entry_workflow.typed_body.expr, CallExpr)
    assert entry_workflow.typed_body.expr.callee_name == "demo/entry::run"


def test_compile_stage3_entrypoint_prefers_local_macros_over_only_imports(tmp_path: Path) -> None:
    source_root = tmp_path / "local_macro_precedence"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/helper :only (m))",
                "  (export LocalOut)",
                "  (defmacro m ()",
                "    (defrecord LocalOut",
                "      (report String)))",
                "  (m))",
            ]
        ),
    )
    _write_module(
        source_root / "demo" / "helper.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/helper)",
                "  (export m)",
                "  (defmacro m ()",
                "    (defrecord ImportedOut",
                "      (report String))))",
            ]
        ),
    )

    result = _compile_stage3_entrypoint(entry_path, source_root=source_root, tmp_path=tmp_path)

    assert [definition.name for definition in result.entry_result.module.definitions] == ["LocalOut"]


def test_compile_stage3_entrypoint_accepts_imported_macros_via_alias_and_module_qualified_names(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "qualified_macro_imports"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/helper :as helper)",
                "  (export AliasOut ModuleOut)",
                "  (helper.m AliasOut)",
                "  (demo/helper/m ModuleOut))",
            ]
        ),
    )
    _write_module(
        source_root / "demo" / "helper.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/helper)",
                "  (export m)",
                "  (defmacro m (name)",
                "    (defrecord name",
                "      (report String))))",
            ]
        ),
    )

    result = _compile_stage3_entrypoint(entry_path, source_root=source_root, tmp_path=tmp_path)

    assert [definition.name for definition in result.entry_result.module.definitions] == [
        "AliasOut",
        "ModuleOut",
    ]


def test_compile_stage3_entrypoint_keeps_ambiguous_imported_macro_names_owned_by_module_resolution(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "ambiguous_macro_imports"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/first :only (m))",
                "  (import demo/second :only (m))",
                "  (export EntryOut)",
                "  (m EntryOut))",
            ]
        ),
    )
    for module_name in ("first", "second"):
        _write_module(
            source_root / "demo" / f"{module_name}.orc",
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    f"  (defmodule demo/{module_name})",
                    "  (export m)",
                    "  (defmacro m (name)",
                    "    (defrecord name",
                    "      (report String))))",
                ]
            ),
        )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage3_entrypoint(entry_path, source_root=source_root, tmp_path=tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "module_import_ambiguous"
    assert diagnostic.code != "macro_reserved_name"


def test_compile_stage3_entrypoint_rejects_mixed_direct_qualified_workflow_references(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "invalid_reference"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/helper :only (Out run))",
                "  (export entry)",
                "  (defworkflow entry",
                "    ()",
                "    -> Out",
                "    (call demo/helper.run)))",
            ]
        ),
    )
    _write_module(
        source_root / "demo" / "helper.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/helper)",
                "  (export run Out)",
                "  (defrecord Out",
                "    (report String))",
                "  (defworkflow run",
                "    ()",
                "    -> Out",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs ()",
                "      :returns Out)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage3_entrypoint(entry_path, source_root=source_root, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "module_reference_invalid")


def test_compile_stage1_entrypoint_exports_helpers_in_module_surfaces() -> None:
    source_root = VALID_FIXTURES / "imported_defun"
    path = source_root / "entry.orc"

    result = _compile_stage1_entrypoint(path, source_root=source_root)

    helper_surface = result.graph.export_surfaces_by_name["neurips/helpers"]
    assert hasattr(helper_surface, "functions_by_name")
    assert "summarize" in helper_surface.functions_by_name
    assert helper_surface.functions_by_name["summarize"].canonical_name == "neurips/helpers::summarize"


def test_compile_stage3_entrypoint_rejects_imported_callable_name_collisions(tmp_path: Path) -> None:
    source_root = tmp_path / "callable_collision"
    _write_module(
        source_root / "demo" / "types.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/types)",
                "  (export WorkReport ImplementationSummary)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport)))",
            ]
        ),
    )
    _write_module(
        source_root / "demo" / "helpers.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/helpers)",
                "  (import demo/types :only (WorkReport ImplementationSummary))",
                "  (export shared)",
                "  (defun shared",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (record ImplementationSummary :report report_path)))",
            ]
        ),
    )
    _write_module(
        source_root / "demo" / "procedures.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/procedures)",
                "  (import demo/types :only (WorkReport ImplementationSummary))",
                "  (export shared)",
                "  (defproc shared",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    :effects ()",
                "    (record ImplementationSummary :report report_path)))",
            ]
        ),
    )
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/types :only (WorkReport ImplementationSummary))",
                "  (import demo/helpers :only (shared))",
                "  (import demo/procedures :only (shared))",
                "  (export orchestrate)",
                "  (defworkflow orchestrate",
                "    ((report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (shared report_path)))",
            ]
        ),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage3_entrypoint(entry_path, source_root=source_root, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "callable_name_collision")
