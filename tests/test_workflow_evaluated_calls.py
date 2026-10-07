from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import PromptExtern
from tests.workflow_lisp_closed_program_helpers import TARGET, install


@pytest.mark.parametrize("imported", (False, True))
def test_public_generic_hooks_keep_distinct_types_and_once_only_calls(tmp_path, monkeypatch, imported):
    from tests.workflow_evaluated_context_helpers import pure_files, pause_context, assert_generic_hook_run
    from tests.workflow_evaluated_totality_helpers import checked_run, compile_public
    from tests.test_workflow_evaluated_resume import _resume_cli

    declarations = '''(defproc integer () -> Int :effects ((uses-command fetch)) :lowering inline
      (command-result fetch :argv ("python" "hooks.py" "integer") :returns Int))
      (defproc text () -> String :effects ((uses-command fetch)) :lowering inline
        (command-result fetch :argv ("python" "hooks.py" "text") :returns String))
      (defproc apply :forall (T) ((hook ProcRef[() -> T])) -> T
        :effects () :lowering inline (hook))'''
    imports = "(import hooks/producer :as old)" if imported else ""
    prefix = "old." if imported else ""
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule hooks/entry) {imports} (export run)
      {"" if imported else declarations}
      (defmacro invoke (hook) ({prefix}apply (proc-ref hook)))
      (defworkflow run () -> String
        (let* ((number (invoke {prefix}integer)) (answer (invoke {prefix}text))) answer)))'''
    files, inputs = pure_files(tmp_path, source, {})
    if imported:
        install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule hooks/producer) (export integer text apply) {declarations})''')
    (tmp_path / "hooks.py").write_text('''import json, os, sys
from pathlib import Path
lane = sys.argv[1]
with open("hooks.log", "a") as log: log.write(lane + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(11 if lane == "integer" else "typed"))
''')
    files["commands"].write_text(json.dumps({"fetch": {"kind": "external_tool",
        "stable_command": ["python", "hooks.py"], "closure": ["hooks.py"]}}))
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    pause_context(files, monkeypatch, inputs)
    authority, _before = checked_run(tmp_path)
    resumed = _resume_cli(tmp_path, authority.header["run_id"])
    assert resumed.returncode == 0, resumed.stderr
    authority, snapshot = checked_run(tmp_path)
    owner = "hooks/producer" if imported else "hooks/entry"
    assert_generic_hook_run(tmp_path, authority, snapshot, owner)


def _walk_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_nodes(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_nodes(child)


def _assert_cached_call_arguments(native_environment):
    assert native_environment.lookup("a__x").dependencies == {"pair-provider-id"}
    assert native_environment.lookup("a__y").dependencies == {"pair-provider-id"}
    assert native_environment.lookup("a__x").committed_result_path is None
    assert native_environment.lookup("a__y").committed_result_path is None
    assert native_environment.lookup("count").dependencies == {"count-provider-id"}
    assert native_environment.lookup("count").committed_result_path == (
        "artifacts/count-result.json"
    )


def _assert_imported_call_effect_result(result, effects, dependencies):
    assert [provider for provider, _identity in effects] == [
        "count-provider-id",
        "pair-provider-id",
    ]
    assert {identity for _provider, identity in effects} == dependencies
    assert result.json_value() == {
        "defaulted": {
            "left": "reports/input-left.txt",
            "right": "reports/input-right.txt",
            "count": 3,
        },
        "supplied": {
            "left": "reports/left.txt",
            "right": "reports/right.txt",
            "count": 11,
        },
    }
    assert result.dependencies == frozenset(dependencies)


def test_imported_boundary_call_projects_cached_values_and_native_result(
    tmp_path: Path,
) -> None:
    producer_root = tmp_path / "producer"
    producer_root.mkdir()
    producer_path = install(
        producer_root,
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule producer) (export get)
          (defpath Report :kind relpath :under "reports" :must-exist false)
          (defrecord Result (left Report) (right Report) (count Int))
          (defworkflow get ((a__x Report) (a__y Report) (count Int :default 3)) -> Result
            (record Result :left a__x :right a__y :count count)))''',
    )
    (producer_root / "prompt.md").write_text("producer prompt", encoding="utf-8")
    producer = compile_stage3_entrypoint(
        producer_path,
        entry_workflow="producer::get",
        source_roots=(producer_root,),
        validate_shared=True,
        workspace_root=producer_root,
    )
    bundle = producer.validated_bundles_by_name["producer::get"]

    consumer_root = tmp_path / "consumer"
    consumer_root.mkdir()
    consumer_path = install(
        consumer_root,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule consumer) (export run)
          (defpath Report :kind relpath :under "reports" :must-exist false)
          (defrecord Pair (x Report) (y Report))
          (defrecord Result (left Report) (right Report) (count Int))
          (defrecord CallsResult (defaulted Result) (supplied Result))
          (defworkflow run ((pair Pair)) -> CallsResult
            (let* ((defaulted (call dep :a pair))
                   (supplied
                     (call dep
                       :count (provider-result count-provider :prompt prompt :inputs () :returns Int)
                       :a (provider-result pair-provider :prompt prompt :inputs () :returns Pair))))
              (record CallsResult :defaulted defaulted :supplied supplied))))''',
    )
    (consumer_root / "prompt.md").write_text("consumer prompt", encoding="utf-8")
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="consumer::run",
        source_roots=(consumer_root,),
        command_boundaries={},
        provider_externs={
            "count-provider": "count-provider-id",
            "pair-provider": "pair-provider-id",
        },
        prompt_externs={"prompt": PromptExtern(name="prompt", input_file="prompt.md")},
        imported_workflow_bundles={"dep": bundle},
        workspace_root=consumer_root,
    )
    compiled = build_closed_program(typed)
    producer_path.unlink()
    consumer_path.unlink()
    (producer_root / "prompt.md").unlink()
    (consumer_root / "prompt.md").unlink()
    program = ClosedProgram.from_artifact(compiled.artifact())

    from orchestrator.workflow.evaluated.calls import call_environment
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.evaluated.values import coerce_evaluated_value

    calls = [
        node for node in _walk_nodes(program.tree["body"]) if node.get("k") == "call"
    ]
    assert len(calls) == 2
    call = calls[-1]
    native = program.tree["definitions"][call["callee"]]
    supplied = {
        "a": (
            {"x": "reports/left.txt", "y": "reports/right.txt"},
            frozenset({"pair-provider-id"}),
            "artifacts/pair-result.json",
        ),
        "count": (
            11,
            frozenset({"count-provider-id"}),
            "artifacts/count-result.json",
        ),
    }
    cached_arguments = [
        coerce_evaluated_value(
            supplied[name][0],
            descriptor,
            dependencies=supplied[name][1],
            committed_result_path=supplied[name][2],
        )
        for name, descriptor in call["boundary"]["params"]
    ]
    native_environment = call_environment(
        call, native, cached_arguments, run_id="calls"
    )
    _assert_cached_call_arguments(native_environment)

    effects: list[tuple[str, str]] = []
    dependencies: set[str] = set()

    def perform(node, _operands, identity, _owner, _reader):
        provider = node["provider"]
        effects.append((provider, identity))
        dependencies.add(identity)
        result = 11 if provider == "count-provider-id" else {
            "x": "reports/left.txt",
            "y": "reports/right.txt",
        }
        return coerce_evaluated_value(
            result, node["result"], dependencies={identity},
            committed_result_path="artifacts/provider-result.json",
        )

    result = evaluate_closed_program(
        program,
        {"pair": {"x": "reports/input-left.txt", "y": "reports/input-right.txt"}},
        effect_handler=perform,
        run_id="calls",
    )

    _assert_imported_call_effect_result(result, effects, dependencies)


def test_union_boundary_skips_inactive_path_rows_on_input_and_result() -> None:
    from tests.test_workflow_lisp_closed_program_check import _boundary_tree
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program

    report = {
        "kind": "path",
        "name": "Report",
        "under": "reports",
        "must_exist_target": True,
    }
    caller = {
        "kind": "union",
        "name": "caller::Choice",
        "variants": [
            {"name": "Ready", "fields": [{"name": "path", "type": report}]},
            {"name": "Skipped", "fields": [{"name": "reason", "type": {"kind": "primitive", "name": "String"}}]},
        ],
    }
    native = {**caller, "name": "native::Choice"}
    tree, _call = _boundary_tree([("choice", caller)], [("choice", native)], caller, native)
    tree["types"]["Report"] = report
    definition = next(iter(tree["definitions"].values()))
    definition["body"] = {"k": "halt", "value": {"k": "name", "n": "choice"}}
    program = ClosedProgram.from_artifact(json.dumps(tree))

    ready = evaluate_closed_program(
        program, {"choice": {"variant": "Ready", "path": "reports/item.txt"}}
    )
    skipped = evaluate_closed_program(
        program, {"choice": {"variant": "Skipped", "reason": "not-needed"}}
    )

    assert ready.json_value() == {"variant": "Ready", "path": "reports/item.txt"}
    assert skipped.json_value() == {"variant": "Skipped", "reason": "not-needed"}


def test_unannotated_local_call_keeps_strict_native_argument_binding(tmp_path: Path) -> None:
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program

    source_path = install(
        tmp_path,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule strict_call) (export run)
          (defworkflow leaf ((left Int) (right Int)) -> Int left)
          (defworkflow run ((x Int) (y Int)) -> Int
            (call leaf :right y :left x)))''',
    )
    typed = compile_typed_program(
        source_path,
        entry_workflow="strict_call::run",
        source_roots=(tmp_path,),
        command_boundaries={},
        workspace_root=tmp_path,
    )
    source_path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    calls = [
        node for node in _walk_nodes(program.tree["body"]) if node.get("k") == "call"
    ]
    assert len(calls) == 1
    assert "boundary" not in calls[0]

    result = evaluate_closed_program(program, {"x": 8, "y": 5})

    assert result.json_value() == 8


def test_public_unannotated_local_call_keeps_strict_native_argument_binding(tmp_path, monkeypatch):
    from tests.workflow_evaluated_context_helpers import pure_files, assert_pure_public

    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule strict_call) (export run)
      (defworkflow leaf ((left Int) (right Int)) -> Int left)
      (defworkflow run ((x Int) (y Int)) -> Int (call leaf :right y :left x)))'''
    files, inputs = pure_files(tmp_path, source, {"x": 8, "y": 5})
    program, result = assert_pure_public(files, inputs, 8, monkeypatch)
    calls = [node for node in _walk_nodes(program.tree["body"]) if node.get("k") == "call"]
    assert len(calls) == 1
    assert "boundary" not in calls[0]
    assert result.descriptor == {"kind": "primitive", "name": "Int"}


def test_public_imported_generics_keep_native_owner_and_argument_types(tmp_path, monkeypatch):
    from tests.workflow_evaluated_context_helpers import pure_files, assert_pure_public
    from tests.workflow_lisp_closed_program_helpers import install

    entry = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule consumer) (export run)
      (defrecord Payload (count Int) (flag Bool))
      (defrecord Result (number Int) (payload Payload))
      (defworkflow run ((number Int) (payload Payload)) -> Result
        (let* ((kept-number (call int-dep :number number))
               (kept-payload (call payload-dep :payload payload)))
          (record Result :number kept-number :payload kept-payload))))'''
    expected = {"number": 6, "payload": {"count": 4, "flag": True}}
    files, inputs = pure_files(tmp_path, entry, expected)
    imports = {}
    for module, formal, type_name, declaration, alias in (
        ("int_producer", "number", "Int", "", "int-dep"),
        ("payload_producer", "payload", "Payload", "(defrecord Payload (count Int) (flag Bool))", "payload-dep"),
    ):
        path = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule {module}) (export keep)
          {declaration}
          (defproc identity :forall (T) ((value T)) -> T :effects () :lowering inline value)
          (defworkflow keep (({formal} {type_name})) -> {type_name} (identity {formal})))''')
        imports[alias] = {"kind": "compiled", "path": path.relative_to(tmp_path).as_posix()}
    files["imports"] = tmp_path / "imports.json"
    files["imports"].write_text(json.dumps(imports))
    program, result = assert_pure_public(files, inputs, expected, monkeypatch)
    assert {row["key"][0] for row in program.tree["definitions"].values()} == {"int_producer", "payload_producer"}
    assert result.descriptor["name"] == "consumer::Result"


def test_public_imported_boundary_projects_once_only_operand_values(tmp_path, monkeypatch):
    import os
    from tests.test_workflow_evaluated_public_context import _provider_files
    from tests.test_workflow_evaluated_providers import (
        _requests, _assert_attempt_evidence, _assert_cli_resumes_unchanged, _orchestrate_snapshot,
    )
    from tests.test_workflow_evaluated_resume import _resume_cli
    from tests.workflow_evaluated_totality_helpers import checked_run, compile_public
    from tests.workflow_evaluated_context_helpers import pause_context

    producer = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule producer) (export get)
      (defpath Report :kind relpath :under "reports" :must-exist false)
      (defrecord Result (left Report) (right Report) (count Int))
      (defworkflow get ((a__x Report) (a__y Report) (count Int :default 3)) -> Result
        (record Result :left a__x :right a__y :count count)))'''
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defpath Report :kind relpath :under "reports" :must-exist false)
      (defrecord Pair (x Report) (y Report))
      (defrecord Result (left Report) (right Report) (count Int))
      (defrecord CallsResult (defaulted Result) (supplied Result) (echoed Int))
      (defworkflow run ((pair Pair)) -> CallsResult
        (let* ((defaulted (call dep :a pair))
               (supplied (call dep
                 :count (provider-result count-provider :prompt prompt :inputs () :returns Int)
                 :a (provider-result pair-provider :prompt prompt :inputs () :returns Pair)))
               (echoed (provider-result echo-provider :prompt prompt :inputs (supplied) :returns Int)))
          (record CallsResult :defaulted defaulted :supplied supplied :echoed echoed))))'''
    files, inputs = _provider_files(tmp_path, source)
    inputs.write_text(json.dumps({"pair": {"x": "reports/input-left.txt", "y": "reports/input-right.txt"}}))
    files["providers"].write_text(json.dumps(
        {"count-provider": "codex", "pair-provider": "codex", "echo-provider": "codex"}))
    files["prompts"].write_text(json.dumps({"prompt": {"asset_file": "prompt.md"}}))
    install(tmp_path, producer)
    files["imports"] = tmp_path / "imports.json"
    files["imports"].write_text(json.dumps({"dep": {"kind": "compiled", "path": "producer.orc"}}))
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PROVIDER_SHIM_RESULTS",
                       json.dumps(["11", '{"x":"reports/left.txt","y":"reports/right.txt"}', "5"]))
    compile_public(files)
    monkeypatch.chdir(tmp_path)
    pause = pause_context(files, monkeypatch, inputs)
    authority, prefix = checked_run(tmp_path)
    assert list(prefix.active_commits.values()) == [pause]
    assert pause.data["value"] == 11
    assert len(_requests(tmp_path)) == 1
    resumed = _resume_cli(tmp_path, authority.header["run_id"])
    assert resumed.returncode == 0, resumed.stderr
    _, snapshot = checked_run(tmp_path)
    expected = {"defaulted": {"left": "reports/input-left.txt", "right": "reports/input-right.txt", "count": 3},
                "supplied": {"left": "reports/left.txt", "right": "reports/right.txt", "count": 11}, "echoed": 5}
    assert snapshot.terminal.data["value"] == expected
    commits = list(snapshot.active_commits.values())
    assert [row.data["value"] for row in commits] == [11, {"x": "reports/left.txt", "y": "reports/right.txt"}, 5]
    assert commits[1].data["depends_on"] == []
    for commit, request in zip(commits, _requests(tmp_path), strict=True):
        _assert_attempt_evidence(authority.run_root, commit.data, request)
    _assert_cli_resumes_unchanged(tmp_path, authority.header["run_id"], _orchestrate_snapshot(tmp_path),
                                (tmp_path / "requests.jsonl").read_bytes(), count=2)
    _assert_boundary_dependencies_and_descriptor(tmp_path, authority, commits, expected)


def _assert_boundary_dependencies_and_descriptor(root, authority, commits, expected):
    """The call result carries both producer identities across the imported boundary."""
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.evaluated.values import coerce_evaluated_value

    producers = sorted(commit.data["identity"] for commit in commits[:2])
    assert commits[2].data["depends_on"] == producers
    rows = {commit.data["identity"]: commit.data for commit in commits}

    def replay(node, _operands, identity, _owner, _reader):
        row = rows[identity]
        return coerce_evaluated_value(row["value"], node["result"], dependencies=(*row["depends_on"], identity))

    for source in root.rglob("*.orc"):
        source.unlink()
    program = ClosedProgram.from_artifact(authority.program_path.read_text())
    result = evaluate_closed_program(program, authority.header["bound_inputs"], effect_handler=replay,
                                     run_id=authority.header["run_id"])
    assert (result.json_value(), result.descriptor["name"]) == (expected, "main::CallsResult")
    assert result.dependencies == set(rows)
