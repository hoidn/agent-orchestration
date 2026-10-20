"""Pure campaign endpoints from frozen checkpoint projections; no provider calls."""

import copy

import pytest

from experiments.orc_structural_search import pareto_readout
from experiments.orc_structural_search.records import UNAVAILABLE


def point(candidate_id, quality, cost, **fields):
    return {"candidate_id": candidate_id, "quality": quality, "cost": cost, "above_floor": True,
            "support": "every_adaptive_task", **fields}


def snapshot(generation, spent, *, frontier=("cheap", "strong"), **fields):
    return {"generation": generation, "frontier": list(frontier),
            "table": {"cheap": point("cheap", 5, 1), "strong": point("strong", 7, 3),
                      "reservoir": point("reservoir", 100, .01)},
            "reservoir": [{"candidate_id": "reservoir", "admitted_generation": 0}],
            "budget": {"metered_cost": spent, "calls": generation + 1, "wall_clock_sec": 30}, **fields}


def endpoints(trajectory, *, ceilings=(1, 2, 4), targets=(5, 6, 8), cuts=(5, 7.5, 10)):
    return pareto_readout.campaign_endpoints(trajectory, ceilings=ceilings, targets=targets,
                                            cuts=cuts, calls_cuts=(4, 6, 8))


def test_endpoints_use_only_supported_members_of_each_bounded_frontier():
    checkpoint = snapshot(0, 1)
    checkpoint["table"]["unpriced"] = point("unpriced", 20, UNAVAILABLE)
    checkpoint["table"]["unsupported"] = point("unsupported", 30, .1, support="insufficient")
    checkpoint["table"]["below"] = point("below", 40, .1, above_floor=False)
    checkpoint["frontier"] += ["unpriced", "unsupported", "below"]

    result = endpoints([checkpoint])["checkpoints"][0]

    assert result["best_quality_under"] == {"1": 5, "2": 5, "4": 7}
    assert result["cheapest_meeting"] == {"5": 1, "6": 3, "8": UNAVAILABLE}
    assert "reservoir" not in result["frontier"]
    assert result["budget"] == checkpoint["budget"]


def test_cost_cuts_read_the_last_checkpoint_without_interpolation_or_lookahead():
    trajectory = [snapshot(0, 0, frontier=("cheap",)), snapshot(1, 4), snapshot(2, 6), snapshot(3, 11)]
    trajectory[2]["table"]["strong"]["quality"] = 8
    trajectory[3]["table"]["strong"]["quality"] = 9

    result = endpoints(trajectory)

    assert [row["cut"] for row in result["cost_cuts"]] == [5, 7.5, 10]
    assert [row["checkpoint"]["generation"] for row in result["cost_cuts"]] == [1, 2, 2]
    assert [row["checkpoint"]["best_quality_under"]["4"] for row in result["cost_cuts"]] == [7, 8, 8]


def test_cost_cut_preserves_settlement_order_within_the_same_generation():
    trajectory = [snapshot(1, 2, frontier=("cheap",)), snapshot(1, 2)]

    result = endpoints(trajectory, cuts=(2,))

    assert result["cost_cuts"][0]["checkpoint"]["frontier"] == ["cheap", "strong"]


def test_cost_cut_before_the_first_checkpoint_has_no_reading():
    result = endpoints([snapshot(1, 2)], cuts=(1, 2))

    assert result["cost_cuts"][0] == {"cut": 1, "checkpoint": None}
    assert result["cost_cuts"][1]["checkpoint"]["generation"] == 1


def test_unsettled_initial_budget_does_not_poison_a_fully_accounted_campaign():
    trajectory = [snapshot(0, UNAVAILABLE), snapshot(0, 1), snapshot(1, 3)]

    result = endpoints(trajectory, cuts=(.5, 1, 3))

    assert not result.get("not_comparable_at_cost_cuts", False)
    assert [row["checkpoint"]["generation"] if row["checkpoint"] else None
            for row in result["cost_cuts"]] == [None, 0, 1]


def test_missing_final_receipt_disables_all_cost_cut_comparisons():
    result = endpoints([snapshot(0, 1), snapshot(1, UNAVAILABLE)])

    assert result["not_comparable_at_cost_cuts"] is True
    assert "cost_cuts" not in result
    assert "calls_cuts" not in result  # no native call-identity proof is supplied by this projection
    assert len(result["checkpoints"]) == 2


def test_empty_trajectory_cannot_claim_cost_comparability():
    result = endpoints([])

    assert result == {"checkpoints": [], "not_comparable_at_cost_cuts": True}


def test_endpoint_readout_does_not_mutate_frozen_snapshots():
    trajectory = [snapshot(0, 0)]
    original = copy.deepcopy(trajectory)

    endpoints(trajectory)

    assert trajectory == original


@pytest.mark.parametrize("field", ["ceilings", "targets", "cuts"])
@pytest.mark.parametrize("invalid", [True, -1, float("inf"), float("nan"), "1"])
def test_endpoint_thresholds_require_finite_nonnegative_numbers(field, invalid):
    kwargs = {"ceilings": [1], "targets": [1], "cuts": [1], field: [invalid]}

    with pytest.raises(ValueError, match=field):
        pareto_readout.campaign_endpoints([snapshot(0, 0)], calls_cuts=[], **kwargs)
