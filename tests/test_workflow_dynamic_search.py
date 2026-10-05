"""Complete paired search through native schemas, imports and certified commands."""

from contextlib import chdir
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.workflow.dynamic.state import load_dynamic_view
from tests.experiments.test_mlevolve_pair_fixture import (
    BUDGETS, SCENARIOS, _SCRIPTED_LEAVES, _reference, _scenario_answers,
)
from tests.test_workflow_dynamic_improve import FIXTURES, ROOT
from tests.experiments.test_evaluated_execution_spike import build as build_spike, spike
from tests.experiments.test_evaluated_execution_spike_programs import compact_controller

CONTROLLER = "mlevolve_pair/search_compact"


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _dynamic_run(root, *, scenario=None, budget=12, scripted=True, answers=None,
                 controller_limit=16, inputs=None):
    directory = root / "dynamic_consumer"
    directory.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "consumer_types.orc", directory / "types.orc")
    source = (FIXTURES / "search.orc").read_text()
    if controller_limit != 16:
        source = source.replace("(= iteration 16)", f"(= iteration {controller_limit})", 1)
    path = directory / "search.orc"
    path.write_text(source)
    leaves = root / "experiments/mlevolve_pair"
    leaves.mkdir(parents=True)
    if scripted:
        (leaves / "answers.json").write_text(json.dumps(
            answers if answers is not None else _scenario_answers(scenario or SCENARIOS[0])))
        (leaves / "leaves.py").write_text(_SCRIPTED_LEAVES)
    else:
        real_source = (ROOT / "experiments/mlevolve_pair/leaves.py").read_text()
        marker = "    request = json.loads(raw)\n"
        logger = marker + '''    with Path(__file__).with_name("calls.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"outer_operation": "evaluate" if operation == "evaluate" else "proposal",
                              "command": "evaluate_candidate" if operation == "evaluate" else "propose_candidate",
                              "inputs": request}) + "\\n")
'''
        assert marker in real_source
        (leaves / "leaves.py").write_text(real_source.replace(marker, logger, 1))
    manifest = root / "commands.json"
    bindings = json.loads((ROOT / "experiments/mlevolve_pair/commands_compact.json").read_text())
    for binding in bindings.values():
        binding["closure"] = ["experiments/mlevolve_pair/leaves.py"]
    manifest.write_text(json.dumps(bindings))
    input_file = root / "inputs.json"
    input_file.write_text(json.dumps(inputs if inputs is not None else {
        "max_evaluations": budget, "target_score": 0.0}))
    args = create_parser().parse_args([
        "run", str(path), "--command-boundaries-file", str(manifest), "--input-file", str(input_file)])
    from orchestrator.workflow.executor import WorkflowExecutor
    with chdir(root), patch.object(WorkflowExecutor, "__init__",
            side_effect=AssertionError("native search constructed WorkflowExecutor")):
        result = run_workflow(args)
    view = load_dynamic_view(result.run_root) if result.run_root else None
    return {"result": result, "view": view,
            "value": json.loads((result.run_root / "state.json").read_text())["workflow_outputs"] if result.run_root else None,
            "calls": _read_jsonl(leaves / "calls.jsonl")}


@pytest.mark.parametrize(("scenario", "budget"),
    [(scenario, budget) for budget in BUDGETS for scenario in SCENARIOS],
    ids=[f"US01/{scenario['name']}/budget-{budget}" for budget in BUDGETS for scenario in SCENARIOS])
def test_US01_dynamic_search_matches_each_scripted_reference_pair(tmp_path, scenario, budget):
    expected, calls = _reference(scenario, budget)
    actual = _dynamic_run(tmp_path, scenario=scenario, budget=budget)
    assert actual["result"].exit_code == 0
    assert actual["value"] == expected
    assert actual["calls"] == calls
    assert [row["ordinal"] for row in actual["view"]["effects"]] == list(range(1, len(calls) + 1))
    assert [row["status"] for row in actual["view"]["effects"]] == ["completed"] * len(calls)


def test_US03_invalid_budget_dispatches_nothing_and_non_int_inputs_stay_strict(tmp_path):
    expected, expected_calls = _reference(SCENARIOS[0], 17)
    actual = _dynamic_run(tmp_path / "invalid", budget=17)
    assert actual["value"] == expected
    assert actual["value"]["status"] == "invalid_budget"
    assert actual["value"]["evaluations"] == 0
    assert actual["calls"] == expected_calls == actual["view"]["effects"] == []
    malformed = _dynamic_run(tmp_path / "bool", inputs={"max_evaluations": True, "target_score": 0.0})
    assert malformed["result"].exit_code == 2
    assert malformed["result"].run_root is None and malformed["view"] is None
    assert malformed["calls"] == []
    assert not (tmp_path / "bool/.orchestrate/runs").exists()


def _assert_failed_prefix(actual, statuses):
    assert actual["result"].exit_code == 1 and actual["value"] is None
    assert actual["view"]["status"] == "failed"
    assert actual["view"]["error"]["code"] == "dynamic_command_result_invalid"
    rows = actual["view"]["effects"]
    assert [row["ordinal"] for row in rows] == list(range(1, len(statuses) + 1))
    assert [row["status"] for row in rows] == statuses
    for row in rows:
        assert (actual["result"].run_root / row["result_path"]).is_file()
        assert (actual["result"].run_root / row["stdout_path"]).is_file()
        assert (actual["result"].run_root / row["stderr_path"]).is_file()


def test_US04_invalid_candidate_bundle_fails_before_evaluation_and_keeps_prefix(tmp_path):
    scenario = SCENARIOS[6]
    answers = _scenario_answers(scenario)
    answers["proposals"]["improve/A/2"].update(a=True)
    actual = _dynamic_run(tmp_path, scenario=scenario, answers=answers)
    _, calls = _reference(scenario, 12)
    assert actual["calls"] == calls[:3]
    _assert_failed_prefix(actual, ["completed", "completed", "failed"])


def test_US05_invalid_evaluation_schema_fails_and_typed_invalid_result_repairs(tmp_path):
    answers = _scenario_answers(SCENARIOS[0])
    answers["evaluations"]["1,0"] = {"valid": "false", "score": 0.0, "error": "invalid-seed"}
    failed = _dynamic_run(tmp_path / "bad", answers=answers)
    _, calls = _reference(SCENARIOS[0], 12)
    assert failed["calls"] == calls[:1]
    _assert_failed_prefix(failed, ["failed"])
    actual = _dynamic_run(tmp_path / "domain-invalid", scenario=SCENARIOS[6], budget=5)
    expected, calls = _reference(SCENARIOS[6], 5)
    assert actual["value"] == expected and actual["calls"] == calls
    assert [(row["action"], row["branch"]) for row in actual["value"]["trace"]] == [
        ("seed", "A"), ("seed", "B"), ("improve", "A"), ("repair", "A"), ("improve", "B")]


def test_US02_real_local_leaves_reproduce_the_ten_evaluation_trace(tmp_path: Path) -> None:
    from experiments.mlevolve_pair.leaves import evaluate, propose
    from experiments.mlevolve_pair.search import run_search

    root = tmp_path / "real-leaves"
    actual = _dynamic_run(root, scripted=False, budget=12)
    reference_calls = []

    def logged_proposal(*args):
        operation, branch, candidate_a, candidate_b, other_a, other_b, history_size = args
        reference_calls.append({
            "outer_operation": "proposal",
            "command": "propose_candidate",
            "inputs": {
                "operation": operation, "branch": branch,
                "candidate_a": candidate_a, "candidate_b": candidate_b,
                "other_a": other_a, "other_b": other_b,
                "history_size": history_size,
            },
        })
        return propose(*args)

    def logged_evaluation(a, b):
        reference_calls.append({
            "outer_operation": "evaluate", "command": "evaluate_candidate",
            "inputs": {"a": a, "b": b},
        })
        return evaluate(a, b)

    expected = run_search(
        max_evaluations=12, proposal=logged_proposal, evaluator=logged_evaluation,
    )
    assert actual["result"].exit_code == 0
    assert actual["value"] == expected
    assert actual["calls"] == reference_calls
    assert expected["evaluations"] == 10
    assert [(row["action"], row["branch"]) for row in expected["trace"]] == [
        ("seed", "A"), ("seed", "B"), ("improve", "A"), ("repair", "A"),
        ("improve", "B"), ("improve", "A"), ("improve", "B"),
        ("improve", "A"), ("improve", "B"), ("fuse", "both"),
    ]
    assert [call["command"] for call in actual["calls"]] == [
        "evaluate_candidate", "evaluate_candidate",
        *[command for _ in expected["trace"][2:] for command in ("propose_candidate", "evaluate_candidate")],
    ]



def test_US06_reduced_authored_bound_matches_the_compact_control(tmp_path: Path) -> None:
    dynamic = _dynamic_run(
        tmp_path / "dynamic-lowered-bound", scripted=False, budget=12, controller_limit=1,
    )
    typed_root = tmp_path / "typed-lowered-bound"
    sources, boundaries = compact_controller(typed_root)
    shutil.copyfile(
        tmp_path / "dynamic-lowered-bound/experiments/mlevolve_pair/leaves.py",
        typed_root / "experiments/mlevolve_pair/leaves.py")
    source_name = f"{CONTROLLER}.orc"
    lowered = sources[source_name].replace(":max 16", ":max 1")
    assert lowered != sources[source_name]
    sources[source_name] = lowered
    closed = build_spike(
        typed_root, sources, workflow=f"{CONTROLLER}::run-search", boundaries=boundaries,
    )
    _closed, typed = spike(
        typed_root, sources, inputs={"max_evaluations": 12, "target_score": 0.0},
        closed=closed, boundaries=boundaries, workflow=f"{CONTROLLER}::run-search",
    )
    assert dynamic["result"].exit_code == 0
    assert dynamic["value"] == typed.value
    assert dynamic["calls"] == _read_jsonl(typed_root / "experiments/mlevolve_pair/calls.jsonl")
    assert dynamic["value"]["status"] == "loop_bound_exhausted"
    assert dynamic["value"]["status"] != "budget_exhausted"
