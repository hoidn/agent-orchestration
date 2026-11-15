"""Seed-set spend guard (experiments/seed_set/spend.py), the order and stop rules (rules.py), the per-unit checks
(units.py, host.py) and the runner's refusals before any provider start (study.py). Nothing here launches a
provider process; the end-to-end launch path is in test_seed_set_e2e.py."""

import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from experiments.compare.repos import sha256_file
from experiments.seed_set import host, layout, rules, spend, study, units
from tests.experiments.seed_set_offline_support import (
    REPORTED_USD, SPEND_TERMS, USAGE, committed_runtime, stable_anchors, write_frozen_criterion,
)

H, S = spend.HAIKU, spend.SONNET
P = (1000.0, 0.01)  # a priced ceiling and per-call worst case no test here reaches
ROOT = Path(__file__).resolve().parents[2]
AUTH = spend.AUTHORIZATION


def env(tranche):
    return {AUTH: tranche}


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "results" / "spend-ledger.jsonl"


def test_no_authorization_variable_refuses():
    with pytest.raises(SystemExit, match="provider spend refused"):
        spend.authorize("calibration", {})


def test_an_authorization_for_another_tranche_refuses():
    with pytest.raises(SystemExit, match="provider spend refused"):
        spend.authorize("calibration", env("smoke"))


@pytest.mark.parametrize("tranche", ["seed_evaluation", "extension"])
def test_an_unauthorized_tranche_refuses_even_when_named(tranche):
    with pytest.raises(SystemExit, match="not authorized"):
        spend.authorize(tranche, env(tranche))


def test_an_unknown_tranche_refuses():
    with pytest.raises(SystemExit, match="unknown tranche"):
        spend.authorize("bonus", env("bonus"))


def test_caps_are_the_plans_budget():
    caps = {t: {k: dict(m) for k, m in kinds.items()} for t, kinds in spend.CAPS.items()}
    assert caps == {"smoke": {"candidate": {H: 10, S: 1}, "judge": {H: 1, S: 1}},
                    "calibration": {"candidate": {H: 80, S: 20}, "judge": {H: 30, S: 30}},
                    "redraw": {"candidate": {H: 40, S: 0}, "judge": {H: 0, S: 0}}}  # review2 M4: probe only


def test_a_start_is_appended_before_it_is_returned(ledger):
    row = spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/records/retry/run-1", env("smoke"), task="t", price=P)
    assert spend.rows(ledger) == [row]


def test_a_unit_is_never_started_twice(ledger):
    spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/records/direct/run-1", env("smoke"), price=P)
    with pytest.raises(SystemExit, match="never retried"):
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/records/direct/run-1", env("smoke"), price=P)


def test_the_call_beyond_a_cap_refuses_and_writes_nothing(ledger):
    for k in range(10):
        spend.reserve(ledger, "smoke", "candidate", H, 1, f"/w/run-{k}", env("smoke"), price=P)
    before = ledger.read_bytes()
    with pytest.raises(SystemExit, match="cap reached"):
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-10", env("smoke"), price=P)
    assert ledger.read_bytes() == before


def test_a_start_reserves_its_maximum_calls_against_the_cap(ledger):
    spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/a", env("smoke"), price=P)
    spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/b", env("smoke"), price=P)
    spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/c", env("smoke"), price=P)
    with pytest.raises(SystemExit, match="cap reached"):
        spend.reserve(ledger, "smoke", "candidate", H, 3, "/w/d", env("smoke"), price=P)


def test_tranches_and_kinds_do_not_share_allowance(ledger):
    spend.reserve(ledger, "smoke", "judge", S, 1, "/p#s", env("smoke"), price=P)
    with pytest.raises(SystemExit, match="cap reached"):
        spend.reserve(ledger, "smoke", "judge", S, 1, "/q#s", env("smoke"), price=P)
    assert spend.reserve(ledger, "calibration", "judge", S, 1, "/q#s", env("calibration"), price=P)["seq"] == 2


def test_a_batch_that_does_not_fit_is_refused_before_any_start(ledger):
    with pytest.raises(SystemExit, match="21 calls planned but 20"):
        spend.check(ledger, "calibration", "candidate", S, 21, env("calibration"))


@pytest.mark.parametrize("model", ["claude-fable-5-1", "claude-opus-5-5", "claude-haiku", "haiku", "", None])
def test_a_model_outside_the_two_exact_ids_refuses_and_writes_nothing(ledger, model):
    with pytest.raises(SystemExit, match="exact IDs"):
        spend.reserve(ledger, "smoke", "candidate", model, 1, "/w/run-1", env("smoke"), price=P)
    assert not ledger.exists()


@pytest.fixture
def runner(tmp_path, monkeypatch):
    """A study whose runtime is a git checkout holding the programs, the rubric and a small task list, with a
    frozen criterion pair and its own state directory."""
    runtime = tmp_path / "runtime"
    tasks = committed_runtime(runtime, [{"id": i, "set": s, "commit": "f" * 40, "tier": "T3", "form": "in-tree"}
                                        for i, s in (("t1", "drawn"), ("t2", "drawn"), ("r1", "reserve"),
                                                     ("r2", "smoke"))])
    monkeypatch.setattr(rules, "loaded_elsewhere", lambda runtime: [])  # the tests import this checkout's modules
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / layout.CHOSEN).write_text(json.dumps({"tasks": [{"id": "t1", "rung": "T3"},
                                                                            {"id": "t2", "rung": "T3"}]}))
    criterion = tmp_path / "judge-calibration.json"
    criterion.write_text(json.dumps({"judges": [H, S], "rubric": layout.RUBRIC}))
    study_ = layout.Study(runtime, tmp_path / "work", tmp_path / "pools", tmp_path / "results", tasks, criterion,
                          tmp_path / "state")
    write_frozen_criterion(study_)
    return study_


def ready(runner, smoke=True, chosen=True):
    """The ledger as the calibration needs it: a freeze and, unless told otherwise, a passed smoke and the probe
    readout's hash of the chosen tasks (t1 and t2)."""
    rules.record_freeze(runner)
    if smoke:
        spend.record(runner.ledger, "smoke", passed=True)
    if chosen:
        spend.record(runner.ledger, "probe_readout", answer={"chosen": "T3"},
                     chosen_sha256=sha256_file(runner.results / layout.CHOSEN))


def run_dir(runner, arm="direct", k=1, calls=0, **facts):
    """A candidate run's records directory with `calls` recorded calls and its study.json."""
    records = runner.work / "records" / arm / f"run-{k}"
    for n in range(1, calls + 1):
        (records / "calls" / str(n)).mkdir(parents=True)
        (records / "calls" / str(n) / "prompt.txt").write_text("p")
    records.mkdir(parents=True, exist_ok=True)
    (records / "record.json").write_text(json.dumps(facts.pop("record", {})))
    (records / "study.json").write_text(json.dumps({"tranche": "calibration", "task": "t1", "arm": arm,
                                                    "model": H, "effort": "medium", "max_calls": 1} | facts))
    return records


def test_candidates_without_authorization_refuse_before_preparing_anything(runner, monkeypatch):
    monkeypatch.delenv(AUTH, raising=False)
    with pytest.raises(SystemExit, match="provider spend refused"):
        study.candidates(runner, "calibration", "direct", ["t1"])
    assert not runner.work.exists()


def test_the_seed_evaluation_refuses_outright(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "seed_evaluation")
    with pytest.raises(SystemExit, match="not authorized"):
        study.candidates(runner, "seed_evaluation", "direct", ["t1"])


def test_judges_without_authorization_refuse(runner, monkeypatch):
    monkeypatch.delenv(AUTH, raising=False)
    with pytest.raises(SystemExit, match="provider spend refused"):
        study.judge(runner, "calibration", "first", ["t1"])


@pytest.mark.parametrize("tranche, arm, tasks, match", [
    ("calibration", "retry_until_check", ["t1"], "not retry_until_check"),
    ("calibration", "direct", ["r1"], "takes tasks among"),
    ("smoke", "direct", ["r1"], "takes tasks among"),  # the smoke runs on the last reserve task only
    ("redraw", "direct", ["t1"], "ladder probe only"),
])
def test_a_run_outside_the_tranches_plan_refuses(runner, monkeypatch, tranche, arm, tasks, match):
    monkeypatch.setenv(AUTH, tranche)
    with pytest.raises(SystemExit, match=match):
        study.candidates(runner, tranche, arm, tasks)


def test_planned_runs_already_started_are_not_launched_again(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    for k in range(4):
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, f"/w/{k}", task="t1", arm="direct", price=P)
    assert study.candidates(runner, "calibration", "direct", ["t1", "t1"]) == []


def test_the_ledger_lies_in_the_home_state_directory_whatever_the_results_path(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    ledgers = {study.study_of(study.parser().parse_args(["--results", str(tmp_path / name), "ledger"])).ledger
               for name in ("a", "b")}
    assert ledgers == {tmp_path / ".local" / "state" / "seed-set" / "spend-ledger.jsonl"}


def test_a_run_with_calls_but_no_ledger_row_refuses_every_start(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    run_dir(runner, calls=1, exit=0)  # the ledger that held it is gone, or belongs to another study
    with pytest.raises(SystemExit, match="has no row"):
        study.candidates(runner, "calibration", "direct", ["t2"])


def test_a_unit_with_more_calls_than_reserved_refuses(runner):
    records = run_dir(runner, calls=2, exit=0)
    spend.reserve(runner.ledger, "calibration", "candidate", H, 1, records, env("calibration"), price=P)
    with pytest.raises(SystemExit, match="2 calls made, 1 reserved"):
        rules.audit_ledger(runner)


def test_starts_beyond_the_planned_runs_of_a_task_and_arm_refuse_under_the_lock(ledger):
    won = []

    def take(k):
        try:
            spend.reserve(ledger, "calibration", "candidate", H, 1, f"/w/{k}", env("calibration"), limit=4,
                          task="t1", arm="direct", price=P)
            won.append(k)
        except SystemExit:
            pass
    threads = [threading.Thread(target=take, args=(k,)) for k in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(won) == 4


def test_no_start_before_the_freeze_is_recorded(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "smoke")
    with pytest.raises(SystemExit, match="no freeze"):
        study.candidates(runner, "smoke", "direct", ["r2"])


def test_no_start_once_the_frozen_criterion_changed(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "smoke")
    ready(runner)
    write_frozen_criterion(runner, plan="edited")  # still names the hashes; its own sha256 changed
    with pytest.raises(SystemExit, match="changed since the freeze"):
        study.candidates(runner, "smoke", "direct", ["r2"])


def test_no_calibration_without_a_passed_smoke(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner, smoke=False)
    spend.record(runner.ledger, "smoke", passed=False)
    with pytest.raises(SystemExit, match="no passed smoke"):
        study.candidates(runner, "calibration", "direct", ["t1"])


def test_no_calibration_before_the_probe_readout_chose_its_tasks(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner, chosen=False)
    with pytest.raises(SystemExit, match="no chosen calibration tasks"):
        study.candidates(runner, "calibration", "direct", ["t1"])


def test_no_calibration_once_the_chosen_list_was_edited(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    (runner.results / layout.CHOSEN).write_text(json.dumps({"tasks": [{"id": "t1", "rung": "T3"}]}))
    with pytest.raises(SystemExit, match="no chosen calibration tasks"):
        study.candidates(runner, "calibration", "direct", ["t1"])


def test_nothing_starts_after_a_stop(ledger):
    spend.record(ledger, "stop", reason="forbidden model in a run")
    with pytest.raises(SystemExit, match="stopped"):
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-1", env("smoke"), price=P)


RESET = 1_794_627_837  # the fixture's resetsAt


def resume(ledger, reset=RESET, five_hour=0.0, weekly=40.0, read_at=RESET + 60, now=RESET + 120):
    return spend.resume_after_limit(ledger, reset, five_hour, weekly, read_at, now=now)


def test_a_usage_limit_pause_closes_every_start(ledger):
    spend.record(ledger, "pause", unit="/w/run-1", reset=RESET)
    with pytest.raises(SystemExit, match="closed by a usage limit"):
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-2", env("smoke"), price=P)


def test_a_batch_is_refused_while_starts_are_closed(ledger):
    spend.record(ledger, "pause", unit="/w/run-1", reset=RESET)
    with pytest.raises(SystemExit, match="closed by a usage limit"):
        spend.check(ledger, "smoke", "candidate", H, 1, env("smoke"))


def test_resume_after_limit_reopens_starts_and_records_the_owners_reading(ledger):
    spend.record(ledger, "pause", unit="/w/run-1", reset=RESET)
    row = resume(ledger, five_hour=3.0, weekly=41.0)
    spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-2", env("smoke"), price=P)
    assert (row["event"], row["reset"], row["reading"]) == (
        "resume", RESET, {"five_hour_pct": 3.0, "weekly_pct": 41.0, "read_at": RESET + 60})


def test_resume_after_limit_refuses_before_the_named_reset(ledger):
    spend.record(ledger, "pause", unit="/w/run-1", reset=RESET)
    with pytest.raises(SystemExit, match="nothing reopens before the reset"):
        resume(ledger, read_at=RESET - 120, now=RESET - 60)


def test_resume_after_limit_refuses_a_reset_earlier_than_the_vendor_named(ledger):
    spend.record(ledger, "pause", unit="/w/run-1", reset=RESET)
    with pytest.raises(SystemExit, match="nothing reopens before the reset"):
        resume(ledger, reset=RESET - 3600, read_at=RESET - 60, now=RESET - 30)


def test_resume_after_limit_needs_a_reading_taken_after_the_reset(ledger):
    spend.record(ledger, "pause", unit="/w/run-1", reset=RESET)
    with pytest.raises(SystemExit, match="meter reading"):
        resume(ledger, read_at=RESET - 60)


@pytest.mark.parametrize("five_hour, weekly", [(-1.0, 40.0), (3.0, 101.0)])
def test_resume_after_limit_refuses_a_reading_that_is_not_a_percentage(ledger, five_hour, weekly):
    spend.record(ledger, "pause", unit="/w/run-1", reset=RESET)
    with pytest.raises(SystemExit, match="percent"):
        resume(ledger, five_hour=five_hour, weekly=weekly)


def test_resume_after_limit_from_the_command_line_takes_zoned_times(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    spend.record(spend.ledger_path(), "pause", unit="/w/run-1", reset=RESET)
    study.main(["resume-after-limit", "--reset", "2026-11-14T03:43:57Z", "--five-hour", "2", "--weekly", "35",
                "--read-at", "2026-11-14T03:50:00+00:00"])
    assert spend.latest(spend.rows(spend.ledger_path()), "resume")["reading"] == {
        "five_hour_pct": 2.0, "weekly_pct": 35.0, "read_at": RESET + 363}


def test_resume_after_limit_without_a_pause_refuses(ledger):
    with pytest.raises(SystemExit, match="nothing to resume"):
        resume(ledger)


def test_a_pause_after_a_resume_closes_starts_again(ledger):
    spend.record(ledger, "pause", unit="/w/run-1", reset=RESET)
    resume(ledger)
    spend.record(ledger, "pause", unit="/w/run-2", reset=RESET + 18000)
    with pytest.raises(SystemExit, match="closed by a usage limit"):
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-3", env("smoke"), price=P)


@pytest.mark.parametrize("price, most", [((100.0, 0.1), 40), ((3.0, 0.1), 30)])  # the call cap, the ceiling
def test_no_start_lands_between_a_pause_and_its_resume_under_sixty_concurrent_tries(ledger, price, most):
    """60 concurrent tries on the redraw cap (40 Haiku calls), one of them closing starts at a usage limit and one
    reopening them: no start row lies between the pause and the resume, and neither the call cap nor the priced
    ceiling is ever passed."""
    def take(k):
        try:
            if k == 20:
                spend.record(ledger, "pause", unit=f"/w/{k}", reset=RESET)
            elif k == 40:
                resume(ledger)
            else:
                spend.reserve(ledger, "redraw", "candidate", H, 1, f"/w/{k}", env("redraw"), price=price)
        except SystemExit:
            pass
    threads = [threading.Thread(target=take, args=(k,)) for k in range(60)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    rows = spend.rows(ledger)
    pause = next(r["seq"] for r in rows if r.get("event") == "pause")
    reopened = next((r["seq"] for r in rows if r.get("event") == "resume"), len(rows) + 1)
    starts = [r["seq"] for r in spend.starts(rows)]
    assert ([s for s in starts if pause < s < reopened], len(starts) <= most,
            sum(r["usd_reserved"] for r in spend.starts(rows)) <= price[0]) == ([], True, True)


CUT = {"call": "1", "reset": RESET, "text": "You've hit your session limit"}


def test_a_slot_cut_by_a_usage_limit_runs_again_once(runner):
    """Planned 4: two of the first four starts were cut, so two more starts are due; the cut re-run gives none."""
    cut = {"cut": CUT, "outcome": "failed"}
    facts = {f"/w/{k}": (cut if k in (1, 3, 5) else {}) for k in range(1, 6)}
    entries = [{"kind": "candidate", "tranche": "calibration", "task": "t1", "arm": "direct", "unit": unit}
               for unit in facts]
    assert study.cut_reruns(entries, facts, "calibration", "t1", "direct", 4) == 2


def test_a_cut_run_is_no_observation_and_never_scores_zero(runner):
    run_dir(runner, cut=CUT, outcome="failed", calls=1)
    assert study.load_records(runner, {"direct": H}, ["t1"]) == ([], [])


def test_cut_runs_do_not_count_toward_the_incident_stop(runner):
    for k in (1, 2):  # 2 of the 10 planned runs: as incidents they would stop the study
        run_dir(runner, k=k, cut=CUT, outcome="failed")
    assert rules.stop_reasons(runner) == []


def cut_run(runner, k=1, cut=None, stdout=(), stderr="", **facts):
    """A settled calibration run cut by a falsely recognised usage limit, with its pause open in the ledger."""
    records = run_dir(runner, k=k, calls=1, outcome="failed", failure={}, scan_hits=0, **facts,
                      cut={"call": "1", "reset": None, "text": "x", "raw": "r", "rule": units.REJECTED,
                           "flag": units.UNRECOGNISED} | (cut or {}))
    (records / "calls" / "1" / "stdout.txt").write_text("".join(json.dumps(e) + "\n" for e in stdout))
    (records / "calls" / "1" / "stderr.txt").write_text(stderr)
    (records / "study.json").write_text(json.dumps(json.loads((records / "study.json").read_text()) | {"calls": 1}))
    spend.record(runner.ledger, "pause", unit=str(records), **units.usage_limit(records) or {"rule": units.REJECTED})
    return records


def test_not_a_limit_reopens_starts_and_files_a_provider_error_as_an_incident(runner, monkeypatch):  # re-review n3
    records = cut_run(runner, stdout=[REJECTED, {**ERROR, "api_error_status": 403, "result": "API Error: 403"}])
    row = study.not_a_limit(runner, str(records), "a 403 beside a stale rejected event, not a limit")
    spend.reserve(runner.ledger, "smoke", "candidate", H, 1, "/w/run-2", env("smoke"), price=P)  # reopened
    facts = json.loads((records / "study.json").read_text())
    assert (row["event"], row["unit"], row["reason"], "cut" in facts, facts["incident"], facts["not_a_limit"]) == (
        "not_a_limit", str(records), "a 403 beside a stale rejected event, not a limit", False,
        "provider: call 1: API Error: 403", "a 403 beside a stale rejected event, not a limit")


def test_not_a_limit_leaves_a_failure_with_no_provider_error_a_natural_failure(runner):
    records = cut_run(runner, stdout=[REJECTED, {**ERROR, "result": "AssertionError: 2 != 3"}])
    study.not_a_limit(runner, str(records), "the task's own failure")
    assert study.load_records(runner, {"direct": H}, ["t1"])[0][0]["status"] == "failed"


def test_not_a_limit_restores_the_incident_the_cut_set_aside(runner):
    records = cut_run(runner, cut={"incident": "expected one orchestrator run, found 0"},
                      stdout=[REJECTED, {**ERROR, "result": "AssertionError"}])
    study.not_a_limit(runner, str(records), "no limit")
    assert json.loads((records / "study.json").read_text())["incident"] == "expected one orchestrator run, found 0"


def test_not_a_limit_runs_nothing_again(runner):
    records = cut_run(runner, stdout=[REJECTED, {**ERROR, "result": "AssertionError"}])
    entries = [{"kind": "candidate", "tranche": "calibration", "task": "t1", "arm": "direct", "unit": str(records)}]
    study.not_a_limit(runner, str(records), "no limit")
    assert study.slot_limits(runner, entries, "calibration", "direct", ["t1"]) == ({"t1": 4}, {"t1": 4})  # cut: 5


def test_not_a_limit_on_a_judge_keeps_its_pool_from_a_rebuild(runner):
    out = runner.pools / "t1" / "first"
    (out / "records" / "judges" / H).mkdir(parents=True)
    (out / "records" / f"study-{H}.json").write_text(json.dumps({"calls": 1, "cut": {"rule": units.REJECTED}}))
    spend.record(runner.ledger, "pause", unit=f"{out}#{H}", reset=None, rule=units.REJECTED)
    study.not_a_limit(runner, f"{out}#{H}", "no limit")
    assert (layout.cut_judges(out), spend.open_pauses(spend.rows(runner.ledger))) == ([], [])


@pytest.mark.parametrize("ledger_rows", ["none", "resumed", "above its worst case"])
def test_not_a_limit_refuses_without_an_open_usage_limit_pause_of_the_unit(runner, ledger_rows):
    records = run_dir(runner, calls=1, outcome="failed", cut=CUT)
    if ledger_rows == "resumed":
        spend.record(runner.ledger, "pause", unit=str(records), reset=RESET, rule=units.WORDING)
        resume(runner.ledger)
    elif ledger_rows == "above its worst case":
        spend.record(runner.ledger, "pause", unit=str(records), reset=None, reason="a unit settled above its worst case")
    with pytest.raises(SystemExit, match="no open usage-limit pause"):
        study.not_a_limit(runner, str(records), "no limit")
    assert "cut" in json.loads((records / "study.json").read_text())


def test_not_a_limit_refuses_an_unsettled_unit_and_a_missing_reason(runner):
    records = run_dir(runner, calls=1)
    spend.record(runner.ledger, "pause", unit=str(records), reset=None, rule=units.WORDING)
    with pytest.raises(SystemExit, match="not settled"):
        study.not_a_limit(runner, str(records), "no limit")
    with pytest.raises(SystemExit, match="reason"):
        study.not_a_limit(runner, str(records), " ")


def test_not_a_limit_on_an_unsettled_unit_names_the_way_out(runner):  # fix round 3, ruling 2
    records = run_dir(runner, calls=1)
    spend.record(runner.ledger, "pause", unit=str(records), reset=None, rule=units.WORDING)
    with pytest.raises(SystemExit) as refused:
        study.not_a_limit(runner, str(records), "no limit")
    assert all(part in str(refused.value) for part in ("`settle`", "a probe run", "`resume-after-limit`"))


def test_not_a_limit_from_the_command_line(runner, monkeypatch):
    monkeypatch.setattr(spend, "ledger_path", lambda: runner.ledger)
    records = cut_run(runner, stdout=[REJECTED, {**ERROR, "result": "AssertionError"}])
    study.main(["--runtime", str(runner.runtime), "--work", str(runner.work), "--pools", str(runner.pools),
                "--results", str(runner.results), "--task-list", str(runner.tasks_file), "--criterion",
                str(runner.criterion), "not-a-limit", str(records), "--reason", "read the raw result: a 403"])
    assert spend.latest(spend.rows(runner.ledger), "not_a_limit")["reason"] == "read the raw result: a 403"


def test_a_cut_unit_whose_session_audit_fails_is_an_incident_and_its_pause_stays(runner):  # re-review n4
    """Settle's session audit: a failed audit is an incident, cut or not, and the pause the cut wrote stays open."""
    import re
    import time
    records = recorded_call(run_dir(runner), "token-usage-limit-NonZeroAgentExitCodeError")
    (records / "calls" / "1" / "prompt.txt").write_text("p")
    home, tree = runner.work / "home", runner.work / "tree"
    tree.mkdir()
    store = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(tree))
    store.mkdir(parents=True)
    for name in ("a", "b"):  # two sessions for one recorded call
        (store / f"{name}.jsonl").write_text(json.dumps({"type": "assistant", "message": {"model": H}}) + "\n")
    (records / "record.json").write_text(json.dumps({"sandbox": {"home": str(home)}, "tree": str(tree),
                                                     "created_at": time.time(), "state_root": str(runner.work / "x")}))
    out = study.settle(runner, records, runner.work / "task", "f" * 40, 1, H, 1)
    assert ("cut" in out, out["incident"], [r["unit"] for r in spend.open_pauses(spend.rows(runner.ledger))]) == (
        False, "session audit: 2 sessions for 1 recorded calls", [str(records)])


def test_a_cut_probe_run_and_its_re_run_are_one_planned_unit_of_the_redraw(runner):  # re-review n4
    """planned_runs for the redraw counts (task, step) units: 21 probe units, one of them cut and run again, are 21."""
    for k in range(21):
        spend.reserve(runner.ledger, "redraw", "candidate", H, 1, f"/w/{k}", env("redraw"), price=P, task=f"t{k}",
                      arm="direct", step="first")
    spend.reserve(runner.ledger, "redraw", "candidate", H, 1, "/w/0-again", env("redraw"), price=P, task="t0",
                  arm="direct", step="first")
    assert rules.planned_runs(runner, "redraw") == 21


def test_runs_launch_two_at_a_time():
    lock, live, peak = threading.Lock(), [0], [0]

    def one(job):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        threading.Event().wait(0.2)
        with lock:
            live[0] -= 1
        return f"/w/{job}", {"calls": 1, "outcome": "completed"}
    study.run_jobs(list(range(6)), one)
    assert peak[0] == 2


def test_three_contaminated_tasks_stop_the_study(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    verdict = {"scan": {"verdict": {"verdict": "contaminated", "reason": "read the fix"}}}
    for k, task in enumerate(("t1", "t2", "r1"), 1):
        records = run_dir(runner, k=k, task=task, record=verdict)
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, records, task=task, arm="direct", price=P)
    with pytest.raises(SystemExit, match="stopped"):
        study.candidates(runner, "calibration", "direct", ["t2"])


def test_incidents_over_a_tenth_of_the_planned_runs_stop_the_study(runner, monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)  # 2 drawn tasks: 10 planned runs, so 2 incidents are over 10%
    for k in (1, 2):
        records = run_dir(runner, k=k, incident="provider: call 1: API Error: 429")
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, records, task="t1", arm="direct", price=P)
    with pytest.raises(SystemExit, match="stopped"):
        study.candidates(runner, "calibration", "direct", ["t2"])


def test_a_single_incident_of_ten_planned_runs_does_not_stop(runner):
    run_dir(runner, incident="provider: call 1: overloaded")
    assert rules.stop_reasons(runner) == []


@pytest.mark.parametrize("text, incident", [
    ("API Error: 429 rate_limit_error", True), ("Claude AI usage limit reached", True),
    ("Invalid API key · Please run /login", True), ("API Error: 529 overloaded_error", True),
    ("shim: call 2 refused by COMPARE_MAX_CALLS=1", True), ("AssertionError: expected 5, got 3", False), ("", False)])
def test_provider_errors_are_incidents_and_task_failures_are_not(tmp_path, text, incident):
    (tmp_path / "calls" / "1").mkdir(parents=True)
    (tmp_path / "calls" / "1" / "stderr.txt").write_text(text)
    assert (units.provider_incident(tmp_path) is not None) == incident


FIXTURES = ROOT / "experiments" / "long_horizon_tasks" / "fixtures"


def recorded_call(records, fixture):
    """A unit's records directory whose one call printed the recorded fixture's stream-json tail."""
    tail = json.loads((FIXTURES / f"{fixture}.json").read_text())["stream_tail"]
    (records / "calls" / "1").mkdir(parents=True)
    (records / "calls" / "1" / "stdout.txt").write_text("".join(json.dumps(event) + "\n" for event in tail))
    return records


LIMIT_FIXTURES = ["token-usage-limit-NonZeroAgentExitCodeError",  # both recordings of the vendor's answer
                  "twenty-tools-token-usage-limit-NonZeroAgentExitCodeError"]


@pytest.mark.parametrize("fixture", LIMIT_FIXTURES)
def test_a_usage_limit_answer_is_recognised_with_the_reset_it_names(tmp_path, fixture):
    named = [e["rate_limit_info"]["resetsAt"] for e in json.loads((FIXTURES / f"{fixture}.json").read_text())[
        "stream_tail"] if e.get("type") == "rate_limit_event"]
    limit = units.usage_limit(recorded_call(tmp_path, fixture))
    assert (limit["call"], limit["reset"]) == ("1", named[-1])


@pytest.mark.parametrize("fixture", LIMIT_FIXTURES)
def test_the_recorded_usage_limit_answer_carries_no_flag(tmp_path, fixture):
    assert "flag" not in units.usage_limit(recorded_call(tmp_path, fixture))


@pytest.mark.parametrize("fixture", ["twenty-tools-token-normal-end", "token-three-tools-normal-end",
                                     "stub-overloaded-UnknownApiError", "token-unauthorized-UnknownApiError"])
def test_a_normal_end_an_overload_or_an_expired_login_is_not_a_usage_limit(tmp_path, fixture):
    assert units.usage_limit(recorded_call(tmp_path, fixture)) is None


ERROR = {"type": "result", "subtype": "success", "is_error": True}


def call_printing(records, stdout=(), stderr=""):
    """A unit's records directory whose one call printed `stdout` (stream-json events or plain lines) and `stderr`."""
    call = records / "calls" / "1"
    call.mkdir(parents=True)
    (call / "prompt.txt").write_text("p")
    (call / "stdout.txt").write_text("".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in stdout))
    (call / "stderr.txt").write_text(stderr)
    return records


@pytest.mark.parametrize("stdout, stderr", [  # review3 X2: recognition fails closed
    ([{**ERROR, "api_error_status": "429", "api_error": "usage_limit_reached", "result": "x"}], ""),
    ([{**ERROR, "api_error_status": 429, "result": "API Error: Request rejected (429)"}], ""),
    ([{**ERROR, "result": "Claude AI usage limit reached|1794627837"}], ""),  # an older CLI's wording
    ([{**ERROR, "result": "You've hit your weekly limit"}], ""),
    ([{"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": RESET}},
      {**ERROR, "result": "something else"}], ""),
    ([], "Error: You've hit your session limit · resets 3:43am (UTC)\n"),
    ([{**ERROR, "api_error_status": "429", "api_error": "x", "result": "x"}], ""),  # re-review N1: still cut
    ([{**ERROR, "result": "You've hit your session limit · resets 3:43am (UTC)"}], ""),
    ([], "Error: Claude AI usage limit reached|1794627837\n"),  # a CLI crash: no result event at all
    ([{"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": RESET}},
      {**ERROR, "api_error_status": 403, "result": "You've hit your limit"}], ""),
    ([{"type": "system", "subtype": "init"}], "Error: You've hit your weekly limit\n"),  # no result: a failed call
    ([{**ERROR, "result": "x"}], "You've hit your session limit\n"),  # an error naming no status, the wording on stderr
])
def test_a_possible_usage_limit_in_another_shape_is_cut_flagged_unrecognised(tmp_path, stdout, stderr):
    assert units.usage_limit(call_printing(tmp_path, stdout, stderr))["flag"] == units.UNRECOGNISED


@pytest.mark.parametrize("fixture", ["stub-rate-limit-ApiRateLimitError", "simple-mode-stub-usage-limit-headers-key-mode-UnknownApiError"])
def test_a_recorded_429_answer_is_a_possible_usage_limit(tmp_path, fixture):
    assert units.usage_limit(recorded_call(tmp_path, fixture))["flag"] == units.UNRECOGNISED


def test_paid_extra_usage_on_a_call_that_ended_normally_is_a_usage_limit_with_its_named_cause(tmp_path):
    """Final scoped check M1: the CLI's rate_limit_event shows overage in use, the call ends normally."""
    limit = units.usage_limit(recorded_call(tmp_path, "token-paid-extra-usage-normal-end"))
    assert (limit["rule"], "flag" in limit) == (units.PAID, False)


@pytest.mark.parametrize("info", [{"status": "allowed", "isUsingOverage": True},
                                  {"status": "allowed", "overageInUse": "true"},
                                  {"status": "rejected", "overageStatus": "allowed"},
                                  {"status": "rejected", "overageStatus": "allowed_warning", "resetsAt": RESET}])
def test_any_sign_of_overage_in_use_is_paid_extra_usage(tmp_path, info):  # final scoped check M1
    stdout = [{"type": "rate_limit_event", "rate_limit_info": info}, OK_END]
    assert units.usage_limit(call_printing(tmp_path, stdout))["rule"] == units.PAID


def test_paid_extra_usage_closes_every_start_naming_its_cause_until_resume_after_limit(runner):  # M1
    records = recorded_call(run_dir(runner), "token-paid-extra-usage-normal-end")
    study.pause_on_limit(runner, records, str(records))
    with pytest.raises(SystemExit) as refused:
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, "/w/next", env("calibration"), price=P)
    assert all(part in str(refused.value) for part in (units.PAID, "resume-after-limit"))


QUOTED = json.dumps({**ERROR, "api_error": "usage_limit_reached", "api_error_status": 429,
                     "result": "You've hit your session limit"})


@pytest.mark.parametrize("stdout", [
    [{"type": "user", "message": {"content": [{"type": "tool_result", "content": QUOTED}]}},
     {"type": "result", "subtype": "success", "is_error": False, "result": "done"}],  # a tool printed the shape
    [{"type": "assistant", "message": {"model": H, "content": [{"type": "text", "text": "You've hit your usage limit"}]}},
     {"type": "result", "subtype": "success", "is_error": False, "result": "I hit a usage limit reached 429"}],
    [{**ERROR, "api_error_status": 401, "result": "Failed to authenticate: usage limit of this token"}],  # another
])
def test_a_model_or_tool_quoting_the_wording_or_another_named_error_is_no_usage_limit(tmp_path, stdout):
    assert units.usage_limit(call_printing(tmp_path, stdout)) is None


OK_END = {"type": "result", "subtype": "success", "is_error": False, "result": "done"}
CUT_TOOL_LINE = '{"type": "user", "message": {"content": [{"type": "tool_result", "content": "docs: the usage limit of'
CUT_TEXT_LINE = '{"type":"assistant","message":{"content":[{"type":"text","text":"I will check the weekly limit handling'


@pytest.mark.parametrize("stdout, stderr", [  # re-review N1: the wording rule reads a failed call's own errors only
    ([OK_END], "Approaching usage limit · resets 5pm\n"),  # a warning on stderr beside a call that succeeded
    ([{"type": "system", "subtype": "init"}, CUT_TOOL_LINE], ""),  # a tool result cut mid-write, no result event
    ([CUT_TEXT_LINE], ""),  # the model's text cut mid-write (a timeout's SIGKILL), no result event
    ([{**ERROR, "api_error_status": 403, "result": "You've hit your limit"}], ""),  # another status, no rejected event
    ([{**ERROR, "api_error_status": 529, "result": "API Error: 529 overloaded; retrying would pass your usage limit"}],
     ""),
    ([{**ERROR, "api_error_status": 500, "result": "x"}], "API Error (500) · Retrying… you may hit your rate limit\n"),
])
def test_a_limit_wording_outside_a_failed_calls_own_errors_is_no_usage_limit(tmp_path, stdout, stderr):
    assert units.usage_limit(call_printing(tmp_path, stdout, stderr)) is None


@pytest.mark.parametrize("stderr", ["Approaching usage limit · resets 5pm\n", "API Error (500) · Retrying in 2s\n"])
def test_a_warning_beside_a_call_that_succeeded_is_no_provider_error(tmp_path, stderr):  # re-review N1
    assert units.provider_incident(call_printing(tmp_path, [OK_END], stderr)) is None


def test_a_tool_line_cut_mid_write_is_no_provider_error(tmp_path):  # re-review N1: tool text is never read
    line = '{"type": "user", "message": {"content": [{"type": "tool_result", "content": "401 oauth token expired'
    assert units.provider_incident(call_printing(tmp_path, [{"type": "system", "subtype": "init"}, line])) is None


def test_a_pause_of_an_unrecognised_shape_tells_the_operator_to_read_the_raw_result(ledger, tmp_path):
    limit = units.usage_limit(call_printing(tmp_path, [{**ERROR, "result": "Claude AI usage limit reached|1"}]))
    spend.record(ledger, "pause", unit=str(tmp_path), **limit)
    with pytest.raises(SystemExit) as refused:
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-2", env("smoke"), price=P)
    assert all(part in str(refused.value) for part in (units.UNRECOGNISED, limit["raw"], "read the raw result",
                                                       "resume-after-limit"))


REJECTED = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": RESET}}


@pytest.mark.parametrize("stdout, stderr, rule, text", [  # re-review n3: which rule fired, on which line
    ([REJECTED, {**ERROR, "api_error": "usage_limit_reached", "api_error_status": 429, "result": "hit"}], "",
     units.RECORDED, "hit"),
    ([{**ERROR, "api_error_status": "429", "result": "API Error: 429"}], "", units.STATUS_429, "API Error: 429"),
    ([REJECTED, {**ERROR, "api_error_status": 403, "result": "forbidden"}], "", units.REJECTED, "forbidden"),
    ([{**ERROR, "result": "x"}], "warn\nYou've hit your session limit\n", units.WORDING,
     "You've hit your session limit"),
])
def test_a_usage_limit_names_the_rule_that_fired_and_the_line_it_read(tmp_path, stdout, stderr, rule, text):
    limit = units.usage_limit(call_printing(tmp_path, stdout, stderr))
    assert (limit["rule"], limit["text"]) == (rule, text)


def test_the_refusal_names_the_rule_the_line_and_the_way_to_record_no_limit(ledger, tmp_path):  # re-review n3
    limit = units.usage_limit(call_printing(tmp_path, [{**ERROR, "result": "x"}], "You've hit your weekly limit\n"))
    spend.record(ledger, "pause", unit=str(tmp_path), **limit)
    with pytest.raises(SystemExit) as refused:
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-2", env("smoke"), price=P)
    assert all(part in str(refused.value) for part in (units.WORDING, "You've hit your weekly limit", "not-a-limit"))


def test_the_refusal_says_what_to_do_for_a_unit_a_killed_runner_left_unsettled(ledger, tmp_path):  # fix round 3
    limit = units.usage_limit(call_printing(tmp_path, [{**ERROR, "result": "x"}], "You've hit your weekly limit\n"))
    spend.record(ledger, "pause", unit=str(tmp_path), **limit)
    with pytest.raises(SystemExit) as refused:
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/run-2", env("smoke"), price=P)
    assert all(part in str(refused.value) for part in ("`settle` it first", "a probe run", "`resume-after-limit`"))


@pytest.mark.parametrize("stdout, stderr", [([{**ERROR, "result": "Claude AI usage limit reached|1794627837"}], ""),
                                            ([], "Error: Claude AI usage limit reached|1794627837\n")])
def test_the_older_wordings_reset_is_read(tmp_path, stdout, stderr):  # re-review n3
    assert units.usage_limit(call_printing(tmp_path, stdout, stderr))["reset"] == 1794627837


def test_the_session_limit_wording_is_a_provider_error(tmp_path):
    assert units.provider_incident(call_printing(tmp_path, stderr="You've hit your session limit\n"))


TABLE = json.loads((ROOT / "orchestrator" / "providers" / "price_table.json").read_text())


def priced_unit(records, *results):
    """A unit's records directory with one recorded call per result event (None: a call that printed nothing)."""
    for n, result in enumerate(results, 1):
        call = records / "calls" / str(n)
        call.mkdir(parents=True)
        (call / "prompt.txt").write_text("p")
        (call / "stdout.txt").write_text("" if result is None else json.dumps({"type": "result", **result}) + "\n")
    return records


def metered(model, cost=REPORTED_USD, **usage):
    return {"total_cost_usd": cost, "modelUsage": {model: USAGE | usage}}


def test_the_ceiling_refuses_a_start_whose_worst_case_would_pass_it_and_writes_nothing(ledger):
    for k in range(2):
        spend.reserve(ledger, "smoke", "candidate", H, 1, f"/w/{k}", env("smoke"), price=(1.0, 0.4))
    before = ledger.read_bytes()
    with pytest.raises(SystemExit, match="priced ceiling"):
        spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/2", env("smoke"), price=(1.0, 0.4))
    assert ledger.read_bytes() == before


def test_a_settled_unit_counts_at_its_metered_price_not_at_its_worst_case(ledger):
    for k in range(2):
        spend.reserve(ledger, "smoke", "candidate", H, 1, f"/w/{k}", env("smoke"), price=(1.0, 0.4))
    spend.record(ledger, "settle", unit="/w/0", usd=0.05, missing=[])
    spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/2", env("smoke"), price=(1.0, 0.4))
    assert spend.priced(ledger)["smoke"] == {"committed_usd": 0.85, "settled_usd": 0.05, "open_usd": 0.8,
                                             "missing_usage": [], "over_reserved": []}


def test_the_ceiling_is_per_tranche_over_candidates_and_judges_of_both_models(ledger):
    spend.reserve(ledger, "smoke", "candidate", H, 1, "/w/0", env("smoke"), price=(1.0, 0.5))
    spend.reserve(ledger, "smoke", "judge", S, 1, "/p#s", env("smoke"), price=(1.0, 0.5))
    with pytest.raises(SystemExit, match="priced ceiling"):
        spend.reserve(ledger, "smoke", "judge", H, 1, "/p#h", env("smoke"), price=(1.0, 0.5))
    assert spend.reserve(ledger, "calibration", "judge", H, 1, "/q#h", env("calibration"), price=(1.0, 0.5))


def test_metered_calls_are_priced_by_the_frozen_table_to_the_cent(tmp_path):
    records = priced_unit(tmp_path, metered(H), metered(H), metered(S))
    # Haiku: 1000 x 0.1 + 2000 x 0.5 + 50000 x 0.01 + 10000 x 0.2 per million; Sonnet: x 2, 10, 0.1 and 4
    assert round(units.priced(records, TABLE, 0.5)["usd"], 2) == round(2 * 0.0036 + 0.067, 2) == 0.07


def test_a_reported_cost_above_the_tables_price_is_the_calls_figure(tmp_path):
    assert units.priced(priced_unit(tmp_path, metered(H, cost=0.25)), TABLE, 0.5)["usd"] == 0.25


@pytest.mark.parametrize("result", [None, {"result": "no usage"}, {"modelUsage": {"claude-unknown-1": USAGE}}])
def test_a_call_with_missing_usage_counts_at_the_worst_case_and_is_flagged(tmp_path, result):
    priced = units.priced(priced_unit(tmp_path, metered(H), result), TABLE, 0.5)
    assert (round(priced["usd"], 4), priced["missing"]) == (0.5036, ["2"])


def test_a_call_refused_by_the_call_cap_costs_nothing(tmp_path):
    records = priced_unit(tmp_path, metered(H))
    (records / "calls" / "2").mkdir()  # the shim refused it: no prompt reached a provider
    assert units.priced(records, TABLE, 0.5) == {"usd": 0.0036, "missing": [], "calls": {"1": 0.0036}}  # 6 places


def test_the_runtime_cap_ends_the_run_command_once(tmp_path):
    script = tmp_path / "score-h.sh"
    script.write_text("cd /j && env A=1 python -P -m orchestrator run score.orc --state-dir /j/state\n")
    for usd in (0.5, 0.75):  # a refused start, then the start
        units.cap_command(script, usd)
    assert script.read_text().split()[-4:] == ["--state-dir", "/j/state", "--max-cost-usd", "0.75"]


def spend_terms(runner, **change):
    write_frozen_criterion(runner, spend={**SPEND_TERMS, **change})


@pytest.mark.parametrize("change", [{"ceiling_usd": {"smoke": 1.0}}, {"ceiling_usd": {"calibration": 0}},
                                    {"per_call_usd": {H: 0.5}}, {"cli": None}])
def test_a_start_without_the_criterions_priced_ceiling_worst_case_or_cli_pin_refuses(runner, change):
    spend_terms(runner, **change)
    with pytest.raises(SystemExit, match="criterion.json"):
        layout.spend_terms(runner, "calibration", S)


def test_the_criterions_spend_terms_give_the_tranches_ceiling_and_the_models_worst_case(runner):
    spend_terms(runner)
    assert layout.spend_terms(runner, "calibration", S)[:2] == (SPEND_TERMS["ceiling_usd"]["calibration"],
                                                                 SPEND_TERMS["per_call_usd"][S])


def test_the_freeze_binds_the_price_tables_hash(runner):
    table = runner.runtime / rules.PRICE_TABLE
    table.write_text(table.read_text().replace('"input": 0.1,', '"input": 0.09,', 1))
    commit_runtime(runner, "a cheaper Haiku")
    with pytest.raises(SystemExit, match="price_table.json"):
        rules.record_freeze(runner)


def stand_in_cli(tmp_path, version):
    cli = tmp_path / "bin" / "claude"
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_text(f"#!/bin/sh\n[ \"$1\" = --version ] && echo '{version}'\n")
    cli.chmod(0o755)
    (tmp_path / "sandbox.json").write_text(json.dumps({"claude": str(cli)}))
    return cli, tmp_path / "sandbox.json"


def test_the_pinned_cli_passes_and_is_returned_for_the_start_row(tmp_path):
    cli, declaration = stand_in_cli(tmp_path, "2.1.311 (Claude Code)")
    assert rules.check_cli(declaration, {"path": str(cli), "version": "2.1.311 (Claude Code)"}) == {
        "path": str(cli), "version": "2.1.311 (Claude Code)"}


@pytest.mark.parametrize("pin", [{"version": "2.1.312 (Claude Code)"}, {"path": "/usr/local/bin/claude"}])
def test_a_cli_other_than_the_pinned_path_or_version_refuses_the_start(tmp_path, pin):
    cli, declaration = stand_in_cli(tmp_path, "2.1.311 (Claude Code)")
    with pytest.raises(SystemExit, match="pinned"):
        rules.check_cli(declaration, {"path": str(cli), "version": "2.1.311 (Claude Code)", **pin})


def test_a_refused_call_directory_is_not_a_physical_call(tmp_path):
    for n, prompt in ((1, True), (2, False)):
        (tmp_path / "calls" / str(n)).mkdir(parents=True)
        if prompt:
            (tmp_path / "calls" / str(n) / "prompt.txt").write_text("p")
    assert units.physical_calls(tmp_path) == 1


def session(home, directory, model, name="s1.jsonl"):
    slug = "".join(c if c.isalnum() else "-" for c in str(directory))
    path = Path(home) / ".claude" / "projects" / slug / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "assistant", "sessionId": "x", "message": {"model": model}}) + "\n")
    return path


def test_the_session_audit_accepts_one_session_per_call_in_the_trees_store(tmp_path):
    session(tmp_path / "home", tmp_path / "tree" / "cand-1", H)
    assert units.audit_sessions(tmp_path / "home", tmp_path / "tree", 1, H)[:2] == (None, None)


def test_a_session_outside_the_trees_store_fails_the_unit(tmp_path):
    session(tmp_path / "home", tmp_path / "tree" / "cand-1", H)
    session(tmp_path / "home", "/tmp", H)  # the real CLI started by absolute path from /tmp
    reason, policy, _ = units.audit_sessions(tmp_path / "home", tmp_path / "tree", 1, H)
    assert ("outside the unit tree" in reason, policy) == (True, None)


def test_more_sessions_than_recorded_calls_fail_the_unit(tmp_path):
    for name in ("s1.jsonl", "s2.jsonl"):
        session(tmp_path / "home", tmp_path / "tree" / "cand-1", H, name)
    assert "2 sessions for 1 recorded calls" in units.audit_sessions(tmp_path / "home", tmp_path / "tree", 1, H)[0]


def test_a_session_answered_by_another_model_anywhere_in_the_home_is_a_policy_hit(tmp_path):
    session(tmp_path / "home", "/elsewhere", "claude-fable-5-1")
    assert units.audit_sessions(tmp_path / "home", tmp_path / "tree", 1, H)[1] is not None


def test_a_disabled_resume_script_refuses_and_names_why(tmp_path):
    script = tmp_path / "resume.sh"
    script.write_text("echo resumed\n")
    units.disable_resume(script)
    done = subprocess.run(["bash", str(script), "run-1"], capture_output=True, text=True)
    assert (done.returncode, "never resumes" in done.stderr, "resumed" in done.stdout) == (64, True, False)


def test_a_guarded_host_command_sees_only_the_stubs_an_empty_home_and_no_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "secret")
    probe = ("import os, shutil, subprocess; print(sorted(os.listdir(os.environ['HOME'])), "
             "'secret' in os.environ.values(), shutil.which('claude').endswith('no_provider/claude')); "
             "subprocess.run(['claude', '-p', '--model', 'claude-fable-5-1'])")
    done, attempts = host.guarded([sys.executable, "-c", probe])
    assert (done.stdout.split(), [line.split(" ", 1)[1] for line in attempts]) == (
        ["[]", "False", "True"], ["claude -p --model claude-fable-5-1"])


def test_a_provider_attempt_in_the_hidden_tests_refuses_the_summary(tmp_path, monkeypatch):
    fake = tmp_path / "experiments" / "compare"
    fake.mkdir(parents=True)
    (tmp_path / "experiments" / "__init__.py").write_text("")
    (fake / "__init__.py").write_text("")
    (fake / "summarize.py").write_text("import subprocess\nsubprocess.run(['claude', '-p'])\n")
    monkeypatch.setattr(host, "ROOT", tmp_path)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    with pytest.raises(SystemExit, match="PROVIDER ATTEMPT"):
        host.summarize(tmp_path / "pool", tmp_path / "criterion.json")


@pytest.mark.parametrize("change", [{"model": "claude-fable-5-1"}, {"model": "claude-opus-5-5"},
                                    {"effort": "high"}, {"max_calls": 4}])
def test_arms_binding_another_model_effort_or_call_count_refuse(runner, change):
    path = runner.programs / "arms.json"
    arms = json.loads(path.read_text())
    arms["direct"] |= change
    path.write_text(json.dumps(arms))
    with pytest.raises(SystemExit):
        layout.load_arms(runner)


@pytest.mark.parametrize("change", [{"purpose": "calibration"}, {"calibration": {"rule": "control-means-v1"}},
                                    {"judges": [H]}, {"rubric": {**layout.RUBRIC, "workflow": "score.orc"}}])
def test_a_criterion_that_would_skip_hidden_tests_or_drop_a_judge_refuses(runner, change):
    runner.criterion.write_text(json.dumps({"judges": [H, S], "rubric": layout.RUBRIC} | change))
    with pytest.raises(SystemExit, match="judge-calibration criterion"):
        layout.load_criterion(runner)


def test_a_run_refuses_to_start_below_the_free_disk_floor(runner):
    full = layout.Study(*[getattr(runner, f) for f in ("runtime", "work", "pools", "results", "tasks_file",
                                                        "criterion", "state")], min_free=10**18)
    with pytest.raises(SystemExit, match="GB free"):
        rules.require_free(full, full.work)
    assert "GB free" in spend.latest(spend.rows(full.ledger), "stop")["reason"]  # review2 minor 5: a recorded stop


def test_the_disk_floor_covers_root_and_the_host_checks_temporary_files(runner):
    assert {Path("/"), Path(tempfile.gettempdir())} <= set(rules.written_filesystems(runner, runner.work))


def test_a_third_live_pool_refuses(runner):
    for task in ("t1", "t2"):
        (runner.pools / task / "first" / "clones").mkdir(parents=True)
    with pytest.raises(SystemExit, match="two pools still hold clones"):
        study.build_pools(runner, "calibration", "retest", ["t1"])


def test_a_retest_takes_only_the_tranches_first_tasks(runner):
    with pytest.raises(SystemExit, match="takes tasks among"):
        study.build_pools(runner, "smoke", "retest", ["r2"])


def test_the_command_line_refuses_an_unauthorized_launch_before_preparing_anything(runner, monkeypatch, tmp_path):
    monkeypatch.delenv(AUTH, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    args = ["--runtime", str(runner.runtime), "--work", str(runner.work), "--pools", str(runner.pools),
            "--results", str(runner.results), "--task-list", str(runner.tasks_file), "--criterion", str(runner.criterion)]
    with pytest.raises(SystemExit, match="provider spend refused"):
        study.main([*args, "candidates", "--tranche", "calibration", "--arm", "direct", "t1", "t2"])
    assert not runner.work.exists()


@pytest.mark.parametrize("step", ["pool", "judge"])
def test_the_redraw_tranche_never_pools_or_judges(runner, monkeypatch, step):  # review2 M4
    monkeypatch.setenv(AUTH, "redraw")
    ready(runner)
    pool_dir_of(runner, "t1")
    with pytest.raises(SystemExit, match="ladder probe only"):
        (study.build_pools if step == "pool" else study.judge)(runner, "redraw", "first", ["t1"])
    assert not [row for row in spend.rows(runner.ledger) if row["kind"] == "judge"]


def pool_dir_of(runner, task, scan=None):
    """A built pool's records as the judge reads them; `scan` is the identity scan's hits, None for no scan."""
    records = runner.pools / task / "first" / "records"
    (records / "judges").mkdir(parents=True)
    (records / "mapping.json").write_text(json.dumps({"batches": [[1]], "clones": {}, "judges": {}}))
    if scan is not None:
        (records / "identity-scan.json").write_text(json.dumps({"hits": scan}))
    return records


@pytest.mark.parametrize("scan", [None, ["direct.orc in clone-1"]])
def test_a_judge_refuses_a_pool_without_a_clean_identity_scan_before_any_launch(runner, monkeypatch, scan):  # M5
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    pool_dir_of(runner, "t1", scan)
    monkeypatch.setattr(study, "launch", lambda *a, **k: pytest.fail("a judge was launched"))
    with pytest.raises(SystemExit, match="identity scan"):
        study.judge(runner, "calibration", "first", ["t1"])
    assert not [row for row in spend.rows(runner.ledger) if row["kind"] == "judge"]


def test_a_pool_that_ended_as_an_incident_is_never_built_again(runner):
    (runner.results / "pools" / "t1-first").mkdir(parents=True)
    (runner.results / "pools" / "t1-first" / "incident.json").write_text("{}")
    with pytest.raises(SystemExit, match="a pool is built once"):
        study.build_pools(runner, "calibration", "first", ["t1"])


LOADED_ELSEWHERE = rules.loaded_elsewhere


def commit_runtime(runner, message="change"):
    subprocess.run(["git", "-C", str(runner.runtime), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(runner.runtime), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
                    message], check=True)


def test_the_freeze_refuses_study_modules_loaded_from_outside_the_runtime(runner, monkeypatch):  # review2 M6
    monkeypatch.setattr(rules, "loaded_elsewhere", LOADED_ELSEWHERE)  # this test process imports the checkout
    with pytest.raises(SystemExit, match="loaded from outside the runtime"):
        rules.record_freeze(runner)


def test_modules_loaded_from_the_runtime_itself_pass_the_check():
    assert LOADED_ELSEWHERE(ROOT.resolve()) == []


def test_the_freeze_refuses_a_task_list_outside_the_runtime(runner, tmp_path):
    outside = tmp_path / "tasks.jsonl"
    outside.write_bytes(runner.tasks_file.read_bytes())
    moved = layout.Study(runner.runtime, runner.work, runner.pools, runner.results, outside, runner.criterion,
                         runner.state)
    with pytest.raises(SystemExit, match="outside the runtime"):
        rules.record_freeze(moved)


def test_the_freeze_refuses_without_the_frozen_criterion(runner):  # pins frozen_identity before its split
    runner.frozen.unlink()
    with pytest.raises(SystemExit, match="is missing: freeze the criterion first"):
        rules.record_freeze(runner)


def test_a_start_refuses_an_untracked_file_in_a_packages_seed(runner):
    ready(runner)
    seed = layout.task_dir(runner, "t1") / "seed"
    seed.mkdir(parents=True)
    (seed / "extra.py").write_text("# seeded into every clone\n")
    with pytest.raises(SystemExit, match="untracked files"):
        rules.require_order(runner, "calibration")


def test_a_start_refuses_a_package_changed_and_committed_after_the_freeze(runner):
    ready(runner)
    (layout.task_dir(runner, "t1")).mkdir(parents=True)
    (layout.task_dir(runner, "t1") / "task.txt").write_text("a new statement\n")
    commit_runtime(runner)
    with pytest.raises(SystemExit, match="changed since the freeze"):
        rules.require_order(runner, "calibration")


@pytest.mark.parametrize("named", [{}, "stale program"])
def test_the_freeze_refuses_a_criterion_that_does_not_name_the_plans_hashes(runner, named):
    if named == "stale program":
        (runner.programs / "direct.orc").write_text(";; edited after criterion.json was written\n")
        commit_runtime(runner)
    else:
        runner.frozen.write_text(json.dumps({"sha256": named}))
    with pytest.raises(SystemExit, match="does not name the current sha256"):
        rules.record_freeze(runner)


def test_a_second_freeze_after_a_start_needs_a_reason(runner, monkeypatch):
    ready(runner)
    spend.reserve(runner.ledger, "smoke", "candidate", H, 1, "/w/run-1", env("smoke"), task="r2", price=P)
    with pytest.raises(SystemExit, match="needs --reason"):
        rules.record_freeze(runner)
    assert rules.record_freeze(runner, reason="dev_check.py fix")["reason"] == "dev_check.py fix"


def test_criterion_files_and_results_written_into_the_runtime_are_not_untracked_code(runner):
    seed_set = runner.runtime / "experiments" / "seed_set"
    moved = layout.Study(runner.runtime, runner.work, runner.pools, seed_set / "results", runner.tasks_file,
                         seed_set / "judge-calibration.json", runner.state)
    moved.criterion.write_bytes(runner.criterion.read_bytes())
    (moved.results / "pools").mkdir(parents=True)
    (moved.results / "readout.md").write_text("x\n")
    write_frozen_criterion(moved)  # Step 1f: criterion.json beside judge-calibration.json, after the commit
    assert rules.record_freeze(moved)["event"] == "freeze"


def test_a_launch_gets_neither_the_spend_switch_nor_the_real_home(tmp_path, monkeypatch):  # review2 minor 2
    monkeypatch.setenv(AUTH, "calibration")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "real" / ".claude"))
    env = study.launch_env(H, 1, home=tmp_path / "host-home")
    assert (AUTH in env, env["HOME"], "CLAUDE_CONFIG_DIR" in env, list((tmp_path / "host-home").iterdir())) == (
        False, str(tmp_path / "host-home"), False, [])


def test_the_prepare_environment_keeps_home_for_the_credential_copy_but_not_the_switch(monkeypatch):
    monkeypatch.setenv(AUTH, "calibration")
    env = study.launch_env(H, 1)
    assert (AUTH in env, env["HOME"]) == (False, str(Path.home()))


def test_copied_credentials_are_removed_from_a_private_home(tmp_path):  # review2 minor 7
    home = tmp_path / "home"
    for path in (home / ".claude" / ".credentials.json", home / ".codex" / "auth.json"):
        path.parent.mkdir(parents=True)
        path.write_text("{}")
    (home / ".claude" / "projects").mkdir()
    units.forget_credentials(home)
    assert sorted(str(p.relative_to(home)) for p in home.rglob("*")) == [".claude", ".claude/projects", ".codex"]


@pytest.mark.parametrize("line, incident", [  # review2 minor 6: the agent's own tool output is not the provider's
    ({"type": "user", "message": {"content": [{"type": "tool_result", "content": "E   401 Unauthorized: bad oauth"}]}},
     False),
    ({"type": "result", "is_error": False, "result": "fixed the quota check"}, False),
    ({"type": "result", "is_error": True, "result": "API Error: 529 overloaded_error"}, True)])
def test_only_the_providers_own_error_in_stream_json_stdout_is_an_incident(tmp_path, line, incident):
    (tmp_path / "calls" / "1").mkdir(parents=True)
    (tmp_path / "calls" / "1" / "stdout.txt").write_text(json.dumps(line) + "\n")
    assert (units.provider_incident(tmp_path) is not None) == incident


@pytest.mark.parametrize("state", ["missing", "unstable", "stale"])
def test_the_freeze_refuses_a_package_without_stable_anchors(runner, state):  # r2: the one usable (smoke) package
    stability = runner.tasks_file.parent / "anchor_stability.json"
    if state == "missing":
        stability.unlink()
    elif state == "unstable":
        stable_anchors(runner.tasks_file, unstable={"r2"})
    else:
        (layout.task_dir(runner, "r2")).mkdir(parents=True)
        (layout.task_dir(runner, "r2") / "task.txt").write_text("changed after the check\n")
    commit_runtime(runner)
    with pytest.raises(SystemExit, match="no stable anchors"):
        rules.record_freeze(runner)


def smoke_runs(runner, settled=True):
    """The smoke's five runs, reserved, each settled as completed with no scan hit unless `settled` is False for
    `direct`."""
    for k, arm in enumerate(layout.PLANNED["smoke"], 1):
        facts = {"tranche": "smoke", "task": "r2", "outcome": "completed", "scan_hits": 0}
        if arm == "direct" and not settled:
            facts = {"tranche": "smoke", "task": "r2"}
        records = run_dir(runner, arm=arm, k=k, record={"sandbox": {"home": str(runner.work / "home")}}, **facts)
        if "outcome" in facts:  # settled: its calls counted
            (records / "study.json").write_text(json.dumps(json.loads((records / "study.json").read_text()) | {
                "calls": 1}))
        spend.reserve(runner.ledger, "smoke", "candidate", H, 1, records, env("smoke"), task="r2", arm=arm, price=P)


@pytest.mark.parametrize("settled", [True, False])
def test_the_smoke_fails_while_a_reserved_unit_is_unsettled(runner, settled):  # review3 X1: unobserved
    smoke_runs(runner, settled)
    assert rules.smoke_check(runner)["checks"]["every_reserved_unit_settled"] is settled


def test_the_runtime_counts_haiku_calls_at_five_times_and_sonnet_calls_at_once_the_ordinary_rate(runner):
    assert (rules.tier_ratio(runner, H), rules.tier_ratio(runner, S)) == (5, 1)  # review3 X3


@pytest.mark.parametrize("change, match", [
    ({"largest_call_usd": {H: 0.06, S: 0.1}}, "per-call worst case"),  # 0.25 < 5 x 0.06
    ({"largest_call_usd": {H: 0.01, S: 1.5}}, "per-call worst case"),  # 1.0 < 1 x 1.5
    ({"largest_call_usd": {H: 0.01}}, "largest ordinary-rate call"),
    ({"ceiling_usd": {"smoke": 1.4, "redraw": 40.0, "calibration": 100.0}}, "ceiling"),  # 2 x 3 x 0.25 = 1.5
    ({"ceiling_usd": {"smoke": 20.0, "redraw": 0.4, "calibration": 100.0}}, "ceiling"),  # 2 x 1 x 0.25 = 0.5
])
def test_the_freeze_refuses_worst_cases_the_runtime_or_two_units_in_flight_would_breach(runner, change, match):
    spend_terms(runner, **change)
    with pytest.raises(SystemExit, match=match):
        rules.record_freeze(runner)
    assert not runner.ledger.exists()


def test_the_freeze_accepts_the_test_spend_terms(runner):
    assert rules.record_freeze(runner)["event"] == "freeze"


def private_home(root, name):
    """A unit's private home under `root` holding a stand-in credential copy (never the real one)."""
    home = root / ".private-homes" / name
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text("stand-in")
    return home


@pytest.fixture
def live_session():
    """A process group that lives for the test, as a launched unit's session does."""
    session = subprocess.Popen(["sleep", "120"], start_new_session=True)
    yield session.pid
    session.kill()
    session.wait()


def test_every_unit_command_starts_by_removing_the_copies_no_live_unit_holds(runner, live_session, capsys):  # X5
    dead, live = private_home(runner.work, "a" * 32), private_home(runner.work, "b" * 32)
    judge_dead, judge_live = (private_home(runner.pools / task / "first", task * 16) for task in ("t1", "t2"))
    (run_dir(runner, record={"sandbox": {"home": str(live)}}) / "run.pgid").write_text(str(live_session))
    run_dir(runner, k=2, record={"sandbox": {"home": str(dead)}})
    for task, home in (("t1", judge_dead), ("t2", judge_live)):
        records = pool_dir_of(runner, task)
        (records / "mapping.json").write_text(json.dumps({"judges": {H: {"sandbox": {"home": str(home)}}}}))
    (runner.pools / "t2" / "first" / "records" / f"judge-{H}.pgid").write_text(str(live_session))
    with pytest.raises(SystemExit, match="provider spend refused"):  # refused, but only after the sweep
        study.candidates(runner, "calibration", "direct", ["t1"])
    left = sorted(p.parents[1].name for root in (runner.work, runner.pools) for p in root.rglob(".credentials.json"))
    out = capsys.readouterr().out
    assert (left, str(dead / ".claude" / ".credentials.json") in out, "stand-in" in out) == (
        sorted(["b" * 32, "t2" * 16]), True, False)


def test_a_second_unit_command_refuses_while_one_runs(runner):  # review3 minor 2: R3 across processes
    with study.command_lock(runner):
        with pytest.raises(SystemExit, match="another study command"):
            study.settle_runs(runner, [])


def test_settle_refuses_a_unit_whose_session_still_runs(runner, live_session):  # review3 X6
    tree = runner.work / "agents" / "x"
    tree.mkdir(parents=True)
    records = run_dir(runner, record={"tree": str(tree), "sandbox": {"home": str(runner.work / "home")}})
    (records / "run.pgid").write_text(str(live_session))
    with pytest.raises(SystemExit, match="still running"):
        study.settle_runs(runner, [records])
    assert (tree.is_dir(), "calls" in json.loads((records / "study.json").read_text())) == (True, False)


def test_a_pause_that_named_no_reset_reopens_only_at_a_reset_after_the_limit_was_hit(ledger):  # review3 minor 10
    pause = spend.record(ledger, "pause", unit="/w/run-1", reset=None)
    hit = pause["time"]
    with pytest.raises(SystemExit, match="after the limit was hit"):
        spend.resume_after_limit(ledger, hit - 60, 1.0, 2.0, hit + 1, now=hit + 2)
    assert spend.resume_after_limit(ledger, hit + 1, 1.0, 2.0, hit + 2, now=hit + 3)["event"] == "resume"


@pytest.mark.parametrize("five_hour, weekly", [(100.0, 3.0), (3.0, 100), (True, 3.0), (3.0, False)])
def test_resume_refuses_a_meter_at_its_limit_or_a_truth_value(ledger, five_hour, weekly):  # review3 minor 10
    spend.record(ledger, "pause", unit="/w/run-1", reset=RESET)
    with pytest.raises(SystemExit, match="percent"):
        resume(ledger, five_hour=five_hour, weekly=weekly)


def test_a_unit_settled_above_its_worst_case_is_flagged_and_closes_starts(runner):  # review3 minor 3
    records = priced_unit(runner.work / "u", metered(H, cost=0.5))
    spend.reserve(runner.ledger, "smoke", "candidate", H, 1, records, env("smoke"), price=(1000.0, 0.25))
    study.settle_price(runner, str(records), records, "smoke", H)
    settle = spend.latest(spend.rows(runner.ledger), "settle")
    with pytest.raises(SystemExit, match="above its worst case"):
        spend.reserve(runner.ledger, "smoke", "candidate", H, 1, "/w/2", env("smoke"), price=P)
    assert (settle["usd"], settle["over_reserved"]) == (0.5, True)


def test_a_call_whose_usage_names_no_model_counts_at_the_worst_case(tmp_path):  # review3 minor 4
    priced = units.priced(priced_unit(tmp_path, {"total_cost_usd": 0, "modelUsage": {}}), TABLE, 0.5)
    assert (priced["usd"], priced["missing"]) == (0.5, ["1"])


def pools_ready(runner, monkeypatch, *tasks):
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    monkeypatch.setattr(study, "launch", lambda *a, **k: pytest.fail("a judge was launched"))
    return [pool_dir_of(runner, task, []).parent for task in tasks]


def test_judges_skip_every_pool_whose_judges_the_caps_cannot_both_hold_and_say_so(runner, monkeypatch):  # minor 7
    pools = pools_ready(runner, monkeypatch, "t1", "t2")
    for k in range(30):
        spend.reserve(runner.ledger, "calibration", "judge", H, 1, f"/elsewhere/{k}#{H}", env("calibration"), price=P)
    with pytest.raises(SystemExit) as refused:
        study.judge(runner, "calibration", "first", ["t1", "t2"])
    assert (all(str(pool) in str(refused.value) for pool in pools), "room" in str(refused.value),
            spend.totals(runner.ledger)["calibration"]["judge"][S]["reserved"]) == (True, True, 0)


def test_a_pool_whose_first_judge_never_settled_gets_no_second_judge(runner, monkeypatch):  # review3 minor 7
    (pool,) = pools_ready(runner, monkeypatch, "t1")
    spend.reserve(runner.ledger, "calibration", "judge", H, 1, f"{pool}#{H}", env("calibration"), price=P)
    with pytest.raises(SystemExit, match="never settled"):
        study.judge(runner, "calibration", "first", ["t1"])
    assert spend.totals(runner.ledger)["calibration"]["judge"][S]["reserved"] == 0


def test_re_runs_of_cut_slots_beyond_the_caps_room_are_left_out_not_refused(runner, monkeypatch, capsys):  # minor 8
    monkeypatch.setenv(AUTH, "calibration")
    ready(runner)
    for k in range(1, 5):  # t1's four direct slots started, the first cut
        records = run_dir(runner, k=k, **({"cut": CUT, "outcome": "failed"} if k == 1 else {"outcome": "completed"}))
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, records, task="t1", arm="direct", price=P)
    for k in range(76):  # the Haiku cap is full
        spend.reserve(runner.ledger, "calibration", "candidate", H, 1, f"/elsewhere/{k}", task="t2", arm="x", price=P)
    assert study.candidates(runner, "calibration", "direct", ["t1"]) == []
    assert "keeps" in capsys.readouterr().out


def test_the_smoke_never_runs_a_cut_slot_again(runner, monkeypatch):  # a smoke cut fails the smoke (plan, R1)
    monkeypatch.setenv(AUTH, "smoke")
    ready(runner, smoke=False, chosen=False)
    records = run_dir(runner, tranche="smoke", task="r2", cut=CUT, outcome="failed")
    spend.reserve(runner.ledger, "smoke", "candidate", H, 1, records, env("smoke"), task="r2", arm="direct", price=P)
    monkeypatch.setattr(study, "one_run", lambda *a, **k: pytest.fail("a cut smoke slot ran again"))
    assert study.candidates(runner, "smoke", "direct", ["r2"]) == []


def test_a_visible_check_past_its_bound_is_counted_apart_never_as_a_pass_or_a_failure():  # re-review N2
    from experiments.seed_set import readout
    timed_out = {"passed": None, "failing": [], "timed_out": "the visible check ran past 1200 s"}
    runs = {f"/w/{k}": {"tranche": "calibration", "arm": "direct", "task": "t1", "outcome": "completed", "calls": 1,
                        "visible": timed_out if k == 0 else {"passed": k == 1}} for k in range(4)}
    records = [{"pool": "first", "task": "t1", "arm": "direct", "run": run, "status": "rated", "scores": {H: 4}}
               for run in runs]
    row = readout.measure_free(runs)["calibration/direct"]
    assert ((row["visible_passed"], row["visible_timed_out"]),
            [visible for _, visible in readout.direct_runs(records, runs, H, ["t1"])["t1"]]) == (
        (1, 1), [True, False, False])


def test_a_cut_run_counts_as_cut_in_the_measure_free_table_never_as_failed():  # R1: no observation
    from experiments.seed_set import readout
    runs = {"/w/1": {"tranche": "calibration", "arm": "direct", "outcome": "failed", "cut": CUT, "calls": 1},
            "/w/2": {"tranche": "calibration", "arm": "direct", "outcome": "failed", "calls": 1}}
    row = readout.measure_free(runs)["calibration/direct"]
    assert (row["runs"], row["failed"], row["cut"], row["calls"]) == (2, 1, 1, 2)


def test_a_reader_never_sees_a_row_half_written(ledger):  # the runner reads the ledger while another unit appends
    big, stop, errors = "x" * 200_000, threading.Event(), []

    def read():
        while not stop.is_set():
            try:
                spend.rows(ledger)
            except ValueError as error:
                errors.append(error)
                return
    reader = threading.Thread(target=read)
    reader.start()
    for k in range(60):
        spend.record(ledger, "settle", unit=f"/w/{k}", note=big)
    stop.set()
    reader.join()
    assert errors == []


def test_a_reader_parses_the_ledger_after_releasing_its_lock(ledger, monkeypatch):  # re-review n7
    """While `rows` parses, a writer can take the exclusive lock: a reader holds the lock only while it reads."""
    import fcntl
    spend.record(ledger, "pause", unit="/w/1", reset=None)
    held = []

    class Parser:  # json as `rows` uses it, asking for the writers' lock at each row it parses
        @staticmethod
        def loads(line):
            with open(ledger) as other:
                try:
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held.append(False)
                except BlockingIOError:
                    held.append(True)
            return json.loads(line)
    monkeypatch.setattr(spend, "json", Parser)
    spend.rows(ledger)
    assert held == [False]


def test_writers_finish_beside_readers_looping_on_the_ledger(ledger):  # re-review n7: 120 writers, 16 readers
    """120 writer threads (reservations of two tranches, judges, pauses with 200 KB rows, resumes) released at once
    beside 16 threads reading the ledger the whole time: every writer finishes, no reader sees a half-written row,
    the caps and the pauses hold; the longest writer wait is printed."""
    import random
    import time
    rng, price = random.Random(0), (5.0, 0.05)
    barrier, stop, errors, waits = threading.Barrier(136), threading.Event(), [], []

    def reader():
        barrier.wait()
        while not stop.is_set():
            try:
                spend.rows(ledger)
            except ValueError as error:
                errors.append(repr(error))

    def writer(k, kind, task):
        barrier.wait()
        start = time.time()
        try:
            if kind == "pause":
                spend.record(ledger, "pause", unit=f"/w/p{k}", reset=RESET - 7200, text="x" * 200_000)
            elif kind == "resume":
                spend.resume_after_limit(ledger, RESET - 7200, 10.0, 20.0, time.time() - 1)
            elif kind == "judge":
                spend.reserve(ledger, "calibration", "judge", rng.choice([H, S]), 1, f"/p/{task}#{k}",
                              env("calibration"), price=price, task=task, pool="first")
            else:
                spend.reserve(ledger, kind, "candidate", H, 1, f"/w/{kind}{k}", env(kind), limit=5, price=price,
                              task=task, arm="direct", step="first")
        except SystemExit:
            pass
        waits.append(time.time() - start)

    jobs = [(k, rng.choice(["calibration", "calibration", "redraw", "judge", "pause", "resume"]), f"t{rng.randrange(6)}")
            for k in range(120)]
    readers = [threading.Thread(target=reader) for _ in range(16)]
    writers = [threading.Thread(target=writer, args=job) for job in jobs]
    for thread in readers + writers:
        thread.start()
    for thread in writers:
        thread.join(timeout=120)
    hung = sum(thread.is_alive() for thread in writers)
    stop.set()
    for thread in readers:
        thread.join(timeout=30)
    rows = spend.rows(ledger)
    print(f"120 writers beside 16 readers: {hung} hung, longest writer wait {max(waits):.2f} s, {len(rows)} rows")
    closed = [r["seq"] for r in spend.starts(rows) if spend.open_pauses([x for x in rows if x["seq"] < r["seq"]])]
    over = [(t, k, m) for t, kinds in spend.CAPS.items() for k, caps in kinds.items() for m, cap in caps.items()
            if spend.reserved(rows, t, k, m) > cap]
    assert (hung, errors, closed, over) == (0, [], [], [])
