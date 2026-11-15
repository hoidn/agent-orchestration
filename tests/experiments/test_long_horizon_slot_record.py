"""The long-horizon slot record (`experiments/long_horizon_tasks/slot_record.py`): the one layout the launcher writes
and the readout reads, and its loader, which refuses a record that does not fit and never skips one.

Every record is constructed here; nothing runs an agent, a container or a provider call.
"""

import pytest

from tests.experiments.long_horizon_record_support import (EFFORTS, LADDER, STANDINS, TASKS, TERM_SHA256, export,
                                                           load_kit, same, with_values)

slot_record = load_kit("slot_record")
CRITERION = with_values(LADDER, STANDINS)
PILOT = LADDER["schedule"]["pilot"]["task"]


def _load(record, ladder=CRITERION):
    return slot_record.load(record, ladder)


def _broken(change):
    record = export({TASKS[0]: same([1, 0])})
    change(record)
    return record


def _one(*outcomes, effort="low", task=TASKS[0]):
    """One task's export with the given starts in one slot of the given effort, and plain observations elsewhere."""
    return export({task: {e: [list(outcomes)] if e == effort else [0] for e in EFFORTS}})


SMOKE_TASK, SMOKE_EFFORT, _ = slot_record.smoke_cell(CRITERION)
SESSION_STOPS = [cause for cause, seen in slot_record.LAUNCHER_STOPS.items() if seen == "a session"]


@pytest.mark.parametrize("change, message", [
    (lambda x: x["starts"][0].update(slot="r9-nowhere-low"), "joins no slot"),
    (lambda x: x["starts"][0].update(label="d" * 64), "label"),
    (lambda x: x["starts"][0].update(row=16), "ruling"),
    (lambda x: x["starts"][0].update(row=17), "row"),
    (lambda x: x["starts"][0].update(reward=0.5), "reward"),
    (lambda x: x["starts"][0].update(reward=None), "regrade"),
    (lambda x: x["starts"][0].update(excluded="cosmic rays"), "excluded"),
    (lambda x: x["starts"][0].update({"row": 15, "class": "infrastructure_failure", "excluded": "indeterminate",
                                      "reward": 0}), "excluded"),
    (lambda x: x["starts"][0].update(extra=1), "keys"),
    (lambda x: x["starts"][0].pop("usd"), "keys"),
    (lambda x: x["starts"][0].pop("contamination"), "keys"),
    (lambda x: x["starts"][0].pop("api_retry"), "keys"),
    (lambda x: x["starts"][0].update(usd=True), "usd"),
    (lambda x: x["starts"][0]["tokens"].pop("cache_read"), "tokens"),
    (lambda x: x["starts"][0].update(api_retry=-1), "api_retry"),
    (lambda x: x["starts"][0].update(tokens=None), "tokens"),
    (lambda x: x["starts"][0]["tokens"].update(output=-1), "negative"),
    (lambda x: x["starts"][0].update(minutes="30"), "minutes"),
    (lambda x: x["starts"][0].update(graded={"passed": 3, "total": 2}), "graded"),
    (lambda x: x["starts"][0].update(egress_refused={"<address>:443": 0}), "egress_refused"),
    (lambda x: x["starts"][1].update(start=1), "start"),
    (lambda x: x["starts"].append(dict(x["starts"][0], start=99)), "run again only after"),
    (lambda x: x["slots"][0].update(task="no-such-task"), "task"),
    (lambda x: x["slots"][0].update(effort="max"), "effort"),
    (lambda x: x["slots"][0].update(round=6), "round"),
    (lambda x: x["slots"].append(dict(x["slots"][0], slot="duplicate")), "given twice"),
    (lambda x: x.update(end={"by": "stop", "cause": None}), "cause"),
    (lambda x: x.update(end={"by": "tired", "cause": None}), "end"),
    (lambda x: x.update(end={"by": "starts", "cause": None}), "starts"),
    (lambda x: x.update(label="not a label"), "label"),
    (lambda x: x.update(earlier_labels=[{"label": x["label"], "ended_by": "a ledger row"}]), "label is given twice"),
    (lambda x: x.update(allowance={"weekly_points": "12"}), "keys"),
    (lambda x: x.update(extra=1), "keys"),
])
def test_a_record_that_does_not_fit_the_layout_is_refused(change, message):
    with pytest.raises(slot_record.RecordError, match=message):
        _load(_broken(change))


def test_an_attempt_still_open_is_listed_apart_and_one_that_names_no_slot_is_refused():
    """Task 8 part A m11: an open attempt is in no count, and the record says it is there."""
    record = export({TASKS[0]: {"low": [1, "-"], "medium": [0], "high": [0]}},
                    open_=[{"slot": f"r2-{TASKS[0]}-low", "start": 9}])
    loaded = len(_load(record))
    record["open"].append({"slot": "r9-nowhere-low", "start": 10})
    with pytest.raises(slot_record.RecordError, match="open"):
        _load(record)
    assert loaded == 3


def test_a_record_that_fits_loads_joined_to_its_slot_and_its_row():
    first = _load(export({TASKS[0]: {"low": [{"row": 8, "reward": 1}], "medium": [0], "high": [0]}}))[0]
    assert {key: first[key] for key in ("task", "effort", "round", "class", "flagged", "counted", "success")} == {
        "task": TASKS[0], "effort": "low", "round": 1, "class": "observation", "flagged": True, "counted": True,
        "success": True}


def test_an_observation_with_no_reward_is_refused_until_it_is_regraded():
    """Task 7 ruling 3: a reward is only what a verifier gave; a time-limit ending with none (row 3) is regraded
    first, never scored 0."""
    with pytest.raises(slot_record.RecordError, match="regraded first"):
        _load(export({TASKS[0]: {"low": [{"row": 3, "reward": None}], "medium": [0], "high": [0]}}))


def test_no_reward_after_the_regrades_of_any_observation_s_ending_is_an_infrastructure_failure_never_scored():
    """Task 7 ruling 3: regrade case 1 holds after any ending whose row is an observation's (row 3 here)."""
    first = _load(_one(CASE_1 | {"row": 3}))[0]
    assert (first["row"], first["class"], first["counted"], first["success"]) == (
        3, "infrastructure_failure", False, None)


def test_a_cut_s_reward_is_never_read():
    first = _load(_one({"row": 10, "reward": 1}, 0))[0]
    assert (first["class"], first["counted"], first["success"]) == ("cut", False, None)


# ---- M1: the launcher's class, checked against the row; a launcher stop is never scored ---------------------------

@pytest.mark.parametrize("cause", slot_record.LAUNCHER_STOPS)
def test_a_launcher_stop_on_a_normal_ending_is_a_stop_and_never_scored(cause):
    """On the smoke's slot every launcher cause can occur."""
    record = _one({"row": 5, "reward": 1, "class": "stop", "stop_cause": cause}, effort=SMOKE_EFFORT, task=SMOKE_TASK)
    first = _load(record)[0]
    assert (first["class"], first["stop_cause"], first["counted"], first["success"]) == ("stop", cause, False, None)


@pytest.mark.parametrize("cause", SESSION_STOPS)
def test_a_cause_that_needs_a_session_is_refused_on_a_pre_session_failure(cause):
    with pytest.raises(slot_record.RecordError, match="does not fit row 1"):
        _load(_one({"row": 1, "class": "stop", "stop_cause": cause}))


ANY_START = [cause for cause, seen in slot_record.LAUNCHER_STOPS.items() if seen == "any start"]


def test_a_match_or_an_incomplete_scan_of_either_teardown_scan_may_stop_any_start():
    """Coordinator ruling (Task 5): token_scan.py reads every teardown's files, and the runtime check reads the
    containers of any start that had a session or containers, which a pre-session failure can have."""
    assert set(ANY_START) == {"a match of token_scan.py", "an incomplete scan of token_scan.py",
                              "a match of the runtime check in the attempt's containers",
                              "an incomplete scan of the runtime check in the attempt's containers"}


@pytest.mark.parametrize("cause", ANY_START)
def test_a_teardown_scan_may_stop_a_pre_session_failure(cause):
    first = _load(_one({"row": 1, "class": "stop", "stop_cause": cause}))[0]
    assert (first["class"], first["counted"]) == ("stop", False)


def test_a_launch_refused_before_the_harness_ran_has_no_cause_since_it_is_no_start():
    """Coordinator ruling (Task 5): a refused launch creates no start and is not exported; it stays in the
    launcher's own log."""
    with pytest.raises(slot_record.RecordError, match="does not fit row 1"):
        _load(_one({"row": 1, "class": "stop", "stop_cause": "refused at launch"}))


@pytest.mark.parametrize("task, effort, rnd", [(TASKS[0], "low", 1), (SMOKE_TASK, "high", 1), (SMOKE_TASK, "low", 2)])
def test_a_failed_smoke_check_is_refused_off_the_smoke_s_slot(task, effort, rnd):
    stop = {"row": 5, "reward": 0, "class": "stop", "stop_cause": "a failed smoke check"}
    cells = {e: [0] * rnd for e in EFFORTS}
    cells[effort] = [0] * (rnd - 1) + [stop]
    with pytest.raises(slot_record.RecordError, match="does not fit row 5"):
        _load(export({task: cells}))


def test_the_smoke_s_slot_falls_back_to_the_first_qualified_task_not_load_sensitive():
    """D7.1: if gsea-proteomics does not qualify, the first qualified task in tasks.json order not load-sensitive."""
    ladder = with_values(CRITERION, {"tasks.qualified": [TASKS[0], TASKS[1], TASKS[2]],
                                     "tasks.load_sensitive": [TASKS[0]]})
    assert slot_record.smoke_cell(ladder) == (TASKS[1], SMOKE_EFFORT, 1)


@pytest.mark.parametrize("fields, why", [
    ({"class": "stop", "stop_cause": None}, "a stop on an observation row without a cause"),
    ({"class": "stop", "stop_cause": "a cosmic ray"}, "a cause that is no launcher stop"),
    ({"class": "observation", "stop_cause": "a subagent file"}, "a cause on a class that is no stop"),
    ({"class": "infrastructure_failure"}, "regrade case 1 as a class: the layout says row 5, excluded"),
    ({"row": 2, "class": "stop", "stop_cause": "a subagent file"}, "a launcher cause on a stop row")])
def test_a_class_that_does_not_fit_the_row_is_refused(fields, why):
    with pytest.raises(slot_record.RecordError, match="does not fit row"):
        _load(_one({"reward": 1} | fields))


# ---- M2: contamination on a start of any class; it excludes an observation only -----------------------------------

def test_a_contamination_hit_excludes_an_observation():
    first = _load(_one({"reward": 1, "contamination": [TERM_SHA256]}))[0]
    assert (first["class"], first["counted"]) == ("observation", False)


@pytest.mark.parametrize("fields, then, cls", [({"row": 10}, [0], "cut"), ({"row": 1}, [0], "pre_session_failure"),
                                               ({"row": 15}, [], "infrastructure_failure"), ({"row": 13}, [], "stop"),
                                               ({"class": "stop", "stop_cause": "a subagent file"}, [], "stop")])
def test_a_contamination_hit_on_a_start_of_another_class_loads_and_keeps_its_class(fields, then, cls):
    first = _load(_one(fields | {"contamination": [TERM_SHA256]}, *then))[0]
    assert (first["class"], first["contamination"], first["counted"]) == (cls, [TERM_SHA256], False)


def test_the_canary_s_sha256_is_a_frozen_term():
    canary = STANDINS.get("readout.contamination_scan.canary_sha256", "c" * 64)
    assert _load(_one({"reward": 0, "contamination": [canary]}))[0]["counted"] is False


@pytest.mark.parametrize("fields, message", [
    ({"contamination": ["0" * 64]}, "no frozen term"), ({"contamination": ["<a frozen term>"]}, "no frozen term"),
    ({"excluded": "contaminated", "contamination": [TERM_SHA256]}, "excluded")])
def test_a_contamination_result_that_names_no_frozen_term_or_an_old_exclusion_is_refused(fields, message):
    with pytest.raises(slot_record.RecordError, match=message):
        _load(_one({"reward": 0} | fields))


def test_while_the_terms_are_pending_no_contamination_result_can_be_joined():
    pending = with_values(LADDER, {"readout.contamination_scan.terms": None,
                                   "readout.contamination_scan.canary_sha256": None})
    with pytest.raises(slot_record.RecordError, match="no frozen term"):
        _load(_one({"reward": 0, "contamination": [TERM_SHA256]}), ladder=pending)


# ---- Minors: figures finite (m2), repeated keys (m3), the order of a slot's starts (m4), exclusions (m5), pilot (m6)

@pytest.mark.parametrize("change", [lambda x: x["starts"][0].update(usd=float("nan")),
                                    lambda x: x["starts"][0].update(usd=float("inf")),
                                    lambda x: x["starts"][0].update(minutes=-1.0),
                                    lambda x: x.update(allowance={"weekly_points": float("nan"), "readings": "r"}),
                                    lambda x: x.update(allowance={"weekly_points": -1, "readings": "r"})])
def test_a_figure_that_is_not_finite_or_is_negative_is_refused(change):
    with pytest.raises(slot_record.RecordError, match="finite number"):
        _load(_broken(change))


def test_a_figure_not_recorded_is_null_and_loads_as_null_never_as_zero():
    """Coordinator ruling (Task 5): minutes, each token count and api_retry may be null, meaning not recorded."""
    missing = {"minutes": None, "tokens": {"input": None, "output": 7, "cache_read": None, "cache_write_5m": 0,
                                           "cache_write_1h": None}, "api_retry": None}
    first = _load(_one(missing | {"reward": 1}))[0]
    assert {key: first[key] for key in missing} == missing


@pytest.mark.parametrize("text, message", [('{"a": 1, "a": 2}', "repeats the keys"), ('{"usd": NaN}', "NaN"),
                                           ('{"usd": Infinity}', "Infinity"), ('[{"x": 1, "x": 1}]', "repeats")])
def test_reading_refuses_a_repeated_key_and_nan_or_infinity(tmp_path, text, message):
    (tmp_path / "export.json").write_text(text)
    with pytest.raises(slot_record.RecordError, match=message):
        slot_record.read(tmp_path / "export.json")


PRE = {"row": 1}


@pytest.mark.parametrize("starts, message", [
    ([PRE, PRE, PRE, 0], "lost after the third"), ([PRE, PRE, {"row": 10}, PRE, 0], "lost after the third"),
    ([PRE, {"row": 10}, PRE, {"row": 10}, PRE, 0], "lost after the third"), ([0, {"row": 10}], "run again only after"),
    ([0, PRE], "run again only after"), ([{"row": 15}, 0], "run again only after")])
def test_a_sequence_of_starts_the_plan_forbids_is_refused(starts, message):
    with pytest.raises(slot_record.RecordError, match=message):
        _load(_one(*starts))


def test_two_pre_session_failures_and_cuts_may_precede_the_slot_s_observation():
    assert [s["class"] for s in _load(_one(PRE, {"row": 10}, PRE, {"row": 10}, 1))][:5] == [
        "pre_session_failure", "cut", "pre_session_failure", "cut", "observation"]


CASE_1 = {"class": "infrastructure_failure", "excluded": "no reward after regrades", "reward": None}


def test_no_reward_after_the_regrades_of_a_normal_ending_is_an_infrastructure_failure_never_scored():
    """D5 and ladder.json: regrade case 1 that still gives no reward is an infrastructure failure (coordinator
    ruling, Task 5): row 5, the class the launcher decided, enters no k or n."""
    first = _load(_one(CASE_1))[0]
    assert (first["row"], first["class"], first["counted"], first["success"]) == (
        5, "infrastructure_failure", False, None)


@pytest.mark.parametrize("fields", [{"excluded": "no reward after regrades", "reward": None},
                                    CASE_1 | {"reward": 1},
                                    {"excluded": "indeterminate", "reward": 1},
                                    {"excluded": "indeterminate", "reward": None}])
def test_an_exclusion_that_contradicts_its_d5_case_is_refused(fields):
    with pytest.raises(slot_record.RecordError, match="does not fit its D5 case"):
        _load(_one(fields))


@pytest.mark.parametrize("fields", [CASE_1 | {"row": 10}, {"class": "infrastructure_failure", "reward": None}])
def test_an_infrastructure_failure_on_an_observation_s_row_is_only_regrade_case_1(fields):
    with pytest.raises(slot_record.RecordError, match="does not fit row"):
        _load(_one(fields))


@pytest.mark.parametrize("usd,loads", [(0.02, True), (0.0, False)])
def test_an_infrastructure_failure_on_the_pre_session_row_is_one_the_passthrough_metered_usage_for(usd, loads):
    """Coordinator ruling on part A m12 (D5): row 1's form with metered usage is an infrastructure failure on its own
    row; with nothing metered it is a pre-session failure."""
    start = {"row": 1, "class": "infrastructure_failure", "reward": None, "usd": usd}
    try:
        loaded = _load(_one(start))[0]
    except slot_record.RecordError:
        loaded = None
    assert (loaded is not None, loaded and (loaded["class"], loaded["counted"])) == (
        loads, ("infrastructure_failure", False) if loads else None)


def _with_pilot(cells):
    return export({PILOT: {e: [0] for e in EFFORTS}, TASKS[0]: {e: [0, 0, 0] for e in EFFORTS}}, pilot=cells)


def test_the_pilot_is_the_three_efforts_of_round_1_of_the_pilot_task():
    loaded = _load(_with_pilot({(PILOT, e, 1) for e in EFFORTS}))
    assert sorted(s["effort"] for s in loaded if s["pilot"]) == sorted(EFFORTS)


@pytest.mark.parametrize("cells", [{(TASKS[0], "low", 3)}, {(PILOT, "low", 1)},
                                   {(TASKS[0], e, 1) for e in EFFORTS}])
def test_a_pilot_mark_on_any_other_slot_is_refused(cells):
    with pytest.raises(slot_record.RecordError, match="marked pilot"):
        _load(_with_pilot(cells))


@pytest.mark.parametrize("change, message", [
    (lambda x: x["starts"][0].update(start=0), "below 1"),
    (lambda x: x.update(earlier_labels=[{"label": "b" * 64, "ended_by": " "}]), "ended_by"),
    (lambda x: x.update(end={"by": "stop", "cause": " "}), "cause")])
def test_a_start_number_below_1_or_a_blank_ledger_row_is_refused(change, message):
    with pytest.raises(slot_record.RecordError, match=message):
        _load(_broken(change))
