"""Pure campaign endpoints from frozen checkpoint projections; no provider calls."""

import copy

import pytest

from experiments.orc_structural_search import pareto_readout, readout
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


@pytest.mark.parametrize("field", ["ceilings", "targets", "cuts", "calls_cuts"])
@pytest.mark.parametrize("invalid", [True, -1, float("inf"), float("nan"), "1"])
def test_endpoint_thresholds_require_finite_nonnegative_numbers(field, invalid):
    kwargs = {"ceilings": [1], "targets": [1], "cuts": [1], "calls_cuts": [1], field: [invalid]}

    with pytest.raises(ValueError, match=field):
        pareto_readout.campaign_endpoints([snapshot(0, 0)], **kwargs)


def decision_log():
    rows = []
    for draw, cid, parent, source, shape, parent_shape, resolution in (
        (0, "child", "cheap", "frontier", "child-shape", "seed-shape", "fresh"),
        (1, "descendant", "child", "reservoir", "descendant-shape", "child-shape", "fresh"),
        (2, "repeat", "cheap", "reservoir_empty", "seed-shape", "seed-shape", "revisit"),
    ):
        rows += [
            {"kind": "parent_decision", "generation": 1, "draw": draw,
             "parent_candidate_id": parent, "parent_source": source},
            {"kind": "episode", "generation": 1, "draw": draw, "episode_id": f"e{draw}",
             "candidate_id": cid, "parent_candidate_id": parent, "parent_source": source,
             "outcome": "accepted", "skeleton": shape, "parent_skeleton": parent_shape,
             "provider_allocation": "same", "parent_provider_allocation": "same"},
            {"kind": resolution, "campaign_decision": True, "generation": 1, "draw": draw,
             "episode_id": f"e{draw}", "candidate_id": cid},
        ]
    return rows


def diagnostic_checkpoint(rows, **fields):
    checkpoint = snapshot(1, 4, frontier=("descendant",))
    checkpoint["table"].update(child=point("child", 6, 1), descendant=point("descendant", 7, 1))
    return checkpoint | {"log_position": len(rows), "convergence": {"shares": {"idea": 1}, "max_share": 1},
                         **fields}


def diagnose(checkpoint, rows):
    criterion = {"final_choice": {"equivalence_tolerance": .5}, "dominance_cost_tolerance": .1}
    return readout.campaign_diagnostics(checkpoint, rows, criterion=criterion, initial_ids={"cheap", "strong"})


def test_diagnostics_compare_each_fresh_child_with_its_own_parent_and_track_reservoir_lineage():
    rows = decision_log()
    checkpoint = diagnostic_checkpoint(rows)

    result = diagnose(checkpoint, rows)

    assert result["completed"] == 3
    assert result["dominating_improvements"] == ["child", "descendant"]
    assert result["improvements_per_completed_episode"] == pytest.approx(2 / 3)
    assert result["frontier_entries"] == ["descendant"]
    assert result["frontier_entries_per_completed_episode"] == pytest.approx(1 / 3)
    assert result["reservoir_draws"] == 1 and result["reservoir_empty_draws"] == 1
    assert result["reservoir_frontier_entries"] == ["descendant"]
    assert result["lineage_depth"] == {"descendant": 2}
    assert result["frontier_by_ancestor"] == {"cheap": ["descendant"], "child": ["descendant"]}
    assert result["diversity"]["revisit_rate"] == pytest.approx(1 / 3)
    assert result["campaign_revisits"] == 1 and result["campaign_revisit_rate"] == pytest.approx(1 / 3)


def test_diagnostics_never_read_a_resolution_or_lineage_after_the_snapshot_prefix():
    rows = decision_log()
    checkpoint = diagnostic_checkpoint(rows, log_position=2)

    result = diagnose(checkpoint, rows)

    assert result["completed"] == 1
    assert result["dominating_improvements"] == [] and result["frontier_entries"] == []
    assert result["reservoir_draws"] == 0 and result["campaign_revisits"] == 0
    assert result["lineage_depth"] == {"descendant": UNAVAILABLE}


def test_diagnostics_keep_completed_episode_denominator_and_exclude_quota_incidents():
    rows = decision_log()[:3]
    rows += [{"kind": "episode", "episode_id": "rejected", "outcome": "rejected"},
             {"kind": "episode", "episode_id": "exhausted", "outcome": "exhausted"},
             {"kind": "episode", "episode_id": "incident", "outcome": "incident", "incidents": []},
             {"kind": "episode", "episode_id": "quota", "outcome": "incident",
              "incidents": ["quota: usage limit reached"]}]
    checkpoint = diagnostic_checkpoint(rows, frontier=("child",))

    result = diagnose(checkpoint, rows)

    assert result["completed"] == 4
    assert result["improvements_per_completed_episode"] == .25


def test_diagnostics_do_not_count_revisits_as_fresh_lineage_or_use_a_different_parent():
    rows = decision_log()
    checkpoint = diagnostic_checkpoint(rows)
    checkpoint["table"]["child"]["quality"] = 9

    result = diagnose(checkpoint, rows)

    assert result["dominating_improvements"] == ["child"]  # descendant does not dominate child
    assert "repeat" not in result["frontier_by_ancestor"]


def test_endpoint_projection_keeps_frozen_convergence_and_prefix_diagnostics():
    rows = decision_log()
    checkpoint = diagnostic_checkpoint(rows)
    checkpoint["diagnostics"] = diagnose(checkpoint, rows)

    result = endpoints([checkpoint])["checkpoints"][0]

    assert result["convergence"] == checkpoint["convergence"]
    assert result["completed"] == 3 and result["lineage_depth"] == {"descendant": 2}


def test_calls_cuts_require_their_own_strict_proof_without_retroauthorization():
    trajectory = [snapshot(0, UNAVAILABLE, calls_proxy_comparable=False),
                  snapshot(1, UNAVAILABLE, calls_proxy_comparable=True),
                  snapshot(2, UNAVAILABLE, calls_proxy_comparable=True)]
    result = pareto_readout.campaign_endpoints(trajectory, ceilings=[4], targets=[5], cuts=[1], calls_cuts=[1, 2, 3])

    assert result["not_comparable_at_cost_cuts"] is True
    assert result["calls_cuts"]["label"] == "secondary_proxy"
    assert [row["checkpoint"]["generation"] if row["checkpoint"] else None
            for row in result["calls_cuts"]["readings"]] == [None, 1, 2]


@pytest.mark.parametrize("proof", [False, None, "true", 1])
def test_calls_cuts_require_a_true_final_proof(proof):
    result = endpoints([snapshot(0, UNAVAILABLE, calls_proxy_comparable=True),
                        snapshot(1, UNAVAILABLE, calls_proxy_comparable=proof)])

    assert "calls_cuts" not in result


def comparison_input():
    criterion = {"criterion_sha256": "a" * 64, "endpoints": {
        "cost_ceilings": [1, 2, 4], "quality_targets": [.5, 1, 2],
        "B_plan_usd": 10, "budget_cuts": [.5, .75, 1], "calls_cuts": [4, 6, 8]}}
    reference = {"candidate_id": "cheap", "quality": 5, "cost": 1}
    return criterion, {"frontier-1": {"policy": "frontier_only", "reference": reference,
        "trajectory": [snapshot(0, 0, frontier=("cheap",)), snapshot(1, 4)]}}


def test_compare_campaigns_derives_predeclared_thresholds_from_verified_p0_reference():
    criterion, campaigns = comparison_input()

    result = pareto_readout.compare_campaigns(campaigns, criterion=criterion, ceiling=4)

    mine = result["campaigns"]["frontier-1"]
    assert result["descriptive_only"] is True and mine["descriptive_only"] is True
    assert "final_assessment" not in mine and "choice" not in mine
    checkpoint = mine["endpoints"]["checkpoints"][-1]
    assert checkpoint["best_quality_under"] == {"1": 5, "2": 5, "4": 7}
    assert checkpoint["cheapest_meeting"] == {"5.5": 3, "6": 3, "7": 3}
    assert [(row["campaign_id"], row["axis"], row["cut"]) for row in result["endpoint_table"]] == [
        ("frontier-1", "metered_USD", 5), ("frontier-1", "metered_USD", 7.5),
        ("frontier-1", "metered_USD", 10)]


def test_compare_formats_verified_final_projection_and_requires_sealed_authorization():
    criterion, campaigns = comparison_input()
    validation = {"finalists": ["strong"], "reference": "cheap", "choice": "cheap", "shrinkage": {"strong": 2}}
    sealed = {"choice": {"candidate_id": "cheap", "quality": 4}, "reference": {"quality": 4}}
    campaigns["frontier-1"]["final_assessment"] = {"validation": validation, "sealed": sealed}

    result = pareto_readout.compare_campaigns(campaigns, criterion=criterion, ceiling=4)

    assert result["descriptive_only"] is False
    assert result["campaigns"]["frontier-1"]["final_assessment"] == {"validation": validation}
    campaigns["frontier-1"]["sealed_opened"] = {"seq": 20}
    result = pareto_readout.compare_campaigns(campaigns, criterion=criterion, ceiling=4)
    assert result["campaigns"]["frontier-1"]["final_assessment"] == {"validation": validation, "sealed": sealed}


def test_compare_never_uses_a_sealed_only_projection_as_a_choice():
    criterion, campaigns = comparison_input()
    campaigns["frontier-1"].update(sealed_opened={"seq": 20}, final_assessment={"sealed": {"choice": "strong"}})

    result = pareto_readout.compare_campaigns(campaigns, criterion=criterion, ceiling=4)

    assert result["descriptive_only"] is True
    assert "final_assessment" not in result["campaigns"]["frontier-1"]


@pytest.mark.parametrize("ceiling", [3, True, float("nan"), float("inf")])
def test_compare_rejects_a_ceiling_other_than_four_times_p0_reference_cost(ceiling):
    criterion, campaigns = comparison_input()

    with pytest.raises(ValueError, match="ceiling"):
        pareto_readout.compare_campaigns(campaigns, criterion=criterion, ceiling=ceiling)


def test_compare_rejects_inconsistent_warm_references_between_campaigns():
    criterion, campaigns = comparison_input()
    campaigns["mixture-2"] = copy.deepcopy(campaigns["frontier-1"])
    campaigns["mixture-2"]["reference"]["quality"] = 9

    with pytest.raises(ValueError, match="reference"):
        pareto_readout.compare_campaigns(campaigns, criterion=criterion, ceiling=4)


@pytest.mark.parametrize("position", [-1, 10, True, 1.0])
def test_diagnostics_refuse_an_invalid_or_unavailable_log_prefix(position):
    rows = decision_log()
    with pytest.raises(ValueError, match="log_position"):
        diagnose(diagnostic_checkpoint(rows, log_position=position), rows)


def test_diagnostics_refuse_an_episode_with_a_different_committed_parent():
    rows = decision_log()
    rows[0]["parent_candidate_id"] = "different"
    with pytest.raises(ValueError, match="parent"):
        diagnose(diagnostic_checkpoint(rows), rows)


def test_diagnostics_refuse_cyclic_candidate_lineage():
    rows = decision_log()
    rows[0]["parent_candidate_id"] = rows[1]["parent_candidate_id"] = "descendant"
    with pytest.raises(ValueError, match="cycle"):
        diagnose(diagnostic_checkpoint(rows), rows)


def test_readout_diagnostics_and_comparison_leave_evidence_unchanged():
    rows = decision_log()
    checkpoint = diagnostic_checkpoint(rows)
    criterion, campaigns = comparison_input()
    original = copy.deepcopy((rows, checkpoint, campaigns))

    diagnose(checkpoint, rows)
    pareto_readout.compare_campaigns(campaigns, criterion=criterion, ceiling=4)

    assert (rows, checkpoint, campaigns) == original


def test_compare_requires_the_generation_zero_baseline_instead_of_inventing_initial_ids():
    criterion, campaigns = comparison_input()
    campaigns["frontier-1"]["trajectory"] = [snapshot(1, 4)]
    with pytest.raises(ValueError, match="baseline"):
        pareto_readout.compare_campaigns(campaigns, criterion=criterion, ceiling=4)


def test_compare_labels_the_calls_proxy_when_metered_cost_is_unavailable():
    criterion, campaigns = comparison_input()
    campaigns["frontier-1"]["trajectory"][-1].update(calls_proxy_comparable=True)
    campaigns["frontier-1"]["trajectory"][-1]["budget"]["metered_cost"] = UNAVAILABLE

    result = pareto_readout.compare_campaigns(campaigns, criterion=criterion, ceiling=4)

    assert {row["axis"] for row in result["endpoint_table"]} == {"secondary_proxy"}
    assert result["campaigns"]["frontier-1"]["endpoints"]["not_comparable_at_cost_cuts"] is True
