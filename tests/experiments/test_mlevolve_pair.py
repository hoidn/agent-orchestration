import pytest

from experiments.mlevolve_pair.leaves import validate_candidate
from experiments.mlevolve_pair.compare import compare_python
from experiments.mlevolve_pair.search import run_search


def test_search_repairs_invalid_proposal_then_keeps_ties_and_fuses() -> None:
    result = run_search()
    trace = result["trace"]

    assert [(row["action"], row["branch"]) for row in trace] == [
        ("seed", "A"), ("seed", "B"), ("improve", "A"), ("repair", "A"),
        ("improve", "B"), ("improve", "A"), ("improve", "B"),
        ("improve", "A"), ("improve", "B"), ("fuse", "both"),
    ]
    assert trace[2]["evaluation"] == {
        "valid": False, "score": 0.0, "error": "coefficient_out_of_domain",
    }
    assert trace[3]["accepted"] is True
    assert all(not row["accepted"] for row in trace[5:9])
    assert result["evaluations"] == 10
    assert result["status"] == "solved"
    assert result["candidate"] == {"a": 2, "b": 3}
    assert result["evaluation"]["score"] == 0.0


def test_search_counts_seeds_repairs_and_ties_against_the_budget() -> None:
    before_repair = run_search(max_evaluations=3)
    assert before_repair["evaluations"] == 3
    assert [row["action"] for row in before_repair["trace"]] == [
        "seed", "seed", "improve",
    ]
    assert before_repair["status"] == "budget_exhausted"

    through_ties = run_search(max_evaluations=7)
    assert through_ties["evaluations"] == 7
    assert [row["accepted"] for row in through_ties["trace"][5:7]] == [
        False, False,
    ]
    assert through_ties["candidate"] == {"a": 0, "b": 3}
    assert through_ties["evaluation"]["score"] == 40.0


def test_candidate_result_contract_rejects_bool_as_integer() -> None:
    with pytest.raises(ValueError, match="integer a and b"):
        validate_candidate({"a": True, "b": 0})


@pytest.mark.parametrize("budget", [3, 7, 12])
def test_subprocess_leaves_match_direct_controller(budget: int) -> None:
    result = compare_python(budget)
    assert result["same"] is True
