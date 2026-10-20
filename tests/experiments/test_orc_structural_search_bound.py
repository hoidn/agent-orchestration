"""Closed AST accounting: invocation multiplicity, real edges and finite bounds."""

import pytest

from experiments.orc_structural_search.closed_checks import planned_maximum, perform_nodes
from experiments.orc_structural_search.ledger import CallCapExceeded


def lit(value=0):
    return {"k": "lit", "v": value}


def effect():
    return {"k": "perform", "class": "provider", "site": "coder", "inputs": []}


def halt(value):
    return {"k": "halt", "value": value}


def loop(body, budget=2, exhausted=None):
    return {"k": "loop", "budget": lit(budget), "init": lit(), "body": body, "exhausted": exhausted}


def program(body, definitions=None):
    return {"body": body, "definitions": definitions or {}}


def test_repeated_helpers_count_per_invocation_and_ignore_unreached_definitions():
    call = {"k": "call", "callee": "helper", "args": [effect()]}
    body = {"k": "let", "value": call, "body": halt(call)}
    definitions = {"helper": {"body": halt(effect())}, "unused": {"body": loop(halt(effect()), 100)}}
    assert planned_maximum(program(body, definitions)) == 4


def test_nested_loop_budget_and_zero_budget_exhaustion_are_counted():
    assert planned_maximum(program(loop(loop(halt(effect()), 3), 2))) == 6
    assert planned_maximum(program(loop(halt(effect()), 0, halt(effect())))) == 1


def test_parallel_workspace_is_per_item_source_is_once():
    body = {"k": "par-map", "max": 3, "source": effect(), "workspace": effect(), "body": halt(effect())}
    assert planned_maximum(program(body)) == 7


@pytest.mark.parametrize("value", ["unknown", "cycle"])
def test_unknown_or_cyclic_callee_refuses_a_bound(value):
    call = {"k": "call", "callee": value, "args": []}
    with pytest.raises(CallCapExceeded):
        planned_maximum(program(halt(call), {"cycle": {"body": halt(call)}}))


def test_dynamic_loop_budget_refuses_even_when_max_looks_literal():
    body = {**loop(halt(effect())), "budget": {"k": "name", "n": "limit"}, "max": 2}
    with pytest.raises(CallCapExceeded):
        planned_maximum(program(body))


def test_literal_payload_that_looks_like_ast_is_data():
    body = halt(lit({"k": "perform", "class": "provider_phased"}))
    assert planned_maximum(program(body)) == 0
    assert perform_nodes(program(body)) == []


def test_effectful_list_map_needs_literal_cardinality():
    body = {"k": "list_map", "source": {"k": "name", "n": "xs"}, "body": effect()}
    with pytest.raises(CallCapExceeded):
        planned_maximum(program(halt(body)))
    body["source"] = {"k": "list", "items": [lit(), lit(), lit()]}
    assert planned_maximum(program(halt(body))) == 3


@pytest.mark.parametrize("invocation", ["(helper task repo)",
    '(let* ((hook (bind-proc (proc-ref helper) :repo repo))) (hook task))'])
def test_compiled_private_provider_helper_counts_repeated_resolved_calls(tmp_path, invocation):
    from experiments.orc_structural_search.ledger import planned_calls, max_provider_calls
    from tests.experiments.test_orc_structural_search_module import SOURCE, REPO, cfg, pair
    start = SOURCE.index("(provider-result providers.coder")
    stop = SOURCE.index(":timeout-sec 5400)", start) + len(":timeout-sec 5400)")
    call = SOURCE[start:stop]
    helper = f'(defproc helper ((task String) (repo String)) -> Change {call})\n'
    replacement = f'(let* ((first {invocation})) {invocation})'
    source = (SOURCE[:start] + replacement + SOURCE[stop:]).replace("  (defworkflow run", helper + "  (defworkflow run")
    _, child = pair(tmp_path, source)
    assert planned_calls(child, cfg(), runtime=REPO) == 2
    assert planned_calls(child, cfg(condition="joint"), runtime=REPO) == max_provider_calls(child / "direct.orc", "run")


@pytest.mark.parametrize("condition", ["joint", "provider-only", "topology-only", "prompt-only"])
def test_unsupported_effect_shape_is_refused_in_every_condition(condition):
    from experiments.orc_structural_search.closed_checks import compiled_refusal
    from tests.experiments.test_orc_structural_search_module import cfg
    before = {**program(halt(lit())), "params": [], "result": "String"}
    after = {**before, "body": halt({"k": "perform", "class": "agent", "policy": {}})}
    assert compiled_refusal(before, after, cfg(condition=condition))["refusal_code"] == "unsupported_effect_shape"


def test_resume_restores_reserved_cap_even_when_caller_changes_environment(tmp_path):
    import json
    import os
    from experiments.orc_structural_search.evaluation import EvaluationRecord, resume
    records, state = tmp_path / "records", tmp_path / "state"
    records.mkdir()
    state.mkdir()
    (records / "record.json").write_text(json.dumps({"arm_kind": "generic-command", "planned_maximum": "1"}))
    (records / "resume.sh").write_text('printf %s "$COMPARE_MAX_CALLS" > "$CAP_RESULT"\n')
    record = EvaluationRecord("e", "r", state, records, "digest", "incident", None, 0, 0, 0, ())
    env = {**os.environ, "COMPARE_MAX_CALLS": "999", "CAP_RESULT": str(tmp_path / "cap")}
    resume(record, env=env, timeout_sec=10)
    assert (tmp_path / "cap").read_text() == "1"
