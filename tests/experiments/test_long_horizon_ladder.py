"""The long-horizon criterion (`experiments/long_horizon_tasks/ladder.json`) and its manifest (`manifest.py`).

The criterion holds the frozen values and rules of the plan's D1 to D7 as data. These tests hold it to the plan's cap
formula, to the recordings and fixtures its rules rest on, and to the kit's price check; and they show that the
manifest notices a one-byte change and refuses to freeze while anything is pending. No container, no network.
"""

import ast
import copy
import glob
import hashlib
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "experiments" / "long_horizon_tasks"
FIXTURES = KIT / "fixtures"
TABLE = ROOT / "orchestrator" / "providers" / "price_table.json"
MODEL = "claude-haiku-5-5"
ARCHIVES = sorted(glob.glob(os.path.join(os.environ.get("LH", os.path.expanduser("~/lh-cache")),
                                         "recordings/archives/*/x")))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


price_check = _load("lh_price_check_ladder", KIT / "price_check.py")
PASSTHROUGH = KIT / "passthrough.py"
passthrough = _load("lh_passthrough_ladder", PASSTHROUGH)
PLAN = ROOT / "docs" / "plans" / "2026-11-13-long-horizon-task-family-and-seed-plan.md"


def _ladder():
    return json.loads((KIT / "ladder.json").read_text())


def _keys(obj):
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    return {k for v in obj for k in _keys(v)} if isinstance(obj, list) else set()


# ---- D1 and D4: caps, model, efforts, deny list, price ------------------------------------------------------

def test_each_cap_follows_the_d1_formula_and_one_cap_per_task_serves_every_effort():
    ladder = _ladder()
    caps, rows = ladder["caps"], ladder["tasks"]["list"]
    names = [t["name"].rsplit("/", 1)[-1] for t in json.loads((KIT / "tasks.json").read_text())["tasks"]]
    want = {t["name"]: round(max(caps["floor_usd"], caps["multiple"] * t["public_mean_usd_at_max"]), 2) for t in rows}
    second_home = [t["name"] for t in json.loads((KIT / "tasks.json").read_text())["tasks"] if "cap" in t]
    assert ([t["name"] for t in rows], {t["name"]: t["cap_usd"] for t in rows}, (caps["floor_usd"], caps["multiple"]),
            set(ladder["attempt"]["efforts"]) & (_keys(caps) | _keys(rows)), second_home) == (
        names, want, (3.0, 3), set(), [])


def test_the_pilot_falls_back_to_the_next_dearest_task_unchanged_since_4_0_0():
    ladder = _ladder()
    unchanged = sorted((t for t in ladder["tasks"]["list"] if not t["changed_since_4_0_0"]),
                       key=lambda t: -t["public_mean_usd_at_max"])
    pilot = ladder["schedule"]["pilot"]
    assert [pilot["task"], *pilot["fallback"]] == [t["name"] for t in unchanged]


def test_the_model_and_the_efforts_are_bound_exactly():
    ladder = _ladder()
    attempt = ladder["attempt"]
    assert (attempt["model"], attempt["efforts"], ladder["harness"]["model_argument"]) == (
        MODEL, ["low", "medium", "high"], f"anthropic/{MODEL}")


OTHER_MODEL = re.compile(r"(?i)\b(?:fable|opus|sonnet|haiku|gpt|gemini|luna|sol|astra|terra)\b"
                         r"|claude-(?!code\b)[\w.-]+")


def test_no_fable_model_and_no_other_model_id_occurs_anywhere_in_the_criterion():
    text = (KIT / "ladder.json").read_text()
    known = set(json.loads(TABLE.read_text())["models"]) - {MODEL}
    rest = text.replace(MODEL, "")
    assert (MODEL in text, [m.group(0) for m in OTHER_MODEL.finditer(rest)], sorted(m for m in known if m in text)) == (
        True, [], [])


def test_the_deny_list_is_the_eighteen_names_the_recordings_ran_with():
    index = json.loads((KIT / "recordings.json").read_text())["recordings"]
    recorded = {re.search(r"--ak disallowed_tools=(\S+)", r["harbor_args"]).group(1)
                for r in index if r["name"].startswith("t2a-") and "disallowed_tools=" in r["harbor_args"]}
    deny = _ladder()["attempt"]["deny_list"]
    assert ([",".join(deny)], len(deny)) == (sorted(recorded), 18)


@pytest.mark.skipif(not ARCHIVES, reason="the three public archives are not in the cache ($LH/recordings/archives)")
@pytest.mark.parametrize("trial", ARCHIVES, ids=lambda path: Path(path).parent.name[:8])
def test_the_criterion_s_price_rule_reproduces_each_public_archive_total(trial):
    rule = price_check.load_rule(KIT / _ladder()["price"]["rule_file"])
    assert round(sum(price_check.price(u, rule) for u in price_check.requests(trial)), 9) == round(
        price_check.cli_total(trial), 9)


def test_the_price_table_by_its_hash_gives_every_rate_but_the_five_minute_write_which_the_criterion_adds():
    price = _ladder()["price"]
    table = json.loads(TABLE.read_text())["models"][MODEL]
    rule = price_check.load_rule(KIT / price["rule_file"])
    rates, long_prompt = rule["per_million_usd"], rule["long_prompt"]
    given = {"input": table["input"], "output": table["output"], "cache_read": table["cache_read"],
             "cache_write_1h": table["cache_write"], "cache_write_5m": price["cache_write_5m_per_million_usd"]}
    long_rates = {k: round(table["long_context"][k] / table[k], 9)
                  for k in ("input", "output", "cache_read", "cache_write")}
    assert (price["table"]["path"], hashlib.sha256(TABLE.read_bytes()).hexdigest(), given,
            table["long_context"]["above_input_tokens"], set(long_rates.values())) == (
        "orchestrator/providers/price_table.json", price["table"]["sha256"], rates,
        long_prompt["above_prompt_tokens"], {long_prompt["multiplier"]})


def _applies(rule, status, value):
    return status != rule["applies_to"].get("status_not") and (value != "" or "header" not in rule["applies_to"])


def _stops(rule, value):
    if "stops_unless_in" in rule:
        return value not in rule["stops_unless_in"]
    return value == rule.get("stops_if") or value in rule.get("stops_if_in", [])


def _paid_stop(status, headers, paid=None):
    """Whether the criterion's paid-usage rule stops the tranche at a response of this status and these headers: a
    header absent or empty reads as "", and its value is lower-cased where `value_case` says case is ignored."""
    paid = paid or _ladder()["paid_usage"]
    fold = str.lower if paid.get("value_case") == "ignored" else str
    rules = paid["passthrough_stop"]
    values = {rule["header"]: fold(headers.get(rule["header"]) or "") for rule in rules}
    return any(_applies(rule, status, values[rule["header"]]) and _stops(rule, values[rule["header"]])
               for rule in rules)


def test_the_paid_usage_stop_acts_on_the_stand_in_s_responses_as_ruled():
    overage = _load("lh_stub_api_ladder", KIT / "stub_api.py").OVERAGE
    limit = {k: v for k, v in overage.items() if "overage" not in k}  # the usage-limit 429's headers, but its reset
    cases = {"a 200 with the overage headers": (200, overage), "a 429 with the overage headers": (429, overage),
             "the usage-limit 429": (429, limit), "a 200 with no rate-limit header": (200, {}),
             "a 200 whose unified status is allowed": (200, {"anthropic-ratelimit-unified-status": "allowed"}),
             "a 429 with overage allowed only": (429, {"anthropic-ratelimit-unified-overage-status": "allowed"})}
    assert {name: _paid_stop(*case) for name, case in cases.items()} == {
        "a 200 with the overage headers": True, "a 429 with the overage headers": True, "the usage-limit 429": False,
        "a 200 with no rate-limit header": False, "a 200 whose unified status is allowed": False,
        "a 429 with overage allowed only": True}


PAID_VALUES = (None, "", "allowed", "allowed_warning", "rejected", "true", "false", "ALLOWED", "True")


def test_the_paid_usage_rule_quotes_d4_and_as_data_stops_exactly_where_the_passthrough_s_own_check_does():
    """The three signals of D4, every combination of nine values each at three statuses, fed through the rule as data
    and through `Passthrough.paid_signal` (its only state is the --paid-usage list, empty here)."""
    paid = _ladder()["paid_usage"]
    names = sorted({rule["header"] for rule in paid["passthrough_stop"]}
                   | {v for k, v in passthrough.PAID_USAGE.items() if k != "allowed"})
    grid = [(status, {n: v for n, v in zip(names, values) if v is not None})
            for status in (200, 429, 500) for values in itertools.product(PAID_VALUES, repeat=len(names))]
    own = SimpleNamespace(paid_usage=[])
    differ = [case for case in grid
              if _paid_stop(*case, paid) != bool(passthrough.Passthrough.paid_signal(own, *case))]
    quote = paid["passthrough_stop_rule"].rsplit(" (D4)", 1)[0]
    assert (quote in " ".join(PLAN.read_text().split()), len(names), differ[:3]) == (True, 3, [])


def test_the_worst_case_the_criterion_states_is_the_passthrough_s_bound():
    """D4: a response whose usage cannot be read whole is priced with the larger of the body's bytes and the prompt
    message_start reported, at the stated prompt rate, and max_tokens at the stated output rate, with the long-prompt
    multiplier above the threshold."""
    worst, rule = _ladder()["price"].get("worst_case", {}), price_check.load_rule()
    rates, long_prompt = rule["per_million_usd"], rule["long_prompt"]

    def stated(body, start, output):
        prompt = max(body, sum((start or {}).values()))
        usd = (prompt * rates.get(worst.get("prompt_rate"), float("nan"))
               + output * rates.get(worst.get("output_rate"), float("nan"))) / 1e6
        return round(usd * (long_prompt["multiplier"] if prompt > long_prompt["above_prompt_tokens"] else 1), 12)

    cases = [(20_000, None, 32_000), (150_000, None, 64_000),
             (10, {"input_tokens": 1000, "cache_read_input_tokens": 120_000}, 1000)]
    code = [round(passthrough._price(passthrough._worst_case(start, {"max_tokens": out}, body)), 12)
            for body, start, out in cases]
    assert code == [stated(*case) for case in cases]


def test_the_agent_setup_timeout_multiplier_is_the_one_every_task_2a_recording_ran_with():
    index = json.loads((KIT / "recordings.json").read_text())["recordings"]
    recorded = {tuple(re.findall(r"--agent-setup-timeout-multiplier (\S+)", r["harbor_args"]))
                for r in index if r["name"].startswith("t2a-") and "--agent claude-code" in r["harbor_args"]}
    assert recorded == {(str(_ladder()["harness"]["agent_setup_timeout_multiplier"]),)}


# ---- D5: every rule rests on the fixtures it cites ----------------------------------------------------------

# The reader of the pattern language is the launcher's (ladder.py); these tests hold it to the fixtures.
ladder = _load("lh_ladder_reader", KIT / "ladder.py")
MISSING, _result, _events = ladder.MISSING, ladder.result_event, ladder.stream_of
STREAM, HARNESS = ladder.STREAM, ladder.HARNESS
_field, _like, OPS, _holds = ladder.field, ladder.like, ladder.OPS, ladder.holds
_alts, _matches, _classify, OWN_STOPS, _log = ladder.alts, ladder.matches, ladder.classify, ladder.OWN_STOPS, ladder.log_view


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


ALL_FIXTURES = [json.loads(p.read_text()) for p in sorted(FIXTURES.glob("*.json"))]


def _leaves(pattern):
    if isinstance(pattern, dict):
        return [x for v in pattern.values() for x in _leaves(v)]
    return [] if pattern == "*" else [pattern]


def _passthrough_problems(alt, cited, ladder):
    """A passthrough condition cannot be read from a stream fixture: its keys must be the log's, its header names the
    stand-in's (stub_api.py), and every value it matches must occur in a cited fixture."""
    problems, stub = [], (KIT / "stub_api.py").read_text()
    row_keys, causes = set(ladder["classification"]["passthrough_row_keys"]), set(ladder["classification"]["own_stops"])
    for name, test in ((f, t) for f, t in alt.items() if f.startswith("passthrough.")):
        pattern = next(iter(test.values()))
        if name == "passthrough.own_stops":
            problems += [] if pattern in causes | {"*"} else [f"{name}: unknown cause {pattern!r}"]
            continue
        problems += [f"{name}: unknown key {k}" for k in set(pattern) - row_keys]
        problems += [f"{name}: header {h} not in stub_api.py" for h in pattern.get("headers", {}) if h not in stub]
        problems += [f"{name}: {v!r} in no cited fixture" for v in _leaves(pattern)
                     if not any(json.dumps(v).strip('"') in json.dumps(fx) for fx in cited.values())]
    return problems


def _unseen(name):
    """A field outside the passthrough's log that no fixture of the kit holds: misspelt, or resting on nothing."""
    return not name.startswith("passthrough.") and all(_field(fx, name) is MISSING for fx in ALL_FIXTURES)


def _field_problems(row, ladder):
    """Every field a row names is in the language, and every field read from a fixture occurs in one."""
    fields = ladder["classification"]["fields"]
    named = {f for alt in _alts(row) + row.get("recorded_form", []) for f in alt}
    unknown = [f"field {f} not in the language" for f in named
               if f not in fields and f"{f.split('.')[0]}.*" not in fields]
    return unknown + [f"field {f} in no fixture" for f in named if _unseen(f)]


def _local_forms(row):
    """What a row asks of the fields fixtures hold: its recorded forms where it has them (its match reads the
    passthrough's log alone), else its alternatives without their passthrough conditions."""
    return row.get("recorded_form") or [{f: t for f, t in alt.items() if not f.startswith("passthrough.")}
                                        for alt in _alts(row)]


def _match_problems(row, cited):
    """Each local form matches a cited fixture, and each cited fixture is matched by one."""
    local = _local_forms(row)
    ok = {name: [all(_holds(t, _field(fx, f)) for f, t in alt.items()) for alt in local] for name, fx in cited.items()}
    unmatched = [f"alternative {i} matches no cited fixture" for i in range(len(local))
                 if not any(v[i] for v in ok.values())]
    return unmatched + [f"{name} matched by no alternative" for name, v in ok.items() if not any(v)]


def _resting(row, ladder):
    """The row with each alternative for a reason no recording shows (`rests_on`: refusal.form_reasons) read as the
    recorded alternative it rests on: the same form, with the recorded reason's text in place of its own."""
    rests = row.get("rests_on")
    if not rests:
        return row
    text = json.dumps(row["match"])
    for reason in ladder["refusal"][rests["reasons"]].values():
        text = text.replace(reason, rests["reason"])
    return {**row, "match": json.loads(text)}


def _problems(row, ladder):
    """What keeps a D5 row from resting on the fixtures it cites; empty when it does."""
    row = _resting(row, ladder)
    problems = _field_problems(row, ladder)
    if not row["fixtures"]:
        return problems + ([] if row.get("no_fixture") else ["no fixture and no reason"])
    cited = {name: _fixture(name) for name in row["fixtures"] + row.get("shared_fixtures", [])}
    return problems + _match_problems(row, cited) + [p for alt in _alts(row)
                                                     for p in _passthrough_problems(alt, cited, ladder)]


def test_every_d5_rule_matches_the_fixtures_it_cites():
    ladder = _ladder()
    rows = ladder["classification"]["rows"]
    assert ([r["row"] for r in rows], {r["row"]: _problems(r, ladder) for r in rows if _problems(r, ladder)}) == (
        list(range(1, 17)), {})


@pytest.mark.parametrize(("row", "old", "new"), [(5, "result.terminal_reason", "result.terminal_reasn"),
                                                 (6, "result.api_error_status", "result.api_error_statuss"),
                                                 (3, "harness.exception", "harnes.exception"),
                                                 (11, "passthrough.requests", "passthrough.request")])
def test_a_rule_with_a_misspelt_field_is_caught(row, old, new):
    ladder = _ladder()
    rule = copy.deepcopy(next(r for r in ladder["classification"]["rows"] if r["row"] == row))
    rule["match"] = [{(new if f == old else f): t for f, t in alt.items()} for alt in rule["match"]]
    assert _problems(rule, ladder) != []


def test_a_passthrough_value_no_cited_fixture_shows_is_caught():
    ladder = _ladder()
    rule = copy.deepcopy(next(r for r in ladder["classification"]["rows"] if r["row"] == 11))
    rule["match"][0]["passthrough.requests"] = {"some": {"refused": "slot cap reachd"}}
    assert _problems(rule, ladder) != []


def _recording_of(fx):
    local = re.match(r"local recording ([a-z0-9-]+)", fx["source"])
    public = re.match(r"public trial ([0-9a-f]{8})", fx["source"])
    return local.group(1) if local else f"public-{public.group(1)}" if public else None


INDEX = {r["name"]: r for r in json.loads((KIT / "recordings.json").read_text())["recordings"]}
SLOTLESS = ("tranche stopped", "path not allowed", "unknown token")  # passthrough.py: refused before the slot is known
SIGNAL_1 = {"anthropic-ratelimit-unified-status": "rejected"}


def _log_row(status, reason, scenario):
    if status == 403 and reason:
        return {"slot": None if reason in SLOTLESS else "s", "status": 403, "refused": reason}
    signal = {"headers": SIGNAL_1} if status == 429 and scenario == "usage_limit" else {}
    return {"slot": "s", "status": status, **signal}


def _with_log(name, rows, ended_at=10):
    """A recorded session with a constructed log; a row without a time is stamped 2, before the ending at 10."""
    return {**_fixture(name), "_log": _log([{"time": 2, **row} for row in rows], ended_at)}


def _session(fx):
    """The fixture with a stand-in for the passthrough's log of its attempt (_session_rows); every request precedes
    the session's ending."""
    rows = _session_rows(fx)
    return {**fx, "_log": _log(rows, len(rows))}


def _session_rows(fx):
    """A stand-in for the passthrough's rows of a fixture's attempt, built from what was recorded: one row per
    request the stand-in answered, with the status its request fixture holds and its index as its time; a 403
    carries the reason the result text names, and a 429 of the usage-limit scenario carries signal 1. A refusal the
    passthrough logs with no slot has a null slot (it is in the tranche's rows only)."""
    name = _recording_of(fx)
    path = FIXTURES / "requests" / f"{name}.json"
    statuses = [row[1] for row in json.loads(path.read_text())["requests"]] if path.is_file() else []
    text = (_result(fx).get("result") or "") if _result(fx) is not MISSING else ""
    reason = re.search(r"lh-passthrough: ([a-z -]*[a-z])", text)
    scenario = re.search(r"scenario (\S+)", INDEX.get(name, {}).get("source", ""))
    return [{**_log_row(status, reason and reason.group(1), scenario and scenario.group(1)), "time": i}
            for i, status in enumerate(statuses)]


BY_NAME = [("pre-session-", 1), ("no-credential", 2), ("forced-empty", 2), ("token-simple-mode-", 2), ("timeout", 3),
           ("normal-end", 5), ("budget-stop", 6), ("context-limit", 7), ("refusal", 8), ("output-limit", 9),
           ("usage-limit", 10), ("passthrough-cap", 11), ("passthrough-total", 12), ("passthrough-stopped", 12),
           ("passthrough-", 13), ("unauthorized", 14), ("rate-limit", 15), ("server-error", 15), ("overloaded", 15),
           ("slow-first-byte", 15)]
REJECTED_FORMS = {"simple-mode-passthrough-model-NonZeroAgentExitCodeError": "the 404 form D4 rejected: retried; lost",
                  "simple-mode-passthrough-tool-UnknownApiError": "the 400 form D4 rejected: retried"}
SESSIONS = sorted(p.stem for p in FIXTURES.glob("*.json"))


def _named_row(name):
    """The row a fixture's name says its ending belongs to; the two refusal forms D4 rejected match no row."""
    return 16 if name in REJECTED_FORMS else next(row for part, row in BY_NAME if part in name)


def test_every_session_fixture_is_classified_in_order_into_the_row_that_cites_it_or_that_its_name_says():
    ladder = _ladder()
    cited = {f: row["row"] for row in ladder["classification"]["rows"] for f in row["fixtures"]}
    got = {name: _classify(_session(_fixture(name)), ladder) for name in SESSIONS}
    want = {name: cited.get(name, _named_row(name)) for name in SESSIONS}
    assert (len(SESSIONS), {n: (got[n], want[n]) for n in SESSIONS if got[n] != want[n]},
            {n: _named_row(n) for n in cited if _named_row(n) != cited[n]}) == (73, {}, {})


WITHHELD_429 = {"slot": "s", "status": 429, "passed_on": False,
                "headers": {**SIGNAL_1, "anthropic-ratelimit-unified-overage-status": "allowed"}}
LIMIT = {"slot": "s", "status": 429, "headers": SIGNAL_1, "time": 1}
OVERRIDDEN = {3: ("stub-timeout-AgentTimeoutError", []), 5: ("token-three-tools-normal-end", []),
              6: ("stub-budget-stop-NonZeroAgentExitCodeError", []),
              7: ("stub-context-limit-NonZeroAgentExitCodeError", []), 8: ("stub-refusal-AgentSafetyRefusalError", []),
              9: ("stub-output-limit-OutputTokenExceededError", []),
              11: ("passthrough-cap-UnknownApiError", [{"slot": "s", "status": 403, "refused": "slot cap reached"}]),
              12: ("passthrough-total-UnknownApiError",
                   [{"slot": "s", "status": 403, "refused": "tranche total reached"}]),
              14: ("token-unauthorized-UnknownApiError", [{"slot": "s", "status": 401}])}


def _constructed():
    """Sessions no recording shows, built from recorded ones, one for each pair of rows the order resolves, keyed by
    the pair: signal 1 met before the ending of each ending row 10 overrides; a vendor 401 behind the passthrough,
    whose retries meet `tranche stopped`; and a usage-limit 429 carrying an overage sign, which the passthrough
    withholds (D4), so the client meets `tranche stopped`."""
    sessions = {frozenset((10, row)): _with_log(name, [LIMIT, *rows]) for row, (name, rows) in OVERRIDDEN.items()}
    sessions[frozenset((14, 12))] = _with_log("passthrough-stopped-UnknownApiError", [
        {"slot": "s", "status": 200}, {"slot": "s", "status": 401},
        {"slot": None, "status": 403, "refused": "tranche stopped"}])
    sessions[frozenset((13, 10))] = _with_log("passthrough-stopped-UnknownApiError", [WITHHELD_429])
    return sessions


def _matching(session, ladder):
    return frozenset(row["row"] for row in ladder["classification"]["rows"] if row["row"] != 16
                     and _matches(row, session))


def test_two_rows_match_one_session_only_where_a_listed_pair_says_why_the_order_resolves_it():
    ladder = _ladder()
    listed = {frozenset(pair["rows"]) for pair in ladder["classification"]["order_resolves"]}
    constructed = _constructed()
    sessions = {name: _session(_fixture(name)) for name in SESSIONS} | {
        f"constructed {sorted(pair)}": session for pair, session in constructed.items()}
    many = {name: m for name, s in sessions.items() if len(m := _matching(s, ladder)) > 1}
    assert ({n: sorted(m) for n, m in many.items() if m not in listed}, set(many.values()),
            {sorted(p)[0]: sorted(_matching(s, ladder)) for p, s in constructed.items() if _matching(s, ladder) != p}
            ) == ({}, listed, {})


def test_the_order_is_d5_s_and_the_natural_order_would_misclassify():
    """Each listed pair's session lands in the row the pair names first; the natural order would take the lower row,
    which differs for every pair in which the later row wins."""
    ladder = _ladder()
    winners = {frozenset(pair["rows"]): pair["rows"][0] for pair in ladder["classification"]["order_resolves"]}
    sessions = _constructed()
    stated = {pair: _classify(sessions[pair], ladder) for pair in winners}
    natural = {pair: _classify(sessions[pair], ladder, list(range(1, 17))) for pair in winners}
    assert (ladder["classification"]["order"], stated, natural) == (
        [13, 10, 1, 2, 3, 4, 5, 6, 7, 8, 9, 14, 11, 12, 15, 16], winners, {pair: min(pair) for pair in winners})


def test_a_usage_limit_met_only_after_the_ending_leaves_the_attempt_in_its_own_row():
    """A time-limit session whose requests after the limit (ending at 3) meet a usage limit stays in row 3, as a
    provider fault stays in row 15; the same limit met before the ending makes the time-limit session a cut."""
    ladder = _ladder()
    after = {"slot": "s", "status": 429, "headers": SIGNAL_1, "time": 5}
    sessions = [_with_log("stub-timeout-AgentTimeoutError", [{"slot": "s", "status": 200, "time": 1}, after], 3),
                _with_log("stub-rate-limit-ApiRateLimitError", [{"slot": "s", "status": 429, "time": 1}, after], 3),
                _with_log("stub-timeout-AgentTimeoutError", [{"slot": "s", "status": 200, "time": 1}, LIMIT], 3)]
    assert [_classify(session, ladder) for session in sessions] == [3, 15, 10]


def test_a_session_with_signal_2_alone_pauses():
    session = {**_fixture("token-usage-limit-NonZeroAgentExitCodeError"), "_log": _log([{"slot": "s", "status": 429}])}
    assert _classify(session, _ladder()) == 16


def test_the_rate_limit_event_of_signal_2_tells_a_usage_limit_from_a_plain_429():
    row = next(r for r in _ladder()["classification"]["rows"] if r["row"] == 10)
    event = row["recorded_form"][0]["stream.rate_limit"]
    assert [_holds(event, _field(_fixture(name), "stream.rate_limit"))
            for name in ("token-usage-limit-NonZeroAgentExitCodeError", "stub-rate-limit-ApiRateLimitError")] == [
        True, False]


ROW_CLASSES = {1: ("pre_session_failure", False, False), 2: ("stop", False, False), 3: ("observation", True, False),
               4: ("infrastructure_failure", False, False), 5: ("observation", False, False),
               6: ("observation", True, False), 7: ("observation", True, False), 8: ("observation", True, False),
               9: ("observation", True, False), 10: ("cut", False, False), 11: ("observation", True, False),
               12: ("infrastructure_failure", False, False), 13: ("stop", False, False),
               14: ("infrastructure_failure", False, True), 15: ("infrastructure_failure", False, False),
               16: ("ruling", False, False)}
COUNTING = {"observation": (True, True, True, False), "infrastructure_failure": (True, True, False, False),
            "cut": (True, True, False, True), "pre_session_failure": (False, False, False, True),
            "stop": (True, True, False, False), "ruling": (True, True, None, None)}


def _count(value):
    return None if value == "by the ruling" else bool(value)


def test_each_row_s_class_and_each_class_s_count_are_d5_s():
    classification = _ladder()["classification"]
    rows = {r["row"]: (r["class"], r.get("flagged", False), r.get("stop", False)) for r in classification["rows"]}
    counting = {name: tuple(_count(c[k]) for k in ("starts", "usd", "k_n", "rerun"))
                for name, c in classification["classes"].items()}
    own_stops = {r["row"]: r["class"] for r in classification["rows"] for alt in _alts(r)
                 if "some" in alt.get("passthrough.own_stops", {})}
    assert (rows, counting, own_stops) == (ROW_CLASSES, COUNTING, {13: "stop"})


def test_every_fixture_a_row_cites_exists_and_its_recording_is_indexed():
    names = {r["name"] for r in json.loads((KIT / "recordings.json").read_text())["recordings"]}
    cited = sorted({f for row in _ladder()["classification"]["rows"] for f in row["fixtures"]})
    missing = [f for f in cited if not (FIXTURES / f"{f}.json").is_file()]
    unindexed = [f for f in cited if f not in missing and _recording_of(_fixture(f)) not in names]
    assert (bool(cited), missing, unindexed) == (True, [], [])


# ---- the passthrough's refusal reasons and its log, read from passthrough.py ---------------------------------

REFUSERS = ("Refusal", "_refusal", "_refuse")


def _values(node):
    """The strings an expression of passthrough.py can evaluate to, where it names them."""
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.IfExp):
        return _values(node.body) | _values(node.orelse)
    if isinstance(node, ast.BoolOp):
        return set().union(*map(_values, node.values))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Dict):
        return set().union(*map(_values, node.func.value.values + node.args[1:]))  # {...}.get(key, default)
    return set()


def _callee(call):
    return call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", None)


def _assigned(fn):
    """Each name a function assigns -> the expressions it assigns to it."""
    assigned = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            assigned.setdefault(node.targets[0].id, []).append(node.value)
    return assigned


def _refused_in(fn):
    """The reasons one function refuses with: what it hands a refusal (itself, or by a name it assigns), and what a
    `*_reason` function returns."""
    assigned = _assigned(fn)
    given = [node.args[0] for node in ast.walk(fn) if isinstance(node, ast.Call) and _callee(node) in REFUSERS
             and node.args]
    exprs = [e for arg in given for e in (assigned.get(arg.id, []) if isinstance(arg, ast.Name) else [arg])]
    returned = [n.value for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value and fn.name.endswith("_reason")]
    return set().union(*map(_values, exprs + returned))


def _code_reasons():
    """Every reason passthrough.py can refuse a request with (the 403 form's `lh-passthrough: <reason>`)."""
    tree = ast.parse(PASSTHROUGH.read_text())
    return set().union(*(_refused_in(fn) for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)))


def test_the_criterion_names_every_reason_the_passthrough_can_refuse_with_once():
    refusal = _ladder()["refusal"]
    named = [r for group in ("reasons", "form_reasons", "load_reasons") for r in (refusal.get(group) or {}).values()]
    assert (sorted(named), len(named)) == (sorted(_code_reasons()), len(set(named)))


REASON_ROWS = {"slot cap reached": 11, "tranche total reached": 12, "tranche stopped": 12, "too many connections": 15,
               "slot busy": 15, "request timed out": 15}  # every other: row 13
OWN_STOP_ROWS = {"paid extra usage": {"passed_on": False}, "token in a log row": {"withheld": "plain"},
                 "response model": {"response_model": "another-model"}}


def _refused_session(reason, slot):
    """The recorded model refusal with its reason replaced, and the passthrough's row for it."""
    fx = copy.deepcopy(_fixture("passthrough-model-UnknownApiError"))
    result = _result(fx)
    result["result"] = result["result"].replace("model not allowed", reason)
    return {**fx, "_log": _log([{"slot": slot, "status": 403, "refused": reason}])}


def _own_stop_session(cause, other):
    """An attempt whose own slot's row shows a stop's cause, so its client meets `tranche stopped`; with `other`,
    another slot's slot-less `tranche stopped` refusal lies in the window too."""
    rows = [{"slot": "s", "status": 200, **OWN_STOP_ROWS[cause]}]
    return _with_log("passthrough-stopped-UnknownApiError",
                     rows + ([{"slot": None, "status": 403, "refused": "tranche stopped"}] if other else []))


def test_a_session_the_passthrough_refused_for_any_of_its_reasons_ends_in_that_reason_s_row():
    """Each reason with the slot logged and without it (a cap's refusal always has one): the load refusals are row 15,
    infrastructure failures (coordinator ruling N2); and each stop whose cause the attempt's own slot's rows show (the
    withheld paid-usage answer among them) is row 13, also with another slot's refusal in the window."""
    ladder = _ladder()
    got = {(reason, slot): _classify(_refused_session(reason, slot), ladder)
           for reason in sorted(_code_reasons()) for slot in ("s", None) if slot or reason != "slot cap reached"}
    own = {(cause, other): _classify(_own_stop_session(cause, other), ladder)
           for cause in ladder["classification"]["own_stops"] for other in (False, True)}
    want = {key: REASON_ROWS.get(key[0], 13) for key in got}
    assert ({key: (got[key], want[key]) for key in got if got[key] != want[key]}, set(own.values()), len(own)) == (
        {}, {13}, 6)


def test_rows_12_and_13_never_both_match_an_attempt_whose_own_slot_stopped_the_tranche():
    ladder = _ladder()
    causes = ladder["classification"]["own_stops"]
    assert {cause: sorted(_matching(_own_stop_session(cause, True), ladder)) for cause in causes} == {
        cause: [13] for cause in causes}


def test_the_log_keys_the_criterion_names_are_keys_the_passthrough_writes():
    classification = _ladder()["classification"]
    log = classification["passthrough_log"] or {}
    named = set(log.get("refused_row", [])) | set(log.get("forwarded_row", [])) | set(log.get("withheld_row", []))
    source = PASSTHROUGH.read_text()
    unwritten = sorted(k for k in named if not re.search(rf'"{k}":|\b{k}=|\["{k}"\] =', source))
    assert (bool(named), sorted(set(classification["passthrough_row_keys"]) - named), unwritten) == (True, [], [])


# ---- pending, manifest and freeze ---------------------------------------------------------------------------

PENDING_OR_FILLED = {
    "tasks.qualified", "tasks.load_sensitive", "tasks.overlay_digests", "tasks.extra_hosts", "tasks.withholding",
    "network.agent_phase.allowed_hosts", "host.cpu_set", "host.disk_plan", "refusal.form_reasons",
    "classification.passthrough_log", "usage_limits.vendor_headers_confirmed", "allowance_guard.utilisation_header",
    "readout.contamination_scan.terms", "readout.contamination_scan.canary_sha256", "readout.graded_outcome.verifiers",
    "schedule.order.seed", "schedule.order.hash", "readout.fall_bound.seed", "readout.cost.dominated_p_at_most"}
TYPE_NAMES = {"array", "object", "string", "sha256", "scalar", "number"}


def test_every_null_is_a_pending_field_and_no_field_leaves_the_list_without_a_record():
    ladder = _ladder()
    manifest = _load("lh_manifest", KIT / "manifest.py")
    entries = ladder["pending"] + ladder["filled"]
    assert (set(manifest.nulls(ladder)), {e["field"] for e in entries},
            [e["field"] for e in entries if e.get("type") not in TYPE_NAMES or not e.get("filled_by")]) == (
        {p["field"] for p in ladder["pending"]}, PENDING_OR_FILLED, [])


@pytest.mark.parametrize("value, typed", [(0.05, True), (4, True), (float("nan"), False), (float("inf"), False),
                                          (True, False), ("0.05", False)])
def test_a_number_filled_field_is_a_finite_integer_or_decimal(value, typed):
    assert _load("lh_manifest", KIT / "manifest.py")._typed(value, "number") is typed


def _kit_copy(tmp_path):
    kit = tmp_path / "repo" / "experiments" / "long_horizon_tasks"
    shutil.copytree(KIT, kit, ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "repo" / "orchestrator" / "providers").mkdir(parents=True)
    shutil.copy(TABLE, tmp_path / "repo" / "orchestrator" / "providers")
    (tmp_path / "repo" / "tests" / "experiments").mkdir(parents=True)
    shutil.copy(__file__, tmp_path / "repo" / "tests" / "experiments" / "test_long_horizon_ladder.py")
    return kit


def _run(kit, *args):
    return subprocess.run([sys.executable, "-I", str(kit / "manifest.py"), *args], capture_output=True, text=True,
                          check=False)


def test_a_frozen_committed_manifest_is_current_and_an_unfrozen_one_reproduces_itself(tmp_path):
    """Before the freeze the committed manifest labels nothing, so only `write` is held to reproduce itself on a copy;
    once frozen, the committed manifest must be current."""
    if json.loads((KIT / "manifest.json").read_text())["frozen"]:
        checked = _run(KIT, "check")
        assert (checked.returncode, checked.stderr) == (0, "")
    else:
        kit = _kit_copy(tmp_path)
        first, second, checked = _run(kit, "write"), _run(kit, "write"), _run(kit, "check")
        assert (first.returncode, second.stdout, checked.returncode, checked.stdout.split()[1:]) == (
            0, first.stdout, 0, ["not", "frozen"])


def test_the_manifest_covers_the_passthrough_the_scanner_the_allowlist_its_builder_and_the_probe():
    covered = set(_load("lh_manifest", KIT / "manifest.py").files())
    kit = {f"experiments/long_horizon_tasks/{name}" for name in (
        "passthrough.py", "token_scan.py", "request_allowlist.json", "make_allowlist.py", "live_probe.sh")}
    assert kit - covered == set()


def _flip(path):
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 1
    path.write_bytes(bytes(data))


CHANGES = {"one byte of a covered kit file": (lambda kit: _flip(kit / "tasks.json"), 1, "tasks.json"),
           "one byte of the price table": (lambda kit: _flip(kit.parents[1] / "orchestrator" / "providers"
                                                             / "price_table.json"), 1, "price_table.json"),
           "one byte of the reference reader": (lambda kit: _flip(kit.parents[1] / "tests" / "experiments"
                                                                  / "test_long_horizon_ladder.py"), 1,
                                                "test_long_horizon_ladder.py"),
           "a new file in the kit": (lambda kit: (kit / "fixtures" / "extra.json").write_text("{}"), 1, "extra.json"),
           "a covered file removed": (lambda kit: (kit / "fixtures" / "public-normal-end.json").unlink(), 1,
                                      "public-normal-end.json"),
           "a wording change in the README": (lambda kit: (kit / "README.md").write_text("changed\n"), 0, "")}


@pytest.mark.parametrize("change", CHANGES)
def test_manifest_check_fails_exactly_when_a_covered_file_changes(tmp_path, change):
    kit = _kit_copy(tmp_path)
    act, code, named = CHANGES[change]
    written, clean = _run(kit, "write"), _run(kit, "check")
    act(kit)
    after = _run(kit, "check")
    label = hashlib.sha256((kit / "manifest.json").read_bytes()).hexdigest()
    assert (written.returncode, written.stdout.split(), clean.returncode, after.returncode, named in after.stderr,
            after.stdout.split()[:1]) == (0, [label], 0, code, True, [label])


SAMPLES = {"array": ["x"], "object": {"x": 1}, "string": "x", "sha256": "0" * 64, "scalar": 1}


def _set(doc, field, value):
    *path, last = field.split(".")
    for key in path:
        doc = doc[key]
    doc[last] = value


def _filled(ladder, value=None, source="a test"):
    """Every pending field filled (with a sample of its type, or `value`) and moved to `filled` with `source`."""
    out = copy.deepcopy(ladder)
    for entry in out["pending"]:
        _set(out, entry["field"], SAMPLES[entry["type"]] if value is None else value)
    out["filled"], out["pending"] = [{**e, "source": source} for e in out["pending"]], []
    return out


FREEZES = {"pending entries left": (lambda d: d, 2),
           "pending emptied, a null left": (lambda d: {**d, "pending": []}, 2),
           "every field filled, typed and sourced": (_filled, 0),
           "a field filled with an empty string": (lambda d: _filled(d, value=""), 2),
           "a field filled with the wrong type": (lambda d: _filled(d, value=7), 2),
           "a field filled with no source": (lambda d: _filled(d, source=""), 2)}


@pytest.mark.parametrize("case", FREEZES)
def test_freeze_is_refused_while_anything_is_pending_or_a_filled_field_is_untyped_or_unsourced(tmp_path, case):
    kit = _kit_copy(tmp_path)
    edit, code = FREEZES[case]
    (kit / "ladder.json").write_text(json.dumps(edit(_ladder()), indent=1))
    before = (kit / "manifest.json").read_bytes()
    frozen = _run(kit, "write", "--freeze")
    after = json.loads((kit / "manifest.json").read_text())
    assert (frozen.returncode, after["frozen"] if code == 0 else (kit / "manifest.json").read_bytes() == before) == (
        code, True)


def test_check_fails_a_manifest_frozen_by_hand_while_anything_is_pending(tmp_path):
    kit = _kit_copy(tmp_path)
    _run(kit, "write")
    recorded = json.loads((kit / "manifest.json").read_text())
    (kit / "manifest.json").write_text(json.dumps({**recorded, "frozen": True}, indent=1) + "\n")
    checked = _run(kit, "check")
    assert (checked.returncode, "pending:" in checked.stderr) == (1, True)


def test_a_plain_write_over_a_frozen_manifest_is_refused(tmp_path):
    kit = _kit_copy(tmp_path)
    (kit / "ladder.json").write_text(json.dumps(_filled(_ladder()), indent=1))
    frozen = _run(kit, "write", "--freeze")
    before = (kit / "manifest.json").read_bytes()
    plain = _run(kit, "write")
    assert (frozen.returncode, plain.returncode, (kit / "manifest.json").read_bytes() == before) == (0, 2, True)
