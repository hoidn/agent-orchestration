"""Usage read from a provider's transport stdout, and the packaged price table."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.providers.pricing import load_price_table, priced
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
                     "rows": [{"model": "claude-haiku-5-5", "tokens": {
                         "input": 10, "output": 5783, "cache_read": 64374, "cache_write": 12727}}]}


def test_claude_killed_turn_counts_each_message_once():
    # Five messages over eight assistant lines; the last line of each message carries its usage.
    usage = usage_from_stdout(CLAUDE, _without_result(TRANSCRIPT.read_bytes()), model="haiku")
    assert usage == {"status": "reported", "source": "assistant.message.usage", "reported_cost_usd": None,
                     "rows": [{"model": "claude-haiku-5-5", "tokens": {
                         "input": 10, "output": 37, "cache_read": 64374, "cache_write": 12727}}]}


def test_claude_killed_turn_ignores_a_cut_final_line():
    raw = _without_result(TRANSCRIPT.read_bytes()) + b'{"type":"assistant","mess'
    assert usage_from_stdout(CLAUDE, raw, model=None)["status"] == "reported"


def test_codex_turn_completed_separates_cached_input():
    usage = usage_from_stdout(CODEX, CODEX_STREAM.read_bytes(), model="gpt-5.6-terra")
    assert usage == {"status": "reported", "source": "turn.completed.usage", "reported_cost_usd": None,
                     "rows": [{"model": "gpt-5.6-terra", "tokens": {
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
], ids=["plain-template", "omp", "claude-prose", "codex-prose", "claude-empty", "codex-failed-turn",
        "claude-negative", "codex-negative-remainder"])
def test_plain_text_or_malformed_stdout_is_unknown_not_zero(mode, raw, reason):
    assert usage_from_stdout(mode, raw, model="m") == {"status": "unknown", "reason": reason}


def test_price_table_names_source_date_and_four_rates_per_model():
    table = load_price_table()
    assert (table["currency"], table["tokens_per_unit"], bool(table["source"]), len(table["date"])) == (
        "USD", 1_000_000, True, 10)
    assert {frozenset(rates) for rates in table["models"].values()} == {
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
