"""US01–US06: full paired-search behavior through dynamic source and compiled leaves."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from tests.experiments.test_dynamic_core_utility_improve import _write_probes
from tests.experiments.test_evaluated_execution_spike import build as build_spike, spike
from tests.experiments.test_evaluated_execution_spike_programs import compact_controller
from tests.experiments.test_mlevolve_pair_fixture import (
    BUDGETS,
    SCENARIOS,
    _SCRIPTED_LEAVES,
    _reference,
    _scenario_answers,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "experiments/dynamic_core_evaluation/fixtures"
SEARCH_SOURCE = FIXTURES / "search.orc"
UTILITY_LEAVES = FIXTURES / "utility_leaves.orc"
CONTROLLER = "mlevolve_pair/search_compact"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def _leaf_states(root: Path) -> list[dict[str, object]]:
    states = [json.loads(path.read_text(encoding="utf-8"))
              for path in (root / ".orchestrate/runs").glob("*/state.json")]
    states.sort(key=lambda state: state["started_at"])
    return states


def _dynamic_run(
    root: Path,
    *,
    scenario: dict | None = None,
    budget: int = 12,
    scripted: bool = True,
    instrument_real: bool = False,
    answers: dict | None = None,
    controller_limit: int = 16,
    inputs: dict[str, object] | None = None,
) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    probes = _write_probes(root)
    _sources, command_boundaries = compact_controller(root)
    leaf_root = root / "experiments/mlevolve_pair"
    if scripted:
        answer_set = answers if answers is not None else _scenario_answers(scenario or SCENARIOS[0])
        (leaf_root / "answers.json").write_text(json.dumps(answer_set), encoding="utf-8")
        (leaf_root / "leaves.py").write_text(_SCRIPTED_LEAVES, encoding="utf-8")
    elif instrument_real:
        leaf_path = leaf_root / "leaves.py"
        original = leaf_path.read_text(encoding="utf-8")
        marker = "    request = json.loads(raw)\n"
        logger = (
            marker
            + '    with Path(__file__).with_name("calls.jsonl").open("a", encoding="utf-8") as log:\n'
            + '        log.write(json.dumps({"outer_operation": "evaluate" if operation == "evaluate" else "proposal", '
            + '"command": "evaluate_candidate" if operation == "evaluate" else "propose_candidate", '
            + '"inputs": request}, separators=(",", ":")) + "\\n")\n'
        )
        assert marker in original
        leaf_path.write_text(original.replace(marker, logger, 1), encoding="utf-8")

    utility_source = root / "utility_leaves.orc"
    utility_text = UTILITY_LEAVES.read_text(encoding="utf-8")
    utility_text = utility_text.replace("PROBE_REVIEW", probes["probe_review"].as_posix())
    utility_text = utility_text.replace("PROBE_REVISE", probes["probe_revise"].as_posix())
    utility_source.write_text(utility_text, encoding="utf-8")

    from experiments.dynamic_core_evaluation.leaf_bridge import LeafBridge
    from experiments.dynamic_core_evaluation.program import DynamicProgram
    from experiments.dynamic_core_evaluation.source import compile_source
    from experiments.dynamic_core_evaluation.evaluator import evaluate

    bridge = LeafBridge.compile(
        utility_source,
        root,
        operations={
            "proposal": "utility_leaves::propose-candidate",
            "evaluation": "utility_leaves::evaluate-candidate",
        },
        command_boundaries={
            **command_boundaries,
            **{
                name: ExternalToolBinding(name=name, stable_command=("python", path.as_posix()))
                for name, path in probes.items()
            },
        },
    )
    source_text = SEARCH_SOURCE.read_text(encoding="utf-8")
    if controller_limit != 16:
        lowered = source_text.replace("(= iteration 16)", f"(= iteration {controller_limit})")
        assert lowered != source_text
        source_text = lowered
    source_path = root / "search.orc"
    source_path.write_text(source_text, encoding="utf-8")
    program = compile_source(source_text, source_path=source_path, type_env=bridge.type_env)
    assert program.result == "SearchResult"
    artifact_path = root / "search.json"
    artifact_path.write_text(program.artifact(), encoding="utf-8")
    restored = DynamicProgram.from_artifact(artifact_path.read_text(encoding="utf-8"))
    assert restored.digest == program.digest
    try:
        result = evaluate(
            restored,
            inputs if inputs is not None else {"max_evaluations": budget, "target_score": 0.0},
            leaf_bridge=bridge,
        )
    except EvaluatedValueError as error:
        return {
            "error": error,
            "calls": _read_jsonl(leaf_root / "calls.jsonl"),
            "states": _leaf_states(root),
        }
    return {
        "value": result.json_value(),
        "steps": result.steps,
        "calls": _read_jsonl(leaf_root / "calls.jsonl"),
        "states": _leaf_states(root),
    }


def _scripted_answers(scenario: dict, mutate) -> dict:
    answers = _scenario_answers(scenario)
    mutate(answers)
    return answers


@pytest.mark.parametrize(
    ("scenario", "budget"),
    [(scenario, budget) for budget in BUDGETS for scenario in SCENARIOS],
    ids=[f"US01/{scenario['name']}/budget-{budget}" for budget in BUDGETS for scenario in SCENARIOS],
)
def test_US01_dynamic_search_matches_each_scripted_reference_pair(
    tmp_path: Path, scenario: dict, budget: int,
) -> None:
    expected, expected_calls = _reference(scenario, budget)
    actual = _dynamic_run(
        tmp_path / f"{scenario['name']}-{budget}", scenario=scenario, budget=budget,
    )
    assert "error" not in actual
    assert actual["value"] == expected, f"{scenario['name']} at budget {budget}"
    assert actual["calls"] == expected_calls, f"{scenario['name']} request order at budget {budget}"


def test_US02_real_local_leaves_reproduce_the_ten_evaluation_trace(tmp_path: Path) -> None:
    from experiments.mlevolve_pair.leaves import evaluate, propose
    from experiments.mlevolve_pair.search import run_search

    root = tmp_path / "real-leaves"
    actual = _dynamic_run(root, scripted=False, instrument_real=True, budget=12)
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
    assert "error" not in actual
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


def test_US03_invalid_budget_dispatches_nothing_and_non_int_inputs_stay_strict(tmp_path: Path) -> None:
    expected, expected_calls = _reference(SCENARIOS[0], 17)
    actual = _dynamic_run(tmp_path / "invalid-budget", scenario=SCENARIOS[0], budget=17)
    assert actual["value"] == expected
    assert actual["value"]["status"] == "invalid_budget"
    assert actual["value"]["evaluations"] == 0
    assert expected_calls == actual["calls"] == []
    assert actual["states"] == []

    malformed = _dynamic_run(
        tmp_path / "non-int-budget", scenario=SCENARIOS[0],
        inputs={"max_evaluations": True, "target_score": 0.0},
    )
    assert malformed["error"].code == "dynamic_boundary_invalid"
    assert malformed["calls"] == malformed["states"] == []


def test_US04_invalid_candidate_bundle_fails_before_evaluation_and_keeps_prefix(tmp_path: Path) -> None:
    scenario = SCENARIOS[6]
    answers = _scripted_answers(
        scenario,
        lambda rows: rows["proposals"]["improve/A/2"].update(a=True),
    )
    actual = _dynamic_run(tmp_path / "invalid-candidate", scenario=scenario, answers=answers, budget=12)
    _expected, expected_calls = _reference(scenario, 12)
    assert actual["error"].code == "dynamic_effect_failed"
    assert actual["calls"] == expected_calls[:3]
    assert [state["status"] for state in actual["states"]] == ["completed", "completed", "failed"]
    assert not actual["states"][-1].get("workflow_outputs")
    failed_steps = [
        step for step in actual["states"][-1]["steps"].values()
        if step.get("error", {}).get("context", {}).get("cause_code") == "leaf_result_schema_invalid"
    ]
    assert len(failed_steps) == 1
    assert not failed_steps[0].get("artifacts")


def test_US05_invalid_evaluation_schema_fails_and_typed_invalid_result_repairs(tmp_path: Path) -> None:
    invalid_schema = _scripted_answers(
        SCENARIOS[0],
        lambda rows: rows["evaluations"].update({
            "1,0": {"valid": "false", "score": 0.0, "error": "invalid-seed"},
        }),
    )
    failed = _dynamic_run(
        tmp_path / "invalid-evaluation", scenario=SCENARIOS[0], answers=invalid_schema,
    )
    _expected, expected_calls = _reference(SCENARIOS[0], 12)
    assert failed["error"].code == "dynamic_effect_failed"
    assert failed["calls"] == expected_calls[:1]
    assert failed["states"][0]["status"] == "failed"
    assert not failed["states"][0].get("workflow_outputs")
    failed_steps = [
        step for step in failed["states"][0]["steps"].values()
        if step.get("error", {}).get("context", {}).get("cause_code") == "leaf_result_schema_invalid"
    ]
    assert len(failed_steps) == 1
    assert not failed_steps[0].get("artifacts")

    scenario, budget = SCENARIOS[6], 5
    expected, expected_calls = _reference(scenario, budget)
    valid_invalid = _dynamic_run(
        tmp_path / "typed-invalid-evaluation", scenario=scenario, budget=budget,
    )
    assert valid_invalid["value"] == expected
    assert valid_invalid["calls"] == expected_calls
    assert [(row["action"], row["branch"]) for row in valid_invalid["value"]["trace"]] == [
        ("seed", "A"), ("seed", "B"), ("improve", "A"), ("repair", "A"),
        ("improve", "B"),
    ]


def test_US06_reduced_authored_bound_matches_the_compact_control(tmp_path: Path) -> None:
    dynamic = _dynamic_run(
        tmp_path / "dynamic-lowered-bound", scripted=False, budget=12, controller_limit=1,
    )
    typed_root = tmp_path / "typed-lowered-bound"
    sources, boundaries = compact_controller(typed_root)
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
    assert "error" not in dynamic
    assert dynamic["value"] == typed.value
    assert dynamic["value"]["status"] == "loop_bound_exhausted"
    assert dynamic["value"]["status"] != "budget_exhausted"
