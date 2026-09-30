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
import re
from pathlib import Path

import pytest

from orchestrator.cli.commands.resume import resume_workflow
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

_DIAGNOSTIC_HEAD = re.compile(r"(?P<path>.+):(?P<line>\d+):(?P<column>\d+): \[(?P<code>[a-z0-9_]+)\] ")
_REASON_NOTE = re.compile(r"^note: reason: (?P<reason>\S+)$", re.MULTILINE)


def _rejection(caplog: pytest.LogCaptureFixture) -> dict[str, object]:
    """Parse the one logged ERROR as a diagnostic: its code, reason and source location."""

    [text] = _errors(caplog)
    head = _DIAGNOSTIC_HEAD.match(text)
    reason = _REASON_NOTE.search(text)
    if head is None or reason is None:
        return {"unparsed": text}
    return {
        "file": Path(head["path"]).name,
        "line": int(head["line"]),
        "column": int(head["column"]),
        "code": head["code"],
        "reason": reason["reason"],
    }


def _replay_rejection(file: str, line: int, column: int) -> dict[str, object]:
    return {
        "file": file,
        "line": line,
        "column": column,
        "code": "pure_result_replay_unavailable",
        "reason": "dependency_index_invalid",
    }


def _replay_location(file: str, line: int, column: int) -> dict[str, object]:
    return {
        key: value
        for key, value in _replay_rejection(file, line, column).items()
        if key != "reason"
    }


def _diagnostic_location(text: str) -> dict[str, object]:
    head = _DIAGNOSTIC_HEAD.match(text)
    assert head is not None, text
    return {
        "file": Path(head["path"]).name,
        "line": int(head["line"]),
        "column": int(head["column"]),
        "code": head["code"],
    }


def _replay_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "[pure_result_replay_unavailable]" in record.getMessage()
    ]
    caplog.clear()
    return warnings


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


# The known defect: `--dry-run` rejects it exactly as the run start does, at the
# authored tail `match` (column 7; line 19, or 28 after the multi-line loop subject)
# that generated the rejected binding.


@pytest.mark.parametrize(
    ("subject", "target", "line"),
    [(COMMAND_SUBJECT, "2.14", 19), (COMMAND_SUBJECT, "2.33", 19), (LOOP_SUBJECT, "2.32", 28), (LOOP_SUBJECT, "2.33", 28)],
    ids=["command-union-2.14", "command-union-2.33", "loop-union-2.32", "loop-union-2.33"],
)
def test_dry_run_rejects_a_record_building_tail_match_as_the_run_start_does(
    workspace: Path, caplog: pytest.LogCaptureFixture, subject: str, target: str, line: int
) -> None:
    files = _program(workspace, subject=subject, tail=RECORD_TAIL, target=target)

    dry = _dry_run(files)
    dry_rejection = _rejection(caplog)
    run = _public_run(files)
    run_rejection = _rejection(caplog)

    expected = _replay_rejection("entry.orc", line, 7)
    assert ((dry.exit_code, dry_rejection), (run.exit_code, run_rejection)) == ((2, expected), (2, expected))


LIBRARY = REPO_ROOT / "workflows" / "library"
WATCHDOG_EXTERNS = REPO_ROOT / "workflows" / "examples" / "inputs" / "workflow_lisp_migrations" / "generic_run_watchdog"


def test_dry_run_accepts_the_shipped_watchdog(workspace: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The documented launch of `generic_run_watchdog/watchdog.orc` (workflows/README.md).

    Its source avoids the rejected shape: the repair arm passes the provider's
    fields to the publisher and binds no pure value over them."""

    files = {
        "source": LIBRARY / "generic_run_watchdog" / "watchdog.orc",
        "source_root": LIBRARY,
        **{name: Path(f"{WATCHDOG_EXTERNS}.{name}.json") for name in ("providers", "prompts", "commands")},
    }
    inputs = workspace / "inputs.json"
    inputs.write_text(
        json.dumps({"target_run_id": "no-such-run", "target_workspace": "/no/such/workspace"}), encoding="utf-8"
    )

    result = _dry_run(files, entry="generic_run_watchdog/watchdog::watchdog", input_file=inputs)

    assert (result.exit_code, _errors(caplog)) == (0, [])


# A called workflow runs in its own frame from its own bundle. `--dry-run` derives
# the index of every bundle a run derives one for, once each, and names the call
# sites that reach a rejected one.

CHILD = """  (defworkflow child () -> Summary
    (let* ((result (check "revise-a")))
      (match result
        ((OK ok) (record Summary :outcome "ok" :title ok.value.title))
        ((ERROR err) (record Summary :outcome "error" :title err.error)))))
"""
SAFE_CHILD = """  (defworkflow safe () -> Summary
    (record Summary :outcome "safe" :title "skipped"))
"""
CALLERS = {
    "called": "  (defworkflow run () -> Summary\n    (call child)))\n",
    "chain": "  (defworkflow mid () -> Summary\n    (call child))\n  (defworkflow run () -> Summary\n    (call mid)))\n",
    "two-call-sites": """  (defworkflow run () -> Summary
    (let* ((first (call child)) (second (call child)))
      (record Summary :outcome first.outcome :title second.title))))
""",
    "in-loop": """  (defworkflow run () -> Summary
    (loop/recur :max 2
      :state (loop-state (n Int 0))
      :on-exhausted (record Summary :outcome "exhausted" :title "none")
      (fn (state)
        (let* ((summary (call child)))
          (done summary))))))
""",
    "match-arm": """  (defworkflow run () -> Summary
    (let* ((result (check "approve-a")))
        (match result
        ((OK ok) (call child))
        ((ERROR err) (call safe))))))
""",
    "false-if": """  (defworkflow run () -> Summary
    (if false
      (call child)
      (record Summary :outcome "safe" :title "skipped"))))
""",
    "inner-conditional-chain": """  (defworkflow mid () -> Summary
    (if false
      (call child)
      (record Summary :outcome "safe" :title "skipped")))
  (defworkflow run () -> Summary
    (call mid)))
""",
    "outer-conditional-chain": """  (defworkflow mid () -> Summary
    (call child))
  (defworkflow run () -> Summary
    (if false
      (call mid)
      (record Summary :outcome "safe" :title "skipped"))))
""",
    "loop-descendant": """  (defworkflow mid () -> Summary
    (call child))
  (defworkflow run () -> Summary
    (loop/recur :max 1
      :state (loop-state (n Int 0))
      :on-exhausted (record Summary :outcome "exhausted" :title "none")
      (fn (state)
        (let* ((summary (call mid)))
          (done summary))))))
""",
    "shared-conditional-and-unconditional": """  (defworkflow run () -> Summary
    (let* ((maybe (if false
                   (call child)
                   (record Summary :outcome "safe" :title "skipped")))
           (always (call child)))
      always)))
""",
}
IMPORTING_ENTRY = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule grt/entry)
  (import grt/lib :only (Summary child))
  (export run)
  (defworkflow run () -> Summary
    (call child)))
"""
_CALL_SITE_NOTE = re.compile(r"^note: workflow call site at (?P<path>.+):(?P<line>\d+):(?P<column>\d+)$", re.MULTILINE)


def _caller_program(root: Path, caller: str) -> dict[str, Path]:
    """`grt/entry::run` reaching `child`, whose tail `match` (entry.orc:19:7) is rejected."""

    probe = _write_probe(root, "probe_check", OUTCOME_PROBE)
    if caller in {"imported", "imported-conditional"}:
        library = PROLOGUE.replace("(defmodule grt/entry)\n  (export run)", "(defmodule grt/lib)\n  (export Summary child)")
        entry = IMPORTING_ENTRY
        if caller == "imported-conditional":
            entry = entry.replace(
                "(call child)",
                '(if false (call child) (record Summary :outcome "ok" :title "skipped"))',
            )
        sources = {"grt/lib.orc": library + CHILD.rstrip() + ")\n", "grt/entry.orc": entry}
    else:
        sources = {"grt/entry.orc": PROLOGUE + CHILD + SAFE_CHILD + CALLERS[caller]}
    _write_sources(
        root, {path: text.replace("TARGET", "2.33").replace("PROBE_CHECK", probe.as_posix()) for path, text in sources.items()}
    )
    return {**_public_run_files(root, {"probe_check": probe}), "probe": probe}


def _call_sites(caplog: pytest.LogCaptureFixture) -> list[tuple[str, int, int]]:
    """The call-site notes of the one logged ERROR, innermost first; the ERROR stays for `_rejection`."""

    [text] = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    return _call_sites_in(text)


def _call_sites_in(text: str) -> list[tuple[str, int, int]]:
    return [(Path(note["path"]).name, int(note["line"]), int(note["column"])) for note in _CALL_SITE_NOTE.finditer(text)]


def _source_location(source: Path, form: str, occurrence: int = 1) -> tuple[str, int, int]:
    matches = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        offset = 0
        while (index := line.find(form, offset)) >= 0:
            matches.append((line_number, index + 1))
            offset = index + len(form)
    line, column = matches[occurrence - 1]
    return source.name, line, column


@pytest.mark.parametrize(
    ("caller", "rejected_in"),
    [
        ("called", "entry.orc"),
        ("imported", "lib.orc"),
        ("chain", "entry.orc"),
        ("two-call-sites", "entry.orc"),
    ],
)
def test_dry_run_rejects_a_called_workflow_as_the_run_does(
    workspace: Path, caplog: pytest.LogCaptureFixture, caller: str, rejected_in: str
) -> None:
    files = _caller_program(workspace, caller)

    dry = _dry_run(files)
    dry_call_sites = _call_sites(caplog)
    dry_rejection = _rejection(caplog)
    run = _public_run(files)
    run_rejection = _rejection(caplog)

    expected = _replay_rejection(rejected_in, 19, 7)
    if caller in {"called", "imported"}:
        expected_call_sites = [_source_location(files["source"], "(call child)")]
    elif caller == "chain":
        expected_call_sites = [
            _source_location(files["source"], "(call child)"),
            _source_location(files["source"], "(call mid)"),
        ]
    else:
        expected_call_sites = [
            _source_location(files["source"], "(call child)")
        ]
    assert ((dry.exit_code, dry_rejection, dry_call_sites), (run.exit_code, run_rejection)) == (
        (2, expected, expected_call_sites),
        (2, expected),
    )


def test_a_rejected_workflow_called_only_inside_a_loop_passes_dry_run_as_it_runs(workspace: Path) -> None:
    """A call frame inside a loop iteration runs without the replay profile, so the run derives no index for it."""

    files = _caller_program(workspace, "in-loop")

    dry = _dry_run(files)
    run = _public_run(files)

    assert (dry.exit_code, run.exit_code) == (0, 0)


@pytest.mark.parametrize(
    "caller",
    ["match-arm", "false-if", "inner-conditional-chain", "outer-conditional-chain", "imported-conditional"],
    ids=["match-arm", "false-if", "inner-conditional-chain", "outer-conditional-chain", "imported-conditional"],
)
def test_dry_run_warns_for_a_callee_that_control_flow_may_skip(
    workspace: Path, caplog: pytest.LogCaptureFixture, caller: str
) -> None:
    files = _caller_program(workspace, caller)

    dry = _dry_run(files)
    [warning] = _replay_warnings(caplog)
    warning_call_sites = _call_sites_in(warning)
    run = _public_run(files)

    if caller == "inner-conditional-chain":
        expected_sites = [
            _source_location(files["source"], "(call child"),
            _source_location(files["source"], "(call mid)"),
        ]
    elif caller == "outer-conditional-chain":
        expected_sites = [
            _source_location(files["source"], "(call child)"),
            _source_location(files["source"], "(call mid)"),
        ]
    elif caller == "false-if":
        expected_sites = [_source_location(files["source"], "(call child)")]
    elif caller == "imported-conditional":
        expected_sites = [_source_location(files["source"], "(call child)")]
    else:
        expected_sites = [_source_location(files["source"], "(call child)")]
    rejected_location = (
        _replay_location("lib.orc", 19, 7)
        if caller == "imported-conditional"
        else _replay_location("entry.orc", 19, 7)
    )
    assert (
        dry.exit_code,
        _diagnostic_location(warning),
        warning_call_sites,
        run.exit_code,
        _errors(caplog),
    ) == (
        0,
        rejected_location,
        expected_sites,
        0,
        [],
    )


def test_dry_run_warns_for_rejected_descendant_reached_through_a_loop(
    workspace: Path, caplog: pytest.LogCaptureFixture
) -> None:
    files = _caller_program(workspace, "loop-descendant")

    dry = _dry_run(files)
    [warning] = _replay_warnings(caplog)
    warning_call_sites = _call_sites_in(warning)
    run = _public_run(files)
    run_rejection = _rejection(caplog)

    assert (
        dry.exit_code,
        _diagnostic_location(warning),
        warning_call_sites,
        run.exit_code,
        run_rejection,
    ) == (
        0,
        _replay_location("entry.orc", 19, 7),
        [
            _source_location(files["source"], "(call child)"),
            _source_location(files["source"], "(call mid)"),
        ],
        2,
        _replay_rejection("entry.orc", 19, 7),
    )


def test_unconditional_call_path_wins_when_a_callee_is_also_conditional(
    workspace: Path, caplog: pytest.LogCaptureFixture
) -> None:
    files = _caller_program(workspace, "shared-conditional-and-unconditional")

    dry = _dry_run(files)
    dry_call_sites = _call_sites(caplog)
    dry_rejection = _rejection(caplog)
    run = _public_run(files)
    run_rejection = _rejection(caplog)

    assert (
        dry.exit_code,
        dry_rejection,
        dry_call_sites,
        run.exit_code,
        run_rejection,
    ) == (
        2,
        _replay_rejection("entry.orc", 19, 7),
        [_source_location(files["source"], "(call child)", occurrence=2)],
        2,
        _replay_rejection("entry.orc", 19, 7),
    )


# The source location is an improvement on the rejection, never a replacement:
# when the compiled source map cannot place the rejected node, the rejection is
# printed at the workflow file, without a line, with a note that says why.

_UNLOCATED_HEAD = re.compile(r"(?P<path>[^:\n]+): \[(?P<code>[a-z0-9_]+)\] ")
_UNLOCATED_NOTE = re.compile(r"^note: source location could not be determined: (?P<why>.+)$", re.MULTILINE)


def _stale_structure(source_map: Path) -> None:
    payload = json.loads(source_map.read_text(encoding="utf-8"))
    for workflow in payload["workflows"].values():
        workflow["executable_nodes"] = None
    source_map.write_text(json.dumps(payload), encoding="utf-8")


def _moved_source(source_map: Path) -> None:
    entry = source_map.parents[3] / "grt" / "entry.orc"
    text = source_map.read_text(encoding="utf-8")
    source_map.write_text(text.replace(entry.as_posix(), entry.with_name("moved.orc").as_posix()), encoding="utf-8")


@pytest.mark.parametrize(
    ("damage", "why"),
    [
        (Path.unlink, "No such file or directory"),
        (lambda path: path.write_text(path.read_text(encoding="utf-8")[:200], encoding="utf-8"), "JSONDecodeError"),
        (_stale_structure, "TypeError"),
        (_moved_source, "moved.orc, which does not exist"),
    ],
    ids=["removed", "truncated", "stale-structure", "points-at-a-missing-source-file"],
)
def test_a_rejection_whose_source_map_cannot_place_it_is_still_reported(
    workspace: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, damage, why: str
) -> None:
    import orchestrator.cli.commands.run as run_module

    build = run_module.build_frontend_bundle

    def build_then_damage_the_source_map(request):
        result = build(request)
        damage(result.validated_bundle.provenance.frontend_source_trace_path)
        return result

    monkeypatch.setattr(run_module, "build_frontend_bundle", build_then_damage_the_source_map)
    files = _program(workspace, subject=COMMAND_SUBJECT, tail=RECORD_TAIL)

    result = _dry_run(files)

    [text] = _errors(caplog)
    head, reason, unlocated = _UNLOCATED_HEAD.match(text), _REASON_NOTE.search(text), _UNLOCATED_NOTE.search(text)
    assert (result.exit_code, head and head.groupdict(), reason and reason["reason"], "\nnote: ref: root.steps." in text) == (
        2,
        {"path": (workspace / "grt" / "entry.orc").as_posix(), "code": "pure_result_replay_unavailable"},
        "dependency_index_invalid",
        True,
    )
    assert unlocated is not None and why in unlocated["why"], text


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


def test_dry_run_of_a_rejected_callee_runs_no_command_and_creates_no_run_directory(workspace: Path) -> None:
    files = _caller_program(workspace, "called")
    before = _tree(workspace)

    result = _dry_run(files)

    assert (result.exit_code, result.run_id, _log(files["probe"]), _tree(workspace)) == (2, None, [], before)


# `resume` prints the rejection as `run` does, whether it resumes or restarts.


@pytest.mark.parametrize("force_restart", [False, True], ids=["resume", "force-restart"])
def test_resume_reports_the_rejection_as_run_does(
    workspace: Path, caplog: pytest.LogCaptureFixture, force_restart: bool
) -> None:
    files = _program(workspace, subject=COMMAND_SUBJECT, tail=RECORD_TAIL)
    run = _public_run(files)
    run_rejection = _rejection(caplog)

    exit_code = resume_workflow(run_id=run.run_id, force_restart=force_restart, retry_delay_ms=0)

    assert (exit_code, _rejection(caplog)) == (1, run_rejection)
