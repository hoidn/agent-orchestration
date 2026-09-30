from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.workflow_lisp.closed.frontend import TypedProgram, compile_typed_program


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
