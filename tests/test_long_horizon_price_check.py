"""The long-horizon kit's per-request price rule (`experiments/long_horizon_tasks/price_check.py`)."""

import glob
import importlib.util
import os
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1] / "experiments" / "long_horizon_tasks"
_spec = importlib.util.spec_from_file_location("lh_price_check", KIT / "price_check.py")
price_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(price_check)
ARCHIVES = sorted(glob.glob(os.path.join(os.environ.get("LH", os.path.expanduser("~/lh-cache")), "recordings/archives/*/x")))


def _usage(inp=1000, out=100, read=0, five=0, hour=0):
    return {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": five + hour,
            "cache_creation": {"ephemeral_5m_input_tokens": five, "ephemeral_1h_input_tokens": hour}}


def test_each_cache_write_is_priced_at_its_own_lifetime_rate():
    rule = price_check.load_rule()
    got = price_check.price(_usage(five=20000, hour=20000), rule)
    assert round(got, 9) == round((1000 * 0.10 + 100 * 0.50 + 20000 * 0.125 + 20000 * 0.20) / 1e6, 9)


def test_write_tokens_the_split_leaves_out_are_priced_at_the_one_hour_rate():
    rule = price_check.load_rule()
    usage = {**_usage(five=1000), "cache_creation_input_tokens": 8000}  # 7000 written tokens in no split field
    assert round(price_check.price(usage, rule), 9) == round(
        (1000 * 0.10 + 100 * 0.50 + 1000 * 0.125 + 7000 * 0.20) / 1e6, 9)


def test_every_rate_is_multiplied_above_the_long_prompt_threshold():
    rule = price_check.load_rule()
    small, large = _usage(inp=50_000), _usage(inp=150_000)
    assert round(price_check.price(large, rule) / price_check.price(small, rule), 6) == round(
        5 * (150_000 * 0.10 + 100 * 0.50) / (50_000 * 0.10 + 100 * 0.50), 6)


@pytest.mark.skipif(not ARCHIVES, reason="the three public archives are not in the local cache ($LH/recordings/archives)")
@pytest.mark.parametrize("trial", ARCHIVES)
def test_the_rule_reproduces_the_cli_total_of_each_public_archive(trial):
    rule = price_check.load_rule()
    assert round(sum(price_check.price(u, rule) for u in price_check.requests(trial)), 9) == round(
        price_check.cli_total(trial), 9)
