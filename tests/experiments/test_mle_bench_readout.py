"""The MLE-bench screen readout (`experiments/mle_bench_tasks/screen_readout.py`; family plan M1, M7 to M9, Task 6).

Every export is built by the ladder's own test helper (`long_horizon_record_support.export`, the layout that
`slot_record.py` loads and the launcher writes), every reward by the verifier's own `grade_submission.outcome`, and
each attempt's files sit where the launcher puts them (`slots/<start>-<slot>/jobs/<job>/<trial>/result.json`, a
regrade's under `regrade/<attempt>-regrade-<n>/`). Nothing runs an agent, a container or a provider call.
"""

import datetime
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from tests.experiments.long_horizon_record_support import ROOT, filled, with_values
from tests.experiments.long_horizon_record_support import export as lh_export

KIT = ROOT / "experiments" / "mle_bench_tasks"
LEADERBOARD = ROOT / "tests" / "experiments" / "fixtures" / "mle_bench" / "tiny-tabular" / "competition" / "leaderboard.csv"
ZONE = "America/Los_Angeles"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


readout = _load(KIT / "screen_readout.py", "mle_screen_readout_tested")
verifier = _load(KIT / "verifier" / "grade_submission.py", "mle_grade_submission_for_readout")

FAMILY = json.loads((KIT / "family.json").read_text())
CPU = [c["name"] for c in FAMILY["candidates"] if c["class"] == "cpu"]  # leaf, textnorm-ru, birds
A, B, C = CPU
SCREEN = with_values(filled(), {"tasks.list": [{"name": name} for name in CPU], "attempt.efforts": ["medium"]})
PLACE = with_values(filled(), {"tasks.list": [{"name": name} for name in CPU]})
ENDED = {"by": "schedule", "cause": None}
STOPPED = {"by": "stop", "cause": "a match of token_scan.py (ledger row 2026-11-20)"}
INFRA = {"row": 4}
CUT = {"row": 10}
NO_REWARD = {"class": "infrastructure_failure", "excluded": "no reward after regrades"}
NOT_COUNTED = {"infrastructure failure": INFRA, "cut": CUT, "no reward after regrades": NO_REWARD}


def _report(medal, score, valid=None):
    """A grader report as the benchmark's grade_csv gives it, for a medal level (0 none to 3 gold)."""
    return {"score": score, "valid_submission": score is not None if valid is None else valid, "above_median": medal > 0,
            "gold_medal": medal == 3, "silver_medal": medal == 2, "bronze_medal": medal == 1,
            "is_lower_better": False}


def _rewards(medal, score=0.8, valid=None):
    """The reward file the verifier writes for that report (Task 2's own function)."""
    return verifier.outcome(_report(medal, score, valid), LEADERBOARD)


def _write(path, rewards):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"verifier_result": None if rewards is None else {"rewards": rewards}}))


def _attempt(state, start):
    return state / "slots" / f"{start['start']:03d}-{start['slot']}"


def _results(state, doc, regrades=None, scores=None, files=None):
    """Each observation's trial result, from its exported reward; regrades: {start: (trial rewards, regrade
    rewards)} for a start whose reward came from a regrade."""
    for start in doc["starts"]:
        attempt = _attempt(state, start)
        attempt.mkdir(parents=True)
        if start["start"] in (regrades or {}):
            trial, regrade = regrades[start["start"]]
            _write(attempt / "jobs" / "job" / "trial" / "result.json", trial)
            _write(attempt / "regrade" / f"{attempt.name}-regrade-1" / "result.json", regrade)
        elif start["start"] in (files or {}):
            _write(attempt / "jobs" / "job" / "trial" / "result.json", files[start["start"]])
        elif start["class"] == "observation" and start["reward"] is not None:
            score = (scores or {}).get(start["start"], 0.8)
            _write(attempt / "jobs" / "job" / "trial" / "result.json", _rewards(int(start["reward"]), score))
    (state / "passthrough").mkdir(parents=True, exist_ok=True)
    rows = [{"time": 1_795_000_000.0 + start["start"], "slot": _attempt(state, start).name, "usd": start["usd"]}
            for start in doc["starts"]]
    (state / "passthrough" / "requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def _stage(tmp_path, name, table, *, end=ENDED, criterion=SCREEN, regrades=None, scores=None, files=None):
    """A stage's (criterion, export, state root): table maps a competition to its slots' outcomes at the one effort."""
    efforts = criterion["attempt"]["efforts"]
    shaped = {task: ({efforts[0]: outcomes} if isinstance(outcomes, list) else outcomes)
              for task, outcomes in table.items()}
    doc = lh_export(shaped, end=end)
    state = tmp_path / name
    _results(state, doc, regrades, scores, files)
    return criterion, doc, state


def _compute(tmp_path, one, two=None, *, no_stage_two=False, placement=None, end_one=ENDED, end_two=ENDED):
    stage_one = _stage(tmp_path, "one", one, end=end_one)
    stage_two = _stage(tmp_path, "two", two, end=end_two) if two is not None else None
    placed = _stage(tmp_path, "place", placement, criterion=PLACE) if placement is not None else None
    return readout.compute(stage_one, stage_two, no_stage_two=no_stage_two, placement=placed,
                           time_zone=ZoneInfo(ZONE))


def _class(result, name):
    return result["competitions"][name]["screen"]["class"]


# ---- 1. The screen's classes (M1, as ruled in fix round 1): a class as soon as no missing outcome could change it --

I, S, AB, LO, TWO = "incomplete", "survives", "above the band", "excluded low", "undecided: awaits stage two"
# (medals, observations) -> (class, missing), for every reachable count of three slots
STAGE_ONE_TABLE = {(0, 0): (I, 3), (0, 1): (I, 2), (1, 1): (I, 2), (0, 2): (I, 1), (1, 2): (S, 0), (2, 2): (I, 1),
                   (0, 3): (TWO, 0), (1, 3): (S, 0), (2, 3): (S, 0), (3, 3): (AB, 0)}
STAGE_TWO_TABLE = {(0, 0): (I, 3), (0, 1): (I, 2), (1, 1): (S, 0), (0, 2): (I, 1), (1, 2): (S, 0), (2, 2): (S, 0),
                   (0, 3): (LO, 0), (1, 3): (S, 0), (2, 3): (S, 0), (3, 3): (S, 0)}


def test_the_tables_hold_every_reachable_count_pair_and_name_the_readouts_classes():
    pairs = {(k, n) for n in range(4) for k in range(n + 1)}
    assert (set(STAGE_ONE_TABLE), set(STAGE_TWO_TABLE), (I, S, AB, LO, TWO)) == (
        pairs, pairs, (readout.INCOMPLETE, readout.SURVIVES, readout.ABOVE, readout.LOW, readout.UNDECIDED))


@pytest.mark.parametrize("stage, counts", [("one", c) for c in STAGE_ONE_TABLE] + [("two", c) for c in STAGE_TWO_TABLE])
def test_a_stage_classes_every_reachable_count_pair_as_the_table_says(stage, counts):
    expected = (STAGE_ONE_TABLE if stage == "one" else STAGE_TWO_TABLE)[counts]
    assert readout.stage_class(stage, *counts, slots=3) == expected


@pytest.mark.parametrize("rewards, expected", [([1, 1, 1], readout.ABOVE), ([1, 0, 0], readout.SURVIVES),
                                               ([0, 1, 1], readout.SURVIVES), ([0, 0, 0], readout.UNDECIDED)])
def test_stage_one_alone_gives_its_rows_of_the_table(tmp_path, rewards, expected):
    assert _class(_compute(tmp_path, {A: rewards}), A) == expected


@pytest.mark.parametrize("rewards, expected", [([0, 0, 1], readout.SURVIVES), ([1, 1, 1], readout.SURVIVES),
                                               ([0, 0, 0], readout.LOW), ([1, "-", "-"], readout.SURVIVES)])
def test_stage_two_decides_a_competition_with_no_medal_in_three(tmp_path, rewards, expected):
    assert _class(_compute(tmp_path, {A: [0, 0, 0]}, {A: rewards}), A) == expected


def test_the_two_stages_are_read_together_for_the_six_observations(tmp_path):
    screen = _compute(tmp_path, {A: [0, 0, 0]}, {A: [0, 0, 0]})["competitions"][A]["screen"]
    assert (screen["observations"], screen["medals"], screen["missing"]) == (6, 0, 0)


def test_no_medal_in_five_observations_is_incomplete_and_names_the_one_missing(tmp_path):
    screen = _compute(tmp_path, {A: [0, 0, 0]}, {A: [0, 0, "-"]})["competitions"][A]["screen"]
    assert (screen["class"], screen["observations"], screen["missing"]) == (readout.INCOMPLETE, 5, 1)


def test_a_competition_the_second_stage_did_not_fund_says_so(tmp_path):
    result = _compute(tmp_path, {A: [0, 0, 0], B: [0, 0, 0]}, {A: [0, 0, 1]})
    assert (_class(result, A), _class(result, B)) == (readout.SURVIVES, readout.NOT_FUNDED)


def test_with_no_second_stage_every_undecided_competition_is_not_funded(tmp_path):
    result = _compute(tmp_path, {A: [0, 0, 0], B: [1, 0, 0]}, no_stage_two=True)
    assert (_class(result, A), _class(result, B)) == (readout.NOT_FUNDED, readout.SURVIVES)


def test_a_competition_with_no_observation_at_all_is_not_screened(tmp_path):
    screen = _compute(tmp_path, {A: ["-", INFRA, "-"], B: [1, 0, 0]})["competitions"][A]["screen"]
    assert (screen["class"], screen["missing"]) == (readout.NOT_SCREENED, 3)


def test_incomplete_and_not_funded_are_not_excluded_low(tmp_path):
    result = _compute(tmp_path, {A: [0, 0, 0], B: [0, 0, 0]}, {A: [0, "-", "-"]})
    assert (_class(result, A), _class(result, B)) == (readout.INCOMPLETE, readout.NOT_FUNDED)


@pytest.mark.parametrize("rewards, expected", [([1, 1, "-"], (readout.INCOMPLETE, 1)), ([1, 0, "-"], (readout.SURVIVES, 0)),
                                               ([0, 0, "-"], (readout.INCOMPLETE, 1))])
def test_stage_one_short_of_three_has_a_class_only_when_the_missing_one_cannot_change_it(tmp_path, rewards, expected):
    screen = _compute(tmp_path, {A: rewards})["competitions"][A]["screen"]
    assert (screen["class"], screen["missing"]) == expected


@pytest.mark.parametrize("rewards, expected", [([1, 0, "-"], readout.SURVIVES), ([1, 1, "-"], readout.INCOMPLETE)])
def test_a_stage_still_running_gives_a_class_once_it_is_decided(tmp_path, rewards, expected):
    assert _class(_compute(tmp_path, {A: rewards}, end_one=None), A) == expected


# ---- 2. Only observations decide (coordinator note 2) ----------------------------------------------------------

@pytest.mark.parametrize("kind", sorted(NOT_COUNTED))
def test_a_start_that_is_no_observation_never_turns_no_medal_in_two_into_a_class(tmp_path, kind):
    result = _compute(tmp_path, {A: [0, 0, NOT_COUNTED[kind]]})
    screen = result["competitions"][A]["screen"]
    assert (screen["class"], screen["observations"], screen["missing"]) == (readout.INCOMPLETE, 2, 1)


@pytest.mark.parametrize("kind", sorted(NOT_COUNTED))
def test_a_start_that_is_no_observation_is_listed_with_its_reason_and_never_scored(tmp_path, kind):
    stage = _compute(tmp_path, {A: [0, 0, NOT_COUNTED[kind]]})["competitions"][A]["stage_one"]
    listed = [(e["start"], e["reason"]) for e in stage["not_counted"]]
    assert (listed, [a["start"] for a in stage["attempts"]]) == ([(3, listed[0][1])], [1, 2]) and listed[0][1]


def test_a_contaminated_observation_is_listed_and_enters_no_count(tmp_path):
    term = sorted(readout.slot_record.frozen_term_digests(SCREEN))[0]
    stage = _compute(tmp_path, {A: [1, 1, {"reward": 1, "contamination": [term]}]})["competitions"][A]
    assert (stage["screen"]["class"], stage["stage_one"]["medals"],
            [e["start"] for e in stage["stage_one"]["not_counted"]]) == (readout.INCOMPLETE, 2, [3])


def test_a_cut_is_counted_as_a_cut_and_its_rerun_slot_as_the_observation(tmp_path):
    stage = _compute(tmp_path, {A: [[CUT, {"reward": 1}], 1, 1]})["competitions"][A]
    assert (stage["screen"]["class"], stage["stage_one"]["cuts"]) == (readout.ABOVE, 1)


def test_the_cost_of_a_competition_counts_every_start_cuts_and_failures_included(tmp_path):
    stage = _compute(tmp_path, {A: [[CUT, {"reward": 0}], INFRA, 1]})["competitions"][A]["stage_one"]
    assert stage["usd"] == pytest.approx(4.0)


# ---- 3. The graded outcomes come from the result that gave the reward -------------------------------------------

def test_score_and_percentile_come_from_the_trial_when_the_trial_gave_the_reward(tmp_path):
    attempt = _compute(tmp_path, {A: [1, 0, 0]})["competitions"][A]["stage_one"]["attempts"][0]
    expected = _rewards(1)
    assert (attempt["score"], attempt["percentile"], attempt["medal"], attempt["source"]) == (
        expected["score"], expected["percentile"], 1, "trial")


@pytest.mark.parametrize("trial", [None, _rewards(0, 0.5)], ids=["case-1-no-reward", "case-2-a-zero"])
def test_score_and_percentile_come_from_the_regrade_when_the_regrade_gave_the_reward(tmp_path, trial):
    regraded = _rewards(2, 0.9)
    stage_one = _stage(tmp_path, "one", {A: [1, 0, 0]}, regrades={1: (trial, regraded)})
    attempt = readout.compute(stage_one, time_zone=ZoneInfo(ZONE))["competitions"][A]["stage_one"]["attempts"][0]
    assert (attempt["score"], attempt["percentile"], attempt["medal"], attempt["source"]) == (
        regraded["score"], regraded["percentile"], 2, "regrade 1")


def test_a_submission_with_no_score_has_no_score_or_percentile_and_counts_as_invalid(tmp_path):
    stage_one = _stage(tmp_path, "one", {A: [0, 0, 1]}, scores={1: None})
    stage = readout.compute(stage_one, time_zone=ZoneInfo(ZONE))["competitions"][A]["stage_one"]
    first = stage["attempts"][0]
    assert ((first["score"], first["percentile"], first["valid"]), stage["valid"], stage["invalid"]) == (
        (None, None, 0), 2, 1)


def _one(tmp_path, files):
    stage_one = _stage(tmp_path, "one", {A: [1, 0, 0]}, files=files)
    return readout.compute(stage_one, time_zone=ZoneInfo(ZONE))


def test_an_attempt_whose_grader_caught_an_error_is_listed_for_a_ruling_and_still_counted(tmp_path):
    result = _one(tmp_path, {1: _rewards(1) | {"grader_exception": 1}})
    stage = result["competitions"][A]["stage_one"]
    assert ([a["start"] for a in stage["grader_exceptions"]], stage["grader_exception"], stage["medals"],
            result["competitions"][A]["screen"]["class"]) == ([1], 1, 1, readout.SURVIVES)


def test_a_reward_file_without_the_grader_exception_field_reads_as_no_exception(tmp_path):
    stage = _one(tmp_path, None)["competitions"][A]["stage_one"]
    assert (stage["grader_exceptions"], stage["grader_exception"]) == ([], 0)


def test_the_table_shows_how_many_observations_carry_a_grader_exception(tmp_path):
    line = next(line for line in readout.table(_one(tmp_path, {1: _rewards(1) | {"grader_exception": 1}}))
                .splitlines() if line.startswith(A))
    assert "1 grader exception" in line


def test_a_valid_submission_with_no_score_is_counted_as_valid_not_scored(tmp_path):
    stage = _one(tmp_path, {2: _rewards(0, None, valid=True)})["competitions"][A]["stage_one"]
    second = stage["attempts"][1]
    assert ((second["valid"], second["score"], second["percentile"]), stage["valid"], stage["valid_not_scored"]) == (
        (1, None, None), 3, 1)


def test_the_above_median_count_is_read_from_the_result_files(tmp_path):
    stage = _compute(tmp_path, {A: [1, 0, 1]})["competitions"][A]["stage_one"]
    assert stage["above_median"] == 2


def _one_of(tmp_path, rewards, files):
    return readout.compute(_stage(tmp_path, "one", {A: rewards}, files=files), time_zone=ZoneInfo(ZONE))


def test_an_observation_whose_reward_has_no_verifier_result_stays_counted_and_is_listed(tmp_path):
    result = _one_of(tmp_path, [1, 0, 0], {3: None})
    stage, screen = result["competitions"][A]["stage_one"], result["competitions"][A]["screen"]
    listed = stage["rewards_without_result"]
    assert ((stage["observations"], stage["medals"], screen["class"]), [e["start"] for e in listed],
            stage["reward_without_result"], bool(listed[0]["reason"])) == ((3, 1, readout.SURVIVES), [3], 1, True)


@pytest.mark.parametrize("rewards, marked", [([1, 0, 0], False), ([0, 0, 0], True)],
                         ids=["unchanged-without-it", "changed-without-it"])
def test_a_class_that_rests_on_a_reward_without_a_verifier_result_is_marked(tmp_path, rewards, marked):
    screen = _one_of(tmp_path, rewards, {3: None})["competitions"][A]["screen"]
    assert screen["rests_on_rewards_without_result"] is marked


def test_the_table_shows_how_many_rewards_have_no_verifier_result(tmp_path):
    line = next(line for line in readout.table(_one_of(tmp_path, [0, 0, 0], {3: None})).splitlines()
                if line.startswith(A))
    assert "1 reward(s) without a verifier result" in line


THRESHOLDS = {"bronze_threshold": 0.75, "silver_threshold": 0.85, "gold_threshold": 0.95, "median_threshold": 0.7}


def test_the_thresholds_are_read_from_the_reward_file_and_absent_ones_are_not_recorded(tmp_path):
    attempts = _one_of(tmp_path, [1, 0, 0], {1: _rewards(1) | THRESHOLDS})["competitions"][A]["stage_one"]["attempts"]
    assert (attempts[0]["thresholds"], attempts[1]["thresholds"]) == (
        {"bronze": 0.75, "silver": 0.85, "gold": 0.95, "median": 0.7},
        {"bronze": None, "silver": None, "gold": None, "median": None})


def test_the_table_prints_each_score_against_the_thresholds(tmp_path):
    lines = readout.table(_one_of(tmp_path, [1, 0, 0], {1: _rewards(1) | THRESHOLDS})).splitlines()
    first, second = (next(line for line in lines if f"start {n}:" in line) for n in (1, 2))
    assert ("bronze 0.75" in first and "median 0.7" in first, "not recorded" in second) == (True, True)


def test_a_result_file_that_disagrees_with_the_exported_reward_is_refused(tmp_path):
    stage_one = _stage(tmp_path, "one", {A: [1, 0, 0]})
    _write(_attempt(stage_one[2], stage_one[1]["starts"][0]) / "jobs" / "job" / "trial" / "result.json",
           _rewards(0))
    with pytest.raises(readout.ReadoutError, match="reward"):
        readout.compute(stage_one, time_zone=ZoneInfo(ZONE))


def test_an_observation_with_no_attempt_directory_is_refused(tmp_path):
    stage_one = _stage(tmp_path, "one", {A: [1, 0, 0]})
    shutil.rmtree(_attempt(stage_one[2], stage_one[1]["starts"][0]))
    with pytest.raises(readout.ReadoutError, match="attempt directory"):
        readout.compute(stage_one, time_zone=ZoneInfo(ZONE))


# ---- 4. The placement: the ladder's pooled label, never pooled with the screen ---------------------------------

FIFTEEN_NONE = {"low": [0] * 5, "medium": [0] * 5, "high": [0] * 5}
THREE_OF_FIFTEEN = {"low": [1, 0, 0, 0, 0], "medium": [1, 0, 0, 0, 0], "high": [1, 0, 0, 0, 0]}


def test_the_screens_attempts_are_never_pooled_into_the_placement_count(tmp_path):
    placed = _compute(tmp_path, {A: [1, 1, 0]}, placement={A: FIFTEEN_NONE})["placement"]["competitions"][A]
    assert ((placed["K"], placed["n"], placed["label"]), (placed["screen"]["medals"], placed["screen"]["observations"])
            ) == ((0, 15, "floor"), (2, 3))


def test_the_placement_gives_the_ladders_label_and_both_exact_intervals(tmp_path):
    placed = _compute(tmp_path, {A: [1, 0, 0]}, placement={A: THREE_OF_FIFTEEN})["placement"]["competitions"][A]
    assert ((placed["K"], placed["n"], placed["label"]), [round(100 * x, 1) for x in placed["interval_90"]],
            [round(100 * x, 1) for x in placed["interval_95"]]) == ((3, 15, "screened in"), [5.7, 44.0], [4.3, 48.1])


def test_a_competition_that_did_not_survive_the_screen_is_not_placed(tmp_path):
    with pytest.raises(readout.ReadoutError, match="survive"):
        _compute(tmp_path, {A: [1, 1, 1]}, placement={A: FIFTEEN_NONE})


# ---- 5. The exact intervals ------------------------------------------------------------------------------------

@pytest.mark.parametrize("k, expected", [(1, (0.3, 27.9)), (2, (2.4, 36.3)), (3, (5.7, 44.0)), (4, (9.7, 51.1)),
                                         (5, (14.2, 57.7))])
def test_the_90_percent_intervals_of_1_to_5_of_fifteen_are_m1s(k, expected):
    assert tuple(round(100 * x, 1) for x in readout.interval(k, 15, 0.90)) == expected


@pytest.mark.parametrize("n", [1, 3, 6, 15])
@pytest.mark.parametrize("level", [0.90, 0.95])
def test_at_the_edges_the_interval_has_its_closed_form(n, level):
    tail = (1 - level) / 2
    none, every = readout.interval(0, n, level), readout.interval(n, n, level)
    assert none == pytest.approx((0.0, 1 - tail ** (1 / n)), abs=1e-12) and every == pytest.approx(
        (tail ** (1 / n), 1.0), abs=1e-12)


# ---- 6. Priced usage per calendar day (M9, "The day") ------------------------------------------------------------

def _at(*fields):
    return datetime.datetime(*fields, tzinfo=ZoneInfo(ZONE)).timestamp()


def test_a_request_priced_after_midnight_counts_on_the_later_day(tmp_path):
    log = tmp_path / "passthrough" / "requests.jsonl"
    log.parent.mkdir(parents=True)
    rows = [{"time": _at(2026, 11, 20, 23, 59, 59), "slot": "x", "usd": 1.25},
            {"time": _at(2026, 11, 21, 0, 0, 1), "slot": "x", "usd": 2.5},
            {"time": _at(2026, 11, 21, 0, 0, 2), "slot": None, "status": 403, "refused": "slot cap reached"}]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert readout.per_day([tmp_path], ZoneInfo(ZONE)) == {"2026-11-20": 1.25, "2026-11-21": 2.5}


def test_the_per_day_total_sums_every_stage_s_request_log(tmp_path):
    result = _compute(tmp_path, {A: [0, 0, 0]}, {A: [0, 0, 1]})
    assert sum(result["per_day_usd"].values()) == pytest.approx(6.0)


# ---- 7. A stop places nothing ----------------------------------------------------------------------------------

def test_a_stage_one_stop_classes_nothing_and_names_the_rule(tmp_path):
    result = _compute(tmp_path, {A: [1, 1, 1], B: [1, 0, 0]}, end_one=STOPPED)
    assert ({_class(result, A), _class(result, B)}, result["stop"]) == (
        {readout.WITHHELD}, {"stage": "one", "cause": STOPPED["cause"]})


def test_a_stage_two_stop_classes_nothing_of_stage_two(tmp_path):
    result = _compute(tmp_path, {A: [0, 0, 0], B: [1, 0, 0]}, {A: [0, 1, 0]}, end_two=STOPPED)
    assert (_class(result, A), result["stop"]["stage"]) == (readout.WITHHELD, "two")


def test_a_placement_stop_places_nothing(tmp_path):
    stage_one = _stage(tmp_path, "one", {A: [1, 0, 0]})
    placed = _stage(tmp_path, "place", {A: THREE_OF_FIFTEEN}, criterion=PLACE, end=STOPPED)
    result = readout.compute(stage_one, no_stage_two=True, placement=placed, time_zone=ZoneInfo(ZONE))
    assert (result["placement"]["competitions"][A]["label"], result["stop"]["stage"]) == (None, "placement")


# ---- 8. The inputs are checked against each other ----------------------------------------------------------------

def test_stage_two_holding_a_competition_with_a_stage_one_medal_is_refused(tmp_path):
    with pytest.raises(readout.ReadoutError, match="stage two"):
        _compute(tmp_path, {A: [1, 0, 0]}, {A: [0, 0, 0]})


def test_stage_two_before_stage_one_has_ended_is_refused(tmp_path):
    with pytest.raises(readout.ReadoutError, match="stage two"):
        _compute(tmp_path, {A: [0, 0, 0]}, {A: [0, 0, 0]}, end_one=None)


def test_a_screen_criterion_with_more_than_one_effort_is_refused(tmp_path):
    stage_one = _stage(tmp_path, "one", {A: {"low": [1, 0, 0]}}, criterion=PLACE)
    with pytest.raises(readout.ReadoutError, match="effort"):
        readout.compute(stage_one, time_zone=ZoneInfo(ZONE))


# ---- 8b. A final readout reads the criterion of its label (the ladder's bound, with this family's paths) ---------

def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _tranche(root, frozen=True, change=None):
    """A tranche's criterion under root, as Task 4 places it, and a manifest in the ladder's format over it."""
    criterion = root / "experiments" / "mle_bench_tasks" / "tranches" / "screen-cpu" / "ladder.json"
    criterion.parent.mkdir(parents=True)
    criterion.write_text(json.dumps(SCREEN))
    files = {"experiments/mle_bench_tasks/tranches/screen-cpu/ladder.json": _sha(criterion.read_bytes())} | {
        f"experiments/{rel}": _sha((ROOT / "experiments" / rel).read_bytes())
        for rel in ("mle_bench_tasks/screen_readout.py", "long_horizon_tasks/readout.py",
                    "long_horizon_tasks/slot_record.py")}
    manifest = root / "manifest.json"
    manifest.write_bytes(json.dumps({"frozen": frozen, "not_covered": {}, "files": files}).encode())
    if change:
        criterion.write_text(json.dumps(with_values(SCREEN, change)))
    return criterion, manifest, _sha(manifest.read_bytes())


def test_a_final_readout_accepts_the_criterion_its_label_names(tmp_path):
    criterion, manifest, label = _tranche(tmp_path)
    assert readout.bound(criterion, manifest, label, root=tmp_path) is None


@pytest.mark.parametrize("case, match", [("not frozen", "not frozen"), ("another label", "label"),
                                         ("a changed criterion", "ladder.json")])
def test_a_final_readout_refuses_a_criterion_its_label_does_not_name(tmp_path, case, match):
    criterion, manifest, label = _tranche(tmp_path, frozen=case != "not frozen",
                                          change={"attempt.model": "x"} if case == "a changed criterion" else None)
    with pytest.raises(readout.ladder.ReadoutError, match=match):
        readout.bound(criterion, manifest, "0" * 64 if case == "another label" else label, root=tmp_path)


# ---- 9. Output: one JSON document and a short table, deterministic -----------------------------------------------

def _cli_args(tmp_path, stages):
    args = []
    for flag, (criterion, doc, state) in stages:
        (state / "ladder.json").write_text(json.dumps(criterion))
        (state / "export.json").write_text(json.dumps(doc))
        (state / "manifest.json").write_text(json.dumps({"frozen": False, "not_covered": {}, "files": {}}))
        args += [flag, str(state / "export.json"), str(state), str(state / "ladder.json"), str(state / "manifest.json")]
    return args


def _run(args):
    return subprocess.run([sys.executable, "-I", str(KIT / "screen_readout.py"), *args], capture_output=True,
                          text=True)


def test_the_command_writes_the_same_json_and_table_twice(tmp_path):
    stage_one = _stage(tmp_path, "one", {A: [1, 0, 0], B: [0, 0, 0], C: [1, 1, 1]})
    stage_two = _stage(tmp_path, "two", {B: [0, 0, 1]})
    args = _cli_args(tmp_path, (("--stage-one", stage_one), ("--stage-two", stage_two)))
    (tmp_path / "stand-ins.json").write_text("{}")
    runs = []
    for out in ("a.json", "b.json"):
        done = _run([*args, "--time-zone", ZONE, "--rehearsal", str(tmp_path / "stand-ins.json"),
                     "--json", str(tmp_path / out)])
        runs.append((done.returncode, done.stdout, (tmp_path / out).read_bytes()))
    document = json.loads(runs[0][2])
    assert (runs[0] == runs[1], runs[0][0], [document["competitions"][n]["screen"]["class"] for n in CPU],
            A in runs[0][1]) == (True, 0, [readout.SURVIVES, readout.SURVIVES, readout.ABOVE], True)


def test_the_command_refuses_a_final_readout_whose_manifest_is_not_the_labels(tmp_path):
    args = _cli_args(tmp_path, (("--stage-one", _stage(tmp_path, "one", {A: [1, 0, 0]})),))
    done = _run([*args, "--time-zone", ZONE, "--json", str(tmp_path / "out.json")])
    assert (done.returncode, "not frozen" in done.stderr, (tmp_path / "out.json").exists()) == (2, True, False)


def test_the_document_names_the_inputs_the_exports_do_not_carry(tmp_path):
    assert set(_compute(tmp_path, {A: [1, 0, 0]})["not_in_the_inputs"]) == {
        "installed packages", "processes holding the GPU"}


def test_the_document_states_that_a_request_counts_on_the_day_it_was_received(tmp_path):
    assert "received" in _compute(tmp_path, {A: [1, 0, 0]})["day_rule"]
