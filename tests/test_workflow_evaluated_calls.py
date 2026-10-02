from __future__ import annotations

import json
from pathlib import Path

from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import PromptExtern
from tests.workflow_lisp_closed_program_helpers import TARGET, install


def _walk_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_nodes(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_nodes(child)


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
    assert native_environment.lookup("a__x").dependencies == {"pair-provider-id"}
    assert native_environment.lookup("a__y").dependencies == {"pair-provider-id"}
    assert native_environment.lookup("a__x").committed_result_path is None
    assert native_environment.lookup("a__y").committed_result_path is None
    assert native_environment.lookup("count").dependencies == {"count-provider-id"}
    assert native_environment.lookup("count").committed_result_path == (
        "artifacts/count-result.json"
    )

    effects: list[tuple[str, str]] = []
    dependencies: set[str] = set()

    def perform(node, _operands, identity):
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
