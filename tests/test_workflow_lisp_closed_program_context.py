from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.closed.names import CanonicalNameError, canonical_type_descriptor
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import ProviderBundlePathExpr
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.model import WccOpaqueFrontendValue
from orchestrator.workflow_lisp.workflows import PromptExtern
from tests.workflow_lisp_closed_program_helpers import TARGET, install


_PREAMBLE = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
  (defmodule context_probe)
  (import std/context :only (RunCtx PhaseCtx ItemCtx))
  (import std/phase :only (with-phase))
  (export entry)
'''
_LEAF = '''(defworkflow leaf ((phase-ctx PhaseCtx)) -> Symbol
  (with-phase phase-ctx plan-gate-wrapper phase-ctx.phase-name))'''


def _compile(root: Path, body: str):
    path = install(root, _PREAMBLE + body + ")")
    typed = compile_typed_program(
        path,
        entry_workflow="entry",
        source_roots=(root,),
        command_boundaries={},
        workspace_root=root,
    )
    return path, typed


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)
    elif is_dataclass(value) and type(value).__name__.startswith("Wcc"):
        yield value
        for field in fields(value):
            if field.name != "metadata":
                yield from _walk(getattr(value, field.name))


def _phase_fields(value):
    assert value["k"] == "record"
    assert value["type"]["name"] == "std/context::PhaseCtx"
    return dict(value["fields"])


def test_hidden_entry_run_context_is_a_typed_x1_record(tmp_path: Path) -> None:
    path, typed = _compile(
        tmp_path,
        "(defworkflow entry ((run RunCtx)) -> RunId run.run-id)",
    )
    assert tuple(typed.entry.signature.hidden_context_requirements) == ("run",)
    path.unlink()

    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )
    body = restored.tree["body"]
    assert restored.tree["params"] == []
    assert body["k"] == "let" and body["name"] == "run"
    value = body["value"]
    assert value["k"] == "record"
    assert value["type"]["name"] == "std/context::RunCtx"
    fields = dict(value["fields"])
    assert fields["run-id"] == {"k": "context", "field": "run-id"}
    assert fields["state-root"]["v"] == "state/run"
    assert fields["artifact-root"]["v"] == "artifacts/run"
    assert fields["state-root"]["type"]["under"] == "state"
    assert fields["artifact-root"]["type"]["under"] == "artifacts"


@pytest.mark.parametrize(
    ("entry", "expected_run"),
    [
        ("(defworkflow entry () -> Symbol (call leaf))", "default"),
        ("(defworkflow entry ((run RunCtx)) -> Symbol (call leaf))", "caller"),
    ],
)
def test_omitted_phase_context_uses_the_default_or_existing_run_context(
    tmp_path: Path,
    entry: str,
    expected_run: str,
) -> None:
    root = tmp_path / expected_run
    path, typed = _compile(root, entry + _LEAF)
    signatures = {
        name: tuple(workflow.signature.params)
        for name, workflow in typed.workflows.items()
    }
    path.unlink()

    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )
    assert signatures == {
        name: tuple(workflow.signature.params)
        for name, workflow in typed.workflows.items()
    }
    call = next(
        node for node in _walk(restored.tree["body"])
        if node.get("k") == "call" and node.get("callee") == "workflow:context_probe::leaf"
    )
    phase = _phase_fields(call["args"][0])
    assert phase["phase-name"]["v"] == "plan-gate-wrapper"
    assert phase["state-root"]["v"] == "state/plan-gate-wrapper"
    assert phase["artifact-root"]["v"] == "artifacts/plan-gate-wrapper"
    if expected_run == "caller":
        assert phase["run"] == {"k": "name", "n": "run"}
    else:
        assert phase["run"]["type"]["name"] == "std/context::RunCtx"
        run_fields = dict(phase["run"]["fields"])
        assert run_fields["run-id"] == {"k": "context", "field": "run-id"}
        assert run_fields["state-root"]["v"] == "state/run"
        assert run_fields["artifact-root"]["v"] == "artifacts/run"


@pytest.mark.parametrize("partition", ("phase-from-phase", "item-derived", "item-explicit"))
def test_phase_context_partitions_keep_exact_source_routes_and_readback(
    tmp_path: Path,
    partition: str,
) -> None:
    if partition == "phase-from-phase":
        body = '''(defworkflow entry ((outer PhaseCtx)) -> Symbol
          (with-phase outer plan-gate-wrapper (call leaf)))''' + _LEAF
        target = "leaf"
    else:
        item = '''(record ItemCtx
          :run (record RunCtx :run-id run_id :state-root run_state :artifact-root run_artifacts)
          :item-id "one" :state-root item_state :artifact-root item_artifacts :ledger ledger)'''
        explicit = ""
        if partition == "item-explicit":
            explicit = ''' :phase-ctx (record PhaseCtx :run item-ctx.run
              :phase-name payload.phase :state-root item-ctx.state-root
              :artifact-root item-ctx.artifact-root)'''
        body = f'''(defrecord Payload (n Int) (phase Symbol))
          (defworkflow entry ((run_id RunId) (run_state Path.state-root)
              (run_artifacts Path.artifact-root) (item_state Path.state-root)
              (item_artifacts Path.artifact-root) (ledger Path.state-root)
              (phase_name Symbol)) -> Symbol
            (call parent :item-ctx {item}
              :payload (record Payload :n 7 :phase phase_name)))
          (defworkflow parent ((item-ctx ItemCtx) (payload Payload)) -> Symbol
            (call child :payload payload{explicit}))
          (defworkflow child ((phase-ctx PhaseCtx) (payload Payload)) -> Symbol
            (with-phase phase-ctx child-phase phase-ctx.phase-name))'''
        target = "child"

    root = tmp_path / partition
    path, typed = _compile(root, body)
    signatures = {
        name: tuple(workflow.signature.params)
        for name, workflow in typed.workflows.items()
    }
    path.unlink()
    built = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(built.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        built.tree,
        built.sites,
        built.digest,
    )
    assert signatures == {
        name: tuple(workflow.signature.params)
        for name, workflow in typed.workflows.items()
    }
    target_name, target_row = next(
        (name, row)
        for name, row in restored.tree["definitions"].items()
        if row["key"][:3] == ["context_probe", "workflow", target]
    )
    bodies = [restored.tree["body"], *(row["body"] for row in restored.tree["definitions"].values())]
    calls = [
        node
        for body_node in bodies
        for node in _walk(body_node)
        if isinstance(node, dict) and node.get("k") == "call" and node.get("callee") == target_name
    ]
    assert len(calls) == 1
    call = calls[0]
    value = call["args"][0]
    all_lets = {
        node["name"]: node["value"]
        for body_node in bodies
        for node in _walk(body_node)
        if isinstance(node, dict) and node.get("k") == "let"
    }
    visited = set()
    while value.get("k") == "name" and value["n"] in all_lets:
        assert value["n"] not in visited
        visited.add(value["n"])
        value = all_lets[value["n"]]
    assert value["k"] == "record"
    fields_by_name = dict(value["fields"])
    if partition == "phase-from-phase":
        assert value["type"]["name"] == "std/context::PhaseCtx"
        assert fields_by_name["run"] == {
            "k": "field", "base": {"k": "name", "n": "outer"}, "path": ["run"]
        }
        assert fields_by_name["phase-name"]["v"] == "plan-gate-wrapper"
        assert fields_by_name["state-root"]["v"] == "state/plan-gate-wrapper"
        assert fields_by_name["artifact-root"]["v"] == "artifacts/plan-gate-wrapper"
    else:
        assert value["type"]["name"] == "std/context::PhaseCtx"
        if partition == "item-derived":
            assert fields_by_name["run"] == {
                "k": "field", "base": {"k": "name", "n": "item-ctx"}, "path": ["run"]
            }
            assert fields_by_name["phase-name"]["v"] == "child-phase"
            assert fields_by_name["state-root"]["v"] == "state/child-phase"
            assert fields_by_name["artifact-root"]["v"] == "artifacts/child-phase"
        else:
            for field_name, base_name, path_name in (
                ("run", "item-ctx", "run"),
                ("phase-name", "payload", "phase"),
                ("state-root", "item-ctx", "state-root"),
                ("artifact-root", "item-ctx", "artifact-root"),
            ):
                field = fields_by_name[field_name]
                assert field["k"] == "field"
                assert field["base"]["k"] == "name"
                assert field["base"]["n"] == base_name
                assert field["path"] == [path_name]


def test_evaluated_execution_rejects_provider_bundle_path_outside_runs(tmp_path: Path) -> None:
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule context_probe) (export entry)
      (defpath SelectionPath :kind relpath :under "state" :must-exist false)
      (defrecord Decision (value String))
      (defworkflow entry ((decision Decision)) -> SelectionPath
        (provider-bundle-path decision :as SelectionPath)))'''
    path = install(tmp_path, source)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_typed_program(
            path,
            entry_workflow="entry",
            source_roots=(tmp_path,),
            command_boundaries={},
            workspace_root=tmp_path,
        )
    assert any(
        diagnostic.code == "provider_bundle_path_target_invalid"
        for diagnostic in excinfo.value.diagnostics
    )


def test_provider_bundle_path_translates_with_its_exact_runs_descriptor(tmp_path: Path) -> None:
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule result_path_probe) (export entry)
      (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
      (defrecord Result (text String))
      (defrecord Projection (bundle ResultBundle))
      (defworkflow entry ((seed String)) -> Projection
        (let* ((r (provider-result provider :prompt prompt :inputs (seed) :returns Result)))
          (record Projection :bundle (provider-bundle-path r :as ResultBundle)))))'''
    path = install(tmp_path, source)
    typed = compile_typed_program(
        path,
        entry_workflow="entry",
        source_roots=(tmp_path,),
        command_boundaries={},
        provider_externs={"provider": "probe-provider"},
        prompt_externs={
            "prompt": PromptExtern(name="prompt", input_file="inputs/prompt.md")
        },
        workspace_root=tmp_path,
    )
    entry = typed.entry
    owner = entry.definition.name
    body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow_body(
            entry.typed_body,
            owner_name=owner,
            type_env=typed.workflow_type_env(owner),
            value_env=dict(entry.signature.params),
            workflow_return_types={owner: entry.signature.return_type_ref},
            procedure_return_types={},
            resolved_procedures_by_name=typed.procedures,
            procedure_type_envs=typed.procedure_type_envs,
            closed_program=True,
        )
    )
    (value,) = [
        node for node in _walk(body)
        if isinstance(node, WccOpaqueFrontendValue)
        and isinstance(node.expr, ProviderBundlePathExpr)
    ]
    builder = Builder(typed)
    definition = builder.definition_context(
        canonical="workflow:result_path_probe::entry",
        owner=owner,
        source_program=typed,
        type_env=typed.workflow_type_env(owner),
        node=entry.typed_body,
        params=entry.definition.params,
    )
    definition.names = {value.expr.source_expr.name: "provider_result"}
    translated = builder.value(value, definition, dict(entry.signature.params))
    assert {key: child for key, child in translated.items() if key != "@"} == {
        "k": "result_path",
        "n": "provider_result",
        "type": canonical_type_descriptor(value.metadata.type_ref, typed=typed),
    }


def test_compiled_import_keeps_its_native_body_and_explicit_context_route(tmp_path: Path) -> None:
    producer_source = '''(workflow-lisp
      (:language "0.1") (:target-dsl "2.34")
      (defmodule producer) (import std/phase :only (with-phase))
      (export entry run-phase)
      (defrecord RunCtx (run-id RunId) (state-root Path.state-root) (artifact-root Path.artifact-root))
      (defrecord PhaseCtx (run RunCtx) (phase-name Symbol) (state-root Path.state-root) (artifact-root Path.artifact-root))
      (defrecord Pair (x String) (y String))
      (defrecord Result (label String) (phase_name Symbol))
      (defworkflow entry ((pair Pair)) -> Result
        (call run-phase :a__x pair.x :a__y pair.y))
      (defworkflow run-phase ((phase__ctx PhaseCtx) (a__x String) (a__y String)) -> Result
        (with-phase phase__ctx plan-gate-wrapper
          (record Result :label a__x :phase_name phase__ctx.phase-name))))'''
    consumer_source = f'''(workflow-lisp
      (:language "0.1") (:target-dsl "{TARGET}") (defmodule consumer) (export run)
      (defrecord RunCtx (run-id RunId) (state-root Path.state-root) (artifact-root Path.artifact-root))
      (defrecord PhaseCtx (run RunCtx) (phase-name Symbol) (state-root Path.state-root) (artifact-root Path.artifact-root))
      (defrecord Pair (x String) (y String))
      (defrecord Result (label String) (phase_name Symbol))
      (defworkflow run ((pair Pair) (ctx PhaseCtx)) -> Result
        (call dep :pair pair :phase__ctx ctx)))'''
    producer_root = tmp_path / "producer"
    producer_root.mkdir()
    producer_path = install(producer_root, producer_source)
    loaded = compile_stage3_entrypoint(
        producer_path,
        source_roots=(producer_root,),
        validate_shared=True,
        workspace_root=producer_root,
    )
    bundle = loaded.validated_bundles_by_name["producer::entry"]
    consumer_root = tmp_path / "consumer"
    consumer_root.mkdir()
    consumer_path = install(consumer_root, consumer_source)
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(consumer_root,),
        command_boundaries={},
        imported_workflow_bundles={"dep": bundle},
        workspace_root=consumer_root,
    )
    producer_path.unlink()
    consumer_path.unlink()

    closed = build_closed_program(typed)
    from orchestrator.workflow_lisp.closed.program import ClosedProgram

    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )
    imported = [
        (name, definition) for name, definition in closed.tree["definitions"].items()
        if definition["key"][:3] == ["producer", "workflow", "entry"]
    ]
    assert len(imported) == 1
    imported_name, imported_definition = imported[0]
    assert len(imported_definition["key"][7]) == 1
    outer_call = next(
        node for node in _walk(closed.tree["body"])
        if node.get("k") == "call" and node.get("callee") == imported_name
    )
    assert outer_call["args"][0]["k"] == "name"
    assert outer_call["args"][0]["n"] == "ctx"
    assert imported_definition["key"][7][0]["routes"][0][0] == "context"


def test_imported_capture_resolves_native_context_after_omitted_and_explicit_calls(
    tmp_path: Path,
) -> None:
    base_producer = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule producer) (import std/context :only (PhaseCtx))
      (import std/phase :only (with-phase)) (export entry run-phase)
      (defworkflow entry ((payload Int)) -> Int
        (call run-phase :payload payload))
      (defworkflow run-phase ((phase__ctx PhaseCtx) (payload Int)) -> Int
        (with-phase phase__ctx plan-gate-wrapper payload)))'''
    base_consumer = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule consumer) (import std/context :only (PhaseCtx)) (export run)
      (defworkflow run ((payload Int) (ctx PhaseCtx)) -> Int
        (call dep :payload payload :phase__ctx ctx)))'''
    body = '''(let* ((first (call run-phase :payload payload))
      (second (call run-phase :phase__ctx explicit :payload payload))
      (third (call run-phase :payload payload))) third)'''
    custom_context = '''(defrecord RunCtx (run-id RunId) (state-root Path.state-root)
      (artifact-root Path.artifact-root))
      (defrecord PhaseCtx (run RunCtx) (phase-name Symbol)
        (state-root Path.state-root) (artifact-root Path.artifact-root))'''
    digests: dict[str, str] = {}

    for owner_kind in ("shared", "caller-private", "transitive"):
        for location in ("one", "relocated/deeper"):
            root = tmp_path / owner_kind / location
            root.mkdir(parents=True)
            producer_source = base_producer.replace(
                "((payload Int)) -> Int",
                "((payload Int) (explicit PhaseCtx)) -> Int",
                1,
            ).replace("(call run-phase :payload payload)", body, 1)
            if owner_kind == "transitive":
                producer_source = (
                    producer_source.replace(
                        "(export entry run-phase)", "(export entry middle run-phase)"
                    )
                    .replace(body, "(call middle :payload payload :explicit explicit)", 1)
                    .replace(
                        "(defworkflow run-phase",
                        f"(defworkflow middle ((payload Int) (explicit PhaseCtx)) -> Int {body})\n"
                        "      (defworkflow run-phase",
                        1,
                    )
                )
            consumer_source = base_consumer.replace(
                "((payload Int) (ctx PhaseCtx))",
                "((payload Int) (ctx PhaseCtx) (explicit PhaseCtx))",
                1,
            ).replace(
                ":payload payload :phase__ctx ctx)",
                ":payload payload :phase__ctx ctx :explicit explicit)",
                1,
            )
            caller_name = "std/context::PhaseCtx"
            if owner_kind == "caller-private":
                consumer_source = consumer_source.replace(
                    "(import std/context :only (PhaseCtx))", "", 1
                ).replace("(export run)", f"(export run) {custom_context}", 1)
                caller_name = "consumer::PhaseCtx"

            producer_path = install(root, producer_source)
            old = compile_stage3_entrypoint(
                producer_path,
                source_roots=(root,),
                validate_shared=True,
                workspace_root=root,
            )
            bundle = old.validated_bundles_by_name["producer::entry"]
            native = bundle.typed_program
            signatures = {
                name: tuple(workflow.signature.params)
                for name, workflow in native.workflows.items()
            }
            consumer_path = install(root, consumer_source)
            typed = compile_typed_program(
                consumer_path,
                entry_workflow="consumer::run",
                source_roots=(root,),
                command_boundaries={},
                imported_workflow_bundles={"dep": bundle},
                workspace_root=root,
            )

            native_ref = dict(native.entry.signature.params)["explicit"]
            caller_ref = dict(typed.entry.signature.params)["ctx"]
            assert canonical_type_descriptor(native_ref, typed=typed)["name"] == (
                "std/context::PhaseCtx"
            )
            assert canonical_type_descriptor(caller_ref, typed=typed)["name"] == caller_name
            forged = replace(native_ref, definition=replace(native_ref.definition))
            with pytest.raises(CanonicalNameError):
                canonical_type_descriptor(forged, typed=typed)

            producer_path.unlink()
            consumer_path.unlink()
            closed = build_closed_program(typed)
            restored = ClosedProgram.from_artifact(closed.artifact())
            assert (restored.tree, restored.sites, restored.digest) == (
                closed.tree,
                closed.sites,
                closed.digest,
            )
            assert signatures == {
                name: tuple(workflow.signature.params)
                for name, workflow in native.workflows.items()
            }
            rows = {
                definition["key"][2]: definition
                for definition in restored.tree["definitions"].values()
                if definition["key"][:2] == ["producer", "workflow"]
            }
            entry = rows["entry"]
            leaf = rows["run-phase"]
            assert len(entry["key"][7]) == 1
            assert entry["key"][7][0]["type"]["name"] == caller_name
            assert entry["key"][8]["params"][1]["name"] == "std/context::PhaseCtx"
            assert leaf["key"][7] == []

            wrapper = rows["middle"] if owner_kind == "transitive" else entry
            calls = [node for node in _walk(wrapper["body"]) if node.get("k") == "call"]
            assert len(calls) == 3
            capture = wrapper["params"][0][0]
            assert calls[0]["args"][0] == calls[2]["args"][0] == {
                "k": "name",
                "n": capture,
            }
            assert calls[1]["args"][0]["k"] == "name"
            assert calls[1]["args"][0]["n"] == "explicit"
            assert [route[1] for route in wrapper["key"][7][0]["routes"]] == [
                [[["producer", "workflow", "run-phase"], 0]],
                [[["producer", "workflow", "run-phase"], 2]],
            ]
            if owner_kind == "transitive":
                assert [route[1] for route in entry["key"][7][0]["routes"]] == [
                    [
                        [["producer", "workflow", "middle"], 0],
                        [["producer", "workflow", "run-phase"], 0],
                    ],
                    [
                        [["producer", "workflow", "middle"], 0],
                        [["producer", "workflow", "run-phase"], 2],
                    ],
                ]
            if location == "one":
                digests[owner_kind] = closed.digest
            else:
                assert digests[owner_kind] == closed.digest


def test_old_native_record_path_boundary_keeps_1_to_n_views_defaults_and_order(
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
    flat = compile_stage3_entrypoint(
        producer_path,
        entry_workflow="producer::get",
        source_roots=(producer_root,),
        validate_shared=True,
        workspace_root=producer_root,
    )
    bundle = flat.validated_bundles_by_name["producer::get"]
    native_params = tuple(bundle.typed_program.entry.signature.params)

    consumer_root = tmp_path / "consumer"
    consumer_root.mkdir()
    consumer_path = install(
        consumer_root,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule consumer) (export run)
          (defpath Report :kind relpath :under "reports" :must-exist false)
          (defrecord Pair (x Report) (y Report))
          (defrecord Result (left Report) (right Report) (count Int))
          (defworkflow run ((pair Pair)) -> Result
            (let* ((defaulted (call dep :a pair))
                   (supplied
                     (call dep
                       :count (provider-result count-provider :prompt prompt :inputs () :returns Int)
                       :a (provider-result pair-provider :prompt prompt :inputs () :returns Pair)))
                   (unused defaulted))
              supplied)))''',
    )
    (consumer_root / "prompt.md").write_text("compile-only prompt input", encoding="utf-8")
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="consumer::run",
        source_roots=(consumer_root,),
        command_boundaries={},
        provider_externs={
            "count-provider": "count-provider",
            "pair-provider": "pair-provider",
        },
        prompt_externs={
            "prompt": PromptExtern(name="prompt", input_file="prompt.md")
        },
        imported_workflow_bundles={"dep": bundle},
        workspace_root=consumer_root,
    )
    producer_path.unlink()
    consumer_path.unlink()

    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        program.tree,
        program.sites,
        program.digest,
    )
    assert tuple(bundle.typed_program.entry.signature.params) == native_params

    definitions = program.tree["definitions"]
    owner, native = next(
        (name, definition)
        for name, definition in definitions.items()
        if definition["key"][:3] == ["producer", "workflow", "get"]
    )
    assert [name for name, _type in native["params"]] == ["a__x", "a__y", "count"]
    assert [param_type["name"] for _name, param_type in native["params"][:2]] == [
        "producer::Report",
        "producer::Report",
    ]
    assert native["params"][2][1] == {"kind": "primitive", "name": "Int"}
    assert native["result"]["name"] == "producer::Result"
    assert [field["type"]["name"] for field in native["result"]["fields"][:2]] == [
        "producer::Report",
        "producer::Report",
    ]

    calls = [
        node for node in _walk(program.tree["body"])
        if node.get("k") == "call" and node.get("callee") == owner
    ]
    assert len(calls) == 2
    expected_outputs = [
        {
            "name": "return__left",
            "path": ["return", "left"],
            "contract": {
                "kind": "relpath",
                "type": "relpath",
                "under": "reports",
                "must_exist_target": False,
            },
        },
        {
            "name": "return__right",
            "path": ["return", "right"],
            "contract": {
                "kind": "relpath",
                "type": "relpath",
                "under": "reports",
                "must_exist_target": False,
            },
        },
        {
            "name": "return__count",
            "path": ["return", "count"],
            "contract": {"kind": "scalar", "type": "integer"},
        },
    ]
    for call in calls:
        boundary = call["boundary"]
        params = dict(boundary["params"])
        assert [name for name, _type in boundary["params"]] == ["a", "count"]
        assert len(call["args"]) == len(boundary["params"]) == 2
        assert params["a"]["name"] == "consumer::Pair"
        assert [field["type"]["name"] for field in params["a"]["fields"]] == [
            "consumer::Report",
            "consumer::Report",
        ]
        assert params["count"] == {"kind": "primitive", "name": "Int"}
        assert call["type"]["name"] == "consumer::Result"
        assert boundary["inputs"]["caller"] == [
            {"name": "a__x", "path": ["a", "x"], "contract": expected_outputs[0]["contract"]},
            {"name": "a__y", "path": ["a", "y"], "contract": expected_outputs[1]["contract"]},
            {"name": "count", "path": ["count"], "contract": expected_outputs[2]["contract"]},
        ]
        assert boundary["inputs"]["callee"] == [
            {"name": "a__x", "path": ["a__x"], "contract": expected_outputs[0]["contract"]},
            {"name": "a__y", "path": ["a__y"], "contract": expected_outputs[1]["contract"]},
            {"name": "count", "path": ["count"], "contract": expected_outputs[2]["contract"]},
        ]
        assert boundary["outputs"]["caller"] == expected_outputs
        assert boundary["outputs"]["callee"] == expected_outputs
        assert boundary["direct"] == []
    assert calls[0]["args"][1]["k"] == "lit" and calls[0]["args"][1]["v"] == 3
    first_source_effects = [
        node.get("provider")
        for node in _walk(program.tree["body"])
        if node.get("k") == "perform"
    ]
    assert first_source_effects == ["count-provider", "pair-provider"]
    second_call = calls[1]
    producer_bindings = {
        node["name"]: node["value"]["provider"]
        for node in _walk(program.tree["body"])
        if node.get("k") == "let" and node.get("value", {}).get("k") == "perform"
    }
    aliases = {
        node["name"]: node["value"]["n"]
        for node in _walk(program.tree["body"])
        if node.get("k") == "let" and node.get("value", {}).get("k") == "name"
    }
    assert [producer_bindings[aliases[arg["n"]]] for arg in second_call["args"]] == [
        "pair-provider",
        "count-provider",
    ]
