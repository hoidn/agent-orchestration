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

import subprocess
import sys

from tests.agent_session_shims import closed_path
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


def init_edited(cell: str, edit):
    """Edit the first attempt's stream-json init event (`edit` returns the new event, or None to drop it)."""
    def change(results):
        stdout = _attempt(results, cell, "stdout.txt")
        rows = [json.loads(line) for line in stdout.read_text().splitlines()]
        rows = [edit(dict(row)) if row.get("subtype") == "init" else row for row in rows]
        stdout.write_text("".join(json.dumps(row) + "\n" for row in rows if row is not None))
    return change


def _added(key: str, item):
    return lambda init: {**init, key: [*init[key], item]}


def _renamed(old: str, new: str):
    return lambda init: {**{k: v for k, v in init.items() if k != old}, new: init[old]}


def budget_stopped(cell: str):
    """The CLI's per-call budget stopped the cell's last call: it ends with an error_max_budget_usd result."""
    def change(results):
        stdout = sorted((results / cell / "workspace").glob(".orchestrate/runs/*/effects/*/attempt-*/stdout.txt"))[-1]
        stdout.write_text(stdout.read_text() + json.dumps({"type": "result", "subtype": "error_max_budget_usd",
                                                          "is_error": True}) + "\n")
        _run(results, cell, lambda run: run.update(status="failed"))
    return change


def result_appended(cell: str, **fields):
    """The cell's last call ends with this `result` event, and the run failed."""
    def change(results):
        stdout = sorted((results / cell / "workspace").glob(".orchestrate/runs/*/effects/*/attempt-*/stdout.txt"))[-1]
        stdout.write_text(stdout.read_text() + json.dumps({"type": "result", **fields}) + "\n")
        _run(results, cell, lambda run: run.update(status="failed"))
    return change


def stream_line(cell: str, row: dict):
    return lambda results: _attempt(results, cell, "stdout.txt").open("a").write(json.dumps(row) + "\n")


def first_turn_budget_stop(cell: str):
    """The CLI's per-call budget stopped the first turn: nothing committed."""
    def change(results):
        (memo,) = (results / cell / "workspace").glob(".orchestrate/runs/*/memo.jsonl")
        rows = [json.loads(line) for line in memo.read_text().splitlines()]
        first = next(index for index, row in enumerate(rows) if row["record"] == "started"
                     and row["identity"].endswith("/ draft"))
        memo.write_text("".join(json.dumps(row) + "\n" for row in rows[:first + 1]))
        stdout = _attempt(results, cell, "stdout.txt")
        stdout.write_text(stdout.read_text() + json.dumps({"type": "result", "subtype": "error_max_budget_usd",
                                                          "is_error": True}) + "\n")
        _run(results, cell, lambda run: run.update(status="failed"))
    return change


def extra_session(cell: str):
    """One more native transcript for the workspace than the attempts name: a CLI ran outside the journal."""
    return lambda results: edit_json(results / cell / "cell.json",
                                     lambda record: record["native_sessions"].append("ffffffff-0000-4000-8000-000000000000"))


def zero_output(cell: str):
    def change(results):
        edit_json(_attempt(results, cell, "usage.json"), lambda usage: usage["rows"][0]["tokens"].update(output=0))
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
    ((budget_stopped(V0),), "Retire"),
    ((log_line(V1, "resume.log", "[spend_cap_reached] spent 10 USD of a 10 USD cap"),), "Retire"),
    ((budget_stopped(B0), times(V0, 0.7), times(V1, 0.7)), "Improve"),
], ids=["retain", "retire-cost", "one-pair-cheaper", "one-pair-dearer", "split", "retire-incomplete",
        "retire-redispatch", "baseline-redispatch-not-retire", "baseline-incomplete", "failed-baseline-not-cheap",
        "both-clean-failed", "partial-could-retire", "partial-could-retain", "partial-band-excluded",
        "partial-but-incomplete", "variant-budget-stop", "variant-cap-reached", "baseline-budget-stop"])
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
    (log_line(V0, "codex-calls.log", "codex exec"),),
    (log_line(B0, "nested-calls.log", "-p --model claude-fable-5-1"),),
    (zero_output(V0),),
    (init_edited(B1, _added("plugins", {"name": "superpowers", "path": "/home/u/.claude/plugins/superpowers",
                                         "source": "superpowers@claude-plugins"})),),
    (init_edited(B1, _added("plugins", {"name": "cc-plugin-agents-md"})),),
    (init_edited(B1, _added("plugins", {"name": "x", "path": "builtin", "source": "x@claude-plugins"})),),
    (init_edited(B1, _added("plugins", {"name": "x", "path": "/home/u/.claude/plugins/x", "source": "x@builtin"})),),
    (stream_line(B1, {"type": "system", "subtype": "hook_response", "hook_event": "SessionStart"}),),
    (meta(B0, native_hook_traces=1),),
    (result_appended(V1, subtype="success", is_error=True, api_error_status=529, result="API Error: overloaded"),),
    (result_appended(V1, subtype="success", is_error=True, result="API Error: Request was aborted."),),
    (init_edited(B1, _added("agents", "developer")),),
    (init_edited(B1, _added("skills", "ponytail")),),
    (init_edited(B1, _added("slash_commands", "brainstorm")),),
    (init_edited(B1, _added("mcp_servers", {"name": "docs", "status": "connected"})),),
    (init_edited(B1, lambda init: {**init, "model": "claude-fable-5-1"}),),
    (init_edited(B1, lambda init: None),),
    (init_edited(B1, _renamed("plugins", "plugin_list")),),
    (init_edited(B1, _renamed("mcp_servers", "mcpServers")),),
    (extra_session(V0),),
    (meta(V1, run_exit=0, resume_exit=None, stop={"exit": 0, "pending": 0, "last_identity": "", "attempts": 4}),
     times(V0, 0.7), times(V1, 0.7)),
    (meta(V1, resume_exit=None),),
    (swapped(V0, B0),),
    (lambda results: shutil.rmtree(results / B1),),
    (lambda results: (results / B0 / "cell.json").write_text("{not json"),),
    tuple(failed(cell) for cell in (V0, V1, B0, B1)) + tuple(unknown_usage(cell) for cell in (V0, V1, B0, B1)),
], ids=["report-missing", "unmetered-attempt", "cap-unmetered", "codex-called", "claude-nested", "zero-output",
        "user-plugin", "plugin-without-builtin-marker", "builtin-path-user-source", "user-path-builtin-source",
        "hook-event-in-stream", "hook-record-in-transcript", "api-error-status", "api-error-text", "user-agent", "user-skill", "slash-command", "mcp-server",
        "other-model", "no-init-event", "renamed-plugins", "renamed-mcp-servers", "extra-native-session",
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


def test_readout_refuses_a_cell_that_ran_with_another_manifest(rehearsal, tmp_path):
    assert _refused(readout(_changed(rehearsal, tmp_path, meta(V0, manifest_sha256="0" * 64))))


def test_readout_refuses_to_run_when_its_own_digest_differs_from_the_manifest(rehearsal, tmp_path):
    kit = tmp_path / "kit"
    shutil.copytree(KIT, kit)
    (kit / "readout.py").write_text((kit / "readout.py").read_text().replace("<= low", "<= low * 2"))
    shown = subprocess.run([sys.executable, "-B", str(kit / "readout.py"), str(rehearsal)], capture_output=True,
                           text=True, timeout=120, check=False, env={"PATH": closed_path()})
    assert _refused(shown), shown.stderr


@pytest.mark.parametrize("key, value", [("claude_version", "2.1.400 (Claude Code)"), ("python_version", "3.99.0"),
                                        ("price_table_sha256", "0" * 64), ("runtime_commit", "0" * 40)])
def test_cells_that_ran_in_different_environments_read_out_undetermined(rehearsal, tmp_path, key, value):
    shown = outcome(_changed(rehearsal, tmp_path, meta(B1, **{key: value})))
    assert shown["outcome"] == "undetermined" and any(key in reason for reason in shown["reasons"]), shown["reasons"]


def test_a_fixture_other_than_the_pinned_one_reads_out_undetermined(rehearsal, tmp_path):
    shown = outcome(_changed(rehearsal, tmp_path, *(meta(cell, fixture_commit="0" * 40) for cell in (V0, V1, B0, B1))))
    assert shown["outcome"] == "undetermined"


def test_a_cost_stop_is_not_retried_and_its_recorded_cost_is_reported(rehearsal, tmp_path):
    results = _changed(rehearsal, tmp_path, budget_stopped(V0))
    cell = outcome(results)["cells"][V0]
    assert (cell["completed"], cell["problems"], cell["recorded_cost_usd"] > 0) == (False, [], True)
    assert readout(results / V0, "--retry-check").returncode == 4


def test_a_retry_shows_the_replaced_attempts_recorded_cost_and_why(rehearsal, tmp_path):
    def killed_then_retried(results):
        shutil.copytree(results / V0, results / f"{V0}-retry", symlinks=True)
        edit_json(results / f"{V0}-retry" / "cell.json", lambda record: record.update(slot=f"{V0}-retry"))
        (results / V0 / "cell.json").unlink()                   # the first attempt died before filing its record
    shown = outcome(_changed(rehearsal, tmp_path, killed_then_retried))
    replaced = shown["cells"][V0]["replaced"]
    assert (shown["outcome"], replaced["recorded_cost_usd"] > 0, "did not finish" in replaced["why"][0]) == (
        "Improve", True, True)


def test_readout_refuses_a_retry_of_a_valid_observation(rehearsal, tmp_path):
    def retry(results):
        shutil.copytree(results / V1, results / f"{V1}-retry", symlinks=True)
        edit_json(results / f"{V1}-retry" / "cell.json", lambda record: record.update(slot=f"{V1}-retry"))
    assert _refused(readout(_changed(rehearsal, tmp_path, retry)))


def test_retry_check_tells_an_infrastructure_failure_from_a_valid_observation(rehearsal, tmp_path):
    results = _changed(rehearsal, tmp_path, unknown_usage(V0))
    assert (readout(results / V0, "--retry-check").returncode, readout(results / V1, "--retry-check").returncode) == (0, 4)


def test_a_call_without_an_init_event_fails_closed(rehearsal, tmp_path):
    shown = outcome(_changed(rehearsal, tmp_path, init_edited(B1, lambda init: None)))
    assert any("0 init events" in reason for reason in shown["reasons"]), shown["reasons"]


def test_a_failure_the_model_produced_stays_a_workflow_outcome(rehearsal, tmp_path):
    results = _changed(rehearsal, tmp_path, result_appended(V1, subtype="error_during_execution", is_error=True))
    assert (outcome(results)["outcome"], readout(results / V1, "--retry-check").returncode) == ("Retire", 4)


def test_an_api_error_is_an_infrastructure_failure_and_retryable(rehearsal, tmp_path):
    results = _changed(rehearsal, tmp_path, result_appended(V1, subtype="success", is_error=True, api_error_status=500))
    assert readout(results / V1, "--retry-check").returncode == 0


def test_a_first_turn_budget_stop_is_a_cost_outcome_not_retryable(rehearsal, tmp_path):
    results = _changed(rehearsal, tmp_path, first_turn_budget_stop(V0))
    cell = outcome(results)["cells"][V0]
    assert (cell["committed_turns"], cell["problems"], cell["completed"]) == ([], [], False)
    assert readout(results / V0, "--retry-check").returncode == 4
