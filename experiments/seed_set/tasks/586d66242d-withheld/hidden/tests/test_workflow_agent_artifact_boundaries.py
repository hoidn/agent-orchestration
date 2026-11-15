"""Stored closed artifacts preserve the Agent trust boundaries of checked source."""
from __future__ import annotations

import io
import json
from copy import deepcopy

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram, ClosedProgramInvalid
from orchestrator.workflow.type_descriptor import compiled_boundary_rows
from orchestrator.contracts.closed_program.sites import _ast_nodes, assign_sites
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.prompts import assemble_provider_prompt
from orchestrator.workflow.evaluated.values import EvaluatedValue
from orchestrator.workflow.agent_value import reject_agent_operand
from orchestrator.workflow.pure_expr import PureExprEvaluationError
from tests.test_workflow_lisp_agent_turn_admission import ALIAS, HEADER, TWO_AGENTS, _request, _turns
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle

AGENT = {"kind": "primitive", "name": "Agent"}
STRING = {"kind": "primitive", "name": "String"}
HANDLE = {"run_id": "r", "identity": "allocated", "provider": "claude_unrestricted_workspace",
          "policy": {}, "config_digest": "sha256:" + "0" * 64}


@pytest.mark.parametrize("descriptor", [
    {"kind": "optional", "item": AGENT},
    {"kind": "list", "item": {"kind": "optional", "item": AGENT}},
    {"kind": "map", "key": STRING, "value": AGENT},
    {"kind": "map", "key": AGENT, "value": STRING},
    {"kind": "record", "name": "Team", "fields": [{"name": "lead", "type": AGENT}]},
    {"kind": "union", "name": "Pick", "variants": [{"name": "yes", "fields": [{"name": "lead", "type": AGENT}]}]},
    {"kind": "variant_case", "union_name": "Pick", "variant": "yes", "fields": [{"name": "lead", "type": AGENT}]},
])
@pytest.mark.parametrize("operator", ["print", "=", "!="])
def test_pure_conversion_guard_checks_every_aggregate_shape(descriptor, operator):
    with pytest.raises(PureExprEvaluationError):
        reject_agent_operand([descriptor], operator)


def _tree(tmp_path, source=ALIAS):
    return deepcopy(build_closed_program_bundle(_request(tmp_path, source)).program.tree)


def _load(tree):
    tree["sites"] = [list(row) for row in assign_sites(tree)]
    return ClosedProgram.from_artifact(json.dumps(tree))


def _halt(tree):
    return tree["body"]["body"]["body"]


def _list_agent():
    return {"k": "list", "type": {"kind": "list", "item": AGENT}, "items": [{"k": "name", "n": "b"}]}


def _perform_log(log):
    def perform(node, operands, identity, owner, reader):
        log.append(node["class"])
        if node["class"] == "agent":
            return EvaluatedValue({**HANDLE, "identity": identity}, AGENT)
        view = {k: v for k, v in node.items() if k not in {"agent", "origins"}}
        view.update({"class": "provider", "provider": HANDLE["provider"]})
        rendered = assemble_provider_prompt(view, operands[1:] if node["class"] == "agent_turn" else operands,
                                            source_text="P", dependency_snapshot=None, result_path="result.json")
        assert "config_digest" not in rendered
        return EvaluatedValue({"text": "done"}, node["result"])
    return perform


@pytest.mark.parametrize("nested", [False, True])
def test_public_loader_blocks_provider_agent_data_before_dispatch(tmp_path, nested):
    tree = _tree(tmp_path, ALIAS.replace('(ask :task task)', 'prompts.base :inputs (task) :returns Note'))
    _turns(tree)[0]["inputs"] = [["handle", "canonical-json", _list_agent() if nested else {"k": "name", "n": "b"}]]
    log = []
    with pytest.raises(ClosedProgramInvalid) as exc:
        evaluate_closed_program(_load(tree), {"task": "t"}, effect_handler=_perform_log(log), run_id="r")
    assert exc.value.rule == "agent_transport_forbidden"
    assert log == []


@pytest.mark.parametrize("descriptor", [AGENT, {"kind": "list", "item": AGENT},
    {"kind": "optional", "item": AGENT}, {"kind": "map", "key": STRING, "value": AGENT}])
def test_public_loader_refuses_agent_entry_parameters(tmp_path, descriptor):
    tree = _tree(tmp_path)
    tree["params"].append(["injected", descriptor])
    with pytest.raises(ClosedProgramInvalid, match="agent_transport_forbidden"):
        _load(tree)


@pytest.mark.parametrize("nested", [False, True])
def test_public_loader_refuses_agent_workflow_results(tmp_path, nested):
    tree = _tree(tmp_path)
    value = _list_agent() if nested else {"k": "name", "n": "b"}
    tree["result"] = value["type"] if nested else AGENT
    tree["body"]["body"]["body"] = {"k": "halt", "value": value}
    with pytest.raises(ClosedProgramInvalid, match="agent_transport_forbidden"):
        _load(tree)


def test_public_loader_refuses_print_of_nested_agent(tmp_path):
    tree = _tree(tmp_path)
    value = _list_agent()
    payload = {"pure_expr_schema_version": 2, "result_type": value["type"],
               "bindings": {"a0": {"type": value["type"]}},
               "expr": {"kind": "op", "operator": "print", "args": [{"kind": "binding", "name": "a0"}]}}
    tree["body"]["body"]["body"] = {"k": "let", "name": "printed",
        "value": {"k": "op", "payload": payload, "args": [value]}, "body": _halt(tree)}
    sink, log = io.StringIO(), []
    with pytest.raises(ClosedProgramInvalid, match="payload_invalid"):
        evaluate_closed_program(_load(tree), {"task": "t"}, effect_handler=_perform_log(log), print_sink=sink)
    assert sink.getvalue() == "" and log == []


@pytest.mark.parametrize("target", ["2.35", "2.36", "2.37"])
def test_agent_descriptor_requires_target_238_even_without_agent_effect(tmp_path, target):
    tree = _tree(tmp_path, HEADER + '(defworkflow run ((task String)) -> Note (record Note :text task)))')
    tree["types"]["Team"] = {"kind": "record", "name": "Team", "fields": [{"name": "lead", "type": AGENT}]}
    tree["target"] = target
    with pytest.raises(ClosedProgramInvalid, match="agent_target_dsl_unsupported"):
        _load(tree)


def test_public_loader_refuses_forged_agent_literal(tmp_path):
    tree = _tree(tmp_path)
    tree["body"]["body"]["value"] = {"k": "lit", "type": AGENT, "v": HANDLE}
    with pytest.raises(ClosedProgramInvalid, match="agent_transport_forbidden"):
        _load(tree)


def test_public_loader_refuses_agent_command_argv(tmp_path):
    source = HEADER + '(defworkflow run ((task String)) -> Note (let* ((a (agent providers.claude)) ' \
        '(x (command-result tool :argv ("python" "t.py" task) :returns String))) (record Note :text x))))'
    tree = _tree(tmp_path, source)
    command = next(n for n in _ast_nodes(tree["body"]) if n.get("class") == "command")
    command["argv"][-1] = {"k": "name", "n": "a"}
    with pytest.raises(ClosedProgramInvalid, match="agent_transport_forbidden"):
        _load(tree)


@pytest.mark.parametrize("boundary", ["state", "result"])
def test_public_loader_refuses_agent_loop_state_and_result(tmp_path, boundary):
    source = HEADER + '(defworkflow run ((task String)) -> Note (let* ((a (agent providers.claude))) ' \
        '(loop/recur :max 1 :state (loop-state (n String task)) ' \
        ':on-exhausted (record Note :text "x") (fn (state) (done (record Note :text "x")))))))'
    tree = _tree(tmp_path, source)
    loop = next(n for n in _ast_nodes(tree["body"]) if n.get("k") == "loop")
    if boundary == "state":
        loop["state_type"] = AGENT
        loop["init"] = {"k": "name", "n": "a"}
    else:
        loop["result"] = AGENT
        loop["body"] = {"k": "done", "value": {"k": "name", "n": "a"}}
        loop["exhausted"] = {"k": "halt", "value": {"k": "name", "n": "a"}}
        tree["body"]["body"]["body"] = {"k": "let", "name": "discard", "value": {"k": "block", "body": loop},
            "body": {"k": "halt", "value": {"k": "record", "type": tree["result"],
                "fields": [["text", {"k": "lit", "type": STRING, "v": "done"}]]}}}
    with pytest.raises(ClosedProgramInvalid, match="agent_transport_forbidden"):
        _load(tree)


PARALLEL = HEADER + '(defworkflow run ((items List[String])) -> List[Note] ' \
    '(let* ((d (agent providers.claude))) (list/map-effect ((item items)) :max 2 :parallel 2 :workspace "." ' \
    '(provider-result providers.claude :prompt (ask :task item))))))'


def test_public_loader_refuses_captured_agent_in_parallel_worker(tmp_path):
    tree = _tree(tmp_path, PARALLEL)
    worker = next(n for n in _ast_nodes(tree["body"]) if n.get("k") == "par-map")
    worker["body"] = {"k": "let", "name": "captured", "value": {"k": "name", "n": "d"}, "body": worker["body"]}
    with pytest.raises(ClosedProgramInvalid, match="parallel_agent_boundary"):
        _load(tree)


def test_public_loader_refuses_agent_parallel_items_even_if_unused(tmp_path):
    tree = _tree(tmp_path, PARALLEL)
    worker = next(n for n in _ast_nodes(tree["body"]) if n.get("k") == "par-map")
    worker["source"] = {"k": "list", "type": {"kind": "list", "item": AGENT}, "items": [{"k": "name", "n": "d"}]}
    worker["item_type"] = AGENT
    # The item is deliberately unused: crossing the boundary itself is forbidden.
    turn = next(n for n in _ast_nodes(worker["body"]) if n.get("class") == "provider")
    turn["prompt"]["fills"][0]["value"] = {"k": "lit", "type": STRING, "v": "t"}
    with pytest.raises(ClosedProgramInvalid, match="parallel_agent_boundary"):
        _load(tree)


@pytest.mark.parametrize("mutation", ["workflow", "capture", "default"])
def test_public_loader_refuses_agent_workflow_keys_captures_and_defaults(tmp_path, mutation):
    tree = _tree(tmp_path, TWO_AGENTS)
    definition = next(iter(tree["definitions"].values()))
    if mutation == "workflow":
        definition["key"][1] = "workflow"
    elif mutation == "capture":
        definition["key"][7] = [{"type": AGENT, "routes": [["parameter", "who"]]}]
    else:
        definition["defaults"] = {"who": HANDLE}
    with pytest.raises(ClosedProgramInvalid, match="agent_transport_forbidden"):
        _load(tree)


def test_public_loader_refuses_agent_in_annotated_call_signature(tmp_path):
    tree = _tree(tmp_path, TWO_AGENTS)
    call = next(n for n in _ast_nodes(tree["body"]) if n.get("k") == "call")
    outputs = compiled_boundary_rows([("return", call["type"])], output=True)
    call["boundary"] = {"params": [["who", AGENT], ["task", STRING]], "direct": [[0, 0], [1, 1]],
                        "inputs": {"caller": [], "callee": []}, "outputs": {"caller": outputs, "callee": outputs}}
    with pytest.raises(ClosedProgramInvalid, match="agent_transport_forbidden"):
        _load(tree)


@pytest.mark.parametrize("fixed_binding", [False, True])
def test_public_loader_refuses_agent_construction_inside_pure_payload(tmp_path, fixed_binding):
    tree = _tree(tmp_path)
    payload = {"pure_expr_schema_version": 2, "result_type": AGENT, "bindings": {},
               "expr": {"kind": "literal", "type": AGENT, "value": HANDLE}}
    if fixed_binding:
        payload.update(bindings={"a0": {"type": AGENT, "value": HANDLE}}, expr={"kind": "binding", "name": "a0"})
    tree["body"]["body"]["value"] = {"k": "op", "payload": payload, "args": []}
    with pytest.raises(ClosedProgramInvalid, match="payload_invalid"):
        _load(tree)


def test_unused_outside_agent_and_shadowed_name_are_legal_in_parallel_worker(tmp_path):
    tree = _tree(tmp_path, PARALLEL)
    worker = next(n for n in _ast_nodes(tree["body"]) if n.get("k") == "par-map")
    worker["body"] = {"k": "let", "name": "d", "value": {"k": "name", "n": "item"},
        "body": {"k": "let", "name": "local", "value": {"k": "name", "n": "d"}, "body": worker["body"]}}
    assert _load(tree)


def test_local_aggregates_branch_selection_and_explicit_procedure_arguments_work(tmp_path):
    log = []
    result = evaluate_closed_program(_load(_tree(tmp_path, TWO_AGENTS)), {"task": "t", "pick": True},
                                     effect_handler=_perform_log(log), run_id="r")
    assert result.value == {"text": "done"}
    assert log == ["agent", "agent", "agent_turn", "agent_turn", "agent_turn", "agent_turn"]


def test_retained_imported_factory_can_return_an_agent(tmp_path):
    source = HEADER.replace('(export run)', '(import child :only (make)) (export run)') + \
        '(defworkflow run ((task String)) -> Note (let* ((who (make task))) ' \
        '(provider-result who :prompt (ask :task task)))))'
    request = _request(tmp_path, source)
    (tmp_path / "child.orc").write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.38") ' \
        '(defmodule child) (export make) (defproc make ((model String)) -> Agent ' \
        ':effects ((uses-provider providers.claude)) (agent providers.claude :model model)))')
    tree = deepcopy(build_closed_program_bundle(request).program.tree)
    factory = next(d for d in tree["definitions"].values() if d["result"] == AGENT)
    assert factory["key"][1] == "procedure" and factory["key"][7] == []
    log = []
    result = evaluate_closed_program(_load(tree), {"task": "t"}, effect_handler=_perform_log(log), run_id="r")
    assert result.value == {"text": "done"} and log == ["agent", "agent_turn"]
