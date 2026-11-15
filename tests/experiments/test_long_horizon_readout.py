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
