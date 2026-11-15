"""The difficulty ladder's pure rules: the flat probe's table, the bisection, the choice of the 20 calibration
tasks, and the detector of an agent running the visible test itself."""

import itertools
import json
from pathlib import Path

import pytest

from experiments.seed_set import ladder
from tests.experiments.seed_set_offline_support import manifest_rows

ROWS = manifest_rows({"T0": 8, "T1": 12, "T2": 12, "T3": 12, "T4": 12, "T5": 8})
ALL = dict.fromkeys(ladder.LADDER, 8)


def counts(picked):
    found = {}
    for _, rung in picked:
        found[rung] = found.get(rung, 0) + 1
    return found


def test_probe_tasks_are_a_rungs_first_four_in_seed_order():
    assert (ladder.probe_tasks(ROWS, "T3"), ladder.probe_tasks(ROWS, "T3w")[0]) == (
        ["T3-00", "T3-01", "T3-02", "T3-03"], "T3w-00")


def test_one_tier_in_band_is_drawn_and_filled_from_the_adjacent_tier_nearer_two():
    results = {"T1": 4, "T2": 4, "T3": 2, "T4": 1, "T5": 0}
    answer = ladder.table(results)
    assert (answer, counts(ladder.choose(ROWS, answer, results, 0.0, ladder.FLAT))) == ({"chosen": "T3"}, {"T3": 12, "T4": 8})


def test_a_chosen_tiers_tasks_come_in_seed_order():
    results = {"T1": 4, "T2": 4, "T3": 2, "T4": 0, "T5": 0}
    picked = ladder.choose(ROWS, ladder.table(results), results, 0.0, ladder.FLAT)
    assert [t for t, _ in picked[:3]] == ["T3-00", "T3-01", "T3-02"]


def test_two_tiers_in_band_take_the_one_nearer_two_and_a_tie_the_harder():
    assert (ladder.table({"T1": 4, "T2": 3, "T3": 2, "T4": 1, "T5": 0}),
            ladder.table({"T1": 4, "T2": 3, "T3": 1, "T4": 0, "T5": 0})) == ({"chosen": "T3"}, {"chosen": "T3"})


def test_no_tier_in_band_takes_ten_and_ten_across_the_band():
    results = {"T1": 4, "T2": 4, "T3": 4, "T4": 0, "T5": 0}
    answer = ladder.table(results)
    assert (answer, counts(ladder.choose(ROWS, answer, results, 0.0, ladder.FLAT))) == ({"split": ["T3", "T4"]},
                                                                           {"T3": 10, "T4": 10})


def test_the_agent_checking_itself_in_80_percent_of_runs_switches_to_the_withheld_form():
    results = {"T1": 4, "T2": 4, "T3": 2, "T4": 1, "T5": 0}
    answer = ladder.table(results)
    assert (counts(ladder.choose(ROWS, answer, results, 0.80, ladder.FLAT)),
            counts(ladder.choose(ROWS, answer, results, 0.79, ladder.FLAT))) == (
        {"T3w": 12, "T4w": 8}, {"T3": 12, "T4": 8})


def test_t5_chosen_keeps_its_form_and_its_in_tree_neighbour():
    results = {"T1": 4, "T2": 4, "T3": 4, "T4": 4, "T5": 2}
    answer = ladder.table(results)
    assert (answer, counts(ladder.choose(ROWS, answer, results, 1.0, ladder.FLAT))) == ({"chosen": "T5"}, {"T5": 8, "T4": 12})


@pytest.mark.parametrize("results, miss", [({"T1": 4, "T2": 4, "T3": 3, "T4": 4, "T5": 3}, "all_easy"),
                                           ({"T1": 1, "T2": 0, "T3": 1, "T4": 0, "T5": 0}, "all_hard")])
def test_a_ladder_entirely_on_one_side_is_a_miss(results, miss):
    assert ladder.table(results) == {"miss": miss}


def test_bisection_starts_at_the_middle_and_stops_in_band():
    assert (ladder.next_rung({}, ALL), ladder.next_rung({"T2": 2}, ALL)) == ({"probe": ["T2"]}, {"chosen": "T2"})


def test_bisection_three_steps_up_ends_at_t5():
    steps = [ladder.next_rung(r, ALL) for r in ({"T2": 4}, {"T2": 4, "T4": 4}, {"T2": 4, "T4": 4, "T5": 4})]
    assert steps == [{"probe": ["T4"]}, {"probe": ["T5"]}, {"miss": "all_easy"}]


def test_bisection_down_ends_at_t0():
    steps = [ladder.next_rung(r, ALL) for r in ({"T2": 0}, {"T2": 0, "T0": 0})]
    assert steps == [{"probe": ["T0"]}, {"miss": "all_hard"}]


def test_bisection_adjacent_four_and_zero_split():
    assert (ladder.next_rung({"T2": 4, "T4": 0}, ALL), ladder.next_rung({"T2": 4, "T4": 0, "T3": 0}, ALL)) == (
        {"probe": ["T3"]}, {"split": ["T2", "T3"]})


def test_bisection_contradiction_probes_the_remaining_rungs_flat():
    assert ladder.next_rung({"T2": 0, "T4": 4}, ALL) == {"probe": ["T0", "T1", "T3", "T5"]}


def test_bisection_skips_a_rung_the_builder_could_not_fill():
    rungs = {**ALL, "T0": 0, "T3": 2}  # T1, T2, T4, T5 remain: the middle is T2
    assert (ladder.next_rung({}, rungs), ladder.next_rung({"T2": 4}, rungs)) == ({"probe": ["T2"]},
                                                                               {"probe": ["T4"]})


def test_bisection_over_the_easy_extension_orders_withheld_rungs_by_tier():
    rungs = dict.fromkeys(ladder.EASY_EXTENSION, 12)
    assert ladder.next_rung({}, rungs) == {"probe": ["T2w"]}


def test_t6_is_not_a_rung():
    assert ("T6" in ladder.LADDER + ladder.EASY_EXTENSION + ladder.HARD_EXTENSION,
            ladder.rung_tasks(manifest_rows({"T6": 1}), "T6")) == (False, [])


def test_packages_leave_out_rejected_rows_and_the_smoke_with_every_package_of_its_commit():
    rows = manifest_rows({"T2": 6, "T5": 1})
    rows[1]["rejected"] = "leak audit"
    rows[-2]["commits"] = [rows[-2]["commit"], "s" * 40]  # the T5 feature contains the smoke's commit
    assert (ladder.rung_tasks(rows, "T2"), ladder.rung_tasks(rows, "T2w")[:2], ladder.rung_tasks(rows, "T5")) == (
        ["T2-00", "T2-02", "T2-03", "T2-04", "T2-05"], ["T2w-00", "T2w-02"], [])


def test_probe_tasks_follow_the_manifest_flag():
    rows = manifest_rows({"T4": 6})
    rows[0]["probe"], rows[4]["probe"] = False, True
    assert ladder.probe_tasks(rows, "T4w") == ["T4w-01", "T4w-02", "T4w-03", "T4w-04"]


def test_a_chosen_rung_is_filled_from_one_adjacent_rung_only():
    rows = manifest_rows({"T3": 12, "T4": 6, "T5": 5})
    answer, results = {"chosen": "T5"}, {"T3": 4, "T4": 4, "T5": 2}
    assert counts(ladder.choose(rows, answer, results, 0.0, ladder.FLAT)) == {"T5": 5, "T4": 6}


def test_a_fill_tie_takes_the_easier_neighbour():  # review2 M1: T3 and T5 are both one from 2 around T4
    rows = manifest_rows({"T3": 20, "T4": 6, "T5": 5})
    results = {"T1": 4, "T2": 4, "T3": 3, "T4": 2, "T5": 1}
    answer = ladder.table(results)
    assert (answer, counts(ladder.choose(rows, answer, results, 0.0, ladder.FLAT))) == (
        {"chosen": "T4"}, {"T4": 6, "T3": 14})


def test_a_split_side_shorter_than_ten_is_topped_up_from_the_other_side_in_seed_order():
    rows = manifest_rows({"T3": 20, "T4": 6, "T5": 5})
    picked = ladder.choose(rows, {"split": ["T3", "T4"]}, {"T3": 4, "T4": 0}, 0.0, ladder.FLAT)
    assert (counts(picked), [t for t, r in picked if r == "T3"][-4:]) == (
        {"T3": 14, "T4": 6}, ["T3-10", "T3-11", "T3-12", "T3-13"])


def test_t4_and_t5_together_cannot_reach_twenty():
    rows = manifest_rows({"T3": 20, "T4": 6, "T5": 5})
    assert len(ladder.choose(rows, {"split": ["T4", "T5"]}, {"T4": 4, "T5": 0}, 0.0, ladder.FLAT)) == 11


ROWS_T0 = manifest_rows({"T0": 10, "T1": 12, "T2": 12})  # T0 is T1 with its failing assertion quoted


@pytest.mark.parametrize("answer, results, drawn", [
    ({"chosen": "T0"}, {"T0": 2, "T1": 2}, {"T0": 10, "T2": 10}),
    ({"chosen": "T1"}, {"T0": 2, "T1": 1}, {"T1": 12, "T2": 8}),
    ({"split": ["T0", "T1"]}, {"T0": 4, "T1": 0}, {"T0": 10, "T1": 2, "T2": 8})])
def test_a_hinted_twin_that_adds_no_commit_gives_way_to_t2(answer, results, drawn):
    assert counts(ladder.choose(ROWS_T0, answer, results, 0.0, ladder.HARD_EXTENSION)) == drawn


def test_a_draw_never_holds_two_packages_of_one_commit():
    picked = ladder.choose(ROWS_T0, {"split": ["T0", "T1"]}, {"T0": 4, "T1": 0}, 0.0, ladder.HARD_EXTENSION)
    commits = [row["commit"] for task, _ in picked for row in ROWS_T0 if task in (row["id"], row["withheld_id"])]
    assert len(commits) == len(set(commits)) == 20


REAL = [json.loads(line) for line in (Path(__file__).resolve().parents[2] / "experiments" / "seed_set" /
                                      "tasks.jsonl").read_text().splitlines()]
REAL_RUNGS = ladder.LADDER + ladder.EASY_EXTENSION


def test_the_real_ladder_after_ruling_1_and_the_anchor_check():  # 9a7547ed4c, its T0 and 1fd10ab4c3: anchors unstable
    sizes = {rung: len(ladder.rung_tasks(REAL, rung)) for rung in REAL_RUNGS}
    t3, smoke = ladder.rung_tasks(REAL, "T3"), [row["id"] for row in REAL if row["set"] == "smoke"]
    assert (sizes, len(t3), t3[-1], "a8ffc5997a" in t3 + ladder.rung_tasks(REAL, "T3w"), smoke) == (
        {"T0": 9, "T1": 11, "T2": 11, "T3": 19, "T4": 6, "T5": 5, "T1w": 11, "T2w": 11, "T3w": 19, "T4w": 6},
        19, "4da856acda", False, ["194ad866a1"])


def test_the_real_probe_tasks_are_each_rungs_first_four():
    assert {rung: ladder.probe_tasks(REAL, rung) == ladder.rung_tasks(REAL, rung)[:4] for rung in REAL_RUNGS} == \
        dict.fromkeys(REAL_RUNGS, True)


def test_every_real_flat_outcome_draws_twenty_unless_t4_and_t5_meet_or_the_split_is_inverted():
    """Short of 20 only when T4 and T5 are the drawn rungs (11 tasks), or when the split is inverted: its "easy"
    side T4 or T5 (3-4 passes) is harder than its "hard" side T1 or T2 (0-1 passes), which T1 and T2 cannot top up."""
    short = set()
    for passes in itertools.product(range(5), repeat=len(ladder.FLAT)):
        results = dict(zip(ladder.FLAT, passes))
        answer = ladder.table(results)
        for share in (0.0, 1.0):
            if "miss" not in answer and len(ladder.choose(REAL, answer, results, share, ladder.FLAT)) < 20:
                short.add(json.dumps(answer))
    assert short == {json.dumps(a) for a in (
        {"chosen": "T4"}, {"chosen": "T5"}, {"split": ["T4", "T5"]}, {"split": ["T5", "T4"]}, {"split": ["T4", "T1"]},
        {"split": ["T4", "T2"]}, {"split": ["T5", "T1"]}, {"split": ["T5", "T2"]})}
