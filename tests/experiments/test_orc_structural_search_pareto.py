"""Literal tolerant dominance and order-independent frontier mechanics."""
import itertools

import pytest

from experiments.orc_structural_search import pareto


def candidate(cid, q, cost, floor=True):
    return {"candidate_id": cid, "quality": q, "cost": cost, "above_floor": floor}


def test_tolerances_need_one_strict_improvement():
    b = candidate("B", 5, 10)
    assert not pareto.dominates(candidate("A", 5.5, 9), b, .5, .1)
    assert pareto.dominates(candidate("A", 4.5, 8.99), b, .5, .1)
    assert pareto.dominates(candidate("A", 5.51, 11), b, .5, .1)
    assert not pareto.dominates(candidate("A", 4.49, 1), b, .5, .1)


def test_frontier_recomputes_every_candidate_and_applies_floor_first():
    rows = [candidate("A", 5, 4), candidate("B", 6, 3), candidate("C", 7, 5),
            candidate("cheap_failure", 0, 0, False), candidate("unknown", 8, "unavailable")]
    for order in itertools.permutations(rows):
        assert pareto.frontier(order, 0, 0) == ["B", "C"]


@pytest.mark.parametrize("tau", [True, -1, float("nan"), float("inf")])
def test_tolerances_reject_invalid_values(tau):
    with pytest.raises(ValueError):
        pareto.frontier([], tau, 0)


def test_nonfinite_candidates_cannot_enter_frontier():
    assert pareto.frontier([candidate('bad-q', float('nan'), 1),
                            candidate('bad-cost', 1, float('inf'))], 0, 0) == []
