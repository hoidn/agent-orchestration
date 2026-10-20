"""Campaign-specific frontier, reservoir, and parent-selection contracts; synthetic records only."""

import random
from pathlib import Path

import pytest

from experiments.orc_structural_search import campaign, pareto_readout
from experiments.orc_structural_search.records import UNAVAILABLE

MODEL = "claude-sonnet-5-5"
PRICE_TABLE = {"currency": "USD", "tokens_per_unit": 1_000_000, "source": "synthetic", "date": "2026-10-19",
               "models": {MODEL: {"input": 3, "output": 15, "cache_read": 0.3, "cache_write": 3.75}}}
CONTEXT = "ctx1:test"


def _receipt(call_id):
    return [{"call_id": call_id, "status": "complete", "provider": "claude", "usage": [{
        "model": MODEL, "provenance": {"complete_native_transcript": True},
        "charge_tokens": {"input": 1000, "output": 1000, "cache_read": 0, "cache_write": 0}}]}]


def _store(campaigns, candidates):
    """Build a valid in-memory projection for campaign APIs without creating a store or calling providers."""
    rows = [{"kind": "campaign", "campaign_id": cid, "context_key": CONTEXT, "warm_start": list(warm)}
            for cid, warm in campaigns.items()]
    subjects = set()
    for index, spec in enumerate(candidates):
        cid, owner = spec["candidate_id"], spec["campaign_id"]
        if cid not in subjects:
            rows.append({"kind": "subject", "candidate_id": cid, "campaign_id": spec.get("subject_campaign", owner)})
            subjects.add(cid)
        tid = spec.get("trial_id", f"trial:{index}")
        receipts = _receipt(tid) if spec.get("metered", True) else UNAVAILABLE
        rows.append({"kind": "trial", "trial_id": tid, "campaign_id": owner, "context_key": spec.get("context", CONTEXT),
                     "origin_trial_id": None, "candidate_id": cid, "task": spec.get("task", "t1"),
                     "provider_calls": 1, "wall_clock_sec": 30.0, "receipt_usage": receipts})
        rows.append({"kind": "assessment", "trial_id": tid, "outcome": "completed", "value": spec["quality"]})
    return campaign.Store(Path("/unused-campaign-store"), rows)


def _criterion(tasks=("t1",), *, archive_size=6, reservoir_capacity=4):
    return {"tasks": list(tasks), "anchors": {task: {"stub": "stub"} for task in tasks},
            "quality_floor": {"kind": "above_stub"}, "calibration": {"margin": 4, "error_rate": 0},
            "final_choice": {"equivalence_tolerance": 0.5}, "dominance_cost_tolerance": 0.1,
            "price_table": PRICE_TABLE, "support": {"min_trials": 1},
            "archive": {"size": archive_size}, "reservoir": {"capacity": reservoir_capacity}}


def _pool(task="t1", total=1.0):
    return {"task": task, "anchors": [{"anchor": "stub", "total": total}]}


def _point(candidate_id, quality, cost, **fields):
    return {"candidate_id": candidate_id, "quality": quality, "cost": cost, "above_floor": True,
            "reason": None, "support": "every_adaptive_task", "provider_calls": 1, "wall_clock_sec": 30.0,
            **fields}


def test_candidate_table_uses_metered_cost_and_leaves_unmetered_candidates_off_the_frontier():
    seed = {"candidate_id": "seed", "campaign_id": "warm", "trial_id": "seed-trial", "quality": 6}
    own = {"candidate_id": "own", "campaign_id": "c1", "quality": 7, "metered": False}
    store = _store({"warm": [], "c1": ["seed-trial"]}, [seed, own])

    table = campaign.candidate_table(store, "c1", context=CONTEXT, tasks=["t1"], price_table=PRICE_TABLE,
                                     floor=1, min_trials=1)

    assert set(table) == {"seed", "own"}
    assert table["own"]["reason"] == "cost_unavailable"
    assert table["own"]["cost"] == UNAVAILABLE and table["own"]["provider_calls"] == 1
    assert table["seed"]["cost"] == pytest.approx(0.018)
    assert "cost_axis" not in table and "provider_calls" in table["own"]
    assert campaign.bounded_frontier(table, size=6, tau_q=0.5, tau_c=0.1) == ["seed"]


def test_quality_floor_averages_each_tasks_stub_across_its_campaign_pools():
    criterion = _criterion(tasks=("t1", "t2"))
    pools = [_pool("t1", 1), _pool("t1", 3), _pool("t2", 2)]

    assert campaign.quality_floor(pools, criterion) == 2


def test_stub_floor_averages_all_generation_pools_per_task():
    criterion = _criterion(tasks=("t1", "t2"))
    pools = [_pool("t1", 1), _pool("t1", 3), _pool("t2", 2)]

    assert pareto_readout.stub_floor(pools, criterion) == 2


def test_rebuild_scopes_candidates_to_campaign_and_pools_shared_initial_evidence_by_context():
    seed0 = {"candidate_id": "seed", "campaign_id": "warm", "trial_id": "seed-original", "quality": 3}
    seed1 = {"candidate_id": "seed", "campaign_id": "c1", "trial_id": "seed-c1", "quality": 5}
    seed2 = {"candidate_id": "seed", "campaign_id": "c2", "trial_id": "seed-c2", "quality": 7}
    own = {"candidate_id": "own", "campaign_id": "c1", "quality": 6}
    sibling = {"candidate_id": "sibling", "campaign_id": "c2", "quality": 99}
    store = _store({"warm": [], "c1": ["seed-original"], "c2": ["seed-original"]},
                   [seed0, seed1, seed2, own, sibling])

    rebuilt = campaign.rebuild(store, "c1", criterion=_criterion(), pools=[_pool(total=1)], generation=2,
                               previous={"reservoir": []})

    assert set(rebuilt["table"]) == {"seed", "own"}
    assert rebuilt["table"]["seed"]["quality"] == 5
    assert "sibling" not in rebuilt["frontier"]
    assert "sibling" not in {row["candidate_id"] for row in rebuilt["reservoir"]}


def test_bounded_frontier_keeps_cost_and_quality_extremes_then_largest_neighbour_gaps():
    points = [_point(cid, quality, cost) for cid, quality, cost in (
        ("a", 2, 1), ("b", 4, 2), ("c", 6, 3), ("d", 7, 5), ("e", 8, 6), ("f", 10, 8))]

    assert campaign.bounded_frontier({p["candidate_id"]: p for p in points}, size=4, tau_q=0, tau_c=0) == [
        "a", "c", "d", "f"]


def test_bounded_frontier_is_independent_of_candidate_arrival_order():
    points = [_point(cid, quality, cost) for cid, quality, cost in (
        ("a", 2, 1), ("b", 4, 2), ("c", 6, 3), ("d", 7, 5), ("e", 8, 6), ("f", 10, 8))]
    forward = {p["candidate_id"]: p for p in points}
    reverse = dict(reversed(list(forward.items())))

    assert campaign.bounded_frontier(forward, size=4, tau_q=0, tau_c=0) == \
        campaign.bounded_frontier(reverse, size=4, tau_q=0, tau_c=0)


def test_candidates_within_both_tolerances_neither_dominate_nor_disappear():
    points = {"a": _point("a", 5, 10), "b": _point("b", 4.5, 10.9)}

    assert campaign.bounded_frontier(points, size=6, tau_q=0.5, tau_c=0.1) == ["a", "b"]


def test_reservoir_admits_valued_below_floor_and_unpriced_candidates_and_evicts_fifo():
    table = {"old": _point("old", 2, 0.1, above_floor=False),
             "low": _point("low", 1, 0.05, above_floor=False),
             "unpriced": _point("unpriced", 4, UNAVAILABLE, reason="cost_unavailable"),
             "thin": _point("thin", UNAVAILABLE, UNAVAILABLE, support="insufficient"),
             "disposed": _point("disposed", 3, 0.04)}
    previous = [{"candidate_id": "old", "admitted_generation": 1},
                {"candidate_id": "low", "admitted_generation": 2}]

    retained = campaign.reservoir_update(previous, table, [], generation=3, capacity=2, disposed={"disposed"})

    assert retained == [{"candidate_id": "low", "admitted_generation": 2},
                        {"candidate_id": "unpriced", "admitted_generation": 3}]
    assert "thin" not in {row["candidate_id"] for row in retained}


def test_reservoir_member_promoted_to_frontier_leaves_the_reservoir():
    previous = [{"candidate_id": "promoted", "admitted_generation": 1},
                {"candidate_id": "kept", "admitted_generation": 2}]
    table = {cid: _point(cid, q, c) for cid, q, c in (("promoted", 3, 1), ("kept", 2, 2))}

    retained = campaign.reservoir_update(previous, table, {"promoted"}, generation=3, capacity=4, disposed=set())

    assert retained == [{"candidate_id": "kept", "admitted_generation": 2}]


def test_evicted_reservoir_parent_does_not_cycle_back_without_a_new_evaluation():
    specs = [{"candidate_id": cid, "campaign_id": "c1", "quality": quality}
             for cid, quality in (("old-a", 2), ("old-b", 3), ("front", 10))]
    store = _store({"c1": []}, specs)
    criterion = _criterion(reservoir_capacity=1)

    first = campaign.rebuild(store, "c1", criterion=criterion, pools=[_pool(total=1)], generation=1, previous={})
    second = campaign.rebuild(store, "c1", criterion=criterion, pools=[_pool(total=1)], generation=2,
                              previous=first)

    assert first["reservoir"] == [{"candidate_id": "old-b", "admitted_generation": 1}]
    assert second["reservoir"] == first["reservoir"]


def test_frontier_only_and_mixture_share_frontier_draws_and_empty_reservoir_falls_back():
    frontier, reservoir = ["f1", "f2", "f3"], [{"candidate_id": "r1"}, {"candidate_id": "r2"}]
    plain_rng, mix_rng = random.Random(31), random.Random(31)
    plain = [campaign.select_parent("frontier_only", draw=draw, episodes=4, fraction=0.25,
                                    frontier=frontier, reservoir=reservoir, rng=plain_rng)
             for draw in range(4)]
    mixture = [campaign.select_parent("mixture", draw=draw, episodes=4, fraction=0.25,
                                      frontier=frontier, reservoir=reservoir, rng=mix_rng)
               for draw in range(4)]

    assert all(source == "frontier" for _, source in plain)
    assert mixture[0][0].startswith("r") and mixture[0][1] == "reservoir"
    assert mixture[0][0] != plain[0][0]
    assert mixture[1:] == plain[1:]
    fallback = campaign.select_parent("mixture", draw=0, episodes=4, fraction=0.25, frontier=frontier,
                                      reservoir=[], rng=random.Random(31))
    assert fallback[0] == plain[0][0] and fallback[1] == "reservoir_empty"


def test_invalid_parent_draw_refuses_before_consuming_rng():
    rng = random.Random(31)
    state = rng.getstate()

    with pytest.raises(ValueError):
        campaign.select_parent("mixture", draw=4, episodes=4, fraction=0.25, frontier=["f"],
                                reservoir=[], rng=rng)

    assert rng.getstate() == state
