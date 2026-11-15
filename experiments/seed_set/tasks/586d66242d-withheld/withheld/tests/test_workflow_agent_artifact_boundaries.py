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










@pytest.mark.parametrize("target", ["2.35", "2.36", "2.37"])
def test_agent_descriptor_requires_target_238_even_without_agent_effect(tmp_path, target):
    tree = _tree(tmp_path, HEADER + '(defworkflow run ((task String)) -> Note (record Note :text task)))')
    tree["types"]["Team"] = {"kind": "record", "name": "Team", "fields": [{"name": "lead", "type": AGENT}]}
    tree["target"] = target
    with pytest.raises(ClosedProgramInvalid, match="agent_target_dsl_unsupported"):
        _load(tree)








PARALLEL = HEADER + '(defworkflow run ((items List[String])) -> List[Note] ' \
    '(let* ((d (agent providers.claude))) (list/map-effect ((item items)) :max 2 :parallel 2 :workspace "." ' \
    '(provider-result providers.claude :prompt (ask :task item))))))'












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
