"""The long-horizon readout (`experiments/long_horizon_tasks/readout.py`, plan D6 and Task 6).

Every record here is constructed by the test; nothing runs an agent, a container or a provider call. The rules come
from `ladder.json`'s `readout` group; where it is pending, the tests pass stand-in values as a rehearsal does.
"""

import importlib.util
import itertools
import json
import re
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "experiments" / "long_horizon_tasks"
REPORT = ROOT / "docs" / "reports" / "2026-11-13-long-horizon-benchmark-survey-and-feasibility.md"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


readout = _load("lh_readout", KIT / "readout.py")


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

LADDER = json.loads((KIT / "ladder.json").read_text())
RULES = LADDER["readout"]
EFFORTS = ("low", "medium", "high")


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
                                         (6, 15, "above the band"), (15, 15, "above the band"),
                                         (4, 12, "screened in"), (5, 12, "above the band"), (0, 9, "floor"),
                                         (1, 2, "above the band"), (0, 0, "no observation")])
def test_the_pooled_label_reads_k_over_n_against_1_15_and_1_3_inclusive(K, n, label):
    assert readout.pooled_label(K, n, RULES["pooled"]) == label


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


# ---- Constructed records: the export the readout reads (readout.py's docstring states its shape) -----------------

LABEL, OLD = "a" * 64, "b" * 64
TASKS = [task["name"] for task in LADDER["tasks"]["list"]]
STAND_IN_VALUES = {"readout.contamination_scan.terms": ["<a frozen term>"],
                   "readout.contamination_scan.canary_sha256": "c" * 64,
                   "readout.graded_outcome.verifiers": {TASKS[0]: "passed and total sub-tests"},
                   "readout.fall_bound.seed": 20261114}
STANDINS = {p["field"]: STAND_IN_VALUES[p["field"]] for p in LADDER["pending"] if p["field"].startswith("readout.")}
CEILING = {"by": "ceiling", "cause": None}


def _start(slot, number, label, reward):
    return {"slot": slot, "start": number, "label": label, "row": 5, "reward": reward, "excluded": None,
            "usd": 1.0, "minutes": 30.0, "tokens": {kind: 10 for kind in readout.TOKEN_KINDS}, "graded": None,
            "egress_refused": {}}


def _outcomes(outcome):
    if outcome == "-":
        return []
    return [{"reward": o} if isinstance(o, int) else o for o in (outcome if isinstance(outcome, list) else [outcome])]


def _export(table, *, label=LABEL, end=CEILING, earlier=(), allowance=None, pilot=()):
    """table: {task: {effort: [outcome of round 1, 2, ...]}}. An outcome is 0 or 1 (an observation ending normally),
    "-" (a slot not started), a dict of start fields, or a list of such dicts (one slot's starts, in order)."""
    slots, starts = [], []
    for task, by_effort in table.items():
        for effort, outcomes in by_effort.items():
            for number, outcome in enumerate(outcomes, 1):
                slot = f"r{number}-{task}-{effort}"
                slots.append({"slot": slot, "task": task, "effort": effort, "round": number,
                              "pilot": (task, effort, number) in pilot})
                for fields in _outcomes(outcome):
                    starts.append(_start(slot, len(starts) + 1, label, None) | fields)
    return {"label": label, "earlier_labels": [{"label": old, "ended_by": f"ledger row ending {old[:8]}"}
                                               for old in earlier],
            "end": end, "slots": slots, "starts": starts, "allowance": allowance}


def _same(rewards):
    return {effort: list(rewards) for effort in EFFORTS}


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


# ---- The record shape: a record that does not fit is an error, never a skipped row --------------------------------

def _broken(change):
    export = _export({TASKS[0]: _same([1, 0])})
    change(export)
    return export


@pytest.mark.parametrize("change, message", [
    (lambda x: x["starts"][0].update(slot="r9-nowhere-low"), "joins no slot"),
    (lambda x: x["starts"][0].update(label="d" * 64), "label"),
    (lambda x: x["starts"][0].update(row=16), "ruling"),
    (lambda x: x["starts"][0].update(row=17), "row"),
    (lambda x: x["starts"][0].update(reward=0.5), "reward"),
    (lambda x: x["starts"][0].update(reward=None), "regrade"),
    (lambda x: x["starts"][0].update(excluded="cosmic rays"), "excluded"),
    (lambda x: x["starts"][0].update(row=15, excluded="contaminated"), "excluded"),
    (lambda x: x["starts"][0].update(extra=1), "keys"),
    (lambda x: x["starts"][0].pop("usd"), "keys"),
    (lambda x: x["starts"][0].update(usd=True), "usd"),
    (lambda x: x["starts"][0]["tokens"].pop("cache_read"), "tokens"),
    (lambda x: x["starts"][0].update(graded={"passed": 3, "total": 2}), "graded"),
    (lambda x: x["starts"][1].update(start=1), "start"),
    (lambda x: x["starts"].append(dict(x["starts"][0], start=99)), "more than one"),
    (lambda x: x["slots"][0].update(task="no-such-task"), "task"),
    (lambda x: x["slots"][0].update(effort="max"), "effort"),
    (lambda x: x["slots"][0].update(round=6), "round"),
    (lambda x: x["slots"].append(dict(x["slots"][0], slot="duplicate")), "twice"),
    (lambda x: x.update(end={"by": "stop", "cause": None}), "cause"),
    (lambda x: x.update(end={"by": "tired", "cause": None}), "end"),
    (lambda x: x.update(label="not a label"), "label"),
    (lambda x: x.update(extra=1), "keys"),
])
def test_a_record_that_does_not_fit_the_shape_is_refused(change, message):
    with pytest.raises(readout.ReadoutError, match=message):
        _compute(_broken(change))


def test_a_timeout_with_no_reward_is_an_observation_scored_zero():
    """D5: an observation enters k and n with the verifier's reward, 0 if the verifier gives none (row 3)."""
    cell = _compute(_export({TASKS[0]: {"low": [{"row": 3, "reward": None}], "medium": [0], "high": [0]}}))
    assert (cell["tasks"][TASKS[0]]["cells"]["low"]["k"], cell["tasks"][TASKS[0]]["cells"]["low"]["n"]) == (0, 1)


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


def _filled(ladder=LADDER):
    """The criterion as the freeze leaves it: every pending readout field filled with its stand-in."""
    filled = json.loads(json.dumps(ladder))
    for field, value in STANDINS.items():
        *path, key = field.split(".")
        target = filled
        for part in path:
            target = target[part]
        target[key] = value
    filled["pending"] = [p for p in filled["pending"] if p["field"] not in STANDINS]
    return filled


def test_a_final_readout_of_a_filled_criterion_is_not_stamped():
    assert _compute(_export(PARTIAL), ladder=_filled(), standins=None)["rehearsal"] is False


# ---- 5. Exclusions are listed and never scored zero ----------------------------------------------------------------

EXCLUDING = {TASKS[0]: {
    "low": [[{"row": 10, "reward": 1}, 1], 1, {"row": 15, "reward": 1}, [{"row": 1}, 0],
            {"reward": 1, "excluded": "contaminated"}],
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
            task["pooled"]["label"], result["effort"]["triples"]) == ((0, 3), (0, 9), "floor", 6)


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
