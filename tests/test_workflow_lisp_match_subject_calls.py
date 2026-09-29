"""A procedure call written directly as a `match` subject.

Contract: Task 3 of docs/plans/2026-09-29-workflow-lisp-shared-defect-repairs-plan.md;
case c of docs/reports/2026-09-29-workflow-lisp-value-effect-separation-decision-brief.md,
section 2.1. From target 2.33, a subject that calls a generic helper through a hook
whose type uses a type parameter is carried in its typechecked form, so the helper is
specialized like the same call bound with `let*`. Every other subject stays authored,
so a 2.33 program that compiled before keeps its step identities. Targets up to 2.32
keep their earlier acceptance.

The behaviour tests run through the public run entry, and the compatibility tests through
the public compile entry. Hooks are command-backed probes
that append their argv to `<probe>.log`; the arms call the `probe_summarize`
command, so each run's command log ends with the arm that was selected.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from orchestrator.cli.main import main as cli_main
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


# Generic helpers that a 2.33 module could already call as a `match` subject at 5c88cd2d,
# directly and bound with `let*`: one without a hook, which runs a command, and one whose
# hook type does not use its type parameter. Both forms keep the lowered output recorded
# there. The direct form names the authored helper and the bound form the specialized
# procedure, so the two forms had different step identities before this repair and still do.
COMPATIBLE_HELPERS = {
    "inspect": (
        "  (defproc inspect :forall (S) ((subject S)) :where ((S is-record)) -> Checked\n"
        "    :effects ((uses-command probe_check)) :lowering inline\n"
        '    (command-result probe_check :argv ("python" "PROBE_CHECK" "revise-x") :returns Checked))\n',
        '(inspect (record Candidate :title "revise-x" :score 0))',
    ),
    "judge-fixed": (
        "  (defproc judge-fixed :forall (S) ((subject S) (check ProcRef[(Candidate) -> Checked]))\n"
        "    :where ((S is-record)) -> Checked :effects () :lowering inline\n"
        '    (check (record Candidate :title "revise-x" :score 0)))\n',
        '(judge-fixed (record Candidate :title "revise-x" :score 0) (proc-ref check-candidate))',
    ),
}


def _compatible_sources(probes: dict[str, Path], *, helper: str, bound: bool) -> dict[str, str]:
    declaration, call = COMPATIBLE_HELPERS[helper]
    entry = (
        HEADER
        + "  (defmodule grt/entry)\n  (export run)\n"
        + CANDIDATE_CHECK.replace("Outcome[Candidate String]", "Checked")
        + CHECKED
        + declaration
        + SUMMARIZE
        + _run_body(call, CHECK_ARMS, bound=bound)
    )
    return {
        "grt/entry.orc": entry.replace("PROBE_CHECK", probes["probe_check"].as_posix()).replace(
            "PROBE_SUMMARIZE", probes["probe_summarize"].as_posix()
        )
    }


# Checkpoint ids and specialized procedure names hash source spans, which carry the absolute
# source path, so these programs are built at the one fixed path where they were recorded.
COMPAT_ROOT = Path("/tmp/orchestrator-test-match-subject-compat")


def _compat_compile_argv(files: dict[str, Path], out: Path) -> list[str]:
    return [
        "compile", str(files["source"]), "--entry-workflow", "grt/entry::run",
        "--source-root", str(files["source_root"]), "--provider-externs-file", str(files["providers"]),
        "--prompt-externs-file", str(files["prompts"]), "--command-boundaries-file", str(files["commands"]),
        "--emit-executable-ir", str(out / "executable_ir.json"), "--emit-runtime-plan", str(out / "runtime_plan.json"),
    ]  # fmt: skip


def _write_compat_program(root: Path, *, helper: str, bound: bool) -> dict[str, Path]:
    probes = _probes(root, CHECK_PROBES)
    _write_sources(root, _compatible_sources(probes, helper=helper, bound=bound))
    return _public_run_files(root, probes)


def _lowered_identity(monkeypatch: pytest.MonkeyPatch, out: Path, *, helper: str, form: str) -> dict[str, object]:
    """Compile through the public CLI entry at the fixed path; return exit code, ids and the lowered IR digest."""

    root = COMPAT_ROOT / f"{helper}-{form}"
    COMPAT_ROOT.mkdir(exist_ok=True)
    with (COMPAT_ROOT / ".lock").open("w") as lock:  # other pytest workers and sessions share the path
        fcntl.flock(lock, fcntl.LOCK_EX)
        shutil.rmtree(root, ignore_errors=True)
        files = _write_compat_program(root, helper=helper, bound=form == "bound")
        monkeypatch.chdir(root)
        exit_code = cli_main(_compat_compile_argv(files, out))
        shutil.rmtree(root)
    executable_ir = (out / "executable_ir.json").read_bytes()
    runtime_plan = json.loads((out / "runtime_plan.json").read_text(encoding="utf-8"))
    return {
        "exit_code": exit_code,
        "step_ids": sorted(json.loads(executable_ir)["nodes"]),
        "checkpoint_ids": sorted(point["checkpoint_id"] for point in runtime_plan["lexical_checkpoint_points"]),
        "executable_ir_sha256": hashlib.sha256(executable_ir).hexdigest(),
    }


# Recorded at 5c88cd2d, the plan's base commit, from the program `_write_compat_program`
# writes at COMPAT_ROOT/<helper>-<form>, by running from that directory
#   PYTHONHASHSEED=0 python -m orchestrator <the arguments of _compat_compile_argv>
# The values do not depend on the hash seed or on where the orchestrator package lives.
RECORDED_AT_BASE: dict[tuple[str, str], dict[str, object]] = {
    ("inspect", "bound"): {
        "exit_code": 0,
        "step_ids": [
            "root.grt_entry_run__match_result",
            "root.grt_entry_run__match_result.grt_entry_run__match_result__error",
            "root.grt_entry_run__match_result.grt_entry_run__match_result__error.grt_entry_run__match_result__error__grt_entry_summarize_2__probe_summarize",
            "root.grt_entry_run__match_result.grt_entry_run__match_result__ok",
            "root.grt_entry_run__match_result.grt_entry_run__match_result__ok.grt_entry_run__match_result__ok__grt_entry_summarize_1__probe_summarize",
            "root.grt_entry_run__result___parametric_call_grt_entry_inspect_b591f2b7e5c1_1__probe_check",
        ],
        "checkpoint_ids": ["ckpt:12d9b4662581afe2f3133b2d", "ckpt:4042da0aec5170b31d0933bb", "ckpt:47bc60faeb38a6ba597d3373"],
        "executable_ir_sha256": "1701305d71a1a06370e855b196edd30447339cfb77eeb3bb85bbc0aafc5cad4e",
    },
    ("inspect", "direct"): {
        "exit_code": 0,
        "step_ids": [
            "root.grt_entry_run__grt_entry_inspect_1__probe_check",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__error",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__error.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__error__grt_entry_summarize_2__probe_summarize",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__ok",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__ok.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__ok__grt_entry_summarize_1__probe_summarize",
        ],
        "checkpoint_ids": ["ckpt:27f383a6c3f634b8ac1f84d7", "ckpt:43e7743d8721b912f3bccd18", "ckpt:6b73edce6a277a0c06630f37"],
        "executable_ir_sha256": "f9c12b34cde3e3a319b8077b015bb40a8cb3ab81b1d11194099af67c364a5a32",
    },
    ("judge-fixed", "bound"): {
        "exit_code": 0,
        "step_ids": [
            "root.grt_entry_run__match_result",
            "root.grt_entry_run__match_result.grt_entry_run__match_result__error",
            "root.grt_entry_run__match_result.grt_entry_run__match_result__error.grt_entry_run__match_result__error__grt_entry_summarize_2__probe_summarize",
            "root.grt_entry_run__match_result.grt_entry_run__match_result__ok",
            "root.grt_entry_run__match_result.grt_entry_run__match_result__ok.grt_entry_run__match_result__ok__grt_entry_summarize_1__probe_summarize",
            "root.grt_entry_run__result___proc_ref_call_parametric_call_grt_entry_judge_fixed_9ef3054d9d5d_b2bfa7025913_1__check_1__probe_check",
        ],
        "checkpoint_ids": ["ckpt:12d9b4662581afe2f3133b2d", "ckpt:4042da0aec5170b31d0933bb", "ckpt:ec002d60f5502258380c2d2d"],
        "executable_ir_sha256": "ca126de7c5ea8d21de0aad6bf9149ddd15a8b302c1615ccf3515ef31b10452ec",
    },
    ("judge-fixed", "direct"): {
        "exit_code": 0,
        "step_ids": [
            "root.grt_entry_run__grt_entry_judge_fixed_1__check_1__probe_check",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__error",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__error.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__error__grt_entry_summarize_2__probe_summarize",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__ok",
            "root.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__ok.grt_entry_run__match___wcc_effect_subject_ebff489945cd0ca9__ok__grt_entry_summarize_1__probe_summarize",
        ],
        "checkpoint_ids": ["ckpt:27f383a6c3f634b8ac1f84d7", "ckpt:4357c3ccf9f7de2bafe04b25", "ckpt:43e7743d8721b912f3bccd18"],
        "executable_ir_sha256": "08ca1536bbebc43f32bca48f754aaf4e051648fd465999e15e5b7b966b9fa5eb",
    },
}


@pytest.mark.parametrize(("helper", "form"), sorted(RECORDED_AT_BASE))
def test_generic_helper_that_already_compiled_as_match_subject_keeps_its_lowered_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, helper: str, form: str
) -> None:
    """Plan, Global Constraints: a 2.33 program that compiled at the base keeps its lowered output,
    step identities and checkpoint ids."""

    assert _lowered_identity(monkeypatch, tmp_path, helper=helper, form=form) == RECORDED_AT_BASE[(helper, form)]


@pytest.mark.parametrize("helper", sorted(COMPATIBLE_HELPERS))
def test_generic_helper_that_already_compiled_as_match_subject_runs_like_the_let_bound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, helper: str
) -> None:
    direct, bound = _direct_and_bound(
        monkeypatch,
        tmp_path,
        CHECK_PROBES,
        lambda probes, is_bound: _compatible_sources(probes, helper=helper, bound=is_bound),
    )

    assert (direct, direct[1].get("return__outcome")) == (bound, "OK")
