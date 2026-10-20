"""Campaign budget union over saved rows and judge receipts; no provider calls."""
import json

import pytest

from experiments.orc_structural_search import campaign
from experiments.orc_structural_search.records import UNAVAILABLE

TABLE = {"currency": "USD", "tokens_per_unit": 1, "source": "frozen synthetic", "date": "2026-10-19",
         "models": {"m": {"input": 1, "output": 1, "cache_read": 1, "cache_write": 1}}}


def receipt(call_id="1", tokens=1, *, complete=True):
    return {"call_id": call_id, "provider": "claude", "status": "complete", "usage": [{
        "model": "m", "provenance": {"complete_native_transcript": complete},
        "charge_tokens": {"input": tokens, "output": 0, "cache_read": 0, "cache_write": 0}}]}


def work(records_dir, *, kind="evaluation", calls=1, seconds=2, receipts=None, **extra):
    return {"kind": kind, "records_dir": str(records_dir), "provider_calls": calls,
            "wall_clock_sec": seconds, "receipt_usage": [receipt()] if receipts is None else receipts, **extra}


def budget(rows=(), pools=(), table=TABLE):
    function = getattr(campaign, "budget_union", None)
    assert callable(function), "campaign.budget_union is not exported"
    return function(rows, pools, table)


def judge_pool(pool, *, judge="m", records_dir=None, calls=1, seconds=3, receipts=None):
    records = pool / "records"
    (records / "judges" / judge).mkdir(parents=True)
    (records / "mapping.json").write_text(json.dumps({"judges": {judge: {}}}))
    record = {"kind": "judge", "records_dir": str(records_dir or records / "judges" / judge),
              "provider_calls": calls, "wall_clock_sec": seconds,
              "receipt_usage": [receipt()] if receipts is None else receipts,
              "native_session_paths": []}
    (records / "judges" / judge / "record.json").write_text(json.dumps(record))


def test_overlapping_rows_and_repeated_pool_count_each_physical_receipt_once(tmp_path):
    episode = work(tmp_path / "episode", kind="episode", seconds=4, receipts=[receipt("1", 2)])
    pool = tmp_path / "pool"
    judge_pool(pool, seconds=5, receipts=[receipt("1", 3)])

    result = budget([episode, dict(episode)], [pool, pool])

    assert (result["calls"], result["wall_clock_sec"], result["receipts"]) == (2, 9, 2)
    assert result["metered_cost"] == 5
    assert result["by_kind"]["episode"]["calls"] == 1
    assert result["by_kind"]["judge"]["calls"] == 1


def test_superseded_attempts_in_distinct_records_dirs_remain_charged(tmp_path):
    rows = [work(tmp_path / "attempt-1", receipts=[receipt(tokens=2)]),
            work(tmp_path / "attempt-2", receipts=[receipt(tokens=3)])]

    result = budget(rows)

    assert (result["calls"], result["receipts"], result["metered_cost"]) == (2, 2, 5)


def test_latest_cumulative_snapshot_replaces_older_partial_snapshot(tmp_path):
    records = tmp_path / "same"
    rows = [work(records, calls=1, seconds=4, receipts=[receipt("1")]),
            work(records, calls=2, seconds=10, receipts=[receipt("1"), receipt("2", 2)])]

    result = budget(rows)

    assert (result["calls"], result["wall_clock_sec"], result["receipts"]) == (2, 10, 2)
    assert result["metered_cost"] == 3


def test_missing_receipt_keeps_observed_calls_and_time_but_not_cost(tmp_path):
    result = budget([work(tmp_path / "records", calls=3, seconds=7, receipts="unavailable")])

    assert (result["calls"], result["wall_clock_sec"]) == (3, 7)
    assert result["metered_cost"] == "unavailable"
    assert result["unpriced_work"]


def test_episode_without_actual_records_dir_cannot_be_priced():
    row = {"kind": "episode", "episode_id": "episode-a", "provider_calls": 1, "wall_clock_sec": 4,
           "receipt_usage": [receipt()]}

    result = budget([row])

    assert (result["calls"], result["wall_clock_sec"]) == (1, 4)
    assert result["metered_cost"] == "unavailable"
    assert result["unpriced_work"][0]["reason"] == "missing_records_dir"


def test_unavailable_records_dir_does_not_collapse_rows_or_enable_pricing():
    rows = [work("unavailable", calls=1, seconds=2, receipts=[receipt("1", 2)], evaluation_id="e1"),
            work(UNAVAILABLE, calls=1, seconds=3, receipts=[receipt("1", 3)], evaluation_id="e2")]

    result = budget(rows)

    assert (result["calls"], result["wall_clock_sec"]) == (2, 5)
    assert result["metered_cost"] == UNAVAILABLE


def test_unknown_calls_preserve_known_wall_time(tmp_path):
    result = budget([work(tmp_path / "records", calls=UNAVAILABLE, seconds=4, receipts=[receipt()])])

    assert result["calls"] == UNAVAILABLE
    assert result["wall_clock_sec"] == 4


def test_unknown_wall_time_preserves_known_calls(tmp_path):
    result = budget([work(tmp_path / "records", calls=2, seconds=UNAVAILABLE,
                          receipts=[receipt("1"), receipt("2")])])

    assert result["calls"] == 2
    assert result["wall_clock_sec"] == UNAVAILABLE


def test_unknown_native_pricing_proof_makes_cost_unavailable(tmp_path):
    result = budget([work(tmp_path / "records", receipts=[receipt(complete=False)])])

    assert result["calls"] == 1
    assert result["metered_cost"] == "unavailable"


def test_known_zero_actual_calls_with_empty_receipts_prices_zero(tmp_path):
    result = budget([work(tmp_path / "records", calls=0, seconds=0, receipts=[])])

    assert (result["calls"], result["wall_clock_sec"], result["receipts"], result["metered_cost"]) == (0, 0, 0, 0)


def test_missing_expected_judge_record_is_unknown_work_not_free(tmp_path):
    pool = tmp_path / "pool"
    mapping = pool / "records" / "mapping.json"
    mapping.parent.mkdir(parents=True)
    mapping.write_text(json.dumps({"judges": {"m": {}}}))

    result = budget([], [pool])

    assert (result["calls"], result["wall_clock_sec"], result["metered_cost"]) == (
        "unavailable", "unavailable", "unavailable")
    assert result["by_kind"]["judge"]["calls"] == "unavailable"
    assert result["unpriced_work"]


def test_kind_breakdown_sums_observed_episode_evaluation_and_judge_work(tmp_path):
    pool = tmp_path / "pool"
    judge_pool(pool, receipts=[receipt(tokens=4)])
    rows = [work(tmp_path / "episode", kind="episode", seconds=2, receipts=[receipt(tokens=1)]),
            work(tmp_path / "evaluation", seconds=3, receipts=[receipt(tokens=2)])]

    result = budget(rows, [pool])

    assert result["by_kind"]["episode"]["calls"] == 1
    assert result["by_kind"]["evaluation"]["calls"] == 1
    assert result["by_kind"]["judge"]["calls"] == 1
    assert result["calls"] == 3
    assert result["metered_cost"] == 7


def test_conflicting_duplicate_call_receipts_are_rejected(tmp_path):
    row = work(tmp_path / "records", calls=2,
               receipts=[receipt("same", 1), receipt("same", 2)])

    with pytest.raises(ValueError, match="conflicting.*receipt|receipt.*conflicting"):
        budget([row])


def test_judges_cannot_claim_another_judges_records_directory(tmp_path):
    pool, shared = tmp_path / "pool", tmp_path / "shared"
    records = pool / "records"
    for judge in ("a", "b"):
        directory = records / "judges" / judge
        directory.mkdir(parents=True)
        (directory / "record.json").write_text(json.dumps({
            "kind": "judge", "records_dir": str(shared), "provider_calls": 1, "wall_clock_sec": 3,
            "receipt_usage": [receipt()], "native_session_paths": []}))
    (records / "mapping.json").write_text(json.dumps({"judges": {"a": {}, "b": {}}}))

    result = budget([], [pool])

    assert (result["calls"], result["wall_clock_sec"], result["metered_cost"]) == (
        UNAVAILABLE, UNAVAILABLE, UNAVAILABLE)
    assert len(result["unpriced_work"]) == 2
