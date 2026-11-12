"""The PQ-1c launcher: its refusals, a four-cell rehearsal with stand-ins, the retry rule and the nesting guard.

`run_cell.sh` is driven through its command line with the stand-ins of `tests/pq1c_kit_support.py` on a
closed PATH and a temporary HOME (so the slot ledger is temporary). A refusal test shows the named gate
fired and that nothing was launched: no paid call, no slot, no cell, no temporary debris.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from tests.pq1c_kit_support import (CELLS, FAILING_PLAN, KIT, MODEL, NO_PROVIDER, REPO, WRAPPER_FLAGS, copy_cells,
                                    edit_json, invocations, launch, ledger, nothing_launched, outcome, paid_calls,
                                    refused, rehearse, standins)
from tests.workflow_evaluated_consumer_sources import design_docs


@pytest.fixture
def tmp(tmp_path) -> Path:
    standins(tmp_path)
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture(scope="module")
def rehearsal(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("rehearsal")
    yield rehearse(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def _kit_copy(tmp: Path, edit=None) -> Path:
    kit = tmp / "kit"
    shutil.copytree(KIT, kit)
    if edit:
        edit(kit)
    return kit


# --- refusals before anything is launched ---

def test_paid_run_refuses_without_spend_authorization(tmp):
    launched = launch(tmp, "variant-clean", rehearsal=False, path=(tmp / "standins",))
    assert refused(launched, "PQ1C_SPEND_AUTHORIZED") and nothing_launched(tmp), launched.stderr


def test_rehearsal_refuses_while_a_spend_authorization_is_set(tmp):
    launched = launch(tmp, "variant-clean", authorized=True)
    assert refused(launched, "never runs while") and nothing_launched(tmp), launched.stderr


@pytest.mark.parametrize("installed", [True, False], ids=["installed-cli", "unmarked"])
def test_rehearsal_runs_only_a_marked_stand_in(tmp, installed):
    fake = (tmp / "home" / ".local" / "share" / "claude" / "versions" / "9.9.9") if installed else tmp / "unmarked"
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_text(f'#!/bin/sh\necho "$@" >> "{tmp}/fake-ran"\necho "9.9.9 (Claude Code)"\n')
    fake.chmod(0o700)
    (tmp / "looks-like-standins").mkdir()
    (tmp / "looks-like-standins" / "claude").symlink_to(fake)
    launched = launch(tmp, "variant-clean", PQ1C_REHEARSAL_STANDINS=str(tmp / "looks-like-standins"))
    gate = "installed Claude CLI" if installed else "not one of the kit's stand-ins"
    assert refused(launched, gate) and nothing_launched(tmp) and not (tmp / "fake-ran").exists(), launched.stderr


@pytest.mark.parametrize("edit", [
    ("inputs.json", "reviewer_model", "claude-fable-5-1"),
    ("inputs.json", "planner_model", "claude-opus-5-5"),
    ("inputs.json", "planner_model", "haiku"),
    ("providers.json", "providers.codex", "codex_metered"),
], ids=["fable-reviewer", "opus-planner", "alias", "codex-template"])
def test_launcher_refuses_any_binding_but_haiku_on_the_claude_metered_template(tmp, edit):
    name, key, value = edit
    kit = _kit_copy(tmp, lambda kit: edit_json(kit / name, lambda document: document.update({key: value})))
    launched = launch(tmp, "baseline-clean", kit=kit)
    assert refused(launched, "bindings:") and nothing_launched(tmp), launched.stderr


def test_launcher_refuses_a_source_that_binds_a_literal_model(tmp):
    runtime = tmp / "runtime"
    subprocess.run(["git", "clone", "-q", str(REPO), str(runtime)], check=True)
    source = runtime / "workflows" / "examples" / "design_review_execute.orc"
    source.write_text(source.read_text().replace(":model reviewer_model", ':model "claude-fable-5-1"', 1))
    launched = launch(tmp, "baseline-clean", runtime=runtime)
    assert refused(launched, "bindings:") and nothing_launched(tmp), launched.stderr


@pytest.mark.parametrize("name", ["inputs.json", "run_cell.sh", "cell_claude.sh", "readout.py", "criterion.json"])
def test_launcher_refuses_kit_files_other_than_the_manifests(tmp, name):
    def edit(kit):
        if name == "inputs.json":
            edit_json(kit / name, lambda inputs: inputs.update(task=inputs["task"] + " Also add a README."))
        elif name == "criterion.json":
            edit_json(kit / name, lambda criterion: criterion["thresholds"].update(retain_cost_ratio_at_or_below=0.95))
        else:
            (kit / name).write_text((kit / name).read_text() + "\n# changed\n")
    launched = launch(tmp, "variant-clean", kit=_kit_copy(tmp, edit))
    assert refused(launched, "differ from manifest.json") and nothing_launched(tmp), launched.stderr


@pytest.mark.parametrize("value, gate", [(None, "set PQ1C_MANIFEST_SHA256"), ("0" * 64, "not the ledger's")],
                         ids=["absent", "another"])
def test_launcher_refuses_without_the_ledgers_manifest_digest(tmp, value, gate):
    launched = launch(tmp, "variant-clean", PQ1C_MANIFEST_SHA256=value)
    assert refused(launched, gate) and nothing_launched(tmp), launched.stderr


def test_launcher_refuses_a_cli_version_other_than_the_first_cells(tmp):
    ledger(tmp).mkdir(parents=True)
    (ledger(tmp) / "claude-version").write_text("9.9.9 (Claude Code)\n")
    launched = launch(tmp, "variant-clean")
    assert refused(launched, "but the first cell ran") and paid_calls(tmp) == [], launched.stderr


def test_paid_run_refuses_the_no_provider_stub(tmp):
    log = NO_PROVIDER.parent / "no-provider.log"
    existed = log.exists()
    launched = launch(tmp, "variant-clean", rehearsal=False, authorized=True, path=(NO_PROVIDER,))
    assert refused(launched, "no-provider stub") and nothing_launched(tmp), launched.stderr
    assert log.exists() == existed                       # the stub was resolved, never run


def test_paid_run_refuses_a_kit_outside_a_committed_checkout(tmp):
    launched = launch(tmp, "variant-clean", kit=_kit_copy(tmp), rehearsal=False, authorized=True,
                      path=(tmp / "standins",))
    assert refused(launched, "not in a git checkout") and nothing_launched(tmp), launched.stderr
    assert invocations(tmp) == []


@pytest.mark.parametrize("cell", ["variant-extra", "variant-clean variant-resumed", "clean", "variant-clean\n"])
def test_launcher_refuses_a_cell_name_other_than_the_four(tmp, cell):
    launched = launch(tmp, cell)
    assert refused(launched, "not one of the four cells") and nothing_launched(tmp), launched.stderr


def test_launcher_refuses_a_run_path_where_another_directory_holds_a_provider_cli(tmp):
    python_dir = tmp / "python-bin"
    python_dir.mkdir()
    (python_dir / "python3").write_text(f'#!/bin/sh\nexec "{__import__("sys").executable}" "$@"\n')
    (python_dir / "codex").write_text("#!/bin/sh\nexit 0\n")
    for path in python_dir.iterdir():
        path.chmod(0o700)
    launched = launch(tmp, "variant-clean", PQ1C_PYTHON=str(python_dir / "python3"))
    assert refused(launched, "on the cell's PATH after the wrapper") and nothing_launched(tmp), launched.stderr


# --- the rehearsal ---

def test_rehearsal_cells_each_make_four_provider_calls(rehearsal):
    calls = paid_calls(rehearsal.parent)
    assert {cell: sum(Path(call["cwd"]).parent.name == cell for call in calls) for cell in CELLS} == dict.fromkeys(CELLS, 4)
    assert len(calls) == 16


def test_every_call_goes_through_the_wrapper_bound_to_haiku_on_the_metered_template(rehearsal):
    for call in paid_calls(rehearsal.parent):
        argv = call["argv"]
        assert (argv[:len(WRAPPER_FLAGS)], argv[argv.index("--model") + 1], "stream-json" in argv,
                call["in_cell"]) == (WRAPPER_FLAGS, MODEL, True, "1")


def test_every_slot_is_claimed_before_its_first_call(rehearsal):
    assert all(Path(call["cwd"]).parent.name in call["claimed"] for call in paid_calls(rehearsal.parent))


def test_rehearsal_refuses_to_run_a_cell_twice(rehearsal):
    again = launch(rehearsal.parent, "variant-clean")
    assert refused(again, "is used"), again.stderr
    assert sorted(path.name for path in rehearsal.glob("*-*")) == sorted(CELLS)


def test_each_cell_leaves_one_native_transcript_per_session(rehearsal):
    sessions = {cell: len(json.loads((rehearsal / cell / "cell.json").read_text())["native_sessions"]) for cell in CELLS}
    assert sessions == {"variant-clean": 2, "variant-resumed": 2, "baseline-clean": 4, "baseline-resumed": 4}


def test_the_cli_version_is_recorded_in_the_ledger_at_the_first_cell(rehearsal):
    assert (ledger(rehearsal.parent) / "claude-version").read_text().strip() == "0.0.0 (pq1c stand-in)"


def test_rehearsal_workspace_is_a_clone_of_the_consumer_design_docs_fixture(rehearsal, tmp_path):
    design_docs(tmp_path)
    expected = {path.relative_to(tmp_path).as_posix(): path.read_text() for path in tmp_path.rglob("*.md")}
    workspace = rehearsal / "variant-clean" / "workspace"
    assert {relpath: (workspace / relpath).read_text() for relpath in expected} == expected
    pinned = json.loads((KIT / "criterion.json").read_text())["fixture_commit"]
    assert {json.loads((rehearsal / cell / "cell.json").read_text())["fixture_commit"] for cell in CELLS} == {pinned}


def test_resumed_cells_stop_after_the_reviewers_first_turn_with_nothing_in_flight(rehearsal):
    for cell in ("variant-resumed", "baseline-resumed"):
        meta = json.loads((rehearsal / cell / "cell.json").read_text())
        stop = meta["stop"]
        assert (stop["exit"], stop["pending"], stop["last_identity"].endswith("/ feedback"), stop["attempts"],
                meta["resume_exit"]) == (75, 0, True, 2, 0), cell


def test_readout_of_the_rehearsal_passes_every_mechanism_axis_and_gives_improve_at_equal_cost(rehearsal):
    shown = outcome(rehearsal)
    cells = shown["cells"]
    assert {cell: (cells[cell]["completed"], cells[cell]["repeated_work"], cells[cell]["usage_recorded"],
                   cells[cell]["problems"]) for cell in CELLS} == dict.fromkeys(CELLS, (True, [], True, []))
    assert (shown["ratios"], shown["outcome"], shown["rehearsal"]) == ({"clean": 1.0, "resumed": 1.0}, "Improve", True)
    assert (cells["variant-clean"]["invalidate"]["passed"], cells["baseline-clean"]["invalidate"]["passed"]) == (True, True)


def test_the_variant_refuses_invalidate_unchanged_and_the_baseline_allows_it(rehearsal):
    variant = json.loads((rehearsal / "variant-clean" / "invalidate.json").read_text())
    baseline = json.loads((rehearsal / "baseline-clean" / "invalidate.json").read_text())
    assert ((variant["exit"], variant["coordinator_committed"], variant["bytes_unchanged"]), baseline["exit"]) == (
        (2, True, True), 0)


# --- the nesting guard ---

def test_a_claude_started_inside_a_cell_is_refused(tmp):
    (tmp / "standins" / "nest").touch()
    launched = launch(tmp, "baseline-clean")
    assert launched.returncode == 0, launched.stderr
    nested = json.loads((tmp / "standins" / "nested.json").read_text())
    cell = tmp / "results" / "baseline-clean"
    assert (nested["exit"], len(paid_calls(tmp)), len((cell / "nested-calls.log").read_text().splitlines())) == (97, 4, 4)


@pytest.mark.parametrize("probe, reason", [("stray", "native sessions for the workspace"),
                                           ("hooked", "hook records in the native transcripts")])
def test_a_session_or_hook_outside_the_journal_makes_the_cell_an_infrastructure_failure(tmp, probe, reason):
    (tmp / "standins" / probe).touch()
    launched = launch(tmp, "baseline-clean")
    assert launched.returncode == 0, launched.stderr
    checked = subprocess.run([__import__("sys").executable, "-B", str(KIT / "readout.py"), "--retry-check",
                              str(tmp / "results" / "baseline-clean")], capture_output=True, text=True, check=False)
    assert checked.returncode == 0 and reason in checked.stdout, checked.stdout


# --- the one infrastructure retry ---

@pytest.fixture(scope="module")
def retried(tmp_path_factory) -> Path:
    """variant-clean failed on its first call (infrastructure), then had the kit's one retry."""
    tmp = tmp_path_factory.mktemp("retried")
    standins(tmp, FAILING_PLAN)
    failed = launch(tmp, "variant-clean")
    assert failed.returncode == 0, failed.stderr
    standins(tmp)
    retry = launch(tmp, "variant-clean", PQ1C_INFRA_RETRY="the stand-in failed to launch")
    assert retry.returncode == 0, retry.stderr
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_an_infrastructure_failure_gets_the_one_retry_and_no_second(retried):
    assert sorted(path.name for path in ledger(retried).iterdir() if path.is_dir()) == ["variant-clean", "variant-clean-retry"]
    again = launch(retried, "variant-clean", PQ1C_INFRA_RETRY="again")
    other = launch(retried, "baseline-clean", PQ1C_INFRA_RETRY="another cell")
    assert refused(again, "one infrastructure retry is used") and refused(other, "one infrastructure retry is used")


def test_the_readout_uses_the_retry_and_names_the_attempt_it_replaced(retried, rehearsal):
    copy_cells(rehearsal, retried / "results", "variant-resumed", "baseline-clean", "baseline-resumed")
    shown = outcome(retried / "results")
    cell = shown["cells"]["variant-clean"]
    assert (shown["outcome"], cell["attempt_used"], cell["replaced"]["status"] != "completed") == ("Improve", "retry", True)
    assert any("no turn committed" in problem for problem in cell["replaced"]["why"])
    assert "recorded_cost_usd" in cell["replaced"]


def test_launcher_refuses_a_retry_of_a_cell_that_never_ran(tmp):
    launched = launch(tmp, "variant-resumed", PQ1C_INFRA_RETRY="never ran")
    assert refused(launched, "nothing to retry") and nothing_launched(tmp), launched.stderr


def test_launcher_refuses_a_retry_of_a_valid_observation(rehearsal):
    before = len(paid_calls(rehearsal.parent))
    launched = launch(rehearsal.parent, "baseline-resumed", PQ1C_INFRA_RETRY="did not like the cost")
    assert refused(launched, "not an infrastructure failure"), launched.stderr
    assert len(paid_calls(rehearsal.parent)) == before and not (rehearsal / "baseline-resumed-retry").exists()


def test_launcher_refuses_a_retry_while_the_first_attempt_runs(tmp):
    (tmp / "standins" / "slow").touch()
    first = launch(tmp, "baseline-clean", background=True)
    deadline = time.monotonic() + 120
    while not (ledger(tmp) / "baseline-clean" / "claimed").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    retry = launch(tmp, "baseline-clean", PQ1C_INFRA_RETRY="impatient")
    first.communicate(timeout=600)
    assert refused(retry, "still running") and first.returncode == 0, retry.stderr
    assert len(paid_calls(tmp)) == 4


def test_two_first_launches_at_once_run_one_cell_and_leave_no_debris(tmp):
    both = [launch(tmp, "baseline-clean", background=True) for _ in range(2)]
    for launched in both:
        launched.communicate(timeout=600)
    assert sorted(launched.returncode for launched in both) == [0, 3]
    assert len(paid_calls(tmp)) == 4
    assert sorted(path.name for path in (tmp / "results").iterdir()) == ["baseline-clean", "fixture.git"]


# --- the frozen files ---

def test_the_kit_files_are_the_manifests():
    manifest = json.loads((KIT / "manifest.json").read_text())
    defining = {"cell_claude.sh", "criterion.json", "inputs.json", "providers.json", "readout.py", "run_cell.sh"}
    assert set(manifest) == defining
    assert {name: hashlib.sha256((KIT / name).read_bytes()).hexdigest() for name in manifest} == manifest
