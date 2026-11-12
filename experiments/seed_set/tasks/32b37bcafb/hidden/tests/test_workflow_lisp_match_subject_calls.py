"""A procedure call written directly as a `match` subject.

Contract: Task 3 of docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md;
case c of docs/reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md,
section 2.1. From target 2.33 the typed `match` carries its typechecked subject, so a
generic helper called in subject position is specialized like the same call bound
with `let*`. Targets up to 2.32 keep their earlier acceptance.

Every program runs through the public run entry. Hooks are command-backed probes
that append their argv to `<probe>.log`; the arms call the `probe_summarize`
command, so each run's command log ends with the arm that was selected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_lisp_generic_unions_runtime import (
    _compile,
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.workflow_lisp_generic_union_runtime_sources import CANDIDATE_CHECK, HEADER, OUTCOME_LIB, OUTCOME_PROBE
from tests.workflow_lisp_improve_stdlib_sources import REVIEW_PROBE, REVISE_PROBE, SUMMARIZE_PROBE, entry_source


SUMMARIZE = """  (defrecord Summary (outcome String) (title String) (score Int))
  (defproc summarize ((outcome String) (candidate Candidate)) -> Summary
    :effects ((uses-command probe_summarize))
    :lowering inline
    (command-result probe_summarize
      :argv ("python" "PROBE_SUMMARIZE" outcome candidate.title candidate.score)
      :returns Summary))
"""

IMPROVE_CALL = (
    '(improve (record Candidate :title "SEED" :score 0) (record Brief :goal "tidy")'
    " (proc-ref review-candidate) (proc-ref revise-candidate) 2)"
)
IMPROVE_ARMS = (
    '((APPROVED approved) (summarize "APPROVED" approved.value))'
    ' ((BLOCKED blocked) (summarize "BLOCKED" blocked.value))'
    ' ((EXHAUSTED exhausted) (summarize "EXHAUSTED" exhausted.value))'
)

CHECK_ARMS = '((OK ok) (summarize "OK" ok.value)) ((ERROR err) (summarize err.error (record Candidate :title "none" :score 0)))'

# `Checked` has the shape of `Outcome[Candidate String]`, so `OUTCOME_PROBE` answers for both.
CHECKED = "  (defunion Checked (OK (value Candidate)) (ERROR (error String)))\n"

# Helpers that take a `check` hook and return its union. `attempt` is generic over the
# generic union `Outcome[T E]` (imported from `OUTCOME_LIB`); `judge` is generic over the
# plain union `Checked`, which a target-2.32 module can also write; `judge-concrete` is
# not generic.
CHECK_HELPERS = {
    "attempt": ("  (import grt/lib :only (Outcome attempt))\n", "", "attempt"),
    "judge": (
        "",
        CHECKED
        + "  (defproc judge :forall (S) ((subject S) (check ProcRef[(S) -> Checked])) :where ((S is-record))\n"
        + "    -> Checked :effects () :lowering inline (check subject))\n",
        "judge",
    ),
    "judge-concrete": (
        "",
        CHECKED
        + "  (defproc judge ((subject Candidate) (check ProcRef[(Candidate) -> Checked])) -> Checked\n"
        + "    :effects () :lowering inline (check subject))\n",
        "judge",
    ),
}


def _run_body(call: str, arms: str, *, bound: bool) -> str:
    match = f"(match result {arms})" if bound else f"(match {call} {arms})"
    body = f"(let* ((result {call})) {match})" if bound else match
    return f"  (defworkflow run () -> Summary\n    {body}))\n"


def _improve_sources(probes: dict[str, Path], *, seed: str, bound: bool) -> dict[str, str]:
    entry = entry_source(seed=seed, limit=2, probes=probes)
    prefix = entry[: entry.index("  (defworkflow run")]
    call = IMPROVE_CALL.replace("SEED", seed)
    summarize = SUMMARIZE.replace("PROBE_SUMMARIZE", probes["probe_summarize"].as_posix())
    return {"grt/entry.orc": prefix + summarize + _run_body(call, IMPROVE_ARMS, bound=bound)}


def _check_sources(
    probes: dict[str, Path], *, helper: str, seed: str, bound: bool, target: str = "2.33"
) -> dict[str, str]:
    imports, declarations, callee = CHECK_HELPERS[helper]
    check = CANDIDATE_CHECK.replace("PROBE_CHECK", probes["probe_check"].as_posix())
    if helper != "attempt":
        check = check.replace("Outcome[Candidate String]", "Checked")
    entry = (
        HEADER.replace('"2.33"', f'"{target}"')
        + "  (defmodule grt/entry)\n"
        + imports
        + "  (export run)\n"
        + check
        + declarations
        + SUMMARIZE.replace("PROBE_SUMMARIZE", probes["probe_summarize"].as_posix())
        + _run_body(f'({callee} (record Candidate :title "{seed}" :score 0) (proc-ref check-candidate))', CHECK_ARMS, bound=bound)
    )
    return {"grt/lib.orc": OUTCOME_LIB, "grt/entry.orc": entry} if helper == "attempt" else {"grt/entry.orc": entry}


IMPROVE_PROBES = (("probe_review", REVIEW_PROBE), ("probe_revise", REVISE_PROBE), ("probe_summarize", SUMMARIZE_PROBE))
CHECK_PROBES = (("probe_check", OUTCOME_PROBE), ("probe_summarize", SUMMARIZE_PROBE))


def _probes(root: Path, texts: tuple[tuple[str, str], ...]) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    return {name: _write_probe(root, name, text) for name, text in texts}


def _public_outcome(monkeypatch: pytest.MonkeyPatch, root: Path, probes: dict[str, Path], sources: dict[str, str]):
    """Run through the public entry; return the exit code, the outputs and each probe's ordered log."""

    _write_sources(root, sources)
    monkeypatch.chdir(root)
    result = _public_run(_public_run_files(root, probes))
    return result.exit_code, dict(result.workflow_outputs), {name: _log(path) for name, path in probes.items()}


def _direct_and_bound(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, texts, make_sources):
    outcomes = []
    for form in ("direct", "bound"):
        probes = _probes(tmp_path / form, texts)
        outcomes.append(_public_outcome(monkeypatch, tmp_path / form, probes, make_sources(probes, form == "bound")))
    return tuple(outcomes)


@pytest.mark.parametrize(
    ("seed", "variant"),
    [("approve", "APPROVED"), ("block", "BLOCKED"), ("draft", "EXHAUSTED")],
)
def test_improve_call_as_match_subject_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: str, variant: str
) -> None:
    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        IMPROVE_PROBES,
        lambda probes, is_bound: _improve_sources(probes, seed=seed, bound=is_bound),
    )

    assert (direct, direct[1].get("return__outcome")) == (bound, variant)


@pytest.mark.parametrize(("seed", "variant"), [("revise-x", "OK"), ("plain", "revise-plain")])
def test_second_generic_helper_over_another_generic_union_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: str, variant: str
) -> None:
    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        CHECK_PROBES,
        lambda probes, is_bound: _check_sources(probes, helper="attempt", seed=seed, bound=is_bound),
    )

    assert (direct, direct[1].get("return__outcome")) == (bound, variant)


def test_generic_helper_over_a_plain_union_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        CHECK_PROBES,
        lambda probes, is_bound: _check_sources(probes, helper="judge", seed="revise-x", bound=is_bound),
    )

    assert (direct, direct[1].get("return__outcome")) == (bound, "OK")


@pytest.mark.parametrize(("seed", "variant"), [("revise-x", "OK"), ("plain", "revise-plain")])
def test_target_232_non_generic_helper_with_a_hook_as_match_subject_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: str, variant: str
) -> None:
    """Control: this form compiles below 2.33 at the base commit and must keep doing so."""

    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        CHECK_PROBES,
        lambda probes, is_bound: _check_sources(
            probes, helper="judge-concrete", seed=seed, bound=is_bound, target="2.32"
        ),
    )

    assert (direct, direct[1].get("return__outcome")) == (bound, variant)


def test_target_232_generic_helper_as_match_subject_keeps_its_earlier_rejection(tmp_path: Path) -> None:
    """Targets up to 2.32 accept exactly what they accepted before the repair (plan, Global Constraints)."""

    probes = _probes(tmp_path, CHECK_PROBES)
    sources = _check_sources(probes, helper="judge", seed="revise-x", bound=False, target="2.32")
    entry = _write_sources(tmp_path, sources)

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path, probes=probes)

    diagnostic = excinfo.value.diagnostics[0]
    lines = sources["grt/entry.orc"].splitlines()
    line = next(number for number, text in enumerate(lines, start=1) if "(match (judge" in text)
    assert (diagnostic.code, Path(diagnostic.span.start.path), diagnostic.span.start.line, diagnostic.span.start.column) == (
        "proc_ref_signature_invalid",
        entry,
        line,
        lines[line - 1].index("(proc-ref check-candidate)") + 1,
    )
