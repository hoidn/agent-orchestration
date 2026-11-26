"""The seed-set kit's reading of a Codex call (Luna plan T4), its Codex login guard (T5) and the Luna model's binding
(T6: refused by every tranche the plan authorizes, its CLI's pin, environment, argv and pause), on synthetic
`exec --json` output, rollouts and hand-made login files only: no provider CLI, no real login file."""

import base64
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.seed_set import layout, rules, spend, study, units

LUNA, EFFORT = "gpt-6-luna", "medium"
TABLE = {"currency": "USD", "tokens_per_unit": 1_000_000, "source": "test", "date": "2026-11-23",
         "models": {LUNA: {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125}}}
USAGE = {"input_tokens": 200_000, "cached_input_tokens": 100_000, "cache_write_input_tokens": 0,
         "output_tokens": 10_000}
USAGE_USD = 0.016  # 100,000 charged input at 0.10, 100,000 cached at 0.01, 10,000 output at 0.50, per million
STARTED = [{"type": "thread.started", "thread_id": "thread"}, {"type": "turn.started"}]
COMPLETED = [*STARTED,
             {"type": "item.completed", "item": {"id": "item_0", "type": "command_execution", "command": "ls"}},
             {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "done"}},
             {"type": "turn.completed", "usage": USAGE}]
LIMIT_TEXT = ("You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro) or try again at "
              "Nov 24th, 2026 3:05 AM.")
FAILED_LIMIT = [*STARTED, {"type": "error", "message": LIMIT_TEXT},
                {"type": "turn.failed", "error": {"message": LIMIT_TEXT}}]
DISCONNECTED = [*STARTED, {"type": "turn.failed", "error": {"message": "stream disconnected before completion"}}]
RESET = 1_795_000_000
CANDIDATE_SEC = study.unit_sec(1, study.CALL_SEC)
NOW = 1_900_000_000.0


def codex_call(records, *events, stderr="", n=1):
    """A Codex call the shim recorded: its provider, prompt, `exec --json` stdout (events or raw lines; its thread is
    `thread-<n>`, as `rollout` names it) and stderr."""
    call = records / "calls" / str(n)
    call.mkdir(parents=True)
    (call / "provider.txt").write_text("codex\n")
    (call / "prompt.txt").write_text("p")
    events = [e | {"thread_id": f"thread-{n}"} if isinstance(e, dict) and "thread_id" in e else e for e in events]
    (call / "stdout.txt").write_text("".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in events))
    (call / "stderr.txt").write_text(stderr)
    return records


def rollout(home, n, tree, *rows, context=None):
    """The rollout of call `n` (session id `thread-<n>`) under the unit's private home: its session_meta (working
    directory `tree`), one turn_context (`context`, default the declared model and effort), then `rows`."""
    path = home / ".codex" / "sessions" / "2026" / "11" / "23" / f"rollout-2026-11-23T10-00-0{n}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    context = {"cwd": str(tree), "model": LUNA, "effort": EFFORT} if context is None else context
    lines = [{"type": "session_meta", "payload": {"id": f"thread-{n}", "cwd": str(tree)}},
             *([{"type": "turn_context", "payload": context}] if context else []), *rows]
    path.write_text("".join(json.dumps(row) + "\n" for row in lines))
    return path


def token_count(used_percent, resets_at=RESET, has_credits=False):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": None, "rate_limits": {
        "primary": {"used_percent": used_percent, "window_minutes": 300, "resets_at": resets_at},
        "secondary": {"used_percent": 40.0, "window_minutes": 10080, "resets_at": resets_at + 86400},
        "credits": {"has_credits": has_credits, "unlimited": False}}}}


def ledger_of(tmp_path):
    return SimpleNamespace(ledger=tmp_path / "ledger.jsonl")


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


def test_a_provider_record_naming_another_cli_refuses(tmp_path):
    records = codex_call(tmp_path, *COMPLETED)
    (records / "calls" / "1" / "provider.txt").write_text("omp\n")
    with pytest.raises(SystemExit, match="not claude or codex"):
        units.provider_incident(records)


def test_a_physical_call_without_a_provider_record_refuses(tmp_path):
    records = codex_call(tmp_path, *COMPLETED)
    (records / "calls" / "1" / "provider.txt").unlink()
    with pytest.raises(SystemExit, match="not claude or codex"):
        units.usage_limit(records)


def test_a_call_directory_the_shim_left_before_its_provider_record_reads_as_nothing(tmp_path):
    (tmp_path / "calls" / "1").mkdir(parents=True)
    assert (units.provider(tmp_path / "calls" / "1"), units.usage_limit(tmp_path)) == ("claude", None)


def test_the_codex_cli_limit_wording_matches_the_kits_limit_wordings():
    assert units.LIMIT_TEXT.search(LIMIT_TEXT) is not None


def test_a_codex_limit_pauses_with_the_reset_its_session_record_names(tmp_path):
    home, records = tmp_path / "home", codex_call(tmp_path / "records", *FAILED_LIMIT, stderr=f"ERROR: {LIMIT_TEXT}\n")
    rollout(home, 1, tmp_path / "tree", token_count(100.0))
    limit = units.usage_limit(records, home=home)
    assert (limit["rule"], limit["reset"], limit["flag"]) == (units.CODEX_REACHED, RESET, units.UNRECOGNISED)


def test_a_codex_limit_cuts_its_unit_and_is_neither_an_incident_nor_a_failure(tmp_path):
    home, records = tmp_path / "home", codex_call(tmp_path / "records", *FAILED_LIMIT)
    rollout(home, 1, tmp_path / "tree", token_count(100.0))
    ledger = ledger_of(tmp_path)
    out = study.provider_end(ledger, records, str(records), {"outcome": "failed", "calls": 1}, home)
    paused = [row["unit"] for row in spend.open_pauses(spend.rows(ledger.ledger))]
    assert ("incident" in out, out["cut"]["reset"], paused) == (False, RESET, [str(records)])


def test_a_window_the_second_call_filled_does_not_class_the_first_calls_failure(tmp_path):  # review major 3
    home, records = tmp_path / "home", codex_call(tmp_path / "records", *DISCONNECTED)
    codex_call(records, *FAILED_LIMIT, n=2)
    rollout(home, 1, tmp_path / "tree", token_count(50.0))
    rollout(home, 2, tmp_path / "tree", token_count(100.0))
    limit = units.usage_limit(records, home=home)
    assert (limit["call"], limit["rule"]) == ("2", units.CODEX_REACHED)


def test_a_codex_limit_wording_without_a_session_record_still_pauses(tmp_path):
    limit = units.usage_limit(codex_call(tmp_path, *FAILED_LIMIT))
    assert (limit["rule"], limit["reset"], limit["text"]) == (units.WORDING, None, LIMIT_TEXT)


def test_a_codex_status_429_pauses(tmp_path):
    failed = {"type": "turn.failed", "error": {"message": "exceeded retry limit, last status: 429 Too Many Requests"}}
    assert units.usage_limit(codex_call(tmp_path, *STARTED, failed))["rule"] == units.STATUS_429


def test_credits_held_with_a_limit_reached_pause_even_a_call_that_completed(tmp_path):
    home, records = tmp_path / "home", codex_call(tmp_path / "records", *COMPLETED)
    rollout(home, 1, tmp_path / "tree", token_count(100.0, has_credits=True))
    limit = units.usage_limit(records, home=home)
    assert ((limit["rule"], "flag" in limit), units.usage_limit(records, cutting=True, home=home)) == (
        (units.CODEX_PAID, False), None)


def credit_pause(tmp_path):
    """A killed Codex call whose rollout shows credits held and no limit reached, through `provider_end`; returns
    (the unit's facts, the ledger)."""
    home, records = tmp_path / "home", codex_call(tmp_path / "records", *COMPLETED[:3])
    rollout(home, 1, tmp_path / "tree", token_count(20.0, has_credits=True))
    ledger = ledger_of(tmp_path)
    return study.provider_end(ledger, records, str(records), {"outcome": "failed", "calls": 1}, home), ledger


def test_credits_held_on_a_killed_call_neither_cut_nor_stop_and_pause_the_codex_starts(tmp_path):  # ruling L-R7
    out, ledger = credit_pause(tmp_path)
    (pause,) = spend.open_pauses(spend.rows(ledger.ledger))
    assert ("cut" in out, spend.latest(spend.rows(ledger.ledger), "stop"), pause["closes"],
            units.CODEX_CREDITS in pause["reason"]) == (False, None, units.CODEX, True)


def test_a_credit_pause_refuses_a_luna_start(tmp_path):
    _, ledger = credit_pause(tmp_path)
    with pytest.raises(SystemExit, match="credit balance"):
        spend.reserve(ledger.ledger, "smoke", "candidate", spend.LUNA, 1, "/u/luna", {spend.AUTHORIZATION: "smoke"},
                      price=(100.0, 1.0))


def test_a_credit_pause_leaves_a_claude_start_open(tmp_path):
    _, ledger = credit_pause(tmp_path)
    spend.reserve(ledger.ledger, "smoke", "candidate", spend.HAIKU, 1, "/u/haiku", {spend.AUTHORIZATION: "smoke"},
                  price=(100.0, 1.0))
    assert [row["model"] for row in spend.starts(spend.rows(ledger.ledger))] == [spend.HAIKU]


def resume(ledger, closes=None):
    return spend.resume_after_limit(ledger.ledger, NOW - 1, 2.0, 30.0, NOW - 1, now=NOW, closes=closes)


def claude_limit(ledger):
    """An ordinary usage-limit pause of a Haiku unit, which closes every start; returns its row."""
    return spend.record(ledger.ledger, "pause", unit="/u/haiku-run", reset=NOW - 10, rule=units.RECORDED)


def test_the_owners_word_for_the_codex_cli_reopens_a_credit_pause(tmp_path):
    _, ledger = credit_pause(tmp_path)
    resume(ledger, units.CODEX)
    assert spend.open_pauses(spend.rows(ledger.ledger)) == []


def test_a_resume_of_every_start_leaves_a_credit_pause_open(tmp_path):  # review finding 1
    _, ledger = credit_pause(tmp_path)
    (credit,) = spend.open_pauses(spend.rows(ledger.ledger))
    claude_limit(ledger)
    resume(ledger)
    assert spend.open_pauses(spend.rows(ledger.ledger)) == [credit]


def test_a_luna_start_stays_refused_after_a_resume_of_every_start(tmp_path):
    _, ledger = credit_pause(tmp_path)
    claude_limit(ledger)
    resume(ledger)
    with pytest.raises(SystemExit, match="resume-after-limit --cli codex"):
        spend.reserve(ledger.ledger, "smoke", "candidate", spend.LUNA, 1, "/u/luna", {spend.AUTHORIZATION: "smoke"},
                      price=(100.0, 1.0))


def test_a_resume_for_the_codex_cli_leaves_a_pause_of_every_start_open(tmp_path):
    _, ledger = credit_pause(tmp_path)
    limit = claude_limit(ledger)
    resume(ledger, units.CODEX)
    assert spend.open_pauses(spend.rows(ledger.ledger)) == [limit]


def test_a_resume_for_the_codex_cli_without_a_credit_pause_refuses(tmp_path):
    ledger = ledger_of(tmp_path)
    claude_limit(ledger)
    with pytest.raises(SystemExit, match="of the codex CLI: nothing to resume"):
        resume(ledger, units.CODEX)


def test_a_ledger_without_scopes_reads_as_one_scope():
    """Pauses and resumes without `closes`: the last resume reopens every pause before it, as before scopes."""
    entries = [{"kind": "event", "event": "pause", "seq": 1}, {"kind": "event", "event": "pause", "seq": 2},
               {"kind": "event", "event": "resume", "seq": 3}, {"kind": "event", "event": "pause", "seq": 4},
               {"kind": "event", "event": "pause", "seq": 5}, {"kind": "event", "event": "not_a_limit", "pause": 5}]
    assert [row["seq"] for row in spend.open_pauses(entries)] == [4]


def test_a_credit_pause_is_recorded_once_per_unit(tmp_path):
    out, ledger = credit_pause(tmp_path)
    records = tmp_path / "records"
    study.pause_on_limit(ledger, records, str(records), tmp_path / "home")
    assert len(spend.open_pauses(spend.rows(ledger.ledger))) == 1


def test_a_codex_turn_failed_that_is_not_a_limit_is_an_incident(tmp_path):
    records = codex_call(tmp_path, *DISCONNECTED)
    assert (units.usage_limit(records), units.provider_incident(records)) == (
        None, "call 1: stream disconnected before completion")


def test_a_codex_agent_message_naming_a_limit_or_401_is_not_an_error_line(tmp_path):
    said = {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message",
                                               "text": "401: you've hit your usage limit"}}
    records = codex_call(tmp_path, *STARTED, said, {"type": "turn.failed", "error": {"message": "boom"}})
    assert (units.usage_limit(records), units.provider_incident(records)) == (None, "call 1: boom")


def audit(tmp_path, made=1):
    records = tmp_path / "records"
    if not (records / "calls" / "1").is_dir():
        codex_call(records, *COMPLETED)
    return units.audit_rollouts(tmp_path / "home", tmp_path / "tree", records, made, LUNA, EFFORT)


def test_a_clean_codex_rollout_passes_the_audit(tmp_path):
    path = rollout(tmp_path / "home", 1, tmp_path / "tree" / "cand-1", token_count(10.0))
    assert audit(tmp_path) == (None, None, [path])


def test_a_completed_codex_call_without_its_rollout_fails_the_audit(tmp_path):  # review major 2
    assert audit(tmp_path)[:2] == ("calls ['1'] have no session record of their thread", None)


def test_a_rollout_of_another_thread_does_not_cover_a_completed_call(tmp_path):
    rollout(tmp_path / "home", 7, tmp_path / "tree" / "cand-1")
    assert audit(tmp_path)[0] == "calls ['1'] have no session record of their thread"


def test_a_failed_codex_call_that_started_a_thread_without_its_rollout_fails_the_audit(tmp_path):
    codex_call(tmp_path / "records", *DISCONNECTED)
    assert audit(tmp_path)[0] == "calls ['1'] have no session record of their thread"


def test_a_codex_rollout_without_an_id_fails_the_audit(tmp_path):
    path = rollout(tmp_path / "home", 1, tmp_path / "tree" / "cand-1")
    path.write_text(path.read_text().replace('"id": "thread-1", ', ""))
    assert audit(tmp_path)[0] == (
        f"sessions without an id or a turn_context naming the model and effort medium: {[str(path)]}")


def test_a_completed_codex_call_without_a_thread_id_fails_the_audit(tmp_path):
    codex_call(tmp_path / "records", *COMPLETED[1:])
    rollout(tmp_path / "home", 1, tmp_path / "tree" / "cand-1")
    assert audit(tmp_path)[0] == "calls ['1'] have no session record of their thread"


@pytest.mark.parametrize("context", [{}, {"model": LUNA}, {"model": LUNA, "effort": "high"}, {"effort": EFFORT}])
def test_a_codex_rollout_without_a_turn_context_naming_model_and_effort_fails_the_audit(tmp_path, context):
    path = rollout(tmp_path / "home", 1, tmp_path / "tree" / "cand-1", context=context)
    assert audit(tmp_path)[:2] == (
        f"sessions without an id or a turn_context naming the model and effort medium: {[str(path)]}", None)


def test_a_codex_rollout_answered_by_another_model_fails_the_audit_as_a_policy_hit(tmp_path):
    rollout(tmp_path / "home", 1, tmp_path / "tree" / "cand-1", context={"model": "gpt-6.1-sol", "effort": EFFORT})
    reason, policy, _ = audit(tmp_path)
    assert ("gpt-6.1-sol" in reason, policy is not None) == (True, True)


def test_a_codex_rollout_working_outside_the_tree_fails_the_audit(tmp_path):
    path = rollout(tmp_path / "home", 1, tmp_path / "elsewhere")
    assert audit(tmp_path)[:2] == (f"sessions outside the unit tree: {[str(path)]}", None)


def test_more_codex_rollouts_than_calls_fail_the_audit(tmp_path):
    for n in (1, 2):
        rollout(tmp_path / "home", n, tmp_path / "tree" / "cand-1")
    assert audit(tmp_path)[:2] == ("2 sessions for 1 recorded calls", None)


def test_a_codex_item_outside_the_allowlist_is_an_isolation_finding(tmp_path):
    mcp = {"type": "item.started", "item": {"id": "item_2", "type": "mcp_tool_call", "server": "s", "tool": "t"}}
    records = codex_call(tmp_path, *COMPLETED[:3], mcp, *COMPLETED[3:])
    assert units.isolation_breach(records) == "call 1: the session was given ['mcp_tool_call'] (1 in all)"


def test_an_error_item_on_a_call_that_succeeded_is_a_finding_named_as_an_error_item(tmp_path):
    error = {"type": "item.completed", "item": {"id": "item_2", "type": "error", "message": "model warning"}}
    finding = units.isolation_breach(codex_call(tmp_path, *COMPLETED[:3], error, *COMPLETED[3:]))
    assert (finding.startswith("call 1: the session was given ['error']"), "an error item" in finding) == (True, True)


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
    path.write_text(json.dumps({"OPENAI_API_KEY": None, "auth_mode": "chatgpt", "tokens": tokens,
                                "last_refresh": "2026-11-23T00:00:00Z"} | login))
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
    needs = (CANDIDATE_SEC + units.EXPIRY_MARGIN_SEC) // 60
    assert re.search(rf"in {needs - 1} minutes; a unit needs {needs} minutes", refusal(monkeypatch, tmp_path))


def test_a_codex_login_holding_an_api_key_refuses(tmp_path, monkeypatch):
    codex_login(tmp_path, exp=int(NOW) + 86400, OPENAI_API_KEY=f"sk-{TOKEN_MARK}")
    assert "API key" in refusal(monkeypatch, tmp_path)


@pytest.mark.parametrize("login", [{"tokens": None}, {"tokens": {}}, {"auth_mode": "apikey"}, {"auth_mode": None},
                                   {"auth_mode": "ChatGPT"}])
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


def test_a_codex_login_without_auth_mode_refuses(tmp_path, monkeypatch):
    path = codex_login(tmp_path, exp=int(NOW) + 86400)
    path.write_text(json.dumps({key: value for key, value in json.loads(path.read_text()).items()
                                if key != "auth_mode"}))
    assert "not a ChatGPT login" in refusal(monkeypatch, tmp_path)


@pytest.mark.parametrize("kind", spend.KINDS)
@pytest.mark.parametrize("tranche", ["smoke", "calibration", "redraw"])
def test_luna_is_refused_in_every_tranche_the_plan_authorizes(tmp_path, tranche, kind):  # Luna plan T6, L-R1
    with pytest.raises(SystemExit, match=f"{tranche} {kind} {LUNA}: cap reached"):
        spend.reserve(tmp_path / "ledger.jsonl", tranche, kind, LUNA, 1, "/u/luna", {spend.AUTHORIZATION: tranche},
                      price=(1000.0, 1.0))


def test_no_planned_arm_of_the_authorized_tranches_runs_luna():
    arms = layout.load_arms(SimpleNamespace(programs=Path(study.__file__).parent / "programs"))
    assert [arm for tranche in ("smoke", "calibration", "redraw") for arm in layout.PLANNED[tranche]
            if spend.CLI[arms[arm]["model"]] != "claude"] == []


def test_a_luna_unit_denies_claude_and_binds_codex_to_its_exact_model(tmp_path):
    env = study.launch_env(LUNA, 1, home=tmp_path / "host-home")
    assert (env["COMPARE_CLAUDE_MODELS"], env["COMPARE_CODEX_MODELS"]) == ("", LUNA)


def test_a_single_cli_pin_is_the_claude_clis_and_names_no_codex_pin():
    pin = {"path": "/bin/claude", "version": "2.1.330 (Claude Code)"}
    assert (layout.cli_pin(pin, "claude"), layout.cli_pin(pin, units.CODEX)) == (pin, None)


def test_a_pin_per_cli_gives_each_cli_its_own():
    pins = {"claude": {"path": "/bin/claude", "version": "c"}, units.CODEX: {"path": "/bin/codex", "version": "x"}}
    assert (layout.cli_pin(pins, "claude"), layout.cli_pin(pins, units.CODEX)) == (pins["claude"], pins[units.CODEX])


def stand_in_codex_cli(tmp_path, version):
    """A Codex CLI that answers `--version`, in a unit declaration that names its directory on the PATH."""
    cli = tmp_path / "bin" / "codex"
    cli.parent.mkdir(parents=True)
    cli.write_text(f"#!/bin/sh\n[ \"$1\" = --version ] && echo '{version}'\n")
    cli.chmod(0o755)
    (tmp_path / "sandbox.json").write_text(json.dumps({"claude": None, units.CODEX: str(cli),
                                                       "path": [str(cli.parent), "/usr/bin", "/bin"]}))
    return cli, tmp_path / "sandbox.json"


def test_the_pinned_codex_cli_passes(tmp_path):
    cli, declaration = stand_in_codex_cli(tmp_path, "codex-cli 0.171.0")
    pin = {"path": str(cli), "version": "codex-cli 0.171.0"}
    assert rules.check_cli(declaration, pin, units.CODEX) == pin


def test_a_codex_cli_of_another_version_refuses(tmp_path):
    cli, declaration = stand_in_codex_cli(tmp_path, "codex-cli 0.172.0")
    with pytest.raises(SystemExit, match="not the pinned 'codex-cli 0.171.0'"):
        rules.check_cli(declaration, {"path": str(cli), "version": "codex-cli 0.171.0"}, units.CODEX)


METERED = ["exec", "--json", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--model", LUNA,
           "--config"]


def argv_call(records, effort):
    """A completed Codex call whose recorded argv is the metered template's with `effort`."""
    codex_call(records, *COMPLETED)
    argv = [*METERED, f"model_reasoning_effort={effort}"]
    (records / "calls" / "1" / "argv.nul").write_bytes(b"".join(arg.encode() + b"\0" for arg in argv))
    return records


def test_a_codex_call_binds_its_effort_by_the_config_override(tmp_path):
    assert rules.bound_argv(argv_call(tmp_path / "records", EFFORT), LUNA, EFFORT) is True


def test_a_codex_call_with_another_effort_is_not_bound(tmp_path):
    assert rules.bound_argv(argv_call(tmp_path / "records", "high"), LUNA, EFFORT) is False


def test_a_claude_session_in_a_codex_units_home_fails_its_audit(tmp_path):  # review finding 4
    rollout(tmp_path / "home", 1, tmp_path / "tree" / "cand-1")
    session = tmp_path / "home" / ".claude" / "projects" / "elsewhere" / "s.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
    assert audit(tmp_path)[:2] == (f"Claude sessions in a Codex unit: {[str(session)]}", None)


def test_the_readout_lists_only_the_arms_the_studys_tranches_plan():  # review finding 5
    runner = SimpleNamespace(programs=Path(study.__file__).parent / "programs")
    arms = layout.load_arms(runner)
    assert list(study.planned_programs(runner, arms)) == [
        arm for arm in arms if spend.CLI[arms[arm]["model"]] == "claude"]


def prepared(tmp_path, providers, command):
    """A prepared unit's records as `bound_model` reads them: its declaration, inputs and command script."""
    (tmp_path / "sandbox.json").write_text(json.dumps({"providers": providers}))
    (tmp_path / "inputs.json").write_text(json.dumps({"model": LUNA}))
    (tmp_path / "command.sh").write_text(command)
    return tmp_path, {"sandbox": {"declaration": str(tmp_path / "sandbox.json")}}


def test_a_codex_unit_whose_command_binds_its_model_is_bound_to_it(tmp_path):
    records, record = prepared(tmp_path, ["codex"], f"cd /t && env COMPARE_CODEX_MODELS={LUNA} PATH=/s:$PATH x\n")
    assert study.bound_model(records, record, units.CODEX) == LUNA


def test_installed_rehearsal_stand_ins_answer_the_codex_pin_and_pass_the_codex_login_guard(tmp_path, monkeypatch):
    """Review finding 10: the rehearsal's `install_stand_ins` (its setup's changed lines) on a scratch directory."""
    from experiments.seed_set import rehearsal
    from tests.experiments.seed_set_offline_support import CODEX_VERSION
    (tmp_path / "bin").mkdir()
    (tmp_path / "home").mkdir()
    rehearsal.install_stand_ins(tmp_path / "bin", tmp_path / "home")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "home" / ".codex"))
    units.require_login(CANDIDATE_SEC, provider=units.CODEX)
    version = subprocess.run([tmp_path / "bin" / "codex", "--version"], capture_output=True, text=True, check=True,
                             env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert (version.stdout.strip(), (tmp_path / "home" / ".claude" / ".credentials.json").is_file()) == (
        CODEX_VERSION, True)


LUNA_SMOKE = layout.LUNA_SMOKE


def reserve_in_luna_smoke(tmp_path, kind, model, calls=1, unit="/u/1"):
    return spend.reserve(tmp_path / "ledger.jsonl", LUNA_SMOKE, kind, model, calls, unit,
                         {spend.AUTHORIZATION: LUNA_SMOKE}, price=(10.0, 0.5))


@pytest.mark.parametrize("kind, model", [("candidate", spend.HAIKU), ("candidate", spend.SONNET),
                                         ("judge", spend.SONNET), ("judge", LUNA)])
def test_the_luna_smoke_refuses_every_call_but_luna_candidates_and_a_haiku_judge(tmp_path, kind, model):  # L-R8
    with pytest.raises(SystemExit, match="cap reached"):
        reserve_in_luna_smoke(tmp_path, kind, model)


def test_the_luna_smoke_holds_four_luna_candidate_calls(tmp_path):
    reserve_in_luna_smoke(tmp_path, "candidate", LUNA, calls=1, unit="/u/direct")
    reserve_in_luna_smoke(tmp_path, "candidate", LUNA, calls=3, unit="/u/retry")
    with pytest.raises(SystemExit, match="cap reached"):
        reserve_in_luna_smoke(tmp_path, "candidate", LUNA, unit="/u/more")


def test_the_luna_smoke_holds_one_haiku_judge_call(tmp_path):
    reserve_in_luna_smoke(tmp_path, "judge", spend.HAIKU, unit="/p#j")
    with pytest.raises(SystemExit, match="cap reached"):
        reserve_in_luna_smoke(tmp_path, "judge", spend.HAIKU, unit="/p#k")


@pytest.mark.parametrize("tranche, kind", [(LUNA_SMOKE, "first"), (LUNA_SMOKE, "retest"), ("smoke", "luna"),
                                           ("calibration", "luna")])
def test_a_pool_kind_another_tranche_builds_refuses(tranche, kind):
    with pytest.raises(SystemExit, match="pools, not"):
        layout.require_pool_kind(tranche, kind)


def test_the_luna_smokes_judges_are_haiku_alone():
    assert (layout.tranche_judges(LUNA_SMOKE), layout.tranche_judges("smoke")) == (
        [spend.HAIKU], [spend.HAIKU, spend.SONNET])


def test_the_luna_smokes_pool_criterion_names_its_one_judge(tmp_path):
    criterion = tmp_path / "judge-calibration.json"
    criterion.write_text(json.dumps({"judges": [spend.HAIKU, spend.SONNET], "rubric": layout.RUBRIC}))
    runner = SimpleNamespace(criterion=criterion, results=tmp_path / "results")
    luna = json.loads(layout.pool_criterion(runner, layout.LUNA_POOL).read_text())
    assert (layout.pool_criterion(runner, "first"), luna) == (criterion, {"judges": [spend.HAIKU],
                                                                          "rubric": layout.RUBRIC})


def frozen_with(tmp_path, terms):
    (tmp_path / "criterion.json").write_text(json.dumps({"spend": terms}))
    return SimpleNamespace(frozen=tmp_path / "criterion.json")


def test_a_freeze_without_the_luna_smokes_terms_bounds_the_studys_tranches_alone(tmp_path):
    from tests.experiments.seed_set_offline_support import SPEND_TERMS
    assert rules.bounded(frozen_with(tmp_path, SPEND_TERMS)) == (
        ["smoke", "calibration", "redraw"], [spend.HAIKU, spend.SONNET])


def test_a_freeze_naming_the_luna_smokes_ceiling_bounds_it_and_luna(tmp_path):
    from tests.experiments.seed_set_offline_support import SPEND_TERMS
    terms = SPEND_TERMS | {"ceiling_usd": SPEND_TERMS["ceiling_usd"] | {LUNA_SMOKE: 10.0}}
    assert rules.bounded(frozen_with(tmp_path, terms)) == (
        ["smoke", "calibration", "redraw", LUNA_SMOKE], [spend.HAIKU, spend.SONNET, LUNA])


def test_a_luna_smoke_start_without_its_ceiling_refuses(tmp_path):
    from tests.experiments.seed_set_offline_support import SPEND_TERMS
    with pytest.raises(SystemExit, match="no priced ceiling for luna_smoke"):
        layout.spend_terms(frozen_with(tmp_path, SPEND_TERMS), LUNA_SMOKE, LUNA)
