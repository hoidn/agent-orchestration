import importlib
from pathlib import Path
from types import MappingProxyType

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage1_module
from orchestrator.workflow_lisp.compiler import compile_stage3_module as _compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import CallExpr
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "modules"
VALID_FIXTURES = FIXTURES / "valid"
INVALID_FIXTURES = FIXTURES / "invalid"
WORKFLOW_REF_FIXTURES = VALID_FIXTURES / "workflow_refs"
PROC_REF_FIXTURES = VALID_FIXTURES / "proc_refs"
INVALID_PROC_REF_FIXTURES = INVALID_FIXTURES / "proc_refs"


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def compile_stage3_module(*args, **kwargs):
    kwargs.setdefault("lowering_route", "legacy")
    return _compile_stage3_module(*args, **kwargs)


def _compile_stage1_entrypoint(path: Path, *, source_root: Path):
    compile_fn = getattr(_compiler_module(), "compile_stage1_entrypoint", None)
    assert callable(compile_fn), "compile_stage1_entrypoint is missing"
    return compile_fn(path, source_roots=(source_root,))


def _compile_stage3_entrypoint(
    path: Path,
    *,
    source_root: Path,
    imported_workflow_bundles=None,
    lowering_route: str | None = "legacy",
    validate_shared: bool = False,
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
        validate_shared=validate_shared,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
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


def test_compile_stage1_entrypoint_preserves_guidance_through_schema_reexports(tmp_path: Path) -> None:
    source_root = tmp_path / "schema_guidance_reexport"
    entry_path = _write_module(
        source_root / "demo" / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule demo/entry)",
                "  (import demo/middle :only (ExtendedReviewFields))",
                "  (defrecord ReviewResult",
                "    (:include ExtendedReviewFields)))",
            ]
        ),
    )
    _write_module(
        source_root / "demo" / "middle.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule demo/middle)",
                "  (import demo/base :only (ReviewFields))",
                "  (export ExtendedReviewFields)",
                "  (defschema ExtendedReviewFields",
                "    (:include ReviewFields)))",
            ]
        ),
    )
    _write_module(
        source_root / "demo" / "base.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule demo/base)",
                "  (export ReviewFields)",
                "  (defschema ReviewFields",
                '    (approved Bool :description "No blockers remain." :example true)))',
            ]
        ),
    )

    result = _compile_stage1_entrypoint(entry_path, source_root=source_root)
    review_result = next(
        definition for definition in result.entry_module.definitions if definition.name == "ReviewResult"
    )
    field = review_result.fields[0]

    assert field.guidance.description == "No blockers remain."
    assert field.guidance.example_expr.datum.value is True


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
    assert "std/phase" in result.compiled_modules_by_name
    assert result.compiled_modules_by_name["std/phase"].module_name == "std/phase"
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
    assert result.graph.export_surfaces_by_name["std/phase"].binding_for("review-revise-loop") is not None
    assert result.graph.export_surfaces_by_name["std/phase"].binding_for("review-revise-loop-proc") is not None


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
        lowering_route="legacy",
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
        lowering_route="legacy",
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
    assert specialized[0].definition.name.startswith("%proc-ref-call.%parametric_call.parametric.helper.apply_runner.")
    assert set(specialized[0].specialization.proc_ref_bindings) == {"runner"}
    assert specialized[0].signature.type_params == ()


def test_compile_stage3_entrypoint_rejects_private_imported_proc_refs(tmp_path: Path) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    path = INVALID_PROC_REF_FIXTURES / "proc_refs" / "private_entry.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_fn(
            path,
            source_roots=(INVALID_PROC_REF_FIXTURES,),
            lowering_route="legacy",
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
            lowering_route="legacy",
            validate_shared=True,
            workspace_root=tmp_path,
        )

    result = compile_fn(
        path,
        source_roots=(source_root,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        lowering_route="legacy",
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


def test_compile_stage3_entrypoint_imported_private_helper_local_union_compiles_on_default_wcc_route(
    tmp_path: Path,
) -> None:
    source_root = VALID_FIXTURES / "imported_private_helper_local_union"
    entry_path = source_root / "imported_private_helper_local_union" / "consumer.orc"

    result = _compile_stage3_entrypoint(
        entry_path,
        source_root=source_root,
        lowering_route=None,
        validate_shared=True,
        tmp_path=tmp_path,
    )

    assert (
        "imported_private_helper_local_union/consumer::run"
        in result.entry_result.validated_bundles
    )
    lowered_names = {
        workflow.typed_workflow.definition.name
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    assert "%helper.imported_private_helper_local_union/helper::route-decision.v1" in lowered_names
    assert "%helper.imported_private_helper_local_union/helper::finalize-decision.v1" in lowered_names


def test_compile_stage3_entrypoint_imported_private_helper_exported_union_not_imported_compiles_on_default_wcc_route(
    tmp_path: Path,
) -> None:
    source_root = VALID_FIXTURES / "imported_private_helper_exported_union_not_imported"
    entry_path = source_root / "imported_private_helper_exported_union_not_imported" / "consumer.orc"

    result = _compile_stage3_entrypoint(
        entry_path,
        source_root=source_root,
        lowering_route=None,
        validate_shared=True,
        tmp_path=tmp_path,
    )

    assert (
        "imported_private_helper_exported_union_not_imported/consumer::run"
        in result.entry_result.validated_bundles
    )
    lowered_names = {
        workflow.typed_workflow.definition.name
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    }
    assert "%helper.imported_private_helper_exported_union_not_imported/helper::route-decision.v1" in lowered_names
    assert (
        "%helper.imported_private_helper_exported_union_not_imported/helper::finalize-decision.v1"
        in lowered_names
    )


@pytest.mark.parametrize(
    ("lowering_route", "consumer_name"),
    (
        ("legacy", "lower_workflow_definitions"),
        ("wcc_m4", "lower_wcc_m4_workflow_definitions"),
    ),
)
def test_linked_private_procedures_resolve_once_in_their_defining_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lowering_route: str,
    consumer_name: str,
) -> None:
    source_root = VALID_FIXTURES / "imported_private_helper_local_union"
    entry_path = source_root / "imported_private_helper_local_union" / "consumer.orc"
    compiler = _compiler_module()
    original_resolver = compiler._resolve_procedure_lowering
    resolver_inputs: list[tuple[str, ...]] = []
    received_rows: list[tuple[object, ...]] = []

    def counting_resolver(typed_procedures, **kwargs):
        resolver_inputs.append(
            tuple(procedure.definition.name for procedure in typed_procedures)
        )
        return original_resolver(typed_procedures, **kwargs)

    original_consumer = getattr(compiler, consumer_name)

    def capture_consumer(typed_workflows, **kwargs):
        if any(
            workflow.definition.name
            == "imported_private_helper_local_union/consumer::run"
            for workflow in typed_workflows
        ):
            typed_rows = kwargs["typed_procedures"]
            resolved_rows = kwargs["resolved_procedures_by_name"]
            assert isinstance(resolved_rows, type(MappingProxyType({})))
            assert all(
                resolved_rows[procedure.definition.name] is procedure
                for procedure in typed_rows
            )
            received_rows.append(typed_rows)
        return original_consumer(typed_workflows, **kwargs)

    monkeypatch.setattr(compiler, "_resolve_procedure_lowering", counting_resolver)
    monkeypatch.setattr(compiler, consumer_name, capture_consumer)

    result = _compile_stage3_entrypoint(
        entry_path,
        source_root=source_root,
        lowering_route=lowering_route,
        validate_shared=False,
        tmp_path=tmp_path,
    )

    assert resolver_inputs == [
        (
            "imported_private_helper_local_union/helper::finalize-decision",
            "imported_private_helper_local_union/helper::route-decision",
        )
    ]
    assert len(received_rows) == 1
    assert {
        procedure.generated_workflow_name
        for procedure in received_rows[0]
    } >= {
        "%helper.imported_private_helper_local_union/helper::finalize-decision.v1",
        "%helper.imported_private_helper_local_union/helper::route-decision.v1",
    }
    assert result.entry_result.typed_procedures == ()


def test_compile_stage3_entrypoint_imported_private_helper_unknown_type_stays_at_helper_span(
    tmp_path: Path,
) -> None:
    source_root = INVALID_FIXTURES / "imported_private_helper_unknown_type"
    entry_path = source_root / "imported_private_helper_unknown_type" / "consumer.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage3_entrypoint(
            entry_path,
            source_root=source_root,
            lowering_route=None,
            validate_shared=False,
            tmp_path=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "type_unknown"
    assert diagnostic.span.start.path.endswith("helper.orc")


def test_compile_stage3_entrypoint_imported_private_helper_runtime_executes_nested_private_call(
    tmp_path: Path,
) -> None:
    source_root = VALID_FIXTURES / "imported_private_helper_local_union"
    entry_path = source_root / "imported_private_helper_local_union" / "consumer.orc"
    result = _compile_stage3_entrypoint(
        entry_path,
        source_root=source_root,
        lowering_route=None,
        validate_shared=True,
        tmp_path=tmp_path,
    )
    bundle = result.entry_result.validated_bundles[
        "imported_private_helper_local_union/consumer::run"
    ]
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        binding_inputs,
        {"input__approved": True, "input__detail": "ok"},
        tmp_path,
    )
    state_manager = StateManager(workspace=tmp_path, run_id="imported-private-helper-runtime")
    state_manager.initialize(
        entry_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"return__variant": "ALLOW", "return__detail": "ok"}
    call_step = state["steps"][
        "imported_private_helper_local_union/consumer::run__decision__call_imported_private_helper_local_union/helper::run-helper"
    ]
    assert call_step["status"] == "completed"
    assert any(
        "route_decision" in frame_name
        for frame_name in call_step["debug"]["call"]["nested_call_frames"]
    )


def test_compile_stage3_entrypoint_pure_projection_boundary_decision_consumer_compiles_on_default_wcc_route(
    tmp_path: Path,
) -> None:
    source_root = VALID_FIXTURES / "pure_projection_boundary_decision_consumer"
    entry_path = source_root / "pure_projection_boundary_decision_consumer" / "entry.orc"

    result = _compile_stage3_entrypoint(
        entry_path,
        source_root=source_root,
        lowering_route=None,
        validate_shared=True,
        tmp_path=tmp_path,
    )

    assert "pure_projection_boundary_decision_consumer/entry::run" in result.entry_result.validated_bundles


def test_compile_stage3_entrypoint_pure_projection_boundary_decision_consumer_executes_runtime_path(
    tmp_path: Path,
) -> None:
    source_root = VALID_FIXTURES / "pure_projection_boundary_decision_consumer"
    entry_path = source_root / "pure_projection_boundary_decision_consumer" / "entry.orc"
    result = _compile_stage3_entrypoint(
        entry_path,
        source_root=source_root,
        lowering_route=None,
        validate_shared=True,
        tmp_path=tmp_path,
    )
    bundle = result.entry_result.validated_bundles[
        "pure_projection_boundary_decision_consumer/entry::run"
    ]
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        binding_inputs,
        {"bundle_path": "state/selection.json", "reason": "gap"},
        tmp_path,
    )
    state_manager = StateManager(
        workspace=tmp_path,
        run_id="pure-projection-boundary-decision-consumer",
    )
    state_manager.initialize(
        entry_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__selected_path": "state/selection.json",
        "return__path_detail": "READY",
        "return__shared_detail": "gap-computed",
    }


def test_compile_stage3_entrypoint_rejects_ambiguous_unqualified_transition_imports(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "ambiguous_transition_imports"
    for module_name in ("first", "second"):
        _write_module(
            source_root / "demo" / f"{module_name}.orc",
            "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    f"  (defmodule demo/{module_name})",
                    "  (export OutcomeRequest OutcomeResult record-outcome outcome-state)",
                    "  (defrecord OutcomeState",
                    "    (status String))",
                    "  (defrecord OutcomeRequest",
                    "    (status String))",
                    "  (defrecord OutcomeResult",
                    "    (status String))",
                    "  (defrecord OutcomeAudit",
                    "    (status String))",
                    "  (defrecord OutcomeTransitionResult",
                    "    (status String))",
                    "  (defresource outcome-state",
                    "    :state-type OutcomeState",
                    "    :backing state-layout)",
                    "  (deftransition record-outcome",
                    "    :resource outcome-state",
                    "    :request-type OutcomeRequest",
                    "    :result-type OutcomeTransitionResult",
                    '    :preconditions ((!= request.status ""))',
                    "    :updates ((set-field status request.status))",
                    "    :write-set (status)",
                    "    :idempotency-fields (status)",
                    "    :result (record OutcomeTransitionResult",
                    "      :status request.status)",
                    "    :audit (record OutcomeAudit",
                    "      :status request.status)",
                    "    :conflict-policy fail_closed",
                    "    :backend runtime_native)",
                    "  (defworkflow shared",
                        "    ()",
                        "    -> OutcomeResult",
                        "    (let* ((transition-result",
                        "             (resource-transition",
                        "               :transition record-outcome",
                        "               :resource outcome-state",
                        "               :request (record OutcomeRequest :status \"ok\"))))",
                        "      (record OutcomeResult",
                        "        :status transition-result.status))))",
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
                "  (import demo/first :only (OutcomeResult OutcomeRequest record-outcome outcome-state))",
                "  (import demo/second :only (OutcomeResult OutcomeRequest record-outcome outcome-state))",
                "  (export run)",
                "  (defworkflow run",
                "    ()",
                "    -> OutcomeResult",
                "    (let* ((transition-result",
                "             (resource-transition",
                "               :transition record-outcome",
                "               :resource outcome-state",
                "               :request (record OutcomeRequest :status \"ok\"))))",
                "      (record OutcomeResult",
                "        :status transition-result.status))))",
                ]
            ),
        )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage3_entrypoint(
            entry_path,
            source_root=source_root,
            lowering_route=None,
            validate_shared=True,
            tmp_path=tmp_path,
        )

    _assert_diagnostic_code(excinfo, "module_import_ambiguous")


def test_compile_stage3_entrypoint_imported_root_result_call_executes_runtime(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    callee_dir = source_root / "rootcall"
    callee_dir.mkdir(parents=True)
    _write_module(
        callee_dir / "rootlib.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule rootcall/rootlib)",
                "  (export root-flag)",
                "  (defworkflow root-flag",
                "    ((count Int))",
                "    -> Bool",
                "    (> count 0)))",
            ]
        )
        + "\n",
    )
    entry_path = _write_module(
        callee_dir / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule rootcall/entry)",
                "  (import rootcall/rootlib :only (root-flag))",
                "  (export run)",
                "  (defrecord Wrap",
                "    (ok Bool))",
                "  (defworkflow run",
                "    ((count Int))",
                "    -> Wrap",
                "    (let* ((ok (call root-flag :count count)))",
                "      (record Wrap :ok ok))))",
            ]
        )
        + "\n",
    )

    result = _compile_stage3_entrypoint(
        entry_path,
        source_root=source_root,
        lowering_route=None,
        validate_shared=True,
        tmp_path=tmp_path,
    )
    bundle = result.entry_result.validated_bundles["rootcall/entry::run"]
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(binding_inputs, {"count": 2}, tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="imported-root-result-call")
    state_manager.initialize(
        entry_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )

    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"return__ok": True}
    call_step = next(
        result_payload
        for step_name, result_payload in state["steps"].items()
        if "__call_" in step_name
    )
    assert call_step["status"] == "completed"
    assert call_step["artifacts"] == {"__result__": True}


def test_root_result_workflow_failure_suppresses_output_finalization(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path / "root_result_failure.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defworkflow root-check",
                "    ((count Int))",
                "    -> Bool",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py")',
                "      :returns Bool)))",
            ]
        )
        + "\n",
    )
    result = compile_stage3_module(
        module_path,
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        bundle
        for name, bundle in result.validated_bundles.items()
        if name == "root-check" or name.endswith("::root-check")
    )
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(binding_inputs, {"count": 1}, tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="root-result-suppression")
    state_manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )

    state = WorkflowExecutor(
        bundle,
        tmp_path,
        state_manager,
        max_retries=0,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert state["status"] == "failed"
    assert not state.get("workflow_outputs")
