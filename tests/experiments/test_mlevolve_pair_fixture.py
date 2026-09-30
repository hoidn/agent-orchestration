"""Current feasibility boundary and reference trace for the paired search."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from experiments.mlevolve_pair.search import run_search
from tests.experiments.test_evaluated_execution_spike import build as build_spike
from tests.experiments.test_evaluated_execution_spike import records, spike
from tests.experiments.test_evaluated_execution_spike_programs import compact_controller
from tests.test_workflow_lisp_generic_unions_runtime import _public_run

ROOT = Path(__file__).resolve().parents[2]
PAIR = ROOT / "experiments" / "mlevolve_pair"
BUDGETS = (0, 1, 2, 3, 5, 6, 9, 12)


def _evaluation(valid: bool, score: float, error: str = "") -> dict[str, object]:
    return {"valid": valid, "score": score, "error": error}


def _candidate(operation: str, branch: str, history_size: int) -> dict[str, int]:
    code = {("improve", "A"): 1, ("improve", "B"): 2, ("repair", "A"): 3,
            ("repair", "B"): 4, ("fuse", "both"): 5}[(operation, branch)]
    return {"a": 100 + history_size, "b": code}


SCENARIOS = [
    {"name": "invalid_seed_a", "seed_a": _evaluation(False, 0.0, "invalid-a"),
     "seed_b": _evaluation(True, 10.0), "outcomes": {}, "default": _evaluation(True, 100.0)},
    {"name": "invalid_seed_b", "seed_a": _evaluation(True, 10.0),
     "seed_b": _evaluation(False, 0.0, "custom-invalid-seed"), "outcomes": {},
     "default": _evaluation(True, 100.0)},
    {"name": "invalid_seeds_both", "seed_a": _evaluation(False, 0.0, "invalid-a"),
     "seed_b": _evaluation(False, -1.0, "invalid-b"), "outcomes": {},
     "default": _evaluation(True, 100.0)},
    {"name": "invalid_candidate_below_best", "seed_a": _evaluation(True, 10.0),
     "seed_b": _evaluation(True, 9.0),
     "outcomes": {"improve/A/2": _evaluation(False, -1.0, "invalid-low")},
     "default": _evaluation(True, 100.0)},
    {"name": "valid_tie_best", "seed_a": _evaluation(True, 10.0),
     "seed_b": _evaluation(True, 9.0), "outcomes": {"improve/A/2": _evaluation(True, 9.0)},
     "default": _evaluation(True, 100.0)},
    {"name": "every_candidate_invalid", "seed_a": _evaluation(False, 8.0, "invalid-a"),
     "seed_b": _evaluation(False, 9.0, "invalid-b"), "outcomes": {},
     "default": _evaluation(False, 5.0, "invalid-candidate")},
    {"name": "repair_fails_then_succeeds", "seed_a": _evaluation(True, 10.0),
     "seed_b": _evaluation(True, 9.0), "outcomes": {
         "improve/A/2": _evaluation(False, -1.0, "first-invalid"),
         "repair/A/3": _evaluation(False, -1.0, "repair-failed"),
         "improve/A/5": _evaluation(False, -1.0, "second-invalid"),
         "repair/A/6": _evaluation(True, 8.0),
     }, "default": _evaluation(True, 100.0)},
    {"name": "only_a_improves", "seed_a": _evaluation(True, 10.0),
     "seed_b": _evaluation(True, 20.0), "outcomes": {"improve/A/2": _evaluation(True, 8.0)},
     "default": _evaluation(True, 100.0)},
    {"name": "invalid_candidate_solved_score", "seed_a": _evaluation(True, 10.0),
     "seed_b": _evaluation(True, 9.0), "outcomes": {"improve/A/2": _evaluation(False, 0.0, "invalid-solved")},
     "default": _evaluation(True, 100.0)},
]


_SCRIPTED_LEAVES = '''import json, os, sys
from pathlib import Path
script = json.loads(Path(__file__).with_name("answers.json").read_text(encoding="utf-8"))
operation, raw = sys.argv[1:3]
request = json.loads(raw)
if operation == "evaluate":
    result = script["evaluations"].get(f"{request['a']},{request['b']}", script["default"])
else:
    key = f"{request['operation']}/{request['branch']}/{request['history_size']}"
    result = script["proposals"][key]
bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
if not bundle.is_absolute():
    bundle = Path.cwd() / bundle
bundle.parent.mkdir(parents=True, exist_ok=True)
with Path(__file__).with_name("calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"outer_operation": operation,
                          "command": "evaluate_candidate" if operation == "evaluate" else "propose_candidate",
                          "inputs": request}) + "\\n")
bundle.write_text(json.dumps(result), encoding="utf-8")
'''


def _scenario_answers(scenario: dict) -> dict:
    evaluations = {"1,0": scenario["seed_a"], "0,1": scenario["seed_b"]}
    proposals = {}
    for operation, branch in (("improve", "A"), ("improve", "B"), ("repair", "A"),
                              ("repair", "B"), ("fuse", "both")):
        for history_size in range(2, 17):
            key = f"{operation}/{branch}/{history_size}"
            candidate = _candidate(operation, branch, history_size)
            proposals[key] = candidate
    for key, evaluation in scenario["outcomes"].items():
        operation, branch, history = key.split("/")
        candidate = _candidate(operation, branch, int(history))
        evaluations[f"{candidate['a']},{candidate['b']}"] = evaluation
    return {"evaluations": evaluations, "proposals": proposals, "default": scenario["default"]}


def _reference(scenario: dict, budget: int) -> tuple[dict, list[dict]]:
    answers = _scenario_answers(scenario)
    calls = []

    def propose(operation, branch, candidate_a, candidate_b, other_a, other_b, history_size):
        calls.append({"outer_operation": "proposal", "command": "propose_candidate", "inputs": {
            "operation": operation, "branch": branch, "candidate_a": candidate_a,
            "candidate_b": candidate_b, "other_a": other_a, "other_b": other_b,
            "history_size": history_size,
        }})
        return _candidate(operation, branch, history_size)

    def evaluate(a, b):
        calls.append({"outer_operation": "evaluate", "command": "evaluate_candidate", "inputs": {"a": a, "b": b}})
        return answers["evaluations"].get(f"{a},{b}", answers["default"])

    result = run_search(
        max_evaluations=budget,
        proposal=propose,
        evaluator=evaluate,
    )
    return result, calls


@pytest.fixture(scope="module")
def compact_spike_program(tmp_path_factory):
    build_root = tmp_path_factory.mktemp("mlevolve-compact")
    sources, boundaries = compact_controller(build_root)
    closed = build_spike(
        build_root, sources, workflow="mlevolve_pair/search_compact::run-search", boundaries=boundaries
    )
    return sources, boundaries, closed


def _run_spike_case(tmp_path: Path, scenario: dict, budget: int, program: tuple) -> tuple[dict, dict, list, list]:
    sources, boundaries, closed = program
    workspace = tmp_path / f"{scenario['name']}-{budget}"
    leaves = workspace / "experiments" / "mlevolve_pair"
    leaves.mkdir(parents=True)
    (leaves / "answers.json").write_text(json.dumps(_scenario_answers(scenario)), encoding="utf-8")
    (leaves / "leaves.py").write_text(_SCRIPTED_LEAVES, encoding="utf-8")
    _, result = spike(
        workspace, sources, inputs={"max_evaluations": budget, "target_score": 0.0}, closed=closed,
        boundaries=boundaries, workflow="mlevolve_pair/search_compact::run-search",
    )
    expected, python_calls = _reference(scenario, budget)
    call_log = leaves / "calls.jsonl"
    spike_calls = [json.loads(line) for line in call_log.read_text(encoding="utf-8").splitlines()] if call_log.exists() else []
    return expected, result.value, python_calls, spike_calls


def _public_run_diagnostic(source_name: str, tmp_path: Path, caplog) -> tuple[int, list[tuple[str, str]]]:
    source_dir = tmp_path / "experiments" / "mlevolve_pair"
    source_dir.mkdir(parents=True)
    source = source_dir / source_name
    source.write_text(
        (PAIR / source_name).read_text(encoding="utf-8").replace("run-search", "run"),
        encoding="utf-8",
    )
    command_manifest = "commands_compact.json" if source_name == "search_compact.orc" else "commands.json"
    shutil.copy2(PAIR / command_manifest, source_dir / "commands.json")
    shutil.copy2(PAIR / "leaves.py", source_dir / "leaves.py")
    providers, prompts = tmp_path / "providers.json", tmp_path / "prompts.json"
    providers.write_text("{}", encoding="utf-8")
    prompts.write_text("{}", encoding="utf-8")
    files = {
        "source": source,
        "source_root": tmp_path / "experiments",
        "providers": providers,
        "prompts": prompts,
        "commands": source_dir / "commands.json",
    }

    result = _public_run(files)
    diagnostics = []
    for record in caplog.records:
        rendered = record.getMessage()
        code = re.search(r"\[([a-z][a-z0-9_]*)\]", rendered)
        form = re.search(r"^form: (.+)$", rendered, re.MULTILINE)
        if code:
            diagnostics.append((code.group(1), form.group(1) if form else ""))
    return result.exit_code, diagnostics


def test_python_reference_trace_records_each_decision_and_the_budget_spent() -> None:
    result = run_search(max_evaluations=12)
    trace = result["trace"]
    assert isinstance(trace, list)
    assert [
        (
            spent,
            row["action"],
            row["branch"],
            row["parents"],
            row["candidate"],
            row["evaluation"],
            row["accepted"],
        )
        for spent, row in enumerate(trace, start=1)
    ] == [
        (1, "seed", "A", [], {"a": 1, "b": 0}, {"valid": True, "score": 316.0, "error": ""}, True),
        (2, "seed", "B", [], {"a": 0, "b": 1}, {"valid": True, "score": 176.0, "error": ""}, True),
        (3, "improve", "A", [{"a": 1, "b": 0}], {"a": 99, "b": 0}, {"valid": False, "score": 0.0, "error": "coefficient_out_of_domain"}, False),
        (4, "repair", "A", [{"a": 99, "b": 0}], {"a": 2, "b": 0}, {"valid": True, "score": 306.0, "error": ""}, True),
        (5, "improve", "B", [{"a": 0, "b": 1}], {"a": 0, "b": 3}, {"valid": True, "score": 40.0, "error": ""}, True),
        (6, "improve", "A", [{"a": 2, "b": 0}], {"a": 2, "b": 0}, {"valid": True, "score": 306.0, "error": ""}, False),
        (7, "improve", "B", [{"a": 0, "b": 3}], {"a": 0, "b": 3}, {"valid": True, "score": 40.0, "error": ""}, False),
        (8, "improve", "A", [{"a": 2, "b": 0}], {"a": 2, "b": 0}, {"valid": True, "score": 306.0, "error": ""}, False),
        (9, "improve", "B", [{"a": 0, "b": 3}], {"a": 0, "b": 3}, {"valid": True, "score": 40.0, "error": ""}, False),
        (10, "fuse", "both", [{"a": 2, "b": 0}, {"a": 0, "b": 3}], {"a": 2, "b": 3}, {"valid": True, "score": 0.0, "error": ""}, True),
    ]
    assert result == {
        "candidate": {"a": 2, "b": 3},
        "evaluation": {"valid": True, "score": 0.0, "error": ""},
        "evaluations": 10,
        "status": "solved",
        "trace": trace,
    }
    for budget, expected in (
        (2, (2, "budget_exhausted", {"a": 0, "b": 1}, {"valid": True, "score": 176.0, "error": ""})),
        (3, (3, "budget_exhausted", {"a": 0, "b": 1}, {"valid": True, "score": 176.0, "error": ""})),
        (4, (4, "budget_exhausted", {"a": 0, "b": 1}, {"valid": True, "score": 176.0, "error": ""})),
        (7, (7, "budget_exhausted", {"a": 0, "b": 3}, {"valid": True, "score": 40.0, "error": ""})),
        (12, (10, "solved", {"a": 2, "b": 3}, {"valid": True, "score": 0.0, "error": ""})),
    ):
        bounded = run_search(max_evaluations=budget)
        assert (
            bounded["evaluations"],
            bounded["status"],
            bounded["candidate"],
            bounded["evaluation"],
        ) == expected


def test_python_reference_reaches_each_scripted_leaf_outcome() -> None:
    results = {scenario["name"]: _reference(scenario, 12)[0] for scenario in SCENARIOS}
    traces = {name: result["trace"] for name, result in results.items()}

    assert traces["invalid_seed_a"][0]["evaluation"]["valid"] is False
    assert traces["invalid_seed_b"][1]["evaluation"]["valid"] is False
    assert all(row["evaluation"]["valid"] is False for row in traces["invalid_seeds_both"][:2])
    assert results["invalid_seeds_both"]["candidate"] == {"a": 1, "b": 0}
    assert not traces["invalid_candidate_below_best"][2]["evaluation"]["valid"]
    assert traces["invalid_candidate_below_best"][2]["evaluation"]["score"] < 9.0
    assert traces["valid_tie_best"][2]["accepted"]
    assert traces["valid_tie_best"][2]["evaluation"]["score"] == 9.0
    assert all(row["evaluation"]["valid"] is False for row in traces["every_candidate_invalid"])
    repairs = [row for row in traces["repair_fails_then_succeeds"] if row["action"] == "repair"]
    assert [row["evaluation"]["valid"] for row in repairs] == [False, True]
    assert [row["branch"] for row in traces["only_a_improves"]
            if row["action"] == "improve" and row["accepted"]] == ["A"]
    assert traces["invalid_candidate_solved_score"][2]["evaluation"] == _evaluation(False, 0.0, "invalid-solved")
    assert results["invalid_candidate_solved_score"]["status"] != "solved"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario["name"])
@pytest.mark.parametrize("budget", BUDGETS)
def test_compact_spike_matches_the_python_reference_for_each_leaf_answer(
    tmp_path: Path, compact_spike_program: tuple, scenario: dict, budget: int
) -> None:
    expected, actual, python_calls, spike_calls = _run_spike_case(
        tmp_path, scenario, budget, compact_spike_program
    )
    assert actual == expected, f"{scenario['name']} at budget {budget}"
    assert spike_calls == python_calls, f"{scenario['name']} call inputs at budget {budget}"
    workspace = tmp_path / f"{scenario['name']}-{budget}"
    assert len(records(workspace)) == max(0, 2 * expected["evaluations"] - 2)


def test_branch_expanded_controller_reports_its_current_diagnostic_code(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _public_run_diagnostic("search.orc", tmp_path, caplog) == (
        2,
        # Bound values are shared in the payload, so the state update passes the size bound.
        # The form meets the next rule: a loop inside a branch.
        [("workflow_boundary_type_invalid", "workflow-lisp > defworkflow > run")],
    )


def test_compact_controller_reports_its_current_diagnostic_code(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _public_run_diagnostic("search_compact.orc", tmp_path, caplog) == (
        2,
        [("workflow_return_not_exportable", "workflow-lisp > defproc > branch-step")],
    )
