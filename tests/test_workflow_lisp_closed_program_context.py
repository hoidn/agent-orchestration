from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.names import canonical_type_descriptor
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import ProviderBundlePathExpr
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.model import WccOpaqueFrontendValue
from orchestrator.workflow_lisp.workflows import PromptExtern
from tests.workflow_lisp_closed_program_helpers import install


_PREAMBLE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule context_probe)
  (import std/context :only (RunCtx PhaseCtx))
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
    body = closed.tree["body"]
    assert closed.tree["params"] == []
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
    assert signatures == {
        name: tuple(workflow.signature.params)
        for name, workflow in typed.workflows.items()
    }
    call = next(
        node for node in _walk(closed.tree["body"])
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


def test_evaluated_execution_rejects_provider_bundle_path_outside_runs(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
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
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
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
    consumer_source = '''(workflow-lisp
      (:language "0.1") (:target-dsl "2.35") (defmodule consumer) (export run)
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
