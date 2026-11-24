"""The seed-set kit's reading of a Codex call (Luna plan T4) and its Codex login guard (T5), on synthetic `exec --json`
output, rollouts and hand-made login files only: no provider CLI, no real login file."""

import base64
import json
import re
from types import SimpleNamespace

import pytest

from experiments.seed_set import spend, study, units

LUNA, EFFORT = "gpt-6-luna", "medium"
TABLE = {"currency": "USD", "tokens_per_unit": 1_000_000, "source": "test", "date": "2026-11-23",
         "models": {LUNA: {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125}}}
USAGE = {"input_tokens": 200_000, "cached_input_tokens": 100_000, "cache_write_input_tokens": 0,
         "output_tokens": 10_000}
USAGE_USD = 0.016  # 100,000 charged input at 0.10, 100,000 cached at 0.01, 10,000 output at 0.50, per million
COMPLETED = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"},
             {"type": "item.completed", "item": {"id": "item_0", "type": "command_execution", "command": "ls"}},
             {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "done"}},
             {"type": "turn.completed", "usage": USAGE}]
LIMIT_TEXT = ("You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro) or try again at "
              "Nov 24th, 2026 3:05 AM.")
FAILED_LIMIT = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"},
                {"type": "error", "message": LIMIT_TEXT}, {"type": "turn.failed", "error": {"message": LIMIT_TEXT}}]
RESET = 1_795_000_000
CANDIDATE_SEC = study.unit_sec(1, study.CALL_SEC)
NOW = 1_900_000_000.0


def codex_call(records, *events, stderr="", n=1):
    """A Codex call the shim recorded: its provider, prompt, `exec --json` stdout (events or raw lines) and stderr."""
    call = records / "calls" / str(n)
    call.mkdir(parents=True)
    (call / "provider.txt").write_text("codex\n")
    (call / "prompt.txt").write_text("p")
    (call / "stdout.txt").write_text("".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in events))
    (call / "stderr.txt").write_text(stderr)
    return records


def rollout(home, name, tree, *rows, model=LUNA, effort=EFFORT):
    """A rollout under the unit's private home: its session_meta (working directory `tree`), one turn_context, rows."""
    path = home / ".codex" / "sessions" / "2026" / "11" / "23" / f"rollout-2026-11-23T10-00-0{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "session_meta", "payload": {"id": name, "cwd": str(tree)}},
             {"type": "turn_context", "payload": {"cwd": str(tree), "model": model, "effort": effort}}, *rows]
    path.write_text("".join(json.dumps(row) + "\n" for row in lines))
    return path


def token_count(used_percent, resets_at=RESET, has_credits=False):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": None, "rate_limits": {
        "primary": {"used_percent": used_percent, "window_minutes": 300, "resets_at": resets_at},
        "secondary": {"used_percent": 40.0, "window_minutes": 10080, "resets_at": resets_at + 86400},
        "credits": {"has_credits": has_credits, "unlimited": False}}}}


def test_a_completed_codex_turn_succeeds_and_is_priced_from_its_usage(tmp_path):
    records = codex_call(tmp_path, *COMPLETED)
    events = units.stream_events(records / "calls" / "1" / "stdout.txt")
    assert (units.succeeded(events, units.CODEX), units.provider_incident(records), units.usage_limit(records),
            units.priced(records, TABLE, 0.5, LUNA)) == (
        True, None, None, {"usd": USAGE_USD, "missing": [], "calls": {"1": USAGE_USD}})


def test_a_codex_call_is_not_read_as_a_claude_stream(tmp_path):
    events = units.stream_events(codex_call(tmp_path, *COMPLETED) / "calls" / "1" / "stdout.txt")
    assert units.succeeded(events) is False


def test_a_killed_codex_call_is_priced_at_the_worst_case(tmp_path):
    records = codex_call(tmp_path, *COMPLETED[:3], '{"type":"item.completed","item":{"id":"item_1","ty')
    assert units.priced(records, TABLE, 0.5, LUNA) == {"usd": 0.5, "missing": ["1"], "calls": {"1": 0.5}}


def test_a_codex_call_without_the_declared_model_is_priced_at_the_worst_case(tmp_path):
    assert units.priced(codex_call(tmp_path, *COMPLETED), TABLE, 0.5)["missing"] == ["1"]


def test_the_codex_cli_limit_wording_matches_the_kits_limit_wordings():
    assert units.LIMIT_TEXT.search(LIMIT_TEXT) is not None


def test_a_codex_limit_pauses_with_the_reset_its_session_record_names(tmp_path):
    home, records = tmp_path / "home", codex_call(tmp_path / "records", *FAILED_LIMIT, stderr=f"ERROR: {LIMIT_TEXT}\n")
    rollout(home, "1", tmp_path / "tree", token_count(100.0))
    limit = units.usage_limit(records, home=home)
    assert (limit["rule"], limit["reset"], limit["flag"]) == (units.CODEX_REACHED, RESET, units.UNRECOGNISED)


def test_a_codex_limit_cuts_its_unit_and_is_neither_an_incident_nor_a_failure(tmp_path):
    home, records = tmp_path / "home", codex_call(tmp_path / "records", *FAILED_LIMIT)
    rollout(home, "1", tmp_path / "tree", token_count(100.0))
    ledger = SimpleNamespace(ledger=tmp_path / "ledger.jsonl")
    out = study.provider_end(ledger, records, str(records), {"outcome": "failed", "calls": 1}, home)
    paused = [row["unit"] for row in spend.open_pauses(spend.rows(ledger.ledger))]
    assert ("incident" in out, out["cut"]["reset"], paused) == (False, RESET, [str(records)])


def test_a_codex_limit_wording_without_a_session_record_still_pauses(tmp_path):
    limit = units.usage_limit(codex_call(tmp_path, *FAILED_LIMIT))
    assert (limit["rule"], limit["reset"], limit["text"]) == (units.WORDING, None, LIMIT_TEXT)


def test_a_codex_status_429_pauses(tmp_path):
    failed = {"type": "turn.failed", "error": {"message": "exceeded retry limit, last status: 429 Too Many Requests"}}
    assert units.usage_limit(codex_call(tmp_path, *FAILED_LIMIT[:2], failed))["rule"] == units.STATUS_429


def test_codex_paid_credits_pause_even_a_call_that_completed(tmp_path):
    home, records = tmp_path / "home", codex_call(tmp_path / "records", *COMPLETED)
    rollout(home, "1", tmp_path / "tree", token_count(20.0, has_credits=True))
    assert ((units.usage_limit(records, home=home) or {}).get("rule"),
            units.usage_limit(records, cutting=True, home=home)) == (units.PAID, None)


def test_a_codex_turn_failed_that_is_not_a_limit_is_an_incident(tmp_path):
    failed = {"type": "turn.failed", "error": {"message": "stream disconnected before completion"}}
    records = codex_call(tmp_path, *FAILED_LIMIT[:2], failed)
    assert (units.usage_limit(records), units.provider_incident(records)) == (
        None, "call 1: stream disconnected before completion")


def test_a_codex_agent_message_naming_a_limit_or_401_is_not_an_error_line(tmp_path):
    said = {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message",
                                               "text": "401: you've hit your usage limit"}}
    records = codex_call(tmp_path, *FAILED_LIMIT[:2], said, {"type": "turn.failed", "error": {"message": "boom"}})
    assert (units.usage_limit(records), units.provider_incident(records)) == (None, "call 1: boom")


def audit(tmp_path, made=1, effort=EFFORT):
    tree = tmp_path / "tree"
    return units.audit_sessions(tmp_path / "home", tree, made, LUNA, provider=units.CODEX, effort=effort)


def test_a_clean_codex_rollout_passes_the_audit(tmp_path):
    path = rollout(tmp_path / "home", "1", tmp_path / "tree" / "cand-1", token_count(10.0))
    assert audit(tmp_path) == (None, None, [path])


def test_a_codex_rollout_answered_by_another_model_fails_the_audit_as_a_policy_hit(tmp_path):
    rollout(tmp_path / "home", "1", tmp_path / "tree" / "cand-1", model="gpt-6.1-sol")
    reason, policy, _ = audit(tmp_path)
    assert ("gpt-6.1-sol" in reason, policy is not None) == (True, True)


def test_a_codex_rollout_at_another_effort_fails_the_audit(tmp_path):
    rollout(tmp_path / "home", "1", tmp_path / "tree" / "cand-1", effort="high")
    assert audit(tmp_path)[:2] == ("a session at another effort than medium: ['high']", None)


def test_a_codex_rollout_working_outside_the_tree_fails_the_audit(tmp_path):
    path = rollout(tmp_path / "home", "1", tmp_path / "elsewhere")
    assert audit(tmp_path)[:2] == (f"sessions outside the unit tree: {[str(path)]}", None)


def test_more_codex_rollouts_than_calls_fail_the_audit(tmp_path):
    for name in "12":
        rollout(tmp_path / "home", name, tmp_path / "tree" / "cand-1")
    assert audit(tmp_path)[:2] == ("2 sessions for 1 recorded calls", None)


def test_a_codex_rollout_offering_a_tool_outside_the_allowlist_fails_the_audit(tmp_path):
    rollout(tmp_path / "home", "1", tmp_path / "tree" / "cand-1",
            {"type": "additional_tools", "payload": {"additional_tools": [{"name": "web_search"}]}})
    assert audit(tmp_path)[0] == "a session was given ['web_search'] (1 in all)"


def test_a_codex_item_outside_the_allowlist_is_an_isolation_finding(tmp_path):
    mcp = {"type": "item.started", "item": {"id": "item_2", "type": "mcp_tool_call", "server": "s", "tool": "t"}}
    records = codex_call(tmp_path, *COMPLETED[:3], mcp, *COMPLETED[3:])
    assert units.isolation_breach(records) == "call 1: the session was given ['mcp_tool_call'] (1 in all)"


def test_codex_items_inside_the_allowlist_are_no_isolation_finding(tmp_path):
    assert units.isolation_breach(codex_call(tmp_path, *COMPLETED)) is None


TOKEN_MARK = "stand-in-signature"


def codex_login(home, exp=None, **login):
    """A hand-made Codex login file under CODEX_HOME `home`: a JWT-shaped access token whose payload names `exp`
    (none when None), stand-in values elsewhere; `login` replaces top-level keys."""
    payload = base64.urlsafe_b64encode(json.dumps({} if exp is None else {"exp": exp}).encode()).decode().rstrip("=")
    tokens = {"id_token": f"e30.e30.{TOKEN_MARK}", "access_token": f"e30.{payload}.{TOKEN_MARK}",
              "refresh_token": f"{TOKEN_MARK}-refresh", "account_id": "stand-in-account"}
    path = home / "auth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"OPENAI_API_KEY": None, "tokens": tokens, "last_refresh": "2026-11-23T00:00:00Z"}
                               | login))
    return path


def refusal(monkeypatch, home, seconds=CANDIDATE_SEC):
    monkeypatch.setenv("CODEX_HOME", str(home))
    with pytest.raises(SystemExit) as refused:
        units.require_login(seconds, now=NOW, provider=units.CODEX)
    assert TOKEN_MARK not in str(refused.value)
    return str(refused.value)


def test_the_codex_login_file_is_the_one_a_unit_copies(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    assert units.login_file(units.CODEX) == tmp_path / "codex" / "auth.json"


def test_a_codex_login_that_outlives_the_unit_and_the_margin_starts(tmp_path, monkeypatch):
    codex_login(tmp_path, exp=int(NOW) + CANDIDATE_SEC + units.EXPIRY_MARGIN_SEC)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert units.require_login(CANDIDATE_SEC, now=NOW, provider=units.CODEX) is None


def test_an_expired_codex_login_refuses(tmp_path, monkeypatch):
    codex_login(tmp_path, exp=int(NOW) - 60)
    assert "refreshed the login" in refusal(monkeypatch, tmp_path)


def test_a_codex_login_expiring_inside_the_units_bound_refuses(tmp_path, monkeypatch):
    codex_login(tmp_path, exp=int(NOW) + CANDIDATE_SEC + units.EXPIRY_MARGIN_SEC - 1)
    assert re.search(r"in 44 minutes; a unit needs 45 minutes", refusal(monkeypatch, tmp_path))


def test_a_codex_login_holding_an_api_key_refuses(tmp_path, monkeypatch):
    codex_login(tmp_path, exp=int(NOW) + 86400, OPENAI_API_KEY=f"sk-{TOKEN_MARK}")
    assert "API key" in refusal(monkeypatch, tmp_path)


@pytest.mark.parametrize("login", [{"tokens": None}, {"tokens": {}}, {"auth_mode": "apikey"}])
def test_a_codex_login_that_is_not_a_chatgpt_login_refuses(tmp_path, monkeypatch, login):
    codex_login(tmp_path, exp=int(NOW) + 86400, **login)
    assert "not a ChatGPT login" in refusal(monkeypatch, tmp_path)


@pytest.mark.parametrize("access", [None, "not-a-jwt", f"e30.%%%.{TOKEN_MARK}", f"e30.InN0cmluZyI.{TOKEN_MARK}"])
def test_a_codex_login_without_a_readable_expiry_refuses(tmp_path, monkeypatch, access):
    path = codex_login(tmp_path)
    if access is not None:
        login = json.loads(path.read_text())
        path.write_text(json.dumps(login | {"tokens": login["tokens"] | {"access_token": access}}))
    assert "no access-token expiry" in refusal(monkeypatch, tmp_path)


def test_an_unreadable_codex_login_file_refuses(tmp_path, monkeypatch):
    assert "cannot be read" in refusal(monkeypatch, tmp_path)


def test_login_expiry_prints_the_codex_expiry_and_never_the_token(tmp_path, monkeypatch, capsys):
    import time
    codex_login(tmp_path / "codex", exp=int(time.time()) + 7200)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("HOME", str(tmp_path))  # the ledger's directory resolves under it; nothing is written
    study.main(["--runtime", str(tmp_path / "runtime"), "login-expiry", "--provider", "codex"])
    out = capsys.readouterr().out
    assert (re.fullmatch(r"expires \S+, in 1[12]\d minutes\n", out) is not None, TOKEN_MARK in out) == (True, False)
