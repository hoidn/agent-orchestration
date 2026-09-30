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
Targets 2.30 to 2.32 keep their behaviour. Program tests use the public run
entry and command-backed effects. Owner checks cover two carried-type cases
not reached by the public programs tried here.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.definitions import RecordDef, RecordField, UnionDef, UnionVariant
from orchestrator.workflow_lisp.expressions import ListExpr, LiteralExpr, NameExpr, RecordExpr, UnionVariantExpr
from orchestrator.workflow_lisp.lowering.control_loops import _loop_seed_pure_projection_expr
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment, ListTypeRef, PrimitiveTypeRef, RecordTypeRef, UnionTypeRef,
)
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


# `make` builds the hidden `Private` inside the visible `Outer`. The public
# program returns that value after using it as a `loop-state` seed.
SEED_LIB = """  (defmodule grt/lib)
  (export Outer make)
  (defrecord Private (word String))
  (defrecord Outer (value Private) (tags List[String]))
  (defproc make () -> Outer :effects () :lowering inline
    (record Outer :value (record Private :word "x") :tags (list "x")))
)
"""

SEED_ENTRY = """  (defmodule grt/entry)
  (import grt/lib :only (Outer make))
  (export run)
  (defworkflow run () -> Outer
    (loop/recur :max 3
      :state (loop-state (current Outer (make)) (n Int 0))
      :on-exhausted state.current
      (fn (state) (if (= state.n 1) (done state.current) (continue (loop-state :like state :n (+ state.n 1)))))))
)
"""

# The same seed rebuild inside an imported inlined body: its loop-state type is
# generated from the library's procedure.
LOOP_LIB = """  (defmodule grt/lib)
  (export Outer make)
  (defrecord Private (word String))
  (defrecord Outer (value Private) (tags List[String]))
  (defproc make () -> Outer :effects () :lowering inline
    (loop/recur :max 3
      :state (loop-state (tags List[String] (list "x")) (n Int 0))
      :on-exhausted (record Outer :value (record Private :word "exhausted") :tags state.tags)
      (fn (state)
        (if (= state.n 1)
          (done (record Outer :value (record Private :word "done") :tags state.tags))
          (continue (loop-state :like state :n (+ state.n 1)))))))
)
"""

LOOP_ENTRY = """  (defmodule grt/entry)
  (import grt/lib :only (Outer make))
  (export run)
  (defworkflow run () -> Outer (make))
)
"""


@pytest.mark.parametrize(
    ("lib", "entry", "expected"),
    [
        (SEED_LIB, SEED_ENTRY, {"return__value__word": "x", "return__tags": ("x",)}),
        (LOOP_LIB, LOOP_ENTRY, {"return__value__word": "done", "return__tags": ("x",)}),
    ],
    ids=["seed-from-imported-body", "loop-in-imported-body"],
)
def test_imported_loop_programs_return_private_record_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lib: str, entry: str, expected: dict[str, object]
) -> None:
    _write_sources(tmp_path, {"grt/lib.orc": HEADER + lib, "grt/entry.orc": HEADER + entry})
    files = _public_run_files(tmp_path, {})
    monkeypatch.chdir(tmp_path)

    result = _public_run(files)

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (0, expected)


# `check` is inlined at two specializations; the public program reads both
# results through their corresponding record fields.
TWO_SPECIALIZATIONS = """  (defmodule grt/entry)
  (export run)
  (defrecord Cand (title String))
  (defrecord Other (name String))
""" + GENERICS + """  (defworkflow make-a ((ok Bool)) -> Outcome[Cand String] (check (record Cand :title "a") ok))
  (defworkflow make-b ((ok Bool)) -> Outcome[Other String] (check (record Other :name "b") ok))
  (defrecord Seen (a String) (b String))
  (defworkflow run ((ok Bool)) -> Seen
    (let* ((a (call make-a :ok ok)) (b (call make-b :ok ok)))
      (record Seen
        :a (match a ((OK hit) hit.value.title) ((ERR miss) miss.error))
        :b (match b ((OK hit) hit.value.name) ((ERR miss) miss.error)))))
)
"""


@pytest.mark.parametrize(("ok", "expected"), [("true", ("a", "b")), ("false", ("rejected", "rejected"))])
def test_two_specialized_workflows_return_their_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ok: str, expected: tuple[str, str]
) -> None:
    _write_sources(tmp_path, {"grt/entry.orc": HEADER + TWO_SPECIALIZATIONS})
    files = _public_run_files(tmp_path, {})
    (tmp_path / "inputs.json").write_text(f'{{"ok": {ok}}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = _public_run(files, input_file=tmp_path / "inputs.json")

    assert (result.exit_code, dict(result.workflow_outputs or {})) == (
        0,
        {"return__a": expected[0], "return__b": expected[1]},
    )


@pytest.mark.parametrize("kind", ["record", "union"])
def test_equal_source_constructors_with_different_carried_types_are_distinct_keys(kind: str) -> None:
    """No public program among four tested shapes distinguishes these nodes today."""

    position = SourcePosition("probe.orc", 1, 1, 0)
    span = SourceSpan(position, position)
    if kind == "record":
        first_type = RecordTypeRef("First", RecordDef("First", (), span), {})
        second_type = RecordTypeRef("Second", RecordDef("Second", (), span), {})
        constructor = lambda typ: RecordExpr("Same", (), span, ("record",), resolved_type=typ)
    else:
        variant = UnionVariant("OK", (), span)
        first_type = UnionTypeRef("First", UnionDef("First", (variant,), span), {"OK": {}})
        second_type = UnionTypeRef("Second", UnionDef("Second", (variant,), span), {"OK": {}})
        constructor = lambda typ: UnionVariantExpr("Same", "OK", (), span, ("variant",), resolved_type=typ)

    first, second = constructor(first_type), constructor(second_type)
    values = {first: "first", second: "second"}

    assert first != second
    assert len(values) == 2
    assert (values[first], values[second]) == ("first", "second")


def test_rebuilt_loop_seed_resolves_its_private_carried_type() -> None:
    """No public program among three tested shapes needs this carried seed type today."""

    position = SourcePosition("probe.orc", 1, 1, 0)
    span = SourceSpan(position, position)
    string_type = PrimitiveTypeRef("String")
    list_type = ListTypeRef("List[String]", string_type)
    seed_type = RecordTypeRef(
        "PrivateSeed",
        RecordDef("PrivateSeed", (RecordField("marks", "List[String]", span),), span),
        {"marks": list_type},
    )
    marks = ListExpr((LiteralExpr("m", "string", span, ("list",)),), string_type, span, ("list",))
    rebuilt = _loop_seed_pure_projection_expr(
        NameExpr("seed", span, ("loop",)),
        state_type=seed_type,
        local_values={"seed": {"marks": marks}},
    )

    assert isinstance(rebuilt, RecordExpr)
    assert rebuilt.resolved_type is seed_type
    assert FrontendTypeEnvironment({}, target_dsl_version="2.33").resolve_constructor_type(rebuilt) is seed_type
