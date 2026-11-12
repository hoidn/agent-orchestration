"""Usage read from a provider's transport stdout, and the packaged price table."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.providers.pricing import cap_cost, load_price_table, priced, validate
from orchestrator.providers.types import ProviderSessionMetadataMode
from orchestrator.providers.usage import usage_from_stdout


CLAUDE = ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value
CODEX = ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
TRANSCRIPT = Path(__file__).parent / "fixtures" / "provider_usage" / "claude-stream-json.jsonl"
CODEX_STREAM = Path(__file__).parent / "experiments" / "fixtures" / "es_task3" / "codex-0.145.0-success.jsonl"


def _without_result(raw: bytes) -> bytes:
    lines = [line for line in raw.splitlines(keepends=True) if json.loads(line)["type"] != "result"]
    return b"".join(lines)


def test_claude_result_line_gives_tokens_per_model_and_reported_cost():
    usage = usage_from_stdout(CLAUDE, TRANSCRIPT.read_bytes(), model="haiku")
    assert usage == {"status": "reported", "source": "result.modelUsage", "reported_cost_usd": 0.006081640000000001,
                     "complete": True, "rows": [{"model": "claude-haiku-5-5", "tokens": {
                         "input": 10, "output": 5783, "cache_read": 64374, "cache_write": 12727}}]}


def test_claude_killed_turn_counts_each_message_once_and_is_marked_incomplete():
    # Five messages over eight assistant lines; the last line of each message carries its usage (a lower bound).
    usage = usage_from_stdout(CLAUDE, _without_result(TRANSCRIPT.read_bytes()), model="haiku")
    assert usage == {"status": "reported", "source": "assistant.message.usage", "reported_cost_usd": None,
                     "complete": False, "rows": [{"model": "claude-haiku-5-5", "tokens": {
                         "input": 10, "output": 37, "cache_read": 64374, "cache_write": 12727}}]}


def test_claude_killed_turn_ignores_a_cut_final_line():
    raw = _without_result(TRANSCRIPT.read_bytes()) + b'{"type":"assistant","mess'
    assert usage_from_stdout(CLAUDE, raw, model=None)["status"] == "reported"


def test_codex_turn_completed_separates_cached_input():
    usage = usage_from_stdout(CODEX, CODEX_STREAM.read_bytes(), model="gpt-5.6-terra")
    assert usage == {"status": "reported", "source": "turn.completed.usage", "reported_cost_usd": None,
                     "complete": True, "rows": [{"model": "gpt-5.6-terra", "tokens": {
                         "input": 16911 - 13056, "output": 5, "cache_read": 13056, "cache_write": 0}}]}


def test_codex_cache_write_is_charged_once():
    raw = (b'{"type":"thread.started","thread_id":"t"}\n'
           b'{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":30,'
           b'"cache_write_input_tokens":20,"output_tokens":7}}\n')
    assert usage_from_stdout(CODEX, raw, model="m")["rows"][0]["tokens"] == {
        "input": 50, "output": 7, "cache_read": 30, "cache_write": 20}


@pytest.mark.parametrize(("mode", "raw", "reason"), [
    (None, b"plain reply\n", "no_transport"),
    (ProviderSessionMetadataMode.OMP_JSON_STDOUT.value, b"{}\n", "no_transport"),
    (CLAUDE, b"plain reply\n", "malformed"),
    (CODEX, b"plain reply\n", "malformed"),
    (CLAUDE, b"", "no_usage_event"),
    (CODEX, b'{"type":"thread.started","thread_id":"t"}\n{"type":"turn.failed"}\n', "no_usage_event"),
    (CLAUDE, b'{"type":"result","modelUsage":{"m":{"inputTokens":-1,"outputTokens":1,'
             b'"cacheReadInputTokens":0,"cacheCreationInputTokens":0}}}\n', "malformed"),
    (CODEX, b'{"type":"turn.completed","usage":{"input_tokens":1,"cached_input_tokens":5,'
            b'"cache_write_input_tokens":0,"output_tokens":1}}\n', "malformed"),
    (CLAUDE, b'{"type":"assistant","message":"x"}\n', "malformed"),
    (CLAUDE, b'{"type":"assistant","message":{"id":[1],"model":"m","usage":{}}}\n', "malformed"),
    (CLAUDE, b'{"type":"assistant","message":{"id":"a","model":"m","usage":[1]}}\n', "malformed"),
    (CLAUDE, b'{"type":"result","modelUsage":{"m":[1]}}\n', "malformed"),
    (CODEX, b'{"type":"turn.completed","usage":"x"}\n', "malformed"),
    (CLAUDE, b"[" * 100000 + b"]" * 100000 + b"\n", "malformed"),
    (CLAUDE, b'{"type":"result","modelUsage":{}}\n', "no_usage_event"),
], ids=["plain-template", "omp", "claude-prose", "codex-prose", "claude-empty", "codex-failed-turn",
        "claude-negative", "codex-negative-remainder", "message-not-object", "unhashable-id", "usage-not-object",
        "model-usage-not-object", "codex-usage-not-object", "deep-nesting", "empty-model-usage-no-cost"])
def test_plain_text_or_malformed_stdout_is_unknown_not_zero(mode, raw, reason):
    assert usage_from_stdout(mode, raw, model="m") == {"status": "unknown", "reason": reason}


def test_price_table_names_source_date_and_four_rates_per_model():
    table = load_price_table()
    assert (table["currency"], table["tokens_per_unit"], bool(table["source"]), len(table["date"])) == (
        "USD", 1_000_000, True, 10)
    assert {frozenset(rates) - {"long_context"} for rates in table["models"].values()} == {
        frozenset(("input", "output", "cache_read", "cache_write"))}


def test_model_without_rates_prices_as_none():
    rows = [{"model": "no-such-model", "tokens": {"input": 1, "output": 1, "cache_read": 0, "cache_write": 0}}]
    assert priced(rows, load_price_table()) is None


def test_priced_sums_tokens_times_rates_over_rows():
    table = {"currency": "USD", "tokens_per_unit": 1000, "source": "test", "date": "2026-11-11",
             "models": {"a": {"input": 1, "output": 2, "cache_read": 3, "cache_write": 4}}}
    tokens = {"input": 1000, "output": 1000, "cache_read": 1000, "cache_write": 1000}
    assert priced([{"model": "a", "tokens": tokens}] * 2, table) == 20


def test_packaged_haiku_rates_reproduce_the_cli_reported_cost():
    usage = usage_from_stdout(CLAUDE, TRANSCRIPT.read_bytes(), model=None)
    assert priced(usage["rows"], load_price_table()) == pytest.approx(usage["reported_cost_usd"])


def test_empty_model_usage_keeps_the_reported_cost():
    raw = b'{"type":"result","modelUsage":{},"total_cost_usd":5}\n'
    assert usage_from_stdout(CLAUDE, raw, model=None) == {
        "status": "reported", "source": "result.modelUsage", "reported_cost_usd": 5, "complete": True, "rows": []}


def test_cap_cost_prices_at_the_highest_tier():
    # Haiku 5.5 above 100k tokens: 0.5 input, 2.5 output, 0.05 cache read, 1 cache write (1-hour) per 1M.
    usage = usage_from_stdout(CLAUDE, TRANSCRIPT.read_bytes(), model=None)
    expected = (10 * 0.5 + 5783 * 2.5 + 64374 * 0.05 + 12727 * 1) / 1e6
    assert cap_cost(usage, load_price_table()) == pytest.approx(expected)


def test_cap_cost_takes_a_higher_reported_cost():
    usage = {**usage_from_stdout(CLAUDE, TRANSCRIPT.read_bytes(), model=None), "reported_cost_usd": 3.0}
    assert cap_cost(usage, load_price_table()) == 3.0


def test_cap_cost_of_incomplete_usage_is_none():
    usage = usage_from_stdout(CLAUDE, _without_result(TRANSCRIPT.read_bytes()), model=None)
    assert cap_cost(usage, load_price_table()) is None


def test_price_table_long_context_tiers_name_four_rates_above_a_threshold():
    tiers = {model: rates["long_context"] for model, rates in load_price_table()["models"].items()
             if "long_context" in rates}
    assert {model: (set(tier) - {"above_input_tokens"}, tier["above_input_tokens"]) for model, tier in tiers.items()} == {
        "claude-haiku-5-5": ({"input", "output", "cache_read", "cache_write"}, 100_000),
        **{model: ({"input", "output", "cache_read", "cache_write"}, 272_000)
           for model in ("gpt-6.1-sol", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")}}


def test_price_table_rejects_a_malformed_long_context_tier():
    table = {**load_price_table()}
    table["models"] = {"m": {"input": 1, "output": 1, "cache_read": 1, "cache_write": 1,
                             "long_context": {"above_input_tokens": 0, "input": 1}}}
    with pytest.raises(ValueError):
        validate(table)


def test_spent_counts_regular_files_only_and_never_follows_links(tmp_path):
    from orchestrator.providers.usage import spent

    usage = usage_from_stdout(CLAUDE, TRANSCRIPT.read_bytes(), model=None)
    real = tmp_path / "effects" / "a" / "attempt-1"
    linked = tmp_path / "effects" / "a" / "attempt-2"
    for attempt in (real, linked):
        attempt.mkdir(parents=True)
        (attempt / "prompt.txt").write_text("p")
    (real / "usage.json").write_text(json.dumps(usage))
    (linked / "usage.json").symlink_to(real / "usage.json")
    (tmp_path / "effects" / "b").symlink_to(tmp_path / "effects" / "a")
    assert spent(tmp_path, load_price_table()) == (cap_cost(usage, load_price_table()), ["effects/a/attempt-2"])
