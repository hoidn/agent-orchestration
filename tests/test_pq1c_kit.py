"""The PQ-1c kit works end to end without any provider call.

`run_cell.sh` is driven through its command line in rehearsal mode: the stand-in `claude` is the
agent-session shim of `tests/agent_session_shims.py` with a `result` line that carries usage (as the
metering stand-ins print), so both the Agent Sessions turns and the baseline's plain metered calls
record priced usage. Every subprocess gets a closed PATH, HOME is a temporary directory (so the slot
ledger is temporary too) and the refusal tests show that nothing was launched. `readout.py` is run
on the four rehearsal cells and on copies of them changed to reach each outcome.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.agent_session_shims import FAKE_CLAUDE, closed_path
from tests.workflow_evaluated_consumer_sources import design_docs

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "experiments" / "pq1c"
MODEL = "claude-haiku-5-5"
CELLS = ("variant-clean", "variant-resumed", "baseline-clean", "baseline-resumed")
NO_PROVIDER = REPO / "experiments" / "thread_m" / "no_provider"
DOC, FINAL = "artifacts/design/wordcount.md", "docs/design/wordcount.md"
PLAN = {"claude": [
    {"result": {"doc": DOC}, "files": {DOC: "# draft\n"}},
    {"result": {"blocking": ["b1"], "notes": []}},
    {"result": {"doc": FINAL}, "files": {FINAL: "# final\n"}},
    {"result": {"summary": "done", "commits": ["abc"], "checks_run": ["pytest"], "left_undone": []}},
]}

# The shim's closing `result` line, given the usage a metered Claude CLI reports.
_RESULT = '"session_id": session, "result": "ok"}'
_USAGE = (', "total_cost_usd": 0.0042, "modelUsage": {"claude-haiku-5-5": {"inputTokens": 1000, "outputTokens": 200,'
          ' "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "costUSD": 0.0042}}')
assert FAKE_CLAUDE.count(_RESULT) == 1
# The kit starts the stand-in through a symlink with a fresh environment: it reads its plan from beside
# itself and keeps its native store where the real CLI does (`~/.claude`), which the orchestrator reads.
STANDIN = '''import os, sys
from pathlib import Path
with (Path(__file__).resolve().parent / "invocations.log").open("a") as _log:
    _log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:] == ["--version"]:
    print("0.0.0 (pq1c stand-in)"); sys.exit(0)
os.environ.setdefault("AGENT_SHIM_PLAN", (Path(__file__).resolve().parent / "plan.json").read_text())
os.environ.setdefault("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
''' + FAKE_CLAUDE.replace(_RESULT, _RESULT[:-1] + _USAGE + "}")


def _readout_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("pq1c_readout", KIT / "readout.py")
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode, before = True, sys.dont_write_bytecode  # no __pycache__ in the kit
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


def _standins(tmp: Path) -> Path:
    bin_dir = tmp / "standins"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text(f"#!{sys.executable}\n" + STANDIN, encoding="utf-8")
    (bin_dir / "claude").chmod(0o700)
    (bin_dir / "plan.json").write_text(json.dumps(PLAN), encoding="utf-8")
    return bin_dir


def _launch(tmp: Path, cell: str, *, kit: Path = KIT, authorized: bool = True, rehearsal: bool = True,
            path: tuple = (), **extra: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH" and not key.startswith("PQ1C_")}
    env.update(HOME=str(tmp / "home"), PATH=closed_path(*path), PQ1C_PYTHON=sys.executable, **extra)
    (tmp / "home").mkdir(exist_ok=True)
    if authorized:
        env["PQ1C_SPEND_AUTHORIZED"] = "yes"
    if rehearsal:
        env["PQ1C_REHEARSAL_STANDINS"] = str(tmp / "standins")
    return subprocess.run(["bash", str(kit / "run_cell.sh"), str(REPO), cell, str(tmp / "results")],
                          env=env, capture_output=True, text=True, timeout=600, check=False)


def _readout(results: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(KIT / "readout.py"), str(results), *extra],
                          capture_output=True, text=True, timeout=120, check=False,
                          env={**os.environ, "PATH": closed_path()})


def _outcome(results: Path) -> dict:
    shown = _readout(results)
    assert shown.returncode == 0, shown.stderr
    return json.loads(shown.stdout)


def _ledger(tmp: Path) -> Path:
    return tmp / "home" / ".local" / "state" / "pq1c-rehearsal"


def _refused(launched: subprocess.CompletedProcess[str], gate: str) -> bool:
    """Refused (exit 3) by `gate`, the cause the refusal names."""
    return launched.returncode == 3 and gate in launched.stderr


def _nothing_launched(tmp: Path) -> bool:
    ledger = _ledger(tmp)
    claimed = sorted(path.name for path in ledger.iterdir()) if ledger.exists() else []
    cells = sorted(path.name for path in (tmp / "results").glob("*-*")) if (tmp / "results").exists() else []
    return claimed == cells == [] and not (tmp / "standins" / "invocations.log").exists()


@pytest.fixture
def standins(tmp_path) -> Path:
    _standins(tmp_path)
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture(scope="module")
def rehearsal(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("rehearsal")
    _standins(tmp)
    for cell in CELLS:
        launched = _launch(tmp, cell)
        assert launched.returncode == 0, launched.stderr
    yield tmp / "results"
    shutil.rmtree(tmp, ignore_errors=True)


def _workspace(results: Path, cell: str) -> Path:
    return results / cell / "workspace"


def _memo(results: Path, cell: str) -> Path:
    (memo,) = _workspace(results, cell).glob(".orchestrate/runs/*/memo.jsonl")
    return memo


def _changed(rehearsal: Path, tmp: Path, *changes) -> Path:
    results = tmp / "results"
    shutil.copytree(rehearsal, results, symlinks=True)
    for change in changes:
        change(results)
    return results


def _report(results: Path, cell: str, edit) -> None:
    path = results / cell / "report.json"
    report = json.loads(path.read_text())
    edit(report["run"])
    path.write_text(json.dumps(report))


def cost_times(cell: str, factor: float):
    return lambda results: _report(results, cell, lambda run: run["usage"].update(cost_usd=run["usage"]["cost_usd"] * factor))


def failed(cell: str):
    return lambda results: _report(results, cell, lambda run: run.update(status="failed"))


def redispatched(cell: str):
    """A second `started` row for a committed turn, as a resume that ran it again would append."""
    def change(results):
        memo = _memo(results, cell)
        rows = [json.loads(line) for line in memo.read_text().splitlines()]
        started = next(row for row in rows if row["record"] == "started" and row["identity"].endswith("/ draft"))
        memo.write_text(memo.read_text() + json.dumps({**started, "attempt": 2}) + "\n")
    return change


def unknown_usage(cell: str):
    def change(results):
        first = sorted(_workspace(results, cell).glob(".orchestrate/runs/*/effects/*/attempt-*/usage.json"))[0]
        first.write_text(json.dumps({"status": "unknown", "reason": "no_usage_event"}))
        _report(results, cell, lambda run: run["usage"].update(partial=True, unknown_attempts=1))
    return change


# --- the launcher refuses before anything is launched ---

def test_launcher_refuses_without_spend_authorization(standins):
    refused = _launch(standins, "variant-clean", authorized=False)
    assert _refused(refused, "PQ1C_SPEND_AUTHORIZED") and _nothing_launched(standins), refused.stderr


@pytest.mark.parametrize("edit", [
    ("inputs.json", "reviewer_model", "claude-fable-5-1"),
    ("inputs.json", "planner_model", "claude-opus-5-5"),
    ("inputs.json", "planner_model", "haiku"),
    ("providers.json", "providers.codex", "codex_metered"),
], ids=["fable-reviewer", "opus-planner", "alias", "codex-template"])
def test_launcher_refuses_any_binding_but_haiku_on_the_claude_metered_template(standins, edit):
    kit = standins / "kit"
    shutil.copytree(KIT, kit)
    name, key, value = edit
    document = json.loads((kit / name).read_text())
    (kit / name).write_text(json.dumps({**document, key: value}))
    refused = _launch(standins, "baseline-clean", kit=kit)
    assert _refused(refused, "bindings:") and _nothing_launched(standins), refused.stderr


def test_launcher_refuses_the_no_provider_stub_outside_rehearsal_mode(standins):
    log = NO_PROVIDER.parent / "no-provider.log"
    existed = log.exists()
    refused = _launch(standins, "variant-clean", rehearsal=False, path=(NO_PROVIDER,))
    assert _refused(refused, "no-provider stub") and _nothing_launched(standins), refused.stderr
    assert log.exists() == existed                       # the stub was resolved, never run


def test_launcher_refuses_a_cell_outside_the_four(standins):
    refused = _launch(standins, "variant-extra")
    assert _refused(refused, "not one of the four cells") and _nothing_launched(standins), refused.stderr


def test_launcher_refuses_a_criterion_other_than_the_frozen_one(standins):
    kit = standins / "kit"
    shutil.copytree(KIT, kit)
    criterion = json.loads((kit / "criterion.json").read_text())
    criterion["thresholds"]["retain_cost_ratio_at_or_below"] = 0.95
    (kit / "criterion.json").write_text(json.dumps(criterion))
    refused = _launch(standins, "variant-clean", kit=kit)
    assert _refused(refused, "frozen criterion") and _nothing_launched(standins), refused.stderr


def test_launcher_refuses_a_used_slot_and_allows_one_infrastructure_retry(standins):
    (_ledger(standins) / "baseline-clean").mkdir(parents=True)        # its first run has happened
    used = _launch(standins, "baseline-clean")
    assert _refused(used, "is used") and not (standins / "standins" / "invocations.log").exists(), used.stderr
    retried = _launch(standins, "baseline-clean", PQ1C_INFRA_RETRY="stand-in host lost power")
    assert retried.returncode == 0, retried.stderr
    assert json.loads((standins / "results" / "baseline-clean-retry" / "cell.json").read_text())["retry_reason"]
    again = _launch(standins, "baseline-clean", PQ1C_INFRA_RETRY="again")
    assert _refused(again, "one infrastructure retry"), again.stderr
    assert sorted(path.name for path in _ledger(standins).iterdir()) == ["baseline-clean", "baseline-clean-retry"]


def test_launcher_refuses_a_retry_of_a_cell_that_never_ran(standins):
    refused = _launch(standins, "variant-resumed", PQ1C_INFRA_RETRY="never ran")
    assert _refused(refused, "nothing to retry") and _nothing_launched(standins), refused.stderr


# --- the rehearsal: four cells with stand-ins ---

def test_rehearsal_refuses_to_run_a_cell_twice(rehearsal):
    again = _launch(rehearsal.parent, "variant-clean")
    assert _refused(again, "is used"), again.stderr
    assert sorted(path.name for path in rehearsal.glob("*-*")) == sorted(CELLS)


def test_rehearsal_cells_each_make_four_provider_calls(rehearsal):
    calls = {cell: len(_workspace(rehearsal, cell).joinpath("requests.jsonl").read_text().splitlines())
             for cell in CELLS}
    assert calls == dict.fromkeys(CELLS, 4)


def test_rehearsal_binds_every_call_to_haiku_on_the_metered_template(rehearsal):
    argvs = [json.loads(line)["argv"] for cell in CELLS
             for line in _workspace(rehearsal, cell).joinpath("requests.jsonl").read_text().splitlines()]
    assert {argv[argv.index("--model") + 1] for argv in argvs} == {MODEL}
    assert all("stream-json" in argv for argv in argvs)


def test_rehearsal_workspace_is_a_clone_of_the_consumer_design_docs_fixture(rehearsal, tmp_path):
    design_docs(tmp_path)
    expected = {path.relative_to(tmp_path).as_posix(): path.read_text() for path in tmp_path.rglob("*.md")}
    workspace = _workspace(rehearsal, "variant-clean")
    assert {relpath: (workspace / relpath).read_text() for relpath in expected} == expected
    commits = {json.loads((rehearsal / cell / "cell.json").read_text())["fixture_commit"] for cell in CELLS}
    assert len(commits) == 1


def test_resumed_cells_stop_after_the_reviewers_first_turn_with_nothing_in_flight(rehearsal):
    for cell in ("variant-resumed", "baseline-resumed"):
        stop = json.loads((rehearsal / cell / "cell.json").read_text())["stop"]
        assert (stop["exit"], stop["pending"], stop["last_identity"].endswith("/ feedback"), stop["attempts"]) == (
            75, 0, True, 2), cell


def test_readout_of_the_rehearsal_passes_every_mechanism_axis_and_gives_improve_at_equal_cost(rehearsal):
    shown = _outcome(rehearsal)
    cells = shown["cells"]
    assert {cell: (cells[cell]["completed"], cells[cell]["repeated_work"], cells[cell]["usage_recorded"])
            for cell in CELLS} == dict.fromkeys(CELLS, (True, [], True))
    assert shown["ratios"] == {"clean": 1.0, "resumed": 1.0}
    assert (shown["outcome"], shown["rehearsal"]) == ("Improve", True)


def test_readout_shows_the_invalidate_refusal_for_the_variant_only(rehearsal):
    cells = _outcome(rehearsal)["cells"]
    assert (cells["variant-clean"]["invalidate"]["passed"], cells["baseline-clean"]["invalidate"]["passed"]) == (True, True)
    variant = json.loads((rehearsal / "variant-clean" / "invalidate.json").read_text())
    baseline = json.loads((rehearsal / "baseline-clean" / "invalidate.json").read_text())
    assert (variant["exit"], variant["coordinator_committed"], variant["bytes_unchanged"]) == (2, True, True)
    assert baseline["exit"] == 0


# --- the readout on changed copies of the rehearsal ---

@pytest.mark.parametrize("changes, outcome", [
    ((cost_times("variant-clean", 0.7), cost_times("variant-resumed", 0.7)), "Retain"),
    ((cost_times("variant-clean", 1.3), cost_times("variant-resumed", 1.3)), "Retire"),
    ((cost_times("variant-clean", 0.7),), "Improve"),
    ((cost_times("variant-clean", 1.3),), "Improve"),
    ((failed("variant-resumed"),), "Retire"),
    ((redispatched("variant-resumed"),), "Retire"),
    ((failed("baseline-clean"), cost_times("variant-clean", 0.7), cost_times("variant-resumed", 0.7)), "Improve"),
    ((unknown_usage("variant-clean"), cost_times("variant-resumed", 1.3)), "undetermined"),
    ((unknown_usage("variant-clean"), cost_times("variant-resumed", 0.7)), "undetermined"),
    ((unknown_usage("variant-clean"),), "Improve"),
    ((unknown_usage("variant-clean"), failed("variant-resumed")), "Retire"),
], ids=["retain", "retire-cost", "one-pair-cheaper", "one-pair-dearer", "retire-incomplete", "retire-redispatch",
        "baseline-incomplete", "unknown-could-retire", "unknown-could-retain", "unknown-band-excluded",
        "unknown-but-incomplete"])
def test_readout_returns_the_criterion_outcome(rehearsal, tmp_path, changes, outcome):
    shown = _outcome(_changed(rehearsal, tmp_path, *changes))
    assert shown["outcome"] == outcome, shown["reasons"]


def test_unknown_usage_makes_the_cost_axis_undetermined_never_a_number(rehearsal, tmp_path):
    shown = _outcome(_changed(rehearsal, tmp_path, unknown_usage("variant-clean")))
    assert (shown["cells"]["variant-clean"]["cost_usd"], shown["ratios"]["clean"]) == (None, None)
    assert shown["cells"]["variant-clean"]["usage_recorded"] is False


def test_readout_is_undetermined_when_a_cell_is_missing(rehearsal, tmp_path):
    results = _changed(rehearsal, tmp_path, lambda results: shutil.rmtree(results / "baseline-resumed"))
    assert _outcome(results)["outcome"] == "undetermined"


def test_readout_takes_a_retry_in_place_of_the_cell_it_retries(rehearsal, tmp_path):
    def retry(results):
        shutil.copytree(results / "variant-resumed", results / "variant-resumed-retry", symlinks=True)
        failed("variant-resumed")(results)
    assert _outcome(_changed(rehearsal, tmp_path, retry))["outcome"] == "Improve"


# --- the frozen criterion ---

def test_readout_refuses_a_criterion_whose_hash_differs_from_the_frozen_one(rehearsal, tmp_path):
    criterion = json.loads((KIT / "criterion.json").read_text())
    criterion["thresholds"]["retire_cost_ratio_at_or_above"] = 1.1
    (tmp_path / "criterion.json").write_text(json.dumps(criterion))
    refused = _readout(rehearsal, "--criterion", str(tmp_path / "criterion.json"))
    assert (refused.returncode, refused.stdout) == (2, ""), refused.stderr


def test_readout_refuses_a_cell_that_recorded_another_criterion_hash(rehearsal, tmp_path):
    def other_hash(results):
        path = results / "variant-clean" / "cell.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), "criterion_sha256": "0" * 64}))
    refused = _readout(_changed(rehearsal, tmp_path, other_hash))
    assert (refused.returncode, refused.stdout) == (2, ""), refused.stderr


def test_the_kit_criterion_is_the_frozen_one():
    import hashlib
    assert hashlib.sha256((KIT / "criterion.json").read_bytes()).hexdigest() == _readout_module().CRITERION_SHA256
