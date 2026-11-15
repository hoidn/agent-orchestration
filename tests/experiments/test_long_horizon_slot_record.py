"""The long-horizon slot record (`experiments/long_horizon_tasks/slot_record.py`): the one layout the launcher writes
and the readout reads, and its loader, which refuses a record that does not fit and never skips one.

Every record is constructed here; nothing runs an agent, a container or a provider call.
"""

import pytest

from tests.experiments.long_horizon_record_support import (LADDER, STANDINS, TASKS, TERM_SHA256, export, load_kit,
                                                           same, with_values)

slot_record = load_kit("slot_record")
CRITERION = with_values(LADDER, STANDINS)


def _load(record, ladder=CRITERION):
    return slot_record.load(record, ladder)


def _broken(change):
    record = export({TASKS[0]: same([1, 0])})
    change(record)
    return record


@pytest.mark.parametrize("change, message", [
    (lambda x: x["starts"][0].update(slot="r9-nowhere-low"), "joins no slot"),
    (lambda x: x["starts"][0].update(label="d" * 64), "label"),
    (lambda x: x["starts"][0].update(row=16), "ruling"),
    (lambda x: x["starts"][0].update(row=17), "row"),
    (lambda x: x["starts"][0].update(reward=0.5), "reward"),
    (lambda x: x["starts"][0].update(reward=None), "regrade"),
    (lambda x: x["starts"][0].update(excluded="cosmic rays"), "excluded"),
    (lambda x: x["starts"][0].update(row=15, excluded="contaminated", contamination=[TERM_SHA256]), "excluded"),
    (lambda x: x["starts"][0].update(extra=1), "keys"),
    (lambda x: x["starts"][0].pop("usd"), "keys"),
    (lambda x: x["starts"][0].pop("contamination"), "keys"),
    (lambda x: x["starts"][0].update(usd=True), "usd"),
    (lambda x: x["starts"][0]["tokens"].pop("cache_read"), "tokens"),
    (lambda x: x["starts"][0].update(graded={"passed": 3, "total": 2}), "graded"),
    (lambda x: x["starts"][0].update(egress_refused={"<address>:443": 0}), "egress_refused"),
    (lambda x: x["starts"][1].update(start=1), "start"),
    (lambda x: x["starts"].append(dict(x["starts"][0], start=99)), "more than one"),
    (lambda x: x["slots"][0].update(task="no-such-task"), "task"),
    (lambda x: x["slots"][0].update(effort="max"), "effort"),
    (lambda x: x["slots"][0].update(round=6), "round"),
    (lambda x: x["slots"].append(dict(x["slots"][0], slot="duplicate")), "twice"),
    (lambda x: x.update(end={"by": "stop", "cause": None}), "cause"),
    (lambda x: x.update(end={"by": "tired", "cause": None}), "end"),
    (lambda x: x.update(label="not a label"), "label"),
    (lambda x: x.update(earlier_labels=[{"label": x["label"], "ended_by": "a ledger row"}]), "twice"),
    (lambda x: x.update(allowance={"weekly_points": "12"}), "keys"),
    (lambda x: x.update(extra=1), "keys"),
])
def test_a_record_that_does_not_fit_the_layout_is_refused(change, message):
    with pytest.raises(slot_record.RecordError, match=message):
        _load(_broken(change))


def test_a_record_that_fits_loads_joined_to_its_slot_and_its_row():
    first = _load(export({TASKS[0]: {"low": [{"row": 8, "reward": 1}], "medium": [0], "high": [0]}}))[0]
    assert {key: first[key] for key in ("task", "effort", "round", "class", "flagged", "counted", "success")} == {
        "task": TASKS[0], "effort": "low", "round": 1, "class": "observation", "flagged": True, "counted": True,
        "success": True}


def test_a_timeout_with_no_reward_is_an_observation_scored_zero():
    """D5: an observation enters k and n with the verifier's reward, 0 if the verifier gives none (row 3)."""
    first = _load(export({TASKS[0]: {"low": [{"row": 3, "reward": None}], "medium": [0], "high": [0]}}))[0]
    assert (first["counted"], first["success"]) == (True, False)


def test_a_cut_s_reward_is_never_read():
    first = _load(export({TASKS[0]: {"low": [[{"row": 10, "reward": 1}, 0]], "medium": [0], "high": [0]}}))[0]
    assert (first["class"], first["counted"], first["success"]) == ("cut", False, None)


# ---- The contamination scan's result: the launcher writes it at teardown; it names terms by SHA-256 only ---------

def _contaminated(**fields):
    return export({TASKS[0]: {"low": [{"reward": 1} | fields], "medium": [0], "high": [0]}})


def test_a_contaminated_start_names_the_sha256_of_a_frozen_term_or_of_the_canary():
    loaded = [_load(_contaminated(excluded="contaminated", contamination=[digest]))[0]["counted"]
              for digest in (TERM_SHA256, STANDINS.get("readout.contamination_scan.canary_sha256", "c" * 64))]
    assert loaded == [False, False]


@pytest.mark.parametrize("fields, message", [
    ({"excluded": "contaminated", "contamination": []}, "disagree"),
    ({"excluded": None, "contamination": [TERM_SHA256]}, "disagree"),
    ({"excluded": "contaminated", "contamination": ["0" * 64]}, "no frozen term"),
    ({"excluded": "contaminated", "contamination": ["<a frozen term>"]}, "no frozen term")])
def test_a_contamination_result_that_disagrees_or_names_no_frozen_term_is_refused(fields, message):
    with pytest.raises(slot_record.RecordError, match=message):
        _load(_contaminated(**fields))


def test_while_the_terms_are_pending_no_contamination_result_can_be_joined():
    pending = with_values(LADDER, {"readout.contamination_scan.terms": None,
                                   "readout.contamination_scan.canary_sha256": None})
    with pytest.raises(slot_record.RecordError, match="no frozen term"):
        _load(_contaminated(excluded="contaminated", contamination=[TERM_SHA256]), ladder=pending)
