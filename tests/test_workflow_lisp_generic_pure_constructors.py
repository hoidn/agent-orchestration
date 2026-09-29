"""Shared defect repairs, Task 4: an inlined body keeps its defining module's types.

Contract: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md
Task 4; decision brief case e
(docs/reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md
section 2.1); docs/design/workflow_lisp_pure_call_composition.md (a selected
body is normalized under its defining-module environment before it is
transplanted).

At target 2.33 a procedure with no effects is inlined with the types its own
module resolves: an applied generic union over its own type parameter, a
union joined with a sibling generic call, and a type its caller cannot see.
Targets 2.30 to 2.32 keep their behaviour. Every program runs through the
public run entry; effects are command-backed probes.
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


@pytest.mark.parametrize("imported", [False, True], ids=["own-module", "imported"])
@pytest.mark.parametrize("case", sorted(CALLS))
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


# The review's join program: the caller imports `choose` but not `lift`, and
# `choose` joins a call to `lift` with its own constructor of the same union.
JOIN_LIB = HEADER + """  (defmodule grt/lib)
  (export Result lift choose)
  (defunion Result :forall (T E) (YES (value T)) (NO (error E)))
  (defproc lift :forall (T) ((x T)) :where ((T is-record)) -> Result[T String]
    :effects () :lowering inline
    (variant Result[T String] YES :value x))
  (defproc choose :forall (U) ((x U) (flag Bool)) :where ((U is-record)) -> Result[U String]
    :effects () :lowering inline
    (if flag (lift x) (variant Result[U String] NO :error "no")))
)
"""

JOIN_ENTRY = HEADER + """  (defmodule grt/entry)
  (import grt/lib :only (Result choose))
  (export run)
  (defrecord Candidate (name String))
  (defworkflow run () -> Result[Candidate String]
    (choose (record Candidate :name "c") FLAG))
)
"""


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("true", {"return__variant": "YES", "return__value__name": "c"}),
        ("false", {"return__variant": "NO", "return__error": "no"}),
    ],
    ids=["sibling-call-branch", "own-constructor-branch"],
)
def test_imported_generic_body_joins_a_sibling_call_with_its_own_constructor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str, expected: dict[str, str]
) -> None:
    _write_sources(tmp_path, {"grt/lib.orc": JOIN_LIB, "grt/entry.orc": JOIN_ENTRY.replace("FLAG", flag)})
    files = _public_run_files(tmp_path, {})
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (0, expected)


# `Secret` is not exported, so the caller cannot name it; the inlined body
# constructs it all the same.
HIDDEN_LIBS = {
    "non-generic": """  (defmodule grt/lib)
  (export Result make)
  (defrecord Secret (name String))
  (defunion Result (YES (value Secret)) (NO (error String)))
  (defproc make ((name String)) -> Result :effects () :lowering inline
    (variant Result YES :value (record Secret :name name)))
)
""",
    "generic": """  (defmodule grt/lib)
  (export Result make)
  (defrecord Secret (name String))
  (defunion Result :forall (T E) (YES (value T)) (NO (error E)))
  (defproc make :forall (T) ((x T) (ok Bool)) :where ((T is-record)) -> Result[T String]
    :effects () :lowering inline
    (let* ((secret (record Secret :name "hidden")))
      (if ok (variant Result[T String] YES :value x) (variant Result[T String] NO :error secret.name))))
)
""",
}

HIDDEN_ENTRIES = {
    "non-generic": """  (defmodule grt/entry)
  (import grt/lib :only (Result make))
  (export run)
  (defworkflow run () -> Result (make "x"))
)
""",
    "generic": """  (defmodule grt/entry)
  (import grt/lib :only (Result make))
  (export run)
  (defrecord Candidate (name String))
  (defworkflow run () -> Result[Candidate String] (make (record Candidate :name "c") false))
)
""",
}


def _install_hidden(root: Path, case: str, target: str) -> dict[str, Path]:
    header = HEADER.replace('"2.33"', f'"{target}"')
    _write_sources(root, {"grt/lib.orc": header + HIDDEN_LIBS[case], "grt/entry.orc": header + HIDDEN_ENTRIES[case]})
    return _public_run_files(root, {})


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("non-generic", {"return__variant": "YES", "return__value__name": "x"}),
        ("generic", {"return__variant": "NO", "return__error": "hidden"}),
    ],
    ids=["non-generic", "generic"],
)
def test_inlined_body_constructs_a_type_its_caller_cannot_see(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, expected: dict[str, str]
) -> None:
    files = _install_hidden(tmp_path, case, "2.33")
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (0, expected)


@pytest.mark.parametrize("target", ["2.30", "2.32"])
def test_before_2_33_the_hidden_type_stays_unknown_in_the_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, target: str
) -> None:
    """Control for the 2.33 gate: older targets keep the diagnostic they give at `5c88cd2d`."""

    files = _install_hidden(tmp_path, "non-generic", target)
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.ERROR):
        result = _public_run(files)

    assert (result.exit_code, "grt/entry.orc:7:33: [type_unknown] unknown type `Secret`" in caplog.text) == (2, True)


# At 2.32 the module record `T` is what `(record T ...)` names inside a
# procedure whose type parameter is also `T`; from 2.33 the parameter shadows it.
SHADOW_ENTRY = """  (defmodule grt/entry)
  (export run)
  (defrecord T (name String))
  (defrecord Candidate (name String))
  (defrecord Wrap (value T))
  (defproc make :forall (T) ((x T)) -> Wrap :effects () :lowering inline
    (record Wrap :value (record T :name "module")))
  (defworkflow run () -> Wrap (make (record Candidate :name "c")))
)
"""


def test_at_2_32_a_type_parameter_does_not_shadow_a_module_record_in_an_inlined_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_sources(tmp_path, {"grt/entry.orc": HEADER.replace('"2.33"', '"2.32"') + SHADOW_ENTRY})
    files = _public_run_files(tmp_path, {})
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (0, {"return__value__name": "module"})
