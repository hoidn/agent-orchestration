"""The PQ-1c readout on copies of a four-cell rehearsal, changed to reach each outcome and each refusal.

The rehearsal runs `run_cell.sh` with the stand-ins of `tests/pq1c_kit_support.py`; every change below edits
only the copy's files (`report.json`, `cell.json`, the memo, an attempt's `usage.json` or `stdout.txt`, a
log), as a real cell could have produced them. No orchestrator command runs here besides the rehearsal.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from tests.pq1c_kit_support import KIT, edit_json, outcome, readout, rehearse


@pytest.fixture(scope="module")
def rehearsal(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("rehearsal")
    yield rehearse(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def _changed(rehearsal: Path, tmp: Path, *changes) -> Path:
    results = tmp / "results"
    shutil.copytree(rehearsal, results, symlinks=True)
    for change in changes:
        change(results)
    return results


def _run(results: Path, cell: str, edit) -> None:
    edit_json(results / cell / "report.json", lambda report: edit(report["run"]))


def _attempt(results: Path, cell: str, name: str) -> Path:
    return sorted((results / cell / "workspace").glob(f".orchestrate/runs/*/effects/*/attempt-*/{name}"))[0]


def times(cell: str, factor: float):
    return lambda results: _run(results, cell, lambda run: run["usage"].update(cost_usd=run["usage"]["cost_usd"] * factor))


def cost_is(cell: str, value):
    return lambda results: _run(results, cell, lambda run: run["usage"].update(cost_usd=value))


def failed(cell: str):
    return lambda results: _run(results, cell, lambda run: run.update(status="failed"))


def meta(cell: str, **fields):
    return lambda results: edit_json(results / cell / "cell.json", lambda record: record.update(fields))


def redispatched(cell: str):
    """A second `started` row for a committed turn, as a resume that ran it again would append."""
    def change(results):
        (memo,) = (results / cell / "workspace").glob(".orchestrate/runs/*/memo.jsonl")
        rows = [json.loads(line) for line in memo.read_text().splitlines()]
        started = next(row for row in rows if row["record"] == "started" and row["identity"].endswith("/ draft"))
        memo.write_text(memo.read_text() + json.dumps({**started, "attempt": 2}) + "\n")
    return change


def partial_usage(cell: str):
    """A turn cut off after the model answered: its usage is a lower bound (`complete: false`)."""
    def change(results):
        edit_json(_attempt(results, cell, "usage.json"), lambda usage: usage.update(complete=False))
        _run(results, cell, lambda run: run["usage"].update(partial=True))
    return change


def unknown_usage(cell: str):
    def change(results):
        _attempt(results, cell, "usage.json").write_text(json.dumps({"status": "unknown", "reason": "malformed"}))
        _run(results, cell, lambda run: run["usage"].update(partial=True, unknown_attempts=1))
    return change


def log_line(cell: str, log: str, line: str):
    return lambda results: (results / cell / log).open("a").write(line + "\n")


def init_with_plugin(cell: str):
    def change(results):
        stdout = _attempt(results, cell, "stdout.txt")
        rows = [json.loads(line) for line in stdout.read_text().splitlines()]
        rows = [{**row, "plugins": [{"name": "superpowers"}]} if row.get("subtype") == "init" else row for row in rows]
        stdout.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return change


def swapped(cell: str, other: str):
    def change(results):
        shutil.rmtree(results / cell)
        shutil.copytree(results / other, results / cell, symlinks=True)
    return change


V0, V1, B0, B1 = "variant-clean", "variant-resumed", "baseline-clean", "baseline-resumed"


@pytest.mark.parametrize("changes, expected", [
    ((times(V0, 0.7), times(V1, 0.7)), "Retain"),
    ((times(V0, 1.3), times(V1, 1.3)), "Retire"),
    ((times(V0, 0.7),), "Improve"),
    ((times(V0, 1.3),), "Improve"),
    ((times(V0, 1.3), times(V1, 0.7)), "Improve"),
    ((failed(V1),), "Retire"),
    ((redispatched(V1),), "Retire"),
    ((redispatched(B0), times(V0, 0.7), times(V1, 0.7)), "Improve"),
    ((failed(B0), times(V0, 0.7), times(V1, 0.7)), "Improve"),
    ((failed(B0), times(B0, 0.25), times(B1, 0.7)), "undetermined"),
    ((failed(V0), failed(B0)), "Improve"),
    ((partial_usage(V0), times(V1, 1.3)), "undetermined"),
    ((partial_usage(V0), times(V1, 0.7)), "undetermined"),
    ((partial_usage(V0),), "Improve"),
    ((partial_usage(V0), failed(V1)), "Retire"),
], ids=["retain", "retire-cost", "one-pair-cheaper", "one-pair-dearer", "split", "retire-incomplete",
        "retire-redispatch", "baseline-redispatch-not-retire", "baseline-incomplete", "failed-baseline-not-cheap",
        "both-clean-failed", "partial-could-retire", "partial-could-retain", "partial-band-excluded",
        "partial-but-incomplete"])
def test_readout_returns_the_criterion_outcome(rehearsal, tmp_path, changes, expected):
    shown = outcome(_changed(rehearsal, tmp_path, *changes))
    assert shown["outcome"] == expected, shown["reasons"]


def test_a_pair_with_a_failed_cell_has_no_cost_ratio(rehearsal, tmp_path):
    shown = outcome(_changed(rehearsal, tmp_path, failed(B0), times(B0, 0.25)))
    assert shown["ratios"]["clean"] is None


def test_partial_usage_makes_the_cost_axis_undetermined_never_a_number(rehearsal, tmp_path):
    shown = outcome(_changed(rehearsal, tmp_path, partial_usage(V0)))
    cell = shown["cells"][V0]
    assert (cell["cost_usd"], cell["usage_recorded"], shown["ratios"]["clean"]) == (None, False, None)


@pytest.mark.parametrize("value", [0, -0.001, float("inf"), float("nan"), "0.0001", True],
                         ids=["zero", "negative", "infinite", "nan", "string", "bool"])
def test_a_cost_that_is_not_a_finite_number_above_zero_decides_nothing(rehearsal, tmp_path, value):
    shown = outcome(_changed(rehearsal, tmp_path, cost_is(V0, value), cost_is(V1, value)))
    assert (shown["ratios"], shown["outcome"]) == ({"clean": None, "resumed": None}, "undetermined")


@pytest.mark.parametrize("changes", [
    (lambda results: (results / V0 / "report.json").unlink(), meta(V0, report_exit=1)),
    (unknown_usage(V0),),
    (log_line(V0, "run.log", "[spend_cap_unmetered] attempt cut off"),),
    (log_line(V1, "resume.log", "[spend_cap_reached] spent 2 USD of a 2 USD cap"),),
    (log_line(V0, "codex-calls.log", "codex exec"),),
    (init_with_plugin(B1),),
    (meta(V1, run_exit=0, resume_exit=None, stop={"exit": 0, "pending": 0, "last_identity": "", "attempts": 4}),
     times(V0, 0.7), times(V1, 0.7)),
    (meta(V1, resume_exit=None),),
    (swapped(V0, B0),),
    (lambda results: shutil.rmtree(results / B1),),
    (lambda results: (results / B0 / "cell.json").write_text("{not json"),),
    tuple(failed(cell) for cell in (V0, V1, B0, B1)) + tuple(unknown_usage(cell) for cell in (V0, V1, B0, B1)),
], ids=["report-missing", "unmetered-attempt", "cap-unmetered", "cap-reached", "codex-called", "plugin-loaded",
        "stop-never-fired", "never-resumed", "another-cells-record", "cell-missing", "unreadable-record",
        "all-failed-silently"])
def test_an_infrastructure_failure_makes_the_readout_undetermined(rehearsal, tmp_path, changes):
    shown = outcome(_changed(rehearsal, tmp_path, *changes))
    assert (shown["outcome"], bool(shown["reasons"])) == ("undetermined", True)


# --- refusals ---

def _refused(shown) -> bool:
    return (shown.returncode, shown.stdout) == (2, "")


def test_readout_refuses_a_criterion_whose_hash_differs_from_the_frozen_one(rehearsal, tmp_path):
    criterion = json.loads((KIT / "criterion.json").read_text())
    criterion["thresholds"]["retire_cost_ratio_at_or_above"] = 1.1
    (tmp_path / "criterion.json").write_text(json.dumps(criterion))
    assert _refused(readout(rehearsal, "--criterion", str(tmp_path / "criterion.json")))


@pytest.mark.parametrize("field", ["criterion_sha256", "frozen_files"])
def test_readout_refuses_a_cell_that_recorded_another_criterion_or_kit(rehearsal, tmp_path, field):
    other = {"criterion_sha256": "0" * 64, "frozen_files": {"inputs.json": "0" * 64}}[field]
    assert _refused(readout(_changed(rehearsal, tmp_path, meta(V0, **{field: other}))))


def test_readout_refuses_a_retry_of_a_valid_observation(rehearsal, tmp_path):
    def retry(results):
        shutil.copytree(results / V1, results / f"{V1}-retry", symlinks=True)
        edit_json(results / f"{V1}-retry" / "cell.json", lambda record: record.update(slot=f"{V1}-retry"))
    assert _refused(readout(_changed(rehearsal, tmp_path, retry)))


def test_retry_check_tells_an_infrastructure_failure_from_a_valid_observation(rehearsal, tmp_path):
    results = _changed(rehearsal, tmp_path, unknown_usage(V0))
    assert (readout(results / V0, "--retry-check").returncode, readout(results / V1, "--retry-check").returncode) == (0, 4)
