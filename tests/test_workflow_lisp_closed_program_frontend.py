from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp import compiler as compiler_module
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.command_boundaries import CertifiedAdapterBinding
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.workflow.loaded_bundle import workflow_boundary_projection
from orchestrator.workflow_lisp.closed.frontend import TypedProgram, compile_typed_program
from orchestrator.workflow.run_ref import bundle_transport
from orchestrator.workflow.surface_ast import SurfaceContract


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "closed_program"
TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
BOUNDARIES = {
    "fetch": ExternalToolBinding(name="fetch", stable_command=("python", "probe.py"))
}


def _fixture(name: str, *, target: str = TARGET) -> str:
    return (FIXTURES / f"{name}.orc").read_text(encoding="utf-8").replace("TARGET", target)


def _install(tmp_path: Path, name: str, *, target: str = TARGET) -> Path:
    path = tmp_path / "cp" / f"{name}.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_fixture(name, target=target), encoding="utf-8")
    return path


def _error(path: Path, operation) -> tuple[str, Path, int, int]:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        operation()
    diagnostic = excinfo.value.diagnostics[0]
    return (
        diagnostic.code,
        Path(diagnostic.span.start.path),
        diagnostic.span.start.line,
        diagnostic.span.start.column,
    )


def test_a_program_the_flat_route_refuses_typechecks_into_a_typed_program(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch")

    typed = compile_typed_program(
        entry,
        entry_workflow="cp/loop_in_branch::run",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
    )

    assert isinstance(typed, TypedProgram)
    assert (typed.entry.definition.name, typed.target, sorted(typed.procedures)) == (
        "cp/loop_in_branch::run",
        TARGET,
        ["cp/loop_in_branch::fetch"],
    )


def test_evaluated_graph_result_has_no_lowered_workflows(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch")

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )

    assert (result.entry_result.lowered_workflows, result.entry_result.typed_program is not None) == (
        (),
        True,
    )


def test_typed_program_retains_procedure_specializations_and_owner_environments(
    tmp_path: Path,
) -> None:
    entry = _install(tmp_path, "if_in_hook")

    typed = compile_typed_program(
        entry,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
    )

    specializations = tuple(
        procedure
        for procedure in typed.procedures.values()
        if procedure.specialization is not None
    )
    assert len(specializations) == 1
    owner_module = specializations[0].specialization.base_name.split("::", 1)[0]
    assert owner_module in typed.module_type_envs
    assert (
        typed.procedure_type_env(specializations[0]).target_dsl_version
        == typed.module_type_envs[owner_module].target_dsl_version
    )


def test_evaluated_entry_skips_flat_lowering_for_its_whole_source_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_helper = _install(tmp_path, "loop_in_branch", target="2.34")
    old_source = old_helper.read_text(encoding="utf-8").replace("(export run)", "(export Box run)")
    old_helper.write_text(old_source, encoding="utf-8")
    entry = tmp_path / "cp" / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/loop_in_branch :as old :only (Box run))
  (export start)
  (defworkflow start ((go Bool)) -> Box
    (call old.run :go go)))
''',
        encoding="utf-8",
    )

    def refuse_lowering(**_kwargs):
        raise AssertionError("evaluated-entry graph reached flat lowering")

    monkeypatch.setattr("orchestrator.workflow_lisp.compiler._lower_workflows_for_route", refuse_lowering)
    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )

    assert all(not item.lowered_workflows and not item.validated_bundles for item in result.compiled_results_by_name.values())
    helper = result.compiled_results_by_name["cp/loop_in_branch"]
    assert helper.typed_workflows[0].definition.name == "cp/loop_in_branch::run"
    assert helper.typed_workflows[0].typed_body is not None
    assert helper.typed_workflows[0].effect_summary
    assert "cp/loop_in_branch::fetch" in helper.procedure_catalog.signatures_by_name
    typed = result.entry_result.typed_program
    private_callee = typed.procedures["cp/loop_in_branch::fetch"]
    assert typed.procedure_type_env(private_callee).target_dsl_version == (
        typed.module_type_envs["cp/loop_in_branch"].target_dsl_version
    )


def test_typed_program_keeps_each_module_externs_and_unused_bindings(
    tmp_path: Path,
) -> None:
    old_helper = _install(tmp_path, "loop_in_branch", target="2.34")
    old_source = old_helper.read_text(encoding="utf-8").replace(
        "(export run)", "(export Box run)"
    )
    old_helper.write_text(old_source, encoding="utf-8")
    entry = tmp_path / "cp" / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/loop_in_branch :as old :only (Box run))
  (export start)
  (defworkflow start ((go Bool)) -> Box (call old.run :go go)))
''',
        encoding="utf-8",
    )
    unused_boundary = ExternalToolBinding(
        name="unused",
        stable_command=("python", "unused.py"),
    )

    typed = compile_typed_program(
        entry,
        entry_workflow="start",
        source_roots=(tmp_path,),
        command_boundaries={**BOUNDARIES, "unused": unused_boundary},
        provider_externs={
            "providers.review": "review-provider",
            "providers.unused": "unused-provider",
        },
    )

    helper_externs = typed.module_externs["cp/loop_in_branch"]
    entry_externs = typed.module_externs["cp/entry"]
    assert helper_externs is not entry_externs
    assert helper_externs["providers.review"].provider_id == "review-provider"
    assert entry_externs["providers.review"].provider_id == "review-provider"
    assert typed.externs["providers.unused"].provider_id == "unused-provider"
    assert typed.configuration_bindings["provider_externs"]["providers.unused"] == (
        "unused-provider"
    )
    assert typed.configuration_bindings["command_boundaries"]["unused"] == unused_boundary
    assert "unused" in typed.command_boundaries


def test_old_entry_keeps_its_flat_route_refusal(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch", target="2.34")

    code, path, line, column = _error(
        entry,
        lambda: compile_stage3_entrypoint(
            entry,
            source_roots=(tmp_path,),
            command_boundaries=BOUNDARIES,
            validate_shared=True,
            workspace_root=tmp_path,
            lowering_route=None,
        ),
    )

    assert (code, path, line, column) == (
        "workflow_signature_mismatch",
        entry,
        17,
        28,
    )


def test_old_entry_cannot_import_an_evaluated_module(tmp_path: Path) -> None:
    entry = tmp_path / "cp" / "old_entry.orc"
    callee = tmp_path / "cp" / "new_callee.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/old_entry)
  (import cp/new_callee :only (run))
  (export start)
  (defworkflow start () -> Int (call run)))
''',
        encoding="utf-8",
    )
    callee.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/new_callee)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    code, path, line, _column = _error(
        entry,
        lambda: compile_stage3_entrypoint(entry, source_roots=(tmp_path,), validate_shared=True),
    )

    assert (code, path, line) == ("evaluated_execution_target_direction_invalid", entry, 5)


def test_old_helper_cannot_call_back_into_the_evaluated_graph(tmp_path: Path) -> None:
    entry = tmp_path / "cp" / "entry.orc"
    helper = tmp_path / "cp" / "helper.orc"
    callee = tmp_path / "cp" / "callee.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/helper :only (relay))
  (export start)
  (defworkflow start () -> Int (call relay)))
''',
        encoding="utf-8",
    )
    helper.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/helper)
  (import cp/callee :only (run))
  (export relay)
  (defworkflow relay () -> Int (call run)))
''',
        encoding="utf-8",
    )
    callee.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/callee)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    code, path, line, _column = _error(
        entry,
        lambda: compile_stage3_entrypoint(entry, source_roots=(tmp_path,), validate_shared=True),
    )

    assert (code, path, line) == ("evaluated_execution_target_direction_invalid", helper, 5)


def test_explicit_new_snapshot_is_refused_only_when_an_old_procedure_calls_it(
    tmp_path: Path,
) -> None:
    producer = tmp_path / "producer.orc"
    producer.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule producer)
  (export get)
  (defrecord Box (n Int))
  (defworkflow get ((input Box)) -> Box input))
''',
        encoding="utf-8",
    )
    typed_producer = compile_typed_program(
        producer,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    helper = tmp_path / "old.orc"
    helper.write_text(
        '''
(workflow-lisp (:language "0.1") (:target-dsl "2.34") (defmodule old)
  (export Box invoke) (defrecord Box (n Int))
  (defproc invoke ((runner WorkflowRef[Box -> Box]) (input Box)) -> Box
    :effects ((calls-workflow runner)) :lowering inline (call runner :input input)))
''',
        encoding="utf-8",
    )
    main = tmp_path / "main.orc"
    main.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule main)
  (import old :only (Box invoke))
  (export run)
  (defworkflow run ((input Box)) -> Box input))
''',
        encoding="utf-8",
    )

    unused_alias = compile_typed_program(
        main,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_programs={"dep": typed_producer},
    )
    assert unused_alias.entry.definition.name == "main::run"

    main.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule main)
  (import old :only (Box invoke))
  (export run)
  (defworkflow run ((input Box)) -> Box
    (invoke (workflow-ref dep) input)))
''',
        encoding="utf-8",
    )
    code, path, line, _column = _error(
        main,
        lambda: compile_typed_program(
            main,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": typed_producer},
        ),
    )

    assert (code, path, line) == (
        "evaluated_execution_target_direction_invalid",
        helper,
        5,
    )


def test_typechecker_diagnostic_is_unchanged_at_the_new_target(tmp_path: Path) -> None:
    entry = tmp_path / "cp" / "bad.orc"
    entry.parent.mkdir(parents=True)

    def compile_at(target: str):
        entry.write_text(
            f'''(workflow-lisp
      (:language "0.1")
      (:target-dsl "{target}")
      (defmodule cp/bad)
      (export run)
      (defrecord Broken (value Missing))
      (defworkflow run ((input Broken)) -> Broken input))
''',
            encoding="utf-8",
        )
        return _error(
            entry,
            lambda: compile_stage3_entrypoint(entry, source_roots=(tmp_path,), validate_shared=True),
        )

    old = compile_at("2.34")
    new = compile_at(TARGET)

    assert old[0] == new[0] == "type_unknown"
    assert (old[2], old[3]) == (new[2], new[3])


def test_typed_entry_refuses_a_pre_evaluated_target_at_its_header(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch", target="2.34")

    code, path, line, _column = _error(
        entry,
        lambda: compile_typed_program(
            entry,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries=BOUNDARIES,
        ),
    )

    assert (code, path, line) == ("evaluated_execution_target_required", entry, 3)


def test_typed_entry_accepts_short_and_canonical_names_and_a_fixed_standalone_namespace(
    tmp_path: Path,
) -> None:
    entry = _install(tmp_path / "moduled", "loop_in_branch")
    short = compile_typed_program(
        entry,
        entry_workflow="run",
        source_roots=(tmp_path / "moduled",),
        command_boundaries=BOUNDARIES,
    )
    canonical = compile_typed_program(
        entry,
        entry_workflow="cp/loop_in_branch::run",
        source_roots=(tmp_path / "moduled",),
        command_boundaries=BOUNDARIES,
    )

    standalone = tmp_path / "standalone.orc"
    standalone.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )
    standalone_typed = compile_typed_program(
        standalone,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )

    assert short.entry.definition.name == canonical.entry.definition.name == "cp/loop_in_branch::run"
    assert standalone_typed.entry.definition.name == "entry::run"


def test_typed_entry_rejects_an_unknown_name_at_the_entry_source(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch")

    code, path, line, column = _error(
        entry,
        lambda: compile_typed_program(
            entry,
            entry_workflow="missing",
            source_roots=(tmp_path,),
            command_boundaries=BOUNDARIES,
        ),
    )

    assert (code, path, line, column) == ("entry_workflow_unknown", entry, 1, 1)


def test_typed_entry_selection_stays_within_the_entry_module(tmp_path: Path) -> None:
    helper = tmp_path / "cp" / "helper.orc"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/helper)
  (export helper)
  (defworkflow helper () -> Int 1))
''',
        encoding="utf-8",
    )
    entry = tmp_path / "cp" / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/helper :as h :only (helper))
  (export start)
  (defworkflow private () -> Int 2)
  (defworkflow start () -> Int 3))
''',
        encoding="utf-8",
    )

    private = compile_typed_program(
        entry,
        entry_workflow="cp/entry::private",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    assert private.entry.definition.name == "cp/entry::private"

    code, path, line, column = _error(
        entry,
        lambda: compile_typed_program(
            entry,
            entry_workflow="cp/helper::helper",
            source_roots=(tmp_path,),
            command_boundaries={},
        ),
    )

    assert (code, path, line, column) == ("entry_workflow_unknown", entry, 1, 1)


def test_imported_snapshots_with_conflicting_context_are_refused(tmp_path: Path) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/producer)
  (export get)
  (defworkflow get ((value Int)) -> Int value))
''',
        encoding="utf-8",
    )
    first = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    second = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={
            "unused": ExternalToolBinding(
                name="unused",
                stable_command=("python", "changed.py"),
            )
        },
    )
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"first": first, "second": second},
        ),
    )

    assert code == "compiled_workflow_snapshot_conflict"
    assert path == producer_path


def test_imported_snapshots_can_select_different_exports_from_one_context(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/producer)
  (export get other)
  (defworkflow get ((value Int)) -> Int value)
  (defworkflow other ((flag Bool)) -> Bool flag))
''',
        encoding="utf-8",
    )
    get = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    other = compile_typed_program(
        producer_path,
        entry_workflow="other",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_programs={"number": get, "flag": other},
    )

    assert consumer.imported_programs == {"number": get, "flag": other}


def test_old_entry_keeps_compiling_when_imported_snapshots_conflict(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "producer.orc"
    bundles = []
    for value in (1, 2):
        producer_path.write_text(
            f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule producer)
  (export get)
  (defworkflow get () -> Int {value}))
''',
            encoding="utf-8",
        )
        result = compile_stage3_entrypoint(
            producer_path,
            source_roots=(tmp_path,),
            validate_shared=True,
            workspace_root=tmp_path,
        )
        bundles.append(result.validated_bundles_by_name["producer::get"])

    parent_path = tmp_path / "parent.orc"
    parent_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule parent)
  (export run)
  (defworkflow run () -> Int (call one)))
''',
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        parent_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
        imported_workflow_bundles={"one": bundles[0], "two": bundles[1]},
    )

    assert "parent::run" in result.validated_bundles_by_name
    assert result.entry_result.typed_program is None


@pytest.mark.parametrize(
    "partial_workflow", ["missing_body", "missing_definition", "missing_env"]
)
def test_partial_non_entry_workflow_prevents_snapshot_admission(
    tmp_path: Path, partial_workflow: str,
) -> None:
    producer_path = tmp_path / "child.orc"
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule child)
  (export run)
  (defworkflow helper ((value Int)) -> Int value)
  (defworkflow run ((value Int)) -> Int (call helper :value value)))
''',
        encoding="utf-8",
    )
    producer = compile_typed_program(
        producer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    workflows = dict(producer.workflows)
    if partial_workflow == "missing_body":
        workflows["child::helper"] = replace(
            workflows["child::helper"],
            typed_body=None,
        )
    elif partial_workflow == "missing_definition":
        del workflows["child::helper"]
    else:
        workflow_type_envs = dict(producer.workflow_type_envs)
        del workflow_type_envs["child::helper"]
        partial = replace(
            producer,
            workflows=workflows,
            workflow_type_envs=workflow_type_envs,
        )
    if partial_workflow != "missing_env":
        partial = replace(producer, workflows=workflows)

    consumer_path = tmp_path / "parent.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule parent)
  (export run)
  (defworkflow run ((value Int)) -> Int (call dep :value value)))
''',
        encoding="utf-8",
    )
    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": partial},
        ),
    )

    assert code == "compiled_workflow_source_required"
    assert path == producer_path


@pytest.mark.parametrize("depth", (1, 2, 3))
def test_incomplete_transitive_program_snapshot_is_locally_refused(
    tmp_path: Path,
    depth: int,
) -> None:
    producer_path = tmp_path / "producer.orc"
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule producer)
  (export get)
  (defworkflow get () -> Int 1))
''',
        encoding="utf-8",
    )
    producer = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    incomplete = replace(producer, imported_programs={"missing": None})
    for _ in range(depth - 1):
        incomplete = replace(producer, imported_programs={"nested": incomplete})
    consumer_path = tmp_path / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": incomplete},
        ),
    )

    assert code == "compiled_workflow_source_required"
    assert path == producer_path


@pytest.mark.parametrize("edit_source", [False, True])
def test_imported_snapshot_must_match_an_overlapping_source_graph(
    tmp_path: Path, edit_source: bool,
) -> None:
    producer_path = tmp_path / "cp" / "shared.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/shared)
  (export get)
  (defworkflow get ((value Int)) -> Int value))
''',
        encoding="utf-8",
    )
    snapshot = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    if edit_source:
        producer_path.write_bytes(producer_path.read_bytes() + b"\n; changed source revision\n")
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (import cp/shared :as source :only (get))
  (export run)
  (defworkflow run () -> Int (call dep :value 1)))
''',
        encoding="utf-8",
    )

    if not edit_source:
        compiled = compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": snapshot},
        )
        assert compiled.entry.definition.name == "cp/consumer::run"
        return

    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": snapshot},
        ),
    )

    assert (code, path) == ("compiled_workflow_snapshot_conflict", producer_path)


def test_source_digests_use_consumed_import_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _install(tmp_path, "loop_in_branch", target="2.34")
    helper_source = helper.read_bytes()
    helper_source_text = helper_source.decode("utf-8").replace("(export run)", "(export Box run)")
    helper.write_text(helper_source_text, encoding="utf-8")
    entry = tmp_path / "cp" / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/loop_in_branch :as old :only (Box run))
  (export start)
  (defworkflow start ((go Bool)) -> Box
    (call old.run :go go)))
''',
        encoding="utf-8",
    )
    trace = SourceReadTrace()
    original = compile_stage3_entrypoint
    changed = False

    def compile_then_edit(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            helper.write_bytes(helper.read_bytes() + b"\n; changed after compile\n")
            changed = True
        return result

    monkeypatch.setattr("orchestrator.workflow_lisp.compiler.compile_stage3_entrypoint", compile_then_edit)
    typed = compile_typed_program(
        entry,
        entry_workflow="start",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        source_read_trace=trace,
    )
    monkeypatch.setattr("orchestrator.workflow_lisp.compiler.compile_stage3_entrypoint", original)
    fresh = compile_typed_program(
        entry,
        entry_workflow="start",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
    )

    assert typed.source_file_digests["cp/loop_in_branch"] == hashlib.sha256(helper_source_text.encode()).hexdigest()
    assert fresh.source_file_digests["cp/loop_in_branch"] == hashlib.sha256(helper.read_bytes()).hexdigest()
    assert typed.source_file_digests["cp/loop_in_branch"] != fresh.source_file_digests["cp/loop_in_branch"]


def test_local_definition_keys_ignore_paths_positions_and_pure_bindings(tmp_path: Path) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/local)
  (export run)
  (defproc apply-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int :effects () :lowering inline (hook value))
  (defworkflow run ((choice Bool) (input Int)) -> Int
    (if choice
      (let-proc (increment ((value Int)) -> Int :captures () (+ value 1))
        (apply-int (proc-ref increment) input))
      (let-proc (increment ((value Int)) -> Int :captures () (+ value 2))
        (apply-int (proc-ref increment) input)))))
'''
    changed = source.replace(
        "  (defworkflow run ((choice Bool) (input Int)) -> Int\n",
        "  (defworkflow run ((choice Bool) (input Int)) -> Int\n    (let* ((unused 0))\n",
    )
    changed = changed.replace(
        "        (apply-int (proc-ref increment) input)))))\n",
        "        (apply-int (proc-ref increment) input))))))\n",
    )
    first = tmp_path / "first" / "cp" / "local.orc"
    second = tmp_path / "elsewhere" / "cp" / "local.orc"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text(source, encoding="utf-8")
    second.write_text(changed, encoding="utf-8")

    first_typed = compile_typed_program(
        first,
        entry_workflow="run",
        source_roots=(first.parent.parent,),
        command_boundaries={},
    )
    second_typed = compile_typed_program(
        second,
        entry_workflow="run",
        source_roots=(second.parent.parent,),
        command_boundaries={},
    )

    first_keys = tuple(sorted(first_typed.local_definition_keys.values()))
    second_keys = tuple(sorted(second_typed.local_definition_keys.values()))
    assert len(first_keys) == 2
    assert first_keys == second_keys
    assert {key[0] for key in first_keys} == {"cp/local::run"}
    assert {key[2] for key in first_keys} == {0, 1}


def test_macro_expansion_local_identity_is_scoped_to_its_callable(tmp_path: Path) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule sample)
  (export run)
  (defproc apply-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int :effects () :lowering inline (hook value))
  (defmacro invoke (value)
    (let-proc (increment ((arg Int)) -> Int :captures () (+ arg 1))
      (apply-int (proc-ref increment) value)))
  (defworkflow run ((input Int)) -> Int (invoke input)))
'''
    with_other = source.rstrip()[:-1] + '''
  (defworkflow other ((input Int)) -> Int
    (if true (invoke input) (invoke input))))
'''
    path = tmp_path / "sample.orc"
    path.write_text(source, encoding="utf-8")

    def compile_current():
        return compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
        )

    first = compile_current()
    path.write_text(with_other, encoding="utf-8")
    second = compile_current()

    first_run_keys = tuple(
        key for key in first.local_definition_keys.values() if key[0] == "sample::run"
    )
    second_run_keys = tuple(
        key for key in second.local_definition_keys.values() if key[0] == "sample::run"
    )
    assert first_run_keys
    assert first_run_keys == second_run_keys


def test_old_source_producer_retains_typed_snapshot_on_result_and_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = tmp_path / "cp" / "producer.orc"
    entry.parent.mkdir(parents=True)
    source = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get)
  (defproc private-inc ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defworkflow get ((n Int)) -> Int (private-inc n)))
    '''
    entry.write_text(source, encoding="utf-8")
    caller_boundaries = {
        "original": ExternalToolBinding(
            name="original",
            stable_command=("python", "original.py"),
        )
    }
    lower_calls = []
    shared_calls = []
    executable_calls = []
    original_lower = compiler_module._lower_workflows_for_route
    original_validate = compiler_module.validate_lowered_workflows
    original_revalidate = compiler_module._revalidate_stage3_executable_bundles
    original_attach = compiler_module._attach_typed_programs_to_source_bundles
    pre_attachment_catalog = {}

    def lower_spy(*args, **kwargs):
        lower_calls.append(kwargs.get("target_dsl_version"))
        return original_lower(*args, **kwargs)

    def validation_spy(*args, **kwargs):
        shared_calls.append(kwargs.get("validation_profile"))
        return original_validate(*args, **kwargs)

    def executable_spy(*args, **kwargs):
        executable_calls.append(True)
        return original_revalidate(*args, **kwargs)

    def attach_spy(bundles_by_name, typed_program):
        pre_attachment_catalog.update(bundles_by_name)
        return original_attach(bundles_by_name, typed_program)

    monkeypatch.setattr(compiler_module, "_lower_workflows_for_route", lower_spy)
    monkeypatch.setattr(compiler_module, "validate_lowered_workflows", validation_spy)
    monkeypatch.setattr(
        compiler_module,
        "_revalidate_stage3_executable_bundles",
        executable_spy,
    )
    monkeypatch.setattr(
        compiler_module,
        "_attach_typed_programs_to_source_bundles",
        attach_spy,
    )

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        command_boundaries=caller_boundaries,
        validate_shared=True,
        workspace_root=tmp_path,
    )

    snapshot = result.entry_result.typed_program
    assert isinstance(snapshot, TypedProgram)
    assert snapshot.entry is None
    assert "cp/producer::private-inc" in snapshot.procedures
    caller_boundaries["later"] = ExternalToolBinding(
        name="later",
        stable_command=("python", "later.py"),
    )
    retained_boundaries = snapshot.configuration_bindings["command_boundaries"]
    assert tuple(retained_boundaries) == ("original",)
    with pytest.raises(TypeError):
        retained_boundaries["mutate"] = caller_boundaries["original"]
    bundle = result.validated_bundles_by_name["cp/producer::get"]
    assert result.entry_result.validated_bundles["cp/producer::get"] is bundle
    assert result.entry_result.validation_profile is not None
    assert lower_calls == ["2.34"]
    assert shared_calls
    assert executable_calls
    assert result.compiled_results_by_name["cp/producer"].validated_bundles[
        "cp/producer::get"
    ] is bundle
    assert bundle.typed_program.entry.definition.name == "cp/producer::get"
    assert bundle.typed_program.procedures["cp/producer::private-inc"].typed_body is not None
    assert bundle.typed_program.source_file_digests["cp/producer"] == hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()
    kwargs = {
        "target_workflow_names": (bundle.surface.name,),
        "closure": (
            bundle_transport.BundleCapsuleClosureBlob(
                path=entry.name,
                roles=("orc",),
                payload=source.encode("utf-8"),
            ),
        ),
        "workflow_closure_paths": {bundle.surface.name: entry.name},
        "compiler_runtime_identity_digest": "sha256:" + "c" * 64,
        "lowering_schema_version": 2,
    }
    encoded_before_attachment = bundle_transport.encode_bundle_capsule(
        pre_attachment_catalog, **kwargs
    )
    encoded_after_attachment = bundle_transport.encode_bundle_capsule(
        result.validated_bundles_by_name, **kwargs
    )
    assert encoded_before_attachment == encoded_after_attachment


def test_typed_snapshot_copies_certified_adapter_configuration(
    tmp_path: Path,
) -> None:
    entry = tmp_path / "cp" / "producer.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get)
  (defworkflow get ((n Int)) -> Int n))
''',
        encoding="utf-8",
    )
    input_contract = {"required": ["before"]}
    path_safety = {"kind": "workspace_relpath"}
    adapter = CertifiedAdapterBinding(
        name="adapter",
        stable_command=("python", "adapter.py"),
        input_contract=input_contract,
        output_type_name="Int",
        effects=("structured_result",),
        path_safety=path_safety,
        source_map_behavior="step",
        fixture_ids=("adapter_ok",),
        negative_fixture_ids=("adapter_bad",),
    )

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        command_boundaries={"adapter": adapter},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    snapshot = result.entry_result.typed_program
    assert isinstance(snapshot, TypedProgram)
    retained = snapshot.command_boundaries["adapter"]
    retained_config = snapshot.configuration_bindings["command_boundaries"]["adapter"]
    assert retained is not adapter
    assert retained_config is not adapter
    input_contract["required"].append("after")
    path_safety["kind"] = "unrestricted"
    assert retained.input_contract["required"] == ("before",)
    assert retained.path_safety["kind"] == "workspace_relpath"
    assert retained_config.input_contract["required"] == ("before",)
    assert retained_config.path_safety["kind"] == "workspace_relpath"


def test_typed_program_can_import_an_explicit_source_snapshot(tmp_path: Path) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get)
  (defproc private-inc ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defworkflow get ((n Int)) -> Int (private-inc n)))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    producer_snapshot = producer.validated_bundles_by_name[
        "cp/producer::get"
    ].typed_program
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run ((n Int)) -> Int (call dep :n n)))
''',
        encoding="utf-8",
    )

    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        imported_programs={"dep": producer_snapshot},
    )

    assert consumer.entry.definition.name == "cp/consumer::run"
    assert consumer.imported_programs["dep"] is producer_snapshot
    assert consumer.module_workflow_signatures["cp/consumer"]["dep"].params[0][0] == "n"
    assert "cp/producer::private-inc" in consumer.procedures


def test_evaluated_consumer_requires_a_matching_bundle_snapshot(tmp_path: Path) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get other)
  (defworkflow get ((n Int)) -> Int n)
  (defworkflow other ((flag Bool)) -> Bool flag))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    get_bundle = producer.validated_bundles_by_name["cp/producer::get"]
    other_bundle = producer.validated_bundles_by_name["cp/producer::other"]
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run ((n Int)) -> Int (call dep :n n)))
''',
        encoding="utf-8",
    )

    def compile_bundle(bundle):
        return compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries=BOUNDARIES,
            imported_workflow_bundles={"dep": bundle},
        )

    compiled = compile_bundle(get_bundle)
    assert compiled.imported_programs["dep"] is get_bundle.typed_program
    assert "cp/producer::get" in compiled.workflows
    assert "cp/producer" in compiled.module_type_envs
    assert "cp/producer" not in compiled.source_file_digests

    decoded_bundle = replace(get_bundle, typed_program=None)
    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_bundle(decoded_bundle),
    )
    assert code == "compiled_workflow_source_required"
    assert path == Path(get_bundle.provenance.workflow_path)

    restored = replace(decoded_bundle, typed_program=get_bundle.typed_program)
    assert compile_bundle(restored).entry.definition.name == "cp/consumer::run"
    producer_path.unlink()
    assert compile_bundle(restored).entry.definition.name == "cp/consumer::run"

    wrong_pair = replace(decoded_bundle, typed_program=other_bundle.typed_program)
    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_bundle(wrong_pair),
    )
    assert code == "compiled_workflow_source_required"
    assert path == Path(get_bundle.provenance.workflow_path)


def test_bundle_snapshot_contract_survives_deleted_nested_nominal_sources(
    tmp_path: Path,
) -> None:
    types_path = tmp_path / "types.orc"
    types_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule types)
  (export Outer)
  (defrecord Inner (x Int))
  (defrecord Outer (inner Inner)))
''',
        encoding="utf-8",
    )
    producer_path = tmp_path / "child.orc"
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule child)
  (import types)
  (export get)
  (defworkflow get ((rows List[types/Outer])) -> Int 1))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = producer.validated_bundles_by_name["child::get"]
    assert compiler_module._typed_program_matches_bundle(bundle.typed_program, bundle)
    types_path.unlink()
    producer_path.unlink()

    consumer_path = tmp_path / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )
    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_workflow_bundles={"dep": bundle},
        ),
    )

    assert (code, path) == ("workflow_call_signature_erased", producer_path)


def test_typed_product_preserves_grouped_inputs_and_defaults(tmp_path: Path) -> None:
    producer_path = tmp_path / "producer.orc"
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule producer)
  (export get)
  (defrecord Pair (left Int) (right Int))
  (defworkflow get ((a Pair) (count Int :default 3)) -> Int count))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = producer.validated_bundles_by_name["producer::get"]

    consumer_path = tmp_path / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer)
  (export run)
  (defrecord Pair (left Int) (right Int))
  (defworkflow run ((pair Pair)) -> Int (call dep :a pair)))
''',
        encoding="utf-8",
    )
    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_workflow_bundles={"dep": bundle},
    )

    imported_signature = consumer.module_workflow_signatures["consumer"]["dep"]
    assert [(name, type_ref.name) for name, type_ref in imported_signature.params] == [
        ("a", "Pair"),
        ("count", "Int"),
    ]
    assert imported_signature.param_defaults["count"].datum == 3
    assert imported_signature.hidden_context_requirements == bundle.typed_program.entry.signature.hidden_context_requirements
    assert imported_signature.private_compatibility_bridge_types == bundle.typed_program.entry.signature.private_compatibility_bridge_types


def test_typed_product_groups_private_context_by_its_source_formal(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "producer.orc"
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule producer)
  (import std/phase :only (with-phase))
  (export entry run-phase)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord Pair (x String) (y String))
  (defrecord Result (label String) (phase_name Symbol))
  (defworkflow entry
    ((pair Pair))
    -> Result
    (call run-phase :a__x pair.x :a__y pair.y))
  (defworkflow run-phase
    ((phase__ctx PhaseCtx)
     (a__x String)
     (a__y String))
    -> Result
    (with-phase phase__ctx plan-gate-wrapper
      (record Result
        :label a__x
        :phase_name phase__ctx.phase-name))))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = producer.validated_bundles_by_name["producer::run-phase"]
    native_signature = bundle.typed_program.entry.signature
    assert compiler_module._typed_program_matches_bundle(bundle.typed_program, bundle)
    assert set(native_signature.hidden_context_requirements) == {"phase__ctx"}
    private_bindings = workflow_boundary_projection(bundle).private_runtime_context_bindings
    assert len(private_bindings) == 1
    assert private_bindings[0].source_param_name == "phase__ctx"
    changed_provenance = replace(
        private_bindings[0],
        source_provenance={"workflow_name": "other-owner", "path": "/other/source.orc"},
    )
    provenance_bundle = replace(
        bundle,
        provenance=replace(
            bundle.provenance,
            private_exec_context_bindings=(changed_provenance,),
        ),
    )
    assert compiler_module._typed_program_matches_bundle(
        bundle.typed_program,
        provenance_bundle,
    )
    changed_source = replace(private_bindings[0], source_param_name="other-context")
    source_bundle = replace(
        bundle,
        provenance=replace(
            bundle.provenance,
            private_exec_context_bindings=(changed_source,),
        ),
    )
    assert not compiler_module._typed_program_matches_bundle(
        bundle.typed_program,
        source_bundle,
    )

    consumer_path = tmp_path / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer)
  (export run)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord Pair (x String) (y String))
  (defrecord Result (label String) (phase_name Symbol))
  (defworkflow run
    ((phase__ctx PhaseCtx)
     (pair Pair))
    -> Result
    (call dep :phase__ctx phase__ctx :a pair)))
''',
        encoding="utf-8",
    )
    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_workflow_bundles={"dep": bundle},
    )

    imported_signature = consumer.module_workflow_signatures["consumer"]["dep"]
    assert [(name, type_ref.name) for name, type_ref in imported_signature.params] == [
        ("a", "Pair"),
        ("phase__ctx", "PhaseCtx"),
    ]
    bundle_requirement = imported_signature.hidden_context_requirements["phase__ctx"]
    assert (bundle_requirement.binding_kind, bundle_requirement.allows_entry_bootstrap) == (
        "derived_private_child_context",
        True,
    )

    typed_consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_programs={"dep": bundle.typed_program},
    )
    typed_signature = typed_consumer.module_workflow_signatures["consumer"]["dep"]
    assert [(name, type_ref.name) for name, type_ref in typed_signature.params] == [
        ("a", "Pair"),
        ("phase__ctx", "PhaseCtx"),
    ]
    assert typed_signature.hidden_context_requirements == (
        native_signature.hidden_context_requirements
    )


def test_source_snapshot_boundary_capture_rejects_projection_changes(
    tmp_path: Path,
) -> None:
    entry = tmp_path / "cp" / "union.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/union)
  (export run)
  (defunion Outcome (OK (value Int)) (NOPE (reason String)))
  (defworkflow run ((flag Bool)) -> Outcome
    (if flag
      (variant Outcome OK :value 1)
      (variant Outcome NOPE :reason "no"))))
''',
        encoding="utf-8",
    )
    result = compile_stage3_module(
        entry,
        entry_workflow="run",
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles["run"]
    retained = bundle.typed_program._compiled_bundle_boundaries["run"]
    assert compiler_module._typed_program_matches_bundle(bundle.typed_program, bundle)
    assert "projection" in retained[1]["return__variant"]
    with pytest.raises(TypeError):
        retained[1]["return__variant"]["projection"]["return_kind"] = "record"

    original = bundle.surface.outputs["return__variant"]
    changed_definition = dict(original.definition)
    changed_projection = dict(changed_definition["projection"])
    changed_projection["active_variants"] = ("NOPE",)
    changed_definition["projection"] = changed_projection
    changed_surface = replace(
        bundle.surface,
        outputs={
            **bundle.surface.outputs,
            "return__variant": SurfaceContract(
                name=original.name,
                kind=original.kind,
                value_type=original.value_type,
                definition=changed_definition,
                from_ref=original.from_ref,
            ),
        },
    )
    changed_bundle = replace(bundle, surface=changed_surface)
    assert not compiler_module._typed_program_matches_bundle(
        bundle.typed_program,
        changed_bundle,
    )


@pytest.mark.parametrize("supply_trace", (True, False))
def test_standalone_old_source_producer_retains_snapshot_and_passes_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supply_trace: bool,
) -> None:
    entry = tmp_path / "producer.orc"
    source = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defproc private-inc ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defworkflow get ((n Int)) -> Int (private-inc n)))
'''
    entry.write_text(source, encoding="utf-8")
    supplied_trace = SourceReadTrace() if supply_trace else None
    seen_traces = []
    original_detector = compiler_module._syntax_module_uses_module_graph
    original_pipeline = compiler_module._run_stage3_validation_pipeline
    lowered_targets = []
    original_lowerer = compiler_module._lower_workflows_for_route

    def trace_detector(path: Path, *, source_read_trace: SourceReadTrace | None = None):
        seen_traces.append(source_read_trace)
        return original_detector(path, source_read_trace=source_read_trace)

    def compile_then_delete(*args, **kwargs):
        result = original_pipeline(*args, **kwargs)
        entry.unlink()
        return result

    def traced_lowerer(*args, **kwargs):
        lowered_targets.append(kwargs["target_dsl_version"])
        return original_lowerer(*args, **kwargs)

    monkeypatch.setattr(
        compiler_module,
        "_syntax_module_uses_module_graph",
        trace_detector,
    )
    monkeypatch.setattr(
        compiler_module,
        "_run_stage3_validation_pipeline",
        compile_then_delete,
    )
    monkeypatch.setattr(
        compiler_module,
        "_lower_workflows_for_route",
        traced_lowerer,
    )
    result = compile_stage3_module(
        entry,
        validate_shared=True,
        workspace_root=tmp_path,
        source_read_trace=supplied_trace,
    )

    snapshot = result.typed_program
    assert isinstance(snapshot, TypedProgram)
    assert snapshot.entry is None
    assert result.module.module_name is None
    assert "get" in snapshot.workflows
    assert "private-inc" in snapshot.procedures
    assert len(seen_traces) == 1
    assert isinstance(seen_traces[0], SourceReadTrace)
    if supplied_trace is not None:
        assert seen_traces[0] is supplied_trace
    trace = seen_traces[0]
    assert trace.records
    assert not entry.exists()
    assert snapshot.source_file_digests["producer"] == hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()
    assert "get" in result.validated_bundles
    assert lowered_targets == ["2.34"]


@pytest.mark.parametrize(
    ("module_name", "expected_module"),
    ((None, "entry"), ("producer", "producer")),
)
def test_standalone_evaluated_source_producer_keeps_canonical_namespace(
    tmp_path: Path,
    module_name: str | None,
    expected_module: str,
) -> None:
    entry = tmp_path / (
        "path_specific_name.orc" if module_name is None else "producer.orc"
    )
    module_declaration = (
        "" if module_name is None else "  (defmodule producer)\n  (export run)\n"
    )
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
{module_declaration}  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    result = compile_stage3_module(entry)

    assert result.module.module_name == expected_module
    assert result.typed_program.entry_module == expected_module
    assert tuple(result.typed_program.workflows) == (f"{expected_module}::run",)
    assert result.lowered_workflows == ()


def test_graph_source_producer_passes_one_trace_through_delegation_and_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = tmp_path / "cp" / "entry.orc"
    child = tmp_path / "cp" / "child.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/entry)
  (import cp/child :only (inc))
  (export run)
  (defworkflow run ((n Int)) -> Int (call inc :n n)))
''',
        encoding="utf-8",
    )
    child.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/child)
  (export inc)
  (defworkflow inc ((n Int)) -> Int (+ n 1)))
''',
        encoding="utf-8",
    )
    supplied_trace = SourceReadTrace()
    delegated_traces = []
    recorded_traces = []
    lowered_targets = []
    original_entrypoint = compiler_module.compile_stage3_entrypoint
    original_record = SourceReadTrace._record
    original_lowerer = compiler_module._lower_workflows_for_route

    def delegated_entrypoint(*args, **kwargs):
        delegated_traces.append(kwargs["source_read_trace"])
        return original_entrypoint(*args, **kwargs)

    def observed_record(trace, **kwargs):
        recorded_traces.append(trace)
        return original_record(trace, **kwargs)

    def observed_lowerer(*args, **kwargs):
        lowered_targets.append(kwargs["target_dsl_version"])
        return original_lowerer(*args, **kwargs)

    monkeypatch.setattr(
        compiler_module,
        "compile_stage3_entrypoint",
        delegated_entrypoint,
    )
    monkeypatch.setattr(SourceReadTrace, "_record", observed_record)
    monkeypatch.setattr(
        compiler_module,
        "_lower_workflows_for_route",
        observed_lowerer,
    )
    result = compile_stage3_module(
        entry,
        entry_workflow="run",
        validate_shared=True,
        workspace_root=tmp_path,
        source_read_trace=supplied_trace,
    )

    assert result.typed_program is not None
    assert delegated_traces == [supplied_trace]
    assert recorded_traces
    assert all(trace is supplied_trace for trace in recorded_traces)
    assert len(lowered_targets) == 2
    assert set(lowered_targets) == {"2.34"}


def test_graph_source_producer_rejects_conflicting_repeated_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = tmp_path / "cp" / "entry.orc"
    child = tmp_path / "cp" / "child.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/entry)
  (import cp/child :only (inc))
  (export run)
  (defworkflow run ((n Int)) -> Int (call inc :n n)))
''',
        encoding="utf-8",
    )
    child.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/child)
  (export inc)
  (defworkflow inc ((n Int)) -> Int (+ n 1)))
''',
        encoding="utf-8",
    )
    original_read_bytes = Path.read_bytes
    child_reads = 0

    def change_second_child_read(path: Path) -> bytes:
        nonlocal child_reads
        content = original_read_bytes(path)
        if path.resolve() == child.resolve():
            child_reads += 1
            if child_reads == 2:
                return content + b"\n; source changed during compilation\n"
        return content

    monkeypatch.setattr(Path, "read_bytes", change_second_child_read)
    trace = SourceReadTrace()
    with pytest.raises(RuntimeError):
        compile_stage3_module(
            entry,
            entry_workflow="run",
            validate_shared=True,
            workspace_root=tmp_path,
            source_read_trace=trace,
        )

    assert child_reads == 2
    assert trace.revision_conflict_paths == (child.resolve(),)


def test_old_source_compilation_preserves_opaque_import_without_claiming_full_snapshot(
    tmp_path: Path,
) -> None:
    child_path = tmp_path / "cp" / "child.orc"
    child_path.parent.mkdir(parents=True)
    child_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/child)
  (export inc)
  (defworkflow inc ((n Int)) -> Int (+ n 1)))
''',
        encoding="utf-8",
    )
    child_result = compile_stage3_entrypoint(
        child_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    opaque_child = replace(
        child_result.validated_bundles_by_name["cp/child::inc"],
        typed_program=None,
    )
    caller_path = tmp_path / "cp" / "caller.orc"
    caller_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/caller)
  (export run)
  (defworkflow run ((n Int)) -> Int (call dep :n n)))
''',
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        caller_path,
        source_roots=(tmp_path,),
        imported_workflow_bundles={"dep": opaque_child},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.entry_result.typed_program is None
    assert result.entry_result.lowered_workflows
    assert "cp/caller::run" in result.validated_bundles_by_name


def test_standalone_old_source_compilation_withholds_conflicting_snapshot(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "producer.orc"
    producer_bundles = []
    for value in (1, 2):
        producer_path.write_text(
            f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule producer)
  (export get)
  (defworkflow get () -> Int {value}))
''',
            encoding="utf-8",
        )
        producer = compile_stage3_entrypoint(
            producer_path,
            source_roots=(tmp_path,),
            validate_shared=True,
            workspace_root=tmp_path,
        )
        producer_bundles.append(
            producer.validated_bundles_by_name["producer::get"]
        )

    caller_path = tmp_path / "caller.orc"
    caller_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule caller)
  (export run)
  (defworkflow run () -> Int (call first)))
''',
        encoding="utf-8",
    )
    result = compile_stage3_module(
        caller_path,
        imported_workflow_bundles={
            "first": producer_bundles[0],
            "second": producer_bundles[1],
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.typed_program is None
    assert result.lowered_workflows
    assert "run" in result.validated_bundles
