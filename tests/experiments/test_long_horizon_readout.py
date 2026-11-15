"""The long-horizon readout (`experiments/long_horizon_tasks/readout.py`, plan D6 and Task 6).

Every record here is constructed by the test; nothing runs an agent, a container or a provider call. The rules come
from `ladder.json`'s `readout` group; where it is pending, the tests pass stand-in values as a rehearsal does.
"""

import importlib.util
import re
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
