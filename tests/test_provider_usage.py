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
           for model in ("gpt-6.1-sol", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-6-luna")}}


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


AGY = ProviderSessionMetadataMode.AGY_STREAM_JSON_STDOUT.value
AGY_FIXTURES = Path(__file__).parent / "fixtures" / "agy"     # `agy` 1.5.16 captures, paths rewritten


def _agy(name: str, *, drop: str | None = None) -> bytes:
    lines = (AGY_FIXTURES / f"{name}.jsonl").read_bytes().splitlines(keepends=True)
    return b"".join(line for line in lines if json.loads(line)["event"] != drop)


def _agy_usage(model: str, input: int, output: int, cache_read: int, *, complete: bool = True) -> dict:
    return {"status": "reported", "source": "step_update.usage", "reported_cost_usd": None, "complete": complete,
            "rows": [{"model": model, "tokens": {"input": input, "output": output, "cache_read": cache_read,
                                                 "cache_write": 0}}]}


@pytest.mark.parametrize(("name", "expected"), [
    ("fresh", _agy_usage("gemini-3.8-flash-low", 10501, 1, 0)),
    # The resumed call's own request, not its `result.usage` (12,761 input over both turns).
    ("resumed", _agy_usage("gemini-3.8-flash-low", 2260, 1, 8457)),
    # Three usage-bearing responses around two tool steps; their sum is the call's `result.usage`.
    ("tools", _agy_usage("gemini-3.8-flash-high", 16278, 1860, 18328)),
])
def test_agy_rows_sum_the_calls_own_step_usage(name, expected):
    assert usage_from_stdout(AGY, _agy(name), model="gemini-3.8-flash") == expected


def test_agy_refused_call_reports_no_rows():
    assert usage_from_stdout(AGY, _agy("refused"), model="no-such-model-xyz") == {
        "status": "reported", "source": "result.usage", "reported_cost_usd": None, "complete": True, "rows": []}


def test_agy_stream_cut_before_its_result_is_incomplete():
    expected = _agy_usage("gemini-3.8-flash-high", 16278, 1860, 18328, complete=False)
    assert usage_from_stdout(AGY, _agy("tools", drop="result"), model=None) == expected
    cut = _agy("tools", drop="result") + b'{"event":"result","res'
    assert usage_from_stdout(AGY, cut, model=None) == expected


def test_agy_without_init_uses_the_policy_model():
    assert usage_from_stdout(AGY, _agy("fresh", drop="init"), model="gemini-3.8-flash")["rows"][0]["model"] == (
        "gemini-3.8-flash")


def _agy_step(usage) -> bytes:
    return json.dumps({"event": "step_update", "step_update": {"step_index": 1, "usage": usage}}).encode() + b"\n"


def _agy_result(usage, *, status="SUCCESS", num_turns=1, conversation_id="c") -> bytes:
    return json.dumps({"event": "result", "result": {"conversation_id": conversation_id, "status": status,
                                                     "num_turns": num_turns, "usage": usage}}).encode() + b"\n"


GOOD_AGY_USAGE = {"input_tokens": 10, "output_tokens": 3, "thinking_tokens": 2, "cache_read_tokens": 4,
                  "total_tokens": 13}
ZERO_AGY_USAGE = dict.fromkeys(GOOD_AGY_USAGE, 0)


def test_agy_last_usage_line_of_a_step_wins():
    first = {**GOOD_AGY_USAGE, "input_tokens": 5, "total_tokens": 8}
    raw = _agy_step(first) + _agy_step(GOOD_AGY_USAGE) + _agy_result(GOOD_AGY_USAGE)
    assert usage_from_stdout(AGY, raw, model="m") == _agy_usage("m", 10, 3, 4)


@pytest.mark.parametrize("result", [
    _agy_result(GOOD_AGY_USAGE, status="ERROR"),
    _agy_result({**GOOD_AGY_USAGE, "input_tokens": 11, "total_tokens": 14}),     # a fresh call's total disagrees
    _agy_result("x"),
    b'{"event":"result","result":"x"}\n',
], ids=["error-status", "fresh-sum-mismatch", "result-usage-malformed", "result-not-object"])
def test_agy_step_sums_are_a_lower_bound_unless_the_result_confirms_them(result):
    assert usage_from_stdout(AGY, _agy_step(GOOD_AGY_USAGE) + result, model="m") == _agy_usage(
        "m", 10, 3, 4, complete=False)


def test_agy_resumed_call_skips_the_cumulative_total():
    raw = _agy_step(GOOD_AGY_USAGE) + _agy_result({**GOOD_AGY_USAGE, "input_tokens": 99, "total_tokens": 102},
                                                  num_turns=2)
    assert usage_from_stdout(AGY, raw, model="m") == _agy_usage("m", 10, 3, 4)


@pytest.mark.parametrize("raw", [
    _agy("fresh", drop="result").splitlines(keepends=True)[0] + _agy_result(ZERO_AGY_USAGE),
    _agy_result(ZERO_AGY_USAGE, conversation_id=""),
    _agy_result(ZERO_AGY_USAGE, status="ERROR"),
    _agy("fresh", drop="result").splitlines(keepends=True)[0]
    + _agy_result(ZERO_AGY_USAGE, status="ERROR", conversation_id=""),
], ids=["init-and-success", "success", "conversation-id", "init"])
def test_agy_zero_usage_is_unknown_unless_the_call_was_refused(raw):
    assert usage_from_stdout(AGY, raw, model="m") == {"status": "unknown", "reason": "no_usage_event"}


@pytest.mark.parametrize(("raw", "reason"), [
    (_agy_step({**GOOD_AGY_USAGE, "input_tokens": -1, "total_tokens": 2}), "malformed"),
    (_agy_step({**GOOD_AGY_USAGE, "thinking_tokens": 1.5}), "malformed"),
    (_agy_step({**GOOD_AGY_USAGE, "total_tokens": 17}), "malformed"),        # total is not input + output
    (_agy_step({key: value for key, value in GOOD_AGY_USAGE.items() if key != "cache_read_tokens"}), "malformed"),
    (_agy_step("x"), "malformed"),
    (b'{"event":"step_update","step_update":{"step_index":"1","usage":{}}}\n', "malformed"),
    (b"plain reply\n", "malformed"),
    (_agy("fresh", drop="step_update"), "no_usage_event"),     # init and a result with non-zero usage
    (_agy("fresh", drop="result").splitlines(keepends=True)[0], "no_usage_event"),
    (b'{"event":"result","result":{"status":"ERROR"}}\n', "no_usage_event"),
    (b"", "no_usage_event"),
    (_agy_result({**GOOD_AGY_USAGE, "total_tokens": 1}, status="ERROR", conversation_id=""), "malformed"),
], ids=["negative", "fraction", "total-mismatch", "missing-counter", "usage-not-object", "index-not-int", "prose",
        "result-usage-only", "init-only", "result-without-usage", "empty", "result-usage-malformed"])
def test_agy_unreadable_usage_is_unknown_not_zero(raw, reason):
    assert usage_from_stdout(AGY, raw, model="m") == {"status": "unknown", "reason": reason}


def test_agy_good_step_usage_is_charged_as_read():
    raw = _agy_step(GOOD_AGY_USAGE) + _agy_result(GOOD_AGY_USAGE)
    assert usage_from_stdout(AGY, raw, model="m") == _agy_usage("m", 10, 3, 4)
