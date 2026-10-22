from __future__ import annotations

from copy import copy
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.cli.commands import repl as repl_cli
from orchestrator.workflow.run_ref import config as run_ref_config
from orchestrator.workflow.trial import config as trial_config
from orchestrator.workflow_lisp import build, syntax
from orchestrator.workflow_lisp.closed.build import Builder
from orchestrator.workflow_lisp.closed.target import refuse_retired_entry_target
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.closed.frontend import TypedProgram, compile_typed_program
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import build_syntax_module


OLD_TARGETS = ("2.14", "2.34")
ADMITTED_TARGETS = ("2.35", "2.38", "2.39", "2.40")


@pytest.mark.parametrize(
    "registry",
    [
        pytest.param(syntax.SUPPORTED_TARGET_DSL_VERSIONS, id="frontend"),
        pytest.param(run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, id="run-ref-config"),
    ],
)
def test_supported_target_registry_is_narrowed_to_235_through_240(registry) -> None:
    assert registry == frozenset({"2.35", "2.36", "2.37", "2.38", "2.39", "2.40"})
    assert run_ref_config._DEFAULT_TARGET_DSL_VERSION in registry
    assert trial_config._DEFAULT_TARGET_DSL_VERSION in registry


def _source(
    module: str,
    target: str,
    *,
    imports: str = "",
    workflow: str = '(defworkflow run () -> Result (record Result :value "ok"))',
) -> str:
    return f'''(workflow-lisp
      (:language "0.1")
      (:target-dsl "{target}")
      (defmodule {module})
      {imports}
      (export Result run)
      (defrecord Result (value String))
      {workflow})'''


def _write(root: Path, module: str, target: str, **kwargs) -> Path:
    path = root.joinpath(*module.split("/")).with_suffix(".orc")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_source(module, target, **kwargs), encoding="utf-8")
    return path


def _typed(path: Path, root: Path) -> TypedProgram:
    return compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(root,),
        command_boundaries={},
        workspace_root=root,
    )


def _call_workflow(alias: str) -> str:
    return f"(defworkflow run ((n Int)) -> Int (call {alias} :n n))"


def _retarget_capsule(program: TypedProgram, target: str) -> TypedProgram:
    """Build a complete in-memory typed capsule from a real compiler result."""
    environments = {}
    for module, environment in program.module_type_envs.items():
        cloned = copy(environment)
        cloned.target_dsl_version = target
        environments[module] = cloned
    return replace(program, target=target, module_type_envs=environments)


def _error_code(error: pytest.ExceptionInfo[LispFrontendCompileError]) -> str:
    return error.value.diagnostics[0].code


@pytest.mark.parametrize("target", OLD_TARGETS)
def test_source_syntax_rejects_pre_235_header_with_target_dsl_unsupported(
    target: str,
) -> None:
    source = _source("entry", target)
    tree = read_sexpr_text(source, source_path="entry.orc")

    with pytest.raises(LispFrontendCompileError) as caught:
        build_syntax_module(tree)

    assert _error_code(caught) == "target_dsl_unsupported"


@pytest.mark.parametrize("target", OLD_TARGETS)
def test_typed_source_entry_rejects_pre_235_header_with_target_dsl_unsupported(
    tmp_path: Path,
    target: str,
) -> None:
    entry = _write(tmp_path, "entry", target)

    with pytest.raises(LispFrontendCompileError) as caught:
        compile_stage3_entrypoint(
            entry,
            source_roots=(tmp_path,),
            command_boundaries={},
            workspace_root=tmp_path,
        )

    assert _error_code(caught) == "target_dsl_unsupported"


@pytest.mark.parametrize("target", OLD_TARGETS)
def test_direct_import_rejects_pre_235_module_header(
    tmp_path: Path,
    target: str,
) -> None:
    _write(tmp_path, "legacy", target)
    entry = _write(
        tmp_path,
        "entry",
        "2.35",
        imports="(import legacy :as legacy)",
    )

    with pytest.raises(LispFrontendCompileError) as caught:
        compile_stage3_entrypoint(
            entry,
            source_roots=(tmp_path,),
            command_boundaries={},
            workspace_root=tmp_path,
        )

    assert _error_code(caught) == "target_dsl_unsupported"


@pytest.mark.parametrize("target", OLD_TARGETS)
def test_transitive_import_rejects_pre_235_leaf_header(
    tmp_path: Path,
    target: str,
) -> None:
    _write(tmp_path, "legacy", target)
    _write(
        tmp_path,
        "middle",
        "2.35",
        imports="(import legacy :as legacy)",
    )
    entry = _write(
        tmp_path,
        "entry",
        "2.35",
        imports="(import middle :as middle)",
    )

    with pytest.raises(LispFrontendCompileError) as caught:
        compile_stage3_entrypoint(
            entry,
            source_roots=(tmp_path,),
            command_boundaries={},
            workspace_root=tmp_path,
        )

    assert _error_code(caught) == "target_dsl_unsupported"


@pytest.mark.parametrize("target", ADMITTED_TARGETS)
def test_admitted_source_controls_compile_at_supported_targets(
    tmp_path: Path,
    target: str,
) -> None:
    entry = _write(tmp_path, "entry", target)

    typed = _typed(entry, tmp_path)

    assert typed.target == target
    assert typed.entry is not None


def test_typed_import_rejects_pre_235_typed_program_capsule(
    tmp_path: Path,
) -> None:
    producer_path = _write(
        tmp_path,
        "producer",
        "2.35",
        workflow="(defworkflow run ((n Int)) -> Int (+ n 1))",
    )
    old_capsule = _retarget_capsule(_typed(producer_path, tmp_path), "2.34")
    entry = _write(
        tmp_path,
        "entry",
        "2.35",
        workflow=_call_workflow("dep"),
    )

    with pytest.raises(LispFrontendCompileError) as caught:
        _typed_with_imports(entry, tmp_path, {"dep": old_capsule})

    assert _error_code(caught) == "target_dsl_unsupported"


def test_typed_import_rejects_old_module_type_environment_in_235_capsule(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "embedded/dep",
        "2.35",
        workflow='(defworkflow run () -> String "embedded")',
    )
    capsule_path = _write(
        tmp_path,
        "capsule",
        "2.35",
        imports="(import embedded/dep :as embedded)",
    )
    capsule = _typed(capsule_path, tmp_path)
    old_environment = copy(capsule.module_type_envs["embedded/dep"])
    old_environment.target_dsl_version = "2.34"
    capsule = replace(
        capsule,
        module_type_envs={
            **capsule.module_type_envs,
            "embedded/dep": old_environment,
        },
    )
    assert capsule.target == "2.35"
    assert capsule.module_type_envs["embedded/dep"].target_dsl_version == "2.34"

    entry = _write(
        tmp_path,
        "entry",
        "2.35",
    )
    with pytest.raises(LispFrontendCompileError) as caught:
        _typed_with_imports(entry, tmp_path, {"capsule": capsule})

    assert _error_code(caught) == "target_dsl_unsupported"


def test_typed_import_rejects_pre_235_transitive_imported_program(
    tmp_path: Path,
) -> None:
    leaf_path = _write(
        tmp_path,
        "leaf",
        "2.35",
        workflow="(defworkflow run ((n Int)) -> Int (+ n 1))",
    )
    old_leaf = _retarget_capsule(_typed(leaf_path, tmp_path), "2.34")
    middle_path = _write(
        tmp_path,
        "middle",
        "2.35",
        workflow="(defworkflow run ((n Int)) -> Int n)",
    )
    middle = replace(_typed(middle_path, tmp_path), imported_programs={"leaf": old_leaf})
    entry = _write(
        tmp_path,
        "entry",
        "2.35",
        workflow=_call_workflow("middle"),
    )

    with pytest.raises(LispFrontendCompileError) as caught:
        _typed_with_imports(entry, tmp_path, {"middle": middle})

    assert _error_code(caught) == "target_dsl_unsupported"


@pytest.mark.parametrize("invalid_field", ("target", "module_environment", "transitive"))
def test_closed_builder_rejects_pre_235_target_anywhere_in_typed_capsule_graph(
    tmp_path: Path,
    invalid_field: str,
) -> None:
    path = _write(tmp_path, "entry", "2.35")
    typed = _typed(path, tmp_path)
    if invalid_field == "target":
        typed = replace(typed, target="2.34")
    elif invalid_field == "module_environment":
        old_environment = copy(typed.module_type_envs[typed.entry_module])
        old_environment.target_dsl_version = "2.34"
        typed = replace(
            typed,
            module_type_envs={**typed.module_type_envs, typed.entry_module: old_environment},
        )
    else:
        leaf_path = _write(
            tmp_path,
            "leaf",
            "2.35",
            workflow="(defworkflow run ((n Int)) -> Int (+ n 1))",
        )
        old_leaf = _retarget_capsule(_typed(leaf_path, tmp_path), "2.34")
        middle_path = _write(tmp_path, "middle", "2.35")
        middle = replace(_typed(middle_path, tmp_path), imported_programs={"leaf": old_leaf})
        typed = replace(typed, imported_programs={"middle": middle})

    with pytest.raises(LispFrontendCompileError) as caught:
        Builder(typed)

    assert _error_code(caught) == "target_dsl_unsupported"


def _typed_with_imports(
    path: Path,
    root: Path,
    imported_programs: dict[str, TypedProgram],
) -> TypedProgram:
    return compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(root,),
        command_boundaries={},
        imported_programs=imported_programs,
        workspace_root=root,
    )


@pytest.mark.parametrize("target", (*OLD_TARGETS, *ADMITTED_TARGETS))
def test_repl_load_uses_the_source_floor(
    tmp_path: Path,
    target: str,
) -> None:
    entry = _write(tmp_path, "entry", target)
    session = repl_cli.ReplSession(workspace=tmp_path, state_dir=None)

    if target in OLD_TARGETS:
        with pytest.raises(LispFrontendCompileError) as caught:
            repl_cli._dispatch(session, f":load {entry}")
        assert _error_code(caught) == "target_dsl_unsupported"
        assert session.module is None
    else:
        assert repl_cli._dispatch(session, f":load {entry}") is True
        assert session.module is not None
        assert session.module.typed_program.target == target


def test_repl_old_target_reload_invalidates_previous_source_snapshot(
    tmp_path: Path,
) -> None:
    entry = _write(tmp_path, "entry", "2.35")
    session = repl_cli.ReplSession(workspace=tmp_path, state_dir=None)
    assert repl_cli._dispatch(session, f":load {entry}") is True
    assert session.module is not None
    session.captured = object()

    entry.write_text(_source("entry", "2.34"), encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as caught:
        repl_cli._dispatch(session, f":load {entry}")

    assert _error_code(caught) == "target_dsl_unsupported"
    assert session.module is None
    assert session.captured is None


@pytest.mark.parametrize(
    "source",
    (
        "",
        '(something (:target-dsl "2.34"))',
        '(workflow-lisp (:language "0.1") (:target-dsl "2.34") '
        '(:target-dsl "2.35"))',
    ),
    ids=("empty", "wrong-root", "duplicate-target-header"),
)
def test_public_entry_retirement_preserves_syntax_errors(
    tmp_path: Path,
    source: str,
) -> None:
    entry = tmp_path / "malformed.orc"
    entry.write_text(source, encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as caught:
        refuse_retired_entry_target(entry)

    assert _error_code(caught) == "frontend_parse_error"


@pytest.mark.parametrize("target", OLD_TARGETS)
def test_lsp_in_memory_frontend_rejects_pre_235_header(
    tmp_path: Path,
    target: str,
) -> None:
    entry = _write(tmp_path, "analysis", target)

    with pytest.raises(LispFrontendCompileError) as caught:
        build.build_frontend_bundle_in_memory(build.FrontendBuildRequest(
            source_path=entry,
            entry_workflow="run",
            workspace_root=tmp_path,
        ))

    assert _error_code(caught) == "target_dsl_unsupported"
