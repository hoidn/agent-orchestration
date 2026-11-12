"""`--dry-run` derives the pure-result replay index a run derives at its start.

Contract: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md,
Task 7 and Review Focus item 5; decision brief
docs/reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md,
section 2.1 case d.

A pure tail `match` whose arms build a record from a matched command or loop
union result is a known lowering defect: the run is rejected at start, before
any effect. These tests fix that `--dry-run` reports the same rejection, that it
still accepts the programs that run today, and that it runs no command and
writes no run state. Every program runs through `run_workflow`; commands are
command-backed probes that log their argv.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from orchestrator.cli.commands.run import run_workflow
from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.test_workflow_lisp_improve_example_e2e import ENTRY as EXAMPLE_ENTRY, _install
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args
from tests.workflow_lisp_generic_union_runtime_sources import OUTCOME_PROBE
from tests.workflow_lisp_improve_example_sources import EXAMPLE, REPO_ROOT
from tests.workflow_lisp_improve_stdlib_sources import (
    REVIEW_PROBE,
    REVISE_PROBE,
    SUMMARIZE_PROBE,
    entry_source,
    inline_entry_source,
    string_inputs_entry_source,
    unnamed_union_caller_sources,
    wrapped_review_sources,
)


PROLOGUE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Candidate (title String) (score Int))
  (defunion Verdict
    (OK (value Candidate))
    (ERROR (error String)))
  (defrecord Summary (outcome String) (title String))
  (defproc check ((title String)) -> Verdict
    :effects ((uses-command probe_check))
    :lowering inline
    (command-result probe_check
      :argv ("python" "PROBE_CHECK" title)
      :returns Verdict))
"""

COMMAND_SUBJECT = '(check "revise-a")'

LOOP_SUBJECT = """(loop/recur :max 3
              :state (loop-state (current Candidate (record Candidate :title "seed" :score 0)))
              :on-exhausted (variant Verdict ERROR :error "exhausted")
              (fn (state)
                (let* ((verdict (check state.current.title)))
                  (match verdict
                    ((OK ok) (done verdict))
                    ((ERROR err)
                     (continue (loop-state :like state
                                 :current (record Candidate :title err.error :score 1))))))))"""

RECORD_TAIL = """  (defworkflow run () -> Summary
    (let* ((result SUBJECT))
      (match result
        ((OK ok) (record Summary :outcome "ok" :title ok.value.title))
        ((ERROR err) (record Summary :outcome "error" :title err.error))))))
"""

SCALAR_TAIL = """  (defworkflow run () -> String
    (let* ((result SUBJECT))
      (match result
        ((OK ok) ok.value.title)
        ((ERROR err) err.error)))))
"""

UNKNOWN_MEMBER = "Validation error: pure replay binding references an unknown result member"
CONTRACT_DISAGREES = "Validation error: pure replay source contract disagrees with its binding type"


def _program(root: Path, *, subject: str, tail: str, target: str = "2.33") -> dict[str, Path]:
    """Write one `grt/entry::run` over the `probe_check` command; return its public run files."""

    probe = _write_probe(root, "probe_check", OUTCOME_PROBE)
    source = (PROLOGUE + tail.replace("SUBJECT", subject)).replace("TARGET", target)
    _write_sources(root, {"grt/entry.orc": source.replace("PROBE_CHECK", probe.as_posix())})
    return {**_public_run_files(root, {"probe_check": probe}), "probe": probe}


def _dry_run(files: dict[str, Path], *, entry: str = "run", input_file: Path | None = None):
    args = _run_args(files, input_file=input_file)
    args.entry_workflow = entry
    args.command_boundaries_file = str(files["commands"])
    args.dry_run = True
    return run_workflow(args)


def _errors(caplog: pytest.LogCaptureFixture) -> list[str]:
    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    caplog.clear()
    return errors


def _tree(root: Path) -> set[str]:
    """Every path under `root` except the frontend build artifacts, which any build writes."""

    paths = {path.relative_to(root).as_posix() for path in root.rglob("*")}
    return {path for path in paths if path != ".orchestrate" and not path.startswith(".orchestrate/build")}


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


# The known defect: `--dry-run` rejects it exactly as the run start does.


@pytest.mark.parametrize(
    ("subject", "target", "diagnostic"),
    [
        (COMMAND_SUBJECT, "2.14", CONTRACT_DISAGREES),
        (COMMAND_SUBJECT, "2.33", CONTRACT_DISAGREES),
        (LOOP_SUBJECT, "2.32", UNKNOWN_MEMBER),
        (LOOP_SUBJECT, "2.33", UNKNOWN_MEMBER),
    ],
    ids=["command-union-2.14", "command-union-2.33", "loop-union-2.32", "loop-union-2.33"],
)
def test_dry_run_rejects_a_record_building_tail_match_as_the_run_start_does(
    workspace: Path, caplog: pytest.LogCaptureFixture, subject: str, target: str, diagnostic: str
) -> None:
    files = _program(workspace, subject=subject, tail=RECORD_TAIL, target=target)

    dry = _dry_run(files)
    dry_errors = _errors(caplog)
    run = _public_run(files)
    run_errors = _errors(caplog)

    assert ((dry.exit_code, dry_errors), (run.exit_code, run_errors)) == ((2, [diagnostic]), (2, [diagnostic]))


# No false rejection: programs that run today still pass `--dry-run`.


@pytest.mark.parametrize(
    ("subject", "value"), [(COMMAND_SUBJECT, "revise-a"), (LOOP_SUBJECT, "revise-seed")], ids=["command-union", "loop-union"]
)
def test_a_scalar_tail_match_passes_dry_run_and_runs(workspace: Path, subject: str, value: str) -> None:
    files = _program(workspace, subject=subject, tail=SCALAR_TAIL)

    dry = _dry_run(files)
    run = _public_run(files)

    assert (dry.exit_code, run.exit_code, dict(run.workflow_outputs)) == (0, 0, {"__result__": value})


def _improve_probes(root: Path) -> dict[str, Path]:
    return {
        name: _write_probe(root, name, text)
        for name, text in (("probe_review", REVIEW_PROBE), ("probe_revise", REVISE_PROBE), ("probe_summarize", SUMMARIZE_PROBE))
    }


def _improve_caller(shape: str, probes: dict[str, Path]) -> dict[str, str]:
    entry = entry_source(seed="draft", limit=3, probes=probes)
    if shape == "imported":
        return {"grt/entry.orc": entry}
    if shape == "inline":
        return {"grt/entry.orc": inline_entry_source(entry)}
    if shape == "wrapped-review":
        return wrapped_review_sources(entry, probes)
    if shape == "string-inputs":
        return {"grt/entry.orc": string_inputs_entry_source(entry)}
    return unnamed_union_caller_sources(seed="draft", limit=2, target=shape.rsplit("-", 1)[1], probes=probes)


@pytest.mark.parametrize(
    "shape",
    ["imported", "inline", "wrapped-review", "string-inputs", "unnamed-union-2.28", "unnamed-union-2.32", "unnamed-union-2.33"],
)
def test_std_improve_callers_pass_dry_run(workspace: Path, shape: str) -> None:
    probes = _improve_probes(workspace)
    _write_sources(workspace, _improve_caller(shape, probes))
    inputs = workspace / "inputs.json"
    inputs.write_text(json.dumps({"goal": "steady"}), encoding="utf-8")

    result = _dry_run(_public_run_files(workspace, probes), input_file=inputs if shape == "string-inputs" else None)

    assert result.exit_code == 0


def test_the_shipped_example_passes_dry_run(workspace: Path) -> None:
    files = _install(workspace, EXAMPLE.read_text(encoding="utf-8"))

    assert _dry_run(files, entry=EXAMPLE_ENTRY, input_file=files["inputs"]).exit_code == 0


SINGLE_CALL_WORKFLOWS = REPO_ROOT / "experiments" / "orc_vs_single_call" / "workflows"


@pytest.mark.parametrize(
    ("module", "entry", "inputs"),
    [
        ("best_of_n", "best-of-n", {"task": "t", "intent": "i", "repos": ["/tmp/a", "/tmp/b"]}),
        ("best_of_n", "select-only", {"intent": "i", "repos": ["/tmp/a"], "accounts": ["a"]}),
        ("reviewed_change", "reviewed-change", {"task": "t", "intent": "i", "repo": "/tmp/a"}),
    ],
)
def test_the_single_call_comparison_workflows_pass_dry_run(workspace: Path, module: str, entry: str, inputs: dict) -> None:
    files = {
        "source": SINGLE_CALL_WORKFLOWS / f"{module}.orc",
        "source_root": SINGLE_CALL_WORKFLOWS,
        "providers": SINGLE_CALL_WORKFLOWS / f"{module}.providers.json",
        **{name: workspace / f"{name}.json" for name in ("prompts", "commands", "inputs")},
    }
    files["prompts"].write_text("{}", encoding="utf-8")
    files["commands"].write_text("{}", encoding="utf-8")
    files["inputs"].write_text(json.dumps(inputs), encoding="utf-8")

    assert _dry_run(files, entry=f"{module}::{entry}", input_file=files["inputs"]).exit_code == 0


# `--dry-run` runs no command and writes no run state, whether it accepts or rejects.


@pytest.mark.parametrize(
    ("subject", "tail", "exit_code"),
    [(COMMAND_SUBJECT, RECORD_TAIL, 2), (LOOP_SUBJECT, RECORD_TAIL, 2), (COMMAND_SUBJECT, SCALAR_TAIL, 0), (LOOP_SUBJECT, SCALAR_TAIL, 0)],
    ids=["rejected-command-union", "rejected-loop-union", "accepted-command-union", "accepted-loop-union"],
)
def test_dry_run_runs_no_command_and_creates_no_run_directory(workspace: Path, subject: str, tail: str, exit_code: int) -> None:
    files = _program(workspace, subject=subject, tail=tail)
    before = _tree(workspace)

    result = _dry_run(files)

    assert (result.exit_code, result.run_id, _log(files["probe"]), _tree(workspace)) == (exit_code, None, [], before)
