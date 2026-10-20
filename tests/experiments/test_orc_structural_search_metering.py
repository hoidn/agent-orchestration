"""Metering receipts: Claude session usage, Codex rollout token events, per-provider coverage."""

import json

import pytest
from pathlib import Path

from experiments.orc_structural_search import metering

U = "unavailable"


def _jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def _assistant(msg_id: str, usage: dict, model: str = "claude-opus-5-5") -> dict:
    return {"type": "assistant", "message": {"id": msg_id, "model": model, "usage": usage}}


def _user(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


FULL = {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 2, "cache_read_input_tokens": 3}


def _token_count(total: int) -> dict:
    usage = {"input_tokens": total - 1, "cached_input_tokens": 0, "cache_write_input_tokens": 0, "output_tokens": 1, "total_tokens": total}
    return {"type": "event_msg", "payload": {"type": "token_count",
                                             "info": {"total_token_usage": usage, "last_token_usage": usage}}}


def _call(records: Path, n: int, prompt: str) -> None:
    call = records / "calls" / str(n)
    call.mkdir(parents=True)
    (call / "prompt.txt").write_text(prompt + "\n")
    (call / "stdout.txt").write_text("done\n")
    (call / "stderr.txt").write_text("")


def test_claude_usage_reads_message_usage_rows(tmp_path):
    # Claude Code writes one line per content block; lines of one message repeat its id and usage.
    session = _jsonl(tmp_path / "s.jsonl", [_user("hi"), _assistant("m1", FULL), _assistant("m1", FULL),
                                             _assistant("m2", {**FULL, "output_tokens": 7})])

    assert metering.claude_usage(session) == [
        {"model": "claude-opus-5-5", **FULL},
        {"model": "claude-opus-5-5", **FULL, "output_tokens": 7},
    ]


def test_claude_usage_marks_missing_fields_unavailable(tmp_path):
    session = _jsonl(tmp_path / "s.jsonl", [{"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 4}}}])

    assert metering.claude_usage(session) == [{"model": U, "input_tokens": 4, "output_tokens": U,
                                               "cache_creation_input_tokens": U, "cache_read_input_tokens": U}]


def test_codex_usage_is_unavailable_without_token_events(tmp_path):
    _jsonl(tmp_path / "rollout-a.jsonl", [{"type": "event_msg", "payload": {"type": "token_count", "info": None}},
                                         {"type": "response_item", "payload": {"type": "message", "usage": "n/a"}}])

    assert metering.codex_usage(tmp_path) == U


def test_codex_usage_reads_the_last_cumulative_token_event_per_rollout(tmp_path):
    rollout = _jsonl(tmp_path / "rollout-a.jsonl", [_token_count(50), _token_count(120)])

    assert metering.codex_usage(tmp_path) == [{"rollout": str(rollout), "input_tokens": 119,
                                               "cached_input_tokens": 0, "cache_write_input_tokens": 0, "output_tokens": 1, "total_tokens": 120}]


def _mixed_run(tmp_path: Path) -> tuple[Path, list[Path], list[Path]]:
    records = tmp_path / "records"
    _call(records, 1, "implement it")
    _call(records, 2, "review it")
    _call(records, 3, "implement it")
    project = tmp_path / "projects" / "p"
    main = _jsonl(project / "a.jsonl", [_user("implement it"), _assistant("m1", FULL)])
    sub = _jsonl(project / "a" / "subagents" / "agent-x.jsonl", [_user("scout"), _assistant("m9", FULL)])
    bare = _jsonl(project / "b.jsonl", [_user("implement it"), _assistant("m2", {"input_tokens": 1})])
    rollout = _jsonl(tmp_path / "codex" / "rollout-r.jsonl",
                     [{"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}},
                      {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                            "content": [{"type": "input_text", "text": "review it"}]}},
                      _token_count(40)])
    return records, [main, sub, bare], [rollout]


def test_coverage_counts_calls_and_receipts_per_provider(tmp_path):
    records, sessions, rollouts = _mixed_run(tmp_path)

    report = metering.coverage(records, claude_sessions=sessions, codex_rollouts=rollouts)

    assert {key: value for key, value in report.items() if key != "receipt_usage"} == {
        "calls": 3,
        "unmatched_calls": 0,
        "claude": {"calls": 2, "calls_with_receipts": 1, "tokens": U, "wall_clock_sec": U},
        "codex": {"calls": 1, "calls_with_receipts": 1, "tokens": 40, "wall_clock_sec": U},
    }


def test_coverage_tokens_are_unavailable_while_any_call_is_unmatched(tmp_path):
    records, sessions, rollouts = _mixed_run(tmp_path)
    (records / "calls" / "3" / "prompt.txt").write_text("unrelated\n")

    report = metering.coverage(records, claude_sessions=sessions[:2], codex_rollouts=rollouts)

    assert (report["unmatched_calls"], report["claude"]["tokens"], report["codex"]["tokens"]) == (1, U, U)


def test_coverage_claude_tokens_include_subagent_sessions(tmp_path):
    records, sessions, rollouts = _mixed_run(tmp_path)
    (records / "calls" / "3" / "prompt.txt").write_text("review it\n")
    rollouts.append(_jsonl(tmp_path / "codex" / "rollout-s.jsonl",
                           [{"type": "event_msg", "payload": {"type": "user_message", "message": "review it"}}, _token_count(2)]))

    report = metering.coverage(records, claude_sessions=sessions[:2], codex_rollouts=rollouts)

    assert report["claude"]["tokens"] == 40


def test_coverage_tokens_are_unavailable_when_a_surplus_session_holds_the_same_prompt(tmp_path):
    records, (main, sub, bare), rollouts = _mixed_run(tmp_path)
    _jsonl(bare, [_user("implement it"), _assistant("m2", FULL)])  # every receipt complete: tokens would be 60
    surplus = _jsonl(bare.with_name("c.jsonl"), [_user("implement it"), _assistant("m3", FULL)])

    report = metering.coverage(records, claude_sessions=[main, sub, bare, surplus], codex_rollouts=rollouts)

    assert report["claude"]["tokens"] == U


def test_coverage_ignores_prompt_text_outside_user_turns(tmp_path):
    records = tmp_path / "records"
    _call(records, 1, "implement it")
    quoted = _jsonl(tmp_path / "s.jsonl", [_user("other"), {"type": "user", "message": {"content": [
        {"type": "tool_result", "content": "implement it"}]}}, {"type": "assistant", "message": {
            "id": "m1", "content": [{"type": "text", "text": "implement it"}], "usage": FULL}}])

    report = metering.coverage(records, claude_sessions=[quoted], codex_rollouts=[])

    assert report["unmatched_calls"] == 1


def test_scoped_receipts_find_claude_and_codex_and_record_only_identified_paths(tmp_path):
    import re
    home, tree, records = tmp_path / "home", tmp_path / "tree", tmp_path / "records"
    _call(records, 1, "claude task")
    _call(records, 2, "codex task")
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(tree))
    claude = _jsonl(home / ".claude/projects" / slug / "one.jsonl", [_user("claude task"), _assistant("m", FULL)])
    codex = _jsonl(home / ".codex/sessions/2026/10/19/rollout-one.jsonl", [
        {"type": "session_meta", "payload": {"cwd": str(tree / "cand-1")}},
        {"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "codex task"}}, _token_count(33)])
    _jsonl(home / ".codex/sessions/2026/10/19/rollout-unrelated.jsonl", [
        {"type": "session_meta", "payload": {"cwd": str(tmp_path / "other")}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "codex task"}}, _token_count(900)])
    got = metering.receipts(records, tree=tree, since=0, home=home)
    assert (got["consumption"]["claude"]["tokens"], got["consumption"]["codex"]["tokens"],
            set(got["native_session_paths"])) == (20, 33, {str(claude), str(codex)})


@pytest.mark.parametrize("state", ["absent", "ambiguous", "truncated", "incomplete"])
def test_missing_ambiguous_or_incomplete_native_receipts_are_unavailable(tmp_path, state):
    import re
    records, tree, home = tmp_path / "records", tmp_path / "tree", tmp_path / "home"
    _call(records, 1, "task")
    root = home / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(tree))
    if state != "absent":
        session = _jsonl(root / "one.jsonl", [_user("task"), _assistant("m", {} if state == "incomplete" else FULL)])
        if state == "ambiguous":
            _jsonl(root / "two.jsonl", [_user("task"), _assistant("n", FULL)])
        if state == "truncated":
            session.write_text(session.read_text() + '{"type":')
    report = metering.receipts(records, tree=tree, since=0, home=home)
    assert report["consumption"] == U
    assert report["native_session_paths"] == ([str(session)] if state in {"incomplete", "truncated"} else U)
    assert report["receipt_usage"][0]["status"] == U
