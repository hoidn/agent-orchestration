"""Shared defect repairs, Task 4: inlining substitutes specialized types.

Contract: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md
Task 4; decision brief case e
(docs/reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md
section 2.1); docs/design/workflow_lisp_pure_call_composition.md (a selected
body is normalized under its own bindings before it is transplanted).

A generic procedure with no effects that constructs an applied generic union
over its own type parameter is inlined into its caller at target 2.33. Every
program runs through the public run entry; effects are command-backed probes.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.workflow_lisp_generic_union_runtime_sources import HEADER


# `check` constructs over its own parameter and calls `lift`, a second
# generic procedure of the same kind.
GENERICS = """  (defunion Outcome :forall (T E)
    (OK (value T))
    (ERR (error E)))
  (defproc lift :forall (T) ((x T)) :where ((T is-record)) -> Outcome[T String]
    :effects () :lowering inline
    (variant Outcome[T String] OK :value x))
  (defproc check :forall (U) ((x U) (ok Bool)) :where ((U is-record)) -> Outcome[U String]
    :effects () :lowering inline
    (if ok (lift x) (variant Outcome[U String] ERR :error "rejected")))
"""

LIB = HEADER + '  (defmodule grt/lib)\n  (export Outcome lift check)\n' + GENERICS + ")\n"

NOTE_PROBE = """import json, os, sys
from pathlib import Path
text = " ".join(sys.argv[1:])
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(text + "\\n")
bundle = os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
Path(bundle).parent.mkdir(parents=True, exist_ok=True)
Path(bundle).write_text(json.dumps({"text": text}), encoding="utf-8")
"""

# The union crosses a workflow call before the `match`: a union built by
# pure code alone has no producing step and cannot be a `match` subject with
# effectful arms (decision brief case a, independent of generics).
CONSUMER = """  (defrecord Note (text String))
  (defproc note-ok ((c Cand)) -> Note
    :effects ((uses-command probe_note)) :lowering inline
    (command-result probe_note :argv ("python" "PROBE" "ok" c.title) :returns Note))
  (defproc note-err ((why String)) -> Note
    :effects ((uses-command probe_note)) :lowering inline
    (command-result probe_note :argv ("python" "PROBE" "err" why) :returns Note))
  (defworkflow make () -> Outcome[Cand String]
    CALL)
  (defworkflow run () -> Note
    (let* ((outcome (call make)))
      (match outcome
        ((OK hit) (note-ok hit.value))
        ((ERR miss) (note-err miss.error)))))
"""

CALLS = {
    "direct": ('(lift (record Cand :title "c"))', {"return__variant": "OK", "return__value__title": "c"}),
    "nested-ok": ('(check (record Cand :title "c") true)', {"return__variant": "OK", "return__value__title": "c"}),
    "nested-err": ('(check (record Cand :title "c") false)', {"return__variant": "ERR", "return__error": "rejected"}),
}

IMPORTED_JOIN_DEFECT = pytest.mark.xfail(
    strict=True,
    reason=(
        "separate defect, reproduced at 5c88cd2d without inlining: in the importer, the `if` of an "
        "imported generic body joins `grt/lib::Outcome[Cand String]` (sibling call) with "
        "`Outcome[Cand String]` (own constructor) and rejects it as type_mismatch"
    ),
)


def _install(root: Path, body: str, *, imported: bool, probes: dict[str, Path] | None = None) -> dict[str, Path]:
    entry = (
        HEADER
        + "  (defmodule grt/entry)\n"
        + ("  (import grt/lib :only (Outcome lift check))\n" if imported else "")
        + "  (export run)\n  (defrecord Cand (title String))\n"
        + ("" if imported else GENERICS)
        + body
        + ")\n"
    )
    _write_sources(root, {"grt/entry.orc": entry, **({"grt/lib.orc": LIB} if imported else {})})
    return _public_run_files(root, probes or {})


def _program(call: str) -> str:
    return f"  (defworkflow run () -> Outcome[Cand String]\n    {call})\n"


def _cases():
    for case in sorted(CALLS):
        for imported in (False, True):
            marks = IMPORTED_JOIN_DEFECT if imported and case.startswith("nested") else ()
            yield pytest.param(case, imported, marks=marks, id=f"{case}-{'imported' if imported else 'own-module'}")


@pytest.mark.parametrize(("case", "imported"), _cases())
def test_generic_constructor_is_inlined_with_its_specialized_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, imported: bool
) -> None:
    call, expected = CALLS[case]
    files = _install(tmp_path, _program(call), imported=imported)
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (0, expected)


@pytest.mark.parametrize(
    ("case", "imported", "expected"),
    [("nested-ok", False, "ok c"), ("nested-err", False, "err rejected"), ("direct", True, "ok c")],
    ids=["ok-arm-own-module", "err-arm-own-module", "ok-arm-imported"],
)
def test_caller_matches_the_returned_union_with_effectful_arms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, imported: bool, expected: str
) -> None:
    probe = _write_probe(tmp_path, "probe_note", NOTE_PROBE)
    body = CONSUMER.replace("PROBE", probe.as_posix()).replace("CALL", CALLS[case][0])
    files = _install(tmp_path, body, imported=imported, probes={"probe_note": probe})
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs or {}), _log(probe)) == (
        0,
        {"return__text": expected},
        [expected],
    )


@pytest.mark.parametrize("imported", [False, True], ids=["own-module", "imported"])
@pytest.mark.parametrize("case", sorted(CALLS))
def test_retargeted_to_2_32_the_program_is_rejected_at_the_generic_union(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    imported: bool,
    case: str,
) -> None:
    """Control: generic unions start at 2.33, so older targets never reach this inlining."""

    files = _install(tmp_path, _program(CALLS[case][0]), imported=imported)
    for source in (tmp_path / "grt").glob("*.orc"):
        source.write_text(source.read_text(encoding="utf-8").replace('"2.33"', '"2.32"'), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.ERROR):
        result = _public_run(files)

    declaring = "lib.orc" if imported else "entry.orc"
    assert (result.exit_code, f"grt/{declaring}:" in caplog.text, "[generic_union_requires_dsl_2_33]" in caplog.text) == (
        2,
        True,
        True,
    )
