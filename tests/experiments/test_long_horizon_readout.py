"""The long-horizon readout (`experiments/long_horizon_tasks/readout.py`, plan D6 and Task 6).

Every record here is constructed by the test; nothing runs an agent, a container or a provider call. The rules come
from `ladder.json`'s `readout` group; where it is pending, the tests pass stand-in values as a rehearsal does.
"""

import getpass
import hashlib
import itertools
import json
import re
import socket
import subprocess
import sys
from fractions import Fraction

import pytest

from tests.experiments.long_horizon_record_support import (EFFORTS, KIT, LABEL, LADDER, OLD, ROOT, STANDINS, TASKS,
                                                           TERM, TERM_SHA256, filled, load_kit, with_values)
from tests.experiments.long_horizon_record_support import export as _export
from tests.experiments.long_horizon_record_support import same as _same

REPORT = ROOT / "docs" / "reports" / "2026-11-13-long-horizon-benchmark-survey-and-feasibility.md"
readout = load_kit("readout")


# ---- 1. Intervals: the report's table (section 9) ---------------------------------------------------------------

def _report_table():
    """(n, k) -> (lower, upper) in percent, as section 9 of the feasibility report prints them."""
    text = REPORT.read_text().split("## 9. Arithmetic used by the plan", 1)[1].split("\n## ", 1)[0]
    table = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells[0].isdigit():
            continue
        for k, cell in enumerate(cells[1:]):
            if cell:
                lower, upper = re.fullmatch(r"([\d.]+)–([\d.]+)%", cell).groups()
                table[int(cells[0]), k] = (float(lower), float(upper))
    return table


def test_the_report_table_holds_every_cell_count_and_the_pooled_counts():
    table = _report_table()
    assert {(5, k) for k in range(6)} | {(15, k) for k in range(6)} <= set(table)


@pytest.mark.parametrize("n, k", sorted(_report_table()))
def test_the_exact_interval_matches_the_report_s_table(n, k):
    lower, upper = readout.interval(k, n, 0.95)
    assert (round(100 * lower, 1), round(100 * upper, 1)) == _report_table()[n, k]


def test_the_interval_is_the_whole_range_for_an_empty_cell():
    assert readout.interval(0, 0, 0.95) == (0.0, 1.0)


# ---- 2. Cell and pooled labels; the band effort ----------------------------------------------------------------

RULES = LADDER["readout"]


@pytest.mark.parametrize("k, label", [(0, "floor"), (1, "screened in"), (2, "screened in"), (3, "above"),
                                      (4, "above"), (5, "above")])
def test_a_cell_of_five_is_labelled_by_its_successes(k, label):
    assert readout.cell_label(k, 5, RULES["cell"]) == label


@pytest.mark.parametrize("n", range(5))
def test_a_cell_under_five_is_incomplete_whatever_its_successes(n):
    assert {readout.cell_label(k, n, RULES["cell"]) for k in range(n + 1)} == {"incomplete"}


def test_a_cell_over_five_is_refused():
    with pytest.raises(readout.ReadoutError, match="more than 5"):
        readout.cell_label(1, 6, RULES["cell"])


@pytest.mark.parametrize("K, n, label", [(0, 15, "floor"), (1, 15, "screened in"), (5, 15, "screened in"),
                                         (6, 15, "above the band"), (15, 15, "above the band")])
def test_at_15_attempts_the_pooled_label_reads_k_over_n_against_1_15_and_1_3_inclusive(K, n, label):
    assert readout.pooled_label(K, n, RULES["pooled"]) == label


@pytest.mark.parametrize("K, n", [(4, 14), (1, 14), (0, 14), (1, 2), (0, 0)])
def test_with_fewer_than_15_attempts_a_task_is_not_screened(K, n):
    """Coordinator ruling R4: the screen is applied only at the planned count; the task is neither in nor out."""
    assert readout.pooled_label(K, n, RULES["pooled"]) == f"not screened: {n} of 15 attempts"


ALL_TRIPLES = [dict(zip(EFFORTS, ks)) for ks in itertools.product(range(6), repeat=3)]
SCREENED = [t for t in ALL_TRIPLES if 1 <= sum(t.values()) <= 5]


def _cells(triple):
    return {effort: (k, 5) for effort, k in triple.items()}


def test_the_screen_admits_the_55_triples_whose_pooled_count_is_1_to_5_of_15():
    admitted = [t for t in ALL_TRIPLES if readout.pooled_label(sum(t.values()), 15, RULES["pooled"]) == "screened in"]
    assert admitted == SCREENED and len(SCREENED) == 55


@pytest.mark.parametrize("triple", SCREENED, ids=lambda t: "-".join(map(str, t.values())))
def test_the_band_effort_is_defined_for_every_screened_in_pattern(triple):
    band = readout.band_effort(_cells(triple), RULES)
    chosen = triple[band["effort"]]
    others = [(abs(k - 1), EFFORTS.index(e)) for e, k in triple.items() if k >= 1]
    assert (chosen >= 1, (abs(chosen - 1), EFFORTS.index(band["effort"])), band["flagged"], band["label"]) == (
        True, min(others), chosen >= 3, "noisy, one cell of five")


@pytest.mark.parametrize("triple, effort, flagged", [((0, 0, 1), "high", False), ((2, 1, 0), "medium", False),
                                                     ((1, 0, 1), "low", False), ((0, 3, 2), "high", False),
                                                     ((0, 3, 0), "medium", True), ((3, 0, 0), "low", True),
                                                     ((0, 0, 5), "high", True), ((2, 0, 2), "low", False)])
def test_the_band_effort_is_closest_to_one_in_five_with_ties_to_the_lower_level(triple, effort, flagged):
    band = readout.band_effort(_cells(dict(zip(EFFORTS, triple))), RULES)
    assert (band["effort"], band["flagged"]) == (effort, flagged)


@pytest.mark.parametrize("triple", [t for t in ALL_TRIPLES if t not in SCREENED],
                         ids=lambda t: "-".join(map(str, t.values())))
def test_the_band_effort_is_refused_for_every_pattern_the_screen_does_not_admit(triple):
    with pytest.raises(readout.ReadoutError, match="not screened in"):
        readout.band_effort(_cells(triple), RULES)


# ---- 3. The effort verdict and the bound on the fall, on constructed tables --------------------------------------

SEEDED = RULES | {"fall_bound": RULES["fall_bound"] | {"seed": 20261114}}


def _tasks(*groups, triples=5):
    """Per-task successes over complete triples: groups of (number of tasks, (low, medium, high) successes)."""
    tasks, count = {}, 0
    for size, successes in groups:
        for _ in range(size):
            count += 1
            tasks[f"t{count:02}"] = {"triples": triples, "successes": dict(zip(EFFORTS, successes))}
    return tasks


def _test(tasks):
    return readout.effort_test(tasks, EFFORTS, SEEDED)


@pytest.mark.parametrize("ds, below, above", [([1, 1, 1], 1, Fraction(1, 8)),
                                              ([2, 1], 1, Fraction(1, 4)),
                                              ([1, -1], Fraction(3, 4), Fraction(3, 4)),
                                              ([], 1, 1)])
def test_the_sign_flip_test_is_exact(ds, below, above):
    assert readout.sign_flip_p(ds) == (below, above)


def test_a_rising_table_rises_and_its_bound_on_the_fall_is_below_zero():
    result = _test(_tasks((16, (0, 1, 2))))
    assert (result["verdict"], result["fall_bound"] < 0) == ("rises", True)


def test_a_flat_table_is_not_resolved_and_its_bound_on_the_fall_is_zero():
    result = _test(_tasks((16, (1, 1, 1))))
    assert (result["verdict"], result["fall_bound"]) == ("not resolved", 0.0)


def test_a_fall_within_the_bound_is_not_resolved_and_the_bound_covers_it():
    """Three tasks fall by one success of five (p = 1/8): no fall is ruled out above the bound, which covers 3.75."""
    result = _test(_tasks((3, (1, 1, 0)), (13, (1, 1, 1))))
    assert (result["verdict"], result["differences"]["high-low"]["p_below"], result["fall_bound"] >= 3.75) == (
        "not resolved", Fraction(1, 8), True)


def test_a_fall_beyond_the_test_s_threshold_falls():
    result = _test(_tasks((6, (1, 1, 0)), (10, (1, 1, 1))))
    assert (result["verdict"], result["differences"]["high-low"]["p_below"]) == ("falls", Fraction(1, 64))


def test_an_adjacent_pair_falls_at_p_one_in_64_but_not_at_one_in_32():
    """The adjacent pairs are held to 0.025: six tasks a step down medium from low falls, five do not."""
    six, five = _test(_tasks((6, (1, 0, 1)), (10, (1, 1, 1)))), _test(_tasks((5, (1, 0, 1)), (11, (1, 1, 1))))
    assert (six["verdict"], five["verdict"], five["differences"]["medium-low"]["p_below"]) == (
        "falls", "not resolved", Fraction(1, 32))


def test_rises_admits_ties_in_the_pooled_order():
    result = _test(_tasks((6, (0, 0, 1)), (10, (1, 1, 1))))
    assert (result["verdict"], result["pooled"]) == ("rises", {"low": 10, "medium": 10, "high": 16})


def test_rises_needs_the_pooled_order_whatever_high_against_low_shows():
    result = _test(_tasks((6, (0, 0, 1)), (2, (1, 0, 1)), (8, (1, 1, 1))))
    assert (result["differences"]["high-low"]["p_above"] <= Fraction(1, 20), result["verdict"]) == (
        True, "not resolved")


def test_tasks_with_no_difference_do_not_move_the_p_value():
    """Ties within a task (d_i = 0) leave the exact p unchanged: five rising tasks give 1/32 among 11 flat or none."""
    alone, among = _test(_tasks((5, (0, 0, 1)))), _test(_tasks((5, (0, 0, 1)), (11, (2, 2, 2))))
    assert alone["differences"]["high-low"]["p_above"] == among["differences"]["high-low"]["p_above"] == (
        Fraction(1, 32))


def test_a_task_short_of_five_triples_weighs_by_its_own_triples_in_the_bound():
    """Every task falls by one success: 20 points over five triples, 25 over four; every resample lies between."""
    short = _tasks((15, (1, 1, 0))) | _tasks((1, (1, 1, 0)), triples=4)
    short["t01-short"] = short.pop("t01")
    result = _test(short)
    assert 20.0 <= result["fall_bound"] <= 25.0


def test_the_bound_is_fixed_by_its_seed():
    tasks = _tasks((4, (1, 1, 0)), (3, (0, 1, 1)), (9, (2, 1, 2)))
    assert _test(tasks)["fall_bound"] == _test(dict(reversed(tasks.items())))["fall_bound"]


def test_no_complete_triple_leaves_the_verdict_not_resolved_and_no_bound():
    result = _test({})
    assert (result["verdict"], result["fall_bound"], result["triples"]) == ("not resolved", None, 0)


# ---- Constructed records: the export of slot_record.py's layout (tests/experiments/long_horizon_record_support.py)

def _compute(export, ladder=LADDER, standins=STANDINS):
    return readout.compute(ladder, export, standins)


# ---- 4. A ceiling stop leaves partial rounds out of complete triples ---------------------------------------------

PARTIAL = {TASKS[0]: _same([1, 0, 0, 0, 0]), TASKS[1]: _same([0, 1, 0, 0, 0]), TASKS[2]: _same([0, 0, 0, 0, "-"]),
           TASKS[3]: {"low": [0, 0, 0, 0, 1], "medium": [0, 0, 0, 0, 0], "high": [0, 0, 0, 0, "-"]}}


def test_a_ceiling_stop_leaves_the_dropped_and_the_partial_block_out_of_complete_triples():
    effort = _compute(_export(PARTIAL))["effort"]
    assert (effort["triples"], {task: entry["triples"] for task, entry in effort["per_task"].items()}) == (
        18, {TASKS[0]: 5, TASKS[1]: 5, TASKS[2]: 4, TASKS[3]: 4})


def test_the_partial_block_s_success_enters_its_cell_and_not_the_effort_test():
    result = _compute(_export(PARTIAL))
    low = result["tasks"][TASKS[3]]["cells"]["low"]
    assert ((low["k"], low["n"]), result["effort"]["pooled"]) == ((1, 5), {"low": 2, "medium": 2, "high": 2})


def test_the_short_cells_of_the_partial_block_are_incomplete_and_printed_with_their_count():
    cells = _compute(_export(PARTIAL))["tasks"][TASKS[3]]["cells"]
    assert {e: (c["n"], c["label"]) for e, c in cells.items()} == {"low": (5, "screened in"), "medium": (5, "floor"),
                                                                   "high": (4, "incomplete")}


# ---- Pending readout fields: refused, unless a rehearsal gives stand-ins and is stamped ---------------------------

def test_a_final_readout_is_refused_while_a_readout_field_is_pending_and_names_each():
    with pytest.raises(readout.ReadoutError) as caught:
        _compute(_export(PARTIAL), standins=None)
    assert all(field in str(caught.value) for field in STANDINS) and STANDINS


def test_a_rehearsal_takes_its_stand_ins_and_is_stamped():
    assert _compute(_export(PARTIAL))["rehearsal"] is True


def test_a_rehearsal_missing_a_stand_in_is_refused():
    with pytest.raises(readout.ReadoutError, match="stand-in"):
        _compute(_export(PARTIAL), standins=dict(list(STANDINS.items())[1:]))


def test_a_stand_in_for_a_field_that_is_not_pending_is_refused():
    with pytest.raises(readout.ReadoutError, match="not pending"):
        _compute(_export(PARTIAL), standins=STANDINS | {"readout.cell.complete_n": 3})


def test_a_final_readout_of_a_filled_criterion_is_not_stamped():
    assert _compute(_export(PARTIAL), ladder=filled(), standins=None)["rehearsal"] is False


# ---- 5. Exclusions are listed and never scored zero ----------------------------------------------------------------

EXCLUDING = {TASKS[0]: {
    "low": [[{"row": 10, "reward": 1}, 1], 1, {"row": 15, "reward": 1}, [{"row": 1}, 0],
            {"reward": 1, "excluded": "contaminated", "contamination": [TERM_SHA256]}],
    "medium": [{"row": 13}, {"row": 4}, {"row": 2}, {"excluded": "no reward after regrades"},
               {"row": 9, "reward": 0}],
    "high": [0, 0, 0, 0, {"reward": 0, "excluded": "indeterminate"}]}}


def test_every_excluded_class_of_d5_and_every_excluded_observation_is_listed():
    listed = _compute(_export(EXCLUDING))["listed"]["exclusions"]
    assert sorted((e["effort"], e["round"], e["class"], e["reason"]) for e in listed) == sorted([
        ("low", 1, "cut", "Usage limit"), ("low", 3, "infrastructure_failure", "Provider fault, after the CLI's ten "
                                         "retries; or the passthrough refused under load or timing"),
        ("low", 4, "pre_session_failure", "Before a session"), ("low", 5, "observation", "contaminated"),
        ("medium", 1, "stop", LADDER["classification"]["rows"][12]["ending"]),
        ("medium", 2, "infrastructure_failure", "The host, Podman, the passthrough or the launcher died"),
        ("medium", 3, "stop", "The CLI read no credential, or the harness found none"),
        ("medium", 4, "observation", "no reward after regrades"), ("high", 5, "observation", "indeterminate")])


def test_an_excluded_attempt_enters_neither_k_nor_n():
    """A cut or an infrastructure failure with a reward of 1, or a contaminated pass, is never a success; a stop, a
    pre-session failure or an attempt with no reward after its regrades is never a failure scored zero."""
    cells = _compute(_export(EXCLUDING))["tasks"][TASKS[0]]["cells"]
    assert {e: (c["k"], c["n"]) for e, c in cells.items()} == {"low": (2, 3), "medium": (0, 1), "high": (0, 4)}


def test_a_flagged_observation_is_listed_and_counted():
    result = _compute(_export(EXCLUDING))
    assert ([(f["effort"], f["round"], f["ending"]) for f in result["listed"]["flags"]],
            result["tasks"][TASKS[0]]["cells"]["medium"]["n"]) == ([("medium", 5, "Output limit")], 1)


def test_an_excluded_round_leaves_its_triple_incomplete():
    assert _compute(_export(EXCLUDING))["effort"]["per_task"] == {}


# ---- 6. Cuts are counted per effort; the pilot's attempts are marked ----------------------------------------------

CUT = {"row": 10, "reward": None}
PILOT_TASK = LADDER["schedule"]["pilot"]["task"]
CUTS = {TASKS[0]: {"low": [[CUT, CUT, 1], 0], "medium": [[CUT, 0], 0], "high": [0, 0]},
        TASKS[1]: {"low": [0, 0], "medium": [0, 0], "high": [0, [CUT, 1]]},
        PILOT_TASK: {"low": [1, 0], "medium": [0, 0], "high": [0, 0]}}
PILOT = {(PILOT_TASK, effort, 1) for effort in EFFORTS}


def test_cuts_are_counted_per_effort():
    assert _compute(_export(CUTS))["listed"]["cuts"] == {"low": 2, "medium": 1, "high": 1}


def test_a_slot_cut_and_run_again_counts_once_in_its_cell():
    assert _compute(_export(CUTS))["tasks"][TASKS[0]]["cells"]["low"] | {"interval": None} == {
        "k": 1, "n": 2, "interval": None, "label": "incomplete"}


def test_the_pilot_s_three_attempts_are_marked_and_are_observations_of_the_ladder():
    result = _compute(_export(CUTS, pilot=PILOT))
    assert ([(p["task"], p["effort"], p["round"], p["class"]) for p in result["listed"]["pilot"]],
            result["tasks"][PILOT_TASK]["cells"]["low"]["k"]) == (
        [(PILOT_TASK, effort, 1, "observation") for effort in EFFORTS], 1)


def test_no_attempt_is_marked_as_the_pilot_s_when_no_slot_is():
    assert _compute(_export(CUTS))["listed"]["pilot"] == []


# ---- 7. Two configuration labels: never pooled; the earlier one printed apart; short cells with their count ---------

def _relabelled(reward):
    return {"reward": reward, "label": OLD}


LABELLED = {TASKS[0]: _same([_relabelled(1), _relabelled(1), 0, 0, 0]),
            TASKS[1]: _same([_relabelled(0), _relabelled(1), 1, 0, 0])}


def test_observations_under_two_labels_are_never_pooled_in_a_cell_or_a_task():
    result = _compute(_export(LABELLED, earlier=(OLD,)))
    task = result["tasks"][TASKS[0]]
    assert ((task["cells"]["low"]["k"], task["cells"]["low"]["n"]), (task["pooled"]["K"], task["pooled"]["n"]),
            task["pooled"]["label"], result["effort"]["triples"]) == (
        (0, 3), (0, 9), "not screened: 9 of 15 attempts", 6)


def test_an_earlier_label_s_observations_are_counted_apart_with_its_label_and_ledger_row():
    earlier = _compute(_export(LABELLED, earlier=(OLD,)))["earlier"]
    assert [(e["label"], e["ended_by"], e["cells"][TASKS[0]]["low"]["k"], e["cells"][TASKS[0]]["low"]["n"])
            for e in earlier] == [(OLD, f"ledger row ending {OLD[:8]}", 2, 2)]


def _rules_only(result):
    return {key: value for key, value in result.items() if key != "earlier"}


def test_an_earlier_label_s_observations_enter_no_rule():
    flipped = {task: {e: [o | {"reward": 1 - o["reward"]} if isinstance(o, dict) else o for o in outcomes]
                      for e, outcomes in by.items()} for task, by in LABELLED.items()}
    assert _rules_only(_compute(_export(LABELLED, earlier=(OLD,)))) == _rules_only(
        _compute(_export(flipped, earlier=(OLD,))))


def _section(text, heading):
    return text.split(f"## {heading}", 1)[1].split("\n## ", 1)[0]


def test_the_earlier_label_is_printed_in_a_table_of_its_own():
    text = readout.render(_compute(_export(LABELLED, earlier=(OLD,))))
    assert (OLD in _section(text, "Earlier configuration labels"), "2 of 2" in _section(text, "Tasks"),
            "2 of 2" in _section(text, "Earlier configuration labels")) == (True, False, True)


def test_a_short_cell_is_printed_with_its_count_and_labelled_incomplete():
    row = next(line for line in _section(readout.render(_compute(_export(LABELLED, earlier=(OLD,)))), "Tasks")
               .splitlines() if line.startswith(f"| {TASKS[0]} "))
    assert row.count("0 of 3") == 3 and row.count("incomplete") == 3


# ---- 8. Cost per effort; the graded outcome and the allowance are printed and enter no rule ------------------------

def _graded(reward, passed, total=10):
    return {"reward": reward, "graded": {"passed": passed, "total": total}}


GRADED = {TASKS[0]: {"low": [_graded(1, 10), _graded(0, 4)], "medium": [_graded(0, 7), _graded(0, 2)],
                     "high": [_graded(0, 0), 1]},
          TASKS[1]: _same([0, 1])}
ALLOWANCE = {"weekly_points": 12.5, "readings": "ledger rows of 2026-11-20 and 2026-11-27"}


def test_the_graded_outcome_is_summed_per_task_and_effort_where_the_verifier_reports_it():
    graded = _compute(_export(GRADED))["graded"]
    assert (graded[TASKS[0]]["low"], graded[TASKS[0]]["high"], graded[TASKS[1]]) == (
        {"passed": 14, "total": 20, "observations": 2}, {"passed": 0, "total": 10, "observations": 1},
        "pass or fail only")


def test_the_graded_outcome_is_printed_beside_the_counts():
    section = _section(readout.render(_compute(_export(GRADED))), "Graded outcome")
    assert ("14 of 20 sub-tests" in section, "pass or fail only" in section) == (True, True)


def _without(result, *keys):
    return {key: value for key, value in result.items() if key not in keys}


def test_the_graded_outcome_enters_no_rule():
    regraded = {task: {e: [o | {"graded": {"passed": 0, "total": 99}} if isinstance(o, dict) else o for o in outcomes]
                       for e, outcomes in by.items()} for task, by in GRADED.items()}
    assert _without(_compute(_export(GRADED)), "graded") == _without(_compute(_export(regraded)), "graded")


def test_the_allowance_is_printed_in_all_and_per_priced_dollar():
    result = _compute(_export(GRADED, allowance=ALLOWANCE))
    section = _section(readout.render(result), "Allowance")
    assert (result["allowance"]["usd"], result["allowance"]["points_per_usd"], "12.5" in section,
            "ledger rows of 2026-11-20" in section) == (12.0, 12.5 / 12.0, True, True)


def test_the_allowance_enters_no_rule():
    assert _without(_compute(_export(GRADED, allowance=ALLOWANCE)), "allowance") == _without(
        _compute(_export(GRADED)), "allowance")


def test_cost_per_success_takes_every_start_at_its_level_cut_starts_included():
    cost = _compute(_export({TASKS[0]: {"low": [[CUT | {"usd": 2.0}, 1], 0], "medium": [0, 0],
                                        "high": [[{"row": 1, "usd": 0.0}, 1], {"row": 15}]}}))["cost"]["per_effort"]
    assert ((cost["low"]["usd_all_starts"], cost["low"]["successes"], cost["low"]["usd_per_success"]),
            (cost["medium"]["usd_per_success"]), (cost["high"]["starts"], cost["high"]["mean_usd"])) == (
        (4.0, 1, 4.0), None, (2, 1.0))


def test_a_level_is_dominated_only_by_one_that_beats_it_on_the_test_and_costs_less():
    beaten = _same([0, 0]) | {"high": [{"reward": 1, "usd": 0.5}, {"reward": 1, "usd": 0.5}]}
    cheap = _compute(_export({task: beaten for task in TASKS[:5]}))["cost"]["dominated"]
    dear = {task: beaten | {"high": [{"reward": 1, "usd": 3.0}, {"reward": 1, "usd": 3.0}]} for task in TASKS[:5]}
    assert (cheap["low"], cheap["high"], _compute(_export(dear))["cost"]["dominated"]["low"]) == (
        {"verdict": "dominated", "by": "high"}, {"verdict": "not resolved", "by": None},
        {"verdict": "not resolved", "by": None})


# ---- 9. A stop readout prints no placement ---------------------------------------------------------------------

STOP = {"by": "stop", "cause": "a vendor 401 (D5 row 14); ledger row of 2026-11-21"}
STOPPED = {TASKS[0]: _same([1, 0, 0, 0, 0]), TASKS[1]: _same([0, 0, 0, 0, 0]), TASKS[2]: _same([1, 1, 1, 1, 1]),
           TASKS[3]: {"low": [0, {"row": 14}], "medium": [0, "-"], "high": [0, "-"]}}
FAMILY = {task: STOPPED[task] for task in TASKS[:3]}
PLACEMENT_WORDS = ("screened in", "floor", "above", "incomplete", "noisy", "rises", "falls", "not resolved",
                   "dominated")


def test_a_stop_readout_computes_no_label_band_effort_verdict_or_dominance():
    result = _compute(_export(STOPPED, end=STOP))
    labels = [c.get("label") for t in result["tasks"].values() for c in [*t["cells"].values(), t["pooled"]]]
    assert (set(labels), {t["band_effort"] for t in result["tasks"].values()}, sorted(result["effort"]),
            result["cost"]["dominated"]) == ({None}, {None}, ["fall_bound", "per_task", "tasks", "triples"], None)


def test_a_stop_readout_reports_the_bound_on_the_fall_over_the_complete_triples_it_has():
    """D6 always reports the bound, which places nothing (coordinator ruling R2, 2026-11-14)."""
    result = _compute(_export(STOPPED, end=STOP))
    stopped, placed = result["effort"], _compute(_export(STOPPED))["effort"]
    assert (stopped["triples"], stopped["fall_bound"] == placed["fall_bound"],
            "over 16 complete triples; no placement is made" in _section(readout.render(result), "Effort test")) == (
        16, True, True)


def test_a_stop_readout_with_no_complete_triple_says_there_is_none():
    result = _compute(_export({TASKS[0]: {"low": [1], "medium": [{"row": 13}], "high": ["-"]}}, end=STOP))
    assert (result["effort"]["fall_bound"], "no complete triple" in _section(readout.render(result), "Effort test")) \
        == (None, True)


def test_a_stop_readout_prints_its_counts_and_its_cause_and_no_placement():
    text = readout.render(_compute(_export(STOPPED, end=STOP)))
    placed = _section(text, "Tasks") + _section(text, "Effort test") + _section(text, "Cost per effort")
    assert (STOP["cause"] in text, "1 of 5" in placed, [w for w in PLACEMENT_WORDS if w in placed]) == (True, True, [])


def test_the_same_records_without_the_stop_are_placed():
    text = readout.render(_compute(_export(STOPPED)))
    assert [w for w in ("screened in", "floor", "above") if w in _section(text, "Tasks")] == [
        "screened in", "floor", "above"]


# ---- 10. family.json: criterion, label and digests; only from a complete, non-stop readout; a pure function -------

TASKS_DOC = json.loads((KIT / "tasks.json").read_text())
CRITERION = "e" * 64
DIGESTS = {t["name"].split("/", 1)[1]: (t["digest_4_1_0"], t["environment_image"], t["verifier_image"])
           for t in TASKS_DOC["tasks"]}


def _family(export, **kwargs):
    return readout.family(_compute(export, **kwargs), CRITERION, TASKS_DOC)


def _dropped(*tasks):
    return [{"task": task, "reason": f"ledger row dropping {task}"} for task in tasks]


def test_family_json_names_the_criterion_the_configuration_label_and_each_task_s_digests():
    family = _family(_export(FAMILY))
    listed = {t["task"]: (t["digests"]["digest_4_1_0"], t["digests"]["environment_image"],
                          t["digests"]["verifier_image"]) for group in family["tasks"].values() for t in group}
    assert (family["criterion_sha256"], family["label"], family["configuration"]["model"], listed) == (
        CRITERION, LABEL, "claude-haiku-5-5", {task: DIGESTS[task] for task in FAMILY})


def test_family_json_lists_the_tasks_by_pooled_label_with_their_counts_and_band_effort_and_the_verdict():
    family = _family(_export(FAMILY))
    screened = family["tasks"]["screened in"][0]
    assert ({label: [t["task"] for t in group] for label, group in family["tasks"].items()},
            screened["band_effort"]["effort"], screened["cells"]["low"]["k"], family["effort"]["verdict"],
            isinstance(family["effort"]["fall_bound"], float)) == (
        {"screened in": [TASKS[0]], "floor": [TASKS[1]], "above the band": [TASKS[2]], "dropped": []},
        "low", 1, "not resolved", True)


@pytest.mark.parametrize("end", [None, STOP], ids=["in progress", "stop"])
def test_family_json_is_written_only_from_a_complete_readout_that_did_not_end_in_a_stop(end):
    with pytest.raises(readout.ReadoutError, match="family.json"):
        _family(_export(FAMILY, end=end))


def _bytes(export):
    return readout.family_bytes(_family(export))


def test_family_json_is_the_same_bytes_from_the_same_records_and_holds_no_time_path_host_or_user():
    once, again = _bytes(_export(FAMILY)), _bytes(_export(FAMILY))
    text = once.decode()
    machine = [getpass.getuser(), socket.gethostname(), str(ROOT), "/tmp", "/home"]
    assert (once == again, [m for m in machine if m in text], re.findall(r"\d{4}-\d\d-\d\dT\d\d", text)) == (
        True, [], [])


def test_a_rehearsal_stamps_family_json_and_the_readout_and_a_final_readout_stamps_neither():
    rehearsal, final = _compute(_export(FAMILY)), _compute(_export(FAMILY), ladder=filled(), standins=None)
    stamps = [readout.family(r, CRITERION, TASKS_DOC)["rehearsal"] for r in (rehearsal, final)]
    texts = ["REHEARSAL" in readout.render(r) for r in (rehearsal, final)]
    assert (stamps, texts) == ([True, False], [True, False])


def test_a_task_missing_from_tasks_json_is_an_error():
    with pytest.raises(readout.ReadoutError, match="tasks.json"):
        readout.family(_compute(_export(FAMILY)), CRITERION, {"tasks": TASKS_DOC["tasks"][1:]})


# ---- The command: python -I readout.py <export> [--rehearsal <stand-ins>] [--family <path>] ----------------------

def _write(path, value):
    path.write_text(json.dumps(value))
    return path


def test_the_command_prints_the_readout_and_writes_family_json_in_a_rehearsal(tmp_path):
    export, standins = _write(tmp_path / "export.json", _export(FAMILY)), _write(tmp_path / "s.json", STANDINS)
    done = subprocess.run([sys.executable, "-I", str(KIT / "readout.py"), str(export), "--rehearsal", str(standins),
                           "--family", str(tmp_path / "family.json")],
                          capture_output=True, text=True, cwd=ROOT, env={"PATH": "/nonexistent"})
    family = json.loads((tmp_path / "family.json").read_text())
    assert (done.returncode, "REHEARSAL" in done.stdout, family["rehearsal"], family["label"]) == (0, True, True, LABEL)


def test_the_command_refuses_a_final_readout_while_a_readout_field_is_pending(tmp_path, capsys):
    code = readout.main([str(_write(tmp_path / "export.json", _export(STOPPED))), "--family",
                         str(tmp_path / "family.json")])
    err = capsys.readouterr().err
    assert (code, all(f in err for f in STANDINS), (tmp_path / "family.json").exists()) == (2, True, False)


def test_the_command_writes_no_family_json_for_a_readout_in_progress(tmp_path, capsys):
    export, standins = _write(tmp_path / "e.json", _export(STOPPED, end=None)), _write(tmp_path / "s.json", STANDINS)
    code = readout.main([str(export), "--rehearsal", str(standins), "--family", str(tmp_path / "family.json")])
    assert (code, "in progress" in capsys.readouterr().err, (tmp_path / "family.json").exists()) == (2, True, False)


def test_a_final_readout_reads_the_criterion_of_its_label_only():
    """The manifest whose SHA-256 is the label must hold the SHA-256 of the ladder.json the readout applies."""
    ladder = b'{"criterion": "frozen"}'
    manifest = json.dumps({"files": {readout.LADDER_PATH: hashlib.sha256(ladder).hexdigest()}}).encode()
    label = hashlib.sha256(manifest).hexdigest()
    refusals = []
    for args in ((ladder, manifest, "f" * 64), (b'{"criterion": "edited"}', manifest, label)):
        with pytest.raises(readout.ReadoutError) as caught:
            readout.bound(*args)
        refusals.append(str(caught.value).split(":")[0])
    assert (readout.bound(ladder, manifest, label), refusals) == (
        None, ["the label is not this manifest's SHA-256", "ladder.json is not the manifest's"])


# ---- D6's remaining lists: refused connections per attempt; no public figure -------------------------------------

def test_refused_connections_are_listed_per_attempt_and_exclude_nothing():
    table = {TASKS[0]: {"low": [{"reward": 1, "egress_refused": {"<address>:443": 3}}], "medium": [0], "high": [0]}}
    result = _compute(_export(table))
    assert ([(e["effort"], e["refused"]) for e in result["listed"]["egress"]],
            result["tasks"][TASKS[0]]["cells"]["low"]["k"], "<address>:443: 3" in readout.render(result)) == (
        [("low", {"<address>:443": 3})], 1, True)


def test_no_public_figure_is_read_or_printed():
    result = _compute(_export(FAMILY))
    public = {str(task["public_mean_usd_at_max"]) for task in LADDER["tasks"]["list"]}
    printed = readout.render(result) + readout.family_bytes(readout.family(result, CRITERION, TASKS_DOC)).decode()
    assert ("public" in printed, sorted(p for p in public if f" {p} " in printed or f"USD {p}" in printed)) == (
        False, [])


def test_a_contaminated_attempt_is_listed_with_the_term_s_sha256_and_never_the_term():
    result = _compute(_export(EXCLUDING))
    listed = [e["contamination"] for e in result["listed"]["exclusions"] if e["reason"] == "contaminated"]
    printed = readout.render(result)
    assert (listed, TERM_SHA256 in printed, TERM in printed) == ([[TERM_SHA256]], True, False)


def test_the_dominance_threshold_is_read_from_its_own_field_of_the_readout_group():
    """Coordinator ruling R3: readout.cost.dominated_p_at_most, and no other field, sets the level (p = 1/32 here)."""
    beaten = _same([0, 0]) | {"high": [{"reward": 1, "usd": 0.5}, {"reward": 1, "usd": 0.5}]}
    table = {task: beaten for task in TASKS[:5]}
    strict = readout.compute(with_values(LADDER, {"readout.cost.dominated_p_at_most": 0.03}), _export(table), STANDINS)
    loose_test = with_values(LADDER, {"readout.effort_test.rises.p_at_most": 0.01})
    assert (LADDER["readout"]["cost"]["dominated_p_at_most"], strict["cost"]["dominated"]["low"]["verdict"],
            readout.compute(loose_test, _export(table), STANDINS)["cost"]["dominated"]["low"]["verdict"]) == (
        0.05, "not resolved", "dominated")



# ---- Ruling R4: the screen is applied at 15 attempts only; family.json waits for every task to be screened or dropped

def test_a_task_with_one_effort_short_after_a_ceiling_stop_is_not_screened_and_printed_with_its_count():
    result = _compute(_export(PARTIAL))
    task = result["tasks"][TASKS[3]]
    row = next(line for line in _section(readout.render(result), "Tasks").splitlines()
               if line.startswith(f"| {TASKS[3]} "))
    short = "not screened: 14 of 15 attempts"
    assert (task["pooled"]["label"], task["band_effort"], "1 of 14 (" in row, short in row) == (short, None, True, True)


def test_a_task_at_15_attempts_is_screened():
    assert _compute(_export(PARTIAL))["tasks"][TASKS[0]]["pooled"]["label"] == "screened in"


def test_family_json_is_refused_while_a_task_is_neither_screened_at_15_nor_dropped():
    with pytest.raises(readout.ReadoutError) as caught:
        _family(_export(PARTIAL))
    assert [task for task in TASKS[:4] if task in str(caught.value)] == [TASKS[2], TASKS[3]]


def test_family_json_lists_a_dropped_task_with_its_reason_and_outside_the_family():
    family = readout.family(readout.compute(LADDER, _export(PARTIAL), STANDINS, _dropped(TASKS[2], TASKS[3])),
                            CRITERION, TASKS_DOC)
    assert ({label: [t["task"] for t in group] for label, group in family["tasks"].items()},
            [t["pooled"]["reason"] for t in family["tasks"]["dropped"]]) == (
        {"screened in": [TASKS[0], TASKS[1]], "floor": [], "above the band": [], "dropped": [TASKS[2], TASKS[3]]},
        [f"ledger row dropping {TASKS[2]}", f"ledger row dropping {TASKS[3]}"])


@pytest.mark.parametrize("dropped, message", [
    (_dropped("no-such-task"), "not a task"), (_dropped(TASKS[2], TASKS[2]), "twice"),
    ([{"task": TASKS[2], "reason": ""}], "reason"), ([{"task": TASKS[2]}], "keys")])
def test_a_drop_that_names_no_task_of_the_tranche_or_no_reason_is_refused(dropped, message):
    with pytest.raises((readout.ReadoutError, readout.slot_record.RecordError), match=message):
        readout.compute(LADDER, _export(PARTIAL), STANDINS, dropped)


def test_the_command_takes_the_drops_and_writes_family_json(tmp_path):
    paths = [_write(tmp_path / name, value) for name, value in (
        ("e.json", _export(PARTIAL)), ("s.json", STANDINS), ("d.json", _dropped(TASKS[2], TASKS[3])))]
    code = readout.main([str(paths[0]), "--rehearsal", str(paths[1]), "--dropped", str(paths[2]), "--family",
                         str(tmp_path / "family.json")])
    family = json.loads((tmp_path / "family.json").read_text())
    assert (code, [t["task"] for t in family["tasks"]["dropped"]]) == (0, [TASKS[2], TASKS[3]])


# ---- Ruling R5: the bootstrap is frozen as built; a pinned bound catches a change of generator or order --------------

PINNED = {f"t{i:02}": {"triples": t, "successes": {"low": low, "medium": 0, "high": high}}
          for i, (t, low, high) in enumerate([(5, 2, 0), (5, 1, 1), (4, 1, 0), (3, 0, 1), (5, 3, 1), (2, 1, 0),
                                              (5, 0, 2), (4, 2, 2), (3, 1, 0), (5, 1, 3), (4, 0, 0), (5, 2, 1)])}


def test_the_bound_on_the_fall_is_pinned_for_one_table_and_one_seed():
    """random.Random(seed), tasks in name order, 10,000 resamples, the 9,500th smallest fall. With the tasks in the
    reverse order the same seed gives 20.45...; with seed 20261115, 20.41..."""
    rule = RULES["fall_bound"] | {"seed": 20261114}
    assert (rule["resamples"], readout.fall_bound(PINNED, "low", "high", rule)) == (10000, 20.833333333333332)
