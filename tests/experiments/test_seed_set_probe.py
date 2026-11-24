"""The ladder probe's steps (experiments/seed_set/probing.py), the early judge look and the apparatus measures
(rules.py, study.py, host.py) on synthetic run records: no provider process is launched here."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.compare.repos import load
from experiments.seed_set import host, ladder, layout, probing, rules, spend, study
from tests.experiments.seed_set_offline_support import (
    committed_runtime, manifest_rows, stand_in_login, write_frozen_criterion,
)

H, S = spend.HAIKU, spend.SONNET
P = (1000.0, 0.01)  # a priced ceiling and per-call worst case no test here reaches
ROOT = Path(__file__).resolve().parents[2]
SIZES = {"T0": 8, "T1": 12, "T2": 12, "T3": 12, "T4": 12, "T5": 8}


@pytest.fixture
def s(tmp_path, monkeypatch):
    """A study with a full ladder of task rows, a freeze and a passed smoke; the redraw tranche authorized."""
    runtime = tmp_path / "runtime"
    tasks = committed_runtime(runtime, manifest_rows(SIZES))
    criterion = tmp_path / "judge-calibration.json"
    criterion.write_text(json.dumps({"judges": [H, S], "rubric": layout.RUBRIC}))
    study_ = layout.Study(runtime, tmp_path / "work", tmp_path / "pools", tmp_path / "results", tasks, criterion,
                          tmp_path / "state")
    write_frozen_criterion(study_)
    monkeypatch.setattr(rules, "loaded_elsewhere", lambda runtime: [])  # the tests import this checkout's modules
    rules.record_freeze(study_)
    spend.record(study_.ledger, "smoke", passed=True, bisect=False)
    monkeypatch.setenv(spend.AUTHORIZATION, "redraw")
    return study_


def probed(s, phase, passes, self_check=False):
    """Checked probe runs, each reserved: `passes[rung]` of the rung's four probe tasks pass their hidden set."""
    for rung, count in passes.items():
        for k, task in enumerate(ladder.probe_tasks(layout.task_rows(s), rung)):
            records = s.work / "records" / "direct" / f"run-{phase}-{task}"
            records.mkdir(parents=True)
            withheld = ladder.tier_form(rung)[1] == ladder.WITHHELD
            (records / "study.json").write_text(json.dumps({
                "tranche": "redraw", "task": task, "arm": "direct", "model": H, "effort": "medium", "max_calls": 1,
                "step": phase, "rung": rung, "calls": 1, "outcome": "completed", "hidden": {"passed": k < count},
                "self_check": None if withheld else self_check}))
            (records / "record.json").write_text("{}")
            spend.reserve(s.ledger, "redraw", "candidate", H, 1, records, task=task, arm="direct", step=phase, price=P)


FLAT_IN_BAND = {"T1": 4, "T2": 4, "T3": 2, "T4": 1, "T5": 0}


def test_the_first_probe_is_the_flat_five(s):
    assert probing.answer(s) == {"phase": "first", "bisect": False, "probe": ["T1", "T2", "T3", "T4", "T5"]}


def test_a_smoke_that_calls_for_bisection_starts_at_the_middle_of_t0_to_t5(s):
    spend.record(s.ledger, "smoke", passed=True, bisect=True)
    assert probing.answer(s)["probe"] == ["T2"]


def test_a_tier_in_band_writes_the_chosen_tasks_and_their_hash(s):
    probed(s, "first", FLAT_IN_BAND)
    out = probing.probe_readout(s)
    row = spend.latest(spend.rows(s.ledger), "probe_readout")
    assert ({t["rung"] for t in out["chosen"]}, len(out["chosen"]), bool(row["chosen_sha256"])) == (
        {"T3", "T4"}, 20, True)


def test_the_chosen_tasks_become_the_calibration_tasks(s):
    probed(s, "first", FLAT_IN_BAND)
    probing.probe_readout(s)
    rules.require_order(s, "calibration")  # no refusal
    assert layout.tranche_tasks(s, "calibration")[:2] == ["T3-00", "T3-01"]


def test_tiers_straddling_the_band_split_ten_and_ten(s):
    probed(s, "first", {"T1": 4, "T2": 4, "T3": 4, "T4": 0, "T5": 0})
    assert ladder.choose(layout.task_rows(s), probing.answer(s), probing.results(s, "first")[0], 0.0,
                         ladder.FLAT)[9:11] == [
        ("T3-09", "T3"), ("T4-00", "T4")]


def test_agents_running_the_test_themselves_switch_the_chosen_tier_to_withheld(s):
    probed(s, "first", FLAT_IN_BAND, self_check=True)
    assert {t["rung"] for t in probing.probe_readout(s)["chosen"]} == {"T3w", "T4w"}


def test_all_too_easy_bisects_the_easy_extension(s):
    probed(s, "first", dict.fromkeys(ladder.FLAT, 4))
    assert probing.answer(s) == {"phase": "extension", "first": "all_easy", "probe": ["T2w"]}


def test_all_too_hard_waits_for_the_transcripts_and_writes_no_list(s):
    probed(s, "first", dict.fromkeys(ladder.FLAT, 0))
    out = probing.probe_readout(s)
    assert ("await" in out["answer"], (s.results / layout.CHOSEN).exists()) == (True, False)


def test_the_extension_probe_refuses_until_the_transcripts_were_read(s):
    probed(s, "first", dict.fromkeys(ladder.FLAT, 0))
    with pytest.raises(SystemExit, match="nothing to probe now"):
        probing.probe(s, ["T0"])


def test_recorded_transcripts_open_t0_and_t1_again(s):
    probed(s, "first", dict.fromkeys(ladder.FLAT, 0))
    probing.record_transcripts(s, False, "runs sound: the agent edited the wrong function", [])
    assert probing.answer(s) == {"phase": "extension", "first": "all_hard", "probe": ["T0"]}


def test_runs_a_fault_failed_become_incidents_and_count_toward_the_stop_rule(s):
    probed(s, "first", dict.fromkeys(ladder.FLAT, 0))
    runs = sorted((s.work / "records" / "direct").glob("run-first-T1-*"))[:3]
    probing.record_transcripts(s, True, "pytest could not start in the sandbox", runs)
    assert (load(runs[0] / "study.json")["incident"], spend.latest(spend.rows(s.ledger), "stop") is not None) == (
        "apparatus fault: pytest could not start in the sandbox", True)  # 3 of 20 planned: over 10%


def test_an_extension_that_still_misses_stops_every_later_start(s):
    probed(s, "first", dict.fromkeys(ladder.FLAT, 4))
    probed(s, "extension", {"T2w": 4, "T3w": 4, "T4w": 4})
    probing.probe_readout(s)
    with pytest.raises(SystemExit, match="the whole ladder missed"):
        spend.reserve(s.ledger, "calibration", "candidate", H, 1, "/w/x", {spend.AUTHORIZATION: "calibration"}, price=P)


def test_an_extension_in_band_chooses_from_the_extension_rungs(s):
    probed(s, "first", dict.fromkeys(ladder.FLAT, 4))
    probed(s, "extension", {"T2w": 2})
    assert {t["rung"] for t in probing.probe_readout(s)["chosen"]} == {"T2w", "T1w"}  # the unprobed tie: easier (M1)


def test_the_extension_is_used_once_nothing_more_probes_after_its_answer(s):
    probed(s, "first", dict.fromkeys(ladder.FLAT, 4))
    probed(s, "extension", {"T2w": 2})
    probing.probe_readout(s)
    with pytest.raises(SystemExit, match="nothing to probe now"):
        probing.probe(s)


def test_a_probe_step_already_started_launches_nothing_again(s):
    for task in ladder.probe_tasks(layout.task_rows(s), "T1"):
        spend.reserve(s.ledger, "redraw", "candidate", H, 1, f"/w/{task}", task=task, arm="direct", step="first", price=P)
    assert probing.probe(s, ["T1"]) == []


def test_the_probe_refuses_a_rung_the_answer_does_not_ask_for(s):
    with pytest.raises(SystemExit, match="takes"):
        probing.probe(s, ["T6"])


def test_the_probe_refuses_without_a_passed_smoke(s):
    spend.record(s.ledger, "smoke", passed=False)
    with pytest.raises(SystemExit, match="no passed smoke"):
        probing.probe(s)


def test_the_probe_is_charged_to_the_redraw_cap_only(s, monkeypatch):
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    with pytest.raises(SystemExit, match="provider spend refused"):
        probing.probe(s)


def test_budget_arithmetic_fits_the_caps():
    caps, tasks = spend.CAPS, ladder.CALIBRATION_TASKS
    worst_probe = (len(ladder.FLAT) + max(len(ladder.EASY_EXTENSION), len(ladder.HARD_EXTENSION))) * ladder.PROBE_TASKS
    assert (worst_probe <= caps["redraw"]["candidate"][H], tasks * layout.PLANNED["calibration"]["direct"],
            tasks * layout.PLANNED["calibration"]["direct_sonnet"], tasks + layout.RETESTS["calibration"]) == (
        True, caps["calibration"]["candidate"][H], caps["calibration"]["candidate"][S],
        caps["calibration"]["judge"][H])  # 36 <= 40, 80, 20, 30: the early look judges three of the 20 first pools


def test_the_41st_probe_call_refuses(s):
    for k in range(40):
        spend.reserve(s.ledger, "redraw", "candidate", H, 1, f"/w/{k}", task=f"x{k}", arm="direct", step="first", price=P)
    with pytest.raises(SystemExit, match="cap reached"):
        spend.reserve(s.ledger, "redraw", "candidate", H, 1, "/w/40", task="x40", arm="direct", step="extension", price=P)


def test_a_probed_task_that_is_drawn_keeps_its_probe_run_as_a_first_haiku_run(s, monkeypatch):
    probed(s, "first", FLAT_IN_BAND)
    probing.probe_readout(s)
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    for k in range(3):  # T3-00 was probed: three more Haiku runs complete its four
        spend.reserve(s.ledger, "calibration", "candidate", H, 1, f"/w/c{k}", task="T3-00", arm="direct", price=P)
    assert study.candidates(s, "calibration", "direct", ["T3-00"]) == []


def early_pool(s, task, base, upstream):
    directory = s.results / "pools" / f"{task}-first"
    directory.mkdir(parents=True)
    clones = {f"c{k}": {"arm": "anchor", "labels": [f"{task}-{name}"], "ratings": {
        H: {"quality": score}, S: {"quality": score}}} for k, (name, score) in enumerate(
        (("base", base), ("upstream", upstream)))}
    (directory / "results.json").write_text(json.dumps({"clones": clones}))


def chosen_world(s):
    probed(s, "first", FLAT_IN_BAND)
    probing.probe_readout(s)
    return layout.tranche_tasks(s, "calibration")


def test_before_the_early_look_only_the_first_three_first_pools_are_judged(s):
    tasks = chosen_world(s)
    rules.require_early_look(s, "calibration", "first", tasks[:3])
    with pytest.raises(SystemExit, match="before the early judge look"):
        rules.require_early_look(s, "calibration", "first", tasks[3:4])


def test_an_early_look_with_the_reference_under_four_points_on_two_of_three_stops_the_judges(s):
    tasks = chosen_world(s)
    for task, (base, upstream) in zip(tasks[:3], ((0, 3), (1, 4), (0, 8))):
        early_pool(s, task, base, upstream)
    assert rules.early_look(s)["passed"] is False
    with pytest.raises(SystemExit, match="early judge look failed"):
        rules.require_early_look(s, "calibration", "first", tasks[3:4])


def test_a_passed_early_look_opens_the_other_judges(s):
    tasks = chosen_world(s)
    for task, (base, upstream) in zip(tasks[:3], ((0, 3), (0, 8), (0, 8))):
        early_pool(s, task, base, upstream)
    assert rules.early_look(s)["passed"] is True
    rules.require_early_look(s, "calibration", "retest", tasks[3:4])  # no refusal


def test_a_withheld_package_names_its_staged_tests_for_the_check_only(tmp_path):
    (tmp_path / "pkg" / "withheld" / "tests").mkdir(parents=True)
    (tmp_path / "pkg" / "withheld" / "tests" / "test_v.py").write_text("def test_v(): pass\n")
    (tmp_path / "records").mkdir()
    staged = study.stage_withheld(tmp_path / "pkg", tmp_path / "records")
    assert (study.launch_env(H, 1, tmp_path / "host-home", withheld=staged)["SEED_SET_WITHHELD"], (staged / "tests" / "test_v.py").is_file(),
            "SEED_SET_WITHHELD" in study.launch_env(H, 1), study.stage_withheld(tmp_path / "in-tree", tmp_path)) == (
        str(tmp_path / "records" / "withheld"), True, False, None)


def test_a_draw_short_of_twenty_is_a_stop_with_no_list(s):
    probed(s, "first", {"T1": 4, "T2": 4, "T3": 4, "T4": 4, "T5": 2})  # T5 (8) filled from T4 (12): 20 here
    rows = layout.task_rows(s)
    for row in rows:
        row["rejected"] = "short" if row["tier"] == "T4" and row["id"] >= "T4-06" else row.get("rejected")
    s.tasks_file.write_text("".join(json.dumps(row) + "\n" for row in rows))
    out = probing.probe_readout(s)
    row, stop = spend.latest(spend.rows(s.ledger), "probe_readout"), spend.latest(spend.rows(s.ledger), "stop")
    assert ((s.results / layout.CHOSEN).exists(), row["drawn"], "too short" in stop["reason"], "owner" in out["stop"]) == (
        False, {"T4": 6, "T5": 8}, True, True)
    with pytest.raises(SystemExit, match="the study is stopped"):
        spend.reserve(s.ledger, "calibration", "candidate", H, 1, "/w/x", {spend.AUTHORIZATION: "calibration"}, price=P)


def test_the_probe_readout_states_the_drawn_sets_count_per_rung(s):
    probed(s, "first", FLAT_IN_BAND)
    out = probing.probe_readout(s)
    assert (out["drawn"], spend.latest(spend.rows(s.ledger), "probe_readout")["drawn"]) == ({"T3": 12, "T4": 8},) * 2


def test_the_host_checks_a_withheld_package_through_its_in_tree_view(tmp_path):
    package = tmp_path / "pkg"
    (package / "withheld" / "tests").mkdir(parents=True)
    (package / "withheld" / "tests" / "test_v.py").write_text("def test_v(): pass\n")
    (package / "seed").mkdir()
    (package / "seed" / "dev-check.json").write_text(json.dumps({"argv": ["pytest"], "timeout_sec": 9,
                                                                 "withheld": True}))
    view = host.in_tree_view(package, tmp_path / "view")
    assert ((view / "seed" / "tests" / "test_v.py").is_file(), json.loads((view / "seed" / "dev-check.json").read_text())) == (
        True, {"argv": ["pytest"], "timeout_sec": 9})


@pytest.mark.parametrize("wall, cost, bisect", [(600, None, False), (901, None, True), (600, 0.51, True)])
def test_the_smoke_calls_for_bisection_above_15_minutes_or_half_a_dollar(tmp_path, wall, cost, bisect):
    home = tmp_path / "home"
    (home / ".claude" / "projects" / "p").mkdir(parents=True)
    if cost is not None:
        (home / ".claude" / "projects" / "p" / "s.jsonl").write_text(json.dumps({"costUSD": cost}) + "\n")
    (tmp_path / "calls" / "1").mkdir(parents=True)
    (tmp_path / "calls" / "1" / "prompt.txt").write_text("p")
    (tmp_path / "record.json").write_text(json.dumps({"wall_clock_sec": wall, "sandbox": {"home": str(home)}}))
    assert rules.bisect_from_start([({}, tmp_path)])["bisect"] is bisect


def test_a_t0_draw_filled_from_t2_fits_the_calibration_caps_and_one_more_call_refuses(s, monkeypatch):
    probed(s, "first", dict.fromkeys(ladder.FLAT, 0))
    probing.record_transcripts(s, False, "runs sound", [])
    probed(s, "extension", {"T0": 2})
    out = probing.probe_readout(s)
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    tasks, planned = len(out["chosen"]), layout.PLANNED["calibration"]
    spend.check(s.ledger, "calibration", "candidate", H, tasks * planned["direct"])  # 80 of 80: no refusal
    spend.check(s.ledger, "calibration", "candidate", S, tasks * planned["direct_sonnet"])  # 20 of 20
    with pytest.raises(SystemExit, match="of the cap remain"):
        spend.check(s.ledger, "calibration", "candidate", H, tasks * planned["direct"] + 1)
    assert (out["drawn"], tasks) == ({"T0": 8, "T2": 12}, 20)


def probe_unit(s, task, rung, attempt=1, phase="first", **facts):
    """One reserved probe run of `task` with the given facts (default: an incident with no hidden result)."""
    records = s.work / "records" / "direct" / f"run-{phase}-{task}-{attempt}"
    records.mkdir(parents=True)
    (records / "study.json").write_text(json.dumps({
        "tranche": "redraw", "task": task, "arm": "direct", "model": H, "effort": "medium", "max_calls": 1,
        "step": phase, "rung": rung, **facts}))
    (records / "record.json").write_text("{}")
    spend.reserve(s.ledger, "redraw", "candidate", H, 1, records, limit=2, task=task, arm="direct", step=phase, price=P)
    return records


def launches(s, monkeypatch):
    """probe() with each launch replaced by a passing probe run written in place; returns the launched jobs."""
    jobs = []
    def fake(study_, spec, task, rung, fix, phase, limit):
        jobs.append((task, rung))
        return probe_unit(s, task, rung, attempt=9, phase=phase, calls=1, outcome="completed",
                          hidden={"passed": True}, self_check=False), {"calls": 1}
    monkeypatch.setattr(probing, "probe_run", fake)
    probing.probe(s)
    return jobs


def flat_with(s, rung, units):
    """The flat probe with every rung but `rung` settled; `units(task, k)` writes `rung`'s four probe runs."""
    probed(s, "first", {r: n for r, n in FLAT_IN_BAND.items() if r != rung})
    for k, task in enumerate(ladder.probe_tasks(layout.task_rows(s), rung)):
        units(task, k)


def test_a_probe_run_whose_runner_died_is_an_incident_relaunched_once(s, monkeypatch):  # review2 M2
    def units(task, k):
        if k == 0:
            probe_unit(s, task, "T3", exit=0)  # reserved and launched; the runner died before it was settled
        else:
            probe_unit(s, task, "T3", calls=1, outcome="completed", hidden={"passed": k < 2}, self_check=False)
    flat_with(s, "T3", units)
    assert (launches(s, monkeypatch), load(s.work / "records/direct/run-first-T3-00-1/study.json")["incident"]) == (
        [("T3-00", "T3")], "interrupted: the runner stopped before the run was settled")


def test_a_provider_incident_is_not_a_failure_the_rung_waits_for_its_relaunch(s):  # review2 M3
    def units(task, k):
        probe_unit(s, task, "T3", calls=1, outcome="failed", incident="provider: call 1: 529 overloaded") if k == 0 \
            else probe_unit(s, task, "T3", calls=1, outcome="completed", hidden={"passed": k < 2}, self_check=False)
    flat_with(s, "T3", units)
    assert probing.answer(s)["probe"] == ["T3"]


def test_a_relaunched_incident_launches_no_third_time_and_its_task_is_excluded(s, monkeypatch):
    def units(task, k):
        if k == 0:
            for attempt in (1, 2):
                probe_unit(s, task, "T3", attempt, calls=1, outcome="failed", incident="provider: 529")
        else:
            probe_unit(s, task, "T3", calls=1, outcome="completed", hidden={"passed": k < 3}, self_check=False)
    flat_with(s, "T3", units)
    figures = probing.results(s, "first")
    assert (figures[0]["T3"], figures[1]["T3"]["excluded"]) == (3, ["T3-00"])  # 2 of 3 usable pass: 3 on four
    assert probing.probe_readout(s)["counted_on_four"]["first/T3"].startswith("2 of 3 usable runs counted as 3")


CUT = {"call": "1", "reset": 1_794_627_837, "text": "You've hit your session limit"}


def test_a_probe_run_cut_by_a_usage_limit_is_no_failure_and_runs_again_once(s, monkeypatch):  # ruling R1
    def units(task, k):
        probe_unit(s, task, "T3", calls=1, outcome="failed", cut=CUT) if k == 0 \
            else probe_unit(s, task, "T3", calls=1, outcome="completed", hidden={"passed": k < 2}, self_check=False)
    flat_with(s, "T3", units)
    assert launches(s, monkeypatch) == [("T3-00", "T3")]


def test_a_probe_task_cut_twice_launches_no_third_time_and_is_excluded(s):
    def units(task, k):
        if k == 0:
            for attempt in (1, 2):
                probe_unit(s, task, "T3", attempt, calls=1, outcome="failed", cut=CUT)
        else:
            probe_unit(s, task, "T3", calls=1, outcome="completed", hidden={"passed": k < 3}, self_check=False)
    flat_with(s, "T3", units)
    figures = probing.results(s, "first")
    assert (figures[0]["T3"], figures[1]["T3"]["excluded"], figures[1]["T3"]["cuts"]) == (3, ["T3-00"], 2)


def test_a_rung_with_two_usable_runs_of_four_stops_the_probe_with_no_list(s):
    def units(task, k):
        if k < 2:
            for attempt in (1, 2):
                probe_unit(s, task, "T3", attempt, calls=1, outcome="failed", incident="provider: 529")
        else:
            probe_unit(s, task, "T3", calls=1, outcome="completed", hidden={"passed": True}, self_check=False)
    flat_with(s, "T3", units)
    out = probing.probe_readout(s)
    assert ("probe incomplete" in out["answer"]["stop"], (s.results / layout.CHOSEN).exists(),
            "probe incomplete" in spend.latest(spend.rows(s.ledger), "stop")["reason"]) == (True, False, True)


def test_a_settled_but_unchecked_probe_run_gets_its_hidden_check_on_the_next_probe(s, monkeypatch, tmp_path):
    monkeypatch.setattr(host, "hidden_check", lambda package, patch, runtime, record: {"passed": True, "failing": []})
    home = tmp_path / "home"
    home.mkdir()
    def units(task, k):
        records = probe_unit(s, task, "T3", calls=1, outcome="completed", final_patch=str(tmp_path / "final.patch"))
        (records / "record.json").write_text(json.dumps({"sandbox": {"home": str(home)}}))
        (layout.task_dir(s, task) / "withheld").mkdir(parents=True)  # no self-check detector to feed
    flat_with(s, "T3", units)
    probing.recover(s)
    assert probing.results(s, "first")[0]["T3"] == 4


def test_a_hidden_check_past_its_bound_makes_the_probe_run_an_incident_never_a_failure(s, monkeypatch, tmp_path):
    """Re-review N2: a timed-out hidden check is neither a pass nor a zero; the run is an incident, relaunched once."""
    monkeypatch.setattr(host, "hidden_check", lambda package, patch, runtime, record: {
        "passed": None, "failing": [], "timed_out": "the hidden tests ran past 600 s"})
    home = tmp_path / "home"
    home.mkdir()
    records = probe_unit(s, "T3-00", "T3", calls=1, outcome="completed", final_patch=str(tmp_path / "final.patch"))
    (records / "record.json").write_text(json.dumps({"sandbox": {"home": str(home)}}))
    (layout.task_dir(s, "T3-00") / "withheld").mkdir(parents=True)
    probing.recover(s)
    facts = json.loads((records / "study.json").read_text())
    assert (facts["incident"], probing.usable(facts), probing.allowed([facts])) == (
        "host check: the hidden tests ran past 600 s", False, 2)


def test_recovery_refuses_while_the_launched_session_still_runs(s):
    records = probe_unit(s, "T3-00", "T3")
    (records / "run.pgid").write_text(str(os.getpgid(0)))
    with pytest.raises(SystemExit, match="still running"):
        probing.recover(s)


def test_settle_finds_the_fix_of_a_withheld_package(s, monkeypatch):  # review2 M2: no KeyError for a withheld id
    tree = s.work / "agents" / "x"
    tree.mkdir(parents=True)
    records = s.work / "records" / "direct" / "run-w"
    records.mkdir(parents=True)
    task = next(row["withheld_id"] for row in layout.task_rows(s) if row.get("withheld_id"))
    (records / "study.json").write_text(json.dumps({"tranche": "calibration", "task": task, "max_calls": 1}))
    (records / "record.json").write_text(json.dumps({"tree": str(tree)}))
    seen = []
    monkeypatch.setattr(study, "finish", lambda study_, records_, facts, fix: seen.append(fix) or {})
    study.settle_runs(s, [records])
    assert seen == [ladder.fix_commits(layout.task_rows(s))[task]]


def test_the_redraw_incident_threshold_counts_the_extensions_probe_units(s):  # minor 4
    probed(s, "first", dict.fromkeys(ladder.FLAT, 4))
    probed(s, "extension", {"T2w": 0, "T3w": 0, "T4w": 0})
    assert rules.planned_runs(s, "redraw") == 32


def test_host_checks_keep_bytecode_in_their_box_and_reuse_it(monkeypatch):  # the 1fd10ab4c3 anchor cause
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    done, _ = host.guarded([sys.executable, "-c", "import os, sys; print(os.environ.get('PYTHONDONTWRITEBYTECODE'),"
                                                  " sys.dont_write_bytecode, sys.pycache_prefix)"])
    flag, dont_write, prefix = done.stdout.split()
    assert (flag, dont_write, Path(prefix).name, Path(prefix).parent.name.startswith("seed-set-host-")) == (
        "None", "False", "pycache", True)


def test_a_probe_step_the_redraw_allowance_cannot_hold_is_a_stop(s):  # review3 minor 8
    for k in range(25):  # 15 calls left for the flat five's 20 runs
        spend.reserve(s.ledger, "redraw", "candidate", H, 1, f"/elsewhere/{k}", task=f"x{k}", arm="direct", step="first",
                      price=P)
    with pytest.raises(SystemExit, match="stopped"):
        probing.probe(s)
    assert "redraw allowance" in spend.latest(spend.rows(s.ledger), "stop")["reason"]


def test_a_probe_run_the_token_would_not_outlive_is_refused_before_it_is_prepared(s, monkeypatch, tmp_path):  # R16
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "login"))
    stand_in_login(tmp_path / "login", expires_in_sec=600)
    with pytest.raises(SystemExit, match="refreshed the login"):
        probing.probe(s, ["T1"])
    assert (spend.starts(spend.rows(s.ledger)), sorted(p.name for p in s.work.iterdir())) == ([], [])
