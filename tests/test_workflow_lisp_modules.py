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


def test_compile_stage1_entrypoint_rejects_declaring_file_path_mismatches() -> None:
    source_root = INVALID_FIXTURES / "path_mismatch"
    path = source_root / "neurips" / "bad.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_stage1_entrypoint(path, source_root=source_root)

    _assert_diagnostic_code(excinfo, "module_path_mismatch")


def test_compile_stage3_entrypoint_registers_canonical_callable_keys(tmp_path: Path) -> None:
    source_root = VALID_FIXTURES / "callables"
    path = source_root / "neurips" / "entry.orc"

    result = _compile_stage3_entrypoint(path, source_root=source_root, tmp_path=tmp_path)

    assert "neurips/procedures::build-checks" in result.entry_result.procedure_catalog.signatures_by_name
    assert "neurips/helper::provider-attempt" in result.entry_result.workflow_catalog.signatures_by_name
    assert "neurips/helper::secondary" in result.validated_bundles_by_name


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
