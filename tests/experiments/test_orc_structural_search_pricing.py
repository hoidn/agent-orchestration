"""Frozen criterion prices and complete native receipts; no provider calls."""
import copy

import pytest

from experiments.orc_structural_search import pricing

TABLE = {"currency": "USD", "tokens_per_unit": 1000000, "source": "frozen synthetic", "date": "2026-10-19",
         "models": {"m": {"input": 2, "output": 4, "cache_read": 1, "cache_write": 3}}}


def receipt():
    return {"provider_calls": 1, "receipt_usage": [{"call_id": "1", "status": "complete", "provider": "codex",
            "usage": [{"model": "m", "provenance": {"complete_native_transcript": True}, "charge_tokens": {"input": 10, "output": 5, "cache_read": 2,
                                                         "cache_write": 3}}]}]}


def test_prices_only_normalized_charge_tokens_once():
    row = receipt()
    row["receipt_usage"][0]["usage"][0].update(reasoning_output_tokens=999, total_tokens=999)
    assert pricing.cost(row, TABLE) == pytest.approx(0.000051)


@pytest.mark.parametrize("edit", [
    lambda r: r["receipt_usage"][0].update(provider="unknown"),
    lambda r: r["receipt_usage"][0]["usage"][0].update(model=[]),
    lambda r: r["receipt_usage"][0]["usage"][0]["provenance"].update(complete_native_transcript=False),
    lambda r: r.update(provider_calls=2), lambda r: r.update(receipt_usage="unavailable"),
    lambda r: r["receipt_usage"][0].update(status="unavailable"),
    lambda r: r["receipt_usage"][0]["usage"][0].update(model="unknown"),
    lambda r: r["receipt_usage"][0]["usage"][0]["charge_tokens"].update(input=True),
    lambda r: r["receipt_usage"][0]["usage"][0]["charge_tokens"].pop("cache_write"),
    lambda r: r["receipt_usage"][0]["usage"][0]["charge_tokens"].update(input=10**1000),
    lambda r: r.update(provider_calls=2, receipt_usage=r["receipt_usage"] * 2),
])
def test_incomplete_unknown_or_duplicate_receipts_are_unavailable(edit):
    row = receipt()
    edit(row)
    assert pricing.cost(row, TABLE) == "unavailable"


@pytest.mark.parametrize("value", [True, -1, float("inf"), float("nan")])
def test_invalid_frozen_rates_fail(value):
    table = copy.deepcopy(TABLE)
    table["models"]["m"]["input"] = value
    with pytest.raises(ValueError):
        pricing.validate(table)


def test_missing_exact_model_rate_is_unavailable():
    row = receipt()
    row["receipt_usage"][0]["usage"][0]["model"] = "m-alias"
    assert pricing.cost(row, TABLE) == "unavailable"


def test_missing_model_rate_is_unavailable_but_other_models_still_price():
    table = copy.deepcopy(TABLE)
    table['models']['m'].pop('cache_write')
    assert pricing.cost(receipt(), table) == 'unavailable'
    table['models']['m'] = {}
    assert pricing.cost(receipt(), table) == 'unavailable'
