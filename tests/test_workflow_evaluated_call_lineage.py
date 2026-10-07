from __future__ import annotations

from pathlib import Path

from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import ExternalToolBinding, PromptExtern
from tests.workflow_lisp_closed_program_helpers import TARGET, install


def _assert_producer_and_caller_configuration(program, definition):
    imported_config = program.tree["configuration"]["imports"][
        definition["configuration"]
    ]
    assert imported_config["commands"]["shared"]["stable_command"] == [
        "python",
        "producer.py",
    ]
    assert imported_config["providers"]["provider"]["provider_id"] == (
        "producer-provider"
    )
    assert imported_config["prompts"]["prompt"]["path"] == "prompt.md"
    assert program.tree["configuration"]["commands"]["shared"]["stable_command"] == [
        "python",
        "consumer.py",
    ]
    assert program.tree["configuration"]["providers"]["provider"]["provider_id"] == (
        "consumer-provider"
    )


def _assert_imported_effect_result(result, effects):
    assert result.json_value() == 18
    assert len(effects) == 2
    command = next(node for node, _identity in effects if node["class"] == "command")
    provider = next(node for node, _identity in effects if node["class"] == "provider")
    assert command["command"] == ["python", "producer.py"]
    assert provider["provider"] == "producer-provider"
    assert provider["prompt"]["path"] == "prompt.md"
    assert result.dependencies == frozenset(identity for _node, identity in effects)


def test_imported_effect_uses_producer_configuration_on_name_conflicts(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.evaluated.values import coerce_evaluated_value

    producer_root = tmp_path / "producer"
    consumer_root = tmp_path / "consumer"
    producer_root.mkdir()
    consumer_root.mkdir()
    producer_path = install(
        producer_root,
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule producer) (export get)
          (defworkflow get ((n Int)) -> Int
            (let* ((command-value
                     (command-result shared
                       :argv ("python" "producer.py" n) :returns Int))
                   (provider-value
                     (provider-result provider
                       :prompt prompt :inputs () :returns Int)))
              (+ command-value provider-value))))''',
    )
    consumer_path = install(
        consumer_root,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule consumer) (export run)
          (defworkflow run ((n Int)) -> Int (call dep :n n)))''',
    )
    producer_prompt = producer_root / "prompt.md"
    consumer_prompt = consumer_root / "prompt.md"
    producer_prompt.write_text("producer prompt", encoding="utf-8")
    consumer_prompt.write_text("consumer prompt", encoding="utf-8")
    producer = compile_stage3_entrypoint(
        producer_path,
        entry_workflow="producer::get",
        source_roots=(producer_root,),
        validate_shared=True,
        workspace_root=producer_root,
        command_boundaries={
            "shared": ExternalToolBinding(
                name="shared",
                stable_command=("python", "producer.py"),
                closure=(),
            )
        },
        provider_externs={"provider": "producer-provider"},
        prompt_externs={
            "prompt": PromptExtern(name="prompt", input_file="prompt.md")
        },
    )
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="consumer::run",
        source_roots=(consumer_root,),
        command_boundaries={
            "shared": ExternalToolBinding(
                name="shared",
                stable_command=("python", "consumer.py"),
                closure=(),
            )
        },
        provider_externs={"provider": "consumer-provider"},
        prompt_externs={
            "prompt": PromptExtern(name="prompt", input_file="prompt.md")
        },
        imported_workflow_bundles={
            "dep": producer.validated_bundles_by_name["producer::get"]
        },
        workspace_root=consumer_root,
    )
    for path in (producer_path, consumer_path, producer_prompt, consumer_prompt):
        path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    call = program.tree["body"]["value"]
    definition = program.tree["definitions"][call["callee"]]
    _assert_producer_and_caller_configuration(program, definition)

    effects: list[tuple[dict, str]] = []

    def perform(node, _operands, identity, _owner, _reader):
        effects.append((node, identity))
        value = 7 if node["class"] == "command" else 11
        return coerce_evaluated_value(
            value,
            node["result"],
            dependencies={identity},
        )

    result = evaluate_closed_program(
        program,
        {"n": 5},
        effect_handler=perform,
    )

    _assert_imported_effect_result(result, effects)


def test_projected_import_result_keeps_committed_file_lineage_without_reread(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.evaluated.values import coerce_evaluated_value

    producer_root = tmp_path / "producer"
    consumer_root = tmp_path / "consumer"
    producer_root.mkdir()
    consumer_root.mkdir()
    producer_path = install(
        producer_root,
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule producer) (export get)
          (defpath Report :kind relpath :under "reports" :must-exist false)
          (defrecord FlatResult (payload__x Report) (payload__y Report))
          (defworkflow get () -> FlatResult
            (provider-result provider :prompt prompt :inputs () :returns FlatResult)))''',
    )
    consumer_path = install(
        consumer_root,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule consumer) (export run)
          (defpath Report :kind relpath :under "reports" :must-exist false)
          (defrecord Pair (x Report) (y Report))
          (defrecord Result (payload Pair))
          (defworkflow run () -> Result (call dep)))''',
    )
    prompt_path = producer_root / "prompt.md"
    prompt_path.write_text("producer prompt", encoding="utf-8")
    producer = compile_stage3_entrypoint(
        producer_path,
        entry_workflow="producer::get",
        source_roots=(producer_root,),
        validate_shared=True,
        workspace_root=producer_root,
        provider_externs={"provider": "producer-provider"},
        prompt_externs={
            "prompt": PromptExtern(name="prompt", input_file="prompt.md")
        },
    )
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="consumer::run",
        source_roots=(consumer_root,),
        command_boundaries={},
        imported_workflow_bundles={
            "dep": producer.validated_bundles_by_name["producer::get"]
        },
        workspace_root=consumer_root,
    )
    for path in (producer_path, consumer_path, prompt_path):
        path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    effects: list[str] = []

    def perform(node, _operands, identity, _owner, _reader):
        effects.append(identity)
        return coerce_evaluated_value(
            {"payload__x": "reports/x.txt", "payload__y": "reports/y.txt"},
            node["result"],
            dependencies={identity},
            committed_result_path="artifacts/committed/effect-result.json",
        )

    def no_filesystem_access(*_args, **_kwargs):
        raise AssertionError("call projection must not reread a committed result path")

    for method in ("exists", "is_file", "read_text", "read_bytes", "resolve"):
        monkeypatch.setattr(Path, method, no_filesystem_access)
    result = evaluate_closed_program(program, {}, effect_handler=perform)

    assert len(effects) == 1
    assert result.json_value() == {
        "payload": {"x": "reports/x.txt", "y": "reports/y.txt"}
    }
    assert result.dependencies == frozenset(effects)
    assert result.committed_result_path == "artifacts/committed/effect-result.json"


def test_source_admitted_imported_union_projects_only_active_variant_rows(
    tmp_path: Path,
) -> None:
    from orchestrator.state import StateManager
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.executor import WorkflowExecutor
    from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
    from orchestrator.workflow.signatures import bind_workflow_inputs
    from tests.workflow_bundle_helpers import bundle_context_dict

    type_forms = '''(defpath Report :kind relpath :under "artifacts/work" :must-exist false)
      (defunion Choice (Ready (path Report)) (Skipped (reason String)))'''
    producer_source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule producer) (export get)
      ''' + type_forms + '''
      (defworkflow get ((allow Bool)) -> Choice
        (if allow
          (variant Choice Ready :path (path/join-under Report "report.md"))
          (variant Choice Skipped :reason "declined"))))'''
    consumer_source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule consumer) (export run)
      {type_forms}
      (defworkflow run ((allow Bool)) -> Choice
        (call dep :allow allow)))'''
    source_root = tmp_path / "evaluated"
    producer_root = source_root / "producer-source"
    consumer_root = source_root / "consumer-source"
    producer_root.mkdir(parents=True)
    consumer_root.mkdir(parents=True)
    producer_path = install(producer_root, producer_source)
    producer = compile_stage3_entrypoint(
        producer_path,
        entry_workflow="producer::get",
        source_roots=(producer_root,),
        validate_shared=True,
        workspace_root=producer_root,
    )
    consumer_path = install(consumer_root, consumer_source)
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="consumer::run",
        source_roots=(consumer_root,),
        command_boundaries={},
        imported_workflow_bundles={
            "dep": producer.validated_bundles_by_name["producer::get"]
        },
        workspace_root=consumer_root,
    )
    producer_path.unlink()
    consumer_path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    call = program.tree["body"]["value"]
    output_rows = call["boundary"]["outputs"]["caller"]
    assert [row["name"] for row in output_rows] == [
        "return__variant",
        "return__path",
        "return__reason",
    ]
    assert output_rows[0]["contract"]["projection"]["active_variants"] == [
        "Ready",
        "Skipped",
    ]
    assert output_rows[1]["contract"]["projection"]["active_variants"] == ["Ready"]
    assert output_rows[2]["contract"]["projection"]["active_variants"] == ["Skipped"]

    evaluated_values = {
        allow: evaluate_closed_program(program, {"allow": allow}).json_value()
        for allow in (True, False)
    }

    old_root = tmp_path / "legacy"
    old_root.mkdir()
    old_producer_path = install(old_root, producer_source)
    old_producer = compile_stage3_entrypoint(
        old_producer_path,
        entry_workflow="producer::get",
        source_roots=(old_root,),
        validate_shared=True,
        workspace_root=old_root,
    )
    old_consumer_source = consumer_source.replace(
        f'(:target-dsl "{TARGET}")', '(:target-dsl "2.34")'
    )
    old_consumer_path = install(old_root, old_consumer_source)
    old_bundle = compile_stage3_entrypoint(
        old_consumer_path,
        entry_workflow="consumer::run",
        source_roots=(old_root,),
        validate_shared=True,
        workspace_root=old_root,
        imported_workflow_bundles={
            "dep": old_producer.validated_bundles_by_name["producer::get"]
        },
    ).validated_bundles_by_name["consumer::run"]

    old_values = {}
    for allow in (True, False):
        contracts = {
            name: contract
            for name, contract in workflow_runtime_input_contracts(old_bundle).items()
            if not name.startswith("__write_root__")
        }
        run_id = f"imported-union-{allow}"
        state = StateManager(workspace=old_root, run_id=run_id)
        state.initialize(
            str(old_consumer_path),
            context=bundle_context_dict(old_bundle),
            bound_inputs=bind_workflow_inputs(contracts, {"allow": allow}, old_root),
        )
        outcome = WorkflowExecutor(old_bundle, old_root, state, retry_delay_ms=0).execute(
            on_error="stop"
        )
        assert outcome["status"] == "completed"
        old_values[allow] = outcome["workflow_outputs"]

    # Compare decoded old-route payloads, not the route-specific flattened names.
    projected_old_values = {
        True: {
            "variant": old_values[True]["return__variant"],
            "path": old_values[True]["return__path"],
        },
        False: {
            "variant": old_values[False]["return__variant"],
            "reason": old_values[False]["return__reason"],
        },
    }
    assert evaluated_values == projected_old_values == {
        True: {"variant": "Ready", "path": "artifacts/work/report.md"},
        False: {"variant": "Skipped", "reason": "declined"},
    }
