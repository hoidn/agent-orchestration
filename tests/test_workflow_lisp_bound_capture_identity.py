"""Binding identity at preparation and actual provider input boundaries."""

import json

import pytest

from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
from tests.workflow_evaluated_consumer_sources import install_shims, requests


HEADER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
(defmodule bound_identity) (export run)
(defrecord Pair (left String) (right String))
(defprompt label (:fills (value :text)) -> String "{value}")
(defproc hook ((n Int) (label String)) -> String
 :effects ((uses-provider providers.test)) :lowering inline
 (provider-result providers.test :prompt (label :value label) :model "gpt-6-sol"))
(defproc apply :forall (T)
 ((n T) (left ProcRef[T -> String]) (right ProcRef[T -> String]))
 -> Pair :effects () :lowering inline
 (let* ((l (left n)) (r (right n))) (record Pair :left l :right r)))
'''
NAMED = '(let* ((left (bind-proc (proc-ref hook) :label a)) '
NAMED += '(right (bind-proc (proc-ref hook) :label b))) (apply 1 left right))'
SHADOW = '(let* ((left (bind-proc (proc-ref hook) :label a)) '
SHADOW += '(a "shadow") (right (bind-proc (proc-ref hook) :label "right"))) '
SHADOW += '(apply 1 left right))'


def _install(root, body, *, declarations=""):
    root.mkdir(parents=True, exist_ok=True)
    source = root / "bound_identity.orc"
    source.write_text(HEADER + declarations +
        '(defworkflow run ((a String) (b String)) -> Pair ' + body + '))\n')
    (root / "providers.json").write_text(json.dumps({"providers.test": "codex"}))
    return source


def _typed(root, body, *, declarations=""):
    source = _install(root, body, declarations=declarations)
    return compile_typed_program(source, entry_workflow="bound_identity::run",
        source_roots=(root,), workspace_root=root,
        provider_externs={"providers.test": "codex"}, command_boundaries={})


def _public_inputs(root, monkeypatch, body, *, declarations="", results=None):
    _install(root, body, declarations=declarations)
    inputs = {"a": str(root / "creation-value"), "b": str(root / "other-value")}
    (root / "inputs.json").write_text(json.dumps(inputs))
    results = results or [{"result": "first"}, {"result": "second"}]
    install_shims(root / "bin", monkeypatch, {"codex": results})
    run = _run_cli(root, "bound_identity.orc", "--entry-workflow", "bound_identity::run",
        "--source-root", ".", "--provider-externs-file", "providers.json",
        "--input-file", "inputs.json")
    assert run.returncode == 0, run.stdout + run.stderr
    # This fixture's prompt consists of its one dynamic value. Inspect the
    # delivered data, independent of the shim's predetermined response.
    delivered = [row["prompt"].splitlines()[0] for row in requests(root)]
    return inputs, delivered


def test_distinct_named_captures_keep_their_prepared_slots(tmp_path):
    program = _typed(tmp_path, NAMED)
    _, children, _ = _prepared_entry(program)
    request, = children.values()
    assert len(request.captures) == 2
    closed = build_closed_program(program)
    assert closed.tree["definitions"]


def test_created_hook_delivers_original_binding_after_shadow(tmp_path, monkeypatch):
    inputs, delivered = _public_inputs(tmp_path, monkeypatch, SHADOW)
    assert delivered == [inputs["a"], "right"]


DIRECT = '(apply 1 (bind-proc (proc-ref hook) :label a) '
DIRECT += '(bind-proc (proc-ref hook) :label b))'
FORWARD = '(defproc forward ((n Int) (left ProcRef[Int -> String]) '
FORWARD += '(right ProcRef[Int -> String])) -> Pair :effects () :lowering inline '
FORWARD += '(apply n left right))'
PROXY = '(defproc proxy ((callback ProcRef[Int -> String]) (n Int)) -> String '
PROXY += ':effects () :lowering inline (callback n))'
PARTITIONS = [
    pytest.param(DIRECT, "", 2, id="direct-distinct"),
    pytest.param(NAMED.replace(":label b", ":label a"), "", 1, id="named-shared"),
    pytest.param(DIRECT.replace(":label b", ":label a"), "", 1, id="direct-shared"),
    pytest.param('(let* ((x a) (y b)) ' + NAMED.replace(":label a", ":label x").replace(
        ":label b", ":label y") + ')', "", 2, id="distinct-aliases"),
    pytest.param('(let* ((x a) (y a)) ' + NAMED.replace(":label a", ":label x").replace(
        ":label b", ":label y") + ')', "", 2, id="equal-value-distinct-binders"),
    pytest.param('(let* ((left (bind-proc (proc-ref hook) :label a))) '
        '(apply 1 left (bind-proc (proc-ref hook) :label a)))', "", 1, id="mixed-shared"),
    pytest.param(NAMED.replace('(apply 1', '(forward 1'), FORWARD, 2, id="forwarded"),
    pytest.param('(apply 1 (bind-proc (proc-ref proxy) :callback '
        '(bind-proc (proc-ref hook) :label a)) '
        '(bind-proc (proc-ref hook) :label b))', PROXY, 2, id="nested-reference"),
]


@pytest.mark.parametrize("body,declarations,slots", PARTITIONS)
def test_runtime_capture_partition_matches_lexical_binders(tmp_path, body, declarations, slots):
    program = _typed(tmp_path, body, declarations=declarations)
    _, children, _ = _prepared_entry(program)
    request, = children.values()
    assert len(request.captures) == slots
    closed = build_closed_program(program)
    assert closed.tree["definitions"]


@pytest.mark.parametrize("forwarded", [False, True])
def test_distinct_hook_inputs_reach_the_provider_separately(tmp_path, monkeypatch, forwarded):
    body = NAMED.replace("(apply 1", "(forward 1") if forwarded else NAMED
    declarations = FORWARD if forwarded else ""
    inputs, delivered = _public_inputs(tmp_path, monkeypatch, body, declarations=declarations)
    assert delivered == [inputs["a"], inputs["b"]]


@pytest.mark.parametrize("owner", ["procedure", "workflow"])
def test_shadow_retention_belongs_to_the_reconstructed_body(tmp_path, monkeypatch, owner):
    if owner == "procedure":
        declarations = '(defproc owner ((a String) (b String)) -> Pair '
        declarations += ':effects ((uses-provider providers.test)) :lowering inline ' + SHADOW + ')'
        body = '(owner a b)'
    else:
        declarations = '(defworkflow owner ((a String) (b String)) -> Pair ' + SHADOW + ')'
        body = '(call owner :a a :b b)'
    inputs, delivered = _public_inputs(tmp_path, monkeypatch, body, declarations=declarations)
    assert delivered == [inputs["a"], "right"]


def test_bound_value_comes_from_the_committed_provider_result(tmp_path, monkeypatch):
    body = '(let* ((saved (provider-result providers.test '
    body += ':prompt (label :value a) :model "gpt-6-sol"))) '
    body += NAMED.replace(":label a", ":label saved") + ')'
    results = [{"result": "committed-provider-value"}, {"result": "left"}, {"result": "right"}]
    inputs, delivered = _public_inputs(tmp_path, monkeypatch, body, results=results)
    assert delivered == [inputs["a"], results[0]["result"], inputs["b"]]


def test_cached_preparation_still_demands_the_callers_original_binder(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed.build import Builder

    body = '(let* ((left (bind-proc (proc-ref hook) :label a)) '
    body += '(right (bind-proc (proc-ref hook) :label a)) (first (apply 1 left right))) '
    body += '(let* ((a "shadow") (second (apply 1 left right))) second))'
    original = Builder._call_request
    hits = []

    def observe(builder, procedure, source, call, context, **kwargs):
        previous = tuple(builder.completed_preparations.values())
        result = original(builder, procedure, source, call, context, **kwargs)
        if context.owner == "bound_identity::run":
            hits.append(any(result is request for request in previous))
        return result

    monkeypatch.setattr(Builder, "_call_request", observe)
    build_closed_program(_typed(tmp_path, body))
    assert hits.count(True) == 1
    results = [{"result": str(index)} for index in range(4)]
    inputs, delivered = _public_inputs(tmp_path, monkeypatch, body, results=results)
    assert delivered == [inputs["a"]] * 4
