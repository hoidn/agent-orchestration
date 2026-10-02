from __future__ import annotations

from pathlib import Path

from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from tests.workflow_lisp_closed_program_helpers import TARGET, install

def test_imported_generic_specializations_and_local_proc_hooks_execute(
    tmp_path: Path,
) -> None:
    producer_paths = []
    producer_bundles = {}
    for module, workflow, formal, type_name, type_definition, alias in (
        ("int_producer", "keep", "number", "Int", "", "int-dep"),
        (
            "payload_producer",
            "keep",
            "payload",
            "Payload",
            "(defrecord Payload (count Int) (flag Bool))",
            "payload-dep",
        ),
    ):
        producer_root = tmp_path / module
        producer_root.mkdir()
        producer_path = install(
            producer_root,
            f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
              (defmodule {module}) (export {workflow})
              {type_definition}
              (defproc identity :forall (T) ((value T)) -> T
                :effects () :lowering inline value)
              (defworkflow {workflow} (({formal} {type_name})) -> {type_name}
                (identity {formal})))''',
        )
        loaded = compile_stage3_entrypoint(
            producer_path,
            entry_workflow=f"{module}::{workflow}",
            source_roots=(producer_root,),
            validate_shared=True,
            workspace_root=producer_root,
        )
        producer_paths.append(producer_path)
        producer_bundles[alias] = loaded.validated_bundles_by_name[
            f"{module}::{workflow}"
        ]
    consumer_root = tmp_path / "consumer"
    consumer_root.mkdir()
    consumer_path = install(
        consumer_root,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule consumer) (export run)
          (defrecord Payload (count Int) (flag Bool))
          (defrecord Result (number Int) (payload Payload))
          (defworkflow run ((number Int) (payload Payload)) -> Result
            (let* ((kept-number (call int-dep :number number))
                   (kept-payload (call payload-dep :payload payload)))
              (record Result :number kept-number :payload kept-payload))))''',
    )
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="consumer::run",
        source_roots=(consumer_root,),
        command_boundaries={},
        imported_workflow_bundles=producer_bundles,
        workspace_root=consumer_root,
    )
    compiled = build_closed_program(typed)
    for producer_path in producer_paths:
        producer_path.unlink()
    consumer_path.unlink()
    program = ClosedProgram.from_artifact(compiled.artifact())

    from orchestrator.workflow.evaluated.machine import evaluate_closed_program

    result = evaluate_closed_program(
        program,
        {"number": 6, "payload": {"count": 4, "flag": True}},
    )

    assert result.json_value() == {
        "number": 6,
        "payload": {"count": 4, "flag": True},
    }


def test_forwarded_bind_proc_keeps_effect_lineage_without_rereading_path(
    tmp_path: Path, monkeypatch
) -> None:
    from tests.test_workflow_lisp_closed_program_elaboration import (
        _BIND_PROC_CAPTURE_SOURCE,
    )
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.evaluated.values import coerce_evaluated_value
    from orchestrator.workflow_lisp.workflows import ExternalToolBinding

    root = tmp_path / "bind-proc"
    source_path = install(root, _BIND_PROC_CAPTURE_SOURCE.replace("TARGET", TARGET))
    typed = compile_typed_program(
        source_path,
        entry_workflow="cp/bind_proc_capture::run",
        source_roots=(root,),
        command_boundaries={
            "add": ExternalToolBinding(
                name="add", stable_command=("python", "add.py"), closure=()
            )
        },
        workspace_root=root,
    )
    source_path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())

    effects: list[tuple[tuple[object, ...], str]] = []

    def perform(node, operands, identity):
        values = tuple(value.value for value in operands)
        effects.append((values, identity))
        return coerce_evaluated_value(
            sum(values),
            node["result"],
            dependencies={identity},
            committed_result_path="artifacts/effect-result.json",
        )

    def no_filesystem_access(*_args, **_kwargs):
        raise AssertionError("evaluated calls must not reread committed paths")

    for method in ("exists", "is_file", "read_text", "read_bytes", "resolve"):
        monkeypatch.setattr(Path, method, no_filesystem_access)
    result = evaluate_closed_program(program, {}, effect_handler=perform)

    assert [values for values, _identity in effects] == [(2, 5)]
    assert result.json_value() == 7
    assert result.dependencies == frozenset({effects[0][1]})
    assert result.committed_result_path == "artifacts/effect-result.json"


def test_captured_let_proc_calls_imported_workflow_after_readback(
    tmp_path: Path,
) -> None:
    producer_root = tmp_path / "producer"
    producer_root.mkdir()
    producer_path = install(
        producer_root,
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule producer) (export keep)
          (defworkflow keep ((value Int)) -> Int (+ value 1)))''',
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        entry_workflow="producer::keep",
        source_roots=(producer_root,),
        validate_shared=True,
        workspace_root=producer_root,
    )
    bundle = producer.validated_bundles_by_name["producer::keep"]

    consumer_root = tmp_path / "consumer"
    consumer_root.mkdir()
    consumer_path = install(
        consumer_root,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule consumer) (export run)
          (defproc apply ((runner ProcRef[Int -> Int]) (value Int)) -> Int
            :effects () :lowering inline (runner value))
          (defworkflow run ((number Int)) -> Int
            (let-proc (saved ((value Int)) -> Int :captures (number)
                (call dep :value (+ value number)))
              (apply (proc-ref saved) 5))))''',
    )
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="consumer::run",
        source_roots=(consumer_root,),
        command_boundaries={},
        imported_workflow_bundles={"dep": bundle},
        workspace_root=consumer_root,
    )
    producer_path.unlink()
    consumer_path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())

    from orchestrator.workflow.evaluated.machine import evaluate_closed_program

    result = evaluate_closed_program(program, {"number": 6})

    assert result.json_value() == 12
    assert any(
        row["key"][:3] == ["producer", "workflow", "keep"]
        for row in program.tree["definitions"].values()
    )


def test_same_module_generic_specializations_execute_with_distinct_types(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program

    source_path = install(
        tmp_path,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule local_generic) (export run)
          (defrecord Payload (count Int) (flag Bool))
          (defrecord Result (number Int) (payload Payload))
          (defproc identity :forall (T) ((value T)) -> T
            :effects () :lowering private-workflow value)
          (defworkflow run ((number Int) (payload Payload)) -> Result
            (let* ((kept-number (identity number))
                   (kept-payload (identity payload)))
              (record Result :number kept-number :payload kept-payload))))''',
    )
    typed = compile_typed_program(
        source_path,
        entry_workflow="local_generic::run",
        source_roots=(tmp_path,),
        command_boundaries={},
        workspace_root=tmp_path,
    )
    source_path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    identities = [
        definition
        for definition in program.tree["definitions"].values()
        if definition["key"][:3] == ["local_generic", "procedure", "identity"]
    ]

    assert len(identities) == 2
    assert {
        definition["key"][8]["params"][0]["name"]
        for definition in identities
    } == {"Int", "local_generic::Payload"}
    result = evaluate_closed_program(
        program,
        {"number": 6, "payload": {"count": 4, "flag": True}},
    )

    assert result.json_value() == {
        "number": 6,
        "payload": {"count": 4, "flag": True},
    }



def test_imported_context_captures_execute_after_artifact_readback(tmp_path: Path) -> None:
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program

    producer_source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule producer)
      (import std/context :only (PhaseCtx))
      (import std/phase :only (with-phase))
      (export entry run-phase)
      (defworkflow entry ((payload Int) (explicit PhaseCtx)) -> Int
        (let* ((first (call run-phase :payload payload))
               (second (call run-phase :phase__ctx explicit :payload payload))
               (third (call run-phase :payload payload)))
          third))
      (defworkflow run-phase ((phase__ctx PhaseCtx) (payload Int)) -> Int
        (with-phase phase__ctx plan-gate-wrapper payload)))'''
    consumer_source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule consumer)
      (import std/context :only (PhaseCtx))
      (export run)
      (defworkflow run ((payload Int) (ctx PhaseCtx) (explicit PhaseCtx)) -> Int
        (call dep :payload payload :phase__ctx ctx :explicit explicit)))'''
    root = tmp_path / "context-import"
    root.mkdir()
    producer_path = install(
        root,
        {"producer.orc": producer_source, "consumer.orc": consumer_source},
        entry_path="producer.orc",
    )
    consumer_path = root / "consumer.orc"
    producer = compile_stage3_entrypoint(
        producer_path,
        entry_workflow="producer::entry",
        source_roots=(root,),
        validate_shared=True,
        workspace_root=root,
    )
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="consumer::run",
        source_roots=(root,),
        command_boundaries={},
        imported_workflow_bundles={
            "dep": producer.validated_bundles_by_name["producer::entry"]
        },
        workspace_root=root,
    )
    producer_path.unlink()
    consumer_path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    context = {
        "run": {
            "run-id": "explicit-run",
            "state-root": "state/explicit-run",
            "artifact-root": "artifacts/explicit-run",
        },
        "phase-name": "caller-phase",
        "state-root": "state/caller-phase",
        "artifact-root": "artifacts/caller-phase",
    }

    result = evaluate_closed_program(
        program,
        {"payload": 9, "ctx": context, "explicit": context},
        run_id="runtime-run",
    )

    assert result.json_value() == 9
