"""Task 2 of the shared defect repairs plan: effect inference includes imported procedures.

Contract: docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md,
Task 2 and Review Focus item 1; decision brief
docs/reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md,
case a of section 2.1.

From target 2.33 a local procedure that calls an imported effectful procedure
carries the callee's effects: it must declare them, it is not inlined as if it
were pure, and a `std/improve` helper specialized with an imported hook lists
the hook's effects. Targets up to 2.32 keep the result they gave at
`7984b51e`; each 2.33 source below has a 2.32 control.

Effects are command-backed probes that append their argv to `<probe>.log`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import UsesCommandEffect
from tests.test_workflow_lisp_generic_unions_runtime import (
    _compile,
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.workflow_lisp_improve_stdlib_sources import (
    REVIEW_PROBE,
    REVISE_PROBE,
    SUMMARIZE_PROBE,
    unnamed_union_caller_sources,
)


CHECK_PROBE = """import json, os, sys
from pathlib import Path
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
title = sys.argv[1]
if title.startswith("a"):
    payload = {"variant": "PASS", "note": {"text": "ok:" + title}}
else:
    payload = {"variant": "FAIL", "why": {"text": "no:" + title}}
bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    Path(bundle).parent.mkdir(parents=True, exist_ok=True)
    Path(bundle).write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
"""

LIB = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/lib)
  (export Text Verdict check)
  (defrecord Text (text String))
  (defunion Verdict (PASS (note Text)) (FAIL (why Text)))
  (defproc check ((title String)) -> Verdict
    :effects ((uses-command probe_check))
    :lowering inline
    (command-result probe_check :argv ("python" "PROBE_CHECK" title) :returns Verdict)))
"""

ENTRY = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (import grt/lib :only (Text Verdict check))
  (export run)
  (defproc check-wrap ((title String)) -> Verdict
    :effects EFFECTS
    :lowering inline
    (check title))
BODY)
"""

DECLARED = "((uses-command probe_check))"
UNDECLARED = "()"

BODIES = {
    "match-subject": """  (defworkflow run () -> Text
    (match (check-wrap "alpha")
      ((PASS p) p.note)
      ((FAIL f) f.why)))""",
    "let-binding": """  (defworkflow run () -> Text
    (let* ((verdict (check-wrap "alpha")))
      (match verdict
        ((PASS p) p.note)
        ((FAIL f) f.why))))""",
    "tail": """  (defworkflow run () -> Verdict
    (check-wrap "alpha"))""",
}

CHECK_EFFECT = UsesCommandEffect(subject=("probe_check",))


def _wrapper_project(root: Path, *, target: str, effects: str, body: str) -> dict[str, Path]:
    probes = {"probe_check": _write_probe(root, "probe_check", CHECK_PROBE)}
    _write_sources(
        root,
        {
            "grt/lib.orc": LIB.replace("TARGET", target).replace("PROBE_CHECK", probes["probe_check"].as_posix()),
            "grt/entry.orc": ENTRY.replace("TARGET", target).replace("EFFECTS", effects).replace("BODY", BODIES[body]),
        },
    )
    return probes


def _run(root: Path, probes: dict[str, Path], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(root)
    result = _public_run(_public_run_files(root, probes))
    return result.exit_code, dict(result.workflow_outputs), _log(probes["probe_check"])


def _rejection(root: Path, probes: dict[str, Path]) -> tuple[str, Path, int, str]:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(root, probes=probes)
    diagnostic = excinfo.value.diagnostics[0]
    return diagnostic.code, Path(diagnostic.span.start.path), diagnostic.span.start.line, diagnostic.message


def _wrapper_line(root: Path) -> int:
    lines = (root / "grt" / "entry.orc").read_text(encoding="utf-8").splitlines()
    return next(number for number, line in enumerate(lines, start=1) if "(defproc check-wrap" in line)


# Target 2.33.


def test_wrapper_of_an_imported_command_carries_the_command_in_its_transitive_summary(tmp_path: Path) -> None:
    probes = _wrapper_project(tmp_path, target="2.33", effects=DECLARED, body="tail")

    wrapper = next(
        procedure
        for procedure in _compile(tmp_path, probes=probes).entry_result.typed_procedures
        if procedure.definition.name == "grt/entry::check-wrap"
    )

    assert wrapper.transitive_effect_summary.transitive_effects == frozenset({CHECK_EFFECT})


@pytest.mark.parametrize("body", ["match-subject", "let-binding"])
def test_wrapper_result_as_match_subject_or_let_binding_returns_the_command_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str
) -> None:
    """Both forms return the same value with the same command log."""

    probes = _wrapper_project(tmp_path, target="2.33", effects=DECLARED, body=body)

    assert _run(tmp_path, probes, monkeypatch) == (0, {"return__text": "ok:alpha"}, ["alpha"])


def test_wrapper_declaring_no_effects_is_rejected_naming_the_missing_effect(tmp_path: Path) -> None:
    probes = _wrapper_project(tmp_path, target="2.33", effects=UNDECLARED, body="tail")

    code, path, line, message = _rejection(tmp_path, probes)

    assert (code, path, line, "uses-command(probe_check)" in message) == (
        "procedure_effect_mismatch",
        tmp_path / "grt" / "entry.orc",
        _wrapper_line(tmp_path),
        True,
    )


def _improve_project(root: Path, *, target: str) -> dict[str, Path]:
    probes = {
        name: _write_probe(root, name, text)
        for name, text in (
            ("probe_review", REVIEW_PROBE),
            ("probe_revise", REVISE_PROBE),
            ("probe_summarize", SUMMARIZE_PROBE),
        )
    }
    _write_sources(root, unnamed_union_caller_sources(seed="draft", limit=2, target=target, probes=probes))
    return probes


def _specialized_improve_effects(root: Path, probes: dict[str, Path]) -> frozenset:
    return next(
        procedure.transitive_effect_summary.transitive_effects
        for procedure in _compile(root, probes=probes).entry_result.typed_procedures
        if getattr(procedure.specialization, "base_name", "") == "std/improve::improve"
    )


def test_hook_imported_from_another_module_is_in_the_specialized_improve_summary(tmp_path: Path) -> None:
    """`assess` lives in `grt/assess` and reaches `improve` by `proc-ref`."""

    probes = _improve_project(tmp_path, target="2.33")

    assert _specialized_improve_effects(tmp_path, probes) == frozenset(
        {UsesCommandEffect(subject=("probe_review",)), UsesCommandEffect(subject=("probe_revise",))}
    )


# Target 2.32 controls: each source above, retargeted, gives its result at `7984b51e`.


@pytest.mark.parametrize("body", ["tail", "match-subject", "let-binding"])
def test_target_232_wrapper_declaring_the_imported_command_keeps_the_mismatch_rejection(
    tmp_path: Path, body: str
) -> None:
    probes = _wrapper_project(tmp_path, target="2.32", effects=DECLARED, body=body)

    code, path, line, message = _rejection(tmp_path, probes)

    assert (code, path, line, message.endswith("but inferred ()")) == (
        "procedure_effect_mismatch",
        tmp_path / "grt" / "entry.orc",
        _wrapper_line(tmp_path),
        True,
    )


def test_target_232_wrapper_declaring_no_effects_still_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probes = _wrapper_project(tmp_path, target="2.32", effects=UNDECLARED, body="tail")

    assert _run(tmp_path, probes, monkeypatch) == (
        0,
        {"return__variant": "PASS", "return__note__text": "ok:alpha"},
        ["alpha"],
    )


def test_target_232_specialized_improve_summary_keeps_its_result(tmp_path: Path) -> None:
    probes = _improve_project(tmp_path, target="2.32")

    assert _specialized_improve_effects(tmp_path, probes) == frozenset({UsesCommandEffect(subject=("probe_revise",))})
