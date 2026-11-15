"""The long-horizon criterion (`experiments/long_horizon_tasks/ladder.json`) and its manifest (`manifest.py`).

The criterion holds the frozen values and rules of the plan's D1 to D7 as data. These tests hold it to the plan's cap
formula, to the recordings and fixtures its rules rest on, and to the kit's price check; and they show that the
manifest notices a one-byte change and refuses to freeze while anything is pending. No container, no network.
"""

import copy
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

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
    assert ([t["name"] for t in rows], {t["name"]: t["cap_usd"] for t in rows}, (caps["floor_usd"], caps["multiple"]),
            set(ladder["attempt"]["efforts"]) & (_keys(caps) | _keys(rows))) == (names, want, (3.0, 3), set())


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


def _applies(rule, status, headers):
    return rule["header"] in headers and status != rule["applies_to"].get("status_not")


def _stops(rule, value):
    if "stops_unless_in" in rule:
        return value not in rule["stops_unless_in"]
    return value == rule.get("stops_if") or value in rule.get("stops_if_in", [])


def _paid_stop(status, headers):
    """Whether the criterion's paid-usage rule stops the tranche at a response of this status and these headers."""
    rules = _ladder()["paid_usage"]["passthrough_stop"]
    return any(_applies(rule, status, headers) and _stops(rule, headers[rule["header"]]) for rule in rules)


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


def test_the_agent_setup_timeout_multiplier_is_the_one_every_task_2a_recording_ran_with():
    index = json.loads((KIT / "recordings.json").read_text())["recordings"]
    recorded = {tuple(re.findall(r"--agent-setup-timeout-multiplier (\S+)", r["harbor_args"]))
                for r in index if r["name"].startswith("t2a-") and "--agent claude-code" in r["harbor_args"]}
    assert recorded == {(str(_ladder()["harness"]["agent_setup_timeout_multiplier"]),)}


# ---- D5: every rule rests on the fixtures it cites ----------------------------------------------------------

MISSING = object()


def _result(fx):
    found = [e for e in fx.get("stream_tail") or [] if e.get("type") == "result"]
    return found[-1] if found else MISSING


def _events(fx, kind):
    return [e for e in fx.get("stream_tail") or [] if e.get("type") == kind]


STREAM = {"events": lambda fx: fx["n_events"], "api_retry": lambda fx: fx["n_api_retry"],
          "system_subtypes": lambda fx: [e.get("subtype") for e in _events(fx, "system")],
          "rate_limit": lambda fx: [e["rate_limit_info"] for e in _events(fx, "rate_limit_event")]}
HARNESS = {"exception": "harness_exception", "message": "exception_message"}


def _field(fx, name):
    """The value a rule's field names in a fixture, or MISSING (an unknown field is MISSING everywhere)."""
    head, _, key = name.partition(".")
    if head == "result":
        result = _result(fx)
        return result if not key or result is MISSING else result.get(key, MISSING)
    if head == "harness":
        return fx if not key else fx.get(HARNESS.get(key), MISSING)
    return STREAM[key](fx) if head == "stream" and key in STREAM else MISSING


def _like(pattern, value):
    if isinstance(pattern, dict):
        return isinstance(value, dict) and all(k in value and _like(p, value[k]) for k, p in pattern.items())
    return pattern == "*" or pattern == value


OPS = {"absent": lambda arg, v: (v is MISSING) == arg, "null": lambda arg, v: (v is None) == arg,
       "in": lambda arg, v: v is not MISSING and v in arg, "not_in": lambda arg, v: v is MISSING or v not in arg,
       "contains": lambda arg, v: isinstance(v, str) and arg in v,
       "lacks": lambda arg, v: isinstance(v, str) and arg not in v,
       "some": lambda arg, v: isinstance(v, list) and any(_like(arg, x) for x in v),
       "none": lambda arg, v: isinstance(v, list) and not any(_like(arg, x) for x in v)}


def _holds(test, value):
    if isinstance(test, dict) and len(test) == 1 and next(iter(test)) in OPS:
        (op, arg), = test.items()
        return OPS[op](arg, value)
    return value is not MISSING and value == test


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
    row_keys = set(ladder["classification"]["passthrough_row_keys"])
    for name, test in ((f, t) for f, t in alt.items() if f.startswith("passthrough.")):
        pattern = next(iter(test.values()))
        problems += [f"{name}: unknown key {k}" for k in set(pattern) - row_keys]
        problems += [f"{name}: header {h} not in stub_api.py" for h in pattern.get("headers", {}) if h not in stub]
        problems += [f"{name}: {v!r} in no cited fixture" for v in _leaves(pattern)
                     if not any(json.dumps(v).strip('"') in json.dumps(fx) for fx in cited.values())]
    return problems


def _alts(row):
    return [] if row["match"] == "otherwise" else row["match"]


def _unseen(name):
    """A field outside the passthrough's log that no fixture of the kit holds: misspelt, or resting on nothing."""
    return not name.startswith("passthrough.") and all(_field(fx, name) is MISSING for fx in ALL_FIXTURES)


def _field_problems(row, ladder):
    """Every field a row names is in the language, and every field read from a fixture occurs in one."""
    fields = ladder["classification"]["fields"]
    named = {f for alt in _alts(row) for f in alt} | set(row.get("recorded_form", {}))
    unknown = [f"field {f} not in the language" for f in named
               if f not in fields and f"{f.split('.')[0]}.*" not in fields]
    return unknown + [f"field {f} in no fixture" for f in named if _unseen(f)]


def _match_problems(row, cited):
    """Each alternative matches a cited fixture, and each cited fixture is matched, on the fields fixtures hold."""
    local = [{f: t for f, t in alt.items() if not f.startswith("passthrough.")} | row.get("recorded_form", {})
             for alt in _alts(row)]
    ok = {name: [all(_holds(t, _field(fx, f)) for f, t in alt.items()) for alt in local] for name, fx in cited.items()}
    unmatched = [f"alternative {i} matches no cited fixture" for i in range(len(local))
                 if not any(v[i] for v in ok.values())]
    return unmatched + [f"{name} matched by no alternative" for name, v in ok.items() if not any(v)]


def _problems(row, ladder):
    """What keeps a D5 row from resting on the fixtures it cites; empty when it does."""
    problems = _field_problems(row, ladder)
    if not row["fixtures"]:
        return problems + ([] if row.get("no_fixture") else ["no fixture and no reason"])
    cited = {name: _fixture(name) for name in row["fixtures"]}
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


def test_every_fixture_a_row_cites_exists_and_its_recording_is_indexed():
    names = {r["name"] for r in json.loads((KIT / "recordings.json").read_text())["recordings"]}
    cited = sorted({f for row in _ladder()["classification"]["rows"] for f in row["fixtures"]})
    missing = [f for f in cited if not (FIXTURES / f"{f}.json").is_file()]
    unindexed = [f for f in cited if f not in missing and _recording_of(_fixture(f)) not in names]
    assert (bool(cited), missing, unindexed) == (True, [], [])


# ---- pending, manifest and freeze ---------------------------------------------------------------------------

def _under(path, field):
    return path == field or path.startswith((field + ".", field + "["))


def test_every_null_of_the_criterion_is_pending_and_every_pending_entry_holds_a_null():
    ladder = _ladder()
    manifest = _load("lh_manifest", KIT / "manifest.py")
    nulls, fields = list(manifest.nulls(ladder)), [p["field"] for p in ladder["pending"]]
    assert ([n for n in nulls if not any(_under(n, f) for f in fields)],
            [f for f in fields if not any(_under(n, f) for n in nulls)],
            [p["field"] for p in ladder["pending"] if not p.get("filled_by")]) == ([], [], [])


def _kit_copy(tmp_path):
    kit = tmp_path / "repo" / "experiments" / "long_horizon_tasks"
    shutil.copytree(KIT, kit, ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "repo" / "orchestrator" / "providers").mkdir(parents=True)
    shutil.copy(TABLE, tmp_path / "repo" / "orchestrator" / "providers")
    return kit


def _run(kit, *args):
    return subprocess.run([sys.executable, "-I", str(kit / "manifest.py"), *args], capture_output=True, text=True,
                          check=False)


def test_the_committed_manifest_is_current():
    """A kit change merged without `manifest.py write` fails here (README: the rerun belongs in that merge)."""
    checked = _run(KIT, "check")
    assert (checked.returncode, checked.stderr) == (0, "")


def _flip(path):
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 1
    path.write_bytes(bytes(data))


CHANGES = {"one byte of a covered kit file": (lambda kit: _flip(kit / "tasks.json"), 1, "tasks.json"),
           "one byte of the price table": (lambda kit: _flip(kit.parents[1] / "orchestrator" / "providers"
                                                             / "price_table.json"), 1, "price_table.json"),
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


def _fill(obj):
    if isinstance(obj, dict):
        return {k: _fill(v) for k, v in obj.items()}
    return [_fill(v) for v in obj] if isinstance(obj, list) else ("filled" if obj is None else obj)


FREEZES = {"pending entries left": (lambda d: d, 2),
           "pending emptied, a null left": (lambda d: {**d, "pending": []}, 2),
           "pending emptied, every null filled": (lambda d: {**_fill(d), "pending": []}, 0)}


@pytest.mark.parametrize("case", FREEZES)
def test_freeze_is_refused_while_anything_is_pending(tmp_path, case):
    kit = _kit_copy(tmp_path)
    edit, code = FREEZES[case]
    (kit / "ladder.json").write_text(json.dumps(edit(_ladder()), indent=1))
    before = (kit / "manifest.json").read_bytes()
    frozen = _run(kit, "write", "--freeze")
    after = json.loads((kit / "manifest.json").read_text())
    assert (frozen.returncode, after["frozen"] if code == 0 else (kit / "manifest.json").read_bytes() == before) == (
        code, True)
